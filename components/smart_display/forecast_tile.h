#pragma once
// The weather tile's forecast (firmware 0.3.3): where its parts go. Pure arithmetic, free of LVGL and ESPHome, so
// tests/test_forecast_tile.cpp checks every shape on a PC; runtime_tiles.h measures the text and draws it.
//
// The tile says the weather now (the condition in its circle, the temperature, the word) and the coming days. It
// takes one of three forms, whichever the cell it got holds:
//
//  - **side**: the weather now at the left, a column per day beside it. A double-width card of one row.
//  - **rows**: the weather now on top and one row per day under it, the day's range drawn as a bar on one scale
//    for the whole week, so a cold day stands left of a warm one. A cell tall enough for four rows or all of them.
//  - **stacked**: the weather now on top and the day columns under it, for a tall cell with no room for rows (a CYD).
//
// A day column holds its name, its icon, the high and the low, and the chance of rain where one of the shown days
// has one worth saying. What a short cell gives up comes in a fixed order: first the rain, then the name on a line
// of its own (it moves beside the icon), then the name. Today's column stands on a pale pill, and that pill keeps
// its padding on every side: every column is as wide as the pill around the widest text, so the row holds one day
// fewer rather than a pill that touches its digits. A cell too short for the pill's padding, or too narrow for two
// columns with it, draws no pill. Nothing here asks LVGL for a size; the caller measures the strings (Metrics) once a render.
#include <algorithm>
#include <array>

#include "ui_scale.h"

namespace forecast_tile {

struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
};

enum class Form : unsigned char { side, stacked, rows };

constexpr int FACES = 3;
constexpr int DAYS = 5;

// What the board brings and what the caller measured.
struct Metrics {
  bool large = true;
  // The temperature now in the faces a board carries for it, largest first (the setpoint's digits, the watch value,
  // the headline): their line heights and how wide the temperature is in each. A width of 0 means the face lacks a
  // glyph of it and is never taken.
  std::array<int, FACES> face_h{75, 45, 32};
  std::array<int, FACES> face_w{0, 0, 0};
  int text_h = 19;      // the value font: the condition, a day's name on a column, the low, the rain
  int bold_h = 21;      // the title font: the high, a day's name on a row
  int icon_h = 30;      // the mini icon font's line: a day's condition
  int circle = 54;      // the board's icon circle (TILE_ICON_SIZE)
  int cond_w = 0;       // the condition, value font
  int line_w = 0;       // the longer line under the temperature on a tall cell ("Rainy · Feels like 17°")
  int temps_w = 0;      // the widest "21° 11°" of the days: the high, a thin space and the low
  int name_w = 0;       // the widest day name, value font
  int row_name_w = 0;   // the widest day name, title font
  int rain_w = 0;       // the widest chance of rain ("95%"), value font
  int low_w = 0;        // the widest low, value font
  int high_w = 0;       // the widest high, title font
  bool rain = false;    // one of the shown days has a chance of rain worth saying (30 % or more)

  int gap() const { return ui::px(large ? 8 : 4); }
  int text_gap() const { return ui::px(large ? 12 : 6); }       // between the circle and the temperature
  int pad_x() const { return ui::px(large ? 6 : 3); }          // today's pill around its text, left and right
  int pad_y() const { return ui::px(large ? 6 : 3); }           // above and under
  int column_air() const { return 1; }      // between two columns' pills
  int inline_gap() const { return ui::px(large ? 4 : 2); }      // a name beside its icon
  int row_h() const { return std::max(bold_h, icon_h) + ui::px(large ? 4 : 2); }
  int min_bar() const { return ui::px(large ? 40 : 24); }
  int bar_h() const { return ui::px(large ? 7 : 4); }
};

struct Column {
  Rect name, icon, temps, rain;  // name or rain empty when given up; the name beside the icon on a short cell
};
struct Row {
  Rect name, icon, rain, low, bar, high;  // rain empty where the row is too narrow for it
};

struct Layout {
  Form form = Form::side;
  int face = -1;             // the temperature's face (index into Metrics::face_h); -1: none fits
  Rect circle, temp, line;   // line: the condition, or on a tall cell the longer line; empty when given up
  bool long_line = false;    // the line is Metrics::line_w's, not only the condition
  int days = 0;              // columns or rows drawn
  std::array<Column, DAYS> columns{};
  Rect pill;                 // today's pill; empty when today is not among the columns
  std::array<Row, DAYS> rows{};
};

