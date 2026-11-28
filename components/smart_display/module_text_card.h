#pragma once
#ifdef SD_MOD_TEXT_CARD
// The template tile (module text_card, firmware 0.58.0, docs/TEXT_TILE.md): a text Home Assistant renders from a
// template, as rows the add-on made of it (screen_manager/app/text_tile.py). The screen parses no markdown and no
// Jinja: it gets headings, lines of text, bullets and table rows, each a few runs in a tone, and lays them out here.
//
// This file only plans, as calendar_card.h does for its card: which words stand where, in which face and ink, and
// where the room ends. module_text_card.cpp paints the plan in one LVGL object per card, so a tile full of text costs
// one object, not a label per row. Its texts are kept in PSRAM (roomy.h): on a P4 every plain allocation is internal
// RAM, which the network and the glass need. Pure, free of LVGL and ESPHome: tests/test_text_card.cpp checks it on a PC.
#include "calendar_card.h"
#include "roomy.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>

namespace text_card {

using calendar_card::Face;
using calendar_card::Measure;

// ---- What the add-on sends (x.md, wire version 1).
enum Kind : uint8_t { HEAD, TEXT, BULLET, ROW, HEAD_ROW };
enum Tone : uint8_t { PLAIN, BOLD, GOOD, ALERT, ACCENT, TONES };
struct Run { uint8_t tone = PLAIN; roomy::Text s; };
using Runs = roomy::List<Run>;
// One cell for a heading, a line or a bullet; one per column for a table row.
struct Row { uint8_t kind = TEXT; roomy::List<Runs> cells; };
struct Data {
  roomy::List<Row> rows;
  roomy::Text error;  // Home Assistant could not render the template: why, in its words
  bool failed = false;
};
// What one tile takes at most, whatever a message says (text_tile.py keeps to the same).
constexpr unsigned MAX_ROWS = 24, MAX_CELLS = 4, MAX_RUNS = 4;
// The bytes of text a screen keeps per tile, stated in its hello (hw::Caps text_bytes): a P4 has the room for more.
#if defined(USE_ESP32_VARIANT_ESP32P4)
constexpr unsigned MAX_BYTES = 3584;
#else
constexpr unsigned MAX_BYTES = 2048;
#endif
// Template tiles a screen subscribes to at once (hw::Caps text_tiles): each is a subscription in Home Assistant.
constexpr unsigned MAX_TILES = 8;

// An empty result draws nothing: the cells stay as empty as the page around them.
inline bool empty(const Data &d) { return !d.failed && d.rows.empty(); }

// ---- The plan, in the card's content coordinates.
enum Ink : uint8_t { INK, MUTED, GOOD_INK, ALERT_INK, ACCENT_INK, RULE, DOT };
enum Align : uint8_t { LEFT, RIGHT };
struct Piece { int x = 0, y = 0, w = 0; Face face = calendar_card::SMALL; uint8_t ink = MUTED; uint8_t align = LEFT; roomy::Text s; };
struct Mark { int x = 0, y = 0, w = 0, h = 0, radius = 0; uint8_t ink = RULE; uint8_t opa = 255; };
// A table's lines: the quiet ink, a third of it, so they show on a card and on the page alike, light and dark.
constexpr uint8_t RULE_OPA = 90;
struct Scene {
  roomy::List<Piece> pieces;
  roomy::List<Mark> marks;
  int height = 0;  // the room the plan took
  bool cut = false;  // more rows than fit: the last line ends in an ellipsis
  void clear() { pieces.clear(); marks.clear(); height = 0; cut = false; }
};

inline const char *ellipsis() { return "\xE2\x80\xA6"; }
inline int P(int big, int small) { return ui::px(ui::large() ? big : small); }
// Headings in the bold label face, the rest in the face a calendar's lines take (calendar_card.h, the compact look's
// small label is too small to read a text in).
inline Face head_face() { return calendar_card::title_face(); }
inline Face text_face() { return calendar_card::meta_face(); }
inline int row_gap() { return P(4, 2); }
inline int head_gap() { return P(8, 4); }
inline int bullet_indent() { return P(14, 9); }
inline int bullet_dot() { return std::max(3, P(5, 3)); }
inline int cell_gap() { return P(10, 6); }

inline uint8_t ink_of(uint8_t tone, uint8_t plain) {
  switch (tone) {
    case BOLD: return INK;
    case GOOD: return GOOD_INK;
    case ALERT: return ALERT_INK;
    case ACCENT: return ACCENT_INK;
    default: return plain;
  }
}
inline int width(const Measure &m, Face f, const roomy::Text &s) { return m.width(f, roomy::plain(s)); }
// `s` cut until it and an ellipsis fit `w`, whole UTF-8 characters at a time.
inline roomy::Text with_ellipsis(const Measure &m, Face f, roomy::Text s, int w) {
  while (!s.empty() && s.back() == ' ') s.pop_back();
  while (!s.empty() && width(m, f, s + ellipsis()) > w) {
    do s.pop_back(); while (!s.empty() && (static_cast<uint8_t>(s.back()) & 0xC0) == 0x80);
    if (!s.empty() && (static_cast<uint8_t>(s.back()) & 0x80)) s.pop_back();
    while (!s.empty() && s.back() == ' ') s.pop_back();
  }
  return s + ellipsis();
}
// A cell on one line: too long ends in an ellipsis.
inline roomy::Text one_line(const Measure &m, Face f, const roomy::Text &s, int w) {
  if (w <= 0) return {};
  return width(m, f, s) <= w ? s : with_ellipsis(m, f, s, w);
}

// The words of a row's runs, each with its tone, and whether a space stood before it.
struct Word { roomy::Text s; uint8_t tone = PLAIN; bool space = false; };
inline roomy::List<Word> words_of(const Runs &runs) {
  roomy::List<Word> out;
  bool space = false;
  for (const auto &run : runs) {
    roomy::Text cur;
    for (char c : run.s) {
      if (c == ' ' || c == '\t') {
        if (!cur.empty()) { out.push_back({cur, run.tone, space}); cur.clear(); space = false; }
        space = true;
      } else {
        cur += c;
      }
    }
    // A word that runs on into the next run ("**75** %" is "75", then " %"): no space between them.
    if (!cur.empty()) { out.push_back({cur, run.tone, space}); space = false; }
  }
  return out;
}

// The text of a table cell, its leading spaces gone, and the tone of its first part.
inline roomy::Text cell_text(const Runs &runs, uint8_t &tone) {
  roomy::Text s;
  tone = PLAIN;
  for (const auto &run : runs) { if (s.empty() && !run.s.empty()) tone = run.tone; s += run.s; }
  while (!s.empty() && s.front() == ' ') s.erase(0, 1);
  return s;
}

struct Planner {
  Scene &sc;
  const Measure &m;
  int w, h, y = 0;
  // The columns of the table being planned: the value columns as wide as their widest cell, the first takes the rest.
  int columns[MAX_CELLS]{};
  int column_count = 0;

