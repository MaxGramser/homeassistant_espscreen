#pragma once
#include <algorithm>
#include "lvgl.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"
#include <string>
#include "glass.h"
#ifdef USE_ESP32
#include <esp_heap_caps.h>
#include <cstring>
#endif

// On-demand diagnostic image of LVGL's rendered screen or of the panel's frame buffer: the whole surface, every
// `step`-th pixel each way, so no side is more than 240 pixels (a 1280 x 800 glass comes as 214 x 134, a 480 x 480 one
// as 240 x 240). Rows of at most 240 pixels keep one log line under ESPHome's limit. Nothing is allocated or streamed
// during normal use. The RGB display signal itself still needs a physical visual check.
namespace screen_diagnostics {
inline bool check_geometry(lv_obj_t *obj) {
  if (lv_obj_has_flag(obj, LV_OBJ_FLAG_HIDDEN)) return true;
  bool ok = true;
  lv_area_t area;
  lv_obj_get_coords(obj, &area);
  if (lv_obj_has_flag(obj, LV_OBJ_FLAG_CLICKABLE) &&
      (area.x1 < 0 || area.y1 < 0 || area.x2 >= lv_display_get_horizontal_resolution(lv_display_get_default()) ||
       area.y2 >= lv_display_get_vertical_resolution(lv_display_get_default()))) {
    ESP_LOGE("ui_test", "GEOMETRY FAIL clickable=(%d,%d)-(%d,%d)",
             (int) area.x1, (int) area.y1, (int) area.x2, (int) area.y2);
    ok = false;
  }
  for (uint32_t i = 0; i < lv_obj_get_child_count(obj); ++i)
    ok = check_geometry(lv_obj_get_child(obj, i)) && ok;
  return ok;
}
#if LV_USE_SNAPSHOT
inline lv_draw_buf_t *snapshot = nullptr;
// LVGL's top layer (an alert, a camera full screen) when something is shown on it, with its transparency.
inline lv_draw_buf_t *overlay = nullptr;
inline int snapshot_row = 0;
// The image's size and the source's step, set at the begin.
inline int image_w = 0, image_h = 0, image_step = 1;
// Where the image starts in its source: the whole surface starts at its corner, a part of the glass (glass_part) not.
inline int image_x0 = 0, image_y0 = 0;
inline void image_size(int w, int h) {
  image_x0 = image_y0 = 0;
  image_step = (std::max(w, h) + 239) / 240;
  image_w = (w + image_step - 1) / image_step;
  image_h = (h + image_step - 1) / image_step;
}
// Or what the panel's frame buffer holds (glass_snapshot): LVGL's drawing and a live picture written past it, copied
// whole under the glass's lock, so it is one frame. What only the panel's own scan does (a frame shifted sideways on an
// RGB panel) no copy shows.
inline uint16_t *frame = nullptr;
inline int frame_w = 0;
inline void glass_begin() {
#ifdef USE_ESP32
  const glass::Panel panel = glass::panel();
  auto *buffer = static_cast<const uint16_t *>(glass::frame_buffer());
  if (frame) heap_caps_free(frame);
  frame = nullptr;
  if (!buffer || panel.w <= 0 || panel.h <= 0) {
    ESP_LOGE("ui_image", "IMAGE FAIL no frame buffer to read");
    return;
  }
  const size_t bytes = static_cast<size_t>(panel.w) * panel.h * 2;
  frame = static_cast<uint16_t *>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM));
  if (!frame) {
    ESP_LOGE("ui_image", "IMAGE FAIL allocation");
    return;
  }
  glass::hold();
  memcpy(frame, buffer, bytes);
  glass::release();
  if (panel.swapped)  // as LVGL's own RGB565, so the picture shows its colours
    for (size_t i = 0; i < bytes / 2; ++i) frame[i] = static_cast<uint16_t>(frame[i] << 8 | frame[i] >> 8);
  frame_w = panel.w;
  image_size(panel.w, panel.h);
  snapshot_row = 0;
  // The frame buffer as the panel scans it: a glass LVGL turns comes standing up (the panel's own size).
  ESP_LOGI("ui_image", "IMAGE BEGIN %d %d of the frame buffer, step %d, panel %d x %d", image_w, image_h, image_step, panel.w, panel.h);
