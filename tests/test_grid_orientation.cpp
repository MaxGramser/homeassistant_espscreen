// A board states the cells of a page for each way its glass can hang, and the screen picks one at boot from
// the canvas LVGL gives it (firmware 0.2.92+). These are a CYD's two grids: six cells lying down, four
// standing up. The same numbers are in packages/boards/cyd-2432s028.yaml.
#define GRID_COLS 2
#define GRID_ROWS 3
#define GRID_COLS_PORTRAIT 1
#define GRID_ROWS_PORTRAIT 4

#include "screen_text_en.h"
#include "../components/smart_display/runtime_model.h"
#include <cassert>

using namespace runtime_tiles;

static void the_grid_counts_like_the_manager_does() {
  // Every rule here has a twin in screen_manager/app/core.py, class Grid, and a slot number means the same
  // thing on both sides of the wire. A screen holds 64 tiles at most, one dirty bit each, over eight pages whatever its grid.
  const Grid lying{2, 3};
  assert(lying.slots() == 6 && lying.pages() == 8 && lying.max_slots() == 48 && lying.max_tiles() == 48);
  const Grid standing{1, 4};
  assert(standing.slots() == 4 && standing.pages() == 8 && standing.max_slots() == 32);
  // Every grid has all eight pages (firmware 0.18.0+); only the tiles of the whole screen stop at 64, so a page need
  // not be full and a grid that grows keeps the pages of a saved layout.
  const Grid wide{3, 3};
  assert(wide.slots() == 9 && wide.pages() == 8 && wide.max_slots() == 72 && wide.max_tiles() == 64);
  const Grid ten_inch{5, 5};
  assert(ten_inch.slots() == 25 && ten_inch.pages() == 8 && ten_inch.max_slots() == 200 && ten_inch.max_tiles() == 64);
  const Grid huge{8, 8};
  assert(huge.slots() == 64 && huge.pages() == 8 && huge.max_tiles() == 64);

  // A wide card takes the cell beside it, and on a single column it is simply the cell itself.
  assert(lying.wide_span() == 2 && standing.wide_span() == 1);
  assert(lying.wide_fits(0) && !lying.wide_fits(1) && lying.wide_fits(2));
  assert(standing.wide_fits(0) && standing.wide_fits(3));
  assert(wide.wide_fits(0) && wide.wide_fits(1) && !wide.wide_fits(2));

  // Reading a slot back as a page, a row and a column.
  assert(lying.page_of(0) == 0 && lying.page_of(5) == 0 && lying.page_of(6) == 1);
  assert(lying.row_of(0) == 0 && lying.row_of(2) == 1 && lying.row_of(7) == 0);
  assert(lying.column_of(0) == 0 && lying.column_of(3) == 1);
  assert(standing.row_of(3) == 3 && standing.column_of(3) == 0);
}

static void the_canvas_picks_the_grid() {
  // Wider than it is tall: lying down. Taller: standing up. Square counts as lying down, which is what LVGL's
  // own orientation does, so a square board answers the same grid either way and never has to state a second.
  grid_select(320, 240);
  assert(grid.columns == 2 && grid.rows == 3 && grid.slots() == 6);
  grid_select(240, 320);
  assert(grid.columns == 1 && grid.rows == 4 && grid.slots() == 4);
  grid_select(480, 480);
  assert(grid.columns == 2 && grid.rows == 3);
  // And back, because a screen may be turned a half turn in its settings without the grid moving.
  grid_select(320, 240);
  assert(grid.slots() == 6);
}

static void the_cards_are_sized_for_the_bigger_grid() {
  // One set of cards serves both ways round: six on a CYD, of which four show when it stands up. Nothing is
  // allocated twice, and the descriptors are long enough for the longer of the four numbers.
  assert(CELLS_MAX == 6);
  assert(DIM_MAX == 4);
  assert(CELLS_MAX <= TILES_MAX);
}

static void explicit_placements_use_the_live_grid() {
  Model model;
  std::array<Placement, TILES_MAX> out;
  grid_select(320, 240);
  assert(model.begin(4, 1, "Landscape"));
  model.slots[0] = 0; model.slots[1] = 2; model.slots[2] = 4; model.slots[3] = 5;
  model.tiles[1].wide = true;
  assert(!model.valid_placement(1, 1, false, true));
  assert(place(model, out) == 1 && out[1].slot == 2 && out[3].slot == 5);
  grid_select(240, 320);
  assert(model.begin(4, 1, "Portrait"));
  for (unsigned i = 0; i < 4; ++i) model.slots[i] = i;
  model.tiles[1].wide = true;
  assert(model.valid_placement(1, 1, false, true));
  assert(place(model, out) == 1 && out[1].slot == 1 && out[3].slot == 3);
  assert(model.begin(4, 3, "Full page"));
  model.slots[0] = 0; model.slots[1] = 4; model.slots[2] = 8; model.slots[3] = 9;
  model.tiles[1].full = true;
  assert(place(model, out) == 3 && out[1].page == 1 && out[2].page == 2);
  grid_select(320, 240);
}

static void a_navigation_tile_may_only_name_a_page_that_exists() {
  // screen.page_<n> is checked against the pages this grid holds, and the grid comes from the canvas.
  grid_select(320, 240);
  assert(valid_entity("screen.page_8") && !valid_entity("screen.page_9"));
  grid_select(240, 320);
  assert(valid_entity("screen.page_8"));
}

int main() {
  the_grid_counts_like_the_manager_does();
  the_canvas_picks_the_grid();
  the_cards_are_sized_for_the_bigger_grid();
  explicit_placements_use_the_live_grid();
  a_navigation_tile_may_only_name_a_page_that_exists();
}
