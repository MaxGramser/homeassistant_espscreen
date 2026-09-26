#pragma once
// Direct controls on the right half of a double-width card, like Home Assistant's
// own entity rows. Pure logic only: which keys a card shows, what they send, how
// a -/+ step lands on the entity's grid, and the status line beside them. The
// LVGL drawing lives in runtime_tiles.h; tests/test_tile_controls.cpp covers this.
#include "alarm_panel.h"
#include "screen_input.h"
#include "runtime_model.h"
#include "screen_text.h"
#include "theme.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace tile_controls {
// Home Assistant supported_features bits.
namespace feature {
constexpr uint32_t COVER_OPEN = 1, COVER_CLOSE = 2, COVER_POSITION = 4, COVER_STOP = 8;
constexpr uint32_t COVER_OPEN_TILT = 16, COVER_CLOSE_TILT = 32, COVER_STOP_TILT = 64, COVER_TILT_POSITION = 128;
constexpr uint32_t MEDIA_PAUSE = 1, MEDIA_VOLUME_SET = 4, MEDIA_VOLUME_MUTE = 8, MEDIA_PREVIOUS = 16, MEDIA_NEXT = 32, MEDIA_TURN_ON = 128, MEDIA_PLAY = 16384;
constexpr uint32_t VACUUM_TURN_ON = 1, VACUUM_TURN_OFF = 2, VACUUM_PAUSE = 4, VACUUM_STOP = 8, VACUUM_RETURN = 16, VACUUM_START = 8192;
}
// Material Design Icons glyphs the icon fonts carry (tile_icons.py FIXED).
namespace glyph {
constexpr const char *PLAY = "\U000F040A", *PAUSE = "\U000F03E4", *STOP = "\U000F04DB", *NEXT = "\U000F04AD", *PREVIOUS = "\U000F04AE";
constexpr const char *VOLUME = "\U000F057E", *MUTED = "\U000F0581", *UP = "\U000F005D", *DOWN = "\U000F0045";
constexpr const char *EXPAND = "\U000F084E", *COLLAPSE = "\U000F084C", *DOCK = "\U000F05F8", *PLUS = "\U000F0415", *MINUS = "\U000F0374";
constexpr const char *LEFT = "\U000F0141", *RIGHT = "\U000F0142", *CLOSE = "\U000F0156", *POWER = "\U000F0425", *FIRE = "\U000F0238";
constexpr const char *SNOWFLAKE = "\U000F0717", *HEAT_COOL = "\U000F1A79", *AUTO = "\U000F1B17", *DRY = "\U000F058E", *FAN = "\U000F0210";
constexpr const char *BLINDS_OPEN = "\U000F1011", *BLINDS = "\U000F00AC", *MORE = "\U000F01D8";
}
enum Command {
  NONE = 0, COVER_OPEN, COVER_STOP, COVER_CLOSE, VACUUM_START, VACUUM_PAUSE, VACUUM_STOP, VACUUM_DOCK,
  MEDIA_PREVIOUS, MEDIA_PLAY_PAUSE, MEDIA_NEXT, MEDIA_MUTE, TIMER_START, TIMER_PAUSE, TIMER_CANCEL,
  HVAC_MODE, SELECT_PREVIOUS, SELECT_NEXT, RUN, TOGGLE, STEP_DOWN, STEP_UP,
  COVER_OPEN_TILT, COVER_STOP_TILT, COVER_CLOSE_TILT,
  OPEN_CARD  // "…": the modes that did not fit are on the card (firmware 0.3.1+)
};
struct Key { const char *icon = ""; int command = NONE; std::string arg; bool checked = false, disabled = false; };
struct Action { std::string service, key, value; bool valid() const { return !service.empty(); } };
using runtime_tiles::Tile;

