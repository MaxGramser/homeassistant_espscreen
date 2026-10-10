// The live view's streams on a P4 (live_view.h says why and what).
//
// Each stream (the full view, a live tile of the page on the glass) is a task of its own with its own buffers and PPA
// client, owned by the main loop: open() makes it, close() and tick() end it. The task reads the stream, decodes each
// picture with the hardware JPEG decoder (one engine for all, its calls are thread safe) and has the PPA bring it to the
// glass: a full view's picture scaled to fill its room and turned as LVGL turns its drawing, straight into the panel's
// frame buffer; a tile's picture first cut or fitted into a canvas of the card's size, where the shade, the corners and
// the name go over it (live_view::compose), and then turned onto the glass. A copy happens with `glass` held and only
// while nobody stopped the stream, so once close() returns nothing of it writes the glass any more and LVGL may draw
// there at once. Buffers live in PSRAM and go when the task has ended (tick()).
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
#include "lvgl_private.h"  // lv_inv_area, lv_area_intersect and the display's list, which LVGL 9 keeps out of lvgl.h

#include <driver/jpeg_decode.h>
#include <driver/ppa.h>
#include <esp_heap_caps.h>
#include <esp_lcd_mipi_dsi.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/stream_buffer.h>
#include <freertos/task.h>
#ifdef USE_SPEAKER
#include "esphome/components/audio/audio.h"
#include "esphome/components/speaker/speaker.h"
#endif

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

// ---- The camera's sound: the board's speaker (features/audio.yaml binds it) ----
#ifdef USE_SPEAKER
static esphome::speaker::Speaker *speaker = nullptr;
void bind_speaker(esphome::speaker::Speaker *s) { speaker = s; }
bool has_speaker() { return speaker != nullptr; }
#else
bool has_speaker() { return false; }
#endif

// ---- One stream ----
struct Stream {
  std::string url;
  Rect area;
  Look look;
  uint32_t *name = nullptr;  // the stream's own copy of look.name
  int turn = 0;
  std::atomic<bool> stopping{false}, done{false}, failed{false};
  // LVGL is kept out of the stream's room from its first picture on (set by the task just before it copies one): until
  // then LVGL draws as ever, a spinner turning while the camera comes.
  std::atomic<bool> armed{false};
  // Where its last picture lies on the glass (LVGL's coordinates): a tile's whole card, a full view's picture as large
  // as fits its room, which leaves room beside it when the camera's shape is not the room's. Written by the task as it
  // copies a picture, read by the main loop: only that is kept from LVGL, which draws the rest of the room itself, and
  // when it moves (a camera's still, then its stream at another size) LVGL draws where it lay again (tick).
  portMUX_TYPE spot_lock = portMUX_INITIALIZER_UNLOCKED;
  Rect spot;
  Rect spot_told;  // the main loop's: the spot it last saw
  std::atomic<uint32_t> shown{0}, bytes{0}, decode_us{0}, copy_us{0}, skipped{0};
  // When the way to the first picture went by (ms after start, written once by the task, read after `shown`).
  uint32_t started_at = 0, connected_ms = 0, answered_ms = 0, first_bytes_ms = 0;
  ppa_client_handle_t ppa = nullptr;
  uint8_t *input = nullptr, *picture = nullptr;
  uint16_t *canvas = nullptr;
  size_t input_size = 0, picture_size = 0, canvas_size = 0;
  // The camera's sound (a full view on a board with a speaker): parts the task puts in `sound`, which the main loop
  // hands to the speaker unless `muted`.
  StreamBufferHandle_t sound = nullptr;
  uint8_t *sound_part = nullptr;
  uint8_t *sound_piece = nullptr;  // what the speaker took part of, the rest of it next tick
  size_t piece_left = 0, piece_at = 0;
  std::atomic<bool> muted{false}, heard{false};
  // The main loop's own: the report of the last REPORT_MS, the first picture and sound told, the speaker started.
  bool told_first = false, told_sound = false, speaking = false;
  uint32_t reported_at = 0, reported_shown = 0, reported_bytes = 0, reported_decode = 0, reported_copy = 0;
};
static Stream *streams[MAX_STREAMS] = {};
static SemaphoreHandle_t glass = nullptr;
static jpeg_decoder_handle_t decoder = nullptr;
static void *frame_buffer = nullptr;