namespace detail {
// One way of stacking a day column, from the fullest to the barest.
struct Stack { bool name, name_inline, rain; };
constexpr Stack STACKS[] = {{true, false, true}, {true, false, false}, {true, true, true}, {true, true, false},
                            {false, false, false}};

inline int stack_h(const Metrics &m, const Stack &s) {
  return (s.name && !s.name_inline ? m.text_h : 0) + m.icon_h + m.bold_h + (s.rain ? m.text_h : 0);
}
inline int stack_w(const Metrics &m, const Stack &s) {
  const int icon_line = s.name && s.name_inline ? m.name_w + m.inline_gap() + m.icon_h : m.icon_h;
  return std::max({m.temps_w, icon_line, s.name && !s.name_inline ? m.name_w : 0, s.rain ? m.rain_w : 0});
}

// Day columns in `area`. A column is as wide as the widest of them plus the pill's padding, whether or not it
// stands on the pill, so every column has the same width and today's pill never touches its text.
inline void columns(const Metrics &m, Layout &l, Rect area, int days, int today) {
  l.days = 0;
  l.pill = {};
  if (area.w <= 0 || area.h <= 0 || days < 2) return;
  // Today's pill is the first thing a short cell gives up, before a single day: a cell with no room for the pill's
  // padding above and under the barest column draws that column without it.
  for (int attempt = 0; attempt < 2; ++attempt) {
  const bool pill = today >= 0 && attempt == 0;
  if (attempt && today < 0) return;
  for (Stack s : STACKS) {
    if (s.rain && !m.rain) continue;
    const int h = stack_h(m, s), content = stack_w(m, s);
    if (h + (pill ? 2 * m.pad_y() : 0) > area.h) continue;
    // A column is as wide as the pill around the widest text; without the pill, a little air on each side.
    const int need = content + (pill ? 2 * m.pad_x() : ui::px(m.large ? 6 : 3)) + m.column_air();
    const int n = std::min(days, area.w / std::max(1, need));
    if (n < 2) {
      if (pill) break;  // a narrow card gives up the pill before it gives up a day
      return;
    }
    const int col = area.w / n, top = area.y + (area.h - h) / 2;
    for (int k = 0; k < n; ++k) {
      Column &c = l.columns[k];
      const int x = area.x + k * col;
      int y = top;
      c = {};
      if (s.name && !s.name_inline) { c.name = {x, y, col, m.text_h}; y += m.text_h; }
      if (s.name && s.name_inline) {
        const int line = m.name_w + m.inline_gap() + m.icon_h, x0 = x + (col - line) / 2;
        c.name = {x0, y + (m.icon_h - m.text_h) / 2, m.name_w, m.text_h};
        c.icon = {x0 + m.name_w + m.inline_gap(), y, m.icon_h, m.icon_h};
      } else {
        c.icon = {x, y, col, m.icon_h};
      }
      y += m.icon_h;
      c.temps = {x, y, col, m.bold_h};
      y += m.bold_h;
      if (s.rain) c.rain = {x, y, col, m.text_h};
    }
    l.days = n;
    if (pill && today < n) {
      const int w = content + 2 * m.pad_x();
      l.pill = {area.x + today * col + (col - w) / 2, top - m.pad_y(), w, h + 2 * m.pad_y()};
    }
    return;
  }
  }
}

// The weather now in `area`: the circle at the left, the temperature and the line beside it, both centred on the
// area's height. The largest face that fits the height with its line under it, and whose temperature fits beside
// the circle, wins; the line is given up before a face is.
inline int now_block(const Metrics &m, Layout &l, Rect area, int circle, int max_text, bool long_line) {
  const int c = std::min(circle, area.h);
  const int text_x = area.x + c + m.text_gap();
  const int room = std::max(1, std::min(max_text, area.x + area.w - text_x));
  const int line_w = long_line && m.line_w <= room ? m.line_w : m.cond_w;
  // A word cut in half says less than no word: the condition is in the circle already.
  const bool line_fits = line_w <= room;
  int face = -1;
  bool line = false;
  for (int pass = 0; pass < 2 && face < 0; ++pass)
    for (int f = 0; f < FACES; ++f) {
      if (m.face_w[f] <= 0 || m.face_w[f] > room) continue;
      if (!pass && !line_fits) continue;
      if (m.face_h[f] + (pass ? 0 : m.text_h) > area.h) continue;
      face = f;
      line = pass == 0;
      break;
    }
  l.face = face;
  l.circle = {area.x, area.y + (area.h - c) / 2, c, c};
  if (face < 0) return c;
  const int block = m.face_h[face] + (line ? m.text_h : 0), y = area.y + (area.h - block) / 2;
  const int text_w = std::min(room, std::max(m.face_w[face], line ? line_w : 0));
  l.temp = {text_x, y, text_w, m.face_h[face]};
  l.line = line ? Rect{text_x, y + m.face_h[face], text_w, m.text_h} : Rect{};
  l.long_line = line && line_w == m.line_w && long_line && m.line_w != m.cond_w;
  return c + m.text_gap() + text_w;
}

inline int rows_fit(const Metrics &m, int room) { return std::max(0, room / std::max(1, m.row_h())); }
}  // namespace detail

