#pragma once
#include <array>
#include <bitset>
#include <cstdint>
#include <string>
#include <vector>
#include "header_bar.h"
#include "layout_memory.h"

// The page configuration and transport guard contain no LVGL or HA dependencies.
// A page has one bar. There is no inherited/global bar and no legacy decoder.
namespace page_protocol {
constexpr unsigned VERSION = 2;
// The most pages and tiles one screen holds (firmware 0.34.0+). A board states its own as the build flags
// SCREEN_MAX_PAGES and SCREEN_MAX_TILES (packages/core.yaml, its board file); a build without them, the host tests
// included, keeps the eight pages and 64 tiles every screen had before. Every table with one entry per tile or per
// page is sized from these two, so nothing else in the firmware says 64 or 8.
#ifndef SCREEN_MAX_PAGES
#define SCREEN_MAX_PAGES 8
#endif
#ifndef SCREEN_MAX_TILES
#define SCREEN_MAX_TILES 64
#endif
constexpr unsigned MAX_PAGES = SCREEN_MAX_PAGES;
constexpr unsigned MAX_TILES = SCREEN_MAX_TILES;
// Eight pages and 64 tiles are what the app may always send (older apps know nothing else); a page is one bit of a
// 32-bit set below and a page number at most two digits (screen.page_<n>).
static_assert(MAX_PAGES >= 8 && MAX_PAGES <= 32, "a screen holds 8 to 32 pages");
static_assert(MAX_TILES >= 64 && MAX_TILES <= 1024, "a screen holds 64 to 1024 tiles");
// One bit per tile of the screen.
using TileSet = std::bitset<MAX_TILES>;
struct TileSize {
  const char *name;
  uint8_t minimum_columns, minimum_rows;
  constexpr bool fits(unsigned columns, unsigned rows) const {
    return columns >= minimum_columns && rows >= minimum_rows;
  }
};
// Wide retains its historical one-column presentation on portrait grids.
// Square requires two actual columns. Advertisement and input use this table.
inline constexpr std::array<TileSize, 5> TILE_SIZES{{
    {"single", 1, 1}, {"wide", 1, 1}, {"full", 1, 1}, {"tall", 1, 2}, {"square", 2, 2}}};
// A span (firmware 0.19.0): "CxR", a tile of C columns and R rows, set with the tile's handles in the editor. The five
// names keep the sizes they always were; a span is every other rectangle smaller than the grid (the whole grid is
// "full"), so 3 x 2 on a grid of three columns and 2 x 3 on one of four rows.
inline bool span_of(const std::string &name, unsigned &columns, unsigned &rows) {
  if (name.size() != 3 || name[1] != 'x' || name[0] < '1' || name[0] > '9' || name[2] < '1' || name[2] > '9') return false;
  columns = static_cast<unsigned>(name[0] - '0');
  rows = static_cast<unsigned>(name[2] - '0');
  return true;
}
inline bool span_offered(unsigned columns, unsigned rows, unsigned grid_columns, unsigned grid_rows) {
  if (columns > grid_columns || rows > grid_rows || (columns == grid_columns && rows == grid_rows)) return false;
  return columns > 2 || rows > 2;  // Up to 2 x 2 the names say it.
}
inline bool accepts_size(const std::string &name, unsigned columns, unsigned rows) {
  unsigned span_columns = 0, span_rows = 0;
  if (span_of(name, span_columns, span_rows)) return span_offered(span_columns, span_rows, columns, rows);
  if (name.empty()) return TILE_SIZES[0].fits(columns, rows);  // Default is single.
  for (const auto &size : TILE_SIZES)
    if (name == size.name && size.fits(columns, rows)) return true;
  return false;
}

inline bool key(const std::string &text, uint64_t &out) {
  if (text.size() != 16) return false;
  uint64_t value = 0;
  for (char c : text) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    value = (value << 4) | static_cast<unsigned>(c <= '9' ? c - '0' : c - 'a' + 10);
  }
  out = value;
  return true;
}

struct Page {
  uint64_t id = 0;
  // Empty means the explicitly selected screen-title source. Custom titles are nonempty.
  std::string title;
  header_bar::Bar bar;
  bool home_control = false;
  bool excluded = false;
  // Whether the Dock shows it (module dock, docs/MODULES.md): `"dock": false` in its page message hides it, and a
  // message without the key, from an app before it, shows it.
  bool dock = true;
  // Its own icon, an MDI codepoint (tile_icon::codepoint), which the Dock shows instead of the page's picture; 0 for none.
  uint32_t icon = 0;
};

struct Pages {
  layout_memory::Vector<Page> records;
  uint8_t home = 0;