#else
  ESP_LOGE("ui_image", "IMAGE FAIL no frame buffer to read");
#endif
}
// A part of the frame buffer at its own size (glass_part): `w` by `h` of the panel's pixels from (`x`, `y`), at most 240
// each way, every one of them. A picture of the whole glass steps over a line one pixel wide (a seam between what LVGL
// drew and what was laid on the glass past it); this shows it. In the panel's own coordinates, as glass_snapshot.
inline void glass_part(int x, int y, int w, int h) {
  glass_begin();
  if (!frame) return;
#ifdef USE_ESP32
  const glass::Panel panel = glass::panel();
  image_step = 1;
  image_w = std::clamp(w, 1, std::min(240, panel.w));
  image_h = std::clamp(h, 1, std::min(240, panel.h));
  image_x0 = std::clamp(x, 0, panel.w - image_w);
  image_y0 = std::clamp(y, 0, panel.h - image_h);
  ESP_LOGI("ui_image", "IMAGE BEGIN %d %d of the frame buffer from %d,%d, every pixel", image_w, image_h, image_x0, image_y0);
#endif
}
// A burst of the frame buffer (glass_burst): the glass now and after each of LVGL's refreshes that follow, at least
// `every` ms apart, up to `count` copies in PSRAM, each with when it was taken. What a change of the whole glass looks
// like in its first moments (a tile that comes back later than the rest). glass_send(n) streams copy n afterwards.
inline uint16_t *burst_frames[8] = {};
inline uint32_t burst_at[8] = {};
inline int burst_count = 0, burst_want = 0, burst_sending = -1;
inline uint32_t burst_every = 0, burst_armed = 0;
inline bool burst_hooked = false;
inline void burst_take() {
#ifdef USE_ESP32
  if (burst_count >= burst_want) return;
  const uint32_t now = esphome::millis();
  if (burst_count && now - (burst_armed + burst_at[burst_count - 1]) < burst_every) return;
  const glass::Panel panel = glass::panel();
  auto *buffer = static_cast<const uint16_t *>(glass::frame_buffer());
  if (!buffer) return;
  const size_t bytes = static_cast<size_t>(panel.w) * panel.h * 2;
  auto *copy = static_cast<uint16_t *>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM));
  if (!copy) { burst_want = burst_count; ESP_LOGW("ui_image", "BURST no room for copy %d", burst_count); return; }
  glass::hold();
  memcpy(copy, buffer, bytes);
  glass::release();
  burst_at[burst_count] = now - burst_armed;
  burst_frames[burst_count++] = copy;
  if (burst_count == burst_want) {
    std::string when;
    for (int i = 0; i < burst_count; ++i) when += (i ? " " : "") + std::to_string(burst_at[i]);
    ESP_LOGI("ui_image", "BURST taken %d copies at ms %s", burst_count, when.c_str());
  }
