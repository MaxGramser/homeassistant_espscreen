// What came of a picture, for its owner, and what every picture wants each round.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in picture_loader.h.
// What proves it: tests/test_picture_loader.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- What came of a picture, for its owner, and the downloads' end ----
// The view's picture: a camera, a map (its focus and the look are part of it) or the screensaver's (its track's picture
// and colour are part of it, so another track is another picture).
inline std::string camera_key() {
  std::string key = "camera|" + camera.entity;
  if (camera_map_index >= 0) key += "|" + map_focus + (theme::dark ? "|dark" : "") + (map_move.none() ? "" : "|" + map_move.text());
  // The cover's colour only shows beside a cover on long glass (saver_view::shape): on square glass it is no new picture.
  if (saver_camera) {
    key += "|saver|" + saver_now.picture + (saver_now.motion ? "|moves" : "");
    if (saver_view::shape(overlay_card::screen_width(), overlay_card::screen_height()) != saver_view::Shape::fill) key += "|" + saver_now.ground;
  }
  return key;
}
inline std::string camera_tag() { return (saver_camera ? "saver|" : "full|") + camera.entity; }
// A photo of the screensaver that moves (app 0.4.89, picture_motion.h): the app cut it larger than the glass, and the
// glass shows its piece of it, a pixel further every PIXEL_MS. One that came at the glass's size (a screen whose memory
// has no room for the larger one) stands still, as every other picture of the screensaver.
inline picture_motion::Path saver_motion;
inline uint32_t saver_motion_since = 0;
inline picture_motion::Offset saver_motion_shown{-1, -1};
inline void saver_motion_place(uint32_t now) {
  if (!camera_picture || !saver_motion.moves()) return;
  const auto o = picture_motion::at(saver_motion, now - saver_motion_since);
  if (o.x == saver_motion_shown.x && o.y == saver_motion_shown.y) return;
  saver_motion_shown = o;
  lv_image_set_offset_x(camera_picture, -o.x);
  lv_image_set_offset_y(camera_picture, -o.y);
}
inline void saver_motion_start(const lv_image_dsc_t *src) {
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  saver_motion = saver_now.kind == "photos" && saver_now.motion && src
                     ? picture_motion::path(src->header.w, src->header.h, width, height, saver_now.picture)
                     : picture_motion::Path{};
  saver_motion_shown = {-1, -1};
  if (!camera_picture) return;
  if (!saver_motion.moves()) {
    lv_image_set_offset_x(camera_picture, 0);
    lv_image_set_offset_y(camera_picture, 0);
    lv_image_set_inner_align(camera_picture, LV_IMAGE_ALIGN_COVER);
    return;
  }
  lv_image_set_inner_align(camera_picture, LV_IMAGE_ALIGN_TOP_LEFT);
  saver_motion_since = esphome::millis();
  saver_motion_place(saver_motion_since);
}
// Every 250 ms (tick): the next pixel, only when it is due.
inline void saver_motion_tick(uint32_t now) { if (saver_camera) saver_motion_place(now); }
// The full view's picture is here, or not.
inline void view_done(picture_loader::Outcome outcome) {
  if (!camera_root) return;
  if (!shows(outcome)) {
    if (!camera.shown && !saver_camera) camera_note_text(tr(txt::camera_no_image));
    if (map_waiting) lv_obj_add_flag(map_waiting, LV_OBJ_FLAG_HIDDEN);  // no picture comes: nothing to wait for
    saver_follow_pending();
    return;
  }
  lv_image_dsc_t *src = picture_of(camera_key());
  if (!src) return;
  picture_memory("after", "camera", src->header.w * src->header.h);
  camera.shown = true;
  const bool first = camera_picture == nullptr;
  camera_show(camera_root, camera_picture, src, outcome == picture_loader::Outcome::LOADED);
  if (camera_picture && saver_camera) saver_motion_start(src);
  if (first && camera_picture && saver_camera) {
    // The screensaver's picture is the whole glass; one that came smaller (the size cap, picture_store::MAX_BYTES) is
    // scaled to it, the same proportions. Its words lie over it. A photo that moves shows the glass's piece of it.
    lv_obj_set_size(camera_picture, lv_pct(100), lv_pct(100));
    if (!saver_motion.moves()) lv_image_set_inner_align(camera_picture, LV_IMAGE_ALIGN_COVER);
    saver_words();
  } else if (camera_picture && saver_camera && saver_words_due) {
    // The next track's picture is on the glass: its words come with it (saver_follow).
    saver_words();
  } else if (first && camera_picture) {
    camera_note_text("");
#ifdef SD_MOD_DOORBELL
    if (doorbell::shown()) doorbell::picture_shown(camera_picture);
#endif
    if (camera_back) lv_obj_move_foreground(camera_back);
    lv_obj_move_foreground(camera_title);
    // A map's card (firmware 0.21.0+) may have come before its first picture: it lies over the map as the bar does.
    if (map_card_obj) lv_obj_move_foreground(map_card_obj);
    map_keys_place();
  }
  // A map's picture of the view its keys asked for (dev): it shows that view as it is, unmoved.
  if (camera_map_index >= 0 && camera_picture) {
    map_move_shown = map_move;
    map_preview();
    map_waiting_show();
  }
  saver_follow_pending();
}
// The alert's picture: its camera, for this alert.
inline std::string alert_key() { return "alert|" + alert_camera + "|" + std::to_string(alert_shown_at); }
inline void alert_done(picture_loader::Outcome outcome) {
  if (!shows(outcome)) { ESP_LOGI("camera", "alert picture failed"); return; }
  // Only for the alert on screen: a picture that arrives after its alert was dismissed or replaced is not shown.
  if (alert_camera.empty() || !alert_frame || lv_obj_has_flag(alert_frame, LV_OBJ_FLAG_HIDDEN)) return;
  auto *source = picture_of(alert_key());
  if (!source || !source->data) return;
  // The card makes room for the picture it got, in that picture's proportions (firmware 0.2.103+): ESP Screens sized
  // it for this frame with the same rule (alert_layout.py), so it fills the frame; the frame then takes the picture's
  // own size where the layout put it, so a pixel of rounding on either side shows no edge.
  const int picture_w = source->header.w, picture_h = source->header.h;
  const auto card = alert_place(true, picture_w, picture_h);
  if (card.image_w <= 0 || card.image_h <= 0) return;  // no room for a picture on this glass after all
  if (picture_w <= card.image_w && picture_h <= card.image_h) {
    lv_obj_set_pos(alert_frame, card.image_x + (card.image_w - picture_w) / 2, card.image_y + (card.image_h - picture_h) / 2);
    lv_obj_set_size(alert_frame, picture_w, picture_h);
  }
  // The picture takes the frame's radius, the alert card's own (features/camera.yaml sets it on the frame).
  camera_show(alert_frame, alert_picture, source, outcome == picture_loader::Outcome::LOADED, lv_obj_get_style_radius(alert_frame, LV_PART_MAIN));
  if (alert_picture && alert_frame_icon) lv_obj_add_flag(alert_frame_icon, LV_OBJ_FLAG_HIDDEN);
  ESP_LOGI("camera", "alert picture shown");
}
// A slot's download let go (another picture lands in it, or the download broke off): a picture drawn from it goes first.
// Only where the store did not keep it (a board without the store, or no room).
inline void slot_letgo(picture_loader::Slot slot) {
  const int s = static_cast<int>(slot);
  if (slot_key[s].empty()) return;
  const std::string had = slot_key[s];
  slot_key[s].clear();
  if (slot == picture_loader::Slot::LIVE) { tile_pictures_letgo(); return; }
  if (slot == picture_loader::Slot::THUMB) {
    if (alert_picture) { lv_obj_delete(alert_picture); alert_picture = nullptr; }
    return;
  }
  cover_forget_pictures();
#if LV_USE_IMAGE
  if (camera_picture) { lv_image_set_src(camera_picture, nullptr); }
#endif
  media_library::art_forget_download();
  plugin_host::card_letgo(camera_full.source ? camera_full.source() : nullptr);
}
// A download ended (picture_fetch, any slot; packages/features/camera.yaml): the store takes the picture over under its
// key, a 304 keeps what the store has, and its owner shows it. Without room in the store the owner draws the download
// itself until the slot loads another picture.
inline void picture_done(picture_loader::Slot slot, bool ok, bool cached) {
  const uint32_t now = esphome::millis();
  auto &hooks = slot_hooks(slot);
  // A 304 for a picture the store let go meanwhile: the slot handed its pixels over, so nothing is left to show. The link
  // forgets its ETag (release) and the load counts as failed, so the loader fetches the picture whole.
  if (ok && cached && pictures_kept()) {
    const std::string asked = loader.loading_key(slot);
    // The same bytes as the picture its owner had before (the ETag that went along with this link): that picture is
    // this key's too, filed again without a copy, so the card on the glass changes nothing.
    if (!asked.empty() && !pictures.entry(asked) && pictures.rekey(loader.loading_had(slot), asked, now))
      ESP_LOGD("picture", "%s came back unchanged: the picture its owner showed is this one", asked.c_str());
    const lv_image_dsc_t *held = hooks.source ? hooks.source() : nullptr;
    if (picture_store::load_again(true, ok, cached, !asked.empty(), !asked.empty() && pictures.entry(asked), held && held->data)) {
      ESP_LOGD("picture", "%s came back unchanged, but the store let it go: loaded again", asked.c_str());
      if (hooks.release) hooks.release();
      ok = cached = false;
    }
  }
  const bool ahead = loader.loading_rank(slot) == picture_loader::Rank::AHEAD;
  const std::string key = loader.loaded(slot, ok, now);
  if (!key.empty()) {
    lv_image_dsc_t *src = hooks.source ? hooks.source() : nullptr;
    const int s = static_cast<int>(slot);
    bool kept = false;
    if (src) picture_memory("after", key.substr(0, key.find('|')).c_str(), src->header.w * src->header.h);
    const auto arrival = picture_store::arrival(pictures_kept(), cached, pictures.entry(key) != nullptr, src && src->data);
    // Fetched ahead, and the spare room it fitted is gone meanwhile (a picture for the glass came first): it is not
    // kept, so it never makes another picture go; it loads when its page comes back (GitHub #415).
    if (ahead && arrival == picture_store::Arrival::adopt && src && !pictures.fits_ahead(src->data_size)) {
      ESP_LOGI("picture", "%s came for a page out of sight, but the spare room is gone: it waits for its page", key.c_str());
      if (hooks.release) hooks.release();
      pictures_round();
      return;
    }
    if (arrival == picture_store::Arrival::touch) {
      pictures.touch(key, now);
      kept = true;
    } else if (arrival == picture_store::Arrival::adopt) {
      // One picture in memory once (docs/PICTURES.md, "Memory"): the store takes the download's own buffer and the slot
      // lets go of it; no copy, and the picture on the glass until now goes once its cards show this one. A slot that
      // cannot give its buffer away is copied once into one the store owns.
      lv_image_dsc_t taken = *src;
      void *copy = nullptr;
      if (!hooks.hand_over && (copy = kept_allocate(src->data_size))) {
        std::memcpy(copy, src->data, src->data_size);
        taken.data = static_cast<const uint8_t *>(copy);
      }
      kept = (hooks.hand_over || copy) && pictures.adopt(key, taken, now, hooks.etag ? hooks.etag() : std::string()) != nullptr;
      if (!kept && copy) kept_free(copy);
      if (kept && hooks.hand_over) hooks.hand_over();
      else if (kept && hooks.release) hooks.release();  // the copy is the store's: the slot's own goes
      if (!kept) ESP_LOGW("picture", "no room to keep %s", key.c_str());
    }
    if (!kept) { slot_key[s] = key; slot_at[s] = now; }
    loader.arrived(key, cached);
  }
  pictures_round();
}

