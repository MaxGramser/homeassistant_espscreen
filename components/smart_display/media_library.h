#pragma once
// A media player's library (firmware 0.24.0+, app 0.4.42+): its folders, a page of covers, and a tap that plays.
//
// Reached from the player's card: the round key at the top right, or the Library key a player at rest shows instead of
// its keys. The first level is what Home Assistant calls the player's media library (Spotify: Playlists, Artists,
// Albums, Liked songs, ...), drawn as cards with the icon of what each folder holds; a folder of things with pictures
// is a grid of covers with the title under each, two lines at most. A tap on something that plays plays it at once,
// on the speaker the player plays on (or, when it plays nowhere, the one chosen in the speaker menu that opens then);
// a folder that only opens, opens. Holding something that does both (an artist, a playlist) opens it instead.
//
// Nothing here knows a brand. The folders, their titles, their classes and their pictures are Home Assistant's,
// through ESP Screen Manager (screen_manager/app/media_library.py): the screen asks for a folder by a number and gets
// its items with numbers of their own; the app keeps what each number stands for and plays it when asked. A folder
// holds at most 48 items, what Home Assistant gives for Spotify, and the pager counts only those.
//
// The covers of a page come as one picture, the way a page's camera tiles do (tile_art): the screen names the frames,
// the app fills them with the thumbnails Home Assistant names and the corners rounded over the page, and every cell
// shows its own part. Nothing waits for it: the page is whole with its placeholders, and the picture comes over them.
//
// Like the effects page, the library is built when it opens and thrown away when it closes, so it costs nothing while
// closed. This header is the part a PC can test (tests/test_media_library.cpp): what a folder holds, how a page is
// laid out, the pager. media_library.cpp draws it, in a file of its own: main.cpp is near the reach of the S3's
// literal pool (page_receiver.cpp says why).
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include "picture_loader.h"

namespace media_library {

constexpr unsigned LIMIT = 48;   // items a folder shows at most
// What an item can do, as the app sends it.
constexpr uint8_t CAN_PLAY = 1, CAN_EXPAND = 2, PICTURED = 4, PLAYING = 8;
constexpr uint32_t ASK_AGAIN_MS = 6000;     // a page that does not come is asked for again, this often
constexpr uint8_t ASK_TRIES = 3;            // and then the library says it did not answer
constexpr uint32_t STARTING_MS = 12000;     // a tapped item is marked as starting this long, or until the player plays

struct Item {
  uint32_t token = 0;
  std::string title;
  uint8_t flags = 0;
  uint32_t icon = 0;  // a codepoint, 0 for the library's own
};
// One message of the app: a page of a folder's items.
struct Answer {
  std::string entity, title;
  uint32_t folder = 0;
  unsigned page = 0, pages = 1, count = 0;
  bool failed = false;
  std::vector<Item> items;
};

enum class Tap : uint8_t { play, open, none };
// What a tap on an item does: what plays, plays; a folder opens. A hold opens what opens.
inline Tap tap_of(uint8_t flags, bool held = false) {
  if (held && (flags & CAN_EXPAND)) return Tap::open;
  if (flags & CAN_PLAY) return Tap::play;
  if (flags & CAN_EXPAND) return Tap::open;
  return Tap::none;
}

// A folder as it comes in, page by page.
struct Folder {
  uint32_t token = 0;   // 0: the top of the library
  std::string title;
  std::vector<Item> items;
  unsigned next = 0, pages = 0;
  bool complete = false, failed = false;
  // Takes one page of the app's answer; whether it was the one this folder waited for.
  bool take(Answer &&answer) {
    if (complete || answer.folder != token || answer.page != next) return false;
    if (answer.failed) { failed = complete = true; return true; }
    if (next == 0) title = answer.title;
    for (auto &item : answer.items) { if (items.size() >= LIMIT) break; items.push_back(std::move(item)); }
    pages = std::max(1u, answer.pages);
    next = answer.page + 1;
    complete = next >= pages || items.size() >= LIMIT;
    return true;
  }
  bool pictured() const {
    return std::any_of(items.begin(), items.end(), [](const Item &i) { return (i.flags & PICTURED) != 0; });
  }
};

// ---- the page ----
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
};
// What the glass and the look bring: the page's width and height, its edge, where the content starts under the top
// bar, the gaps, the line height of a cover's title, the pager's row and the least a folder's card may be.
struct Shape {
  int width = 480, height = 480, pad = 20, top = 88, gap = 12, line_h = 22, pager_h = 44, card_h = 64;
  int min_art = 48;  // the smallest a cover may get for a second row: a finger's width and a little
  // The ring that marks what plays lies round a cover, inside its cell: LVGL draws a cell's parts again only within
  // the cell, so a ring past its edge lost its top whenever it was drawn anew (the first row, under the top bar).
  int ring = 5;
};
struct Grid {
  bool covers = false;  // squares with a picture and the title under each; else cards with an icon and the name
  int columns = 1, rows = 1, per_page = 1;
  int x = 0, y = 0, cell_w = 0, cell_h = 0, art = 0;  // the first cell, a cell's size and a cover's side
  bool pager = false;
  int pager_y = 0;
  // The n-th cell of a page, row by row.
  Rect cell(int n) const {
    const int c = n % columns, r = n / columns;
    return {x + c * (cell_w + gap), y + r * (cell_h + gap), cell_w, cell_h};
  }
  // Where a cell's cover goes: its side, centred over the title, the ring's room above it.
  Rect cover(int n) const {
    const Rect c = cell(n);
    return {c.x + (c.w - art) / 2, c.y + ring, art, art};
  }
  int gap = 0, ring = 0;
};
// A wide glass (three units of width to two of height, the rule the effects page and the cards keep) takes five
// covers a row, a very wide one (1200 pixels and more) six; a square or a standing one three.
inline bool wide(int width, int height) { return width * 2 > height * 3; }
inline int cover_columns(int width, int height) { return wide(width, height) ? (width >= 1200 ? 6 : 5) : 3; }
inline int card_columns(int width, int height) { return wide(width, height) ? 4 : 2; }

