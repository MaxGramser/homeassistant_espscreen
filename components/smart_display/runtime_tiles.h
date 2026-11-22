#pragma once
// The binder of the tile renderer (docs/ARCHITECTURE.md, "The binder and its parts"). What draws one kind of thing with
// LVGL stands in a file of its own, <thing>_lvgl.h, included below in its place. Those files have their code only
// while this is defined: ESPHome includes every header of a component on its own too, where they must be empty.
#define RUNTIME_TILES_PARTS
#include <cmath>
#include <atomic>
#include <cstring>
#include <string_view>
#include "runtime_model.h"
#include "redraw_log.h"
#include "loop_stack.h"
#ifdef ESP_SCREEN_HOST
#include "host_shims.h"
#else
#include "esphome/core/preferences.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/api/api_server.h"
#ifdef USE_API_HOMEASSISTANT_ACTION_RESPONSES
#include "esphome/components/api/homeassistant_service.h"
#endif
#include "esphome/core/hal.h"
#include "esphome/core/util.h"
#include "esphome/core/time.h"
// The screen's own battery sensors (firmware 0.41.0, find_battery).
#include "esphome/core/application.h"
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif
#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif
#ifdef USE_LOGGER
#include "esphome/components/logger/logger.h"
#endif
#endif
// The words of a Home Assistant action's fields (its service, each key and value) as this ESPHome's API has them:
// StringRef up to ESPHome 2026.10, ProgmemStringRef from 2026.11, which is made from a StringRef only explicitly. Every
// field is filled through api_text::of, so the firmware builds on both. The text stays the caller's, as before.
namespace api_text {
using Text = decltype(esphome::api::HomeassistantServiceMap::key);
inline Text of(const std::string &text) { return Text(esphome::StringRef(text)); }
inline Text of(const char *text) { return Text(esphome::StringRef(text)); }
}  // namespace api_text
#include "header_bar.h"
#include "page_header.h"
#include "tile_palette.h"
#include "overlay_card.h"
#include "detail_bar.h"
#include "page_bar.h"
#include "tall_tile.h"
#include "cover_tile.h"
#include "cover_paint.h"
#include "alert_overlay.h"
#include "screen_motion.h"
#include "theme.h"
#include "tile_icon.h"
#include "screen_settings.h"
#include "settings_screen.h"
#include "climate_card.h"
#include "screen_input.h"
#include "light_controls.h"
#include "effects_page.h"
#include "media_library.h"
#include "group_page.h"
#include "tile_controls.h"
#include "history_view.h"
#include "camera_view.h"
#include "picture_fetch.h"
#include "file_fetch.h"
#include "kept_sound.h"
#include "live_spots.h"
#include "pressure.h"
#include "live_view.h"
#include "talk_uplink.h"
#include "hw.h"
#include "boot_trial.h"
#include "heap_watch.h"
#include "kept_pages.h"
#include "tile_memory.h"
#include "wifi_status.h"
#include "ota_status.h"
#include "picture_store.h"
#include "picture_loader.h"
#include "tile_picture.h"
#include "media_card.h"
#include "saver_view.h"
#include "picture_motion.h"
#include "energy_view.h"
#include "calendar_view.h"
#ifdef SD_MOD_TEXT_CARD
#include "module_text_card_view.h"
#endif
#ifdef SD_MOD_TODO
#include "module_todo_view.h"
#endif
#ifdef SD_MOD_TEXT_EDIT
#include "module_text_edit_view.h"
#endif
#include "meter_view.h"
#include "module_vacuum_tile.h"
#ifdef SD_MOD_DOORBELL
#include "module_doorbell.h"
#ifdef SD_MOD_CALL
#include "module_call.h"
#endif
#endif
#include "plugin_api.h"
#include "plugin_host.h"
#include "screen_hooks.h"
#include "touch_feedback.h"
#include "light_card.h"
#include "forecast_tile.h"
#include "weather_chart.h"
#include "climate_tile.h"
#include "swipe_profile.h"
#include "lvgl.h"
#include <functional>
#include <algorithm>
#include <new>
#include <cstdlib>

#ifdef SD_MOD_SECTIONS
// Sections on a page (module sections, module_sections.h at the module site at the end of this file).
namespace runtime_tiles { struct Widgets; }
namespace sections {
inline void place(runtime_tiles::Widgets &w, int page, int32_t column, int32_t span_x, int32_t row, int32_t span_y);
inline void show(int page);
inline void summaries(int page);
inline void forget();
inline void restyle();
}  // namespace sections
#endif

