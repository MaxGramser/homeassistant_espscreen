#pragma once
// The energy card (firmware 0.47.0): Home Assistant's energy distribution card, live, as power-flow-card-plus draws
// it. Solar on top, the grid at the left, the house at the right, the battery below, the house's devices in a column
// beside the house; a 1 px line between every pair that can exchange power, a dot running along each line that
// carries it (faster for more power), and a ring round the house in the shares of what feeds it. On a tall, narrow
// card the same picture turns a quarter (the grid on top, the house below), the words upright.
//
// Where everything goes, and in which of the board's fonts. Pure arithmetic, free of LVGL and ESPHome, so
// tests/test_energy_card.cpp checks every board shape on a PC; energy_view.cpp measures the text and paints the
// Scene this builds. The numbers come from the add-on, which splits the moment as Home Assistant's own live view does
// (screen_manager/app/energy_flow.py).
//
// The card takes the richest form its room holds, giving up one thing at a time (docs/ENERGY.md):
//   0. everything: names, both directions of the grid and the battery with their arrows;
//   1. only the direction that flows;  2. without the arrows (the colour says the direction);
//   3. without names (the icon says what it is);  5. one line per circle;
//   6. compact: the icon alone in a smaller circle, the number where the name was, no devices;
//   7. one line per circle and 8. compact, both without the battery's charge (its glyph still shows it).
// The battery's charge stands beside its glyph, as Home Assistant's energy distribution card puts it; in the compact
// form, whose circles hold their icon alone, it stands before the battery's number under the circle.
// Fonts come from the board's fixed set, the largest step that fits; a name is never cut: it takes two lines, or the
// card shows one device fewer. The lines and the circles' middles sit on the pixel grid LVGL draws on (a line of odd
// width at y covers the row around y + 0.5, an even one is centred on y), and a turn is a true quarter circle (LVGL
// draws arcs exactly, slanted lines up to half a pixel off), so a dot always runs in the middle of its line.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

#include "ui_scale.h"

