#pragma once
#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#include "screen_text.h"
#include "ui_scale.h"
#include <cmath>
#include <cstdint>
#include <cstdlib>
// The tiles of a screen live on the heap, as many as the layout has (firmware 0.2.62+): a screen with twelve
// tiles pays for twelve. On a board with PSRAM ESPHome's allocator puts that list, the fixed part of every
// tile, in PSRAM; without PSRAM it takes the internal heap. What a tile holds beyond it, its strings and its
// Extra, comes from plain malloc and new, which ESPHome's psram setup (CONFIG_SPIRAM_USE_CAPS_ALLOC) keeps in
// the internal heap on both boards. The host tests and the host render build have neither, so they take the
// standard allocator.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif
#ifdef USE_ESP32
#include "esp_heap_caps.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#endif

namespace runtime_tiles {
// A board states the cells of a page for each way its glass can hang: GRID_COLS x GRID_ROWS when it lies down,
// GRID_COLS_PORTRAIT x GRID_ROWS_PORTRAIT when it stands up (firmware 0.2.92+). Both arrive as build flags. The
// screen picks one at boot from the canvas LVGL hands it (grid_select) and everything below counts with that
// one, so the same firmware serves a board either way round and nothing here knows which board it is.
#ifndef GRID_COLS
#define GRID_COLS 2
#endif
#ifndef GRID_ROWS
#define GRID_ROWS 3
#endif
// A square board, or one whose second grid nobody worked out yet, keeps the same cells both ways.
#ifndef GRID_COLS_PORTRAIT
#define GRID_COLS_PORTRAIT GRID_COLS
#endif
#ifndef GRID_ROWS_PORTRAIT
#define GRID_ROWS_PORTRAIT GRID_ROWS
#endif
// One bit per tile for the cards the next render draws again (firmware 0.2.65+). Firmware 0.2.62-0.2.64 kept 32 bits
// while a screen holds 48 tiles, so a state for tile 33 to 48 redrew the whole page. 0 beyond them: draw everything.
// This is the ceiling on a screen whatever its grid, so it sizes the arrays that hold one entry per tile.
constexpr size_t TILES_MAX = 64;
// Explicit grid positions (0.2.26+) address at most eight pages.
constexpr size_t PAGES_MAX = 8;
// The bigger of the two grids: what the cards, the page's own arrays and the grid descriptors are sized for. A
// CYD carries six cards and shows four of them standing up; nothing is allocated twice.
constexpr size_t CELLS_MAX = (GRID_COLS * GRID_ROWS) > (GRID_COLS_PORTRAIT * GRID_ROWS_PORTRAIT)
                                 ? (GRID_COLS * GRID_ROWS)
                                 : (GRID_COLS_PORTRAIT * GRID_ROWS_PORTRAIT);
constexpr size_t dim_max(size_t a, size_t b, size_t c, size_t d) {
  size_t most = a;
  if (b > most) most = b;
  if (c > most) most = c;
  if (d > most) most = d;
  return most;
}
constexpr size_t DIM_MAX = dim_max(GRID_COLS, GRID_ROWS, GRID_COLS_PORTRAIT, GRID_ROWS_PORTRAIT);
static_assert(GRID_COLS >= 1 && GRID_ROWS >= 1 && GRID_COLS_PORTRAIT >= 1 && GRID_ROWS_PORTRAIT >= 1, "a grid needs a cell");
static_assert(CELLS_MAX <= TILES_MAX, "a page holds at most as many cells as a screen holds tiles");

// The cells of one page, and everything that follows from them. ESP Screens counts with the same object
// (screen_manager/app/core.py, class Grid), method for method, so a slot number means the same thing on both
// sides of the wire whichever way a screen hangs.
struct Grid {
  size_t columns = GRID_COLS;
  size_t rows = GRID_ROWS;
  constexpr size_t slots() const { return columns * rows; }
  constexpr size_t pages() const { return TILES_MAX / slots() < PAGES_MAX ? TILES_MAX / slots() : PAGES_MAX; }
  constexpr size_t max_slots() const { return pages() * slots(); }
  constexpr size_t max_tiles() const { return max_slots(); }
  // A wide card takes the cell beside it, or the only cell there is on a single-column screen.
  constexpr size_t wide_span() const { return columns > 1 ? 2 : 1; }
  // Whether a wide card started here would still stand in the row it starts in.
  constexpr bool wide_fits(size_t slot) const { return columns == 1 || slot % columns + 2 <= columns; }
  constexpr size_t page_of(size_t slot) const { return slot / slots(); }
  constexpr size_t column_of(size_t slot) const { return slot % columns; }
  constexpr size_t row_of(size_t slot) const { return slot % slots() / columns; }
};
// The grid this screen runs on. It stands at the board's landscape grid until grid_select reads the canvas, so a
// host test or a board that never turns needs no boot step.
inline Grid grid{GRID_COLS, GRID_ROWS};
// Pick the grid from the canvas LVGL draws on. A square canvas counts as lying down, as LVGL's own orientation
// does, so a square board answers the same grid either way.
inline void grid_select(int canvas_width, int canvas_height) {
#ifndef ESP_SCREEN_HOST
  const bool upright = canvas_height > canvas_width;
  grid = upright ? Grid{GRID_COLS_PORTRAIT, GRID_ROWS_PORTRAIT} : Grid{GRID_COLS, GRID_ROWS};
#endif
}
constexpr uint64_t tile_bit(size_t index) { return index < 64 ? uint64_t{1} << index : 0; }
// A navigation tile (screen.page_<n>, firmware 0.2.62+).
inline bool page_entity(const std::string &entity) { return entity.size() == 13 && entity.compare(0, 12, "screen.page_") == 0; }
inline bool valid_entity(const std::string &entity) {
  if (entity.size() > 120) return false;
  auto dot = entity.find('.');
  if (dot == std::string::npos || dot == 0 || dot + 1 == entity.size()) return false;
  for (size_t i = 0; i < entity.size(); ++i)
    if (i != dot && !(entity[i] >= 'a' && entity[i] <= 'z') &&
        !(entity[i] >= '0' && entity[i] <= '9') && entity[i] != '_') return false;
  std::string domain = entity.substr(0, dot);
  // screen.* are built-in cards without a Home Assistant entity behind them; screen.page_<n> (firmware 0.2.62+)
  // only goes to page n. Several pages may each carry the same one (firmware 0.2.65+, Model::set_layout).
  if (domain == "screen") {
    if (entity == "screen.clock" || entity == "screen.settings") return true;
    return page_entity(entity) && entity[12] >= '1' && entity[12] <= static_cast<char>('0' + grid.pages());
  }
  for (const auto *allowed : {"light", "switch", "input_boolean", "scene", "script", "climate", "vacuum", "fan", "cover", "sensor", "binary_sensor", "input_select", "select", "number", "input_number", "weather", "media_player", "button", "input_button", "sun", "timer", "person", "camera", "image"})
    if (domain == allowed) return true;
  return false;
}
// A comma-separated list of entities (a page's live camera tiles, firmware 0.2.77+); an empty item stands for a tile
// without a picture.
inline bool valid_entity_list(const std::string &list) {
  if (list.empty() || list.size() > 400) return false;
  for (size_t start = 0;; ) {
    const size_t comma = list.find(',', start);
    const std::string item = list.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
    if (!item.empty() && !valid_entity(item)) return false;
    if (comma == std::string::npos) return true;
    start = comma + 1;
  }
}
// An action as Home Assistant names it (domain.action: lowercase letters, digits, underscores), of any integration.
inline bool valid_action(const std::string &action) {
  if (action.size() > 64) return false;
  auto dot = action.find('.');
  if (dot == std::string::npos || dot == 0 || dot + 1 == action.size() || action.find('.', dot + 1) != std::string::npos) return false;
  for (size_t i = 0; i < action.size(); ++i)
    if (i != dot && !(action[i] >= 'a' && action[i] <= 'z') && !(action[i] >= '0' && action[i] <= '9') && action[i] != '_') return false;
  return true;
}
// A tile keeps a fingerprint (FNV-1a) of its last state message instead of a copy of it. It is also an
// ArduinoJson writer: the firmware hashes the attributes while serializing them, without a string.
struct Fingerprint {
  uint32_t value = 2166136261u;
  size_t write(uint8_t c) { value = (value ^ c) * 16777619u; return 1; }
  size_t write(const uint8_t *data, size_t size) { for (size_t i = 0; i < size; ++i) write(data[i]); return size; }
  void add(const std::string &text) { write(reinterpret_cast<const uint8_t *>(text.data()), text.size()); }
};
inline uint32_t state_revision(const std::string &state, const std::string &attributes) {
  Fingerprint f;
  f.add(state);
  f.write('\n');
  f.add(attributes);
  return f.value;
}
struct Forecast { std::string day, condition; float high = NAN, low = NAN, rain = NAN, mm = NAN; };
struct Hour { std::string time, condition; float temp = NAN, rain = NAN, mm = NAN; };
// One row of choices on a vacuum card (firmware 0.2.39+), found by the manager on the robot's device:
// kind 'm' a cleaning mode select (Roborock: vacuum, mop or both), 'w' a water or mop intensity
// select, 's' the suction speeds of the vacuum itself. `values` go to Home Assistant, `labels` are
// shown; a cleaning mode carries one role letter per value (v vacuum only, m mop only, b both,
// a automatic: the robot or the app decides suction and water). `sent` is the value just tapped.
struct Choice {
  char kind = 0;
  std::string entity, current, roles, sent;
  std::vector<std::string> values, labels;
};
// What only some tiles carry: climate modes, a select's options, weather, sun and timer times, a media
// title, the vacuum rows. A light or a sensor has none of it, so a tile holds this block only while its
// state needs one: twenty tiles with these fields inline took 24 KB of the CYD's RAM, mostly empty.
// A light's effects page (firmware 0.2.70+): a select entity of the light's device with what it is set to and how many
// options it has, and a number entity with its range; the names and icons are Home Assistant's, through the add-on.
struct OptionRow { std::string entity, name, current; uint16_t count = 0; uint32_t icon = 0; };
struct NumberRow { std::string entity, name; float value = NAN, low = 0, high = 100, step = 1; uint32_t icon = 0; };
struct Extra {
  // The effect a light runs (its `effect` attribute), and the rows of its effects page.
  std::string effect;
  std::vector<OptionRow> option_rows;
  std::vector<NumberRow> number_rows;
  // Climate: the modes as JSON lists, the current fan and swing mode, and what it is doing now.
  std::string hvac_modes, fan_modes, swing_modes, fan_mode, swing_mode, hvac_action;
  // A select's options, at most eight.
  std::vector<std::string> options;
  // Weather: up to five days and eight hours.
  std::vector<Forecast> forecast;
  std::vector<Hour> hours;
  float wind = NAN, feels = NAN;
  std::string wind_unit;
  std::string sunrise, sunset, duration, remaining;
  uint32_t timer_end = 0;
  std::string media_title;
  // The media card (firmware 0.2.64+, app 0.2.77+): the artist and the album, the track's length and where it was when
  // Home Assistant last said so (seconds, and that moment as an epoch), and a short mark of the cover picture, empty
  // when the player shows none. The mark changes with the picture: the card fetches a new cover when it does.
  std::string media_artist, media_album, media_picture;
  uint32_t media_duration = 0, media_position = 0, media_position_at = 0;
  // Vacuum: its own speeds (at most four) and speed, the mode, water and suction rows (see Choice), and
  // from sensors of its device the room it is in and whether it charges.
  std::vector<std::string> fan_speeds;
  std::string fan_speed;
  std::vector<Choice> choices;
  std::string room;
  bool charging = false;
  // Cover (firmware 0.2.50+): the tilt of its slats, 0 closed to 100 open.
  float tilt = NAN;
  // A tap that performs a Home Assistant action of the tile's own choosing (firmware 0.2.58+): the action, its data as
  // text, and the values Home Assistant renders itself (numbers, lists, true or false) as templates.
  std::string action;
  std::vector<std::pair<std::string, std::string>> action_data, action_templates;
  // Home Assistant's word for the state where the screen has none of its own (app 0.2.67+): "Open", "Playing", "Rinsing".
  std::string state_word;
  // A value of this entity that the second line was set to (firmware 0.2.90+, "attr:<name>"): the app reads the
  // attribute from Home Assistant, writes it the way Home Assistant writes it and sends the finished line. A
  // moment in time comes as seconds instead, so the screen says it in its own words and its own clock, the way
  // it already says when a script last ran (last_run_text) - one wording, not a second one in Python.
  std::string subtitle;
  uint32_t subtitle_at = 0;
  Choice *choice(char kind) { for (auto &c : choices) if (c.kind == kind) return &c; return nullptr; }
  bool empty() const {
    return hvac_modes.empty() && fan_modes.empty() && swing_modes.empty() && fan_mode.empty() && swing_mode.empty() &&
           hvac_action.empty() && options.empty() && forecast.empty() && hours.empty() && std::isnan(wind) &&
           std::isnan(feels) && wind_unit.empty() && sunrise.empty() && sunset.empty() && duration.empty() &&
           remaining.empty() && !timer_end && media_title.empty() && media_artist.empty() && media_album.empty() &&
           media_picture.empty() && !media_duration && !media_position && !media_position_at && fan_speeds.empty() && fan_speed.empty() &&
           choices.empty() && room.empty() && !charging && std::isnan(tilt) && action.empty() && action_data.empty() &&
           action_templates.empty() && state_word.empty() && subtitle.empty() && !subtitle_at && effect.empty() &&
           option_rows.empty() && number_rows.empty();
  }
};
// The numbers of a clock text ("0:05:00", "07:45"), at most `max` of them, each after optional white space, up to the
// first character that is not a digit or a colon after one: what sscanf's "%u:%u:%u" reads. Read by hand (firmware
// 0.2.75+): sscanf brought newlib's whole scanf into the firmware, 9.5 KB on the CYD.
inline int clock_parts(const std::string &text, unsigned *out, int max) {
  int n = 0;
  const char *p = text.c_str();
  while (n < max) {
    while (*p == ' ' || (*p >= '\t' && *p <= '\r')) ++p;
    if (*p < '0' || *p > '9') break;
    unsigned value = 0;
    while (*p >= '0' && *p <= '9') value = value * 10 + unsigned(*p++ - '0');
    out[n++] = value;
    if (*p != ':') break;
    ++p;
  }
  return n;
}
// A timer's duration or remaining time as Home Assistant writes it ("0:05:00", or "5:00") in seconds; 0 when unusable.
inline uint32_t duration_seconds(const std::string &text) {
  unsigned v[3] = {0, 0, 0};
  const int n = clock_parts(text, v, 3);
  if (n == 3) return v[0] * 3600 + v[1] * 60 + v[2];
  if (n == 2) return v[0] * 60 + v[1];
  return 0;
}
// Seconds a running timer has left, from Home Assistant's end time and the screen's clock. Both are whole seconds and
// the clock runs up to a second behind Home Assistant's (it syncs in whole seconds), so the difference can be one more
// than the timer holds: never more than its duration (firmware 0.2.75+; a 3 s timer started early in a second read 0:04).
inline uint32_t timer_left(uint32_t end, uint32_t now, const std::string &duration) {
  const uint32_t left = end > now && now ? end - now : 0;
  const uint32_t full = duration_seconds(duration);
  return full && left > full ? full : left;
}
// A sun time from the add-on ("06:45") in minutes after midnight; -1 when unusable.
inline int minutes_of(const std::string &clock) {
  unsigned v[2] = {0, 0};
  return clock_parts(clock, v, 2) == 2 && v[0] < 24 && v[1] < 60 ? int(v[0] * 60 + v[1]) : -1;
}
// The Extra of a tile on the heap, copied along with the tile like an ordinary member.
struct ExtraBox {
  std::unique_ptr<Extra> ptr;
  ExtraBox() = default;
  ExtraBox(const ExtraBox &other) : ptr(other.ptr ? new Extra(*other.ptr) : nullptr) {}
  ExtraBox &operator=(const ExtraBox &other) { if (this != &other) ptr.reset(other.ptr ? new Extra(*other.ptr) : nullptr); return *this; }
  ExtraBox(ExtraBox &&) noexcept = default;
  ExtraBox &operator=(ExtraBox &&) noexcept = default;
};
struct Tile {
  std::string entity, name, state, unit, modes;
  float brightness = NAN, percentage = NAN, position = NAN;
  float current = NAN, target = NAN, humidity = NAN, minimum = 7, maximum = 35, step = 0.5f;
  int hue = 0, kelvin = 3000, min_kelvin = 0, max_kelvin = 0;
  bool received = false;
  bool has_hs_color = false;
  int saturation = 0;
  std::string tap = "auto", display = "standard", inline_control = "none";
  // What the second line says (firmware 0.2.90+), as the option was stored: "auto" is the line the screen works
  // out itself, "none" leaves it empty, "text:<words>" says those words, and "attr:<name>" says a value of this
  // entity that Home Assistant itself names. Only the last one needs an answer from the app: the other three
  // are decided here, so they keep working while Home Assistant is away.
  std::string subtitle = "auto";
  // A camera tile's live picture (firmware 0.2.77+): "display": "live" puts a small picture of the camera in the
  // icon's place, loaded again every `refresh` seconds.
  uint16_t refresh = 15;
  bool live() const { const auto d = domain(); return display == "live" && (d == "camera" || d == "image"); }
  // A media player's album cover in the icon's place (firmware 0.2.78+): "display": "cover" on a single or double-width
  // tile, while the player has a picture; the tile over the whole page keeps the card's big cover.
  bool cover_tile() const { return display == "cover" && domain() == "media_player" && !full && !extra().media_picture.empty(); }
  // A tile that draws its picture out of the page's strip (runtime_tiles.h, live_*).
  bool pictured() const { return live() || cover_tile(); }
  // Double width takes a row; full (firmware 0.2.62+) takes the whole page, all six slots, and is also wide.
  bool wide = false, full = false;
  // Direct control set on a wide card (firmware 0.2.19+); empty keeps the plain card.
  std::string controls, device_class;
  bool muted = false;
  // A -/+ edit shows at once and is sent as one call after a short pause; the
  // value stays until Home Assistant reports it (or a timeout clears it).
  float edit_value = NAN; uint32_t edit_since = 0; bool edit_sent = false;
  // Knob position a toggle shows while its command is under way.
  bool optimistic_on = false;
  // A slider the finger let go stays where it was put while the light fades towards it (firmware 0.2.60+): the value
  // sent, in the attribute's own unit (brightness 0-255, a fan's percent, a volume 0-1), the value Home Assistant
  // reported meanwhile, and when the last of those came.
  float slider_sent = NAN, slider_real = NAN;
  uint32_t slider_sent_at = 0, slider_state_at = 0;
  // A tap that switched this tile is waiting; `optimistic_prev_on` is the stand to put back on a refusal.
  bool optimistic_tap = false, optimistic_prev_on = false;
  // A sensor's graph: 24 samples over `history_hours`, empty without one.
  unsigned history_hours = 24;
  std::vector<float> history;
  bool has_history = false;
  // When a scene, script or button last ran (unix time), pre-computed by the manager.
  uint32_t last_run = 0;
  float battery = NAN, volume = NAN;
  uint32_t supported = 0, background = 0;
  bool transparent = false;  // "Background: none": card fill and border hidden, contents unchanged.
  std::string icon;  // UTF-8 glyph of a chosen icon the icon fonts contain; empty keeps the domain icon.
  uint32_t revision = 0, pending_revision = 0;  // state_revision() fingerprints
  uint32_t pending_since = 0;
  // When Home Assistant answered "it worked" for a watched call (firmware 0.2.59+); 0 while no answer came.
  uint32_t answered_at = 0;
  bool pending = false, confirmed = false, local_feedback = false;
  // When Home Assistant refused the action a tap sent (firmware 0.2.58+); the tile says so for a moment.
  uint32_t refused_at = 0;
  ExtraBox extra_box;
  const Extra &extra() const { static const Extra none; return extra_box.ptr ? *extra_box.ptr : none; }
  Extra *extra_ptr() { return extra_box.ptr.get(); }
  Extra &edit_extra() { if (!extra_box.ptr) extra_box.ptr.reset(new Extra()); return *extra_box.ptr; }
  // A state message's extras replace the block: it stays allocated while the tile needs one and is freed
  // when a state brings none.
  void set_extra(Extra &&next) {
    if (next.empty()) extra_box.ptr.reset();
    else if (extra_box.ptr) *extra_box.ptr = std::move(next);
    else extra_box.ptr.reset(new Extra(std::move(next)));
  }
  Choice *choice(char kind) { return extra_box.ptr ? extra_box.ptr->choice(kind) : nullptr; }
  const Choice *choice(char kind) const { for (auto &c : extra().choices) if (c.kind == kind) return &c; return nullptr; }
  bool is_switch() const { return domain()=="switch" || domain()=="input_boolean"; }
  // Waiting for Home Assistant. It answered in 342-599 ms for every command measured on a real installation, so the
  // tile draws nothing for the first 400 ms: a command that lands looks instant (firmware 0.2.59+). After that the busy
  // sheet shows until the new state arrives, Home Assistant refuses, its "it worked" answer has stood for a moment
  // without a state following (a stop on a cover that already stands still), or the wait runs out.
  static constexpr uint32_t BUSY_GRACE = 400, BUSY_AFTER_ANSWER = 800, BUSY_CAP = 3000;
  bool waiting(uint32_t now) const {
    if (!pending || confirmed || local_feedback) return false;
    return now - pending_since < (answered_at ? answered_at - pending_since + BUSY_AFTER_ANSWER : BUSY_CAP);
  }
  // What the busy sheet, the card's "Command sent..." and its greyed keys follow: the wait, once it takes long enough
  // to be worth showing.
  bool loading(uint32_t now) const { return waiting(now) && now - pending_since >= BUSY_GRACE; }
  void begin(uint32_t now, bool local=false) { pending=true; pending_since=now; confirmed=false; local_feedback=local; pending_revision=revision; answered_at=0; }
  void observe(uint32_t next) { revision=next; optimistic_tap=false; if (pending && revision!=pending_revision) confirmed=true; }
  // Switching shows the new stand at once, as Home Assistant's own switch does (its ha-control-switch flips before the
  // command goes out). `undo_optimistic` puts the old stand back when Home Assistant refuses or never answers; a state
  // message always wins, because it clears the flag in `observe`.
  void optimistic(bool on) { optimistic_prev_on = state == "on"; optimistic_on = on; optimistic_tap = true; state = on ? "on" : "off"; }
  void undo_optimistic() { if (optimistic_tap) { state = optimistic_prev_on ? "on" : "off"; optimistic_tap = false; } }
  // The attribute a small slider sets: nothing for a cover, whose position slider follows the blind as it moves.
  float *slider_field() {
    auto d = domain();
    return d == "light" ? &brightness : d == "fan" ? &percentage : d == "media_player" ? &volume : nullptr;
  }
  // Holding a slider: from the send until Home Assistant reports a value within 3 % of it, reports the entity off or
  // unavailable, refuses, or reports once and then stays quiet for SLIDER_SETTLE (a fan that only knows 33/66/100
  // took the nearest step). A hold never outlives SLIDER_HOLD_CAP, and with no report at all it ends with the wait.
  static constexpr uint32_t SLIDER_HOLD_CAP = 8000, SLIDER_SETTLE = 1500;
  bool slider_holding(uint32_t now) const {
    if (!std::isfinite(slider_sent) || refused_at || now - slider_sent_at >= SLIDER_HOLD_CAP) return false;
    if (!slider_state_at) return waiting(now) || answered_at;
    return now - slider_state_at < SLIDER_SETTLE;
  }
  float slider_span() const { return domain() == "light" ? 255 : domain() == "media_player" ? 1 : 100; }
  // The finger let go: the field shows the value sent from now on.
  void hold_slider(uint32_t now, float value) {
    float *field = slider_field();
    if (!field) return;
    slider_sent = value; slider_real = *field; slider_sent_at = now; slider_state_at = 0; *field = value;
    // A slider on an off light or fan turns it on, so the tile lights up with it, as after a tap.
    if (domain() != "media_player" && state == "off") optimistic(true);
  }
  // A state came in with `field` already parsed: keep the sent value in front while the hold goes on.
  void slider_reported(uint32_t now) {
    float *field = slider_field();
    if (!field || !std::isfinite(slider_sent)) return;
    float real = *field;
    bool moved = !std::isfinite(slider_real) ? std::isfinite(real) : std::isfinite(real) && std::fabs(real - slider_real) > 0.5f * slider_span() / 100;
    slider_real = real;
    bool reached = std::isfinite(real) && std::fabs(real - slider_sent) <= 3 * slider_span() / 100;
    bool off = !slider_active();
    if (reached || off || refused_at) { slider_sent = NAN; return; }
    if (moved) slider_state_at = std::max<uint32_t>(1, now);
    if (!slider_holding(now)) { slider_sent = NAN; return; }
    *field = slider_sent;
  }
  // The hold ran out without a report that ended it: what Home Assistant last said shows again.
  void release_slider() {
    float *field = slider_field();
    if (field && std::isfinite(slider_sent)) *field = slider_real;
    slider_sent = NAN;
  }
  std::string domain() const { return entity.substr(0, entity.find('.')); }
  bool builtin() const { return domain() == "screen"; }
  // Two built-in cards, and only one of them is a clock that has to be redrawn every minute.
  bool is_clock() const { return entity == "screen.clock"; }
  bool is_settings() const { return entity == "screen.settings"; }
  // A navigation tile (screen.page_<n>, firmware 0.2.62+) and the page it goes to, counted from one.
  bool is_page() const { return page_entity(entity); }
  int page_target() const { return is_page() ? entity[12] - '0' : 0; }
  // Slots a tile takes: one, a row of two, or the six of a page.
  unsigned cells() const { return full ? grid.slots() : wide ? grid.wide_span() : 1u; }
  // A scene, button or input button that never ran is "unknown" in Home Assistant, which still lets you press it
  // (hui-button-entity-row disables only an unavailable one): its state is the moment it last ran (firmware 0.2.58+).
  bool available() const {
    if (builtin()) return true;
    if (!received || state.empty() || state == "unavailable") return false;
    auto d = domain();
    return state != "unknown" || d == "scene" || d == "button" || d == "input_button";
  }
  // Home Assistant's stateActive() (frontend src/common/entity/state_active.ts), the rule its cards colour by: an
  // entity it calls inactive is grey, such as an airco that is off, a closed blind, a docked robot, a player in
  // standby or a paused timer (firmware 0.2.71+). Only the cases of the domains a tile can show are here. A scene,
  // button or image states the moment it last ran (TIMESTAMP_STATE_DOMAINS), so only "unavailable" makes it
  // inactive. A built-in card has no state and is always active.
  bool active() const {
    if (builtin()) return true;
    if (!received || state.empty() || state == "unavailable") return false;
    auto d = domain();
    if (d == "scene" || d == "button" || d == "input_button" || d == "image") return true;
    if (state == "unknown" || state == "off") return false;
    if (d == "cover") return state != "closed";
    if (d == "person") return state != "not_home";
    if (d == "media_player") return state != "standby";
    if (d == "vacuum") return state != "idle" && state != "docked" && state != "paused";
    if (d == "timer") return state == "active";
    if (d == "camera") return state == "streaming" || state == "recording";
    return true;
  }
  // A slider shows the card's colour like Home Assistant's tile sliders: grey only while the entity is inactive
  // (active() above), such as an off light or fan and a media player that is off or in standby. A number with a
  // value is active there, and a closed cover's position slider keeps the cover's colour so it never looks
  // disabled (hui-cover-position-card-feature.ts).
  bool slider_active() const {
    if (!available()) return false;
    return domain() == "cover" || active();
  }
};
// Slot position of a tile within the fixed two-column, three-row pages.
struct Placement { uint8_t page = 0, slot = 0; };
#ifdef USE_ESP32
// ESPHome's allocator prefers PSRAM and falls back to the internal heap; this wrapper gives it the comparison
// std::vector wants. RAMAllocator answers nullptr when neither has room, and std::vector (no exceptions on the
// ESP32) would write the tiles through it: set_layout checks the room first (tile_room), and anything that still
// gets here stops with a log line instead of corrupting memory (firmware 0.2.65+).
template<class T> struct TileAllocator {
  using value_type = T;
  TileAllocator() = default;
  template<class U> TileAllocator(const TileAllocator<U> &) {}
  T *allocate(size_t n) {
    T *p = esphome::RAMAllocator<T>().allocate(n);
    if (!p) {
      ESP_LOGE("runtime", "No memory for %u tiles (%u bytes)", static_cast<unsigned>(n), static_cast<unsigned>(n * sizeof(T)));
      abort();
    }
    return p;
  }
  void deallocate(T *p, size_t n) { esphome::RAMAllocator<T>().deallocate(p, n); }
  bool operator==(const TileAllocator &) const { return true; }
  bool operator!=(const TileAllocator &) const { return false; }
};
using TileList = std::vector<Tile, TileAllocator<Tile>>;
#else
using TileList = std::vector<Tile>;
#endif
// The largest block the tile list could get: ESPHome's own answer on the ESP32 (PSRAM or the internal heap,
// whichever has the larger one). Nothing on the host, which has room; the tests put in a figure of their own.
#ifdef USE_ESP32
inline size_t largest_tile_block() { return esphome::RAMAllocator<Tile>().get_max_free_block_size(); }
inline size_t (*tile_room)() = largest_tile_block;
// What is left of the memory inside the chip. Strings, std::vector and everything else that goes through the
// ordinary allocator lands there, PSRAM or no PSRAM, and an allocation that fails is not an error the firmware
// can catch: it aborts, which a user sees as the screen restarting. Anything that grows with what Home
// Assistant sends asks this first. Boards differ by a lot: an 800x480 RGB panel keeps two bounce buffers of
// ten lines in there, where a board with an SPI panel keeps none.
inline size_t internal_free() { return heap_caps_get_free_size(MALLOC_CAP_INTERNAL); }
inline size_t (*heap_room)() = internal_free;
#else
inline size_t (*tile_room)() = nullptr;
inline size_t (*heap_room)() = nullptr;
#endif
// Wide tiles start in the left column and take the whole row; a right-column gap before them stays
// empty. A full tile starts a page of its own; the slots it leaves behind stay empty. Returns the page
// count (at least one).
inline unsigned pack(const TileList &tiles, size_t count, std::array<Placement, TILES_MAX> &out) {
  unsigned position = 0;
  for (size_t i = 0; i < count && i < grid.max_tiles(); ++i) {
    if (tiles[i].full && position % grid.slots()) position += grid.slots() - position % grid.slots();
    else if (tiles[i].wide && !grid.wide_fits(position)) ++position;
    out[i] = {static_cast<uint8_t>(position / grid.slots()), static_cast<uint8_t>(position % grid.slots())};
    position += tiles[i].cells();
  }
  unsigned pages = (position + grid.slots() - 1) / grid.slots();
  return pages ? pages : 1;
}
// Grid position per tile: the explicit slots when the manager sent them (a wide
// card always starts in the left column), else the in-order packing. Returns the
// page count (at least one); an empty page between two used ones stays a page.
struct Model;
inline unsigned place(const Model &m, std::array<Placement, TILES_MAX> &out);
struct Model {
  TileList tiles;
  // Absolute grid slot per tile when the manager sent `slots` (0.2.26+): gaps stay
  // empty and a tile keeps its place. Without them the tiles pack in order.
  std::array<uint8_t, TILES_MAX> slots{};
  bool explicit_slots = false;
  // Pages the manager wants shown even when the last ones are still empty (0.2.26+).
  uint8_t pages = 1;
  size_t count = 0;
  std::string title = screen_text::tr(screen_text::txt::status_choose_tiles);
  // A title of its own for a page (firmware 0.2.90+). The screen's title stands on every page, which is what
  // most screens want; a page that says something else says it here. Empty, or missing, means the screen's.
  // A vector and not an array of grid.pages(): a screen where nobody set one pays nothing for the possibility.
  std::vector<std::string> page_titles;
  // What the top bar says on `page`, counted from 0.
  const std::string &title_of(int page) const {
    if (page >= 0 && static_cast<size_t>(page) < page_titles.size() && !page_titles[page].empty()) return page_titles[page];
    return title;
  }
  bool configured = false;
  // Why the last set_layout refused a layout, for the manager's inbox status; empty when it took the layout or the
  // message itself was wrong (the status then says "invalid message", as before).
  std::string refusal;
  bool set_layout(const std::vector<std::string> &entities, const std::string &name, bool &changed) {
    bool moved = false;
    return set_layout(entities, name, changed, {}, moved);
  }
  // `changed`: the tiles differ, states restart. `moved`: same tiles on other
  // positions, the pages re-place without touching states or an open card.
  bool set_layout(const std::vector<std::string> &entities, const std::string &name, bool &changed,
                  const std::vector<uint8_t> &positions, bool &moved) {
    refusal.clear();
    if (entities.size() > grid.max_tiles() || name.size() > 96) return false;
    for (size_t i = 0; i < entities.size(); ++i) {
      if (!valid_entity(entities[i])) return false;
      // A Home Assistant entity appears once on a screen; a navigation tile may sit on several pages (firmware 0.2.65+).
      // Everything that reaches a tile goes by its index (Model::accepts), so each copy gets its own options.
      if (page_entity(entities[i])) continue;
      for (size_t j = 0; j < i; ++j) if (entities[i] == entities[j]) return false;
    }
    if (!positions.empty()) {
      if (positions.size() != entities.size()) return false;
      for (size_t i = 0; i < positions.size(); ++i) {
        if (positions[i] >= grid.max_slots()) return false;
        for (size_t j = 0; j < i; ++j) if (positions[i] == positions[j]) return false;
      }
    }
    changed = !configured || count != entities.size();
    for (size_t i = 0; i < entities.size() && i < tiles.size(); ++i) if (tiles[i].entity != entities[i]) changed = true;
    moved = !changed && (explicit_slots != !positions.empty());
    for (size_t i = 0; i < positions.size() && !changed; ++i) if (slots[i] != positions[i]) moved = true;
    // A longer list needs one block that holds every tile. Without it the layout is refused before anything changes, so
    // the screen keeps the tiles it shows and the manager hears why (firmware 0.2.65+).
    if (entities.size() > tiles.capacity() && tile_room && tile_room() < entities.size() * sizeof(Tile)) {
      refusal = "Error: no memory for " + std::to_string(entities.size()) + " tiles";
      return false;
    }
    // A title-only update must not interrupt an open control card.
    title = name.empty() ? std::string(screen_text::tr(screen_text::txt::status_home)) : name;
    if (changed) {
      // Freed before the new list is made, so the heap never holds both.
      tiles.clear();
      tiles.shrink_to_fit();
      tiles.resize(entities.size());
      count = entities.size();
      for (size_t i = 0; i < count; ++i) tiles[i].entity = entities[i];
    }
    explicit_slots = !positions.empty();
    slots.fill(0);
    for (size_t i = 0; i < positions.size(); ++i) slots[i] = positions[i];
    configured = true;
    return true;
  }
  bool ready() const {
    if (!configured) return false;
    for (size_t i = 0; i < count; ++i) if (!tiles[i].received) return false;
    return true;
  }
  bool accepts(size_t index, const std::string &entity) const {
    return configured && index < count && tiles[index].entity == entity;
  }
};
inline unsigned place(const Model &m, std::array<Placement, TILES_MAX> &out) {
  if (!m.explicit_slots) return pack(m.tiles, m.count, out);
  unsigned last = 0;
  for (size_t i = 0; i < m.count && i < grid.max_tiles(); ++i) {
    unsigned slot = m.slots[i];
    if (m.tiles[i].full) slot -= slot % grid.slots();
    else if (m.tiles[i].wide && !grid.wide_fits(slot)) --slot;
    out[i] = {static_cast<uint8_t>(slot / grid.slots()), static_cast<uint8_t>(slot % grid.slots())};
    last = std::max(last, slot + m.tiles[i].cells());
  }
  unsigned pages = (last + grid.slots() - 1) / grid.slots();
  return std::max({pages, 1u, std::min<unsigned>(m.pages, grid.pages())});
}
}  // namespace runtime_tiles
