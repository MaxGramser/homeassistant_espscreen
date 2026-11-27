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

// A finger landed, moved or lifted, or a key was pressed: what is drawn next is its answer.
inline void finger(uint32_t now) {
  if (is()) printer().finger(now);
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
