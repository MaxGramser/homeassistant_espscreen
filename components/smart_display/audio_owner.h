#pragma once
// Who may play and who may listen (docs/PLATFORM_PLAN.md, section 3.4). A screen has one loudspeaker and one
// microphone, and several things want them: a doorbell's ring and talk, a camera's sound, the voice assistant, music or
// a message from Home Assistant, and a plugin's short sounds. Before this, each started and stopped the speaker on its
// own: the camera's sound and Home Assistant's media both set the same input of the mixer without knowing of each
// other, and the wake word listened on through a doorbell. Now every one of them asks the owner first, the way an app
// asks iOS for its audio session: it claims a side (OUT, IN or BOTH) in a role, and the owner says yes or no, tells the
// holder it took the side from that it lost it, and gives it back afterwards to whoever asked to have it back.
//
// The ranking, highest first: DOORBELL (a ring, and later the talk), VOICE (the wake word and a session), CAMERA_SOUND
// (a full view with sound), MEDIA (music and messages from Home Assistant). A higher role takes a side from a lower
// one; the same role replaces its holder (a second camera's full view takes over from the first); a lower role is
// refused. A plugin's short sounds and Home Assistant's announcements never claim: they mix over whatever plays
// (features/audio-player.yaml, the mixer's announcement input), so they have no role here.
//
// Taken from and given back: a claim carries `lost`, called when a higher claim takes the side, and `regained`, called
// when that claim releases it and this one is next in rank. A claim without `regained` is forgotten once it lost (music
// does not come back after a doorbell); one with it waits (a camera's sound comes back after a voice session, since the
// camera is still open). Both callbacks run on the main loop, from inside claim() or release(), after the owner's own
// state has changed, so a callback may claim or release in turn.
//
// Pure: no ESPHome, no FreeRTOS, no LVGL. tests/test_audio_owner.cpp drives it on a PC. The screen has one Owner
// (audio_owner::the()); live_view, module_doorbell, the audio YAML and the plugin API (tessera::audio) all go through it.
#include <cstdint>
#include <cstdio>
#include <functional>
#include <vector>

namespace audio_owner {

enum class Role : uint8_t { MEDIA = 0, CAMERA_SOUND = 1, VOICE = 2, DOORBELL = 3 };  // lowest first
enum class Side : uint8_t { OUT = 1, IN = 2, BOTH = 3 };
constexpr int SIDES = 2;  // OUT, IN

inline bool has_out(Side s) { return (static_cast<uint8_t>(s) & 1) != 0; }
inline bool has_in(Side s) { return (static_cast<uint8_t>(s) & 2) != 0; }
inline const char *name(Role r) {
  switch (r) {
    case Role::MEDIA: return "media";
    case Role::CAMERA_SOUND: return "camera";
    case Role::VOICE: return "voice";
    case Role::DOORBELL: return "doorbell";
  }
  return "?";
}

using Callback = std::function<void()>;

// A claimant: who asks, with what it wants to hear back. `id` tells two claims of one role apart (two camera streams).
struct Claim {
  Role role = Role::MEDIA;
  uint32_t id = 0;
  Callback lost;      // the side was taken: stop playing or listening at once
  Callback regained;  // the side is free again and this claim is next: play or listen again; empty = do not wait
};

class Owner {
 public:
  // What the owner says as it changes hands, one line a change ("camera took OUT from media", "media gave OUT back",
  // "voice refused IN: doorbell holds it"), to whatever the screen binds: the core logs it at INFO (core.yaml, tag
  // "audio"), the host test reads it. Empty: silent.
  std::function<void(const char *)> log;

