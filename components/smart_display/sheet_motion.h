#pragma once
// The rest of a sheet's way after a finger let it go (screen_motion.h, settle): how long it takes and where it is at each moment,
// so that it goes on at the finger's speed and comes to rest at its place, as a phone's sheet does. Knows distances and
// speeds, nothing of LVGL, of a board or of the Dock. tests/test_sheet_motion.cpp proves it.
#include <algorithm>
#include <cstdint>

namespace sheet_motion {

// `lead` is the way the sheet would go in `ms` at the speed it starts with, in px.
struct Settle {
  uint32_t ms;
  int32_t lead;
};

// `distance` px left of a sheet `full` px long, `speed` px a second towards its place (at or below 0: none). The time is
// what a steady braking from that speed takes, within `shortest` and the share of `longest` that the part left is of the
// whole. The lead stays between one and a half times the distance, so even a sheet let go at rest leaves at once, and
// three times, the most a curve that ends at rest can start with and not pass its place.
inline Settle settle(int distance, int speed, int full, uint32_t shortest, uint32_t longest) {
  const int64_t d = std::max(distance, 0), s = std::max(speed, 0);
  const uint32_t slowest = std::max<uint32_t>(shortest, static_cast<uint32_t>(longest * d / std::max(full, 1)));
  const uint32_t braking = s > 0 ? static_cast<uint32_t>(std::min<int64_t>(2000 * d / s, slowest)) : slowest;
  const uint32_t ms = std::max(shortest, braking);
  const int64_t lead = std::min(std::max(s * ms / 1000, d * 3 / 2), d * 3);
  return {ms, static_cast<int32_t>(lead)};
}

// Where the sheet is `now` ms into `ms`, on its way from `from` to `to`: the cubic that starts with the lead and ends at
// rest.
inline int32_t at(int32_t from, int32_t to, int32_t lead, int32_t now, int32_t ms) {
  if (now <= 0 || ms <= 0) return ms <= 0 ? to : from;
  if (now >= ms) return to;
  const float t = static_cast<float>(now) / ms, t2 = t * t, t3 = t2 * t;
  const float directed = static_cast<float>(to >= from ? lead : -lead);
  const float place = (2 * t3 - 3 * t2 + 1) * from + (t3 - 2 * t2 + t) * directed + (3 * t2 - 2 * t3) * to;
  return static_cast<int32_t>(place >= 0 ? place + 0.5f : place - 0.5f);
}

}  // namespace sheet_motion
