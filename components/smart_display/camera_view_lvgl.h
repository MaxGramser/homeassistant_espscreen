// Camera images: what the full view, the alert card and the doorbell remember of a picture, and the alert card's
// layout. Opening the full view itself is full_view_lvgl.h.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in camera_view.h, camera_turn.h.
// What proves it: tests/test_camera_view.cpp, tests/test_camera.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
struct ImageHooks {
  std::function<void(const std::string &)> load;  // set the online_image's URL and download it
  std::function<void()> release;                  // free the decoded image
  std::function<lv_image_dsc_t *()> source;       // the decoded image for LVGL
  // The store took the decoded image's buffer over (picture_store::adopt): the slot lets go of it without freeing it.
  // Empty for a slot that cannot give its buffer away (the editor's WASM preview): the store gets a copy of its own.
  std::function<void()> hand_over;
  // A load that sends the ETag of a picture its owner already has, and the ETag of the slot's last picture: the same
  // bytes under another link come back 304 (docs/PICTURES.md, "Unchanged pictures"). Empty where the slot has no ETag.
  std::function<void(const std::string &url, const std::string &etag)> load_as;
  std::function<std::string()> etag;
};
// The page's strip (firmware 0.2.77+) comes through the third.
inline ImageHooks camera_full, camera_thumb, camera_live;
// What the full view shows (firmware 0.2.57+): a camera at its pace, a map, or the screensaver's picture. Its picture goes
// the way every picture goes (camera_want).
struct ViewPicture {
  std::string entity;
  uint32_t every = camera_view::REFRESH_MS;
  bool once = false;   // the screensaver's cover: one picture, and a new track is another
  bool shown = false;  // a picture of it is on the glass
  // Live on a P4 (live_view.h, live_spots::ViewStream): a stream runs or is about to, its link waiting while the last
  // stream ends, and the streams that failed for this opening (TRIES of them, and the view takes the stills of every board).
  live_spots::ViewStream stream;
  void open(const std::string &e) { *this = ViewPicture{}; entity = e; }
  bool open() const { return !entity.empty(); }
};
inline ViewPicture camera;
// What a picture costs this board (firmware 0.2.83+). Every picture goes the same way: the app sends a BMP of
// exactly the pixels the screen asked for and online_image decodes it to RGB565, so the room it takes is
// `width * height * 2`. ESPHome's RAMAllocator asks for that with PREFER_INTERNAL, which means a picture small
// enough to fit inside the chip takes memory the Wi-Fi link, the API and LVGL also want; a larger one lands in
// PSRAM and costs nothing inside. Which is why the number that decides a board's picture sizes is not how much
// PSRAM it has, but what one load does to both heaps. One line per stage of one load, for every kind of picture,
// so the four boards can be compared with the same instrument.
// `pixels` is what the picture holds when the screen knows it (a cover asks for its own square), 0 when only the
// app knows (a camera's box comes from the board shape); then only the heaps are worth reading.
// Free sizes only, no largest block (firmware 0.3.2+): finding the largest block walks every block of that heap with
// its lock held and the interrupts of this core off. On the 4-inch Guition a walk of the PSRAM took 1.7 ms with one
// page built and 2.3 ms with eight (2026-09-26, 3,300 and 4,600 blocks), while the RGB panel's bounce buffer is
// refilled by an interrupt on this core every 0.34 ms: every picture that loaded shifted a frame on the glass.
inline void picture_memory(const char *stage, const char *what, int pixels) {
#ifdef USE_ESP32
  ESP_LOGI("picture", "%s %s: %d px wants %d B; inside free=%u, psram free=%u", stage, what, pixels, pixels * 2,
           (unsigned) heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned) heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
#else
  (void) stage; (void) what; (void) pixels;
#endif
}
// Freeing the image waits for the next tick: ending a download under way can take a few hundred ms, and Back should
// show the page below at once.
inline bool camera_release_due = false;
inline lv_obj_t *camera_root = nullptr, *camera_picture = nullptr, *camera_note = nullptr, *camera_back = nullptr, *camera_title = nullptr;
// Turns in the middle until the first image is there (firmware 0.2.73+); a note (no image) takes its place.
inline lv_obj_t *camera_spinner = nullptr;
// The alert's image: the frame across the top of the card (features/camera.yaml), the camera the app announced for the
// next alert and the one the card on screen shows.
inline lv_obj_t *alert_frame = nullptr, *alert_picture = nullptr, *alert_frame_icon = nullptr;
// The parts of the alert card the shared tree draws (packages/core.yaml binds them at boot); alert_place puts them.
struct AlertParts {
  lv_obj_t *card = nullptr, *icon = nullptr, *title = nullptr, *subtitle = nullptr, *button = nullptr;
  lv_obj_t *label = nullptr, *button2 = nullptr, *label2 = nullptr;  // the words on the button, the second button (0.3.3+)
};
inline AlertParts alert_parts;
// Whether the alert on screen has a second button (show_alert_choice, firmware 0.3.3+); alert_show sets it.
inline bool alert_two_buttons = false;
// A button in a key colour of its own (theme::KEY_SWATCHES), or back to its paint for 0.
inline void alert_key(lv_obj_t *button, lv_obj_t *label, uint32_t key) {
  if (!button) return;
  if (!key) {
    lv_obj_remove_local_style_prop(button, LV_STYLE_BG_COLOR, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_remove_local_style_prop(button, LV_STYLE_BG_COLOR, LV_PART_MAIN | LV_STATE_PRESSED);
    if (label) lv_obj_remove_local_style_prop(label, LV_STYLE_TEXT_COLOR, LV_PART_MAIN | LV_STATE_DEFAULT);
    return;
  }
  lv_obj_set_style_bg_color(button, theme::rgb(key), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_obj_set_style_bg_color(button, theme::rgb(theme::key_pressed(key)), LV_PART_MAIN | LV_STATE_PRESSED);
  if (label) lv_obj_set_style_text_color(label, theme::rgb(theme::key_text(key)), LV_PART_MAIN | LV_STATE_DEFAULT);
}
// Lays the alert card out on this screen's glass (screen_alert::layout, firmware 0.2.103+), with room for a picture of
// `aw` x `ah` proportions or without one: at boot, when an alert comes (with a picture's frame of a camera's 16:9 until
// the picture is there), and once more when the picture arrives, for that picture's own proportions.
inline screen_alert::Layout alert_place(bool image, int aw = screen_alert::PICTURE_W, int ah = screen_alert::PICTURE_H) {
  const auto &p = alert_parts;
  if (!p.card || !p.icon || !p.title || !p.subtitle || !p.button) return {};
  const auto l = screen_alert::layout(overlay_card::screen_width(), overlay_card::screen_height(),
                                      lv_font_get_line_height(lv_obj_get_style_text_font(p.title, LV_PART_MAIN)),
                                      lv_font_get_line_height(lv_obj_get_style_text_font(p.subtitle, LV_PART_MAIN)),
                                      image && alert_frame, aw, ah);
  lv_obj_set_size(p.card, l.card_w, l.card_h);
  lv_obj_set_pos(p.icon, l.icon_x, l.icon_y);
  lv_obj_set_pos(p.title, l.text_x, l.title_y);
  lv_obj_set_size(p.title, l.text_w, l.title_h);
  lv_obj_set_pos(p.subtitle, l.text_x, l.subtitle_y);
  lv_obj_set_size(p.subtitle, l.text_w, l.subtitle_h);
  // From the card's bottom right, as the card's content area (inside its border) is measured from there too. A second
  // button stands on the left of the first (screen_alert::buttons); the words on each end in dots when they are too long.
  const bool two = alert_two_buttons && p.button2;
  const auto b = screen_alert::buttons(l, two);
  const int pad = ui::px(ui::large() ? 12 : 8);
  const auto place = [&](lv_obj_t *button, lv_obj_t *label, int x, int w) {
    lv_obj_set_size(button, w, l.button_h);
    lv_obj_align(button, LV_ALIGN_BOTTOM_RIGHT, -(l.card_w - x - w), -(l.card_h - l.button_y - l.button_h));
    // One line high: LVGL only ends a DOT label in dots when its text is taller than the label.
    if (label) lv_obj_set_size(label, std::max(0, w - 2 * pad), lv_font_get_line_height(lv_obj_get_style_text_font(label, LV_PART_MAIN)));
  };
  place(p.button, p.label, b.x, b.w);
  if (p.button2) {
    if (two) {
      place(p.button2, p.label2, b.x2, b.w2);
      lv_obj_remove_flag(p.button2, LV_OBJ_FLAG_HIDDEN);
    } else {
      lv_obj_add_flag(p.button2, LV_OBJ_FLAG_HIDDEN);
    }
  }
  if (!alert_frame) return l;
  if (l.image_w > 0 && l.image_h > 0) {
    lv_obj_set_pos(alert_frame, l.image_x, l.image_y);
    lv_obj_set_size(alert_frame, l.image_w, l.image_h);
  } else {
    // No picture, or no room for one on this glass: the frame stays hidden and the image is never fetched for it.
    lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
  }
  return l;
}
inline std::string alert_announced, alert_camera, alert_url;
inline uint32_t alert_announced_at = 0, alert_shown_at = 0;
// An alert's picture is worth a few more tries after a failed connection (alert_want). It goes before every other
// picture: a download on its way finishes first, and one for a page out of sight breaks off for it.
constexpr uint8_t ALERT_IMAGE_RETRIES = 3;

inline bool camera_supported() { return static_cast<bool>(camera_full.load); }
inline bool camera_visible() { return camera_root != nullptr; }
// A ring's view keeps the screen from standby (module doorbell, packages/core.yaml's standby interval); lite has none.
inline bool doorbell_holds() {
#ifdef SD_MOD_CALL
  if (call::holds()) return true;
#endif
#ifdef SD_MOD_DOORBELL
  return doorbell::holds();
#else
  return false;
#endif
}
// Its bindings, for the YAML of every board: a lambda that holds a ${...} cannot hold an #ifdef (ESPHome reads it as a
// template), so these take the module's place there. How a ring ended goes to ESP Screens (packages/core.yaml); the chime
// plays on `speaker` (features/audio-player.yaml).
inline void call_reports(std::function<void(const std::string &, const std::string &, bool, const std::string &)> report) {
#ifdef SD_MOD_CALL
  call::report = std::move(report);
#else
  (void) report;
#endif
}
template<class Speaker> inline void call_audio(Speaker *speaker, std::function<float()> volume_get, std::function<void(float)> volume_set,
                                               std::function<bool()> ring_on, std::function<bool()> switch_on, float ring_top) {
#ifdef SD_MOD_CALL
  call::switch_on = std::move(switch_on);
  call::ring_top = ring_top;
  call::bind_speaker(speaker);
  call::volume_get = std::move(volume_get);
  call::volume_set = std::move(volume_set);
  call::ring_on = std::move(ring_on);
#else
  (void) speaker; (void) volume_get; (void) volume_set; (void) ring_on; (void) switch_on; (void) ring_top;
#endif
}
// A board with an echo canceller hands it to a call (parts/es7210/aec.yaml): to work or to rest, and what its switch says.
inline void call_echo_cancel(std::function<void(bool)> set, std::function<bool()> is, std::function<void(int)> level) {
#ifdef SD_MOD_CALL
  call::echo_cancel = std::move(set);
  call::echo_cancel_is = std::move(is);
  call::echo_level = std::move(level);
#else
  (void) set; (void) is; (void) level;
#endif
}
inline void doorbell_reports(std::function<void(const std::string &, const std::string &)> report) {
#ifdef SD_MOD_DOORBELL
  doorbell::report = std::move(report);
#else
  (void) report;
#endif
}
template<class Speaker> inline void doorbell_audio(Speaker *speaker) {
#ifdef SD_MOD_DOORBELL
  doorbell::bind_speaker(speaker);
#else
  (void) speaker;
#endif
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
