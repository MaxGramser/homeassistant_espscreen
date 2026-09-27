#pragma once
// The lock (firmware 0.4.0+): a Home Assistant lock entity as a tile and a card, the way Home Assistant's own lock
// dialog does it. Pure logic only, free of LVGL, so tests/test_lock_panel.cpp checks it on a PC: the colours and icons,
// what a tap on the tile does, which keys the card offers, when a code is asked for and how long a "tap again" waits.
// runtime_tiles.h draws it; the keypad and its lock after wrong codes are the alarm panel's (alarm_panel.h).
//
// What Home Assistant does, which this follows:
// - The states are locked, unlocked, locking, unlocking, open, opening and jammed (LockState). The actions are
//   lock.lock, lock.unlock and lock.open; open exists only where supported_features has OPEN (1), the latch that lets
//   the door swing. There is no lock.toggle.
// - Colours (--state-lock-*-color): locked green, the three moments in between orange, unlocked, open and jammed red.
//   Icons (icons.json of lock): lock, lock-open-variant, lock-clock while it moves, lock-alert when jammed.
// - A code is asked for (callProtectedLockService) when the lock has a code_format and no default code in its registry
//   options, for every one of the three actions: Home Assistant fills a default code in itself. The add-on says
//   whether one is stored; the code never leaves Home Assistant. Only digits are offered, as on the alarm's keypad.
// - Opening the door takes a second tap: the key says "Really open?" for five seconds (CONFIRM_TIMEOUT_SECOND in
//   more-info-lock.ts). The screen asks the same for unlocking, which Home Assistant's dialog does in one tap: a wall
//   screen is touched by everyone who walks past, so one stray tap never unlocks a door here.
// - Locking never asks: it is the safe way round, as every voice assistant Home Assistant bridges treats it (Google
//   asks its PIN to unlock, never to lock). A lock whose state the screen does not know is never unlocked.
//
// A tile decides for itself how far it may go (the `guard` option, per tile and so per screen): "confirm", the
// default, unlocks after a second tap; "lock_only" never unlocks or opens from this screen, for a screen in a porch,
// a garage or a child's room.
#include <cstdint>
#include <string>
#include "theme.h"

