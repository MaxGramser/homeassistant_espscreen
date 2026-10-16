// The vacuum card of the module (module vacuum, tier full; docs/MODULES.md, docs/VACUUM.md). A lite screen keeps the
// card it had (render_vacuum_detail) and compiles none of this.
//
// One card that grows with the glass. What matters most comes first, and what the glass has no room for becomes a key
// with words that opens its view of the card; what the robot does not have is not there:
//   1. the robot: its state as a headline and its battery, with its map under it (vacuum_model.h; the add-on cleans the
//      map up and draws it in the screen's look, vacuum_map.py), or the drawn robot of the lite card without one;
//   2. its keys, as Home Assistant's dialog gives them (vacuum_model::first_key), and Locate where it can;
//   3. cleaning per room (vacuum.clean_area): the rooms on the card, picked in the order of the taps with Start counting
//      them, or a key to the rooms view (per floor, pages where they don't all fit, Home Assistant's empty state when no
//      area is linked yet);
//   4. suction and water: the chips of the lite card on the card, or a key in the top bar to their view;
//   5. the robot's routines: a list on the card, or a key to their view.
// Square and standing glass stack it in one column a hand wide; landscape glass puts the map at the left and the rest
// at the right (Start and Dock under both when the right column is too narrow for them side by side); low landscape
// glass puts the state beside the map and one row of keys, each an icon over its word, under it.
//
// The views are the card's own (view): built again when one opens, the back key returns to the card. Picks are the
// card's, painted in place (docs/CARD_PARTS.md); a value of Home Assistant on the card is bound or in its shape.
// Compiled on its own, as media_library.cpp and page_receiver.cpp are: every header of this component lands in main.cpp,
// and on Xtensa the literal pool of one object file must stay within reach of all of its code (an S3 build of the
// Guition failed to link with this card inline). runtime_tiles.h knows it by its header.
#include "esphome/core/defines.h"
#ifdef SD_MOD_VACUUM_CARD
#include "esphome/core/log.h"
#include "runtime_tiles.h"

