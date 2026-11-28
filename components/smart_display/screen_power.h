#pragma once
// Saving power while the glass is dark (standby or Sleep at brightness 0). The backlight is already off then; this
// stops the two things that still run for nobody, and gives up nothing a lit screen needs:
//
// - drawing: LVGL pauses (ESPHome's own lvgl.pause), so nothing is rendered or sent to the panel. The model, the cards
//   and every change from Home Assistant keep being applied; LVGL draws the whole screen once when it resumes.
// - Wi-Fi: the radio dozes between the router's beacons (ESP-IDF's modem sleep, ESPHome's `light`). A lit screen keeps
//   the mode its YAML has, `none` from the core and from the YAML ESP Screens writes, so its messages never wait for a
//   beacon (firmware 0.2.74+); a dark one dozes, and gets its own mode back when it wakes. The connection stays up, so
//   Home Assistant still sees the screen and can wake it. ESPHome's high-performance request can't do this: it only
//   lets go of a `none` the YAML does not have, and every screen's YAML has it.
//
// rest() saves REST_MS after the screen went dark, once the backlight has faded out; leave() comes first in every
// wake, before the backlight comes up. A touch on the dark glass resumes drawing at once (touched()), so the touch
// reaches the wake overlay as it always did. SETTLE_MS after the finger lifted, once LVGL has had the release, a screen
// that is still dark had a tap LVGL did not see: one of TAP_MS or more wakes it, a shorter one is noise on the glass
// and the screen rests again. One wait does both (later), on the standby's timer (screen_standby.h, POWER). Small on
// purpose: every byte counts on the 4 MB boards. Free of LVGL and ESPHome; core.yaml hands it the hooks at boot.
#include <cstdint>
// In the firmware: ESP-IDF's Wi-Fi (core.yaml keeps no #if of its own: a line starting with # is Jinja there).
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif
#if defined(USE_ESP32) && defined(USE_WIFI)
#include <esp_wifi.h>
#endif

namespace screen_power {

// Plain function pointers, not std::function: each std::function costs flash of its own.
inline void (*freeze)(bool) = nullptr;     // LVGL paused (true) or drawing (false)
inline void (*later)(uint32_t) = nullptr;  // due() after so many ms
inline bool (*dark)() = nullptr;           // the glass is dark
inline void (*wake)() = nullptr;           // wakes the screen

constexpr uint32_t REST_MS = 2000, SETTLE_MS = 100, TAP_MS = 30;

inline bool saving = false, touching = false, settling = false, was_tap = false;
inline uint32_t touch_start = 0;

// The radio dozes (modem sleep), or gets back the mode ESPHome gave it from the YAML. Also the minute's check of a
// dark screen: ESPHome puts its own mode back when it connects again.
inline void doze_wifi(bool doze) {
#if defined(USE_ESP32) && defined(USE_WIFI)
  static bool dozing = false;
  static wifi_ps_type_t own = WIFI_PS_NONE;
  wifi_ps_type_t now;
  if (esp_wifi_get_ps(&now) != ESP_OK) return;
  if (doze) {
    if (!dozing) own = now;
    dozing = true;
    if (now == WIFI_PS_NONE) esp_wifi_set_ps(WIFI_PS_MIN_MODEM);
  } else if (dozing) {
    dozing = false;
    if (now != own) esp_wifi_set_ps(own);
  }
#else
  (void) doze;
#endif
}

inline void enter() {
  if (saving) return;
  saving = true;
  doze_wifi(true);
  if (freeze) freeze(true);
}

inline void leave() {
  settling = false;
  if (!saving) return;
  saving = false;
  doze_wifi(false);
  if (freeze) freeze(false);
}

// The screen went dark: save in a moment. Not while a touch on the dark glass is being settled.
inline void rest() {
  if (!settling && later) later(REST_MS);
}

// A finger on the dark glass: drawing resumes before LVGL reads the touch again.
inline void touched(uint32_t now) {
  if (!saving) return;
  leave();
  touching = true;
  touch_start = now;
}

// The finger lifted: the wake overlay gets its click on LVGL's next round, and due() looks after the rest.
inline void released(uint32_t now) {
  if (!touching) return;
  touching = false;
  was_tap = now - touch_start >= TAP_MS;
  settling = true;
  if (later) later(SETTLE_MS);
}

inline void due() {
  const bool still_dark = dark && dark();
  if (settling) {
    settling = false;
    if (!still_dark) return;
    if (was_tap) {
      if (wake) wake();
    } else {
      rest();
    }
    return;
  }
  if (still_dark) enter();
}

}  // namespace screen_power
