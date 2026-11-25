#pragma once
// An alert's life (firmware 0.64.0+; before, scripts and globals of packages/core.yaml and features/backlight.yaml):
// the card a Home Assistant automation puts over the whole screen (the actions show_alert and show_alert_choice), or
// the screen itself (an explanation of its own). What the card says and where its parts stand is alert_overlay.h's
// and LVGL's; this decides when it is up, what ends it and what Home Assistant hears. One state, private here.
//
// show(): a new alert replaces one that is up, which reports "replaced". The settings page closes, the card is made
// (glass.prepare: its keys and places, then what hangs on an alert about to show, such as the frame for a camera's
// picture), filled (glass.fill) and revealed, and the screen wakes: an alert lights a screen in standby, a standby by
// hand too, and holds it lit for as long as it is up (up(), which the standby asks).
//
// It ends (dismiss) by its OK ("ok"), its second button ("button2"), its time running out ("timeout", when it has
// one), or from Home Assistant: the action dismiss_alert and a standby by hand ("remote"). Every ending takes what
// hung on the card away, puts the backlight back at its brightness, starts the standby time again and reports itself
// as esphome.screen_alert with the alert's title. An alert of the screen's own (own_next) reports nothing: no
// automation takes it for its own.
//
// A flash: the backlight blinks `blinks` times when the alert arrives, BLINK_DARK_MS dark and BLINK_LIT_MS lit each.
// The number is the board's: a backlight that must never go dark gives 0, and the card itself is the signal.
//
// Who may ask what. The actions, scripts and the card's two keys of packages/core.yaml call show, dismiss, flash,
// timeout and report. The standby closes an alert (a standby by hand) and asks up(). What draws on the card hangs on
// the glass and only asks: the camera's picture (camera_answer_lvgl.h: alert_prepare runs in glass.prepare,
// alert_clear in glass.clear, and opening the camera from the card takes title()), a plugin's on_alert (glass.prepare),
// a change of look (color()). A doorbell's ring and a call are no alerts: each is a view of its own that holds the
// glass by itself, and neither calls in here.
//
// Free of LVGL and ESPHome. packages/core.yaml binds the glass at boot (`the().glass`) and one script of it is the
// timer (`later`, due()). tests/test_alert_life.cpp runs every rule above, the meeting with the standby included, and
// `tools/render/run.py guition --only alertlife` ends an alert every way on the real firmware and hears the event.
#include <cstdint>
#include <cstdio>
#include <string>
#include "alert_overlay.h"
#include "one_timer.h"
#include "screen_settings.h"

namespace alert_life {

// A blink: the backlight fades out and in over BLINK_FADE_MS, and stays dark and lit this long from the start of each
// fade. An ending brings the light back over END_FADE_MS.
constexpr int BLINK_FADE_MS = 60, END_FADE_MS = 80;
constexpr uint32_t BLINK_DARK_MS = 140, BLINK_LIT_MS = 180;

// What only the firmware around this can do. Plain function pointers, each a no-op until packages/core.yaml binds it.
struct Glass {
  void (*close_settings)() = []() {};                            // the settings page closes: an alert outranks it
  void (*prepare)(const screen_alert::Alert &) = [](const screen_alert::Alert &) {};  // the card's keys and places,
                                                                 // then what hangs on an alert about to show
  void (*fill)(const screen_alert::Alert &) = [](const screen_alert::Alert &) {};     // its words and its colour
  void (*reveal)(bool) = [](bool) {};                            // the card comes (true) or goes
  void (*clear)() = []() {};                                     // what hung on the card goes: a camera's picture
  void (*wake)() = []() {};                                      // the screen lights and its cards close
  void (*stir)() = []() {};                                      // the standby time counts from now
  void (*light)(int, int) = [](int, int) {};                     // the backlight to a level (percent), over so many ms
  void (*report)(const char *, const std::string &) = [](const char *, const std::string &) {};  // an ending and
                                                                 // the alert's title, to Home Assistant
  void (*later)(uint32_t) = [](uint32_t) {};                     // due() after so many ms; a new ask replaces the last
  void (*say)(const char *) = [](const char *) {};               // one line for the log
};

class Life {
 public:
  Glass glass;
  // How often the backlight blinks for an alert that flashes: the board's (ALERT_BLINKS), 0 where it never goes dark.
  int blinks = 4;

