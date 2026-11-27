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
    block(source, ink, 3, 2, 5, 9, 6, big, 2);
    for (int row = 0; row < 2; ++row)
      for (int column = 0; column < 3; ++column) {
        const uint8_t *o = ink + (row * 3 + column) * 2;
        const uint16_t got = big ? static_cast<uint16_t>((o[0] << 8) | o[1]) : static_cast<uint16_t>((o[1] << 8) | o[0]);
        assert(got == ink565(pixels[row * 5 + column], 9 + column, 6 + row, 2));
        assert(got == 0x0000 || got == 0xFFFF);
      }
  }
}

int main() {
  an_ink_stays_an_ink();
  a_grey_is_its_share_of_dots();
  the_raster_hangs_on_the_place();
  the_driver_reads_the_same_ink();
  a_block_as_lvgl_flushes_it();
  std::puts("paper_ink: ok");
  return 0;
}
