// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_sheet_motion.cpp -o /tmp/test_sheet_motion && /tmp/test_sheet_motion
// The way a sheet goes after a finger let go (sheet_motion.h) and the veil over the glass (glass.h): both pure.
#include "../components/smart_display/sheet_motion.h"
#include "../components/smart_display/glass.h"
#include <cassert>
#include <cstdlib>

using sheet_motion::at;
using sheet_motion::settle;

static void the_time_follows_the_finger() {
  // At rest: the share of the longest that the part left is.
  auto s = settle(200, 0, 400, 120, 260);
  assert(s.ms == 130 && s.lead == 300);
  // A speed that would stop it sooner takes that much less, never less than the shortest.
  s = settle(200, 3200, 400, 120, 260);
  assert(s.ms == 125 && s.lead == 400);
  s = settle(200, 20000, 400, 120, 260);
  assert(s.ms == 120 && s.lead == 600);
  // Moving away from its place counts as rest.
  assert(settle(200, -3000, 400, 120, 260).lead == 300);
  // Nothing left.
  s = settle(0, 3000, 400, 120, 260);
  assert(s.ms == 120 && s.lead == 0);
}

static void it_never_passes_its_place() {
  for (int way : {1, 40, 397}) {
    for (int speed : {0, 500, 2500, 9000, 40000}) {
      const auto s = settle(way, speed, 400, 120, 260);
      for (int sign : {1, -1}) {
        const int from = 100, to = from + sign * way;
        assert(at(from, to, s.lead, 0, static_cast<int>(s.ms)) == from);
        assert(at(from, to, s.lead, static_cast<int>(s.ms), static_cast<int>(s.ms)) == to);
        int last = from;
        for (int now = 1; now < static_cast<int>(s.ms); ++now) {
          const int here = at(from, to, s.lead, now, static_cast<int>(s.ms));
          assert(sign > 0 ? here >= last && here <= to : here <= last && here >= to);
          last = here;
        }
      }
    }
  }
}

static void it_leaves_at_the_speed_it_was_let_go() {
  // 3200 px a second is 3.2 px a millisecond: the first steps go about that far, less what the braking takes.
  const auto s = settle(200, 3200, 400, 120, 260);
  const int moved = at(0, 200, s.lead, 5, static_cast<int>(s.ms));
  assert(moved >= 12 && moved <= 16);
}

static void the_veil_is_lvgls_mix_and_comes_back() {
  using glass::unveiled;
  using glass::veiled;
  using glass::veil_mix;
  // LVGL's step of 1/32 for the Dock's 50 % (127) and an alert's 60 % (153).
  assert(veil_mix(127) == 16);
  assert(veil_mix(153) == 19);
  // A white page under a black scrim: half of 31 and of 63, in LVGL's own rounding.
  assert(veiled(0xFFFF, 0x0000, 16) == 0x7BEF);
  assert(veiled(0x0000, 0x0000, 16) == 0x0000);
  assert(veiled(0x1234, 0x1234, 16) == 0x1234);
  for (uint8_t mix : {uint8_t{16}, uint8_t{19}}) {
    for (uint16_t scrim : {uint16_t{0x0000}, uint16_t{0x10C4}}) {
      for (uint32_t p = 0; p < 0x10000; ++p) {
        const auto pixel = static_cast<uint16_t>(p);
        const uint16_t back = unveiled(veiled(pixel, scrim, mix), scrim, mix);
        assert(std::abs((back >> 11) - (pixel >> 11)) <= 3);
        assert(std::abs(((back >> 5) & 63) - ((pixel >> 5) & 63)) <= 5);
        assert(std::abs((back & 31) - (pixel & 31)) <= 3);
      }
    }
  }
}

int main() {
  the_time_follows_the_finger();
  it_never_passes_its_place();
  it_leaves_at_the_speed_it_was_let_go();
  the_veil_is_lvgls_mix_and_comes_back();
  return 0;
}
