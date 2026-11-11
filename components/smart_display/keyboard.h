#pragma once
// The screen's own keyboard, planned (docs/KEYBOARD.md): a layout's keys, what a key does to what is typed, and the
// sheet a caller shows at the bottom of the glass: the field with the key that sends it, a row of suggestions, and four
// rows of keys. A long press on a letter shows its accents in a strip above it.
//
// What it knows: a layout (a table: the letters, the capitals, a page of digits and one of signs, the accents of a
// letter), and the Spec a caller hands it: the layout, the hint in the empty field, the suggestions, whether their row
// keeps its room, what the send key shows (an icon or a word), the most bytes and characters the field holds, the fewest
// it sends, and whether it shows dots for what is typed (a password). It plans rectangles,
// texts and the places a finger may hit, as the calendar card does (calendar_card.h Scene).
// What it does not know: LVGL, Home Assistant, who asked for it. keyboard_lvgl.h shows a plan on the glass and hears
// the finger; the caller decides what a sent text does and whether the keyboard stays up.
//
// Header only, and nothing in it is made unless a caller uses it: a board whose firmware has no user of the keyboard
// (the CYD, without the to-do card) carries none of it. Pure: tests/test_keyboard.cpp checks it on a PC, with a second
// layout of its own and a send key that is a word; tests/test_keyboard_glyphs.py checks that the screens' fonts have
// every character of every layout here.
#include "calendar_card.h"
#include "ui_scale.h"

#include <algorithm>
#include <cstring>
#include <string>
#include <vector>

namespace keyboard {
namespace cc = calendar_card;

// ---- A layout: three rows of letters (at most 10, 10 and 7 keys: the third stands between shift and backspace), the
// same number of keys on every page, and the labels of the keys that change the page. A new layout is a new table
// like qwerty() and a line in layout(); the planner and the callers stay as they are.
struct Accents {
  const char *key;            // the letter, as the lower-case page has it
  const char *lower[6], *upper[6];  // at most six each, nullptr after the last
};
struct Layout {
  const char *name;
  uint8_t rows[3];
  const char *const *letters, *const *capitals, *const *digits, *const *signs;
  const Accents *accents;
  uint8_t accented;  // how many letters have accents
  const char *to_digits, *to_signs, *to_letters;
};
inline int keys(const Layout &l) { return l.rows[0] + l.rows[1] + l.rows[2]; }

// QWERTY, with a page of digits (`123`) and one of signs (`#+=`). Every character is one the screens' text fonts have
// (packages/core.yaml, the `label` font's glyphs).
inline const Layout &qwerty() {
  static const char *const LOWER[26] = {"q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "a", "s", "d", "f", "g", "h", "j", "k", "l",
                                        "z", "x", "c", "v", "b", "n", "m"};
  static const char *const UPPER[26] = {"Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "A", "S", "D", "F", "G", "H", "J", "K", "L",
                                        "Z", "X", "C", "V", "B", "N", "M"};
  static const char *const DIGITS[26] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "/", ":", ";", "(", ")", "€", "&", "@",
                                         ".", ",", "?", "!", "'", "\"", "+"};
  static const char *const SIGNS[26] = {"[", "]", "{", "}", "#", "%", "^", "*", "=", "_", "\\", "|", "~", "<", ">", "$", "£", "¥", "·",
                                        ".", ",", "?", "!", "'", "°", "…"};
  static const Accents ACCENTS[] = {
      {"a", {"á", "à", "â", "ä", "ã", "å"}, {"Á", "À", "Â", "Ä", "Ã", "Å"}},
      {"e", {"é", "è", "ê", "ë", "ę", nullptr}, {"É", "È", "Ê", "Ë", "Ę", nullptr}},
      {"i", {"í", "ì", "î", "ï", nullptr, nullptr}, {"Í", "Ì", "Î", "Ï", nullptr, nullptr}},
      {"o", {"ó", "ò", "ô", "ö", "õ", "ø"}, {"Ó", "Ò", "Ô", "Ö", "Õ", "Ø"}},
      {"u", {"ú", "ù", "û", "ü", nullptr, nullptr}, {"Ú", "Ù", "Û", "Ü", nullptr, nullptr}},
      {"c", {"ç", "ć", "č", nullptr, nullptr, nullptr}, {"Ç", "Ć", "Č", nullptr, nullptr, nullptr}},
      {"n", {"ñ", "ń", nullptr, nullptr, nullptr, nullptr}, {"Ñ", "Ń", nullptr, nullptr, nullptr, nullptr}},
      {"s", {"ß", "ś", "š", nullptr, nullptr, nullptr}, {"Ś", "Š", nullptr, nullptr, nullptr, nullptr}},
      {"y", {"ý", "ÿ", nullptr, nullptr, nullptr, nullptr}, {"Ý", "Ÿ", nullptr, nullptr, nullptr, nullptr}},
      {"z", {"ž", "ź", "ż", nullptr, nullptr, nullptr}, {"Ž", "Ź", "Ż", nullptr, nullptr, nullptr}},
      {"l", {"ł", nullptr, nullptr, nullptr, nullptr, nullptr}, {"Ł", nullptr, nullptr, nullptr, nullptr, nullptr}},
  };
  static const Layout LAYOUT{"qwerty", {10, 9, 7}, LOWER, UPPER, DIGITS, SIGNS, ACCENTS, uint8_t(sizeof(ACCENTS) / sizeof(*ACCENTS)),
                             "123", "#+=", "abc"};
  return LAYOUT;
}
// The layouts the screens have, by name; none for a name it does not know.
inline const Layout *layout(const std::string &name) {
  if (name == qwerty().name) return &qwerty();
  return nullptr;
}

