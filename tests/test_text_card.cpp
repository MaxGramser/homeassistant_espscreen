// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_text_card.cpp -o /tmp/test_text_card && /tmp/test_text_card
// The template tile's plan (components/smart_display/module_text_card.h, module text_card) on the faces of the boards
// of the full tier: every piece and mark inside the room it got, words flowed onto lines and never broken across one,
// tones kept apart, table cells on one line each, and a text that does not fit ending in an ellipsis on its last line.
#define SD_MOD_TEXT_CARD
#include "../components/smart_display/module_text_card.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace text_card;
using calendar_card::FACES;

// Roboto's line is 1.17 of its size; widths in em, near enough for layout (tests/test_calendar_card.cpp has the same).
static int line(int size) { return (int) std::lround(size * 1.172); }
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c == ' ') em += 0.25;
    else if (c >= 'A' && c <= 'Z') em += 0.65;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}
struct Board { const char *name, *look; int dpi; int sizes[FACES]; };
static const Board BOARDS[] = {
  {"jc3248w535", "compact", 160, {11, 11, 14, 18, 22, 24, 18, 28}},
  {"guition", "standard", 170, {18, 16, 21, 27, 38, 48, 26, 42}},
  {"waveshare43", "standard", 217, {23, 20, 27, 34, 49, 61, 33, 54}},
  {"jc8012p4a1", "standard", 149, {16, 14, 18, 24, 33, 42, 23, 37}},
};
static Measure measure(const Board &b) {
  Measure m;
  for (int f = 0; f < FACES; ++f) m.line[f] = line(b.sizes[f]);
  const Board *bp = &b;
  m.width = [bp](calendar_card::Face f, const std::string &s) { return wide(s, bp->sizes[f]); };
  return m;
}
static Runs runs(std::initializer_list<std::pair<uint8_t, const char *>> list) {
  Runs out;
  for (auto &r : list) out.push_back({r.first, roomy::Text(r.second)});
  return out;
}
static Row row(uint8_t kind, Runs r) { Row out; out.kind = kind; out.cells.push_back(std::move(r)); return out; }
static Row table(uint8_t kind, std::initializer_list<const char *> cells) {
  Row out; out.kind = kind;
  for (auto *c : cells) out.cells.push_back(runs({{PLAIN, c}}));
  return out;
}
static Data briefing() {
  Data d;
  d.rows.push_back(row(HEAD, runs({{PLAIN, "Today at home"}})));
  d.rows.push_back(row(BULLET, runs({{PLAIN, "Empty the "}, {BOLD, "dishwasher"}})));
  d.rows.push_back(row(BULLET, runs({{ALERT, "Rinse aid"}, {PLAIN, " is low, refill it before tonight's run please"}})));
  d.rows.push_back(row(HEAD, runs({{PLAIN, "Battery tonight"}})));
  d.rows.push_back(table(HEAD_ROW, {"", "Planned", "Applied"}));
  d.rows.push_back(table(ROW, {"Charge target", "80 %", "75 %"}));
  d.rows.push_back(row(TEXT, runs({{PLAIN, "Night power costs "}, {BOLD, "0.18"}, {PLAIN, " per kWh."}})));
  d.rows.push_back(row(TEXT, runs({{GOOD, "Target reached"}})));
  return d;
}
static void inside(const Scene &sc, const Measure &m, int w, int h, const char *what) {
  for (auto &p : sc.pieces) {
    if (p.x < 0 || p.y < 0 || p.x + p.w > w || p.y + m.line[p.face] > h || p.s.empty()) {
      std::printf("FAIL %s: piece '%s' at %d,%d w%d outside %dx%d\n", what, p.s.c_str(), p.x, p.y, p.w, w, h);
      assert(false);
    }
    assert(width(m, p.face, p.s) <= p.w + 1 || p.align == RIGHT);
  }
  for (auto &k : sc.marks) assert(k.x >= 0 && k.y >= 0 && k.x + k.w <= w && k.y + k.h <= h);
}
static bool has(const Scene &sc, const char *text, uint8_t ink) {
  for (auto &p : sc.pieces) if (p.s.find(text) != roomy::Text::npos && p.ink == ink) return true;
  return false;
}

