// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_section_layout.cpp -o /tmp/test_section_layout && /tmp/test_section_layout
// The room a section's title and padding take from its own tiles, and which blocks a screen takes
// (components/smart_display/section_layout.h, docs/PAGES.md "Sections"). The editor's insideMargins
// (web/tests/sections.spec.ts) answers the same cases.
#include "../components/smart_display/section_layout.h"
#include <cassert>

using namespace section_layout;

static Section block(int column, int row, int columns, int rows, const char *title = "Lights") {
  Section s;
  s.column = uint8_t(column); s.row = uint8_t(row); s.columns = uint8_t(columns); s.rows = uint8_t(rows); s.title = title;
  return s;
}

int main() {
  // The 10.1-inch at 6 x 5: header 38 + 11 = 49, padding 11, three rows. Each tile gives up (49 + 11) / 3 = 20 pixels.
  Inset a = inside(49, 11, 3, 0, 0), b = inside(49, 11, 3, 1, 1), c = inside(49, 11, 3, 2, 2);
  assert(a.top == 49 && a.bottom == -29);
  assert(b.top == 29 && b.bottom == -9);
  assert(c.top == 9 && c.bottom == 11);
  // Every tile the same height: what it gives up at its top and its foot is the same for each row.
  assert(a.top + a.bottom == 20 && b.top + b.bottom == 20 && c.top + c.bottom == 20);
  // The first tile's top is the header, the last one's foot the padding: the panel's edges stay on the rows beside it.
  Inset whole = inside(49, 11, 3, 0, 2);
  assert(whole.top == 49 && whole.bottom == 11);
  // A share that is no whole number rounds half away from zero, as lroundf does.
  assert(round_div(5, 2) == 3 && round_div(-5, 2) == -3 && round_div(4, 3) == 1 && round_div(-4, 3) == -1);
  Inset one = inside(49, 11, 1, 0, 0);
  assert(one.top == 49 && one.bottom == 11);

  // What a screen takes: inside the grid, none over another, a title, at most sixteen.
  assert(valid({block(1, 0, 2, 2)}, 4, 3));
  assert(!valid({block(3, 0, 2, 2)}, 4, 3));
  assert(!valid({block(0, 0, 2, 2), block(1, 1, 2, 1)}, 4, 3));
  assert(!valid({block(0, 0, 1, 1, "")}, 4, 3));
  std::vector<Section> many(MAX + 1, block(0, 0, 1, 1));
  assert(!valid(many, 8, 8));
  return 0;
}
