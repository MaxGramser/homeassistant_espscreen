#pragma once
// The screen's standby (firmware 0.64.0+; before, scripts and globals of packages/core.yaml): whether the glass is lit
// or in standby, why it went there, which wake lights it, and the order in which a standby closes what is open, goes to
// page 1 and shows its screensaver. One state, kept private here: the firmware around it asks (in_standby()) and calls.
//
// Two ways in.
// - The standby time ran out (tick, Auto standby on): nobody was there.
// - Someone asked by hand (standby_by_hand: Home Assistant's Sleep, the board's key, the home key held). That one holds
//   with Auto standby off too, and it closes an alert that is up. Not while the touch calibration runs.
//
// The ways out, every one through wake():
// - a finger on the glass, and what puts something on the glass for someone to look at (an alert, a page or a camera
//   Home Assistant opens, an update coming in): wake() itself, which also closes the cards of a lit screen;
// - a wake that is no finger and shows nothing of its own goes through wake_from() as one of the kinds of `Wake`: the
//   board's key, Home Assistant's Wake, an event (a plugin's popup, a call, a doorbell) and a sensed wake (a plugin's
//   tessera::wake, Home Assistant's Motion, a board that moved). Each lights a screen in standby and only starts the
//   standby time of a lit one again.
// One line of policy, waits_for_quiet(), says which kind waits after a standby by hand: the sensed one. The person is
// still there then, and walking away from the glass is motion, so a sensed wake waits until the room went quiet: no
// sensed wake for QUIET_MS, and the next one lights the screen, someone came. Each one it holds starts the quiet
// again. The screen cannot know that motion stopped, only that no wake came. Any wake ends the hold.
//
// Every standby shows the screensaver while the backlight is still lit (show(), a level above 0), a standby by hand
// too. It opens last: the cards close and page 1 comes first, and from inside the API's call (Home Assistant's Sleep)
// page 1 is built one pass of the loop later, where the loop task's stack has the room (docs/ARCHITECTURE.md, "The
// loop's stack"); a screensaver that opened before it was closed by it again (GitHub #457).
//
// Two clocks. The standby time counts from the last touch, wake, alert that ended or Auto standby turned on
// (since_touch). Back to page 1 counts from the last touch or page Home Assistant opened (since_use), so a wake on every
// motion holds no card or second page up.
//
// Free of LVGL and ESPHome. packages/core.yaml binds the glass at boot (`the().glass`), its scripts and entities call
// in, and one script of it is the timer (`later`, due()). tests/test_screen_standby.cpp runs every rule above.
#include <cstdint>
#include <cstdio>
#include "one_timer.h"
#include "screen_power.h"
#include "screen_settings.h"

namespace screen_standby {

// The quiet a sensed wake waits for after a standby by hand.
constexpr uint32_t QUIET_MS = 60000;
// The backlight's way down into standby is slow, its way up quick: a wake must be seen at once.
constexpr int FADE_OUT_MS = 1500, FADE_IN_MS = 200;

// The wakes that are no finger, by name (wake_from).
enum class Wake : uint8_t {
  KEY,     // the board's own key: a person pressed it
  REMOTE,  // Home Assistant's Wake: a person, or an automation that means it
  EVENT,   // something to see or hear: a plugin's popup, a call, a doorbell
  SENSED,  // someone was sensed: a plugin's tessera::wake, Home Assistant's Motion, a board that moved
};
// The policy, in one line: which wake waits for the quiet after a standby by hand.
constexpr bool waits_for_quiet(Wake kind) { return kind == Wake::SENSED; }
// A caller that has only a yes or no on "this senses someone" names itself, and its kind follows here, in one place:
// a script of the YAML (Home Assistant's Wake and Motion buttons, a board's own sensor) means it when it is not
// sensed, a plugin (plugin_host::wake) shows or sounds something. plugin_host::wake hands over the kind itself once it
// can; until then its yes or no comes through here.
enum class Asker : uint8_t { SCRIPT, PLUGIN };
constexpr Wake kind_of(Asker who, bool sensed) {
  return sensed ? Wake::SENSED : who == Asker::PLUGIN ? Wake::EVENT : Wake::REMOTE;
}

// What holds the glass lit and keeps a standby away (Glass::owned).
enum Owner : uint8_t { CALIBRATION = 1, ALERT = 2, RING = 4 };

// What only the firmware around this can answer or do. Plain function pointers (a std::function costs flash of its
// own), each with an answer of its own until packages/core.yaml binds it, so nothing here asks whether one is there.
struct Glass {
  bool (*can_standby)() = []() { return true; };      // false: this board's backlight never goes dark
  uint8_t (*owned)() = []() -> uint8_t { return 0; };  // the Owner bits of now
  bool (*away)() = []() { return false; };            // a card, the settings page or another page than page 1 is up
  uint32_t (*home_after)() = []() -> uint32_t { return 0; };  // Back to page 1 after so many seconds; 0: off
  int (*standby_level)() = []() { return 0; };        // the backlight's level in standby now (night or day)

