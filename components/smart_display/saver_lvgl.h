// The screensaver: its clock, its keys and what it follows.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in saver_view.h.
// What proves it: tests/test_saver_view.cpp, tests/test_screen_saver.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// The clock: the time in the bedside clock's digits where they fit, else the largest digit step that does, and the date
// under it in the card heading's font, white on black whatever the look. In 12 hours AM or PM stands after the time, and
// the outside temperature the app sends stands small in the middle at the bottom (firmware 0.31.0+).
inline void saver_clock_draw() {
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const auto now = now_time ? now_time() : esphome::ESPTime{};
#ifdef SD_MOD_CLOCK_FACES
  // A face of the module in the place of the digital clock, with the same row of entities (Classic shows it).
  if (saver_next.face.kind != SaverFace::DIGITAL) { clock_faces::draw(saver_root, saver_next.face, now, saver_next.row, saver_next.weather); return; }
#endif
  const std::string time = time_text(now), date = date_text(now), ampm = am_pm(now);
  const std::string &degrees = saver_next.weather;
  const auto &entities = saver_next.row;
  const bool large = ui::large();
  const int margin = ui::px(large ? 24 : 10), gap = ui::px(large ? 12 : 6), space = ui::px(large ? 8 : 4);
  const lv_font_t *date_font = watch_font ? watch_font : detail_font;
  const lv_font_t *small = control_font ? control_font : detail_font;
  const int date_h = date_font ? lv_font_get_line_height(date_font) : 24;
  const int small_h = small ? lv_font_get_line_height(small) : 20;
  // AM or PM stands after the time in the small font, and the outside temperature keeps a line at the bottom
  // (firmware 0.31.0+): the digits get the room that is left.
  const int ampm_w = ampm.empty() || !small ? 0 : text_width(ampm, small);
  const int room_w = width - 2 * margin - (ampm_w ? space + ampm_w : 0);
  // The temperature in the date's font: small beside the digits, and as easy to read across a room as the date.
  const int below = degrees.empty() && entities.empty() ? 0 : date_h + gap;
  const lv_font_t *digits = bedside_digits();
  if (!digits || text_width(time, digits) > room_w) digits = largest_digits(time.c_str(), room_w, height - 2 * margin - gap - date_h - 2 * below);
  if (!digits) digits = clock_font;
  int top = 0, digits_h = 40;
  if (digits) digit_box(digits, top, digits_h);
  // Black with white digits in both looks (firmware 0.31.0+): a screensaver gives as little light as it can. Before,
  // the clock stood on the page's own colour, a lit white glass in the light look.
  lv_obj_set_style_bg_color(saver_root, theme::color(theme::CAMERA_PAGE), 0);
  const uint32_t ink = media_ink(), soft = theme::mix(ink, theme::hex(theme::CAMERA_PAGE), 150);
  const auto l = saver_view::clock(width, height, digits_h, date.empty() ? 0 : date_h, date.empty() ? 0 : gap);
  const int time_w = digits ? text_width(time, digits) : width;
  const auto row = saver_view::clock_row(width, time_w, ampm_w, space);
  saver_text(saver_root, digits, ink, {row.time_x, l.time.y - top, time_w + 2, digits ? (int) lv_font_get_line_height(digits) : digits_h}, time, LV_TEXT_ALIGN_LEFT);
  if (ampm_w) {
    // On the digits' baseline, as the clock card's own AM and PM.
    int small_top = 0, small_digits = small_h;
    digit_box(small, small_top, small_digits);
    saver_text(saver_root, small, soft, {row.ampm_x, l.time.y + digits_h - small_digits - small_top, ampm_w + 2, small_h}, ampm, LV_TEXT_ALIGN_LEFT);
  }
  if (!date.empty()) saver_text(saver_root, date_font, soft, {margin, l.date.y, width - 2 * margin, date_h}, date);
  if (!entities.empty() && date_font && header_icon_font) saver_row_draw(entities, now, soft, saver_view::temperature(width, height, margin, date_h), date_font);
  else if (!degrees.empty() && date_font) saver_text(saver_root, date_font, soft, saver_view::temperature(width, height, margin, date_h), degrees);
}

