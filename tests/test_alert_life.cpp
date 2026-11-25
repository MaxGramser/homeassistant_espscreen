// An alert's life, run: every rule of components/smart_display/alert_life.h on a glass that writes down what it was
// told, in order, with a clock the test moves. The standby it meets is a real one (screen_standby.h), bound to it the
// way packages/core.yaml binds the two.
#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/alert_life.h"
#include "components/smart_display/screen_standby.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using alert_life::Life;
using screen_standby::Standby;

static uint32_t now_ms = 1000;
static std::vector<std::string> trail;  // what the glass was told, in order
static std::vector<std::string> log_lines;
static bool alert_timer = false, standby_timer = false;
static uint32_t alert_at = 0, standby_at = 0;
static Life a;     // the alert of the case that runs
static Standby s;  // and the standby it meets

static void told(const std::string &what) { trail.push_back(what); }
static bool has(const std::string &what) {
  for (const auto &line : trail) if (line == what) return true;
  return false;
}
static int count(const std::string &what) {
  int n = 0;
  for (const auto &line : trail) n += line == what;
  return n;
}
static int place(const std::string &what) {
  for (size_t i = 0; i < trail.size(); ++i) if (trail[i] == what) return static_cast<int>(i);
  return -1;
}
static bool logged(const std::string &line) {
  for (const auto &l : log_lines) if (l == line) return true;
  return false;
}

static screen_alert::Alert alert(const std::string &title, int timeout = 0, bool flash = false, const std::string &button2 = "") {
  screen_alert::Alert made;
  made.title = title;
  made.button = "OK";
  made.button2 = button2;
  made.timeout_seconds = timeout;
  made.flash = flash;
  return made;
}

// A lit screen with nothing on it, brightness 80, a standby level of 20, and the two bound as the core binds them.
static void fresh() {
  now_ms = 1000;
  trail.clear();
  log_lines.clear();
  alert_timer = standby_timer = false;
  screen_settings::current = {};
  screen_settings::current.brightness = 80;
  screen_power::saving = screen_power::touching = screen_power::settling = screen_power::was_tap = false;
  screen_power::freeze = nullptr;
  screen_power::later = [](uint32_t ms) { s.power_wait(ms, now_ms); };
  screen_power::dark = []() { return false; };
  screen_power::wake = nullptr;
  a = Life{};
  s = Standby{};
  s.touch(now_ms);
  a.glass.close_settings = []() { told("close settings"); };
  a.glass.prepare = [](const screen_alert::Alert &card) { told("prepare " + card.title); };
  a.glass.fill = [](const screen_alert::Alert &card) { told("fill " + card.title); };
  a.glass.reveal = [](bool shown) { told(shown ? "card comes" : "card goes"); };
  a.glass.clear = []() { told("clear"); };
  a.glass.wake = []() { told("wake"); s.wake(now_ms); };
  a.glass.stir = []() { s.stir(now_ms); };
  a.glass.light = [](int to, int ms) { told("light " + std::to_string(to) + " in " + std::to_string(ms)); };
  a.glass.report = [](const char *action, const std::string &title) { told(std::string("report ") + action + " " + title); };
  a.glass.later = [](uint32_t ms) { alert_timer = true; alert_at = now_ms + ms; };
  a.glass.say = [](const char *line) { log_lines.push_back(line); };
  s.glass.owned = []() -> uint8_t { return a.up() ? screen_standby::ALERT : 0; };
  s.glass.standby_level = []() { return 20; };
  s.glass.light = [](int to, int ms) { told("light " + std::to_string(to) + " in " + std::to_string(ms)); };
  s.glass.alert_close = []() { a.dismiss("remote"); };
  s.glass.apply = []() { told("standby shows"); s.show(); };
  s.glass.later = [](uint32_t ms) { standby_timer = true; standby_at = now_ms + ms; };
}

// The clock moves on, and each module's timer fires on its way as its script would.
static void to(uint32_t when) {
  for (;;) {
    const bool alert_due = alert_timer && static_cast<int32_t>(when - alert_at) >= 0;
    const bool standby_due = standby_timer && static_cast<int32_t>(when - standby_at) >= 0;
    if (!alert_due && !standby_due) break;
    if (alert_due && (!standby_due || static_cast<int32_t>(alert_at - standby_at) <= 0)) {
      now_ms = alert_at;
      alert_timer = false;
      a.due(now_ms);
    } else {
      now_ms = standby_at;
      standby_timer = false;
      s.due(now_ms);
    }
  }
  now_ms = when;
}
static void after(uint32_t ms) { to(now_ms + ms); }