  void (*light)(int, int) = [](int, int) {};          // the backlight to a level (percent), over so many ms
  void (*overlay)(bool) = [](bool) {};                // the sheet over a screen in standby that takes the waking tap
  void (*saver)(bool) = [](bool) {};                  // the screensaver follows: in standby with the backlight lit
  bool (*saver_wake)() = []() { return false; };      // the screensaver goes; true when one was up
  void (*close_settings)() = []() {};                 // the settings page closes
  void (*close_cards)() = []() {};                    // every card closes
  void (*page_1)() = []() {};                         // page 1 of the tiles comes
  void (*alert_close)() = []() {};                    // an alert that is up closes, as closed from Home Assistant
  void (*apply)() = []() {};                          // the glass follows the settings and this state; it calls show()
  void (*later)(uint32_t) = [](uint32_t) {};          // due() after so many ms; a new ask replaces the last
  void (*say)(const char *) = [](const char *) {};    // one line for the log
};

class Standby {
 public:
  Glass glass;

  // ---- what the screen is doing: to read, never to write ----
  bool in_standby() const { return dimmed_; }  // the backlight at its standby level, which may be 0
  bool by_hand() const { return hand_; }       // that standby was asked for by hand
  bool touched() const { return finger_; }     // a finger is on the glass
  uint32_t since_touch(uint32_t now) const { return now - last_touch_; }  // the standby clock
  uint32_t since_use(uint32_t now) const { return now - last_use_; }      // the page clock

  // ---- the clocks ----
  // A finger on the glass, or one that just left: both clocks start again.
  void touch(uint32_t now) { last_touch_ = last_use_ = now; }
  void contact(bool down, uint32_t now) {
    touch(now);
    finger_ = down;
  }
  // The screen was used without a finger (Home Assistant opened a page): Back to page 1 counts from now.
  void use(uint32_t now) { last_use_ = now; }
  // The standby time alone starts again: Auto standby turned on, an alert that ended.
  void stir(uint32_t now) { last_touch_ = now; }

  // ---- the glass follows the state ----
  // The backlight, the power saving of a dark screen, the sheet that takes the waking tap and, last, the screensaver.
  // Auto standby turned off lights a screen the time dimmed, never one someone sent to standby by hand.
  void show() {
    if (dimmed_ && !screen_settings::current.standby_enabled && !hand_) dimmed_ = false;
    const int level = dimmed_ ? glass.standby_level() : static_cast<int>(screen_settings::current.brightness);
    glass.light(level, dimmed_ ? FADE_OUT_MS : FADE_IN_MS);
    // Dark (a level of 0): the power saving of screen_power.h, once the backlight has faded out. ESPHome puts its own
    // Wi-Fi mode back when it connects again, so a screen that is saving dozes again here, within the minute.
    if (dimmed_ && level == 0) {
      if (screen_power::saving) screen_power::doze_wifi(true);
      else screen_power::rest();
    } else {
      stop(POWER);
      screen_power::leave();
    }
    glass.overlay(dimmed_);
    glass.saver(dimmed_ && level > 0);
  }

