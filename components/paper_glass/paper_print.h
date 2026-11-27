#pragma once
// When a paper glass prints (docs/PAPER.md, "Printing"). A panel of e-paper takes a third of a second to several
// seconds for one refresh and wears a little with each, so what LVGL draws is not shown as it is drawn: this file
// decides the moment, and whether the panel refreshes only what changed or all of itself.
//
// The rules, each with its case in tests/test_paper_print.cpp:
// - A change waits a short quiet for more of them, and never longer than a most from the first: a burst of values from
//   Home Assistant, a card's parts, a page's tiles print as one refresh, not as one each.
// - A finger does not wait. What is drawn soon after a finger landed, moved or lifted is the answer to it and prints
//   at once.
// - While something is on its way that is only whole at its end (a layout, a page's build), nothing prints; a hold
//   that never ends still lets go after a most of its own.
// - A partial refresh leaves a trace of what stood there. So the glass keeps count of how much of itself partial
//   refreshes have changed, and once that is enough it refreshes whole (the panel flashes, the traces go): when it has
//   been left alone for a while, never under a finger. Only when the count runs far past enough does the next print
//   become the whole one, wanted or not.
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
  uint32_t finger_ms = 1200;    // what is drawn this soon after a finger is its answer
  uint32_t hold_most_ms = 10000;  // a hold lets go by itself after this
  uint32_t rest_ms = 30000;     // left alone this long, the glass may refresh whole
  uint16_t tidy_area = 3000;    // per mille of the glass changed by partial refreshes that is enough: three glasses
  uint16_t tidy_prints = 30;    // or this many partial refreshes
  uint16_t must_area = 9000;    // past this the next print is whole, rest or no rest
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
  // A finger landed, moved or lifted, or a key was pressed.
  void finger(uint32_t now) {
    finger_at_ = now;
    fingered_ = true;
    active_at_ = now;
    tick(now);
  }
  // LVGL finished a round of drawing that changed `permille` of the glass.
  void drawn(uint16_t permille, uint32_t now) {
    if (!dirty_) first_at_ = now;
    dirty_ = true;
    last_at_ = now;
    active_at_ = now;
    area_ = static_cast<uint16_t>(area_ + permille > 1000 ? 1000 : area_ + permille);
    tick(now);
  }
  // Something that is only whole at its end begins or ends.
  void hold(bool on, uint32_t now) {
    if (on && !held_) hold_at_ = now;
    held_ = on;
    tick(now);
  }
  // The next print is a whole one: a key asked for it, the look of the whole glass changed.
  void whole_next(uint32_t now) {
    whole_next_ = true;
    tick(now);
  }
  // The panel finished the refresh print() started.
  void printed(uint32_t now) {
    printing_ = false;
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
    if (!wants_tidy()) return;
    const int32_t rest = static_cast<int32_t>(active_at_ + rules.rest_ms - now);
    if (rest <= 0) {
      whole_next_ = true;
      print(now);
    } else {
      glass.later(static_cast<uint32_t>(rest));
    }
  }

  // ---- to read ----
  bool printing() const { return printing_; }
  bool waiting() const { return dirty_; }                 // something drawn is not on the glass yet
  uint16_t worn() const { return worn_; }                 // per mille of the glass changed since the last whole refresh
  uint32_t parts() const { return parts_total_; }         // partial refreshes since the start
  uint32_t wholes() const { return wholes_total_; }       // whole refreshes since the start

 private:
  bool wants_tidy() const { return rules.partial && (worn_ >= rules.tidy_area || parts_ >= rules.tidy_prints); }
  // How long what is drawn still waits, in ms; zero or less: it prints now.
  int32_t wait(uint32_t now) const {
    if (held_) {
      const int32_t let_go = static_cast<int32_t>(hold_at_ + rules.hold_most_ms - now);
      if (let_go > 0) return let_go;
    }
    if (!dirty_) return 0;  // a whole refresh that was asked for, with nothing new drawn
    if (fingered_ && now - finger_at_ < rules.finger_ms) return 0;
    const int32_t quiet = static_cast<int32_t>(last_at_ + rules.quiet_ms - now);
    const int32_t most = static_cast<int32_t>(first_at_ + rules.most_ms - now);
    return quiet < most ? quiet : most;
  }
  void print(uint32_t now) {
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
    (void) now;
    glass.print(whole);
  }

  bool dirty_ = false, printing_ = false, held_ = false, fingered_ = false, whole_next_ = false;
  bool started_ = false;  // the panel has been refreshed since the start
  uint32_t first_at_ = 0, last_at_ = 0, finger_at_ = 0, hold_at_ = 0, active_at_ = 0;
  uint16_t area_ = 0;   // per mille of the glass drawn and not printed yet
  uint16_t worn_ = 0;   // per mille changed by partial refreshes since the last whole one
  uint16_t parts_ = 0;  // partial refreshes since the last whole one
  uint32_t parts_total_ = 0, wholes_total_ = 0;
};

}  // namespace paper_print
