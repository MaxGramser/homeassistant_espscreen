#pragma once
// A cover on its way (docs/OPTIMISTIC.md, "A cover on its way"). A blind, a curtain or a garage door takes seconds to
// get where the finger sent it, and Home Assistant reports it on the way: "opening" with the position from before,
// sometimes a position now and then, the end state when it stops. Shown as it comes, the slider the finger let go at
// 60 % jumps back to 20 % and only reaches 60 % when the cover does.
//
// A travel holds what the finger asked for in front of those reports: the fill stays at the target, the tile says
// "Opening" or "Closing" from the moment of the tap, and the cover's slider shows its fill faint and no handle, so
// nothing looks as if it waits for a finger. It still takes one: a press brings the handle back, and a new release
// sends the cover elsewhere on its way, as the stop, open and close keys do. It ends when Home Assistant reports the cover there,
// reports it standing still after it moved (stopped short: a stop key, an obstacle, a remote), says it is
// unavailable, refuses the action, or gives no sign of moving at all (QUIET). What Home Assistant reported shows again
// then. A cover that reports only positions on its way, never "opening" or "closing", and the slats' tilt, which has
// no state word, end once they are there or have stopped changing for SETTLE.
//
// Pure, so tests/test_cover_travel.cpp runs it on the host; Tile (runtime_model.h) holds one and writes what it shows.
#include <cmath>
#include <cstdint>
#include <string>

namespace cover_travel {

// No sign of moving this long after the command: the cover did not take it, and what Home Assistant says shows again.
constexpr uint32_t QUIET = 10000;
// On its way, but no report for this long: Home Assistant would have said something by now.
constexpr uint32_t SILENT = 60000;
// The longest travel shown (a long curtain, a garage door).
constexpr uint32_t CAP = 180000;
// A cover without words for moving (and the slats) stopped changing this long ago: it is where it goes.
constexpr uint32_t SETTLE = 5000;
// A position this close to the target is there (a motor stops a point or two short).
constexpr float NEAR = 2.0f;

enum class State : uint8_t { OTHER, OPEN, CLOSED, OPENING, CLOSING };

inline State state_of(const std::string &state) {
  if (state == "open") return State::OPEN;
  if (state == "closed") return State::CLOSED;
  if (state == "opening") return State::OPENING;
  if (state == "closing") return State::CLOSING;
  return State::OTHER;
}
inline const char *state_word(State state) {
  switch (state) {
    case State::OPEN: return "open";
    case State::CLOSED: return "closed";
    case State::OPENING: return "opening";
    case State::CLOSING: return "closing";
    default: return "";
  }
}

struct Travel {
  float to = NAN;     // the position asked for, 0-100; NAN for open or close of a cover without positions
  float real = NAN;   // the position Home Assistant last reported
  State real_state = State::OTHER;
  int8_t dir = 0;     // +1 opening, -1 closing, 0 no travel
  bool moved = false; // Home Assistant said it is on its way
  bool worded = false; // ...in so many words ("opening", "closing"), so a still state means it stopped
  bool tilt = false;  // the slats' tilt travels, not the cover
  uint32_t at = 0, sign_at = 0;
  bool active() const { return dir != 0; }
};

// A command went out: `to` the position (NAN for open or close without one), `dir` the way for open (+1) and close
// (-1), 0 to take it from the positions. Returns whether there is a travel to show (a cover already there has none).
inline bool start(Travel &t, uint32_t now, float to, int dir, float real, const std::string &state, bool tilt = false) {
  const State reported = state_of(state);
  t = Travel();
  if (reported == State::OTHER) return false;  // unavailable or unknown: nothing to hold in front of
  if (!dir) {
    if (!std::isfinite(to) || !std::isfinite(real) || std::fabs(to - real) <= NEAR) return false;
    dir = to > real ? 1 : -1;
  } else if (!std::isfinite(real)) {
    to = NAN;  // open or close of a cover that reports no position: only the way shows
  }
  t.to = to;
  t.tilt = tilt;
  t.real = real;
  t.real_state = reported;
  t.dir = static_cast<int8_t>(dir > 0 ? 1 : -1);
  t.at = now ? now : 1;
  return true;
}

inline void end(Travel &t) { t.dir = 0; }

// Whether the travel still shows, by the clock.
inline bool holding(const Travel &t, uint32_t now) {
  if (!t.active() || now - t.at >= CAP) return false;
  if (!t.moved) return now - t.at < QUIET;
  return now - t.sign_at < (t.worded ? SILENT : SETTLE);
}

// Home Assistant reported the cover: `position` (the tilt for a tilt travel; NAN without one) and `state`. Returns
// whether the travel still shows.
inline bool reported(Travel &t, uint32_t now, float position, const std::string &state) {
  if (!t.active()) return false;
  const State s = state_of(state);
  const bool changed = std::isfinite(position) && std::isfinite(t.real) && std::fabs(position - t.real) > 0.5f;
  t.real = position;
  t.real_state = s;
  if (s == State::OTHER) { end(t); return false; }
  const bool there = std::isfinite(t.to) ? std::isfinite(position) && std::fabs(position - t.to) <= NEAR
                                         : s == (t.dir > 0 ? State::OPEN : State::CLOSED);
  if (there) { end(t); return false; }
  const bool word = s == State::OPENING || s == State::CLOSING;
  if (word && !t.tilt) t.worded = true;
  // A still state from a cover that says when it moves: it stopped short of the target (or, before it moved, the
  // message is from before the command).
  if (!word && t.worded) { end(t); return false; }
  if (word || changed) {
    t.moved = true;
    t.sign_at = now ? now : 1;
  }
  return holding(t, now);
}

// What the tile shows while the travel holds: the target, and the way it goes.
inline float shown_position(const Travel &t) { return std::isfinite(t.to) ? t.to : t.real; }
inline const char *shown_state(const Travel &t) { return t.dir > 0 ? "opening" : "closing"; }

}  // namespace cover_travel
