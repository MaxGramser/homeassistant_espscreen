// The screen's standby, run: every rule of components/smart_display/screen_standby.h on a glass that writes down what
// it was told, in order, with a clock the test moves. What packages/core.yaml binds for real is bound here to a trail.
#include "components/smart_display/screen_standby.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace screen_standby;

static uint32_t now_ms = 1000;
static std::vector<std::string> trail;  // what the glass was told, in order
static std::vector<std::string> log_lines;
static bool timer_set = false;
static uint32_t timer_at = 0;
static uint8_t owners = 0;
static bool is_away = false, can = true, saver_up = false;
static uint32_t home_seconds = 0;
static int level = 20;
static int alerts_closed = 0;
static Standby s;  // the standby of the case that runs

static void told(const std::string &what) { trail.push_back(what); }
static bool has(const std::string &what) {
  for (const auto &line : trail) if (line == what) return true;
  return false;
}
static int place(const std::string &what) {
  for (size_t i = 0; i < trail.size(); ++i) if (trail[i] == what) return static_cast<int>(i);
  return -1;
}
static int count(const std::string &what) {
  int n = 0;
  for (const auto &line : trail) n += line == what;
  return n;
}
static bool logged(const std::string &line) { return !log_lines.empty() && log_lines.back() == line; }

// A screen as it starts: lit, Auto standby on at 600 s, a standby level of 20, nothing open. Every case gets a standby
// of its own; what it works on (the settings, the power saving) is put back too.
static void fresh() {
  now_ms = 1000;
  trail.clear();
  log_lines.clear();
  timer_set = false;
  owners = 0;
  is_away = false;
  can = true;
  saver_up = false;
  home_seconds = 0;
  level = 20;
  alerts_closed = 0;
  screen_settings::current = {};
  screen_power::saving = screen_power::touching = screen_power::settling = screen_power::was_tap = false;
  screen_power::freeze = [](bool on) { told(on ? "freeze" : "draw"); };
  screen_power::later = [](uint32_t ms) { s.power_wait(ms, now_ms); };
  screen_power::dark = []() { return s.in_standby() && level == 0; };
  screen_power::wake = []() { s.wake(now_ms); };
  s = Standby{};
  s.touch(now_ms);
  s.glass.can_standby = []() { return can; };
  s.glass.owned = []() { return owners; };
  s.glass.away = []() { return is_away; };
  s.glass.home_after = []() { return home_seconds; };
  s.glass.standby_level = []() { return level; };
  s.glass.light = [](int to, int ms) { told("light " + std::to_string(to) + " in " + std::to_string(ms)); };
  s.glass.overlay = [](bool on) { told(on ? "overlay on" : "overlay off"); };
  s.glass.saver = [](bool on) { saver_up = on; told(on ? "saver on" : "saver off"); };
  s.glass.saver_wake = []() { const bool was = saver_up; saver_up = false; return was; };
  s.glass.close_settings = []() { told("close settings"); };
  s.glass.close_cards = []() { told("close cards"); };
  s.glass.page_1 = []() { is_away = false; told("page 1"); };
  s.glass.alert_close = []() { ++alerts_closed; owners &= static_cast<uint8_t>(~ALERT); told("close alert"); };
  s.glass.apply = []() { told("apply"); s.show(); };
  s.glass.later = [](uint32_t ms) { timer_set = true; timer_at = now_ms + ms; };
  s.glass.say = [](const char *line) { log_lines.push_back(line); };
}
// When the two clocks last started.
static uint32_t touch_at() { return now_ms - s.since_touch(now_ms); }
static uint32_t use_at() { return now_ms - s.since_use(now_ms); }

// The clock moves on, and the timer fires on its way as ESPHome's script would.
static void to(uint32_t when) {
  while (timer_set && static_cast<int32_t>(when - timer_at) >= 0) {
    now_ms = timer_at;
    timer_set = false;
    s.due(now_ms);
  }
  now_ms = when;
}
static void after(uint32_t ms) { to(now_ms + ms); }
// The loop's next pass: whatever waits 0 ms runs.
static void pass() { after(0); }

