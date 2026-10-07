#pragma once
// Pages kept whole (firmware 0.3.2+). A board with PSRAM keeps the cards of the pages it has shown, so turning back to
// one shows it again instead of building its cards anew: the switch hides one set of cards and shows another, and only
// the cards whose tile changed while the page was away are drawn again. A board without PSRAM (the CYD) keeps none and
// builds every page the way it always did; both go through the same show_page.
//
// What changed while a page was away is told by sequence numbers, not by flags handed around: every change a card could
// show (a tile's state, a minute on a tile that shows the time, everything at once) takes the next number when it is
// asked for, and every kept page
// remembers the number its cards were drawn up to (`synced`). A change is on a kept page's cards exactly when its
// number is at most `synced`, however late the drawing it asked for came.
//
// Pure bookkeeping, free of LVGL and ESPHome, so tests/test_kept_pages.cpp can check it on a PC. runtime_tiles.h owns
// the cards: one set on the glass (`widgets`) and one set per entry here, exchanged when a page is shown.
#include <array>
#include <cstddef>
#include <cstdint>
#include "page_protocol.h"

namespace kept_pages {
// Every page beside the one on the glass, up to the board's page ceiling (page_protocol.h MAX_PAGES): with some pages
// kept and others built when they come, paging through a long layout was quick on one page and slow on the next. The
// board's PSRAM decides how many it makes (runtime_tiles::kept_capacity stops at KEEP_RESERVE), and the pictures of a
// page out of sight make way when the picture store is full (picture_store::collect). The price is the first opening
// of a layout, which prepares every page (docs/KEPT_PAGES.md, "Prepared pages"). Until GitHub #183's round: seven.
constexpr size_t MAX_KEPT = page_protocol::MAX_PAGES - 1;
constexpr size_t NONE = MAX_KEPT;

// Where a page's cards come from when it goes on the glass.
struct Visit {
  size_t entry = NONE;   // the entry whose cards go on the glass and that takes the page leaving it; NONE: keep nothing
  bool kept = false;     // those cards already show the page, drawn up to change number `synced`
  bool build = false;    // the entry has no cards yet: make a set before the exchange
  uint32_t synced = 0;
};

// Changes numbered as they are asked for (see above).
struct Changes {
  uint32_t last = 0, all = 0;
  std::array<uint32_t, page_protocol::MAX_TILES> tile{};
  uint32_t mark_tile(size_t index) { return index < tile.size() ? tile[index] = ++last : mark_all(); }
  uint32_t mark_all() { return all = ++last; }
  // What a page drawn up to `synced` lacks.
  bool tile_after(size_t index, uint32_t synced) const { return index < tile.size() && tile[index] > synced; }
  bool all_after(uint32_t synced) const { return all > synced; }
};

struct Shelf {
  struct Entry {
    int page = -1;         // the page these cards show; -1 for cards that belong to no page (yet, or any more)
    bool built = false;    // the entry has a set of cards
    uint32_t synced = 0;   // the change number its cards are drawn up to
    uint32_t used = 0;     // when it was last shown, to choose which page gives its cards up
  };
  std::array<Entry, MAX_KEPT> entries{};
  size_t capacity = 0;     // pages kept beside the one on the glass: 0 on a board without room for them
  uint32_t turns = 0;

  // `page` goes on the glass and `leaving`, drawn up to `leaving_synced`, comes off it. The entry that holds `page`
  // hands its cards over, or else a free entry (one without cards), cards that belong to no page, or the page shown
  // longest ago; that entry then holds `leaving`.
  Visit visit(int page, int leaving, uint32_t leaving_synced) {
    Visit v;
    if (!capacity || page < 0 || leaving < 0 || page == leaving) return v;
    const size_t room = capacity < MAX_KEPT ? capacity : MAX_KEPT;
    size_t oldest = NONE, empty = NONE;
    for (size_t i = 0; i < room; ++i) {
      const auto &e = entries[i];
      if (e.built && e.page == page) { v.entry = i; break; }
      if (!e.built) { if (empty == NONE) empty = i; continue; }
      // Cards that belong to no page go first, then the page shown longest ago.
      const bool free = e.page < 0, free_oldest = oldest != NONE && entries[oldest].page < 0;
      if (oldest == NONE || (free && !free_oldest) || (free == free_oldest && e.used < entries[oldest].used)) oldest = i;
    }
    if (v.entry != NONE) {
      v.kept = true;
      v.synced = entries[v.entry].synced;
    } else if (empty != NONE) {
      v.entry = empty; v.build = true;
    } else {
      v.entry = oldest;
    }
    if (v.entry == NONE) return v;
    auto &e = entries[v.entry];
    e.page = leaving; e.built = true; e.synced = leaving_synced; e.used = ++turns;
    return v;
  }
  bool keeps(int page) const { return held(page) != NONE; }
  size_t held(int page) const {
    for (size_t i = 0; i < capacity && i < MAX_KEPT; ++i) if (entries[i].built && entries[i].page == page) return i;
    return NONE;
  }
  // How many entries hold a page.
  size_t pages() const {
    size_t n = 0;
    for (const auto &e : entries) n += e.built && e.page >= 0;
    return n;
  }
  // The layout or the grid changed: no kept page is what it was. The cards stay for the next pages to use.
  void forget() { for (auto &e : entries) e.page = -1; }
};
}  // namespace kept_pages