// Where a player's keys stand on this glass (saver_view::keys), the sizes the media card's keys have: the play key when
// the player can play or pause, the volume keys when it has a volume. A screensaver that is no player has none.
inline saver_view::Keys saver_key_layout() {
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const bool large = ui::large(), media = saver_now.kind == "media";
  using namespace tile_controls;
  media_card::Metrics m;
  m.large = large;
  return saver_view::keys(width, height, ui::px(large ? 28 : 12), m.key_h(), m.play_h(), ui::px(large ? 14 : 8),
                          media && (saver_now.features & (feature::MEDIA_PLAY | feature::MEDIA_PAUSE)),
                          media && (saver_now.features & (feature::MEDIA_VOLUME_SET | feature::ha::media_player::VOLUME_STEP)));
}
// The words over the picture, once it is there: a cover's title with its artist and album, a camera's name alone, in
// white over the darkened picture or the cover's colour.
inline void saver_words() {
  if (!camera_root || !saver_camera) return;
  // Under a plugin's face the picture stands alone: the face draws its own words and keys.
  if (saver_bare) { saver_words_due = false; return; }
  // A photo stands alone: no words, no keys (app 0.4.89).
  if (saver_now.kind == "photos") { saver_words_due = false; return; }
  const auto &c = saver_now;
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const bool large = ui::large();
  const int margin = ui::px(large ? 28 : 12), gap = ui::px(large ? 4 : 2);
  const lv_font_t *first_font = watch_font ? watch_font : detail_font;
  const lv_font_t *second_font = control_font ? control_font : detail_font;
  const bool media = c.kind == "media";
  const std::string first = media && !c.title.empty() ? c.title : c.name;
  const std::string second = media ? media_card::subtitle(c.artist, c.album) : std::string();
  const lv_font_t *font = media ? first_font : second_font;
  const int first_h = font ? lv_font_get_line_height(font) : 24;
  const int second_h = second.empty() || !second_font ? 0 : lv_font_get_line_height(second_font);
  const auto shape = media ? saver_view::shape(width, height) : saver_view::Shape::fill;
  auto w = saver_view::words(shape, width, height, margin, first_h, second_h, gap);
  // A player's keys stand in the bottom right corner, and the words end before them (firmware 0.33.0+).
  const auto keys = saver_key_layout();
  saver_view::before_keys(w, keys, margin);
  // A long title takes a second line, and the words are laid out again around the taller title (saver_view.h).
  if (font) {
    lv_point_t need;
    lv_text_get_size(&need, first.c_str(), font, 0, 0, w.first.w, LV_TEXT_FLAG_NONE);
    const int lines = saver_view::title_lines(need.y, first_h);
    if (lines > 1) {
      const auto taller = saver_view::words(shape, width, height, margin, lines * first_h, second_h, gap);
      if (saver_view::fits(shape, taller, width, height)) { w = taller; saver_view::before_keys(w, keys, margin); }
    }
  }
  for (lv_obj_t **words : {&saver_first, &saver_second}) if (*words) { lv_obj_delete(*words); *words = nullptr; }
  saver_words_due = false;
  saver_first = saver_text(camera_root, font, media_ink(), w.first, first, LV_TEXT_ALIGN_LEFT);
  if (second_h) saver_second = saver_text(camera_root, second_font, theme::mix(media_ink(), 0, 200), w.second, second, LV_TEXT_ALIGN_LEFT);
  saver_keys_draw();
}
// The keys: white rounds over the darkened cover, the play key whole and the two volume keys a haze with a white sign,
// as the media card's keys stand over its cover. Each takes its own tap (the touch guard first, as every key), sends its
// action for the player on the glass and leaves the screen in standby. The play key turns at once and Home Assistant's
// word follows (saver_tick puts it back when none came).
// Volume down held for a second and a half mutes the player, where Home Assistant says it can be muted; the key then shows the
// muted speaker. The next tap on either volume key takes the mute off and changes nothing else, and after that the two
// are the volume again.
constexpr uint32_t SAVER_MUTE_HOLD_MS = MEDIA_MUTE_HOLD_MS;
inline uint32_t saver_pressed = 0;  // when the finger came down on volume down; 0 once this hold has muted
inline void saver_faces() {
  auto face = [](lv_obj_t *key, const char *glyph) {
    auto *icon = key ? lv_obj_get_child(key, 0) : nullptr;
    if (!icon) return;
    lv_label_set_text(icon, glyph);
    lv_obj_center(icon);
  };
  face(saver_keys[1], saver_now.muted ? tile_controls::glyph::MUTED : tile_controls::glyph::MINUS);
  face(saver_keys[2], saver_now.state == "playing" ? tile_controls::glyph::PAUSE : tile_controls::glyph::PLAY);
}
inline void saver_send(const char *service, const char *key = nullptr, const char *value = nullptr) {
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(service);
  request.data.init(key ? 2 : 1);
  esphome::api::HomeassistantServiceMap target;
  target.key = api_text::of("entity_id");
  target.value = api_text::of(saver_now.entity);
  request.data.push_back(target);
  if (key) {
    esphome::api::HomeassistantServiceMap field;
    field.key = api_text::of(key);
    field.value = api_text::of(value);
    request.data.push_back(field);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("saver", "key %s%s%s for %s", service, value ? " " : "", value ? value : "", saver_now.entity.c_str());
}
// What a finger changed on the screensaver's player (its keys, or a plugin's face through tessera::wish, plugin API
// 0.14), shown at once and squared with Home Assistant's word by optimistic.h's rules, as every control's
// (docs/OPTIMISTIC.md): the app's next word that still says the old value keeps the wish in front, the value wished
// ends it, and silence puts the old value back. The player is no tile of the page (a speaker in another room), so the
// wish reads and writes the screensaver's word where a tile's wish reads and writes the tile.
inline optimistic::Pool<2> saver_wishes;
inline std::string saver_read(const SaverChoice &c, optimistic::Field f) {
  if (f == optimistic::Field::PLAYING) return c.state == "playing" ? "1" : "0";
  if (f == optimistic::Field::MUTED) return c.muted ? "1" : "0";
  return {};
}
inline void saver_write(SaverChoice &c, optimistic::Field f, const std::string &value) {
  if (f == optimistic::Field::PLAYING) c.state = value == "1" ? "playing" : "paused";
  else if (f == optimistic::Field::MUTED) c.muted = value == "1";
}
// The glass shows the wished value: the keys' faces, and a plugin's face hears it in its on_state.
inline void saver_wish_show() {
  saver_faces();
  plugin_host::saver_refresh();
}
inline void saver_wish_tick(uint32_t now) {
  for (auto &w : saver_wishes.wishes) {
    if (w.phase == optimistic::Phase::IDLE) continue;
    const auto outcome = optimistic::tick(w, now);
    if (outcome == optimistic::Outcome::SEND) {
      if (w.entity == saver_now.entity) saver_send(w.service.c_str(), w.key.empty() ? nullptr : w.key.c_str(), w.value.c_str());
      optimistic::sent(w, false);
    } else if (outcome == optimistic::Outcome::REVERT && w.entity == saver_now.entity) {
      ESP_LOGI("saver", "%s back to '%s' (no word from Home Assistant)", w.entity.c_str(), w.before.c_str());
      saver_write(saver_now, w.field, w.before);
      saver_wish_show();
    }
  }
}
// A finger's wish for the player on the glass: `value` in optimistic::Field's words, and the action that makes it so.
inline bool saver_wish(optimistic::Field field, const std::string &value, const char *service, const char *key = "",
                       const char *data = "") {
  if (!fresh() || saver_now.kind != "media" || !valid_entity(saver_now.entity) || !service) return false;
  auto &w = saver_wishes.slot(saver_now.entity, field);
  optimistic::want(w, saver_now.entity, saver_now.entity, field, saver_read(saver_now, field), value, esphome::millis());
  w.service = service; w.key = key ? key : ""; w.value = data ? data : "";
  ESP_LOGI("saver", "wish %s: '%s' (was '%s')", saver_now.entity.c_str(), value.c_str(), w.before.c_str());
  saver_write(saver_now, field, value);
  saver_wish_show();
  saver_wish_tick(esphome::millis());  // a choice goes out now, unless one is on its way
  return true;
}
// The app's next word for the player: a wish still on its way stays in front of a word from before it.
inline void saver_wish_reported(SaverChoice &next) {
  for (auto &w : saver_wishes.wishes) {
    if (!w.live() || w.entity != next.entity || next.kind != "media") continue;
    if (optimistic::report(w, saver_read(next, w.field)) == optimistic::Outcome::KEEP) saver_write(next, w.field, w.want);
  }
}
inline void saver_mute(bool muted) {
  saver_wish(optimistic::Field::MUTED, muted ? "1" : "0", "media_player.volume_mute", "is_volume_muted", muted ? "true" : "false");
}
inline void saver_key_event(lv_event_t *e) {
  const int n = (int) (intptr_t) lv_event_get_user_data(e);
  const auto code = lv_event_get_code(e);
  const uint32_t now = esphome::millis();
  if (!saver_camera || saver_now.kind != "media" || !fresh() || !valid_entity(saver_now.entity)) return;
  if (code == LV_EVENT_PRESSED) { saver_pressed = now ? now : 1; return; }
  if (code == LV_EVENT_PRESSING) {
    if (!saver_pressed || now - saver_pressed < SAVER_MUTE_HOLD_MS || saver_now.muted ||
        !(saver_now.features & tile_controls::feature::MEDIA_VOLUME_MUTE)) return;
    saver_pressed = 0;
    if (allowed(now, 703, "screensaver mute")) saver_mute(true);
    return;
  }
  if (n == 2) {
    if (!allowed(now, 700, "screensaver play")) return;
    saver_wish(optimistic::Field::PLAYING, saver_now.state == "playing" ? "0" : "1", "media_player.media_play_pause");
    return;
  }
  // A volume key, on the release: the hold that muted used this contact up, so it does not also step.
  if (!screen_input::touch_guard.accept_repeat(now, 701 + n)) return;
  if (saver_now.muted) { saver_mute(false); return; }
  saver_send(n == 0 ? "media_player.volume_up" : "media_player.volume_down");
}
inline void saver_keys_draw() {
  for (lv_obj_t *&key : saver_keys) if (key) { lv_obj_delete(key); key = nullptr; }
  if (!camera_root || !saver_camera || saver_bare || saver_now.kind != "media") return;
  const auto l = saver_key_layout();
  const uint32_t ink = media_ink();
  const lv_font_t *small = mini_icon_font ? mini_icon_font : detail_font;
  auto key = [&](int n, const media_card::Rect &r, const char *glyph, const lv_font_t *font, bool primary) {
    if (r.w <= 0) return;
    auto *o = lv_obj_create(camera_root);
    lv_obj_remove_style_all(o);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_ext_click_area(o, ui::px(6));
    lv_obj_set_pos(o, r.x, r.y);
    lv_obj_set_size(o, r.w, r.h);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(o, theme::rgb(ink), 0);
    lv_obj_set_style_bg_opa(o, primary ? LV_OPA_COVER : 56, 0);
    lv_obj_set_style_bg_color(o, theme::rgb(primary ? theme::mix(ink, 0, 200) : ink), LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(o, primary ? LV_OPA_COVER : 110, LV_STATE_PRESSED);
    auto *icon = lv_label_create(o);
    lv_obj_remove_flag(icon, LV_OBJ_FLAG_CLICKABLE);
    if (font) lv_obj_set_style_text_font(icon, font, 0);
    lv_obj_set_style_text_color(icon, primary ? theme::color(theme::CAMERA_PAGE) : theme::rgb(ink), 0);
    lv_label_set_text(icon, glyph);
    lv_obj_center(icon);
    // The play key takes a short tap, as every play key; a volume key its release, so a slow press still steps, and
    // volume down also the hold that mutes.
    lv_obj_add_event_cb(o, saver_key_event, n == 2 ? LV_EVENT_SHORT_CLICKED : LV_EVENT_CLICKED, (void *) (intptr_t) n);
    if (n == 1) {
      lv_obj_add_event_cb(o, saver_key_event, LV_EVENT_PRESSED, (void *) (intptr_t) n);
      lv_obj_add_event_cb(o, saver_key_event, LV_EVENT_PRESSING, (void *) (intptr_t) n);
    }
    saver_keys[n] = o;
  };
  key(0, l.plus, tile_controls::glyph::PLUS, small, false);
  key(1, l.minus, saver_now.muted ? tile_controls::glyph::MUTED : tile_controls::glyph::MINUS, small, false);
  key(2, l.play, saver_now.state == "playing" ? tile_controls::glyph::PAUSE : tile_controls::glyph::PLAY, tile_icon_font(), true);
}

inline void saver_hide() {
  saver_follow_due = false;
  plugin_host::saver_hide();
#ifdef SD_MOD_CLOCK_FACES
  clock_faces::forget();
#endif
  if (saver_root) lv_obj_delete(saver_root);
  saver_root = nullptr;
  if (saver_camera) camera_close();
  saver_camera = false;
  saver_bare = false;
  saver_now = SaverChoice{};
  saver_pictures = false;
}
// The glass the screensaver draws on itself (the clock, a plugin's saver): black, the whole of it, on the top layer under
// an alert, with nothing that takes a tap (a plugin's parts that do take theirs, ui::takes_taps).
inline lv_obj_t *saver_glass() {
  auto *root = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(root);
  lv_obj_remove_flag(root, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(root, lv_pct(100), lv_pct(100));
  lv_obj_set_style_bg_opa(root, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(root, theme::color(theme::CAMERA_PAGE), 0);
  lv_obj_move_to_index(root, 0);
  return root;
}
inline void saver_show() {
  saver_now = saver_next;
  // A plugin's face or step (plugin API 0.14): the plugin draws on the glass; the step's picture is a place of its own
  // (step:), loaded by the plugin host, so the full view stays closed.
  if (saver_plugin_draws(saver_now)) {
    saver_pictures = camera_supported();
    // A face with the step's own picture under it (`backdrop`): the full view as Tessera's own face opens it, bare, and
    // the plugin's glass clear over it, under an alert.
    if (plugin_host::saver_backdrop(saver_now.plugin) && saver_picture_kind(saver_now.kind) && camera_supported()) {
      saver_bare = saver_camera = true;
      camera_open(saver_now.entity, saver_now.name, -1, "");
      if (camera_root) {
        lv_obj_remove_flag(camera_root, LV_OBJ_FLAG_CLICKABLE);
        for (lv_obj_t **part : {&camera_back, &camera_title, &camera_spinner}) if (*part) { lv_obj_delete(*part); *part = nullptr; }
        lv_obj_move_to_index(camera_root, 0);
        if (saver_now.kind != "camera") camera.once = true;
        else camera.every = SAVER_CAMERA_MS;
      } else {
        saver_bare = saver_camera = false;
      }
    }
    saver_root = saver_glass();
    if (saver_bare) {
      lv_obj_set_style_bg_opa(saver_root, LV_OPA_TRANSP, 0);
      lv_obj_move_to_index(saver_root, 1);
    }
    plugin_host::saver_show(saver_root, saver_now.plugin, saver_now.plugin_data, standby_level(),
                            screen_settings::current.night(minute_of_day()));
    ESP_LOGI("saver", "%s by %s", saver_now.kind.c_str(), saver_now.plugin.c_str());
    return;
  }
  saver_pictures = saver_now.kind != "clock";
  if (saver_pictures) {
    // The full view, asked for as the screensaver's picture (camera_request adds what it shows), then stripped of its
    // keys, its name and its spinner, and laid under an alert that may come.
    saver_camera = true;
    camera_open(saver_now.entity, saver_now.name, -1, "");
    if (!camera_root) { saver_camera = false; return; }
    lv_obj_remove_flag(camera_root, LV_OBJ_FLAG_CLICKABLE);
    for (lv_obj_t **part : {&camera_back, &camera_title, &camera_spinner}) if (*part) { lv_obj_delete(*part); *part = nullptr; }
    lv_obj_move_to_index(camera_root, 0);
    // A camera refreshes at its pace; a cover and a photo load once, and the next is a new picture (saver_sync).
    if (saver_now.kind != "camera") camera.once = true;
    else camera.every = SAVER_CAMERA_MS;
    ESP_LOGI("saver", "%s %s", saver_now.kind.c_str(), saver_now.entity.c_str());
    return;
  }
  saver_root = saver_glass();
  saver_clock_draw();
  ESP_LOGI("saver", "clock");
}
// Another track, another cover or another picture step while a picture stands (firmware 0.32.0+): the view stays, with
// the picture and its words, and the next picture loads under it; the words change when it has come. Before, the view
// closed and opened again, and the glass stood black for as long as the next picture took.
inline void saver_follow() {
  // The same picture with other words (the title came before the cover's colour, or the other way round): the words
  // alone, nothing loads; while that picture is still on its way, they come with it.
  // The cover's colour only shows beside a cover on long glass (saver_view::shape): on square glass it is no new picture.
  const bool ground_shows = saver_view::shape(overlay_card::screen_width(), overlay_card::screen_height()) != saver_view::Shape::fill;
  if (saver_next.kind == saver_now.kind && saver_next.entity == saver_now.entity && saver_next.picture == saver_now.picture &&
      (saver_next.ground == saver_now.ground || !ground_shows)) {
    saver_now = saver_next;
    if (!saver_words_due) saver_words();
    else saver_keys_draw();
    return;
  }
  // The next picture loads under the one that stands (the loader breaks off one for a track that went meanwhile).
  saver_follow_due = false;
  saver_now = saver_next;
  saver_keys_draw();  // the keys are the next player's at once; its words wait for its picture
  camera.open(saver_now.entity);
  if (saver_now.kind != "camera") camera.once = true;
  else camera.every = SAVER_CAMERA_MS;
  saver_words_due = true;
  ESP_LOGI("saver", "%s %s, the last picture stays until it comes", saver_now.kind.c_str(), saver_now.entity.c_str());
}
inline void saver_follow_pending() {
  if (!std::exchange(saver_follow_due, false)) return;
  if (saver_lit && saver_camera && camera_root && camera_picture && !(saver_next == saver_now) &&
      saver_picture_kind(saver_next.kind) && (!saver_plugin_draws(saver_next) || saver_bare)) saver_follow();
}
// apply_screen_settings, after every change and every minute: `lit` is standby with a backlight that is on.
inline void saver_sync(bool lit) {
  saver_lit = lit;
  const bool shown = saver_root || saver_camera;
  if (lit) saver_woke = false;  // standby again: no waking touch is still to be read
  if (!lit || !saver_wanted()) { if (shown) saver_hide(); return; }
  // The camera and the cover stand as they are while nothing changed; the clock is drawn again, a minute later. A
  // plugin's saver stays and draws on its own clock (on_tick).
  if (shown && saver_next == saver_now && (saver_now.kind != "clock" || !saver_now.plugin.empty())) return;
  // The same plugin's saver for the same step with a new word: it paints that in place (on_state). Other options make
  // it anew, as Tessera's own face is drawn again for another look: a saver reads its options in show().
  if (saver_view::paints_in_place(saver_now, saver_next, saver_root != nullptr, saver_plugin_draws(saver_next))) {
    // Its backdrop follows the next cover or photo as Tessera's own face does (the last stays until it comes).
    if (saver_bare && camera_root && camera_picture && (saver_next.entity != saver_now.entity ||
        saver_next.picture != saver_now.picture || saver_next.motion != saver_now.motion)) saver_follow();
    else saver_now = saver_next;
    plugin_host::saver_state(saver_now.plugin_data);
    return;
  }
  if (saver_camera && camera_root && camera_picture && saver_picture_kind(saver_next.kind) && !saver_plugin_draws(saver_next)) {
    saver_follow();
    return;
  }
  saver_hide();
  saver_show();
}
// Whether a screensaver is on the glass now: a finger that lands on one wakes the screen at once (dim_wake_overlay).
inline bool saver_on() { return saver_root || saver_camera; }
// wake_display: the screensaver goes, and the touch that woke the screen does nothing else. It goes at once and the
// page under it is drawn in sight: a finger gets its answer the moment it lands, on every board. Hiding that drawing
// behind a dark backlight kept the glass black for as long as the page took to draw, which read as a tap not heard.
// `saver_woke` stays until wake_tap has read it, since the finger that woke the screen on its press clicks after.
inline void saver_wake() {
  saver_lit = false;
  if (saver_on()) saver_woke = true;
  saver_hide();
}
// A new layout on its way (cancel_layout_input): every picture goes; saver_tick draws the screensaver again.
inline void saver_forget() { saver_hide(); }
// The app's word (page_receiver.cpp). In standby the glass follows at once, through apply_screen_settings.
inline void saver_receive(SaverChoice next) {
  saver_wish_reported(next);
  if (next == saver_next) return;
  saver_next = next;
  if (!awake() && saver_changed) saver_changed();
}
inline void saver_tick(uint32_t now) {
  if (now - saver_ticked < 1000) return;
  saver_ticked = now;
  // Gone under it (a new layout, an alert that closed the camera): drawn again.
  if (saver_lit && !saver_root && !saver_camera && saver_wanted()) saver_show();
#ifdef SD_MOD_CLOCK_FACES
  // A face's seconds hand, one step a second.
  else if (saver_root && now_time) clock_faces::tick(now_time());
#endif
}

// ---------------------------------------------------------------------------------------------------------
// What a finger on the glass does (firmware 0.2.80). ESPHome gives a board three touchscreen triggers, and
// what they did used to be copied into every board file: 55 of the Waveshare's 62 lines were word for word the
// Guition's. A new board took `on_touch` and not the other two, so one tap worked and nothing after it -- the
// guard waited for a release that was never reported. It is behaviour, not hardware, so it lives here once and
// a board's triggers are one line each. The boot lambda of packages/core.yaml hands over the four things that
// live in the YAML.
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