static void the_standby_time() {
  fresh();
  // Nothing before the time is over, and the second it is: the page and the cards close, then the glass follows.
  after(600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby() && trail.empty());
  after(1);
  s.tick(now_ms);
  assert(s.in_standby() && !s.by_hand());
  assert((trail == std::vector<std::string>{"close settings", "close cards", "apply", "light 20 in 1500", "overlay on",
                                            "saver on"}));
  // It dims once: a screen in standby is left alone.
  trail.clear();
  after(5000);
  s.tick(now_ms);
  assert(trail.empty());

  // A touch starts the time again.
  fresh();
  after(599 * 1000);
  s.touch(now_ms);
  after(599 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());

  // Auto standby off, a s.touched() on the glass, a calibration, an alert and a doorbell's ring each hold the screen lit.
  fresh();
  screen_settings::current.standby_enabled = 0;
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  fresh();
  s.contact(true, now_ms);
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  for (uint8_t owner : {CALIBRATION, ALERT, RING}) {
    fresh();
    owners = owner;
    after(3600 * 1000);
    s.tick(now_ms);
    assert(!s.in_standby());
    owners = 0;
    s.tick(now_ms);
    assert(s.in_standby());
  }

  // A board whose backlight never goes dark has no standby.
  fresh();
  can = false;
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby() && trail.empty());
}

static void a_dark_standby_saves_power() {
  fresh();
  level = 0;
  s.standby_by_time(now_ms);
  // Dark: no screensaver, and drawing stops once the backlight has faded out.
  assert(has("light 0 in 1500") && has("saver off") && !has("freeze"));
  after(screen_power::REST_MS - 1);
  assert(!has("freeze"));
  after(1);
  assert(has("freeze") && screen_power::saving);
  // A wake draws again before the light comes up.
  trail.clear();
  s.wake(now_ms);
  assert(!screen_power::saving);
  assert(place("draw") >= 0 && place("draw") < place("light 100 in 200"));

  // A wake before the fade is over: the screen never stops drawing, whatever the timer still does.
  fresh();
  level = 0;
  s.standby_by_time(now_ms);
  after(500);
  s.wake(now_ms);
  after(10000);
  assert(!has("freeze") && !screen_power::saving);

  // A way home asked for while a dark standby waits to save power: both waits are kept, each fires at its time.
  fresh();
  level = 0;
  s.standby_by_time(now_ms);
  s.go_home(now_ms);
  pass();
  assert(has("page 1") && !has("freeze"));
  after(screen_power::REST_MS);
  assert(has("freeze"));
}

static void by_hand_holds_and_closes_an_alert() {
  fresh();
  owners = ALERT;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(logged("Standby from Home Assistant's Sleep"));
  assert(s.in_standby() && s.by_hand() && alerts_closed == 1);
  // The alert closes before anything of the standby shows.
  assert(place("close alert") == 0 && place("close alert") < place("apply"));
  // A screensaver that is set shows on a standby by s.by_hand() as on any other.
  assert(has("saver on"));

  // It holds with Auto standby off, whatever applies the settings again; a standby the time brought does not.
  screen_settings::current.standby_enabled = 0;
  s.show();
  assert(s.in_standby());
  fresh();
  s.standby_by_time(now_ms);
  screen_settings::current.standby_enabled = 0;
  trail.clear();
  s.show();
  assert(!s.in_standby() && has("light 100 in 200") && has("overlay off") && has("saver off"));

  // A Sleep on a screen the time s.in_standby() makes it a standby by s.by_hand().
  fresh();
  s.standby_by_time(now_ms);
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(s.in_standby() && s.by_hand());

  // Not while the touch calibration runs: the crosses stay lit, and an alert stays too.
  fresh();
  owners = CALIBRATION;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(!s.in_standby() && !s.by_hand() && trail.empty());
  assert(logged("Standby from Home Assistant's Sleep ignored: touch calibration is running"));

  // A board that cannot go dark: nothing but the alert closing.
  fresh();
  can = false;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(!s.in_standby() && !s.by_hand() && (trail == std::vector<std::string>{"close alert"}));
}

