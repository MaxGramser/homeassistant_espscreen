// The full view: a camera, a map or a picture over the whole glass, its keys and its map sheet.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the tiles' pictures and live streams (tile_picture_lvgl.h, live_spots_lvgl.h), which it only asks to stand aside.
// What proves it: tests/test_camera.py, tests/test_map_card.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// opened over the glass (firmware 0.21.0+), the screensaver's picture (firmware 0.29.0+); or, with a `size`, a media
// card's cover (firmware 0.2.64+) of that side with rounded corners over `background`. One question (picture_question.h).
inline void camera_request(const std::string &entity, int size, uint32_t background) {
  if (inbox.empty()) return;
  using picture_question::Fit;
  picture_question::Question q;
  picture_question::Place place;
  q.dark = theme::dark;
  const auto cap = picture_cap();
  q.cap = cap.bytes;
  if (size > 0) {
    q.owner = picture_question::Owner::CARD;
    q.sources = {picture_question::cover_source(entity)};
    q.w = q.h = place.w = place.h = size;
    place.radius = media_card::radius_for(size);
    place.ground = background;
    q.places = {place};
    picture_ask(q, "cover", entity, ++cover_view_id);
    ESP_LOGI("camera", "asked for the cover of %s", entity.c_str());
    return;
  }
  // The whole glass, within the board's cap (picture_cap, GitHub #183): a board with the memory gets its own pixels.
  int glass_w = overlay_card::screen_width(), glass_h = overlay_card::screen_height();
#ifdef SD_MOD_DOORBELL
  // A ring's picture fills the room beside its keys.
  if (doorbell::shown() && camera_map_index < 0 && !saver_camera) { glass_w = doorbell::area().w; glass_h = doorbell::area().h; }
#endif
#ifdef SD_MOD_CALL
  if (call::shown() && camera_map_index < 0 && !saver_camera) { glass_w = call::area().w; glass_h = call::area().h; }
#endif
  const int scale = picture_store::fit_scale(glass_w, glass_h, cap);
  q.w = place.w = std::max(1, picture_store::scaled(glass_w, scale));
  q.h = place.h = std::max(1, picture_store::scaled(glass_h, scale));
  const char *kind = "full";
  if (saver_camera) {
    // The screensaver's picture: the player's cover over the glass, a camera, or the photo of the photos step, darkened
    // under the words it carries (not the photo); a photo that moves slowly comes a little larger (picture_motion.h).
    q.owner = picture_question::Owner::SAVER;
    kind = "saver";
    if (saver_now.kind == "photos") {
      q.sources = {picture_question::PHOTOS_SOURCE};
      q.of = SAVER_PHOTOS;
      place.fit = Fit::AUTO;
      place.move = saver_now.motion ? 8 : 0;
    } else if (saver_now.kind == "media") {
      q.sources = {picture_question::cover_source(entity)};
      place.fit = Fit::SAVER;
      place.dim = 30;
    } else {
      q.sources = {picture_question::camera_source(entity)};
      place.dim = 30;
      q.pace = camera.every;  // SAVER_CAMERA_MS, set as the screensaver opens
    }
    q.formats = {"bmp8", "bmp24"};
  } else if (camera_map_index >= 0) {
    // A map's full view, drawn in the screen's look, with a person a finger picked and the moves of its own keys.
    q.owner = picture_question::Owner::VIEW;
    q.of = entity;
    q.sources = {picture_question::map_source(camera_map_index, map_focus, map_move.text())};
    place.fit = Fit::EXACT;
    q.formats = {"bmp8", "bmp24"};
  } else {
    // A camera: at its own proportions within the glass, at the view's pace. A P4 streams it into the room below its
    // top bar (live_view.h), with its sound where the board has a speaker; an app without streams answers with a still.
    q.owner = picture_question::Owner::VIEW;
    q.sources = {picture_question::camera_source(entity)};
    place.fit = Fit::SHRINK;
    q.pace = camera.every;
    if (live_wanted()) {
      const auto room = live_area();
      q.live_w = room.w;
      q.live_h = room.h;
      q.sound = live_view::has_speaker();
    }
  }
  q.places = {place};
  picture_ask(q, kind, saver_camera && saver_now.kind == "photos" ? SAVER_PHOTOS : entity, ++camera_view_id);
  ESP_LOGI("camera", "asked for %s", entity.c_str());
}

