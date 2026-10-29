#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_live_spots.cpp -o /tmp/test_live_spots && /tmp/test_live_spots
// The live spots of a page (live_spots.h): a camera tile set to Live and a plugin's live place, driven through the
// rounds as runtime_tiles drives them: asked in their turn and again after a silence, opened on a stream, stopped when
// covered or moved, given up after TRIES failures or an answer that is no stream, forgotten once not wanted; and the
// full view's handle and tries (ViewStream).
#include "../components/smart_display/live_spots.h"
#include <cassert>
#include <cstdio>
#include <vector>

using namespace live_spots;
using live_view::Event;

struct Rig {
  Spots spots;
  std::vector<std::string> asked, opened, closed, notes;
  uint32_t number = 0;
  live_view::Handle next_handle = 7;  // what open() gives: a handle, -1, or Spots::NOT_NOW
  Rig() {
    spots.ask = [&](const Spot &s) { asked.push_back(s.entity); return ++number; };
    spots.open = [&](const Spot &s, const std::string &url) { opened.push_back(s.entity + " " + url); return next_handle; };
    spots.close = [&](live_view::Handle h) { closed.push_back(std::to_string(h)); };
    spots.log = [&](const Spot &s, const char *what) { notes.push_back(s.entity + ": " + what); };
  }
  // One round with these spots wanted.
  void round(std::vector<Spot> wanted, uint32_t now) {
    spots.begin();
    for (const auto &s : wanted) spots.want(s);
    spots.end(now);
  }
};
static Spot tile(uint32_t index, const char *entity, glass::Rect room = {10, 20, 300, 200}) {
  Spot s;
  s.kind = Kind::TILE;
  s.index = index;
  s.entity = entity;
  s.room = room;
  return s;
}
static Spot place(const void *object, uint32_t index, const char *entity, bool contain = false, glass::Rect room = {0, 0, 200, 150}) {
  Spot s;
  s.kind = Kind::PLACE;
  s.index = index;
  s.place = object;
  s.entity = entity;
  s.room = room;
  s.contain = contain;
  return s;
}
static const std::string STREAM = "http://192.168.1.20:8098/camera/abcdefghijklmnopqrstuvwx.mjpeg";

// A tile asks at once, again after ASK_AGAIN_MS, streams on its answer and stops when covered.
static void a_tile() {
  Rig r;
  r.round({tile(3, "camera.front_door")}, 1000);
  assert(r.asked.size() == 1 && r.spots.active(3) && !r.spots.streaming(3));
  // Asked already: no second ask within ASK_AGAIN_MS, and still the one ask after it.
  r.round({tile(3, "camera.front_door")}, 1000 + camera_view::ASK_AGAIN_MS - 1);
  assert(r.asked.size() == 1);
  r.round({tile(3, "camera.front_door")}, 1000 + camera_view::ASK_AGAIN_MS);
  assert(r.asked.size() == 2);
  // The answer, a stream, opens it; the handle is the stream's.
  r.spots.answer(Kind::TILE, 3, STREAM, true);
  assert(r.opened.size() == 1 && r.spots.active(3));
  const auto &l = r.spots.all().front();
  assert(l.handle == 7 && !l.asked && l.failures == 0);
  // A second answer to the same question counts no more (the tile asked no more).
  r.spots.answer(Kind::TILE, 3, STREAM, true);
  assert(r.opened.size() == 1);
  // Its first picture: streaming; a round while it streams asks nothing.
  assert(r.spots.event(7, Event::FIRST, 30000) && r.spots.streaming(3));
  r.round({tile(3, "camera.front_door")}, 30000);
  assert(r.asked.size() == 2);
  // Covered: closed now, and asked again only GAP_MS later.
  r.spots.covered(tile(3, "camera.front_door"), 40000, "the top layer");
  assert(r.closed == std::vector<std::string>{"7"} && !r.spots.active(3) && !r.spots.streaming(3));
  r.round({tile(3, "camera.front_door")}, 40000 + camera_view::GAP_MS - 1);
  assert(r.asked.size() == 2);
  r.round({tile(3, "camera.front_door")}, 40000 + camera_view::GAP_MS);
  assert(r.asked.size() == 3 && r.notes.back() == "camera.front_door: asks");
  // An event of a handle that is no spot's is not the machine's.
  assert(!r.spots.event(99, Event::FAILED, 50000));
}

