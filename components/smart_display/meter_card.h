#pragma once
// A sensor's meter (firmware 0.56.0, docs/METER.md): where its value stands in its range, as a ring, a tape or a bar of
// cells, drawn on any size of card. This file only plans: what goes where, in which face. meter_view.cpp paints a plan
// in one LVGL object per card (as the calendar and energy cards do), so a bar of a hundred cells is one object.
//
// The three looks, chosen with the owner in the design study of 10-12 (tools/render/gauge_study.h, rounds 3 to 13):
//   ring  a 240 degree ring filled to the value on a grey track, open at the bottom; the tile's icon in its tinted
//         circle inside; the value with its unit under the ring's ends, the name quiet under it. Beside the ring on a
//         long card, and on a roomy long card the right half is the last 24 hours as a line with a soft fill.
//   tape  Teenage Engineering: the name in small capitals, the value in a regular face, a still ruler of hairline
//         marks over the tile's range with one pointer at the value; the ends named small under their marks (never
//         for a percentage, whose ends everyone knows).
//   bar   an LCD: the words at the top, narrow cells over all the room under them, lit in the value's colour and the
//         rest a dim tint of it; a standing card stands the bar up beside its words.
// Every decision follows from the room, the board's faces and its scale (ui::px), never from a board's name.
#include "ui_scale.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace meter_card {
enum Style : uint8_t { RING, TAPE, BAR };
// The board's fixed fonts a meter takes (meter_view.cpp names them): the name, the small words, the control words,
// the headline, the big value, the setpoint's digits (digits only), and four icon sizes.
enum Face : uint8_t { LABEL, SMALL, CONTROL, HEADLINE, VALUE, DIGITS, ICON_WATCH, ICON_MINI, ICON, ICON_BIG, FACES };
struct Measure {
  std::array<int, FACES> line{};  // a face's line height
  std::array<int, FACES> base{};  // from the bottom of its line to its baseline (lv_font_t::base_line)
  std::function<int(Face, const std::string &)> width;
  // Whether a face draws every glyph of a text: the setpoint's digits have no letters, the big icons a few icons.
  std::function<bool(Face, const std::string &)> covers;
  int h(Face f) const { return line[f]; }
  int ascent(Face f) const { return line[f] - base[f]; }
  int w(Face f, const std::string &s) const { return width ? width(f, s) : 0; }
  bool has(Face f, const std::string &s) const { return !covers || covers(f, s); }
};
// What a card shows: the words the tile writes, and where the value stands.
struct Data {
  std::string number;  // the value as the screen writes it ("21,5"), or a word where there is none ("Unavailable")
  std::string unit;    // Home Assistant's unit, "" for none
  std::string words;   // the number with its unit as the tile writes them ("21,5 °C", "64 %")
  std::string name, icon;
  std::string low, high;  // the range's ends as the screen writes them
  bool percent = false;   // the unit is %: the tape names no ends
  bool graph = false;     // 24 samples of the last day to draw beside a long ring
};
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  int cx() const { return x + w / 2; }
  int cy() const { return y + h / 2; }
};
enum Role : uint8_t { INK, MUTED };
enum Align : uint8_t { LEFT, CENTRE, RIGHT };
struct Text { int x = 0, y = 0, w = 0; Face face = LABEL; Role role = INK; Align align = LEFT; std::string s; };
struct Plan {
  Style style = RING;
  int width = 0, height = 0;
  // The ring: its centre, its outer diameter and its thickness; the icon's circle and its face.
  bool ring = false;
  int cx = 0, cy = 0, d = 0, thick = 0, disc = 0;
  Face icon = ICON;
  // The tape's ruler (the marks stand on its bottom edge), its steps, and the pointer's width and reach above it.
  bool tape = false;
  Rect ruler;
  float major = 0, minor = 0;
  int pointer = 0, over = 0;
  // The bar's cells: their room, standing or lying, each cell's depth along the bar and the gap between two.
  bool bar = false, up = false;
  Rect cells;
  int cell = 0, gap = 0, count = 0;
  // The last day's line, beside a long ring.
  bool graph = false;
  Rect line;
  int stroke = 0;
  std::vector<Text> texts;
  int cut = 0;  // texts that had to be shortened to fit (tests want none on the sizes a screen takes)
};

