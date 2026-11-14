#pragma once
// The squeeze of a canvas of square pixels into a panel whose pixels are wider than tall (logical_width): which two
// canvas columns each panel column blends, and in what share. Plain C++, so tests/test_squeeze.cpp checks it on the host.
#include <algorithm>
#include <cstdint>

namespace esphome::mipi_dsi::squeeze {

// Panel column p of `panel` columns over `canvas` columns: its first canvas column << 6 | the second's share, out of 32.
inline uint32_t source(int p, int canvas, int panel) {
  // the centre of panel column p, in canvas columns, in 32nds
  const int at = std::max(0, ((2 * p + 1) * canvas * 32 / panel - 32) / 2);
  const int column = std::min(at / 32, canvas - 2);
  return column << 6 | std::min(32, at - column * 32);
}

// The panel columns, first to last, whose two canvas columns a redraw of canvas columns [x, x + w) touches.
inline void touched(const uint32_t *source, int canvas, int panel, int x, int w, int &first, int &last) {
  first = std::max(0, x * panel / canvas - 2);
  while (first < panel - 1 && int(source[first] >> 6) + 1 < x)
    first++;
  last = std::min(panel - 1, (x + w) * panel / canvas + 2);
  while (last > first && int(source[last] >> 6) > x + w - 1)
    last--;
}

// One panel pixel from a canvas row: RGB565 spread so the three channels blend in one multiply each side.
inline uint16_t blend(const uint16_t *row, uint32_t source) {
  const uint32_t column = source >> 6, share = source & 63;
  uint32_t a = row[column], b = row[column + 1];
  a = (a | a << 16) & 0x07E0F81F;
  b = (b | b << 16) & 0x07E0F81F;
  const uint32_t c = ((a * (32 - share) + b * share) >> 5) & 0x07E0F81F;
  return c | c >> 16;
}

}  // namespace esphome::mipi_dsi::squeeze
