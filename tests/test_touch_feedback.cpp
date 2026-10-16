// touch_feedback.h (docs/PLUGINS.md, "Touch feedback"): how a range is cut into steps, and what a press, a drag and a
// held key say to the plugins that listen.
#include "../components/smart_display/touch_feedback.h"
#include <cassert>
#include <vector>
using touch_feedback::step_of;
using touch_feedback::Step;

int main() {
  // Every 5 % of a long range, every position of a short one.
  assert(step_of(0, 0, 100) == 0);
  assert(step_of(4, 0, 100) == 0);
  assert(step_of(5, 0, 100) == 1);
  assert(step_of(100, 0, 100) == 20);
  assert(step_of(127, 0, 255) == 9);
  assert(step_of(3, 0, 6) == 3);
  assert(step_of(190, 160, 300) == 4);
  assert(step_of(500, 160, 300) == 20);
  assert(step_of(7, 7, 7) == 0);
  // A tile's slider reaches below 0 only to draw its round end: it counts from 0, per mille like every slider of the core.
  assert(step_of(-8, -8, 1000) == 0);
  assert(step_of(50, -8, 1000) == 1);
  assert(step_of(1000, -8, 1000) == 20);
  // A cover's runs the other way round (1000 at the top, a stub below 0): counted all the same.
  assert(step_of(500, 1000, -60) == 10);
  assert(step_of(1000, 1000, -60) == 20);
  assert(touch_feedback::steps_in(-8, 1000) == 20);
  assert(touch_feedback::steps_in(1000, -60) == 20);
  assert(touch_feedback::steps_in(0, 6) == 6);

  // Without a listener nothing is said or kept.
  touch_feedback::land();
  touch_feedback::press();
  touch_feedback::moved(nullptr, 10, 0, 100);

  int presses = 0;
  std::vector<Step> steps;
  touch_feedback::pressed().push_back([&presses]() { ++presses; });
  touch_feedback::stepped().push_back([&steps](const Step &s) { steps.push_back(s); });
  int slider = 0, other = 0;

  // A press, then a drag: the first value only says where it starts (a slider that jumped to the finger is no run).
  touch_feedback::land();
  touch_feedback::press();
  assert(presses == 1);
  touch_feedback::moved(&slider, 450, -8, 1000);
  assert(steps.empty());
  touch_feedback::moved(&slider, 520, -8, 1000);
  assert(steps.size() == 1 && steps[0].direction == 1 && !steps[0].edge);
  touch_feedback::moved(&slider, 540, -8, 1000);   // within the same step
  assert(steps.size() == 1);
  touch_feedback::moved(&slider, 380, -8, 1000);   // back three steps: two said
  assert(steps.size() == 3 && steps[1].direction == -1 && steps[2].direction == -1);
  touch_feedback::moved(&slider, 1000, -8, 1000);  // up to the end: two said, the last one an edge
  assert(steps.size() == 5 && !steps[3].edge && steps[4].edge && steps[4].direction == 1);
  touch_feedback::moved(&slider, -8, -8, 1000);    // down to 0: the edge again
  assert(steps.size() == 7 && steps[6].edge && steps[6].direction == -1);

  // Another control, or the same after a new landing, starts afresh.
  touch_feedback::moved(&other, 300, 0, 1000);
  assert(steps.size() == 7);
  touch_feedback::land();
  touch_feedback::moved(&slider, 600, -8, 1000);
  assert(steps.size() == 7);

  // A held key steps by itself: one step each time, its way as given.
  touch_feedback::step(1);
  touch_feedback::step(-3);
  touch_feedback::step();
  assert(steps.size() == 10 && steps[7].direction == 1 && steps[8].direction == -1 && steps[9].direction == 0);

  // Quiet (a dimmed screen waking, a calibration): nothing is said.
  touch_feedback::quiet = []() { return true; };
  touch_feedback::press();
  touch_feedback::step(1);
  touch_feedback::moved(&slider, 1000, -8, 1000);
  assert(presses == 1 && steps.size() == 10);
  touch_feedback::quiet = nullptr;
  return 0;
}
