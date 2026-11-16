#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_saver_view.cpp -o /tmp/test_saver_view && /tmp/test_saver_view
#include "../components/smart_display/saver_view.h"
#include <cassert>
#include <string>
#include <cstdio>

using namespace saver_view;

static bool inside(const Rect &r, int width, int height) { return r.x >= 0 && r.y >= 0 && r.right() <= width && r.bottom() <= height; }

// Every glass a board has, lying and standing: the CYD's 320x240 to the ten-inch Guition's 1280x800.
static const int GLASS[][2] = {{320, 240}, {240, 320}, {480, 320}, {320, 480}, {480, 480}, {720, 720}, {800, 480},
                               {480, 800}, {1024, 600}, {600, 1024}, {1280, 800}, {800, 1280}};

static void words_on_every_glass() {
  for (const auto &g : GLASS) {
    const int width = g[0], height = g[1];
    const Shape s = shape(width, height);
    const Words w = words(s, width, height, 24, 32, 25, 6);
    assert(inside(w.first, width, height) && inside(w.second, width, height));
    assert(w.second.y >= w.first.bottom());
    // Beside or under the cover the words keep off it; over a picture they stand at the bottom left.
    if (s == Shape::side) assert(w.first.x >= height);
    if (s == Shape::top) assert(w.first.y >= width);
    if (s == Shape::fill) assert(w.first.x == 24 && height - w.second.bottom() == 24);
    // A camera's single line.
    const Words one = words(Shape::fill, width, height, 24, 25, 0, 6);
    assert(inside(one.first, width, height) && height - one.first.bottom() == 24 && one.second.w == 0);
    std::printf("%4dx%-4d %s\n", width, height, s == Shape::fill ? "fill" : s == Shape::side ? "cover at the left" : "cover at the top");
  }
  // A title on two lines (firmware 0.30.0+): the block grows upward, the line under it stays where it was and the two
  // never overlap, on every glass.
  for (const auto &g : GLASS) {
    const int width = g[0], height = g[1];
    const Shape s = shape(width, height);
    const Words one = words(s, width, height, 24, 32, 25, 6), two = words(s, width, height, 24, 2 * 32, 25, 6);
    assert(fits(s, one, width, height) && two.second.y >= two.first.bottom());
    // Only the CYD standing up lacks the room under its cover: its title keeps one line.
    assert(fits(s, two, width, height) == !(width == 240 && height == 320));
    if (fits(s, two, width, height)) assert(inside(two.first, width, height) && inside(two.second, width, height));
    if (s == Shape::fill) assert(two.second.y == one.second.y && two.first.y == one.first.y - 32);
  }
  assert(title_lines(32, 32) == 1 && title_lines(64, 32) == 2 && title_lines(96, 32) == 2 && title_lines(0, 32) == 1 && title_lines(40, 0) == 1);
  // The clock's AM or PM after the time, the two together in the middle; the temperature small at the bottom (0.31.0+).
  const ClockRow row = clock_row(480, 300, 40, 8);
  assert(row.time_x == (480 - 348) / 2 && row.ampm_x == row.time_x + 308);
  assert(clock_row(480, 300, 0, 8).time_x == 90);
  for (const auto &g : GLASS) {
    const Rect t = temperature(g[0], g[1], 10, 21);
    assert(inside(t, g[0], g[1]) && g[1] - t.bottom() == 10 && t.x == 10 && t.w == g[0] - 20);
  }
  // About square fills, longer glass does not: four to five either way.
  assert(shape(480, 480) == Shape::fill && shape(500, 400) == Shape::fill && shape(400, 500) == Shape::fill);
  assert(shape(501, 400) == Shape::side && shape(400, 501) == Shape::top && shape(480, 320) == Shape::side);
}