static void auto_standby_turned_off_while_dark() {
  // A screen the time s.in_standby() to a level of 0 saves power. Auto standby turned off lights it: drawing comes back before
  // the light, and the overlay and the screensaver go.
  fresh();
  level = 0;
  s.standby_by_time(now_ms);
  after(screen_power::REST_MS);
  assert(screen_power::saving);
  screen_settings::current.standby_enabled = 0;
  trail.clear();
  s.show();
  assert(!s.in_standby() && !screen_power::saving);
  assert((trail == std::vector<std::string>{"light 100 in 200", "draw", "overlay off", "saver off"}));

  // A standby by s.by_hand() stays dark and goes on saving, whatever applies the settings again.
  fresh();
  level = 0;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  after(screen_power::REST_MS);
  assert(screen_power::saving);
  screen_settings::current.standby_enabled = 0;
  trail.clear();
  s.show();
  assert(s.in_standby() && screen_power::saving && !has("draw"));
  assert((trail == std::vector<std::string>{"light 0 in 1500", "overlay on", "saver off"}));
}

static void an_alert_in_standby() {
  // An alert lights a screen in standby (the alert's script takes s.wake()), a standby by s.by_hand() too, and holds it lit for
  // as long as it is up, however long the standby time is over.
  fresh();
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  after(5000);
  trail.clear();
  s.wake(now_ms);
  owners = ALERT;
  assert(!s.in_standby() && !s.by_hand() && has("light 100 in 0"));
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  // It ends: the standby time counts from there, not from the last touch.
  owners = 0;
  s.stir(now_ms);
  after(599 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
  after(2000);
  s.tick(now_ms);
  assert(s.in_standby() && !s.by_hand());
}

// A ring that closes with the cards, as the doorbell's view does (runtime_tiles::dismiss).
static void cards_take_the_ring() {
  s.glass.close_cards = []() {
    if (owners & RING) {
      owners &= static_cast<uint8_t>(~RING);
      told("ring closed");
    }
    told("close cards");
  };
}

static void a_standby_by_hand_closes_a_ring() {
  // A doorbell's ring is a view on the glass that holds the screen lit: the standby time leaves it alone and the home
  // key held is refused under it. A standby someone asks for with Home Assistant's Sleep or the board's key takes it
  // away with every other card (glass.close_cards, where the doorbell reports the ring closed and gives the speaker
  // back: module_doorbell.cpp through runtime_tiles::dismiss), and the screen goes to standby.
  fresh();
  cards_take_the_ring();
  owners = RING;
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby() && trail.empty());
  assert(!s.hold_home(now_ms) && trail.empty());
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(s.in_standby() && s.by_hand() && owners == 0);
  // The ring closes before the standby shows itself.
  assert(place("ring closed") >= 0 && place("ring closed") < place("apply"));
  assert(logged("Standby from Home Assistant's Sleep"));

  // The board's key does the same.
  fresh();
  cards_take_the_ring();
  owners = RING;
  s.key(now_ms);
  assert(s.in_standby() && has("ring closed") && owners == 0);

  // With Back to page 1 on standby it closes one pass later, with the cards, before page 1 and the screensaver.
  fresh();
  cards_take_the_ring();
  screen_settings::current.home_on_standby = 1;
  owners = RING;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(s.in_standby() && !has("ring closed"));
  pass();
  assert(place("ring closed") < place("page 1") && place("page 1") < place("saver on") && owners == 0);

  // A ring that comes during a standby is no business of the standby's: the doorbell wakes the screen itself (an
  // event), and the standby time then waits for it.
  fresh();
  s.standby_by_time(now_ms);
  s.wake_from("the doorbell", Wake::EVENT, now_ms);
  owners = RING;
  after(3600 * 1000);
  s.tick(now_ms);
  assert(!s.in_standby());
}

