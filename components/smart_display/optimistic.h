#pragma once
// What a finger changed, shown at once and squared with Home Assistant later (docs/OPTIMISTIC.md).
//
// Every control that changes a value of an entity goes through one Wish: the value the finger wants, kept in front of
// what Home Assistant reports until Home Assistant agrees, says something else, refuses, or leaves it as it was. The
// rules follow Home Assistant's own frontend:
// - the new value shows at once (ha-entity-toggle, the mode selects of its card features);
// - a choice (on or off, a mode, play) goes out at once; taps that come while it is on its way are folded into one:
//   only the last wish goes out, once Home Assistant has taken the one before, and none when it is what was sent
//   already. A fast Home Assistant gets every tap, a slow device a burst as one action;
// - a step (-/+) goes out once the finger rested `quiet` ms, as Home Assistant's target temperature waits for the last
//   press, so 16 to 20 is one call and not four;
// - a report that still says the value from before is a message from before the action, and the wish stays in front
//   (a Hue room reports its lamps first and itself a second later);
// - the value sent reported ends it; any other value ends it too, and that value shows: Home Assistant decides;
// - a refusal puts the old value back at once (the mode selects' catch), "it worked" without the value changing puts it
//   back TAP_HOLD later (ha-entity-toggle's two seconds), and no answer at all puts it back after a cap.
//
// This file knows values as text and time as millis(); runtime_tiles.h reads and writes the tile's fields
// (wish_read, wish_write) and sends the actions. Pure, so tests/test_optimistic.cpp runs it on the host.
#include <array>
#include <cstdint>
#include <string>

