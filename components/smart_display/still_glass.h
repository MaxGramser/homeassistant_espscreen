#pragma once
// A still glass, the rules (docs/PAPER.md, "A still glass"): what a screen does differently when a change of its
// picture is a print that takes a part of a second (hw::Caps::still, a glass of ink). Nothing on such a glass runs by
// itself: no hand that steps each second, no bar that creeps, no ring that turns, no dot that travels. What counts
// time counts it in steps a print can keep up with, and says a time that is true at the moment it is printed.
//
// This file is the sums, free of LVGL and of the screen. screen_motion.h asks the capability record and stops what
// moves (still(), start()); still_glass_lvgl.h gives LVGL's own widgets their still form. tests/test_still_glass.cpp.
#include <cstdint>

namespace still_glass {

// A time that counts down, as a still glass shows it: whole minutes while more than one is left, and steps of ten
// seconds inside the last. Rounded up, so the glass never says less than there is, and is exact at the moment it
// changes: "5:00" stands from 5:00 down to 4:01, "0:50" from fifty seconds to forty-one.
constexpr uint32_t LAST_MINUTE_STEP = 10;
constexpr uint32_t counted(uint32_t seconds) {
  const uint32_t step = seconds > 60 ? 60 : LAST_MINUTE_STEP;
  return (seconds + step - 1) / step * step;
}

// A picture that is fetched again and again (a camera's still): one a minute, where a lit glass takes one every few
// seconds. Each is a print of a large part of the glass.
constexpr uint32_t PICTURE_MS = 60000;
constexpr uint32_t picture_every(uint32_t lit_ms) { return lit_ms > PICTURE_MS ? lit_ms : PICTURE_MS; }

}  // namespace still_glass
