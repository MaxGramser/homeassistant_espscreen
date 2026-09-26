// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_alarm_panel.cpp -o /tmp/test_alarm_panel && /tmp/test_alarm_panel
#define THEME_TEST
#include "../components/smart_display/alarm_panel.h"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace alarm_panel;

static bool inside(const Rect &r, int width, int top, int bottom) {
  return r.x >= 0 && r.right() <= width && r.y >= top && r.bottom() <= bottom;
}
static bool apart(const Rect &a, const Rect &b) {
  return a.right() <= b.x || b.right() <= a.x || a.bottom() <= b.y || b.bottom() <= a.y;
}

// The modes follow supported_features in Home Assistant's order, disarm always last; trigger is never offered.
static void test_modes() {
  auto all = modes(feature::ARM_HOME | feature::ARM_AWAY | feature::ARM_NIGHT | feature::TRIGGER | feature::ARM_CUSTOM_BYPASS |
                   feature::ARM_VACATION);
  assert(all.size() == 6);
  const char *order[] = {"armed_home", "armed_away", "armed_night", "armed_vacation", "armed_custom_bypass", "disarmed"};
  for (unsigned i = 0; i < 6; ++i) assert(std::strcmp(MODES[all[i]].state, order[i]) == 0);
  auto few = modes(feature::ARM_AWAY | feature::TRIGGER);
  assert(few.size() == 2 && few[0] == 1 && few[1] == DISARM);
  auto none = modes(0);
  assert(none.size() == 1 && none[0] == DISARM);
  assert(mode_of("armed_night") == 2 && mode_of("disarmed") == (int) DISARM && mode_of("arming") == -1);
  assert(std::strcmp(MODES[DISARM].service, "alarm_control_panel.alarm_disarm") == 0);
}

// Home Assistant's frontend rule (setProtectedAlarmControlPanelMode).
static void test_codes() {
  Codes number{"number", true, false};
  assert(needs_code(number, DISARM) && needs_code(number, 1));
  Codes disarm_only{"number", false, false};
  assert(needs_code(disarm_only, DISARM) && !needs_code(disarm_only, 1));
  Codes none{"", true, false};
  assert(!needs_code(none, DISARM) && !needs_code(none, 0));
  Codes saved{"number", true, true};
  assert(!needs_code(saved, DISARM) && !needs_code(saved, 0));
  assert(code_typable(number) && !code_typable(Codes{"text", true, false}));
}

static void test_states() {
  assert(armed("armed_away") && !armed("arming") && !armed("disarmed"));
  assert(urgent("arming") && urgent("pending") && urgent("triggered") && !urgent("disarming") && !urgent("armed_home"));
  assert(calls_for_attention("pending") && calls_for_attention("triggered") && !calls_for_attention("arming"));
  assert(color("triggered") == RED && color("pending") == ORANGE && color("arming") == ORANGE && color("armed_night") == GREEN);
  assert(std::strcmp(icon("triggered"), glyph::BELL_RING) == 0 && std::strcmp(icon("arming"), glyph::SHIELD) == 0);
  assert(std::strcmp(icon("disarmed"), glyph::SHIELD_OFF) == 0 && std::strcmp(icon("armed_away"), glyph::SHIELD_LOCK) == 0);
}

// An attempt is accepted when the state moves towards the mode (the exit delay counts), failed on a refusal or when
// nothing moved within the wait.
static void test_attempt() {
  Attempt a;
  a.begin(1, true, 1000);
  assert(a.settle("disarmed", 2000) == Outcome::WAITING);
  assert(a.settle("arming", 3000) == Outcome::ACCEPTED && !a.active);
  a.begin(1, true, 1000);
  assert(a.settle("armed_away", 1500) == Outcome::ACCEPTED);
  a.begin(DISARM, true, 1000);
  assert(a.settle("pending", 5000) == Outcome::WAITING);          // still counting down: not what was asked
  assert(a.settle("disarming", 5500) == Outcome::ACCEPTED);
  a.begin(DISARM, true, 1000);
  assert(a.settle("triggered", 1000 + ATTEMPT_WAIT_MS) == Outcome::FAILED);  // an ignored code
  a.begin(0, true, 4000);
  assert(a.refused() == Outcome::FAILED && !a.active);
  assert(a.refused() == Outcome::WAITING);                         // settled once
  // millis() wraps: the wait still counts.
  a.begin(0, true, 0xFFFFF000u);
  assert(a.settle("disarmed", 0x100u) == Outcome::WAITING);
  assert(a.settle("disarmed", 0xFFFFF000u + ATTEMPT_WAIT_MS) == Outcome::FAILED);
}

