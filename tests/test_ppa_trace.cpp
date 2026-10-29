// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_ppa_trace.cpp -o /tmp/test_ppa_trace && /tmp/test_ppa_trace
//
// The PPA watch's rule (components/smart_display/ppa_trace.h): a call asked more than NEVER_MS ago and not back is the
// one that never came back; one that came back, failed, or is younger is not, and the clock may wrap in between.
#include "../components/smart_display/ppa_trace.h"
#include <cassert>
#include <cstdio>

using namespace ppa_trace;

static Call call(uint32_t seq, uint32_t at_ms, uint8_t state) {
  Call c{};
  c.seq = seq;
  c.at_ms = at_ms;
  c.state = state;
  return c;
}

int main() {
  Call calls[CALLS] = {};
  // An empty ring, and one of calls that came back or failed however long ago: none.
  assert(never_back(calls, CALLS, 100000) == nullptr);
  calls[0] = call(1, 1000, BACK);
  calls[1] = call(2, 1000, FAILED);
  assert(never_back(calls, CALLS, 100000) == nullptr);

  // A call still out, younger than NEVER_MS and exactly NEVER_MS old: not yet.
  calls[2] = call(3, 1000, ASKED);
  assert(never_back(calls, CALLS, 1000 + NEVER_MS - 1) == nullptr);
  assert(never_back(calls, CALLS, 1000 + NEVER_MS) == nullptr);
  // A millisecond more: that one.
  assert(never_back(calls, CALLS, 1000 + NEVER_MS + 1) == &calls[2]);

  // Asked just before the millisecond clock wraps: its age counts across the wrap.
  Call wrapped[CALLS] = {};
  wrapped[5] = call(7, 0xFFFFFF00u, ASKED);
  assert(never_back(wrapped, CALLS, 100) == nullptr);
  assert(never_back(wrapped, CALLS, 0xFFFFFF00u + NEVER_MS + 1) == &wrapped[5]);

  // Asked a moment after the watch took its clock (the streams keep asking while it walks the ring): younger than
  // now, not 4294967 s old. A Tab5 aborted a sound boot on exactly this (TR-NQRE3E, "-5 ms").
  Call fresh[CALLS] = {};
  fresh[3] = call(9, 100005, ASKED);
  assert(never_back(fresh, CALLS, 100000) == nullptr);
  fresh[3] = call(9, 0x00000002u, ASKED);  // just past the wrap, the watch's clock just before it
  assert(never_back(fresh, CALLS, 0xFFFFFFFEu) == nullptr);

  printf("test_ppa_trace: ok\n");
  return 0;
}
