// The colour card of a light.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in light_controls.h, effects_page.h.
// What proves it: web/wasm/test_colour_card.mjs, tests/test_effects_page.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- The colour card (firmware 0.2.80+; in C++ since app 0.4.86) ----
// A light with a colour or a colour temperature opens this card on a hold, not the runtime card: three rows of
// light_controls (colour, white shade, brightness) under the same top bar as every card, with the sparkles key for
// its effects page and the lamps key for a light group's lamps.
//
// It is a page over the glass the way a light's effects page and a group's lamp page are: built when it opens and
// thrown away when it closes, so it costs nothing while closed; painted from the light's tile on every change
// (colour_updated, through detail_update), so it follows Home Assistant and every other way the light changes while
// it is open; and a slider let go is a wish (docs/OPTIMISTIC.md), so the tile shows the new colour at once. The
// brightness row sends what the tile's own slider sends (commit_slider). Until dev it was built once, kept the values
// it opened with and sent its changes past the wishes.
// `colour_entity` is the light it shows, empty while it is closed: the swipe guards and the way home read it.
inline std::string colour_entity;
inline lv_obj_t *colour_root = nullptr;
inline detail_bar::Bar colour_bar;  // the back key, the name, the sparkles key and the lamps key
inline bool colour_shown() { return !colour_entity.empty(); }
// The light the card shows: the tile whose hold opened it (active_index), else the first tile of the light, as the
// pages over a card find theirs. None for the example the screen shows on its own (colour_demo).
inline int colour_index() {
  if (active_index >= 0 && static_cast<size_t>(active_index) < model.count && model.tiles[active_index].entity == colour_entity)
    return active_index;
  for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == colour_entity) return static_cast<int>(i);
  return -1;
}
// What the rows show of a light: its colour modes, its hue and white shade, and its brightness where the tile's own
// slider stands (slider_value: the value held while the light fades towards it).
inline light_controls::Values colour_values(const Tile &t) {
  auto has = [&](const char *mode) { return t.modes.find(mode) != std::string::npos; };
  light_controls::Values v;
  v.color = has("hs") || has("rgb") || has("xy");
  v.temperature = has("color_temp");
  v.hue = t.hue; v.kelvin = t.kelvin; v.minimum = t.min_kelvin; v.maximum = t.max_kelvin;
  v.brightness = t.state == "on" ? std::clamp(static_cast<int>(std::lround(slider_value(t) / 10.0f)), 1, 100) : 0;
  return v;
}
inline void colour_back(lv_event_t *) { if (dismiss) dismiss(); else hide_detail(); }
inline void colour_effects(lv_event_t *) { effects_page::open(colour_entity); }
inline void colour_lamps(lv_event_t *) { group_page::open(colour_entity); }
// A slider let go: the light's colour and white shade as wishes, its brightness as the tile's slider sends it.
inline void colour_commits() {
  light_controls::commits[0] = [](int hue) {
    const int i = colour_index();
    if (i < 0) return;
    hue = light_controls::clamp(hue, 0, 360);
    wish(model.tiles[i], optimistic::Field::HUE, std::to_string(hue), "light.turn_on", "hs_color", "[" + std::to_string(hue) + ", 100]", "", "", true);
  };
  light_controls::commits[1] = [](int kelvin) {
    const int i = colour_index();
    if (i < 0) return;
    wish(model.tiles[i], optimistic::Field::KELVIN, std::to_string(kelvin), "light.turn_on", "color_temp_kelvin", std::to_string(kelvin));
  };
  light_controls::commits[2] = [](int percent) {
    const int i = colour_index();
    if (i >= 0) commit_slider(static_cast<unsigned>(i), light_controls::clamp(percent, 1, 100) * 10);
  };
}
#ifdef SD_MOD_LIGHT_PRESETS
// The colour card's presets (module light_presets, module_light_presets.cpp draws them): the light's tile's, kept while
// the card is open, and their keys.
inline std::shared_ptr<const light_presets::Presets> colour_presets;
inline std::array<lv_obj_t *, light_presets::MAX> colour_dots{};
#endif
// The card drawn anew, for `title` with the values `v`: the page under it covers the glass and takes every press, so
// nothing leaks through to the tiles and the page keys (firmware 0.2.82); the card inside keeps a hand's width and
// stands in the middle, like every other card.
inline void colour_draw(const std::string &title, const light_controls::Values &v) {
  if (colour_root) { lv_obj_delete(colour_root); light_controls::forget(); }
  colour_root = lv_obj_create(lv_screen_active());
  lv_obj_remove_style_all(colour_root);
  lv_obj_set_size(colour_root, lv_pct(100), lv_pct(100));
  lv_obj_remove_flag(colour_root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(colour_root, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_style(colour_root, theme::style(theme::Paint::page_soft), 0);
  lv_obj_set_style_bg_opa(colour_root, LV_OPA_COVER, 0);
  auto *card = light_controls::card = lv_obj_create(colour_root);
  lv_obj_remove_style_all(card);
  lv_obj_set_height(card, lv_pct(100));
  lv_obj_remove_flag(card, LV_OBJ_FLAG_SCROLLABLE);
  overlay_card::frame(card, overlay_card::controls);
  int rows_width = overlay_card::content_width();
#ifdef SD_MOD_LIGHT_PRESETS
  // The presets beside the rows take a column at their right, the card as much wider as the glass has room for; else a
  // fourth row the three share the room with.
  const bool beside = !light_controls::demo && colour_beside();
  light_controls::extra = !light_controls::demo && colour_presets && colour_presets->count && !beside ? 1 : 0;
  if (beside) {
    const int column = colour_column() + ui::px(ui::large() ? 12 : 5);
    const int whole = std::min(overlay_card::screen_width(), rows_width + column);
    rows_width = whole - column;
    const int side = (overlay_card::screen_width() - whole) / 2;
    lv_obj_set_style_pad_left(card, side, 0);
    lv_obj_set_style_pad_right(card, side, 0);
  }
#endif
  // Every page's top bar (detail_bar): the back key, the name, and at the right the sparkles key and the lamps key,
  // where the light has effects or modes on its device (a WLED's palette, preset, speed) or is a group with lamps.
  colour_bar = detail_bar::make(card, title, {detail_bar::BACK, colour_back}, {"\U000F0674", colour_effects}, {tile_controls::glyph::LAMPS, colour_lamps});
  auto shown = [](lv_obj_t *k, bool on) { if (on) lv_obj_remove_flag(k, LV_OBJ_FLAG_HIDDEN); else lv_obj_add_flag(k, LV_OBJ_FLAG_HIDDEN); };
  shown(colour_bar.right[0], effects_page::offered(colour_entity));
  shown(colour_bar.right[1], group_page::offered(colour_entity));
  if (light_controls::demo) lv_obj_add_flag(colour_bar.back, LV_OBJ_FLAG_HIDDEN);
  detail_bar::place(card, colour_bar);
  light_controls::setup(card, small_font, rows_width, overlay_card::screen_height(), mini_icon_font);
  colour_commits();
  const int below = light_controls::place(v);
  light_controls::paint(v, true);
#ifdef SD_MOD_LIGHT_PRESETS
  if (!light_controls::demo) {
    // The rows' block: from the first that shows to the end of the last.
    int top = below;
    // Read from the styles place() set: the coordinates follow only at LVGL's next layout pass.
    for (auto &row : light_controls::rows)
      if (row.box && !lv_obj_has_flag(row.box, LV_OBJ_FLAG_HIDDEN)) top = std::min(top, (int) lv_obj_get_style_y(row.box, LV_PART_MAIN));
    colour_presets_draw(card, beside, top, below - light_controls::row_gap, below);
    const int i = colour_index();
    if (i >= 0) colour_presets_paint(model.tiles[i]);
  }
#else
  (void) below;
#endif
  lv_obj_move_foreground(colour_root);
}
inline void colour_open(Tile &t) {
  colour_entity = t.entity;
#ifdef SD_MOD_LIGHT_PRESETS
  colour_presets = t.presets;
#endif
  colour_draw(t.name.empty() ? t.entity : t.name, colour_values(t));
}
inline void colour_close() {
  if (colour_root) { lv_obj_delete(colour_root); colour_root = nullptr; light_controls::forget(); }
  colour_entity.clear();
#ifdef SD_MOD_LIGHT_PRESETS
  colour_presets.reset(); colour_dots.fill(nullptr);
#endif
}
// A new state of the light while its card is open: the sliders follow it, one under a finger is left alone. A light that
// gained or lost a colour mode is laid out again, unless a finger is on the card.
inline void colour_updated(const Tile &t) {
  if (!colour_root || light_controls::demo || t.entity != colour_entity) return;
  const auto v = colour_values(t);
  // Laid out again only while nothing lies over it (a light's effects, a group's lamps) and no finger is on the glass.
  if (!v.same_rows(light_controls::shown)) {
    if (!lv_indev_get_active_obj() && !effects_page::visible() && !group_page::visible()) colour_draw(t.name.empty() ? t.entity : t.name, v);
    return;
  }
  light_controls::paint(v, false);
#ifdef SD_MOD_LIGHT_PRESETS
  colour_presets_paint(t);
#endif
}
// A change of look while the card is open: drawn again in place.
inline void colour_restyle() {
  if (!colour_root) return;
  const int i = colour_index();
  if (i >= 0) colour_open(model.tiles[i]);
  else colour_draw(lv_label_get_text(colour_bar.title), light_controls::shown);
  // The pages over it stay over it.
  for (auto *page : {effects_page::root, group_page::root}) if (page) lv_obj_move_foreground(page);
}
// The card as an example for 40 seconds (the screen's light_controls_preview action, the UI self test): a lamp that is
// no lamp, nothing sent, and no back key, as it closes by itself.
inline void colour_demo(bool on) {
  light_controls::demo = on;
  if (!on) { colour_close(); return; }
  light_controls::Values v;
  v.color = v.temperature = true;
  v.hue = 200; v.kelvin = 3000; v.minimum = 2000; v.maximum = 6500; v.brightness = 75;
  colour_entity = "diagnostic";
  colour_draw("Example lamp", v);
}
// The pages behind the colour card's keys (a light's effects, firmware 0.2.70+; a group's lamps, 0.3.9+): the tile they
// show and their ways out, actions to Home Assistant and the question for a picker's names. The board binds their
// fonts and its touch limit; the browser preview calls this as the screen does.
inline void bind_pages() {
  effects_page::tile_of = [](const std::string &entity) -> const Tile * {
    // The tile whose card is open (active_index, set by every tap or hold that opens one): an entity may stand on
    // several tiles (firmware 0.16.0+), and the pages behind its card belong to that one.
    if (active_index >= 0 && static_cast<size_t>(active_index) < model.count && model.tiles[active_index].entity == entity)
      return &model.tiles[active_index];
    for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == entity) return &model.tiles[i];
    return nullptr;
  };
  effects_page::send = [](const std::string &service, const std::string &entity, const std::string &key, const std::string &value) {
    action(service, entity, key, value);
  };
  // A lamp's own actions; a list such as hs_color rendered by Home Assistant.
  group_page::send = [](const std::string &service, const std::string &entity, const std::string &key, const std::string &value, bool rendered) {
    if (rendered) action_template(service, entity, key, value);
    else action(service, entity, key, value);
  };
  // Both pages change a lamp or a row as a wish, shown at once and squared with Home Assistant (docs/OPTIMISTIC.md).
  group_page::wish = wish_part;
  effects_page::wish = wish_part;
  effects_page::ask = [](const std::string &entity, unsigned page) { options_request(entity, page); };
  effects_page::drift = []() { return screen_input::touch_guard.distance(); };
  effects_page::now = []() { return static_cast<uint32_t>(esphome::millis()); };
  options_received = effects_page::received;
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
