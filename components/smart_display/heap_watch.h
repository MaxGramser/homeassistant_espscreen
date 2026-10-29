// What asks the internal RAM for room. On an ESP32-P4 screen ESPHome builds with CONFIG_SPIRAM_USE_CAPS_ALLOC: every
// plain malloc, new, std::string and std::vector takes internal RAM, however large, and TLS does too
// (MBEDTLS_INTERNAL_MEM_ALLOC). A reTerminal D1001 settles at about 250 KB of it free, yet its lowest since boot read
// 162 KB five minutes after a boot and 20 KB after a few hours (2026-10-24), with nothing in its log to say what took
// the rest; a Tab5 of a dev tester that restarts every few minutes read 38 KB.
//
// So the screen watches two things and keeps them where a reset leaves them (.noinit), the way loop_record keeps the
// main loop at the watchdog:
// - the lowest the internal RAM has been since boot (ESP-IDF's own counter, heap_caps_get_minimum_free_size, which
//   walks nothing), logged each time it falls another STEP, with the moment, so the log around it says what ran;
// - every allocation that found no room (heap_caps_register_failed_alloc_callback): its size, the memory it asked for,
//   the function and the task that asked, and how much internal RAM was free then. The hook runs in the task that
//   asked, with the heap short, so it only writes the record; the main loop logs it.
// The next boot hands both on: `*** INTERNAL RAM ON PREVIOUS BOOT ***` with a `Lowest:` and a `Failed:` line, logged
// with ESPHome's config dump, which every log subscriber asks for (the troubleshooting report's too: reports.py
// CRASH_LINE keeps the lines with a crash).
//
// One ask fails on every P4 screen with Screen camera's video, and is no failure: Espressif's H.264 encoder (esp_h264,
// esp_h264_enc_hw_param.c) asks internal RAM first for its reference frame, a whole frame (1382464 bytes at 1280x720),
// more than the chip has, and takes PSRAM right after. Every report of such a screen began with it (a Tab5,
// TR-2M2KX9, 2026-10-27). So an ask of the encoder's own caps (internal, cache aligned) larger than all internal RAM
// is counted apart, as one that fell back to PSRAM; should PSRAM fail it too, that second ask is a failure as any
// other.
#pragma once
#include <cstdint>

namespace heap_watch {

constexpr uint32_t STEP = 16 * 1024;  // the lowest is logged again once it falls this much further
constexpr uint32_t EVERY_MS = 250;    // how often the main loop reads the counter

// The encoder's first ask, which falls back to PSRAM by itself: its caps are ESP-IDF's MALLOC_CAP_INTERNAL and
// MALLOC_CAP_CACHE_ALIGNED (esp_h264_alloc.c adds the second), and it could never fit in the internal RAM there is.
constexpr uint32_t FIRST_TRY_CAPS = (1u << 11) | (1u << 19);
inline bool falls_back(uint32_t size, uint32_t caps, uint32_t internal_total) {
  return caps == FIRST_TRY_CAPS && size > internal_total;
}

// The lowest seen, and whether it fell far enough below the last one logged to be logged again.
struct LowWater {
  uint32_t logged = 0;
  bool due(uint32_t lowest, uint32_t step) {
    if (logged != 0 && lowest + step > logged) return false;
    logged = lowest;
    return true;
  }
};

// At boot: takes the previous boot's record and starts this one's (the hook included).
void setup();
// Every turn of the main loop: the lowest and the failures since the last turn, logged.
void tick(uint32_t now);
// With the config dump: the previous boot's record, and this boot's so far.
void dump();

}  // namespace heap_watch