  // ---- out of standby ----
  // Lit, whatever way: drawing and full-speed Wi-Fi come back before the light, the standby time starts again and the
  // hold of a standby by hand ends. wake() is this and the glass; an update coming in lights the glass itself.
  void lit(uint32_t now) {
    // Stopping the power saving's wait is tidiness, not a rule: a wait that still fires finds a lit screen and does
    // nothing (screen_power::due), so no test can tell this stop from its absence.
    stop(POWER);
    screen_power::leave();
    last_touch_ = now;
    dimmed_ = false;
    hand_ = false;
  }

  // The one way every wake takes. From a screensaver the light is up at once: a finger on it must see that it was
  // heard, and the page comes in sight under that light. From the dark it fades in.
  void wake(uint32_t now) {
    lit(now);
    const bool from_saver = glass.saver_wake();
    glass.light(static_cast<int>(screen_settings::current.brightness), from_saver ? 0 : FADE_IN_MS);
    glass.overlay(false);
    glass.close_cards();
  }

  // A wake that is no finger, of one of the kinds of `Wake`; `source` goes into the log. A screen in standby lights
  // up, and goes to page 1 at once when that time ran out meanwhile; a lit one only starts its standby time again. A
  // kind that waits for the quiet is held after a standby by hand until the room went quiet.
  void wake_from(const char *source, Wake kind, uint32_t now) {
    char line[128];
    if (waits_for_quiet(kind) && dimmed_ && hand_ && now - sensed_at_ < QUIET_MS) {
      sensed_at_ = now;
      std::snprintf(line, sizeof(line), "Wake from %s held: standby by hand, waiting for %u s without movement", source,
                    static_cast<unsigned>(QUIET_MS / 1000));
      glass.say(line);
      return;
    }
    std::snprintf(line, sizeof(line), "Wake from %s, screen %s", source, dimmed_ ? "in standby" : "on");
    glass.say(line);
    if (!dimmed_) {
      last_touch_ = now;
      return;
    }
    wake(now);
    page_1_when_due(now);
  }
  // The same for a caller that has only a yes or no on "this senses someone" (kind_of).
  void wake_from(const char *source, Asker who, bool sensed, uint32_t now) { wake_from(source, kind_of(who, sensed), now); }

  // ---- page 1 ----
  // Page 1 from the loop's next pass, never at the bottom of the call that asked (the API's): the latest ask wins.
  void go_home(uint32_t now) {
    going_home_ = true;
    wait(NEXT_PASS, 0, now);
  }

  // Back to page 1 by itself: a card, the settings page or another page left open, and nobody touched the glass for
  // the time of the setting. Not under a finger, a calibration, an alert or a doorbell's ring, and not in standby: a
  // wake asks again, so a page whose time ran out during standby lights up on page 1.
  void page_1_when_due(uint32_t now) {
    const uint32_t after = glass.home_after();
    if (!after || finger_ || glass.owned() || dimmed_) return;
    if (glass.away() && now - last_use_ > after * 1000UL) go_home(now);
  }

  // ---- into standby ----
  // The standby time ran out, or something stands in for it (tick; the host render's standby).
  void standby_by_time(uint32_t now) { enter(false, now); }

  // Standby by hand: Home Assistant's Sleep, the board's key, the home key held.
  void standby_by_hand(const char *source, uint32_t now) {
    char line[128];
    if (glass.owned() & CALIBRATION) {
      std::snprintf(line, sizeof(line), "Standby from %s ignored: touch calibration is running", source);
      glass.say(line);
      return;
    }
    std::snprintf(line, sizeof(line), "Standby from %s", source);
    glass.say(line);
    glass.alert_close();
    enter(true, now);
  }

