#pragma once
// Paints a meter_card::Plan into an LVGL layer: the meter's one object per card (meter_view.cpp) and the host design
// renders (tools/render/meter_firmware.py) share it, so what the renders show is what the glass shows.
#include "lvgl.h"
#include "meter_card.h"
#include "theme.h"
#include "draw_text.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace meter_paint {
namespace mc = meter_card;

// What a card shows besides its plan: where the value stands, its colours and the card under it.
struct Look {
  mc::Plan plan;
  std::array<const lv_font_t *, mc::FACES> faces{};  // the board's fonts, in meter_card::Face's order
  float value = NAN, low = 0, high = 100;
  mc::Colours colours;
  uint32_t own = 0;      // the tile's own colour (Home Assistant's for its state)
  uint32_t ground = 0;   // the card's colour, round the tape's pointer
  bool background = false;  // a card of its own colour: the quiet words in slate, as on every tile
  std::string icon;
  std::vector<float> history;
};

inline float share(const Look &v, float x) { return std::clamp((x - v.low) / std::max(1e-6f, v.high - v.low), 0.0f, 1.0f); }
inline uint32_t colour_at(const Look &v, float x) { return mc::colour_at(v.colours, x, v.low, v.high, v.own); }

// ---- Painting.
inline void rect(lv_layer_t *layer, int x, int y, int w, int h, uint32_t colour, int radius = 0, lv_opa_t opa = LV_OPA_COVER) {
  if (w <= 0 || h <= 0) return;
  lv_draw_rect_dsc_t d;
  lv_draw_rect_dsc_init(&d);
  d.bg_color = lv_color_hex(colour);
  d.bg_opa = opa;
  d.radius = radius;
  lv_area_t a{x, y, x + w - 1, y + h - 1};
  lv_draw_rect(layer, &d, &a);
}
inline void arc(lv_layer_t *layer, int cx, int cy, int d, int w, float a0, float a1, uint32_t colour) {
  lv_draw_arc_dsc_t a;
  lv_draw_arc_dsc_init(&a);
  a.color = lv_color_hex(colour);
  a.width = w;
  a.rounded = 1;
  a.center = {cx, cy};
  a.radius = d / 2;
  a.start_angle = static_cast<lv_value_precise_t>(std::fmod(a0, 360.0f));
  a.end_angle = static_cast<lv_value_precise_t>(std::fmod(a1, 360.0f));
  lv_draw_arc(layer, &a);
}
inline void words(lv_layer_t *layer, const mc::Text &t, const lv_font_t *f, uint32_t colour, int ox, int oy) {
  if (!f) return;
  lv_draw_label_dsc_t d;
  lv_draw_label_dsc_init(&d);
  d.font = f;
  d.color = lv_color_hex(colour);
  d.text = t.s.c_str();
  d.align = t.align == mc::CENTRE ? LV_TEXT_ALIGN_CENTER : t.align == mc::RIGHT ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT;
  // The plan fitted the line to its box; a glyph's overhang may not wrap a left-aligned line onto a second.
  if (t.align == mc::LEFT) d.flag = LV_TEXT_FLAG_EXPAND;
  lv_area_t a{ox + t.x, oy + t.y, ox + t.x + std::max(1, t.w) - 1, oy + t.y + lv_font_get_line_height(f) - 1};
  draw_text::label(layer, d, a);
}
inline void paint_ring(lv_layer_t *layer, const Look &v, int ox, int oy) {
  const auto &p = v.plan;
  const int cx = ox + p.cx, cy = oy + p.cy;
  const bool known = std::isfinite(v.value);
  const uint32_t raw = known ? colour_at(v, v.value) : theme::STATE_OFF, c = theme::foreground(raw);
  arc(layer, cx, cy, p.d, p.thick, 150, 390, theme::hex(theme::TRACK));
  if (known) {
    const float f = share(v, v.value);
    if (f * 240 < 1.0f) {
      // Nothing yet: a dot at the start says where the ring begins.
      const float a = 150 * 3.14159265f / 180, r = p.d / 2.0f - p.thick / 2.0f;
      const int x = cx + static_cast<int>(std::lround(r * std::cos(a))), y = cy + static_cast<int>(std::lround(r * std::sin(a)));
      rect(layer, x - p.thick / 2, y - p.thick / 2, p.thick, p.thick, c, LV_RADIUS_CIRCLE);
    } else arc(layer, cx, cy, p.d, p.thick, 150, 150 + f * 240, c);
  }
  rect(layer, cx - p.disc / 2, cy - p.disc / 2, p.disc, p.disc, known ? theme::tint(raw, theme::dark ? 70 : 45) : theme::hex(theme::TRACK), LV_RADIUS_CIRCLE);
  const lv_font_t *f = v.faces[p.icon];
  if (f && !v.icon.empty()) {
    mc::Text t;
    t.s = v.icon; t.align = mc::CENTRE; t.x = p.cx - p.disc / 2; t.w = p.disc; t.y = p.cy - lv_font_get_line_height(f) / 2;
    words(layer, t, f, known ? c : theme::hex(theme::OFF), ox, oy);
  }
}
inline void paint_tape(lv_layer_t *layer, const Look &v, int ox, int oy) {
  const auto &p = v.plan;
  const mc::Rect r = p.ruler;
  const float span = std::max(1e-6f, v.high - v.low);
  auto mark = [&](float x, bool big) {
    const int at = ox + r.x + std::min(r.w - 1, static_cast<int>(std::lround((x - v.low) / span * (r.w - 1))));
    const int len = big ? r.h * 60 / 100 : r.h * 30 / 100;
    rect(layer, at, oy + r.bottom() - len, 1, std::max(1, len), theme::hex(big ? theme::INK : theme::SUBTLE));
  };
  // The two ends long, and between them a mark at every step from the start, long on the long steps.
  mark(v.low, true);
  mark(v.high, true);
  for (int i = 1; i < 400; ++i) {
    const float x = v.low + i * p.minor;
    if (x >= v.high - p.minor / 10) break;
    mark(x, std::fabs(std::remainder(x - v.low, p.major)) < p.minor / 10);
  }
  if (!std::isfinite(v.value)) return;
  // The pointer a little stronger than the marks, a touch taller than the ruler, the card's colour either side so a
  // mark beside it never runs into it. Orange (Teenage Engineering's, Home Assistant's deep orange), or the segment's.
  const bool own = v.colours.segments > 1 || v.colours.chosen;
  const uint32_t c = theme::foreground(own ? colour_at(v, v.value) : theme::ha::DEEP_ORANGE);
  const int x = ox + r.x + static_cast<int>(std::lround(share(v, v.value) * (r.w - 1))), y = oy + r.y - p.over;
  rect(layer, x - p.pointer / 2 - 1, y, p.pointer + 2, r.h + p.over, v.ground, p.pointer / 2 + 1);
  rect(layer, x - p.pointer / 2, y, p.pointer, r.h + p.over, c, p.pointer / 2);
}
inline void paint_bar(lv_layer_t *layer, const Look &v, int ox, int oy) {
  const auto &p = v.plan;
  const mc::Rect b = p.cells;
  const int len = p.up ? b.h : b.w, n = p.count;
  const bool known = std::isfinite(v.value);
  const int lit = known ? static_cast<int>(std::lround(share(v, v.value) * n)) : 0;
  const uint32_t one = known ? colour_at(v, v.value) : theme::STATE_OFF;
  for (int i = 0; i < n; ++i) {
    const int a = static_cast<int>(static_cast<long>(len) * i / n), e = static_cast<int>(static_cast<long>(len) * (i + 1) / n) - p.gap;
    // With segments each cell wears its own place's colour, so the bar shows where orange and red begin.
    const uint32_t raw = v.colours.segments > 1 ? colour_at(v, v.low + (i + 0.5f) / n * (v.high - v.low)) : one;
    const uint32_t c = i < lit ? theme::foreground(raw) : theme::tint(raw, theme::dark ? 40 : 30);
    if (p.up) rect(layer, ox + b.x, oy + b.bottom() - e, b.w, std::max(1, e - a), c);
    else rect(layer, ox + b.x + a, oy + b.y, std::max(1, e - a), b.h, c);
  }
}
// The last day as Home Assistant's mini graph: a smooth line through the samples and a soft fill under it.
inline void paint_graph(lv_layer_t *layer, const Look &v, int ox, int oy) {
  const auto &p = v.plan;
  std::vector<float> s;
  for (float x : v.history) if (std::isfinite(x)) s.push_back(x);
  const int n = static_cast<int>(s.size());
  if (n < 2 || p.line.w < ui::px(30) || p.line.h < ui::px(16)) return;
  float lo = *std::min_element(s.begin(), s.end()), hi = *std::max_element(s.begin(), s.end());
  if (hi - lo < 1e-6f) { lo -= 1; hi += 1; }
  const uint32_t c = theme::foreground(std::isfinite(v.value) ? colour_at(v, v.value) : v.own);
  const mc::Rect b{ox + p.line.x, oy + p.line.y, p.line.w, p.line.h};
  const int lw = p.stroke;
  constexpr int POINTS = 63;
  lv_point_precise_t pts[POINTS];
  for (int k = 0; k < POINTS; ++k) {
    // Catmull-Rom through the samples.
    const float t = k * (n - 1) / float(POINTS - 1);
    const int i = std::min(n - 2, static_cast<int>(t));
    const float u = t - i;
    auto at = [&](int j) { return s[std::clamp(j, 0, n - 1)]; };
    const float p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
    const float y = 0.5f * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u);
    const float py = b.y + lw / 2.0f + (b.h - lw) * (1 - (y - lo) / (hi - lo));
    pts[k] = {static_cast<lv_value_precise_t>(b.x + lw / 2.0f + (b.w - lw) * t / (n - 1)),
              static_cast<lv_value_precise_t>(std::clamp(py, float(b.y), float(b.bottom())))};
  }
  lv_draw_triangle_dsc_t fill;
  lv_draw_triangle_dsc_init(&fill);
  fill.color = lv_color_hex(c);
  fill.opa = theme::fill_opacity();
  const lv_value_precise_t base = b.bottom();
  for (int k = 0; k + 1 < POINTS; ++k) {
    const auto &a = pts[k], &e = pts[k + 1];
    fill.p[0] = a; fill.p[1] = e; fill.p[2] = {e.x, base};
    lv_draw_triangle(layer, &fill);
    fill.p[1] = fill.p[2]; fill.p[2] = {a.x, base};
    lv_draw_triangle(layer, &fill);
  }
  lv_draw_line_dsc_t line;
  lv_draw_line_dsc_init(&line);
  line.color = lv_color_hex(c);
  line.width = lw;
  line.round_start = line.round_end = 1;
  for (int k = 0; k + 1 < POINTS; ++k) {
    line.p1 = pts[k]; line.p2 = pts[k + 1];
    lv_draw_line(layer, &line);
  }
}

// The whole card at (ox, oy).
inline void paint(lv_layer_t *layer, const Look &v, int ox, int oy) {
  const auto &p = v.plan;
  if (p.ring) paint_ring(layer, v, ox, oy);
  if (p.tape) paint_tape(layer, v, ox, oy);
  if (p.bar) paint_bar(layer, v, ox, oy);
  if (p.graph) paint_graph(layer, v, ox, oy);
  const uint32_t ink = theme::hex(theme::INK), muted = theme::hex(v.background ? theme::SLATE : theme::MUTED);
  for (const auto &t : p.texts) words(layer, t, v.faces[t.face], t.role == mc::INK ? ink : muted, ox, oy);
}
}  // namespace meter_paint
