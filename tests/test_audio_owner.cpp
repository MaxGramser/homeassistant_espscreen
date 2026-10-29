// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_audio_owner.cpp -o /tmp/test_audio_owner && /tmp/test_audio_owner
// Who may play and who may listen (audio_owner.h), driven as the screen drives it: music, a camera's sound, the wake
// word, a voice session and a doorbell, each claiming and releasing; what each hears back (lost, regained), who holds
// each side after every step, and that a lower role is refused and a waiting claim comes back in rank.
#include "../components/smart_display/audio_owner.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

using namespace audio_owner;

struct Log {
  std::vector<std::string> lines;
  Callback say(const char *what) {
    return [this, what] { lines.push_back(what); };
  }
  std::string joined() const {
    std::string s;
    for (const auto &l : lines) s += (s.empty() ? "" : ",") + l;
    return s;
  }
  void clear() { lines.clear(); }
};

static Claim make(Role role, uint32_t id, Callback lost, Callback regained = {}) {
  Claim c;
  c.role = role;
  c.id = id;
  c.lost = std::move(lost);
  c.regained = std::move(regained);
  return c;
}

int main() {
  // 1. Music plays; a camera's full view with sound opens: music loses OUT and does not come back when the camera
  //    closes (no regained): "muziek hervat niet vanzelf".
  {
    Owner o;
    Log log, said;
    o.log = [&](const char *line) { said.lines.push_back(line); };
    assert(o.claim(Side::OUT, make(Role::MEDIA, 0, log.say("media lost"))));
    assert(o.held(Side::OUT) && o.holder(Side::OUT) == Role::MEDIA);
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("camera lost"), log.say("camera back"))));
    assert(log.joined() == "media lost");
    assert(o.holder(Side::OUT) == Role::CAMERA_SOUND);
    assert(o.waiting(Side::OUT) == 0);  // music did not ask to come back
    o.release(Side::OUT, Role::CAMERA_SOUND, 1);
    assert(!o.held(Side::OUT));
    assert(log.joined() == "media lost");
    // What the screen logs of it, one line a change: the proof read off the glass.
    assert(said.joined() == "media holds the speaker,camera took the speaker from media,camera gave the speaker back");
    assert(!o.claim(Side::OUT, make(Role::MEDIA, 0, {})) == false);  // free again: granted
    assert(!o.claim(Side::OUT, make(Role::DOORBELL, 7, {})) == false);
    assert(!o.claim(Side::OUT, make(Role::MEDIA, 0, {})));          // refused under the ring
    assert(said.lines.back() == std::string("media refused the speaker: doorbell holds it"));
  }

  // 2. A camera's sound plays; the wake word is heard and a voice session claims BOTH: the camera's sound loses OUT and
  //    comes back after the session, since the camera is still open.
  {
    Owner o;
    Log log;
    assert(o.claim(Side::IN, make(Role::VOICE, 0, log.say("wake lost"), log.say("wake back"))));  // listening
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("camera lost"), log.say("camera back"))));
    assert(o.holder(Side::IN) == Role::VOICE && o.holder(Side::OUT) == Role::CAMERA_SOUND);
    // The session: the same role and id as the listening claim, now for both sides.
    assert(o.claim(Side::BOTH, make(Role::VOICE, 0, log.say("session lost"), log.say("session back"))));
    assert(log.joined() == "camera lost");
    assert(o.holder(Side::OUT) == Role::VOICE && o.holder(Side::IN) == Role::VOICE);
    assert(o.waiting(Side::OUT) == 1);
    log.clear();
    // The session ends: OUT goes back to the camera; IN stays the voice's (it listens on).
    o.release(Side::OUT, Role::VOICE, 0);
    assert(log.joined() == "camera back");
    assert(o.holder(Side::OUT) == Role::CAMERA_SOUND && o.holder(Side::IN) == Role::VOICE);
  }

  // 3. A doorbell rings while music plays and the wake word listens: it takes both sides; the wake word comes back
  //    after, the music does not. A camera's sound that tries meanwhile is refused.
  {
    Owner o;
    Log log;
    assert(o.claim(Side::OUT, make(Role::MEDIA, 0, log.say("media lost"))));
    assert(o.claim(Side::IN, make(Role::VOICE, 0, log.say("wake lost"), log.say("wake back"))));
    assert(o.claim(Side::BOTH, make(Role::DOORBELL, 7, log.say("doorbell lost"), log.say("doorbell back"))));
    assert(log.joined() == "media lost,wake lost");
    assert(!o.claim(Side::OUT, make(Role::CAMERA_SOUND, 2, log.say("camera lost"))));  // refused, nothing changed
    assert(o.holder(Side::OUT) == Role::DOORBELL && o.holder(Side::IN) == Role::DOORBELL);
    assert(!o.would_grant(Side::OUT, Role::MEDIA) && o.would_grant(Side::OUT, Role::DOORBELL));
    log.clear();
    o.release(Side::BOTH, Role::DOORBELL, 7);
    assert(log.joined() == "wake back");
    assert(!o.held(Side::OUT) && o.holder(Side::IN) == Role::VOICE);
  }

  // 4. The same role replaces its holder: a second camera's full view takes the sound from the first, which is told
  //    and forgotten (it is closed, not waiting). Releasing the first afterwards changes nothing.
  {
    Owner o;
    Log log;
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("one lost"), log.say("one back"))));
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 2, log.say("two lost"), log.say("two back"))));
    assert(log.joined() == "one lost");
    assert(o.waiting(Side::OUT) == 0);
    o.release(Side::OUT, Role::CAMERA_SOUND, 1);  // the old one, already gone
    assert(o.held(Side::OUT) && o.holder(Side::OUT) == Role::CAMERA_SOUND);
    o.release(Side::OUT, Role::CAMERA_SOUND, 2);
    assert(!o.held(Side::OUT));
  }

  // 5. The same claim again is no change: a camera's sound unmuted claims again and nothing is lost or logged.
  {
    Owner o;
    Log log;
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("lost"), log.say("back"))));
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("lost"), log.say("back"))));
    assert(log.lines.empty() && o.waiting(Side::OUT) == 0);
  }

  // 6. Two waiting claims come back in rank: the camera's sound before the music, when a doorbell releases, and a
  //    waiting claim that released meanwhile (the camera closed during the ring) is dropped.
  {
    Owner o;
    Log log;
    assert(o.claim(Side::OUT, make(Role::MEDIA, 0, log.say("media lost"), log.say("media back"))));
    assert(o.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, log.say("camera lost"), log.say("camera back"))));
    assert(o.claim(Side::OUT, make(Role::DOORBELL, 7, log.say("doorbell lost"))));
    assert(o.waiting(Side::OUT) == 2);
    log.clear();
    o.release(Side::OUT, Role::DOORBELL, 7);
    assert(log.joined() == "camera back");
    assert(o.waiting(Side::OUT) == 1);  // the music still waits behind the camera
    o.release(Side::OUT, Role::CAMERA_SOUND, 1);
    assert(log.joined() == "camera back,media back");
    assert(o.holder(Side::OUT) == Role::MEDIA);
    // Again, but the camera closes during the ring: it must not come back.
    Owner p;
    Log plog;
    assert(p.claim(Side::OUT, make(Role::CAMERA_SOUND, 1, plog.say("camera lost"), plog.say("camera back"))));
    assert(p.claim(Side::OUT, make(Role::DOORBELL, 7, plog.say("doorbell lost"))));
    p.release(Side::OUT, Role::CAMERA_SOUND, 1);  // closed while waiting
    assert(p.waiting(Side::OUT) == 0);
    p.release(Side::OUT, Role::DOORBELL, 7);
    assert(plog.joined() == "camera lost" && !p.held(Side::OUT));
  }

  // 7. A callback may act in turn: a claim whose `lost` releases its other side leaves the owner consistent.
  {
    Owner o;
    Owner *po = &o;
    assert(o.claim(Side::BOTH, make(Role::VOICE, 0, [po] { po->release(Side::IN, Role::VOICE, 0); })));
    assert(o.claim(Side::OUT, make(Role::DOORBELL, 7, {})));
    assert(o.holder(Side::OUT) == Role::DOORBELL && !o.held(Side::IN));
  }

  std::puts("test_audio_owner: ok");
  return 0;
}
