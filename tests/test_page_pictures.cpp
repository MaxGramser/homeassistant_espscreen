// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_page_pictures.cpp -o /tmp/test_page_pictures && /tmp/test_page_pictures
// The rules of page pictures (docs/KEPT_PAGES.md, "Page pictures"): which blocks of a picture are true, what a page
// that comes back lacks, which pages hold a picture and how many a board keeps.
#include "../components/smart_display/page_pictures.h"
#include <cassert>
#include <vector>

using namespace page_pictures;

// A glass of pixels, to copy as the firmware does: every pixel a take or a put touches, counted.
struct Glass {
  int w, h;
  std::vector<uint16_t> px;
  Glass(int w, int h, uint16_t fill) : w(w), h(h), px(static_cast<size_t>(w) * h, fill) {}
  void fill(const Rect &r, uint16_t v) {
    for (int y = r.y; y < r.y + r.h; ++y) for (int x = r.x; x < r.x + r.w; ++x) px[static_cast<size_t>(y) * w + x] = v;
  }
};
static void copy(const Map &map, int row, uint32_t blocks, const Glass &from, Glass &to) {
  runs(map, row, blocks, [&](const Rect &r) {
    for (int y = r.y; y < r.y + r.h; ++y)
      for (int x = r.x; x < r.x + r.w; ++x) to.px[static_cast<size_t>(y) * to.w + x] = from.px[static_cast<size_t>(y) * from.w + x];
  });
}
static void take(Map &map, const Glass &glass, Glass &picture) {
  for (int row = 0; row < map.rows; ++row) {
    const uint32_t blocks = map.wanted(row);
    copy(map, row, blocks, glass, picture);
    map.took(row, blocks);
  }
}
static void put(const Map &map, const Glass &picture, Glass &glass) {
  for (int row = 0; row < map.rows; ++row) copy(map, row, map.good[row], picture, glass);
}

