#pragma once
// When a paper glass prints (docs/PAPER.md, "Printing"). A panel of e-paper takes a third of a second to several
// seconds for one refresh and wears a little with each, so what LVGL draws is not shown as it is drawn: this file
// decides the moment, and whether the panel refreshes only what changed or all of itself.
//
// The rules, each with its case in tests/test_paper_print.cpp:
// - A change waits a short quiet for more of them, and never longer than a most from the first: a burst of values from
//   Home Assistant, a card's parts, a page's tiles print as one refresh, not as one each.
// - Nothing prints under a finger. What LVGL draws while one lies on the glass is the look of a press, which is gone
//   again when it lifts; a refresh takes longer than a tap, so printing it would show the press after the fact and
//   make every tap two refreshes. A finger that stays (a hold, a drag) is shown after a most of its own.
// - What comes by itself and keeps coming (a meter's watts, a clock) prints no sooner than a few seconds after the last
//   print ended: a value every second would be a refresh every second, on a glass that wears with each. A finger's
//   answer, news the screen was told of and a whole refresh that was asked for do not wait for it.
// - A finger's answer does not wait for the quiet of a burst. What is drawn soon after a finger lifted or a key was
//   pressed prints as soon as the drawing has stood still for a few frames, so a short fade ends before its print and
//   never is one.
// - While something is on its way that is only whole at its end (a layout, a page's build), nothing prints; a hold
//   that never ends still lets go after a most of its own.
// - A partial refresh leaves a trace of what stood there. So the glass keeps count of how much of itself partial
//   refreshes have changed. A whole refresh takes the traces off, and it flashes the whole panel black and white,
//   which draws the eye from across a room (the owner of the first paper screen, 2026-11-27: every few minutes was
//   far too often, and so was "once an hour"). So the glass refreshes whole by itself at one moment only: as the
//   screen comes to rest, its standby, when nobody has touched it for the whole standby time. Never on a clock. Only
//   when the count runs far past enough does a print that changes the glass anyway become the whole one.
// - A panel that cannot refresh a part (a panel of coloured inks) prints every time whole, after a longer quiet.
// - The first print after a start is a whole one: the panel still shows what it showed before the restart, which no
//   partial refresh can take off cleanly.
//
// It knows no LVGL, no driver and no clock of its own: the paper glass (components/paper_glass) tells it what
// happened with the time it happened at, and does what it is told through Glass.
#include <cstdint>

namespace paper_print {

// The numbers. A panel's own (how long a refresh takes, whether it has a partial one) come from its board through the
// paper glass; the rest are the same for every paper.
struct Rules {
  bool partial = true;          // the panel refreshes only what changed, between whole refreshes
  uint32_t quiet_ms = 350;      // a change waits this long for more of them
  uint32_t most_ms = 1500;      // and never longer than this from the first of them
  uint32_t stream_ms = 5000;    // what comes by itself prints no sooner than this after the last print ended
  uint32_t finger_ms = 1200;    // what is drawn this soon after a finger is its answer
  uint32_t finger_quiet_ms = 80;   // an answer prints once the drawing stood still this long
  uint32_t finger_most_ms = 400;   // and never later than this after the finger
  uint32_t down_most_ms = 1500;    // a finger that stays down this long is shown where it is
  uint32_t hold_most_ms = 10000;  // a hold lets go by itself after this
  uint16_t must_area = 30000;   // past this, thirty glasses, the next print is whole, rest or no rest
};
// A panel without a partial refresh: every print is the whole panel and takes many seconds, so changes gather longer.
constexpr Rules poster() {
  Rules r;
  r.partial = false;
  r.quiet_ms = 3000;
  r.most_ms = 15000;
  return r;
}

// What only the paper glass can do. Plain function pointers, each with an answer of its own until it is bound.
struct Glass {
  void (*print)(bool whole) = [](bool) {};    // the panel refreshes: what changed, or all of itself
  void (*later)(uint32_t) = [](uint32_t) {};  // tick() again after so many ms; a new ask replaces the last
};

class Printer {
 public:
  Glass glass;
  Rules rules;

  // ---- what happened ----
  // A finger lies on the glass (down) or lifted from it. A key's press is a finger that lifted.
  void finger(bool down, uint32_t now) {
    if (down && !down_) down_at_ = now;
    down_ = down;
    finger_at_ = now;
    fingered_ = true;
    tick(now);
  }
  // LVGL finished a round of drawing that changed `permille` of the glass.
  void drawn(uint16_t permille, uint32_t now) {
    if (!dirty_) first_at_ = now;
    dirty_ = true;
    last_at_ = now;
    area_ = static_cast<uint16_t>(area_ + permille > 1000 ? 1000 : area_ + permille);
    tick(now);
  }
  // Something that is only whole at its end begins or ends.
  void hold(bool on, uint32_t now) {
    if (on && !held_) hold_at_ = now;
    held_ = on;
    tick(now);
  }
  // The screen came to rest (its standby began) or left it. Coming to rest, a glass with traces is made clean once:
  // it will stand for a long time, and nobody has touched it for the whole standby time.
  void rest(bool on, uint32_t now) {
    if (on && !resting_ && rules.partial && parts_ > 0) {
      whole_next_ = true;
      asked_at_ = now;
    }
    resting_ = on;
    tick(now);
  }
  // The next print is a whole one: a key asked for it, the look of the whole glass changed.
  void whole_next(uint32_t now) {
    whole_next_ = true;
    asked_at_ = now;
    tick(now);
  }
  // The panel finished the refresh print() started.
  void printed(uint32_t now) {
    printing_ = false;
    printed_at_ = now;
    printed_once_ = true;
    tick(now);
  }

