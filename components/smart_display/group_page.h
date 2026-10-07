#pragma once
// A light group's lamp page (firmware 0.3.9+, app 0.3.16+): the lamps of the group, one card per lamp, reached from the
// lamps key beside the sparkles key on the group's colour card.
//
// Every part is one the screens already draw: the top bar and the cards of the effects page, the colour card's
// brightness slider (amber fill, the white handle inside the fill, an off lamp only its track) and its colour and
// white-shade sliders, and the pager of the tile pages and the settings page. A group with more lamps than the glass
// holds is paged, never scrolled. A lamp that can take a colour or a white shade has an ellipsis key: it opens a
// small panel with just those sliders, and a finger that comes down beside the panel closes it at once.
//
// Like the effects page, the page is built when it opens and thrown away when it closes, so it costs nothing while
// closed. The model part (which lamps, where the cards stand, the values) stays free of LVGL for tests/test_group_page.cpp.
#include <algorithm>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include "runtime_model.h"
#include "optimistic.h"
#include "tile_controls.h"
#include "ui_scale.h"

namespace group_page {
using runtime_tiles::Lamp;
using runtime_tiles::Tile;

// The fallback range of a white-shade slider when the lamp names none.
constexpr int KELVIN_LOW = 2000, KELVIN_HIGH = 6500;

// Whether a light has a lamp page: it is a group with lamps.
inline bool available(const Tile &t) { return t.domain() == "light" && !t.extra().lamps.empty(); }
// Whether a lamp gets the ellipsis key: it takes a colour or a white shade, and answers at all.
inline bool has_panel(const Lamp &l) { return !l.unavailable && (l.color || l.temperature); }
// The white-shade range of a lamp, its own when it names one.
inline int kelvin_low(const Lamp &l) { return l.high > l.low ? l.low : KELVIN_LOW; }
inline int kelvin_high(const Lamp &l) { return l.high > l.low ? l.high : KELVIN_HIGH; }
inline int kelvin_of(const Lamp &l, int value) { return std::max(kelvin_low(l), std::min(kelvin_high(l), value)); }

// The colour a lamp's card paints in while the lamp is on (firmware 0.4.0+): the lamp's own, the way its tile shows it
// (tile_controls::lamp_color), and the amber of a lamp that is on when Home Assistant names no colour. A hue just sent
// is in the lamp already: the wish wrote it there (docs/OPTIMISTIC.md).
inline uint32_t color_of(const Lamp &l) { return tile_controls::lamp_color(l.hue, l.saturation); }
// Where the cards stand, in the page's own room (the card's width, overlay_card::content_width, and the glass's
// height). As many columns as keep a card wide enough for a name and a slider a thumb can drag, as many rows as fit
// between the top bar and the pager; the pager only takes its band when the lamps need more than one page.
struct Room { int width = 480, height = 480, pad = 20, top = 86, pager = 40, pager_bottom = 16; bool large = true; };
struct Layout {
  int cols = 1, rows = 1, per_page = 1, pages = 1, card_w = 0, card_h = 0, gap = 0, top = 0, pager_y = 0;
  int card_x(int i) const { return (i % cols) * (card_w + gap); }
  int card_y(int i) const { return top + (i / cols) * (card_h + gap); }
};
inline Layout layout(int count, const Room &r) {
  Layout l;
  l.gap = ui::px(r.large ? 8 : 4);
  l.top = r.top;
  const int inner = r.width - 2 * r.pad, least_w = ui::px(r.large ? 280 : 140);
  l.cols = std::max(1, std::min(2, (inner + l.gap) / (least_w + l.gap)));
  l.card_w = (inner - (l.cols - 1) * l.gap) / l.cols;
  l.card_h = std::max(ui::touch_min() + ui::px(r.large ? 30 : 8), ui::px(r.large ? 76 : 44));
  auto rows_in = [&](int room) { return std::max(1, (room + l.gap) / (l.card_h + l.gap)); };
  l.rows = rows_in(r.height - ui::px(r.large ? 12 : 6) - l.top);
  if (count > l.rows * l.cols) {
    l.pager_y = r.height - r.pager - r.pager_bottom / 2;
    l.rows = rows_in(l.pager_y - ui::px(r.large ? 6 : 3) - l.top);
  }
  l.per_page = l.rows * l.cols;
  l.pages = std::max(1, (std::max(0, count) + l.per_page - 1) / l.per_page);
  return l;
}
}  // namespace group_page

