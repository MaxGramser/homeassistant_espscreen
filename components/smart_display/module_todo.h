#pragma once
// The to-do card (module todo, docs/TODO.md): a Home Assistant to-do list as a tile that shows more as it gets more
// room, a full screen with the whole list, and the keyboard that adds an item to it.
//
// What it knows: the list as the app sends it (`x.todo`, screen_manager/app/todo_feed.py: the items in the tile's
// order, each with a number the app keeps for it, what the screen may do with the list, and names to offer while
// typing), the room it gets, and the board's faces. It plans rectangles, texts and the places a finger may hit, as
// the calendar card does (calendar_card.h Scene), and it keeps what is typed (Entry).
// What it does not know: LVGL, Home Assistant, the app. module_todo.cpp paints a plan, hears the finger and sends
// what it asks for.
//
// Pure: tests/test_todo.cpp checks it on a PC.
#include "calendar_card.h"
#include "roomy.h"
#include "ui_scale.h"

#include <algorithm>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace todo {
namespace cc = calendar_card;

// ---- The list, as the app sends it.
constexpr size_t MAX_ITEMS = 40;     // the hello says so (`todo_items`), and the app sends no more
constexpr size_t MAX_OFFERS = 12;
constexpr size_t SUMMARY_BYTES = 67;  // the app cuts a name to 64 bytes, with an ellipsis
constexpr size_t TEXT_BYTES = 120;    // what the field holds
// What the screen may do with the list (`f`): the list's features in Home Assistant and the tile's choices.
enum : uint8_t { MAY_ADD = 1, MAY_TICK = 2, MAY_REMOVE = 4, MAY_CLEAR = 8, MAY_RENAME = 16 };
// An item's flags; HAS_DUE is the screen's own (the app sends the days or leaves them out).
enum : uint8_t { DONE = 1, LATE = 2, HAS_DUE = 128 };
struct Item {
  uint32_t id = 0;
  uint8_t flags = 0;
  int16_t days = 0;  // its due day, counted from today
  roomy::Text text;
};
struct Data {
  bool waiting = false;         // the app has no list from Home Assistant yet
  uint8_t may = 0;
  uint16_t open = 0, done = 0;  // of the whole list, also what was not sent
  roomy::List<Item> items;      // open first, then done
  roomy::List<roomy::Text> offers;
};
// What a finger ticked and Home Assistant has not confirmed yet: the item's number and what it should be.
using Marks = std::vector<std::pair<uint32_t, bool>>;
inline bool is_done(const Item &it, const Marks &marks) {
  for (const auto &m : marks) if (m.first == it.id) return m.second;
  return it.flags & DONE;
}

// ---- The words, in the screen's language (module_todo.cpp fills them from screen_text.h).
struct Words {
  std::string open = "{x} open", all_done = "All done", more = "+{x} more", completed = "Completed", add = "Add item",
              added = "{x} added", rename = "Rename", remove = "Remove", cancel = "Cancel", clear = "Remove {x} completed?",
              waiting = "Loading", empty = "Nothing on the list";
  std::function<std::string(int)> day;  // a due day by its distance from today: "Today", "Friday", "12 Nov"
};
inline std::string fill(const std::string &pattern, const std::string &value) {
  const size_t at = pattern.find("{x}");
  return at == std::string::npos ? pattern : pattern.substr(0, at) + value + pattern.substr(at + 3);
}
inline std::string count_words(const Data &d, const Marks &marks, const Words &w) {
  if (d.waiting) return w.waiting;
  int open = d.open;
  // What a finger ticked counts at once, before the list comes back.
  for (const auto &it : d.items) open += (is_done(it, marks) ? 0 : 1) - ((it.flags & DONE) ? 0 : 1);
  if (open <= 0) return d.done || !d.items.empty() ? w.all_done : w.empty;
  return fill(w.open, std::to_string(open));
}

// ---- Places a finger may hit. They live in calendar_card's Hit, whose own kinds end far below these.
constexpr cc::HitKind H_ROW = cc::HitKind(64), H_ADD = cc::HitKind(65), H_CLOSE = cc::HitKind(66), H_FIELD = cc::HitKind(67),
    H_CLEAR = cc::HitKind(68), H_KEY = cc::HitKind(69), H_OFFER = cc::HitKind(70), H_SEND = cc::HitKind(71),
    H_HIDE = cc::HitKind(72), H_PANEL = cc::HitKind(73), H_SCRIM = cc::HitKind(74), H_RENAME = cc::HitKind(75),
    H_REMOVE = cc::HitKind(76), H_YES = cc::HitKind(77), H_NO = cc::HitKind(78);
// The list's own colours, as places in the painter's colour list (module_todo.cpp): the list's colour, the pale
// circle behind its icon, the icon in it, late, and a key that is no letter.
enum : uint8_t { C_LIST, C_TINT, C_ICON, C_LATE, C_SPECIAL, COLOURS };
inline cc::Paint own(uint8_t c) { return cc::cal(cc::CAL_KEY, c); }

// Icons the screens' fonts already carry (screen_manager/app/tile_icons.py): the list, plus, check, close, the arrows
// that stand for backspace and shift, and the bin.
constexpr const char *I_LIST = "\U000F10D4", *I_PLUS = "\U000F0415", *I_CHECK = "\U000F012C", *I_CLOSE = "\U000F0156",
    *I_BACK = "\U000F004D", *I_SHIFT = "\U000F005D", *I_BIN = "\U000F0A79";

