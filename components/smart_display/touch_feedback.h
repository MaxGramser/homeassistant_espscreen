#pragma once
// Feedback a finger can hear or feel, at the moment it happens (docs/PLUGINS.md, "Touch feedback"): a finger landing on
// something that takes it, and the steps of a value under the finger, as a detent clicks. What listens is a plugin's
// on_press and on_step (plugin_host.cpp: Tap sound clicks, a buzzer could buzz); the core only says when.
//
// Three ways in, one each for the three kinds of control, so a control of the core or of a plugin needs at most one line:
// - LVGL's own widgets need nothing: touch_feedback_lvgl.h hears every press of the input device, and the steps of every
//   lv_slider and lv_arc a finger drags, wherever it is (a tile, a card, an overlay, the settings, a plugin's card).
// - A control that is dragged but is no LVGL slider (a player's seek bar) calls moved() from its own handler with its
//   value and range, on the press and on every move.
// - A control that steps by itself while a key is held (the -/+ of a thermostat) calls step() each time it steps.
//
// Free of LVGL and ESPHome, so tests/test_touch_feedback.cpp walks it on this computer.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <vector>

namespace touch_feedback {

// One step of a value: `direction` +1 towards the larger end of its range, -1 towards the smaller, 0 for a step whose
// way is not known; `edge` when it reached either end of its range, for a firmer click there.
struct Step {
  int8_t direction;
  bool edge;
};

// How a range is cut into steps: every whole unit of a range of STEPS or fewer (a setting of a few positions), else
// every 1/STEPS of it, 5 %. At most MOST_AT_ONCE steps are said for one move, however many it passed: a detent turned
// fast clicks as a run, not as a burst that trails behind the finger.
constexpr int STEPS = 20;
constexpr int MOST_AT_ONCE = 2;

// The step a value is on. A range that reaches below zero only to draw a round end at 0 (runtime_tiles' slider_handle)
// counts from 0, and a reversed one (a cover's, whose fill hangs from the top) the same way round.
inline int step_of(int value, int low, int high) {
  if (low > high) std::swap(low, high);
  if (low < 0 && high > 0) low = 0;
  const int span = high - low;
  if (span <= 0) return 0;
  value = std::clamp(value, low, high);
  if (span <= STEPS) return value - low;
  return static_cast<int>(static_cast<long>(value - low) * STEPS / span);
}
inline int steps_in(int low, int high) { return step_of(std::max(low, high), low, high); }

// Who listens: plugin_host.cpp adds the plugins' moments when the first plugin starts. Without a listener nothing below
// keeps or runs anything.
inline std::vector<std::function<void()>> &pressed() {
  static std::vector<std::function<void()>> list;
  return list;
}
inline std::vector<std::function<void(const Step &)>> &stepped() {
  static std::vector<std::function<void(const Step &)>> list;
  return list;
}
// When nothing is said: the push that wakes a dimmed screen, a calibration (packages/core.yaml sets it at boot).
inline bool (*quiet)() = nullptr;
inline bool silent() { return quiet != nullptr && quiet(); }

namespace detail {
struct Drag {
  const void *control = nullptr;
  int step = 0;
};
inline Drag &drag() {
  static Drag d;
  return d;
}
inline void say(const Step &step) {
  for (auto &f : stepped()) f(step);
}
}  // namespace detail

// A finger arrived on the glass: whatever was dragged before is let go, so the next control starts afresh.
inline void land() { detail::drag().control = nullptr; }

// The finger landed on something that takes it (touch_feedback_lvgl.h decides that for LVGL's widgets).
inline void press() {
  if (pressed().empty() || silent()) return;
  for (auto &f : pressed()) f();
}

// A dragged control's value is `value` in [low, high] now; `control` names it (its object). Its first report after the
// finger landed only says where it starts, so a slider that jumps to the finger is no run of steps; after that every
// step passed is said, MOST_AT_ONCE at most, the last one an edge when it reached an end.
inline void moved(const void *control, int value, int low, int high) {
  if (stepped().empty() || silent()) return;
  auto &d = detail::drag();
  const int now = step_of(value, low, high);
  if (d.control != control) {
    d.control = control;
    d.step = now;
    return;
  }
  const int passed = std::abs(now - d.step);
  if (passed == 0) return;
  const int8_t direction = now > d.step ? 1 : -1;
  d.step = now;
  const int said = std::min(MOST_AT_ONCE, passed), last = steps_in(low, high);
  for (int i = 1; i <= said; ++i) detail::say({direction, i == said && (now == 0 || now == last)});
}

// A control that stepped by itself (a key held down): one step, its way if it is known.
inline void step(int direction = 0) {
  if (stepped().empty() || silent()) return;
  detail::say({static_cast<int8_t>(direction > 0 ? 1 : direction < 0 ? -1 : 0), false});
}

}  // namespace touch_feedback
