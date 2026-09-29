#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_media_card.cpp -o /tmp/test_media_card && /tmp/test_media_card
#include "../components/smart_display/media_card.h"
#include <cassert>
#include <cstdio>

using namespace media_card;

static bool inside(const Rect &r, int width, int height) { return r.x >= 0 && r.y >= 0 && r.right() <= width && r.bottom() <= height; }
static bool apart(const Rect &a, const Rect &b) { return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y; }
static bool above(const Rect &a, const Rect &b) { return a.bottom() <= b.y; }

// Every part inside the area, nothing over anything else, the keys in one row and the volume row at the bottom.
static void sound(const Layout &l, int width, int height) {
  const Rect *parts[] = {&l.art, &l.title, &l.bar, &l.prev, &l.play, &l.next, &l.mute, &l.volume, &l.percent};
  for (const Rect *r : parts) assert(r->w > 0 && r->h > 0 && inside(*r, width, height));
  if (l.artist) assert(l.artist_line.h > 0 && inside(l.artist_line, width, height));
  if (l.times) assert(l.elapsed.h > 0 && l.total.h > 0 && inside(l.elapsed, width, height) && inside(l.total, width, height));
  // The keys share a centre line, the play key is the biggest, previous and next are alike.
  assert(l.prev.cy() == l.play.cy() && l.next.cy() == l.play.cy());
  assert(l.play.w > l.prev.w && l.prev.w == l.next.w && l.prev.w == l.prev.h);
  assert(l.prev.right() < l.play.x && l.play.right() < l.next.x);
  // The volume row runs along the bottom under everything else: the mute key, the slider, the percentage.
  assert(l.mute.right() < l.volume.x && l.volume.right() < l.percent.x);
  for (const Rect *r : {&l.art, &l.title, &l.bar, &l.prev, &l.play, &l.next}) assert(above(*r, l.volume) && above(*r, l.mute));
  // Nothing overlaps.
  const Rect *rects[] = {&l.art, &l.title, &l.artist_line, &l.bar, &l.elapsed, &l.total, &l.prev, &l.play, &l.next, &l.mute, &l.volume, &l.percent};
  for (const Rect *a : rects) for (const Rect *b : rects) if (a != b && a->w && b->w) assert(apart(*a, *b));
  // The art is square and its corner follows its size.
  assert(l.art.w == l.art.h && l.art_radius == radius_for(l.art.w));
}

