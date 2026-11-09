#include "components/ili9488_i80/pixels.h"
#include <cassert>
using esphome::ili9488_i80::pack_pixels;
int main() {
  // LVGL can provide either byte order. The parallel bus consumes native words.
  const uint8_t big[] = {0xF8,0, 7,0xE0, 0,0x1F, 0xFF,0xFF};
  const uint8_t little[] = {0,0xF8, 0xE0,7, 0x1F,0, 0xFF,0xFF};
  uint16_t a[5] = {0,0,0,0,0x1234}, b[4]{};
  pack_pixels(a, big, 4, true, false);
  pack_pixels(b, little, 4, false, false);
  for (int i=0;i<4;++i) assert(a[i] == b[i]);
  assert(a[0]==0xF800 && a[1]==0x07E0 && a[2]==0x001F && a[3]==0xFFFF);
  assert(a[4]==0x1234); // Never overwrite the next chunk.
  pack_pixels(b, big, 4, true, true);
  assert(b[0]==0x001F && b[1]==0x07E0 && b[2]==0xF800 && b[3]==0xFFFF);
  pack_pixels(a, nullptr, 0, false, false);
  assert(a[0]==0xF800);
}