namespace runtime_tiles {
// What the screen says, in the language its firmware was built for (screen_text.h, app 0.2.90).
using screen_text::fill;
using screen_text::plural;
using screen_text::tr;
namespace txt = screen_text::txt;
inline bool enabled = false;
// Swiping, rotation and going back to page 1 live in settings_screen, next to the other settings the
// screen can change itself; these names stay as the way the rest of the firmware reaches them.
using settings_screen::swipe_pages;
using settings_screen::rotation;
using settings_screen::quarter_turns;
using settings_screen::auto_home;
using settings_screen::auto_home_seconds;
using settings_screen::page_buttons;
inline esphome::ESPPreferenceObject rotation_preference;
inline esphome::ESPPreferenceObject buttons_preference, loop_preference;
inline esphome::ESPPreferenceObject home_button_preference;  // the home button in the top bar (0x48425431, 0.60.0+)
inline esphome::ESPPreferenceObject swipe_preference;
inline esphome::ESPPreferenceObject home_preference;
inline esphome::ESPPreferenceObject dark_preference;
inline esphome::ESPPreferenceObject debug_preference;
// Debug mode (settings_screen.h): the logger at the level the firmware is built with while it is on, warnings and
// errors alone while it is off. At boot and after every change of a setting. The host build (tools/render) keeps its
// level: it has no glass to flash and its driver reads the INFO lines.
inline void apply_debug_mode() {
#if defined(USE_LOGGER) && !defined(ESP_SCREEN_HOST) && !defined(USE_HOST)
  if (esphome::logger::global_logger != nullptr)
    esphome::logger::global_logger->set_log_level(settings_screen::debug_mode ? ESPHOME_LOG_LEVEL : ESPHOME_LOG_LEVEL_WARN);
#endif
}
// The grid chosen for each way the glass hangs (firmware 0.53.0+, regrid), lying down first.
struct GridChoice { uint8_t columns[2], rows[2]; };
inline esphome::ESPPreferenceObject grid_preference;
inline void save_grids() {
  GridChoice choice{};
  for (int i = 0; i < 2; ++i) { choice.columns[i] = (uint8_t) chosen_grids[i].columns; choice.rows[i] = (uint8_t) chosen_grids[i].rows; }
  grid_preference.save(&choice);
}
// Which way the glass hangs (firmware 0.53.0+): the LVGL angle the screen is turned to, before the turn its Rotation
// setting adds. A screen is built lying down or standing up (LVGL_ROTATION, its board's ROTATION_LANDSCAPE or a quarter
// further); ESP Screens may stand it up or lay it down with a layout (begin's "upright"), and the screen keeps that. A
// square screen keeps the angle it was built with: a quarter turn there is its Rotation setting and keeps the canvas.
inline int landscape_turn = 0, base_turn = 0;
inline bool square_glass = true;
inline esphome::ESPPreferenceObject upright_preference;
// At the start, before anything measures the canvas (packages/core.yaml turns LVGL to base_turn right after).
inline void hang_at_boot(int landscape, int built, bool square) {
  landscape_turn = ((landscape % 360) + 360) % 360;
  square_glass = square;
  base_turn = ((built % 360) + 360) % 360;
  if (square) return;
  upright_preference = esphome::global_preferences->make_preference<uint32_t>(0x55505231);
  uint32_t upright = 0;
  if (upright_preference.load(&upright) && upright <= 1) base_turn = (landscape_turn + (upright ? 90 : 0)) % 360;
}
// When the screen was asked to hang the other way, 0 for never: it starts again a moment later (tick), standing or lying
// as asked, because every size it measures from its canvas is measured at its start. ESP Screens sends the layout again
// once it is back.
inline uint32_t turn_restart_at = 0;
inline void hang(bool upright) {
  if (square_glass) return;
  uint32_t value = upright ? 1 : 0;
  upright_preference.save(&value);
  esphome::global_preferences->sync();
  base_turn = (landscape_turn + (upright ? 90 : 0)) % 360;
  turn_restart_at = std::max<uint32_t>(1, esphome::millis());
  ESP_LOGI("grid", "the screen stands %s now: starting again", upright ? "up" : "lying down");
}
// The number format of Settings -> Language & region (app 0.2.90), kept for the next start: screen_text::number_style
// (bits 0-3), number_group_min (4-5) and number_percent (6-7) in one word.
inline esphome::ESPPreferenceObject numbers_preference;
inline uint32_t screen_text_numbers() {
  return screen_text::number_style | (uint32_t) screen_text::number_group_min << 4 | (uint32_t) screen_text::number_percent << 6;
}
inline void screen_text_numbers(uint32_t word) {
  screen_text::number_style = (word & 0xF) <= 3 ? word & 0xF : 0;
  screen_text::number_group_min = (word >> 4 & 3) <= 2 ? word >> 4 & 3 : 0;
  screen_text::number_percent = (word >> 6 & 3) <= 2 ? word >> 6 & 3 : 0;
}
inline Model model;
inline std::string inbox;
inline const lv_font_t *watch_font = nullptr;
inline const lv_font_t *mini_icon_font = nullptr;
// The large icon font of a full-page card (firmware 0.2.62+): the domain icons only, so the flash stays free.
inline const lv_font_t *big_icon_font = nullptr;
// Page shown by the navigation bar and the swipe (the profile's tile_page), remembered by show_page.
inline int *shown_page = nullptr;
inline void go_to_page(int page, bool remember = true);
inline void go_back();
inline const lv_font_t *watch_value_font = nullptr, *watch_icon_font = nullptr;
// Big digits for the clock card; the board profile sets it with the local time source.
inline const lv_font_t *clock_font = nullptr;
// The climate card's setpoint, big enough to read across the room (FONT_SETPOINT_SIZE in the board file).
inline const lv_font_t *setpoint_font = nullptr;
// The bedside clock's own digit step (firmware 0.8.0+), where the board has one (FONT_BEDSIDE_SIZE, looks/shared/digits.yaml).
inline const lv_font_t *bedside_font = nullptr;
// The display step (firmware 0.17.0+, packages/looks/shared/digits.yaml): digits as large as half a page's width.
inline const lv_font_t *display_font = nullptr;
// Text in the -/+ pill and the run key of direct controls; the board profile sets it.
inline const lv_font_t *control_font = nullptr;
// A tile's name (the `label` font): the plugin API's Font::TITLE (plugin_host.cpp).
inline const lv_font_t *label_font = nullptr;
// The smallest regular text (sublabel): axis labels and the legend of the history card.
inline const lv_font_t *small_font = nullptr;
inline lv_obj_t *room_label = nullptr;  // remembered by render() so page switches can render synchronously
// The name the top bar was given, as we gave it (firmware 0.2.101+). The name ends in dots when it does not fit
// (LV_LABEL_LONG_DOT), and LVGL writes those dots into the label's own text: lv_label_set_dots() saves the letters
// it covers and puts "..." in their place, so lv_label_get_text() answers "Ha..." from then on. The bar measures the
// name to decide how wide the label may be, and measuring the dotted answer made that room a little smaller every
// time, until one letter and dots were left (GitHub #27). It measures this copy instead, which no dot ever touches.
inline std::string header_name;
// False until the bar carries a name of ours: before that the label still says the profile's ${ROOM_NAME}, which
// an empty first name has to replace.
inline bool header_named = false;
// Top bar (0.2.32+): the profile's clock label only lends its place and margin; values use the
// profile's text font, icons its small icon font. Set by the board profile at boot.
inline page_protocol::Transfer transfer;
inline page_protocol::NavigationHistory navigation_history;
enum class ProtocolProblem : uint8_t { none, old_addon, unsupported };
inline ProtocolProblem protocol_problem = ProtocolProblem::none;
// Pages prepared ahead (firmware 0.3.2+): after a layout the pages are built off the glass one by one, the first layout
// since the start under a "Preparing pages" screen, a later one in the background while the screen is idle.
struct Preparing { bool active = false, foreground = false; unsigned done = 0, total = 0; lv_timer_t *timer = nullptr; };
inline Preparing preparing;
inline bool prepare_busy() { return preparing.active; }
// Pages turn once the layout is whole (transfer.whole, the same rule as fresh()), and not while the "Preparing pages"
// screen covers them.
inline bool navigation_ready() {
  return protocol_problem == ProtocolProblem::none && transfer.whole(model.ready()) && !preparing.foreground;
}
// A page Home Assistant asked for (show_page) before the layout was ready, 1 up, 0 for none: a layout that came while the
// screen stood dark is prepared once it is lit, and the page opens then (core.yaml's open_page, from the 1 s interval).
inline int wanted_page = 0;
inline uint64_t previous_page_id = 0;
inline bool had_previous_page = false;
inline uint32_t history_view_id = 0, options_view_id = 0, camera_view_id = 0, cover_view_id = 0, vacuum_map_view_id = 0;
// A tap on a short calendar event (calendar_view.cpp): the question asked last.
inline uint32_t calendar_view_id = 0;
// A player's library (firmware 0.24.0+): the folder asked for last, and the covers of its page.
inline uint32_t library_view_id = 0, library_art_view_id = 0;
inline void cancel_layout_input(bool invalidate_widgets = true);
inline void forget_kept();
inline void prepare_start();
inline int home_page() { return model.page_data.home; }
inline int sequential_page(int page, int step) {
  return navigation_ready() ? model.page_data.step(page, step, settings_screen::loop_pages != 0) : page;
}
inline int previous_button_page(int page) {
  if (!navigation_ready()) return page;
  return model.page_data.detail(page) ? navigation_history.pop(model.page_data, page) : sequential_page(page, -1);
}
inline bool header_back() {
  return !settings_screen::page_buttons && shown_page && model.page_data.detail(*shown_page);
}
inline lv_obj_t *time_label = nullptr;
inline const lv_font_t *header_text_font = nullptr, *header_icon_font = nullptr;
inline void render_header();
inline std::function<esphome::ESPTime()> now_time;
// True while the screen is in use: the profile reports standby (also the night level) as not awake.
// The analog clock's second hand runs only then; a standby screen stays on its minute redraws.
inline std::function<bool()> screen_awake;
inline bool awake() { return !screen_awake || screen_awake(); }
// The screensaver (firmware 0.29.0+) shows a cover or a camera in standby: those two load their picture while the screen
// is not awake, everything else keeps waiting for a touch.
inline bool saver_pictures = false;
inline bool pictures_awake() { return awake() || saver_pictures; }
// What ESP Screen Manager says the screensaver shows (op "saver", screen_saver.py): "media", "photos" (app 0.4.89, a
// folder of Home Assistant's media; `entity` is screen_saver.PHOTOS_ENTITY, `picture` the photo's mark), "camera",
// "clock", "plugin" (a plugin's step of its own, plugin API 0.14) or "" for none, with the player's or camera's name and, for a player, its title, artist and album, its picture's mark and
// the cover's colour (the picture is made again when either changes). Where the track is, is no part of it.
// The clock's face (module clock_faces, app `cf`): the digital clock every screen has, or Glass, Classic or Bauhaus on
// a screen with the module. Its numerals (Glass: 0, 4 or 12), its seconds hand, and its look: dark, light or the screen's.
struct SaverFace {
  enum Kind : uint8_t { DIGITAL, GLASS, CLASSIC, BAUHAUS };
  enum Look : uint8_t { DARK, LIGHT, FOLLOW };
  uint8_t kind = DIGITAL, numerals = 4, look = DARK;
  bool seconds = true;
  bool operator==(const SaverFace &o) const { return kind == o.kind && numerals == o.numerals && look == o.look && seconds == o.seconds; }
};
// The photos step's picture on the wire (screen_saver.PHOTOS_ENTITY): no entity of Home Assistant's, the step itself.
inline const std::string SAVER_PHOTOS = "saver.photos";
struct SaverChoice {
  std::string kind, entity, name, title, artist, album, picture, ground;
  SaverFace face;
  std::string weather;  // the clock's outside temperature, ready to draw (firmware 0.31.0+, app 0.4.52)
  // The clock's row of entities, the temperature first (firmware 0.50.0+, app 0.4.81): an icon and a text each.
  std::vector<header_bar::Item> row;
  // A player's keys (firmware 0.33.0+, app 0.4.55): whether it plays or is paused, and what Home Assistant says it can do.
  std::string state;
  uint32_t features = 0;
  bool muted = false;
  // A plugin's face of this step or a plugin's own step (plugin API 0.14, app `pf`): its key (plugin:<plugin>.<saver>),
  // and its options and what it draws from as the app sent them ({"o": ..., "x": ...}), handed to the plugin as they are.
  std::string plugin;
  roomy::Text plugin_data;
  // Its options alone (`pf.o`): other options make the plugin's saver anew, as a tile's do (docs/PLUGINS.md).
  roomy::Text plugin_options;
  // The photos step's photo moves slowly (app `x.mv`, picture_motion.h).
  bool motion = false;
  bool operator==(const SaverChoice &o) const {
    return kind == o.kind && entity == o.entity && name == o.name && title == o.title && artist == o.artist &&
           album == o.album && picture == o.picture && ground == o.ground && weather == o.weather && row == o.row &&
           state == o.state && features == o.features && muted == o.muted && face == o.face && plugin == o.plugin &&
           plugin_data == o.plugin_data && motion == o.motion;
  }
};
inline SaverChoice saver_next, saver_now;  // the app's latest word, and what the glass shows
inline lv_obj_t *saver_root = nullptr;      // the clock
// The words over the screensaver's picture (firmware 0.32.0+): drawn again with the next track's picture, and
// `saver_words_due` until it has come.
inline lv_obj_t *saver_first = nullptr, *saver_second = nullptr;
inline bool saver_words_due = false;
// A player's keys over its cover (firmware 0.33.0+): volume up, volume down, play or pause. They take their own tap, so
// the screen stays in standby; a touch anywhere else wakes it. What a key changes shows at once and is squared with Home
// Assistant's word as every control's (saver_wish, docs/OPTIMISTIC.md).
inline std::array<lv_obj_t *, 3> saver_keys{};
inline void saver_keys_draw();
// A next track that came while a picture was on its way (firmware 0.32.0+): followed once that load has ended, so the
// online_image never gets a second link in the middle of a download and the one that lands is the one asked for.
inline bool saver_follow_due = false;
inline void saver_follow_pending();
inline bool saver_camera = false;           // the camera's full view on the glass is the screensaver's (a camera or a cover)
// The full view is the backdrop of a plugin's face (plugin API 0.14, `backdrop: true`): the picture alone, no words, no keys.
inline bool saver_bare = false;
inline void saver_words();
inline bool saver_woke = false;  // the last wake took the screensaver away: that touch does nothing else
inline void saver_tick(uint32_t now);
inline void saver_forget();
inline uint32_t now_epoch() { if (!now_time) return 0; auto t = now_time(); return t.is_valid() ? static_cast<uint32_t>(t.timestamp) : 0; }
// The minute of the day on the screen's clock, -1 until Home Assistant has given the time.
inline int minute_of_day() {
  const auto now = now_time ? now_time() : esphome::ESPTime{};
  return now.is_valid() ? now.hour * 60 + now.minute : -1;
}
// The level of the glass in standby right now, 0 to 100: the night level at night, else the standby level. The backlight
// (apply_screen_settings) and what is seen in standby (tiles_seen) both go by it (firmware 0.40.0+).
inline int standby_level() { return screen_settings::current.dim_level(minute_of_day()); }
// The tiles are there to be seen, so their pictures load (camera_view::tiles_seen, firmware 0.40.0+).
inline bool tiles_seen() { return camera_view::tiles_seen(awake(), saver_root || saver_camera, standby_level()); }
inline void tick();
inline void refresh_tile(size_t index, redraw_log::TileWhy why = redraw_log::TileWhy::unnamed);
// Style setters that only touch a property when it changes (defined with the card renderers below).
inline void set_color(lv_obj_t *obj, lv_style_prop_t prop, lv_color_t color, lv_style_selector_t selector = 0);
inline void set_number(lv_obj_t *obj, lv_style_prop_t prop, int32_t number, lv_style_selector_t selector = 0);
inline void set_font(lv_obj_t *obj, const lv_font_t *value);
inline void set_hidden(lv_obj_t *obj, bool hidden);
#ifdef SWIPE_PROFILE
inline void swipe_test(unsigned count, unsigned interval_ms, unsigned back_ms);
#endif
inline void refresh_header_only();
inline void refresh_all(redraw_log::Why why=redraw_log::Why::unnamed);
inline void refresh_detail(unsigned index);
// What a finger changed, shown at once (optimistic.h, docs/OPTIMISTIC.md): Home Assistant's answers reach it from
// watch_call; defined with the wishes below.
inline optimistic::Pool<6> wishes;
inline lv_timer_t *wish_timer{};
inline void wish_answered(const std::string &target, bool ok);
// A wish of the entity went out a while ago and Home Assistant has not squared it: its tile says "Updating..."
// (docs/OPTIMISTIC.md), the one sign of a wait a wish shows.
// A wish of the entity is still under way (ready to go out, or sent and not yet squared).
inline bool wish_live(const std::string &entity) {
  for (const auto &w : wishes.wishes) if (w.entity == entity && w.live()) return true;
  return false;
}
inline bool wish_slow(const std::string &entity, uint32_t now) {
  for (const auto &w : wishes.wishes) if (w.entity == entity && optimistic::slow(w, now)) return true;
  return false;
}
inline bool wish_unanswered(const std::string &target);
inline void wish_revert(const optimistic::Wish &w, bool refused, bool unanswered, bool show = true);
inline void wish_run(optimistic::Wish &w, uint32_t now);
inline void wish_refresh(const std::string &entity, bool card = true);
// ---- Cards that paint themselves (docs/CARD_PARTS.md) ----
// A card is built once. Every part of it that shows a value (a mode key, the number, the play key, a title) binds a
// paint function while the card is built, and the card names its shape: what decides which parts exist. A change of the
// tile (a wish, a state from Home Assistant) with the same shape runs the paint functions, which touch only what
// changed, so LVGL redraws a few pixels instead of the whole card (LVGL's own advice, and the idea of its observer
// module). Another shape builds the card again. A card that binds nothing is built again on every change, as before.
struct CardPart;
using CardPaint = void (*)(lv_obj_t *, const Tile &, const CardPart &);
struct CardPart {
  lv_obj_t *obj = nullptr;
  CardPaint paint = nullptr;
  std::string value;  // what the part stands for (a mode key's mode), for its paint function
  intptr_t arg = 0;
};
inline std::vector<CardPart> card_parts;               // cleared whenever a card is built
inline uint32_t card_pass = 0;                         // counts the card's paints, for a part that works out once per paint
// The open card's keys wait with a command of the tile, or for Home Assistant (tick() sets it). A part that fades for
// a reason of its own (- at the end of the span) fades for this one too: paint_state(key, DISABLED, card_blocked || own).
inline bool card_blocked = false;
inline uint32_t (*card_shape_of)(const Tile &) = nullptr;  // null: the open card does not paint itself
inline uint32_t card_builds = 0;                       // how often a card was built (the preview's test counts them)
inline uint32_t card_shape = 0;
// Binds a part and gives it its first look, so the card's first look and every later one come from one function.
inline lv_obj_t *card_bind(lv_obj_t *obj, const Tile &t, CardPaint paint, const std::string &value = "", intptr_t arg = 0) {
  if (!obj || !paint) return obj;
  card_parts.push_back(CardPart{obj, paint, value, arg});
  ++card_pass;
  paint(obj, t, card_parts.back());
  return obj;
}
// The shape of a card that is a picture of its values (the weather card's days, a sensor's graph): the whole message
// from Home Assistant, the page and range it shows and the history it drew, so only a message that changes nothing
// it draws is skipped (docs/CARD_PARTS.md, "Picture cards").
inline uint32_t weather_page_shown();
inline uint32_t history_shown();
inline uint32_t picture_card_shape(const Tile &t) {
  Fingerprint f; f.add(t.entity); f.write('|'); f.add(std::to_string(t.revision)); f.write('|');
  f.add(std::to_string(weather_page_shown())); f.write('|'); f.add(std::to_string(history_shown()));
  return f.value;
}
// The shape of a card whose parts do not change with any value: only another entity builds it again.
inline uint32_t entity_shape(const Tile &t) { Fingerprint f; f.add(t.entity); return f.value; }
// The card names its shape once it is built (card_shape_of: the same function on every later change).
inline void card_shaped(const Tile &t, uint32_t (*shape)(const Tile &)) { card_shape_of = shape; card_shape = shape ? shape(t) : 0; }
// The open card painted for the tile as it is now; false when it must be built again (defined with the card below).
inline bool card_repaint(const Tile &t);
inline const char *weather_icon(const std::string &condition);
inline const char *weather_text(const std::string &condition);
inline std::string timer_text(const Tile &t);
inline std::string countdown(uint32_t seconds);
// The alarm panel (firmware 0.3.3+), further down beside the other cards.
inline void alarm_refused(const std::string &entity);
inline void alarm_state_arrived(unsigned index, const std::string &before);
inline void lock_state_arrived(unsigned index, const std::string &before);
inline std::string last_run_text(uint32_t epoch, bool compact = false);
// "07:12": a time of day as Home Assistant and ESP Screens send it, for screen_text::clock_text.
inline std::string hhmm(const esphome::ESPTime &time) {
  char b[8]; snprintf(b, sizeof(b), "%02d:%02d", time.hour, time.minute);
  return b;
}
inline void history_received();
// Camera images full screen and on an alert (firmware 0.2.57+, the Guition binds them; see the end of this file).
inline void camera_open(const std::string &entity, const std::string &name, int map_index = -1, const std::string &focus = "");
inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url, uint32_t number);
inline void camera_link_now(const std::string &url);
inline bool camera_supported();
// Every picture goes one way (picture_loader.h; see the end of this file): an owner says what it wants, and draws what
// picture_of() has for its key.
inline lv_image_dsc_t *picture_of(const std::string &key);
inline std::string cover_key(const std::string &entity, const std::string &mark, int size, uint32_t background);
// The cover a media card or tile wants: the player, the mark of its picture, the size and the colour behind the rounded
// corners, which the app bakes in.
struct CoverAsk {
  std::string entity, mark;
  int size = 0;
  uint32_t ground = 0;
  bool valid() const { return !entity.empty() && !mark.empty() && size > 0; }
};
// The cover the open media card wants (media_face_follow sets it while it paints; empty while it wants none).
inline CoverAsk media_card_cover;
inline bool pictures_kept();
// Whether the store still holds this picture (a board without the store: always), and a cover no card wants any more
// (both with the store, further down).
inline bool picture_kept_here(const lv_image_dsc_t *image);
inline void picture_retire(const std::string &key);
inline bool picture_shown(const lv_image_dsc_t *image);
struct Widgets;
// The card's cover on screen, and the part a media tile keeps its cover in; both go with the image buffer.
inline lv_obj_t *media_detail_picture = nullptr;
constexpr unsigned MEDIA_PICTURE = 14;
inline void media_action(Tile &t, int cmd);
inline const char *icon_for(const Tile &tile);
// A favourite's tap (firmware 0.24.0+), further down with its card.
inline void favorite_tap(size_t index);
inline void label(lv_obj_t *obj, const std::string &text);
// An icon in a circle or a key sits on the centre of its ink, not of its label box: a Material Design glyph's box
// carries the font's side bearings and line gap, so a box-centred icon sat a few pixels off. Some glyphs fill their
// whole box (the air conditioner, the robot) and ran into the edge of their circle: when the ink's corners reach past
// 78 % of the circle's radius, that icon takes the control keys' icon font instead, the same glyph smaller. Words and
// empty labels keep the plain centre (firmware 0.3.1).
inline bool icon_ink(lv_obj_t *icon,const lv_font_t *font,lv_font_glyph_dsc_t &g){
  const char *text=lv_label_get_text(icon);if(!text||!*text||!font)return false;
  const std::string shown(text);size_t i=0;const uint32_t cp=header_bar::next_codepoint(shown,i);
  return i==shown.size()&&cp>=0xF0000&&lv_font_get_glyph_dsc(font,&g,cp,0)&&g.box_w&&g.box_h;
}
inline void center_icon(lv_obj_t *icon){
  const lv_font_t *font=lv_obj_get_style_text_font(icon,LV_PART_MAIN);
  lv_font_glyph_dsc_t g;int dx=0,dy=0;
  if(icon_ink(icon,font,g)){
    auto *holder=lv_obj_get_parent(icon);
    const int side=holder?(int)std::min(lv_obj_get_style_width(holder,LV_PART_MAIN),lv_obj_get_style_height(holder,LV_PART_MAIN)):0;
    const auto reach=[&](const lv_font_glyph_dsc_t &d){return 4*((int)d.box_w*(int)d.box_w+(int)d.box_h*(int)d.box_h);};  // (2 x half-diagonal)^2
    const int limit=side*78/100;
    lv_font_glyph_dsc_t small;
    if(side>0&&mini_icon_font&&font!=mini_icon_font&&reach(g)>4*limit*limit&&icon_ink(icon,mini_icon_font,small)){
      lv_obj_set_style_text_font(icon,mini_icon_font,0);font=mini_icon_font;g=small;
    }
    const int top=(font->line_height-font->base_line)-(int)g.box_h-g.ofs_y;  // the ink's top in the label
    dx=(int)g.adv_w/2-(g.ofs_x+(int)g.box_w/2);
    dy=(int)font->line_height/2-(top+(int)g.box_h/2);
    // A play triangle looks centred on its centre of mass, a sixth of its width right of the middle of its ink: Material
    // Design draws it there in its own box and every player shows it so. On the middle of its ink it sat to the left
    // in its key (GitHub #177, firmware 0.52.0).
    if(!strcmp(lv_label_get_text(icon),tile_controls::glyph::PLAY))dx+=((int)g.box_w+3)/6;
  }
  lv_obj_align(icon,LV_ALIGN_CENTER,dx,dy);
}
inline int active_index = -1;
inline uint32_t last_received = 0;
// Seconds between the manager's full repeats; every layout message declares it (app
// 0.2.26+). Older managers get the 120 s that app 0.2.20 introduced.
inline uint32_t keepalive_seconds = 120;
// Revision of the layout the manager sent last (app 0.2.39+). A keepalive ping carries the
// manager's revision; a mismatch (a restart, a demo layout) asks for the whole layout again.
inline std::string layout_rev;
// History on a detail card (firmware 0.2.51+): the last history the manager sent (app 0.2.59+ answers
// history_request with op "history"), for the card that asked.
struct HistoryState { std::string label; uint32_t color = 0; uint32_t seconds = 0; };
struct History {
  std::string entity, unit;
  uint32_t hours = 0, start = 0, end = 0, began = 0;
  int32_t offset = 0;
  bool line = true, has_high = false, has_low = false;
  float values[history_view::PARTS]{};
  bool has[history_view::PARTS]{};
  float bottom = 0, top = 1, high = 0, low = 0;
  uint32_t high_at = 0, low_at = 0;
  int decimals = 1, active = -1;
  std::vector<std::pair<float, std::string>> ticks;
  std::vector<uint32_t> times;
  uint16_t slots = 0;
  std::vector<history_view::Run> runs;
  std::vector<HistoryState> states;
  // Home Assistant's words for the states (raw state, words), so the heading follows a state that changes.
  std::vector<std::pair<std::string, std::string>> words;
};
inline History history;
// The range the open card shows (1, 24 or 168 hours); what it asked for last and when; whether that answer came.
inline uint32_t history_hours = 24, history_asked_at = 0, history_asked_hours = 0, history_received_at = 0;
inline std::string history_asked_entity;
inline bool history_answered = false;
// What the history card drew from: the range, when its history came, and whether it still waited (picture_card_shape).
inline uint32_t history_shown() { return history_hours * 31u + history_received_at + (history_answered ? 7u : 0u); }
inline std::function<void()> layout_changed, refresh, dismiss, settings_changed;
inline esphome::ESPPreferenceObject settings_preference;
// The two extra values of 0.2.44+ in one record: going back to page 1 by itself, and after how long.
struct HomeTimeout { uint32_t enabled = 1, seconds = 120; };
inline void alarm_load_lock();
inline void load_settings() {
  settings_preference = esphome::global_preferences->make_preference<screen_settings::Settings>(0x53435231);
  swipe_preference = esphome::global_preferences->make_preference<uint32_t>(0x53575031);
  home_preference = esphome::global_preferences->make_preference<HomeTimeout>(0x484F4D31);
  dark_preference = esphome::global_preferences->make_preference<uint32_t>(0x44524B31);
  buttons_preference = esphome::global_preferences->make_preference<uint32_t>(0x50474231);
  debug_preference = esphome::global_preferences->make_preference<uint32_t>(0x44424731);
  numbers_preference = esphome::global_preferences->make_preference<uint32_t>(0x4E554D31);
  uint32_t numbers_saved=0;
  if(numbers_preference.load(&numbers_saved))screen_text_numbers(numbers_saved);
  uint32_t swipe_saved=1;
  if(swipe_preference.load(&swipe_saved))swipe_pages=swipe_saved==1;
  uint32_t dark_saved=0;
  if(dark_preference.load(&dark_saved))settings_screen::dark_mode=dark_saved==1;
  uint32_t buttons_saved=1;
  if(buttons_preference.load(&buttons_saved))page_buttons=buttons_saved!=0;
  // Loop pages: on until someone turns it off, so a screen with no record of it starts on.
  loop_preference=esphome::global_preferences->make_preference<uint32_t>(0x4C4F5031);
  uint32_t loop_saved=1;
  if(loop_preference.load(&loop_saved))settings_screen::loop_pages=loop_saved!=0;
  // The home button (0.2.122+) had no record of its own until 0.60.0, so a screen forgot it was off (GitHub #319).
  home_button_preference=esphome::global_preferences->make_preference<uint32_t>(0x48425431);
  uint32_t house_saved=1;
  if(home_button_preference.load(&house_saved))settings_screen::home_button=house_saved!=0;
  uint32_t debug_saved=0;
  if(debug_preference.load(&debug_saved))settings_screen::debug_mode=debug_saved==1;
  apply_debug_mode();
  HomeTimeout home;
  if(home_preference.load(&home) && home.seconds>=30 && home.seconds<=3600){
    auto_home=home.enabled?1:0;auto_home_seconds=(int32_t)home.seconds;
  }
  // The turn the screen was left at (every board since firmware 0.2.80, the Guition before that). A quarter turn
  // saved on glass that cannot take one (a board file that changed) is left where it is.
  // The grids ESP Screens gave this screen (firmware 0.53.0+); one this firmware cannot take (a screen's YAML that
  // narrowed GRID_MAX_*) leaves the board's own for that way of the glass.
  grid_preference=esphome::global_preferences->make_preference<GridChoice>(0x47524431);
  GridChoice grids{};
  if(grid_preference.load(&grids))
    for(int i=0;i<2;++i)
      if(GRID_RANGES[i].takes(grids.columns[i],grids.rows[i]))chosen_grids[i]=Grid{grids.columns[i],grids.rows[i]};
  rotation_preference=esphome::global_preferences->make_preference<uint32_t>(0x524F5431);
  uint32_t saved_turn=0;
  if(rotation_preference.load(&saved_turn) && saved_turn<=270 && saved_turn%90==0 && (saved_turn%180==0 || quarter_turns))rotation=(int32_t)saved_turn;
  screen_settings::Settings saved;
  if (settings_preference.load(&saved) && saved.valid()) screen_settings::current = saved;
  alarm_load_lock();
}
// Everything the screen remembers, written in one go. ESPHome batches the flash writes, so a row of
// taps on -/+ costs one write, and a value that did not change costs nothing.
inline void persist_settings() {
  if (screen_settings::current.valid()) settings_preference.save(&screen_settings::current);
  uint32_t swipe = swipe_pages ? 1 : 0;
  swipe_preference.save(&swipe);
  HomeTimeout home{(uint32_t) (auto_home ? 1 : 0), (uint32_t) std::clamp<int32_t>(auto_home_seconds, 30, 3600)};
  home_preference.save(&home);
  uint32_t dark = settings_screen::dark_mode ? 1 : 0;
  dark_preference.save(&dark);
  uint32_t buttons = page_buttons ? 1 : 0;
  buttons_preference.save(&buttons);
  uint32_t looping = settings_screen::loop_pages ? 1 : 0;
  loop_preference.save(&looping);
  uint32_t house = settings_screen::home_button ? 1 : 0;
  home_button_preference.save(&house);
  uint32_t debug = settings_screen::debug_mode ? 1 : 0;
  debug_preference.save(&debug);
  uint32_t turned = (uint32_t) rotation;
  rotation_preference.save(&turned);
}
// One page of a picker's names (op "options", app 0.2.83+), for the light's effects page.
inline std::function<void(const std::string &, unsigned, unsigned, std::vector<std::string> &&)> options_received;
struct Widgets {
  lv_obj_t *tile{}, *title{}, *value{}, *circle{}, *icon{}; size_t index{}; int cached_active = -1; lv_obj_t *slider{}, *progress{}, *unit{};
  const lv_font_t *value_font{}, *icon_font{};
  // Wide cards span both columns; custom cards (clock, forecast, graph) draw into `extra`.
  // Full (firmware 0.2.62+) takes the whole page: the double-width card's head on top, a control at the bottom.
  bool wide=false, full=false; int base_width=0, base_height=0; const lv_font_t *title_font{};
  // A key of a bedside clock (firmware 0.8.0+): the card is the round key itself, `key_size` across, in the place its
  // clock gives it (place_page). The card, circle, icon and colours are a tile's; only the shape is the key's.
  bool key=false; int key_size=0;
  // The heartbeat an alarm or lock circle of this card runs (an AlarmLook) and the state change it last marked
  // (alarm_tile_look). They belong to the card, not to the slot: a kept page's cards leave the glass with their
  // animation and come back with it (firmware 0.16.0+; before, a ring kept beating on a card whose lock had settled).
  uint8_t alarm_look=0; uint32_t alarm_mark=0;
  // The card's paint the colours were last drawn for (its background, bit 24 for "none"), next to `cached_active`: a
  // tile whose background alone changed repaints too (firmware 0.17.0+; before, it waited for the entity's next state,
  // which an idle timer never sends).
#ifdef SD_MOD_SECTIONS
  uint64_t cached_paint=UINT64_MAX;  // with the card's look and ground (render_slot)
#else
  uint32_t cached_paint=UINT32_MAX;
#endif
  // `extra_full`: the size the parts were built for; a slot that changes between full and double width rebuilds them.
  // `base_circle`: the board's icon circle (TILE_ICON_SIZE), the one size of the head a board states.
  int base_circle=0;
  lv_obj_t *extra{}; std::string extra_mode; bool extra_full=false; std::array<lv_obj_t *, 36> parts{}; lv_point_precise_t *points{};
  // Cache shared by mutually exclusive custom renderers. Clocks store their dial
  // geometry; cover tiles reuse cx/cy/width for bounds and a structure signature,
  // avoiding additional per-slot state for an optional control.
  int hand_cx=0, hand_cy=0, hand_r=0, hand_width=1;
  // A media tile over the whole page (firmware 0.2.64+): the width of its progress bar, so the fill can run once a
  // second without a card redraw.
  int media_bar_w=0;
  // Soft area under a polyline (graph, sun path), painted by the extra container's draw event.
  const lv_point_precise_t *fill_points{}; unsigned fill_count=0; int fill_x=0, fill_y=0, fill_base=0; lv_color_t fill_color{}; lv_opa_t fill_opa=0;
  // Direct controls on a wide card: a panel at the right with pill keys, a -/+ pill,
  // a slider or a toggle. Objects are rebuilt only when the control set changes.
  lv_obj_t *panel{}; std::string panel_mode; bool panel_dirty=false, panel_full=false, panel_tall=false; uint8_t panel_pair=0; int panel_w=0; uint16_t panel_layout_w=0,panel_layout_h=0;
  std::array<lv_obj_t *,3> keys{}, key_icons{}; std::array<int,3> key_commands{}; std::array<std::string,3> key_args; std::array<int,3> key_checked{};
#ifdef SD_MOD_LIGHT_PRESETS
  // A light's presets on its panel (module light_presets): a round key each, the presets they were made for and their size.
  std::array<lv_obj_t *,light_presets::MAX> dots{}; const void *dots_of=nullptr; int dots_size=0;
#endif
  // A thermostat's mode bar as its panel ("Mode", firmware 0.19.0): its segments, on the panel's track (pill).
  std::array<lv_obj_t *,climate_tile::SEGMENTS> segments{};
  lv_obj_t *pill{}, *pill_value{}, *knob{}, *control_slider{}; int knob_on=-1;
  lv_color_t panel_accent{}, panel_text{};
  // Busy sheet: a translucent white cover with a small spinner while a command is under way.
  lv_obj_t *busy{}, *spinner{}; bool busy_drawn=false;
  // The same spinner, alone on a camera card while its picture loads (firmware 0.3.3).
  lv_obj_t *loading{};
  // A camera tile's live picture (firmware 0.2.77+) or a media tile's album cover (0.2.78+) in the icon's place.
  lv_obj_t *picture{};
  // The picture the tile's last round asked for (tile_picture::key, card_picture_wants), "" for none, and the place its
  // card gave it when it was drawn (the icon's circle of art_size at art_x, art_y; 0 for the whole card).
  std::string art_key; int art_size=0, art_x=0, art_y=0;
  // The album cover a media card over the whole page shows (firmware 0.3.2+): the player, its picture's mark, the size
  // and colour asked for and where it goes on the card, so a kept page can have it fetched ahead and put on the card.
  std::string cover_entity, cover_mark; int cover_size=0; uint32_t cover_ground=0; media_card::Rect cover_rect{};
  // The cover the card shows (its cover_key, "" for none), and until when it keeps that cover while the next one is on
  // its way (firmware 0.52.0; 0: it keeps none).
  std::string cover_shown; uint32_t cover_hold=0;
  bool media_live=false;  // the media card shows "Live" for a stream (media_live), drawn again when that changes
  // The energy card's scene and running dots (firmware 0.47.0+, energy_view.cpp); it goes with the card's extra layer.
  energy_view::View *energy{};
  // A calendar card's plan (firmware 0.56.0+, calendar_view.cpp); it goes with the card's extra layer.
  calendar_view::View *calendar{};
#ifdef SD_MOD_TEXT_CARD
  // A template tile's plan (module text_card, firmware 0.58.0+, module_text_card.cpp); it goes with the card's extra layer.
  text_card_view::View *text{};
#endif
#ifdef SD_MOD_TODO
  // A to-do card's plan (module todo, firmware 0.61.0+, module_todo.cpp); it goes with the card's extra layer.
  todo_view::View *todo{};
#endif
  // A sensor's meter (firmware 0.56.0+, meter_view.cpp); it goes with the card's extra layer.
  meter_view::View *meter{};
#ifdef SD_MOD_VACUUM_CARD
  // A robot vacuum's larger tile (module_vacuum_tile.cpp); it goes with the card's extra layer.
  vacuum_face::View *vacuum_face{};
#endif
  // A plugin tile's card (docs/PLUGINS.md, plugin_host.cpp): the plugin's object; it goes with the card's extra layer.
  plugin_host::Card *plugin{};
  // The card's look and what lies behind it, both relative to the screen's look (theme::screen_dark), so a change of
  // Dark mode needs no card told: `look_other`, the card is painted in the other look (its section follows its contrast);
  // `ground_role` in the look `ground_other` gives, what lies behind it (PAGE, or its section's SECTION /
  // SECTION_CONTRAST panel). Set where the sections module places the card on its own page; a card outside a section,
  // and every card of a board without sections, keeps the screen's look on the page.
  bool look_other=false, ground_other=false;
  uint8_t ground_role=theme::PAGE;
};
// The one door into a card's paint (docs/THEME.md, "A card's look"): for as long as it lasts, the roles are the card's
// look. Every path that paints into a card enters through it, with the card's Widgets or, where LVGL draws later (a
// draw callback), with one of the card's own objects; outside one the look is the screen's. Nested scopes are fine:
// each sets the card's look from the screen's, and gives back what was there.
#ifdef SD_MOD_SECTIONS
struct CardScope : theme::LookScope {
  explicit CardScope(const Widgets &w) : theme::LookScope(w.look_other) {}
  explicit CardScope(const lv_obj_t *obj) : theme::LookScope(theme::other_look(obj)) {}
};
#else
// A board without sections: every card is in the screen's look, so the door costs nothing (docs/MODULES.md).
struct CardScope {
  explicit CardScope(const Widgets &) {}
  explicit CardScope(const lv_obj_t *) {}
  void end() {}
};
#endif
// The two answers about a card's colours (docs/THEME.md "A card's look"), answerable at any moment, in a paint or away
// from one (a picture's question, a plugin's call). What lies behind the card: the page, or the panel of the section it
// stands in, in that panel's look. A picture's corners are rounded over it (an album cover, a camera), and a bare card
// shows it: a contrast section is dark where the page is light.
inline uint32_t card_ground(const Widgets &w) {
  return theme::hex_in(static_cast<theme::Role>(w.ground_role), theme::screen_dark != w.ground_other);
}
// The card's own colour as a value: what a plugin tile gave its card (plugin API 0.26), else the tile's background.
inline theme::Face card_face(const Widgets &w);
// The card's own colour as it is painted, in the card's look.
inline uint32_t card_surface(const Widgets &w) {
  CardScope scope(w);
  return theme::surface(card_face(w));
}
// A page is being built off the glass (warm_page): its cards ask for no pictures and wake nothing.
inline bool warming=false;
constexpr unsigned POINT_BUFFER = 128;
// The points a card's lines are drawn through (a graph, a clock's hands, a history chart): a kilobyte each, PSRAM first
// (roomy.h). LVGL reads them only when it draws, and its objects live in PSRAM already; inside the chip, one for every
// card of every kept page took the memory Wi-Fi needs (2026-10-13). Aborts, as the `new[]` before it did, only when no
// memory has room.
inline lv_point_precise_t *new_points() {
  void *p = roomy::allocate(sizeof(lv_point_precise_t) * POINT_BUFFER);
  if (!p) std::abort();
  return static_cast<lv_point_precise_t *>(p);
}
inline void free_points(lv_point_precise_t *&p) { if (p) roomy::release(p); p = nullptr; }
// One widget per cell of the grid the screen runs on: the cards make_cells makes at boot. The table is sized for the
// biggest grid the screen may be given (CELLS_MAX, about 700 bytes a cell), so a board with PSRAM keeps it there, beside
// the kept pages' sets (firmware 0.53.0+): fifteen cells inside the chip would take 10 KB the 4-inch Guition does not
// have to spare. Without PSRAM it stays inside the chip, as before.
inline std::array<Widgets, CELLS_MAX> &glass_cards() {
  using Table = std::array<Widgets, CELLS_MAX>;
#ifdef USE_ESP32
  void *memory = heap_caps_malloc(sizeof(Table), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!memory) memory = heap_caps_malloc(sizeof(Table), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
#else
  void *memory = std::malloc(sizeof(Table));
#endif
  return *new (memory) Table();
}
inline std::array<Widgets, CELLS_MAX> &widgets = glass_cards();
// ---- Pages kept whole (firmware 0.3.2+, kept_pages.h) ----
// A board with PSRAM keeps the cards of the pages it has shown. `widgets` is always the set on the glass; a page that
// leaves the glass takes its set onto the shelf, hidden, and a page that comes back brings its own set with it. A card
// keeps its index in whichever set holds it, and its callbacks name that index (or `&widgets[index]`), so a set is only
// ever exchanged whole: a callback fires on the glass, where `widgets[index]` is that very card. Cards are drawn only
// while they are on the glass. The first set is the board's own (make_cells), make_card builds the others alike.
using CardSet = std::array<Widgets, CELLS_MAX>;
inline kept_pages::Shelf shelf;
inline kept_pages::Changes changes;  // what a card could show, numbered as it is asked for (kept_pages.h)
inline uint32_t glass_synced = 0;    // the change number the cards on the glass are drawn up to
inline std::array<CardSet *, kept_pages::MAX_KEPT> kept_sets{};
// The styles of a card (packages/core.yaml hands them over at boot), for the cards make_card builds.
struct CardLook { lv_style_t *tile = nullptr, *circle = nullptr, *title = nullptr, *value = nullptr; };
inline CardLook card_look;
inline uint32_t last_turn_ms = 0;
inline void live_tiles_halt();  // live tiles stop at once (a page turns; live_tiles_round)
inline void live_tile_answer(size_t index, const std::string &url);  // the last page turn: pictures wait until the pages stand still (camera_view::settled)
inline uint32_t touched_at = 0;    // the last finger on the glass: pages are prepared in the background only after a pause
inline int kept_limit = -1;        // at most this many pages kept, -1 for as many as fit (a diagnostic build's A/B)
// Every card, on the glass and kept.
template <class F> inline void each_card(F f) {
  for (auto &w : widgets) f(w);
  for (auto *set : kept_sets) if (set) for (auto &w : *set) f(w);
}
// The tile area. Its cells are an LVGL grid of grid.columns by grid.rows free units: LVGL divides the room
// over the cells and keeps the gaps (the container's pad_row and pad_column) and the side margin (its padding),
// so a board states columns and rows and nothing here computes a coordinate. place_page only says which cell a
// card takes and how many it spans. The descriptors live as long as the grid does.
inline lv_obj_t *tile_grid = nullptr;
inline int grid_margin = 0, grid_base_height = 0;
inline std::array<int32_t, DIM_MAX + 1> grid_columns_dsc{};
inline std::array<int32_t, DIM_MAX + 1> grid_rows_dsc{};
// Bind the tile area and lay out its cells (firmware 0.2.92+: from the canvas, not from the board file). The
// canvas LVGL hands us says which way the glass hangs, so it picks the grid; the area then runs the full width
// and from under the top bar down to where the page bar starts. A board states a margin, a gap and the height of
// that bar, all of them a look and not an orientation, and no pixel here comes from a substitution.
inline void grid_cells();
inline void grid_bind(lv_obj_t *container, int margin, int page_bar_height) {
  tile_grid = container;
  grid_margin = margin;
  // Every page's pager is the band under the tiles, its chevrons on their margin (page_bar.h).
  page_bar::band = page_bar_height;
  page_bar::margin = margin;
  page_bar::allowed = [](int key) { return screen_input::touch_guard.accept_repeat(esphome::millis(), key); };
  auto *display = lv_display_get_default();
  const int canvas_w = lv_display_get_horizontal_resolution(display);
  const int canvas_h = lv_display_get_vertical_resolution(display);
  grid_select(canvas_w, canvas_h);
  lv_obj_set_width(container, canvas_w);
  // Where the area starts is the height of the top bar, which the board states as the object's y. It has to be
  // laid out before that coordinate means anything: read straight after boot it is still zero, and the tile
  // area then runs a top bar too far down, over the page bar.
  lv_obj_update_layout(container);
  grid_base_height = canvas_h - lv_obj_get_y(container) - page_bar_height;
  lv_obj_set_height(container, grid_base_height);
  grid_cells();
}
// The tile area's columns and rows as free units, for the grid in use (grid_bind, regrid).
inline void grid_cells() {
  if (!tile_grid) return;
  for (size_t c = 0; c < grid.columns; ++c) grid_columns_dsc[c] = LV_GRID_FR(1);
  grid_columns_dsc[grid.columns] = LV_GRID_TEMPLATE_LAST;
  for (size_t r = 0; r < grid.rows; ++r) grid_rows_dsc[r] = LV_GRID_FR(1);
  grid_rows_dsc[grid.rows] = LV_GRID_TEMPLATE_LAST;
  lv_obj_set_grid_dsc_array(tile_grid, grid_columns_dsc.data(), grid_rows_dsc.data());
  lv_obj_update_layout(tile_grid);
}

inline void tile_picture_place(Widgets &w, const Tile &t, int size, int x, int y);
// A camera or cover that fills its card but came smaller than the card (the picture cap, GitHub #68): the card behind
// it is dark, as around a picture full screen, so the white name over it stays readable (firmware 0.9.0+).
inline bool letterboxed(const Widgets &w) {
#if LV_USE_IMAGE
  if (!w.picture || !w.tile || lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN) || lv_obj_get_index(w.picture) != 0) return false;
  return lv_obj_get_style_width(w.picture, LV_PART_MAIN) < lv_obj_get_width(w.tile) ||
         lv_obj_get_style_height(w.picture, LV_PART_MAIN) < lv_obj_get_height(w.tile);
#else
  (void) w;
  return false;
#endif
}
inline bool tile_picture_waiting(const Widgets &w, const Tile &t);
inline bool tile_picture_marquee_ready(const Widgets &w, const Tile &t);
// A picture over the whole card: a media player's cover on a 1x2 or 2x2 tile, dimmed under its track (firmware 0.3.1),
// and a live camera in full colour with its name at the bottom, on a shade the app puts in the picture: on a 1x2 or 2x2
// tile since 0.3.3, on every size since 0.3.7 (the small square in the icon's place said too little to be of use).
// A map (firmware 0.20.0) fills its card on every size too, with its name drawn into the picture by the app.
// A favourite (firmware 0.24.0+) fills its card with what it plays on every size, as a live camera does.
// A player's album cover over the whole card on every size (a card of one row since the picture system; taller ones
// since firmware 0.3.1, when it stood in the icon's place on one row), as a camera's and a favourite's picture are.
inline bool card_art(const Tile &t) {return (!t.full && t.cover_tile()) || t.live() || t.is_map() || (t.favorite() && t.pictured());}
// All icon fonts carry the same generated glyph set, so the first bound one answers for all.
inline bool has_icon_glyph(uint32_t codepoint) {
  for (auto &w : widgets) if (w.icon_font) { lv_font_glyph_dsc_t dsc; return lv_font_get_glyph_dsc(w.icon_font, &dsc, codepoint, 0); }
  return false;
}
// Whether `font` draws the glyph a label's UTF-8 text starts with (a four-byte Material Design icon).
inline bool font_has(const lv_font_t *font, const std::string &utf8) {
  if (!font || utf8.size() < 4) return false;
  const auto *b = reinterpret_cast<const unsigned char *>(utf8.data());
  uint32_t cp = (uint32_t(b[0] & 7) << 18) | (uint32_t(b[1] & 0x3F) << 12) | (uint32_t(b[2] & 0x3F) << 6) | (b[3] & 0x3F);
  lv_font_glyph_dsc_t dsc; return lv_font_get_glyph_dsc(font, &dsc, cp, 0);
}
// Home Assistant's API link as ESPHome itself tracks it: gone the moment the socket drops,
// back the moment HA reconnects, no guessing from message age.
#ifdef SCREEN_HOST_LINK
// The host renders draw the starting screen's steps without Home Assistant: -1 follows the API, 0 and 1 say it.
inline int host_ha = -1;
inline bool ha_connected() { return host_ha >= 0 ? host_ha != 0 : esphome::api_is_connected(); }
#else
inline bool ha_connected() { return esphome::api_is_connected(); }
#endif
// The manager repeats the whole layout every keepalive; one missed round plus its 20 s
// loop slack and the sending itself are tolerated before the feed counts as gone.
inline bool feed_alive() { return esphome::millis() - last_received < keepalive_seconds * 2000 + 60000; }
// Values may be trusted and actions sent: a whole layout (transfer.whole, the same rule as navigation_ready()), Home
// Assistant connected and the app's feed alive. Not transfer.begun: a hello from an app that starts again clears it
// while the layout held stays true, and asking it greyed every value and drew every card twice at each start of the
// app (docs/PAGES.md, "A hello"; the host render's hello_again round).
inline bool fresh() { return protocol_problem == ProtocolProblem::none && transfer.whole(model.ready()) && ha_connected() && feed_alive(); }
// The number a tile's own tap is known by to the bounce guard: far above the numbers of the buttons on a card or a
// control (300+, 400+, 2000+ ...), so a screen of hundreds of tiles never shares one with them (firmware 0.34.0+).
constexpr int TILE_TOUCH = 100000;
// A dropped tap is logged with its reason, so a missed touch can be read from the ESPHome log
// instead of guessed: moved too far, too short, already used by this contact, or bounce.
inline bool allowed(uint32_t now, int tile, const std::string &what) {
  if (screen_input::touch_guard.accept(now, tile)) return true;
  ESP_LOGI("touch", "tap on %s ignored: %s", what.c_str(), screen_input::touch_guard.reason().c_str());
  return false;
}
// A control that wishes (docs/OPTIMISTIC.md) takes every clean tap, as the -/+ keys do: the wish folds a burst into
// one action, so only a bounce of the same key is dropped, never a second tap of the finger.
inline bool allowed_wish(uint32_t now, int tile, const std::string &what) {
  if (screen_input::touch_guard.accept_repeat(now, tile)) return true;
  ESP_LOGI("touch", "tap on %s ignored: %s", what.c_str(), screen_input::touch_guard.reason().c_str());
  return false;
}
inline float number(JsonVariant value, float fallback = NAN) {
  if (!value.is<float>() && !value.is<int>()) return fallback;
  float n = value.as<float>();
  return std::isfinite(n) ? n : fallback;
}
// A text of a message, at most `maximum` bytes and never half a character. Made at its own length (firmware 0.34.0+):
// shortening a copy of the whole value kept the whole value's room, so a 300-byte attribute cut to 48 still held 300.
inline std::string string(JsonVariant value, size_t maximum = 160) {
  if (!value.is<const char *>()) return {};
  const char *text = value.as<const char *>();
  size_t size = 0;
  while (size <= maximum && text[size]) ++size;
  if (size > maximum) {
    size = maximum;
    while (size > 0 && (static_cast<unsigned char>(text[size]) & 0xC0) == 0x80) --size;
  }
  return std::string(text, size);
}
inline std::string list(JsonVariant value) {
  if (!value.is<JsonArray>()) return {};
  std::string out;
  serializeJson(value, out);
  return out.size() <= 512 ? out : "";
}
inline std::string protocol_key(uint64_t value) {
  char text[17];
  snprintf(text, sizeof(text), "%08x%08x", static_cast<unsigned>(value >> 32), static_cast<unsigned>(value));
  return text;
}
}  // namespace runtime_tiles
#include "page_receiver.h"
namespace runtime_tiles {

// Between the manager's messages nothing redraws a card, so a command under way gets its own 200 ms LVGL timer: it
// brings the busy sheet up once the grace has passed, takes it away as soon as Home Assistant answered or the wait ran
// out, and deletes itself when no tile waits any more (firmware 0.2.59+).
inline lv_timer_t *busy_timer{};
inline void end_wait(size_t index) {
  auto &t = model.tiles[index];
  t.pending = false;
}
inline void busy_watch(lv_timer_t *) {
  const uint32_t now = esphome::millis();
  bool any = false;
  for (auto &w : widgets) {
    if (!w.tile || w.index >= model.count) continue;
    auto &t = model.tiles[w.index];
    if (!t.pending) continue;
    if (!t.waiting(now) && !t.confirmed) end_wait(w.index);
    any = any || t.pending;
    if (t.loading(now) != w.busy_drawn) refresh_tile(w.index, redraw_log::TileWhy::wait);
  }
  if (!any && busy_timer) { lv_timer_delete(busy_timer); busy_timer = nullptr; }
}
inline void watch_busy() { if (!busy_timer) busy_timer = lv_timer_create(busy_watch, 200, nullptr); }

#ifdef USE_API_HOMEASSISTANT_ACTION_RESPONSES
// Home Assistant answers an action sent with a call id (firmware 0.2.58+, Home Assistant 2025.10+). ESPHome keeps each
// answer's callback until the answer arrives and has no timeout of its own, so a tap asks for at most four answers at a
// time and ends the ones Home Assistant never gives (actions not allowed, an older Home Assistant) after eight seconds.
// Only a refusal shows: the tile says Refused for a moment instead of waiting.
struct WatchedCall { uint32_t id = 0, since = 0; };
// The screen's own alert card (firmware 0.38.0): the first tap Home Assistant leaves without an answer explains itself
// once per start, through the same card an automation shows (packages/core.yaml binds it). Such an alert of the
// screen's own sends no esphome.screen_alert event when it closes (own_alert), so no automation takes it for its own.
inline void (*hint_alert)(const std::string &title, const std::string &text) = nullptr;
inline bool own_alert = false, own_alert_next = false, unanswered_told = false;
inline std::array<WatchedCall, 4> watched_calls{};
inline const char *const NO_ANSWER = "no answer";
// Returns whether Home Assistant will answer this one (a free place among the four).
inline bool watch_call(esphome::api::HomeassistantActionRequest &request, const std::string &entity) {
  static uint32_t last_id = 0x5C000000u;  // apart from ESPHome's own counter for YAML actions, which starts at 1
  auto slot = std::find_if(watched_calls.begin(), watched_calls.end(), [](const WatchedCall &c) { return c.id == 0; });
  if (slot == watched_calls.end()) return false;
  const uint32_t id = ++last_id;
  *slot = {id, esphome::millis()};
  request.call_id = id;
  const uint64_t session = transfer.lease, revision = transfer.revision;
  esphome::api::global_api_server->register_action_response_callback(id, [id, entity, session, revision](const esphome::api::ActionResponse &answer) {
    for (auto &c : watched_calls) if (c.id == id) c = {};
    if (!transfer.active || transfer.lease != session || transfer.revision != revision) return;
    // No answer and no new state in eight seconds (firmware 0.38.0): Home Assistant took the action and did nothing, which
    // is what it does when the screen may not perform actions (the ESPHome integration's option); it answers every
    // other call since 2025.10. The tile says so, the first time a card says why, and the app shows the fix in the editor.
    if (answer.get_error_message().c_str() == NO_ANSWER) {
      bool silent = false;
      const uint32_t now = esphome::millis();
      for (size_t i = 0; i < model.tiles.size(); ++i) {
        auto &t = model.tiles[i];
        // The tile's own wait ended after BUSY_CAP and it went back already; what counts is that no state changed since
        // the tap and no "it worked" came.
        if (t.entity != entity || t.confirmed || t.answered_at || t.revision != t.pending_revision ||
            now - t.pending_since > 12000) continue;
        silent = true;
        t.pending = false;
        t.release_slider();
        t.release_travel();
        t.refused_at = std::max<uint32_t>(1, esphome::millis());
        t.unanswered = true;
        refresh_tile(i, redraw_log::TileWhy::answer);
      }
      silent = wish_unanswered(entity) || silent;
      if (silent) ESP_LOGW("runtime_action", "Home Assistant neither answered nor acted on %s: may this screen perform actions?", entity.c_str());
      if (silent && !unanswered_told && hint_alert) {
        unanswered_told = true;
        hint_alert(tr(txt::status_no_answer_title), tr(txt::status_no_answer_text));
      }
      return;
    }
    if (answer.is_success()) {
      wish_answered(entity, true);
      // "It worked" without a new state (a stop on a cover that already stands still) ends the wait in a moment
      // instead of running to the cap.
      if (answer.is_success())
        for (size_t i = 0; i < model.tiles.size(); ++i)
          if (model.tiles[i].entity == entity && model.tiles[i].pending && !model.tiles[i].answered_at)
            model.tiles[i].answered_at = std::max<uint32_t>(1, esphome::millis());
      return;
    }
    ESP_LOGW("runtime_action", "Home Assistant refused the action for %s: %.*s", entity.c_str(),
             (int) answer.get_error_message().size(), answer.get_error_message().c_str());
    alarm_refused(entity);
    wish_answered(entity, false);
    for (size_t i = 0; i < model.tiles.size(); ++i) if (model.tiles[i].entity == entity) {
      model.tiles[i].pending = false;
      model.tiles[i].release_slider();
      model.tiles[i].release_travel();
      model.tiles[i].refused_at = std::max<uint32_t>(1, esphome::millis());
      model.tiles[i].unanswered = false;
      refresh_tile(i, redraw_log::TileWhy::answer);
    }
  });
  return true;
}
inline void expire_calls(uint32_t now) {
  for (auto &c : watched_calls) {
    if (!c.id || now - c.since < 8000) continue;
    const uint32_t id = c.id;
    c = {};
    esphome::api::global_api_server->handle_action_response(id, false, esphome::StringRef(NO_ANSWER, 9));
  }
}
#endif
// Marks every tile of the entity busy and sends; `watch` asks Home Assistant for an answer (a tap).
// `busy`: the tiles of the entity wait for the answer (the busy sheet, greyed keys); a wish (docs/OPTIMISTIC.md) shows
// its value instead and waits for nothing.
// Returns whether Home Assistant will answer it (watch_call).
inline bool send_action(esphome::api::HomeassistantActionRequest &request, const std::string &entity, bool watch, bool busy = true) {
  if (busy) {
    for(size_t i=0;i<model.tiles.size();++i) if(model.tiles[i].entity==entity){model.tiles[i].begin(esphome::millis());model.tiles[i].refused_at=0;refresh_tile(i,redraw_log::TileWhy::wait);}
    watch_busy();
  }
  bool watched = false;
#ifdef USE_API_HOMEASSISTANT_ACTION_RESPONSES
  if (watch) watched = watch_call(request, entity);
#endif
  esphome::api::global_api_server->send_homeassistant_action(request);
  return watched;
}
// `key2` and `value2`: a second field, for a thermostat's range (both ends in one call, firmware 0.19.0).
// The player a card's media keys act on (firmware 0.26.0+): the speaker it follows (the app's `ct`, a Spotify tile that
// plays on a Sonos), or the tile's own.
inline const std::string &media_entity(const Tile &t){return t.extra().media_target.empty()?t.entity:t.extra().media_target;}
// Returns whether Home Assistant will answer it.
inline bool action(const std::string &service, const std::string &entity, const std::string &key="", const std::string &value="", bool watch=true,
                   const std::string &key2="", const std::string &value2="", bool busy=true) {
  // Of any domain: a tile's entity was checked when it came, and a plugin may act on one Tessera draws no tile for.
  if (!fresh() || !entity_id(entity)) return false;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(service);
  request.data.init(1 + !key.empty() + !key2.empty());
  esphome::api::HomeassistantServiceMap entry;
  entry.key = api_text::of("entity_id");
  entry.value = api_text::of(entity);
  request.data.push_back(entry);
  if(!key.empty()) {esphome::api::HomeassistantServiceMap param;param.key=api_text::of(key);param.value=api_text::of(value);request.data.push_back(param);}
  if(!key2.empty()) {esphome::api::HomeassistantServiceMap param;param.key=api_text::of(key2);param.value=api_text::of(value2);request.data.push_back(param);}
  const bool watched = send_action(request, entity, watch, busy);
  ESP_LOGI("runtime_action","Sent service=%s entity=%s",service.c_str(),entity.c_str());
  return watched;
}
inline bool action_template(const std::string &service, const std::string &entity, const std::string &key, const std::string &value,
                            bool busy = true, const std::string &key2 = "", const std::string &value2 = "");
// One wish's turn (docs/OPTIMISTIC.md): it goes out when it is ready, its old value comes back when Home Assistant
// leaves it as it was, and a slow one says so. Run at a tap, at an answer, at a report and by the clock.
inline void wish_run(optimistic::Wish &w, uint32_t now) {
  switch (optimistic::tick(w, now)) {
    case optimistic::Outcome::SEND:
      optimistic::sent(w, w.rendered ? action_template(w.service, w.target, w.key, w.value, false, w.key2, w.value2)
                                     : action(w.service, w.target, w.key, w.value, true, w.key2, w.value2, false));
      break;
    case optimistic::Outcome::REVERT: wish_revert(w, false, false); break;
    default:
      if (!w.slow_shown && optimistic::slow(w, now)) { w.slow_shown = true; wish_refresh(w.entity, false); }
      break;
  }
}
// The wishes' clock: every 50 ms while a wish is known, deleted after the last.
inline void wish_watch(lv_timer_t *) {
  const uint32_t now = esphome::millis();
  for (auto &w : wishes.wishes) if (w.phase != optimistic::Phase::IDLE) wish_run(w, now);
  if (!wishes.any() && wish_timer) { lv_timer_delete(wish_timer); wish_timer = nullptr; }
}
// An action that waits for nothing: no busy tile, no redraw, and the next one goes out at once. A remote's key and a
// player's volume step, which a finger repeats faster than Home Assistant answers.
inline void step_action(const std::string &service, const std::string &entity, const std::string &key = "", const std::string &value = "") {
  if (!fresh() || !valid_entity(entity)) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(service);
  request.data.init(key.empty() ? 1 : 2);
  esphome::api::HomeassistantServiceMap target, field;
  target.key = api_text::of("entity_id"); target.value = api_text::of(entity); request.data.push_back(target);
  if (!key.empty()) { field.key = api_text::of(key); field.value = api_text::of(value); request.data.push_back(field); }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("runtime_action", "Sent %s%s%s to %s", service.c_str(), value.empty() ? "" : " ", value.c_str(), entity.c_str());
}
// A remote's key (firmware 0.22.0+): remote.send_command with one command, sent as a remote sends it. It changes no state,
// so nothing waits for one, as on the remote in your hand.
inline void remote_key(const std::string &entity, const std::string &command) { step_action("remote.send_command", entity, "command", command); }
// An action whose one value Home Assistant renders itself: a list such as a lamp's hs_color "[20, 100]" does not
// travel as text (firmware 0.3.9+, the lamp page of a light group).
// Returns whether Home Assistant will answer it; `busy` as for action().
inline bool action_template(const std::string &service, const std::string &entity, const std::string &key, const std::string &value,
                            bool busy, const std::string &key2, const std::string &value2) {
  if (!fresh() || !valid_entity(entity)) return false;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(service);
  request.data.init(1);
  esphome::api::HomeassistantServiceMap target;
  target.key = api_text::of("entity_id");
  target.value = api_text::of(entity);
  request.data.push_back(target);
  request.data_template.init(1 + !key2.empty());
  esphome::api::HomeassistantServiceMap entry;
  entry.key = api_text::of(key);
  entry.value = api_text::of(value);
  request.data_template.push_back(entry);
  if (!key2.empty()) {
    esphome::api::HomeassistantServiceMap second;
    second.key = api_text::of(key2);
    second.value = api_text::of(value2);
    request.data_template.push_back(second);
  }
  const bool watched = send_action(request, entity, true, busy);
  ESP_LOGI("runtime_action", "Sent service=%s entity=%s %s", service.c_str(), entity.c_str(), key.c_str());
  return watched;
}
// A tap's own action (firmware 0.2.58+): the tile's entity with the data the app sent, text as data and the values Home
// Assistant renders itself (numbers, lists, true or false) as a data_template.
inline void perform(const Tile &tile) {
  const auto &x = tile.extra();
  if (!fresh() || !valid_entity(tile.entity) || x.action.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(x.action);
  request.data.init(1 + x.action_data.size());
  esphome::api::HomeassistantServiceMap target;
  target.key = api_text::of("entity_id");
  target.value = api_text::of(tile.entity);
  request.data.push_back(target);
  for (const auto &pair : x.action_data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(pair.first);
    entry.value = api_text::of(pair.second);
    request.data.push_back(entry);
  }
  request.data_template.init(x.action_templates.size());
  for (const auto &pair : x.action_templates) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(pair.first);
    entry.value = api_text::of(pair.second);
    request.data_template.push_back(entry);
  }
  send_action(request, tile.entity, true);
  ESP_LOGI("runtime_action", "Sent service=%s entity=%s (%u values)", x.action.c_str(), tile.entity.c_str(),
           (unsigned) (x.action_data.size() + x.action_templates.size()));
}
// A picker on a light's effects page asks the manager for its names (app 0.2.83+ answers with op "options"), one
// page at a time. An event, like history_request.
inline void options_request(const std::string &entity, unsigned page) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of("esphome.screen_options");
  request.is_event = true;
  const std::string number = std::to_string(page);
  const std::string keys[] = {"inbox", "entity", "page", "session", "rev", "view"}, values[] = {inbox, entity, number, protocol_key(transfer.lease), layout_rev, std::to_string(++options_view_id)};
  request.data.init(6);
  for (int i = 0; i < 6; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(keys[i]);
    entry.value = api_text::of(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("effects", "Asked for the names of %s, page %u", entity.c_str(), page);
}
// A player's library (firmware 0.24.0+, app 0.4.42+ answers): events like options_request, each with the screen's
// session and layout, so an answer for an older one is dropped. `esphome.screen_browse` asks for a page of a folder
// (op "browse"), `esphome.screen_play` plays an item on a speaker or where the player plays now.
inline void library_event(const char *service, std::initializer_list<std::pair<const char *, std::string>> pairs) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of(service);
  request.is_event = true;
  // The values live until the request is sent: the request holds references to them.
  std::vector<std::pair<std::string, std::string>> data = {{"inbox", inbox}, {"session", protocol_key(transfer.lease)}, {"rev", layout_rev}};
  for (const auto &pair : pairs) data.emplace_back(pair.first, pair.second);
  request.data.init(data.size());
  for (const auto &pair : data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(pair.first);
    entry.value = api_text::of(pair.second);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
}
// ---- The one question for a picture (picture_question.h, docs/PICTURES.md) ----
// Every owner asks the same way: the question, how an older app would have answered it (`kind`, `entity`) and the
// owner's own number of it. To an app whose hello says `pictures` it goes as the question (`q`) with one number for every
// owner (`n`); to an older app as the fields that app reads, with the owner's number (`view`). The answer finds its owner
// either way (page_receiver, op "camera").
inline bool app_reads_questions = false;
inline picture_question::Numbers picture_numbers;
inline void picture_ask(const picture_question::Question &q, const char *kind, const std::string &entity, uint32_t own) {
#if defined(USE_ESP32) && !defined(SCREEN_PICTURES)
  // A board without pictures (the CYD, picture_store.h) never shows one, so it asks for none, and the question's text
  // (json, legacy) stays out of its flash. The host builds (the render, the WASM preview) ask as a board with pictures.
  (void) q; (void) kind; (void) entity; (void) own;
#else
  if (inbox.empty() || !esphome::api::global_api_server) return;
  // The values live until the request is sent: the request holds references to them.
  picture_question::Fields data = {{"inbox", inbox}, {"session", protocol_key(transfer.lease)}, {"rev", layout_rev}};
  if (app_reads_questions) {
    // A screen whose engine takes a format whole (a P4 decodes JPEG in hardware, picture_engine::whole_formats) names
    // it first in its question, and the app picks the format per picture, a photo as JPEG and a drawn map as BMP
    // (docs/PICTURES.md, "Formats").
    picture_question::Question asked = q;
    for (const auto &format : picture_engine::whole_formats())
      if (std::find(asked.formats.begin(), asked.formats.end(), format) == asked.formats.end())
        asked.formats.insert(asked.formats.begin(), format);
    data.emplace_back("n", std::to_string(picture_numbers.ask(kind, entity, own)));
    data.emplace_back("q", picture_question::json(asked));
  } else {
    // An app from before the feature `pictures`. To remove one day, with picture_question::legacy (see there).
    data.emplace_back("view", std::to_string(own));
    for (auto &field : picture_question::legacy(q)) data.push_back(std::move(field));
  }
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of("esphome.screen_camera");
  request.is_event = true;
  request.data.init(data.size());
  for (const auto &pair : data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(pair.first);
    entry.value = api_text::of(pair.second);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGD("picture", "asked %s %s as %s", picture_question::owner_text(q.owner),
           q.sources.empty() ? "" : q.sources.front().c_str(), app_reads_questions ? "a question" : kind);
#endif
}
inline void library_request(const std::string &entity, uint32_t folder, unsigned page) {
  library_event("esphome.screen_browse", {{"entity", entity}, {"folder", std::to_string(folder)}, {"page", std::to_string(page)}, {"view", std::to_string(++library_view_id)}});
  ESP_LOGI("library", "Asked for folder %u of %s, page %u", (unsigned) folder, entity.c_str(), page);
}
// A tap in the speaker menu (firmware 0.26.0+): the app picks the speaker, joins it to the group or takes it out, or
// sets its volume, each through Home Assistant's own action (speakers.py).
inline void speaker_request(const std::string &entity, const std::string &speaker, const char *op, int volume = -1) {
  if (volume >= 0) library_event("esphome.screen_speaker", {{"entity", entity}, {"speaker", speaker}, {"op", op}, {"volume", std::to_string(volume)}});
  else library_event("esphome.screen_speaker", {{"entity", entity}, {"speaker", speaker}, {"op", op}});
}
inline void play_request(const std::string &entity, uint32_t item, const std::string &source) {
  library_event("esphome.screen_play", {{"entity", entity}, {"item", std::to_string(item)}, {"source", source}});
  ESP_LOGI("library", "Play %u on %s%s%s", (unsigned) item, entity.c_str(), source.empty() ? "" : " on ", source.c_str());
}
// A detail card asks the manager for its history (app 0.2.59+ answers with op "history"). An event, like
// setting_event: it needs no permission to call Home Assistant actions.
inline void history_request(const std::string &entity, uint32_t hours) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = api_text::of("esphome.screen_history");
  request.is_event = true;
  const std::string span = std::to_string(hours);
  const std::string keys[] = {"inbox", "entity", "hours", "session", "rev", "view"}, values[] = {inbox, entity, span, protocol_key(transfer.lease), layout_rev, std::to_string(++history_view_id)};
  request.data.init(6);
  for (int i = 0; i < 6; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = api_text::of(keys[i]);
    entry.value = api_text::of(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  history_asked_at = esphome::millis();
  history_answered = false;
  history_asked_entity = entity;
  history_asked_hours = hours;
  ESP_LOGI("history", "asked for %u h of %s", static_cast<unsigned>(hours), entity.c_str());
}
inline void setting_event(const std::string &key, int value) {
  if(inbox.empty())return;
  esphome::api::HomeassistantActionRequest request;request.service=api_text::of("esphome.screen_setting");request.is_event=true;
  std::string number=std::to_string(value);request.data.init(3);
  const std::string keys[]={"inbox","key","value"},values[]={inbox,key,number};
  for(int i=0;i<3;++i){esphome::api::HomeassistantServiceMap entry;entry.key=api_text::of(keys[i]);entry.value=api_text::of(values[i]);request.data.push_back(entry);}
  esphome::api::global_api_server->send_homeassistant_action(request);
}
} // namespace runtime_tiles
// Small shared native-LVGL detail cards. No images, canvas buffers or free scrolling.
namespace runtime_tiles {
inline lv_obj_t *detail_root=nullptr,*detail_backdrop=nullptr;
// A place in the open card, in the screen's coordinates: what a finger's point may be compared with.
// Everything a card draws is placed in detail_root's room, which overlay_card::frame puts in the middle
// of the glass, so the two only agree on a board whose cards fill their screen.
inline int detail_screen_x(int in_card){
  if(!detail_root)return in_card;
  lv_area_t a;lv_obj_get_content_coords(detail_root,&a);return int(a.x1)+in_card;
}
// The place of the `i`-th key from the right in an open card's top bar (detail_bar), in the card's own coordinates.
inline climate_card::Rect bar_key(int i=0){const auto r=detail_bar::right_slot(detail_root,i);return {r.x,r.y,r.w,r.h};}
// A card that works out its own room says so, and the frame then leaves it where it put itself.
inline bool detail_placed=false;
// What the climate card's keys answer with: a mode, a fan or swing choice, the power key and the setpoint's
// - and + (the card itself is further down, beside the vacuum's and the cover's).
inline constexpr int CLIMATE_MODE_FIRST=200,CLIMATE_ROW_FIRST=210,CLIMATE_POWER=230,CLIMATE_DOWN=231,CLIMATE_UP=232,CLIMATE_END_LOW=233,CLIMATE_END_HIGH=234;
inline void climate_paint_ends(const Tile &t);
// The power key of a light or fan card (firmware 0.2.80), in the same top bar.
inline constexpr int LIGHT_POWER=240;
// The rows of the select card (render_select_detail): option i is SELECT_OPTION_FIRST + i.
inline constexpr int SELECT_OPTION_FIRST=900;
// A remote's keypad (firmware 0.22.0+): key i of Extra::keypad is REMOTE_KEY_FIRST + i.
inline constexpr int REMOTE_KEY_FIRST=260;
enum RemoteKey : int { RK_UP, RK_DOWN, RK_LEFT, RK_RIGHT, RK_OK, RK_BACK, RK_HOME, RK_PLAY, RK_VOLUME_UP, RK_VOLUME_DOWN, RK_MUTE, RK_COUNT };
inline void climate_step(Tile &t,int direction);
inline const lv_font_t *tile_icon_font();
inline unsigned detail_index=0;
// A sensor that is no tile of its own, on the card a tap opened (firmware 0.47.0+): an energy card's circle opens its
// sensor's history, as a node of Home Assistant's own live view opens its more-info. Its index lies past every tile, so
// what works on a tile's card (its keys, its tile) finds nothing to do; what reads the open card asks detail_tile().
inline constexpr unsigned SENSOR_DETAIL=0xFFFFu;
inline Tile detail_sensor;
inline Tile *detail_tile(){return detail_index<model.count?&model.tiles[detail_index]:detail_index==SENSOR_DETAIL?&detail_sensor:nullptr;}
// The open card painted for the tile as it is now; false when it must be built again (another shape, or none).
inline bool card_repaint(const Tile &t) {
  if (!card_shape_of || !detail_root || lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN)) return false;
  if (card_shape_of(t) != card_shape) return false;
  ++card_pass;
  for (const auto &part : card_parts) part.paint(part.obj, t, part);
  return true;
}

}  // namespace runtime_tiles
#include "optimistic_lvgl.h"
#include "travel_stripe_lvgl.h"
#include "detail_lvgl.h"
#include "card_parts_lvgl.h"
#include "weather_card_lvgl.h"
#include "select_card_lvgl.h"
#include "vacuum_card_lvgl.h"
#include "cover_card_lvgl.h"
#include "remote_card_lvgl.h"
#include "light_card_lvgl.h"
#include "climate_card_lvgl.h"
#include "alarm_panel_lvgl.h"
#include "lock_panel_lvgl.h"
#include "history_card_lvgl.h"
#include "media_card_lvgl.h"
#include "detail_show_lvgl.h"
#include "tile_words_lvgl.h"
#include "colour_card_lvgl.h"
#include "tile_tap_lvgl.h"
#include "tile_widgets_lvgl.h"
#include "clock_tile_lvgl.h"
#include "weather_tile_lvgl.h"
#include "tile_controls_lvgl.h"
namespace runtime_tiles {
// ---- A favourite (firmware 0.24.0+, app 0.4.42+) ----
// One playlist, album or artist of a player's library on a tile of its own: a tap plays it on the speaker chosen for
// it (or where the player plays), and a tap while it plays pauses it. Holding opens the player's card. Where the board
// draws pictures, what it plays fills the card, dimmed as an album cover over a card is, with its name and line at the
// bottom and a round
// key at the bottom right; elsewhere it is an ordinary tile whose whole card is the key. What plays now has a ring of
// the accent. The app knows what each favourite plays; the screen only asks to play its tile.
inline uint32_t favorite_started_at[TILES_MAX]{};  // by the tile's index: a tap that is starting it, until the player plays
constexpr uint32_t FAVORITE_STARTING_MS = 12000;
inline bool favorite_starting(size_t index,const Tile &t){
  if(index>=TILES_MAX||!favorite_started_at[index])return false;
  if(t.extra().fav_playing||esphome::millis()-favorite_started_at[index]>=FAVORITE_STARTING_MS){favorite_started_at[index]=0;return false;}
  return true;
}
inline size_t tile_index(const Tile &t){return model.count?static_cast<size_t>(&t-&model.tiles[0]):SIZE_MAX;}
// The line under its name: "Playlist", "Playlist · Kitchen"; "Starting on Kitchen" while a tap starts it, "Playing" or
// "Playing · Kitchen" while it plays.
inline std::string favorite_line(const Tile &t){
  const auto &x=t.extra();
  const std::string speaker=!x.fav_source.empty()?x.fav_source:x.media_source;
  if(favorite_starting(tile_index(t),t))return speaker.empty()?std::string(tr(txt::media_loading)):fill(txt::media_starting_on,"speaker",speaker);
  if(x.fav_playing)return x.media_source.empty()?std::string(tr(txt::ha_media_playing)):std::string(tr(txt::ha_media_playing))+" · "+x.media_source;
  if(x.fav_kind.empty())return x.fav_source;
  return x.fav_source.empty()?x.fav_kind:x.fav_kind+" · "+x.fav_source;
}
// A tap: pause what it plays, or play it.
inline void favorite_tap(size_t index){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  if(t.extra().fav_playing&&t.state=="playing"){wish(t,optimistic::Field::PLAYING,"0","media_player.media_pause","","",media_entity(t));return;}
  // No speaker of its own and the player plays nowhere: which speaker first, as a cover in the library asks.
  const auto &x=t.extra();
  if(x.fav_source.empty()&&x.media_source.empty()&&!(t.supported&tile_controls::feature::MEDIA_PLAY_MEDIA)&&!x.media_sources.empty()){
    media_library::speakers(t.entity,0,static_cast<int>(index));
    return;
  }
  if(index<TILES_MAX)favorite_started_at[index]=std::max<uint32_t>(1,esphome::millis());
  library_event("esphome.screen_play",{{"entity",t.entity},{"tile",std::to_string(index)}});
  ESP_LOGI("library","Play favourite %u of %s",(unsigned)index,t.entity.c_str());
  refresh_tile(index,redraw_log::TileWhy::finger);
}
inline void favorite_key_event(lv_event_t *e){
  const unsigned slot=(uintptr_t)lv_event_get_user_data(e);
  if(slot>=widgets.size()||!enabled||!fresh())return;
  auto &w=widgets[slot];
  if(w.index>=model.count||w.extra_mode!="favorite"||!model.tiles[w.index].available())return;
  if(!allowed(esphome::millis(),TILE_TOUCH+static_cast<int>(w.index),model.tiles[w.index].entity))return;
  favorite_tap(w.index);
}
// The card with its picture, or while its picture is on its way the same card with the spinner every picture card
// has; false on a board without pictures and when the app has none, and the tile is drawn as an ordinary one.
inline bool render_favorite_card(Widgets &w,const Tile &t,int width,int height){
  tile_picture_place(w,t,0,0,0);
  const bool photo=w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN),waiting=!photo&&t.pictured()&&tile_picture_waiting(w,t);
  set_loading(w,waiting,width,height);
  if(!photo&&!waiting)return false;
  hide_panel(w);begin_extra(w,"favorite",width,height);
  for(auto *part:w.parts)if(part)lv_obj_add_flag(part,LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.circle,LV_OBJ_FLAG_HIDDEN);
  const bool large=ui::large();
  // The key: the size of a playback key, round and white, at the bottom right.
  const int key=std::min({std::max(ui::touch_min(),ui::px(large?44:32)),width/2,height});
  const media_card::Rect r{width-key,height-key,key,key};
  const bool starting=favorite_starting(w.index,t),playing=t.extra().fav_playing&&t.state=="playing";
  w.parts[0]=media_key(w.extra,w.parts[0],r,playing?tile_controls::glyph::PAUSE:tile_controls::glyph::PLAY,mini_icon_font?mini_icon_font:w.icon_font,false,false,t.available(),favorite_key_event,(void*)(uintptr_t)(&w-widgets.data()));
  set_number(w.parts[0],LV_STYLE_BG_OPA,starting?LV_OPA_60:LV_OPA_COVER);
  lv_obj_remove_flag(w.parts[0],LV_OBJ_FLAG_HIDDEN);
  // While a tap starts it, a ring turns round the key.
  if(starting){
    if(!w.parts[1])w.parts[1]=spinner_create(w.extra,key,ui::px(large?4:3));
    if(w.parts[1]){lv_obj_set_pos(w.parts[1],r.x,r.y);lv_obj_set_size(w.parts[1],key,key);lv_obj_remove_flag(w.parts[1],LV_OBJ_FLAG_HIDDEN);}
  }
  // The name and its line at the bottom left, on the shade the app put in the picture.
  const int name_h=lv_font_get_line_height(w.title_font),line_h=lv_font_get_line_height(w.value_font),text_w=std::max(1,width-key-ui::px(large?8:4));
  set_hidden(w.title,false);set_hidden(w.value,false);
  set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
  lv_obj_set_pos(w.title,0,height-name_h-line_h);lv_obj_set_size(w.title,text_w,name_h);
  lv_obj_set_pos(w.value,0,height-line_h);lv_obj_set_size(w.value,text_w,line_h);
  return true;
}
inline bool render_camera_card(Widgets &w,const Tile &t,int width,int height){
  tile_picture_place(w,t,0,0,0);
  const bool photo=w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN),waiting=!photo&&t.pictured()&&tile_picture_waiting(w,t);
  set_loading(w,waiting,width,height);
  if(!photo&&!waiting)return false;
  // A tall card to style_tall, which gives the name the picture's ink; it only has no parts of its own.
  hide_panel(w);begin_extra(w,"tall",width,height);
  for(auto *part:w.parts)if(part)lv_obj_add_flag(part,LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  // A map carries its name in the picture (on a pill in the card's own colours), so the label only stands in while the
  // picture is on its way.
  lv_obj_add_flag(w.circle,LV_OBJ_FLAG_HIDDEN);set_hidden(w.value,true);set_hidden(w.title,!t.overlay||(photo&&t.is_map()));
  const auto name=camera_view::name_box(width,height,lv_font_get_line_height(w.title_font));
  set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);
  lv_obj_set_pos(w.title,name.x,name.y);lv_obj_set_size(w.title,name.w,name.h);
  return true;
}
// False only for a full-page cover whose slat group cannot be drawn here (no tilt, or too little room): the caller
// then draws the ordinary full card with the primary controls, untouched by this function.
// A player's volume standing at the right of its taller card (volume_playback on a card wider than high), beside its
// playback keys: one of the card's own parts, so it stays inside the card's content however the keys stand, with the
// tile slider's look (slider_handle_standing) and colours (style_panel's: the fill in the accent over 20 % of it).
constexpr unsigned MEDIA_STANDING_PART=34;
inline void media_standing(Widgets &w,const Tile &t,int x,int y,int width,int height){
  auto *&s=w.parts[MEDIA_STANDING_PART];
  if(s&&!lv_obj_check_type(s,&lv_slider_class)){lv_obj_delete(s);s=nullptr;}
  if(!s){
    s=lv_slider_create(w.extra);
    lv_obj_remove_flag(s,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_remove_flag(s,LV_OBJ_FLAG_SCROLLABLE);
    lv_slider_set_orientation(s,LV_SLIDER_ORIENTATION_VERTICAL);
    lv_obj_set_style_pad_all(s,0,LV_PART_MAIN);
    lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_MAIN);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_INDICATOR);
    lv_obj_set_style_radius(s,2,LV_PART_KNOB);lv_obj_add_style(s,theme::style(theme::Paint::knob),LV_PART_KNOB);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_KNOB);
    lv_obj_set_style_border_width(s,0,LV_PART_KNOB);lv_obj_set_style_shadow_width(s,0,LV_PART_KNOB);
    lv_obj_add_event_cb(s,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)w.index);
  }
  lv_obj_set_pos(s,x,y);lv_obj_set_size(s,width,height);slider_handle_standing(s,width,height);
  const lv_color_t fill=t.muted?theme::color(theme::OFF):w.panel_accent,card=lv_color_hex(card_surface(w));
  set_color(s,LV_STYLE_BG_COLOR,lv_color_mix(fill,card,51),LV_PART_MAIN);set_color(s,LV_STYLE_BG_COLOR,fill,LV_PART_INDICATOR);
  if(!lv_obj_has_state(s,LV_STATE_PRESSED) && !(t.pending && !t.confirmed))lv_slider_set_value(s,slider_value(t),LV_ANIM_OFF);
  lv_obj_remove_flag(s,LV_OBJ_FLAG_HIDDEN);
}
// A light's presets on a card of one cell (module light_presets): its heading over a row of the keys, as a taller card
// has its controls under its name.
inline bool preset_cell(const Widgets &w,const Tile &t){
#ifdef SD_MOD_LIGHT_PRESETS
  return !w.wide&&!w.full&&t.row_span()==1&&t.domain()=="light"&&tile_controls::panel_kind(t)=="presets";
#else
  (void)w;(void)t;return false;
#endif
}
inline bool render_tall(Widgets &w,const Tile &t,bool selected,int width,int height) {
  selected=selected&&tile_controls::panel_available(t);
  const bool large=ui::large();const int gap=ui::px(large?8:4);
  const int touch=std::max(ui::touch_min(),ui::px(large?48:34));
  tall_tile::Metrics m{width,height,(int)lv_font_get_line_height(w.title_font),
    (int)lv_font_get_line_height(w.value_font),w.base_circle,gap,ui::touch_min(),ui::control_max_width(),{touch+2,0},selected?1:0};
  const int media_key=t.domain()=="media_player"?media_tall_key(touch,height):touch;
  if(media_key!=touch)m.row_heights={media_key+2,0};
  // A player's volume beside its keys: on a card wider than high it stands at the right, the whole height of the card,
  // and the heading, the track and the keys share the rest; on a narrower card it lies over the keys as a second row.
  // Without the room for either, its keys alone.
  // `standing` the volume's height at the card's right, -1 no room for the volume: the keys alone.
  const int whole_w=width;int standing=0;
  if(selected&&!w.full&&tile_controls::media_volume_selected(t)&&(t.supported&tile_controls::feature::MEDIA_VOLUME_SET)){
    const int lane=media_key,inner=width-lane-gap;
    auto beside=m;beside.width=inner;
    if(width*4>=height*5&&inner>=3*media_key+2*gap&&tall_tile::layout(beside).fits){m=beside;standing=height;width=inner;}
    else{
      auto both=m;both.row_heights={media_key+2,media_key+2};both.row_count=2;
      if(tall_tile::layout(both).fits)m=both;else standing=-1;
    }
  }
#ifdef SD_MOD_LIGHT_PRESETS
  // A light's slider with its presets under it: two rows, the second as high as the keys.
  if(selected&&tile_controls::panel_kind(t)=="brightness_presets"&&t.presets){
    auto both=m;both.row_heights={touch+2,light_presets::tile_key()+2*light_presets::ring()};both.row_count=2;
    if(tall_tile::layout(both).fits)m=both;
  }
  // The presets alone: a row as high as their keys and the ring round one, on a card of one cell and on a taller one.
  if(selected&&tile_controls::panel_kind(t)=="presets")m.row_heights={light_presets::tile_key()+2*light_presets::ring(),0};
#endif
  auto cover_metrics=m;cover_metrics.row_count=0;
  const auto cover_base=tall_tile::layout(cover_metrics);
  auto cover=cover_tile_layout(t,cover_base.body,touch,gap,m.state_h);
  // A card (not a full page) at least twice as wide as high puts its heading at the left and the cover's controls at the right, where
  // that gives them a richer layout than under the heading (a CYD's 2x2: two bars instead of one and its swap key).
  bool beside=false;
  // Only where the whole name fits the left half: a name cut short is worse than a poorer layout under it.
  const int side_circle=std::min(w.base_circle,width/6);
  if(!w.full&&width>=2*height&&text_width(lv_label_get_text(w.title),w.title_font)<=width/2-side_circle-gap){
    const auto side=cover_tile_layout(t,{width/2+gap,0,width-width/2-gap,height},touch,gap,m.state_h);
    if(side.fits&&(!cover.fits||side.tier>cover.tier)){cover=side;beside=true;}
  }
  if((w.full||t.row_span()==1)&&!cover.fits&&!tile_controls::climate_modes_selected(t)&&!preset_cell(w,t)){if(w.extra_mode=="cover_tilt")hide_extra(w);return false;}
  if(cover.fits){selected=false;m.row_count=0;}
  auto l=tall_tile::layout(m);
  // An unusual override can leave too little physical room for the selection.
  // Keep the entity heading and its existing detail action rather than clipping keys.
  if(!l.fits){selected=false;m.row_count=0;l=tall_tile::layout(m);}
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  if(!l.fits){hide_extra(w);hide_panel(w);return true;}
  if(t.is_settings()||t.is_page()||t.is_call()){
    const auto action=tall_tile::action(width,height,w.base_circle,lv_font_get_line_height(w.icon_font),
      m.name_h,lv_label_get_text(w.value)[0]?m.state_h:0,gap);
    if(action.fits){
      hide_panel(w);hide_extra(w);
      lv_obj_set_size(w.circle,action.icon.w,action.icon.h);lv_obj_set_pos(w.circle,action.icon.x,action.icon.y);
      set_font(w.icon,action.icon.w>=w.base_circle||!mini_icon_font?w.icon_font:mini_icon_font);center_icon(w.icon);
      set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_CENTER);
      lv_obj_set_pos(w.title,action.title.x,action.title.y);lv_obj_set_size(w.title,action.title.w,action.title.h);
      set_font(w.value,w.value_font);set_text_align(w.value,LV_TEXT_ALIGN_CENTER);
      lv_obj_set_pos(w.value,action.state.x,action.state.y);lv_obj_set_size(w.value,action.state.w,std::max(1,action.state.h));
      set_hidden(w.value,action.state.empty());
      return true;
    }
  }
  // An on/off or run card two rows tall is one big key (firmware 0.17.0+, big_key): a large circle, the name in the
  // page's headline size and the state under it, and no switch or run key: the whole card is what you tap.
  if(t.row_span()>=2&&!w.full&&big_key(t)){
    hide_panel(w);hide_extra(w);
    // The page's headline size for the name when the whole name fits the card, else the tile's own title size.
    const lv_font_t *name_font=room_label?lv_obj_get_style_text_font(room_label,LV_PART_MAIN):w.title_font;
    if(text_width(lv_label_get_text(w.title),name_font)>width)name_font=w.title_font;
    const int name_h=lv_font_get_line_height(name_font),side=std::min(width,height)*44/100;
    const auto a=tall_tile::action(width,height,side,lv_font_get_line_height(w.icon_font),name_h,l.state?m.state_h:0,gap);
    if(a.fits){
      const lv_font_t *icon_font=big_icon_font&&font_has(big_icon_font,icon_for(t))&&a.icon.w>=ui::px(96)?big_icon_font:w.icon_font;
      lv_obj_set_size(w.circle,a.icon.w,a.icon.h);lv_obj_set_pos(w.circle,a.icon.x,a.icon.y);
      set_font(w.icon,icon_font);center_icon(w.icon);
      set_font(w.title,name_font);set_text_align(w.title,LV_TEXT_ALIGN_CENTER);lv_obj_set_pos(w.title,a.title.x,a.title.y);lv_obj_set_size(w.title,a.title.w,a.title.h);
      set_text_align(w.value,LV_TEXT_ALIGN_CENTER);lv_obj_set_pos(w.value,a.state.x,a.state.y);lv_obj_set_size(w.value,a.state.w,std::max(1,a.state.h));
      set_hidden(w.value,a.state.empty());
      tile_picture_place(w,t,a.icon.w,a.icon.x,a.icon.y);
    }
    return true;
  }
  int circle=std::min({w.base_circle,l.header.h,width/3});
  const lv_font_t *heading_font=heading_icon(w,circle,l.header.h,width);
  const int tx=circle+gap,tw=std::max(1,width-tx),lines=m.name_h+(l.state?m.state_h:0);
  const int y=(l.header.h-lines)/2;
  lv_obj_set_size(w.circle,circle,circle);lv_obj_set_pos(w.circle,0,(l.header.h-circle)/2);
  set_font(w.icon,heading_font);center_icon(w.icon);
  set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);
  lv_obj_set_pos(w.title,tx,y);lv_obj_set_size(w.title,tw,m.name_h);
  set_font(w.value,w.value_font);set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
  lv_obj_set_pos(w.value,tx,y+m.name_h);lv_obj_set_size(w.value,tw,m.state_h);set_hidden(w.value,!l.state);
  tile_picture_place(w,t,circle,0,(l.header.h-circle)/2);
  if(cover.fits&&beside){
    // The heading stands in the left half, its circle, name and state centred on the card's height.
    const int half=width/2,lines=m.name_h+m.state_h,ty=(height-lines)/2;
    int c=std::min(w.base_circle,half/3);
    const lv_font_t *font=heading_icon(w,c,height,half);
    lv_obj_set_size(w.circle,c,c);lv_obj_set_pos(w.circle,0,(height-c)/2);
    set_font(w.icon,font);center_icon(w.icon);
    lv_obj_set_pos(w.title,c+gap,ty);lv_obj_set_size(w.title,std::max(1,half-c-gap),m.name_h);
    lv_obj_set_pos(w.value,c+gap,ty+m.name_h);lv_obj_set_size(w.value,std::max(1,half-c-gap),m.state_h);set_hidden(w.value,false);
    tile_picture_place(w,t,c,0,(height-c)/2);
  }
  if(cover.fits){render_cover_tile(w,t,cover,width,height);return true;}
  bool panel=selected&&layout_panel(w,t,large,width,height,standing);
  if(!panel)hide_panel(w);
  if(panel){
    const int pw=lv_obj_get_style_width(w.panel,LV_PART_MAIN),ph=lv_obj_get_style_height(w.panel,LV_PART_MAIN);
    // Its rows together: one row, or the volume's and the keys' with the gap between them.
    const int top=l.rows[0].y,room=(l.count>1?l.rows[1].bottom():l.rows[0].bottom())-top;
    if(pw>width||ph>room){hide_panel(w);panel=false;}
    else lv_obj_set_pos(w.panel,(width-pw)/2,top+(room-ph)/2);
    // Beside a standing volume the keys start at the card's left, under the track and the name: one left edge for the
    // card's words and keys, the volume its counterweight at the right (centred in the room left, they looked off).
    if(panel&&standing>0)lv_obj_set_x(w.panel,0);
  }
  const auto d=t.domain();
  begin_extra(w,"tall",whole_w,height);
  for(auto *part:w.parts)if(part)lv_obj_add_flag(part,LV_OBJ_FLAG_HIDDEN);
  if(panel&&standing>0)media_standing(w,t,width+gap,0,whole_w-width-gap,standing);
  auto text=[&](int i,const std::string &value,const lv_font_t *font,tall_tile::Rect area,lv_text_align_t align){
    if(value.empty()||area.h<(int)lv_font_get_line_height(font))return false;
    auto *p=part_label(w,i,font,area.x,area.y,area.w,align,value);
    if(d=="media_player"&&i==0)marquee(p,true,tile_picture_marquee_ready(w,t));
    else if(lv_label_get_long_mode(p)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);
    lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);
    return true;
  };
  // A card that shows its value large does not repeat it in small type under the name. A second line of the user's
  // own (other words, another value) differs from the headline and stays.
  auto drop_repeat=[&](const std::string &headline){
    if(headline.empty()||lv_obj_has_flag(w.value,LV_OBJ_FLAG_HIDDEN))return;
    const std::string state=lv_label_get_text(w.value);
    if(state!=headline&&state.rfind(headline+" ",0)!=0)return;
    set_hidden(w.value,true);lv_obj_set_y(w.title,(l.header.h-m.name_h)/2);
  };
  if((d=="climate"||d=="humidifier")&&panel&&w.panel_mode=="setpoint"){
    // Home Assistant's thermostat in two groups (firmware 0.3.3, climate_tile.h): the number between - and + is the
    // first thing, the mode bar the second; off is the circle in the head. The big form stands the number large in
    // the middle with the bar under it, the row form puts a stepper and the bar on one finger's row. Which modes the
    // bar shows is tile_controls::climate_bar_keys: heat and cool first, the current one always.
    std::array<tile_controls::Key,CLIMATE_MODE_PARTS> modes;
    const bool wanted=tile_controls::climate_modes_selected(t);
    const int want=wanted?(int)tile_controls::climate_bar_keys(t,modes):0;
    // A range's chip carries an icon beside the number (two digits' room for it) and is measured by its widest temperature.
    const std::string target=tile_controls::climate_range(t)?tile_controls::widest_setpoint(t)+"88":std::string(lv_label_get_text(w.pill_value));
    climate_tile::Metrics cm;cm.large=large;cm.touch=touch;cm.gap=gap;cm.max_width=ui::control_max_width();
    const lv_font_t *faces[climate_tile::FACES]={setpoint_font,watch_value_font,control_font?control_font:w.title_font};
    for(int f=0;f<climate_tile::FACES;++f){
      const bool usable=faces[f]&&face_covers(faces[f],target);
      cm.face_h[f]=usable?lv_font_get_line_height(faces[f]):0;cm.face_w[f]=usable?text_width(target,faces[f])+2:0;
    }
    cm.caption_h=m.state_h;
    const auto cl=climate_tile::layout(cm,width,l.body.y,height,want);
    if(cl.form!=climate_tile::Form::none){
      w.hand_r=cl.form==climate_tile::Form::row?1:2;
      const bool row=cl.form==climate_tile::Form::row;
      // The big form's number stands taller than its keys and has the "now" line under it: the panel holds all of
      // them, or the digits are cut at its edge and the line lies under the panel.
      const int top_y=std::min(cl.minus.y,cl.number.y);
      const int bottom_y=std::max({cl.minus.bottom(),cl.number.bottom(),cl.caption?cl.caption_box.bottom():0});
      const auto area=row?cl.stepper:climate_tile::Rect{cl.minus.x,top_y,cl.plus.right()-cl.minus.x,bottom_y-top_y};
      lv_obj_set_pos(w.panel,area.x,area.y);lv_obj_set_size(w.panel,area.w,area.h);lv_obj_set_size(w.pill,area.w,area.h);
      for(int n=0;n<2;++n){
        const auto &k=n?cl.plus:cl.minus;
        lv_obj_set_size(w.keys[n],k.w,k.h);lv_obj_set_pos(w.keys[n],k.x-area.x,k.y-area.y);
        lv_obj_set_style_bg_opa(w.keys[n],LV_OPA_COVER,0);lv_obj_set_style_radius(w.keys[n],LV_RADIUS_CIRCLE,0);
        lv_obj_set_ext_click_area(w.keys[n],row?cm.inset():0);center_icon(w.key_icons[n]);
      }
      const lv_font_t *number=faces[cl.face];
      set_font(w.pill_value,number);
      lv_obj_set_pos(w.pill_value,cl.number.x-area.x,cl.number.y-area.y);lv_obj_set_size(w.pill_value,cl.number.w,cl.number.h);
      range_chip(w,t,cl.number.x-area.x,cl.number.y-area.y,cl.number.w,cl.number.h,cl.number.h,{number,watch_value_font,w.value_font});
      // The "now" line lives in the pill beside the number (its fourth child), so the panel is one block.
      if(lv_obj_get_child_count(w.pill)<4){auto *line=lv_label_create(w.pill);lv_obj_remove_flag(line,LV_OBJ_FLAG_CLICKABLE);
        lv_label_set_long_mode(line,LV_LABEL_LONG_DOT);lv_obj_set_style_text_align(line,LV_TEXT_ALIGN_CENTER,0);}
      auto *now_line=lv_obj_get_child(w.pill,3);
      set_hidden(now_line,!(cl.caption&&std::isfinite(t.current)));
      if(cl.caption&&std::isfinite(t.current)){
        set_font(now_line,w.value_font);label(now_line,screen_text::fill(txt::climate_now,"value",tile_controls::reading_text(t,t.current)));
        set_color(now_line,LV_STYLE_TEXT_COLOR,theme::color(theme::MUTED));
        lv_obj_set_pos(now_line,cl.caption_box.x-area.x,cl.caption_box.y-area.y);lv_obj_set_size(now_line,cl.caption_box.w,cl.caption_box.h);
      }
      if(!cl.bar.empty())draw_mode_bar(w,t,w.extra,w.parts[2],&w.parts[4],cl.bar,cl.room,cm,large);
      return true;
    }
    w.hand_r=0;hide_panel(w);
  }
  if(panel&&w.panel_mode=="toggle"){
    // An on/off card has no value for its body: icon, name, state and the switch stand as one centred stack, the way
    // a built-in action card does, on every grid and glass. Too little room keeps the heading above the switch.
    const int pw=lv_obj_get_style_width(w.panel,LV_PART_MAIN),ph=lv_obj_get_style_height(w.panel,LV_PART_MAIN);
    const auto a=tall_tile::action(width,height,w.base_circle,lv_font_get_line_height(w.icon_font),m.name_h,
      l.state?m.state_h:0,gap,pw,ph);
    if(a.fits){
      lv_obj_set_size(w.circle,a.icon.w,a.icon.h);lv_obj_set_pos(w.circle,a.icon.x,a.icon.y);
      set_font(w.icon,a.icon.w>=w.base_circle||!mini_icon_font?w.icon_font:mini_icon_font);center_icon(w.icon);
      set_text_align(w.title,LV_TEXT_ALIGN_CENTER);lv_obj_set_pos(w.title,a.title.x,a.title.y);lv_obj_set_size(w.title,a.title.w,a.title.h);
      set_text_align(w.value,LV_TEXT_ALIGN_CENTER);lv_obj_set_pos(w.value,a.state.x,a.state.y);lv_obj_set_size(w.value,a.state.w,std::max(1,a.state.h));
      set_hidden(w.value,a.state.empty());
      lv_obj_set_pos(w.panel,a.control.x,a.control.y);
      tile_picture_place(w,t,a.icon.w,a.icon.x,a.icon.y);
    }
    return true;
  }
  auto body=l.body;
  if(d=="media_player"){
    const auto &x=t.extra();
    const std::string title=fresh()&&t.available()&&media_card::has_track(t.state)?x.media_title:std::string();
    const std::string artist=media_card::subtitle(x.media_artist,x.media_album);
    // The largest step of the board's text fonts that fits (docs/RESPONSIVE.md, "One set of fonts"): on a large card
    // the track in the large value's face with its artist in the top bar's, then the page headline over the small text,
    // then the tile's name. The large face only where the whole title fits the width (a marquee that size reads badly)
    // and leaves its artist line room; the artist gives way before the title steps down.
    const lv_font_t *headline=room_label?lv_obj_get_style_text_font(room_label,LV_PART_MAIN):w.title_font;
    struct Step{const lv_font_t *title,*artist;bool whole;};
    const Step steps[]={{watch_value_font,control_font?control_font:w.value_font,true},{headline,w.value_font,false},{w.title_font,w.value_font,false}};
    const lv_font_t *font=w.title_font,*small=w.value_font;bool secondary=false;
    for(const auto &step:steps){
      if(!step.title||!face_covers(step.title,title))continue;
      const int th=lv_font_get_line_height(step.title),ah=lv_font_get_line_height(step.artist);
      if(th>body.h||(step.whole&&(title.empty()||text_width(title,step.title)>width)))continue;
      const bool both=!artist.empty()&&body.h>=th+ah+gap/2;
      if(step.whole&&!artist.empty()&&!both)continue;
      font=step.title;small=step.artist;secondary=both;break;
    }
    const int fh=lv_font_get_line_height(font),ah=lv_font_get_line_height(small);
    int y=body.y+std::max(0,(body.h-fh-(secondary?ah+gap/2:0))/2);
    if(text(0,title,font,{0,y,width,fh},LV_TEXT_ALIGN_LEFT))drop_repeat(title);
    if(secondary)text(1,artist,small,{0,y+fh+gap/2,width,ah},LV_TEXT_ALIGN_LEFT);
  }else if((d=="climate"||d=="humidifier")&&std::isfinite(t.current)){
    const auto *font=watch_value_font&&lv_font_get_line_height(watch_value_font)<=body.h?watch_value_font:w.value_font;
    text(0,tile_controls::reading_text(t,t.current),font,{0,body.y+std::max(0,(body.h-static_cast<int>(lv_font_get_line_height(font)))/2),width,body.h},LV_TEXT_ALIGN_CENTER);
  }else if(tile_controls::text_value(t)&&!t.secret){
    // A text's value (docs/TEXT_ENTITY.md) fills the body under the head, from its top, over as many lines as it holds,
    // the last ending in dots: a long note reads whole, and the name stays at the top. One line of a short value stands
    // in the middle of the body, as any value does. A card of one row keeps its one line under the name.
    const std::string value=tile_controls::text_shown(t);
    const lv_font_t *font=w.value_font;
    const int lh=lv_font_get_line_height(font),lines=std::min(8,lh>0?body.h/lh:0);
    const bool one=text_width(value,font)<=width;
    if(lines>0&&text(0,value,font,{0,one?body.y+(body.h-lh)/2:body.y,width,body.h},LV_TEXT_ALIGN_LEFT)){
      if(!one){lv_label_set_long_mode(w.parts[0],LV_LABEL_LONG_DOT);lv_obj_set_height(w.parts[0],lines*lh);}
      // The body is the value: the line under the name would repeat it (cut short, which drop_repeat cannot see).
      set_hidden(w.value,true);lv_obj_set_y(w.title,(l.header.h-m.name_h)/2);
    }
  }else if(!t.builtin() && fresh() && t.available()){
    const std::string value=d=="light"?light_value_text(t):card_status(t,true);
    const lv_font_t *font=w.value_font;
    // A light's percentage that cannot take the large face (its slider and presets under it) steps down to the controls'
    // regular face, never the bold name's: a value, not a heading.
    const lv_font_t *second=d=="light"&&control_font?control_font:w.title_font;
    for(const auto *candidate:{watch_value_font,second,w.value_font})
      if(candidate&&face_covers(candidate,value)&&tall_tile::fits_text(body,text_width(value,candidate),lv_font_get_line_height(candidate))){font=candidate;break;}
    if(text(0,value,font,{0,body.y+std::max(0,(body.h-static_cast<int>(lv_font_get_line_height(font)))/2),width,body.h},LV_TEXT_ALIGN_CENTER))
      drop_repeat(value);
  }
  return true;
}
// A favourite that plays now has a ring of the accent (firmware 0.24.0+), drawn over its picture along the card's own
// corners. An outline outside the card left the picture's corners, which the app fills with the page's colour, as a
// light wedge between the ring and the picture. The ring is drawn after the card's parts (ring_draw) and is no border:
// a wider border moved the card's inside, so the picture under it slid out past the ring by the difference and the
// card looked to grow. Every other card keeps its hairline under its parts.
inline void ring_favorite(Widgets &w,const Tile &t){
  const bool ringed=t.favorite()&&t.extra().fav_playing;
  if(lv_obj_has_flag(w.tile,LV_OBJ_FLAG_USER_1)==ringed)return;
  if(ringed)lv_obj_add_flag(w.tile,LV_OBJ_FLAG_USER_1);else lv_obj_remove_flag(w.tile,LV_OBJ_FLAG_USER_1);
  lv_obj_invalidate(w.tile);
}
inline void style_tall(Widgets &w,const Tile &t){
  // A thermostat's stepper (render_tall, climate_tile.h): a grey pill with white keys on one row, or the keys alone
  // in grey beside a big number. The number is grey while the thermostat is off.
  if(tile_controls::thermostat(t)&&w.extra_mode=="tall"&&w.panel_mode=="setpoint"&&w.pill&&(w.hand_r==1||w.hand_r==2)){
    const bool row=w.hand_r==1;
    lv_obj_set_style_bg_opa(w.pill,row?LV_OPA_COVER:LV_OPA_TRANSP,0);set_color(w.pill,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
    for(int n=0;n<2;++n)if(w.keys[n]){
      set_color(w.keys[n],LV_STYLE_BG_COLOR,theme::color(row?theme::STEPPER_KEY:theme::TRACK));
      set_color(w.keys[n],LV_STYLE_BG_COLOR,theme::color(row?theme::STEPPER_KEY_PRESSED:theme::KEY_PRESSED),LV_STATE_PRESSED);
      if(w.key_icons[n])set_color(w.key_icons[n],LV_STYLE_TEXT_COLOR,theme::color(theme::INK));
    }
    set_color(w.pill_value,LV_STYLE_TEXT_COLOR,theme::color(tile_controls::climate_off(t)?theme::MUTED:theme::INK));
  }
  // A favourite over its picture (firmware 0.24.0+): light words on the dimmed picture, a white key with a dark glyph;
  // while the picture is on its way, the card's own words and the accent key.
  if(w.extra_mode=="favorite"){
    const bool photo=w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    set_color(w.title,LV_STYLE_TEXT_COLOR,theme::color(photo?theme::CAMERA_INK:theme::INK));
    set_color(w.value,LV_STYLE_TEXT_COLOR,theme::color(photo?theme::CAMERA_INK:theme::MUTED));
    if(w.parts[0]){
      set_color(w.parts[0],LV_STYLE_BG_COLOR,theme::color(photo?theme::CAMERA_INK:theme::ACCENT));
      set_color(w.parts[0],LV_STYLE_BG_COLOR,theme::color(photo?theme::CAMERA_NOTE:theme::ACCENT_PRESSED),LV_STATE_PRESSED);
      if(auto *icon=lv_obj_get_child(w.parts[0],0))set_color(icon,LV_STYLE_TEXT_COLOR,theme::color(photo?theme::CAMERA_PAGE:theme::ON_ACCENT));
    }
    return;
  }
  // An album cover over a card of one row (card_art): light words on the dimmed picture and the icon in a dark circle,
  // as on a taller card; while the picture is on its way, or for a player without one, the card's own colours.
  if(w.extra_mode!="tall"&&t.cover_tile()&&t.row_span()==1&&!t.full){
    if(!card_art(t)||!w.picture||lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN))return;
    const auto ink=theme::color(theme::CAMERA_INK);
    set_color(w.title,LV_STYLE_TEXT_COLOR,ink);set_color(w.value,LV_STYLE_TEXT_COLOR,ink);
    set_color(w.circle,LV_STYLE_BG_COLOR,theme::color(theme::CAMERA_TRACK));set_color(w.icon,LV_STYLE_TEXT_COLOR,ink);
    return;
  }
  if(w.extra_mode!="tall"||(!t.live()&&!t.is_map()&&(t.row_span()<2||t.full)))return;
  const bool photo=card_art(t)&&w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
  const auto ink=theme::color(photo?theme::CAMERA_INK:theme::INK),muted=theme::color(photo?theme::CAMERA_INK:theme::MUTED);
  set_color(w.title,LV_STYLE_TEXT_COLOR,ink);set_color(w.value,LV_STYLE_TEXT_COLOR,muted);
  for(unsigned i=0;i<2;++i)if(w.parts[i])set_color(w.parts[i],LV_STYLE_TEXT_COLOR,i?muted:ink);
  if(photo){set_color(w.circle,LV_STYLE_BG_COLOR,theme::color(theme::CAMERA_TRACK));set_color(w.icon,LV_STYLE_TEXT_COLOR,ink);}
  if(w.panel_mode=="playback"){
    for(unsigned n=0;n<3;++n)if(w.keys[n]){
      lv_obj_set_style_radius(w.keys[n],LV_RADIUS_CIRCLE,0);lv_obj_set_ext_click_area(w.keys[n],0);
      const bool primary=w.key_commands[n]==tile_controls::MEDIA_PLAY_PAUSE;
      set_color(w.keys[n],LV_STYLE_BG_COLOR,theme::color(primary?(photo?theme::CAMERA_INK:theme::ACCENT):theme::TRACK));
      lv_obj_set_style_bg_opa(w.keys[n],photo&&!primary?LV_OPA_TRANSP:LV_OPA_COVER,0);
      if(w.key_icons[n])set_color(w.key_icons[n],LV_STYLE_TEXT_COLOR,theme::color(primary?(photo?theme::CAMERA_PAGE:theme::ON_ACCENT):(photo?theme::CAMERA_INK:theme::INK)));
    }
  }
}
inline void render_full(Widgets &w,const Tile &t,bool custom,bool clock,bool sunpath,bool graph,bool mini,bool with_panel,bool large,
                        const std::string &value,const std::string &unit,int content_w,int content_h) {
  const bool big=ui::large();  // the look's class, never the cell's height
  lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
  if(custom){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);
    // The forecast and the sun path keep their board's layout (the CYD's two-row days); a taller dial is fine.
    if(clock)render_clock(w,t,large,content_w,content_h);
    else if(sunpath)render_sunpath(w,t,big,content_w,content_h);
    else render_forecast(w,t,big,content_w,content_h);
    return;
  }
  int value_h=lv_font_get_line_height(lv_obj_get_style_text_font(w.value,LV_PART_MAIN));
  int gap=ui::px(big?12:6);
  // A media player that answers gets the media card under its head (firmware 0.2.64+); unavailable, it is the plain card.
  const bool media=t.domain()=="media_player" && fresh() && t.available();
  if(!mini && !with_panel && !graph && !media){
    hide_extra(w);hide_panel(w);lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
    const lv_font_t *name_font=room_label?lv_obj_get_style_text_font(room_label,LV_PART_MAIN):w.title_font;
    int name_h=lv_font_get_line_height(name_font),circle=ui::px(big?128:64);
    int block=circle+gap+name_h+2+value_h,top=std::max(0,(content_h-block)/2);
    lv_obj_set_size(w.circle,circle,circle);lv_obj_set_pos(w.circle,std::max(0,(content_w-circle)/2),top);
    tile_picture_place(w,t,circle,std::max(0,(content_w-circle)/2),top);
    // The big icon font carries the domain icons; another chosen icon keeps its usual size in the big circle.
    const lv_font_t *icon_font=big_icon_font && font_has(big_icon_font,icon_for(t))?big_icon_font:w.icon_font;
    if(lv_obj_get_style_text_font(w.icon,LV_PART_MAIN)!=icon_font)set_font(w.icon,icon_font);center_icon(w.icon);
    set_font(w.title,name_font);set_text_align(w.title,LV_TEXT_ALIGN_CENTER);set_text_align(w.value,LV_TEXT_ALIGN_CENTER);
    lv_obj_set_height(w.title,name_h);
    lv_obj_set_pos(w.title,0,top+circle+gap);lv_obj_set_width(w.title,content_w);
    lv_obj_set_pos(w.value,0,top+circle+gap+name_h+2);lv_obj_set_width(w.value,content_w);
    if(!unit.empty())label(w.value,screen_text::with_unit(value,unit));
    return;
  }
  // The head as on the double-width card: the circle at the left, name and state beside it.
  set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
  int title_h=lv_font_get_line_height(w.title_font);
  lv_obj_set_height(w.title,title_h);
  // The head is one cell of the look (ui::cell_height) less the card's padding, whatever grid the board has, and
  // never more than 30 % of the card: a wide 4.3 inch has 56 mm of glass under the bar, where a Guition's head would
  // take from the media card what its keys need (30 % is the share the head has on a CYD graph card, 48 of 160, so both
  // reference boards keep their pixels). The circle and the two lines stand in it by the one rule (head_row).
  // Whatever stands under the head is placed from head_h, which never ends above what the head draws.
  int head_h=std::max<int>(1,std::min<int>(ui::cell_height()-lv_obj_get_style_space_top(w.tile,LV_PART_MAIN)-lv_obj_get_style_space_bottom(w.tile,LV_PART_MAIN),content_h*30/100));
  const HeadRow head=head_row(w,big,w.base_circle>0?w.base_circle:ui::px(big?54:36),head_h,title_h,value.empty()?0:value_h);
  const int circle=head.circle;
  lv_obj_set_size(w.circle,circle,circle);
  if(lv_obj_get_style_text_font(w.icon,LV_PART_MAIN)!=w.icon_font)set_font(w.icon,w.icon_font);center_icon(w.icon);
  lv_obj_set_pos(w.circle,0,head.circle_y);
  tile_picture_place(w,t,circle,0,head.circle_y);
  lv_obj_set_pos(w.title,head.text_x,head.title_y);
  lv_obj_set_pos(w.value,head.text_x,head.value_y);
  lv_obj_set_width(w.title,std::max(1,content_w-head.text_x));lv_obj_set_width(w.value,std::max(1,content_w-head.text_x));
  head_h=std::max(head_h,std::max(head.circle_y+circle,head.value_y+value_h));
  if(media){
    hide_panel(w);lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
    render_media_full(w,t,big,content_w,content_h,head_h);
    return;
  }
  if(mini){
    // The small slider becomes a strip a thumb finds at the bottom; the room above it is the button.
    hide_extra(w);hide_panel(w);
    int strip=ui::px(big?64:40);
    lv_obj_set_size(w.slider,content_w,strip);lv_obj_set_ext_click_area(w.slider,slider_zone(w,strip));
    slider_handle(w.slider,content_w,strip);
    lv_obj_remove_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
    travel_look(w.slider,t,false,true);
    if(!lv_obj_has_state(w.slider,LV_STATE_PRESSED) && lv_slider_get_value(w.slider)!=slider_value(t))lv_slider_set_value(w.slider,slider_value(t),LV_ANIM_OFF);
    return;
  }
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
  if(graph){
    hide_panel(w);
    render_graph(w,t,large,0,head_h+gap,content_w,std::max(8,content_h-head_h-gap));
    return;
  }
  // Direct controls at the bottom, centred; the room between shows what the double-width card had no room for.
  hide_extra(w);
  if(!layout_panel(w,t,large,content_w,content_h)){hide_panel(w);return;}
  int panel_h=lv_obj_get_style_height(w.panel,LV_PART_MAIN);
  int mid_top=head_h,mid_h=content_h-head_h-gap-panel_h;
  // The large value font carries digits, the degree sign and the percent sign; the clock font only digits and a colon.
  std::string middle;const lv_font_t *mid_font=watch_value_font?watch_value_font:w.value_font;
  auto d=t.domain();
  if((d=="climate"||d=="humidifier") && std::isfinite(t.current))middle=tile_controls::reading_text(t,t.current);
  else if(d=="cover" && std::isfinite(t.position)){middle=screen_text::percent(static_cast<int>(std::lround(t.position)));}
  else if(d=="media_player" && !t.extra().media_title.empty()){middle=t.extra().media_title;mid_font=room_label?lv_obj_get_style_text_font(room_label,LV_PART_MAIN):w.title_font;}
  int mid_font_h=lv_font_get_line_height(mid_font);
  if(middle.empty() || mid_h<mid_font_h)return;
  set_font(w.unit,mid_font);set_text_align(w.unit,LV_TEXT_ALIGN_CENTER);label(w.unit,middle);
  lv_obj_set_pos(w.unit,0,mid_top+std::max(0,(mid_h-mid_font_h)/2));lv_obj_set_size(w.unit,content_w,mid_font_h);
  lv_obj_remove_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
}
// One card: name, status, icon, layout and palette. Everything reads the model; nothing is created
// unless the card's custom parts or controls change kind.
// A key that shows its value instead of an icon (firmware 0.8.0+): what is read, not switched, such as a temperature.
inline bool key_shows_value(const Tile &t){
  const std::string d=t.domain();
  if(d=="weather")return std::isfinite(t.current);
  return (d=="sensor"||d=="number"||d=="input_number") && !t.state.empty() && t.state!="unknown";
}
// The value in a key: a temperature as its number and degree sign ("19,5°"), a percentage with its sign, any other
// number alone; the name under the key says what it is.
inline std::string key_value(const Tile &t){
  if(t.domain()=="weather")return screen_text::decimal(t.current,1)+"°";
  char *end=nullptr;const float number=strtof(t.state.c_str(),&end);
  if(!end||*end||!std::isfinite(number))return t.state;
  const std::string text=screen_text::localize(t.state);
  if(t.unit.rfind("°",0)==0)return text+"°";
  if(t.unit=="%")return screen_text::percent((int)std::lround(number));
  return text;
}
#ifdef SD_MOD_SECTIONS
// A card in a section whose tiles follow its contrast (docs/PAGES.md "Sections") is painted in the other look: every
// role it asks for while it is drawn comes in that look, and what it takes from the shared paints is set on it in that
// look once it is drawn (module_sections.h follow). A card that leaves such a section gives those back.