// ---- What a caller asks for.
struct Spec {
  const Layout *layout = nullptr;        // none: QWERTY
  std::string hint;                      // in the empty field
  std::vector<std::string> suggestions;  // above the keys, a tap on one is the caller's
  bool keep_row = false;                 // the row of suggestions keeps its room while it has none to show
  const char *send_glyph = nullptr;      // the send key: an icon of the screens' icon font ...
  std::string send_word;                 // ... or a word, which takes the place of the icon
  size_t most = 120;                     // the most bytes the field holds
  // The most characters the field holds, as Home Assistant counts a text (Python's len(): code points); 0 for none
  // beyond `most`. A text entity's `max`.
  size_t chars = 0;
  // The fewest characters the send key takes: with fewer it is faded and sends nothing, as Home Assistant's own field
  // refuses a text shorter than its `minlength`. A text entity's `min`.
  size_t least = 0;
  // The field shows a dot for every character instead of the text (a text entity in mode password).
  bool mask = false;
  // The field and its send key above the keys. Off, the sheet is the keys alone and the check key at the bottom right
  // sends: for a caller that shows the text itself (a text entity's text area). It has no close key then either, so
  // such a caller keeps the field where the keyboard takes the whole glass.
  bool field = true;
};
inline const Layout &layout_of(const Spec &k) { return k.layout ? *k.layout : qwerty(); }

// Icons the screens' fonts already carry (screen_manager/app/tile_icons.py): close, the arrows that stand for backspace
// and shift, and the check of the key that sends.
constexpr const char *I_CLOSE = "\U000F0156", *I_BACK = "\U000F004D", *I_SHIFT = "\U000F005D", *I_CHECK = "\U000F012C";
// What a masked field shows for every character: the dot a browser's password field shows.
constexpr const char *MASK = "•";

// ---- Places a finger may hit, as calendar_card's Hit. These five are the keyboard's; a caller that puts the keyboard
// into a scene of its own keeps its own kinds off them (the to-do card's run from 64 to 78 around them).
constexpr cc::HitKind KEY = cc::HitKind(69), SUGGESTION = cc::HitKind(70), SEND = cc::HitKind(71), HIDE = cc::HitKind(72),
                      PANEL = cc::HitKind(73);
// The one colour of its own, as a place in the painter's colour list: a key that is no letter (keyboard_lvgl.h paints
// it the theme's BUTTON).
constexpr uint8_t SPECIAL = 0;