namespace energy_card {
constexpr float PI = 3.14159265358979f;

// ---- What the add-on sends, in W.
struct Device {
  std::string name, entity;
  uint32_t icon = 0;
  float w = 0;
  bool rest = false;  // Other or Untracked consumption: grey, as Home Assistant's sankey paints them
};
// A sensor behind a circle as Home Assistant states it, for the history card a tap opens.
struct Reading {
  std::string entity, state, unit;
};
struct Data {
  bool solar = false, grid = false, battery = false;
  float solar_w = 0, from_grid = 0, to_grid = 0, from_battery = 0, to_battery = 0, home = 0;
  // The split of the moment: source_to_sink.
  float s2h = 0, s2g = 0, s2b = 0, g2h = 0, g2b = 0, b2h = 0, b2g = 0;
  int soc = -1;  // the batteries' charge, -1 without one
  // The sensor behind each source's circle, for a tap (empty where Home Assistant has several or none).
  std::string solar_entity, grid_entity, battery_entity;
  std::vector<Reading> readings;  // those sensors' and the devices' own state and unit
  std::vector<Device> devices;  // drawing power now, in the order of Home Assistant's Energy settings
  std::string home_name;        // the home's name in Home Assistant, for the house's circle
  float rest = 0;               // devices drawing power beyond the ones sent
  // A period instead of the moment (the tile's `period`, the full screen's keys): "day", "week", "month" or "year", every
  // number above in kWh, as Home Assistant's energy dashboard splits the period. Empty for the power now.
  std::string period;
  int range[6]{};      // its first and last day: year, month, day of each
  int offset = 0;      // steps back from the period now (0 the period now, -1 the one before)
  int this_year = 0;   // the year now, so a date of another year says its year
  bool waiting = false;  // the app has not read the period yet
  bool any() const { return solar || grid || battery; }
  bool energy() const { return !period.empty(); }
};

// ---- Glyphs (Material Design Icons) and words.
constexpr uint32_t ICON_HOME = 0xF02DC, ICON_SOLAR = 0xF0A72, ICON_GRID = 0xF0D3E, ICON_OTHER = 0xF01D8, ICON_FLASH = 0xF0241;
constexpr uint32_t ICON_UNTRACKED = 0xF06A1;  // home-outline: the rest of the house
constexpr uint32_t ARROW_LEFT = 0xF004D, ARROW_RIGHT = 0xF0054, ARROW_UP = 0xF005D, ARROW_DOWN = 0xF0045;
// Home Assistant's battery icon by its charge: outline, battery-10 .. battery-90, battery.
inline uint32_t battery_glyph(int soc) {
  if (soc < 0) return 0xF0079;
  const int step = (soc + 5) / 10;
  if (step <= 0) return 0xF008E;
  if (step >= 10) return 0xF0079;
  return 0xF007A + uint32_t(step - 1);
}
inline std::string utf8(uint32_t c) {
  std::string s;
  if (c < 0x80) s += char(c);
  else if (c < 0x800) { s += char(0xC0 | (c >> 6)); s += char(0x80 | (c & 0x3F)); }
  else if (c < 0x10000) { s += char(0xE0 | (c >> 12)); s += char(0x80 | ((c >> 6) & 0x3F)); s += char(0x80 | (c & 0x3F)); }
  else { s += char(0xF0 | (c >> 18)); s += char(0x80 | ((c >> 12) & 0x3F)); s += char(0x80 | ((c >> 6) & 0x3F)); s += char(0x80 | (c & 0x3F)); }
  return s;
}
// The card's own words in the screen's language (screen_text): the draw step fills them.
struct Words {
  std::string solar, grid, battery, home, other, untracked;  // the screen's own words (screen.energy.*)
  // How the screen writes numbers (screen_text.h, Home Assistant's own rule for the language and region): the decimal
  // mark, and what follows a number for a percentage ("%" or " %").
  char decimal = '.';
  std::string percent = " %";
  // A period's words (screen.energy.day ..): the full screen's keys, Today (the calendar's key and its word for the day
  // now), and the dates its line under the name writes (screen.date: Monday first, January first).
  std::array<std::string, 4> units;
  std::string today_key, today;
  std::array<std::string, 7> weekdays;
  std::array<std::string, 12> months, months_short;
};

// power-flow-card-plus's numbers: W below 1000 without decimals, kW with one, a trailing ".0" dropped ("1 kW"),
// rounded half up as JavaScript's toFixed reads them.
inline std::string power(float w, char decimal = '.') {
  char b[24];
  w = std::fabs(w);
  if (std::round(w) < 1000) { snprintf(b, sizeof b, "%.0f W", std::round(w)); return b; }
  snprintf(b, sizeof b, "%.1f", std::round(w / 100) / 10);
  std::string v = b;
  if (v.size() > 2 && v.compare(v.size() - 2, 2, ".0") == 0) v.erase(v.size() - 2);
  for (auto &c : v) if (c == '.') c = decimal;
  return v + " kW";
}
// Home Assistant's energy numbers (formatConsumptionShort in data/energy.ts): kWh, Wh below 1 kWh and MWh from 1000, with
// at most two decimals below 10, one below 100 and none from there, the trailing zeros dropped ("2.5 kWh", "12 kWh").
inline std::string energy(float kwh, char decimal = '.') {
  static const char *const UNITS[] = {"Wh", "kWh", "MWh", "GWh"};
  float v = std::fabs(kwh);
  int unit = 1;
  if (v < 1) { v *= 1000; unit = 0; }  // nothing too: "0 Wh"
  while (v >= 1000 && unit < 3) { v /= 1000; ++unit; }
  const int digits = v < 10 ? 2 : v < 100 ? 1 : 0;
  // Rounded half up in whole hundredths or tenths (no pow: on the CYD its library code alone is some 3 KB of flash).
  static const float SCALE[] = {1.f, 10.f, 100.f};
  char b[32];
  snprintf(b, sizeof b, "%.*f", digits, std::floor(v * SCALE[digits] + 0.5f) / SCALE[digits]);
  std::string s = b;
  if (s.find('.') != std::string::npos) {
    while (s.back() == '0') s.pop_back();
    if (s.back() == '.') s.pop_back();
  }
  for (auto &c : s) if (c == '.') c = decimal;
  return s + " " + UNITS[unit];
}
// A number of the card: power for the moment, energy for a period.
inline std::string amount(const Data &d, float v, char decimal) { return d.energy() ? energy(v, decimal) : power(v, decimal); }

// The line that names a period, as Home Assistant's period selector names it, in the calendar card's words: "Today" or
// "Mon 19 Oct" for a day, "19 – 25 Oct" for a week, "October 2026" for a month, "2026" for a year; a day or a week of
// another year says its year.
inline int days_from_civil(int y, int m, int d) {  // Howard Hinnant's, as the calendar card counts its days
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400, yoe = y - era * 400;
  const int doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1, doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + doe - 719468;
}
inline int weekday_of(int y, int m, int d) { const int z = days_from_civil(y, m, d); return ((z % 7) + 7 + 3) % 7; }  // 0 Monday
inline std::string period_text(const Data &d, const Words &w) {
  const int *r = d.range;
  if (r[1] < 1 || r[1] > 12 || r[4] < 1 || r[4] > 12) return "";
  const std::string dash = " \xE2\x80\x93 ";  // an en dash between the days, as Home Assistant writes a range
  const bool other_year = d.this_year && r[0] != d.this_year;
  const std::string year = std::to_string(r[0]);
  if (d.period == "year") return year;
  if (d.period == "month") return w.months[r[1] - 1] + " " + year;
  if (d.period == "day") {
    if (d.offset == 0 && !w.today.empty()) return w.today;
    return w.weekdays[weekday_of(r[0], r[1], r[2])] + " " + std::to_string(r[2]) + " " + w.months_short[r[1] - 1] + (other_year ? " " + year : "");
  }
  const std::string last = std::to_string(r[5]) + " " + w.months_short[r[4] - 1] + (d.this_year && r[3] != d.this_year ? " " + std::to_string(r[3]) : "");
  if (r[1] == r[4]) return std::to_string(r[2]) + dash + last;
  return std::to_string(r[2]) + " " + w.months_short[r[1] - 1] + (r[0] != r[3] ? " " + year : "") + dash + last;
}
// The seconds a dot takes to run its line: power-flow-card-plus's flow-rate model, 6 s for almost nothing, 0.75 s
// from 2 kW.
inline float duration(float w) { return w > 2000 ? 0.75f : (w - 0.01f) * (0.75f - 6.f) / (2000.f - 0.01f) + 6.f; }

// ---- Colours by role; the draw step asks the theme for them (theme.h, energy section).
enum class Paint : uint8_t { SOLAR, GRID_IN, GRID_OUT, BATTERY_OUT, BATTERY_IN, DEVICE0, DEVICE1, DEVICE2, DEVICE3, REST, INK, MUTED, IDLE, ACCENT,
                             KEY, ON_ACCENT, SUBTLE };  // the full screen's keys: a key, the words on the chosen one, a key that is off

// ---- The board's faces the card may use (its fixed font set) and what the caller measured of them.
enum Face : uint8_t { WATCH_VALUE, HEADLINE, CONTROL, SMALL, ICON, ICON_MINI, ICON_WATCH, FACES };
struct Measure {
  std::array<int, FACES> line{};                         // line heights, 0 where the board lacks the face
  std::function<int(Face, const std::string &)> width;   // a string's width in a face
};

// ---- Geometry.
struct P { float x = 0, y = 0; };
// A line a -> b, or an arc round c from angle t0 to t1 (radians, screen coordinates: 0 points right, pi/2 down).
struct Seg {
  bool arc = false;
  P a, b, c;
  float r = 0, t0 = 0, t1 = 0;
  float length() const { return arc ? std::fabs(t1 - t0) * r : std::hypot(b.x - a.x, b.y - a.y); }
  P at(float u) const {
    if (arc) { const float t = t0 + (t1 - t0) * u; return {c.x + r * std::cos(t), c.y + r * std::sin(t)}; }
    return {a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u};
  }
};
using Path = std::vector<Seg>;
// Paced along the path, as SVG's calcMode="paced" moves power-flow-card-plus's dots.
inline P along(const Path &v, float t) {
  float total = 0;
  for (auto &s : v) total += s.length();
  float want = t * total;
  for (auto &s : v) {
    const float l = s.length();
    if (want <= l && l > 0) return s.at(want / l);
    want -= l;
  }
  return v.empty() ? P{} : v.back().at(1);
}

// What the card paints: circles, the house's ring, the lines and the dots on them, and every word and glyph.
struct Circle {
  P c;
  int d = 0, border = 0;
  Paint paint = Paint::INK;
  std::string entity;  // a tap opens this sensor (none for the house and Other, as in Home Assistant)
};
struct Arc {  // a ring segment of the house, or a turn of a line: centre, outer radius and width, angles in degrees
  P c;
  int radius = 0, width = 0;
  float a0 = 0, a1 = 0;
  Paint paint = Paint::INK;
};
struct Line { P a, b; int width = 1; Paint paint = Paint::INK; };  // pixel coordinates as LVGL takes them
struct Flow {
  Path path;  // the centre line, from where the power comes to where it goes
  Paint paint = Paint::INK;
  float w = 0, seconds = 6;
};
// An arrow in the middle of a line that carries power (the card drawn with lines instead of dots): its tip points the
// way the power goes.
struct Arrow { P tip, left, right; Paint paint = Paint::INK; };
struct Text {
  std::string s;
  Face face = SMALL;
  int x = 0, y = 0, w = 0;
  bool centre = false;
  Paint paint = Paint::INK;
};
// A key of the full screen's header (calendar_card.h's header): a rounded box, and what a finger on it does.
struct KeyBox { int x = 0, y = 0, w = 0, h = 0, radius = 0; Paint paint = Paint::KEY; };
enum HitKind : uint8_t { HIT_CLOSE, HIT_UNIT, HIT_TODAY, HIT_PREV, HIT_NEXT };
struct Hit { int x = 0, y = 0, w = 0, h = 0; HitKind kind = HIT_CLOSE; int arg = 0; };
struct Scene {
  bool ok = false;     // false: the card is too small for the diagram (the draw step shows the house's use alone)
  bool vertical = false;
  int d = 0, lw = 1, step = 0, pass = 0, devices = 0;
  bool cut = false;    // device names cut to their width (no device fit whole)
  float dot_r = 0;
  std::vector<Circle> circles;
  std::vector<Arc> arcs;   // the turns of the lines, under the circles
  std::vector<Arc> ring;   // the house's ring, over its circle
  std::vector<Line> lines;
  std::vector<Flow> flows;   // the lines a dot runs along (none where the card draws lines instead)
  std::vector<Arrow> arrows; // the arrows of a card drawn with lines
  std::vector<Text> texts;
  std::vector<KeyBox> boxes;  // the header's keys, under everything
  std::vector<Hit> hits;
};

// How the card shows power going along a line: power-flow-card-plus's running dots (the default), or a calm card whose
// lines grow thicker with the power and carry an arrow the way it goes (the tile's `flow`, catalogue/screen.yaml).
enum class Style : uint8_t { DOTS, LINES };
// A line's width by its power in the calm card: its width at rest, then two steps up to 2 kW, the power at which a dot
// runs its fastest (duration() above). Each step adds the same even number of pixels, so the line stays centred on the
// pixel grid the circles and turns are built on, and no line grows past a quarter of the room between two neighbours
// (`spacing` is half that room, the lines' distance from their middle).
inline int flow_width(float watts, int lw, float spacing) {
  if (watts <= 0) return lw;
  const int step = std::max(1, lw / 2) * 2;
  const int widest = std::max(lw, lw + int(std::floor((spacing * 0.5f - lw) / step)) * step);
  const int k = watts >= 2000 * 2 / 3.f ? 2 : watts >= 2000 / 3.f ? 1 : 0;
  return std::min(widest, lw + k * step);
}

// ---- The fit: the richest form and the largest fonts the room holds.
struct Steps { Face value, arrow, icon, label; };
struct Mode { bool both, labels, arrows, one, compact, charge; };
constexpr Mode MODES[] = {{true, true, true, false, false, true},   {false, true, true, false, false, true},
                          {false, true, false, false, false, true},  {false, false, true, false, false, true},
                          {false, false, false, false, false, true}, {false, false, false, true, false, true},
                          {false, true, true, false, true, true},    {false, false, false, true, false, false},
                          {false, true, true, false, true, false}};
constexpr int PASSES = sizeof(MODES) / sizeof(MODES[0]);
constexpr Steps LADDER[] = {{WATCH_VALUE, ICON_MINI, ICON, CONTROL}, {HEADLINE, ICON_MINI, ICON, CONTROL},
                            {CONTROL, ICON_WATCH, ICON, SMALL},      {CONTROL, ICON_WATCH, ICON_MINI, SMALL},
                            {SMALL, ICON_WATCH, ICON_MINI, SMALL},   {SMALL, ICON_WATCH, ICON_WATCH, SMALL}};

// Lying: top/bottom rows and three or four columns. Standing: rows for the grid, the sources, the house and the
// devices under it, three columns.
struct Shape {
  bool top = false, bottom = false;
  int cols = 3;
  int lines = 1;  // the most lines of text a circle holds besides its icon (both directions of the grid or the battery)
  bool charge = false;  // the battery's charge beside its glyph
  bool vertical = false, grid_row = true, source_row = true, device_row = false;
  int label_lines = 1;
};
struct Fit {
  int d = 0, pass = 99, step = 0, label_h = 0, label_lines = 1, cols = 3, rows = 3;
  Mode mode{};
  float x[4]{}, y_top = 0, y_mid = 0, y_bottom = 0;
  bool vertical = false;
  float y_grid = 0, y_sources = 0, y_home = 0, y_devices = 0;
  Steps steps() const { return LADDER[step]; }
};

// The smallest circle whose rows of text all fit inside the ring: each row's half width against the half chord at
// its outer edge, with the border and a pixel of air taken off the radius.
struct Row { int h, w; };
inline int smallest(const std::vector<Row> &rows) {
  int total = 0;
  for (auto &r : rows) total += r.h;
  for (int d = 8; d < 1000; ++d) {
    const float r_in = d / 2.f - std::max(2.f, d / 40.f) - ui::px(1);
    float y = -total / 2.f;
    bool ok = true;
    for (auto &r : rows) {
      const float edge = std::max(std::fabs(y), std::fabs(y + r.h));
      y += r.h;
      if (edge >= r_in || r.w / 2.f > std::sqrt(r_in * r_in - edge * edge)) { ok = false; break; }
    }
    if (ok) return d;
  }
  return 1000;
}

inline Fit fit(const Measure &m, int w, int h, const Shape &sh, const std::vector<std::string> &values) {
  const int rows = sh.vertical ? sh.grid_row + sh.source_row + 1 + sh.device_row : 1 + sh.top + sh.bottom;
  for (int pass = 0; pass < PASSES; ++pass) {
    const Mode &md = MODES[pass];
    const float gap_f = md.one || md.compact ? 0.25f : 0.375f;
    for (int step = 0; step < int(sizeof(LADDER) / sizeof(LADDER[0])); ++step) {
      Steps st = LADDER[step];
      if (!m.line[st.value] || !m.line[st.icon] || !m.line[st.arrow]) continue;
      if (md.compact) st.label = st.value;  // the numbers take the names' place, in the value's size
      const int vh = m.line[st.value], ih = m.line[st.icon];
      // Room for the widest number on the card, at least "8.8 kW".
      int value_w = m.width(st.value, "8.8 kW");
      for (auto &v : values) value_w = std::max(value_w, m.width(st.value, v));
      const int arrowed = md.arrows ? value_w + m.width(st.arrow, utf8(ARROW_LEFT)) + ui::px(2) : value_w;
      // The glyph's row: the battery's glyph and its charge side by side where the card shows it.
      const int charge_w = sh.charge && md.charge ? m.width(st.value, "100 %") + ui::px(6) : 0;  // before a number
      const Row glyph = sh.charge && md.charge && !md.compact ? Row{std::max(ih, vh), m.width(st.icon, utf8(battery_glyph(100))) + ui::px(2) + m.width(st.value, "100 %")}
                                               : Row{ih, ih};
      std::vector<Row> worst;  // the fullest circle this card has
      if (md.compact) worst = {glyph};
      else if (md.one) worst = {glyph, {vh, value_w}};
      else if (sh.lines >= 2) { worst = {glyph, {vh, arrowed}}; if (md.both) worst.push_back({vh, arrowed}); }
      else worst = {{ih, ih}, {vh, value_w}};
      const int d_text = md.compact ? int(std::ceil(smallest(worst) * 1.15f))
                                    : std::max(smallest(worst), smallest({{ih, ih}, {vh, value_w}}));
      // Names over the top row and under the lowest; between rows a gap of 30/80 of a circle (Home Assistant's
      // 110 px pitch at 80 px circles) that also holds the names under the middle row.
      const int lab = md.labels ? m.line[st.label] * (md.compact ? 1 : sh.label_lines) + ui::px(2) : 0;
      const int above = md.labels && (sh.vertical ? sh.grid_row : sh.top) ? lab : 0, below = md.labels ? lab : 0;
      float d_h, d_w;
      if (!sh.vertical) {
        d_h = (h - above - below) / (rows + gap_f * (rows - 1));
        if (md.labels && rows > 1 && gap_f * d_h < lab) d_h = (h - above - below - (rows - 1) * lab) / float(rows);
        d_w = w / (sh.cols + 0.45f * (sh.cols - 1));
      } else {
        // Standing, the rows stretch like the lying columns (at least 0.45 of a circle that also holds the names
        // under each row) and the three columns keep the lying rows' pitch.
        const float room = h - above - below;
        d_h = room / (rows + 0.45f * (rows - 1));
        if (md.labels && 0.45f * d_h < lab + 0.2f * d_h) d_h = (room - (rows - 1) * lab) / (rows + 0.2f * (rows - 1));
        d_w = w / (3 + 2 * gap_f);
      }
      int room = int(std::floor(std::min(d_h, d_w)));
      // Lying with names, the rows may close up to a line of names apart before the card gives up names or devices:
      // a car charging at 11 kW makes every circle wider, and Home Assistant's own pitch is a look, not a rule.
      if (room < d_text && md.labels && !sh.vertical && rows > 1)
        room = int(std::floor(std::min<float>((h - above - below - (rows - 1) * lab) / float(rows), d_w)));
      if (room < d_text) continue;
      if (md.compact && !sh.vertical && arrowed + ui::px(4) > w / float(sh.cols - 1) * 0.9f) continue;
      // Lying, the battery's number stands alone under the bottom row (the compact form shows no devices): the charge
      // before it may take the card's width.
      if (md.compact && !sh.vertical && arrowed + charge_w + ui::px(4) > w * 0.95f) continue;
      if (md.compact && sh.vertical && arrowed + charge_w + ui::px(4) > (1 + gap_f) * d_w * 0.95f) continue;
      Fit r;
      r.mode = md; r.pass = pass; r.step = step; r.vertical = sh.vertical; r.rows = rows;
      r.label_h = lab; r.label_lines = md.compact ? 1 : sh.label_lines;
      // Not much bigger than its text: in Home Assistant's card the text fills 45 to 75 % of a circle.
      r.d = std::min(room, int(d_text * (md.compact ? 1.15f : 1.4f)));
      if (sh.vertical) {
        const float pitch = r.d * (1 + gap_f), gmin = std::max(0.45f * r.d, md.labels ? lab + 0.2f * r.d : 0.f);
        r.cols = 3;
        for (int i = 0; i < 3; ++i) r.x[i] = w / 2.f + (i - 1) * pitch;
        const float length = std::min<float>(h - above - below, std::max(r.d * 5.875f, rows * r.d + (rows - 1) * gmin));
        const float stride = rows > 1 ? (length - r.d) / (rows - 1) : 0;
        float y = (h - above - length - below) / 2.f + above + r.d / 2.f;
        if (sh.grid_row) { r.y_grid = y; y += stride; }
        if (sh.source_row) { r.y_sources = y; y += stride; }
        r.y_home = y; y += stride;
        if (sh.device_row) r.y_devices = y;
        return r;
      }
      r.cols = sh.cols;
      const int gap_v = rows > 1 ? std::max(lab, std::min(int(gap_f * r.d), (h - above - below - rows * r.d) / (rows - 1))) : 0;
      const int height = above + rows * r.d + (rows - 1) * gap_v + below;
      const float width = std::min<float>(w, r.d * 5.875f);  // the card's max-width of 470 px at 80 px circles
      const float x0 = (w - width) / 2;
      for (int i = 0; i < sh.cols; ++i) r.x[i] = x0 + r.d / 2.f + i * (width - r.d) / (sh.cols - 1);
      float y = (h - height) / 2.f + above;
      if (sh.top) { r.y_top = y + r.d / 2.f; y += r.d + gap_v; }
      r.y_mid = y + r.d / 2.f; y += r.d + gap_v;
      if (sh.bottom) r.y_bottom = y + r.d / 2.f;
      return r;
    }
  }
  return Fit{};
}

// A circle's diameter on the grid: odd lines, odd circles, so both are centred on a pixel's middle.
inline int line_width(int d) { return std::max(1, int(std::lround(d / 80.f))); }
inline int on_grid(int d) { const int lw = line_width(d); return d % 2 == lw % 2 ? d : d - 1; }
// The width a name may take: its column's pitch less some air, so neighbouring names never touch.
inline int name_width(const Fit &x, int w) {
  return int(std::min<float>(x.cols > 1 ? (x.x[1] - x.x[0]) - ui::px(14) : w, on_grid(x.d) * 1.9f));
}
// A name on one line, or broken at the space that keeps both lines shortest; empty when two lines do not hold it.
inline std::vector<std::string> wrap2(const std::string &s, const Measure &m, Face f, int w) {
  if (m.width(f, s) <= w) return {s};
  std::vector<std::string> best;
  int best_w = 1 << 30;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] != ' ') continue;
    const std::string a = s.substr(0, i), b = s.substr(i + 1);
    const int wide = std::max(m.width(f, a), m.width(f, b));
    if (wide <= w && wide < best_w) { best_w = wide; best = {a, b}; }
  }
  return best;
}

