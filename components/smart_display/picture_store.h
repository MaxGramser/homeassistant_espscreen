#pragma once
// Pictures kept until they change (firmware 0.3.2+). A download lands in one of the board's online_image buffers, which
// the next download overwrites; the store copies it into memory of its own (PSRAM) under what was asked for (the tiles,
// their colours, the track), and the cards draw that copy. A page that comes back finds its pictures here: an album cover
// is not fetched again while the track plays, a camera shows its last picture at once and refreshes at its own pace.
//
// A copy stays where it is while a card may draw it: a camera's next picture of the same size is written over the old
// one, another size gets a new copy and the old one waits until no card shows it (`collect`). The store keeps to its
// budget by dropping the pictures used longest ago, never one a card still shows.
//
// Pure bookkeeping over an image descriptor with LVGL's fields (header, data_size, data), so tests/test_picture_store.cpp
// checks it on a PC with a stand-in; runtime_tiles.h uses lv_image_dsc_t and PSRAM.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>

namespace picture_store {
// One place per picture a screen may hold at once: every tile's own picture (tile_picture.h) on the glass and on the
// kept pages, the covers, the full view, the alert's and the library's. A board that draws no pictures (the CYD, built
// without SCREEN_PICTURES) keeps none and needs no room for them.
#if defined(USE_ESP32) && !defined(SCREEN_PICTURES)
constexpr size_t ENTRIES = 1;
#else
constexpr size_t ENTRIES = 48;
#endif

// The largest picture any screen gets, whatever its glass (firmware 0.9.0+, GitHub #68): at most MAX_SIDE pixels
// either way and MAX_BYTES decoded (RGB565, two bytes a pixel). It holds for each picture alone: a tile's picture is
// its own (tile_picture.h), so only a tile larger than the cap, a camera over a whole 10-inch page, comes smaller and
// is shown in the middle of its place. 1024x640 keeps every board up to the
// 7-inch and the 1024x600 glass at its own pixels. ESP Screen Manager caps the pictures it sizes itself with the same
// numbers (camera_feed.PICTURE_MAX_SIDE and PICTURE_MAX_BYTES, tests/test_camera.py keeps them equal).
constexpr int MAX_SIDE = 1024;
constexpr size_t MAX_BYTES = 1024 * 640 * 2;
// A board whose store has the room takes larger pictures (GitHub #183): one picture may be a third of the store's
// budget, at most LARGE_SIDE either way. The 32 MB of the P4 boards keep 6 MB, so one picture of 2 MB: the 10-inch
// glass's 1280x800 at its own pixels, for a camera over the whole page, the full view and the screensaver. A board with
// 8 MB keeps the cap above. ESP Screen Manager honours the same side (camera_feed.PICTURE_LARGE_SIDE).
constexpr int LARGE_SIDE = 2048;
struct Cap {
  int side = MAX_SIDE;
  size_t bytes = MAX_BYTES;
};
inline Cap cap_for(size_t budget) {
  Cap cap;
  if (budget / 3 > MAX_BYTES) { cap.side = LARGE_SIDE; cap.bytes = budget / 3; }
  return cap;
}
// A scale in 1/SCALE_ONE, so the screen and its request round a picture's frames the same way.
constexpr int SCALE_ONE = 4096;
// The scale that brings a picture of `width` by `height` within the cap, SCALE_ONE when it fits already.
inline int fit_scale(int width, int height, const Cap &cap = Cap{}) {
  if (width <= 0 || height <= 0) return SCALE_ONE;
  double scale = std::min({1.0, double(cap.side) / width, double(cap.side) / height,
                           std::sqrt(double(cap.bytes) / (2.0 * width * height))});
  return std::max(1, static_cast<int>(scale * SCALE_ONE));
}
// A coordinate at that scale, rounded down: a frame from `x` to `x + w` becomes scaled(x) to scaled(x + w), so frames
// that did not overlap still do not.
inline int scaled(int value, int scale) { return static_cast<int>(static_cast<int64_t>(value) * scale / SCALE_ONE); }

template <class Image> struct Store {
  struct Entry {
    std::string key;
    Image image{};
    void *buffer = nullptr;
    size_t bytes = 0;
    uint32_t stored_at = 0, used = 0;
    bool retired = false;    // replaced by a copy of another size; freed once no card shows it
  };
  std::array<Entry, ENTRIES> entries{};
  std::function<void *(size_t)> allocate;
  std::function<void(void *)> release;
  // Whether a card (or an open card over the page) still draws a picture: put() makes room only with what none draws.
  std::function<bool(const Image *)> shown;
  // Every copy kept, renewed, retired and freed, for a diagnosis (runtime_tiles.h logs it at DEBUG).
  std::function<void(const char *what, const Entry &)> log;
  size_t budget = 0;         // bytes; 0 keeps nothing, so a board without the room stores no picture
  uint32_t uses = 0;

  size_t size() const {
    size_t total = 0;
    for (const auto &e : entries) total += e.bytes;
    return total;
  }
  Entry *entry(const std::string &key) {
    if (key.empty()) return nullptr;
    for (auto &e : entries) if (e.buffer && !e.retired && e.key == key) return &e;
    return nullptr;
  }
  // The kept picture for `key`, or nullptr.
  Image *find(const std::string &key) {
    Entry *e = entry(key);
    if (!e) return nullptr;
    e->used = ++uses;
    return &e->image;
  }
  // Keep a copy of `from` under `key`. The same key with the same size keeps its place (the cards drawing it show the
  // new picture); nullptr when there is no room, and the caller draws nothing from the store. With every slot taken the
  // picture used longest ago that no card draws makes way (make_room).
  Image *put(const std::string &key, const Image &from, uint32_t now) {
    if (!budget || !allocate || !from.data || !from.data_size || key.empty() || from.data_size > budget) return nullptr;
    Entry *e = entry(key);
    if (e && e->bytes == from.data_size && std::memcmp(&e->image.header, &from.header, sizeof(from.header)) == 0) {
      std::memcpy(e->buffer, from.data, from.data_size);
      e->stored_at = now; e->used = ++uses;
      note("renews", *e);
      return &e->image;
    }
    if (e) { e->retired = true; note("retires (another size)", *e); }
    Entry *slot = nullptr;
    for (auto &c : entries) if (!c.buffer) { slot = &c; break; }
    if (!slot) slot = make_room();
    if (!slot) return nullptr;
    void *buffer = allocate(from.data_size);
    if (!buffer) return nullptr;
    std::memcpy(buffer, from.data, from.data_size);
    slot->key = key; slot->buffer = buffer; slot->bytes = from.data_size;
    slot->image = from;
    slot->image.data = static_cast<decltype(from.data)>(buffer);
    slot->stored_at = now; slot->used = ++uses; slot->retired = false;
    note("keeps", *slot);
    return &slot->image;
  }
  // Every slot taken (firmware 0.52.0): the picture that no card draws and was used longest ago makes way, one no longer
  // wanted (retired) before any other. Before, the slots ran out long before the bytes reached the budget: on a 4-inch
  // board sixteen covers of tracks gone by take 0.7 MB of 1.5, and from then on no new picture was kept, so a media card
  // stood on its placeholder for good (GitHub #177). nullptr when every picture is on a card.
  Entry *make_room() {
    if (!shown) return nullptr;
    Entry *oldest = nullptr;
    for (auto &c : entries) {
      if (!c.buffer || shown(&c.image)) continue;
      if (!oldest || (c.retired != oldest->retired ? c.retired : c.used < oldest->used)) oldest = &c;
    }
    if (oldest) drop(*oldest, "frees (making room)");
    return oldest;
  }
  // Frees what may go: copies that were replaced, then the pictures used longest ago while the store is over its
  // budget. `shown` says whether a card (or an open card over the page) still draws a picture. Over the budget with
  // every picture on a card, `away` says which only a card out of sight draws (a kept page's, GitHub #183): the one of
  // those used longest ago goes, after `let_go` took it off its cards, which ask for it again when their page comes
  // back. What the glass shows always stays.
  void collect(const std::function<bool(const Image *)> &shown, const std::function<bool(const Image *)> &away = {},
               const std::function<void(const Image *)> &let_go = {}) {
    for (auto &e : entries) if (e.buffer && e.retired && !shown(&e.image)) drop(e, "frees (retired, on no card)");
    while (size() > budget) {
      Entry *oldest = nullptr;
      for (auto &e : entries)
        if (e.buffer && !shown(&e.image) && (!oldest || e.used < oldest->used)) oldest = &e;
      bool held = false;
      if (!oldest && away) {
        for (auto &e : entries)
          if (e.buffer && away(&e.image) && (!oldest || e.used < oldest->used)) oldest = &e;
        held = oldest != nullptr;
      }
      if (!oldest) return;  // everything left is on the glass: it stays until its card lets it go
      if (held && let_go) let_go(&oldest->image);
      drop(*oldest, held ? "frees (over the budget, from a page out of sight)" : "frees (over the budget)");
    }
  }
  // The picture for `key` is the same as before (the app answered 304): kept as it is, as fresh as a new one.
  void touch(const std::string &key, uint32_t now) {
    if (Entry *e = entry(key)) { e->stored_at = now; e->used = ++uses; }
  }
  // The picture for `key` is no longer wanted (the camera full screen closed): it goes at the next collect once nothing
  // draws it, before any picture that is still wanted.
  void retire(const std::string &key) {
    if (Entry *e = entry(key)) { e->retired = true; note("retires", *e); }
  }
  // The entry whose copy this is, also one already replaced (a card may still draw it), or nullptr.
  Entry *holder(const Image *image) {
    if (!image) return nullptr;
    for (auto &e : entries) if (e.buffer && &e.image == image) return &e;
    return nullptr;
  }
  // Every picture `gone` names is no longer wanted (a page's strip from before someone on its map moved): each goes
  // at the next collect once nothing draws it, so a tile whose picture changes often never fills the store.
  void retire_if(const std::function<bool(const Entry &)> &gone) {
    for (auto &e : entries) if (e.buffer && !e.retired && gone(e)) e.retired = true;
  }
  // Nothing kept is right any more (another layout, another look): what no card shows goes now, the rest as soon as
  // its card lets it go.
  void forget(const std::function<bool(const Image *)> &shown) {
    for (auto &e : entries) if (e.buffer && !shown(&e.image)) drop(e, "frees (another layout)");
    for (auto &e : entries) if (e.buffer) e.retired = true;
  }

 private:
  void note(const char *what, const Entry &e) const { if (log) log(what, e); }
  void drop(Entry &e, const char *why = "frees") {
    note(why, e);
    if (release) release(e.buffer);
    e = Entry{};
  }
};
}  // namespace picture_store
