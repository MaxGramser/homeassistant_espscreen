// A robot vacuum's larger tile on the glass (docs/VACUUM.md, "A larger tile"), of the module vacuum_card (tier full):
// vacuum_tile.h places the parts, this file paints them and takes their taps.
//
// Three objects in the card's extra layer: a canvas under the map (the frame), the map's picture (the tile's own, the
// app paints it through the source vacuum:<entity> at the map's exact size, docs/PICTURES.md), and a canvas over it
// (the header, the chips, the rooms, the routines, the mode and the keys). The canvas over it takes the finger: a part
// under it acts and is drawn pressed; anywhere else the tap is the card's own (its card opens).
//
// What a robot has decides what is drawn, as Home Assistant's own dialog does: its keys (vacuum_model::first_key,
// second_key), its map, its rooms linked to areas, its routines, its cleaning mode. The rooms picked are the tile's own,
// for its robot, until they are cleaned or the robot is another.
//
// Compiled on its own, as module_vacuum_card.cpp is: on Xtensa the literal pool of one object file must stay within
// reach of all of its code.
#include "esphome/core/defines.h"
#ifdef SD_MOD_VACUUM_CARD
#include "esphome/core/log.h"
#include "runtime_tiles.h"
#include "vacuum_tile.h"
#include "battery_status.h"

