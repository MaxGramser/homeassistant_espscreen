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
  // A picture starts loading only with no finger down and the pages standing still for SETTLE_MS.
  static_assert(may_load(false, 10000, 10000 - SETTLE_MS) && !may_load(true, 10000, 0));
  static_assert(!may_load(false, 10000, 10000 - SETTLE_MS + 1));
  // The tiles' pictures (GitHub #161): those on the glass load while the tiles are seen and nothing covers them...
  static_assert(pictures_on_glass(true, false, false));
  static_assert(!pictures_on_glass(true, true, false) && !pictures_on_glass(true, false, true));  // a card, a full view
  static_assert(!pictures_on_glass(false, false, false));  // a screensaver, or dark
  // ...and a kept page's are fetched ahead only while the screen is in use and nothing else is busy; whether each one
  // fits is the store's spare room, per picture (tests/test_pictures_ahead.cpp, GitHub #415).
  static_assert(pictures_ahead(true, true, false, 0));
  static_assert(!pictures_ahead(false, true, false, 0));  // dimmed: what is not seen waits for a screen in use
  static_assert(!pictures_ahead(true, false, false, 0) && !pictures_ahead(true, true, true, 0));
  static_assert(!pictures_ahead(true, true, false, 1));  // a busy screen fetches nothing ahead
  // A dimmed screen without a screensaver still shows its tiles, so their pictures on the glass load (tiles_seen).
  static_assert(pictures_on_glass(tiles_seen(false, false, 30), false, false));
  // A picture card's name and the live picture's copy of it: left, as wide as the content, one line high, at the bottom.
  static_assert(name_box(200, 120, 20).x == 0 && name_box(200, 120, 20).y == 100);
  static_assert(name_box(200, 120, 20).w == 200 && name_box(200, 120, 20).h == 20);
  return 0;
}