int main() {
  int checks = 0;
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, b.look);
    const Measure m = measure(b);
    const Data d = briefing();
    // From one cell to a whole page, lying down and standing up.
    for (int w : {ui::mm(20), ui::mm(35), ui::mm(60), ui::mm(120)})
      for (int h : {ui::mm(12), ui::mm(25), ui::mm(45), ui::mm(90)}) {
        Scene sc;
        plan(sc, m, w, h, d);
        inside(sc, m, w, h, b.name);
        assert(sc.height <= h);
        // Not everything fits: the last line says so.
        if (sc.cut) assert(!sc.pieces.empty() && sc.pieces.back().s.find(ellipsis()) != roomy::Text::npos);
        ++checks;
      }
    // Room for all of it: nothing is cut, every tone keeps its ink, the table's cells stand on their own.
    {
      Scene sc;
      const int w = ui::mm(120), h = ui::mm(120);
      plan(sc, m, w, h, d);
      assert(!sc.cut);
      assert(has(sc, "Today at home", INK));
      assert(has(sc, "dishwasher", INK));
      assert(has(sc, "Empty the", MUTED));
      assert(has(sc, "Rinse aid", ALERT_INK));
      assert(has(sc, "Target reached", GOOD_INK));
      assert(has(sc, "Planned", MUTED));
      assert(has(sc, "80 %", INK));
      int dots = 0;
      for (auto &k : sc.marks) dots += k.ink == DOT;
      assert(dots == 2);
      // A bullet's words stand right of its dot.
      for (auto &p : sc.pieces) if (p.s.find("dishwasher") != roomy::Text::npos) assert(p.x >= bullet_indent());
      ++checks;
    }
    // A table measures its columns: the values as wide as they need, so a card of 60 mm cuts none of them, and they
    // line up from one row to the next.
    {
      Data t;
      t.rows.push_back(table(HEAD_ROW, {"", "Planned", "Applied"}));
      t.rows.push_back(table(ROW, {"Charge target", "80 %", "75 %"}));
      t.rows.push_back(table(ROW, {"Price", "0.18", "0.21"}));
      Scene sc;
      plan(sc, m, ui::mm(60), ui::mm(60), t);
      int right = -1;
      for (auto &p : sc.pieces) {
        assert(p.s.find(ellipsis()) == roomy::Text::npos);
        if (p.s == "Applied") right = p.x + p.w;
      }
      for (auto &p : sc.pieces) if (p.s == "75 %" || p.s == "0.21") assert(p.x + p.w == right);
      for (auto &k : sc.marks) assert(k.ink != RULE || k.opa == RULE_OPA);
      ++checks;
    }
    // A narrow card flows a long line onto several, every word whole.
    {
      Data one;
      one.rows.push_back(row(TEXT, runs({{PLAIN, "the quick brown fox jumps over the lazy dog again and again"}})));
      Scene sc;
      plan(sc, m, ui::mm(25), ui::mm(80), one);
      int lines = 0, last = -1;
      for (auto &p : sc.pieces) { if (p.y != last) { ++lines; last = p.y; } assert(p.s.find(ellipsis()) == roomy::Text::npos); }
      assert(lines >= 3);
      ++checks;
    }
    // A word longer than the card ends in an ellipsis instead of breaking out of it.
    {
      Data one;
      one.rows.push_back(row(TEXT, runs({{PLAIN, "Donaudampfschifffahrtsgesellschaftskapitaen"}})));
      Scene sc;
      plan(sc, m, ui::mm(15), ui::mm(30), one);
      inside(sc, m, ui::mm(15), ui::mm(30), "long word");
      assert(sc.pieces.size() == 1 && sc.pieces[0].s.find(ellipsis()) != roomy::Text::npos);
      ++checks;
    }
    // A template error is one alert line or a few; an empty result plans nothing.
    {
      Data bad;
      bad.failed = true;
      bad.error = "TemplateSyntaxError: unexpected end of template";
      Scene sc;
      plan(sc, m, ui::mm(40), ui::mm(30), bad);
      assert(!sc.pieces.empty());
      for (auto &p : sc.pieces) assert(p.ink == ALERT_INK);
      Data none;
      assert(empty(none) && !empty(bad));
      plan(sc, m, ui::mm(40), ui::mm(30), none);
      assert(sc.pieces.empty() && sc.marks.empty());
      ++checks;
    }
  }
  std::printf("PASS: the template tile's plan, %d layouts on %zu boards\n", checks, sizeof BOARDS / sizeof BOARDS[0]);
  return 0;
}
