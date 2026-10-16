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
// A plugin's tile (plugin API 0.10, docs/PLUGINS.md "Pictures") shows pictures of its own: places it laid out on its
// card, each with an address (a film's poster). The card asks for all of them as one picture, an atlas of their frames
// from the card's top left (`parts`, as a page of a player's library asks for its covers), the app fetches each
// address once and paints the frames, and the card draws each place its own frame of the atlas: one question, one
// download and one entry in the store for a tile of eight posters, and the same cap as every tile's picture.
//
// Pure, free of LVGL and ESPHome: tests/test_tile_picture.cpp checks it on a PC; runtime_tiles.h measures the card,
// hands the picture to the loader (picture_loader.h) and draws it; plugin_host.cpp measures a plugin tile's places.
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

// A piece of a card's picture (plugin API 0.10): a place of the card's own with a picture of its own address, where it
// lies on the card (the card's top left is 0,0) in the card's pixels. At most MAX_PARTS on one card, the manifest's
// `pictures` (plugin_manifest.MAX_PICTURES, a test keeps them equal).
constexpr size_t MAX_PARTS = 8;
struct Part {
  int x = 0, y = 0, w = 0, h = 0, radius = 0;
  std::string url;
  bool contain = false;       // the whole picture within the place; else the place filled and the rest cut away
  uint8_t turn = 0;           // 0 flat, 1 facing left, 2 facing right (plugin_api.h Turn), drawn by the app
  bool mirror = false;        // a reflection under the picture, within the place
};
// The frame a part takes in the atlas, at the atlas's scale (a card over the cap comes smaller, as a whole).
struct Piece {
  int x = 0, y = 0, w = 0, h = 0, radius = 0;
};
inline Piece piece(const Part &p, int scale) {
  Piece f;
  f.x = picture_store::scaled(p.x, scale);
  f.y = picture_store::scaled(p.y, scale);
  f.w = std::max(1, picture_store::scaled(p.x + p.w, scale) - f.x);
  f.h = std::max(1, picture_store::scaled(p.y + p.h, scale) - f.y);
  f.radius = std::max(0, std::min(picture_store::scaled(p.radius, scale), std::min(f.w, f.h) / 2));
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
  std::vector<Part> parts;    // a plugin tile's places (plugin API 0.10); empty for a picture over the whole place
  int scale = picture_store::SCALE_ONE;  // the atlas's scale, for its pieces
};
// A short hash of a text (FNV-1a), as sixteen hex digits: a mark for what would be too long for a key.
inline std::string digest(const std::string &text) {
  uint64_t h = 1469598103934665603ull;
  for (unsigned char c : text) { h ^= c; h *= 1099511628211ull; }
  char out[17];
  snprintf(out, sizeof(out), "%08lx%08lx", (unsigned long) (h >> 32), (unsigned long) (h & 0xFFFFFFFFu));
  return out;
}
// A plugin tile's ask: its parts, whose atlas spans from the card's top left to the farthest edge of them, within the
// cap (then every piece comes smaller alike). The mark is a digest of the places and their addresses: another address,
// a place that moved or grew, is another picture.
inline void set_parts(Ask &a, std::vector<Part> parts, uint32_t ground, const picture_store::Cap &cap = {}) {
  int right = 0, bottom = 0;
  std::string what;
  for (const auto &p : parts) {
    right = std::max(right, p.x + p.w);
    bottom = std::max(bottom, p.y + p.h);
    what += std::to_string(p.x) + "," + std::to_string(p.y) + "," + std::to_string(p.w) + "," + std::to_string(p.h) + "," +
            std::to_string(p.radius) + (p.contain ? "c" : "f") + std::to_string(p.turn) + (p.mirror ? "m" : "") + p.url + ";";
  }
  a.frame = frame(right, bottom, 0, 0, ground, ground, cap);
  a.scale = picture_store::fit_scale(right, bottom, cap);
  a.parts = std::move(parts);
  a.mark = digest(what);
  a.circle = 0;
  a.every = 0;
  a.drawn = true;  // the app fetches them: an answer without a picture (a host that was slow) is asked again, later each time
}

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