// A text shortened with an ellipsis until it fits `w` (the fonts all have "…"); `cut` counts it.
inline std::string fit(const Measure &m, Face f, const std::string &s, int w, int &cut) {
  if (m.w(f, s) <= w) return s;
  ++cut;
  std::string out = s;
  while (!out.empty()) {
    // Drop one UTF-8 character from the end.
    size_t at = out.size() - 1;
    while (at > 0 && (static_cast<unsigned char>(out[at]) & 0xC0) == 0x80) --at;
    out.erase(at);
    while (!out.empty() && out.back() == ' ') out.pop_back();
    if (m.w(f, out + "…") <= w) return out + "…";
  }
  return "";
}
inline void add(Plan &p, const Measure &m, int x, int y, int w, Face f, Role role, Align a, const std::string &s) {
  if (s.empty() || w <= 0) return;
  Text t;
  t.x = x; t.y = y; t.w = w; t.face = f; t.role = role; t.align = a;
  t.s = fit(m, f, s, w, p.cut);
  if (!t.s.empty()) p.texts.push_back(std::move(t));
}
inline std::string upper(const std::string &s) {
  std::string out = s;
  for (auto &c : out) if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
  return out;
}
// A step for a ruler's long marks: the first of the usual steps that makes at most `most` of them over `span`.
// A step for a ruler's long marks that divides the range into whole parts (400 to 1600 in six of 200), at most `most`
// of them; a range no round step divides gets the round step that makes at most `most` of them.
inline float ruler_step(float span, int most) {
  for (float s : {0.01f, 0.02f, 0.05f, 0.1f, 0.2f, 0.25f, 0.5f, 1.0f, 2.0f, 2.5f, 5.0f, 10.0f, 20.0f, 25.0f, 50.0f, 100.0f,
                  200.0f, 250.0f, 500.0f, 1000.0f, 2000.0f, 2500.0f, 5000.0f, 10000.0f}) {
    const float parts = span / s;
    if (parts >= 0.999f && parts <= most && std::fabs(parts - std::round(parts)) < 1e-3f) return s;
  }
  return 0;
}
inline float nice_step(float span, int most) {
  for (float s : {0.01f, 0.02f, 0.05f, 0.1f, 0.2f, 0.25f, 0.5f, 1.0f, 2.0f, 2.5f, 5.0f, 10.0f, 20.0f, 25.0f, 50.0f, 100.0f,
                  200.0f, 250.0f, 500.0f, 1000.0f, 2000.0f, 2500.0f, 5000.0f, 10000.0f})
    if (span / s <= most) return s;
  return std::pow(10.0f, std::ceil(std::log10(std::max(span, 1.0f) / most)));
}

// ---- The words, as every look writes them.
// The name in the label face, a step down when it would not fit.
inline Face name_face(const Measure &m, const std::string &name, int w) {
  for (Face f : {LABEL, CONTROL, SMALL}) if (m.w(f, name) <= w) return f;
  return SMALL;
}
// The number and its unit a step smaller, on one baseline (the tape): the pair of faces that fits `w` x `h`.
struct Pair { Face n, u; };
inline int pair_width(const Measure &m, const Data &d, Pair f) {
  const int gap = d.unit == "%" ? ui::px(1) : ui::px(4);
  return m.w(f.n, d.number) + (d.unit.empty() ? 0 : gap + m.w(f.u, d.unit));
}
inline Pair pair_face(const Measure &m, const Data &d, int w, int h, bool digits) {
  static constexpr Pair STEPS[] = {{DIGITS, HEADLINE}, {VALUE, CONTROL}, {HEADLINE, SMALL}, {CONTROL, SMALL}, {LABEL, SMALL}, {SMALL, SMALL}};
  for (const auto &st : STEPS) {
    if (st.n == DIGITS && (!digits || !m.has(DIGITS, d.number))) continue;
    if (m.h(st.n) <= h && pair_width(m, d, st) <= w) return st;
  }
  return STEPS[5];
}
// The pair at (x, y): left, centred or right in `w`.
inline void pair(Plan &p, const Measure &m, const Data &d, int x, int y, int w, Pair f, Align a) {
  const int gap = d.unit == "%" ? ui::px(1) : ui::px(4), total = std::min(w, pair_width(m, d, f));
  const int x0 = a == LEFT ? x : a == CENTRE ? x + (w - total) / 2 : x + w - total;
  const int un = d.unit.empty() ? 0 : m.w(f.u, d.unit);
  add(p, m, x0, y, std::max(1, total - (un ? gap + un : 0)), f.n, INK, LEFT, d.number);
  if (un) add(p, m, x0 + total - un, y + m.ascent(f.n) - m.ascent(f.u), un, f.u, MUTED, LEFT, d.unit);
}