// Panel kinds: keys (a row of pill buttons), stepper (-/+ pill), slider, toggle, run.
inline bool is_key_row(const std::string &c) { return c == "buttons" || c == "mode" || c == "playback" || c == "chevrons"; }
inline bool is_slider(const std::string &c) { return c == "volume" || c == "brightness" || c == "speed" || c == "position" || c == "slider"; }
// The slider "a small slider on the tile" asks for, per domain: what a light, a fan, a blind, a player or a
// number has to slide. A double-width card draws it as the panel's slider beside the name; a domain without
// one (a switch) has no small slider either.
inline std::string inline_kind(const std::string &domain) {
  if (domain == "light") return "brightness";
  if (domain == "fan") return "speed";
  if (domain == "cover") return "position";
  if (domain == "media_player") return "volume";
  if (domain == "number" || domain == "input_number") return "slider";
  return {};
}
// The extra slat choice lives in the existing controls field. The primary group
// stays independent, including when capabilities or the tile size change.
inline bool cover_tilt_selected(const Tile &t) {
  return t.domain()=="cover" && (t.controls=="tilt"||t.controls=="buttons_tilt"||t.controls=="position_tilt");
}
// A climate's second group (firmware 0.3.1+): the mode keys under the setpoint, where a taller card has the room.
inline bool climate_modes_selected(const Tile &t) {
  return t.domain()=="climate" && t.controls=="setpoint_mode";
}
// A select's "stepper" is a pair of chevron keys; numbers and climate get the -/+ pill.
inline std::string panel_kind(const Tile &t) {
  auto c = t.controls, d = t.domain();
  if(d=="cover"){if(c=="tilt")return {};if(c=="buttons_tilt")return "buttons";if(c=="position_tilt")return "position";}
  if(d=="climate"&&c=="setpoint_mode")return "setpoint";
  // The small slider of a wide card is that domain's slider: the manager sends no control set beside it
  // (resolve_controls), so the kind comes from the domain.
  if (c.empty() && t.inline_control == "slider") return inline_kind(d);
  if (c == "stepper" && (d == "select" || d == "input_select")) return "chevrons";
  return c;
}
inline bool has_mode(const std::string &hvac_modes, const char *mode) { return hvac_modes.find("\"" + std::string(mode) + "\"") != std::string::npos; }
// Home Assistant's colour for a climate mode (the card and its mode keys use it).
inline uint32_t mode_color(const std::string &mode) {
  using namespace theme::ha;
  if (mode == "heat") return DEEP_ORANGE;
  if (mode == "cool") return BLUE;
  if (mode == "heat_cool") return AMBER;
  if (mode == "auto") return GREEN;
  if (mode == "fan_only") return CYAN;
  if (mode == "dry") return ORANGE;
  return GREY;
}
// Binary sensor classes Home Assistant draws red while they are on (its --state-binary_sensor-<class>-on-color): an
// alarm, a problem, a low battery, an unlocked lock. header_bar.ALARM_CLASSES gives the top bar the same list.
inline bool alarm_class(const std::string &device_class) {
  for (const char *alarm : {"battery", "carbon_monoxide", "gas", "heat", "lock", "moisture", "problem", "safety", "smoke",
                            "sound", "tamper"})
    if (device_class == alarm) return true;
  return false;
}
// Home Assistant's colour for a weather condition (--state-weather-<condition>-color); a condition it has none for
// takes its --state-active-color.
inline uint32_t weather_color(const std::string &condition) {
  using namespace theme::ha;
  if (condition == "sunny") return AMBER;
  if (condition == "clear-night") return DEEP_PURPLE;
  if (condition == "partlycloudy") return BLUE_GREY;
  if (condition == "cloudy") return LIGHT_GREY;
  if (condition == "fog") return GREY;
  if (condition == "rainy") return BLUE;
  if (condition == "pouring") return INDIGO;
  if (condition == "snowy") return ICE;
  if (condition == "snowy-rainy") return LIGHT_BLUE;
  if (condition == "hail") return CYAN;
  if (condition == "lightning") return YELLOW;
  if (condition == "lightning-rainy") return LIME;
  if (condition == "windy" || condition == "windy-variant") return GREEN;
  if (condition == "exceptional") return RED;
  return AMBER;
}
// The colour of a tile while Home Assistant calls it active (Tile::active; anything inactive is grey): its
// stateColorCss() (frontend src/common/entity/state_color.ts) for the domains it colours by state, and a colour of
// our own per kind for those it draws in one neutral blue, such as scenes, selects, numbers and sensors (0.2.3).
// A state Home Assistant has no colour of its own for takes its --state-active-color, amber (firmware 0.2.71+).
// Colours set in a Lovelace card or theme are no entity attributes and never reach the screen.
inline uint32_t accent(const Tile &t) {
  using namespace theme::ha;
  const auto d = t.domain();
  if (d == "binary_sensor") return alarm_class(t.device_class) ? RED : AMBER;
  if (d == "light" || d == "switch" || d == "input_boolean" || d == "script" || d == "timer" || d == "camera") return AMBER;
  if (d == "climate") { const uint32_t c = mode_color(t.state); return c == GREY ? AMBER : c; }
  if (d == "vacuum") return t.state == "error" ? RED : TEAL;
  if (d == "fan") return CYAN;
  if (d == "cover" || d == "scene") return PURPLE;
  if (d == "media_player") return LIGHT_BLUE;
  if (d == "select" || d == "input_select") return INDIGO;
  if (d == "number" || d == "input_number") return TEAL;
  if (d == "weather") return weather_color(t.state);
  if (d == "sun") return t.state == "above_horizon" ? AMBER : INDIGO;
  // At home green; in another zone blue (--state-person-active-color).
  if (d == "person") return t.state == "home" ? GREEN : BLUE;
  // An alarm panel: armed green, the delays orange, going off red (--state-alarm_control_panel-*-color).
  if (d == "alarm_control_panel") return alarm_panel::color(t.state);
  if (d == "sensor") {
    // A battery by its charge, as Home Assistant's battery_color.ts: green from 70 %, orange from 30 %, red below.
    if (t.device_class == "battery") {
      char *end = nullptr;
      const float charge = std::strtof(t.state.c_str(), &end);
      if (end != t.state.c_str() && *end == '\0' && std::isfinite(charge)) return charge >= 70 ? GREEN : charge >= 30 ? ORANGE : RED;
    }
    if (t.unit == "lx") return AMBER;
    if (t.unit == "°C" || t.unit == "°F") return DEEP_ORANGE;
    if (t.unit == "kWh" || t.unit == "Wh") return PURPLE;
    if (t.unit == "%") return TEAL;
  }
  return BLUE;
}
inline const char *mode_icon(const std::string &mode) {
  if (mode == "off") return glyph::POWER;
  if (mode == "heat") return glyph::FIRE;
  if (mode == "cool") return glyph::SNOWFLAKE;
  if (mode == "heat_cool") return glyph::HEAT_COOL;
  if (mode == "auto") return glyph::AUTO;
  if (mode == "dry") return glyph::DRY;
  return glyph::FAN;
}
// Covers that move sideways get the horizontal arrows, like Home Assistant.
inline bool sideways_cover(const std::string &device_class) {
  return device_class == "curtain" || device_class == "awning" || device_class == "door" || device_class == "gate";
}
inline float numeric_state(const Tile &t) {
  char *end; float value = std::strtof(t.state.c_str(), &end);
  return end != t.state.c_str() && std::isfinite(value) ? value : NAN;
}
// Value the -/+ pill edits: the climate setpoint or the number itself.
inline float edit_target(const Tile &t) { return t.domain() == "climate" ? t.target : numeric_state(t); }
inline float edit_step(const Tile &t) {
  float step = t.step;
  if (!std::isfinite(step) || step <= 0) step = t.domain() == "climate" ? 0.5f : 1.0f;
  return step;
}
// One step up or down, snapped to the entity's grid and kept inside its range.
inline float step_value(float current, float step, float minimum, float maximum, int direction) {
  if (!std::isfinite(step) || step <= 0) step = 1;
  bool has_min = std::isfinite(minimum), has_max = std::isfinite(maximum) && (!has_min || maximum >= minimum);
  float origin = has_min ? minimum : 0;
  if (!std::isfinite(current)) current = has_min ? minimum : 0;
  float next = origin + std::round((current + direction * step - origin) / step) * step;
  if (has_min) next = std::fmax(next, minimum);
  if (has_max) next = std::fmin(next, maximum);
  return next;
}
// Whole degrees when the entity steps by whole units, one decimal otherwise, with the language's decimal mark.
inline std::string format_value(float value, float step, const char *suffix) {
  if (!std::isfinite(value)) return "--";
  return screen_text::decimal(value, step >= 1 ? 0 : 1) + suffix;
}
// Home Assistant's word for a climate fan ('f') or swing ('s') setting that Home Assistant names itself ("low" is
// "Laag" in Dutch); an integration's own mode reads as its name ("fan_only" -> "Fan only").
inline std::string climate_setting_text(char kind, std::string raw) {
  using namespace screen_text;
  struct Word { const char *value; uint16_t id; };
  static const Word fan[] = {{"auto", txt::ha_climate_fan_auto}, {"low", txt::ha_climate_fan_low},
                             {"medium", txt::ha_climate_fan_medium}, {"high", txt::ha_climate_fan_high},
                             {"middle", txt::ha_climate_fan_middle}, {"focus", txt::ha_climate_fan_focus},
                             {"diffuse", txt::ha_climate_fan_diffuse}, {"top", txt::ha_climate_fan_top},
                             {"on", txt::ha_climate_fan_on}, {"off", txt::ha_climate_fan_off}};
  static const Word swing[] = {{"on", txt::ha_climate_swing_on}, {"off", txt::ha_climate_swing_off},
                               {"both", txt::ha_climate_swing_both}, {"vertical", txt::ha_climate_swing_vertical},
                               {"horizontal", txt::ha_climate_swing_horizontal}};
  if (kind == 'f') { for (const auto &w : fan) if (raw == w.value) return tr(w.id); }
  if (kind == 's') { for (const auto &w : swing) if (raw == w.value) return tr(w.id); }
  for (char &c : raw) if (c == '_') c = ' ';
  if (!raw.empty() && raw[0] >= 'a' && raw[0] <= 'z') raw[0] = static_cast<char>(raw[0] - 'a' + 'A');
  return raw;
}
inline const char *climate_mode_text(const std::string &mode) {
  if (mode == "off") return screen_text::tr(screen_text::txt::ha_climate_off);
  if (mode == "heat") return screen_text::tr(screen_text::txt::ha_climate_heat);
  if (mode == "cool") return screen_text::tr(screen_text::txt::ha_climate_cool);
  if (mode == "heat_cool") return screen_text::tr(screen_text::txt::ha_climate_heat_cool);
  if (mode == "auto") return screen_text::tr(screen_text::txt::ha_climate_auto);
  if (mode == "dry") return screen_text::tr(screen_text::txt::ha_climate_dry);
  if (mode == "fan_only") return screen_text::tr(screen_text::txt::ha_climate_fan_only);
  return mode.c_str();
}
inline const char *climate_action_text(const std::string &action) {
  if (action == "heating") return screen_text::tr(screen_text::txt::ha_hvac_action_heating);
  if (action == "cooling") return screen_text::tr(screen_text::txt::ha_hvac_action_cooling);
  if (action == "idle") return screen_text::tr(screen_text::txt::ha_hvac_action_idle);
  if (action == "off") return screen_text::tr(screen_text::txt::ha_hvac_action_off);
  if (action == "drying") return screen_text::tr(screen_text::txt::ha_hvac_action_drying);
  if (action == "fan") return screen_text::tr(screen_text::txt::ha_hvac_action_fan);
  if (action == "preheating") return screen_text::tr(screen_text::txt::ha_hvac_action_preheating);
  if (action == "defrosting") return screen_text::tr(screen_text::txt::ha_hvac_action_defrosting);
  return "";
}
// ---- The climate card (firmware 0.2.80) ----
// One computed card for every board: what a thermostat can be set to, taken from Home Assistant's own
// attributes. The drawing is climate_card.h (where the parts go) and runtime_tiles.h (the widgets).
inline std::string lower_case(std::string value) {
  for (char &c : value) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
  return value;
}
// The items of a JSON list Home Assistant sent, at most `limit`.
inline std::vector<std::string> list_values(const std::string &json, unsigned limit) {
  std::vector<std::string> values;
  for (unsigned i = 0; i < limit; ++i) {
    std::string item = screen_input::list_item(json, i);
    if (item.empty()) break;
    values.push_back(item);
  }
  return values;
}
// A thermostat is off when Home Assistant says its mode is off (or says nothing at all).
inline bool climate_off(const Tile &t) {
  const std::string mode = lower_case(t.state);
  return mode == "off" || mode.empty() || mode == "unknown" || mode == "unavailable";
}
// The icon of a mode, as Home Assistant's own thermostat card draws it.
inline const char *climate_mode_icon(const std::string &mode) {
  if (mode == "heat") return glyph::FIRE;
  if (mode == "cool") return glyph::SNOWFLAKE;
  if (mode == "heat_cool") return glyph::HEAT_COOL;
  if (mode == "auto") return glyph::AUTO;
  if (mode == "dry") return glyph::DRY;
  if (mode == "fan_only") return glyph::FAN;
  return glyph::POWER;
}
// The modes the card offers, in Home Assistant's order, without "off": the power key already does that one.
// A device that reports no modes at all still shows the one it is in, so the card is never empty.
inline std::vector<std::string> climate_modes(const Tile &t) {
  std::vector<std::string> modes;
  for (const auto &raw : list_values(t.extra().hvac_modes, 8)) {
    const std::string mode = lower_case(raw);
    if (mode != "off") modes.push_back(mode);
  }
  if (modes.empty() && !climate_off(t)) modes.push_back(lower_case(t.state));
  return modes;
}
// One row of settings under the modes: the fan and the swing, each with the entity's own choices, in its own
// order and in Home Assistant's words. 'f' and 's' are what a tap reports back.
struct ClimateRow {
  char kind = 0;
  const char *icon = "";
  std::vector<std::string> values, labels;
  std::string current;
};
inline std::vector<ClimateRow> climate_rows(const Tile &t) {
  std::vector<ClimateRow> rows;
  const auto &x = t.extra();
  const struct { char kind; const char *icon; const std::string &modes; const std::string &current; } wanted[] = {
      {'f', glyph::FAN, x.fan_modes, x.fan_mode},
      {'s', "\U000F1C91", x.swing_modes, x.swing_mode},
  };
  for (const auto &row : wanted) {
    auto values = list_values(row.modes, 6);
    if (values.empty()) continue;
    ClimateRow out;
    out.kind = row.kind;
    out.icon = row.icon;
    out.current = row.current;
    for (const auto &value : values) out.labels.push_back(climate_setting_text(row.kind, value));
    out.values = std::move(values);
    rows.push_back(std::move(out));
  }
  return rows;
}
// What a tap on a row sends.
inline Action climate_row_action(char kind, const std::string &value) {
  if (kind == 'f') return {"climate.set_fan_mode", "fan_mode", value};
  return {"climate.set_swing_mode", "swing_mode", value};
}
// The line under the name: what the device is doing (or its mode), the temperature it measures and the
// humidity it reports. `brief` is the form for glass with no room for a line of its own, where the line moves
// under the setpoint: the temperature without the word before it, and no humidity.
inline std::string climate_card_status(const Tile &t, bool brief = false) {
  if (!t.available()) return screen_text::tr(screen_text::txt::ha_unavailable);
  std::string status = climate_off(t) ? std::string(screen_text::tr(screen_text::txt::ha_off))
                                      : std::string(climate_action_text(lower_case(t.extra().hvac_action)));
  if (status.empty()) status = climate_mode_text(lower_case(t.state));
  if (std::isfinite(t.current)) {
    const std::string value = screen_text::decimal(t.current, 1) + "°";
    status += " · " + (brief ? value : screen_text::fill(screen_text::txt::climate_now, "value", value));
  }
  if (!brief && std::isfinite(t.humidity)) status += " · " + screen_text::percent(static_cast<int>(std::lround(t.humidity)));
  return status;
}
inline const char *cover_state_text(const std::string &state) {
  if (state == "open") return screen_text::tr(screen_text::txt::ha_cover_open);
  if (state == "closed") return screen_text::tr(screen_text::txt::ha_cover_closed);
  if (state == "opening") return screen_text::tr(screen_text::txt::ha_cover_opening);
  if (state == "closing") return screen_text::tr(screen_text::txt::ha_cover_closing);
  return state.c_str();
}
inline const char *media_state_text(const std::string &state) {
  if (state == "playing") return screen_text::tr(screen_text::txt::ha_media_playing);
  if (state == "paused") return screen_text::tr(screen_text::txt::ha_media_paused);
  if (state == "idle") return screen_text::tr(screen_text::txt::ha_media_idle);
  if (state == "standby") return screen_text::tr(screen_text::txt::ha_media_standby);
  if (state == "buffering") return screen_text::tr(screen_text::txt::media_loading);
  if (state == "on") return screen_text::tr(screen_text::txt::ha_on);
  if (state == "off") return screen_text::tr(screen_text::txt::ha_off);
  return state.c_str();
}
// A binary sensor's state in Home Assistant's words for its device class: a door is Open or Closed, a leak sensor
// Wet or Dry, in the screen's language (screen.ha.binary, taken from Home Assistant's own translations). The add-on's
// header_bar.BINARY_STATES reads the same words from the same file for the top bar and the history card. Without a
// class, or with one this table lacks: On and Off.
struct BinaryWords { const char *device_class; uint16_t on, off; };
constexpr BinaryWords BINARY_WORDS[] = {
    {"battery", screen_text::txt::ha_binary_battery_on, screen_text::txt::ha_binary_battery_off},
    {"battery_charging", screen_text::txt::ha_binary_battery_charging_on, screen_text::txt::ha_binary_battery_charging_off},
    {"carbon_monoxide", screen_text::txt::ha_binary_carbon_monoxide_on, screen_text::txt::ha_binary_carbon_monoxide_off},
    {"cold", screen_text::txt::ha_binary_cold_on, screen_text::txt::ha_binary_cold_off},
    {"connectivity", screen_text::txt::ha_binary_connectivity_on, screen_text::txt::ha_binary_connectivity_off},
    {"door", screen_text::txt::ha_binary_door_on, screen_text::txt::ha_binary_door_off},
    {"garage_door", screen_text::txt::ha_binary_garage_door_on, screen_text::txt::ha_binary_garage_door_off},
    {"gas", screen_text::txt::ha_binary_gas_on, screen_text::txt::ha_binary_gas_off},
    {"heat", screen_text::txt::ha_binary_heat_on, screen_text::txt::ha_binary_heat_off},
    {"light", screen_text::txt::ha_binary_light_on, screen_text::txt::ha_binary_light_off},
    {"lock", screen_text::txt::ha_binary_lock_on, screen_text::txt::ha_binary_lock_off},
    {"moisture", screen_text::txt::ha_binary_moisture_on, screen_text::txt::ha_binary_moisture_off},
    {"motion", screen_text::txt::ha_binary_motion_on, screen_text::txt::ha_binary_motion_off},
    {"moving", screen_text::txt::ha_binary_moving_on, screen_text::txt::ha_binary_moving_off},
    {"occupancy", screen_text::txt::ha_binary_occupancy_on, screen_text::txt::ha_binary_occupancy_off},
    {"opening", screen_text::txt::ha_binary_opening_on, screen_text::txt::ha_binary_opening_off},
    {"plug", screen_text::txt::ha_binary_plug_on, screen_text::txt::ha_binary_plug_off},
    {"power", screen_text::txt::ha_binary_power_on, screen_text::txt::ha_binary_power_off},
    {"presence", screen_text::txt::ha_binary_presence_on, screen_text::txt::ha_binary_presence_off},
    {"problem", screen_text::txt::ha_binary_problem_on, screen_text::txt::ha_binary_problem_off},
    {"running", screen_text::txt::ha_binary_running_on, screen_text::txt::ha_binary_running_off},
    {"safety", screen_text::txt::ha_binary_safety_on, screen_text::txt::ha_binary_safety_off},
    {"smoke", screen_text::txt::ha_binary_smoke_on, screen_text::txt::ha_binary_smoke_off},
    {"sound", screen_text::txt::ha_binary_sound_on, screen_text::txt::ha_binary_sound_off},
    {"tamper", screen_text::txt::ha_binary_tamper_on, screen_text::txt::ha_binary_tamper_off},
    {"update", screen_text::txt::ha_binary_update_on, screen_text::txt::ha_binary_update_off},
    {"vibration", screen_text::txt::ha_binary_vibration_on, screen_text::txt::ha_binary_vibration_off},
    {"window", screen_text::txt::ha_binary_window_on, screen_text::txt::ha_binary_window_off},
};
inline const char *binary_state_text(const std::string &device_class, bool on) {
  for (const auto &words : BINARY_WORDS)
    if (device_class == words.device_class) return screen_text::tr(on ? words.on : words.off);
  return screen_text::tr(on ? screen_text::txt::ha_on : screen_text::txt::ha_off);
}
// Status line beside a control panel: what Home Assistant shows under the name.
inline std::string status_text(const Tile &t) {
  auto d = t.domain();
  if (d == "climate") {
    std::string text = climate_action_text(t.extra().hvac_action);
    if (text.empty()) text = climate_mode_text(t.state);
    if (std::isfinite(t.current)) text += " · " + screen_text::decimal(t.current, 1) + "°";
    return text;
  }
  if (d == "cover") {
    std::string text = cover_state_text(t.state);
    if (std::isfinite(t.position)) text += " · " + screen_text::percent((int) std::lround(t.position));
    return text;
  }
  if (d == "media_player") {
    const std::string &title = t.extra().media_title;
    std::string text = (t.state == "playing" || t.state == "paused") && !title.empty() ? title : media_state_text(t.state);
    if (std::isfinite(t.volume) && (t.supported & feature::MEDIA_VOLUME_SET)) text += " · " + screen_text::percent((int) std::lround(t.volume * 100));
    return text;
  }
  return {};
}
// The cover card (firmware 0.2.50+) offers what Home Assistant's own dialog does: a position slider when the
// cover reports positions, a tilt slider for slats, open, stop and close, and the tilt keys of slats that
// tilt without a position. A cover whose features are not known yet gets the three keys.
struct CoverCard { bool position = false, tilt = false, keys = false, tilt_keys = false; };
inline CoverCard cover_card(const Tile &t) {
  CoverCard card;
  const uint32_t f = t.supported;
  if (!f) { card.keys = true; return card; }
  card.position = f & feature::COVER_POSITION;
  card.tilt = f & feature::COVER_TILT_POSITION;
  card.keys = f & (feature::COVER_OPEN | feature::COVER_CLOSE | feature::COVER_STOP);
  card.tilt_keys = !card.tilt && (f & (feature::COVER_OPEN_TILT | feature::COVER_CLOSE_TILT | feature::COVER_STOP_TILT));
  return card;
}
// The card's status line: the state, the position, and the tilt where the cover has one.
inline std::string cover_card_status(const Tile &t) {
  std::string text = status_text(t);
  if ((t.supported & feature::COVER_TILT_POSITION) && std::isfinite(t.extra().tilt)) {
    text += " · " + screen_text::fill(screen_text::txt::cover_tilt_value, "n", (int) std::lround(t.extra().tilt));
  }
  return text;
}
// Open, stop and close as the cover supports them (all three while its features are unknown). A key that
// cannot move the cover further is disabled, unless the cover is on its way the other way.
inline unsigned cover_keys(const Tile &t, std::array<Key, 3> &out) {
  unsigned n = 0;
  const uint32_t f = t.supported ? t.supported : feature::COVER_OPEN | feature::COVER_STOP | feature::COVER_CLOSE;
  bool sideways = sideways_cover(t.device_class);
  bool fully_open = std::isfinite(t.position) ? t.position >= 99.5f : t.state == "open";
  bool fully_closed = std::isfinite(t.position) ? t.position <= 0.5f : t.state == "closed";
  if (f & feature::COVER_OPEN) out[n++] = Key{sideways ? glyph::EXPAND : glyph::UP, COVER_OPEN, "", t.state == "opening", fully_open && t.state != "closing"};
  if (f & feature::COVER_STOP) out[n++] = Key{glyph::STOP, COVER_STOP, "", false, false};
  if (f & feature::COVER_CLOSE) out[n++] = Key{sideways ? glyph::COLLAPSE : glyph::DOWN, COVER_CLOSE, "", t.state == "closing", fully_closed && t.state != "opening"};
  return n;
}
inline unsigned cover_tilt_keys(const Tile &t, std::array<Key, 3> &out) {
  unsigned n = 0;
  const float tilt = t.extra().tilt;
  if (t.supported & feature::COVER_OPEN_TILT) out[n++] = Key{glyph::BLINDS_OPEN, COVER_OPEN_TILT, "", false, std::isfinite(tilt) && tilt >= 99.5f};
  if (t.supported & feature::COVER_STOP_TILT) out[n++] = Key{glyph::STOP, COVER_STOP_TILT, "", false, false};
  if (t.supported & feature::COVER_CLOSE_TILT) out[n++] = Key{glyph::BLINDS, COVER_CLOSE_TILT, "", false, std::isfinite(tilt) && tilt <= 0.5f};
  return n;
}
// The same percentage direction and capability guard for overlay and tile. A cover whose features Home Assistant did
// not report (0) still takes its position, as the slider did before firmware 0.3.1; the slats only when it says so.
inline Action cover_position_action(const Tile &t,int raw,bool tilt) {
  const bool can=tilt?(t.supported&feature::COVER_TILT_POSITION):(!t.supported||(t.supported&feature::COVER_POSITION));
  if(t.domain()!="cover"||!t.available()||!can)return {};
  const int percent=(int)std::lround(std::clamp(raw,0,1000)/10.0f);
  return tilt?Action{"cover.set_cover_tilt_position","tilt_position",std::to_string(percent)}
             :Action{"cover.set_cover_position","position",std::to_string(100-percent)};
}
// A climate's mode keys: the modes Home Assistant lists for this device, in its order, as many as `room` holds.
// When they do not all fit, the last key is "…" and opens the card, which has every mode (firmware 0.3.1+).
template <size_t N> inline unsigned climate_mode_keys(const Tile &t, std::array<Key, N> &out, unsigned room = N) {
  room = std::min<unsigned>(room, N);
  const auto modes = list_values(t.extra().hvac_modes, 8);
  const bool more = modes.size() > room;
  const unsigned shown = more ? (room ? room - 1 : 0) : (unsigned) modes.size();
  const std::string current = lower_case(t.state);
  unsigned n = 0;
  for (unsigned i = 0; i < shown; ++i) {
    const std::string mode = lower_case(modes[i]);
    out[n++] = Key{mode_icon(mode), HVAC_MODE, mode, current == mode, false};
  }
  if (more && room) out[n++] = Key{glyph::MORE, OPEN_CARD, "", false, false};
  return n;
}
// A thermostat tile's mode bar (firmware 0.3.3): heat and cool before the rest, so an airco shows both ways it can go
// and not only the first Home Assistant lists; never off, which the tile's circle switches; and the mode it is in
// always among them. When the modes do not all fit, the last place is "…" and opens the card with every mode; a bar
// with room for two shows two modes rather than one and a "…". A device with one mode has no bar: its circle is
// all it needs.
template <size_t N> inline unsigned climate_bar_keys(const Tile &t, std::array<Key, N> &out, unsigned room = N) {
  static const char *const ORDER[] = {"heat", "cool", "heat_cool", "auto", "dry", "fan_only"};
  room = std::min<unsigned>(room, N);
  std::vector<std::string> modes;
  const auto listed = list_values(t.extra().hvac_modes, 8);
  for (const char *mode : ORDER)
    for (const auto &raw : listed)
      if (lower_case(raw) == mode) { modes.push_back(mode); break; }
  if (modes.size() < 2 || room < 2) return 0;
  const bool more = modes.size() > room;
  const unsigned shown = !more ? (unsigned) modes.size() : room == 2 ? 2 : room - 1;
  std::vector<std::string> pick(modes.begin(), modes.begin() + shown);
  const std::string current = lower_case(t.state);
  if (std::find(modes.begin(), modes.end(), current) != modes.end() && std::find(pick.begin(), pick.end(), current) == pick.end())
    pick.back() = current;
  unsigned n = 0;
  for (const auto &mode : pick) out[n++] = Key{mode_icon(mode), HVAC_MODE, mode, mode == current, false};
  if (more && shown < room) out[n++] = Key{glyph::MORE, OPEN_CARD, "", false, false};
  return n;
}
// The row of up to three pill keys for a key-row panel; returns how many.
//
// A key is greyed for one reason only (firmware 0.2.90+): a command of this tile is on its way to Home Assistant
// and has not been answered yet (Tile::loading, the same wait the busy sheet and the cards follow). It is never
// greyed because of what the device is doing. A robot that says "docked" while it is already cleaning left its
// Stop and its Dock unreachable exactly when they were wanted: the state word is Home Assistant's news, and news
// can be late. The cover's keys are the one place a state still closes a key, and it is not a state word there
// but the position: a blind at its end stop cannot open further, which is what Home Assistant's own card shows.
// `now` is millis(); 0 greys nothing, for the tests and for callers without a clock.
inline unsigned keys_for(const Tile &t, std::array<Key, 3> &out, uint32_t now = 0) {
  auto d = t.domain(); auto c = panel_kind(t); unsigned n = 0;
  auto add = [&](const char *icon, int command, bool disabled = false, bool checked = false, const std::string &arg = "") {
    if (n < out.size()) out[n++] = Key{icon, command, arg, checked, disabled};
  };
  if (c == "buttons" && d == "cover") {
    // The tile keys are the card's keys, without the direction a moving cover shows there.
    if (t.supported) for (unsigned i = 0, count = cover_keys(t, out); i < count; ++i) { out[i].checked = false; ++n; }
  } else if (c == "buttons" && d == "vacuum") {
    // The state decides which key the first one is, never whether a key can be pressed: send it home while it
    // still says "docked".
    bool cleaning = t.state == "cleaning";
    if (cleaning && (t.supported & feature::VACUUM_PAUSE)) add(glyph::PAUSE, VACUUM_PAUSE);
    else if (cleaning && (t.supported & feature::VACUUM_TURN_OFF) && !(t.supported & feature::VACUUM_START)) add(glyph::PAUSE, VACUUM_STOP);
    else if (t.supported & (feature::VACUUM_START | feature::VACUUM_TURN_ON)) add(glyph::PLAY, VACUUM_START);
    if (t.supported & feature::VACUUM_STOP) add(glyph::STOP, VACUUM_STOP);
    if (t.supported & feature::VACUUM_RETURN) add(glyph::DOCK, VACUUM_DOCK);
  } else if (c == "buttons" && d == "timer") {
    bool active = t.state == "active";
    add(active ? glyph::PAUSE : glyph::PLAY, active ? TIMER_PAUSE : TIMER_START);
    add(glyph::CLOSE, TIMER_CANCEL);
  } else if (c == "playback") {
    if (t.supported & feature::MEDIA_PREVIOUS) add(glyph::PREVIOUS, MEDIA_PREVIOUS);
    if (t.supported & (feature::MEDIA_PLAY | feature::MEDIA_PAUSE)) add(t.state == "playing" ? glyph::PAUSE : glyph::PLAY, MEDIA_PLAY_PAUSE, !(t.supported & (t.state == "playing" ? feature::MEDIA_PAUSE : feature::MEDIA_PLAY)));
    if (t.supported & feature::MEDIA_NEXT) add(glyph::NEXT, MEDIA_NEXT);
  } else if (c == "mode") {
    n = climate_mode_keys(t, out);
  } else if (c == "chevrons") {
    // Nothing to step through is not a state that can lag: without two options there is no next one.
    add(glyph::LEFT, SELECT_PREVIOUS, t.extra().options.size() < 2);
    add(glyph::RIGHT, SELECT_NEXT, t.extra().options.size() < 2);
  }
  // A command of this tile is out and unanswered: the whole row waits with it, long enough to be worth showing.
  if (now && t.loading(now)) for (unsigned i = 0; i < n; ++i) out[i].disabled = true;
  return n;
}
inline std::string neighbour_option(const Tile &t, int direction) {
  const auto &options = t.extra().options;
  if (options.empty()) return {};
  int current = 0, count = (int) options.size();
  for (int i = 0; i < count; ++i) if (options[i] == t.state) current = i;
  return options[(current + direction + count) % count];
}
inline const char *run_label(const std::string &domain) {
  if (domain == "scene") return screen_text::tr(screen_text::txt::ha_button_activate);
  if (domain == "script") return screen_text::tr(screen_text::txt::ha_button_run);
  return screen_text::tr(screen_text::txt::ha_button_press);
}
// The Home Assistant action behind a key. STEP_* are handled locally (debounced) and return nothing.
inline Action key_action(const Tile &t, int command, const std::string &arg = "") {
  auto d = t.domain();
  switch (command) {
    case COVER_OPEN: return {"cover.open_cover", "", ""};
    case COVER_STOP: return {"cover.stop_cover", "", ""};
    case COVER_CLOSE: return {"cover.close_cover", "", ""};
    case COVER_OPEN_TILT: return {"cover.open_cover_tilt", "", ""};
    case COVER_STOP_TILT: return {"cover.stop_cover_tilt", "", ""};
    case COVER_CLOSE_TILT: return {"cover.close_cover_tilt", "", ""};
    case VACUUM_START: return {(t.supported & feature::VACUUM_START) ? "vacuum.start" : "vacuum.turn_on", "", ""};
    case VACUUM_PAUSE: return {"vacuum.pause", "", ""};
    case VACUUM_STOP: return {(t.supported & feature::VACUUM_STOP) ? "vacuum.stop" : "vacuum.turn_off", "", ""};
    case VACUUM_DOCK: return {"vacuum.return_to_base", "", ""};
    case MEDIA_PREVIOUS: return {"media_player.media_previous_track", "", ""};
    case MEDIA_PLAY_PAUSE:
      if((t.supported&(feature::MEDIA_PLAY|feature::MEDIA_PAUSE))==(feature::MEDIA_PLAY|feature::MEDIA_PAUSE))return {"media_player.media_play_pause", "", ""};
      if(t.state=="playing"&&(t.supported&feature::MEDIA_PAUSE))return {"media_player.media_pause", "", ""};
      if(t.state!="playing"&&(t.supported&feature::MEDIA_PLAY))return {"media_player.media_play", "", ""};
      return {};
    case MEDIA_NEXT: return {"media_player.media_next_track", "", ""};
    case MEDIA_MUTE: return {"media_player.volume_mute", "is_volume_muted", t.muted ? "false" : "true"};
    case TIMER_START: return {"timer.start", "", ""};
    case TIMER_PAUSE: return {"timer.pause", "", ""};
    case TIMER_CANCEL: return {"timer.cancel", "", ""};
    case HVAC_MODE: return arg.empty() ? Action{} : Action{"climate.set_hvac_mode", "hvac_mode", arg};
    case SELECT_PREVIOUS: case SELECT_NEXT: {
      std::string option = neighbour_option(t, command == SELECT_NEXT ? 1 : -1);
      return option.empty() ? Action{} : Action{d + ".select_option", "option", option};
    }
    case RUN:
      if (d == "scene" || d == "script") return {d + ".turn_on", "", ""};
      if (d == "button" || d == "input_button") return {d + ".press", "", ""};
      return {};
    case TOGGLE:
      if (d == "light" || d == "switch" || d == "input_boolean" || d == "fan") return {d + (t.state == "on" ? ".turn_off" : ".turn_on"), "", ""};
      return {};
    default: return {};
  }
}
// A tap on a key: the action follows the stand the tile had, and a toggle then shows its new stand at once. The order
// matters, because Tile::optimistic writes the new stand into `state`: asked afterwards, key_action sent an off light
// light.turn_off, so the knob flipped on and back while the light stayed off (firmware 0.2.59 to 0.2.71).
inline Action press_key(Tile &t, int command, const std::string &arg = "") {
  Action a = key_action(t, command, arg);
  if (command == TOGGLE && a.valid()) t.optimistic(t.state != "on");
  return a;
}
// ---- Vacuum card rows (firmware 0.2.39+) ----
// The value a row shows as chosen: the one just tapped while Home Assistant has not answered yet.
inline const std::string &shown_value(const Tile &t, const runtime_tiles::Choice &c, uint32_t now) {
  return !c.sent.empty() && t.waiting(now) ? c.sent : c.current;
}
// Role of the cleaning mode in use: 'v' vacuum only, 'm' mop only, 'b' both, 'a' automatic; 'b' when
// the robot has no mode select or reports a mode the manager did not know.
inline char vacuum_role(const Tile &t, uint32_t now) {
  const auto *mode = t.choice('m');
  if (!mode) return 'b';
  const std::string &value = shown_value(t, *mode, now);
  for (size_t i = 0; i < mode->values.size() && i < mode->roles.size(); ++i)
    if (mode->values[i] == value) return mode->roles[i];
  return 'b';
}
// Rows under the mode: suction unless the robot only mops, water (when the robot has a water select)
// unless it only vacuums; an automatic mode leaves both to the robot or its app.
struct VacuumRows { bool suction = false, water = false; };
inline VacuumRows vacuum_rows(const Tile &t, uint32_t now) {
  char role = vacuum_role(t, now);
  VacuumRows rows;
  rows.suction = role != 'm' && role != 'a' && t.choice('s');
  rows.water = role != 'v' && role != 'a' && t.choice('w');
  return rows;
}
// Labels for a manager that sends no suction row (app before 0.2.46): the vacuum's own speed names.
inline std::string speed_label(const std::string &speed) {
  if (speed == "quiet") return screen_text::tr(screen_text::txt::vacuum_speed_quiet);
  if (speed == "balanced") return screen_text::tr(screen_text::txt::vacuum_speed_balanced);
  if (speed == "turbo") return screen_text::tr(screen_text::txt::vacuum_speed_turbo);
  if (speed == "max") return screen_text::tr(screen_text::txt::vacuum_speed_max);
  return speed;
}
// The suction row a vacuum card shows: the manager's (filtered, labelled) speeds, else the first four
// of the vacuum's own list. Its value is always the vacuum's fan_speed.
inline void settle_suction(runtime_tiles::Extra &x) {
  auto *row = x.choice('s');
  if (!row && !x.fan_speeds.empty()) {
    runtime_tiles::Choice legacy; legacy.kind = 's';
    for (const auto &speed : x.fan_speeds) { legacy.values.push_back(speed); legacy.labels.push_back(speed_label(speed)); }
    x.choices.push_back(std::move(legacy));
    row = &x.choices.back();
  }
  if (row) row->current = x.fan_speed;
}
// Whether a light runs an effect worth naming on its tile (firmware 0.2.70+): WLED's "Solid" is its plain colour, a Hue's
// "off" and Home Assistant's "None" mean no effect.
inline bool effect_running(const std::string &effect) {
  std::string lower;
  for (char c : effect) lower += static_cast<char>(c >= 'A' && c <= 'Z' ? c - 'A' + 'a' : c);
  while (!lower.empty() && lower.back() == ' ') lower.pop_back();
  return !lower.empty() && lower != "solid" && lower != "off" && lower != "none" && lower != "unknown" && lower != "unavailable";
}
// The service call behind a chip: a select option on the device, or the vacuum's own fan speed.
inline Action choice_action(const Tile &t, char kind, const std::string &value) {
  if (kind == 's') return {"vacuum.set_fan_speed", "fan_speed", value};
  const auto *row = t.choice(kind);
  if (!row || row->entity.empty()) return {};
  return {"select.select_option", "option", value};
}

