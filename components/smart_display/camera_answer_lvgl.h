// The board's picture tick and what an answer with a picture does: the camera's, the alert's, the screensaver's.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the governor (pressure_lvgl.h), which only tells it what to give up.
// What proves it: tests/test_camera.py, tests/test_alert.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// loader asks, loads and breaks off (pictures_round), and the screensaver follows.
inline void camera_tick() {
  pressure_tick(esphome::millis());
#ifdef SD_MOD_DOORBELL
  doorbell::tick(esphome::millis());  // its chime, how long ago it rang, the close of a ring nobody answered
#endif
#ifdef SD_MOD_CALL
  call::tick(esphome::millis());  // its ring, its timer, the end shown for a moment
#endif
  pictures_collect();  // copies no card shows any more, and the oldest over the budget
  live_tiles_round();
  pictures_round();
  saver_tick(esphome::millis());
}

inline void alert_picture_clear() {
  if (alert_picture) { lv_obj_delete(alert_picture); alert_picture = nullptr; }
  if (alert_frame_icon) lv_obj_remove_flag(alert_frame_icon, LV_OBJ_FLAG_HIDDEN);
  // Its picture goes with it, a download on its way breaks off, and the frame's buffer is freed.
  loader.release(owners::ALERT);
  slot_key[static_cast<int>(picture_loader::Slot::THUMB)].clear();
  if (camera_thumb.release) camera_thumb.release();
}

// alert_show: the card gets its frame when the app announced a camera for it just before. A new alert closes the camera.
inline void alert_prepare() {
  camera_close();
  alert_picture_clear();
  const bool with_image = camera_supported() && alert_frame && !alert_announced.empty() &&
                          esphome::millis() - alert_announced_at < camera_view::PENDING_MS;
  alert_camera = with_image ? alert_announced : std::string();
  alert_shown_at = esphome::millis();
  alert_url.clear();
  alert_announced.clear();
  if (alert_frame) {
    if (with_image) lv_obj_remove_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
  }
  alert_place(with_image);
}

// alert_dismiss: the frame goes, and so does its image.
inline void alert_clear() {
  alert_picture_clear();
  alert_camera.clear();
  alert_url.clear();
  if (alert_frame) lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
}

inline std::string camera_tag();
// The app's answer: a link, or "" when it has no picture. It goes to the picture that asked (picture_loader::answer), and
// the round right after starts the download, rather than the next tick (firmware 0.2.73+): the answer is most of the wait.
// A stream the app made before the view asked (a ring's, the op doorbell's `l`): opened at once in the view's room,
// which the link learns from the open (?room=WxH), where asking for one took 1.3 s of a ring's 1.54 s to its first
// picture (docs/PLATFORM_PLAN.md 4.9). A link that fails leaves the view to ask, as every view does.
inline void camera_link_now(const std::string &url) {
  if (!camera_root || camera.stream.live || !live_view::is_stream(url) || live_view::is_own(url) || !live_wanted()) return;
  const auto room = live_area();
  live_begin(url + (url.find('?') == std::string::npos ? "?" : "&") + "room=" + std::to_string(room.w) + "x" +
             std::to_string(room.h));
}
inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url, uint32_t number) {
  if (!camera_supported()) return;
  const uint32_t now = esphome::millis();
  if (view == "plive") {  // a live place of a plugin tile (plugin API 0.17), found by its question's number
    live_place_answer(number, url);
    return;
  }
  if (view == "full" || view == "saver") {
    // "saver" (firmware 0.29.0+): the screensaver's picture, into the full view it opened without its keys.
    if (!camera_root || camera.entity != entity || (view == "saver") != saver_camera) return;
    // A stream of pictures (live_view.h), for the view that asked for one; a still goes the way every picture goes.
    if (view == "full" && live_view::is_stream(url)) {
      if (live_wanted() && !camera.stream.live) live_begin(url);
      return;
    }
    loader.answer(camera_tag(), url, now);
  } else if (view == "cover") {  // a media card's or tile's album cover (firmware 0.2.64+)
    if (url.empty()) ESP_LOGI("camera", "no cover for %s", entity.c_str());
    loader.answer("cover|" + entity, url, now);
#ifdef SD_MOD_VACUUM_CARD
  } else if (view == "vmap") {  // a vacuum card's map (module vacuum)
    if (url.empty()) ESP_LOGI("camera", "no map for %s", entity.c_str());
    loader.answer("vmap|" + entity, url, now);
#endif
  } else if (view == "lib") {  // the covers of a page of a player's library (firmware 0.24.0+)
    media_library::art_answer(entity, url);
  } else if (view == "live") {  // a tile's own picture (tile_picture.h), found by its question's number
    tile_picture_answer(number, url, now);
  } else if (view == "pcard") {  // the pictures of a plugin's card over the page (plugin API 0.13)
    plugin_host::card_picture_answer(entity, url, number);
  } else if (view == "psaver") {  // the pictures of a plugin's screensaver (plugin API 0.14)
    plugin_host::saver_picture_answer(entity, url, number);
  } else if (url.empty()) {  // announced before its alert
    alert_announced = entity;
    alert_announced_at = now;
    return;
  } else {
    // The alert's link comes by itself; alert_want hands it to the loader.
    if (entity != alert_camera || !alert_frame || lv_obj_has_flag(alert_frame, LV_OBJ_FLAG_HIDDEN)) return;
    alert_url = url;
  }
  pictures_round();
}

// LVGL's image widget is only built for a board whose profile draws images (LV_USE_IMAGE, features/camera.yaml); the CYD's has none.
// `radius` rounds the picture's corners (the alert's, firmware 0.2.73+): LVGL 9.5's software renderer clips an image
// to its own radius row by row with a one-row mask (radius_only in lv_draw_sw_img.c), without a layer; clip_corner on
// the frame would draw the frame into a layer of its size instead.
inline void camera_show(lv_obj_t *parent, lv_obj_t *&picture, lv_image_dsc_t *source, bool fresh_pixels, int32_t radius = 0) {
#if LV_USE_IMAGE
  if (!source || !source->data) return;
  if (!picture) {
    picture = lv_image_create(parent);
    lv_obj_remove_flag(picture, LV_OBJ_FLAG_CLICKABLE);
    if (radius > 0) lv_obj_set_style_radius(picture, radius, LV_PART_MAIN);
    lv_image_set_src(picture, source);
    lv_obj_center(picture);
    return;
  }
  if (!fresh_pixels && lv_image_get_src(picture) == source) return;
  // The same buffer with new pixels, or another picture (the screensaver's next track, a map's other focus). LVGL keeps no decoded copy of an RGB565 image (its image cache is off in
  // ESPHome's build), so drawing the area again shows them.
  lv_image_set_src(picture, source);
  lv_obj_invalidate(picture);
#else
  (void) parent; (void) picture; (void) source; (void) fresh_pixels; (void) radius;
#endif
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