namespace runtime_tiles {
namespace vacuum_face {
namespace vt = vacuum_tile;
using vacuum_model::Key;

const char *const PLAY = "\U000F040A", *const PAUSE = "\U000F03E4", *const STOP = "\U000F04DB", *const DOCK = "\U000F05F8",
                  *const MORE = "\U000F01D8", *const CLOCK = "\U000F0996", *const MARKER = "\U000F034E", *const FAN = "\U000F0210",
                  *const WATER = "\U000F058C", *const AUTO = "\U000F18F2", *const AREA = "\U000F0FE6", *const ROBOT = "\U000F070D",
                  *const CHARGING = "\U000F0084";

struct View {
  std::string entity;          // the robot the picks are for
  std::vector<uint8_t> picks;  // rooms in the order of the taps
  vt::Input input;
  vt::Layout plan;
  std::string modes;           // the cleaning mode's kinds, one letter per segment (tile_controls::vacuum_role's)
  int mode_on = -1;            // the segment of the mode in use
  vt::Hit pressed;             // the part under the finger, drawn pressed
  std::shared_ptr<const vacuum_model::Data> data;
};

// ---- What the robot has ----
inline const vacuum_model::Data *data_of(const Tile &t) { return t.extra().vacuum.get(); }
bool shows(const Tile &t) {
  return t.domain() == "vacuum" && (t.controls == "map" || t.controls == "rooms" || t.controls == "routines" || t.controls == "map_rooms");
}
static bool has_map(const Tile &t) {
  const auto *d = data_of(t);
  return d && d->has_map() && camera_supported() && (t.controls == "map" || t.controls == "map_rooms");
}
// The cleaning mode as segments: two to four of their own kinds, so each has its own icon; else the card keeps it.
static std::string tile_modes(const Tile &t) {
  const Choice *mode = t.choice('m');
  if (!mode || mode->roles.size() != mode->values.size() || mode->roles.size() < 2 || mode->roles.size() > 4) return "";
  for (size_t i = 0; i < mode->roles.size(); ++i)
    for (size_t j = i + 1; j < mode->roles.size(); ++j) if (mode->roles[i] == mode->roles[j]) return "";
  return mode->roles;
}
static vacuum_model::Can can_of(const Tile &t) { return vacuum_model::can(t.supported); }

// ---- Words and the board's faces ----
static const lv_font_t *face(vt::Face f) {
  switch (f) {
    case vt::LABEL: return label_font ? label_font : detail_font;
    case vt::SMALL: return small_font ? small_font : detail_font;
    case vt::MINI: return mini_icon_font ? mini_icon_font : detail_font;
    case vt::ICON: return tile_icon_font();
    default: return watch_icon_font ? watch_icon_font : (mini_icon_font ? mini_icon_font : detail_font);
  }
}
static vt::Measure measure() {
  vt::Measure m;
  for (int i = 0; i < vt::FACES; ++i) m.line[i] = lv_font_get_line_height(face(static_cast<vt::Face>(i)));
  m.circle = widgets[0].base_circle > 0 ? widgets[0].base_circle : ui::px(ui::large() ? 54 : 36);
  m.width = [](vt::Face f, const std::string &s) { return text_width(s, face(f)); };
  return m;
}
// A line that never leaves its box: too long ends in three dots, as a label of LVGL's does.
static std::string fit(vt::Face f, const std::string &s, int w) {
  const lv_font_t *font = face(f);
  if (w <= 0) return "";
  if (text_width(s, font) <= w) return s;
  std::string out = s;
  while (!out.empty()) {
    do out.pop_back(); while (!out.empty() && (static_cast<uint8_t>(out.back()) & 0xC0) == 0x80);
    if (!out.empty() && (static_cast<uint8_t>(out.back()) & 0x80)) { out.pop_back(); continue; }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    if (text_width(out + "...", font) <= w) return out + "...";
  }
  return "";
}
static std::string room_glyph(uint32_t icon) {
  lv_font_glyph_dsc_t g;
  const lv_font_t *f = face(vt::MINI);
  return icon && f && lv_font_get_glyph_dsc(f, &g, icon, 0) ? tile_icon::utf8(icon) : AREA;
}
// Home Assistant's battery icon for the level, in tens (battery_status::LEVEL_GLYPHS, tile icons all of them).
static std::string battery_glyph(float level) {
  const int round = battery_status::tens(level);
  return tile_icon::utf8(battery_status::LEVEL_GLYPHS[round < 1 ? 1 : round > 10 ? 10 : round]);
}
static const char *key_icon(Key k) {
  switch (k) {
    case Key::PAUSE: return PAUSE;
    case Key::STOP: return STOP;
    case Key::DOCK: return DOCK;
    default: return PLAY;
  }
}
static std::string state_words(const Tile &t, const View &v) {
  const auto *d = v.data.get();
  // Why it stopped where the robot says, else Home Assistant's word.
  if (t.state == "error" && d && !d->error.empty()) return d->error;
  std::string words = vacuum_badge_text(t);
  // The room it is in, where no map shows it with its chip.
  if (t.state == "cleaning" && !t.extra().room.empty() && v.plan.map.empty()) words += "  ·  " + t.extra().room;
  return words;
}

// ---- Painting: the plan's boxes in the canvas's coordinates (the card's content) ----
struct Pen {
  lv_layer_t *layer;
  int ox, oy;
  void box(const vt::Box &b, uint32_t colour, int radius, int border = 0, uint32_t line = 0) const {
    if (b.empty()) return;
    lv_draw_rect_dsc_t d;
    lv_draw_rect_dsc_init(&d);
    d.bg_color = lv_color_hex(colour);
    d.bg_opa = LV_OPA_COVER;
    d.radius = radius;
    if (border) { d.border_width = border; d.border_color = lv_color_hex(line); d.border_opa = LV_OPA_COVER; }
    lv_area_t a{ox + b.x, oy + b.y, ox + b.x + b.w - 1, oy + b.y + b.h - 1};
    lv_draw_rect(layer, &d, &a);
  }
  void text(vt::Face f, const std::string &s, int x, int y, int w, uint32_t colour, lv_text_align_t align = LV_TEXT_ALIGN_LEFT) const {
    const lv_font_t *font = face(f);
    if (s.empty() || w <= 0 || !font) return;
    lv_draw_label_dsc_t d;
    lv_draw_label_dsc_init(&d);
    d.font = font;
    d.color = lv_color_hex(colour);
    d.text = s.c_str();
    // LVGL draws later, when it dispatches the layer; the string here is often a temporary (fit(), std::to_string),
    // gone by then. So LVGL takes a copy of its own: without it the loop task drew freed memory for ever (task
    // watchdog, a boot loop with a vacuum tile on page 1).
    d.text_local = 1;
    d.align = align;
    if (align == LV_TEXT_ALIGN_LEFT) d.flag = LV_TEXT_FLAG_EXPAND;
    const int h = lv_font_get_line_height(font);
    lv_area_t a{ox + x, oy + y, ox + x + w - 1, oy + y + h - 1};
    lv_draw_label(layer, &d, &a);
  }
  // A glyph in the middle of a box.
  void glyph(vt::Face f, const std::string &g, const vt::Box &b, uint32_t colour) const {
    const lv_font_t *font = face(f);
    if (!font) return;
    text(f, g, b.x, b.y + (b.h - lv_font_get_line_height(font)) / 2, b.w, colour, LV_TEXT_ALIGN_CENTER);
  }
};
static View *view_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? extra_owner(extra) : nullptr;
  return owner ? owner->vacuum_face : nullptr;
}
static const Tile *tile_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  auto *owner = extra ? extra_owner(extra) : nullptr;
  return owner && owner->index < model.count ? &model.tiles[owner->index] : nullptr;
}
static uint32_t pressed(uint32_t colour, bool on) { return on ? theme::pressed(colour) : colour; }

