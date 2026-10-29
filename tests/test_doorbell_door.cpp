// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_doorbell_door.cpp -o /tmp/test_doorbell_door && /tmp/test_doorbell_door
#define THEME_TEST
#include "../components/smart_display/doorbell_door.h"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace doorbell_door;

constexpr uint32_t GREY = 0x444444;

static Door lock_at(const char *state) {
  Door d;
  d.kind = Kind::LOCK;
  d.set_state(state);
  return d;
}

// The op's `d`: a lock, an action, or no key at all.
static void test_kinds() {
  assert(kind_of(1) == Kind::LOCK && kind_of(2) == Kind::ACTION);
  assert(kind_of(0) == Kind::NONE && kind_of(3) == Kind::NONE);
  Door none;
  assert(!none.opens(1000) && !none.tap(1000) && !none.tap(1500));
}

// One tap never opens: the first arms it for lock_panel's five seconds, the second within them opens.
static void test_two_taps() {
  Door d = lock_at("locked");
  assert(!d.tap(1000) && d.armed(1000) && d.armed(5999));
  assert(d.tap(3000) && !d.armed(3000));
  // Too late: the second tap arms it again instead.
  Door late = lock_at("locked");
  assert(!late.tap(1000) && !late.tap(1000 + lock_panel::CONFIRM_MS) && late.armed(1000 + lock_panel::CONFIRM_MS));
  assert(late.tap(1000 + lock_panel::CONFIRM_MS + 100));
}

// A lock opens only from locked or jammed; never while it moves, once it is open or from a state it does not know.
static void test_which_states_open() {
  for (const char *s : {"locked", "jammed"}) assert(lock_at(s).opens(1000));
  for (const char *s : {"unlocked", "open", "opening", "locking", "unlocking", "unavailable", "unknown", ""}) {
    Door d = lock_at(s);
    assert(!d.opens(1000) && !d.tap(1000) && !d.armed(1000) && !d.tap(1200));
  }
  // It unlocked meanwhile: an armed key is no longer armed after the next tap.
  Door d = lock_at("locked");
  assert(!d.tap(1000));
  d.set_state("unlocked");
  assert(!d.tap(1500) && !d.armed(1500));
}

// After the second tap: a lock says Unlocking until its new state comes (at most WAIT_MS), an action Sent for SENT_MS;
// meanwhile a tap does nothing.
static void test_after_the_second_tap() {
  Door d = lock_at("locked");
  d.tap(1000);
  assert(d.tap(2000) && d.sending(2000));
  assert(look(d, 2500, GREY).line == Line::UNLOCKING && !d.tap(2600) && !d.armed(2600));
  d.set_state("unlocking");
  assert(!d.sending(2700) && look(d, 2700, GREY).line == Line::STATE);
  Door slow = lock_at("locked");
  slow.tap(1000);
  slow.tap(2000);
  assert(slow.sending(2000 + WAIT_MS - 1) && !slow.sending(2000 + WAIT_MS));
  Door a;
  a.kind = Kind::ACTION;
  assert(a.opens(1000) && !a.tap(1000) && a.tap(2000));
  assert(look(a, 2100, GREY).line == Line::SENT && !a.tap(2200) && !a.armed(2200));
  assert(look(a, 2000 + SENT_MS, GREY).line == Line::NONE && a.opens(2000 + SENT_MS));
}

// The looks: the lock's own colour and icon by its state (lock_panel), orange while it waits for its second tap or its
// new state, the key's grey for a state it does not know and for an action.
static void test_looks() {
  using namespace lock_panel;
  Look l = look(lock_at("locked"), 1000, GREY);
  assert(l.color == GREEN && std::strcmp(l.glyph, glyph::LOCK) == 0 && l.line == Line::STATE);
  l = look(lock_at("unlocked"), 1000, GREY);
  assert(l.color == RED && std::strcmp(l.glyph, glyph::LOCK_OPEN) == 0);
  assert(look(lock_at("unavailable"), 1000, GREY).color == GREY);
  Door d = lock_at("locked");
  d.tap(1000);
  l = look(d, 1100, GREY);
  assert(l.color == ORANGE && l.line == Line::TAP_AGAIN);
  Door a;
  a.kind = Kind::ACTION;
  l = look(a, 1000, GREY);
  assert(l.color == GREY && std::strcmp(l.glyph, glyph::DOOR_OPEN) == 0 && l.line == Line::NONE);
}

int main() {
  test_kinds();
  test_two_taps();
  test_which_states_open();
  test_after_the_second_tap();
  test_looks();
  std::puts("PASS: the door key's two taps, which lock states open, the wait after it and its looks");
  return 0;
}