int main() {
  assert(bits(0, 32) == 0xFFFFFFFFu && bits(3, 5) == 0x18u && bits(4, 4) == 0 && bits(31, 32) == 0x80000000u);

  // ---- The map ----
  // A glass of 1280 x 800 with the page's room below a top bar of 56 px and above a page bar of 70.
  const Rect room{0, 56, 1280, 674};
  Map map;
  assert(!map.shaped() && map.true_blocks() == 0);
  assert(map.shape(1280, 800, 0, room));
  assert(map.columns == 20 && map.rows == 13 && map.room_blocks() == 20 * 12 && map.true_blocks() == 0 && !map.whole());
  assert(map.fits(1280, 800, 0, room) && !map.fits(1280, 800, 90, room) && !map.fits(800, 1280, 0, room));
  assert(!map.fits(1280, 800, 0, Rect{0, 56, 1280, 744}));  // the page bar went: another room
  // A room that is not on the panel, or a panel no map holds, gives no map.
  Map none;
  assert(!none.shape(1280, 800, 0, Rect{0, 700, 1280, 200}) && !none.shaped());
  assert(!none.shape(4096, 800, 0, Rect{0, 0, 100, 100}) && !none.shape(1280, 800, 0, Rect{}));

  // A take copies the room and nothing else: the bars' pixels never reach a picture.
  Glass glass(1280, 800, 0x1111), picture(1280, 800, 0);
  glass.fill(Rect{0, 0, 1280, 56}, 0xAAAA);    // the top bar
  glass.fill(Rect{0, 730, 1280, 70}, 0xBBBB);  // the page bar
  take(map, glass, picture);
  assert(map.whole() && map.true_blocks() == 240);
  for (int y = 0; y < 800; ++y)
    for (int x = 0; x < 1280; x += 37) assert(picture.px[static_cast<size_t>(y) * 1280 + x] == (y >= 56 && y < 730 ? 0x1111 : 0));
  assert(bytes_of(map, 0, map.in_room[0]) == 1280u * 8 * 2);    // the first row of blocks: 8 px of it are the room's
  assert(bytes_of(map, 11, map.in_room[11]) == 1280u * 26 * 2);  // the last: 26
  assert(bytes_of(map, 12, 0xFFFFFFFFu) == 0);                   // the page bar's row: nothing

  // LVGL draws a card again: its blocks, rounded out, are true no more, and only they are taken again.
  const Rect card{200, 200, 300, 150};  // blocks 3..7 across, 3..5 down
  map.untrue(card);
  assert(map.true_blocks() == 240 - 5 * 3 && !map.is_true(3, 3) && !map.is_true(7, 5) && map.is_true(2, 3) && map.is_true(8, 5) && map.is_true(3, 2));
  assert(map.wanted(3) == bits(3, 8) && map.wanted(2) == 0 && map.wanted(3, bits(3, 5)) == bits(5, 8));
  // A put with that card's value changed on the glass under it: every pixel outside the card's blocks is the
  // picture's, every pixel inside them is left as the glass had it.
  Glass now(1280, 800, 0x2222);  // another page on the glass
  put(map, picture, now);
  for (int y = 0; y < 800; ++y)
    for (int x = 0; x < 1280; ++x) {
      const bool in_room = y >= 56 && y < 730, hole = x >= 192 && x < 512 && y >= 192 && y < 384;
      assert(now.px[static_cast<size_t>(y) * 1280 + x] == (in_room && !hole ? 0x1111 : 0x2222));
    }
  // An area that reaches past the panel, or lies off it, touches what is on it and no more.
  Map edge = map;
  edge.untrue(Rect{-50, -50, 100, 200});
  assert(!edge.is_true(0, 0) && !edge.is_true(0, 2) && edge.is_true(1, 1) && edge.is_true(0, 3));
  edge.untrue(Rect{2000, 2000, 10, 10});
  edge.untrue(Rect{100, 100, 0, 50});
  assert(edge.true_blocks() == map.true_blocks() - 3);
  // took() never makes a block outside the room true.
  edge.took(12, 0xFFFFFFFFu);
  assert(!edge.is_true(0, 12));

  // The same room on the panel of a glass that stands up (LVGL turned 90 degrees): the rectangles of the screen go
  // through glass::on_panel, and a card that changes there costs the blocks under it on the panel.
  const Rect upright_room = glass::on_panel(Rect{0, 56, 800, 1154}, 90, 1280, 800);
  Map turned;
  assert(turned.shape(1280, 800, 90, upright_room) && (upright_room == Rect{70, 0, 1154, 800}));
  Glass g2(1280, 800, 0x3333), p2(1280, 800, 0);
  take(turned, g2, p2);
  assert(turned.whole());
  turned.untrue(glass::on_panel(Rect{100, 100, 200, 100}, 90, 1280, 800));  // x 1080..1179, y 100..299 on the panel
  assert(!turned.is_true(16, 1) && !turned.is_true(18, 4) && turned.is_true(15, 1) && turned.is_true(19, 1) && turned.is_true(16, 5));

  // ---- A take in steps, with a value that changes between two of them ----
  // The first step copies the upper rows; then LVGL draws a card anew, one that reaches from rows already copied into
  // rows still to come; the later steps copy the rest and the card's blocks again. No block holds half of a drawing:
  // the picture is the glass, pixel for pixel, in every block that is true.
  {
    Map steps;
    assert(steps.shape(1280, 800, 0, room));
    Glass g(1280, 800, 0x1111), p(1280, 800, 0);
    for (int row = 0; row < 4; ++row) { copy(steps, row, steps.wanted(row), g, p); steps.took(row, steps.wanted(row)); }
    const Rect changed{300, 150, 200, 250};  // rows 2 to 6 of blocks: 2 and 3 are copied, 4 to 6 are not yet
    g.fill(changed, 0x7777);                 // LVGL draws the new value...
    steps.untrue(changed);                   // ...and its refresh says so before the next step
    assert(!steps.is_true(4, 2) && !steps.is_true(7, 3) && steps.is_true(3, 2));
    take(steps, g, p);
    assert(steps.whole());
    for (int y = 56; y < 730; ++y)
      for (int x = 0; x < 1280; ++x) assert(p.px[static_cast<size_t>(y) * 1280 + x] == g.px[static_cast<size_t>(y) * 1280 + x]);
  }

  // ---- A block is taken once it stood still ----
  // A card that draws every second is never still for a second and a half: its blocks wait, the rest is taken.
  Stillness still;
  assert(still.moving(3, 5000, 1500) == 0);  // nothing was ever drawn
  for (uint32_t t = 1000; t <= 5000; t += 1000) still.drawn(map, card, t);
  assert(still.moving(3, 5400, 1500) == bits(3, 8) && still.moving(5, 5400, 1500) == bits(3, 8) && still.moving(2, 5400, 1500) == 0);
  assert(map.wanted(3, still.moving(3, 5400, 1500)) == 0);              // moved 400 ms ago: not now
  assert(map.wanted(3, still.moving(3, 6500, 1500)) == bits(3, 8));     // still for a second and a half: now
  still.drawn(map, Rect{0, 0, 1280, 800}, 0xFFFFFFF0u);                 // the clock wraps: the sum still holds
  assert(still.moving(0, 0x00000010u, 1500) == bits(0, 20) && still.moving(0, 0x00000010u + 2000, 1500) == 0);

  // ---- What a page that comes back lacks ----
  kept_pages::Changes changes;
  Map away = map;
  for (int row = 0; row < away.rows; ++row) away.took(row, away.wanted(row));
  assert(away.whole());
  const Card cards[] = {{4, Rect{0, 64, 320, 320}}, {7, Rect{640, 64, 320, 320}}};
  const uint32_t left = changes.last;
  // Nothing changed: all of it is put.
  Map back = away;
  assert(settle(back, cards, 2, changes, left) && back.whole());
  // A tile of another page changed: nothing of this page.
  changes.mark_tile(9);
  back = away;
  assert(settle(back, cards, 2, changes, left) && back.whole());
  // One of its tiles changed: that card's blocks are left to LVGL, the rest is put.
  changes.mark_tile(7);
  back = away;
  assert(settle(back, cards, 2, changes, left) && back.true_blocks() == 240 - 5 * 5 && !back.is_true(10, 1) && back.is_true(0, 1));
  // A change before the page left is on its picture.
  back = away;
  assert(settle(back, cards, 2, changes, changes.last) && back.whole());
  // Everything was asked to be drawn again (the look, Home Assistant gone or back): no block is true.
  changes.mark_all();
  back = away;
  assert(!settle(back, cards, 2, changes, left) && back.true_blocks() == 0);

  // ---- How many ----
  const size_t MB = 1u << 20, one = 1280u * 800 * 2;
  // A picture for every page of the layout, within half of the PSRAM heap: the 29.3 MB a 32 MB chip gives hold seven
  // pages of a 1280 x 800 glass, so six pages all have one and a layout of sixteen keeps seven; 16 MB hold three.
  const size_t heap32 = 29320u << 10;
  assert(share(32 * MB) == 16 * MB && reserve(32 * MB) == 8 * MB && reserve(8 * MB) == 8 * MB / 5 + 2 * MB);
  assert(count(heap32, one, 6) == 6 && count(heap32, one, 7) == 7 && count(heap32, one, 16) == 7 && count(heap32, one, 1) == 0);
  assert(count(16 * MB, one, 8) == 4 && count(8 * MB, one, 8) == 2 && count(4 * MB, one, 8) == 0 && count(0, one, 8) == 0 && count(32 * MB, 0, 8) == 0);  // one picture alone is none
  assert(count(32 * MB, 480u * 480 * 2, 20) == (MAX_KEPT < 20 ? MAX_KEPT : 20));
  assert(affords(20 * MB, 32 * MB, one) && !affords(9 * MB, 32 * MB, one) && !affords(MB, 32 * MB, one));
  assert(reserve(32 * MB) == picture_store::budget_for(32 * MB) + kept_pages::KEEP_RESERVE);  // asked, not written again
  // Short of memory a picture goes. One refusal costs one picture, never a second (a board let both of its pictures
  // go for one refused ask, 2026-11-16): the next look finds it answered.
  Yield yield;
  assert(!yield.due(0, 0, 20 * MB, 2 * one));
  assert(yield.due(1, 3 * MB, MB * 5 / 2, 2 * one));   // 3 MB refused with 2.5 free and 4 held: letting go helps
  assert(!yield.due(1, 3 * MB, 5 * MB, one));          // the same refusal again: answered
  assert(yield.due(2, 3 * MB, 5 * MB, one));           // refused once more: the next picture
  // An ask no picture could help costs none: 40 MB with 20 free and 4 held.
  assert(!yield.due(3, 40 * MB, 20 * MB, 2 * one) && !yield.due(3, 40 * MB, 20 * MB, 2 * one));
  // Nothing held: nothing to give.
  assert(!yield.due(4, MB, 3 * MB, 0));
  // Under the kept pages' reserve one goes at every look, refusal or not, until it is over it.
  assert(yield.due(4, 0, MB, 2 * one) && yield.due(4, 0, MB, one) && !yield.due(4, 0, 3 * MB, one));

  // ---- Which pages ----
  assert(apart(0, 7, 8, false) == 7 && apart(0, 7, 8, true) == 1 && apart(2, 5, 8, true) == 3 && apart(3, 3, 8, true) == 0);
  Shelf shelf;
  bool fresh = false;
  assert(shelf.take(0, 8, false, fresh) == NONE);  // no room: no picture
  shelf.capacity = 3;
  assert(shelf.take(0, 8, false, fresh) == 0 && fresh);
  assert(shelf.take(1, 8, false, fresh) == 1 && fresh);
  assert(shelf.take(0, 8, false, fresh) == 0 && !fresh && shelf.held(1) == 1);
  assert(shelf.take(2, 8, false, fresh) == 2 && fresh && shelf.pages() == 3);
  // Page 3 comes: the page farthest from it gives its picture up (page 0), the neighbours stay.
  assert(shelf.take(3, 8, false, fresh) == 0 && fresh && shelf.held(0) == NONE && shelf.held(1) == 1 && shelf.held(2) == 2);
  // With pages that loop, page 7 is page 0's neighbour: from page 0, page 3 is the farthest of 1, 2 and 3.
  Shelf loop;
  loop.capacity = 3;
  loop.take(7, 8, true, fresh); loop.take(1, 8, true, fresh); loop.take(4, 8, true, fresh);
  assert(loop.take(0, 8, true, fresh) == 2 && loop.held(7) == 0 && loop.held(1) == 1 && loop.held(4) == NONE);
  // Without the loop page 7 is the farthest from page 0.
  Shelf line;
  line.capacity = 3;
  line.take(7, 8, false, fresh); line.take(1, 8, false, fresh); line.take(4, 8, false, fresh);
  assert(line.take(0, 8, false, fresh) == 0 && line.held(7) == NONE);
  // Of two as far, the one on the glass longest ago goes.
  Shelf tie;
  tie.capacity = 2;
  tie.take(2, 8, false, fresh); tie.take(4, 8, false, fresh);
  assert(tie.take(3, 8, false, fresh) == 0 && tie.held(4) == 1);
  // ---- Made ahead ----
  // After a start page 0 is on the glass and no page has a picture: the nearest first, the page after before the page
  // before, around the end when the pages loop.
  {
    Shelf ahead;
    ahead.capacity = 6;
    bool f = false;
    auto lacks = [&](int page) { return ahead.held(page) == NONE; };
    std::vector<int> order;
    ahead.take(0, 6, true, f);
    for (int page; (page = ahead.next_ahead(0, 6, true, lacks)) >= 0;) { order.push_back(page); assert(ahead.take_for(page, 0, 6, true, f) != NONE && f); }
    assert((order == std::vector<int>{1, 5, 2, 4, 3}) && ahead.pages() == 6);
    // Without the loop from page 0 there is only the way forward.
    Shelf line2;
    line2.capacity = 6;
    order.clear();
    auto lacks2 = [&](int page) { return line2.held(page) == NONE; };
    line2.take(0, 6, false, f);
    for (int page; (page = line2.next_ahead(0, 6, false, lacks2)) >= 0;) { order.push_back(page); line2.take_for(page, 0, 6, false, f); }
    assert((order == std::vector<int>{1, 2, 3, 4, 5}));
    // Sixteen pages and room for seven: the glass's page and the three each side, and then nothing more is made: a
    // farther page never takes a nearer one's picture.
    Shelf few;
    few.capacity = 7;
    order.clear();
    auto lacks3 = [&](int page) { return few.held(page) == NONE; };
    few.take(8, 16, true, f);
    for (int page; (page = few.next_ahead(8, 16, true, lacks3)) >= 0;) { order.push_back(page); few.take_for(page, 8, 16, true, f); }
    assert((order == std::vector<int>{9, 7, 10, 6, 11, 5}) && few.take_for(12, 8, 16, true, f) == NONE);
    // The glass moves on to page 11: page 12 comes ahead now and the farthest (5) gives its entry up for it.
    assert(few.take(11, 16, true, f) != NONE && !f);
    assert(few.next_ahead(11, 16, true, lacks3) == 12 && few.take_for(12, 11, 16, true, f) != NONE && few.held(5) == NONE);
    // A page whose picture has nothing true is made again, though it holds an entry.
    assert(few.next_ahead(11, 16, true, [&](int page) { return page == 10 || few.held(page) == NONE; }) == 10);
  }
  // A picture drawn off the glass lands where the glass would have it, however the panel is turned: every pixel of the
  // screen at (x, y) is on the panel where glass::on_panel puts it.
  for (int turn : {0, 90, 180, 270}) {
    const int sw = turn % 180 ? 96 : 160, sh = turn % 180 ? 160 : 96, pw = 160, ph = 96;
    std::vector<uint8_t> screen(static_cast<size_t>(sw) * sh * 2 + 64);
    const size_t stride = static_cast<size_t>(sw) * 2;
    auto value = [&](int x, int y) { return static_cast<uint16_t>(x * 251 + y * 7 + 1); };
    for (int y = 0; y < sh; ++y) for (int x = 0; x < sw; ++x) { screen[y * stride + x * 2] = value(x, y) & 0xFF; screen[y * stride + x * 2 + 1] = value(x, y) >> 8; }
    const Rect screen_room{8, 16, sw - 24, sh - 40}, panel_room = glass::on_panel(screen_room, turn, pw, ph);
    std::vector<uint16_t> out(static_cast<size_t>(pw) * ph, 0xDEAD);
    page_pictures::turned(screen.data(), sw, sh, stride, out.data(), pw, ph, turn, panel_room, false);
    for (int y = 0; y < sh; ++y)
      for (int x = 0; x < sw; ++x) {
        const Rect at = glass::on_panel(Rect{x, y, 1, 1}, turn, pw, ph);
        const bool in_room = x >= screen_room.x && x < screen_room.x + screen_room.w && y >= screen_room.y && y < screen_room.y + screen_room.h;
        assert(out[static_cast<size_t>(at.y) * pw + at.x] == (in_room ? value(x, y) : 0xDEAD));
      }
    page_pictures::turned(screen.data(), sw, sh, stride, out.data(), pw, ph, turn, panel_room, true);
    const Rect corner = glass::on_panel(Rect{screen_room.x, screen_room.y, 1, 1}, turn, pw, ph);
    const uint16_t v = value(screen_room.x, screen_room.y);
    assert(out[static_cast<size_t>(corner.y) * pw + corner.x] == static_cast<uint16_t>(v << 8 | v >> 8));
  }

  // Memory is short: the page farthest from the glass lets go first, the glass's own last, and then there is none.
  Shelf yields;
  yields.capacity = 4;
  for (int page : {0, 1, 2, 5}) yields.take(page, 8, false, fresh);
  assert(yields.let_go(1, 8, false) == 3 && yields.held(5) == NONE && yields.pages() == 3);  // page 5 is 4 away
  assert(yields.let_go(1, 8, false) == 0 && yields.held(0) == NONE);  // 0 and 2 are as far: 0 was on the glass longer ago
  assert(yields.let_go(1, 8, false) == 2 && yields.let_go(1, 8, false) == 1 && yields.let_go(1, 8, false) == NONE);
  // The number the page left at stays with its entry; another layout forgets every page.
  shelf.entries[1].synced = 42;
  assert(shelf.take(1, 8, false, fresh) == 1 && !fresh && shelf.entries[1].synced == 42);
  shelf.forget();
  assert(shelf.pages() == 0 && shelf.held(1) == NONE);
  return 0;
}