int main() {
  // Long 640x180 panel: its content area is short after the top bar.
  // Playback keys and the volume row must occupy separate bands.
  {
    ui::configure(196, "compact");
    Metrics m; m.large = false; m.title_h = 25; m.artist_h = 20; m.small_h = 16;
    for (int height : {100, 110, 120}) {
      Layout l = layout(m, 640, height);
      sound(l, 640, height);
      assert(l.wide && !l.artist && !l.times);
      assert(l.play.bottom() < l.volume.y);
    }
    ui::configure(170, "standard");
  }
  // The Guition's card: 480 wide under its top bar, a tall area, so everything stacks under the art.
  {
    Metrics m; Layout l = layout(m, 480, 396);
    sound(l, 480, 396);
    assert(!l.wide && l.times && l.artist);
    assert(l.art.w >= 160 && l.art.cx() == 240);
    assert(above(l.art, l.title) && above(l.title, l.artist_line) && above(l.artist_line, l.bar) && above(l.bar, l.play));
    assert(l.play.cx() == 240 && l.title.x == 24 && l.title.w == 432);
    // The times sit at the ends of the bar, on its line.
    assert(l.elapsed.cy() == l.bar.cy() && l.total.cy() == l.bar.cy() && l.elapsed.right() <= l.bar.x && l.bar.right() <= l.total.x);
    assert(l.elapsed.x == l.title.x && l.total.right() == l.title.right());
    // The keys are big enough for a thumb.
    assert(l.play.w >= 64 && l.prev.w >= 52);
    printf("guition card: art %d at %d,%d keys y=%d volume y=%d\n", l.art.w, l.art.x, l.art.y, l.play.y, l.volume.y);
  }
  // The CYD's card: 320 wide, 192 tall under its bar: the art at the left, the column beside it, times included.
  {
    Metrics m; m.large = false; m.title_h = 21; m.artist_h = 17; m.small_h = 13;
    Layout l = layout(m, 320, 192);
    sound(l, 320, 192);
    assert(l.wide && l.times && l.artist && l.art.w == 120);
    assert(l.title.x > l.art.right() && l.title.y >= l.art.y && l.play.bottom() <= l.art.bottom());
    assert(l.title.right() == 310 && l.play.cx() == l.title.cx());
    printf("cyd card: art %d column x=%d w=%d keys y=%d\n", l.art.w, l.title.x, l.title.w, l.play.y);
  }
  // A Guition tile over the whole page under its head: wide, everything fits, the keys never wider than the column.
  {
    Metrics m; Layout l = layout(m, 448, 236);
    sound(l, 448, 236);
    assert(l.wide && l.times && l.artist && l.art.w >= 180);
    // The head of a real tile leaves 202 px: the artist line still fits beside a smaller cover.
    Layout r = layout(m, 448, 202);
    sound(r, 448, 202);
    assert(r.artist && r.times && r.art.w >= 150);
    assert(l.prev.x >= l.title.x && l.next.right() <= l.title.right());
    printf("guition full: art %d column w=%d gap=%d\n", l.art.w, l.title.w, l.play.x - l.prev.right());
  }
  // A CYD tile over the whole page under its head: little room, so the artist line goes and the art shrinks.
  {
    Metrics m; m.large = false; m.title_h = 21; m.artist_h = 17; m.small_h = 13;
    Layout l = layout(m, 302, 108);
    sound(l, 302, 108);
    assert(l.wide && !l.artist && l.art.w < 120 && l.art.w >= 60);
    assert(l.play.bottom() <= 108 - 22 - 6 && l.bar.h == 4);
    printf("cyd full: art %d keys y=%d bottom=%d\n", l.art.w, l.play.y, l.play.bottom());
  }
  // A very short tall area still holds every part (times gone, a small cover).
  {
    Metrics m; Layout l = layout(m, 300, 300);
    sound(l, 300, 300);
    assert(!l.wide);
  }
  // Progress: the position runs on while playing, stands still when paused, never beyond the track.
  assert(progress(0, 0, 0, true, 0) == -1);
  assert(progress(60, 1000, 1000, true, 240) == 250);
  assert(progress(60, 1000, 1060, true, 240) == 500);
  assert(progress(60, 1000, 1060, false, 240) == 250);
  assert(progress(60, 1000, 9000, true, 240) == 1000);
  assert(progress(60, 0, 9000, true, 240) == 250);  // no report time: the position as it was
  assert(elapsed_seconds(60, 1000, 1030, true, 240) == 90 && elapsed_seconds(300, 0, 0, false, 240) == 240);
  // Times as every player writes them.
  assert(clock_text(0) == "0:00" && clock_text(187) == "3:07" && clock_text(3600) == "1:00:00" && clock_text(3765) == "1:02:45");
  // The second line and the idle words.
  assert(subtitle("KATZROAR", "Invocation") == "KATZROAR · Invocation");
  assert(subtitle("KATZROAR", "") == "KATZROAR" && subtitle("", "Invocation") == "Invocation" && subtitle("", "").empty());
  assert(std::string(idle_text("off")) == "Off" && std::string(idle_text("idle")) == "Not playing" && std::string(idle_text("standby")) == "Standby");
  assert(playing("playing") && playing("buffering") && !playing("paused"));
  assert(has_track("paused") && !has_track("idle") && !has_track("off"));
  printf("test_media_card: ok\n");
  return 0;
}