// The value as the ring and the bar write it: the number and its unit in one face, or on a card with the room the
// setpoint's big digits with the unit a step down beside them (DIGITS stands for that pair), as the tape writes it.
constexpr Pair BIG{DIGITS, HEADLINE};
inline int words_width(const Measure &m, const Data &d, Face f) { return f == DIGITS ? pair_width(m, d, BIG) : m.w(f, d.words); }
inline bool words_fit(const Measure &m, const Data &d, Face f, int w, int h) {
  if (f == DIGITS && !m.has(DIGITS, d.number)) return false;
  return m.h(f) <= h && words_width(m, d, f) <= w;
}
// The largest face that holds the value in `w` x `h`.
inline Face words_face(const Measure &m, const Data &d, int w, int h) {
  for (Face f : {DIGITS, VALUE, HEADLINE, CONTROL, LABEL}) if (words_fit(m, d, f, w, h)) return f;
  return LABEL;
}
// The value in `face` and the name quiet under it, from (x, y) in `w`.
inline void words(Plan &p, const Measure &m, const Data &d, int x, int y, int w, Face face, Align a, int lift = 0) {
  if (face == DIGITS) pair(p, m, d, x, y, w, BIG, a);
  else add(p, m, x, y, w, face, INK, a, d.words);
  const Face nf = name_face(m, d.name, w);
  add(p, m, x, y + m.h(face) - lift + (m.h(LABEL) - m.h(nf)), w, nf, MUTED, a, d.name);
}
// ---- The ring.
inline void ring_at(Plan &p, const Measure &m, const Data &d, int cx, int cy, int dia, int thick) {
  p.ring = true; p.cx = cx; p.cy = cy; p.d = dia; p.thick = thick; p.disc = dia * 36 / 100;
  // The largest icon face that fits the disc and has the glyph; else the smallest that has it, never a face without it
  // (an empty disc until the next value, on a 10.1 inch, 2026-11-15).
  p.icon = ICON_WATCH;
  bool found = false;
  for (Face f : {ICON_BIG, ICON, ICON_MINI})
    if (m.h(f) <= dia * 22 / 100 && m.has(f, d.icon)) { p.icon = f; found = true; break; }
  if (!found)
    for (Face f : {ICON_MINI, ICON, ICON_WATCH, ICON_BIG})
      if (m.has(f, d.icon)) { p.icon = f; break; }
}
inline void plan_ring(Plan &p, const Measure &m, const Data &d, Rect r) {
  // A long card: the ring at the left, the words beside it.
  if (r.w > r.h * 13 / 10) {
    const int dia = std::max(ui::px(16), std::min(r.h, r.w * 42 / 100)), thick = std::max(ui::px(4), dia / 13);
    ring_at(p, m, d, r.x + dia / 2, r.cy(), dia, thick);
    const Rect c{r.x + dia + ui::px(14), r.y, r.w - dia - ui::px(14), r.h};
    const Face f = words_face(m, d, c.w, c.h * 55 / 100);
    words(p, m, d, c.x, c.y + (c.h - m.h(f) - m.h(LABEL)) / 2, c.w, f, LEFT);
    return;
  }
  // The ends stand half a radius under the centre; the words start under them, with air between.
  Face f = LABEL;
  int dia = 0;
  for (Face x : {DIGITS, VALUE, HEADLINE, CONTROL, LABEL}) {
    dia = std::min(r.w * 90 / 100, static_cast<int>((r.h - m.h(x) - m.h(LABEL) - ui::px(6)) / 0.79f));
    f = x;
    const int thick = std::max(ui::px(5), dia / 14), gap = static_cast<int>(1.732f * (dia / 2.0f - thick / 2.0f)) - thick - ui::px(12);
    if (words_fit(m, d, x, gap, dia * 22 / 100)) break;
  }
  dia = std::max(ui::px(16), dia);
  const int thick = std::max(ui::px(5), dia / 14);
  const int total = static_cast<int>(0.75f * dia) + thick / 2 + ui::px(6) + m.h(f) + m.h(LABEL);
  const int cx = r.cx(), cy = r.y + std::max(0, (r.h - total) / 2) + dia / 2;
  ring_at(p, m, d, cx, cy, dia, thick);
  // The digits' tops a little under the ends' round caps (a line's top holds some air of its own).
  const int y = cy + static_cast<int>(0.5f * (dia / 2.0f - thick / 2.0f)) + thick / 2 + ui::px(6) - 2 * m.base[f] / 3;
  words(p, m, d, r.x, std::min(y, r.bottom() - m.h(f) - m.h(LABEL)), r.w, f, CENTRE);
}

