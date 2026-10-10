// The live view's task on a P4 (live_view.h says why and what).
//
// One stream at a time, owned by the main loop: start() makes the task, stop() and tick() end it. The task reads the
// stream, decodes each picture with the hardware JPEG decoder into a buffer of its own and has the PPA copy it into the
// panel's frame buffer, turned as LVGL turns its drawing, at the place below the top bar the view gave it. The copy
// happens with `glass` held and only while nobody stopped the stream, so once stop() returns nothing of the stream
// writes the glass any more and LVGL may draw the page there at once. Buffers live in PSRAM and go when the task has
// ended (tick()), the decoder and the PPA client stay for the next stream.
#include "live_view.h"
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
#include <atomic>
#include <cerrno>
#include <cstdlib>
#include <sys/socket.h>
#include <unistd.h>

#include "esphome/components/lvgl/lvgl_esphome.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "lvgl.h"
#include "lvgl_private.h"  // lv_inv_area and lv_area_intersect, which LVGL 9 keeps out of lvgl.h

#include <driver/jpeg_decode.h>
#include <driver/ppa.h>
#include <esp_heap_caps.h>
#include <esp_lcd_mipi_dsi.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

namespace live_view {

static const char *const TAG = "live";
constexpr size_t CHUNK = 16 * 1024;
constexpr uint32_t WAIT_MS = 500;  // a read waits this long, so a stop is seen within it

// ---- The panel ESPHome's display made (the wrap of esp_lcd_new_panel_dpi at the end of this file) and LVGL ----
static esp_lcd_panel_handle_t panel = nullptr;
static int panel_w = 0, panel_h = 0;
static bool panel_rgb565 = false;
static esphome::lvgl::LvglComponent *lvgl = nullptr;
void bind(esphome::lvgl::LvglComponent *component) { lvgl = component; }
void panel_made(esp_lcd_panel_handle_t made, const esp_lcd_dpi_panel_config_t *config) {
  panel = made;
  panel_w = config->video_timing.h_size;
  panel_h = config->video_timing.v_size;
  // ESPHome names the frame buffer's format in either field, by ESP-IDF version.
  panel_rgb565 = config->in_color_format == LCD_COLOR_FMT_RGB565 ||
                 (config->in_color_format == 0 && config->pixel_format == LCD_COLOR_PIXEL_FORMAT_RGB565);
}
static int turn_now() { return lvgl ? static_cast<int>(lvgl->get_rotation()) : 0; }

bool available() { return panel != nullptr && panel_rgb565 && lvgl != nullptr; }

// ---- One stream ----
struct Run {
  std::string url;
  Rect area;
  int turn = 0;
  std::atomic<bool> stopping{false}, done{false}, failed{false};
  std::atomic<uint32_t> shown{0}, bytes{0}, decode_us{0}, copy_us{0}, skipped{0};
};
static Run *run = nullptr;
static SemaphoreHandle_t glass = nullptr;
static jpeg_decoder_handle_t decoder = nullptr;
static ppa_client_handle_t ppa = nullptr;
static void *frame_buffer = nullptr;
static uint8_t *input = nullptr, *picture = nullptr;
static size_t input_size = 0, picture_size = 0;
static bool first_told = false;
static uint32_t started_at = 0, reported_at = 0;
// The totals at the last report: each report sums up what came since (the totals may wrap; their differences do not).
static uint32_t reported_shown = 0, reported_bytes = 0, reported_decode = 0, reported_copy = 0;

// ---- LVGL stays out of the picture while it streams ----
// A card on the page behind the view that changes (a sensor's new value) has LVGL draw its area again, the view's black
// page over it included: that black would cover the live picture until its next frame. So every area LVGL is asked to
// draw again is cut: what lies outside the stream's place is drawn as always, what lies over it is not. LVGL 9.5 cannot
// be told to drop an area, so a stand-in takes its place: an area already in LVGL's list (which LVGL then skips), else
// the top bar above the picture. LVGL also sends this event while it draws, to have an area rounded (get_max_row, and
// ESPHome's rounder listens to it for that): those are left alone, since asking LVGL to draw again while it draws
// trips its assert, which spins the main loop until the watchdog restarts the screen (2026-10-10, the D1001).
// Once the stream ends nothing is cut, and the view or the page is drawn there again.
static lv_area_t kept_out{};
static bool keeping_out = false;
static void invalidate(int x1, int y1, int x2, int y2) {
  const lv_area_t part{x1, y1, x2, y2};
  lv_inv_area(lv_display_get_default(), &part);
}
static void keep_out(lv_event_t *e) {
  auto *area = static_cast<lv_area_t *>(lv_event_get_param(e));
  lv_display_t *display = lv_display_get_default();
  lv_area_t common;
  if (!keeping_out || !area || display->rendering_in_progress || !lv_area_intersect(&common, area, &kept_out)) return;
  const lv_area_t whole = *area;
  keeping_out = false;  // the parts outside pass straight through
  if (whole.y1 < kept_out.y1) invalidate(whole.x1, whole.y1, whole.x2, kept_out.y1 - 1);
  if (whole.y2 > kept_out.y2) invalidate(whole.x1, kept_out.y2 + 1, whole.x2, whole.y2);
  if (whole.x1 < kept_out.x1) invalidate(whole.x1, common.y1, kept_out.x1 - 1, common.y2);
  if (whole.x2 > kept_out.x2) invalidate(kept_out.x2 + 1, common.y1, whole.x2, common.y2);
  keeping_out = true;
  if (display->inv_p > 0) *area = display->inv_areas[display->inv_p - 1];
  else *area = lv_area_t{0, 0, lv_display_get_horizontal_resolution(display) - 1, std::max<int32_t>(0, kept_out.y1 - 1)};
}
static void keep_lvgl_out(const Rect &area) {
  kept_out = lv_area_t{area.x, area.y, area.x + area.w - 1, area.y + area.h - 1};
  if (!keeping_out) lv_display_add_event_cb(lv_display_get_default(), keep_out, LV_EVENT_INVALIDATE_AREA, nullptr);
  keeping_out = true;
}
static void let_lvgl_in() {
  if (!keeping_out) return;
  keeping_out = false;
  lv_display_remove_event_cb_with_user_data(lv_display_get_default(), keep_out, nullptr);
  // What the stream left there is not LVGL's: it draws its own again.
  invalidate(kept_out.x1, kept_out.y1, kept_out.x2, kept_out.y2);
}

static void free_buffers() {
  if (input) free(input);
  if (picture) free(picture);
  input = picture = nullptr;
  input_size = picture_size = 0;
}

// One picture of `length` bytes in `input`: decoded, then copied onto the glass, scaled to fill the room it has.
static void show(Run &r, size_t length) {
  jpeg_decode_picture_info_t info{};
  if (jpeg_decoder_get_info(input, length, &info) != ESP_OK) {
    r.skipped++;
    return;
  }
  // The decoder writes whole MCUs: rows as wide as the picture rounded up to 16 (4:2:0, 4:2:2) or 8 pixels.
  const bool wide = info.sample_method == JPEG_DOWN_SAMPLING_YUV420 || info.sample_method == JPEG_DOWN_SAMPLING_YUV422;
  const bool tall = info.sample_method == JPEG_DOWN_SAMPLING_YUV420;
  const uint32_t stride_w = (info.width + (wide ? 15 : 7)) & ~(wide ? 15u : 7u);
  const uint32_t rows = (info.height + (tall ? 15 : 7)) & ~(tall ? 15u : 7u);
  int sixteenths = 0;
  const Rect where = fit(info.width, info.height, r.area, sixteenths);
  if (where.empty()) {
    if (r.skipped++ == 0) ESP_LOGW(TAG, "a picture of %ux%u does not fit below the top bar (%dx%d)", (unsigned) info.width,
                                   (unsigned) info.height, r.area.w, r.area.h);
    return;
  }
  const size_t need = static_cast<size_t>(stride_w) * rows * 2;
  if (need > picture_size) {
    if (picture) free(picture);
    jpeg_decode_memory_alloc_cfg_t out{.buffer_direction = JPEG_DEC_ALLOC_OUTPUT_BUFFER};
    picture = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(need, &out, &picture_size));
    if (!picture) {
      picture_size = 0;
      ESP_LOGW(TAG, "no memory for a picture of %ux%u", (unsigned) info.width, (unsigned) info.height);
      r.failed = true;
      r.stopping = true;
      return;
    }
  }
  jpeg_decode_cfg_t cfg{};
  cfg.output_format = JPEG_DECODE_OUT_FORMAT_RGB565;
  cfg.rgb_order = JPEG_DEC_RGB_ELEMENT_ORDER_BGR;  // little-endian RGB565, as LVGL's own pixels
  cfg.conv_std = JPEG_YUV_RGB_CONV_STD_BT601;
  uint32_t written = 0;
  const int64_t t0 = esp_timer_get_time();
  if (jpeg_decoder_process(decoder, &cfg, input, length, picture, picture_size, &written) != ESP_OK) {
    r.skipped++;
    return;
  }
  const int64_t t1 = esp_timer_get_time();
  if (r.shown == 0)
    ESP_LOGD(TAG, "picture %ux%u decoded in %u us; copying %dx%d to %d,%d of the screen at %d/16", (unsigned) info.width,
             (unsigned) info.height, (unsigned) (t1 - t0), where.w, where.h, where.x, where.y, sixteenths);
  // The PPA turns the picture as ESPHome's LVGL turns its own drawing: its angles go the other way round.
  const Rect target = on_panel(where, r.turn, panel_w, panel_h);
  ppa_srm_oper_config_t srm{};
  srm.in.buffer = picture;
  srm.in.pic_w = stride_w;
  srm.in.pic_h = rows;
  srm.in.block_w = info.width;
  srm.in.block_h = info.height;
  srm.in.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  srm.out.buffer = frame_buffer;
  srm.out.buffer_size = static_cast<uint32_t>(panel_w) * panel_h * 2;
  srm.out.pic_w = panel_w;
  srm.out.pic_h = panel_h;
  srm.out.block_offset_x = target.x;
  srm.out.block_offset_y = target.y;
  srm.out.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  srm.rotation_angle = r.turn == 90    ? PPA_SRM_ROTATION_ANGLE_270
                       : r.turn == 180 ? PPA_SRM_ROTATION_ANGLE_180
                       : r.turn == 270 ? PPA_SRM_ROTATION_ANGLE_90
                                       : PPA_SRM_ROTATION_ANGLE_0;
  // Scaled on the way (fit): the app sends the camera's own size where that is smaller than the glass.
  srm.scale_x = srm.scale_y = sixteenths / 16.0f;
  srm.mode = PPA_TRANS_MODE_BLOCKING;
  xSemaphoreTake(glass, portMAX_DELAY);
  esp_err_t err = ESP_OK;
  if (!r.stopping) err = ppa_do_scale_rotate_mirror(ppa, &srm);
  xSemaphoreGive(glass);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "copy to the glass failed: %s", esp_err_to_name(err));
    r.failed = true;
    r.stopping = true;
    return;
  }
  r.decode_us += static_cast<uint32_t>(t1 - t0);
  r.copy_us += static_cast<uint32_t>(esp_timer_get_time() - t1);
  r.shown++;
}