using cc::L;
inline void box(cc::Scene &s, int x, int y, int w, int h, int radius, cc::Paint p, uint8_t opa = 255) {
  cc::Box b; b.x = x; b.y = y; b.w = w; b.h = h; b.radius = radius; b.paint = p; b.opa = opa; s.boxes.push_back(b);
}
inline void ring(cc::Scene &s, int x, int y, int d, int width, cc::Paint p) {
  cc::Box b; b.x = x; b.y = y; b.w = d; b.h = d; b.radius = d / 2; b.opa = 0; b.border = width; b.line = p; s.boxes.push_back(b);
}
inline void words(cc::Scene &s, const cc::Measure &m, int x, int y, int w, cc::Face f, cc::Paint p, const std::string &text,
                  cc::Align align = cc::LEFT) {
  if (w <= 0) return;
  cc::Text t; t.x = x; t.y = y; t.w = w; t.face = f; t.paint = p; t.align = align; t.s = cc::fit(m, f, text, w); s.texts.push_back(std::move(t));
}
// A glyph centred in a box.
inline void glyph(cc::Scene &s, const cc::Measure &m, int x, int y, int w, int h, cc::Face f, cc::Paint p, const char *g) {
  cc::Text t; t.x = x; t.y = y + (h - L(m, f)) / 2; t.w = w; t.face = f; t.paint = p; t.align = cc::CENTRE; t.s = g; s.texts.push_back(std::move(t));
}
inline void hit(cc::Scene &s, int x, int y, int w, int h, cc::HitKind kind, int arg = 0) {
  cc::Hit a; a.x = x; a.y = y; a.w = w; a.h = h; a.kind = kind; a.arg = arg; s.hits.push_back(a);
}
inline void round_key(cc::Scene &s, const cc::Measure &m, int x, int y, int d, const char *g, cc::HitKind kind, int arg = 0,
                      cc::Paint ground = {cc::TRACK}, cc::Paint ink = {cc::INK}) {
  box(s, x, y, d, d, d / 2, ground);
  glyph(s, m, x, y, d, d, cc::ICON, ink, g);
  hit(s, x, y, d, d, kind, arg);
}
// The round box of a row: as wide as the small icon needs to stand in it.
inline int tick_size(const cc::Measure &m) { return std::max(ui::px(26), L(m, cc::ICON) + ui::px(2)); }

// One item: a round box to tick, its name, and its due day where the whole name still fits beside it.
inline void row(cc::Scene &s, const cc::Measure &m, int x, int y, int w, int rowh, cc::Face face, const Item &it, bool done,
                bool due, const Words &wd) {
  const int d = tick_size(m), cy = y + (rowh - d) / 2;
  if (done) {
    box(s, x, cy, d, d, d / 2, own(C_LIST));
    glyph(s, m, x, cy, d, d, cc::ICON, {cc::ON_NOW}, I_CHECK);
  } else {
    ring(s, x, cy, d, std::max(2, ui::px(2)), (it.flags & LATE) ? own(C_LATE) : cc::Paint{cc::SUBTLE});
  }
  const std::string name = roomy::plain(it.text);
  int tx = x + d + ui::px(12), tw = w - d - ui::px(12);
  if (due && !done && (it.flags & HAS_DUE) && wd.day) {
    const std::string day = wd.day(it.days);
    const int dw = m.width(cc::SMALL, day);
    if (!day.empty() && tw - dw - ui::px(12) >= m.width(face, name)) {
      words(s, m, x + w - dw, y + (rowh - L(m, cc::SMALL)) / 2, dw, cc::SMALL, (it.flags & LATE) ? own(C_LATE) : cc::Paint{cc::MUTED}, day);
      tw -= dw + ui::px(12);
    }
  }
  const int ty = y + (rowh - L(m, face)) / 2;
  words(s, m, tx, ty, tw, face, {done ? cc::SUBTLE : cc::INK}, name);
  if (done) {
    // Struck through: a line across the words, as wide as they are.
    const int lw = std::min(tw, m.width(face, cc::fit(m, face, name, tw)));
    box(s, tx, ty + L(m, face) / 2, lw, std::max(1, ui::px(1)), 0, {cc::SUBTLE});
  }
}

// The rows a room holds: what is open first, a line that counts what does not fit where four rows or more stand, then
// what is done. A second column comes only when the first cannot hold what is open.
inline void rows(cc::Scene &s, const cc::Measure &m, int x, int y, int w, int h, cc::Face face, int rowh, bool columns,
                 const Data &d, const Marks &marks, const Words &wd, bool may_hit, bool due = true, bool count = true) {
  const int cap = std::max(1, h / rowh);
  int open_sent = 0;
  for (const auto &it : d.items) open_sent += !(it.flags & DONE);
  const int cols = columns && open_sent > cap ? 2 : 1;
  const int gap = ui::px(20), total = cap * cols, colw = (w - (cols - 1) * gap) / cols;
  const bool more = count && cap >= 4 && d.open > total;
  const int keep = more ? total - 1 : total;
  int n = 0, shown_open = 0;
  for (size_t i = 0; i < d.items.size() && n < keep; ++i) {
    const Item &it = d.items[i];
    // What is done comes only into room that what is open leaves.
    if ((it.flags & DONE) && d.open > shown_open) break;
    const int rx = x + (n / cap) * (colw + gap), ry = y + (n % cap) * rowh;
    row(s, m, rx, ry, colw, rowh, face, it, is_done(it, marks), due, wd);
    if (may_hit) hit(s, rx - ui::px(8), ry, colw + ui::px(16), rowh, H_ROW, int(i));
    shown_open += !(it.flags & DONE);
    ++n;
  }
  if (more && d.open > shown_open) {
    const int rx = x + (n / cap) * (colw + gap), ry = y + (n % cap) * rowh, indent = tick_size(m) + ui::px(12);
    words(s, m, rx + indent, ry + (rowh - L(m, cc::SMALL)) / 2, colw - indent, cc::SMALL, {cc::MUTED},
          fill(wd.more, std::to_string(d.open - shown_open)));
  }
}

