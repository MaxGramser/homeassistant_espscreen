#pragma once
// The live spots of a page (docs/PICTURE_ARCHITECTURE.md, section 3.5): what streams on the glass beside the full view,
// a camera tile set to Live and a plugin tile's place set live (ui::live), as one machine. Each spot says every round
// whether it may stream (its card on the glass, the page clear, nothing over it, its room as it is now), and the
// machine does the rest: it asks the app for the spot's stream in its turn, opens the stream when the answer is one,
// stops the spot when it is covered, moved or not wanted, gives it up after TRIES failures, and forgets it, failures
// and all, once a round goes by without it. The rules are the ones the tiles and the places each kept before (firmware
// dev, 2026-10): asked again after camera_view::ASK_AGAIN_MS without an answer, never two asks within GAP_MS, an
// answer that is no stream gives the spot up, an answer while the page is not clear is dropped, and a stream that
// fails counts one of the spot's tries.
//
// The full view's stream is not a spot: the loader asks for its picture (picture_loader.h) and the stream comes back as
// that question's answer. What it shares with the spots, the handle and the tries, is ViewStream below.
//
// Pure, free of LVGL and ESPHome: tests/test_live_spots.cpp drives it on a PC. runtime_tiles.h binds it: it says which
// spots may stream (drawn_over, page_clear, card_room), builds the question and the look, and opens the stream
// (live_view::open).
#include <algorithm>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "camera_view.h"
#include "glass.h"
#include "live_view.h"

namespace live_spots {

enum class Kind : uint8_t { TILE, PLACE };
// A spot: a camera tile (its index) or a plugin tile's place (the place, on the tile of that index), the camera it
// shows, its room on the glass as LVGL lays it out, and for a place whether the picture shows whole.
struct Spot {
  Kind kind = Kind::TILE;
  uint32_t index = 0;
  const void *place = nullptr;
  std::string entity;
  glass::Rect room;
  bool contain = false;
  // The same spot (a tile by its index, a place by its object).
  bool is(const Spot &o) const { return kind == o.kind && index == o.index && place == o.place; }
  // The same spot, unchanged: kept from one round to the next. A tile is kept while its room is; a place also while it
  // shows the same camera the same way.
  bool unchanged(const Spot &o) const {
    if (!is(o) || !(room == o.room)) return false;
    return kind == Kind::TILE || (entity == o.entity && contain == o.contain);
  }
};
// One spot's state.
struct Live {
  Spot spot;
  live_view::Handle handle = -1;
  bool asked = false;      // its question is out
  bool streaming = false;  // its first picture is on the glass
  bool seen = false;       // wanted this round
  uint32_t asked_at = 0, number = 0;
  uint8_t failures = 0;
};

class Spots {
 public:
  // ---- bound once (runtime_tiles.h) ----
  // Sends the spot's question: its number, or 0 when it could not be asked (then the spot asks again next round).
  std::function<uint32_t(const Spot &)> ask;
  // Opens the stream `url` for the spot: live_view's handle, NOT_NOW when the spot is not to be opened now (its card is
  // gone or not wanted any more: nothing counts), or -1 when the stream could not open (no room for another, no memory:
  // the spot gives up and keeps its stills).
  static constexpr live_view::Handle NOT_NOW = -2;
  std::function<live_view::Handle(const Spot &, const std::string &url)> open;
  std::function<void(live_view::Handle)> close;
  std::function<void(const Spot &, const char *what)> log;

  // ---- every round ----
  void begin() {
    for (auto &l : live_) l.seen = false;
  }
  // The spot may stream this round, its room as it is now. A spot that moved or changed is stopped and starts over.
  void want(const Spot &spot) {
    Live *l = find(spot);
    if (l && !l->spot.unchanged(spot)) {
      stop(*l);
      live_.erase(live_.begin() + (l - live_.data()));
      l = nullptr;
    }
    if (!l) {
      live_.push_back(Live{});
      l = &live_.back();
      l->spot = spot;
    }
    l->seen = true;
  }
  // After every spot had its say: what was not wanted stops and is forgotten (its failures too); what is wanted and
  // streams not yet asks in its turn.
  void end(uint32_t now) {
    for (size_t i = 0; i < live_.size();) {
      if (live_[i].seen) { ++i; continue; }
      stop(live_[i]);
      live_.erase(live_.begin() + i);
    }
    for (auto &l : live_) {
      if (l.failures >= live_view::TRIES || l.handle >= 0) continue;
      // An answer that does not come is asked for again.
      if (l.asked && now - l.asked_at >= camera_view::ASK_AGAIN_MS) l.asked = false;
      if (!l.asked && (!l.asked_at || now - l.asked_at >= camera_view::GAP_MS)) {
        const uint32_t number = ask ? ask(l.spot) : 0;
        if (!number) continue;
        l.number = number;
        l.asked = true;
        l.asked_at = now;
        note(l, "asks");
      }
    }
  }

