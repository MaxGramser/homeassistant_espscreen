// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_lock_panel.cpp -o /tmp/test_lock_panel && /tmp/test_lock_panel
#define THEME_TEST
#include "../components/smart_display/lock_panel.h"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace lock_panel;

static Lock at(const char *state, uint32_t supported = 0) { Lock l; l.state = state; l.supported = supported; return l; }

// Home Assistant's colours and icons (--state-lock-*-color, icons.json of lock).
static void test_looks() {
  assert(color("locked") == GREEN);
  for (const char *s : {"locking", "unlocking", "opening"}) assert(color(s) == ORANGE && std::strcmp(icon(s), glyph::LOCK_CLOCK) == 0);
  for (const char *s : {"unlocked", "open", "jammed"}) assert(color(s) == RED);
  assert(std::strcmp(icon("locked"), glyph::LOCK) == 0 && std::strcmp(icon("unlocked"), glyph::LOCK_OPEN) == 0);
  assert(std::strcmp(icon("open"), glyph::LOCK_OPEN) == 0 && std::strcmp(icon("jammed"), glyph::LOCK_ALERT) == 0);
  assert(std::strcmp(service(LOCK), "lock.lock") == 0 && std::strcmp(service(UNLOCK), "lock.unlock") == 0 &&
         std::strcmp(service(OPEN), "lock.open") == 0 && !*service(NONE));
}

// canLock / canUnlock / canOpen of Home Assistant's frontend, plus the screen's rules: never unlock an unknown lock,
// never unlock or open from a lock-only tile.
static void test_can() {
  const auto C = Guard::CONFIRM, L = Guard::LOCK_ONLY;
  assert(can(at("unlocked"), LOCK, C) && !can(at("locked"), LOCK, C));
  assert(can(at("locked"), UNLOCK, C) && !can(at("unlocked"), UNLOCK, C));
  assert(!can(at("locking"), LOCK, C) && !can(at("unlocking"), UNLOCK, C));
  assert(can(at("unknown"), LOCK, C) && !can(at("unknown"), UNLOCK, C) && !can(at("unknown", feature::OPEN), OPEN, C));
  assert(!can(at("locked"), OPEN, C) && can(at("locked", feature::OPEN), OPEN, C) && !can(at("open", feature::OPEN), OPEN, C));
  assert(!can(at("locked"), UNLOCK, L) && !can(at("locked", feature::OPEN), OPEN, L) && can(at("unlocked"), LOCK, L));
  Lock gone = at("locked"); gone.available = false;
  assert(!can(gone, LOCK, C) && !can(gone, UNLOCK, C));
  Lock assumed = at("locked"); assumed.assumed = true;
  assert(can(assumed, LOCK, C) && can(assumed, UNLOCK, C));
  assert(can(at("jammed"), LOCK, C) && can(at("jammed"), UNLOCK, C));
}

// The tile: lock at once, unlock after a second tap, nothing while it moves or from a lock-only tile.
static void test_tap() {
  const auto C = Guard::CONFIRM, L = Guard::LOCK_ONLY;
  assert(tap(at("unlocked"), C) == LOCK && tap(at("open"), C) == LOCK && tap(at("jammed"), C) == LOCK);
  assert(tap(at("locked"), C) == UNLOCK && tap(at("locked"), L) == NONE && tap(at("unlocked"), L) == LOCK);
  assert(tap(at("locking"), C) == NONE && tap(at("unlocking"), C) == NONE);
  assert(tap(at("unknown"), C) == LOCK);
  assert(confirms(UNLOCK) && confirms(OPEN) && !confirms(LOCK));
}

// The card: the big key does what the tile does; the keys beside it do the rest.
static void test_card() {
  const auto C = Guard::CONFIRM, L = Guard::LOCK_ONLY;
  assert(primary(at("locked"), C) == UNLOCK && primary(at("unlocked"), C) == LOCK && primary(at("jammed"), C) == LOCK);
  assert(primary(at("locked"), L) == NONE && primary(at("locking"), C) == NONE);
  auto k = secondary(at("locked"), C);
  assert(k.count == 0);
  k = secondary(at("locked", feature::OPEN), C);
  assert(k.count == 1 && k.act[0] == OPEN);
  k = secondary(at("jammed", feature::OPEN), C);
  assert(k.count == 2 && k.act[0] == UNLOCK && k.act[1] == OPEN);
  k = secondary(at("jammed", feature::OPEN), L);
  assert(k.count == 0);
}

// "Tap again" waits five seconds for the same action.
static void test_confirm() {
  Confirm c;
  assert(!c.press(UNLOCK, 1000) && c.waiting(UNLOCK, 5999) && c.any(2000));
  assert(c.press(UNLOCK, 5999) && !c.any(6000));
  assert(!c.press(UNLOCK, 10000) && !c.waiting(UNLOCK, 15000) && !c.press(UNLOCK, 15000));
  assert(!c.press(OPEN, 16000) && !c.press(UNLOCK, 16500) && c.waiting(UNLOCK, 17000) && !c.waiting(OPEN, 17000));
  c.clear();
  assert(!c.any(17000));
}

// A code_format and no default code asks for a code, for every action; letters cannot be typed.
static void test_codes() {
  assert(needs_code("^\\d{4}$", false) && !needs_code("^\\d{4}$", true) && !needs_code("", false));
  for (const char *f : {"^\\d{4}$", "^[0-9]{6}$", "\\d+", "number", "^\\d{4,8}$"}) assert(code_typable(f));
  for (const char *f : {"text", ".+", "^\\w{4}$", "^[a-z0-9]+$", "^[A-Z]{4}$", "\\S+"}) assert(!code_typable(f));
}

static void test_reached() {
  assert(reached("locked", LOCK) && reached("locking", LOCK) && !reached("unlocked", LOCK));
  assert(reached("unlocked", UNLOCK) && reached("unlocking", UNLOCK) && reached("open", UNLOCK) && !reached("locked", UNLOCK));
  assert(reached("open", OPEN) && reached("opening", OPEN) && !reached("locked", OPEN) && !reached("jammed", OPEN));
  assert(guard_of("lock_only") == Guard::LOCK_ONLY && guard_of("confirm") == Guard::CONFIRM && guard_of("") == Guard::CONFIRM);
}

int main() {
  test_looks();
  test_can();
  test_tap();
  test_card();
  test_confirm();
  test_codes();
  test_reached();
  std::puts("lock_panel: all tests passed");
  return 0;
}