  // Asks for `side` in `role`. True: the side is this claim's now (every side of it). False: a higher role holds one
  // of its sides, nothing changed. A side taken from a lower claim calls that claim's `lost` after the change; one
  // taken from the same role (a replacement) calls its `lost` too and forgets it.
  bool claim(Side side, const Claim &c) {
    for (int s = 0; s < SIDES; ++s)
      if (wants(side, s) && holders_[s].held && above(holders_[s].claim.role, c.role)) {
        say("%s refused %s: %s holds it", name(c.role), side_name(s), name(holders_[s].claim.role));
        return false;
      }
    std::vector<Callback> losses;
    for (int s = 0; s < SIDES; ++s) {
      if (!wants(side, s)) continue;
      // The same claim again (a camera's sound that was muted and unmuted): nothing to take.
      if (holders_[s].held && same(holders_[s].claim, c)) {
        holders_[s].claim = c;
        continue;
      }
      if (holders_[s].held) {
        Slot &h = holders_[s];
        say("%s took %s from %s", name(c.role), side_name(s), name(h.claim.role));
        if (h.claim.lost) losses.push_back(h.claim.lost);
        // A lower claim that wants the side back waits for it; the same role's old holder is simply replaced.
        if (h.claim.role != c.role && h.claim.regained) waiting_[s].push_back(h.claim);
      } else {
        say("%s holds %s", name(c.role), side_name(s));
      }
      holders_[s].held = true;
      holders_[s].claim = c;
      // What this claim itself was waiting for, it has now.
      drop_waiting(s, c);
    }
    for (auto &l : losses) l();
    return true;
  }

  // Gives `side` back if this claim holds it, or stops waiting for it. The next waiting claim of the highest role takes
  // the side and hears `regained`.
  void release(Side side, Role role, uint32_t id = 0) {
    std::vector<Callback> regains;
    for (int s = 0; s < SIDES; ++s) {
      if (!wants(side, s)) continue;
      Claim probe;
      probe.role = role;
      probe.id = id;
      drop_waiting(s, probe);
      if (!holders_[s].held || !same(holders_[s].claim, probe)) continue;
      holders_[s].held = false;
      // The highest waiting claim takes it back.
      int best = -1;
      for (size_t i = 0; i < waiting_[s].size(); ++i)
        if (best < 0 || above(waiting_[s][i].role, waiting_[s][best].role)) best = static_cast<int>(i);
      if (best >= 0) {
        holders_[s].held = true;
        holders_[s].claim = waiting_[s][best];
        waiting_[s].erase(waiting_[s].begin() + best);
        say("%s gave %s back: %s has it again", name(role), side_name(s), name(holders_[s].claim.role));
        if (holders_[s].claim.regained) regains.push_back(holders_[s].claim.regained);
      } else {
        say("%s gave %s back", name(role), side_name(s));
      }
    }
    for (auto &r : regains) r();
  }

  // Who holds a side now; false and MEDIA when nobody does.
  bool held(Side side) const {
    for (int s = 0; s < SIDES; ++s)
      if (wants(side, s) && holders_[s].held) return true;
    return false;
  }
  Role holder(Side side) const {
    Role best = Role::MEDIA;
    bool any = false;
    for (int s = 0; s < SIDES; ++s)
      if (wants(side, s) && holders_[s].held && (!any || above(holders_[s].claim.role, best))) {
        best = holders_[s].claim.role;
        any = true;
      }
    return best;
  }
  // Whether a claim of `role` would be granted `side` now (nothing claimed): what a plugin asks before it speaks.
  bool would_grant(Side side, Role role) const {
    for (int s = 0; s < SIDES; ++s)
      if (wants(side, s) && holders_[s].held && above(holders_[s].claim.role, role)) return false;
    return true;
  }
  size_t waiting(Side side) const {
    size_t n = 0;
    for (int s = 0; s < SIDES; ++s)
      if (wants(side, s)) n += waiting_[s].size();
    return n;
  }

 private:
  struct Slot {
    bool held = false;
    Claim claim;
  };
  static bool wants(Side side, int s) { return s == 0 ? has_out(side) : has_in(side); }
  static const char *side_name(int s) { return s == 0 ? "the speaker" : "the microphone"; }
  void say(const char *form, const char *a, const char *b, const char *c = nullptr) {
    if (!log) return;
    char line[96];
    std::snprintf(line, sizeof line, form, a, b, c ? c : "");
    log(line);
  }
  static bool above(Role a, Role b) { return static_cast<uint8_t>(a) > static_cast<uint8_t>(b); }
  static bool same(const Claim &a, const Claim &b) { return a.role == b.role && a.id == b.id; }
  void drop_waiting(int s, const Claim &c) {
    auto &w = waiting_[s];
    for (size_t i = 0; i < w.size();)
      if (same(w[i], c)) w.erase(w.begin() + i);
      else ++i;
  }
  Slot holders_[SIDES];
  std::vector<Claim> waiting_[SIDES];
};

// The screen's one owner.
inline Owner &the() {
  static Owner owner;
  return owner;
}

}  // namespace audio_owner
