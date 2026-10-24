// What an abort said. A failed assert or an abort() restarts a screen through ESP-IDF's panic_abort, which prints the
// details ("assert failed: vTaskDelete tasks.c:1234 (pxTCB)", "abort() was called at PC 0x...") to the serial port
// alone: ESPHome's crash record keeps `Reason: Abort` and a backtrace that ends in the assert's own frames, and over the
// network nothing says which assert it was. The home reTerminal D1001 restarted that way twice in an hour of the
// stress test (2026-10-25) with nothing more to go on.
//
// So the link step wraps panic_abort (`--wrap=panic_abort`, __init__.py): the wrapper copies the details into memory a
// reset leaves alone (.noinit) and calls the real one. It runs where the abort happens, an interrupt or a task, with
// the flash cache perhaps off: it sits in IRAM, reads nothing from flash and only copies bytes. The next boot takes the
// record over (take, at setup) and logs it with ESPHome's config dump, which every log subscriber asks for, as
// `*** ABORT ON PREVIOUS BOOT ***` and a `Details:` line the troubleshooting report keeps with the crash (reports.py
// CRASH_LINE).
#pragma once

namespace abort_record {

constexpr int TEXT = 160;  // what is kept of the details, enough for an assert's function, file, line and expression

// At boot: takes over the record the last abort left, and forgets it where the reset left it.
void take();
// With the config dump: logs the record taken at boot, if there was one.
void report();

}  // namespace abort_record