inline void camera_note_text(const char *text) {
  if (!camera_note) return;
  if (camera_spinner) { lv_obj_delete(camera_spinner); camera_spinner = nullptr; }
  lv_label_set_text(camera_note, text);
  if (text[0]) lv_obj_remove_flag(camera_note, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(camera_note, LV_OBJ_FLAG_HIDDEN);
}

inline void camera_release() {
  camera_release_due = false;
  if (camera_full.release) camera_full.release();
}


inline void camera_close() {
  if (!camera_root) return;
#ifdef SD_MOD_DOORBELL
  doorbell::closing();  // a ring's view says how it ended
#endif
#ifdef SD_MOD_CALL
  call::closing();
#endif
  // A live picture stops first: nothing of it writes the glass once LVGL draws the page there again.
  live_view::close(camera.stream.handle);
  view_wait.link.clear();
  camera_ram_low();  // a view that never streamed ends its watch too
  lv_obj_delete(camera_root);
  camera_root = camera_picture = camera_note = camera_back = camera_title = camera_spinner = map_card_obj = nullptr;
  camera_sound_key = camera_warm_spinner = nullptr;  // they went with the view
  camera_sound_waiting = false;
  map_zoom_keys = map_pad = map_waiting = nullptr;
  saver_first = saver_second = nullptr;  // they went with the view
  saver_keys = {};
  map_focus.clear();
  map_pinned = false;
  map_move = map_move_shown = MapMove{};
  map_sheet = MapSheet{};
  camera_release_due = true;
  // Its picture goes with it (the next collect, once nothing draws it), and a download on its way breaks off.
  loader.release(owners::VIEW);
  ESP_LOGI("camera", "closed %s", camera.entity.c_str());
  camera = ViewPicture{};
}

// The map's card at the bottom of its full view: the name, the state since when, and the day's changes with their
// times, in the card's own colours as a tile's card (firmware 0.21.0+). Every word comes ready from the app.
// The card over the bottom of a focused map: the effects page's card of rows (effects_page::card, its Metrics, its fonts,
// an icon at the left, the name, the value at the right), and the one picked as the top bar's name, as a deeper card
// names what it shows. Every word and icon comes ready from the app, from Home Assistant.
inline std::string camera_name;  // the tile's own name, the top bar's when nobody is picked
inline void map_keys_place();
inline void map_sheet_draw() {
  if (map_card_obj) { lv_obj_delete(map_card_obj); map_card_obj = nullptr; }
  const bool picked = camera_root && !map_focus.empty() && map_sheet.focus == map_focus && !map_sheet.title.empty();
  if (camera_title) lv_label_set_text(camera_title, (picked ? map_sheet.title : camera_name).c_str());
  if (!picked || map_sheet.rows.empty() || !effects_page::row_font) { map_keys_place(); return; }
  const auto m = effects_page::screen_metrics();
  const int side = (overlay_card::screen_width() - m.width) / 2, w = m.width - 2 * m.pad;
  // As many rows as the lower half of the glass holds, which the app left free under the one picked.
  const int rows = std::max(1, std::min<int>(map_sheet.rows.size(), (overlay_card::screen_height() / 2 - m.pad) / m.row_h));
  const int h = rows * m.row_h;
  map_card_obj = effects_page::card(camera_root, side + m.pad, overlay_card::screen_height() - m.pad - h, w, h, m.radius);
  lv_obj_add_flag(map_card_obj, LV_OBJ_FLAG_CLICKABLE);  // a finger on the card is no finger on the map
  const int text_h = lv_font_get_line_height(effects_page::row_font);
  const int icon_h = effects_page::icon_font ? lv_font_get_line_height(effects_page::icon_font) : 0;
  for (int n = 0; n < rows; ++n) {
    const auto &row = map_sheet.rows[n];
    auto *line = effects_page::plain(map_card_obj, 0, n * m.row_h, w, m.row_h);
    int x = m.inset;
    if (effects_page::icon_font) {
      auto *icon = effects_page::text(line, effects_page::glyph(row.icon, "\U000F034E"), effects_page::icon_font, theme::MUTED);
      lv_obj_set_width(icon, LV_SIZE_CONTENT);
      lv_obj_set_pos(icon, m.inset - 2, (m.row_h - icon_h) / 2);
      x += m.icon + 6;
    }
    auto *name = effects_page::text(line, row.name, effects_page::row_font, theme::INK);
    lv_obj_set_pos(name, x, (m.row_h - text_h) / 2);
    lv_obj_set_width(name, std::max(20, w * 3 / 5 - x));
    auto *value = effects_page::text(line, row.value, effects_page::row_font, theme::MUTED, LV_TEXT_ALIGN_RIGHT);
    lv_obj_set_width(value, w * 2 / 5 - m.inset);
    lv_obj_set_pos(value, w * 3 / 5, (m.row_h - text_h) / 2);
  }
  map_keys_place();
}

inline void camera_map_sheet(const MapSheet &next) {
  if (!camera_root || camera_map_index < 0 || camera.entity != next.entity) return;
  // An answer for another focus than the one picked since is not this one's.
  if (next.focus != map_focus) return;
  map_sheet = next;
  map_sheet_draw();
}

// The picture on the glass shows what the keys asked for at once (dev): the one there moved and scaled to the place
// asked for, around the middle of the glass, until the app's picture of it comes (view_done).
inline void map_preview() {
#if LV_USE_IMAGE
  if (!camera_picture) return;
  const auto *src = static_cast<const lv_image_dsc_t *>(lv_image_get_src(camera_picture));
  if (!src) return;
  const float f = std::ldexp(1.0f, map_move.zoom - map_move_shown.zoom), shown = std::ldexp(1.0f, map_move_shown.zoom);
  const float dx = (map_move.x - map_move_shown.x) * shown * f, dy = (map_move.y - map_move_shown.y) * shown * f;
  lv_image_set_pivot(camera_picture, src->header.w / 2, src->header.h / 2);
  lv_image_set_scale(camera_picture, (uint32_t) std::max(16.0f, std::min(4096.0f, 256.0f * f)));
  lv_obj_align(camera_picture, LV_ALIGN_CENTER, (int32_t) -dx, (int32_t) -dy);
#endif
}
// Focus a marker (or everyone again with ""): the card goes at once, the new picture and card come with the answer.
// Another focus is another view: the keys' move starts again from it.
inline void map_focus_on(const std::string &entity) {
  map_focus = entity;
  map_move = map_move_shown = MapMove{};
  map_preview();
  map_waiting_show();
  map_sheet.focus.clear();
  map_sheet_draw();
  // Another focus is another picture (camera_want): asked for at once.
  pictures_round();
}

// A round key of the full view: the back key, and a map's zoom and arrows (dev). On a map (`over_map`) the keys turn
// the look round for contrast, the ink as their fill and the card's colour as their glyph (dark keys in the light look,
// light ones in the dark), and let the map show through a little until a finger is on them.
inline lv_obj_t *view_key(lv_obj_t *parent, int size, const char *glyph, bool over_map = false) {
  auto *key = lv_obj_create(parent);
  lv_obj_remove_style_all(key);
  lv_obj_set_size(key, size, size);
  lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(key, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_radius(key, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
  if (over_map) {
    lv_obj_set_style_bg_color(key, theme::color(theme::INK), 0);
    lv_obj_set_style_bg_opa(key, LV_OPA_70, 0);
    lv_obj_set_style_bg_opa(key, LV_OPA_COVER, LV_STATE_PRESSED);
  } else {
    lv_obj_set_style_bg_color(key, theme::color(theme::KEY), 0);
    lv_obj_set_style_bg_color(key, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  }
  auto *label = lv_label_create(key);
  if (mini_icon_font) lv_obj_set_style_text_font(label, mini_icon_font, 0);
  lv_obj_set_style_text_color(label, theme::color(over_map ? theme::CARD : theme::INK), 0);
  lv_label_set_text(label, glyph);
  lv_obj_center(label);
  return key;
}
// The sizes of the full view's top bar, every page's (detail_bar), which the map's keys share.
using ViewBar = detail_bar::Metrics;
inline ViewBar view_bar() { return detail_bar::metrics(); }
// A map's own keys on its full view (dev): + and - at the bottom right, as the volume keys stand, and four arrows at
// the bottom left that move the map a centimetre of glass each. Each tap asks for the picture of the new view at once.
enum MapKey : int { MK_IN, MK_OUT, MK_UP, MK_DOWN, MK_LEFT, MK_RIGHT };
inline void map_key_event(lv_event_t *e) {
  if (!camera_root || camera_map_index < 0) return;
  const int k = (int) (intptr_t) lv_event_get_user_data(e);
  if (k == MK_IN || k == MK_OUT) {
    const int zoom = std::max(MAP_ZOOM_OUT, std::min(MAP_ZOOM_IN, map_move.zoom + (k == MK_IN ? 1 : -1)));
    if (zoom == map_move.zoom) return;
    map_move.zoom = zoom;
  } else {
    // A centimetre of glass in pixels of the framed zoom.
    const float step = ui::mm(10) / std::ldexp(1.0f, map_move.zoom);
    if (k == MK_UP) map_move.y -= step;
    else if (k == MK_DOWN) map_move.y += step;
    else if (k == MK_LEFT) map_move.x -= step;
    else map_move.x += step;
  }
  map_preview();
  map_waiting_show();
  pictures_round();
}
inline void map_keys_create() {
  const auto b = view_bar();
  auto group = [](int w, int h) {
    auto *box = lv_obj_create(camera_root);
    lv_obj_remove_style_all(box);
    lv_obj_set_size(box, w, h);
    lv_obj_remove_flag(box, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));  // a finger beside a key is on the map
    return box;
  };
  auto key = [&](lv_obj_t *box, int x, int y, const char *glyph, int k) {
    auto *obj = view_key(box, b.key, glyph, true);
    lv_obj_set_pos(obj, x, y);
    lv_obj_add_event_cb(obj, map_key_event, LV_EVENT_SHORT_CLICKED, (void *) (intptr_t) k);
  };
  map_zoom_keys = group(b.key, 2 * b.key + b.gap);
  key(map_zoom_keys, 0, 0, tile_controls::glyph::PLUS, MK_IN);
  key(map_zoom_keys, 0, b.key + b.gap, tile_controls::glyph::MINUS, MK_OUT);
  // A cross of round keys, the arrows of a remote's ring (render_remote_keypad).
  const int step = b.key + b.gap / 2;
  map_pad = group(2 * step + b.key, 2 * step + b.key);
  key(map_pad, step, 0, "\U000F0143", MK_UP);
  key(map_pad, 0, step, "\U000F0141", MK_LEFT);
  key(map_pad, 2 * step, step, "\U000F0142", MK_RIGHT);
  key(map_pad, step, 2 * step, "\U000F0140", MK_DOWN);
  // The busy card's spinner (set_busy), in the top bar's row across from the back key.
  const int spin = ui::px(ui::large() ? 30 : 20);
  map_waiting = spinner_create(camera_root, spin, ui::px(ui::large() ? 4 : 3));
  if (map_waiting) {
    lv_obj_set_pos(map_waiting, overlay_card::screen_width() - b.x - (b.key + spin) / 2, b.y + (b.key - spin) / 2);
    lv_obj_add_flag(map_waiting, LV_OBJ_FLAG_HIDDEN);
  }
  map_keys_place();
}
// Over the bottom of the map, clear of its attribution; above a picked one's card, or hidden where there is no room.
inline void map_keys_place() {
  if (!camera_root || !map_zoom_keys || !map_pad) return;
  const auto b = view_bar();
  const int top = b.y + b.key + b.gap;
  int bottom = overlay_card::screen_height() - b.y - ui::mm(3);
  if (map_card_obj) { lv_obj_update_layout(map_card_obj); bottom = lv_obj_get_y(map_card_obj) - b.gap; }
  const int width = overlay_card::screen_width();
  // Their sizes are only measured once LVGL laid them out: right after the view opens they would read 0.
  lv_obj_update_layout(camera_root);
  auto place = [&](lv_obj_t *box, int x) {
    const int h = lv_obj_get_height(box);
    if (bottom - h < top) { lv_obj_add_flag(box, LV_OBJ_FLAG_HIDDEN); return; }
    lv_obj_remove_flag(box, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_pos(box, x, bottom - h);
    lv_obj_move_foreground(box);
  };
  place(map_zoom_keys, width - b.x - lv_obj_get_width(map_zoom_keys));
  place(map_pad, b.x);
}

inline void camera_open(const std::string &entity, const std::string &name, int map_index, const std::string &focus) {
  // The screensaver's photos (app 0.4.89) open the full view as a camera does, under the step's own name.
  if (!camera_supported() || (!valid_entity(entity) && entity != SAVER_PHOTOS)) return;
  camera_close();
  // The view covers the page: its live tiles stop now, not at the next round, so their streams are gone before the
  // view's asks for its own (a ring with four live tiles was refused once, PLATFORM_PLAN.md 4.9).
  live_tiles_halt();
  camera_map_index = map_index;
  // Opened on someone (a person tile tapped): focused from the start, and Back closes the map at once.
  map_focus = focus;
  map_pinned = !focus.empty();
  camera.open(entity);
  camera_opened_at = esphome::millis();
  // The lowest internal RAM from here to its first picture (said with it): the page's streams end and the view's starts.
  camera_ram_watched = live_view::available() && camera_ram_watch();
  const int width = lv_display_get_horizontal_resolution(lv_display_get_default());
  const bool large = ui::large();
  // On the top layer: above the tiles, every card and an alert, which is there again after Back.
  camera_root = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(camera_root);
  lv_obj_set_size(camera_root, lv_pct(100), lv_pct(100));
  lv_obj_remove_flag(camera_root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(camera_root, LV_OBJ_FLAG_CLICKABLE);  // nothing reaches the tiles below
  // A map stands on the page behind the tiles (dev): light grey in the light look, black in the dark, so the edge a
  // moved map leaves until its next picture comes is the page and not a black band. A camera stays on black.
  const bool on_page = map_index >= 0;
  lv_obj_set_style_bg_color(camera_root, theme::color(on_page ? theme::PAGE : theme::CAMERA_PAGE), 0);
  lv_obj_set_style_bg_opa(camera_root, LV_OPA_COVER, 0);
  camera_note = lv_label_create(camera_root);
  if (detail_font) lv_obj_set_style_text_font(camera_note, detail_font, 0);
  lv_obj_set_style_text_color(camera_note, theme::color(on_page ? theme::MUTED : theme::CAMERA_NOTE), 0);
  lv_obj_center(camera_note);
  camera_note_text("");
  // The starting screen's spinner, its ring dark on the black page in both looks, a map's the page's own track.
  camera_spinner = spinner_create(camera_root, ui::px(large ? 48 : 32), ui::px(large ? 5 : 4));
  if (camera_spinner) {
    lv_obj_set_style_arc_color(camera_spinner, theme::color(on_page ? theme::TRACK : theme::CAMERA_TRACK), LV_PART_MAIN);
    lv_obj_center(camera_spinner);
  }
#ifdef SD_MOD_CALL
  // A call (module call): its keys and its other screen, on the same view.
  if (call::shown()) {
    call::build(camera_root, name);
    camera_name = name;
    if (!call::link().empty()) camera_link_now(call::link());
    pictures_round();
    return;
  }
#endif
#ifdef SD_MOD_DOORBELL
  // A ring (module doorbell): the doorbell's own header and keys instead of the back key and the name.
  if (doorbell::shown()) {
    doorbell::build(camera_root, name);
    camera_name = name;
    ESP_LOGI("camera", "open %s for a ring", entity.c_str());
    // The stream the app made for this ring as the event came: open before the round, which then asks for nothing.
    if (!doorbell::link().empty()) camera_link_now(doorbell::link());
    pictures_round();
    return;
  }
#endif
  // The top bar of every page a tap opens (detail_bar), its back key dark over a map.
  const auto home = detail_bar::back_slot(camera_root);
  const int bar = home.h, bar_y = home.y;
  camera_back = view_key(camera_root, bar, detail_bar::BACK, map_index >= 0);
  lv_obj_set_pos(camera_back, home.x, home.y);
  lv_obj_add_event_cb(camera_back, [](lv_event_t *) {
    // A map focused on someone goes back to everyone first (firmware 0.21.0+); then the key closes the view.
    if (!map_focus.empty() && !map_pinned) { map_focus_on(""); return; }
    // Closed after this event: the key that sends it goes with the view.
    lv_async_call([](void *) { camera_close(); }, nullptr);
  }, LV_EVENT_SHORT_CLICKED, nullptr);
  // A finger on a map's marker focuses that person or tracker, on the map beside it everyone again (firmware 0.21.0+).
  if (map_index >= 0) lv_obj_add_event_cb(camera_root, [](lv_event_t *) {
    lv_point_t point;
    lv_indev_t *input = lv_indev_active();
    // The markers are where the picture on the glass has them only once it shows what the keys asked for.
    if (!input || !camera_picture || !(map_move == map_move_shown)) return;
    lv_indev_get_point(input, &point);
    lv_area_t area;
    lv_obj_get_coords(camera_picture, &area);
    const int x = point.x - area.x1, y = point.y - area.y1;
    const MapSheet::Hit *best = nullptr;
    long nearest = 0;
    for (const auto &hit : map_sheet.hits) {
      const long dx = x - hit.x, dy = y - hit.y, reach = hit.r + ui::px(10);
      if (dx * dx + dy * dy > reach * reach) continue;
      if (!best || dx * dx + dy * dy < nearest) { best = &hit; nearest = dx * dx + dy * dy; }
    }
    if (best && best->entity != map_focus) map_focus_on(best->entity);
    else if (!best && !map_focus.empty() && !map_pinned) map_focus_on("");
  }, LV_EVENT_SHORT_CLICKED, nullptr);
  const lv_font_t *title_font = watch_font ? watch_font : detail_font;
  camera_title = lv_label_create(camera_root);
  if (title_font) lv_obj_set_style_text_font(camera_title, title_font, 0);
  lv_obj_set_style_text_color(camera_title, theme::color(theme::CAMERA_INK), 0);
  lv_obj_set_style_text_align(camera_title, LV_TEXT_ALIGN_CENTER, 0);
  lv_label_set_long_mode(camera_title, LV_LABEL_LONG_DOT);
  detail_bar::place_title(camera_title, camera_root);
  lv_label_set_text(camera_title, name.c_str());
  camera_name = name;
  // A map (firmware 0.21.0+) is light in the light look, where the camera's white name would vanish: its name is the
  // pill its tile carries, ink on the card's colour, as high as the back key and centred over the map.
  if (map_index >= 0) {
    const int line = title_font ? lv_font_get_line_height(title_font) : 20;
    lv_obj_set_style_text_color(camera_title, theme::color(theme::INK), 0);
    lv_obj_set_style_bg_color(camera_title, theme::color(theme::CARD), 0);
    lv_obj_set_style_bg_opa(camera_title, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(camera_title, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_hor(camera_title, ui::px(large ? 22 : 16), 0);
    lv_obj_set_style_pad_ver(camera_title, std::max(0, (bar - line) / 2), 0);
    lv_obj_set_style_max_width(camera_title, detail_bar::middle(camera_root).w, 0);
    lv_obj_set_size(camera_title, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_align(camera_title, LV_ALIGN_TOP_MID, 0, bar_y);
    map_keys_create();
  }
  ESP_LOGI("camera", "open %s", entity.c_str());
  // Asked for now rather than on the next tick (firmware 0.2.73+): the answer is most of the wait.
  pictures_round();
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
