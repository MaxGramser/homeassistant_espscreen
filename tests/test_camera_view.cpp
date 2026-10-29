#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_camera_view.cpp -o /tmp/test_camera_view && /tmp/test_camera_view
// The rhythm's rules (camera_view.h): nothing loads between two quick page turns, and the tiles' pictures load while
// the tiles are there to be seen. The rhythm's constants themselves are read by picture_loader.h, whose test drives them.
#include "../components/smart_display/camera_view.h"
#include <cassert>

using namespace camera_view;

int main() {
  // Nothing loads between two quick page turns.
  assert(!settled(10500, 10000) && settled(10000 + SETTLE_MS, 10000));

  // Pictures load while the tiles are seen (GitHub #161): a screen in use, whatever its levels.
  assert(tiles_seen(true, false, 0) && tiles_seen(true, true, 0));
  // In standby the dimmed tiles are seen without a screensaver over them, from SEEN_LEVEL % on.
  assert(tiles_seen(false, false, SEEN_LEVEL) && tiles_seen(false, false, 40));
  assert(!tiles_seen(false, false, SEEN_LEVEL - 1) && !tiles_seen(false, false, 0));
  // A screensaver covers them, the clock as much as a camera, at any level.
  assert(!tiles_seen(false, true, 40) && !tiles_seen(false, true, 100));

  // A failed load is tried again after the gap, and a link that fails MAX_FAILURES times in a row is asked for anew:
  // the loader's rules, whose numbers come from here.
  assert(GAP_MS < REFRESH_MS && ASK_AGAIN_MS > REFRESH_MS && ASK_AGAIN_MAX_MS > ASK_AGAIN_MS && MAX_FAILURES >= 2);
  return 0;
}
