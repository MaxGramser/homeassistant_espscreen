#pragma once
// Whether the board itself moved, from a motion sensor on it (Wake when moved, packages/features/wake-when-moved.yaml):
// picked up, tilted, turned or knocked. It feels the board, not someone walking past.
//
// Each axis of the accelerometer and of the gyroscope keeps its own resting value, which follows the readings slowly;
// the board moved when an axis leaves its resting value by more than its kind's threshold. A board that lies still at
// any angle is still, since gravity is in the resting value, and so is the few degrees a second every gyroscope reads
// while it lies still. ESPHome's `motion`
// reports acceleration in g and turning in degrees a second, not m/s²: the first Wake when moved compared two readings
// with 1.0, a whole g, which only a shake reached.
//
// Free of LVGL and ESPHome: a board feeds it every reading and runs its wake when it says so.
// tests/test_moved.cpp drives it with made readings and checks the thresholds against the D1001's recording.
#include <cmath>
#include <cstdint>

namespace moved {

enum Kind : uint8_t { ACCELERATION = 0, TURNING = 1 };

// The thresholds come from a reTerminal D1001 on a desk (tests/data/moved_d1001.csv, 2026-11-24). Lying still, the
// gyroscope stayed within 0.86 degrees a second of its resting value and the accelerometer within 0.021 g (the desk's
// own small shakes); picked up as gently as a person does, the board turned at 22 degrees a second or more and moved
// 0.17 g or more. Turning is the sign of a hand: a board is never lifted without turning a little, and the desk's
// shakes barely turn it.
//
// Turning, in degrees a second: 3 is three and a half times the most it read at rest and a seventh of the gentlest
// lift. A slow tilt of five degrees a second passes it too.
constexpr float TURNING_DPS = 3.0f;
// Acceleration, in g: 0.06 is three times the desk's shakes and a third of the gentlest lift. A knock on the board or
// the table (0.12 g in the recording) wakes it too, by design.
constexpr float ACCELERATION_G = 0.06f;
// How long the resting value takes to follow (a time constant): acceleration half a second, so a tilt over a second
// or two is still a change; turning two seconds, which takes away the gyroscope's drift and little else.
constexpr uint32_t ACCELERATION_FOLLOW_MS = 500;
constexpr uint32_t TURNING_FOLLOW_MS = 2000;
// Once it said the board moved, it stays silent this long: a pick-up is one wake, not ten.
constexpr uint32_t REPEAT_MS = 2000;

class Detector {
 public:
  // One reading of one axis (0, 1, 2) at `now` (milliseconds). True when the board moved.
  bool feel(Kind kind, uint8_t axis, float value, uint32_t now) {
    if (kind > TURNING || axis > 2 || std::isnan(value)) return false;
    Axis &a = axes_[kind][axis];
    if (!a.known) {
      a = Axis{true, value, now};
      return false;
    }
    float away = std::fabs(value - a.rest);
    if (away > largest_[kind]) largest_[kind] = away;
    float follow = kind == ACCELERATION ? (float) ACCELERATION_FOLLOW_MS : (float) TURNING_FOLLOW_MS;
    float dt = (float) (uint32_t) (now - a.at);
    a.rest += (value - a.rest) * (dt / (follow + dt));
    a.at = now;
    if (away <= (kind == ACCELERATION ? ACCELERATION_G : TURNING_DPS)) return false;
    if (said_ && now - said_at_ < REPEAT_MS) return false;
    said_ = true;
    said_at_ = now;
    last_kind_ = kind;
    last_axis_ = axis;
    last_away_ = away;
    return true;
  }

  // The largest departure of any axis of a kind since the last call, then from zero again: the measurement the
  // thresholds come from (Debug mode logs it every second, features/wake-when-moved.yaml).
  float take_largest(Kind kind) {
    float largest = largest_[kind];
    largest_[kind] = 0;
    return largest;
  }

  // What the last "moved" felt, for the log.
  Kind last_kind() const { return last_kind_; }
  uint8_t last_axis() const { return last_axis_; }
  float last_away() const { return last_away_; }

 private:
  struct Axis {
    bool known = false;
    float rest = 0;
    uint32_t at = 0;
  };
  Axis axes_[2][3]{};
  float largest_[2]{0, 0};
  bool said_ = false;
  uint32_t said_at_ = 0;
  Kind last_kind_ = ACCELERATION;
  uint8_t last_axis_ = 0;
  float last_away_ = 0;
};

// The board's one detector.
inline Detector &the() {
  static Detector detector;
  return detector;
}

}  // namespace moved
