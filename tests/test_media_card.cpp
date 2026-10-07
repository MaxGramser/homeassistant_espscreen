#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_media_card.cpp -o /tmp/test_media_card && /tmp/test_media_card
#include "../components/smart_display/media_card.h"
#include <cassert>
#include <cstdlib>
#include <cstdio>

using namespace media_card;

static bool inside(const Rect &r, int width, int height) { return r.x >= 0 && r.y >= 0 && r.right() <= width && r.bottom() <= height; }
static bool apart(const Rect &a, const Rect &b) { return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y; }
static bool above(const Rect &a, const Rect &b) { return a.bottom() <= b.y; }

// Every part inside the area, nothing over anything else, the keys in one row and the volume row at the bottom.
static void sound(const Layout &l, int width, int height, bool art = true, const Metrics &m = Metrics{}) {
  // A board without pictures has no cover and no square for one (firmware 0.46.0).
  if (art) assert(l.art.w > 0 && l.art.h > 0 && inside(l.art, width, height));
  else assert(l.art.w == 0 && l.art.h == 0);
  const Rect *parts[] = {&l.title, &l.bar, &l.prev, &l.play, &l.next, &l.minus, &l.volume, &l.plus};
  for (const Rect *r : parts) assert(r->w > 0 && r->h > 0 && inside(*r, width, height));
  if (l.artist) assert(l.artist_line.h > 0 && inside(l.artist_line, width, height));
  if (l.times) assert(l.elapsed.h > 0 && l.total.h > 0 && inside(l.elapsed, width, height) && inside(l.total, width, height));
  // The keys share a centre line, the play key is the biggest, previous and next are alike.
  assert(l.prev.cy() == l.play.cy() && l.next.cy() == l.play.cy());
  assert(l.play.w > l.prev.w && l.prev.w == l.next.w && l.prev.w == l.prev.h);
  assert(l.prev.right() < l.play.x && l.play.right() < l.next.x);
  // The volume row runs along the bottom under everything else: volume down, the slider, volume up, the player's own
  // keys, round keys as big as previous and next on one centre line (firmware 0.39.0, GitHub #146).
  assert(l.minus.right() < l.volume.x && l.volume.right() < l.plus.x);
  // (smaller where those keys would push the artist line out: layout()).
  assert(l.minus.w <= l.prev.w && l.minus.h == l.minus.w && l.plus.w == l.minus.w);
  assert(l.minus.cy() == l.volume.cy() && l.plus.cy() == l.volume.cy());
  // The volume knob at 0 or 100 % stands a gap clear of volume down and up, and the seek knob at either end of the bar
  // half a gap clear of the times (firmware 0.52.0): both reached into the keys and the words before (GitHub #177).
  assert(l.volume.x - m.knob_h() / 2 - l.minus.right() >= m.gap() && l.plus.x - (l.volume.right() + m.knob_h() / 2) >= m.gap());
  if (l.times) assert(l.bar.x - m.seek_knob_h() / 2 - l.elapsed.right() >= m.gap() / 2 && l.total.x - (l.bar.right() + m.seek_knob_h() / 2) >= m.gap() / 2);
  for (const Rect *e : {&l.ends[0], &l.ends[1]}) if (e->w) assert(inside(*e, width, height) && e->x > l.plus.right() && e->cy() == l.plus.cy());
  if (l.ends[1].w) assert(l.ends[1].right() < l.ends[0].x);
  for (const Rect *r : {&l.art, &l.title, &l.bar, &l.prev, &l.play, &l.next}) if (r->w) assert(above(*r, l.minus));
  // Nothing overlaps.
  const Rect *rects[] = {&l.art, &l.title, &l.artist_line, &l.bar, &l.elapsed, &l.total, &l.prev, &l.play, &l.next, &l.minus, &l.volume, &l.plus, &l.ends[0], &l.ends[1]};
  for (const Rect *a : rects) for (const Rect *b : rects) if (a != b && a->w && b->w) assert(apart(*a, *b));
  // The art is square and its corner follows its size.
  if (art) assert(l.art.w == l.art.h && l.art_radius == radius_for(l.art.w));
}

