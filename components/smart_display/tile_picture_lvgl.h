// A tile's own picture.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in tile_picture.h.
// What proves it: tests/test_tile_picture.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- A tile's own picture (tile_picture.h, GitHub #183) ----
// A live camera, a media tile's album cover, a favourite and a map show a picture the app paints for exactly their
// place: the whole card (card_art) or the icon's circle. Every such tile asks for its own picture, at its own pace, in
// the board's third download slot, and the store keeps it under its own key: a new track replaces that tile's cover
// and nothing else, a camera refreshes at its own tile's pace, and no picture comes smaller because of another one on
// the page. A tile on the glass asks at once; a tile of a kept page has a picture that does not refresh (a cover, a
// favourite, a map) fetched ahead while the screen is in use, after everything on the glass, as a media card's cover is
// (card_picture_wants). Until its next picture is here, a card keeps the one it shows of the same place.
inline tile_picture::Questions tile_questions;
inline bool tile_pictures_supported() { return static_cast<bool>(camera_live.load); }
// The detail card a tap opens (detail_root) is up.
inline bool detail_shown() { return detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN); }
// Any card over the page: the detail card, a lamp's colour card, and the effects or lamps page a card opens. One notion
// for all of them, which the pictures, the pages prepared ahead, a page turn and the live tiles all ask: the colour card
// in C++ was none of them at first, and the live tiles streamed on over it (2026-10-10, the D1001).
inline bool card_open() { return detail_shown() || colour_shown() || effects_page::visible() || group_page::visible(); }
// What a card's picture is: its place measured on the card as LVGL laid it out, how the app paints it, and its pace.
// False when the tile shows no picture, or the card has no size yet.
inline bool tile_ask(const Widgets &w, const Tile &t, tile_picture::Ask &a) {
  // The question's look (a.dark, part of the picture's key) and its ground are the card's (docs/THEME.md).
  CardScope look(w);
  // A plugin tile's places (plugin API 0.10): its parts, measured by the host.
  if (w.plugin) return plugin_host::picture_ask(w, t, a);
#ifdef SD_MOD_VACUUM_CARD
  // A robot's map on its larger tile: the map's place, on the frame's colour, drawn by the app from the robot's map.
  if (vacuum_face::picture(w)) {
    int x, y, width, height;
    if (!t.pictured() || !vacuum_face::map_place(w, x, y, width, height) || width <= 0 || height <= 0) return false;
    a.frame = tile_picture::frame(width, height, 0, 0, theme::hex(theme::TRACK), theme::hex(theme::TRACK), picture_cap());
    a.index = w.index;
    a.entity = t.entity;
    a.mark = t.extra().vacuum ? t.extra().vacuum->map_mark : std::string();
    a.dark = theme::dark;
    a.drawn = true;
    a.source = picture_question::vacuum_source(t.entity);
    return true;
  }
#endif
  if (!w.tile || !w.circle || !t.pictured()) return false;
  const bool art = card_art(t);
  lv_obj_t *place = art ? w.tile : w.circle;
  lv_obj_update_layout(place);
  const int width = lv_obj_get_width(place), height = lv_obj_get_height(place);
  if (width <= 0 || height <= 0) return false;
  const int radius = art ? lv_obj_get_style_radius(w.tile, LV_PART_MAIN) : width / 6;
  const uint32_t ground = t.transparent || art ? card_ground(w) : card_surface(w);
  // An album cover and a favourite carry their words on the picture, dimmed whole as a cover over a card is.
  const int shade = art && (t.cover_tile() || t.favorite()) ? tile_picture::SHADE : 0;
  // A picture over the cap sits in the middle of its card on the dark of a camera's page, which its corners round over.
  a.frame = tile_picture::frame(width, height, radius, shade, ground, theme::hex(theme::CAMERA_PAGE), picture_cap());
  a.index = w.index;
  a.entity = t.entity;
  // A favourite's picture is what it plays (firmware 0.24.0+), never the player's cover; a map's mark is where its
  // people are (app 0.4.33). A camera has none: its next picture is the same picture, newer.
  a.mark = t.cover_tile() ? t.extra().media_picture : t.favorite() ? t.extra().fav_mark : t.is_map() ? t.extra().map_mark : std::string();
  a.circle = lv_obj_get_style_width(w.circle, LV_PART_MAIN);
  a.dark = theme::dark;
  // A tile set to Live (pace 0) that cannot stream (another board, no room, an app without streams) refreshes its
  // still at the pace every camera tile takes by default.
  a.every = t.live() ? (t.refresh ? t.refresh : 15u) * 1000u : 0;
  a.drawn = t.is_map();
  return true;
}
// Asks the app for a tile's picture: `esphome.screen_camera` as a page of one tile (tile_picture::fields), numbered so
// the answer finds its tile.
// A tile's question (tile_picture::question): a tile's own picture, or a plugin tile's places (plugin API 0.10).
inline picture_question::Question tile_question(const tile_picture::Ask &a) {
  const bool plugin = !a.parts.empty();
  auto q = tile_picture::question(a, plugin ? picture_question::Owner::PLUGIN_TILE : picture_question::Owner::TILE,
                                  plugin ? a.entity : std::string());
  q.cap = picture_cap().bytes;
  return q;
}
inline void tile_picture_request(const tile_picture::Ask &a) {
  if (inbox.empty()) return;
  picture_ask(tile_question(a), "live", a.entity, tile_questions.ask(a.index));
  ESP_LOGI("camera", "asked for the picture of tile %u, %s", (unsigned) a.index, a.entity.c_str());
}
// Whether a card on the glass waits for its picture: until the tile's first try at it (here, failed, or the app has
// none). A refresh of a picture on the glass never starts the spinner. A screen that cannot ask right now (after a
// restart, before the app has sent the layout again; Home Assistant away) waits for nothing: the card shows its head as
// every card does then, not a spinner that never ends.
inline bool tile_picture_waiting(const Widgets &w, const Tile &t) {
  if (!tile_pictures_supported() || !fresh() || !t.pictured() ||
      !camera_view::pictures_on_glass(tiles_seen(), card_open(), camera_root != nullptr)) return false;
  if (w.picture && !lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN)) return false;
  const auto owner = owners::tile(w.index);
  return !loader.has(owner) || !loader.settled_for(owner);
}
// The card's picture in its place: the whole card, or the icon's circle of `size` at x, y. The picture is the one the
// card's last round asked for (art_key, card_picture_wants), drawn at its own pixels in the middle of its place (one
// over the cap is smaller, on the card's dark). Without it the card keeps the one it shows of the same place (the last
// track's cover, a map before someone moved) until the next is here.
inline void tile_picture_place(Widgets &w, const Tile &t, int size, int x, int y) {
  CardScope scope(w);  // also reached from a picture's arrival, outside render_slot
  w.art_size = size; w.art_x = x; w.art_y = y;
#ifdef SD_MOD_VACUUM_CARD
  if (vacuum_face::picture(w)) { vacuum_face::picture_place(w, t); return; }
#endif
  // A plugin tile's picture is an atlas of its places' pieces (plugin API 0.10): the host lays each on its place.
  if (w.plugin) {
    const bool its = tile_picture::belongs(w.art_key, w.index, t.entity);
    lv_image_dsc_t *src = its ? picture_of(w.art_key) : nullptr;
#if LV_USE_IMAGE
    // Its last picture stays on its places while the next one comes (other addresses in the same frame: a carousel that
    // turned), as a tile's own picture does; the store keeps it, since the places still draw it.
    if (!src && its && pictures_kept()) {
      const auto *held = pictures.holder(static_cast<const lv_image_dsc_t *>(plugin_host::picture_drawn(w)));
      if (held && tile_picture::place_of(held->key) == tile_picture::place_of(w.art_key)) {
        ESP_LOGD("picture", "tile %u keeps %s until %s", (unsigned) w.index, held->key.c_str(), w.art_key.c_str());
        return;
      }
    }
#endif
    plugin_host::picture_place(w, src);
    return;
  }
#if LV_USE_IMAGE
  const bool mine = t.pictured() && tile_picture::belongs(w.art_key, w.index, t.entity);
  lv_image_dsc_t *src = mine ? picture_of(w.art_key) : nullptr;
  if (!src && mine && w.picture && pictures_kept()) {
    auto *held = pictures.holder(static_cast<const lv_image_dsc_t *>(lv_image_get_src(w.picture)));
    if (held && tile_picture::place_of(held->key) == tile_picture::place_of(w.art_key)) {
      src = &held->image;
      ESP_LOGD("picture", "tile %u keeps %s until %s", (unsigned) w.index, held->key.c_str(), w.art_key.c_str());
    }
  }
  const bool background = card_art(t);
  if (src) {
    if (!w.picture) {
      w.picture = lv_image_create(w.tile);
      lv_obj_remove_flag(w.picture, LV_OBJ_FLAG_CLICKABLE);
    }
    lv_image_set_src(w.picture, src);
    const int left = lv_obj_get_style_space_left(w.tile, LV_PART_MAIN), top = lv_obj_get_style_space_top(w.tile, LV_PART_MAIN);
    const int width = background ? lv_obj_get_width(w.tile) : size, height = background ? lv_obj_get_height(w.tile) : size;
    const int pw = src->header.w, ph = src->header.h;
    lv_obj_set_pos(w.picture, (background ? -left : x) + (width - pw) / 2, (background ? -top : y) + (height - ph) / 2);
    lv_obj_set_size(w.picture, pw, ph);
    if (background) {
      lv_obj_move_to_index(w.picture, 0);
      // The card behind a smaller picture: dark while it is smaller, the card's own colour again once it fills it.
      const bool dark = pw < width || ph < height;
      set_color(w.tile, LV_STYLE_BG_COLOR, dark ? theme::color(theme::CAMERA_PAGE) : lv_color_hex(card_surface(w)));
      set_number(w.tile, LV_STYLE_BG_OPA, t.transparent && !dark ? LV_OPA_TRANSP : LV_OPA_COVER);
    }
    lv_obj_remove_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
    lv_obj_invalidate(w.picture);
  } else if (w.picture) {
    // Hidden, it lets go of its picture too: a picture object still pointing at a copy counts as drawing it, and the
    // store never frees what a card draws.
    lv_image_set_src(w.picture, nullptr);
    lv_obj_add_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
  }
  // The icon's circle gives way to a picture in its place. Over a whole card the card's own drawing decides (a camera
  // card hides it under its picture): a picture put on its card the moment it came (tile_picture_done) never shows the
  // circle, which flashed the camera's icon through the picture at every refresh until the card was drawn again.
  if (!background) set_hidden(w.circle, src != nullptr);
  else if (!src) set_hidden(w.circle, false);
#else
  (void) w; (void) t; (void) size; (void) x; (void) y;
#endif
}
// Background downloads share the drawing loop. Keep the title readable but still until the picture is placed (or its
// first try is over), then reuse LVGL's reading pause. No extra animation or per-tile timer is needed.
inline bool tile_picture_marquee_ready(const Widgets &w, const Tile &t) {
  if (!card_art(t) || !tile_pictures_supported()) return true;
  // A picture already on the glass keeps its title scrolling through a refresh: pausing it for every camera round
  // started a long title from its first letter again, so it was never read to the end (firmware 0.3.1).
  if (w.picture && !lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN)) return true;
  return !tile_picture_waiting(w, t);
}
// The picture of a tile came, or did not (the app has none, the download failed). One that came goes on its card at
// once, on the glass or on a kept page, in the place the card gave it, as a media card's cover does (tile_cover_arrived):
// a picture no card draws is the first the store lets go when it is over its budget, and one let go is fetched again.
// The card then draws itself again, on the glass now and on a kept page when that page comes back (its change number).
inline void tile_picture_done(size_t index, picture_loader::Outcome outcome) {
  if (!shows(outcome))
    ESP_LOGI("camera", "tile %u: %s", (unsigned) index, outcome == picture_loader::Outcome::NONE ? "no picture" : "the picture failed");
  else if (outcome == picture_loader::Outcome::LOADED)
    ESP_LOGI("camera", "tile %u: picture loaded", (unsigned) index);
  else
    ESP_LOGD("picture", "tile %u: shows the picture the store kept", (unsigned) index);
  // A plugin card that kept its last picture while asking lets go of it when the next one did not come: its places show
  // their blocks, not a picture of the addresses before.
  if (!shows(outcome) && index < model.count)
    each_card([&](Widgets &w) {
      if (w.index != index || !w.plugin) return;
      plugin_host::picture_place(w, nullptr);
      plugin_host::picture_outcome(w, outcome);  // the plugin hears it (0.17, Tile::on_picture)
    });
  if (shows(outcome) && index < model.count)
    each_card([&](Widgets &w) {
      if (w.index != index || !w.tile) return;
      tile_picture_place(w, model.tiles[index], w.art_size, w.art_x, w.art_y);
      ESP_LOGD("picture", "tile %u: %s on its card %s", (unsigned) index, w.art_key.c_str(), on_glass(w) ? "on the glass" : "of a kept page");
    });
  refresh_tile(index, redraw_log::TileWhy::picture);
}
// The app's answer to a tile's question, found by the question's number: a link, or "" when it has no picture.
inline void tile_picture_answer(uint32_t number, const std::string &url, uint32_t now) {
  const int index = tile_questions.answered(number);
  ESP_LOGD("picture", "answer %u for tile %d: %s", (unsigned) number, index, url.empty() ? "no picture" : url.c_str());
  if (index >= 0 && live_view::is_stream(url)) { live_tile_answer(static_cast<size_t>(index), url); return; }
  if (index >= 0) loader.answer(tile_picture::tag(static_cast<size_t>(index)), url, now);
}
// Every tile asks for its picture anew: another layout (what the store kept for the last one goes with forget_kept), or
// a render that wants the question again (tools/render, render_live_reset).
inline void slot_letgo(picture_loader::Slot slot);
inline void tile_pictures_reset() {
  tile_questions.clear();
  each_card([](Widgets &w) {
    if (!w.art_key.empty() && w.index < grid.max_tiles()) loader.release(owners::tile(w.index));
    w.art_key.clear();
  });
  slot_letgo(picture_loader::Slot::LIVE);
}
// A download let go of its slot (a board without the store, or a picture the store had no room for, drew it): every
// card that drew it lets go first and draws itself again.
inline void tile_pictures_letgo() {
#if LV_USE_IMAGE
  auto *download = camera_live.source ? camera_live.source() : nullptr;
  if (!download) return;
  each_card([&](Widgets &w) {
    bool took = plugin_host::picture_let_go(w, download);
    for (lv_obj_t *picture : {w.picture, face_picture(w)})
      if (draws(picture, download)) {
        lv_image_set_src(picture, nullptr);
        lv_obj_add_flag(picture, LV_OBJ_FLAG_HIDDEN);
        took = true;
      }
    if (took && w.index < model.count) refresh_tile(w.index, redraw_log::TileWhy::picture);
  });
#endif
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
