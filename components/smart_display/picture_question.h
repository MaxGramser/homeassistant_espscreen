#pragma once
// The question a screen asks for a picture (docs/PICTURES.md, "The question"): one shape for every owner on the screen.
// The full view, the screensaver, an open card's cover or map, a player's library, a tile's own picture and a plugin's
// places each say the same things: who asks, a source per place (what the picture is of), the picture's size and its
// places in it, how each is painted, the formats this screen's decoder takes, and whether it may stream. ESP Screen
// Manager answers every one of them the one way (screen_manager/app/picture_service.py).
//
// An app that reads questions says so in its hello (`features` holds "pictures", picture_question.FEATURE); to an older
// app the screen asks the way that app understands, the old fields of each owner, made here from the same question
// (legacy()), so a screen built from main before its app was updated still gets its pictures. Each answer finds its
// owner by its number (Numbers): one count for every owner, whichever way it was asked.
//
// Pure, free of LVGL and ESPHome: tests/test_picture_question.cpp checks the question, its old fields against what each
// owner asked before, and the numbers on a PC.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>
#include "picture_store.h"

namespace picture_question {
// Who asks (picture_question.OWNERS in the app).
enum class Owner : uint8_t { TILE, VIEW, CARD, SAVER, LIBRARY, PLUGIN_TILE, PLUGIN_CARD, PLUGIN_SAVER };
inline const char *owner_text(Owner o) {
  switch (o) {
    case Owner::TILE: return "tile";
    case Owner::VIEW: return "view";
    case Owner::CARD: return "card";
    case Owner::SAVER: return "saver";
    case Owner::LIBRARY: return "library";
    case Owner::PLUGIN_TILE: return "plugin_tile";
    case Owner::PLUGIN_CARD: return "plugin_card";
    default: return "plugin_saver";
  }
}
// How a picture fills its place (picture_question.FITS in the app): cut to it, whole on black, whole on what lies under
// it, whole on its own colour, filled when about its shape and whole otherwise (the screensaver's photos), at its own
// proportions within the box (a full view's still), stretched to the box (a frame made for those proportions), a cover
// over the screensaver's glass.
enum class Fit : uint8_t { COVER, CONTAIN, WITHIN, WHOLE, AUTO, SHRINK, EXACT, SAVER };
inline const char *fit_text(Fit f) {
  switch (f) {
    case Fit::CONTAIN: return "contain";
    case Fit::WITHIN: return "within";
    case Fit::WHOLE: return "whole";
    case Fit::AUTO: return "auto";
    case Fit::SHRINK: return "shrink";
    case Fit::EXACT: return "exact";
    case Fit::SAVER: return "saver";
    default: return "cover";
  }
}
// A place in the picture: where it lies, its corners and shade (0 or tile_picture::SHADE), how it fills, the colour
// behind its corners, and its effects: the shade under a name (`fade`), darkened by `dim` percent, turned (`turn` 1
// facing left, 2 facing right) and reflected, and cut `move` percent larger on either side to move slowly in.
struct Place {
  int x = 0, y = 0, w = 0, h = 0, radius = 0, shade = 0;
  Fit fit = Fit::COVER;
  uint32_t ground = 0;
  bool fade = false;
  uint8_t dim = 0;
  uint8_t turn = 0;
  bool mirror = false;
  uint8_t move = 0;
};
struct Question {
  Owner owner = Owner::VIEW;
  int index = -1;                     // a tile's index (TILE, PLUGIN_TILE), or the tile a plugin's card opened from
  std::string key;                    // a plugin's type, plugin:<plugin>.<tile|card|saver>
  std::string of;                     // the entity a tile, a map, a plugin's card or step shows
  std::vector<std::string> sources;   // one per place, or one for every place (docs/PICTURES.md "Sources")
  int w = 0, h = 0;                   // the picture
  std::vector<Place> places;
  bool dark = false;                  // the screen's look
  size_t cap = picture_store::MAX_BYTES;   // the most bytes one decoded picture may take here
  std::vector<std::string> formats{"bmp24"};  // what this screen's decoder takes, best first
  uint32_t pace = 0;                  // ms until the next picture of a source that changes by itself; 0 once
  int live_w = 0, live_h = 0;         // the rectangle this screen can stream into; 0 when it cannot
  bool sound = false;                 // with the camera's sound
  int circle = 0;                     // for an older app only: a tile's icon circle (camera_feed.LIVE_SIZES)
};

// ---- The sources (docs/PICTURES.md "Sources") ----
inline std::string tile_source(size_t index) { return "tile:" + std::to_string(index); }
inline std::string camera_source(const std::string &entity) { return "camera:" + entity; }
inline std::string cover_source(const std::string &entity) { return "cover:" + entity; }
inline std::string vacuum_source(const std::string &entity) { return "vacuum:" + entity; }
inline std::string library_source(const std::string &entity, uint32_t item) { return "library:" + entity + "/" + std::to_string(item); }
inline const char *const PHOTOS_SOURCE = "photos:";
// A map tile's full view: its index, a person a finger picked on it and the moves of the map's own keys.
inline std::string map_source(int index, const std::string &focus, const std::string &move) {
  std::string out = "map:" + std::to_string(std::max(0, index));
  std::string query;
  if (!focus.empty()) query += "focus=" + focus;
  if (!move.empty()) query += (query.empty() ? "" : "&") + std::string("move=") + move;
  return query.empty() ? out : out + "?" + query;
}
// What a source text names: its kind ("camera") and its reference ("camera.front_door"), and a query's value.
inline std::string kind_of(const std::string &source) {
  const size_t colon = source.find(':');
  return colon == std::string::npos || source.compare(0, 4, "http") == 0 || source[0] == '/' ? std::string() : source.substr(0, colon);
}
inline std::string ref_of(const std::string &source) {
  const size_t colon = source.find(':');
  if (colon == std::string::npos) return {};
  const size_t query = source.find('?', colon);
  return source.substr(colon + 1, query == std::string::npos ? std::string::npos : query - colon - 1);
}
inline std::string param_of(const std::string &source, const std::string &name) {
  const size_t query = source.find('?');
  if (query == std::string::npos) return {};
  size_t at = query + 1;
  while (at < source.size()) {
    size_t end = source.find('&', at);
    if (end == std::string::npos) end = source.size();
    const std::string part = source.substr(at, end - at);
    if (part.compare(0, name.size() + 1, name + "=") == 0) return part.substr(name.size() + 1);
    at = end + 1;
  }
  return {};
}

// ---- Writing it ----
// A text as a JSON string, between quotes (control characters left out).
inline std::string quoted(const std::string &text) {
  std::string out = "\"";
  for (char c : text) {
    if (c == '"' || c == '\\') out += '\\';
    if (static_cast<unsigned char>(c) < 0x20) continue;
    out += c;
  }
  return out + "\"";
}
inline std::string hex(uint32_t colour) {
  char out[8];
  snprintf(out, sizeof(out), "%06X", (unsigned) (colour & 0xFFFFFF));
  return out;
}
// The question as the app reads it: the compact JSON of the event's `q` (picture_question.parse in the app).
inline std::string json(const Question &q) {
  std::string out = "{\"o\":\"" + std::string(owner_text(q.owner)) + "\"";
  if (q.owner == Owner::TILE || q.owner == Owner::PLUGIN_TILE) out += ",\"i\":" + std::to_string(std::max(0, q.index));
  if (!q.key.empty()) out += ",\"p\":" + quoted(q.key);
  if (!q.of.empty()) out += ",\"for\":" + quoted(q.of);
  out += ",\"src\":[";
  for (size_t i = 0; i < q.sources.size(); ++i) out += (i ? "," : "") + quoted(q.sources[i]);
  out += "],\"box\":[" + std::to_string(q.w) + "," + std::to_string(q.h) + "],\"at\":[";
  std::string fits, grounds, effects;
  bool any_effect = false;
  for (size_t i = 0; i < q.places.size(); ++i) {
    const Place &p = q.places[i];
    char frame[96];
    snprintf(frame, sizeof(frame), "%s[%d,%d,%d,%d,%d,%d]", i ? "," : "", p.x, p.y, p.w, p.h, p.radius, p.shade);
    out += frame;
    fits += std::string(i ? "," : "") + "\"" + fit_text(p.fit) + "\"";
    grounds += std::string(i ? "," : "") + "\"" + hex(p.ground) + "\"";
    std::string fx;
    if (p.fade) fx += "\"fade\":1";
    if (p.dim) fx += std::string(fx.empty() ? "" : ",") + "\"dim\":" + std::to_string(p.dim);
    if (p.turn) fx += std::string(fx.empty() ? "" : ",") + "\"turn\":\"" + (p.turn == 1 ? "left" : "right") + "\"";
    if (p.mirror) fx += std::string(fx.empty() ? "" : ",") + "\"mirror\":1";
    if (p.move) fx += std::string(fx.empty() ? "" : ",") + "\"move\":" + std::to_string(p.move);
    any_effect = any_effect || !fx.empty();
    effects += std::string(i ? "," : "") + "{" + fx + "}";
  }
  out += "],\"fit\":[" + fits + "],\"bg\":[" + grounds + "]";
  if (any_effect) out += ",\"fx\":[" + effects + "]";
  out += std::string(",\"look\":\"") + (q.dark ? "d" : "l") + "\"";
  if (q.cap > picture_store::MAX_BYTES) out += ",\"cap\":" + std::to_string(q.cap);
  out += ",\"fmt\":[";
  for (size_t i = 0; i < q.formats.size(); ++i) out += (i ? "," : "") + quoted(q.formats[i]);
  out += "]";
  if (q.pace) out += ",\"pace\":" + std::to_string(q.pace);
  if (q.live_w > 0 && q.live_h > 0) {
    out += ",\"live\":[" + std::to_string(q.live_w) + "," + std::to_string(q.live_h) + "]";
    if (q.sound) out += ",\"sound\":1";
  }
  return out + "}";
}

// ---- The question as an older app reads it (before the feature `pictures`) ----
// The fields each owner asked with before, made from the same question; the sender adds the session's (`inbox`,
// `session`, `rev`) and the owner's own number (`view`). The constants an older app checks a tile's question against
// (picture_legacy.LIVE_SIZES in the app) and the screensaver's photos entity are the owners' (tile_picture.h,
// runtime_tiles.h).
//
// TO REMOVE ONE DAY: this part (legacy, atlas_of, CIRCLE_MIN/MAX) and the `else` of runtime_tiles::picture_ask that
// uses it exist only for an app from before the feature `pictures` (0.4.89 and older) that builds this firmware anyway:
// a Docker or other app without a channel, or a screen's own ESPHome YAML on `ref: main` (core.ref; the stable app
// builds its own release tag since 0.4.85). The maintainer chose to keep it (2026-10-20): it costs about 2.3 KB on the
// boards with pictures and none on the 4 MB boards (picture_ask asks nothing there). It may go once no app older than
// the feature can build a screen any more; the app's own reading of older firmware (picture_legacy.py) stays.
constexpr int CIRCLE_MIN = 24, CIRCLE_MAX = 160;
using Fields = std::vector<std::pair<std::string, std::string>>;
inline std::string atlas_of(const Question &q) {
  std::string atlas = "[";
  for (size_t i = 0; i < q.places.size(); ++i) {
    const Place &p = q.places[i];
    char frame[96];
    snprintf(frame, sizeof(frame), "%s[%d,%d,%d,%d,%d,%d]", i ? "," : "", p.x, p.y, p.w, p.h, p.radius, p.shade);
    atlas += frame;
  }
  return atlas + "]";
}
inline Fields legacy(const Question &q) {
  Fields out;
  const std::string first = q.sources.empty() ? std::string() : q.sources.front();
  const std::string kind = kind_of(first), ref = ref_of(first);
  const Place place = q.places.empty() ? Place{} : q.places.front();
  const std::string look = q.dark ? "1" : "0";
  const bool larger = q.cap > picture_store::MAX_BYTES;
  auto stream = [&]() {
    if (q.live_w > 0 && q.live_h > 0) {
      out.emplace_back("live", std::to_string(q.live_w) + "x" + std::to_string(q.live_h));
      if (q.sound) out.emplace_back("sound", "1");
    }
  };
  switch (q.owner) {
    case Owner::VIEW:
    case Owner::SAVER: {
      const bool map = kind == "map";
      if (q.owner == Owner::SAVER)
        out.emplace_back("saver", kind == "cover" ? "media" : kind == "camera" ? "camera" : "photos");
      if (larger) out.emplace_back("cap", std::to_string(q.cap));
      stream();
      out.emplace_back("entity", map || kind == "photos" ? q.of : ref);
      out.emplace_back("size", "");
      out.emplace_back("bg", "");
      if (map) {
        out.emplace_back("idx", ref);
        out.emplace_back("dark", look);
        out.emplace_back("focus", param_of(first, "focus"));
        out.emplace_back("move", param_of(first, "move"));
      }
      break;
    }
    case Owner::CARD:
      if (kind == "vacuum") {
        out.emplace_back("entity", ref);
        out.emplace_back("vmap", std::to_string(q.w) + "x" + std::to_string(q.h));
        out.emplace_back("bg", hex(place.ground));
        out.emplace_back("dark", look);
      } else {
        out.emplace_back("entity", ref);
        out.emplace_back("size", std::to_string(q.w));
        out.emplace_back("bg", hex(place.ground));
      }
      break;
    case Owner::LIBRARY: {
      std::string items;
      for (const auto &s : q.sources) {
        const std::string r = ref_of(s);
        items += (items.empty() ? "" : ",") + r.substr(r.find('/') + 1);
      }
      out.emplace_back("entity", ref.substr(0, ref.find('/')));
      out.emplace_back("lib", items);
      out.emplace_back("atlas", atlas_of(q));
      out.emplace_back("bg", hex(place.ground));
      break;
    }
    default: {
      // A tile's own picture, or a plugin's places: the question of a page of one tile (tile_picture.h).
      const bool plugin = q.owner != Owner::TILE;
      out.emplace_back("tiles", plugin ? q.key : q.of);
      out.emplace_back("idx", std::to_string(std::max(0, q.index)));
      out.emplace_back("size", std::to_string(std::max(CIRCLE_MIN, std::min(CIRCLE_MAX, q.circle))));
      out.emplace_back("bg", hex(place.ground));
      out.emplace_back("dark", look);
      out.emplace_back("atlas", atlas_of(q));
      if (plugin) {
        std::string src = "[", fit = "[", turn = "[", mirror = "[";
        bool styled = false;
        for (size_t i = 0; i < q.places.size(); ++i) {
          const Place &p = q.places[i];
          const std::string &s = i < q.sources.size() ? q.sources[i] : first;
          src += (i ? "," : "") + quoted(s);
          fit += std::string(i ? "," : "") + (p.fit == Fit::WITHIN ? "\"contain\"" : "\"cover\"");
          turn += std::string(i ? "," : "") + (p.turn == 1 ? "\"left\"" : p.turn == 2 ? "\"right\"" : "\"\"");
          mirror += std::string(i ? "," : "") + (p.mirror ? "1" : "0");
          styled = styled || p.turn || p.mirror;
        }
        out.emplace_back("src", src + "]");
        out.emplace_back("fit", fit + "]");
        if (styled) {
          out.emplace_back("turn", turn + "]");
          out.emplace_back("mirror", mirror + "]");
        }
        if (q.owner == Owner::PLUGIN_CARD) { out.emplace_back("card", "1"); out.emplace_back("for", q.of); }
        if (q.owner == Owner::PLUGIN_SAVER) { out.emplace_back("saver", "1"); out.emplace_back("for", q.of); }
      } else {
        stream();
      }
      break;
    }
  }
  return out;
}

// ---- The numbers: one count for every owner, and what each number was asked as ----
// An answer carries its question's number. `kind` and `entity` are how an older app would have answered it (its `t`
// and `e`), `own` the owner's own number of it, so the answer goes where that answer always went.
struct Asked {
  uint32_t number = 0;
  std::string kind, entity;
  uint32_t own = 0;
};
class Numbers {
 public:
  uint32_t ask(const std::string &kind, const std::string &entity, uint32_t own) {
    const uint32_t n = ++count_;
    if (asked_.size() == KEPT) asked_.erase(asked_.begin());
    asked_.push_back({n, kind, entity, own});
    return n;
  }
  const Asked *find(uint32_t number) const {
    for (const auto &a : asked_) if (a.number == number) return &a;
    return nullptr;
  }
  void clear() { asked_.clear(); }
  static constexpr size_t KEPT = 64;

 private:
  uint32_t count_ = 0;
  std::vector<Asked> asked_;
};
}  // namespace picture_question