static void stream(Run &r) {
  const auto address = picture_fetch::split(r.url);
  const int fd = address.ok ? picture_fetch::connect_to(address, WAIT_MS) : -1;
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", address.host.c_str(), address.port);
    r.failed = true;
    return;
  }
  // HTTP/1.0: the app answers without chunks, and ends the stream by closing it.
  if (!picture_fetch::send_all(fd, "GET " + address.path + " HTTP/1.0\r\nHost: " + address.host + "\r\n\r\n")) {
    close(fd);
    r.failed = true;
    return;
  }
  auto *chunk = static_cast<uint8_t *>(heap_caps_malloc(CHUNK, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (!chunk) {
    close(fd);
    r.failed = true;
    return;
  }
  Reader reader;
  uint32_t heard = esphome::millis();
  while (!r.stopping) {
    const int n = recv(fd, chunk, CHUNK, 0);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      if (esphome::millis() - heard < QUIET_MS) continue;
      ESP_LOGW(TAG, "the stream went quiet");
      r.failed = true;
      break;
    }
    if (n <= 0) {
      ESP_LOGW(TAG, "the stream ended (%d, errno %d)", n, errno);
      r.failed = true;
      break;
    }
    heard = esphome::millis();
    r.bytes += n;
    const bool ok = reader.feed(
        chunk, n, [](size_t length) -> uint8_t * { return length <= input_size ? input : nullptr; },
        [&r](size_t length) { show(r, length); });
    if (!ok) {
      ESP_LOGW(TAG, "not a stream of pictures (answer %d)", reader.status());
      r.failed = true;
      break;
    }
  }
  close(fd);
  free(chunk);
}