#endif
inline void render_slot(size_t slot) {
  swipe_profile::SlotTimer slot_timer(slot);
  swipe_profile::Lap lap;
  auto &w=widgets[slot];
  if(!w.tile || w.index>=model.count)return;
#ifdef SD_MOD_SECTIONS
  CardScope look(w);  // the card's look for the whole paint (docs/THEME.md "A card's look"); without sections, the screen's
#endif
  const auto &t = model.tiles[w.index];
  auto d=t.domain();
  // A slot is another tile on another page: only a camera card that waits for its picture keeps a spinner.
  if(w.loading&&!(t.live()||t.is_map()||t.favorite()))lv_obj_add_flag(w.loading,LV_OBJ_FLAG_HIDDEN);
  label(w.title, t.name.empty() ? t.entity : t.name);
  label(w.icon, icon_for(t));
  bool watch=t.display=="watch";
  // Home Assistant's own words for the value (a duration in hours and minutes, firmware 0.56.0+) carry their units.
  std::string unit=watch&&t.extra().state_word.empty()?t.unit:"";
  std::string value = t.state;
  // What the second line was set to wins over every word the screen would work out itself (firmware 0.2.90+),
  // but not over the two that say the screen cannot answer: an unavailable entity and a refused tap still say so.
  std::string chosen;
  const bool set_by_hand = chosen_subtitle(t, chosen);
  const bool refused = t.refused_at && esphome::millis() - t.refused_at < 4000;
  // A tile of a plugin this screen does not have (docs/PLUGINS.md) is a plain card that says so; one it has draws itself.
  if (t.is_plugin())
    value = plugin_host::known(t) ? std::string() : std::string(tr(txt::plugin_missing));
  // Nothing in Home Assistant stands behind a built-in card, so it says its own line with the link down too.
  else if (t.is_settings() || t.is_page() || t.is_call())
    value = set_by_hand ? chosen
          : t.is_settings() || t.is_call() ? std::string(tr(txt::tile_tap_to_open))
          : fill(txt::tile_page, "n", t.page_target());
  else if (!fresh() || !t.available()) value = tr(txt::ha_unavailable);
  else if (refused) value = tr(t.unanswered ? txt::tile_no_answer : txt::tile_refused);
  else if (set_by_hand) value = chosen;
  // A text's value as it is (docs/TEXT_ENTITY.md): "on" is no On here, and an empty value leaves the line empty.
  else if (tile_controls::text_value(t)) value = tile_controls::text_shown(t);
  else if (d == "light" && t.state == "on" && tile_controls::effect_running(t.extra().effect)) value = t.extra().effect;
  else if (d == "light" && t.state == "on" && std::isfinite(t.brightness)) value = screen_text::percent(static_cast<int>(std::lround(std::clamp(t.brightness, 0.0f, 255.0f) * 100 / 255)));
  // An airco that is off says so, with the room's temperature when it knows it, as Home Assistant's tile does
  // (firmware 0.2.71+); while it runs, the tile shows the temperature it is set to, written as Home Assistant writes
  // it: 68°, 21.5° (firmware 0.19.0; before, always one decimal).
  else if (d == "climate" && t.state == "off") { value = tile_controls::climate_mode_text(t.state); if (std::isfinite(t.current)) value += " · " + tile_controls::temperature_text(t.current); }
  else if (d == "climate" && std::isfinite(t.target)) value = tile_controls::temperature_text(t.target);
  // Without one temperature to reach (a range, dry, fan only) the line is Home Assistant's own tile line for a
  // thermostat, its state and the room's temperature (state-display: climate ["state", "current_temperature"]).
  else if (d == "climate") { value = tile_controls::climate_mode_text(tile_controls::lower_case(t.state)); if (std::isfinite(t.current)) value += " · " + tile_controls::temperature_text(t.current); }
  // A humidifier says what it is doing (or On, Off) and the humidity it measures: Home Assistant's tile line for it,
  // state and current_humidity, with its action in the state's place, as its dialog writes it (firmware 0.42.0+).
  else if (d == "humidifier") value = tile_controls::climate_card_status(t, true);
  else if (d == "person") value = t.state=="home"?tr(txt::ha_person_home):t.state=="not_home"?tr(txt::ha_person_not_home):t.state;
  else if (d == "sun") value = !t.extra().sunrise.empty() && !t.extra().sunset.empty() ? screen_text::clock_text(t.extra().sunrise,screen_settings::current.clock_24h!=0,true)+" - "+screen_text::clock_text(t.extra().sunset,screen_settings::current.clock_24h!=0,true) : tr(t.state=="above_horizon"?txt::ha_sun_above_horizon:txt::ha_sun_below_horizon);
  else if (d == "timer") value = timer_text(t);
  else if (d == "script" || d == "scene" || d == "button" || d == "input_button") value = t.state == "on" ? std::string(tr(txt::script_running)) : last_run_text(t.last_run);
  // An automation that runs on a tap says what a script's button says, and Off while it is switched off: its actions
  // still run on a tap then, but nothing starts them on their own (firmware 0.7.0+).
  // A remote that runs an activity names it, as the Harmony hub does (firmware 0.22.0+); otherwise On or Off.
  else if (d == "remote" && t.state == "on" && !t.extra().activity.empty()) value = t.extra().activity;
  else if (t.runs()) value = t.running ? std::string(tr(txt::script_running)) : t.state == "off" ? std::string(tr(txt::ha_off)) : last_run_text(t.last_run);
  else if (d == "camera") value = tr(t.state == "streaming" ? txt::camera_live : t.state == "recording" ? txt::camera_recording : txt::camera_tap_to_view);
  else if (d == "image") value = tr(t.last_run ? txt::camera_tap_to_view : txt::camera_no_image_yet);
  else if (d == "binary_sensor" && (value == "on" || value == "off")) value = tile_controls::binary_state_text(t.device_class, value == "on");
  else if (d == "alarm_control_panel") value = alarm_status(t, false);
  else if (d == "lock") value = lock_status(t, false);
  else if (value == "on") value = tr(txt::ha_on);
  else if (value == "off") value = tr(txt::ha_off);
  else if (value == "cleaning") value = tr(txt::ha_vacuum_cleaning);
  else if (value == "docked") value = tr(txt::ha_vacuum_docked);
  // Home Assistant's word where the screen has none of its own (firmware 0.2.58+): a cover says Open, a washer Rinsing.
  // A favourite says what it plays and where (firmware 0.24.0+), never the player's state.
  else if (t.favorite()) value = favorite_line(t);
  else if (!t.extra().state_word.empty()) value = t.extra().state_word;
  // A player's state in the screen's own words where Home Assistant sent none (firmware 0.2.64+).
  else if (d == "media_player") value = tile_controls::media_state_text(t.state);
  // A measurement in the screen's number format ("21,5 °C" in Dutch), as Home Assistant writes a state with a unit; a
  // number without one (a code, a year) stays as it is, as there.
  else if (!t.unit.empty() && !watch) value = screen_text::with_unit(screen_text::localize(value), t.unit);
  else if (!t.unit.empty() || d == "number" || d == "input_number" || d == "counter") value = screen_text::localize(value);
  bool pending=t.loading(esphome::millis());
  if(d=="weather" && std::isfinite(t.current)) {value=screen_text::decimal(t.current,1);if(!watch)value=screen_text::with_unit(value,t.unit);}
  // What a narrow tile falls back to once its room is known (fit_value): another wording of the whole line, and the
  // end that must stay readable whatever happens to the words in front of it.
  std::string value_short,value_tail;
  if((d=="script"||d=="scene"||d=="button"||d=="input_button") && t.state!="on")value_short=last_run_text(t.last_run,true);
  if(t.runs() && !t.running && t.state=="on")value_short=last_run_text(t.last_run,true);
  // A lock-only tile's word where the whole of it does not fit.
  if(d=="lock"&&lock_noting(t))value_short=tr(txt::lock_lock_only_short);
  // A vacuum's status ends on its battery; the unavailable and refused words and a line chosen by hand do not (#293).
  if(fresh() && t.available() && !refused){value_tail=tile_controls::vacuum_tail(t);value+=value_tail;}
  // A humidifier's humidity stays readable when its action word does not fit ("Humidif… · 38%").
  if(d=="humidifier" && fresh() && t.available() && std::isfinite(t.current) && !set_by_hand)value_tail=" · "+tile_controls::humidity_text(t.current);
  // Direct controls: only a wide card in the standard layout has room for the panel.
  // A small slider on a double-width card is that panel's slider: it stands beside the name, where every other
  // control of a wide card stands and where the editor's mockup draws it. A single card keeps the strip under
  // its head (mini below), and so does a wide card too narrow for a panel.
  const bool taller=t.row_span()>1 && !w.full;
  const bool inline_panel=(w.wide||taller) && !w.full && t.inline_control=="slider" && !tile_controls::inline_kind(d).empty();
  bool with_panel=(w.wide||taller||preset_cell(w,t)) && !t.builtin() && !watch && fresh() && t.available() &&
                  (inline_panel || (!t.controls.empty() && t.inline_control!="slider"));
  // A panel needs its own width plus the icon and some name; a narrow wide card stays a plain card. What it
  // needs is what it takes: the cells its controls fill (layout_panel), or the toggle and the run key their own
  // width.
  if(with_panel && !w.full && !taller && w.wide){
    const bool lt=ui::large();
    const PanelMetrics pm=panel_metrics(lt);
    const std::string kind=tile_controls::panel_kind(t);
    const int panel_need=kind=="toggle"?pm.toggle_w:kind=="run"?pm.key_w*3/2:rest_content_width(w);
    if(content_width(w)<panel_need+pm.text_gap+ui::px(lt?54:36)+ui::px(60))with_panel=false;
  }
  // A wide card with a panel says what its control is doing, unless the second line was set by hand.
  if(with_panel && !set_by_hand){std::string status=tile_controls::status_text(t);if(!status.empty()){value=status;value_short.clear();value_tail.clear();}}
  // A wish Home Assistant takes long to square says so where the state stands (docs/OPTIMISTIC.md).
  if(!t.builtin() && wish_slow(t.entity,esphome::millis())){value=tr(txt::tile_updating);value_short.clear();value_tail.clear();}
  label(w.value, value);
  // Only a thermostat with controls takes a tap on its circle (climate_circle_event); every other card's circle is
  // part of the card and the card's own tap.
  if((d=="climate"||d=="humidifier")&&with_panel)lv_obj_add_flag(w.circle,LV_OBJ_FLAG_CLICKABLE);else lv_obj_remove_flag(w.circle,LV_OBJ_FLAG_CLICKABLE);
  bool mini=t.inline_control=="slider" && !watch && t.available() && !with_panel;
  // The card's size class is the look's, never the cell's momentary height: a class that flips when the rows
  // grow (page buttons off) would reuse a clock's numeral labels as tick lines.
  bool large_tile=ui::large();
  lap(swipe_profile::TEXT);
  // Cards that replace the name/status layout entirely.
  bool bedside=t.is_bedside() && w.full;
  bool clock=t.is_clock(), forecast=d=="weather" && t.display=="forecast" && w.wide && t.extra().forecast.size()>0 && fresh() && t.available();
  bool sunpath=d=="sun" && t.display=="sunpath" && w.wide && !t.extra().sunrise.empty() && !t.extra().sunset.empty() && fresh() && t.available();
  bool graph=d=="sensor" && t.display=="graph" && t.has_history && !clock;
  // The energy card (firmware 0.47.0+) draws its own diagram, on any size it takes.
  bool energy=t.is_energy();
  // The calendar card (firmware 0.56.0+) draws its own head and what its room allows, on any size (calendar_card.h).
  bool calendar=d=="calendar" && !w.key;
  // A sensor's meter (firmware 0.56.0+): a ring, a tape or a bar of cells, drawn on any size (meter_card.h). A key of a
  // bedside clock stays a key.
  bool meter=t.is_meter() && !w.key;
  // A plugin's tile (docs/PLUGINS.md) draws itself too, when this screen has its plugin; else it is a plain card.
  bool plugin=t.is_plugin() && plugin_host::known(t);
#ifdef SD_MOD_VACUUM_CARD
  // A robot's larger tile (docs/VACUUM.md, "A larger tile"): a map, rooms or routines with its keys, on a tall card.
  bool vacuum=d=="vacuum" && !w.key && vacuum_face::shows(t);
#else
  constexpr bool vacuum=false;
#endif
  // The template tile (module text_card, firmware 0.58.0+) draws the rows Home Assistant rendered, on any size.
#ifdef SD_MOD_TEXT_CARD
  bool text=t.is_text();
#else
  constexpr bool text=false;
#endif
  // The to-do card (module todo, firmware 0.61.0+) draws its list on any size; without the module a to-do list is a
  // tile like any other, with the number of open items as its state.
#ifdef SD_MOD_TODO
  bool todo_list=d=="todo" && !w.key;
#else
  constexpr bool todo_list=false;
#endif
  bool custom=clock||forecast||sunpath||bedside||energy||plugin||calendar||meter||vacuum||text||todo_list;
  if(!large_tile)pad_vertical(w.tile,watch||custom||graph?2:4);
  // A big value that stepped up to the setpoint's digits (the watch block below) keeps them until that block
  // decides again, so a card is not restyled twice a render. Only a card that goes through that block: a full card
  // (render_full) never decides again, and kept the digits of what its cell showed before, 30 px too tall, its value
  // under the card (the layout audit on the 3.5-inch, 2026-11-16; a redraw between two layouts used to hide it).
  const bool full_card=w.full && !bedside;
  if(!(watch && !full_card && setpoint_font && lv_obj_get_style_text_font(w.value,LV_PART_MAIN)==setpoint_font))
    set_font(w.value,watch && watch_value_font ? watch_value_font : w.value_font);
  // Both text boxes are one line high; the sizes come from the styles, not from a layout pass.
  int title_height=lv_font_get_line_height(lv_obj_get_style_text_font(w.title,LV_PART_MAIN));
  int value_height=lv_font_get_line_height(lv_obj_get_style_text_font(w.value,LV_PART_MAIN));
  lv_obj_set_height(w.value,value_height);
  int content_w=content_width(w),content_h=content_height(w);
  lap(swipe_profile::LAYOUT);
  w.busy_drawn = pending && !t.builtin();
  set_busy(w,w.busy_drawn,large_tile);
  lap(swipe_profile::BUSY);
  for(auto *o:{w.title,w.value,w.circle,w.unit})set_hidden(o,custom);  // a big-value card on a short cell hides its circle again below
  if(!w.key)set_hidden(w.icon,plugin);  // a key that showed a value hid its icon; a plugin tile draws its own
  if(custom && w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
  if(w.key){
    // A key of a bedside clock: the card is the key, round, with the tile's icon in the middle, or its value where
    // the value is what it is for (a temperature). Its name stands under it, drawn by its clock (render_bedside).
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);hide_extra(w);
    for(auto *o:{w.title,w.unit})set_hidden(o,true);
    const int d=std::max(1,std::min(content_w,content_h));
    lv_obj_set_size(w.circle,d,d);lv_obj_set_pos(w.circle,(content_w-d)/2,(content_h-d)/2);set_hidden(w.circle,false);
    std::string shown;
    if(fresh() && t.available() && key_shows_value(t))shown=key_value(t);
    set_hidden(w.icon,!shown.empty());set_hidden(w.value,shown.empty());
    if(shown.empty()){if(lv_obj_get_style_text_font(w.icon,LV_PART_MAIN)!=w.icon_font)set_font(w.icon,w.icon_font);center_icon(w.icon);}
    else{
      const lv_font_t *face=control_font && text_width(shown,control_font)<=d-ui::px(8)?control_font:w.value_font;
      set_font(w.value,face);set_text_align(w.value,LV_TEXT_ALIGN_CENTER);label(w.value,shown);
      const int vh=lv_font_get_line_height(face);lv_obj_set_size(w.value,d,vh);lv_obj_set_pos(w.value,(content_w-d)/2,(content_h-vh)/2);
    }
    lap(swipe_profile::GEOMETRY);
  }else if(energy){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    energy_view::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
  }else if(calendar){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    calendar_view::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
#ifdef SD_MOD_TEXT_CARD
  }else if(text){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    text_card_view::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
#endif
#ifdef SD_MOD_TODO
  }else if(todo_list){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    todo_view::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
#endif
  }else if(meter){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    meter_view::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
#ifdef SD_MOD_VACUUM_CARD
  }else if(vacuum){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    vacuum_face::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
#endif
  }else if(plugin){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
    if(w.picture)lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);
    lap(swipe_profile::GEOMETRY);
    plugin_host::render(w,t,content_w,content_h);
    lap(swipe_profile::CUSTOM);
  }else if((t.live()||t.is_map())&&render_camera_card(w,t,content_w,content_h)){
    lap(swipe_profile::GEOMETRY);
  }else if(t.favorite()&&render_favorite_card(w,t,content_w,content_h)){
    label(w.value,value);
    lap(swipe_profile::GEOMETRY);
  }else if((taller||(w.full&&(tile_controls::cover_tilt_selected(t)||tile_controls::climate_modes_selected(t)))||
            (!w.full&&t.row_span()==1&&t.inline_control!="slider"&&(cover_row_card(t)||preset_cell(w,t))))&&!custom&&!watch&&!graph&&
     render_tall(w,t,with_panel,content_w,content_h)){
    lap(swipe_profile::GEOMETRY);
  }else if(w.full && !bedside){
    lap(swipe_profile::GEOMETRY);
    render_full(w,t,custom,clock,sunpath,graph,mini,with_panel,large_tile,value,unit,content_w,content_h);
    lap(swipe_profile::CUSTOM);
  }else if(!custom && !watch && !mini && !graph && !with_panel && !w.wide && tile_height(w)>=2*ui::cell_height()){
    // A cell at least twice the look's height shows its icon above its name and state, like a full card does.
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);hide_extra(w);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
    set_font(w.title,w.title_font);title_height=lv_font_get_line_height(w.title_font);lv_obj_set_height(w.title,title_height);
    const int circle=large_tile?std::min(content_w,content_h*45/100):std::min(content_w,content_h*40/100);
    const int gap=ui::px(large_tile?10:6),line_gap=ui::px(large_tile?2:1);
    const int block=circle+gap+title_height+line_gap+value_height;
    const int top=std::max(0,(content_h-block)/2);
    lv_obj_set_size(w.circle,circle,circle);lv_obj_set_pos(w.circle,(content_w-circle)/2,top);
    if(lv_obj_get_style_text_font(w.icon,LV_PART_MAIN)!=w.icon_font){set_font(w.icon,w.icon_font);}
    center_icon(w.icon);tile_picture_place(w,t,circle,(content_w-circle)/2,top);
    set_text_align(w.title,LV_TEXT_ALIGN_CENTER);set_text_align(w.value,LV_TEXT_ALIGN_CENTER);
    lv_obj_set_pos(w.title,0,top+circle+gap);lv_obj_set_width(w.title,content_w);
    lv_obj_set_pos(w.value,0,top+circle+gap+title_height+line_gap);lv_obj_set_width(w.value,content_w);
    fit_value(w.value,value,value_short,value_tail,content_w);
    lap(swipe_profile::CUSTOM);
  }else if(custom){
    lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);hide_panel(w);
    // The hidden name back to the card's own font and alignment, so nothing of the card the slot showed before (a
    // centred tall card) stays on it for the next tile to inherit (firmware 0.3.2).
    set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
    lap(swipe_profile::GEOMETRY);
    if(bedside)render_bedside(w,t,content_w,content_h);
    else if(clock)render_clock(w,t,large_tile,content_w,content_h);
    else if(sunpath)render_sunpath(w,t,large_tile,content_w,content_h);
    else render_forecast(w,t,large_tile,content_w,content_h);
    lap(swipe_profile::CUSTOM);
  }else{
  // A single-width graph takes the slider strip; a wide graph takes the right half.
  bool graph_strip=graph && !w.wide, graph_side=graph && w.wide;
  int chart_w=graph_side?content_w*55/100:0;
  lap(swipe_profile::GEOMETRY);
  int panel_w=with_panel && !graph?layout_panel(w,t,large_tile,content_w,content_h):0;
  if(!panel_w)hide_panel(w);
  lap(swipe_profile::PANEL);
  // A slot that just held a full card gets its own name font, one-line box and left-aligned text back. A name with
  // room gets bigger letters (name_font).
  const lv_font_t *title_face=name_font(w,content_w-chart_w-panel_w);
  set_font(w.title,title_face);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
  title_height=lv_font_get_line_height(title_face);lv_obj_set_height(w.title,title_height);
  int line_gap=head_gap(large_tile),text_height=title_height+line_gap+value_height;
  int slider_height=ui::px(large_tile?28:8);
  // The circle follows the board's icon size (TILE_ICON_SIZE), so a 73 pt icon on a 294 dpi panel gets its disc;
  // the watch and mini circles keep their ratios to it.
  const int base_circle=w.base_circle>0?w.base_circle:(ui::px(large_tile?54:36));
  int circle_size=watch?(large_tile?base_circle*26/54:base_circle/2):(mini||graph_strip)?base_circle*2/3:base_circle;
  lv_obj_set_size(w.circle,circle_size,circle_size);
  // A strip that leaves the two lines no room takes what is left instead: a board with more rows than the look
  // was drawn for has short cells, and the name and the value were drawn over the slider (or the graph). When even
  // that leaves the strip below its least, the head keeps the room its circle and one line need, and the name and
  // the value share that line (one_line below).
  // The strip and the head were drawn for the look's cell (ui::cell_height). A cell taller than that has surplus,
  // and a graph, which is the card's picture and not a control, takes all of it: on a 10.1 inch (162 px where the
  // look wants 108) the name and the value keep the look's place at the top and the graph runs under them to the
  // bottom of the card, instead of standing thin under a head centred in the air. A slider keeps its thumb-thick
  // strip and its head stands in the room that is left. A cell of the look's height, or a shorter one, is laid
  // out exactly as before.
  if(mini||graph_strip){
    const int least=ui::px(large_tile?14:6),gap=ui::px(large_tile?6:3);
    const int look_h=std::min<int>(content_h,ui::cell_height()-lv_obj_get_style_space_top(w.tile,LV_PART_MAIN)-lv_obj_get_style_space_bottom(w.tile,LV_PART_MAIN));
    const int head_need=look_h-text_height-gap>=least?text_height:std::max(title_height,circle_size);
    slider_height=std::max(least,std::min(slider_height,look_h-head_need-gap));
    if(graph_strip)slider_height+=content_h-look_h;
  }
  int header_height=(mini||graph_strip)?content_h-slider_height-(ui::px(large_tile?6:3)):content_h;
  int text_y=std::max(0,(header_height-text_height)/2);
  // Two lines stay while the value's letters keep two pixels of air above the strip (its line box may hang into
  // the gap, as on a CYD); when the strip would touch them, the name and the value share one line, the value at
  // the right as in a row of Home Assistant (three rows on a 4.3 inch: 39 px above the strip for 58 px of lines).
  const lv_font_t *value_face=lv_obj_get_style_text_font(w.value,LV_PART_MAIN);
  // A strip card places its own head, so the one rule (head_row) does not reach it: it centres a lone name here,
  // by the same "there is only one line" branch it already had for a head squeezed by its strip.
  const bool one_line=(mini||graph_strip) && (value.empty() ||
      text_y+title_height+line_gap+value_height-value_face->base_line+(ui::px(2))>header_height+(ui::px(large_tile?6:3)));
  if(one_line){text_height=title_height;text_y=std::max(0,(header_height-title_height)/2);}
  const lv_font_t *icon_font=watch && watch_icon_font ? watch_icon_font : (mini||graph_strip) && mini_icon_font ? mini_icon_font : w.icon_font;
  if(lv_obj_get_style_text_font(w.icon,LV_PART_MAIN)!=icon_font)set_font(w.icon,icon_font);center_icon(w.icon);
  // The plain head (a single or double-width card, with or without a panel) stands by the one rule, head_row,
  // centred on the room it got on this grid. The watch and the strip cards place their smaller circle themselves.
  const bool plain=!watch && !(mini||graph_strip);
  const HeadRow head=plain?head_row(w,large_tile,circle_size,header_height,title_height,value.empty()?0:value_height):HeadRow{};
  if(plain){circle_size=head.circle;lv_obj_set_size(w.circle,circle_size,circle_size);}
  int text_x=watch?0:plain?head.text_x:circle_size+(ui::px(large_tile?8:6));
  lv_obj_set_pos(w.title,text_x,watch?0:plain?head.title_y:text_y);
  lv_obj_set_pos(w.value,text_x,watch?(ui::px(large_tile?42:19)):plain?head.value_y:text_y+title_height+line_gap);
  const int circle_y=plain?head.circle_y:watch?0:std::max<int>(2-lv_obj_get_style_space_top(w.tile,LV_PART_MAIN),(header_height-circle_size)/2);
  lv_obj_set_pos(w.circle,0,circle_y);
  tile_picture_place(w,t,circle_size,0,circle_y);
  // Use the requested coordinates: LVGL getters still return the previous
  // layout until its next pass when a slot changes from watch/slider to normal.
  int text_room=content_w-chart_w-(graph_side?(ui::px(large_tile?10:6)):0)-panel_w;
  // A navigation tile ends in a chevron, as a row in Home Assistant's settings does.
  const lv_font_t *chevron_font=mini_icon_font?mini_icon_font:w.icon_font;
  int chevron_w=t.is_page() && !watch?lv_font_get_line_height(chevron_font):0;
  if(chevron_w)text_room-=chevron_w+(ui::px(large_tile?8:4));
  lv_obj_set_width(w.title,std::max(1,text_room-text_x));
  int value_room=std::max(1,text_room-text_x);
  lv_obj_set_width(w.value,value_room);
  fit_value(w.value,value,value_short,value_tail,value_room);
  if(one_line){
    lv_point_t need;lv_text_get_size(&need,lv_label_get_text(w.value),value_face,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
    const int line_w=std::max(1,text_room-text_x),value_w=std::max(1,std::min((int)need.x+2,line_w*55/100));
    set_text_align(w.value,LV_TEXT_ALIGN_RIGHT);
    lv_obj_set_pos(w.value,text_room-value_w,text_y+title_height-value_height);lv_obj_set_width(w.value,value_w);
    lv_obj_set_width(w.title,std::max(1,line_w-value_w-(ui::px(large_tile?6:3))));
    fit_value(w.value,value,value_short,value_tail,value_w);
  }
  if(watch){
    int gap=ui::px(large_tile?6:2),header=std::max(circle_size,title_height);
    set_font(w.unit,w.value_font);set_text_align(w.unit,LV_TEXT_ALIGN_LEFT);
    label(w.unit,unit);
    lv_point_t size;lv_text_get_size(&size,unit.c_str(),w.value_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
    int unit_width=unit.empty()?0:std::min((int)size.x,text_room-20);
    const int unit_gap=unit_width?unit_width+(ui::px(large_tile?6:3)):0;
    int number_x=0,number_width=text_room-unit_gap,unit_x=text_room-unit_width;
    // A big value grows into a cell taller than the look was drawn for (a 10.1 inch draws 162 px where the look
    // wants 108): the number takes the setpoint's digits, the largest face a board carries, when they fit under
    // the icon and the name and beside the unit, and the value has no letter that face lacks (it carries digits,
    // a sign, a point, a comma and a degree; a word keeps the value's own face). A 4-inch Guition has no such
    // room and keeps its face.
    const lv_font_t *face=watch_value_font?watch_value_font:w.value_font;
    if(setpoint_font && header+gap+lv_font_get_line_height(setpoint_font)<=content_h && text_width(value,setpoint_font)<=number_width && face_covers(setpoint_font,value))face=setpoint_font;
    if(lv_obj_get_style_text_font(w.value,LV_PART_MAIN)!=face){set_font(w.value,face);label(w.value,value);fit_value(w.value,value,value_short,value_tail,value_room);}
    value_height=lv_font_get_line_height(face);lv_obj_set_height(w.value,value_height);
    // The icon and the name above the number while the three fit the cell, the number in the largest watch face that
    // lets them (firmware 0.35.0): a lower cell keeps its icon with a smaller number before it gives the icon up.
    // Only a cell too short even for the smaller face (three rows on a 4.3 inch before, 65 px) stands the number
    // in the middle of the card with the name small in the top-left corner, and the icon goes.
    bool stacked=header+gap+value_height<=content_h;
    if(!stacked && watch_font && watch_font!=face && header+gap+lv_font_get_line_height(watch_font)<=content_h &&
       text_width(value,watch_font)<=number_width && face_covers(watch_font,value)){
      face=watch_font;set_font(w.value,face);label(w.value,value);fit_value(w.value,value,value_short,value_tail,value_room);
      value_height=lv_font_get_line_height(face);lv_obj_set_height(w.value,value_height);
      stacked=true;
    }
    int group_y=stacked?std::max(0,(content_h-header-gap-value_height)/2):0;
    int value_y=stacked?group_y+header+gap:0;
    set_hidden(w.circle,!stacked);
    if(stacked){
      lv_obj_set_pos(w.circle,0,group_y+(header-circle_size)/2);
      lv_obj_set_pos(w.title,circle_size+(ui::px(large_tile?6:4)),group_y+(header-title_height)/2);
      lv_obj_set_width(w.title,text_room-circle_size-(ui::px(large_tile?6:4)));
    }else{
      set_font(w.title,w.value_font);
      const int name_h=lv_font_get_line_height(w.value_font);
      lv_obj_set_pos(w.title,0,0);lv_obj_set_size(w.title,text_room,name_h);
      // The number under the name, never in its box (firmware 0.35.0): the largest of the board's faces that fits the
      // rest of the card, so a lower cell (a 4-inch with four rows, eleven millimetres) gets a smaller number with air
      // above it instead of the big one pressed against the name. The line may end in the padding, never past the
      // border. Before, the big face stayed and its top space ran into the name's line.
      const int below=name_h+ui::px(2),floor_y=content_h+lv_obj_get_style_space_bottom(w.tile,LV_PART_MAIN)-2;
      const lv_font_t *ladder[]={face,watch_font,w.value_font};
      const lv_font_t *fitted=w.value_font;
      for(const lv_font_t *f:ladder){
        if(!f || (f!=w.value_font && !face_covers(f,value)))continue;
        if(below+lv_font_get_line_height(f)<=floor_y && text_width(value,f)<=number_width){fitted=f;break;}
      }
      if(fitted!=face){face=fitted;set_font(w.value,face);label(w.value,value);}
      value_height=lv_font_get_line_height(face);lv_obj_set_height(w.value,value_height);
      value_y=std::max(below,(content_h-value_height)/2);
      value_y=std::min<int>(value_y,floor_y-value_height);
      fit_value(w.value,value,value_short,value_tail,number_width);
      lv_point_t number;lv_text_get_size(&number,lv_label_get_text(w.value),lv_obj_get_style_text_font(w.value,LV_PART_MAIN),0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
      number_width=std::max(1,std::min(number_width,(int)number.x+2));
      number_x=std::max(0,(text_room-number_width-unit_gap)/2);unit_x=number_x+number_width+(unit_gap-unit_width);
    }
    lv_obj_set_pos(w.value,number_x,value_y);lv_obj_set_width(w.value,number_width);
    lv_obj_set_pos(w.unit,unit_x,value_y+value_height-lv_font_get_line_height(w.value_font));
    lv_obj_set_size(w.unit,unit_width,lv_font_get_line_height(w.value_font));
    set_hidden(w.unit,!unit_width);
  }else if(chevron_w){
    set_font(w.unit,chevron_font);set_text_align(w.unit,LV_TEXT_ALIGN_RIGHT);label(w.unit,"\U000F0142");
    lv_obj_set_pos(w.unit,content_w-chevron_w,std::max(0,(header_height-chevron_w)/2));lv_obj_set_size(w.unit,chevron_w,chevron_w);
    lv_obj_remove_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  }else lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  lv_obj_set_size(w.slider,content_w,slider_height);lv_obj_set_ext_click_area(w.slider,slider_zone(w,slider_height));
  slider_handle(w.slider,content_w,slider_height);
  if(mini){lv_obj_remove_flag(w.slider,LV_OBJ_FLAG_HIDDEN);travel_look(w.slider,t,false,true);if(!lv_obj_has_state(w.slider,LV_STATE_PRESSED) && lv_slider_get_value(w.slider)!=slider_value(t))lv_slider_set_value(w.slider,slider_value(t),LV_ANIM_OFF);}
  else lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
  lap(swipe_profile::GEOMETRY);
  if(graph_strip)render_graph(w,t,large_tile,0,content_h-slider_height,content_w,slider_height);
  else if(graph_side)render_graph(w,t,large_tile,content_w-chart_w,0,chart_w,content_h);
  else hide_extra(w);
  lap(swipe_profile::CUSTOM);
  }
  // Home Assistant's rule (Tile::active): what it calls inactive is grey, such as an airco that is off, a closed
  // blind, a docked robot or a player in standby (firmware 0.2.71+). A built-in card has no state and keeps its colour.
  bool on = t.builtin() || (fresh() && t.active());
  // A closed blind's slider keeps the blind's colour while its card is grey, as in Home Assistant (Tile::slider_active).
  bool slider_on = fresh() && t.slider_active();
  bool available=fresh() && t.available();
  // A locked lock is inactive in Home Assistant and still green, not grey (--state-lock-locked-color); a lock that
  // waits for the second tap is orange.
  const bool lock_tile=d=="lock";
  if(lock_tile)on=available;
  int palette_state=(available?2:0)|(on?1:0)|(slider_on?4:0)|((card_art(t)&&w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN))?8:0)|
                    (lock_tile&&lock_asking(t,false)?16:0)|(lock_tile?(int)(lock_panel::color(t.state)&0xFF)<<8:0);
  // An alarm panel's circle beats while it counts down or goes off, and springs once when it arms or disarms.
  if (d == "alarm_control_panel" || d == "lock" || w.alarm_look || w.alarm_mark) alarm_tile_look(slot, &t);
  // A template tile Home Assistant rendered empty hides its card as "Background: none" does (module text_card).
#ifdef SD_MOD_TEXT_CARD
  const bool bare=t.transparent||(t.is_text()&&text_card_view::empty(t));
#else
  const bool bare=t.transparent;
#endif
  // A plugin tile may give its card a colour of its own (plugin API 0.26, ui::set_card_color): it goes over the tile's.
  const theme::Face face=card_face(w);
#ifdef SD_MOD_SECTIONS
  // The card's look and what lies behind it are part of what it was painted for: a card that moves into or out of a
  // section whose tiles follow its contrast is painted again (sections::place traded its shared styles already).
  const uint64_t paint=uint64_t(face.key())|(bare?1ull<<27:0)|(w.look_other?1ull<<25:0)|(w.ground_other?1ull<<26:0)|(uint64_t(w.ground_role)<<32);
#else
  const uint32_t paint=face.key()|(bare?1u<<25:0);  // a board without sections: every card in the screen's look on the page
#endif
  if (w.cached_active == palette_state && w.cached_paint == paint && !w.panel_dirty) { style_tall(w,t);ring_favorite(w,t);lap(swipe_profile::GEOMETRY); return; }
  w.cached_active = palette_state;w.cached_paint=paint;w.panel_dirty=false;
  // Home Assistant's colour for the state (tile_controls::accent), and a lamp's own colour while it is on.
  uint32_t accent=lock_tile?lock_accent(t):tile_controls::accent(t);
  // A lamp's own colour goes through Home Assistant's contrast rule before it reaches the glass
  // (tile_controls::lamp_color, shared with the lamp page of a group): a white bulb keeps the amber of a lamp that is on.
  if(d=="light" && on && t.has_hs_color)
    accent=tile_controls::lamp_color(t.hue,t.saturation);
  uint32_t state_color=on?accent:theme::STATE_OFF;
  auto color=lv_color_hex(theme::state(state_color));
  auto circle_color=lv_color_hex(available?theme::tint(state_color,38):theme::hex(theme::TRACK));
  // Very pale bulbs still need a visible icon: a touch darker on a light card, a touch lighter on a dark one.
  auto icon_color=lv_color_hex(available?theme::icon(state_color):theme::hex(theme::OFF));
  // Off: a grey track without fill or handle, as in Home Assistant.
  const uint32_t fill=slider_on?accent:theme::STATE_OFF;
  auto fill_color=lv_color_hex(theme::state(fill));
  set_color(w.slider,LV_STYLE_BG_COLOR,fill_color,LV_PART_INDICATOR);
  set_color(w.slider,LV_STYLE_BG_COLOR,lv_color_hex(theme::tint(fill,51)),LV_PART_MAIN);
  slider_bar(w.slider,slider_bar_shown(t,slider_on));
  // Every card, the one over the whole page too, is white or its own pastel (firmware 0.2.77+): the state shows in the
  // icon and the controls, as on the other sizes. Firmware 0.2.62 to 0.2.76 tinted a full-page card in its state colour
  // while it was on.
  press_ground(w.tile,letterboxed(w)?theme::color(theme::CAMERA_PAGE):lv_color_hex(theme::surface(face)));
  set_number(w.tile,LV_STYLE_BORDER_WIDTH,1);
  // "Background: none" hides only the card; geometry and padding stay identical, and the press still shows because
  // it lives on the PRESSED state: a shade of what the finger sees, what is behind the card there (the page or its
  // section), the card everywhere else.
  set_color(w.tile,LV_STYLE_BG_COLOR,lv_color_hex(bare ? theme::pressed(card_ground(w)) : theme::pressed(face)),LV_STATE_PRESSED);
  set_number(w.tile,LV_STYLE_BG_OPA,bare&&!letterboxed(w) ? LV_OPA_TRANSP : LV_OPA_COVER);
  set_number(w.tile,LV_STYLE_BORDER_OPA,bare ? LV_OPA_TRANSP : LV_OPA_COVER);
  // The hairline sets the card off from what is behind it: in a contrast section that is the other look, so a card of
  // the page's own colour takes the other look's line (a light line drew a white frame round a cover on a dark panel).
  uint32_t line;
  {
#ifdef SD_MOD_SECTIONS
    theme::LookScope line_look(w.look_other || (face.kind == theme::Face::CARD && w.ground_role == theme::SECTION_CONTRAST));
#endif
    line = theme::outline(face);
  }
  set_color(w.tile,LV_STYLE_BORDER_COLOR,lv_color_hex(line));
  set_color(w.circle,LV_STYLE_BG_COLOR,circle_color);
  set_color(w.icon,LV_STYLE_TEXT_COLOR,icon_color);
  // A key is its circle: the card takes the circle's colour and its press, with no border (firmware 0.8.0+).
  if(w.key){
    set_color(w.tile,LV_STYLE_BG_COLOR,circle_color);
    set_color(w.tile,LV_STYLE_BG_COLOR,lv_color_hex(theme::pressed(available?theme::tint(state_color,38):theme::hex(theme::TRACK))),LV_STATE_PRESSED);
    set_number(w.tile,LV_STYLE_BG_OPA,LV_OPA_COVER);set_number(w.tile,LV_STYLE_BORDER_OPA,LV_OPA_TRANSP);
  }
  auto title_color=theme::color(theme::INK);
  auto value_color=theme::color(w.key ? theme::INK : face.kind!=theme::Face::CARD ? theme::SLATE : theme::MUTED);
  set_color(w.unit,LV_STYLE_TEXT_COLOR,theme::color(t.is_page()?theme::CHEVRON:theme::SLATE));
  set_color(w.title,LV_STYLE_TEXT_COLOR,title_color);
  set_color(w.value,LV_STYLE_TEXT_COLOR,value_color);
  // The controls take the state's colour even while the card is grey: a closed blind's position slider stays coloured
  // (Tile::slider_active), while the slider of something off turns grey and the Off mode key has a grey of its own.
  style_panel(w,t,lv_color_hex(theme::state(accent)),title_color);
  style_tall(w,t);
  ring_favorite(w,t);
  // Custom parts follow the card palette: text like the title, lines/dots in the accent.
  // The sun path sets its own colours on every render, the sunlit area under its arc too: taking the
  // accent here made that area orange after a palette change and yellow again after the next minute.
  if(w.extra_mode!="sunpath")w.fill_color=color;
  // The media tile (firmware 0.2.64+) paints its own parts on every render: keys, the bar and the cover's placeholder
  // in the media colours, not the card's.
  if(w.extra_mode=="bedside"){}  // render_bedside paints its own parts
  else if(w.extra_mode=="calm"||w.extra_mode=="flip")paint_face(w,title_color,value_color,icon_color);
  else for(unsigned i=0;i<w.parts.size() && w.extra_mode!="media" && w.extra_mode!="tall" && w.extra_mode!="cover_tilt" && w.extra_mode!="forecast" && w.extra_mode!="forecast_rows" && w.extra_mode!="week" && w.extra_mode!="favorite" && w.extra_mode!="energy" && w.extra_mode!="calendar_card" && w.extra_mode!="meter_card";++i){
    auto *p=w.parts[i];if(!p)continue;
    bool muted=w.extra_mode=="sunpath" ? i>=1 : w.extra_mode=="calendar" ? i==15||i==17 : w.extra_mode=="digital" ? i==16||i==17 : i==16;
    if(lv_obj_check_type(p,&lv_label_class))set_color(p,LV_STYLE_TEXT_COLOR,muted?value_color:title_color);
    else if(w.extra_mode=="sunpath")continue;
    else if(lv_obj_check_type(p,&lv_line_class))set_color(p,LV_STYLE_LINE_COLOR,w.extra_mode=="graph"?color:i==18?lv_color_hex(theme::foreground(theme::ha::ALARM)):i<12?value_color:i==13?icon_color:title_color);
    else set_color(p,LV_STYLE_BG_COLOR,i==14?icon_color:value_color);
  }
  lap(swipe_profile::PALETTE);
}
// What the next render() draws besides the name and the top bar: the cards of the tiles a state
// message or a tick named, or every card. A refresh that names nothing (the board's own triggers,
// such as the minute tick and time sync) draws every card.
inline TileSet dirty_tiles;
inline bool dirty_all=false, dirty_header=false;
// A display setting changed (packages/core.yaml says so before its refresh): every card on the glass is drawn, as for a
// refresh that names nothing, and on a kept page the cards that show the time (firmware 0.3.2+). The minute turning is
// mark_minute: only the cards that show the time.
inline bool dirty_time=false;
// A card whose text or drawing moves on with the clock: a clock, a timer, the sun's arc, a graph's window, a playing
// track's bar, "5 min ago" under a script or a scene, a second line that names a moment, and a calendar's now and
// minutes left. A forecast changes with its entity, which Home Assistant updates on its own; its today and its hours'
// window follow the clock once an hour (mark_minute).
inline bool shows_time(const Tile &t) {
  const std::string d=t.domain();
  return t.is_clock() || t.is_bedside() || t.display=="graph" || t.extra().subtitle_at || d=="timer" || d=="sun" ||
         (d=="media_player" && media_card::playing(t.state)) ||
         d=="script" || d=="scene" || d=="button" || d=="input_button" || d=="automation" || d=="calendar";
}
inline void mark_time() {
  dirty_time=true;
  for(size_t i=0;i<model.count;++i)if(shows_time(model.tiles[i]))changes.mark_tile(i);
}
// The page whose cells are placed right now, -1 before the first one. It lives here and not beside show_page
// because the top bar reads it: a page with a title of its own says that title (Model::title_of), so render()
// has to know which page it is drawing.
inline int applied_page=-1;
// Why every card is drawn next (mark_all's `why`): the render's log names it, so a page that seems to load again can be
// traced to its cause (a 10.1 inch, 2026-11-15). The first reason since the last render is kept; the reasons and their
// words live in redraw_log.h, log words the translations' lint leaves alone by rule.
inline const char *all_why=nullptr;
inline void mark_all(redraw_log::Why why=redraw_log::Why::unnamed) { dirty_all=true; changes.mark_all(); if(!all_why)all_why=redraw_log::words(why); }
// What last asked for each card to be drawn (redraw_log::TileWhy), for render()'s slow-pass line: a byte a tile.
inline std::array<uint8_t, TILES_MAX> tile_why{};
inline void mark_tile(size_t index, redraw_log::TileWhy why = redraw_log::TileWhy::unnamed) {
  changes.mark_tile(index); if(index<dirty_tiles.size())dirty_tiles.set(index); else dirty_all=true;
  if(index<tile_why.size())tile_why[index]=static_cast<uint8_t>(why);
}
inline void refresh_tile(size_t index, redraw_log::TileWhy why) { mark_tile(index, why); if(refresh)refresh(); }
inline void refresh_header_only() { dirty_header=true; if(refresh)refresh(); }
// The minute turned, or Home Assistant set the clock: the top bar's clock and the cards that show the time, on the glass
// now and on a kept page when it comes back. Not every card: on a 10-inch that redrew the whole glass twice a minute
// (200 ms each), and a sound that played meanwhile stuttered.
inline void mark_minute() {
  dirty_header=true;
  const bool hour=minute_of_day()%60==0;
  for(size_t i=0;i<model.count;++i)
    if(shows_time(model.tiles[i]) || (hour && model.tiles[i].domain()=="weather"))mark_tile(i, redraw_log::TileWhy::minute);
}
inline void refresh_all(redraw_log::Why why) { mark_all(why); if(refresh)refresh(); }
// The starting screen (firmware 0.2.73+): what the screen waits for in the middle of the page with a spinner under it,
// until the first layout arrives. The first render() makes it and the first layout deletes it, spinner and all.
// Above the text stands the Tessera lockup (firmware 0.3.8+): the mosaic mark beside the name, as the website draws it.
inline const lv_font_t *brand_font = nullptr;
inline const void *brand_mark = nullptr;  // the image's lv_image_dsc_t, from the YAML
// The firmware number, small at the foot of the page whatever the screen says (firmware 0.10.0+).
inline const char *firmware_version = nullptr;
inline lv_obj_t *boot_panel = nullptr, *boot_text = nullptr, *boot_spinner = nullptr, *boot_brand = nullptr,
                *boot_version = nullptr;
// The mark and the name side by side in one box, sized to what they hold. Null where the build has neither.
inline lv_obj_t *boot_brand_create(lv_obj_t *parent) {
  if (!brand_font && !brand_mark) return nullptr;
  auto *box = lv_obj_create(parent);
  lv_obj_remove_style_all(box);
  lv_obj_remove_flag(box, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(box, LV_OBJ_FLAG_SCROLLABLE);
  int width = 0, height = 0, mark = 0;
  lv_obj_t *image = nullptr;
#if LV_USE_IMAGE
  if (brand_mark) {
    image = lv_image_create(box);
    lv_image_set_src(image, brand_mark);
    lv_obj_remove_flag(image, LV_OBJ_FLAG_CLICKABLE);
    mark = static_cast<const lv_image_dsc_t *>(brand_mark)->header.w;
    width = mark;
    height = static_cast<const lv_image_dsc_t *>(brand_mark)->header.h;
  }
#endif
  if (brand_font) {
    // The website's wordmark: bold, the letters drawn a little closer together (-0.04 em).
    const int space = -(int) lv_font_get_line_height(brand_font) / 28;
    auto *name = lv_label_create(box);
    lv_obj_add_style(name, theme::style(theme::Paint::ink), 0);
    lv_obj_set_style_text_font(name, brand_font, 0);
    lv_obj_set_style_text_letter_space(name, space, 0);
    lv_label_set_text(name, "tessera");
    lv_point_t size;
    lv_text_get_size(&size, "tessera", brand_font, space, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
    const int gap = mark ? mark / 3 : 0;
    // Centred on the mark, as the website's header lines them up.
    const int line = lv_font_get_line_height(brand_font);
    lv_obj_set_pos(name, width + gap, (std::max(height, line) - line) / 2);
    width += gap + size.x;
    height = std::max(height, line);
  }
  // The mark centred on the name's line too, where that is the taller.
  if (image) lv_obj_set_y(image, (height - (int) static_cast<const lv_image_dsc_t *>(brand_mark)->header.h) / 2);
  lv_obj_set_size(box, width, height);
  return box;
}
// `cover`: over everything on the page, opaque, with the spinner turning ("Preparing pages", firmware 0.3.2+).
// `facts` and `hint` (firmware 0.38.0): small lines under the text, what the screen knows of the step it is on (its
// network, its address, how long it has waited) and, once a step takes long, what usually fixes it.
// `qr` (firmware 0.38.0): what a phone's camera reads under the hint, the hotspot to join on the Wi-Fi problem screen,
// drawn with LVGL's QR code where the board builds it (features/hotspot.yaml, the boards with a hotspot).
inline lv_obj_t *boot_facts = nullptr, *boot_hint = nullptr, *boot_qr = nullptr, *boot_steps = nullptr;
// What a person does next, one line per step, each after a small tile in one of the Tessera mark's colours (firmware
// 0.45.0): what a screen shows while it waits for its first tiles. The lines start under each other and the block stands
// in the middle; a line too long for the glass wraps under its own start. Returns the block, sized.
struct StepsSize { int tile, gap, row_gap, widest, width, height; std::vector<int> heights; };
inline StepsSize steps_measure(const std::vector<std::string> &steps, const lv_font_t *font, int width) {
  StepsSize m{};
  const int line = lv_font_get_line_height(font);
  // The tile as tall as a capital, its corners the mark's (11 of 43), a capital's width from the words.
  m.tile = std::max(6, line * 58 / 100);
  m.gap = std::max(6, line * 3 / 5);
  m.row_gap = std::max(4, line * 9 / 20);
  const int room = std::max(40, width - m.tile - m.gap);
  for (size_t i = 0; i < steps.size(); ++i) {
    lv_point_t size;
    lv_text_get_size(&size, steps[i].c_str(), font, 0, 0, room, LV_TEXT_FLAG_NONE);
    m.widest = std::max(m.widest, (int) size.x);
    m.heights.push_back(size.y);
    m.height += size.y + (i + 1 < steps.size() ? m.row_gap : 0);
  }
  m.width = m.tile + m.gap + m.widest;
  return m;
}
inline lv_obj_t *steps_create(lv_obj_t *parent, const std::vector<std::string> &steps, const lv_font_t *font, int width) {
  static constexpr theme::Role marks[] = {theme::MARK_AMBER, theme::MARK_BLUE, theme::MARK_PURPLE, theme::MARK_GREEN};
  const int line = lv_font_get_line_height(font);
  const auto m = steps_measure(steps, font, width);
  const int tile = m.tile, gap = m.gap, row_gap = m.row_gap, widest = m.widest;
  const auto &heights = m.heights;
  auto *box = lv_obj_create(parent);
  lv_obj_remove_style_all(box);
  lv_obj_remove_flag(box, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(box, LV_OBJ_FLAG_SCROLLABLE);
  int y = 0;
  for (size_t i = 0; i < steps.size(); ++i) {
    auto *mark = lv_obj_create(box);
    lv_obj_remove_style_all(mark);
    lv_obj_set_size(mark, tile, tile);
    lv_obj_set_style_radius(mark, tile * 26 / 100, 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(mark, theme::color(marks[i % 4]), 0);
    // On the middle of the first line.
    lv_obj_set_pos(mark, 0, y + (line - tile) / 2);
    auto *words = lv_label_create(box);
    lv_obj_add_style(words, theme::style(theme::Paint::ink), 0);
    lv_obj_set_style_text_font(words, font, 0);
    lv_label_set_long_mode(words, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(words, widest);
    lv_label_set_text(words, steps[i].c_str());
    lv_obj_set_pos(words, tile + gap, y);
    y += heights[i] + (i + 1 < steps.size() ? row_gap : 0);
  }
  lv_obj_set_size(box, tile + gap + widest, y);
  return box;
}
inline void boot_status(lv_obj_t *page, const char *text, bool waiting = true, bool cover = false,
                        const std::string &facts = std::string(), const std::string &hint = std::string(),
                        const std::string &qr = std::string(), const std::vector<std::string> &steps = {}) {
  const int width = lv_display_get_horizontal_resolution(lv_obj_get_display(page));
  const bool large = ui::large();
  const int ring = ui::px(large ? 48 : 32), gap = ui::px(large ? 24 : 16), text_width = width - 2 * lv_obj_get_style_x(room_label, LV_PART_MAIN);
  const int line_gap = ui::px(large ? 8 : 4);
  const lv_font_t *font = watch_font ? watch_font : lv_obj_get_style_text_font(room_label, LV_PART_MAIN);
  const lv_font_t *note_font = small_font ? small_font : font;
  auto note = [&](theme::Paint paint) {
    auto *label = lv_label_create(boot_panel);
    lv_obj_add_style(label, theme::style(paint), 0);
    lv_obj_set_style_text_font(label, note_font, 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(label, text_width);
    return label;
  };
  if (!boot_panel) {
    boot_panel = lv_obj_create(page);
    lv_obj_remove_style_all(boot_panel);
    lv_obj_remove_flag(boot_panel, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(boot_panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(boot_panel, lv_pct(100), lv_pct(100));
    // The name's place in the drawing order: under the tiles, the cards and an alert.
    lv_obj_move_to_index(boot_panel, lv_obj_get_index(room_label));
    boot_brand = boot_brand_create(boot_panel);
    boot_text = lv_label_create(boot_panel);
    lv_obj_add_style(boot_text, theme::style(theme::Paint::ink), 0);
    lv_obj_set_style_text_font(boot_text, font, 0);
    lv_obj_set_style_text_align(boot_text, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(boot_text, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(boot_text, text_width);
    boot_facts = note(theme::Paint::muted);
    boot_hint = note(theme::Paint::ink_soft);
    boot_spinner = spinner_create(boot_panel, ring, ui::px(large ? 5 : 4));
    if (firmware_version) {
      boot_version = lv_label_create(boot_panel);
      lv_obj_add_style(boot_version, theme::style(theme::Paint::subtle), 0);
      if (small_font) lv_obj_set_style_text_font(boot_version, small_font, 0);
      lv_label_set_text_fmt(boot_version, "v%s", firmware_version);
      lv_obj_align(boot_version, LV_ALIGN_BOTTOM_MID, 0, -ui::px(large ? 16 : 8));
    }
  }
  // A protocol mismatch is a clear, blocking message, also when an older
  // sender connects after a valid layout. Do not leave stale tiles underneath
  // the text or let an invisible control take the user's tap.
  if (!waiting || cover) {
    lv_obj_add_flag(boot_panel, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_bg_color(boot_panel, theme::color(theme::PAGE), 0);
    lv_obj_set_style_bg_opa(boot_panel, LV_OPA_COVER, 0);
    lv_obj_move_foreground(boot_panel);
  } else {
    lv_obj_remove_flag(boot_panel, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_bg_opa(boot_panel, LV_OPA_TRANSP, 0);
    // Back under the tiles after a cover (a layout that stopped on its way): a see-through panel over them would lay
    // its words across the cards.
    if (room_label && lv_obj_get_index(boot_panel) > lv_obj_get_index(room_label))
      lv_obj_move_to_index(boot_panel, lv_obj_get_index(room_label));
  }
  if (boot_spinner) set_hidden(boot_spinner, !waiting);
  if (strcmp(lv_label_get_text(boot_text), text) != 0) lv_label_set_text(boot_text, text);
  if (facts != lv_label_get_text(boot_facts)) lv_label_set_text(boot_facts, facts.c_str());
  if (hint != lv_label_get_text(boot_hint)) lv_label_set_text(boot_hint, hint.c_str());
  set_hidden(boot_facts, facts.empty());
  set_hidden(boot_hint, hint.empty());
  // The lockup, the text and the spinner as one block in the middle of the page, the lockup a wider step away: it
  // names the screen, the text and the spinner say what it waits for. The facts sit close under the text they belong
  // to, the hint a step further.
  auto height = [&](const char *words, const lv_font_t *f) {
    lv_point_t size;
    lv_text_get_size(&size, words, f, 0, 0, text_width, LV_TEXT_FLAG_NONE);
    return (int) size.y;
  };
  // The steps a person takes next (firmware 0.45.0) and the text over them in the largest faces that leave the block
  // air on this glass, the lockup over them where there is room for it too: words to act on come before the name, so
  // the 2.8-inch shows them large without the lockup and the 10.1-inch large with it.
  const lv_font_t *title_font = font, *steps_font = control_font ? control_font : note_font;
  bool lockup_shown = true;
  if (!steps.empty()) {
    const int glass_h = lv_display_get_vertical_resolution(lv_obj_get_display(page));
    const int lockup = boot_brand ? (int) lv_obj_get_style_height(boot_brand, LV_PART_MAIN) + 2 * gap : 0;
    struct Step { const lv_font_t *title, *steps; bool lockup; };
    const Step ladder[] = {{watch_value_font, font, true}, {watch_value_font, font, false},
                           {font, steps_font, true}, {font, steps_font, false}};
    for (const auto &step : ladder) {
      if (!step.title || !step.steps) continue;
      const auto m = steps_measure(steps, step.steps, text_width);
      const int block_h = (step.lockup ? lockup : 0) + height(text, step.title) + 2 * gap + m.height;
      if (block_h <= glass_h * 3 / 5 && m.width <= text_width) {
        title_font = step.title;
        steps_font = step.steps;
        lockup_shown = step.lockup;
        break;
      }
    }
  }
  if (lv_obj_get_style_text_font(boot_text, LV_PART_MAIN) != title_font) lv_obj_set_style_text_font(boot_text, title_font, 0);
  const int text_h = height(text, title_font);
  const int facts_h = facts.empty() ? 0 : line_gap + height(facts.c_str(), note_font);
  const int hint_h = hint.empty() ? 0 : gap + height(hint.c_str(), note_font);
  int brand = boot_brand ? (int) lv_obj_get_style_height(boot_brand, LV_PART_MAIN) : 0, brand_gap = boot_brand ? 2 * gap : 0;
  int qr_h = 0;
#if LV_USE_QRCODE
  if (!qr.empty()) {
    // As large as the room leaves, at most half the glass's width, with a quiet zone of a tenth on every side. Where
    // that leaves too small a code, the lockup goes first.
    const int height = lv_display_get_vertical_resolution(lv_obj_get_display(page));
    const int foot = boot_version ? 2 * ui::px(large ? 16 : 8) + lv_obj_get_height(boot_version) : gap;
    auto room = [&]() { return height - foot - gap - (brand + brand_gap + text_h + facts_h + hint_h) - gap; };
    if (room() < ui::px(120) && boot_brand) { set_hidden(boot_brand, true); brand = brand_gap = 0; }
    const int side = std::max(ui::px(60), std::min(width / 2, room()));
    const int zone = std::max(4, side / 10), code = side - 2 * zone;
    if (!boot_qr) {
      boot_qr = lv_qrcode_create(boot_panel);
      lv_qrcode_set_dark_color(boot_qr, theme::color(theme::QR_DARK));
      lv_qrcode_set_light_color(boot_qr, theme::color(theme::QR_LIGHT));
      lv_obj_set_style_border_color(boot_qr, theme::color(theme::QR_LIGHT), 0);
    }
    if (lv_obj_get_style_border_width(boot_qr, LV_PART_MAIN) != zone) lv_obj_set_style_border_width(boot_qr, zone, 0);
    lv_qrcode_set_size(boot_qr, code);
    lv_qrcode_update(boot_qr, qr.data(), qr.size());
    set_hidden(boot_qr, false);
    qr_h = gap + side;
  } else if (boot_qr) {
    set_hidden(boot_qr, true);
  }
  if (qr.empty() && boot_brand) set_hidden(boot_brand, false);
#endif
  // The steps a person takes next, under the text (firmware 0.45.0): made again when they change, gone without.
  static std::vector<std::string> shown_steps;
  static const lv_font_t *shown_font = nullptr;
  if (boot_steps && (steps != shown_steps || steps_font != shown_font)) { lv_obj_delete(boot_steps); boot_steps = nullptr; }
  if (!steps.empty() && !boot_steps) boot_steps = steps_create(boot_panel, steps, steps_font, text_width);
  shown_steps = steps;
  shown_font = steps_font;
  const int steps_h = boot_steps ? 2 * gap + (int) lv_obj_get_style_height(boot_steps, LV_PART_MAIN) : 0;
  if (boot_steps && !lockup_shown && boot_brand) { set_hidden(boot_brand, true); brand = brand_gap = 0; }
  const int block = brand + brand_gap + text_h + facts_h + hint_h + qr_h + steps_h + (waiting ? gap + ring : 0);
  int top = -block / 2;
  if (boot_brand && brand) { lv_obj_align(boot_brand, LV_ALIGN_CENTER, 0, top + brand / 2); top += brand + brand_gap; }
  lv_obj_align(boot_text, LV_ALIGN_CENTER, 0, top + text_h / 2);
  top += text_h;
  if (facts_h) { lv_obj_align(boot_facts, LV_ALIGN_CENTER, 0, top + line_gap + (facts_h - line_gap) / 2); top += facts_h; }
  if (hint_h) { lv_obj_align(boot_hint, LV_ALIGN_CENTER, 0, top + gap + (hint_h - gap) / 2); top += hint_h; }
#if LV_USE_QRCODE
  if (qr_h && boot_qr) { lv_obj_align(boot_qr, LV_ALIGN_CENTER, 0, top + gap + (qr_h - gap) / 2); top += qr_h; }
#endif
  if (steps_h) { lv_obj_align(boot_steps, LV_ALIGN_CENTER, 0, top + 2 * gap + (steps_h - 2 * gap) / 2); top += steps_h; }
  top += gap;
  if (boot_spinner) lv_obj_align(boot_spinner, LV_ALIGN_CENTER, 0, top + ring / 2);
  // The version under the block, where the block leaves it room (firmware 0.45.0): a long hint with its spinner on
  // the smallest glass reached into it.
  if (boot_version) {
    const int height = lv_display_get_vertical_resolution(lv_obj_get_display(page));
    const int foot = 2 * ui::px(large ? 16 : 8) + lv_font_get_line_height(small_font ? small_font : font) + gap;
    set_hidden(boot_version, block / 2 > height / 2 - foot);
  }
}
// A connection that left before it said who it was (firmware 0.38.0, ESPHome's api on_client_disconnected): every
// client names itself in its first message after the encrypted handshake, so one without a name never got through it.
// That is Home Assistant (or another ESPHome client) with a key that is not this screen's, and the starting screen says
// so while it waits for Home Assistant. A client that does get in clears it.
inline std::string turned_away;
inline void client_left(const std::string &name, const std::string &address) {
  if (name.empty() && !address.empty()) turned_away = address;
}
inline void client_came() { turned_away.clear(); }
inline void boot_forget() {
  if (boot_panel) lv_obj_delete(boot_panel);
  boot_panel = boot_text = boot_spinner = boot_brand = boot_version = boot_facts = boot_hint = boot_qr = boot_steps = nullptr;
}
// A line of fun under "Preparing pages", about what the page being built holds: a joke is welcome where nothing is at
// stake, and waiting for a screen to load is such a moment. Its first tile of a kind with a line of its own picks it;
// every line only looks, so nobody wonders what the screen is doing to a device.
inline uint16_t prepare_joke(int page) {
  std::array<Placement, TILES_MAX> placement;
  place(model, placement);
  std::array<int, CELLS_MAX> first;
  first.fill(-1);
  for (size_t i = 0; i < model.count; ++i)
    if (placement[i].page == page && placement[i].slot < first.size()) first[placement[i].slot] = (int) i;
  for (int index : first) {
    if (index < 0) continue;
    const auto &t = model.tiles[index];
    const std::string d = t.domain();
    if (t.is_clock() || t.is_bedside()) return txt::preparing_clock;
    if (d == "light") return txt::preparing_light;
    if (d == "media_player") return txt::preparing_media;
    if (d == "camera" || d == "image") return txt::preparing_camera;
    if (d == "climate" || d == "water_heater") return txt::preparing_climate;
    if (d == "weather") return txt::preparing_weather;
    if (d == "cover") return txt::preparing_cover;
    if (d == "vacuum" || d == "lawn_mower") return txt::preparing_vacuum;
    if (d == "sun") return txt::preparing_sun;
    if (d == "scene" || d == "script" || d == "automation") return txt::preparing_scene;
    if (d == "switch" || d == "input_boolean" || d == "fan" || d == "remote") return txt::preparing_switch;
    if (d == "sensor" || d == "binary_sensor") return txt::preparing_sensor;
  }
  return txt::preparing_default;
}
inline int next_to_prepare();
// "Preparing pages 3/8" over everything while the pages are built after the first layout (firmware 0.3.2+), with the
// line of fun for the page that is next.
inline void prepare_status() {
  if (!room_label) return;
  const unsigned shown = std::min(preparing.done + 1, std::max(1u, preparing.total));
  const int next = next_to_prepare();
  const std::string text = fill(fill(txt::status_preparing_pages, "n", (int) shown), "total", std::to_string(preparing.total)) +
                           "\n" + tr(next >= 0 ? prepare_joke(next) : txt::preparing_default);
  boot_status(lv_obj_get_parent(room_label), text.c_str(), true, true);
}
// The network as a line of facts: its name, the signal and the address, as far as the screen has them.
inline std::string network_facts(const wifi_status::Link &link) {
  std::string facts = link.ssid;
  auto add = [&](const std::string &part) { if (!part.empty()) facts += (facts.empty() ? "" : " \u00B7 ") + part; };
  if (link.connected && link.rssi < 0) add(std::to_string(link.rssi) + " dBm");
  add(link.address);
  return facts;
}
// What keeps the screen off its network, in words (wifi_status::trouble), empty while nothing is known to be wrong.
inline std::string trouble_text(const wifi_status::Link &link) {
  switch (wifi_status::trouble(link)) {
    case wifi_status::Trouble::not_found: return tr(txt::status_wifi_not_found);
    case wifi_status::Trouble::password: return tr(txt::status_wifi_password);
    case wifi_status::Trouble::weak:
      return fill(txt::status_wifi_weak, "dbm", std::to_string(link.seen ? link.seen_rssi : link.reason_rssi));
    case wifi_status::Trouble::failed: return tr(txt::status_wifi_failed);
    default: return std::string();
  }
}
// A network the screen cannot reach, said on the loading screen over everything (firmware 0.19.0, wifi_status.h): what is
// wrong, then what fixes it, the hotspot to join with its password or, without one, the way over USB. Since firmware
// 0.38.0 the network it tries and why that fails stand between the two.
// What a phone's camera reads to join the hotspot: the Wi-Fi QR code every phone knows (WIFI:T:WPA;S:...;P:...;;), with
// the characters it reserves escaped.
inline std::string hotspot_qr(const wifi_status::Problem &wifi) {
  if (!wifi.hotspot || wifi.ssid.empty()) return std::string();
  auto escape = [](const std::string &value) {
    std::string out;
    for (char c : value) { if (c == '\\' || c == ';' || c == ',' || c == ':' || c == '"') out += '\\'; out += c; }
    return out;
  };
  return "WIFI:T:" + std::string(wifi.password.empty() ? "nopass" : "WPA") + ";S:" + escape(wifi.ssid) + ";P:" +
         escape(wifi.password) + ";;";
}
inline std::string wifi_fix_text(const wifi_status::Problem &wifi) {
  return wifi.hotspot
      ? fill(fill(std::string(tr(txt::status_wifi_hotspot)), "name", wifi.ssid), "password", wifi.password)
      : std::string(tr(txt::status_wifi_usb));
}
// The starting screen, step by step (firmware 0.38.0). People asked what the screen is doing while it starts, and the
// screen knows: which network it tries and why that fails, its address once it has one, whether Home Assistant came,
// whether Tessera sent the tiles and how many of them arrived. Every step says itself with what the screen knows of it
// and how long it has been at it, and once a step takes long, what usually fixes it. tick() draws it again as soon as
// any of it changes.
enum class BootStep : uint8_t { wifi, address, home_assistant, tessera, choose, tiles };
// `choose`: Tessera said in its hello that it has no tiles for this screen yet (app 0.4.74+, page_protocol.h), so the
// screen waits for a person, not for a program: it says how its tiles are chosen, step by step.
struct BootView { std::string title, facts, hint; std::vector<std::string> steps; };
// Set by every hello: whether Tessera has no tiles for this screen yet. The first tiles of a layout clear it.
inline bool awaiting_tiles = false;
// This screen's name as its YAML gives it (esphome: friendly_name), the one Tessera lists it under.
inline std::string screen_name();
// How long a step may take before the screen says what usually fixes it.
constexpr uint32_t BOOT_HINT_MS = 30000;
inline BootStep boot_step = BootStep::wifi;
inline uint32_t boot_step_since = 0;
inline std::string elapsed_text(uint32_t ms) {
  const uint32_t seconds = ms / 1000;
  char text[12];
  snprintf(text, sizeof(text), "%u:%02u", (unsigned) (seconds / 60), (unsigned) (seconds % 60));
  return text;
}
inline std::string screen_name() {
#ifndef ESP_SCREEN_HOST
  const auto &friendly = esphome::App.get_friendly_name();
  return (friendly.empty() ? esphome::App.get_name() : friendly).str();
#else
  return std::string();
#endif
}
inline BootView boot_view(uint32_t now) {
  const auto link = wifi_status::link();
  const BootStep step = link.wifi && !link.connected ? (link.joined ? BootStep::address : BootStep::wifi)
                      : !ha_connected() ? BootStep::home_assistant
                      : transfer.begun ? BootStep::tiles : awaiting_tiles ? BootStep::choose : BootStep::tessera;
  if (step != boot_step || !boot_step_since) { boot_step = step; boot_step_since = now ? now : 1; }
  const uint32_t waited = now - boot_step_since;
  BootView view;
  if (step == BootStep::choose) {
    // Nothing technical to report: the screen is up and waits for its tiles, chosen in Tessera.
    view.title = tr(txt::status_first_tiles);
    view.steps = {tr(txt::status_first_tiles_open), fill(txt::status_first_tiles_pick, "name", screen_name()),
                  tr(txt::status_first_tiles_save)};
    return view;
  }
  std::vector<std::string> lines;
  if (link.wifi) lines.push_back(network_facts(link));
  std::string status;
  switch (step) {
    case BootStep::wifi:
      view.title = tr(txt::status_wifi_connecting);
      status = trouble_text(link);
      break;
    case BootStep::address: view.title = tr(txt::status_wifi_address); break;
    case BootStep::home_assistant:
      view.title = tr(txt::status_connecting);
      if (!turned_away.empty()) view.hint = fill(txt::status_hint_key, "address", turned_away);
      else if (waited >= BOOT_HINT_MS) view.hint = tr(txt::status_hint_home_assistant);
      break;
    case BootStep::tessera:
      view.title = tr(txt::status_waiting);
      if (waited >= BOOT_HINT_MS) view.hint = tr(txt::status_hint_tessera);
      break;
    case BootStep::choose: break;  // said above, with its steps
    case BootStep::tiles:
      view.title = transfer.expected_tiles
          ? fill(fill(txt::status_loading_tiles_count, "n", (int) transfer.tiles.count()), "total", std::to_string(transfer.expected_tiles))
          : std::string(tr(txt::status_loading_tiles));
      break;
  }
  // The time a step takes, once it takes long enough to wonder about (a normal start passes each step in a second).
  if (waited >= 3000) status += (status.empty() ? "" : " \u00B7 ") + elapsed_text(waited);
  if (!status.empty()) lines.push_back(status);
  for (const auto &line : lines) if (!line.empty()) view.facts += (view.facts.empty() ? "" : "\n") + line;
  return view;
}
// An update coming in, over everything (ota_status.h): drawn at once, since ESPHome's update loop holds LVGL's own. It
// stands on LVGL's top layer, over the screensaver, a card and the settings page, and the screen wakes for it first
// (ota_status::wake): an update that ran under a screensaver showed nothing until the screen restarted.
inline lv_obj_t *ota_panel = nullptr, *ota_label = nullptr;
inline void ota_forget() {
  if (ota_panel) lv_obj_delete(ota_panel);
  ota_panel = ota_label = nullptr;
}
inline void ota_draw() {
  const auto &p = ota_status::now;
  if (p.phase == ota_status::Phase::none) { ota_forget(); return; }
  if (!ota_panel) {
    if (ota_status::wake) ota_status::wake();
    ota_panel = lv_obj_create(lv_layer_top());
    lv_obj_remove_style_all(ota_panel);
    lv_obj_set_size(ota_panel, lv_pct(100), lv_pct(100));
    lv_obj_remove_flag(ota_panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ota_panel, LV_OBJ_FLAG_CLICKABLE);  // nothing under it takes a tap meanwhile
    lv_obj_set_style_bg_color(ota_panel, theme::color(theme::PAGE), 0);
    lv_obj_set_style_bg_opa(ota_panel, LV_OPA_COVER, 0);
    ota_label = lv_label_create(ota_panel);
    lv_obj_add_style(ota_label, theme::style(theme::Paint::ink), 0);
    if (watch_font) lv_obj_set_style_text_font(ota_label, watch_font, 0);
    lv_obj_set_style_text_align(ota_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(ota_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(ota_label, lv_pct(86));
    lv_obj_center(ota_label);
  }
  lv_obj_move_foreground(ota_panel);
  const std::string text = p.phase == ota_status::Phase::done ? std::string(tr(txt::status_update_restart))
                         : p.phase == ota_status::Phase::failed ? std::string(tr(txt::status_update_failed))
                         : fill(txt::status_updating, "percent", screen_text::percent(p.percent));
  lv_label_set_text(ota_label, text.c_str());
  lv_refr_now(nullptr);
}
// Before the first layout the screen is starting: HA connects, then ESP Screens sends the tiles.
// A pass that drew a few cards slowly (30 ms, 10 in Debug mode; docs/open-issues/slow-single-cards.md): its slowest
// card, the steps of its paint in ms (render_slot's laps), what asked for it to be drawn (tile_why), and how many objects
// stand on the screen, which every invalidation walks (LVGL 9.5 looks for a blurred object over the area it
// invalidates). The words and the count are made only here, in statics, for a slow pass.
inline void slow_pass_log(unsigned drawn,uint32_t took,size_t index,uint32_t slowest,const uint32_t *steps){
  static char line[128];
  size_t at=0;line[0]=0;
  for(unsigned i=0;i<swipe_profile::PARTS&&at<sizeof(line);++i)
    if(steps[i])at+=snprintf(line+at,sizeof(line)-at,"%s%s %u",at?", ":"",swipe_profile::PART_NAMES[i],(unsigned)steps[i]);
  static uint32_t objects;objects=0;
  lv_obj_tree_walk(lv_screen_active(),[](lv_obj_t *,void *)->lv_obj_tree_walk_res_t{++objects;return LV_OBJ_TREE_WALK_NEXT;},nullptr);
  ESP_LOGI("render","%u cards drawn in %u ms, slowest tile %u (%s), %u ms: %s ms, marked by %s; %u objects on the screen",drawn,(unsigned)took,
           (unsigned)index,index<model.count?model.tiles[index].entity.c_str():"",(unsigned)slowest,at?line:redraw_log::NO_STEP,
           redraw_log::words(static_cast<redraw_log::TileWhy>(index<tile_why.size()?tile_why[index]:0)),(unsigned)objects);
}
inline void render(lv_obj_t *room) {
  if (!enabled) return;
  room_label=room; swipe_profile::Lap lap;
  ota_status::watch();
  ota_status::draw = ota_draw;
  if (const auto wifi = wifi_status::problem(); wifi.shown) {
    const auto link = wifi_status::link();
    std::string facts = link.ssid;
    if (const std::string why = trouble_text(link); !why.empty()) facts += (facts.empty() ? "" : "\n") + why;
    boot_status(lv_obj_get_parent(room), tr(txt::status_wifi_problem), false, true, facts, wifi_fix_text(wifi), hotspot_qr(wifi));
    return;
  }
  if (protocol_problem != ProtocolProblem::none) {
    boot_status(lv_obj_get_parent(room), tr(protocol_problem == ProtocolProblem::old_addon
        ? txt::status_configuration_problem : txt::status_configuration_version), false);
    return;
  }
  if (!model.configured && !model.refusal.empty()) boot_status(lv_obj_get_parent(room), tr(txt::tile_refused), false);
  else if (!model.configured) {
    // A layout on its way (transfer.begun) covers everything until it is complete and its pages are prepared: the
    // cards of the new layout are drawn as their tiles arrive, and through a see-through screen they showed one by
    // one over the words, with the page flickering under them.
    const auto view = boot_view(esphome::millis());
    boot_status(lv_obj_get_parent(room), view.title.c_str(), view.steps.empty(), transfer.begun, view.facts, view.hint, std::string(), view.steps);
  }
  else if (preparing.foreground) prepare_status();
  else if (boot_panel) boot_forget();
  name_label(room, !model.configured ? std::string() : !model.ready() ? tr(txt::status_loading_tiles) : !ha_connected() ? tr(txt::status_ha_not_connected) : !feed_alive() ? tr(txt::status_manager_not_active) : model.title_of(applied_page));
  render_header();
  lap(swipe_profile::HEADER);
  // A refresh that names nothing draws every card (and counts as a change of everything); a changed display setting
  // says it is only the look and the time (dirty_time), the minute marks its own cards (mark_minute).
  if(!dirty_all && dirty_tiles.none() && !dirty_header && !dirty_time)mark_all(redraw_log::Why::nothing_named);
  const bool all=dirty_all || dirty_time;
  const char *why=dirty_all ? (all_why ? all_why : redraw_log::words(redraw_log::Why::unnamed)) : redraw_log::words(redraw_log::Why::display_setting);
  all_why=nullptr;
  const uint32_t upto=changes.last;  // every change asked for so far is drawn below, for the cards on the glass
  const TileSet tiles=dirty_tiles;
  dirty_all=dirty_header=dirty_time=false;dirty_tiles.reset();
  // What was drawn and how long it took, said when it was every card or a slow pass: a page that seems to load again
  // is a pass over every card (its reason) or one card built anew (the slowest slot).
  const uint32_t began=esphome::millis();
  unsigned drawn=0;uint32_t slowest=0;size_t slowest_index=0;
  // The steps of the slowest card's paint (swipe_profile's laps, in statics: nothing more on the loop task's stack).
  static uint32_t slowest_steps[swipe_profile::PARTS];
  for (size_t slot = 0; slot < grid.slots(); ++slot) {
    const auto &w=widgets[slot];
    if(w.index>=model.count)continue;
    if(!(all || tiles.test(w.index)))continue;
    const uint32_t from=esphome::millis();
    render_slot(slot);
    ++drawn;
    if(esphome::millis()-from>slowest){
      slowest=esphome::millis()-from;slowest_index=w.index;
      std::copy(std::begin(swipe_profile::slot_steps),std::end(swipe_profile::slot_steps),std::begin(slowest_steps));
    }
  }
  const uint32_t took=esphome::millis()-began;
  if(all)ESP_LOGI("render","every card drawn: %s, %u cards in %u ms (slowest tile %u, %u ms)",why,drawn,(unsigned)took,(unsigned)slowest_index,(unsigned)slowest);
  // In Debug mode a pass of 10 ms already says its slowest card, so a card that drew in 33 ms once and now under 30 is
  // still seen; without it the logger stands at WARN and the line is never written anyway.
  else if(took>=(settings_screen::debug_mode?10u:30u))slow_pass_log(drawn,took,slowest_index,slowest,slowest_steps);
  // Kept pages learn nothing here: what they lack follows from the change numbers when they come back (kept_pages.h).
  glass_synced=upto;
}

// The page owns the header data; this adapter resolves navigation and settings.
inline const void *header_home_mark = nullptr;  // the Tessera mark of the home key, an lv_image_dsc_t
inline const lv_font_t *header_back_font = nullptr;
inline const lv_font_t *header_status_font = nullptr;  // the Wi-Fi item's bars (firmware 0.38.0)
inline std::function<void()> back_home;
// The battery the top bar can show (firmware 0.41.0, docs/BATTERY.md): the first of the screen's sensors in Home
// Assistant's `battery` device class (percent), and the first binary sensor in its `battery_charging` class. Whatever the
// board measures them with, a fuel gauge, a power chip, a voltage on a pin and a formula or the Tab5's INA226, the
// firmware reads them itself, so the item stays right while Home Assistant is away. Found once at boot (packages/core.yaml);
// a screen without such a sensor has no battery, says none in its hello, and ESP Screens offers no item for it.
#ifndef ESP_SCREEN_HOST
inline bool has_device_class(const esphome::EntityBase *entity, const char *wanted) {
  std::array<char, esphome::MAX_DEVICE_CLASS_LENGTH> buffer{};
  const char *name = entity->get_device_class_to(buffer);
  return name != nullptr && std::strcmp(name, wanted) == 0;
}
#endif
inline void find_battery() {
#ifndef ESP_SCREEN_HOST
#ifdef USE_SENSOR
  for (auto *sensor : esphome::App.get_sensors()) {
    if (!has_device_class(sensor, "battery")) continue;
    battery_status::level = [sensor]() { return sensor->state; };
    ESP_LOGI("battery", "Top bar battery: %s", sensor->get_name().c_str());
    break;
  }
#endif
#ifdef USE_BINARY_SENSOR
  if (battery_status::level) {
    for (auto *binary : esphome::App.get_binary_sensors()) {
      if (!has_device_class(binary, "battery_charging")) continue;
      battery_status::charging = [binary]() { return binary->has_state() ? (binary->state ? 1 : 0) : -1; };
      break;
    }
  }
#endif
#endif
}
// What the screen's own top bar items read (firmware 0.38.0): its network and whether Home Assistant and Tessera are there,
// and its battery (firmware 0.41.0).
inline header_bar::Device header_device() {
  const auto link = wifi_status::link();
  return {link.connected, link.rssi, ha_connected() && feed_alive(), battery_status::read()};
}
inline const header_bar::Bar *shown_bar() {
  const int index = shown_page ? *shown_page : 0;
  return model.configured && index >= 0 && static_cast<size_t>(index) < model.page_data.records.size()
       ? &model.page_data.records[index].bar : nullptr;
}
inline page_header::Renderer header_renderer;
inline void draw_header(bool live) {
  const int index = shown_page ? *shown_page : 0;
  const auto *record = model.configured && index >= 0 && static_cast<size_t>(index) < model.page_data.records.size()
                     ? &model.page_data.records[index] : nullptr;
  const header_bar::Bar empty;
  using page_header::Leading;
  const auto leading = !record ? Leading::none : header_back() ? Leading::back
                     : record->home_control && settings_screen::home_button ? Leading::home : Leading::none;
  page_header::View view{record ? record->bar : empty, header_name, now_time ? now_time() : esphome::ESPTime{},
                         now_epoch(), leading, live, screen_settings::current.clock_24h != 0, header_device()};
  header_renderer.draw({room_label, time_label, tile_grid, settings_screen::hold_area,
                        header_text_font, header_icon_font, header_home_mark, header_back_font, header_status_font},
                       view, []() {
    // The leading key keeps its existing place in the shared action guard.
    if (!allowed(esphome::millis(), 14, "header navigation")) return;
    if (header_back()) go_back();
    else if (back_home) back_home();
  });
}
// A tap on the Wi-Fi item or the link mark opens "This screen" (firmware 0.38.0), the network and links in words.
inline std::function<void()> open_this_screen;
inline void render_header() {
  if (!enabled) return;
  header_renderer.on_status([]() {
    if (!allowed(esphome::millis(), 14, "header navigation")) return;
    if (open_this_screen) open_this_screen();
  });
  // An entity in the top bar (firmware 0.56.0+) opens its tile's card through hold_card, and does nothing else: a switch
  // there opens its card instead of switching. Its tile is one on a page or a tile of the top bar (Tile::BAR_TILE), and
  // an unavailable entity opens nothing, as its tile does.
  header_renderer.on_item([](size_t item) {
    const auto *bar = shown_bar();
#ifdef SD_MOD_DOORBELL
    // A missed ring (module doorbell) opens that ring's view again.
    if (bar && item < bar->count && bar->items[item].card == header_bar::DOORBELL_CARD) {
      if (allowed(esphome::millis(), 14, "header doorbell")) doorbell::reopen();
      return;
    }
#endif
    if (!bar || item >= bar->count || bar->items[item].card >= model.count || !fresh()) return;
    const auto &tile = model.tiles[bar->items[item].card];
    if (!tile.received || !tile.available() || !allowed(esphome::millis(), 14, "header item")) return;
    hold_card(bar->items[item].card);
  });
  draw_header(ha_connected() && feed_alive());
}

// Inspect actual LVGL coordinates, including padding and the loaded font metrics.
// The Previous and Next bar and the page number between them (show_page binds them).
inline lv_obj_t *nav_prev=nullptr,*nav_next=nullptr,*nav_number=nullptr,*nav_back_label=nullptr;
// Whether the Previous and Next bar was on screen at the last placement (the grid is taller without it).
inline bool applied_bar=true;
inline bool check_tile_geometry() {
  bool ok=true;
  for(auto &w:widgets){
    if(!w.tile || lv_obj_has_flag(w.tile,LV_OBJ_FLAG_HIDDEN))continue;
    lv_obj_update_layout(w.tile);
    lv_area_t title,value,track,content;
    lv_obj_get_content_coords(w.tile,&content);
    lv_obj_get_coords(w.title,&title);lv_obj_get_coords(w.value,&value);
    // A camera's or a map's picture fills the card (render_camera_card): its name, if any, stands at the bottom on the
    // picture and the state line, the icon and the parts are hidden, so only the name's place is checked here.
    const bool picture_card=w.index<model.count&&(model.tiles[w.index].live()||model.tiles[w.index].is_map())&&w.extra_mode=="tall";
    bool custom=lv_obj_has_flag(w.title,LV_OBJ_FLAG_HIDDEN)||picture_card;
    const bool extended=!picture_card&&w.index<model.count&&model.tiles[w.index].row_span()>1&&!w.full&&(w.extra_mode=="tall"||w.extra_mode=="cover_tilt");
    bool fits=true;
    if(picture_card&&!lv_obj_has_flag(w.title,LV_OBJ_FLAG_HIDDEN)){
      const bool named=title.x1>=content.x1&&title.x2<=content.x2&&title.y1>=content.y1&&title.y2<=content.y2;
      if(!named)ESP_LOGE("ui_test","Picture name bounds slot=%u title=%d,%d..%d,%d content=%d,%d..%d,%d",(unsigned)w.index,(int)title.x1,(int)title.y1,(int)title.x2,(int)title.y2,(int)content.x1,(int)content.y1,(int)content.x2,(int)content.y2);
      fits=fits&&named;
    }
    if(w.index<model.count && model.tiles[w.index].height>1 && tile_grid){
      const int gap=lv_obj_get_style_pad_row(tile_grid,LV_PART_MAIN);
      const int cell=(lv_obj_get_content_height(tile_grid)-(int)(grid.rows-1)*gap)/(int)grid.rows;
      if(std::abs(lv_obj_get_height(w.tile)-((int)model.tiles[w.index].row_span()*cell+((int)model.tiles[w.index].row_span()-1)*gap))>2){
        fits=false;ESP_LOGE("ui_test","Tall card height FAIL slot=%u",(unsigned)w.index);
      }
    }
    for(const auto &other:widgets) if(other.tile && other.tile!=w.tile && !lv_obj_has_flag(other.tile,LV_OBJ_FLAG_HIDDEN)){
      lv_area_t a,b;lv_obj_get_coords(w.tile,&a);lv_obj_get_coords(other.tile,&b);
      // A bedside clock's keys lie on its card (firmware 0.8.0+): inside it, never over each other.
      if((w.key&&other.full)||(w.full&&other.key)){
        const lv_area_t &key=w.key?a:b,&clock=w.key?b:a;
        if(key.x1<clock.x1||key.x2>clock.x2||key.y1<clock.y1||key.y2>clock.y2){fits=false;ESP_LOGE("ui_test","Key outside its clock FAIL slot=%u",(unsigned)(w.key?w.index:other.index));}
        continue;
      }
      if(a.x1<=b.x2 && b.x1<=a.x2 && a.y1<=b.y2 && b.y1<=a.y2){
        fits=false;ESP_LOGE("ui_test","Card overlap FAIL slots=%u,%u",(unsigned)w.index,(unsigned)other.index);
      }
    }
    if(w.wide && !w.full && grid.columns>1 && tile_grid){
      // A wide card is its cells of the row plus the gaps between them: two, or a span's own (a 3 x 2).
      const int gap=lv_obj_get_style_pad_column(tile_grid,LV_PART_MAIN);
      const int span=w.index<model.count?(int)model.tiles[w.index].column_span():2;
      // The columns' free units: LVGL shares the room exactly and rounds each track, so the sum is rounded once.
      const int room=lv_obj_get_content_width(tile_grid)-(int)(grid.columns-1)*gap;
      int expected=(span*room+(int)grid.columns/2)/(int)grid.columns+(span-1)*gap;
      const bool width_ok=std::abs(lv_obj_get_width(w.tile)-expected)<=1;
      fits=fits && width_ok;
      if(!width_ok)ESP_LOGE("ui_test","Wide width FAIL slot=%u width=%d expected=%d",(unsigned)w.index,(int)lv_obj_get_width(w.tile),expected);
    }
    {
      // Every card lies inside the tile area, a full card reaches its end, and the area stays clear of the page bar
      // and keeps the side margin at the bottom of the screen (firmware 0.2.69+ moves the rows without the bar).
      lv_area_t card,area,screen;auto *grid=lv_obj_get_parent(w.tile);
      lv_obj_get_coords(w.tile,&card);lv_obj_get_coords(grid,&area);lv_obj_get_coords(lv_obj_get_parent(grid),&screen);
      // The margin is the grid's padding now, and LVGL's lv_obj_get_x() reports a cell without it.
      const int margin=grid_margin;
      bool placed=card.y1>=area.y1 && card.y2<=area.y2 && area.y2<=screen.y2-margin && (!w.full || card.y2==area.y2);
      if(applied_bar && nav_next){lv_area_t nav;lv_obj_get_coords(nav_next,&nav);placed=placed && area.y2<nav.y1;}
      if(!applied_bar)placed=placed && area.y2>=screen.y2-margin-3;
      if(!placed){fits=false;ESP_LOGE("ui_test","Card place FAIL slot=%u card=%d..%d area=%d..%d screen_bottom=%d bar=%d",(unsigned)w.index,(int)card.y1,(int)card.y2,(int)area.y1,(int)area.y2,(int)screen.y2,applied_bar);}
    }
    // A centred stack (a built-in action, or an on/off card with its switch under the name). Only with its name on the
    // card: a clock hides the name, which keeps the alignment of whatever the card showed before (firmware 0.3.2).
    const bool centered_action=!custom && w.index<model.count && model.tiles[w.index].row_span()>1 && !w.full &&
      lv_obj_get_style_text_align(w.title,LV_PART_MAIN)==LV_TEXT_ALIGN_CENTER;
    if(centered_action){
      lv_area_t circle;lv_obj_get_coords(w.circle,&circle);
      const bool state=!lv_obj_has_flag(w.value,LV_OBJ_FLAG_HIDDEN);
      int bottom=state?value.y2:title.y2;
      if(w.panel&&!lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN)){
        lv_area_t b;lv_obj_get_coords(w.panel,&b);
        fits=fits&&b.y1>bottom&&b.x1>=content.x1&&b.x2<=content.x2&&b.y2<=content.y2&&std::abs(b.x1+b.x2-content.x1-content.x2)<=1;
        bottom=b.y2;
      }
      fits=fits&&circle.x1>=content.x1&&circle.x2<=content.x2&&circle.y1>=content.y1&&circle.y2<title.y1;
      fits=fits&&title.x1>=content.x1&&title.x2<=content.x2&&bottom<=content.y2;
      if(state)fits=fits&&value.x1>=content.x1&&value.x2<=content.x2&&title.y2<value.y1;
      fits=fits&&std::abs(circle.x1+circle.x2-content.x1-content.x2)<=1&&
        std::abs(title.x1+title.x2-content.x1-content.x2)<=1&&
        std::abs(circle.y1+bottom-content.y1-content.y2)<=1;
    }else if(extended){
      lv_area_t circle;lv_obj_get_coords(w.circle,&circle);
      fits=fits&&title.x1>=content.x1&&title.x2<=content.x2&&title.y1>=content.y1&&title.y2<=content.y2;
      if(!lv_obj_has_flag(w.value,LV_OBJ_FLAG_HIDDEN))fits=fits&&title.y2<value.y1&&value.x1>=content.x1&&value.x2<=content.x2&&value.y2<=content.y2;
      fits=fits&&circle.x1>=content.x1&&circle.x2<title.x1&&circle.y1>=content.y1&&circle.y2<=content.y2;
      for(auto *part:w.parts)if(part&&!lv_obj_has_flag(part,LV_OBJ_FLAG_HIDDEN)){
        lv_area_t a;lv_obj_get_coords(part,&a);
        // Under the heading, or wholly right of it (a player's volume standing at the card's right, media_standing).
        const bool beside_head=a.x1>std::max(title.x2,lv_obj_has_flag(w.value,LV_OBJ_FLAG_HIDDEN)?title.x2:value.x2);
        fits=fits&&a.x1>=content.x1&&a.x2<=content.x2&&(beside_head||a.y1>std::max(title.y2,value.y2))&&a.y1>=content.y1&&a.y2<=content.y2;
        if(w.panel&&!lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN)){
          lv_area_t b;lv_obj_get_coords(w.panel,&b);fits=fits&&(a.x2<b.x1||b.x2<a.x1||a.y2<b.y1||b.y2<a.y1);
        }
      }
    }else if(!custom && w.full){
      // Everything inside the card, the name above the state, a slider or the controls below them.
      fits=fits && title.x1>=content.x1 && title.x2<=content.x2 && value.x1>=content.x1 && value.x2<=content.x2 &&
        title.y1>=content.y1 && title.y2<value.y1 && value.y2<=content.y2;
      lv_area_t circle;lv_obj_get_coords(w.circle,&circle);
      fits=fits && circle.x1>=content.x1 && circle.x2<=content.x2 && circle.y1>=content.y1 && circle.y2<=content.y2;
      if(!lv_obj_has_flag(w.slider,LV_OBJ_FLAG_HIDDEN)){
        lv_obj_get_coords(w.slider,&track);
        fits=fits && value.y2<track.y1 && track.y2<=content.y2;
      }
    }else if(!custom){
      // The value stands under the name, or beside it on a strip card whose cell is short (one_line); a big value
      // on a short cell may end its line in the padding (never past the border).
      lv_area_t card;lv_obj_get_coords(w.tile,&card);
      const bool big_value=w.index<model.count && model.tiles[w.index].display=="watch";
      // A big value stands under the name on every cell, a short one too (render_slot's watch block, firmware 0.35.0):
      // its line no longer reaches into the name's.
      fits=fits && title.x1>=content.x1 && title.x2<=content.x2 &&
        value.x1>=content.x1 && value.x2<=content.x2 && (title.y2<value.y1 || title.x2<value.x1) &&
        value.y2<=(big_value?card.y2-1:content.y2);
      if(!lv_obj_has_flag(w.slider,LV_OBJ_FLAG_HIDDEN)){
        lv_obj_get_coords(w.slider,&track);
        fits=fits && value.y2<track.y1 && track.y2<=content.y2;
      }
      if(!lv_obj_has_flag(w.circle,LV_OBJ_FLAG_HIDDEN)){
        lv_area_t circle,card;lv_obj_get_coords(w.circle,&circle);lv_obj_get_coords(w.tile,&card);
        bool mini=!lv_obj_has_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
        // The circle may stand in the card's padding on a short cell (head_row), never past its border. It
        // stands beside the name on a cell of the usual height and above it on a tall one, where the card
        // stacks (a ten-inch standing up gives a cell twice the look's height), so both count as in place.
        const bool beside=circle.x2<title.x1;
        const bool above=circle.y2<=title.y1 && circle.x2<=content.x2;
        fits=fits && circle.x1>=content.x1 && (beside || above) && circle.y1>card.y1;
        if(mini)fits=fits && circle.y2<track.y1;
        else fits=fits && circle.y2<card.y2;
        if(!fits)ESP_LOGE("ui_test","Icon bounds slot=%u circle=%d,%d..%d,%d title_x=%d content=%d,%d..%d,%d",(unsigned)w.index,(int)circle.x1,(int)circle.y1,(int)circle.x2,(int)circle.y2,(int)title.x1,(int)content.x1,(int)content.y1,(int)content.x2,(int)content.y2);
        bool watch=w.index<model.count && model.tiles[w.index].display=="watch";
        bool graph=w.extra && !lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN) && w.extra_mode=="graph";
        if(!watch && !graph && (mini || !ui::large())){
          int header_bottom=mini?track.y1-ui::px(ui::large()?6:3)-1:content.y2;
          int center_twice=content.y1+header_bottom;
          fits=fits && std::abs(circle.y1+circle.y2-center_twice)<=2 &&
            std::abs(title.y1+value.y2-center_twice)<=2;
        }
      }
      if(!lv_obj_has_flag(w.unit,LV_OBJ_FLAG_HIDDEN)){
        // A large value's unit sits under the name beside the number; a navigation tile's chevron beside both.
        lv_area_t unit;lv_obj_get_coords(w.unit,&unit);
        bool chevron=w.index<model.count && model.tiles[w.index].is_page();
        fits=fits && value.x2<unit.x1 && unit.x2<=content.x2 && unit.y2<=content.y2 && unit.y1>=content.y1 && (chevron ? title.x2<unit.x1 : unit.y1>title.y2);
      }
    }
    if(w.panel && !lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN)){
      // Direct controls stay inside the card, right of the name and status, and inside their panel.
      lv_area_t panel;lv_obj_get_coords(w.panel,&panel);
      bool inside=panel.x1>=content.x1 && panel.x2<=content.x2 && panel.y1>=content.y1 && panel.y2<=content.y2 && (custom || ((w.full||extended) ? value.y2<panel.y1 : title.x2<panel.x1 && value.x2<panel.x1));
      for(uint32_t i=0;i<lv_obj_get_child_count(w.panel);++i){
        auto *child=lv_obj_get_child(w.panel,i);if(lv_obj_has_flag(child,LV_OBJ_FLAG_HIDDEN))continue;
        lv_area_t part;lv_obj_get_coords(child,&part);
        inside=inside && part.x1>=panel.x1 && part.x2<=panel.x2 && part.y1>=panel.y1 && part.y2<=panel.y2;
      }
      if(!inside)ESP_LOGE("ui_test","Panel bounds slot=%u mode=%s panel=%d,%d..%d,%d title_x2=%d content=%d,%d..%d,%d",(unsigned)w.index,w.panel_mode.c_str(),(int)panel.x1,(int)panel.y1,(int)panel.x2,(int)panel.y2,(int)title.x2,(int)content.x1,(int)content.y1,(int)content.x2,(int)content.y2);
      fits=fits && inside;
    }
    if(w.extra && !lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN)){
      // Custom parts stay inside the card; a graph never runs into the text.
      lv_area_t extra;lv_obj_get_coords(w.extra,&extra);
      const bool extra_inside=extra.x1>=content.x1 && extra.x2<=content.x2 && extra.y1>=content.y1 && extra.y2<=content.y2;
      if(!extra_inside)ESP_LOGE("ui_test","Extra bounds slot=%u mode=%s extra=%d,%d..%d,%d content=%d,%d..%d,%d",(unsigned)w.index,w.extra_mode.c_str(),(int)extra.x1,(int)extra.y1,(int)extra.x2,(int)extra.y2,(int)content.x1,(int)content.y1,(int)content.x2,(int)content.y2);
      fits=fits && extra_inside;
    // A dial's ticks are strokes standing on the rim of the dial, and a stroke straddles the line it is drawn
    // on: half its width falls outside the circle it marks. On a card whose cell is short the dial fills the
    // content area exactly, so that half stroke reaches into the card's own padding. It is inside the card and
    // reads as intended, the way the icon circle is allowed to stand in the padding on a short cell, so a
    // clock's parts are held to the card's border instead of its content area.
    // The clock's digits are placed by their glyphs (firmware 0.3.6+): the empty top and bottom of a big font's line
    // box may stand in the padding too, the digits themselves stay in the content area.
    // The calendar card's canvas covers the whole card, its padding too (calendar_view.cpp), and paints its plan in the
    // content's coordinates: it is held to the card's border as well.
    const bool dial=w.extra_mode=="calendar" || w.extra_mode=="calendar_card" || w.extra_mode=="analog" || w.extra_mode=="calm" || w.extra_mode=="flip" || w.extra_mode=="digital" || w.extra_mode=="bedside";
    lv_area_t card_box;lv_obj_get_coords(w.tile,&card_box);
      for(auto *p:w.parts){
        if(!p || lv_obj_has_flag(p,LV_OBJ_FLAG_HIDDEN))continue;
        lv_area_t part;lv_obj_get_coords(p,&part);
        // The bedside clock's digits count by their glyphs: a font's line box keeps room above the digits that on a
        // 350 px face is taller than the card's padding, and nothing is drawn there.
        if(w.extra_mode=="bedside" && (p==w.parts[0]||p==w.parts[1])){int top,h;digit_box(bedside_digits(),top,h);part.y1+=top;part.y2=part.y1+h-1;}
        const lv_area_t &room=dial?card_box:content;
        bool inside=part.x1>=room.x1 && part.x2<=room.x2 && part.y1>=room.y1 && part.y2<=room.y2;
        if(!inside)ESP_LOGE("ui_test","Part bounds slot=%u mode=%s part=%d,%d..%d,%d room=%d,%d..%d,%d",(unsigned)w.index,w.extra_mode.c_str(),(int)part.x1,(int)part.y1,(int)part.x2,(int)part.y2,(int)room.x1,(int)room.y1,(int)room.x2,(int)room.y2);
        fits=fits && inside;
        if(w.extra_mode=="graph" && !custom)fits=fits && (w.wide && !w.full?part.x1>value.x2:part.y1>value.y2);
      }
    }
    // The board's bedside digits fit its page in one of the three arrangements (bedside_digits, looks/shared/digits.yaml).
    if(w.extra_mode=="bedside" && w.index<model.count){
      const auto l=bedside_layout(content_width(w),content_height(w),lv_obj_get_style_space_top(w.tile,LV_PART_MAIN),bedside_names(w.index));
      if(!l.fits){fits=false;ESP_LOGE("ui_test","Bedside digits fit FAIL slot=%u w=%d h=%d pad=%d digit_h=%d key=%d names=%d",(unsigned)w.index,
        (int)content_width(w),(int)content_height(w),(int)lv_obj_get_style_space_top(w.tile,LV_PART_MAIN),l.digit_h,l.key,l.name_h);}
    }
    if(!fits)ESP_LOGE("ui_test","Tile geometry FAIL slot=%u mode=%s wide=%d title_y=%d..%d value_y=%d..%d content_y=%d..%d",(unsigned)w.index,w.extra_mode.c_str(),w.wide,(int)title.y1,(int)title.y2,(int)value.y1,(int)value.y2,(int)content.y1,(int)content.y2);
    if(w.index<model.count && card_face(w).kind!=theme::Face::CARD){
      bool palette_ok=lv_color_eq(lv_obj_get_style_bg_color(w.tile,LV_PART_MAIN),lv_color_hex(card_surface(w))) &&
        lv_color_eq(lv_obj_get_style_text_color(w.title,LV_PART_MAIN),theme::color(theme::INK));
      if(!palette_ok)ESP_LOGE("ui_test","Tile palette FAIL slot=%u",(unsigned)w.index);
      fits=fits && palette_ok;
    }
    if(w.index<model.count){
      bool bare=model.tiles[w.index].transparent;
      bool opa_ok=(lv_obj_get_style_bg_opa(w.tile,LV_PART_MAIN)==LV_OPA_TRANSP)==bare && (lv_obj_get_style_border_opa(w.tile,LV_PART_MAIN)==LV_OPA_TRANSP)==bare;
      // A bedside clock's key is its filled circle, without a border (firmware 0.8.0+).
      if(w.key)opa_ok=lv_obj_get_style_bg_opa(w.tile,LV_PART_MAIN)==LV_OPA_COVER && lv_obj_get_style_border_opa(w.tile,LV_PART_MAIN)==LV_OPA_TRANSP;
      if(!opa_ok)ESP_LOGE("ui_test","Tile background FAIL slot=%u transparent=%d",(unsigned)w.index,bare);
      fits=fits && opa_ok;
    }
    ok=ok && fits;
  }
  // The tiles start below the top bar with room to spare (firmware 0.15.0+, GitHub #90): the tail of a g in the
  // page's name, the lowest any title can reach in its font, stays at least a pixel clear of the tile area.
  if(room_label && tile_grid && !lv_obj_has_flag(room_label,LV_OBJ_FLAG_HIDDEN)){
    const lv_font_t *font=lv_obj_get_style_text_font(room_label,LV_PART_MAIN);lv_font_glyph_dsc_t tail;
    if(font && lv_font_get_glyph_dsc(font,&tail,'g',0) && tail.box_h){
      const int baseline=lv_obj_get_y(room_label)+(font->line_height-font->base_line);
      const int lowest=baseline-tail.ofs_y,grid_top=lv_obj_get_y(tile_grid);
      if(grid_top<=lowest){ok=false;ESP_LOGE("ui_test","Top bar clear FAIL tail=%d grid=%d",lowest,grid_top);}
    }
  }
  return ok;
}

inline unsigned page_count() {
  std::array<Placement,TILES_MAX> placement;
  return place(model,placement);
}
// A page switch lands whole (firmware 0.2.93+): the swipe pass places the new page (page number,
// card widths) and draws every one of its cards before the loop goes on, so the refresh after it
// puts the complete page on the glass in one frame, and the old page stays there until then. Up to
// firmware 0.2.92 the first frame showed every card as an empty skeleton and the refreshes after it
// filled two cards each, which read as a page being built up in front of you. The whole pass is
// about 60 ms of CPU on the Guition and 30 ms on the CYD (docs/SWIPE_PROFILE.md): cheaper to wait
// for than to watch. Keepalives and re-packing on the same page draw at once. Nothing is allocated.
// A card's cell, set only when it changes: setting it always lays the whole grid out again.
inline void set_cell(lv_obj_t *obj, int32_t column, int32_t span_x, int32_t row, int32_t span_y) {
  if (lv_obj_get_style_grid_cell_column_pos(obj, LV_PART_MAIN) == column && lv_obj_get_style_grid_cell_column_span(obj, LV_PART_MAIN) == span_x &&
      lv_obj_get_style_grid_cell_row_pos(obj, LV_PART_MAIN) == row && lv_obj_get_style_grid_cell_row_span(obj, LV_PART_MAIN) == span_y &&
      lv_obj_get_style_grid_cell_x_align(obj, LV_PART_MAIN) == LV_GRID_ALIGN_STRETCH &&
      lv_obj_get_style_grid_cell_y_align(obj, LV_PART_MAIN) == LV_GRID_ALIGN_STRETCH) return;
  lv_obj_set_grid_cell(obj, LV_GRID_ALIGN_STRETCH, column, span_x, LV_GRID_ALIGN_STRETCH, row, span_y);
}
// What a page key shows: its chevron (page_bar::glyph), not its first child, which is the press patch behind it.
inline lv_obj_t *nav_glyph(lv_obj_t *key){return page_bar::glyph(key);}
// A card turns into a bedside clock's key and back (firmware 0.8.0+): out of the grid, round and without padding, so
// the card is the key; back in the grid with the card's own shape from its styles.
inline void key_shape(Widgets &w,bool key){
  if(key){
    // Out of the grid's stretch first: LVGL keeps a size a layout gave (it marks it) until a layout gives another, so
    // the grid places the card once more without stretching it, and place_keys then takes it out of the grid.
    lv_obj_set_grid_cell(w.tile,LV_GRID_ALIGN_START,0,1,LV_GRID_ALIGN_START,0,1);
    set_number(w.tile,LV_STYLE_RADIUS,LV_RADIUS_CIRCLE);
    for(auto prop:{LV_STYLE_PAD_LEFT,LV_STYLE_PAD_RIGHT,LV_STYLE_PAD_TOP,LV_STYLE_PAD_BOTTOM})set_number(w.tile,prop,0);
  }else{
    lv_obj_remove_flag(w.tile,LV_OBJ_FLAG_IGNORE_LAYOUT);
    for(auto prop:{LV_STYLE_RADIUS,LV_STYLE_PAD_LEFT,LV_STYLE_PAD_RIGHT,LV_STYLE_PAD_TOP,LV_STYLE_PAD_BOTTOM})
      lv_obj_remove_local_style_prop(w.tile,prop,LV_PART_MAIN);
    // Everything the key's round form set, back to the card's own: its circle, its icon and its value line.
    const int circle=w.base_circle>0?w.base_circle:ui::px(ui::large()?54:36);
    lv_obj_set_size(w.circle,circle,circle);set_hidden(w.icon,false);
    if(w.icon_font)set_font(w.icon,w.icon_font);
    if(w.value_font)set_font(w.value,w.value_font);
    set_text_align(w.value,LV_TEXT_ALIGN_LEFT);
    w.key_size=0;
  }
  // The heartbeat of an alarm or a lock moves from the circle to the card or back (alarm_tile_look): the old one stands
  // still, the next render starts it on the new one.
  alarm_still(key?w.circle:w.tile);
  w.alarm_look=LOOK_NONE;w.alarm_mark=0;
  w.key=key;w.cached_active=-1;
}
// The keys of the bedside clock on this page where its layout puts them, once the grid has placed the clock's card.
inline void place_keys(){
  auto &clock=widgets[0];
  if(!clock.tile||clock.index>=model.count||!model.tiles[clock.index].is_bedside()||!clock.full)return;
  const int pad=lv_obj_get_style_space_top(clock.tile,LV_PART_MAIN);
  const auto l=bedside_layout(content_width(clock),content_height(clock),pad,bedside_names(clock.index));
  const int x0=lv_obj_get_x(clock.tile)+lv_obj_get_style_space_left(clock.tile,LV_PART_MAIN);
  const int y0=lv_obj_get_y(clock.tile)+pad;
  for(size_t slot=1;slot<widgets.size();++slot){
    auto &w=widgets[slot];
    if(!w.key||!w.tile||w.index>=model.count)continue;
    const unsigned k=model.tiles[w.index].key;
    if(k>=l.keys){lv_obj_add_flag(w.tile,LV_OBJ_FLAG_HIDDEN);continue;}
    w.key_size=l.key;
    lv_obj_add_flag(w.tile,LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_pos(w.tile,x0+l.key_x[k],y0+l.key_y[k]);lv_obj_set_size(w.tile,l.key,l.key);
  }
}
// Slot assignment plus card places, sizes and visibility for a page; contents are untouched. `kept`: the cards already
// show this page (kept_pages.h), so a card that keeps its tile keeps what it knows about its own colours too.
// Whether each chevron leads somewhere from this page: past the ends too when the pages loop (docs/SETTINGS.md).
inline void show_page_keys(int page, bool detail) {
  const bool loop=settings_screen::loop_pages!=0;
  const int previous=detail?navigation_history.target(model.page_data,page):model.page_data.step(page,-1,loop);
  page_bar::enable(nav_prev,previous!=page);
  page_bar::enable(nav_next,model.page_data.step(page,1,loop)!=page);
}
inline int place_page(int page, bool kept = false) {
  swipe_profile::Lap lap;
  std::array<Placement,TILES_MAX> placement;
  int pages=place(model,placement);
  page=std::clamp(page,0,pages-1);
  const unsigned sequential_count = model.page_data.count();
  const bool bar=model.configured && model.page_data.footer(page_buttons);
  const bool detail=bar && model.page_data.detail(page);
  const bool sequential=bar && !detail && sequential_count>1 && page_buttons;
  applied_bar=bar;
  // Footer space belongs to the whole layout, not the current page. Switching
  // between a sequential page and a detail page never changes tile geometry.
  if(tile_grid){
    auto *screen=lv_obj_get_parent(tile_grid);
    const int height=bar||!screen?grid_base_height:lv_obj_get_height(screen)-lv_obj_get_y(tile_grid)-grid_margin;
    if(lv_obj_get_style_height(tile_grid,LV_PART_MAIN)!=height)lv_obj_set_height(tile_grid,height);
  }
  std::array<size_t,CELLS_MAX> shown;shown.fill(grid.max_tiles());
  for(size_t i=0;model.configured && i<model.count;++i)if(placement[i].page==page && placement[i].slot<shown.size())shown[placement[i].slot]=i;
  // A bedside clock takes the whole page; its keys take the cards of the cells it covers (firmware 0.8.0+).
  if(model.configured && shown[0]<model.count && model.tiles[shown[0]].is_bedside() && model.tiles[shown[0]].full)
    for(size_t i=0;i<model.count;++i){
      const auto &k=model.tiles[i];
      if(k.is_key() && (size_t)k.parent==shown[0] && k.key<bedside_key_room())shown[1+k.key]=i;
    }
  for(size_t slot=0;slot<widgets.size();++slot){
    auto &w=widgets[slot];
    if(!kept || w.index!=shown[slot])w.cached_active=-1;
    w.index=shown[slot];
    w.wide=w.index<model.count && model.tiles[w.index].wide;w.full=w.index<model.count && model.tiles[w.index].full;
    const bool key=w.index<model.count && model.tiles[w.index].is_key();
    if(w.tile && key!=w.key)key_shape(w,key);
  }
  for(size_t slot=0;slot<widgets.size();++slot){
    auto &w=widgets[slot];if(!w.tile)continue;
    if(w.key){lv_obj_remove_flag(w.tile,LV_OBJ_FLAG_HIDDEN);continue;}  // placed by place_keys below
    if(slot<grid.slots() && w.index<model.count){
      // A wide card takes two cells of its row (one on a single-column board), a full card the whole page.
      const int32_t column=w.full?0:(int32_t)(slot%grid.columns),row=w.full?0:(int32_t)(slot/grid.columns);
      const auto &tile=model.tiles[w.index];
      const int32_t span_x=tile.column_span(),span_y=tile.row_span();
#ifdef SD_MOD_SECTIONS
      ::sections::place(w,page,column,span_x,row,span_y);
#else
      set_cell(w.tile,column,span_x,row,span_y);
#endif
      lv_obj_remove_flag(w.tile,LV_OBJ_FLAG_HIDDEN);
    }
    else{lv_obj_add_flag(w.tile,LV_OBJ_FLAG_HIDDEN);hide_extra(w);hide_panel(w);}
  }
  set_hidden(nav_prev,!(sequential || detail));
  for(auto *control:{nav_next,nav_number})set_hidden(control,!sequential);
  if(nav_back_label){
    set_hidden(nav_back_label,!detail);
    if(detail){
      label(nav_back_label,tr(txt::navigation_back));
      set_color(nav_back_label,LV_STYLE_TEXT_COLOR,theme::color(theme::INK));
      if(header_text_font)set_font(nav_back_label,header_text_font);
      if(auto *chevron=nav_glyph(nav_prev))lv_obj_align_to(nav_back_label,chevron,LV_ALIGN_OUT_RIGHT_MID,ui::px(4),0);
    }
  }
  // Paint the document's destinations even while an error overlay blocks input.
  // Settings can re-place this page under that overlay; using the action guard
  // here would leave the arrows disabled when the same document recovers.
  show_page_keys(page,detail);
  // The dots between the two chevrons (firmware 0.2.69+): the page on screen in ink.
  if(sequential && nav_number)page_bar::dots(nav_number,model.page_data.ordinal(page),sequential_count);
#ifdef SD_MOD_SECTIONS
  ::sections::show(page);
#endif
  // The cards are drawn from the sizes the grid gives them, so it lays out before anything reads one.
  if(tile_grid)lv_obj_update_layout(tile_grid);
  if(widgets[0].tile && widgets[0].index<model.count && model.tiles[widgets[0].index].is_bedside()){
    place_keys();
    if(tile_grid)lv_obj_update_layout(tile_grid);
  }
  lap(swipe_profile::PLACE);
  return page;
}
inline void apply_page(int page) {
  applied_page=place_page(page);
  if(room_label){mark_all(redraw_log::Why::page_placed);render(room_label);}else refresh_all(redraw_log::Why::page_placed);
}
// ---- Pages kept whole: memory and the exchange of card sets (kept_pages.h) ----
inline void *kept_allocate(size_t bytes) {
#ifdef USE_ESP32
  return heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
#else
  return std::malloc(bytes);
#endif
}
inline void kept_free(void *memory) {
#ifdef USE_ESP32
  heap_caps_free(memory);
#else
  std::free(memory);
#endif
}
inline size_t psram_free() {
#ifdef USE_ESP32
  return heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
#else
  return SIZE_MAX;
#endif
}
// ---- The memory the tiles take (tile_memory.h, firmware 0.34.0+) ----
// Whether this board has PSRAM: the sum of its regions, which walks no heap (rgb-heap-walk-glitch: never walk the PSRAM
// heap while an RGB panel is lit).
inline bool has_psram() {
#ifdef USE_ESP32
  return heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0;
#else
  return false;
#endif
}
// This board as tile_memory prices a tile: whether it has PSRAM, and the size of a tile and of its block of extras, which
// a board without PSRAM keeps inside the chip.
inline tile_memory::Board memory_board() { return {has_psram(), sizeof(Tile), sizeof(Extra), sizeof(page_protocol::Page)}; }
// What the tiles of the layout on the screen cost inside the chip, by the tile catalogue's prices (tile_memory.h).
inline size_t layout_cost() {
  const auto board = memory_board();
  size_t sum = 0;
  for (size_t i = 0; i < model.count && i < model.tiles.size(); ++i) {
    const auto &t = model.tiles[i];
    // A plugin's tile costs what its plugin says (its manifest's memory), and keeps its options and data as extras.
    if (t.is_plugin()) sum += plugin_host::bytes(t.entity) + (board.psram ? 0 : board.tile_bytes + board.extra_bytes);
    else sum += tile_memory::cost(t.entity, tile_memory::own_action(t.tap), tile_memory::own_line(t.subtitle), board);
  }
  // And its pages: a page's title, each item of its top bar that shows an entity (a text or a moment), its sections.
  for (const auto &page : model.page_data.records) {
    unsigned entities = 0;
    for (size_t i = 0; i < page.bar.count && i < page.bar.items.size(); ++i)
      entities += page.bar.items[i].kind == header_bar::Kind::text || page.bar.items[i].kind == header_bar::Kind::ago;
#ifdef SD_MOD_SECTIONS
    const unsigned sections = unsigned(page.sections.size());
#else
    const unsigned sections = 0;
#endif
    sum += tile_memory::page_cost(entities, sections, board);
  }
  return sum;
}
// The tile list and the page records keep the room of the most they held (layout_memory: a smaller layout reuses it), so
// after a big layout that room is out of the free heap without being in use. Where they live inside the chip (no PSRAM)
// it counts as room for tiles: the next layout takes it without asking the heap.
inline size_t spare_tiles() {
  if (has_psram()) return 0;
  const size_t tiles = model.tiles.capacity() > model.count ? model.tiles.capacity() - model.count : 0;
  const auto &pages = model.page_data.records;
  return tiles * sizeof(Tile) + (pages.capacity() > pages.size() ? pages.capacity() - pages.size() : 0) * sizeof(page_protocol::Page);
}
inline tile_memory::Window memory_window;
inline uint32_t memory_sampled_at = 0;
// When a tile last went without its extras for want of memory (page_receiver.cpp), 0 for never.
inline uint32_t memory_short_at = 0;
// When the layout on the screen landed (page_receiver.cpp), 0 while there is none: the room is sampled only once it has
// settled (tile_memory::SETTLE_MS).
inline uint32_t layout_landed_at = 0;
// One sample a minute, and only with a whole layout in place that has settled: halfway through a transfer, and in the first
// minute after one, the heap says nothing about what the screen has.
inline void sample_memory(uint32_t now) {
  if (!heap_room || !tile_memory::sample_due(now, layout_landed_at, memory_window.known(), memory_sampled_at)) return;
  if (transfer.begun && !transfer.active) return;
  memory_sampled_at = now;
  memory_window.add(tile_memory::room(heap_room() + spare_tiles(), layout_cost()));
}
// Whether the screen knows its room yet (firmware 0.51.0): until the first sample it reports none, and the app shows that
// it is still measuring instead of a room of nothing.
inline bool memory_known(uint32_t now) { sample_memory(now); return memory_window.known(); }
inline size_t memory_room(uint32_t now) { sample_memory(now); return memory_window.least(); }
// The room this moment, unsettled: what a screen that had to turn a layout down says before it ever had a sample.
inline size_t memory_room_now() { return heap_room ? tile_memory::room(heap_room() + spare_tiles(), layout_cost()) : 0; }
// Short of memory in the last ten minutes: the app says so beside the screen in the editor.
inline bool memory_short(uint32_t now) { return memory_short_at && now - memory_short_at < 600000; }
// Short of memory with a layout in place (page_receiver.cpp): the tiles off the glass give up their extras, which their
// next state brings back (the app sends every tile again at its keepalive), so the Wi-Fi link and the API keep room to
// breathe. Once a minute at most: a screen that stays short should not spend its loop on it.
inline uint32_t shed_at = 0;
inline void shed_extras() {
  const uint32_t now = esphome::millis();
  if (shed_at && now - shed_at < 60000) return;
  shed_at = std::max<uint32_t>(1, now);
  TileSet shown;
  for (const auto &w : widgets) if (w.tile && w.index < shown.size()) shown.set(w.index);
  size_t freed = 0;
  for (size_t i = 0; i < model.count && i < model.tiles.size(); ++i)
    if (!shown.test(i) && model.tiles[i].extra_ptr()) { model.tiles[i].set_extra(Extra()); ++freed; }
  ESP_LOGW("memory", "short of memory: %u tiles off the glass let go of their extras, %u B free", (unsigned) freed,
           (unsigned) (heap_room ? heap_room() : 0));
}
// A transfer that ran out of memory halfway (page_receiver.cpp): the tiles taken so far go, so the memory comes back and
// the screen says it has no layout instead of a half one, and the next hello starts afresh.
inline void abandon_layout() {
  ESP_LOGW("memory", "layout refused halfway: %u B free inside the chip", (unsigned) (heap_room ? heap_room() : 0));
  cancel_layout_input();
  model.begin(0, 1, "");
  transfer.begun = false;
  layout_landed_at = 0;
  memory_short_at = std::max<uint32_t>(1, esphome::millis());
  refresh_all(redraw_log::Why::layout_dropped_for_memory);
}
// The reply to a hello or a ping carries the memory figures (packages/core.yaml); a tile's state does not need them.
inline bool reply_memory = false;

using kept_pages::KEEP_RESERVE;  // PSRAM another kept page may never take (kept_pages.h)
// How many pages the board keeps beside the one on the glass: none without PSRAM (the CYD), every other page with it,
// and no new set once PSRAM runs short of KEEP_RESERVE (the sets already made stay in use). A host build keeps none
// unless kept_limit asks for some, so the renders in tools/render stay what they were.
inline size_t kept_capacity() {
#ifdef USE_ESP32
  size_t room = heap_caps_get_total_size(MALLOC_CAP_SPIRAM) ? kept_pages::MAX_KEPT : 0;
#elif defined(KEPT_PAGES_HOST)
  size_t room = kept_pages::MAX_KEPT;  // tools/render with KEPT_PAGES_HOST=1: the path a board with PSRAM takes
#else
  size_t room = 0;
#endif
  if (kept_limit >= 0) room = std::min<size_t>(kept_limit, kept_pages::MAX_KEPT);
  const unsigned pages = page_count();
  room = std::min<size_t>(room, pages > 1 ? pages - 1 : 0);
  size_t made = 0;
  while (made < room && kept_sets[made]) ++made;
  return room > made && psram_free() < KEEP_RESERVE ? made : room;
}
// A card and everything it made goes: its custom parts and their points, its energy scene, its plugin, its objects.
inline void drop_card(Widgets &w) {
  end_extra(w);
  if (w.energy) energy_view::release(w);
  if (w.calendar) calendar_view::release(w);
  if (w.meter) meter_view::release(w);
#ifdef SD_MOD_TEXT_CARD
  if (w.text) text_card_view::release(w);
#endif
#ifdef SD_MOD_TODO
  if (w.todo) todo_view::release(w);
#endif
#ifdef SD_MOD_VACUUM_CARD
  if (w.vacuum_face) vacuum_face::release(w);
#endif
  if (w.plugin) plugin_host::release(w);
  if (captured_slider && (captured_slider == w.slider || captured_slider == w.control_slider)) { captured_slider = nullptr; slider_changed = false; }
  if (w.tile) lv_obj_delete(w.tile);
  w = Widgets{};
}
// A kept set the board no longer needs (fewer pages, or a smaller limit) goes, cards and all.
inline void release_kept(size_t from) {
  for (size_t i = from; i < kept_sets.size(); ++i) {
    if (!kept_sets[i]) continue;
    for (auto &w : *kept_sets[i]) drop_card(w);
    kept_sets[i]->~CardSet();
    kept_free(kept_sets[i]);
    kept_sets[i] = nullptr;
    shelf.entries[i] = kept_pages::Shelf::Entry{};
  }
}
// Told when the grid changed (packages/core.yaml: the Screen layout sensor says so at once).
inline std::function<void()> grid_changed;
// Another grid for the way the glass hangs now, sent by ESP Screens with a layout (firmware 0.53.0+, page_receiver.cpp):
// every card goes, the kept ones too, as each was measured in a cell of the old grid, and the cards of the new one are
// made, all under the loading screen the layout brings. The caller has closed what was open (cancel_layout_input). The
// screen keeps the grid for its next start and reports it in its hello.
inline void regrid(size_t columns, size_t rows) {
  if (columns == grid.columns && rows == grid.rows) return;
  shelf.forget();
  release_kept(0);
  for (auto &w : widgets) drop_card(w);
#ifdef SD_MOD_SECTIONS
  ::sections::forget();
#endif
  grid = Grid{columns, rows};
  chosen_grids[canvas_upright ? 1 : 0] = grid;
  save_grids();
  grid_cells();
  make_cells(cell_icon_font, cell_circle);
  ESP_LOGI("grid", "grid %u x %u (%s)", (unsigned) columns, (unsigned) rows, canvas_upright ? "standing up" : "lying down");
  if (grid_changed) grid_changed();
}
inline CardSet *new_card_set() {
  void *memory = kept_allocate(sizeof(CardSet));
  if (!memory) return nullptr;
  auto *set = new (memory) CardSet();
  const Widgets *like = nullptr;
  for (const auto &w : widgets) if (w.tile) { like = &w; break; }
  if (!like) { set->~CardSet(); kept_free(memory); return nullptr; }
  for (size_t i = 0; i < CELLS_MAX; ++i) if (widgets[i].tile) make_card((*set)[i], i, *like);
  return set;
}
// `page` goes on the glass: its kept set comes back (or a set is made, or the page shown longest ago gives its cards
// up), and the cards on the glass go onto the shelf for the page leaving. What has to be drawn is in the answer.
inline kept_pages::Visit keep_page(int page, uint32_t leaving_synced) {
  shelf.capacity = kept_capacity();
  release_kept(shelf.capacity);
  auto visit = shelf.visit(page, applied_page, leaving_synced);
  if (visit.entry == kept_pages::NONE) return {};
  auto *&set = kept_sets[visit.entry];
  if (visit.build) {
    set = new_card_set();
    if (!set) { shelf.entries[visit.entry] = kept_pages::Shelf::Entry{}; return {}; }
    ESP_LOGI("kept", "cards made for another kept page (%u of %u), PSRAM free %u B", (unsigned) visit.entry + 1,
             (unsigned) shelf.capacity, (unsigned) psram_free());
  }
  for (size_t i = 0; i < CELLS_MAX; ++i) {
    std::swap(widgets[i], (*set)[i]);
    if ((*set)[i].tile) lv_obj_add_flag((*set)[i].tile, LV_OBJ_FLAG_HIDDEN);
  }
  return visit;
}
inline unsigned kept_count() { return (unsigned) shelf.pages(); }
// Nothing kept shows what it did (another layout): the sets stay for the pages to come, their cards drawn anew.
// What a card drew of its own goes now (its custom parts, their points, a calendar's events, a meter's texts): a card
// that next shows a tile without custom parts only hides them (hide_extra, made for paging a slot back and forth), so
// over a few layouts every kept card held a hidden one, and on a 4-inch Guition two pages added and taken away took
// the memory inside the chip from 49 to 20 KB until layouts were refused (2026-10-13). The card itself stays.
// The picture a card's own face draws beside its picture object (a robot's map on its larger tile), for the store's count.
inline lv_obj_t *face_picture(const Widgets &w) {
#ifdef SD_MOD_VACUUM_CARD
  return vacuum_face::picture(w);
#else
  (void) w;
  return nullptr;
#endif
}
inline void forget_kept() {
  shelf.forget();
#ifdef SD_MOD_SECTIONS
  // A new layout's sections are drawn anew when their pages are placed.
  ::sections::forget();
#endif
  for (auto *set : kept_sets) if (set) for (auto &w : *set) {
    end_extra(w);
    w.index = grid.max_tiles(); w.cached_active = -1; w.art_key.clear();
#if LV_USE_IMAGE
    // Their pictures go with what they showed: a picture object still pointing at a copy counts as drawing it, and the
    // store frees nothing a card draws, so the old layout's pictures stayed beside the new ones until the set showed
    // another page (GitHub #183). The cards are drawn anew with their own.
    for (lv_obj_t *picture : {w.picture, w.extra_mode == "media" ? w.parts[MEDIA_PICTURE] : nullptr, face_picture(w)})
      if (picture) { lv_image_set_src(picture, nullptr); lv_obj_add_flag(picture, LV_OBJ_FLAG_HIDDEN); }
    plugin_host::picture_let_go(w, nullptr);
    w.cover_shown.clear();
#endif
  }
}
inline void show_page(int &page, lv_obj_t *previous, lv_obj_t *next, lv_obj_t *number) {
  // The tile pages' bar is declared in the core and dressed by the pager every page shares (page_bar.h): the press
  // patch, and the chevrons' ink on the tiles' margin.
  if(!nav_prev){page_bar::patch(previous);page_bar::patch(next);}
  if(!nav_prev){page_bar::align(previous,true,grid_margin);page_bar::align(next,false,grid_margin);}
  nav_prev=previous;nav_next=next;nav_number=number;shown_page=&page;
  if(!nav_back_label && previous){
    nav_back_label=lv_label_create(previous);
    lv_obj_remove_flag(nav_back_label,LV_OBJ_FLAG_CLICKABLE);
    set_color(nav_back_label,LV_STYLE_TEXT_COLOR,theme::color(theme::INK));
  }
  int requested=page;
  page=std::clamp(page,0,int(page_count())-1);
  // A swipe past the first or last page: the page on screen is already right, so nothing is
  // drawn again. A layout change always lands in range or on a different page.
  if(requested!=page && page==applied_page)return;
  if(applied_page<0 || page==applied_page || !room_label){apply_page(page);return;}
  swipe_profile::begin(applied_page,page);
  swipe_profile::FillTimer timer;
  last_turn_ms=esphome::millis();
  live_tiles_halt();  // a live tile's picture never stays where its card left
  const auto kept=keep_page(page,glass_synced);
  applied_page=place_page(page,kept.kept);
  // A page with a title of its own carries it into the top bar with the same frame as its tiles, not a tick later.
  // The bar is measured again in that same frame (firmware 0.2.102): a name is given to a label that still has the
  // width of the page before it, so a longer name would stand there in dots until the next render said otherwise.
  if(room_label && model.configured && model.ready() && ha_connected() && feed_alive()){
    name_label(room_label,model.title_of(applied_page));
    render_header();
  }
  // Every card of the page, in this pass: the refresh that follows shows them together. A kept page draws only the
  // cards whose tile changed while it was away; after a minute (or a display setting) they all follow a frame later.
  const bool all=!kept.kept || changes.all_after(kept.synced);
  for(size_t slot=0;slot<grid.slots();++slot){
    const auto &w=widgets[slot];
    if(w.tile && w.index<model.count && (all || changes.tile_after(w.index,kept.synced)))render_slot(slot);
  }
  glass_synced=changes.last;
  swipe_profile::content_complete();
}
// A navigation tile (screen.page, firmware 0.2.62+): the page it names, kept within the pages the screen has.
inline void go_to_page(int page, bool remember) {
  if(!shown_page || !nav_number)return;
  if (!navigation_ready()) return;
  const int target=std::clamp(page,0,int(page_count())-1);
  if(remember)navigation_history.push(model.page_data,*shown_page,target);
  else navigation_history.clear();
  *shown_page=target;
  show_page(*shown_page,nav_prev,nav_next,nav_number);
}
inline void go_back() {
  if(!shown_page || !nav_number || !navigation_ready())return;
  *shown_page=navigation_history.pop(model.page_data,*shown_page);
  show_page(*shown_page,nav_prev,nav_next,nav_number);
}
// ---- Pages prepared ahead (firmware 0.3.2+) ----
// A page is built off the glass in one pass: its set of cards takes the glass's place with LVGL's invalidation off, is
// laid out by the grid (a hidden card gets no size, lv_grid.c skips LV_OBJ_FLAG_HIDDEN) and drawn into its objects,
// and goes back onto the shelf before anything reaches the panel. The glass keeps showing what it showed; the page on
// it gets its own cards back untouched. Its cards ask for no pictures (`warming`): a cover is fetched ahead later.
inline bool camera_visible();
inline bool card_open();
// Whether a kept page lacks a change: one of its tiles, everything or the time took a number after its cards were drawn.
inline bool page_behind(int page, const std::array<Placement, TILES_MAX> &placement) {
  const size_t at = shelf.held(page);
  if (at == kept_pages::NONE) return false;
  const uint32_t synced = shelf.entries[at].synced;
  if (changes.all_after(synced)) return true;
  for (size_t i = 0; i < model.count; ++i) if (placement[i].page == page && changes.tile_after(i, synced)) return true;
  return false;
}
// Builds `page` off the glass, or brings its kept cards up to date (only the ones behind are drawn).
inline bool warm_page(int page) {
  if (applied_page < 0 || page == applied_page || !room_label) return false;
  auto *display = lv_display_get_default();
  const int glass = applied_page;
  lv_display_enable_invalidation(display, false);
  warming = true;
  const auto visit = keep_page(page, glass_synced);
  if (visit.entry != kept_pages::NONE) {
    applied_page = place_page(page, visit.kept);
    const bool all = !visit.kept || changes.all_after(visit.synced);
    for (size_t slot = 0; slot < grid.slots(); ++slot) {
      const auto &w = widgets[slot];
      if (w.tile && w.index < model.count && (all || changes.tile_after(w.index, visit.synced))) render_slot(slot);
    }
    keep_page(glass, changes.last);  // the glass's own cards come back; the page stays on the shelf, drawn up to now
    applied_page = place_page(glass, true);
  }
  warming = false;
  lv_display_enable_invalidation(display, true);
  // The page bar was set for the other page and back: drawn again, the rest of the glass never changed. Its own keys,
  // never their parent: that is the whole screen, and a freshen drew the whole glass again each time (300 ms on a
  // 10-inch, and the sound that played meanwhile stuttered).
  for (lv_obj_t *part : {nav_prev, nav_next, nav_number})
    if (part) lv_obj_invalidate(part);
  return visit.entry != kept_pages::NONE;
}
// The next page to work on: first one that is neither on the glass nor kept (while there is room to keep it), then,
// unless `build_only`, a kept page that is behind, in turn so no page waits on a busy one.
inline int prepare_cursor = 0;
inline int next_to_prepare(bool build_only) {
  const int pages = (int) page_count();
  if (applied_page < 0 || pages < 2) return -1;
  if (shelf.pages() < kept_capacity())
    for (int page = 0; page < pages; ++page) if (page != applied_page && !shelf.keeps(page)) return page;
  if (build_only) return -1;
  std::array<Placement, TILES_MAX> placement;
  place(model, placement);
  for (int k = 0; k < pages; ++k) {
    const int page = (prepare_cursor + k) % pages;
    if (page != applied_page && page_behind(page, placement)) { prepare_cursor = page + 1; return page; }
  }
  return -1;
}
inline int next_to_prepare() { return next_to_prepare(false); }
// In the background a page is worked on only while nobody uses the screen: no finger for a moment, the pages standing
// still, no card, camera or slider in use. Building one takes 70 to 250 ms of the loop on an S3 (2026-09-26), bringing
// one up to date less; a kept page is brought up to date at most once a second, so a sensor that changes every second
// keeps the loop free most of the time.
constexpr uint32_t PREPARE_QUIET_MS = 1500;   // before a page is built in the background
constexpr uint32_t FRESHEN_QUIET_MS = 3000;   // before a kept page is brought up to date
constexpr uint32_t FRESHEN_GAP_MS = 1000;     // between two kept pages brought up to date
// The "Preparing pages" screen stays at most this long after the last page is built, while the data ESP Screens sends
// after a layout (a graph's history, a player's details) lands on the cards it belongs to.
constexpr uint32_t SETTLE_MAX_MS = 3000;
inline bool prepare_idle(uint32_t now, uint32_t quiet) {
  if (captured_slider || card_open() || camera_visible()) return false;
  if (!camera_view::settled(now, last_turn_ms) || now - touched_at < quiet) return false;
  auto *input = lv_indev_get_next(nullptr);
  return !(input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED);
}
inline uint32_t prepare_built_at = 0, last_freshen = 0;
inline void prepare_done() {
  const bool shown = preparing.foreground;
  preparing.active = preparing.foreground = false;
  if (preparing.timer) lv_timer_set_period(preparing.timer, 300);  // from now on: kept pages up to date, when idle
  ESP_LOGI("kept", "pages prepared: %u of %u, PSRAM free %u B", preparing.done, preparing.total, (unsigned) psram_free());
  // The render takes the "Preparing pages" screen away; the header alone, as nothing on the cards changed.
  if (shown) refresh_header_only();
}
inline void prepare_step(lv_timer_t *) {
  if (protocol_problem != ProtocolProblem::none || !transfer.whole(model.ready())) return;
  const uint32_t now = esphome::millis();
  int page = next_to_prepare(true);
  if (page >= 0) {
    if (!preparing.foreground && !prepare_idle(now, PREPARE_QUIET_MS)) return;
    warm_page(page);
    ++preparing.done;
    ESP_LOGI("kept", "page %d prepared in %u ms (%u of %u)", page + 1, (unsigned) (esphome::millis() - now), preparing.done, preparing.total);
    if (preparing.foreground) prepare_status();
    return;
  }
  if (preparing.foreground) {
    // Every page is built: bring up to date what the data after the layout changed, for a moment at most.
    if (!prepare_built_at) prepare_built_at = now;
    page = next_to_prepare();
    if (page < 0 || now - prepare_built_at > SETTLE_MAX_MS) { prepare_done(); return; }
    warm_page(page);
    ESP_LOGD("kept", "page %d brought up to date in %u ms", page + 1, (unsigned) (esphome::millis() - now));
    return;
  }
  if (preparing.active) prepare_done();
  if (now - last_freshen < FRESHEN_GAP_MS || !prepare_idle(now, FRESHEN_QUIET_MS)) return;
  page = next_to_prepare();
  if (page < 0) return;
  warm_page(page);
  last_freshen = esphome::millis();
  ESP_LOGD("kept", "page %d brought up to date in %u ms", page + 1, (unsigned) (last_freshen - now));
}
// A layout was applied: build its other pages under the "Preparing pages" screen, which goes the moment they are
// ready, so the glass shows the loading screen and then the finished layout and nothing in between (every layout;
// before, only the first since the start was, and a save in the editor flickered). From then on
// kept pages are brought up to date while the screen is idle. A board that keeps no pages (the CYD) builds each page
// when it is shown, as before.
inline void prepare_start() {
  const unsigned pages = page_count();
  if (!room_label || applied_page < 0 || pages < 2 || !kept_capacity()) return;
  preparing.active = true;
  preparing.foreground = true;
  preparing.done = 0;
  preparing.total = pages - 1;
  prepare_built_at = 0;
  if (!preparing.timer) preparing.timer = lv_timer_create(prepare_step, 10, nullptr);
  lv_timer_set_period(preparing.timer, 10);
  lv_timer_reset(preparing.timer);
  ESP_LOGI("kept", "preparing %u pages before the first page opens", preparing.total);
  prepare_status();
}
// Another layout is on its way: its pages are built once it is complete (prepare_start).
inline void prepare_cancel() {
  preparing.active = preparing.foreground = false;
  if (preparing.timer) lv_timer_set_period(preparing.timer, 300);
}
// The Page buttons setting changed (firmware 0.2.69+): the same page again, with the bar and the cards in their new places.
// The settings are applied every minute; only a real change places the page again (firmware 0.3.2+), and then every
// card, kept ones too, is measured anew for the room the bar leaves.
inline int applied_buttons=-1;
inline void page_buttons_changed() {
  if(!shown_page || !nav_number || applied_page<0 || applied_buttons==(page_buttons?1:0))return;
  applied_buttons=page_buttons?1:0;
  each_card([](Widgets &w){w.cached_active=-1;w.panel_dirty=true;});
  apply_page(applied_page);
}

// Loop pages changed: the chevrons of the page on the glass say so at once.
inline int applied_loop=-1;
inline void loop_pages_changed() {
  const int loop=settings_screen::loop_pages?1:0;
  if(!shown_page || !nav_number || applied_page<0 || applied_loop==loop)return;
  applied_loop=loop;
  show_page_keys(applied_page,applied_bar && model.page_data.detail(applied_page));
}

#ifdef SWIPE_PROFILE
inline unsigned swipe_test_left=0, swipe_test_back=0;
inline bool swipe_test_returning=false;
inline lv_timer_t *swipe_test_timer=nullptr;
inline void swipe_test_step(lv_timer_t *timer) {
  if(!shown_page || !swipe_test_left || page_count()<2){lv_timer_pause(timer);swipe_test_left=0;ESP_LOGI("swipe_prof","swipe test finished");return;}
  int pages=page_count(),from=*shown_page;
  *shown_page=swipe_test_returning?from-1:(from+1<pages?from+1:0);
  if(*shown_page<0)*shown_page=pages-1;
  show_page(*shown_page,nav_prev,nav_next,nav_number);
  if(swipe_test_back && !swipe_test_returning){swipe_test_returning=true;lv_timer_set_period(timer,swipe_test_back);return;}
  swipe_test_returning=false;--swipe_test_left;
  lv_timer_set_period(timer,lv_timer_get_user_data(timer)?(uint32_t)(uintptr_t)lv_timer_get_user_data(timer):1200);
}
inline void swipe_test(unsigned count, unsigned interval_ms, unsigned back_ms) {
  swipe_test_left=std::min(count,200u);swipe_test_back=back_ms;swipe_test_returning=false;
  interval_ms=std::clamp(interval_ms,200u,10000u);
  if(!swipe_test_timer)swipe_test_timer=lv_timer_create(swipe_test_step,interval_ms,(void*)(uintptr_t)interval_ms);
  lv_timer_set_user_data(swipe_test_timer,(void*)(uintptr_t)interval_ms);
  lv_timer_set_period(swipe_test_timer,interval_ms);lv_timer_reset(swipe_test_timer);lv_timer_resume(swipe_test_timer);
  ESP_LOGI("swipe_prof","swipe test: %u page switches every %u ms, back after %u ms",swipe_test_left,interval_ms,back_ms);
}
#endif
inline uint32_t last_live_second=0;
inline int last_clock_minute=-2;
inline bool was_fresh=false;
inline void saver_wish_tick(uint32_t now);
inline void saver_motion_tick(uint32_t now);
inline void tick() {
  // A finger's wish on the screensaver's player goes out, or comes back without a word (saver_wish).
  saver_wish_tick(esphome::millis());
  // A photo of the screensaver that moves takes its next pixel.
  saver_motion_tick(esphome::millis());
#ifndef ESP_SCREEN_HOST
  // Asked to hang the other way (hang): the answer went out, the preferences are written, the screen starts again.
  if (turn_restart_at && esphome::millis() - turn_restart_at > 500) { turn_restart_at = 0; esphome::App.safe_reboot(); }
#endif
  // The network lost or found again changes the whole glass: the Wi-Fi message over everything, or the pages back.
  static bool wifi_shown = false;
  if (const bool shown = wifi_status::problem().shown; shown != wifi_shown) {
    wifi_shown = shown;
    if (shown) ESP_LOGW("wifi_status", "No Wi-Fi: the glass says how to fix it");
    else ESP_LOGI("wifi_status", "Wi-Fi back: the pages again");
    if (room_label) { mark_all(redraw_log::Why::wifi); render(room_label); } else refresh_all(redraw_log::Why::wifi);
  }
  if(detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) && detail_tile()){
    auto &t=*detail_tile();bool waiting=t.loading(esphome::millis());
    // The history the card waits for: drawn once it is here (a finger on the screen holds that back), asked for
    // again every 30 s, and after 8 s without it (an app from before 0.2.59, Home Assistant away) the card says so.
    if(history_chart.status&&!history_chart.ready){
      const uint32_t now=esphome::millis();
      if(history_fits(t))refresh_detail(detail_index);
      else if(now-history_asked_at>30000)history_request(t.entity,history_hours);
      else if(now-history_asked_at>8000)label(history_chart.status,tr(txt::history_unavailable));
    }
    // The card's keys wait with it; only a change touches them, and then the parts that fade for a reason of their own
    // paint that again (docs/CARD_PARTS.md).
    const bool blocked=waiting||!fresh()||!t.available();
    if(blocked!=card_blocked){
      card_blocked=blocked;
      for(unsigned i=0;i<detail_action_count;++i){if(blocked)lv_obj_add_state(detail_actions[i],LV_STATE_DISABLED);else lv_obj_remove_state(detail_actions[i],LV_STATE_DISABLED);}
      card_repaint(t);
    }
    std::string status=waiting?std::string(tr(t.confirmed?txt::tile_confirmed:txt::tile_command_sent)):card_status(t,detail_status_brief);
    if(detail_status)label(detail_status,waiting?status:screen_text::with_unit(status,t.unit));
    // The vacuum card lays its state out with the room and battery beside it, so a new text draws the
    // card again; once Home Assistant answered, the new state says enough.
    if(detail_badge_status && t.domain()=="vacuum"){
      status=vacuum_badge_text(t);
      if(status!=lv_label_get_text(detail_badge_status))refresh_detail(detail_index);
    }else if(detail_badge_status)label(detail_badge_status,status);
    if(detail_switch && !lv_obj_has_state(detail_switch,LV_STATE_PRESSED)){
      if(t.state=="on")lv_obj_add_state(detail_switch,LV_STATE_CHECKED);
      else lv_obj_remove_state(detail_switch,LV_STATE_CHECKED);
    }
  }
  if(!enabled)return;
  // A failed update says so for five seconds, then the pages come back (ota_status.h).
  if(ota_status::now.phase==ota_status::Phase::failed){
    static uint32_t failed_at=0;
    if(!failed_at)failed_at=esphome::millis()|1;
    else if(esphome::millis()-failed_at>5000){failed_at=0;ota_status::now={};ota_forget();refresh_all(redraw_log::Why::update_status_gone);}
  }
  // The starting screen follows every step as it happens (firmware 0.38.0): drawn again whenever what it says changes,
  // the seconds of a step that takes long included.
  if(room_label && !model.configured && model.refusal.empty() && protocol_problem==ProtocolProblem::none && !wifi_shown){
    static std::string said;
    const auto view=boot_view(esphome::millis());
    std::string now_said=view.title+'\x1f'+view.facts+'\x1f'+view.hint;
    for(const auto &step:view.steps)now_said+='\x1f'+step;
    if(now_said!=said || !boot_panel){said=std::move(now_said);boot_status(lv_obj_get_parent(room_label),view.title.c_str(),view.steps.empty(),false,view.facts,view.hint,std::string(),view.steps);}
  }
  // "This screen" on the settings page tells its network and links again every two seconds while it is open.
  if(settings_screen::root && settings_screen::current_page==4){
    static uint32_t told=0;
    if(esphome::millis()-told>2000){told=esphome::millis();settings_screen::refresh();}
  }
  // The Wi-Fi item follows the signal (firmware 0.38.0) and the battery item its level and charging (firmware 0.41.0):
  // looked at every five seconds, drawn when what one of them says changes.
  if(const auto *bar=shown_bar()){
    static uint32_t looked=0;
    static std::string said;
    if(esphome::millis()-looked>5000){
      looked=esphome::millis();
      const auto device=header_device();
      std::string now_said;
      for(size_t i=0;i<bar->count;++i){
        const auto kind=bar->items[i].kind;
        if(kind!=header_bar::Kind::wifi && kind!=header_bar::Kind::battery && kind!=header_bar::Kind::plugin)continue;
        const auto now_shown=header_bar::device_item(bar->items[i],device);
        now_said+=std::to_string(now_shown.shown)+':'+std::to_string(now_shown.icon)+':'+now_shown.text+':'+std::to_string(now_shown.has_color?now_shown.color:0)+'\x1f';
      }
      if(now_said!=said){said=std::move(now_said);refresh_header_only();}
    }
  }
  media_library::tick(esphome::millis());
  // Only the cards that change are drawn again: a clock or a finished command redraws its own card.
  bool redraw=false;
  auto card=[&](size_t index){ mark_tile(index, redraw_log::TileWhy::tick); redraw=true; };
  // HA dropping or returning and the feed timing out change every card at once.
  bool now_fresh=fresh();
  if(now_fresh!=was_fresh){was_fresh=now_fresh;ESP_LOGI("render","the feed is %s (Home Assistant %s, the app's feed %s, protocol %s, transfer %s/%s, model %s)",now_fresh?"fresh again":"no longer fresh",ha_connected()?"connected":"away",feed_alive()?"alive":"silent",protocol_problem==ProtocolProblem::none?"ok":"problem",transfer.active?"active":"inactive",transfer.begun?"begun":"not begun",model.ready()?"ready":"not ready");mark_all(now_fresh?redraw_log::Why::feed_fresh_again:redraw_log::Why::feed_no_longer_fresh);redraw=true;}
#ifdef USE_API_HOMEASSISTANT_ACTION_RESPONSES
  expire_calls(esphome::millis());
#endif
  alarm_tick();
  lock_tick();
  for(size_t i=0;i<model.tiles.size();++i){
    auto &t=model.tiles[i];
    if(t.refused_at && esphome::millis()-t.refused_at>=4000){t.refused_at=0;card(i);}
    // A held slider whose light never got there shows what Home Assistant last reported again.
    if(std::isfinite(t.slider_sent) && !t.slider_holding(esphome::millis())){t.release_slider();card(i);}
    // A cover that gave no sign of getting where it was sent shows where Home Assistant last said it is.
    if(t.travelling() && !cover_travel::holding(t.travel,esphome::millis())){t.release_travel();card(i);}
    if(!t.pending || t.waiting(esphome::millis()))continue;
    end_wait(i);card(i);
  }
  // A -/+ edit goes out as one call once the finger rests; a value HA never reports is dropped after a while.
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];if(!std::isfinite(t.edit_value)&&!std::isfinite(t.edit_high))continue;
    uint32_t now=esphome::millis();
    if(!t.edit_sent){
      if(now-t.edit_since<700 || t.waiting(now))continue;
      auto a=tile_controls::edit_action(t,t.edit_value);
      // The number already shows the value: nothing greys or waits while Home Assistant takes it (docs/OPTIMISTIC.md).
      if(a.valid()){t.edit_sent=true;t.edit_since=now;action(a.service,t.entity,a.key,a.value,true,a.key2,a.value2,false);}else{t.edit_value=NAN;t.edit_high=NAN;}
    }else if(now-t.edit_since>10000){t.edit_value=NAN;t.edit_high=NAN;card(i);}
  }
  // Running timers advance once per second without any HA traffic; clocks show hours and minutes,
  // so they are drawn again only when the minute (or the time's validity) changes.
  uint32_t second=esphome::millis()/1000;
  if(second!=last_live_second){
    last_live_second=second;
    // Every plugin card on the glass counts on its own clock (docs/PLUGINS.md).
    plugin_host::tick_cards(now_epoch());
    // The media card's bar runs on while the track plays (firmware 0.2.64+). A wait of its face that ran out paints the
    // card again (media_face_follow): a cover that waited for its colour long enough is asked for without it, and an old
    // cover whose next one did not come goes.
    if(detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) && detail_index<model.count && model.tiles[detail_index].domain()=="media_player"){
      if(media_face.recheck && static_cast<int32_t>(esphome::millis()-media_face.recheck)>=0){media_face.recheck=0;refresh_detail(detail_index);}
      if(media_progress_fill && !media_seeking)media_bar_now(model.tiles[detail_index]);
    }
    auto now=now_time?now_time():esphome::ESPTime{};
    int minute=now.is_valid()?now.day_of_year*1440+now.hour*60+now.minute:-1;
    bool new_minute=minute!=last_clock_minute;last_clock_minute=minute;
    if(new_minute)calendar_view::minute();
    for(size_t slot=0;slot<grid.slots();++slot){
      auto &w=widgets[slot];if(!w.tile || w.index>=model.count || lv_obj_has_flag(w.tile,LV_OBJ_FLAG_HIDDEN))continue;
      const auto &t=model.tiles[w.index];
      if(((t.is_clock() || t.is_bedside() || t.domain()=="calendar") && new_minute) || (t.domain()=="timer" && t.state=="active") || (t.domain()=="sun" && second%60==0))card(w.index);
      // An alarm's delay counts down on its tile; its heartbeat stops while the screen sleeps and starts when it wakes.
      if(t.domain()=="alarm_control_panel"){if(alarm_left(t))card(w.index);alarm_tile_look(slot,&t);}
      if(t.domain()=="lock")alarm_tile_look(slot,&t);
      // A favourite whose start never came stops saying it starts (firmware 0.24.0+).
      if(t.favorite()&&w.index<TILES_MAX&&favorite_started_at[w.index]&&!favorite_starting(w.index,t))card(w.index);
      // A media tile over the whole page: its bar runs on while the track plays (firmware 0.2.64+).
      if(w.extra_mode=="media" && w.extra && !lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN) && w.parts[5] && !lv_obj_has_flag(w.parts[5],LV_OBJ_FLAG_HIDDEN) && media_card::has_track(t.state))media_progress(t,w.parts[5],w.parts[6],w.media_bar_w);
      // A cover kept while the next one was on its way, whose wait ran out: the card draws itself again without it. A
      // stream that just became one (media_live) draws it again with "Live".
      if(w.extra_mode=="media" && ((w.cover_hold && static_cast<int32_t>(esphome::millis()-w.cover_hold)>=0) || media_live(t)!=w.media_live))refresh_tile(w.index, redraw_log::TileWhy::picture);
      // The second hand moves on its own: only its line is redrawn, and it hides during standby. Only while the
      // slot's parts are a dial: right after a page switch the slot already names the clock while its parts still
      // belong to the card drawn before (a forecast's hour labels take part 18 too), until the fill draws the dial.
      // A single dial is drawn as "calendar", a wide or full one as "analog"; firmware 0.2.62-0.2.64 moved only the
      // latter, so the hand of a single clock stood still (0.2.65). Part 18 must be the hand's own line either way.
      else if(w.parts[18] && lv_obj_check_type(w.parts[18],&lv_line_class) && w.points &&
              (((w.extra_mode=="analog" || w.extra_mode=="calendar") && t.display=="analog") || (w.extra_mode=="calm" && t.display=="dial")) && t.is_clock())second_hand(w,now);
    }
  }
  if(redraw && refresh)refresh();
}
// A change of look (Dark mode). The paints follow by themselves (theme::set_dark); what the tiles, the top bar and an
// open card painted in code is drawn again here, in the same pass, so no frame shows half of each look.
inline void restyle() {
  each_card([](Widgets &w) { w.cached_active = -1; w.panel_dirty = true; });
  if (nav_number && applied_bar && applied_page >= 0)
    page_bar::dots(nav_number, model.page_data.ordinal(applied_page), model.page_data.count());
  header_renderer.restyle();
#ifdef SD_MOD_SECTIONS
  ::sections::restyle();
#endif
  if (room_label) { mark_all(redraw_log::Why::look_changed); render(room_label); }
  if (detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN) && detail_tile()) show_detail(detail_index);
  media_library::restyle();
}
}

// ---- Camera images (firmware 0.2.57+) ----
// A camera or image tile, and an alert's image, open the camera full screen: the image as large as fits, the round back
// key at the top left like on every card, the name beside it. ESP Screen Manager fetches the snapshot, sizes it for this
// screen and serves it on its own port; the loader decides when to ask for a link and when to load it again
// (picture_loader.h, with the rhythm's constants of camera_view.h). The
// board binds the two online_images (the full view and the alert's frame) through ImageHooks; a board without them (the
// CYD) never opens the view. Nothing here exists while no camera is open, apart from the alert's small frame.
#include "camera_view_lvgl.h"
#include "picture_store_lvgl.h"
#include "tile_picture_lvgl.h"
#include "live_view_lvgl.h"
#include "live_spots_lvgl.h"
#include "full_view_lvgl.h"
#include "pressure_lvgl.h"
#include "camera_answer_lvgl.h"
#include "picture_rounds_lvgl.h"
#include "saver_state_lvgl.h"
namespace runtime_tiles {
#ifdef SD_MOD_CLOCK_FACES
// The clock's faces of the module (module_clock_faces.cpp, a compilation unit of its own).
}  // namespace runtime_tiles
#include "module_clock_faces.h"
namespace runtime_tiles {
#endif
}  // namespace runtime_tiles
#include "saver_lvgl.h"
namespace runtime_tiles {
// ---- The acknowledgement of a swipe (firmware 0.2.100+) ----
// A white haze at the edge the gesture came from: an oval, half of it off the glass, that lights up the moment the
// swipe is taken and fades out in a quarter of a second. One object with one property animated and nothing else on
// the page moving, so it costs a blend over its own corner and no redraw of the tiles. The colour is the light the
// glass already makes: white on the light look, and on the dark one too, where it reads as a glow instead of a haze.
enum class Edge : uint8_t { left, right, bottom };
inline lv_obj_t *swipe_glow_obj = nullptr;
// The haze at its brightest, before the fade. White on a light page barely lifts its grey, so there it starts at
// full and the gradient does the softening; on the dark look white is loud, so it starts at little over half.
// Measured on the host render: white at 43 % over the light page is invisible.
inline int glow_peak() { return theme::dark ? 150 : 255; }
// It stays at full for a breath and then takes its time: bright enough to notice out of the corner of an eye, and
// slow enough on the way out to read as the page coming in rather than a blink.
constexpr int GLOW_HOLD_MS = 90, GLOW_MS = 420;
inline void swipe_glow(Edge edge) {
  if (!room_label) return;
  auto *page = lv_obj_get_parent(room_label);
  // The page's own glass, the way the top bar measures it, not the display: a screen that was turned, or built
  // standing up, then lights the edge the finger really came from.
  const int width = lv_obj_get_width(page), height = lv_obj_get_height(page);
  if (width <= 0 || height <= 0) return;
  if (!swipe_glow_obj) {
    swipe_glow_obj = lv_obj_create(page);
    lv_obj_remove_style_all(swipe_glow_obj);
    lv_obj_remove_flag(swipe_glow_obj, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(swipe_glow_obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(swipe_glow_obj, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_add_flag(swipe_glow_obj, LV_OBJ_FLAG_HIDDEN);
    // An oval of white that thins out towards the middle of the glass: the soft edge is the gradient, not a blur,
    // which the software renderer would pay for by the pixel.
    lv_obj_set_style_radius(swipe_glow_obj, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(swipe_glow_obj, lv_color_white(), 0);
    lv_obj_set_style_bg_grad_color(swipe_glow_obj, lv_color_white(), 0);
  }
  // Half of the oval lies off the glass, so what shows is an arc coming in from that edge: as wide as a third of
  // the glass at a side, and as tall as a third of it along the bottom.
  const int along = edge == Edge::bottom ? width * 7 / 10 : width * 7 / 20;
  const int across = edge == Edge::bottom ? height * 7 / 20 : height * 7 / 10;
  if (edge == Edge::bottom) {
    lv_obj_set_size(swipe_glow_obj, along, across);
    lv_obj_set_pos(swipe_glow_obj, (width - along) / 2, height - across / 2);
    lv_obj_set_style_bg_grad_dir(swipe_glow_obj, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_main_opa(swipe_glow_obj, LV_OPA_TRANSP, 0);
    lv_obj_set_style_bg_grad_opa(swipe_glow_obj, LV_OPA_COVER, 0);
  } else {
    lv_obj_set_size(swipe_glow_obj, along, across);
    lv_obj_set_pos(swipe_glow_obj, edge == Edge::left ? -along / 2 : width - along / 2, (height - across) / 2);
    lv_obj_set_style_bg_grad_dir(swipe_glow_obj, LV_GRAD_DIR_HOR, 0);
    lv_obj_set_style_bg_main_opa(swipe_glow_obj, edge == Edge::left ? LV_OPA_COVER : LV_OPA_TRANSP, 0);
    lv_obj_set_style_bg_grad_opa(swipe_glow_obj, edge == Edge::left ? LV_OPA_TRANSP : LV_OPA_COVER, 0);
  }
  const int peak = glow_peak();
  lv_obj_set_style_bg_opa(swipe_glow_obj, static_cast<lv_opa_t>(peak), 0);
  lv_obj_remove_flag(swipe_glow_obj, LV_OBJ_FLAG_HIDDEN);
  lv_obj_move_foreground(swipe_glow_obj);
  lv_anim_t fade;
  lv_anim_init(&fade);
  lv_anim_set_var(&fade, swipe_glow_obj);
  lv_anim_set_values(&fade, peak, 0);
  lv_anim_set_duration(&fade, GLOW_MS);
  lv_anim_set_delay(&fade, GLOW_HOLD_MS);
  // Slow at the start, quick at the end: the haze holds its light and then goes, instead of dropping away at once.
  lv_anim_set_path_cb(&fade, lv_anim_path_ease_in);
  lv_anim_set_exec_cb(&fade, [](void *object, int32_t value) {
    lv_obj_set_style_bg_opa(static_cast<lv_obj_t *>(object), static_cast<lv_opa_t>(value), 0);
  });
  lv_anim_set_completed_cb(&fade, [](lv_anim_t *) {
    if (swipe_glow_obj) lv_obj_add_flag(swipe_glow_obj, LV_OBJ_FLAG_HIDDEN);
  });
  lv_anim_start(&fade);
}

namespace touch_input {
// A finger arrived or left: the standby clock, the "back to page 1" clock and `touch_down`.
inline std::function<void(bool down)> contact;
// A touchscreen's report in the screen's own coordinates: ESPHome's LvglComponent::rotate_coordinates,
// which already carries the board's quarter turn and the turn the user chose.
inline std::function<void(int &x, int &y)> to_screen;
// Why no edge swipe may do anything now, or nullptr when one may. Reads what only the YAML knows (a dimmed screen, a
// calibration, an alert).
inline std::function<const char *()> swipe_blocked;
// Whether a card is open (what only the YAML knows): a page stays where it is under it.
inline std::function<bool()> card_open;
// One page further or back, and draw it.
inline std::function<void(int target)> turn_page;
// Both capacitive edge swipes and resistive LVGL gestures resolve one target
// here. An edge or excluded page neither glows nor logs a move that did not run.
inline bool step_page(int step) {
  if (!navigation_ready() || !shown_page || !turn_page) return false;
  const int target = sequential_page(*shown_page, step);
  if (target == *shown_page) return false;
  ESP_LOGI("touch", "page swipe: page %d -> %d", *shown_page, target);
  swipe_glow(step > 0 ? Edge::right : Edge::left);
  turn_page(target);
  return true;
}

// The same point as the screen draws with, so a band along the glass means the glass and not the panel.
inline void screen_point(int &x, int &y) { if (to_screen) to_screen(x, y); }

// Whether the finger came down on a slider or a dial: a drag that starts there is that control's, also in the band
// along an edge (on small glass a lamp's brightness bar reaches down into the bottom one). The camera and other
// views over everything live on the top layer, the rest on the page.
inline bool starts_on_control(int x, int y) {
  lv_point_t point{x, y};
  lv_obj_t *hit = lv_indev_search_obj(lv_layer_top(), &point);
  if (!hit || hit == lv_layer_top()) hit = lv_indev_search_obj(lv_screen_active(), &point);
  for (auto *o = hit; o; o = lv_obj_get_parent(o))
    if (lv_obj_check_type(o, &lv_slider_class) || lv_obj_check_type(o, &lv_arc_class)) return true;
  return false;
}

}  // namespace touch_input
}  // namespace runtime_tiles
// The modules of the tier (docs/MODULES.md): only their define brings their code in, so a lite screen has none of it.
#define SMART_DISPLAY_MODULE_SITE
#ifdef SD_MOD_DOCK
#include "module_dock.h"
#endif
#ifdef SD_MOD_SECTIONS
#include "module_sections.h"
#endif
#undef SMART_DISPLAY_MODULE_SITE
namespace runtime_tiles {
// The page dots of the tile pages' bar: a key that opens the Dock on a screen with the module, nothing without it.
inline void page_dots_open(lv_obj_t *number) {
#ifdef SD_MOD_DOCK
  dock::dots_open(number);
#else
  (void) number;
#endif
}
namespace touch_input {

// The edge swipe of every board, in the touchscreen's own coordinates: where a touch starts, where it goes, and when
// it ends. The capacitive boards feed it from pressed, moved and released below; the resistive ones call these three
// from their own triggers (features/resistive-touch.yaml), where only the top and the bottom band are armed.
// Where and when the touch started, on the glass: the Dock rises from there under the finger.
inline int edge_start_y = 0;
inline uint32_t edge_pressed_ms = 0;
inline void edge_press(int x, int y) {
  int sx = x, sy = y;
  screen_point(sx, sy);
  edge_start_y = sy;
  edge_pressed_ms = lv_tick_get();
  screen_input::edge_swipe.begin(sx, sy, overlay_card::screen_width(), overlay_card::screen_height());
  if (screen_input::edge_swipe.armed() && starts_on_control(sx, sy)) {
    ESP_LOGI("touch", "edge swipe off: the touch starts on a slider");
    screen_input::edge_swipe.end();
  }
}

inline void edge_move(int x, int y) {
  int sx = x, sy = y;
  screen_point(sx, sy);
  using Gesture = screen_input::EdgeSwipe::Gesture;
#ifdef SD_MOD_DOCK
  // The finger that opened the Dock carries it until it lets go.
  if (dock::lifting()) { dock::lift_move(sy); return; }
#endif
  const auto gesture = screen_input::edge_swipe.update(sx, sy);
  if (gesture == Gesture::none) return;
#ifdef SD_MOD_DOCK
  // While the Dock is open a page turns only by a tap in it, and up from the bottom once more goes home: one swipe up
  // shows the Dock, a second one goes further out, as on a tablet. The Dock closes on the way (go_home closes every card).
  if (dock::open() && gesture != Gesture::settings) {
    screen_input::touch_guard.consume();
    if (gesture == Gesture::home) {
      ESP_LOGI("touch", "edge swipe up over the Dock: back home");
      for (auto *indev = lv_indev_get_next(nullptr); indev; indev = lv_indev_get_next(indev)) lv_indev_wait_release(indev);
      swipe_glow(Edge::bottom);
      if (back_home) back_home();
      else dock::close();
    }
    return;
  }
#endif
  // Up from the bottom and down from the top work wherever the person is, over a card, a camera or the settings page,
  // as on a phone (firmware 0.28.0+). A page turns only over the tiles.
  const bool page = gesture == Gesture::previous || gesture == Gesture::next;
  const bool detail_open = detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN);
  const char *held = swipe_blocked ? swipe_blocked() : nullptr;
  const char *blocked = !enabled                ? "no runtime tiles"
                      : !swipe_pages            ? "setting off"
                      : captured_slider         ? "a slider is being dragged"
                      : held                    ? held
                      : !page                   ? nullptr
                      : !navigation_ready()     ? "configuration not ready"
                      : camera_visible()        ? "camera open"
                      : detail_open             ? "detail card open"
                      : card_open && card_open() ? "card open"
                      : settings_screen::visible() ? "settings page open"
                      : nullptr;
  if (blocked) { ESP_LOGI("touch", "edge swipe ignored: %s", blocked); return; }
  screen_input::touch_guard.consume();
  for (auto *indev = lv_indev_get_next(nullptr); indev; indev = lv_indev_get_next(indev)) lv_indev_wait_release(indev);
  // Up from the bottom edge closes whatever is open and goes home (firmware 0.2.100+, over everything 0.28.0+), in
  // from a side edge is one page. Either way the edge it came from lights up for a moment, so the gesture is answered
  // before the new page is drawn.
  if (gesture == Gesture::home) {
#ifdef SD_MOD_DOCK
    // Full: up from the bottom opens the dock, over whatever is open, once the pages are there to show.
    if (navigation_ready() && dock::show(true, edge_start_y, sy, edge_pressed_ms)) {
      // No glow: the drawer under the finger is the answer, and a haze fading under it would draw its area anew.
      ESP_LOGI("touch", "edge swipe up: dock");
      return;
    }
#endif
    ESP_LOGI("touch", "edge swipe up: close everything, back home");
    swipe_glow(Edge::bottom);
    if (back_home) back_home();
    return;
  }
  // Down from the top edge opens the settings page (GitHub #133); holding the top bar still does too. Whatever card
  // was open closes first, as it does when the page opens from that hold.
  if (gesture == Gesture::settings) {
    if (settings_screen::visible()) return;
    if (dismiss) dismiss();
    if (settings_screen::may_open && !settings_screen::may_open()) { ESP_LOGI("touch", "edge swipe down: settings page may not open"); return; }
    ESP_LOGI("touch", "edge swipe down: settings page");
    settings_screen::open();
    return;
  }
  step_page(gesture == Gesture::next ? 1 : -1);
}

inline void edge_release() {
#ifdef SD_MOD_DOCK
  dock::lift_release();
#endif
  if (screen_input::edge_swipe.armed() && screen_input::edge_swipe.inward() > 0)
    ESP_LOGI("touch", "edge swipe not fired: %d px travelled, %d px across", screen_input::edge_swipe.inward(), screen_input::edge_swipe.sideways());
  screen_input::edge_swipe.end();
}

inline void pressed(int x, int y, int id, bool calibrating) {
  if (contact) contact(true);
  pressure_finger(true, false);
  screen_input::touch_guard.begin(esphome::millis(), x, y, id);
  int sx = x, sy = y;
  screen_point(sx, sy);
  edge_press(x, y);
  ESP_LOGI("touch", "press x=%d y=%d id=%d test=%d screen=%d,%d", x, y, id, calibrating ? 1 : 0, sx, sy);
}

// One contact of one report. Only the contact that started the touch counts.
inline void moved(int x, int y, int id, int state) {
  if (contact) contact(true);
  touched_at = esphome::millis();
  // Trace every sample of an edge touch: the log then shows how often the panel delivers.
  if (screen_input::edge_swipe.armed()) ESP_LOGI("touch", "swipe id=%d st=%d x=%d y=%d", id, state, x, y);
  // The stray (0, 0) contact (screen_input::GhostTouch) is not where the finger went.
  if (x == 0 && y == 0) return;
  screen_input::touch_guard.update(x, y, id);
  if (id != screen_input::touch_guard.contact()) return;
  // Past a tap's reach it is a drag (a slider, a list, a page swipe): the live tiles give way too.
  pressure_finger(true, screen_input::touch_guard.distance() > ui::touch_min() / 2);
  // Swiping in from an edge ("Swiping between pages"); the tap under the finger is consumed and LVGL waits for the
  // release. LVGL 9.5 sends no PRESSING to the input device, hence the touchscreen trigger.
  edge_move(x, y);
}

inline void released() {
  if (contact) contact(false);
  pressure_finger(false, false);
  touched_at = esphome::millis();
  edge_release();
}
}  // namespace touch_input
// Invalidate contacts and asynchronous views before their old tile records are freed.
inline void cancel_layout_input(bool invalidate_widgets) {
  prepare_cancel();
  screen_input::touch_guard.consume();
  screen_input::edge_swipe.end();
  for (auto *indev = lv_indev_get_next(nullptr); indev; indev = lv_indev_get_next(indev)) lv_indev_wait_release(indev);
  captured_slider = nullptr;
  slider_changed = false;
  active_index = -1;
  if (dismiss) dismiss();
  saver_forget();
  camera_close();
  // Every picture is asked for anew by what the next layout draws; what the store kept for this one goes (forget, below).
  media_card_cover = CoverAsk{};
  tile_pictures_reset();
  history_asked_entity.clear();
  history = History{};
  if (invalidate_widgets) {
    for (auto &w : widgets) { w.index = grid.max_tiles(); w.cached_active = -1; }
    // The next layout's cover cards start at their primary control: an index may be another cover's now.
    cover_swapped.fill(0);
    forget_kept();
    if (layout_changed) layout_changed();
  }
}
}  // namespace runtime_tiles
#undef RUNTIME_TILES_PARTS