// The grid of a page with `count` items in all; the pager only takes its row when they need more than one page.
inline Grid place(const Shape &s, bool covers, size_t count) {
  Grid g;
  g.covers = covers;
  g.gap = s.gap;
  g.ring = covers ? s.ring : 0;
  const int inner = std::max(1, s.width - 2 * s.pad);
  auto lay = [&](bool pager) {
    const int room = std::max(1, s.height - s.top - s.pad - (pager ? s.pager_h + s.gap / 2 : 0));
    if (covers) {
      g.columns = cover_columns(s.width, s.height);
      g.cell_w = std::max(1, (inner - (g.columns - 1) * s.gap) / g.columns);
      const int text_h = s.gap / 2 + 2 * s.line_h + 2 * g.ring;
      // As many rows as the covers fill at about their width, and two where a cover stays a finger wide: a wide glass
      // is short, and one row of five is a fifth of a library a page. The cover then shrinks to what the rows leave it.
      const int art_of = [&](int rows) { return (room - (rows - 1) * s.gap) / rows - text_h; }(2);
      g.rows = std::max(1, (2 * (room + s.gap) + (g.cell_w + text_h + s.gap)) / (2 * (g.cell_w + text_h + s.gap)));
      if (g.rows < 2 && art_of >= s.min_art) g.rows = 2;
      g.art = std::max(1, std::min(g.cell_w - 2 * g.ring, (room - (g.rows - 1) * s.gap) / g.rows - text_h));
      g.cell_h = g.art + text_h;
    } else {
      g.columns = card_columns(s.width, s.height);
      g.cell_w = std::max(1, (inner - (g.columns - 1) * s.gap) / g.columns);
      g.rows = std::max(1, (room + s.gap) / (s.card_h + s.gap));
      // The cards share the room, but never grow past half again their own height: a page of three folders on a
      // ten-inch panel keeps cards, not slabs.
      g.cell_h = std::min(s.card_h * 3 / 2, std::max(s.card_h, (room - (g.rows - 1) * s.gap) / g.rows));
      g.art = 0;
    }
    g.per_page = g.columns * g.rows;
    const int used_w = g.columns * g.cell_w + (g.columns - 1) * s.gap, used_h = g.rows * g.cell_h + (g.rows - 1) * s.gap;
    g.x = (s.width - used_w) / 2;
    g.y = s.top + std::max(0, (room - used_h) / 2);
    g.pager = pager;
    g.pager_y = s.height - s.pad - s.pager_h;
  };
  lay(false);
  if (std::min<size_t>(count, LIMIT) > static_cast<size_t>(g.per_page)) lay(true);
  return g;
}
inline unsigned page_count(size_t count, int per_page) {
  const size_t n = std::min<size_t>(count, LIMIT);
  return per_page <= 0 || n == 0 ? 1 : static_cast<unsigned>((n + per_page - 1) / per_page);
}
// The items of page `page`: [first, end).
inline size_t first_of(unsigned page, int per_page) { return static_cast<size_t>(page) * std::max(1, per_page); }
inline size_t end_of(unsigned page, int per_page, size_t count) {
  return std::min({first_of(page, per_page) + std::max(1, per_page), count, static_cast<size_t>(LIMIT)});
}
// The pager: the dots every page bar has up to eight pages, "3 / 12" past that.
inline bool dots(unsigned pages) { return pages <= 8; }
inline std::string page_text(unsigned page, unsigned pages) {
  char b[16];
  snprintf(b, sizeof(b), "%u / %u", page + 1, pages);
  return b;
}

