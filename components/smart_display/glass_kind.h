#pragma once
// The kind of glass this screen has, and what follows from it: the one fact that everything hangs on which differs
// between a glass that is lit and a glass of ink (docs/GLASS_KINDS.md). Nothing else in the firmware asks "is this
// paper"; each part asks the consequence it depends on, under that consequence's own name, here.
//
//   the board's file     a display of the platform paper_glass with its inks (features/paper.yaml), or none
//   paper::inks()        this screen's inks, said by the paper glass before anything is drawn
//   glass_kind (here)    ink, still, keeps, lit: what follows, each for the part that depends on it
//   who asks             theme.h (ink: the stylesheet of ink), screen_motion.h (still), the binder for
//                        screen_standby.h (keeps), settings_screen.h and the binder (lit), hw.cpp (inks, for the app)
//
// A build without a paper glass, every lit board, has no paper.h in it. There every answer is a constant, so the
// compiler drops what is only for ink: the ink stylesheet (theme_ink.h), the still glass's pass, every branch behind
// one of these answers. A lit board pays nothing in flash for a kind of glass it does not have. The tests on a PC,
// the editor's preview and the host render read paper.h from the repository and can stand on either glass.
//
// Free of LVGL and ESPHome. tests/test_glass_kind.cpp walks it.
#include <cstdint>

// GLASS_NEVER_INK builds as a lit board does where paper.h is in reach all the same: tests/test_glass_lit.cpp, which
// holds that such a build has none of the ink in it.
#if __has_include("../paper_glass/paper.h") && !defined(GLASS_NEVER_INK)
#include "../paper_glass/paper.h"
#define GLASS_MAY_BE_INK 1
#define GLASS_KIND_ANSWER inline
#else
#define GLASS_KIND_ANSWER constexpr
#endif

namespace glass_kind {

// The inks the panel prints with: 0 on a glass that is lit and shows colours, 2 for black and white, 4 for four greys.
#ifdef GLASS_MAY_BE_INK
inline uint8_t inks() { return paper::inks(); }
#else
constexpr uint8_t inks() { return 0; }
#endif

// It prints with inks instead of showing colours: a role is a tone and a state is a shape (theme.h, theme_ink.h).
GLASS_KIND_ANSWER bool ink() { return inks() != 0; }
// A change on it is a print that takes a part of a second, so nothing on it moves or runs by itself
// (screen_motion.h, still_glass_lvgl.h).
GLASS_KIND_ANSWER bool still() { return inks() != 0; }
// It keeps its picture without power or light, so its standby is rest and not dark (screen_standby.h).
GLASS_KIND_ANSWER bool keeps() { return inks() != 0; }
// It has a light of its own: a brightness, a night level, a fade (settings_screen.h).
GLASS_KIND_ANSWER bool lit() { return inks() == 0; }

}  // namespace glass_kind

// ---- What the screen tells its glass ----
// Moments the shared code says out loud, without knowing who listens: a finger, a key, news, rest, a layout on its
// way, a change of the whole look. On a glass of ink the printer hears them and times its prints by them
// (components/paper_glass/paper_print.h); on a glass that is lit nobody does, and each call is empty.
namespace glass_moment {

#ifdef GLASS_MAY_BE_INK
// A finger lies on the glass or lifted from it: nothing prints under it, and what is drawn after it is its answer.
inline void finger(bool down, uint32_t now) { paper::finger(down, now); }
// A key of the board was pressed: a finger that came and went at once.
inline void key(uint32_t now) { paper::key(now); }
// News the screen was told to show now (an alert, a ring at the door, a call, a page Home Assistant asked for).
inline void news(uint32_t now) { paper::news(now); }
// The screen is at rest (its standby) or not: said again and again, the listener hears the change.
inline void rest(bool on, uint32_t now) { paper::rest(on, now); }
// Something that is only whole at its end begins or ends: a layout on its way, a page being built.
inline void hold(bool on, uint32_t now) { paper::hold(on, now); }
// The whole glass changes its look at once (a new layout, the other look, a screensaver): one clean change.
inline void whole(uint32_t now) { paper::whole_next(now); }
#else
inline void finger(bool, uint32_t) {}
inline void key(uint32_t) {}
inline void news(uint32_t) {}
inline void rest(bool, uint32_t) {}
inline void hold(bool, uint32_t) {}
inline void whole(uint32_t) {}
#endif

}  // namespace glass_moment