inline void icon_circle(cc::Scene &s, const cc::Measure &m, int x, int y, int d, cc::Face face, const std::string &icon) {
  box(s, x, y, d, d, d / 2, own(C_TINT));
  glyph(s, m, x, y, d, d, face, own(C_ICON), icon.empty() ? I_LIST : icon.c_str());
}

// ---- The tile. Its view follows the room it gets (`w` x `h`, the card's content): a count in one cell, the first
// items beside the name on a wide cell (as rows to tick where two fit a finger, else as a line of names), and a list
// with a key to add an item as soon as the name and two rows fit.
enum class View : uint8_t { count, wide, list };
inline int list_row(const cc::Measure &m, cc::Face face) { return std::max(ui::touch_min(), L(m, face) + ui::px(14)); }
inline View view_of(const cc::Measure &m, int w, int h) {
  const cc::Face face = w >= ui::px(250) ? cc::CONTROL : cc::SMALL;
  const int head = std::max(ui::px(44), ui::touch_min());
  if (h - head - ui::px(6) >= 2 * list_row(m, face)) return View::list;
  // A cell's own padding belongs to the finger too, so two rows may be a little lower than a finger's 7 mm.
  if (w >= ui::mm(52) && (h + ui::px(16)) / 2 >= ui::touch_min()) return View::wide;
  return View::count;
}
inline void plan_tile(cc::Scene &s, const cc::Measure &m, int w, int h, const std::string &name, const Data &d, const Marks &marks,
                      const Words &wd, const std::string &icon = "") {
  s.clear();
  if (w <= 0 || h <= 0) return;
  const std::string count = count_words(d, marks, wd);
  const bool tick = d.may & MAY_TICK;
  const View view = view_of(m, w, h);
  const int two = L(m, cc::LABEL) + L(m, cc::SMALL);
  if (view == View::list) {
    const cc::Face face = w >= ui::px(250) ? cc::CONTROL : cc::SMALL;
    const int key = ui::touch_min(), small = ui::px(44), head = std::max(small, key);
    const bool add = (d.may & MAY_ADD) && w >= small + key + ui::px(110);
    icon_circle(s, m, 0, (head - small) / 2, small, cc::ICON, icon);
    const int tx = small + ui::px(12), tw = w - tx - (add ? key + ui::px(8) : 0);
    words(s, m, tx, (head - two) / 2, tw, cc::LABEL, {cc::INK}, name);
    words(s, m, tx, (head - two) / 2 + L(m, cc::LABEL), tw, cc::SMALL, {cc::MUTED}, count);
    if (add) round_key(s, m, w - key, (head - key) / 2, key, I_PLUS, H_ADD);
    const int y = head + ui::px(6);
    rows(s, m, 0, y, w, h - y, face, list_row(m, face), w >= ui::mm(105), d, marks, wd, tick);
    return;
  }
  const int big = m.circle;
  icon_circle(s, m, 0, (h - big) / 2, big, cc::TILE_ICON, icon);
  const int tx = big + ui::px(14);
  if (view == View::wide && !d.waiting && !d.items.empty()) {
    const int left = std::min(w * 46 / 100, ui::px(230)), tw = left - tx;
    words(s, m, tx, (h - two) / 2, tw, cc::LABEL, {cc::INK}, name);
    words(s, m, tx, (h - two) / 2 + L(m, cc::LABEL), tw, cc::SMALL, {cc::MUTED}, count);
    const int rh = (h + ui::px(12)) / 2;
    rows(s, m, left + ui::px(14), -ui::px(6), w - left - ui::px(14), 2 * rh, cc::SMALL, rh, false, d, marks, wd, tick, false, false);
    return;
  }
  std::string second = count;
  if (w >= ui::mm(52) && !d.waiting) {
    // Room beside the count: the names of what comes first.
    int n = 0;
    for (const auto &it : d.items)
      if (!is_done(it, marks) && n < 5) { second += n++ ? ", " : "  ·  "; second += roomy::plain(it.text); }
  }
  words(s, m, tx, (h - two) / 2, w - tx, cc::LABEL, {cc::INK}, name);
  words(s, m, tx, (h - two) / 2 + L(m, cc::LABEL), w - tx, cc::SMALL, {cc::MUTED}, second);
}