// Under the map: the frame.
static void draw_under(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *v = view_of(canvas);
  if (!v) return;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const Pen pen{lv_event_get_layer(e), a.x1, a.y1};
  pen.box(v->plan.frame, theme::hex(theme::TRACK), v->plan.frame_radius);
}

// Over the map: everything else.
static void draw_over(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  View *v = view_of(canvas);
  const Tile *tp = tile_of(canvas);
  if (!v || !tp) return;
  const Tile &t = *tp;
  const vt::Layout &l = v->plan;
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  const Pen pen{lv_event_get_layer(e), a.x1, a.y1};
  const uint32_t ink = theme::hex(theme::INK), muted = theme::hex(theme::MUTED), card = theme::hex(theme::CARD),
                 track = theme::hex(theme::TRACK), slate = theme::hex(theme::SLATE), accent = theme::hex(theme::ACCENT),
                 on_accent = theme::hex(theme::ON_ACCENT), line = theme::hex(theme::LINE);
  const bool live = fresh() && t.available();

  // The header: the circle as every tile has it, the name, the state.
  const int c = v->input.width ? measure().circle : 0;
  const uint32_t state_colour = t.active() ? tile_controls::accent(t) : theme::STATE_OFF;
  const vt::Box circle{0, (l.head - c) / 2, c, c};
  pen.box(circle, t.available() ? theme::tint(state_colour, 38) : track, c / 2);
  pen.glyph(vt::ICON, icon_for(t), circle, t.available() ? theme::icon(state_colour) : theme::hex(theme::OFF));
  const int lh = lv_font_get_line_height(face(vt::LABEL)), sh = lv_font_get_line_height(face(vt::SMALL));
  const int ty = (l.head - lh - ui::px(2) - sh) / 2;
  pen.text(vt::LABEL, fit(vt::LABEL, t.name.empty() ? t.entity : t.name, l.text.w), l.text.x, ty, l.text.w, ink);
  std::string words = state_words(t, *v);
  if (l.chips.empty() && std::isfinite(t.battery)) words += "  ·  " + screen_text::percent(static_cast<int>(std::lround(t.battery)));
  if (t.state == "error" && text_width(words, face(vt::SMALL)) > l.text.w) words = tr(txt::ha_vacuum_error);
  pen.text(vt::SMALL, fit(vt::SMALL, words, l.text.w), l.text.x, ty + lh + ui::px(2), l.text.w,
           t.state == "error" ? theme::foreground(theme::ha::RED) : muted);
  // The chips: how far it is, its battery.
  for (const auto &chip : l.chips) {
    pen.box(chip.box, track, chip.box.h / 2);
    const std::string icon = chip.kind == 0 ? CLOCK : t.extra().charging ? CHARGING : battery_glyph(t.battery);
    const uint32_t colour = chip.ink == vt::INK_TEAL ? theme::foreground(theme::ha::TEAL) : chip.ink == vt::INK_CHARGING ? theme::foreground(theme::ha::CHARGING)
                            : chip.ink == vt::INK_RED ? theme::foreground(theme::ha::RED) : slate;
    const int iw = text_width(icon, face(vt::WATCH_ICON));
    pen.glyph(vt::WATCH_ICON, icon, {chip.box.x + ui::px(10), chip.box.y, iw, chip.box.h}, colour);
    pen.text(vt::SMALL, chip.words, chip.box.x + ui::px(10) + iw + ui::px(5), chip.box.y + (chip.box.h - sh) / 2, chip.box.w, ink);
  }

  const auto *d = v->data.get();
  // The map: where the robot is while it cleans, as a chip on the map; a robot without its map shows itself.
  if (v->input.face == "map" || v->input.face == "map_rooms") {
    if (l.map.empty()) {
      const vt::Box hero = vt::inside(vt::metrics(), l.frame);
      pen.glyph(vt::ICON, ROBOT, hero, slate);
    } else if (t.state == "cleaning" && !t.extra().room.empty()) {
      const int ch = sh + ui::px(10), iw = text_width(MARKER, face(vt::WATCH_ICON));
      const std::string room = fit(vt::SMALL, t.extra().room, l.map.w / 2);
      const vt::Box chip{l.map.x + ui::px(4), l.map.y + l.map.h - ch - ui::px(4), ui::px(10) + iw + ui::px(5) + text_width(room, face(vt::SMALL)) + ui::px(12), ch};
      pen.box(chip, card, ch / 2);
      pen.glyph(vt::WATCH_ICON, MARKER, {chip.x + ui::px(10), chip.y, iw, ch}, theme::foreground(theme::ha::TEAL));
      pen.text(vt::SMALL, room, chip.x + ui::px(10) + iw + ui::px(5), chip.y + (ch - sh) / 2, chip.w, ink);
    }
  }
  // The rooms: an icon tile each, picked in blue with its place in the order.
  const vt::Face room_icon = l.big_icons ? vt::ICON : vt::MINI;
  for (const auto &p : l.rooms) {
    if (!d || p.index >= static_cast<int>(d->rooms.size())) continue;
    const int at = vacuum_model::place(v->picks, static_cast<uint8_t>(p.index));
    const bool down = v->pressed.kind == vt::HIT_ROOM && v->pressed.arg == p.index;
    pen.box(p, pressed(at ? accent : card, down), l.tile_radius);
    const int il = lv_font_get_line_height(face(room_icon)), y = p.y + (p.h - il - sh) / 2;
    pen.glyph(room_icon, room_glyph(d->rooms[p.index].icon), {p.x, y, p.w, il}, at ? on_accent : slate);
    pen.text(vt::SMALL, fit(vt::SMALL, d->rooms[p.index].name, p.w - 2 * ui::px(6)), p.x + ui::px(6), y + il, p.w - 2 * ui::px(6), at ? on_accent : ink, LV_TEXT_ALIGN_CENTER);
    if (at) {
      const int n = sh + ui::px(2);
      const vt::Box disc{p.x + p.w - n - ui::px(5), p.y + ui::px(5), n, n};
      pen.box(disc, on_accent, n / 2);
      pen.text(vt::SMALL, std::to_string(at), disc.x, disc.y + (n - sh) / 2, n, accent, LV_TEXT_ALIGN_CENTER);
    }
  }
  if (!l.more.empty()) {
    // The rest are on the card: a pick among them says so in blue.
    bool hides = false;
    for (uint8_t k : v->picks) hides = hides || k >= l.rooms.size();
    const bool down = v->pressed.kind == vt::HIT_MORE && v->pressed.arg == 0;
    pen.box(l.more, pressed(card, down), l.tile_radius, hides ? 2 : 0, accent);
    const int il = lv_font_get_line_height(face(room_icon)), y = l.more.y + (l.more.h - il - sh) / 2;
    pen.glyph(room_icon, MORE, {l.more.x, y, l.more.w, il}, hides ? accent : slate);
    pen.text(vt::SMALL, "+" + std::to_string(l.more.count), l.more.x, y + il, l.more.w, hides ? accent : muted, LV_TEXT_ALIGN_CENTER);
  }
  // A robot that cleans by area with no room linked yet: Home Assistant's own words, which the card explains.
  if (v->input.face == "rooms" && d && d->rooms.empty()) {
    const vt::Box in = vt::inside(vt::metrics(), l.frame);
    pen.text(vt::SMALL, fit(vt::SMALL, tr(txt::vacuum_no_rooms), in.w), in.x, in.y + (in.h - sh) / 2, in.w, muted, LV_TEXT_ALIGN_CENTER);
  }
  // The routines: a play mark and the name; a tap runs one.
  for (const auto &p : l.routines) {
    if (!d || p.index >= static_cast<int>(d->routines.size())) continue;
    const bool down = v->pressed.kind == vt::HIT_ROUTINE && v->pressed.arg == p.index;
    pen.box(p, pressed(card, down), l.tile_radius);
    const int disc = p.h - 2 * ui::px(6);
    const vt::Box mark{p.x + ui::px(6), p.y + ui::px(6), disc, disc};
    pen.box(mark, theme::tint(theme::ha::TEAL, 36), disc / 2);
    pen.glyph(vt::WATCH_ICON, PLAY, mark, theme::foreground(theme::ha::TEAL));
    const int tx = mark.x + disc + ui::px(10);
    pen.text(vt::SMALL, fit(vt::SMALL, d->routines[p.index].name, p.x + p.w - tx - ui::px(6)), tx, p.y + (p.h - sh) / 2, p.x + p.w - tx - ui::px(6), ink);
  }
  if (!l.routines_more.empty()) {
    const bool down = v->pressed.kind == vt::HIT_MORE && v->pressed.arg == 1;
    pen.box(l.routines_more, pressed(card, down), l.tile_radius);
    pen.text(vt::SMALL, "+" + std::to_string(l.routines_more.count), l.routines_more.x, l.routines_more.y + (l.routines_more.h - sh) / 2,
             l.routines_more.w, muted, LV_TEXT_ALIGN_CENTER);
  }
  // The cleaning mode as icons, the one in use in blue.
  if (!l.mode.empty() && !v->modes.empty()) {
    pen.box(l.mode, track, l.mode.h / 2);
    const int n = static_cast<int>(v->modes.size()), inset = std::max(3, l.mode.h / 12), sw = (l.mode.w - 2 * inset) / n;
    for (int i = 0; i < n; ++i) {
      const vt::Box seg{l.mode.x + inset + i * sw, l.mode.y + inset, i == n - 1 ? l.mode.w - 2 * inset - (n - 1) * sw : sw, l.mode.h - 2 * inset};
      const bool on = i == v->mode_on, down = v->pressed.kind == vt::HIT_MODE && v->pressed.arg == i;
      if (on || down) pen.box(seg, on ? pressed(accent, down) : theme::pressed(track), seg.h / 2);
      const uint32_t colour = on ? on_accent : slate;
      const char kind = v->modes[i];
      if (kind == 'b') {
        const int fw = text_width(FAN, face(vt::MINI)), ww = text_width(WATER, face(vt::MINI)), gap = ui::px(2), x0 = seg.x + (seg.w - fw - gap - ww) / 2;
        pen.glyph(vt::MINI, FAN, {x0, seg.y, fw, seg.h}, colour);
        pen.glyph(vt::MINI, WATER, {x0 + fw + gap, seg.y, ww, seg.h}, colour);
      } else {
        pen.glyph(vt::MINI, kind == 'v' ? FAN : kind == 'm' ? WATER : AUTO, seg, colour);
      }
    }
  }
  // The keys: the second white with a hairline, the first blue and a size up, with the rooms picked on it.
  const auto can = can_of(t);
  const Key first = vacuum_model::first_key(t.state, can), second = vacuum_model::second_key(t.state, can);
  const bool wait = t.loading(esphome::millis()) || !live;
  if (!l.second.empty() && second != Key::NONE) {
    const bool down = v->pressed.kind == vt::HIT_SECOND;
    pen.box(l.second, pressed(card, down), l.second.h / 2, 1, line);
    pen.glyph(vt::MINI, key_icon(second), l.second, wait ? muted : ink);
  }
  if (first != Key::NONE) {
    const bool down = v->pressed.kind == vt::HIT_FIRST;
    pen.box(l.first, wait ? theme::hex(theme::OFF) : pressed(accent, down), l.first.h / 2);
    pen.glyph(vt::MINI, key_icon(first), l.first, on_accent);
    if (first == Key::START && !v->picks.empty() && (v->input.face == "rooms" || v->input.face == "map_rooms")) {
      const int n = std::max(sh, l.first.h * 2 / 5);
      const vt::Box badge{l.first.x + l.first.w - n, l.first.y, n, n};
      pen.box(badge, card, n / 2, 2, accent);
      pen.text(vt::SMALL, std::to_string(v->picks.size()), badge.x, badge.y + (n - sh) / 2, n, accent, LV_TEXT_ALIGN_CENTER);
    }
  }
}