static void task_main(void *arg) {
  auto *r = static_cast<Run *>(arg);
  stream(*r);
  r->done.store(true, std::memory_order_release);
  vTaskDelete(nullptr);
}

bool start(const std::string &url, const Rect &area) {
  if (!available() || run != nullptr || area.empty()) return false;
  if (!glass) glass = xSemaphoreCreateMutex();
  if (!decoder) {
    jpeg_decode_engine_cfg_t engine{.intr_priority = 0, .timeout_ms = 200};
    if (jpeg_new_decoder_engine(&engine, &decoder) != ESP_OK) decoder = nullptr;
  }
  if (!ppa) {
    ppa_client_config_t client{};
    client.oper_type = PPA_OPERATION_SRM;
    client.max_pending_trans_num = 1;
    if (ppa_register_client(&client, &ppa) != ESP_OK) ppa = nullptr;
  }
  if (!frame_buffer && esp_lcd_dpi_panel_get_frame_buffer(panel, 1, &frame_buffer) != ESP_OK) frame_buffer = nullptr;
  if (!glass || !decoder || !ppa || !frame_buffer) {
    ESP_LOGW(TAG, "cannot stream on this panel");
    return false;
  }
  jpeg_decode_memory_alloc_cfg_t in{.buffer_direction = JPEG_DEC_ALLOC_INPUT_BUFFER};
  input = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(MAX_PICTURE, &in, &input_size));
  if (!input) {
    input_size = 0;
    return false;
  }
  run = new Run();
  run->url = url;
  run->area = area;
  run->turn = turn_now();
  first_told = false;
  started_at = reported_at = esphome::millis();
  reported_shown = reported_bytes = reported_decode = reported_copy = 0;
  if (xTaskCreatePinnedToCore(task_main, "live_view", 6144, run, 5, nullptr, 1) != pdPASS) {
    delete run;
    run = nullptr;
    free_buffers();
    return false;
  }
  keep_lvgl_out(area);
  ESP_LOGI(TAG, "streaming into %dx%d at %d,%d, turned %d", area.w, area.h, area.x, area.y, run->turn);
  return true;
}