  // ---- the app's answer ----
  // A tile's answer finds it by its index (a tile's own count numbers its questions, tile_picture::Questions), a
  // place's by the number this machine gave. `clear`: the page is clear now; an answer while it is not is dropped, and
  // the spot asks again in its turn.
  void answer(Kind kind, uint32_t index, const std::string &url, bool clear) {
    Spot key;
    key.kind = kind;
    key.index = index;
    if (Live *l = kind == Kind::TILE ? find(key) : nullptr) answered(*l, url, clear);
  }
  void answer(uint32_t number, const std::string &url, bool clear) {
    for (auto &l : live_)
      if (l.spot.kind == Kind::PLACE && l.asked && l.number == number) { answered(l, url, clear); return; }
  }
  // Whether the number is a place's question that waits for its answer.
  bool question(uint32_t number) const {
    return std::any_of(live_.begin(), live_.end(), [&](const Live &l) { return l.spot.kind == Kind::PLACE && l.asked && l.number == number; });
  }

  // ---- what happens to a spot ----
  // Something lies over the spot, its card moved or is gone (live_stop_covered): it stops now and asks again in its
  // turn, GAP_MS from now, when it is wanted again.
  void covered(const Spot &spot, uint32_t now, const char *why) {
    Live *l = find(spot);
    if (!l) return;
    note(*l, why);
    stop(*l);
    l->asked_at = now;
  }
  // What a stream did (live_view::tick): true when the handle is a spot's.
  bool event(live_view::Handle handle, live_view::Event event, uint32_t now) {
    for (auto &l : live_) {
      if (l.handle != handle || handle < 0) continue;
      if (event == live_view::Event::FIRST) {
        l.streaming = true;
      } else if (event == live_view::Event::FAILED || event == live_view::Event::TURNED || event == live_view::Event::ENDED) {
        if (event == live_view::Event::FAILED) ++l.failures;
        l.handle = -1;
        l.streaming = false;
        l.asked_at = now;
      }
      return true;
    }
    return false;
  }
  // Every spot stops at once and is forgotten (a page turns, a card opens over them).
  void halt() {
    for (auto &l : live_) stop(l);
    live_.clear();
  }

  // ---- what the owners read ----
  // Whether a tile asked for its stream or streams: the loader leaves its still alone meanwhile.
  bool active(uint32_t index) const {
    const Live *l = find_tile(index);
    return l && (l->asked || l->handle >= 0);
  }
  bool streaming(uint32_t index) const {
    const Live *l = find_tile(index);
    return l && l->streaming;
  }
  const std::vector<Live> &all() const { return live_; }
  bool empty() const { return live_.empty(); }

 private:
  std::vector<Live> live_;
  Live *find(const Spot &spot) {
    for (auto &l : live_) if (l.spot.is(spot)) return &l;
    return nullptr;
  }
  const Live *find_tile(uint32_t index) const {
    for (const auto &l : live_) if (l.spot.kind == Kind::TILE && l.spot.index == index) return &l;
    return nullptr;
  }
  void note(const Live &l, const char *what) const {
    if (log) log(l.spot, what);
  }
  void stop(Live &l) {
    if (l.handle >= 0 && close) close(l.handle);
    l.handle = -1;
    l.asked = false;
    l.streaming = false;
  }
  void answered(Live &l, const std::string &url, bool clear) {
    if (!l.asked) return;
    l.asked = false;
    // No stream (the camera is not the tile's own, a screen that cannot stream it): the spot keeps its stills.
    if (!live_view::is_stream(url)) {
      l.failures = live_view::TRIES;
      note(l, "answered: no stream");
      return;
    }
    if (!clear) return;
    const live_view::Handle handle = open ? open(l.spot, url) : -1;
    if (handle == NOT_NOW) return;
    l.handle = handle;
    if (handle < 0) {
      l.handle = -1;
      l.failures = live_view::TRIES;  // no room for another stream: its stills stay
      note(l, "could not open");
    } else {
      note(l, "opened");
    }
  }
};

// The full view's stream: the loader asks for the view's picture, and the stream comes back as that question's
// answer (runtime_tiles::camera_answer). What the view keeps of it is here: whether it streams, its handle, and the
// tries this opening of the view has left before it takes the stills of every board.
struct ViewStream {
  live_view::Handle handle = -1;
  bool live = false;      // a stream runs or is about to
  uint8_t failures = 0;
  // Whether the view may still try a stream.
  bool may() const { return failures < live_view::TRIES; }
  bool is(live_view::Handle h) const { return live && handle == h && h >= 0; }
  // A stream opened (or not: no room, no memory: the view takes the stills).
  void opened(live_view::Handle h) {
    handle = h;
    live = h >= 0;
    if (h < 0) failures = live_view::TRIES;
  }
  // The view stopped its stream itself (closed, covered).
  void stopped() {
    live = false;
    handle = -1;
  }
  // The stream failed or the glass turned: asked again, or after TRIES failures the stills.
  void ended(live_view::Event event) {
    if (event == live_view::Event::FAILED) ++failures;
    live = false;
    handle = -1;
  }
};

}  // namespace live_spots