// ---- What is typed.
// A key: a place on the page (0 .. keys(layout) - 1), a key of the accent strip (ACCENT + its place), or one of K_*.
// K_ENTER is the caller's: it sends what the field holds.
constexpr int K_SHIFT = -1, K_BACK = -2, K_PAGE = -3, K_SPACE = -4, K_ENTER = -5, K_SIGNS = -6;
constexpr int ACCENT = 1000;
struct Entry {
  std::string text;
  uint8_t page = 0;   // 0 letters, 1 digits, 2 signs
  bool shift = true;  // the next letter is a capital
  int accents = -1;   // the letter key whose accents show, or none
  // Where what is typed goes, and what backspace erases before: a byte offset into `text`, at the start of a character.
  // reset() puts it at the end; a caller that shows the text itself may put it elsewhere (place()).
  size_t at = 0;
};
inline const char *const *page_keys(const Layout &l, uint8_t page, bool shift) {
  return page == 1 ? l.digits : page == 2 ? l.signs : shift ? l.capitals : l.letters;
}
// The accents of a letter key, at most six; none for a key that has none.
inline std::vector<const char *> accents_of(const Layout &l, int key, bool shift) {
  std::vector<const char *> out;
  if (key < 0 || key >= keys(l)) return out;
  const char *base = l.letters[key];
  for (int i = 0; i < l.accented; ++i)
    if (!std::strcmp(l.accents[i].key, base))
      for (const char *a : shift ? l.accents[i].upper : l.accents[i].lower) if (a) out.push_back(a);
  return out;
}
// The cursor, inside the text and at the start of a character, whatever a caller did to the entry.
inline size_t caret(const Entry &e) {
  size_t at = std::min(e.at, e.text.size());
  while (at > 0 && at < e.text.size() && (static_cast<unsigned char>(e.text[at]) & 0xC0) == 0x80) --at;
  return at;
}
// Puts the cursor at a byte offset (a finger in the caller's text), on the start of the character there.
inline void place(Entry &e, size_t at) {
  e.at = at;
  e.at = caret(e);
  e.accents = -1;
}
// Erases the character before the cursor.
inline void erase_last(Entry &e) {
  size_t at = caret(e);
  if (at == 0) return;
  size_t from = at - 1;
  while (from > 0 && (static_cast<unsigned char>(e.text[from]) & 0xC0) == 0x80) --from;
  e.text.erase(from, at - from);
  e.at = from;
}
// The characters of a text as Home Assistant counts them (code points): every byte that does not continue one.
inline size_t characters(const std::string &text) {
  size_t n = 0;
  for (unsigned char c : text) n += (c & 0xC0) != 0x80;
  return n;
}
// The byte offset after the first `n` characters of a text.
inline size_t after_chars(const std::string &text, size_t n) {
  size_t at = 0;
  while (at < text.size() && n) { ++at; while (at < text.size() && (static_cast<unsigned char>(text[at]) & 0xC0) == 0x80) ++at; --n; }
  return at;
}
// What a field shows of a text: the text, or a dot for every character of it.
inline std::string shown_text(const std::string &text, bool mask) {
  if (!mask) return text;
  std::string dots;
  for (size_t i = characters(text); i > 0; --i) dots += MASK;
  return dots;
}
// Whether the send key takes what the field holds: at least `least` characters.
inline bool sendable(const Entry &e, const Spec &k) { return characters(e.text) >= k.least; }
inline void type(Entry &e, const char *s, const Spec &k) {
  const std::string add = s ? s : "";
  if (add.empty() || e.text.size() + add.size() > k.most) return;
  if (k.chars && characters(e.text) + characters(add) > k.chars) return;
  const size_t at = caret(e);
  // No space at the start, and none beside another.
  if (add == " " && (at == 0 || e.text[at - 1] == ' ' || (at < e.text.size() && e.text[at] == ' '))) return;
  e.text.insert(at, add);
  e.at = at + add.size();
  e.shift = false;
}
inline void press(Entry &e, int key, const Spec &k) {
  const Layout &l = layout_of(k);
  if (key >= ACCENT) {
    const auto strip = accents_of(l, e.accents, e.shift);
    if (size_t(key - ACCENT) < strip.size()) type(e, strip[key - ACCENT], k);
    e.accents = -1;
    return;
  }
  e.accents = -1;
  if (key >= 0 && key < keys(l)) { type(e, page_keys(l, e.page, e.shift)[key], k); return; }
  if (key == K_SHIFT) e.shift = !e.shift;
  else if (key == K_BACK) { erase_last(e); if (e.text.empty() && e.page == 0) e.shift = true; }
  else if (key == K_PAGE) { e.page = e.page ? 0 : 1; }
  else if (key == K_SIGNS) { e.page = e.page == 2 ? 1 : 2; }
  else if (key == K_SPACE) type(e, " ", k);
}
// A long press on a letter that has accents shows them; anything else is the key itself.
inline bool hold(Entry &e, int key, const Spec &k) {
  if (e.page != 0 || accents_of(layout_of(k), key, e.shift).empty()) return false;
  e.accents = key;
  return true;
}
// A new entry, empty or with a text to change (a rename, a text entity's value): what is typed goes at its end.
inline void reset(Entry &e, const std::string &text = "") {
  e = Entry();
  e.text = text;
  e.at = text.size();
  e.shift = text.empty();
}
// What the field holds, ready to send: no space at either end.
inline std::string typed(const Entry &e) {
  size_t a = 0, b = e.text.size();
  while (a < b && e.text[a] == ' ') ++a;
  while (b > a && e.text[b - 1] == ' ') --b;
  return e.text.substr(a, b - a);
}

