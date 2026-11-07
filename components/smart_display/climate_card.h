#pragma once
// The climate card (firmware 0.2.80): where its parts go. Pure arithmetic, free of LVGL and ESPHome, so
// tests/test_climate_card.cpp checks every shape on a PC; runtime_tiles.h draws it.
//
// One card for every board, Home Assistant's thermostat dialog in this look: the state under the name, a white
// card with the setpoint between a round - and + key, a row with one key per mode the device supports, and a
// white card with a segmented row for everything else the entity can be set to (the fan, the swing). The power
// key sits in the top bar, across from the back key.
//
// The blocks are a stack, and the stack fits the glass by giving up room in a fixed order: first the spaces
// between the blocks, then the setpoint card down to its number, then the mode keys and the rows down to a
// finger's height, then the word under the setpoint, then the state line. A wide panel that stays too short
// even then - a 480 x 272, a wide seven-inch - puts the setpoint beside the modes and the rows instead of
// above them (two columns, overlay_card::columns). Nothing is ever dropped that a finger needs: a thermostat
// keeps its setpoint, its modes and its rows on every board.
#include <algorithm>
#include <cstdint>
#include "ui_scale.h"

namespace climate_card {
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  int cx() const { return x + w / 2; }
  int cy() const { return y + h / 2; }
  bool empty() const { return w <= 0 || h <= 0; }
};

// What the board brings: its size class, the line heights of the fonts the card writes with, and the width of
// the setpoint as it is drawn ("21.5°"), which decides how much room the - and + keys have left.
struct Metrics {
  bool large = true;
  int number_h = 64;    // the setpoint digits
  int number_w = 150;   // the widest the number gets ("-10.5°")
  int small_number_h = 40;  // the same number in the card heading's font, for glass that cannot hold both
  int small_number_w = 90;  // the digits big enough to read, or a thermostat with nowhere to put its rows
  int caption_h = 19;   // the word under the number
  int text_h = 25;      // the words on the fan and swing rows
  int status_h = 25;    // the state line under the name
  int side = 20;        // overlay_card::pad(): the room every card keeps from the edge of its area
  int icon_h = 28;      // the mode icons and the icon before a row
  int bar = 60;         // the top bar: the back key's size and where it sits
  int bar_x = 16, bar_y = 16;
  int touch = 48;       // ui::touch_min(): the smallest a finger may get

  int margin() const { return ui::px(large ? 18 : 8); }        // under the last block
  int gap() const { return ui::px(large ? 16 : 8); }           // between the blocks
  int pad() const { return ui::px(large ? 12 : 6); }           // inside the setpoint card, above and below
  int key_inset() const { return ui::px(large ? 18 : 10); }    // the - and + keys from the card's edge
  int key_max() const { return ui::px(large ? 116 : 72); }     // their diameter where there is room
  int setpoint_max() const { return ui::px(large ? 200 : 120); }
  int mode_h() const { return ui::px(large ? 72 : 44); }       // a mode key
  int mode_gap() const { return ui::px(large ? 10 : 6); }
  int edge() const { return ui::px(large ? 14 : 8); }          // inside the settings card
  int row_h() const { return ui::px(large ? 48 : 32); }        // a fan or swing row
  int row_gap() const { return ui::px(large ? 10 : 6); }
  int row_icon() const { return ui::px(large ? 40 : 26); }     // the icon before a row
  int radius() const { return ui::px(large ? 24 : 16); }       // the white cards' corner
  // The smallest a block a finger uses may get.
  int min_key() const { return std::max(touch, icon_h + ui::px(6)); }
  int min_row() const { return std::max(touch * 3 / 4, text_h + ui::px(8)); }
  // The setpoint card at its smallest: the number, and the word under it while it is kept.
  int min_setpoint(bool caption, bool small = false) const {
    return (small ? small_number_h : number_h) + (caption ? caption_h : 0) + 2 * pad();
  }
};

struct Layout {
  int columns = 1;
  Rect power;                  // in the top bar, across from the back key
  Rect status;                 // the state line; empty when the glass has no room for it
  Rect setpoint, minus, plus, number, caption;
  Rect modes;                  // the area the mode keys share
  Rect settings;               // the white card with the rows
  Rect rows[3], row_icons[3], row_tracks[3];
  int mode_count = 0;          // 0 when the device has one mode: the power key already does that
  int mode_gap = 0;
  int row_count = 0;
  // On glass with no room for a line of its own, the state moves under the number, where the word "Target"
  // stands on a bigger screen: one line instead of two, and the card still says what the thermostat is doing.
  bool caption_is_status = false;
  // Glass too short for everything draws the setpoint in the card heading's font instead of the big one: a
  // smaller number, but the modes and the rows keep their place.
  bool small_number = false;
  // A range (firmware 0.25.0): the setpoint card of a single target, and under its number the band with both ends
  // (`caption` is that band's row, the card's width minus the keys' inset): the -/+ move the end last chosen on it.
  bool range = false;
};

