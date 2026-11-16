// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_live_sound.cpp -o /tmp/test_live_sound && /tmp/test_live_sound
// A live camera's sound (live_view.h): what the stream's task lets into the sound buffer (sound_part), when the main loop
// plays (sound_on), how it hands the buffer to the speaker (SoundPump, with a buffer and a speaker of its own here), and
// what the stream claims of the audio owner and gives back (SoundClaim, with an Owner of its own here). live_view.cpp
// runs the same over FreeRTOS's stream buffer, the board's speaker and audio_owner::the().
#include "../components/smart_display/live_view.h"
#include <cassert>
#include <cstdio>
#include <deque>
#include <string>
#include <vector>

using namespace live_view;
using audio_owner::Owner;
using audio_owner::Role;
using audio_owner::Side;

// The sound buffer: bytes in the order they came.
struct Buffer {
  std::deque<uint8_t> bytes;
  void put(size_t n, uint8_t first = 0) {
    for (size_t i = 0; i < n; ++i) bytes.push_back(static_cast<uint8_t>(first + i));
  }
  size_t held() const { return bytes.size(); }
  size_t take(uint8_t *into, size_t most) {
    size_t n = 0;
    for (; n < most && !bytes.empty(); ++n) {
      into[n] = bytes.front();
      bytes.pop_front();
    }
    return n;
  }
};
// The speaker: takes up to `room` bytes a write (0: full), and keeps what it played.
struct Speaker {
  size_t room = SOUND_PART;
  bool started = false;
  int starts = 0, stops = 0;
  std::vector<uint8_t> played;
  void start() { started = true, ++starts; }
  void stop() { started = false, ++stops; }
  size_t play(const uint8_t *data, size_t n) {
    const size_t taken = std::min(n, room);
    played.insert(played.end(), data, data + taken);
    return taken;
  }
};