// ---- LVGL stays out of a live picture's room ----
// A card on the page behind the view that changes (a sensor's new value), or a page's own redraw around a live tile,
// has LVGL draw that area again, and what LVGL has there (the view's black, a tile's still with its spinner and name)
// would cover the live picture until its next one. So what LVGL is about to draw is cut against where the picture of
// every stream that streams lies (its spot: a full view's picture may leave room beside it, which stays LVGL's), once, as it starts drawing (LV_EVENT_RENDER_START: its areas joined, nothing drawn yet): what lies
// outside a room stays, in pieces, what lies inside goes. That one place sees every way LVGL comes to draw there: an
// area as it comes, one it had before a stream's first picture, two it joined into one, and the whole glass, which LVGL
// draws when more areas come in one frame than its list holds. A filter of each area as it came missed the last three
// (2026-10-10, the D1001: a tile's spinner and name over its live picture after the camera full screen closed). Each
// piece goes through the display's own rounding (ESPHome's draw_rounding), as LVGL's own areas do. Once a stream ends
// nothing is cut for it, and LVGL draws its room again.
static bool filtering = false;
static lv_area_t lv_rect(const Rect &r) { return {r.x, r.y, r.x + r.w - 1, r.y + r.h - 1}; }
static Rect spot_of(Stream &s) {
  taskENTER_CRITICAL(&s.spot_lock);
  const Rect spot = s.spot;
  taskEXIT_CRITICAL(&s.spot_lock);
  return spot;
}
static void set_spot(Stream &s, const Rect &spot) {
  taskENTER_CRITICAL(&s.spot_lock);
  s.spot = spot;
  taskEXIT_CRITICAL(&s.spot_lock);
}
// What LVGL keeps out of: where the stream's last picture lies.
static lv_area_t room_of(Stream &s) {
  const Rect spot = spot_of(s);
  return lv_rect(spot.empty() ? s.area : spot);
}
static void invalidate(const lv_area_t &part) { lv_inv_area(lv_display_get_default(), &part); }
static bool covered(const lv_area_t &a) {
  for (auto *o : streams) {
    if (!o || !o->armed) continue;
    const lv_area_t room = room_of(*o);
    lv_area_t common;
    if (lv_area_intersect(&common, &a, &room)) return true;
  }
  return false;
}
// `area` less every streaming room, as up to MAX_PIECES rectangles; -1 when that takes more.
constexpr int MAX_PIECES = LV_INV_BUF_SIZE;
static lv_area_t pieces[MAX_PIECES], next_pieces[MAX_PIECES], kept[LV_INV_BUF_SIZE];
static int cut_out(const lv_area_t &area) {
  int count = 1;
  pieces[0] = area;
  for (auto *s : streams) {
    if (!s || !s->armed) continue;
    const lv_area_t room = room_of(*s);
    int made = 0;
    for (int i = 0; i < count; ++i) {
      const lv_area_t r = pieces[i];
      lv_area_t common;
      if (!lv_area_intersect(&common, &r, &room)) {
        if (made == MAX_PIECES) return -1;
        next_pieces[made++] = r;
        continue;
      }
      const lv_area_t parts[4] = {{r.x1, r.y1, r.x2, room.y1 - 1}, {r.x1, room.y2 + 1, r.x2, r.y2},
                                  {r.x1, common.y1, room.x1 - 1, common.y2}, {room.x2 + 1, common.y1, r.x2, common.y2}};
      const bool there[4] = {r.y1 < room.y1, r.y2 > room.y2, r.x1 < room.x1, r.x2 > room.x2};
      for (int k = 0; k < 4; ++k) {
        if (!there[k]) continue;
        if (made == MAX_PIECES) return -1;
        next_pieces[made++] = parts[k];
      }
    }
    count = made;
    for (int i = 0; i < count; ++i) pieces[i] = next_pieces[i];
  }
  return count;
}
static void keep_out(lv_event_t *) {
  lv_display_t *display = lv_display_get_default();
  int count = 0;
  bool whole = false;  // more pieces than LVGL's list holds
  for (uint32_t i = 0; i < display->inv_p && !whole; ++i) {
    if (display->inv_area_joined[i]) continue;
    const lv_area_t &area = display->inv_areas[i];
    if (!covered(area)) {
      kept[count++] = area;  // as LVGL had it, rounded on its way in
      continue;
    }
    const int made = cut_out(area);
    if (made < 0 || count + made > LV_INV_BUF_SIZE) {
      whole = true;
      break;
    }
    for (int k = 0; k < made; ++k) kept[count++] = pieces[k];
  }
  if (whole) {
    // Then the whole glass less the rooms; should even that take too many, LVGL draws what it has, a frame of its own
    // over the live pictures.
    const lv_area_t glass = {0, 0, lv_display_get_horizontal_resolution(display) - 1,
                             lv_display_get_vertical_resolution(display) - 1};
    const int made = cut_out(glass);
    if (made < 0) return;
    count = 0;
    for (int k = 0; k < made; ++k) kept[count++] = pieces[k];
  }
  for (int i = 0; i < count; ++i) {
    lv_display_send_event(display, LV_EVENT_INVALIDATE_AREA, &kept[i]);  // rounding twice changes nothing
    display->inv_areas[i] = kept[i];
    display->inv_area_joined[i] = 0;
  }
  display->inv_p = count;
}
static void watch_lvgl() {
  if (filtering) return;
  lv_display_add_event_cb(lv_display_get_default(), keep_out, LV_EVENT_RENDER_START, nullptr);
  filtering = true;
}
static void unwatch_lvgl_when_alone() {
  for (auto *o : streams)
    if (o) return;
  if (!filtering) return;
  lv_display_remove_event_cb_with_user_data(lv_display_get_default(), keep_out, nullptr);
  filtering = false;
}

