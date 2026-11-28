// Pictures kept until they change, the one route every picture takes, and the album covers.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in picture_store.h, picture_loader.h.
// What proves it: tests/test_picture_store.cpp, tests/test_picture_loader.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Pictures kept until they change (firmware 0.3.2+, picture_store.h) ----
// On a board with PSRAM every picture a card draws (a page's strip, an album cover) is the store's own copy, never the
// online_image buffer the next download overwrites: a kept page keeps its pictures, a cover is fetched once per track,
// and a camera shows its last picture at once when its page comes back. A board without PSRAM stores nothing and draws
// from the download as before.
inline picture_store::Store<lv_image_dsc_t> pictures;
// The whole picture budget of this board; the streams that run take their share of it (pictures_share, docs/PICTURES.md).
inline size_t pictures_budget_whole = 0;
inline bool pictures_kept() {
  if (!pictures.release) {
#ifdef USE_ESP32
    // A fifth of the PSRAM, at most 6 MB: about 1.2 MB on a board with 8 MB (the 4-inch Guition reports 6 MB of PSRAM
    // heap), where a page of four tall covers is 384 KB; 6 MB on the 32 MB of the P4 boards, whose 10-inch glass shows a
    // page of five 2x2 cameras of about 300 KB each and keeps more pages. Pictures on a card are never let go for the
    // budget; it says how much is kept beside them.
    const size_t psram = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    pictures.budget = picture_store::budget_for(psram);
#elif defined(KEPT_PAGES_HOST)
    // tools/render with KEPT_PAGES_HOST=1 draws as a board with PSRAM, its pictures too: the store of a 4-inch Guition.
    // Without it the host keeps one download at a time, and a page of several pictured tiles shows only the last.
    pictures.budget = 1200u << 10;
#endif
    pictures_budget_whole = pictures.budget;
    pictures.release = kept_free;
    // With every slot taken, a new picture takes the place of the one used longest ago that no card draws.
    pictures.shown = [](const lv_image_dsc_t *image) { return picture_shown(image); };
    // Each picture's life, for a diagnosis (`logger: level: DEBUG`): taken, retired, freed and why.
    pictures.log = [](const char *what, const picture_store::Store<lv_image_dsc_t>::Entry &e) {
      ESP_LOGD("picture", "store %s %s (%ux%u, %u KB)", what, e.key.c_str(), (unsigned) e.image.header.w,
               (unsigned) e.image.header.h, (unsigned) (e.bytes >> 10));
    };
  }
  return pictures.budget > 0;
}
// Whether this image object draws that picture (never on a board whose profile draws no images).
inline bool draws(lv_obj_t *obj, const lv_image_dsc_t *image) {
#if LV_USE_IMAGE
  return obj && lv_image_get_src(obj) == image;
#else
  (void) obj; (void) image;
  return false;
#endif
}
// Whether a card on the glass or kept, or the card open over the page, still draws this picture.
inline bool picture_shown(const lv_image_dsc_t *image) {
#if LV_USE_IMAGE
  bool shown = false;
  auto on = [&](lv_obj_t *obj) { if (draws(obj, image)) shown = true; };
  each_card([&](Widgets &w) { on(w.picture); if (w.extra_mode == "media") on(w.parts[MEDIA_PICTURE]); if (plugin_host::picture_draws(w, image)) shown = true; on(face_picture(w)); });
  on(media_detail_picture);
  on(camera_picture);
  on(alert_picture);
  if (media_library::draws(image) || plugin_host::card_draws(image)) shown = true;
#ifdef SD_MOD_VACUUM_CARD
  if (vacuum_card::draws(image)) shown = true;
#endif
  return shown;
#else
  (void) image;
  return false;
#endif
}
// Whether only cards out of sight draw this picture (a kept page's), none on the glass or open over it: over the budget
// it may make way (picture_store::collect), and its page asks for it again when it comes back.
inline bool picture_away(const lv_image_dsc_t *image) {
#if LV_USE_IMAGE
  const auto drawn = [&](Widgets &w) { return draws(w.picture, image) || (w.extra_mode == "media" && draws(w.parts[MEDIA_PICTURE], image)) || plugin_host::picture_draws(w, image) || draws(face_picture(w), image); };
  for (auto &w : widgets) if (drawn(w)) return false;
  if (draws(media_detail_picture, image) || draws(camera_picture, image) || draws(alert_picture, image) || media_library::draws(image) ||
      plugin_host::card_draws(image))
    return false;
#ifdef SD_MOD_VACUUM_CARD
  if (vacuum_card::draws(image)) return false;
#endif
  bool kept = false;
  for (auto *set : kept_sets) if (set) for (auto &w : *set) kept = kept || drawn(w);
  return kept;
#else
  (void) image;
  return false;
#endif
}
// Takes a picture off the cards of pages out of sight: each draws itself again, and asks for it, when its page comes back.
inline void picture_let_go(const lv_image_dsc_t *image) {
#if LV_USE_IMAGE
  for (auto *set : kept_sets) if (set) for (auto &w : *set) {
    bool took = false;
    for (lv_obj_t *picture : {w.picture, w.extra_mode == "media" ? w.parts[MEDIA_PICTURE] : nullptr, face_picture(w)})
      if (draws(picture, image)) { lv_image_set_src(picture, nullptr); lv_obj_add_flag(picture, LV_OBJ_FLAG_HIDDEN); took = true; }
    if (plugin_host::picture_let_go(w, image)) took = true;
    if (!took) continue;
    if (w.extra_mode == "media") w.cover_shown.clear();
    if (w.index < model.count) mark_tile(w.index, redraw_log::TileWhy::picture);
  }
#else
  (void) image;
#endif
}
// What the store holds, in the log whenever it changes: how many pictures, how much of the budget.
inline size_t pictures_logged_bytes = SIZE_MAX;
inline unsigned pictures_logged_count = 0;
// A cover of a track its player no longer plays never comes on the glass again: it goes once nothing draws it (a card
// may still hold it while the next one loads, MediaFace). Covers its owner moved on from go the same way (the loader's
// forget); this catches the ones whose page or card was not there when the track changed.
inline void covers_gone_by() {
  for (auto &e : pictures.entries) {
    if (!e.buffer || e.retired || e.key.compare(0, 6, "cover|") != 0) continue;
    const size_t mark_at = e.key.find('|', 6), mark_end = mark_at == std::string::npos ? mark_at : e.key.find('|', mark_at + 1);
    if (mark_end == std::string::npos) continue;
    const std::string entity = e.key.substr(6, mark_at - 6), mark = e.key.substr(mark_at + 1, mark_end - mark_at - 1);
    bool playing = false;
    for (size_t i = 0; i < model.count && !playing; ++i) playing = model.tiles[i].entity == entity && model.tiles[i].extra().media_picture == mark;
    if (!playing) e.retired = true;
  }
}
inline void pictures_collect() {
  if (!pictures_kept()) return;
  if (model.ready()) covers_gone_by();
  pictures.collect(picture_shown, picture_away, picture_let_go);
  unsigned count = 0, retired = 0;
  std::string kinds;  // what it holds, by kind of picture: "cover cover live camera"
  for (const auto &e : pictures.entries) {
    if (!e.buffer) continue;
    ++count;
    retired += e.retired;
    if (!kinds.empty()) kinds += ' ';
    kinds += e.key.substr(0, e.key.find('|'));
  }
  const size_t bytes = pictures.size();
  if (bytes == pictures_logged_bytes && count == pictures_logged_count) return;
  pictures_logged_bytes = bytes;
  pictures_logged_count = count;
  ESP_LOGI("picture", "store: %u pictures, %u of %u KB (%s), %u to go", count, (unsigned) (bytes >> 10), (unsigned) (pictures.budget >> 10),
           kinds.c_str(), retired);
}
// What one picture may be on this board (picture_store::cap_for): larger where the store has the room.
inline picture_store::Cap picture_cap() { return picture_store::cap_for(pictures_kept() ? pictures.budget : 0); }
inline bool picture_kept_here(const lv_image_dsc_t *image) { return !pictures_kept() || pictures.holder(image) != nullptr; }
// A cover no card wants any more (a track gone by): it goes at the next collect once nothing draws it, so the covers of
// a long evening's tracks never fill the store (firmware 0.52.0, GitHub #177).
inline void picture_retire(const std::string &key) { if (pictures_kept() && !key.empty()) pictures.retire(key); }

