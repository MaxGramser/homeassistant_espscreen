#pragma once
#include <cstdint>

namespace esphome::smart_display::voice_timing {
// loop() takes a clock snapshot before callbacks or the network/audio tasks may
// publish newer timestamps. A newer stamp has zero age, not UINT32_MAX age.
// All voice deadlines are far below half the 32-bit millis() range.
inline uint32_t elapsed(uint32_t now, uint32_t since) {
  const auto delta = static_cast<int32_t>(now - since);
  return delta > 0 ? static_cast<uint32_t>(delta) : 0;
}
}  // namespace esphome::smart_display::voice_timing
