#pragma once
// The weather card (firmware 0.2.80): where its blocks go. Pure arithmetic, free of LVGL and ESPHome, so
// tests/test_weather_card.cpp checks every shape on a PC; runtime_tiles.h draws it.
//
// The card is two blocks: a white card with the weather now and a strip of the next hours, and a white card
// with one row per coming day. Until now they were simply stacked, which holds on glass as tall as the design
// and nowhere else: on 800 x 480 the standard look draws 28 % larger while the height stays 480, and the days
// card came out 51 px tall with five rows in it (2026-09-21).
//
// Three rules keep that from happening on any glass:
//
//  1. **Glass wide enough for two of them stands them beside each other** instead of under each other: the
//     height the stack lacks is width the board has (overlay_card::columns decides, the same rule as the
//     thermostat and the blind). Wide enough means a column that still holds the weather now with its icon,
//     its temperature and the condition beside them (Metrics::min_column) - half of 800 px at 217 dpi is not,
//     half of 1024 at 170 is. The days card then gets the whole height of the card.
//  2. **What is left over is given up in a fixed order**, and the order is the design decision: first the rain
//     under the hours (every day row says its rain again), then the "Coming days" heading (the card below it
//     says what it is), and only then the hour strip as a whole. The two blocks themselves never go: a weather
//     card without its days is not a weather card. These are states and not one concession after another: the
//     strip buys so much room that the heading comes back with it, and on the Waveshare that is what happens.
//  3. **The days that do not fit move to a next page**, with the tile pages' own pager across the foot of the glass
//     and the settings page, so nothing is ever drawn on top of something else. A row is never thinner than
//     three quarters of its own line: that is what the two first boards draw today (a CYD five rows of 11 px
//     with a 14 px line, a Guition five of 25), and keeping that number keeps their pixels.
//
// Nothing here asks LVGL for a size and nothing is laid out twice: the caller measures one string (the width
// of an hour's time) and everything else follows from the fonts' line heights, which the board's look decides.
#include <algorithm>

#include "ui_scale.h"

namespace weather_card {

struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
};

// What the board brings: its size class, the line heights of the fonts the card writes with, and the width of
// one hour's time ("12 PM", "14:00") as it is drawn, which decides how many hours the strip holds.
struct Metrics {
  bool large = true;
  int text_h = 22;   // the card's own font: a day's name, a temperature
  int small_h = 20;  // the muted lines: the hour, the condition, the rain
  int mini_h = 32;   // a condition icon on a row
  int tiny_h = 22;   // the rain drop
  int icon_h = 50;   // the big condition icon of "now"
  int big_h = 46;    // the temperature of "now"
  int hour_w = 46;   // what one column of the hour strip needs, measured by the caller
  int top = 84;      // where the content starts, under the card's top bar
  int pad = 20;      // overlay_card::pad(): the room the card keeps from the edge of the glass
  int band = 0;      // the pager every page shares across the foot of the glass (page_bar::height); 0 in the tests

  int card_pad() const { return ui::px(large ? 14 : 7); }    // inside a white card
  int gap() const { return ui::px(large ? 12 : 6); }         // between the two blocks
  int margin() const { return ui::px(large ? 10 : 4); }      // under the last block
  int hours_gap() const { return ui::px(large ? 14 : 8); }   // between "now" and the hour strip
  int row_pad() const { return ui::px(large ? 8 : 4); }      // above the first and under the last day row
  int row_lead() const { return ui::px(large ? 16 : 6); }    // the offsets between the hour strip's four lines
  int heading_h() const { return large ? text_h + ui::px(8) : 0; }  // "Coming days"; the compact look has none
  int pager_h() const { return band > 0 ? band : ui::px(large ? 34 : 20); }
  // The narrowest a column of two may be: what the weather now asks for, the icon and the temperature beside
  // each other with the condition and the line under it next to them. Glass narrower than two of these keeps
  // its stack; a column that cuts "Partly cloudy" in half is not a column.
  int min_column() const { return 2 * card_pad() + icon_h + ui::px(14 + 92 + 4 + 150); }
  // The room the "now" block needs: its hero, and the hour strip when there is one.
  int hero() const { return std::max(icon_h, big_h); }
  int hours_h(bool rain) const { return small_h + mini_h + text_h + (rain ? small_h : 0) + row_lead(); }
  int now_h(int hour_columns, bool rain) const {
    return 2 * card_pad() + hero() + (hour_columns ? hours_gap() + hours_h(rain) : 0);
  }
  // A day row is never thinner than the glyphs on it. Three quarters of the line height is what the two first
  // boards draw today, so this number is what keeps their five rows five rows.
  int min_row() const { return std::max(1, std::max(text_h, small_h) * 3 / 4); }
  int days_h(int rows) const { return 2 * row_pad() + rows * min_row(); }
};

