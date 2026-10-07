// A board with the memory for more states its own ceilings (firmware 0.34.0+): SCREEN_MAX_TILES and SCREEN_MAX_PAGES,
// build flags from its board file. These are the numbers of an ESP32-S3 board with PSRAM and a 2 x 3 grid; every table
// with one entry per tile or per page follows them, and nothing past them is taken.
#define SCREEN_MAX_TILES 128
#define SCREEN_MAX_PAGES 24
#define GRID_COLS 2
#define GRID_ROWS 3
#include "screen_text_en.h"
#include "../components/smart_display/runtime_model.h"
#include "../components/smart_display/kept_pages.h"
#include <cassert>

static void the_ceilings_follow_the_board() {
  using namespace runtime_tiles;
  static_assert(TILES_MAX == 128 && PAGES_MAX == 24, "the board's numbers");
  assert(grid.pages() == 24 && grid.max_slots() == 144 && grid.max_tiles() == 128);
  kept_pages::Changes changes;
  assert(changes.tile.size() == 128);
  const uint32_t all = changes.all;
  changes.mark_tile(127);
  assert(changes.all == all && changes.tile_after(127, 0));
  changes.mark_tile(128);
  assert(changes.all > all);
  // Every page beside the one on the glass may be kept (GitHub #183): paging is as quick on page 13 as on page 2. The
  // board's PSRAM decides how many it really makes (runtime_tiles::kept_capacity).
  static_assert(kept_pages::MAX_KEPT == page_protocol::MAX_PAGES - 1, "every page beside the one on the glass may be kept");
}

static void a_layout_may_fill_them_and_no_more() {
  using namespace runtime_tiles;
  Model m;
  assert(m.begin(128, 24, "Everything") && m.count == 128 && m.page_data.records.size() == 24);
  assert(!m.begin(129, 24, "One too many") && m.count == 128);
  assert(!m.begin(1, 25, "A page too many"));
}

static void navigation_reaches_every_page() {
  using namespace runtime_tiles;
  assert(valid_entity("screen.page_9") && valid_entity("screen.page_10") && valid_entity("screen.page_24"));
  assert(!valid_entity("screen.page_25") && !valid_entity("screen.page_0") && !valid_entity("screen.page_01"));
  Tile t;
  t.entity = "screen.page_17";
  assert(t.is_page() && t.page_target() == 17);
}

static void a_transfer_counts_every_tile_and_page() {
  using namespace page_protocol;
  Transfer transfer;
  transfer.grant(1, 2);
  assert(transfer.begin(7, 24, 128) == Begin::replace);
  for (unsigned p = 0; p < 24; ++p) assert(transfer.page(p) && !transfer.page(p));
  for (unsigned t = 0; t < 127; ++t) assert(transfer.tile(t) && !transfer.tile(t));
  assert(!transfer.complete() && !transfer.tile(128) && !transfer.page(24));
  assert(transfer.tile(127) && transfer.complete() && transfer.commit());
  // The same layout again is unchanged: 128 tiles fit the count, where a byte would have wrapped.
  transfer.grant(3, 4);
  assert(transfer.begin(7, 24, 128) == Begin::unchanged);
  // More than the board holds is refused before anything is sent.
  Transfer other;
  other.grant(5, 6);
  assert(other.begin(8, 25, 1) == Begin::reject);
  other.grant(9, 10);
  assert(other.begin(8, 1, 129) == Begin::reject);
}

int main() {
  the_ceilings_follow_the_board();
  a_layout_may_fill_them_and_no_more();
  navigation_reaches_every_page();
  a_transfer_counts_every_tile_and_page();
  return 0;
}