  // Measures the table that starts at row `at` (its rows up to the next row of another kind).
  void measure_table(const roomy::List<Row> &rows, size_t at) {
    const Face f = text_face();
    int widest[MAX_CELLS]{}, n = 1;
    for (size_t i = at; i < rows.size() && (rows[i].kind == ROW || rows[i].kind == HEAD_ROW); ++i) {
      n = std::max<int>(n, rows[i].cells.size());
      for (size_t c = 1; c < rows[i].cells.size() && c < MAX_CELLS; ++c) {
        uint8_t tone;
        widest[c] = std::max(widest[c], width(m, f, cell_text(rows[i].cells[c], tone)));
      }
    }
    column_count = n;
    const int gaps = cell_gap() * (n - 1), room = w - gaps;
    int values = 0;
    for (int c = 1; c < n; ++c) values += widest[c];
    // The first column names the rows: it keeps a third of the room at least. Values that need more share what is left.
    const int first_min = n > 1 ? room / 3 : room;
    const int for_values = std::max(0, room - first_min);
    for (int c = 1; c < n; ++c)
      columns[c] = values <= for_values ? widest[c] : (values ? widest[c] * for_values / values : for_values / (n - 1));
    int used = 0;
    for (int c = 1; c < n; ++c) used += columns[c];
    columns[0] = room - used;
  }