  // ---- the one clock ----
  void tick(uint32_t now) {
    if (printing_) return;  // printed() comes back here
    if (dirty_ || whole_next_) {
      const int32_t left = wait(now);
      if (left <= 0) {
        print(now);
        return;
      }
      glass.later(static_cast<uint32_t>(left));
      return;
    }
  }

  // ---- to read ----
  bool printing() const { return printing_; }
  bool waiting() const { return dirty_; }                 // something drawn is not on the glass yet
  uint16_t worn() const { return worn_; }                 // per mille of the glass changed since the last whole refresh
  uint32_t parts() const { return parts_total_; }         // partial refreshes since the start
  uint32_t wholes() const { return wholes_total_; }       // whole refreshes since the start

 private:
  // How long what is drawn still waits, in ms; zero or less: it prints now.
  int32_t wait(uint32_t now) const {
    if (held_) {
      const int32_t let_go = static_cast<int32_t>(hold_at_ + rules.hold_most_ms - now);
      if (let_go > 0) return let_go;
    }
    // A whole refresh that was asked for, with nothing drawn yet: it waits the short quiet for what comes with it
    // (the page in its calm look as the screen comes to rest, the other look), so the two are one print.
    if (!dirty_) return static_cast<int32_t>(asked_at_ + rules.quiet_ms - now);
    if (down_) {
      const int32_t stays = static_cast<int32_t>(down_at_ + rules.down_most_ms - now);
      if (stays > 0) return stays;
    }
    if (fingered_ && now - finger_at_ < rules.finger_ms) {
      // Counted from the finger or from the first drawing after it, whichever is later: what was drawn under the
      // finger does not hurry the print that follows its lifting.
      const uint32_t from = static_cast<int32_t>(first_at_ - finger_at_) > 0 ? first_at_ : finger_at_;
      const int32_t still = static_cast<int32_t>(last_at_ + rules.finger_quiet_ms - now);
      const int32_t latest = static_cast<int32_t>(from + rules.finger_most_ms - now);
      return still < latest ? still : latest;
    }
    const int32_t quiet = static_cast<int32_t>(last_at_ + rules.quiet_ms - now);
    const int32_t most = static_cast<int32_t>(first_at_ + rules.most_ms - now);
    int32_t left = quiet < most ? quiet : most;
    // A stream: what comes by itself waits for its turn after the last print. A whole refresh that was asked for is
    // no stream.
    if (printed_once_ && !whole_next_ && now - printed_at_ < rules.stream_ms) {
      const int32_t turn = static_cast<int32_t>(printed_at_ + rules.stream_ms - now);
      if (turn > left) left = turn;
    }
    return left;
  }
  void print(uint32_t) {
    // Whole: a panel that knows no other way, one that was asked for (the screen coming to rest asks), the first, or
    // far too many traces.
    const bool whole = !rules.partial || whole_next_ || !started_ || worn_ + area_ >= rules.must_area;
    started_ = true;
    if (whole) {
      worn_ = 0;
      parts_ = 0;
      ++wholes_total_;
    } else {
      worn_ = static_cast<uint16_t>(worn_ + area_);
      ++parts_;
      ++parts_total_;
    }
    whole_next_ = false;
    dirty_ = false;
    area_ = 0;
    printing_ = true;
    glass.print(whole);
  }

  bool dirty_ = false, printing_ = false, held_ = false, fingered_ = false, whole_next_ = false;
  bool started_ = false;  // the panel has been refreshed since the start
  bool down_ = false;     // a finger lies on the glass
  uint32_t down_at_ = 0;
  uint32_t first_at_ = 0, last_at_ = 0, finger_at_ = 0, hold_at_ = 0;
  uint32_t printed_at_ = 0;    // when the last print ended
  uint32_t asked_at_ = 0;      // when a whole refresh was last asked for
  bool printed_once_ = false;  // one has ended since the start
  bool resting_ = false;       // the screen is at rest (its standby)
  uint16_t area_ = 0;   // per mille of the glass drawn and not printed yet
  uint16_t worn_ = 0;   // per mille changed by partial refreshes since the last whole one
  uint16_t parts_ = 0;  // partial refreshes since the last whole one
  uint32_t parts_total_ = 0, wholes_total_ = 0;
};

}  // namespace paper_print
