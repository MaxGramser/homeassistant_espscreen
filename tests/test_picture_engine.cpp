// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_engine.cpp -o /tmp/test_picture_engine && /tmp/test_picture_engine
// The picture engine (picture_engine.h) as a PC has it, the software one: it takes no format whole, decodes no JPEG and
// blits nothing, so every caller takes the stills' way (the BMP decoder row by row, LVGL drawing them); and the one
// mapping of LVGL's clockwise turn to the PPA's counter-clockwise angle, which the P4 engine's blit uses (and
// tests/test_ppa_guard.cpp counts the same way).
#include "../components/smart_display/picture_engine.h"
#include "../components/smart_display/ppa_guard.h"
#include <cassert>
#include <cstdio>

using namespace picture_engine;

int main() {
  // The software engine: nothing whole, nothing decoded, nothing blitted.
  static_assert(!JPEG, "a PC build has no hardware decoder");
  assert(whole_formats().empty());
  assert(!start() && !ready());
  size_t got = 1;
  assert(input(100, &got) == nullptr && got == 0);
  assert(output(100, &got) == nullptr && got == 0);
  Still still;
  const uint8_t jpeg[] = {0xFF, 0xD8, 0xFF, 0xD9};
  assert(!info(jpeg, sizeof(jpeg), still) && still.w == 0);
  uint8_t into[16];
  assert(!decode_into(jpeg, sizeof(jpeg), into, sizeof(into)));
  assert(decode(jpeg, sizeof(jpeg), still) == nullptr);
  assert(client() == nullptr);
  drop(nullptr);
  Block block;
  assert(block.scale == AS_IS && block.turn == 0);
  // The software engine takes no stream's pictures at all, and asks no burst of a 2D-DMA it does not have.
  static_assert(limits().burst_bytes == 0 && limits().picture_bytes == 0 && limits().tile_picture_bytes == 0, "none");
  assert(blit(nullptr, block) != 0);
  // LVGL's clockwise turn as the PPA's counter-clockwise angle, in the PPA's own order (0, 90, 180, 270 as 0 to 3):
  // a glass turned 90 clockwise copies at the PPA's 270, and the other way round; 180 is 180; anything else flat.
  assert(ppa_angle(0) == ppa_guard::A0 && ppa_angle(90) == ppa_guard::A270 && ppa_angle(180) == ppa_guard::A180 &&
         ppa_angle(270) == ppa_guard::A90 && ppa_angle(45) == ppa_guard::A0);
  // The tiles' budget shared: a P4's 24 keeps four tiles at 6 each and one at 6 too; an S3's 8 gives one tile 6, two 4
  // each, three 2; never fewer than 2, whatever the budget, and never over the most.
  assert(tile_pps(24, 1, 6) == 6 && tile_pps(24, 4, 6) == 6 && tile_pps(24, 5, 6) == 4);
  assert(tile_pps(8, 1, 6) == 6 && tile_pps(8, 2, 6) == 4 && tile_pps(8, 3, 6) == 2 && tile_pps(8, 8, 6) == 2);
  assert(tile_pps(8, 0, 6) == 6 && tile_pps(0, 1, 6) == 2);
  static_assert(limits().tile_budget_pps == 0, "the software engine streams no tile");
  std::puts("picture_engine: ok");
  return 0;
}
