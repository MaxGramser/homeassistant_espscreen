// The touch calibration wizard of a resistive board (cyd_calibration.h holds its state and says why this is a
// compilation unit of its own). A board without the wizard never calls these, and the linker leaves them out.
#include <algorithm>
#include <cmath>
#include "cyd_calibration.h"

namespace screen_calibration {
void prompt(const char *message) {
  if (!message) message = screen_text::tr(screen_text::txt::calibration_hold);
  const Point at = target(point);
  lv_obj_set_pos(cross, at.x-12, at.y-12);
  lv_label_set_text(instructions, screen_text::fill(screen_text::fill(screen_text::txt::calibration_crosshair, "point", (int) point + 1), "tap", std::to_string(sample + 1)).c_str());
  lv_label_set_text(status, message);
}
void begin() {
  if (!screen) return;
  active = true; pressed = false; point = sample = 0;
  if (isolation) isolation(true);
  prompt(); lv_screen_load(screen);
}
void setup(lv_obj_t *home_screen, const lv_font_t *font, const lv_font_t *large,
                  int xmin, int xmax, int ymin, int ymax) {
  if (screen) return;
  home = home_screen;
  // The crosses stand on the canvas the person is looking at, so the wizard works the same on a screen built
  // standing up (firmware 0.2.92+). Which way the panel's axes run under that canvas is not worked out here:
  // the fit measures it from the taps themselves.
  auto *display = lv_display_get_default();
  bind(lv_display_get_horizontal_resolution(display), lv_display_get_vertical_resolution(display));
  calibration.bounds[0]=xmin; calibration.bounds[1]=xmax; calibration.bounds[2]=ymin; calibration.bounds[3]=ymax;
  preference = esphome::global_preferences->make_preference<Calibration>(0x43594403);
  Calibration stored;
  bool valid = preference.load(&stored);
  for (int i = 0; i < 4; ++i) valid &= stored.bounds[i] == calibration.bounds[i];
  for (float coefficient : stored.c) valid &= std::isfinite(coefficient);
  screen = lv_obj_create(nullptr);
  lv_obj_set_style_bg_color(screen, theme::color(theme::CALIBRATION_PAGE), 0);
  lv_obj_set_style_text_color(screen, theme::color(theme::CALIBRATION_INK), 0);
  lv_obj_set_style_text_font(screen, font, 0);
  // Both lines keep a margin from the edges and wrap inside it, so they read on narrow glass too.
  const int text_width = canvas.width - 32;
  instructions = lv_label_create(screen);
  lv_obj_set_style_text_align(instructions, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(instructions, text_width);
  lv_label_set_long_mode(instructions, LV_LABEL_LONG_WRAP);
  lv_obj_align(instructions, LV_ALIGN_CENTER, 0, -40);
  status = lv_label_create(screen);
  lv_obj_set_style_text_align(status, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(status, text_width);
  lv_label_set_long_mode(status, LV_LABEL_LONG_WRAP);
  lv_obj_align(status, LV_ALIGN_BOTTOM_MID, 0, -42);
  cross = lv_label_create(screen); lv_label_set_text(cross, "+");
  lv_obj_set_size(cross, 24, 24); lv_obj_set_style_text_font(cross, large, 0);
  lv_obj_set_style_text_align(cross, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_text_color(cross, theme::color(theme::CALIBRATION_MARK), 0);
  if (valid) { calibration = stored; if (apply) apply(calibration); }
  else begin();
}
void hold(int id, int screen_x, int screen_y, int raw_x, int raw_y) {
  if (!active || !pressed || id != touch_id) return;
  last_screen = {double(screen_x), double(screen_y)};
  last_raw = {double(raw_x), double(raw_y)};
  held = true;
}
void press(int id, int screen_x, int screen_y, int raw_x, int raw_y) {
  if (!active) return;
  down_at = esphome::millis(); pressed = true; held = false; touch_id = (uint8_t) id;
  hold(id, screen_x, screen_y, raw_x, raw_y);
}
// The middle of three taps, as one tap. The median used to be taken per axis and again per half, so the reading
// could come from one tap and the point the screen made of it from another: the same pairs pulled apart, a level
// up. Three taps on one cross may sit up to the spread check apart, so that mix is worth up to that spread. This
// takes the tap that sits closest to the median of the three, and its two halves travel together. A single wild
// tap is still thrown away: it is the one furthest from that middle, so it is never the one picked.
unsigned middle_of(const std::array<Point,3> &three) {
  double xs[3] = {three[0].x, three[1].x, three[2].x}, ys[3] = {three[0].y, three[1].y, three[2].y};
  std::sort(xs, xs + 3); std::sort(ys, ys + 3);
  unsigned best = 0;
  double closest = std::hypot(three[0].x - xs[1], three[0].y - ys[1]);
  for (unsigned i = 1; i < 3; ++i) {
    const double away = std::hypot(three[i].x - xs[1], three[i].y - ys[1]);
    if (away < closest) { closest = away; best = i; }
  }
  return best;
}
void release() {
  if (!active || !pressed) return;
  pressed = false;
  const double raw_x = last_raw.x, raw_y = last_raw.y;
  if (!held || esphome::millis()-down_at < 80 || raw_x < 0 || raw_x > 4095 || raw_y < 0 || raw_y > 4095) { prompt(screen_text::tr(screen_text::txt::calibration_gently)); return; }
  screen_samples[point][sample] = last_screen;
  samples[point][sample++] = last_raw;
  if (sample < 3) { prompt(); return; }
  double xs[3], ys[3];
  for (int i=0;i<3;++i) { xs[i]=samples[point][i].x; ys[i]=samples[point][i].y; }
  std::sort(xs,xs+3); std::sort(ys,ys+3);
  if (xs[2]-xs[0]>180 || ys[2]-ys[0]>180) { sample=0; prompt(screen_text::tr(screen_text::txt::calibration_same)); return; }
  point++; sample=0;
  if (point < 5) { prompt(); return; }
  std::array<Point,5> raw, reported;
  for (unsigned n=0;n<5;++n) {
    const unsigned pick = middle_of(samples[n]);
    raw[n] = samples[n][pick];
    reported[n] = screen_samples[n][pick];
  }
  Calibration next = calibration;
  if (!fit(raw,reported,next)) { point=0;prompt(screen_text::tr(screen_text::txt::calibration_rejected));return; }
  if (!preference.save(&next) || !esphome::global_preferences->sync()) { point=0;prompt(screen_text::tr(screen_text::txt::calibration_save_failed));return; }
  calibration=next;
  if (apply) apply(calibration);
  active=false;
  if (isolation) isolation(false);
  lv_screen_load(home);
}
}  // namespace screen_calibration
