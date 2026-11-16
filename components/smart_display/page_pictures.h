#pragma once
// Page pictures (docs/KEPT_PAGES.md, "Page pictures"). A screen whose frame buffer a task may write keeps, in PSRAM, a
// picture of the pages it has shown: the pixels of the page's own room as LVGL last drew them, taken from the glass
// while the page stood still. When the screen turns to such a page the picture goes on the glass at once, past LVGL,
// and LVGL then draws the page as it always did, underneath, which changes no pixel.
//
// This file is the rules, free of LVGL, ESP-IDF and the glass, so tests/test_page_pictures.cpp checks them on a PC:
//   Map     which blocks of a picture are true: equal to what LVGL would draw there now. A picture is true per block,
//           never as a whole: the part of a page whose value moved is left to LVGL, the rest is put
//   Stillness  when LVGL last drew each block: a block is taken only once it has stood still
//   settle  what a page that comes back lacks, from the change numbers the kept pages already keep (kept_pages.h)
//   Shelf   which pages hold a picture: the page on the glass and its nearest neighbours, the farthest lets go first
//   count   how many pictures a board keeps, from its PSRAM and the size of one picture, never from its name
// page_pictures_lvgl.h is the other half: taking a picture from the glass, putting one on it, and the hooks.
//
// The invariant every rule here serves: a true block holds exactly the pixels LVGL last drew there for this page.
//   on the glass   every area LVGL draws makes the blocks under it untrue (it sees what no change number sees: a title
//                  that scrolls, a spinner, a pressed tile), and a take makes them true again once the page rests
//   away           a card's blocks are untrue once its tile took a change number after the page left, and every block
//                  once everything was asked to be drawn again (the look, Home Assistant gone or back)
//   never          the room of another layout, grid, turn or panel: the map is shaped anew, with no block true
#include <array>
#include <cstddef>
#include <cstdint>

#include "glass.h"
#include "kept_pages.h"
#include "picture_store.h"
#include "page_protocol.h"

namespace page_pictures {

using glass::Rect;

// A block is this many pixels of the panel each way. LVGL's areas are rounded out to whole blocks, so a smaller block
// keeps more of a page true around a card that changed, and a larger one makes shorter work of each refresh: 64 gives a
// glass of 1280 x 800 a map of 20 x 13.
constexpr int BLOCK = 64;
constexpr int MAX_SIDE = 32;  // blocks each way: a panel of up to 2048 x 2048

inline Rect common(const Rect &a, const Rect &b) {
  const int x0 = a.x > b.x ? a.x : b.x, y0 = a.y > b.y ? a.y : b.y;
  const int x1 = a.x + a.w < b.x + b.w ? a.x + a.w : b.x + b.w, y1 = a.y + a.h < b.y + b.h ? a.y + a.h : b.y + b.h;
  return x1 > x0 && y1 > y0 ? Rect{x0, y0, x1 - x0, y1 - y0} : Rect{};
}

// The bits of one row of blocks, from column `from` up to `to` (not included).
constexpr uint32_t bits(int from, int to) {
  return to <= from ? 0 : ((to >= 32 ? 0u : (1u << to)) - 1u) & ~((1u << from) - 1u);
}

// Which blocks of a picture are true. Everything is in the panel's own pixels, as the frame buffer has them: a
// rectangle of the screen as LVGL lays it out goes through glass::on_panel first.
struct Map {
  int w = 0, h = 0, turn = 0;  // the panel, and how LVGL was turned on it
  Rect room;                   // the page's own room on the panel: only pixels inside it are ever taken or put
  int columns = 0, rows = 0;
  std::array<uint32_t, MAX_SIDE> in_room{};  // the blocks the room touches
  std::array<uint32_t, MAX_SIDE> good{};     // the blocks that are true

