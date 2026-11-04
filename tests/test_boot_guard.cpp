// The boot guard's decision (components/boot_guard/boot_guard_decision.h): when a new firmware image is confirmed,
// when it goes back to the one before, and when it only waits.
#include "components/boot_guard/boot_guard_decision.h"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace esphome::boot_guard;

int main() {
  const Config strict{180000, 900000, true};
  const Config no_api{180000, 900000, false};

  // Early on nothing is decided, whatever is up.
  assert(decide(0, true, true, strict) == Decision::WAIT);
  assert(decide(179999, true, true, strict) == Decision::WAIT);
  assert(decide(179999, false, false, strict) == Decision::WAIT);

  // From confirm_after on: confirmed only with Wi-Fi and (when required) an API client seen.
  assert(decide(180000, true, true, strict) == Decision::CONFIRM);
  assert(decide(600000, true, true, strict) == Decision::CONFIRM);
  assert(decide(180000, false, true, strict) == Decision::WAIT);   // Wi-Fi is down now
  assert(decide(180000, true, false, strict) == Decision::WAIT);   // no client ever
  assert(decide(180000, false, false, strict) == Decision::WAIT);

  // Without require_api_client the client is not asked for.
  assert(decide(180000, true, false, no_api) == Decision::CONFIRM);
  assert(decide(180000, false, false, no_api) == Decision::WAIT);

  // The deadline: anything still missing rolls back, from the deadline on.
  assert(decide(899999, false, false, strict) == Decision::WAIT);
  assert(decide(900000, false, false, strict) == Decision::ROLLBACK);
  assert(decide(900000, true, false, strict) == Decision::ROLLBACK);
  assert(decide(900000, false, true, strict) == Decision::ROLLBACK);
  assert(decide(900000, false, false, no_api) == Decision::ROLLBACK);
  assert(decide(5000000, false, true, strict) == Decision::ROLLBACK);

  // Meeting the conditions on the tick of the deadline, or after it, still confirms.
  assert(decide(900000, true, true, strict) == Decision::CONFIRM);
  assert(decide(900001, true, true, strict) == Decision::CONFIRM);

  // A client that came and went still counts (the guard latches api_seen), Wi-Fi must be up right now.
  assert(decide(300000, true, true, strict) == Decision::CONFIRM);

  // A short deadline and a confirm_after of zero.
  const Config quick{0, 1000, true};
  assert(decide(0, true, true, quick) == Decision::CONFIRM);
  assert(decide(0, true, false, quick) == Decision::WAIT);
  assert(decide(1000, true, false, quick) == Decision::ROLLBACK);

  // The reason given for a rollback names what was missing, Wi-Fi first.
  assert(std::strcmp(missing(900000, false, false, strict), "Wi-Fi is not connected") == 0);
  assert(std::strcmp(missing(900000, true, false, strict), "no API client has connected since boot") == 0);
  assert(missing(900000, true, true, strict) == nullptr);
  assert(std::strcmp(missing(100, true, true, strict), "uptime is below confirm_after") == 0);

  std::puts("test_boot_guard: ok");
  return 0;
}
