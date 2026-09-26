#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_climate_tile.cpp -o /tmp/test_climate_tile && /tmp/test_climate_tile
#include "../components/smart_display/climate_tile.h"
#include <cassert>
#include <cmath>
#include <cstdio>

using namespace climate_tile;

static int line(int size) { return (int) std::lround(size * 1.172); }
static Metrics metrics(int dpi) {
  Metrics m;
  m.large = ui::large();
  m.touch = std::max(ui::touch_min(), ui::px(m.large ? 48 : 34));
  m.gap = ui::px(m.large ? 8 : 4);
  const int setp = ui::px(m.large ? 64 : 40), watch = ui::px(m.large ? 38 : 22), control = ui::px(m.large ? 21 : 14);
  m.face_h = {line(setp), line(watch), line(control)};
  // "21.5°": four digits-ish at 0.56 em and the degree sign at 0.38.
  m.face_w = {(int) std::lround(setp * 2.35), (int) std::lround(watch * 2.35), (int) std::lround(control * 2.35)};
  m.caption_h = line(ui::px(m.large ? 16 : 11));
  m.max_width = ui::control_max_width();
  (void) dpi;
  return m;
}
static bool inside(const Rect &r, int width, int top, int bottom) {
  return r.empty() || (r.x >= 0 && r.right() <= width && r.y >= top && r.bottom() <= bottom);
}
static bool apart(const Rect &a, const Rect &b) {
  return a.empty() || b.empty() || a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y;
}

static Layout check(const Metrics &m, int width, int top, int bottom, int modes, const char *what) {
  const Layout l = layout(m, width, top, bottom, modes);
  if (l.form == Form::none) { std::printf("  %-18s none\n", what); return l; }
  for (const Rect *r : {&l.stepper, &l.minus, &l.plus, &l.number, &l.caption_box, &l.bar}) assert(inside(*r, width, top, bottom));
  // The keys are a finger's size in the big form and fill the stepper's height less its inset in the row form.
  if (l.form == Form::big) assert(l.minus.w >= m.touch && l.plus.w == l.minus.w);
  else assert(l.minus.h == m.touch - 2 * m.inset() && l.stepper.h == m.touch);
  assert(l.minus.right() <= l.number.x && l.number.right() <= l.plus.x);
  assert(l.number.w >= m.face_w[l.face]);
  assert(apart(l.minus, l.plus) && apart(l.number, l.bar) && apart(l.minus, l.bar) && apart(l.plus, l.bar));
  if (l.caption) assert(l.caption_box.y == l.number.bottom() && apart(l.caption_box, l.bar));
  if (!l.bar.empty()) {
    assert(l.room >= 2 && l.room <= modes);
    const auto seg = segments(m, l.bar, l.room);
    for (int i = 0; i < l.room; ++i) {
      assert(seg[i].w >= m.touch - 2 * m.inset() && seg[i].x >= l.bar.x && seg[i].right() <= l.bar.right());
      if (i) assert(seg[i].x == seg[i - 1].right());
    }
    if (l.form == Form::row) assert(l.stepper.right() + m.gap <= l.bar.x || l.stepper.bottom() + m.gap <= l.bar.y);
  } else {
    assert(l.room == 0);
  }
  std::printf("  %-18s %s face %d%s, %d segments\n", what, l.form == Form::big ? "big" : "row", l.face, l.caption ? " + now" : "", l.room);
  return l;
}

int main() {
  struct Board { const char *name; int dpi; const char *look; int w, h11, h12, h22; };
  // Content of a square (2 x 2) and a tall (1 x 2) card: width, and the room under the head as tall_tile gives it.
  const Board boards[] = {
      {"CYD 2.8", 143, "compact", 286, 52, 50, 50},
      {"Waveshare 3.5", 165, "standard", 424, 58, 120, 120},
      {"Guition 4", 170, "standard", 424, 108, 142, 142},
      {"Waveshare 4.3", 217, "standard", 478, 95, 104, 104},
      {"Waveshare 7", 133, "standard", 360, 85, 110, 110},
      {"Guition 10.1", 149, "standard", 470, 162, 256, 256},
  };
  for (const Board &b : boards) {
    ui::configure(b.dpi, b.look);
    const Metrics m = metrics(b.dpi);
    std::printf("%s\n", b.name);
    const Layout square = check(m, b.w, 60, 60 + b.h22, 5, "2x2 airco");
    assert(square.form != Form::none);
    // An airco's bar shows heat and cool at least.
    assert(square.room >= 2);
    check(m, b.w, 60, 60 + b.h22, 0, "2x2 setpoint only");
    const Layout tall = check(m, b.w / 2 - 6, 60, 60 + b.h12, 5, "1x2 airco");
    if (b.h12 >= 2 * m.touch + m.gap) assert(tall.room >= 2);
    if (b.h22 >= 140) assert(square.form == Form::big);
  }
  // Too short for a finger: nothing, the card opens on a tap.
  ui::configure(170, "standard");
  assert(layout(metrics(170), 424, 0, 40, 5).form == Form::none);
  // Segments share the bar evenly.
  const auto seg = segments(metrics(170), {0, 0, 300, 48}, 3);
  assert(seg[0].w == seg[2].w && seg[2].right() <= 300);
  std::printf("climate tile: all shapes sound\n");
  return 0;
}