// ---- One route for every picture (firmware 0.52.0, picture_loader.h) ----
// Each picture on the glass says what it wants, every round (pictures_round, from camera_tick and after every answer
// and download): the full view and the screensaver (camera_want), an alert's frame (alert_want), the media card's
// cover (card_cover_want), a player's library (media_library::picture_want), and every card's own: a tile's picture and
// the cover of a media tile over a whole page, on the glass and fetched ahead for kept pages (card_picture_wants). The loader
// asks the app, downloads one picture at a time in the order of what matters, breaks off what nobody wants any more and
// tells each owner when its picture is here; the owner then draws it from the store (picture_of). Before, each of
// them kept its own state of what it had, what it asked and what loaded, and they waited for each other by name.
// The map tile a full view shows (firmware 0.21.0+), -1 for a camera: its index goes with every ask for its picture.
inline int camera_map_index = -1;
// A map's full view (firmware 0.21.0+): where its markers are on the picture, the one a finger picked (`focus`, asked
// for with the picture) and that one's card, as Home Assistant's own map shows a selected person (app 0.4.36).
struct MapSheet {
  struct Hit { std::string entity; int x, y, r; };
  struct Row { uint32_t icon; std::string name, value; };
  std::string entity, focus, title;
  std::vector<Hit> hits;
  std::vector<Row> rows;
};
inline MapSheet map_sheet;
inline std::string map_focus;
inline bool map_pinned = false;  // opened focused on its person: the focus is the view, not a step into it
inline lv_obj_t *map_card_obj = nullptr;
// A map's full view moved by its own keys (dev): whole zoom steps from the view the app frames, and its middle moved by
// x, y pixels of that framed zoom, so a step out and back in lands on the same place. Asked for with the picture
// (`move`); the picture on the glass shows `map_move_shown` until the next one comes.
struct MapMove {
  int zoom = 0;
  float x = 0, y = 0;
  bool operator==(const MapMove &o) const { return zoom == o.zoom && x == o.x && y == o.y; }
  bool none() const { return *this == MapMove{}; }
  std::string text() const {
    if (none()) return "";
    char out[48];
    snprintf(out, sizeof(out), "%d,%.2f,%.2f", zoom, x, y);
    return out;
  }
};
constexpr int MAP_ZOOM_OUT = -8, MAP_ZOOM_IN = 5;
inline MapMove map_move, map_move_shown;
inline lv_obj_t *map_zoom_keys = nullptr, *map_pad = nullptr;  // + and - at the right, the four arrows at the left
inline lv_obj_t *map_waiting = nullptr;  // a small spinner at the top right while the picture of a move is on its way
// The spinner turns only while the picture on the glass is not yet the view the keys asked for.
inline void map_waiting_show() {
  if (!map_waiting) return;
  if (map_move == map_move_shown) lv_obj_add_flag(map_waiting, LV_OBJ_FLAG_HIDDEN);
  else { lv_obj_remove_flag(map_waiting, LV_OBJ_FLAG_HIDDEN); lv_obj_move_foreground(map_waiting); }
}
inline void camera_map_sheet(const MapSheet &next);
inline void camera_request(const std::string &entity, int size = 0, uint32_t background = 0);
inline void camera_release();

