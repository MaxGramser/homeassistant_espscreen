// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_paper_ink.cpp -o /tmp/test_paper_ink && /tmp/test_paper_ink
// The ink step of a paper glass (paper_ink.h): a colour that is an ink stays it, everything between becomes a raster
// that hangs on the pixel's place, and the greys it writes are greys ESPHome's drivers read as the same ink.
#include "../components/paper_glass/paper_ink.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

using namespace paper_ink;

// ESPHome's own cuts (esphome/components/epaper_spi/colorconv.h, display_color_utils.h): black and white at a luma of
// 128, four greys at 32, 96 and 160.
static int driver_mono(uint8_t l) { return l >= 128 ? 1 : 0; }
static int driver_grey4(uint8_t l) { const int level = (l + 32) >> 6; return level > 3 ? 3 : level; }

static int dots(uint8_t l, uint8_t inks, uint8_t lvl) {
  int n = 0;
  for (int y = 0; y < 4; ++y)
    for (int x = 0; x < 4; ++x) n += level(l, x, y, inks) == lvl;
  return n;
}

static void an_ink_stays_an_ink() {
  for (int y = 0; y < 8; ++y)
    for (int x = 0; x < 8; ++x) {
      assert(ink565(0x0000, x, y, 2) == 0x0000);
      assert(ink565(0xFFFF, x, y, 2) == 0xFFFF);
      assert(ink565(0x0000, x, y, 4) == 0x0000);
      assert(ink565(0xFFFF, x, y, 4) == 0xFFFF);
      // A colour a few steps from an ink (RGB565's rounding, the last bits of a mix) is that ink, without a stray dot.
      assert(level(255 - NEAR, x, y, 2) == 1 && level(NEAR, x, y, 2) == 0);
      // The four greys' own middles.
      assert(level(85, x, y, 4) == 1 && level(170, x, y, 4) == 2);
    }
}

static void a_grey_is_its_share_of_dots() {
  // Two inks: a half grey is half the dots, a quarter a quarter, and more light is never fewer white dots.
  assert(dots(128, 2, 1) == 8);
  assert(dots(64, 2, 1) == 4);
  assert(dots(191, 2, 1) == 12);
  int last = 0;
  for (int l = 0; l <= 255; ++l) {
    const int white = dots(static_cast<uint8_t>(l), 2, 1);
    assert(white >= last);
    last = white;
  }
  assert(last == 16);
  // A word at 40 % black over white (luma 153) keeps dots of ink: it does not vanish, as it would at a cut of 128.
  assert(dots(153, 2, 0) >= 5 && dots(153, 2, 0) <= 8);
  // Four inks: a grey between two of them is a raster of those two alone.
  for (int l = 86; l < 170; ++l)
    for (int y = 0; y < 4; ++y)
      for (int x = 0; x < 4; ++x) {
        const int lvl = level(static_cast<uint8_t>(l), x, y, 4);
        assert(lvl == 1 || lvl == 2);
      }
}

static void the_raster_hangs_on_the_place() {
  // The same grey at the same place is the same ink, whatever is drawn around it and however often: what a partial
  // refresh needs to leave a raster alone.
  for (int l = 0; l <= 255; l += 5)
    for (int y = 0; y < 16; ++y)
      for (int x = 0; x < 16; ++x) {
        assert(level(static_cast<uint8_t>(l), x, y, 2) == level(static_cast<uint8_t>(l), x + 4, y + 8, 2));
        assert(level(static_cast<uint8_t>(l), x, y, 4) == level(static_cast<uint8_t>(l), x + 12, y + 4, 4));
      }
}

static void the_driver_reads_the_same_ink() {
  // What this step writes, ESPHome's driver cuts into the ink this step meant.
  for (int lvl = 0; lvl < 2; ++lvl) assert(driver_mono(luma565(grey565(grey(static_cast<uint8_t>(lvl), 2)))) == lvl);
  for (int lvl = 0; lvl < 4; ++lvl) assert(driver_grey4(luma565(grey565(grey(static_cast<uint8_t>(lvl), 4)))) == lvl);
}

