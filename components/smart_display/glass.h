#pragma once
// The glass: the panel as a surface (docs/PICTURE_ARCHITECTURE.md, section 3.1). What the panel is as ESP-IDF made it
// for ESPHome's display and LVGL lays it out (its size, its pixel format, its turn), the frame buffer a task may write
// past LVGL where there is one, the one-writer lock that LVGL holds for each refresh and a stream's task for each copy,
// and the rooms LVGL keeps out of while a stream writes there. The glass knows pictures, streams, the decoder and the
// PPA not at all: live_view.cpp (the streams) and picture_engine (the copies) ask it.
//
// On an ESP32-P4 with a MIPI-DSI panel (USE_LIVE_VIEW and pictures) the glass is direct: glass_dsi.cpp has the panel
// picked up as ESP-IDF makes it (a linker wrap of esp_lcd_new_panel_dpi), the frame buffer, the lock and LVGL's refresh
// hooks, the keep-out of LVGL's areas, the panel's underrun counter and the wrap that shortens every PPA client's bursts
// so the panel keeps its share of the memory bus. Every other board, the host renders and the editor's preview have
// no direct glass: direct() is false and the rest are inline stubs that cost no flash.
//
// Two writers reach the frame buffer, and the lock covers both. LVGL's refresh (on a turned glass through ESPHome's own
// PPA turn of each strip into a buffer in PSRAM, then the panel's DMA copy) holds it from LV_EVENT_REFR_START to
// REFR_READY; a stream's task holds it for each decode and each copy. Without it a stream's first picture could land
// while LVGL was still drawing the still and the name it had decided on before the stream armed, and that drawing then
// lay over the picture until the next one (2026-10-12, the D1001). It is also the one user of the 2D-DMA at a time: the
// decoder, the PPA and the panel's copy of LVGL's strips all go through it, and two of them at once from different
// tasks is what hangs in ESP-IDF's reports on the P4 (espressif/esp-idf #18999, #19108). Recursive: a stream closes
// under it too, inside a refresh when something covers it (live_stop_covered, on REFR_START).
//
// What a PC can check is pure: a rectangle of the screen on a turned panel (on_panel, tests/test_live_view.cpp).
#include <cstdint>
// USE_LIVE_VIEW comes with ESPHome's defines (smart_display/__init__.py); a PC test has none and builds without it.
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif

namespace esphome::lvgl {
class LvglComponent;
}

namespace glass {

// A rectangle of the screen as LVGL lays it out.
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  bool empty() const { return w <= 0 || h <= 0; }
  bool operator==(const Rect &o) const { return x == o.x && y == o.y && w == o.w && h == o.h; }
};
// Where a rectangle of the screen as LVGL lays it out lies on a panel of pw x ph, LVGL turned `turn` degrees clockwise:
// exactly ESPHome's own sums for a flushed area (LvglComponent::draw_buffer_), so a picture lands where LVGL would
// have drawn it.
inline Rect on_panel(const Rect &r, int turn, int pw, int ph) {
  switch (turn) {
    case 90: return {pw - r.y - r.h, r.x, r.h, r.w};
    case 180: return {pw - r.x - r.w, ph - r.y - r.h, r.w, r.h};
    case 270: return {r.y, ph - r.x - r.w, r.h, r.w};
    default: return r;
  }
}

// ---- The panel's share of the memory bus ----
// The DSI bridge reads the frame buffer from PSRAM without pause, a frame every 16 ms; when another DMA (the PPA, the
// JPEG decoder, the DMA2D that copies what LVGL drew) holds the bus too long, the bridge runs dry and the panel shows
// a frame of blue, its colour for no data. So every PPA client on the screen moves in bursts of this many bytes instead
// of ESP-IDF's 128, and the bus turns to the bridge between bursts (lvgl/lvgl #9590 took the same way for the same
// underrun): the streams' own clients and a plugin's ask for it, and ESPHome's LVGL, which turns every flush of a turned
// glass with the PPA, gets it through the wrap of ppa_register_client in glass_dsi.cpp. The burst is the engine's
// (picture_engine::limits().burst_bytes).

// The panel as ESP-IDF made it: its size, and whether its frame buffer is RGB565 (the one format a task writes).
struct Panel {
  int w = 0, h = 0;
  bool rgb565 = false;
};
// A room LVGL keeps out of while a stream writes there; -1 for none.
using Room = int;
constexpr int MAX_ROOMS = 8;
// The FreeRTOS priority a writer waits for the glass at: a stream's task runs at it, and a still's download waits at it
// in turn with them (picture_engine::decode), as a mutex goes to its highest waiter.
constexpr unsigned WRITER_PRIORITY = 5;