// A name cut to `w` with three dots, as power-flow-card-plus cuts a long one: only where no device fits whole.
inline std::string ellipsize(std::string s, const Measure &m, Face f, int w) {
  if (m.width(f, s) <= w) return s;
  while (!s.empty() && m.width(f, s + "...") > w) {
    size_t cut = s.size() - 1;
    while (cut > 0 && (static_cast<unsigned char>(s[cut]) & 0xC0) == 0x80) --cut;  // a whole UTF-8 character
    s.erase(cut);
    while (!s.empty() && s.back() == ' ') s.pop_back();
  }
  return s + "...";
}

// The devices the card shows: as many as their names fit for, the last place summing the rest ("Other", as Home
// Assistant's sankey folds its smallest devices) when there are more than places. Names stay whole where any device
// fits whole; only where none does, they are cut as power-flow-card-plus cuts them, rather than no device at all.
struct Choice { Fit fit; std::vector<Device> shown; bool cut = false; };
// The search below tries every form, font step, number of devices and both directions: some 300 ms on an ESP32-S3,
// which held the whole screen at every new value. What it decides follows from the card's shape (its size, which
// sources it has, the devices' names), and from the numbers only through the room the widest one takes. A card keeps
// its last choice and asks again only when the shape changes or a number outgrows the room it was given, as
// docs/CARD_PARTS.md has every card build once and paint its values in place.
struct ChoiceCache {
  std::string shape;  // what the choice was made for
  Fit fit;
  int places = 0, room = 0;  // the devices' places it chose, and the widest number it made room for
  bool cut = false;
};
inline Choice choose(const Data &data, const Measure &m, int w, int h, const Words &words, const std::string &widest = "",
                     ChoiceCache *cache = nullptr) {
  std::vector<std::string> values;
  for (float v : {data.solar_w, data.from_grid, data.to_grid, data.from_battery, data.to_battery, data.home}) values.push_back(amount(data, v, words.decimal));
  for (auto &dv : data.devices) values.push_back(amount(data, dv.w, words.decimal));
  if (!widest.empty()) values.push_back(widest);
  // What no device measures, as Home Assistant's sankey draws it: the house less every device and Other, from 1 W
  // (untrackedFloor). A house without a measured device keeps it in its own number: it would only repeat the house.
  float measured = data.rest;
  for (auto &dv : data.devices) measured += dv.w;
  const float untracked = data.home - measured;
  // A period's floor is a watt-hour (energy sankey: untrackedFloor 0, its numbers start at 1 Wh).
  const bool tracks = measured > 0 && untracked > (data.energy() ? 0.001f : 1.f);
  if (tracks) values.push_back(amount(data, untracked, words.decimal));
  const int listed = int(data.devices.size()) + (data.rest > 0 ? 1 : 0) + (tracks ? 1 : 0);
  std::string shape = std::to_string(w) + 'x' + std::to_string(h) + char('0' + data.solar) + char('0' + data.grid) +
                      char('0' + data.battery) + char(data.soc >= 0 ? 's' : '-') + char(data.rest > 0 ? 'o' : '-') + char(tracks ? 'u' : '-') + words.decimal;
  for (auto *word : {&words.solar, &words.grid, &words.battery, &words.home, &words.other, &words.untracked}) shape += '\n' + *word;
  for (auto &dv : data.devices) shape += '\n' + dv.name;
  // The room a fit gives its numbers: the widest of them in the value's face, at least "8.8 kW" (fit() below).
  auto room = [&](const Fit &x) {
    const Face f = x.steps().value;
    int r = m.width(f, "8.8 kW");
    for (auto &v : values) r = std::max(r, m.width(f, v));
    return r;
  };
  auto devices_for = [&](int n) {
    std::vector<Device> out;
    const int total = int(data.devices.size());
    if (n <= 0) return out;
    if (total + (data.rest > 0 ? 1 : 0) <= n || total == 0) {
      out.assign(data.devices.begin(), data.devices.end());
      if (data.rest > 0) out.push_back({words.other, "", ICON_OTHER, data.rest, true});
      return out;
    }
    // The biggest keep a place, in the order they came (Home Assistant's): the smallest share the last as Other, at
    // least two of them, as Home Assistant groups its smallest devices. One place alone goes to the biggest.
    std::vector<int> by_size(total);
    for (int i = 0; i < total; ++i) by_size[i] = i;
    std::stable_sort(by_size.begin(), by_size.end(), [&](int a, int b) { return data.devices[a].w > data.devices[b].w; });
    if (n == 1) { out.push_back(data.devices[by_size.front()]); return out; }
    std::vector<int> kept(by_size.begin(), by_size.begin() + std::min(n - 1, total));
    std::sort(kept.begin(), kept.end());
    for (int i : kept) out.push_back(data.devices[i]);
    Device other{words.other, "", ICON_OTHER, data.rest, true};
    for (int k = n - 1; k < total; ++k) other.w += data.devices[by_size[k]].w;
    out.push_back(other);
    return out;
  };
  // Untracked consumption keeps the last place, as Home Assistant's sankey puts it after every device; the devices
  // share the places before it, where they all fit or with Other for the rest. Two places for more devices than one
  // stay the biggest and Other: the devices would otherwise go missing from a sum that is meant to add up.
  auto shown_for = [&](int n) {
    std::vector<Device> out;
    const int own = int(data.devices.size()) + (data.rest > 0 ? 1 : 0);
    if (tracks && n >= 2 && (n >= 3 || own <= n - 1)) {
      out = devices_for(n - 1);
      out.push_back({words.untracked, "", ICON_UNTRACKED, untracked, true});
      return out;
    }
    return devices_for(n);
  };
  bool cut = false;
  auto names_fit = [&](const Fit &x, const std::vector<Device> &shown) {
    if (cut || shown.empty() || x.mode.compact || !x.mode.labels) return true;
    const int nw = name_width(x, w);
    for (auto &dv : shown) {
      if (m.width(x.steps().label, dv.name) <= nw) continue;
      if (x.label_lines == 2 && !wrap2(dv.name, m, x.steps().label, nw).empty()) continue;
      return false;
    }
    return true;
  };
  if (cache && cache->fit.d > 0 && cache->shape == shape && room(cache->fit) <= cache->room)
    return {cache->fit, shown_for(cache->places), cache->cut};
  auto keep = [&](const Choice &c, int places) {
    if (cache && c.fit.d > 0) *cache = {shape, c.fit, places, room(c.fit), c.cut};
    return c;
  };
  Shape sh;
  sh.lines = data.battery || data.grid ? 2 : 1;
  sh.charge = data.battery && data.soc >= 0;
  for (int attempt = 0; attempt < 2; ++attempt, cut = true)
  for (int n = std::min(4, listed); n >= (cut ? 0 : 1); --n) {
    const auto shown = shown_for(n);
    for (int lines = 1; lines <= (n > 0 ? 2 : 1); ++lines) {
      sh.cols = n >= 3 ? 4 : 3;
      sh.top = data.solar || n >= 1;
      sh.bottom = data.battery || n >= 2;
      sh.label_lines = lines;
      Shape sv = sh;
      sv.vertical = true; sv.grid_row = data.grid; sv.source_row = data.solar || data.battery; sv.device_row = n >= 3;
      const Fit fh = fit(m, w, h, sh, values), fv = fit(m, w, h, sv, values);
      const bool h_ok = fh.d > 0 && names_fit(fh, shown), v_ok = fv.d > 0 && names_fit(fv, shown);
      Fit best = !h_ok ? fv : !v_ok ? fh : fv.pass < fh.pass || (fv.pass == fh.pass && fv.d > fh.d * 1.1f) ? fv : fh;
      if (!h_ok && !v_ok) best = n == 0 ? (fh.d ? fh : fv) : Fit{};
      if (best.d > 0 && (n == 0 || (best.mode.labels && !best.mode.compact))) return keep({best, shown, cut && n > 0}, n);
      if (n == 0) return keep({best, {}, false}, 0);
    }
  }
  return {};
}

