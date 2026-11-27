#pragma once
// A still glass in LVGL (docs/PAPER.md, "A still glass"): what LVGL's own widgets are on a glass that prints, where a
// change takes a part of a second and nothing can follow a finger or run by itself. One pass over the objects on the
// glass, before each round of drawing, gives every widget of a kind its still form, wherever it was made: a tile, a
// card, the settings, a plugin's card. Nobody who makes a slider asks which glass it is on.
//
// - A slider is a level (level_bar.h): blocks filled up to its value and, where it is thick enough for a finger, a key
//   at each end. It stays the lv_slider it was, with its range, its value and every listener it had; only what it
//   draws and what a finger's place means are replaced. A tap on a block sets that level, a key takes one step, and
//   listeners hear the value the level has, never one between two blocks.
// - A spinner stands still: an arc that turns would be a refresh every frame.
// - A label that would roll its words is cut with dots.
//
// watch() starts it, once, on a glass of ink (packages/core.yaml); on every other screen it is an empty call, and a
// build without a paper glass does not carry the rest of this file.
#include "paper_screen.h"

#if __has_include("../paper_glass/paper.h")
#include <algorithm>
#include <cstdint>

#include "level_bar.h"
#include "lvgl.h"
#include "theme.h"
#include "ui_scale.h"

