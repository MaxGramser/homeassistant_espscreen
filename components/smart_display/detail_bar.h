#pragma once
// The top bar of every page a tap opens: a tile's card, the effects page and its picker, a light group, the media
// library and its folders, a plugin's card, a camera and a map. One bar, built here: a round back key at the left,
// the page's name in the middle, and at most two keys at the right (a power key, the picker's check, the speakers).
//
// **The bar stands on the glass, not on the card.** A card of controls is only a hand wide and stands in the middle of
// wide glass, a card in two columns is wider, a picture fills the glass (overlay_card), but the back key keeps the
// glass's top left corner and the keys at the right its top right one on every one of them. A finger that goes a page
// deeper (a group, one of its lights, that light's effects) and back again finds the key where it left it, on a CYD and
// on a ten-inch panel alike. Its parent may be any page's root: the bar works out where the edge of the glass lies in
// that root's own coordinates (glass_left), so a root that is capped by its padding or by its place needs no help.
//
// What a card puts in the bar of its own, a key that follows its entity or a battery's meter, takes the bar's place for
// it (right_slot) and the room between the keys (middle), so it lines up with the rest without a number of its own.
#include <algorithm>
#include <string>
#include "ui_scale.h"
#ifndef DETAIL_BAR_TEST
#include "lvgl.h"
#include "overlay_card.h"
#include "theme.h"
#endif

namespace detail_bar {


struct Metrics { int key, x, y, gap; };
// The key's size, its distance from the glass's side and top, and the gap between two keys and between a key and the name.
inline Metrics metrics() {
  const bool large = ui::large();
  return {ui::px(large ? 60 : 40), ui::px(large ? 16 : 10), ui::px(large ? 16 : 8), ui::px(large ? 10 : 6)};
}
// The bar's foot: where a page's own content may start.
inline int bottom() { const auto m = metrics(); return m.y + m.key; }
#ifndef DETAIL_BAR_TEST  // the sizes above are free of LVGL, for the model tests

// The round keys' glyphs and the name, set once by the core (packages/core.yaml).
inline const lv_font_t *icon_font = nullptr, *title_font = nullptr;
constexpr const char *BACK = "\U000F004D";  // mdi:arrow-left

struct Rect { int x, y, w, h; };

// Where the glass's left edge lies in `parent`'s coordinates, those lv_obj_set_pos takes (its content area). Read from
// the styles, not from the coordinates: those follow only at LVGL's next layout pass, and a page is built before that.
inline int glass_left(const lv_obj_t *parent) {
  int x = 0;
  for (const lv_obj_t *o = parent; o && lv_obj_get_parent(o); o = lv_obj_get_parent(o))
    x += lv_obj_get_style_x(o, LV_PART_MAIN) + lv_obj_get_style_pad_left(o, LV_PART_MAIN) +
         lv_obj_get_style_border_width(o, LV_PART_MAIN);
  return -x;
}
// The back key's place, and the `i`-th key's from the right (0 at the edge), in `parent`'s coordinates.
inline Rect back_slot(const lv_obj_t *parent) {
  const auto m = metrics();
  return {glass_left(parent) + m.x, m.y, m.key, m.key};
}
inline Rect right_slot(const lv_obj_t *parent, int i = 0) {
  const auto m = metrics();
  return {glass_left(parent) + overlay_card::screen_width() - m.x - m.key - i * (m.key + m.gap), m.y, m.key, m.key};
}
// The room for the name, or for what a card shows there instead (the media card's speaker): between the back key and
// `right` keys at the right, and as much at the left as at the right, so its middle is the glass's middle.
inline Rect middle(const lv_obj_t *parent, int right = 1) {
  const auto m = metrics();
  const int keys = std::max(1, right), side = m.x + keys * m.key + (keys - 1) * m.gap + ui::px(8);
  return {glass_left(parent) + side, m.y, std::max(1, overlay_card::screen_width() - 2 * side), m.key};
}

// A round key of the bar: the key's grey, a little darker under a finger, the glyph in ink in its middle (the glyph is
// its first child, for a card that paints the key its own way).
inline lv_obj_t *key(lv_obj_t *parent, const Rect &at, const char *glyph, lv_event_cb_t handler, void *user = nullptr) {
  auto *key = lv_obj_create(parent);
  lv_obj_remove_style_all(key);
  lv_obj_set_pos(key, at.x, at.y);
  lv_obj_set_size(key, at.w, at.h);
  lv_obj_remove_flag(key, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_radius(key, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY), 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  auto *label = lv_label_create(key);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  if (icon_font) lv_obj_set_style_text_font(label, icon_font, 0);
  lv_obj_set_style_text_color(label, theme::color(theme::INK), 0);
  lv_label_set_text(label, glyph);
  lv_obj_center(label);
  if (handler) lv_obj_add_event_cb(key, handler, LV_EVENT_SHORT_CLICKED, user);
  return key;
}

// Put the name in the room between the keys, on the keys' middle line; a long name ends in dots.
inline void place_title(lv_obj_t *title, const lv_obj_t *parent, int right = 1) {
  if (!title) return;
  const auto room = middle(parent, right);
  const lv_font_t *font = lv_obj_get_style_text_font(title, LV_PART_MAIN);
  const int line = font ? lv_font_get_line_height(font) : room.h;
  lv_obj_set_pos(title, room.x, room.y + (room.h - line) / 2);
  lv_obj_set_size(title, room.w, line);
}

struct Key { const char *glyph = nullptr; lv_event_cb_t handler = nullptr; void *user = nullptr; };
struct Bar { lv_obj_t *back = nullptr, *title = nullptr, *right[2] = {nullptr, nullptr}; };

// The whole bar: the back key and the name first (a card centred under its bar keeps its first two children where
// they are, overlay_card::centre), then the keys at the right, the first at the edge.
inline Bar make(lv_obj_t *parent, const std::string &title, Key back, Key right = {}, Key right2 = {}) {
  Bar bar;
  bar.back = key(parent, back_slot(parent), back.glyph ? back.glyph : BACK, back.handler, back.user);
  bar.title = lv_label_create(parent);
  lv_obj_remove_flag(bar.title, LV_OBJ_FLAG_CLICKABLE);
  if (title_font) lv_obj_set_style_text_font(bar.title, title_font, 0);
  lv_obj_set_style_text_color(bar.title, theme::color(theme::INK), 0);
  lv_obj_set_style_text_align(bar.title, LV_TEXT_ALIGN_CENTER, 0);
  lv_label_set_long_mode(bar.title, LV_LABEL_LONG_DOT);
  lv_label_set_text(bar.title, title.c_str());
  int count = 0;
  for (const Key &k : {right, right2}) {
    if (!k.glyph) continue;
    bar.right[count] = key(parent, right_slot(parent, count), k.glyph, k.handler, k.user);
    ++count;
  }
  place_title(bar.title, parent, count);
  return bar;
}

#endif  // DETAIL_BAR_TEST
}  // namespace detail_bar
