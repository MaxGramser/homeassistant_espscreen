#pragma once
// A standby someone asked for by hand (firmware 0.64.0+): the home key held, the board's key, Home Assistant's Sleep.
// Unlike the standby time running out, the person is still there: walking away from the glass is motion, and a wake
// on motion (a plugin's tessera::wake, a board that wakes when moved, Home Assistant's Wake from a motion automation)
// would light the screen again at once. So after a standby by hand a sensed wake waits for the room to go quiet: no
// sensed wake for QUIET_MS, and the next one lights the screen, someone came. Each sensed wake it holds starts the
// quiet again. A wake that is no sensing (a finger, the board's key, an alert, a doorbell, a call, a popup) always
// lights it, and any wake ends the hold. The standby time running out holds nothing: nobody was there.
// Free of LVGL and ESPHome; packages/core.yaml (wake_from, standby_by_hand) uses it. tests/test_hand_standby.cpp.
#include <cstdint>

namespace hand_standby {

constexpr uint32_t QUIET_MS = 60000;

inline bool holding = false;
inline uint32_t last_sensed = 0;

// The screen went to standby by hand: sensed wakes wait for the quiet from now.
inline void begin(uint32_t now) {
  holding = true;
  last_sensed = now;
}

// The screen woke, by whatever way.
inline void end() { holding = false; }

// A sensed wake: true when it may light the screen. One it holds starts the quiet again.
inline bool sensed_wakes(uint32_t now) {
  if (!holding || now - last_sensed >= QUIET_MS) return true;
  last_sensed = now;
  return false;
}

}  // namespace hand_standby
