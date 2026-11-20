// A tile's tap and hold: what a finger on a tile does, and the one way to a tile's card.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: what the card it opens draws (the cards, each in its own part).
// What proves it: web/wasm/test_page_frame.mjs, tests/test_new_screen_swipe.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// What a hold on tile `index` opens, without the finger: the one way to a tile's card, for a tap or a hold on the tile
// that opens it (event), an entity's item in the top bar (render_header, firmware 0.56.0+), the screen's
// preview_runtime_card action and the browser preview. The colour card for a light with a colour, the runtime card for
// everything else; tile_controls::tap_route decides, as it does for the hold itself.
inline void hold_card(size_t index) {
  if (!enabled || index >= model.count) return;
  active_index = static_cast<int>(index);
  auto &tile = model.tiles[index];
  if (tile_controls::tap_route(tile, true).route == tile_controls::TapRoute::OVERLAY) {
    tile.begin(esphome::millis(), true);
    colour_open(tile);
    return;
  }
  show_detail(index);
}
inline void event(lv_event_t *event) {
  auto &w = *static_cast<Widgets *>(lv_event_get_user_data(event));
  // Only the card on the glass at this index answers (a kept card never gets a finger; kept_pages.h).
  if (!enabled || w.index >= model.count || w.tile != lv_event_get_current_target(event)) return;
  auto code = lv_event_get_code(event);
  if (code != LV_EVENT_SHORT_CLICKED && code != LV_EVENT_LONG_PRESSED) return;
  // A finger that slid off the card is not a tap or a hold on it (the Guition, firmware 0.2.65+). LVGL keeps the press
  // on the object it started on (LV_OBJ_FLAG_PRESS_LOCK, which LVGL 9.5 sets on every child) and clicks it on release
  // wherever the finger is. The CYD's drift limit already drops such a tap; the Guition has none (TOUCH_MOVE_LIMIT_PX 0,
  // so a firm press that drifts still counts) and asks where the finger let go instead. The lock itself stays: without
  // it a finger that slides on to a slider would press and drag that slider.
  lv_point_t point;
  if (screen_input::touch_guard.move_limit() <= 0 && finger_at(point) && !lv_obj_hit_test(w.tile, &point)) {
    ESP_LOGI("touch", "tap on %s ignored: %s outside the tile", model.tiles[w.index].entity.c_str(),
             code == LV_EVENT_LONG_PRESSED ? "held" : "let go");
    return;
  }
  // The built-in cards need nothing from Home Assistant: the settings card opens the screen's own page with
  // the link down too, as its card says (firmware 0.2.49+), and the clock card does nothing under a finger.
  if (model.tiles[w.index].builtin()) {
    auto &card = model.tiles[w.index];
    if (card.is_page()) {
      // A navigation tile goes to its page on a short tap, with the link down too; holding does nothing.
      if (code != LV_EVENT_SHORT_CLICKED || card.tap == "none" || card.page_target() < 1) return;
      if (allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity)) go_to_page(card.page_target() - 1);
      return;
    }
    // The map tile opens full screen as any map does (firmware 0.21.0+).
    if (card.is_map()) {
      if (code == LV_EVENT_SHORT_CLICKED && card.tap != "none" && camera_supported() && allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity))
        camera_open(card.entity, card.name, (int)w.index);  // its name comes with its state ("Map")
      return;
    }
#ifdef SD_MOD_CALL
    // The Call tile: set to one screen a tap calls it, else the list of the house's screens (docs/CALLS.md).
    if (card.is_call()) {
      if (code == LV_EVENT_SHORT_CLICKED && card.tap != "none" && allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity)) {
        ESP_LOGI("call", "the tile: %s", card.call_to.empty() ? "the list" : card.call_to.c_str());
        if (card.call_to.empty()) call::open_list();
        else call::dial(card.call_to, !card.call_sound_only);
      }
      return;
    }
