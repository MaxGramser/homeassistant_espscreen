// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_store.cpp -o /tmp/test_picture_store && /tmp/test_picture_store
#include "../components/smart_display/picture_store.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <utility>
#include <vector>

// LVGL's image descriptor, as far as the store reads it.
struct Header { uint32_t w = 0, h = 0, cf = 0; };
struct Image { Header header; uint32_t data_size = 0; const uint8_t *data = nullptr; };

// A download as picture_fetch makes it: pixels in a buffer of its own, which the store takes over (adopt) or the caller
// frees. `live` counts the buffers that exist, downloads and kept pictures alike.
static int live = 0;
static Image download(uint8_t colour, uint32_t w, uint32_t h) {
  const size_t bytes = size_t(w) * h * 2;
  auto *pixels = static_cast<uint8_t *>(std::malloc(bytes));
  std::memset(pixels, colour, bytes);
  ++live;
  return Image{{w, h, 1}, uint32_t(bytes), pixels};
}
static void drop(const Image &download) { --live; std::free(const_cast<uint8_t *>(download.data)); }

int main() {
  picture_store::Store<Image> store;
  store.release = [](void *p) { --live; std::free(p); };

  // No budget, no pictures: a board without PSRAM draws from the download as before (the caller keeps it).
  Image a = download(1, 10, 5);
  assert(!store.adopt("cover", a, 1));
  drop(a);
  store.budget = 1000;

  // The download's own buffer, no copy: found again by what was asked for.
  a = download(1, 10, 5);
  Image *kept = store.adopt("cover", a, 1);
  assert(kept && kept->data == a.data && store.find("cover") == kept && live == 1);
  assert(store.entry("cover") && !store.find("other"));

  // The next picture under the same key (a camera's next frame): taken over too, and the one before stays while a card
  // draws it. Two pictures at the moment one changes over to the next, never three; the old goes once no card shows it.
  std::set<const Image *> shown{kept};
  auto on_card = [&](const Image *i) { return shown.count(i) > 0; };
  Image b = download(2, 10, 5);
  Image *next = store.adopt("cover", b, 2);
  assert(next && next != kept && next->data == b.data && store.find("cover") == next && live == 2);
  assert(store.entry("cover")->stored_at == 2 && store.holder(kept) && store.holder(kept)->retired);
  store.collect(on_card);
  assert(live == 2);  // still on its card
  shown = {next};
  store.collect(on_card);
  assert(live == 1 && store.size() == 100);

  // Another size is the same: the bigger one is taken, the smaller goes once its card shows the bigger.
  Image c = download(3, 10, 15);
  Image *bigger = store.adopt("cover", c, 3);
  assert(bigger && bigger->data == c.data && store.find("cover") == bigger && live == 2);
  shown = {bigger};
  store.collect(on_card);
  assert(live == 1 && store.size() == 300);

  // Over budget: the picture used longest ago goes, never one on a card.
  store.budget = 500;
  assert(store.adopt("a", download(4, 10, 5), 4) && store.adopt("b", download(5, 10, 5), 5));  // 300 + 100 + 100
  store.find("a");                                        // of the two not on a card, "b" was used longest ago
  store.budget = 350;
  store.collect(on_card);                                 // "cover" is on a card and stays: "b" goes, then "a"
  assert(store.find("cover") && !store.find("b") && !store.find("a") && live == 1);

  // A picture larger than the budget is not kept: its download stays the caller's.
  store.budget = 200;
  Image huge = download(6, 10, 15);
  assert(!store.adopt("huge", huge, 6) && live == 2);
  drop(huge);

  // A picture no longer wanted (the camera full screen closed): gone at the next collect once nothing draws it, while
  // the budget alone would have kept it; a new picture under the same key is one of its own.
  store.budget = 1000;
  Image *camera = store.adopt("camera", download(7, 10, 5), 7);
  shown.insert(camera);
  store.retire("camera");
  store.retire("nothing");  // a key the store has not got: nothing happens
  assert(!store.find("camera") && live == 2);
  store.collect(on_card);
  assert(live == 2);  // still drawn
  Image *again = store.adopt("camera", download(8, 10, 5), 8);
  assert(again && again != camera && again->data[0] == 8 && live == 3);
  shown.erase(camera);
  store.collect(on_card);
  assert(live == 2 && store.find("camera") == again);
  store.retire("camera");
  store.collect(on_card);
  assert(live == 1 && !store.find("camera") && store.find("cover"));

  // Another layout: what no card shows goes now, the rest once its card lets it go.
  store.adopt("x", download(9, 10, 5), 7);
  store.forget(on_card);
  assert(!store.find("x") && !store.find("cover") && live == 1);
  shown.clear();
  store.collect(on_card);
  assert(live == 0 && store.size() == 0);

  // A page's strip from before someone on its map moved (firmware 0.30.0+): retired by what its key says, found by
  // its picture for as long as a card draws it, and gone once none does. Sixteen moves never fill the store.
  Image *first = store.adopt("live|a|1", download(1, 10, 5), 8);
  shown = {first};
  Image *second = store.adopt("live|a|2", download(2, 10, 5), 9);
  store.retire_if([](const auto &e) { return e.key != "live|a|2" && e.key.rfind("live|a|", 0) == 0; });
  Image outside{};
  assert(!store.find("live|a|1") && store.find("live|a|2") == second);
  assert(store.holder(first) && store.holder(first)->key == "live|a|1" && !store.holder(&outside) && !store.holder(nullptr));
  store.collect(on_card);
  assert(live == 2 && store.holder(first));           // a card still draws the old one
  shown = {second};
  store.collect(on_card);
  assert(live == 1 && !store.holder(first) && store.find("live|a|2") == second);
  for (int move = 3; move < 40; ++move) {
    const std::string key = "live|a|" + std::to_string(move);
    Image *moved = store.adopt(key, download(uint8_t(move), 10, 5), 10 + move);
    assert(moved);                                      // always a place for the next one
    store.retire_if([&](const auto &e) { return e.key != key && e.key.rfind("live|a|", 0) == 0; });
    shown = {moved};
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
    picture_store::Store<Image> full;
    full.release = [](void *p) { --live; std::free(p); };
    full.budget = 1u << 20;
    std::set<const Image *> drawn;
    for (size_t i = 0; i < picture_store::ENTRIES; ++i) assert(full.adopt("track" + std::to_string(i), download(1, 10, 5), uint32_t(i)));
    assert(live == int(picture_store::ENTRIES) && full.size() < full.budget);
    // Without being told what the cards draw, the store keeps what it has (as before): the download stays the caller's.
    Image refused = download(2, 10, 5);
    assert(!full.adopt("next", refused, 20));
    drop(refused);
    full.shown = [&](const Image *i) { return drawn.count(i) > 0; };
    // The oldest, "track0", is on a card: "track1" makes way.
    drawn = {full.find("track0")};
    for (size_t i = 2; i < picture_store::ENTRIES; ++i) full.find("track" + std::to_string(i));
    Image *next = full.adopt("next", download(3, 10, 5), 21);
    assert(next && full.find("next") == next && full.find("track0") && !full.find("track1") && live == int(picture_store::ENTRIES));
    // A cover no longer wanted goes before one used longer ago that is.
    full.retire("track9");
    assert(full.adopt("after", download(4, 10, 5), 22) && full.find("track2") && live == int(picture_store::ENTRIES));
    for (auto &e : full.entries) assert(e.key != "track9");  // gone, not just out of sight
    // Every picture on a card: nothing makes way, and nothing is kept.
    drawn.clear();
    for (auto &e : full.entries) drawn.insert(&e.image);
    Image more = download(5, 10, 5);
    assert(!full.adopt("one more", more, 23) && live == int(picture_store::ENTRIES) + 1);
    drop(more);
    drawn.clear();
    full.forget([](const Image *) { return false; });
    assert(live == 0);
  }
  // Over the budget with every picture on a card (GitHub #183, every page kept): a picture only a page out of sight
  // draws makes way, the one used longest ago first, after it was taken off its cards; the glass keeps its own.
  {
    picture_store::Store<Image> kept;
    kept.release = [](void *p) { --live; std::free(p); };
    kept.budget = 250;
    Image *glass = kept.adopt("glass", download(7, 10, 5), 1);
    Image *old_page = kept.adopt("old page", download(7, 10, 5), 2), *new_page = kept.adopt("new page", download(7, 10, 5), 3);
    kept.find("new page");  // used later than the old page's
    const auto shown = [](const Image *) { return true; };  // every picture is on some card
    const auto away = [&](const Image *i) { return i != glass; };
    std::vector<const Image *> taken;
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(live == 2 && taken.size() == 1 && taken[0] == old_page && kept.find("glass") && kept.find("new page") && new_page);
    // Within the budget again: nothing more goes. Without `away` nothing on a card ever goes, as before.
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(live == 2 && taken.size() == 1);
    kept.budget = 50;
    kept.collect(shown);
    assert(live == 2);
    // Only the glass left over the budget: it stays.
    kept.collect(shown, away, [&](const Image *i) { taken.push_back(i); });
    assert(live == 1 && kept.find("glass") && taken.size() == 2);
    kept.forget([](const Image *) { return false; });
    assert(live == 0);
  }
  return 0;
}
