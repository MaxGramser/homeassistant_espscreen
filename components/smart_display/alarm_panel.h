#pragma once
// The alarm panel (firmware 0.3.3+): an alarm_control_panel entity as a tile and a card, the way Home Assistant's own
// alarm dialog and alarm panel card do it. Pure logic only, free of LVGL, so tests/test_alarm_panel.cpp checks it on a
// PC: which modes a panel offers, when a mode asks for a code, what a tap sends, how the card tells an accepted code
// from a refused or ignored one, and how long the keypad locks after wrong codes. runtime_tiles.h draws it.
//
// What Home Assistant does, which this follows:
// - The modes are the ones supported_features names (ARM_HOME 1, ARM_AWAY 2, ARM_NIGHT 4, TRIGGER 8, ARM_CUSTOM_BYPASS
//   16, ARM_VACATION 32), plus disarm, which every panel has. Its order is the frontend's (ALARM_MODES in
//   src/data/alarm_control_panel.ts): home, away, night, vacation, custom bypass, disarmed. Trigger is left out, as
//   Home Assistant's dialogs leave it out: a panic button one mistap away is not a control for a wall.
// - A code is asked for (setProtectedAlarmControlPanelMode) when disarming and the panel has a code_format, or when
//   arming and it also has code_arm_required, unless the entity has a default code in its registry options: Home
//   Assistant then fills that in itself. The add-on says whether one is stored; the code never leaves Home Assistant.
// - A code goes to Home Assistant as the action's `code`, never stored and never logged by the screen. Only digits
//   are offered: a panel whose code_format is "text" (letters) cannot be armed or disarmed with a code from here.
// - Whether a code was wrong depends on the integration. Some refuse the action (the manual alarm's
//   ServiceValidationError reaches the screen as a refusal), some raise an error ESPHome does not pass back, and some
//   ignore it (Alarmo only logs a warning; Home Assistant's own documentation says a wrong code "fails silently"). So
//   an attempt with a code counts as failed when Home Assistant refuses it, or when the panel's state has not moved
//   towards the mode within ATTEMPT_WAIT_MS.
// - Home Assistant has no limit on attempts. The screen keeps its own: three wrong codes lock the keypad for 30 s,
//   and every wrong code after that doubles the time, up to 15 minutes. A code that works starts the count again.
#include <cstdint>
#include <string>
#include <vector>
#include "climate_card.h"
#include "theme.h"
#include "ui_scale.h"