  bool shaped() const { return columns > 0; }
  // Whether the map is of this panel, this turn and this room.
  bool fits(int panel_w, int panel_h, int panel_turn, const Rect &panel_room) const {
    return shaped() && w == panel_w && h == panel_h && turn == panel_turn && room == panel_room;
  }
  // A map for a room on a panel, with no block true. False, and no map, for a panel larger than a map holds or a room
  // that is not on it.
  bool shape(int panel_w, int panel_h, int panel_turn, const Rect &panel_room) {
    *this = Map{};
    const Rect inside = common(panel_room, Rect{0, 0, panel_w, panel_h});
    if (panel_w <= 0 || panel_h <= 0 || panel_w > MAX_SIDE * BLOCK || panel_h > MAX_SIDE * BLOCK || inside.empty() ||
        !(inside == panel_room))
      return false;
    w = panel_w; h = panel_h; turn = panel_turn; room = panel_room;
    columns = (w + BLOCK - 1) / BLOCK; rows = (h + BLOCK - 1) / BLOCK;
    for (int row = room.y / BLOCK; row <= (room.y + room.h - 1) / BLOCK; ++row)
      in_room[row] = bits(room.x / BLOCK, (room.x + room.w - 1) / BLOCK + 1);
    return true;
  }
  // The blocks a rectangle touches, per row: `each(row, bits)`.
  template <typename Each> void blocks_of(const Rect &r, Each each) const {
    const Rect inside = common(r, Rect{0, 0, w, h});
    if (!shaped() || inside.empty()) return;
    const uint32_t across = bits(inside.x / BLOCK, (inside.x + inside.w - 1) / BLOCK + 1);
    for (int row = inside.y / BLOCK; row <= (inside.y + inside.h - 1) / BLOCK; ++row) each(row, across);
  }
  // LVGL drew here, or what lies here changed: every block the rectangle touches is true no more.
  void untrue(const Rect &r) {
    blocks_of(r, [&](int row, uint32_t across) { good[row] &= ~across; });
  }
  void untrue_all() { good.fill(0); }
  bool is_true(int column, int row) const {
    return column >= 0 && column < columns && row >= 0 && row < rows && (good[row] >> column & 1u);
  }
  // How many blocks are true, and how many the room has.
  unsigned true_blocks() const { return count(good); }
  unsigned room_blocks() const { return count(in_room); }
  bool whole() const { return shaped() && good == in_room; }
  // The blocks of a row a take still has to copy: in the room, not true, and not under `skip` (where a stream writes).
  uint32_t wanted(int row, uint32_t skip = 0) const { return row >= 0 && row < rows ? in_room[row] & ~good[row] & ~skip : 0; }
  // Those blocks were copied from the glass as LVGL drew them.
  void took(int row, uint32_t blocks) { if (row >= 0 && row < rows) good[row] |= blocks & in_room[row]; }

