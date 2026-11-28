// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_loader.cpp -o /tmp/test_picture_loader && /tmp/test_picture_loader
#include "../components/smart_display/picture_loader.h"
#include "../components/smart_display/picture_loader.cpp"  // the loader's bodies (its own compilation unit)
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <functional>
#include <map>
#include <string>
#include <vector>

using namespace picture_loader;

// A screen as the loader sees it: a store, the app's questions, the downloads and what owners were told.
struct Bench {
  Loader loader;
  std::map<std::string, uint32_t> store;           // key -> stored at
  std::vector<std::string> asked, loads, cancels, forgotten;
  std::vector<std::pair<std::string, Outcome>> told;
  Bench() {
    loader.kept = [this](const std::string &key, uint32_t &at) {
      auto it = store.find(key);
      if (it == store.end()) return false;
      at = it->second;
      return true;
    };
    loader.load = [this](Slot slot, const std::string &url, const std::string &) { loads.push_back(std::to_string(int(slot)) + ":" + url); };
    loader.cancel = [this](Slot slot) { cancels.push_back(std::to_string(int(slot))); };
    loader.forget = [this](const std::string &key) { forgotten.push_back(key); store.erase(key); };
  }
  Want want(const std::string &key, const std::string &tag, Rank rank, Slot slot = Slot::FULL, uint32_t every = 0, bool drawn = false) {
    Want w;
    w.key = key; w.tag = tag; w.rank = rank; w.slot = slot; w.every = every; w.drawn = drawn;
    w.ask = [this, tag] { asked.push_back(tag); };
    w.done = [this, key](Outcome o) { told.emplace_back(key, o); };
    return w;
  }
  // A download ends: into the store, and its owner is told.
  void finish(Slot slot, bool ok, uint32_t now) {
    const std::string key = loader.loaded(slot, ok, now);
    if (!key.empty()) { store[key] = now; loader.arrived(key, false); }
  }
};

static const Owner CARD{Kind::CARD, 0}, VIEW{Kind::VIEW, 0}, ALERT{Kind::ALERT, 0};
static Owner tile(uint32_t n) { return {Kind::TILE, n}; }

// A screen whose store takes no picture over (it has none, as tools/render's host program without KEPT_PAGES_HOST, or
// every place of it is on a card): a slot's own download is what its owner draws, until the next one loads into that
// slot. Bound as picture_rounds_lvgl.h binds it (loader_bind, picture_done, slot_letgo). `store` holds what a store did
// take, for a screen that has one with a single place left.
struct Slotted {
  Loader loader;
  std::array<std::string, 3> slot_key{};
  std::array<uint32_t, 3> slot_at{};
  std::map<std::string, uint32_t> store;
  int places = 0;                                  // how many more pictures the store takes
  std::vector<std::string> asked, loads, taken;    // `taken`: pictures that went off the glass for another download
  std::vector<std::pair<std::string, Outcome>> told;
  uint32_t started = 0;
  explicit Slotted(bool rule = true) {
    loader.kept = [this](const std::string &key, uint32_t &at) {
      if (auto it = store.find(key); it != store.end()) { at = it->second; return true; }
      for (int s = 0; s < 3; ++s) if (slot_key[s] == key) { at = slot_at[s]; return true; }
      return false;
    };
    loader.load = [this](Slot slot, const std::string &, const std::string &key) {
      loads.push_back(key);
      auto &held = slot_key[int(slot)];
      if (held != key) { if (!held.empty()) taken.push_back(held); held.clear(); }
    };
    loader.cancel = [this](Slot slot) { slot_key[int(slot)].clear(); };
    loader.forget = [this](const std::string &key) { store.erase(key); };
    if (rule) loader.in_slot = [this](Slot slot, const std::string &key) { return slot_key[int(slot)] == key; };
  }
  Want want(const std::string &key, Rank rank = Rank::PAGE, uint32_t every = 0, Slot slot = Slot::LIVE) {
    Want w;
    w.key = key; w.tag = key; w.rank = rank; w.slot = slot; w.every = every;
    w.ask = [this, key] { asked.push_back(key); };
    w.done = [this, key](Outcome o) { told.emplace_back(key, o); };
    return w;
  }
  // A download ends: into the store while it has a place, else it stays in its slot.
  void finish(Slot slot, bool ok, uint32_t now) {
    const std::string key = loader.loaded(slot, ok, now);
    if (key.empty()) return;
    if (places > 0) { --places; store[key] = now; }
    else { slot_key[int(slot)] = key; slot_at[int(slot)] = now; }
    loader.arrived(key, false);
  }
  // A minute of a page that stands: `wants` every 50 ms, the app answering every question 100 ms after the first round,
  // a download taking 200 ms.
  void minute(const std::function<void(uint32_t)> &wants, uint32_t from = 1000, uint32_t length = 60000) {
    for (uint32_t t = from; t < from + length; t += 50) {
      loader.begin(); wants(t); loader.end(t, true);
      if (t >= from + 100) for (; answered < asked.size(); ++answered) loader.answer(asked[answered], "http://app/" + asked[answered], t);
      if (!loader.busy()) started = 0;
      else if (!started) started = t;
      else if (t - started >= 200) { finish(Slot::LIVE, true, t); started = 0; }
    }
  }
  size_t answered = 0;
  int count(const std::string &key) const { return int(std::count(loads.begin(), loads.end(), key)); }
};

