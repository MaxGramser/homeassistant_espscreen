#pragma once
// A tile's own picture (GitHub #183). A live camera, a media tile's album cover, a favourite and a map show a picture
// that ESP Screen Manager paints for exactly their place on the card: the whole card, or the icon's circle. Each tile
// asks for its own picture, at its own pace, and the store keeps it under its own key:
//
// - A new track replaces one cover and nothing else; a camera refreshes at the pace its own tile chose.
// - The size cap (picture_store::MAX_SIDE, MAX_BYTES) holds for each picture alone, so a picture is never made smaller
//   because of another picture on the page.
// - A tile on a kept page keeps its picture, and one that does not refresh is fetched ahead for it.
//
// Before, a page's pictures came as one image spanning all of them, from the top left of the first to the bottom right
// of the last. Every change sent all of them again (five cameras for one new album cover), and on a large glass the
// span went over the cap: every picture of the page then came smaller, with a dark edge, as soon as one more tile had a
// picture (a player that started to play).
//
// The question is the one a page of pictures has always been asked with, for a page of one tile: `esphome.screen_camera`
// with `tiles`, `idx`, `size`, `bg`, `dark` and an `atlas` of one frame at the top left. Every app since 0.3.8 answers it
// (camera_feed.live_request, tile_art.parse), with the question's number (`view`) in its answer, so the answer finds
// its tile by that number (Questions). An app keeps the strip of an older screen as it was.
//
// Pure, free of LVGL and ESPHome: tests/test_tile_picture.cpp checks it on a PC; runtime_tiles.h measures the card,
// hands the picture to the loader (picture_loader.h) and draws it.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>
#include "picture_store.h"

namespace tile_picture {
// The shade the app lays over a picture with words on it (an album cover under its track, a favourite under its name),
// as tile_art.parse takes it: 0 or 170.
constexpr int SHADE = 170;
// The icon's circle an older app checks a question against (camera_feed.LIVE_SIZES); the frame says the real size.
constexpr int CIRCLE_MIN = 24, CIRCLE_MAX = 160;

// How the app paints a picture: its pixels (within the cap), the radius of its corners, a shade over all of it and the
// colour behind its corners.
struct Frame {
  int w = 0, h = 0, radius = 0, shade = 0;
  uint32_t ground = 0;
};
// The frame for a place of `width` by `height` with corners of `radius`: the place's own pixels, or, over the board's
// cap, the largest picture of its proportions within it, which then sits in the middle of its place on `smaller_ground`.
inline Frame frame(int width, int height, int radius, int shade, uint32_t ground, uint32_t smaller_ground,
                   const picture_store::Cap &cap = {}) {
  Frame f;
  const int scale = picture_store::fit_scale(width, height, cap);
  f.w = std::max(1, picture_store::scaled(width, scale));
  f.h = std::max(1, picture_store::scaled(height, scale));
  f.radius = std::max(0, std::min(picture_store::scaled(radius, scale), std::min(f.w, f.h) / 2));
  f.shade = shade == SHADE ? SHADE : 0;
  f.ground = f.w < width || f.h < height ? smaller_ground : ground;
  return f;
}

// What a tile asks for.
struct Ask {
  size_t index = 0;           // the tile's index in the layout: the app paints it the way that tile's settings say
  std::string entity;
  std::string mark;           // what makes it another picture: a track, a favourite's choice, where people on a map are
  Frame frame;
  int circle = 0;             // the icon's circle, for an older app's check
  bool dark = false;          // the screen's look: a map is drawn in it, and its ground differs
  uint32_t every = 0;         // a camera's pace in ms; 0: once
  bool drawn = false;         // the app draws it (a map), so an answer without one is asked again
};

// The picture's place: its tile, its entity and its frame. The next picture of the same place has another mark (the
// next track); a camera's next picture keeps its key and is written over the last one.
inline std::string place(const Ask &a) {
  char frame[64];
  snprintf(frame, sizeof(frame), "|%dx%d r%d s%d|%06X|%c|", a.frame.w, a.frame.h, a.frame.radius, a.frame.shade,
           (unsigned) a.frame.ground, a.dark ? 'd' : 'l');
  return "tile|" + std::to_string(a.index) + "|" + a.entity + frame;
}
inline std::string key(const Ask &a) { return place(a) + a.mark; }
// A key's place: everything before its mark ("" for no tile picture's key).
inline std::string place_of(const std::string &key) {
  size_t at = 0;
  for (int bars = 0; bars < 6; ++bars) {
    at = key.find('|', at);
    if (at == std::string::npos) return {};
    ++at;
  }
  return key.compare(0, 5, "tile|") == 0 ? key.substr(0, at) : std::string();
}
// Whether a key is of this tile showing this entity (a card on a screen without kept pages shows another tile on the
// next page, and keeps the key it had until the next round).
inline bool belongs(const std::string &key, size_t index, const std::string &entity) {
  const std::string head = "tile|" + std::to_string(index) + "|" + entity + "|";
  return key.size() > head.size() && key.compare(0, head.size(), head) == 0;
}
// The loader's tag for a tile's question: one per tile, so the tiles of a page are asked for together.
inline std::string tag(size_t index) { return "tile|" + std::to_string(index); }

// The question's fields beside the inbox, the session and its number.
inline std::vector<std::pair<std::string, std::string>> fields(const Ask &a) {
  char ground[8], atlas[64];
  snprintf(ground, sizeof(ground), "%06X", (unsigned) a.frame.ground);
  snprintf(atlas, sizeof(atlas), "[[0,0,%d,%d,%d,%d]]", a.frame.w, a.frame.h, a.frame.radius, a.frame.shade);
  return {{"tiles", a.entity},
          {"idx", std::to_string(a.index)},
          {"size", std::to_string(std::max(CIRCLE_MIN, std::min(CIRCLE_MAX, a.circle)))},
          {"bg", ground},
          {"dark", a.dark ? "1" : "0"},
          {"atlas", atlas}};
}

// The questions out to the app, by number: every question has a number of its own, the app answers with it, and only
// the answer to a tile's last question counts (an earlier one was for a picture the tile has moved on from).
class Questions {
 public:
  // A new question of the tile's: its number.
  uint32_t ask(size_t index) {
    const uint32_t number = ++count_;
    for (auto &q : last_) if (q.first == index) { q.second = number; return number; }
    last_.emplace_back(index, number);
    return number;
  }
  // The tile an answer with this number is for, or -1 when it is no tile's last question.
  int answered(uint32_t number) const {
    for (const auto &q : last_) if (q.second == number) return static_cast<int>(q.first);
    return -1;
  }
  // Another layout: no answer to a question of the last one counts.
  void clear() { last_.clear(); }

 private:
  uint32_t count_ = 0;
  std::vector<std::pair<size_t, uint32_t>> last_;
};
}  // namespace tile_picture