// ---- The scene: everything placed.
struct Grid {
  int lw = 1;
  float snap(float v) const { return lw % 2 ? std::floor(v) + 0.5f : std::round(v); }
  int pix(float v) const { return int(std::lround(lw % 2 ? v - 0.5f : v)); }  // centre line -> the point LVGL takes
};
// From (x, y0) straight along x, a quarter turn of centre radius r, then straight along y to x1. x and y are centre
// lines on the grid; the radius is chosen so the turn's box is whole pixels.
inline Path elbow(const Grid &g, float x, float y0, float y, float x1, float r) {
  const float vy = y > y0 ? 1 : -1, hx = x1 > x ? 1 : -1;
  const int n = std::max(2, int(std::lround(r + g.lw / 2.f)));
  const float rc = n - g.lw / 2.f;
  const P c{x + hx * rc, y - vy * rc};
  const float t0 = std::atan2(0.f, -hx), t1 = std::atan2(vy, 0.f);
  float d = t1 - t0;
  while (d > PI) d -= 2 * PI;
  while (d < -PI) d += 2 * PI;
  Seg a, b, e;
  a.a = {x, y0}; a.b = {x, c.y};
  b.arc = true; b.c = c; b.r = rc; b.t0 = t0; b.t1 = t0 + d;
  e.a = {c.x, y}; e.b = {x1, y};
  return {a, b, e};
}
inline Path reversed(Path v) {
  std::reverse(v.begin(), v.end());
  for (auto &s : v) { if (s.arc) std::swap(s.t0, s.t1); else std::swap(s.a, s.b); }
  return v;
}

