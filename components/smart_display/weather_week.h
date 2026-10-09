#pragma once
// The weather card's week and its next hours (design study 10-09, tools/render/weather_study.h): day columns in a
// light grid over one chart, drawn by one LVGL object.
//
// What a chart shows follows its room, in fixed tiers; a bigger card shows more, never the same things larger first:
//   0  a card of one row: name, icon, and the high and the low on one line, in the same grid
//   1  the days: name, icon, high, low
//   2  + the temperature as a line through the week
//   3  + the rain as a second row (a flat bar per wet day hung from a line, the amount under it)
//   4  + the chance of rain, where the provider gives one
// The highest tier that fits at the smallest face wins, then the largest face that keeps it. Every day the forecast
// has (up to seven) comes before either: a narrow card drops days only when the smallest face cannot hold them.
//
// One object draws the whole chart in its draw event: names, icons, numbers, the curve, the bars and the grid. A week
// of seven days is some sixty strings; as labels that is sixty objects per card, which the CYD cannot spare. The object
// owns what it draws (a Chart on the heap, freed with the object), so nothing in it points into the model or at a
// card slot that kept pages may swap (the firmware 0.3.6 crash). `plan()` is arithmetic on measured numbers, free of
// LVGL objects: tests/test_weather_week.cpp checks it.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

#include "ui_scale.h"

