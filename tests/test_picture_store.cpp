// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_store.cpp -o /tmp/test_picture_store && /tmp/test_picture_store
#include "../components/smart_display/picture_store.h"
#include <cassert>
#include <cstdlib>
#include <set>
#include <string>
#include <utility>
#include <vector>

// LVGL's image descriptor, as far as the store reads it.
struct Header { uint32_t w = 0, h = 0, cf = 0; };
struct Image { Header header; uint32_t data_size = 0; const uint8_t *data = nullptr; };

int main() {
  int live = 0;
  picture_store::Store<Image> store;
  store.allocate = [&](size_t n) { ++live; return std::malloc(n); };
  store.release = [&](void *p) { --live; std::free(p); };

  std::vector<uint8_t> red(100, 1), blue(100, 2), big(300, 3);
  Image a{{10, 5, 1}, 100, red.data()};

  // No budget, no pictures: a board without PSRAM draws from the download as before.
  assert(!store.put("cover", a, 1));
  store.budget = 1000;

  // A copy of its own, found again by what was asked for.
  Image *kept = store.put("cover", a, 1);
  assert(kept && kept->data != red.data() && kept->data[0] == 1 && store.find("cover") == kept && live == 1);
  assert(store.entry("cover") && !store.find("other"));

  // The next camera picture of the same size is written over the old one: the card keeps its pointer.
  Image b{{10, 5, 1}, 100, blue.data()};
  assert(store.put("cover", b, 2) == kept && kept->data[0] == 2 && live == 1 && store.entry("cover")->stored_at == 2);

  // Another size: a new copy, the old one waits while a card still shows it.
  std::set<const Image *> shown{kept};
  auto on_card = [&](const Image *i) { return shown.count(i) > 0; };
  Image c{{10, 15, 1}, 300, big.data()};
  Image *bigger = store.put("cover", c, 3);
  assert(bigger && bigger != kept && store.find("cover") == bigger && live == 2);
  store.collect(on_card);
  assert(live == 2);
  shown = {bigger};
  store.collect(on_card);
  assert(live == 1 && store.size() == 300);

  // Over budget: the picture used longest ago goes, never one on a card.
  store.budget = 500;
  assert(store.put("a", a, 4) && store.put("b", b, 5));  // 300 + 100 + 100
  store.find("a");                                        // of the two not on a card, "b" was used longest ago
  store.budget = 350;
  store.collect(on_card);                                 // "cover" is on a card and stays: "b" goes, then "a"
  assert(store.find("cover") && !store.find("b") && !store.find("a") && live == 1);

  // A picture larger than the budget is not kept.
  store.budget = 200;
  assert(!store.put("huge", c, 6));

  // A picture no longer wanted (the camera full screen closed): gone at the next collect once nothing draws it, while
  // the budget alone would have kept it; a new picture under the same key is a copy of its own.
  store.budget = 1000;
  Image *camera = store.put("camera", a, 7);
  shown.insert(camera);
  store.retire("camera");
  store.retire("nothing");  // a key the store has not got: nothing happens
  assert(!store.find("camera") && live == 2);
  store.collect(on_card);
  assert(live == 2);  // still drawn
  Image *next = store.put("camera", b, 8);
  assert(next && next != camera && next->data[0] == 2 && live == 3);
  shown.erase(camera);
  store.collect(on_card);
  assert(live == 2 && store.find("camera") == next);
  store.retire("camera");
  store.collect(on_card);
  assert(live == 1 && !store.find("camera") && store.find("cover"));

  // Another layout: what no card shows goes now, the rest once its card lets it go.
  store.put("x", a, 7);
  store.forget(on_card);
  assert(!store.find("x") && !store.find("cover") && live == 1);
  shown.clear();
  store.collect(on_card);
  assert(live == 0 && store.size() == 0);

  // A page's strip from before someone on its map moved (firmware 0.30.0+): retired by what its key says, found by
  // its picture for as long as a card draws it, and gone once none does. Sixteen moves never fill the store.
  Image *first = store.put("live|a|1", a, 8);
  shown = {first};
  Image *second = store.put("live|a|2", a, 9);
  store.retire_if([](const auto &e) { return e.key != "live|a|2" && e.key.rfind("live|a|", 0) == 0; });
  assert(!store.find("live|a|1") && store.find("live|a|2") == second);
  assert(store.holder(first) && store.holder(first)->key == "live|a|1" && !store.holder(&a) && !store.holder(nullptr));
  store.collect(on_card);
  assert(live == 2 && store.holder(first));           // a card still draws the old one
  shown = {second};
  store.collect(on_card);
  assert(live == 1 && !store.holder(first) && store.find("live|a|2") == second);
  for (int move = 3; move < 40; ++move) {
    const std::string key = "live|a|" + std::to_string(move);
    Image *next = store.put(key, a, 10 + move);
    assert(next);                                       // always a place for the next one
    store.retire_if([&](const auto &e) { return e.key != key && e.key.rfind("live|a|", 0) == 0; });
    shown = {next};
    store.collect(on_card);
    assert(live == 1);
  }
  shown.clear();
  store.forget(on_card);
  assert(live == 0);

  // The cap on every picture (GitHub #68): a picture within it keeps its pixels.
  using picture_store::fit_scale;
  using picture_store::scaled;
  assert(fit_scale(480, 480) == picture_store::SCALE_ONE && fit_scale(1024, 600) == picture_store::SCALE_ONE);
  assert(fit_scale(1024, 640) == picture_store::SCALE_ONE && fit_scale(0, 10) == picture_store::SCALE_ONE);
  // Three 2x2 cameras on a 10-inch glass: 1248x684, 1.7 MB, comes within both caps.
  for (auto size : {std::pair<int, int>{1248, 684}, {1280, 800}, {2560, 1440}, {4000, 200}, {200, 4000}}) {
    const int scale = fit_scale(size.first, size.second);
    const int w = scaled(size.first, scale), h = scaled(size.second, scale);
    assert(scale < picture_store::SCALE_ONE && w >= 1 && h >= 1);
    assert(w <= picture_store::MAX_SIDE && h <= picture_store::MAX_SIDE);
    assert(size_t(w) * h * 2 <= picture_store::MAX_BYTES);
    // Not needlessly small: within a few percent of the cap on its tighter side.
    assert(w >= picture_store::MAX_SIDE * 9 / 10 || h >= picture_store::MAX_SIDE * 9 / 10 ||
           size_t(w) * h * 2 >= picture_store::MAX_BYTES * 9 / 10);
  }
  // Frames side by side stay side by side: rounding down the start and the end of each keeps them apart.
  const int scale = fit_scale(1248, 684);
  for (int x = 0; x < 1248; x += 37) assert(scaled(x, scale) <= scaled(x + 1, scale));
  assert(scaled(0, scale) == 0 && scaled(1248, scale) <= picture_store::MAX_SIDE);
  // The cap fits the store: whatever the cap lets through, a board's store takes (runtime_tiles.h pictures_kept).
  assert(picture_store::MAX_BYTES <= size_t(1536u << 10));

  // Every slot taken long before the bytes reach the budget (GitHub #177: sixteen covers of tracks gone by on a 4-inch
  // board): the next picture takes the place of the one used longest ago that no card draws, one no longer wanted
  // first, and never one on a card.
  {
    int left = 0;
    picture_store::Store<Image> full;
    full.allocate = [&](size_t n) { ++left; return std::malloc(n); };
    full.release = [&](void *p) { --left; std::free(p); };
    full.budget = 1u << 20;
    std::set<const Image *> drawn;
    for (size_t i = 0; i < picture_store::ENTRIES; ++i) assert(full.put("track" + std::to_string(i), a, uint32_t(i)));
    assert(left == int(picture_store::ENTRIES) && full.size() < full.budget);
    // Without being told what the cards draw, the store keeps what it has (as before).
    assert(!full.put("next", a, 20));
    full.shown = [&](const Image *i) { return drawn.count(i) > 0; };
    // The oldest, "track0", is on a card: "track1" makes way.
    drawn = {full.find("track0")};
    for (size_t i = 2; i < picture_store::ENTRIES; ++i) full.find("track" + std::to_string(i));
    Image *next = full.put("next", a, 21);
    assert(next && full.find("next") == next && full.find("track0") && !full.find("track1") && left == int(picture_store::ENTRIES));
    // A cover no longer wanted goes before one used longer ago that is.
    full.retire("track9");
    assert(full.put("after", a, 22) && full.find("track2") && left == int(picture_store::ENTRIES));
    for (auto &e : full.entries) assert(e.key != "track9");  // gone, not just out of sight
    // Every picture on a card: nothing makes way, and nothing is kept.
    drawn.clear();
    for (auto &e : full.entries) drawn.insert(&e.image);
    assert(!full.put("one more", a, 23) && left == int(picture_store::ENTRIES));
  }
  // Over the budget with every picture on a card (GitHub #183, every page kept): a picture only a page out of sight
  // draws makes way, the one used longest ago first, after it was taken off its cards; the glass keeps its own.
  {
    int left = 0;
    picture_store::Store<Image> kept;
    kept.allocate = [&](size_t n) { ++left; return std::malloc(n); };
    kept.release = [&](void *p) { --left; std::free(p); };
    kept.budget = 250;
    std::vector<uint8_t> pixels(100, 7);
    Image a{{10, 5, 1}, 100, pixels.data()};
    Image *glass = kept.put("glass", a, 1), *old_page = kept.put("old page", a, 2), *new_page = kept.put("new page", a, 3);
    kept.find("new page");  // used later than the old page's
    const auto shown = [](const Image *) { return true; };  // every picture is on some card
    const auto away = [&](const Image *i) { return i != glass; };
    std::vector<const Image *> taken;
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(left == 2 && taken.size() == 1 && taken[0] == old_page && kept.find("glass") && kept.find("new page") && new_page);
    // Within the budget again: nothing more goes. Without `away` nothing on a card ever goes, as before.
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(left == 2 && taken.size() == 1);
    kept.budget = 50;
    kept.collect(shown);
    assert(left == 2);
    // Only the glass left over the budget: it stays.
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(left == 1 && kept.find("glass") && taken.size() == 2);
  }
  return 0;
}