static void it_shows() {
  fresh();
  a.show(alert("Washing done"), now_ms);
  assert(a.up() && a.title() == "Washing done");
  // The settings page closes first, the card is made before it is filled, the screen wakes, then the card comes.
  assert((trail == std::vector<std::string>{"close settings", "prepare Washing done", "fill Washing done", "wake",
                                            "light 80 in 200", "card comes"}));
  assert(logged("show \"Washing done\" timeout=0 flash=0 buttons=1"));
  // Without a time it stays until someone ends it.
  trail.clear();
  after(24 * 3600 * 1000);
  assert(a.up() && trail.empty());

  // What hangs on the card (a camera's frame, a plugin) sees no alert up yet when it prepares, and one when it fills.
  fresh();
  a.glass.prepare = [](const screen_alert::Alert &) { told(a.up() ? "prepared up" : "prepared before"); };
  a.glass.fill = [](const screen_alert::Alert &) { told(a.up() ? "filled up" : "filled before"); };
  a.show(alert("Door"), now_ms);
  assert(has("prepared before") && has("filled up"));

  // Two buttons, a colour: the log and what a change of look asks.
  fresh();
  auto choice = alert("Call from the gate", 0, false, "Decline");
  choice.color = 0xFFE1C6;
  a.show(choice, now_ms);
  assert(logged("show \"Call from the gate\" timeout=0 flash=0 buttons=2") && a.color() == 0xFFE1C6);
}

static void it_ends_for_a_reason() {
  for (const char *reason : {"ok", "button2", "remote"}) {
    fresh();
    a.show(alert("Washing done"), now_ms);
    after(5000);
    trail.clear();
    a.dismiss(reason);
    assert(!a.up());
    // What hung on the card goes, the card goes, the light is back at its brightness, and Home Assistant hears why.
    assert((trail == std::vector<std::string>{"clear", "card goes", "light 80 in 80", std::string("report ") + reason + " Washing done"}));
    assert(logged(std::string("dismissed: ") + reason));
    // The standby time counts from the ending.
    assert(s.since_touch(now_ms) == 0);
    // Once: a second ending of the same alert is nothing.
    trail.clear();
    a.dismiss(reason);
    assert(trail.empty());
  }
  // Nothing up, nothing to end.
  fresh();
  a.dismiss("ok");
  assert(trail.empty() && log_lines.empty());
}

static void its_time_runs_out() {
  fresh();
  a.show(alert("Oven", 30), now_ms);
  after(29999);
  assert(a.up());
  after(1);
  assert(!a.up() && has("report timeout Oven") && logged("dismissed: timeout"));

  // Ended by a finger first: the time that was running closes nothing later, not even the next alert.
  fresh();
  a.show(alert("Oven", 30), now_ms);
  after(10000);
  a.dismiss("ok");
  a.show(alert("Dryer"), now_ms);
  after(60000);
  assert(a.up() && a.title() == "Dryer");
}

static void a_new_alert_replaces_it() {
  fresh();
  a.show(alert("Oven", 30), now_ms);
  after(10000);
  trail.clear();
  a.show(alert("Door", 20), now_ms);
  // The one that was up reports "replaced" with its own title, before the new card is made.
  assert(place("report replaced Oven") == 0 && place("report replaced Oven") < place("prepare Door"));
  assert(a.up() && a.title() == "Door");
  // The first one's time is gone: the new one closes on its own.
  after(19999);
  assert(a.up());
  after(1);
  assert(!a.up() && has("report timeout Door") && count("report timeout Oven") == 0);

  // A new alert without a time stays, however much time the one before it had left.
  fresh();
  a.show(alert("Oven", 30), now_ms);
  after(10000);
  a.show(alert("Dryer"), now_ms);
  after(3600 * 1000);
  assert(a.up() && a.title() == "Dryer" && count("report timeout Oven") == 0 && count("report timeout Dryer") == 0);
}