void stop() {
  if (!run) return;
  run->stopping = true;
  // A copy on its way finishes; none starts after this, and LVGL draws there again.
  xSemaphoreTake(glass, portMAX_DELAY);
  xSemaphoreGive(glass);
  let_lvgl_in();
}

bool running() { return run != nullptr; }

static void report(uint32_t now, bool last) {
  const uint32_t span = now - reported_at;
  if (span == 0) return;
  const uint32_t shown = run->shown, bytes = run->bytes, decode = run->decode_us, copy = run->copy_us;
  const uint32_t frames = shown - reported_shown;
  ESP_LOGI(TAG, "%s%.1f pictures/s, %u KB/s, decoding %.1f ms and copying %.1f ms a picture, %u skipped in all",
           last ? "ended: " : "", frames * 1000.0f / span, (unsigned) ((bytes - reported_bytes) / span),
           frames ? (decode - reported_decode) / 1000.0f / frames : 0.0f,
           frames ? (copy - reported_copy) / 1000.0f / frames : 0.0f, (unsigned) run->skipped);
  reported_at = now;
  reported_shown = shown;
  reported_bytes = bytes;
  reported_decode = decode;
  reported_copy = copy;
}

Event tick() {
  if (!run) return Event::NONE;
  const uint32_t now = esphome::millis();
  if (run->done.load(std::memory_order_acquire)) {
    report(now, true);
    const bool failed = run->failed, turned = run->turn != turn_now();
    let_lvgl_in();
    delete run;
    run = nullptr;
    free_buffers();
    if (turned) return Event::TURNED;
    return failed ? Event::FAILED : Event::NONE;
  }
  // The glass turned (a setting): this stream's place is gone; the view asks again for its new shape.
  if (run->turn != turn_now()) {
    stop();
    return Event::NONE;  // TURNED once the task has ended
  }
  if (now - reported_at >= REPORT_MS) report(now, false);
  if (!first_told && run->shown > 0) {
    first_told = true;
    ESP_LOGI(TAG, "first picture after %u ms", (unsigned) (now - started_at));
    return Event::FIRST;
  }
  return Event::NONE;
}

}  // namespace live_view

// ESP-IDF makes the DPI panel for ESPHome's display (mipi_dsi, or the repo's mipi_dsi_v3 copy): its handle and its
// size are picked up here as they are made (-Wl,--wrap=esp_lcd_new_panel_dpi, smart_display/__init__.py on a P4).
extern "C" esp_err_t __real_esp_lcd_new_panel_dpi(esp_lcd_dsi_bus_handle_t bus, const esp_lcd_dpi_panel_config_t *config,
                                                   esp_lcd_panel_handle_t *made);
extern "C" esp_err_t __wrap_esp_lcd_new_panel_dpi(esp_lcd_dsi_bus_handle_t bus, const esp_lcd_dpi_panel_config_t *config,
                                                   esp_lcd_panel_handle_t *made) {
  const esp_err_t err = __real_esp_lcd_new_panel_dpi(bus, config, made);
  if (err == ESP_OK && made && config) live_view::panel_made(*made, config);
  return err;
}
#endif
