// Live tiles and live places on a P4.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in live_spots.h, live_view.h.
// What proves it: tests/test_live_spots.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Live tiles and live places on a P4 (live_spots.h, live_view.h) ----
// A camera tile set to Live (its pace 0) streams while it is on the glass, the pages stand still and nothing lies over
// them: no card, no camera full screen, no settings, no alert, no screensaver. Otherwise, and until its first live
// picture, it shows its last still, as a camera tile on every board does. Its pictures come plain at the card's size;
// the screen lays the card's rounded corners, the shade and the name over each of them (live_view::compose), so the app
// does nothing per picture a screen can do itself. Opening the camera full screen stops the tiles' streams; the app's
// source of the camera keeps running a while, so the full view's first picture is there at once.
// A plugin tile's place with a camera's address that the tile set live (plugin API 0.17, ui::live) streams the same
// way: while it is on the glass, the page stands still and nothing lies over it, its stills under it until its first
// live picture, into the place's room with the place's corners, filled or whole as its fit says, on the card's colour.
// Asked only of an app that reads questions; the app checks that the camera is the tile's own entity. One writer on
// the glass stays live_view: a plugin never draws a stream itself (docs/PICTURES.md, "For plugins").
// What streams, asks, stops and gives up is one machine for both, live_spots::Spots; here is what it is bound to: which
// spots may stream this round, their question, their look, and the stream itself.
inline live_spots::Spots spots;
// Whether a tile asked for its stream or streams: the loader leaves its still alone meanwhile (its still's question
// would make the link's answer an earlier question's; streaming, its still is under the live picture and stays as it was).
inline bool live_tile_active(size_t index) { return spots.active(static_cast<uint32_t>(index)); }
// The answer to a live place's question is the one its number names.
inline bool live_place_question(uint32_t number) { return spots.question(number); }
inline bool page_clear() {
  return live_view::available() && tiles_seen() && !camera_visible() && !card_open() && !settings_screen::visible() &&
         !(alert_parts.card && lv_obj_is_visible(alert_parts.card)) && camera_view::settled(esphome::millis(), last_turn_ms);
}
inline live_view::Rect card_room(const Widgets &w);
inline bool live_tile_wanted(const Widgets &w, const Tile &t) {
  if (!w.tile || !t.live() || t.refresh != 0 || t.domain() != "camera" || !card_art(t) || !on_glass(w)) return false;
  const auto room = card_room(w);
  return !drawn_over(w.tile, room.x, room.y, room.w, room.h);
}
inline live_view::Rect card_room(const Widgets &w) {
  lv_obj_update_layout(w.tile);
  lv_area_t a;
  lv_obj_get_coords(w.tile, &a);
  return {static_cast<int>(a.x1), static_cast<int>(a.y1), static_cast<int>(lv_area_get_width(&a)),
          static_cast<int>(lv_area_get_height(&a))};
}
inline live_view::Rect object_room(const lv_obj_t *o) {
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  return {static_cast<int>(a.x1), static_cast<int>(a.y1), static_cast<int>(lv_area_get_width(&a)),
          static_cast<int>(lv_area_get_height(&a))};
}
// Every live place of the plugin tiles on the glass: `each(card, place, camera, contain)`.
inline void live_places_each(const std::function<void(Widgets &, lv_obj_t *, const std::string &, bool)> &each) {
  each_card([&](Widgets &w) {
    if (!w.plugin || !w.tile || w.index >= model.count || !on_glass(w)) return;
    plugin_host::live_places(w, [&](lv_obj_t *place, const std::string &camera, bool contain) { each(w, place, camera, contain); });
  });
}
inline bool tile_ask(const Widgets &w, const Tile &t, tile_picture::Ask &a);
// The loader a live tile or place turns in its top right corner while its camera's stills show, until it is live
// (live_view.h, "Until it is live"): the firmware's spinner, its ring the camera's track and its arc Home Assistant's
// blue, a little smaller than a loading card's, on a round shade.
inline void live_loader(live_view::Look &look) {
  const bool large = ui::large();
  look.loader = ui::px(large ? 34 : 26);
  look.loader_margin = ui::px(large ? 10 : 8);
  look.loader_arc = ui::px(large ? 4 : 3);
  look.loader_ring = live_view::rgb565(theme::hex(theme::CAMERA_TRACK));
  look.loader_turn = live_view::rgb565(theme::ha::RAIN);
}
// The mark of a squeezed live tile (docs/PLATFORM_PLAN.md 4.10): speedometer-slow in white on a round dark chip where
// the loader turns (live_view::loader_spot), drawn once by LVGL off the glass and copied by the stream (Look::badge),
// which lays it over its pictures while the governor squeezes the live tiles. Nullptr without the glyph or snapshots;
// the caller destroys it after live_view::open.
inline constexpr uint32_t SQUEEZED_GLYPH = 0xF0F86;  // speedometer-slow, in the status font (packages/core.yaml)
inline lv_draw_buf_t *live_badge(live_view::Look &look, int card_w, int card_h) {
#if LV_USE_SNAPSHOT
  int x = 0, y = 0;
  lv_font_glyph_dsc_t glyph;
  if (!header_status_font || !live_view::loader_spot(look, card_w, card_h, x, y) ||
      !lv_font_get_glyph_dsc(header_status_font, &glyph, SQUEEZED_GLYPH, 0))
    return nullptr;
  lv_obj_t *off = lv_obj_create(nullptr);  // a screen never shown: the chip is drawn for the snapshot alone
  lv_obj_t *chip = lv_obj_create(off);
  lv_obj_remove_style_all(chip);
  lv_obj_set_size(chip, look.loader, look.loader);
  lv_obj_set_style_radius(chip, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_color(chip, lv_color_black(), 0);
  lv_obj_set_style_bg_opa(chip, LV_OPA_60, 0);
  lv_obj_t *icon = lv_label_create(chip);
  lv_obj_set_style_text_font(icon, header_status_font, 0);
  lv_obj_set_style_text_color(icon, lv_color_white(), 0);
  lv_label_set_text(icon, tile_icon::utf8(SQUEEZED_GLYPH).c_str());
  lv_obj_center(icon);
  lv_obj_update_layout(off);
  lv_draw_buf_t *drawn = lv_snapshot_take(chip, LV_COLOR_FORMAT_ARGB8888);
  lv_obj_delete(off);
  if (!drawn) return nullptr;
  look.badge = reinterpret_cast<const uint32_t *>(drawn->data);
  look.badge_w = drawn->header.w;
  look.badge_h = drawn->header.h;
  look.badge_stride = drawn->header.stride / 4;
  look.badge_x = x;
  look.badge_y = y;
  return drawn;
#else
  return nullptr;
#endif
}
// A live tile's name as the card lays it over its picture (render_camera_card): the tile's font, left, at the bottom of
// the card's content, in the picture's ink. Drawn once by LVGL off the glass and copied by the stream (Look::name), not
// taken from the card's own label: a card that had no still yet stands in its plain layout, its name in the page's ink
// halfway up, and that copy lay dark over every live picture (2026-10-28, a wallbox). Nullptr without a name or
// snapshots; the caller destroys it after live_view::open.
inline lv_draw_buf_t *live_name(live_view::Look &look, const Widgets &card, const live_view::Rect &room) {
#if LV_USE_SNAPSHOT
  if (!card.title || !card.title_font) return nullptr;
  const char *text = lv_label_get_text(card.title);
  if (!text || !*text) return nullptr;
  lv_area_t content;
  lv_obj_get_content_coords(card.tile, &content);
  const auto box = camera_view::name_box(lv_area_get_width(&content), lv_area_get_height(&content),
                                         lv_font_get_line_height(card.title_font));
  const int32_t w = box.w, h = box.h;
  lv_obj_t *off = lv_obj_create(nullptr);  // a screen never shown: the name is drawn for the snapshot alone
  lv_obj_t *label = lv_label_create(off);
  lv_obj_set_style_text_font(label, card.title_font, 0);
  lv_obj_set_style_text_color(label, theme::color(theme::CAMERA_INK), 0);
  lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_LEFT, 0);
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_set_size(label, w, h);
  lv_label_set_text(label, text);
  lv_obj_update_layout(off);
  lv_draw_buf_t *drawn = lv_snapshot_take(label, LV_COLOR_FORMAT_ARGB8888);
  lv_obj_delete(off);
  if (!drawn) return nullptr;
  // A snapshot holds what the label draws beyond its box too, as much on every side.
  const int32_t ext = std::max<int32_t>(0, (static_cast<int32_t>(drawn->header.w) - w) / 2);
  look.name = reinterpret_cast<const uint32_t *>(drawn->data);
  look.name_w = drawn->header.w;
  look.name_h = drawn->header.h;
  look.name_stride = drawn->header.stride / 4;
  look.name_x = content.x1 + box.x - ext - room.x;
  look.name_y = content.y1 + box.y - ext - room.y;
  return drawn;
#else
  return nullptr;
#endif
}
// A tile's spot: its card's room on the glass. A place's: the place's room, its camera and its fit.
inline live_spots::Spot tile_spot(const Widgets &w, const Tile &t) {
  live_spots::Spot spot;
  spot.kind = live_spots::Kind::TILE;
  spot.index = static_cast<uint32_t>(w.index);
  spot.entity = t.entity;
  spot.room = card_room(w);
  return spot;
}
inline live_spots::Spot place_spot(const Widgets &w, const lv_obj_t *place, const std::string &camera, bool contain,
                                   const live_view::Rect &room) {
  live_spots::Spot spot;
  spot.kind = live_spots::Kind::PLACE;
  spot.index = static_cast<uint32_t>(w.index);
  spot.place = place;
  spot.entity = camera;
  spot.contain = contain;
  spot.room = room;
  return spot;
}
inline uint32_t live_place_numbers = 0;
// Asks the app for a spot's stream: a live tile's with its picture's question (tile_picture::fields) and `live`, the
// card's size; a live place's with the question of its camera into the place's room. The question's number, or 0 when
// nothing could be asked (the spot asks again next round).
inline uint32_t live_spot_ask(const live_spots::Spot &spot) {
  if (spot.kind == live_spots::Kind::TILE) {
    Widgets *card = nullptr;
    each_card([&](Widgets &w) { if (w.index == spot.index && w.tile && on_glass(w)) card = &w; });
    if (!card || spot.index >= model.count) return 0;
    const Tile &t = model.tiles[spot.index];
    tile_picture::Ask a;
    if (inbox.empty() || !tile_ask(*card, t, a)) return 0;
    auto q = tile_question(a);
    q.live_w = spot.room.w;
    q.live_h = spot.room.h;
    // A board with a speaker: the app takes the camera's sound along already, so the full view has it at once.
    q.sound = live_view::has_speaker();
    const uint32_t number = tile_questions.ask(spot.index);
    picture_ask(q, "live", t.entity, number);
    ESP_LOGI("camera", "asked for tile %u live, %s at %dx%d", (unsigned) spot.index, t.entity.c_str(), spot.room.w, spot.room.h);
    return number;
  }
  if (spot.index >= model.count) return 0;
  auto *place = const_cast<lv_obj_t *>(static_cast<const lv_obj_t *>(spot.place));
  CardScope look(place);  // a plugin's live place asks in its card's look
  picture_question::Question q;
  q.owner = picture_question::Owner::PLUGIN_TILE;
  q.index = static_cast<int>(spot.index);
  q.key = model.tiles[spot.index].entity;
  q.sources = {picture_question::camera_source(spot.entity)};
  q.w = spot.room.w;
  q.h = spot.room.h;
  q.dark = theme::dark;
  picture_question::Place at;
  at.w = spot.room.w;
  at.h = spot.room.h;
  at.radius = lv_obj_get_style_radius(place, LV_PART_MAIN);
  at.fit = spot.contain ? picture_question::Fit::CONTAIN : picture_question::Fit::COVER;
  q.places = {at};
  q.live_w = spot.room.w;
  q.live_h = spot.room.h;
  const uint32_t number = ++live_place_numbers;
  picture_ask(q, "plive", spot.entity, number);
  ESP_LOGI("camera", "asked for a live place of tile %u, %s at %dx%d", (unsigned) spot.index, spot.entity.c_str(), spot.room.w, spot.room.h);
  return number;
}
// Opens a spot's stream as the app answered it: a tile's laid out as its card (the card's corners, the shade and the
// name over each picture), a place's laid in the place. NOT_NOW when the card is gone or not wanted now.
inline live_view::Handle live_spot_open(const live_spots::Spot &spot, const std::string &url) {
  // The one stream an S3 holds is still ending (a full view that just closed): not now, the spot asks again in its turn
  // instead of giving up for its stills.
  if (live_view::ending() && !live_view::room_for_another()) return live_spots::Spots::NOT_NOW;
  if (spot.kind == live_spots::Kind::TILE) {
    Widgets *card = nullptr;
    each_card([&](Widgets &w) { if (w.index == spot.index && spot.index < model.count && live_tile_wanted(w, model.tiles[spot.index])) card = &w; });
    if (!card) return live_spots::Spots::NOT_NOW;
    const Tile &t = model.tiles[spot.index];
    CardScope scope(*card);  // the stream's colours (loader, name, badge, ground) in the card's look
    live_view::Look look;
    look.tile = true;
    look.contain = url.find("fit=contain") != std::string::npos;
    look.radius = lv_obj_get_style_radius(card->tile, LV_PART_MAIN);
    look.ground = live_view::rgb565(card_ground(*card));
    look.fade = t.overlay;
    live_loader(look);
    lv_draw_buf_t *name = t.overlay ? live_name(look, *card, spot.room) : nullptr;
    if (name)
      ESP_LOGI("camera", "live tile %u: its name %dx%d at %d,%d of the card's %dx%d", (unsigned) spot.index, (int) look.name_w,
               (int) look.name_h, (int) look.name_x, (int) look.name_y, spot.room.w, spot.room.h);
    lv_draw_buf_t *badge = live_badge(look, spot.room.w, spot.room.h);
    const live_view::Handle handle = live_view::open(url, spot.room, look);
#if LV_USE_SNAPSHOT
    if (name) lv_draw_buf_destroy(name);
    if (badge) lv_draw_buf_destroy(badge);
#endif
    return handle;
  }
  Widgets *card = nullptr;
  each_card([&](Widgets &w) { if (w.index == spot.index && w.plugin && on_glass(w)) card = &w; });
  if (!card || spot.index >= model.count) return live_spots::Spots::NOT_NOW;
  const Tile &t = model.tiles[spot.index];
  auto *place = const_cast<lv_obj_t *>(static_cast<const lv_obj_t *>(spot.place));
  CardScope scope(*card);
  live_view::Look look;
  look.tile = true;
  look.contain = url.find("fit=contain") != std::string::npos;
  look.radius = lv_obj_get_style_radius(place, LV_PART_MAIN);
  look.ground = live_view::rgb565(t.transparent ? card_ground(*card) : card_surface(*card));
  look.fade = false;
  live_loader(look);
  return live_view::open(url, spot.room, look);
}
inline void live_spots_bind() {
  if (spots.open) return;
  spots.ask = live_spot_ask;
  spots.open = live_spot_open;
  spots.close = [](live_view::Handle handle) { live_view::close(handle); };
  spots.log = [](const live_spots::Spot &spot, const char *what) {
    ESP_LOGD("camera", "%s of tile %u, %s: %s", spot.kind == live_spots::Kind::TILE ? "the live tile" : "a live place",
             (unsigned) spot.index, spot.entity.c_str(), what);
  };
}
// Every live tile and place stops at once: a page turns, a card opens over them. They start again on a round with the
// page clear.
inline void live_tiles_halt() { spots.halt(); }
// Every round of the pictures (250 ms): what streams, what stops, what asks.
inline void live_tiles_round() {
  live_spots_bind();
  const uint32_t now = esphome::millis();
  // A new firmware on trial streams nothing: the tiles keep their stills until it is confirmed (boot_trial.h).
  const bool clear = page_clear() && model.ready() && !boot_trial::on(now);
  spots.begin();
  if (clear) {
    // A plugin's live places (0.17), asked only of an app that reads questions.
    if (app_reads_questions)
      live_places_each([&](Widgets &w, lv_obj_t *place, const std::string &camera, bool contain) {
        lv_obj_update_layout(place);
        const auto room = object_room(place);
        if (room.w < 64 || room.h < 64 || drawn_over(place, room.x, room.y, room.w, room.h)) return;
        spots.want(place_spot(w, place, camera, contain, room));
      });
    // At most hw::caps().live_tiles camera tiles stream at once (the picture engine's, docs/PLATFORM_PLAN.md 4.1), the
    // first by tile order; the rest keep their stills, which a live tile loads every 15 s anyway (its asker's `every`). The app gives those tiles
    // the same count from the hello, and the editor says so on the fifth tile. Logged when the count of tiles left out
    // changes, so the log says which page did it.
    size_t streaming = 0, left_out = 0;
    each_card([&](Widgets &w) {
      if (w.index >= model.count) return;
      const Tile &t = model.tiles[w.index];
      if (!live_tile_wanted(w, t)) return;
      if (streaming >= hw::caps().live_tiles) { ++left_out; return; }
      ++streaming;
      spots.want(tile_spot(w, t));
    });
    static size_t left_out_before = 0;
    if (left_out != left_out_before) {
      left_out_before = left_out;
      if (left_out) ESP_LOGI("camera", "%u live tiles stream; %u more on the page keep their stills (at most %u at once)",
                             (unsigned) streaming, (unsigned) left_out, (unsigned) hw::caps().live_tiles);
    }
  }
  spots.end(now);
}
// The app's answer to a live tile's question: its stream, laid out as its card.
inline void live_tile_answer(size_t index, const std::string &url) {
  spots.answer(live_spots::Kind::TILE, static_cast<uint32_t>(index), url, page_clear());
}
// The app's answer to a live place's question: its stream, laid in the place. No stream (the camera is not the tile's
// own, a screen that cannot stream it): the place keeps its stills.
inline void live_place_answer(uint32_t number, const std::string &url) { spots.answer(number, url, page_clear()); }
// The board's 50 ms interval (features/camera.yaml), beside the downloads' hand-off: what each stream did, and live tiles
// stopped the moment something lies over their page (a card, the camera full screen, an alert, the settings).
// Something came over a live picture (the update's progress, a toast, a sheet): it stops at once, and starts again once
// nothing lies over it. On the board's interval, and as LVGL starts every drawing (LV_EVENT_REFR_START), before it draws:
// also one the main loop does not run for, as ESPHome's update holds it and has its progress drawn at once (ota_draw,
// lv_refr_now), where the live pictures went on over it (2026-10-10, the D1001).
inline void live_stop_covered() {
  if (spots.empty() && !(camera_root && camera.stream.live && camera.stream.handle >= 0)) return;
  lv_obj_update_layout(lv_layer_top());  // what was made just now has its place before it is asked for it
  lv_obj_update_layout(lv_layer_sys());
  if (!spots.empty() && !page_clear()) live_tiles_halt();
  const uint32_t now = esphome::millis();
  for (size_t i = 0; i < spots.all().size(); ++i) {
    if (spots.all()[i].handle < 0) continue;
    const live_spots::Spot spot = spots.all()[i].spot;  // its own copy: covered() changes the entry
    if (spot.kind == live_spots::Kind::PLACE) {
      bool there = false;
      live_places_each([&](Widgets &, lv_obj_t *place, const std::string &, bool) { if (place == spot.place) there = true; });
      auto *place = const_cast<lv_obj_t *>(static_cast<const lv_obj_t *>(spot.place));
      const bool moved = there && !(object_room(place) == spot.room);
      if (!there || moved || drawn_over(place, spot.room.x, spot.room.y, spot.room.w, spot.room.h)) {
        const char *why = !there ? "it is gone" : moved ? "it moved" : drawn_over_by ? drawn_over_by : "nothing over it";
        ESP_LOGI("camera", "a live place of tile %u stops streaming: %s", (unsigned) spot.index, why);
        spots.covered(spot, now, why);
      }
      continue;
    }
    Widgets *card = nullptr;
    each_card([&](Widgets &w) { if (w.index == spot.index && w.tile) card = &w; });
    // Its picture lies at the room it asked for, on the glass: a card that moved (a page animated, a layout made anew)
    // leaves the picture where it was, so it stops before LVGL draws, and asks again from where the card is now.
    const bool moved = card && !(card_room(*card) == spot.room);
    if (!card || moved || drawn_over(card->tile, spot.room.x, spot.room.y, spot.room.w, spot.room.h)) {
      const char *why = moved ? "its card moved" : drawn_over_by ? drawn_over_by : "nothing over it";
      ESP_LOGI("camera", "tile %u stops streaming: %s", (unsigned) spot.index, why);
      spots.covered(spot, now, why);
    }
  }
  if (camera_root && camera.stream.live && camera.stream.handle >= 0) {
    const auto area = live_area();
    if (drawn_over(camera_root, area.x, area.y, area.w, area.h)) {
      ESP_LOGI("camera", "the camera stops streaming: %s over it", drawn_over_by ? drawn_over_by : "nothing");
      live_view::close(camera.stream.handle);
      camera.stream.stopped();
      camera_warm(false);
      camera_sound_waiting = false;
    }
  }
}
inline void live_tick() {
  static bool hooked = false;
  if (!hooked && live_view::available()) {
    hooked = true;
    lv_display_add_event_cb(lv_display_get_default(), [](lv_event_t *) { live_stop_covered(); }, LV_EVENT_REFR_START, nullptr);
  }
  live_stop_covered();
  if (view_wait.waiting()) {
    const uint32_t now = esphome::millis();
    static uint32_t told_at = 0;
    if (!camera_root || !live_wanted() || camera.stream.live) {
      view_wait.link.clear();  // the view closed meanwhile
    } else if (live_view::ViewWait::may_open(live_view::ending(), live_view::beside(), now - view_wait.since)) {
      live_begin(view_wait.link);
    } else if (now - view_wait.since >= live_view::ViewWait::WAIT_MS && told_at != view_wait.since) {
      told_at = view_wait.since;
      ESP_LOGW("camera", "the page's stream did not end in %u ms: the full view waits for it (one stream at once)",
               (unsigned) live_view::ViewWait::WAIT_MS);
    }
  }
  live_view::tick([](live_view::Handle handle, live_view::Event event) {
    if (camera_root && camera.stream.is(handle)) {
      if (event == live_view::Event::FIRST) {
        ESP_LOGI("camera", "live: first picture %u ms after the camera opened, internal RAM at least %d KB meanwhile",
                 (unsigned) (esphome::millis() - camera_opened_at), camera_ram_low());
        camera.shown = true;
        camera_note_text("");  // the spinner goes; LVGL no longer draws there while the camera streams
        camera_warm(true);     // in the top bar until the camera is live (LIVE, at once for a picture that is)
        // LVGL draws the whole glass once more, now that the picture lies in its spot and the keep-out holds it: the
        // bands of the room around the picture, the top bar, and anything a live tile's last copy left under the view
        // before it stopped (live_begin). The start's twin of the redraw at a full view's end (live_view::tick).
        glass::redraw_all();
      } else if (event == live_view::Event::LIVE) {
        camera_warm(false);
        if (camera_sound_waiting) camera_sound_show();  // its place is free now
        camera_sound_waiting = false;
      } else if (event == live_view::Event::SOUND) {
        if (camera_warming()) camera_sound_waiting = true;
        else camera_sound_show();
      } else if (event == live_view::Event::FAILED || event == live_view::Event::TURNED) {
        camera_warm(false);
        camera_sound_waiting = false;  // a new stream tells its sound again
        // Asked again: a new stream for the glass as it is now, or after TRIES failures the stills (ViewStream::ended).
        ESP_LOGI("camera", "live %s for %s", event == live_view::Event::FAILED ? "failed" : "turned", camera.entity.c_str());
        camera.stream.ended(event);
        pictures_round();
      }
      return;
    }
    // A live tile or place (live_spots.h): its first picture, or a stream that ended, failed or turned.
    spots.event(handle, event, esphome::millis());
  });
}

// Asks ESP Screen Manager for the full view's picture (app 0.2.66+ answers with op "camera"): a camera, a map tile
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