static void free_stream(Stream *s) {
  if (s->sound) vStreamBufferDelete(s->sound);
  if (s->sound_part) free(s->sound_part);
  if (s->sound_piece) free(s->sound_piece);
  if (s->input) free(s->input);
  if (s->picture) free(s->picture);
  if (s->canvas) free(s->canvas);
  if (s->name) free(s->name);
  if (s->ppa) ppa_unregister_client(s->ppa);
  delete s;
}

// The PPA's block copy, with its scale and turn: `bw` x `bh` at bx, by of a picture (`stride_w` x `rows`) to x, y of
// another (ow x oh, `out_size` bytes).
static esp_err_t copy(Stream &s, const void *in, int stride_w, int rows, int bx, int by, int bw, int bh, void *out,
                      size_t out_size, int ow, int oh, int x, int y, int sixteenths, int turn) {
  ppa_srm_oper_config_t srm{};
  srm.in.buffer = in;
  srm.in.pic_w = stride_w;
  srm.in.pic_h = rows;
  srm.in.block_w = bw;
  srm.in.block_h = bh;
  srm.in.block_offset_x = bx;
  srm.in.block_offset_y = by;
  srm.in.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  srm.out.buffer = out;
  srm.out.buffer_size = out_size;
  srm.out.pic_w = ow;
  srm.out.pic_h = oh;
  srm.out.block_offset_x = x;
  srm.out.block_offset_y = y;
  srm.out.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  // ESPHome's LVGL turns clockwise, the PPA counter-clockwise.
  srm.rotation_angle = turn == 90    ? PPA_SRM_ROTATION_ANGLE_270
                       : turn == 180 ? PPA_SRM_ROTATION_ANGLE_180
                       : turn == 270 ? PPA_SRM_ROTATION_ANGLE_90
                                     : PPA_SRM_ROTATION_ANGLE_0;
  srm.scale_x = srm.scale_y = sixteenths / 16.0f;
  srm.mode = PPA_TRANS_MODE_BLOCKING;
  return ppa_do_scale_rotate_mirror(s.ppa, &srm);
}

