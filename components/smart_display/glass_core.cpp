// The glass every panel kind shares (glass.h says what and why): the one-writer lock with LVGL's refresh hooks, the count
// of who keeps a stream waiting, and the rooms LVGL keeps out of. What a panel kind adds, the panel ESPHome's display made
// and its frame buffer, is its own file's: glass_dsi.cpp for a P4's MIPI-DSI panel, glass_rgb.cpp for an S3's RGB panel.
// Moved out of glass_dsi.cpp as it was: the lock's reach, the keep-out's rule and the invalidations are unchanged.
#include "glass.h"
#if (defined(GLASS_DSI) || defined(GLASS_RGB)) && defined(SCREEN_PICTURES)
#include <atomic>

#include "esphome/components/lvgl/lvgl_esphome.h"
#include "esphome/core/log.h"
#include "lvgl.h"
#include "lvgl_private.h"  // lv_inv_area, lv_area_intersect and the display's list, which LVGL 9 keeps out of lvgl.h

#include <esp_attr.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

namespace glass {

static const char *const TAG = "glass";

// ---- LVGL, and the lock ----
static esphome::lvgl::LvglComponent *lvgl = nullptr;
// One writer on the glass at a time (glass.h): made at bind, on the main loop, before any task.
static SemaphoreHandle_t lock = nullptr;

void bind(esphome::lvgl::LvglComponent *component) {
  lvgl = component;
  if (!lock) lock = xSemaphoreCreateRecursiveMutex();
}
bool bound() { return lvgl != nullptr; }
int turn() { return lvgl ? static_cast<int>(lvgl->get_rotation()) : 0; }

// ---- One writer at a time ----
// Who holds it, for the count of who keeps a stream waiting (Held below): LVGL's refresh, a stream, or another writer
// (a still's decode, a page's picture ahead). Set and cleared by the holder only, at its outermost hold.
static std::atomic<uint8_t> holder{NOBODY};
static int depth = 0;  // the holder's own nesting; only the task that holds the lock touches it
void hold() {
  if (!lock) return;
  xSemaphoreTakeRecursive(lock, portMAX_DELAY);
  if (depth++ == 0) holder.store(OTHER, std::memory_order_relaxed);
}
bool try_hold() {
  if (!lock || xSemaphoreTakeRecursive(lock, 0) != pdTRUE) return false;
  if (depth++ == 0) holder.store(OTHER, std::memory_order_relaxed);
  return true;
}
void release() {
  if (!lock) return;
  if (--depth == 0) holder.store(NOBODY, std::memory_order_relaxed);
  xSemaphoreGiveRecursive(lock);
}
// ---- Who keeps a stream waiting (glass.h, Held) ----
// LVGL's side on the main loop only; the streams' waits and the PPA's calls from any task, so all of it atomic.
struct Count {
  std::atomic<uint32_t> n{0}, us{0}, most_us{0};
  void add(uint32_t t) {
    n.fetch_add(1, std::memory_order_relaxed);
    us.fetch_add(t, std::memory_order_relaxed);
    uint32_t most = most_us.load(std::memory_order_relaxed);
    while (t > most && !most_us.compare_exchange_weak(most, t, std::memory_order_relaxed)) {
    }
  }
  void take(uint32_t &n_out, uint32_t &us_out, uint32_t &most_out) {
    n_out = n.exchange(0, std::memory_order_relaxed);
    us_out = us.exchange(0, std::memory_order_relaxed);
    most_out = most_us.exchange(0, std::memory_order_relaxed);
  }
};
static Count refreshes, flushes, turns, behind_lvgl, behind_stream, behind_other;
static std::atomic<bool> flushing{false};
static std::atomic<TaskHandle_t> flusher{nullptr};
static int64_t refresh_from = 0, flush_from = 0;

static void hold_glass(lv_event_t *) {
  hold();
  holder.store(LVGL, std::memory_order_relaxed);
  refresh_from = esp_timer_get_time();
}
static void release_glass(lv_event_t *) {
  refreshes.add(static_cast<uint32_t>(esp_timer_get_time() - refresh_from));
  release();
}
static void flush_start(lv_event_t *) {
  flusher.store(xTaskGetCurrentTaskHandle(), std::memory_order_relaxed);
  flush_from = esp_timer_get_time();
  flushing.store(true, std::memory_order_release);
}
static void flush_finish(lv_event_t *) {
  flushing.store(false, std::memory_order_relaxed);
  flushes.add(static_cast<uint32_t>(esp_timer_get_time() - flush_from));
}
IRAM_ATTR Holder holder_now() { return static_cast<Holder>(holder.load(std::memory_order_relaxed)); }
IRAM_ATTR bool flushing_now() { return flushing.load(std::memory_order_relaxed); }
static bool holding = false;  // LVGL holds the glass while it refreshes, from the first stream or still on and for good
bool watch() {
  if (!lv_display_get_default() || !lock) return false;
  if (!holding) {
    lv_display_add_event_cb(lv_display_get_default(), hold_glass, LV_EVENT_REFR_START, nullptr);
    lv_display_add_event_cb(lv_display_get_default(), release_glass, LV_EVENT_REFR_READY, nullptr);
    lv_display_add_event_cb(lv_display_get_default(), flush_start, LV_EVENT_FLUSH_START, nullptr);
    lv_display_add_event_cb(lv_display_get_default(), flush_finish, LV_EVENT_FLUSH_FINISH, nullptr);
    holding = true;
  }
  return true;
}
uint32_t hold_counted() {
  const uint8_t before = holder.load(std::memory_order_relaxed);
  const int64_t asked = esp_timer_get_time();
  hold();
  if (depth == 1) holder.store(STREAM, std::memory_order_relaxed);
  const uint32_t waited = static_cast<uint32_t>(esp_timer_get_time() - asked);
  (before == LVGL ? behind_lvgl : before == STREAM ? behind_stream : behind_other).add(waited);
  return waited;
}
void engine_took(uint32_t us) {
  if (flushing.load(std::memory_order_acquire) && flusher.load(std::memory_order_relaxed) == xTaskGetCurrentTaskHandle())
    turns.add(us);
}
Held held_since() {
  Held h;
  uint32_t n = 0, lvgl_waits = 0, stream_waits = 0;
  refreshes.take(h.refreshes, h.refresh_us, h.refresh_most_us);
  flushes.take(h.flushes, h.flush_us, h.flush_most_us);
  turns.take(n, h.turn_us, h.turn_most_us);
  behind_lvgl.take(lvgl_waits, h.behind_lvgl_us, h.behind_lvgl_most_us);
  behind_stream.take(stream_waits, h.behind_stream_us, h.behind_stream_most_us);
  uint32_t other_waits = 0;
  behind_other.take(other_waits, h.behind_other_us, h.behind_other_most_us);
  h.waits = lvgl_waits + stream_waits + other_waits;
  return h;
}

// ---- LVGL stays out of a live picture's room ----
// A card on the page behind the view that changes (a sensor's new value), or a page's own redraw around a live tile,
// has LVGL draw that area again, and what LVGL has there (the view's black, a tile's still with its spinner and name)
// would cover the live picture until its next one. So what LVGL is about to draw is cut against where the picture of
// every stream that streams lies (its spot: a full view's picture may leave room beside it, which stays LVGL's), once,
// as it starts drawing (LV_EVENT_RENDER_START: its areas joined, nothing drawn yet): what lies outside a room stays, in
// pieces, what lies inside goes. That one place sees every way LVGL comes to draw there: an area as it comes, one it
// had before a stream's first picture, two it joined into one, and the whole glass, which LVGL draws when more areas
// come in one frame than its list holds. A filter of each area as it came missed the last three (2026-10-10, the D1001:
// a tile's spinner and name over its live picture after the camera full screen closed). Each piece goes through the
// display's own rounding (ESPHome's draw_rounding), as LVGL's own areas do. Once a room is disarmed nothing is cut for
// it, and LVGL draws its room again.
struct RoomState {
  bool used = false;
  Rect area;
  // Where the stream's last picture lies (LVGL's coordinates). Written by the task as it copies a picture, read by the
  // main loop: only that is kept from LVGL, which draws the rest of the room itself, and when it moves (a camera's
  // still, then its stream at another size) LVGL draws where it lay again (follow).
  portMUX_TYPE spot_lock = portMUX_INITIALIZER_UNLOCKED;
  Rect spot;
  Rect spot_told;  // the main loop's: the spot it last saw
  // LVGL is kept out from the stream's first picture on (set by the task just before it copies one): until then LVGL
  // draws as ever, a spinner turning while the camera comes.
  std::atomic<bool> armed{false};
};
static RoomState rooms[MAX_ROOMS];
static bool filtering = false;
static lv_area_t lv_rect(const Rect &r) { return {r.x, r.y, r.x + r.w - 1, r.y + r.h - 1}; }
static Rect spot_of(RoomState &s) {
  taskENTER_CRITICAL(&s.spot_lock);
  const Rect spot = s.spot;
  taskEXIT_CRITICAL(&s.spot_lock);
  return spot;
}
static void set_spot(RoomState &s, const Rect &spot) {
  taskENTER_CRITICAL(&s.spot_lock);
  s.spot = spot;
  taskEXIT_CRITICAL(&s.spot_lock);
}
// What LVGL keeps out of: where the stream's last picture lies.
static lv_area_t room_of(RoomState &s) {
  const Rect spot = spot_of(s);
  return lv_rect(spot.empty() ? s.area : spot);
}
static void invalidate(const lv_area_t &part) { lv_inv_area(lv_display_get_default(), &part); }
static bool covered(const lv_area_t &a) {
  for (auto &o : rooms) {
    if (!o.used || !o.armed) continue;
    const lv_area_t room = room_of(o);
    lv_area_t common;
    if (lv_area_intersect(&common, &a, &room)) return true;
  }
  return false;
}
// `area` less every streaming room, as up to MAX_PIECES rectangles; -1 when that takes more.
constexpr int MAX_PIECES = LV_INV_BUF_SIZE;
static lv_area_t pieces[MAX_PIECES], next_pieces[MAX_PIECES], kept[LV_INV_BUF_SIZE];
static int cut_out(const lv_area_t &area) {
  int count = 1;
  pieces[0] = area;
  for (auto &s : rooms) {
    if (!s.used || !s.armed) continue;
    const lv_area_t room = room_of(s);
    int made = 0;
    for (int i = 0; i < count; ++i) {
      const lv_area_t r = pieces[i];
      lv_area_t common;
      if (!lv_area_intersect(&common, &r, &room)) {
        if (made == MAX_PIECES) return -1;
        next_pieces[made++] = r;
        continue;
      }
      const lv_area_t parts[4] = {{r.x1, r.y1, r.x2, room.y1 - 1}, {r.x1, room.y2 + 1, r.x2, r.y2},
                                  {r.x1, common.y1, room.x1 - 1, common.y2}, {room.x2 + 1, common.y1, r.x2, common.y2}};
      const bool there[4] = {r.y1 < room.y1, r.y2 > room.y2, r.x1 < room.x1, r.x2 > room.x2};
      for (int k = 0; k < 4; ++k) {
        if (!there[k]) continue;
        if (made == MAX_PIECES) return -1;
        next_pieces[made++] = parts[k];
      }
    }
    count = made;
    for (int i = 0; i < count; ++i) pieces[i] = next_pieces[i];
  }
  return count;
}
static void keep_out(lv_event_t *) {
  lv_display_t *display = lv_display_get_default();
  int count = 0;
  bool whole = false;  // more pieces than LVGL's list holds
  for (uint32_t i = 0; i < display->inv_p && !whole; ++i) {
    if (display->inv_area_joined[i]) continue;
    const lv_area_t &area = display->inv_areas[i];
    if (!covered(area)) {
      kept[count++] = area;  // as LVGL had it, rounded on its way in
      continue;
    }
    const int made = cut_out(area);
    if (made < 0 || count + made > LV_INV_BUF_SIZE) {
      whole = true;
      break;
    }
    for (int k = 0; k < made; ++k) kept[count++] = pieces[k];
  }
  if (whole) {
    // Then the whole glass less the rooms; should even that take too many, LVGL draws what it has, a frame of its own
    // over the live pictures.
    const lv_area_t whole_glass = {0, 0, lv_display_get_horizontal_resolution(display) - 1,
                                   lv_display_get_vertical_resolution(display) - 1};
    const int made = cut_out(whole_glass);
    if (made < 0) return;
    count = 0;
    for (int k = 0; k < made; ++k) kept[count++] = pieces[k];
  }
  for (int i = 0; i < count; ++i) {
    lv_display_send_event(display, LV_EVENT_INVALIDATE_AREA, &kept[i]);  // rounding twice changes nothing
    display->inv_areas[i] = kept[i];
    display->inv_area_joined[i] = 0;
  }
  display->inv_p = count;
}
static void filter_when_rooms() {
  bool any = false;
  for (auto &s : rooms) any = any || s.used;
  if (any && !filtering && lv_display_get_default()) {
    lv_display_add_event_cb(lv_display_get_default(), keep_out, LV_EVENT_RENDER_START, nullptr);
    filtering = true;
  } else if (!any && filtering) {
    lv_display_remove_event_cb_with_user_data(lv_display_get_default(), keep_out, nullptr);
    filtering = false;
  }
}

Room reserve(const Rect &area) {
  for (int i = 0; i < MAX_ROOMS; ++i) {
    RoomState &s = rooms[i];
    if (s.used) continue;
    s.used = true;
    s.area = area;
    set_spot(s, Rect{});
    s.spot_told = Rect{};
    s.armed = false;
    filter_when_rooms();
    return i;
  }
  ESP_LOGW(TAG, "no room for another stream");
  return -1;
}
static RoomState *room_at(Room room) { return room >= 0 && room < MAX_ROOMS && rooms[room].used ? &rooms[room] : nullptr; }
void place(Room room, const Rect &spot) {
  RoomState *s = room_at(room);
  if (!s) return;
  set_spot(*s, spot);
  s->armed = true;  // from now on LVGL draws nothing here
}
bool armed(Room room) {
  RoomState *s = room_at(room);
  return s && s->armed;
}
void disarm(Room room, bool under_glass) {
  RoomState *s = room_at(room);
  if (!s) return;
  // A copy on its way finishes; none starts after this, and LVGL draws there again.
  if (under_glass) hold();
  const bool was_armed = s->armed.exchange(false);
  if (under_glass) release();
  if (was_armed) invalidate(lv_rect(s->area));
}
void follow(Room room) {
  RoomState *s = room_at(room);
  if (!s || !s->armed) return;
  // Its picture lies elsewhere now, or at another size: LVGL draws where it lay again (but where it lies now).
  const Rect spot = spot_of(*s);
  if (!(spot == s->spot_told)) {
    if (!s->spot_told.empty()) invalidate(lv_rect(s->spot_told));
    s->spot_told = spot;
  }
}
void give_back(Room room) {
  RoomState *s = room_at(room);
  if (!s) return;
  s->armed = false;
  s->used = false;
  filter_when_rooms();
}
void redraw_all() {
  lv_display_t *display = lv_display_get_default();
  if (!display) return;
  const lv_area_t whole = {0, 0, lv_display_get_horizontal_resolution(display) - 1,
                           lv_display_get_vertical_resolution(display) - 1};
  invalidate(whole);
}

}  // namespace glass
#endif