// ---- The plan.
namespace draw {
inline void box(cc::Scene &s, int x, int y, int w, int h, int radius, cc::Paint p) {
  cc::Box b; b.x = x; b.y = y; b.w = w; b.h = h; b.radius = radius; b.paint = p; s.boxes.push_back(b);
}
inline void framed(cc::Scene &s, int x, int y, int w, int h, int radius, cc::Paint p, cc::Paint line) {
  cc::Box b; b.x = x; b.y = y; b.w = w; b.h = h; b.radius = radius; b.paint = p; b.border = 1; b.line = line; s.boxes.push_back(b);
}
inline void words(cc::Scene &s, const cc::Measure &m, int x, int y, int w, cc::Face f, cc::Paint p, const std::string &text,
                  cc::Align align = cc::LEFT) {
  if (w <= 0) return;
  cc::Text t; t.x = x; t.y = y; t.w = w; t.face = f; t.paint = p; t.align = align; t.s = cc::fit(m, f, text, w); s.texts.push_back(std::move(t));
}
// A glyph or a short label centred in a box.
inline void glyph(cc::Scene &s, const cc::Measure &m, int x, int y, int w, int h, cc::Face f, cc::Paint p, const char *g) {
  cc::Text t; t.x = x; t.y = y + (h - cc::L(m, f)) / 2; t.w = w; t.face = f; t.paint = p; t.align = cc::CENTRE; t.s = g; s.texts.push_back(std::move(t));
}
inline void hit(cc::Scene &s, int x, int y, int w, int h, cc::HitKind kind, int arg = 0) {
  cc::Hit a; a.x = x; a.y = y; a.w = w; a.h = h; a.kind = kind; a.arg = arg; s.hits.push_back(a);
}
inline void round_key(cc::Scene &s, const cc::Measure &m, int x, int y, int d, const char *g, cc::HitKind kind, cc::Paint ground,
                      cc::Paint ink) {
  box(s, x, y, d, d, d / 2, ground);
  glyph(s, m, x, y, d, d, cc::ICON, ink, g);
  hit(s, x, y, d, d, kind);
}
}  // namespace draw

