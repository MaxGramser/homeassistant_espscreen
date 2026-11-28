// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_camera_turn.cpp -o /tmp/test_camera_turn && /tmp/test_camera_turn
// The screen's camera turns its picture upright (components/smart_display/camera_turn.h): the board's mounting, and the
// screen turned half way round from lying down, each turn it half way; a quarter turn leaves it as it is.
#include <cstdio>

#include "components/smart_display/camera_turn.h"

using camera_turn::degrees;

static int failures = 0;
static void expect(int got, int want, const char *what) {
  if (got != want) {
    std::printf("FAIL %s: %d, not %d\n", what, got, want);
    ++failures;
  }
}

int main() {
  // A sensor mounted as the glass, the screen lying down as built: as it is.
  expect(degrees(0, 0, 0), 0, "as built");
  expect(degrees(0, 90, 90), 0, "as built, a panel laid down by LVGL's 90 (the Tab5)");
  // A sensor mounted upside down (the Tab5's): half way round, on every board's own lying-down angle.
  expect(degrees(180, 0, 0), 180, "mounted upside down");
  expect(degrees(180, 90, 90), 180, "mounted upside down, landscape at 90");
  // The screen turned half way round: the camera with it.
  expect(degrees(0, 180, 0), 180, "screen turned half way");
  expect(degrees(0, 270, 90), 180, "screen turned half way, landscape at 90");
  expect(degrees(180, 270, 90), 0, "both: upright again");
  // A quarter turn either way changes nothing.
  expect(degrees(0, 90, 0), 0, "stood up");
  expect(degrees(0, 270, 0), 0, "stood up the other way");
  expect(degrees(180, 0, 90), 180, "mounted upside down, stood up");
  expect(degrees(180, 180, 90), 180, "mounted upside down, stood up the other way");
  // Angles outside 0 to 359, as LVGL's sums might give them.
  expect(degrees(-180, -360, 0), 180, "negative angles");
  expect(degrees(540, 720, 360), 180, "angles past a full turn");
  if (failures == 0) std::printf("camera_turn: all good\n");
  return failures == 0 ? 0 : 1;
}