// The debounced -/+ edit lands as one service call.
inline Action edit_action(const Tile &t, float value) {
  if (!std::isfinite(value)) return {};
  char b[24]; snprintf(b, sizeof(b), "%.2f", value);
  std::string text = b;
  while (text.size() > 1 && text.back() == '0') text.pop_back();
  if (text.back() == '.') text.pop_back();
  auto d = t.domain();
  if (d == "climate") return {"climate.set_temperature", "temperature", text};
  if (d == "number" || d == "input_number") return {d + ".set_value", "value", text};
  return {};
}

// ---- What a finger on a tile does ----
// The tile's own `tap` choice comes first. `toggle` sends <domain>.toggle on every domain (firmware 0.2.58+): the app
// only offers it where Home Assistant lists that action for the entity, such as a cover, which stops while it moves.
// Otherwise the domain decides, as before: holding or `detail` opens a card, a short tap switches, runs or presses.
// CARD is the runtime detail card (show_detail), OVERLAY the board's own colour card; `busy` marks the
// tile busy for a moment while the card opens.
// CUSTOM (firmware 0.2.58+) is an action of the tile's own choosing from Home Assistant's list, with its data.
enum class TapRoute : uint8_t { NONE, ACTION, CARD, OVERLAY, CUSTOM };
struct Tap { TapRoute route = TapRoute::NONE; std::string service; bool busy = false; };
inline bool runtime_card_domain(const std::string &d) {
  return d == "sensor" || d == "binary_sensor" || d == "weather" || d == "number" || d == "input_number" || d == "select" ||
         d == "input_select" || d == "media_player" || d == "vacuum" || d == "cover" || d == "sun" || d == "person" ||
         d == "timer" || d == "climate" || d == "alarm_control_panel";
}
// Whether a light offers a colour or a colour temperature, and so opens the colour card instead of the card
// with the brightness slider. The modes come from Home Assistant as one string (`supported_color_modes`) and
// are looked for in it, the way the YAML script did before this lived here: "rgb" also matches "rgbw" and
// "rgbww", which is what we want, since each of them is a colour.
inline bool light_colour(const Tile &t) {
  if (t.domain() != "light") return false;
  for (const char *mode : {"hs", "rgb", "xy", "color_temp"})
    if (t.modes.find(mode) != std::string::npos) return true;
  return false;
}