// ---- What every picture wants, each round ----
inline void camera_want() {
  if (!camera_root || !camera.open() || !pictures_awake()) return;
  if (camera.stream.live) return;  // its pictures stream (live_view.h); the loader has nothing to fetch
  picture_loader::Want w;
  w.key = camera_key();
  w.tag = camera_tag();
  w.slot = picture_loader::Slot::FULL;
  w.rank = picture_loader::Rank::VIEW;
  // A camera at its pace, the screensaver's cover once; a map is drawn by the app, so it is always there to be had.
  w.every = camera.once ? 0 : camera.every;
  w.drawn = camera_map_index >= 0;
  const std::string entity = camera.entity;
  w.ask = [entity] { camera_request(entity); };
  w.done = view_done;
  loader.want(owners::VIEW, std::move(w));
}
inline void alert_want() {
  if (alert_camera.empty() || !alert_frame || lv_obj_has_flag(alert_frame, LV_OBJ_FLAG_HIDDEN)) return;
  picture_loader::Want w;
  w.key = alert_key();
  w.tag = "alert|" + alert_camera;
  w.slot = picture_loader::Slot::THUMB;
  w.rank = picture_loader::Rank::ALERT;
  w.tries = ALERT_IMAGE_RETRIES + 1;
  w.url = alert_url;  // the app sends it by itself, with the alert: nothing to ask
  w.done = alert_done;
  loader.want(owners::ALERT, std::move(w));
}
// The open media card's cover, while its tiles are seen (firmware 0.40.0+): the card paints it in with its colour.
inline void card_cover_want() {
  if (!media_card_cover.valid() || !detail_shown() || !tiles_seen() || detail_index >= model.count ||
      model.tiles[detail_index].entity != media_card_cover.entity) return;
  loader.want(owners::CARD, cover_picture(media_card_cover, picture_loader::Rank::CARD, [](picture_loader::Outcome o) {
    if (shows(o) && detail_shown() && detail_index < model.count) refresh_detail(detail_index);
  }));
}
// A tile's own picture (tile_picture.h): the card records what it wants (art_key), draws it from the store at once when
// the store has it (a page that comes back, a look that comes back), and hands the rest to the loader.
inline void tile_picture_want(Widgets &w, bool glass) {
  const Tile &t = model.tiles[w.index];
  tile_picture::Ask a;
  if (!tile_ask(w, t, a)) { w.art_key.clear(); return; }
  const std::string key = tile_picture::key(a);
  if (key != w.art_key) {
    w.art_key = key;
    if (picture_of(key) && !draws(w.picture, picture_of(key))) refresh_tile(w.index, redraw_log::TileWhy::picture);
  }
  // A page out of sight has what does not change by itself fetched ahead; its cameras load when it comes back, showing
  // their last picture meanwhile.
  if (!glass && a.every) return;
  picture_loader::Want want;
  want.key = key;
  want.tag = tile_picture::tag(a.index);
  want.slot = picture_loader::Slot::LIVE;
  want.rank = glass ? picture_loader::Rank::PAGE : picture_loader::Rank::AHEAD;
  want.every = glass ? a.every : 0;
  want.bytes = picture_store::bytes_of(a.frame.w, a.frame.h);
  want.drawn = a.drawn;
  want.ask = [a] { tile_picture_request(a); };
  const size_t index = a.index;
  want.done = [index](picture_loader::Outcome o) { tile_picture_done(index, o); };
  loader.want(owners::tile(index), std::move(want));
}
// Every card's picture, one owner per tile: a tile's own picture, and the cover of a media card over a whole page.
// What is on the glass is wanted while the tiles are seen (a dimmed screen without a screensaver too, firmware 0.40.0+,
// GitHub #161); what is on a kept page is fetched ahead while the screen is in use, after everything on the glass and
// broken off for it, so the page shows it the moment it comes back (firmware 0.3.2+). A media card that shows another
// track than it was drawn with asks once it is drawn again.
inline void card_picture_wants() {
  // On the glass while the tiles are seen; ahead only while the store has room to spare and the screen is not busy.
  const bool seen = camera_view::pictures_on_glass(tiles_seen(), card_open(), camera_root != nullptr);
  const bool ahead = camera_view::pictures_ahead(awake(), pictures_kept(), prepare_busy(), pressure::level_of(pressure::BACKGROUND));
  const bool tiles = tile_pictures_supported() && model.ready();
  each_card([&](Widgets &w) {
#if LV_USE_IMAGE
    // A hidden picture object draws nothing, so it holds no picture either (a card that shows another tile now).
    if (w.picture && lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN) && lv_image_get_src(w.picture)) lv_image_set_src(w.picture, nullptr);
#endif
    if (!w.tile || w.index >= model.count) return;
    const auto &t = model.tiles[w.index];
    // A plugin tile with places that have an address shows pictures too (plugin API 0.10).
    const bool pictured = t.pictured() || (w.plugin && plugin_host::pictured(w));
    // A tile that shows no picture any more (a track without one, a player turned off): its last one goes once nothing
    // draws it, not when the store happens to need the room.
    if (tiles && !pictured && !w.art_key.empty()) {
      ESP_LOGD("picture", "tile %u shows no picture now: %s goes", (unsigned) w.index, w.art_key.c_str());
      loader.release(owners::tile(w.index));
      picture_retire(w.art_key);
      w.art_key.clear();
    }
    const bool glass = seen && on_glass(w);
    if (!glass && !ahead) return;
    // A slot keeps the parts of the media card it drew last while it shows another tile (hide_extra), so the card's
    // cover is only this tile's while those parts are on it: a cover or camera tile in that slot asks for its own.
    if (w.extra_mode == "media" && !w.cover_entity.empty() && w.extra && !lv_obj_has_flag(w.extra, LV_OBJ_FLAG_HIDDEN)) {
      if (t.entity != w.cover_entity || t.extra().media_picture != w.cover_mark) return;
      const size_t index = w.index;
      auto cover = cover_picture({w.cover_entity, w.cover_mark, w.cover_size, w.cover_ground},
                                 glass ? picture_loader::Rank::PAGE : picture_loader::Rank::AHEAD,
                                 [index](picture_loader::Outcome o) { if (shows(o)) tile_cover_arrived(index); });
      cover.bytes = picture_store::bytes_of(w.cover_size, w.cover_size);
      loader.want(owners::tile(index), std::move(cover));
    } else if (tiles && pictured) {
      // A live tile's still waits while it asks for its stream or streams (live_tiles_round).
      if (live_tile_active(w.index)) return;
      tile_picture_want(w, glass);
    }
  });
}
// Who wants a picture, in the log.
inline const char *owner_name(const picture_loader::Owner &o) {
  switch (o.kind) {
    case picture_loader::Kind::ALERT: return "alert";
    case picture_loader::Kind::VIEW: return "view";
    case picture_loader::Kind::CARD: return "card";
    case picture_loader::Kind::LIBRARY: return "library";
    default: return "tile";
  }
}
inline void loader_bind() {
  // Every step of every picture, for a diagnosis (`logger: level: DEBUG`).
  loader.log = [](const picture_loader::Owner &o, const std::string &key, const char *what, const std::string &detail) {
    ESP_LOGD("picture", "%s %u %s: %s%s%s", owner_name(o), (unsigned) o.index, what, key.c_str(), detail.empty() ? "" : " -> ",
             detail.c_str());
  };
  loader.kept = [](const std::string &key, uint32_t &at) {
    if (pictures_kept()) if (auto *e = pictures.entry(key)) { at = e->stored_at; return true; }
    for (int s = 0; s < 3; ++s) if (slot_key[s] == key) { at = slot_at[s]; return true; }
    return false;
  };
  loader.load = [](picture_loader::Slot slot, const std::string &url, const std::string &key) {
    if (slot_key[static_cast<int>(slot)] != key) slot_letgo(slot);
    picture_memory("before", key.substr(0, key.find('|')).c_str(), 0);
    auto &hooks = slot_hooks(slot);
    // The picture its owner shows until this one comes (another track, the same album): its ETag goes along, so the app
    // answers 304 when the new link holds the same bytes, and picture_done files that picture under the new key.
    std::string had_etag;
    if (pictures_kept() && hooks.load_as)
      if (auto *had = pictures.entry_any(loader.loading_had(slot))) had_etag = had->etag;
    if (!had_etag.empty()) hooks.load_as(url, had_etag);
    else if (hooks.load) hooks.load(url);
  };
  loader.cancel = [](picture_loader::Slot slot) {
    slot_letgo(slot);
    auto &hooks = slot_hooks(slot);
    if (hooks.release) hooks.release();
  };
  loader.forget = [](const std::string &key) { picture_retire(key); };
  // A picture for a page out of sight uses spare room and nothing else (GitHub #415, picture_store fits_ahead).
  loader.room_ahead = [](size_t bytes, size_t coming) { return pictures_kept() && pictures.fits_ahead(bytes, coming); };
}
// One round: every picture says what it wants, and the loader does the rest. From camera_tick, and right after an answer
// of the app, a download's end, a page turn, a camera that opens.
inline bool pictures_rounding = false;
inline void pictures_round() {
  if (!camera_supported() || pictures_rounding) return;
  pictures_rounding = true;
  if (!loader.load) loader_bind();
  const uint32_t now = esphome::millis();
  // One budget for every picture (docs/PICTURES.md): while streams run (live_view.h) they hold their share of it, at
  // most half, and the store keeps the rest. A store over its budget lets go of what no card draws as it needs room.
  if (pictures_kept()) pictures.budget = pictures_budget_whole - std::min(pictures_budget_whole / 2, live_view::held_bytes());
  loader.begin();
  alert_want();
  camera_want();
  card_cover_want();
#ifdef SD_MOD_VACUUM_CARD
  vacuum_card::picture_want();
#endif
  picture_loader::Want library;
  if (media_library::picture_want(library)) loader.want(owners::LIBRARY, std::move(library));
  card_picture_wants();
  plugin_host::card_picture_want();
  plugin_host::saver_picture_want();
  // Never under a finger, and not between two quick page turns (camera_view::settled): a download that starts then is
  // for a page on its way past. Asking the app is an event and goes at once.
  auto *input = lv_indev_get_next(nullptr);
  const bool pressed = input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED;
  loader.end(now, camera_view::may_load(pressed, now, last_turn_ms));
  // The full view's buffer is freed once it closed and nothing loads into it (camera_close).
  if (camera_release_due && !camera_root && !loader.slot_busy(picture_loader::Slot::FULL)) camera_release();
  pictures_rounding = false;
}

// ---------------------------------------------------------------------------------------------------------
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