// ---- The finger ----
static Widgets *owner_of(lv_obj_t *canvas) {
  auto *extra = canvas ? lv_obj_get_parent(canvas) : nullptr;
  return extra ? extra_owner(extra) : nullptr;
}
static vt::Hit hit_at(Widgets &w, lv_obj_t *canvas) {
  View *v = w.vacuum_face;
  auto *input = lv_indev_active();
  if (!v || !input) return {};
  lv_point_t p;
  lv_indev_get_point(input, &p);
  lv_area_t a;
  lv_obj_get_coords(canvas, &a);
  return vt::hit(v->plan, static_cast<int>(v->modes.size()), p.x - a.x1, p.y - a.y1);
}
static void finger(lv_event_t *e) {
  auto *canvas = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  Widgets *w = owner_of(canvas);
  if (!w || !w->vacuum_face || !w->tile) return;
  View &v = *w->vacuum_face;
  const lv_event_code_t code = lv_event_get_code(e);
  if (code == LV_EVENT_PRESSED) {
    // A part shows its own press; anywhere else the card does, as every card.
    v.pressed = hit_at(*w, canvas);
    if (v.pressed.kind == vt::HIT_NONE) lv_obj_add_state(w->tile, LV_STATE_PRESSED);
    lv_obj_invalidate(canvas);
    return;
  }
  if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) {
    if (v.pressed.kind == vt::HIT_NONE) lv_obj_remove_state(w->tile, LV_STATE_PRESSED);
    v.pressed = {};
    lv_obj_invalidate(canvas);
    return;
  }
  // A tap beside the parts and every hold are the card's own: its card opens.
  if (code == LV_EVENT_LONG_PRESSED || hit_at(*w, canvas).kind == vt::HIT_NONE) {
    lv_obj_send_event(w->tile, code, nullptr);
    return;
  }
  if (code == LV_EVENT_SHORT_CLICKED && w->index < model.count) card_tap(*w, model.tiles[w->index]);
}