#ifndef GROUP_PAGE_TEST
#include <cstdio>
#include "esphome/core/log.h"
#include "lvgl.h"
#include "effects_page.h"
#include "light_controls.h"
#include "overlay_card.h"
#include "screen_text.h"
#include "settings_screen.h"
#include "theme.h"
namespace group_page {
// ---- what the board profile wires up at boot (fonts and the tile come from the effects page's) ----
// An action to Home Assistant: service, lamp, key, value; `rendered` for a value Home Assistant renders (a list).
inline std::function<void(const std::string &, const std::string &, const std::string &, const std::string &, bool)> send;
// A lamp's change as a wish (docs/OPTIMISTIC.md): the group, the field, the lamp, the value it shows, and the action
// that makes it so (runtime_tiles::wish_part). The card shows the lamp as the group's tile holds it, wish and all.
inline std::function<void(const std::string &, optimistic::Field, const std::string &, const std::string &, const std::string &,
                          const std::string &, const std::string &, bool)> wish;

// ---- state while open ----
inline lv_obj_t *root = nullptr;
inline std::string entity;   // the group
inline int page = 0;
struct Card {
  lv_obj_t *box = nullptr, *icon = nullptr, *slider = nullptr, *knob = nullptr, *key = nullptr;
  std::string entity;
  bool dirty = false;
};
inline std::vector<Card> cards;
// The panel of one lamp: the sheet under it that closes it, the panel, and its sliders.
struct PanelSlider { lv_obj_t *slider = nullptr, *value = nullptr; bool hue = true, dirty = false; };
inline lv_obj_t *panel = nullptr, *catcher = nullptr;
inline int panel_card = -1;
inline std::vector<PanelSlider> panel_sliders;

inline uint32_t clock() { return effects_page::clock(); }
inline const Tile *tile() { return effects_page::tile_of ? effects_page::tile_of(entity) : nullptr; }
inline const Lamp *lamp_of(const std::string &lamp) {
  if (const Tile *t = tile()) for (auto &l : t->extra().lamps) if (l.entity == lamp) return &l;
  return nullptr;
}
inline bool offered(const std::string &group) {
  const Tile *t = effects_page::tile_of ? effects_page::tile_of(group) : nullptr;
  return t && available(*t);
}
inline bool visible() { return root != nullptr; }
inline Room room() {
  const auto em = effects_page::screen_metrics();
  const auto sm = settings_screen::metrics();
  Room r;
  r.width = em.width; r.height = em.height; r.pad = em.pad; r.large = ui::large();
  r.top = em.bar_y + em.bar + ui::px(r.large ? 14 : 6);
  r.pager = sm.pager; r.pager_bottom = sm.bottom;
  return r;
}
inline void emit(const char *service, const std::string &lamp, const char *key, const std::string &value, bool rendered = false) {
  ESP_LOGI("group", "%s %s %s=%s", service, lamp.c_str(), key, value.c_str());
  if (send) send(service, lamp, key, value, rendered);
}
// A lamp's change: a wish where the runtime takes one, the bare action otherwise.
inline void want(optimistic::Field field, const std::string &lamp, const std::string &shown, const char *service, const char *key,
                 const std::string &value, bool rendered = false) {
  if (wish) wish(entity, field, lamp, shown, service, key, value, rendered);
  else emit(service, lamp, key, value, rendered);
}

// ---- the panel ----
inline void close_panel() {
  if (catcher) { lv_obj_delete(catcher); catcher = nullptr; }
  if (panel) { lv_obj_delete(panel); panel = nullptr; }
  if (panel_card >= 0 && panel_card < static_cast<int>(cards.size()) && cards[panel_card].key)
    lv_obj_set_style_bg_color(cards[panel_card].key, theme::color(theme::KEY), 0);
  panel_card = -1;
  panel_sliders.clear();
}
inline void panel_value_text(PanelSlider &p) {
  if (!p.value) return;
  char text[16];
  const int v = lv_slider_get_value(p.slider);
  if (p.hue) snprintf(text, sizeof(text), "%d°", v); else snprintf(text, sizeof(text), "%d K", v);
  lv_label_set_text(p.value, text);
}
inline void knob_color(PanelSlider &p, const Lamp &l) {
  const int v = lv_slider_get_value(p.slider);
  lv_obj_set_style_bg_color(p.slider, p.hue ? lv_color_hsv_to_rgb(v % 360, 100, 100)
                                            : light_controls::kelvin_color(v, kelvin_low(l), kelvin_high(l)), LV_PART_KNOB);
}
inline void paint(Card &c, const Lamp &l, bool fresh_card);
inline void panel_event(lv_event_t *e) {
  const size_t index = reinterpret_cast<intptr_t>(lv_event_get_user_data(e));
  if (index >= panel_sliders.size() || panel_card < 0 || panel_card >= static_cast<int>(cards.size())) return;
  auto &p = panel_sliders[index];
  const Lamp *l = lamp_of(cards[panel_card].entity);
  if (!l) return;
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) { p.dirty = true; panel_value_text(p); knob_color(p, *l); }
  if (code == LV_EVENT_PRESS_LOST) p.dirty = false;
  if (code == LV_EVENT_RELEASED && p.dirty) {
    p.dirty = false;
    const int v = lv_slider_get_value(p.slider);
    // The card of the lamp takes the new colour at once: the wish writes it into the lamp, and the page paints it.
    const std::string lamp = l->entity;
    if (p.hue) want(optimistic::Field::LAMP_HUE, lamp, std::to_string(v), "light.turn_on", "hs_color", "[" + std::to_string(v) + ", 100]", true);
    else want(optimistic::Field::LAMP_KELVIN, lamp, std::to_string(kelvin_of(*l, v)), "light.turn_on", "color_temp_kelvin", std::to_string(kelvin_of(*l, v)));
  }
}
inline lv_obj_t *round_end(lv_obj_t *parent, int x, int y, int size, uint32_t color) {
  auto *end = effects_page::plain(parent, x, y, size, size);
  lv_obj_set_style_radius(end, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(end, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(end, lv_color_hex(color), 0);
  return end;
}
// The colour card's colour and white-shade sliders (light_controls::setup, rows 0 and 1): a gradient pill with a round
// knob in the chosen colour.
inline lv_obj_t *gradient_slider(lv_obj_t *box, int x, int y, int w, int h, bool hue, const Lamp &l) {
  const bool large = ui::large();
  const uint32_t *rainbow = light_controls::RAINBOW;
  round_end(box, x, y, h, hue ? rainbow[0] : light_controls::WARM);
  round_end(box, x + w - h, y, h, hue ? rainbow[6] : light_controls::COOL);
  const int radius = h / 2, span = w - h;
  const unsigned segments = hue ? 6 : 1;
  for (unsigned n = 0; n < segments; ++n) {
    const int a = n * span / segments, b = (n + 1) * span / segments;
    auto *stripe = effects_page::plain(box, x + radius + a, y, b - a, h);
    lv_obj_set_style_bg_opa(stripe, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(stripe, lv_color_hex(hue ? rainbow[n] : light_controls::WARM), 0);
    lv_obj_set_style_bg_grad_color(stripe, lv_color_hex(hue ? rainbow[n + 1] : light_controls::COOL), 0);
    lv_obj_set_style_bg_grad_dir(stripe, LV_GRAD_DIR_HOR, 0);
  }
  auto *s = lv_slider_create(box);
  lv_obj_remove_style_all(s);
  lv_obj_remove_flag(s, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_ext_click_area(s, ui::px(large ? 12 : 8));
  lv_obj_set_pos(s, x + radius, y);
  lv_obj_set_size(s, span, h);
  lv_obj_set_style_bg_opa(s, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(s, LV_OPA_TRANSP, LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(s, LV_OPA_COVER, LV_PART_KNOB);
  lv_obj_set_style_radius(s, LV_RADIUS_CIRCLE, LV_PART_KNOB);
  lv_obj_set_style_pad_all(s, ui::px(large ? 4 : 3), LV_PART_KNOB);
  lv_obj_set_style_border_width(s, ui::px(large ? 4 : 3), LV_PART_KNOB);
  lv_obj_set_style_border_color(s, theme::color(theme::KNOB), LV_PART_KNOB);
  lv_obj_set_style_outline_width(s, 1, LV_PART_KNOB);
  lv_obj_set_style_outline_color(s, lv_color_black(), LV_PART_KNOB);
  lv_obj_set_style_outline_opa(s, LV_OPA_20, LV_PART_KNOB);
  lv_slider_set_range(s, hue ? 0 : kelvin_low(l), hue ? 360 : kelvin_high(l));
  return s;
}
inline void open_panel(int index);
inline void key_event(lv_event_t *e) {
  if (!effects_page::steady()) return;
  open_panel(static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e))));
}
inline void open_panel(int index) {
  if (!root || index < 0 || index >= static_cast<int>(cards.size()) || !cards[index].key) return;
  const bool same = index == panel_card;
  close_panel();
  const Lamp *l = lamp_of(cards[index].entity);
  if (same || !l || !has_panel(*l)) return;
  panel_card = index;
  const bool large = ui::large();
  const auto em = effects_page::screen_metrics();
  lv_obj_update_layout(root);
  lv_area_t k; lv_obj_get_coords(cards[index].key, &k);
  lv_area_t r; lv_obj_get_coords(root, &r);
  const lv_font_t *font = effects_page::row_font;
  const int rows = (l->color ? 1 : 0) + (l->temperature ? 1 : 0);
  const int pad = ui::px(large ? 8 : 4), inset = ui::px(large ? 14 : 7), text_y = ui::px(large ? 10 : 4);
  const int track_h = ui::px(large ? 28 : 16), text_h = lv_font_get_line_height(font), foot = ui::px(large ? 12 : 6);
  const int row_h = text_y + text_h + ui::px(large ? 10 : 5) + track_h + foot;
  const int w = std::min(em.width - 2 * em.pad, ui::px(large ? 320 : 220)), h = rows * row_h + 2 * pad;
  // Under the key, over it where the glass ends, never over the top bar or past the bottom.
  int x = std::max(em.pad, static_cast<int>(k.x2 - r.x1) - w), y = k.y2 - r.y1 + ui::px(large ? 6 : 3);
  if (y + h > em.height - ui::px(4)) y = k.y1 - r.y1 - h - ui::px(large ? 6 : 3);
  y = std::max(em.bar_y, std::min(y, em.height - h - ui::px(4)));
  // A finger that comes down anywhere beside the panel closes it at once, on the touch and not on the release: a
  // finger that drags a slider out over the panel's edge was pressed inside it, so the panel stays.
  const int side = (overlay_card::screen_width() - em.width) / 2;
  catcher = effects_page::plain(root, -side, 0, overlay_card::screen_width(), em.height);
  lv_obj_add_flag(catcher, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(catcher, [](lv_event_t *) { lv_async_call([](void *) { close_panel(); }, nullptr); }, LV_EVENT_PRESSED, nullptr);
  // The key of the lamp the panel belongs to stays dark while it is open.
  lv_obj_set_style_bg_color(cards[index].key, theme::color(theme::KEY_PRESSED), 0);
  panel = effects_page::card(root, x, y, w, h, ui::px(large ? 18 : 10));
  lv_obj_set_style_shadow_width(panel, ui::px(large ? 24 : 14), 0);
  lv_obj_set_style_shadow_opa(panel, LV_OPA_20, 0);
  lv_obj_set_style_shadow_offset_y(panel, ui::px(large ? 4 : 2), 0);
  lv_obj_add_flag(panel, LV_OBJ_FLAG_CLICKABLE);  // a tap between the sliders stays on the panel
  panel_sliders.reserve(2);
  int row = 0;
  for (int kind = 0; kind < 2; ++kind) {
    const bool hue = kind == 0;
    if (hue ? !l->color : !l->temperature) continue;
    const int top = pad + row++ * row_h;
    int tx = inset;
    if (effects_page::icon_font) {
      auto *ic = effects_page::text(panel, hue ? "\U000F03D8" : "\U000F050F", effects_page::icon_font, theme::MUTED);
      lv_obj_set_width(ic, LV_SIZE_CONTENT);
      const int ih = lv_font_get_line_height(effects_page::icon_font);
      lv_obj_set_pos(ic, inset - ui::px(large ? 2 : 1), top + text_y + (text_h - ih) / 2);
      tx += ih + ui::px(large ? 6 : 4);
    }
    const int value_w = ui::px(large ? 80 : 50);
    PanelSlider p; p.hue = hue;
    p.value = effects_page::text(panel, "", font, theme::MUTED, LV_TEXT_ALIGN_RIGHT);
    lv_obj_set_width(p.value, value_w);
    lv_obj_set_pos(p.value, w - inset - value_w, top + text_y);
    auto *label = effects_page::text(panel, screen_text::tr(hue ? screen_text::txt::light_color : screen_text::txt::light_color_temperature), font, theme::INK);
    lv_obj_set_width(label, w - inset - value_w - ui::px(4) - tx);
    lv_obj_set_pos(label, tx, top + text_y);
    p.slider = gradient_slider(panel, inset, top + row_h - foot - track_h, w - 2 * inset, track_h, hue, *l);
    lv_slider_set_value(p.slider, hue ? l->hue : kelvin_of(*l, l->kelvin ? l->kelvin : (kelvin_low(*l) + kelvin_high(*l)) / 2), LV_ANIM_OFF);
    panel_value_text(p);
    knob_color(p, *l);
    lv_obj_add_event_cb(p.slider, panel_event, LV_EVENT_ALL, reinterpret_cast<void *>(static_cast<intptr_t>(panel_sliders.size())));
    panel_sliders.push_back(p);
  }
  ESP_LOGI("group", "Panel of %s: %d sliders", l->entity.c_str(), rows);
}

// ---- the cards ----
// The colour card's brightness slider (light_controls::setup, row 2), at the size of a card in this list.
inline lv_obj_t *brightness_slider(lv_obj_t *parent, int x, int y, int w, int h) {
  const bool large = ui::large();
  auto *s = lv_slider_create(parent);
  lv_obj_remove_style_all(s);
  lv_obj_remove_flag(s, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_ext_click_area(s, ui::px(large ? 12 : 8));
  lv_obj_set_pos(s, x, y);
  lv_obj_set_size(s, w, h);
  const int corner = h * 12 / 42;
  lv_obj_set_style_radius(s, corner, LV_PART_MAIN);
  lv_obj_set_style_radius(s, corner, LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(s, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_bg_color(s, lv_color_hex(theme::ha::AMBER), LV_PART_INDICATOR);
  const int handle = ui::px(large ? 4 : 3), back = std::max(1, h / 8) + handle / 2, half = h >> 1;
  lv_obj_set_style_bg_color(s, theme::color(theme::KNOB), LV_PART_KNOB);
  lv_obj_set_style_radius(s, 2, LV_PART_KNOB);
  lv_obj_set_style_pad_left(s, back + handle / 2 - half, LV_PART_KNOB);
  lv_obj_set_style_pad_right(s, handle / 2 - back - (h - half), LV_PART_KNOB);
  lv_obj_set_style_pad_top(s, -(h / 4), LV_PART_KNOB);
  lv_obj_set_style_pad_bottom(s, -(h / 4), LV_PART_KNOB);
  // 1 % still shows a stub a third of the height wide: the range starts that far below 1.
  const int stub = std::max(h / 3, 2 * std::max(1, h / 8) + handle), below = w > stub ? 99 * stub / (w - stub) : 0;
  lv_slider_set_range(s, 1 - below, 100);
  return s;
}
// A card as the lamp is now: its icon, the fill of its slider (an off lamp shows only the track, as on the colour card,
// until a finger moves it), or the word of a lamp that cannot be dimmed. A slider under a finger is left alone.
inline void paint(Card &c, const Lamp &l, bool fresh_card) {
  const bool on = l.on;
  const uint32_t color = color_of(l);
  // The pale track under the fill: amber's own for an amber lamp, else the tile's tint of the lamp's colour.
  const lv_color_t track = color == theme::ha::AMBER ? theme::color(theme::AMBER_TRACK) : lv_color_hex(theme::tint(color, 51));
  if (c.icon) {
    lv_label_set_text(c.icon, on ? "\U000F0335" : "\U000F0E4F");
    lv_obj_set_style_text_color(c.icon, on ? lv_color_hex(color) : theme::color(theme::MUTED), 0);
  }
  // A lamp that only switches: the settings page's switch, in the lamp's colour while it is on like the other lamps' fill.
  if (c.knob) {
    auto *track = lv_obj_get_parent(c.knob);
    const int w = lv_obj_get_style_width(track, LV_PART_MAIN), h = lv_obj_get_style_height(track, LV_PART_MAIN);
    lv_obj_set_style_bg_color(track, on ? lv_color_hex(color) : theme::color(theme::TOGGLE_OFF), 0);
    lv_obj_set_x(c.knob, settings_screen::knob_x(w, h, on));
  }
  if (c.slider && (fresh_card || (!c.dirty && !lv_obj_has_state(c.slider, LV_STATE_PRESSED)))) {
    const int level = l.level;
    const bool lit = on && level > 0;
    lv_obj_set_style_bg_color(c.slider, lit ? track : theme::color(theme::TRACK), LV_PART_MAIN);
    lv_obj_set_style_bg_color(c.slider, lv_color_hex(color), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, lit ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, lit ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_KNOB);
    lv_slider_set_value(c.slider, std::max(1, level), LV_ANIM_OFF);
  }
  lv_obj_set_style_opa(c.box, l.unavailable ? LV_OPA_50 : LV_OPA_COVER, 0);
}
inline int card_index(lv_event_t *e) { return static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e))); }
// A tap on a card switches its lamp, the way a tap on a lamp's tile does.
inline void card_event(lv_event_t *e) {
  const int i = card_index(e);
  if (!effects_page::steady() || i < 0 || i >= static_cast<int>(cards.size())) return;
  const Lamp *l = lamp_of(cards[i].entity);
  if (!l || l->unavailable) return;
  // On or off by what the card shows, as Home Assistant's toggle sends it (turn_on or turn_off, never toggle).
  const bool on = !l->on;
  want(optimistic::Field::LAMP_ON, l->entity, on ? "1" : "0", on ? "light.turn_on" : "light.turn_off", "", "");
}
inline void slider_event(lv_event_t *e) {
  const int i = card_index(e);
  if (i < 0 || i >= static_cast<int>(cards.size())) return;
  auto &c = cards[i];
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) {
    c.dirty = true;
    if (lv_slider_get_value(c.slider) < 1) lv_slider_set_value(c.slider, 1, LV_ANIM_OFF);
    // A lamp that was off shows its fill as soon as the slider moves, in the lamp's colour.
    const Lamp *l = lamp_of(c.entity);
    const uint32_t color = l ? color_of(*l) : theme::ha::AMBER;
    lv_obj_set_style_bg_color(c.slider, color == theme::ha::AMBER ? theme::color(theme::AMBER_TRACK) : lv_color_hex(theme::tint(color, 51)), LV_PART_MAIN);
    lv_obj_set_style_bg_color(c.slider, lv_color_hex(color), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_KNOB);
  }
  if (code == LV_EVENT_PRESS_LOST) c.dirty = false;
  if (code == LV_EVENT_RELEASED && c.dirty) {
    c.dirty = false;
    const int v = std::max(1, static_cast<int>(lv_slider_get_value(c.slider)));
    want(optimistic::Field::LAMP_LEVEL, c.entity, std::to_string(v), "light.turn_on", "brightness_pct", std::to_string(v));
  }
}
inline void member_card(lv_obj_t *parent, int x, int y, int w, int h, const Lamp &l, int index) {
  const bool large = ui::large();
  const auto user = reinterpret_cast<void *>(static_cast<intptr_t>(index));
  Card c; c.entity = l.entity;
  c.box = effects_page::card(parent, x, y, w, h, ui::px(large ? 18 : 10));
  lv_obj_add_flag(c.box, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_color(c.box, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
  lv_obj_add_event_cb(c.box, card_event, LV_EVENT_SHORT_CLICKED, user);
  const lv_font_t *font = effects_page::row_font;
  const int inset = ui::px(large ? 16 : 8), text_y = ui::px(large ? 11 : 4), text_h = lv_font_get_line_height(font);
  int right = w;
  if (has_panel(l)) {
    const int key = std::min(ui::touch_min(), h - 2 * ui::px(large ? 8 : 4));
    c.key = effects_page::round_key(c.box, w - inset - key, (h - key) / 2 - 1, key, "\U000F01D8", [](lv_event_t *) {});
    lv_obj_add_event_cb(c.key, key_event, LV_EVENT_SHORT_CLICKED, user);
    right = w - key - ui::px(large ? 10 : 5);
  }
  // A lamp that cannot be dimmed has a switch at the right instead of a slider, its name in the middle of the card;
  // the whole card is the target, as on the settings page.
  const bool slider = l.dimmable && !l.unavailable, pill = !l.dimmable && !l.unavailable;
  const int line_y = slider ? text_y : (h - text_h) / 2 - 1;
  int text_x = inset;
  if (effects_page::icon_font) {
    c.icon = effects_page::text(c.box, "", effects_page::icon_font, theme::MUTED);
    lv_obj_set_width(c.icon, LV_SIZE_CONTENT);
    const int icon_h = lv_font_get_line_height(effects_page::icon_font);
    lv_obj_set_pos(c.icon, inset - ui::px(large ? 2 : 1), line_y + (text_h - icon_h) / 2);
    text_x += icon_h + ui::px(large ? 6 : 4);
  }
  int name_right = right - inset;
  if (pill) {
    const auto sm = settings_screen::metrics();
    c.knob = settings_screen::pill(c.box, right - inset - sm.switch_w, (h - sm.switch_h) / 2 - 1, sm.switch_w, sm.switch_h, l.on);
    name_right -= sm.switch_w + ui::px(large ? 10 : 5);
  }
  auto *name = effects_page::text(c.box, l.name.empty() ? l.entity : l.name, font, theme::INK);
  lv_obj_set_width(name, std::max(ui::px(20), name_right - text_x));
  lv_obj_set_pos(name, text_x, line_y);
  if (slider) {
    const int track_h = ui::px(large ? 28 : 14), foot = ui::px(large ? 12 : 5);
    c.slider = brightness_slider(c.box, inset, h - foot - track_h - 2, right - 2 * inset, track_h);
    lv_obj_add_event_cb(c.slider, slider_event, LV_EVENT_ALL, user);
  }
  cards.push_back(std::move(c));
  paint(cards.back(), l, true);
}

// ---- the page ----
inline void draw();
inline void pager_event(lv_event_t *e) {
  page += static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
  draw();
}
// The same pager as the tile pages and the settings page (settings_screen::draw): a chevron in each half, the page dots
// between them; a half that leads nowhere is dimmed and takes no touches.
inline void pager(const Layout &l) {
  const auto em = effects_page::screen_metrics();
  const auto sm = settings_screen::metrics();
  const int half = (em.width - 2 * em.pad) / 2 - 20;
  const lv_font_t *chevrons = effects_page::icon_font ? effects_page::icon_font : effects_page::row_font;
  const int chevron_h = lv_font_get_line_height(chevrons);
  auto *dots = effects_page::plain(root, 0, l.pager_y, em.width, sm.pager);
  settings_screen::page_dots(dots, page, l.pages, sm.large);
  for (int side = 0; side < 2; ++side) {
    const bool enabled = side ? page + 1 < l.pages : page > 0;
    auto *bar = effects_page::plain(root, side ? em.width - em.pad - half : em.pad, l.pager_y, half, sm.pager);
    auto *glyph = effects_page::text(bar, side ? "\U000F0142" : "\U000F0141", chevrons, theme::INK,
                                     side ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT);
    lv_obj_set_width(glyph, half - 12);
    lv_obj_set_pos(glyph, 6, (sm.pager - chevron_h) / 2);
    if (!enabled) { lv_obj_set_style_opa(glyph, LV_OPA_30, 0); continue; }
    lv_obj_add_flag(bar, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_STATE_PRESSED);
    lv_obj_set_style_bg_color(bar, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
    lv_obj_set_style_radius(bar, sm.radius, 0);
    lv_obj_add_event_cb(bar, pager_event, LV_EVENT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(side ? 1 : -1)));
  }
}
inline void close() {
  close_panel();
  cards.clear();
  if (root) { lv_obj_delete(root); root = nullptr; }
  entity.clear();
}
inline void back_event(lv_event_t *) { if (effects_page::steady()) close(); }
inline void draw() {
  if (!root) return;
  close_panel();
  lv_obj_clean(root);
  cards.clear();
  const Tile *t = tile();
  const auto em = effects_page::screen_metrics();
  effects_page::top_bar(root, em, t ? (t->name.empty() ? t->entity : t->name) : entity, back_event);
  if (!t) return;
  const auto &lamps = t->extra().lamps;
  const Layout l = layout(static_cast<int>(lamps.size()), room());
  page = std::max(0, std::min(page, l.pages - 1));
  const int first = page * l.per_page, shown = std::min(l.per_page, static_cast<int>(lamps.size()) - first);
  cards.reserve(std::max(0, shown));
  for (int i = 0; i < shown; ++i) member_card(root, em.pad + l.card_x(i), l.card_y(i), l.card_w, l.card_h, lamps[first + i], i);
  if (l.pages > 1) pager(l);
  ESP_LOGI("group", "Lamp page of %s: %u lamps, page %d of %d, %d a page", entity.c_str(), (unsigned) lamps.size(), page + 1, l.pages, l.per_page);
}
// A state of the group while its page is open: the cards follow Home Assistant, a card just sent keeps its value a
// moment, a slider under a finger is left alone. A group that gained or lost lamps is drawn again, unless a finger
// is on the page.
inline void updated(const Tile &t) {
  if (!root || t.entity != entity) return;
  const auto &lamps = t.extra().lamps;
  if (lamps.empty()) { close(); return; }
  const Layout l = layout(static_cast<int>(lamps.size()), room());
  const int first = std::min(page, l.pages - 1) * l.per_page;
  bool same = static_cast<int>(cards.size()) == std::min(l.per_page, static_cast<int>(lamps.size()) - first);
  for (size_t i = 0; same && i < cards.size(); ++i) {
    const Lamp &lamp = lamps[first + i];
    same = lamp.entity == cards[i].entity && has_panel(lamp) == (cards[i].key != nullptr) &&
           (lamp.dimmable && !lamp.unavailable) == (cards[i].slider != nullptr) &&
           (!lamp.dimmable && !lamp.unavailable) == (cards[i].knob != nullptr);
  }
  if (!same) {
    if (!lv_indev_get_active_obj()) draw();
    return;
  }
  for (size_t i = 0; i < cards.size(); ++i) paint(cards[i], lamps[first + i], false);
  if (panel_card >= 0 && panel_card < static_cast<int>(cards.size())) {
    const Lamp &lamp = lamps[first + panel_card];
    for (auto &p : panel_sliders) {
      if (p.dirty || lv_obj_has_state(p.slider, LV_STATE_PRESSED)) continue;
      const int reported = p.hue ? lamp.hue : kelvin_of(lamp, lamp.kelvin ? lamp.kelvin : lv_slider_get_value(p.slider));
      if (lv_slider_get_value(p.slider) != reported) lv_slider_set_value(p.slider, reported, LV_ANIM_OFF);
      panel_value_text(p);
      knob_color(p, lamp);
    }
  }
}
inline void open(const std::string &group) {
  const Tile *t = effects_page::tile_of ? effects_page::tile_of(group) : nullptr;
  if (!t || !available(*t)) return;
  if (entity != group) page = 0;
  entity = group;
  if (!root) root = effects_page::page_root();
  lv_obj_move_foreground(root);
  draw();
}
// A change of look while the page is open: drawn again in place, the panel closed.
inline void restyle() {
  if (!root) return;
  lv_obj_set_style_bg_color(root, theme::color(theme::PAGE_SOFT), 0);
  draw();
}

// The colour card's top bar with the lamps key: the keys on the right stand together at the card's corner (the sparkles
// key outermost, the lamps key beside it), and the title keeps one line: in the middle with the same room on both sides
// when it fits there, else in all the room between the back key and the keys on the right, ending in dots. `text` is
// the title as it is meant, never read back from the label (LVGL writes its dots into the label's own text).
inline void place_card_keys(lv_obj_t *card, lv_obj_t *back, lv_obj_t *effects, lv_obj_t *group, lv_obj_t *title,
                            const std::string &text) {
  lv_obj_update_layout(card);
  const int card_w = lv_obj_get_width(card), key = lv_obj_get_width(back), edge = lv_obj_get_x(back);
  const int gap = ui::px(ui::large() ? 8 : 5);
  const bool fx = !lv_obj_has_flag(effects, LV_OBJ_FLAG_HIDDEN), lamps = !lv_obj_has_flag(group, LV_OBJ_FLAG_HIDDEN);
  if (lamps) lv_obj_align(group, LV_ALIGN_TOP_RIGHT, -(edge + (fx ? key + gap : 0)), lv_obj_get_y(back));
  const int right = (fx ? 1 : 0) + (lamps ? 1 : 0);
  const int right_side = edge + std::max(1, right) * key + std::max(0, right - 1) * gap + gap, left_side = edge + key + gap;
  const lv_font_t *font = lv_obj_get_style_text_font(title, LV_PART_MAIN);
  lv_label_set_long_mode(title, LV_LABEL_LONG_DOT);
  lv_obj_set_height(title, lv_font_get_line_height(font));
  lv_point_t size;
  lv_text_get_size(&size, text.c_str(), font, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
  const int y = lv_obj_get_y(back) + (key - lv_font_get_line_height(font)) / 2;
  const int centred = card_w - 2 * std::max(left_side, right_side);
  if (size.x <= centred) {
    lv_obj_set_width(title, centred);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, y);
  } else {
    lv_obj_set_width(title, std::max(key, card_w - left_side - right_side));
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, left_side, y);
  }
  lv_label_set_text(title, text.c_str());
}
}  // namespace group_page
#endif