// Where everything goes in a card's content area of `width` x `height`, for `days` coming days (Home Assistant
// sends five at most); `today` is the index of today among them, or -1. `tall`: the card spans more than one row (or
// the whole page); a card of one row keeps the side form however tall its cell is, so every double-width weather
// card on a page reads the same way.
inline Layout layout(const Metrics &m, int width, int height, int days, int today, bool tall) {
  Layout l;
  days = std::clamp(days, 0, DAYS);
  const int g = m.gap();
  // Rows, when the card holds the weather now in a face of its own and four rows (or every day) under it. The
  // largest face that still leaves all rows wins; otherwise the largest that leaves the least.
  const int least = std::min(days, 4);
  const int row_fixed = m.row_name_w + ui::px(m.large ? 10 : 5) + m.icon_h + ui::px(m.large ? 8 : 4) +
                        m.low_w + ui::px(m.large ? 10 : 5) + m.high_w + ui::px(m.large ? 8 : 4);
  if (tall && days >= 2 && width >= row_fixed + m.min_bar()) {
    int face = -1, count = 0;
    for (int f = 0; f < FACES; ++f) {
      if (m.face_w[f] <= 0) continue;
      const int n = std::min(days, detail::rows_fit(m, height - m.face_h[f] - m.text_h - 2 * g));
      if (n > count) { face = f; count = n; }
      if (n >= days) break;
    }
    if (face >= 0 && count >= least) {
      l.form = Form::rows;
      Metrics top = m;  // the head takes this face only: now_block picks the first that fits
      for (int f = 0; f < FACES; ++f) if (f != face) top.face_w[f] = 0;
      const int now_h = m.face_h[face] + m.text_h;
      const int circle = std::min(m.circle * 5 / 4, now_h);
      detail::now_block(top, l, {0, 0, width, now_h}, circle, width, true);
      l.face = face;
      const int first = now_h + 2 * g, pitch = (height - first) / count, content = std::max(m.bold_h, m.icon_h);
      const bool rain = m.rain && width >= row_fixed + m.rain_w + ui::px(m.large ? 10 : 5) + ui::px(m.large ? 90 : 50);
      for (int k = 0; k < count; ++k) {
        Row &r = l.rows[k];
        const int y = first + k * pitch + (pitch - content) / 2;
        int x = 0;
        r.name = {x, y + (content - m.bold_h) / 2, m.row_name_w, m.bold_h};
        x += m.row_name_w + ui::px(m.large ? 10 : 5);
        r.icon = {x, y + (content - m.icon_h) / 2, m.icon_h, m.icon_h};
        x += m.icon_h + ui::px(m.large ? 8 : 4);
        if (rain) {
          r.rain = {x, y + (content - m.text_h) / 2, m.rain_w, m.text_h};
          x += m.rain_w + ui::px(m.large ? 10 : 5);
        }
        r.low = {x, y + (content - m.text_h) / 2, m.low_w, m.text_h};
        x += m.low_w + ui::px(m.large ? 10 : 5);
        r.high = {width - m.high_w, y + (content - m.bold_h) / 2, m.high_w, m.bold_h};
        const int bar_w = r.high.x - ui::px(m.large ? 8 : 4) - x;
        r.bar = {x, y + (content - m.bar_h()) / 2, bar_w, m.bar_h()};
      }
      l.days = count;
      return l;
    }
  }
  // Stacked, on a tall cell without room for rows: the weather now on top, the columns under it. Only when the
  // columns keep at least their icon and temperatures there; otherwise the side form stands in the middle.
  for (int f = 0; f < FACES && tall && days >= 2; ++f) {
    if (m.face_w[f] <= 0) continue;
    const int now_h = m.face_h[f] + m.text_h;
    const Rect below{0, now_h + 2 * g, width, height - now_h - 2 * g};
    Layout trial;
    detail::columns(m, trial, below, days, today);
    if (trial.days < 2) continue;
    Metrics top = m;
    for (int k = 0; k < FACES; ++k) if (k != f) top.face_w[k] = 0;
    trial.form = Form::stacked;
    detail::now_block(top, trial, {0, 0, width, now_h}, std::min(m.circle * 5 / 4, now_h), width, true);
    return trial;
  }
  // Side: the weather now takes what it needs up to 30 % of the card, the days share the rest.
  l.form = Form::side;
  const int circle = std::min(m.circle, height);
  // The temperature in the largest face the height holds always has its width; the word under it only up to 30 %.
  int face_w = 0;
  for (int f = 0; f < FACES && !face_w; ++f)
    if (m.face_w[f] > 0 && m.face_h[f] + m.text_h <= height) face_w = m.face_w[f];
  for (int f = 0; f < FACES && !face_w; ++f)
    if (m.face_w[f] > 0 && m.face_h[f] <= height) face_w = m.face_w[f];
  const int cap = std::max(width * 30 / 100 - circle - m.text_gap(), face_w);
  const int used = detail::now_block(m, l, {0, 0, width, height}, circle, cap, false);
  const int x = used + g + ui::px(m.large ? 4 : 2);
  detail::columns(m, l, {x, 0, width - x, height}, days, today);
  return l;
}

}  // namespace forecast_tile
