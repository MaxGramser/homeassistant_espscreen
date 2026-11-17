#pragma once
// The rhythm of asking for a picture and loading it again (firmware 0.2.57+): the constants every owner of a picture
// keeps to, through picture_loader.h (one route for every picture) and runtime_tiles.h (the full view, the live tiles).
// Pure, free of LVGL and ESPHome, so tests/test_camera_view.cpp checks the rules on a PC.
//
// The app answers `esphome.screen_camera` with a link to a picture it keeps fresh (docs/PICTURES.md, picture_service.py).
// The rhythm is fixed rather than as fast as the Wi-Fi allows: a picture every four seconds, every time, reads as
// smoother than one after three seconds and the next after five. Never a queue: a slow load makes the next one later.
#include <cstddef>
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
constexpr bool settled(uint32_t now, uint32_t last_turn) { return now - last_turn >= SETTLE_MS; }
// Whether a picture may start loading this round (pictures_round): never under a finger, and not while the pages turn.
constexpr bool may_load(bool pressed, uint32_t now, uint32_t last_turn) { return !pressed && settled(now, last_turn); }
// Whether the tiles are there to be seen (firmware 0.40.0+, GitHub #161), and so whether their pictures (a page's live
// pictures, a media card's cover) keep loading: a screen in use, or one in standby that still shows its dimmed tiles. A
// screensaver over them (the clock too) hides them, and below SEEN_LEVEL % of brightness nobody reads a picture. Before,
// standby stopped every picture, and a camera that stood still on a dimmed screen looked like a camera that stopped.
constexpr int SEEN_LEVEL = 5;
constexpr bool tiles_seen(bool awake, bool screensaver, int standby_level) {
  return awake || (!screensaver && standby_level >= SEEN_LEVEL);
}
// Which of the tiles' pictures may load now (card_picture_wants, tile_picture_waiting). Those on the glass, while the
// tiles are there to be seen (tiles_seen, so also on a dimmed screen without a screensaver, GitHub #161) and no card
// or full view stands over them. tests/test_camera_view.cpp.
constexpr bool pictures_on_glass(bool tiles_seen, bool card_open, bool view_open) {
  return tiles_seen && !card_open && !view_open;
}
// Those of a kept page out of sight, fetched ahead: only while the screen is in use, no pages are being prepared, the
// store has room to spare (under three quarters of its budget: over it a page out of sight lets its pictures go, and
// fetching them again would only send them round) and the screen is not busy (the governor's background, pressure.h).
constexpr bool pictures_ahead(bool awake, bool kept, bool preparing, size_t used, size_t budget, int background_pressure) {
  return awake && kept && !preparing && used < budget / 4 * 3 && background_pressure == 0;
}

// Where a picture card's name lies (render_camera_card) and where the live picture's copy of it lies (live_name): left,
// as wide as the card's content, one line of the tile's font high, at the bottom. One place for both, so the name over a
// live picture lies where the card's own did; a copy of the card's label once lay halfway up (a wallbox, 2026-10-28).
struct NameBox { int x, y, w, h; };
constexpr NameBox name_box(int width, int height, int line_h) { return {0, height - line_h, width, line_h}; }

}  // namespace camera_view