#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
// LVGL, which says how the glass is turned (smart_display/__init__.py binds it at boot).
void bind(esphome::lvgl::LvglComponent *lvgl);
Panel panel();      // 0 x 0 while ESP-IDF made no panel for LVGL
int turn();         // LVGL's rotation now, degrees clockwise: read every time, the app can stand a screen up at run time
bool direct();      // a frame buffer a task may write past LVGL: a panel ESP-IDF made with RGB565, and LVGL bound
void *frame_buffer();  // that buffer, panel().w x panel().h RGB565, found as needed; nullptr without
// One writer at a time: LVGL for the whole of each refresh, a task for each decode and each copy. Recursive.
void hold();
void release();
// LVGL holds the glass while it refreshes, from now on and for good (the hooks on REFR_START and REFR_READY). False
// while LVGL has no display yet.
bool watch();
// A room for a stream: LVGL draws it as ever until the stream places its first picture (place), from then on LVGL draws
// nothing of the spot the picture lies on until the room is disarmed, and draws the rest of the room itself. The
// keep-out of LVGL's areas (on LV_EVENT_RENDER_START) is on while any room exists.
Room reserve(const Rect &area);
// The stream's picture lies at `spot` (its whole card, or a full view's picture as large as fits its room) from now on:
// the room is armed. From the stream's task, under hold().
void place(Room room, const Rect &spot);
bool armed(Room room);
// The stream writes the room no more: LVGL draws the room's area again when it was armed. `under_glass` takes the lock
// around it (a stream closed while its task may still copy); a stream whose task has ended needs none.
void disarm(Room room, bool under_glass);
// The main loop: the picture lies elsewhere now, or at another size (a camera's still, then its stream at another size),
// so LVGL draws where it lay again.
void follow(Room room);
// The room goes; the keep-out goes with the last room.
void give_back(Room room);
// LVGL draws the whole glass again (a full view's stream gone for good, its room drawn again while its task may still
// have been busy with its last picture).
void redraw_all();
// The underrun flag read and counted (every 50 ms, from the streams' tick), and how often the panel ran dry since boot.
void tick();
uint32_t misses();
// Who keeps a stream waiting for the glass (live_view's 10 s report, PLATFORM_PLAN 4.10): LVGL's refreshes, how many
// and how long it held the glass, in all and the longest; how much of that went to flushing what it drew (the turn on
// the PPA of a turned glass, then the panel's copy and its wait for the copy's end) and how much of the flushing to the
// PPA's turn alone; and the streams' waits for the glass, behind LVGL's refresh, another stream or another writer (a
// still's decode, a page's picture fetched ahead). Counted since the last call, which starts the count again (the main
// loop).
struct Held {
  uint32_t refreshes = 0, flushes = 0, refresh_us = 0, refresh_most_us = 0, flush_us = 0, flush_most_us = 0,
           turn_us = 0, turn_most_us = 0;
  uint32_t waits = 0, behind_lvgl_us = 0, behind_lvgl_most_us = 0, behind_stream_us = 0, behind_stream_most_us = 0,
           behind_other_us = 0, behind_other_most_us = 0;
};
Held held_since();
// A task asks for the glass (hold), as hold() does, and says how long it waited for it.
uint32_t hold_counted();
// A copy of the picture engine came back after `us` (its wrap, any task): counted as the turn while LVGL flushes on
// that task.
void engine_took(uint32_t us);
#else
inline void bind(esphome::lvgl::LvglComponent *) {}
inline Panel panel() { return {}; }
inline int turn() { return 0; }
inline bool direct() { return false; }
inline void *frame_buffer() { return nullptr; }
inline void hold() {}
inline void release() {}
inline bool watch() { return false; }
inline Room reserve(const Rect &) { return -1; }
inline void place(Room, const Rect &) {}
inline bool armed(Room) { return false; }
inline void disarm(Room, bool) {}
inline void follow(Room) {}
inline void give_back(Room) {}
inline void redraw_all() {}
inline void tick() {}
inline uint32_t misses() { return 0; }
struct Held {
  uint32_t refreshes = 0, flushes = 0, refresh_us = 0, refresh_most_us = 0, flush_us = 0, flush_most_us = 0,
           turn_us = 0, turn_most_us = 0;
  uint32_t waits = 0, behind_lvgl_us = 0, behind_lvgl_most_us = 0, behind_stream_us = 0, behind_stream_most_us = 0,
           behind_other_us = 0, behind_other_most_us = 0;
};
inline Held held_since() { return {}; }
inline uint32_t hold_counted() { return 0; }
inline void engine_took(uint32_t) {}
#endif

}  // namespace glass
