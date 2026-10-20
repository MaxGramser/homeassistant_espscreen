#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>

#include "screen_hooks.h"

namespace screen_input {
// The n-th quoted item of a JSON list such as ["auto","low","high"]; empty when absent.
inline std::string list_item(const std::string &json, unsigned index) {
  size_t pos = 0; unsigned n = 0;
  while ((pos = json.find('"', pos)) != std::string::npos) {
    size_t end = json.find('"', pos + 1);
    if (end == std::string::npos) return {};
    if (n++ == index) return json.substr(pos + 1, end - pos - 1);
    pos = end + 1;
  }
  return {};
}
// Work in tenths of a degree and always clamp AFTER rounding.
inline int quantize_temperature(int value, int minimum, int maximum, int step) {
  step = std::max(1, step);
  value = std::clamp(value, minimum, maximum);
  const int snapped = minimum + static_cast<int>(std::lround(
      static_cast<double>(value - minimum) / step)) * step;
  return std::clamp(snapped, minimum, maximum);
}

class TouchGuard {
 public:
  enum Reject { NONE, MOVED, TOO_SHORT, USED, BOUNCE };
  // Board tuning, set from the profile on boot: how far the finger may drift (pixels) before
  // a tap is dropped, 0 for no limit at all, and the shortest contact that counts. A resistive
  // panel (CYD) bounces on landing and lift-off and needs both; a capacitive one (Guition) needs
  // neither. Without a limit a tile checks itself that the finger let go on it (runtime_tiles::event:
  // LVGL keeps the press on the tile and clicks it wherever the finger lets go), and a quick flick
  // is LVGL's gesture, which consume()s the contact (firmware 0.2.65+).
  void configure(int move_limit_px, uint32_t min_press_ms) {
    move_limit_ = move_limit_px;
    min_press_ = min_press_ms;
  }
  int move_limit() const { return move_limit_; }
  uint32_t min_press() const { return min_press_; }
  void begin(uint32_t now, int x = 0, int y = 0, int contact = 0) {
    started_ = now;
    accepted_ = false;
    moved_ = false;
    contact_ = contact;
    samples_ = 1;
    sum_x_ = anchor_x_ = x;
    sum_y_ = anchor_y_ = y;
    distance_ = 0;
    reject_ = NONE;
  }
  int contact() const { return contact_; }
  // Follows only the contact that started this touch: a second finger elsewhere is no movement.
  // The reference point settles over the first samples, because a finger flattens as it lands;
  // a tap is dropped once the finger is farther than the limit from that point.
  void update(int x, int y, int contact = 0) {
    if (contact != contact_) return;
    if (samples_ < SETTLE_SAMPLES) {
      ++samples_;
      sum_x_ += x;
      sum_y_ += y;
      anchor_x_ = sum_x_ / samples_;
      anchor_y_ = sum_y_ / samples_;
    }
    const long dx = x - anchor_x_, dy = y - anchor_y_;
    const int distance = static_cast<int>(std::lround(std::sqrt(static_cast<double>(dx * dx + dy * dy))));
    distance_ = std::max(distance_, distance);
    if (move_limit_ > 0 && distance > move_limit_) moved_ = true;
  }
  int distance() const { return distance_; }
  void consume() { accepted_ = true; moved_ = true; }
  // A tap and a key say so to screen_hooks::touched() (a click of a plugin); a slider's release does not.
  bool accept(uint32_t now, int tile) {
    if (moved_) { reject_ = MOVED; return false; }
    if (!accept_within(now, tile, 600)) return false;
    screen_hooks::run_touched();
    return true;
  }
  // For -/+ keys and the page buttons: every clean tap counts, even the third within a second,
  // so a setpoint moves several steps in one go and Next, Next, Next reaches page 4 without
  // waiting for each page to draw. Only bounce (same key within `gap`) is dropped.
  bool accept_repeat(uint32_t now, int tile, uint32_t gap = 150) {
    if (moved_) { reject_ = MOVED; return false; }
    if (accepted_) { reject_ = USED; return false; }
    if (!long_enough(now, std::min<uint32_t>(min_press_, 40))) return false;
    if (has_previous_ && tile == previous_tile_ && now - previous_ < gap) { reject_ = BOUNCE; return false; }
    remember(now, tile);
    screen_hooks::run_touched();
    return true;
  }
  // Only for a slider which captured this contact and did not lose the press.
  // Consume the gesture so its parent can never also turn it into a tile tap. A slider sends
  // once per contact, on release, so a second drag right after the first is no bounce.
  bool accept_slider(uint32_t now, int tile) { return accept_within(now, tile, 0); }
  // Why the last accept() refused, for the touch log; empty after a success.
  std::string reason() const {
    switch (reject_) {
      case MOVED: return "moved " + std::to_string(distance_) + " px (limit " + std::to_string(move_limit_) + ")";
      case TOO_SHORT: return "too short (" + std::to_string(duration_) + " ms, minimum " + std::to_string(min_press_) + ")";
      case USED: return "already handled in this contact";
      case BOUNCE: return "same button within the debounce window";
      default: return "";
    }
  }
 private:
  static constexpr int SETTLE_SAMPLES = 4;
  bool accept_within(uint32_t now, int tile, uint32_t gap) {
    if (accepted_) { reject_ = USED; return false; }
    if (!long_enough(now, min_press_)) return false;
    if (gap && has_previous_ && tile == previous_tile_ && now - previous_ < gap) { reject_ = BOUNCE; return false; }
    remember(now, tile);
    return true;
  }
  bool long_enough(uint32_t now, uint32_t minimum) {
    duration_ = now - started_;
    if (duration_ < minimum) { reject_ = TOO_SHORT; return false; }
    return true;
  }
  void remember(uint32_t now, int tile) {
    accepted_ = true;
    has_previous_ = true;
    previous_tile_ = tile;
    previous_ = now;
    reject_ = NONE;
  }
  int move_limit_{18};
  uint32_t min_press_{60};
  uint32_t started_{0}, previous_{0}, duration_{0};
  int previous_tile_{-1};
  int contact_{0}, samples_{1};
  long sum_x_{0}, sum_y_{0};
  int anchor_x_{0}, anchor_y_{0}, distance_{0};
  bool moved_{false};
  bool accepted_{false}, has_previous_{false};
  Reject reject_{NONE};
};
inline TouchGuard touch_guard;

// Page navigation by swiping in from a side edge (Guition, firmware 0.2.24+). Fed from
// ESPHome's touchscreen triggers: on_touch begins, on_update updates, on_release ends, because
// LVGL 9.5 sends no PRESSING to the input device. A touch that starts within `band` pixels of the
// left or right edge of the screen as the user sees it and travels `travel` pixels inward, more
// sideways than up or down, flips one page: from the right edge leftwards is "next", from the left
// edge rightwards "previous". No speed requirement; a touch that starts in the middle never counts,
// so tapping and dragging on tiles cannot change the page by accident. Up from the bottom edge goes home and down
// from the top edge opens the settings page, over every card as well as the tiles (firmware 0.28.0+).
//
// Every point here is already in the screen's own coordinates: `runtime_tiles::touch_input` turns a
// touchscreen's report with ESPHome's own `LvglComponent::rotate_coordinates`, the same call that
// places the pointer, so the board's quarter turn and the turn the user chose are both in it. This
// class used to redo that arithmetic from the display size the board declares, which is the canvas
// *after* the turn while ESPHome reports in the panel's own pixels: on a 800 x 1280 panel drawn as
// 1280 x 800 the right-hand band began at 772 instead of 1252, so two fifths of the glass turned a
// page on any leftward drag and nothing came back (firmware 0.2.82).
class EdgeSwipe {
 public:
  // A band along the left and right edge of the glass, and how far inward a finger must travel. The width of
  // the glass is not stated: `begin` reads it from the display every time, so the bands stay on the edges when
  // a screen is built standing up or turned in its settings (firmware 0.2.92+).
  void configure(int band, int travel) {
    band_ = band; travel_ = travel;
    configured_ = true;
  }
  // Glass that turns its pages by a flick anywhere (the resistive CYD, LVGL's gesture) keeps only the bands along
  // the top and the bottom: a drag in from a side edge stays that flick's (firmware 0.28.0+).
  void without_sides() { sides_ = false; }
  // What a finger asked for: another page, the way home (firmware 0.2.100+), or the settings page (0.28.0+).
  enum class Gesture : uint8_t { none, previous, next, home, settings };
  // A board that never configured one has no edge swipe: a swipe along its edge must not flip a page. Without
  // this, shared touch handling would arm this on the default 480 x 480 band and turn pages on a screen that never
  // did.
  bool in_use() const { return configured_; }
  // `width` is the glass as the person sees it, measured now rather than stated once: a screen built standing
  // up, or turned in its settings, keeps its bands on the edges (firmware 0.2.92+). This class stays free of
  // LVGL so tests/test_screen_input.cpp can walk a whole gesture over any size of glass.
  // `height` is the glass the same way, so the bands along the bottom and the top edge lie on those edges
  // (firmware 0.2.100+). A screen that states no height has neither and behaves exactly as it did.
  void begin(int x, int y, int width, int height = 0) {
    start_x_ = x; start_y_ = y;
    from_ = !sides_ ? 0 : x < band_ ? 1 : x >= width - band_ ? -1 : 0;  // 1: left edge, -1: right edge
    up_ = height > 0 && y >= height - band_;
    down_ = height > 0 && y < band_;
    done_ = false;
    inward_ = sideways_ = 0;
  }
  bool armed() const { return configured_ && (from_ != 0 || up_ || down_) && !done_; }
  // The next page, the previous one, page 1, the settings page or nothing; fires at most once per touch. A finger
  // that starts in a corner where two bands meet is judged by the way it actually travels.
  Gesture update(int x, int y) {
    if (!armed()) return Gesture::none;
    const int dx = x - start_x_, dy = y - start_y_;
    const bool upright = std::abs(dy) > std::abs(dx);
    if (up_ && -dy >= travel_ && upright) {
      inward_ = std::max(inward_, -dy);
      done_ = true;
      return Gesture::home;
    }
    // Down from the top edge opens the settings page, as a phone pulls down its quick settings (GitHub #133).
    if (down_ && dy >= travel_ && upright) {
      inward_ = std::max(inward_, dy);
      done_ = true;
      return Gesture::settings;
    }
    if (from_ == 0) {
      inward_ = std::max(inward_, std::abs(dy));
      sideways_ = std::max(sideways_, std::abs(dx));
      return Gesture::none;
    }
    const int inward = from_ == 1 ? dx : -dx;
    inward_ = std::max(inward_, inward);
    sideways_ = std::max(sideways_, std::abs(dy));
    if (inward < travel_ || std::abs(dx) < std::abs(dy)) return Gesture::none;
    done_ = true;
    return from_ == 1 ? Gesture::previous : Gesture::next;
  }
  // The finger left the glass: a stale armed state must never fire on the next touch
  // (ESPHome runs on_update before on_touch in the first cycle of a new touch).
  void end() { done_ = true; }
  // How far the finger got, for the log when an edge touch ends without a page flip.
  int inward() const { return inward_; }
  int sideways() const { return sideways_; }
 private:
  bool configured_{false}, sides_{true};
  int band_{32}, travel_{40};
  int start_x_{0}, start_y_{0}, from_{0}, inward_{0}, sideways_{0};
  bool done_{true}, up_{false}, down_{false};
};
inline EdgeSwipe edge_swipe;

// The GT911 (Guition) now and then reports a contact at exactly (0, 0), mostly as the last
// sample before the finger lifts. LVGL takes the last pressed sample as the finger's position
// on release, so a slider jumped to its end and sent that value (a colour turning red). The
// corner pixel is never a real touch: such a sample repeats the read before it instead.
struct PointerRead {
  bool pressed;
  int x, y;
};
class GhostTouch {
 public:
  // `ghost_x`, `ghost_y`: where the native (0, 0) lands after the display rotation.
  PointerRead filter(PointerRead read, int ghost_x, int ghost_y) {
    if (read.pressed && read.x == ghost_x && read.y == ghost_y) {
      ++dropped_;
      return last_;
    }
    last_ = read;
    return read;
  }
  unsigned dropped() const { return dropped_; }
 private:
  PointerRead last_{false, 0, 0};
  unsigned dropped_{0};
};
inline GhostTouch ghost_touch;

// ESPHome hands what a touchscreen read to its listeners, LVGL's among them, one loop later (Touchscreen::loop defers
// send_touches_). In a loop where the touchscreen runs before LVGL, as its priority puts it (ESPHome reorders loops
// when a component pauses its own), LVGL reads a finger that the touchscreen has just read as gone. After a loop that
// took long, such as the redraw of a pressed card on a large glass with its draw buffer in PSRAM (the Waveshare 7B),
// LVGL counts that whole wait as press time, and past its long press a tap is a hold: a plugin's tile gets no tap, a
// light's tile opens its card instead of switching. The lift is taken from the touchscreen's own last read instead,
// once LVGL has heard the press; a finger that comes down still reaches LVGL the way ESPHome hands it on, after
// on_touch has begun the touch guard.
//
// ESPHome marks each touch a touchscreen holds (esphome/components/touchscreen/touchscreen.h): PRESSED (1) or UPDATED
// (2) for a finger its last read reported, the same with RELEASING (4) for one that read no longer did, RELEASED (0) for
// one gone before, CALIBRATE (7) for a finger on a panel without its range. Whether that read let go of every finger it
// held; `touches` is anything with a `state` per touch (Touchscreen::get_touches()).
template<typename Touches> bool panel_let_go(const Touches &touches) {
  bool held = false;
  for (const auto &touch : touches) {
    const int state = touch.state;
    if (state == 1 || state == 2 || state == 7) return false;
    held = true;
  }
  return held;
}
// How long LVGL holds a press before it is a long press: ESPHome's long_press_time for a touchscreen, which
// packages/core.yaml leaves as it is. Only for the log line of a lift that came that late.
constexpr uint32_t LVGL_LONG_PRESS_MS = 400;
class PanelRelease {
 public:
  // `read`: what ESPHome's listener tells LVGL now; `let_go`: panel_let_go() of the touchscreen's touches; `now` in ms.
  PointerRead filter(PointerRead read, bool let_go, uint32_t now) {
    // A press LVGL has not heard yet reaches it first, or a tap shorter than one loop would never reach it at all. A
    // finger let go stays let go until ESPHome says so too, so a later read can never press it a second time.
    const bool early = read.pressed && let_go && (pressed_ || early_);
    lifted_ = early && pressed_;
    if (lifted_) held_ = now - since_;
    if (early) read.pressed = false;
    else if (read.pressed && !pressed_) since_ = now;
    early_ = early;
    pressed_ = read.pressed;
    return read;
  }
  // Whether the last read let go of the press LVGL had, and how long LVGL had heard the finger by then.
  bool lifted() const { return lifted_; }
  uint32_t held() const { return held_; }
 private:
  bool pressed_{false}, early_{false}, lifted_{false};
  uint32_t since_{0}, held_{0};
};
inline PanelRelease panel_release;

// A dragged slider that LVGL moved to one of its ends on release, far from where the finger held
// it: the touch panel reported a stray point. Worth a log line, the finger was never there.
inline bool release_jump(int held, int released, int minimum, int maximum) {
  const bool at_end = released <= minimum || released >= maximum;
  return at_end && std::abs(released - held) * 4 > maximum - minimum;
}

// A slider whose end lies within `band` pixels of the screen's edge cannot be dragged to that end:
// the panel loses a finger swiped off the glass before it gets there (a GT911 reports a fast swipe
// for the last time 30-50 px inside the edge), and LVGL keeps the last point it saw. A finger let go
// inside that band meant the end, as a pointer clamped to the bar does in Home Assistant's slider.
// `point`, `start` and `end` lie along the slider's axis; returns -1 for the start, 1 for the end.
inline int edge_snap(int point, int start, int end, int screen, int band) {
  if (band <= 0 || screen <= 0) return 0;
  if (end >= screen - band && point >= screen - band) return 1;
  if (start < band && point < band) return -1;
  return 0;
}
inline int edge_snap_band = 0;
}  // namespace screen_input
