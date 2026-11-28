// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_vacuum_tile.cpp -o /tmp/test_vacuum_tile && /tmp/test_vacuum_tile
// A robot vacuum's larger tile (vacuum_tile.h): the header, the frame and the dock on a roomy tile, the keys in the
// header on a short one, the rooms as icon tiles in even rows with a last "+N", the map beside or over the rooms, the
// mode only where it fits, and what a tap lands on.
#include "../components/smart_display/vacuum_tile.h"
#include <cassert>
#include <cstdio>
#include <string>

using namespace vacuum_tile;

// Roboto, roughly: half a size per letter, as the editor estimates without a canvas.
static Measure measure(int label, int small) {
  Measure m;
  m.line[LABEL] = label * 1172 / 1000;
  m.line[SMALL] = small * 1172 / 1000;
  m.line[MINI] = 30;
  m.line[ICON] = 49;
  m.line[WATCH_ICON] = 21;
  m.circle = 54;
  m.width = [label, small](Face f, const std::string &s) {
    const int size = f == LABEL ? label : f == SMALL ? small : f == MINI ? 26 : f == ICON ? 42 : 18;
    return static_cast<int>(s.size()) * size * 55 / 100;
  };
  return m;
}
static const std::vector<std::string> ROOMS = {"Kitchen", "Living room", "Hallway", "Bedroom", "Office", "Bathroom"};
static const std::vector<std::string> ROUTINES = {"After dinner", "Daily clean", "Deep clean", "Empty the bin", "Mop the kitchen"};
static Input input(const std::string &face, int w, int h) {
  Input in;
  in.face = face; in.width = w; in.height = h;
  in.rooms = ROOMS; in.routines = ROUTINES; in.map = true; in.modes = 3;
  in.state = "docked"; in.battery = 100; in.charging = true;
  return in;
}
static bool within(const Box &b, int w, int h) { return b.x >= 0 && b.y >= 0 && b.x + b.w <= w && b.y + b.h <= h; }

int main() {
  // The Guition's look (170 dpi, standard): a 2x2 of its 2x3 grid holds its keys in the header, the rooms all six.
  ui::configure(170, "standard");
  const Measure me = measure(18, 16);
  {
    const Layout l = plan(me, input("rooms", 424, 223));
    assert(!l.docked && l.chips.empty());
    assert(l.rooms.size() == ROOMS.size() && l.more.empty());
    assert(l.first.y == l.second.y && l.first.x > l.second.x && within(l.first, 424, 223));
    for (const auto &r : l.rooms) assert(within(r, 424, 223) && r.y >= l.frame.y);
    // Even rows: six as three and three.
    assert(l.rooms[0].y == l.rooms[2].y && l.rooms[3].y > l.rooms[0].y);
    const Hit k = hit(l, 0, l.first.x + l.first.w / 2, l.first.y + l.first.h / 2);
    assert(k.kind == HIT_FIRST);
    const Hit r = hit(l, 0, l.rooms[4].x + 2, l.rooms[4].y + 2);
    assert(r.kind == HIT_ROOM && r.arg == 4);
  }
  // The whole page of the Guition: the dock at the bottom with Start a size up, the map and every room beside it.
  {
    const Layout l = plan(me, input("map_rooms", 424, 353));
    assert(l.docked && l.first.w > ui::touch_min());
    assert(!l.map.empty() && l.rooms.size() == ROOMS.size() && l.more.empty());
    for (const auto &r : l.rooms) assert(within(r, 424, 353) && (r.x >= l.map.x + l.map.w || r.y >= l.map.y + l.map.h));
  }
  // The 8-inch D1001's 2x2 (189 dpi): four rooms in two rows beside the map, none behind a "+N".
  ui::configure(189, "standard");
  {
    Input in = input("map_rooms", 464, 240);
    in.rooms = {"Gang", "Keuken", "Slaapkamer", "Woonkamer"};
    const Layout l = plan(measure(20, 18), in);
    assert(!l.map.empty() && l.rooms.size() == 4 && l.more.empty());
  }
  ui::configure(170, "standard");
  // A 10-inch's 3x3 (149 dpi): the dock with the mode and both keys, chips in the header, the map beside the rooms.
  ui::configure(149, "standard");
  {
    const Measure big = measure(16, 14);
    const Layout l = plan(big, input("map_rooms", 720, 395));
    assert(l.docked && !l.mode.empty() && l.chips.size() == 1);
    assert(l.first.w > l.second.w && l.first.x > l.second.x && l.mode.x == 0);
    assert(!l.map.empty() && l.map.x < l.rooms.front().x);
    assert(l.rooms.size() == ROOMS.size());
    const Hit m = hit(l, 3, l.mode.x + l.mode.w - 2, l.mode.y + l.mode.h / 2);
    assert(m.kind == HIT_MODE && m.arg == 2);
    // While it cleans: how far it is beside the battery.
    Input c = input("map_rooms", 720, 395);
    c.state = "cleaning"; c.progress = 42; c.charging = false;
    assert(plan(big, c).chips.size() == 2);
    // A robot without a second key (SwitchBot while it cleans): Start alone, in the middle where no mode stands.
    Input one = input("rooms", 720, 395);
    one.second = false; one.modes = 0;
    const Layout lo = plan(big, one);
    assert(lo.second.empty() && lo.docked && lo.first.x + lo.first.w / 2 >= 720 / 2 - 2 && lo.first.x + lo.first.w / 2 <= 720 / 2 + 2);
  }
  // A short and narrow tile: a last tile says how many more, and it opens the card.
  ui::configure(170, "standard");
  {
    const Layout l = plan(me, input("rooms", 200, 223));
    assert(!l.more.empty() && l.more.count + static_cast<int>(l.rooms.size()) == static_cast<int>(ROOMS.size()));
    assert(hit(l, 0, l.more.x + 2, l.more.y + 2).kind == HIT_MORE);
  }
  // Routines: a list, and the rest behind "+N".
  {
    const Layout l = plan(me, input("routines", 424, 223));
    assert(!l.routines.empty());
    assert(l.routines.size() + static_cast<size_t>(l.routines_more.count) == ROUTINES.size());
  }
  // One place for routines: the first routine, not a "+N" alone.
  {
    ui::configure(143, "compact");
    int one_place = 0;
    for (int w = 150; w <= 500; w += 10)
      for (int h = 120; h <= 300; h += 10) {
        const Layout l = plan(me, input("routines", w, h));
        assert(l.routines_more.empty() || !l.routines.empty());
        one_place += l.routines.size() == 1 && l.routines_more.empty();
      }
    assert(one_place > 0);
    ui::configure(170, "standard");
  }
  // A robot that cleans by area but has no room linked yet: the frame stands empty for the card's words.
  {
    Input in = input("rooms", 424, 223);
    in.rooms.clear();
    const Layout l = plan(me, in);
    assert(l.rooms.empty() && l.more.empty() && !l.frame.empty());
  }
  // Corners that run with the tile's: its radius less its padding, a room's less the frame's.
  {
    const Layout l = plan(me, input("rooms", 424, 223));
    assert(l.frame_radius == std::max(ui::px(8), 22 - 12) && l.tile_radius <= l.frame_radius);
  }
  std::puts("vacuum tile: ok");
  return 0;
}
