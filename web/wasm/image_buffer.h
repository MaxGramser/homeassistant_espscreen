#pragma once
// Host allocation/pixel sink for the unmodified ESPHome BMP decoder. It creates
// no widgets: runtime_tiles owns the image objects, sizing, clipping and lifetime.
#include <cstdint>
#include <cstddef>
#include <sys/types.h>
#include <vector>
#include "lvgl.h"
#include "host_shims.h"
#define USE_RUNTIME_IMAGE_BMP
#ifndef HOT
#define HOT
#endif
namespace esphome {
struct Color {
  uint8_t r, g, b;
  Color(uint8_t red, uint8_t green, uint8_t blue) : r(red), g(green), b(blue) {}
};
inline uint16_t encode_uint16(uint8_t a, uint8_t b) { return uint16_t(a) << 8 | b; }
inline uint32_t encode_uint32(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
  return uint32_t(a) << 24 | uint32_t(b) << 16 | uint32_t(c) << 8 | d;
}
namespace display {
inline const Color COLOR_ON{255, 255, 255}, COLOR_OFF{0, 0, 0};
}
namespace runtime_image {
class RuntimeImage {
 public:
  std::vector<uint16_t> pixels;
  lv_image_dsc_t descriptor{};
  size_t resize(int w, int h) {
    if (w < 1 || h < 1 || w > 2560 || h > 2560) return 0;
    pixels.resize(size_t(w) * h);
    descriptor = {};
    descriptor.header.magic = LV_IMAGE_HEADER_MAGIC;
    descriptor.header.cf = LV_COLOR_FORMAT_RGB565;
    descriptor.header.w = w; descriptor.header.h = h; descriptor.header.stride = w * 2;
    descriptor.data_size = pixels.size() * 2;
    descriptor.data = reinterpret_cast<const uint8_t *>(pixels.data());
    return descriptor.data_size;
  }
  int get_buffer_width() const { return descriptor.header.w; }
  int get_buffer_height() const { return descriptor.header.h; }
  void draw_pixel(int x, int y, const Color &color) {
    if (x >= 0 && y >= 0 && x < get_buffer_width() && y < get_buffer_height())
      pixels[size_t(y) * get_buffer_width() + x] = lv_color_to_u16(lv_color_make(color.r, color.g, color.b));
  }
  void release() { descriptor = {}; std::vector<uint16_t>().swap(pixels); }
};
}
}
