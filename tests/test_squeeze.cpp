// The squeeze of the JC1060P470 V2's square-pixel canvas into its panel (components/mipi_dsi_v3/squeeze.h): redraws in
// strips give the panel exactly what one redraw of the whole canvas gives, a line one pixel wide never drops out, and a
// flat colour stays that colour.
#include "components/mipi_dsi_v3/squeeze.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
using namespace esphome::mipi_dsi::squeeze;

constexpr int CANVAS = 1074, PANEL = 1024, ROWS = 3;
std::vector<uint32_t> sources(PANEL);
std::vector<uint16_t> canvas(CANVAS *ROWS), panel(PANEL *ROWS);

// What the driver does with a redraw of canvas columns [x, x + w) over every row.
void draw(int x, int w, const uint16_t *pixels) {
  for (int y = 0; y != ROWS; y++)
    std::memcpy(&canvas[y * CANVAS + x], pixels + y * w, w * sizeof(uint16_t));
  int first, last;
  touched(sources.data(), CANVAS, PANEL, x, w, first, last);
  for (int y = 0; y != ROWS; y++)
    for (int p = first; p <= last; p++)
      panel[y * PANEL + p] = blend(&canvas[y * CANVAS], sources[p]);
}

int main() {
  for (int p = 0; p != PANEL; p++)
    sources[p] = source(p, CANVAS, PANEL);
  // The first panel column is the first canvas column, the last one ends on the last canvas column.
  assert(sources[0] == 0);
  assert((sources[PANEL - 1] >> 6) == CANVAS - 2);

  std::srand(1);
  std::vector<uint16_t> picture(CANVAS * ROWS);
  for (auto &pixel : picture)
    pixel = std::rand();
  draw(0, CANVAS, picture.data());
  const auto whole = panel;
  std::fill(canvas.begin(), canvas.end(), 0);
  std::fill(panel.begin(), panel.end(), 0);
  for (int x = 0; x < CANVAS;) {
    const int w = std::min(CANVAS - x, 1 + std::rand() % 40);
    std::vector<uint16_t> strip(w * ROWS);
    for (int y = 0; y != ROWS; y++)
      std::memcpy(&strip[y * w], &picture[y * CANVAS + x], w * sizeof(uint16_t));
    draw(x, w, strip.data());
    x += w;
  }
  assert(panel == whole);

  // A white line one canvas column wide on black: wherever it stands, some panel column shows it at 40 % or more
  // (halfway between two panel columns it is shared about evenly).
  const std::vector<uint16_t> black(CANVAS * ROWS, 0);
  const uint16_t white[ROWS] = {0xFFFF, 0xFFFF, 0xFFFF};
  for (int x = 0; x != CANVAS; x++) {
    draw(0, CANVAS, black.data());
    draw(x, 1, white);
    int brightest = 0;
    for (int p = 0; p != PANEL; p++)
      brightest = std::max(brightest, panel[p] >> 11);
    assert(brightest >= 13);
  }

  const std::vector<uint16_t> flat(CANVAS * ROWS, 0x1234);
  draw(0, CANVAS, flat.data());
  for (auto pixel : panel)
    assert(pixel == 0x1234);
  std::puts("squeeze ok");
}
