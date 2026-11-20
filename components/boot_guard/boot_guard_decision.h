#pragma once
// The decision of the boot guard, apart from everything that touches a chip, so tests/test_boot_guard.cpp runs it on a
// computer. components/boot_guard/README.md says what the guard is for.
#include <cstdint>

namespace esphome::boot_guard {

struct Config {
  uint32_t confirm_after_ms;  // the firmware must have run this long before it may be confirmed
  uint32_t deadline_ms;       // not confirmed by now: go back to the firmware from before
  bool require_api_client;    // a native API client must have connected at least once since boot
};

enum class Decision : uint8_t { WAIT, CONFIRM, ROLLBACK };

// Confirm only when every condition holds at once. Confirming wins over the deadline: a firmware that meets them on
// the very tick of the deadline is a good one. Past the deadline without them, roll back.
inline Decision decide(uint32_t uptime_ms, bool wifi_up, bool api_seen, const Config &cfg) {
  const bool api_ok = !cfg.require_api_client || api_seen;
  if (uptime_ms >= cfg.confirm_after_ms && wifi_up && api_ok)
    return Decision::CONFIRM;
  if (uptime_ms >= cfg.deadline_ms)
    return Decision::ROLLBACK;
  return Decision::WAIT;
}

// What is missing, for the log line that says why a rollback happens (nullptr when nothing is).
inline const char *missing(uint32_t uptime_ms, bool wifi_up, bool api_seen, const Config &cfg) {
  if (!wifi_up)
    return "Wi-Fi is not connected";
  if (cfg.require_api_client && !api_seen)
    return "no API client has connected since boot";
  if (uptime_ms < cfg.confirm_after_ms)
    return "uptime is below confirm_after";
  return nullptr;
}

}  // namespace esphome::boot_guard
