#pragma once
// A sound louder than the screen's own volume, and the volume put back after it (docs/SOUNDS.md, "Louder than the
// screen"). A call's ring stands at the top of the speaker, and a plugin's alarm may ask for a level of its own (plugin
// API 0.29, tessera::audio::raise_volume). Each of them is a lift: the speaker plays at the loudest of the screen's own
// volume and every lift that is up, and when the last lift comes down the speaker goes back to the screen's volume.
// One place keeps what that volume was, so two lifts that overlap (an alarm rings and a call comes in) never put back
// each other's level and leave the speaker loud.
//
// What it knows: the speaker's volume as its DAC takes it (0 to 1, ESPHome's speaker volume), read and set through the
// two functions the audio YAML binds (features/audio-player.yaml). What it does not: who plays what, and when. A lift
// never lowers the speaker: a person who turned the screen up hears it at least that loud.
// A person who changes the volume while a lift is up (Home Assistant's slider, the settings page) keeps it: the lift
// notices the speaker no longer stands where it left it, takes that as the screen's volume, and when it comes down leaves
// it there.
// Nothing here is stored: the screen's own volume is the media player's, which ESPHome keeps in flash and sets at boot.
// A restart or an update in the middle of a ring therefore comes back at the screen's own volume, never at a lift's.
//
// Pure: no ESPHome. tests/test_volume_lift.cpp drives it on a PC.
#include <cmath>
#include <cstdint>
#include <functional>

namespace volume_lift {

class Lifts {
 public:
  static constexpr int MOST = 4;  // the call, and three plugins at once
  void bind(std::function<float()> get, std::function<void(float)> set) {
    get_ = std::move(get);
    set_ = std::move(set);
  }
  bool bound() const { return get_ && set_; }
  // Lift `who` (any number that is its own: the call's, a plugin's address) to at least `level` (0 to 1 of the DAC).
  // Again with the same `who` changes its level. False without a speaker, or with MOST lifts up.
  bool lift(uintptr_t who, float level) {
    if (!bound() || !(level >= 0.0f)) return false;
    level = std::fmin(level, 1.0f);
    if (count_ == 0) {
      base_ = get_();
    } else {
      notice();
    }
    int at = find(who);
    if (at < 0) {
      if (count_ == MOST) return false;
      at = count_++;
      who_[at] = who;
    }
    level_[at] = level;
    apply();
    return true;
  }
  // `who` comes down; the last one down puts back the screen's volume. Nothing when `who` was not up.
  void drop(uintptr_t who) {
    const int at = find(who);
    if (at < 0) return;
    notice();
    who_[at] = who_[count_ - 1];
    level_[at] = level_[count_ - 1];
    --count_;
    apply();
  }
  // Every lift comes down (the firmware updates).
  void drop_all() {
    if (count_ == 0) return;
    notice();
    count_ = 0;
    apply();
  }
  bool up(uintptr_t who) const { return find(who) >= 0; }
  // The speaker's volume now (0 to 1 of the DAC), -1 without a speaker: for a log line beside a lift.
  float now() const { return bound() ? get_() : -1.0f; }
  bool any() const { return count_ > 0; }

 private:
  int find(uintptr_t who) const {
    for (int i = 0; i < count_; ++i)
      if (who_[i] == who) return i;
    return -1;
  }
  // The speaker no longer stands where a lift left it: someone changed the volume, and that is the screen's now.
  void notice() {
    const float now = get_();
    if (std::fabs(now - set_to_) > 0.001f) base_ = now;
  }
  void apply() {
    float target = base_;
    for (int i = 0; i < count_; ++i) target = std::fmax(target, level_[i]);
    if (std::fabs(get_() - target) > 0.0001f) set_(target);
    set_to_ = target;
  }
  std::function<float()> get_;
  std::function<void(float)> set_;
  uintptr_t who_[MOST]{};
  float level_[MOST]{};
  int count_ = 0;
  float base_ = 0.0f, set_to_ = -1.0f;
};

// The screen's one set of lifts, bound by features/audio-player.yaml on a board with a speaker; unbound elsewhere, where
// every lift says false.
inline Lifts &the() {
  static Lifts lifts;
  return lifts;
}
// What the media player's 0 to 1 is on the DAC (its volume_min and volume_max), for a plugin that asks in the screen's
// own volume as Home Assistant shows it. Set with the binding.
inline float &low() { static float v = 0.0f; return v; }
inline float &high() { static float v = 1.0f; return v; }
inline float on_dac(float volume) { return low() + std::fmin(std::fmax(volume, 0.0f), 1.0f) * (high() - low()); }

}  // namespace volume_lift
