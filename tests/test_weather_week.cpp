// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_weather_week.cpp -o /tmp/test_weather_week && /tmp/test_weather_week
// The weather card's week (weather_week.h): which tier a card of each size reaches on the boards' own fonts, that every
// row it places stays inside the card, that the days come before larger letters, and that a dry week shows no rain row.
#include "../components/smart_display/weather_week.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace weather_week;

static int line(int size) { return (int) std::lround(size * 1.172); }
// Roboto's advance widths in em, near enough for layout (tests/test_forecast_tile.cpp has the same).
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c == 0xC2 && i + 1 < s.size() && (unsigned char) s[i + 1] == 0xB0) { em += 0.38; ++i; }
    else if (c == ' ') em += 0.25;
    else if (c == '%') em += 0.73;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}

// A board's font sizes for the chart's levels (weather_fonts() in runtime_tiles.h): sublabel, sublabel_big, label,
// headline, watch_value; and its icon sizes (watch_icon, icon_mini, icon, icon_big).
struct Board { const char *name; int dpi; const char *look; int sub, big, label, head, value, watch, mini, icon, icon_big; };
static const Board BOARDS[] = {
  {"cyd", 143, "compact", 11, 14, 11, 18, 22, 12, 18, 28, 40},
  {"guition", 170, "standard", 16, 21, 18, 27, 38, 18, 26, 42, 64},
  {"waveshare43", 217, "standard", 20, 27, 23, 34, 49, 23, 33, 54, 82},
  {"waveshare7", 133, "standard", 13, 16, 14, 21, 30, 14, 20, 33, 50},
  {"jc8012p4a1", 149, "standard", 14, 18, 16, 24, 33, 16, 23, 37, 56},
};

static Metrics metrics(const Board &b) {
  ui::configure(b.dpi, b.look);
  Metrics m;
  m.large = ui::large();
  // name, icon, high, low, rain per level (0 tight .. 3 large)
  const int sizes[LEVELS][ROLES] = {{b.sub, b.watch, b.label, b.sub, b.sub}, {b.sub, b.mini, b.label, b.sub, b.sub},
                                    {b.big, b.icon, b.head, b.big, b.sub}, {b.head, b.icon_big, b.value, b.head, b.big}};
  for (int l = 0; l < LEVELS; ++l)
    for (int r = 0; r < ROLES; ++r) m.h[l][r] = r == ICON ? sizes[l][r] : line(sizes[l][r]);
  m.width = [sizes](int level, Role role, const std::string &s) { return role == ICON ? sizes[level][role] : wide(s, sizes[level][role]) + 2; };
  return m;
}

static std::vector<Day> week(bool rain, bool chance) {
  const char *names[] = {"Today", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
  std::vector<Day> days;
  for (int k = 0; k < 7; ++k) {
    Day d;
    d.name = names[k];
    d.condition = "rainy";
    d.high = 19 - k;
    d.low = -12 + k;  // the widest lows: two digits and a sign
    d.mm = rain && k % 2 ? 14.5f : NAN;
    d.chance = chance ? 55 : NAN;
    days.push_back(d);
  }
  return days;
}

static Plan check(const Board &b, int w, int h, bool rain, bool chance, const char *what) {
  const Metrics m = metrics(b);
  const auto days = week(rain, chance);
  const Plan p = plan(m, days, "mm", w, h);
  if (!p.ok()) { printf("%-12s %-8s %4dx%-4d nothing\n", b.name, what, w, h); return p; }
  assert(column_need(m, days, p.cols, p.tier, p.level, "mm") * p.cols <= w);
  const Place r = place(m, p, h);
  assert(r.top >= 0 && r.bottom <= h);
  // rows in order, none on another
  assert(r.name < r.icon && r.icon < r.high);
  if (p.tier >= 1) assert(r.rule1 > r.icon && r.rule1 < r.high && r.high < r.low);
  if (p.tier >= 2) assert(r.curve_h >= curve_min(m, p.level) && r.curve + r.curve_h <= r.low);
  if (p.tier >= 3) assert(r.rule2 > r.low && r.bar > r.rule2 && r.rain > r.bar + r.bar_h - 1);
  if (p.chance) assert(r.chance >= r.rain && r.chance + m.h[p.level][RAIN] <= h);
  printf("%-12s %-8s %4dx%-4d tier %d level %d days %d\n", b.name, what, w, h, p.tier, p.level, p.cols);
  return p;
}

int main() {
  // The cards a board gets, from its grid (screen_manager/app/boards.json) less the card's padding.
  struct Case { const char *board, *what; int w, h; };
  const Case cases[] = {
    {"cyd", "2x1", 210, 34}, {"cyd", "2x2", 286, 70}, {"cyd", "full", 286, 140},
    {"guition", "2x1", 300, 93}, {"guition", "2x2", 424, 166}, {"guition", "full", 424, 300},
    {"waveshare43", "full", 712, 280}, {"waveshare7", "4x2", 600, 160}, {"waveshare7", "full", 738, 340},
    {"jc8012p4a1", "2x2", 450, 180}, {"jc8012p4a1", "full", 1180, 600},
  };
  for (const auto &c : cases)
    for (const auto &b : BOARDS)
      if (std::string(b.name) == c.board) check(b, c.w, c.h, true, true, c.what);

  // A bigger card shows more: the tier never falls as the card grows.
  for (const auto &b : BOARDS) {
    int last = -1;
    for (int h = 40; h <= 600; h += 10) {
      const Metrics m = metrics(b);
      const Plan p = plan(m, week(true, true), "mm", 600, h);
      const int tier = p.ok() ? p.tier : -1;
      assert(tier >= last);
      last = tier;
    }
  }
  // Every day before larger letters: a whole page of the Guition shows all seven.
  {
    const Plan p = check(BOARDS[1], 424, 300, true, true, "days");
    assert(p.cols == 7);
  }
  // A dry week without chances has no rain row; the same card with rain has it.
  {
    const Plan dry = check(BOARDS[1], 424, 300, false, false, "dry");
    const Plan wet = check(BOARDS[1], 424, 300, true, false, "wet");
    assert(dry.tier == 2 && wet.tier == 3);
  }
  // A card of one row shows the days on one line (tier 0), never nothing, where two columns fit.
  {
    const Plan p = check(BOARDS[1], 300, 93, true, true, "row");
    assert(p.ok() && p.tier == 0 && p.cols >= 3);
  }
  // A card of two rows on the Guition shows the line through the week.
  {
    const Plan p = check(BOARDS[1], 424, 166, true, true, "2x2");
    assert(p.tier >= 2);
  }
  // amount() writes the provider's unit, one decimal under ten.
  assert(amount(5.5f, "mm") == "5.5 mm" && amount(14.2f, "mm") == "14 mm" && amount(4.0f, "mm") == "4 mm" && amount(0.25f, "in") == "0.25 in");
  assert(degrees(-0.3f) == "0°" && degrees(19.6f) == "20°");
  // The hours lead the days and hand over to them: the curve has a value everywhere and no jump where hours end.
  {
    auto days = week(true, true);
    std::vector<Hour> hours;
    for (int h = 10; h < 58; ++h) hours.push_back({h, "rainy", 12.0f + (h % 24 > 12 ? 2.0f : 0.0f), 0});
    for (float h = 10; h < 168; h += 0.5f) assert(std::isfinite(through(days, hours, h)));
    assert(std::fabs(through(days, hours, 57.5f) - through(days, hours, 57.0f)) < 1.0f);
  }
  printf("weather_week: all checks passed\n");
  return 0;
}