#endif
    // The energy card: a circle with a sensor behind it opens that sensor's history (firmware 0.47.0+).
    if (card.is_energy()) {
      lv_point_t at;
      if (code == LV_EVENT_SHORT_CLICKED && card.tap != "none" && finger_at(at) && allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity))
        energy_view::tap(w, card, at);
      return;
    }
    if (!card.is_settings() || card.tap == "none" || (settings_screen::may_open && !settings_screen::may_open())) return;
    if (allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity)) settings_screen::open();
    return;
  }
  // A plugin's tile (docs/PLUGINS.md): a short tap goes to the plugin, through the same guard as every tile's.
  if (model.tiles[w.index].is_plugin()) {
    if (code == LV_EVENT_SHORT_CLICKED && model.tiles[w.index].tap != "none" && w.plugin &&
        allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), model.tiles[w.index].entity)) {
      lv_point_t at{-1, -1};
      if (!finger_at(at)) at = {-1, -1};
      plugin_host::tap(w, at.x, at.y);
    }
    return;
  }
  if (!fresh()) return;
  auto &tile = model.tiles[w.index];
  auto d = tile.domain();
  // A tap set to a plugin's tap action (docs/PLUGINS.md): a short tap runs it, through the guard every tap passes; a
  // hold still opens the tile's own card. A screen without that plugin does nothing on the tap.
  if (code == LV_EVENT_SHORT_CLICKED && tile.tap.rfind("plugin:", 0) == 0) {
    if (allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), tile.entity)) plugin_host::tap_action(w.index);
    return;
  }
  // A tap that switches is a wish and takes every clean tap; one that opens or runs something keeps the guard.
  {
    const auto route = tile_controls::tap_route(tile, code == LV_EVENT_LONG_PRESSED);
    const bool switches = route.route == tile_controls::TapRoute::ACTION && toggle_tap(tile, route.service);
    if (!(switches ? allowed_wish(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), tile.entity)
                   : allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), tile.entity))) return;
  }
  // Scenes/scripts often have timestamps or 'off'; unavailable devices never act.
  if (!tile.available() || tile.waiting(esphome::millis()) || tile.tap=="none") return;
  // A camera or an image entity opens full screen on a board that draws images (firmware 0.2.57+).
  if(d=="camera" || d=="image"){if(camera_supported())camera_open(tile.entity,tile.name);return;}
  // A map opens full screen as a camera does (firmware 0.21.0+): the app draws it as large as the board takes a camera,
  // from this tile's own choices (its index), in the screen's look.
  // Held, a person's tile opens its card with the history, as it always did; a person's map too.
  const bool held = code == LV_EVENT_LONG_PRESSED;
  if(tile.is_map()&&!held){if(camera_supported())camera_open(tile.entity,tile.name.empty()?tile.entity:tile.name,(int)w.index);return;}
  // A person tile tapped (Automatic, firmware 0.21.0+): where they are, on the full map focused on them with their card,
  // as Home Assistant's own map shows a person picked; on a board without pictures the card opens as before.
  if(d=="person"&&!held&&tile.tap=="auto"&&camera_supported()){camera_open(tile.entity,tile.name.empty()?tile.entity:tile.name,(int)w.index,tile.entity);return;}
  // A favourite plays (or pauses) what it holds on a tap; held, it opens the player's card (firmware 0.24.0+).
  if(tile.favorite()&&!held&&tile.tap=="auto"){favorite_tap(w.index);return;}
  // A room's calendar card books on its keys (calendar_view.cpp); the rest of the card opens its full screen.
  if(d=="calendar"&&!held&&calendar_view::card_tap(w,tile))return;
#ifdef SD_MOD_TODO
  // A to-do card ticks the item under the finger and opens its keyboard on its key (module_todo.cpp); the rest of the
  // card opens its full screen, whatever the tile's tap says: a list has no other action.
  if(d=="todo"&&!held&&w.todo){if(!todo_view::card_tap(w,tile))show_detail(w.index);return;}
#endif
#ifdef SD_MOD_VACUUM_CARD
  // A robot's larger tile acts on its own parts (its keys, rooms, routines, mode); the rest of it opens its card.
  if(d=="vacuum"&&!held&&w.vacuum_face&&vacuum_face::card_tap(w,tile))return;
#endif
  // tile_controls::tap_route decides; tests/test_tile_controls.cpp keeps every older tap choice routed as before.
  auto tap = tile_controls::tap_route(tile, code == LV_EVENT_LONG_PRESSED);
  switch (tap.route) {
    case tile_controls::TapRoute::ACTION:
      // On / off shows the new stand at once, as Home Assistant's switch does; other actions have nothing to show yet.
      if (toggle_tap(tile, tap.service)) {
        toggle_wish(tile);
        return;
      }
      action(tap.service, tile.entity, "", "", true);
      return;
    case tile_controls::TapRoute::CUSTOM:
      perform(tile);
      return;
    case tile_controls::TapRoute::LOCK:
      lock_tap(w.index);
      return;
    case tile_controls::TapRoute::CARD:
      if (tap.busy) tile.begin(esphome::millis(), true);
      hold_card(w.index);
      return;
    case tile_controls::TapRoute::OVERLAY:
      hold_card(w.index);
      return;
    default:
      return;
  }
}
// The push that wakes a screen in standby only wakes it (dim_wake_overlay), with one exception (firmware 0.2.65+): on a
// page that is one full tile which switches something on or off, the push also switches it, as a light switch on the
// wall does in the dark. It is handed to the tile as its own tap, so it goes the way a tap on a lit screen goes (the
// touch guard, the busy sheet, the new stand at once) and counts once. A push on the tile's slider or keys, the top bar
// or the page bar only wakes, as does a flick. Called by both boards' dim_wake_overlay; true when it tapped the tile.
inline bool wake_tap() {
  // A touch on the screensaver only wakes: what it lay over was not on the glass to be aimed at (firmware 0.29.0+).
  if (std::exchange(saver_woke, false)) return false;
  auto &w = widgets[0];
  if (!enabled || !fresh() || !w.tile || !w.full || w.index >= model.count || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) return false;
  const auto &t = model.tiles[w.index];
  const auto route = tile_controls::tap_route(t, false);
  if (t.builtin() || route.route != tile_controls::TapRoute::ACTION || route.service != t.domain() + ".toggle") return false;
  lv_point_t point;
  if (!finger_at(point) || lv_indev_search_obj(w.tile, &point) != w.tile) return false;
  lv_obj_send_event(w.tile, LV_EVENT_SHORT_CLICKED, nullptr);
  return true;
}
// The same guard for any local style: a page switch mostly hands a slot the colours it already has,
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
