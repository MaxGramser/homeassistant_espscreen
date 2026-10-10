#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <iterator>
#include <cstdio>
#include <string>
#include <vector>
#include "battery_status.h"
#include "screen_hooks.h"
#include "screen_settings.h"
#include "screen_text.h"
#include "ui_scale.h"

// The settings page on the screen itself (firmware 0.2.44+). It changes the same values ESP Screen
// Manager writes, for the moments you stand in front of the panel instead of behind a browser.
//
// Everything the page shows is one table: `pages[]` of `Row`s. A row knows how to read and write its
// value and what kind of control it needs, so a new setting is one line in that table -- no drawing
// code, no layout. docs/SETTINGS.md walks through adding one end to end.
//
// The model (rows, stepping, the texts) is free of LVGL so tests/test_settings_screen.cpp covers it
// on a PC; the drawing below it is behind SETTINGS_SCREEN_TEST.
namespace settings_screen {

// Values that are not part of the persisted `screen_settings::Settings` block, because that format is
// frozen at version 1: each of these keeps its own preference, so a new option never rewrites the
// old ones. The manager sends the older ones as their own keys in the layout message; dark_mode (firmware
// 0.2.54+) only exists as the screen's own setting and entity, like page_buttons (firmware 0.2.69+): off, the
// Previous and Next bar under the tiles goes and the tiles take its room.
inline int32_t swipe_pages = 0, rotation = 0, auto_home = 1, auto_home_seconds = 120, dark_mode = 0, page_buttons = 1;
// The house at the far left of the top bar (firmware 0.2.100+): one tap and the screen is back on page 1, from
// wherever it stands. On page 1 there is nowhere to go, so it is not drawn there and the page title starts at the
// margin as it always did. Off, the bar is exactly what it was.
inline int32_t home_button = 1;
// Whether this board's backlight takes levels (firmware 0.2.90+). The Waveshare's is one line on an I2C expander:
// the panel is lit or it is not, and anything above a hair of a level lights it. A percentage there is a number
// that lies, so the board's own file says so (BACKLIGHT_DIMMABLE) and the rows below follow: the normal brightness
// goes, and standby and night become the switch they really are. ESP Screens reads the same fact from boards.json.
inline bool dimmable = true;
// Whether this board's screen can go dark at all (firmware 0.2.91+). The Waveshare's backlight line also enables
// the boost converter behind its LEDs, and switching that on from a dark screen pulls the 3.3 V rail under the
// brownout level: measured on 2026-09-21, every wake from a dark standby ended in a reset or a dead I2C bus. A
// board that says CAN_STANDBY false never dims, so it has no standby and no night (night is standby with a clock):
// these rows, the entities behind them and the add-on's Settings leave them out, and dim_display in
// packages/core.yaml does nothing there.
inline bool can_standby = true;
// What this screen is able to do, in the words ESP Screens reads from its "Screen features" sensor (firmware
// 0.2.99+): one word per ability, space separated, and "none" for a screen that can do none of them. The add-on
// used to read these facts from a table it keeps per board, which is right until a board is changed: a Waveshare
// whose backlight was rewired to a PWM pin (docs/WAVESHARE7.md) really does dim, and the table would keep saying it
// cannot. The screen is the one that knows. One line per ability below, and the add-on skips a word it does not
// know (FEATURES in screen_manager/app/core.py), so this list may grow without an older app minding.
inline std::string features() {
  const struct { bool able; const char *word; } list[] = {
    {dimmable, "dimmable"},     // the backlight takes levels, not only lit or dark
    {can_standby, "standby"},   // the screen can go dark and come back
    // it has a battery the top bar can show (firmware 0.41.0, runtime_tiles::find_battery, docs/BATTERY.md)
    {static_cast<bool>(battery_status::level), "battery"},
  };
  std::string words;
  for (const auto &item : list) {
    if (!item.able) continue;
    if (!words.empty()) words += ' ';
    words += item.word;
  }
  return words.empty() ? "none" : words;
}
// Turning: a half turn keeps the canvas, the grid and the whole size table, so every screen offers it (firmware
// 0.2.80+); a quarter turn only a square screen, whose canvas is the same either way. packages/core.yaml sets this
// from DISPLAY_W == DISPLAY_H at boot.
inline bool quarter_turns = false;

// ------------------------------------------------------------------ the table
enum class Kind : uint8_t { page, toggle, number, duration, moment, choice, info, action };
using Read = int32_t (*)();
using Write = void (*)(int32_t);
using Text = std::string (*)();
using Shown = bool (*)();
using Run = void (*)();

// The page's words are keys into the screen's language (screen.settings in screen_manager/translations, app 0.2.90):
// the table stays constexpr, the text is looked up when a row is drawn.
constexpr uint16_t NO_TEXT = 0xFFFF;
// A row of a plugin (docs/PLUGINS.md, plugin_host.cpp): its own words instead of a key, and its own reader, writer,
// action and text with a context, since a plugin's row reads an entity of its own. Apart from Row, so Tessera's own
// rows, which are constant tables in flash, grow by one pointer and not by seven.
struct Own {
  const char *words = nullptr, *confirm = nullptr;
  void *ctx = nullptr;
  int32_t (*read)(void *) = nullptr;
  void (*write)(void *, int32_t) = nullptr;
  void (*run)(void *) = nullptr;
  std::string (*text)(void *) = nullptr;
  bool (*active)(void *) = nullptr;   // an action that runs now (a test): its row is lit until it stops
};
struct Row {
  Kind kind = Kind::info;
  uint16_t label = NO_TEXT;
  const char *icon = "";              // page rows and actions; a Material Design Icons glyph
  Read read = nullptr;                // toggle, number, duration, moment, choice
  Write write = nullptr;
  int32_t low = 0, high = 0, step = 0;  // number: fixed step; duration: seconds, step from the ladder
  const char *unit = "";              // straight after a number ("%")
  const char *const *options = nullptr;  // choice with the same words in every language ("90°")
  uint16_t option_keys = NO_TEXT;     // choice in words: the key of its first option, the others follow it
  uint8_t option_count = 0;
  Text text = nullptr;                // info
  Run run = nullptr;                  // action
  uint16_t confirm = NO_TEXT;         // action: what the row asks before it does it
  Shown shown = nullptr;              // absent rows: the quarter turns on glass that is not square
  Shown enabled = nullptr;            // greyed out while the switch it depends on is off
  uint8_t opens = 0;                  // page rows: the page they open
  const Own *own = nullptr;          // a plugin's row: its own words and functions
};
// Every reader of a row asks through these, so Tessera's rows and a plugin's are drawn and tapped the same way.
inline bool readable(const Row &row) { return row.read || (row.own && row.own->read); }
inline bool writable(const Row &row) { return row.write || (row.own && row.own->write); }
inline int32_t get(const Row &row) {
  return row.read ? row.read() : row.own && row.own->read ? row.own->read(row.own->ctx) : 0;
}
inline void put(const Row &row, int32_t value) {
  if (row.write) row.write(value);
  else if (row.own && row.own->write) row.own->write(row.own->ctx, value);
}
inline void act(const Row &row) {
  if (row.run) row.run();
  else if (row.own && row.own->run) row.own->run(row.own->ctx);
}

constexpr Row page_row(uint16_t label, const char *icon, uint8_t opens, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::page; r.label = label; r.icon = icon; r.opens = opens; r.shown = shown; return r;
}
constexpr Row toggle(uint16_t label, Read read, Write write, Shown shown = nullptr, Shown enabled = nullptr) {
  Row r{}; r.kind = Kind::toggle; r.label = label; r.read = read; r.write = write; r.shown = shown; r.enabled = enabled; return r;
}
constexpr Row number(uint16_t label, Read read, Write write, int32_t low, int32_t high, int32_t step,
                     const char *unit = "", Shown enabled = nullptr, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::number; r.label = label; r.read = read; r.write = write;
  r.low = low; r.high = high; r.step = step; r.unit = unit; r.enabled = enabled; r.shown = shown; return r;
}
constexpr Row duration(uint16_t label, Read read, Write write, int32_t low, int32_t high,
                       Shown enabled = nullptr, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::duration; r.label = label; r.read = read; r.write = write;
  r.low = low; r.high = high; r.enabled = enabled; r.shown = shown; return r;
}
constexpr Row moment(uint16_t label, Read read, Write write, Shown enabled = nullptr, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::moment; r.label = label; r.read = read; r.write = write;
  r.low = 0; r.high = 1439; r.step = 15; r.enabled = enabled; r.shown = shown; return r;
}
constexpr Row choice(uint16_t label, Read read, Write write, const char *const *options, uint8_t count,
                     Shown shown = nullptr) {
  Row r{}; r.kind = Kind::choice; r.label = label; r.read = read; r.write = write;
  r.options = options; r.option_count = count; r.shown = shown; return r;
}
constexpr Row choice(uint16_t label, Read read, Write write, uint16_t option_keys, uint8_t count, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::choice; r.label = label; r.read = read; r.write = write;
  r.option_keys = option_keys; r.option_count = count; r.shown = shown; return r;
}
inline const char *label_text(const Row &row) { return row.own && row.own->words ? row.own->words : screen_text::tr(row.label); }
inline const char *confirm_text(const Row &row) {
  return row.own && row.own->confirm ? row.own->confirm : screen_text::tr(row.confirm);
}
constexpr Row info(uint16_t label, Text text) {
  Row r{}; r.kind = Kind::info; r.label = label; r.text = text; return r;
}
constexpr Row action(uint16_t label, const char *icon, Run run, uint16_t confirm, Shown shown = nullptr) {
  Row r{}; r.kind = Kind::action; r.label = label; r.icon = icon; r.run = run; r.confirm = confirm; r.shown = shown; return r;
}

// ------------------------------------------------------------------ values
// One place where a change is kept, put into effect and sent to the manager, so the add-on's page
// shows what the screen shows. The same path the Home Assistant number entities already take.
inline void (*store)() = nullptr;                          // save the preferences
inline void (*apply)() = nullptr;                          // backlight, rotation, night
inline void (*report)(const char *, int32_t) = nullptr;    // esphome.screen_setting event
inline void changed(const char *key, int32_t value) {
  if (store) store();
  if (apply) apply();
  if (report) report(key, value);
}

// The one way a setting changes, for every writer: the rows below, and the Home Assistant entities of the
// board profile (firmware 0.2.49+). The value is clamped the way the page steps it, a lower brightness pulls
// the two dim levels down with it, and a value the screen already has is not saved, applied or reported
// again: an automation may set it on every light change.
enum class SetResult : uint8_t { unknown, same, changed };
inline SetResult set(const std::string &key, int32_t value) {
  auto &s = screen_settings::current;
  const auto before = s;
  const int32_t before_swipe = swipe_pages, before_rotation = rotation, before_home = auto_home,
                before_home_seconds = auto_home_seconds, before_dark = dark_mode, before_buttons = page_buttons,
                before_home_button = home_button;
  int32_t reported = 0;
  auto flag = [](int32_t v) -> int32_t { return v ? 1 : 0; };
  if (key == "standby_enabled") reported = s.standby_enabled = flag(value);
  else if (key == "standby_seconds") reported = s.standby_seconds = std::clamp<int32_t>(value, 60, 86400);
  else if (key == "brightness") {
    reported = s.brightness = std::clamp<int32_t>(value, 5, 100);
    s.standby_brightness = std::min(s.standby_brightness, s.brightness);
    s.night_brightness = std::min(s.night_brightness, s.brightness);
  } else if (key == "standby_brightness") reported = s.standby_brightness = std::clamp<int32_t>(value, 0, s.brightness);
  else if (key == "night_enabled") reported = s.night_enabled = flag(value);
  else if (key == "night_start") reported = s.night_start = std::clamp<int32_t>(value, 0, 1439);
  else if (key == "night_end") reported = s.night_end = std::clamp<int32_t>(value, 0, 1439);
  else if (key == "night_brightness") reported = s.night_brightness = std::clamp<int32_t>(value, 0, s.brightness);
  else if (key == "clock_24h") reported = s.clock_24h = flag(value);
  else if (key == "home_on_standby") reported = s.home_on_standby = flag(value);
  else if (key == "swipe_pages") reported = swipe_pages = flag(value);
  else if (key == "rotation") {
    const int32_t turn = std::clamp<int32_t>(value, 0, 270) / 90 * 90;
    if (turn % 180 && !quarter_turns) return SetResult::unknown;  // a quarter turn only on a square screen
    reported = rotation = turn;
  }
  else if (key == "auto_home") reported = auto_home = flag(value);
  else if (key == "auto_home_seconds") reported = auto_home_seconds = std::clamp<int32_t>(value, 30, 3600);
  else if (key == "dark_mode") reported = dark_mode = flag(value);
  else if (key == "page_buttons") reported = page_buttons = flag(value);
  else if (key == "home_button") reported = home_button = flag(value);
  else return SetResult::unknown;
  if (s == before && swipe_pages == before_swipe && rotation == before_rotation && auto_home == before_home &&
      auto_home_seconds == before_home_seconds && dark_mode == before_dark && page_buttons == before_buttons &&
      home_button == before_home_button)
    return SetResult::same;
  changed(key.c_str(), reported);
  return SetResult::changed;
}

// How coarse a duration steps: seconds near the bottom, quarters of an hour at the top. Stepping down
// reads the ladder one second lower, so up and down always land on the same values again.
inline int32_t ladder_step(int32_t seconds) {
  if (seconds < 300) return 30;
  if (seconds < 900) return 60;
  if (seconds < 3600) return 300;
  if (seconds < 7200) return 900;
  return 1800;
}
// The value one press of - or + gives. Moments wrap around midnight; everything else stops at its end.
// `held` is a finger that has been on the key for a while: a time then walks whole hours instead of
// quarters, so setting night from 22:00 to 07:00 is one hold and not thirty-six taps.
inline int32_t stepped(const Row &row, int32_t value, int direction, bool held = false) {
  if (row.kind == Kind::moment) {
    int32_t step = held ? 60 : row.step;
    // From a hold, land on the whole hour first; after that every step is an hour.
    int32_t next = held && value % 60 ? (value / 60) * 60 + (direction > 0 ? 60 : 0) : value + direction * step;
    int32_t span = row.high + 1;
    next %= span;
    return next < 0 ? next + span : next;
  }
  int32_t step = row.kind == Kind::duration ? ladder_step(direction < 0 ? value - 1 : value) : row.step;
  return std::clamp<int32_t>(value + direction * step, row.low, row.high);
}
inline bool at_end(const Row &row, int32_t value, int direction) {
  if (row.kind == Kind::moment) return false;
  return stepped(row, value, direction) == value;
}
// Where the knob of a w by h switch sits: at the left when off, at the right when on, inset all round.
inline int knob_x(int w, int h, bool on) {
  int inset = std::max(2, h / 10), size = h - 2 * inset;
  return on ? w - inset - size : inset;
}

inline std::string duration_text(int32_t seconds) {
  using namespace screen_text;
  if (seconds < 60) return fill(txt::settings_seconds, "n", (int) seconds);
  if (seconds < 3600) return fill(txt::settings_minutes, "n", (int) (seconds / 60));
  int hours = seconds / 3600, minutes = (seconds % 3600) / 60;
  if (!minutes) return fill(txt::settings_hours, "n", hours);
  char two[4];
  snprintf(two, sizeof(two), "%02d", minutes);
  return fill(fill(txt::settings_hours_minutes, "h", hours), "m", two);
}
// Minutes since midnight as the clock on this screen shows them.
inline std::string moment_text(int32_t minutes, bool clock_24h) {
  char buffer[8];
  snprintf(buffer, sizeof(buffer), "%02d:%02d", (int) (minutes / 60 % 24), (int) (minutes % 60));
  return screen_text::clock_text(buffer, clock_24h);
}
// What the right-hand side of a row says. A toggle draws a switch instead, its text is for the tests.
inline std::string value_text(const Row &row) {
  switch (row.kind) {
    case Kind::toggle: return screen_text::tr(get(row) ? screen_text::txt::ha_on : screen_text::txt::ha_off);
    case Kind::number: {
      int value = (int) get(row);
      return strcmp(row.unit, "%") == 0 ? screen_text::percent(value) : std::to_string(value) + row.unit;
    }
    case Kind::duration: return duration_text(get(row));
    case Kind::moment: return moment_text(get(row), screen_settings::current.clock_24h != 0);
    case Kind::choice: {
      int32_t index = get(row);
      if (index < 0 || index >= row.option_count) return "";
      return row.option_keys != NO_TEXT ? screen_text::tr(row.option_keys + index) : row.options[index];
    }
    case Kind::info: return row.text ? row.text() : row.own && row.own->text ? row.own->text(row.own->ctx) : "";
    case Kind::action: return row.own && row.own->text ? row.own->text(row.own->ctx) : "";
    default: return "";
  }
}
inline bool visible_row(const Row &row) { return !row.shown || row.shown(); }
// A plugin's action that is running (plugin API 0.3): lit in the accent, as a row that asks is, until it stops.
inline bool busy_row(const Row &row) {
  return row.kind == Kind::action && row.own && row.own->active && row.own->active(row.own->ctx);
}
inline bool live_row(const Row &row) { return !row.enabled || row.enabled(); }

struct Page {
  uint16_t title;
  const Row *rows;
  uint8_t count;
  uint8_t parent = 0;              // where Back goes: the menu, or for a plugin's page the list of plugins
  const char *words = nullptr;     // a plugin's page: its title in its own words
};

// How many rows fit, and whether the page therefore needs its pager. Reserving the pager only when it
// is really needed keeps a group that just fits on one page.
inline uint8_t fitting_rows(int span, int row_height, int gap, int pager, uint8_t count, bool &paged) {
  int loose = std::max(1, (span + gap) / (row_height + gap));
  paged = count > loose;
  if (!paged) return count;
  return (uint8_t) std::max(1, (span - pager + gap) / (row_height + gap));
}

// ------------------------------------------------------------------ the pages
inline constexpr const char *rotation_options[] = {"0°", "90°", "180°", "270°"};
inline constexpr const char *half_turn_options[] = {"0°", "180°"};

// Brightness, the dark look for a screen beside a bed, and when the screen dims by itself.
// Every reader says `-> int32_t` out loud: on the ESP32 that is `long`, and a lambda that returns a
// plain `int` (a ternary, say) then does not convert to Read at all. The Mac's host build accepts it,
// the board does not.
inline constexpr Row light_rows[] = {
  number(screen_text::txt::settings_brightness, []() -> int32_t { return screen_settings::current.brightness; },
         [](int32_t value) { set("brightness", value); }, 5, 100, 5, "%", nullptr,
         [] { return dimmable; }),
  toggle(screen_text::txt::settings_dark_mode, []() -> int32_t { return dark_mode; },
         [](int32_t value) { set("dark_mode", value); }),
  // Standby and everything under it only on a board whose screen can go dark (can_standby).
  toggle(screen_text::txt::settings_auto_standby, []() -> int32_t { return screen_settings::current.standby_enabled; },
         [](int32_t value) { set("standby_enabled", value); },
         [] { return can_standby; }),
  duration(screen_text::txt::settings_standby_after, []() -> int32_t { return screen_settings::current.standby_seconds; },
           [](int32_t value) { set("standby_seconds", value); }, 60, 86400,
           [] { return screen_settings::current.standby_enabled != 0; },
           [] { return can_standby; }),
  number(screen_text::txt::settings_standby_brightness, []() -> int32_t { return screen_settings::current.standby_brightness; },
         [](int32_t value) { set("standby_brightness", value); }, 0, 100, 5, "%",
         [] { return screen_settings::current.standby_enabled != 0; },
         [] { return dimmable && can_standby; }),
  // The same setting on a backlight without levels: lit or dark. It writes the same key, so Home Assistant, the
  // app and the screen keep one number between them and a board that can dim shows it as the percentage it is.
  toggle(screen_text::txt::settings_standby_lit, []() -> int32_t { return screen_settings::current.standby_brightness > 0; },
         [](int32_t value) { set("standby_brightness", value ? 100 : 0); },
         [] { return !dimmable && can_standby; },
         [] { return screen_settings::current.standby_enabled != 0; }),
};

// Darker between two times, so a panel in a hallway does not light up the bedroom.
inline constexpr Row night_rows[] = {
  // Night is standby with a clock: a board that cannot go dark has none of it (can_standby).
  toggle(screen_text::txt::settings_night_mode, []() -> int32_t { return screen_settings::current.night_enabled; },
         [](int32_t value) { set("night_enabled", value); },
         [] { return can_standby; }),
  moment(screen_text::txt::settings_starts, []() -> int32_t { return screen_settings::current.night_start; },
         [](int32_t value) { set("night_start", value); },
         [] { return screen_settings::current.night_enabled != 0; },
         [] { return can_standby; }),
  moment(screen_text::txt::settings_ends, []() -> int32_t { return screen_settings::current.night_end; },
         [](int32_t value) { set("night_end", value); },
         [] { return screen_settings::current.night_enabled != 0; },
         [] { return can_standby; }),
  number(screen_text::txt::settings_night_brightness, []() -> int32_t { return screen_settings::current.night_brightness; },
         [](int32_t value) { set("night_brightness", value); }, 0, 100, 5, "%",
         [] { return screen_settings::current.night_enabled != 0; },
         [] { return dimmable && can_standby; }),
  toggle(screen_text::txt::settings_night_lit, []() -> int32_t { return screen_settings::current.night_brightness > 0; },
         [](int32_t value) { set("night_brightness", value ? 100 : 0); },
         [] { return !dimmable && can_standby; },
         [] { return screen_settings::current.night_enabled != 0; }),
};

// How the screen behaves under your finger: going back to the first page, swiping, the page buttons, turning. The
// clock's 12 or 24 hours is no longer a setting of each screen (app 0.2.90): ESP Screens sends it with the number
// format, from Settings -> Language & region, the one place for every screen.
inline constexpr Row screen_rows[] = {
  toggle(screen_text::txt::settings_back_to_page_1, []() -> int32_t { return auto_home; },
         [](int32_t value) { set("auto_home", value); }),
  duration(screen_text::txt::settings_after, []() -> int32_t { return auto_home_seconds; },
           [](int32_t value) { set("auto_home_seconds", value); }, 30, 3600,
           [] { return auto_home != 0; }),
  toggle(screen_text::txt::settings_also_on_standby, []() -> int32_t { return screen_settings::current.home_on_standby; },
         [](int32_t value) { set("home_on_standby", value); },
         [] { return can_standby; }),
  toggle(screen_text::txt::settings_swipe_between_pages, []() -> int32_t { return swipe_pages; },
         [](int32_t value) { set("swipe_pages", value); }),
  toggle(screen_text::txt::settings_page_buttons, []() -> int32_t { return page_buttons; },
         [](int32_t value) { set("page_buttons", value); }),
  toggle(screen_text::txt::settings_home_button, []() -> int32_t { return home_button; },
         [](int32_t value) { set("home_button", value); }),
  // Turning the screen: every board the half turn, a square one the quarter turns as well; one of the two rows shows.
  choice(screen_text::txt::settings_rotation, []() -> int32_t { return rotation >= 180 ? 1 : 0; },
         [](int32_t value) { set("rotation", value ? 180 : 0); },
         half_turn_options, 2, [] { return !quarter_turns; }),
  choice(screen_text::txt::settings_rotation, []() -> int32_t { return rotation / 90; },
         [](int32_t value) { set("rotation", std::clamp<int32_t>(value, 0, 3) * 90); },
         rotation_options, 4, [] { return quarter_turns; }),
};

// Read-only facts plus the actions: what you want when something is stuck. Both of them take the glass away for a
// while, so both ask once, in place, before they run.
inline std::string (*name_text)() = nullptr;
inline std::string (*address_text)() = nullptr;
inline std::string (*firmware_text)() = nullptr;
inline std::string (*link_text)() = nullptr;
// The network it holds with its signal, and whether Tessera is there (firmware 0.38.0, GitHub #130): what to look at
// when a screen in a far room keeps waiting. The page tells them again every two seconds while it is open.
inline std::string (*wifi_text)() = nullptr;
inline std::string (*tessera_text)() = nullptr;
inline void (*restart_device)() = nullptr;
// Start the calibration wizard again (firmware 0.2.96+). A resistive panel reads a voltage off the film and has to
// be told what that voltage means in pixels, so it has a wizard; a capacitive one reports the point it was touched
// on and has nothing to fit. ESPHome names no such difference, and this page needs no name for it: the board that
// builds a wizard binds this, every other board leaves it null, and the row shows exactly where there is something
// to run. It closes this page first: the wizard loads a screen of its own and leaves the home page behind it.
inline void (*calibrate_touch)() = nullptr;
inline constexpr Row about_rows[] = {
  info(screen_text::txt::settings_screen, [] { return name_text ? name_text() : std::string(); }),
  info(screen_text::txt::settings_address, [] { return address_text ? address_text() : std::string(); }),
  info(screen_text::txt::settings_wifi, [] { return wifi_text ? wifi_text() : std::string(); }),
  info(screen_text::txt::settings_firmware, [] { return firmware_text ? firmware_text() : std::string(); }),
  info(screen_text::txt::settings_home_assistant, [] { return link_text ? link_text() : std::string(); }),
  info(screen_text::txt::settings_tessera, [] { return tessera_text ? tessera_text() : std::string(); }),
  action(screen_text::txt::settings_calibrate_touch, "\U000F01A3", [] { if (calibrate_touch) calibrate_touch(); },
         screen_text::txt::settings_tap_again_to_calibrate, [] { return calibrate_touch != nullptr; }),
  action(screen_text::txt::settings_restart, "\U000F0709", [] { if (restart_device) restart_device(); },
         screen_text::txt::settings_tap_again_to_restart),
};

// The plugins' pages (docs/PLUGINS.md): built once at the start from what each plugin adds (plugin_host.cpp), after the
// table's own pages. The first is the list of plugins, each opening its own page.
inline std::vector<Page> plugin_pages;
inline bool has_plugin_pages() { return !plugin_pages.empty(); }
constexpr uint8_t PLUGINS_PAGE = 5;  // the first page after the table's own (PAGE_COUNT, checked below)

// A board's extras (docs/SETTINGS.md, "A board's own settings"): rows a feature or a board file adds at boot through its
// hook (BOOT_AUDIO_SETTINGS, BOOT_BOARD_SETTINGS in packages/core.yaml), each bound to an ESPHome entity of the screen
// so Home Assistant and the app show and change the same value. The page and its row in the menu are there only when a
// board has some: a screen without stays as it was.
inline std::vector<Row> board_rows;
inline bool has_board_rows() { return !board_rows.empty(); }
constexpr uint8_t BOARD_PAGE = 250;  // beside the numbered pages: the plugins' pages count up from PLUGINS_PAGE

inline constexpr Row menu_rows[] = {
  page_row(screen_text::txt::settings_brightness, "\U000F0599", 1),
  page_row(screen_text::txt::settings_night, "\U000F0594", 2, [] { return can_standby; }),
  page_row(screen_text::txt::settings_screen, "\U000F0379", 3),
  page_row(screen_text::txt::settings_this_screen, "\U000F02FD", 4),
  page_row(screen_text::txt::settings_extras, "\U000F0493", BOARD_PAGE, has_board_rows),
  page_row(screen_text::txt::settings_plugins, "\U000F0A66", PLUGINS_PAGE, has_plugin_pages),
};

inline constexpr Page pages[] = {
  {screen_text::txt::settings_title, menu_rows, (uint8_t) std::size(menu_rows)},
  {screen_text::txt::settings_brightness, light_rows, (uint8_t) std::size(light_rows)},
  {screen_text::txt::settings_night, night_rows, (uint8_t) std::size(night_rows)},
  {screen_text::txt::settings_screen, screen_rows, (uint8_t) std::size(screen_rows)},
  {screen_text::txt::settings_this_screen, about_rows, (uint8_t) std::size(about_rows)},
};
constexpr uint8_t PAGE_COUNT = (uint8_t) std::size(pages);
static_assert(PLUGINS_PAGE == PAGE_COUNT, "the plugins' pages follow the table's own");
inline uint8_t page_total() { return (uint8_t) (PAGE_COUNT + plugin_pages.size()); }
inline const Page &page_at(uint8_t index) {
  if (index == BOARD_PAGE) {
    static Page board{screen_text::txt::settings_extras, nullptr, 0};
    board.rows = board_rows.data();
    board.count = (uint8_t) std::min<size_t>(board_rows.size(), 12);   // what one page draws (draw)
    return board;
  }
  return index < PAGE_COUNT || index - PAGE_COUNT >= plugin_pages.size() ? pages[index < PAGE_COUNT ? index : 0]
                                                                        : plugin_pages[index - PAGE_COUNT];
}
inline const char *page_title(const Page &page) { return page.words ? page.words : screen_text::tr(page.title); }

}  // namespace settings_screen