// Whether a light can be dimmed at all. Home Assistant lists "onoff" and nothing else for a light that is only
// a switch (a relay behind a ceiling lamp), and its own dialog then shows no brightness control - so neither
// does ours: the card draws the light's icon instead of a slider that sends a brightness the light ignores.
// A light that says nothing about its modes is taken for a dimmer, which is what every screen did before.
inline bool light_dims(const Tile &t) {
  if (t.domain() != "light") return true;   // a fan's speed is its percentage, and it always has one
  if (t.modes.empty()) return true;
  return t.modes.find("brightness") != std::string::npos || light_colour(t) ||
         t.modes.find("white") != std::string::npos;
}

// A saved tall-tile selection can outlive the entity's capabilities. Keep the
// selection in configuration, but do not draw or dispatch an unsupported panel.
inline bool panel_available(const Tile &t) {
  if(!t.available())return false;
  const auto mode=panel_kind(t),domain=t.domain();
  if(is_key_row(mode)){std::array<Key,3> keys;return keys_for(t,keys)>0;}
  if(mode=="brightness")return domain=="light"&&light_dims(t);
  if(mode=="speed")return domain=="fan"&&(t.supported&1);
  if(mode=="position")return domain=="cover"&&(t.supported&feature::COVER_POSITION);
  if(mode=="volume")return domain=="media_player"&&(t.supported&(feature::MEDIA_VOLUME_SET|feature::MEDIA_VOLUME_MUTE));
  if(mode=="setpoint")return domain=="climate"&&(t.supported&1); // single target, not a heat/cool range
  if(mode=="slider"||mode=="stepper")return domain=="number"||domain=="input_number";
  if(mode=="toggle")return domain=="light"||domain=="switch"||domain=="input_boolean"||domain=="fan";
  if(mode=="run")return domain=="scene"||domain=="script"||domain=="button"||domain=="input_button";
  return false;
}