int main() {
  // The Guition's card: 480 wide under its top bar, a tall area, so everything stacks under the art.
  {
    Metrics m; Layout l = layout(m, 480, 396);
    sound(l, 480, 396);
    assert(!l.wide && l.times && l.artist);
    // The volume row of round keys (firmware 0.39.0) costs the cover 20 px of the 164 it had.
    assert(l.art.w >= 140 && l.art.cx() == 240 && l.minus.w == m.key_h());
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
    sound(l, 320, 192, true, m);
    assert(l.wide && l.times && l.artist && l.art.w == 120);
    assert(l.title.x > l.art.right() && l.title.y >= l.art.y && l.play.bottom() <= l.art.bottom());
    assert(l.title.right() == 310 && l.play.cx() == l.title.cx());
    printf("cyd card: art %d column x=%d w=%d keys y=%d\n", l.art.w, l.title.x, l.title.w, l.play.y);
  }
  // A Guition tile over the whole page under its head: wide, everything fits, the keys never wider than the column.
  {
    Metrics m; Layout l = layout(m, 448, 236);
    sound(l, 448, 236);
    assert(l.wide && l.times && l.artist && l.art.w >= 170);  // 180 before the round volume keys (0.39.0)
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
    sound(l, 302, 108, true, m);
    assert(l.wide && !l.artist && l.art.w < 120 && l.art.w >= 60);
    assert(l.play.bottom() <= 108 - 22 - 6 && l.bar.h == 4);
    printf("cyd full: art %d keys y=%d bottom=%d\n", l.art.w, l.play.y, l.play.bottom());
  }
  // The player's own keys (its inputs, its library) close the volume row; the slider gives them the room.
  {
    Metrics m; Layout none = layout(m, 480, 396), two = layout(m, 480, 396, 2);
    sound(two, 480, 396);
    assert(none.ends[0].w == 0 && two.ends[0].w == m.key_h() && two.ends[1].w == m.key_h());
    assert(two.ends[0].right() == none.plus.right() && two.volume.w < none.volume.w && two.volume.w >= 2 * m.key_h());
    Metrics small; small.large = false; small.title_h = 21; small.artist_h = 17; small.small_h = 13;
    Layout cyd = layout(small, 320, 192, 2);
    sound(cyd, 320, 192, true, small);
    assert(cyd.volume.w >= 2 * small.key_h());
    printf("volume row: guition slider %d (%d with two keys), cyd %d with two keys\n", none.volume.w, two.volume.w, cyd.volume.w);
  }
  // A very short tall area still holds every part (times gone, a small cover).
  {
    Metrics m; Layout l = layout(m, 300, 300);
    sound(l, 300, 300);
    assert(!l.wide);
  }
  // Shuffle and repeat (firmware 0.24.0+) stand at the ends of the keys' row where it has room: the Guition's card
  // has it, the CYD's card and a CYD tile do not.
  {
    Metrics m; Layout l = layout(m, 480, 396);
    assert(l.sides);
    assert(l.shuffle.right() < l.prev.x && l.next.right() < l.repeat.x);
    assert(l.shuffle.cy() == l.play.cy() && l.repeat.cy() == l.play.cy() && l.shuffle.w == l.repeat.w);
    assert(inside(l.shuffle, 480, 396) && inside(l.repeat, 480, 396) && l.shuffle.x >= m.margin());
    assert(l.play.cx() == 240);  // the row stays in the middle
    // The seek area is the bar's length and at least a key's height, round the bar's own line.
    assert(l.seek.x == l.bar.x && l.seek.w == l.bar.w && l.seek.h > l.bar.h && l.seek.cy() == l.bar.cy());
    Metrics small; small.large = false; small.title_h = 21; small.artist_h = 17; small.small_h = 13;
    Layout cyd = layout(small, 320, 192);
    assert(!cyd.sides && cyd.shuffle.w == 0);
    // A wide glass (800x480) has the room as well; the row keeps its keys at their full gaps.
    Layout wide = layout(m, 800, 396);
    sound(wide, 800, 396);
    printf("sides: guition shuffle x=%d repeat x=%d; 800 wide %s\n", l.shuffle.x, l.repeat.x, wide.sides ? "yes" : "no");
  }
  // A board without pictures (firmware 0.46.0): no cover and no square for one; the player takes the room, in the middle.
  {
    Metrics m; m.large = false; m.art = false; m.title_h = 21; m.artist_h = 17; m.small_h = 13;
    // The CYD's card: everything stacked and centred, the column wider than beside a cover, the times kept.
    Layout card = layout(m, 320, 192);
    sound(card, 320, 192, false, m);
    Metrics with_art = m; with_art.art = true;
    const Layout before = layout(with_art, 320, 192);
    assert(!card.wide && card.artist && card.times && card.title.w > before.title.w);
    assert(card.title.cx() == 160 && card.bar.cx() == 160 && card.play.cx() == 160);
    assert(above(card.title, card.artist_line) && above(card.artist_line, card.bar) && above(card.bar, card.play));
    // In the middle of the room above the volume row: as much air over the title as under the keys.
    const int top_air = card.title.y, low_air = card.minus.y - m.gap() - card.play.bottom();
    assert(std::abs(top_air - low_air) <= 1);
    // The CYD standing up (240 wide) and a CYD tile over the whole page under its head: the artist line goes first.
    sound(layout(m, 240, 272), 240, 272, false, m);
    Layout tile = layout(m, 302, 108);
    sound(tile, 302, 108, false, m);
    assert(!tile.artist && tile.play.cx() == 151);
    // A board with PSRAM keeps its cover exactly as before.
    Metrics big; Layout guition = layout(big, 480, 396);
    assert(guition.art.w >= 140);
    printf("no pictures: cyd column w=%d (%d beside a cover), sides %s; tile artist %d\n", card.title.w, before.title.w,
           card.sides ? "yes" : "no", tile.artist);
  }
  // The times beside the bar take the room the longest time needs (firmware 0.46.0): "1:02:45" was cut at "12:34"'s width.
  {
    Metrics m;
    const Layout narrow = layout(m, 480, 396);
    m.clock_w = m.time_w() + 20;
    const Layout hour = layout(m, 480, 396);
    sound(hour, 480, 396, true, m);
    assert(hour.times && hour.elapsed.w == m.clock_w && hour.total.w == m.clock_w && hour.bar.w == narrow.bar.w - 40);
    m.clock_w = 1;  // never narrower than a minutes' time
    assert(layout(m, 480, 396).elapsed.w == m.time_w());
    // The CYD without its cover has the room for an hour's times too.
    Metrics cyd; cyd.large = false; cyd.art = false; cyd.title_h = 21; cyd.artist_h = 17; cyd.small_h = 13;
    cyd.clock_w = cyd.time_w() + 14;
    const Layout podcast = layout(cyd, 320, 192);
    sound(podcast, 320, 192, false, cyd);
    assert(podcast.times && podcast.elapsed.w == cyd.clock_w);
  }
  // Seeking: a place on the bar is a second of the track, and a seek holds until Home Assistant agrees.
  assert(seek_seconds(0, 200, 240) == 0 && seek_seconds(100, 200, 240) == 120 && seek_seconds(250, 200, 240) == 240);
  assert(seek_seconds(-5, 200, 240) == 0 && seek_seconds(50, 0, 240) == 0 && seek_seconds(50, 200, 0) == 0);
  {
    Seek s;
    s.send(120, 1000, 5000, "Song");
    assert(s.holds(30, 4990, 1500, 5001, true, "Song"));         // the old position: the knob stays where it was sent
    assert(!s.holds(121, 5001, 1600, 5002, true, "Song"));       // near it: Home Assistant agrees, the hold ends
    s.send(120, 1000, 5000, "Song");
    assert(!s.holds(30, 4990, 1500, 5001, true, "Other"));       // another track: the hold ends
    s.send(120, 1000, 5000, "Song");
    assert(!s.holds(30, 4990, 1000 + SEEK_HOLD_MS, 5007, true, "Song"));  // too long without an answer
    s.send(60, 1000, 5000, "Song");
    assert(s.holds(10, 5000, 2000, 5010, false, "Song") && !s.holds(61, 5000, 2000, 5010, false, "Song"));
  }
  // The card's ground: one colour from the app, the first of the two it sends for the firmware of before (0.52.0).
  {
    uint32_t colour = 0;
    assert(ground("2B484F,2B484F", colour) && colour == 0x2B484F);
    assert(ground("611d18,280c0a", colour) && colour == 0x611D18);
    assert(ground("1F3338", colour) && colour == 0x1F3338);
    assert(!ground("-", colour) && !ground("", colour) && !ground("2B484F;121E20", colour) && !ground("2B484G,121E20", colour) && !ground("2B484", colour));
    assert(std::string(next_repeat("off")) == "all" && std::string(next_repeat("all")) == "one" && std::string(next_repeat("one")) == "off");
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
