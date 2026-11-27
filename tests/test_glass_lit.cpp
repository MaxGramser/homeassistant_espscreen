// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_glass_lit.cpp -o /tmp/test_glass_lit && /tmp/test_glass_lit
// A build that cannot stand on a glass of ink, which is every lit board (glass_kind.h): the kind of glass is a
// constant, the theme answers at compile time that it is not ink, and the ink stylesheet is not in the build at all.
// So a lit board pays nothing in flash for a kind of glass it does not have; every branch behind one of these answers
// is dropped by the compiler.
//
// GLASS_NEVER_INK builds this test as such a board builds, though paper.h is in reach here.
#define GLASS_NEVER_INK
#define THEME_TEST
#include "../components/smart_display/theme.h"
// ESPHome includes every header of a component by itself too (esphome.h): read alone, the theme's part files are
// empty, so the ink stylesheet does not come in by that door either (a lit board's host build failed on it).
#include "../components/smart_display/theme_ink.h"
#include "../components/smart_display/theme_lit.h"
#include "../components/smart_display/theme_parts.h"
#include <cassert>
#include <cstdio>

#ifdef GLASS_MAY_BE_INK
#error "GLASS_NEVER_INK builds as a board without a paper glass"
#endif
#ifdef THEME_INK_STYLESHEET
#error "a build that is never ink carries no ink stylesheet (theme_parts.h includes theme_ink.h only where it may be ink)"
#endif

// Constants, each of them: a compiler folds every `if` on one away.
static_assert(glass_kind::inks() == 0);
static_assert(!glass_kind::ink() && !glass_kind::still() && !glass_kind::keeps() && glass_kind::lit());
static_assert(!theme::inked());

int main() {
  using namespace theme;
  // The parts are the lit stylesheet's, with no way to the other.
  TestLook::set(false, false);
  assert(hex(PAGE) == ROLES[PAGE].light && state(ha::AMBER) == ha::AMBER && mark(ha::RED) == ha::RED);
  assert(shades() && hairline() == 1 && shape_rim() == 0 && gone(77) == 77 && whole(128) == 128);
  assert(state_disc(ha::AMBER, true, true).rim == 0 && pager_dot(false, SUBTLE, 102).opa == 102);
  // The moments are empty calls.
  glass_moment::finger(true, 0);
  glass_moment::key(0);
  glass_moment::news(0);
  glass_moment::rest(true, 0);
  glass_moment::hold(true, 0);
  glass_moment::whole(0);
  std::puts("PASS: a build that is never ink answers in constants and carries no ink stylesheet");
  return 0;
}