struct Layout {
  int columns = 1;
  Rect now;             // the white card with the weather now
  Rect hours;           // the hour strip inside it, in the card's own coordinates; empty when it was given up
  int hour_columns = 0;
  bool hour_rain = true;
  Rect heading;         // "Coming days"; empty when it was given up
  Rect days;            // the white card with the day rows
  Rect pager;           // the chevrons and dots under it; empty while every day fits on one page
  int row_h = 0;        // a day row, as the card's room divides it
  int rows_y = 0;       // where the first row starts inside the days card
  int rows = 0;         // day rows on the page shown
  int pages = 1;
  // The columns of a day row, in the days card's own coordinates.
  int day_x = 0, day_w = 0, icon_x = 0, cond_x = 0, cond_w = 0, rain_x = 0, rain_w = 0, drop_w = 0;
  bool rain_mm = false;  // the millimetres behind the chance ("90 % · 6.5 mm"), where the row is wide enough
  int high_x = 0, high_w = 0, low_x = 0, low_w = 0;

  // The days on `page`, counted from 0: [first, first + rows).
  int first_day(int page) const { return std::min(std::max(page, 0), pages - 1) * rows; }
};

// How many hours the strip holds in a card `card_w` wide: as many as its width carries, six at most, and none
// at all below two, where a strip is no longer a strip.
inline int hour_columns(const Metrics &m, int card_w, int hours) {
  const int room = card_w - 2 * m.card_pad();
  const int fit = std::min(hours, room / std::max(1, m.hour_w));
  return fit >= 2 ? std::min(fit, 6) : 0;
}

// The height the card asks for when its two blocks stand under each other. The caller hands this to
// overlay_card::columns, which turns the stack into two columns when the glass is wide and short.
inline int stacked_height(const Metrics &m, int width, int hours, int days) {
  const int card_w = width - 2 * m.pad;
  return m.top + m.now_h(hour_columns(m, card_w, hours), true) + m.gap() + m.heading_h() +
         m.days_h(std::max(1, days)) + m.margin();
}