// ---- The tape: a still ruler from the tile's minimum to its maximum, the pointer at the value.
inline void plan_ruler(Plan &p, const Measure &m, const Data &d, Rect t, float span) {
  const bool ends = !d.percent && t.h >= m.h(SMALL) + ui::px(10);
  Rect r{t.x, t.y, t.w, t.h - (ends ? m.h(SMALL) + ui::px(2) : 0)};
  p.tape = true;
  p.pointer = std::max(3, ui::px(3));
  p.over = std::max(2, ui::px(4));
  // A number stands centred under its mark: the ruler draws in by half of each end's number, so they stay on the card,
  // and always by half the pointer and its rim, so the pointer at an end stays on it too.
  const int rim = p.pointer / 2 + 1;
  const int in_l = std::max(rim, ends ? (m.w(SMALL, d.low) + 1) / 2 : 0), in_r = std::max(rim, ends ? (m.w(SMALL, d.high) + 1) / 2 : 0);
  r.x += in_l; r.w = std::max(1, r.w - in_l - in_r);
  p.ruler = r;
  // The long marks divide the range into whole parts, each cut in fives or halves while a mark keeps a finger's
  // breadth of air (14 px of the look); the marks count from the range's start, so both ends are marks.
  p.major = ruler_step(span, 8);
  if (!(p.major > 0)) p.major = nice_step(span, 5);
  const float major_px = r.w * p.major / span;
  p.minor = major_px / 5 >= ui::px(14) ? p.major / 5 : major_px / 2 >= ui::px(14) ? p.major / 2 : p.major;
  // Too many long marks for a narrow ruler: only the ends are long, the parts short between them.
  if (major_px < ui::px(14)) { p.minor = p.major; p.major = span; }
  if (ends) {
    const int y = r.bottom() + ui::px(2);
    for (int k = 0; k < 2; ++k) {
      const std::string &s = k ? d.high : d.low;
      const int at = k ? r.right() - 1 : r.x, w = m.w(SMALL, s);
      add(p, m, std::max(t.x, at - w / 2), y, w + 1, SMALL, MUTED, LEFT, s);
    }
  }
}
inline void plan_tape(Plan &p, const Measure &m, const Data &d, Rect r, float span) {
  const std::string caps = upper(d.name);
  // A short card: the name and the value on one row, the tape under them.
  if (r.h < m.h(SMALL) + m.h(VALUE) + ui::px(30)) {
    const Pair f = pair_face(m, d, r.w / 2, r.h * 55 / 100, false);
    const int vw = std::min(r.w / 2, pair_width(m, d, f));
    add(p, m, r.x, r.y + m.ascent(f.n) - m.ascent(SMALL), r.w - vw - ui::px(10), SMALL, MUTED, LEFT, caps);
    pair(p, m, d, r.right() - vw, r.y, vw, f, LEFT);
    const int ty = r.y + m.h(f.n) + ui::px(4);
    plan_ruler(p, m, d, {r.x, ty, r.w, std::max(ui::px(8), r.bottom() - ty)}, span);
    return;
  }
  add(p, m, r.x, r.y, r.w, SMALL, MUTED, LEFT, caps);
  const int top = r.y + m.h(SMALL) + ui::px(6), room = r.bottom() - top;
  const int th = std::clamp(room * 34 / 100, ui::px(22), ui::px(56));
  const Pair f = pair_face(m, d, r.w, room - th - ui::px(10), true);
  const int group = m.h(f.n) + ui::px(8) + th, gy = top + std::max(0, (room - group) / 2);
  pair(p, m, d, r.x, gy, r.w, f, CENTRE);
  plan_ruler(p, m, d, {r.x, gy + m.h(f.n) + ui::px(8), r.w, th}, span);
}