// The least room the diagram takes, in millimetres of the card's content: from here up it fits on every board, both
// looks, with every house tests/test_energy_card.cpp knows (seven devices, a car at 11 kW). The editor offers the card
// only where it fits (web/src/model/ui-scale.ts energyFits, the same numbers); a lower card shows the house's use alone.
constexpr int MIN_WIDTH_MM = 30, MIN_HEIGHT_MM_COMPACT = 25, MIN_HEIGHT_MM_STANDARD = 32;
inline bool offered(int w, int h) {
  return w >= ui::mm(MIN_WIDTH_MM) && h >= ui::mm(ui::large() ? MIN_HEIGHT_MM_STANDARD : MIN_HEIGHT_MM_COMPACT);
}

inline Scene build(const Data &data, const Measure &m, int w, int h, const Words &words, const std::string &widest = "",
                   ChoiceCache *cache = nullptr, Style style = Style::DOTS) {
  Scene sc;
  const Choice ch = choose(data, m, w, h, words, widest, cache);
  const Fit &ft = ch.fit;
  if (ft.d == 0) return sc;
  const auto &dev = ch.shown;
  sc.ok = true; sc.vertical = ft.vertical; sc.pass = ft.pass; sc.step = ft.step; sc.devices = int(dev.size());
  sc.cut = ch.cut;
  const int lw = line_width(ft.d);
  const Grid g{lw};
  const int d = on_grid(ft.d);
  const float rr = d / 2.f;
  const int border = std::max(2, int(std::lround(d / 40.f))), ring = 2 * border;
  sc.d = d; sc.lw = lw;
  sc.dot_r = std::max(2.5f, d * 0.05f);  // power-flow-card-plus: about 4 px at 80 px circles
  const float o = 0.175f * d, od = 0.11f * d;  // the lines' spacing; devices at the side enter closer to the middle
  auto at = [&](float x, float y) { return P{g.snap(x), g.snap(y)}; };
  P grid, solar, battery, home, slot[4];
  if (!ft.vertical) {
    grid = at(ft.x[0], ft.y_mid); solar = at(ft.x[1], ft.y_top); battery = at(ft.x[1], ft.y_bottom); home = at(ft.x[2], ft.y_mid);
    slot[0] = at(ft.x[2], ft.y_top); slot[1] = at(ft.x[2], ft.y_bottom); slot[2] = at(ft.x[3], ft.y_top); slot[3] = at(ft.x[3], ft.y_bottom);
  } else {
    grid = at(ft.x[1], ft.y_grid); solar = at(ft.x[0], ft.y_sources); battery = at(ft.x[2], ft.y_sources); home = at(ft.x[1], ft.y_home);
    slot[0] = at(ft.x[0], ft.y_home); slot[1] = at(ft.x[2], ft.y_home); slot[2] = at(ft.x[0], ft.y_devices); slot[3] = at(ft.x[2], ft.y_devices);
  }
  // Standing, the lines are built lying on the mirror image over the diagonal and mirrored back: one set of turns
  // serves both, a quarter turn of the picture with the words upright.
  auto lie = [&](P q) { return ft.vertical ? P{q.y, q.x} : q; };
  const P Lgrid = lie(grid), Lsolar = lie(solar), Lbattery = lie(battery), Lhome = lie(home);
  P Lslot[4];
  for (int i = 0; i < 4; ++i) Lslot[i] = lie(slot[i]);
  auto stand = [&](Path v) {
    if (!ft.vertical) return v;
    for (auto &s : v) {
      std::swap(s.a.x, s.a.y); std::swap(s.b.x, s.b.y); std::swap(s.c.x, s.c.y);
      s.t0 = PI / 2 - s.t0; s.t1 = PI / 2 - s.t1;
    }
    return v;
  };
  // Where a centre line at `off` from a circle's middle meets its edge, less the dot: there the dot slips under the
  // circle, as power-flow-card-plus's line box clips it.
  auto edge = [&](float off) { return std::sqrt(std::max(0.f, rr * rr - off * off)) - sc.dot_r - 1; };
  const float turn = 0.55f * d;  // Home Assistant's turn spans about 42 of 80 px
  auto flow = [&](Path path, Paint paint, float watts, bool reverse = false) {
    path = stand(path);
    // Lines drawn calm grow with their power; with dots every line keeps its width.
    // A period's lines keep their width: the steps up to 2 kW are of power, not of kWh.
    const int width = style == Style::LINES && !data.energy() ? flow_width(watts, lw, o) : lw;
    for (size_t i = 0; i < path.size(); ++i) {
      const Seg &s = path[i];
      if (s.arc) {
        const int n = int(std::lround(s.r + width / 2.f));
        float a0 = s.t0 * 180 / PI, a1 = s.t1 * 180 / PI;
        if (a1 < a0) std::swap(a0, a1);
        sc.arcs.push_back({s.c, n, width, std::fmod(a0 + 360, 360.f), std::fmod(a1 + 360, 360.f), paint});
        continue;
      }
      if (s.length() < 0.5f) continue;
      // A straight piece runs a pixel on under a neighbouring turn: its square end would leave a pale seam.
      P a = s.a, b = s.b;
      const float l = s.length(), ux = (b.x - a.x) / l, uy = (b.y - a.y) / l;
      if (i > 0 && path[i - 1].arc) { a.x -= ux; a.y -= uy; }
      if (i + 1 < path.size() && path[i + 1].arc) { b.x += ux; b.y += uy; }
      sc.lines.push_back({{float(g.pix(a.x)), float(g.pix(a.y))}, {float(g.pix(b.x)), float(g.pix(b.y))}, width, paint});
    }
    if (watts <= 0) return;
    if (reverse) path = reversed(path);
    if (style == Style::DOTS) { sc.flows.push_back({path, paint, watts, duration(watts)}); return; }
    // Halfway along the line, an arrow the way the power goes: as long as a dot is wide and a half, and wide enough to
    // stand out of the thickest line, but within the half of the line that shows between two close circles (a line
    // runs on under a circle for a dot's width at each end).
    const P mid = along(path, 0.5f), ahead = along(path, 0.52f), behind = along(path, 0.48f);
    float ux = ahead.x - behind.x, uy = ahead.y - behind.y;
    const float len = std::hypot(ux, uy);
    if (len <= 0) return;
    ux /= len; uy /= len;
    float total = 0;
    for (auto &sg : path) total += sg.length();
    const float shown = total - 2 * (sc.dot_r + 1);
    const float lng = std::min(std::max(3.f * sc.dot_r, width * 2.f), 0.5f * shown);
    if (lng < 3) return;
    const float half = lng * std::max(0.53f, width * 0.6f / lng);
    const P tip{mid.x + ux * lng / 2, mid.y + uy * lng / 2}, back{mid.x - ux * lng / 2, mid.y - uy * lng / 2};
    sc.arrows.push_back({tip, {back.x - uy * half, back.y + ux * half}, {back.x + uy * half, back.y - ux * half}, paint});
  };
  // A source above or below the middle row: down (or up) at x, a turn into the row at y, on to the circle at `to`.
  auto bend = [&](P from, float x, float y, P to) {
    const float vy = y > from.y ? 1 : -1, hx = to.x > x ? 1 : -1;
    const float y0 = from.y + vy * edge(x - from.x), x1 = to.x - hx * edge(y - to.y);
    const float room_v = std::fabs(y - (from.y + vy * rr)), room_h = std::fabs((to.x - hx * rr) - x);
    return elbow(g, x, y0, y, x1, std::min({turn, room_v, room_h * 0.9f}));
  };
  auto straight = [](P a, P b) { Seg s; s.a = a; s.b = b; return Path{s}; };
  const float up = g.snap(Lhome.y - o), down = g.snap(Lhome.y + o);
  const bool grid_exports = data.to_grid > data.from_grid;
  if (data.solar && data.grid) flow(bend(Lsolar, g.snap(Lsolar.x - o), up, Lgrid), Paint::GRID_OUT, data.s2g);
  if (data.solar) flow(bend(Lsolar, g.snap(Lsolar.x + o), up, Lhome), Paint::SOLAR, data.s2h);
  if (data.solar && data.battery) flow(straight({Lsolar.x, Lsolar.y + edge(0)}, {Lbattery.x, Lbattery.y - edge(0)}), Paint::BATTERY_IN, data.s2b);
  if (data.grid) flow(straight({Lgrid.x + edge(0), Lhome.y}, {Lhome.x - edge(0), Lhome.y}), Paint::GRID_IN, data.g2h);
  if (data.battery) flow(bend(Lbattery, g.snap(Lbattery.x + o), down, Lhome), Paint::BATTERY_OUT, data.b2h);
  if (data.battery && data.grid) {
    auto path = bend(Lbattery, g.snap(Lbattery.x - o), down, Lgrid);  // battery -> grid
    if (data.g2b > data.b2g) flow(path, Paint::GRID_IN, data.g2b, true);
    else flow(path, data.b2g > 0 ? Paint::GRID_OUT : Paint::GRID_IN, data.b2g);
  }
  // A device takes the colour of its place; Other and Untracked consumption are grey, as in Home Assistant's sankey.
  const Paint device_paint[4] = {Paint::DEVICE0, Paint::DEVICE1, Paint::DEVICE2, Paint::DEVICE3};
  auto paint_of = [&](size_t i) { return dev[i].rest ? Paint::REST : device_paint[i]; };
  for (size_t i = 0; i < dev.size(); ++i) {
    const P s = Lslot[i];
    if (i == 0) flow(straight({Lhome.x, Lhome.y - edge(0)}, {s.x, s.y + edge(0)}), paint_of(i), dev[i].w);
    else if (i == 1) flow(straight({Lhome.x, Lhome.y + edge(0)}, {s.x, s.y - edge(0)}), paint_of(i), dev[i].w);
    else flow(bend(s, s.x, g.snap(Lhome.y + (i == 2 ? -od : od)), Lhome), paint_of(i), dev[i].w, true);
  }

  // Circles and their words.
  const Steps st = [&] { Steps s = ft.steps(); if (ft.mode.compact) s.label = s.value; return s; }();
  const int name_w = name_width(ft, w), gap = ui::px(2);
  auto lines_of = [&](const std::string &s) {
    auto v = ft.label_lines == 2 ? wrap2(s, m, st.label, name_w) : std::vector<std::string>{s};
    if (v.empty()) v = {s};
    if (ch.cut) for (auto &line : v) line = ellipsize(line, m, st.label, name_w);
    return v;
  };
  auto name = [&](const std::string &s, P at, bool top) {
    if (!ft.mode.labels) return;
    const auto v = lines_of(s);
    const int lh = m.line[st.label];
    int y = top ? int(at.y - rr) - ft.label_h + (ft.label_lines - int(v.size())) * lh : int(at.y + rr) + gap;
    // Each line centred under its own circle: a box of the name's whole room, pushed off the card's edge, carried the
    // names of the circles at the sides up to half a circle off their middle. Only a line that would cross the edge
    // moves in, and only as far as it must.
    for (auto &line : v) {
      const int tw = m.width(st.label, line);
      const int x = std::max(0, std::min(w - tw - 2, int(std::lround(at.x - tw / 2.f))));
      sc.texts.push_back({line, st.label, x, y, tw + 2, false, Paint::MUTED});
      y += lh;
    }
  };
  struct Value { std::string arrow, text; Paint paint; };
  // A number in a name's place (the compact step): arrow and number in the flow's colour, after the battery's charge.
  auto value_label = [&](P at, bool top, const Value &v, const std::string &charge) {
    const int lh = m.line[st.value];
    const int cw = charge.empty() ? 0 : m.width(st.value, charge) + ui::px(6);
    const int aw = v.arrow.empty() ? 0 : m.width(st.arrow, v.arrow) + gap, tw = m.width(st.value, v.text);
    const int x = std::max(0, std::min(w - cw - aw - tw - 2, int(std::lround(at.x - (cw + aw + tw) / 2.f))));
    const int y = top ? int(at.y - rr) - ft.label_h : int(at.y + rr) + gap;
    if (cw) sc.texts.push_back({charge, st.value, x, y, cw - ui::px(6) + 2, false, Paint::INK});
    if (aw) sc.texts.push_back({v.arrow, st.arrow, x + cw, y + (lh - m.line[st.arrow]) / 2, aw, false, v.paint});
    sc.texts.push_back({v.text, st.value, x + cw + aw, y, tw + 2, false, v.paint});
  };
  // A circle's inside: the icon and the lines, centred as one block (the card's flex column). The battery's charge
  // stands beside its glyph in one row, as Home Assistant's energy distribution card shows it (.battery-soc).
  auto inside = [&](P c, const std::string &icon, Paint icon_paint, const std::vector<Value> &rows, const std::string &charge) {
    const int vh = m.line[st.value], ih = m.line[st.icon];
    const int head = charge.empty() ? ih : std::max(ih, vh);
    const int block = head + int(rows.size()) * vh;
    int y = int(std::lround(c.y - block / 2.f));
    if (charge.empty()) {
      sc.texts.push_back({icon, st.icon, int(std::lround(c.x - rr)) + 1, y, d - 2, true, icon_paint});
    } else {
      const int iw = m.width(st.icon, icon), cw = m.width(st.value, charge);
      const int x = int(std::lround(c.x - (iw + gap + cw) / 2.f));
      sc.texts.push_back({icon, st.icon, x, y + (head - ih) / 2, iw + 2, false, icon_paint});
      sc.texts.push_back({charge, st.value, x + iw + gap, y + (head - vh) / 2, cw + 2, false, Paint::INK});
    }
    y += head;
    for (auto &r : rows) {
      const int aw = r.arrow.empty() ? 0 : m.width(st.arrow, r.arrow) + gap, tw = m.width(st.value, r.text);
      const int x = int(std::lround(c.x - (aw + tw) / 2.f));
      if (aw) sc.texts.push_back({r.arrow, st.arrow, x, y + (vh - m.line[st.arrow]) / 2, aw, false, r.paint});
      sc.texts.push_back({r.text, st.value, x + aw, y, tw + 2, false, r.paint});
      y += vh;
    }
  };
  auto place = [&](P c, const std::string &icon, Paint icon_paint, std::vector<Value> rows, const std::string &label,
                   bool top, const std::string &charge = "") {
    if (ft.mode.compact) {
      inside(c, icon, icon_paint, {}, "");
      if (!rows.empty()) value_label(c, top, rows.front(), charge);
      return;
    }
    inside(c, icon, icon_paint, rows, charge);
    if (!label.empty()) name(label, c, top);
  };
  auto circle = [&](P c, int b, Paint p, const std::string &entity) { sc.circles.push_back({c, d, b, p, entity}); };
  const std::string left = ft.mode.arrows ? utf8(ARROW_LEFT) : "", right = ft.mode.arrows ? utf8(ARROW_RIGHT) : "";
  const std::string down_a = ft.mode.arrows ? utf8(ARROW_DOWN) : "", up_a = ft.mode.arrows ? utf8(ARROW_UP) : "";
  if (data.solar) {
    circle(solar, border, Paint::SOLAR, data.solar_entity);
    place(solar, utf8(ICON_SOLAR), Paint::INK, {{"", amount(data, data.solar_w, words.decimal), Paint::INK}}, words.solar, !ft.vertical);
  }
  if (data.grid) {
    circle(grid, border, grid_exports ? Paint::GRID_OUT : Paint::GRID_IN, data.grid_entity);
    std::vector<Value> rows;
    if (ft.mode.both || data.to_grid > 0) rows.push_back({left, amount(data, data.to_grid, words.decimal), Paint::GRID_OUT});
    if (ft.mode.both || data.from_grid > 0 || data.to_grid <= 0) rows.push_back({right, amount(data, data.from_grid, words.decimal), Paint::GRID_IN});
    if ((ft.mode.one || ft.mode.compact) && rows.size() > 1) rows.erase(rows.begin() + (grid_exports ? 1 : 0));
    if (ft.mode.one) for (auto &r : rows) r.arrow.clear();
    place(grid, utf8(ICON_GRID), Paint::INK, rows, words.grid, ft.vertical);
  }
  if (data.battery) {
    const bool charging = data.to_battery > data.from_battery;
    circle(battery, border, charging ? Paint::BATTERY_IN : Paint::BATTERY_OUT, data.battery_entity);
    std::vector<Value> rows;
    if (ft.mode.both || data.to_battery > 0) rows.push_back({down_a, amount(data, data.to_battery, words.decimal), Paint::BATTERY_IN});
    if (ft.mode.both || data.from_battery > 0) rows.push_back({up_a, amount(data, data.from_battery, words.decimal), Paint::BATTERY_OUT});
    const std::string soc = data.soc >= 0 ? std::to_string(data.soc) + words.percent : "";
    const std::string charge = ft.mode.charge ? soc : "";
    // At rest: "0 W"; the charge alone in the number's place where the form has no room for it beside the glyph.
    if (rows.empty()) rows.push_back({"", charge.empty() && !soc.empty() ? soc : amount(data, 0, words.decimal), Paint::INK});
    if (ft.mode.one) for (auto &r : rows) r.arrow.clear();
    place(battery, utf8(battery_glyph(data.soc)), Paint::INK, rows, words.battery, false, charge);
  }
  {  // The house: a ring in its sources' shares instead of a border; with no sun, Home Assistant's plain border.
    const float total = data.g2h + data.s2h + data.b2h;
    if (!data.solar || total <= 0) circle(home, border, total <= 0 && data.solar ? Paint::IDLE : Paint::ACCENT, "");
    else {
      circle(home, 0, Paint::ACCENT, "");
      // Clockwise from three o'clock: the grid, the battery, the sun (energy-distribution-home-circle.ts).
      const struct { float w; Paint p; } segs[] = {{total - data.s2h - data.b2h, Paint::GRID_IN}, {data.b2h, Paint::BATTERY_OUT}, {data.s2h, Paint::SOLAR}};
      float a = 0;
      for (auto &sg : segs) {
        if (sg.w <= 0) continue;
        const float span = 360.f * sg.w / total;
        // An arc's centre is a pixel corner (LVGL's arc box is even), the circle's may be a pixel's middle: the
        // ring keeps the circle's outer edge within half a pixel, and its colour hides the difference.
        sc.ring.push_back({{std::round(home.x), std::round(home.y)}, int(std::floor(rr)), ring, a, a + span, sg.p});
        a += span;
      }
    }
    place(home, utf8(ICON_HOME), Paint::INK, {{"", amount(data, data.home, words.decimal), Paint::INK}}, dev.size() <= 1 ? words.home : "", false);
  }
  for (size_t i = 0; i < dev.size(); ++i) {
    circle(slot[i], border, paint_of(i), dev[i].entity);
    const bool top = !ft.vertical && (i == 0 || i == 2);
    place(slot[i], utf8(dev[i].icon ? dev[i].icon : ICON_FLASH), paint_of(i), {{"", amount(data, dev[i].w, words.decimal), Paint::INK}}, dev[i].name, top);
  }
  return sc;
}

