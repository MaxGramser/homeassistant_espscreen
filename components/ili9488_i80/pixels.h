// RGB565 source pixels -> native 16-bit DMA words. Independent of ESP-IDF for host tests.
#pragma once
#include <cstddef>
#include <cstdint>
namespace esphome::ili9488_i80 {
inline void pack_pixels(uint16_t *dest, const uint8_t *source, size_t count, bool big_endian, bool bgr) {
  for (size_t i = 0; i < count; ++i, source += 2) {
    uint16_t pixel = big_endian ? (uint16_t(source[0]) << 8) | source[1]
                                : source[0] | (uint16_t(source[1]) << 8);
    if (bgr) pixel = (pixel & 0x07E0) | ((pixel & 0x001F) << 11) | ((pixel & 0xF800) >> 11);
    dest[i] = pixel;
  }
}
}  // namespace esphome::ili9488_i80