inline Tap tap_route(const Tile &t, bool hold) {
  const std::string d = t.domain();
  if (t.tap == "none") return {};
  // A tile whose action didn't arrive (an app before 0.2.67) taps automatically, as older firmware does.
  if (!hold && t.tap == "action" && !t.extra().action.empty()) return {TapRoute::CUSTOM, t.extra().action};
  if (!hold && t.tap == "toggle") return {TapRoute::ACTION, d + ".toggle"};
  bool open = hold || t.tap == "detail" || d == "vacuum" || d == "cover";
  // A short tap runs or pauses the timer; holding opens the card with a cancel button.
  if (d == "timer" && !open) return {TapRoute::ACTION, t.state == "active" ? "timer.pause" : "timer.start"};
  if (runtime_card_domain(d)) return {TapRoute::CARD, "", true};
  // A light with colour keeps the board's own colour card (OVERLAY); a light that only dims and a fan open the
  // computed card with the standing slider, which every other domain has opened since firmware 0.2.80.
  if (open) return light_colour(t) ? Tap{TapRoute::OVERLAY, "", true}
                                   : d == "light" || d == "fan" ? Tap{TapRoute::CARD, "", true} : Tap{TapRoute::CARD, "", false};
  if (d == "light" || d == "switch" || d == "input_boolean" || d == "fan") return {TapRoute::ACTION, d + ".toggle"};
  if (d == "scene" || d == "script") return {TapRoute::ACTION, d + ".turn_on"};
  if (d == "button" || d == "input_button") return {TapRoute::ACTION, d + ".press"};
  return {};
}
}  // namespace tile_controls
