// The picture engine of an ESP32-P4 (picture_engine.h says what and why): the hardware JPEG decoder and the PPA, moved
// out of live_view.cpp as they were (docs/PICTURE_ARCHITECTURE.md, section 6, step 4). The decoder's configuration,
// the whole MCUs it writes (picture_jpeg.h), the PPA's block copy with its scale and turn, and the client with the
// glass's bursts are the streams' before the move, written once here for the streams and the stills alike.
#include "picture_engine.h"
#if defined(PICTURE_ENGINE_P4) && defined(SCREEN_PICTURES)
#include <atomic>

#include "esphome/core/log.h"
#include "glass.h"
#include "picture_jpeg.h"

#include <driver/jpeg_decode.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <driver/ppa.h>

namespace picture_engine {

static const char *const TAG = "picture_engine";

// ---- The decoder: one engine for all, its calls are thread safe ----
static jpeg_decoder_handle_t decoder = nullptr;
static std::atomic<bool> stills_on{false};

const std::vector<std::string> &whole_formats() {
  static const std::vector<std::string> formats{"jpeg"};
  return formats;
}
bool start() {
  if (!decoder) {
    jpeg_decode_engine_cfg_t engine{.intr_priority = 0, .timeout_ms = 200};
    if (jpeg_new_decoder_engine(&engine, &decoder) != ESP_OK) decoder = nullptr;
  }
  return decoder != nullptr;
}
bool ready() {
  if (stills_on.load(std::memory_order_acquire)) return true;
  if (!glass::watch() || !start()) return false;
  stills_on.store(true, std::memory_order_release);
  return true;
}
uint8_t *input(size_t bytes, size_t *got) {
  jpeg_decode_memory_alloc_cfg_t in{.buffer_direction = JPEG_DEC_ALLOC_INPUT_BUFFER};
  size_t size = 0;
  auto *buffer = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(bytes, &in, &size));
  if (got) *got = buffer ? size : 0;
  return buffer;
}
uint8_t *output(size_t bytes, size_t *got) {
  jpeg_decode_memory_alloc_cfg_t out{.buffer_direction = JPEG_DEC_ALLOC_OUTPUT_BUFFER};
  size_t size = 0;
  auto *buffer = static_cast<uint8_t *>(jpeg_alloc_decoder_mem(bytes, &out, &size));
  if (got) *got = buffer ? size : 0;
  return buffer;
}
// The decoder's sampling, as picture_jpeg.h counts whole MCUs by it.
static picture_jpeg::Sampling sampling_of(jpeg_down_sampling_type_t method) {
  return method == JPEG_DOWN_SAMPLING_YUV420   ? picture_jpeg::Sampling::YUV420
         : method == JPEG_DOWN_SAMPLING_YUV422 ? picture_jpeg::Sampling::YUV422
                                               : picture_jpeg::Sampling::OTHER;
}
bool info(const uint8_t *data, size_t length, Still &out) {
  jpeg_decode_picture_info_t picture{};
  if (jpeg_decoder_get_info(data, length, &picture) != ESP_OK) return false;
  const picture_jpeg::Sampling sampling = sampling_of(picture.sample_method);
  out.w = picture.width;
  out.h = picture.height;
  out.stride = picture_jpeg::decoded_width(picture.width, sampling);
  out.bytes = static_cast<size_t>(out.stride) * picture_jpeg::decoded_height(picture.height, sampling) * 2;
  return true;
}
// RGB565 in LVGL's order, as every decode of this screen.
static jpeg_decode_cfg_t decode_cfg() {
  jpeg_decode_cfg_t cfg{};
  cfg.output_format = JPEG_DECODE_OUT_FORMAT_RGB565;
  cfg.rgb_order = JPEG_DEC_RGB_ELEMENT_ORDER_BGR;  // little-endian RGB565, as LVGL's own pixels
  cfg.conv_std = JPEG_YUV_RGB_CONV_STD_BT601;
  return cfg;
}
bool decode_into(const uint8_t *data, size_t length, uint8_t *into, size_t into_size) {
  if (!decoder) return false;
  const jpeg_decode_cfg_t cfg = decode_cfg();
  uint32_t written = 0;
  return jpeg_decoder_process(decoder, &cfg, data, length, into, into_size, &written) == ESP_OK;
}
uint8_t *decode(const uint8_t *data, size_t length, Still &out) {
  if (!stills_on.load(std::memory_order_acquire)) return nullptr;
  Still still;
  if (!info(data, length, still)) return nullptr;
  size_t size = 0;
  uint8_t *pixels = output(still.bytes, &size);
  if (!pixels) return nullptr;
  // The glass goes to its highest waiter, and the streams' tasks wait at WRITER_PRIORITY: a download at its own
  // priority 1 waited behind four live tiles for up to two minutes (a reTerminal D1001, 2026-10-25). It waits at theirs,
  // in turn with them, and is back at its own once it let go.
  const UBaseType_t own = uxTaskPriorityGet(nullptr);
  if (own < glass::WRITER_PRIORITY) vTaskPrioritySet(nullptr, glass::WRITER_PRIORITY);
  const int64_t asked = esp_timer_get_time();
  glass::hold();
  const int64_t got = esp_timer_get_time();
  const bool decoded = decode_into(data, length, pixels, size);
  glass::release();
  if (own < glass::WRITER_PRIORITY) vTaskPrioritySet(nullptr, own);
  still.waited_ms = static_cast<uint32_t>((got - asked) / 1000);
  still.held_ms = static_cast<uint32_t>((esp_timer_get_time() - got) / 1000);
  if (!decoded) {
    free(pixels);
    return nullptr;
  }
  out = still;
  out.bytes = size;
  return pixels;
}