inline picture_loader::Loader loader;
namespace owners {
using picture_loader::Kind;
using picture_loader::Owner;
inline constexpr Owner VIEW{Kind::VIEW, 0}, CARD{Kind::CARD, 0}, ALERT{Kind::ALERT, 0}, LIBRARY{Kind::LIBRARY, 0};
inline Owner tile(size_t index) { return {Kind::TILE, static_cast<uint32_t>(index)}; }
}  // namespace owners
inline ImageHooks &slot_hooks(picture_loader::Slot slot) {
  switch (slot) {
    case picture_loader::Slot::THUMB: return camera_thumb;
    case picture_loader::Slot::LIVE: return camera_live;
    default: return camera_full;
  }
}
// What each download slot holds, for a board without the store (or a picture the store had no room for): the owner
// draws the download itself until the slot loads another.
inline std::array<std::string, 3> slot_key{};
inline std::array<uint32_t, 3> slot_at{};
// The picture for `key`: the store's copy, or the download that holds it.
inline lv_image_dsc_t *picture_of(const std::string &key) {
  if (key.empty()) return nullptr;
  if (pictures_kept()) if (auto *kept = pictures.find(key)) return kept;
  for (int s = 0; s < 3; ++s) {
    if (slot_key[s] != key) continue;
    auto &hooks = slot_hooks(static_cast<picture_loader::Slot>(s));
    auto *src = hooks.source ? hooks.source() : nullptr;
    return src && src->data ? src : nullptr;
  }
  return nullptr;
}

