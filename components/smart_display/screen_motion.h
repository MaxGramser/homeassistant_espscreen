#pragma once
// Motion: the one layer the UI asks for anything that moves or changes over the whole glass (docs/MOTION.md). A card,
// the Dock or a plugin says what happens (an overlay shows, a sheet is let go, the whole glass changes) and this layer
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
//   cut           the whole glass changes behind the backlight: dark, drawn at once, lit again
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

// ---- The whole glass changes ----
// The backlight, as the screen's own scripts drive it: dark at once, and back to the level the screen should have now
// over `ms`. Set where the backlight lives (features/backlight.yaml); without them a cut is the change alone.
inline std::function<void()> dark;
inline std::function<void(int ms)> lit;
// The dark is as short as the drawing: the light goes out, one step later the change is made and LVGL draws the whole of
// it at once, and the light comes up. Waiting for the page to come to rest instead kept a page with a live tile or a
// playing song dark for half a second (a camera on the glass, 2026-11-10): what still changes after the first whole
// drawing is the page's ordinary life.
constexpr uint32_t CUT_STEP_MS = 12, CUT_LIT_MS = 100;
struct Cut {
  std::function<void()> change;
  lv_timer_t *timer = nullptr;
  bool own = false;
};
inline Cut cutting;
// For the backlight's script: the light is the cut's until it ends, so no other writer brings it up over a page that is
// still being drawn. The cut's own calls pass.
inline bool holds_light() { return cutting.timer && !cutting.own; }
inline void cut_light(bool up) {
  cutting.own = true;
  if (up) lit(CUT_LIT_MS);
  else dark();
  cutting.own = false;
}
inline void cut_step(lv_timer_t *) {  // a timer of one run: it deletes itself
  auto change = std::move(cutting.change);
  cutting.change = nullptr;
  if (change) change();
  lv_refr_now(nullptr);
  cut_light(true);
  cutting.timer = nullptr;
}
// `change` makes the glass another (the screensaver goes, the page under it comes): LVGL would draw that strip by
// strip in sight. So the light goes out, the change is made and drawn in the dark, and the light comes up on the whole
// of it: one movement, out and in. A second change while one waits joins it, in the same dark. On a screen without
// motion, without the light's hooks or with LVGL paused the change is made at once, as ever.
inline void cut(std::function<void()> change) {
  if (cutting.timer) {
    cutting.change = [first = std::move(cutting.change), second = std::move(change)]() {
      if (first) first();
      second();
    };
    return;
  }
  if (!able() || !dark || !lit || !glass::drawing()) {
    change();
    return;
  }
  cutting.change = std::move(change);
  cutting.timer = lv_timer_create(cut_step, CUT_STEP_MS, nullptr);
  lv_timer_set_repeat_count(cutting.timer, 1);
  cut_light(false);
}

}  // namespace screen_motion