// ---- The PPA ----
static_assert(limits().burst_bytes == 64, "the burst below is the engine's");
Client client() {
  ppa_client_config_t config{};
  config.oper_type = PPA_OPERATION_SRM;
  config.max_pending_trans_num = 1;
  config.data_burst_length = PPA_DATA_BURST_LENGTH_64;
  ppa_client_handle_t handle = nullptr;
  if (ppa_register_client(&config, &handle) != ESP_OK) return nullptr;
  return handle;
}
void drop(Client client) {
  if (client) ppa_unregister_client(static_cast<ppa_client_handle_t>(client));
}
int blit(Client client, const Block &b) {
  if (!client) return ESP_ERR_INVALID_STATE;
  if (b.swap) return ESP_ERR_NOT_SUPPORTED;  // no P4 panel ESPHome makes is drawn big-endian
  ppa_srm_oper_config_t srm{};
  srm.in.buffer = b.in;
  srm.in.pic_w = b.in_w;
  srm.in.pic_h = b.in_rows;
  srm.in.block_w = b.bw;
  srm.in.block_h = b.bh;
  srm.in.block_offset_x = b.bx;
  srm.in.block_offset_y = b.by;
  srm.in.srm_cm = b.yuv420 ? PPA_SRM_COLOR_MODE_YUV420 : PPA_SRM_COLOR_MODE_RGB565;
  if (b.yuv420) {
    srm.in.yuv_range = PPA_COLOR_RANGE_LIMIT;
    srm.in.yuv_std = PPA_COLOR_CONV_STD_RGB_YUV_BT601;
  }
  srm.out.buffer = b.out;
  srm.out.buffer_size = b.out_size;
  srm.out.pic_w = b.out_w;
  srm.out.pic_h = b.out_h;
  srm.out.block_offset_x = b.x;
  srm.out.block_offset_y = b.y;
  srm.out.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  // ESPHome's LVGL turns clockwise, the PPA counter-clockwise (ppa_angle).
  srm.rotation_angle = static_cast<ppa_srm_rotation_angle_t>(ppa_angle(b.turn));
  srm.scale_x = srm.scale_y = b.scale / 16.0f;  // sixteenths (fit, cut)
  srm.mode = PPA_TRANS_MODE_BLOCKING;
  return ppa_do_scale_rotate_mirror(static_cast<ppa_client_handle_t>(client), &srm);
}

}  // namespace picture_engine
#endif