// One picture of `length` bytes in the stream's input: decoded, laid out, and copied onto the glass.
static void show(Stream &s, size_t length) {
  jpeg_decode_picture_info_t info{};
  if (jpeg_decoder_get_info(s.input, length, &info) != ESP_OK) {
    s.skipped++;
    return;
  }
  // The decoder writes whole MCUs: rows as wide as the picture rounded up to 16 (4:2:0, 4:2:2) or 8 pixels.
  const bool wide = info.sample_method == JPEG_DOWN_SAMPLING_YUV420 || info.sample_method == JPEG_DOWN_SAMPLING_YUV422;
  const bool tall = info.sample_method == JPEG_DOWN_SAMPLING_YUV420;
  const int stride_w = (info.width + (wide ? 15 : 7)) & ~(wide ? 15 : 7);
  const int rows = (info.height + (tall ? 15 : 7)) & ~(tall ? 15 : 7);
  const int w = info.width, h = info.height;
  // Where it goes: a full view's picture as large as fits its room, a tile's into its card.
  int sixteenths = 0;
  Rect where;
  Cut into;
  if (s.look.tile) {
    into = cut(w, h, s.area.w, s.area.h, s.look.contain);
    if (into.ok) where = s.area;
  } else {
    where = fit(w, h, s.area, sixteenths);
  }
  if (where.empty()) {
    if (s.skipped++ == 0) ESP_LOGW(TAG, "a picture of %dx%d does not fit its room (%dx%d)", w, h, s.area.w, s.area.h);
    return;
  }
  const size_t need = static_cast<size_t>(stride_w) * rows * 2;
  if (need > s.picture_size) {
    if (s.picture) free(s.picture);
    jpeg_decode_memory_alloc_cfg_t out{.buffer_direction = JPEG_DEC_ALLOC_OUTPUT_BUFFER};
    s.picture = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(need, &out, &s.picture_size));
    if (!s.picture) {
      s.picture_size = 0;
      ESP_LOGW(TAG, "no memory for a picture of %dx%d", w, h);
      s.failed = true;
      s.stopping = true;
      return;
    }
  }
  jpeg_decode_cfg_t cfg{};
  cfg.output_format = JPEG_DECODE_OUT_FORMAT_RGB565;
  cfg.rgb_order = JPEG_DEC_RGB_ELEMENT_ORDER_BGR;  // little-endian RGB565, as LVGL's own pixels
  cfg.conv_std = JPEG_YUV_RGB_CONV_STD_BT601;
  uint32_t written = 0;
  const int64_t t0 = esp_timer_get_time();
  if (jpeg_decoder_process(decoder, &cfg, s.input, length, s.picture, s.picture_size, &written) != ESP_OK) {
    s.skipped++;
    return;
  }
  const int64_t t1 = esp_timer_get_time();
  if (s.shown == 0)
    ESP_LOGD(TAG, "picture %dx%d decoded in %u us, for %dx%d at %d,%d", w, h, (unsigned) (t1 - t0), where.w, where.h,
             where.x, where.y);
  const size_t glass_size = static_cast<size_t>(panel_w) * panel_h * 2;
  esp_err_t err = ESP_OK;
  if (s.look.tile) {
    // The card: the picture cut or fitted into it, on black where it leaves room, then the shade, corners and name.
    const int cw = s.area.w, ch = s.area.h;
    const size_t canvas_need = (static_cast<size_t>(cw) * ch * 2 + 127) & ~static_cast<size_t>(127);
    if (canvas_need > s.canvas_size) {
      if (s.canvas) free(s.canvas);
      s.canvas = static_cast<uint16_t *>(heap_caps_aligned_calloc(128, 1, canvas_need, MALLOC_CAP_SPIRAM));
      s.canvas_size = s.canvas ? canvas_need : 0;
      if (!s.canvas) {
        ESP_LOGW(TAG, "no memory for a card of %dx%d", cw, ch);
        s.failed = true;
        s.stopping = true;
        return;
      }
    }
    if (!into.covers(cw, ch)) memset(s.canvas, 0, static_cast<size_t>(cw) * ch * 2);
    err = copy(s, s.picture, stride_w, rows, into.in_x, into.in_y, into.in_w, into.in_h, s.canvas, s.canvas_size, cw,
               ch, into.out_x, into.out_y, into.sixteenths, 0);
    if (err == ESP_OK) {
      compose(s.canvas, cw, cw, ch, s.look);
      const Rect target = on_panel(s.area, s.turn, panel_w, panel_h);
      xSemaphoreTake(glass, portMAX_DELAY);
      if (!s.stopping) {
        set_spot(s, s.area);
        s.armed = true;  // from now on LVGL draws nothing here
        err = copy(s, s.canvas, cw, ch, 0, 0, cw, ch, frame_buffer, glass_size, panel_w, panel_h, target.x, target.y, 16,
                   s.turn);
      }
      xSemaphoreGive(glass);
    }
  } else {
    // The full view: scaled to fill its room on the way (the app sends the camera's own size where that is smaller).
    const Rect target = on_panel(where, s.turn, panel_w, panel_h);
    xSemaphoreTake(glass, portMAX_DELAY);
    if (!s.stopping) {
      set_spot(s, where);
      s.armed = true;
      err = copy(s, s.picture, stride_w, rows, 0, 0, w, h, frame_buffer, glass_size, panel_w, panel_h, target.x,
                 target.y, sixteenths, s.turn);
    }
    xSemaphoreGive(glass);
  }
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "copy to the glass failed: %s", esp_err_to_name(err));
    s.failed = true;
    s.stopping = true;
    return;
  }
  s.decode_us += static_cast<uint32_t>(t1 - t0);
  s.copy_us += static_cast<uint32_t>(esp_timer_get_time() - t1);
  s.shown++;
}