// Three wrong codes lock for 30 s, each next one doubles, never beyond 15 minutes; a good code opens everything.
static void test_lockout() {
  assert(lock_seconds(0) == 0 && lock_seconds(2) == 0 && lock_seconds(3) == 30 && lock_seconds(4) == 60 && lock_seconds(5) == 120);
  assert(lock_seconds(8) == 900 && lock_seconds(40) == 900);
  Lockout l;
  uint32_t now = 5000;
  assert(l.fail(now) == 0 && l.fail(now) == 0 && !l.locked(now));
  assert(l.fail(now) == 30 && l.locked(now) && l.remaining_s(now) == 30);
  assert(l.remaining_s(now + 29001) == 1 && !l.locked(now + 30000));
  assert(l.fail(now + 31000) == 60);
  l.success();
  assert(!l.locked(now) && l.failures == 0);
  // After a restart the time that was left still holds.
  Lockout again;
  again.resume(4, 45, 100);
  assert(again.locked(100) && again.remaining_s(100) == 45 && again.fail(200) == 120);
  Lockout capped;
  capped.resume(9, 100000, 0);
  assert(capped.remaining_s(0) == MAX_LOCK_S);
  // Across the millis() wrap.
  Lockout wrap;
  for (int i = 0; i < 3; ++i) wrap.fail(0xFFFFFF00u);
  assert(wrap.locked(0x1000u) && !wrap.locked(0xFFFFFF00u + 31000u));
  assert(seconds_left(1100, 1000) == 100 && seconds_left(900, 1000) == 0 && seconds_left(0, 1000) == 0);
}

// Every shape of glass the boards have (landscape, portrait, square, the ten-inch cap), in both looks, with one to
// six modes: every key a finger's size, inside the card, and nothing over anything else.
static void test_layouts() {
  struct Glass { const char *name; bool large; int dpi; int width, height; };
  const Glass glass[] = {
      {"CYD", false, 143, 320, 240},        {"CYD standing", false, 143, 240, 320},
      {"Guition", true, 170, 480, 480},     {"Waveshare 4.3", true, 217, 800, 480},
      {"Waveshare 4.3 standing", true, 217, 480, 800}, {"Waveshare 3.5", false, 165, 480, 320},
      {"7 inch", true, 133, 1024, 600},     {"10 inch", true, 149, 800, 1280},
  };
  for (const auto &g : glass) {
    ui::configure(g.dpi, g.large ? "standard" : "compact");
    Metrics m;
    m.large = g.large;
    m.touch = ui::touch_min();
    m.text_h = ui::px(g.large ? 25 : 16);
    m.side = ui::px(g.large ? 20 : 10);
    const int width = std::min(g.width, ui::control_max_width());
    const int top = ui::px(g.large ? 100 : 56), bottom = g.height - ui::px(g.large ? 18 : 8);
    for (unsigned n = 1; n <= MODE_COUNT; ++n) {
      const CardLayout l = card_layout(m, width, top, bottom, n, false);
      assert(l.key_count == n && !l.hero.empty() && inside(l.hero, width, top, bottom));
      for (unsigned i = 0; i < n; ++i) {
        const Rect &k = l.keys[i];
        if (!(inside(k, width, top, bottom) && k.h >= m.least_key() && apart(k, l.hero))) {
          std::printf("%s: mode key %u of %u at %d,%d %dx%d (card %d, %d..%d)\n", g.name, i, n, k.x, k.y, k.w, k.h, width, top, bottom);
          assert(false);
        }
        for (unsigned j = 0; j < i; ++j) assert(apart(k, l.keys[j]));
      }
    }
    const CardLayout u = card_layout(m, width, top, bottom, 4, true);
    assert(u.key_count == 0 && inside(u.disarm, width, top, bottom) && u.disarm.h >= m.least_key() && apart(u.disarm, u.hero));
    assert(u.hero.h >= m.hero_min() / 2);
    for (unsigned digits : {0u, 4u, 6u, 10u}) {
      const KeypadLayout k = keypad_layout(m, width, top, bottom, digits);
      for (int i = 0; i < 12; ++i) {
        if (!(inside(k.keys[i], width, top, bottom) && k.keys[i].h >= m.least_key() && k.keys[i].w >= m.least_key())) {
          std::printf("%s: keypad key %d at %d,%d %dx%d (card %d, %d..%d)\n", g.name, i, k.keys[i].x, k.keys[i].y, k.keys[i].w, k.keys[i].h, width, top, bottom);
          assert(false);
        }
        assert(apart(k.keys[i], k.dots) && apart(k.keys[i], k.line));
        for (int j = 0; j < i; ++j) assert(apart(k.keys[i], k.keys[j]));
      }
      assert(inside(k.dots, width, top, bottom) && inside(k.line, width, top, bottom) && k.dot >= 4);
    }
  }
  ui::configure(170, "standard");
}

int main() {
  test_modes();
  test_codes();
  test_states();
  test_attempt();
  test_lockout();
  test_layouts();
  std::puts("alarm_panel: ok");
}