// ---- The keyboard. One layout, QWERTY, with a page of digits and one of signs; a long press on a letter shows its
// accents above it. Every character is one the screens' fonts have (packages/core.yaml `label`).
enum : int { K_SHIFT = -1, K_BACK = -2, K_PAGE = -3, K_SPACE = -4, K_ENTER = -5, K_SIGNS = -6 };
constexpr int ACCENT = 1000;  // a key of the accent strip: ACCENT + its place
struct Entry {
  std::string text;
  uint8_t page = 0;   // 0 letters, 1 digits, 2 signs
  bool shift = true;  // the next letter is a capital
  int accents = -1;   // the letter key whose accents show, or none
};
inline const char *const *page_keys(uint8_t page, bool shift) {
  static const char *const LOWER[26] = {"q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "a", "s", "d", "f", "g", "h", "j", "k", "l",
                                        "z", "x", "c", "v", "b", "n", "m"};
  static const char *const UPPER[26] = {"Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "A", "S", "D", "F", "G", "H", "J", "K", "L",
                                        "Z", "X", "C", "V", "B", "N", "M"};
  static const char *const DIGITS[26] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "/", ":", ";", "(", ")", "€", "&", "@",
                                         ".", ",", "?", "!", "'", "\"", "+"};
  static const char *const SIGNS[26] = {"[", "]", "{", "}", "#", "%", "^", "*", "=", "_", "\\", "|", "~", "<", ">", "$", "£", "¥", "·",
                                        ".", ",", "?", "!", "'", "°", "…"};
  return page == 1 ? DIGITS : page == 2 ? SIGNS : shift ? UPPER : LOWER;
}
// The accents of a letter key, at most six; none for a key that has none.
inline std::vector<const char *> accents_of(int key, bool shift) {
  struct Row { char base; const char *lower[6]; const char *upper[6]; };
  static const Row ROWS[] = {
      {'a', {"á", "à", "â", "ä", "ã", "å"}, {"Á", "À", "Â", "Ä", "Ã", "Å"}},
      {'e', {"é", "è", "ê", "ë", "ę", nullptr}, {"É", "È", "Ê", "Ë", "Ę", nullptr}},
      {'i', {"í", "ì", "î", "ï", nullptr, nullptr}, {"Í", "Ì", "Î", "Ï", nullptr, nullptr}},
      {'o', {"ó", "ò", "ô", "ö", "õ", "ø"}, {"Ó", "Ò", "Ô", "Ö", "Õ", "Ø"}},
      {'u', {"ú", "ù", "û", "ü", nullptr, nullptr}, {"Ú", "Ù", "Û", "Ü", nullptr, nullptr}},
      {'c', {"ç", "ć", "č", nullptr, nullptr, nullptr}, {"Ç", "Ć", "Č", nullptr, nullptr, nullptr}},
      {'n', {"ñ", "ń", nullptr, nullptr, nullptr, nullptr}, {"Ñ", "Ń", nullptr, nullptr, nullptr, nullptr}},
      {'s', {"ß", "ś", "š", nullptr, nullptr, nullptr}, {"Ś", "Š", nullptr, nullptr, nullptr, nullptr}},
      {'y', {"ý", "ÿ", nullptr, nullptr, nullptr, nullptr}, {"Ý", "Ÿ", nullptr, nullptr, nullptr, nullptr}},
      {'z', {"ž", "ź", "ż", nullptr, nullptr, nullptr}, {"Ž", "Ź", "Ż", nullptr, nullptr, nullptr}},
      {'l', {"ł", nullptr, nullptr, nullptr, nullptr, nullptr}, {"Ł", nullptr, nullptr, nullptr, nullptr, nullptr}},
  };
  std::vector<const char *> out;
  if (key < 0 || key >= 26) return out;
  const char base = page_keys(0, false)[key][0];
  for (const auto &r : ROWS)
    if (r.base == base)
      for (const char *a : shift ? r.upper : r.lower) if (a) out.push_back(a);
  return out;
}
inline void erase_last(std::string &text) {
  if (text.empty()) return;
  size_t at = text.size() - 1;
  while (at > 0 && (static_cast<unsigned char>(text[at]) & 0xC0) == 0x80) --at;
  text.erase(at);
}
inline void type(Entry &e, const char *s) {
  const std::string add = s ? s : "";
  if (add.empty() || e.text.size() + add.size() > TEXT_BYTES) return;
  if (add == " " && (e.text.empty() || e.text.back() == ' ')) return;
  e.text += add;
  e.shift = false;
}
// A key of the keyboard: a place on the page (0..25), a key of the accent strip (ACCENT + place), or one of K_*.
// K_ENTER is the caller's: it sends what the field holds.
inline void press(Entry &e, int key) {
  if (key >= ACCENT) {
    const auto strip = accents_of(e.accents, e.shift);
    if (size_t(key - ACCENT) < strip.size()) type(e, strip[key - ACCENT]);
    e.accents = -1;
    return;
  }
  e.accents = -1;
  if (key >= 0 && key < 26) { type(e, page_keys(e.page, e.shift)[key]); return; }
  if (key == K_SHIFT) e.shift = !e.shift;
  else if (key == K_BACK) { erase_last(e.text); if (e.text.empty() && e.page == 0) e.shift = true; }
  else if (key == K_PAGE) { e.page = e.page ? 0 : 1; }
  else if (key == K_SIGNS) { e.page = e.page == 2 ? 1 : 2; }
  else if (key == K_SPACE) type(e, " ");
}
// A long press on a letter that has accents shows them; anything else is the key itself.
inline bool hold(Entry &e, int key) {
  if (e.page != 0 || accents_of(key, e.shift).empty()) return false;
  e.accents = key;
  return true;
}
inline void reset(Entry &e, const std::string &text = "") {
  e = Entry();
  e.text = text;
  e.shift = text.empty();
}
// What the field holds, ready to send: no space at either end.
inline std::string typed(const Entry &e) {
  size_t a = 0, b = e.text.size();
  while (a < b && e.text[a] == ' ') ++a;
  while (b > a && e.text[b - 1] == ' ') --b;
  return e.text.substr(a, b - a);
}

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline bool starts(const roomy::Text &name, const std::string &with) {
  if (with.size() > name.size()) return false;
  for (size_t i = 0; i < with.size(); ++i) if (lower(name[i]) != lower(with[i])) return false;
  return true;
}
// The names to offer for what is typed: what was done before and begins so, the last done first.
inline std::vector<std::string> offers(const Data &d, const std::string &text) {
  std::vector<std::string> out;
  if (!(d.may & MAY_ADD)) return out;
  for (const auto &name : d.offers)
    if (starts(name, text) && !roomy::same(name, text)) out.push_back(roomy::plain(name));
  return out;
}