  int index_of(uint64_t id) const {
    for (size_t i = 0; i < records.size(); ++i) if (records[i].id == id) return static_cast<int>(i);
    return -1;
  }
  bool included(int index) const {
    return index >= 0 && static_cast<size_t>(index) < records.size() && !records[index].excluded;
  }
  unsigned count() const {
    unsigned result = 0;
    for (const auto &page : records) if (!page.excluded) ++result;
    return result;
  }
  int ordinal(int index) const {
    if (!included(index)) return -1;
    int result = -1;
    for (int i = 0; i <= index; ++i) if (included(i)) ++result;
    return result;
  }
  int step(int index, int direction) const {
    if (!included(index) || (direction != -1 && direction != 1)) return index;
    for (int i = index + direction; i >= 0 && static_cast<size_t>(i) < records.size(); i += direction)
      if (included(i)) return i;
    return index;
  }
  int restore(uint64_t previous, bool had_previous) const {
    const int found = had_previous ? index_of(previous) : -1;
    return found >= 0 ? found : home;
  }
  bool footer(bool page_buttons) const {
    // Reserve the same room on every page. When hidden, detail pages offer
    // Back through the leading top-bar control instead.
    return records.size() > 1 && page_buttons;
  }
  bool detail(int index) const {
    return index >= 0 && static_cast<size_t>(index) < records.size() && records[index].excluded;
  }
};

// Only page IDs, never a second configuration or tile data. Home starts a new
// route; Back pops it. IDs survive reordering and deleted destinations are skipped.
struct NavigationHistory {
  std::array<uint64_t, MAX_PAGES> ids{};
  uint8_t size = 0;
  void clear() { size = 0; }
  void push(const Pages &pages, int from, int to) {
    if (from == to || from < 0 || static_cast<size_t>(from) >= pages.records.size()) return;
    if (size == ids.size()) {
      for (unsigned i = 1; i < size; ++i) ids[i - 1] = ids[i];
      --size;
    }
    ids[size++] = pages.records[from].id;
  }
  int target(const Pages &pages, int current) const {
    for (unsigned i = size; i > 0; --i) {
      const int found = pages.index_of(ids[i - 1]);
      if (found >= 0 && found != current) return found;
    }
    return pages.home;
  }
  int pop(const Pages &pages, int current) {
    while (size) {
      const int found = pages.index_of(ids[--size]);
      if (found >= 0 && found != current) return found;
    }
    return pages.home;
  }
};

enum class Packet : uint8_t { reject, duplicate, accept };
enum class Begin : uint8_t { reject, unchanged, replace };

// A fresh hello grants a device-generated lease. A delayed begin from a prior
// sender cannot take it over. One serialized sender and one monotonic sequence
// cover every indexed operation, avoiding per-tile sequence arrays on the board.
// The caller only advances the sequence after validating and applying a packet.
struct Transfer {
  uint64_t lease = 0, hello_id = 0, revision = 0;
  TileSet tiles;
  uint32_t sequence = 0, digest = 0;
  uint32_t pages = 0;
  uint16_t expected_pages = 0, expected_tiles = 0;
  bool granted = false, begun = false, active = false;

  uint64_t grant(uint64_t request, uint64_t random_token) {
    if (granted && request == hello_id) return lease;
    hello_id = request;
    lease = random_token;
    granted = true;
    begun = false;
    sequence = digest = 0;
    return lease;
  }
  Packet packet(uint64_t token, uint32_t next, uint32_t hash) const {
    if (!granted || token != lease || next == 0 || next < sequence) return Packet::reject;
    if (next == sequence) return hash == digest ? Packet::duplicate : Packet::reject;
    return Packet::accept;
  }
  void accepted(uint32_t next, uint32_t hash) { sequence = next; digest = hash; }
  Begin begin(uint64_t rev, unsigned page_count, unsigned tile_count) {
    if (!granted || page_count == 0 || page_count > MAX_PAGES || tile_count > MAX_TILES) return Begin::reject;
    // A session has only one begin. Repeating its exact packet is handled by packet().
    if (begun) return Begin::reject;
    begun = true;
    if (active && revision == rev && expected_pages == page_count && expected_tiles == tile_count)
      return Begin::unchanged;
    active = false;
    revision = rev;
    expected_pages = static_cast<uint16_t>(page_count);
    expected_tiles = static_cast<uint16_t>(tile_count);
    pages = 0;
    tiles.reset();
    return Begin::replace;
  }
  bool matches(uint64_t rev) const { return begun && revision == rev; }
  bool page(unsigned index) {
    if (!begun || active || index >= expected_pages || (pages & (uint32_t{1} << index))) return false;
    pages |= uint32_t{1} << index;
    return true;
  }
  bool tile(unsigned index) {
    if (!begun || active || index >= expected_tiles || tiles.test(index)) return false;
    tiles.set(index);
    return true;
  }
  // Every page and every tile of the session arrived once (tile() and page() take only indexes below the expected).
  bool complete() const {
    const uint32_t pages_wanted = expected_pages >= 32 ? UINT32_MAX : (uint32_t{1} << expected_pages) - 1;
    return begun && expected_pages && pages == pages_wanted && tiles.count() == expected_tiles;
  }
  bool received_page(unsigned index) const { return index < 32 && (pages & (uint32_t{1} << index)); }
  bool commit() {
    if (!complete()) return false;
    active = true;
    return true;
  }
};
}  // namespace page_protocol
