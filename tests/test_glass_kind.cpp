// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_glass_kind.cpp -o /tmp/test_glass_kind && /tmp/test_glass_kind
// The kind of glass (components/smart_display/glass_kind.h): one fact, the panel's inks, and what follows from it under
// the name of each consequence. And the moments the screen tells its glass, which only a glass of ink hears.
#include "../components/smart_display/glass_kind.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

static int prints = 0, wholes = 0;

int main() {
  // A build that reads the paper glass's paper.h can stand on either glass (the tests, the editor's preview, the host
  // render, a paper board); a build without it answers in constants (static_asserts in the firmware's own headers
  // could not be written against these otherwise).
#ifndef GLASS_MAY_BE_INK
#error "the tests read components/paper_glass/paper.h: this build may be ink"
#endif

  // ---- a glass that is lit: no inks, it moves, it goes dark, it has a light
  paper::inks() = 0;
  assert(glass_kind::inks() == 0);
  assert(!glass_kind::ink() && !glass_kind::still() && !glass_kind::keeps() && glass_kind::lit());

  // ---- a glass of ink, of two inks and of four: each consequence under its own name
  for (uint8_t inks : {uint8_t(2), uint8_t(4)}) {
    paper::inks() = inks;
    assert(glass_kind::inks() == inks);
    assert(glass_kind::ink());     // a role is a tone, a state a shape
    assert(glass_kind::still());   // nothing moves by itself
    assert(glass_kind::keeps());   // its standby is rest
    assert(!glass_kind::lit());    // no brightness, no night level
  }

  // ---- the moments: on a glass that is lit nobody hears them
  auto &printer = paper::printer();
  printer.glass.print = [](bool whole) { ++prints; if (whole) ++wholes; };
  paper::inks() = 0;
  glass_moment::finger(true, 0);
  glass_moment::finger(false, 10);
  glass_moment::key(20);
  glass_moment::news(30);
  glass_moment::rest(true, 40);
  glass_moment::hold(true, 50);
  glass_moment::whole(70);
  printer.tick(60000);
  assert(prints == 0 && !printer.waiting());  // nothing was held, asked for or printed

  // ---- on a glass of ink the printer does: what is drawn prints, the first time whole
  paper::inks() = 2;
  printer.drawn(1000, 100000);
  printer.tick(160000);
  assert(prints == 1 && wholes == 1);
  printer.printed(161000);
  // A finger on the glass holds back what is drawn under it; lifting it lets its answer print.
  glass_moment::finger(true, 200000);
  printer.drawn(100, 200010);
  printer.tick(200200);
  assert(prints == 1 && printer.waiting());
  glass_moment::finger(false, 200300);
  printer.tick(260000);
  assert(prints == 2 && wholes == 1);
  printer.printed(261000);
  // A change of the whole look asks for one whole print.
  glass_moment::whole(300000);
  printer.drawn(1000, 300000);
  printer.tick(360000);
  assert(prints == 3 && wholes == 2);

  paper::inks() = 0;
  std::puts("PASS: one fact (the inks), four consequences under their own names, and moments only a glass of ink hears");
  return 0;
}
