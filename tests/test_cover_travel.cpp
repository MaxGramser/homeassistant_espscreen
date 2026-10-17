// A cover on its way shows where it goes until Home Assistant reports it there or stopped (cover_travel.h).
#include "components/smart_display/cover_travel.h"
#include <cassert>

using namespace cover_travel;

int main() {
  // The finger lets go at 60 % of a blind at 20 %: "opening" with the old position keeps the target in front, the
  // position reached ends it.
  {
    Travel t;
    assert(start(t, 1000, 60, 0, 20, "open"));
    assert(t.dir == 1 && shown_position(t) == 60 && std::string(shown_state(t)) == "opening");
    assert(reported(t, 1200, 20, "opening"));
    assert(reported(t, 4000, 41, "opening"));
    assert(!reported(t, 6000, 59, "open") && !t.active());
  }
  // A message from before the command (still "open" at 20 %) keeps it; no sign of moving at all lets it go.
  {
    Travel t;
    assert(start(t, 1000, 60, 0, 20, "open"));
    assert(reported(t, 1100, 20, "open"));
    assert(holding(t, 1000 + QUIET - 1));
    assert(!holding(t, 1000 + QUIET));
  }
  // It moved, then stood still short of the target (a stop from a remote, an obstacle): the travel ends there.
  {
    Travel t;
    assert(start(t, 1000, 0, 0, 100, "open"));
    assert(t.dir == -1 && std::string(shown_state(t)) == "closing");
    assert(reported(t, 1500, 100, "closing"));
    assert(!reported(t, 3000, 70, "open") && !t.active());
  }
  // A cover that reports positions on its way but never a state word for it still counts as moving, and has stopped
  // once its position stands still a while.
  {
    Travel t;
    assert(start(t, 1000, 80, 0, 10, "open"));
    assert(reported(t, 2000, 30, "open") && t.moved);
    assert(reported(t, 4000, 30, "open"));
    assert(holding(t, 2000 + SETTLE - 1) && !holding(t, 2000 + SETTLE));
  }
  // Open on a garage door without positions: only the way shows, and the open state ends it.
  {
    Travel t;
    assert(start(t, 1000, 100, 1, NAN, "closed"));
    assert(std::isnan(t.to) && std::isnan(shown_position(t)) && std::string(shown_state(t)) == "opening");
    assert(reported(t, 1500, NAN, "opening"));
    assert(!reported(t, 9000, NAN, "open"));
  }
  // Already there, or a cover that is unavailable: no travel.
  {
    Travel t;
    assert(!start(t, 1000, 41, 0, 40, "open"));
    assert(!start(t, 1000, 60, 0, 20, "unavailable"));
    assert(start(t, 1000, 60, 0, 20, "open"));
    assert(!reported(t, 1500, NAN, "unavailable") && !t.active());
  }
  // The slats: no state word for tilting, so they end when there, or once they stopped changing.
  {
    Travel t;
    assert(start(t, 1000, 80, 0, 0, "open", true));
    assert(reported(t, 1500, 30, "open"));
    assert(reported(t, 2000, 30, "open"));
    assert(holding(t, 1500 + SETTLE - 1) && !holding(t, 1500 + SETTLE));
    assert(start(t, 1000, 80, 0, 0, "open", true));
    assert(!reported(t, 1500, 79, "open"));
  }
  // A long travel never outlives the cap, however it reports.
  {
    Travel t;
    assert(start(t, 1000, 100, 0, 0, "closed"));
    uint32_t now = 1000;
    while (now < 1000 + CAP - 30000) { now += 30000; assert(reported(t, now, 0, "opening")); }
    assert(!holding(t, 1000 + CAP));
  }
  // The clock wraps around.
  {
    Travel t;
    assert(start(t, 0xFFFFF000u, 60, 0, 20, "open"));
    assert(holding(t, 0x00000100u));
  }
  return 0;
}
