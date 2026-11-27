#pragma once
// This screen's paper, for the firmware around the paper glass (docs/PAPER.md): how many inks its panel prints with,
// and the one printer that decides when it prints (paper_print.h). The paper glass (paper_glass.h) fills both in at
// its setup; a screen without one has zero inks, and every call here does nothing there, so the shared code asks
// nothing before it calls.
//
// Free of LVGL and ESPHome, so a PC test and the editor's preview include it as it is.
#include <cstdint>

#include "paper_print.h"

namespace paper {

// The inks of this screen's panel: 0 on a glass that is lit and shows colours, 2 for black and white, 4 for four greys.
inline uint8_t &inks() {
  static uint8_t n = 0;
  return n;
}
inline bool is() { return inks() != 0; }

inline paper_print::Printer &printer() {
  static paper_print::Printer p;
  return p;
}

// A finger lies on the glass or lifted from it: nothing prints under it, and what is drawn after it is its answer.
inline void finger(bool down, uint32_t now) {
  if (is()) printer().finger(down, now);
}
// A key was pressed: a finger that came and went at once.
inline void key(uint32_t now) { finger(false, now); }
// News the screen was told to show now (an alert, a ring at the door, a page Home Assistant asked for): what is drawn
// next prints as a finger's answer does, without waiting for a stream's turn.
inline void news(uint32_t now) { finger(false, now); }
// The screen is at rest (its standby) or not: said again and again, the printer hears the change.
inline void rest(bool on, uint32_t now) {
  if (is()) printer().rest(on, now);
}
// Something that is only whole at its end begins or ends: a layout on its way, a page being built.
inline void hold(bool on, uint32_t now) {
  if (is()) printer().hold(on, now);
}
// The next print refreshes the whole panel: the look of the whole glass changed, or someone asked for a clean glass.
inline void whole_next(uint32_t now) {
  if (is()) printer().whole_next(now);
}

}  // namespace paper