// ---- The bar of cells.
inline void cells_in(Plan &p, Rect b, bool up) {
  b.w = std::max(1, b.w); b.h = std::max(1, b.h);
  const int len = up ? b.h : b.w, depth = up ? b.w : b.h;
  p.bar = true; p.up = up; p.cells = b;
  p.cell = std::clamp(depth / 12, std::max(2, ui::px(3)), std::max(2, ui::px(5)));
  p.gap = std::max(1, p.cell * 3 / 5);
  // At most 60 cells, as a real LED bar graph has: on a big card the cells grow wider instead of turning into a hatch.
  p.count = std::clamp((len + p.gap) / (p.cell + p.gap), 10, 60);
}
inline void plan_bar(Plan &p, const Measure &m, const Data &d, Rect r) {
  // A standing card: the bar stands up at the right, near a third of the card wide, the words at the top beside it.
  if (r.h > r.w * 11 / 10) {
    const int bw = std::clamp(r.w * 30 / 100, std::min(ui::px(14), r.w / 2), std::max(1, r.w / 2));
    cells_in(p, {r.right() - bw, r.y, bw, r.h}, true);
    const int room = r.w - bw - ui::px(14);
    const Face f = words_face(m, d, room, r.h / 4);
    words(p, m, d, r.x, r.y, room, f, LEFT, ui::px(2));
    return;
  }
  const int least = std::clamp(r.h * 20 / 100, ui::px(10), ui::px(26));
  // A short card: the name and the value on one row, the cells under them.
  if (r.h < m.h(VALUE) + m.h(LABEL) + least + ui::px(8)) {
    const Face f = words_face(m, d, r.w * 60 / 100, std::max(m.h(LABEL), r.h - least - ui::px(6)));
    const int vw = std::min(r.w * 60 / 100, words_width(m, d, f));
    if (f == DIGITS) pair(p, m, d, r.right() - vw, r.y, vw, BIG, LEFT);
    else add(p, m, r.right() - vw, r.y, vw, f, INK, LEFT, d.words);
    const Face nf = name_face(m, d.name, r.w - vw - ui::px(8));
    add(p, m, r.x, r.y + m.ascent(f) - m.ascent(nf), r.w - vw - ui::px(8), nf, MUTED, LEFT, d.name);
    const int y = r.y + m.h(f) + ui::px(6);
    cells_in(p, {r.x, y, r.w, std::max(ui::px(6), r.bottom() - y)}, false);
    return;
  }
  const Face f = words_face(m, d, r.w, r.h - least - m.h(LABEL) - ui::px(12));
  words(p, m, d, r.x, r.y, r.w, f, LEFT, ui::px(2));
  const int y = r.y + m.h(f) + m.h(LABEL) + ui::px(12);
  cells_in(p, {r.x, y, r.w, r.bottom() - y}, false);
}

// ---- A card: the look chosen, in `width` x `height` (the card's content). `span` is the range's width.
inline void plan(Plan &p, const Measure &m, const Data &d, Style style, int width, int height, float span) {
  p = Plan();
  p.style = style; p.width = width; p.height = height;
  if (width < 4 || height < 4) return;
  span = span > 0 ? span : 1;
  const Rect r{0, 0, width, height};
  if (style == TAPE) { plan_tape(p, m, d, r, span); return; }
  if (style == BAR) { plan_bar(p, m, d, r); return; }
  // A roomy long ring card in halves (the owner's pick, round 9): the ring as on any card of the left half's shape,
  // the last 24 hours in the right half, the line and its soft fill as tall as the card.
  if (d.graph && width > height * 13 / 10 && width >= ui::px(360)) {
    const int gap = ui::px(16), left = (width - gap) / 2;
    plan_ring(p, m, d, {0, 0, left, height});
    p.graph = true;
    p.line = {left + gap, ui::px(4), width - left - gap, height - ui::px(4)};
    p.stroke = std::max(2, ui::px(2));
    return;
  }
  plan_ring(p, m, d, r);
}

// ---- The colours: one (the tile's own or one chosen), or two or three segments up to their thresholds.
struct Colours {
  int segments = 1;
  std::array<uint32_t, 3> colors{};  // 0: the tile's own (one segment)
  std::array<float, 2> thresholds{NAN, NAN};
  bool chosen = false;  // a colour of its own, not the tile's: the tape's pointer wears it instead of the orange
};
// Where the thresholds stand when the tile has none: 80 % and 90 % of the range (screen_manager/app/meter.py SHARES).
inline float threshold(const Colours &c, int i, float lo, float hi) {
  if (std::isfinite(c.thresholds[i])) return c.thresholds[i];
  const float share = c.segments == 2 ? 0.8f : i == 0 ? 0.8f : 0.9f;
  return lo + share * (hi - lo);
}
// The colour of a value: the segment it falls in, or the one colour (`own` where the tile chose none).
inline uint32_t colour_at(const Colours &c, float v, float lo, float hi, uint32_t own) {
  if (c.segments <= 1) return c.colors[0] ? c.colors[0] : own;
  int at = 0;
  for (int i = 0; i < c.segments - 1; ++i) if (v >= threshold(c, i, lo, hi)) at = i + 1;
  return c.colors[at] ? c.colors[at] : own;
}
}  // namespace meter_card
