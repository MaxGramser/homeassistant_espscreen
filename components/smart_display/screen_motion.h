#pragma once
// Motion: the one layer the UI asks for anything that moves or changes over the whole glass (docs/MOTION.md). A card,
// the Dock or a plugin says what happens (an overlay shows, a sheet is let go) and this layer
// picks how this screen does it. It knows LVGL's objects, the glass and the capability record; nothing of a board, a
// chip or what an overlay holds.
//
// The hard rule: a screen has motion only when hw::caps().motion says so (hw.h: a full-tier screen with a frame buffer a
// task may write). Every other screen, the CYD first, gets the plain LVGL way from the same calls, with no cost in
// time and none it could avoid in flash. A new board takes its side of the rule from its hardware, never by name.
//
// The blocks:
//   show / hide   an overlay with a card over a dimmed page: the card first and whole, then the page dims around it on
//                 the glass itself (glass::veil), and the way back in the same order
//   dim           the dim alone, for an overlay that moves its own part (the Dock's drawer)
//   settle        what a finger let go travels on at the finger's speed and comes to rest (sheet_motion.h)
// The sums are pure (glass.h, sheet_motion.h; tests/test_sheet_motion.cpp); the rule is hw.h's (tests/test_hw.cpp).
#include <algorithm>
#include <cstdint>
#include <functional>

#include "glass.h"
#include "hw.h"
#include "lvgl.h"
#include "sheet_motion.h"

namespace screen_motion {

// The rule, in one place.
inline bool able() { return hw::caps().motion; }

// ---- An overlay over a dimmed page ----
// What LVGL is told while the pixels already show it: it draws nothing for this, and whatever changes later is drawn
// under the dim as it should be.
template <typename Change> inline void quietly(lv_obj_t *over, Change &&change) {
  auto *display = lv_obj_get_display(over);
  lv_display_enable_invalidation(display, false);
  change();
  lv_display_enable_invalidation(display, true);
}
// The room LVGL draws for `o`, which is what the dim keeps off: its place through the display's own rounding (ESPHome's
// draw_rounding, as glass_core.cpp's rooms go through it), because that is the area LVGL redraws when the card is
// invalidated. A card on an odd pixel has a rim of a pixel around it that LVGL drew, dim and all; with the card's bare
// place kept, the veil dimmed that rim a second time and it stood as a dark line around the card (a Guition 10.1,
// 2026-11-22).
inline glass::Rect room_of(lv_obj_t *o) {
  lv_obj_update_layout(lv_obj_get_screen(o));
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  lv_display_send_event(lv_obj_get_display(o), LV_EVENT_INVALIDATE_AREA, &a);
  return {a.x1, a.y1, lv_area_get_width(&a), lv_area_get_height(&a)};
}
// What lies over the overlay was darkened with the rest: LVGL draws it again.
inline void redraw_above(lv_obj_t *over) {
  auto *parent = lv_obj_get_parent(over);
  for (uint32_t i = lv_obj_get_index(over) + 1; i < lv_obj_get_child_count(parent); ++i)
    lv_obj_invalidate(lv_obj_get_child(parent, i));
  for (uint32_t i = 0; i < lv_obj_get_child_count(lv_layer_sys()); ++i) lv_obj_invalidate(lv_obj_get_child(lv_layer_sys(), i));
}
// Whether the dim can go on the glass now: this screen has motion, and nothing else writes the glass.
inline bool dims() { return able() && glass::veilable(); }
// The dim of `over`'s colour at `opa` goes on the glass or comes off it, all of it but `keep`; false, with nothing
// done, when it cannot. The caller tells LVGL (quietly).
inline bool dim(lv_obj_t *over, lv_opa_t opa, const glass::Rect &keep, bool on) {
  if (!able() || !glass::veil(keep, lv_color_to_u16(lv_obj_get_style_bg_color(over, LV_PART_MAIN)), opa, on)) return false;
  redraw_above(over);
  return true;
}
// A hidden layer over the whole glass, with `card` on it, shows. The card first and whole, drawn at once by LVGL over
// what will be dim, and then the glass dims around it: the dim takes longer than a frame and a card drawn after it comes
// in pieces of it.
inline void show(lv_obj_t *over, lv_obj_t *card) {
  if (!lv_obj_has_flag(over, LV_OBJ_FLAG_HIDDEN)) return;
  if (!dims()) {
    lv_obj_remove_flag(over, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  // What LVGL still has to draw is drawn first, with the overlay still hidden. A wake from standby leaves it the whole
  // screen (the sheet that took the waking tap goes); drawn after the overlay is revealed, that redraw carried the
  // overlay's own scrim over the whole glass, and the dim laid on the glass then darkened the page a second time (an
  // alert that arrived in standby, a Guition 10.1 in the light look, 2026-11-24). With nothing left to draw this is free.
  lv_refr_now(lv_obj_get_display(over));
  lv_obj_update_layout(over);  // what it holds has its place, so LVGL has nothing of it to draw over the whole glass later
  quietly(over, [&] { lv_obj_remove_flag(over, LV_OBJ_FLAG_HIDDEN); });
  lv_obj_invalidate(card);
  lv_refr_now(lv_obj_get_display(over));
  if (!dim(over, lv_obj_get_style_bg_opa(over, LV_PART_MAIN), room_of(card), true)) lv_obj_invalidate(over);
}
// The way back in the same order: the card goes first, whole, then the page comes back bright around where it stood.
// LVGL's redraw of the whole glass that follows puts the last bits of each colour right, and the eye has nothing to see
// in it.
inline void hide(lv_obj_t *over, lv_obj_t *card) {
  if (lv_obj_has_flag(over, LV_OBJ_FLAG_HIDDEN)) return;
  if (!dims()) {
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
  dim(over, opa, room, false);
  lv_obj_invalidate(lv_display_get_screen_active(display));
}

// ---- What a finger let go ----
// `o` goes from `from` to `to` through `set`, starting at `speed` (px a second, towards `to` positive) and coming to
// rest there: `full` is the whole way such a part can go, and the time lies between `shortest` and the share of
// `longest` that the part left is of it. Plain LVGL, so every screen has it.
inline int32_t settled_at(const lv_anim_t *a) {
  return sheet_motion::at(a->start_value, a->end_value, static_cast<int32_t>(reinterpret_cast<intptr_t>(a->user_data)), a->act_time, a->duration);
}
inline void settle(lv_obj_t *o, lv_anim_exec_xcb_t set, int32_t from, int32_t to, int speed, int full, uint32_t shortest,
                   uint32_t longest, lv_anim_completed_cb_t done = nullptr) {
  const auto s = sheet_motion::settle(std::abs(to - from), speed, full, shortest, longest);
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, o);
  lv_anim_set_exec_cb(&a, set);
  lv_anim_set_values(&a, from, to);
  lv_anim_set_duration(&a, s.ms);
  lv_anim_set_path_cb(&a, settled_at);
  lv_anim_set_user_data(&a, reinterpret_cast<void *>(static_cast<intptr_t>(s.lead)));
  if (done) lv_anim_set_completed_cb(&a, done);
  set(o, from);
  lv_anim_start(&a);
}

}  // namespace screen_motion
