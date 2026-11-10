#pragma once
// A dim over the whole glass in one step (the Dock, an alert, a plugin's popup): the pixels on the glass darkened where
// they are (glass::veil), so LVGL need not draw every tile again to put a layer over them. Knows LVGL's objects and the
// glass; what an overlay holds, its card or its drawer, is its owner's. Where the glass cannot (no frame buffer, a
// stream writing it, LVGL paused) the owner's overlay comes the ordinary way, through LVGL. The sums are glass.h's,
// proved by tests/test_sheet_motion.cpp; on real glass, docs/ARCHITECTURE.md.
#include "glass.h"
#include "lvgl.h"

namespace overlay_dim {

// What LVGL is told while the pixels already show it: it draws nothing for this, and whatever changes later is drawn
// under the dim as it should be.
template <typename Change> inline void quietly(lv_obj_t *over, Change &&change) {
  auto *display = lv_obj_get_display(over);
  lv_display_enable_invalidation(display, false);
  change();
  lv_display_enable_invalidation(display, true);
}

inline uint16_t colour_of(lv_obj_t *over) { return lv_color_to_u16(lv_obj_get_style_bg_color(over, LV_PART_MAIN)); }

inline glass::Rect room_of(lv_obj_t *o) {
  lv_obj_update_layout(lv_obj_get_screen(o));
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  return {a.x1, a.y1, lv_area_get_width(&a), lv_area_get_height(&a)};
}

// What lies over the overlay was darkened with the rest: LVGL draws it again.
inline void redraw_above(lv_obj_t *over) {
  auto *parent = lv_obj_get_parent(over);
  for (uint32_t i = lv_obj_get_index(over) + 1; i < lv_obj_get_child_count(parent); ++i)
    lv_obj_invalidate(lv_obj_get_child(parent, i));
  for (uint32_t i = 0; i < lv_obj_get_child_count(lv_layer_sys()); ++i) lv_obj_invalidate(lv_obj_get_child(lv_layer_sys(), i));
}

// The dim goes on the glass or comes off it, all of it but `keep`; false when the glass cannot, with nothing done.
inline bool lay(lv_obj_t *over, lv_opa_t opa, const glass::Rect &keep, bool on) {
  if (!glass::veil(keep, colour_of(over), opa, on)) return false;
  redraw_above(over);
  return true;
}

// A hidden layer over the whole glass, with `card` on it, shows. The card first and whole, drawn at once by LVGL over
// what will be dim, and then the glass dims around it: the dim takes longer than a frame and a card drawn after it comes
// in pieces of it. Where the glass cannot, LVGL draws the layer the ordinary way.
inline void show(lv_obj_t *over, lv_obj_t *card) {
  if (!lv_obj_has_flag(over, LV_OBJ_FLAG_HIDDEN)) return;
  if (!glass::veilable()) {
    lv_obj_remove_flag(over, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  lv_obj_update_layout(over);  // what it holds has its place, so LVGL has nothing of it to draw over the whole glass later
  quietly(over, [&] { lv_obj_remove_flag(over, LV_OBJ_FLAG_HIDDEN); });
  lv_obj_invalidate(card);
  lv_refr_now(lv_obj_get_display(over));
  if (!lay(over, lv_obj_get_style_bg_opa(over, LV_PART_MAIN), room_of(card), true)) lv_obj_invalidate(over);
}

// The way back in the same order: the card goes first, whole, then the page comes back bright around where it stood.
// LVGL's redraw of the whole glass that follows puts the last bits of each colour right, and the eye has nothing to see
// in it.
inline void hide(lv_obj_t *over, lv_obj_t *card) {
  if (lv_obj_has_flag(over, LV_OBJ_FLAG_HIDDEN)) return;
  if (!glass::veilable()) {
    lv_obj_add_flag(over, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  const glass::Rect room = room_of(card);
  const lv_opa_t opa = lv_obj_get_style_bg_opa(over, LV_PART_MAIN);
  auto *display = lv_obj_get_display(over);
  quietly(over, [&] { lv_obj_add_flag(over, LV_OBJ_FLAG_HIDDEN); });
  lv_area_t area = {room.x, room.y, room.x + room.w - 1, room.y + room.h - 1};
  lv_obj_invalidate_area(lv_display_get_screen_active(display), &area);
  lv_refr_now(display);
  lay(over, opa, room, false);
  lv_obj_invalidate(lv_display_get_screen_active(display));
}

}  // namespace overlay_dim
