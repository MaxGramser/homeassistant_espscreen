#pragma once
// The doorbell view's door key (module doorbell, docs/DOORBELL.md, "Open the door"): what it shows and what a tap does,
// free of LVGL, so tests/test_doorbell_door.cpp checks it on a PC. module_doorbell.cpp draws it.
//
// The ring's automation names the door, and ESP Screens says how in the op doorbell (`d`): a lock entity, whose state it
// sends along and again at every change (`ds`), or an action of the automation's own (a script, a gate's button). The
// screen never performs it itself: a second tap says "door" in its report of the ring, and ESP Screens performs
// lock.unlock on the lock, or the action, through Home Assistant, as it performs an alert's button.
//
// As the lock tile (lock_panel.h): a wall screen by the door is touched by everyone who walks past, so one tap never
// opens it. The first tap arms the key ("Tap again to open", in the lock's orange) for lock_panel's five seconds; the
// second within that time opens. A lock opens only from a state it knows and can leave (locked, or jammed as Home
// Assistant's dialog allows), never while it moves or once it is open; after the second tap the key says "Unlocking"
// until the lock's new state comes, or shows "Sent" for two seconds after an action.
#include <cstdint>
#include <string>
#include "lock_panel.h"

namespace doorbell_door {

enum class Kind : uint8_t { NONE, LOCK, ACTION };
// The op's `d`: 1 a lock, 2 an action; anything else no door, and no key.
inline Kind kind_of(unsigned d) { return d == 1 ? Kind::LOCK : d == 2 ? Kind::ACTION : Kind::NONE; }

// How long the key waits for a lock's new state after the second tap, and shows "Sent" after an action.
constexpr uint32_t WAIT_MS = 10000, SENT_MS = lock_panel::DONE_MS;

struct Door {
  Kind kind = Kind::NONE;
  std::string state;  // the lock's state, as Home Assistant has it
  lock_panel::Confirm confirm;
  uint32_t sent_at = 0;  // the second tap, 0 before it

  // A lock's state from ESP Screens: a new one ends the wait for it.
  void set_state(const std::string &now) {
    if (now != state) sent_at = 0;
    state = now;
  }
  bool sending(uint32_t now) const {
    return sent_at && now - sent_at < (kind == Kind::LOCK ? WAIT_MS : SENT_MS);
  }
  // Whether a tap may open it now.
  bool opens(uint32_t now) const {
    if (sending(now)) return false;
    if (kind == Kind::ACTION) return true;
    return kind == Kind::LOCK && (state == "locked" || state == "jammed");
  }
  bool armed(uint32_t now) const { return confirm.waiting(lock_panel::UNLOCK, now); }
  // A finger on the key: true for the second tap within the time, when the screen says "door".
  bool tap(uint32_t now) {
    if (!opens(now)) {
      confirm.clear();
      return false;
    }
    if (!confirm.press(lock_panel::UNLOCK, now)) return false;
    sent_at = now ? now : 1;
    return true;
  }
};

// What the key shows: its colour, its glyph and the line under the word "Door".
enum class Line : uint8_t { NONE, STATE, TAP_AGAIN, UNLOCKING, SENT };
struct Look {
  uint32_t color;
  const char *glyph;
  Line line;
};
inline Look look(const Door &d, uint32_t now, uint32_t idle) {
  using namespace lock_panel;
  if (d.armed(now)) return {ORANGE, glyph::LOCK_OPEN, Line::TAP_AGAIN};
  if (d.kind == Kind::ACTION) return {idle, glyph::DOOR_OPEN, d.sending(now) ? Line::SENT : Line::NONE};
  if (d.sending(now)) return {ORANGE, glyph::LOCK_CLOCK, Line::UNLOCKING};
  // A lock whose state is not one of a lock's (unavailable, unknown) in the key's own grey.
  return {known(d.state) ? color(d.state) : idle, icon(d.state), Line::STATE};
}

}  // namespace doorbell_door