// A stream that fails counts a try; three tries and the tile keeps its stills; a round without it forgets that.
static void tries() {
  Rig r;
  uint32_t now = 1000;
  for (uint8_t i = 0; i < live_view::TRIES; ++i) {
    r.round({tile(1, "camera.a")}, now);
    assert(r.asked.size() == i + 1u);
    r.spots.answer(Kind::TILE, 1, STREAM, true);
    assert(r.opened.size() == i + 1u);
    assert(r.spots.event(7, Event::FAILED, now + 100));
    now += camera_view::GAP_MS + 100;
  }
  // Given up: wanted, but asked no more.
  r.round({tile(1, "camera.a")}, now);
  r.round({tile(1, "camera.a")}, now + camera_view::ASK_AGAIN_MS);
  assert(r.asked.size() == live_view::TRIES && !r.spots.active(1));
  // A round without the tile forgets it, failures too: wanted again, it asks afresh.
  r.round({}, now + 2 * camera_view::ASK_AGAIN_MS);
  assert(r.spots.empty());
  r.round({tile(1, "camera.a")}, now + 3 * camera_view::ASK_AGAIN_MS);
  assert(r.asked.size() == live_view::TRIES + 1u);
  // The glass turned: no try counted, asked again after GAP_MS.
  r.spots.answer(Kind::TILE, 1, STREAM, true);
  assert(r.spots.event(7, Event::TURNED, 900000));
  assert(r.spots.all().front().failures == 0 && r.spots.all().front().handle == -1);
  r.round({tile(1, "camera.a")}, 900000 + camera_view::GAP_MS);
  assert(r.asked.size() == live_view::TRIES + 2u);
}

// A stream that could not open (no room, no memory) gives the spot up; an answer while the page is not clear is
// dropped and asked again; a card that is gone by the answer counts nothing.
static void opening() {
  Rig r;
  r.round({tile(2, "camera.b")}, 1000);
  r.spots.answer(Kind::TILE, 2, STREAM, false);  // not clear: dropped
  assert(r.opened.empty() && !r.spots.active(2));
  r.round({tile(2, "camera.b")}, 1000 + camera_view::GAP_MS);
  assert(r.asked.size() == 2);
  r.next_handle = Spots::NOT_NOW;
  r.spots.answer(Kind::TILE, 2, STREAM, true);  // its card is not wanted now: nothing counts
  assert(r.opened.size() == 1 && r.spots.all().front().failures == 0 && r.spots.all().front().handle == -1);
  r.round({tile(2, "camera.b")}, 1000 + 2 * camera_view::GAP_MS);
  assert(r.asked.size() == 3);
  r.next_handle = -1;
  r.spots.answer(Kind::TILE, 2, STREAM, true);  // no room for another stream: the stills stay
  assert(r.spots.all().front().failures == live_view::TRIES && r.notes.back() == "camera.b: could not open");
  r.round({tile(2, "camera.b")}, 1000 + 3 * camera_view::GAP_MS + camera_view::ASK_AGAIN_MS);
  assert(r.asked.size() == 3);
}