// ---- Drawing the face ----
static lv_obj_t *canvas(lv_obj_t *parent, lv_event_cb_t draw, bool takes_finger) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  if (takes_finger) {
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    for (auto code : {LV_EVENT_PRESSED, LV_EVENT_RELEASED, LV_EVENT_PRESS_LOST, LV_EVENT_SHORT_CLICKED, LV_EVENT_LONG_PRESSED})
      lv_obj_add_event_cb(o, finger, code, nullptr);
  } else {
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  }
  lv_obj_add_event_cb(o, draw, LV_EVENT_DRAW_MAIN, nullptr);
  return o;
}
void release(Widgets &w) {
  delete w.vacuum_face;
  w.vacuum_face = nullptr;
}
static void replan(Widgets &w, const Tile &t, int width, int height) {
  View &v = *w.vacuum_face;
  const auto *d = data_of(t);
  v.data = t.extra().vacuum;
  vt::Input &in = v.input;
  in = vt::Input();
  in.face = t.controls;
  in.width = width;
  in.height = height;
  if (d) {
    for (const auto &r : d->rooms) in.rooms.push_back(r.name);
    for (const auto &r : d->routines) in.routines.push_back(r.name);
  }
  // Cleaning per room only where the robot can (Home Assistant's CLEAN_AREA).
  if (!can_of(t).by_area) in.rooms.clear();
  in.map = has_map(t);
  v.modes = tile_modes(t);
  in.modes = static_cast<int>(v.modes.size());
  v.mode_on = -1;
  if (const Choice *mode = t.choice('m')) {
    const std::string now = tile_controls::shown_value(t, *mode, esphome::millis());
    for (size_t i = 0; i < mode->values.size(); ++i) if (mode->values[i] == now) v.mode_on = static_cast<int>(i);
  }
  in.second = vacuum_model::second_key(t.state, can_of(t)) != Key::NONE;
  in.state = t.state;
  in.battery = std::isfinite(t.battery) ? static_cast<int>(std::lround(t.battery)) : -1;
  in.charging = t.extra().charging;
  in.progress = d && t.state == "cleaning" ? d->progress : -1;
  in.radius = lv_obj_get_style_radius(w.tile, LV_PART_MAIN);
  in.pad = lv_obj_get_style_pad_left(w.tile, LV_PART_MAIN);
  v.plan = vt::plan(measure(), in);
}
void render(Widgets &w, const Tile &t, int width, int height) {
  begin_extra(w, "vacuum_tile", width, height);
  if (!w.vacuum_face) w.vacuum_face = new View();
  View &v = *w.vacuum_face;
  // The picks are the robot's: another robot in this slot starts without any, rooms gone are dropped.
  if (v.entity != t.entity) { v.entity = t.entity; v.picks.clear(); v.pressed = {}; }
  if (const auto *d = data_of(t)) vacuum_model::keep_valid(v.picks, d->rooms.size());
  auto *&under = w.parts[0];
  auto *&map = w.parts[1];
  auto *&over = w.parts[2];
  if (!under) under = canvas(w.extra, draw_under, false);
#if LV_USE_IMAGE
  if (!map) {
    map = lv_image_create(w.extra);
    lv_obj_remove_flag(map, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(map, LV_OBJ_FLAG_HIDDEN);
  }
#endif
  if (!over) over = canvas(w.extra, draw_over, true);
  for (auto *o : {under, over}) { lv_obj_set_pos(o, 0, 0); lv_obj_set_size(o, width, height); }
  replan(w, t, width, height);
  picture_place(w, t);
  lv_obj_invalidate(under);
  lv_obj_invalidate(over);
}

// ---- The map's picture ----
bool map_place(const Widgets &w, int &x, int &y, int &width, int &height) {
  if (!w.vacuum_face || w.vacuum_face->plan.map.empty()) return false;
  const auto &m = w.vacuum_face->plan.map;
  x = m.x; y = m.y; width = m.w; height = m.h;
  return true;
}
lv_obj_t *picture(const Widgets &w) { return w.vacuum_face && w.extra_mode == "vacuum_tile" ? w.parts[1] : nullptr; }
void picture_place(Widgets &w, const Tile &t) {
#if LV_USE_IMAGE
  lv_obj_t *image = picture(w);
  if (!image) return;
  const auto &m = w.vacuum_face->plan.map;
  const bool mine = !m.empty() && tile_picture::belongs(w.art_key, w.index, t.entity);
  lv_image_dsc_t *src = mine ? picture_of(w.art_key) : nullptr;
  // Until the robot's next map is here the tile keeps the one it shows of the same place.
  if (!src && mine && pictures_kept()) {
    auto *held = pictures.holder(static_cast<const lv_image_dsc_t *>(lv_image_get_src(image)));
    if (held && tile_picture::place_of(held->key) == tile_picture::place_of(w.art_key)) src = &held->image;
  }
  if (!src) {
    lv_image_set_src(image, nullptr);
    lv_obj_add_flag(image, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  if (lv_image_get_src(image) != src) lv_image_set_src(image, src);
  const int pw = src->header.w, ph = src->header.h;
  lv_obj_set_pos(image, m.x + (m.w - pw) / 2, m.y + (m.h - ph) / 2);
  lv_obj_set_size(image, pw, ph);
  lv_obj_remove_flag(image, LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(image);
#else
  (void) w; (void) t;
#endif
}

std::string describe(const Widgets &w) {
  const View *v = w.vacuum_face;
  auto *over = w.extra_mode == "vacuum_tile" ? w.parts[2] : nullptr;
  if (!v || !over) return "";
  lv_area_t a;
  lv_obj_get_coords(over, &a);
  std::string out = v->input.face + "|";
  auto add = [&](int kind, int arg, const vt::Box &b) {
    if (b.empty()) return;
    out += std::to_string(kind) + ":" + std::to_string(arg) + "@" + std::to_string(a.x1 + b.x + b.w / 2) + "," + std::to_string(a.y1 + b.y + b.h / 2) + ";";
  };
  const auto &l = v->plan;
  add(vt::HIT_FIRST, 0, l.first);
  add(vt::HIT_SECOND, 0, l.second);
  for (const auto &r : l.rooms) add(vt::HIT_ROOM, r.index, r);
  for (const auto &r : l.routines) add(vt::HIT_ROUTINE, r.index, r);
  add(vt::HIT_MORE, 0, l.more);
  add(vt::HIT_MORE, 1, l.routines_more);
  const int n = static_cast<int>(v->modes.size());
  for (int i = 0; i < n && !l.mode.empty(); ++i) add(vt::HIT_MODE, i, {l.mode.x + l.mode.w * i / n, l.mode.y, l.mode.w / n, l.mode.h});
  out += "|picks=";
  for (uint8_t k : v->picks) out += std::to_string(k) + ",";
  out += "|map=" + std::to_string(l.map.x) + "," + std::to_string(l.map.y) + "," + std::to_string(l.map.w) + "," + std::to_string(l.map.h);
  return out;
}

// ---- A tap on a part ----
bool card_tap(Widgets &w, const Tile &tile) {
  View *v = w.vacuum_face;
  auto *over = w.parts[2];
  if (!v || !over || w.index >= model.count) return false;
  const vt::Hit h = hit_at(w, over);
  if (h.kind == vt::HIT_NONE) return false;
  const uint32_t now = esphome::millis();
  Tile &t = model.tiles[w.index];
  (void) tile;
  // The guard every key has: a second tap of one contact, drift and bounce go (touch_guard).
  if (!allowed(now, 3200 + static_cast<int>(w.index) * 8 + static_cast<int>(h.kind), t.entity)) return true;
  if (h.kind == vt::HIT_MORE) { hold_card(w.index); return true; }
  if (!fresh() || !t.available() || t.waiting(now)) return true;
  const auto *d = v->data.get();
  const auto can = can_of(t);
  switch (h.kind) {
    case vt::HIT_ROOM:
      vacuum_model::toggle(v->picks, static_cast<uint8_t>(h.arg));
      break;
    case vt::HIT_ROUTINE:
      if (d && h.arg < static_cast<int>(d->routines.size())) action("button.press", d->routines[h.arg].entity);
      break;
    case vt::HIT_MODE:
      if (Choice *mode = const_cast<Choice *>(t.choice('m'))) if (h.arg < static_cast<int>(mode->values.size())) choose(t, *mode, mode->values[h.arg]);
      break;
    case vt::HIT_FIRST: {
      const Key k = vacuum_model::first_key(t.state, can);
      // Start with rooms picked cleans those, in the order of the taps (vacuum.clean_area, Home Assistant 2026.3+).
      if (k == Key::START && !v->picks.empty() && can.by_area && d) {
        const std::string areas = vacuum_model::areas_template(*d, v->picks);
        if (!areas.empty()) action_template("vacuum.clean_area", t.entity, "cleaning_area_id", areas);
        v->picks.clear();
      } else if (k != Key::NONE) {
        action(vacuum_model::service(k), t.entity);
      }
      break;
    }
    case vt::HIT_SECOND: {
      const Key k = vacuum_model::second_key(t.state, can);
      if (k != Key::NONE) action(vacuum_model::service(k), t.entity);
      break;
    }
    default: break;
  }
  ESP_LOGI("vacuum", "tile %u: part %d (%d)", (unsigned) w.index, static_cast<int>(h.kind), h.arg);
  replan(w, t, v->input.width, v->input.height);
  lv_obj_invalidate(over);
  return true;
}

}  // namespace vacuum_face
}  // namespace runtime_tiles
#endif
