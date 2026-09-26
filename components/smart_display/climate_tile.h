#pragma once
// A thermostat tile of more than one row (firmware 0.3.3): where its controls go under its head. Pure arithmetic,
// free of LVGL, so tests/test_climate_tile.cpp checks every shape on a PC; runtime_tiles.h draws it.
//
// Two groups with a clear order of importance. The temperature it is set to is the first: the number between a -
// and a + key. The modes are the second: one bar with a segment per mode, the one it is in filled in its colour.
// Off is not a mode on the bar; the tile's circle switches the thermostat on and off, as on a Home Assistant tile.
//
// The form follows the room under the head:
//  - **big**: the number large in the middle with the keys at its sides, the bar under it over the card's width.
//  - **row**: one row of a finger's height: the - number + stepper at the left, the bar at the right; on a card too
//    narrow for both, the bar under the stepper.
//  - **none**: no room for a finger's row; the head alone, and a tap opens the card.
// What gives first when the big form is short: the "now" line under the number (the head says it too), then the
// number's size. A segment is never narrower than a finger; the caller asks for as many modes as `room` holds.
#include <algorithm>
#include <array>

#include "ui_scale.h"

namespace climate_tile {

struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
};

enum class Form : unsigned char { none, row, big };
constexpr int FACES = 3;
constexpr int SEGMENTS = 6;

struct Metrics {
  bool large = true;
  int touch = 48;                        // ui::touch_min() or the look's key, whichever is larger
  int gap = 8;
  // The target in the faces a board carries for it, largest first (setpoint digits, watch value, the control text):
  // line height and width. A width of 0: the face lacks a glyph of it.
  std::array<int, FACES> face_h{75, 45, 25};
  std::array<int, FACES> face_w{0, 0, 0};
  int caption_h = 19;                    // "Now 20.5°" under the number, value font
  int max_width = 740;                   // ui::control_max_width(): the reach of one hand
  int inset() const { return std::max(2, ui::px(large ? 4 : 3)); }   // a key inside the stepper, a segment inside the bar
  int stepper_max() const { return ui::px(large ? 250 : 170); }
};

struct Layout {
  Form form = Form::none;
  int face = -1;
  bool caption = false;
  Rect stepper;        // the row form's pill; empty in the big form, whose keys stand on their own
  Rect minus, plus, number, caption_box;
  Rect bar;            // empty when there are no modes to show
  int room = 0;        // how many segments the bar holds
};

// The segments of a bar holding `count` of them, each the same width.
inline std::array<Rect, SEGMENTS> segments(const Metrics &m, Rect bar, int count) {
  std::array<Rect, SEGMENTS> out{};
  count = std::clamp(count, 0, SEGMENTS);
  if (count == 0 || bar.empty()) return out;
  const int in = m.inset(), w = (bar.w - 2 * in) / count;
  for (int i = 0; i < count; ++i) out[i] = {bar.x + in + i * w, bar.y + in, w, bar.h - 2 * in};
  return out;
}