 private:
  static unsigned count(const std::array<uint32_t, MAX_SIDE> &rows_of) {
    unsigned n = 0;
    for (uint32_t row : rows_of) for (; row; row &= row - 1) ++n;
    return n;
  }
};

// The pixels of a row's blocks, as rectangles of the panel cut to the room: `each(Rect)` for every run of set bits. A
// block on the room's edge gives only its part inside the room, so nothing of the bars around a page is ever copied.
template <typename Each> inline void runs(const Map &map, int row, uint32_t blocks, Each each) {
  if (row < 0 || row >= map.rows) return;
  blocks &= map.in_room[row];
  for (int column = 0; column < map.columns;) {
    if (!(blocks >> column & 1u)) { ++column; continue; }
    int end = column;
    while (end < map.columns && (blocks >> end & 1u)) ++end;
    const Rect piece = common(Rect{column * BLOCK, row * BLOCK, (end - column) * BLOCK, BLOCK}, map.room);
    if (!piece.empty()) each(piece);
    column = end;
  }
}
// How many bytes of RGB565 those blocks are.
inline size_t bytes_of(const Map &map, int row, uint32_t blocks) {
  size_t bytes = 0;
  runs(map, row, blocks, [&](const Rect &r) { bytes += static_cast<size_t>(r.w) * r.h * 2; });
  return bytes;
}

// When LVGL last drew each block of the page on the glass. A block is taken only once it has stood still for a while:
// a card that draws every second (a playing track's bar, a title that scrolls) would be untrue again before anyone
// turned back to it, so copying it is work for nothing, and it is simply never in its page's picture.
struct Stillness {
  std::array<uint32_t, MAX_SIDE * MAX_SIDE> at{};  // ms; 0 for never
  void drawn(const Map &map, const Rect &r, uint32_t now) {
    map.blocks_of(r, [&](int row, uint32_t across) {
      for (int column = 0; column < MAX_SIDE; ++column)
        if (across >> column & 1u) at[static_cast<size_t>(row) * MAX_SIDE + column] = now ? now : 1;
    });
  }
  // The blocks of a row LVGL drew less than `ms` ago.
  uint32_t moving(int row, uint32_t now, uint32_t ms) const {
    uint32_t blocks = 0;
    if (row < 0 || row >= MAX_SIDE) return 0;
    for (int column = 0; column < MAX_SIDE; ++column) {
      const uint32_t drew = at[static_cast<size_t>(row) * MAX_SIDE + column];
      if (drew && now - drew < ms) blocks |= 1u << column;
    }
    return blocks;
  }
};

// A card of the page: the tile it shows and where it lies on the panel (with whatever it draws around itself).
struct Card {
  uint32_t tile = 0;
  Rect at;
};
// What a page lacks whose blocks were true up to change number `synced` (kept_pages::Changes): everything when
// everything was asked for since, else the cards whose tile took a later number. The same rule the kept pages draw a
// card again by, so a picture is put exactly where no card is drawn again. Returns whether anything is left true.
inline bool settle(Map &map, const Card *cards, size_t count, const kept_pages::Changes &changes, uint32_t synced) {
  if (changes.all_after(synced)) map.untrue_all();
  else
    for (size_t i = 0; i < count; ++i)
      if (changes.tile_after(cards[i].tile, synced)) map.untrue(cards[i].at);
  return map.true_blocks() > 0;
}

// ---- How many, and which pages ----
constexpr size_t MAX_KEPT = page_protocol::MAX_PAGES;
constexpr size_t NONE = MAX_KEPT;
// The most PSRAM page pictures may ever hold: half of the heap (14.6 MB of the 29.3 MB a P4 board's 32 MB chip gives).
// The other half is always there for the kept pages' cards, LVGL's objects, the picture store and the streams. Within
// it a layout has a picture for every page, as it has the cards of every page (kept_pages.h).
// Written where the board's picture budget is (picture_store.h), with the store's own.
constexpr size_t share(size_t psram_total) { return picture_store::page_pictures_ceiling(psram_total); }
// What must stay free after a picture's memory is taken: the picture store's whole budget and the room the kept pages
// leave for a full camera and an alert, each asked where it is written (picture_store.h, kept_pages.h).
constexpr size_t reserve(size_t psram_total) { return picture_store::budget_for(psram_total) + kept_pages::KEEP_RESERVE; }
// How many pictures of `bytes` each a board with that PSRAM keeps for a layout of `pages`: none when not even two fit
// (one picture alone is never turned to: it is of the page on the glass).
constexpr size_t count(size_t psram_total, size_t bytes, unsigned pages) {
  if (!bytes || pages < 2) return 0;
  size_t n = share(psram_total) / bytes;
  if (n > pages) n = pages;
  if (n > MAX_KEPT) n = MAX_KEPT;
  return n >= 2 ? n : 0;
}
// Whether another picture's memory may be taken now.
constexpr bool affords(size_t psram_free, size_t psram_total, size_t bytes) {
  return psram_free >= bytes && psram_free - bytes >= reserve(psram_total);
}
// Page pictures are the first thing a screen gives up when its PSRAM runs short: a cover, a camera's full view, a live
// stream, a call and a plugin's picture all matter more. One picture goes, the farthest from the glass first
// (Shelf::let_go):
//   for a refusal   an allocation from PSRAM was refused since the last look (the heap watch counts every one and
//                   keeps the last one's size, heap_watch.h), and letting go could have helped it: it asked for no more
//                   than what is free and what the pictures hold together. One refusal costs one picture; whoever asked
//                   asks again, and a second refusal costs the next. An ask no picture could help (40 MB on a board
//                   with 20 free and 4 held) costs none.
//   under the floor less PSRAM is free than the kept pages' reserve: one picture each look, until it is not.
// After that no picture takes memory again for YIELD_REST_MS, so what was refused has its turn first.
constexpr uint32_t YIELD_REST_MS = 30000;
struct Yield {
  uint32_t seen = 0;  // the refusals answered so far
  // Whether one picture goes now. `refused` and `refused_bytes` are the heap watch's count and its last size, `held`
  // the bytes the page pictures hold.
  bool due(uint32_t refused, size_t refused_bytes, size_t psram_free, size_t held) {
    const bool fresh = refused != seen;
    seen = refused;  // answered, whatever the answer: the same refusal never costs a second picture
    return (fresh && held > 0 && refused_bytes <= psram_free + held) || psram_free < kept_pages::KEEP_RESERVE;
  }
};
// How far two pages lie apart, as someone pages from one to the other: around the end too when the pages loop.
constexpr int apart(int a, int b, int pages, bool loop) {
  const int d = a > b ? a - b : b - a;
  return loop && pages > 0 && pages - d < d ? pages - d : d;
}

struct Shelf {
  struct Entry {
    int page = -1;        // the page this picture is of; -1 for none
    uint32_t synced = 0;  // the change number the page's cards were drawn up to when it left the glass
    uint32_t used = 0;    // when it was last on the glass
  };
  std::array<Entry, MAX_KEPT> entries{};
  size_t capacity = 0;  // pictures kept: 0 on a board without the room
  uint32_t turns = 0;