static void stream(Stream &s) {
  const auto address = picture_fetch::split(s.url);
  const int fd = address.ok ? picture_fetch::connect_to(address, WAIT_MS) : -1;
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", address.host.c_str(), address.port);
    s.failed = true;
    return;
  }
  s.connected_ms = esphome::millis() - s.started_at;
  // HTTP/1.0: the app answers without chunks, and ends the stream by closing it.
  if (!picture_fetch::send_all(fd, "GET " + address.path + " HTTP/1.0\r\nHost: " + address.host + "\r\n\r\n")) {
    ::close(fd);
    s.failed = true;
    return;
  }
  auto *chunk = static_cast<uint8_t *>(heap_caps_malloc(CHUNK, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (!chunk) {
    ::close(fd);
    s.failed = true;
    return;
  }
  Reader reader;
  uint32_t heard = esphome::millis();
  while (!s.stopping) {
    const int n = recv(fd, chunk, CHUNK, 0);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      if (esphome::millis() - heard < QUIET_MS) continue;
      ESP_LOGW(TAG, "the stream went quiet");
      s.failed = true;
      break;
    }
    if (n <= 0) {
      ESP_LOGW(TAG, "the stream ended (%d, errno %d)", n, errno);
      s.failed = true;
      break;
    }
    heard = esphome::millis();
    if (s.bytes == 0) s.first_bytes_ms = heard - s.started_at;
    s.bytes += n;
    const bool ok = reader.feed(
        chunk, n,
        [&s](size_t length, bool audio) -> uint8_t * {
          if (audio) return s.sound && length <= SOUND_PART ? s.sound_part : nullptr;
          return length <= s.input_size ? s.input : nullptr;
        },
        [&s](size_t length, bool audio) {
          if (!audio) {
            show(s, length);
            return;
          }
          // Sound: into the buffer the main loop plays from; none of it while muted, and none when it is full.
          s.heard = true;
          if (!s.muted) xStreamBufferSend(s.sound, s.sound_part, length, 0);
        });
    if (!ok) {
      ESP_LOGW(TAG, "not a stream of pictures (answer %d)", reader.status());
      s.failed = true;
      break;
    }
    if (!s.answered_ms && reader.status()) s.answered_ms = esphome::millis() - s.started_at;
  }
  ::close(fd);
  free(chunk);
}

static void task_main(void *arg) {
  auto *s = static_cast<Stream *>(arg);
  stream(*s);
  s->done.store(true, std::memory_order_release);
  vTaskDelete(nullptr);
}

