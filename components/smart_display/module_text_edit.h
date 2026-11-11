#pragma once
// A text's field (module text_edit, docs/TEXT_ENTITY.md): what the keyboard is asked for when a tile of a Home Assistant
// text (text, input_text) opens, and what its send key does with what was typed. Home Assistant is the reference: its
// entity row for a text (hui-input-text-entity-row) and the text entity's own checks (text/entity.py, services.py).
//
// What it knows: the entity's state, its `min` and `max` (characters, as Python's len() counts them) and whether it is
// a password. What it does not know: LVGL, the keyboard's sheet, how the value reaches Home Assistant.
// module_text_edit.cpp shows the field with keyboard_lvgl.h and sends a value through wish() (docs/OPTIMISTIC.md).
// `pattern` is not checked here: Home Assistant's text.set_value refuses a value that does not match, and the tile then
// shows the old value again.
//
// Pure: tests/test_text_edit.cpp checks it on a PC.
#include "keyboard.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <string>
#include <vector>

namespace text_edit {

// Home Assistant's longest state (MAX_LENGTH_STATE_STATE): no text holds more characters.
constexpr size_t MOST_CHARS = 255;
// ... each at most four bytes of UTF-8 (tile_controls::TEXT_BYTES, what the screen keeps of the state).
constexpr size_t MOST_BYTES = 4 * MOST_CHARS;

// "unknown" and "unavailable" are the words of a state, not a text: Home Assistant's field never sends them, and a text
// without a value yet starts empty.
inline bool state_word(const std::string &text) { return text == "unknown" || text == "unavailable"; }
inline std::string start(const std::string &state) { return state_word(state) ? std::string() : state; }

// The keyboard for a text with these attributes: at most `max` characters, at least `min` before the check takes it,
// dots for a password, and no suggestions. The send key is the keyboard's check, as on its bottom right: it needs no
// word in ten languages, and the field keeps its room on the smallest glass.
inline keyboard::Spec spec(float min, float max, bool secret) {
  keyboard::Spec k;
  const float most = std::isfinite(max) && max >= 1 ? std::min<float>(max, MOST_CHARS) : MOST_CHARS;
  k.chars = static_cast<size_t>(most);
  k.least = std::isfinite(min) && min > 0 ? std::min(static_cast<size_t>(min), k.chars) : 0;
  k.most = MOST_BYTES;
  k.mask = secret;
  return k;
}

// What the send key does with the field: KEEP while it holds too few or too many characters (the key is faded then),
// CLOSE without sending what Home Assistant has already (or a state's word), SEND anything else.
enum class Verdict { KEEP, CLOSE, SEND };
inline Verdict sent(const std::string &text, const std::string &state, const keyboard::Spec &k) {
  const size_t n = keyboard::characters(text);
  if (n < k.least || (k.chars && n > k.chars) || text.size() > k.most) return Verdict::KEEP;
  if (text == start(state) || state_word(text)) return Verdict::CLOSE;
  return Verdict::SEND;
}

// ---- The text area: the whole value over as many lines as it takes, above the keys, with the cursor where a finger put
// it (a tap, or a finger held and dragged, as on a phone). It shows what the field holds (dots for a password), and the
// lines that hold the cursor stay in view.
namespace cc = calendar_card;
struct Line { size_t from = 0, to = 0; int y = 0; };  // a line's bytes of the shown text and where it stands
struct Area {
  std::string shown;         // the text as it stands on the glass: the text, or its dots
  std::vector<Line> lines;   // only the ones in view
  int x = 0, y = 0, w = 0, h = 0, pad = 0, line = 0;
  cc::Face face = cc::CONTROL;
};
// Where the lines of `text` break in `width`: after a space where a word would not fit, inside a word only when the word
// alone is wider than the line. A text of Home Assistant holds no line feed (a state is one line).
inline std::vector<Line> wrap(const cc::Measure &m, cc::Face f, const std::string &text, int width) {
  std::vector<Line> out;
  size_t from = 0;
  while (from < text.size() || out.empty()) {
    size_t at = from, space = std::string::npos;
    while (at < text.size()) {
      size_t next = at + 1;
      while (next < text.size() && (static_cast<unsigned char>(text[next]) & 0xC0) == 0x80) ++next;
      if (m.width(f, text.substr(from, next - from)) > width && at > from) break;
      if (text[at] == ' ') space = next;
      at = next;
    }
    if (at < text.size() && space != std::string::npos && space > from) at = space;
    Line l;
    l.from = from;
    l.to = at;
    out.push_back(l);
    if (at >= text.size()) break;
    from = at;
  }
  return out;
}
// The area in (x, y, w, h): its ground, the lines in view and the cursor. Returns what a finger is held against.
inline Area plan_area(cc::Scene &s, const cc::Measure &m, int x, int y, int w, int h, const keyboard::Entry &e, bool mask) {
  Area a;
  a.x = x; a.y = y; a.w = w; a.h = h;
  a.pad = ui::px(16);
  a.face = cc::CONTROL;
  a.line = cc::L(m, a.face) + ui::px(6);
  a.shown = keyboard::shown_text(e.text, mask);
  cc::Box b; b.x = x; b.y = y; b.w = w; b.h = h; b.radius = ui::px(16); b.paint = {cc::TRACK}; s.boxes.push_back(b);
  auto lines = wrap(m, a.face, a.shown, std::max(1, w - 2 * a.pad - ui::px(4)));
  // The cursor in the shown text: after as many characters as stand before it in the text.
  const size_t at = keyboard::after_chars(a.shown, keyboard::characters(e.text.substr(0, keyboard::caret(e))));
  size_t on = lines.size() - 1;
  for (size_t i = 0; i < lines.size(); ++i) if (at < lines[i].to || (at == lines[i].to && i + 1 == lines.size())) { on = i; break; }
  const int rows = std::max(1, (h - 2 * a.pad + ui::px(6)) / a.line);
  const size_t first = on + 1 > size_t(rows) ? on + 1 - rows : 0;
  for (size_t i = first; i < lines.size() && i < first + rows; ++i) {
    Line l = lines[i];
    l.y = y + a.pad + int(i - first) * a.line;
    cc::Text t; t.x = x + a.pad; t.y = l.y; t.w = w - 2 * a.pad; t.face = a.face; t.paint = {cc::INK};
    t.s = a.shown.substr(l.from, l.to - l.from);
    if (!t.s.empty()) s.texts.push_back(std::move(t));
    a.lines.push_back(l);
    if (i == on) {
      const int cx = x + a.pad + (at > l.from ? m.width(a.face, a.shown.substr(l.from, at - l.from)) : 0);
      cc::Box c; c.x = std::min(cx + ui::px(1), x + w - a.pad); c.y = l.y; c.w = std::max(2, ui::px(2)); c.h = cc::L(m, a.face); c.radius = 1;
      c.paint = {cc::ACCENT}; s.boxes.push_back(c);
    }
  }
  return a;
}
// The byte offset in the text a finger at (px, py) puts the cursor at: the nearest place between two characters on the
// line under the finger (above the first line: its start; below the last: the end of the last).
inline size_t caret_at(const Area &a, const cc::Measure &m, const std::string &text, int px, int py) {
  if (a.lines.empty()) return text.size();
  size_t row = 0;
  while (row + 1 < a.lines.size() && py >= a.lines[row + 1].y) ++row;
  const Line &l = a.lines[row];
  size_t best = l.from, at = l.from;
  int best_d = 1 << 30;
  while (true) {
    const int cx = a.x + a.pad + (at > l.from ? m.width(a.face, a.shown.substr(l.from, at - l.from)) : 0);
    const int d = std::abs(cx - px);
    if (d < best_d) { best_d = d; best = at; }
    if (at >= l.to) break;
    ++at;
    while (at < l.to && (static_cast<unsigned char>(a.shown[at]) & 0xC0) == 0x80) ++at;
  }
  // From the shown text back to the text: as many characters in.
  return keyboard::after_chars(text, keyboard::characters(a.shown.substr(0, best)));
}

}  // namespace text_edit