// The keyboard's sheet at the bottom of a glass of `W` x `H`, never above `top`: the field with the key that sends
// it, the names offered, and four rows of keys. Never wider than two hands need; a key never taller than 9 mm. On
// glass too short for keys a finger can hit below `top` it takes the whole glass (`whole`), with a key that puts it
// away. Returns where the sheet begins.
struct Keyboard { int top = 0; bool whole = false; };
inline Keyboard plan_keyboard(cc::Scene &s, const cc::Measure &m, int W, int H, int top, const Entry &e,
                              const std::vector<std::string> &offered, const std::string &hint, bool offers_row = false) {
  Keyboard out;
  const int sp = ui::px(10), g = std::max(3, ui::px(6)), field = ui::touch_min(), margin = ui::px(16);
  int kw = std::min(W, ui::mm(165));
  if (W - kw < ui::mm(24)) kw = W;
  const bool floats = kw < W;
  const int least = 2 * sp + field + 5 * g + 4 * ui::mm(7);
  out.whole = H - top - (floats ? margin : 0) < least;
  if (out.whole) top = 0;
  const int room = H - top - (floats && !out.whole ? margin : 0);
  // The row of offered names keeps its room while the list has any to offer, also when none begins with what is
  // typed: the keys never move under a finger that is typing.
  int chips = ui::mm(6) + g;
  if ((offered.empty() && !offers_row) || (room - 2 * sp - field - chips - 5 * g) / 4 < ui::mm(13) / 2) chips = 0;
  const int keyh = std::max(ui::px(20), std::min(ui::mm(9), (room - 2 * sp - field - chips - 5 * g) / 4));
  const int sh = out.whole ? H : 2 * sp + field + chips + 5 * g + 4 * keyh;
  const int sx = (W - kw) / 2, sy = out.whole ? 0 : H - sh - (floats ? margin : 0);
  out.top = sy;
  if (out.whole) box(s, 0, 0, W, H, 0, {cc::CARD});
  else {
    cc::Box b; b.x = sx; b.y = sy; b.w = kw; b.h = sh; b.radius = floats ? ui::px(20) : 0; b.paint = {cc::CARD};
    b.border = 1; b.line = {cc::GRID};
    s.boxes.push_back(b);
  }
  hit(s, out.whole ? 0 : sx, sy, out.whole ? W : kw, sh, H_PANEL);
  const int inner = kw - 2 * sp, x0 = sx + sp;
  // The field, the key that puts the keyboard away where it covers the page's own, and the key that sends.
  const int fx = out.whole ? field + g : 0;
  if (out.whole) round_key(s, m, x0, sy + sp, field, I_CLOSE, H_HIDE);
  const int fw = inner - field - g - fx;
  box(s, x0 + fx, sy + sp, fw, field, field / 2, {cc::TRACK});
  const int ty = sy + sp + (field - L(m, cc::CONTROL)) / 2, pad = ui::px(16);
  if (e.text.empty()) words(s, m, x0 + fx + pad + ui::px(6), ty, fw - 2 * pad, cc::CONTROL, {cc::SUBTLE}, hint);
  // The end of what is typed stays in view: a long text shows its tail.
  std::string shown = e.text;
  while (!shown.empty() && m.width(cc::CONTROL, shown) > fw - 2 * pad - ui::px(4)) shown.erase(0, 1 + (static_cast<unsigned char>(shown[0]) >= 0xC0 ? (static_cast<unsigned char>(shown[0]) >= 0xE0 ? 2 : 1) : 0));
  if (!shown.empty()) { cc::Text t; t.x = x0 + fx + pad; t.y = ty; t.w = fw - 2 * pad; t.face = cc::CONTROL; t.paint = {cc::INK}; t.s = shown; s.texts.push_back(std::move(t)); }
  box(s, x0 + fx + pad + (shown.empty() ? 0 : m.width(cc::CONTROL, shown)) + ui::px(2), ty, std::max(2, ui::px(2)), L(m, cc::CONTROL), 1, {cc::ACCENT});
  round_key(s, m, x0 + inner - field, sy + sp, field, I_PLUS, H_SEND, 0, {cc::ACCENT}, {cc::ON_NOW});
  if (chips) {
    int x = x0;
    const int h = chips - g, y = sy + sp + field + g;
    for (size_t i = 0; i < offered.size(); ++i) {
      const int w = m.width(cc::SMALL, offered[i]) + 2 * ui::px(14);
      if (x + w > x0 + inner) break;
      cc::Box b; b.x = x; b.y = y; b.w = w; b.h = h; b.radius = h / 2; b.paint = {cc::CARD}; b.border = 1; b.line = {cc::GRID};
      s.boxes.push_back(b);
      words(s, m, x, y + (h - L(m, cc::SMALL)) / 2, w, cc::SMALL, {cc::INK}, offered[i], cc::CENTRE);
      hit(s, x, y - g / 2, w, h + g, H_OFFER, int(i));
      x += w + g;
    }
  }
  // On the whole glass the keys stand at its bottom, where the thumbs are.
  const int kwid = (inner - 9 * g) / 10, radius = ui::px(8);
  const int y0 = out.whole ? std::max(sy + sp + field + chips + g + g / 2, H - sp - 4 * keyh - 3 * g) : sy + sp + field + chips + g + g / 2;
  const cc::Face letter = keyh >= 2 * L(m, cc::HEADLINE) - ui::px(8) && kwid >= ui::mm(11) ? cc::HEADLINE : cc::CONTROL;
  auto key = [&](int x, int y, int w, const char *label, int code, bool icon = false, cc::Paint ground = {cc::TRACK}, cc::Paint ink = {cc::INK}) {
    box(s, x, y, w, keyh, radius, ground);
    if (label && *label) glyph(s, m, x, y, w, keyh, icon ? cc::ICON : letter, ink, label);
    // A key's place reaches into the gaps around it, so no touch falls between two keys.
    hit(s, x - g / 2, y - g / 2, w + g, keyh + g, H_KEY, code);
  };
  const char *const *keys = page_keys(e.page, e.shift);
  const int x2 = x0 + (kwid + g) / 2, side = (3 * kwid + g) / 2, x3 = x0 + side + g + ((inner - 2 * side - 2 * g) - (7 * kwid + 6 * g)) / 2;
  for (int i = 0; i < 10; ++i) key(x0 + i * (kwid + g), y0, kwid, keys[i], i);
  for (int i = 0; i < 9; ++i) key(x2 + i * (kwid + g), y0 + keyh + g, kwid, keys[10 + i], 10 + i);
  const int y3 = y0 + 2 * (keyh + g), y4 = y0 + 3 * (keyh + g), wide = 2 * kwid + g;
  if (e.page == 0) key(x0, y3, side, I_SHIFT, K_SHIFT, true, e.shift ? cc::Paint{cc::ACCENT_TINT} : own(C_SPECIAL));
  else key(x0, y3, side, e.page == 1 ? "#+=" : "123", K_SIGNS, false, own(C_SPECIAL));
  for (int i = 0; i < 7; ++i) key(x3 + i * (kwid + g), y3, kwid, keys[19 + i], 19 + i);
  key(x0 + inner - side, y3, side, I_BACK, K_BACK, true, own(C_SPECIAL));
  key(x0, y4, wide, e.page ? "abc" : "123", K_PAGE, false, own(C_SPECIAL));
  key(x0 + wide + g, y4, inner - 2 * wide - 2 * g, "", K_SPACE);
  key(x0 + inner - wide, y4, wide, I_CHECK, K_ENTER, true, own(C_SPECIAL));
  // A letter's accents, in a strip above it: a tap takes one, a tap beside it puts the strip away.
  const auto strip = accents_of(e.accents, e.shift);
  if (e.page == 0 && !strip.empty()) {
    const int row = e.accents < 10 ? 0 : e.accents < 19 ? 1 : 2, col = e.accents < 10 ? e.accents : e.accents < 19 ? e.accents - 10 : e.accents - 19;
    const int kx = (row == 0 ? x0 : row == 1 ? x2 : x3) + col * (kwid + g), ky = y0 + row * (keyh + g);
    const int n = int(strip.size()), w = n * kwid + 2 * g, h = keyh + 2 * g;
    const int px = std::min(x0 + inner - w, std::max(x0, kx - g)), py = ky - h - g / 2;
    hit(s, sx, sy, kw, sh, H_PANEL);  // a tap beside the strip takes no key under it
    cc::Box b; b.x = px; b.y = py; b.w = w; b.h = h; b.radius = radius + g; b.paint = {cc::RAISED}; b.border = 1; b.line = {cc::RAISED_LINE};
    s.boxes.push_back(b);
    for (int i = 0; i < n; ++i) {
      if (i == 0) box(s, px + g, py + g, kwid, keyh, radius, {cc::ACCENT});
      glyph(s, m, px + g + i * kwid, py + g, kwid, keyh, letter, {i == 0 ? cc::ON_NOW : cc::INK}, strip[i]);
      hit(s, px + g + i * kwid, py, kwid, h, H_KEY, ACCENT + i);
    }
  }
  return out;
}

