#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_text_edit.cpp -o /tmp/test_text_edit && /tmp/test_text_edit
// A Home Assistant text (text, input_text; docs/TEXT_ENTITY.md): what its tile shows on every board (tile_controls.h)
// and what its field asks of the keyboard and does with what was typed (module_text_edit.h), by Home Assistant's rules:
// characters counted as Python counts them, min and max from its attributes (255 at most), a password as dots, an
// unchanged value or a state's word never sent.
#define THEME_TEST
#include "../components/smart_display/tile_controls.h"
#include "../components/smart_display/module_text_edit.h"
#include <cassert>
#include <cmath>
#include <string>

using runtime_tiles::Tile;
using text_edit::Verdict;

static Tile make(const char *entity, const std::string &state) {
  Tile t; t.entity = entity; t.state = state; t.received = true; return t;
}

static void tile() {
  assert(tile_controls::text_entity("text") && tile_controls::text_entity("input_text"));
  assert(!tile_controls::text_entity("input_select") && !tile_controls::text_entity("sensor"));
  // The value as it is: "on" is a text here, an empty value stays empty.
  Tile t = make("input_text.note", "on");
  assert(tile_controls::text_value(t) && tile_controls::text_shown(t) == "on");
  t.state = "";
  assert(tile_controls::text_value(t) && tile_controls::text_shown(t).empty());
  // No value yet, or no entity: the state's words, as for any entity.
  t.state = "unknown";
  assert(!tile_controls::text_value(t));
  t.state = "unavailable";
  assert(!tile_controls::text_value(t));
  // A password: a dot per character, é and € each one.
  Tile p = make("text.code", "é€x");
  p.secret = true;
  assert(tile_controls::text_shown(p) == "•••");
  assert(tile_controls::TEXT_BYTES == text_edit::MOST_BYTES);
}

static void field() {
  // Home Assistant's attributes: min and max, a password or not.
  keyboard::Spec k = text_edit::spec(3, 20, true);
  assert(k.least == 3 && k.chars == 20 && k.mask && k.most == text_edit::MOST_BYTES);
  assert(k.suggestions.empty() && k.send_word.empty() && !k.keep_row);
  // A max above Home Assistant's state limit, none or nonsense: 255. A min above the max: the max.
  assert(text_edit::spec(0, 1000, false).chars == 255 && !text_edit::spec(0, 1000, false).mask);
  assert(text_edit::spec(NAN, NAN, false).chars == 255 && text_edit::spec(NAN, NAN, false).least == 0);
  assert(text_edit::spec(-4, 0, false).chars == 255 && text_edit::spec(-4, 0, false).least == 0);
  assert(text_edit::spec(30, 10, false).least == 10);
  // The field starts with the value, never with a state's word.
  assert(text_edit::start("Hello") == "Hello" && text_edit::start("unknown").empty() && text_edit::start("").empty());
  // The send key: too short or too long keeps the field, the same value or a state's word closes, anything else goes.
  keyboard::Spec three = text_edit::spec(3, 5, false);
  assert(text_edit::sent("ab", "abcd", three) == Verdict::KEEP);
  assert(text_edit::sent("abcdef", "abcd", three) == Verdict::KEEP);
  assert(text_edit::sent("abcd", "abcd", three) == Verdict::CLOSE);
  assert(text_edit::sent("abc", "abcd", three) == Verdict::SEND);
  assert(text_edit::sent("ééé", "abcd", three) == Verdict::SEND);  // three characters, six bytes
  // An empty value is a value: a text without a min may be emptied, and one without a value yet stays as it is.
  keyboard::Spec any = text_edit::spec(0, 100, false);
  assert(text_edit::sent("", "Hello", any) == Verdict::SEND);
  assert(text_edit::sent("", "unknown", any) == Verdict::CLOSE);
  assert(text_edit::sent("unknown", "abcd", any) == Verdict::CLOSE && text_edit::sent("unavailable", "", any) == Verdict::CLOSE);
  assert(text_edit::sent(" a ", "a", any) == Verdict::SEND);  // spaces and all, as Home Assistant's field sends it
  // What the keyboard types into the field obeys the same limits: no sixth character, and the check faded under three.
  keyboard::Entry e;
  keyboard::reset(e, text_edit::start("abcd"));
  keyboard::press(e, 0, three);
  keyboard::press(e, 0, three);
  assert(e.text == "abcdq" && keyboard::sendable(e, three));
  keyboard::press(e, keyboard::K_BACK, three);
  keyboard::press(e, keyboard::K_BACK, three);
  keyboard::press(e, keyboard::K_BACK, three);
  assert(e.text == "ab" && !keyboard::sendable(e, three));
}

// The text area (plan_area): a long value over several lines, none wider than the area, the cursor's line in view, and
// a finger that puts the cursor between two characters.
static int low_line(const calendar_card::Measure &m) { return calendar_card::L(m, calendar_card::CONTROL) + ui::px(6); }
static void area() {
  ui::configure(170, "standard");
  calendar_card::Measure m;
  for (int i = 0; i < calendar_card::FACES; ++i) m.line[i] = 22;
  m.width = [](calendar_card::Face, const std::string &s) { return int(keyboard::characters(s)) * 10; };
  const std::string text = "Back at three. Parcels go to the side door behind the garden gate, please ring twice.";
  for (const auto &l : text_edit::wrap(m, calendar_card::CONTROL, text, 200)) {
    assert(m.width(calendar_card::CONTROL, text.substr(l.from, l.to - l.from)) <= 200 + 10);  // a space at the end may hang
    assert(l.to == text.size() || text[l.to - 1] == ' ');  // a line breaks after a word
  }
  keyboard::Entry e;
  keyboard::reset(e, text);
  calendar_card::Scene s;
  const auto a = text_edit::plan_area(s, m, 0, 0, 260, 400, e, false);
  assert(a.lines.size() > 3 && s.texts.size() == a.lines.size());
  // A finger on the second line, 5 characters in, puts the cursor there.
  const size_t at = text_edit::caret_at(a, m, text, a.x + a.pad + 50 + 2, a.lines[1].y + 5);
  assert(at == a.lines[1].from + 5);
  keyboard::place(e, at);
  keyboard::press(e, 0, keyboard::Spec());  // q
  assert(e.text.substr(a.lines[1].from, 6) == text.substr(a.lines[1].from, 5) + "q");
  // A short area keeps the cursor's line in view: the cursor at the end, the last lines show.
  keyboard::reset(e, text);
  calendar_card::Scene t;
  const auto low = text_edit::plan_area(t, m, 0, 0, 260, 2 * ui::px(16) + 2 * low_line(m), e, false);
  assert(low.lines.size() == 2 && low.lines.back().to == text.size());
  // A password: the same, on its dots.
  keyboard::reset(e, "secret");
  calendar_card::Scene u;
  const auto pw = text_edit::plan_area(u, m, 0, 0, 260, 200, e, true);
  assert(u.texts.size() == 1 && u.texts[0].s == "••••••");
  assert(text_edit::caret_at(pw, m, "secret", pw.x + pw.pad + 20, pw.lines[0].y) == 2);
}

int main() {
  tile();
  field();
  area();
  printf("text entity: ok\n");
  return 0;
}
