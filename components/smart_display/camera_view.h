#pragma once
// The rhythm of asking for a picture and loading it again (firmware 0.2.57+): the constants every owner of a picture
// keeps to, through picture_loader.h (one route for every picture) and runtime_tiles.h (the full view, the live tiles).
// Pure, free of LVGL and ESPHome, so tests/test_camera_view.cpp checks the rules on a PC.
//
// The app answers `esphome.screen_camera` with a link to a picture it keeps fresh (docs/PICTURES.md, picture_service.py).
// The rhythm is fixed rather than as fast as the Wi-Fi allows: a picture every four seconds, every time, reads as
// smoother than one after three seconds and the next after five. Never a queue: a slow load makes the next one later.
#include <cstdint>

namespace camera_view {
constexpr uint32_t REFRESH_MS = 4000;      // from the start of one load to the start of the next: a steady rhythm
constexpr uint32_t GAP_MS = 800;           // at least this long between the end of one load and the next
constexpr uint32_t ASK_AGAIN_MS = 10000;   // a link that does not come (or an app without an image) is asked for again
// A picture the app draws itself (a map) is always there to be had, so an answer without one is a failure on the way
// (firmware 0.30.0+): asked for again after ASK_AGAIN_MS, then twice as long each time, up to this.
constexpr uint32_t ASK_AGAIN_MAX_MS = 300000;
constexpr uint8_t MAX_FAILURES = 3;        // a link that fails this often in a row is old: ask for a new one
constexpr uint32_t PENDING_MS = 20000;     // an alert's camera announced this long before the alert still belongs to it
// A page on its way past (firmware 0.3.2+): no picture starts loading until the pages have stood still this long, so a
// download never lands between two quick page turns and holds the next one up. Asking the app for a link is an event
// and costs the screen nothing; only the download waits.
constexpr uint32_t SETTLE_MS = 800;
inline bool settled(uint32_t now, uint32_t last_turn) { return now - last_turn >= SETTLE_MS; }
// Whether the tiles are there to be seen (firmware 0.40.0+, GitHub #161), and so whether their pictures (a page's live
// pictures, a media card's cover) keep loading: a screen in use, or one in standby that still shows its dimmed tiles. A
// screensaver over them (the clock too) hides them, and below SEEN_LEVEL % of brightness nobody reads a picture. Before,
// standby stopped every picture, and a camera that stood still on a dimmed screen looked like a camera that stopped.
constexpr int SEEN_LEVEL = 5;
inline bool tiles_seen(bool awake, bool screensaver, int standby_level) {
  return awake || (!screensaver && standby_level >= SEEN_LEVEL);
}
}  // namespace camera_view