// ---- The album covers (firmware 0.2.64+) ----
// The media card, or a media tile over the whole page, wants the cover of what plays (CoverAsk). The app answers
// `esphome.screen_camera` with a link to a BMP of exactly that (op "camera", t "cover"). A cover is the same picture as
// long as the player, its picture's mark, the size and the colour behind its corners are.
inline std::string cover_key(const std::string &entity, const std::string &mark, int size, uint32_t background) {
  char tail[24];
  snprintf(tail, sizeof(tail), "|%d|%06X", size, (unsigned) background);
  return "cover|" + entity + "|" + mark + tail;
}
inline std::string cover_key(const CoverAsk &c) { return cover_key(c.entity, c.mark, c.size, c.ground); }
inline std::string cover_key(const Widgets &w) { return cover_key(w.cover_entity, w.cover_mark, w.cover_size, w.cover_ground); }
inline picture_loader::Want cover_picture(const CoverAsk &c, picture_loader::Rank rank, std::function<void(picture_loader::Outcome)> done) {
  picture_loader::Want w;
  w.key = cover_key(c);
  w.tag = "cover|" + c.entity;
  w.slot = picture_loader::Slot::FULL;
  w.rank = rank;
  const CoverAsk ask = c;
  w.ask = [ask] { camera_request(ask.entity, ask.size, ask.ground); };
  w.done = std::move(done);
  return w;
}
inline bool shows(picture_loader::Outcome o) { return o == picture_loader::Outcome::LOADED || o == picture_loader::Outcome::UNCHANGED; }
// A card on the glass now (not one of a kept page).
inline bool on_glass(const Widgets &w) {
  return &w >= widgets.data() && &w < widgets.data() + widgets.size() && w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN);
}
// A media tile's cover is here: the tile on the glass draws itself again, a kept page's card takes it at once.
inline void tile_cover_arrived(size_t index) {
  each_card([&](Widgets &w) {
    if (w.index != index || w.extra_mode != "media" || w.cover_entity.empty()) return;
    if (on_glass(w)) { refresh_tile(index, redraw_log::TileWhy::picture); return; }
    const std::string key = cover_key(w);
    if (auto *src = picture_of(key)) {
      w.parts[MEDIA_PICTURE] = media_picture_show(w.extra, w.parts[MEDIA_PICTURE], w.cover_rect, src);
      w.cover_shown = key;
      w.cover_hold = 0;
      changes.mark_tile(index);  // the card changed off the glass: its kept page knows it drew this cover
    }
  });
}
// The pictures on screen go before their buffer does (a board without the store: a picture drawn from the download).
inline void cover_forget_pictures() {
  // The card's picture is one of its parts (media_picture_paint): it shows nothing, and stays.
#if LV_USE_IMAGE
  if (media_detail_picture) { lv_image_set_src(media_detail_picture, nullptr); lv_obj_add_flag(media_detail_picture, LV_OBJ_FLAG_HIDDEN); }
#endif
  media_face.key.clear(); media_face.src = nullptr;
#ifdef SD_MOD_VACUUM_CARD
  vacuum_card::forget_pictures();
#endif
  for (auto &w : widgets) if (w.extra_mode == "media" && w.parts[MEDIA_PICTURE]) { lv_obj_delete(w.parts[MEDIA_PICTURE]); w.parts[MEDIA_PICTURE] = nullptr; w.cover_shown.clear(); }
}
inline void pictures_round();
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