// The controls in the card's content, `width` wide, between `top` (under the head) and `bottom`. `modes`: how many
// modes the bar would like to show (0 for a setpoint only).
inline Layout layout(const Metrics &m, int width, int top, int bottom, int modes) {
  Layout l;
  const int body = bottom - top, t = m.touch, g = m.gap, in = m.inset();
  if (body < t || width < 2 * t + g) return l;
  const int reach = std::min(width, m.max_width), x0 = (width - reach) / 2;
  const int bar_room = modes >= 2 ? std::min(modes, (reach - 2 * in) / t) : 0;
  // Big: the number zone above the bar. The largest face wins, with the "now" line if it fits and without it if
  // only then the face fits; a smaller face with its line comes after.
  const int zone = body - (bar_room >= 2 ? t + 2 * g : 0);
  const int key = std::clamp(std::min(zone, t * 115 / 100), t, t * 2);
  if (zone >= t) {
    // The largest face with its line, then without it, then the smaller faces with their line and last without.
    static constexpr int TRIES[][2] = {{0, 1}, {0, 0}, {1, 1}, {2, 1}, {1, 0}, {2, 0}};
    for (const auto &tr : TRIES) {
      const int f = tr[0], with = tr[1];
      if (m.face_w[f] <= 0 || m.face_w[f] > reach - 2 * key - 2 * g) continue;
      if (m.face_h[f] + (with ? m.caption_h : 0) > zone) continue;
      l.face = f;
      l.caption = with == 1;
      break;
    }
    // The big form is for a card that has more than one row of room: its number has to stand taller than a key.
    if (l.face >= 0 && m.face_h[l.face] + (l.caption ? m.caption_h : 0) >= t + g) {
      l.form = Form::big;
      // The number and the bar are one group in the middle of the room: a tall card (a ten-inch standing up)
      // does not stand its number at the top and its bar at the bottom with a field of white between them.
      const int block = m.face_h[l.face] + (l.caption ? m.caption_h : 0), lead = std::max(block, key);
      const int group = lead + (bar_room >= 2 ? 2 * g + t : 0), first = top + std::max(0, (body - group) / 2);
      l.minus = {x0, first + (lead - key) / 2, key, key};
      l.plus = {x0 + reach - key, l.minus.y, key, key};
      l.number = {l.minus.right() + g, first + (lead - block) / 2, reach - 2 * key - 2 * g, m.face_h[l.face]};
      if (l.caption) l.caption_box = {l.number.x, l.number.bottom(), l.number.w, m.caption_h};
      if (bar_room >= 2) { l.bar = {x0, std::min(bottom - t, first + lead + 2 * g), reach, t}; l.room = bar_room; }
      return l;
    }
    l.face = -1;
    l.caption = false;
  }
  // Row: the stepper at the left, the bar at the right, on one line in the middle of the room.
  int face = -1;
  for (int f = 0; f < FACES; ++f)
    if (m.face_w[f] > 0 && m.face_h[f] <= t + ui::px(m.large ? 6 : 4)) { face = f; break; }
  if (face < 0) return l;
  const int key_in = t - 2 * in;
  const int step_min = 2 * key_in + 2 * in + m.face_w[face] + ui::px(m.large ? 12 : 6);
  if (step_min > reach) {
    // The widest face does not fit between the keys: try the smaller ones.
    for (int f = face + 1; f < FACES; ++f)
      if (m.face_w[f] > 0 && 2 * key_in + 2 * in + m.face_w[f] + ui::px(m.large ? 12 : 6) <= reach) { face = f; break; }
  }
  const int need = 2 * key_in + 2 * in + m.face_w[face] + ui::px(m.large ? 12 : 6);
  if (need > reach) return l;
  int room = modes >= 2 ? std::min(modes, (reach - need - g - 2 * in) / t) : 0;
  // A narrow card (one column, two rows) with no room for the bar beside the stepper puts it under the stepper,
  // where the card has the height for a second finger's row.
  const bool two_lines = modes >= 2 && room < 2 && body >= 2 * t + g && (reach - 2 * in) / t >= 2;
  if (two_lines) room = std::min(modes, (reach - 2 * in) / t);
  const int bar_w = room >= 2 ? (two_lines ? reach : room * t + 2 * in) : 0;
  const int step_w = two_lines ? reach : std::min(bar_w ? reach - bar_w - g : reach, std::max(need, m.stepper_max()));
  const int y = top + (body - (two_lines ? 2 * t + g : t)) / 2;
  l.form = Form::row;
  l.face = face;
  l.stepper = {x0, y, std::max(need, step_w), t};
  l.minus = {x0 + in, y + in, key_in, key_in};
  l.plus = {l.stepper.right() - in - key_in, y + in, key_in, key_in};
  l.number = {l.minus.right(), y + (t - m.face_h[face]) / 2, l.plus.x - l.minus.right(), m.face_h[face]};
  if (room >= 2) { l.bar = two_lines ? Rect{x0, y + t + g, bar_w, t} : Rect{x0 + reach - bar_w, y, bar_w, t}; l.room = room; }
  return l;
}

}  // namespace climate_tile