// How many mode keys fit a row `width` wide, each at least a finger.
inline int mode_keys_fit(const Metrics &m, int width, int wanted) {
  const int key = m.min_key(), gap = m.mode_gap();  // a mode key carries an icon, so a finger's width is enough
  if (wanted <= 0 || width <= 0) return 0;
  int fit = (width + gap) / (key + gap);
  return std::clamp(fit, 1, std::min(wanted, 7));
}

// The - and + keys take what the number leaves them, never less than a finger, never more than the look's key.
inline int key_size(const Metrics &m, int card_w, int card_h, bool small_number = false) {
  const int number = small_number ? m.small_number_w : m.number_w;
  const int beside = (card_w - number - 2 * m.key_inset()) / 2;
  return std::clamp(std::min(beside, card_h - 2 * m.pad()), m.touch, m.key_max());
}

// The narrowest column the setpoint card can stand in: the number between two finger-sized keys.
inline int min_column(const Metrics &m) { return m.number_w + 2 * m.touch + 2 * m.key_inset(); }

// The height the one-column form asks for once everything that can give has given.
inline int need_height(const Metrics &m, int modes, int rows) {
  const int keys = modes > 1 ? m.min_key() : 0;
  const int settings = rows > 0 ? 2 * ui::px(6) + rows * m.min_row() + (rows - 1) * m.row_gap() : 0;
  const int gaps = ((keys ? 1 : 0) + (settings ? 1 : 0)) * ui::px(6);
  return m.min_setpoint(false, true) + keys + settings + gaps;
}

