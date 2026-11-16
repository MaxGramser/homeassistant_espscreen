// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_meter_card.cpp -o /tmp/test_meter_card && /tmp/test_meter_card
// The meter's plan (components/smart_display/meter_card.h) on the faces and grids of the boards it runs on, lying down
// and standing up: on every span a grid takes, every look keeps every word whole and inside its card, the ring inside
// the card, the ruler and its pointer, the cells filling the room under the words, and the colours of the segments.
#include "../components/smart_display/meter_card.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace meter_card;

// Roboto's line is 1.17 of its size and its baseline a fifth of the line up; widths in em, near enough for layout. A
// glyph of the icon font is one em.
static int line(int size) { return (int) std::lround(size * 1.172); }
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c >= 0xF0) { em += 1.0; i += 3; }
    else if (c == ' ') em += 0.25;
    else if (c >= 'A' && c <= 'Z') em += 0.65;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}
struct Board { const char *name, *look; int dpi; int sizes[FACES]; int top, footer, margin, gx, gy, pad; int width, height, cols, rows; };
// label, sublabel, sublabel_big, headline, watch_value, setpoint, watch icon, icon mini, icon, icon big (packages/looks
// via tools/profiles.py), then the top bar, the page bar, the margin, the gaps and the card's padding, and the glass
// with its grid lying down and standing up.
static const Board BOARDS[] = {
  {"cyd", "compact", 143, {11, 11, 14, 18, 22, 40, 12, 18, 28, 40}, 37, 36, 9, 6, 4, 8, 320, 240, 2, 3},
  {"cyd portrait", "compact", 143, {11, 11, 14, 18, 22, 40, 12, 18, 28, 40}, 37, 36, 9, 6, 4, 8, 240, 320, 1, 4},
  {"guition", "standard", 170, {18, 16, 21, 27, 38, 64, 18, 26, 42, 64}, 56, 47, 16, 12, 12, 12, 480, 480, 2, 3},
  {"jc3248w535", "standard", 165, {17, 16, 20, 26, 37, 62, 17, 25, 41, 62}, 55, 45, 16, 12, 12, 12, 480, 320, 2, 2},
  {"waveshare43", "standard", 217, {23, 20, 27, 34, 49, 82, 23, 33, 54, 82}, 64, 60, 16, 12, 13, 15, 800, 480, 3, 3},
  {"waveshare43 portrait", "standard", 217, {23, 20, 27, 34, 49, 82, 23, 33, 54, 82}, 64, 60, 16, 12, 13, 15, 480, 800, 1, 4},
  {"waveshare7", "standard", 133, {14, 13, 16, 21, 30, 50, 14, 20, 33, 50}, 43, 37, 13, 9, 9, 9, 800, 480, 4, 4},
  {"waveshare7 portrait", "standard", 133, {14, 13, 16, 21, 30, 50, 14, 20, 33, 50}, 43, 37, 13, 9, 9, 9, 480, 800, 2, 7},
  {"jc8012p4a1", "standard", 149, {16, 14, 18, 24, 33, 56, 16, 23, 37, 56}, 50, 41, 14, 11, 11, 11, 1280, 800, 5, 5},
  {"reterminald1001 portrait", "standard", 189, {20, 18, 23, 30, 42, 71, 20, 29, 47, 71}, 59, 52, 16, 12, 12, 13, 800, 1280, 3, 8},
  {"tab5", "standard", 294, {31, 28, 36, 47, 66, 111, 31, 45, 73, 111}, 81, 81, 16, 12, 12, 21, 1280, 720, 3, 3},
  {"tab5 portrait", "standard", 294, {31, 28, 36, 47, 66, 111, 31, 45, 73, 111}, 81, 81, 16, 12, 12, 21, 720, 1280, 1, 5},
};
static Measure measure(const Board &b) {
  Measure m;
  for (int f = 0; f < FACES; ++f) { m.line[f] = line(b.sizes[f]); m.base[f] = m.line[f] / 5; }
  const Board *bp = &b;
  m.width = [bp](Face f, const std::string &s) { return wide(s, bp->sizes[f]); };
  // The setpoint's digits have no letters.
  m.covers = [](Face f, const std::string &s) { return f != DIGITS || s.find_first_not_of("0123456789-.,%") == std::string::npos; };
  return m;
}
static Data sensor(const char *name, const char *number, const char *unit, const char *low, const char *high, bool graph) {
  Data d;
  d.name = name; d.number = number; d.unit = unit;
  d.words = std::string(number) + (d.unit.empty() ? "" : d.unit == "%" ? "%" : " " + d.unit);
  d.icon = "\xF3\xB0\x9F\xA4";  // molecule-co2
  d.low = low; d.high = high; d.percent = d.unit == "%"; d.graph = graph;
  return d;
}
static int failures = 0;
static void check(bool ok, const char *where, const char *what) {
  if (ok) return;
  fprintf(stderr, "%s: %s\n", where, what);
  ++failures;
}
// Everything of the plan inside its card of w x h.
static void inside(const Plan &p, const Measure &m, int w, int h, const char *where) {
  for (auto &t : p.texts) {
    const int tw = m.w(t.face, t.s), tx = t.align == LEFT ? t.x : t.align == CENTRE ? t.x + (t.w - tw) / 2 : t.x + t.w - tw;
    check(tx >= 0 && tx + tw <= w + 1 && t.y >= 0 && t.y + m.h(t.face) <= h + 1, where, ("text " + t.s).c_str());
  }
  // The ring is open at the bottom: its ends, at 30 and 150 degrees, stand half a radius under its centre.
  if (p.ring) check(p.cx - p.d / 2 >= 0 && p.cx + p.d / 2 <= w && p.cy - p.d / 2 >= 0 && p.cy + p.d / 4 + p.thick / 2 <= h, where, "ring");
  if (p.tape && !(p.ruler.x - p.pointer / 2 - 1 >= 0 && p.ruler.right() + p.pointer / 2 + 1 <= w && p.ruler.y - p.over >= 0 && p.ruler.bottom() <= h && p.ruler.h >= 4))
    fprintf(stderr, "  ruler %d,%d %dx%d pointer %d over %d in %dx%d\n", p.ruler.x, p.ruler.y, p.ruler.w, p.ruler.h, p.pointer, p.over, w, h);
  if (p.tape) check(p.ruler.x - p.pointer / 2 - 1 >= 0 && p.ruler.right() + p.pointer / 2 + 1 <= w && p.ruler.y - p.over >= 0 && p.ruler.bottom() <= h && p.ruler.h >= 4, where, "ruler");
  if (p.bar) check(p.cells.x >= 0 && p.cells.right() <= w && p.cells.y >= 0 && p.cells.bottom() <= h && p.count >= 10, where, "cells");
  if (p.graph) check(p.line.x >= 0 && p.line.right() <= w && p.line.bottom() <= h, where, "graph");
  // Nothing overlaps the words: the cells and the ruler stand under them (or beside them on a standing bar).
  for (auto &t : p.texts) {
    const int ty = t.y + m.h(t.face) - m.base[t.face] / 2;
    if (p.bar && !p.up) check(ty <= p.cells.y + 1, where, ("cells over " + t.s).c_str());
    if (p.bar && p.up) check(t.x + t.w <= p.cells.x, where, ("standing cells over " + t.s).c_str());
    if (p.tape && t.y < p.ruler.y) check(ty <= p.ruler.y - p.over + 2, where, ("ruler over " + t.s).c_str());
  }
}
int main() {
  const Data sensors[] = {
    sensor("Office", "840", "ppm", "400", "1600", true),
    sensor("CPU usage", "86", "%", "0", "100", false),
    sensor("Living room temperature by the window", "21.4", "°C", "16", "26", true),
    sensor("House power", "Unavailable", "", "0", "7", false),
  };
  int plans = 0;
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, b.look);
    const Measure m = measure(b);
    const int cw = (b.width - 2 * b.margin - (b.cols - 1) * b.gx) / b.cols;
    const int ch = (b.height - b.top - b.footer - (b.rows - 1) * b.gy) / b.rows;
    for (int r = 1; r <= b.rows; ++r)
      for (int c = 1; c <= b.cols; ++c) {
        const int w = c * cw + (c - 1) * b.gx - 2 * b.pad, h = r * ch + (r - 1) * b.gy - 2 * b.pad;
        for (Style st : {RING, TAPE, BAR})
          for (size_t k = 0; k < sizeof sensors / sizeof sensors[0]; ++k) {
            Plan p;
            const auto &d = sensors[k];
            plan(p, m, d, st, w, h, 1200);
            char where[160];
            snprintf(where, sizeof where, "%s %dx%d %s sensor %zu", b.name, c, r, st == RING ? "ring" : st == TAPE ? "tape" : "bar", k);
            inside(p, m, w, h, where);
            // A short name, value and range keep every word whole on every card; a name longer than the card may end in
            // an ellipsis, never the value.
            if (k < 2) check(p.cut == 0, where, "a word was shortened");
            for (auto &t : p.texts) if (t.s == d.words || t.s == d.number) check(t.s.find("…") == std::string::npos, where, "the value was shortened");
            check(st != RING || p.ring, where, "no ring");
            check(st != TAPE || p.tape, where, "no ruler");
            check(st != BAR || p.bar, where, "no cells");
            ++plans;
          }
      }
  }
  // The bar fills its card: on a big card the cells take the room under the words, wider and deeper with it.
  {
    const Board &b = BOARDS[8];
    ui::configure(b.dpi, b.look);
    const Measure m = measure(b);
    Plan small, big;
    plan(small, m, sensors[0], BAR, 200, 120, 1200);
    plan(big, m, sensors[0], BAR, 500, 400, 1200);
    assert(big.cells.h > small.cells.h && big.cells.w > small.cells.w && big.cell >= small.cell);
    assert(small.cells.bottom() == 120 && big.cells.bottom() == 400);
    // A standing card stands the bar up at its right.
    Plan standing;
    plan(standing, m, sensors[0], BAR, 200, 500, 1200);
    assert(standing.up && standing.cells.right() == 200 && standing.cells.h == 500);
    // A roomy long ring card gets the last day in its right half; without samples it is the ring as everywhere.
    Plan half, alone;
    plan(half, m, sensors[0], RING, 700, 300, 1200);
    plan(alone, m, sensors[1], RING, 700, 300, 100);
    assert(half.graph && half.cx < 350 && half.line.x > 350 && !alone.graph);
    // The tape names its ends, centred under its end marks, and never those of a percentage.
    Plan tape, percent;
    plan(tape, m, sensors[0], TAPE, 300, 200, 1200);
    plan(percent, m, sensors[1], TAPE, 300, 200, 100);
    int named = 0;
    for (auto &t : tape.texts) if (t.s == "400" || t.s == "1600") ++named;
    assert(named == 2);
    for (auto &t : percent.texts) assert(t.s != "0" && t.s != "100");
    // The ring's icon is drawn in a face that has its glyph: when the faces that fit the disc lack it (a tile icon font
    // larger than this card's, a big font with a few icons), it takes the smallest that has it, never an empty disc.
    Measure only_mini = m;
    only_mini.covers = [](Face f, const std::string &s) { return s != "\xF3\xB0\x9F\xA4" || f == ICON_MINI; };
    only_mini.line[ICON_MINI] = 1000;  // too tall for any disc
    Plan lacking;
    plan(lacking, only_mini, sensors[0], RING, 300, 300, 1200);
    assert(lacking.ring && lacking.icon == ICON_MINI);
  }
  // The colours: one (the tile's own unless chosen), or segments up to their thresholds, which start at 80 % and 90 %.
  {
    Colours one;
    assert(colour_at(one, 50, 0, 100, 0x123456) == 0x123456);
    one.colors[0] = 0x2196F3;
    assert(colour_at(one, 50, 0, 100, 0x123456) == 0x2196F3);
    Colours three;
    three.segments = 3; three.colors = {0x4CAF50, 0xFF9800, 0xF44336};
    assert(colour_at(three, 79, 0, 100, 0) == 0x4CAF50 && colour_at(three, 85, 0, 100, 0) == 0xFF9800 && colour_at(three, 95, 0, 100, 0) == 0xF44336);
    assert(colour_at(three, 1300, 400, 1600, 0) == 0x4CAF50 && colour_at(three, 1400, 400, 1600, 0) == 0xFF9800);
    three.thresholds = {800, 1200};
    assert(colour_at(three, 840, 400, 1600, 0) == 0xFF9800 && colour_at(three, 1250, 400, 1600, 0) == 0xF44336);
    Colours two;
    two.segments = 2; two.colors = {0x4CAF50, 0xF44336, 0};
    assert(colour_at(two, 79, 0, 100, 0) == 0x4CAF50 && colour_at(two, 81, 0, 100, 0) == 0xF44336);
    // A battery turned round: red low, green high, by its colours alone.
    Colours battery;
    battery.segments = 3; battery.colors = {0xF44336, 0xFF9800, 0x4CAF50}; battery.thresholds = {20, 50};
    assert(colour_at(battery, 10, 0, 100, 0) == 0xF44336 && colour_at(battery, 64, 0, 100, 0) == 0x4CAF50);
  }
  // A ruler's steps are round numbers.
  assert(nice_step(1200, 5) == 250 && nice_step(10, 5) == 2 && nice_step(100, 5) == 20);
  // The ruler's long marks divide the range into whole parts: 400 to 1600 in six, 0 to 100 in five, 16 to 26 in five.
  assert(ruler_step(1200, 8) == 200 && ruler_step(100, 8) == 20 && ruler_step(10, 8) == 2 && ruler_step(7, 8) == 1 && ruler_step(7.3f, 8) == 0);
  if (failures) { fprintf(stderr, "%d failures in %d plans\n", failures, plans); return 1; }
  printf("meter card: %d plans OK\n", plans);
  return 0;
}
