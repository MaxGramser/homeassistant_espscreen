#pragma once
// A still glass in LVGL (docs/PAPER.md, "A still glass"): what LVGL's own widgets are on a glass that prints, where a
// change takes a part of a second and nothing can follow a finger or run by itself. One pass over the objects on the
// glass, before each round of drawing, gives every widget of a kind its still form, wherever it was made: a tile, a
// card, the settings, a plugin's card. Nobody who makes a slider asks which glass it is on.
//
// - A slider is a level (level_bar.h): one shape that fills in steps up to its value and, where it is thick enough for
//   a finger, a key at each end. It stays the lv_slider it was, with its range, its value and every listener it had; only what it
//   draws and what a finger's place means are replaced. A tap on a block sets that level, a key takes one step, and
//   listeners hear the value the level has, never one between two blocks.
// - A spinner stands still: an arc that turns would be a refresh every frame.
// - A label that would roll its words is cut with dots.
// - A dark ground that lets what is under it through (a scrim behind a card, a key over a picture) is solid black.
//   Mixed with what lies under it, it is a grey, and a grey prints as a raster in which a word or a glyph is lost
//   (the owner at the first paper screen, 2026-11-27). A pale wash and anything as small as a dot keep their raster:
//   the first is how a tile says it waits, the second how a row of dots says which page this is.
//
// watch() starts it, once, on a glass of ink (packages/core.yaml); on every other screen it is an empty call, and a
// build without a paper glass does not carry the rest of this file.
#include "glass_kind.h"

#ifdef GLASS_MAY_BE_INK
#include <algorithm>
#include <cstdint>