namespace still_glass {

// What marks a widget that has its still form.
constexpr lv_obj_flag_t DRESSED = LV_OBJ_FLAG_USER_3;

// ---- a level ----
struct Level {
  int32_t start = 0;  // the value when the finger landed: a key steps from here, however long it is held
  int32_t given = 0;  // the value its listeners heard last
};

inline bool runs_back(lv_obj_t *s) { return lv_slider_get_min_value(s) > lv_slider_get_max_value(s); }
inline level_bar::Layout layout_of(lv_obj_t *s) {
  const int count = level_bar::steps_for(lv_slider_get_min_value(s), lv_slider_get_max_value(s));
  // A key a finger hits is 5 mm at least; the gap between two blocks reads at arm's length from about half a millimetre.
  return level_bar::layout(lv_obj_get_width(s), lv_obj_get_height(s), count, ui::mm(5), std::max(3, ui::px(5)));
}
// A box of the layout on the glass. A range that counts down lies the other way round, as LVGL draws it.
inline lv_area_t on_glass(lv_obj_t *s, const level_bar::Box &b) {
  lv_area_t a;
  lv_obj_get_coords(s, &a);
  const int w = lv_area_get_width(&a), h = lv_area_get_height(&a);
  const int x = runs_back(s) ? w - b.x - b.w : b.x, y = runs_back(s) ? h - b.y - b.h : b.y;
  return {a.x1 + x, a.y1 + y, a.x1 + x + b.w - 1, a.y1 + y + b.h - 1};
}
// What the finger's place picks now.
inline level_bar::Pick picked(lv_obj_t *s) {
  auto *indev = lv_indev_active();
  if (!indev) return {};
  lv_point_t p;
  lv_indev_get_point(indev, &p);
  lv_area_t a;
  lv_obj_get_coords(s, &a);
  int x = p.x - a.x1, y = p.y - a.y1;
  if (runs_back(s)) {
    x = lv_area_get_width(&a) - 1 - x;
    y = lv_area_get_height(&a) - 1 - y;
  }
  return level_bar::pick(layout_of(s), x, y);
}

inline void level_pressed(lv_event_t *e) {
  auto *s = static_cast<lv_obj_t *>(lv_event_get_target(e));
  auto *level = static_cast<Level *>(lv_event_get_user_data(e));
  level->start = level->given = lv_slider_get_value(s);
}
// LVGL's slider has worked out a value from where the finger is along its whole length. The level's own comes in its
// place before anyone hears of it, and nobody hears twice of the same one.
inline void level_changed(lv_event_t *e) {
  auto *s = static_cast<lv_obj_t *>(lv_event_get_target(e));
  auto *level = static_cast<Level *>(lv_event_get_user_data(e));
  if (!lv_indev_active()) return;  // set by the firmware, not by a finger
  const int low = lv_slider_get_min_value(s), high = lv_slider_get_max_value(s);
  const int count = level_bar::steps_for(low, high);
  const auto pick = picked(s);
  int32_t value = level->start;
  if (pick.kind == level_bar::Pick::MINUS) value = level_bar::step(level->start, -1, low, high, count);
  else if (pick.kind == level_bar::Pick::PLUS) value = level_bar::step(level->start, +1, low, high, count);
  else if (pick.kind == level_bar::Pick::LEVEL) value = level_bar::value_of(pick.level, low, high, count);
  lv_bar_set_value(s, value, LV_ANIM_OFF);
  if (value == level->given) {
    lv_event_stop_processing(e);
    return;
  }
  level->given = value;
}
// The gaps between the blocks show what lies behind: the level never covers its area.
inline void level_covers(lv_event_t *e) {
  static_cast<lv_cover_check_info_t *>(lv_event_get_param(e))->res = LV_COVER_RES_NOT_COVER;
  lv_event_stop_processing(e);
}
inline void level_draw(lv_event_t *e) {
  auto *s = static_cast<lv_obj_t *>(lv_event_get_target(e));
  auto *layer = lv_event_get_layer(e);
  lv_event_stop_processing(e);  // the slider's own track, fill and knob are not drawn
  const theme::LookOf look(s);
  const auto ink = lv_color_hex(theme::hex(theme::INK)), sheet = lv_color_hex(theme::hex(theme::CARD));
  const auto l = layout_of(s);
  const int low = lv_slider_get_min_value(s), high = lv_slider_get_max_value(s);
  const int filled = level_bar::level_of(lv_slider_get_value(s), low, high, l.count);
  lv_draw_rect_dsc_t box;
  lv_draw_rect_dsc_init(&box);
  box.border_color = ink;
  box.border_width = theme::PAPER_RIM;
  box.border_opa = LV_OPA_COVER;
  box.bg_opa = LV_OPA_COVER;
  box.radius = std::max(2, ui::px(4));
  for (int n = 1; n <= l.count; ++n) {
    box.bg_color = n <= filled ? ink : sheet;
    const lv_area_t a = on_glass(s, l.block(n));
    lv_draw_rect(layer, &box, &a);
  }
  if (!l.keys) return;
  // The keys: a ring with a minus or a plus of ink, drawn as bars so they need no font.
  const auto key = [&](const level_bar::Box &where, bool plus) {
    const lv_area_t a = on_glass(s, where);
    box.bg_color = sheet;
    box.radius = LV_RADIUS_CIRCLE;
    lv_draw_rect(layer, &box, &a);
    lv_draw_rect_dsc_t bar;
    lv_draw_rect_dsc_init(&bar);
    bar.bg_color = ink;
    bar.bg_opa = LV_OPA_COVER;
    const int side = lv_area_get_width(&a), arm = side * 2 / 10, thick = std::max(3, side / 14);
    const int cx = (a.x1 + a.x2 + 1) / 2, cy = (a.y1 + a.y2 + 1) / 2;
    const lv_area_t across = {cx - arm, cy - thick / 2, cx + arm - 1, cy - thick / 2 + thick - 1};
    lv_draw_rect(layer, &bar, &across);
    if (!plus) return;
    const lv_area_t down = {cx - thick / 2, cy - arm, cx - thick / 2 + thick - 1, cy + arm - 1};
    lv_draw_rect(layer, &bar, &down);
  };
  key(l.minus, false);
  key(l.plus, true);
}
inline void level_gone(lv_event_t *e) { delete static_cast<Level *>(lv_event_get_user_data(e)); }

inline void dress_level(lv_obj_t *s) {
  auto *level = new Level;
  const auto first = [](lv_event_code_t code) { return static_cast<lv_event_code_t>(code | LV_EVENT_PREPROCESS); };
  lv_obj_add_event_cb(s, level_pressed, first(LV_EVENT_PRESSED), level);
  lv_obj_add_event_cb(s, level_changed, first(LV_EVENT_VALUE_CHANGED), level);
  lv_obj_add_event_cb(s, level_covers, first(LV_EVENT_COVER_CHECK), level);
  lv_obj_add_event_cb(s, level_draw, first(LV_EVENT_DRAW_MAIN), level);
  lv_obj_add_event_cb(s, level_gone, LV_EVENT_DELETE, level);
  lv_obj_invalidate(s);
}

// ---- the pass ----
inline void dress(lv_obj_t *o) {
  if (lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) return;  // dressed when it shows
  if (lv_obj_check_type(o, &lv_slider_class)) {
    if (!lv_obj_has_flag(o, DRESSED)) {
      lv_obj_add_flag(o, DRESSED);
      dress_level(o);
    }
  }
#if LV_USE_SPINNER
  else if (lv_obj_check_type(o, &lv_spinner_class)) {
    lv_anim_delete(o, nullptr);
  }
#endif
  else if (lv_obj_check_type(o, &lv_label_class)) {
    const auto mode = lv_label_get_long_mode(o);
    if (mode == LV_LABEL_LONG_MODE_SCROLL || mode == LV_LABEL_LONG_MODE_SCROLL_CIRCULAR) lv_label_set_long_mode(o, LV_LABEL_LONG_MODE_DOTS);
  }
  for (uint32_t i = 0, n = lv_obj_get_child_count(o); i < n; ++i) dress(lv_obj_get_child(o, i));
}
inline void pass(lv_event_t *e) {
  auto *display = static_cast<lv_display_t *>(lv_event_get_target(e));
  if (auto *screen = lv_display_get_screen_active(display)) dress(screen);
  if (auto *top = lv_display_get_layer_top(display)) dress(top);
  if (auto *sys = lv_display_get_layer_sys(display)) dress(sys);
}
// Starts the pass on the screen's display, once, where the glass is ink.
inline void watch() {
  static bool watching = false;
  if (watching || !paper::is()) return;
  watching = true;
  lv_display_add_event_cb(lv_display_get_default(), pass, LV_EVENT_REFR_START, nullptr);
}

}  // namespace still_glass
#else
namespace still_glass {
inline void watch() {}
}  // namespace still_glass
#endif