static void page_1_comes_before_the_screensaver() {
  // GitHub #457. With Back to page 1 on standby the standby goes home, never at the bottom of the call that asked
  // (Home Assistant's Sleep comes inside the API's call), and its screensaver opens after page 1, not before.
  fresh();
  screen_settings::current.home_on_standby = 1;
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  assert(s.in_standby());
  assert(!has("page 1") && !has("close cards") && !has("apply") && !has("saver on"));
  pass();
  assert((trail == std::vector<std::string>{"close alert", "close settings", "close cards", "page 1", "apply",
                                            "light 20 in 1500", "overlay on", "saver on"}));

  // A way home asked for in the same pass is that one page 1, not a second one behind the screensaver.
  fresh();
  screen_settings::current.home_on_standby = 1;
  s.go_home(now_ms);
  s.standby_by_time(now_ms);
  s.go_home(now_ms);
  pass();
  assert(count("page 1") == 1 && place("page 1") < place("saver on"));
  assert(trail.back() == "saver on");
  // And nothing is left waiting.
  trail.clear();
  after(5000);
  assert(trail.empty());

  // Without the setting the page stays, and the standby shows at once.
  fresh();
  s.standby_by_time(now_ms);
  assert(!has("page 1") && trail.back() == "saver on");
}

static void every_wake_takes_one_way() {
  fresh();
  s.standby_by_time(now_ms);
  after(5000);
  trail.clear();
  const uint32_t used = use_at();
  s.wake(now_ms);
  assert(!s.in_standby() && !s.by_hand());
  // From a screensaver the light is up at once, and the overlay and the cards go.
  assert((trail == std::vector<std::string>{"light 100 in 0", "overlay off", "close cards"}));
  // The standby time starts again; nobody used a page.
  assert(touch_at() == now_ms && use_at() == used);

  // From the dark it fades in.
  fresh();
  level = 0;
  s.standby_by_time(now_ms);
  trail.clear();
  s.wake(now_ms);
  assert(has("light 100 in 200"));

  // A wake of a lit screen keeps an open settings page: only the cards close.
  fresh();
  s.wake(now_ms);
  assert(!has("close settings") && has("close cards"));
}

static void wake_from_lights_or_only_restarts_the_time() {
  // A lit screen: the standby time alone starts again, and Back to page 1 goes on counting.
  fresh();
  after(4000);
  const uint32_t used = use_at();
  s.wake_from("Home Assistant", Wake::REMOTE, now_ms);
  assert(logged("Wake from Home Assistant, screen on"));
  assert(trail.empty() && touch_at() == now_ms && use_at() == used);

  // A screen in standby lights up.
  s.standby_by_time(now_ms);
  after(4000);
  s.wake_from("Home Assistant", Wake::REMOTE, now_ms);
  assert(logged("Wake from Home Assistant, screen in standby"));
  assert(!s.in_standby() && use_at() == used);

  // A page whose time ran out during standby: the wake brings page 1, on the loop's next pass.
  fresh();
  home_seconds = 30;
  is_away = true;
  s.standby_by_time(now_ms);
  after(60 * 1000);
  s.tick(now_ms);
  assert(!has("page 1"));
  trail.clear();
  s.wake_from("Home Assistant", Wake::REMOTE, now_ms);
  assert(!has("page 1"));
  pass();
  assert(has("page 1"));
}