  bool fits(int line) const { return y + line <= h; }
  // The last line ends in an ellipsis: what follows did not fit.
  void cut() {
    sc.cut = true;
    if (sc.pieces.empty()) return;
    Piece &p = sc.pieces.back();
    const int room = p.align == RIGHT ? p.w : w - p.x;
    p.s = with_ellipsis(m, p.face, p.s, room);
    p.w = std::min(room, width(m, p.face, p.s));
  }
  // Words flowed onto lines from x0, at most as many lines as the room has; false when the room ended first.
  bool flow(const Runs &runs, Face f, uint8_t plain, int x0) {
    const int line = m.line[f], space = std::max(1, m.width(f, " "));
    auto words = words_of(runs);
    if (words.empty()) words.push_back({{}, PLAIN, false});
    if (!fits(line)) return false;
    int x = x0;
    Piece *open = nullptr;
    bool first = true;
    for (auto &word : words) {
      int ww = width(m, f, word.s);
      const int gap = first || !word.space ? 0 : space;
      if (!first && x + gap + ww > w) {
        // A new line, if the room has one.
        y += line;
        if (!fits(line)) { y -= line; cut(); return false; }
        x = x0; open = nullptr;
      } else {
        x += gap;
      }
      if (ww > w - x0) { word.s = with_ellipsis(m, f, word.s, w - x0); ww = width(m, f, word.s); }
      const uint8_t ink = ink_of(word.tone, plain);
      if (open && open->ink == ink && open->y == y) {
        // The same ink goes on in the same piece: fewer pieces to paint.
        if (gap) open->s += ' ';
        open->s += word.s;
        open->w = x + ww - open->x;
      } else {
        sc.pieces.push_back({x, y, ww, f, ink, LEFT, word.s});
        open = &sc.pieces.back();
      }
      x += ww;
      first = false;
    }
    y += line;
    return true;
  }
  bool table_row(const Row &row) {
    const Face f = text_face();
    const int line = m.line[f];
    if (!fits(line)) { cut(); return false; }
    // The first column names the row; the others hold values, right-aligned as numbers are (measure_table).
    const int n = std::min<int>(row.cells.size(), column_count);
    int x = 0;
    for (int i = 0; i < n; ++i) {
      const int cw = columns[i];
      uint8_t tone;
      roomy::Text s = cell_text(row.cells[i], tone);
      if (!s.empty()) {
        const uint8_t ink = row.kind == HEAD_ROW ? MUTED : ink_of(tone, INK);
        s = one_line(m, f, s, cw);
        sc.pieces.push_back({x, y, cw, f, ink, static_cast<uint8_t>(i == 0 ? LEFT : RIGHT), s});
      }
      x += cw + cell_gap();
    }
    y += line;
    const int rule = std::max(1, ui::px(1));
    if (y + rule <= h) sc.marks.push_back({0, y + P(2, 1), w, rule, 0, RULE, RULE_OPA});
    y += P(4, 2) + rule;
    return true;
  }
};

// The plan of a card `w` x `h` (its content) for `d`.
inline void plan(Scene &sc, const Measure &m, int w, int h, const Data &d) {
  sc.clear();
  if (w <= 0 || h <= 0) return;
  Planner p{sc, m, w, h};
  if (d.failed) {
    Runs runs;
    runs.push_back({ALERT, d.error});
    p.flow(runs, text_face(), ALERT_INK, 0);
    sc.height = p.y;
    return;
  }
  uint8_t last = 255;
  for (size_t i = 0; i < d.rows.size(); ++i) {
    const auto &row = d.rows[i];
    if (row.cells.empty()) continue;
    const bool table = row.kind == ROW || row.kind == HEAD_ROW;
    const bool in_table = last == ROW || last == HEAD_ROW;
    if (last != 255 && !(table && in_table)) p.y += row.kind == HEAD ? head_gap() : row_gap();
    if (table && !in_table) p.measure_table(d.rows, i);
    bool more = true;
    if (table) {
      more = p.table_row(row);
    } else if (row.kind == HEAD) {
      more = p.flow(row.cells[0], head_face(), INK, 0);
    } else if (row.kind == BULLET) {
      const Face f = text_face();
      const int top = p.y;
      // Plain words in the quiet ink, as a line's, so a bold part stands out in a bullet too.
      more = p.flow(row.cells[0], f, MUTED, bullet_indent());
      if (top + m.line[f] <= h) {
        const int dot = bullet_dot();
        sc.marks.push_back({P(3, 2), top + (m.line[f] - dot) / 2, dot, dot, dot, DOT});
      }
    } else {
      more = p.flow(row.cells[0], text_face(), MUTED, 0);
    }
    if (!more) { if (!sc.cut) p.cut(); break; }
    last = row.kind;
  }
  sc.height = std::min(p.y, h);
}

}  // namespace text_card
#endif  // SD_MOD_TEXT_CARD