  // The board's own key is a toggle: it wakes a screen in standby and sends a lit one there.
  void key(uint32_t now) {
    if (dimmed_) wake_from("the board's key", Wake::KEY, now);
    else standby_by_hand("the board's key", now);
  }

  // The home key held for half a second. False: the lift is a tap home after all (a board that cannot go dark, a
  // screen in standby already, a calibration, an alert, a doorbell ringing).
  bool hold_home(uint32_t now) {
    if (!glass.can_standby() || dimmed_ || glass.owned()) return false;
    standby_by_hand("the home key held", now);
    return true;
  }

  // ---- time ----
  // Every second: the standby time ran out (Auto standby on, and no finger, calibration, alert or doorbell's ring
  // holds the screen lit), and Back to page 1.
  void tick(uint32_t now) {
    const auto &settings = screen_settings::current;
    if (settings.standby_enabled && !dimmed_ && !finger_ && !glass.owned() &&
        now - last_touch_ > static_cast<uint32_t>(settings.standby_seconds) * 1000UL) {
      enter(false, now);
    }
    page_1_when_due(now);
  }

  // The power saving's wait (screen_power::later): due() runs screen_power::due() after so many ms.
  void power_wait(uint32_t ms, uint32_t now) { wait(POWER, ms, now); }

  // The timer fired. A standby that waited for page 1 goes there once, however many asked, and shows itself after it.
  void due(uint32_t now) {
    sorting_ = true;
    if (reached(NEXT_PASS, now)) {
      const bool land = landing_;
      const bool go = going_home_;
      landing_ = going_home_ = false;
      if (land || go) home();
      if (land) glass.apply();
    }
    if (reached(POWER, now)) screen_power::due();
    sorting_ = false;
    ask(now);
  }

 private:
  bool dimmed_ = false, hand_ = false, finger_ = false;
  uint32_t last_touch_ = 0, last_use_ = 0;
  uint32_t sensed_at_ = 0;      // the standby by hand, or the last sensed wake it held
  bool landing_ = false;        // a standby waits one pass for page 1, then shows itself
  bool going_home_ = false;     // page 1 was asked for, from the loop's next pass

  // The timer: every wait of the standby on one script (glass.later, one_timer.h).
  enum Wait : uint8_t { NEXT_PASS, POWER, WAITS };
  one_timer::Waits<WAITS> waits_;
  bool sorting_ = false;  // inside due(): it asks once, at its end

  void ask(uint32_t now) { waits_.ask(now, glass.later); }
  void wait(Wait which, uint32_t ms, uint32_t now) {
    waits_.set(which, ms, now);
    if (!sorting_) ask(now);
  }
  void stop(Wait which) { waits_.stop(which); }
  bool reached(Wait which, uint32_t now) { return waits_.reached(which, now); }

  // The settings page and every card close and page 1 comes: Back to page 1, the way home, a standby that goes home.
  void home() {
    glass.close_settings();
    glass.close_cards();
    glass.page_1();
  }

  // The settings page and every card close; with Back to page 1 on standby the screen goes home too, one pass later
  // (the head of this file), and only then shows itself. A board whose screen cannot go dark has no standby at all.
  void enter(bool hand, uint32_t now) {
    if (!glass.can_standby()) return;
    dimmed_ = true;
    if (hand) {
      hand_ = true;
      sensed_at_ = now;
    }
    if (screen_settings::current.home_on_standby) {
      landing_ = true;
      wait(NEXT_PASS, 0, now);
      return;
    }
    glass.close_settings();
    glass.close_cards();
    glass.apply();
  }
};

// The screen's one standby.
inline Standby &the() {
  static Standby one;
  return one;
}

}  // namespace screen_standby
