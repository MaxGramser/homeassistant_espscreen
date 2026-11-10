// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_todo.cpp -o /tmp/test_todo && /tmp/test_todo
// The to-do card's plans (components/smart_display/module_todo.h, module todo) on the faces of the boards of the full
// tier: the view a room gets, every piece inside its room, keys a finger can hit, what a tick shows before Home
// Assistant confirms it, and what the keyboard types.
#define SD_MOD_TODO
#include "../components/smart_display/module_todo.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace todo;
using calendar_card::FACES;
using calendar_card::Measure;
using calendar_card::Scene;

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
struct Board { const char *name; int dpi, width, height; int sizes[FACES]; };
static const Board BOARDS[] = {
  {"jc3248w535", 165, 480, 320, {17, 16, 20, 26, 37, 47, 25, 41}},
  {"guition", 170, 480, 480, {18, 16, 21, 27, 38, 48, 26, 42}},
  {"waveshare43", 217, 800, 480, {23, 20, 27, 34, 49, 61, 33, 54}},
  {"waveshare7", 133, 800, 480, {14, 13, 16, 21, 30, 38, 20, 33}},
  {"jc8012p4a1", 149, 1280, 800, {16, 14, 18, 24, 33, 42, 23, 37}},
  {"jc3248w535 upright", 165, 320, 480, {17, 16, 20, 26, 37, 47, 25, 41}},
};
static Measure measure(const Board &b) {
  Measure m;
  for (int f = 0; f < FACES; ++f) m.line[f] = line(b.sizes[f]);
  const Board *bp = &b;
  m.width = [bp](calendar_card::Face f, const std::string &s) { return wide(s, bp->sizes[f]); };
  m.circle = ui::px(54);
  return m;
}
static Item item(uint32_t id, const char *text, uint8_t flags = 0, int days = 0) {
  Item it; it.id = id; it.flags = flags; it.days = (int16_t) days; it.text = roomy::Text(text);
  return it;
}
static Data shopping() {
  Data d;
  d.may = MAY_ADD | MAY_TICK | MAY_REMOVE | MAY_CLEAR | MAY_RENAME;
  const char *open[] = {"Oat milk", "Bananas", "Coffee beans", "Tomatoes", "Dishwasher tablets", "Olive oil", "Sourdough bread", "Eggs", "Toilet paper"};
  uint32_t id = 1;
  for (const char *name : open) d.items.push_back(item(id++, name));
  d.items[1].flags |= HAS_DUE | LATE; d.items[1].days = -2;
  d.items[2].flags |= HAS_DUE; d.items[2].days = 1;
  for (const char *name : {"Butter", "Apples"}) d.items.push_back(item(id++, name, DONE));
  d.open = 9; d.done = 2;
  for (const char *name : {"Butter", "Apples", "Burger buns"}) d.offers.push_back(roomy::Text(name));
  return d;
}
static Words english() {
  Words w;
  w.day = [](int days) { return days == 0 ? std::string("Today") : days == 1 ? std::string("Tomorrow") : std::to_string(days) + " d"; };
  return w;
}
static int count(const Scene &s, calendar_card::HitKind kind) {
  int n = 0;
  for (const auto &h : s.hits) n += h.kind == kind;
  return n;
}
static bool has_text(const Scene &s, const std::string &part) {
  for (const auto &t : s.texts) if (t.s.find(part) != std::string::npos) return true;
  return false;
}
// Every box and text of a plan lies inside the room it was planned for (a row's place for the finger may reach into
// the card's own padding, so hits are held to a margin).
static void inside(const Scene &s, int w, int h, const Measure &m, const char *what, const char *board) {
  for (const auto &b : s.boxes)
    if (b.x < 0 || b.y < -ui::px(8) || b.x + b.w > w || b.y + b.h > h + ui::px(8)) {
      printf("%s on %s: a box at %d,%d %dx%d leaves %dx%d\n", what, board, b.x, b.y, b.w, b.h, w, h);
      assert(false);
    }
  for (const auto &t : s.texts)
    if (t.x < 0 || t.x + t.w > w || t.y < -ui::px(8) || t.y + m.line[t.face] > h + ui::px(8) || m.width(t.face, t.s) > t.w + m.line[t.face]) {
      printf("%s on %s: \"%s\" at %d,%d width %d leaves %dx%d\n", what, board, t.s.c_str(), t.x, t.y, t.w, w, h);
      assert(false);
    }
}

