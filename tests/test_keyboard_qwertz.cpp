// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_keyboard_qwertz.cpp -o /tmp/test_keyboard_qwertz && /tmp/test_keyboard_qwertz
// The keyboard of a screen built in German (docs/KEYBOARD.md, "The layout of a screen"): its build defines
// SCREEN_KEYBOARD_QWERTZ (components/smart_display/keyboard_build.py), as this test does, and every caller that names no
// layout types on QWERTZ: a Spec of its own (a text entity's field) and the to-do card's keys alike.
#define SCREEN_KEYBOARD_QWERTZ
#include "screen_text_en.h"
#include "../components/smart_display/module_todo.h"
#include <cassert>
#include <cstdio>
#include <string>

using namespace keyboard;

int main() {
  assert(&standard() == &qwertz() && &layout_of(Spec()) == &qwertz());
  // A Spec that names no layout types z where QWERTY has y, and an umlaut with one key.
  Spec any;
  Entry e;
  reset(e);
  press(e, 5, any); press(e, 20, any); press(e, 22, any);
  assert(e.text == "Zöy");
  // The to-do card's keys are the screen's own: 29 on every page, z and ü in the first row.
  for (uint8_t page = 0; page < 3; ++page)
    for (int k = 0; k < keys(standard()); ++k) assert(todo::page_keys(page, false)[k] && *todo::page_keys(page, false)[k]);
  assert(std::string(todo::page_keys(0, false)[5]) == "z" && std::string(todo::page_keys(0, true)[10]) == "Ü");
  assert(std::string(todo::page_keys(1, false)[10]) == "ß" && std::string(todo::accents_of(12, false)[0]) == "ß");
  // A caller that names a layout still gets it.
  Spec us;
  us.layout = &qwerty();
  Entry q;
  reset(q);
  press(q, 5, us);
  assert(q.text == "Y");
  printf("keyboard qwertz: ok\n");
  return 0;
}
