#pragma once
// A cover's paint (firmware 0.57.0), shared by its tile, its card and a cover group's page: Home Assistant's purple for
// covers and its tints, the slats of a tilt slider at the angle the blind stands at (cover_tile::slats), and the lying
// tilt slider with those slats behind its accent handle. One drawing, wherever a blind's slats show.
#include <algorithm>
#include <cmath>
#include "lvgl.h"
#include "cover_tile.h"
#include "theme.h"
#include "ui_scale.h"

namespace cover_paint {
// Home Assistant's purple for covers; the track and the slats are its tints.
inline constexpr uint32_t ACCENT = theme::ha::PURPLE;
inline uint32_t track() { return theme::tint(ACCENT, 37); }
inline uint32_t slats() { return theme::tint(ACCENT, 80); }

// The slats behind a tilt slider's handle, at the angle the slider stands at: drawn by the slider itself just before its
// handle (LV_EVENT_DRAW_MAIN_BEGIN), so they turn with every value it takes, a finger's or Home Assistant's, and cost no
// objects of their own. Pale, so the handle stays what the eye takes first.
inline void slats_draw(lv_event_t *e) {
  auto *slider = lv_event_get_target_obj(e);
  lv_area_t a;
  lv_obj_get_coords(slider, &a);
  const float tilt = std::clamp(lv_slider_get_value(slider) / 10.0f, 0.0f, 100.0f);
  const auto s = cover_tile::slats(lv_area_get_width(&a), lv_area_get_height(&a), tilt, ui::mm(3), std::max(3, ui::mm(1) + 1));
  lv_draw_line_dsc_t d;
  lv_draw_line_dsc_init(&d);
  d.color = lv_color_hex(slats());
  d.width = s.width;
  d.round_start = d.round_end = 1;
  for (int i = 0; i < s.count; ++i) {
    const auto &l = s.slat[i];
    d.p1 = {(lv_value_precise_t) std::lround(a.x1 + l.x1), (lv_value_precise_t) std::lround(a.y1 + l.y1)};
    d.p2 = {(lv_value_precise_t) std::lround(a.x1 + l.x2), (lv_value_precise_t) std::lround(a.y1 + l.y2)};
    lv_draw_line(lv_event_get_layer(e), &d);
  }
}

// A tilt slider lying across `w` x `h`: the track behind it, the slats, and an upright accent handle a third of its
// height. Its value is the tilt times ten; a margin past both ends keeps the handle on the track at 0 and 100 %.
inline lv_obj_t *tilt_bar(lv_obj_t *parent, int x, int y, int w, int h, float value) {
  const int radius = h > 20 ? h * 12 / 42 : LV_RADIUS_CIRCLE, handle = std::max(4, h / 9), inset = std::max(4, h / 6);
  auto *back = lv_obj_create(parent);
  lv_obj_remove_style_all(back);
  lv_obj_remove_flag(back, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(back, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(back, x, y);
  lv_obj_set_size(back, w, h);
  lv_obj_set_style_radius(back, radius, 0);
  lv_obj_set_style_bg_color(back, lv_color_hex(track()), 0);
  lv_obj_set_style_bg_opa(back, LV_OPA_COVER, 0);
  auto *slider = lv_slider_create(parent);
  lv_obj_remove_style_all(slider);
  lv_obj_set_pos(slider, x, y);
  lv_obj_set_size(slider, w, h);
  lv_slider_set_orientation(slider, LV_SLIDER_ORIENTATION_HORIZONTAL);
  lv_obj_set_style_radius(slider, radius, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(slider, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(slider, LV_OPA_TRANSP, LV_PART_INDICATOR);
  lv_obj_set_style_opa(slider, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_set_style_bg_color(slider, lv_color_hex(ACCENT), LV_PART_KNOB);
  lv_obj_set_style_bg_opa(slider, LV_OPA_COVER, LV_PART_KNOB);
  lv_obj_set_style_radius(slider, LV_RADIUS_CIRCLE, LV_PART_KNOB);
  // LVGL's knob is a square as high as the bar; the pads make it an upright handle.
  const int across = -(h - 2 * handle) / 2, along = -(h - h * 3 / 5) / 2;
  lv_obj_set_style_pad_left(slider, across, LV_PART_KNOB);
  lv_obj_set_style_pad_right(slider, across, LV_PART_KNOB);
  lv_obj_set_style_pad_top(slider, along, LV_PART_KNOB);
  lv_obj_set_style_pad_bottom(slider, along, LV_PART_KNOB);
  const int margin = 1000 * (inset + handle) / std::max(1, w - 2 * (inset + handle));
  lv_slider_set_range(slider, -margin, 1000 + margin);
  lv_slider_set_value(slider, std::isfinite(value) ? (int) std::lround(std::clamp(value, 0.0f, 100.0f) * 10) : 500, LV_ANIM_OFF);
  lv_obj_add_event_cb(slider, slats_draw, LV_EVENT_DRAW_MAIN_BEGIN, nullptr);
  return slider;
}
}  // namespace cover_paint