static void tiles() {
  const Data d = shopping();
  const Words wd = english();
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, "standard");
    const Measure m = measure(b);
    Scene s;
    // One cell: the count, and nothing to hit, so a tap opens the list.
    const int cell_w = ui::px(190), cell_h = ui::px(84);
    assert(view_of(m, cell_w, cell_h) == View::count);
    plan_tile(s, m, cell_w, cell_h, "Shopping list", d, {}, wd);
    inside(s, cell_w, cell_h, m, "one cell", b.name);
    assert(s.hits.empty() && has_text(s, "9 open"));
    // A large tile: a list, its key to add, rows to tick, and a line for what does not fit.
    const int big_w = ui::px(420), big_h = ui::px(330);
    assert(view_of(m, big_w, big_h) == View::list);
    plan_tile(s, m, big_w, big_h, "Shopping list", d, {}, wd);
    inside(s, big_w, big_h, m, "a large tile", b.name);
    assert(count(s, H_ADD) == 1 && count(s, H_ROW) >= 2);
    for (const auto &h : s.hits) assert(h.h >= ui::touch_min() - ui::px(4));
    if (count(s, H_ROW) < 9) assert(has_text(s, "more"));
    // A list that takes nothing new has no key to add, and one that cannot change has no rows to tick.
    Data fixed = d; fixed.may = 0;
    plan_tile(s, m, big_w, big_h, "Shopping list", fixed, {}, wd);
    assert(s.hits.empty());
    // Room for everything: what is done follows what is open, struck through.
    Data small; small.may = d.may; small.open = 2; small.done = 1;
    small.items.push_back(item(1, "Eggs")); small.items.push_back(item(2, "Bread")); small.items.push_back(item(3, "Butter", DONE));
    plan_tile(s, m, big_w, big_h, "Shopping list", small, {}, wd);
    assert(count(s, H_ROW) == 3 && has_text(s, "Butter") && has_text(s, "2 open"));
  }
}

static void marks() {
  ui::configure(170, "standard");
  const Measure m = measure(BOARDS[1]);
  const Words wd = english();
  Data d = shopping();
  // A tick counts and shows at once, in its place, before the list comes back.
  Marks ticked = {{2, true}, {10, false}};
  assert(is_done(d.items[1], ticked) && !is_done(d.items[9], ticked) && !is_done(d.items[0], ticked));
  assert(count_words(d, {}, wd) == "9 open");
  assert(count_words(d, {{2, true}}, wd) == "8 open");
  assert(count_words(d, ticked, wd) == "9 open");
  Scene plain, marked;
  plan_tile(plain, m, 420, 330, "Shopping list", d, {}, wd);
  plan_tile(marked, m, 420, 330, "Shopping list", d, {{2, true}}, wd);
  assert(plain.hits.size() == marked.hits.size());
  for (size_t i = 0; i < plain.hits.size(); ++i) assert(plain.hits[i].y == marked.hits[i].y && plain.hits[i].arg == marked.hits[i].arg);
  Data none; none.open = 0; none.done = 2; none.items.push_back(item(1, "Butter", DONE));
  assert(count_words(none, {}, wd) == "All done");
  Data waiting; waiting.waiting = true;
  assert(count_words(waiting, {}, wd) == "Loading");
}

static void typing() {
  Entry e;
  reset(e);
  assert(e.shift);
  press(e, 9); press(e, 2); press(e, 10);          // P e a
  assert(e.text == "Pea" && !e.shift);
  press(e, K_SPACE); press(e, K_SPACE);
  assert(e.text == "Pea ");
  press(e, K_PAGE); press(e, 1); press(e, K_PAGE);  // 2
  assert(e.text == "Pea 2" && e.page == 0);
  press(e, K_BACK);
  assert(e.text == "Pea ");
  // A long press on e shows its accents; the first is é.
  assert(hold(e, 2) && e.accents == 2);
  press(e, ACCENT);
  assert(e.text == "Pea é" && e.accents == -1);
  press(e, K_BACK);
  assert(e.text == "Pea ");                          // a whole character goes, never half of one
  assert(!hold(e, 0));                               // q has none
  assert(typed(e) == "Pea");
  while (!e.text.empty()) press(e, K_BACK);
  assert(e.shift);
  for (int i = 0; i < 200; ++i) press(e, 10);
  assert(e.text.size() <= TEXT_BYTES);
  // Every character a key types is one of its page's 26, on every page.
  for (uint8_t page = 0; page < 3; ++page) for (int k = 0; k < 26; ++k) assert(page_keys(page, false)[k] && *page_keys(page, false)[k]);
  assert(accents_of(2, true).size() == accents_of(2, false).size());
}

