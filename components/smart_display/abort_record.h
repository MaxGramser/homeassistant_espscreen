// What an abort said. A failed assert or an abort() restarts a screen through ESP-IDF's panic_abort, which prints the
// details to the serial port alone: ESPHome's crash record keeps `Reason: Abort` and a backtrace that ends in the
// assert's own frames, and ESP-IDF builds its asserts compact, so the details are the assert's address and nothing
// says who called what failed. The home reTerminal D1001 restarted that way in the stress test of 2026-10-25 with
// nothing more to go on.
//
// So the link step wraps panic_abort (`--wrap=panic_abort`, __init__.py). The wrapper, in IRAM, copies the details into
// memory a reset leaves alone (.noinit) with the aborting task's name and the code addresses on its own stack (as
// loop_record reads the main loop's), then calls the real one. An abort nearly always comes in a task with the flash
// cache on; one with the cache off would fault in the stack scan, and ESP-IDF's panic handler restarts the screen all
// the same. The next boot takes the record over (take, at setup) and logs it with ESPHome's config dump, which every
// log subscriber asks for: `*** ABORT ON PREVIOUS BOOT ***`, a `Details:` line and `AT0:` and on, with the addr2line
// line to decode them. The troubleshooting report keeps them with the crash (reports.py CRASH_LINE).
#pragma once

namespace abort_record {

constexpr int TEXT = 160;  // what is kept of the details, enough for an assert's function, file, line and expression
constexpr int MOST = 32;   // code addresses kept from the aborting task's stack (ESP-IDF builds asserts as an address)

// At boot: takes over the record the last abort left, and forgets it where the reset left it.
void take();
// With the config dump: logs the record taken at boot, if there was one.
void report();

}  // namespace abort_record