// ---- The full screen a tap opens: the list whole, a field that opens the keyboard, and what is done under it.
struct Full {
  bool keys = false;      // the keyboard is up
  Entry entry;
  int sheet = -1;         // the item whose sheet is open (a long press), by its place in the list
  uint32_t renaming = 0;  // the keyboard changes this item's name instead of adding one
  bool confirm = false;   // "Remove N completed?" is asked
  std::string notice;     // what was added last, said in the empty field
};
struct FullPlan {
  cc::Scene fixed, content, overlay;
  int scroll_y = 0, scroll_h = 0;  // where the list scrolls
  bool covered = false;            // the overlay takes every touch (a sheet, a question, a keyboard on the whole glass)
};
// The list's face: on glass read from across a room (a hand and a half wide or more) the larger headline face.
inline cc::Face full_face(int W, int H) { return W >= ui::mm(150) && H >= ui::mm(85) ? cc::HEADLINE : cc::CONTROL; }
inline int full_row(const cc::Measure &m, cc::Face face = cc::CONTROL) { return std::max(ui::touch_min(), L(m, face) + ui::px(18)); }
inline int full_head() { return std::max(ui::px(56), ui::touch_min() + ui::px(16)); }
inline bool is_typing(const Data &d, const Full &st) { return st.keys && (d.may & (MAY_ADD | MAY_RENAME)); }
// The keyboard of the full screen, into the plan's overlay alone: a key that only changes what is typed plans and
// paints nothing else (module_todo.cpp retype). Returns where the sheet begins.
inline Keyboard plan_typing(FullPlan &p, const cc::Measure &m, int W, int H, const Data &d, const Words &wd, const Full &st) {
  p.overlay.clear();
  const std::string hint = st.renaming ? wd.rename : st.notice.empty() ? wd.add : fill(wd.added, st.notice);
  const Keyboard k = plan_keyboard(p.overlay, m, W, H, full_head() + full_row(m, full_face(W, H)) + ui::px(8), st.entry,
                                   st.renaming ? std::vector<std::string>() : offers(d, st.entry.text), hint,
                                   !st.renaming && (d.may & MAY_ADD) && !d.offers.empty());
  p.covered = k.whole;
  return k;
}
inline void plan_full(FullPlan &p, const cc::Measure &m, int W, int H, const std::string &name, const Data &d, const Marks &marks,
                      const Words &wd, const Full &st) {
  p.fixed.clear(); p.content.clear(); p.overlay.clear(); p.covered = false;
  const cc::Face face = full_face(W, H);
  const int key = ui::touch_min(), margin = ui::px(16), head = full_head(), rowh = full_row(m, face);
  // The head: the key that closes, the list's name, and how much is open.
  round_key(p.fixed, m, margin, (head - key) / 2, key, I_CLOSE, H_CLOSE);
  const std::string count = count_words(d, marks, wd);
  const int cw = m.width(cc::SMALL, count), tx = margin + key + ui::px(14);
  words(p.fixed, m, tx, (head - L(m, cc::HEADLINE)) / 2, W - tx - margin - cw - ui::px(16), cc::HEADLINE, {cc::INK}, name);
  words(p.fixed, m, W - margin - cw, (head - L(m, cc::SMALL)) / 2, cw, cc::SMALL, {cc::MUTED}, count);
  int bottom = H;
  const bool typing = is_typing(d, st);
  if (typing) bottom = plan_typing(p, m, W, H, d, wd, st).top;
  p.scroll_y = head;
  p.scroll_h = std::max(0, bottom - head);
  // The list, in a column no wider than a line reads.
  const int col = std::min(W - 2 * margin, ui::control_max_width()), x = (W - col) / 2;
  int y = ui::px(4);
  if ((d.may & MAY_ADD) && !typing) {
    box(p.content, x, y, col, key, key / 2, {cc::TRACK});
    words(p.content, m, x + ui::px(16), y + (key - L(m, cc::CONTROL)) / 2, col - key - ui::px(16), cc::CONTROL, {cc::SUBTLE}, wd.add);
    glyph(p.content, m, x + col - key, y, key, key, cc::ICON, {cc::MUTED}, I_PLUS);
    hit(p.content, x, y, col, key, H_FIELD);
    y += key + ui::px(8);
  }
  int shown_open = 0;
  size_t i = 0;
  for (; i < d.items.size() && !(d.items[i].flags & DONE); ++i) {
    row(p.content, m, x, y, col, rowh, face, d.items[i], is_done(d.items[i], marks), true, wd);
    hit(p.content, x - ui::px(8), y, col + ui::px(16), rowh, H_ROW, int(i));
    y += rowh;
    ++shown_open;
  }
  if (d.open > shown_open) {
    const int indent = tick_size(m) + ui::px(12);
    words(p.content, m, x + indent, y + (rowh - L(m, cc::SMALL)) / 2, col - indent, cc::SMALL, {cc::MUTED},
          fill(wd.more, std::to_string(d.open - shown_open)));
    y += rowh;
  }
  if (d.items.empty() && !d.open) {
    words(p.content, m, x, y + ui::px(24), col, cc::CONTROL, {cc::MUTED}, d.waiting ? wd.waiting : wd.empty, cc::CENTRE);
    y += rowh + ui::px(24);
  }
  if (i < d.items.size()) {
    y += ui::px(10);
    const bool clear = d.may & MAY_CLEAR;
    words(p.content, m, x, y + (key - L(m, cc::SMALL)) / 2, col - (clear ? key : 0), cc::SMALL, {cc::MUTED}, wd.completed);
    if (clear) round_key(p.content, m, x + col - key, y, key, I_BIN, H_CLEAR);
    y += key + ui::px(4);
    for (; i < d.items.size(); ++i) {
      row(p.content, m, x, y, col, rowh, face, d.items[i], is_done(d.items[i], marks), false, wd);
      hit(p.content, x - ui::px(8), y, col + ui::px(16), rowh, H_ROW, int(i));
      y += rowh;
    }
  }
  p.content.height = y + ui::px(16);
  // A sheet over the page: an item's (its name, and what may be done with it) or the question before what is done goes.
  const bool sheet = st.sheet >= 0 && size_t(st.sheet) < d.items.size() && !typing;
  if (!sheet && !(st.confirm && !typing)) return;
  p.covered = true;
  box(p.overlay, 0, 0, W, H, 0, {cc::SCRIM}, 120);
  hit(p.overlay, 0, 0, W, H, H_SCRIM);
  const int pad = ui::px(20), gap = ui::px(10), pw = std::min(W - 2 * margin, ui::px(420)), kh = std::max(key, ui::px(48));
  const int ph = 2 * pad + L(m, cc::CONTROL) + ui::px(18) + kh, px = (W - pw) / 2, py = (H - ph) / 2;
  cc::Box b; b.x = px; b.y = py; b.w = pw; b.h = ph; b.radius = ui::px(20); b.paint = {cc::RAISED}; b.border = 1; b.line = {cc::RAISED_LINE};
  p.overlay.boxes.push_back(b);
  hit(p.overlay, px, py, pw, ph, H_PANEL);
  const std::string title = sheet ? roomy::plain(d.items[st.sheet].text) : fill(wd.clear, std::to_string(d.done));
  words(p.overlay, m, px + pad, py + pad, pw - 2 * pad, cc::CONTROL, {cc::INK}, title, cc::CENTRE);
  const int by = py + pad + L(m, cc::CONTROL) + ui::px(18), bw = (pw - 2 * pad - gap) / 2;
  auto button = [&](int n, int of, const std::string &label, cc::HitKind kind, cc::Paint ground, cc::Paint ink) {
    const int w = of == 1 ? pw - 2 * pad : bw, bx = px + pad + n * (bw + gap);
    box(p.overlay, bx, by, w, kh, kh / 2, ground);
    words(p.overlay, m, bx + ui::px(8), by + (kh - L(m, cc::LABEL)) / 2, w - ui::px(16), cc::LABEL, ink, label, cc::CENTRE);
    hit(p.overlay, bx, by, w, kh, kind);
  };
  if (sheet) {
    const bool rename = d.may & MAY_RENAME, remove = d.may & MAY_REMOVE;
    const int of = (rename ? 1 : 0) + (remove ? 1 : 0);
    int n = 0;
    if (rename) button(n++, of, wd.rename, H_RENAME, {cc::TRACK}, {cc::INK});
    if (remove) button(n++, of, wd.remove, H_REMOVE, {cc::TRACK}, own(C_LATE));
    if (!of) button(0, 1, wd.cancel, H_NO, {cc::TRACK}, {cc::INK});
  } else {
    button(0, 2, wd.cancel, H_NO, {cc::TRACK}, {cc::INK});
    button(1, 2, wd.remove, H_YES, {cc::ACCENT}, {cc::ON_NOW});
  }
}


