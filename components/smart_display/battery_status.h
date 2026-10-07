#pragma once
// A battery as the glass tells it (firmware 0.41.0, docs/BATTERY.md). A screen has one when it has a sensor in Home
// Assistant's `battery` device class, in percent: a fuel gauge or power chip that knows the percentage, a voltage turned
// into one by a formula (packages/features/battery-voltage.yaml, with battery-adc.yaml for a pin), the Tab5's curve, or a
// sensor in a screen's own Override YAML. A binary sensor in the `battery_charging` class says whether it charges.
// runtime_tiles::find_battery() hands both to `level` and `charging` at boot; the screen then reads them itself, so the
// top bar's battery item stays right while Home Assistant is away, and its hello says `battery`, so ESP Screens offers
// the item only on a screen that has one. Everything here is free of LVGL and ESPHome, so tests/test_header_bar.cpp
// covers it on a PC.
#include <cmath>
#include <cstdint>
#include <functional>

namespace battery_status {

// What find_battery() sets at boot: the percentage, NAN while it has no reading yet; and whether it charges, -1 while
// that is not known (no charging sensor, or no reading yet), else 0 or 1.
inline std::function<float()> level;
inline std::function<int()> charging;

struct Reading {
  bool present = false;  // the board has a battery
  float level = NAN;     // percent, NAN while unknown
  int charging = -1;     // -1 unknown, 0 or 1
};

#if defined(USE_HOST) || defined(ESP_SCREEN_HOST)
// The preview and the host renders draw a battery at three quarters that is not charging, as the Wi-Fi item draws a
// good signal there (wifi_status::host_link); the editor only offers the item for a screen that has a battery.
inline Reading host_reading = [] { Reading r; r.present = true; r.level = 76; r.charging = 0; return r; }();
inline Reading read() { return host_reading; }
#else
inline Reading read() {
  Reading r;
  if (!level) return r;
  r.present = true;
  const float value = level();
  r.level = std::isfinite(value) ? std::fmin(100.0f, std::fmax(0.0f, value)) : NAN;
  if (charging) r.charging = charging();
  return r;
}
#endif

// Shown by an item that only appears while the battery runs low: at or under this percentage, while it does not charge.
constexpr float LOW = 20;

// The icon Home Assistant draws for a battery level (frontend src/common/entity/battery_icon.ts, batteryLevelIcon):
// the level rounded to tens, the charging set from 10 % up and its outline below, the alert outline at 5 % or less,
// and battery-unknown without a number. The level icons, battery-unknown and the full charging one are tile icons; the
// other charging ones and the alert outline are in the top bar's status font (packages/core.yaml).
constexpr uint32_t UNKNOWN_GLYPH = 0xF0091;           // battery-unknown
constexpr uint32_t ALERT_GLYPH = 0xF10CD;             // battery-alert-variant-outline
constexpr uint32_t CHARGING_OUTLINE_GLYPH = 0xF089F;  // battery-charging-outline
// battery-10 .. battery-90, battery (index 1 to 10: tens)
constexpr uint32_t LEVEL_GLYPHS[11] = {0, 0xF007A, 0xF007B, 0xF007C, 0xF007D, 0xF007E,
                                       0xF007F, 0xF0080, 0xF0081, 0xF0082, 0xF0079};
// battery-charging-10 .. battery-charging-90, battery-charging
constexpr uint32_t CHARGING_GLYPHS[11] = {0, 0xF089C, 0xF0086, 0xF0087, 0xF0088, 0xF089D,
                                          0xF0089, 0xF089E, 0xF008A, 0xF008B, 0xF0084};

// JavaScript's Math.round(level / 10): halves round up.
inline int tens(float level) { return static_cast<int>(std::floor(level / 10.0f + 0.5f)); }

inline uint32_t icon(float level, bool charging) {
  if (!std::isfinite(level)) return UNKNOWN_GLYPH;
  const int round = tens(level);
  if (charging && level >= 10) return CHARGING_GLYPHS[round < 1 ? 1 : round > 10 ? 10 : round];
  if (charging) return CHARGING_OUTLINE_GLYPH;
  if (level <= 5) return ALERT_GLYPH;
  return LEVEL_GLYPHS[round < 1 ? 1 : round > 10 ? 10 : round];
}

// Whether an item that shows only while the battery runs low shows now: a reading at or under LOW, charging or not
// (the icon then says it charges). Without a reading there is nothing to warn about yet.
inline bool low(const Reading &r) { return std::isfinite(r.level) && r.level <= LOW; }

}  // namespace battery_status