// A tile whose card moved (a page animated, a layout made anew) is stopped and starts over from where the card is.
static void moving() {
  Rig r;
  r.round({tile(4, "camera.c", {0, 0, 300, 200})}, 1000);
  r.spots.answer(Kind::TILE, 4, STREAM, true);
  assert(r.spots.all().front().handle == 7);
  r.round({tile(4, "camera.c", {0, 100, 300, 200})}, 2000);
  assert(r.closed == std::vector<std::string>{"7"} && r.spots.all().size() == 1 && r.spots.all().front().handle == -1);
  // Started over: asked at once (its asked_at is new).
  assert(r.asked.size() == 2 && r.spots.all().front().spot.room.y == 100);
  // Halted (a page turns): everything stops and is forgotten.
  r.spots.answer(Kind::TILE, 4, STREAM, true);
  r.spots.halt();
  assert(r.closed.size() == 2 && r.spots.empty());
}

// A plugin's place: found by the number of its question, and an answer that is no stream gives it up.
static void places() {
  Rig r;
  int one = 1, two = 2;
  r.round({place(&one, 5, "camera.d"), place(&two, 5, "camera.e", true)}, 1000);
  assert(r.asked.size() == 2 && r.spots.question(1) && r.spots.question(2) && !r.spots.question(3));
  // A still's link for the first: it keeps its stills for good.
  r.spots.answer(1, "http://192.168.1.20:8098/camera/abcdefghijklmnopqrstuvwx.bmp", true);
  assert(r.opened.empty() && !r.spots.question(1) && r.spots.all()[0].failures == live_view::TRIES);
  // A stream for the second, into its place.
  r.spots.answer(2, STREAM, true);
  assert(r.opened.size() == 1 && r.opened[0] == "camera.e " + STREAM && r.spots.all()[1].handle == 7);
  // The same place showing another camera, or the picture the other way: another spot, started over.
  r.round({place(&one, 5, "camera.d"), place(&two, 5, "camera.e", false)}, 2000);
  assert(r.closed == std::vector<std::string>{"7"} && r.spots.all()[1].handle == -1 && r.asked.size() == 3);
  // The place's number is not a tile's: a tile's answer with that number finds nothing.
  r.spots.answer(Kind::TILE, 3, STREAM, true);
  assert(r.opened.size() == 1);
  // Its stream ended by itself: asked again after GAP_MS, no try counted.
  r.spots.answer(3, STREAM, true);
  assert(r.spots.event(7, Event::ENDED, 5000) && r.spots.all()[1].failures == 0);
  r.round({place(&one, 5, "camera.d"), place(&two, 5, "camera.e", false)}, 5000 + camera_view::GAP_MS);
  assert(r.asked.size() == 4);
}

// A question that could not be sent (the ask returned 0) leaves the spot asking next round.
static void unasked() {
  Rig r;
  r.spots.ask = [&](const Spot &) { return 0u; };
  r.round({tile(6, "camera.f")}, 1000);
  assert(!r.spots.active(6));
  r.spots.ask = [&](const Spot &s) { r.asked.push_back(s.entity); return ++r.number; };
  r.round({tile(6, "camera.f")}, 1100);  // no GAP_MS to wait: nothing was asked
  assert(r.asked.size() == 1 && r.spots.active(6));
}

// The full view's stream: its handle and its tries, as the view keeps them.
static void view() {
  ViewStream v;
  assert(v.may() && !v.live && v.handle == -1);
  v.opened(3);
  assert(v.live && v.is(3) && !v.is(4));
  v.ended(Event::FAILED);
  assert(!v.live && v.handle == -1 && v.failures == 1 && v.may());
  v.opened(4);
  v.stopped();  // closed or covered by its owner: no try counted
  assert(!v.live && v.failures == 1);
  v.opened(5);
  v.ended(Event::TURNED);
  assert(v.failures == 1 && v.may());
  v.opened(6);
  v.ended(Event::FAILED);
  v.opened(8);
  v.ended(Event::FAILED);
  assert(v.failures == live_view::TRIES && !v.may());
  // Could not open: the stills, for good.
  ViewStream w;
  w.opened(-1);
  assert(!w.live && !w.may());
}

int main() {
  a_tile();
  tries();
  opening();
  moving();
  places();
  unasked();
  view();
  std::puts("live_spots: ok");
  return 0;
}