// ---- the speaker menu ----
// A panel of rows under the pill in the player's top bar, one per speaker (or input); more than the glass holds page,
// the last row then the pager.
// A speaker's flags from the app (firmware 0.26.0+, speakers.py): it plays here (in the group), and it may join or
// leave the group with a key of its own.
constexpr uint8_t SPEAKER_ON = 1, SPEAKER_GROUPS = 2;
// The first row of every page of a menu whose rows each have their height (a speaker in the group is taller for its
// volume), in `room` pixels: when they do not all fit, every page keeps `pager_h` for the pager. A page holds one row
// at least, however tall.
inline std::vector<size_t> page_starts(const std::vector<int> &heights, int room, int pager_h) {
  std::vector<size_t> starts{0};
  int total = 0;
  for (int h : heights) total += h;
  if (total <= room) return starts;
  const int fit = room - pager_h;
  int used = 0;
  for (size_t i = 0; i < heights.size(); ++i) {
    if (used > 0 && used + heights[i] > fit) { starts.push_back(i); used = 0; }
    used += heights[i];
  }
  return starts;
}

// ---- what the rest of the firmware sees (media_library.cpp) ----
// The library page is built on a board with PSRAM (every board that draws pictures): a board without it, such as the
// CYD, has its flash nearly full and keeps the player, its speakers and the favourites, without the library. The host
// renders and the editor's preview build it too.
#if defined(USE_PSRAM) || !defined(USE_ESP32)
constexpr bool LIBRARY = true;
#else
constexpr bool LIBRARY = false;
#endif
inline bool available() { return LIBRARY; }
void open(const std::string &entity);
void close();
bool visible();
// The speaker menu over the player's card, over the library or over a page; `then` is an item of the library and
// `tile` a favourite's tile that plays once a speaker is chosen.
void speakers(const std::string &entity, uint32_t then = 0, int tile = -1);
// The inputs of a player (firmware 0.26.0+): Home Assistant's source_list where its sources are inputs.
void inputs(const std::string &entity);
bool menu_visible();
void received(Answer &&answer);
// The covers of the page: what the library wants this round (runtime_tiles::pictures_round), the app's link for them,
// and a download they were drawn from that goes (a board without the store).
bool picture_want(picture_loader::Want &want);
void art_answer(const std::string &entity, const std::string &url);
void art_forget_download();
// A state of the player while the library or the menu is open.
void updated(const std::string &entity);
void restyle();
void tick(uint32_t now);
// Whether one of the library's pictures is this image (the store keeps what a page draws).
bool draws(const void *image);
// What is on the glass, for the render harness (tools/render): what is open, the folder, the page, and the centre of
// everything a finger uses.
std::string describe();
}  // namespace media_library
