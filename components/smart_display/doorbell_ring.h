#pragma once
// A ring on the glass (module doorbell, docs/DOORBELL.md): how long it stays, what a ring does to the view, and which keys
// the view has, free of LVGL, so tests/test_doorbell_ring.cpp checks it on a PC. module_doorbell.cpp asks these.
//
// The app sends the ring's timeout (the event's `timeout`, the op's `t`), whether its view opens quiet (`m`) and whether
// it rings without the chime (`nc`). What the app keeps in the same numbers is screen_manager/app/doorbell.py (TIMEOUT,
// TIMEOUT_MIN, TIMEOUT_MAX); tests/test_doorbell.py keeps the two alike.
#include <cstdint>

namespace doorbell_ring {

// How long a ring nobody touches stays on the glass, in seconds: the op's `t`, a minute when it says none, never shorter
// than TIMEOUT_MIN_S nor longer than TIMEOUT_MAX_S.
constexpr uint32_t TIMEOUT_S = 60, TIMEOUT_MIN_S = 10, TIMEOUT_MAX_S = 600;
inline uint32_t untouched_ms(uint32_t seconds) {
  const uint32_t s = seconds ? seconds : TIMEOUT_S;
  return (s < TIMEOUT_MIN_S ? TIMEOUT_MIN_S : s > TIMEOUT_MAX_S ? TIMEOUT_MAX_S : s) * 1000;
}

// What a ring does. A ring of the camera and door the view shows rings again in it: the chime again, and the sound stays
// as the person at the screen left it. Any other ring opens a view of its own, whose sound is on unless the ring is
// quiet. Either way it chimes unless its automation said `chime: false`.
struct Ring {
  bool again;  // rings again in the view that shows
  bool chime;  // plays the chime
  bool sets_sound;  // the view's sound is set (a new view); else it stays as it is
  bool muted;  // that sound: off for a quiet ring
};
inline Ring ring(bool showing_same, bool quiet, bool chimes) {
  if (showing_same) return {true, chimes, false, false};
  return {false, chimes, true, quiet};
}

// The keys of the view, from the top or the left: Door when the ring has one, Talk where the screen hears (a microphone,
// the voice's way to Home Assistant, and a place for it from the app, the op's `tk`), Sound where it plays. A key the
// screen cannot use is not there at all.
struct Keys {
  bool door, talk, sound;
  int count() const { return door + talk + sound; }
};
inline Keys keys(bool has_door, bool microphone, bool uplink, bool talk_link, bool speaker) {
  return {has_door, microphone && uplink && talk_link, speaker};
}

}  // namespace doorbell_ring