  // ---- to read, never to write ----
  bool up() const { return up_; }                    // an alert is on the glass
  const std::string &title() const { return title_; }
  uint32_t color() const { return color_; }          // the card's colour as the alert named it; 0: the normal card

  // The next alert is the screen's own: it reports nothing to Home Assistant.
  void own_next() { own_next_ = true; }

  void show(const screen_alert::Alert &alert, uint32_t now) {
    if (up_) report("replaced");
    own_ = own_next_;
    own_next_ = false;
    glass.close_settings();
    glass.prepare(alert);
    up_ = true;
    title_ = alert.title;
    color_ = alert.color;
    glass.fill(alert);
    char line[160];
    std::snprintf(line, sizeof(line), "show \"%s\" timeout=%d flash=%d buttons=%d", alert.title.c_str(), alert.timeout_seconds,
                  static_cast<int>(alert.flash), alert.button2.empty() ? 1 : 2);
    glass.say(line);
    glass.wake();
    glass.reveal(true);
    // The time of the alert before it is over; its blinks run out by themselves.
    waits_.stop(END);
    if (alert.flash) flash(now);
    if (alert.timeout_seconds > 0) timeout(alert.timeout_seconds, now);
    waits_.ask(now, glass.later);
  }

  // The alert ends, for the reason Home Assistant hears. Nothing when none is up.
  void dismiss(const char *reason) {
    if (!up_) return;
    up_ = false;
    glass.stir();
    glass.clear();
    char line[64];
    std::snprintf(line, sizeof(line), "dismissed: %s", reason);
    glass.say(line);
    glass.reveal(false);
    waits_.stop(END);
    waits_.stop(BLINK);
    glass.light(static_cast<int>(screen_settings::current.brightness), END_FADE_MS);
    report(reason);
  }

  // The backlight's blinks, from the start.
  void flash(uint32_t now) {
    if (blinks <= 0) {
      glass.say("no backlight blinks on this board");
      return;
    }
    step_ = 0;
    blink(now);
    waits_.ask(now, glass.later);
  }

  // The alert closes by itself after so many seconds; a new time replaces the last.
  void timeout(int seconds, uint32_t now) {
    waits_.set(END, static_cast<uint32_t>(seconds) * 1000UL, now);
    waits_.ask(now, glass.later);
  }

  // An ending, to Home Assistant, unless the alert is the screen's own.
  void report(const char *action) {
    if (!own_) glass.report(action, title_);
  }

  // The timer fired.
  void due(uint32_t now) {
    if (waits_.reached(BLINK, now)) blink(now);
    if (waits_.reached(END, now)) dismiss("timeout");
    waits_.ask(now, glass.later);
  }

 private:
  enum Wait : uint8_t { END, BLINK, WAITS };
  one_timer::Waits<WAITS> waits_;
  bool up_ = false, own_ = false, own_next_ = false;
  std::string title_;
  uint32_t color_ = 0;
  int step_ = 0;  // of the blinks: even steps go dark, odd ones come back

  // One half of a blink, and the wait for the next; after the last one the light stays as it is, lit.
  void blink(uint32_t now) {
    const bool dark = step_ % 2 == 0;
    glass.light(dark ? 0 : static_cast<int>(screen_settings::current.brightness), BLINK_FADE_MS);
    ++step_;
    if (step_ < blinks * 2) waits_.set(BLINK, dark ? BLINK_DARK_MS : BLINK_LIT_MS, now);
  }
};

// The screen's one alert.
inline Life &the() {
  static Life one;
  return one;
}

}  // namespace alert_life
