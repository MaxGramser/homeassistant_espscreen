#include "components/smart_display/hand_standby.h"
#include <cassert>
#include <cstdio>
using namespace hand_standby;

int main() {
  // No standby by hand: every sensed wake lights the screen.
  assert(sensed_wakes(5));

  // Standby by hand at 1000: walking away is motion, held, and each one starts the quiet again.
  begin(1000);
  assert(!sensed_wakes(2000));
  assert(!sensed_wakes(2000 + QUIET_MS - 1));
  assert(!sensed_wakes(2000 + 2 * QUIET_MS - 2));
  // A full quiet after the last one: someone came, the screen lights.
  assert(sensed_wakes(2000 + 3 * QUIET_MS));

  // Nobody moved at all after the standby: the first motion after the quiet wakes.
  begin(100);
  assert(sensed_wakes(100 + QUIET_MS));

  // Any wake ends the hold (a finger, the key): the next sensed wake is let through.
  begin(500);
  end();
  assert(sensed_wakes(600));

  // The millisecond counter wraps.
  begin(UINT32_MAX - 10);
  assert(!sensed_wakes(20));
  assert(sensed_wakes(20 + QUIET_MS));

  std::puts("hand_standby ok");
}