namespace alarm_panel {

namespace feature {
constexpr uint32_t ARM_HOME = 1, ARM_AWAY = 2, ARM_NIGHT = 4, TRIGGER = 8, ARM_CUSTOM_BYPASS = 16, ARM_VACATION = 32;
}

// The glyphs of Home Assistant's alarm icons (icons.json of alarm_control_panel: the state icons and the service
// icons), all in the tile icon fonts (tile_icons.HA_DEFAULTS).
namespace glyph {
constexpr const char *SHIELD = "\U000F0498", *SHIELD_OFF = "\U000F099E", *SHIELD_HOME = "\U000F068A", *SHIELD_LOCK = "\U000F099D";
constexpr const char *SHIELD_MOON = "\U000F1828", *SHIELD_AIRPLANE = "\U000F06BB", *SECURITY = "\U000F0483";
constexpr const char *SHIELD_OUTLINE = "\U000F0499", *BELL_RING = "\U000F009E", *LOCK_CLOCK = "\U000F097F";
constexpr const char *CHECK = "\U000F012C", *CLOSE = "\U000F0156";
}

// One mode the card offers: the state it leads to, the action that sets it, and the feature bit it needs (0: disarm).
struct Mode { const char *state, *service, *icon; uint32_t feature; };
constexpr Mode MODES[] = {
    {"armed_home", "alarm_control_panel.alarm_arm_home", glyph::SHIELD_HOME, feature::ARM_HOME},
    {"armed_away", "alarm_control_panel.alarm_arm_away", glyph::SHIELD_LOCK, feature::ARM_AWAY},
    {"armed_night", "alarm_control_panel.alarm_arm_night", glyph::SHIELD_MOON, feature::ARM_NIGHT},
    {"armed_vacation", "alarm_control_panel.alarm_arm_vacation", glyph::SHIELD_AIRPLANE, feature::ARM_VACATION},
    {"armed_custom_bypass", "alarm_control_panel.alarm_arm_custom_bypass", glyph::SECURITY, feature::ARM_CUSTOM_BYPASS},
    {"disarmed", "alarm_control_panel.alarm_disarm", glyph::SHIELD_OFF, 0},
};
constexpr unsigned MODE_COUNT = sizeof(MODES) / sizeof(MODES[0]);
constexpr unsigned DISARM = MODE_COUNT - 1;

// The modes this panel offers, as indexes into MODES, in Home Assistant's order.
inline std::vector<unsigned> modes(uint32_t supported) {
  std::vector<unsigned> out;
  for (unsigned i = 0; i < MODE_COUNT; ++i)
    if (!MODES[i].feature || (supported & MODES[i].feature)) out.push_back(i);
  return out;
}
inline int mode_of(const std::string &state) {
  for (unsigned i = 0; i < MODE_COUNT; ++i) if (state == MODES[i].state) return (int) i;
  return -1;
}

inline bool armed(const std::string &state) { return state.compare(0, 6, "armed_") == 0; }
// The states in which Home Assistant's dialog shows only the pulsing icon and one Disarm key: the exit delay, the
// entry delay and the alarm going off.
inline bool urgent(const std::string &state) { return state == "arming" || state == "pending" || state == "triggered"; }
// What wakes a screen and opens its card by itself: someone came in (the entry delay) or the alarm goes off.
inline bool calls_for_attention(const std::string &state) { return state == "pending" || state == "triggered"; }

// Home Assistant's colour for the state (--state-alarm_control_panel-*-color): armed green, the three moments in
// between orange, going off red. Disarmed is inactive, grey (Tile::active).
constexpr uint32_t GREEN = theme::ha::GREEN, ORANGE = theme::ha::ORANGE, RED = theme::ha::RED;
inline uint32_t color(const std::string &state) {
  if (state == "triggered") return RED;
  if (state == "arming" || state == "pending" || state == "disarming") return ORANGE;
  return GREEN;
}
// Home Assistant's state icon (icons.json of alarm_control_panel); arming and disarming have none and take the shield.
inline const char *icon(const std::string &state) {
  if (state == "disarmed") return glyph::SHIELD_OFF;
  if (state == "armed_home") return glyph::SHIELD_HOME;
  if (state == "armed_away") return glyph::SHIELD_LOCK;
  if (state == "armed_night") return glyph::SHIELD_MOON;
  if (state == "armed_vacation") return glyph::SHIELD_AIRPLANE;
  if (state == "armed_custom_bypass") return glyph::SECURITY;
  if (state == "pending") return glyph::SHIELD_OUTLINE;
  if (state == "triggered") return glyph::BELL_RING;
  return glyph::SHIELD;
}

// What the panel says about codes: its code_format ("number", "text" or nothing), code_arm_required, and whether the
// add-on found a default code in its registry options.
struct Codes { std::string format; bool arm_required = true, saved = false; };
// Whether choosing this mode asks for a code first.
inline bool needs_code(const Codes &c, unsigned mode) {
  if (c.saved || c.format.empty()) return false;
  return mode == DISARM || c.arm_required;
}
// A code of letters cannot be typed here (only digits are offered).
inline bool code_typable(const Codes &c) { return c.format != "text"; }
constexpr unsigned CODE_MAX = 10;

// Whether a state is where a mode was heading: the mode itself, or the step Home Assistant takes on the way (the exit
// delay before an armed mode, disarming before disarmed).
inline bool reached(const std::string &state, unsigned mode) {
  if (mode >= MODE_COUNT) return false;
  if (state == MODES[mode].state) return true;
  return mode == DISARM ? state == "disarming" : state == "arming";
}

// One attempt with a code, until it is settled: accepted when the state moves towards the mode, failed when Home
// Assistant refuses it or the state has not moved after ATTEMPT_WAIT_MS.
constexpr uint32_t ATTEMPT_WAIT_MS = 10000;
enum class Outcome : uint8_t { WAITING, ACCEPTED, FAILED };
struct Attempt {
  bool active = false, with_code = false;
  unsigned mode = 0;
  uint32_t since = 0;
  void begin(unsigned m, bool code, uint32_t now) { active = true; with_code = code; mode = m; since = now ? now : 1; }
  // A state arrived, or time passed (`state` is the panel's state now).
  Outcome settle(const std::string &state, uint32_t now) {
    if (!active) return Outcome::WAITING;
    if (reached(state, mode)) { active = false; return Outcome::ACCEPTED; }
    if (now - since >= ATTEMPT_WAIT_MS) { active = false; return Outcome::FAILED; }
    return Outcome::WAITING;
  }
  Outcome refused() { if (!active) return Outcome::WAITING; active = false; return Outcome::FAILED; }
};

// The keypad's lock after wrong codes: FREE_TRIES wrong codes lock it for FIRST_LOCK_S, every wrong code after that
// doubles the time, up to MAX_LOCK_S. It counts on the screen's clock (millis), and what is left is saved, so a
// restart does not open it (remaining_s and resume).
constexpr unsigned FREE_TRIES = 3;
constexpr uint32_t FIRST_LOCK_S = 30, MAX_LOCK_S = 900;
inline uint32_t lock_seconds(unsigned failures) {
  if (failures < FREE_TRIES) return 0;
  uint32_t seconds = FIRST_LOCK_S;
  for (unsigned i = FREE_TRIES; i < failures && seconds < MAX_LOCK_S; ++i) seconds *= 2;
  return seconds < MAX_LOCK_S ? seconds : MAX_LOCK_S;
}
struct Lockout {
  uint32_t failures = 0, until = 0;  // until: millis() when the lock ends, while `closed`
  bool closed = false;
  bool locked(uint32_t now) const { return closed && (int32_t) (until - now) > 0; }
  uint32_t remaining_s(uint32_t now) const { return locked(now) ? (until - now + 999) / 1000 : 0; }
  // A wrong code; returns the seconds the keypad is now locked for (0: still open).
  uint32_t fail(uint32_t now) {
    ++failures;
    const uint32_t seconds = lock_seconds(failures);
    closed = seconds > 0;
    until = now + seconds * 1000;
    return seconds;
  }
  void success() { failures = 0; until = 0; closed = false; }
  // After a restart: the failures and the seconds that were left when it was saved.
  void resume(uint32_t saved_failures, uint32_t seconds_left, uint32_t now) {
    failures = saved_failures;
    closed = seconds_left > 0;
    until = now + (seconds_left > MAX_LOCK_S ? MAX_LOCK_S : seconds_left) * 1000;
  }
};

// Seconds left of an exit or entry delay, from the moment it ends (epoch) and the screen's clock; 0 when unknown.
// Alarmo reports the delay (its `delay` attribute); the add-on turns it into the moment it ends.
inline uint32_t seconds_left(uint32_t ends, uint32_t now) { return ends && now && ends > now ? ends - now : 0; }

// ---- Where the parts go ----
// One card for every board, as climate_card.h does it: the name and the state at the top (show_detail's bar), and
// under them the shield on a white card (the hero) with a key per mode, two to a row under it. Glass too short for
// that and wider than tall puts the keys beside the shield instead, as Home Assistant's dialog stands its modes
// beside the state. While the alarm counts down or goes off, the keys give way to one big Disarm key, as there.
// The keypad replaces the card: the dots and a line of words above twelve keys (1-9, clear, 0, OK, the keys of Home
// Assistant's code dialog), or beside them on wide glass. Every key keeps at least a finger's size (Metrics::touch).
using climate_card::Rect;
struct Metrics {
  bool large = true;
  int touch = 48;      // ui::touch_min()
  int text_h = 25;     // the words on the keys and the line under the dots
  int icon_h = 42;     // the icons on the mode keys
  int side = 20;       // overlay_card::pad()
  int key_h() const { return ui::px(large ? 64 : 42); }        // a mode key or a keypad key where there is room
  int big_h() const { return ui::px(large ? 72 : 46); }        // the Disarm key of an urgent card
  int gap() const { return ui::px(large ? 12 : 6); }           // between keys and blocks
  int radius() const { return ui::px(large ? 24 : 16); }
  int hero_min() const { return ui::px(large ? 120 : 64); }    // the shield's card at its smallest
  // The card at its largest is the Guition's (480 x 480 in the reference look): a bigger screen shows the same card,
  // as large to the eye, in the middle of its glass, instead of a white field that grows with the panel.
  int hero_max() const { return ui::px(large ? 150 : 96); }
  int card_max() const { return ui::px(large ? 440 : 300); }
  int dot() const { return ui::px(large ? 16 : 10); }
  int least_key() const { return touch > text_h + ui::px(8) ? touch : text_h + ui::px(8); }
};
struct CardLayout {
  Rect hero;
  Rect keys[MODE_COUNT];
  unsigned key_count = 0;
  bool beside = false;  // the keys stand beside the shield
  Rect disarm;          // the one key of an urgent card
};
// The card under the bar, between `top` and `bottom`, `width` wide (the room overlay_card gave it).
inline CardLayout card_layout(const Metrics &m, int width, int top, int bottom, unsigned modes, bool urgent_card) {
  CardLayout l;
  const int room = width - 2 * m.side, h = bottom - top, g = m.gap();
  if (room <= 0 || h <= 0) return l;
  // Stacked, the card keeps the Guition's width; beside each other, the shield and the keys share the glass's.
  const int stacked_w = room < m.card_max() ? room : m.card_max();
  int x = m.side + (room - stacked_w) / 2, w = stacked_w;
  if (urgent_card) {
    int kh = m.big_h() > m.least_key() ? m.big_h() : m.least_key();
    if (kh > h / 3) kh = h / 3 > m.least_key() ? h / 3 : m.least_key();
    const int kw = w < ui::mm(70) ? w : ui::mm(70);
    const int hero_h = h - kh - g < m.hero_max() ? h - kh - g : m.hero_max();
    const int y0 = top + (h - (hero_h + g + kh)) / 2;
    l.hero = {x, y0, w, hero_h};
    l.disarm = {x + (w - kw) / 2, y0 + hero_h + g, kw, kh};
    return l;
  }
  l.key_count = modes > MODE_COUNT ? MODE_COUNT : modes;
  const int n = (int) l.key_count;
  if (!n) { l.hero = {x, top, w, h}; return l; }
  int kh = m.key_h() > m.least_key() ? m.key_h() : m.least_key();
  // Under the shield while the keys keep their full height there and the shield its least, as on a square or a
  // standing screen; beside it on glass too short for that (a CYD lying down, a wide 4.3 inch).
  const int stack_rows = (n + (n == 1 ? 0 : 1)) / (n == 1 ? 1 : 2);
  l.beside = h - (stack_rows * kh + (stack_rows - 1) * g) - g < m.hero_min() && room * 10 >= h * 11;
  if (l.beside) {
    x = m.side; w = room;
    // One column of keys while they fit under each other, else two; the shield takes what is left.
    int columns = n * kh + (n - 1) * g <= h ? 1 : 2;
    const int rows = (n + columns - 1) / columns;
    if (rows * kh + (rows - 1) * g > h) kh = (h - (rows - 1) * g) / rows > m.least_key() ? (h - (rows - 1) * g) / rows : m.least_key();
    // Two columns of keys need the room for a word each; the shield keeps a third of the card.
    int keys_w = w * (columns == 1 ? 46 : 68) / 100;
    if (columns == 1 && keys_w > ui::mm(50)) keys_w = ui::mm(50);
    const int block = rows * kh + (rows - 1) * g, y0 = top + (h - block) / 2, kx = x + w - keys_w;
    const int hero_h = h < m.hero_max() ? h : (block > m.hero_max() ? block : m.hero_max());
    const int cw = columns == 1 ? keys_w : (keys_w - g) / 2;
    for (int i = 0; i < n; ++i) {
      const int row = i / columns, column = i % columns;
      // An odd last key in two columns takes the whole row.
      const bool alone = columns == 2 && i == n - 1 && n % 2 == 1;
      l.keys[i] = {kx + (alone ? 0 : column * (cw + g)), y0 + row * (kh + g), alone ? keys_w : cw, kh};
    }
    l.hero = {x, top + (h - hero_h) / 2, w - keys_w - g, hero_h};
    return l;
  }
  // Under the shield: two keys to a row (one when there is one), the shield above them.
  const int columns = n == 1 ? 1 : 2, rows = (n + columns - 1) / columns;
  int block = rows * kh + (rows - 1) * g;
  if (h - block - g < m.hero_min()) {
    const int fit = (h - m.hero_min() - g - (rows - 1) * g) / rows;
    kh = fit > m.least_key() ? fit : m.least_key();
    block = rows * kh + (rows - 1) * g;
  }
  // The shield takes what is left up to its largest, and the two stand together in the middle of the card.
  const int hero_h = h - block - g < m.hero_max() ? h - block - g : m.hero_max();
  const int hero_y = top + (h - (hero_h + g + block)) / 2;
  const int cw = (w - (columns - 1) * g) / columns, y0 = hero_y + hero_h + g;
  for (int i = 0; i < n; ++i) {
    const int row = i / columns, column = i % columns;
    const bool alone = columns == 2 && i == n - 1 && n % 2 == 1;
    l.keys[i] = {x + (alone ? 0 : column * (cw + g)), y0 + row * (kh + g), alone ? w : cw, kh};
  }
  l.hero = {x, hero_y, w, hero_h};
  return l;
}

// The space between two dots.
inline int dot_gap(int dot) { return dot * 3 / 5; }
struct KeypadLayout {
  Rect info;          // where the dots and the line stand
  Rect dots, line;
  int dot = 16;       // a dot's diameter, smaller when many digits have to fit
  Rect keys[12];      // 1-9, clear, 0, OK
  bool beside = false;
};
// The keypad under the bar. `digits` is how many dots it shows (at least four, like a PIN field).
inline KeypadLayout keypad_layout(const Metrics &m, int width, int top, int bottom, unsigned digits) {
  KeypadLayout l;
  const int x = m.side, w = width - 2 * m.side, h = bottom - top;
  if (w <= 0 || h <= 0) return l;
  const int shown = (int) (digits < 4 ? 4 : digits > CODE_MAX ? CODE_MAX : digits);
  l.beside = w * 10 >= h * 13;
  int g = m.gap();
  const int info_h = m.dot() + g + m.text_h;
  int kh = m.key_h() > m.least_key() ? m.key_h() : m.least_key();
  const int keys_h = l.beside ? h : h - info_h - 2 * g;
  // Short glass gives up the space between the keys before a key gets smaller than a finger.
  if (4 * m.least_key() + 3 * g > keys_h) g = (keys_h - 4 * m.least_key()) / 3 > 2 ? (keys_h - 4 * m.least_key()) / 3 : 2;
  if (4 * kh + 3 * g > keys_h) kh = (keys_h - 3 * g) / 4 > m.least_key() ? (keys_h - 3 * g) / 4 : m.least_key();
  // A key as wide as a finger and a half, and never wider than a third of the room.
  int kw = kh * 3 / 2;
  const int third = ((l.beside ? w * 64 / 100 : w) - 2 * g) / 3;
  if (kw > third) kw = third;
  if (kw < m.least_key()) kw = m.least_key();
  const int pad_w = 3 * kw + 2 * g, pad_h = 4 * kh + 3 * g;
  // Beside each other on wide glass, the dots keep close to the keys: the two stand together in the middle.
  const int info_w = l.beside ? (w - pad_w - 2 * g < pad_w ? w - pad_w - 2 * g : pad_w) : w;
  const int pair_x = l.beside ? x + (w - (info_w + 2 * g + pad_w)) / 2 : x;
  const int px0 = l.beside ? pair_x + info_w + 2 * g : x + (w - pad_w) / 2;
  // Under each other, the dots stand right above the keys and the two in the middle of the card, as a phone's.
  const int py0 = l.beside ? top + (h - pad_h) / 2 : top + (h - (info_h + 2 * g + pad_h)) / 2 + info_h + 2 * g;
  for (int i = 0; i < 12; ++i) l.keys[i] = {px0 + (i % 3) * (kw + g), py0 + (i / 3) * (kh + g), kw, kh};
  l.info = l.beside ? Rect{pair_x, top, info_w, h} : Rect{x, py0 - 2 * g - info_h, w, info_h + g};
  l.dot = m.dot();
  while (l.dot > 4 && shown * l.dot + (shown - 1) * dot_gap(l.dot) > l.info.w) --l.dot;
  const int row_w = shown * l.dot + (shown - 1) * dot_gap(l.dot);
  // Beside the keys the column is narrow (a CYD lying down leaves it a hundred pixels), so the line under the dots may
  // take up to three lines there ("Nothing changed. Check the code." cut after its first word otherwise).
  const int lines = l.beside ? 3 : 1;
  const int block = l.dot + g + lines * m.text_h, by = l.info.y + (l.info.h - block) / 2;
  l.dots = {l.info.x + (l.info.w - row_w) / 2, by, row_w, l.dot};
  l.line = {l.info.x, by + l.dot + g, l.info.w, lines * m.text_h};
  return l;
}

}  // namespace alarm_panel
