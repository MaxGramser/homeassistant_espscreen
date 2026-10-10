#pragma once
// The weather card's chart (weather_week.h plans it): the week as day columns in a light grid, or the next hours, drawn
// by one LVGL object in its draw event. The object owns a Chart; set() replaces it and asks for a redraw.
//
// The chart is light to draw: the curve is some fifty short straight strokes, opaque, round only at its two ends,
// each in Home Assistant's temperature hue of its stretch; no fill under it. A redraw is a few dozen texts and strokes, and set() asks for none while the forecast it shows has not changed (Home Assistant sends a weather
// entity's state far more often than its forecast). The plan is worked out once per forecast and size, not per draw.
#include <lvgl.h>

#include "theme.h"
#include "ui_scale.h"
#include "layout_memory.h"
#include "weather_week.h"

namespace weather_chart {
using namespace weather_week;

struct Level { const lv_font_t *name, *icon, *small, *high, *low, *rain; };
struct Fonts {
  std::array<Level, LEVELS> levels{};
  std::array<const lv_font_t *, 3> marks{};  // the icon faces a cloud's drops may take, smallest first
  const lv_font_t *axis = nullptr;           // the hours' times
};
struct Item {
  enum Kind : uint8_t { TEXT, RECT, LINE, DOT } kind = TEXT;
  bool round_start = false, round_end = false;
  lv_opa_t opa = LV_OPA_COVER;
  int16_t x1 = 0, y1 = 0, x2 = 0, y2 = 0;  // its area, relative to the chart
  int16_t lx1 = 0, ly1 = 0, lx2 = 0, ly2 = 0;  // a line's ends
  uint8_t radius = 0, width = 0;
  lv_text_align_t align = LV_TEXT_ALIGN_CENTER;
  uint32_t color = 0;
  const lv_font_t *font = nullptr;
  char text[16] = {};  // the chart's texts are short: a day's name, "-12°", "14.5 mm", a glyph
};
// The parts, PSRAM first and never by an allocation that can throw (layout_memory.h): the Guition's internal RAM is
// tight beside its panel, and an ESP32 build aborts where std::vector would throw.
using Sink = layout_memory::Vector<Item>;
// Adds a part, doubling the room when it is full; false when the board has no memory for it (the chart then draws
// what it has).
inline bool add(Sink &out, const Item &item) {
  if (out.size() == out.capacity()) {
    const size_t n = out.size();
    if (!out.resize(std::max<size_t>(32, n * 2))) return false;
    while (out.size() > n) out.pop_back();
  }
  return out.push_back(item);
}
struct Chart {
  bool hourly = false;
  bool icon_only = false;             // the first day's icon alone, in the largest face (the card's weather now)
  std::vector<Day> days;
  std::vector<Hour> hours;
  std::vector<std::string> weekdays;  // the hours' midnights, Sunday first
  std::string unit;                   // the rain's unit
  bool fahrenheit = false;
  int now = 0;                        // hours since today's midnight
  int today = 0;                      // today's weekday, Sunday 0
  Fonts fonts;
  bool large = true;
  mutable int plan_w = -1, plan_h = -1;  // the size the plan below is for
  mutable Plan plan_;
};
// What a chart object owns: its chart, and the parts built from it for a size and a look.
struct Holder {
  Chart chart;
  Sink items;
  int w = -1, h = -1;
  bool dark = false;
};
// The plan for this size, measured once per forecast and size.
inline const Plan &plan_of(const Chart &c, const Metrics &m, int width, int height) {
  if (c.plan_w != width || c.plan_h != height) { c.plan_ = plan(m, c.days, c.unit, width, height); c.plan_w = width; c.plan_h = height; }
  return c.plan_;
}
// Does `b` draw the same as `a`? Then set() keeps the picture on the glass as it is.
inline bool same(const Chart &a, const Chart &b) {
  auto eq = [](float x, float y) { return (std::isnan(x) && std::isnan(y)) || x == y; };
  if (a.hourly != b.hourly || a.icon_only != b.icon_only || a.unit != b.unit || a.fahrenheit != b.fahrenheit || a.now != b.now ||
      a.today != b.today || a.days.size() != b.days.size() || a.hours.size() != b.hours.size() || a.large != b.large) return false;
  for (size_t i = 0; i < a.days.size(); ++i) {
    const auto &x = a.days[i], &y = b.days[i];
    if (x.name != y.name || x.condition != y.condition || !eq(x.high, y.high) || !eq(x.low, y.low) || !eq(x.mm, y.mm) || !eq(x.chance, y.chance)) return false;
  }
  if (a.hourly)
    for (size_t i = 0; i < a.hours.size(); ++i) {
      const auto &x = a.hours[i], &y = b.hours[i];
      if (x.at != y.at || x.condition != y.condition || !eq(x.temp, y.temp) || !eq(x.mm, y.mm)) return false;
    }
  return true;
}

inline int line_h(const lv_font_t *f) { return f ? lv_font_get_line_height(f) : 0; }
inline int text_w(const std::string &s, const lv_font_t *f) {
  if (!f) return 0;
  lv_point_t size;
  lv_text_get_size(&size, s.c_str(), f, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
  return size.x;
}
inline const lv_font_t *font_of(const Level &l, Role r) {
  switch (r) { case NAME: return l.name; case ICON: return l.icon; case HIGH: return l.high; case LOW: return l.low; default: return l.rain; }
}
inline Metrics metrics(const Fonts &f, bool large) {
  Metrics m;
  m.large = large;
  for (int i = 0; i < LEVELS; ++i)
    for (int r = 0; r < ROLES; ++r) m.h[i][r] = line_h(font_of(f.levels[i], (Role) r));
  const Fonts *fonts = &f;
  m.width = [fonts](int level, Role role, const std::string &s) { return text_w(s, font_of(fonts->levels[level], role)) + 2; };
  return m;
}
inline float celsius(const Chart &c, float v) { return c.fahrenheit ? (v - 32) * 5 / 9 : v; }

// ---- drawing: the chart's parts are worked out once per forecast, size and look (build), as a list of what to
// draw where; a draw only paints the parts that touch the stripe LVGL is rendering. A board with little memory renders
// the glass in a dozen stripes, and the chart's draw event runs for each of them: working it all out every time cost
// the CYD a frame twice as long as any other page.
inline void text(Sink &out, const std::string &s, int x, int y, int w, const lv_font_t *f, uint32_t color,
                 lv_text_align_t align = LV_TEXT_ALIGN_CENTER) {
  if (!f || s.empty()) return;
  Item i;
  i.kind = Item::TEXT; i.font = f; i.color = color; i.align = align;
  snprintf(i.text, sizeof(i.text), "%s", s.c_str());
  i.x1 = x; i.y1 = y; i.x2 = x + std::max(1, w) - 1; i.y2 = y + line_h(f) - 1;
  add(out, i);
}
inline void rect(Sink &out, int x1, int y1, int x2, int y2, uint32_t color, lv_opa_t opa = LV_OPA_COVER, int radius = 0) {
  if (x2 < x1 || y2 < y1 || opa < 2) return;
  Item i;
  i.kind = Item::RECT; i.color = color; i.opa = opa; i.radius = radius; i.x1 = x1; i.y1 = y1; i.x2 = x2; i.y2 = y2;
  add(out, i);
}
// The curve through `ys` (one value per pixel column from x0): straight strokes every few pixels, each in the colour of
// its middle, opaque, round only at the line's two ends.
inline void curve(Sink &out, int x0, const std::vector<float> &ys, const std::vector<uint32_t> &colors, int y0, float lw) {
  const int n = ys.size(), step = std::max(5, (int) ui::px(8)), w = std::max(2, (int) std::lround(lw));
  for (int i = 0; i + 1 < n; i += step) {
    const int j = std::min(n - 1, i + step);
    Item it;
    it.kind = Item::LINE; it.width = w; it.color = colors[(i + j) / 2];
    // Round ends only where the line starts and stops: at two or three pixels the joins do not show.
    it.round_start = i == 0; it.round_end = j == n - 1;
    it.lx1 = x0 + i; it.ly1 = y0 + (int) std::lround(ys[i]);
    it.lx2 = x0 + j; it.ly2 = y0 + (int) std::lround(ys[j]);
    it.x1 = std::min(it.lx1, it.lx2) - w; it.y1 = std::min(it.ly1, it.ly2) - w;
    it.x2 = std::max(it.lx1, it.lx2) + w; it.y2 = std::max(it.ly1, it.ly2) + w;
    if (!add(out, it)) return;
  }
}
inline void dot(Sink &out, float x, float y, int r, uint32_t color) {
  Item i;
  const int cx = (int) std::lround(x), cy = (int) std::lround(y);
  i.kind = Item::DOT; i.color = color; i.radius = r; i.x1 = cx - r; i.y1 = cy - r; i.x2 = cx + r; i.y2 = cy + r;
  add(out, i);
}
// Paints the items that touch the layer's clip area, `x`/`y` the chart's place on the glass.
inline void paint(lv_layer_t *layer, const Sink &items, int x, int y) {
  const lv_area_t clip = layer->_clip_area;
  for (const auto &i : items) {
    lv_area_t a{i.x1 + x, i.y1 + y, i.x2 + x, i.y2 + y};
    if (a.x2 < clip.x1 || a.x1 > clip.x2 || a.y2 < clip.y1 || a.y1 > clip.y2) continue;
    switch (i.kind) {
      case Item::TEXT: {
        lv_draw_label_dsc_t d;
        lv_draw_label_dsc_init(&d);
        d.font = i.font; d.color = lv_color_hex(i.color); d.text = i.text; d.align = i.align;
        lv_draw_label(layer, &d, &a);
        break;
      }
      case Item::RECT: {
        lv_draw_rect_dsc_t d;
        lv_draw_rect_dsc_init(&d);
        d.bg_color = lv_color_hex(i.color); d.bg_opa = i.opa; d.radius = i.radius;
        lv_draw_rect(layer, &d, &a);
        break;
      }
      case Item::LINE: {
        lv_draw_line_dsc_t d;
        lv_draw_line_dsc_init(&d);
        d.width = i.width; d.color = lv_color_hex(i.color); d.round_start = i.round_start; d.round_end = i.round_end;
        d.p1 = {(lv_value_precise_t) (i.lx1 + x), (lv_value_precise_t) (i.ly1 + y)};
        d.p2 = {(lv_value_precise_t) (i.lx2 + x), (lv_value_precise_t) (i.ly2 + y)};
        lv_draw_line(layer, &d);
        break;
      }
      case Item::DOT: {
        lv_draw_rect_dsc_t d;
        lv_draw_rect_dsc_init(&d);
        d.bg_color = lv_color_hex(i.color); d.bg_opa = LV_OPA_COVER; d.radius = LV_RADIUS_CIRCLE;
        d.border_color = lv_color_hex(theme::hex(theme::CARD)); d.border_width = std::max(2, i.radius / 2);
        lv_draw_rect(layer, &d, &a);
        break;
      }
    }
  }
}

// ---- icons: a condition as Home Assistant's weather pictures draw it, from a few MDI glyphs: a cloud in front, a sun
// or a second cloud behind it, and what falls out of it (drops, flakes, a bolt) in a face at most two fifths of the
// cloud's. Where the board has no such face, the single glyph of the condition in its colour (the tile's own icon).
inline const char *glyph(const std::string &c) {
  if (c == "sunny") return "\U000F0599";
  if (c == "clear-night") return "\U000F0594";
  if (c == "cloudy") return "\U000F0590";
  if (c == "partlycloudy") return "\U000F0595";
  if (c == "rainy") return "\U000F0597";
  if (c == "pouring") return "\U000F0596";
  if (c == "snowy") return "\U000F0598";
  if (c == "snowy-rainy") return "\U000F067F";
  if (c == "fog") return "\U000F0591";
  if (c == "hail") return "\U000F0592";
  if (c == "lightning" || c == "lightning-rainy") return "\U000F0593";
  if (c == "windy" || c == "windy-variant") return "\U000F059D";
  return "\U000F05D6";
}
inline uint32_t hue(const std::string &c) {
  namespace h = theme::ha;
  if (c == "sunny") return h::SUNNY;
  if (c == "clear-night") return h::NIGHT_SKY;
  if (c == "partlycloudy") return h::PARTLY_CLOUDY;
  if (c == "rainy" || c == "pouring") return h::RAIN;
  if (c == "snowy" || c == "snowy-rainy" || c == "hail") return h::SNOW;
  if (c == "lightning" || c == "lightning-rainy") return h::LIGHTNING;
  return h::CLOUDY;
}
inline bool falls(const std::string &c) {
  return c == "rainy" || c == "pouring" || c == "snowy" || c == "snowy-rainy" || c == "hail" || c == "lightning" || c == "lightning-rainy";
}
inline const lv_font_t *mark_font(const Fonts &f, const lv_font_t *big) {
  const lv_font_t *best = nullptr;
  for (auto *m : f.marks)
    if (m && line_h(m) * 100 <= line_h(big) * 42 && (!best || line_h(m) > line_h(best))) best = m;
  return best;
}
// Can every condition of a row be drawn two-tone in `big`? One style per row: else all of it single glyphs.
inline bool two_tone(const Fonts &f, const lv_font_t *big, const std::vector<std::string> &conditions) {
  if (mark_font(f, big)) return true;
  for (auto &c : conditions) if (falls(c)) return false;
  return true;
}
inline void icon(Sink &layer, const Fonts &f, const std::string &c, int cx, int y, const lv_font_t *big, const lv_font_t *small, bool tone) {
  const int b = line_h(big), x = cx - b / 2;
  namespace h = theme::ha;
  auto gl = [&](const char *g, int gx, int gy, const lv_font_t *font, uint32_t color) {
    text(layer, g, gx, gy, line_h(font) * 3 / 2, font, color, LV_TEXT_ALIGN_LEFT);
  };
  if (!tone || c == "fog" || c == "windy" || c == "windy-variant" || c == "exceptional") {
    gl(tone ? glyph(c) : glyph(c), x, y, big, tone ? theme::hex(theme::WEATHER_CLOUD_BACK) : theme::foreground(hue(c)));
    return;
  }
  const char *CLOUD = "\U000F0590", *SUN = "\U000F0599", *MOON = "\U000F0594", *DROP = "\U000F058C", *FLAKE = "\U000F0717", *BOLT = "\U000F0241";
  if (c == "sunny") { gl(SUN, x, y, big, theme::foreground(h::SUNNY)); return; }
  if (c == "clear-night") { gl(MOON, x, y, big, theme::foreground(h::NIGHT_SKY)); return; }
  const int s = line_h(small);
  const lv_font_t *mf = falls(c) ? mark_font(f, big) : nullptr;
  const int m = mf ? line_h(mf) : 0, lift = m * 2 / 3;
  if (c == "partlycloudy") gl(SUN, x + b / 2 - s / 8, y - s / 10, small, theme::foreground(h::SUNNY));
  if (c == "cloudy") gl(CLOUD, x + b / 2 - s / 6, y - s / 12, small, theme::hex(theme::WEATHER_CLOUD_BACK));
  gl(CLOUD, x, y + (c == "partlycloudy" || c == "cloudy" ? b / 12 : 0) - lift, big, theme::hex(theme::WEATHER_CLOUD));
  if (!mf) return;
  const int below = y + b - lift - m / 2, step = m * 3 / 4;
  auto mark = [&](const char *g, uint32_t color, int dx) { gl(g, cx - m / 2 + dx, below, mf, color); };
  const uint32_t rain = theme::foreground(h::RAIN), snow = theme::foreground(h::SNOW);
  if (c == "lightning" || c == "lightning-rainy") {
    mark(BOLT, theme::foreground(h::LIGHTNING), c == "lightning" ? 0 : -step / 2);
    if (c != "lightning") mark(DROP, rain, step * 3 / 4);
    return;
  }
  if (c == "pouring") { mark(DROP, rain, -step); mark(DROP, rain, 0); mark(DROP, rain, step); return; }
  if (c == "snowy") { mark(FLAKE, snow, -step / 2); mark(FLAKE, snow, step / 2); return; }
  if (c == "snowy-rainy") { mark(DROP, rain, -step / 2); mark(FLAKE, snow, step / 2); return; }
  if (c == "hail") { mark(FLAKE, snow, -step / 2); mark(DROP, rain, step / 2); return; }
  mark(DROP, rain, -step / 2);
  mark(DROP, rain, step / 2);
}

// ---- the week
inline void draw_week(Sink &layer, const lv_area_t &area, const Chart &c) {
  const int width = lv_area_get_width(&area), height = lv_area_get_height(&area);
  const Metrics m = metrics(c.fonts, c.large);
  const Plan p = plan_of(c, m, width, height);
  if (!p.ok()) return;
  const Place r = place(m, p, height);
  const Level &l = c.fonts.levels[p.level];
  const int cw = width / p.cols, x0 = area.x1 + (width - cw * p.cols) / 2, x1 = x0 + cw * p.cols, y0 = area.y1;
  const int inset = ui::px(p.level > 1 ? 8 : 5);
  const uint32_t ink = theme::hex(theme::INK), muted = theme::hex(theme::MUTED);
  const uint32_t rule = theme::hex(theme::dark ? theme::RAISED_LINE : theme::LINE);
  // The light grid: a line under the icons and one over the rain, short of the card's sides, and a line between
  // every two days from the first line to the foot of the last row of numbers.
  if (r.rule1 >= 0) rect(layer, x0 + inset, y0 + r.rule1, x1 - inset - 1, y0 + r.rule1, rule);
  if (r.rule2 >= 0) rect(layer, x0 + inset, y0 + r.rule2, x1 - inset - 1, y0 + r.rule2, rule);
  // A card of one row has no line across: its lines between the days run the height of the days.
  const int head = r.rule1 >= 0 ? r.rule1 : r.name, foot = r.bar >= 0 ? r.bar + r.bar_h : r.words >= 0 ? r.words + m.h[p.level][RAIN] : r.low + m.h[p.level][r.rule1 >= 0 ? LOW : HIGH];
  for (int k = 1; k < p.cols; ++k) rect(layer, x0 + k * cw, y0 + head, x0 + k * cw, y0 + foot, rule);
  std::vector<std::string> conds;
  for (int k = 0; k < p.cols; ++k) conds.push_back(c.days[k].condition);
  const bool tone = two_tone(c.fonts, l.icon, conds);
  float most = c.unit == "in" ? 0.4f : 10;
  for (int k = 0; k < p.cols; ++k) if (std::isfinite(c.days[k].mm)) most = std::max(most, c.days[k].mm);
  for (int k = 0; k < p.cols; ++k) {
    const auto &d = c.days[k];
    const int x = x0 + k * cw;
    text(layer, d.name, x, y0 + r.name, cw, l.name, k ? muted : ink);
    icon(layer, c.fonts, d.condition, x + cw / 2, y0 + r.icon, l.icon, l.small, tone);
    if (p.tier == 0) {
      // the high in its face and the low beside it in the smaller one, on one baseline
      const std::string hi = degrees(d.high), lo = degrees(d.low);
      const int hw = text_w(hi, l.high), lw = text_w(lo, l.low), gap = pair_gap(p.level), sx = x + (cw - hw - gap - lw) / 2;
      const int drop = (l.high->line_height - l.high->base_line) - (l.low->line_height - l.low->base_line);
      text(layer, hi, sx, y0 + r.high, hw + 2, l.high, ink, LV_TEXT_ALIGN_LEFT);
      text(layer, lo, sx + hw + gap, y0 + r.high + drop, lw + 2, l.low, muted, LV_TEXT_ALIGN_LEFT);
      if (r.words >= 0) text(layer, rain_words(d, c.unit), x, y0 + r.words, cw, l.rain, theme::foreground(theme::ha::RAIN));
      continue;
    }
    text(layer, degrees(d.high), x, y0 + r.high, cw, l.high, ink);
    text(layer, degrees(d.low), x, y0 + r.low, cw, l.low, muted);
    if (r.bar >= 0 && wet(d.mm, c.unit)) {
      // A flat bar hung from the line, nearly the column's width, as long as the day is wet on one scale for the week
      // (10 mm at least), never thinner than a stroke; the amount under it in ink.
      const int bh = std::max(ui::px(3), (int) std::lround(r.bar_h * d.mm / most)), pad = ui::px(p.level > 1 ? 6 : 4);
      rect(layer, x + pad, y0 + r.bar, x + cw - pad - 1, y0 + r.bar + bh - 1, theme::foreground(theme::ha::RAIN));
      text(layer, amount(d.mm, c.unit), x, y0 + r.rain, cw, l.rain, ink);
    }
    if (r.words >= 0) text(layer, rain_words(d, c.unit), x, y0 + r.words, cw, l.rain, theme::foreground(theme::ha::RAIN));
    if (r.chance >= 0 && std::isfinite(d.chance)) {
      char b[8];
      snprintf(b, sizeof(b), "%.0f%%", d.chance);
      text(layer, b, x, y0 + r.chance, cw, l.rain, muted);
    }
  }
  if (p.tier < 2) return;
  // The temperature through the week on one scale, from now to the end of the last column.
  const int last = 24 * p.cols;
  float lo = INFINITY, hi = -INFINITY;
  for (int h = c.now; h <= last; ++h) {
    const float v = through(c.days, c.hours, h);
    if (std::isfinite(v)) { lo = std::min(lo, v); hi = std::max(hi, v); }
  }
  if (!std::isfinite(lo)) return;
  const float lw = std::max(1.5f, ui::px(p.level > 1 ? 5 : 4) / 2.f), in = lw + ui::px(4), span = std::max(1.f, hi - lo);
  const int fx = (int) std::ceil(x0 + c.now * cw / 24.f);
  std::vector<float> ys;
  std::vector<uint32_t> colors;
  for (int x = fx; x < x1; ++x) {
    const float v = through(c.days, c.hours, std::max<float>(c.now, (x - x0) * 24.f / cw));
    ys.push_back(r.curve + in + (r.curve_h - 2 * in) * (hi - v) / span);
    colors.push_back(theme::foreground(theme::temperature(celsius(c, v))));
  }
  if (ys.empty()) return;
  curve(layer, fx, ys, colors, y0, lw);
  dot(layer, fx, y0 + ys.front(), ui::px(p.level > 1 ? 5 : 4), colors.front());
}

// ---- the next hours: their condition and temperature every few clock hours, one curve, rain per hour, a time axis
inline int hours_need(const Fonts &f) {
  const Level &l = f.levels[1];
  return line_h(l.icon) + line_h(l.high) + line_h(f.axis) + ui::px(8) + 4 * ui::px(4) + ui::px(40);
}
inline void draw_hours(Sink &layer, const lv_area_t &area, const Chart &c) {
  const int n = std::min<int>(HOURS, c.hours.size());
  if (n < 4) return;
  const int width = lv_area_get_width(&area), height = lv_area_get_height(&area), y0 = area.y1, gap = ui::px(4);
  const float slot = float(width) / n;
  // The largest face whose labels fit their stretch of hours; marks on whole clock hours (00, 03, 06 ...).
  int level = 2, step = 3;
  for (; level >= 1; --level) {
    const Level &l = c.fonts.levels[level];
    bool fits = false;
    for (int k : {3, 4, 6, 12}) {
      const int need = std::max({text_w("00:00", c.fonts.axis), text_w("-12°", l.high), line_h(l.icon) * 5 / 4}) + ui::px(8);
      if (slot * k >= need) { step = k; fits = true; break; }
    }
    if (fits && line_h(l.icon) + line_h(l.high) + ui::px(12) + line_h(c.fonts.axis) + 4 * gap + ui::px(30) <= height) break;
  }
  level = std::max(level, 1);
  const Level &l = c.fonts.levels[level];
  const int bar = ui::px(level > 1 ? 12 : 8), axis = line_h(c.fonts.axis), rs = ui::px(level > 1 ? 6 : 3);
  const int curve_h = height - (line_h(l.icon) + line_h(l.high) + 2 * rs + 1 + gap + rs + 1 + bar + gap + axis);
  if (curve_h < ui::px(20)) return;
  // The same light grid as the week: a line under the temperatures, one over the rain, one between every two marks.
  const int icon_y = y0, high_y = icon_y + line_h(l.icon), rule1 = high_y + line_h(l.high) + rs, curve_y = rule1 + 1 + rs;
  const int rule2 = curve_y + curve_h + gap, bar_y = rule2 + 1, axis_y = bar_y + bar + gap;
  std::vector<float> t(n);
  for (int i = 0; i < n; ++i) {
    float sum = 0, w = 0;
    for (int j = -2; j <= 2; ++j) {
      const float v = c.hours[std::clamp(i + j, 0, n - 1)].temp, wt = 3 - std::abs(j);
      if (std::isfinite(v)) { sum += wt * v; w += wt; }
    }
    t[i] = w > 0 ? sum / w : NAN;
  }
  float lo = INFINITY, hi = -INFINITY, most = c.unit == "in" ? 0.08f : 2;
  for (int i = 0; i < n; ++i) {
    if (std::isfinite(t[i])) { lo = std::min(lo, t[i]); hi = std::max(hi, t[i]); }
    if (std::isfinite(c.hours[i].mm)) most = std::max(most, c.hours[i].mm);
  }
  if (!std::isfinite(lo)) return;
  const float lw = std::max(1.5f, ui::px(level > 1 ? 5 : 4) / 2.f), in = lw + ui::px(4), span = std::max(1.f, hi - lo);
  const uint32_t ink = theme::hex(theme::INK), muted = theme::hex(theme::MUTED);
  const uint32_t rule = theme::hex(theme::dark ? theme::RAISED_LINE : theme::LINE);
  const int inset = ui::px(level > 1 ? 8 : 5);
  rect(layer, area.x1 + inset, rule1, area.x2 - inset, rule1, rule);
  rect(layer, area.x1 + inset, rule2, area.x2 - inset, rule2, rule);
  std::vector<float> ys;
  std::vector<uint32_t> colors;
  const int fx = area.x1 + (int) std::lround(slot / 2), ex = area.x1 + (int) std::lround(slot * (n - 0.5f));
  for (int x = fx; x <= ex; ++x) {
    const float u = (x - area.x1) / slot - 0.5f;
    const int i = std::clamp((int) u, 0, n - 2);
    const float v = t[i] + (t[i + 1] - t[i]) * ease(std::clamp(u - i, 0.f, 1.f));
    ys.push_back(curve_y - y0 + in + (curve_h - 2 * in) * (hi - v) / span);
    colors.push_back(theme::foreground(theme::temperature(celsius(c, v))));
  }
  std::vector<std::string> conds;
  for (int i = 0; i < n; ++i) conds.push_back(c.hours[i].condition);
  const bool tone = two_tone(c.fonts, l.icon, conds);
  for (int i = 0; i < n; ++i) {
    const auto &h = c.hours[i];
    const int x = area.x1 + (int) (slot * i);
    if (wet(h.mm, c.unit)) {
      const int bh = std::max(ui::px(2), (int) std::lround(bar * h.mm / most)), bw = std::max(2, (int) slot - ui::px(2));
      rect(layer, x + ((int) slot - bw) / 2, bar_y + bar - bh, x + ((int) slot - bw) / 2 + bw - 1, bar_y + bar - 1, theme::foreground(theme::ha::RAIN), LV_OPA_COVER, ui::px(1));
    }
    const int hour = ((h.at % 24) + 24) % 24;
    // a line halfway between two marks, from the first line to the foot of the rain
    if (i && (hour + step / 2) % step == 0 && hour % step) rect(layer, x, rule1, x, bar_y + bar, rule);
    if (hour % step || i == 0) continue;
    const int span_w = (int) (slot * step), cx = x + (int) (slot / 2), lx = std::clamp(cx - span_w / 2, (int) area.x1, (int) area.x2 + 1 - span_w);
    if (cx - line_h(l.icon) / 2 < area.x1 || cx + line_h(l.icon) / 2 > area.x2) continue;
    icon(layer, c.fonts, h.condition, cx, icon_y, l.icon, l.small, tone);
    text(layer, degrees(t[i]), lx, high_y, span_w, l.high, ink);
    char b[8];
    snprintf(b, sizeof(b), "%02d:00", hour);
    const bool midnight = hour == 0 && !c.weekdays.empty();
    text(layer, midnight ? c.weekdays[(c.today + h.at / 24) % 7] : std::string(b), lx, axis_y, span_w, c.fonts.axis, midnight ? ink : muted);
  }
  curve(layer, fx, ys, colors, y0, lw);
  dot(layer, fx, y0 + ys.front(), ui::px(level > 1 ? 5 : 4), colors.front());
}

// ---- the object
inline void draw_event(lv_event_t *e) {
  auto *obj = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *k = static_cast<Holder *>(lv_obj_get_user_data(obj));
  if (!k) return;
  lv_area_t a;
  lv_obj_get_coords(obj, &a);
  const int w = lv_area_get_width(&a), h = lv_area_get_height(&a);
  if (k->w != w || k->h != h || k->dark != theme::dark) {
    const Chart &c = k->chart;
    k->items.clear();
    const lv_area_t local{0, 0, w - 1, h - 1};
    if (c.icon_only) {
      if (!c.days.empty()) {
        const Level &l = c.fonts.levels[LEVELS - 1];
        icon(k->items, c.fonts, c.days[0].condition, w / 2, 0, l.icon, l.small, two_tone(c.fonts, l.icon, {c.days[0].condition}));
      }
    } else if (c.hourly) draw_hours(k->items, local, c);
    else draw_week(k->items, local, c);
    k->w = w; k->h = h; k->dark = theme::dark;
  }
  paint(lv_event_get_layer(e), k->items, a.x1, a.y1);
}
inline void delete_event(lv_event_t *e) {
  auto *obj = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  delete static_cast<Holder *>(lv_obj_get_user_data(obj));
  lv_obj_set_user_data(obj, nullptr);
}
inline lv_obj_t *create(lv_obj_t *parent) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_user_data(o, new (std::nothrow) Holder());
  lv_obj_add_event_cb(o, draw_event, LV_EVENT_DRAW_MAIN, nullptr);
  lv_obj_add_event_cb(o, delete_event, LV_EVENT_DELETE, nullptr);
  return o;
}
inline void set(lv_obj_t *o, Chart &&chart) {
  auto *k = static_cast<Holder *>(lv_obj_get_user_data(o));
  if (!k) return;
  if (same(k->chart, chart)) return;  // nothing new to draw: the forecast and the hour are as they were
  k->chart = std::move(chart);
  k->w = -1;                          // build the parts again at the next draw
  lv_obj_invalidate(o);
}
// The tier the week reaches in this room, -1 where it shows nothing: the card around it decides with it.
inline int week_tier(const Chart &c, int width, int height) {
  const Metrics m = metrics(c.fonts, c.large);
  const Plan &p = plan_of(c, m, width, height);
  return p.ok() ? p.tier : -1;
}

}  // namespace weather_chart