// The circle under a finger, with a touch area of at least `touch` across (docs/RESPONSIVE.md, 7 mm).
inline const Circle *hit(const Scene &sc, float x, float y, int touch) {
  const Circle *best = nullptr;
  float best_d = 1e9f;
  for (auto &c : sc.circles) {
    const float reach = std::max(c.d, touch) / 2.f, dist = std::hypot(x - c.c.x, y - c.c.y);
    if (dist <= reach && dist < best_d) { best = &c; best_d = dist; }
  }
  return best;
}

// ---- A period: the tile's line that names it, and the full screen's header.
// Everything of a scene `dy` lower: the diagram under the tile's line or the full screen's header.
inline void shift(Scene &sc, int dy) {
  const float f = float(dy);
  for (auto &c : sc.circles) c.c.y += f;
  for (auto *list : {&sc.arcs, &sc.ring}) for (auto &a : *list) a.c.y += f;
  for (auto &l : sc.lines) { l.a.y += f; l.b.y += f; }
  for (auto &fl : sc.flows) for (auto &s : fl.path) { s.a.y += f; s.b.y += f; s.c.y += f; }
  for (auto &a : sc.arrows) { a.tip.y += f; a.left.y += f; a.right.y += f; }
  for (auto &t : sc.texts) t.y += dy;
  for (auto &b : sc.boxes) b.y += dy;
  for (auto &h : sc.hits) h.y += dy;
}
// The tile's line over the diagram: the period it shows, quiet, in the smallest face, where it leaves the diagram the
// least room it needs (the CYD's page has none to spare: its card has the diagram alone, and its full screen names the
// period). Returns how much room it takes.
inline int caption(Scene &sc, const Measure &m, int w, int h, const std::string &line) {
  const int need = m.line[SMALL] + ui::px(4);
  if (line.empty() || !m.line[SMALL] || (offered(w, h) && !offered(w, h - need))) return 0;
  sc.texts.push_back({line, SMALL, 0, 0, w, false, Paint::MUTED});
  return need;
}