// The keyboard's sheet at the bottom of a glass of `W` x `H`, never above `top`: the field with the key that sends it,
// the suggestions, and four rows of keys. Never wider than two hands need; a key never taller than 9 mm. On glass too
// short for keys a finger can hit below `top` it takes the whole glass (`whole`), with a key that puts it away.
// Returns where the sheet begins.
struct Place { int top = 0; bool whole = false; };
inline Place plan(cc::Scene &s, const cc::Measure &m, int W, int H, int top, const Entry &e, const Spec &k) {
  using cc::L;
  using namespace draw;
  const Layout &lay = layout_of(k);
  Place out;
  const int sp = ui::px(10), g = std::max(3, ui::px(6)), field = ui::touch_min(), margin = ui::px(16);
  // Without the field the keys begin at the top of the sheet: its height and the gaps around it go.
  const int fieldh = k.field ? field : 0, gaps = k.field ? 5 * g : 3 * g + g / 2, keys_y = k.field ? field + g + g / 2 : 0;
  int kw = std::min(W, ui::mm(165));
  if (W - kw < ui::mm(24)) kw = W;
  const bool floats = kw < W;
  const int least = 2 * sp + fieldh + gaps + 4 * ui::mm(7);
  out.whole = H - top - (floats ? margin : 0) < least;
  if (out.whole) top = 0;
  const int room = H - top - (floats && !out.whole ? margin : 0);
  // The row of suggestions keeps its room while the caller says so, also when it has none to show: the keys never
  // move under a finger that is typing.
  int chips = ui::mm(6) + g;
  if ((k.suggestions.empty() && !k.keep_row) || (room - 2 * sp - fieldh - chips - gaps) / 4 < ui::mm(13) / 2) chips = 0;
  const int keyh = std::max(ui::px(20), std::min(ui::mm(9), (room - 2 * sp - fieldh - chips - gaps) / 4));
  const int sh = out.whole ? H : 2 * sp + fieldh + chips + gaps + 4 * keyh;
  const int sx = (W - kw) / 2, sy = out.whole ? 0 : H - sh - (floats ? margin : 0);
  out.top = sy;
  if (out.whole) box(s, 0, 0, W, H, 0, {cc::CARD});
  else framed(s, sx, sy, kw, sh, floats ? ui::px(20) : 0, {cc::CARD}, {cc::GRID});
  hit(s, out.whole ? 0 : sx, sy, out.whole ? W : kw, sh, PANEL);
  const int inner = kw - 2 * sp, x0 = sx + sp;
  // The field, the key that puts the keyboard away where it covers the caller's own, and the key that sends: round
  // with an icon, or as wide as its word.
  const bool ready = sendable(e, k);
  if (k.field) {
  const int fx = out.whole ? field + g : 0;
  if (out.whole) round_key(s, m, x0, sy + sp, field, I_CLOSE, HIDE, {cc::TRACK}, {cc::INK});
  const bool word = !k.send_word.empty();
  const int send = word ? std::max(field, m.width(cc::LABEL, k.send_word) + 2 * ui::px(16)) : field;
  const int fw = inner - send - g - fx;
  box(s, x0 + fx, sy + sp, fw, field, field / 2, {cc::TRACK});
  const int ty = sy + sp + (field - L(m, cc::CONTROL)) / 2, pad = ui::px(16);
  if (e.text.empty()) words(s, m, x0 + fx + pad + ui::px(6), ty, fw - 2 * pad, cc::CONTROL, {cc::SUBTLE}, k.hint);
  // The end of what is typed stays in view: a long text shows its tail. A masked field shows a dot for each character.
  std::string shown = shown_text(e.text, k.mask);
  while (!shown.empty() && m.width(cc::CONTROL, shown) > fw - 2 * pad - ui::px(4)) shown.erase(0, 1 + (static_cast<unsigned char>(shown[0]) >= 0xC0 ? (static_cast<unsigned char>(shown[0]) >= 0xE0 ? 2 : 1) : 0));
  if (!shown.empty()) { cc::Text t; t.x = x0 + fx + pad; t.y = ty; t.w = fw - 2 * pad; t.face = cc::CONTROL; t.paint = {cc::INK}; t.s = shown; s.texts.push_back(std::move(t)); }
  // The cursor where what is typed goes: after the characters before it that are in view.
  const size_t before = characters(e.text.substr(0, caret(e))), hidden = characters(e.text) - characters(shown);
  const std::string lead = shown.substr(0, after_chars(shown, before > hidden ? before - hidden : 0));
  box(s, x0 + fx + pad + (lead.empty() ? 0 : m.width(cc::CONTROL, lead)) + ui::px(2), ty, std::max(2, ui::px(2)), L(m, cc::CONTROL), 1, {cc::ACCENT});
  // Too short to send: the key is faded, as the check key at the bottom right is.
  const cc::Paint send_ground = ready ? cc::Paint{cc::ACCENT} : cc::Paint{cc::TRACK}, send_ink = ready ? cc::Paint{cc::ON_NOW} : cc::Paint{cc::SUBTLE};
  if (word) {
    const int bx = x0 + inner - send, by = sy + sp;
    box(s, bx, by, send, field, field / 2, send_ground);
    words(s, m, bx + ui::px(8), by + (field - L(m, cc::LABEL)) / 2, send - ui::px(16), cc::LABEL, send_ink, k.send_word, cc::CENTRE);
    hit(s, bx, by, send, field, SEND);
  } else {
    round_key(s, m, x0 + inner - field, sy + sp, field, k.send_glyph ? k.send_glyph : I_CHECK, SEND, send_ground, send_ink);
  }
  }
  if (chips) {
    int x = x0;
    const int h = chips - g, y = sy + sp + (k.field ? field + g : 0);
    for (size_t i = 0; i < k.suggestions.size(); ++i) {
      const int w = m.width(cc::SMALL, k.suggestions[i]) + 2 * ui::px(14);
      if (x + w > x0 + inner) break;
      framed(s, x, y, w, h, h / 2, {cc::CARD}, {cc::GRID});
      words(s, m, x, y + (h - L(m, cc::SMALL)) / 2, w, cc::SMALL, {cc::INK}, k.suggestions[i], cc::CENTRE);
      hit(s, x, y - g / 2, w, h + g, SUGGESTION, int(i));
      x += w + g;
    }
  }
  // On the whole glass the keys stand at its bottom, where the thumbs are.
  const int kwid = (inner - 9 * g) / 10, radius = ui::px(8);
  const int y0 = out.whole ? std::max(sy + sp + keys_y + chips, H - sp - 4 * keyh - 3 * g) : sy + sp + keys_y + chips;
  const cc::Face letter = keyh >= 2 * L(m, cc::HEADLINE) - ui::px(8) && kwid >= ui::mm(11) ? cc::HEADLINE : cc::CONTROL;
  const cc::Paint special = cc::cal(cc::CAL_KEY, SPECIAL);
  auto key = [&](int x, int y, int w, const char *label, int code, bool icon = false, cc::Paint ground = {cc::TRACK}, cc::Paint ink = {cc::INK}) {
    box(s, x, y, w, keyh, radius, ground);
    if (label && *label) glyph(s, m, x, y, w, keyh, icon ? cc::ICON : letter, ink, label);
    // A key's place reaches into the gaps around it, so no touch falls between two keys.
    hit(s, x - g / 2, y - g / 2, w + g, keyh + g, KEY, code);
  };
  const char *const *keys = page_keys(lay, e.page, e.shift);
  // The first two rows stand on a grid of ten keys, a shorter one in its middle; the third between shift and backspace.
  const int side = (3 * kwid + g) / 2;
  const int x_of[3] = {x0 + (10 - lay.rows[0]) * (kwid + g) / 2, x0 + (10 - lay.rows[1]) * (kwid + g) / 2,
                       x0 + side + g + ((inner - 2 * side - 2 * g) - (lay.rows[2] * kwid + (lay.rows[2] - 1) * g)) / 2};
  auto row = [&](int r) {
    const int n = r == 0 ? 0 : r == 1 ? lay.rows[0] : lay.rows[0] + lay.rows[1];
    for (int i = 0; i < lay.rows[r]; ++i) key(x_of[r] + i * (kwid + g), y0 + r * (keyh + g), kwid, keys[n + i], n + i);
  };
  row(0);
  row(1);
  const int y3 = y0 + 2 * (keyh + g), y4 = y0 + 3 * (keyh + g), wide = 2 * kwid + g;
  if (e.page == 0) key(x0, y3, side, I_SHIFT, K_SHIFT, true, e.shift ? cc::Paint{cc::ACCENT_TINT} : special);
  else key(x0, y3, side, e.page == 1 ? lay.to_signs : lay.to_digits, K_SIGNS, false, special);
  row(2);
  key(x0 + inner - side, y3, side, I_BACK, K_BACK, true, special);
  key(x0, y4, wide, e.page ? lay.to_letters : lay.to_digits, K_PAGE, false, special);
  key(x0 + wide + g, y4, inner - 2 * wide - 2 * g, "", K_SPACE);
  key(x0 + inner - wide, y4, wide, I_CHECK, K_ENTER, true, special, ready ? cc::Paint{cc::INK} : cc::Paint{cc::SUBTLE});
  // A letter's accents, in a strip above it: a tap takes one.
  const auto strip = accents_of(lay, e.accents, e.shift);
  if (e.page == 0 && !strip.empty()) {
    const int row = e.accents < lay.rows[0] ? 0 : e.accents < lay.rows[0] + lay.rows[1] ? 1 : 2;
    const int col = e.accents - (row > 0 ? lay.rows[0] : 0) - (row > 1 ? lay.rows[1] : 0);
    const int kx = x_of[row] + col * (kwid + g), ky = y0 + row * (keyh + g);
    const int n = int(strip.size()), w = n * kwid + 2 * g, h = keyh + 2 * g;
    const int px = std::min(x0 + inner - w, std::max(x0, kx - g)), py = ky - h - g / 2;
    hit(s, sx, sy, kw, sh, PANEL);  // a tap beside the strip takes no key under it
    cc::Box b; b.x = px; b.y = py; b.w = w; b.h = h; b.radius = radius + g; b.paint = {cc::RAISED}; b.border = 1; b.line = {cc::RAISED_LINE};
    s.boxes.push_back(b);
    for (int i = 0; i < n; ++i) {
      if (i == 0) box(s, px + g, py + g, kwid, keyh, radius, {cc::ACCENT});
      glyph(s, m, px + g + i * kwid, py + g, kwid, keyh, letter, {i == 0 ? cc::ON_NOW : cc::INK}, strip[i]);
      hit(s, px + g + i * kwid, py, kwid, h, KEY, ACCENT + i);
    }
  }
  return out;
}

}  // namespace keyboard