namespace weather_week {

constexpr int DAYS = 7;
// The hours a screen keeps: two days where PSRAM holds them, one on the boards without.
#ifdef USE_PSRAM
constexpr int HOURS = 48;
#else
constexpr int HOURS = 24;
#endif

struct Day {
  std::string name, condition;  // name: what the column says ("Today", "Sat")
  float high = NAN, low = NAN, mm = NAN, chance = NAN;
};
struct Hour {
  int at = 0;                    // hours since today's midnight, local time
  std::string condition;
  float temp = NAN, mm = NAN;
};

// ---- the plan: pure arithmetic --------------------------------------------------------------------------------------

// The faces of one size step: the day's name, its icon, the marks under a cloud, the high, the low, the rain's words.
enum Role : unsigned char { NAME, ICON, HIGH, LOW, RAIN, ROLES };
constexpr int LEVELS = 4;  // 0: tight (the icon in its smallest face), 1: the board's small step, 2, 3: larger
struct Metrics {
  std::array<std::array<int, ROLES>, LEVELS> h{};  // line heights per level and role
  // width of a text in a level's role: the caller measures with the board's fonts
  std::function<int(int level, Role role, const std::string &text)> width;
  bool large = true;
};
struct Rows { int pp, g, rs, bar; };  // the air above and under the days, a gap, the room around a line, the rain bars' height
inline Rows rows_of(int level, bool large) {
  const int n = level - 1;  // -1 tight, 0 small, 1, 2
  (void) large;
  // The grid frames the days, so they need no air of their own above and under them (a pill around today did).
  return {0, ui::px(n >= 2 ? 8 : n > 0 ? 5 : 3), ui::px(n > 0 ? 8 : 3), ui::px(n >= 2 ? 24 : n > 0 ? 18 : 12)};
}
inline int curve_min(const Metrics &m, int level) {
  return std::max(ui::px(m.large ? 30 : 22), m.h[level][HIGH] * 3 / 2);
}
struct Plan {
  int level = -1, cols = 0, tier = 0;
  bool chance = false;
  bool words = false;  // below the rain row's tier: one line of the chance (or the amount) on a wet day
  bool ok() const { return level >= 0; }
};
// Everything but the curve's growth, for a plan.
inline int fixed_height(const Metrics &m, const Plan &p) {
  const auto &h = m.h[p.level];
  const Rows w = rows_of(p.level, m.large);
  if (p.tier == 0) return 2 * w.pp + h[NAME] + w.g + h[ICON] + w.g + h[HIGH] + (p.words ? h[RAIN] : 0);
  int y = 2 * w.pp + h[NAME] + w.g + h[ICON] + h[HIGH] + h[LOW];
  y += 2 * w.rs + 1;                                  // the grid's line under the icons
  if (p.tier >= 2) y += curve_min(m, p.level);
  if (p.tier >= 3) y += w.rs + 1 + w.bar + w.g + h[RAIN];
  if (p.chance) y += h[RAIN];
  if (p.words) y += h[RAIN];
  return y;
}
inline std::string degrees(float v) {
  if (!std::isfinite(v)) return "--";
  char b[16];
  snprintf(b, sizeof(b), "%.0f°", v);
  return std::string(b) == "-0°" ? "0°" : b;
}
// "5.5 mm", "14 mm", "0.2 in": the provider's unit, one decimal under ten.
inline std::string amount(float v, const std::string &unit) {
  char b[24];
  const bool inches = unit == "in";
  if (v < (inches ? 1 : 10) && std::fabs(v - std::round(v)) >= 0.05f) snprintf(b, sizeof(b), inches ? "%.2f" : "%.1f", v);
  else snprintf(b, sizeof(b), "%.0f", v);
  return std::string(b) + " " + (unit.empty() ? "mm" : unit);
}
inline bool wet(float mm, const std::string &unit) { return std::isfinite(mm) && mm >= (unit == "in" ? 0.005f : 0.1f); }
// The rain's line below the rain row's tier: the chance where the provider gives one and it is worth saying (30 % or
// more, as the forecast tile has always said it), else the amount on a wet day; "" on a dry day.
inline std::string rain_words(const Day &d, const std::string &unit) {
  if (std::isfinite(d.chance)) {
    if (d.chance < 30) return "";
    char b[8];
    snprintf(b, sizeof(b), "%.0f%%", d.chance);
    return b;
  }
  return wet(d.mm, unit) ? amount(d.mm, unit) : "";
}
// The width a column needs at a level: its widest text, an icon and a quarter, the pill's padding on both sides.
inline int pair_gap(int level) { return ui::px(level > 1 ? 4 : 2); }
inline int column_need(const Metrics &m, const std::vector<Day> &days, int cols, int tier, int level, const std::string &unit) {
  int w = m.h[level][ICON] * 5 / 4;
  for (int k = 0; k < cols; ++k) {
    const auto &d = days[k];
    w = std::max({w, m.width(level, NAME, d.name), m.width(level, HIGH, degrees(d.high)), m.width(level, LOW, degrees(d.low))});
    if (tier == 0) w = std::max(w, m.width(level, HIGH, degrees(d.high)) + pair_gap(level) + m.width(level, LOW, degrees(d.low)));
    if (tier >= 3 && wet(d.mm, unit)) w = std::max(w, m.width(level, RAIN, amount(d.mm, unit)));
    if (tier < 3) w = std::max(w, m.width(level, RAIN, rain_words(d, unit)));
  }
  return w + 2 * ui::px(tier == 0 ? 3 : level > 1 ? 8 : 5);
}
inline Plan plan(const Metrics &m, const std::vector<Day> &days, const std::string &unit, int width, int height) {
  int cols = std::min<int>(DAYS, days.size());
  if (cols < 2) return {};
  const int all = cols;  // a card of one row may hold more narrow columns than the tiers above
  while (cols > 4 && column_need(m, days, cols, 3, 1, unit) * cols > width) --cols;
  bool rain = false, chance = false;
  for (int k = 0; k < cols; ++k) {
    rain |= wet(days[k].mm, unit);
    chance |= std::isfinite(days[k].chance);
  }
  // The order a card gives things up: the chance, then the rain's row, then the line through the week; the rain's
  // words come before the line (a small card says it will rain before it draws the shape of the week).
  bool says = false;
  for (int k = 0; k < cols; ++k) says |= !rain_words(days[k], unit).empty();
  // A card of one row: the days with the high and the low on one line, as many as fit (two at least).
  auto one_row = [&](bool with) -> Plan {
    for (int c = all; c >= 2; --c)
      for (int level = 2; level >= 0; --level) {
        bool any = false;
        for (int k = 0; k < c; ++k) any |= !rain_words(days[k], unit).empty();
        if (with && !any) continue;
        Plan p{level, c, 0, false, with};
        if (column_need(m, days, c, 0, level, unit) * c > width || fixed_height(m, p) > height) continue;
        if (level > 1 && fixed_height(m, p) > height * 3 / 4) continue;
        return p;
      }
    return {};
  };
  struct Step { int tier; bool words; };
  // tier 0 is the one-row form; its words step comes before the curve or the rows without rain
  const Step steps[] = {{4, false}, {3, false}, {2, true}, {1, true}, {0, true}, {2, false}, {1, false}, {0, false}};
  for (const Step &st : steps) {
    if (st.tier >= 3 && !rain && !chance) continue;  // a dry week has no rain row to show
    if (st.tier == 4 && !chance) continue;
    if (st.words && !says) continue;
    if (st.tier == 0) {
      const Plan p = one_row(st.words);
      if (p.ok()) return p;
      continue;
    }
    for (int level = LEVELS - 1; level >= (st.tier == 1 ? 0 : 1); --level) {
      Plan p{level, cols, st.tier, st.tier >= 4, st.words};
      if (column_need(m, days, cols, st.tier, level, unit) * cols > width) continue;
      const int fixed = fixed_height(m, p);
      if (fixed > height) continue;
      if (level > 1 && fixed > height * 3 / 4) continue;  // a larger face only where the card keeps air around it
      return p;
    }
  }
  return {};
}
// Where the rows of a plan go in a chart of `height` (y from the chart's top).
struct Place { int top, bottom, name, icon, rule1, high, curve, curve_h, low, rule2, bar, bar_h, rain, chance, words; };
inline Place place(const Metrics &m, const Plan &p, int height) {
  const auto &h = m.h[p.level];
  const Rows w = rows_of(p.level, m.large);
  const int fixed = fixed_height(m, p);
  int left = height - fixed, curve = p.tier >= 2 ? curve_min(m, p.level) : 0;
  // The room left goes to the curve first, up to three tenths of the card and three times the digits above it; what
  // is left after that is air above and under the whole.
  if (p.tier >= 2) {
    const int more = std::max(0, std::min({left, height * 3 / 10 - curve, 3 * h[HIGH] - curve}));
    curve += more;
    left -= more;
  }
  Place r{};
  r.top = left / 2;
  int y = r.top + w.pp;
  r.name = y; y += h[NAME] + w.g;
  r.icon = y; y += h[ICON];
  if (p.tier == 0) {
    r.rule1 = r.rule2 = r.bar = r.rain = r.chance = -1;
    y += w.g; r.high = r.low = y; y += h[HIGH];
    r.curve = y; r.curve_h = r.bar_h = 0;
    r.words = p.words ? y : -1;
    if (p.words) y += h[RAIN];
    r.bottom = y + w.pp;
    return r;
  }
  r.rule1 = y + w.rs; y += 2 * w.rs + 1;
  r.high = y; y += h[HIGH];
  r.curve = y; r.curve_h = curve; y += curve;
  r.low = y; y += h[LOW];
  r.rule2 = r.bar = r.rain = -1; r.bar_h = 0;
  if (p.tier >= 3) { r.rule2 = y + w.rs; y += w.rs + 1; r.bar = y; r.bar_h = w.bar; y += w.bar + w.g; r.rain = y; y += h[RAIN]; }
  r.chance = p.chance ? y : -1;
  if (p.chance) y += h[RAIN];
  r.words = p.words ? y : -1;
  if (p.words) y += h[RAIN];
  r.bottom = y + w.pp;
  return r;
}

// ---- the temperature through the week ------------------------------------------------------------------------------
// Home Assistant's hourly forecast where it has one (softened over seven hours, sampled every third: a provider's
// whole degrees read as steps), then a day's low at five in the morning and its high at three in the afternoon,
// joined by half cosines (the shape of a real day). The two meet over twelve hours.
inline float ease(float t) { return (1 - std::cos(t * 3.14159265f)) / 2; }
inline float through(const std::vector<Day> &days, const std::vector<Hour> &hours, float h) {
  float v = NAN;
  if (!days.empty()) {
    auto anchor = [&](int i) -> std::pair<float, float> {
      const int k = i / 2;
      if (k >= (int) days.size()) return {24.f * days.size() + 5, days.back().low};
      return i % 2 ? std::pair<float, float>{24.f * k + 15, days[k].high} : std::pair<float, float>{24.f * k + 5, days[k].low};
    };
    const int n = 2 * days.size() + 1;
    v = anchor(0).second;
    if (h >= anchor(n - 1).first) v = anchor(n - 1).second;
    for (int i = 0; i + 1 < n; ++i) {
      const auto a = anchor(i), b = anchor(i + 1);
      if (h >= a.first && h < b.first) { v = a.second + (b.second - a.second) * ease((h - a.first) / (b.first - a.first)); break; }
    }
  }
  if (hours.size() >= 4) {
    const int n = hours.size();
    const float first = hours.front().at, last = hours.back().at;
    auto soft = [&](int i) {
      float sum = 0, w = 0;
      for (int j = -3; j <= 3; ++j) {
        const float t = hours[std::clamp(i + j, 0, n - 1)].temp, wt = 4 - std::abs(j);
        if (std::isfinite(t)) { sum += wt * t; w += wt; }
      }
      return w > 0 ? sum / w : NAN;
    };
    auto at = [&](float x) {
      const float u = (std::clamp(x, first, last) - first) / 3;
      const int i = std::clamp((int) u, 0, std::max(0, (n - 1) / 3 - 1));
      const float a = soft(3 * i), b = soft(std::min(n - 1, 3 * i + 3));
      return a + (b - a) * ease(std::clamp(u - i, 0.f, 1.f));
    };
    if (h >= first && h <= last) return at(h);
    if (h > last && h < last + 12 && std::isfinite(v)) { const float t = (h - last) / 12, k = t * t * (3 - 2 * t); return at(last) * (1 - k) + v * k; }
    if (!std::isfinite(v)) return at(h);
  }
  return v;
}

}  // namespace weather_week
