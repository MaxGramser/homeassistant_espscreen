#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_forecast_tile.cpp -o /tmp/test_forecast_tile && /tmp/test_forecast_tile
#include "../components/smart_display/forecast_tile.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace forecast_tile;

// A board's look as the test measures it: Roboto's line is 1.17 of its size, a character about 0.55 of it.
struct Board { const char *name; int dpi; const char *look; int w2, h2, w22, h22; };
static int line(int size) { return (int) std::lround(size * 1.172); }
// Roboto's advance widths in em, near enough for layout: digits 0.56, the degree sign 0.38, a space 0.25.
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c == 0xC2 && i + 1 < s.size() && (unsigned char) s[i + 1] == 0xB0) { em += 0.38; ++i; }
    else if (c == 0xC2) { em += 0.25; ++i; }
    else if (c == ' ') em += 0.25;
    else if (c == '%') em += 0.73;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}

static Metrics metrics(bool large) {
  auto f = [](int n) { return ui::px(n); };
  Metrics m;
  m.large = large;
  const int setp = f(large ? 64 : 40), watch = f(large ? 38 : 22), head = f(large ? 27 : 18);
  const int sub = f(large ? 16 : 11), label = f(large ? 18 : 11), mini = f(large ? 26 : 18);
  m.face_h = {line(setp), line(watch), line(head)};
  m.face_w = {wide("18°", setp), wide("18°", watch), wide("18°", head)};
  m.text_h = line(sub);
  m.bold_h = line(label);
  m.icon_h = mini;
  m.circle = f(large ? 54 : 36);
  m.cond_w = wide("Partly cloudy", sub);
  m.line_w = wide("Partly cloudy · Feels like 16°", sub);
  m.temps_w = wide("23°", label) + wide(" ", sub) / 2 + wide("12°", sub);
  m.name_w = wide("We", sub);
  m.row_name_w = wide("We", label);
  m.rain_w = wide("95%", sub);
  m.low_w = wide("12°", sub);
  m.high_w = wide("23°", label);
  m.rain = true;
  return m;
}

static bool inside(const Rect &r, int w, int h) { return r.empty() || (r.x >= 0 && r.y >= 0 && r.right() <= w && r.bottom() <= h); }
static bool apart(const Rect &a, const Rect &b) {
  return a.empty() || b.empty() || a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y;
}

static Layout check(const Metrics &m, int w, int h, bool tall, int today, const char *what) {
  const Layout l = layout(m, w, h, 5, today, tall);
  assert(l.face >= 0);
  for (const Rect *r : {&l.circle, &l.temp, &l.line}) assert(inside(*r, w, h));
  assert(apart(l.circle, l.temp) && apart(l.temp, l.line));
  if (l.form == Form::rows) {
    for (int k = 0; k < l.days; ++k) {
      const Row &r = l.rows[k];
      for (const Rect *p : {&r.name, &r.icon, &r.rain, &r.low, &r.bar, &r.high}) assert(inside(*p, w, h));
      assert(apart(r.name, r.icon) && apart(r.icon, r.low) && apart(r.low, r.bar) && apart(r.bar, r.high) && apart(r.rain, r.low));
      assert(r.bar.w >= m.min_bar());
      // Rows stand under the weather now and never over each other.
      assert(r.name.y >= l.line.bottom() || r.name.y >= l.temp.bottom());
      if (k) assert(r.icon.y > l.rows[k - 1].icon.y);
    }
  } else {
    const int head_right = l.form == Form::side ? std::max(l.temp.right(), l.line.right()) : 0;
    for (int k = 0; k < l.days; ++k) {
      const Column &c = l.columns[k];
      for (const Rect *p : {&c.name, &c.icon, &c.temps, &c.rain}) assert(inside(*p, w, h));
      if (l.form == Form::side) assert(c.icon.x >= head_right && c.temps.x >= head_right);
      else assert(c.icon.y >= l.line.bottom() && c.icon.y >= l.temp.bottom());
      if (k) assert(c.temps.x >= l.columns[k - 1].temps.right());
    }
    // Today's pill keeps its padding: it holds the column's content with pad_x at the sides and pad_y above and
    // under, stays inside the card, and never reaches into the next column.
    if (today >= 0 && today < l.days && !l.pill.empty()) {
      const Column &c = l.columns[today];
      assert(!l.pill.empty() && inside(l.pill, w, h));
      const int top = c.name.empty() || c.name.y > c.icon.y ? c.icon.y : c.name.y;
      const int bottom = c.rain.empty() ? c.temps.bottom() : c.rain.bottom();
      assert(l.pill.y + m.pad_y() <= top && bottom + m.pad_y() <= l.pill.bottom());
      const int centre = c.temps.x + c.temps.w / 2;
      assert(l.pill.x + m.pad_x() <= centre - m.temps_w / 2 && centre + m.temps_w / 2 <= l.pill.right() - m.pad_x());
      assert(l.pill.x >= c.temps.x && l.pill.right() <= c.temps.right());
    } else if (today < 0 || today >= l.days) {
      assert(l.pill.empty());
    }
  }
  std::printf("  %-26s %s %d days, face %d\n", what, l.form == Form::rows ? "rows   " : l.form == Form::stacked ? "stacked" : "side   ",
              l.days, l.face);
  return l;
}

int main() {
  const Board boards[] = {
      {"CYD 2.8", 143, "compact", 286, 48, 286, 100},
      {"Waveshare 3.5", 165, "standard", 424, 66, 424, 168},
      {"Guition 4", 170, "standard", 424, 84, 424, 204},
      {"Waveshare 4.3", 217, "standard", 478, 65, 478, 173},
      {"Waveshare 7", 133, "standard", 360, 67, 360, 152},
      {"Guition 7", 170, "standard", 466, 84, 466, 204},
      {"Guition 10.1", 149, "standard", 470, 140, 470, 314},
  };
  for (const Board &b : boards) {
    ui::configure(b.dpi, b.look);
    const Metrics m = metrics(ui::large());
    std::printf("%s\n", b.name);
    const Layout wide2 = check(m, b.w2, b.h2, false, 0, "2x1, today first");
    assert(wide2.form == Form::side);
    // A double-width card of one row shows at least three days on every board, four from the Guition up.
    assert(wide2.days >= 3);
    if (ui::large() && b.h2 >= 84) assert(wide2.days >= 4);
    check(m, b.w2, b.h2, false, -1, "2x1, today unknown");
    check(m, b.w2, b.h2, false, 3, "2x1, today fourth");
    const Layout square = check(m, b.w22, b.h22, true, 0, "2x2");
    // A square card is taller than a wide one: rows where there is room, and never fewer days.
    assert(square.days >= wide2.days || square.form == Form::rows);
    if (ui::large() && b.h22 >= 200) assert(square.form == Form::rows && square.days >= 4);
  }
  // A one-column board standing up (a 3.5-inch: 264 px of card) keeps two days by giving up today's pill.
  ui::configure(165, "standard");
  const Layout slim = check(metrics(true), 264, 66, false, 0, "3.5 standing, 1x1 wide");
  assert(slim.days >= 2);
  // A cell too narrow for two columns shows the weather now alone.
  ui::configure(170, "standard");
  const Layout narrow = layout(metrics(true), 150, 84, 5, 0, false);
  assert(narrow.days == 0 && narrow.face >= 0 && narrow.pill.empty());
  // No forecast days: the head alone, no pill.
  const Layout none = layout(metrics(true), 424, 84, 0, -1, false);
  assert(none.days == 0 && none.pill.empty());
  std::printf("forecast tile: all shapes sound\n");
  return 0;
}
