#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include "screen_text.h"
#include "battery_status.h"
#include "wifi_status.h"

namespace header_bar {
// The top bar right of the screen name (firmware 0.2.32+). ESP Screen Manager decides what shows
// and writes an entity's text; the screen draws it, ticks its clocks and counts "5 min ago"
// itself. Everything here is free of LVGL, so tests/test_header_bar.cpp covers it on a PC.
// The items one page's bar holds (firmware 0.34.0+): six, or what a board with room for more states as the build flag
// SCREEN_MAX_BAR_ITEMS (packages/core.yaml, its board file). The glass's width still decides how many show (place()).
#ifndef SCREEN_MAX_BAR_ITEMS
#define SCREEN_MAX_BAR_ITEMS 6
#endif
constexpr size_t MAX_ITEMS = SCREEN_MAX_BAR_ITEMS;
static_assert(MAX_ITEMS >= 6 && MAX_ITEMS <= 16, "a page's bar holds 6 to 16 items");
// The items the app numbered a bar_value's targets by when it says nothing (page * 6 + index): every app before 0.4.57.
constexpr size_t WIRE_ITEMS = 6;
constexpr size_t TEXT_BYTES = 48;
// `wifi` and `link` (firmware 0.38.0) and `battery` (firmware 0.41.0) are the screen's own: it reads them itself, so they
// stay when Home Assistant goes.
enum class Kind : uint8_t { none, clock, analog, date, text, ago, wifi, link, battery };

inline Kind kind(const std::string &name) {
  if (name == "clock") return Kind::clock;
  if (name == "analog") return Kind::analog;
  if (name == "date") return Kind::date;
  if (name == "text") return Kind::text;
  if (name == "ago") return Kind::ago;
  if (name == "wifi") return Kind::wifi;
  if (name == "link") return Kind::link;
  if (name == "battery") return Kind::battery;
  return Kind::none;
}

struct Item {
  Kind kind = Kind::none;
  uint32_t icon = 0;   // Material Design Icons codepoint, 0 without an icon
  std::string text;    // Kind::text
  int64_t epoch = 0;   // Kind::ago: the moment, past or future
  uint32_t color = 0;  // accent of the icon while `has_color`
  bool has_color = false;
  // Shown only now and then (`a`): Kind::wifi while the signal is weak or gone, Kind::battery while it runs low.
  bool only_weak = false;
  bool operator==(const Item &o) const {
    return kind == o.kind && icon == o.icon && text == o.text && epoch == o.epoch && color == o.color && has_color == o.has_color &&
           only_weak == o.only_weak;
  }
};

struct Bar {
  std::array<Item, MAX_ITEMS> items{};
  size_t count = 0;
  bool received = false;  // false until the manager sent one: the clock of show_clock then
};

// "RRGGBB" as 0xRRGGBB; false for anything else.
inline bool color(const std::string &hex, uint32_t &out) {
  if (hex.size() != 6) return false;
  uint32_t value = 0;
  for (char c : hex) {
    int digit = c >= '0' && c <= '9' ? c - '0' : c >= 'A' && c <= 'F' ? c - 'A' + 10 : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
    if (digit < 0) return false;
    value = value << 4 | static_cast<uint32_t>(digit);
  }
  out = value;
  return true;
}

// Next codepoint of UTF-8 text at `i` (advanced past it); 0 at the end. Broken bytes count as one.
inline uint32_t next_codepoint(const std::string &s, size_t &i) {
  if (i >= s.size()) return 0;
  unsigned char c = static_cast<unsigned char>(s[i]);
  int extra = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
  uint32_t cp = extra == 3 ? c & 0x07 : extra == 2 ? c & 0x0F : extra == 1 ? c & 0x1F : c;
  ++i;
  for (int k = 0; k < extra && i < s.size() && (static_cast<unsigned char>(s[i]) & 0xC0) == 0x80; ++k, ++i)
    cp = cp << 6 | (static_cast<unsigned char>(s[i]) & 0x3F);
  return cp;
}

// Relative time in the editor's words (app.js agoText): "Just now", "5 min ago", "Yesterday",
// "In 2 hours", in the screen's language (screen.time, app 0.2.90). `now` 0 means the clock is not set yet.
inline std::string ago_text(int64_t then, int64_t now) {
  using namespace screen_text;
  if (now <= 0 || then <= 0) return "—";
  int64_t seconds = now - then, span = seconds < 0 ? -seconds : seconds;
  auto n = [&](int64_t unit) { return static_cast<int>(span / unit); };
  if (seconds < 0) {
    if (span < 3600) return fill(txt::time_in_minutes, "n", std::max(1, n(60)));
    if (span < 86400) return plural(txt::time_in_hours, n(3600));
    if (span < 172800) return tr(txt::time_tomorrow);
    return plural(txt::time_in_days, n(86400));
  }
  if (span < 60) return tr(txt::time_just_now);
  if (span < 3600) return fill(txt::time_minutes_ago, "n", n(60));
  if (span < 86400) return plural(txt::time_hours_ago, n(3600));
  if (span < 172800) return tr(txt::time_yesterday);
  if (span < 604800) return plural(txt::time_days_ago, n(86400));
  if (span < 2592000) return plural(txt::time_weeks_ago, n(604800));
  if (span < 31536000) return plural(txt::time_months_ago, n(2592000));
  return plural(txt::time_years_ago, n(31536000));
}

// "Mo 14 Sep" in English, "za 19 sep" in Dutch, "sam. 19 sept." in French (screen.date.top_bar, with the language's
// abbreviation as {weekday} or its two letters as {weekday_min}); day_of_week 1 is Sunday, as ESPHome counts.
inline std::string date_text(int day_of_week, int day_of_month, int month) {
  using namespace screen_text;
  if (day_of_week < 1 || day_of_week > 7 || month < 1 || month > 12) return "—";
  std::string text = fill(txt::date_top_bar, "weekday", tr(txt::date_weekdays_short + day_of_week - 1));
  text = fill(text, "weekday_min", tr(txt::date_weekdays_min + day_of_week - 1));
  text = fill(text, "day", std::to_string(day_of_month));
  return fill(text, "month", tr(txt::date_months_short + month - 1));
}

// The screen's own items (firmware 0.38.0). Wi-Fi draws the signal as a phone does, four bars down to one, and the bars
// struck through without a network; its text is "" (the icon alone), "%" or "dBm" as the app sends it. The link is a
// mark that appears only while Home Assistant or Tessera is away. The battery (firmware 0.41.0) draws Home Assistant's
// battery icon for its level and whether it charges, with "%" beside it when the app asks. All of them read the screen
// itself, so they also show, and matter most, while Home Assistant is gone and every other item has left the bar.
constexpr uint32_t WIFI_OFF_GLYPH = 0xF092E;  // wifi-strength-off-outline
constexpr uint32_t WIFI_GLYPHS[5] = {WIFI_OFF_GLYPH, 0xF091F, 0xF0922, 0xF0925, 0xF0928};  // wifi-strength-1 .. 4
constexpr uint32_t LINK_GLYPH = 0xF0319;  // lan-disconnect, one of the tile icons
struct Device {
  bool wifi = false;   // holds its network
  int rssi = 0;        // dBm
  bool linked = true;  // Home Assistant and Tessera both there
  battery_status::Reading battery{};
};
struct Shown {
  bool shown = false;
  uint32_t icon = 0;
  std::string text;
};
inline Shown device_item(const Item &item, const Device &device) {
  Shown s;
  if (item.kind == Kind::link) {
    s.shown = !device.linked;
    s.icon = LINK_GLYPH;
  } else if (item.kind == Kind::wifi) {
    const int strength = device.wifi ? wifi_status::bars(device.rssi) : 0;
    s.icon = WIFI_GLYPHS[strength];
    s.shown = !item.only_weak || !strength || wifi_status::weak(device.rssi);
    if (strength && item.text == "%") s.text = screen_text::percent(wifi_status::percent(device.rssi));
    else if (strength && item.text == "dBm") s.text = std::to_string(device.rssi) + " dBm";
  } else if (item.kind == Kind::battery) {
    const auto &b = device.battery;
    s.shown = b.present && (!item.only_weak || battery_status::low(b));
    s.icon = battery_status::icon(b.level, b.charging == 1);
    if (item.text == "%" && std::isfinite(b.level)) s.text = screen_text::percent(static_cast<int>(std::lround(b.level)));
  }
  return s;
}

// What you see between icon and value, between two items and after the name, from the height of
// the digits; the editor's barGaps() uses the same factors.
struct Gaps { int icon, item, name; };
inline int scaled(int cap, int tenths) { return (cap * tenths + 5) / 10; }
inline Gaps gaps(int cap) {
  return {std::max(2, scaled(cap, 4)), std::max(6, (cap * 125 + 50) / 100), std::max(8, scaled(cap, 16))};
}

// Right-aligned placement of item widths (ink, gaps included) in `width` pixels beside a name of
// `name_natural` pixels. The name keeps at least min(natural, 35% of the width); items leave from
// the front until the rest fits. `x` is each item's left ink edge; `name_room` what the name may use.
struct Placement {
  size_t first = 0;
  std::array<int, MAX_ITEMS> x{};
  int name_room = 0;
};
// The width of items `from` up to `to`, with the gaps between them.
inline int span(const int *widths, size_t from, size_t to, const Gaps &g) {
  int sum = 0;
  for (size_t i = from; i < to; ++i) sum += widths[i] + (i > from ? g.item : 0);
  return sum;
}
inline Placement place(const int *widths, size_t count, const Gaps &g, int width, int name_natural) {
  Placement p;
  count = std::min(count, MAX_ITEMS);
  int min_name = std::min(name_natural, width * 35 / 100);
  while (p.first < count && span(widths, p.first, count, g) + g.name + min_name > width) ++p.first;
  int x = width - span(widths, p.first, count, g);
  for (size_t i = p.first; i < count; ++i) { p.x[i] = x; x += widths[i] + g.item; }
  p.name_room = p.first < count ? p.x[p.first] - g.name : width;
  return p;
}
// A row of the same items without a name, centred in `width` (the screensaver clock's, firmware 0.50.0+). Items leave
// from the end until the rest fits, so the first stays; `count` is how many show.
struct Centred {
  size_t count = 0;
  std::array<int, MAX_ITEMS> x{};
};
inline Centred centre(const int *widths, size_t count, const Gaps &g, int width) {
  Centred c;
  c.count = std::min(count, MAX_ITEMS);
  while (c.count && span(widths, 0, c.count, g) > width) --c.count;
  int x = (width - span(widths, 0, c.count, g)) / 2;
  for (size_t i = 0; i < c.count; ++i) { c.x[i] = x; x += widths[i] + g.item; }
  return c;
}
}  // namespace header_bar