namespace runtime_tiles {
namespace vacuum_card {
using vacuum_model::Data;
using vacuum_model::Key;

// ---- The card's own state: which view, what is picked, and the map it asks for ----
enum View : uint8_t { MAIN, ROOMS, ROUTINES, HOW };
inline View view = MAIN;
inline std::string entity;            // the robot the state belongs to
inline std::vector<uint8_t> picks;    // rooms in the order of the taps (indexes into Data::rooms)
inline int floor = 0, page = 0;       // the rooms view's floor and page
struct MapAsk {
  std::string entity, map, mark;
  int w = 0, h = 0;
  uint32_t ground = 0;
  bool dark = false;
  bool valid() const { return !entity.empty() && !map.empty() && !mark.empty() && w > 0 && h > 0; }
};
inline MapAsk map_ask;
inline std::string map_shown;         // the key of the picture on the card now; it stays until the next one is here
inline lv_obj_t *map_picture = nullptr;
// The firmware's one spinner in the map's place until the map is here; it goes too when the app has none to give.
inline lv_obj_t *map_spinner = nullptr;
inline std::string map_missing;       // the key the app had no picture for
// The card's keys with their commands, for the renders (tools/render/host.py, render_vacuum) and a diagnosis.
struct Hit { int cmd; lv_obj_t *obj; };
inline std::vector<Hit> hits;

// Commands of the card's keys (detail_command): beside the lite card's 0-3, 10-15, 50-55 and 60-65.
constexpr int CMD_FIRST = 800, CMD_SECOND = 801, CMD_LOCATE = 802, CMD_CLEAN_ROOMS = 803, CMD_PICK = 810, CMD_ROOMS = 840, CMD_ROUTINES = 841,
              CMD_HOW = 842, CMD_FLOOR = 843, CMD_PAGE_BACK = 849, CMD_PAGE_ON = 850, CMD_ROUTINE = 860, CMD_LAST = 899;
const char *const ICON_ROOMS = "\U000F0FE6", *const ICON_ROUTINES = "\U000F0411", *const ICON_HOW = "\U000F0210",
           *const ICON_LOCATE = "\U000F034E", *const ICON_PLAY = "\U000F040A", *const ICON_PAUSE = "\U000F03E4",
           *const ICON_STOP = "\U000F04DB", *const ICON_DOCK = "\U000F05F8", *const ICON_CHEVRON = "\U000F0142",
           *const ICON_BACK = "\U000F0141", *const ICON_ROBOT = "\U000F070D";

inline const Data *data_of(const Tile &t) { return t.extra().vacuum.get(); }
inline vacuum_model::Can can_of(const Tile &t) { return vacuum_model::can(t.supported); }
inline bool by_room(const Tile &t) { const Data *d = data_of(t); return d && can_of(t).by_area && d->by_room(); }
inline bool has_routines(const Tile &t) { const Data *d = data_of(t); return d && !d->routines.empty(); }
inline bool shows_map(const Tile &t) { const Data *d = data_of(t); return d && d->has_map() && camera_supported(); }
inline bool has_how(const Tile &t) { return t.choice('m') || t.choice('s') || t.choice('w'); }
// The card the screen had opened last for another robot is forgotten.
inline void follow(const Tile &t) {
  if (t.entity == entity) return;
  entity = t.entity;
  view = MAIN; picks.clear(); floor = page = 0;
}
inline void reset() { view = MAIN; picks.clear(); floor = page = 0; map_ask = MapAsk{}; }

// ---- Sizes, from the look ----
struct Metrics {
  bool large;
  int pad, gap, in, action_h, key_h, chip_h, row_h, radius;
  const lv_font_t *big, *text, *small, *icons, *small_icons;
};
inline Metrics metrics() {
  const bool large = ui::large();
  Metrics m{};
  m.large = large;
  m.pad = overlay_card::pad();
  m.gap = ui::px(large ? 12 : 6);
  m.in = ui::px(large ? 16 : 10);
  m.action_h = std::max(ui::touch_min(), ui::px(large ? 54 : 40));
  m.key_h = std::max(ui::touch_min(), ui::px(large ? 56 : 40));
  m.chip_h = std::max(ui::touch_min(), ui::px(large ? 48 : 34));
  m.row_h = std::max(ui::touch_min(), ui::px(large ? 52 : 38));
  m.radius = lv_obj_get_style_radius(widgets[0].tile, LV_PART_MAIN);
  m.big = watch_font ? watch_font : detail_font;
  m.text = large ? detail_font : (control_font ? control_font : detail_font);
  m.small = small_font ? small_font : detail_font;
  m.icons = mini_icon_font ? mini_icon_font : detail_font;
  m.small_icons = watch_icon_font ? watch_icon_font : m.icons;
  return m;
}
inline int line_of(const lv_font_t *f) { return static_cast<int>(lv_font_get_line_height(f)); }
// The glyph of an area's icon when the font carries it, else Home Assistant's own icon for an area.
inline std::string room_glyph(uint32_t icon, const lv_font_t *font) {
  if (icon && font) { lv_font_glyph_dsc_t dsc; if (lv_font_get_glyph_dsc(font, &dsc, icon, 0)) return tile_icon::utf8(icon); }
  return ICON_ROOMS;
}

// ---- Parts ----
// A plain object that answers a tap with a card command (as detail_button does), and a tile's press feedback.
inline lv_obj_t *key_obj(int x, int y, int w, int h, int cmd, uint32_t color, int radius) {
  auto *o = lv_obj_create(detail_root);
  lv_obj_remove_style_all(o);
  lv_obj_set_pos(o, x, y); lv_obj_set_size(o, w, h);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_color(o, lv_color_hex(color), 0);
  lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(o, radius, 0);
  lv_obj_set_style_opa(o, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_add_event_cb(o, [](lv_event_t *e) { detail_command(static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)))); },
                      LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(cmd)));
  if (detail_action_count < 32) detail_actions[detail_action_count++] = o;
  hits.push_back({cmd, o});
  return o;
}
inline lv_obj_t *glyph(lv_obj_t *parent, const std::string &g, int x, int y, const lv_font_t *font, uint32_t color) {
  auto *l = lv_label_create(parent);
  lv_label_set_text(l, g.c_str());
  lv_obj_remove_flag(l, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(l, font, 0);
  lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
  lv_obj_set_pos(l, x, y);
  return l;
}
inline void glyph_centred(lv_obj_t *parent, const std::string &g, int x, int y, int w, int h, const lv_font_t *font, uint32_t color) {
  glyph(parent, g, x + (w - text_width(g, font)) / 2, y + (h - line_of(font)) / 2, font, color);
}

// The robot's header: the state as a headline (vacuum_badge_text: the wait and a slow answer too), the battery at its
// right, or under it in a narrow header; while it cleans a line with the room and how far, and a thin bar; on an error
// why, in red.
inline bool cleaning(const Tile &t) { return t.state == "cleaning"; }
// The headline: why it stopped when the robot's integration says so (the reason is the news), else the state as the
// lite card words it (vacuum_badge_text: the wait and a slow answer too).
// The headline: the state as the lite card words it (vacuum_badge_text: the wait and a slow answer too); on an error
// with a reason Home Assistant's word for it, the reason on the line under it, so a long reason is never cut.
inline bool has_reason(const Tile &t) { const Data *d = data_of(t); return t.state == "error" && d && !d->error.empty(); }
inline std::string headline(const Tile &t) {
  if (has_reason(t) && !t.loading(esphome::millis())) return tr(txt::ha_vacuum_error);
  return vacuum_badge_text(t);
}
inline void headline_paint(lv_obj_t *o, const Tile &t, const CardPart &) { label(o, headline(t)); }
inline std::string detail_line(const Tile &t, int room, const lv_font_t *font) {
  const Data *d = data_of(t);
  if (has_reason(t)) return d->error;
  if (!cleaning(t)) return "";
  std::string parts[3] = {t.extra().room, d && d->progress >= 0 ? screen_text::percent(d->progress) : "",
                          d && std::isfinite(d->area) ? screen_text::with_unit(screen_text::decimal(d->area, 0), "m²") : ""};
  for (int n = 3; n > 0; --n) {
    std::string out;
    for (int i = 0; i < n; ++i) if (!parts[i].empty()) out += (out.empty() ? "" : "  ·  ") + parts[i];
    if (text_width(out, font) <= room || n == 1) return out;
  }
  return "";
}
inline bool has_line(const Tile &t) { return !detail_line(t, 100000, detail_font).empty(); }
inline bool has_bar(const Tile &t) { const Data *d = data_of(t); return cleaning(t) && d && d->progress >= 0; }
inline bool has_battery(const Tile &t) { return std::isfinite(t.battery); }
inline int header_h(const Tile &t, const Metrics &m, bool stacked) {
  return line_of(m.big) + (stacked && has_battery(t) ? ui::px(4) + line_of(m.text) : 0) + (has_line(t) ? ui::px(4) + line_of(m.text) : 0) +
         (has_bar(t) ? ui::px(12) : 0);
}
// The header as wide as its longest words need: the state, the battery and the card's padding.
inline int header_need(const Tile &t, const Metrics &m) {
  const int battery = has_battery(t) ? vacuum_power(nullptr, t, 0, 0, m.text, m.large) : 0;
  int words = text_width(headline(t), m.big);
  for (auto id : {txt::ha_vacuum_cleaning, txt::ha_vacuum_returning, txt::ha_vacuum_docked}) words = std::max(words, text_width(tr(id), m.big));
  return 2 * m.in + ui::px(20) + words + ui::px(12) + battery;
}
inline void line_paint(lv_obj_t *o, const Tile &t, const CardPart &part) {
  label(o, detail_line(t, static_cast<int>(part.arg), lv_obj_get_style_text_font(o, LV_PART_MAIN)));
}
inline void bar_paint(lv_obj_t *o, const Tile &t, const CardPart &part) {
  const Data *d = data_of(t);
  set_number(o, LV_STYLE_WIDTH, std::max<int>(ui::px(4), static_cast<int>(part.arg) * (d ? std::max(0, d->progress) : 0) / 100));
}
inline void header(lv_obj_t *parent, const Tile &t, int x, int y, int w, const Metrics &m, bool stacked) {
  const VacuumLook look = vacuum_look(t.state);
  const int dot = ui::px(m.large ? 10 : 8), battery = has_battery(t) ? vacuum_power(nullptr, t, 0, 0, m.text, m.large) : 0;
  // The state's colour, as Home Assistant colours a vacuum: red on an error, grey while it is not there.
  const uint32_t colour = t.state == "error" ? theme::foreground(theme::ha::RED) : !t.available() ? theme::hex(theme::OFF) : look.accent;
  detail_shape(parent, x, y + (line_of(m.big) - dot) / 2, dot, dot, colour, dot / 2);
  const int tx = x + dot + ui::px(10), tw = x + w - tx;
  detail_badge_status = card_bind(detail_text(parent, headline(t), tx, y, stacked || !battery ? tw : tw - battery - ui::px(12), m.big,
                                              LV_TEXT_ALIGN_LEFT, theme::INK), t, headline_paint);
  int ly = y + line_of(m.big);
  if (battery) {
    if (stacked) { ly += ui::px(4); vacuum_power(parent, t, tx, ly, m.text, m.large); ly += line_of(m.text); }
    else vacuum_power(parent, t, x + w - battery, y + (line_of(m.big) - line_of(m.text)) / 2, m.text, m.large);
  }
  if (has_line(t)) {
    ly += ui::px(4);
    card_bind(detail_text(parent, "", tx, ly, tw, m.text, LV_TEXT_ALIGN_LEFT, theme::MUTED), t, line_paint, "", tw);
    ly += line_of(m.text);
  }
  if (has_bar(t)) {
    ly += ui::px(8);
    const int bar = ui::px(4);
    detail_shape(parent, tx, ly, tw, bar, theme::TRACK, bar / 2);
    card_bind(detail_shape(parent, tx, ly, bar, bar, theme::foreground(theme::ha::TEAL), bar / 2), t, bar_paint, "", tw);
  }
}

// The map's picture: what the store has for the card's key, else the one it showed until the next is here.
inline std::string map_look(const MapAsk &a) {
  char tail[48];
  snprintf(tail, sizeof(tail), "|%dx%d|%06X|%d", a.w, a.h, (unsigned) a.ground, a.dark ? 1 : 0);
  return a.entity + tail;
}
inline std::string map_key(const MapAsk &a) { return "vmap|" + a.mark + "|" + map_look(a); }
inline void map_paint(lv_obj_t *o, const Tile &, const CardPart &) {
#if LV_USE_IMAGE
  if (!map_ask.valid()) return;
  const std::string key = map_key(map_ask);
  auto *src = picture_of(key);
  // Until the robot's next map is here the card keeps the one it shows, of the same size and look only: after a change
  // of look or size the old one would be the wrong picture (a dark map on a light card).
  const std::string look = "|" + map_look(map_ask);
  const bool same_look = map_shown.size() > look.size() && map_shown.compare(map_shown.size() - look.size(), look.size(), look) == 0;
  if (!src && same_look) src = picture_of(map_shown);
  else if (src && map_shown != key) { if (!map_shown.empty()) picture_retire(map_shown); map_shown = key; }
  if (src && lv_image_get_src(o) != src) { lv_image_set_src(o, src); lv_obj_invalidate(o); }
  set_hidden(o, !src);
  if (map_spinner) set_hidden(map_spinner, src || map_missing == key);
#else
  (void) o;
#endif
}
// The drawn robot of the lite card, for a robot without a map or a board without pictures.
inline void robot_drawing(lv_obj_t *parent, const Tile &t, int x, int y, int size) { vacuum_robot(parent, x, y, size, vacuum_look(t.state)); }

// The hero card: the header over the map (beside it on low glass), or the drawn robot beside the header.
inline int robot_size(const Metrics &m) { return ui::px(m.large ? 84 : 56); }
inline int map_aspect_h(int w) { return w * 10 / 22; }  // until the map's own shape is known, a robot's map is wide
inline int hero_natural(const Tile &t, const Metrics &m, int w) {
  if (!shows_map(t)) return 2 * m.in + std::max(robot_size(m), header_h(t, m, true));
  // Worked out for the robot at rest: the lines that come while it cleans take their room from the map.
  return 2 * m.in + line_of(m.big) + ui::px(12) + map_aspect_h(w - 2 * m.in);
}
inline int hero_least(const Tile &t, const Metrics &m) {
  if (!shows_map(t)) return 2 * m.in + std::max(ui::px(48), header_h(t, m, true));
  return 2 * m.in + line_of(m.big) + ui::px(12) + ui::mm(16);
}
inline void hero(const Tile &t, int x, int y, int w, int h, const Metrics &m, bool side) {
  auto *card = detail_card(x, y, w, h);
  const int iw = w - 2 * m.in, ih = h - 2 * m.in;
  if (!shows_map(t)) {
    const int d = std::min(robot_size(m), ih);
    robot_drawing(card, t, m.in, m.in + (ih - d) / 2, d);
    const int hx = m.in + d + ui::px(16), hh = header_h(t, m, true);
    header(card, t, hx, m.in + (ih - hh) / 2, w - hx - m.in, m, true);
    return;
  }
  int mx = m.in, my, mw = iw, mh;
  if (side) {  // low glass: the header at the left, the map beside it
    const int hw = std::min(iw * 11 / 20, std::max(header_need(t, m) - 2 * m.in, ui::px(26) + text_width(detail_line(t, iw, m.text), m.text)));
    const int hh = header_h(t, m, true);
    header(card, t, m.in, m.in + (ih - hh) / 2, hw, m, true);
    mx = m.in + hw + ui::px(12); mw = iw - hw - ui::px(12); my = m.in; mh = ih;
  } else {
    header(card, t, m.in, m.in, iw, m, false);
    my = m.in + header_h(t, m, false) + ui::px(12); mh = h - my - m.in;
  }
  if (mw < 16 || mh < 16) return;
  const Data *d = data_of(t);
  map_ask = MapAsk{t.entity, d->map_entity, d->map_mark, mw, mh, theme::hex(theme::CARD), theme::dark};
#if LV_USE_IMAGE
  const int size = ui::px(m.large ? 40 : 28);
  map_spinner = spinner_create(card, size, ui::px(m.large ? 4 : 3));
  if (map_spinner) lv_obj_set_pos(map_spinner, mx + (mw - size) / 2, my + (mh - size) / 2);
  map_picture = lv_image_create(card);
  lv_obj_remove_flag(map_picture, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_pos(map_picture, mx, my);
  lv_obj_add_flag(map_picture, LV_OBJ_FLAG_HIDDEN);
  card_bind(map_picture, t, map_paint);
#endif
}

// The keys under the robot: the first in blue, the second beside it, Locate as a round key at the end when there is
// room (Home Assistant keeps it with the commands).
struct KeyLook { const char *icon; std::string words; };
inline KeyLook look_of(Key k) {
  switch (k) {
    case Key::START: return {ICON_PLAY, tr(txt::vacuum_clean)};
    case Key::RESUME: return {ICON_PLAY, tr(txt::vacuum_resume)};
    case Key::PAUSE: return {ICON_PAUSE, tr(txt::vacuum_pause)};
    case Key::STOP: return {ICON_STOP, tr(txt::vacuum_stop)};
    case Key::DOCK: return {ICON_DOCK, tr(txt::vacuum_dock)};
    default: return {"", ""};
  }
}
inline std::string start_words(const Tile &t, bool counted) {
  const Key k = vacuum_model::first_key(t.state, can_of(t));
  if (k == Key::START && counted && !picks.empty()) return tr(txt::vacuum_clean) + std::string(" (") + std::to_string(picks.size()) + ")";
  return look_of(k).words;
}
inline int key_need(const std::string &words, const Metrics &m) { return text_width(ICON_PLAY, m.icons) + ui::px(8) + text_width(words, m.text) + 2 * ui::px(14); }
inline int keys_side_need(const Tile &t, const Metrics &m, bool counted) {
  const Key second = vacuum_model::second_key(t.state, can_of(t));
  return key_need(start_words(t, counted), m) + (second != Key::NONE ? m.gap + key_need(look_of(second).words, m) : 0);
}
inline bool locate_in_row(const Tile &t, int w, const Metrics &m, bool counted) {
  return can_of(t).locate && w >= keys_side_need(t, m, counted) + m.gap + m.action_h;
}
inline int keys_least(const Tile &t, const Metrics &m, bool counted) {
  return key_need(start_words(t, counted), m) + (vacuum_model::second_key(t.state, can_of(t)) != Key::NONE ? m.gap + m.action_h : 0);
}
// The first key's words follow the picks ("Clean (2)"): the words and the icon in front of them centred again as one
// group, as vacuum_command placed them (its words are the key's first child, the icon its second).
inline void key_words_paint(lv_obj_t *key, const std::string &words) {
  auto *text = lv_obj_get_child(key, 0), *icon = lv_obj_get_child(key, 1);
  if (!text || !icon || words == lv_label_get_text(text)) return;
  const lv_font_t *font = lv_obj_get_style_text_font(text, LV_PART_MAIN), *icons = lv_obj_get_style_text_font(icon, LV_PART_MAIN);
  const int w = lv_obj_get_width(key), h = lv_obj_get_height(key), gap = std::max(6, h / 7);
  const int icon_w = text_width(lv_label_get_text(icon), icons), words_w = text_width(words, font), left = std::max(4, (w - icon_w - gap - words_w) / 2);
  label(text, words);
  lv_obj_set_width(text, std::min(w - left - icon_w - gap - 4, words_w + 2));
  lv_obj_align(icon, LV_ALIGN_LEFT_MID, left, 0);
  lv_obj_align(text, LV_ALIGN_LEFT_MID, left + icon_w + gap, 0);
}
inline void start_paint(lv_obj_t *o, const Tile &t, const CardPart &part) { key_words_paint(o, start_words(t, part.arg != 0)); }
inline void keys(const Tile &t, int x, int y, int w, const Metrics &m, bool counted) {
  const Key first = vacuum_model::first_key(t.state, can_of(t)), second = vacuum_model::second_key(t.state, can_of(t));
  const int radius = m.large ? m.radius : m.action_h / 2;
  if (locate_in_row(t, w, m, counted)) {
    auto *k = key_obj(x + w - m.action_h, y, m.action_h, m.action_h, CMD_LOCATE, theme::hex(theme::TRACK), m.action_h / 2);
    lv_obj_set_style_bg_color(k, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
    glyph_centred(k, ICON_LOCATE, 0, 0, m.action_h, m.action_h, m.icons, theme::hex(theme::SLATE));
    w -= m.action_h + m.gap;
  }
  if (first == Key::NONE) return;
  const KeyLook a = look_of(first);
  if (second == Key::NONE) {
    auto *k = vacuum_command(a.icon, start_words(t, counted).c_str(), x, y, w, m.action_h, CMD_FIRST, true, m.text, m.icons, radius);
    card_bind(k, t, start_paint, "", counted);
    hits.push_back({CMD_FIRST, k});
    return;
  }
  const KeyLook b = look_of(second);
  int fw = std::max((w - m.gap) * 3 / 5, key_need(start_words(t, counted), m));
  if (w - fw - m.gap < key_need(b.words, m)) fw = std::max(key_need(start_words(t, counted), m), w - m.gap - key_need(b.words, m));
  const bool words = w - fw - m.gap >= key_need(b.words, m);
  if (!words) fw = w - m.gap - m.action_h;
  auto *k = vacuum_command(a.icon, start_words(t, counted).c_str(), x, y, fw, m.action_h, CMD_FIRST, true, m.text, m.icons, radius);
  card_bind(k, t, start_paint, "", counted);
  hits.push_back({CMD_FIRST, k});
  if (words) hits.push_back({CMD_SECOND, vacuum_command(b.icon, b.words.c_str(), x + fw + m.gap, y, w - fw - m.gap, m.action_h, CMD_SECOND, false, m.text, m.icons, radius)});
  else {
    auto *d = key_obj(x + fw + m.gap, y, w - fw - m.gap, m.action_h, CMD_SECOND, theme::hex(theme::CARD), radius);
    lv_obj_set_style_border_width(d, 1, 0); lv_obj_set_style_border_color(d, theme::color(theme::LINE), 0);
    lv_obj_set_style_bg_color(d, theme::color(theme::KEY), LV_STATE_PRESSED);
    glyph_centred(d, b.icon, 0, 0, w - fw - m.gap, m.action_h, m.icons, theme::hex(theme::INK));
  }
}

// A key that opens a view, as the effects row looks: the icon, the words, a chevron.
inline int page_key_need(const std::string &words, const Metrics &m) {
  return 2 * ui::px(16) + line_of(m.icons) + ui::px(12) + text_width(words, m.text) + ui::px(10) + text_width(ICON_CHEVRON, m.icons);
}
inline void page_key(int x, int y, int w, int h, const char *icon, const std::string &words, int cmd, const Metrics &m) {
  auto *k = key_obj(x, y, w, h, cmd, theme::hex(theme::CARD), m.radius);
  lv_obj_set_style_border_width(k, 1, 0); lv_obj_set_style_border_color(k, theme::color(theme::LINE), 0);
  lv_obj_set_style_bg_color(k, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
  const int e = ui::px(16), iw = line_of(m.icons), cw = text_width(ICON_CHEVRON, m.icons);
  glyph(k, icon, e, (h - iw) / 2, m.icons, theme::hex(theme::ROW_ICON));
  detail_text(k, words, e + iw + ui::px(12), (h - line_of(m.text)) / 2, w - 2 * e - iw - ui::px(12) - cw - ui::px(10), m.text, LV_TEXT_ALIGN_LEFT, theme::INK);
  glyph(k, ICON_CHEVRON, w - e - cw, (h - iw) / 2, m.icons, theme::hex(theme::CHEVRON));
}

// Suction and water: the lite card's rows (mode, suction, water), the ones the chosen mode uses.
struct HowRows { const Choice *mode, *suction, *water; bool automatic; };
inline HowRows how_rows(const Tile &t) {
  const uint32_t now = esphome::millis();
  const auto rows = tile_controls::vacuum_rows(t, now);
  const Choice *mode = t.choice('m');
  return {mode, rows.suction ? t.choice('s') : nullptr, rows.water ? t.choice('w') : nullptr, mode && tile_controls::vacuum_role(t, now) == 'a'};
}
inline int level_h(const Metrics &m) { return std::max(ui::touch_min() * 3 / 4, ui::px(m.large ? 44 : 32)); }
inline int how_h(const Tile &t, const Metrics &m) {
  const HowRows r = how_rows(t);
  const int step = ui::px(m.large ? 10 : 6);
  int h = 2 * ui::px(m.large ? 14 : 8), n = 0;
  if (r.mode) { h += m.chip_h; ++n; }
  if (r.suction) { h += level_h(m); ++n; }
  if (r.water) { h += level_h(m); ++n; }
  if (r.automatic) { h += line_of(m.text); ++n; }
  return h + std::max(0, n - 1) * step;
}
inline int segments_need(const Choice *c, const Metrics &m) {
  if (!c) return 0;
  int w = 0;
  for (const auto &l : c->labels) w += text_width(l, small_font ? small_font : m.text) + ui::px(14);
  return w;
}
inline int how_need(const Tile &t, const Metrics &m) {
  const HowRows r = how_rows(t);
  const int icon_w = ui::px(m.large ? 40 : 26);
  return 2 * ui::px(m.large ? 14 : 8) + std::max({segments_need(r.mode, m), r.suction ? icon_w + segments_need(r.suction, m) : 0,
                                                   r.water ? icon_w + segments_need(r.water, m) : 0});
}
inline void how(const Tile &t, int x, int y, int w, const Metrics &m) {
  const HowRows r = how_rows(t);
  detail_card(x, y, w, how_h(t, m));
  const int e = ui::px(m.large ? 14 : 8), step = ui::px(m.large ? 10 : 6), icon_w = ui::px(m.large ? 40 : 26), lh = level_h(m);
  const uint32_t track = theme::hex(theme::TRACK);
  int cx = x + e, cw = w - 2 * e, cy = y + e;
  if (r.mode) { vacuum_segments(t, *r.mode, 50, cx, cy, cw, m.chip_h, track, false, m.text); cy += m.chip_h + step; }
  auto level = [&](const Choice &row, int first, const char *icon) {
    detail_text(detail_root, icon, cx, cy + (lh - line_of(m.icons)) / 2, icon_w, m.icons, LV_TEXT_ALIGN_LEFT, theme::SUBTLE);
    vacuum_segments(t, row, first, cx + icon_w, cy, cw - icon_w, lh, track, false, m.text);
    cy += lh + step;
  };
  if (r.suction) level(*r.suction, 10, "\U000F0210");
  if (r.water) level(*r.water, 60, "\U000F058C");
  if (r.automatic) {
    const bool smart = tile_controls::shown_value(t, *r.mode, esphome::millis()).find("smart") != std::string::npos;
    detail_text(detail_root, tr(smart ? txt::vacuum_robot_chooses : txt::vacuum_per_room), cx, cy, cw, m.text, LV_TEXT_ALIGN_CENTER, theme::SUBTLE);
  }
}

// Room chips: the room's icon and name; a picked one is blue, with its place in the order where the icon was.
inline int chip_cols(const Data &d, int w, const Metrics &m) {
  int widest = 0;
  for (const auto &r : d.rooms) widest = std::max(widest, text_width(r.name, m.text));
  const int need = widest + line_of(m.icons) + ui::px(8) + 2 * ui::px(14);
  for (int c = static_cast<int>(d.rooms.size()); c > 1; --c) if (c != 3 && (w - (c - 1) * ui::px(8)) / c >= need) return c;
  return 1;
}
inline int chips_rows(const Data &d, int w, const Metrics &m) { const int c = chip_cols(d, w, m); return (static_cast<int>(d.rooms.size()) + c - 1) / c; }
inline int chips_h(const Data &d, int w, const Metrics &m) { const int r = chips_rows(d, w, m); return r * m.chip_h + (r - 1) * ui::px(8); }
// A chip's parts, painted from the picks: the chip, its icon, its number's disc and number, its name.
inline void chip_paint(lv_obj_t *o, const Tile &, const CardPart &part) {
  const int at = vacuum_model::place(picks, static_cast<uint8_t>(part.arg));
  set_color(o, LV_STYLE_BG_COLOR, theme::color(at ? theme::ACCENT : theme::TRACK));
  if (auto *icon = lv_obj_get_child(o, 0)) set_hidden(icon, at != 0);
  if (auto *disc = lv_obj_get_child(o, 1)) {
    set_hidden(disc, at == 0);
    if (auto *n = lv_obj_get_child(disc, 0)) label(n, at ? std::to_string(at) : "");
  }
  if (auto *name = lv_obj_get_child(o, 2)) set_color(name, LV_STYLE_TEXT_COLOR, theme::color(at ? theme::ON_ACCENT : theme::INK));
}
inline void chips(const Tile &t, const Data &d, int x, int y, int w, const Metrics &m) {
  const int c = chip_cols(d, w, m), g = ui::px(8), cw = (w - (c - 1) * g) / c;
  for (size_t i = 0; i < d.rooms.size(); ++i) {
    const int cx = x + static_cast<int>(i % c) * (cw + g), cy = y + static_cast<int>(i / c) * (m.chip_h + g);
    auto *o = key_obj(cx, cy, cw, m.chip_h, CMD_PICK + static_cast<int>(i), theme::hex(theme::TRACK), m.chip_h / 2);
    lv_obj_set_style_bg_color(o, theme::color(theme::ACCENT_TINT), LV_STATE_PRESSED);
    const int iw = line_of(m.icons), ix = ui::px(14);
    glyph(o, room_glyph(d.rooms[i].icon, m.icons), ix, (m.chip_h - iw) / 2, m.icons, theme::hex(theme::MUTED));
    auto *disc = detail_shape(o, ix, (m.chip_h - iw) / 2, iw, iw, theme::ON_ACCENT, iw / 2);
    detail_text(disc, "", 0, (iw - line_of(m.small)) / 2, iw, m.small, LV_TEXT_ALIGN_CENTER, theme::ACCENT);
    detail_text(o, d.rooms[i].name, ix + iw + ui::px(8), (m.chip_h - line_of(m.text)) / 2, cw - ix - iw - ui::px(8) - ui::px(10), m.text, LV_TEXT_ALIGN_LEFT, theme::INK);
    card_bind(o, t, chip_paint, "", static_cast<intptr_t>(i));
  }
}
// The routines as rows: a play disc and the name; a tap runs one. `first` and `count` draw a part of them (a page of
// the routines view), in `cols` columns.
inline int routines_h(int count, const Metrics &m, int cols = 1) {
  const int rows = (count + cols - 1) / std::max(1, cols);
  return rows * (m.row_h + ui::px(8)) - ui::px(8);
}
inline int routines_h(const Data &d, const Metrics &m) { return routines_h(static_cast<int>(d.routines.size()), m); }
inline void routines(const Data &d, int x, int y, int w, const Metrics &m, size_t first = 0, size_t count = SIZE_MAX, int cols = 1) {
  const size_t end = std::min(d.routines.size(), count == SIZE_MAX ? d.routines.size() : first + count);
  const int g = ui::px(8), cw = (w - (cols - 1) * m.gap) / std::max(1, cols);
  for (size_t i = first; i < end; ++i) {
    const int slot = static_cast<int>(i - first), rx = x + (slot % cols) * (cw + m.gap), ry = y + (slot / cols) * (m.row_h + g);
    auto *k = key_obj(rx, ry, cw, m.row_h, CMD_ROUTINE + static_cast<int>(i), theme::hex(theme::CARD), m.radius);
    lv_obj_set_style_border_width(k, 1, 0); lv_obj_set_style_border_color(k, theme::color(theme::LINE), 0);
    lv_obj_set_style_bg_color(k, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
    const int disc = ui::px(m.large ? 36 : 28), e = ui::px(12);
    auto *circle = detail_shape(k, e, (m.row_h - disc) / 2, disc, disc, theme::tint(theme::ha::TEAL, 36), disc / 2);
    glyph_centred(circle, ICON_PLAY, 0, 0, disc, disc, m.small_icons, theme::foreground(theme::ha::TEAL));
    detail_text(k, d.routines[i].name, e + disc + ui::px(12), (m.row_h - line_of(m.text)) / 2, cw - 2 * e - disc - ui::px(12), m.text, LV_TEXT_ALIGN_LEFT, theme::INK);
  }
}
// The media library's pager: a round key either side, a dot per page between them.
inline void pager_key(int x, int y, int k, bool forward, bool off, const Metrics &m) {
  auto *key = key_obj(x, y, k, k, forward ? CMD_PAGE_ON : CMD_PAGE_BACK, theme::hex(theme::TRACK), k / 2);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  glyph_centred(key, forward ? ICON_CHEVRON : ICON_BACK, 0, 0, k, k, m.icons, theme::hex(theme::INK));
  if (off) lv_obj_add_state(key, LV_STATE_DISABLED);
}
inline void pager(int x, int y, int w, int k, int page_now, int pages, const Metrics &m) {
  const int dot = ui::px(8), dg = ui::px(10), dw = pages * dot + (pages - 1) * dg;
  pager_key(x, y, k, false, page_now == 0, m);
  pager_key(x + w - k, y, k, true, page_now >= pages - 1, m);
  for (int i = 0; i < pages; ++i)
    detail_shape(detail_root, x + w / 2 - dw / 2 + i * (dot + dg), y + (k - dot) / 2, dot, dot, i == page_now ? theme::INK : theme::TICK, dot / 2);
}
inline int heading_h(const Metrics &m) { return line_of(m.small) + ui::px(8); }
inline void heading(int x, int y, int w, const std::string &words, const Metrics &m) {
  detail_text(detail_root, words, x + ui::px(4), y, w - ui::px(8), m.small, LV_TEXT_ALIGN_LEFT, theme::MUTED);
}

// ---- The plan: the blocks under the hero, in order of importance, each on the card or as a key ----
struct Block { int h; int min_w; std::function<void(int x, int y, int w)> draw; };
struct Plan { bool rooms, how, routines; };
inline std::vector<Block> blocks(const Tile &t, const Metrics &m, const Plan &p, int w, bool with_keys) {
  std::vector<Block> out;
  const Data *d = data_of(t);
  const Tile *tp = &t;
  const Metrics mm = m;
  if (with_keys) out.push_back({m.action_h, keys_least(t, m, p.rooms), [tp, mm, p](int x, int y, int bw) { keys(*tp, x, y, bw, mm, p.rooms); }});
  if (p.rooms && d) {
    // On the card only while every room fits in two rows of chips; else the view has them.
    const bool fits = chips_rows(*d, w, m) <= 2 && d->floors.size() < 2 && !d->rooms.empty();
    out.push_back({fits ? heading_h(m) + chips_h(*d, w, m) : 1 << 20, 0, [tp, d, mm](int x, int y, int bw) {
      heading(x, y, bw, tr(txt::vacuum_by_room), mm);
      chips(*tp, *d, x, y + heading_h(mm), bw, mm);
    }});
  }
  if (p.how) out.push_back({how_h(t, m), how_need(t, m), [tp, mm](int x, int y, int bw) { how(*tp, x, y, bw, mm); }});
  if (p.routines && d) out.push_back({heading_h(m) + routines_h(*d, m), 0, [d, mm](int x, int y, int bw) {
      heading(x, y, bw, tr(txt::vacuum_routines), mm);
      routines(*d, x, y + heading_h(mm), bw, mm);
    }});
  // The keys to the views of what is not on the card: side by side when both fit, else one above the other.
  std::vector<std::pair<const char *, int>> k;
  if (by_room(t) && !p.rooms) k.push_back({ICON_ROOMS, CMD_ROOMS});
  if (has_routines(t) && !p.routines) k.push_back({ICON_ROUTINES, CMD_ROUTINES});
  auto words = [](int cmd) { return std::string(tr(cmd == CMD_ROOMS ? txt::vacuum_by_room : txt::vacuum_routines)); };
  int need = 0;
  for (auto &e : k) need = std::max(need, page_key_need(words(e.second), m));
  if (k.size() == 1 || (k.size() == 2 && w >= 2 * need + m.gap)) {
    if (!k.empty()) out.push_back({m.key_h, need, [k, mm, words](int x, int y, int bw) {
        const int n = static_cast<int>(k.size()), kw = (bw - (n - 1) * mm.gap) / n;
        for (int i = 0; i < n; ++i) page_key(x + i * (kw + mm.gap), y, kw, mm.key_h, k[i].first, words(k[i].second), k[i].second, mm);
      }});
  } else {
    for (auto &e : k) out.push_back({m.key_h, need, [e, mm, words](int x, int y, int bw) { page_key(x, y, bw, mm.key_h, e.first, words(e.second), e.second, mm); }});
  }
  return out;
}
inline int stack_h(const std::vector<Block> &v, int gap) { int h = 0; for (auto &b : v) h += b.h + gap; return v.empty() ? 0 : h - gap; }
inline bool fits_w(const std::vector<Block> &v, int w) { for (auto &b : v) if (b.min_w > w) return false; return true; }
// From the richest plan to the plainest, only with what the robot has.
inline std::vector<Plan> plans(const Tile &t) {
  static const Plan all[] = {{1, 1, 1}, {1, 1, 0}, {1, 0, 1}, {1, 0, 0}, {0, 1, 1}, {0, 1, 0}, {0, 0, 1}, {0, 0, 0}};
  std::vector<Plan> out;
  for (Plan p : all) {
    p.rooms = p.rooms && by_room(t) && data_of(t) && !data_of(t)->rooms.empty();
    p.how = p.how && has_how(t);
    p.routines = p.routines && has_routines(t);
    bool seen = false;
    for (auto &q : out) seen = seen || (q.rooms == p.rooms && q.how == p.how && q.routines == p.routines);
    if (!seen) out.push_back(p);
  }
  return out;
}
// The keys at the right of the top bar: Locate when the row has no room for it, the view of suction and water when
// the card has no room for them.
struct BarKeys { bool locate = false, how = false; };

// Square and standing glass: one column a hand wide. The map keeps its natural height or half the room, whichever is
// less; a drawn robot may shrink to its least.
inline BarKeys one_column(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  const int keep = shows_map(t) ? std::max(hero_least(t, m), std::min(hero_natural(t, m, w), h / 2)) : hero_least(t, m);
  for (const Plan &p : plans(t)) {
    auto v = blocks(t, m, p, w, true);
    const int rest = stack_h(v, m.gap) + m.gap;
    if (h - rest < keep || !fits_w(v, w)) continue;
    const int hh = std::min(hero_natural(t, m, w), h - rest), total = hh + rest;
    int cy = y + (h - total) / 2;
    hero(t, x, cy, w, hh, m, false);
    cy += hh + m.gap;
    for (auto &b : v) { b.draw(x, cy, w); cy += b.h + m.gap; }
    return {can_of(t).locate && !locate_in_row(t, w, m, p.rooms), has_how(t) && !p.how};
  }
  // Nothing fits (a very short glass): the hero and the keys.
  hero(t, x, y, w, std::max(hero_least(t, m), h - m.action_h - m.gap), m, false);
  keys(t, x, y + h - m.action_h, w, m, false);
  return {can_of(t).locate && !locate_in_row(t, w, m, false), has_how(t)};
}
// Low landscape glass (under 36 mm for the content): the hero across the width with the state beside the map, and one
// row of keys under it, each an icon over its word: the robot's keys and the views.
inline bool low(int h) { return h < ui::mm(36); }
inline BarKeys low_glass(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  struct K { const char *icon; std::string words; int cmd; bool primary; };
  std::vector<K> ks;
  const Key first = vacuum_model::first_key(t.state, can_of(t)), second = vacuum_model::second_key(t.state, can_of(t));
  if (first != Key::NONE) ks.push_back({look_of(first).icon, look_of(first).words, CMD_FIRST, true});
  if (second != Key::NONE) ks.push_back({look_of(second).icon, look_of(second).words, CMD_SECOND, false});
  if (by_room(t)) ks.push_back({ICON_ROOMS, tr(txt::vacuum_by_room), CMD_ROOMS, false});
  if (has_routines(t)) ks.push_back({ICON_ROUTINES, tr(txt::vacuum_routines), CMD_ROUTINES, false});
  const int kh = std::max(ui::touch_min(), ui::px(12) + line_of(m.icons) + ui::px(2) + line_of(m.small) + ui::px(10));
  hero(t, x, y, w, h - kh - m.gap, m, true);
  const int n = static_cast<int>(ks.size());
  if (!n) return {can_of(t).locate, has_how(t)};
  std::vector<int> ws;
  int sum = 0;
  for (auto &k : ks) { ws.push_back(text_width(k.words, m.small) + ui::px(16)); sum += ws.back(); }
  const int extra = std::max(0, (w - (n - 1) * m.gap - sum) / n);
  int kx = x;
  for (int i = 0; i < n; ++i) {
    const int kw = i == n - 1 ? x + w - kx : ws[i] + extra;
    auto *k = key_obj(kx, y + h - kh, kw, kh, ks[i].cmd, theme::hex(ks[i].primary ? theme::ACCENT : theme::CARD), m.radius);
    if (!ks[i].primary) { lv_obj_set_style_border_width(k, 1, 0); lv_obj_set_style_border_color(k, theme::color(theme::LINE), 0);
                          lv_obj_set_style_bg_color(k, theme::color(theme::KEY), LV_STATE_PRESSED); }
    else lv_obj_set_style_bg_color(k, theme::color(theme::ACCENT_PRESSED), LV_STATE_PRESSED);
    const uint32_t c = theme::hex(ks[i].primary ? theme::ON_ACCENT : theme::INK);
    const int top = (kh - line_of(m.icons) - ui::px(2) - line_of(m.small)) / 2;
    glyph_centred(k, ks[i].icon, 0, top, kw, line_of(m.icons), m.icons, c);
    detail_text(k, ks[i].words, ui::px(4), top + line_of(m.icons) + ui::px(2), kw - ui::px(8), m.small, LV_TEXT_ALIGN_CENTER, c);
    kx += kw + m.gap;
  }
  return {can_of(t).locate, has_how(t)};
}
// Landscape glass: the hero at the left, the blocks at the right; a block that doesn't fit at the right goes under the
// hero when there is room. Start and Dock go under both columns when the right column is too narrow for them.
inline BarKeys two_columns(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  const int g = ui::mm(5);
  const bool bottom = w * 42 / 100 < keys_side_need(t, m, true);
  const int colh = h - (bottom ? m.action_h + m.gap : 0);
  // Sized for the robot at rest, so nothing moves when it starts; never narrower than its header needs.
  const int want = (colh - 2 * m.in - line_of(m.big) - ui::px(12)) * 22 / 10 + 2 * m.in;
  int lw = std::max(std::clamp(want, w * 45 / 100, w * 62 / 100), header_need(t, m));
  // The right column keeps room for what must stand there: the keys (unless they go under both) and the keys to the
  // views. The map gives way first.
  int need = bottom ? 0 : keys_least(t, m, true);
  if (by_room(t)) need = std::max(need, page_key_need(tr(txt::vacuum_by_room), m));
  if (has_routines(t)) need = std::max(need, page_key_need(tr(txt::vacuum_routines), m));
  lw = std::max(w * 40 / 100, std::min(lw, w - g - need));
  const int rw = std::min(w - lw - g, ui::control_max_width());
  lw = w - rw - g;
  const int rx = x + lw + g, hh = std::min(colh, hero_natural(t, m, lw));
  for (const Plan &p : plans(t)) {
    auto v = blocks(t, m, p, rw, !bottom);
    int ry = 0, ly = hh + m.gap;
    bool ok = true;
    struct At { size_t i; int x, y, w; };
    std::vector<At> at;
    for (size_t i = 0; i < v.size(); ++i) {
      if (ry + v[i].h <= colh && v[i].min_w <= rw) { at.push_back({i, rx, ry, rw}); ry += v[i].h + m.gap; }
      else if (ly + v[i].h <= colh && v[i].min_w <= lw) { at.push_back({i, x, ly, lw}); ly += v[i].h + m.gap; }
      else { ok = false; break; }
    }
    if (!ok) continue;
    const int used = std::max({ry - m.gap, hh, ly - m.gap}), dy = y + (colh - used) / 2;
    hero(t, x, dy, lw, hh, m, false);
    for (auto &a : at) v[a.i].draw(a.x, dy + a.y, a.w);
    if (bottom) keys(t, x, y + h - m.action_h, w, m, p.rooms);
    return {can_of(t).locate && !locate_in_row(t, bottom ? w : rw, m, p.rooms), has_how(t) && !p.how};
  }
  // Nothing fits (very short glass): the hero, the keys and the keys to the views, one above the other.
  hero(t, x, y, lw, colh, m, false);
  int ky = y;
  if (!bottom) { keys(t, rx, ky, rw, m, false); ky += m.action_h + m.gap; }
  else keys(t, x, y + h - m.action_h, w, m, false);
  for (auto &b : blocks(t, m, Plan{false, false, false}, rw, false))
    if (ky + b.h <= y + colh) { b.draw(rx, ky, rw); ky += b.h + m.gap; }
  return {can_of(t).locate, has_how(t)};
}
inline bool landscape() { return overlay_card::screen_width() * 10 >= overlay_card::screen_height() * 14; }
inline int content_top(const Metrics &m) { return detail_bar::bottom() + ui::px(m.large ? 16 : 8); }
// Whether the card takes the whole glass (a picture's frame, overlay_card): landscape glass with a map, or low glass.
bool wide(const Tile &t) {
  if (!landscape()) return false;
  const Metrics m = metrics();
  return shows_map(t) || low(overlay_card::screen_height() - content_top(m) - m.pad);
}

// ---- The views ----
// The rooms view: Home Assistant's clean by area. A key per floor when the rooms are on more than one; the rooms as
// tiles as large as the room allows (standing: a disc over the name; lying: the disc beside it); the media library's
// pages only when they don't all fit; Home Assistant's empty state when no area is linked yet.
inline void tile_paint(lv_obj_t *o, const Tile &, const CardPart &part) {
  const int at = vacuum_model::place(picks, static_cast<uint8_t>(part.arg));
  set_color(o, LV_STYLE_BG_COLOR, theme::color(at ? theme::ACCENT_TINT : theme::CARD));
  set_number(o, LV_STYLE_BORDER_WIDTH, at ? ui::px(2) : 1);
  set_color(o, LV_STYLE_BORDER_COLOR, theme::color(at ? theme::ACCENT : theme::LINE));
  if (auto *disc = lv_obj_get_child(o, 0)) {
    set_color(disc, LV_STYLE_BG_COLOR, theme::color(at ? theme::ACCENT : theme::TRACK));
    if (auto *icon = lv_obj_get_child(disc, 0)) set_hidden(icon, at != 0);
    if (auto *n = lv_obj_get_child(disc, 1)) { set_hidden(n, at == 0); label(n, at ? std::to_string(at) : ""); }
  }
}
inline void rooms_start_paint(lv_obj_t *o, const Tile &, const CardPart &) {
  paint_state(o, LV_STATE_DISABLED, picks.empty());
  key_words_paint(o, picks.empty() ? std::string(tr(txt::vacuum_clean)) : tr(txt::vacuum_clean) + std::string(" (") + std::to_string(picks.size()) + ")");
}
inline void hint_paint(lv_obj_t *o, const Tile &, const CardPart &) { label(o, tr(picks.empty() ? txt::vacuum_pick_rooms : txt::vacuum_order_hint)); }
inline void rooms_view(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  const Data *d = data_of(t);
  if (!d || d->rooms.empty()) {
    // Home Assistant's own words when nothing is linked yet.
    const int disc = ui::px(m.large ? 64 : 44), cw = std::min(w, ui::control_max_width());
    const int total = disc + ui::px(16) + line_of(m.big) + ui::px(10) + 2 * line_of(m.text);
    int cy = y + std::max(0, (h - total) / 2);
    auto *c = detail_shape(detail_root, x + (w - disc) / 2, cy, disc, disc, theme::TRACK, disc / 2);
    glyph_centred(c, ICON_ROOMS, 0, 0, disc, disc, m.icons, theme::hex(theme::SLATE));
    cy += disc + ui::px(16);
    detail_text(detail_root, tr(txt::vacuum_no_rooms), x + (w - cw) / 2, cy, cw, m.big, LV_TEXT_ALIGN_CENTER, theme::INK);
    cy += line_of(m.big) + ui::px(10);
    auto *note = detail_text(detail_root, tr(txt::vacuum_no_rooms_how), x + (w - cw) / 2, cy, cw, m.text, LV_TEXT_ALIGN_CENTER, theme::MUTED);
    lv_label_set_long_mode(note, LV_LABEL_LONG_WRAP);
    lv_obj_set_height(note, 2 * line_of(m.text));
    return;
  }
  const int g = m.gap, cw = std::min(w, ui::control_max_width() * 4 / 3);
  const bool floors = d->floors.size() > 1;
  floor = std::clamp(floor, 0, std::max(0, static_cast<int>(d->floors.size()) - 1));
  const auto list = vacuum_model::on_floor(*d, floor);
  const int n = static_cast<int>(list.size()), fh = floors ? m.chip_h + g : 0;
  int widest = 0;
  for (uint8_t i : list) widest = std::max(widest, text_width(d->rooms[i].name, m.text));
  const int disc = ui::px(m.large ? 52 : 36), tall = ui::px(18) + disc + ui::px(10) + line_of(m.text) + ui::px(18);
  const bool tight = h < ui::mm(40);  // low glass: no hint, and the pager's keys sit either side of Start
  const int hint = tight ? 0 : line_of(m.small) + ui::px(14), below = ui::px(10) + hint + m.action_h;
  const int pager_h = tight ? 0 : std::max(ui::touch_min(), ui::px(m.large ? 44 : 34));
  struct Grid { bool up; int cols, tw, rows, per; bool paged; };
  auto lay = [&](bool up) {
    Grid gr{up, 1, 0, 1, 1, false};
    const int th = up ? tall : m.key_h;
    const int fit = up ? std::min(4, (cw + g) / (std::max(widest + ui::px(24), ui::px(120)) + g)) : std::min(3, (cw + g) / (widest + ui::px(84) + g));
    gr.cols = vacuum_model::even_columns(n, std::max(1, fit));
    gr.tw = std::min(up ? ui::px(200) : ui::px(300), (cw - (gr.cols - 1) * g) / gr.cols);
    int room = h - fh - below;
    gr.rows = std::max(1, (room + g) / (th + g));
    if (gr.rows * gr.cols < n) { gr.paged = true; room -= pager_h + (tight ? 0 : g); gr.rows = std::max(1, (room + g) / (th + g)); }
    gr.rows = std::min(gr.rows, (n + gr.cols - 1) / gr.cols);
    gr.per = gr.rows * gr.cols;
    return gr;
  };
  Grid gr = lay(true);
  if (gr.paged || gr.per < std::min(n, 4)) gr = lay(false);
  const int th = gr.up ? tall : m.key_h, gw = gr.cols * gr.tw + (gr.cols - 1) * g, gh = gr.rows * th + (gr.rows - 1) * g;
  const int total = fh + gh + (gr.paged && !tight ? g + pager_h : 0) + below;
  int cy = y + std::max(0, (h - total) / 2);
  const int x0 = x + (w - gw) / 2;
  if (floors) {
    const int fw = std::max(gw, std::min(cw, ui::px(420)));
    // The floors as the lite card's chips: one track, the chosen one blue.
    Choice row; row.kind = 'f';
    for (size_t i = 0; i < d->floors.size(); ++i) { row.values.push_back(std::to_string(i)); row.labels.push_back(d->floors[i].empty() ? "?" : d->floors[i]); }
    segments(x + (w - fw) / 2, cy, fw, m.chip_h, row.labels, floor, CMD_FLOOR, theme::hex(theme::TRACK), false, m.text, small_font);
    cy += fh;
  }
  const int pages = vacuum_model::pages(n, gr.per);
  page = std::clamp(page, 0, pages - 1);
  const int first = page * gr.per;
  for (int k = first; k < std::min(n, first + gr.per); ++k) {
    const uint8_t i = list[k];
    const int slot = k - first, tx = x0 + (slot % gr.cols) * (gr.tw + g), ty = cy + (slot / gr.cols) * (th + g);
    auto *o = key_obj(tx, ty, gr.tw, th, CMD_PICK + i, theme::hex(theme::CARD), m.radius);
    lv_obj_set_style_border_width(o, 1, 0); lv_obj_set_style_border_color(o, theme::color(theme::LINE), 0);
    lv_obj_set_style_bg_color(o, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
    const int dd = gr.up ? disc : ui::px(m.large ? 36 : 28);
    const int dx = gr.up ? (gr.tw - dd) / 2 : ui::px(12), dy = gr.up ? ui::px(18) : (th - dd) / 2;
    auto *c = detail_shape(o, dx, dy, dd, dd, theme::TRACK, dd / 2);
    const lv_font_t *icon_font = gr.up ? m.icons : m.small_icons, *number_font = gr.up ? m.big : m.small;
    auto *g1 = glyph(c, room_glyph(d->rooms[i].icon, icon_font), 0, 0, icon_font, theme::hex(theme::SLATE));
    lv_obj_align(g1, LV_ALIGN_CENTER, 0, 0);
    auto *num = detail_text(c, "", 0, (dd - line_of(number_font)) / 2, dd, number_font, LV_TEXT_ALIGN_CENTER, theme::ON_ACCENT);
    (void) num;
    if (gr.up) detail_text(o, d->rooms[i].name, ui::px(6), dy + dd + ui::px(10), gr.tw - ui::px(12), m.text, LV_TEXT_ALIGN_CENTER, theme::INK);
    else detail_text(o, d->rooms[i].name, dx + dd + ui::px(10), (th - line_of(m.text)) / 2, gr.tw - dx - dd - ui::px(20), m.text, LV_TEXT_ALIGN_LEFT, theme::INK);
    card_bind(o, t, tile_paint, "", i);
  }
  cy += gh;
  int bw = std::min(std::max(gw, ui::px(300)), std::min(w, ui::control_max_width()));
  int bx = x + (w - bw) / 2;
  if (gr.paged && !tight) {
    cy += g;
    pager(x0, cy, gw, pager_h, page, pages, m);
    cy += pager_h;
  }
  cy += ui::px(10);
  if (!tight) {
    card_bind(detail_text(detail_root, "", bx, cy, bw, m.small, LV_TEXT_ALIGN_CENTER, theme::SUBTLE), t, hint_paint);
    cy += hint;
  }
  if (gr.paged && tight) {
    pager_key(bx, cy, m.action_h, false, page == 0, m);
    pager_key(bx + bw - m.action_h, cy, m.action_h, true, page >= pages - 1, m);
    bx += m.action_h + g; bw -= 2 * (m.action_h + g);
  }
  auto *start = vacuum_command(ICON_PLAY, tr(txt::vacuum_clean), bx, cy, bw, m.action_h, CMD_CLEAN_ROOMS, true, m.text, m.icons, m.large ? m.radius : m.action_h / 2);
  card_bind(start, t, rooms_start_paint);
  hits.push_back({CMD_CLEAN_ROOMS, start});
}
// The routines view: every routine of the robot as a row, in two columns where the glass is wide enough for two rows
// side by side, and in pages, with the pager, when they don't all fit.
inline void routines_view(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  const Data *d = data_of(t);
  if (!d) return;
  const int n = static_cast<int>(d->routines.size());
  int widest = 0;
  for (const auto &r : d->routines) widest = std::max(widest, text_width(r.name, m.text));
  const int row_need = 2 * ui::px(12) + ui::px(m.large ? 36 : 28) + ui::px(12) + widest + ui::px(8);
  const int cw = std::min(w, ui::control_max_width() * 4 / 3);
  const int cols = n > 4 && cw >= 2 * std::max(row_need, ui::mm(55)) + m.gap ? 2 : 1;
  const int gw = cols == 2 ? cw : std::min(w, ui::control_max_width());
  const int note = ui::px(12) + line_of(m.small), pager_h = std::max(ui::touch_min(), ui::px(m.large ? 44 : 34));
  int rows = std::max(1, (h - note + ui::px(8)) / (m.row_h + ui::px(8)));
  bool paged = rows * cols < n;
  if (paged) rows = std::max(1, (h - note - pager_h - m.gap + ui::px(8)) / (m.row_h + ui::px(8)));
  const int per = rows * cols, pages = vacuum_model::pages(n, per);
  page = std::clamp(page, 0, pages - 1);
  const int shown = std::min(per, n - page * per), list_h = routines_h(paged ? per : shown, m, cols);
  const int total = list_h + (paged ? m.gap + pager_h : 0) + note;
  int cy = y + std::max(0, (h - total) / 2);
  const int cx = x + (w - gw) / 2;
  routines(*d, cx, cy, gw, m, static_cast<size_t>(page * per), static_cast<size_t>(per), cols);
  cy += list_h;
  if (paged) { cy += m.gap; pager(cx, cy, gw, pager_h, page, pages, m); cy += pager_h; }
  detail_text(detail_root, tr(txt::vacuum_routines_note), cx, cy + ui::px(12), gw, m.small, LV_TEXT_ALIGN_CENTER, theme::SUBTLE);
}
inline void how_view(const Tile &t, const Metrics &m, int x, int y, int w, int h) {
  const int cw = std::min(w, ui::control_max_width());
  how(t, x + (w - cw) / 2, y + std::max(0, (h - how_h(t, m)) / 2), cw, m);
}

// ---- The card ----
inline uint32_t card_shape(const Tile &t) {
  Fingerprint f;
  auto add = [&](const std::string &text) { f.add(text); f.write('|'); };
  add(t.entity); add(std::to_string(t.supported)); add(t.state); f.write(static_cast<uint8_t>('0' + view));
  add(std::to_string(floor)); add(std::to_string(page));
  add(std::isfinite(t.battery) ? std::to_string(static_cast<int>(std::lround(t.battery))) : "");
  f.write(t.extra().charging ? 'c' : '-');
  f.write(has_line(t) ? 'l' : '-'); f.write(has_bar(t) ? 'b' : '-');
  if (const Data *d = data_of(t)) {
    add(d->map_entity); f.write(d->unmapped ? 'u' : '-'); add(d->error);
    for (const auto &r : d->rooms) { add(r.area); add(r.name); f.write(r.floor); }
    for (const auto &n : d->floors) add(n);
    for (const auto &r : d->routines) { add(r.entity); add(r.name); }
  }
  f.write(camera_supported() ? 'p' : '-');
  // What decides the rows of suction and water (vacuum_card_shape of the lite card).
  const uint32_t now = esphome::millis();
  const auto rows = tile_controls::vacuum_rows(t, now);
  f.write(rows.suction); f.write(rows.water);
  for (char kind : {'m', 's', 'w'}) if (const Choice *c = t.choice(kind)) { f.write(kind); for (const auto &v : c->values) add(v); for (const auto &l : c->labels) add(l); }
  if (const Choice *mode = t.choice('m')) {
    f.write(static_cast<uint8_t>(tile_controls::vacuum_role(t, now)));
    f.write(tile_controls::shown_value(t, *mode, now).find("smart") != std::string::npos);
  }
  return f.value;
}
void render(Tile &t, lv_obj_t *heading_obj, int width, int height) {
  follow(t);
  if (const Data *d = data_of(t)) vacuum_model::keep_valid(picks, d->rooms.size());
  map_ask = MapAsk{};
  map_picture = nullptr;
  const Metrics m = metrics();
  const int x = m.pad, y = content_top(m), w = width - 2 * m.pad, h = height - y - m.pad;
  // A view of the card: its own name in the bar, the back key returns to the card.
  if (view != MAIN) {
    if (heading_obj) label(heading_obj, tr(view == ROOMS ? txt::vacuum_by_room : view == ROUTINES ? txt::vacuum_routines : txt::vacuum_suction_water));
    if (view == ROOMS) rooms_view(t, m, x, y, w, h);
    else if (view == ROUTINES) routines_view(t, m, x, y, w, h);
    else how_view(t, m, x, y, w, h);
    detail_placed = true;
    card_shaped(t, card_shape);
    return;
  }
  BarKeys bar;
  if (landscape() && (shows_map(t) || low(h))) bar = low(h) ? low_glass(t, m, x, y, w, h) : two_columns(t, m, x, y, w, h);
  else bar = one_column(t, m, x, y, w, h);
  // The top bar's keys: suction and water at the edge, Locate beside it; the name keeps the room between them.
  detail_bar::Bar keys_bar;
  keys_bar.title = heading_obj;
  int count = 0;
  auto add_key = [&](const char *g, int cmd) {
    auto *k = detail_bar::key(detail_root, detail_bar::right_slot(detail_root, count), g,
                              [](lv_event_t *e) { detail_command(static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)))); },
                              reinterpret_cast<void *>(static_cast<intptr_t>(cmd)));
    keys_bar.right[count++] = k;
    hits.push_back({cmd, k});
  };
  if (bar.how) add_key(ICON_HOW, CMD_HOW);
  if (bar.locate && count < 2) add_key(ICON_LOCATE, CMD_LOCATE);
  if (count) detail_bar::place_title(heading_obj, detail_root, count);
  // An unavailable robot: everything under the robot faded, as Home Assistant's dialog disables its keys.
  if (!t.available()) for (uint32_t i = 0; i < detail_action_count; ++i) lv_obj_add_state(detail_actions[i], LV_STATE_DISABLED);
  detail_placed = true;
  card_shaped(t, card_shape);
}

// ---- Taps ----
inline void rebuild() {
  lv_async_call([](void *) { if (detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN)) show_detail(detail_index); }, nullptr);
}
inline void open_view(View v) { view = v; page = 0; rebuild(); }
// The back key: a view returns to the card; on the card it closes it.
bool back() {
  if (view == MAIN) return false;
  view = MAIN;
  rebuild();
  return true;
}
bool handles(int cmd) { return cmd >= CMD_FIRST && cmd <= CMD_LAST; }
void command(Tile &t, int cmd) {
  const Data *d = data_of(t);
  const uint32_t now = esphome::millis();
  if (cmd == CMD_ROOMS) { open_view(ROOMS); return; }
  if (cmd == CMD_ROUTINES) { open_view(ROUTINES); return; }
  if (cmd == CMD_HOW) { open_view(HOW); return; }
  if (cmd == CMD_PAGE_BACK || cmd == CMD_PAGE_ON) { page += cmd == CMD_PAGE_ON ? 1 : -1; page = std::max(0, page); rebuild(); return; }
  if (cmd >= CMD_FLOOR && cmd < CMD_FLOOR + static_cast<int>(vacuum_model::MAX_FLOORS)) {
    if (cmd - CMD_FLOOR != floor) { floor = cmd - CMD_FLOOR; page = 0; rebuild(); }
    return;
  }
  if (cmd >= CMD_PICK && cmd < CMD_PICK + static_cast<int>(vacuum_model::MAX_ROOMS)) {
    if (!d || cmd - CMD_PICK >= static_cast<int>(d->rooms.size())) return;
    vacuum_model::toggle(picks, static_cast<uint8_t>(cmd - CMD_PICK));
    if (!card_repaint(t)) rebuild();
    return;
  }
  if (!t.available() || t.waiting(now)) return;
  if (cmd >= CMD_ROUTINE && cmd < CMD_ROUTINE + static_cast<int>(vacuum_model::MAX_ROUTINES)) {
    if (d && cmd - CMD_ROUTINE < static_cast<int>(d->routines.size())) action("button.press", d->routines[cmd - CMD_ROUTINE].entity);
    return;
  }
  if (cmd == CMD_LOCATE) { action("vacuum.locate", t.entity); return; }
  const auto c = can_of(t);
  const Key k = cmd == CMD_FIRST ? vacuum_model::first_key(t.state, c) : cmd == CMD_SECOND ? vacuum_model::second_key(t.state, c) : Key::NONE;
  if (k == Key::NONE && cmd != CMD_CLEAN_ROOMS) return;
  // Start with rooms picked cleans those rooms, in the order of the taps (Home Assistant's clean_area); the rooms view's
  // own key does nothing else.
  if ((cmd == CMD_CLEAN_ROOMS || k == Key::START) && d && !picks.empty() && c.by_area) {
    const std::string areas = vacuum_model::areas_template(*d, picks);
    if (areas.empty()) return;
    action_template("vacuum.clean_area", t.entity, "cleaning_area_id", areas);
    picks.clear();
    if (view == ROOMS) view = MAIN;
    rebuild();
    return;
  }
  if (cmd == CMD_CLEAN_ROOMS) return;
  action(vacuum_model::service(k), t.entity);
}

// ---- The map's picture (picture_loader.h): wanted while the card shows it ----
inline void map_request(const MapAsk &a) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_camera");
  request.is_event = true;
  char box[16], ground[8];
  snprintf(box, sizeof(box), "%dx%d", a.w, a.h);
  snprintf(ground, sizeof(ground), "%06X", (unsigned) a.ground);
  const std::string session = protocol_key(transfer.lease), number = std::to_string(++vacuum_map_view_id);
  const std::string keys_[] = {"inbox", "entity", "vmap", "bg", "dark", "session", "rev", "view"};
  const std::string values[] = {inbox, a.entity, box, ground, a.dark ? "1" : "0", session, layout_rev, number};
  request.data.init(8);
  for (int i = 0; i < 8; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys_[i]);
    entry.value = esphome::StringRef(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("camera", "asked for the map of %s at %dx%d", a.entity.c_str(), a.w, a.h);
}
void picture_want() {
  if (!map_ask.valid() || view != MAIN || !detail_shown() || !tiles_seen() || detail_index >= model.count ||
      model.tiles[detail_index].entity != map_ask.entity) return;
  picture_loader::Want want;
  want.key = map_key(map_ask);
  want.tag = "vmap|" + map_ask.entity;
  want.slot = picture_loader::Slot::FULL;
  want.rank = picture_loader::Rank::CARD;
  want.drawn = true;
  const MapAsk ask = map_ask;
  want.ask = [ask] { map_request(ask); };
  const std::string key = want.key;
  want.done = [key](picture_loader::Outcome o) {
    if (o == picture_loader::Outcome::NONE) map_missing = key;
    if ((shows(o) || o == picture_loader::Outcome::NONE) && detail_shown() && detail_index < model.count &&
        !card_repaint(model.tiles[detail_index])) refresh_detail(detail_index);
  };
  loader.want(owners::CARD, std::move(want));
}
bool draws(const lv_image_dsc_t *image) {
#if LV_USE_IMAGE
  return map_picture && lv_image_get_src(map_picture) == image;
#else
  (void) image;
  return false;
#endif
}
void forget_pictures() {
#if LV_USE_IMAGE
  if (map_picture) { lv_image_set_src(map_picture, nullptr); lv_obj_add_flag(map_picture, LV_OBJ_FLAG_HIDDEN); }
#endif
  map_shown.clear();
}
// The card's objects are deleted (another card is built): nothing here points at them any more.
void card_cleared() { map_picture = map_spinner = nullptr; map_ask = MapAsk{}; hits.clear(); }
// The card closed: the views and the picks go, the map's picture may go once nothing draws it.
void closed() {
  if (!map_shown.empty()) picture_retire(map_shown);
  map_shown.clear();
  map_picture = map_spinner = nullptr;
  map_ask = MapAsk{};
  hits.clear();
  view = MAIN;
  picks.clear();
  floor = page = 0;
}

// The card's keys with their commands and where they are, for the renders (tools/render/host.py) and a diagnosis.
std::string describe() {
  std::string keys;
  for (auto &h : hits) {
    if (!h.obj) continue;
    lv_area_t a;
    lv_obj_get_coords(h.obj, &a);
    keys += std::to_string(h.cmd) + "@" + std::to_string((a.x1 + a.x2) / 2) + "," + std::to_string((a.y1 + a.y2) / 2) + ";";
  }
  return "view=" + std::to_string(static_cast<int>(view)) + " keys=" + keys;
}
}  // namespace vacuum_card
}  // namespace runtime_tiles
#endif