int main() {
  // A card's cover: asked for at once, loaded once its link is here, and then it is simply there.
  {
    Bench b;
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(1000, true);
    assert(b.asked.size() == 1 && b.loads.empty() && b.loader.phase(CARD) == Loader::Phase::ASKED);
    b.loader.answer("cover|p", "http://app/1.bmp", 1100);
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(1150, true);
    assert(b.loads.size() == 1 && b.loads[0] == "0:http://app/1.bmp" && b.loader.busy());
    b.finish(Slot::FULL, true, 1400);
    assert(b.told.size() == 1 && b.told[0].second == Outcome::LOADED && !b.loader.busy());
    for (uint32_t t = 1500; t < 60000; t += 250) {
      b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(t, true);
    }
    assert(b.asked.size() == 1 && b.loads.size() == 1 && b.loader.phase(CARD) == Loader::Phase::DONE);
    // The store let it go (room for another picture): fetched again at once through its link, never waited for.
    b.store.clear();
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(60000, true);
    assert(b.loads.size() == 2 && b.asked.size() == 1);
  }
  // Another track: the download of the new cover knows the key its owner had, so its picture's ETag can go along.
  {
    Bench b;
    b.loader.begin(); b.loader.want(tile(1), b.want("tile|track1", "tile|p1", Rank::PAGE, Slot::LIVE)); b.loader.end(1000, true);
    b.loader.answer("tile|p1", "http://app/1.jpg", 1050);
    b.loader.begin(); b.loader.want(tile(1), b.want("tile|track1", "tile|p1", Rank::PAGE, Slot::LIVE)); b.loader.end(1100, true);
    assert(b.loader.loading_had(Slot::LIVE).empty());
    b.finish(Slot::LIVE, true, 1200);
    b.loader.begin(); b.loader.want(tile(1), b.want("tile|track2", "tile|p1", Rank::PAGE, Slot::LIVE)); b.loader.end(1300, true);
    b.loader.answer("tile|p1", "http://app/2.jpg", 1350);
    b.loader.begin(); b.loader.want(tile(1), b.want("tile|track2", "tile|p1", Rank::PAGE, Slot::LIVE)); b.loader.end(1400, true);
    assert(b.loader.busy() && b.loader.loading_key(Slot::LIVE) == "tile|track2" && b.loader.loading_had(Slot::LIVE) == "tile|track1");
  }
  // A picture the store holds is there at once: nothing is asked, nothing loads.
  {
    Bench b;
    b.store["tile|picture2"] = 5;
    b.loader.begin(); b.loader.want(tile(2), b.want("tile|picture2", "tile|p", Rank::PAGE, Slot::LIVE)); b.loader.end(1000, true);
    assert(b.asked.empty() && b.loads.empty() && b.loader.settled_for(tile(2)) && !b.loader.glass_waiting(1000));
  }
  // Pages turned fast: each page on the glass for a moment. What was not wanted any more never loads, a download for a
  // page already gone breaks off, and only the page that stays is loaded.
  {
    Bench b;
    uint32_t t = 1000;
    for (uint32_t n : {3u, 5u, 9u, 4u}) {
      b.loader.begin(); b.loader.want(tile(n), b.want("tile|picture" + std::to_string(n), "tile|" + std::to_string(n), Rank::PAGE, Slot::LIVE));
      b.loader.end(t, false);  // the pages do not stand still: nothing starts loading
      b.loader.answer("tile|" + std::to_string(n), "http://app/tile" + std::to_string(n), t + 50);
      t += 300;
    }
    assert(b.loads.empty() && b.loader.size() == 1);
    // Page 4 stands still and starts loading; then the page turns to 2 before it came.
    b.loader.begin(); b.loader.want(tile(4), b.want("tile|picture4", "tile|4", Rank::PAGE, Slot::LIVE)); b.loader.end(t, true);
    assert(b.loads.size() == 1 && b.loads[0] == "2:http://app/tile4");
    b.loader.begin(); b.loader.want(tile(2), b.want("tile|picture2", "tile|2", Rank::PAGE, Slot::LIVE)); b.loader.end(t += 200, false);
    assert(b.cancels.size() == 1 && !b.loader.busy());
    // The download that was broken off reports nothing; page 2 gets its own.
    b.loader.answer("tile|2", "http://app/tile2", t + 50);
    b.loader.begin(); b.loader.want(tile(2), b.want("tile|picture2", "tile|2", Rank::PAGE, Slot::LIVE)); b.loader.end(t += 900, true);
    assert(b.loads.size() == 2 && b.loads[1] == "2:http://app/tile2");
    b.finish(Slot::LIVE, true, t + 300);
    assert(b.store.count("tile|picture2") && !b.store.count("tile|picture4"));
  }
  // A card opened and closed before its cover came: the download breaks off, nothing is left behind.
  {
    Bench b;
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(1000, true);
    b.loader.answer("cover|p", "http://app/c", 1100);
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(1200, true);
    assert(b.loader.busy());
    b.loader.begin(); b.loader.end(1300, true);  // the card closed
    assert(b.cancels.size() == 1 && b.loader.size() == 0 && !b.loader.busy());
    b.finish(Slot::FULL, true, 1500);              // a late report of the broken-off download goes nowhere
    assert(b.store.empty() && b.told.empty());
  }
  // Another track: the owner's last cover is forgotten, the new one asked for.
  {
    Bench b;
    b.store["cover|p|a|132"] = 1;
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD)); b.loader.end(1000, true);
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|b|132", "cover|p", Rank::CARD)); b.loader.end(1250, true);
    assert(b.forgotten.size() == 1 && b.forgotten[0] == "cover|p|a|132" && b.asked.size() == 1);
  }
  // A cover fetched ahead for a kept page goes last: it asks only once nothing on the glass waits, and the page on the
  // glass breaks its download off.
  {
    Bench b;
    auto round = [&](uint32_t t, bool card) {
      b.loader.begin();
      b.loader.want(tile(7), b.want("cover|p|a|196", "cover|p", Rank::AHEAD));
      if (card) b.loader.want(tile(2), b.want("tile|picture2", "tile|2", Rank::PAGE, Slot::LIVE));
      b.loader.end(t, true);
    };
    round(1000, false);
    assert(b.asked.size() == 1);
    b.loader.answer("cover|p", "http://app/ahead", 1100);
    round(1200, false);
    assert(b.loads.size() == 1 && b.loads[0] == "0:http://app/ahead");
    round(1300, true);  // a tile on the glass wants its picture: the download ahead breaks off
    assert(b.cancels.size() == 1 && b.asked.size() == 2 && b.asked[1] == "tile|2");
    b.loader.answer("tile|2", "http://app/strip", 1400);
    round(1500, true);
    assert(b.loads.size() == 2 && b.loads[1] == "2:http://app/strip");
    b.finish(Slot::LIVE, true, 1700);
    round(2600, true);  // the glass has its picture: the one ahead goes on, through the link it had
    assert(b.loads.size() == 3 && b.loads[2] == "0:http://app/ahead");
  }
  // One question of a kind at a time: two covers of one player wait for each other's answer.
  {
    Bench b;
    b.loader.begin();
    b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD));
    b.loader.want(tile(3), b.want("cover|p|a|196", "cover|p", Rank::PAGE));
    b.loader.end(1000, true);
    assert(b.asked.size() == 1);
    b.loader.answer("cover|p", "http://app/132", 1100);
    assert(b.loader.phase(CARD) == Loader::Phase::LINKED && b.loader.phase(tile(3)) == Loader::Phase::NEW);
    b.loader.begin();
    b.loader.want(CARD, b.want("cover|p|a|132", "cover|p", Rank::CARD));
    b.loader.want(tile(3), b.want("cover|p|a|196", "cover|p", Rank::PAGE));
    b.loader.end(1200, true);
    assert(b.asked.size() == 2 && b.loads.size() == 1 && b.loads[0] == "0:http://app/132");
  }
  // A camera refreshes at its pace; a load that fails is tried again at that pace too, and a link that fails three times
  // is asked for anew.
  {
    Bench b;
    auto round = [&](uint32_t t) { b.loader.begin(); b.loader.want(VIEW, b.want("camera|c", "full|c", Rank::VIEW, Slot::FULL, 4000)); b.loader.end(t, true); };
    round(1000);
    b.loader.answer("full|c", "http://app/cam", 1100);
    round(1200);
    b.finish(Slot::FULL, true, 1500);
    round(2000); round(5000);
    assert(b.loads.size() == 1);
    round(5600);  // 4 s after the copy was made
    assert(b.loads.size() == 2);
    b.finish(Slot::FULL, false, 6000);
    round(7000);
    assert(b.loads.size() == 2);  // not after the gap: a failure waits the pace
    round(10000);
    assert(b.loads.size() == 3);
    b.finish(Slot::FULL, false, 10500);
    round(14500);
    assert(b.loads.size() == 4);
    b.finish(Slot::FULL, false, 15000);
    round(16000);
    assert(b.loader.phase(VIEW) == Loader::Phase::ASKED && b.asked.size() == 2);
    int failed = 0;
    for (auto &t : b.told) failed += t.second == Outcome::FAILED;
    assert(failed == 3);
  }
  // The app has no picture: a cover stays without one; a map (drawn by the app) is asked for again, later each time.
  {
    Bench b;
    auto round = [&](uint32_t t) {
      b.loader.begin();
      b.loader.want(CARD, b.want("cover|radio", "cover|radio", Rank::CARD));
      b.loader.want(tile(4), b.want("tile|map", "tile|map", Rank::PAGE, Slot::LIVE, 0, true));
      b.loader.end(t, true);
    };
    round(1000);
    b.loader.answer("cover|radio", "", 1100);
    b.loader.answer("tile|map", "", 1100);
    assert(b.told.size() == 2 && b.told[0].second == Outcome::NONE && b.loader.settled_for(CARD));
    for (uint32_t t = 1250; t < 12000; t += 250) round(t);
    assert(b.asked.size() == 3);  // the map once more after ten seconds, the cover never
    b.loader.answer("tile|map", "", 11200);
    for (uint32_t t = 11250; t < 31000; t += 250) round(t);
    assert(b.asked.size() == 3);  // twenty seconds the second time
    round(31250);
    assert(b.asked.size() == 4);
  }
  // An answer that never came is asked for again; nothing loads while a finger is down or the pages move (may_load).
  {
    Bench b;
    auto round = [&](uint32_t t, bool may) { b.loader.begin(); b.loader.want(ALERT, b.want("alert|c", "alert|c", Rank::ALERT, Slot::THUMB)); b.loader.end(t, may); };
    round(1000, true);
    round(10900, true);
    assert(b.asked.size() == 1);
    round(11000, true);
    assert(b.asked.size() == 2);
    b.loader.answer("alert|c", "http://app/a", 11100);
    round(11200, false);
    assert(b.loads.empty());
    round(11450, true);
    assert(b.loads.size() == 1 && b.loads[0] == "1:http://app/a");
  }
  // The most urgent picture goes first: an alert before a card before a page.
  {
    Bench b;
    b.loader.begin();
    b.loader.want(tile(1), b.want("tile|1", "tile|1", Rank::PAGE, Slot::LIVE));
    b.loader.want(CARD, b.want("cover|p", "cover|p", Rank::CARD));
    b.loader.want(ALERT, b.want("alert|c", "alert|c", Rank::ALERT, Slot::THUMB));
    b.loader.end(1000, true);
    for (auto tag : {"tile|1", "cover|p", "alert|c"}) b.loader.answer(tag, std::string("http://app/") + tag, 1100);
    b.loader.begin();
    b.loader.want(tile(1), b.want("tile|1", "tile|1", Rank::PAGE, Slot::LIVE));
    b.loader.want(CARD, b.want("cover|p", "cover|p", Rank::CARD));
    b.loader.want(ALERT, b.want("alert|c", "alert|c", Rank::ALERT, Slot::THUMB));
    b.loader.end(1200, true);
    assert(b.loads.size() == 1 && b.loads[0] == "1:http://app/alert|c");
    // A download on the glass is not broken off for another on the glass: the card waits for the alert's.
    assert(b.cancels.empty());
  }
  // An owner that is done for good (the camera full screen closed): its picture and download go.
  {
    Bench b;
    b.loader.begin(); b.loader.want(VIEW, b.want("camera|c", "full|c", Rank::VIEW, Slot::FULL, 4000)); b.loader.end(1000, true);
    b.loader.answer("full|c", "http://app/cam", 1100);
    b.loader.begin(); b.loader.want(VIEW, b.want("camera|c", "full|c", Rank::VIEW, Slot::FULL, 4000)); b.loader.end(1200, true);
    b.loader.release(VIEW);
    assert(b.cancels.size() == 1 && b.forgotten.size() == 1 && b.loader.size() == 0);
  }
  // A picture the store holds is told to its owner once, as a download would be; a link the owner has is loaded without
  // a question; a picture with a number of tries is given up after them.
  {
    Bench b;
    b.store["cover|kept"] = 1;
    for (uint32_t t = 1000; t < 2000; t += 250) { b.loader.begin(); b.loader.want(CARD, b.want("cover|kept", "cover|p", Rank::CARD)); b.loader.end(t, true); }
    assert(b.told.size() == 1 && b.told[0].second == Outcome::UNCHANGED);
    Bench a;
    auto alert = [&](uint32_t t) {
      Want w = a.want("alert|c|1", "alert|c", Rank::ALERT, Slot::THUMB);
      w.url = "http://app/alert"; w.tries = 3; w.ask = nullptr;
      a.loader.begin(); a.loader.want(ALERT, w); a.loader.end(t, true);
    };
    alert(1000);
    assert(a.asked.empty() && a.loads.size() == 1 && a.loads[0] == "1:http://app/alert");
    for (int i = 0; i < 3; ++i) { a.finish(Slot::THUMB, false, 1200 + i * 1000); alert(1200 + i * 1000 + 900); }
    assert(a.loads.size() == 3 && a.loader.phase(ALERT) == Loader::Phase::NONE);
    for (uint32_t t = 5000; t < 60000; t += 250) alert(t);
    assert(a.loads.size() == 3 && a.asked.empty());
  }
  // An owner that wanted nothing for a while and comes back with another picture (a card opened again on the next track)
  // lets the one it had go; back with the same picture, it keeps it.
  {
    Bench b;
    b.store["cover|p|a"] = 1;
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a", "cover|p", Rank::CARD)); b.loader.end(1000, true);
    b.loader.begin(); b.loader.end(1250, true);  // the card closed
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|a", "cover|p", Rank::CARD)); b.loader.end(1500, true);
    assert(b.forgotten.empty());
    b.loader.begin(); b.loader.end(1750, true);
    b.loader.begin(); b.loader.want(CARD, b.want("cover|p|b", "cover|p", Rank::CARD)); b.loader.end(2000, true);
    assert(b.forgotten.size() == 1 && b.forgotten[0] == "cover|p|a");
  }
  // A page of tiles, each with its own picture (tile_picture.h, GitHub #183): all of them are asked for at once, the
  // ones not there yet load first, and cameras at the same pace take turns, the oldest picture first.
  {
    Bench b;
    b.store["tile|2"] = 200;  // the third tile's camera is kept from before: it is there at once
    auto round = [&](uint32_t t, bool may = true) {
      b.loader.begin();
      for (uint32_t n = 0; n < 3; ++n) {
        const std::string name = "tile|" + std::to_string(n);
        b.loader.want(tile(n), b.want(name, name, Rank::PAGE, Slot::LIVE, 5000));
      }
      b.loader.end(t, may);
    };
    assert(!b.loader.has(tile(0)));
    round(1000);
    assert(b.asked.size() == 2 && b.loader.has(tile(0)) && !b.loader.settled_for(tile(0)) && b.loader.settled_for(tile(2)));
    for (uint32_t n = 0; n < 2; ++n) b.loader.answer("tile|" + std::to_string(n), "http://app/t" + std::to_string(n), 1100);
    // One download at a time, each the moment the last one is in.
    round(1200);
    assert(b.loads.size() == 1 && b.loads[0] == "2:http://app/t0");
    b.finish(Slot::LIVE, true, 1300);
    round(1300);
    assert(b.loads.size() == 2 && b.loads[1] == "2:http://app/t1");
    b.finish(Slot::LIVE, true, 1400);
    // A finger on the glass until all three are due: the oldest picture goes first, not the first tile.
    for (uint32_t t = 1500; t < 7000; t += 250) round(t, false);
    assert(b.asked.size() == 3 && b.asked[2] == "tile|2");  // its turn came: it has no link yet, so it asks for one
    b.loader.answer("tile|2", "http://app/t2", 6900);
    for (uint32_t t = 7000; b.loads.size() < 5; t += 250) {
      round(t);
      if (b.loader.busy()) b.finish(Slot::LIVE, true, t + 100);
    }
    assert(b.loads[2] == "2:http://app/t2" && b.loads[3] == "2:http://app/t0" && b.loads[4] == "2:http://app/t1");
    // A new track on one tile: only that tile asks again, and its last picture is let go.
    b.loader.begin();
    b.loader.want(tile(0), b.want("tile|0", "tile|0", Rank::PAGE, Slot::LIVE, 5000));
    b.loader.want(tile(1), b.want("tile|1|next", "tile|1", Rank::PAGE, Slot::LIVE));
    b.loader.want(tile(2), b.want("tile|2", "tile|2", Rank::PAGE, Slot::LIVE, 5000));
    b.loader.end(8000, true);
    assert(b.asked.size() == 4 && b.asked[3] == "tile|1" && b.forgotten.size() == 1 && b.forgotten[0] == "tile|1");
    assert(b.loader.settled_for(tile(0)) && !b.loader.settled_for(tile(1)));
  }
  // Pictured tiles of one page on a screen whose store takes none of them over (measured 2026-11-27 on the host render:
  // four tiles of the media round's favourites page, 136 downloads in the 35 s the page stood, and only the tile that
  // loaded last showed its picture). Each picture is its slot's own download, so the next tile's download takes it off
  // the glass. Without the rule the loader then fetches it again, which takes the next one off: without end.
  for (uint32_t tiles : {2u, 4u}) {
    auto page = [tiles](Slotted &b) {
      return [&b, tiles](uint32_t) { for (uint32_t n = 0; n < tiles; ++n) b.loader.want(tile(n), b.want("tile|" + std::to_string(n))); };
    };
    Slotted before(false);
    before.minute(page(before));
    printf("%u pictured tiles, no store: without the rule %zu asks, %zu downloads and %zu pictures taken off the glass in a minute\n",
           tiles, before.asked.size(), before.loads.size(), before.taken.size());
    assert(before.asked.size() == tiles && before.loads.size() >= 100);
    // With it: each picture loads once, the last one stays, and the others stand aside. They wait for nothing (no
    // spinner, nothing held up behind them) and are not asked for again.
    Slotted b;
    b.minute(page(b));
    printf("%u pictured tiles, no store: with the rule %zu asks, %zu downloads and %zu taken off the glass\n",
           tiles, b.asked.size(), b.loads.size(), b.taken.size());
    assert(b.asked.size() == tiles && b.loads.size() == tiles && b.taken.size() == tiles - 1);
    assert(b.slot_key[int(Slot::LIVE)] == "tile|" + std::to_string(tiles - 1));
    for (uint32_t n = 0; n < tiles; ++n) assert(b.count("tile|" + std::to_string(n)) == 1 && b.loader.settled_for(tile(n)));
    assert(!b.loader.glass_waiting(61000) && !b.loader.busy());
    assert(b.loader.phase(tile(tiles - 1)) == Loader::Phase::DONE && b.loader.phase(tile(0)) == Loader::Phase::LINKED);
  }
  // The picture in the slot is no longer wanted (its tile went from the page): one of those that stood aside has its
  // turn again, one download, and stays.
  {
    Slotted b;
    b.minute([&](uint32_t) { for (uint32_t n = 0; n < 3; ++n) b.loader.want(tile(n), b.want("tile|" + std::to_string(n))); });
    assert(b.loads.size() == 3 && b.slot_key[int(Slot::LIVE)] == "tile|2");
    b.minute([&](uint32_t) { for (uint32_t n = 0; n < 2; ++n) b.loader.want(tile(n), b.want("tile|" + std::to_string(n))); }, 61000);
    assert(b.loads.size() == 4 && b.asked.size() == 3 && b.slot_key[int(Slot::LIVE)] == b.loads[3] && b.loads[3] != "tile|2");
  }
  // Another picture for a tile that stood aside (its favourite started to play, another track): that is a new picture
  // with a turn of its own. It loads once, and the one that was in the slot stands aside for it.
  {
    Slotted b;
    b.minute([&](uint32_t) { b.loader.want(tile(0), b.want("tile|0")); b.loader.want(tile(1), b.want("tile|1")); });
    assert(b.loads.size() == 2 && b.slot_key[int(Slot::LIVE)] == "tile|1");
    b.minute([&](uint32_t) { b.loader.want(tile(0), b.want("tile|0|next")); b.loader.want(tile(1), b.want("tile|1")); }, 61000);
    assert(b.loads.size() == 3 && b.loads[2] == "tile|0|next" && b.slot_key[int(Slot::LIVE)] == "tile|0|next" && b.count("tile|1") == 1);
  }
  // Two cameras: the one in the slot refreshes at its pace, the other stands aside (before: they took the slot from each
  // other at every refresh).
  {
    Slotted b;
    b.minute([&](uint32_t) { b.loader.want(tile(0), b.want("tile|0", Rank::PAGE, 15000)); b.loader.want(tile(1), b.want("tile|1", Rank::PAGE, 15000)); });
    assert(b.count("tile|0") == 1 && b.count("tile|1") == 4 && b.taken.size() == 1);
  }
  // A download that takes the slot and breaks off (its tile went before it came) leaves the slot empty: the picture it
  // took off the glass comes back.
  {
    Slotted b;
    b.minute([&](uint32_t) { b.loader.want(tile(0), b.want("tile|0")); }, 1000, 2000);
    assert(b.loads.size() == 1 && b.slot_key[int(Slot::LIVE)] == "tile|0");
    auto both = [&](uint32_t t) { b.loader.begin(); b.loader.want(tile(0), b.want("tile|0")); b.loader.want(tile(1), b.want("tile|1")); b.loader.end(t, true); };
    both(3000);
    b.loader.answer("tile|1", "http://app/1", 3050);
    both(3100);
    assert(b.loads.size() == 2 && b.loads[1] == "tile|1" && b.taken.size() == 1 && b.loader.busy());
    b.minute([&](uint32_t) { b.loader.want(tile(0), b.want("tile|0")); }, 3150, 5000);
    assert(b.loads.size() == 3 && b.loads[2] == "tile|0" && b.slot_key[int(Slot::LIVE)] == "tile|0");
  }
  // A screen with a store that has one place left (its other places are all on cards): the first picture is kept, the
  // next two are their slot's. The kept one is never touched; of the other two the last one stays.
  {
    Slotted b;
    b.places = 1;
    b.minute([&](uint32_t) { for (uint32_t n = 0; n < 3; ++n) b.loader.want(tile(n), b.want("tile|" + std::to_string(n))); });
    assert(b.loads.size() == 3 && b.store.count("tile|0") && b.slot_key[int(Slot::LIVE)] == "tile|2" && b.taken.size() == 1);
    // A picture the store let go (not one that left a slot) is fetched again at once, as before, also beside a picture
    // drawn from the slot: its download takes that one off the glass, the store takes it again, and one of the two
    // that are their slot's has the slot again. Five downloads in all, and then nothing more.
    b.store.clear();
    b.places = 1;
    b.minute([&](uint32_t) { for (uint32_t n = 0; n < 3; ++n) b.loader.want(tile(n), b.want("tile|" + std::to_string(n))); }, 61000);
    assert(b.loads.size() == 5 && b.loads[3] == "tile|0" && b.store.count("tile|0") && b.slot_key[int(Slot::LIVE)] == b.loads[4]);
    assert(b.loads[4] != "tile|0" && b.asked.size() == 3 && !b.loader.glass_waiting(121000));
  }
  // A picture for a page out of sight never takes a slot from the glass, not on its first turn either, and is not asked
  // for; the glass takes the slot from one of a page out of sight, which then stands aside.
  {
    Slotted b;
    auto round = [&](uint32_t) { b.loader.want(tile(0), b.want("tile|0")); b.loader.want(tile(9), b.want("tile|9", Rank::AHEAD)); };
    b.minute(round);
    assert(b.loads.size() == 1 && b.asked.size() == 1 && b.slot_key[int(Slot::LIVE)] == "tile|0" && b.taken.empty());
    Slotted c;
    c.minute([&](uint32_t) { c.loader.want(tile(9), c.want("tile|9", Rank::AHEAD)); }, 1000, 2000);
    assert(c.loads.size() == 1 && c.slot_key[int(Slot::LIVE)] == "tile|9");
    c.minute([&](uint32_t) { c.loader.want(tile(0), c.want("tile|0")); c.loader.want(tile(9), c.want("tile|9", Rank::AHEAD)); }, 3000);
    assert(c.loads.size() == 2 && c.loads[1] == "tile|0" && c.slot_key[int(Slot::LIVE)] == "tile|0" && c.count("tile|9") == 1);
  }
  printf("test_picture_loader: ok\n");
  return 0;
}