// A player's keys (firmware 0.33.0+): one column in the bottom right corner, a margin from both edges, play or pause at
// the bottom and the volume over it; the words end before them, however long the title.
static bool apart(const Rect &a, const Rect &b) { return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y; }
static void keys_on_every_glass() {
  for (const auto &g : GLASS) {
    const int width = g[0], height = g[1];
    const bool large = width >= 480 && height >= 480;
    const int margin = large ? 28 : 12, key = large ? 52 : 34, play = large ? 64 : 40, gap = large ? 14 : 8;
    const Keys k = keys(width, height, margin, key, play, gap, true, true);
    for (const Rect &r : {k.play, k.minus, k.plus}) assert(inside(r, width, height) && r.w == r.h);
    assert(width - k.play.right() == margin && height - k.play.bottom() == margin && k.left == k.play.x);
    assert(k.minus.bottom() + gap == k.play.y && k.plus.bottom() + gap == k.minus.y);
    assert(k.minus.cx() == k.play.cx() && k.plus.cx() == k.play.cx());
    // The words, one line or two, never reach the keys and keep room to read.
    const Shape s = shape(width, height);
    for (int lines = 1; lines <= 2; ++lines) {
      Words w = words(s, width, height, margin, lines * 32, 25, 6);
      before_keys(w, k, margin);
      for (const Rect &r : {w.first, w.second})
        for (const Rect &round : {k.play, k.minus, k.plus}) assert(apart(r, round));
      assert(w.first.w >= 1 && w.first.right() <= k.left - margin / 2);
      // Every glass that draws pictures (480 pixels and up on its short side) keeps a title's width to read.
      if (large) assert(w.first.w >= 180);
      if (large && lines == 1) { std::printf("%4dx%-4d words %d wide beside the keys\n", width, height, w.first.w); }
    }
    // A player without a volume has the play key alone in the corner, one without play the volume there, and one
    // that can do neither has no key: the words keep the whole width.
    const Keys alone = keys(width, height, margin, key, play, gap, true, false);
    assert(alone.minus.w == 0 && alone.plus.w == 0 && alone.play.x == k.play.x && alone.play.y == k.play.y);
    const Keys volume = keys(width, height, margin, key, play, gap, false, true);
    assert(volume.play.w == 0 && height - volume.minus.bottom() == margin && inside(volume.plus, width, height));
    const Keys none = keys(width, height, margin, key, play, gap, false, false);
    Words w = words(s, width, height, margin, 32, 25, 6);
    const Words whole = w;
    before_keys(w, none, margin);
    assert(none.left == width && w.first.w == whole.first.w && w.second.w == whole.second.w);
  }
}

static void clock_in_the_middle() {
  const ClockLayout l = clock(480, 480, 120, 32, 12);
  assert(l.time.y + l.time.h + 12 == l.date.y);
  assert(l.time.y - (480 - l.date.bottom()) <= 1 && l.time.y - (480 - l.date.bottom()) >= -1);
  assert(l.time.w == 480 && l.date.w == 480);
}

// Nothing stands still for hours (clock faces, a plugin's saver): within a millimetre's circle, and every minute elsewhere.
static void drift_moves_within_its_circle() {
  const int radius = 6;
  for (int minute = 0; minute < 1440; ++minute) {
    const Offset a = drift(minute, radius), b = drift(minute + 1, radius);
    assert(a.x * a.x + a.y * a.y <= (radius + 1) * (radius + 1));
    assert(a.x != b.x || a.y != b.y || minute == 1439);
  }
  assert(drift(-1, radius).x == 0 && drift(-1, radius).y == 0);  // no clock yet: it stands where it is drawn
}

// A plugin's saver is painted in place for a new word, and made anew for other options (saver_sync).
struct Word { std::string plugin, kind, plugin_options; };
static void a_plugin_saver_is_painted_in_place_or_made_anew() {
  const Word now{"plugin:deck.spin", "media", "{\"spin\":true}"};
  assert(paints_in_place(now, now, true, true));                                   // the next track: on_state
  assert(!paints_in_place(now, Word{now.plugin, now.kind, "{\"spin\":false}"}, true, true));  // other options: anew
  assert(!paints_in_place(now, Word{"plugin:deck.still", now.kind, now.plugin_options}, true, true));  // another saver
  assert(!paints_in_place(now, Word{now.plugin, "clock", now.plugin_options}, true, true));  // another step
  assert(!paints_in_place(now, now, false, true));                                 // nothing shown: it is made
  assert(!paints_in_place(now, now, true, false));                                 // the plugin left this screen
  assert(!paints_in_place(Word{"", "clock", ""}, Word{"", "clock", ""}, true, true));  // Tessera's own face
}

int main() {
  a_plugin_saver_is_painted_in_place_or_made_anew();
  drift_moves_within_its_circle();
  words_on_every_glass();
  keys_on_every_glass();
  clock_in_the_middle();
  std::puts("saver view ok");
}
