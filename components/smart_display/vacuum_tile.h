#pragma once
// A robot vacuum's larger tile (docs/VACUUM.md, "A larger tile"): where its parts go. Pure arithmetic, free of LVGL and
// ESPHome, so tests/test_vacuum_tile.cpp checks it on a PC and tests/test_editor_parity.py holds the editor's port
// (web/src/model/vacuum-tile.ts) to it; module_vacuum_tile.cpp paints what it places.
//
// A small app screen on a tile: a header (the icon, the name, the state, status chips with icons), a hero in a frame
// (the map, the rooms as icon tiles, the routines, or the map with the rooms) and a control dock (the cleaning mode as
// icons, the second key and the first one size up as the tile's focal point). A short tile gives way in a fixed order:
// the mode control, then the keys move up into the header (the battery into the state line), then a last room tile
// says "+N" and opens the card.
#include <algorithm>
#include <cmath>
#include <functional>
#include <string>
#include <vector>
#include "ui_scale.h"

namespace vacuum_tile {

struct Box {
  int x = 0, y = 0, w = 0, h = 0;
  bool empty() const { return w <= 0 || h <= 0; }
  bool has(int px, int py) const { return px >= x && py >= y && px < x + w && py < y + h; }
};
struct Place : Box { int index = 0; };
struct More : Box { int count = 0; };

// The board's faces as the tile writes with them: the name, the small text, the keys' icons, a room's large icon and
// the chips' icons; their line heights, and a width of a text in one of them.
enum Face { LABEL, SMALL, MINI, ICON, WATCH_ICON, FACES };
struct Measure {
  int line[FACES] = {21, 19, 30, 49, 21};
  int circle = 54;  // the tile's icon circle (TILE_ICON_SIZE)
  std::function<int(Face, const std::string &)> width;
};

// What the tile shows: its face, its content box, and what the robot has and says.
enum Ink { INK_TEAL, INK_CHARGING, INK_SLATE, INK_RED };
struct Input {
  std::string face;                  // map, rooms, routines, map_rooms
  int width = 0, height = 0;         // the tile's content
  std::vector<std::string> rooms, routines;
  bool map = false;                  // the robot's device has a map
  int modes = 0;                     // the cleaning mode's segments: 0 none, else 2 to 4
  bool second = true;                // the robot has a second key (vacuum_model::second_key: Dock, or Stop)
  std::string state;
  int battery = -1;                  // -1 when the robot says none
  bool charging = false;
  int progress = -1;                 // -1 when it says none
  int radius = 22, pad = 12;         // the tile's corner and padding (TILE_RADIUS, TILE_PAD)
};
struct Chip { Box box; int kind = 0; std::string words; Ink ink = INK_SLATE; };  // kind 0 the progress, 1 the battery
struct Layout {
  int head = 0;
  Box text;                          // the name and the state line
  std::vector<Chip> chips;
  bool docked = false;               // the keys stand in the dock (else in the header)
  Box second, first, mode, frame;
  int frame_radius = 0, tile_radius = 0;
  Box map;
  std::vector<Place> rooms;
  bool big_icons = false;
  More more;
  std::vector<Place> routines;
  More routines_more;
};

// ---- The look's sizes, from the board's density (ui::px, ui::mm, ui::touch_min) ----
struct Metrics {
  bool large;
  int touch, gap, key, row, pad;
};
inline Metrics metrics() {
  const bool large = ui::large();
  Metrics m{};
  m.large = large;
  m.touch = ui::touch_min();
  m.gap = ui::px(large ? 10 : 6);
  m.key = std::max(m.touch, ui::px(large ? 52 : 40));
  m.row = std::max(m.touch, ui::px(large ? 46 : 34));
  m.pad = ui::px(large ? 8 : 6);
  return m;
}
inline Box inside(const Metrics &m, Box r) { return {r.x + m.pad, r.y + m.pad, r.w - 2 * m.pad, r.h - 2 * m.pad}; }
inline int start_d(const Metrics &m, bool dock) { return dock ? m.key * 6 / 5 : m.key; }
inline int pair_w(const Metrics &m, bool dock = false, bool second = true) { return (second ? m.key + m.gap : 0) + start_d(m, dock); }
inline int mode_w(const Measure &me, const Metrics &m, int modes) {
  const int one = std::max(m.key * 5 / 4, 2 * me.width(MINI, "M") + ui::px(24));
  return modes * one + 2 * std::max(3, m.key / 12);
}
inline int chip_w(const Measure &me, const std::string &words) {
  return ui::px(10) + me.width(WATCH_ICON, "M") + ui::px(5) + me.width(SMALL, words) + ui::px(12);
}

// ---- Rooms as icon tiles ----
inline int room_need_w(const Measure &me, const Metrics &m, const std::vector<std::string> &rooms) {
  int w = 0;
  for (const auto &r : rooms) w = std::max(w, me.width(SMALL, r));
  return w + 2 * m.pad;
}
// Its icon over its name with a thin margin: a frame two rows of rooms almost fit kept them on one (the 8-inch D1001).
inline int room_need_h(const Measure &me, const Metrics &, Face icon) { return 2 * ui::px(5) + me.line[icon] + me.line[SMALL]; }
struct Grid { int cols = 0, rows = 0, w = 0, h = 0, shown = 0; bool big = false; };
// Even rows, every tile at least a name wide and an icon and a line high, no taller than 22 mm; a last "+N" for the rest.
inline Grid room_grid(const Measure &me, const Metrics &m, const std::vector<std::string> &rooms, Box r, int max_rows = 99) {
  const int g = ui::px(6), count = static_cast<int>(rooms.size());
  const int need_w = std::max(room_need_w(me, m, rooms), m.touch), need_h = std::max(room_need_h(me, m, MINI), m.touch);
  const int cols_fit = std::max(0, (r.w + g) / (need_w + g)), rows_fit = std::min(max_rows, (r.h + g) / (need_h + g));
  Grid best;
  if (!cols_fit || rows_fit <= 0 || !count) return best;
  double score = 1e9;
  for (int rows = 1; rows <= rows_fit; ++rows) {
    const int cols = (count + rows - 1) / rows;
    if (cols > cols_fit || cols * (rows - 1) >= count) continue;
    const int w = (r.w - (cols - 1) * g) / cols, h = std::min((r.h - (rows - 1) * g) / rows, ui::mm(22));
    const double a = static_cast<double>(w) / h, off = a > 1.2 ? a / 1.2 : 1.2 / a;
    if (off < score) { score = off; best = {cols, rows, w, h, count, false}; }
  }
  if (!best.cols) {
    const int cap = cols_fit * rows_fit;
    if (cap < 2) return Grid{};
    best = {cols_fit, rows_fit, (r.w - (cols_fit - 1) * g) / cols_fit, std::min((r.h - (rows_fit - 1) * g) / rows_fit, ui::mm(22)), cap - 1, false};
  }
  best.big = best.h >= room_need_h(me, m, ICON) + ui::px(6);
  return best;
}
inline int rooms_reach(const Measure &me, const Metrics &m, const std::vector<std::string> &rooms, Box r, int max_rows = 99) {
  return room_grid(me, m, rooms, r, max_rows).shown;
}
inline void rooms_in(Layout &l, const Measure &me, const Metrics &m, const std::vector<std::string> &rooms, Box r, int max_rows = 99) {
  const Grid gr = room_grid(me, m, rooms, r, max_rows);
  if (!gr.cols) return;
  const int g = ui::px(6), used = gr.rows * gr.h + (gr.rows - 1) * g, y0 = r.y + (r.h - used) / 2;
  auto at = [&](int i) { return Box{r.x + (i % gr.cols) * (gr.w + g), y0 + (i / gr.cols) * (gr.h + g), gr.w, gr.h}; };
  for (int i = 0; i < gr.shown; ++i) { Place p; static_cast<Box &>(p) = at(i); p.index = i; l.rooms.push_back(p); }
  if (gr.shown < static_cast<int>(rooms.size())) { static_cast<Box &>(l.more) = at(gr.shown); l.more.count = static_cast<int>(rooms.size()) - gr.shown; }
  l.big_icons = gr.big;
}

// ---- Routines as a list: a play mark and the name ----
inline int routine_cols(const Measure &me, const Metrics &m, const std::vector<std::string> &names, Box r) {
  int widest = 0;
  for (const auto &n : names) widest = std::max(widest, me.width(SMALL, n));
  return r.w >= 2 * (widest + m.row + ui::px(22)) + ui::px(6) ? 2 : 1;
}
inline int routines_reach(const Measure &me, const Metrics &m, const std::vector<std::string> &names, Box r) {
  const int g = ui::px(6), cap = (r.h + g) / (m.row + g) * routine_cols(me, m, names, r), count = static_cast<int>(names.size());
  // A last place says how many more; where one place is all there is, it shows the first routine instead.
  return cap >= count ? count : cap == 1 ? 1 : std::max(0, cap - 1);
}
inline void routines_in(Layout &l, const Measure &me, const Metrics &m, const std::vector<std::string> &names, Box r) {
  const int g = ui::px(6), count = static_cast<int>(names.size()), cols = routine_cols(me, m, names, r), rows_fit = (r.h + g) / (m.row + g);
  const int rows = std::min(rows_fit, (count + cols - 1) / cols), cap = rows * cols;
  if (cap < 1 || !count) return;
  const int shown = count > cap ? std::max(1, cap - 1) : count, cw = (r.w - (cols - 1) * g) / cols;
  const int used = rows * m.row + (rows - 1) * g, y0 = r.y + (r.h - used) / 2;
  auto at = [&](int i) { return Box{r.x + (i % cols) * (cw + g), y0 + (i / cols) * (m.row + g), cw, m.row}; };
  for (int i = 0; i < shown; ++i) { Place p; static_cast<Box &>(p) = at(i); p.index = i; l.routines.push_back(p); }
  if (shown < count && shown < cap) { static_cast<Box &>(l.routines_more) = at(shown); l.routines_more.count = count - shown; }
}

// ---- The map and the rooms in one frame: side by side on a frame lying down, else the map over a strip of rooms ----
struct Split { Box map, rooms; bool side = false; };  // side: the rooms in a column beside the map, else a strip under it
inline Split split(const Measure &me, const Metrics &m, const std::vector<std::string> &rooms, Box r) {
  const int g = ui::px(8);
  if (r.w * 5 >= r.h * 8) {
    const int rw = std::max(room_need_w(me, m, rooms) * 2 + ui::px(6), r.w * 2 / 5);
    return {{r.x, r.y, r.w - rw - g, r.h}, {r.x + r.w - rw, r.y, rw, r.h}, true};
  }
  const int need_h = std::max(room_need_h(me, m, MINI), m.touch);
  const int rows = rooms_reach(me, m, rooms, {0, 0, r.w, need_h}, 1) >= static_cast<int>(rooms.size()) ? 1 : 2;
  const int rh = rows * need_h + (rows - 1) * ui::px(6);
  return {{r.x, r.y, r.w, r.h - rh - g}, {r.x, r.y + r.h - rh, r.w, rh}, false};
}
inline bool content_ok(const Measure &me, const Metrics &m, const Input &in, Box hero, int map_least, int places) {
  const Box inner = inside(m, hero);
  if (inner.w <= 0 || inner.h <= 0) return false;
  places = std::min(places, static_cast<int>(in.rooms.size()));
  if (in.face == "map") return inner.h >= map_least;
  if (in.face == "rooms") return rooms_reach(me, m, in.rooms, inner) >= places;
  if (in.face == "routines") return routines_reach(me, m, in.routines, inner) >= std::min(3, static_cast<int>(in.routines.size()));
  if (in.face == "map_rooms") {
    const Split sp = split(me, m, in.rooms, inner);
    return sp.map.h >= map_least && sp.map.w >= ui::mm(20) && rooms_reach(me, m, in.rooms, sp.rooms, sp.side ? 99 : 2) >= places;
  }
  return false;
}

// The status chips: how far a run is while the robot cleans, and its battery (by level, or charging).
inline std::string percent(int n) { return std::to_string(n) + " %"; }

// Where every part of the tile stands in its content box.
inline Layout plan(const Measure &me, const Input &in) {
  const Metrics m = metrics();
  Layout l;
  const int w = in.width, h = in.height;
  l.head = std::max(me.circle, me.line[LABEL] + me.line[SMALL] + ui::px(2));
  const int top = l.head + m.gap, tx = me.circle + ui::px(m.large ? 12 : 8), dock_h = start_d(m, true);
  const Box with_dock{0, top, w, h - top - dock_h - m.gap};
  l.docked = content_ok(me, m, in, with_dock, ui::mm(16), 4);
  l.frame = l.docked ? with_dock : Box{0, top, w, h - top};
  if (l.docked) {
    const int cy = h - dock_h / 2, sd = start_d(m, true);
    const int pw = pair_w(m, true, in.second);
    const bool with_mode = in.modes >= 2 && in.face != "routines" && w >= mode_w(me, m, in.modes) + 2 * m.gap + pw;
    const int x = with_mode ? w - pw : (w - pw) / 2;
    if (in.second) l.second = {x, cy - m.key / 2, m.key, m.key};
    l.first = {x + pw - sd, cy - sd / 2, sd, sd};
    if (with_mode) l.mode = {0, cy - m.key / 2, mode_w(me, m, in.modes), m.key};
  } else {
    const int x = w - pair_w(m, false, in.second), y = (l.head - m.key) / 2;
    if (in.second) l.second = {x, y, m.key, m.key};
    l.first = {w - m.key, y, m.key, m.key};
  }
  // Status chips at the header's right where it has room for them beside the name, the battery else in the state line.
  if (l.docked) {
    std::vector<Chip> wanted;
    if (in.state == "cleaning" && in.progress >= 0) { Chip c; c.kind = 0; c.words = percent(in.progress); c.ink = INK_TEAL; wanted.push_back(c); }
    if (in.battery >= 0) {
      Chip c; c.kind = 1; c.words = percent(in.battery);
      c.ink = in.charging ? INK_CHARGING : in.battery <= 20 ? INK_RED : INK_SLATE;
      wanted.push_back(c);
    }
    int all = -ui::px(6);
    for (const auto &c : wanted) all += chip_w(me, c.words) + ui::px(6);
    const int name_least = std::max(me.width(LABEL, "Vacuum"), ui::px(80));
    if (!wanted.empty() && w - tx - all - m.gap >= name_least) {
      const int ch = me.line[SMALL] + ui::px(10);
      int x = w - all;
      for (auto c : wanted) { c.box = {x, (l.head - ch) / 2, chip_w(me, c.words), ch}; x += c.box.w + ui::px(6); l.chips.push_back(c); }
    }
  }
  const int right = l.docked ? (l.chips.empty() ? 0 : w - l.chips.front().box.x + m.gap) : pair_w(m, false, in.second) + m.gap;
  l.text = {tx, 0, w - tx - right, l.head};
  const Box inner = inside(m, l.frame);
  if (in.face == "map") { if (in.map) l.map = inner; }
  else if (in.face == "rooms") rooms_in(l, me, m, in.rooms, inner);
  else if (in.face == "routines") routines_in(l, me, m, in.routines, inner);
  else if (in.face == "map_rooms") {
    const Split sp = split(me, m, in.rooms, inner);
    if (in.map) l.map = sp.map;
    rooms_in(l, me, m, in.rooms, sp.rooms, sp.side ? 99 : 2);
  }
  l.frame_radius = std::max(ui::px(8), in.radius - in.pad);
  l.tile_radius = std::max(ui::px(6), l.frame_radius - m.pad);
  return l;
}

// What a tap at (x, y) of the content lands on: the two keys, a mode segment, a room, a routine, the "+N" tiles, else
// the tile's own tap (its card).
enum HitKind { HIT_NONE, HIT_FIRST, HIT_SECOND, HIT_MODE, HIT_ROOM, HIT_ROUTINE, HIT_MORE };
struct Hit { HitKind kind = HIT_NONE; int arg = 0; };
inline Hit hit(const Layout &l, int modes, int x, int y) {
  // A finger's worth around a small key still lands on it.
  if (l.first.has(x, y)) return {HIT_FIRST, 0};
  if (!l.second.empty() && l.second.has(x, y)) return {HIT_SECOND, 0};
  if (!l.mode.empty() && l.mode.has(x, y) && modes > 0) return {HIT_MODE, std::clamp((x - l.mode.x) * modes / l.mode.w, 0, modes - 1)};
  for (const auto &p : l.rooms) if (p.has(x, y)) return {HIT_ROOM, p.index};
  for (const auto &p : l.routines) if (p.has(x, y)) return {HIT_ROUTINE, p.index};
  if (!l.more.empty() && l.more.has(x, y)) return {HIT_MORE, 0};
  if (!l.routines_more.empty() && l.routines_more.has(x, y)) return {HIT_MORE, 1};
  return {};
}

}  // namespace vacuum_tile