// The card's parts in an area `width` wide, between `top` (under the top bar) and `bottom` (the glass, minus
// the margin). `modes` is how many hvac modes the device supports apart from off, `rows` how many setting rows
// it has (the fan, the swing). `columns` comes from overlay_card::columns().
inline Layout layout(const Metrics &m, int width, int top, int bottom, int modes, int rows, int columns = 1, bool range = false) {
  Layout l;
  l.range = range;
  l.columns = columns >= 2 ? 2 : 1;
  l.row_count = std::clamp(rows, 0, 3);
  l.mode_gap = m.mode_gap();
  l.power = {width - m.bar_x - m.bar, m.bar_y, m.bar, m.bar};

  int gap = m.gap(), mode_h = m.mode_h(), row_h = m.row_h(), edge = m.edge();
  int setpoint_h = m.setpoint_max();
  bool caption = true, status = true;

  const int inner = width - 2 * m.side;
  const int left_w = l.columns == 2 ? std::max(min_column(m), (inner - ui::column_gap()) / 2) : inner;
  const int right_w = l.columns == 2 ? inner - left_w - ui::column_gap() : inner;
  l.mode_count = modes > 1 ? mode_keys_fit(m, right_w, modes) : 0;

  auto number_height = [&] { return l.small_number ? m.small_number_h : m.number_h; };
  auto floor_setpoint = [&] { return m.min_setpoint(caption, l.small_number); };
  auto settings_h = [&] { return l.row_count ? 2 * edge + l.row_count * row_h + (l.row_count - 1) * m.row_gap() : 0; };
  // In one column the blocks stand under each other; in two the setpoint stands beside them.
  auto stack = [&] {
    const int below = (l.mode_count ? gap + mode_h : 0) + (l.row_count ? gap + settings_h() : 0);
    return l.columns == 2 ? std::max(setpoint_h, below - gap) : setpoint_h + below;
  };
  // Give room up in order: the spaces, the setpoint card, the keys and the rows, the state line (which moves
  // under the number), and last the word under it. Nothing a finger uses is ever given up.
  auto room_now = [&] { return bottom - top - (status ? m.status_h + gap / 2 : 0); };
  while (stack() > room_now()) {
    const int over = stack() - room_now();
    if (gap > ui::px(6)) { gap = std::max(ui::px(6), gap - over); continue; }
    if (setpoint_h > floor_setpoint()) { setpoint_h = std::max(floor_setpoint(), setpoint_h - over); continue; }
    if (mode_h > m.min_key()) { mode_h = std::max(m.min_key(), mode_h - over); continue; }
    if (row_h > m.min_row()) { row_h = std::max(m.min_row(), row_h - over); continue; }
    if (edge > ui::px(6)) { edge = std::max(ui::px(6), edge - over); continue; }
    if (status) { status = false; l.caption_is_status = caption && !l.range; continue; }
    // The number itself is the last thing to give: smaller digits, but every control keeps its place.
    if (!l.small_number && m.small_number_h < m.number_h) {
      l.small_number = true;
      setpoint_h = std::max(floor_setpoint(), setpoint_h - (m.number_h - m.small_number_h));
      continue;
    }
    if (caption && !l.range) { caption = false; l.caption_is_status = false; setpoint_h = std::max(floor_setpoint(), setpoint_h - over); continue; }
    break;  // the glass is smaller than a finger's worth of controls; the card keeps them anyway
  }
  // A concession frees whole pixels of a block, often more than was asked for. What is left over goes back,
  // so a card never stands with a band of empty glass above and below it: first the line that says what the
  // thermostat does, then the rows and keys, then the setpoint card itself.
  if (!caption && room_now() - stack() >= m.caption_h && setpoint_h + m.caption_h <= m.setpoint_max()) {  // NOLINT
    caption = true;
    l.caption_is_status = !status;
    setpoint_h += m.caption_h;
  }
  auto give = [&](int &value, int ceiling, int per_pixel) {
    const int spare = room_now() - stack();
    if (spare <= 0 || value >= ceiling || per_pixel <= 0) return;
    value += std::min(ceiling - value, spare / per_pixel);
  };
  give(row_h, m.row_h(), std::max(1, l.row_count));
  give(mode_h, m.mode_h(), 1);
  give(setpoint_h, m.setpoint_max(), 1);

  int y = top;
  if (status) {
    l.status = {m.side, y, inner, m.status_h};
    y += m.status_h + gap / 2;
  }
  const int left_x = m.side, right_x = l.columns == 2 ? left_x + left_w + ui::column_gap() : left_x;
  const int content_h = stack();
  const int spare = std::max(0, bottom - y - content_h);
  y += spare / 2;  // a card that leaves room stands in the middle of what is left

  l.setpoint = {left_x, y, left_w, setpoint_h};
  const int key = key_size(m, left_w, setpoint_h, l.small_number);
  l.minus = {left_x + m.key_inset(), y + (setpoint_h - key) / 2, key, key};
  l.plus = {left_x + left_w - m.key_inset() - key, l.minus.y, key, key};
  const int block = number_height() + (caption ? m.caption_h : 0);
  const int number_x = l.minus.right(), number_w = std::max(1, l.plus.x - number_x);
  l.number = {number_x, y + (setpoint_h - block) / 2, number_w, number_height()};
  if (caption) l.caption = {number_x, l.number.bottom(), number_w, m.caption_h};
  if (l.range) {
    // The band runs along the card's foot; the number and its keys share what is above it.
    const int foot = m.caption_h + m.pad();
    const int upper = std::max(1, setpoint_h - foot);
    const int k = key_size(m, left_w, upper - m.pad(), l.small_number);
    l.minus = {left_x + m.key_inset(), y + m.pad() + std::max(0, (upper - m.pad() - k) / 2), k, k};
    l.plus = {left_x + left_w - m.key_inset() - k, l.minus.y, k, k};
    const int nx = l.minus.right(), nw = std::max(1, l.plus.x - nx);
    l.number = {nx, l.minus.cy() - number_height() / 2, nw, number_height()};
    l.caption = {left_x + m.key_inset(), y + setpoint_h - foot, left_w - 2 * m.key_inset(), m.caption_h};
  }

  int ry = l.columns == 2 ? y : l.setpoint.bottom() + gap;
  if (l.columns == 2) {
    const int below = (l.mode_count ? mode_h : 0) + (l.mode_count && l.row_count ? gap : 0) + settings_h();
    ry = y + std::max(0, (setpoint_h - below) / 2);
  }
  if (l.mode_count) {
    l.modes = {right_x, ry, right_w, mode_h};
    ry += mode_h + gap;
  }
  if (l.row_count) {
    l.settings = {right_x, ry, right_w, settings_h()};
    int iy = ry + edge;
    for (int i = 0; i < l.row_count; ++i) {
      l.rows[i] = {right_x + edge, iy, right_w - 2 * edge, row_h};
      l.row_icons[i] = {l.rows[i].x, iy, m.row_icon(), row_h};
      l.row_tracks[i] = {l.rows[i].x + m.row_icon(), iy, l.rows[i].w - m.row_icon(), row_h};
      iy += row_h + m.row_gap();
    }
  }
  return l;
}
}  // namespace climate_card