// A text as a JSON string, between quotes.
inline std::string quoted(const std::string &text) {
  std::string out = "\"";
  for (char c : text) {
    if (c == '"' || c == '\\') out += '\\';
    if (static_cast<unsigned char>(c) < 0x20) continue;
    out += c;
  }
  return out + "\"";
}
// The question's fields beside the inbox, the session and its number. A plugin tile's parts (0.10) go as the atlas of
// their pieces with `src`, their addresses, and `fit`, how each fills its place, in the same order.
inline std::vector<std::pair<std::string, std::string>> fields(const Ask &a) {
  char ground[8], one[64];
  snprintf(ground, sizeof(ground), "%06X", (unsigned) a.frame.ground);
  std::string atlas;
  if (a.parts.empty()) {
    snprintf(one, sizeof(one), "[[0,0,%d,%d,%d,%d]]", a.frame.w, a.frame.h, a.frame.radius, a.frame.shade);
    atlas = one;
  } else {
    atlas = "[";
    for (const auto &p : a.parts) {
      const Piece f = piece(p, a.scale);
      snprintf(one, sizeof(one), "%s[%d,%d,%d,%d,%d,0]", atlas.size() > 1 ? "," : "", f.x, f.y, f.w, f.h, f.radius);
      atlas += one;
    }
    atlas += "]";
  }
  std::vector<std::pair<std::string, std::string>> out{{"tiles", a.entity},
                                                       {"idx", std::to_string(a.index)},
                                                       {"size", std::to_string(std::max(CIRCLE_MIN, std::min(CIRCLE_MAX, a.circle)))},
                                                       {"bg", ground},
                                                       {"dark", a.dark ? "1" : "0"},
                                                       {"atlas", atlas}};
  if (!a.parts.empty()) {
    std::string src = "[", fit = "[";
    for (const auto &p : a.parts) {
      if (src.size() > 1) { src += ","; fit += ","; }
      src += quoted(p.url);
      fit += p.contain ? "\"contain\"" : "\"cover\"";
    }
    out.push_back({"src", src + "]"});
    out.push_back({"fit", fit + "]"});
    // Only when a place asks for it, so a flat card's question stays as it was: how each turns, and its reflection.
    bool styled = false;
    for (const auto &p : a.parts) styled = styled || p.turn || p.mirror;
    if (styled) {
      std::string turn = "[", mirror = "[";
      for (const auto &p : a.parts) {
        if (turn.size() > 1) { turn += ","; mirror += ","; }
        turn += p.turn == 1 ? "\"left\"" : p.turn == 2 ? "\"right\"" : "\"\"";
        mirror += p.mirror ? "1" : "0";
      }
      out.push_back({"turn", turn + "]"});
      out.push_back({"mirror", mirror + "]"});
    }
  }
  return out;
}

// ---- A plugin's card over the page (plugin API 0.13) ----
// A card shows pictures the way a plugin tile does: places it laid out in its room, each with an address, asked for as
// one picture of their frames from the room's top left (set_parts). Its key starts apart from every tile's, so a card
// and the tile it opened from never take each other's picture, and names the card, the entity it shows and the frame:
// "pcard|plugin:<plugin>.<card>|<entity>|WxH r0 s0|<ground>|<look>|" and the mark of its places.
inline std::string card_key(const Ask &a, const std::string &card, const std::string &entity) {
  char frame[64];
  snprintf(frame, sizeof(frame), "|%dx%d r%d s%d|%06X|%c|", a.frame.w, a.frame.h, a.frame.radius, a.frame.shade,
           (unsigned) a.frame.ground, a.dark ? 'd' : 'l');
  return "pcard|" + card + "|" + entity + frame + a.mark;
}
// The loader's tag for a card's question: one card is open at a time.
inline std::string card_tag(const std::string &card) { return "pcard|" + card; }
// Where the places lie, without what they show: the same digest for a card that only shows other addresses, so it keeps
// its last picture on its places until the next is here.
inline std::string layout_of(const std::vector<Part> &parts) {
  std::string what;
  for (const auto &p : parts)
    what += std::to_string(p.x) + "," + std::to_string(p.y) + "," + std::to_string(p.w) + "," + std::to_string(p.h) + ";";
  return digest(what);
}
// A card's question: a tile's fields with `card` (the app answers it as "pcard") and `for`, the entity the card shows
// ("" for none), whose Home Assistant pictures it may show. `tiles` names the card (plugin:<plugin>.<card>).
inline std::vector<std::pair<std::string, std::string>> card_fields(const Ask &a, const std::string &entity) {
  auto out = fields(a);
  out.push_back({"card", "1"});
  out.push_back({"for", entity});
  return out;
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