int main() {
  // A part goes in whole samples, all of it or nothing, never cut to the room left; nothing while held back.
  {
    SoundPart p = sound_part(4096, SOUND_BUFFER, false);
    assert(p.send == 4096 && !p.full);
    p = sound_part(4095, SOUND_BUFFER, false);  // an odd part: its last byte, half a sample, stays out
    assert(p.send == 4094 && !p.full);
    p = sound_part(4096, 4094, false);  // room for all but one sample: none of it, counted
    assert(p.send == 0 && p.full);
    p = sound_part(4095, 4094, false);  // the odd part's whole samples fit exactly
    assert(p.send == 4094 && !p.full);
    p = sound_part(4096, SOUND_BUFFER, true);  // muted, or the speaker someone else's: nothing, and not counted as full
    assert(p.send == 0 && !p.full);
    for (size_t length = 1; length < 64; ++length)
      for (size_t space = 0; space < 64; ++space) {
        const SoundPart q = sound_part(length, space, false);
        assert(q.send % 2 == 0 && q.send <= space && (q.send == (length & ~size_t(1)) || q.send == 0));
      }
  }
  // The main loop plays only a stream that runs, not muted and holding the speaker.
  assert(sound_on(false, false, false));
  assert(!sound_on(true, false, false) && !sound_on(false, true, false) && !sound_on(false, false, true));

  uint8_t piece[SOUND_PART];
  // The run-up: nothing reaches the speaker until SOUND_LOW waits, then it starts once and plays.
  {
    SoundPump pump;
    Buffer buffer;
    Speaker speaker;
    buffer.put(SOUND_LOW - 2);
    pump.tick(true, false, 0, piece, buffer, speaker);
    assert(!speaker.started && speaker.played.empty() && buffer.held() == SOUND_LOW - 2);
    buffer.put(2);
    pump.tick(true, false, 50, piece, buffer, speaker);
    assert(speaker.started && speaker.starts == 1 && speaker.played.size() == SOUND_LOW && buffer.held() == 0);
    // Off (stopped, muted or taken): the speaker stops, and what it had not taken is not played later.
    buffer.put(100);
    speaker.room = 10;
    pump.tick(true, false, 100, piece, buffer, speaker);  // eight writes of 10 a tick
    assert(pump.piece_left == 20);
    pump.tick(false, false, 150, piece, buffer, speaker);
    assert(!speaker.started && speaker.stops == 1 && pump.piece_left == 0);
  }
  // Ran dry while speaking: no more until a run-up waits again, instead of each part as it trickles in.
  {
    SoundPump pump;
    Buffer buffer;
    Speaker speaker;
    buffer.put(SOUND_LOW);
    pump.tick(true, false, 0, piece, buffer, speaker);
    pump.tick(true, false, 50, piece, buffer, speaker);  // nothing waits: dry
    assert(pump.dry && pump.ran_dry == 1);
    buffer.put(SOUND_PART);
    pump.tick(true, false, 100, piece, buffer, speaker);
    assert(speaker.played.size() == SOUND_LOW && buffer.held() == SOUND_PART);
    buffer.put(SOUND_LOW - SOUND_PART);
    pump.tick(true, false, 150, piece, buffer, speaker);
    assert(!pump.dry && speaker.played.size() == 2 * SOUND_LOW && speaker.starts == 1);
  }
  // A conversation: a run-up of SOUND_TALK_LOW, and dry only once its sound has been gone SOUND_TALK_GONE_MS.
  {
    SoundPump pump;
    Buffer buffer;
    Speaker speaker;
    buffer.put(SOUND_TALK_LOW);
    pump.tick(true, true, 1000, piece, buffer, speaker);
    assert(speaker.started && speaker.played.size() == SOUND_TALK_LOW);
    pump.tick(true, true, 1000 + SOUND_TALK_GONE_MS, piece, buffer, speaker);
    assert(!pump.dry);
    pump.tick(true, true, 1001 + SOUND_TALK_GONE_MS, piece, buffer, speaker);
    assert(pump.dry && pump.ran_dry == 1);
  }
  // Behind the picture: above SOUND_HIGH the oldest goes, down to SOUND_LOW, also while the speaker is full; the
  // newest is what plays next.
  {
    SoundPump pump;
    Buffer buffer;
    Speaker speaker;
    buffer.put(SOUND_LOW);
    pump.tick(true, false, 0, piece, buffer, speaker);
    speaker.room = 0;  // full: takes nothing
    buffer.put(SOUND_HIGH + 2, 7);
    pump.tick(true, false, 50, piece, buffer, speaker);
    assert(pump.caught_up == 1 && buffer.held() + pump.piece_left == SOUND_LOW);
    assert(pump.caught_up_bytes == SOUND_HIGH + 2 - SOUND_LOW);
    // At SOUND_HIGH or below nothing goes.
    buffer.bytes.clear();
    pump.piece_left = 0;
    buffer.put(SOUND_HIGH);
    pump.tick(true, false, 100, piece, buffer, speaker);
    assert(pump.caught_up == 1 && buffer.held() + pump.piece_left == SOUND_HIGH);
    // A conversation catches up above SOUND_TALK_HIGH, to SOUND_TALK_LOW.
    SoundPump talk;
    Buffer said;
    Speaker full;
    said.put(SOUND_TALK_LOW);
    talk.tick(true, true, 0, piece, said, full);
    full.room = 0;
    said.put(SOUND_TALK_HIGH + 2);
    talk.tick(true, true, 50, piece, said, full);
    assert(talk.caught_up == 1 && said.held() + talk.piece_left == SOUND_TALK_LOW);
  }
  // Whole samples to the speaker: a write it took an odd number of bytes of goes on from the very next byte, and no
  // catching up cuts a piece in the middle of a sample.
  {
    SoundPump pump;
    Buffer buffer;
    Speaker speaker;
    buffer.put(SOUND_LOW);
    speaker.room = 3;
    pump.tick(true, false, 0, piece, buffer, speaker);
    assert(speaker.played.size() == 24 && pump.odd_taken == 8 && pump.piece_at % 2 == 0);  // eight writes of 3, a round
    speaker.room = 1;
    pump.tick(true, false, 50, piece, buffer, speaker);
    assert(pump.piece_at % 2 == 0 && pump.odd_taken == 16);
    speaker.room = 1;
    buffer.put(SOUND_HIGH + 2);
    const size_t before = pump.caught_up;
    pump.tick(true, false, 100, piece, buffer, speaker);  // eight writes of 1 leave it even: it catches up
    assert(pump.caught_up == before + 1);
    speaker.room = 3;
    pump.tick(true, false, 150, piece, buffer, speaker);
    assert(pump.piece_at % 2 == 0);
    // Every byte played is the next one of the stream: nothing skipped or played twice inside a piece.
    for (size_t i = 1; i < 32; ++i) assert(speaker.played[i] == static_cast<uint8_t>(speaker.played[i - 1] + 1));
    // An odd write leaves the next tick in the middle of a sample: it does not catch up until it is whole again.
    SoundPump odd;
    Buffer b;
    Speaker s;
    b.put(SOUND_LOW);
    odd.tick(true, false, 0, piece, b, s);
    s.room = 0;
    b.put(SOUND_HIGH + 2);
    odd.piece_left = 5;
    odd.piece_at = 9;
    odd.tick(true, false, 50, piece, b, s);
    assert(odd.caught_up == 0 && odd.piece_left == 5);
    odd.piece_at = 10;
    odd.tick(true, false, 100, piece, b, s);
    assert(odd.caught_up == 1 && b.held() + odd.piece_left == SOUND_LOW);
  }

  // The stream's claim on the speaker, against an owner that runs as the screen's does.
  {
    // A camera opened: music pauses for it (its `lost`), and the camera's sound plays.
    Owner owner;
    std::vector<std::string> said;
    audio_owner::Claim music;
    music.role = Role::MEDIA;
    music.lost = [&said] { said.push_back("music paused"); };
    assert(owner.claim(Side::OUT, music));
    SoundClaim camera;
    int emptied = 0;
    camera.claim(owner, true, Role::CAMERA_SOUND, 2, [&emptied] { ++emptied; });
    assert(camera.claims && owner.holder(Side::OUT) == Role::CAMERA_SOUND && !owner.held(Side::IN));
    assert(said == std::vector<std::string>{"music paused"} && !camera.yielded);
    // A voice session takes the speaker: the sound is held back and what waited goes; back once the session ends.
    audio_owner::Claim voice;
    voice.role = Role::VOICE;
    assert(owner.claim(Side::BOTH, voice));
    assert(camera.yielded && emptied == 1);
    assert(!sound_on(false, false, camera.yielded) && sound_part(4096, SOUND_BUFFER, camera.yielded).send == 0);
    owner.release(Side::BOTH, Role::VOICE);
    assert(!camera.yielded && owner.holder(Side::OUT) == Role::CAMERA_SOUND);
    // Closed: the speaker is free, the music does not come back by itself, and a second release changes nothing.
    camera.release(owner);
    assert(!owner.held(Side::OUT) && !camera.claims);
    camera.release(owner);
    assert(!owner.held(Side::OUT));
  }
  {
    // A view without sound, or on a board without a speaker, claims nothing.
    Owner owner;
    SoundClaim quiet;
    quiet.claim(owner, false, Role::CAMERA_SOUND, 0, {});
    assert(!quiet.claims && !owner.held(Side::OUT));
    // A ring's view claims nothing of its own: the ring holds both sides (module_doorbell), and closing the view
    // leaves that claim alone, so the wake word still rests while the ring is up.
    audio_owner::Claim ring;
    ring.role = Role::DOORBELL;
    ring.id = 7;
    assert(owner.claim(Side::BOTH, ring));
    SoundClaim view;
    view.claim(owner, true, Role::DOORBELL, 0, {});
    assert(!view.claims);
    view.release(owner);
    assert(owner.holder(Side::OUT) == Role::DOORBELL && owner.holder(Side::IN) == Role::DOORBELL);
    // A camera opened meanwhile is refused the speaker: the ring outranks it.
    SoundClaim camera;
    camera.claim(owner, true, Role::CAMERA_SOUND, 1, {});
    assert(owner.holder(Side::OUT) == Role::DOORBELL);
    camera.release(owner);
    assert(owner.holder(Side::OUT) == Role::DOORBELL);
  }
  // The role a full view's sound claims (live_begin): a ring's view the ring's, a call's the call's, any other a camera's.
  static_assert(view_role(false, false) == Role::CAMERA_SOUND);
  static_assert(view_role(true, false) == Role::DOORBELL);
  static_assert(view_role(false, true) == Role::CALL);
  static_assert(view_role(true, true) == Role::CALL, "a call over a ring is the call");
  std::puts("live sound: whole samples, run-up, catching up, claimed and given back");
  return 0;
}
