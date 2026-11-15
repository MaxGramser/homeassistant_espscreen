#pragma once
// Sections on a page (docs/PAGES.md "Sections"): what a screen keeps of them and the room their titles take.
//
// A section is a block of cells on a page with a title, an icon and a soft panel behind its tiles. The add-on sends
// each page's blocks in the page's message; the tiles come as always, each at its own cell. What this file knows: a
// block's place, title, icon and summary, whether a page's blocks fit the grid without covering each other, and the
// room a section's title takes from its tiles. What it does not know: LVGL, fonts, colours (the module sections draws them).
//
// The page's rows stay what they are: a section's title and padding come out of its own cells (inside, below), so a
// loose tile beside it keeps its full height. Test: tests/test_section_layout.cpp.
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace section_layout {
// At most this many sections on a page (the add-on's core.STORE_MAX_SECTIONS), their titles at most this long.
constexpr size_t MAX = 16;
constexpr size_t TITLE_BYTES = 48;
constexpr size_t SUMMARY_BYTES = 48;
// The most columns and rows a grid has (runtime_model.h DIM_MAX).
constexpr unsigned DIM = 8;

struct Section {
  uint8_t column = 0, row = 0, columns = 1, rows = 1;
  uint32_t icon = 0;        // a Material Design Icons codepoint, 0 for none
  std::string title;
  std::string summary;      // an entity's state at the title's right end, as the add-on formats it; empty for none
  bool contrast = false;    // the panel in the page's opposite colour, its words in its ink (off unless chosen)
  bool follow = false;      // with contrast: the whole section in the other look, its tiles' cards too
};

// Every block inside a grid of `columns` x `rows`, none over another, at most MAX of them.
inline bool valid(const std::vector<Section> &sections, unsigned columns, unsigned rows) {
  if (sections.size() > MAX || columns > DIM || rows > DIM) return false;
  uint64_t taken = 0;
  for (const auto &s : sections) {
    if (s.columns < 1 || s.rows < 1 || s.column + s.columns > columns || s.row + s.rows > rows) return false;
    if (s.title.empty() || s.title.size() > TITLE_BYTES || s.summary.size() > SUMMARY_BYTES) return false;
    for (unsigned r = s.row; r < unsigned(s.row + s.rows); ++r)
      for (unsigned c = s.column; c < unsigned(s.column + s.columns); ++c) {
        const uint64_t bit = uint64_t(1) << (r * DIM + c);
        if (taken & bit) return false;
        taken |= bit;
      }
  }
  return true;
}

// The room a section's title and padding take, out of the section's own cells (the block model, 2026-11-15): the page's
// rows stay as they are, so no tile outside a section changes, and the panel's top and foot stay on the rows beside it.
// The header (the title's band and a gap) and the padding under the last row are shared evenly by the section's rows,
// so every tile inside is the same height. `header` = the title's top + its line + the grid's gap, `pad` = the grid's
// gap, `rows` the section's rows, `first` and `last` the rows of the tile inside the section (from 0). Rounded half away
// from zero in whole numbers, exactly as the editor (web/src/model/sections.ts insideMargins).
struct Inset { int top = 0, bottom = 0; };
inline int round_div(int n, int d) { return n >= 0 ? (2 * n + d) / (2 * d) : -((-2 * n + d) / (2 * d)); }
inline Inset inside(int header, int pad, int rows, int first, int last) {
  if (rows < 1) rows = 1;
  const int total = header + pad;
  return {round_div(header * rows - first * total, rows), round_div((last + 1) * total - header * rows, rows)};
}
}  // namespace section_layout
