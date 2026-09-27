#pragma once
// A camera image full screen (firmware 0.2.57+, Guition): when to ask ESP Screen Manager for a link and when to load it
// again. Pure bookkeeping, free of LVGL and ESPHome, so tests/test_camera_view.cpp can check it on a PC; runtime_tiles.h
// draws the view and the board's online_image loads the link.
//
// The app answers `esphome.screen_camera` with a link to a BMP it keeps fresh (screen_manager/app/camera_feed.py).
// Loading shares the main loop with touch and drawing, so the view loads one image at a time and leaves time free after
// each. The rhythm is fixed rather than as fast as the Wi-Fi allows: a picture every four seconds, every time, reads as
// smoother than one after three seconds and the next after five. Never a queue: a slow load makes the next one later.
#include <cstdint>
#include <string>

namespace camera_view {
constexpr uint32_t REFRESH_MS = 4000;      // from the start of one load to the start of the next: a steady rhythm
constexpr uint32_t GAP_MS = 800;           // at least this long between the end of one load and the next
constexpr uint32_t ASK_AGAIN_MS = 10000;   // a link that does not come (or an app without an image) is asked for again
constexpr uint8_t MAX_FAILURES = 3;        // a link that fails this often in a row is old: ask for a new one
constexpr uint32_t PENDING_MS = 20000;     // an alert's camera announced this long before the alert still belongs to it
// A page on its way past (firmware 0.3.2+): no picture starts loading until the pages have stood still this long, so a
// download never lands between two quick page turns and holds the next one up. Asking the app for a link is an event
// and costs the screen nothing; only the download waits.
constexpr uint32_t SETTLE_MS = 800;
inline bool settled(uint32_t now, uint32_t last_turn) { return now - last_turn >= SETTLE_MS; }

struct Feed {
  std::string entity, url;
  uint32_t asked_at = 0, started_at = 0, finished_at = 0;
  bool asked = false, loading = false, shown = false, empty = false;  // empty: the app said it has no image
  // once (firmware 0.2.64+): an album cover on the media card. It loads one time per link and stays; a new cover comes
  // with a new link (the card asks again when Home Assistant's picture changes), never on a clock.
  bool once = false, loaded = false;  // loaded: this link's image is on screen
  // every (firmware 0.2.77+): the live pictures on a page's camera tiles load at their own pace, 5 to 30 s, where the
  // camera full screen keeps REFRESH_MS.
  uint32_t every = REFRESH_MS;
  uint8_t failures = 0;
  // A picture kept from before (picture_store.h) that is still good until this moment (firmware 0.3.2+): the feed asks
  // for its link as usual but loads nothing sooner. 0: no picture kept.
  uint32_t kept_until = 0;

  void open(const std::string &camera, bool one_load = false, uint32_t every_ms = REFRESH_MS) { *this = Feed{}; entity = camera; once = one_load; every = every_ms; }
  bool open() const { return !entity.empty(); }
  // Decorative motion waits for the initial image attempt. A failed or missing
  // image must not hold readable fallback text still forever. Retries pause it
  // again before loading; an unchanged completed image does not restart it.
  bool animation_ready() const { return !loading && (loaded || empty || finished_at != 0); }

  // A cover the app has none of (or an app that knows no covers) is asked for once: the card keeps its placeholder.
  // A feed whose app has no picture asks again at its own pace, never sooner than ASK_AGAIN_MS.
  bool should_ask(uint32_t now) const {
    if (once && empty) return false;
    const uint32_t again = empty && every > ASK_AGAIN_MS ? every : ASK_AGAIN_MS;
    return open() && !loading && url.empty() && (!asked || now - asked_at >= again);
  }
  void ask(uint32_t now) { asked = true; asked_at = now; }
  // The app's answer: a link, or none (no image from Home Assistant, or a camera this screen may not show).
  void link(const std::string &address) {
    url = address;
    empty = address.empty();
    failures = 0;
    started_at = finished_at = 0;
    loaded = false;
  }
  // The picture on the tiles came from the store, loaded at `loaded_at`: the next load waits for its turn.
  void resume(uint32_t loaded_at) { kept_until = (loaded_at ? loaded_at : 1) + every; }
  bool should_load(uint32_t now) const {
    if (!open() || loading || url.empty()) return false;
    if (kept_until && static_cast<int32_t>(now - kept_until) < 0) return false;
    if (!started_at) return true;
    if (once) return !loaded && now - finished_at >= GAP_MS;  // a failed load is tried again, a loaded one stays
    return now - started_at >= every && now - finished_at >= GAP_MS;
  }
  void start(uint32_t now) { loading = true; started_at = now ? now : 1; }
  void finish(uint32_t now, bool ok) {
    loading = false;
    finished_at = now;
    if (ok) { shown = true; loaded = true; failures = 0; return; }
    if (++failures >= MAX_FAILURES) { url.clear(); asked = false; failures = 0; }
  }
};
}  // namespace camera_view
