// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_heap_watch.cpp -o /tmp/test_heap_watch && /tmp/test_heap_watch
//
// What asks the internal RAM for room (components/smart_display/heap_watch.h): the lowest since boot is logged the
// first time and again only once it fell another step below the last one logged.
#include "../components/smart_display/heap_watch.h"
#include <cassert>
#include <cstdio>

using namespace heap_watch;

int main() {
  LowWater water;
  assert(water.due(289000, STEP));             // the first reading is the start
  assert(!water.due(289000 - STEP + 1, STEP));  // less than a step lower: not yet
  assert(water.due(289000 - STEP, STEP));       // a whole step: logged
  assert(water.logged == 289000 - STEP);
  assert(!water.due(289000, STEP));             // the lowest never rises, and a higher reading says nothing
  assert(water.due(20000, STEP));               // a deep fall is one line, not one per step
  assert(!water.due(20000 - STEP + 1, STEP));

  // The H.264 encoder's first ask for its reference frame falls back to PSRAM: its caps, more than all internal RAM.
  const uint32_t internal_total = 589000;
  assert(falls_back(1382464, FIRST_TRY_CAPS, internal_total));
  assert(!falls_back(92160, FIRST_TRY_CAPS, internal_total));      // the encoder's own internal buffers: a failure
  assert(!falls_back(1382464, FIRST_TRY_CAPS | (1u << 10), internal_total));  // with PSRAM asked too: a failure
  assert(!falls_back(1382464, (1u << 11), internal_total));        // other caps: a failure
  printf("test_heap_watch: ok\n");
  return 0;
}