static void offered() {
  const Data d = shopping();
  assert(offers(d, "").size() == 3);
  const auto bu = offers(d, "bu");
  assert(bu.size() == 2 && bu[0] == "Butter" && bu[1] == "Burger buns");
  assert(offers(d, "Butter").empty());
  Data closed = d; closed.may &= ~MAY_ADD;
  assert(offers(closed, "").empty());
}

static void full() {
  const Data d = shopping();
  const Words wd = english();
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, "standard");
    const Measure m = measure(b);
    FullPlan p;
    Full st;
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, st);
    inside(p.fixed, b.width, b.height, m, "the head", b.name);
    inside(p.content, b.width, p.content.height, m, "the list", b.name);
    assert(count(p.fixed, H_CLOSE) == 1 && count(p.content, H_FIELD) == 1 && count(p.content, H_ROW) == 11 && count(p.content, H_CLEAR) == 1);
    assert(p.overlay.hits.empty() && !p.covered && p.scroll_y > 0 && p.scroll_y + p.scroll_h == b.height);
    // The keyboard: inside the glass, 26 keys and five more, every one a finger can hit, the list above it or the
    // whole glass where that leaves no room.
    st.keys = true;
    reset(st.entry, "Bu");
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, st);
    inside(p.overlay, b.width, b.height, m, "the keyboard", b.name);
    assert(count(p.overlay, H_KEY) == 31 && count(p.overlay, H_SEND) == 1);
    assert(count(p.content, H_FIELD) == 0);
    for (const auto &h : p.overlay.hits)
      if (h.kind == H_KEY) {
        if (h.h < ui::mm(13) / 2) { printf("%s: a key of %d px is lower than 6.5 mm\n", b.name, h.h); assert(false); }
      }
    assert(p.covered || p.scroll_h >= full_row(m, full_face(b.width, b.height)));
    if (!p.covered) assert(count(p.overlay, H_OFFER) >= 1 && has_text(p.overlay, "Butter"));
    // A letter's accents stand above its key, inside the glass.
    assert(hold(st.entry, 2));
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, st);
    inside(p.overlay, b.width, b.height, m, "the accents", b.name);
    assert(count(p.overlay, H_KEY) == 31 + (int) accents_of(2, st.entry.shift).size());
    // An item's sheet and the question before what is done goes take every touch.
    Full sheet; sheet.sheet = 0;
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, sheet);
    inside(p.overlay, b.width, b.height, m, "the sheet", b.name);
    assert(p.covered && count(p.overlay, H_RENAME) == 1 && count(p.overlay, H_REMOVE) == 1 && has_text(p.overlay, "Oat milk"));
    // A row swiped to the left gets Rename and Remove at its end, inside its own strip.
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, Full{});
    Swipe sw;
    assert(plan_swipe(sw, m, p, d, wd, 3));
    assert(count(sw.keys, H_RENAME) == 1 && count(sw.keys, H_REMOVE) == 1);
    assert(sw.reveal >= 2 * ui::touch_min() && sw.reveal < sw.w);
    for (const auto &h : sw.keys.hits) assert(h.x >= sw.x + sw.w - sw.reveal && h.x + h.w <= sw.x + sw.w && h.arg == 3);
    for (const auto &bx : sw.keys.boxes) assert(bx.x >= sw.x && bx.x + bx.w <= sw.x + sw.w && bx.y >= sw.y && bx.y + bx.h <= sw.y + sw.h);
    Data fixed = d; fixed.may = MAY_TICK;
    assert(!plan_swipe(sw, m, p, fixed, wd, 3) && !plan_swipe(sw, m, p, d, wd, 99));
    // The keys stand where they stood when the names offered go: typing never moves them.
    Full with, without; with.keys = without.keys = true;
    reset(with.entry, "Bu"); reset(without.entry, "Zz");
    FullPlan a, z;
    plan_full(a, m, b.width, b.height, "Shopping list", d, {}, wd, with);
    plan_full(z, m, b.width, b.height, "Shopping list", d, {}, wd, without);
    for (const auto &h : a.overlay.hits) if (h.kind == H_KEY) { bool same = false; for (const auto &o : z.overlay.hits) same = same || (o.kind == H_KEY && o.arg == h.arg && o.x == h.x && o.y == h.y); assert(same); }
    Full ask; ask.confirm = true;
    plan_full(p, m, b.width, b.height, "Shopping list", d, {}, wd, ask);
    assert(p.covered && count(p.overlay, H_YES) == 1 && count(p.overlay, H_NO) == 1 && has_text(p.overlay, "2"));
  }
}

int main() {
  tiles();
  marks();
  typing();
  offered();
  full();
  printf("to-do card: ok\n");
  return 0;
}
