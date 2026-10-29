// The main loop at the task watchdog. ESPHome's crash record keeps the fault location of the task that was running on
// the crashed core, and when the task watchdog restarts a screen because the main loop (loopTask) stopped feeding it,
// that task is nearly always the idle one: the record then says `esp_cpu_wait_for_intr` and nothing of what the main
// loop waited on. Two P4 screens of a dev tester restarted that way on 2026-10-23 and 24 (TR-4EFBDE, TR-FNFW9J), both
// with the esp_hosted SDIO wedge in the log (espressif/esp-hosted-mcu #197) and nothing to prove the chain.
//
// So the watchdog's own hook (`esp_task_wdt_isr_user_handler`, which ESP-IDF calls in the watchdog's interrupt before
// it aborts) takes the main loop's stack as it stands, blocked or running, and keeps every word of it that points at
// code, newest first, in memory the reset leaves alone. The next boot takes them over and logs them as `LOOP0: 0x...`
// lines with ESPHome's config dump, which every log subscriber asks for, as ESPHome hands its own crash record to the
// first subscriber (logged at boot they reached the serial port alone, never a subscriber over the API); the troubleshooting report keeps them with the crash (reports.py CRASH_LINE) and decodes
// them with the ELF, and `addr2line -pfiaC -e firmware.elf <addresses>` does the same by hand. On a RISC-V chip the
// first two are the saved frame's MEPC and RA, the rest a scan of the stack: return addresses of the callers with,
// between them, whatever else on the stack happens to look like code, which addr2line names as `??` and the report
// drops. Read the chain for the names that make sense together.
//
// The same hook keeps ESP-IDF's esp_timer task too: its state (running, ready, blocked, suspended) and the code on its
// stack, logged as `TIMER0: 0x...` lines after the main loop's. That task runs the PPA watch (ppa_trace.h), which
// restarts a screen within four seconds when a copy of the picture engine never comes back; on a Tab5 of a dev tester
// (TR-2M2KX9, 2026-10-27) a live tile's copy never came back and the task watchdog restarted the screen 20 s later
// instead, the watch silent, where on a Guition 10.1 the same watch caught a forced hang after 3.1 s. Its stack at the
// next such watchdog says whether it waited for its next timer, as it should, or sat in a callback that never returned.
#pragma once
#include <cstdint>

namespace loop_record {

constexpr int MOST = 24;        // addresses kept, enough for the chain from the wait to the component that waited
constexpr int MOST_TIMER = 12;  // the esp_timer task's: a callback and its callers

// The words from `from` (the top of the stack, the newest) up to `end` that `is_code` takes for code, at most `most`.
template <typename IsCode>
inline int scan(const uint32_t *from, const uint32_t *end, uint32_t *out, int most, IsCode is_code) {
  int n = 0;
  for (const uint32_t *p = from; p < end && n < most; ++p)
    if (is_code(*p)) out[n++] = *p;
  return n;
}

// At boot: takes over the record the last task watchdog left, and forgets it where the reset left it.
void take();
// With the config dump: logs the record taken at boot, if there was one.
void report();

}  // namespace loop_record
