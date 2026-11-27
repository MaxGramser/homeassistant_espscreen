#pragma once
// The ink step of a paper glass (docs/PAPER.md, "Ink"): what a pixel LVGL drew becomes on a panel that prints with a
// few inks instead of sixty thousand colours. A colour that is one of the panel's inks stays that ink. Everything
// between two inks (a see-through layer, a tint, the soft edge of a shape, a picture) becomes a fixed pattern of the
// two, so nothing the UI draws ever vanishes: a word at 40 % still reads, as a raster.
//
// The pattern is ordered (a 4 x 4 Bayer matrix) and hangs on the pixel's own place on the glass, never on what was drawn
// around it or before it. So a part LVGL draws again prints the same dots it printed last time, and a partial refresh,
// which moves only the pixels that changed, has nothing to move in a raster that stayed. An error-diffusing dither
// would shift its dots with every redraw and shimmer; pictures get that kind from the app, before they are sent
// (screen_manager/app/picture_paint.py), where the whole picture is known.
//
// Free of LVGL and ESPHome: the paper glass runs it at every flush (components/paper_glass), the editor's preview and
// the host render run the same function over their own pixels (web/wasm/firmware_preview.cpp, tools/render), so a
// laptop shows what the glass prints. tests/test_paper_ink.cpp walks it.
//
// Today's panels print greys: two inks (black and white) or four (two greys between). A panel with coloured inks
// joins here as a palette: the nearest ink first, then the same raster between the two nearest. Nothing above this
// file changes for it, because the theme already names its colours by what they mean (theme.h, "Ink").
#include <cstdint>

namespace paper_ink {

// Rec. 601 luma of a colour, 0 to 255: the weights ESPHome's e-paper drivers cut on, so a colour this step calls
// white is white to the driver too.
constexpr uint8_t luma(uint8_t r, uint8_t g, uint8_t b) {
  return static_cast<uint8_t>((r * 299U + g * 587U + b * 114U + 500U) / 1000U);
}
// An RGB565 pixel's, its five and six bits widened the way LVGL widens them.
constexpr uint8_t luma565(uint16_t p) {
  const uint8_t r5 = (p >> 11) & 0x1F, g6 = (p >> 5) & 0x3F, b5 = p & 0x1F;
  return luma(static_cast<uint8_t>((r5 << 3) | (r5 >> 2)), static_cast<uint8_t>((g6 << 2) | (g6 >> 4)),
              static_cast<uint8_t>((b5 << 3) | (b5 >> 2)));
}

// How near an ink a colour must be to print as that ink alone. RGB565 and LVGL's mixing lose a few steps, and a page
// that is white but for one dot in sixteen reads as dirt.
constexpr uint8_t NEAR = 20;

// The matrix: each place's own threshold, 0 to 15, every value once, so a grey prints as that share of dots.
constexpr uint8_t BAYER[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};

// The level a luma prints as at (x, y) on a panel of `inks` levels of grey: 0 is the darkest ink, inks - 1 the paper.
// `inks` is 2 or 4; anything else counts as 2.
constexpr uint8_t level(uint8_t l, int x, int y, uint8_t inks) {
  const unsigned steps = inks == 4 ? 3U : 1U;  // the gaps between the inks
  const unsigned scaled = l * steps;           // 0 to 255 * steps
  const unsigned below = scaled / 255U;        // the ink at or under it
  const unsigned rest = scaled - below * 255U; // how far towards the next, 0 to 254
  if (below >= steps) return static_cast<uint8_t>(steps);
  if (rest <= NEAR) return static_cast<uint8_t>(below);
  if (rest >= 255U - NEAR) return static_cast<uint8_t>(below + 1);
  const unsigned threshold = BAYER[y & 3][x & 3] * 16U + 8U;  // 8 to 248
  return static_cast<uint8_t>(rest > threshold ? below + 1 : below);
}

// A level as a grey of 0 to 255, in the middle of the band the driver reads as that ink: black and white for two
// inks; for four, the middles of ESPHome's four bands (under 32, 32 to 95, 96 to 159, 160 and up).
constexpr uint8_t grey(uint8_t lvl, uint8_t inks) {
  if (inks != 4) return lvl ? 255 : 0;
  return lvl == 0 ? 0 : lvl == 1 ? 64 : lvl == 2 ? 128 : 255;
}
constexpr uint16_t grey565(uint8_t g) { return static_cast<uint16_t>(((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)); }

// One RGB565 pixel at (x, y), as the ink it prints.
constexpr uint16_t ink565(uint16_t pixel, int x, int y, uint8_t inks) {
  return grey565(grey(level(luma565(pixel), x, y, inks), inks));
}

// A block of RGB565 pixels as LVGL flushes it: `rows` rows of `columns` pixels read from `source`, whose rows are
// `stride` pixels apart, written tightly into `ink`. The block's first pixel lies at (x, y) on the glass. Two bytes a
// pixel, the high byte first when `big_endian`, in and out alike.
inline void block(const uint8_t *source, uint8_t *ink, int columns, int rows, int stride, int x, int y, bool big_endian,
                  uint8_t inks) {
  for (int row = 0; row < rows; ++row) {
    const uint8_t *in = source + static_cast<long>(row) * stride * 2;
    for (int column = 0; column < columns; ++column, in += 2, ink += 2) {
      const uint16_t pixel = big_endian ? static_cast<uint16_t>((in[0] << 8) | in[1]) : static_cast<uint16_t>((in[1] << 8) | in[0]);
      const uint16_t out = ink565(pixel, x + column, y + row, inks);
      ink[0] = static_cast<uint8_t>(big_endian ? out >> 8 : out & 0xFF);
      ink[1] = static_cast<uint8_t>(big_endian ? out & 0xFF : out >> 8);
    }
  }
}

}  // namespace paper_ink
