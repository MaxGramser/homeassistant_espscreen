// The last calls to the P4's PPA, kept across a restart. A copy the engine never finishes (ppa_guard.h: the 2D-DMA's
// DIG-734, espressif/esp-idf #19023 and #19096) leaves no error and no log: the task that asked waits for good, the
// main loop behind it when LVGL held the glass, and the task watchdog restarts the screen with a record that names only
// the wait (loop_record.h: ppa_do_operation). A reTerminal D1001 restarted that way while its top bar was held
// (2026-10-27), and only a trace of the calls themselves named the copy that never came back: the hold line's 336x6,
// turned a quarter.
//
// So every call through the guard's wrap (ppa_guard.cpp) is noted in a ring of the last few, in memory a reset leaves
// alone: its block, angle, where it lands, the pieces the guard cut it into, the task that asked and whether it came
// back. The next boot takes the ring over and logs it with ESPHome's config dump, as loop_record does, so a log
// subscriber and the troubleshooting report see it next to the main loop's record: a call that never came back is the
// one the screen stopped on.
//
// And a call that never comes back ends the boot by name: a task of its own, outside every task that waits for the
// engine, looks at the ring each second, and a call still out after NEVER_MS aborts the screen with "PPA copy never
// finished" and the call (abort_record.h keeps those words), rather than freezing until the task watchdog restarts it
// with a record that names nobody. Nothing brings the engine back without a restart (espressif/esp-idf #19096), so a
// restart it stays; the copies this firmware makes take milliseconds, and the slowest wait for the engine measured, a
// camera's frame halved behind two live tiles on a Guition 10.1, took 0.74 s.
//
// The watch ran in ESP-IDF's esp_timer task at first, which every esp_timer callback of the firmware and its drivers
// shares. On a Guition 10.1 it caught a forced hang (368x66 turned 270, espressif/esp-idf #19023's block) after 3.1 s
// from the main loop and 3.8 s from a task like a stream's (2026-10-27); on a Tab5 of a dev tester (TR-2M2KX9, the
// same day) a live tile's copy of 618x307 never came back and the screen stood still until the task watchdog, 20 s,
// the watch silent: that task never got to it there. So the watch has a task of its own now, and its words say how the
// esp_timer task stood (loop_record.h keeps that task's stack at a task watchdog too).
#pragma once
#include <cstdint>

namespace ppa_trace {

constexpr uint32_t NEVER_MS = 3000;
constexpr uint32_t CALLS = 32;  // the calls the ring keeps

// One call as the ring keeps it.
enum : uint8_t { ASKED = 1, BACK = 2, FAILED = 3 };
struct Call {
  uint32_t seq, at_ms;
  uint16_t w, h, out_x, out_y;  // the input block, and where it lands in the output picture
  uint8_t angle;                // counter-clockwise, in quarters
  int8_t pieces;                // the guard's plan: 1 whole, more in pieces, 0 the block as it was
  uint8_t state;
  char task[13];
};

// The call among `calls` that was asked more than NEVER_MS before `now_ms` and is not back, or nullptr. The age is
// signed: the watch takes `now_ms` once and then walks the ring while the streams keep asking, so a call noted after
// that moment is younger than now, not 4294967 s old (a Tab5 aborted a sound boot on one, TR-NQRE3E: "-5 ms"). The
// millisecond clock wrapping in between still counts right, as the difference is taken modulo 2^32 first.
inline const Call *never_back(const Call *calls, uint32_t count, uint32_t now_ms) {
  for (uint32_t i = 0; i < count; ++i) {
    const Call &call = calls[i];
    if (__atomic_load_n(&call.state, __ATOMIC_ACQUIRE) != ASKED) continue;
    const int32_t age_ms = static_cast<int32_t>(now_ms - call.at_ms);
    if (age_ms > static_cast<int32_t>(NEVER_MS)) return &call;
  }
  return nullptr;
}

// At boot: takes over the calls the last boot left, if it left any, starts the ring again and the watch.
void take();
// With the config dump: logs the calls taken at boot, the newest last.
void report();

}  // namespace ppa_trace
