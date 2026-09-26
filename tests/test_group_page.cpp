#include "screen_text_en.h"
// c++ -std=c++17 -Wall -Wextra -pedantic tests/test_group_page.cpp -o /tmp/test_group_page && /tmp/test_group_page
// The model of a light group's lamp page (firmware 0.3.9+): which lights have one, which lamps get the colour panel,
// where the cards stand on each board, and how a value just sent is held.
#define GROUP_PAGE_TEST
#define THEME_TEST
#include "../components/smart_display/group_page.h"
#include <cassert>

using namespace group_page;
using runtime_tiles::Tile;

int main() {
  // A light with lamps has a page; a light without, or anything else, has none.
  Tile group; group.entity = "light.living_room";
  assert(!available(group));
  Lamp spot; spot.entity = "light.spot"; spot.dimmable = true; spot.temperature = true; spot.low = 2202; spot.high = 6535;
  group.edit_extra().lamps.push_back(spot);
  assert(available(group));
  Tile sw; sw.entity = "switch.x"; sw.edit_extra().lamps.push_back(spot);
  assert(!available(sw));

  // The ellipsis key: a colour or a white shade, and a lamp that answers.
  assert(has_panel(spot));
  Lamp plain; plain.dimmable = true;
  assert(!has_panel(plain));
  Lamp gone = spot; gone.unavailable = true;
  assert(!has_panel(gone));

  // A white shade stays in the lamp's own range, or the fallback when it names none.
  assert(kelvin_low(spot) == 2202 && kelvin_high(spot) == 6535);
  assert(kelvin_of(spot, 2000) == 2202 && kelvin_of(spot, 9000) == 6535 && kelvin_of(spot, 3000) == 3000);
  assert(kelvin_low(plain) == KELVIN_LOW && kelvin_high(plain) == KELVIN_HIGH);

  // Where the cards stand. The Guition's standard look: one column, four lamps, then a pager.
  ui::configure(170, "standard");
  Room guition; guition.width = 480; guition.height = 480; guition.pad = 20; guition.top = 86; guition.pager = 40; guition.pager_bottom = 16;
  Layout g = layout(3, guition);
  assert(g.cols == 1 && g.pages == 1 && g.pager_y == 0);
  g = layout(20, guition);
  assert(g.cols == 1 && g.per_page == 4 && g.pages == 5 && g.pager_y > 0);
  assert(g.card_y(g.per_page - 1) + g.card_h <= g.pager_y);
  // The CYD's compact look lying down: two columns, six lamps a page, nothing under a finger's width.
  ui::configure(143, "compact");
  Room cyd; cyd.width = 320; cyd.height = 240; cyd.pad = 10; cyd.top = 52; cyd.pager = 26; cyd.pager_bottom = 10; cyd.large = false;
  Layout c = layout(20, cyd);
  assert(c.cols == 2 && c.per_page == 6 && c.pages == 4);
  assert(c.card_h >= ui::touch_min());
  assert(c.card_x(1) + c.card_w <= cyd.width - 2 * cyd.pad);
  // Standing up: one column.
  Room tall = cyd; tall.width = 240; tall.height = 320;
  assert(layout(20, tall).cols == 1);
  // Every lamp lands on a page, and no page is empty.
  for (int n = 1; n <= static_cast<int>(runtime_tiles::MAX_LAMPS); ++n) {
    Layout l = layout(n, cyd);
    assert((l.pages - 1) * l.per_page < n && l.pages * l.per_page >= n);
  }

  // A value just sent is shown until Home Assistant reports it, or four seconds at most.
  Held held;
  assert(held.show(40, 0) == 40);
  held.send(80, 1000);
  assert(held.show(40, 1500) == 80);
  assert(held.show(80, 1600) == 80 && held.value < 0);
  held.send(70, 2000);
  assert(held.show(40, 2000 + SENT_HOLD_MS) == 40);
  return 0;
}