  size_t held(int page) const {
    for (size_t i = 0; i < capacity && i < MAX_KEPT; ++i)
      if (page >= 0 && entries[i].page == page) return i;
    return NONE;
  }
  // The entry for the page on the glass: its own, a free one, or the one of the page farthest from it (of two as far,
  // the one on the glass longest ago), which lets its picture go. NONE without room. `fresh` says the entry holds
  // nothing of this page yet.
  size_t take(int page, int pages, bool loop, bool &fresh) {
    fresh = false;
    if (!capacity || page < 0) return NONE;
    size_t at = held(page);
    if (at == NONE) {
      fresh = true;
      const size_t room = capacity < MAX_KEPT ? capacity : MAX_KEPT;
      for (size_t i = 0; i < room && at == NONE; ++i) if (entries[i].page < 0) at = i;
      if (at == NONE) {
        at = 0;
        for (size_t i = 1; i < room; ++i) {
          const int far = apart(entries[i].page, page, pages, loop), farthest = apart(entries[at].page, page, pages, loop);
          if (far > farthest || (far == farthest && entries[i].used < entries[at].used)) at = i;
        }
      }
      entries[at] = Entry{};
      entries[at].page = page;
    }
    entries[at].used = ++turns;
    return at;
  }
  // The entry whose picture goes when memory is short: of the page farthest from the one on the glass (of two as far,
  // the one on the glass longest ago), the glass's own last. NONE when no page holds one. Its entry is free after.
  size_t let_go(int glass, int pages, bool loop) {
    size_t at = NONE;
    for (size_t i = 0; i < capacity && i < MAX_KEPT; ++i) {
      if (entries[i].page < 0) continue;
      if (at == NONE) { at = i; continue; }
      const int far = apart(entries[i].page, glass, pages, loop), farthest = apart(entries[at].page, glass, pages, loop);
      if (far > farthest || (far == farthest && entries[i].used < entries[at].used)) at = i;
    }
    if (at != NONE) entries[at] = Entry{};
    return at;
  }
  // Another layout or grid: no picture is of a page any more. Entries past a smaller capacity go too.
  void forget(size_t from = 0) { for (size_t i = from; i < MAX_KEPT; ++i) entries[i] = Entry{}; }
  size_t pages() const {
    size_t n = 0;
    for (size_t i = 0; i < capacity && i < MAX_KEPT; ++i) n += entries[i].page >= 0;
    return n;
  }
};

}  // namespace page_pictures