#ifndef SETTINGS_SCREEN_TEST
#include "lvgl.h"
#include "detail_bar.h"
#include "page_bar.h"
#include "theme.h"
#include <functional>

namespace settings_screen {

// Bound by the board profile on boot: the fonts of the board and what the page may do to it.
inline const lv_font_t *title_font = nullptr, *row_font = nullptr, *icon_font = nullptr;
inline std::function<bool()> may_open;   // awake, no calibration, runtime tiles alive
inline std::function<int()> drift;       // how far the finger travelled during this touch
inline std::function<void()> before_open;  // close whatever card is open first
// Holding the top bar opens the page; a finger that travels further than this is swiping, not holding.
inline uint32_t hold_ms = 1500;
inline int hold_limit = 20;
// How far a tap on a row may drift, the same figure the board's own touch guard uses for tiles
// (a centimetre on the resistive CYD, no limit on the capacitive Guition). 0 is no limit.
inline int tap_limit = 0;

// The page while it is on screen; nothing of it exists when it is closed, which is how a 320x240
// board with 60 KB of free heap can afford a settings page at all.
inline lv_obj_t *root = nullptr, *hold_area = nullptr, *hold_bar = nullptr;
inline uint8_t current_page = 0, first_row = 0;
inline int confirm_row = -1;             // the action row that asked "tap again"
inline lv_timer_t *confirm_timer = nullptr;

struct Drawn {
  lv_obj_t *card = nullptr, *value = nullptr, *knob = nullptr, *minus = nullptr, *plus = nullptr, *label = nullptr;
  uint8_t row = 0;
  bool lit = false;   // drawn in the accent: a row that asks, or an action that runs
};
inline std::array<Drawn, 8> drawn{};
inline uint8_t drawn_count = 0;

inline bool visible() { return root != nullptr; }

struct Metrics {
  bool large;
  int width, height, pad, radius, inset, bar, bar_y, rows_y, row_h, gap, pager, bottom, pill_w, pill_h, switch_w, switch_h;
};
inline Metrics metrics() {
  int width = lv_display_get_horizontal_resolution(lv_display_get_default());
  int height = lv_display_get_vertical_resolution(lv_display_get_default());
  // The look decides the class (ui::large), never the width: a 480 px compact panel keeps the small rows.
  bool large = ui::large();
  return Metrics{large, width, height,
                 ui::px(large ? 20 : 10), ui::px(large ? 18 : 10), ui::px(large ? 18 : 10),
                 ui::px(large ? 56 : 36), ui::px(large ? 16 : 7),
                 ui::px(large ? 92 : 50), ui::px(large ? 52 : 32), ui::px(large ? 8 : 5),
                 ui::px(large ? 40 : 26), ui::px(large ? 16 : 10),
                 ui::px(large ? 44 : 30), ui::px(large ? 40 : 26),
                 ui::px(large ? 62 : 40), ui::px(large ? 34 : 22)};
}

inline lv_obj_t *plain(lv_obj_t *parent, int x, int y, int w, int h) {
  auto *obj = lv_obj_create(parent);
  lv_obj_remove_style_all(obj);
  lv_obj_remove_flag(obj, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
  lv_obj_set_pos(obj, x, y);
  lv_obj_set_size(obj, w, h);
  return obj;
}
inline lv_obj_t *text(lv_obj_t *parent, const std::string &value, const lv_font_t *font, theme::Role color,
                      lv_text_align_t align = LV_TEXT_ALIGN_LEFT) {
  auto *label = lv_label_create(parent);
  lv_label_set_text(label, value.c_str());
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, theme::color(color), 0);
  lv_obj_set_style_text_align(label, align, 0);
  lv_obj_set_height(label, lv_font_get_line_height(font));
  return label;
}
inline void draw();

// ---- the controls on a row ----
// A round key like the -/+ on the climate card: the finger sees the press in the same frame.
inline lv_obj_t *key(lv_obj_t *parent, const char *glyph, int x, int y, int w, int h, lv_event_cb_t handler,
                     void *data) {
  auto *button = plain(parent, x, y, w, h);
  lv_obj_add_flag(button, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(button, theme::color(theme::SETTING_KEY), 0);
  lv_obj_set_style_bg_color(button, theme::color(theme::SETTING_KEY_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_radius(button, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_opa(button, LV_OPA_40, LV_STATE_DISABLED);
  auto *label = text(button, glyph, icon_font ? icon_font : row_font, theme::INK);
  lv_obj_set_width(label, LV_SIZE_CONTENT);
  lv_obj_center(label);
  lv_obj_add_event_cb(button, handler, LV_EVENT_SHORT_CLICKED, data);
  lv_obj_add_event_cb(button, handler, LV_EVENT_LONG_PRESSED_REPEAT, data);
  return button;
}
// Not an lv_switch: the row itself is the target, so the pill only has to show the state and can
// never swallow half the taps that land next to it.
inline lv_obj_t *pill(lv_obj_t *parent, int x, int y, int w, int h, bool on) {
  auto *track = plain(parent, x, y, w, h);
  lv_obj_set_style_bg_opa(track, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(track, theme::color(on ? theme::ACCENT : theme::TOGGLE_OFF), 0);
  lv_obj_set_style_radius(track, LV_RADIUS_CIRCLE, 0);
  int inset = std::max(2, h / 10), size = h - 2 * inset;
  auto *knob = plain(track, knob_x(w, h, on), inset, size, size);
  lv_obj_set_style_bg_opa(knob, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(knob, theme::color(theme::KNOB), 0);
  lv_obj_set_style_radius(knob, LV_RADIUS_CIRCLE, 0);
  return knob;
}
inline void move_knob(Drawn &d, const Row &row) {
  if (!d.knob) return;
  auto *track = lv_obj_get_parent(d.knob);
  bool on = get(row) != 0;
  // Setting a style always repaints, so only a real change sets it; lv_obj_set_x checks by itself.
  const lv_color_t color = theme::color(on ? theme::ACCENT : theme::TOGGLE_OFF);
  if (!lv_color_eq(lv_obj_get_style_bg_color(track, LV_PART_MAIN), color)) lv_obj_set_style_bg_color(track, color, 0);
  // The size pill() gave the track, not its coordinates: draw() ends in refresh() before LVGL has laid the
  // new page out, when every width still reads 0 and a switch that is on would show its knob at the left.
  lv_obj_set_x(d.knob, knob_x(lv_obj_get_style_width(track, LV_PART_MAIN), lv_obj_get_style_height(track, LV_PART_MAIN), on));
}

// After any change: every row on this page tells its own value again. Cheap (eight labels at most) and
// it keeps rows that lean on each other honest -- lowering Brightness also lowers the two dim levels.
// The board runs it after a change from Home Assistant too, so a text is only set when it differs.
inline void refresh() {
  if (!root) return;
  const Page &page = page_at(current_page);
  for (uint8_t i = 0; i < drawn_count; ++i) {
    Drawn &d = drawn[i];
    const Row &row = page.rows[d.row];
    // An action that started or stopped running draws the page again, lit or not (a handful of rows).
    if (row.kind == Kind::action && row.own && row.own->active && d.lit != (busy_row(row) || confirm_row == d.row)) {
      draw();
      return;
    }
    if (d.value) {
      const std::string text = value_text(row);
      if (text != lv_label_get_text(d.value)) lv_label_set_text(d.value, text.c_str());
    }
    if (d.knob) move_knob(d, row);
    // A row whose switch is off (night times, the standby levels) is there but does nothing, and says so.
    bool live = live_row(row);
    const lv_opa_t opa = live ? LV_OPA_COVER : LV_OPA_50;
    if (d.card && lv_obj_get_style_opa(d.card, LV_PART_MAIN) != opa) lv_obj_set_style_opa(d.card, opa, 0);
    if (d.minus && readable(row)) {
      bool off = !live || at_end(row, get(row), -1);
      if (off) lv_obj_add_state(d.minus, LV_STATE_DISABLED); else lv_obj_remove_state(d.minus, LV_STATE_DISABLED);
    }
    if (d.plus && readable(row)) {
      bool off = !live || at_end(row, get(row), 1);
      if (off) lv_obj_add_state(d.plus, LV_STATE_DISABLED); else lv_obj_remove_state(d.plus, LV_STATE_DISABLED);
    }
  }
}

inline void forget_confirm() {
  if (confirm_timer) { lv_timer_delete(confirm_timer); confirm_timer = nullptr; }
  confirm_row = -1;
}

// ---- events ----
inline bool steady(int limit) { return !drift || limit <= 0 || drift() <= limit; }
// Holding - or + repeats, but at the pace of the climate card (five a second) instead of LVGL's ten.
// After a second of holding the steps grow; a single tap is always the small step.
inline uint32_t last_repeat = 0;
inline uint8_t repeats = 0;
constexpr uint8_t REPEATS_BEFORE_FAST = 5;
inline void step_event(lv_event_t *event) {
  if (!steady(tap_limit)) return;
  bool held = false;
  if (lv_event_get_code(event) == LV_EVENT_LONG_PRESSED_REPEAT) {
    uint32_t now = lv_tick_get();
    if (now - last_repeat < 200) return;
    last_repeat = now;
    if (repeats < 255) ++repeats;
    held = repeats > REPEATS_BEFORE_FAST;
  } else {
    repeats = 0;
    screen_hooks::run_touched();   // a tap, never a repeat of a key that is held (a plugin's click)
  }
  int data = (int) (intptr_t) lv_event_get_user_data(event);
  const Page &page = page_at(current_page);
  uint8_t index = (uint8_t) (data >> 1);
  if (index >= page.count) return;
  const Row &row = page.rows[index];
  if (!readable(row) || !writable(row) || !live_row(row)) return;
  int32_t value = get(row);
  int32_t next = stepped(row, value, data & 1 ? 1 : -1, held);
  if (next == value) return;
  put(row, next);
  refresh();
}
inline void row_event(lv_event_t *event) {
  if (!steady(tap_limit)) return;
  int index = (int) (intptr_t) lv_event_get_user_data(event);
  const Page &page = page_at(current_page);
  if (index < 0 || index >= page.count) return;
  const Row &row = page.rows[index];
  if (!live_row(row)) return;
  screen_hooks::run_touched();
  if (row.kind == Kind::page) { current_page = row.opens; first_row = 0; forget_confirm(); draw(); return; }
  if (row.kind == Kind::toggle && readable(row) && writable(row)) { put(row, get(row) ? 0 : 1); refresh(); return; }
  if (row.kind == Kind::choice && readable(row) && writable(row) && row.option_count) {
    put(row, (get(row) + 1) % row.option_count);
    refresh();
    return;
  }
  if (row.kind == Kind::action) {
    // Nothing on this page is worth a dialog, except the one row that takes the screen away for ten
    // seconds: it asks once, in place, and forgets the question after five.
    // A plugin's action without a question runs at once; one with a question asks first, as Restart does.
    if (row.confirm == NO_TEXT && !(row.own && row.own->confirm)) { act(row); refresh(); return; }
    if (confirm_row == index) { forget_confirm(); act(row); return; }
    forget_confirm();
    confirm_row = index;
    confirm_timer = lv_timer_create([](lv_timer_t *) { forget_confirm(); draw(); }, 5000, nullptr);
    lv_timer_set_repeat_count(confirm_timer, 1);
    draw();
  }
}
inline void close();
inline void back_event(lv_event_t *) {
  screen_hooks::run_touched();
  forget_confirm();
  if (current_page == 0) { close(); return; }
  current_page = page_at(current_page).parent;
  first_row = 0;
  draw();
}
inline uint8_t rows_per_page = 1;
inline void pager_step(int step) {
  int next = (int) first_row + step * (int) rows_per_page;
  if (next < 0) return;
  screen_hooks::run_touched();
  first_row = (uint8_t) next;
  forget_confirm();
  draw();
}

// ---- drawing ----
inline void draw() {
  if (!root) return;
  Metrics m = metrics();
  lv_obj_clean(root);
  drawn_count = 0;

  const Page &page = page_at(current_page);
  // Rows a screen does not have (the quarter turns on glass that is not square) leave the table out of sight entirely.
  std::array<uint8_t, 12> shown{};
  uint8_t count = 0;
  for (uint8_t i = 0; i < page.count && count < shown.size(); ++i)
    if (visible_row(page.rows[i])) shown[count++] = i;

  // The top bar of every page a tap opens (detail_bar): the back key and the page's name.
  detail_bar::make(root, page_title(page), {detail_bar::BACK, back_event});

  int span = m.height - m.rows_y - m.bottom;
  bool paged = false;
  // The pager every page shares (page_bar) stands on the foot of the glass, over the bottom margin.
  const int pager = page_bar::height() - m.bottom + m.gap;
  uint8_t per_page = std::min<uint8_t>(fitting_rows(span, m.row_h, m.gap, pager, count, paged), drawn.size());
  rows_per_page = per_page;
  // Always start a page on a page boundary, and never scroll a group that fits.
  first_row = paged && first_row < count ? (uint8_t) ((first_row / per_page) * per_page) : 0;

  int label_h = lv_font_get_line_height(row_font);
  for (uint8_t slot = 0; slot < per_page && first_row + slot < count; ++slot) {
    uint8_t index = shown[first_row + slot];
    const Row &row = page.rows[index];
    Drawn &d = drawn[slot];
    d = Drawn{};
    d.row = index;
    bool tappable = row.kind == Kind::page || row.kind == Kind::toggle || row.kind == Kind::choice ||
                    row.kind == Kind::action;
    bool asking = row.kind == Kind::action && confirm_row == index;
    bool lit = asking || busy_row(row);
    d.lit = lit;

    d.card = plain(root, m.pad, m.rows_y + slot * (m.row_h + m.gap), m.width - 2 * m.pad, m.row_h);
    lv_obj_set_style_bg_opa(d.card, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(d.card, theme::color(lit ? theme::ACCENT : theme::CARD), 0);
    lv_obj_set_style_radius(d.card, m.radius, 0);
    lv_obj_set_style_border_width(d.card, 1, 0);
    lv_obj_set_style_border_color(d.card, theme::color(lit ? theme::ACCENT : theme::LINE), 0);
    if (tappable) {
      lv_obj_add_flag(d.card, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_set_style_bg_color(d.card, theme::color(lit ? theme::ACCENT_PRESSED : theme::CARD_PRESSED), LV_STATE_PRESSED);
      lv_obj_add_event_cb(d.card, row_event, LV_EVENT_SHORT_CLICKED, (void *) (intptr_t) index);
    }

    int left = m.inset;
    if (row.icon && *row.icon) {
      auto *glyph = text(d.card, row.icon, icon_font ? icon_font : row_font, lit ? theme::ON_ACCENT : theme::ROW_ICON);
      int icon_h = lv_font_get_line_height(icon_font ? icon_font : row_font);
      lv_obj_set_width(glyph, LV_SIZE_CONTENT);
      lv_obj_set_pos(glyph, left, (m.row_h - icon_h) / 2);
      left += icon_h + (ui::px(m.large ? 12 : 8));
    }
    d.label = text(d.card, asking ? confirm_text(row) : label_text(row), row_font,
                   lit ? theme::ON_ACCENT : theme::INK);
    lv_obj_set_pos(d.label, left, (m.row_h - label_h) / 2);

    int right = m.width - 2 * m.pad - m.inset;  // free space from the right edge of the card
    if (row.kind == Kind::page) {
      auto *chevron = text(d.card, "\U000F0142", icon_font ? icon_font : row_font, theme::CHEVRON);
      int icon_h = lv_font_get_line_height(icon_font ? icon_font : row_font);
      lv_obj_set_width(chevron, LV_SIZE_CONTENT);
      lv_obj_set_pos(chevron, right - icon_h, (m.row_h - icon_h) / 2);
      lv_obj_set_width(d.label, right - icon_h - left - 6);
    } else if (row.kind == Kind::toggle) {
      d.knob = pill(d.card, right - m.switch_w, (m.row_h - m.switch_h) / 2, m.switch_w, m.switch_h, get(row) != 0);
      lv_obj_set_width(d.label, right - m.switch_w - left - 6);
    } else if (row.kind == Kind::number || row.kind == Kind::duration || row.kind == Kind::moment) {
      int y = (m.row_h - m.pill_h) / 2, value_w = ui::px(m.large ? 116 : 74);
      d.plus = key(d.card, "\U000F0415", right - m.pill_w, y, m.pill_w, m.pill_h, step_event,
                   (void *) (intptr_t) (index * 2 + 1));
      d.minus = key(d.card, "\U000F0374", right - m.pill_w - value_w - m.pill_w, y, m.pill_w, m.pill_h, step_event,
                    (void *) (intptr_t) (index * 2));
      d.value = text(d.card, value_text(row), row_font, theme::INK, LV_TEXT_ALIGN_CENTER);
      lv_obj_set_width(d.value, value_w);
      lv_obj_set_pos(d.value, right - m.pill_w - value_w, (m.row_h - label_h) / 2);
      lv_obj_set_width(d.label, right - 2 * m.pill_w - value_w - left - 6);
    } else if (row.kind == Kind::choice) {
      int value_w = ui::px(m.large ? 150 : 96), chip_h = m.pill_h;
      auto *chip = plain(d.card, right - value_w, (m.row_h - chip_h) / 2, value_w, chip_h);
      lv_obj_set_style_bg_opa(chip, LV_OPA_COVER, 0);
      lv_obj_set_style_bg_color(chip, theme::color(theme::SETTING_KEY), 0);
      lv_obj_set_style_radius(chip, LV_RADIUS_CIRCLE, 0);
      d.value = text(chip, value_text(row), row_font, theme::INK, LV_TEXT_ALIGN_CENTER);
      lv_obj_set_width(d.value, value_w - 8);
      lv_obj_set_pos(d.value, 4, (chip_h - label_h) / 2);
      lv_obj_set_width(d.label, right - value_w - left - 6);
    } else if (row.kind == Kind::info || (row.kind == Kind::action && row.own && row.own->text)) {
      // An action of a plugin may say how it is going on the right ("Playing"), as an info row does (plugin API 0.3).
      d.value = text(d.card, value_text(row), row_font, lit ? theme::ON_ACCENT : theme::MUTED, LV_TEXT_ALIGN_RIGHT);
      int value_w = (m.width - 2 * m.pad) / 2;
      lv_obj_set_width(d.value, value_w);
      lv_obj_set_pos(d.value, right - value_w, (m.row_h - label_h) / 2);
      lv_obj_set_width(d.label, right - value_w - left - 6);
    } else {
      lv_obj_set_width(d.label, right - left);
    }
    drawn_count = (uint8_t) (slot + 1);
  }
  refresh();

  if (!paged) return;
  // The pager every page shares (page_bar.h), the tile pages' own in the same place, so it is the one already learned.
  page_bar::show(page_bar::make(root, pager_step), first_row / per_page, (count + per_page - 1) / per_page);
}

inline void hide_hold_bar() {
  if (!hold_bar) return;
  lv_anim_delete(hold_bar, nullptr);
  lv_obj_add_flag(hold_bar, LV_OBJ_FLAG_HIDDEN);
}

inline void open(uint8_t page = 0) {
  hide_hold_bar();
  current_page = page < page_total() ? page : 0;
  first_row = 0;
  forget_confirm();
  if (before_open) before_open();
  if (!root) {
    root = lv_obj_create(lv_screen_active());
    lv_obj_remove_style_all(root);
    lv_obj_set_size(root, lv_pct(100), lv_pct(100));
    lv_obj_remove_flag(root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(root, LV_OBJ_FLAG_CLICKABLE);  // nothing leaks through to the tiles below
    lv_obj_set_style_bg_color(root, theme::color(theme::PAGE), 0);
    lv_obj_set_style_bg_opa(root, LV_OPA_COVER, 0);
  }
  lv_obj_move_foreground(root);
  draw();
}

inline void close() {
  forget_confirm();
  drawn_count = 0;
  if (root) { lv_obj_delete(root); root = nullptr; }
}

// A change of look while the page is open (Dark mode is one of its rows): the page is drawn again in place.
inline void restyle() {
  if (!root) return;
  lv_obj_set_style_bg_color(root, theme::color(theme::PAGE), 0);
  draw();
}

// ---- holding the top bar opens the page ----
// Not a tile, not a button in view: a press of `hold_ms` on the strip with the screen name. A line
// grows along the top edge while you hold, so the gesture explains itself the first time it happens.
inline void hold_step(void *object, int32_t value) {
  auto *bar = static_cast<lv_obj_t *>(object);
  int width = lv_display_get_horizontal_resolution(lv_display_get_default());
  if (drift && drift() > hold_limit) { hide_hold_bar(); return; }
  // The first quarter second stays invisible: a tap must not flash a line across the screen.
  if (value < 250) return;
  lv_obj_remove_flag(bar, LV_OBJ_FLAG_HIDDEN);
  lv_obj_set_width(bar, std::max<int32_t>(1, (int32_t) width * (value - 250) / (int32_t) (hold_ms - 250)));
}

inline void hold_event(lv_event_t *event) {
  auto code = lv_event_get_code(event);
  if (!hold_bar) return;
  if (code == LV_EVENT_PRESSED) {
    if (visible() || (may_open && !may_open())) return;
    // The line takes the look's blue when it starts; it is hidden the rest of the time.
    const lv_color_t blue = theme::color(theme::ACCENT);
    if (!lv_color_eq(lv_obj_get_style_bg_color(hold_bar, LV_PART_MAIN), blue)) lv_obj_set_style_bg_color(hold_bar, blue, 0);
    lv_obj_set_width(hold_bar, 1);
    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, hold_bar);
    lv_anim_set_values(&anim, 0, (int32_t) hold_ms);
    lv_anim_set_duration(&anim, (uint32_t) hold_ms);
    lv_anim_set_exec_cb(&anim, hold_step);
    lv_anim_set_completed_cb(&anim, [](lv_anim_t *) {
      hide_hold_bar();
      if (drift && drift() > hold_limit) return;
      if (may_open && !may_open()) return;
      open();
    });
    lv_anim_start(&anim);
    return;
  }
  hide_hold_bar();
}

// A transparent strip over the top bar plus the line that fills while it is held. Both belong to the
// page below, so they survive every redraw of the tiles. `below` is the first card that opens over the
// page: the strip goes under it, so a card's back button and its action at the top right get their taps
// (firmware 0.2.44-0.2.47 created the strip last, on top of every card).
inline void attach_hold(lv_obj_t *page, int x, int y, int width, int height, lv_obj_t *below = nullptr) {
  const bool large = ui::large();
  hold_area = plain(page, x, y, width, height);
  lv_obj_add_flag(hold_area, LV_OBJ_FLAG_CLICKABLE);
  // No pressed style at all: a repaint of a strip this wide costs a frame that the touch polling on a
  // resistive panel needs (the lesson of firmware 0.2.35).
  lv_obj_add_event_cb(hold_area, hold_event, LV_EVENT_PRESSED, nullptr);
  lv_obj_add_event_cb(hold_area, hold_event, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(hold_area, hold_event, LV_EVENT_PRESS_LOST, nullptr);
  hold_bar = plain(page, 0, 0, 1, ui::px(large ? 5 : 3));
  lv_obj_set_style_bg_opa(hold_bar, LV_OPA_COVER, 0);
  lv_obj_add_flag(hold_bar, LV_OBJ_FLAG_HIDDEN);
  lv_obj_move_foreground(hold_bar);
  if (below && lv_obj_get_parent(below) == page) {
    lv_obj_move_to_index(hold_area, lv_obj_get_index(below));
    lv_obj_move_to_index(hold_bar, lv_obj_get_index(below));
  }
}

}  // namespace settings_screen
#endif
