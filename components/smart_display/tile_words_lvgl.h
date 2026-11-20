// A tile's icon and words: Home Assistant's icon for an entity, weather words, dates, countdowns and the second line.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: where they are drawn (render_slot).
// What proves it: tests/test_tile_icons.py, web/wasm/test_automation_tile.mjs.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// Home Assistant weather conditions mapped to Material Design Icons glyphs.
inline const char *weather_icon(const std::string &condition) {
  if (condition == "sunny") return "\U000F0599";
  if (condition == "clear-night") return "\U000F0594";
  if (condition == "cloudy") return "\U000F0590";
  if (condition == "partlycloudy") return "\U000F0595";
  if (condition == "rainy") return "\U000F0597";
  if (condition == "pouring") return "\U000F0596";
  if (condition == "snowy") return "\U000F0598";
  if (condition == "snowy-rainy") return "\U000F067F";
  if (condition == "fog") return "\U000F0591";
  if (condition == "hail") return "\U000F0592";
  if (condition == "lightning") return "\U000F0593";
  if (condition == "lightning-rainy") return "\U000F067E";
  if (condition == "windy" || condition == "windy-variant") return "\U000F059D";
  if (condition == "exceptional") return "\U000F05D6";
  return "\U000F0595";
}
inline const char *weather_text(const std::string &condition) {
  if (condition == "sunny") return tr(txt::ha_weather_sunny);
  if (condition == "clear-night") return tr(txt::ha_weather_clear_night);
  if (condition == "cloudy") return tr(txt::ha_weather_cloudy);
  if (condition == "partlycloudy") return tr(txt::ha_weather_partlycloudy);
  if (condition == "rainy") return tr(txt::ha_weather_rainy);
  if (condition == "pouring") return tr(txt::ha_weather_pouring);
  if (condition == "snowy") return tr(txt::ha_weather_snowy);
  if (condition == "snowy-rainy") return tr(txt::ha_weather_snowy_rainy);
  if (condition == "fog") return tr(txt::ha_weather_fog);
  if (condition == "hail") return tr(txt::ha_weather_hail);
  if (condition == "lightning") return tr(txt::ha_weather_lightning);
  if (condition == "lightning-rainy") return tr(txt::ha_weather_lightning_rainy);
  if (condition == "windy" || condition == "windy-variant") return tr(txt::ha_weather_windy);
  if (condition == "exceptional") return tr(txt::ha_weather_exceptional);
  return condition.c_str();
}
inline const char *icon_for(const Tile &tile) {
  // A lock that waits for its second tap shows the open lock, also over an icon Home Assistant or the tile chose: for
  // five seconds it says what the next tap does.
  if (tile.domain() == "lock" && lock_asking(tile, false, lock_panel::NONE)) return lock_panel::glyph::LOCK_OPEN;
  if (!tile.icon.empty()) return tile.icon.c_str();
  // A favourite shows the glyph of what it plays (a playlist, an album) where it has no picture (firmware 0.24.0+).
  if (tile.favorite() && !tile.extra().fav_glyph.empty()) return tile.extra().fav_glyph.c_str();
  auto d = tile.domain();
  // Home Assistant's own icon: a bulb, crossed out while off. A chosen icon stays, as in Home Assistant.
  if (d == "light" && tile.state == "off") return "\U000F0E4F";
  if (d == "light") return "\U000F0335";
  if (d == "climate") return "\U000F001B";
  // Home Assistant's humidifier icons (humidifier/icons.json), crossed out while off (firmware 0.42.0+).
  if (d == "humidifier" && tile.state == "off") return "\U000F1466";
  if (d == "humidifier") return "\U000F1099";
  if (d == "vacuum") return "\U000F070D";
  if (d == "fan") return "\U000F0210";
  if (d == "cover") return "\U000F111C";
  if (d == "scene" || d == "script") return "\U000F04B9";
  // Home Assistant's automation icons (automation/icons.json): a robot, crossed out while off, confused while unavailable.
  if (d == "automation" && tile.state == "off") return "\U000F16A7";
  if (d == "automation" && tile.state == "unavailable") return "\U000F169F";
  if (d == "automation") return "\U000F06A9";
  // Home Assistant's remote icons (remote/icons.json), crossed out while off (firmware 0.22.0+).
  if (d == "remote" && tile.state == "off") return "\U000F0EC4";
  if (d == "remote") return "\U000F0454";
  if (d == "weather") return tile.available() ? weather_icon(tile.state) : "\U000F0595";
  // Home Assistant's calendar icons: calendar-check while an event runs, calendar-blank while none does.
  if (d == "calendar") return tile.state == "on" ? "\U000F00EF" : "\U000F00EE";
  if (d == "sensor" || d == "binary_sensor") return "\U000F029A";
  if (d == "sun") return tile.state == "above_horizon" ? "\U000F059B" : "\U000F059C";
  if (d == "timer") return "\U000F051B";
  if (d == "person") return "\U000F0004";
  // The map tile's marker (firmware 0.21.0) only shows while its picture is on its way.
  if (d == "screen") return tile.is_call() ? "\U000F03F2" : tile.is_settings() ? "\U000F0493" : tile.is_page() ? "\U000F0054" : tile.entity == "screen.map" ? "\U000F034E" : tile.is_energy() ? "\U000F140B" : tile.is_text() ? "\U000F0279" : "\U000F0150";
  if (d == "camera" || d == "image") return "\U000F07AE";
  if (d == "alarm_control_panel") return alarm_panel::icon(tile.state);
  if (d == "lock") return lock_icon(tile);
  return "\U000F0425";
}
inline std::string countdown(uint32_t seconds) {
  char b[16];
  if (seconds >= 3600) snprintf(b, sizeof(b), "%u:%02u:%02u", (unsigned)(seconds / 3600), (unsigned)(seconds / 60 % 60), (unsigned)(seconds % 60));
  else snprintf(b, sizeof(b), "%u:%02u", (unsigned)(seconds / 60), (unsigned)(seconds % 60));
  return b;
}
// "Last 14:32" today, "Yesterday 14:32", else "Last 13 Sep", in the screen's language; scripts and scenes have no
// useful on/off. `compact` takes the short wording of yesterday a tile has room for ("Yest. 9:15 PM"); every
// language that needs no shorter word keeps the same text there.
inline std::string month_short(const esphome::ESPTime &now);
inline std::string last_run_text(uint32_t epoch, bool compact) {
  if (!epoch) return tr(txt::script_never_run);
  auto when = esphome::ESPTime::from_epoch_local(epoch);
  auto now = now_time ? now_time() : esphome::ESPTime{};
  if (!when.is_valid()) return tr(txt::script_never_run);
  std::string clock = screen_text::clock_text(hhmm(when), screen_settings::current.clock_24h != 0);
  if (now.is_valid() && now.year == when.year && now.day_of_year == when.day_of_year) return fill(txt::script_last_time, "time", clock);
  if (now.is_valid() && now.year == when.year && now.day_of_year == when.day_of_year + 1)
    return fill(compact ? txt::script_yesterday_time_short : txt::script_yesterday_time, "time", clock);
  std::string date = fill(fill(txt::date_day_month, "day", std::to_string(when.day_of_month)), "month", month_short(when));
  return fill(txt::script_last_date, "date", date);
}
// What the second line was set to, or nothing when it is the line the screen works out itself (firmware 0.2.90+).
// "none" is an empty line on purpose, which is why this answers `chosen` separately from the text: a page tile
// that should not say "Page 3" says nothing at all.
inline bool chosen_subtitle(const Tile &t, std::string &out) {
  const std::string &choice = t.subtitle;
  if (!tile_controls::subtitle_by_hand(choice)) return false;
  if (choice == "none") { out.clear(); return true; }
  if (choice.compare(0, 5, "text:") == 0) { out = choice.substr(5); return true; }
  // A value of the entity: the app sends the finished line, or seconds for a moment in time, which the screen
  // says in its own words and its own clock.
  const Extra &x = t.extra();
  if (x.subtitle_at) { out = last_run_text(x.subtitle_at, true); return true; }
  out = x.subtitle;
  return true;
}
inline std::string timer_text(const Tile &t) {
  const Extra &x = t.extra();
  if (t.state == "active") return countdown(timer_left(x.timer_end, now_epoch(), x.duration));
  if (t.state == "paused") return fill(txt::timer_paused_left, "time", countdown(duration_seconds(x.remaining)));
  return x.duration.empty() ? std::string(tr(txt::ha_off)) : countdown(duration_seconds(x.duration));
}
inline std::string weekday_text(const esphome::ESPTime &now) {
  return now.is_valid() && now.day_of_week >= 1 && now.day_of_week <= 7 ? tr(txt::date_weekdays + now.day_of_week - 1) : "";
}
inline std::string month_short(const esphome::ESPTime &now) {
  return now.is_valid() && now.month >= 1 && now.month <= 12 ? tr(txt::date_months_short + now.month - 1) : "";
}
// "Monday 14 September" in English, "maandag 14 september" in Dutch (screen.date.full).
inline std::string date_text(const esphome::ESPTime &now) {
  if (!now.is_valid() || now.day_of_week < 1 || now.day_of_week > 7 || now.month < 1 || now.month > 12) return "";
  std::string text = fill(txt::date_full, "weekday", weekday_text(now));
  text = fill(text, "day", std::to_string(now.day_of_month));
  return fill(text, "month", tr(txt::date_months + now.month - 1));
}
// Where the finger is, or where it let go, in the screen's coordinates; false without a finger (a test's event).
inline bool finger_at(lv_point_t &point) {
  auto *indev = lv_indev_active();
  if (!indev || lv_indev_get_type(indev) != LV_INDEV_TYPE_POINTER) return false;
  lv_indev_get_point(indev, &point);
  return true;
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