namespace optimistic {

// After Home Assistant's "it worked", the wish waits this long for the value to change (ha-entity-toggle: 2000 ms).
constexpr uint32_t TAP_HOLD = 2000;
// Without any answer the old value comes back after this long (Tile::BUSY_CAP, the wait every command had before)...
constexpr uint32_t HOLD_CAP = 3000;
// ...unless Home Assistant was asked to answer (watch_call): then the wish waits for it, as Home Assistant's toggle
// waits for its call to return, however long a slow device takes. watch_call gives up after eight seconds.
constexpr uint32_t WATCHED_CAP = 9000;
// A newer wish waits for the answer to the one on its way; where none will come (watch_call had no place free), it
// goes this long after the one before.
constexpr uint32_t NEXT_UNWATCHED = 400;
// A wish Home Assistant has not squared this long after it went out says so on its tile ("Updating...", as Apple's
// Home app does for a slow accessory); a device that answers in time never shows it.
constexpr uint32_t SLOW_SHOW = 1000;
// A wish that lapsed without an answer stays known this long, for the "no answer" verdict watch_call gives at 8 s.
constexpr uint32_t LAPSED_KEEP = 12000;

// What a tile shows that a finger can change; runtime_tiles.h reads and writes each (wish_read, wish_write).
enum class Field : uint8_t {
  ON_OFF,           // state "on" / "off": lights, switches, fans, automations, remotes, humidifiers
  OPTION,           // state = the option: select, input_select
  HVAC_MODE,        // state = the mode: climate
  HUMIDIFIER_MODE,  // the humidifier's mode attribute
  FAN_MODE,         // a thermostat's fan mode
  SWING_MODE,       // a thermostat's swing mode
  ACTIVITY,         // a remote's activity (and it is on)
  PLAYING,          // "1" playing, "0" not: a player's play / pause key
  SHUFFLE,          // "1" / "0"
  REPEAT,           // "off" / "all" / "one"
  MUTED,            // "1" / "0"
  // A part of the tile's entity, named by the wish's `item` (a lamp of a group, a row of a light's effects page):
  LAMP_ON,          // "1" / "0": a lamp of a group
  LAMP_LEVEL,       // its brightness 1-100, "0" for off
  LAMP_HUE,         // its hue 0-360 (at full saturation)
  LAMP_KELVIN,      // its white shade in kelvin
  EFFECT,           // the effect a light runs (no item: the light itself)
  ROW_OPTION,       // the option of a select on the light's device (item: the select)
  ROW_NUMBER,       // the value of a number on the light's device (item: the number)
  VACUUM_ROW,       // the choice of a vacuum's row (item: the row's kind, 'm' mode, 's' suction, 'w' water)
};

// IDLE: nothing. READY: to go out at the next tick (a step waits for its quiet first). SENT: on its way, `sent` asked
// for, `want` maybe newer. LAPSED: given up without an answer, kept for watch_call's verdict.
enum class Phase : uint8_t { IDLE, READY, SENT, LAPSED };

// What a report, an answer or the clock did to a wish.
enum class Outcome : uint8_t {
  KEEP,       // the wish stays in front; write `want` over the report
  DONE,       // Home Assistant reports what was wished
  CORRECTED,  // Home Assistant reports another value: that one shows
  SEND,       // send the action for `want` now (`sent` is set to it)
  DROP,       // what is wished is what Home Assistant has: nothing to send
  REVERT,     // put `before` back (refused, unchanged after "it worked", or no answer)
};

struct Wish {
  std::string entity;  // the tile's entity, whose reports square the wish
  std::string target;  // the entity the action goes to (a player's speaker), whose answers do
  Field field = Field::ON_OFF;
  std::string item;    // which part of the entity, for a field of a part (a lamp, a row); empty for the tile's own
  bool rendered = false;  // the action's value is one Home Assistant renders (a list such as hs_color)
  // `before`: what Home Assistant had before the action on its way; `sent`: what that action asks; `want`: the shown.
  std::string before, sent, want;
  // The action that makes `want` come true, kept from the last tap.
  std::string service, key, value;
  Phase phase = Phase::IDLE;
  uint32_t quiet = 0;  // 0 for a choice; a step's rest before it goes out
  uint32_t changed_at = 0, sent_at = 0, answered_at = 0;
  bool refused = false;     // REVERT because Home Assistant said no: the tile says so
  bool watched = false;     // Home Assistant was asked to answer the action on its way
  bool slow_shown = false;  // its tile says it is still under way (slow())
  bool live() const { return phase == Phase::READY || phase == Phase::SENT; }
  bool queued() const { return phase == Phase::SENT && want != sent; }
};

// A finger's new wish for a field; `shown` is what the tile shows now. A choice goes out with the next tick (the caller
// runs it at once); a step after `quiet` ms of rest. While an action is on its way the wish only changes `want`: the
// answer to that action sends it (settle).
inline void want(Wish &w, const std::string &entity, const std::string &target, Field field, const std::string &shown,
                 const std::string &value, uint32_t now, uint32_t quiet = 0, const std::string &item = "") {
  if (!w.live() || w.entity != entity || w.field != field || w.item != item) {
    w = Wish();
    w.entity = entity;
    w.field = field;
    w.item = item;
    w.before = shown;
    w.phase = Phase::READY;
  }
  w.target = target;
  w.want = value;
  w.quiet = quiet;
  w.changed_at = now;
  w.refused = false;
}

// The action on its way is taken (Home Assistant answered or reported it): a newer wish goes out next.
inline Outcome settle(Wish &w, const std::string &taken) {
  if (w.want == taken) { w.phase = Phase::IDLE; return Outcome::DONE; }
  w.before = taken;
  w.phase = Phase::READY;
  return Outcome::KEEP;
}

// A state message for the wish's entity carries `reported` for its field.
inline Outcome report(Wish &w, const std::string &reported) {
  if (!w.live()) return Outcome::DONE;
  // Nothing on its way yet: a new value is someone else's change, and the wish goes out from there.
  if (w.phase == Phase::READY) { w.before = reported; return Outcome::KEEP; }
  if (reported == w.sent) return settle(w, reported);
  if (reported == w.before) return Outcome::KEEP;
  w.phase = Phase::IDLE;
  return Outcome::CORRECTED;
}

// The clock: a wish ready to go out, a hold running out.
inline Outcome tick(Wish &w, uint32_t now) {
  if (w.phase == Phase::READY) {
    if (w.quiet && now - w.changed_at < w.quiet) return Outcome::KEEP;
    if (w.want == w.before) { w.phase = Phase::IDLE; return Outcome::DROP; }
    w.phase = Phase::SENT;
    w.sent = w.want;
    w.sent_at = now;
    w.answered_at = 0;
    w.watched = false;  // the sender says (sent())
    w.slow_shown = false;
    return Outcome::SEND;
  }
  if (w.phase == Phase::SENT) {
    // A newer wish where Home Assistant gives no answers: it goes a moment after the one before.
    if (w.queued() && !w.watched && now - w.sent_at >= NEXT_UNWATCHED) { settle(w, w.sent); return tick(w, now); }
    if (w.answered_at ? now - w.answered_at >= TAP_HOLD : now - w.sent_at >= (w.watched ? WATCHED_CAP : HOLD_CAP)) {
      w.phase = w.answered_at ? Phase::IDLE : Phase::LAPSED;
      return Outcome::REVERT;
    }
    return Outcome::KEEP;
  }
  if (w.phase == Phase::LAPSED && now - w.sent_at >= LAPSED_KEEP) w.phase = Phase::IDLE;
  return Outcome::KEEP;
}

// The action went out after SEND; `watched`: Home Assistant will answer it.
inline void sent(Wish &w, bool watched) { w.watched = watched; }

// Home Assistant answered the action on its way: "it worked" lets a newer wish go next or starts the hold, a refusal
// puts the old value back at once (and drops what came after it).
inline Outcome answer(Wish &w, bool ok, uint32_t now) {
  if (w.phase != Phase::SENT) return Outcome::KEEP;
  if (!ok) {
    w.phase = Phase::IDLE;
    w.refused = true;
    return Outcome::REVERT;
  }
  if (w.queued()) return settle(w, w.sent);
  w.answered_at = now ? now : 1;
  return Outcome::KEEP;
}

// No answer and no change (watch_call's verdict after eight seconds). REVERT: the wish still waited, put `before` back
// and say why; KEEP: it lapsed and its value went back already, only say why; DONE: nothing of this wish.
inline Outcome unanswered(Wish &w) {
  if (w.phase != Phase::SENT && w.phase != Phase::LAPSED) return Outcome::DONE;
  const bool waited = w.phase == Phase::SENT;
  w.phase = Phase::IDLE;
  return waited ? Outcome::REVERT : Outcome::KEEP;
}

// Sent, and neither squared nor given up after SLOW_SHOW: the tile says it is under way.
inline bool slow(const Wish &w, uint32_t now) { return w.phase == Phase::SENT && now - w.sent_at >= SLOW_SHOW; }

// The few wishes a screen holds at once: a finger makes them one or two at a time.
template <size_t N> struct Pool {
  std::array<Wish, N> wishes{};
  Wish *find(const std::string &entity, Field field, const std::string &item = "") {
    for (auto &w : wishes) if (w.live() && w.entity == entity && w.field == field && w.item == item) return &w;
    return nullptr;
  }
  // A slot for a new wish: the one for this field (and part), a free one, or the oldest (ended as if Home Assistant
  // agreed).
  Wish &slot(const std::string &entity, Field field, const std::string &item = "") {
    if (Wish *w = find(entity, field, item)) return *w;
    for (auto &w : wishes) if (w.phase == Phase::IDLE) return w;
    for (auto &w : wishes) if (w.phase == Phase::LAPSED) return w;
    Wish *oldest = &wishes[0];
    for (auto &w : wishes) if (w.changed_at < oldest->changed_at) oldest = &w;
    oldest->phase = Phase::IDLE;
    return *oldest;
  }
  bool any() const {
    for (auto &w : wishes) if (w.phase != Phase::IDLE) return true;
    return false;
  }
};

}  // namespace optimistic
