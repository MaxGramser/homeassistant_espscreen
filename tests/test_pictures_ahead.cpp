// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_pictures_ahead.cpp -o /tmp/test_pictures_ahead && /tmp/test_pictures_ahead
// Pictures out of sight use spare room and nothing else (GitHub #415): the loader and the store together, as
// picture_rounds_lvgl.h binds them. A Waveshare 7B with a store of 1046 KB sat on a page without pictures while two kept
// pages held a picture each, 713 KB and 478 KB. Each alone fits under three quarters of the store, both do not: the
// second came, the store went over its budget, the first was let go from its page out of sight, the store was under three
// quarters again, the first was fetched ahead again, and so on every second or two until standby. With the rule a
// picture fetched ahead is taken only when the store with it in stays at or under the level, so nothing is let go and
// the downloads stop; two that fit together are both fetched ahead.
#include "../components/smart_display/picture_loader.h"
#include "../components/smart_display/picture_loader.cpp"  // the loader's bodies (its own compilation unit)
#include "../components/smart_display/picture_store.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

using namespace picture_loader;

struct Header { uint32_t w = 0, h = 0, cf = 0; };
struct Image { Header header; uint32_t data_size = 0; const uint8_t *data = nullptr; };

// A screen on a page without pictures, its kept pages drawing what the store holds for them.
struct Screen {
  Loader loader;
  picture_store::Store<Image> store;
  std::map<std::string, std::pair<int, int>> size;  // what the app sends for each key (w, h)
  std::string loading;
  Slot loading_slot = Slot::LIVE;
  int downloads = 0, let_go = 0, refused = 0, asked = 0;
  bool rule = true;  // the spare-room rule bound, as picture_rounds_lvgl.h does

  explicit Screen(size_t budget) {
    store.budget = budget;
    store.release = [](void *p) { std::free(p); };
    // Every picture kept is drawn by a card of a kept page (the glass's page has none), so none goes as unused.
    store.shown = [](const Image *) { return true; };
    loader.kept = [this](const std::string &key, uint32_t &at) {
      if (auto *e = store.entry(key)) { at = e->stored_at; return true; }
      return false;
    };
    loader.load = [this](Slot slot, const std::string &, const std::string &key) { loading = key; loading_slot = slot; ++downloads; };
    loader.forget = [this](const std::string &key) { store.retire(key); };
    loader.room_ahead = [this](size_t bytes, size_t coming) { return !rule || store.fits_ahead(bytes, coming); };
  }
  Want ahead(const std::string &key) {
    Want w;
    w.key = key; w.tag = "tile|" + key; w.slot = Slot::LIVE; w.rank = Rank::AHEAD;
    w.bytes = picture_store::bytes_of(size[key].first, size[key].second);
    w.ask = [this, key] { ++asked; loader.answer("tile|" + key, "http://app/" + key, 0); };
    return w;
  }
  // One round: both kept pages say what they want, a download that ran ends, the store keeps to its budget.
  void round(uint32_t now) { start(now); finish(now); }
  void start(uint32_t now) {
    loader.begin();
    uint32_t n = 0;
    for (const auto &k : size) loader.want({Kind::TILE, n++}, ahead(k.first));
    loader.end(now, true);
  }
  void finish(uint32_t now) {
    if (loading.empty()) return;
    const bool was_ahead = loader.loading_rank(loading_slot) == Rank::AHEAD;
    const std::string key = loader.loaded(loading_slot, true, now);
    loading.clear();
    const auto [w, h] = size[key];
    const size_t bytes = picture_store::bytes_of(w, h);
    if (rule && was_ahead && !store.fits_ahead(bytes)) { ++refused; return; }  // picture_done: not kept
    auto *pixels = static_cast<uint8_t *>(std::malloc(bytes));
    std::memset(pixels, 1, bytes);
    Image download{{uint32_t(w), uint32_t(h), 1}, uint32_t(bytes), pixels};
    if (!store.adopt(key, download, now)) std::free(pixels);
    loader.arrived(key, false);
    // Over the budget, a picture only a page out of sight draws goes (picture_away / picture_let_go).
    store.collect(store.shown, [](const Image *) { return true; }, [this](const Image *) { ++let_go; });
  }
};

int main() {
  constexpr size_t KB = 1024;
  // One way to size a picture, and one level.
  static_assert(picture_store::bytes_of(640, 360) == 640 * 360 * 2 && picture_store::bytes_of(0, 10) == 0);
  {
    picture_store::Store<Image> s;
    s.budget = 1000;
    assert(s.ahead_level() == 750 && s.fits_ahead(750) && !s.fits_ahead(751) && !s.fits_ahead(700, 51));
  }
  // GitHub #415's screen: 1046 KB, pictures of 713 KB (a 3x4 plugin tile) and 478 KB (a 2x4 map).
  auto issue = [&](bool rule) {
    Screen s(1046 * KB);
    s.rule = rule;
    s.size["plugin"] = {596, 612};  // 729,504 B, about 713 KB
    s.size["map"] = {490, 500};     // 490,000 B, about 478 KB
    for (uint32_t t = 1000; t < 1000 + 60 * 1000; t += 250) s.round(t);  // a minute of an awake screen
    return s;
  };
  {
    const Screen before = issue(false);  // the guard of before: the two take turns
    assert(before.let_go > 10 && before.downloads > 10);
    std::printf("without the rule: %d downloads, %d let go in a minute\n", before.downloads, before.let_go);
  }
  {
    const Screen after = issue(true);
    assert(after.let_go == 0);
    // The first that came stays (the map, by the order the pages ask), the other loads when its page comes back. The app
    // is asked for one picture only: the second would not fit beside the first, which was let in the same round.
    assert(after.downloads == 1 && after.store.size() == picture_store::bytes_of(490, 500));
    assert(after.asked == 1);
    std::printf("with the rule: %d download, nothing let go\n", after.downloads);
  }
  // The mirror: two that fit together are both fetched ahead, once each.
  {
    Screen s(1046 * KB);
    s.size["cover"] = {300, 300};
    s.size["map"] = {490, 500};
    for (uint32_t t = 1000; t < 31000; t += 250) s.round(t);
    assert(s.downloads == 2 && s.asked == 2 && s.let_go == 0 && s.store.entry("cover") && s.store.entry("map"));
  }
  // The room taken meanwhile: a picture that arrives for a page out of sight when it no longer fits is not kept.
  {
    Screen s(1000 * KB);
    s.size["map"] = {490, 500};
    s.start(1000);   // asked, answered and started: it fitted then
    assert(s.loading == "map");
    auto *pixels = static_cast<uint8_t *>(std::malloc(600 * KB));
    Image glass{{1, 1, 1}, uint32_t(600 * KB), pixels};
    assert(s.store.adopt("glass", glass, 1100));  // a picture for the glass came first
    s.finish(1200);
    assert(s.refused == 1 && !s.store.entry("map") && s.let_go == 0 && s.store.entry("glass"));
  }
  std::printf("pictures ahead: the issue's two pictures stop taking turns, two that fit both come, a late one is not kept\n");
  return 0;
}
