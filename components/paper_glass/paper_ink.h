#pragma once
// The ink step of a paper glass (docs/PAPER.md, "Ink"): what a pixel LVGL drew becomes on a panel that prints with a
// few inks instead of sixty thousand colours. A colour that is one of the panel's inks stays that ink. Everything
// between two inks (a see-through layer, a tint, the soft edge of a shape, a picture) becomes a fixed pattern of the
// two, so nothing the UI draws ever vanishes: a word at 40 % still reads, as a raster.
//
// One kind of in-between is not an area but an edge: the soft pixels LVGL draws along a rounded corner, a slanted
// line or a letter, each a step between the ink on one side of it and the ink on the other. Rastered, such an edge
// frays into loose dots (seen on a reTerminal Sticky, 2026-11-27: the corners of a card). So a pixel that has a
// clearly darker neighbour and a clearly lighter one is an edge and prints as the nearer ink, and only a pixel in an
// even stretch of its own tone, a see-through word, a tint, a picture, gets the raster.
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

// The ink nearest a luma, with no raster: what an edge prints as.
constexpr uint8_t nearest(uint8_t l, uint8_t inks) {
  return inks == 4 ? static_cast<uint8_t>((l * 3U + 127U) / 255U) : static_cast<uint8_t>(l >= 128 ? 1 : 0);
}
// How far a neighbour's luma must lie from a pixel's to count as the other side of an edge.
constexpr uint8_t EDGE = 40;
// Whether a pixel of luma `l` is an edge between two tones: one of its neighbours clearly darker and one clearly
// lighter. `around` holds the lumas of the neighbours there are (a block's rim has fewer).
constexpr bool edge(uint8_t l, const uint8_t *around, int count) {
  bool darker = false, lighter = false;
  for (int i = 0; i < count; ++i) {
    darker = darker || around[i] + EDGE <= l;
    lighter = lighter || around[i] >= l + EDGE;
  }
  return darker && lighter;
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

// What a luma prints as wherever it stands, or BETWEEN for one that lies between two inks and so depends on its place
// and on what is around it. Most of a page is paper and ink, so block() reads this once a pixel and looks no further.
constexpr uint8_t BETWEEN = 0xFF;
struct Plain {
  uint8_t level[256];
};
constexpr Plain plain_of(uint8_t inks) {
  Plain p{};
  const unsigned steps = inks == 4 ? 3U : 1U;
  for (unsigned l = 0; l < 256; ++l) {
    const unsigned rest = (l * steps) % 255U;
    p.level[l] = (l == 255 || rest <= NEAR || rest >= 255U - NEAR) ? level(static_cast<uint8_t>(l), 0, 0, inks) : BETWEEN;
  }
  return p;
}
inline constexpr Plain PLAIN2 = plain_of(2), PLAIN4 = plain_of(4);

// A block of RGB565 pixels as LVGL flushes it: `total_rows` rows of `columns` pixels at `source`, whose rows are
// `stride` pixels apart, with its first pixel at (x, y) on the glass. The rows from `first` on, `rows` of them, are
// written tightly into `ink`; the rows around them are read for what lies beside a pixel. Two bytes a pixel, the high
// byte first when `big_endian`, in and out alike. `rastered`, where given, gets a byte for each pixel written: 1 for
// one printed as a raster (between two inks, in an even stretch of its tone), else 0. The host render's ink audit
// reads it (tools/render/paper_ink_tool.cpp); a screen passes none.
//
// This runs over every pixel LVGL draws, a whole glass at a turn of a page (384 000 on a reTerminal Sticky, where the
// first version took 280 ms of a turn and this one 93 ms, measured 2026-11-27). So a row is walked with one pointer,
// and a pixel that is an ink, which most are, costs one look in a table.
inline void block(const uint8_t *source, uint8_t *ink, int columns, int total_rows, int stride, int first, int rows,
                  int x, int y, bool big_endian, uint8_t inks, uint8_t *rastered = nullptr) {
  const Plain &plain = inks == 4 ? PLAIN4 : PLAIN2;
  const int high = big_endian ? 0 : 1, low = 1 - high;  // where a pixel's high and low byte lie
  const auto luma_of = [high, low](const uint8_t *in) {
    return luma565(static_cast<uint16_t>((in[high] << 8) | in[low]));
  };
  // Each level as the two bytes it is written as.
  uint8_t bytes[4][2] = {};
  for (uint8_t lvl = 0; lvl < (inks == 4 ? 4 : 2); ++lvl) {
    const uint16_t out = grey565(grey(lvl, inks));
    bytes[lvl][high] = static_cast<uint8_t>(out >> 8);
    bytes[lvl][low] = static_cast<uint8_t>(out & 0xFF);
  }
  const long step = static_cast<long>(stride) * 2;
  for (int row = first; row < first + rows; ++row) {
    const uint8_t *in = source + row * step;
    for (int column = 0; column < columns; ++column, in += 2, ink += 2) {
      const uint8_t l = luma_of(in);
      uint8_t lvl = plain.level[l];
      bool raster = false;
      if (lvl == BETWEEN) {
        // Between two inks: an edge prints as the nearer ink, an even stretch as its raster.
        uint8_t around[4];
        int count = 0;
        if (column > 0) around[count++] = luma_of(in - 2);
        if (column + 1 < columns) around[count++] = luma_of(in + 2);
        if (row > 0) around[count++] = luma_of(in - step);
        if (row + 1 < total_rows) around[count++] = luma_of(in + step);
        raster = !edge(l, around, count);
        lvl = raster ? level(l, x + column, y + row, inks) : nearest(l, inks);
      }
      if (rastered) *rastered++ = raster;
      ink[0] = bytes[lvl][0];
      ink[1] = bytes[lvl][1];
    }
  }
}

}  // namespace paper_ink