#endif
}
inline void burst_free() {
#ifdef USE_ESP32
  for (auto *&f : burst_frames) { if (f) heap_caps_free(f); f = nullptr; }
#endif
  burst_count = burst_want = 0;
}
inline void glass_burst(int count, int every) {
  burst_free();
  burst_want = std::clamp(count, 1, 8);
  burst_every = every > 0 ? every : 0;
  burst_armed = esphome::millis();
  if (!burst_hooked && lv_display_get_default()) {
    lv_display_add_event_cb(lv_display_get_default(), [](lv_event_t *) { burst_take(); }, LV_EVENT_REFR_READY, nullptr);
    burst_hooked = true;
  }
  burst_take();  // the glass as it is now, before what follows
}
inline void glass_send(int n) {
#ifdef USE_ESP32
  if (n < 0 || n >= burst_count || !burst_frames[n]) { ESP_LOGE("ui_image", "IMAGE FAIL no burst copy %d", n); return; }
  const glass::Panel panel = glass::panel();
  if (frame) heap_caps_free(frame);
  frame = burst_frames[n];
  burst_frames[n] = nullptr;  // the stream frees it at its end
  if (panel.swapped)
    for (size_t i = 0; i < static_cast<size_t>(panel.w) * panel.h; ++i) frame[i] = static_cast<uint16_t>(frame[i] << 8 | frame[i] >> 8);
  frame_w = panel.w;
  image_size(panel.w, panel.h);
  snapshot_row = 0;
  ESP_LOGI("ui_image", "IMAGE BEGIN %d %d of burst copy %d at %u ms, step %d", image_w, image_h, n, (unsigned) burst_at[n], image_step);
#endif
}
inline void snapshot_begin() {
  if (snapshot) lv_draw_buf_destroy(snapshot);
  if (overlay) lv_draw_buf_destroy(overlay);
  overlay = nullptr;
  snapshot = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_RGB565);
  snapshot_row = 0;
  const int width = lv_display_get_horizontal_resolution(lv_display_get_default());
  const int height = lv_display_get_vertical_resolution(lv_display_get_default());
  if (!snapshot || (int) snapshot->header.w != width || (int) snapshot->header.h != height) {
    if (snapshot) lv_draw_buf_destroy(snapshot);
    snapshot = nullptr;
    ESP_LOGE("ui_image", "IMAGE FAIL allocation/dimensions");
    return;
  }
  for (uint32_t i = 0; i < lv_obj_get_child_count(lv_layer_top()); ++i)
    if (!lv_obj_has_flag(lv_obj_get_child(lv_layer_top(), i), LV_OBJ_FLAG_HIDDEN)) {
      overlay = lv_snapshot_take(lv_layer_top(), LV_COLOR_FORMAT_ARGB8888);
      if (overlay && ((int) overlay->header.w != width || (int) overlay->header.h != height)) { lv_draw_buf_destroy(overlay); overlay = nullptr; }
      break;
    }
  image_size(width, height);
  ESP_LOGI("ui_image", "IMAGE BEGIN %d %d%s, step %d", image_w, image_h, overlay ? " with top layer" : "", image_step);
}
// The top layer's pixel over the page's, as the panel shows them.
inline uint16_t layered(uint16_t pixel, int x, int y) {
  if (!overlay) return pixel;
  const uint8_t *p = overlay->data + y * overlay->header.stride + x * 4;  // B, G, R, A
  const unsigned alpha = p[3];
  if (!alpha) return pixel;
  const unsigned r = ((pixel >> 11) & 31) * 255 / 31, g = ((pixel >> 5) & 63) * 255 / 63, b = (pixel & 31) * 255 / 31;
  const unsigned mr = (p[2] * alpha + r * (255 - alpha)) / 255, mg = (p[1] * alpha + g * (255 - alpha)) / 255,
                 mb = (p[0] * alpha + b * (255 - alpha)) / 255;
  return static_cast<uint16_t>((mr * 31 / 255) << 11 | (mg * 63 / 255) << 5 | (mb * 31 / 255));
}
// Whether an image is on its way: its rows are sent until the last.
inline bool streaming() { return snapshot != nullptr || frame != nullptr; }
inline void snapshot_next_row() {
  if (!snapshot && !frame) return;
  const int y = image_y0 + snapshot_row * image_step;
  const auto *row = frame ? frame + static_cast<size_t>(y) * frame_w
                          : reinterpret_cast<const uint16_t *>(snapshot->data + y * snapshot->header.stride);
  static constexpr char hex[] = "0123456789abcdef";
  char line[961];
  for (int x = 0; x < image_w; ++x) {
    const int at = image_x0 + x * image_step;
    uint16_t pixel = frame ? row[at] : layered(row[at], at, y);
    for (int digit = 0; digit < 4; ++digit)
      line[x * 4 + digit] = hex[(pixel >> (12 - digit * 4)) & 15];
  }
  line[image_w * 4] = 0;
  ESP_LOGI("ui_image", "ROW %03d %s", snapshot_row, line);
  if (++snapshot_row == image_h) {
#ifdef USE_ESP32
    if (frame) heap_caps_free(frame);
#endif
    frame = nullptr;
    if (snapshot) lv_draw_buf_destroy(snapshot);
    snapshot = nullptr;
    if (overlay) lv_draw_buf_destroy(overlay);
    overlay = nullptr;
    ESP_LOGI("ui_image", "IMAGE COMPLETE");
  }
}
#endif
}  // namespace screen_diagnostics