namespace lock_panel {

namespace feature {
constexpr uint32_t OPEN = 1;
}

// Home Assistant's lock icons (icons.json of lock), all in the tile icon fonts (tile_icons.HA_DEFAULTS), and the
// door of its open action.
namespace glyph {
constexpr const char *LOCK = "\U000F033E", *LOCK_OPEN = "\U000F0FC6", *LOCK_CLOCK = "\U000F097F", *LOCK_ALERT = "\U000F08EE";
constexpr const char *DOOR_OPEN = "\U000F081C";
}

enum Act : uint8_t { LOCK, UNLOCK, OPEN, NONE };
constexpr const char *SERVICES[] = {"lock.lock", "lock.unlock", "lock.open"};
inline const char *service(Act a) { return a < NONE ? SERVICES[a] : ""; }

inline bool moving(const std::string &state) { return state == "locking" || state == "unlocking" || state == "opening"; }
inline bool known(const std::string &state) {
  return state == "locked" || state == "unlocked" || state == "open" || state == "jammed" || moving(state);
}

constexpr uint32_t GREEN = theme::ha::GREEN, ORANGE = theme::ha::ORANGE, RED = theme::ha::RED;
inline uint32_t color(const std::string &state) {
  if (state == "locked") return GREEN;
  if (moving(state)) return ORANGE;
  return RED;
}
inline const char *icon(const std::string &state) {
  if (state == "jammed") return glyph::LOCK_ALERT;
  if (moving(state)) return glyph::LOCK_CLOCK;
  if (state == "unlocked" || state == "open") return glyph::LOCK_OPEN;
  return glyph::LOCK;
}

// How far a tile may go.
enum class Guard : uint8_t { CONFIRM, LOCK_ONLY };
inline Guard guard_of(const std::string &option) { return option == "lock_only" ? Guard::LOCK_ONLY : Guard::CONFIRM; }

// What Home Assistant's dialog allows now (canLock, canUnlock, canOpen): nothing while it moves or when it is not
// there, unless the integration only assumes its state. The screen adds its own rule: unlock or open only from a
// state it knows.
struct Lock { std::string state; uint32_t supported = 0; bool assumed = false, available = true; };
inline bool can(const Lock &l, Act a, Guard g) {
  if (!l.available || a >= NONE) return false;
  if (a != LOCK && g == Guard::LOCK_ONLY) return false;
  if (a == OPEN && !(l.supported & feature::OPEN)) return false;
  if (l.assumed) return true;
  if (moving(l.state)) return false;
  if (a == LOCK) return l.state != "locked";
  if (!known(l.state)) return false;
  if (a == UNLOCK) return l.state != "unlocked";
  return l.state != "open";
}
// Whether an action asks for a second tap.
inline bool confirms(Act a) { return a == UNLOCK || a == OPEN; }

// A tap on the tile: lock what is not locked, at once; a locked lock unlocks after a second tap on the same tile.
inline Act tap(const Lock &l, Guard g) {
  if (!l.available || moving(l.state)) return NONE;
  if (l.state == "locked") return can(l, UNLOCK, g) ? UNLOCK : NONE;
  return can(l, LOCK, g) ? LOCK : NONE;
}

// The card: the lock itself is its big key and does what a tap on the tile does (primary). Beside it stand the keys
// for what that one key cannot do (secondary): Unlock while the lock is jammed, since the big key then locks, as Home
// Assistant's dialog shows both while it is jammed; and Open door where the lock has one.
inline Act primary(const Lock &l, Guard g) { return tap(l, g); }
struct Keys { Act act[2] = {NONE, NONE}; unsigned count = 0; };
inline Keys secondary(const Lock &l, Guard g) {
  Keys k;
  if (g == Guard::LOCK_ONLY) return k;
  if (l.state == "jammed") k.act[k.count++] = UNLOCK;
  if (l.supported & feature::OPEN) k.act[k.count++] = OPEN;
  return k;
}

// "Tap again": a key or a tile waits five seconds for its second tap, as Home Assistant's Open door key does.
constexpr uint32_t CONFIRM_MS = 5000, DONE_MS = 2000;
struct Confirm {
  Act act = NONE;
  uint32_t since = 0;
  bool waiting(Act a, uint32_t now) const { return act == a && act != NONE && now - since < CONFIRM_MS; }
  bool any(uint32_t now) const { return act != NONE && now - since < CONFIRM_MS; }
  // A first tap arms it and says false; the second within the time says true and ends it.
  bool press(Act a, uint32_t now) {
    if (waiting(a, now)) { act = NONE; return true; }
    act = a; since = now ? now : 1;
    return false;
  }
  void clear() { act = NONE; }
};

// Whether an action asks for a code first: a code_format and no default code, for all three actions.
inline bool needs_code(const std::string &format, bool saved) { return !format.empty() && !saved; }
// A code of letters cannot be typed here (only digits are offered). Home Assistant writes a lock's code_format as a
// regular expression; one that allows no letters at all (^\d{4}$, ^[0-9]{6}$, \d+) can be typed.
inline bool code_typable(const std::string &format) {
  if (format.empty() || format == "number") return true;
  if (format == "text") return false;
  for (size_t i = 0; i < format.size(); ++i) {
    const char c = format[i];
    if (c == '\\') { if (i + 1 < format.size() && (format[i + 1] == 'w' || format[i + 1] == 'S' || format[i + 1] == 'D')) return false; ++i; continue; }
    if (c == '.' || (c >= 'a' && c <= 'z' && (i == 0 || format[i - 1] != '\\')) || (c >= 'A' && c <= 'Z')) return false;
  }
  return true;
}

// Whether a state is where an action was heading: the state itself or the step on the way.
inline bool reached(const std::string &state, Act a) {
  if (a == LOCK) return state == "locked" || state == "locking";
  if (a == UNLOCK) return state == "unlocked" || state == "unlocking" || state == "open" || state == "opening";
  if (a == OPEN) return state == "open" || state == "opening" || state == "unlocked";
  return false;
}

}  // namespace lock_panel
