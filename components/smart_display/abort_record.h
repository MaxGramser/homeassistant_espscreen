// What an abort said. A failed assert or an abort() restarts a screen through ESP-IDF's panic_abort, which prints the
// details ("assert failed: vTaskDelete tasks.c:1234 (pxTCB)", "abort() was called at PC 0x...") to the serial port
// alone: ESPHome's crash record keeps `Reason: Abort` and a backtrace that ends in the assert's own frames, and over the
// network nothing says which assert it was. The home reTerminal D1001 restarted that way twice in an hour of the
// stress test (2026-10-25) with nothing more to go on.
//
// So the link step wraps panic_abort (`--wrap=panic_abort`, __init__.py): the wrapper copies the details into memory a
// reset leaves alone (.noinit) and calls the real one, from IRAM. Where the abort happens is nearly always a task with
// the flash cache on (a failed assert, an abort()); there the wrapper also keeps the code addresses on that task's own
// stack, which ESP-IDF's compact asserts (the details are the assert's address alone) and ESPHome's backtrace (the
// assert's own frames) leave out: who called what failed. An abort with the cache off would fault in that scan, and
// ESP-IDF's panic handler then restarts the screen all the same. The next boot takes the
// record over (take, at setup) and logs it with ESPHome's config dump, which every log subscriber asks for, as
// `*** ABORT ON PREVIOUS BOOT ***`, a `Details:` line and `AT0:` and on, the aborting task's stack read as loop_record
// reads the main loop's, the troubleshooting report keeps with the crash (reports.py
// CRASH_LINE).
#pragma once

namespace abort_record {

constexpr int TEXT = 160;  // what is kept of the details, enough for an assert's function, file, line and expression
constexpr int MOST = 32;   // code addresses kept from the aborting task's stack (ESP-IDF builds asserts as an address)

// At boot: takes over the record the last abort left, and forgets it where the reset left it.
void take();
// With the config dump: logs the record taken at boot, if there was one.
void report();

}  // namespace abort_record
