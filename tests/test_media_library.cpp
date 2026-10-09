// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_media_library.cpp -o /tmp/test_media_library && /tmp/test_media_library
// A player's library (firmware 0.24.0+): what a folder holds as it comes in, how a page is laid out on every glass, the
// pager and the speaker menu. media_library.cpp draws what these numbers say.
#include "../components/smart_display/media_library.h"
#include <cassert>
#include <cstdio>

using namespace media_library;

static bool inside(const Rect &r, int width, int height) { return r.x >= 0 && r.y >= 0 && r.right() <= width && r.bottom() <= height; }
static bool apart(const Rect &a, const Rect &b) { return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y; }

// Every cell of a full page on the glass, under the top bar, above the pager, none over another; a cover inside its cell.
static void sound(const Shape &s, const Grid &g) {
  assert(g.columns >= 1 && g.rows >= 1 && g.per_page == g.columns * g.rows);
  for (int n = 0; n < g.per_page; ++n) {
    const Rect c = g.cell(n);
    assert(c.w > 0 && c.h > 0 && inside(c, s.width, s.height) && c.y >= s.top);
    if (g.pager) assert(c.bottom() <= g.pager_y);
    for (int k = 0; k < n; ++k) assert(apart(c, g.cell(k)));
    if (g.covers) {
      const Rect a = g.cover(n);
      assert(a.w == a.h && a.w == g.art && a.y == c.y + g.ring);
      // The ring round the cover stays inside the cell (LVGL redraws a cell's parts only there).
      assert(a.x - g.ring >= c.x && a.right() + g.ring <= c.right() && a.y - g.ring >= c.y);
      // Two lines of title fit under it, under the ring.
      assert(c.bottom() - (a.bottom() + g.ring) >= 2 * s.line_h);
    }
  }
  if (g.pager) assert(g.pager_y + s.pager_h <= s.height);
}

int main() {
  // The Guition (480x480): three covers a row, two rows; the top folder's eight cards two by four, on one page.
  {
    Shape s;
    Grid g = place(s, true, 48);
    sound(s, g);
    assert(g.columns == 3 && g.rows == 2 && g.per_page == 6 && g.pager);
    assert(page_count(48, g.per_page) == 8);
    assert(g.art >= 90);
    Grid top = place(s, false, 8);
    sound(s, top);
    assert(top.columns == 2 && top.per_page >= 8 && !top.pager);
    printf("guition: covers %dx%d art %d, cards %dx%d h=%d\n", g.columns, g.rows, g.art, top.columns, top.rows, top.cell_h);
  }
  // The Waveshare 4.3 (800x480, wide): five covers a row.
  {
    Shape s; s.width = 800; s.height = 480; s.pad = 26; s.top = 112; s.gap = 15; s.line_h = 25; s.pager_h = 58; s.card_h = 90;
    Grid g = place(s, true, 48);
    sound(s, g);
    assert(g.columns == 5 && g.rows == 2 && g.art >= s.min_art);
    Grid cards = place(s, false, 8);
    sound(s, cards);
    assert(cards.columns == 4);
    printf("waveshare 4.3: covers %dx%d art %d (%u pages), cards %dx%d\n", g.columns, g.rows, g.art, page_count(48, g.per_page), cards.columns, cards.rows);
  }
  // The ten-inch (1280x800): six covers a row.
  {
    Shape s; s.width = 1280; s.height = 800; s.pad = 30; s.top = 130; s.gap = 18; s.line_h = 30; s.pager_h = 70; s.card_h = 108;
    Grid g = place(s, true, 48);
    sound(s, g);
    assert(g.columns == 6 && g.rows >= 2);
    printf("ten-inch: covers %dx%d art %d (%u pages)\n", g.columns, g.rows, g.art, page_count(48, g.per_page));
  }
  // The CYD (320x240) draws no pictures: cards, two a row, paged.
  {
    Shape s; s.width = 320; s.height = 240; s.pad = 12; s.top = 58; s.gap = 6; s.line_h = 15; s.pager_h = 30; s.card_h = 42;
    Grid g = place(s, false, 8);
    sound(s, g);
    assert(g.columns == 2 && g.pager && page_count(8, g.per_page) >= 2);
    Grid one = place(s, false, 2);
    assert(!one.pager);
    printf("cyd: cards %dx%d h=%d (%u pages for 8)\n", g.columns, g.rows, g.cell_h, page_count(8, g.per_page));
  }
  // A standing glass (480x800) keeps three covers a row and more rows.
  {
    Shape s; s.width = 480; s.height = 800;
    Grid g = place(s, true, 48);
    sound(s, g);
    assert(g.columns == 3 && g.rows >= 3);
  }
  // The pager counts at most 48 items.
  assert(page_count(0, 6) == 1 && page_count(6, 6) == 1 && page_count(7, 6) == 2 && page_count(48, 6) == 8 && page_count(200, 6) == 8);
  assert(page_count(48, 4) == 12);
  assert(first_of(2, 6) == 12 && end_of(2, 6, 48) == 18 && end_of(7, 6, 46) == 46 && end_of(9, 6, 200) == 48);
  // What a tap does.
  assert(tap_of(CAN_PLAY | CAN_EXPAND) == Tap::play && tap_of(CAN_PLAY | CAN_EXPAND, true) == Tap::open);
  assert(tap_of(CAN_EXPAND) == Tap::open && tap_of(CAN_PLAY, true) == Tap::play && tap_of(0) == Tap::none);
  // A folder comes page by page, in order, and only the one asked for.
  {
    Folder f; f.token = 7;
    Answer a; a.entity = "media_player.spotify"; a.folder = 7; a.page = 0; a.pages = 2; a.title = "Albums";
    for (int i = 0; i < 30; ++i) a.items.push_back(Item{static_cast<uint32_t>(i + 1), "Album", PICTURED | CAN_PLAY, 0});
    Answer other = a; other.folder = 8;
    assert(!f.take(std::move(other)));
    Answer late = a; late.page = 1;
    assert(!f.take(std::move(late)));
    assert(f.take(std::move(a)) && !f.complete && f.next == 1 && f.title == "Albums" && f.pictured());
    Answer b; b.folder = 7; b.page = 1; b.pages = 2;
    for (int i = 0; i < 30; ++i) b.items.push_back(Item{static_cast<uint32_t>(i + 31), "Album", CAN_PLAY, 0});
    assert(f.take(std::move(b)) && f.complete && f.items.size() == LIMIT);
    Folder g; g.token = 3;
    Answer failed; failed.folder = 3; failed.failed = true;
    assert(g.take(std::move(failed)) && g.complete && g.failed && g.items.empty());
    Folder h;
    Answer empty; empty.title = "Media Library";
    assert(h.take(std::move(empty)) && h.complete && h.items.empty() && !h.pictured());
  }
  // The speaker menu (firmware 0.26.0+): pages by height, a speaker in the group a row taller for its volume, and the
  // pager's row kept on every page once they do not all fit.
  {
    assert((page_starts({56, 56}, 372, 56) == std::vector<size_t>{0}));
    std::vector<int> sixteen(16, 56);
    assert((page_starts(sixteen, 372, 56) == std::vector<size_t>{0, 5, 10, 15}));
    // Two in the group (56 + 48 each) and four others on a CYD's 190 pixels.
    assert((page_starts({104, 104, 40, 40, 40, 40}, 190, 40) == std::vector<size_t>{0, 1, 3}));
    // A row taller than the page still gets a page of its own.
    assert((page_starts({300, 40}, 200, 40) == std::vector<size_t>{0, 1}));
  }
  printf("test_media_library: ok\n");
  return 0;
}
