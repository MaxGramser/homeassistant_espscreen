// The camera live, full screen, on a P4.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in live_view.h.
// What proves it: tests/test_live_view.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- The camera live, full screen, on a P4 (live_view.h) ----
inline void camera_note_text(const char *text);
// Whether anything LVGL draws after `owner` overlaps its room (x, y, w, h: the screen as LVGL lays it out), in LVGL's own
// order of drawing: on the way from `owner` up to its screen or layer, every sibling that comes after it; then, for
// something on a screen, the screen no longer on the glass or anything on the top layer; and anything on the system
// layer. A live picture writes past LVGL, so it may only write where nothing of LVGL's lies over it, without a list of
// what may: the update's progress, an alert, the camera full screen, the screensaver, and a card opened on the page
// itself, as a lamp's colour card is, which an earlier rule of the two layers alone missed (2026-10-10, the D1001).
// An object without a look of its own (a plain, clear container) is not in the way by itself; what it holds may be.
inline const char *drawn_over_by = nullptr;  // what lay over a live picture last, for the log
inline bool drawn_over_covers(lv_obj_t *o, int x, int y, int w, int h, int depth = 0) {
  if (!o || lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN) || lv_obj_get_style_opa(o, LV_PART_MAIN) == LV_OPA_TRANSP) return false;
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  if (!(a.x1 < x + w && a.x2 >= x && a.y1 < y + h && a.y2 >= y && a.x2 >= a.x1 && a.y2 >= a.y1)) return false;
  const bool plain = lv_obj_check_type(o, &lv_obj_class) && lv_obj_get_style_bg_opa(o, LV_PART_MAIN) <= LV_OPA_MIN &&
                     lv_obj_get_style_border_width(o, LV_PART_MAIN) == 0 && lv_obj_get_style_outline_width(o, LV_PART_MAIN) == 0 &&
                     lv_obj_get_style_shadow_width(o, LV_PART_MAIN) == 0;
  if (!plain) return true;
  if (depth >= 6) return true;
  for (uint32_t i = 0; i < lv_obj_get_child_count(o); ++i)
    if (drawn_over_covers(lv_obj_get_child(o, i), x, y, w, h, depth + 1)) return true;
  return false;
}
inline bool drawn_over(lv_obj_t *owner, int x, int y, int w, int h) {
  drawn_over_by = nullptr;
  if (!owner) return true;
  lv_obj_t *sys = lv_layer_sys(), *top = lv_layer_top();
  lv_obj_t *at = owner;
  while (lv_obj_t *parent = lv_obj_get_parent(at)) {
    const uint32_t count = lv_obj_get_child_count(parent);
    for (uint32_t i = static_cast<uint32_t>(lv_obj_get_index(at)) + 1; i < count; ++i)
      if (drawn_over_covers(lv_obj_get_child(parent, i), x, y, w, h)) {
        drawn_over_by = parent == top ? "the top layer" : parent == sys ? "the system layer" : "something on the page";
        return true;
      }
    at = parent;
  }
  // `at` is the screen or the layer `owner` is on.
  if (at != top && at != sys) {
    if (at != lv_screen_active()) { drawn_over_by = "another screen"; return true; }
    for (uint32_t i = 0; top && i < lv_obj_get_child_count(top); ++i)
      if (drawn_over_covers(lv_obj_get_child(top, i), x, y, w, h)) { drawn_over_by = "the top layer"; return true; }
  }
  if (at != sys)
    for (uint32_t i = 0; sys && i < lv_obj_get_child_count(sys); ++i)
      if (drawn_over_covers(lv_obj_get_child(sys, i), x, y, w, h)) { drawn_over_by = "the system layer"; return true; }
  return false;
}
// The room below the top bar: the back key and the name stay LVGL's, on the view's black, never over the picture.
inline live_view::Rect live_area() {
#ifdef SD_MOD_CALL
  if (call::shown()) return call::area();
#endif
#ifdef SD_MOD_DOORBELL
  // A ring's view (module doorbell): the room beside or above its keys.
  if (doorbell::shown()) return doorbell::area();
#endif
  const int top = detail_bar::bottom();
  return {0, top, overlay_card::screen_width(), overlay_card::screen_height() - top};
}
// A camera opened by itself (not a map, an image or the screensaver), on a board that streams, until its streams
// failed TRIES times for this opening.
inline bool live_wanted() {
  if (!live_view::full_view() || !camera.open() || camera.entity.rfind("camera.", 0) != 0 || camera_map_index >= 0 ||
      saver_camera || !camera.stream.may() || boot_trial::on(esphome::millis()))
    return false;
  const auto area = live_area();
  return !drawn_over(camera_root, area.x, area.y, area.w, area.h);
}
inline uint32_t camera_opened_at = 0;  // when the view opened, for the log of a live camera's first picture
inline bool camera_ram_watched = false;  // the lowest internal RAM is watched from the view's opening (camera_ram_low)
// The lowest internal RAM since the view opened, in KB, and the watch ends; -1 when none ran.
inline bool camera_ram_watch() {
#ifdef USE_ESP32
  return heap_caps_monitor_local_minimum_free_size_start() == ESP_OK;
#else
  return false;
#endif
}
inline int camera_ram_low() {
  if (!camera_ram_watched) return -1;
  camera_ram_watched = false;
#ifdef USE_ESP32
  const size_t low = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
  heap_caps_monitor_local_minimum_free_size_stop();
  return static_cast<int>(low / 1024);
#else
  return -1;
#endif
}
// The camera's sound: on, until someone mutes it; muted stays muted for every camera until the screen starts again.
inline bool camera_muted = false;
inline lv_obj_t *camera_sound_key = nullptr;
inline lv_obj_t *view_key(lv_obj_t *parent, int size, const char *glyph, bool over_map);
inline void camera_sound_glyph() {
#ifdef SD_MOD_DOORBELL
  if (doorbell::shown()) { doorbell::sound_changed(); return; }
#endif
#ifdef SD_MOD_CALL
  if (call::shown()) { call::sound_changed(); return; }
#endif
  if (!camera_sound_key) return;
  lv_label_set_text(lv_obj_get_child(camera_sound_key, 0), camera_muted ? "\U000F0581" : "\U000F057E");  // volume-off, -high
}
// The key at the right of the view's top bar, once the camera's sound comes (Event::SOUND): a tap mutes it or lets it in.
inline void camera_sound_show() {
  if (!camera_root || camera_sound_key) return;
#ifdef SD_MOD_DOORBELL
  if (doorbell::shown()) return;  // a ring's view has its sound key from the start
#endif
#ifdef SD_MOD_CALL
  if (call::shown()) return;  // a call's keys are its own
#endif
  const auto slot = detail_bar::right_slot(camera_root);
  camera_sound_key = view_key(camera_root, slot.h, camera_muted ? "\U000F0581" : "\U000F057E", false);
  lv_obj_set_pos(camera_sound_key, slot.x, slot.y);
  lv_obj_add_event_cb(camera_sound_key, [](lv_event_t *) {
    camera_muted = !camera_muted;
    live_view::mute(camera.stream.handle, camera_muted);
    camera_sound_glyph();
  }, LV_EVENT_SHORT_CLICKED, nullptr);
}
// Until the camera is live (live_view.h, "Until it is live"): from its first picture, a still, the firmware's spinner
// turns at the right of the view's top bar, and goes with the first live picture (Event::LIVE). One place for the two:
// the sound key comes there once the spinner has gone (its sound comes with the live stream anyway), so neither moves
// the other aside; a stream that starts again while the key is there turns no spinner. LVGL draws it: the bar lies
// above the stream's room, so nothing of it is over the picture.
inline lv_obj_t *camera_warm_spinner = nullptr;
inline bool camera_sound_waiting = false;  // the sound came while the spinner turned: its key follows at LIVE
inline bool camera_warming() { return camera_warm_spinner && !lv_obj_has_flag(camera_warm_spinner, LV_OBJ_FLAG_HIDDEN); }
inline void camera_warm(bool on) {
  if (!on || !camera_root || !camera_title || camera_sound_key) {
    if (camera_warm_spinner) lv_obj_add_flag(camera_warm_spinner, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  const bool large = ui::large();
  const int size = ui::px(large ? 30 : 20);
  if (!camera_warm_spinner) {
    camera_warm_spinner = spinner_create(camera_root, size, ui::px(large ? 4 : 3));
    if (!camera_warm_spinner) return;
    lv_obj_set_style_arc_color(camera_warm_spinner, theme::color(theme::CAMERA_TRACK), LV_PART_MAIN);
  }
#ifdef SD_MOD_DOORBELL
  // A ring's view has its close key at the edge: the spinner turns beside it.
  if (doorbell::shown()) { doorbell::spinner_place(camera_warm_spinner, size); lv_obj_remove_flag(camera_warm_spinner, LV_OBJ_FLAG_HIDDEN); return; }
#endif
#ifdef SD_MOD_CALL
  if (call::shown()) return;  // no spinner in a call: its keys and the ground are there at once
#endif
  const auto slot = detail_bar::right_slot(camera_root);
  lv_obj_set_pos(camera_warm_spinner, slot.x + (slot.w - size) / 2, slot.y + (slot.h - size) / 2);
  lv_obj_remove_flag(camera_warm_spinner, LV_OBJ_FLAG_HIDDEN);
}
inline void live_tiles_halt();
// The full view's link while the streams of the page under it end, and since when (live_view::ViewWait); live_tick
// opens it once they are gone.
inline live_view::ViewWait view_wait;
inline void live_begin(const std::string &link) {
  const uint32_t now = esphome::millis();
  const bool was_waiting = view_wait.waiting();
  const uint32_t since = view_wait.since;
  if (!was_waiting) ESP_LOGI("camera", "live link %u ms after the camera opened", (unsigned) (now - camera_opened_at));
  // The live tiles and places of the page under the view stop before the view's stream exists, not at the next
  // drawing (live_stop_covered): a tile's task could still copy its picture into the frame buffer after LVGL had drawn
  // the view over the page, and a band of it stayed under the view's top bar until the view's first picture (2026-10-24,
  // the reTerminal D1001, two live tiles). A page under a full view never streams anyway.
  live_tiles_halt();
  // And the view's stream opens once theirs are gone, never beside them: one connection at a time (live_view::ending,
  // read after the halt, and live_view::ViewWait, which keeps its own copy of the link).
  const bool ending = live_view::ending();
  const auto begun = view_wait.begin(link, now, ending, live_view::beside());
  if (!begun.open) return;
  const std::string &url = begun.url;
  if (ending)
    ESP_LOGW("camera", "the page's streams did not end in %u ms: the full view opens beside them",
             (unsigned) live_view::ViewWait::WAIT_MS);
  if (was_waiting) ESP_LOGI("camera", "live link opened %u ms later, after the page's streams ended", (unsigned) (now - since));
  // The role its sound claims: a ring's view as the ring, a call's as the call, any other as a camera's sound
  // (live_view::view_role).
  bool ring = false, call_up = false;
#ifdef SD_MOD_DOORBELL
  ring = doorbell::shown();
#endif
#ifdef SD_MOD_CALL
  call_up = call::shown();
#endif
  camera.stream.opened(live_view::open(url, live_area(), live_view::Look{}, live_view::has_speaker(),
                                       live_view::view_role(ring, call_up)));
  if (camera.stream.live) {
    if (camera_muted) live_view::mute(camera.stream.handle, true);
    return;
  }
  // No room for another stream, or no memory: the view takes the stills of every board (ViewStream::opened).
  ESP_LOGW("camera", "the full view could not stream (no room for another stream, or no memory): it shows stills");
  pictures_round();
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