static void it_flashes() {
  fresh();
  a.show(alert("Door", 0, true), now_ms);
  // Four blinks from the moment it arrives: dark for 140 ms, lit for 180, and it ends lit.
  std::vector<std::string> lights;
  std::vector<uint32_t> times;
  const size_t from = trail.size();
  const uint32_t start = now_ms;
  for (uint32_t t = 0; t <= 2000; t += 10) {
    const size_t before = trail.size();
    to(start + t);
    for (size_t i = before; i < trail.size(); ++i) {
      lights.push_back(trail[i]);
      times.push_back(t);
    }
  }
  (void) from;
  assert((lights == std::vector<std::string>{"light 80 in 60", "light 0 in 60", "light 80 in 60", "light 0 in 60",
                                             "light 80 in 60", "light 0 in 60", "light 80 in 60"}));
  assert((times == std::vector<uint32_t>{140, 320, 460, 640, 780, 960, 1100}));
  // The first dark came with the alert itself, after the wake's light.
  assert(place("light 80 in 200") < place("light 0 in 60") && place("light 0 in 60") < place("light 80 in 60"));
  assert(count("light 0 in 60") == 4 && count("light 80 in 60") == 4);

  // An ending in the dark half of a blink stops the blinks and brings the light back.
  fresh();
  a.show(alert("Door", 0, true), now_ms);
  after(100);
  trail.clear();
  a.dismiss("ok");
  assert(has("light 80 in 80"));
  trail.clear();
  after(5000);
  assert(trail.empty());

  // A board whose backlight never goes dark blinks nothing, and says so: the card is the signal.
  fresh();
  a.blinks = 0;
  a.show(alert("Door", 0, true), now_ms);
  after(5000);
  assert(count("light 0 in 60") == 0 && logged("no backlight blinks on this board") && a.up());

  // A flash and a time together: both run, on the one timer.
  fresh();
  a.show(alert("Door", 2, true), now_ms);
  after(1999);
  assert(a.up() && count("light 0 in 60") == 4);
  after(1);
  assert(!a.up());
}

static void the_screens_own_alert_tells_nobody() {
  fresh();
  a.own_next();
  a.show(alert("No answer from Home Assistant"), now_ms);
  a.dismiss("ok");
  assert(!a.up() && count("report ok No answer from Home Assistant") == 0);
  // Only that one: the next alert is Home Assistant's again.
  a.show(alert("Door"), now_ms);
  a.dismiss("ok");
  assert(has("report ok Door"));
  // Replaced by an alert of Home Assistant, it still reports nothing.
  fresh();
  a.own_next();
  a.show(alert("No answer from Home Assistant"), now_ms);
  a.show(alert("Door"), now_ms);
  for (const auto &line : trail) assert(line.rfind("report", 0) != 0);
}

static void it_meets_the_standby() {
  // An alert lights a screen in standby, a standby by hand too, and ends its hold.
  fresh();
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(s.in_standby() && s.by_hand());
  after(5000);
  a.show(alert("Door"), now_ms);
  assert(!s.in_standby() && !s.by_hand());

  // It holds the screen lit for as long as it is up, however long the standby time is over.
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  // It ends: the standby time counts from there.
  a.dismiss("ok");
  after(599 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  after(2000);
  s.tick(now_ms);
  assert(s.in_standby());

  // A standby by hand closes an alert that is up, as closed from Home Assistant, and then goes to standby: the light
  // that came back for the ending goes down to the standby's level right after.
  fresh();
  a.show(alert("Washing done"), now_ms);
  after(3000);
  trail.clear();
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(!a.up() && s.in_standby());
  assert(has("report remote Washing done"));
  assert(place("light 80 in 80") >= 0 && place("light 80 in 80") < place("standby shows"));

  // The home key held under an alert is refused: the lift is a tap home.
  fresh();
  a.show(alert("Washing done"), now_ms);
  assert(!s.hold_home(now_ms) && a.up() && !s.in_standby());
}

int main() {
  it_shows();
  it_ends_for_a_reason();
  its_time_runs_out();
  a_new_alert_replaces_it();
  it_flashes();
  the_screens_own_alert_tells_nobody();
  it_meets_the_standby();
  std::puts("alert_life ok");
}