#include "level_bar.h"
#include "still_glass.h"
#include "lvgl.h"
#include "screen_input.h"
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
// The ends the level counts between: the slider's own, without the stub its range keeps past them (level_bar.h).
inline int low_of(lv_obj_t *s) { return level_bar::real_end(lv_slider_get_min_value(s), lv_slider_get_max_value(s)); }
inline int high_of(lv_obj_t *s) { return level_bar::real_end(lv_slider_get_max_value(s), lv_slider_get_min_value(s)); }
inline level_bar::Layout layout_of(lv_obj_t *s) {
  const int count = level_bar::steps_for(low_of(s), high_of(s));
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
  const int low = low_of(s), high = high_of(s);
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
  const int low = low_of(s), high = high_of(s);
  // A slider whose maker shows neither fill nor knob (a lamp that is off keeps its last level under parts that are
  // not drawn) is an empty level: every lamp of a group that was off stood at one step. One with a knob alone (a
  // blind, a tilt, a hue) shows where it stands by its fill here.
  const bool shown = lv_obj_get_style_bg_opa(s, LV_PART_INDICATOR) > LV_OPA_TRANSP || lv_obj_get_style_bg_opa(s, LV_PART_KNOB) > LV_OPA_TRANSP;
  const int filled = shown ? level_bar::level_of(lv_slider_get_value(s), low, high, l.count) : 0;
  // One shape that fills in steps, as the slider of a lit glass fills: a rimmed room, ink from its start up to the
  // level, and a short mark where each step ends, of paper on the ink and of ink on the paper.
  const int thick = l.upright ? lv_obj_get_width(s) : lv_obj_get_height(s);
  const int round = std::max(3, std::min(thick / 4, ui::px(16)));
  lv_draw_rect_dsc_t box;
  lv_draw_rect_dsc_init(&box);
  box.border_color = ink;
  box.border_width = theme::PAPER_RIM;
  box.border_opa = LV_OPA_COVER;
  box.bg_opa = LV_OPA_COVER;
  box.bg_color = sheet;
  box.radius = round;
  const lv_area_t room = on_glass(s, l.blocks);
  lv_draw_rect(layer, &box, &room);
  lv_draw_rect_dsc_t solid;
  lv_draw_rect_dsc_init(&solid);
  solid.bg_opa = LV_OPA_COVER;
  solid.bg_color = ink;
  if (filled > 0) {
    solid.radius = round;
    const lv_area_t f = on_glass(s, l.filled(filled));
    lv_draw_rect(layer, &solid, &f);
    if (filled < l.count) {
      // Its end inside the room is straight: only the room's own ends are round.
      solid.radius = 0;
      lv_area_t end = f;
      if (l.upright) {
        if (f.y1 > room.y1) end.y2 = std::min<int32_t>(f.y2, f.y1 + round);
        else end.y1 = std::max<int32_t>(f.y1, f.y2 - round);
      } else {
        if (f.x2 < room.x2) end.x1 = std::max<int32_t>(f.x1, f.x2 - round);
        else end.x2 = std::min<int32_t>(f.x2, f.x1 + round);
      }
      lv_draw_rect(layer, &solid, &end);
    }
  }
  if (thick >= ui::px(14)) {
    solid.radius = 0;
    const int reach = std::max(4, thick / 8), away = std::max(3, thick / 14), line = thick >= ui::mm(4) ? 2 : 1;
    for (int n = 1; n < l.count; ++n) {
      if (n == filled) continue;  // the level's own edge says it
      const int along = l.mark(n);
      const level_bar::Box mark = l.upright
          ? level_bar::Box{l.blocks.x + l.blocks.w - away - reach, l.blocks.y + l.blocks.h - along - line / 2, reach, line}
          : level_bar::Box{l.blocks.x + along - line / 2, l.blocks.y + l.blocks.h - away - reach, line, reach};
      solid.bg_color = n < filled ? sheet : ink;
      const lv_area_t a = on_glass(s, mark);
      lv_draw_rect(layer, &solid, &a);
    }
  }
  if (!l.keys) return;
  // The keys: the room's own corners and rim, with a minus or a plus of ink drawn as bars, so they need no font.
  const auto key = [&](const level_bar::Box &where, bool plus) {
    const lv_area_t a = on_glass(s, where);
    lv_draw_rect(layer, &box, &a);
    lv_draw_rect_dsc_t bar;
    lv_draw_rect_dsc_init(&bar);
    bar.bg_color = ink;
    bar.bg_opa = LV_OPA_COVER;
    const int side = std::min(lv_area_get_width(&a), lv_area_get_height(&a)), arm = side * 2 / 10, wide = std::max(3, side / 14);
    const int cx = (a.x1 + a.x2 + 1) / 2, cy = (a.y1 + a.y2 + 1) / 2;
    const lv_area_t across = {cx - arm, cy - wide / 2, cx + arm - 1, cy - wide / 2 + wide - 1};
    lv_draw_rect(layer, &bar, &across);
    if (!plus) return;
    const lv_area_t down = {cx - wide / 2, cy - arm, cx - wide / 2 + wide - 1, cy + arm - 1};
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
  // A dark see-through ground of some size, in its own state at rest: solid black.
  if (lv_obj_get_state(o) == LV_STATE_DEFAULT && !lv_obj_check_type(o, &lv_slider_class)) {
    const lv_opa_t opa = lv_obj_get_style_bg_opa(o, LV_PART_MAIN);
    if (opa >= LV_OPA_30 && opa < LV_OPA_COVER && lv_obj_get_width(o) >= ui::mm(4) && lv_obj_get_height(o) >= ui::mm(4) &&
        lv_color_brightness(lv_obj_get_style_bg_color(o, LV_PART_MAIN)) < 128) {
      lv_obj_set_style_bg_color(o, lv_color_black(), 0);
      lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    }
  }
  // Nothing is faded: a part at part strength is a raster through everything in it, so it keeps its ink whole,
  // switched off or not. A card's keys are switched off for the moment a command is on its way (card_blocked): were
  // they taken away instead, every tap would be two prints, the keys going and coming back. Whole in both states they
  // are no print at all. What must not look as if it works is taken away by its maker (a page key that leads
  // nowhere, a stepper's key at its end on the settings page). Set for the state the part is in, and never under a
  // finger, where nothing prints.
  if (const lv_state_t state = lv_obj_get_state(o); !(state & LV_STATE_PRESSED)) {
    const lv_opa_t whole = lv_obj_get_style_opa(o, LV_PART_MAIN);
    if (whole > LV_OPA_TRANSP && whole < LV_OPA_COVER) lv_obj_set_style_opa(o, LV_OPA_COVER, state);
    // Words are ink: at four fifths of their strength a letter has holes in it.
    if (lv_obj_check_type(o, &lv_label_class)) {
      const lv_opa_t words = lv_obj_get_style_text_opa(o, LV_PART_MAIN);
      if (words >= LV_OPA_30 && words < LV_OPA_COVER) lv_obj_set_style_text_opa(o, LV_OPA_COVER, state);
    }
  }
  // A list that is let go stops where the finger left it: gliding on and springing back are a row of prints.
  if (lv_obj_has_flag(o, LV_OBJ_FLAG_SCROLL_MOMENTUM) || lv_obj_has_flag(o, LV_OBJ_FLAG_SCROLL_ELASTIC))
    lv_obj_remove_flag(o, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLL_MOMENTUM | LV_OBJ_FLAG_SCROLL_ELASTIC));
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
  if (watching || !glass_kind::still()) return;
  watching = true;
  // A slider on a lit glass takes a finger let go near the glass's edge for its end, because a drag cannot reach it
  // (screen_input::edge_snap). A level is not dragged, and its end near the edge is a key: with that rule a tap on
  // minus or plus was the lowest or the highest (a reTerminal Sticky, 2026-11-27). So a still glass has no such band.
  screen_input::edge_snap_band = 0;
  lv_display_add_event_cb(lv_display_get_default(), pass, LV_EVENT_REFR_START, nullptr);
}

}  // namespace still_glass
#else
namespace still_glass {
inline void watch() {}
}  // namespace still_glass
#endif