inline int look_px(int big, int small) { return ui::px(ui::large() ? big : small); }
// A round key: the calendar card's size, at least a finger wide.
inline int key_size(const Measure &m) { return std::max(ui::touch_min(), m.line[ICON_MINI] + look_px(14, 6)); }
constexpr uint32_t GLYPH_CLOSE = 0xF0156, GLYPH_LEFT = 0xF0141, GLYPH_RIGHT = 0xF0142, GLYPH_CALENDAR = 0xF00ED;
const char *const UNITS[] = {"day", "week", "month", "year"};
inline int unit_index(const std::string &u) {
  for (int i = 0; i < 4; ++i) if (u == UNITS[i]) return i;
  return 0;
}
// The full screen's header, in the calendar card's style (calendar_card.h header()): close, the card's name with the
// period under it, the units as keys (the chosen one blue, no menu: every choice shows), Today, back and forward.
// Narrow glass moves the units under the rest, and then Today becomes a round key with the calendar. `now`: the period
// on show is the one now, so Today and forward have nothing to do; `back`: an earlier period may be asked for.
// Returns where the header ends.
inline int header(Scene &sc, const Measure &m, int width, int margin, const std::string &name, const std::string &line,
                  int unit, bool now, bool back, const Words &w) {
  const int d = key_size(m), y = margin, g = look_px(16, 8), gap = look_px(8, 4), pad = look_px(4, 2);
  const Face kf = SMALL, tf = ui::large() ? HEADLINE : CONTROL;
  auto glyph_key = [&](int x, int ky, uint32_t glyph, HitKind kind, bool on) {
    sc.boxes.push_back({x, ky, d, d, d / 2, Paint::KEY});
    sc.texts.push_back({utf8(glyph), ICON_MINI, x, ky + (d - m.line[ICON_MINI]) / 2, d, true, on ? Paint::INK : Paint::SUBTLE});
    if (on) sc.hits.push_back({x - pad, ky - pad, d + 2 * pad, d + 2 * pad, kind, 0});
  };
  int seg_w[4], units_w = 2 * pad;
  for (int i = 0; i < 4; ++i) { seg_w[i] = m.width(kf, w.units[i]) + look_px(28, 14); units_w += seg_w[i]; }
  const int word_w = m.width(kf, w.today_key) + look_px(28, 14), arrows = 2 * d + gap;
  const int tx = margin + d + look_px(14, 8);
  const int title_w = std::max(m.width(tf, name), m.width(SMALL, line));
  auto room = [&](int right) { return width - margin - right - g - tx; };
  // One row where the name fits beside every key; else the units on a row of their own, and Today a round key where
  // even then the name has no room.
  bool row = room(arrows + g + word_w + g + units_w) >= title_w;
  bool icon = false;
  if (!row) icon = room(arrows + g + word_w) < title_w;
  const int today_w = icon ? d : word_w;
  glyph_key(margin, y, GLYPH_CLOSE, HIT_CLOSE, true);
  int rx = width - margin - d;
  glyph_key(rx, y, GLYPH_RIGHT, HIT_NEXT, !now);
  rx -= gap + d;
  glyph_key(rx, y, GLYPH_LEFT, HIT_PREV, back);
  rx -= g + today_w;
  if (icon) glyph_key(rx, y, GLYPH_CALENDAR, HIT_TODAY, !now);
  else {
    sc.boxes.push_back({rx, y, today_w, d, d / 2, Paint::KEY});
    sc.texts.push_back({w.today_key, kf, rx, y + (d - m.line[kf]) / 2, today_w, true, now ? Paint::MUTED : Paint::INK});
    if (!now) sc.hits.push_back({rx, y - pad, today_w, d + 2 * pad, HIT_TODAY, 0});
  }
  int ux = rx - g - units_w, uy = y;
  if (!row) { ux = std::max(margin, (width - units_w) / 2); uy = y + d + look_px(12, 6); }
  sc.boxes.push_back({ux, uy, units_w, d, d / 2, Paint::KEY});
  int x = ux + pad;
  for (int i = 0; i < 4; ++i) {
    const bool chosen = i == unit;
    if (chosen) sc.boxes.push_back({x, uy + pad, seg_w[i], d - 2 * pad, (d - 2 * pad) / 2, Paint::ACCENT});
    sc.texts.push_back({w.units[i], kf, x, uy + (d - m.line[kf]) / 2, seg_w[i], true, chosen ? Paint::ON_ACCENT : Paint::INK});
    sc.hits.push_back({x, uy - pad, seg_w[i], d + 2 * pad, HIT_UNIT, i});
    x += seg_w[i];
  }
  // The name, and the period under it, in the room the keys leave.
  const int tw = (row ? ux : rx) - g - tx, th = m.line[tf] + m.line[SMALL];
  sc.texts.push_back({name, tf, tx, y + (d - th) / 2, std::max(0, tw), false, Paint::INK});
  sc.texts.push_back({line, SMALL, tx, y + (d - th) / 2 + m.line[tf], std::max(0, tw), false, Paint::MUTED});
  return (row ? y + d : uy + d) + look_px(12, 6);
}
// The key under a finger, in the header's own coordinates; nullptr where none is.
inline const Hit *key_at(const Scene &sc, int x, int y) {
  for (auto it = sc.hits.rbegin(); it != sc.hits.rend(); ++it)
    if (x >= it->x && x < it->x + it->w && y >= it->y && y < it->y + it->h) return &*it;
  return nullptr;
}
// How far back a unit steps (energy_flow.MAX_BACK): about ten years.
inline int max_back(int unit) { static const int BACK[] = {3660, 522, 120, 10}; return BACK[std::clamp(unit, 0, 3)]; }
}  // namespace energy_card