static void a_block_as_lvgl_flushes_it() {
  // Three columns of two rows out of a buffer whose rows are five pixels apart, big and little endian, at a place of its
  // own on the glass: each pixel the ink of its own place.
  const uint16_t pixels[10] = {0xFFFF, 0x0000, 0x8410, 0xAAAA, 0xBBBB, 0x8410, 0x8410, 0xFFFF, 0xCCCC, 0xDDDD};
  for (bool big : {true, false}) {
    uint8_t source[20], ink[12];
    for (int i = 0; i < 10; ++i) {
      source[i * 2] = static_cast<uint8_t>(big ? pixels[i] >> 8 : pixels[i] & 0xFF);
      source[i * 2 + 1] = static_cast<uint8_t>(big ? pixels[i] & 0xFF : pixels[i] >> 8);
    }
    block(source, ink, 3, 2, 5, 0, 2, 9, 6, big, 2);
    for (int row = 0; row < 2; ++row)
      for (int column = 0; column < 3; ++column) {
        const uint8_t *o = ink + (row * 3 + column) * 2;
        const uint16_t got = big ? static_cast<uint16_t>((o[0] << 8) | o[1]) : static_cast<uint16_t>((o[1] << 8) | o[0]);
        assert(got == 0x0000 || got == 0xFFFF);
        // The two that are inks stay them; the grey in an even stretch of grey is the raster of its place.
        if (pixels[row * 5 + column] != 0x8410) assert(got == pixels[row * 5 + column]);
      }
    const uint8_t *corner = ink + (1 * 3 + 0) * 2;  // the grey of the second row, beside another grey
    const uint16_t raster = big ? static_cast<uint16_t>((corner[0] << 8) | corner[1]) : static_cast<uint16_t>((corner[1] << 8) | corner[0]);
    assert(raster == ink565(0x8410, 9, 7, 2));
  }
}

// A row of greys as a block one pixel high, printed at (x, y): the levels it prints as.
static void print_row(const uint8_t *lumas, int count, int x, int y, uint8_t inks, uint8_t *levels) {
  uint8_t source[64], ink[64];
  for (int i = 0; i < count; ++i) {
    const uint16_t pixel = grey565(lumas[i]);
    source[i * 2] = static_cast<uint8_t>(pixel >> 8);
    source[i * 2 + 1] = static_cast<uint8_t>(pixel & 0xFF);
  }
  block(source, ink, count, 1, count, 0, 1, x, y, true, inks);
  for (int i = 0; i < count; ++i) {
    const uint8_t g = luma565(static_cast<uint16_t>((ink[i * 2] << 8) | ink[i * 2 + 1]));
    levels[i] = inks == 4 ? static_cast<uint8_t>((g + 32) >> 6 > 3 ? 3 : (g + 32) >> 6) : static_cast<uint8_t>(g >= 128);
  }
}

static void an_edge_is_not_rastered() {
  // The soft pixels of a rounded corner or a letter: black, a step between, white. The step prints as the nearer ink
  // at every place on the glass, so the edge is a line and not a row of loose dots.
  for (int y = 0; y < 4; ++y)
    for (int x = 0; x < 4; ++x) {
      uint8_t levels[5];
      const uint8_t dark_step[5] = {0, 0, 96, 255, 255};
      print_row(dark_step, 5, x, y, 2, levels);
      assert(levels[0] == 0 && levels[1] == 0 && levels[2] == 0 && levels[3] == 1 && levels[4] == 1);
      const uint8_t light_step[5] = {0, 0, 170, 255, 255};
      print_row(light_step, 5, x, y, 2, levels);
      assert(levels[2] == 1);
      // The rim of a grey area against white is an edge too: the area keeps its raster, the rim takes a side.
      const uint8_t rim[5] = {128, 128, 190, 255, 255};
      print_row(rim, 5, x, y, 2, levels);
      assert(levels[2] == 1);
    }
  // A word at 40 % over white is no edge: its pixels have white beside them and their own tone, nothing darker. It
  // keeps its raster, and with it its ink.
  int ink_dots = 0;
  for (int y = 0; y < 4; ++y)
    for (int x = 0; x < 4; ++x) {
      uint8_t levels[5];
      const uint8_t word[5] = {255, 153, 153, 153, 255};
      print_row(word, 5, x, y, 2, levels);
      ink_dots += levels[2] == 0;
      assert(levels[0] == 1 && levels[4] == 1);
    }
  assert(ink_dots >= 5 && ink_dots <= 8);
  // Four inks: an edge takes the nearest of the four.
  uint8_t levels[3];
  const uint8_t step[3] = {0, 120, 255};
  print_row(step, 3, 0, 0, 4, levels);
  assert(levels[1] == 1);
}

