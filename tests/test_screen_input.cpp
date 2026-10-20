#include "screen_text_en.h"
#include "../components/smart_display/screen_input.h"
#include <cassert>
#include <limits>
#include <vector>
int main() {
  using screen_input::quantize_temperature;
  // Fan and swing mode chips read the n-th name of a JSON list attribute.
  assert(screen_input::list_item("[\"auto\",\"low\",\"high\"]", 0) == "auto");
  assert(screen_input::list_item("[\"auto\",\"low\",\"high\"]", 2) == "high");
  assert(screen_input::list_item("[\"auto\",\"low\",\"high\"]", 3).empty());
  assert(screen_input::list_item("", 0).empty());
  assert(screen_input::list_item("[\"broken", 0).empty());
  assert(quantize_temperature(223, 160, 300, 5) == 225);
  assert(quantize_temperature(221, 160, 300, 5) == 220);
  assert(quantize_temperature(-1, 160, 300, 5) == 160);
  assert(quantize_temperature(999, 160, 299, 5) == 299);
  assert(quantize_temperature(201, 160, 300, 0) == 201);
  // -/+ keys: quick successive taps on the same key all count; bounce within 150 ms does not.
  screen_input::TouchGuard r;
  r.begin(1000); assert(r.accept_repeat(1060, 7)); assert(!r.accept_repeat(1070, 7));  // one contact, one step
  r.begin(1200); assert(r.accept_repeat(1260, 7));                                      // 200 ms later: accepted
  r.begin(1300); assert(!r.accept_repeat(1340, 7));                                     // 80 ms after the last: bounce
  r.begin(1300); r.update(40, 0); assert(!r.accept_repeat(1500, 7));                   // a swipe is never a step
  r.begin(1600); assert(r.accept_repeat(1660, 8));                                      // the other key right away
  // A tap and a key the guard takes reach screen_hooks::touched() (a plugin's click, plugin API 0.3); a refused one,
  // and a slider's release, do not.
  {
    int heard = 0;
    screen_hooks::touched().push_back([&heard]() { ++heard; });
    screen_input::TouchGuard t;
    t.begin(5000); assert(t.accept(5080, 3)); assert(heard == 1);
    t.begin(5100); assert(!t.accept(5180, 3)); assert(heard == 1);                    // bounce: no click
    t.begin(6000); t.update(40, 0); assert(!t.accept(6100, 4)); assert(heard == 1);   // a swipe: no click
    t.begin(7000); assert(t.accept_repeat(7060, 9)); assert(heard == 2);
    t.begin(8000); assert(t.accept_slider(8100, 200)); assert(heard == 2);
    screen_hooks::touched().clear();
  }
  // Page buttons (0.2.72): Next, Next, Next at a finger's pace all count, so page 4 is three taps away
  // while the pages are still drawing; accept() would have dropped the second and third (600 ms).
  screen_input::TouchGuard pager;
  pager.begin(2000); assert(pager.accept_repeat(2080, 12));
  pager.begin(2250); assert(pager.accept_repeat(2330, 12));                              // 250 ms after the last
  pager.begin(2500); assert(pager.accept_repeat(2580, 12));                              // and again
  pager.begin(2800); assert(!pager.accept(2880, 12));                                    // 300 ms after the last Next: the old
  assert(pager.accept_repeat(2880, 12));                                                 // rule's 600 ms window drops it, this takes it
  pager.begin(2950); assert(pager.accept_repeat(3030, 11));                              // Previous right after Next
  screen_input::TouchGuard g;
  g.begin(100);
  assert(!g.accept(120, 1)); // resistive noise pulse
  assert(g.accept(180, 1));
  assert(!g.accept(800, 1)); // same physical gesture cannot fire twice
  g.begin(200);
  assert(!g.accept(280, 1)); // contact bounce cannot repeat the action
  g.begin(300);
  assert(g.accept(380, 2)); // another tile is still responsive
  g.begin(1000);
  assert(g.accept(1080, 2));
  screen_input::TouchGuard moving;
  moving.begin(100, 50, 50);
  moving.update(52, 48);
  assert(moving.accept(180, 1)); // small resistive jitter remains usable
  moving.begin(1000, 50, 50);
  moving.update(51, 50); moving.update(50, 51); moving.update(50, 50);             // reference settled
  moving.update(50, 80);                                                           // 30 px beyond the default 18 px
  moving.update(50, 50);
  assert(!moving.accept(1200, 2)); // excursion stays cancelled, even on return
  assert(moving.accept_slider(1200, 202)); // captured drag is a valid slider gesture
  assert(!moving.accept(1201, 2)); // no parent action after slider release
  assert(!moving.accept_slider(1202, 202)); // one send per contact
  moving.begin(1250);
  assert(!moving.accept_slider(1260, 202)); // noise remains rejected
  assert(moving.accept_slider(1350, 202)); // a second drag 150 ms after the first commit counts (0.2.81)
  // Per-board limits (0.2.23): a centimetre of drift on the Guition is still a tap, and the
  // reference settles over the first samples, so the landing wobble does not count.
  screen_input::TouchGuard wide;
  wide.configure(67, 20);
  assert(wide.move_limit() == 67 && wide.min_press() == 20);
  wide.begin(100, 200, 200, 3);
  wide.update(206, 203, 3); wide.update(210, 205, 3); wide.update(212, 206, 3);   // finger flattens
  wide.update(262, 206, 3);                                                        // 55 px from the settled point
  assert(wide.distance() > 45 && wide.distance() <= 67);
  assert(wide.accept(180, 1)); // under one centimetre: still a tap
  wide.begin(1000, 200, 200, 3);
  wide.update(275, 200, 3); wide.update(300, 200, 3); wide.update(340, 200, 3);     // a real swipe: the reference
  wide.update(380, 200, 3);                                                        // settles, the finger keeps going
  assert(!wide.accept(1100, 1));
  assert(wide.reason().rfind("moved", 0) == 0);
  wide.begin(2000, 200, 200, 3);
  wide.update(400, 400, 5);                                                        // a second finger elsewhere
  assert(wide.accept(2050, 1)); // ignored: only contact 3 is followed; 50 ms is long enough here
  wide.begin(3000, 200, 200, 3);
  assert(!wide.accept(3010, 2)); // 10 ms is below the capacitive minimum
  assert(wide.reason().rfind("too short", 0) == 0);
  wide.begin(3100, 200, 200, 3);
  assert(wide.accept(3160, 2));
  assert(wide.reason().empty());
  assert(!wide.accept(3170, 2));
  assert(wide.reason() == "already handled in this contact");
  wide.begin(3200, 200, 200, 3);
  assert(!wide.accept(3260, 2)); // same tile within 600 ms
  assert(wide.reason() == "same button within the debounce window");
  // No movement limit (0, the Guition): drift never drops a tap. The tile checks that the finger let go on it
  // (runtime_tiles::event, firmware 0.2.65+), and a quick flick is LVGL's gesture, which consumes the contact.
  screen_input::TouchGuard free;
  free.configure(0, 20);
  free.begin(100, 200, 200, 3);
  free.update(205, 200, 3); free.update(205, 200, 3); free.update(205, 200, 3);       // settled
  free.update(400, 260, 3);
  assert(free.distance() > 200);
  assert(free.accept(180, 1));  // 200 px of drift, still a tap
  free.begin(1000, 200, 200, 3);
  free.update(205, 200, 3); free.update(205, 200, 3); free.update(205, 200, 3);
  free.update(400, 200, 3);
  assert(free.accept_repeat(1060, 7));  // -/+ keys follow the same rule
  free.begin(2000, 200, 200, 3);
  free.consume();                        // a flick (the Guition's gesture handler)
  assert(!free.accept(2100, 1) && !free.accept_repeat(2100, 7) && !free.accept_slider(2100, 201));
  screen_input::TouchGuard resistive;
  resistive.configure(56, 60);
  resistive.begin(100, 50, 50);
  resistive.update(80, 50); resistive.update(50, 50);                              // the CYD's jump of 30 px is fine now
  assert(resistive.accept(180, 1));
  resistive.begin(1000, 50, 50);
  resistive.update(50, 120); resistive.update(50, 130); resistive.update(50, 140);
  resistive.update(50, 180);                                                       // 70 px past the settled point: a swipe
  assert(!resistive.accept(1100, 1));
  assert(!resistive.accept_repeat(1100, 1));
  // Edge swipe (0.2.24, back on the touchscreen triggers since 0.2.29): only a touch that
  // starts in the side band flips a page, from the right edge leftwards "next", from the left
  // edge rightwards "previous", once per touch, slow or fast, more sideways than vertical,
  // never from the middle. Every point is already in the screen's coordinates (firmware 0.2.82:
  // runtime_tiles::touch_input turns it with ESPHome's own rotate_coordinates); end() disarms.
  using G = screen_input::EdgeSwipe::Gesture;
  screen_input::EdgeSwipe edge;
  // A board that never configured one has no edge swipe at all: the CYD turns its pages by another gesture,
  // and shared touch handling must not flip a page there on the default band.
  screen_input::EdgeSwipe unconfigured;
  assert(!unconfigured.in_use());
  unconfigured.begin(2, 100, 480);
  assert(!unconfigured.armed());
  assert(unconfigured.update(200, 100) == G::none);

  edge.configure(32, 40);
  assert(edge.in_use());
  edge.begin(6, 240, 480);
  assert(edge.armed());
  assert(edge.update(30, 242) == G::none);   // not far enough yet
  assert(edge.update(48, 245) == G::previous);  // 42 px inward from the left edge: previous page
  assert(edge.update(90, 245) == G::none);   // once per touch
  assert(!edge.armed());
  edge.begin(474, 100, 480);
  assert(edge.update(430, 104) == G::next);  // from the right edge: next page
  edge.begin(240, 240, 480);
  assert(!edge.armed());
  assert(edge.update(300, 240) == G::none);  // started in the middle: never a page swipe
  edge.begin(6, 240, 480);
  assert(edge.update(50, 300) == G::none);   // steeper than 45 degrees: 44 px sideways against 60 down
  assert(edge.update(-10, 240) == G::none);  // moving outward: nothing
  assert(edge.update(60, 270) == G::previous);  // 54 sideways against 30 down: a slanted thumb swipe counts
  edge.begin(6, 240, 480);
  edge.update(20, 250);
  assert(edge.inward() == 14 && edge.sideways() == 10);  // what the log reports for a swipe that ended early
  edge.end();
  assert(!edge.armed());
  assert(edge.update(300, 250) == G::none);  // the next touch's first update, before begin(): nothing
  // Wide glass: the band is a band of the glass, not of the panel the picture came from. A 800 x 1280
  // panel drawn as 1280 x 800 used to arm the right-hand band from x = 772, so a leftward drag anywhere
  // past two fifths of the screen turned a page and nothing turned back (firmware 0.2.82).
  screen_input::EdgeSwipe ten_inch;
  ten_inch.configure(28, 35);
  ten_inch.begin(772, 400, 1280);
  assert(!ten_inch.armed());               // the middle of a ten-inch screen is the middle
  ten_inch.begin(640, 400, 1280);
  assert(!ten_inch.armed());
  ten_inch.begin(1260, 400, 1280);
  assert(ten_inch.armed());
  assert(ten_inch.update(1210, 404) == G::next); // in from the right edge: next page
  ten_inch.begin(10, 400, 1280);
  assert(ten_inch.update(60, 404) == G::previous);  // in from the left edge: previous page
  // The same board built standing up (firmware 0.2.92+): the glass is 800 across now, so the right-hand band
  // starts at 772 and what used to be the right edge is off the screen. The width is measured at every touch,
  // which is why one screen can be built either way round without a second set of numbers.
  ten_inch.begin(772, 400, 800);
  assert(ten_inch.armed());
  assert(ten_inch.update(730, 404) == G::next);
  ten_inch.begin(640, 400, 800);
  assert(!ten_inch.armed());               // the middle of the standing glass is still the middle
  // Up from the bottom edge is the way home (firmware 0.2.100+): the same class, the same band and the same
  // travel, only along the bottom. A screen that states no height has no bottom band, so a board that never
  // asked for one behaves exactly as it did.
  screen_input::EdgeSwipe up;
  up.configure(32, 40);
  up.begin(240, 470, 480, 480);
  assert(up.armed());
  assert(up.update(242, 440) == G::none);   // 30 px up: not far enough
  assert(up.update(244, 425) == G::home);   // 45 px up: back to page 1
  assert(up.update(244, 300) == G::none);   // once per touch
  up.begin(240, 240, 480, 480);
  assert(!up.armed());                      // the middle of the glass is not the bottom band
  up.begin(240, 470, 480, 480);
  assert(up.update(300, 430) == G::none);   // 60 px sideways against 40 up: that is a sideways drag
  up.begin(240, 470, 480);                  // no height stated: the bottom band is not armed at all
  assert(!up.armed());
  assert(up.update(240, 400) == G::none);
  // The corner where the left band meets the bottom one: what the finger does decides.
  up.begin(6, 470, 480, 480);
  assert(up.armed());
  assert(up.update(10, 420) == G::home);
  up.begin(6, 470, 480, 480);
  assert(up.update(60, 468) == G::previous);
  // A screen standing up: the bottom band follows the glass it is given, like the side bands.
  up.begin(240, 790, 480, 800);
  assert(up.armed());
  assert(up.update(240, 745) == G::home);
  // Down from the top edge opens the settings page (firmware 0.28.0+, GitHub #133): the same band and travel along
  // the top, judged by the way the finger goes in the corners as well.
  screen_input::EdgeSwipe down;
  down.configure(32, 40);
  down.begin(240, 6, 480, 480);
  assert(down.armed());
  assert(down.update(242, 30) == G::none);      // 24 px down: not far enough
  assert(down.update(244, 50) == G::settings);  // 44 px down: the settings page
  assert(down.update(244, 200) == G::none);     // once per touch
  down.begin(240, 6, 480, 480);
  assert(down.update(300, 46) == G::none);      // 60 px sideways against 40 down: a sideways drag
  down.begin(240, 6, 480, 480);
  assert(down.update(240, -40) == G::none);     // up and off the glass: nothing
  down.begin(240, 6, 480);                      // no height stated: no top band either
  assert(!down.armed());
  down.begin(474, 6, 480, 480);                 // the top right corner: what the finger does decides
  assert(down.update(470, 60) == G::settings);
  down.begin(474, 6, 480, 480);
  assert(down.update(420, 10) == G::next);
  // Glass that turns its pages by a flick anywhere (the resistive CYD) keeps only the top and the bottom band: a drag
  // in from a side edge is that flick's, never a second page turn.
  screen_input::EdgeSwipe ends;
  ends.configure(27, 34);
  ends.without_sides();
  ends.begin(4, 120, 320, 240);
  assert(!ends.armed());
  assert(ends.update(80, 120) == G::none);
  ends.begin(160, 236, 320, 240);
  assert(ends.update(160, 200) == G::home);
  ends.begin(160, 3, 320, 240);
  assert(ends.update(162, 40) == G::settings);
  ends.begin(3, 236, 320, 240);                 // the bottom left corner: only the bottom band is there
  assert(ends.update(60, 234) == G::none);
  screen_input::TouchGuard rollover;
  rollover.begin(std::numeric_limits<uint32_t>::max() - 30);
  assert(rollover.accept(50, 1)); // millis wraps after 49 days
  rollover.begin(60);
  assert(!rollover.accept(130, 1));
  // GT911 stray (0, 0): measured on Studio 1 as the last sample of a drag before lift-off.
  screen_input::GhostTouch ghost;
  auto same = [](screen_input::PointerRead a, bool pressed, int x, int y) { return a.pressed == pressed && a.x == x && a.y == y; };
  assert(same(ghost.filter({false, 0, 0}, 0, 0), false, 0, 0));      // released: nothing to hide
  assert(same(ghost.filter({true, 0, 0}, 0, 0), false, 0, 0));       // a touch cannot start in the corner
  assert(same(ghost.filter({true, 302, 250}, 0, 0), true, 302, 250)); // the finger on blue
  assert(same(ghost.filter({true, 0, 0}, 0, 0), true, 302, 250));    // stray sample: still on blue
  assert(same(ghost.filter({true, 0, 0}, 0, 0), true, 302, 250));    // and again
  assert(same(ghost.filter({false, 302, 250}, 0, 0), false, 302, 250)); // released where the finger was
  assert(ghost.dropped() == 3);
  assert(same(ghost.filter({true, 0, 240}, 0, 0), true, 0, 240));    // the left edge itself is a real touch
  assert(same(ghost.filter({true, 479, 479}, 479, 479), true, 0, 240)); // rotated 180: (0, 0) is that corner
  assert(same(ghost.filter({true, 0, 0}, 479, 479), true, 0, 0));    // and the top-left is a real pixel there
  // A lift the panel already read reaches LVGL then, not one loop later (the Waveshare 7B: a tap became a long press).
  // ESPHome's marks: 1 pressed, 2 updated, +4 releasing (its last read no longer had it), 0 released, 7 uncalibrated.
  struct Touch { int8_t state; };
  using Touches = std::vector<Touch>;
  assert(!screen_input::panel_let_go(Touches{}));                // no finger held: nothing to let go
  assert(!screen_input::panel_let_go(Touches{{1}}));             // just came down
  assert(!screen_input::panel_let_go(Touches{{2}}));             // still there
  assert(screen_input::panel_let_go(Touches{{5}}));              // gone in the read after the press
  assert(screen_input::panel_let_go(Touches{{6}}));              // gone after it moved
  assert(!screen_input::panel_let_go(Touches{{6}, {2}}));        // one finger up, the other still down
  assert(!screen_input::panel_let_go(Touches{{0}, {2}}));
  assert(screen_input::panel_let_go(Touches{{0}, {6}}));         // the last finger up
  assert(!screen_input::panel_let_go(Touches{{7}}));             // a finger on a panel without its range
  screen_input::PanelRelease lift;
  // A tap read in the loop that also redrew the pressed card for 450 ms: LVGL hears the press, the loop stalls, then
  // ESPHome still says pressed while the panel has let go. LVGL is told released, at the point it had.
  assert(same(lift.filter({true, 300, 200}, false, 1000), true, 300, 200));
  assert(!lift.lifted());
  assert(same(lift.filter({true, 300, 200}, true, 1450), false, 300, 200));
  assert(lift.lifted() && lift.held() == 450);
  assert(same(lift.filter({true, 300, 200}, true, 1455), false, 300, 200));   // read again before ESPHome lets go:
  assert(!lift.lifted());                                                      // still up, never a second press
  assert(same(lift.filter({false, 300, 200}, false, 1460), false, 300, 200));  // ESPHome's own release, a loop on
  assert(!lift.lifted());
  // A tap shorter than one loop: the panel has let go before LVGL heard the press. LVGL hears the press first, the
  // release a read later, or it would never see the tap at all.
  assert(same(lift.filter({true, 120, 80}, true, 2000), true, 120, 80));
  assert(!lift.lifted());
  assert(same(lift.filter({true, 120, 80}, true, 2030), false, 120, 80));
  assert(lift.lifted() && lift.held() == 30);
  // A hold: the panel keeps the finger, so LVGL keeps the press as long as it lasts, and a long press stays one.
  assert(same(lift.filter({true, 50, 60}, false, 3000), true, 50, 60));
  assert(same(lift.filter({true, 52, 61}, false, 3500), true, 52, 61));
  assert(same(lift.filter({false, 52, 61}, false, 3520), false, 52, 61));
  assert(!lift.lifted());
  // A finger that slid on before it let go: the release is where the panel saw it last, as LVGL's slider takes it.
  assert(same(lift.filter({true, 100, 60}, false, 4000), true, 100, 60));
  assert(same(lift.filter({true, 180, 60}, true, 4400), false, 180, 60));
  // A dragged slider sent to its end on release is reported; a drag that ends there is not a jump.
  assert(screen_input::release_jump(240, 0, 0, 360));      // hue: blue to red at the start
  assert(screen_input::release_jump(120, 360, 0, 360));    // green to red at the end
  assert(!screen_input::release_jump(20, 0, 0, 360));      // dragged to the start and let go
  assert(!screen_input::release_jump(240, 238, 0, 360));   // a few pixels on lift-off
  assert(screen_input::release_jump(80, -6, -6, 100));     // brightness: 80 % to the stub below 1 %
  // A slider let go within the edge band of the glass meant the end that lies in that band.
  assert(screen_input::edge_snap(437, 29, 450, 480, 67) == 1);   // wide tile, a fast swipe the panel lost at 437
  assert(screen_input::edge_snap(431, 29, 450, 480, 67) == 1);
  assert(screen_input::edge_snap(412, 29, 450, 480, 67) == 0);   // let go just before the band
  assert(screen_input::edge_snap(437, 29, 222, 480, 67) == 0);   // a narrow tile's end is far from the edge
  assert(screen_input::edge_snap(20, 29, 450, 480, 67) == -1);   // off the left: the start
  assert(screen_input::edge_snap(20, 258, 452, 480, 67) == 0);   // the right column's start is not in the band
  assert(screen_input::edge_snap(437, 29, 450, 480, 0) == 0);    // band off
  // A second drag on the same slider right after the first counts (a slider sends once per contact, on release);
  // a tap on the tile that soon after the slider's commit is still a bounce for the tile's own id only.
  screen_input::TouchGuard drags;
  drags.begin(3000); assert(drags.accept_slider(3200, 205));
  drags.begin(3300); assert(drags.accept_slider(3500, 205));                             // 300 ms after the last commit
  drags.begin(3550); assert(drags.accept(3650, 105));                                    // the tile itself: another id
  drags.begin(3700); assert(!drags.accept(3800, 105));                                   // the tile twice within 600 ms
}
