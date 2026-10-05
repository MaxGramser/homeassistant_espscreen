#pragma once
// What the tiles of a layout cost in the memory inside the chip, and how much of it this screen has for them
// (firmware 0.34.0+). The screen says both in its hello reply, so the app and the editor can tell before saving whether a
// layout fits, and show how full the screen is, instead of finding out from a screen that restarts (docs/TILE_MEMORY.md).
//
// Why the memory inside the chip: everything else has room. A board with PSRAM keeps the tile list, the cards and the
// pictures there (megabytes free on every bench board); what grows with every tile and stays inside is the text of its
// state and what only some tiles carry (a forecast, a player's sources, a thermostat's modes). A board without PSRAM
// keeps all of it inside.
//
// Pure arithmetic, free of LVGL and ESPHome, so tests/test_tile_memory.cpp checks it on a PC.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include "tile_catalogue.h"

namespace tile_memory {
// What a tile costs here comes from the tile catalogue (catalogue/<type>.yaml `memory`, generated into tile_catalogue.h),
// the one place every type states it, so a new type cannot leave the budget guessing: what one tile of the type keeps in
// the memory inside the chip, measured on a board with PSRAM, where the tile itself and its block of extras live in PSRAM.
// A board without PSRAM keeps those inside the chip too, so it pays their size on top, which only the firmware knows
// (sizeof(Tile), sizeof(Extra)): the screen says it in its hello, and the add-on and the editor count with the same rule
// (core.tile_cost, web/src/model/memory.ts; tests/fixtures/memory-conformance.json holds the cases all three answer).
struct Board {
  bool psram = true;
  uint32_t tile_bytes = 0, extra_bytes = 0, page_bytes = 0;
};
inline std::string domain_of(const std::string &entity) { return entity.substr(0, entity.find('.')); }
// The catalogue's entry for a tile's entity or type: a screen card with a price of its own (the energy card), else its
// type's; a type it does not know (none should reach a screen) costs as the dearest.
inline const tile_catalogue::Memory &entry(const std::string &what) {
  for (const auto &m : tile_catalogue::CARDS)
    if (what == m.domain) return m;
  const std::string domain = domain_of(what);
  const tile_catalogue::Memory *dearest = &tile_catalogue::MEMORY[0];
  for (const auto &m : tile_catalogue::MEMORY) {
    if (domain == m.domain) return m;
    if (m.bytes > dearest->bytes) dearest = &m;
  }
  return *dearest;
}
// What one tile costs inside the chip: its type's bytes, what its own choices add (a tap that runs its own action, a
// second line set to one of its values), and on a board without PSRAM the tile itself and, where it keeps one, its block
// of extras.
inline uint32_t cost(const std::string &what, bool action, bool line, const Board &board) {
  const auto &m = entry(what);
  uint32_t bytes = m.bytes + (action ? tile_catalogue::ACTION_BYTES : 0) + (line ? tile_catalogue::LINE_BYTES : 0);
  if (!board.psram) bytes += board.tile_bytes + ((m.extras || action || line) ? board.extra_bytes : 0);
  return bytes;
}
// What one page costs: what it keeps (its title), what each item of its top bar that shows an entity keeps (its text),
// and on a board without PSRAM the page's own record (sizeof(page_protocol::Page)), which holds its bar.
inline uint32_t page_cost(unsigned entity_items, const Board &board) {
  return tile_catalogue::PAGE_BYTES + entity_items * tile_catalogue::BAR_TEXT_BYTES + (board.psram ? 0 : board.page_bytes);
}
// A tile's own choices as the cost counts them: the tap option "action", and a second line "attr:<name>".
inline bool own_action(const std::string &tap) { return tap == "action"; }
inline bool own_line(const std::string &subtitle) { return subtitle.compare(0, 5, "attr:") == 0; }

// Memory the tiles may never take: a layout switch dips about 20 KB below where it settles, a picture that loads takes
// another 20 to 25 KB for a moment, and the Wi-Fi link and the API need room to breathe. Below it, the screen stopped
// answering on the bench before it restarted, which is worse than a restart.
inline constexpr size_t RESERVE = 40 * 1024;
// Below this much free inside the chip a state still sets a tile's state, but no tile gets a new block of extras
// (Tile::set_extra): tiles turn plainer instead of the screen restarting, and the app is told (`short`).
inline constexpr size_t LOW_WATER = 16 * 1024;

// The room for tiles: what is free now plus what the tiles on the screen already take, less the reserve. Measured with
// the layout in place, so whatever else the screen holds (its fonts, the draw buffer, the panel, the pictures) is out of
// it already, on every board alike.
inline size_t room(size_t free_now, size_t layout_cost) {
  const size_t total = free_now + layout_cost;
  return total > RESERVE ? total - RESERVE : 0;
}

// The room reported is the smallest of the last few samples, one a minute: the free heap moves with every picture and
// state, and the editor should show one steady number that errs on the safe side.
struct Window {
  static constexpr unsigned SIZE = 5;
  size_t samples[SIZE]{};
  unsigned count = 0, next = 0;
  void add(size_t value) {
    samples[next] = value;
    next = (next + 1) % SIZE;
    if (count < SIZE) ++count;
  }
  size_t least() const {
    if (!count) return 0;
    size_t least = samples[0];
    for (unsigned i = 1; i < count; ++i) least = std::min(least, samples[i]);
    return least;
  }
  void clear() { count = next = 0; }
};
}  // namespace tile_memory
