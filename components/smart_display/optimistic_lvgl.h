// What a finger changed: a wish shown at once on every tile and card of its entity, and squared with what Home Assistant says (docs/OPTIMISTIC.md).
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in optimistic.h.
// What proves it: tests/test_optimistic.cpp, tests/test_optimistic_rule.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- What a finger changed (docs/OPTIMISTIC.md) ----
// Every control that changes a value of an entity calls wish(): the value shows at once on every tile and card of the
// entity, the action goes out at once (one at a time: taps meanwhile fold into the next), and optimistic.h decides
// what Home Assistant's reports, answers and silence do to it. A control never writes a value into the model itself.
inline uint32_t media_elapsed(const Tile &t);
inline void redraw_detail();
// A field as the tile shows it, as text (optimistic::Field).
// A lamp of a group, a row of a light's effects page: the part a wish names (`item`).
inline const Lamp *wish_lamp(const Tile &t, const std::string &item) {
  for (const auto &l : t.extra().lamps) if (l.entity == item) return &l;
  return nullptr;
}
#ifdef SD_MOD_LIGHT_PRESETS
// The light as its presets read it: on, its brightness in percent, and its white shade or its colour.
inline light_presets::Light preset_light(const Tile &t) {
  light_presets::Light l;
  l.on = t.state == "on";
  l.level = std::isfinite(t.brightness) ? std::clamp((int) std::lround(t.brightness * 100.0f / 255.0f), 1, 100) : 100;
  l.white = t.white; l.kelvin = t.kelvin; l.hue = t.hue; l.saturation = t.saturation;
  // Its effect and its device's settings as they stand (the effects page's rows), for a preset that names them.
  const auto &x = t.extra();
  l.effect = x.effect;
  for (const auto &r : x.option_rows) l.now.push_back({r.entity, r.current, NAN});
  for (const auto &r : x.number_rows) l.now.push_back({r.entity, effects_page::number_text(r.value), r.value});
  return l;
}
// The preset the light shows now, or -1: a group's lamp by lamp where the screen has its lamps (light_presets::Lamp),
// any other light by its own state.
inline int preset_lit(const Tile &t) {
  if (!t.presets) return -1;
  const auto &lamps = t.extra().lamps;
  if (lamps.empty()) return light_presets::shown(*t.presets, preset_light(t));
  std::array<light_presets::Lamp, MAX_LAMPS> each{};
  size_t n = 0;
  for (const auto &l : lamps) {
    if (n == each.size()) break;
    auto &e = each[n++];
    e.on = l.on; e.unavailable = l.unavailable; e.dims = l.dimmable; e.color = l.color; e.temperature = l.temperature;
    e.level = l.level; e.hue = l.hue; e.saturation = l.saturation; e.kelvin = l.temperature ? l.kelvin : 0;
  }
  return light_presets::group_shown(*t.presets, each.data(), n, preset_light(t));
}
// The preset a tap set on its way, or -1: one of its wishes (its colour and brightness, its effect, a setting) is still
// live, so Home Assistant has not reported it yet. Its key turns a spinner in the ring's place until it has.
inline int preset_pending(const Tile &t) {
  if (!t.presets) return -1;
  const auto on_way = [&](optimistic::Field field, const std::string &want, const std::string &item = "") {
    const auto *w = wishes.find(t.entity, field, item);
    return w && w->want == want;
  };
  for (unsigned n = 0; n < t.presets->count; ++n) {
    const auto &p = t.presets->items[n];
    bool busy = (p.level && on_way(optimistic::Field::PRESET, light_presets::value(p))) ||
                (!p.effect.empty() && on_way(optimistic::Field::EFFECT, p.effect));
    for (const auto &s : p.settings)
      busy = busy || on_way(s.is_number() ? optimistic::Field::ROW_NUMBER : optimistic::Field::ROW_OPTION, s.text, s.entity);
    if (busy) return (int) n;
  }
  return -1;
}
#endif
inline std::string wish_read(const Tile &t, optimistic::Field field, const std::string &item = "") {
  using F = optimistic::Field;
  const auto &x = t.extra();
  const Lamp *lamp = wish_lamp(t, item);
  switch (field) {
    case F::LAMP_ON: return lamp ? (lamp->on ? "1" : "0") : std::string();
    case F::LAMP_LEVEL: return lamp ? std::to_string(lamp->on ? lamp->level : 0) : std::string();
    case F::LAMP_HUE: return lamp ? std::to_string(lamp->saturation ? lamp->hue : 0) : std::string();
    case F::LAMP_KELVIN: return lamp ? std::to_string(lamp->kelvin) : std::string();
    case F::MEMBER_POSITION: case F::MEMBER_TILT:
      for (const auto &b : x.blinds) if (b.entity == item) {
        const float v = field == F::MEMBER_POSITION ? b.position : b.tilt;
        return std::isfinite(v) ? std::to_string((int) std::lround(v)) : std::string();
      }
      return {};
    case F::EFFECT: return x.effect;
    case F::ROW_OPTION: for (const auto &r : x.option_rows) if (r.entity == item) return r.current; return {};
    case F::ROW_NUMBER: for (const auto &r : x.number_rows) if (r.entity == item) return effects_page::number_text(r.value); return {};
    case F::VACUUM_ROW: { const Choice *c = item.empty() ? nullptr : t.choice(item[0]); return c ? c->current : std::string(); }
    case F::ON_OFF: case F::OPTION: case F::HVAC_MODE: case F::TEXT: return t.state;
    case F::HUMIDIFIER_MODE: return x.humidifier_mode;
    case F::FAN_MODE: return x.fan_mode;
    case F::SWING_MODE: return x.swing_mode;
    case F::ACTIVITY: return t.state == "on" ? x.activity : std::string();  // empty: the remote is off
    case F::PLAYING: return media_card::playing(t.state) ? "1" : "0";
    case F::SHUFFLE: return x.media_shuffle < 0 ? std::string() : x.media_shuffle ? "1" : "0";
    case F::REPEAT: return x.media_repeat;
    case F::MUTED: return t.muted ? "1" : "0";
    case F::HUE: return std::to_string(t.saturation ? t.hue : 0);
    case F::KELVIN: return std::to_string(t.kelvin);
    case F::PRESET: {
#ifdef SD_MOD_LIGHT_PRESETS
      const auto l = preset_light(t);
      return light_presets::read(l, tile_controls::light_colour(t), light_presets::Preset::WHITE);
#else
      return {};
#endif
    }
  }
  return {};
}
// The same field written, as Home Assistant would report it.
inline void wish_write(Tile &t, optimistic::Field field, const std::string &value, const std::string &item = "") {
  using F = optimistic::Field;
  Lamp *lamp = nullptr;
  if (auto *x = t.extra_ptr()) for (auto &l : x->lamps) if (l.entity == item) lamp = &l;
  const int number = std::atoi(value.c_str());
  switch (field) {
    case F::LAMP_ON: if (lamp) lamp->on = value == "1"; break;
    case F::LAMP_LEVEL: if (lamp) { lamp->on = number > 0; if (number > 0) lamp->level = (uint8_t) std::min(100, number); } break;
    case F::LAMP_HUE: if (lamp) { lamp->hue = (uint16_t) number; lamp->saturation = 100; } break;
    case F::LAMP_KELVIN: if (lamp) { lamp->kelvin = (uint16_t) number; lamp->saturation = 0; } break;
    case F::MEMBER_POSITION: case F::MEMBER_TILT:
      if (auto *x = t.extra_ptr()) for (auto &b : x->blinds) if (b.entity == item) {
        (field == F::MEMBER_POSITION ? b.position : b.tilt) = (float) std::clamp(number, 0, 100);
      }
      break;
    case F::EFFECT: t.edit_extra().effect = value; break;
    case F::ROW_OPTION: for (auto &r : t.edit_extra().option_rows) if (r.entity == item) r.current = value; break;
    case F::ROW_NUMBER: for (auto &r : t.edit_extra().number_rows) if (r.entity == item) r.value = std::strtof(value.c_str(), nullptr); break;
    case F::VACUUM_ROW: if (!item.empty()) if (Choice *c = t.choice(item[0])) c->current = value; break;
    case F::ON_OFF: case F::OPTION: case F::HVAC_MODE: case F::TEXT: t.state = value; break;
    case F::HUMIDIFIER_MODE: t.edit_extra().humidifier_mode = value; break;
    case F::FAN_MODE: t.edit_extra().fan_mode = value; break;
    case F::SWING_MODE: t.edit_extra().swing_mode = value; break;
    case F::ACTIVITY:
      if (value.empty()) t.state = "off";
      else { t.edit_extra().activity = value; t.state = "on"; }
      break;
    case F::PLAYING: {
      const bool play = value == "1";
      if (media_card::playing(t.state) == play) break;
      // The bar stops where it is, or runs on from there, as the player's own next report will say.
      const uint32_t at = media_elapsed(t), now = now_epoch();
      auto &x = t.edit_extra();
      if (now && (x.media_duration || x.media_position)) { x.media_position = at; x.media_position_at = now; }
      t.state = play ? "playing" : "paused";
      break;
    }
    case F::SHUFFLE: t.edit_extra().media_shuffle = value.empty() ? -1 : value == "1" ? 1 : 0; break;
    case F::REPEAT: t.edit_extra().media_repeat = value; break;
    case F::MUTED: t.muted = value == "1"; break;
    case F::HUE: t.hue = number; t.saturation = 100; t.has_hs_color = true; t.white = false; break;
    case F::KELVIN: t.kelvin = number; t.saturation = 0; t.white = true; break;
    case F::PRESET: {
#ifdef SD_MOD_LIGHT_PRESETS
      // As Home Assistant reports it after light.turn_on: on at the brightness, in the white shade or the colour.
      const auto p = light_presets::parse(value);
      if (p.level == 0) { t.state = "off"; break; }
      t.state = "on"; t.brightness = p.level * 255.0f / 100.0f;
      if (p.kind == light_presets::Preset::WHITE) { t.kelvin = p.kelvin; t.saturation = 0; t.white = true; }
      if (p.kind == light_presets::Preset::COLOUR) { t.hue = p.hue; t.saturation = p.saturation; t.has_hs_color = true; t.white = false; }
      // A group's lamps as Home Assistant carries the call out, lamp by lamp: each on, at the brightness if it dims, in the
      // white shade or the colour where it can show it (light/helper.py); what a lamp makes of the rest Home Assistant says.
      if (auto *x = t.extra_ptr()) for (auto &l : x->lamps) {
        if (l.unavailable) continue;
        l.on = true;
        if (l.dimmable) l.level = p.level;
        if (p.kind == light_presets::Preset::WHITE && l.temperature) { l.kelvin = p.kelvin; l.saturation = 0; }
        if (p.kind == light_presets::Preset::COLOUR && l.color) { l.hue = p.hue; l.saturation = p.saturation; l.kelvin = 0; }
      }
#endif
      break;
    }
  }
}
// Every tile and the open card of the entity show `value`; drawn after the event that asked, whose key a redraw may delete.
// The open card shows this entity.
// The pages over a card (a light's colour card, its effects, a group's lamps) follow a new state of their tile by themselves.
inline void colour_updated(const Tile &t);
inline void detail_update(const Tile &t) { effects_page::updated(t); group_page::updated(t); colour_updated(t); }
inline bool wish_card_open(const std::string &entity) {
  return detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN) && detail_index < model.count &&
         model.tiles[detail_index].entity == entity;
}
// Every tile of the entity drawn again, and its open card with `card` (its status line follows by itself, in tick()).
inline void wish_refresh(const std::string &entity, bool card) {
  bool told = false;
  for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == entity) {
    refresh_tile(i, redraw_log::TileWhy::wish);
    // The pages over a card (a group's lamps, a light's effects) paint themselves from the tile (detail_update).
    if (!told) { detail_update(model.tiles[i]); told = true; }
  }
  if (card && wish_card_open(entity)) redraw_detail();
}
// The value written and shown: the tiles drawn again, and the open card painted in place (card_repaint), or built again
// where it cannot be.
inline void wish_show(const std::string &entity, optimistic::Field field, const std::string &value, const std::string &item = "") {
  for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == entity) wish_write(model.tiles[i], field, value, item);
  const bool painted = wish_card_open(entity) && card_repaint(model.tiles[detail_index]);
  wish_refresh(entity, !painted);
}
// The old value back: Home Assistant refused (the tile says so for a moment, as after any refused tap), never answered
// (the tile says that, and the screen once why), or said "it worked" and nothing changed (quietly, as its toggle does).
inline void wish_revert(const optimistic::Wish &w, bool refused, bool unanswered, bool show) {
  const uint32_t now = esphome::millis();
  if (refused) for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == w.entity) {
    model.tiles[i].refused_at = std::max<uint32_t>(1, now);
    model.tiles[i].unanswered = unanswered;
    if (!show) refresh_tile(i, redraw_log::TileWhy::wish);
  }
  if (show) wish_show(w.entity, w.field, w.before, w.item);
  ESP_LOGI("wish", "%s back to '%s'%s", w.entity.c_str(), w.before.c_str(), refused ? (unanswered ? " (no answer)" : " (refused)") : "");
}
inline void wish_watch(lv_timer_t *);
// The one way a control changes a value: `value` (in optimistic::Field's words) for `t`'s entity, and the action that
// makes it so, sent to `target` (the tile's entity unless a player plays on another) at once, or after the one on its way.
// `item` names the part of the entity a field of a part changes (a lamp, a row), and is the action's target then;
// `rendered`: the action's value is one Home Assistant renders (a lamp's hs_color list).
inline void wish(Tile &t, optimistic::Field field, const std::string &value, const std::string &service,
                 const std::string &key = "", const std::string &data = "", const std::string &target = "",
                 const std::string &item = "", bool rendered = false, const std::string &key2 = "", const std::string &value2 = "") {
  if (!fresh() || !valid_entity(t.entity) || service.empty()) return;
  auto &w = wishes.slot(t.entity, field, item);
  optimistic::want(w, t.entity, !target.empty() ? target : !item.empty() ? item : t.entity, field, wish_read(t, field, item), value,
                   esphome::millis(), 0, item);
  w.service = service; w.key = key; w.value = data; w.rendered = rendered; w.key2 = key2; w.value2 = value2;
  for (size_t i = 0; i < model.count; ++i) if (model.tiles[i].entity == t.entity) { model.tiles[i].refused_at = 0; model.tiles[i].unanswered = false; }
  ESP_LOGI("wish", "%s%s%s: '%s' (was '%s')", t.entity.c_str(), item.empty() ? "" : " ", item.c_str(), value.c_str(), w.before.c_str());
  wish_show(t.entity, field, value, item);
  wish_run(w, esphome::millis());  // a choice goes out now, unless one is on its way
  if (!wish_timer) wish_timer = lv_timer_create(wish_watch, 50, nullptr);
}
// A wish of a page over a card (the lamps of a group, a light's effects): the tile is the group or the light.
inline void wish_part(const std::string &entity, optimistic::Field field, const std::string &item, const std::string &value,
                      const std::string &service, const std::string &key, const std::string &data, bool rendered) {
  for (size_t i = 0; i < model.count; ++i)
    if (model.tiles[i].entity == entity) { wish(model.tiles[i], field, value, service, key, data, "", item, rendered); return; }
}
// A state message for `t` arrived (page_receiver.cpp): a wish keeps its value in front of a message from before it.
inline void wish_reported(Tile &t) {
  for (auto &w : wishes.wishes) {
    if (!w.live() || w.entity != t.entity) continue;
    const auto outcome = optimistic::report(w, wish_read(t, w.field, w.item));
    if (outcome == optimistic::Outcome::KEEP) { wish_write(t, w.field, w.want, w.item); wish_run(w, esphome::millis()); }
    else ESP_LOGI("wish", "%s: Home Assistant says '%s'%s", t.entity.c_str(), wish_read(t, w.field, w.item).c_str(),
                  outcome == optimistic::Outcome::DONE ? "" : " (not the wish)");
  }
}
inline void wish_answered(const std::string &target, bool ok) {
  const uint32_t now = esphome::millis();
  for (auto &w : wishes.wishes) {
    if (w.target != target) continue;
    if (optimistic::answer(w, ok, now) == optimistic::Outcome::REVERT) wish_revert(w, true, false);
    else wish_run(w, now);  // a newer wish goes out now that this one is taken
  }
}
// On / off by the stand the tile shows, as Home Assistant's toggle (getToggleAction: turn_on or turn_off, never the
// toggle action itself, so a burst sends what the last tap shows).
// A tap whose action is the tile's toggle, for a domain that is on or off: it switches through toggle_wish.
inline bool toggle_tap(const Tile &t, const std::string &service) {
  const auto d = t.domain();
  return service == d + ".toggle" && (d == "light" || d == "switch" || d == "input_boolean" || d == "fan" || d == "automation" || d == "remote");
}
#ifdef SD_MOD_LIGHT_PRESETS
// A preset's key: the light to its brightness and its white shade or colour at once, shown on every tile and the open card
// of the light before Home Assistant answers (Field::PRESET), as one light.turn_on whose values Home Assistant renders.
// Its effect and its device's settings each go as the light's effects page sends them (effects_page.h): the effect as
// light.turn_on, a select's option and a number's value as the row's own action, each a wish shown at once. A preset of the
// lamp itself is its settings alone.
inline void preset_wish(Tile &t, const light_presets::Preset &p) {
  if (t.domain() != "light" || !t.available() || !p.valid()) return;
  if (p.level) {
    const auto colour = light_presets::colour_data(p);
    wish(t, optimistic::Field::PRESET, light_presets::value(p), "light.turn_on", "brightness_pct", std::to_string(p.level), "", "", true,
         colour.key2, colour.value2);
  }
  if (!p.effect.empty()) wish(t, optimistic::Field::EFFECT, p.effect, "light.turn_on", "effect", p.effect);
  for (const auto &s : p.settings) {
    if (s.is_number())
      wish(t, optimistic::Field::ROW_NUMBER, s.text, "number.set_value", "value", s.text, "", s.entity);
    else
      wish(t, optimistic::Field::ROW_OPTION, s.text, "select.select_option", "option", s.text, "", s.entity);
  }
}
#endif
inline void toggle_wish(Tile &t) {
  const bool on = t.state != "on";
  wish(t, optimistic::Field::ON_OFF, on ? "on" : "off", t.domain() + (on ? ".turn_on" : ".turn_off"));
}
// A thermostat's mode; the line under it would still say what the mode before it did.
inline void climate_mode_wish(Tile &t, const std::string &mode) {
  if (auto *x = t.extra_ptr()) x->hvac_action.clear();
  wish(t, optimistic::Field::HVAC_MODE, mode, "climate.set_hvac_mode", "hvac_mode", mode);
}
// A thermostat's or humidifier's power key: off shows at once; on restores the mode Home Assistant remembers, which the
// screen cannot know, so that one waits for it.
inline void climate_power(Tile &t) {
  if (!tile_controls::climate_off(t)) {
    wish(t, t.domain() == "humidifier" ? optimistic::Field::ON_OFF : optimistic::Field::HVAC_MODE, "off", t.domain() + ".turn_off");
    return;
  }
  t.begin(esphome::millis());
  action(t.domain() + ".turn_on", t.entity);
}
// A cover's command (cover_travel.h): every tile and the card of the cover show where it goes and which way at once,
// and the action goes out without the busy sheet, so a finger can send the cover elsewhere while it is on its way.
// `to` the position or tilt asked for, `dir` +1 open, -1 close, 0 from the positions. A stop ends the travel: Home
// Assistant's next report says where the cover stood still.
inline void cover_go(Tile &t, const tile_controls::Action &a, float to, int dir, bool tilt = false) {
  if (!a.valid()) return;
  const uint32_t now = esphome::millis();
  const bool stop = a.service == "cover.stop_cover" || a.service == "cover.stop_cover_tilt";
  const std::string entity = t.entity;
  for (size_t i = 0; i < model.tiles.size(); ++i) {
    auto &o = model.tiles[i];
    if (o.entity != entity) continue;
    o.release_travel();
    if (!stop) o.travel_start(now, to, dir, tilt);
    o.refused_at = 0;
    refresh_tile(i, redraw_log::TileWhy::finger);
  }
  action(a.service, entity, a.key, a.value, true, "", "", false);
}
// A cover's key: open and close travel to their end, the stops end a travel.
inline void cover_key(Tile &t, int command) {
  const auto a = tile_controls::key_action(t, command);
  switch (command) {
    case tile_controls::COVER_OPEN: cover_go(t, a, 100, 1); break;
    case tile_controls::COVER_CLOSE: cover_go(t, a, 0, -1); break;
    // A blind open at 50 (tilt_open) opens to 50 and closes to the nearer end, down from the middle; the way follows.
    case tile_controls::COVER_OPEN_TILT: t.tilt_middle ? cover_go(t, a, 50, 0, true) : cover_go(t, a, 100, 1, true); break;
    case tile_controls::COVER_CLOSE_TILT:
      if (t.tilt_middle) cover_go(t, a, std::isfinite(t.extra().tilt) && t.extra().tilt > 50 ? 100 : 0, 0, true);
      else cover_go(t, a, 0, -1, true);
      break;
    default: cover_go(t, a, NAN, 0); break;
  }
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