Handle open(const std::string &url, const Rect &area, const Look &look, bool sound) {
  if (!available() || area.empty()) return -1;
  int slot = -1;
  for (int i = 0; i < MAX_STREAMS && slot < 0; ++i)
    if (!streams[i]) slot = i;
  if (slot < 0) return -1;
  if (!glass) glass = xSemaphoreCreateMutex();
  if (!decoder) {
    jpeg_decode_engine_cfg_t engine{.intr_priority = 0, .timeout_ms = 200};
    if (jpeg_new_decoder_engine(&engine, &decoder) != ESP_OK) decoder = nullptr;
  }
  if (!frame_buffer && esp_lcd_dpi_panel_get_frame_buffer(panel, 1, &frame_buffer) != ESP_OK) frame_buffer = nullptr;
  if (!glass || !decoder || !frame_buffer) {
    ESP_LOGW(TAG, "cannot stream on this panel");
    return -1;
  }
  auto *s = new Stream();
  s->url = url;
  s->area = area;
  s->look = look;
  s->look.name = nullptr;
  s->turn = turn_now();
  s->started_at = s->reported_at = esphome::millis();
  ppa_client_config_t client{};
  client.oper_type = PPA_OPERATION_SRM;
  client.max_pending_trans_num = 1;
  jpeg_decode_memory_alloc_cfg_t in{.buffer_direction = JPEG_DEC_ALLOC_INPUT_BUFFER};
  s->input = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(look.tile ? TILE_PICTURE : MAX_PICTURE, &in, &s->input_size));
  bool ok = s->input && ppa_register_client(&client, &s->ppa) == ESP_OK;
  if (ok && sound && has_speaker()) {
    s->sound = xStreamBufferCreate(SOUND_BUFFER, 1);
    s->sound_part = static_cast<uint8_t *>(heap_caps_malloc(SOUND_PART, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    s->sound_piece = static_cast<uint8_t *>(heap_caps_malloc(SOUND_PART, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    ok = s->sound && s->sound_part && s->sound_piece;
  }
  // The name as LVGL drew it, the stream's own copy: its owner may draw the card again meanwhile.
  if (ok && look.tile && look.name && look.name_w > 0 && look.name_h > 0) {
    s->name = static_cast<uint32_t *>(heap_caps_malloc(static_cast<size_t>(look.name_w) * look.name_h * 4, MALLOC_CAP_SPIRAM));
    ok = s->name != nullptr;
    if (ok) {
      const int stride = look.name_stride ? look.name_stride : look.name_w;
      for (int y = 0; y < look.name_h; ++y)
        memcpy(s->name + static_cast<size_t>(y) * look.name_w, look.name + static_cast<size_t>(y) * stride,
               static_cast<size_t>(look.name_w) * 4);
      s->look.name = s->name;
      s->look.name_stride = look.name_w;
    }
  }
  if (!ok) {
    ESP_LOGW(TAG, "no memory for another stream");
    free_stream(s);
    return -1;
  }
  streams[slot] = s;
  if (xTaskCreatePinnedToCore(task_main, "live_view", 6144, s, 5, nullptr, 1) != pdPASS) {
    streams[slot] = nullptr;
    free_stream(s);
    return -1;
  }
  watch_lvgl();
  ESP_LOGI(TAG, "stream %d into %dx%d at %d,%d%s, turned %d", slot, area.w, area.h, area.x, area.y,
           look.tile ? (look.contain ? " (a tile, whole picture)" : " (a tile)") : "", s->turn);
  return slot;
}

void mute(Handle handle, bool muted) {
  if (handle < 0 || handle >= MAX_STREAMS || !streams[handle]) return;
  streams[handle]->muted = muted;
  if (muted && streams[handle]->sound) xStreamBufferReset(streams[handle]->sound);
}

// The main loop hands a stream's sound to the speaker: it starts once a part of a second waits (so it does not stutter
// at its first gap) and stops with the stream or when muted.
static void speak(Stream &s, bool on) {
#ifdef USE_SPEAKER
  if (!speaker || !s.sound) return;
  if (!on) {
    if (s.speaking) speaker->stop();
    s.speaking = false;
    s.piece_left = 0;
    return;
  }
  if (!s.speaking) {
    if (xStreamBufferBytesAvailable(s.sound) < SOUND_RATE * 2 * 150 / 1000) return;
    speaker->set_audio_stream_info(esphome::audio::AudioStreamInfo(16, 1, SOUND_RATE));
    speaker->start();
    s.speaking = true;
  }
  for (int rounds = 0; rounds < 8; ++rounds) {
    if (s.piece_left == 0) {
      s.piece_left = xStreamBufferReceive(s.sound, s.sound_piece, SOUND_PART, 0);
      s.piece_at = 0;
      if (s.piece_left == 0) return;
    }
    const size_t taken = speaker->play(s.sound_piece + s.piece_at, s.piece_left, 0);
    s.piece_at += taken;
    s.piece_left -= taken;
    if (taken == 0) return;  // the speaker's own buffer is full: the rest next tick
  }
#else
  (void) s;
  (void) on;
#endif
}

void close(Handle handle) {
  if (handle < 0 || handle >= MAX_STREAMS || !streams[handle]) return;
  Stream &s = *streams[handle];
  s.stopping = true;
  // A copy on its way finishes; none starts after this, and LVGL draws there again.
  xSemaphoreTake(glass, portMAX_DELAY);
  const bool was_armed = s.armed.exchange(false);
  xSemaphoreGive(glass);
  if (was_armed) invalidate(lv_rect(s.area));
}

static void report(int slot, Stream &s, uint32_t now, bool last) {
  const uint32_t span = now - s.reported_at;
  if (span == 0) return;
  const uint32_t shown = s.shown, bytes = s.bytes, decode = s.decode_us, copied = s.copy_us;
  const uint32_t frames = shown - s.reported_shown;
  ESP_LOGI(TAG, "%s %d: %.1f pictures/s, %u KB/s, decoding %.1f ms and laying out %.1f ms a picture, %u skipped in all",
           last ? "ended" : "stream", slot, frames * 1000.0f / span, (unsigned) ((bytes - s.reported_bytes) / span),
           frames ? (decode - s.reported_decode) / 1000.0f / frames : 0.0f,
           frames ? (copied - s.reported_copy) / 1000.0f / frames : 0.0f, (unsigned) s.skipped);
  s.reported_at = now;
  s.reported_shown = shown;
  s.reported_bytes = bytes;
  s.reported_decode = decode;
  s.reported_copy = copied;
}

void tick(const std::function<void(Handle, Event)> &tell) {
  const uint32_t now = esphome::millis();
  const int turn = turn_now();
  for (int slot = 0; slot < MAX_STREAMS; ++slot) {
    Stream *s = streams[slot];
    if (!s) continue;
    if (s->done.load(std::memory_order_acquire)) {
      speak(*s, false);
      report(slot, *s, now, true);
      const bool turned = s->turn != turn, ended = s->stopping && !s->failed;
      const bool was_armed = s->armed.exchange(false);
      streams[slot] = nullptr;
      if (was_armed) invalidate(lv_rect(s->area));
      free_stream(s);
      unwatch_lvgl_when_alone();
      tell(slot, turned ? Event::TURNED : ended ? Event::ENDED : Event::FAILED);
      continue;
    }
    // Its picture lies elsewhere now, or at another size: LVGL draws where it lay again (but where it lies now).
    if (s->armed) {
      const Rect spot = spot_of(*s);
      if (!(spot == s->spot_told)) {
        if (!s->spot_told.empty()) invalidate(lv_rect(s->spot_told));
        s->spot_told = spot;
      }
    }
    // The glass turned (a setting): this stream's place is gone; its owner asks again for its new shape.
    if (s->turn != turn && !s->stopping) close(slot);
    speak(*s, !s->stopping && !s->muted);
    if (!s->told_sound && s->heard) {
      s->told_sound = true;
      tell(slot, Event::SOUND);
    }
    if (now - s->reported_at >= REPORT_MS) report(slot, *s, now, false);
    if (!s->told_first && s->shown > 0) {
      s->told_first = true;
      ESP_LOGI(TAG, "stream %d: first picture on the glass %u ms after it started (connected after %u, the app "
               "answered after %u, its first bytes after %u)", slot, (unsigned) (now - s->started_at),
               (unsigned) s->connected_ms, (unsigned) s->answered_ms, (unsigned) s->first_bytes_ms);
      tell(slot, Event::FIRST);
    }
  }
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
