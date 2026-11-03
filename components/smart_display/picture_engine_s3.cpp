// The picture engine of an ESP32-S3 with PSRAM (picture_engine.h says what and why): Espressif's software JPEG decoder,
// esp_new_jpeg, with the S3's SIMD, for the stills a screen downloads and a live tile's pictures
// (docs/PICTURE_ARCHITECTURE.md, section 3.2). It decodes baseline JPEG into RGB565 in LVGL's order: a still into a
// picture buffer of its own that LVGL draws, as a BMP's rows went before, and a live tile's picture into its stream's
// buffer, which blit copies onto the glass with the CPU (there is no 2D engine on this chip: no scale and no turn on the
// way).
//
// The panel of an S3 board reads its picture out of PSRAM while it draws, through bounce buffers on the bus the decoder
// writes (packages/hardware/esp32s3-rgb.yaml: one frame shifted sideways when a refill came too late). A BMP's rows came
// as fast as the Wi-Fi brought them; a decode writes a whole picture in tens of milliseconds. So the decoder works in
// blocks of rows (its block mode: one MCU row a call) and lets the bus go between them (BREATH), and the panel's
// refills find room. Its own state and work buffers come from PSRAM (the wraps at the end of this file): asked inside
// the chip, as the library does, they took the internal RAM a Guition 4848S040 has least of down to 33 KB at a camera's
// full-screen stills, against 42 KB with BMP (2026-10-28).
#include "picture_engine.h"
#if defined(PICTURE_ENGINE_S3) && defined(SCREEN_PICTURES)
#include "esphome/core/log.h"

#include <cstring>

#include <esp_err.h>
#include <esp_heap_caps.h>
#include <esp_jpeg_dec.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace picture_engine {

static const char *const TAG = "picture_engine";
// The bus left to the panel after each block of rows the decoder wrote: a tick of FreeRTOS.
constexpr TickType_t BREATH = 1;
// The decoder's output must start on 16 bytes (esp_new_jpeg on the S3, its FAQ: misaligned output otherwise).
constexpr size_t ALIGN = 16;