static void a_sensed_wake_waits_for_the_quiet() {
  // No standby by s.by_hand(): every sensed wake lights the screen.
  fresh();
  s.standby_by_time(now_ms);
  after(2000);
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(!s.in_standby());

  // By s.by_hand() at 1000: walking away is motion, held, and each one starts the quiet again.
  fresh();
  s.standby_by_hand("the home key held", now_ms);
  to(2000);
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(s.in_standby() && logged("Wake from plugin camera held: standby by hand, waiting for 60 s without movement"));
  to(2000 + QUIET_MS - 1);
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(s.in_standby());
  to(2000 + 2 * QUIET_MS - 2);
  s.wake_from("Home Assistant's Motion", Wake::SENSED, now_ms);
  assert(s.in_standby());
  // A full quiet after the last one: someone came.
  to(2000 + 3 * QUIET_MS);
  s.wake_from("the board moved", Wake::SENSED, now_ms);
  assert(!s.in_standby() && !s.by_hand());

  // Nobody moved at all after the standby: the first motion after the quiet wakes.
  fresh();
  s.standby_by_hand("the board's key", now_ms);
  after(QUIET_MS);
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(!s.in_standby());

  // The policy is one line: of the kinds, only a sensed wake waits. The board's key, Home Assistant's Wake and an event
  // (a popup, a call, a doorbell) light a standby by s.by_hand() at once.
  assert(waits_for_quiet(Wake::SENSED));
  for (Wake kind : {Wake::KEY, Wake::REMOTE, Wake::EVENT}) {
    assert(!waits_for_quiet(kind));
    fresh();
    s.standby_by_hand("Home Assistant's Sleep", now_ms);
    after(1000);
    s.wake_from("something meant", kind, now_ms);
    assert(!s.in_standby());
  }

  // A caller with only a yes or no names itself, and one place says which kind that is: a script that is not sensed
  // means it (Home Assistant's Wake), a plugin that is not sensed shows something (a popup, a call, a doorbell).
  assert(kind_of(Asker::SCRIPT, false) == Wake::REMOTE && kind_of(Asker::PLUGIN, false) == Wake::EVENT);
  assert(kind_of(Asker::SCRIPT, true) == Wake::SENSED && kind_of(Asker::PLUGIN, true) == Wake::SENSED);
  for (Asker who : {Asker::SCRIPT, Asker::PLUGIN}) {
    fresh();
    s.standby_by_hand("Home Assistant's Sleep", now_ms);
    after(1000);
    s.wake_from("someone sensed", who, true, now_ms);
    assert(s.in_standby());
    s.wake_from("something meant or shown", who, false, now_ms);
    assert(!s.in_standby());
  }

  // Any wake ends the hold: a standby the time brings after it holds nothing.
  fresh();
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  after(1000);
  s.wake(now_ms);
  s.standby_by_time(now_ms);
  after(1000);
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(!s.in_standby());

  // So does an update coming in.
  fresh();
  s.standby_by_hand("Home Assistant's Sleep", now_ms);
  s.lit(now_ms);
  assert(!s.in_standby() && !s.by_hand());

  // A lit screen takes a sensed wake as any other: the standby time starts again.
  fresh();
  after(3000);
  s.wake_from("Home Assistant's Motion", Wake::SENSED, now_ms);
  assert(touch_at() == now_ms && logged("Wake from Home Assistant's Motion, screen on"));

  // The millisecond counter wraps.
  fresh();
  now_ms = UINT32_MAX - 10;
  s.standby_by_hand("the home key held", now_ms);
  now_ms = 20;
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(s.in_standby());
  now_ms = 20 + QUIET_MS;
  s.wake_from("plugin camera", Wake::SENSED, now_ms);
  assert(!s.in_standby());
}

static void the_boards_key_is_a_toggle() {
  fresh();
  after(3000);
  const uint32_t used = use_at();
  s.key(now_ms);
  assert(s.in_standby() && s.by_hand() && logged("Standby from the board's key"));
  after(3000);
  s.key(now_ms);
  assert(!s.in_standby() && logged("Wake from the board's key, screen in standby"));
  // A press is no touch: Back to page 1 goes on counting.
  assert(use_at() == used);

  // After its own standby the key wakes at once: it senses nobody, a person pressed it.
  fresh();
  s.key(now_ms);
  after(10);
  s.key(now_ms);
  assert(!s.in_standby());

  // In a calibration the key does nothing on a lit screen.
  fresh();
  owners = CALIBRATION;
  s.key(now_ms);
  assert(!s.in_standby());
}