// ---- A row swiped to the left (the full screen): what may be done with its item comes in from the row's end, over
// its due day, as far as the finger drew it; the item's name stays where it is, so it is clear whose keys they are.
// The keys are planned once when the drag begins, at the place they end up, so a finger's move repaints the row's
// strip and plans nothing.
struct Swipe {
  cc::Scene keys;
  int x = 0, y = 0, w = 0, h = 0;  // the row's strip, in the list's coordinates
  int reveal = 0;                  // how far the keys travel to stand whole
};
inline bool plan_swipe(Swipe &sw, const cc::Measure &m, const FullPlan &p, const Data &d, const Words &wd, int index) {
  sw.keys.clear(); sw.reveal = 0;
  const cc::Hit *at = nullptr;
  for (const auto &h : p.content.hits) if (h.kind == H_ROW && h.arg == index) at = &h;
  const bool rename = d.may & MAY_RENAME, remove = d.may & MAY_REMOVE;
  if (!at || index < 0 || size_t(index) >= d.items.size() || (!rename && !remove)) return false;
  sw.x = at->x; sw.y = at->y; sw.w = at->w; sw.h = at->h;
  const int pad = ui::px(8), gap = ui::px(8), kh = sw.h - ui::px(8), end = sw.x + sw.w - pad;
  int x = end;
  auto pill = [&](const std::string &label, cc::HitKind kind, cc::Paint ground, cc::Paint ink) {
    const int w = std::max(ui::touch_min() + ui::px(16), m.width(cc::LABEL, label) + ui::px(28));
    x -= w;
    box(sw.keys, x, sw.y + (sw.h - kh) / 2, w, kh, kh / 2, ground);
    words(sw.keys, m, x + ui::px(6), sw.y + (sw.h - L(m, cc::LABEL)) / 2, w - ui::px(12), cc::LABEL, ink, label, cc::CENTRE);
    hit(sw.keys, x - gap / 2, sw.y, w + gap, sw.h, kind, index);
    x -= gap;
  };
  if (remove) pill(wd.remove, H_REMOVE, own(C_LATE), {cc::ON_NOW});
  if (rename) pill(wd.rename, H_RENAME, {cc::TRACK}, {cc::INK});
  sw.reveal = end - x + pad;
  // The card's own ground under the keys, so they cover what the row shows there.
  cc::Box ground; ground.x = sw.x + sw.w - sw.reveal; ground.y = sw.y; ground.w = sw.reveal; ground.h = sw.h; ground.paint = {cc::CARD};
  sw.keys.boxes.insert(sw.keys.boxes.begin(), ground);
  return true;
}

}  // namespace todo