// The block walks its rows with a pointer and reads a table for a pixel that is an ink. Whatever it does to be quick,
// each pixel prints as the rules say: an ink stays it, an edge is the nearer ink, an even stretch its raster.
static void a_block_is_every_pixel_by_the_rules() {
  const int columns = 13, rows = 9, stride = 17, at_x = 5, at_y = 3;
  uint32_t seed = 12345;
  const auto next = [&seed]() { seed = seed * 1664525u + 1013904223u; return seed >> 8; };
  for (uint8_t inks : {uint8_t(2), uint8_t(4)})
    for (bool big : {true, false})
      for (int round = 0; round < 40; ++round) {
        uint16_t pixels[rows][stride];
        uint8_t source[rows * stride * 2], ink[rows * columns * 2];
        for (int r = 0; r < rows; ++r)
          for (int c = 0; c < stride; ++c) {
            // Mostly greys, with paper and ink between them, as a page has.
            const uint32_t pick = next();
            const uint8_t g = pick % 5 == 0 ? 0 : pick % 5 == 1 ? 255 : static_cast<uint8_t>(next());
            pixels[r][c] = grey565(g);
            source[(r * stride + c) * 2] = static_cast<uint8_t>(big ? pixels[r][c] >> 8 : pixels[r][c] & 0xFF);
            source[(r * stride + c) * 2 + 1] = static_cast<uint8_t>(big ? pixels[r][c] & 0xFF : pixels[r][c] >> 8);
          }
        // The middle rows alone, as a band of a flush is: the rows around them are still read.
        const int first = 2, count = 5;
        block(source, ink, columns, rows, stride, first, count, at_x, at_y, big, inks);
        for (int r = first; r < first + count; ++r)
          for (int c = 0; c < columns; ++c) {
            const uint8_t l = luma565(pixels[r][c]);
            const unsigned rest = (l * (inks == 4 ? 3U : 1U)) % 255U;
            uint8_t want;
            if (l == 255 || rest <= NEAR || rest >= 255U - NEAR) {
              want = level(l, at_x + c, at_y + r, inks);
            } else {
              uint8_t around[4];
              int n = 0;
              if (c > 0) around[n++] = luma565(pixels[r][c - 1]);
              if (c + 1 < columns) around[n++] = luma565(pixels[r][c + 1]);
              if (r > 0) around[n++] = luma565(pixels[r - 1][c]);
              if (r + 1 < rows) around[n++] = luma565(pixels[r + 1][c]);
              want = edge(l, around, n) ? nearest(l, inks) : level(l, at_x + c, at_y + r, inks);
            }
            const uint8_t *o = ink + ((r - first) * columns + c) * 2;
            const uint16_t got = big ? static_cast<uint16_t>((o[0] << 8) | o[1]) : static_cast<uint16_t>((o[1] << 8) | o[0]);
            assert(got == grey565(grey(want, inks)));
          }
      }
}

int main() {
  an_ink_stays_an_ink();
  a_grey_is_its_share_of_dots();
  the_raster_hangs_on_the_place();
  the_driver_reads_the_same_ink();
  a_block_as_lvgl_flushes_it();
  an_edge_is_not_rastered();
  a_block_is_every_pixel_by_the_rules();
  std::puts("paper_ink: ok");
  return 0;
}
