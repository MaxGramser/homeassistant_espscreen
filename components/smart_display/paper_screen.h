#pragma once
// What the shared code asks of a paper glass, whether this screen has one or not (docs/PAPER.md). A screen whose panel
// is e-paper builds the paper glass (components/paper_glass), and paper.h there is this screen's paper: its inks and
// the calls the printer hears. Every other screen has no such component in its build, and the same calls are the
// empty ones below, so nothing in the binder, the standby or packages/core.yaml asks which glass it is on before it
// says that a finger lifted or that a layout is on its way.
//
// The tests on a PC, the editor's preview and the host render read the real paper.h from the repository, with zero
// inks until one of them says otherwise.
#include <cstdint>

#if __has_include("../paper_glass/paper.h")
#include "../paper_glass/paper.h"
#else
namespace paper {
inline uint8_t &inks() {
  static uint8_t none = 0;
  return none;
}
inline bool is() { return false; }
inline void finger(bool, uint32_t) {}
inline void key(uint32_t) {}
inline void hold(bool, uint32_t) {}
inline void whole_next(uint32_t) {}
}  // namespace paper
#endif