static void the_home_key_held() {
  fresh();
  assert(s.hold_home(now_ms));
  assert(s.in_standby() && s.by_hand() && logged("Standby from the home key held"));
  // Refused, so the lift is a tap home after all: in standby already, an alert, a doorbell, a calibration, no standby.
  assert(!s.hold_home(now_ms));
  for (uint8_t owner : {CALIBRATION, ALERT, RING}) {
    fresh();
    owners = owner;
    assert(!s.hold_home(now_ms) && !s.in_standby() && trail.empty());
  }
  fresh();
  can = false;
  assert(!s.hold_home(now_ms) && !s.in_standby() && trail.empty());

  // It works with Auto standby off.
  fresh();
  screen_settings::current.standby_enabled = 0;
  assert(s.hold_home(now_ms));
  s.show();
  assert(s.in_standby());
}

static void back_to_page_1() {
  // Something open, nobody touched the glass for the time of the setting: home, from the loop's next pass.
  fresh();
  screen_settings::current.standby_enabled = 0;
  home_seconds = 30;
  is_away = true;
  after(30 * 1000);
  s.tick(now_ms);
  assert(trail.empty());
  after(1);
  s.tick(now_ms);
  assert(trail.empty());
  pass();
  assert((trail == std::vector<std::string>{"close settings", "close cards", "page 1"}));

  // Wake on every motion holds nothing up: only a touch counts.
  fresh();
  screen_settings::current.standby_enabled = 0;
  home_seconds = 30;
  is_away = true;
  for (int i = 0; i < 8; ++i) {
    after(5000);
    s.wake_from("Home Assistant", Wake::REMOTE, now_ms);
    s.tick(now_ms);
    pass();
  }
  assert(has("page 1"));

  // On page 1 already, the setting off, a s.touched() down, an alert, a doorbell, a calibration, in standby: nothing.
  fresh();
  home_seconds = 30;
  after(60 * 1000);
  s.page_1_when_due(now_ms);
  pass();
  assert(!has("page 1"));
  fresh();
  is_away = true;
  after(60 * 1000);
  s.page_1_when_due(now_ms);
  pass();
  assert(!has("page 1"));
  for (uint8_t owner : {CALIBRATION, ALERT, RING}) {
    fresh();
    home_seconds = 30;
    is_away = true;
    owners = owner;
    after(60 * 1000);
    s.page_1_when_due(now_ms);
    pass();
    assert(!has("page 1"));
  }
  // A finger that stays on the glass holds the page, however long ago it landed.
  fresh();
  home_seconds = 30;
  is_away = true;
  s.contact(true, now_ms);
  after(60 * 1000);
  s.page_1_when_due(now_ms);
  pass();
  assert(!has("page 1"));
  // In standby the page waits: a wake asks again.
  fresh();
  home_seconds = 30;
  is_away = true;
  s.standby_by_time(now_ms);
  after(60 * 1000);
  s.page_1_when_due(now_ms);
  pass();
  assert(s.in_standby() && !has("page 1"));

  // Home Assistant opening a page counts as use.
  fresh();
  home_seconds = 30;
  is_away = true;
  after(29 * 1000);
  s.use(now_ms);
  after(29 * 1000);
  s.page_1_when_due(now_ms);
  pass();
  assert(!has("page 1"));
}

static void the_clocks() {
  fresh();
  after(100);
  s.contact(true, now_ms);
  assert(s.touched() && touch_at() == now_ms && use_at() == now_ms);
  after(100);
  s.contact(false, now_ms);
  assert(!s.touched() && touch_at() == now_ms && use_at() == now_ms);
  after(100);
  const uint32_t used = use_at();
  s.stir(now_ms);
  assert(touch_at() == now_ms && use_at() == used);
}

int main() {
  the_standby_time();
  a_dark_standby_saves_power();
  by_hand_holds_and_closes_an_alert();
  a_standby_by_hand_closes_a_ring();
  auto_standby_turned_off_while_dark();
  an_alert_in_standby();
  page_1_comes_before_the_screensaver();
  every_wake_takes_one_way();
  wake_from_lights_or_only_restarts_the_time();
  a_sensed_wake_waits_for_the_quiet();
  the_boards_key_is_a_toggle();
  the_home_key_held();
  back_to_page_1();
  the_clocks();
  std::puts("screen_standby ok");
}
