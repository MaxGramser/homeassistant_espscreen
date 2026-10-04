#include "../components/smart_display/panel_voice_timing.h"
#include <cassert>
#include <initializer_list>

using esphome::smart_display::voice_timing::elapsed;

int main() {
  // Receive/listen callbacks can run after loop() took its snapshot. Previously
  // this falsely expired the heartbeat, microphone startup and silence timers.
  const uint32_t loop_now = 12000;
  for (uint32_t newer : {12000u, 12001u, 12020u}) {
    assert(elapsed(loop_now, newer) == 0);
    assert(elapsed(loop_now, newer) < 3000);
  }
  assert(elapsed(15000, 12000) == 3000);
  assert(elapsed(17001, 12000) > 5000);  // a real heartbeat timeout still fires
  assert(elapsed(612000, 12000) >= 600000);  // maximum session duration
  assert(elapsed(20, UINT32_MAX - 29) == 50);  // millis() rollover
  assert(elapsed(UINT32_MAX - 1, 1) == 0);  // newer callback across rollover
}