const std::vector<std::string> &whole_formats() {
  static const std::vector<std::string> formats{"jpeg"};
  return formats;
}
bool start() { return true; }
bool ready() { return true; }
uint8_t *input(size_t bytes, size_t *got) {
  auto *buffer = static_cast<uint8_t *>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (got) *got = buffer ? bytes : 0;
  return buffer;
}
uint8_t *output(size_t bytes, size_t *got) {
  const size_t size = (bytes + ALIGN - 1) & ~(ALIGN - 1);
  auto *buffer = static_cast<uint8_t *>(heap_caps_aligned_calloc(ALIGN, 1, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (got) *got = buffer ? size : 0;
  return buffer;
}

// A decoder for one picture, closed as it goes out of scope; `blocks` for a picture of whole MCUs (block mode: no scale,
// no turn, sides in multiples of 8, which the app's JPEGs are, picture_paint.encode).
struct Decoder {
  jpeg_dec_handle_t handle = nullptr;
  jpeg_dec_io_t io{};
  jpeg_dec_header_info_t header{};
  Decoder(const uint8_t *data, size_t length, bool blocks) {
    jpeg_dec_config_t config = DEFAULT_JPEG_DEC_CONFIG();
    config.output_type = JPEG_PIXEL_FORMAT_RGB565_LE;  // little-endian RGB565, as LVGL's own pixels
    config.block_enable = blocks;
    if (jpeg_dec_open(&config, &this->handle) != JPEG_ERR_OK) {
      this->handle = nullptr;
      return;
    }
    this->io.inbuf = const_cast<uint8_t *>(data);
    this->io.inbuf_len = static_cast<int>(length);
    if (jpeg_dec_parse_header(this->handle, &this->io, &this->header) != JPEG_ERR_OK) this->close();
  }
  ~Decoder() { this->close(); }
  void close() {
    if (this->handle) jpeg_dec_close(this->handle);
    this->handle = nullptr;
  }
  bool ok() const { return this->handle != nullptr; }
};

bool info(const uint8_t *data, size_t length, Still &out) {
  Decoder decoder(data, length, false);
  int bytes = 0;
  if (!decoder.ok() || jpeg_dec_get_outbuf_len(decoder.handle, &bytes) != JPEG_ERR_OK || bytes <= 0) return false;
  out.w = decoder.header.width;
  out.h = decoder.header.height;
  out.stride = decoder.header.width;
  out.bytes = static_cast<size_t>(bytes);
  return true;
}

bool decode_into(const uint8_t *data, size_t length, uint8_t *into, size_t into_size) {
  Still still;
  if (!info(data, length, still) || into_size < still.bytes) return false;
  const bool blocks = still.w % 8 == 0 && still.h % 8 == 0;
  Decoder decoder(data, length, blocks);
  int count = 1;
  if (!decoder.ok() || (blocks && jpeg_dec_get_process_count(decoder.handle, &count) != JPEG_ERR_OK)) return false;
  size_t at = 0;
  for (int i = 0; i < count; ++i) {
    decoder.io.outbuf = into + at;
    if (jpeg_dec_process(decoder.handle, &decoder.io) != JPEG_ERR_OK) return false;
    at += static_cast<size_t>(decoder.io.out_size);
    if (at > into_size) return false;
    if (blocks && i + 1 < count) vTaskDelay(BREATH);
  }
  return true;
}

uint8_t *decode(const uint8_t *data, size_t length, Still &out) {
  Still still;
  if (!info(data, length, still)) return nullptr;
  size_t size = 0;
  uint8_t *pixels = output(still.bytes, &size);
  if (!pixels) {
    ESP_LOGW(TAG, "no memory for a picture of %dx%d", still.w, still.h);
    return nullptr;
  }
  if (!decode_into(data, length, pixels, size)) {
    heap_caps_free(pixels);
    return nullptr;
  }
  out = still;
  out.bytes = size;
  return pixels;
}

// ---- The copy onto the glass: the CPU's ----
Client client() {
  static int token = 0;
  return &token;
}
void drop(Client) {}
int blit(Client, const Block &b) {
  if (b.scale != AS_IS || b.turn != 0 || b.yuv420 || !b.in || !b.out) return ESP_ERR_NOT_SUPPORTED;
  if (b.bx < 0 || b.by < 0 || b.bw <= 0 || b.bh <= 0 || b.bx + b.bw > b.in_w || b.by + b.bh > b.in_rows || b.x < 0 ||
      b.y < 0 || b.x + b.bw > b.out_w || b.y + b.bh > b.out_h ||
      static_cast<size_t>(b.out_w) * b.out_h * 2 > b.out_size)
    return ESP_ERR_INVALID_ARG;
  const auto *in = static_cast<const uint16_t *>(b.in);
  auto *out = static_cast<uint16_t *>(b.out);
  for (int row = 0; row < b.bh; ++row) {
    const uint16_t *from = in + static_cast<size_t>(b.by + row) * b.in_w + b.bx;
    uint16_t *to = out + static_cast<size_t>(b.y + row) * b.out_w + b.x;
    if (!b.swap) {
      memcpy(to, from, static_cast<size_t>(b.bw) * 2);
      continue;
    }
    for (int i = 0; i < b.bw; ++i) to[i] = static_cast<uint16_t>(from[i] << 8 | from[i] >> 8);
  }
  return ESP_OK;
}

}  // namespace picture_engine

// esp_new_jpeg asks for its tables and work buffers inside the chip first (its jpeg_calloc*, internal RAM preferred,
// PSRAM when there is none). On an S3 with an RGB panel the internal RAM is the Wi-Fi's and lwIP's, which must stay there
// (packages/hardware/esp32s3-rgb.yaml), so here the decoder's memory comes from PSRAM first (-Wl,--wrap, engine_build.py).
extern "C" void *__wrap_jpeg_calloc(size_t count, size_t size) {
  return heap_caps_calloc_prefer(count, size, 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}
extern "C" void *__wrap_jpeg_calloc_inner(size_t size) { return __wrap_jpeg_calloc(1, size); }
extern "C" void *__wrap_jpeg_calloc_align(size_t size, int aligned) {
  void *p = heap_caps_aligned_calloc(aligned, 1, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  return p ? p : heap_caps_aligned_calloc(aligned, 1, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}
extern "C" void *__wrap_jpeg_calloc_align_inner(size_t size, int aligned) { return __wrap_jpeg_calloc_align(size, aligned); }
#endif