// Where every block goes on glass of `width` x `height`, for `hours` hours and `days` days, in `columns`
// columns (1 or 2, from overlay_card::columns).
inline Layout layout(const Metrics &m, int width, int height, int hours, int days, int columns = 1) {
  Layout l;
  l.columns = columns >= 2 ? 2 : 1;
  const int pad = m.pad, card_pad = m.card_pad();
  const int card_w = l.columns == 2 ? (width - 2 * pad - ui::column_gap()) / 2 : width - 2 * pad;
  const int full_hours = hour_columns(m, card_w, hours);
  const int wanted = std::max(1, days);

  // What the card may give up, best first. The order is the design decision: the rain under the hours goes
  // before the heading, because a day row says its rain again; the heading goes before the hour strip, because
  // a word costs less than a block; the strip goes last, because it is the only one that gives real room.
  //
  // These are *states*, not one concession after another, and that is the point: a card that has given up its
  // strip has room for the heading again, and taking the heading first and the strip after would leave it
  // without one for nothing. Every state is tried in turn and the first that holds every day wins; when none
  // does, the one that shows the most days does, and what is left over goes on a next page.
  struct State { bool strip, rain, heading; };
  static constexpr State STATES[] = {{true, true, true}, {true, true, false}, {true, false, false},
                                     {false, false, true}, {false, false, false}};
  auto days_top = [&](const State &s) {
    const int heading_h = s.heading ? m.heading_h() : 0;
    return l.columns == 2 ? m.top : m.top + m.now_h(s.strip ? full_hours : 0, s.rain) + m.gap() + heading_h;
  };
  auto room = [&](const State &s) { return std::max(0, height - m.margin() - days_top(s)); };
  // The days a state shows on one page, and the pager it needs for the rest. Reserving the pager's room only
  // when there is really a second page keeps a card that just fits on one (settings_screen::fitting_rows).
  // The honest count: zero when the room does not hold a row, so a state that shows nothing never wins.
  auto rows_of = [&](int space) { return std::min(wanted, std::max(0, (space - 2 * m.row_pad()) / m.min_row())); };
  auto shown = [&](const State &s) {
    const int avail = room(s);
    const int rows = rows_of(avail);
    return rows >= wanted ? rows : rows_of(std::max(0, avail - m.pager_h()));
  };

  State best = STATES[0];
  int best_rows = 0;
  for (const State &s : STATES) {
    const int rows = shown(s);
    if (rows > best_rows) { best = s; best_rows = rows; }
    if (best_rows >= wanted) break;
  }
  l.hour_columns = best.strip ? full_hours : 0;
  l.hour_rain = best.rain && l.hour_columns > 0;
  const int heading_h = best.heading ? m.heading_h() : 0;

  const int avail = room(best);
  l.rows = std::max(1, best_rows);
  l.pages = (wanted + l.rows - 1) / l.rows;
  const int space = l.pages > 1 ? std::max(0, avail - m.pager_h()) : avail;

  const int now_h = m.now_h(l.hour_columns, l.hour_rain);
  l.now = {pad, m.top, card_w, now_h};
  if (l.hour_columns)
    l.hours = {card_pad, card_pad + m.hero() + m.hours_gap(), card_w - 2 * card_pad, m.hours_h(l.hour_rain)};
  const int days_x = l.columns == 2 ? pad + card_w + ui::column_gap() : pad;
  if (heading_h) l.heading = {days_x + ui::px(4), days_top(best) - heading_h, card_w - 2 * ui::px(4), m.text_h};
  l.days = {days_x, days_top(best), card_w, space};
  // The pager every page shares stands across the foot of the glass (page_bar.h); the days end above it.
  if (l.pages > 1) l.pager = {days_x, height - m.pager_h(), card_w, m.pager_h()};
  l.rows_y = m.row_pad();
  l.row_h = std::max(m.min_row(), (l.days.h - 2 * m.row_pad()) / std::max(1, l.rows));

  // A day row: the day, its condition icon, the condition in words, the rain, and the high and low temperature
  // against the right edge. The words take whatever is left between the icon and the rain.
  l.day_w = ui::px(m.large ? 46 : 26);
  l.day_x = card_pad;
  l.icon_x = l.day_x + l.day_w;
  l.cond_x = l.icon_x + m.mini_h + ui::px(m.large ? 12 : 5);
  l.high_w = ui::px(m.large ? 52 : 30);
  l.low_w = ui::px(m.large ? 46 : 28);
  l.high_x = card_w - card_pad - l.high_w - l.low_w;
  l.low_x = l.high_x + l.high_w;
  l.drop_w = m.tiny_h + ui::px(m.large ? 4 : 2);
  l.rain_w = std::min(ui::px(m.large ? 120 : 60), std::max(0, l.high_x - l.cond_x - ui::px(m.large ? 40 : 20)));
  // A row too narrow for the drop and a number behind it says no rain at all: the words then take that room,
  // and the day still reads. A rain block half drawn would be the one thing worse than none.
  if (l.rain_w < l.drop_w + ui::px(m.large ? 30 : 16)) l.rain_w = 0;
  l.rain_x = l.high_x - (l.rain_w ? ui::px(m.large ? 14 : 6) + l.rain_w : 0);
  // The millimetres only where the whole line fits behind the drop; the compact look never had room.
  l.rain_mm = m.large && l.rain_w >= ui::px(100);
  l.cond_w = std::max(1, l.rain_x - l.cond_x - ui::px(4));
  return l;
}

}  // namespace weather_card
