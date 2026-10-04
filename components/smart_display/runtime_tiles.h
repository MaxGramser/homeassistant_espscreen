#pragma once
#include <cstring>
#include "runtime_model.h"
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
#endif
#include "header_bar.h"
#include "page_header.h"
#include "tile_palette.h"
#include "overlay_card.h"
#include "tall_tile.h"
#include "cover_tile.h"
#include "alert_overlay.h"
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
#include "kept_pages.h"
#include "tile_memory.h"
#include "wifi_status.h"
#include "ota_status.h"
#include "picture_store.h"
#include "media_card.h"
#include "saver_view.h"
#include "light_card.h"
#include "weather_card.h"
#include "forecast_tile.h"
#include "climate_tile.h"
#include "swipe_profile.h"
#include "lvgl.h"
#include <functional>
#include <algorithm>
#include <new>
#include <cstdlib>

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
inline esphome::ESPPreferenceObject buttons_preference;
inline esphome::ESPPreferenceObject swipe_preference;
inline esphome::ESPPreferenceObject home_preference;
inline esphome::ESPPreferenceObject dark_preference;
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
// Pages turn once the layout is complete, and not while the "Preparing pages" screen covers them.
inline bool navigation_ready() {
  return protocol_problem == ProtocolProblem::none && transfer.active && model.ready() && !preparing.foreground;
}
inline uint64_t previous_page_id = 0;
inline bool had_previous_page = false;
inline uint32_t history_view_id = 0, options_view_id = 0, camera_view_id = 0, cover_view_id = 0, live_view_id = 0;
// A player's library (firmware 0.24.0+): the folder asked for last, and the covers of its page.
inline uint32_t library_view_id = 0, library_art_view_id = 0;
inline void cancel_layout_input(bool invalidate_widgets = true);
inline void forget_kept();
inline void prepare_start();
inline int home_page() { return model.page_data.home; }
inline int sequential_page(int page, int step) {
  return navigation_ready() ? model.page_data.step(page, step) : page;
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
// What ESP Screen Manager says the screensaver shows (op "saver", screen_saver.py): "media", "camera", "clock" or ""
// for none, with the player's or camera's name and, for a player, its title, artist and album, its picture's mark and
// the cover's colour (the picture is made again when either changes). Where the track is, is no part of it.
struct SaverChoice {
  std::string kind, entity, name, title, artist, album, picture, ground;
  std::string weather;  // the clock's outside temperature, ready to draw (firmware 0.31.0+, app 0.4.52)
  // A player's keys (firmware 0.33.0+, app 0.4.55): whether it plays or is paused, and what Home Assistant says it can do.
  std::string state;
  uint32_t features = 0;
  bool muted = false;
  bool operator==(const SaverChoice &o) const {
    return kind == o.kind && entity == o.entity && name == o.name && title == o.title && artist == o.artist &&
           album == o.album && picture == o.picture && ground == o.ground && weather == o.weather &&
           state == o.state && features == o.features && muted == o.muted;
  }
};
inline SaverChoice saver_next, saver_now;  // the app's latest word, and what the glass shows
inline lv_obj_t *saver_root = nullptr;      // the clock
// The words over the screensaver's picture (firmware 0.32.0+): drawn again with the next track's picture, and
// `saver_words_due` until it has come.
inline lv_obj_t *saver_first = nullptr, *saver_second = nullptr;
inline bool saver_words_due = false;
// A player's keys over its cover (firmware 0.33.0+): volume up, volume down, play or pause. They take their own tap, so
// the screen stays in standby; a touch anywhere else wakes it. `saver_flipped`: when the play key last showed the other
// face ahead of Home Assistant's word.
inline std::array<lv_obj_t *, 3> saver_keys{};
inline uint32_t saver_flipped = 0;
inline void saver_keys_draw();
// A next track that came while a picture was on its way (firmware 0.32.0+): followed once that load has ended, so the
// online_image never gets a second link in the middle of a download and the one that lands is the one asked for.
inline bool saver_follow_due = false;
inline void saver_follow_pending();
inline bool saver_camera = false;           // the camera's full view on the glass is the screensaver's (a camera or a cover)
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
inline void refresh_tile(size_t index);
// Style setters that only touch a property when it changes (defined with the card renderers below).
inline void set_color(lv_obj_t *obj, lv_style_prop_t prop, lv_color_t color, lv_style_selector_t selector = 0);
inline void set_number(lv_obj_t *obj, lv_style_prop_t prop, int32_t number, lv_style_selector_t selector = 0);
inline void set_font(lv_obj_t *obj, const lv_font_t *value);
#ifdef SWIPE_PROFILE
inline void swipe_test(unsigned count, unsigned interval_ms, unsigned back_ms);
#endif
inline void refresh_header_only();
inline void refresh_all();
inline void refresh_detail(unsigned index);
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
inline void live_tick(uint32_t now);
inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url);
inline bool camera_supported();
// The media card's album cover (firmware 0.2.64+): the card or a tile over the whole page says which cover it shows,
// the board's online_image loads it; see the end of this file.
// PREFETCH (firmware 0.3.2+): a media card on a kept page, fetched ahead while the screen is idle.
enum class CoverOwner : uint8_t { NONE, DETAIL, TILE, PREFETCH };
inline void cover_want(const std::string &entity, const std::string &picture, int size, uint32_t background, CoverOwner owner, size_t slot);
inline lv_image_dsc_t *cover_ready(const std::string &entity, int size, uint32_t background);
struct Widgets;
inline lv_image_dsc_t *kept_cover(const Widgets &w);
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
  numbers_preference = esphome::global_preferences->make_preference<uint32_t>(0x4E554D31);
  uint32_t numbers_saved=0;
  if(numbers_preference.load(&numbers_saved))screen_text_numbers(numbers_saved);
  uint32_t swipe_saved=0;
  if(swipe_preference.load(&swipe_saved))swipe_pages=swipe_saved==1;
  uint32_t dark_saved=0;
  if(dark_preference.load(&dark_saved))settings_screen::dark_mode=dark_saved==1;
  uint32_t buttons_saved=1;
  if(buttons_preference.load(&buttons_saved))page_buttons=buttons_saved!=0;
  HomeTimeout home;
  if(home_preference.load(&home) && home.seconds>=30 && home.seconds<=3600){
    auto_home=home.enabled?1:0;auto_home_seconds=(int32_t)home.seconds;
  }
  // The turn the screen was left at (every board since firmware 0.2.80, the Guition before that). A quarter turn
  // saved on glass that cannot take one (a board file that changed) is left where it is.
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
  uint32_t turned = (uint32_t) rotation;
  rotation_preference.save(&turned);
}
inline std::function<void(Tile &)> detail, detail_update;
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
  uint32_t cached_paint=UINT32_MAX;
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
  lv_obj_t *panel{}; std::string panel_mode; bool panel_dirty=false, panel_full=false, panel_tall=false; int panel_w=0; uint16_t panel_layout_w=0,panel_layout_h=0;
  std::array<lv_obj_t *,3> keys{}, key_icons{}; std::array<int,3> key_commands{}; std::array<std::string,3> key_args; std::array<int,3> key_checked{};
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
  // The album cover a media card over the whole page shows (firmware 0.3.2+): the player, its picture's mark, the size
  // and colour asked for and where it goes on the card, so a kept page can have it fetched ahead and put on the card.
  std::string cover_entity, cover_mark; int cover_size=0; uint32_t cover_ground=0; media_card::Rect cover_rect{};
};
// A page is being built off the glass (warm_page): its cards ask for no pictures and wake nothing.
inline bool warming=false;
constexpr unsigned POINT_BUFFER = 128;
// One widget per cell of the board's grid: the cards packages/cells/<number>.yaml brings, bound at boot.
inline std::array<Widgets, CELLS_MAX> widgets;
// ---- Pages kept whole (firmware 0.3.2+, kept_pages.h) ----
// A board with PSRAM keeps the cards of the pages it has shown. `widgets` is always the set on the glass; a page that
// leaves the glass takes its set onto the shelf, hidden, and a page that comes back brings its own set with it. A card
// keeps its index in whichever set holds it, and its callbacks name that index (or `&widgets[index]`), so a set is only
// ever exchanged whole: a callback fires on the glass, where `widgets[index]` is that very card. Cards are drawn only
// while they are on the glass. The first set is the board's own (packages/cells), make_card builds the others alike.
using CardSet = std::array<Widgets, CELLS_MAX>;
inline kept_pages::Shelf shelf;
inline kept_pages::Changes changes;  // what a card could show, numbered as it is asked for (kept_pages.h)
inline uint32_t glass_synced = 0;    // the change number the cards on the glass are drawn up to
inline std::array<CardSet *, kept_pages::MAX_KEPT> kept_sets{};
// The styles of a card (packages/core.yaml hands them over at boot), for the cards make_card builds.
struct CardLook { lv_style_t *tile = nullptr, *circle = nullptr, *title = nullptr, *value = nullptr; };
inline CardLook card_look;
inline uint32_t last_turn_ms = 0;  // the last page turn: pictures wait until the pages stand still (camera_view::settled)
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
inline void grid_bind(lv_obj_t *container, int margin, int page_bar_height) {
  tile_grid = container;
  grid_margin = margin;
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
  for (size_t c = 0; c < grid.columns; ++c) grid_columns_dsc[c] = LV_GRID_FR(1);
  grid_columns_dsc[grid.columns] = LV_GRID_TEMPLATE_LAST;
  for (size_t r = 0; r < grid.rows; ++r) grid_rows_dsc[r] = LV_GRID_FR(1);
  grid_rows_dsc[grid.rows] = LV_GRID_TEMPLATE_LAST;
  lv_obj_set_grid_dsc_array(container, grid_columns_dsc.data(), grid_rows_dsc.data());
  lv_obj_update_layout(container);
}

inline void live_place(Widgets &w, const Tile &t, int size, int x, int y);
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
inline bool live_waiting(const Tile &t);
inline bool live_marquee_ready(const Widgets &w, const Tile &t);
// A picture over the whole card: a media player's cover on a 1x2 or 2x2 tile, dimmed under its track (firmware 0.3.1),
// and a live camera in full colour with its name at the bottom, on a shade the app puts in the picture: on a 1x2 or 2x2
// tile since 0.3.3, on every size since 0.3.7 (the small square in the icon's place said too little to be of use).
// A map (firmware 0.20.0) fills its card on every size too, with its name drawn into the picture by the app.
// A favourite (firmware 0.24.0+) fills its card with what it plays on every size, as a live camera does.
inline bool card_art(const Tile &t) {return (t.row_span()>1 && !t.full && t.cover_tile()) || t.live() || t.is_map() || (t.favorite() && t.pictured());}
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
inline bool fresh() { return protocol_problem == ProtocolProblem::none && transfer.active && transfer.begun && model.ready() && ha_connected() && feed_alive(); }
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
  t.undo_optimistic();
  if (auto *x = t.extra_ptr()) for (auto &c : x->choices) c.sent.clear();
}
inline void busy_watch(lv_timer_t *) {
  const uint32_t now = esphome::millis();
  bool any = false;
  for (auto &w : widgets) {
    if (!w.tile || w.index >= model.count) continue;
    auto &t = model.tiles[w.index];
    if (!t.pending) continue;
    if (!t.waiting(now) && !t.tap_held(now) && !t.confirmed) end_wait(w.index);
    any = any || t.pending;
    if (t.loading(now) != w.busy_drawn) refresh_tile(w.index);
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
inline void watch_call(esphome::api::HomeassistantActionRequest &request, const std::string &entity) {
  static uint32_t last_id = 0x5C000000u;  // apart from ESPHome's own counter for YAML actions, which starts at 1
  auto slot = std::find_if(watched_calls.begin(), watched_calls.end(), [](const WatchedCall &c) { return c.id == 0; });
  if (slot == watched_calls.end()) return;
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
        t.undo_optimistic();
        t.release_slider();
        t.refused_at = std::max<uint32_t>(1, esphome::millis());
        t.unanswered = true;
        refresh_tile(i);
      }
      if (silent) ESP_LOGW("runtime_action", "Home Assistant neither answered nor acted on %s: may this screen perform actions?", entity.c_str());
      if (silent && !unanswered_told && hint_alert) {
        unanswered_told = true;
        hint_alert(tr(txt::status_no_answer_title), tr(txt::status_no_answer_text));
      }
      return;
    }
    if (answer.is_success()) {
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
    for (size_t i = 0; i < model.tiles.size(); ++i) if (model.tiles[i].entity == entity) {
      model.tiles[i].pending = false;
      model.tiles[i].undo_optimistic();
      model.tiles[i].release_slider();
      model.tiles[i].refused_at = std::max<uint32_t>(1, esphome::millis());
      model.tiles[i].unanswered = false;
      refresh_tile(i);
    }
  });
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
inline void send_action(esphome::api::HomeassistantActionRequest &request, const std::string &entity, bool watch) {
  for(size_t i=0;i<model.tiles.size();++i) if(model.tiles[i].entity==entity){model.tiles[i].begin(esphome::millis());model.tiles[i].refused_at=0;refresh_tile(i);}
  watch_busy();
#ifdef USE_API_HOMEASSISTANT_ACTION_RESPONSES
  if (watch) watch_call(request, entity);
#endif
  esphome::api::global_api_server->send_homeassistant_action(request);
}
// `key2` and `value2`: a second field, for a thermostat's range (both ends in one call, firmware 0.19.0).
// The player a card's media keys act on (firmware 0.26.0+): the speaker it follows (the app's `ct`, a Spotify tile that
// plays on a Sonos), or the tile's own.
inline const std::string &media_entity(const Tile &t){return t.extra().media_target.empty()?t.entity:t.extra().media_target;}
inline void action(const std::string &service, const std::string &entity, const std::string &key="", const std::string &value="", bool watch=true,
                   const std::string &key2="", const std::string &value2="") {
  if (!fresh() || !valid_entity(entity)) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(service);
  request.data.init(1 + !key.empty() + !key2.empty());
  esphome::api::HomeassistantServiceMap entry;
  entry.key = esphome::StringRef("entity_id");
  entry.value = esphome::StringRef(entity);
  request.data.push_back(entry);
  if(!key.empty()) {esphome::api::HomeassistantServiceMap param;param.key=esphome::StringRef(key);param.value=esphome::StringRef(value);request.data.push_back(param);}
  if(!key2.empty()) {esphome::api::HomeassistantServiceMap param;param.key=esphome::StringRef(key2);param.value=esphome::StringRef(value2);request.data.push_back(param);}
  send_action(request, entity, watch);
  ESP_LOGI("runtime_action","Sent service=%s entity=%s",service.c_str(),entity.c_str());
}
// An action that waits for nothing: no busy tile, no redraw, and the next one goes out at once. A remote's key and a
// player's volume step, which a finger repeats faster than Home Assistant answers.
inline void step_action(const std::string &service, const std::string &entity, const std::string &key = "", const std::string &value = "") {
  if (!fresh() || !valid_entity(entity)) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(service);
  request.data.init(key.empty() ? 1 : 2);
  esphome::api::HomeassistantServiceMap target, field;
  target.key = esphome::StringRef("entity_id"); target.value = esphome::StringRef(entity); request.data.push_back(target);
  if (!key.empty()) { field.key = esphome::StringRef(key); field.value = esphome::StringRef(value); request.data.push_back(field); }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("runtime_action", "Sent %s%s%s to %s", service.c_str(), value.empty() ? "" : " ", value.c_str(), entity.c_str());
}
// A remote's key (firmware 0.22.0+): remote.send_command with one command, sent as a remote sends it. It changes no state,
// so nothing waits for one, as on the remote in your hand.
inline void remote_key(const std::string &entity, const std::string &command) { step_action("remote.send_command", entity, "command", command); }
// An action whose one value Home Assistant renders itself: a list such as a lamp's hs_color "[20, 100]" does not
// travel as text (firmware 0.3.9+, the lamp page of a light group).
inline void action_template(const std::string &service, const std::string &entity, const std::string &key, const std::string &value) {
  if (!fresh() || !valid_entity(entity)) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(service);
  request.data.init(1);
  esphome::api::HomeassistantServiceMap target;
  target.key = esphome::StringRef("entity_id");
  target.value = esphome::StringRef(entity);
  request.data.push_back(target);
  request.data_template.init(1);
  esphome::api::HomeassistantServiceMap entry;
  entry.key = esphome::StringRef(key);
  entry.value = esphome::StringRef(value);
  request.data_template.push_back(entry);
  send_action(request, entity, true);
  ESP_LOGI("runtime_action", "Sent service=%s entity=%s %s", service.c_str(), entity.c_str(), key.c_str());
}
// A tap's own action (firmware 0.2.58+): the tile's entity with the data the app sent, text as data and the values Home
// Assistant renders itself (numbers, lists, true or false) as a data_template.
inline void perform(const Tile &tile) {
  const auto &x = tile.extra();
  if (!fresh() || !valid_entity(tile.entity) || x.action.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(x.action);
  request.data.init(1 + x.action_data.size());
  esphome::api::HomeassistantServiceMap target;
  target.key = esphome::StringRef("entity_id");
  target.value = esphome::StringRef(tile.entity);
  request.data.push_back(target);
  for (const auto &pair : x.action_data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(pair.first);
    entry.value = esphome::StringRef(pair.second);
    request.data.push_back(entry);
  }
  request.data_template.init(x.action_templates.size());
  for (const auto &pair : x.action_templates) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(pair.first);
    entry.value = esphome::StringRef(pair.second);
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
  request.service = esphome::StringRef("esphome.screen_options");
  request.is_event = true;
  const std::string number = std::to_string(page);
  const std::string keys[] = {"inbox", "entity", "page", "session", "rev", "view"}, values[] = {inbox, entity, number, protocol_key(transfer.lease), layout_rev, std::to_string(++options_view_id)};
  request.data.init(6);
  for (int i = 0; i < 6; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
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
  request.service = esphome::StringRef(service);
  request.is_event = true;
  // The values live until the request is sent: the request holds references to them.
  std::vector<std::pair<std::string, std::string>> data = {{"inbox", inbox}, {"session", protocol_key(transfer.lease)}, {"rev", layout_rev}};
  for (const auto &pair : pairs) data.emplace_back(pair.first, pair.second);
  request.data.init(data.size());
  for (const auto &pair : data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(pair.first);
    entry.value = esphome::StringRef(pair.second);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
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
// The covers of a page: the items by their numbers, the frames they fill (tile_art) and the page's colour behind them.
inline void library_art_request(const std::string &entity, const std::string &items, const std::string &atlas, uint32_t ground) {
  char bg[8];
  snprintf(bg, sizeof(bg), "%06X", (unsigned) ground);  // a theme colour, six digits
  library_event("esphome.screen_camera", {{"entity", entity}, {"lib", items}, {"atlas", atlas}, {"bg", bg}, {"view", std::to_string(++library_art_view_id)}});
  ESP_LOGI("library", "Asked for the covers of %s", items.c_str());
}
// A detail card asks the manager for its history (app 0.2.59+ answers with op "history"). An event, like
// setting_event: it needs no permission to call Home Assistant actions.
inline void history_request(const std::string &entity, uint32_t hours) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_history");
  request.is_event = true;
  const std::string span = std::to_string(hours);
  const std::string keys[] = {"inbox", "entity", "hours", "session", "rev", "view"}, values[] = {inbox, entity, span, protocol_key(transfer.lease), layout_rev, std::to_string(++history_view_id)};
  request.data.init(6);
  for (int i = 0; i < 6; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
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
  esphome::api::HomeassistantActionRequest request;request.service=esphome::StringRef("esphome.screen_setting");request.is_event=true;
  std::string number=std::to_string(value);request.data.init(3);
  const std::string keys[]={"inbox","key","value"},values[]={inbox,key,number};
  for(int i=0;i<3;++i){esphome::api::HomeassistantServiceMap entry;entry.key=esphome::StringRef(keys[i]);entry.value=esphome::StringRef(values[i]);request.data.push_back(entry);}
  esphome::api::global_api_server->send_homeassistant_action(request);
}
} // namespace runtime_tiles
// Small shared native-LVGL detail cards. No images, canvas buffers or free scrolling.
namespace runtime_tiles {
inline lv_obj_t *detail_root=nullptr,*detail_backdrop=nullptr;
// A place in the open card, in the screen's coordinates: what a finger's point may be compared with.
// Everything a card draws is placed inside detail_root, which overlay_card::frame puts in the middle
// of the glass, so the two only agree on a board whose cards fill their screen.
inline int detail_screen_x(int in_card){
  if(!detail_root)return in_card;
  lv_area_t a;lv_obj_get_coords(detail_root,&a);return int(a.x1)+in_card;
}
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
inline const lv_font_t *detail_font=nullptr;
inline lv_obj_t *detail_actions[32]{};
inline unsigned detail_action_count=0;
inline lv_obj_t *detail_status=nullptr;
inline lv_obj_t *detail_badge_status=nullptr;
inline lv_obj_t *detail_switch=nullptr;
inline lv_obj_t *detail_label(lv_obj_t *parent,const std::string &text,int x,int y,int width) {
  auto *label=lv_label_create(parent);lv_label_set_text(label,text.c_str());lv_obj_set_pos(label,x,y);lv_obj_set_width(label,width);
  lv_obj_set_style_text_font(label,detail_font,0);lv_obj_set_style_text_color(label,theme::color(theme::INK),0);
  lv_label_set_long_mode(label,LV_LABEL_LONG_DOT);lv_obj_set_height(label,lv_font_get_line_height(detail_font));return label;
}
inline std::string detail_state(const Tile &t){
  if(t.domain()=="person")return t.state=="home"?tr(txt::ha_person_home):t.state=="not_home"?tr(txt::ha_person_not_home):t.state;
  if(t.domain()=="sun")return tr(t.state=="above_horizon"?txt::ha_sun_above_horizon:txt::ha_sun_below_horizon);
  if(t.domain()=="timer")return timer_text(t);
  if(t.domain()=="script"||t.domain()=="scene"||t.domain()=="button"||t.domain()=="input_button")return t.state=="on"?tr(txt::script_running):last_run_text(t.last_run);
  if(t.domain()=="binary_sensor"&&(t.state=="on"||t.state=="off"))return tile_controls::binary_state_text(t.device_class,t.state=="on");
  if(t.state=="on")return tr(txt::ha_on);
  if(t.state=="off")return tr(txt::ha_off);
  if(t.state=="docked")return tr(txt::ha_vacuum_docked);
  if(t.state=="cleaning")return tr(txt::ha_vacuum_cleaning);
  if(t.state=="paused")return tr(txt::ha_vacuum_paused);
  if(t.state=="returning")return tr(txt::ha_vacuum_returning);
  if(t.state=="idle")return tr(txt::ha_vacuum_idle);
  if(t.state=="error")return tr(txt::vacuum_check_robot);
  if(!t.available())return tr(txt::ha_unavailable);
  // Home Assistant's word where the screen has none of its own (firmware 0.2.58+).
  if(!t.extra().state_word.empty())return t.extra().state_word;
  return t.unit.empty()?t.state:screen_text::localize(t.state);
}
inline void alarm_close_pad();
inline void lock_card_closed();
// Every way a card closes (Back, standby, Back to page 1, another card) also forgets a code half typed on an alarm's
// keypad: it never waits in memory for the next person at the screen.
inline void hide_detail(){
  alarm_close_pad();lock_card_closed();
  if(detail_backdrop)lv_obj_add_flag(detail_backdrop,LV_OBJ_FLAG_HIDDEN);if(detail_root)lv_obj_add_flag(detail_root,LV_OBJ_FLAG_HIDDEN);
  // A player's library and speaker menu go with its card (firmware 0.24.0+), after it: the card stays as it was.
  media_library::close();}
inline int slider_value(const Tile &t){
  auto d=t.domain();float value=0;
  if(d=="light")value=std::isfinite(t.brightness)?t.brightness/255:0;
  if(d=="fan")value=std::isfinite(t.percentage)?t.percentage/100:0;
  // A blind's bar is the blind itself: the closed part is filled, so a closed cover is a full bar, as on its card and in
  // Home Assistant's own cover dialog (firmware 0.2.66+; before, the bar filled with the open part, the other way round).
  if(d=="cover")value=std::isfinite(t.position)?(100-t.position)/100:1;
  if(d=="media_player")value=std::isfinite(t.volume)?t.volume:0;
  if(d=="number"||d=="input_number") {char *end;float state=strtof(t.state.c_str(),&end);if(end!=t.state.c_str() && t.maximum>t.minimum)value=(state-t.minimum)/(t.maximum-t.minimum);}
  // A humidifier's slider is the humidity it is set to, over its own range (Home Assistant's target-humidity slider).
  if(d=="humidifier"&&std::isfinite(t.target)&&t.maximum>t.minimum)value=(t.target-t.minimum)/(t.maximum-t.minimum);
  return std::clamp((int)std::lround(value*1000),0,1000);
}
inline lv_obj_t *captured_slider=nullptr;
inline bool slider_changed=false;
inline int slider_held=0;
inline void slider_event(lv_event_t *e);
inline void commit_slider(unsigned i,int raw,bool tilt=false){
  if(i>=model.count || !fresh())return;auto &t=model.tiles[i];if(!t.available() || t.waiting(esphome::millis()))return;
  float value=std::clamp(raw,0,1000)/1000.0f;auto d=t.domain();
  if(d=="cover"){
    if(tilt&&!tile_controls::cover_tilt_selected(t))return;
    const auto call=tile_controls::cover_position_action(t,raw,tilt);
    if(call.valid())action(call.service,t.entity,call.key,call.value);
    return;
  }
  if(tilt)return;
  // A light's slider stops at 1 %, as in Home Assistant; tapping the card turns it off.
  // The slider stays where the finger left it while the light fades towards it (Tile::hold_slider).
  if(d=="light"){int sent=std::max(3,(int)std::lround(value*255));action("light.turn_on",t.entity,"brightness",std::to_string(sent));t.hold_slider(esphome::millis(),sent);}
  if(d=="fan"){int sent=(int)std::lround(value*100);action("fan.set_percentage",t.entity,"percentage",std::to_string(sent));t.hold_slider(esphome::millis(),sent);}
  if(d=="media_player"){action("media_player.volume_set",media_entity(t),"volume_level",std::to_string(value));t.hold_slider(esphome::millis(),value);}
  if(d=="number"||d=="input_number") {
    if(!std::isfinite(t.minimum)||!std::isfinite(t.maximum)||t.maximum<=t.minimum||t.step<=0)return;
    value=std::clamp(t.minimum+std::round(value*(t.maximum-t.minimum)/t.step)*t.step,t.minimum,t.maximum);
    action(d+".set_value",t.entity,"value",std::to_string(value)); }
  if(d=="humidifier"&&t.maximum>t.minimum){
    const float step=std::max(1.0f,tile_controls::edit_step(t));
    const int sent=(int)std::lround(std::clamp(t.minimum+std::round(value*(t.maximum-t.minimum)/step)*step,t.minimum,t.maximum));
    action("humidifier.set_humidity",t.entity,"humidity",std::to_string(sent));}
}
// Where the finger landed on a slider, the value it had, and whether it landed beside the strip (in the tile's lower
// half that the strip claims, slider_zone) and moved: a press beside the strip that never moves is a tap on the tile.
inline lv_point_t slider_press{0,0};inline int slider_press_value=0;inline bool slider_press_beside=false,slider_press_moved=false,slider_press_held=false;
// The card a strip belongs to, for a press beside the strip that turns out to be the card's tap or hold.
inline lv_obj_t *strip_card(lv_obj_t *slider){for(auto &w:widgets)if(w.slider==slider)return w.tile;return nullptr;}
inline void slider_event(lv_event_t *e){
  auto *slider=lv_event_get_target_obj(e);auto code=lv_event_get_code(e);
  if(code==LV_EVENT_PRESSED){captured_slider=slider;slider_changed=false;slider_press_moved=false;slider_press_beside=false;slider_press_held=false;
    slider_press_value=lv_slider_get_value(slider);
    if(auto *indev=lv_indev_active()){lv_indev_get_point(indev,&slider_press);lv_area_t a;lv_obj_get_coords(slider,&a);slider_press_beside=slider_press.x<a.x1 || slider_press.x>a.x2 || slider_press.y<a.y1 || slider_press.y>a.y2;}
    // Beside the strip the card lights up as under a tap, until the finger starts dragging.
    if(slider_press_beside)if(auto *card=strip_card(slider))lv_obj_add_state(card,LV_STATE_PRESSED);}
  if(code==LV_EVENT_PRESSING && captured_slider==slider && !slider_press_moved){
    if(auto *indev=lv_indev_active()){lv_point_t p;lv_indev_get_point(indev,&p);if(std::abs(p.x-slider_press.x)>=10 || std::abs(p.y-slider_press.y)>=10){slider_press_moved=true;
      if(auto *card=strip_card(slider))lv_obj_remove_state(card,LV_STATE_PRESSED);}}}
  // A finger resting beside the strip holds the card, as it would without the strip's claim on the card.
  if(code==LV_EVENT_LONG_PRESSED && captured_slider==slider && slider_press_beside && !slider_press_moved && !slider_press_held){
    if(auto *card=strip_card(slider)){slider_press_held=true;lv_obj_send_event(card,LV_EVENT_LONG_PRESSED,nullptr);}}
  if((code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST) && slider_press_beside)if(auto *card=strip_card(slider))lv_obj_remove_state(card,LV_STATE_PRESSED);
  // On release LVGL sets the value once more from the last touch point: log it when that throws a
  // dragged slider to one of its ends, so a stray touch sample shows up (screen_input::release_jump).
  if(code==LV_EVENT_VALUE_CHANGED && captured_slider==slider){
    auto *indev=lv_indev_active();int raw=lv_slider_get_value(slider);
    if(!indev || lv_indev_get_state(indev)!=LV_INDEV_STATE_RELEASED)slider_held=raw;
    else if(slider_changed && screen_input::release_jump(slider_held,raw,lv_slider_get_min_value(slider),lv_slider_get_max_value(slider))){
      lv_point_t point;lv_indev_get_point(indev,&point);
      ESP_LOGW("slider","Tile slider jumped on release: %d -> %d (touch x=%d y=%d)",slider_held,raw,(int)point.x,(int)point.y);
    }
  }
  // The range reaches below zero only to draw the round end at 0 (slider_handle).
  if(code==LV_EVENT_VALUE_CHANGED && lv_slider_get_value(slider)<0)lv_slider_set_value(slider,0,LV_ANIM_OFF);
  if(code==LV_EVENT_VALUE_CHANGED && captured_slider==slider)slider_changed=true;
  if(code==LV_EVENT_PRESS_LOST && captured_slider==slider){captured_slider=nullptr;slider_changed=false;}
  if(code==LV_EVENT_RELEASED && captured_slider==slider){
    unsigned index=(uintptr_t)lv_event_get_user_data(e);bool tilt=false;
    // A slider among a card's own parts (the media tile's volume) belongs to the tile the slot shows now.
    for(auto &w:widgets)if(w.slider==slider || w.control_slider==slider || (w.extra && lv_obj_get_parent(slider)==w.extra)){index=w.index;tilt=w.extra_mode=="cover_tilt"&&w.parts[3]==slider;break;}
    bool changed=slider_changed;captured_slider=nullptr;slider_changed=false;
    // A finger that landed beside a tile's strip and let go without moving tapped the tile (or held it, sent above):
    // the value LVGL set from that point on release goes back, and the tile's own rules decide what the tap does.
    if(slider_press_beside && !slider_press_moved){
      if(auto *card=strip_card(slider)){
        lv_slider_set_value(slider,slider_press_value,LV_ANIM_OFF);
        ESP_LOGI("slider","%s beside the strip of %s: the tile's",slider_press_held?"Hold":"Tap",model.tiles[index].entity.c_str());
        if(!slider_press_held)lv_obj_send_event(card,LV_EVENT_SHORT_CLICKED,nullptr);
        return;}
    }
    // A finger let go within the edge band of the glass meant the slider's end (screen_input::edge_snap).
    if(auto *indev=lv_indev_active();indev && lv_obj_get_width(slider)>=lv_obj_get_height(slider)){
      lv_point_t p;lv_indev_get_point(indev,&p);lv_area_t a;lv_obj_get_coords(slider,&a);
      int screen=lv_display_get_horizontal_resolution(lv_obj_get_display(slider));
      int snap=screen_input::edge_snap(p.x,a.x1,a.x2,screen,screen_input::edge_snap_band);
      if(snap){int end=snap>0?(int)lv_slider_get_max_value(slider):std::max(0,(int)lv_slider_get_min_value(slider));
        ESP_LOGI("slider","Let go %d px from the %s edge: slider %d -> %d",snap>0?screen-1-(int)p.x:(int)p.x,snap>0?"right":"left",(int)lv_slider_get_value(slider),end);
        lv_slider_set_value(slider,end,LV_ANIM_OFF);changed=true;}
    }
    if(index<model.count&&model.tiles[index].row_span()>1&&!model.tiles[index].full)
      for(const auto &w:widgets)if(w.control_slider==slider&&!tile_controls::panel_available(model.tiles[index]))return;
    if(changed && screen_input::touch_guard.accept_slider(esphome::millis(),200+index))commit_slider(index,lv_slider_get_value(slider),tilt);
  }
}
inline void show_detail(unsigned index);
// A chip on the vacuum card: the service call goes out, the chip shows the choice at once, and the card
// waits for Home Assistant like after its other buttons. The card is drawn again once this tap's event
// has finished, because a chosen mode can add or remove the suction and water rows.
inline void redraw_detail(){
  lv_async_call([](void *){if(detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))show_detail(detail_index);},nullptr);
}
inline void choose(Tile &t,Choice &row,const std::string &value){
  if(value==row.current)return;
  auto a=tile_controls::choice_action(t,row.kind,value);if(!a.valid())return;
  action(a.service,row.kind=='s'?t.entity:row.entity,a.key,a.value);
  row.sent=value;t.begin(esphome::millis());
  redraw_detail();
}
// What a key on a card does; `cmd` is the key's command. Shared by the plain keys (detail_button) and the round
// keys of the media card. -1 is Back.
inline void alarm_command(int cmd);
inline void lock_command(int cmd);
inline bool alarm_pad_open();
inline void detail_command(int cmd){
  // Back on the alarm's keypad goes back to its card; everywhere else it closes the card.
  if(cmd==-1&&alarm_pad_open()){alarm_close_pad();redraw_detail();return;}
  if(cmd==-1){hide_detail();return;}
  // The alarm panel's modes, digits, Clear and OK (600-621): the digits count every clean tap, like the -/+ keys.
  if(cmd>=600&&cmd<=621){alarm_command(cmd);return;}
  // A lock's keys (700-702): Lock, Unlock, Open door.
  if(cmd>=700&&cmd<=709){lock_command(cmd);return;}
  // History ranges (firmware 0.2.51+): redraw after this event, which belongs to a key the redraw deletes.
  if(cmd>=160&&cmd<163){
    static const uint32_t hours[]={1,24,168};
    if(detail_index<model.count&&allowed(esphome::millis(),300+cmd,"history range")&&history_hours!=hours[cmd-160]){
      history_hours=hours[cmd-160];
      lv_async_call([](void *){if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))show_detail(detail_index);},nullptr);
    }
    return;
  }
  // The setpoint's - and +: every clean tap counts, also while the last one is still on its way to Home
  // Assistant, so a series of taps is one series of steps (the send waits for the last of them).
  if(cmd==CLIMATE_END_LOW||cmd==CLIMATE_END_HIGH){
    if(detail_index>=model.count)return;
    auto &tile=model.tiles[detail_index];
    tile.range_end=cmd==CLIMATE_END_HIGH?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW;
    climate_paint_ends(tile);
    refresh_tile(detail_index);   // the tile's chip says the same end
    return;
  }
  if(cmd==CLIMATE_DOWN||cmd==CLIMATE_UP){
    if(!fresh()||detail_index>=model.count)return;
    auto &tile=model.tiles[detail_index];
    if(!tile.available()||!screen_input::touch_guard.accept_repeat(esphome::millis(),300+cmd))return;
    climate_step(tile,cmd==CLIMATE_UP?1:-1);
    return;
  }
  // A key of a remote's keypad (firmware 0.22.0+): the command its integration takes for it, sent as a remote sends it.
  // Every clean tap counts, as on the -/+ keys, so down, down, down moves three rows; only a bounce is dropped.
  if(cmd>=REMOTE_KEY_FIRST&&cmd<REMOTE_KEY_FIRST+RK_COUNT){
    if(!fresh()||detail_index>=model.count)return;
    auto &t=model.tiles[detail_index];
    const auto &keys=t.extra().keypad;const unsigned i=cmd-REMOTE_KEY_FIRST;
    if(!t.available()||i>=keys.size()||keys[i].empty()||!screen_input::touch_guard.accept_repeat(esphome::millis(),300+cmd))return;
    remote_key(t.entity,keys[i]);
    return;
  }
  if(!fresh()||detail_index>=model.count || !allowed(esphome::millis(),300+cmd,"card button "+model.tiles[detail_index].entity))return;
  auto &t=model.tiles[detail_index];
  // A player's library and its speakers (firmware 0.24.0+) open while a key of it is still on its way.
  if(cmd==27){media_library::open(t.entity);return;}
  if(cmd==28){media_library::speakers(t.entity);return;}
  if(cmd==29){media_library::inputs(t.entity);return;}
  if(!t.available()||t.waiting(esphome::millis()))return;
  if(cmd<4){const char *services[]={"vacuum.start","vacuum.pause","vacuum.return_to_base","vacuum.locate"};action(services[cmd],t.entity);}
  // Vacuum rows: 10-15 suction, 50-55 cleaning mode, 60-65 water.
  static const std::pair<int,char> rows[]={{10,'s'},{50,'m'},{60,'w'}};
  for(const auto &[first,kind]:rows)
    if(cmd>=first && cmd<first+6){auto *row=t.choice(kind);if(row && cmd-first<(int)row->values.size())choose(t,*row,row->values[cmd-first]);}
  // The media card's keys (20-23); its volume slider goes through commit_slider.
  if(cmd>=20 && cmd<=26)media_action(t,cmd);
  if(cmd>=30 && cmd<38 && cmd-30<(int)t.extra().options.size())action(t.domain()+".select_option",t.entity,"option",t.extra().options[cmd-30]);
  // A row of the select card: chosen at once on the card, confirmed by Home Assistant's next state.
  if(cmd>=SELECT_OPTION_FIRST&&cmd<SELECT_OPTION_FIRST+64&&cmd-SELECT_OPTION_FIRST<(int)t.extra().options.size()){
    const std::string option=t.extra().options[cmd-SELECT_OPTION_FIRST];
    // A remote's activity (firmware 0.22.0+) turns it on with that activity, as Home Assistant's dialog does
    // (more-info-remote.ts: remote.turn_on with `activity`). The row shows the choice at once.
    if(t.domain()=="remote"){
      if(option==t.extra().activity&&t.state=="on")return;
      if(auto *x=t.extra_ptr())x->activity=option;
      t.optimistic(true);t.begin(esphome::millis());
      action("remote.turn_on",t.entity,"activity",option);
      redraw_detail();
      return;
    }
    if(option==t.state)return;
    t.state=option;t.begin(esphome::millis());
    action(t.domain()+".select_option",t.entity,"option",option);
    redraw_detail();
    return;
  }
  // Cover keys: 70 + tile_controls::Command (open, stop, close and the tilt keys).
  if(cmd>=70 && cmd<130){auto a=tile_controls::key_action(t,cmd-70);if(a.valid()&&t.domain()=="cover")action(a.service,t.entity,a.key,a.value);}
  if(cmd==40)action(t.state=="active"?"timer.pause":"timer.start",t.entity);
  if(cmd==41)action("timer.cancel",t.entity);
  // The climate card: a mode (200-207), a fan or swing choice (210-221) and the power key (230). The card
  // shows the choice at once and waits for Home Assistant, like the vacuum card's chips.
  if(cmd>=CLIMATE_MODE_FIRST&&cmd<CLIMATE_MODE_FIRST+8){
    const auto modes=tile_controls::climate_modes(t);
    const unsigned i=cmd-CLIMATE_MODE_FIRST;
    if(i<modes.size()&&tile_controls::humidifier(t)&&modes[i]!=t.extra().humidifier_mode){
      t.edit_extra().humidifier_mode=modes[i];
      t.begin(esphome::millis());
      action("humidifier.set_mode",t.entity,"mode",modes[i]);
      redraw_detail();
    }else if(i<modes.size()&&!tile_controls::humidifier(t)&&modes[i]!=tile_controls::lower_case(t.state)){
      t.state=modes[i];
      t.edit_extra().hvac_action.clear();   // the line would still say what the mode before it did
      t.begin(esphome::millis());
      action("climate.set_hvac_mode",t.entity,"hvac_mode",modes[i]);
      redraw_detail();
    }
    return;
  }
  if(cmd>=CLIMATE_ROW_FIRST&&cmd<CLIMATE_ROW_FIRST+12){
    const auto rows=tile_controls::climate_rows(t);
    const unsigned r=(cmd-CLIMATE_ROW_FIRST)/6,i=(cmd-CLIMATE_ROW_FIRST)%6;
    if(r<rows.size()&&i<rows[r].values.size()&&rows[r].values[i]!=rows[r].current){
      const char kind=rows[r].kind;
      const std::string value=rows[r].values[i];
      (kind=='m'?t.edit_extra().humidifier_mode:kind=='f'?t.edit_extra().fan_mode:t.edit_extra().swing_mode)=value;
      t.begin(esphome::millis());
      const auto a=tile_controls::climate_row_action(kind,value);
      action(a.service,t.entity,a.key,a.value);
      redraw_detail();
    }
    return;
  }
  if(cmd==LIGHT_POWER){
    // The same toggle a tap on the tile does, and the card shows the new stand at once as that tap does.
    const bool turning_on=t.state!="on";
    t.optimistic(turning_on);
    t.begin(esphome::millis());
    action(t.domain()+(turning_on?".turn_on":".turn_off"),t.entity);
    redraw_detail();
    return;
  }
  if(cmd==CLIMATE_POWER){
    const bool off=tile_controls::climate_off(t);
    t.begin(esphome::millis());
    if(!off)t.state="off";   // turning on restores the mode Home Assistant remembers, so that one waits
    action(t.domain()+(off?".turn_on":".turn_off"),t.entity);
    redraw_detail();
    return;
  }
}
inline lv_obj_t *detail_button(const char *text,int x,int y,int width,int height,int command){
  auto *button=lv_obj_create(detail_root);lv_obj_remove_style_all(button);lv_obj_set_pos(button,x,y);lv_obj_set_size(button,width,height);
  lv_obj_set_style_bg_color(button,theme::color(command==0?theme::ACCENT:theme::BUTTON),0);lv_obj_set_style_bg_opa(button,LV_OPA_COVER,0);lv_obj_set_style_radius(button,12,0);lv_obj_add_flag(button,LV_OBJ_FLAG_CLICKABLE);
  auto *label=detail_label(button,text,6,0,width-12);lv_obj_center(label);lv_obj_set_style_text_align(label,LV_TEXT_ALIGN_CENTER,0);if(command==0)lv_obj_set_style_text_color(label,theme::color(theme::ON_ACCENT),0);lv_obj_remove_flag(label,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(button,[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));},LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)command);
  lv_obj_set_style_bg_color(button,theme::color(theme::ACCENT_PRESSED),LV_STATE_PRESSED);
  lv_obj_set_style_transform_width(button,-2,LV_STATE_PRESSED);lv_obj_set_style_transform_height(button,-2,LV_STATE_PRESSED);
  lv_obj_set_style_opa(button,LV_OPA_50,LV_STATE_DISABLED);
  if(command>=0 && detail_action_count<32)detail_actions[detail_action_count++]=button;
  return button;
}

// The width a line of text is drawn at, for a layout that has to know before it places it.
inline int text_width(const std::string &text,const lv_font_t *font){
  lv_point_t size;lv_text_get_size(&size,text.c_str(),font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_NONE);return size.x;
}
// ---- Weather card: now, the next hours and the coming days, with rain ----
// The colour of a condition's icon, as this look draws it on a card.
inline uint32_t weather_color_raw(const std::string &c) {
  using namespace theme::ha;
  if(c=="sunny")return SUNNY;
  if(c=="clear-night")return DEEP_PURPLE;
  if(c=="rainy"||c=="pouring"||c=="lightning-rainy"||c=="snowy-rainy")return RAIN;
  if(c=="snowy"||c=="hail")return SNOW;
  if(c=="lightning")return LIGHTNING;
  if(c=="partlycloudy")return PARTLY_CLOUDY;
  return CLOUDY;
}
inline uint32_t weather_accent(const std::string &c) { return theme::foreground(weather_color_raw(c)); }
inline lv_obj_t *detail_text(lv_obj_t *parent,const std::string &text,int x,int y,int width,const lv_font_t *font,lv_text_align_t align,uint32_t color){
  auto *l=detail_label(parent,text,x,y,std::max(1,width));lv_obj_set_style_text_font(l,font,0);lv_obj_set_height(l,lv_font_get_line_height(font));
  lv_obj_set_style_text_align(l,align,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
inline lv_obj_t *detail_text(lv_obj_t *parent,const std::string &text,int x,int y,int width,const lv_font_t *font,lv_text_align_t align,theme::Role role){
  return detail_text(parent,text,x,y,width,font,align,theme::hex(role));
}
// "30%", "30% · 1.7 mm" or "1.7 mm": whatever the provider reports; empty when dry.
inline std::string rain_text(float chance,float mm,bool with_mm){
  if(std::isfinite(chance) && chance>=0){
    if(with_mm && std::isfinite(mm) && mm>=0.05f)return screen_text::percent((int)std::lround(chance))+" · "+screen_text::with_unit(screen_text::decimal(mm,1),"mm");
    return screen_text::percent((int)std::lround(chance));
  }
  if(std::isfinite(mm) && mm>=0.05f)return screen_text::decimal(mm,mm<10?1:0)+" mm";
  return "";
}
inline std::string degrees(float value){ if(!std::isfinite(value))return "--"; char b[16];snprintf(b,sizeof(b),"%.0f°",value);return b; }
inline lv_obj_t *detail_card(int x,int y,int w,int h){
  auto *card=lv_obj_create(detail_root);lv_obj_remove_style_all(card);lv_obj_remove_flag(card,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(card,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_pos(card,x,y);lv_obj_set_size(card,w,h);
  lv_obj_set_style_bg_color(card,theme::color(theme::CARD),0);lv_obj_set_style_bg_opa(card,LV_OPA_COVER,0);
  lv_obj_set_style_radius(card,lv_obj_get_style_radius(widgets[0].tile,LV_PART_MAIN),0);
  lv_obj_set_style_border_width(card,1,0);lv_obj_set_style_border_color(card,theme::color(theme::LINE),0);
  return card;
}
// Two cards: "now" with the next hours, and the coming days. Bold highs, muted lows, rain in blue with a drop,
// so the eye finds temperature first and rain second. Where the blocks go is weather_card.h's arithmetic:
// beside each other on wide glass, under each other elsewhere, and the days that do not fit on a next page.
inline weather_card::Layout weather_layout;
inline lv_obj_t *weather_days_card=nullptr,*weather_dots=nullptr,*weather_chevron[2]={};
inline int weather_page=0;
// The metrics the board's fonts give this card. Every number is a line height the look decides; the one string
// that is measured is an hour's time, which says how many hours a strip of this width holds.
inline weather_card::Metrics weather_metrics(bool large){
  const lv_font_t *icon=widgets[0].icon_font?widgets[0].icon_font:detail_font;
  const lv_font_t *small=widgets[0].value?lv_obj_get_style_text_font(widgets[0].value,LV_PART_MAIN):detail_font;
  weather_card::Metrics m;
  m.large=large;
  m.text_h=lv_font_get_line_height(detail_font);
  m.small_h=lv_font_get_line_height(small);
  m.mini_h=lv_font_get_line_height(mini_icon_font?mini_icon_font:icon);
  m.tiny_h=lv_font_get_line_height(watch_icon_font?watch_icon_font:(mini_icon_font?mini_icon_font:icon));
  m.icon_h=lv_font_get_line_height(icon);
  m.big_h=lv_font_get_line_height(watch_value_font?watch_value_font:detail_font);
  m.hour_w=text_width(screen_settings::current.clock_24h!=0?"00:00":"12 PM",small)+ui::px(large?10:4);
  m.top=ui::px(large?84:38);
  m.pad=overlay_card::pad();
  return m;
}
// One column or two: the stack's own height decides, the same way the thermostat and the blind decide.
inline int weather_columns(const Tile &t,bool large){
  const auto m=weather_metrics(large);const Extra &w=t.extra();
  return overlay_card::columns(weather_card::stacked_height(m,overlay_card::screen_width(),(int)w.hours.size(),(int)w.forecast.size()),
                               m.min_column());
}
// The rows of the days card, for the page shown. A page turn makes only these objects again: the two white
// cards, the hour strip and the pager itself stay as they are.
inline void weather_draw_days(const Tile &t){
  if(!weather_days_card)return;
  lv_obj_clean(weather_days_card);
  const auto &l=weather_layout;const auto &days=t.extra().forecast;
  const lv_font_t *icon=widgets[0].icon_font?widgets[0].icon_font:detail_font;
  const lv_font_t *mini=mini_icon_font?mini_icon_font:icon,*tiny=watch_icon_font?watch_icon_font:mini;
  const lv_font_t *small=widgets[0].value?lv_obj_get_style_text_font(widgets[0].value,LV_PART_MAIN):detail_font;
  const uint32_t ink=theme::hex(theme::INK),muted=theme::hex(theme::SUBTLE),rain=theme::foreground(theme::ha::RAIN);
  const int text_h=lv_font_get_line_height(detail_font),small_h=lv_font_get_line_height(small),mini_h=lv_font_get_line_height(mini),tiny_h=lv_font_get_line_height(tiny);
  const int first=l.first_day(weather_page);
  for(int i=0;i<l.rows && first+i<(int)days.size();++i){
    const auto &f=days[first+i];const int ry=l.rows_y+i*l.row_h,tcy=ry+(l.row_h-text_h)/2,scy=ry+(l.row_h-small_h)/2;
    detail_text(weather_days_card,f.day,l.day_x,tcy,l.day_w,detail_font,LV_TEXT_ALIGN_LEFT,ink);
    detail_text(weather_days_card,weather_icon(f.condition),l.icon_x,ry+(l.row_h-mini_h)/2,mini_h+6,mini,LV_TEXT_ALIGN_LEFT,weather_accent(f.condition));
    detail_text(weather_days_card,weather_text(f.condition),l.cond_x,scy,l.cond_w,small,LV_TEXT_ALIGN_LEFT,muted);
    const std::string wet=l.rain_w?rain_text(f.rain,f.mm,l.rain_mm):std::string();
    if(!wet.empty()){
      detail_text(weather_days_card,"\U000F058E",l.rain_x,ry+(l.row_h-tiny_h)/2,l.drop_w,tiny,LV_TEXT_ALIGN_LEFT,rain);
      detail_text(weather_days_card,wet,l.rain_x+l.drop_w,scy,l.rain_w-l.drop_w,small,LV_TEXT_ALIGN_LEFT,rain);
    }
    detail_text(weather_days_card,std::isfinite(f.high)?degrees(f.high):"",l.high_x,tcy,l.high_w,detail_font,LV_TEXT_ALIGN_RIGHT,ink);
    detail_text(weather_days_card,std::isfinite(f.low)?degrees(f.low):"",l.low_x,scy,l.low_w,small,LV_TEXT_ALIGN_RIGHT,muted);
  }
  if(weather_dots)settings_screen::page_dots(weather_dots,weather_page,l.pages,ui::large());
  for(int side=0;side<2;++side){
    auto *bar=weather_chevron[side];if(!bar||!lv_obj_get_child_count(bar))continue;
    const bool on=side?weather_page<l.pages-1:weather_page>0;
    lv_obj_set_style_opa(lv_obj_get_child(bar,0),on?LV_OPA_COVER:LV_OPA_30,0);
    if(on)lv_obj_add_flag(bar,LV_OBJ_FLAG_CLICKABLE);else lv_obj_remove_flag(bar,LV_OBJ_FLAG_CLICKABLE);
  }
}
// CLICKED, not SHORT_CLICKED: LVGL sends no short click after a press of long_press_time, so a firm press did
// nothing (the tile pager and the settings page learned the same).
inline void weather_pager_event(lv_event_t *e){
  const int step=(int)(intptr_t)lv_event_get_user_data(e);
  const int next=std::clamp(weather_page+step,0,weather_layout.pages-1);
  if(next==weather_page||detail_index>=model.count)return;
  weather_page=next;
  weather_draw_days(model.tiles[detail_index]);
}
inline void render_weather_detail(const Tile &t,bool large,int width,int height,int columns){
  const Extra &weather=t.extra();
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
  const lv_font_t *big=watch_value_font?watch_value_font:detail_font;
  const lv_font_t *icon_font=widgets[0].icon_font?widgets[0].icon_font:detail_font;
  const lv_font_t *mini=mini_icon_font?mini_icon_font:icon_font;
  const lv_font_t *small=widgets[0].value?lv_obj_get_style_text_font(widgets[0].value,LV_PART_MAIN):detail_font;
  const uint32_t ink=theme::hex(theme::INK),muted=theme::hex(theme::SUBTLE);
  const auto m=weather_metrics(large);
  weather_layout=weather_card::layout(m,width,height,(int)weather.hours.size(),(int)weather.forecast.size(),columns);
  const auto &l=weather_layout;
  const int text_h=m.text_h,small_h=m.small_h,mini_h=m.mini_h,icon_h=m.icon_h,big_h=m.big_h,hero=m.hero();
  const int card_pad=m.card_pad();
  weather_days_card=weather_dots=weather_chevron[0]=weather_chevron[1]=nullptr;
  // Now: icon, temperature, condition, then feels-like / humidity / wind in one muted line.
  auto *now=detail_card(l.now.x,l.now.y,l.now.w,l.now.h);
  int cy=card_pad;char b[48];
  detail_text(now,t.available()?weather_icon(t.state):"\U000F0595",card_pad,cy+(hero-icon_h)/2,icon_h+8,icon_font,LV_TEXT_ALIGN_LEFT,weather_accent(t.state));
  const int temp_x=card_pad+icon_h+(ui::px(large?14:6)),temp_w=ui::px(large?92:50);
  detail_text(now,degrees(t.current),temp_x,cy+(hero-big_h)/2,temp_w,big,LV_TEXT_ALIGN_LEFT,ink);
  const int text_x=temp_x+temp_w+(ui::px(large?4:2)),text_w=l.now.w-card_pad-text_x;
  const int lines_h=text_h+small_h+(ui::px(large?2:0));
  detail_text(now,t.available()?weather_text(t.state):tr(txt::ha_unavailable),text_x,cy+(hero-lines_h)/2,text_w,detail_font,LV_TEXT_ALIGN_LEFT,ink);
  std::string details;
  if(std::isfinite(weather.feels))details=fill(txt::weather_feels_like,"n",(int)std::lround(weather.feels));
  if(std::isfinite(t.humidity))details+=(details.empty()?"":" · ")+screen_text::percent((int)std::lround(t.humidity));
  if(std::isfinite(weather.wind)){snprintf(b,sizeof(b),"%.0f %s",weather.wind,weather.wind_unit.empty()?"km/h":weather.wind_unit.c_str());details+=(details.empty()?"":" · ")+std::string(b);}
  detail_text(now,details,text_x,cy+(hero-lines_h)/2+text_h+(ui::px(large?2:0)),text_w,small,LV_TEXT_ALIGN_LEFT,muted);
  // The next hours inside the same card: time, icon, temperature and, while there is room for it, rain.
  if(l.hour_columns){
    const int col=l.hours.w/l.hour_columns;
    for(int i=0;i<l.hour_columns && i<(int)weather.hours.size();++i){
      const auto &h=weather.hours[i];const int x=l.hours.x+i*col,hy=l.hours.y;
      detail_text(now,screen_text::clock_text(h.time,screen_settings::current.clock_24h!=0,true),x,hy,col,small,LV_TEXT_ALIGN_CENTER,muted);
      detail_text(now,weather_icon(h.condition),x,hy+small_h+(ui::px(large?4:1)),col,mini,LV_TEXT_ALIGN_CENTER,weather_accent(h.condition));
      detail_text(now,std::isfinite(h.temp)?degrees(h.temp):"",x,hy+small_h+mini_h+(ui::px(large?8:2)),col,detail_font,LV_TEXT_ALIGN_CENTER,ink);
      if(l.hour_rain)detail_text(now,rain_text(h.rain,h.mm,false),x,hy+small_h+mini_h+text_h+(ui::px(large?8:3)),col,small,LV_TEXT_ALIGN_CENTER,theme::foreground(theme::ha::RAIN));
    }
  }
  // Coming days: a heading and a card with one row per day; what does not fit is a page further.
  if(!weather.forecast.size()){detail_text(detail_root,tr(txt::weather_no_forecast),l.days.x,l.days.y,l.days.w,small,LV_TEXT_ALIGN_LEFT,muted);return;}
  if(!l.heading.empty())detail_text(detail_root,tr(txt::weather_coming_days),l.heading.x,l.heading.y,l.heading.w,detail_font,LV_TEXT_ALIGN_LEFT,muted);
  weather_days_card=detail_card(l.days.x,l.days.y,l.days.w,l.days.h);
  if(!l.pager.empty()){
    // The same pager as the tile pages and the settings page: a chevron in each half, the dots between them.
    const lv_font_t *chevrons=mini_icon_font?mini_icon_font:icon_font;
    const int chevron_h=lv_font_get_line_height(chevrons),half=l.pager.w/2-ui::px(10);
    weather_dots=lv_obj_create(detail_root);lv_obj_remove_style_all(weather_dots);
    lv_obj_set_pos(weather_dots,l.pager.x,l.pager.y);lv_obj_set_size(weather_dots,l.pager.w,l.pager.h);
    lv_obj_remove_flag(weather_dots,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(weather_dots,LV_OBJ_FLAG_CLICKABLE);
    for(int side=0;side<2;++side){
      auto *bar=lv_obj_create(detail_root);lv_obj_remove_style_all(bar);
      lv_obj_set_pos(bar,side?l.pager.right()-half:l.pager.x,l.pager.y);lv_obj_set_size(bar,half,l.pager.h);
      lv_obj_remove_flag(bar,LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_style_bg_opa(bar,LV_OPA_COVER,LV_STATE_PRESSED);lv_obj_set_style_bg_color(bar,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
      lv_obj_set_style_radius(bar,ui::px(large?12:8),0);
      auto *glyph=detail_text(bar,side?"\U000F0142":"\U000F0141",ui::px(6),(l.pager.h-chevron_h)/2,half-ui::px(12),chevrons,
                              side?LV_TEXT_ALIGN_RIGHT:LV_TEXT_ALIGN_LEFT,theme::hex(theme::INK));
      lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
      overlay_card::touchable(bar,l.pager.h);
      lv_obj_add_event_cb(bar,weather_pager_event,LV_EVENT_CLICKED,(void*)(intptr_t)(side?1:-1));
      weather_chevron[side]=bar;
    }
  }
  if(weather_page>=l.pages)weather_page=0;
  weather_draw_days(t);
}
// ---- Select card (firmware 0.3.3) ----
// A select's options as rows of one white card, like a list in Home Assistant's more-info dialog: the option it is
// on stands on the pale accent with a check at its end, a tap on another row chooses that one and shows it at once.
// Wide glass that has more options than one column holds gets a second column (read top to bottom, then the next);
// options that still do not fit go to a next page with the same chevrons and dots as the tile pages.
inline int select_page=0;
inline void select_pager_event(lv_event_t *e){
  select_page+=(int)(intptr_t)lv_event_get_user_data(e);
  redraw_detail();
}
// What is chosen: a select's state, or the activity a remote runs (firmware 0.22.0+).
inline void render_select_detail(const Tile &t,bool large,int width,int height,int pad,int top,const std::string &current){
  const auto &options=t.extra().options;
  const int n=(int)options.size();
  if(!n)return;
  const lv_font_t *text=control_font?control_font:detail_font,*glyphs=mini_icon_font?mini_icon_font:detail_font;
  const int row_h=std::max(ui::touch_min(),ui::px(large?52:36)),inset=ui::px(large?6:4),gap=ui::px(large?4:2);
  const int pager_h=std::max(ui::touch_min(),ui::px(large?44:30)),card_w=std::min(width-2*pad,ui::control_max_width());
  const int room=height-top-pad;
  auto rows_in=[&](int span){return std::max(1,(span-2*inset+gap)/(row_h+gap));};
  // Two columns once one does not hold every option and each column keeps room for a word of some length.
  const int columns=n>rows_in(room)&&card_w>=2*ui::px(large?200:130)+gap?2:1;
  int rows=rows_in(room);
  const bool paged=n>rows*columns;
  if(paged)rows=rows_in(room-pager_h-gap);
  const int per_page=rows*columns,pages=(n+per_page-1)/per_page;
  select_page=std::clamp(select_page,0,pages-1);
  const int first=select_page*per_page,shown=std::min(per_page,n-first);
  // A card of one page is as tall as its rows; a paged card keeps the height of a full page on every page.
  const int used_rows=paged?rows:(shown+columns-1)/columns;
  const int card_h=2*inset+used_rows*row_h+(used_rows-1)*gap,x=(width-card_w)/2;
  auto *card=detail_card(x,top,card_w,card_h);
  const int col_w=(card_w-2*inset-(columns-1)*gap)/columns;
  for(int k=0;k<shown;++k){
    const int i=first+k,c=k/used_rows,r=k%used_rows;
    const bool chosen=options[i]==current;
    auto *row=lv_obj_create(card);lv_obj_remove_style_all(row);
    lv_obj_set_pos(row,inset+c*(col_w+gap),inset+r*(row_h+gap));lv_obj_set_size(row,col_w,row_h);
    lv_obj_add_flag(row,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(row,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_radius(row,ui::px(large?12:8),0);
    lv_obj_set_style_bg_opa(row,chosen?LV_OPA_COVER:LV_OPA_TRANSP,0);lv_obj_set_style_bg_color(row,theme::color(theme::ACCENT_TINT),0);
    lv_obj_set_style_bg_opa(row,LV_OPA_COVER,LV_STATE_PRESSED);
    lv_obj_set_style_bg_color(row,theme::color(chosen?theme::ACCENT_TINT:theme::CARD_PRESSED),LV_STATE_PRESSED);
    lv_obj_set_style_opa(row,LV_OPA_50,LV_STATE_DISABLED);
    const int side=ui::px(large?16:10),check=lv_font_get_line_height(glyphs);
    auto *name=detail_text(row,options[i],side,(row_h-lv_font_get_line_height(text))/2,col_w-2*side-(chosen?check+side/2:0),text,
                           LV_TEXT_ALIGN_LEFT,theme::INK);
    lv_label_set_long_mode(name,LV_LABEL_LONG_DOT);lv_obj_remove_flag(name,LV_OBJ_FLAG_CLICKABLE);
    if(chosen){
      auto *mark=detail_text(row,"\U000F012C",col_w-side-check,(row_h-check)/2,check,glyphs,LV_TEXT_ALIGN_RIGHT,theme::ACCENT_ICON);
      lv_obj_remove_flag(mark,LV_OBJ_FLAG_CLICKABLE);
    }
    lv_obj_add_event_cb(row,[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));},LV_EVENT_SHORT_CLICKED,
                        (void*)(intptr_t)(SELECT_OPTION_FIRST+i));
    if(detail_action_count<32)detail_actions[detail_action_count++]=row;
  }
  if(!paged)return;
  // The same pager as the tile pages and the settings page: a chevron in each half, the dots between them.
  const int py=top+card_h+gap,half=card_w/2-ui::px(10);
  const int chevron_h=lv_font_get_line_height(glyphs);
  auto *dots=lv_obj_create(detail_root);lv_obj_remove_style_all(dots);
  lv_obj_set_pos(dots,x,py);lv_obj_set_size(dots,card_w,pager_h);
  lv_obj_remove_flag(dots,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(dots,LV_OBJ_FLAG_CLICKABLE);
  settings_screen::page_dots(dots,select_page,pages,large);
  for(int side=0;side<2;++side){
    const bool can=side?select_page<pages-1:select_page>0;
    auto *bar=lv_obj_create(detail_root);lv_obj_remove_style_all(bar);
    lv_obj_set_pos(bar,side?x+card_w-half:x,py);lv_obj_set_size(bar,half,pager_h);
    lv_obj_remove_flag(bar,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(bar,LV_OPA_COVER,LV_STATE_PRESSED);lv_obj_set_style_bg_color(bar,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
    lv_obj_set_style_radius(bar,ui::px(large?12:8),0);
    auto *glyph=detail_text(bar,side?"\U000F0142":"\U000F0141",ui::px(6),(pager_h-chevron_h)/2,half-ui::px(12),glyphs,
                            side?LV_TEXT_ALIGN_RIGHT:LV_TEXT_ALIGN_LEFT,can?theme::INK:theme::CHEVRON);
    lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
    if(can){overlay_card::touchable(bar,pager_h);lv_obj_add_event_cb(bar,select_pager_event,LV_EVENT_CLICKED,(void*)(intptr_t)(side?1:-1));}
    else lv_obj_remove_flag(bar,LV_OBJ_FLAG_CLICKABLE);
  }
}
// ---- Vacuum card ----
// A robot with its state and battery, the two commands used most, and one block that says how it cleans:
// the cleaning mode, then suction and water. Only the rows the chosen mode uses are shown, and they sit
// below the mode, so a tap never moves the control under the finger. Native shapes and labels only.
// Native shapes keep the robot crisp without image buffers or extra layers.
inline lv_obj_t *detail_shape(lv_obj_t *parent,int x,int y,int w,int h,uint32_t color,int radius){
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_set_pos(o,x,y);lv_obj_set_size(o,w,h);
  lv_obj_set_style_radius(o,radius,0);lv_obj_set_style_bg_color(o,lv_color_hex(color),0);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
  lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);return o;
}
inline lv_obj_t *detail_shape(lv_obj_t *parent,int x,int y,int w,int h,theme::Role role,int radius){
  return detail_shape(parent,x,y,w,h,theme::hex(role),radius);
}
// The status line under a tile's name, once its room is known. LVGL cuts the end of a line that doesn't fit, which
// is where this line carries its news, so (firmware 0.2.76+):
//   `shorter`  another wording of the whole line, taken when the full one doesn't fit ("Yest. 9:15 PM");
//   `tail`     the end that has to stay readable (a robot's battery): the words in front of it take the dots,
//              "Angedockt / 10 %" becomes "Angedo… / 10 %".
// A line that fits, or a room too small for the tail itself, is left to LVGL as before.
// True when `face` has a glyph for every character of `text`: a board's fonts carry listed glyphs only, and a
// letter outside the list draws as nothing.
inline bool face_covers(const lv_font_t *face,const std::string &text){
  size_t i=0;lv_font_glyph_dsc_t dsc;
  while(uint32_t cp=header_bar::next_codepoint(text,i))if(!lv_font_get_glyph_dsc(face,&dsc,cp,0))return false;
  return true;
}
inline void fit_value(lv_obj_t *obj,const std::string &value,const std::string &shorter,const std::string &tail,int room){
  const lv_font_t *font=lv_obj_get_style_text_font(obj,LV_PART_MAIN);
  if(!font||room<=0||text_width(value,font)<=room)return;
  if(!shorter.empty()&&shorter!=value&&text_width(shorter,font)<=room){label(obj,shorter);return;}
  if(tail.empty()||value.size()<=tail.size())return;
  static const std::string dots="…";
  const int head_room=room-text_width(dots+tail,font);
  if(head_room<=0)return;
  const std::string head=value.substr(0,value.size()-tail.size());
  std::string cut;
  for(size_t i=0;i<head.size();){
    size_t next=i+1;
    while(next<head.size()&&(static_cast<unsigned char>(head[next])&0xC0)==0x80)++next;
    if(text_width(head.substr(0,next),font)>head_room)break;
    cut=head.substr(0,next);i=next;
  }
  while(!cut.empty()&&cut.back()==' ')cut.pop_back();
  label(obj,cut+dots+tail);
}
// The state colour, as Home Assistant colours a vacuum: teal while cleaning, blue on the way back, amber
// when paused, red on an error; a docked or idle robot keeps the card's own blue. `tint` is the halo.
struct VacuumLook { uint32_t accent, tint; };
inline VacuumLook vacuum_look(const std::string &state){
  using namespace theme::ha;
  const uint32_t accent=state=="cleaning"?TEAL:state=="returning"?BLUE:state=="paused"?ORANGE:state=="error"?RED:SKY;
  // A robot at rest has the quietest halo.
  return {accent,theme::tint(accent,accent==SKY?22:36)};
}
// A robot seen from above on a halo: a white body with a rim, the laser turret, a light bar in the state colour.
inline void vacuum_robot(lv_obj_t *parent,int x,int y,int size,const VacuumLook &look){
  auto *halo=detail_shape(parent,x,y,size,size,look.tint,size/2);
  int r=size*72/100,rim=std::max(1,size/44);
  auto *body=detail_shape(halo,(size-r)/2,(size-r)/2,r,r,theme::ROBOT_BODY,r/2);
  lv_obj_set_style_border_width(body,rim,0);lv_obj_set_style_border_color(body,theme::color(theme::ROBOT_RIM),0);
  int c=r-2*rim;auto s=[&](int v){return std::max(1,v*c/100);};
  detail_shape(body,s(32),s(10),s(36),s(36),theme::ROBOT_TOP,s(18));
  detail_shape(body,s(41),s(19),s(18),s(18),theme::ROBOT_LENS,s(9));
  detail_shape(body,s(31),s(70),s(38),std::max(3,s(7)),look.accent,s(4));
}
// A battery like a phone's: outline, level fill (red below 20 %) and a small cap.
inline void vacuum_battery(lv_obj_t *parent,int x,int y,int w,int h,float level){
  int line=std::max(1,h/7),fill_w=w-4*line,fill=std::clamp((int)std::lround(fill_w*level/100.0f),0,fill_w);
  auto *shell=detail_shape(parent,x,y,w,h,theme::CARD,std::max(2,h/4));
  lv_obj_set_style_bg_opa(shell,LV_OPA_TRANSP,0);
  lv_obj_set_style_border_width(shell,line,0);lv_obj_set_style_border_color(shell,theme::color(theme::BATTERY),0);
  if(fill)detail_shape(shell,line,line,fill,h-4*line,level<20?theme::foreground(theme::ha::ALARM):theme::hex(theme::SLATE),std::max(1,h/9));
  detail_shape(parent,x+w,y+h*3/10,std::max(2,line+1),h-2*(h*3/10),theme::BATTERY,1);
}
// Battery meter, level and a green bolt while charging, in one row from `x`; returns the row's width.
// Without a parent it only measures.
inline int vacuum_power(lv_obj_t *parent,const Tile &t,int x,int y,const lv_font_t *font,bool large){
  const lv_font_t *bolt_font=large && watch_icon_font?watch_icon_font:mini_icon_font;
  std::string percent=screen_text::percent((int)std::lround(t.battery));
  int h=lv_font_get_line_height(font),meter_w=ui::px(large?30:22),meter_h=ui::px(large?15:11),gap=ui::px(large?10:6),words=text_width(percent,font);
  int bolt_w=t.extra().charging && bolt_font?text_width("\U000F0241",bolt_font):0;
  int width=meter_w+3+gap+words+(bolt_w?gap/2+bolt_w:0);
  if(!parent)return width;
  vacuum_battery(parent,x,y+(h-meter_h)/2,meter_w,meter_h,t.battery);
  int px=x+meter_w+3+gap;
  detail_text(parent,percent,px,y,words+2,font,LV_TEXT_ALIGN_LEFT,theme::MUTED);
  if(bolt_w)detail_text(parent,"\U000F0241",px+words+gap/2,y+(h-lv_font_get_line_height(bolt_font))/2,bolt_w+2,bolt_font,LV_TEXT_ALIGN_LEFT,theme::foreground(theme::ha::CHARGING));
  return width;
}
// Put a detail_button's words in `font`, sized to the words and centred (or at `x` when given).
inline lv_obj_t *button_words(lv_obj_t *button,const lv_font_t *font,uint32_t color,int available,int x=-1){
  auto *label=lv_obj_get_child(button,0);
  lv_obj_set_style_text_font(label,font,0);lv_obj_set_style_text_color(label,lv_color_hex(color),0);
  lv_obj_set_size(label,std::min(available,text_width(lv_label_get_text(label),font)+2),lv_font_get_line_height(font));
  if(x<0)lv_obj_center(label);else lv_obj_align(label,LV_ALIGN_LEFT_MID,x,0);
  return label;
}
// A command button with its icon before the words, the two centred as one group.
inline lv_obj_t *vacuum_command(const char *icon,const char *text,int x,int y,int w,int h,int command,bool primary,
                                const lv_font_t *font,const lv_font_t *icon_font,int radius){
  auto *button=detail_button(text,x,y,w,h,command);
  const uint32_t ink=theme::hex(primary?theme::ON_ACCENT:theme::INK);
  lv_obj_set_style_radius(button,radius,0);
  lv_obj_set_style_bg_color(button,theme::color(primary?theme::ACCENT:theme::CARD),0);
  if(!primary){
    lv_obj_set_style_border_width(button,1,0);lv_obj_set_style_border_color(button,theme::color(theme::LINE),0);
    lv_obj_set_style_bg_color(button,theme::color(theme::KEY),LV_STATE_PRESSED);
  }
  int gap=std::max(6,h/7),icon_w=text_width(icon,icon_font),words=text_width(text,font);
  int group=icon_w+gap+words,left=std::max(4,(w-group)/2);
  auto *glyph=lv_label_create(button);lv_label_set_text(glyph,icon);lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(glyph,icon_font,0);lv_obj_set_style_text_color(glyph,lv_color_hex(ink),0);
  lv_obj_align(glyph,LV_ALIGN_LEFT_MID,left,0);
  button_words(button,font,ink,w-left-icon_w-gap-4,left+icon_w+gap);
  return button;
}
// A segmented control: one rounded track, each option as wide as its words plus an equal share of the room
// left, the chosen one filled in blue; `chosen` is the option's place in the list, -1 for none. The options
// answer as first..first+5. However thin the row is drawn, each option keeps a finger's worth of touch area,
// so a segmented row on a short panel is still hittable (overlay_card::touchable).
inline void segments(int x,int y,int w,int h,const std::vector<std::string> &labels,int chosen,int first,uint32_t track,bool border,const lv_font_t *font,const lv_font_t *smaller=nullptr){
  int n=std::min<int>((int)labels.size(),6);if(n<=0||w<=0||h<=0)return;
  auto *bar=detail_shape(detail_root,x,y,w,h,track,h/2);
  if(border){lv_obj_set_style_border_width(bar,1,0);lv_obj_set_style_border_color(bar,theme::color(theme::LINE),0);}
  int inset=std::max(3,h/12),room=w-2*inset,words=0;int widths[6];
  for(int i=0;i<n;++i)words+=text_width(labels[i],font);
  // A narrow row reads better in smaller letters than in "A…" and "Med…": the words shrink before they are cut.
  if(words+n*ui::px(10)>room&&smaller&&smaller!=font&&lv_font_get_line_height(smaller)<=h-2*inset)font=smaller;
  words=0;
  for(int i=0;i<n;++i){widths[i]=text_width(labels[i],font);words+=widths[i];}
  int share=(room-words)/n;
  int sx=x+inset;
  for(int i=0;i<n;++i){
    int sw=i==n-1?x+w-inset-sx:(words<=room?widths[i]+share:room/n);
    bool selected=i==chosen;
    auto *segment=detail_button(labels[i].c_str(),sx,y+inset,sw,h-2*inset,first+i);
    lv_obj_set_style_radius(segment,(h-2*inset)/2,0);
    lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT),0);
    lv_obj_set_style_bg_opa(segment,selected?LV_OPA_COVER:LV_OPA_TRANSP,0);
    lv_obj_set_style_bg_opa(segment,LV_OPA_COVER,LV_STATE_PRESSED);
    if(!selected)lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT_TINT),LV_STATE_PRESSED);
    button_words(segment,font,theme::hex(selected?theme::ON_ACCENT:theme::INK),sw-6);
    overlay_card::touchable(segment,h-2*inset);
    sx+=sw;
  }
}
// The vacuum's rows: the same control, showing the value just tapped while Home Assistant has not answered.
inline void vacuum_segments(const Tile &t,const Choice &row,int first,int x,int y,int w,int h,uint32_t track,bool border,const lv_font_t *font){
  const std::string &chosen=tile_controls::shown_value(t,row,esphome::millis());
  int index=-1;
  for(size_t i=0;i<row.values.size();++i)if(row.values[i]==chosen)index=(int)i;
  segments(x,y,w,h,row.labels,index,first,track,border,font,small_font);
}
inline void render_vacuum_detail(Tile &t,bool large,int width,int height,int pad){
  uint32_t now=esphome::millis();
  auto rows=tile_controls::vacuum_rows(t,now);
  const Choice *mode=t.choice('m'),*suction=rows.suction?t.choice('s'):nullptr,*water=rows.water?t.choice('w'):nullptr;
  bool automatic=mode && tile_controls::vacuum_role(t,now)=='a';
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *big=watch_font?watch_font:detail_font;
  const lv_font_t *icons=mini_icon_font?mini_icon_font:detail_font;
  VacuumLook look=vacuum_look(t.state);
  bool cleaning=t.state=="cleaning",paused=t.state=="paused";
  bool battery=std::isfinite(t.battery),on_the_way=cleaning||paused||t.state=="returning";
  int inner=width-2*pad,gap=ui::px(large?12:6),radius=lv_obj_get_style_radius(widgets[0].tile,LV_PART_MAIN);
  std::string state=t.loading(now)?tr(txt::tile_command_sent):detail_state(t);
  // A robot with little to set gets a hero on the small screen too; one with mode and water rows uses a status row.
  bool small_hero=!large && !mode && !t.choice('w');
  int y=ui::px(large?92:52);
  // The blocks of the card, and what each of them may give up when the glass is shorter than they ask for
  // (a 800 x 480 panel at 217 dpi asked for 550 px). The portrait is the first to give, the keys the last.
  const bool hero_form=large||small_hero;
  int hero_h=ui::px(large?108:60),action_h=ui::px(large?54:(small_hero?40:36));
  int mode_h=ui::px(large?48:34),row_h=ui::px(large?44:32),step=ui::px(large?10:6),edge=ui::px(large?14:0);
  const int note_h=lv_font_get_line_height(text),line_h=lv_font_get_line_height(text);
  const bool any_row=mode||suction||water;
  auto block_h=[&]{
    return (mode?mode_h:0)+(suction?(mode?step:0)+row_h:0)+(water?((mode||suction)?step:0)+row_h:0)+
           (automatic?step+note_h+step:0);
  };
  auto total_h=[&]{
    return y+(hero_form?hero_h+gap:line_h+gap+ui::px(4))+action_h+gap+(any_row?block_h()+2*edge:0)+ui::px(large?18:6);
  };
  if(total_h()>height){
    const int rows_shown=(suction?1:0)+(water?1:0);
    const int steps=(suction&&mode?1:0)+(water&&(mode||suction)?1:0)+(automatic?2:0);
    ui::shrink({{&hero_h,ui::px(large?76:48)},
                {&step,ui::px(4),std::max(1,steps)},
                {&mode_h,ui::touch_min()},
                {&row_h,std::max(ui::touch_min()*3/4,note_h+ui::px(6)),std::max(1,rows_shown)},
                {&edge,ui::px(4),2},
                {&action_h,ui::touch_min()},
                {&gap,ui::px(4),3},
                {&y,ui::px(large?64:40)}},
               total_h()-height);
  }
  if(hero_form){
    int robot=std::min(ui::px(large?84:48),hero_h-ui::px(large?12:6));
    int edge_hero=ui::px(large?12:6);
    auto *hero=detail_card(pad,y,inner,hero_h);
    vacuum_robot(hero,edge_hero,(hero_h-robot)/2,robot,look);
    // Locate, when the robot can do it (VacuumEntityFeature.LOCATE; unknown features keep the button).
    bool locate=large && (!t.supported || (t.supported & tile_controls::feature::VACUUM_LOCATE));
    int key=std::min(ui::px(48),hero_h-ui::px(8)),text_x=edge_hero+robot+(ui::px(large?18:12)),text_w=inner-text_x-(locate?key+2*edge_hero:edge_hero);
    int line=lv_font_get_line_height(big),text_h=lv_font_get_line_height(text),space=ui::px(large?6:3);
    bool room=on_the_way && !t.extra().room.empty();
    int block=line+(room?space+text_h:0)+(battery?space+text_h:0),ty=(hero_h-block)/2;
    detail_badge_status=detail_text(hero,state,text_x,ty,text_w,big,LV_TEXT_ALIGN_LEFT,theme::INK);
    ty+=line;
    if(room){ty+=space;detail_text(hero,t.extra().room,text_x,ty,text_w,text,LV_TEXT_ALIGN_LEFT,theme::MUTED);ty+=text_h;}
    if(battery){ty+=space;vacuum_power(hero,t,text_x,ty,text,large);}
    if(locate){
      auto *find=detail_button("",pad+inner-edge_hero-key-6,y+(hero_h-key)/2,key,key,3);
      lv_obj_set_style_radius(find,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(find,theme::color(theme::TRACK),0);
      lv_obj_set_style_bg_color(find,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
      auto *glyph=lv_obj_get_child(find,0);lv_obj_set_style_text_font(glyph,icons,0);lv_label_set_text(glyph,"\U000F034E");
      lv_obj_set_style_text_color(glyph,theme::color(theme::SLATE),0);lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
    }
    y+=hero_h+gap;
  }else{
    // Status row: a dot in the state colour, the state (and the room on the way), the battery at the right.
    int line=lv_font_get_line_height(text),dot=8,power_w=battery?vacuum_power(nullptr,t,0,0,text,false):0;
    detail_shape(detail_root,pad+2,y+(line-dot)/2,dot,dot,look.accent,dot/2);
    int words=inner-dot-10-power_w-12,state_w=std::min(words,text_width(state,text)+2);
    detail_badge_status=detail_text(detail_root,state,pad+dot+10,y,state_w,text,LV_TEXT_ALIGN_LEFT,theme::INK);
    if(on_the_way && !t.extra().room.empty() && words-state_w>24)
      detail_text(detail_root," · "+t.extra().room,pad+dot+10+state_w,y,words-state_w,text,LV_TEXT_ALIGN_LEFT,theme::MUTED);
    if(battery)vacuum_power(detail_root,t,pad+inner-power_w,y,text,false);
    y+=line+(gap+4);
  }
  // Start (or pause, or resume) as the one blue button, dock beside it.
  int start_w=large?(inner-gap)*2/3:(inner-gap)/2;
  vacuum_command(cleaning?"\U000F03E4":"\U000F040A",tr(cleaning?(large?txt::vacuum_pause_cleaning:txt::vacuum_pause):paused?txt::vacuum_resume:(large?txt::vacuum_start_cleaning:txt::vacuum_clean)),
                 pad,y,start_w,action_h,cleaning?1:0,true,text,icons,large?radius:action_h/2);
  vacuum_command("\U000F05F8",tr(txt::vacuum_dock),pad+start_w+gap,y,inner-start_w-gap,action_h,2,false,text,icons,large?radius:action_h/2);
  y+=action_h+gap;
  if(!mode && !suction && !water){
    auto *note=detail_text(detail_root,tr(txt::vacuum_auto_suction),pad,y+gap,inner,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);(void)note;
    return;
  }
  // How it cleans. The Guition groups the rows on one white card; the small screen has no room for a card.
  const int icon_w=ui::px(large?40:26);
  const int block=block_h();
  const uint32_t track=theme::hex(large?theme::TRACK:theme::CARD);
  if(large)detail_card(pad,y,inner,block+2*edge);
  int x=pad+edge,w=inner-2*edge;
  y+=edge;
  if(mode){vacuum_segments(t,*mode,50,x,y,w,mode_h,track,!large,text);y+=mode_h+step;}
  auto level=[&](const Choice &row,int first,const char *icon){
    detail_text(detail_root,icon,x,y+(row_h-lv_font_get_line_height(icons))/2,icon_w,icons,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
    vacuum_segments(t,row,first,x+icon_w,y,w-icon_w,row_h,track,!large,text);
    y+=row_h+step;
  };
  if(suction)level(*suction,10,"\U000F0210");
  if(water)level(*water,60,"\U000F058C");
  if(automatic){
    bool smart=tile_controls::shown_value(t,*mode,now).find("smart")!=std::string::npos;
    detail_text(detail_root,tr(smart?txt::vacuum_robot_chooses:txt::vacuum_per_room),x,y,w,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
  }
}
// ---- Cover card (firmware 0.2.50+): Home Assistant's cover dialog in the style of the vacuum and climate cards ----
// A tall slider per movement: the position as a blind hanging from the top (a fully open cover shows none of it)
// and the tilt as a handle over slats, each with its value below, like Home Assistant's own sliders. Open, stop
// and close as a row of pill keys under them; the key of the direction the cover moves is filled. A slider
// sends its value when the finger lifts, and shows it while it moves.
// Home Assistant's purple for covers; the track and the slats are its tints.
inline constexpr uint32_t COVER_ACCENT = theme::ha::PURPLE;
inline uint32_t cover_track(){return theme::tint(COVER_ACCENT,37);}
inline uint32_t cover_slats(){return theme::tint(COVER_ACCENT,80);}
inline lv_obj_t *cover_values[2]{};
inline std::string alarm_card_line(const Tile &t);
inline std::string lock_card_line(const Tile &t);
inline std::string cover_status_line(const Tile &t){return t.available()?tile_controls::cover_card_status(t):tr(txt::ha_unavailable);}
// The line under a card's name: the domain that writes its own says it here, so the card, its refresh and the
// second-by-second tick all show the same words.
inline std::string card_status(const Tile &t,bool brief=false){
  const auto d=t.domain();
  if(d=="cover")return cover_status_line(t);
  if(d=="climate"||d=="humidifier")return tile_controls::climate_card_status(t,brief);
  if(d=="alarm_control_panel")return alarm_card_line(t);
  if(d=="lock")return lock_card_line(t);
  return detail_state(t);
}
// Set while the state line lives in a smaller place than its own line (the climate card's caption), so the
// second-by-second refresh writes the same short form the card drew.
inline bool detail_status_brief=false;
inline void cover_slider_event(lv_event_t *e){
  auto *slider=lv_event_get_target_obj(e);auto code=lv_event_get_code(e);
  const bool tilt=(uintptr_t)lv_event_get_user_data(e)==1;
  if(code==LV_EVENT_VALUE_CHANGED){
    // The range reaches past 0 and 1000 only to keep the handle inside the track.
    int raw=lv_slider_get_value(slider);
    if(raw<0||raw>1000){raw=std::clamp(raw,0,1000);lv_slider_set_value(slider,raw,LV_ANIM_OFF);}
    int percent=(int)std::lround(raw/10.0f);
    if(auto *value=cover_values[tilt?1:0])label(value,screen_text::percent(tilt?percent:100-percent));
    return;
  }
  if(code!=LV_EVENT_RELEASED||detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(!fresh()||!t.available()||!screen_input::touch_guard.accept_slider(esphome::millis(),390+(tilt?1:0)))return;
  const auto call=tile_controls::cover_position_action(t,lv_slider_get_value(slider),tilt);
  if(call.valid())action(call.service,t.entity,call.key,call.value);
}
// One slider. The position fills from the top by how far the cover is closed; the tilt has no fill and its
// handle moves over slats drawn behind it, thicker towards the closed end as in Home Assistant.
inline lv_obj_t *cover_slider(lv_obj_t *parent,int x,int y,int w,int h,float value,bool tilt,lv_event_cb_t callback=nullptr,void *user=nullptr){
  int radius=std::max(8,w/7),handle_h=std::max(4,w/18),handle_w=tilt?w*3/5:w*2/5,inset=std::max(6,w/9);
  if(tilt){
    auto *slats=detail_shape(parent,x,y,w,h,cover_track(),radius);
    const int count=10,pitch=(h-2*radius/2)/count;
    for(int i=0;i<count;++i){
      int thick=std::max(2,pitch*(20+60*i/(count-1))/100);
      detail_shape(slats,inset,radius/2+i*pitch+(pitch-thick)/2,w-2*inset,thick,cover_slats(),thick/2);
    }
  }
  auto *slider=lv_slider_create(parent);lv_obj_remove_style_all(slider);
  lv_obj_set_pos(slider,x,y);lv_obj_set_size(slider,w,h);lv_slider_set_orientation(slider,LV_SLIDER_ORIENTATION_VERTICAL);
  lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,lv_color_hex(cover_track()),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,tilt?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_bg_color(slider,lv_color_hex(COVER_ACCENT),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,tilt?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,tilt?lv_color_hex(COVER_ACCENT):theme::color(theme::KNOB),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
  lv_obj_set_style_radius(slider,LV_RADIUS_CIRCLE,LV_PART_KNOB);
  lv_obj_set_style_opa(slider,LV_OPA_50,LV_STATE_DISABLED);
  // LVGL centres the knob on the end of the fill in a square as wide as the slider; the pads shrink it to a
  // handle bar. The position's handle sits inside the blind, an inset above its edge; the tilt's is centred.
  int side=-(w-handle_w)/2;
  lv_obj_set_style_pad_left(slider,side,LV_PART_KNOB);lv_obj_set_style_pad_right(slider,side,LV_PART_KNOB);
  if(tilt){
    int squeeze=-(w-2*handle_h)/2;
    lv_obj_set_style_pad_top(slider,squeeze,LV_PART_KNOB);lv_obj_set_style_pad_bottom(slider,squeeze,LV_PART_KNOB);
    // A margin past both ends keeps the handle on the track at 0 and 100 %.
    int margin=1000*(inset+handle_h)/std::max(1,h-2*(inset+handle_h));
    lv_slider_set_range(slider,-margin,1000+margin);
    lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround(std::clamp(value,0.0f,100.0f)*10):500,LV_ANIM_OFF);
  }else{
    lv_obj_set_style_pad_top(slider,inset+handle_h-w/2,LV_PART_KNOB);lv_obj_set_style_pad_bottom(slider,1-inset-w/2,LV_PART_KNOB);
    // Reversed, the fill hangs from the top; the stub past 0 holds the handle of a cover that is fully open.
    int stub=inset+handle_h+inset,below=1000*stub/std::max(1,h-stub);
    lv_slider_set_range(slider,1000,-below);
    lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround((100.0f-std::clamp(value,0.0f,100.0f))*10):0,LV_ANIM_OFF);
  }
  // A thin track is fine to look at, not to hit: the touch area is grown to a finger's size.
  overlay_card::touchable(slider,w);
  if(callback){lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_set_ext_click_area(slider,0);lv_obj_add_event_cb(slider,callback,LV_EVENT_ALL,user);}
  else {
  lv_obj_add_event_cb(slider,cover_slider_event,LV_EVENT_VALUE_CHANGED,(void*)(uintptr_t)(tilt?1:0));
  lv_obj_add_event_cb(slider,cover_slider_event,LV_EVENT_RELEASED,(void*)(uintptr_t)(tilt?1:0));
  if(detail_action_count<32)detail_actions[detail_action_count++]=slider;
  }
  return slider;
}
// A row of pill keys with an icon each, as the climate card's modes. A key that cannot move the cover further
// is drawn disabled and left out of the keys the card enables again once Home Assistant answers.
inline void cover_key_row(const std::array<tile_controls::Key,3> &keys,unsigned count,int x,int y,int w,int h,int gap,const lv_font_t *icons){
  int key_w=count?(w-gap*((int)count-1))/(int)count:0;
  for(unsigned i=0;i<count;++i){
    const auto &key=keys[i];
    auto *button=detail_button("",x+(int)i*(key_w+gap),y,key_w,h,70+key.command);
    lv_obj_set_style_radius(button,h/2,0);
    lv_obj_set_style_bg_color(button,key.checked?lv_color_hex(COVER_ACCENT):theme::color(theme::CARD),0);
    lv_obj_set_style_bg_color(button,key.checked?lv_color_hex(theme::ha::PURPLE_PRESSED):theme::color(theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(button,key.checked?0:1,0);lv_obj_set_style_border_color(button,theme::color(theme::LINE),0);
    auto *glyph=lv_obj_get_child(button,0);
    lv_obj_set_style_text_font(glyph,icons,0);lv_label_set_text(glyph,key.icon);
    lv_obj_set_style_text_color(glyph,theme::color(key.checked?theme::ON_ACCENT:theme::INK),0);
    lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
    if(key.disabled){lv_obj_add_state(button,LV_STATE_DISABLED);if(detail_action_count && detail_actions[detail_action_count-1]==button)--detail_action_count;}
  }
}
// A battery-powered cover shows its level at the top right, across from the back key: the meter over the
// percentage, red below 20 % (the battery sensor of its device, app 0.2.58+).
inline void cover_battery(const Tile &t,bool large,int width){
  if(!std::isfinite(t.battery))return;
  const lv_font_t *font=large?detail_font:(control_font?control_font:detail_font);
  int bar=ui::px(large?60:40),bar_x=ui::px(large?16:10),bar_y=ui::px(large?16:8),meter_w=ui::px(large?30:22),meter_h=ui::px(large?15:11),gap=ui::px(large?4:2);
  int level=(int)std::lround(std::clamp(t.battery,0.0f,100.0f));
  int line=lv_font_get_line_height(font),block=meter_h+gap+line,cx=width-bar_x-bar/2,y=bar_y+(bar-block)/2;
  vacuum_battery(detail_root,cx-meter_w/2-1,y,meter_w,meter_h,t.battery);
  detail_text(detail_root,screen_text::percent(level),cx-bar/2-8,y+meter_h+gap,bar+16,font,LV_TEXT_ALIGN_CENTER,theme::MUTED);
}
// A blind's slider is dragged, so it needs millimetres of glass, not a share of it: a panel that is wide and
// short (800 x 480 at 217 dpi, a 480 x 272 strip) cannot give a stack of slider, value and keys that height
// while half its width stays empty. Such a card stands in two columns instead: the sliders at their full
// height on the left, the keys beside them.
inline int cover_slider_min(bool large){return ui::mm(large?22:16);}
inline int cover_need_height(const Tile &t,bool large){
  auto card=tile_controls::cover_card(t);
  std::array<tile_controls::Key,3> keys,tilt_keys;
  const unsigned key_count=card.keys?tile_controls::cover_keys(t,keys):0;
  const unsigned tilt_count=card.tilt_keys?tile_controls::cover_tilt_keys(t,tilt_keys):0;
  const int rows=(key_count?1:0)+(tilt_count?1:0),gap=ui::px(large?12:6);
  const int text_h=lv_font_get_line_height(large?detail_font:(control_font?control_font:detail_font));
  const int value_h=lv_font_get_line_height(watch_font?watch_font:detail_font);
  const int box=cover_slider_min(large)+(large?value_h+text_h:0)+2*ui::px(large?16:6);
  return ui::px(large?108:72)+box+gap+rows*ui::px(large?64:38)+(rows>1?gap:0)+ui::px(large?18:6);
}
inline int cover_columns(const Tile &t,bool large){
  const auto card=tile_controls::cover_card(t);
  if(!card.position&&!card.tilt)return 1;   // a garage door has no slider to make tall
  return overlay_card::columns(cover_need_height(t,large),ui::mm(30));
}
inline void render_cover_detail(Tile &t,bool large,int width,int height,int pad,int columns=1){
  auto card=tile_controls::cover_card(t);
  cover_battery(t,large,width);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *big=watch_font?watch_font:detail_font;
  cover_values[0]=cover_values[1]=nullptr;
  int inner=width-2*pad,gap=ui::px(large?12:6),key_h=ui::px(large?64:38),bottom=height-(ui::px(large?18:6));
  // The tile icons' own size where it fits the keys (42 px on the Guition, 28 on the CYD).
  const lv_font_t *key_icons=widgets[0].icon_font && lv_font_get_line_height(widgets[0].icon_font)<=key_h-6?widgets[0].icon_font:(mini_icon_font?mini_icon_font:detail_font);
  std::array<tile_controls::Key,3> keys,tilt_keys;
  unsigned key_count=card.keys?tile_controls::cover_keys(t,keys):0,tilt_count=card.tilt_keys?tile_controls::cover_tilt_keys(t,tilt_keys):0;
  int rows=(key_count?1:0)+(tilt_count?1:0);
  int top=ui::px(large?108:72);
  const int n=(card.position?1:0)+(card.tilt?1:0);
  // Two columns on glass that is wide and short: the sliders keep the whole height on the left, the keys
  // stand beside them. A card in one column is the stack it has always been.
  const bool split=columns>=2 && n>0;
  const int edge=split?ui::px(16):(large?16:6);
  const int slider_w=split?ui::px(76):ui::px(large?(n==2?120:140):(n==2?48:56));
  const int slider_gap=split?ui::px(32):(large?ui::px(48):(n==2?16:0));
  int box_w=inner,keys_w=inner,keys_x=pad,keys_y=0,box_h=0;
  if(split){
    box_w=std::min(inner-ui::mm(30)-ui::column_gap(),n*slider_w+(n-1)*slider_gap+2*edge);
    keys_w=inner-box_w-ui::column_gap();
    keys_x=pad+box_w+ui::column_gap();
    box_h=bottom-top;
  }else{
    keys_y=bottom-rows*key_h-(rows>1?gap:0);
    box_h=keys_y-gap-top;
  }
  // The value and the name go under a slider, or beside it on a small screen where that fits. Two sliders
  // beside their values need more width than a 240 px panel in portrait has, and the card then stacks them.
  const int side_label=ui::px(n==2?76:96);
  const bool beside_fits=n*(slider_w+ui::px(8)+side_label)+(n-1)*slider_gap+2*ui::px(6)<=inner;
  const bool under=large||split||!beside_fits;
  if(card.position||card.tilt){
    detail_card(pad,top,box_w,box_h);
    struct Part{bool tilt;float value;const char *caption;};
    Part parts[2];int count=0;
    if(card.position)parts[count++]={false,t.position,tr(txt::cover_position)};
    if(card.tilt)parts[count++]={true,t.extra().tilt,tr(txt::cover_tilt)};
    int value_h=lv_font_get_line_height(big),caption_h=lv_font_get_line_height(text);
    auto percent=[](float value){return std::isfinite(value)?screen_text::percent((int)std::lround(std::clamp(value,0.0f,100.0f))):std::string("--");};
    if(under){
      // Columns: the slider with its value and name below.
      int slider_h=box_h-2*edge-value_h-caption_h+4;
      int x=pad+(box_w-(count*slider_w+(count-1)*slider_gap))/2;
      for(int i=0;i<count;++i,x+=slider_w+slider_gap){
        cover_slider(detail_root,x,top+edge,slider_w,slider_h,parts[i].value,parts[i].tilt);
        int ty=top+edge+slider_h+2,room=slider_w+slider_gap-4;
        cover_values[parts[i].tilt?1:0]=detail_text(detail_root,percent(parts[i].value),x-(room-slider_w)/2,ty,room,big,LV_TEXT_ALIGN_CENTER,theme::INK);
        detail_text(detail_root,parts[i].caption,x-(room-slider_w)/2,ty+value_h,room,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
      }
    }else{
      // The small screen puts the value and name beside each slider.
      int slider_h=box_h-2*edge,label_w=side_label;
      int column=slider_w+8+label_w,x=pad+(box_w-(count*column+(count-1)*slider_gap))/2;
      for(int i=0;i<count;++i,x+=column+slider_gap){
        cover_slider(detail_root,x,top+edge,slider_w,slider_h,parts[i].value,parts[i].tilt);
        int ty=top+(box_h-value_h-caption_h)/2;
        cover_values[parts[i].tilt?1:0]=detail_text(detail_root,percent(parts[i].value),x+slider_w+8,ty,label_w,big,LV_TEXT_ALIGN_LEFT,theme::INK);
        detail_text(detail_root,parts[i].caption,x+slider_w+8,ty+value_h,label_w,text,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
      }
    }
  }else{
    // Open and close only (a garage door, a gate): the cover's icon on a halo and its state, as the vacuum's hero.
    detail_card(pad,top,box_w,box_h);
    const lv_font_t *icon_font=widgets[0].icon_font?widgets[0].icon_font:mini_icon_font;
    int halo=std::min(box_h-24,ui::px(large?120:72));
    auto *ring=detail_shape(detail_root,pad+(box_w-halo)/2,top+(box_h-halo)/2,halo,halo,cover_track(),halo/2);
    if(icon_font){auto *icon=detail_text(ring,icon_for(t),0,(halo-lv_font_get_line_height(icon_font))/2,halo,icon_font,LV_TEXT_ALIGN_CENTER,theme::foreground(COVER_ACCENT));(void)icon;}
  }
  // Beside the sliders the keys stand under each other, like the switch on the wall next to a blind; under
  // them they keep their rows. A card with tilt keys as well falls back to rows when a stack would not fit.
  const int stacked=(int)(key_count+tilt_count);
  const bool stack_keys=split && stacked*key_h+(stacked-1)*gap<=box_h;
  if(stack_keys){
    const int key_w=std::min(keys_w,ui::mm(45));
    const int x=keys_x+(keys_w-key_w)/2;
    int y=top+(box_h-(stacked*key_h+(stacked-1)*gap))/2;
    auto one=[&](const tile_controls::Key &key){
      std::array<tile_controls::Key,3> single{key,{},{}};
      cover_key_row(single,1,x,y,key_w,key_h,gap,key_icons);
      y+=key_h+gap;
    };
    for(unsigned i=0;i<key_count;++i)one(keys[i]);
    for(unsigned i=0;i<tilt_count;++i)one(tilt_keys[i]);
  }else{
    int y=split?top+(box_h-rows*key_h-(rows>1?gap:0))/2:keys_y;
    if(key_count){cover_key_row(keys,key_count,keys_x,y,keys_w,key_h,gap,key_icons);y+=key_h+gap;}
    if(tilt_count)cover_key_row(tilt_keys,tilt_count,keys_x,y,keys_w,key_h,gap,key_icons);
  }
}
// A round key of a card: the - and the + beside a thermostat's setpoint, and the power key in the top bar
// of the thermostat and of a light or fan. It takes a climate_card::Rect because that card asked first;
// every card's rectangle is the same four numbers.
inline lv_obj_t *climate_round_key(const climate_card::Rect &r,const char *icon,const lv_font_t *font,theme::Role fill,theme::Role ink,int command){
  auto *key=detail_button("",r.x,r.y,r.w,r.h,command);
  lv_obj_set_style_radius(key,LV_RADIUS_CIRCLE,0);
  lv_obj_set_style_bg_color(key,theme::color(fill),0);
  lv_obj_set_style_bg_color(key,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
  auto *glyph=lv_obj_get_child(key,0);
  if(font)lv_obj_set_style_text_font(glyph,font,0);
  lv_label_set_text(glyph,icon);
  lv_obj_set_style_text_color(glyph,theme::color(ink),0);
  lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
  return key;
}
// A remote's card (firmware 0.22.0+), what Home Assistant's dialog has for it (more-info-remote.ts): on and off, and its
// activities where it supports them (Harmony, Android TV Remote), each of which turns it on with that activity. The power
// key sits in the top bar across from the back key, where the light's and the thermostat's have theirs; the activities
// are the select card's rows. Home Assistant lists no commands, so a remote's keys are tiles of their own that perform
// remote.send_command.
// A remote's keypad (firmware 0.22.0+): a ring with four arrows round OK, as every TV remote has it, and beside it Back,
// Home and Play/Pause on the left and the volume on the right; on glass too narrow for those columns they stand in a row
// under the ring. Only the keys the remote's integration takes are drawn (catalogue/remote.yaml keypad).
inline void render_remote_keypad(const Tile &t,bool large,int width,int height,int top){
  const auto &keys=t.extra().keypad;
  auto has=[&](int k){return k<(int)keys.size()&&!keys[k].empty();};
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font,*text=control_font?control_font:detail_font;
  const lv_font_t *arrows=tile_icon_font()?tile_icon_font():mini;   // the ring's arrows a size up from the round keys
  // A remote in the hand: a ring of at most about eight centimetres, its round keys the card's own keys, growing with
  // the ring on large glass up to a thumb's width.
  const int pad=overlay_card::pad(),gap=ui::px(large?12:6),most=ui::mm(80),room=height-top-pad,span=width-2*pad;
  std::vector<int> lefts,rights;
  for(int k:{RK_BACK,RK_HOME,RK_PLAY})if(has(k))lefts.push_back(k);
  for(int k:{RK_VOLUME_UP,RK_MUTE,RK_VOLUME_DOWN})if(has(k))rights.push_back(k);
  // The glass decides where the keys stand, never the remote, so every remote on one screen looks alike with fewer keys
  // where it has fewer: a row of six under the ring, two rows of three under it (narrow glass standing up), or a column
  // of three on each side, whichever leaves the largest ring.
  int rows=0;bool below=false;
  auto fit=[&](int key){
    rows=6*key+5*gap<=span?1:3*key+2*gap<=span?2:0;
    const int under=rows?std::min({room-rows*(key+gap),span,most}):0,beside=std::min({room,span-2*(key+gap),most});
    below=under>=beside;
    return std::max(ui::touch_min()*3,below?under:beside);
  };
  int key=std::max(ui::touch_min(),ui::px(large?60:40)),ring=fit(key);
  const int grown=std::min(std::max(key,ring/5),ui::mm(14));
  if(grown>key){key=grown;ring=fit(key);}
  const int x=(width-ring)/2,y=top;
  auto *disc=lv_obj_create(detail_root);lv_obj_remove_style_all(disc);
  lv_obj_set_pos(disc,x,y);lv_obj_set_size(disc,ring,ring);lv_obj_set_style_radius(disc,LV_RADIUS_CIRCLE,0);
  lv_obj_set_style_bg_color(disc,theme::color(theme::KEY),0);lv_obj_set_style_bg_opa(disc,LV_OPA_COVER,0);
  lv_obj_remove_flag(disc,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(disc,LV_OBJ_FLAG_CLICKABLE);
  auto press=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  // The arrows: from the rim to OK's edge, a third of the ring wide, lit while a finger is on them.
  const int ok=ring*2/5,third=ring/3,deep=(ring-ok)/2;
  struct Zone{int k,x,y,w,h;const char *glyph;};
  const Zone zones[]={{RK_UP,third,0,third,deep,"\U000F0143"},{RK_DOWN,third,ring-deep,third,deep,"\U000F0140"},
                      {RK_LEFT,0,third,deep,third,"\U000F0141"},{RK_RIGHT,ring-deep,third,deep,third,"\U000F0142"}};
  for(const auto &z:zones){
    auto *zone=lv_obj_create(disc);lv_obj_remove_style_all(zone);lv_obj_set_pos(zone,z.x,z.y);lv_obj_set_size(zone,z.w,z.h);
    lv_obj_add_flag(zone,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(zone,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_radius(zone,ui::px(large?18:12),0);
    lv_obj_set_style_bg_color(zone,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);lv_obj_set_style_bg_opa(zone,LV_OPA_COVER,LV_STATE_PRESSED);
    auto *glyph=lv_label_create(zone);lv_label_set_text(glyph,z.glyph);lv_obj_set_style_text_font(glyph,arrows,0);
    lv_obj_set_style_text_color(glyph,theme::color(theme::INK),0);lv_obj_center(glyph);
    lv_obj_add_event_cb(zone,press,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)(REMOTE_KEY_FIRST+z.k));
    if(detail_action_count<32)detail_actions[detail_action_count++]=zone;
  }
  // OK in the middle: the card's own white, as the key a thumb rests on.
  auto *centre=lv_obj_create(disc);lv_obj_remove_style_all(centre);lv_obj_set_pos(centre,(ring-ok)/2,(ring-ok)/2);lv_obj_set_size(centre,ok,ok);
  lv_obj_set_style_radius(centre,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(centre,theme::color(theme::CARD),0);lv_obj_set_style_bg_opa(centre,LV_OPA_COVER,0);
  lv_obj_set_style_bg_color(centre,theme::color(theme::CARD_PRESSED),LV_STATE_PRESSED);
  lv_obj_add_flag(centre,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(centre,LV_OBJ_FLAG_SCROLLABLE);
  auto *word=lv_label_create(centre);lv_label_set_text(word,"OK");lv_obj_set_style_text_font(word,text,0);
  lv_obj_set_style_text_color(word,theme::color(theme::INK),0);lv_obj_center(word);
  lv_obj_add_event_cb(centre,press,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)(REMOTE_KEY_FIRST+RK_OK));
  if(detail_action_count<32)detail_actions[detail_action_count++]=centre;
  // The round keys: the remote's own, Back, Home and Play/Pause first, then the volume.
  auto glyph_of=[](int k){
    switch(k){case RK_BACK:return "\U000F17B3";case RK_HOME:return "\U000F02DC";case RK_PLAY:return "\U000F040E";
              case RK_VOLUME_UP:return "\U000F075D";case RK_VOLUME_DOWN:return "\U000F075E";default:return "\U000F075F";}
  };
  auto round_key=[&](int k,int kx,int ky){climate_round_key({kx,ky,key,key},glyph_of(k),mini,theme::KEY,theme::INK,REMOTE_KEY_FIRST+k);};
  auto row=[&](const std::vector<int> &list,int ky){
    const int n=(int)list.size(),step=key+gap,start=(width-(n-1)*step-key)/2;
    for(int i=0;i<n;++i)round_key(list[i],start+i*step,ky);
  };
  if(below&&rows==1){
    std::vector<int> all(lefts);all.insert(all.end(),rights.begin(),rights.end());
    row(all,y+ring+gap);
    return;
  }
  if(below){
    row(lefts,y+ring+gap);
    row(rights,y+ring+gap+(lefts.empty()?0:key+gap));
    return;
  }
  auto column=[&](const std::vector<int> &list,int kx){
    const int n=(int)list.size(),span=n*key+(n-1)*gap,start=y+(ring-span)/2;
    for(int i=0;i<n;++i)round_key(list[i],kx,start+i*(key+gap));
  };
  column(lefts,x-gap-key);
  column(rights,x+ring+gap);
}
inline void render_remote_detail(const Tile &t,bool large,int width,int height,int pad,int top,int bar,int bar_x,int bar_y){
  const bool on=t.state=="on";
  const auto fill=on?theme::ACCENT_TINT:theme::KEY,ink=on?theme::ACCENT_ICON:theme::ICON_OFF;
  if(!t.extra().keypad.empty()){
    // A remote whose keys Home Assistant's integration names: its keypad, the power key in the top bar.
    if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
    auto *power=climate_round_key({width-bar_x-bar,bar_y,bar,bar},tile_controls::glyph::POWER,
                                  mini_icon_font?mini_icon_font:detail_font,fill,ink,LIGHT_POWER);
    lv_obj_move_to_index(power,2);
    render_remote_keypad(t,large,width,height,top);
    overlay_card::centre(detail_root,3);
    detail_placed=true;
    return;
  }
  if(t.extra().options.empty()){
    // Nothing but on and off (a Broadlink, an Apple TV): one big power key in the middle, its state under it.
    const lv_font_t *icons=tile_icon_font();
    const int side=ui::px(large?120:76);
    climate_round_key({(width-side)/2,top,side,side},tile_controls::glyph::POWER,icons?icons:detail_font,fill,ink,LIGHT_POWER);
    if(detail_status)lv_obj_set_y(detail_status,top+side+ui::px(large?12:6));
    return;
  }
  // The activities say what runs and the lit key that it is on, so the card draws no state line of its own. The key
  // stays in the top bar while the rows below it are centred.
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
  auto *key=climate_round_key({width-bar_x-bar,bar_y,bar,bar},tile_controls::glyph::POWER,
                              mini_icon_font?mini_icon_font:detail_font,fill,ink,LIGHT_POWER);
  lv_obj_move_to_index(key,2);
  render_select_detail(t,large,width,height,pad,top,on?t.extra().activity:std::string());
  overlay_card::centre(detail_root,3);
  detail_placed=true;
}
// ---- Light and fan card (firmware 0.2.80): the last card that was built in YAML ----
// A light without colour and a fan open this: a white card with a standing slider, the value under it and what
// it is under that, and the power key in the top bar across from the back key, where the thermostat has it. A
// light with colour or a colour temperature opens the colour card instead, as it always did.
//
// Until now this was `brightness_overlay`: a full-screen widget tree that sat in the LVGL tree whether it was
// open or not, eight sizes per board file, its own scripts for the preview and the send, and a slider whose
// fill was rounded less than its track, which made LVGL draw it through a buffer of 61 KB (0.2.93). It is a
// card like the others now - light_card.h says where the parts go, this draws them, the card is made when it
// opens and cleaned away when it closes - and the value it sends goes the way a tile's own slider goes
// (commit_slider: the 1 % floor of a light, the held value while it fades, the touch guard).
inline lv_obj_t *light_value=nullptr;

// What the board brings to the card: its class, the fonts it writes with and its top bar.
inline light_card::Metrics light_metrics(bool large) {
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  light_card::Metrics m;
  m.large=large;
  m.value_h=lv_font_get_line_height(big);
  m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):ui::px(large?42:28);
  m.touch=ui::touch_min();
  m.pad=overlay_card::pad();
  m.bar=ui::px(large?60:40);
  m.bar_x=ui::px(large?16:10);
  m.bar_y=ui::px(large?16:8);
  return m;
}
// One column or two: the stack's own height decides, as it does for the thermostat and the blind.
inline int light_columns(bool large) {
  const auto m=light_metrics(large);
  return overlay_card::columns(light_card::stacked_height(m),m.slider_w()+2*m.edge());
}
// What the card writes beside the slider: the percentage, or the word Home Assistant uses when it is off.
// What the card writes under the slider: the percentage the slider stands at, or Home Assistant's own word for
// a light that is off, unavailable, or on without a brightness of its own.
inline std::string light_value_text(const Tile &t) {
  const int raw=slider_value(t);
  if(t.state=="on"&&raw>0)return screen_text::percent((raw+5)/10);
  return card_status(t);
}
inline void light_slider_event(lv_event_t *e) {
  auto *slider=lv_event_get_target_obj(e);const auto code=lv_event_get_code(e);
  if(code==LV_EVENT_VALUE_CHANGED){
    // The range reaches past its ends only to keep the handle inside the track (slider_handle).
    int raw=lv_slider_get_value(slider);
    if(raw<0||raw>1000){raw=std::clamp(raw,0,1000);lv_slider_set_value(slider,raw,LV_ANIM_OFF);}
    if(light_value)label(light_value,screen_text::percent((int)std::lround(raw/10.0f)));
    return;
  }
  // The send is the tile slider's own: the 1 % floor, the value held while the light fades, the touch guard.
  if(code==LV_EVENT_RELEASED&&screen_input::touch_guard.accept_slider(esphome::millis(),380))commit_slider(detail_index,lv_slider_get_value(slider));
}
// The standing slider of the card, drawn like the blind's: one radius on the track and the fill (a fill rounded
// less than its track costs a layer of tens of kilobytes on every redraw), a handle bar inside the fill.
inline lv_obj_t *light_slider(int x,int y,int w,int h,int raw,uint32_t accent,bool enabled,bool amber) {
  const int radius=std::max(8,w/7),handle_h=std::max(4,w/18),handle_w=w*2/5,inset=std::max(6,w/9);
  auto *slider=lv_slider_create(detail_root);lv_obj_remove_style_all(slider);
  lv_obj_set_pos(slider,x,y);lv_obj_set_size(slider,w,h);lv_slider_set_orientation(slider,LV_SLIDER_ORIENTATION_VERTICAL);
  lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);
  // A light's track is the pale amber Home Assistant gives it; a fan's is the neutral one, so the track
  // never fights the fill's own colour.
  lv_obj_set_style_bg_color(slider,theme::color(amber&&raw>0?theme::AMBER_TRACK:theme::TRACK),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_bg_color(slider,lv_color_hex(accent),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,theme::color(theme::KNOB),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
  lv_obj_set_style_radius(slider,LV_RADIUS_CIRCLE,LV_PART_KNOB);
  lv_obj_set_style_opa(slider,LV_OPA_50,LV_STATE_DISABLED);
  // LVGL centres the knob on the end of the fill in a square as wide as the slider; the pads shrink that square
  // to a handle bar and drop it an inset inside the fill, the way the blind's handle sits inside the blind.
  const int side=-(w-handle_w)/2;
  lv_obj_set_style_pad_left(slider,side,LV_PART_KNOB);lv_obj_set_style_pad_right(slider,side,LV_PART_KNOB);
  lv_obj_set_style_pad_top(slider,-(w-handle_h)/2-inset,LV_PART_KNOB);
  lv_obj_set_style_pad_bottom(slider,-(w-handle_h)/2+inset,LV_PART_KNOB);
  // Room past the bottom end only, so the handle still sits on the track at 0 (the event snaps the value back).
  // Not past the top: the fill is what the value is, and a slider that reached 1000 of a range that ran to
  // 1000 + margin stopped a handle's width short of the top at 100 % - which is exactly what it looked like.
  const int below=1000*(inset+handle_h)/std::max(1,h-(inset+handle_h));
  lv_slider_set_range(slider,-below,1000);
  lv_slider_set_value(slider,std::clamp(raw,0,1000),LV_ANIM_OFF);
  if(!enabled)lv_obj_add_state(slider,LV_STATE_DISABLED);
  lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(slider,light_slider_event,LV_EVENT_ALL,nullptr);
  return slider;
}
inline void render_light_detail(Tile &t,bool large,int width,int height,int columns) {
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  const lv_font_t *icons=tile_icon_font();
  const auto m=light_metrics(large);
  const bool dims=tile_controls::light_dims(t);
  const auto l=light_card::layout(m,width,height,columns,dims);
  detail_placed=true;   // the layout has already put every part where the glass has room for it
  // The big value says what the state line would have said, so the card draws no second one.
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}

  const bool on=t.state=="on";
  const uint32_t accent=tile_controls::accent(t);
  // The power key, across from the back key: lit while the light or the fan is on.
  climate_round_key({l.power.x,l.power.y,l.power.w,l.power.h},tile_controls::glyph::POWER,mini,
                    on?theme::ACCENT_TINT:theme::KEY,on?theme::ACCENT_ICON:theme::ICON_OFF,LIGHT_POWER);

  detail_card(l.card.x,l.card.y,l.card.w,l.card.h);
  // Where the slider stands is the tile's own answer (slider_value), so the strip on the tile and the card it
  // opens never disagree - including the value held in front while a light fades towards it.
  const int raw=on?slider_value(t):0;
  if(dims){
    auto *slider=light_slider(l.slider.x,l.slider.y,l.slider.w,l.slider.h,raw,accent,t.available(),t.domain()=="light");
    overlay_card::touchable(slider,l.slider.w);
  }else if(!l.halo.empty()){
    // A light that only switches: its icon on a round field where the slider would be, lit while it is on, the
    // way the blind's card shows a door that only opens and closes. The power key in the bar does the work.
    // The same two colours the slider's track has, so a light that dims and one that only switches are the
    // same card with the same palette: the light's own pale amber while it is on, the neutral track while off.
    detail_shape(detail_root,l.halo.x,l.halo.y,l.halo.w,l.halo.h,
                 theme::hex(on?theme::AMBER_TRACK:theme::TRACK),l.halo.w/2);
  }
  // The entity's icon rides on the foot of the slider, or in the middle of the round field, where the fill is
  // and a finger is not, as it did on the overlay before it and as Home Assistant draws it.
  if(!l.icon.empty()&&icons&&lv_font_get_line_height(icons)<=l.icon.h+ui::px(4)){
    const uint32_t ink=dims?(raw>0?theme::hex(theme::ON_ACCENT):theme::hex(theme::ICON_OFF))
                           :(on?accent:theme::hex(theme::ICON_OFF));
    auto *glyph=detail_text(detail_root,icon_for(t),l.icon.x,l.icon.y,l.icon.w,icons,LV_TEXT_ALIGN_CENTER,ink);
    lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
  }
  light_value=detail_text(detail_root,light_value_text(t),l.value.x,l.value.y,l.value.w,big,
                          l.columns==2?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,theme::hex(theme::INK));
  // The caption only where the words exist: a light says what the slider is, a fan's speed has no word of its
  // own in the screen's languages and does without (the name at the top says which fan it is).
  if(!l.caption.empty()&&dims&&t.domain()=="light")
    detail_text(detail_root,tr(txt::light_brightness),l.caption.x,l.caption.y,l.caption.w,text,
                l.columns==2?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,theme::hex(theme::SUBTLE));
}
// ---- Climate card (firmware 0.2.80): one computed card on every board ----
// Home Assistant's thermostat dialog in this look, worked out from the entity's own attributes: the state
// under the name, a white card with the setpoint between a round - and a round + key, a key per mode, and a
// white card with a segmented row for the fan and for the swing. Until now every board carried its own table
// of pixels for this card (six layouts in the board file) and only the Guition's table had room for the fan
// and swing rows, which is why a CYD sent them to a second page. climate_card.h works out where the parts go;
// this draws them, and the same card now stands on every board.
inline lv_obj_t *climate_number=nullptr;   // the setpoint itself: a -/+ tap moves it before Home Assistant answers

// What the board brings to the card: its class, the fonts it writes with and where its top bar sits.
inline climate_card::Metrics climate_metrics(bool large){
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *small=small_font?small_font:text;
  const lv_font_t *number=setpoint_font?setpoint_font:(watch_font?watch_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  climate_card::Metrics m;
  m.large=large;
  const lv_font_t *small_number=watch_font?watch_font:(control_font?control_font:detail_font);
  m.number_h=lv_font_get_line_height(number);
  m.number_w=text_width("-88.8°",number);
  m.small_number_h=std::min<int>(m.number_h,lv_font_get_line_height(small_number));
  m.small_number_w=text_width("-88.8°",small_number);
  m.caption_h=lv_font_get_line_height(small);
  m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;
  m.bar=ui::px(large?60:40);m.bar_x=ui::px(large?16:10);m.bar_y=ui::px(large?16:8);
  m.touch=ui::touch_min();
  return m;
}
// Where the card's content begins: under the top bar.
inline int climate_top(const climate_card::Metrics &m){return m.bar_y+m.bar+ui::px(m.large?8:4);}
// One column, or two on glass too short for the stack (a 480 x 272 panel, a wide seven-inch).
inline int climate_columns(const Tile &t,bool large){
  const climate_card::Metrics m=climate_metrics(large);
  const int modes=(int)tile_controls::climate_modes(t).size(),rows=(int)tile_controls::climate_rows(t).size();
  return overlay_card::columns(climate_top(m)+climate_card::need_height(m,modes,rows)+m.margin(),climate_card::min_column(m));
}
inline std::string climate_number_text(const Tile &t){
  const float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  return tile_controls::format_value(shown,tile_controls::edit_step(t),tile_controls::setpoint_suffix(t));
}
// A range (firmware 0.19.0): its two ends side by side in the number's place, as on Home Assistant's thermostat card.
// A tap picks the end the -/+ move (Tile::range_end, the same one the tile's chip shows); that one is drawn in full,
// the other at 70 %.
// A range (heat/cool, firmware 0.25.0): under the number the device's whole span as an LVGL scale, the range on it as
// Home Assistant's dual thermostat draws it (ha-control-circular-slider, renderArc): the low end's colour runs from
// the minimum up to the low target, the high end's from the high target up to the maximum, both at half opacity, and
// the bare track between the two targets. Where the room lies outside the range, the part the device has to cover
// (current to target) is drawn in full, with a mark at the current temperature; inside it nothing marks the room, the
// state line says it. A knob stands on each end; a tap on one chooses the end the -/+ move, and the number shows that
// end. The -/+ and the chosen knob take that side's tint, so what a key moves is always in sight.
inline lv_obj_t *climate_ends[2]={nullptr,nullptr};       // the knob of each end
inline lv_obj_t *climate_now_mark=nullptr;                // the current temperature on the band, while it is outside the range
inline lv_obj_t *climate_keys[2]={nullptr,nullptr};       // the - and +, which take the chosen side's colour
inline int climate_track_x=0,climate_track_w=1,climate_track_y=0,climate_knob_d=24;
inline std::vector<std::string> climate_tick_words;inline std::vector<const char*> climate_tick_src;
inline lv_style_t climate_sec_style[5];inline bool climate_sec_init=false;   // heat 50 %, cool 50 %, heat full, cool full, the bare track
// The swatch a side of a range is drawn in: Home Assistant's heat and cool, as the tiles' own card colours.
inline uint32_t range_tint(uint8_t end){return theme::surface(theme::swatch(end==tile_controls::RANGE_HIGH?"blue":"orange"));}
inline int range_units(const Tile &t,float v){return (int)std::lround((v-t.minimum)/tile_controls::edit_step(t));}
inline int range_x(const Tile &t,float v){
  const float span=std::max(0.01f,t.maximum-t.minimum);
  return climate_track_x+(int)std::lround(std::clamp((v-t.minimum)/span,0.f,1.f)*climate_track_w);
}
// The parts that follow the chosen end and the values: the number, the keys' tint, the knobs and the room's mark.
inline void climate_paint_ends(const Tile &t){
  const float step=tile_controls::edit_step(t);
  const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
  if(climate_number)label(climate_number,tile_controls::format_value(tile_controls::range_end(t,t.range_end),step,"°"));
  for(auto *key:climate_keys)if(key)lv_obj_set_style_bg_color(key,lv_color_hex(range_tint(t.range_end)),0);
  for(uint8_t i=0;i<2;++i){
    if(!climate_ends[i])continue;
    const uint8_t end=i?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW;
    const bool chosen=end==t.range_end;
    const int d=chosen?climate_knob_d:climate_knob_d*3/4;
    lv_obj_set_size(climate_ends[i],d,d);
    lv_obj_set_pos(climate_ends[i],range_x(t,i?high:low)-d/2,climate_track_y-d/2);
    lv_obj_set_style_border_width(climate_ends[i],chosen?ui::px(3):ui::px(2),0);
    lv_obj_set_style_bg_color(climate_ends[i],chosen?lv_color_hex(range_tint(end)):theme::color(theme::CARD),0);
  }
  if(climate_now_mark&&std::isfinite(t.current))lv_obj_set_x(climate_now_mark,range_x(t,t.current)-ui::px(2)/2);
}
inline void climate_end_event(lv_event_t *e){
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  t.range_end=(uint8_t)(uintptr_t)lv_event_get_user_data(e);
  climate_paint_ends(t);
  refresh_tile(detail_index);   // the tile's chip says the same end
}
// One step of a range's chosen end, never past the other end: the number follows the finger at once, tick() sends both
// ends after a short pause.
inline void range_step(Tile &t,int direction){
  const float step=tile_controls::edit_step(t);
  const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
  if(t.range_end==tile_controls::RANGE_HIGH)t.edit_high=tile_controls::step_value(high,step,low,t.maximum,direction);
  else t.edit_value=tile_controls::step_value(low,step,t.minimum,high,direction);
  t.edit_since=esphome::millis();t.edit_sent=false;
}
// A -/+ tap: the number follows the finger at once, tick() sends the last value after a short pause, exactly
// as the -/+ pill on a wide tile does. On a range it moves the chosen end.
inline void climate_step(Tile &t,int direction){
  if(tile_controls::climate_range(t)){
    range_step(t,direction);
    climate_paint_ends(t);
    if(detail_index<model.count)refresh_tile(detail_index);
    return;
  }
  const uint32_t now=esphome::millis();
  const float current=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  t.edit_value=tile_controls::step_value(current,tile_controls::edit_step(t),t.minimum,t.maximum,direction);
  t.edit_since=now;t.edit_sent=false;
  if(climate_number)label(climate_number,climate_number_text(t));
}
// Holding a key steps three times a second.
inline void climate_hold(lv_event_t *e){
  const int direction=(int)(intptr_t)lv_event_get_user_data(e);
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(!fresh()||!t.available()||esphome::millis()-t.edit_since<300)return;
  climate_step(t,direction);
}
// A humidifier's dial (firmware 0.42.0+): Home Assistant's humidity ring (ha-control-circular-slider) round the number,
// as a picture and not a control (the - and + set it, a finger on a small ring would not): a 270 degree track, the part from the minimum to the target filled
// at half strength (from the target to the maximum for a dehumidifier), the part still to go from the humidity now to
// the target in full while the device has work to do, a dot at the humidity now and a white knob at the target.
inline void humidity_ring(const Tile &t,const climate_card::Rect &card,const climate_card::Rect &minus,const climate_card::Rect &plus,bool large){
#if LV_USE_ARC
  const int d=std::min(plus.x-minus.right()-ui::px(large?16:8),card.h-ui::px(large?16:8));
  if(d<ui::px(70))return;
  const int cx=card.cx(),cy=card.cy(),w=std::max(ui::px(large?10:6),d/14);
  const bool off=tile_controls::climate_off(t),dry=t.device_class=="dehumidifier";
  const uint32_t colour=off?theme::hex(theme::OFF):theme::state(tile_controls::accent(t));
  auto arc=[&](int a0,int a1,uint32_t c,lv_opa_t opa){
    if(a1<=a0)return;
    auto *o=lv_arc_create(detail_root);lv_obj_remove_style_all(o);lv_obj_set_size(o,d,d);lv_obj_set_pos(o,cx-d/2,cy-d/2);
    lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_arc_width(o,w,LV_PART_MAIN);lv_obj_set_style_arc_rounded(o,true,LV_PART_MAIN);
    lv_obj_set_style_arc_color(o,lv_color_hex(c),LV_PART_MAIN);lv_obj_set_style_arc_opa(o,opa,LV_PART_MAIN);
    lv_obj_set_style_arc_opa(o,LV_OPA_TRANSP,LV_PART_INDICATOR);
    lv_arc_set_bg_angles(o,a0%360,a1%360);
  };
  const float span=std::max(1.0f,t.maximum-t.minimum);
  auto angle=[&](float v){return 135+(int)std::lround(std::clamp((v-t.minimum)/span,0.0f,1.0f)*270);};
  auto point=[&](int a,int size,uint32_t c,lv_opa_t opa,bool knob){
    const int r=d/2-w/2;
    const int x=cx+(int)std::lround(r*std::cos(a*3.14159265f/180)),y=cy+(int)std::lround(r*std::sin(a*3.14159265f/180));
    auto *o=detail_shape(detail_root,x-size/2,y-size/2,size,size,c,LV_RADIUS_CIRCLE);
    lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_bg_opa(o,opa,0);
    if(knob){lv_obj_set_style_shadow_width(o,ui::px(6),0);lv_obj_set_style_shadow_opa(o,LV_OPA_30,0);}
  };
  arc(135,405,theme::hex(theme::TRACK),LV_OPA_COVER);
  const float target=std::isfinite(t.edit_value)?t.edit_value:t.target;
  if(std::isfinite(target)){
    if(!off)arc(dry?angle(target):135,dry?405:angle(target),colour,LV_OPA_50);
    const bool work=!off&&std::isfinite(t.current)&&(dry?t.current>target:t.current<target);
    if(work)arc(dry?angle(target):angle(t.current),dry?angle(t.current):angle(target),colour,LV_OPA_COVER);
    if(!off&&std::isfinite(t.current))point(angle(t.current),std::max(ui::px(6),w*2/3),theme::hex(theme::INK),LV_OPA_50,false);
    point(angle(target),w+ui::px(large?8:4),theme::hex(theme::CARD),LV_OPA_COVER,true);
  }
#else
  (void)t;(void)card;(void)minus;(void)plus;(void)large;
#endif
}
inline void render_climate_detail(Tile &t,bool large,int width,int height,int columns){
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *small=small_font?small_font:text;
  const lv_font_t *number_font=setpoint_font?setpoint_font:(watch_font?watch_font:detail_font);
  const lv_font_t *tile_icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  const auto modes=tile_controls::climate_modes(t);
  const auto rows=tile_controls::climate_rows(t);
  const climate_card::Metrics m=climate_metrics(large);
  const int top=climate_top(m);
  const bool range=tile_controls::climate_range(t);
  // A range's band takes the place of the word under the number: the knob, a hair of air, and the degrees under the
  // knobs where they stay clear of them.
  climate_card::Metrics mr=m;
  if(range){
    const int knob=std::clamp(m.min_row()-ui::px(6),ui::px(18),ui::px(26));
    mr.caption_h=knob+ui::px(4)+m.caption_h;
  }
  auto l=climate_card::layout(mr,width,top,height-m.margin(),(int)modes.size(),(int)rows.size(),columns,range);
  // A humidifier's ring takes the setpoint card's height, the - and + a finger's size at its sides.
  if(tile_controls::humidifier(t)){
    const auto &c=l.setpoint;const int key=std::max(m.touch,ui::px(large?64:40)),in=m.key_inset();
    l.minus={c.x+in,c.cy()-key/2,key,key};l.plus={c.right()-in-key,c.cy()-key/2,key,key};
    const int block=l.number.h+(l.caption.empty()?0:l.caption.h);
    l.number.y=c.cy()-block/2;if(!l.caption.empty())l.caption.y=l.number.bottom();
  }
  const bool off=tile_controls::climate_off(t),known=std::isfinite(tile_controls::edit_target(t))||std::isfinite(t.edit_value);
  const std::string mode=tile_controls::current_mode(t);
  detail_placed=true;   // the layout has already put every block where the glass has room for it

  // The power key, across from the back key: lit while the device runs in any mode.
  climate_round_key(l.power,tile_controls::glyph::POWER,mini,off?theme::KEY:theme::ACCENT_TINT,
                    off?theme::ICON_OFF:theme::ACCENT_ICON,CLIMATE_POWER);
  if(!l.status.empty()){
    detail_status=detail_text(detail_root,card_status(t),l.status.x,l.status.y,l.status.w,text,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  }
  // The setpoint: the number between the two keys, the word under it while there is room.
  detail_card(l.setpoint.x,l.setpoint.y,l.setpoint.w,l.setpoint.h);
  const lv_font_t *key_icons=tile_icons&&lv_font_get_line_height(tile_icons)<=l.minus.h-ui::px(8)?tile_icons:mini;
  auto *down=climate_round_key(l.minus,tile_controls::glyph::MINUS,key_icons,theme::TRACK,theme::INK,CLIMATE_DOWN);
  auto *up=climate_round_key(l.plus,tile_controls::glyph::PLUS,key_icons,theme::TRACK,theme::INK,CLIMATE_UP);
  const float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  if(known&&std::isfinite(shown)&&!tile_controls::climate_range(t)){   // a range stops at the other end in climate_step
    if(shown<=t.minimum)lv_obj_add_state(down,LV_STATE_DISABLED);
    if(shown>=t.maximum)lv_obj_add_state(up,LV_STATE_DISABLED);
  }
  for(lv_obj_t *key:{down,up})lv_obj_add_event_cb(key,climate_hold,LV_EVENT_LONG_PRESSED_REPEAT,(void*)(intptr_t)(key==up?1:-1));
  const lv_font_t *face=l.small_number?(watch_font?watch_font:number_font):number_font;
  if(range){
    // One number, the end last chosen; under it the band (see climate_paint_ends above).
    climate_number=detail_text(detail_root,"",l.number.x,l.number.y,l.number.w,face,LV_TEXT_ALIGN_CENTER,off?theme::OFF:theme::INK);
    climate_keys[0]=down;climate_keys[1]=up;
    const auto &sw=l.caption;
    const float step=tile_controls::edit_step(t);
    const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
    // The knob stays a touch smaller than its row, so it keeps clear of the digits above it.
    climate_knob_d=std::clamp(m.min_row()-ui::px(6),ui::px(18),ui::px(26));
    const int track_h=std::max(ui::px(6),climate_knob_d/3);
    auto *scale=lv_scale_create(detail_root);lv_obj_remove_style_all(scale);
    climate_track_x=sw.x+climate_knob_d/2;climate_track_w=sw.w-climate_knob_d;climate_track_y=sw.y+climate_knob_d/2+ui::px(2);
    // The band's centre line is climate_track_y: the scale draws its main line just inside its top edge. Its side
    // padding holds the band's round ends, which reach half a width past the first and last value.
    lv_obj_set_pos(scale,climate_track_x-track_h/2,climate_track_y-track_h/2);lv_obj_set_size(scale,climate_track_w+track_h,sw.h-climate_knob_d/2-ui::px(2)+track_h/2);
    lv_obj_set_style_pad_left(scale,track_h/2,LV_PART_MAIN);lv_obj_set_style_pad_right(scale,track_h/2,LV_PART_MAIN);
    lv_scale_set_mode(scale,LV_SCALE_MODE_HORIZONTAL_BOTTOM);
    lv_obj_remove_flag(scale,LV_OBJ_FLAG_CLICKABLE);
    const int units=std::max(1,range_units(t,t.maximum));
    lv_scale_set_range(scale,0,units);
    // A tick a degree places the labels; only the ticks with a degree under them are drawn, every 5 or 10 degrees.
    const int degrees=std::max(1,(int)std::lround(t.maximum-t.minimum));
    const int every=degrees>40?10:5;
    lv_scale_set_total_tick_count(scale,degrees+1);
    lv_scale_set_major_tick_every(scale,every);
    lv_scale_set_label_show(scale,true);
    climate_tick_words.clear();climate_tick_src.clear();
    for(int d=0;d<=degrees;d+=every)climate_tick_words.push_back(tile_controls::format_value(t.minimum+d,1,"°"));
    for(auto &w:climate_tick_words)climate_tick_src.push_back(w.c_str());
    climate_tick_src.push_back(nullptr);
    lv_scale_set_text_src(scale,climate_tick_src.data());
    // The main line only sets the band's place; the sections draw it, so no two lines mix at the ends.
    lv_obj_set_style_line_width(scale,track_h,LV_PART_MAIN);lv_obj_set_style_line_opa(scale,LV_OPA_TRANSP,LV_PART_MAIN);
    lv_obj_set_style_line_opa(scale,LV_OPA_TRANSP,LV_PART_ITEMS);lv_obj_set_style_length(scale,0,LV_PART_ITEMS);
    lv_obj_set_style_line_width(scale,1,LV_PART_INDICATOR);lv_obj_set_style_line_color(scale,theme::color(theme::LINE),LV_PART_INDICATOR);
    lv_obj_set_style_length(scale,track_h/2+ui::px(4),LV_PART_INDICATOR);
    // The degrees start under the knobs: the gap after the tick is what the knob reaches past the tick. (pad_bottom
    // of the indicator part is that gap in a straight scale; pad_radial only counts in a round one.)
    lv_obj_set_style_pad_bottom(scale,std::max(0,climate_knob_d/2-(track_h/2+ui::px(4))+ui::px(2)),LV_PART_INDICATOR);
    lv_obj_set_style_text_font(scale,small,LV_PART_INDICATOR);lv_obj_set_style_text_color(scale,theme::color(theme::SUBTLE),LV_PART_INDICATOR);
    if(!climate_sec_init){for(auto &st:climate_sec_style)lv_style_init(&st);climate_sec_init=true;}
    const char *sides[2]={"heat","cool"};
    for(int i=0;i<5;++i){
      lv_style_set_line_width(&climate_sec_style[i],track_h);
      lv_style_set_line_color(&climate_sec_style[i],i==4?theme::color(theme::TRACK):lv_color_hex(tile_controls::mode_color(sides[i%2])));
      lv_style_set_line_opa(&climate_sec_style[i],i<2?LV_OPA_50:LV_OPA_COVER);
    }
    const int lo=range_units(t,low),hi=range_units(t,high);
    const int cur=std::isfinite(t.current)?std::clamp(range_units(t,t.current),0,units):-1;
    auto band=[&](int style,int from,int to){
      if(to<from)return;
      auto *sec=lv_scale_add_section(scale);
      lv_scale_set_section_range(scale,sec,from,to);
      lv_scale_set_section_style_main(scale,sec,&climate_sec_style[style]);
    };
    band(4,lo,hi);band(0,0,lo);band(1,hi,units);
    const bool cold=cur>=0&&cur<=lo,hot=cur>=0&&cur>=hi;
    if(cold)band(2,cur,lo);
    if(hot)band(3,hi,cur);
    // A section's line has square ends (the scale reads only its width, colour and opacity): the band's two round
    // ends are two discs, opaque in the half-mixed colour, so where they overlap the section's end nothing darkens.
    for(int i=0;i<2;++i){
      auto *cap=detail_shape(detail_root,(i?climate_track_x+climate_track_w:climate_track_x)-track_h/2,climate_track_y-track_h/2,track_h,track_h,theme::mix(tile_controls::mode_color(sides[i]),theme::hex(theme::CARD),128),LV_RADIUS_CIRCLE);
      lv_obj_remove_flag(cap,LV_OBJ_FLAG_CLICKABLE);
    }
    for(uint8_t i=0;i<2;++i){
      auto *knob=detail_button("",0,0,climate_knob_d,climate_knob_d,i?CLIMATE_END_HIGH:CLIMATE_END_LOW);
      lv_obj_set_style_radius(knob,LV_RADIUS_CIRCLE,0);
      lv_obj_set_style_bg_color(knob,theme::color(theme::CARD),0);
      lv_obj_set_style_bg_color(knob,lv_color_hex(range_tint(i?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW)),LV_STATE_PRESSED);
      lv_obj_set_style_border_color(knob,lv_color_hex(tile_controls::mode_color(sides[i])),0);
      lv_obj_set_style_shadow_width(knob,ui::px(6),0);lv_obj_set_style_shadow_opa(knob,LV_OPA_20,0);
      lv_obj_set_ext_click_area(knob,ui::touch_min()/2);
      climate_ends[i]=knob;
    }
    // The room's mark: a line a little taller than the band, only while the device has work to do. Home Assistant
    // cuts a gap in its arc of 24 px; in a band this thin a gap reads as a stain, a line reads.
    climate_now_mark=detail_shape(detail_root,0,climate_track_y-track_h/2-ui::px(2),ui::px(2),track_h+ui::px(4),theme::hex(theme::INK),ui::px(1));
    lv_obj_remove_flag(climate_now_mark,LV_OBJ_FLAG_CLICKABLE);
    if(!cold&&!hot)lv_obj_add_flag(climate_now_mark,LV_OBJ_FLAG_HIDDEN);
    climate_paint_ends(t);
  }else{
    if(tile_controls::humidifier(t))humidity_ring(t,l.setpoint,l.minus,l.plus,large);
    climate_number=detail_text(detail_root,climate_number_text(t),l.number.x,l.number.y,l.number.w,face,LV_TEXT_ALIGN_CENTER,off?theme::OFF:theme::INK);
  }
  // The word under the number, or what the thermostat is doing when the glass had no room for a line of its own.
  if(!range&&!l.caption.empty()){
    auto *caption=detail_text(detail_root,l.caption_is_status?card_status(t,true):std::string(tr(txt::climate_target)),
                              l.caption.x,l.caption.y,l.caption.w,small,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
    if(l.caption_is_status){detail_status=caption;detail_status_brief=true;}
  }
  // One key per mode, in Home Assistant's colour for the one in use. A device with one mode shows none: the
  // power key already turns it on and off.
  if(l.mode_count){
    const int shown_modes=std::min<int>(l.mode_count,(int)modes.size());
    const int key_w=(l.modes.w-(shown_modes-1)*l.mode_gap)/std::max(1,shown_modes);
    // More modes than keys: the mode in use takes the last key, so the card always says where it stands.
    std::vector<std::string> keys(modes.begin(),modes.begin()+shown_modes);
    std::vector<int> commands(shown_modes);
    for(int i=0;i<shown_modes;++i)commands[i]=CLIMATE_MODE_FIRST+i;
    if((int)modes.size()>shown_modes)
      for(int i=shown_modes;i<(int)modes.size();++i)
        if(modes[i]==mode){keys[shown_modes-1]=modes[i];commands[shown_modes-1]=CLIMATE_MODE_FIRST+i;}
    const lv_font_t *mode_icons=tile_icons&&lv_font_get_line_height(tile_icons)<=l.modes.h-ui::px(6)?tile_icons:mini;
    for(int i=0;i<shown_modes;++i){
      const bool selected=!off&&keys[i]==mode;
      const uint32_t colour=tile_controls::humidifier(t)?tile_controls::accent(t):tile_controls::mode_color(keys[i]);
      auto *key=detail_button("",l.modes.x+i*(key_w+l.mode_gap),l.modes.y,key_w,l.modes.h,commands[i]);
      lv_obj_set_style_radius(key,l.modes.h/2,0);
      lv_obj_set_style_bg_color(key,selected?lv_color_hex(colour):theme::color(theme::CARD),0);
      lv_obj_set_style_bg_color(key,theme::color(theme::KEY),LV_STATE_PRESSED);
      lv_obj_set_style_border_width(key,selected?0:1,0);
      lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
      auto *glyph=lv_obj_get_child(key,0);
      if(mode_icons)lv_obj_set_style_text_font(glyph,mode_icons,0);
      lv_label_set_text(glyph,tile_controls::thermostat_mode_icon(t,keys[i]));
      lv_obj_set_style_text_color(glyph,theme::color(selected?theme::ON_ACCENT:theme::SLATE),0);
      lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
    }
  }
  // The fan and the swing, each a row of choices behind its icon, on one white card.
  if(l.row_count){
    detail_card(l.settings.x,l.settings.y,l.settings.w,l.settings.h);
    for(int i=0;i<l.row_count&&i<(int)rows.size();++i){
      const auto &row=rows[i];
      const int icon_h=mini?lv_font_get_line_height(mini):m.text_h;
      detail_text(detail_root,row.icon,l.row_icons[i].x,l.row_icons[i].y+(l.row_icons[i].h-icon_h)/2,l.row_icons[i].w,mini,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
      int chosen=-1;
      for(size_t v=0;v<row.values.size();++v)if(row.values[v]==row.current)chosen=(int)v;
      segments(l.row_tracks[i].x,l.row_tracks[i].y,l.row_tracks[i].w,l.row_tracks[i].h,row.labels,chosen,
               CLIMATE_ROW_FIRST+i*6,theme::hex(theme::TRACK),false,text,small);
    }
  }
}
// ---- Alarm panel (firmware 0.3.3+): Home Assistant's alarm dialog and its code dialog in this look ----
// alarm_panel.h decides (the modes, when a code is asked for, the lock after wrong codes, where the parts go); this
// draws it. The card: the shield on a white card with a key per mode, or one big Disarm key while the alarm counts
// down or goes off. A mode that needs a code opens the keypad in the card's place: the dots, a line of words and
// twelve keys. The code goes to Home Assistant with the action and is wiped here as soon as it is sent. The screen
// never logs it, stores it or puts it in an event.
inline constexpr int ALARM_MODE_FIRST=600,ALARM_DIGIT_FIRST=610,ALARM_CLEAR=620,ALARM_OK=621;
// What the keypad of the open card holds. It lives outside the card's widgets, so a new state (the card is drawn
// again) keeps what was typed.
struct AlarmPad {
  bool open=false;
  unsigned mode=0;
  std::string code, entity;
  uint16_t note=0;      // a line in place of "Enter code" (Wrong code, Nothing changed), 0 for none
  uint32_t note_at=0, shake_at=0;
};
inline AlarmPad alarm_pad;
inline alarm_panel::Attempt alarm_attempt;
inline std::string alarm_attempt_entity;
inline alarm_panel::Lockout alarm_lock;
inline uint16_t alarm_card_note=0;   // a line in place of the card's state (a code with letters)
inline uint32_t alarm_card_note_at=0;
inline esphome::ESPPreferenceObject alarm_preference;
struct AlarmSaved { uint32_t failures=0, seconds=0; };
inline lv_obj_t *alarm_dots=nullptr,*alarm_line=nullptr,*alarm_ring=nullptr,*alarm_keys[12]{};
inline unsigned alarm_dots_shown=0;
// Set by packages/core.yaml: wake the screen as a touch does (the backlight, the dim overlay, open cards closed).
inline std::function<void()> alarm_wake;

// The card is about to be drawn again from nothing: what pointed into the last one points nowhere now.
inline void alarm_forget_widgets(){alarm_dots=alarm_line=alarm_ring=nullptr;for(auto *&k:alarm_keys)k=nullptr;}
inline alarm_panel::Codes alarm_codes(const Tile &t){
  alarm_panel::Codes c;c.format=t.extra().code_format;c.arm_required=!t.extra().arm_code_free;c.saved=t.extra().code_saved;return c;
}
inline const char *alarm_state_text(const std::string &state){
  using namespace screen_text;
  if(state=="disarmed")return tr(txt::ha_alarm_disarmed);
  if(state=="armed_home")return tr(txt::ha_alarm_armed_home);
  if(state=="armed_away")return tr(txt::ha_alarm_armed_away);
  if(state=="armed_night")return tr(txt::ha_alarm_armed_night);
  if(state=="armed_vacation")return tr(txt::ha_alarm_armed_vacation);
  if(state=="armed_custom_bypass")return tr(txt::ha_alarm_armed_custom_bypass);
  if(state=="pending")return tr(txt::ha_alarm_pending);
  if(state=="arming")return tr(txt::ha_alarm_arming);
  if(state=="disarming")return tr(txt::ha_alarm_disarming);
  if(state=="triggered")return tr(txt::ha_alarm_triggered);
  return state.c_str();
}
inline const char *alarm_mode_text(unsigned mode){
  static const uint16_t words[]={txt::ha_alarm_mode_armed_home,txt::ha_alarm_mode_armed_away,txt::ha_alarm_mode_armed_night,
                                 txt::ha_alarm_mode_armed_vacation,txt::ha_alarm_mode_armed_custom_bypass,txt::ha_alarm_mode_disarmed};
  return tr(words[mode<alarm_panel::MODE_COUNT?mode:alarm_panel::DISARM]);
}
// The keypad's title, as Home Assistant's code dialog names it: Disarm, or the mode that arms.
inline const char *alarm_action_text(unsigned mode){
  static const uint16_t words[]={txt::ha_alarm_action_arm_home,txt::ha_alarm_action_arm_away,txt::ha_alarm_action_arm_night,
                                 txt::ha_alarm_action_arm_vacation,txt::ha_alarm_action_arm_custom_bypass,txt::ha_alarm_action_disarm};
  return tr(words[mode<alarm_panel::MODE_COUNT?mode:alarm_panel::DISARM]);
}
// Seconds left of the exit or entry delay, where the integration says how long it is.
inline uint32_t alarm_left(const Tile &t){
  return (t.state=="arming"||t.state=="pending")?alarm_panel::seconds_left(t.extra().alarm_end,now_epoch()):0;
}
// The line under the name on the tile and on the card: Home Assistant's word, the time the delay has left, and on
// the card who changed it last where Home Assistant says so.
inline std::string alarm_status(const Tile &t,bool card){
  if(!t.available())return tr(txt::ha_unavailable);
  std::string text=!t.extra().state_word.empty()?t.extra().state_word:std::string(alarm_state_text(t.state));
  if(const uint32_t left=alarm_left(t))text+=" · "+countdown(left);
  if(card&&!t.extra().changed_by.empty()&&!alarm_panel::urgent(t.state))text+=" · "+t.extra().changed_by;
  return text;
}
// The card's line under the name: the state, or for a moment why a mode did nothing (a code with letters).
inline std::string alarm_card_line(const Tile &t){
  if(alarm_card_note&&esphome::millis()-alarm_card_note_at<6000)return tr(alarm_card_note);
  return alarm_status(t,true);
}
inline bool alarm_pad_open(){return alarm_pad.open&&detail_index<model.count&&model.tiles[detail_index].entity==alarm_pad.entity;}
// A code leaves no copy behind: the bytes are overwritten before the string lets them go.
inline void alarm_wipe(std::string &code){for(char &c:code)c='\0';code.clear();}
inline void alarm_close_pad(){alarm_wipe(alarm_pad.code);alarm_pad.open=false;alarm_pad.note=0;}
inline void alarm_save_lock(){
  AlarmSaved saved{alarm_lock.failures,alarm_lock.remaining_s(esphome::millis())};
  alarm_preference.save(&saved);
}
inline void alarm_load_lock(){
  alarm_preference=esphome::global_preferences->make_preference<AlarmSaved>(0x414C4D31);
  AlarmSaved saved;
  if(alarm_preference.load(&saved)&&saved.failures<1000)alarm_lock.resume(saved.failures,saved.seconds,esphome::millis());
}
// Home Assistant hears of every wrong code (an event, like the manual alarm's manual_alarm_bad_code_attempt), with
// the panel, how many in a row and how long the keypad is locked; never the code.
inline void alarm_refused_event(const std::string &entity,uint32_t locked){
  esphome::api::HomeassistantActionRequest request;
  // A lock's keypad has an event of its own (firmware 0.5.0+).
  request.service=esphome::StringRef(entity.compare(0,5,"lock.")==0?"esphome.screen_lock_code_refused":"esphome.screen_alarm_code_refused");
  request.is_event=true;
  const std::string failures=std::to_string(alarm_lock.failures),seconds=std::to_string(locked);
  const std::string keys[]={"entity_id","failures","locked"},values[]={entity,failures,seconds};
  request.data.init(3);
  for(int i=0;i<3;++i){esphome::api::HomeassistantServiceMap entry;entry.key=esphome::StringRef(keys[i]);entry.value=esphome::StringRef(values[i]);request.data.push_back(entry);}
  esphome::api::global_api_server->send_homeassistant_action(request);
}
inline void redraw_detail();
// The end of an attempt with a code: accepted closes the keypad and opens the lock again; failed counts, may lock the
// keypad, tells Home Assistant and shakes the dots.
inline void alarm_settled(alarm_panel::Outcome outcome,bool silent){
  using alarm_panel::Outcome;
  if(outcome==Outcome::WAITING)return;
  const uint32_t now=esphome::millis();
  if(outcome==Outcome::ACCEPTED){
    if(alarm_attempt.with_code&&alarm_lock.failures){alarm_lock.success();alarm_save_lock();}
    if(alarm_pad.open)alarm_close_pad();
    ESP_LOGI(alarm_attempt_entity.compare(0,5,"lock.")==0?"lock":"alarm","%s accepted",alarm_attempt_entity.c_str());
  }else{
    if(!alarm_attempt.with_code)return;
    const uint32_t locked=alarm_lock.fail(now);
    alarm_save_lock();
    alarm_refused_event(alarm_attempt_entity,locked);
    alarm_pad.note=silent?txt::alarm_nothing_changed:txt::alarm_wrong_code;alarm_pad.note_at=now;alarm_pad.shake_at=now;
    ESP_LOGW(alarm_attempt_entity.compare(0,5,"lock.")==0?"lock":"alarm","%s: code not accepted (%s), %u in a row, keypad locked for %u s",alarm_attempt_entity.c_str(),
             silent?"ignored":"refused",(unsigned)alarm_lock.failures,(unsigned)locked);
  }
  redraw_detail();
}
// Home Assistant refused an action (watch_call): an attempt with a code on its way failed.
inline void alarm_refused(const std::string &entity){
  if(alarm_attempt.active&&entity==alarm_attempt_entity)alarm_settled(alarm_attempt.refused(),false);
}
// A mode key: straight to Home Assistant when no code is needed, else the keypad.
inline void alarm_choose(Tile &t,unsigned mode){
  using namespace alarm_panel;
  if(mode>=MODE_COUNT||t.state==MODES[mode].state)return;
  const Codes codes=alarm_codes(t);
  if(needs_code(codes,mode)){
    if(!code_typable(codes)){alarm_card_note=txt::alarm_letters;alarm_card_note_at=esphome::millis();redraw_detail();return;}
    alarm_wipe(alarm_pad.code);alarm_pad.open=true;alarm_pad.mode=mode;alarm_pad.note=0;alarm_pad.entity=t.entity;
    redraw_detail();
    return;
  }
  alarm_attempt.begin(mode,false,esphome::millis());alarm_attempt_entity=t.entity;
  action(MODES[mode].service,t.entity);
}
inline void alarm_send(Tile &t){
  using namespace alarm_panel;
  const uint32_t now=esphome::millis();
  if(alarm_pad.code.empty()||alarm_lock.locked(now)||alarm_attempt.active)return;
  alarm_attempt.begin(alarm_pad.mode,true,now);alarm_attempt_entity=t.entity;
  alarm_pad.note=0;
  // The one place the code leaves the screen: the action's `code`, as Home Assistant's own dialogs send it.
  action(t.domain()=="lock"?lock_panel::service((lock_panel::Act)alarm_pad.mode):MODES[alarm_pad.mode].service,t.entity,"code",alarm_pad.code);
  alarm_wipe(alarm_pad.code);
  redraw_detail();
}

// ---- The animations: they show what the alarm does, never how a card opens, and only inside the shield's circle ----
// A ring that grows out of the circle and fades (a heartbeat: slow while arming, fast while someone is inside, in Home
// Assistant's one-second rhythm while it goes off), a ring that closes round the shield when it arms, and a short
// spring of the circle when it arms or disarms. They run on the circle only, so the CYD redraws a small square.
enum AlarmLook : uint8_t { LOOK_NONE, LOOK_ARMING, LOOK_PENDING, LOOK_TRIGGERED };
inline AlarmLook alarm_look(const Tile &t){
  if(!t.available())return LOOK_NONE;
  if(t.state=="triggered")return LOOK_TRIGGERED;
  if(t.state=="pending")return LOOK_PENDING;
  if(t.state=="arming")return LOOK_ARMING;
  return LOOK_NONE;
}
inline void alarm_beat_exec(lv_anim_t *a,int32_t v){
  auto *o=static_cast<lv_obj_t *>(a->var);const int reach=(int)(intptr_t)lv_anim_get_user_data(a);
  lv_obj_set_style_outline_width(o,reach*v/255,0);
  lv_obj_set_style_outline_opa(o,(lv_opa_t)(150*(255-v)/255),0);
}
// The spring grows the circle by a few pixels on every side: transform_width and _height draw it bigger in place,
// without the layer a scale or a rotation would give it (tests/test_layer_free.py).
inline void alarm_spring_exec(void *o,int32_t v){
  auto *obj=static_cast<lv_obj_t *>(o);lv_obj_set_style_transform_width(obj,v,0);lv_obj_set_style_transform_height(obj,v,0);
}
inline void alarm_still(lv_obj_t *o){
  if(!o)return;
  lv_anim_delete(o,nullptr);
  lv_obj_set_style_outline_width(o,0,0);lv_obj_set_style_outline_opa(o,LV_OPA_TRANSP,0);
  lv_obj_set_style_transform_width(o,0,0);lv_obj_set_style_transform_height(o,0,0);
}
// A heartbeat of `period` ms, forever, or once.
inline void alarm_beat(lv_obj_t *o,uint32_t colour,uint32_t period,int reach,bool once){
  lv_obj_set_style_outline_color(o,lv_color_hex(colour),0);lv_obj_set_style_outline_pad(o,0,0);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,o);lv_anim_set_values(&a,0,255);lv_anim_set_duration(&a,period);
  lv_anim_set_custom_exec_cb(&a,alarm_beat_exec);lv_anim_set_user_data(&a,(void *)(intptr_t)reach);lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
  lv_anim_set_repeat_count(&a,once?1:LV_ANIM_REPEAT_INFINITE);
  lv_anim_start(&a);
}
inline void alarm_spring(lv_obj_t *o,uint32_t delay){
  lv_obj_set_style_radius(o,LV_RADIUS_CIRCLE,0);
  const int32_t grow=std::max<int32_t>(2,lv_obj_get_width(o)/24);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,o);lv_anim_set_values(&a,0,grow);lv_anim_set_duration(&a,150);
  lv_anim_set_reverse_duration(&a,200);lv_anim_set_delay(&a,delay);lv_anim_set_exec_cb(&a,alarm_spring_exec);
  lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
  lv_anim_start(&a);
}
// How long after a change of state the arrival is still shown: a card drawn later (opened a minute after arming)
// shows the shield standing still.
constexpr uint32_t ALARM_ARRIVAL_MS=1500;
inline bool alarm_arrived(const Tile &t){return t.changed_at&&esphome::millis()-t.changed_at<ALARM_ARRIVAL_MS;}
// The tile's circle, after every render of its slot and once a second from tick(): the heartbeat of the state while
// the screen is awake, the arrival once.
// A lock's heartbeat: slow while it moves, quicker while its tile waits for the second tap (lock section below).
inline AlarmLook lock_look(const Tile &t);
inline uint32_t lock_accent(const Tile &t);
inline void alarm_tile_look(size_t slot,const Tile *t){
  if(slot>=widgets.size()||!widgets[slot].circle)return;
  auto &w=widgets[slot];
  // A key of a bedside clock is its circle (render_slot): the ring grows out of the round card, since the card cuts off
  // what its children draw past its edge, and a circle as large as the card has no room inside it.
  lv_obj_t *circle=widgets[slot].key?widgets[slot].tile:widgets[slot].circle;
  // A lock's circle moves the same way (firmware 0.5.0+): it beats while the lock moves or waits for its second tap,
  // and beats once and springs when it locks.
  const bool lock=t&&t->domain()=="lock";
  const bool alarm=t&&(t->domain()=="alarm_control_panel"||lock);
  // The slot shows another tile now: its circle stands still.
  if(!alarm){
    if(w.alarm_look||w.alarm_mark)alarm_still(circle);
    w.alarm_look=LOOK_NONE;w.alarm_mark=0;
    return;
  }
  const AlarmLook want=alarm&&awake()&&fresh()?(lock?lock_look(*t):alarm_look(*t)):LOOK_NONE;
  const bool large=ui::large();
  if(alarm&&want==LOOK_NONE&&alarm_arrived(*t)&&w.alarm_mark!=t->changed_at&&awake()){
    w.alarm_mark=t->changed_at;alarm_still(circle);w.alarm_look=LOOK_NONE;
    const bool closed=lock?t->state=="locked":alarm_panel::armed(t->state);
    if(closed)alarm_beat(circle,theme::state(alarm_panel::GREEN),600,ui::px(large?10:5),true);
    alarm_spring(circle,closed?120:0);
    return;
  }
  if(want==w.alarm_look)return;
  w.alarm_look=want;alarm_still(circle);
  if(want==LOOK_NONE)return;
  const uint32_t colour=theme::state(lock?lock_accent(*t):alarm_panel::color(t->state));
  alarm_beat(circle,colour,want==LOOK_ARMING?1600:want==LOOK_PENDING?600:1000,ui::px(large?10:5),false);
}
// The bell rings while the alarm goes off: it shakes a few pixels either way, then stands still, once a second (a
// shift, not a rotation, which would need a layer of its own).
inline void alarm_swing_exec(lv_anim_t *a,int32_t v){
  const int reach=(int)(intptr_t)lv_anim_get_user_data(a);
  lv_obj_set_style_translate_x(static_cast<lv_obj_t *>(a->var),v<500?(int32_t)lv_trigo_sin((int16_t)(v*1440/500))*reach*(500-v)/500/32767:0,0);
}
#if LV_USE_ARC
inline void alarm_ring_turn(void *o,int32_t v){lv_arc_set_rotation(static_cast<lv_obj_t *>(o),v);}
inline void alarm_ring_close(void *o,int32_t v){lv_arc_set_angles(static_cast<lv_obj_t *>(o),0,v);}
#endif
// The ring round the card's shield: the exit delay running out where its length is known, a short arc going round
// where it is not, and the ring closing when the alarm arms.
inline void alarm_card_ring(const Tile &t,int cx,int cy,int size,int width){
  alarm_ring=nullptr;
#if LV_USE_ARC
  const bool closing=alarm_panel::armed(t.state)&&alarm_arrived(t);
  if(t.state!="arming"&&!closing)return;
  const uint32_t colour=theme::state(alarm_panel::color(t.state));
  auto *arc=lv_arc_create(detail_root);
  lv_obj_remove_style_all(arc);lv_obj_set_size(arc,size,size);lv_obj_set_pos(arc,cx-size/2,cy-size/2);
  lv_obj_remove_flag(arc,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_arc_width(arc,width,LV_PART_MAIN);lv_obj_set_style_arc_width(arc,width,LV_PART_INDICATOR);
  lv_obj_set_style_arc_rounded(arc,true,LV_PART_INDICATOR);
  lv_obj_set_style_arc_color(arc,lv_color_hex(theme::tint(colour,38)),LV_PART_MAIN);lv_obj_set_style_arc_opa(arc,closing?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_arc_color(arc,lv_color_hex(colour),LV_PART_INDICATOR);lv_obj_set_style_arc_opa(arc,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_arc_set_rotation(arc,270);lv_arc_set_bg_angles(arc,0,360);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,arc);
  if(closing){
    lv_arc_set_angles(arc,0,0);
    lv_anim_set_values(&a,0,360);lv_anim_set_duration(&a,500);lv_anim_set_exec_cb(&a,alarm_ring_close);lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
    lv_anim_set_completed_cb(&a,[](lv_anim_t *done){lv_obj_add_flag(static_cast<lv_obj_t *>(done->var),LV_OBJ_FLAG_HIDDEN);});
    lv_anim_start(&a);
    return;
  }
  const uint32_t delay=t.extra().alarm_delay,left=alarm_left(t);
  if(delay&&left){
    // The part still to run, from the top clockwise; tick() takes a second off it each second.
    lv_arc_set_range(arc,0,(int32_t)delay);lv_arc_set_mode(arc,LV_ARC_MODE_REVERSE);lv_arc_set_value(arc,(int32_t)std::min(left,delay));
    alarm_ring=arc;
    return;
  }
  lv_arc_set_angles(arc,0,70);
  lv_anim_set_values(&a,270,630);lv_anim_set_duration(&a,1600);lv_anim_set_exec_cb(&a,alarm_ring_turn);
  lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
#else
  (void)t;(void)cx;(void)cy;(void)size;(void)width;
#endif
}
// The dots of the keypad: one filled per digit typed, and empty ones up to four, like a PIN field.
inline void alarm_draw_dots(const alarm_panel::KeypadLayout &l){
  if(!alarm_dots)return;
  lv_obj_clean(alarm_dots);
  const unsigned n=alarm_pad.code.size(),shown=std::max<unsigned>(4,n);
  alarm_dots_shown=shown;
  const int gap=alarm_panel::dot_gap(l.dot),row=(int)shown*l.dot+((int)shown-1)*gap;
  lv_obj_set_size(alarm_dots,std::max(row,l.dots.w),l.dot);
  lv_obj_set_x(alarm_dots,l.dots.x+(l.dots.w-row)/2-(std::max(row,l.dots.w)-l.dots.w)/2);
  const bool bad=alarm_pad.note==txt::alarm_wrong_code||alarm_pad.note==txt::alarm_nothing_changed;
  for(unsigned i=0;i<shown;++i){
    auto *dot=detail_shape(alarm_dots,(std::max(row,l.dots.w)-row)/2+(int)i*(l.dot+gap),0,l.dot,l.dot,
                           i<n?(bad?theme::state(alarm_panel::RED):theme::hex(theme::INK)):theme::hex(theme::CARD),l.dot/2);
    if(i>=n){lv_obj_set_style_border_width(dot,std::max(1,l.dot/7),0);lv_obj_set_style_border_color(dot,theme::color(theme::TICK),0);}
  }
}
inline alarm_panel::KeypadLayout alarm_keypad_layout;
inline void alarm_shake_exec(void *o,int32_t v){
  const int reach=alarm_keypad_layout.dot;
  lv_obj_set_style_translate_x(static_cast<lv_obj_t *>(o),v<320?(int32_t)lv_trigo_sin((int16_t)(v*1080/320))*reach*(320-v)/320/32767:0,0);
}
inline std::string alarm_line_text(){
  const uint32_t now=esphome::millis();
  if(alarm_lock.locked(now))return fill(txt::alarm_try_again,"time",countdown(alarm_lock.remaining_s(now)));
  if(alarm_attempt.active)return tr(txt::tile_command_sent);
  if(alarm_pad.note&&now-alarm_pad.note_at<4000)return tr(alarm_pad.note);
  return tr(txt::ha_alarm_action_enter_code);
}
// What the keypad's keys may do now: nothing while the lock holds or a code is on its way, and Clear and OK only with
// a digit to act on.
inline void alarm_keys_state(){
  const uint32_t now=esphome::millis();
  const bool held=alarm_lock.locked(now)||alarm_attempt.active||!fresh();
  for(int i=0;i<12;++i){
    if(!alarm_keys[i])continue;
    const bool off=held||((i==9||i==11)&&alarm_pad.code.empty())||(i!=9&&i!=11&&alarm_pad.code.size()>=alarm_panel::CODE_MAX);
    if(off)lv_obj_add_state(alarm_keys[i],LV_STATE_DISABLED);else lv_obj_remove_state(alarm_keys[i],LV_STATE_DISABLED);
  }
  if(alarm_line){
    label(alarm_line,alarm_line_text());
    const bool bad=!alarm_lock.locked(now)&&alarm_pad.note&&now-alarm_pad.note_at<4000;
    lv_obj_set_style_text_color(alarm_line,bad?lv_color_hex(theme::foreground(alarm_panel::RED)):theme::color(theme::MUTED),0);
  }
}
// A key with an icon and a word side by side, centred: the mode keys and the Disarm key.
inline void alarm_key_face(lv_obj_t *key,const char *icon,const std::string &word,const lv_font_t *icons,const lv_font_t *text,lv_color_t ink,int w,int h){
  auto *words=lv_obj_get_child(key,0);
  lv_obj_set_align(words,LV_ALIGN_TOP_LEFT);   // detail_button centred it; this face places it itself
  lv_obj_set_style_text_font(words,text,0);lv_label_set_text(words,word.c_str());lv_obj_set_style_text_color(words,ink,0);
  const int icon_w=icons?lv_font_get_line_height(icons):0,room=std::max(1,w-icon_w-ui::px(8)-2*ui::px(10));
  // A word that does not fit whole leaves the key to its icon, which says the same thing, rather than to "Vac…".
  const bool word_fits=text_width(word,text)<=room||!icons;
  if(!word_fits)lv_obj_add_flag(words,LV_OBJ_FLAG_HIDDEN);
  const int gap=word_fits?ui::px(8):0,word_w=word_fits?std::min(room,text_width(word,text)):0;
  lv_obj_set_size(words,std::max(1,word_w),lv_font_get_line_height(text));
  const int x=(w-icon_w-gap-word_w)/2;
  lv_obj_set_pos(words,x+icon_w+gap,(h-lv_font_get_line_height(text))/2);lv_obj_set_style_text_align(words,LV_TEXT_ALIGN_LEFT,0);
  if(icons){
    auto *glyph=lv_label_create(key);lv_label_set_text(glyph,icon);lv_obj_set_style_text_font(glyph,icons,0);lv_obj_set_style_text_color(glyph,ink,0);
    lv_obj_set_pos(glyph,x,(h-icon_w)/2);lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
  }
}
// The keypad: the dots, a line of words and twelve keys, in the card's place. The alarm panel's and a lock's.
inline void render_code_pad(const alarm_panel::Metrics &m,int width,int top,int bottom,const lv_font_t *text,const lv_font_t *icons,const lv_font_t *mini){
  using namespace alarm_panel;
  const auto l=keypad_layout(m,width,top,bottom,(unsigned)alarm_pad.code.size());
  alarm_keypad_layout=l;
  alarm_dots=lv_obj_create(detail_root);lv_obj_remove_style_all(alarm_dots);lv_obj_set_pos(alarm_dots,l.dots.x,l.dots.y);
  lv_obj_remove_flag(alarm_dots,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(alarm_dots,LV_OBJ_FLAG_SCROLLABLE);
  alarm_draw_dots(l);
  if(alarm_pad.shake_at&&esphome::millis()-alarm_pad.shake_at<400){
    alarm_pad.shake_at=0;
    lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,alarm_dots);lv_anim_set_values(&a,0,320);lv_anim_set_duration(&a,320);
    lv_anim_set_exec_cb(&a,alarm_shake_exec);lv_anim_start(&a);
  }
  alarm_line=detail_text(detail_root,alarm_line_text(),l.line.x,l.line.y,l.line.w,text,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  // The words wrap within their room instead of ending in dots after the first one (keypad_layout gives it the lines).
  lv_label_set_long_mode(alarm_line,LV_LABEL_LONG_WRAP);lv_obj_set_height(alarm_line,l.line.h);
  const lv_font_t *digits=watch_font?watch_font:detail_font;
  const lv_font_t *glyphs=icons&&lv_font_get_line_height(icons)<=l.keys[0].h-ui::px(6)?icons:mini;
  const unsigned before=detail_action_count;
  for(int i=0;i<12;++i){
    const Rect &r=l.keys[i];
    const bool ok=i==11,clear=i==9;
    const int digit=i<9?i+1:0;
    auto *key=detail_button("",r.x,r.y,r.w,r.h,ok?ALARM_OK:clear?ALARM_CLEAR:ALARM_DIGIT_FIRST+digit);
    lv_obj_set_style_radius(key,r.h/2,0);
    lv_obj_set_style_bg_color(key,theme::color(ok?theme::ACCENT:theme::CARD),0);
    lv_obj_set_style_bg_color(key,theme::color(ok?theme::ACCENT_PRESSED:theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,ok?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    auto *face=lv_obj_get_child(key,0);
    lv_obj_set_style_text_font(face,ok||clear?glyphs:digits,0);
    lv_label_set_text(face,ok?glyph::CHECK:clear?glyph::CLOSE:std::to_string(digit).c_str());
    lv_obj_set_style_text_color(face,theme::color(ok?theme::ON_ACCENT:theme::INK),0);
    lv_obj_set_size(face,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(face);
    alarm_keys[i]=key;
  }
  // The keypad keeps its own states (alarm_keys_state), not the card's "wait for Home Assistant" ones.
  detail_action_count=before;
  alarm_keys_state();
}
inline void render_alarm_detail(Tile &t,bool large,int width,int height,lv_obj_t *heading){
  using namespace alarm_panel;
  detail_placed=true;
  if(alarm_pad.entity!=t.entity){alarm_close_pad();alarm_pad.entity=t.entity;}
  // A keypad to disarm closes when the panel is disarmed another way.
  if(alarm_pad.open&&(!t.available()||(alarm_pad.mode==DISARM&&t.state=="disarmed")))alarm_close_pad();
  alarm_forget_widgets();
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  Metrics m;m.large=large;m.touch=ui::touch_min();m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;m.side=overlay_card::pad();
  const int top=ui::px(large?80:50)+lv_font_get_line_height(detail_font)+m.gap(),bottom=height-ui::px(large?18:8);
  const bool on=t.active(),available=t.available();
  const uint32_t colour=on?color(t.state):theme::STATE_OFF;
  if(alarm_pad.open){
    // The keypad in the card's place, titled as Home Assistant's code dialog: Disarm, Arm away.
    if(heading)label(heading,alarm_action_text(alarm_pad.mode));
    render_code_pad(m,width,top,bottom,text,icons,mini);
    return;
  }
  // The card: the shield on its white card, and the modes or the one Disarm key.
  const bool urgent_card=urgent(t.state)&&available;
  const auto offered=modes(t.supported);
  const auto l=card_layout(m,width,top,bottom,urgent_card?0:(unsigned)offered.size(),urgent_card);
  detail_card(l.hero.x,l.hero.y,l.hero.w,l.hero.h);
  const int icon_h=m.icon_h,ring_w=ui::px(large?8:5),ring_gap=ui::px(large?8:5);
  int d=std::min(std::min(l.hero.w,l.hero.h)-2*(ring_w+ring_gap)-ui::px(large?10:6),icon_h*5/2);
  d=std::max(d,icon_h+ui::px(8));
  const int cx=l.hero.cx(),cy=l.hero.cy();
  auto *circle=detail_shape(detail_root,cx-d/2,cy-d/2,d,d,available?theme::tint(theme::state(colour),38):theme::hex(theme::TRACK),d/2);
  if(icons){
    auto *icon=detail_text(circle,t.icon.empty()?alarm_panel::icon(t.state):t.icon.c_str(),0,(d-icon_h)/2,d,icons,LV_TEXT_ALIGN_CENTER,
                           available?theme::icon(theme::state(colour)):theme::hex(theme::OFF));
    if(t.state=="triggered"&&awake()){
      lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,icon);lv_anim_set_values(&a,0,1000);lv_anim_set_duration(&a,1000);
      lv_anim_set_custom_exec_cb(&a,alarm_swing_exec);lv_anim_set_user_data(&a,(void *)(intptr_t)std::max(2,icon_h/10));
      lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
    }
  }
  alarm_card_ring(t,cx,cy,d+2*(ring_w+ring_gap),ring_w);
  if(awake()&&available){
    const AlarmLook look=alarm_look(t);
    if(look==LOOK_PENDING||look==LOOK_TRIGGERED)alarm_beat(circle,theme::state(colour),look==LOOK_PENDING?600:1000,ui::px(large?28:14),false);
    else if(look==LOOK_NONE&&alarm_arrived(t))alarm_spring(circle,armed(t.state)?450:0);
  }
  if(urgent_card){
    auto *key=detail_button("",l.disarm.x,l.disarm.y,l.disarm.w,l.disarm.h,ALARM_MODE_FIRST+DISARM);
    lv_obj_set_style_radius(key,l.disarm.h/2,0);
    lv_obj_set_style_bg_color(key,theme::color(theme::BUTTON_DARK),0);lv_obj_set_style_bg_color(key,theme::color(theme::BUTTON_DARK_PRESSED),LV_STATE_PRESSED);
    alarm_key_face(key,glyph::SHIELD_OFF,alarm_action_text(DISARM),icons&&lv_font_get_line_height(icons)<=l.disarm.h-ui::px(8)?icons:mini,
                   watch_font?watch_font:text,theme::color(theme::ON_ACCENT),l.disarm.w,l.disarm.h);
    return;
  }
  const lv_font_t *key_icons=icons&&lv_font_get_line_height(icons)<=(l.key_count?l.keys[0].h:0)-ui::px(10)?icons:mini;
  for(unsigned i=0;i<l.key_count;++i){
    const unsigned mode=offered[i];
    const Rect &r=l.keys[i];
    const bool current=t.state==MODES[mode].state;
    auto *key=detail_button("",r.x,r.y,r.w,r.h,ALARM_MODE_FIRST+(int)mode);
    lv_obj_set_style_radius(key,r.h/2,0);
    const uint32_t mode_colour=mode==DISARM?theme::STATE_OFF:GREEN;
    lv_obj_set_style_bg_color(key,current?lv_color_hex(theme::state(mode_colour)):theme::color(theme::CARD),0);
    lv_obj_set_style_bg_color(key,theme::color(theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,current?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    alarm_key_face(key,MODES[mode].icon,alarm_mode_text(mode),key_icons,text,
                   current?theme::color(theme::ON_ACCENT):theme::color(theme::INK),r.w,r.h);
    // The icon in the mode's colour on a white key, as Home Assistant colours its choices.
    if(!current&&lv_obj_get_child_count(key)>1)lv_obj_set_style_text_color(lv_obj_get_child(key,1),mode==DISARM?theme::color(theme::SLATE):lv_color_hex(theme::foreground(GREEN)),0);
  }
}
// A new state of an alarm panel arrived (page_receiver): an attempt may be settled by it, and someone coming in or
// the alarm going off wakes the screen with the card open, and the keypad when disarming asks for a code.
inline void alarm_state_arrived(unsigned index,const std::string &before){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  if(alarm_attempt.active&&t.entity==alarm_attempt_entity)alarm_settled(alarm_attempt.settle(t.state,esphome::millis()),true);
  if(!alarm_panel::calls_for_attention(t.state)||alarm_panel::calls_for_attention(before)||!t.available())return;
  if(!enabled||!model.ready())return;
  // A panel on several tiles gets a state message per tile: the first of them wakes the screen, once.
  for(size_t i=0;i<index;++i)if(model.tiles[i].entity==t.entity)return;
  ESP_LOGI("alarm","%s is %s: the screen wakes with its card",t.entity.c_str(),t.state.c_str());
  if(alarm_wake)alarm_wake();
  settings_screen::close();
  const auto codes=alarm_codes(t);
  if(alarm_pad.entity!=t.entity)alarm_close_pad();
  alarm_pad.entity=t.entity;
  if(alarm_panel::needs_code(codes,alarm_panel::DISARM)&&alarm_panel::code_typable(codes)&&!alarm_pad.open){
    alarm_pad.open=true;alarm_pad.mode=alarm_panel::DISARM;alarm_pad.note=0;alarm_wipe(alarm_pad.code);
  }
  active_index=(int)index;
  show_detail(index);
}
// Once a second and on every tick (tick()): an attempt nothing answered runs out, the keypad's lock counts down, the
// exit delay's ring and the tiles' heartbeats follow the screen's clock and whether it is awake.
inline void alarm_tick(){
  const uint32_t now=esphome::millis();
  if(alarm_attempt.active){
    std::string state;
    for(size_t i=0;i<model.count;++i)if(model.tiles[i].entity==alarm_attempt_entity){state=model.tiles[i].state;break;}
    // A lock's attempt heads for a lock's state (lock_panel::reached).
    const bool lock=alarm_attempt_entity.compare(0,5,"lock.")==0;
    alarm_settled(lock?alarm_attempt.settle_if(lock_panel::reached(state,(lock_panel::Act)alarm_attempt.mode),now):alarm_attempt.settle(state,now),true);
  }
  if(alarm_keys[0])alarm_keys_state();
  // A lock that ran out while nobody looked: the count stays, the keypad opens.
  static bool was_locked=false;
  const bool locked=alarm_lock.locked(now);
  if(was_locked&&!locked)alarm_save_lock();
  was_locked=locked;
#if LV_USE_ARC
  if(alarm_ring&&detail_index<model.count){
    const auto &t=model.tiles[detail_index];
    lv_arc_set_value(alarm_ring,(int32_t)std::min(alarm_left(t),t.extra().alarm_delay));
  }
#endif
}
inline void alarm_command(int cmd){
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  // The keypad is a lock's too (firmware 0.5.0+); the mode keys are the alarm's own.
  if(t.domain()!="alarm_control_panel"&&!(t.domain()=="lock"&&cmd>=ALARM_DIGIT_FIRST))return;
  const uint32_t now=esphome::millis();
  if(cmd>=ALARM_DIGIT_FIRST&&cmd<ALARM_DIGIT_FIRST+10){
    if(!alarm_pad.open||alarm_lock.locked(now)||alarm_attempt.active||alarm_pad.code.size()>=alarm_panel::CODE_MAX)return;
    if(!screen_input::touch_guard.accept_repeat(now,300+cmd))return;
    alarm_pad.code+=(char)('0'+cmd-ALARM_DIGIT_FIRST);alarm_pad.note=0;
    // The dots follow the finger at once; a fifth digit makes the row longer, so it is drawn again.
    alarm_draw_dots(alarm_keypad_layout);
    alarm_keys_state();
    return;
  }
  if(cmd==ALARM_CLEAR){
    if(!screen_input::touch_guard.accept_repeat(now,300+cmd))return;
    alarm_wipe(alarm_pad.code);alarm_pad.note=0;alarm_draw_dots(alarm_keypad_layout);alarm_keys_state();
    return;
  }
  if(!fresh()||!allowed(now,300+cmd,"alarm:"+t.entity)||!t.available())return;
  if(cmd==ALARM_OK){alarm_send(t);return;}
  if(cmd>=ALARM_MODE_FIRST&&cmd<ALARM_MODE_FIRST+(int)alarm_panel::MODE_COUNT){
    if(t.waiting(now))return;
    alarm_choose(t,(unsigned)(cmd-ALARM_MODE_FIRST));
  }
}
// ---- Lock (firmware 0.5.0+): Home Assistant's lock dialog in this look, and a tile that locks with one tap ----
// lock_panel.h decides (what may happen, which keys, when a code is asked for); this draws it. A tap on the tile locks
// what is not locked at once. A locked lock asks first: the tile turns orange, and its circle
// beats and says "Confirm", and a second tap within five seconds unlocks. The card (hold the tile) has the key that changes the state,
// both keys while the lock is jammed, and Open door where the lock has one; Unlock and Open door ask for a second tap
// on the same key. A lock with a code opens the alarm panel's keypad instead, with its lock after wrong codes: typing
// the code is the second tap. The animations are the alarm panel's: a heartbeat while the lock moves or waits for its
// second tap, a ring going round while it moves, and a ring that closes round the lock when it locks.
inline constexpr int LOCK_KEY_FIRST=700;   // 700 lock, 701 unlock, 702 open
// The "tap again" a tile waits for lives on the tile (Tile::ask_act, firmware 0.16.0+); one tile waits at a time, and
// `lock_waits` says whether any does, so lock_tick has nothing to look at otherwise.
inline bool lock_waits=false;
inline lock_panel::Confirm lock_ask_of(const Tile &t){
  lock_panel::Confirm c;if(t.ask_act>=0){c.act=(lock_panel::Act)t.ask_act;c.since=t.ask_since;}return c;
}
inline void lock_keep_ask(Tile &t,const lock_panel::Confirm &c){t.ask_act=c.act==lock_panel::NONE?-1:(int8_t)c.act;t.ask_since=c.since;}
inline lv_obj_t *lock_ring=nullptr;
inline lock_panel::Lock lock_of(const Tile &t){
  lock_panel::Lock l;l.state=t.state;l.supported=t.supported;l.assumed=t.extra().assumed;l.available=t.available()&&fresh();return l;
}
inline lock_panel::Guard lock_guard(const Tile &t){return lock_panel::guard_of(t.guard);}
inline bool lock_noting(const Tile &t){return t.noted_at&&esphome::millis()-t.noted_at<3000;}
inline bool lock_asking(const Tile &t,bool card,lock_panel::Act a=lock_panel::NONE){
  if(t.ask_act<0||t.ask_card!=card)return false;
  const uint32_t now=esphome::millis();const auto c=lock_ask_of(t);
  return a==lock_panel::NONE?c.any(now):c.waiting(a,now);
}
// Ends the "tap again" of every tile but `keep`: each shows its state again at once, on its tile or its open card.
inline void lock_end_asks(size_t keep=SIZE_MAX){
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];
    if(i==keep||t.ask_act<0)continue;
    t.ask_act=-1;
    if(!t.ask_card)refresh_tile(i);
    else if(detail_index==i&&detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))redraw_detail();
  }
}
inline const char *lock_state_text(const std::string &state){
  using namespace screen_text;
  if(state=="locked")return tr(txt::ha_lock_locked);
  if(state=="unlocked")return tr(txt::ha_lock_unlocked);
  if(state=="locking")return tr(txt::ha_lock_locking);
  if(state=="unlocking")return tr(txt::ha_lock_unlocking);
  if(state=="open")return tr(txt::ha_lock_open);
  if(state=="opening")return tr(txt::ha_lock_opening);
  if(state=="jammed")return tr(txt::ha_lock_jammed);
  return state.c_str();
}
// A key's word, as Home Assistant's dialog names it; the keypad's title too.
inline const char *lock_action_text(unsigned act){
  if(act==lock_panel::LOCK)return tr(txt::ha_lock_action_lock);
  if(act==lock_panel::UNLOCK)return tr(txt::ha_lock_action_unlock);
  return tr(txt::ha_lock_action_open_door);
}
// The tile's icon: the open lock while it waits for the second tap that unlocks it. A chosen icon stays.
inline const char *lock_icon(const Tile &t){return lock_panel::icon(t.state);}
// The line under the name: the second tap it waits for, a lock-only tile's word, or Home Assistant's word for the
// state, and on the card who changed it last.
inline std::string lock_status(const Tile &t,bool card){
  if(!t.available())return tr(txt::ha_unavailable);
  if(!card&&lock_asking(t,false))return tr(txt::lock_confirm);
  if(!card&&lock_noting(t))return tr(txt::lock_lock_only);
  std::string text=!t.extra().state_word.empty()?t.extra().state_word:std::string(lock_state_text(t.state));
  if(card&&!t.extra().changed_by.empty()&&!lock_panel::moving(t.state))text+=" · "+t.extra().changed_by;
  return text;
}
inline std::string lock_card_line(const Tile &t){
  if(alarm_card_note&&esphome::millis()-alarm_card_note_at<6000)return tr(alarm_card_note);
  return lock_status(t,true);
}
// The tile's colour: orange while it waits for the second tap, else Home Assistant's for the state.
inline uint32_t lock_accent(const Tile &t){
  return lock_asking(t,false)?lock_panel::ORANGE:lock_panel::color(t.state);
}
// What a tap or a key asks for: lock, unlock or open. A code opens the keypad; Unlock and Open door wait for a second
// tap on the same tile or key; the rest goes to Home Assistant at once.
inline void lock_do(unsigned index,lock_panel::Act act,bool card){
  using namespace lock_panel;
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  const uint32_t now=esphome::millis();
  if(!can(lock_of(t),act,lock_guard(t))||t.waiting(now))return;
  const auto &x=t.extra();
  if(needs_code(x.code_format,x.code_saved)){
    t.ask_act=-1;
    if(!code_typable(x.code_format)){alarm_card_note=txt::alarm_letters;alarm_card_note_at=now;}
    else{alarm_wipe(alarm_pad.code);alarm_pad.open=true;alarm_pad.mode=act;alarm_pad.note=0;alarm_pad.entity=t.entity;}
    if(card)redraw_detail();else{active_index=(int)index;show_detail(index);}
    return;
  }
  if(confirms(act)){
    // One tile waits at a time: a first tap here ends another tile's wait, and the card's wait is not the tile's.
    lock_end_asks(index);
    if(t.ask_card!=card)t.ask_act=-1;
    t.ask_card=card;
    auto c=lock_ask_of(t);
    const bool second=c.press(act,now);
    lock_keep_ask(t,c);
    if(!second){
      lock_waits=true;
      ESP_LOGI("lock","%s: tap again to %s",t.entity.c_str(),act==OPEN?"open":"unlock");
      if(card)redraw_detail();else refresh_tile(index);
      return;
    }
  }
  t.ask_act=-1;
  alarm_attempt.begin(act,false,now);alarm_attempt_entity=t.entity;
  action(service(act),t.entity);
  if(card)redraw_detail();else refresh_tile(index);
}
// A finger on the tile (tile_controls::TapRoute::LOCK).
inline void lock_tap(unsigned index){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  const auto act=lock_panel::tap(lock_of(t),lock_guard(t));
  if(act==lock_panel::NONE){
    if(t.state=="locked"&&lock_guard(t)==lock_panel::Guard::LOCK_ONLY){t.noted_at=std::max<uint32_t>(1,esphome::millis());refresh_tile(index);}
    return;
  }
  lock_do(index,act,false);
}
// The ring round the card's lock: a short arc going round while it moves, and a ring closing when it locks.
inline void lock_card_ring(const Tile &t,int cx,int cy,int size,int width){
  lock_ring=nullptr;
#if LV_USE_ARC
  const bool closing=t.state=="locked"&&alarm_arrived(t);
  if(!lock_panel::moving(t.state)&&!closing)return;
  const uint32_t colour=theme::state(lock_panel::color(t.state));
  auto *arc=lv_arc_create(detail_root);
  lv_obj_remove_style_all(arc);lv_obj_set_size(arc,size,size);lv_obj_set_pos(arc,cx-size/2,cy-size/2);
  lv_obj_remove_flag(arc,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_arc_width(arc,width,LV_PART_MAIN);lv_obj_set_style_arc_width(arc,width,LV_PART_INDICATOR);
  lv_obj_set_style_arc_rounded(arc,true,LV_PART_INDICATOR);
  lv_obj_set_style_arc_color(arc,lv_color_hex(theme::tint(colour,38)),LV_PART_MAIN);lv_obj_set_style_arc_opa(arc,closing?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_arc_color(arc,lv_color_hex(colour),LV_PART_INDICATOR);lv_obj_set_style_arc_opa(arc,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_arc_set_rotation(arc,270);lv_arc_set_bg_angles(arc,0,360);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,arc);
  if(closing){
    lv_arc_set_angles(arc,0,0);
    lv_anim_set_values(&a,0,360);lv_anim_set_duration(&a,500);lv_anim_set_exec_cb(&a,alarm_ring_close);lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
    lv_anim_set_completed_cb(&a,[](lv_anim_t *done){lv_obj_add_flag(static_cast<lv_obj_t *>(done->var),LV_OBJ_FLAG_HIDDEN);});
    lv_anim_start(&a);
    return;
  }
  lv_arc_set_angles(arc,0,70);
  lv_anim_set_values(&a,270,630);lv_anim_set_duration(&a,1600);lv_anim_set_exec_cb(&a,alarm_ring_turn);
  lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
  lock_ring=arc;
#else
  (void)t;(void)cx;(void)cy;(void)size;(void)width;
#endif
}
inline void render_code_pad(const alarm_panel::Metrics &m,int width,int top,int bottom,const lv_font_t *text,const lv_font_t *icons,const lv_font_t *mini);
inline void render_lock_detail(Tile &t,bool large,int width,int height,lv_obj_t *heading){
  using namespace alarm_panel;
  detail_placed=true;
  if(alarm_pad.entity!=t.entity){alarm_close_pad();alarm_pad.entity=t.entity;}
  if(alarm_pad.open&&!t.available())alarm_close_pad();
  alarm_forget_widgets();lock_ring=nullptr;
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  Metrics m;m.large=large;m.touch=ui::touch_min();m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;m.side=overlay_card::pad();
  const int top=ui::px(large?80:50)+lv_font_get_line_height(detail_font)+m.gap(),bottom=height-ui::px(large?18:8);
  if(alarm_pad.open){
    // The keypad in the card's place, titled as the key that asked for it: Unlock, Lock, Open door.
    if(heading)label(heading,lock_action_text(alarm_pad.mode));
    render_code_pad(m,width,top,bottom,text,icons,mini);
    return;
  }
  const auto lock=lock_of(t);
  const auto guard=lock_guard(t);
  const auto primary=lock_panel::primary(lock,guard);
  const auto keys=lock_panel::secondary(lock,guard);
  const bool available=t.available();
  const bool asking=lock_asking(t,true);
  // The lock's hero is its control, so it takes the height the alarm's shield leaves to its keys.
  m.hero_cap=ui::px(large?300:190);
  const auto l=card_layout(m,width,top,bottom,keys.count,false);
  detail_card(l.hero.x,l.hero.y,l.hero.w,l.hero.h);
  // The lock itself is the big key, as Apple's Home and Home Assistant's own lock dialog make the lock the control:
  // a round key in its state's colour, and under it the word of what a tap does (Lock, Unlock, Confirm).
  const int icon_h=m.icon_h,ring_w=ui::px(large?8:5),ring_gap=ui::px(large?8:5),word_h=m.text_h,inner=ui::px(large?10:6);
  const int room_h=l.hero.h-2*inner-word_h-ui::px(large?8:4);
  int d=std::min({room_h-2*(ring_w+ring_gap),l.hero.w*11/20,icon_h*4});
  d=std::max(d,std::max(icon_h+ui::px(8),m.least_key()));
  const int block=d+2*(ring_w+ring_gap)+ui::px(large?8:4)+word_h;
  const int cx=l.hero.cx(),cy=l.hero.y+(l.hero.h-block)/2+ring_w+ring_gap+d/2;
  const bool waits_open=lock_asking(t,true,lock_panel::OPEN);
  const uint32_t colour=asking&&!waits_open?lock_panel::ORANGE:lock_panel::color(t.state);
  auto *big=detail_button("",cx-d/2,cy-d/2,d,d,LOCK_KEY_FIRST+(int)(primary==lock_panel::NONE?lock_panel::LOCK:primary));
  lv_obj_set_style_radius(big,LV_RADIUS_CIRCLE,0);lv_obj_set_style_border_width(big,0,0);
  const uint32_t ground=available?theme::tint(theme::state(colour),38):theme::hex(theme::TRACK);
  lv_obj_set_style_bg_color(big,lv_color_hex(ground),0);
  lv_obj_set_style_bg_color(big,lv_color_hex(theme::pressed(ground)),LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(big,lv_color_hex(ground),LV_STATE_DISABLED);lv_obj_set_style_bg_opa(big,LV_OPA_COVER,LV_STATE_DISABLED);
  if(icons){
    auto *face=lv_obj_get_child(big,0);
    const char *glyph=asking&&!waits_open?lock_panel::glyph::LOCK_OPEN:(t.icon.empty()?lock_panel::icon(t.state):t.icon.c_str());
    // The large icon face where the key has room for it and it carries the glyph.
    const lv_font_t *face_font=big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=d*3/5?big_icon_font:icons;
    lv_obj_set_style_text_font(face,face_font,0);lv_label_set_text(face,glyph);
    lv_obj_set_style_text_color(face,lv_color_hex(available?theme::icon(theme::state(colour)):theme::hex(theme::OFF)),0);
    lv_obj_set_style_text_color(face,lv_color_hex(available?theme::icon(theme::state(colour)):theme::hex(theme::OFF)),LV_STATE_DISABLED);
    lv_obj_set_size(face,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(face);
  }
  if(primary==lock_panel::NONE||!lock_panel::can(lock,primary,guard))lv_obj_add_state(big,LV_STATE_DISABLED);
  // The word under the key: what a tap does, "Confirm" in orange while it waits, the state while it moves, and why a
  // lock-only tile's locked lock does nothing.
  std::string word;uint32_t ink=theme::hex(theme::INK);
  if(!available)word=tr(txt::ha_unavailable);
  else if(asking&&!waits_open){word=tr(txt::lock_confirm);ink=theme::foreground(lock_panel::ORANGE);}
  else if(lock_panel::moving(t.state))word=lock_state_text(t.state);
  else if(primary==lock_panel::NONE&&guard==lock_panel::Guard::LOCK_ONLY)word=tr(txt::lock_lock_only);
  else if(primary!=lock_panel::NONE)word=lock_action_text(primary);
  const int word_y=cy+d/2+ring_w+ring_gap+ui::px(large?8:4);
  auto *caption=detail_text(detail_root,word,l.hero.x+inner,word_y,l.hero.w-2*inner,text,LV_TEXT_ALIGN_CENTER,ink);
  lv_label_set_long_mode(caption,LV_LABEL_LONG_DOT);
  lock_card_ring(t,cx,cy,d+2*(ring_w+ring_gap),ring_w);
  if(awake()&&available){
    if(asking&&!waits_open)alarm_beat(big,theme::state(colour),1000,ui::px(large?28:14),false);
    else if(lock_panel::moving(t.state))alarm_beat(big,theme::state(colour),1600,ui::px(large?28:14),false);
    else if(alarm_arrived(t)){
      if(t.state=="locked")alarm_beat(big,theme::state(colour),600,ui::px(large?28:14),true);
      alarm_spring(big,t.state=="locked"?450:0);
    }
  }
  const lv_font_t *key_icons=icons&&lv_font_get_line_height(icons)<=(l.key_count?l.keys[0].h:0)-ui::px(10)?icons:mini;
  for(unsigned i=0;i<l.key_count;++i){
    const auto act=keys.act[i];
    const Rect &r=l.keys[i];
    const bool waiting=lock_asking(t,true,act);
    auto *key=detail_button("",r.x,r.y,r.w,r.h,LOCK_KEY_FIRST+(int)act);
    lv_obj_set_style_radius(key,r.h/2,0);
    // A key that waits for its second tap turns orange and asks, as Home Assistant's Open door key does.
    const uint32_t ask=theme::state(lock_panel::ORANGE);
    lv_obj_set_style_bg_color(key,waiting?lv_color_hex(ask):theme::color(theme::CARD),0);
    lv_obj_set_style_bg_color(key,waiting?lv_color_hex(theme::pressed(ask)):theme::color(theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,waiting?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    const char *glyph=act==lock_panel::UNLOCK?lock_panel::glyph::LOCK_OPEN:lock_panel::glyph::DOOR_OPEN;
    const std::string label_text=waiting?(act==lock_panel::OPEN?tr(txt::ha_lock_action_open_door_confirm):tr(txt::lock_really_unlock)):lock_action_text(act);
    // Neutral keys, as Home Assistant's dialog draws them: the colour belongs to the lock, not to what a key does.
    alarm_key_face(key,glyph,label_text,key_icons,text,waiting?theme::color(theme::ON_ACCENT):theme::color(theme::INK),r.w,r.h);
    if(!lock_panel::can(lock,act,guard))lv_obj_add_state(key,LV_STATE_DISABLED);
  }
}
// A new state of a lock arrived (page_receiver): an attempt may be settled by it, and a "tap again" for it ends.
inline void lock_state_arrived(unsigned index,const std::string &before){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  if(alarm_attempt.active&&t.entity==alarm_attempt_entity)
    alarm_settled(alarm_attempt.settle_if(lock_panel::reached(t.state,(lock_panel::Act)alarm_attempt.mode),esphome::millis()),true);
  if(before!=t.state)t.ask_act=-1;
}
// Every tick (tick()): a "tap again" that ran out, or a screen that went to sleep, puts the tile or the card back.
inline void lock_tick(){
  if(!lock_waits)return;
  const uint32_t now=esphome::millis();
  bool waiting=false;
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];
    if(t.ask_act<0)continue;
    if(awake()&&lock_ask_of(t).any(now)){waiting=true;continue;}
    t.ask_act=-1;
    if(!t.ask_card)refresh_tile(i);
    else if(detail_index==i&&detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))redraw_detail();
  }
  lock_waits=waiting;
}
inline void lock_command(int cmd){
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(t.domain()!="lock"||!fresh()||!t.available())return;
  if(!allowed(esphome::millis(),300+cmd,"lock:"+t.entity))return;
  const int act=cmd-LOCK_KEY_FIRST;
  if(act<0||act>=(int)lock_panel::NONE)return;
  lock_do((unsigned)detail_index,(lock_panel::Act)act,true);
}
inline AlarmLook lock_look(const Tile &t){
  if(!t.available())return LOOK_NONE;
  if(lock_asking(t,false))return LOOK_TRIGGERED;
  if(lock_panel::moving(t.state))return LOOK_ARMING;
  return LOOK_NONE;
}
// A card that closes forgets the second tap its keys waited for.
inline void lock_card_closed(){if(detail_index<model.count&&model.tiles[detail_index].ask_card)model.tiles[detail_index].ask_act=-1;}
// ---- History card (firmware 0.2.51+): numbers as a line with axes, states as a timeline ----
// Sensors, numbers, switches, binary sensors and people. The card asks the manager for the chosen range when it
// opens (an hour, a day or a week; always 24 averages or 96 slots) and draws what comes back. A finger on the
// graph shows the value or state and its time at the top, until it lifts.
inline bool history_card(const Tile &t){
  auto d=t.domain();
  return d=="sensor"||d=="binary_sensor"||d=="switch"||d=="input_boolean"||d=="person"||d=="number"||d=="input_number";
}
// Before the history arrives: a line for numbers, a timeline for the rest.
inline bool history_line_guess(const Tile &t){
  auto d=t.domain();
  if(d=="number"||d=="input_number")return true;
  if(d!="sensor"||t.device_class=="enum"||t.device_class=="timestamp"||t.device_class=="date")return false;
  if(!t.unit.empty())return true;
  char *end=nullptr;std::strtof(t.state.c_str(),&end);return end!=t.state.c_str();
}
// The open card's parts that a finger changes, and the plot: x, y, w, h on the screen.
struct HistoryChart {
  lv_obj_t *value=nullptr,*first=nullptr,*second=nullptr,*area=nullptr,*status=nullptr;
  int x=0,y=0,w=0,h=0;
  float bottom=0,top=1;
  // The highest and lowest moment the card shows: the history's, or the value now when it goes beyond them.
  float high=NAN,low=NAN;
  uint32_t high_at=0,low_at=0;
  bool line=true,ready=false;
  uint32_t accent=theme::ha::BLUE;
  std::string value_text,first_text,second_text;
  lv_point_precise_t *points=nullptr;unsigned count=0;
};
inline HistoryChart history_chart;
inline void history_forget(){
  auto &c=history_chart;c.value=c.first=c.second=c.area=c.status=nullptr;c.count=0;c.ready=false;c.high=c.low=NAN;
}
inline float history_y(float value){
  const auto &c=history_chart;
  return c.y+c.h-(std::clamp(value,c.bottom,c.top)-c.bottom)/(c.top-c.bottom)*c.h;
}
// Where a moment of the range lies across the plot, from its left edge.
inline float history_x(uint32_t at){
  const auto &h=history;const auto &c=history_chart;
  return float(std::clamp(at,h.start,h.end)-h.start)/float(std::max<uint32_t>(1,h.end-h.start))*(c.w-1);
}
// The history holds the open card's entity and range, and is new: the answer to this opening, or less than a
// minute old (a card opened again shows it at once while it asks).
inline bool history_fits(const Tile &t){
  return history.entity==t.entity&&history.hours==history_hours&&
    (history_answered||esphome::millis()-history_received_at<60000);
}
// Home Assistant's word for the state now: from this entity's history words, else the card's own. The history can
// still be the previous card's while this one waits for its answer.
inline std::string history_words(const Tile &t){
  if(!t.available())return tr(txt::ha_unavailable);
  if(history.entity==t.entity)for(const auto &pair:history.words)if(pair.first==t.state)return pair.second;
  return detail_state(t);
}
inline std::string history_clock(uint32_t epoch,bool weekday){
  return history_view::clock(epoch,history.offset,screen_settings::current.clock_24h!=0,weekday);
}
// The soft area under the line: two triangles per segment down to the plot's bottom, no layer buffer.
inline void history_fill(lv_event_t *e){
  const auto &c=history_chart;if(!c.line||c.count<2||!c.area)return;
  auto *layer=lv_event_get_layer(e);lv_area_t area;lv_obj_get_coords(c.area,&area);
  lv_draw_triangle_dsc_t dsc;lv_draw_triangle_dsc_init(&dsc);dsc.color=lv_color_hex(c.accent);dsc.opa=theme::fill_opacity();
  const lv_value_precise_t ox=area.x1,oy=area.y1,base=area.y2+1;
  for(unsigned i=0;i+1<c.count;++i){
    const auto &a=c.points[i],&b=c.points[i+1];
    dsc.p[0]={ox+a.x,oy+a.y};dsc.p[1]={ox+b.x,oy+b.y};dsc.p[2]={ox+b.x,base};lv_draw_triangle(layer,&dsc);
    dsc.p[1]=dsc.p[2];dsc.p[2]={ox+a.x,base};lv_draw_triangle(layer,&dsc);
  }
}
// The timeline: one rectangle per run, drawn in the bar's own draw event instead of an object each.
inline void history_bar(lv_event_t *e){
  const auto &h=history;if(h.line||!h.slots)return;
  auto *obj=lv_event_get_current_target_obj(e);auto *layer=lv_event_get_layer(e);
  lv_area_t area;lv_obj_get_coords(obj,&area);const int w=lv_area_get_width(&area);
  lv_draw_rect_dsc_t dsc;lv_draw_rect_dsc_init(&dsc);dsc.bg_opa=LV_OPA_COVER;
  for(size_t i=0;i<h.runs.size();++i){
    const int state=h.runs[i].state;
    const int x1=area.x1+w*h.runs[i].slot/h.slots,x2=area.x1+w*history_view::run_end(h.runs,h.slots,i)/h.slots-1;
    dsc.bg_color=lv_color_hex(state<0||state>=static_cast<int>(h.states.size())?theme::hex(theme::TRACK):theme::state(h.states[state].color));
    lv_area_t piece{x1,area.y1,std::max(x1,x2),area.y2};lv_draw_rect(layer,&dsc,&piece);
  }
}
inline void history_restore(){
  auto &c=history_chart;
  if(c.value){label(c.value,c.value_text);lv_obj_set_style_text_color(c.value,theme::color(theme::INK),0);}
  if(c.first)label(c.first,c.first_text);
  if(c.second)label(c.second,c.second_text);
}
// A finger on the graph: the value (or state) of the moment under it, and when, at the top of the card. The graph
// itself stays as it is.
inline void history_scrub(lv_event_t *e){
  auto &c=history_chart;const auto &h=history;auto code=lv_event_get_code(e);
  if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST){history_restore();return;}
  if((code!=LV_EVENT_PRESSED&&code!=LV_EVENT_PRESSING)||!c.ready||!c.value||!lv_indev_active())return;
  lv_point_t point;lv_indev_get_point(lv_indev_active(),&point);
  // A finger's point is the screen's; the plot's own x is the card's, and a card that does not fill the
  // glass stands in the middle of it. Reading the two against each other put the whole graph a card's
  // left edge too far left: on a ten-inch screen the middle of the glass already read "now" and the
  // card's own left half read the start of the range (firmware 0.2.82).
  const float fraction=std::clamp(float(point.x-detail_screen_x(c.x))/float(std::max(1,c.w)),0.0f,1.0f);
  const bool week=h.hours==168;
  if(c.line){
    // A part without a value (before the sensor existed, while it was unavailable) says so.
    const int i=history_view::part_at(fraction);
    const uint64_t span=h.end-h.start;
    const uint32_t begin=h.start+static_cast<uint32_t>(span*i/history_view::PARTS),finish=h.start+static_cast<uint32_t>(span*(i+1)/history_view::PARTS);
    label(c.value,h.has[i]?history_view::number(h.values[i],h.decimals,h.unit):std::string(tr(txt::history_no_data)));
    lv_obj_set_style_text_color(c.value,lv_color_hex(h.has[i]?theme::foreground(c.accent):theme::hex(theme::SUBTLE)),0);
    if(c.first)label(c.first,history_clock(begin,week)+" \u2013 "+history_clock(finish,false));
    if(c.second)label(c.second,!h.has[i]?std::string():h.hours==1?std::string(tr(txt::history_average)):fill(txt::history_average_of,"duration",history_view::duration(finish-begin)));
  }else{
    // A run reads the real times of its state, not the slots it covers: a door open for 5 minutes says 5 min.
    const int r=history_view::run_at(h.runs,h.slots,fraction);if(r<0)return;
    const auto &run=h.runs[r];
    const uint32_t begin=h.start+run.begin,finish=h.start+run.end;
    label(c.value,run.state<0||run.state>=static_cast<int>(h.states.size())?std::string(tr(txt::history_no_data)):h.states[run.state].label);
    if(c.first)label(c.first,history_clock(begin,week)+" \u2013 "+history_clock(finish,week&&finish-begin>=43200));
    if(c.second)label(c.second,history_view::duration(run.seconds));
  }
}
// The transparent area a finger scrubs, over the graph and a little around it; it keeps the finger while it drags.
inline void history_touch(int x,int y,int w,int h){
  auto *area=lv_obj_create(detail_root);lv_obj_remove_style_all(area);lv_obj_set_pos(area,x,y);lv_obj_set_size(area,w,h);
  lv_obj_add_flag(area,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_flag(area,LV_OBJ_FLAG_PRESS_LOCK);
  lv_obj_remove_flag(area,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(area,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(area,history_scrub,LV_EVENT_ALL,nullptr);
}
// Times below the graph: round clock times (weekdays for a week) where they fit, and "Now" at the end.
inline void history_times(int x,int w,int y,const lv_font_t *font,bool large){
  const auto &h=history;
  const lv_font_t *bold=detail_font?detail_font:font;
  const int now_w=text_width(tr(txt::history_now),bold),gap=ui::px(large?10:6);
  detail_text(detail_root,tr(txt::history_now),x+w-now_w,y,now_w+2,bold,LV_TEXT_ALIGN_LEFT,theme::INK);
  int last=x-1000;
  for(uint32_t at:h.times){
    if(at<=h.start||at>=h.end)continue;
    const std::string words=h.hours==168?history_view::clock(at,h.offset,true,true).substr(0,3)
      :history_view::axis_clock(at,h.offset,screen_settings::current.clock_24h!=0);
    const int tw=text_width(words,font),cx=x+static_cast<int>(std::lround(float(at-h.start)/float(h.end-h.start)*w));
    const int left=std::max(x-(ui::px(large?8:4)),cx-tw/2);
    if(left<=last+gap||left+tw>x+w-now_w-gap)continue;
    detail_shape(detail_root,cx,y-(ui::px(large?7:4)),1,ui::px(large?5:3),theme::TICK,0);
    detail_text(detail_root,words,left,y,tw+2,font,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
    last=left+tw;
  }
}
inline void render_history_line(bool large,int card_x,int card_y,int card_w,int card_h,const lv_font_t *small,float current){
  auto &c=history_chart;const auto &h=history;
  // The value now can lie outside the history (the last hour is not in the statistics yet): the plot makes room.
  c.bottom=h.bottom;c.top=h.top;
  if(std::isfinite(current)&&(current<c.bottom||current>c.top)){
    const float margin=(std::max(c.top,current)-std::min(c.bottom,current))*0.06f;
    if(current<c.bottom)c.bottom=current-margin;else c.top=current+margin;
  }
  const int label_h=lv_font_get_line_height(small),edge=ui::px(large?14:8);
  int label_w=0;for(const auto &tick:h.ticks)label_w=std::max(label_w,text_width(tick.second,small));
  c.x=card_x+edge+label_w+(label_w?(ui::px(large?10:5)):0);c.w=card_x+card_w-(ui::px(large?18:10))-c.x;
  c.y=card_y+(ui::px(large?22:10));c.h=card_y+card_h-(label_h+(ui::px(large?16:8)))-c.y;
  if(c.w<40||c.h<24)return;
  for(const auto &tick:h.ticks){
    const int ty=static_cast<int>(std::lround(history_y(tick.first)));
    detail_shape(detail_root,c.x,ty,c.w,1,theme::GRID,0);
    detail_text(detail_root,tick.second,card_x+edge,ty-label_h/2,label_w+2,small,LV_TEXT_ALIGN_RIGHT,theme::SUBTLE);
  }
  // Through the middle of each part, from the left edge when the range begins with a value, to "Now" at the right
  // (the value now); a curve that never overshoots them, so the axis and the highest and lowest moment stay true.
  // The averages only reach the highest and lowest moment in their hour, so the line also runs through those two
  // moments: its peak and its valley are where the rings are.
  float xs[history_view::PARTS+4],ys[history_view::PARTS+4];unsigned n=0;
  for(int i=0;i<history_view::PARTS;++i){
    if(!h.has[i])continue;
    const float y=history_y(h.values[i])-c.y;
    if(i==0){xs[n]=0;ys[n++]=y;}
    xs[n]=history_view::part_middle(i)*(c.w-1);ys[n++]=y;
  }
  if(n&&std::isfinite(current)){xs[n]=float(c.w-1);ys[n++]=history_y(current)-c.y;}
  // A moment takes the place of its part's point, so the curve stays smooth; its ring goes where the point is.
  float high_x=history_x(c.high_at),low_x=history_x(c.low_at);
  if(n){
    const float snap=(c.w-1)/float(2*history_view::PARTS);
    int kept=-1;
    if(std::isfinite(c.high)&&(kept=history_view::through(xs,ys,n,history_view::PARTS+4,high_x,history_y(c.high)-c.y,snap))>=0)high_x=xs[kept];
    if(std::isfinite(c.low)){
      const int at=history_view::through(xs,ys,n,history_view::PARTS+4,low_x,history_y(c.low)-c.y,snap,kept);
      if(at>=0)low_x=xs[at];
    }
  }
  if(!c.points)c.points=new lv_point_precise_t[POINT_BUFFER];
  c.count=n>=2?history_view::monotone(xs,ys,n,4,c.points,POINT_BUFFER):0;
  c.area=lv_obj_create(detail_root);lv_obj_remove_style_all(c.area);lv_obj_set_pos(c.area,c.x,c.y);lv_obj_set_size(c.area,c.w,c.h);
  lv_obj_remove_flag(c.area,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(c.area,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_event_cb(c.area,history_fill,LV_EVENT_DRAW_MAIN,nullptr);
  if(c.count>=2){
    auto *stroke=lv_line_create(detail_root);lv_obj_remove_flag(stroke,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_line_rounded(stroke,true,0);lv_obj_set_style_line_width(stroke,ui::px(large?3:2),0);
    lv_obj_set_style_line_color(stroke,lv_color_hex(c.accent),0);
    lv_line_set_points(stroke,c.points,c.count);lv_obj_set_pos(stroke,c.x,c.y);
  }
  // The highest and lowest moment as rings; the Guition writes their values beside them.
  const int ring=ui::px(large?12:8);
  auto marker=[&](float value,float at_x,bool high){
    const int mx=c.x+static_cast<int>(std::lround(at_x));
    const int my=static_cast<int>(std::lround(history_y(value)));
    auto *o=detail_shape(detail_root,mx-ring/2,my-ring/2,ring,ring,theme::CARD,ring/2);
    lv_obj_set_style_border_width(o,ui::px(large?3:2),0);lv_obj_set_style_border_color(o,lv_color_hex(c.accent),0);
    if(!large)return;
    const std::string words=history_view::number(value,h.decimals,"");
    const int lh=lv_font_get_line_height(detail_font),tw=text_width(words,detail_font)+2;
    int ly=high?my-ring/2-lh-2:my+ring/2+2;
    if(ly<card_y+4)ly=my+ring/2+2;
    if(ly+lh>c.y+c.h+6)ly=my-ring/2-lh-2;
    const int lx=std::max(c.x,std::min(mx-tw/2,c.x+c.w-tw));
    detail_text(detail_root,words,lx,ly,tw,detail_font,LV_TEXT_ALIGN_CENTER,theme::INK);
  };
  if(std::isfinite(c.high))marker(c.high,high_x,true);
  if(std::isfinite(c.low)&&c.low!=c.high)marker(c.low,low_x,false);
  if(std::isfinite(current)){
    const int size=ui::px(large?12:8);
    auto *o=detail_shape(detail_root,c.x+c.w-1-size/2,static_cast<int>(std::lround(history_y(current)))-size/2,size,size,c.accent,size/2);
    lv_obj_set_style_border_width(o,2,0);lv_obj_set_style_border_color(o,theme::color(theme::CARD),0);
  }
  history_times(c.x,c.w,c.y+c.h+(ui::px(large?8:4)),small,large);
  history_touch(c.x-(ui::px(large?14:8)),card_y,c.w+(ui::px(large?28:16)),card_h);
}
inline void render_history_timeline(bool large,int card_x,int card_y,int card_w,int card_h,const lv_font_t *small){
  auto &c=history_chart;const auto &h=history;
  const int edge=ui::px(large?16:8),label_h=lv_font_get_line_height(small),times_gap=ui::px(large?8:4),legend_gap=ui::px(large?16:6);
  const int row_h=label_h+(ui::px(large?10:3)),square=ui::px(large?14:8);
  c.x=card_x+edge;c.w=card_w-2*edge;c.h=ui::px(large?56:24);
  // Bar, times and legend as one block in the middle of the card; a legend that does not fit loses its last rows.
  const int above=c.h+times_gap+label_h+legend_gap;
  const int rows=std::max(1,std::min(static_cast<int>((h.states.size()+1)/2),(card_h-2*edge-above+row_h-label_h)/row_h));
  const int block=above+rows*row_h-(row_h-label_h);
  c.y=card_y+std::max(edge,(card_h-block)/2);
  auto *bar=lv_obj_create(detail_root);lv_obj_remove_style_all(bar);lv_obj_set_pos(bar,c.x,c.y);lv_obj_set_size(bar,c.w,c.h);
  lv_obj_remove_flag(bar,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(bar,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_event_cb(bar,history_bar,LV_EVENT_DRAW_MAIN,nullptr);
  history_times(c.x,c.w,c.y+c.h+times_gap,small,large);
  // Every state with its colour and its time, in two columns. The bar is the graph and takes the glass; the
  // legend is read, so it keeps a hand's width in the middle, where a time at the far edge would be lost.
  const auto list=overlay_card::reach(card_w,c.w);
  const int top=c.y+above,col_w=list.w/2,list_x=card_x+list.x;
  const size_t shown=std::min<size_t>(h.states.size(),static_cast<size_t>(rows)*2);
  for(size_t i=0;i<shown;++i){
    const int lx=list_x+static_cast<int>(i%2)*col_w,ly=top+static_cast<int>(i/2)*row_h;
    detail_shape(detail_root,lx,ly+(label_h-square)/2,square,square,theme::state(h.states[i].color),ui::px(large?4:2));
    const std::string time=history_view::duration(h.states[i].seconds);
    const int tw=text_width(time,small)+2,words_x=lx+square+(ui::px(large?10:5)),time_x=lx+col_w-(ui::px(large?14:8))-tw;
    detail_text(detail_root,h.states[i].label,words_x,ly,std::max(8,time_x-words_x-6),small,LV_TEXT_ALIGN_LEFT,theme::INK);
    detail_text(detail_root,time,time_x,ly,tw,small,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
  }
  history_touch(c.x-(ui::px(large?14:8)),card_y,c.w+(ui::px(large?28:16)),c.y+c.h+(ui::px(large?24:12))-card_y);
}
// The range: an hour, a day or a week, as one segmented row. It asks the manager, not Home Assistant, so
// waiting for a command does not lock it. However thin the row is drawn, each key keeps a finger's worth
// of touch area (overlay_card::touchable), as the other segmented rows do.
inline void history_ranges(int x,int y,int w,int h){
  static const uint32_t hours[]={1,24,168};
  const char *const words[]={tr(txt::history_range_hour),tr(txt::history_range_day),tr(txt::history_range_week)};
  const lv_font_t *font=control_font?control_font:detail_font;
  auto *track=detail_shape(detail_root,x,y,w,h,theme::CARD,h/2);
  lv_obj_set_style_border_width(track,1,0);lv_obj_set_style_border_color(track,theme::color(theme::LINE),0);
  const int inset=std::max(3,h/10),sw=(w-2*inset)/3;
  for(int i=0;i<3;++i){
    const bool selected=history_hours==hours[i];
    const int segment_w=i==2?w-2*inset-2*sw:sw;
    auto *segment=detail_button(words[i],x+inset+i*sw,y+inset,segment_w,h-2*inset,160+i);
    lv_obj_set_style_radius(segment,(h-2*inset)/2,0);
    lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT),0);
    lv_obj_set_style_bg_opa(segment,selected?LV_OPA_COVER:LV_OPA_TRANSP,0);
    lv_obj_set_style_bg_opa(segment,LV_OPA_COVER,LV_STATE_PRESSED);
    if(!selected)lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT_TINT),LV_STATE_PRESSED);
    button_words(segment,font,theme::hex(selected?theme::ON_ACCENT:theme::INK),segment_w-6);
    overlay_card::touchable(segment,h-2*inset);
    if(detail_action_count&&detail_actions[detail_action_count-1]==segment)--detail_action_count;
  }
}
inline void render_history_detail(const Tile &t,bool large,int width,int height,int pad){
  auto &c=history_chart;const auto &h=history;auto d=t.domain();
  history_forget();
  // Asked once per opening and range; again after 30 s without an answer (see tick).
  if(history_asked_entity!=t.entity||history_asked_hours!=history_hours||(!history_fits(t)&&esphome::millis()-history_asked_at>30000))
    history_request(t.entity,history_hours);
  c.ready=history_fits(t);
  const bool line=c.ready?h.line:history_line_guess(t);
  c.line=line;c.accent=tile_controls::accent(t);
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=control_font?control_font:detail_font;
  const lv_font_t *small=small_font?small_font:detail_font;
  // The header: the value now (or the state), and at the right what the history says about it.
  char *end=nullptr;const float parsed=std::strtof(t.state.c_str(),&end);
  const bool numeric=end!=t.state.c_str()&&std::isfinite(parsed)&&t.available();
  const float current=numeric?parsed:NAN;
  c.first_text.clear();c.second_text.clear();
  if(line){
    int decimals=0;const auto dot=t.state.find('.');if(dot!=std::string::npos)decimals=static_cast<int>(std::min<size_t>(4,t.state.size()-dot-1));
    if(c.ready)decimals=h.decimals;
    c.value_text=!t.available()?std::string(tr(txt::ha_unavailable)):numeric?history_view::number(current,decimals,t.unit):t.state;
    if(c.ready){
      // The value now counts too: it can lie beyond the history (the running hour is not in the statistics yet).
      if(h.has_high){c.high=h.high;c.high_at=h.high_at;}
      if(h.has_low){c.low=h.low;c.low_at=h.low_at;}
      if(std::isfinite(current)&&std::isfinite(c.high)&&current>c.high){c.high=current;c.high_at=h.end;}
      if(std::isfinite(current)&&std::isfinite(c.low)&&current<c.low){c.low=current;c.low_at=h.end;}
    }
    if(std::isfinite(c.high))c.first_text=fill(txt::history_high,"value",history_view::number(c.high,h.decimals,h.unit))+" \u00B7 "+history_clock(c.high_at,h.hours==168);
    if(std::isfinite(c.low))c.second_text=fill(txt::history_low,"value",history_view::number(c.low,h.decimals,h.unit))+" \u00B7 "+history_clock(c.low_at,h.hours==168);
  }else{
    c.value_text=history_words(t);
    if(c.ready&&h.active>=0){
      c.first_text=h.states[h.active].label+" \u00B7 "+history_view::duration(h.states[h.active].seconds);
      c.second_text=h.began?plural(txt::history_times,h.began):"";
    }
  }
  const int row=ui::px(large?84:50),row_h=lv_font_get_line_height(big),text_h=lv_font_get_line_height(text);
  int right=width-pad-(ui::px(large?8:4));
  if(t.is_switch()){
    const int sw=ui::px(large?84:52),sh=ui::px(large?46:28);
    detail_switch=lv_switch_create(detail_root);
    lv_obj_set_size(detail_switch,sw,sh);lv_obj_set_pos(detail_switch,right-sw,row+(row_h-sh)/2);
    lv_obj_set_style_bg_color(detail_switch,theme::color(theme::SWITCH_OFF),LV_PART_MAIN);
    lv_obj_set_style_bg_color(detail_switch,lv_color_hex(theme::ha::SWITCH_ON),static_cast<lv_style_selector_t>(LV_PART_INDICATOR)|LV_STATE_CHECKED);
    lv_obj_set_style_bg_color(detail_switch,theme::color(theme::KNOB),LV_PART_KNOB);
    lv_obj_set_style_opa(detail_switch,LV_OPA_50,LV_STATE_DISABLED);
    if(t.state=="on")lv_obj_add_state(detail_switch,LV_STATE_CHECKED);
    lv_obj_add_event_cb(detail_switch,[](lv_event_t *e){
      if(detail_index>=model.count)return;
      auto &tile=model.tiles[detail_index];auto *control=lv_event_get_target_obj(e);
      bool allowed=fresh() && tile.available() && !tile.waiting(esphome::millis()) &&
        screen_input::touch_guard.accept(esphome::millis(),350);
      bool requested_on=lv_obj_has_state(control,LV_STATE_CHECKED);
      // Only HA's reported state is authoritative, including a refused/failed command.
      if(tile.state=="on")lv_obj_add_state(control,LV_STATE_CHECKED);else lv_obj_remove_state(control,LV_STATE_CHECKED);
      if(allowed){tile.optimistic(requested_on);action(tile.domain()+(requested_on?".turn_on":".turn_off"),tile.entity);}
    },LV_EVENT_VALUE_CHANGED,nullptr);
    if(detail_action_count<32)detail_actions[detail_action_count++]=detail_switch;
    right-=sw+(ui::px(large?14:8));
  }
  // The value column fits the widest text a finger can show there, so a readout never runs into the texts beside it.
  int widest=text_width(c.value_text,big);
  if(c.ready)widest=std::max(widest,text_width(tr(txt::history_no_data),big));
  if(c.ready&&line){for(int i=0;i<history_view::PARTS;++i)if(h.has[i])widest=std::max(widest,text_width(history_view::number(h.values[i],h.decimals,h.unit),big));}
  else if(c.ready){for(const auto &s:h.states)widest=std::max(widest,text_width(s.label,big));}
  const int value_x=pad+(ui::px(large?8:4)),value_w=std::min(widest+6,(width-2*pad)*11/20);
  c.value=detail_text(detail_root,c.value_text,value_x,row,value_w,big,LV_TEXT_ALIGN_LEFT,theme::INK);
  const int words_x=value_x+value_w+(ui::px(large?12:6)),words_w=std::max(20,right-words_x),words_y=row+(row_h-2*text_h)/2;
  c.first=detail_text(detail_root,c.first_text,words_x,words_y,words_w,text,LV_TEXT_ALIGN_RIGHT,theme::MUTED);
  c.second=detail_text(detail_root,c.second_text,words_x,words_y+text_h,words_w,text,LV_TEXT_ALIGN_RIGHT,theme::MUTED);
  int top=row+std::max(row_h,2*text_h)+(ui::px(large?10:4));
  if(d=="number"||d=="input_number"){
    const int slider_h=ui::px(large?24:14);
    // A slider is dragged, so it keeps a hand's width however wide the card's graph is.
    const auto bar=overlay_card::reach(width,width-2*pad-(ui::px(large?28:20)));
    auto *slider=lv_slider_create(detail_root);lv_obj_set_pos(slider,bar.x,top+(ui::px(large?10:5)));
    lv_obj_set_size(slider,bar.w,slider_h);lv_slider_set_range(slider,0,1000);
    lv_slider_set_value(slider,slider_value(t),LV_ANIM_OFF);lv_obj_set_style_bg_color(slider,theme::color(theme::SLIDER_KNOB),LV_PART_KNOB);
    lv_obj_add_event_cb(slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)detail_index);
    top+=slider_h+(ui::px(large?22:12));
  }
  const int range_h=ui::px(large?48:28),bottom=height-(ui::px(large?16:6)),range_y=bottom-range_h,card_h=range_y-(ui::px(large?10:5))-top;
  detail_card(pad,top,width-2*pad,card_h);
  const bool empty=c.ready&&(line?std::none_of(h.has,h.has+history_view::PARTS,[](bool v){return v;}):h.states.empty());
  if(!c.ready||empty){
    c.status=detail_text(detail_root,tr(!c.ready?txt::history_loading:txt::history_empty),pad,top+(card_h-text_h)/2,width-2*pad,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
  }else if(line){
    render_history_line(large,pad,top,width-2*pad,card_h,small,current);
  }else{
    render_history_timeline(large,pad,top,width-2*pad,card_h,small);
  }
  // The graph took the glass; the keys under it keep a hand's width and stand in the middle of the card.
  const auto keys=overlay_card::reach(width,width-2*pad);
  history_ranges(keys.x,range_y,keys.w,range_h);
}
// ---- The media card (firmware 0.2.64+) ----
// "Now playing" as a phone shows it: the album cover (app 0.2.77+ serves it, a Guition draws it; the CYD keeps the
// placeholder), the title, the artist and the album, a progress bar that runs while the track plays, round keys for
// previous, play or pause and next, and the volume row. media_card.h decides where everything goes for a tall card and
// a wide one; the same parts draw the card here and a tile over the whole page (render_media_full). The keys go
// through detail_command like every card's, the slider through commit_slider.
inline lv_obj_t *media_progress_fill=nullptr,*media_elapsed_label=nullptr;  // the card's, moved by tick() once a second
inline int media_bar_width=0;
inline media_card::Rect media_art_rect;  // where the card's cover goes once it is here
inline uint32_t media_accent(){return theme::foreground(theme::ha::LIGHT_BLUE);}
inline const lv_font_t *tile_icon_font(){for(auto &w:widgets)if(w.icon_font)return w.icon_font;return mini_icon_font?mini_icon_font:detail_font;}
inline media_card::Metrics media_metrics(bool large){
  media_card::Metrics m;m.large=large;
  const lv_font_t *title=watch_font?watch_font:detail_font,*artist=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  m.title_h=lv_font_get_line_height(title);m.artist_h=lv_font_get_line_height(artist);m.small_h=lv_font_get_line_height(small);
  return m;
}
// What the keys do, on the card and on a tile over the whole page: 20 play or pause, 21 previous, 22 next, 23 mute,
// 24 turn on, 30 turn off.
inline void media_action(Tile &t,int cmd){
  if(cmd==20)action("media_player.media_play_pause",media_entity(t));
  if(cmd==21)action("media_player.media_previous_track",media_entity(t));
  if(cmd==22)action("media_player.media_next_track",media_entity(t));
  if(cmd==23)action("media_player.volume_mute",media_entity(t),"is_volume_muted",t.muted?"false":"true");
  if(cmd==24)action("media_player.turn_on",media_entity(t));
  if(cmd==30)action("media_player.turn_off",media_entity(t));
  // Shuffle and repeat on the card (firmware 0.24.0+): the other way round, and repeat's next step.
  if(cmd==25)action("media_player.shuffle_set",media_entity(t),"shuffle",t.extra().media_shuffle==1?"false":"true");
  if(cmd==26)action("media_player.repeat_set",media_entity(t),"repeat",media_card::next_repeat(t.extra().media_repeat));
}
// An off or standby player shows one key: power, when the player can be turned on from here.
inline bool media_off(const Tile &t){return t.state=="off" || t.state=="standby";}
// A rounded box without a style of its own: the art's placeholder, the bar's track and its fill.
inline lv_obj_t *media_box(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,uint32_t color,int radius){
  auto *o=existing;
  if(!o){o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,std::max(1,r.w),std::max(1,r.h));
  set_color(o,LV_STYLE_BG_COLOR,theme::rgb(color));set_number(o,LV_STYLE_RADIUS,radius);
  return o;
}
// A round key: a glyph on a grey circle, the play key on the accent, the mute key bare beside the slider. Faded while
// it cannot be used. `existing` keeps a tile's key across redraws; the card builds its keys anew each time.
inline lv_obj_t *media_key(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,const char *glyph,const lv_font_t *font,bool accent,bool bare,bool enabled,lv_event_cb_t cb,void *user,
                           lv_event_code_t code=LV_EVENT_SHORT_CLICKED){
  auto *key=existing;
  if(!key){
    key=lv_obj_create(parent);lv_obj_remove_style_all(key);
    lv_obj_set_style_radius(key,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(key,bare?LV_OPA_TRANSP:LV_OPA_COVER,0);lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_PRESSED);
    lv_obj_set_style_opa(key,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_add_flag(key,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(key,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_ext_click_area(key,bare?10:6);
    auto *icon=lv_label_create(key);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(key,cb,code,user);
  }
  lv_obj_set_pos(key,r.x,r.y);lv_obj_set_size(key,r.w,r.h);
  set_color(key,LV_STYLE_BG_COLOR,theme::color(accent?theme::ACCENT:theme::KEY));
  set_color(key,LV_STYLE_BG_COLOR,theme::color(accent?theme::ACCENT_PRESSED:theme::KEY_PRESSED),LV_STATE_PRESSED);
  auto *icon=lv_obj_get_child(key,0);
  if(font)set_font(icon,font);
  set_color(icon,LV_STYLE_TEXT_COLOR,theme::color(accent?theme::ON_ACCENT:theme::INK));
  label(icon,glyph);center_icon(icon);
  if(enabled)lv_obj_remove_state(key,LV_STATE_DISABLED);else lv_obj_add_state(key,LV_STATE_DISABLED);
  return key;
}
// The volume slider: the media colour on a pale track, a round white knob, the range every card slider has.
inline lv_obj_t *media_slider(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,const Tile &t,bool large,bool enabled,void *user){
  auto *s=existing;
  if(!s){
    s=lv_slider_create(parent);lv_obj_remove_style_all(s);lv_slider_set_range(s,0,1000);
    lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_MAIN);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_INDICATOR);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_KNOB);
    lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_MAIN);lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_INDICATOR);lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_KNOB);
    lv_obj_set_style_pad_all(s,ui::px(large?4:3),LV_PART_KNOB);lv_obj_set_style_bg_opa(s,LV_OPA_80,(lv_style_selector_t)LV_PART_KNOB|(lv_style_selector_t)LV_STATE_PRESSED);
    lv_obj_set_style_opa(s,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_set_ext_click_area(s,ui::px(large?12:8));
    lv_obj_add_event_cb(s,slider_event,LV_EVENT_ALL,user);
  }
  lv_obj_set_pos(s,r.x,r.y);lv_obj_set_size(s,std::max(1,r.w),r.h);
  set_color(s,LV_STYLE_BG_COLOR,theme::rgb(theme::tint(theme::ha::LIGHT_BLUE,64)),LV_PART_MAIN);
  set_color(s,LV_STYLE_BG_COLOR,theme::rgb(t.muted?theme::hex(theme::OFF):media_accent()),LV_PART_INDICATOR);
  set_color(s,LV_STYLE_BG_COLOR,theme::color(theme::SLIDER_KNOB),LV_PART_KNOB);
  if(!lv_obj_has_state(s,LV_STATE_PRESSED) && lv_slider_get_value(s)!=slider_value(t))lv_slider_set_value(s,slider_value(t),LV_ANIM_OFF);
  if(enabled){lv_obj_remove_state(s,LV_STATE_DISABLED);lv_obj_add_flag(s,LV_OBJ_FLAG_CLICKABLE);}
  else{lv_obj_add_state(s,LV_STATE_DISABLED);lv_obj_remove_flag(s,LV_OBJ_FLAG_CLICKABLE);}
  return s;
}
// The cover over its placeholder: LVGL's image widget exists only on a board whose profile draws images.
inline lv_obj_t *media_picture_show(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,lv_image_dsc_t *src){
#if LV_USE_IMAGE
  if(!src || !src->data)return existing;
  auto *p=existing;
  if(!p){p=lv_image_create(parent);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);}
  lv_image_set_src(p,src);lv_obj_set_pos(p,r.x,r.y);lv_obj_set_size(p,r.w,r.h);lv_obj_invalidate(p);
  return p;
#else
  (void)parent;(void)r;(void)src;return existing;
#endif
}
// A media text that is wider than its line rolls by, round and round, and stands still when it fits (firmware 0.2.77+):
// LVGL's own circular scroll, at its own pace, where the dots of LV_LABEL_LONG_DOT cut a long title short.
inline void marquee(lv_obj_t *label,bool reading_pause=false,bool ready=true){
  if(!label)return;
  if(!ready){
    if(lv_label_get_long_mode(label)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(label,LV_LABEL_LONG_DOT);
    return;
  }
  if(lv_label_get_long_mode(label)==LV_LABEL_LONG_SCROLL_CIRCULAR)return;
  if(reading_pause){
    static const lv_anim_t timing=[](){lv_anim_t a;lv_anim_init(&a);lv_anim_set_delay(&a,1400);lv_anim_set_repeat_delay(&a,1800);lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);return a;}();
    lv_obj_set_style_anim(label,&timing,0);
    lv_obj_set_style_anim_duration(label,lv_anim_speed(ui::px(24)),0);
  }
  // LVGL cancels the old animation when long mode is assigned, even unchanged.
  lv_label_set_long_mode(label,LV_LABEL_LONG_SCROLL_CIRCULAR);
}
// The bar's fill and the elapsed time follow the track: once a second from tick(), without a redraw.
inline void media_progress(const Tile &t,lv_obj_t *fill,lv_obj_t *elapsed,int bar_w){
  const auto &x=t.extra();
  if(!fill || !x.media_duration)return;
  const bool play=media_card::playing(t.state);
  const int p=media_card::progress(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration);
  const int h=lv_obj_get_style_height(fill,LV_PART_MAIN);
  const int w=std::max(h,bar_w*std::max(0,p)/1000);
  if(lv_obj_get_style_width(fill,LV_PART_MAIN)!=w)lv_obj_set_width(fill,w);
  if(elapsed)label(elapsed,media_card::clock_text(media_card::elapsed_seconds(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration)));
}
// ---- The media card on its cover's ground (firmware 0.24.0+) ----
// The card is dark in both looks, the way a player's own "now playing" is: a ground running from one dark colour at the
// top to another at the bottom, both read from the cover by the app (two colours with the player's state, a few bytes),
// white words and keys on it. Everything is there before a picture is: a screen without pictures (the CYD) gets the
// same ground, and a cover only comes over its placeholder. Before the app has read a cover's colours, and for a cover
// without colour, and while nothing plays, the card is plain black (theme::MEDIA_TOP and MEDIA_BOTTOM; firmware 0.39.0,
// a grey to black gradient before).
struct MediaGround { uint32_t top, bottom; };
inline MediaGround media_ground(const Tile &t){
  const auto &x=t.extra();
  return x.has_ground?MediaGround{x.ground_top,x.ground_bottom}:MediaGround{theme::hex(theme::MEDIA_TOP),theme::hex(theme::MEDIA_BOTTOM)};
}
inline uint32_t media_ink(){return theme::hex(theme::CAMERA_INK);}
// The second line, the times and what is faded: the ink, a quarter of the way into the ground.
inline uint32_t media_soft(const MediaGround &g){return theme::mix(media_ink(),g.top,190);}
// The ground at a height of the card: what a cover's corners are rounded over.
inline uint32_t media_ground_at(const MediaGround &g,int y,int height){
  return theme::mix(g.bottom,g.top,(uint8_t)std::clamp(255*y/std::max(1,height),0,255));
}
// A key on the ground: a white key for the main one with the ground's own colour in it, a faint white circle for the
// others, none at all for a bare one (mute, shuffle, repeat), white icons.
inline void media_dark_key(lv_obj_t *key,bool primary,bool bare,const MediaGround &g,uint32_t icon_color=0){
  if(!key)return;
  set_color(key,LV_STYLE_BG_COLOR,theme::rgb(media_ink()));
  set_color(key,LV_STYLE_BG_COLOR,theme::rgb(primary?theme::mix(media_ink(),g.bottom,200):media_ink()),LV_STATE_PRESSED);
  set_number(key,LV_STYLE_BG_OPA,primary?LV_OPA_COVER:bare?LV_OPA_TRANSP:40);
  set_number(key,LV_STYLE_BG_OPA,primary?LV_OPA_COVER:90,LV_STATE_PRESSED);
  if(auto *icon=lv_obj_get_child(key,0))set_color(icon,LV_STYLE_TEXT_COLOR,theme::rgb(icon_color?icon_color:primary?g.bottom:media_ink()));
}
// The volume row's keys (firmware 0.39.0, GitHub #146), on the card and on a tile over the whole page, the keys the
// screensaver has: volume down and up step the player (Home Assistant's volume_down and volume_up), every clean tap
// counts and nothing waits for an answer, so a series of taps is a series of steps. Volume down held for a second and
// a half mutes the player where Home Assistant says it can be muted, and shows the muted speaker; the next tap on
// either key takes the mute off and changes nothing else.
constexpr uint32_t MEDIA_MUTE_HOLD_MS=1500;
inline uint32_t media_hold_at=0;    // when the finger came down on volume down; 0 once this hold has muted
inline bool media_hold_muted=false; // the hold muted: its own release is no step
// The tile the key belongs to: the open card's, or the tile over the whole page whose part the key is (asked of the
// key itself, never of a slot handed to LVGL: kept pages swap whole Widgets).
inline Tile *media_volume_tile(lv_obj_t *key,bool card){
  if(card)return detail_index<model.count?&model.tiles[detail_index]:nullptr;
  for(auto &w:widgets)if(w.extra_mode=="media"&&key&&(w.parts[11]==key||w.parts[13]==key))return w.index<model.count?&model.tiles[w.index]:nullptr;
  return nullptr;
}
inline std::string media_mute_entity;
inline void media_mute(Tile &t,bool muted){
  step_action("media_player.volume_mute",media_entity(t),"is_volume_muted",muted?"true":"false");
  t.muted=muted;
  // The card and the tiles show it at once; drawn after this event, which belongs to a key the redraw may delete.
  media_mute_entity=t.entity;
  lv_async_call([](void *){
    for(size_t i=0;i<model.count;++i)if(model.tiles[i].entity==media_mute_entity)refresh_tile(i);
    if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))redraw_detail();
  },nullptr);
}
inline void media_volume_event(lv_event_t *e){
  const intptr_t tag=(intptr_t)lv_event_get_user_data(e);
  const bool up=tag&1,card=tag&2;
  const auto code=lv_event_get_code(e);
  const uint32_t now=esphome::millis();
  auto *key=lv_event_get_current_target_obj(e);
  if(!enabled||!fresh()||lv_obj_has_state(key,LV_STATE_DISABLED))return;
  Tile *t=media_volume_tile(key,card);
  if(!t||!t->available())return;
  if(code==LV_EVENT_PRESSED){media_hold_at=now?now:1;media_hold_muted=false;return;}
  if(code==LV_EVENT_PRESSING){
    if(!media_hold_at||now-media_hold_at<MEDIA_MUTE_HOLD_MS||t->muted||!(t->supported&tile_controls::feature::MEDIA_VOLUME_MUTE))return;
    media_hold_at=0;media_hold_muted=true;
    media_mute(*t,true);
    return;
  }
  if(media_hold_muted){media_hold_muted=false;return;}
  if(!screen_input::touch_guard.accept_repeat(now,720+up))return;
  if(t->muted){media_mute(*t,false);return;}
  step_action(up?"media_player.volume_up":"media_player.volume_down",media_entity(*t));
}
// Volume down, the slider and volume up. `parts` keeps a tile's three across redraws (nullptr: the card makes them
// anew), `g` the card's ground its keys are drawn on (a tile keeps the keys' own colours).
inline void media_volume_row(lv_obj_t *parent,lv_obj_t **parts,const media_card::Rect &minus,const media_card::Rect &volume,const media_card::Rect &plus,
                             const Tile &t,bool large,bool usable,void *slider_user,bool card,const MediaGround *g,const lv_font_t *font){
  using namespace tile_controls;
  const uint32_t f=t.supported;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  const bool step=can(feature::MEDIA_VOLUME_SET|feature::MEDIA_VOLUME_STEP)||(t.muted&&can(feature::MEDIA_VOLUME_MUTE));
  const intptr_t tag=card?2:0;
  lv_obj_t *made[3];
  const bool fresh_minus=!parts||!parts[0];
  made[0]=media_key(parent,parts?parts[0]:nullptr,minus,t.muted?glyph::MUTED:glyph::MINUS,font,false,false,step,media_volume_event,(void*)tag,LV_EVENT_CLICKED);
  if(fresh_minus){
    lv_obj_add_event_cb(made[0],media_volume_event,LV_EVENT_PRESSED,(void*)tag);
    lv_obj_add_event_cb(made[0],media_volume_event,LV_EVENT_PRESSING,(void*)tag);
  }
  made[1]=media_slider(parent,parts?parts[1]:nullptr,volume,t,large,can(feature::MEDIA_VOLUME_SET),slider_user);
  made[2]=media_key(parent,parts?parts[2]:nullptr,plus,glyph::PLUS,font,false,false,step,media_volume_event,(void*)(tag|1),LV_EVENT_CLICKED);
  if(g){
    const uint32_t ink=media_ink(),soft=media_soft(*g);
    media_dark_key(made[0],false,false,*g);media_dark_key(made[2],false,false,*g);
    set_color(made[1],LV_STYLE_BG_COLOR,theme::rgb(theme::mix(ink,g->bottom,70)),LV_PART_MAIN);
    set_color(made[1],LV_STYLE_BG_COLOR,theme::rgb(t.muted?soft:ink),LV_PART_INDICATOR);
    set_color(made[1],LV_STYLE_BG_COLOR,theme::rgb(ink),LV_PART_KNOB);
  }
  if(parts)for(int i=0;i<3;++i)parts[i]=made[i];
}
// The media card's seek (firmware 0.24.0+): a finger on the bar moves its knob, and the place it lets go of is sent.
// The bar then stands there until Home Assistant reports the player near it (media_card::Seek).
inline std::string media_ground_waited;
inline uint32_t media_ground_since=0;
inline bool media_ground_pending=false;
constexpr uint32_t MEDIA_GROUND_WAIT_MS=2500;
inline media_card::Seek media_seek;
inline std::string media_seek_entity;
inline lv_obj_t *media_knob=nullptr;
// The card's pill and library key (firmware 0.24.0+), for the render harness.
inline lv_obj_t *media_pill_obj=nullptr,*media_library_key=nullptr,*media_input_key=nullptr;
inline int media_bar_x=0,media_knob_size=0;
inline bool media_seeking=false;
// Where the track is now, as the card shows it: a seek just sent wins over Home Assistant's word until it agrees.
inline uint32_t media_elapsed(const Tile &t){
  const auto &x=t.extra();
  const bool play=media_card::playing(t.state);
  const uint32_t now=now_epoch();
  if(media_seek_entity==t.entity&&media_seek.holds(x.media_position,x.media_position_at,esphome::millis(),now,play,x.media_title)){
    uint32_t at=media_seek.seconds+(play&&now>media_seek.epoch?now-media_seek.epoch:0);
    return x.media_duration?std::min(at,x.media_duration):at;
  }
  return media_card::elapsed_seconds(x.media_position,x.media_position_at,now,play,x.media_duration);
}
// The fill and the knob at a number of seconds.
inline void media_bar_at(uint32_t seconds,uint32_t duration,lv_obj_t *fill,lv_obj_t *elapsed,int bar_w){
  if(!fill||!duration)return;
  const int h=lv_obj_get_style_height(fill,LV_PART_MAIN);
  const int w=std::max(h,(int)((uint64_t)bar_w*std::min(seconds,duration)/duration));
  if(lv_obj_get_style_width(fill,LV_PART_MAIN)!=w)lv_obj_set_width(fill,w);
  if(media_knob&&lv_obj_get_parent(media_knob)==lv_obj_get_parent(fill))lv_obj_set_x(media_knob,media_bar_x+w-media_knob_size/2);
  if(elapsed)label(elapsed,media_card::clock_text(seconds));
}
inline void media_seek_event(lv_event_t *e){
  const auto code=lv_event_get_code(e);
  if(detail_index>=model.count||!media_progress_fill)return;
  auto &t=model.tiles[detail_index];
  const auto &x=t.extra();
  if(!x.media_duration)return;
  lv_point_t point;lv_indev_get_point(lv_indev_active(),&point);
  lv_area_t area;lv_obj_get_coords(lv_obj_get_parent(media_progress_fill),&area);
  const int along=point.x-area.x1-media_bar_x;
  const uint32_t seconds=media_card::seek_seconds(along,media_bar_width,x.media_duration);
  if(code==LV_EVENT_PRESSED||code==LV_EVENT_PRESSING){media_seeking=true;media_bar_at(seconds,x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);return;}
  if(code==LV_EVENT_PRESS_LOST){media_seeking=false;media_bar_at(media_elapsed(t),x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);return;}
  if(code!=LV_EVENT_RELEASED||!media_seeking)return;
  media_seeking=false;
  if(!fresh()||!t.available())return;
  media_seek.send(seconds,esphome::millis(),now_epoch(),x.media_title);media_seek_entity=t.entity;
  media_bar_at(seconds,x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);
  action("media_player.media_seek",media_entity(t),"seek_position",std::to_string(seconds));
}
// The card's top bar for a player (firmware 0.24.0+): the back key on the ground, the speaker it plays on as a pill
// in the middle where Home Assistant lists speakers (a tap opens the menu of them), and at the right the power key,
// where every other card has it (firmware 0.39.0, GitHub #146). A player without speakers keeps its name there. The
// library and the input keys stood at the right before; they close the volume row now (media_row_keys).
// The power key follows Home Assistant's dialog (computeMediaControls): turn off for a player that is on and can be
// turned off, and for a player whose state is only assumed both keys, whatever it reports. An off player's turn on is
// the big key in the middle of the card.
inline void media_top_bar(const Tile &t,lv_obj_t *back,lv_obj_t *heading,int width,int bar,int bar_x,int bar_y){
  using namespace tile_controls;
  const auto &x=t.extra();
  const MediaGround g=media_ground(t);
  media_dark_key(back,false,false,g);
  set_color(heading,LV_STYLE_TEXT_COLOR,theme::rgb(media_ink()));
  auto cb=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  const lv_font_t *icons=mini_icon_font?mini_icon_font:detail_font;
  const bool usable=fresh()&&t.available(),off=media_off(t);
  const bool power_off=usable&&(t.supported&feature::MEDIA_TURN_OFF)&&(!off||x.assumed);
  const bool power_on=usable&&(t.supported&feature::MEDIA_TURN_ON)&&!off&&x.assumed;
  const int key_gap=ui::px(ui::large()?8:6);
  int right=0;  // the room the keys at the right take, from the glass's edge
  for(int cmd:{30,24}){
    if(cmd==30?!power_off:!power_on)continue;
    const media_card::Rect r{width-bar_x-bar-(right?right-bar_x+key_gap:0),bar_y,bar,bar};
    auto *key=media_key(detail_root,nullptr,r,glyph::STANDBY,icons,false,false,true,cb,(void*)(intptr_t)cmd);
    media_dark_key(key,false,false,g);
    right=width-r.x;
  }
  media_pill_obj=nullptr;
  if(right>bar_x+bar){
    // Two keys at the right: the name keeps clear of both, centred between the back key and them.
    const int left=bar_x+bar+8,w=std::max(1,width-left-right-8);
    lv_obj_set_x(heading,left);lv_obj_set_width(heading,w);
  }
  if(x.media_sources.empty())return;
  lv_obj_add_flag(heading,LV_OBJ_FLAG_HIDDEN);
  // The pill: the speaker icon, the speaker's name (or "Choose a speaker"), the arrow of a menu.
  const lv_font_t *font=control_font?control_font:detail_font;
  const std::string name=x.media_source.empty()?std::string(tr(txt::media_choose_speaker)):x.media_source;
  const int h=bar*3/4,inset=ui::px(ui::large()?14:8),icon_w=lv_font_get_line_height(icons),gap=ui::px(ui::large()?6:4);
  // The room between the back key and the keys at the right; the pill stands in the middle of the glass where it fits
  // there, and in the middle of that room when two keys at the right leave too little (a speaker's name stays whole).
  const int lo=bar_x+bar+gap,hi=width-bar_x-std::max(bar,right-bar_x)-gap,room=std::max(h,hi-lo);
  const int w=std::max(h,std::min(room,inset+icon_w+gap+text_width(name,font)+gap+icon_w+inset));
  const int centred=(width-w)/2,px_left=centred>=lo&&centred+w<=hi?centred:lo+(room-w)/2;
  auto *pill=lv_obj_create(detail_root);lv_obj_remove_style_all(pill);
  lv_obj_set_pos(pill,px_left,bar_y+(bar-h)/2);lv_obj_set_size(pill,w,h);
  lv_obj_set_style_radius(pill,LV_RADIUS_CIRCLE,0);lv_obj_add_flag(pill,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(pill,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(pill,theme::rgb(media_ink()),0);lv_obj_set_style_bg_opa(pill,40,0);lv_obj_set_style_bg_opa(pill,90,LV_STATE_PRESSED);
  lv_obj_set_ext_click_area(pill,(bar-h)/2);
  lv_obj_add_event_cb(pill,cb,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)28);
  media_pill_obj=pill;
  auto glyph_at=[&](const char *glyph,int gx){
    auto *icon=lv_label_create(pill);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);set_font(icon,icons);
    lv_obj_set_style_text_color(icon,theme::rgb(media_ink()),0);lv_label_set_text(icon,glyph);
    lv_obj_set_pos(icon,gx,(h-lv_font_get_line_height(icons))/2);
  };
  glyph_at("\U000F04C3",inset);
  glyph_at("\U000F0140",w-inset-icon_w);
  auto *words=detail_text(pill,name,inset+icon_w+gap,(h-lv_font_get_line_height(font))/2,std::max(1,w-2*(inset+icon_w+gap)),font,LV_TEXT_ALIGN_CENTER,media_ink());
  lv_obj_remove_flag(words,LV_OBJ_FLAG_CLICKABLE);
}
// The card: everything under the top bar, from `top` down.
inline void render_media_detail(Tile &t,unsigned index,bool large,int width,int height,int top){
  using namespace media_card;
  using namespace tile_controls;
  const auto &x=t.extra();
  const Metrics m=media_metrics(large);
  // The volume row ends with the keys of what the player has besides: its inputs, and its library outermost.
  const bool library=x.media_library&&media_library::available(),inputs=!x.media_inputs.empty();
  const Layout l=layout(m,width,std::max(60,height-top-(ui::px(large?12:6))),library+inputs);
  auto at=[&](Rect r){r.y+=top;return r;};
  const bool usable=fresh()&&t.available(),track=usable&&has_track(t.state),play=media_card::playing(t.state);
  const uint32_t f=t.supported,had=f|x.media_features;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  const MediaGround g=media_ground(t);
  const uint32_t ink=media_ink(),soft=media_soft(g);
  // A player at rest whose library opens, with nothing to play or pause (Spotify playing nowhere): the card says how
  // to start it, and its one key is the library.
  const bool rest=usable&&!track&&!media_off(t)&&x.media_library&&media_library::available()&&!(f&(feature::MEDIA_PLAY|feature::MEDIA_PAUSE));
  // The cover, or its placeholder with the player's icon; the cover comes over it once the app served it.
  // A darker square on a cover's colours, a faint white one on the plain black.
  auto *frame=media_box(detail_root,nullptr,at(l.art),x.has_ground?theme::hex(theme::CAMERA_PAGE):ink,l.art_radius);
  lv_obj_set_style_bg_opa(frame,x.has_ground?60:24,0);
  const std::string glyph=rest?std::string("\U000F04C7"):icon_for(t);
  // The big icon where the square holds it, the tile's icon in a small one.
  const lv_font_t *placeholder_font=big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=l.art.h?big_icon_font:tile_icon_font();
  auto *icon=lv_label_create(frame);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_text_font(icon,placeholder_font,0);
  lv_obj_set_style_text_color(icon,theme::rgb(theme::mix(ink,g.top,120)),0);lv_label_set_text(icon,glyph.c_str());center_icon(icon);
  media_art_rect=at(l.art);media_detail_picture=nullptr;
  const uint32_t ground=media_ground_at(g,media_art_rect.cy(),height);
  // The cover is rounded over the ground behind it, so it is asked for once the app has read its colours, or after
  // MEDIA_GROUND_WAIT_MS without them (an app from before): one download per track, not one for each ground.
  const std::string waited=t.entity+"|"+x.media_picture;
  if(waited!=media_ground_waited){media_ground_waited=waited;media_ground_since=esphome::millis();}
  media_ground_pending=!x.ground_known&&esphome::millis()-media_ground_since<MEDIA_GROUND_WAIT_MS;
  if(camera_supported()&&track&&!x.media_picture.empty()&&!media_ground_pending){
    cover_want(t.entity,x.media_picture,l.art.w,ground,CoverOwner::DETAIL,0);
    media_detail_picture=media_picture_show(detail_root,nullptr,media_art_rect,cover_ready(t.entity,l.art.w,ground));
  }
  // Title, artist · album.
  const lv_font_t *title_font=watch_font?watch_font:detail_font,*artist_font=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  const lv_text_align_t align=l.wide?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER;
  // A title or artist line wider than the card rolls by, round and round (firmware 0.2.77+); a shorter one stands still.
  marquee(detail_text(detail_root,track&&!x.media_title.empty()?x.media_title:std::string(idle_text(usable?t.state:"unavailable")),l.title.x,l.title.y+top,l.title.w,title_font,align,ink));
  const std::string second=track?subtitle(x.media_artist,x.media_album):rest?std::string(tr(txt::media_library_hint)):std::string();
  if(l.artist)marquee(detail_text(detail_root,second,l.artist_line.x,l.artist_line.y+top,l.artist_line.w,artist_font,align,soft));
  // The progress bar: the fill runs while the track plays; a stream without a length has no bar to show. Where the
  // player seeks (firmware 0.24.0+) the bar has a knob, and a finger on it moves the track.
  media_progress_fill=nullptr;media_elapsed_label=nullptr;media_knob=nullptr;media_bar_width=l.bar.w;media_bar_x=l.bar.x;
  if(track && x.media_duration){
    const bool seek=can(feature::MEDIA_SEEK);
    if(seek){
      auto *area=lv_obj_create(detail_root);lv_obj_remove_style_all(area);
      lv_obj_set_pos(area,l.seek.x,l.seek.y+top);lv_obj_set_size(area,l.seek.w,l.seek.h);
      lv_obj_add_flag(area,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(area,LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_remove_flag(area,LV_OBJ_FLAG_GESTURE_BUBBLE);
      overlay_card::touchable(area,l.seek.h);
      lv_obj_add_event_cb(area,media_seek_event,LV_EVENT_ALL,nullptr);
    }
    media_box(detail_root,nullptr,at(l.bar),theme::mix(ink,g.top,70),LV_RADIUS_CIRCLE);
    const uint32_t elapsed=media_elapsed(t);
    Rect fill=at(l.bar);fill.w=std::max(l.bar.h,(int)((uint64_t)l.bar.w*std::min(elapsed,x.media_duration)/x.media_duration));
    media_progress_fill=media_box(detail_root,nullptr,fill,ink,LV_RADIUS_CIRCLE);
    if(seek){
      media_knob_size=l.bar.h+ui::px(large?14:10);
      media_knob=media_box(detail_root,nullptr,Rect{fill.right()-media_knob_size/2,fill.cy()-media_knob_size/2,media_knob_size,media_knob_size},ink,LV_RADIUS_CIRCLE);
    }
    if(l.times){
      media_elapsed_label=detail_text(detail_root,clock_text(elapsed),l.elapsed.x,l.elapsed.y+top,l.elapsed.w,small,LV_TEXT_ALIGN_LEFT,soft);
      detail_text(detail_root,clock_text(x.media_duration),l.total.x,l.total.y+top,l.total.w,small,LV_TEXT_ALIGN_RIGHT,soft);
    }
  }
  // The keys: previous, play or pause in white, next; shuffle and repeat at the ends where the row has room; under them
  // the volume row. An off player shows one power key instead, and no volume: it reports none. A player at rest with a
  // library shows the Library key.
  auto cb=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  const lv_font_t *key_font=mini_icon_font?mini_icon_font:detail_font;
  std::vector<lv_obj_t *> keys;
  if(rest){
    // Where the keys would be: under the words on a tall card, in the column beside the cover on a wide one.
    const int w=std::min(std::max(l.next.right()-l.prev.x,ui::px(large?200:120)),l.title.w);
    auto *start=detail_button(tr(txt::media_library),l.play.cx()-w/2,l.play.y+top,w,l.play.h,27);
    lv_obj_set_style_radius(start,LV_RADIUS_CIRCLE,0);
    set_color(start,LV_STYLE_BG_COLOR,theme::rgb(ink));set_color(start,LV_STYLE_BG_COLOR,theme::rgb(theme::mix(ink,g.bottom,200)),LV_STATE_PRESSED);
    if(auto *words=lv_obj_get_child(start,0)){
      set_color(words,LV_STYLE_TEXT_COLOR,theme::rgb(g.bottom));
      if(control_font){set_font(words,control_font);lv_obj_set_height(words,lv_font_get_line_height(control_font));}
      lv_obj_center(words);
    }
  }else if(usable && media_off(t)){
    if(can(feature::MEDIA_TURN_ON)){keys.push_back(media_key(detail_root,nullptr,at(l.play),glyph::STANDBY,tile_icon_font(),true,false,true,cb,(void*)(intptr_t)24));media_dark_key(keys.back(),true,false,g);}
  }else{
    keys={media_key(detail_root,nullptr,at(l.prev),glyph::PREVIOUS,key_font,false,false,can(feature::MEDIA_PREVIOUS),cb,(void*)(intptr_t)21),
          media_key(detail_root,nullptr,at(l.play),play?glyph::PAUSE:glyph::PLAY,tile_icon_font(),true,false,can(feature::MEDIA_PLAY|feature::MEDIA_PAUSE),cb,(void*)(intptr_t)20),
          media_key(detail_root,nullptr,at(l.next),glyph::NEXT,key_font,false,false,can(feature::MEDIA_NEXT),cb,(void*)(intptr_t)22)};
    media_dark_key(keys[0],false,false,g);media_dark_key(keys[1],true,false,g);media_dark_key(keys[2],false,false,g);
    // Shuffle on is the accent with a dot under it, as on a phone; repeat all and one the accent, off a faded white.
    if(l.sides && x.media_shuffle>=0 && (had&feature::MEDIA_SHUFFLE)){
      const bool on=x.media_shuffle==1;
      keys.push_back(media_key(detail_root,nullptr,at(l.shuffle),"\U000F049F",key_font,false,true,can(feature::MEDIA_SHUFFLE),cb,(void*)(intptr_t)25));
      media_dark_key(keys.back(),false,true,g,on?media_accent():soft);
      if(on){const int d=ui::px(large?5:4);media_box(detail_root,nullptr,Rect{at(l.shuffle).cx()-d/2,at(l.shuffle).bottom()+ui::px(2),d,d},media_accent(),LV_RADIUS_CIRCLE);}
    }
    if(l.sides && !x.media_repeat.empty() && (had&feature::MEDIA_REPEAT)){
      const bool on=x.media_repeat!="off";
      keys.push_back(media_key(detail_root,nullptr,at(l.repeat),x.media_repeat=="one"?"\U000F0458":"\U000F0456",key_font,false,true,can(feature::MEDIA_REPEAT),cb,(void*)(intptr_t)26));
      media_dark_key(keys.back(),false,true,g,on?media_accent():soft);
    }
    if(std::isfinite(t.volume))media_volume_row(detail_root,nullptr,at(l.minus),at(l.volume),at(l.plus),t,large,usable,(void*)(uintptr_t)index,true,&g,key_font);
  }
  // The player's own keys at the right end of the volume row, whatever it plays: the inputs (firmware 0.26.0+, Home
  // Assistant's source of a player whose sources are inputs, a Sonos's TV input or a TV's ports, with its icon) and the
  // library (firmware 0.24.0+).
  media_library_key=media_input_key=nullptr;
  int end=0;
  for(int cmd:{27,29}){
    if(cmd==27?!library:!inputs)continue;
    auto *key=media_key(detail_root,nullptr,at(l.ends[end++]),cmd==27?"\U000F0CB8":"\U000F0206",key_font,false,false,true,cb,(void*)(intptr_t)cmd);
    media_dark_key(key,false,false,g);
    (cmd==27?media_library_key:media_input_key)=key;
  }
  // Only the keys the player supports join the card's actions: tick() enables those again after a wait, and a key
  // the player lacks stays faded.
  for(auto *k:keys)if(!lv_obj_has_state(k,LV_STATE_DISABLED) && detail_action_count<32)detail_actions[detail_action_count++]=k;
}
inline void show_detail(unsigned index){
  if(index>=model.count)return;
  // Another tile's card: a keypad left open for an alarm does not come back with it.
  if(alarm_pad.open&&model.tiles[index].entity!=alarm_pad.entity)alarm_close_pad();
  // A card that opens starts on a day (an hour for a tile whose graph shows one); switching ranges keeps it open.
  if(!detail_root||lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)||detail_index!=index){
    history_hours=model.tiles[index].history_hours==1?1:24;history_asked_entity.clear();weather_page=0;select_page=0;
  }
  detail_index=index;auto &t=model.tiles[index];
  if(!detail_font)detail_font=lv_obj_get_style_text_font(widgets[0].title,LV_PART_MAIN);
  if(!detail_root){
    // The backdrop covers the page; the card itself is only as wide as a hand spans (overlay_card).
    detail_backdrop=lv_obj_create(lv_screen_active());lv_obj_remove_style_all(detail_backdrop);
    lv_obj_set_size(detail_backdrop,lv_pct(100),lv_pct(100));lv_obj_remove_flag(detail_backdrop,LV_OBJ_FLAG_SCROLLABLE);
    // Nothing leaks through to what lies under it, the same rule the effects page keeps. LVGL looks on
    // under an overlay that takes no press: a tap in the room a card leaves reached the tiles and the page
    // keys behind it, so a miss beside the range keys turned the page under the open card (firmware 0.2.82).
    lv_obj_add_flag(detail_backdrop,LV_OBJ_FLAG_CLICKABLE);
    detail_root=lv_obj_create(lv_screen_active());lv_obj_remove_style_all(detail_root);lv_obj_set_size(detail_root,lv_pct(100),lv_pct(100));lv_obj_remove_flag(detail_root,LV_OBJ_FLAG_SCROLLABLE);
  }
  lv_obj_set_style_bg_color(detail_backdrop,theme::color(theme::PAGE),0);lv_obj_set_style_bg_opa(detail_backdrop,LV_OPA_COVER,0);
  lv_obj_remove_flag(detail_backdrop,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(detail_backdrop);
  detail_action_count=0;detail_status=nullptr;detail_badge_status=nullptr;detail_switch=nullptr;climate_number=nullptr;climate_ends[0]=climate_ends[1]=nullptr;climate_now_mark=nullptr;climate_keys[0]=climate_keys[1]=nullptr;detail_placed=false;detail_status_brief=false;history_forget();
  alarm_forget_widgets();media_progress_fill=nullptr;media_elapsed_label=nullptr;media_detail_picture=nullptr;weather_days_card=nullptr;weather_dots=nullptr;weather_chevron[0]=weather_chevron[1]=nullptr;light_value=nullptr;lv_obj_clean(detail_root);lv_obj_remove_flag(detail_root,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(detail_root);
  lv_obj_set_style_bg_color(detail_root,theme::color(theme::PAGE),0);lv_obj_set_style_bg_opa(detail_root,LV_OPA_COVER,0);
  lv_obj_set_style_bg_grad_dir(detail_root,LV_GRAD_DIR_NONE,0);
  media_knob=media_pill_obj=media_library_key=media_input_key=nullptr;
  // The card's room: capped to what a hand spans and centred, unless it shows a picture (the media card's
  // cover art, a camera), which may fill the glass. Every size below follows from `width`.
  auto d=t.domain();
  // A player's card stands on its cover's ground, top to bottom (firmware 0.24.0+).
  if(d=="media_player"){
    const MediaGround g=media_ground(t);
    lv_obj_set_style_bg_color(detail_root,theme::rgb(g.top),0);
    lv_obj_set_style_bg_grad_color(detail_root,theme::rgb(g.bottom),0);
    lv_obj_set_style_bg_grad_dir(detail_root,LV_GRAD_DIR_VER,0);
    lv_obj_set_style_bg_color(detail_backdrop,theme::rgb(g.bottom),0);
  }
  // A day of a sensor is a picture as much as a cover is: it may take the whole glass, and only the row of
  // range keys under it keeps a hand's width (overlay_card::reach). Asked here because every size below
  // follows from `width`.
  const bool with_history=history_card(t);
  const auto kind=d=="media_player"?overlay_card::picture:with_history?overlay_card::graph:overlay_card::controls;
  bool large=ui::large();
  // A card whose stack asks for more height than the glass has stands in two columns instead.
  const int columns=d=="climate"||d=="humidifier"?climate_columns(t,large):d=="cover"?cover_columns(t,large):d=="weather"?weather_columns(t,large)
                     :d=="light"||d=="fan"?light_columns(large):1;
  overlay_card::frame(detail_root,kind,columns);
  // The room the frame just gave the card; LVGL reports the new width only after its next layout pass.
  int width=overlay_card::content_width(kind,columns), height=overlay_card::screen_height();int pad=overlay_card::pad(), top=ui::px(large?100:62), gap=ui::px(large?12:6),bh=ui::px(large?58:34),cw=(width-pad*2-gap)/2;
  // The same top bar as the board's own cards: a round back arrow at the left, the name centred.
  int bar=ui::px(large?60:40),bar_x=ui::px(large?16:10),bar_y=ui::px(large?16:8);
  auto *back=detail_button("",bar_x,bar_y,bar,bar,-1);lv_obj_set_style_radius(back,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(back,theme::color(theme::KEY),0);
  auto *arrow=lv_obj_get_child(back,0);if(mini_icon_font)lv_obj_set_style_text_font(arrow,mini_icon_font,0);lv_label_set_text(arrow,"\U000F004D");lv_obj_set_size(arrow,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(arrow);
  const lv_font_t *title_font=watch_font?watch_font:detail_font;
  auto *heading=detail_label(detail_root,t.name,bar_x+bar+8,bar_y+(bar-lv_font_get_line_height(title_font))/2,width-2*(bar_x+bar+8));
  lv_obj_set_style_text_font(heading,title_font,0);lv_obj_set_height(heading,lv_font_get_line_height(title_font));lv_obj_set_style_text_align(heading,LV_TEXT_ALIGN_CENTER,0);
  if(d=="media_player")media_top_bar(t,back,heading,width,bar,bar_x,bar_y);
  std::string state=card_status(t);
  // The vacuum and history cards draw their own state.
  if(d!="vacuum"&&d!="media_player"&&d!="climate"&&d!="humidifier"&&d!="light"&&d!="fan"&&d!="select"&&d!="input_select"&&!with_history){detail_status=detail_label(detail_root,screen_text::with_unit(state,t.unit),pad,ui::px(large?80:50),width-2*pad);lv_obj_set_style_text_align(detail_status,LV_TEXT_ALIGN_CENTER,0);lv_obj_set_style_text_color(detail_status,theme::color(theme::MUTED),0);}
  if(with_history){
    render_history_detail(t,large,width,height,pad);
  }else if(d=="vacuum"){
    render_vacuum_detail(t,large,width,height,pad);
  }else if(d=="climate"||d=="humidifier"){
    // A humidifier is the thermostat's card in percent: its power key, the humidity it is set to, its modes.
    render_climate_detail(t,large,width,height,columns);
  }else if(d=="cover"){
    if(detail_status && control_font){lv_obj_set_style_text_font(detail_status,control_font,0);lv_obj_set_height(detail_status,lv_font_get_line_height(control_font));}
    render_cover_detail(t,large,width,height,pad,columns);
  }else if(d=="remote"){
    render_remote_detail(t,large,width,height,pad,top,bar,bar_x,bar_y);
  }else if(d=="select"||d=="input_select"){
    render_select_detail(t,large,width,height,pad,top,t.state);
  }else if(d=="media_player"){
    // "Now playing" (firmware 0.2.64+): the cover, the track, a running progress bar, round keys and the volume row.
    render_media_detail(t,index,large,width,height,bar_y+bar+(ui::px(large?8:4)));
  }else if(d=="light"||d=="fan"){
    render_light_detail(t,large,width,height,columns);
  }else if(d=="weather"){
    render_weather_detail(t,large,width,height,columns);
  }else if(d=="alarm_control_panel"){
    render_alarm_detail(t,large,width,height,heading);
  }else if(d=="lock"){
    render_lock_detail(t,large,width,height,heading);
  }else if(d=="timer"){
    detail_label(detail_root,tr(t.state=="active"?txt::timer_running:t.state=="paused"?txt::timer_paused:txt::timer_stopped),pad,top,width-2*pad);
    detail_button(tr(t.state=="active"?txt::timer_pause:txt::timer_start),pad,top+(ui::px(large?50:30)),cw,bh,40);
    detail_button(tr(txt::timer_cancel),pad+cw+gap,top+(ui::px(large?50:30)),cw,bh,41);
  }else if(d=="sun"){
    detail_label(detail_root,fill(txt::sun_sunrise,"time",screen_text::clock_text(t.extra().sunrise,screen_settings::current.clock_24h!=0)),pad,top,width-2*pad);
    detail_label(detail_root,fill(txt::sun_sunset,"time",screen_text::clock_text(t.extra().sunset,screen_settings::current.clock_24h!=0)),pad,top+lv_font_get_line_height(detail_font)+(ui::px(large?10:4)),width-2*pad);
  }
  // A card that leaves room sits in the middle of the glass; a picture fills it and stays where it is.
  // The back key and the name stay at the top of the card; the content under them is centred.
  if(kind==overlay_card::controls&&!detail_placed)overlay_card::centre(detail_root,2);
}
}

namespace runtime_tiles {
inline void history_received(){
  if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)&&detail_index<model.count&&
     model.tiles[detail_index].entity==history.entity&&history_hours==history.hours)refresh_detail(detail_index);
}
inline void refresh_detail(unsigned index){
  if(!detail_root || lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) || detail_index!=index)return;
  // A player's library or speaker menu over its card follows the player itself; the card is drawn again when they
  // close (firmware 0.24.0+).
  if(index<model.count && (media_library::visible()||media_library::menu_visible())){media_library::updated(model.tiles[index].entity);return;}
  auto *input=lv_indev_get_next(nullptr);if(input && lv_indev_get_state(input)==LV_INDEV_STATE_PRESSED)return;
  show_detail(index);
}
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
  // Home Assistant's automation icons (automation/icons.json): a robot, crossed out while off.
  if (d == "automation" && tile.state == "off") return "\U000F16A7";
  if (d == "automation") return "\U000F06A9";
  // Home Assistant's remote icons (remote/icons.json), crossed out while off (firmware 0.22.0+).
  if (d == "remote" && tile.state == "off") return "\U000F0EC4";
  if (d == "remote") return "\U000F0454";
  if (d == "weather") return tile.available() ? weather_icon(tile.state) : "\U000F0595";
  if (d == "sensor" || d == "binary_sensor") return "\U000F029A";
  if (d == "sun") return tile.state == "above_horizon" ? "\U000F059B" : "\U000F059C";
  if (d == "timer") return "\U000F051B";
  if (d == "person") return "\U000F0004";
  // The map tile's marker (firmware 0.21.0) only shows while its picture is on its way.
  if (d == "screen") return tile.is_settings() ? "\U000F0493" : tile.is_page() ? "\U000F0054" : tile.entity == "screen.map" ? "\U000F034E" : "\U000F0150";
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
  if (choice.empty() || choice == "auto") return false;
  if (choice == "none") { out.clear(); return true; }
  if (choice.compare(0, 5, "text:") == 0) { out = choice.substr(5); return true; }
  if (choice.compare(0, 5, "attr:") != 0) return false;
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
    if (!card.is_settings() || card.tap == "none" || (settings_screen::may_open && !settings_screen::may_open())) return;
    if (allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), card.entity)) settings_screen::open();
    return;
  }
  if (!fresh()) return;
  if (!allowed(esphome::millis(), TILE_TOUCH + static_cast<int>(w.index), model.tiles[w.index].entity)) return;
  auto &tile = model.tiles[w.index];
  auto d = tile.domain();
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
  // tile_controls::tap_route decides; tests/test_tile_controls.cpp keeps every older tap choice routed as before.
  auto tap = tile_controls::tap_route(tile, code == LV_EVENT_LONG_PRESSED);
  switch (tap.route) {
    case tile_controls::TapRoute::ACTION:
      // On / off shows the new stand at once, as Home Assistant's switch does; other actions have nothing to show yet.
      if (tap.service == d + ".toggle" && (d == "light" || d == "switch" || d == "input_boolean" || d == "fan" || d == "automation" || d == "remote"))
        tile.optimistic(tile.state != "on");
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
      active_index = w.index;
      show_detail(w.index);
      return;
    case tile_controls::TapRoute::OVERLAY:
      active_index = w.index;
      tile.begin(esphome::millis(), true);
      if (detail) detail(tile);
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
// and each real set refreshes the style and invalidates the object (about 0.3 ms on the Guition).
inline void set_color(lv_obj_t *obj, lv_style_prop_t prop, lv_color_t color, lv_style_selector_t selector) {
  lv_style_value_t current;
  if (lv_obj_get_local_style_prop(obj, prop, &current, selector) == LV_STYLE_RES_FOUND && lv_color_eq(current.color, color)) return;
  lv_style_value_t value{}; value.color = color;
  lv_obj_set_local_style_prop(obj, prop, value, selector);
}
inline void set_number(lv_obj_t *obj, lv_style_prop_t prop, int32_t number, lv_style_selector_t selector) {
  lv_style_value_t current;
  if (lv_obj_get_local_style_prop(obj, prop, &current, selector) == LV_STYLE_RES_FOUND && current.num == number) return;
  lv_style_value_t value{}; value.num = number;
  lv_obj_set_local_style_prop(obj, prop, value, selector);
}
// Card sliders follow Home Assistant's control slider (a 42 px track there): corners of 12 and
// 8 px on track and fill, a white handle 4 px wide and half the height, an eighth of the height in
// from the end of the fill, and a fill that never gets shorter than a third of the height. LVGL
// centres the knob on the end of the fill, so the knob is narrowed and moved back; the range starts
// below zero, so at 0 the fill is still that short stub holding the handle. Values below zero never
// leave the slider (see slider_event). Small strips keep round ends: the corners would not show.
inline int slider_handle_width(int height) { return height > 20 ? 4 : 2; }
inline int slider_stub(int height) { return std::max(height / 3, 2 * std::max(1, height / 8) + slider_handle_width(height)); }
inline void slider_handle(lv_obj_t *slider, int width, int height) {
  int handle = slider_handle_width(height), inset = std::max(1, height / 8) + handle / 2, half = height >> 1;
  // Track and fill share one radius: a fill rounded less than its track makes LVGL draw the fill into
  // a buffer of its own size on every redraw (15 KB on a CYD card), which the CYD's heap can't spare.
  int corner = height > 20 ? height * 12 / 42 : LV_RADIUS_CIRCLE;
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_MAIN);
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_INDICATOR);
  set_number(slider, LV_STYLE_PAD_LEFT, inset + handle / 2 - half, LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_RIGHT, handle / 2 - inset - (height - half), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_TOP, -(height / 4), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_BOTTOM, -(height / 4), LV_PART_KNOB);
  int stub = slider_stub(height), below = width > stub ? 1000 * stub / (width - stub) : 0;
  if (lv_slider_get_min_value(slider) != -below || lv_slider_get_max_value(slider) != 1000) lv_slider_set_range(slider, -below, 1000);
}
// An off light or fan shows only the grey track, as in Home Assistant: no fill, no handle.
inline void slider_bar(lv_obj_t *slider, bool shown) {
  set_number(slider, LV_STYLE_BG_OPA, shown ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_INDICATOR);
  set_number(slider, LV_STYLE_BG_OPA, shown ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_KNOB);
}
inline bool slider_bar_shown(const Tile &t, bool on) { auto d = t.domain(); return on || (d != "light" && d != "fan"); }
inline void set_hidden(lv_obj_t *obj, bool hidden) { if (hidden) lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN); else lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN); }
// A card's size as its styles request it. LVGL's own getters only follow after a layout pass, and
// that pass walks every object on the screen, so the cards are laid out without asking for one.
// The card's size as the grid laid it out (place_page updates the layout before a card is drawn).
inline int tile_width(const Widgets &w) { return lv_obj_get_width(w.tile); }
inline int tile_height(const Widgets &w) { return lv_obj_get_height(w.tile); }
inline int content_width(const Widgets &w) {
  return tile_width(w) - lv_obj_get_style_space_left(w.tile, LV_PART_MAIN) - lv_obj_get_style_space_right(w.tile, LV_PART_MAIN);
}
// The name of a plain card. The compact look draws it in small letters for a cell of two columns (a CYD lying down);
// a card whose name has more room than that (one column standing up, a double-width card, a 4-inch glass) gets the
// L step of the text set a little larger (WIDE_NAME_FONT in looks/compact.yaml; a bold 14 of its own before firmware
// 0.17.0), so the words are not small in a wide empty card (GitHub #50). The standard look keeps one size. The room is the name's own, after a panel or a graph took
// theirs.
inline const lv_font_t *wide_name_font = nullptr;
inline int wide_name_room() { return ui::mm(30); }
inline const lv_font_t *name_font(const Widgets &w, int room) {
  return !ui::large() && wide_name_font && room >= wide_name_room() ? wide_name_font : w.title_font;
}
inline int content_height(const Widgets &w) {
  return tile_height(w) - lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) - lv_obj_get_style_space_bottom(w.tile, LV_PART_MAIN);
}
// What one cell of the grid has to draw in. A control that fills its room on a double-width card takes exactly
// this: such a card is two cells, its controls claim the second one, and their edges then stand where the cards
// in the rows above and below have theirs. The look's own numbers (panel_metrics) are what one cell of a Guition
// and a CYD measures, give or take two pixels; a board whose grid divides its glass differently (three columns
// on a 4.3 inch) gets its own cell instead of that number.
inline int cell_content_width(const Widgets &w) {
  const int edges = tile_width(w) - content_width(w);
  if (tile_grid && grid.wide_span() > 1) {
    const int gap = lv_obj_get_style_pad_column(tile_grid, LV_PART_MAIN);
    const int cell = (lv_obj_get_content_width(tile_grid) - (int) (grid.columns - 1) * gap) / (int) grid.columns;
    if (cell - edges > 0) return cell - edges;
  }
  return std::max(1, w.base_width > edges ? w.base_width - edges : content_width(w) / 2);
}
// The head of a card: the icon circle at the left, the name and the state as two lines beside it. One rule for
// every card that draws it (a single or double-width card, the top of a full-page card), whatever grid the board
// has: the row is centred on the room it got, never on a place typed per board, so two rows or three on the same
// glass both stand in the middle. The circle keeps the board's icon size (TILE_ICON_SIZE) while it leaves `edge`
// to the tile's border, standing a little into the padding for that (three rows on 800x480: a 69 px circle in
// 65 px of content); a cell shorter than that shrinks it. The two lines keep the look's own spacing (the
// Guition's 6 px between the name and the state) instead of packing when the rows are short.
struct HeadRow { int circle=0, circle_y=0, text_x=0, title_y=0, value_y=0; };
inline int head_gap(bool large) { return ui::px(large ? 6 : 1); }
inline int head_text_x(int circle, bool large) { return circle + ui::px(large ? 10 : 12); }
// `value_h` is 0 for a card with no second line (firmware 0.2.90+): the name is then the whole head and stands in
// the middle of the room on its own, instead of sitting high with an empty line under it. One rule, so it holds on
// every board and on every cell a grid gives a card.
inline HeadRow head_row(const Widgets &w, bool large, int circle, int room, int title_h, int value_h) {
  HeadRow h;
  const int pad = lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) + lv_obj_get_style_space_bottom(w.tile, LV_PART_MAIN);
  h.circle = std::max(1, std::min(circle, room + pad - 2 * ui::px(large ? 6 : 3)));
  h.circle_y = (room - h.circle) / 2;
  h.title_y = std::max(0, (room - (title_h + (value_h ? head_gap(large) + value_h : 0))) / 2);
  h.value_y = h.title_y + title_h + head_gap(large);
  h.text_x = head_text_x(h.circle, large);
  return h;
}
// A card's strip is thin (8 px on a CYD card), so the whole card belongs to it: a finger that lands above the strip
// still drags it. A press that never moves taps or holds the card instead (slider_event), so nothing is lost.
inline int slider_zone(const Widgets &w, int strip) {
  return std::max(8, (int) lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) + content_height(w) - strip);
}
// A card under a finger (firmware 0.2.95+). The press darkens the card the moment the finger lands (theme::pressed on
// the PRESSED state, in place of the theme's 45 % veil); letting go fades the card back over PRESS_FADE_MS. The fade is
// LVGL's own style transition on the card's background: no object, no layer, one small animation that redraws the
// card alone. LVGL takes the transition of the most specific state that matches the new one, so the PRESSED state
// carries one of 0 ms and the press stays instant; the fade lives on one shared style every card gets in bind().
constexpr uint32_t PRESS_FADE_MS = 200;
struct PressStyles { lv_style_t fade; lv_style_transition_dsc_t release, at_once; };
inline PressStyles &press_styles() {
  static PressStyles s;
  static bool ready = false;
  if (!ready) {
    static const lv_style_prop_t props[] = {LV_STYLE_BG_COLOR, LV_STYLE_BG_OPA, LV_STYLE_PROP_INV};
    lv_style_transition_dsc_init(&s.release, props, lv_anim_path_ease_out, PRESS_FADE_MS, 0, nullptr);
    lv_style_transition_dsc_init(&s.at_once, props, lv_anim_path_linear, 0, 0, nullptr);
    lv_style_init(&s.fade);
    lv_style_set_transition(&s.fade, &s.release);
    ready = true;
  }
  return s;
}
inline void press_feedback(lv_obj_t *tile) {
  auto &s = press_styles();
  lv_obj_add_style(tile, &s.fade, 0);
  lv_obj_set_style_transition(tile, &s.at_once, LV_STATE_PRESSED);
  lv_obj_set_style_bg_opa(tile, LV_OPA_COVER, LV_STATE_PRESSED);
}
// The card's own colour. A new colour ends a fade that may still run from the card this slot showed before (a page
// switch within PRESS_FADE_MS), so the new card never wears the old one's shade: adding a style again is LVGL's way
// to end the transitions of an object.
inline void press_ground(lv_obj_t *tile, lv_color_t colour) {
  lv_style_value_t was;
  if (lv_obj_get_local_style_prop(tile, LV_STYLE_BG_COLOR, &was, 0) == LV_STYLE_RES_FOUND && !lv_color_eq(was.color, colour))
    lv_obj_add_style(tile, &press_styles().fade, 0);
  set_color(tile, LV_STYLE_BG_COLOR, colour);
}
// The circle of a thermostat card with controls switches it on and off (firmware 0.3.3), as the icon of a Home
// Assistant tile does: off is no mode on the card's mode bar. Turning on restores the mode Home Assistant remembers,
// as the card's power key does. render_slot makes the circle clickable for such a card only.
inline void climate_circle_event(lv_event_t *e){
  const unsigned slot=(uintptr_t)lv_event_get_user_data(e);
  if(slot>=widgets.size())return;
  auto &w=widgets[slot];
  if(!enabled||!fresh()||w.index>=model.count)return;
  auto &t=model.tiles[w.index];const uint32_t now=esphome::millis();
  if(!tile_controls::thermostat(t)||!t.available()||t.waiting(now))return;
  if(!allowed(now,2000+slot,"power "+std::to_string(slot)))return;
  const bool off=tile_controls::climate_off(t);
  t.begin(now);
  if(!off)t.state="off";
  action(t.domain()+(off?".turn_on":".turn_off"),t.entity);
  refresh_tile(w.index);
}
// A card into its set at `index`. Its callbacks name the index and `widgets[index]`: they only fire while the card is on
// the glass, and then that is where it is (the set exchange in keep_page never moves a card to another index).
// `like`: a card of the board's own set whose measurements this one takes over (make_card), instead of laying the grid
// out to measure it; that pass walks every card on the screen, kept ones too, and made a new set cost up to a second.
inline void bind_card(Widgets &into, size_t index, lv_obj_t *tile, lv_obj_t *title, lv_obj_t *value, lv_obj_t *circle, lv_obj_t *icon,
                      const Widgets *like = nullptr) {
  // A card is measured in the cell it will live in (firmware 0.2.92+). Everything below reads the size the card
  // has here, so it is put in the first cell of the grid first: one cell is exactly what a plain single card
  // gets, whatever the board and whichever way its glass hangs. place_page moves it to its real cell later.
  if (!like) {
    if (tile_grid) {
      lv_obj_set_grid_cell(tile, LV_GRID_ALIGN_STRETCH, 0, 1, LV_GRID_ALIGN_STRETCH, 0, 1);
      lv_obj_update_layout(tile_grid);
    }
    lv_obj_update_layout(tile);
  }
  const int width = like ? like->base_width : lv_obj_get_width(tile), height = like ? like->base_height : lv_obj_get_height(tile);
  // Compact cards need room for two text lines and a separate dimmer track.
  if(height<=80){lv_obj_set_style_pad_top(tile,4,0);lv_obj_set_style_pad_bottom(tile,4,0);}
  lv_obj_set_style_border_width(tile,1,0);
  press_feedback(tile);
  if (!like) lv_obj_update_layout(tile);
  into = {tile, title, value, circle, icon, index};
  lv_obj_add_event_cb(circle,climate_circle_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)index);
  lv_obj_set_style_opa(circle,LV_OPA_60,LV_STATE_PRESSED);
  auto &w=into; w.value_font=lv_obj_get_style_text_font(value,LV_PART_MAIN);
  w.base_width=width;w.base_height=height;w.base_circle=like ? like->base_circle : lv_obj_get_width(circle);
  w.title_font=lv_obj_get_style_text_font(title,LV_PART_MAIN);
  w.icon_font=lv_obj_get_style_text_font(icon,LV_PART_MAIN);
  w.unit=lv_label_create(tile);lv_obj_set_style_text_font(w.unit,w.value_font,0);lv_obj_remove_flag(w.unit,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  lv_label_set_long_mode(w.unit,LV_LABEL_LONG_DOT);
  // Fixed one-line boxes prevent wrapped names from overlapping the state on both boards.
  lv_obj_set_height(title,lv_font_get_line_height(lv_obj_get_style_text_font(title,LV_PART_MAIN)));
  lv_obj_set_height(value,lv_font_get_line_height(w.value_font));
  lv_label_set_long_mode(title,LV_LABEL_LONG_DOT);lv_label_set_long_mode(value,LV_LABEL_LONG_DOT);
  w.progress=lv_obj_create(tile);lv_obj_remove_style_all(w.progress);lv_obj_set_size(w.progress,0,3);lv_obj_align(w.progress,LV_ALIGN_BOTTOM_LEFT,0,0);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
  w.slider=lv_slider_create(tile);lv_obj_set_size(w.slider,width-24,ui::px(ui::large()?28:10));lv_obj_align(w.slider,LV_ALIGN_BOTTOM_MID,0,0);lv_slider_set_range(w.slider,0,1000);
  // A short white bar inside the fill as handle, like the control sliders (invisible before 0.2.20).
  int strip=ui::px(ui::large()?28:10);
  lv_obj_add_style(w.slider,theme::style(theme::Paint::knob),LV_PART_KNOB);lv_obj_set_style_bg_opa(w.slider,LV_OPA_COVER,LV_PART_KNOB);
  slider_handle(w.slider,width-24,strip);
  lv_obj_set_style_border_width(w.slider,0,LV_PART_KNOB);lv_obj_set_style_shadow_width(w.slider,0,LV_PART_KNOB);
  // Track and fill follow the card's palette (render_slot), which is drawn before the slider shows.
  lv_obj_set_style_radius(w.slider,2,LV_PART_KNOB);
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
  lv_obj_remove_flag(w.slider,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(w.slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)index);
  lv_obj_add_event_cb(tile, event, LV_EVENT_SHORT_CLICKED, &widgets[index]);
  lv_obj_add_event_cb(tile, event, LV_EVENT_LONG_PRESSED, &widgets[index]);
}
// The board's own cards (packages/cells/<n>.yaml, bound at boot).
inline void bind(size_t index, lv_obj_t *tile, lv_obj_t *title, lv_obj_t *value, lv_obj_t *circle, lv_obj_t *icon) {
  bind_card(widgets[index], index, tile, title, value, circle, icon);
}
// A card like the ones packages/cells/<n>.yaml brings (tools/generate_cells.py writes those): the same four styles, the
// same parts and flags, the board's icon size and icon font as its first card has them. Hidden until a page shows it.
inline void make_card(Widgets &into, size_t index, const Widgets &like) {
  auto *tile = lv_obj_create(tile_grid);
  lv_obj_add_flag(tile, LV_OBJ_FLAG_HIDDEN);  // out of the grid's layout from the start
  lv_obj_add_style(tile, card_look.tile, 0);
  lv_obj_set_size(tile, 1, 1);
  auto *circle = lv_obj_create(tile);
  lv_obj_add_style(circle, card_look.circle, 0);
  lv_obj_set_size(circle, like.base_circle, like.base_circle);
  auto *icon = lv_label_create(circle);
  lv_obj_set_style_text_font(icon, like.icon_font, 0);
  lv_obj_align(icon, LV_ALIGN_CENTER, 0, 0);
  auto *title = lv_label_create(tile);
  lv_obj_add_style(title, card_look.title, 0);
  auto *value = lv_label_create(tile);
  lv_obj_add_style(value, card_look.value, 0);
  for (auto *o : {tile, circle}) { lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE); lv_obj_set_scrollbar_mode(o, LV_SCROLLBAR_MODE_OFF); }
  for (auto *o : {circle, icon, title, value}) lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  bind_card(into, index, tile, title, value, circle, icon, &like);
}
inline void label(lv_obj_t *obj, const std::string &text) {
  if (text != lv_label_get_text(obj)) lv_label_set_text(obj, text.c_str());
}
// The name in the top bar. Its own copy is the truth about what it says: the dots LVGL writes into the label are
// not a change of name, so they neither set the text again nor pass for the name when the bar measures it.
inline void name_label(lv_obj_t *obj, const std::string &text) {
  if (!obj || (header_named && header_name == text)) return;
  header_named = true;
  header_name = text;
  lv_label_set_text(obj, text.c_str());
}
// lv_obj_set_style_* always invalidates the object; these only do so on a real change,
// which keeps a one-second clock tick or a busy spinner from redrawing whole cards.
inline void set_font(lv_obj_t *obj, const lv_font_t *value) { if (lv_obj_get_style_text_font(obj, LV_PART_MAIN) != value) lv_obj_set_style_text_font(obj, value, 0); }
inline void set_text_align(lv_obj_t *obj, lv_text_align_t value) { if (lv_obj_get_style_text_align(obj, LV_PART_MAIN) != value) lv_obj_set_style_text_align(obj, value, 0); }
inline void pad_vertical(lv_obj_t *obj, int value) {
  if (lv_obj_get_style_pad_top(obj, LV_PART_MAIN) != value) lv_obj_set_style_pad_top(obj, value, 0);
  if (lv_obj_get_style_pad_bottom(obj, LV_PART_MAIN) != value) lv_obj_set_style_pad_bottom(obj, value, 0);
}
inline void set_line_width(lv_obj_t *obj, int value) { if (lv_obj_get_style_line_width(obj, LV_PART_MAIN) != value) lv_obj_set_style_line_width(obj, value, 0); }
// Custom cards draw into a transparent `extra` container; parts are rebuilt only
// when a slot changes mode, so paging keeps RAM use flat on the CYD.
// A slot whose next card draws no custom part only hides them: paging back to the clock or
// graph in that slot reuses its objects instead of creating them again (tens of ms per card).
inline void hide_extra(Widgets &w) {
  if(!w.extra)return;
  if(!lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN))lv_obj_add_flag(w.extra,LV_OBJ_FLAG_HIDDEN);
  w.fill_points=nullptr;w.fill_count=0;
}
inline void end_extra(Widgets &w) {
  if(!w.extra)return;
  hide_extra(w);
  if(!w.extra_mode.empty()){
    if(captured_slider&&std::find(w.parts.begin(),w.parts.end(),captured_slider)!=w.parts.end()){captured_slider=nullptr;slider_changed=false;}
    lv_obj_clean(w.extra);w.parts.fill(nullptr);w.extra_mode.clear();delete[] w.points;w.points=nullptr;}
}
// Two triangles per segment between the polyline and its baseline. No canvas
// buffer is needed, so the CYD can afford it as well.
// The Widgets whose extra layer this is, wherever keep_page moved it: the slots and the kept sets.
inline Widgets *extra_owner(lv_obj_t *extra) {
  for (auto &w : widgets) if (w.extra == extra) return &w;
  for (auto *set : kept_sets) if (set) for (auto &w : *set) if (w.extra == extra) return &w;
  return nullptr;
}
inline void extra_draw(lv_event_t *e) {
  // The pointer given at creation names the slot the layer was made in; after keep_page swapped Widgets it may be
  // another card's, so the layer's own card is looked up when they differ.
  auto *given=static_cast<Widgets *>(lv_event_get_user_data(e));
  auto *extra=static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *owner=given && given->extra==extra?given:extra_owner(extra);
  if(!owner)return;
  auto &w=*owner;
  if(!w.fill_points || w.fill_count<2 || !w.fill_opa)return;
  auto *layer=lv_event_get_layer(e);lv_area_t area;lv_obj_get_coords(w.extra,&area);
  lv_draw_triangle_dsc_t dsc;lv_draw_triangle_dsc_init(&dsc);dsc.color=w.fill_color;dsc.opa=w.fill_opa;
  const lv_value_precise_t ox=area.x1+w.fill_x, oy=area.y1+w.fill_y, base=oy+w.fill_base;
  for(unsigned i=0;i+1<w.fill_count;++i){
    const auto &a=w.fill_points[i],&b=w.fill_points[i+1];
    dsc.p[0]={ox+a.x,oy+a.y};dsc.p[1]={ox+b.x,oy+b.y};dsc.p[2]={ox+b.x,base};lv_draw_triangle(layer,&dsc);
    dsc.p[1]=dsc.p[2];dsc.p[2]={ox+a.x,base};lv_draw_triangle(layer,&dsc);
  }
}
inline void begin_extra(Widgets &w,const char *mode,int width,int height) {
  if(!w.extra){
    w.extra=lv_obj_create(w.tile);lv_obj_remove_style_all(w.extra);lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(w.extra,extra_draw,LV_EVENT_DRAW_MAIN,&w);
    // LVGL draws the children of an object whose overflow is visible only as far as its own extra draw size: a clock
    // face asks for the card's padding, so its dial and a date's descenders show up to the card's edge.
    // It reads the object itself and its card, never a Widgets pointer: kept pages swap whole Widgets between a slot
    // and a kept set (keep_page), so a pointer given here would name another card, or a fresh one without parts, and
    // LVGL asks for this size in any layout pass, also of a hidden kept page (firmware 0.3.6 crash-looped on it).
    lv_obj_add_event_cb(w.extra,[](lv_event_t *e){
      auto *extra=static_cast<lv_obj_t *>(lv_event_get_current_target(e));
      auto *tile=extra?lv_obj_get_parent(extra):nullptr;
      if(tile && lv_obj_has_flag(extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE))
        lv_event_set_ext_draw_size(e,std::max({lv_obj_get_style_space_left(tile,LV_PART_MAIN),lv_obj_get_style_space_top(tile,LV_PART_MAIN),
                                               lv_obj_get_style_space_right(tile,LV_PART_MAIN),lv_obj_get_style_space_bottom(tile,LV_PART_MAIN)}));
    },LV_EVENT_REFR_EXT_DRAW_SIZE,nullptr);
  }
  if(w.extra_mode!=mode || w.extra_full!=w.full){end_extra(w);w.extra_mode=mode;w.extra_full=w.full;w.points=(w.extra_mode=="tall"||w.extra_mode=="cover_tilt")?nullptr:new lv_point_precise_t[POINT_BUFFER];w.cached_active=-1;}
  w.fill_points=nullptr;w.fill_count=0;
  // Parts that were hidden kept the colours of the card they last showed.
  if(lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN)){w.cached_active=-1;lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_HIDDEN);}
  lv_obj_set_pos(w.extra,0,0);lv_obj_set_size(w.extra,width,height);
  // A clock face may use the card's padding (firmware 0.3.6+): a dial or flip blocks reach nearer the card's edge
  // on a one-row card, and a big font's letters below the line (a date's y and p) are not cut off.
  const bool face=w.extra_mode=="calm"||w.extra_mode=="flip"||w.extra_mode=="digital"||w.extra_mode=="bedside";
  if(face!=lv_obj_has_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE)){
    if(face)lv_obj_add_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE);else lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  }
  // The padding can change with the card (a short cell keeps less of it), so the draw size is asked for every time.
  lv_obj_refresh_ext_draw_size(w.extra);
}
// How far a clock face may reach past the content area into the card's padding: up to a small margin from the edge.
inline int face_reach(const Widgets &w,const Tile &t){
  if(w.full || t.row_span()>1)return 0;
  // The smallest side: a short cell keeps less padding above and below than beside (and a dial reaches up and down).
  const int pad=std::min({lv_obj_get_style_space_left(w.tile,LV_PART_MAIN),lv_obj_get_style_space_top(w.tile,LV_PART_MAIN),
                          lv_obj_get_style_space_bottom(w.tile,LV_PART_MAIN)});
  return std::max(0,pad-ui::px(6));
}
// Catmull-Rom curve through the samples: the trend reads smoothly without extra data.
inline unsigned smooth(const lv_point_precise_t *in,unsigned n,lv_point_precise_t *out,unsigned capacity,int width,int height) {
  if(n<2 || capacity<2){for(unsigned i=0;i<n && i<capacity;++i)out[i]=in[i];return n<capacity?n:capacity;}
  const unsigned steps=4;unsigned count=0;
  for(unsigned i=0;i+1<n;++i){
    const auto &p0=in[i?i-1:0],&p1=in[i],&p2=in[i+1],&p3=in[i+2<n?i+2:n-1];
    for(unsigned s=0;s<steps && count<capacity-1;++s){
      float t=float(s)/steps,t2=t*t,t3=t2*t;
      float x=0.5f*(2*p1.x+(-p0.x+p2.x)*t+(2*p0.x-5*p1.x+4*p2.x-p3.x)*t2+(-p0.x+3*p1.x-3*p2.x+p3.x)*t3);
      float y=0.5f*(2*p1.y+(-p0.y+p2.y)*t+(2*p0.y-5*p1.y+4*p2.y-p3.y)*t2+(-p0.y+3*p1.y-3*p2.y+p3.y)*t3);
      out[count++]={(lv_value_precise_t)std::clamp(x,0.0f,float(width-1)),(lv_value_precise_t)std::clamp(y,0.0f,float(height-1))};
    }
  }
  out[count++]=in[n-1];return count;
}
inline lv_obj_t *part_label(Widgets &w,unsigned i,const lv_font_t *font,int x,int y,int width,lv_text_align_t align,const std::string &text) {
  auto *&p=w.parts[i];
  if(!p){p=lv_label_create(w.extra);lv_label_set_long_mode(p,LV_LABEL_LONG_CLIP);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);}
  set_font(p,font);set_text_align(p,align);
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),lv_font_get_line_height(font));label(p,text);return p;
}
inline lv_obj_t *part_dot(Widgets &w,unsigned i,int x,int y,int size) {
  auto *&p=w.parts[i];
  if(!p){p=lv_obj_create(w.extra);lv_obj_remove_style_all(p);lv_obj_set_style_bg_opa(p,LV_OPA_COVER,0);lv_obj_set_style_radius(p,LV_RADIUS_CIRCLE,0);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,size,size);return p;
}
// Points are relative to (x,y): the line object then covers only its own rectangle.
inline lv_obj_t *part_line(Widgets &w,unsigned i,lv_point_precise_t *points,unsigned count,int width,int x=0,int y=0) {
  auto *&p=w.parts[i];
  if(!p){p=lv_line_create(w.extra);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_line_rounded(p,true,0);}
  set_line_width(p,width);lv_line_set_points(p,points,count);lv_obj_set_pos(p,x,y);return p;
}
// The big digits of the clock card: "07:12" on 24 hours, "7:12" on 12 (the clock font has no letters for AM and PM).
inline std::string time_text(esphome::ESPTime now) {
  if (!now.is_valid()) return "--:--";
  if (screen_settings::current.clock_24h) return hhmm(now);
  char b[8]; snprintf(b, sizeof(b), "%d:%02d", now.hour % 12 ? now.hour % 12 : 12, now.minute);
  return b;
}
// Digital: big time over the date. Analog: index strokes (numerals at 12/3/6/9 on
// large cards) with hour and minute hands. A single card adds a calendar block
// beside the dial (weekday, big day number, short month); a wide card adds the
// digital time and the date instead. Parts: 0-11 marks, 12-13 hands, 14 centre,
// 15-17 text, 18 the second hand (points 28-29), shown while the screen is awake.
inline void second_hand(Widgets &w,const esphome::ESPTime &now) {
  float a=(now.is_valid()?now.second:0)*3.14159265f/30;
  w.points[28]={(lv_value_precise_t)(w.hand_cx-w.hand_r*0.2f*sinf(a)),(lv_value_precise_t)(w.hand_cy+w.hand_r*0.2f*cosf(a))};
  w.points[29]={(lv_value_precise_t)(w.hand_cx+w.hand_r*0.92f*sinf(a)),(lv_value_precise_t)(w.hand_cy-w.hand_r*0.92f*cosf(a))};
  auto *p=part_line(w,18,w.points+28,2,w.hand_width);
  set_hidden(p,!(awake() && now.is_valid()));
}
// ---- Clock faces beside the digital clock and the classic dial (firmware 0.3.6+) ----
// "dial": a calm face, a filled disc with four strokes and eight dots and no numerals, so it reads at any size.
// "flip": hours and minutes on two blocks, like a flip clock. Both take the card's shape: wide cards put the time
// or the blocks at the left with the time and date beside them, tall cards stack, a full page centres.
// Digits are placed by the box their glyphs fill, not by the font's line box: a line box carries room above and
// below the digits, and centring that left the digits of the old wide clock visibly low.
inline void digit_box(const lv_font_t *font,int &top,int &height){
  lv_font_glyph_dsc_t g;
  if(font && lv_font_get_glyph_dsc(font,&g,'0',0) && g.box_h>0){
    height=g.box_h;top=lv_font_get_line_height(font)-font->base_line-g.box_h-g.ofs_y;return;
  }
  const int line=font?lv_font_get_line_height(font):10;height=line*7/10;top=(line-height)/2;
}
// AM or PM in the screen's language ("p. m." in Spanish) when it shows 12 hours, else nothing.
inline std::string am_pm(const esphome::ESPTime &now){
  if(screen_settings::current.clock_24h || !now.is_valid())return "";
  return tr(now.hour<12?txt::time_am:txt::time_pm);
}
inline lv_obj_t *part_rect(Widgets &w,unsigned i,int x,int y,int width,int height,int radius){
  auto *&p=w.parts[i];
  if(!p){p=lv_obj_create(w.extra);lv_obj_remove_style_all(p);lv_obj_set_style_bg_opa(p,LV_OPA_COVER,0);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_style_radius(p,radius,0);lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),std::max(1,height));return p;
}
// A label whose digits start at `digits_top`: its box is moved up by the room the font keeps above them.
inline lv_obj_t *digit_label(Widgets &w,unsigned i,const lv_font_t *font,int x,int digits_top,int width,lv_text_align_t align,const std::string &text){
  int top,h;digit_box(font,top,h);
  return part_label(w,i,font,x,digits_top-top,width,align,text);
}
// The time column beside or under a dial: the time (with AM/PM after it) over the date. The largest font that fits
// the room, with the date if it fits too; the long date first, then the short one.
struct ClockText{const lv_font_t *font=nullptr;std::string date;int width=0,height=0,digits=0,gap=0;};
inline ClockText face_text(Widgets &w,const esphome::ESPTime &now,bool large,int room_w,int room_h,bool want_date=true){
  const lv_font_t *fonts[]={clock_font,watch_value_font,watch_font,w.value_font};
  const lv_font_t *small=w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  int small_top,small_h;digit_box(small,small_top,small_h);
  const std::string dates[]={date_text(now),fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now))};
  const int line_gap=ui::px(large?9:5);
  // A date under a small time looks lost: it only comes with a time at least twice its own height.
  for(int with=want_date?1:0;with>=0;--with)for(auto *f:fonts){
    if(!f)continue;
    int top,dh;digit_box(f,top,dh);
    if(with && dh<2*small_h)continue;
    const int tw=text_width(time,f)+(ampm.empty()?0:ui::px(4)+text_width(ampm,small));
    const int h=dh+(with?line_gap+small_h:0);
    // The date's letters below the line (y, p) must fit too.
    if(h+(with?small->base_line:0)>room_h || tw>room_w)continue;
    if(!with)return ClockText{f,"",tw,h,dh,line_gap};
    for(const auto &date:dates){const int dw=text_width(date,small);if(dw<=room_w)return ClockText{f,date,std::max(tw,dw),h,dh,line_gap};}
  }
  return ClockText{};
}
// Place a ClockText with its left edge (align left) or its middle (centred) at x, its top at y.
inline void place_face_text(Widgets &w,const ClockText &c,const esphome::ESPTime &now,int x,int y,int room_w,bool centred){
  const lv_font_t *small=w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  const int tw=text_width(time,c.font),aw=ampm.empty()?0:ui::px(4)+text_width(ampm,small);
  const int tx=centred?x+(room_w-(tw+aw))/2:x;
  digit_label(w,15,c.font,tx,y,tw+2,LV_TEXT_ALIGN_LEFT,time);
  set_hidden(w.parts[15],false);
  int stop,sh;digit_box(small,stop,sh);
  // AM/PM sits on the time's baseline.
  digit_label(w,17,small,tx+tw+ui::px(4),y+c.digits-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  set_hidden(w.parts[17],ampm.empty());
  const int dw=c.date.empty()?1:text_width(c.date,small)+2;
  digit_label(w,16,small,centred?x+(room_w-dw)/2:x,y+c.digits+c.gap,dw,LV_TEXT_ALIGN_LEFT,c.date);
  set_hidden(w.parts[16],c.date.empty());
}
inline void hide_face_text(Widgets &w){for(unsigned q=15;q<18;++q)if(w.parts[q])set_hidden(w.parts[q],true);}
inline void render_calm_dial(Widgets &w,const Tile &t,bool large,int width,int height){
  begin_extra(w,"calm",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const int gap=ui::px(large?16:8);
  // The disc goes first, so everything else is drawn over it.
  part_dot(w,19,0,0,1);
  // Where the dial goes: beside the time on a card wider than tall (reaching into the padding, so a one-row card
  // gets a dial nearly as tall as the card), above the time on a tall card or a page, alone when neither leaves room.
  const int side=std::min(width,height);
  int dial=side,cx=width/2,cy=height/2,tx=0,ty=0,room=0;ClockText text;bool centred=false;
  const bool upright=w.full || height>width*9/10;
  if(!upright){
    const int reach=face_reach(w,t),big=height+2*reach;
    text=face_text(w,now,large,width-(big-reach)-gap,height+reach);
    if(text.font){
      dial=big;cx=dial/2-reach;tx=dial-reach+gap;ty=(height-text.height)/2;room=width-tx;
      // What is left beside the time is shared: the dial and the text move in together as one group.
      const int spare=std::min(std::max(0,room-text.width)/2,gap);cx+=spare;tx+=2*spare;room-=2*spare;
    }
  }
  if(!text.font){
    text=face_text(w,now,large,width,height-side*60/100-gap);
    if(text.font){
      // Under the dial the date's letters below the line count too, or they touch the card's edge.
      const int below=text.date.empty()?0:w.value_font->base_line;
      dial=std::min(width,height-text.height-below-gap);
      const int top=(height-dial-gap-text.height-below)/2;cx=width/2;cy=top+dial/2;ty=top+dial+gap;tx=0;room=width;centred=true;
    }
  }
  if(!text.font){dial=side;cx=width/2;cy=height/2;hide_face_text(w);}
  else place_face_text(w,text,now,tx,ty,room,centred);
  const float R=dial/2.0f-1;
  lv_obj_set_pos(w.parts[19],cx-int(R),cy-int(R));lv_obj_set_size(w.parts[19],int(R)*2,int(R)*2);
  // Four strokes at 12, 3, 6 and 9 and a dot at every other hour, all inside the disc.
  const float inset=std::max(2.0f,R*0.09f),stroke=std::max(3.0f,R*0.22f);
  const int stroke_w=std::max(2,int(R*0.08f+0.5f)),dot=std::max(2,int(R*0.075f+0.5f));
  for(int i=0;i<12;++i){
    const float a=i*3.14159265f/6;
    if(i%3==0){
      if(w.parts[i] && !lv_obj_check_type(w.parts[i],&lv_line_class)){lv_obj_delete(w.parts[i]);w.parts[i]=nullptr;}
      auto *p=w.points+4+2*i;
      p[0]={(lv_value_precise_t)(cx+(R-inset)*sinf(a)),(lv_value_precise_t)(cy-(R-inset)*cosf(a))};
      p[1]={(lv_value_precise_t)(cx+(R-inset-stroke)*sinf(a)),(lv_value_precise_t)(cy-(R-inset-stroke)*cosf(a))};
      part_line(w,i,p,2,stroke_w);
    }else{
      const float r=R-inset-stroke*0.3f;
      part_dot(w,i,int(cx+r*sinf(a)+0.5f)-dot/2,int(cy-r*cosf(a)+0.5f)-dot/2,dot);
    }
  }
  float hour=((now.is_valid()?now.hour%12:0)+(now.is_valid()?now.minute:0)/60.0f)*3.14159265f/6, minute=(now.is_valid()?now.minute:0)*3.14159265f/30;
  w.points[0]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[1]={(lv_value_precise_t)(cx+R*0.5f*sinf(hour)),(lv_value_precise_t)(cy-R*0.5f*cosf(hour))};
  w.points[2]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[3]={(lv_value_precise_t)(cx+R*0.78f*sinf(minute)),(lv_value_precise_t)(cy-R*0.78f*cosf(minute))};
  part_line(w,12,w.points,2,std::max(3,int(R*0.16f+0.5f)));part_line(w,13,w.points+2,2,std::max(2,int(R*0.11f+0.5f)));
  const int center=std::max(5,int(R*0.26f+0.5f));part_dot(w,14,cx-center/2,cy-center/2,center);
  w.hand_cx=cx;w.hand_cy=cy;w.hand_r=int(R*0.9f);w.hand_width=std::max(1,int(R*0.045f+0.5f));
  const bool new_hand=!w.parts[18];
  second_hand(w,now);
  if(new_hand)lv_obj_move_to_index(w.parts[18],lv_obj_get_index(w.parts[14]));
}
// The digit steps, largest first (packages/looks/shared/digits.yaml): the display step, the setpoint's and the clock
// card's. A card takes the largest one that fits (largest_digits) and never brings a size of its own
// (tests/test_font_set.py).
inline std::array<const lv_font_t *,3> digit_steps(){return {display_font,setpoint_font,clock_font};}
// The largest digit step whose digits are at most `height` tall and whose `text` is at most `width` wide; null if none.
inline const lv_font_t *largest_digits(const char *text,int width,int height){
  for(const lv_font_t *f:digit_steps()){
    if(!f)continue;int top,h;digit_box(f,top,h);
    if(h<=height && text_width(text,f)<=width)return f;
  }
  return nullptr;
}
// The bedside clock's digits: its own step where the board has one (a page a fifth larger than the display step), else
// the display step; the 8 px place holder a board without its own step keeps is never drawn.
inline const lv_font_t *bedside_digits(){
  if(bedside_font && (!display_font || lv_font_get_line_height(bedside_font)>lv_font_get_line_height(display_font)))return bedside_font;
  return display_font?display_font:setpoint_font?setpoint_font:clock_font;
}
// A card that only switches (a lamp, a switch, a fan) or only runs (a script, a scene, a button), with no other control
// chosen: two rows tall, one column or two, it is one big key (firmware 0.17.0+), as the same card over a whole page is.
inline bool big_key(const Tile &t){
  const auto d=t.domain();
  return (d=="light"||d=="switch"||d=="input_boolean"||d=="fan"||d=="script"||d=="scene"||d=="button"||d=="input_button") && t.inline_control!="slider" &&
         (t.controls.empty()||t.controls=="toggle"||t.controls=="run"||t.controls=="none"||t.controls=="auto");
}
inline void render_flip(Widgets &w,const Tile &t,bool large,int width,int height){
  begin_extra(w,"flip",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  char hh[4]="--",mm[4]="--";
  if(now.is_valid()){
    if(screen_settings::current.clock_24h)snprintf(hh,sizeof(hh),"%02d",now.hour);else snprintf(hh,sizeof(hh),"%d",now.hour%12?now.hour%12:12);
    snprintf(mm,sizeof(mm),"%02d",now.minute);
  }
  const std::string ampm=am_pm(now);
  const lv_font_t *small=w.value_font,*bold=w.title_font?w.title_font:w.value_font;
  const lv_font_t *fonts[]={setpoint_font,clock_font,watch_value_font,watch_font,w.value_font};
  int stop,sh;digit_box(small,stop,sh);
  const int aw=ampm.empty()?0:text_width(ampm,small);
  // A card as wide as two columns and two rows or more, or a whole page (firmware 0.17.0+): the two blocks share its
  // width, and one line under them carries the day at the left and AM or PM at the right. The digits are the board's
  // display step (looks/shared/digits.yaml), else the largest digit step that fits a block.
  if(w.full || (w.wide && t.row_span()>=2)){
    // The blocks keep room above them and under the day's line, so on a low card (a compact look) they never touch its
    // edge: at least 6 px, a twentieth of the card on a taller one.
    const int line_gap=ui::px(large?12:6),gb=std::max(ui::px(6),width/36),bw=(width-gb)/2,air=std::max(ui::px(6),height/20);
    const int bh=std::min(height-2*air-line_gap-sh,bw*92/100);
    const lv_font_t *font=largest_digits("88",bw*88/100,bh*72/100);int dh=0;
    if(font){int top;digit_box(font,top,dh);}
    for(unsigned q=0;q<7;++q)if(w.parts[q])set_hidden(w.parts[q],!font);
    if(!font){hide_face_text(w);return;}
    const int radius=std::max(ui::px(4),bh/12),seam=std::max(1,bh/60);
    const int by=(height-(bh+line_gap+sh))/2;
    for(int b=0;b<2;++b){
      const int x=b*(bw+gb);
      part_rect(w,b,x,by,bw,bh,radius);
      digit_label(w,2+b,font,x,by+(bh-dh)/2,bw,LV_TEXT_ALIGN_CENTER,b?mm:hh);
      part_rect(w,4+b,x,by+bh/2-seam/2,bw,seam,0);
    }
    const std::string day=weekday_text(now)+" "+fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now));
    digit_label(w,16,small,0,by+bh+line_gap,std::max(1,width-aw-ui::px(8)),LV_TEXT_ALIGN_LEFT,day);set_hidden(w.parts[16],false);
    digit_label(w,6,small,width-aw-2,by+bh+line_gap,aw+2,LV_TEXT_ALIGN_RIGHT,ampm);set_hidden(w.parts[6],ampm.empty());
    if(w.parts[15])set_hidden(w.parts[15],true);if(w.parts[17])set_hidden(w.parts[17],true);
    return;
  }
  // The blocks: the largest digits whose blocks fit. A block is as tall as the room allows (a one-row card: the
  // card, into its padding; a page: a bit over half of it) and a little wider than tall. A card that is not a page
  // takes the two blocks side by side or one over the other, whichever gives the bigger blocks.
  struct Blocks{const lv_font_t *font=nullptr;int bh=0,bw=0,gb=0;};
  const int reach=face_reach(w,t);
  auto fit=[&](bool stack)->Blocks{
    const int want_h=stack?height:w.full?height*55/100:height+2*reach,grow=stack?0:reach;
    for(auto *f:fonts){
      if(!f)continue;
      int top,dh;digit_box(f,top,dh);
      int h=std::min(want_h,dh*100/62);
      const int g=std::max(ui::px(3),h/12);
      if(stack)h=std::min(h,(height-g)/2);
      if(dh>h*72/100)continue;
      const int bwid=std::max(text_width("88",f)+dh*6/10,h*108/100);
      const int need=(stack?bwid:2*bwid+g)+(aw?ui::px(6)+aw:0)-2*grow;
      if(need>width)continue;
      return Blocks{f,h,bwid,g};
    }
    return Blocks{};
  };
  Blocks row=fit(false),column=w.full?Blocks{}:fit(true);
  const bool stacked=column.font && column.bh>row.bh*11/10;
  const Blocks &chosen=stacked?column:row;
  const lv_font_t *font=chosen.font;const int bh=chosen.bh,bw=chosen.bw,gb=chosen.gb;
  const int reach_used=stacked?0:reach;
  for(unsigned q=0;q<7;++q)if(w.parts[q])set_hidden(w.parts[q],!font);
  if(!font){hide_face_text(w);return;}
  int dtop,dh;digit_box(font,dtop,dh);
  const int radius=std::max(ui::px(4),bh/9),seam=std::max(1,bh/45);
  // The date: weekday over the day and month beside wide blocks, one line under blocks on a page or stacked.
  const std::string weekday=weekday_text(now),date=fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now));
  int bx=0,by=0,group_w=(stacked?bw:2*bw+gb)+(aw?ui::px(6)+aw:0),group_h=stacked?2*bh+gb:bh;
  const int gap=ui::px(large?16:8);
  bool side=false,under=false;
  int bold_top,bold_h;digit_box(bold,bold_top,bold_h);
  const int col_w=std::max(text_width(weekday,bold),text_width(date,small)),col_h=bold_h+ui::px(large?9:5)+sh;
  if(!stacked && !w.full && group_w-reach_used+gap+col_w<=width && col_h<=height)side=true;
  else if((stacked||w.full) && group_h+gap+sh<=height && text_width(stacked?date:weekday+" "+date,small)<=width)under=true;
  if(side){
    const int spare=std::max(0,width+reach_used-(group_w+gap+col_w))/2;
    bx=std::min(spare,gap)-reach_used;by=(height-bh)/2;
    const int cx=bx+group_w+gap+std::min(spare,gap),cy=(height-col_h)/2;
    digit_label(w,15,bold,cx,cy,col_w+2,LV_TEXT_ALIGN_LEFT,weekday);
    digit_label(w,16,small,cx,cy+bold_h+ui::px(large?9:5),col_w+2,LV_TEXT_ALIGN_LEFT,date);
    set_hidden(w.parts[15],false);set_hidden(w.parts[16],false);
  }else{
    const int total=group_h+(under?gap+sh:0);
    bx=(width-group_w)/2;by=(height-total)/2;
    if(under){
      const std::string line=stacked?date:weekday+" "+date;
      digit_label(w,16,small,0,by+group_h+gap,width,LV_TEXT_ALIGN_CENTER,line);
      set_hidden(w.parts[16],false);
    }else if(w.parts[16])set_hidden(w.parts[16],true);
    if(w.parts[15])set_hidden(w.parts[15],true);
  }
  // Blocks 0 (hours) and 1 (minutes), their digits 2 and 3, the seams 4 and 5, AM/PM 6.
  for(int b=0;b<2;++b){
    const int x=stacked?bx:bx+b*(bw+gb),y=stacked?by+b*(bh+gb):by;
    part_rect(w,b,x,y,bw,bh,radius);
    digit_label(w,2+b,font,x,y+(bh-dh)/2,bw,LV_TEXT_ALIGN_CENTER,b?mm:hh);
    part_rect(w,4+b,x,y+bh/2-seam/2,bw,seam,0);
  }
  // AM/PM beside the minutes on the digits' baseline; beside the hours when the blocks are stacked.
  if(stacked)digit_label(w,6,small,bx+bw+ui::px(6),by+(bh-dh)/2+dh-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  else digit_label(w,6,small,bx+2*bw+gb+ui::px(6),by+(bh-dh)/2+dh-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  set_hidden(w.parts[6],ampm.empty());
  if(w.parts[17])set_hidden(w.parts[17],true);
}
// The colours of the two faces above, from the card's palette (called where the other cards get theirs).
inline void paint_face(Widgets &w,lv_color_t ink,lv_color_t muted,lv_color_t accent){
  const bool flip=w.extra_mode=="flip";
  const lv_color_t block=theme::color(theme::TRACK);
  const lv_color_t card=lv_obj_get_style_bg_opa(w.tile,LV_PART_MAIN)==LV_OPA_TRANSP?theme::color(theme::PAGE):lv_obj_get_style_bg_color(w.tile,LV_PART_MAIN);
  for(unsigned i=0;i<w.parts.size();++i){
    auto *p=w.parts[i];if(!p)continue;
    if(lv_obj_check_type(p,&lv_label_class)){set_color(p,LV_STYLE_TEXT_COLOR,(flip?(i==6||i==16):(i==16||i==17))?muted:ink);continue;}
    if(flip){set_color(p,LV_STYLE_BG_COLOR,i==4||i==5?card:block);continue;}
    // The calm dial is the card turned round: a disc in the ink's colour, its strokes and hour hand in the card's
    // (dark on a light card, light on a dark one), so it stands out instead of fading into the card.
    if(lv_obj_check_type(p,&lv_line_class))set_color(p,LV_STYLE_LINE_COLOR,i==18?lv_color_hex(theme::foreground(theme::ha::ALARM)):i==13?accent:card);
    else set_color(p,LV_STYLE_BG_COLOR,i==19?ink:i==14?accent:muted);
  }
}
// ---- The bedside clock (firmware 0.8.0+) ----
// A clock over the whole page: the time as large as the page allows, and up to three round keys, each a tile of its
// own (runtime_model.h, Tile::parent). The keys stand in a row under the time; on a card too low for that, in a
// column beside it; on a card too narrow, under the hours stacked over the minutes. The room above the time, between
// the time and the keys and below the keys is the same, and the middle stops growing at 14 mm, so on a large glass
// the group stays together in the middle. The board's digits (FONT_BEDSIDE_SIZE) are the largest one of these fits
// in both orientations, so the same font serves the glass lying down and standing up.
// The keys a bedside clock's page has cards for: the cells its clock covers but its own (place_page).
static_assert(CELLS_MAX > BEDSIDE_KEYS, "a bedside clock's keys take the cards of the cells its page leaves free");
inline unsigned bedside_key_room(){return std::min<unsigned>(BEDSIDE_KEYS,std::min<unsigned>(widgets.size(),grid.slots())-1);}
struct BedsideLayout {
  enum Mode : uint8_t { ROW, COLUMN, STACK } mode = ROW;
  int digits_y = 0, digits_x = 0, digits_w = 0, digit_h = 0, line_gap = 0;  // content coordinates of the card
  int key = 0; unsigned keys = 0; bool names = false, fits = true; int name_h = 0, name_gap = 0;
  std::array<int, BEDSIDE_KEYS> key_x{}, key_y{};  // each key's top-left corner, content coordinates
  std::array<int, BEDSIDE_KEYS> name_x{}, name_y{}, name_w{};
};
// `pad`: the card's own padding, so the room above the time counts from the card's edge as it looks.
inline BedsideLayout bedside_layout(int w,int h,int pad,const std::vector<std::string> &names_in){
  BedsideLayout l;
  const lv_font_t *font=bedside_digits();
  const lv_font_t *small=small_font?small_font:font;
  int top;digit_box(font,top,l.digit_h);
  l.line_gap=l.digit_h/6;
  l.keys=std::min<unsigned>(names_in.size(),BEDSIDE_KEYS);
  // Names under the keys in the standard look; the compact look (a CYD) keeps the keys alone, its smallest letters
  // would be under the size the owner reads in the dark.
  l.names=l.keys && ui::large() && std::any_of(names_in.begin(),names_in.begin()+l.keys,[](const std::string &n){return !n.empty();});
  l.name_h=l.names?lv_font_get_line_height(small):0;l.name_gap=l.names?ui::px(8):0;
  int name_w=0;if(l.names)for(unsigned i=0;i<l.keys;++i)name_w=std::max(name_w,text_width(names_in[i],small));
  // A long name ends in dots rather than push the keys apart: a third of the card, about five letters and a half of
  // the name's size (the looks size FONT_BEDSIDE_SIZE with the same limit).
  name_w=std::min({name_w,w/3,(int)lv_font_get_line_height(small)*47/10});
  const int card_h=h+2*pad,least=std::max(ui::px(8),card_h*7/100),touch=ui::touch_min();
  const int time_w=text_width("00:00",font),pair_w=text_width("00",font);
  auto key_size=[&](int room){return std::max(touch,std::min<int>(ui::mm(12),room*28/100));};
  // What each arrangement needs; the first that fits is taken.
  int d=key_size(h);
  int kg=std::max({ui::px(16),d/2,l.names?name_w-d+ui::px(12):0});
  if(l.keys && (int)l.keys*d+((int)l.keys-1)*kg>w)d=std::max(touch,(w-((int)l.keys-1)*kg)/(int)l.keys);
  const int band=l.keys?d+l.name_gap+l.name_h:0;
  const bool row=time_w<=w && l.digit_h+band+(l.keys?3:2)*least<=card_h;
  const int vg=ui::px(12),col_d=std::max(touch,std::min(d,(h-2*vg)/3));
  const int col_w=col_d+(l.names?ui::px(12)+name_w:0);
  const bool column=!row && l.keys && time_w<=w-col_w-ui::px(28) && (int)l.keys*col_d+((int)l.keys-1)*vg<=h;
  const bool stack=!row && !column && pair_w<=w && 2*l.digit_h+l.line_gap+band+(l.keys?3:2)*least<=card_h;
  l.mode=row?BedsideLayout::ROW:column?BedsideLayout::COLUMN:stack?BedsideLayout::STACK:BedsideLayout::ROW;
  // The board's digits (bedside_digits, looks/shared/digits.yaml) are sized for one of the three to fit; the self test fails a
  // board where none does, instead of the time running into its keys.
  l.fits=row||column||stack;
  if(l.mode==BedsideLayout::COLUMN){
    l.key=col_d;
    const int area=w-col_w-ui::px(28);
    l.digits_x=0;l.digits_w=area;l.digits_y=(h-l.digit_h)/2;
    const int y0=(h-((int)l.keys*col_d+((int)l.keys-1)*vg))/2,x=w-col_w;
    for(unsigned i=0;i<l.keys;++i){
      l.key_x[i]=x;l.key_y[i]=y0+i*(col_d+vg);
      l.name_x[i]=x+col_d+ui::px(12);l.name_y[i]=l.key_y[i]+(col_d-l.name_h)/2;l.name_w[i]=std::max(1,w-l.name_x[i]);
    }
    return l;
  }
  l.key=d;
  const int tall=l.mode==BedsideLayout::STACK?2*l.digit_h+l.line_gap:l.digit_h;
  // Equal room above, between and below, measured from the card's edge; the middle stops at 14 mm.
  const int free=card_h-tall-band;
  const int mid=l.keys?std::min(free/3,ui::mm(14)):0,edge=(free-mid)/2;
  l.digits_x=0;l.digits_w=w;l.digits_y=edge-pad;
  const int keys_y=l.digits_y+tall+mid,x0=(w-((int)l.keys*d+((int)l.keys-1)*kg))/2;
  for(unsigned i=0;i<l.keys;++i){
    l.key_x[i]=x0+i*(d+kg);l.key_y[i]=keys_y;
    // A name may be wider than its key, never wider than the card: the outer ones stay inside it.
    const int nw=std::min(w,d+kg-ui::px(4));
    l.name_x[i]=std::clamp(l.key_x[i]+d/2-nw/2,0,w-nw);l.name_y[i]=keys_y+d+l.name_gap;l.name_w[i]=nw;
  }
  return l;
}
// The names of a bedside clock's keys, in their order (the tiles that name `index` as their clock).
inline std::vector<std::string> bedside_names(size_t index){
  std::vector<std::string> names;
  for(unsigned k=0;k<bedside_key_room();++k)for(size_t i=0;i<model.count;++i){
    const auto &t=model.tiles[i];
    // A key whose name is hidden (overlay "none", firmware 0.17.0+) keeps its place with an empty name.
    if(t.is_key() && (size_t)t.parent==index && t.key==k){names.push_back(!t.overlay?std::string():t.name.empty()?t.entity:t.name);break;}
  }
  return names;
}
// Parts: 0 the time (the hours when stacked), 1 the minutes when stacked, 2 AM/PM, 3-5 the keys' names.
inline void render_bedside(Widgets &w,const Tile &t,int width,int height){
  begin_extra(w,"bedside",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const int pad=lv_obj_get_style_space_top(w.tile,LV_PART_MAIN);
  const auto names=bedside_names(w.index);
  const auto l=bedside_layout(width,height,pad,names);
  const lv_font_t *font=bedside_digits(),*small=small_font?small_font:w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  const auto ink=theme::color(theme::BEDSIDE),muted=theme::color(theme::MUTED);
  if(l.mode==BedsideLayout::STACK){
    const size_t colon=time.find(':');
    digit_label(w,0,font,l.digits_x,l.digits_y,l.digits_w,LV_TEXT_ALIGN_CENTER,time.substr(0,colon));
    digit_label(w,1,font,l.digits_x,l.digits_y+l.digit_h+l.line_gap,l.digits_w,LV_TEXT_ALIGN_CENTER,colon==std::string::npos?"":time.substr(colon+1));
    set_hidden(w.parts[1],false);
  }else{
    digit_label(w,0,font,l.digits_x,l.digits_y,l.digits_w,LV_TEXT_ALIGN_CENTER,time);
    if(w.parts[1])set_hidden(w.parts[1],true);
  }
  set_color(w.parts[0],LV_STYLE_TEXT_COLOR,ink);if(w.parts[1])set_color(w.parts[1],LV_STYLE_TEXT_COLOR,ink);
  // AM or PM under the end of the time when the screen shows 12 hours (firmware 0.17.0+): beside it, "10:08" already
  // fills the width the digits were sized for and the letters ran off the glass (GitHub #93).
  if(!ampm.empty()){
    const int tw=text_width(l.mode==BedsideLayout::STACK?time.substr(time.find(':')+1):time,font);
    const int last=l.mode==BedsideLayout::STACK?l.digits_y+2*l.digit_h+l.line_gap:l.digits_y+l.digit_h;
    const int aw=text_width(ampm,small)+2,end=l.digits_x+(l.digits_w+tw)/2;
    auto *p=digit_label(w,2,small,end-aw,last+ui::px(10),aw,LV_TEXT_ALIGN_LEFT,ampm);
    set_color(p,LV_STYLE_TEXT_COLOR,muted);set_hidden(p,false);
  }else if(w.parts[2])set_hidden(w.parts[2],true);
  for(unsigned i=0;i<BEDSIDE_KEYS;++i){
    if(i<l.keys && l.names && !names[i].empty()){
      auto *p=part_label(w,3+i,small,l.name_x[i],l.name_y[i],l.name_w[i],l.mode==BedsideLayout::COLUMN?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,names[i]);
      lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);set_color(p,LV_STYLE_TEXT_COLOR,muted);set_hidden(p,false);
    }else if(w.parts[3+i])set_hidden(w.parts[3+i],true);
  }
}
inline void render_clock(Widgets &w,const Tile &t,bool large,int width,int height) {
  if(t.display=="dial"||t.display=="flip"){
    // A part made on this render has no colour yet: the palette pass paints it (it runs after this, on a change).
    auto made=[&w]{return std::count_if(w.parts.begin(),w.parts.end(),[](lv_obj_t *p){return p!=nullptr;});};
    const auto before=w.extra_mode==(t.display=="dial"?"calm":"flip")?made():-1;
    if(t.display=="dial")render_calm_dial(w,t,large,width,height);else render_flip(w,t,large,width,height);
    if(made()!=before)w.cached_active=-1;
    return;
  }
  bool analog=t.display=="analog";
  begin_extra(w,analog?(w.wide?"analog":"calendar"):"digital",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const lv_font_t *big=clock_font?clock_font:watch_value_font?watch_value_font:w.value_font;
  // The card's own name font, not the name label's: a card that showed a centred name before (a tall on/off card)
  // left its label in that card's font, and a card reused for another page kept it (firmware 0.3.2).
  const lv_font_t *small=w.title_font;
  // The date line only appears when both lines fit the card height.
  bool with_date=lv_font_get_line_height(big)+2+lv_font_get_line_height(small)<=height;
  int text_h=lv_font_get_line_height(big)+(with_date?2+lv_font_get_line_height(small):0);
  if(!analog){
    // The largest time that fits, with the date under it when that fits too, centred on the digits themselves
    // (firmware 0.3.6+: a 61 px time in a 63 px card no longer hangs 8 px out of it).
    // A one-row card lends the time and date part of its padding, as it does a dial.
    const int reach=face_reach(w,t);
    const auto text=face_text(w,now,large,width,height+reach);
    if(!text.font){hide_face_text(w);return;}
    place_face_text(w,text,now,0,(height-text.height)/2,width,true);
    return;
  }
  // The dial keeps the same size with or without a card behind it.
  // A full-page card centres its dial; the digital time and date beside a wide dial stay off it.
  int dial=std::min(height,width);
  // A single card keeps the dial of the profile's card when it grows without the page bar (firmware 0.2.69+), so the
  // calendar block beside it keeps its room; the dial stays in the card's middle.
  if(!w.full && !w.wide)dial=std::min(dial,w.base_height-(tile_height(w)-height));
  // A single card whose width has no room for the date beside the dial centres the dial instead.
  bool date_fits=true;
  if(!w.full && w.wide){
    // Multi-row cards can be taller than they are wide. Keep the dial centred
    // when its usual time/date column has no room beside it.
    const int room=width-dial-ui::px(large?16:8);
    const int need=std::max(text_width(time_text(now),big),with_date?text_width(date_text(now),small):0);
    date_fits=room>=need;
  }
  if(!w.full && !w.wide){
    int room=width-dial-(ui::px(large?10:6)),need=0;lv_point_t sz;
    if(large){
      lv_text_get_size(&sz,weekday_text(now).c_str(),w.value_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);need=sz.x;
      std::string day_probe=now.is_valid()?std::to_string(now.day_of_month):"--";
      lv_point_t d,m;lv_text_get_size(&d,day_probe.c_str(),big,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);lv_text_get_size(&m,month_short(now).c_str(),small,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
      need=std::max<int>(need,d.x+6+m.x);
    }else{
      const lv_font_t *font=watch_value_font?watch_value_font:w.value_font;
      std::string day_probe=now.is_valid()?std::to_string(now.day_of_month):"--";
      lv_text_get_size(&sz,fill(fill(txt::date_day_month,"day",day_probe),"month",month_short(now)).c_str(),font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);need=sz.x;
    }
    date_fits=room>=need;
  }
  int cx=((w.full||!date_fits)?(width-dial)/2:0)+dial/2,cy=height/2,outer=dial/2-1,radius=dial/2-(ui::px(large?4:2));
  // Numerals replace the four cardinal strokes on a dial with room for them (firmware 0.35.0): the 12 and the 3 stand a
  // ring's radius apart either way, so a ring shorter than a numeral's box (a 4-inch with four rows) puts them on top
  // of each other, and the dial keeps its strokes instead.
  const int numeral_box=lv_font_get_line_height(w.value_font)+4,numeral_ring=outer-11;
  const bool numerals=large && numeral_ring>=numeral_box+ui::px(2);
  for(int i=0;i<12;++i){
    float a=i*3.14159265f/6;bool cardinal=i%3==0;
    // A part kept from a dial of the other size is the other kind (a numeral is a label, a stroke a line).
    // Its successor is made below without a colour; the palette pass paints it (cached_active, as the dial does).
    if(cardinal && w.parts[i] && lv_obj_check_type(w.parts[i],&lv_label_class)!=numerals){lv_obj_delete(w.parts[i]);w.parts[i]=nullptr;w.cached_active=-1;}
    if(cardinal && numerals){
      part_label(w,i,w.value_font,cx+std::lround(numeral_ring*sinf(a))-numeral_box/2,cy-std::lround(numeral_ring*cosf(a))-numeral_box/2,
                 numeral_box,LV_TEXT_ALIGN_CENTER,i==0?"12":std::to_string(i));
      continue;
    }
    int length=cardinal?(ui::px(large?9:5)):(ui::px(large?5:3));
    auto *p=w.points+4+2*i;
    p[0]={(lv_value_precise_t)(cx+outer*sinf(a)),(lv_value_precise_t)(cy-outer*cosf(a))};
    p[1]={(lv_value_precise_t)(cx+(outer-length)*sinf(a)),(lv_value_precise_t)(cy-(outer-length)*cosf(a))};
    part_line(w,i,p,2,cardinal?(ui::px(large?3:2)):(ui::px(large?2:1)));
  }
  float hour=((now.is_valid()?now.hour%12:0)+(now.is_valid()?now.minute:0)/60.0f)*3.14159265f/6, minute=(now.is_valid()?now.minute:0)*3.14159265f/30;
  w.points[0]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[1]={(lv_value_precise_t)(cx+radius*0.52f*sinf(hour)),(lv_value_precise_t)(cy-radius*0.52f*cosf(hour))};
  w.points[2]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[3]={(lv_value_precise_t)(cx+radius*0.82f*sinf(minute)),(lv_value_precise_t)(cy-radius*0.82f*cosf(minute))};
  part_line(w,12,w.points,2,ui::px(large?5:3));part_line(w,13,w.points+2,2,ui::px(large?3:2));
  int center=ui::px(large?8:4);part_dot(w,14,cx-center/2,cy-center/2,center);
  // A thin red second hand with a short tail, under the centre dot; tick() moves it every second.
  w.hand_cx=cx;w.hand_cy=cy;w.hand_r=radius;w.hand_width=ui::px(large?2:1);
  bool new_hand=!w.parts[18];
  second_hand(w,now);
  if(new_hand)lv_obj_move_to_index(w.parts[18],lv_obj_get_index(w.parts[14]));
  std::string day=now.is_valid()?std::to_string(now.day_of_month):"--";
  if(w.full){
    part_label(w,15,big,0,0,1,LV_TEXT_ALIGN_CENTER,"");
    part_label(w,16,small,0,0,1,LV_TEXT_ALIGN_CENTER,"");
    return;
  }
  // What does not fit is left out of the card: the date labels hide, nothing else moves.
  for(unsigned q=15;q<18;++q)if(w.parts[q])set_hidden(w.parts[q],!date_fits);
  if(!date_fits)return;
  if(w.wide){
    int x=dial+(ui::px(large?16:8)),y=std::max(0,(height-text_h)/2);
    part_label(w,15,big,x,y,width-x,LV_TEXT_ALIGN_CENTER,time_text(now));
    part_label(w,16,small,x,with_date?y+lv_font_get_line_height(big)+2:y,width-x,LV_TEXT_ALIGN_CENTER,with_date?date_text(now):"");
    return;
  }
  int x=dial+(ui::px(large?10:6)),room=std::max(1,width-x);
  if(!large){
    // Compact cards: "13 sep" in the large-value font beside the dial, in the language's order (screen.date.day_month).
    const lv_font_t *font=watch_value_font?watch_value_font:w.value_font;
    part_label(w,16,font,x,std::max(0,int(height-lv_font_get_line_height(font))/2),room,LV_TEXT_ALIGN_CENTER,
               fill(fill(txt::date_day_month,"day",day),"month",month_short(now)));
    return;
  }
  // Calendar block: weekday over a big day number with the short month beside it. It has to fit the card's
  // height: on a board with more rows than its size table was drawn for, the weekday and a big number are
  // together taller than the cell and the number was cut off at the bottom. The weekday goes first, then the
  // number takes the smaller font; the day and the month never go, they are what a calendar is for.
  const lv_font_t *day_font=big;
  int week_h=lv_font_get_line_height(w.value_font);
  bool with_weekday=week_h+lv_font_get_line_height(day_font)<=height;
  if(!with_weekday && lv_font_get_line_height(day_font)>height)day_font=w.value_font;
  if(!with_weekday)week_h=0;
  if(w.parts[15])set_hidden(w.parts[15],!with_weekday);
  int top=std::max(0,int(height-week_h-lv_font_get_line_height(day_font))/2);
  if(with_weekday)part_label(w,15,w.value_font,x,top,room,LV_TEXT_ALIGN_CENTER,weekday_text(now));
  std::string month=month_short(now);
  lv_point_t day_size,month_size;
  lv_text_get_size(&day_size,day.c_str(),day_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
  lv_text_get_size(&month_size,month.c_str(),small,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
  int gap=6,sx=x+std::max(0,int(room-(day_size.x+gap+month_size.x))/2),day_y=top+week_h;
  part_label(w,16,day_font,sx,day_y,std::min(room,(int)day_size.x+2),LV_TEXT_ALIGN_LEFT,day);
  // Both baselines line up: LVGL measures base_line from the bottom of the line box.
  int month_y=day_y+(day_font->line_height-day_font->base_line)-(small->line_height-small->base_line);
  part_label(w,17,small,sx+day_size.x+gap,std::max(0,month_y),std::max(1,int(x+room-(sx+day_size.x+gap))),LV_TEXT_ALIGN_LEFT,month);
}
// ---- The weather tile's forecast (firmware 0.3.3): forecast_tile.h decides where, this draws ----
// Today among the forecast's days: the day's short name as the manager wrote it (screen.date.weekdays_min) against
// the screen's own clock in the same words. -1 while the clock is not set, or when the two speak another language.
inline int forecast_today(const Tile &t){
  const auto now=now_time?now_time():esphome::ESPTime{};
  if(!now.is_valid()||now.day_of_week<1||now.day_of_week>7)return -1;
  const std::string name=tr(txt::date_weekdays_min+now.day_of_week-1);
  const auto &days=t.extra().forecast;
  for(size_t k=0;k<days.size()&&k<(size_t)forecast_tile::DAYS;++k)if(days[k].day==name)return (int)k;
  return -1;
}
// A rounded bar with a second one inside it: the week's range as the track, one day's range as the fill.
inline lv_obj_t *part_bar(Widgets &w,unsigned i,int x,int y,int width,int height){
  auto *&p=w.parts[i];
  if(!p){
    p=lv_obj_create(w.extra);
    for(auto *o:{p,lv_obj_create(p)}){
      lv_obj_remove_style_all(o);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);lv_obj_set_style_radius(o,LV_RADIUS_CIRCLE,0);
      lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
    }
    lv_obj_set_style_bg_grad_dir(lv_obj_get_child(p,0),LV_GRAD_DIR_HOR,0);
  }
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),std::max(1,height));return p;
}
// The weather now (the condition in its circle, the temperature, the word) and the coming days, in the form the
// card's cell holds: days as columns beside it on a card of one row, as rows under it with the week's range as bars
// on a taller one. Every colour is set here on every render, because each day has its own: the palette pass that
// colours the other custom cards leaves these parts alone.
inline void render_forecast(Widgets &w,const Tile &t,bool large,int width,int height) {
  namespace ft=forecast_tile;
  const auto &x=t.extra();const auto &days=x.forecast;
  const lv_font_t *bold=w.title_font?w.title_font:lv_obj_get_style_text_font(w.title,LV_PART_MAIN),*text=w.value_font;
  const lv_font_t *mini=mini_icon_font?mini_icon_font:w.icon_font;
  const lv_font_t *faces[ft::FACES]={setpoint_font,watch_value_font,watch_font};
  char now_text[16];
  if(std::isfinite(t.current))snprintf(now_text,sizeof(now_text),"%.0f°",t.current);else snprintf(now_text,sizeof(now_text),"--");
  ft::Metrics m;m.large=large;
  for(int f=0;f<ft::FACES;++f){
    const bool usable=faces[f]&&face_covers(faces[f],now_text);
    m.face_h[f]=usable?lv_font_get_line_height(faces[f]):0;m.face_w[f]=usable?text_width(now_text,faces[f])+2:0;
  }
  m.text_h=lv_font_get_line_height(text);m.bold_h=lv_font_get_line_height(bold);m.icon_h=lv_font_get_line_height(mini);
  m.circle=w.base_circle>0?w.base_circle:ui::px(large?54:36);
  const std::string cond=t.available()?weather_text(t.state):tr(txt::ha_unavailable);
  std::string line=cond;
  if(std::isfinite(x.feels))line+=" · "+fill(txt::weather_feels_like,"n",(int)std::lround(x.feels));
  m.cond_w=text_width(cond,text)+2;m.line_w=text_width(line,text)+2;
  const int n=(int)std::min<size_t>(days.size(),ft::DAYS),space=ui::px(large?4:2);
  float lowest=INFINITY,highest=-INFINITY;
  for(int k=0;k<n;++k){
    const auto &f=days[k];
    const int hw=text_width(degrees(f.high),bold),lw=text_width(degrees(f.low),text);
    m.temps_w=std::max(m.temps_w,hw+space+lw);m.high_w=std::max(m.high_w,hw+2);m.low_w=std::max(m.low_w,lw+2);
    m.name_w=std::max(m.name_w,text_width(f.day,text)+2);m.row_name_w=std::max(m.row_name_w,text_width(f.day,bold)+2);
    if(std::isfinite(f.rain)&&f.rain>=30){m.rain=true;m.rain_w=std::max(m.rain_w,text_width(screen_text::percent((int)std::lround(f.rain)),text)+2);}
    if(std::isfinite(f.low))lowest=std::min(lowest,f.low);
    if(std::isfinite(f.high))highest=std::max(highest,f.high);
  }
  const bool tall=t.row_span()>1||w.full;
  const auto l=ft::layout(m,width,height,n,forecast_today(t),tall);
  const bool rows=l.form==ft::Form::rows;
  begin_extra(w,rows?"forecast_rows":"forecast",width,height);
  for(auto *p:w.parts)if(p)lv_obj_add_flag(p,LV_OBJ_FLAG_HIDDEN);
  auto show=[](lv_obj_t *p){lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);return p;};
  auto paint=[](lv_obj_t *p,uint32_t color){set_color(p,LV_STYLE_TEXT_COLOR,lv_color_hex(color));};
  auto words=[&](unsigned i,const lv_font_t *font,ft::Rect r,lv_text_align_t align,const std::string &s,uint32_t color){
    auto *p=show(part_label(w,i,font,r.x,r.y,r.w,align,s));
    if(lv_label_get_long_mode(p)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);
    paint(p,color);return p;
  };
  const uint32_t ink=theme::hex(theme::INK),muted=theme::hex(theme::MUTED),rain=theme::foreground(theme::ha::RAIN);
  // The weather now. The circle is the look's, in the condition's colour, the icon in it as on every other card.
  const uint32_t sky=t.available()?weather_color_raw(t.state):theme::STATE_OFF;
  if(!l.circle.empty()){
    auto *disc=show(part_dot(w,0,l.circle.x,l.circle.y,l.circle.w));
    set_color(disc,LV_STYLE_BG_COLOR,lv_color_hex(t.available()?theme::tint(sky,38):theme::hex(theme::TRACK)));
    const lv_font_t *glyph=l.circle.w>=m.circle||!mini_icon_font?w.icon_font:mini_icon_font;
    const int gh=lv_font_get_line_height(glyph);
    paint(show(part_label(w,1,glyph,l.circle.x,l.circle.y+(l.circle.h-gh)/2,l.circle.w,LV_TEXT_ALIGN_CENTER,t.available()?weather_icon(t.state):"\U000F0595")),
          t.available()?theme::icon(sky):theme::hex(theme::OFF));
  }
  if(l.face>=0){
    words(2,faces[l.face],l.temp,LV_TEXT_ALIGN_LEFT,now_text,ink);
    if(!l.line.empty())words(3,text,l.line,LV_TEXT_ALIGN_LEFT,l.long_line?line:cond,muted);
  }
  // The high in the title font and the low beside it in the value font, on one baseline.
  const int low_drop=(bold->line_height-bold->base_line)-(text->line_height-text->base_line);
  if(rows){
    const float span=highest>lowest?highest-lowest:1.0f;
    const bool fahrenheit=t.unit.find('F')!=std::string::npos;
    auto celsius=[&](float v){return fahrenheit?(v-32)*5/9:v;};
    for(int k=0;k<l.days;++k){
      const auto &f=days[k];const auto &r=l.rows[k];const unsigned base=4+k*6;
      words(base,bold,r.name,LV_TEXT_ALIGN_LEFT,f.day,ink);
      words(base+1,mini,r.icon,LV_TEXT_ALIGN_CENTER,weather_icon(f.condition),weather_accent(f.condition));
      if(!r.rain.empty()&&std::isfinite(f.rain)&&f.rain>=30)words(base+2,text,r.rain,LV_TEXT_ALIGN_LEFT,screen_text::percent((int)std::lround(f.rain)),rain);
      words(base+3,text,{r.low.x,r.low.y,r.low.w,r.low.h},LV_TEXT_ALIGN_RIGHT,degrees(f.low),muted);
      auto *track=show(part_bar(w,base+4,r.bar.x,r.bar.y,r.bar.w,r.bar.h));
      set_color(track,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
      auto *fill_bar=lv_obj_get_child(track,0);
      if(std::isfinite(f.low)&&std::isfinite(f.high)&&std::isfinite(lowest)){
        const int from=(int)std::lround((f.low-lowest)/span*r.bar.w),to=(int)std::lround((f.high-lowest)/span*r.bar.w);
        lv_obj_remove_flag(fill_bar,LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_pos(fill_bar,std::min(from,r.bar.w-r.bar.h),0);lv_obj_set_size(fill_bar,std::max(r.bar.h,to-from),r.bar.h);
        set_color(fill_bar,LV_STYLE_BG_COLOR,lv_color_hex(theme::temperature(celsius(f.low))));
        set_color(fill_bar,LV_STYLE_BG_GRAD_COLOR,lv_color_hex(theme::temperature(celsius(f.high))));
      }else lv_obj_add_flag(fill_bar,LV_OBJ_FLAG_HIDDEN);
      words(base+5,bold,r.high,LV_TEXT_ALIGN_RIGHT,degrees(f.high),ink);
    }
    return;
  }
  // Today's pill, below everything else it stands behind.
  if(!l.pill.empty()){
    auto *pill=show(part_dot(w,4,l.pill.x,l.pill.y,0));
    lv_obj_set_size(pill,l.pill.w,l.pill.h);lv_obj_set_style_radius(pill,std::min(ui::px(large?14:9),l.pill.h/2),0);
    set_color(pill,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
    if(lv_obj_get_index(pill)!=0)lv_obj_move_to_index(pill,0);
  }
  for(int k=0;k<l.days;++k){
    const auto &f=days[k];const auto &c=l.columns[k];const unsigned base=5+k*5;
    const bool beside=!c.name.empty()&&c.name.y>c.icon.y;
    if(!c.name.empty())words(base,text,c.name,beside?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,f.day,muted);
    words(base+1,mini,c.icon,LV_TEXT_ALIGN_CENTER,weather_icon(f.condition),weather_accent(f.condition));
    const std::string hi=degrees(f.high),lo=degrees(f.low);
    const int hw=text_width(hi,bold),lw=text_width(lo,text),x0=c.temps.x+(c.temps.w-(hw+space+lw))/2;
    words(base+2,bold,{x0,c.temps.y,hw+2,c.temps.h},LV_TEXT_ALIGN_LEFT,hi,ink);
    words(base+3,text,{x0+hw+space,c.temps.y+low_drop,lw+2,m.text_h},LV_TEXT_ALIGN_LEFT,lo,muted);
    if(!c.rain.empty()&&std::isfinite(f.rain)&&f.rain>=30)words(base+4,text,c.rain,LV_TEXT_ALIGN_CENTER,screen_text::percent((int)std::lround(f.rain)),rain);
  }
}
// Smoothed trend of the manager's 24 history samples with a soft fill beneath.
inline void render_graph(Widgets &w,const Tile &t,bool large,int x,int y,int width,int height) {
  begin_extra(w,"graph",x+width,y+height);
  float minimum=INFINITY,maximum=-INFINITY;for(float v:t.history)if(std::isfinite(v)){minimum=std::min(minimum,v);maximum=std::max(maximum,v);}
  lv_point_precise_t raw[24];unsigned n=0;int stroke=ui::px(large?3:2),top=stroke;
  for(unsigned i=0;i<t.history.size() && i<24;++i){
    if(!std::isfinite(t.history[i]))continue;
    float level=maximum>minimum?(t.history[i]-minimum)/(maximum-minimum):0.5f;
    raw[n++]={(lv_value_precise_t)(stroke/2+i*(width-stroke-1)/23),(lv_value_precise_t)(height-stroke/2-1-level*(height-stroke-1-top))};
  }
  if(n==1){raw[1]=raw[0];raw[1].x=(lv_value_precise_t)(width-1);n=2;}
  unsigned count=smooth(raw,n,w.points,POINT_BUFFER,width,height);
  part_line(w,0,w.points,count,stroke,x,y);
  w.fill_points=w.points;w.fill_count=count;w.fill_x=x;w.fill_y=y;w.fill_base=height;w.fill_opa=theme::fill_opacity();
}
// Sun path: horizon, an arc from sunrise to sunset and the sun at the current
// position (or below the horizon at night). Wide cards only.
inline void render_sunpath(Widgets &w,const Tile &t,bool large,int width,int height) {
  begin_extra(w,"sunpath",width,height);
  const lv_font_t *title_font=w.title_font;  // the card's own, as in render_clock
  int title_h=lv_font_get_line_height(title_font),text_h=lv_font_get_line_height(w.value_font);
  // The sun's glow is the widest thing on the path: the path keeps half of it from either side of the card, so the sun at
  // rise or set (and clamped there at night) stays inside it (firmware 0.2.104; the standard look's glow is 30 px against
  // a 14 px margin, and stuck out a pixel).
  const int size=ui::px(large?18:10),glow=size+(ui::px(large?12:6));
  int horizon=height-text_h-(ui::px(large?4:2)),top=title_h+(ui::px(large?4:2)),x0=std::max(ui::px(large?14:8),(glow+1)/2),x1=width-x0;
  part_label(w,0,title_font,0,0,width,LV_TEXT_ALIGN_LEFT,t.name.empty()?std::string(tr(txt::sun_name)):t.name);
  part_label(w,1,w.value_font,0,horizon+(ui::px(large?3:1)),width/2,LV_TEXT_ALIGN_LEFT,fill(txt::sun_rise,"time",screen_text::clock_text(t.extra().sunrise,screen_settings::current.clock_24h!=0,true)));
  part_label(w,2,w.value_font,width/2,horizon+(ui::px(large?3:1)),width/2,LV_TEXT_ALIGN_RIGHT,fill(txt::sun_set,"time",screen_text::clock_text(t.extra().sunset,screen_settings::current.clock_24h!=0,true)));
  auto now=now_time?now_time():esphome::ESPTime{};
  int rise=minutes_of(t.extra().sunrise),set=minutes_of(t.extra().sunset),minute=now.is_valid()?now.hour*60+now.minute:-1;
  bool day=t.state=="above_horizon";float fraction=0.5f;
  if(rise>=0 && set>=0 && minute>=0){
    if(day){int span=(set-rise+1440)%1440;if(!span)span=1;fraction=std::clamp(float((minute-rise+1440)%1440)/span,0.0f,1.0f);}
    else{int span=(rise-set+1440)%1440;if(!span)span=1;fraction=std::clamp(float((minute-set+1440)%1440)/span,0.0f,1.0f);}
  }
  const unsigned segments=40;float amplitude=day?float(horizon-top):float(height-text_h-horizon-(ui::px(large?2:1)));
  auto *arc=w.points,*travelled=w.points+segments+1,*line=w.points+2*segments+3;
  for(unsigned i=0;i<=segments;++i){
    float a=3.14159265f*i/segments;
    arc[i]={(lv_value_precise_t)(x0+(x1-x0)*float(i)/segments),(lv_value_precise_t)(day?horizon-sinf(a)*amplitude:horizon+sinf(a)*amplitude)};
  }
  unsigned filled=std::min(segments,unsigned(fraction*segments));
  for(unsigned i=0;i<=filled;++i)travelled[i]=arc[i];
  float sa=3.14159265f*fraction;
  lv_point_precise_t sun={(lv_value_precise_t)(x0+(x1-x0)*fraction),(lv_value_precise_t)(day?horizon-sinf(sa)*amplitude:horizon+sinf(sa)*amplitude)};
  travelled[filled+1]=sun;
  line[0]={(lv_value_precise_t)0,(lv_value_precise_t)horizon};line[1]={(lv_value_precise_t)(width-1),(lv_value_precise_t)horizon};
  const uint32_t path=theme::hex(theme::SUN_PATH), accent=day?theme::ha::ORANGE:theme::foreground(theme::ha::NIGHT_SKY), disc=day?theme::ha::SUNNY:theme::hex(theme::MOON);
  lv_obj_set_style_line_color(part_line(w,3,line,2,2),lv_color_hex(path),0);
  lv_obj_set_style_line_color(part_line(w,4,arc,segments+1,ui::px(large?2:1)),lv_color_hex(path),0);
  lv_obj_set_style_line_color(part_line(w,5,travelled,filled+2,ui::px(large?4:3)),lv_color_hex(accent),0);
  auto *halo=part_dot(w,6,int(sun.x)-glow/2,int(sun.y)-glow/2,glow);lv_obj_set_style_bg_color(halo,lv_color_hex(disc),0);lv_obj_set_style_bg_opa(halo,LV_OPA_30,0);
  lv_obj_set_style_bg_color(part_dot(w,7,int(sun.x)-size/2,int(sun.y)-size/2,size),lv_color_hex(disc),0);
  if(day){w.fill_points=travelled;w.fill_count=filled+2;w.fill_x=0;w.fill_y=0;w.fill_base=horizon;w.fill_color=lv_color_hex(theme::ha::SUNNY);w.fill_opa=theme::fill_opacity();}
}

// ---- Direct controls on wide cards (Home Assistant entity-row style) ----
struct PanelMetrics { int key_w, key_h, radius, gap, pill_w, pill_key, slider_w, slider_h, toggle_w, toggle_h, run_pad, text_gap, ext; };
// A thermostat's mode bar in a panel ("Mode"): a finger is the panel's key, the reach of one hand the look's.
inline climate_tile::Metrics bar_metrics(const PanelMetrics &m,bool large){
  climate_tile::Metrics cm;cm.large=large;cm.touch=m.key_h;cm.gap=m.gap;cm.max_width=ui::control_max_width();
  return cm;
}
inline void draw_mode_bar(Widgets &w,const Tile &t,lv_obj_t *parent,lv_obj_t *&track,lv_obj_t **segments,climate_tile::Rect bar,
                          int room,const climate_tile::Metrics &cm,bool large);
inline PanelMetrics panel_metrics(bool large) {
  return large ? PanelMetrics{ui::px(60), ui::px(46), ui::px(14), ui::px(8), ui::px(196), ui::px(52), ui::px(140), ui::px(44), ui::px(76), ui::px(40), ui::px(22), ui::px(8), ui::px(4)} : PanelMetrics{ui::px(40), ui::px(34), ui::px(9), ui::px(4), ui::px(128), ui::px(36), ui::px(90), ui::px(30), ui::px(48), ui::px(26), ui::px(14), ui::px(6), ui::px(6)};
}
// The same controls at the bottom of a full-page card (firmware 0.2.62+): keys a thumb finds without looking.
inline PanelMetrics panel_metrics_full(bool big) {
  return big ? PanelMetrics{ui::px(120), ui::px(84), ui::px(24), ui::px(16), ui::px(300), ui::px(84), ui::px(400), ui::px(56), ui::px(120), ui::px(60), ui::px(30), ui::px(8), ui::px(4)} : PanelMetrics{ui::px(80), ui::px(44), ui::px(12), ui::px(8), ui::px(200), ui::px(48), ui::px(260), ui::px(34), ui::px(76), ui::px(40), ui::px(18), ui::px(6), ui::px(4)};
}
inline lv_obj_t *panel_obj(lv_obj_t *parent,bool clickable) {
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
  if(clickable)lv_obj_add_flag(o,LV_OBJ_FLAG_CLICKABLE);else lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);
  return o;
}
// Like the custom parts: a card without controls hides the slot's panel and a later card with
// the same control set shows it again.
inline void hide_panel(Widgets &w) {
  if(!w.panel)return;
  if(!lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN))lv_obj_add_flag(w.panel,LV_OBJ_FLAG_HIDDEN);
  w.panel_w=0;
  if(captured_slider && captured_slider==w.control_slider)captured_slider=nullptr;
}
inline void end_panel(Widgets &w) {
  if(!w.panel)return;
  hide_panel(w);
  if(!w.panel_mode.empty()){
    lv_obj_clean(w.panel);w.keys.fill(nullptr);w.key_icons.fill(nullptr);w.key_checked.fill(-1);w.segments.fill(nullptr);
    w.pill=w.pill_value=w.knob=w.control_slider=nullptr;w.knob_on=-1;w.panel_mode.clear();
  }
}
inline void control_event(lv_event_t *e);
// A pill key: rounded, pressed darker, checked in the accent, disabled faded.
inline lv_obj_t *panel_key(Widgets &w,unsigned n,lv_obj_t *parent,const PanelMetrics &m,int width,int height,bool transparent) {
  auto *key=panel_obj(parent,true);lv_obj_set_size(key,width,height);
  lv_obj_set_style_radius(key,transparent?LV_RADIUS_CIRCLE:m.radius,0);
  lv_obj_set_style_bg_opa(key,transparent?LV_OPA_TRANSP:LV_OPA_COVER,0);
  lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_PRESSED);
  lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_CHECKED);
  lv_obj_set_style_opa(key,LV_OPA_40,LV_STATE_DISABLED);
  lv_obj_set_ext_click_area(key,m.ext);
  size_t slot=&w-widgets.data();
  lv_obj_add_event_cb(key,control_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)(slot*16+n));
  w.keys[n]=key;w.key_checked[n]=-1;
  return key;
}
inline lv_obj_t *panel_icon(Widgets &w,unsigned n,const lv_font_t *font) {
  auto *icon=lv_label_create(w.keys[n]);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(icon,font,0);center_icon(icon);w.key_icons[n]=icon;return icon;
}
// The - and + keys of a stepper as round keys inside its grey pill (firmware 0.3.3), with the number between them
// in the largest face that fits: the value is what the stepper is for, the keys only change it. The keys keep a
// finger's reach through their click area, which covers the pill's inset.
// The chip of a thermostat's range between its - and + (firmware 0.19.0), in the room (x, y, cw, ch) the number would
// take: the icon of the end they move, heat or cool, in that mode's colour, and its temperature in the largest of
// `faces` whose line is no taller than `face_h` (the pill's, as the single number's) and fits beside the icon. No digit
// to spare, as the single number keeps: every tap lays the tile out again. Without a range the chip hides.
inline void range_chip(Widgets &w,const Tile &t,int x,int y,int cw,int ch,int face_h,std::initializer_list<const lv_font_t *> faces){
  auto *chip=w.keys[2];
  if(!chip||t.domain()!="climate")return;
  const bool range=tile_controls::climate_range(t);
  set_hidden(chip,!range);
  if(w.pill_value)set_hidden(w.pill_value,range);
  w.key_commands[2]=range?tile_controls::RANGE_SWITCH:tile_controls::NONE;
  if(!range)return;
  const char *end=t.range_end==tile_controls::RANGE_HIGH?"cool":"heat";
  auto *icon=w.key_icons[2],*value=lv_obj_get_child(chip,1);
  label(icon,tile_controls::climate_mode_icon(end));
  set_color(icon,LV_STYLE_TEXT_COLOR,lv_color_hex(tile_controls::mode_color(end)));
  if(mini_icon_font&&(int)lv_font_get_line_height(lv_obj_get_style_text_font(icon,LV_PART_MAIN))>ch-ui::px(6))set_font(icon,mini_icon_font);
  const int icon_w=lv_font_get_line_height(lv_obj_get_style_text_font(icon,LV_PART_MAIN)),pad=ui::px(6);
  const std::string text=tile_controls::format_value(tile_controls::range_end(t,t.range_end),tile_controls::edit_step(t),"°");
  // Measured by the widest temperature this thermostat can show, as a single temperature is by its number: the face
  // stays the same from tap to tap, and the icon never makes the number smaller.
  const std::string widest=tile_controls::widest_setpoint(t);
  const lv_font_t *face=nullptr;
  for(const auto *candidate:faces){
    if(!candidate||!face_covers(candidate,widest))continue;
    face=candidate;
    if((int)lv_font_get_line_height(candidate)<=face_h&&text_width(widest,candidate)+pad<=cw)break;
  }
  if(!face)face=lv_obj_get_style_text_font(value,LV_PART_MAIN);
  set_font(value,face);label(value,text);
  lv_obj_set_pos(chip,x,y);lv_obj_set_size(chip,std::max(1,cw),std::max(1,ch));
  // The number may stand taller than the chip, as the single number stands in its pill: it is not cut at the chip's edge.
  lv_obj_add_flag(chip,LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  // No room for the icon beside the widest number: the number alone, in the colour of its end, on every tap alike.
  const int tw=text_width(text,face);
  const bool with_icon=icon_w+pad/2+text_width(widest,face)+pad<=cw;
  set_hidden(icon,!with_icon);
  set_color(value,LV_STYLE_TEXT_COLOR,with_icon?theme::color(theme::INK):lv_color_hex(tile_controls::mode_color(end)));
  const int left=std::max(0,(cw-(with_icon?icon_w+pad/2:0)-tw)/2);
  lv_obj_set_align(icon,LV_ALIGN_TOP_LEFT);lv_obj_set_pos(icon,left,(ch-icon_w)/2);
  lv_obj_set_align(value,LV_ALIGN_TOP_LEFT);lv_obj_set_pos(value,left+(with_icon?icon_w+pad/2:0),(ch-(int)lv_font_get_line_height(face))/2);
}
// The - and + keys of a stepper as round keys inside its grey pill, the number or a range's chip between them.
inline void stepper_keys(Widgets &w,int width,int height,const lv_font_t *text_font,const Tile *tile=nullptr){
  const int in=std::max(2,ui::px(ui::large()?4:3)),d=std::max(1,height-2*in);
  for(int n=0;n<2;++n){
    if(!w.keys[n])continue;
    lv_obj_set_size(w.keys[n],d,d);lv_obj_set_pos(w.keys[n],n?width-in-d:in,in);
    lv_obj_set_style_bg_opa(w.keys[n],LV_OPA_COVER,0);lv_obj_set_ext_click_area(w.keys[n],in);center_icon(w.key_icons[n]);
  }
  if(tile)range_chip(w,*tile,in+d+in,in,width-2*(in+d+in),d,height,{watch_value_font,text_font,small_font});
  // Measured with a digit to spare, so the number a tap on + makes still fits the face chosen here.
  const std::string widest=std::string(lv_label_get_text(w.pill_value))+"8";
  const int room=width-2*(d+in)-ui::px(4);
  // A thermostat's range is two numbers: the small face before it gives up (never dots: LVGL writes them into the text
  // measured here, lvgl-dots-in-label-text).
  const lv_font_t *face=text_font;
  for(const auto *candidate:{watch_value_font,text_font,small_font})
    if(candidate&&face_covers(candidate,widest)&&(int)lv_font_get_line_height(candidate)<=height&&text_width(widest,candidate)<=room){face=candidate;break;}
  set_font(w.pill_value,face);
  const int lh=lv_font_get_line_height(face);
  lv_obj_set_pos(w.pill_value,in+d,(height-lh)/2);lv_obj_set_size(w.pill_value,std::max(1,width-2*(in+d)),lh);
}
// Build (once per control set) and lay out the panel; returns the width it takes
// from the text, including the gap, or 0 when the card shows no panel.
inline int layout_panel(Widgets &w,const Tile &t,bool large,int content_w,int content_h) {
  std::string mode=tile_controls::panel_kind(t);
  // A full card that draws its setpoint and mode keys as rows (render_tall) takes the taller card's control sizes.
  const bool taller=t.row_span()>1 && (!w.full || tile_controls::climate_modes_selected(t));
  // A full-page card fills the glass whatever the grid under it, so its keys follow the room the card has on the glass:
  // large keys once its content runs 56 mm along its longer side, the way the keys stand in a row. Before (firmware
  // 0.35.0) the height of one cell decided, so more rows chosen (a 10.1-inch with eight) gave the whole page the small
  // keys. Every board keeps what it had: the CYD's card (at most 51 mm) the small keys, every other the large.
  PanelMetrics m=w.full?panel_metrics_full(std::max(content_w,content_h)>=ui::mm(56)):panel_metrics(large);
  if(taller){
    m.key_h=std::max(ui::touch_min(),ui::px(large?48:34));m.key_w=m.key_h;
    m.pill_w=std::min(content_w,ui::control_max_width());m.pill_key=m.key_h;
    m.slider_h=m.key_h;m.toggle_h=m.key_h;m.ext=0;
    if(mode=="toggle"){
      const auto toggle=tall_tile::toggle(content_w,m.toggle_h);
      if(toggle.empty()){hide_panel(w);return 0;}
      m.toggle_w=toggle.w;
    }
    m.slider_w=std::max(ui::touch_min(),m.pill_w-m.key_h-m.gap);
    // A resized panel is rebuilt once, not on each live state update.
    if(w.panel_layout_w!=content_w||w.panel_layout_h!=content_h){end_panel(w);w.panel_mode.clear();}
    w.panel_layout_w=content_w;w.panel_layout_h=content_h;
  }
  const int knob_pad=taller?ui::px(large?4:3):4;
  const lv_font_t *icon_font=w.full?w.icon_font:mini_icon_font?mini_icon_font:w.icon_font;
  const lv_font_t *text_font=control_font?control_font:w.title_font;
  auto d=t.domain();
  // A double-width card's controls fill the cell they stand on (cell_content_width); a card over the whole page
  // keeps the wide sizes of panel_metrics_full, centred under it. A row of keys divides that cell between three
  // of them, and never takes a key above the size the look gives it.
  // A full card's sizes are the look's, but its glass can be narrower than they are (a small screen standing up):
  // every width stays inside the card, and a key never below the touch minimum.
  if(w.full){
    m.pill_w=std::min(m.pill_w,content_w);
    m.slider_w=std::min(m.slider_w,std::max(ui::touch_min(),content_w-m.key_h-m.gap));
    m.toggle_w=std::min(m.toggle_w,content_w);
  }
  const int fill=(w.full||taller)?m.pill_w:cell_content_width(w);
  const int keys_room=w.full?content_w:fill;
  const int key_w=std::min(m.key_w,std::max(ui::touch_min(),(keys_room-2*m.gap)/3));
  // A player's volume shares that room with its mute key; every other slider takes it whole.
  const int track=(w.full||taller)?(mode=="volume"?m.slider_w:m.pill_w):(mode=="volume"?std::max(ui::touch_min(),fill-m.gap-m.key_h):fill);
  if(!w.panel){w.panel=panel_obj(w.tile,false);}
  if(w.panel_mode!=mode || w.panel_full!=w.full || w.panel_tall!=taller){
    end_panel(w);w.panel_mode=mode;w.panel_full=w.full;w.panel_tall=taller;w.panel_dirty=true;
    if(tile_controls::is_key_row(mode)){
      for(unsigned n=0;n<3;++n){panel_key(w,n,w.panel,m,key_w,m.key_h,false);panel_icon(w,n,icon_font);}
    }else if(mode=="mode"){
      // Drawn per render (draw_mode_bar): the track and a segment per mode, as many as its width holds.
    }else if(mode=="setpoint"||mode=="stepper"){
      w.pill=panel_obj(w.panel,false);lv_obj_set_size(w.pill,fill,m.key_h+2);
      lv_obj_set_style_radius(w.pill,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(w.pill,LV_OPA_COVER,0);
      panel_key(w,0,w.pill,m,m.pill_key,m.key_h+2,true);panel_icon(w,0,icon_font);lv_label_set_text(w.key_icons[0],tile_controls::glyph::MINUS);
      panel_key(w,1,w.pill,m,m.pill_key,m.key_h+2,true);panel_icon(w,1,icon_font);lv_label_set_text(w.key_icons[1],tile_controls::glyph::PLUS);
      // Holding -/+ keeps stepping (LVGL repeats while pressed); one call goes out after the finger rests.
      for(unsigned n=0;n<2;++n)lv_obj_add_event_cb(w.keys[n],control_event,LV_EVENT_LONG_PRESSED_REPEAT,(void*)(uintptr_t)((&w-widgets.data())*16+n));
      lv_obj_set_pos(w.keys[0],0,0);lv_obj_set_pos(w.keys[1],fill-m.pill_key,0);
      w.pill_value=lv_label_create(w.pill);lv_obj_remove_flag(w.pill_value,LV_OBJ_FLAG_CLICKABLE);
      lv_obj_set_style_text_font(w.pill_value,text_font,0);lv_obj_set_style_text_align(w.pill_value,LV_TEXT_ALIGN_CENTER,0);
      lv_label_set_long_mode(w.pill_value,LV_LABEL_LONG_CLIP);
      // A thermostat's range (firmware 0.19.0): in the number's place the end the -/+ move, its heat or cool icon before
      // the temperature, on the pill as a single temperature stands there; a tap switches it and lights it up while
      // the finger is down. The third key of the panel, on the panel above the pill, so the pill's own children stay.
      if(t.domain()=="climate"){
        panel_key(w,2,w.panel,m,m.pill_key,m.key_h,true);panel_icon(w,2,icon_font);
        auto *value=lv_label_create(w.keys[2]);lv_obj_remove_flag(value,LV_OBJ_FLAG_CLICKABLE);
        set_color(w.keys[2],LV_STYLE_BG_COLOR,theme::color(theme::STEPPER_KEY),LV_STATE_PRESSED);
        lv_obj_add_flag(w.keys[2],LV_OBJ_FLAG_HIDDEN);
      }
      lv_obj_set_size(w.pill_value,std::max(1,fill-2*m.pill_key),lv_font_get_line_height(text_font));
      lv_obj_set_pos(w.pill_value,m.pill_key,(m.key_h+2-lv_font_get_line_height(text_font))/2);
      w.key_commands[0]=tile_controls::STEP_DOWN;w.key_commands[1]=tile_controls::STEP_UP;
    }else if(tile_controls::is_slider(mode)){
      int h=m.slider_h;
      auto *slider=lv_slider_create(w.panel);w.control_slider=slider;
      lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_remove_flag(slider,LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_size(slider,track,h);
      lv_obj_set_style_pad_all(slider,0,LV_PART_MAIN);
      lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
      // The handle is a short white bar inside the fill, like Home Assistant's slider.
      lv_obj_set_style_radius(slider,2,LV_PART_KNOB);lv_obj_add_style(slider,theme::style(theme::Paint::knob),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
      slider_handle(slider,track,h);
      lv_obj_set_style_border_width(slider,0,LV_PART_KNOB);lv_obj_set_style_shadow_width(slider,0,LV_PART_KNOB);
      lv_obj_set_ext_click_area(slider,m.ext+2);
      lv_obj_add_event_cb(slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)w.index);
      if(mode=="volume"){panel_key(w,0,w.panel,m,m.key_h,m.key_h,false);panel_icon(w,0,icon_font);w.key_commands[0]=tile_controls::MEDIA_MUTE;}
    }else if(mode=="toggle"){
      panel_key(w,0,w.panel,m,m.toggle_w,m.toggle_h,false);lv_obj_set_style_radius(w.keys[0],LV_RADIUS_CIRCLE,0);
      w.knob=panel_obj(w.keys[0],false);lv_obj_set_size(w.knob,m.toggle_h-2*knob_pad,m.toggle_h-2*knob_pad);lv_obj_set_y(w.knob,knob_pad);
      lv_obj_set_style_radius(w.knob,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(w.knob,LV_OPA_COVER,0);lv_obj_add_style(w.knob,theme::style(theme::Paint::knob),0);
      w.key_commands[0]=tile_controls::TOGGLE;
    }else if(mode=="run"){
      const char *text=tile_controls::run_label(d);
      lv_point_t size;lv_text_get_size(&size,text,text_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
      panel_key(w,0,w.panel,m,std::max(m.key_w*3/2,(int)size.x+2*m.run_pad),m.key_h,false);lv_obj_set_style_radius(w.keys[0],LV_RADIUS_CIRCLE,0);
      panel_icon(w,0,text_font);lv_label_set_text(w.key_icons[0],text);
      w.key_commands[0]=tile_controls::RUN;
    }else{end_panel(w);return 0;}
  }
  // Per-render contents: which keys, their icons and states; then the panel size and place.
  int panel_w=0,panel_h=m.key_h;uint32_t now=esphome::millis();
  auto set_checked=[&](unsigned n,bool checked){
    if(w.key_checked[n]==(int)checked)return;w.key_checked[n]=checked;
    if(checked)lv_obj_add_state(w.keys[n],LV_STATE_CHECKED);else lv_obj_remove_state(w.keys[n],LV_STATE_CHECKED);
    if(w.key_icons[n])lv_obj_set_style_text_color(w.key_icons[n],checked?theme::color(theme::ON_ACCENT):w.panel_text,0);
  };
  auto set_disabled=[&](unsigned n,bool disabled){if(disabled)lv_obj_add_state(w.keys[n],LV_STATE_DISABLED);else lv_obj_remove_state(w.keys[n],LV_STATE_DISABLED);};
  if(tile_controls::is_key_row(mode)){
    std::array<tile_controls::Key,3> keys;unsigned count=tile_controls::keys_for(t,keys,now);
    for(unsigned n=0;n<3;++n){
      if(n>=count){lv_obj_add_flag(w.keys[n],LV_OBJ_FLAG_HIDDEN);w.key_commands[n]=tile_controls::NONE;continue;}
      lv_obj_remove_flag(w.keys[n],LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.keys[n],n*(key_w+m.gap),0);
      label(w.key_icons[n],keys[n].icon);center_icon(w.key_icons[n]);w.key_commands[n]=keys[n].command;w.key_args[n]=keys[n].arg;
      // The active mode key carries the accent; "off" stays neutral grey.
      if(keys[n].checked && w.key_checked[n]!=1)lv_obj_set_style_bg_color(w.keys[n],keys[n].arg=="off"?theme::color(theme::OFF):w.panel_accent,LV_STATE_CHECKED);
      set_checked(n,keys[n].checked);set_disabled(n,keys[n].disabled);
    }
    panel_w=count?count*key_w+(count-1)*m.gap:0;
  }else if(mode=="mode"){
    // A thermostat's modes (firmware 0.19.0): the bar under its -/+ in "Temperature and mode", with the same rule for
    // how many fit (climate_tile::bar_room) and the same modes (climate_bar_keys). Over the card's reach on a card of
    // more than one row or the whole page, a finger per segment beside the name on a card of one row.
    const auto cm=bar_metrics(m,large);
    const bool stretches=w.full||taller;
    const int reach=std::min(keys_room,ui::control_max_width());
    std::array<tile_controls::Key,climate_tile::SEGMENTS> modes;
    const int room=climate_tile::bar_room(cm,reach,(int)tile_controls::climate_bar_keys(t,modes));
    panel_w=climate_tile::bar_width(cm,reach,room,stretches);panel_h=cm.touch;
    if(panel_w)draw_mode_bar(w,t,w.panel,w.pill,w.segments.data(),{0,0,panel_w,panel_h},room,cm,large);
  }else if(mode=="setpoint"||mode=="stepper"){
    float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
    std::string suffix=tile_controls::thermostat(t)?tile_controls::setpoint_suffix(t):screen_text::unit_suffix(t.unit);
    // A range: the chip says the chosen end (range_chip); the number keeps it too, which the tall form measures by.
    const float step=tile_controls::edit_step(t);
    label(w.pill_value,tile_controls::format_value(tile_controls::climate_range(t)?tile_controls::range_end(t,t.range_end):shown,step,suffix.c_str()));
    panel_w=fill;panel_h=m.key_h+2;
    if(!taller)stepper_keys(w,fill,panel_h,text_font,&t);
  }else if(tile_controls::is_slider(mode)){
    bool has_slider=mode!="volume" || (t.supported & tile_controls::feature::MEDIA_VOLUME_SET);
    if(has_slider){
      lv_obj_remove_flag(w.control_slider,LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.control_slider,0,(panel_h-m.slider_h)/2);
      // Keep the dragged value while the command is under way; HA's report takes over afterwards.
      if(!lv_obj_has_state(w.control_slider,LV_STATE_PRESSED) && !(t.pending && !t.confirmed))lv_slider_set_value(w.control_slider,slider_value(t),LV_ANIM_OFF);
      panel_w=track;
    }else lv_obj_add_flag(w.control_slider,LV_OBJ_FLAG_HIDDEN);
    if(mode=="volume"){
      bool has_mute=t.supported & tile_controls::feature::MEDIA_VOLUME_MUTE;
      if(has_mute){
        lv_obj_remove_flag(w.keys[0],LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.keys[0],panel_w?panel_w+m.gap:0,0);
        label(w.key_icons[0],t.muted?tile_controls::glyph::MUTED:tile_controls::glyph::VOLUME);
        if(t.muted && w.key_checked[0]!=1)lv_obj_set_style_bg_color(w.keys[0],w.panel_accent,LV_STATE_CHECKED);
        set_checked(0,t.muted);panel_w+=(panel_w?m.gap:0)+m.key_h;
      }else lv_obj_add_flag(w.keys[0],LV_OBJ_FLAG_HIDDEN);
    }
  }else if(mode=="toggle"){
    bool on=t.pending && !t.confirmed ? t.optimistic_on : t.state=="on";
    if(on && w.key_checked[0]!=1)lv_obj_set_style_bg_color(w.keys[0],w.panel_accent,LV_STATE_CHECKED);
    set_checked(0,on);
    if(w.knob_on!=(int)on){w.knob_on=on;lv_obj_set_x(w.knob,on?m.toggle_w-m.toggle_h+knob_pad:knob_pad);}
    panel_w=m.toggle_w;panel_h=m.toggle_h;
  }else if(mode=="run"){
    // The requested width: a key created in this pass has no coordinates before LVGL's layout.
    panel_w=lv_obj_get_style_width(w.keys[0],LV_PART_MAIN);
  }
  (void)now;
  if(!panel_w){hide_panel(w);return 0;}
  // A panel shown again kept the colours of the card it last served.
  if(lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN)){lv_obj_remove_flag(w.panel,LV_OBJ_FLAG_HIDDEN);w.panel_dirty=true;}
  lv_obj_set_size(w.panel,panel_w,panel_h);
  if(w.full||taller)lv_obj_set_pos(w.panel,std::max(0,(content_w-panel_w)/2),std::max(0,content_h-panel_h));
  else lv_obj_set_pos(w.panel,content_w-panel_w,std::max(0,(content_h-panel_h)/2));
  w.panel_w=panel_w+m.text_gap;
  return w.panel_w;
}
// Colours follow the card palette; called with the rest of the palette when it changes.
inline void style_panel(Widgets &w,const Tile &t,lv_color_t accent,lv_color_t text) {
  if(!w.panel || w.panel_mode.empty())return;
  const uint32_t surface=theme::surface(t.background);
  lv_color_t card=lv_color_hex(surface);
  lv_color_t key_bg=lv_color_hex(theme::key_on(surface,236));
  lv_color_t key_pressed=lv_color_hex(theme::key_on(surface,212));
  w.panel_accent=accent;w.panel_text=text;
  for(unsigned n=0;n<3;++n){
    auto *key=w.keys[n];if(!key)continue;
    bool in_pill=w.pill && lv_obj_get_parent(key)==w.pill;
    if(n==2&&w.pill&&w.panel_mode=="setpoint"){   // a range's chip (range_chip): no fill of its own, grey while pressed
      set_color(key,LV_STYLE_BG_COLOR,theme::color(theme::CARD));set_color(key,LV_STYLE_BG_COLOR,theme::color(theme::STEPPER_KEY_PRESSED),LV_STATE_PRESSED);
      continue;
    }
    set_color(key,LV_STYLE_BG_COLOR,in_pill?theme::color(theme::STEPPER_KEY):key_bg);
    set_color(key,LV_STYLE_BG_COLOR,in_pill?theme::color(theme::STEPPER_KEY_PRESSED):key_pressed,LV_STATE_PRESSED);
    set_color(key,LV_STYLE_BG_COLOR,w.key_args[n]=="off" && w.panel_mode=="mode"?theme::color(theme::OFF):accent,LV_STATE_CHECKED);
    if(w.key_icons[n])set_color(w.key_icons[n],LV_STYLE_TEXT_COLOR,w.key_checked[n]==1?theme::color(theme::ON_ACCENT):text);
  }
  if(w.pill){set_color(w.pill,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));if(w.pill_value)set_color(w.pill_value,LV_STYLE_TEXT_COLOR,text);}
  if(w.control_slider){
    bool on=fresh() && t.slider_active();
    lv_color_t fill=on?accent:theme::color(theme::OFF);
    // The track is the fill colour at 20 % over the card, as in Home Assistant.
    set_color(w.control_slider,LV_STYLE_BG_COLOR,lv_color_mix(fill,card,51),LV_PART_MAIN);
    set_color(w.control_slider,LV_STYLE_BG_COLOR,fill,LV_PART_INDICATOR);
    slider_bar(w.control_slider,slider_bar_shown(t,on));
  }
  if(w.knob){set_color(w.keys[0],LV_STYLE_BG_COLOR,theme::color(theme::PANEL_TOGGLE_OFF));set_color(w.keys[0],LV_STYLE_BG_COLOR,theme::color(theme::PANEL_TOGGLE_OFF_PRESSED),LV_STATE_PRESSED);}
}
inline void control_event(lv_event_t *e) {
  unsigned code=(uintptr_t)lv_event_get_user_data(e);unsigned slot=code/16,n=code%16;
  if(slot>=widgets.size() || n>=3)return;
  auto &w=widgets[slot];
  if(!enabled || !fresh() || w.index>=model.count || !w.keys[n])return;
  if(lv_obj_has_state(w.keys[n],LV_STATE_DISABLED))return;
  uint32_t now=esphome::millis();
  auto &t=model.tiles[w.index];
  if(t.row_span()>1&&!t.full&&!tile_controls::panel_available(t))return;
  int command=w.key_commands[n];
  bool step=command==tile_controls::STEP_DOWN || command==tile_controls::STEP_UP;
  bool held=lv_event_get_code(e)==LV_EVENT_LONG_PRESSED_REPEAT;
  if(held){ if(!step || now-t.edit_since<300)return; }  // three steps a second while holding
  else if(step){ if(!screen_input::touch_guard.accept_repeat(now,400+slot*16+n)){ESP_LOGI("touch","tap on control %u ignored: %s",(unsigned)slot,screen_input::touch_guard.reason().c_str());return;} }
  else if(!allowed(now,400+slot*16+n,"control "+std::to_string(slot)))return;
  if(!t.available())return;
  // A range (firmware 0.19.0): the chip switches the end the -/+ move, heat or cool; the -/+ move that end.
  if(command==tile_controls::RANGE_SWITCH&&tile_controls::climate_range(t)){
    t.range_end=t.range_end==tile_controls::RANGE_HIGH?tile_controls::RANGE_LOW:tile_controls::RANGE_HIGH;
    refresh_tile(w.index);return;
  }
  if(step&&tile_controls::climate_range(t)){
    range_step(t,command==tile_controls::STEP_UP?1:-1);
    if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)&&detail_index==w.index)climate_paint_ends(t);
    refresh_tile(w.index);return;
  }
  if(step){
    // Local at once, tap after tap; tick() sends the last value after a short pause.
    float current=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
    t.edit_value=tile_controls::step_value(current,tile_controls::edit_step(t),t.minimum,t.maximum,command==tile_controls::STEP_UP?1:-1);
    t.edit_since=now;t.edit_sent=false;
    if(w.pill_value){std::string suffix=tile_controls::thermostat(t)?tile_controls::setpoint_suffix(t):screen_text::unit_suffix(t.unit);label(w.pill_value,tile_controls::format_value(t.edit_value,tile_controls::edit_step(t),suffix.c_str()));}
    return;
  }
  if(command==tile_controls::OPEN_CARD){active_index=w.index;show_detail(w.index);return;}
  if(t.waiting(now))return;
  auto a=tile_controls::press_key(t,command,w.key_args[n]);
  if(a.valid())action(a.service,t.entity,a.key,a.value);
}
// The one spinner of the firmware: a busy card, the starting screen and a camera that loads (firmware 0.2.73+). The
// ring in the spinner paint, the arc in Home Assistant's blue. Null where the board builds no spinner.
inline lv_obj_t *spinner_create(lv_obj_t *parent, int size, int arc) {
#if LV_USE_SPINNER
  auto *spinner = lv_spinner_create(parent);
  lv_spinner_set_anim_params(spinner, 900, 200);
  lv_obj_set_size(spinner, size, size);
  lv_obj_remove_flag(spinner, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_arc_width(spinner, arc, LV_PART_MAIN);
  lv_obj_set_style_arc_width(spinner, arc, LV_PART_INDICATOR);
  lv_obj_add_style(spinner, theme::style(theme::Paint::spinner), LV_PART_MAIN);
  lv_obj_set_style_arc_color(spinner, lv_color_hex(theme::ha::RAIN), LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(spinner, LV_OPA_TRANSP, LV_PART_KNOB);
  lv_obj_set_style_pad_all(spinner, 0, LV_PART_KNOB);
  return spinner;
#else
  (void) parent; (void) size; (void) arc;
  return nullptr;
#endif
}
// A busy card is covered by a translucent white sheet with a small spinner until
// Home Assistant confirms; the sheet also swallows taps meanwhile.
inline void set_busy(Widgets &w,bool busy,bool large){
  if(!busy){if(w.busy)lv_obj_add_flag(w.busy,LV_OBJ_FLAG_HIDDEN);return;}
  if(!w.busy){
    w.busy=lv_obj_create(w.tile);lv_obj_remove_style_all(w.busy);lv_obj_remove_flag(w.busy,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_flag(w.busy,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_style(w.busy,theme::style(theme::Paint::veil),0);lv_obj_set_style_bg_opa(w.busy,LV_OPA_60,0);
    lv_obj_set_style_radius(w.busy,lv_obj_get_style_radius(w.tile,LV_PART_MAIN),0);
    w.spinner=spinner_create(w.busy,ui::px(large?30:20),ui::px(large?4:3));
    if(w.spinner)lv_obj_center(w.spinner);
  }
  // Cover the whole card, padding included, at the width the card asks for: a slot that just turned
  // wide is still single width in LVGL's own coordinates. Unchanged sizes cost LVGL nothing.
  lv_obj_set_pos(w.busy,-lv_obj_get_style_pad_left(w.tile,LV_PART_MAIN),-lv_obj_get_style_pad_top(w.tile,LV_PART_MAIN));
  lv_obj_set_size(w.busy,tile_width(w),tile_height(w));
  lv_obj_remove_flag(w.busy,LV_OBJ_FLAG_HIDDEN);
  // Controls and custom parts created after the sheet would otherwise paint over its right side.
  if(lv_obj_get_index(w.busy)!=(int32_t)lv_obj_get_child_count(w.tile)-1)lv_obj_move_foreground(w.busy);
}
// A camera whose picture fills its card turns the firmware's one spinner in the middle of the card while that picture
// loads (firmware 0.3.3), the size a busy card's has: a page turn to a camera shows it coming, never an empty card.
inline void set_loading(Widgets &w,bool on,int width,int height){
  if(!on){if(w.loading)lv_obj_add_flag(w.loading,LV_OBJ_FLAG_HIDDEN);return;}
  const bool large=ui::large();const int size=ui::px(large?30:20);
  if(!w.loading)w.loading=spinner_create(w.tile,size,ui::px(large?4:3));
  if(!w.loading)return;
  lv_obj_set_pos(w.loading,(width-size)/2,(height-size)/2);
  lv_obj_remove_flag(w.loading,LV_OBJ_FLAG_HIDDEN);
}
// The card that takes a whole page (firmware 0.2.62+). Without a control it is one big button: the icon in a
// large circle with the name and the state under it (the circle in the state colour, the card white or its own
// pastel like every other card), so a wall switch reads from across the room and a push anywhere works. With a
// small slider, direct controls or a graph the double-width card's head stays on top and the control takes
// a strip at the bottom, so a tap anywhere else still does what a tap on the tile does. The built-in cards
// (clock, forecast, sun path) simply get the whole page.
// A media player over the whole page (firmware 0.2.64+): the head as on every full card, and under it the media card
// itself, wide: the cover at the left, the track, the bar and the keys beside it, the volume row along the bottom.
// Parts: 0 placeholder, 1 its icon, 2 title, 3 artist, 4 track, 5 fill, 6 elapsed, 7 total, 8-10 keys, 11 volume
// down, 12 slider, 13 volume up (firmware 0.39.0; a mute key and the percentage before), MEDIA_PICTURE (14) the cover. Built once per slot and moved on every redraw.
inline void media_tile_key_event(lv_event_t *e){
  unsigned code=(uintptr_t)lv_event_get_user_data(e);unsigned slot=code/16,n=code%16;
  if(slot>=widgets.size() || n>2)return;
  auto &w=widgets[slot];
  if(!enabled || !fresh() || w.index>=model.count || w.extra_mode!="media")return;
  if(lv_obj_has_state(lv_event_get_target_obj(e),LV_STATE_DISABLED))return;
  const uint32_t now=esphome::millis();
  if(!allowed(now,500+slot*16+n,"media key "+std::to_string(slot)))return;
  auto &t=model.tiles[w.index];
  if(!t.available() || t.waiting(now))return;
  static const int commands[]={21,20,22};
  media_action(t,n==1 && media_off(t)?24:commands[n]);
}
inline void render_media_full(Widgets &w,const Tile &t,bool big,int content_w,int content_h,int head_h){
  using namespace media_card;
  using namespace tile_controls;
  const auto &x=t.extra();
  const Metrics m=media_metrics(big);
  const int top=head_h+(ui::px(big?8:4));
  const Layout l=layout(m,content_w,std::max(40,content_h-top-(ui::px(big?4:2))));
  begin_extra(w,"media",content_w,content_h);
  auto at=[&](Rect r){r.y+=top;return r;};
  const bool usable=fresh()&&t.available(),track=usable&&has_track(t.state),play=media_card::playing(t.state);
  const uint32_t f=t.supported;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  const size_t slot=&w-widgets.data();
  // The placeholder and the player's icon; the cover comes over them once the app served it.
  w.parts[0]=media_box(w.extra,w.parts[0],at(l.art),theme::tint(theme::ha::LIGHT_BLUE,51),l.art_radius);
  const std::string glyph=icon_for(t);
  // The big icon where the square holds it (a cover that shrank for the volume row may not), else the tile's icon.
  const lv_font_t *placeholder_font=big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=l.art.h?big_icon_font:w.icon_font;
  if(!w.parts[1]){w.parts[1]=lv_label_create(w.parts[0]);lv_obj_remove_flag(w.parts[1],LV_OBJ_FLAG_CLICKABLE);}
  set_font(w.parts[1],placeholder_font);set_color(w.parts[1],LV_STYLE_TEXT_COLOR,theme::rgb(theme::icon(theme::ha::LIGHT_BLUE)));label(w.parts[1],glyph);lv_obj_center(w.parts[1]);
  // The colour behind the cover's rounded corners: the card's own, as the palette below will paint it (firmware 0.3.2).
  // Read from the card, it was the colour of whatever the card showed before, so a new card asked for a cover with the
  // wrong corners first and for the right one after its first drawing.
  const uint32_t ground=t.transparent?theme::hex(theme::PAGE):theme::surface(t.background);
  lv_image_dsc_t *src=nullptr;
  // A card open over the page owns the cover then; the tile asks again once the card closes (cover_tick).
  const bool card_open=detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN);
  const bool pictured=camera_supported()&&track&&!x.media_picture.empty();
  w.cover_entity=pictured?t.entity:std::string();w.cover_mark=pictured?x.media_picture:std::string();
  w.cover_size=l.art.w;w.cover_ground=ground;w.cover_rect=at(l.art);
  // Built off the glass (warm_page): the cover it may already have in the store, without asking for one.
  if(pictured&&warming)src=kept_cover(w);
  else if(pictured&&!card_open){cover_want(t.entity,x.media_picture,l.art.w,ground,CoverOwner::TILE,slot);src=cover_ready(t.entity,l.art.w,ground);}
  if(src)w.parts[MEDIA_PICTURE]=media_picture_show(w.extra,w.parts[MEDIA_PICTURE],at(l.art),src);
  else if(w.parts[MEDIA_PICTURE]){lv_obj_delete(w.parts[MEDIA_PICTURE]);w.parts[MEDIA_PICTURE]=nullptr;}
  // Title, artist · album, left-aligned beside the cover.
  const lv_font_t *title_font=watch_font?watch_font:w.title_font,*artist_font=control_font?control_font:w.title_font,*small=small_font?small_font:w.title_font;
  auto text=[&](unsigned i,const lv_font_t *font,const Rect &r,lv_text_align_t align,const std::string &value,theme::Role role){
    auto *p=part_label(w,i,font,r.x,r.y+top,r.w,align,value);lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);set_color(p,LV_STYLE_TEXT_COLOR,theme::color(role));lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);return p;
  };
  // The title and the artist line roll by when they are too long (firmware 0.2.77+), as on the card.
  marquee(text(2,title_font,l.title,LV_TEXT_ALIGN_LEFT,track&&!x.media_title.empty()?x.media_title:std::string(idle_text(usable?t.state:"unavailable")),theme::INK));
  if(l.artist)marquee(text(3,artist_font,l.artist_line,LV_TEXT_ALIGN_LEFT,track?subtitle(x.media_artist,x.media_album):std::string(),theme::MUTED));
  else if(w.parts[3])lv_obj_add_flag(w.parts[3],LV_OBJ_FLAG_HIDDEN);
  // The progress bar and its times; a stream without a length has none.
  w.media_bar_w=l.bar.w;
  const bool timed=track&&x.media_duration;
  if(timed){
    w.parts[4]=media_box(w.extra,w.parts[4],at(l.bar),theme::hex(theme::TRACK),LV_RADIUS_CIRCLE);lv_obj_remove_flag(w.parts[4],LV_OBJ_FLAG_HIDDEN);
    Rect fill=at(l.bar);fill.w=std::max(l.bar.h,l.bar.w*std::max(0,progress(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration))/1000);
    w.parts[5]=media_box(w.extra,w.parts[5],fill,media_accent(),LV_RADIUS_CIRCLE);lv_obj_remove_flag(w.parts[5],LV_OBJ_FLAG_HIDDEN);
  }else for(unsigned i:{4u,5u})if(w.parts[i])lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);
  if(timed&&l.times){
    text(6,small,l.elapsed,LV_TEXT_ALIGN_LEFT,clock_text(elapsed_seconds(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration)),theme::SUBTLE);
    text(7,small,l.total,LV_TEXT_ALIGN_RIGHT,clock_text(x.media_duration),theme::SUBTLE);
  }else for(unsigned i:{6u,7u})if(w.parts[i])lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);
  // The keys and the volume row. Their events carry the slot: the tile in it may change with the page. An off player
  // shows one power key and no volume row.
  const lv_font_t *key_font=mini_icon_font?mini_icon_font:w.icon_font;
  auto user=[&](unsigned n){return (void*)(uintptr_t)(slot*16+n);};
  auto show=[&](unsigned i,bool on){if(w.parts[i]){if(on)lv_obj_remove_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);}};
  const bool off=usable && media_off(t), volume=!off && std::isfinite(t.volume);
  if(off){
    w.parts[9]=media_key(w.extra,w.parts[9],at(l.play),glyph::STANDBY,w.icon_font,true,false,can(feature::MEDIA_TURN_ON),media_tile_key_event,user(1));
    show(9,can(feature::MEDIA_TURN_ON));
  }else{
    w.parts[8]=media_key(w.extra,w.parts[8],at(l.prev),glyph::PREVIOUS,key_font,false,false,can(feature::MEDIA_PREVIOUS),media_tile_key_event,user(0));
    w.parts[9]=media_key(w.extra,w.parts[9],at(l.play),play?glyph::PAUSE:glyph::PLAY,w.icon_font,true,false,can(feature::MEDIA_PLAY|feature::MEDIA_PAUSE),media_tile_key_event,user(1));
    w.parts[10]=media_key(w.extra,w.parts[10],at(l.next),glyph::NEXT,key_font,false,false,can(feature::MEDIA_NEXT),media_tile_key_event,user(2));
    show(9,true);
  }
  show(8,!off);show(10,!off);
  if(volume)media_volume_row(w.extra,&w.parts[11],at(l.minus),at(l.volume),at(l.plus),t,big,usable,(void*)(uintptr_t)w.index,false,nullptr,key_font);
  show(11,volume);show(12,volume);show(13,volume);
}
// Both overlay and tile use the same feature-filtered cover commands. Slot
// ownership is resolved on every tap; stale/offline/waiting entities stay inert.
inline void cover_tile_key_event(lv_event_t *e){
  const unsigned tag=(uintptr_t)lv_event_get_user_data(e),slot=tag/8,part=tag%8;
  if(slot>=widgets.size()||part>=6)return;
  const auto &w=widgets[slot];if(w.index>=model.count||w.extra_mode!="cover_tilt")return;
  const auto &t=model.tiles[w.index];
  if(!enabled||!fresh()||!t.available()||t.waiting(esphome::millis())||!tile_controls::cover_tilt_selected(t))return;
  std::array<tile_controls::Key,3> keys;
  const unsigned count=part>=3?tile_controls::cover_tilt_keys(t,keys):tile_controls::keys_for(t,keys);
  if(part%3>=count||keys[part%3].disabled)return;
  if(!screen_input::touch_guard.accept(esphome::millis(),600+tag))return;
  const auto call=tile_controls::key_action(t,keys[part%3].command);
  if(!call.service.empty())action(call.service,t.entity,call.key,call.value);
}
// A thermostat's mode bar (firmware 0.3.3): under its -/+ on a card of "Temperature and mode" (the tall card's parts
// 2 and 4..9) and on its own as the panel of "Mode" (the panel's pill and segments, firmware 0.19.0). One bar, one
// drawing, one press: a segment says its place in the bar, and the bar's modes are climate_bar_keys for the room it
// holds, so the press finds the mode the segment shows.
constexpr int CLIMATE_MODE_PARTS=climate_tile::SEGMENTS;
// The segments of the bar a card shows: its panel's for "Mode", its tall card's otherwise.
inline lv_obj_t *const *mode_bar_segments(const Widgets &w){
  if(w.panel_mode=="mode")return w.segments.data();
  return w.extra_mode=="tall"?&w.parts[4]:nullptr;
}
inline void climate_mode_key_event(lv_event_t *e){
  const unsigned code=(uintptr_t)lv_event_get_user_data(e),slot=code/16,n=code%16;
  if(slot>=widgets.size())return;
  auto &w=widgets[slot];if(w.index>=model.count)return;
  auto *const *segments=mode_bar_segments(w);if(!segments)return;
  unsigned room=0;
  for(int i=0;i<CLIMATE_MODE_PARTS;++i)if(segments[i]&&!lv_obj_has_flag(segments[i],LV_OBJ_FLAG_HIDDEN))++room;
  auto &t=model.tiles[w.index];const uint32_t now=esphome::millis();
  if(n>=room||!enabled||!fresh()||!t.available()||t.waiting(now)||!tile_controls::thermostat(t))return;
  std::array<tile_controls::Key,CLIMATE_MODE_PARTS> keys;
  if(n>=tile_controls::climate_bar_keys(t,keys,room))return;
  if(!allowed(now,700+slot*8+n,"control "+std::to_string(slot)))return;
  if(keys[n].command==tile_controls::OPEN_CARD){active_index=w.index;show_detail(w.index);return;}
  const auto a=tile_controls::press_key(t,keys[n].command,keys[n].arg);
  if(a.valid())action(a.service,t.entity,a.key,a.value);
}
// One segment of a thermostat's mode bar: the mode's icon, its word where the bar has room, and the mode it is in
// filled in Home Assistant's colour for it with a white icon on it. `code`: its card's slot * 16 and its place.
inline void mode_segment(lv_obj_t *&p,lv_obj_t *parent,unsigned code,climate_tile::Rect r,const tile_controls::Key &k,bool words,
                         const lv_font_t *glyphs,const lv_font_t *text,bool ready,const Tile &t){
  if(!p){
    p=lv_obj_create(parent);lv_obj_remove_style_all(p);lv_obj_set_style_radius(p,LV_RADIUS_CIRCLE,0);
    lv_obj_set_style_bg_opa(p,LV_OPA_COVER,LV_STATE_PRESSED);lv_obj_set_style_opa(p,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_add_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);
    for(int c=0;c<2;++c){auto *label=lv_label_create(p);lv_obj_remove_flag(label,LV_OBJ_FLAG_CLICKABLE);}
    lv_obj_add_event_cb(p,climate_mode_key_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)code);
  }
  lv_obj_set_pos(p,r.x,r.y);lv_obj_set_size(p,r.w,r.h);lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);
  const bool mode=k.command==tile_controls::HVAC_MODE;
  lv_obj_set_style_bg_opa(p,k.checked?LV_OPA_COVER:LV_OPA_TRANSP,0);
  // A humidifier's mode has no colour of its own in Home Assistant: the one it is in takes the humidifier's blue.
  if(k.checked)set_color(p,LV_STYLE_BG_COLOR,lv_color_hex(theme::foreground(tile_controls::humidifier(t)?tile_controls::accent(t):tile_controls::mode_color(k.arg))));
  set_color(p,LV_STYLE_BG_COLOR,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
  const auto ink=k.checked?theme::color(theme::ON_ACCENT):theme::color(mode?theme::SLATE:theme::MUTED);
  auto *icon=lv_obj_get_child(p,0),*word=lv_obj_get_child(p,1);
  set_font(icon,glyphs);label(icon,k.icon);set_color(icon,LV_STYLE_TEXT_COLOR,ink);
  const bool with_word=words&&mode;
  const std::string name=with_word?tile_controls::thermostat_mode_text(t,k.arg):"";
  const int gh=lv_font_get_line_height(glyphs),space=ui::px(ui::large()?6:3),tw=with_word?text_width(name,text)+2:0;
  const int x0=(r.w-gh-(with_word?space+tw:0))/2;
  lv_obj_set_pos(icon,x0,(r.h-gh)/2);lv_obj_set_size(icon,gh,gh);lv_obj_set_style_text_align(icon,LV_TEXT_ALIGN_CENTER,0);
  set_hidden(word,!with_word);
  if(with_word){
    set_font(word,text);label(word,name);set_color(word,LV_STYLE_TEXT_COLOR,ink);
    const int th=lv_font_get_line_height(text);lv_obj_set_pos(word,x0+gh+space,(r.h-th)/2);lv_obj_set_size(word,tw,th);
  }
  if(ready)lv_obj_remove_state(p,LV_STATE_DISABLED);else lv_obj_add_state(p,LV_STATE_DISABLED);
}
// The whole bar in `bar` of `parent`: its track, and a segment per mode climate_bar_keys picks for `room`, with words
// beside the icons where every segment has room for its own ("Heat", "Cool", "Auto"). Segments past them hide.
inline void draw_mode_bar(Widgets &w,const Tile &t,lv_obj_t *parent,lv_obj_t *&track,lv_obj_t **segments,climate_tile::Rect bar,
                          int room,const climate_tile::Metrics &cm,bool large){
  if(!track){track=lv_obj_create(parent);lv_obj_remove_style_all(track);lv_obj_set_style_bg_opa(track,LV_OPA_COVER,0);
    lv_obj_set_style_radius(track,LV_RADIUS_CIRCLE,0);lv_obj_remove_flag(track,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(track,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(track,bar.x,bar.y);lv_obj_set_size(track,bar.w,bar.h);lv_obj_remove_flag(track,LV_OBJ_FLAG_HIDDEN);
  set_color(track,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
  std::array<tile_controls::Key,CLIMATE_MODE_PARTS> modes;
  const unsigned count=tile_controls::climate_bar_keys(t,modes,std::max(0,room));
  const auto seg=climate_tile::segments(cm,bar,(int)count);
  const lv_font_t *glyphs=mini_icon_font?mini_icon_font:w.icon_font;
  bool words=count>0;
  for(unsigned n=0;n<count&&words;++n)
    words=modes[n].command!=tile_controls::HVAC_MODE||seg[n].w>=lv_font_get_line_height(glyphs)+ui::px(large?26:14)+
          text_width(tile_controls::thermostat_mode_text(t,modes[n].arg),w.value_font);
  const unsigned slot=&w-widgets.data();
  const bool ready=fresh()&&t.available()&&!t.waiting(esphome::millis());
  for(unsigned n=0;n<(unsigned)CLIMATE_MODE_PARTS;++n){
    if(n<count)mode_segment(segments[n],parent,slot*16+n,seg[n],modes[n],words,glyphs,w.value_font,ready,t);
    else if(segments[n])lv_obj_add_flag(segments[n],LV_OBJ_FLAG_HIDDEN);
  }
}
inline cover_tile::Layout cover_tile_layout(const Tile &t,tall_tile::Rect body,int touch,int gap,int caption){
  // Capability, not freshness, decides the layout: while HA reconnects the same keys stay, greyed out (ready below).
  if(!tile_controls::cover_tilt_selected(t))return {};
  const auto card=tile_controls::cover_card(t);std::array<tile_controls::Key,3> keys;
  const auto kind=tile_controls::panel_kind(t);
  return cover_tile::layout(body,touch,gap,caption,2*touch,
    kind=="position"&&card.position,kind=="buttons"?tile_controls::keys_for(t,keys):0,
    card.tilt,card.tilt_keys?tile_controls::cover_tilt_keys(t,keys):0);
}
inline void render_cover_tile(Widgets &w,const Tile &t,const cover_tile::Layout &l,int width,int height){
  hide_panel(w);
  // Rebuild only when structure, physical size or theme changes, never for live
  // position updates (which must not interrupt an active drag).
  const int signature=(int)t.supported+(tile_controls::panel_kind(t)=="position"?256:0)+
    (tile_controls::panel_kind(t)=="buttons"?512:0)+(theme::dark?1024:0);
  if(w.extra_mode=="cover_tilt"&&(w.hand_cx!=width||w.hand_cy!=height||w.hand_width!=signature))end_extra(w);
  begin_extra(w,"cover_tilt",width,height);w.hand_cx=width;w.hand_cy=height;w.hand_width=signature;
  const int slot=&w-widgets.data(),gap=ui::px(ui::large()?8:4),touch=std::max(ui::touch_min(),ui::px(ui::large()?48:34));
  const bool ready=fresh()&&t.available()&&!t.waiting(esphome::millis());
  for(int i=0;i<2;++i){
    const auto &g=l.groups[i];if(g.area.empty())continue;
    const float value=i?t.extra().tilt:t.position;
    std::string caption=std::string(tr(i?txt::cover_tilt:txt::cover_position));
    if(g.slider&&std::isfinite(value)){
      const auto with_value=caption+" "+screen_text::percent((int)std::lround(value));
      if(text_width(with_value,w.value_font)<=g.caption.w)caption=with_value;
    }
    auto *label=part_label(w,i,w.value_font,g.caption.x,g.caption.y,g.caption.w,LV_TEXT_ALIGN_CENTER,caption);
    set_color(label,LV_STYLE_TEXT_COLOR,theme::color(theme::MUTED));
    if(g.slider){
      auto *&slider=w.parts[2+i];
      if(!slider)slider=cover_slider(w.extra,g.control.x,g.control.y,g.control.w,g.control.h,value,i,slider_event,nullptr);
      if(captured_slider!=slider)lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround((i?value:100-value)*10):500,LV_ANIM_OFF);
      if(ready)lv_obj_remove_state(slider,LV_STATE_DISABLED);else lv_obj_add_state(slider,LV_STATE_DISABLED);
    }else{
      std::array<tile_controls::Key,3> keys;
      const unsigned count=i?tile_controls::cover_tilt_keys(t,keys):tile_controls::keys_for(t,keys);
      for(unsigned n=0;n<count;++n){
        const int part=4+i*3+n;const auto &k=keys[n];
        media_card::Rect r{g.control.x+(g.horizontal?(int)n*(touch+gap):(g.control.w-touch)/2),g.control.y+(g.horizontal?0:(int)n*(touch+gap)),touch,touch};
        w.parts[part]=media_key(w.extra,w.parts[part],r,k.icon,mini_icon_font?mini_icon_font:w.icon_font,false,false,ready&&!k.disabled,cover_tile_key_event,(void*)(uintptr_t)(slot*8+i*3+n));
        lv_obj_set_ext_click_area(w.parts[part],0);
        set_color(w.parts[part],LV_STYLE_BG_COLOR,lv_color_hex(cover_track()));
        set_color(lv_obj_get_child(w.parts[part],0),LV_STYLE_TEXT_COLOR,lv_color_hex(COVER_ACCENT));
      }
    }
  }
}
// Additional rows extend the existing heading and controls. Compact tiles never
// enter this path. The selected control kind and its events remain authoritative.
// A heading's circle carries the look's icon in the look's proportion (base_circle). On a card too narrow or too short
// for that, the circle may take up to half the width first; below that the icon steps down to the control keys' icon
// font (the same glyphs, smaller), so it never spills out of its circle. No icon font of its own (firmware 0.3.1).
inline const lv_font_t *heading_icon(const Widgets &w,int &circle,int max_side,int width){
  if(circle>=w.base_circle||!mini_icon_font)return w.icon_font;
  circle=std::min({w.base_circle,max_side,width/2});
  return circle>=w.base_circle?w.icon_font:mini_icon_font;
}
// A live camera's picture is the card, on every size: its name at the bottom on the shade the app made there, or
// nothing on it at all. A camera's state ("Idle") says nothing next to its own picture. The name stands where the
// picture will put it while the card waits for it, so the card does not move when the picture comes. False for a
// camera the app has no picture of (or a screen that cannot ask now): the caller then draws the head its size has.
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
  if(t.extra().fav_playing&&t.state=="playing"){action("media_player.media_pause",media_entity(t));return;}
  // No speaker of its own and the player plays nowhere: which speaker first, as a cover in the library asks.
  const auto &x=t.extra();
  if(x.fav_source.empty()&&x.media_source.empty()&&!(t.supported&tile_controls::feature::MEDIA_PLAY_MEDIA)&&!x.media_sources.empty()){
    media_library::speakers(t.entity,0,static_cast<int>(index));
    return;
  }
  if(index<TILES_MAX)favorite_started_at[index]=std::max<uint32_t>(1,esphome::millis());
  library_event("esphome.screen_play",{{"entity",t.entity},{"tile",std::to_string(index)}});
  ESP_LOGI("library","Play favourite %u of %s",(unsigned)index,t.entity.c_str());
  refresh_tile(index);
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
  live_place(w,t,0,0,0);
  const bool photo=w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN),waiting=!photo&&t.pictured()&&live_waiting(t);
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
  live_place(w,t,0,0,0);
  const bool photo=w.picture&&!lv_obj_has_flag(w.picture,LV_OBJ_FLAG_HIDDEN),waiting=!photo&&t.pictured()&&live_waiting(t);
  set_loading(w,waiting,width,height);
  if(!photo&&!waiting)return false;
  // A tall card to style_tall, which gives the name the picture's ink; it only has no parts of its own.
  hide_panel(w);begin_extra(w,"tall",width,height);
  for(auto *part:w.parts)if(part)lv_obj_add_flag(part,LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  // A map carries its name in the picture (on a pill in the card's own colours), so the label only stands in while the
  // picture is on its way.
  lv_obj_add_flag(w.circle,LV_OBJ_FLAG_HIDDEN);set_hidden(w.value,true);set_hidden(w.title,!t.overlay||(photo&&t.is_map()));
  const int name_h=lv_font_get_line_height(w.title_font);
  set_font(w.title,w.title_font);set_text_align(w.title,LV_TEXT_ALIGN_LEFT);
  lv_obj_set_pos(w.title,0,height-name_h);lv_obj_set_size(w.title,width,name_h);
  return true;
}
// False only for a full-page cover whose slat group cannot be drawn here (no tilt, or too little room): the caller
// then draws the ordinary full card with the primary controls, untouched by this function.
inline bool render_tall(Widgets &w,const Tile &t,bool selected,int width,int height) {
  selected=selected&&tile_controls::panel_available(t);
  const bool large=ui::large();const int gap=ui::px(large?8:4);
  const int touch=std::max(ui::touch_min(),ui::px(large?48:34));
  tall_tile::Metrics m{width,height,(int)lv_font_get_line_height(w.title_font),
    (int)lv_font_get_line_height(w.value_font),w.base_circle,gap,ui::touch_min(),ui::control_max_width(),{touch+2,0},selected?1:0};
  auto cover_metrics=m;cover_metrics.row_count=0;
  const auto cover_base=tall_tile::layout(cover_metrics);
  const auto cover=cover_tile_layout(t,cover_base.body,touch,gap,m.state_h);
  if(w.full&&!cover.fits&&!tile_controls::climate_modes_selected(t)){if(w.extra_mode=="cover_tilt")hide_extra(w);return false;}
  if(cover.fits){selected=false;m.row_count=0;}
  auto l=tall_tile::layout(m);
  // An unusual override can leave too little physical room for the selection.
  // Keep the entity heading and its existing detail action rather than clipping keys.
  if(!l.fits){selected=false;m.row_count=0;l=tall_tile::layout(m);}
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  if(!l.fits){hide_extra(w);hide_panel(w);return true;}
  if(t.is_settings()||t.is_page()){
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
      live_place(w,t,a.icon.w,a.icon.x,a.icon.y);
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
  live_place(w,t,circle,0,(l.header.h-circle)/2);
  if(cover.fits){render_cover_tile(w,t,cover,width,height);return true;}
  bool panel=selected&&layout_panel(w,t,large,width,height);
  if(!panel)hide_panel(w);
  if(panel){
    const int pw=lv_obj_get_style_width(w.panel,LV_PART_MAIN),ph=lv_obj_get_style_height(w.panel,LV_PART_MAIN);
    if(pw>width||ph>l.rows[0].h){hide_panel(w);panel=false;}
    else lv_obj_set_pos(w.panel,(width-pw)/2,l.rows[0].y+(l.rows[0].h-ph)/2);
  }
  const auto d=t.domain();
  begin_extra(w,"tall",width,height);
  for(auto *part:w.parts)if(part)lv_obj_add_flag(part,LV_OBJ_FLAG_HIDDEN);
  auto text=[&](int i,const std::string &value,const lv_font_t *font,tall_tile::Rect area,lv_text_align_t align){
    if(value.empty()||area.h<(int)lv_font_get_line_height(font))return false;
    auto *p=part_label(w,i,font,area.x,area.y,area.w,align,value);
    if(d=="media_player"&&i==0)marquee(p,true,live_marquee_ready(w,t));
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
      live_place(w,t,a.icon.w,a.icon.x,a.icon.y);
    }
    return true;
  }
  auto body=l.body;
  if(d=="media_player"){
    const auto &x=t.extra();
    const std::string title=fresh()&&t.available()&&media_card::has_track(t.state)?x.media_title:std::string();
    const lv_font_t *font=room_label?lv_obj_get_style_text_font(room_label,LV_PART_MAIN):w.title_font;
    if(lv_font_get_line_height(font)>body.h)font=w.title_font;
    const int fh=lv_font_get_line_height(font);
    const std::string artist=media_card::subtitle(x.media_artist,x.media_album);
    const bool secondary=!artist.empty()&&body.h>=fh+m.state_h+gap/2;
    int y=body.y+std::max(0,(body.h-fh-(secondary?m.state_h+gap/2:0))/2);
    if(text(0,title,font,{0,y,width,fh},LV_TEXT_ALIGN_LEFT))drop_repeat(title);
    if(secondary)text(1,artist,w.value_font,{0,y+fh+gap/2,width,m.state_h},LV_TEXT_ALIGN_LEFT);
  }else if((d=="climate"||d=="humidifier")&&std::isfinite(t.current)){
    const auto *font=watch_value_font&&lv_font_get_line_height(watch_value_font)<=body.h?watch_value_font:w.value_font;
    text(0,tile_controls::reading_text(t,t.current),font,{0,body.y+std::max(0,(body.h-static_cast<int>(lv_font_get_line_height(font)))/2),width,body.h},LV_TEXT_ALIGN_CENTER);
  }else if(!t.builtin() && fresh() && t.available()){
    const std::string value=d=="light"?light_value_text(t):card_status(t,true);
    const lv_font_t *font=w.value_font;
    for(const auto *candidate:{watch_value_font,w.title_font,w.value_font})
      if(candidate&&face_covers(candidate,value)&&tall_tile::fits_text(body,text_width(value,candidate),lv_font_get_line_height(candidate))){font=candidate;break;}
    if(text(0,value,font,{0,body.y+std::max(0,(body.h-static_cast<int>(lv_font_get_line_height(font)))/2),width,body.h},LV_TEXT_ALIGN_CENTER))
      drop_repeat(value);
  }
  return true;
}
// A favourite that plays now has a ring of the accent (firmware 0.24.0+): the card's own border, drawn over its picture
// along the card's own corners. An outline outside the card left the picture's corners, which the app fills with the
// page's colour, as a light wedge between the ring and the picture. Every other card keeps its hairline under its parts.
inline void ring_favorite(Widgets &w,const Tile &t){
  const bool ringed=t.favorite()&&t.extra().fav_playing;
  set_number(w.tile,LV_STYLE_BORDER_POST,ringed?1:0);
  if(ringed){
    set_number(w.tile,LV_STYLE_BORDER_WIDTH,ui::px(3));
    set_number(w.tile,LV_STYLE_BORDER_OPA,LV_OPA_COVER);
    set_color(w.tile,LV_STYLE_BORDER_COLOR,theme::color(theme::ACCENT));
  }else if(t.favorite()){
    // The palette's own hairline again: the palette pass is skipped while the card's colours stand still.
    set_number(w.tile,LV_STYLE_BORDER_WIDTH,1);
    set_number(w.tile,LV_STYLE_BORDER_OPA,t.transparent?LV_OPA_TRANSP:LV_OPA_COVER);
    set_color(w.tile,LV_STYLE_BORDER_COLOR,lv_color_hex(theme::outline(t.background)));
  }
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
    live_place(w,t,circle,std::max(0,(content_w-circle)/2),top);
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
  live_place(w,t,circle,0,head.circle_y);
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
inline void render_slot(size_t slot) {
  swipe_profile::SlotTimer slot_timer(slot);
  swipe_profile::Lap lap;
  auto &w=widgets[slot];
  if(!w.tile || w.index>=model.count)return;
  const auto &t = model.tiles[w.index];
  auto d=t.domain();
  // A slot is another tile on another page: only a camera card that waits for its picture keeps a spinner.
  if(w.loading&&!(t.live()||t.is_map()||t.favorite()))lv_obj_add_flag(w.loading,LV_OBJ_FLAG_HIDDEN);
  label(w.title, t.name.empty() ? t.entity : t.name);
  label(w.icon, icon_for(t));
  bool watch=t.display=="watch";
  std::string unit=watch?t.unit:"";
  std::string value = t.state;
  // What the second line was set to wins over every word the screen would work out itself (firmware 0.2.90+),
  // but not over the two that say the screen cannot answer: an unavailable entity and a refused tap still say so.
  std::string chosen;
  const bool set_by_hand = chosen_subtitle(t, chosen);
  // Nothing in Home Assistant stands behind a built-in card, so it says its own line with the link down too.
  if (t.is_settings() || t.is_page())
    value = set_by_hand ? chosen
          : t.is_settings() ? std::string(tr(txt::tile_tap_to_open))
          : fill(txt::tile_page, "n", t.page_target());
  else if (!fresh() || !t.available()) value = tr(txt::ha_unavailable);
  else if (t.refused_at && esphome::millis() - t.refused_at < 4000) value = tr(t.unanswered ? txt::tile_no_answer : txt::tile_refused);
  else if (set_by_hand) value = chosen;
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
  if(d=="vacuum" && std::isfinite(t.battery)){value_tail=" / "+screen_text::percent((int)t.battery);value+=value_tail;}
  // A humidifier's humidity stays readable when its action word does not fit ("Humidif… · 38%").
  if(d=="humidifier" && fresh() && t.available() && std::isfinite(t.current) && !set_by_hand)value_tail=" · "+tile_controls::humidity_text(t.current);
  // Direct controls: only a wide card in the standard layout has room for the panel.
  // A small slider on a double-width card is that panel's slider: it stands beside the name, where every other
  // control of a wide card stands and where the editor's mockup draws it. A single card keeps the strip under
  // its head (mini below), and so does a wide card too narrow for a panel.
  const bool taller=t.row_span()>1 && !w.full;
  const bool inline_panel=(w.wide||taller) && !w.full && t.inline_control=="slider" && !tile_controls::inline_kind(d).empty();
  bool with_panel=(w.wide||taller) && !t.builtin() && !watch && fresh() && t.available() &&
                  (inline_panel || (!t.controls.empty() && t.inline_control!="slider"));
  // A panel needs its own width plus the icon and some name; a narrow wide card stays a plain card. What it
  // needs is what it takes: the cell its controls fill (layout_panel), or the toggle and the run key their own
  // width.
  if(with_panel && !w.full && !taller){
    const bool lt=ui::large();
    const PanelMetrics pm=panel_metrics(lt);
    const std::string kind=tile_controls::panel_kind(t);
    const int panel_need=kind=="toggle"?pm.toggle_w:kind=="run"?pm.key_w*3/2:cell_content_width(w);
    if(content_width(w)<panel_need+pm.text_gap+ui::px(lt?54:36)+ui::px(60))with_panel=false;
  }
  // A wide card with a panel says what its control is doing, unless the second line was set by hand.
  if(with_panel && !set_by_hand){std::string status=tile_controls::status_text(t);if(!status.empty()){value=status;value_short.clear();value_tail.clear();}}
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
  bool custom=clock||forecast||sunpath||bedside;
  if(!large_tile)pad_vertical(w.tile,watch||custom||graph?2:4);
  // A big value that stepped up to the setpoint's digits (the watch block below) keeps them until that block
  // decides again, so a card is not restyled twice a render.
  if(!(watch && setpoint_font && lv_obj_get_style_text_font(w.value,LV_PART_MAIN)==setpoint_font))
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
  if(!w.key)set_hidden(w.icon,false);  // a key that showed a value hid its icon
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
  }else if((t.live()||t.is_map())&&render_camera_card(w,t,content_w,content_h)){
    lap(swipe_profile::GEOMETRY);
  }else if(t.favorite()&&render_favorite_card(w,t,content_w,content_h)){
    label(w.value,value);
    lap(swipe_profile::GEOMETRY);
  }else if((taller||(w.full&&(tile_controls::cover_tilt_selected(t)||tile_controls::climate_modes_selected(t))))&&!custom&&!watch&&!graph&&
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
    center_icon(w.icon);live_place(w,t,circle,(content_w-circle)/2,top);
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
  live_place(w,t,circle_size,0,circle_y);
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
  if(mini){lv_obj_remove_flag(w.slider,LV_OBJ_FLAG_HIDDEN);if(!lv_obj_has_state(w.slider,LV_STATE_PRESSED) && lv_slider_get_value(w.slider)!=slider_value(t))lv_slider_set_value(w.slider,slider_value(t),LV_ANIM_OFF);}
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
  const uint32_t paint=t.background|(t.transparent?1u<<24:0);
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
  press_ground(w.tile,letterboxed(w)?theme::color(theme::CAMERA_PAGE):lv_color_hex(theme::surface(t.background)));
  set_number(w.tile,LV_STYLE_BORDER_WIDTH,1);
  // "Background: none" hides only the card; geometry and padding stay identical, and the press still shows because
  // it lives on the PRESSED state: a shade of what the finger sees, the page there, the card everywhere else.
  set_color(w.tile,LV_STYLE_BG_COLOR,lv_color_hex(theme::pressed(t.transparent ? theme::hex(theme::PAGE) : theme::surface(t.background))),LV_STATE_PRESSED);
  set_number(w.tile,LV_STYLE_BG_OPA,t.transparent&&!letterboxed(w) ? LV_OPA_TRANSP : LV_OPA_COVER);
  set_number(w.tile,LV_STYLE_BORDER_OPA,t.transparent ? LV_OPA_TRANSP : LV_OPA_COVER);
  set_color(w.tile,LV_STYLE_BORDER_COLOR,lv_color_hex(theme::outline(t.background)));
  set_color(w.circle,LV_STYLE_BG_COLOR,circle_color);
  set_color(w.icon,LV_STYLE_TEXT_COLOR,icon_color);
  // A key is its circle: the card takes the circle's colour and its press, with no border (firmware 0.8.0+).
  if(w.key){
    set_color(w.tile,LV_STYLE_BG_COLOR,circle_color);
    set_color(w.tile,LV_STYLE_BG_COLOR,lv_color_hex(theme::pressed(available?theme::tint(state_color,38):theme::hex(theme::TRACK))),LV_STATE_PRESSED);
    set_number(w.tile,LV_STYLE_BG_OPA,LV_OPA_COVER);set_number(w.tile,LV_STYLE_BORDER_OPA,LV_OPA_TRANSP);
  }
  auto title_color=theme::color(theme::INK);
  auto value_color=theme::color(w.key ? theme::INK : t.background ? theme::SLATE : theme::MUTED);
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
  else for(unsigned i=0;i<w.parts.size() && w.extra_mode!="media" && w.extra_mode!="tall" && w.extra_mode!="cover_tilt" && w.extra_mode!="forecast" && w.extra_mode!="forecast_rows" && w.extra_mode!="favorite";++i){
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
// The minute turned or a display setting changed (packages/core.yaml says so before its refresh): every card on the
// glass is drawn, as for a refresh that names nothing, and on a kept page the cards that show the time (firmware 0.3.2+).
inline bool dirty_time=false;
// A card whose text or drawing moves on with the clock: a clock, a timer, the sun's arc, a graph's window, a playing
// track's bar, "5 min ago" under a script or a scene, and a second line that names a moment. A forecast changes with
// its entity, which Home Assistant updates on its own.
inline bool shows_time(const Tile &t) {
  const std::string d=t.domain();
  return t.is_clock() || t.is_bedside() || t.display=="graph" || t.extra().subtitle_at || d=="timer" || d=="sun" ||
         (d=="media_player" && media_card::playing(t.state)) ||
         d=="script" || d=="scene" || d=="button" || d=="input_button" || d=="automation";
}
inline void mark_time() {
  dirty_time=true;
  for(size_t i=0;i<model.count;++i)if(shows_time(model.tiles[i]))changes.mark_tile(i);
}
// The page whose cells are placed right now, -1 before the first one. It lives here and not beside show_page
// because the top bar reads it: a page with a title of its own says that title (Model::title_of), so render()
// has to know which page it is drawing.
inline int applied_page=-1;
inline void mark_all() { dirty_all=true; changes.mark_all(); }
inline void mark_tile(size_t index) { changes.mark_tile(index); if(index<dirty_tiles.size())dirty_tiles.set(index); else dirty_all=true; }
inline void refresh_tile(size_t index) { mark_tile(index); if(refresh)refresh(); }
inline void refresh_header_only() { dirty_header=true; if(refresh)refresh(); }
inline void refresh_all() { mark_all(); if(refresh)refresh(); }
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
inline lv_obj_t *boot_facts = nullptr, *boot_hint = nullptr, *boot_qr = nullptr;
inline void boot_status(lv_obj_t *page, const char *text, bool waiting = true, bool cover = false,
                        const std::string &facts = std::string(), const std::string &hint = std::string(),
                        const std::string &qr = std::string()) {
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
  const int text_h = height(text, font);
  const int facts_h = facts.empty() ? 0 : line_gap + height(facts.c_str(), note_font);
  const int hint_h = hint.empty() ? 0 : gap + height(hint.c_str(), note_font);
  int brand = boot_brand ? lv_obj_get_height(boot_brand) : 0, brand_gap = boot_brand ? 2 * gap : 0;
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
  const int block = brand + brand_gap + text_h + facts_h + hint_h + qr_h + (waiting ? gap + ring : 0);
  int top = -block / 2;
  if (boot_brand) { lv_obj_align(boot_brand, LV_ALIGN_CENTER, 0, top + brand / 2); top += brand + brand_gap; }
  lv_obj_align(boot_text, LV_ALIGN_CENTER, 0, top + text_h / 2);
  top += text_h;
  if (facts_h) { lv_obj_align(boot_facts, LV_ALIGN_CENTER, 0, top + line_gap + (facts_h - line_gap) / 2); top += facts_h; }
  if (hint_h) { lv_obj_align(boot_hint, LV_ALIGN_CENTER, 0, top + gap + (hint_h - gap) / 2); top += hint_h; }
#if LV_USE_QRCODE
  if (qr_h && boot_qr) { lv_obj_align(boot_qr, LV_ALIGN_CENTER, 0, top + gap + (qr_h - gap) / 2); top += qr_h; }
#endif
  top += gap;
  if (boot_spinner) lv_obj_align(boot_spinner, LV_ALIGN_CENTER, 0, top + ring / 2);
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
  boot_panel = boot_text = boot_spinner = boot_brand = boot_version = boot_facts = boot_hint = boot_qr = nullptr;
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
enum class BootStep : uint8_t { wifi, address, home_assistant, tessera, tiles };
struct BootView { std::string title, facts, hint; };
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
inline BootView boot_view(uint32_t now) {
  const auto link = wifi_status::link();
  const BootStep step = link.wifi && !link.connected ? (link.joined ? BootStep::address : BootStep::wifi)
                      : !ha_connected() ? BootStep::home_assistant
                      : transfer.begun ? BootStep::tiles : BootStep::tessera;
  if (step != boot_step || !boot_step_since) { boot_step = step; boot_step_since = now ? now : 1; }
  const uint32_t waited = now - boot_step_since;
  BootView view;
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
    const auto view = boot_view(esphome::millis());
    boot_status(lv_obj_get_parent(room), view.title.c_str(), true, false, view.facts, view.hint);
  }
  else if (preparing.foreground) prepare_status();
  else if (boot_panel) boot_forget();
  name_label(room, !model.configured ? std::string() : !model.ready() ? tr(txt::status_loading_tiles) : !ha_connected() ? tr(txt::status_ha_not_connected) : !feed_alive() ? tr(txt::status_manager_not_active) : model.title_of(applied_page));
  render_header();
  lap(swipe_profile::HEADER);
  // A refresh that names nothing draws every card (and counts as a change of everything); the minute tick says it is
  // only the time (dirty_time).
  if(!dirty_all && dirty_tiles.none() && !dirty_header && !dirty_time)mark_all();
  const bool all=dirty_all || dirty_time;
  const uint32_t upto=changes.last;  // every change asked for so far is drawn below, for the cards on the glass
  const TileSet tiles=dirty_tiles;
  dirty_all=dirty_header=dirty_time=false;dirty_tiles.reset();
  for (size_t slot = 0; slot < grid.slots(); ++slot) {
    const auto &w=widgets[slot];
    if(w.index>=model.count)continue;
    if(all || tiles.test(w.index))render_slot(slot);
  }
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
    bool custom=lv_obj_has_flag(w.title,LV_OBJ_FLAG_HIDDEN);
    const bool extended=w.index<model.count&&model.tiles[w.index].row_span()>1&&!w.full&&(w.extra_mode=="tall"||w.extra_mode=="cover_tilt");
    bool fits=true;
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
      // A wide card is two cells of its row plus the gap between them.
      const int gap=lv_obj_get_style_pad_column(tile_grid,LV_PART_MAIN);
      // Two of the columns' free units: LVGL shares the room exactly and rounds each track, so the sum is rounded once.
      const int room=lv_obj_get_content_width(tile_grid)-(int)(grid.columns-1)*gap;
      int expected=(2*room+(int)grid.columns/2)/(int)grid.columns+gap;
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
        fits=fits&&a.x1>=content.x1&&a.x2<=content.x2&&a.y1>std::max(title.y2,value.y2)&&a.y2<=content.y2;
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
    const bool dial=w.extra_mode=="calendar" || w.extra_mode=="analog" || w.extra_mode=="calm" || w.extra_mode=="flip" || w.extra_mode=="digital" || w.extra_mode=="bedside";
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
    if(w.index<model.count && model.tiles[w.index].background){
      bool palette_ok=lv_color_eq(lv_obj_get_style_bg_color(w.tile,LV_PART_MAIN),lv_color_hex(theme::surface(model.tiles[w.index].background))) &&
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
// What a page key shows: its chevron. Not its first child: since firmware 0.3.1 that is the press patch behind the
// chevron (nav_key_patch), which made the chevron keep full ink on the first and last page (fixed in firmware 0.3.2).
inline lv_obj_t *nav_glyph(lv_obj_t *key) {
  for (uint32_t i = 0; key && i < lv_obj_get_child_count(key); ++i) {
    auto *child = lv_obj_get_child(key, i);
    if (child != nav_back_label && lv_obj_check_type(child, &lv_label_class)) return child;
  }
  return nullptr;
}
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
      set_cell(w.tile,column,span_x,row,span_y);
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
  const int previous=detail?navigation_history.target(model.page_data,page):model.page_data.step(page,-1);
  if(previous==page)lv_obj_add_state(nav_prev,LV_STATE_DISABLED);else lv_obj_remove_state(nav_prev,LV_STATE_DISABLED);
  if(model.page_data.step(page,1)==page)lv_obj_add_state(nav_next,LV_STATE_DISABLED);else lv_obj_remove_state(nav_next,LV_STATE_DISABLED);
  for(auto *control:{nav_prev,nav_next})if(auto *chevron=nav_glyph(control))
    set_number(chevron,LV_STYLE_TEXT_OPA,lv_obj_has_state(control,LV_STATE_DISABLED)?LV_OPA_30:LV_OPA_COVER);
  // The dots between the two chevrons (firmware 0.2.69+): the page on screen in ink.
  if(sequential && nav_number)settings_screen::page_dots(nav_number,model.page_data.ordinal(page),sequential_count,ui::large());
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
  if(room_label){mark_all();render(room_label);}else refresh_all();
}
// A page key takes touches across its half of the bar, which runs under the page dots; its press shows as a rounded
// patch around what the key shows (the chevron, or "Back") instead of across that whole half (firmware 0.3.1).
// The inked box of what a label shows: for a lone icon the glyph's own box from the font, since the label's box
// carries the font's side bearings and line gap and a patch centred on it would sit off the chevron.
inline lv_area_t ink_area(lv_obj_t *o){
  lv_area_t a;lv_obj_get_coords(o,&a);
  if(!lv_obj_check_type(o,&lv_label_class))return a;
  const char *text=lv_label_get_text(o);if(!text||!*text)return a;
  const std::string shown(text);size_t i=0;const uint32_t cp=header_bar::next_codepoint(shown,i);
  if(i!=shown.size()||cp<0xF0000)return a;  // words ("Back") keep their label box
  const lv_font_t *font=lv_obj_get_style_text_font(o,LV_PART_MAIN);lv_font_glyph_dsc_t g;
  if(!font||!lv_font_get_glyph_dsc(font,&g,cp,0)||!g.box_w||!g.box_h)return a;
  const int32_t top=a.y1+(font->line_height-font->base_line)-(int32_t)g.box_h-g.ofs_y,left=a.x1+g.ofs_x;
  return lv_area_t{left,top,left+(int32_t)g.box_w-1,top+(int32_t)g.box_h-1};
}
inline void nav_key_event(lv_event_t *e){
  auto *key=(lv_obj_t*)lv_event_get_current_target(e);auto *patch=(lv_obj_t*)lv_event_get_user_data(e);
  const auto code=lv_event_get_code(e);
  if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST){lv_obj_add_flag(patch,LV_OBJ_FLAG_HIDDEN);return;}
  if(code!=LV_EVENT_PRESSED)return;
  // Around everything the key shows: the chevron, and "Back" beside it on a detail page.
  lv_area_t k,c{};bool any=false;lv_obj_get_coords(key,&k);
  for(uint32_t i=0;i<lv_obj_get_child_count(key);++i){
    auto *child=lv_obj_get_child(key,i);
    if(child==patch||lv_obj_has_flag(child,LV_OBJ_FLAG_HIDDEN))continue;
    const lv_area_t a=ink_area(child);
    if(!any){c=a;any=true;}else{c.x1=std::min(c.x1,a.x1);c.y1=std::min(c.y1,a.y1);c.x2=std::max(c.x2,a.x2);c.y2=std::max(c.y2,a.y2);}
  }
  if(!any)return;
  // A circle around a lone chevron, a pill around chevron and word; never taller than the bar.
  const int pad=ui::px(ui::large()?14:10),bar=(int)lv_area_get_height(&k),iw=(int)lv_area_get_width(&c),ih=(int)lv_area_get_height(&c);
  const int h=std::min(bar-ui::px(4),std::max(iw,ih)+2*pad),w=std::max(h,iw+2*pad);
  const int cx=(int)(c.x1+c.x2+1)/2-(int)k.x1,cy=(int)(c.y1+c.y2+1)/2-(int)k.y1;
  lv_obj_set_size(patch,w,h);lv_obj_set_pos(patch,cx-w/2,cy-h/2);
  lv_obj_remove_flag(patch,LV_OBJ_FLAG_HIDDEN);
}
inline void nav_key_patch(lv_obj_t *key){
  if(!key)return;
  auto *patch=lv_obj_create(key);lv_obj_remove_style_all(patch);
  lv_obj_remove_flag(patch,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(patch,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(patch,LV_OBJ_FLAG_IGNORE_LAYOUT);lv_obj_add_flag(patch,LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_style(patch,theme::style(theme::Paint::page_pressed),0);lv_obj_set_style_bg_opa(patch,LV_OPA_COVER,0);
  lv_obj_set_style_radius(patch,LV_RADIUS_CIRCLE,0);
  lv_obj_move_to_index(patch,0);  // behind the chevron
  for(auto code:{LV_EVENT_PRESSED,LV_EVENT_RELEASED,LV_EVENT_PRESS_LOST})lv_obj_add_event_cb(key,nav_key_event,code,patch);
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
    sum += tile_memory::cost(tile_memory::domain_of(t.entity), tile_memory::own_action(t.tap), tile_memory::own_line(t.subtitle), board);
  }
  // And its pages: a page's title, and each item of its top bar that shows an entity (a text or a moment).
  for (const auto &page : model.page_data.records) {
    unsigned entities = 0;
    for (size_t i = 0; i < page.bar.count && i < page.bar.items.size(); ++i)
      entities += page.bar.items[i].kind == header_bar::Kind::text || page.bar.items[i].kind == header_bar::Kind::ago;
    sum += tile_memory::page_cost(entities, board);
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
// One sample a minute, and only with a whole layout in place: halfway through a transfer the heap says nothing.
inline void sample_memory(uint32_t now) {
  if (!heap_room || (memory_window.count && now - memory_sampled_at < 60000)) return;
  if (transfer.begun && !transfer.active) return;
  memory_sampled_at = now;
  memory_window.add(tile_memory::room(heap_room() + spare_tiles(), layout_cost()));
}
inline size_t memory_room(uint32_t now) { sample_memory(now); return memory_window.least(); }
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
  memory_short_at = std::max<uint32_t>(1, esphome::millis());
  refresh_all();
}
// The reply to a hello or a ping carries the memory figures (packages/core.yaml); a tile's state does not need them.
inline bool reply_memory = false;

// PSRAM another kept page may never take: the pictures (picture_store.h), a camera full screen and an alert's picture
// live there too. Measured on the 4-inch Guition (2026-09-26): about 5.6 MB of its 8 MB are free with a layout loaded.
constexpr size_t KEEP_RESERVE = 2u << 20;
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
// A kept set the board no longer needs (fewer pages, or a smaller limit) goes, cards and all.
inline void release_kept(size_t from) {
  for (size_t i = from; i < kept_sets.size(); ++i) {
    if (!kept_sets[i]) continue;
    for (auto &w : *kept_sets[i]) if (w.tile) lv_obj_delete(w.tile);
    kept_sets[i]->~CardSet();
    kept_free(kept_sets[i]);
    kept_sets[i] = nullptr;
    shelf.entries[i] = kept_pages::Shelf::Entry{};
  }
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
inline void forget_kept() {
  shelf.forget();
  for (auto *set : kept_sets) if (set) for (auto &w : *set) { w.index = grid.max_tiles(); w.cached_active = -1; }
}
// A page key's chevron with its ink on the tiles' margin (firmware 0.14.0+), the line the top bar and the cards keep
// from the side of the glass, measured from the glyph itself so the font's side bearing does not push it inward.
inline void nav_align(lv_obj_t *key,bool left){
  auto *chevron=nav_glyph(key);if(!chevron)return;
  const lv_font_t *font=lv_obj_get_style_text_font(chevron,LV_PART_MAIN);lv_font_glyph_dsc_t g;
  if(!font||!lv_font_get_glyph_dsc(font,&g,left?0xF0141:0xF0142,0)||!g.box_w)return;
  lv_obj_set_x(chevron,left?grid_margin-g.ofs_x:-(grid_margin-(int(g.adv_w)-g.ofs_x-int(g.box_w))));
}
inline void show_page(int &page, lv_obj_t *previous, lv_obj_t *next, lv_obj_t *number) {
  if(!nav_prev){nav_key_patch(previous);nav_key_patch(next);}
  if(!nav_prev){nav_align(previous,true);nav_align(next,false);}
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
  // The page bar was set for the other page and back: drawn again, the rest of the glass never changed.
  if (nav_prev && lv_obj_get_parent(nav_prev)) lv_obj_invalidate(lv_obj_get_parent(nav_prev));
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
inline bool prepared_once = false;  // the first layout since the start was prepared on screen
inline uint32_t prepare_built_at = 0, last_freshen = 0;
inline void prepare_done() {
  const bool shown = preparing.foreground;
  preparing.active = preparing.foreground = false;
  if (preparing.timer) lv_timer_set_period(preparing.timer, 300);  // from now on: kept pages up to date, when idle
  ESP_LOGI("kept", "pages prepared: %u of %u, PSRAM free %u B", preparing.done, preparing.total, (unsigned) psram_free());
  // The render takes the "Preparing pages" screen away; the header alone, as nothing on the cards changed.
  if (shown) { prepared_once = true; refresh_header_only(); }
}
inline void prepare_step(lv_timer_t *) {
  if (protocol_problem != ProtocolProblem::none || !transfer.active || !model.ready()) return;
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
// A layout was applied: build its other pages, the first time since the start on screen, afterwards in
// the background; from then on kept pages are brought up to date while the screen is idle. A board that keeps no
// pages (the CYD) builds each page when it is shown, as before.
inline void prepare_start() {
  const unsigned pages = page_count();
  if (!room_label || applied_page < 0 || pages < 2 || !kept_capacity()) return;
  preparing.active = true;
  preparing.foreground = !prepared_once;
  preparing.done = 0;
  preparing.total = pages - 1;
  prepare_built_at = 0;
  if (!preparing.timer) preparing.timer = lv_timer_create(prepare_step, 10, nullptr);
  lv_timer_set_period(preparing.timer, preparing.foreground ? 10 : 300);
  lv_timer_reset(preparing.timer);
  ESP_LOGI("kept", "preparing %u pages %s", preparing.total, preparing.foreground ? "before the first page opens" : "in the background");
  if (preparing.foreground) prepare_status();
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
inline void tick() {
  // The network lost or found again changes the whole glass: the Wi-Fi message over everything, or the pages back.
  static bool wifi_shown = false;
  if (const bool shown = wifi_status::problem().shown; shown != wifi_shown) {
    wifi_shown = shown;
    if (shown) ESP_LOGW("wifi_status", "No Wi-Fi: the glass says how to fix it");
    else ESP_LOGI("wifi_status", "Wi-Fi back: the pages again");
    if (room_label) { mark_all(); render(room_label); } else refresh_all();
  }
  if(detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) && detail_index<model.count){
    auto &t=model.tiles[detail_index];bool waiting=t.loading(esphome::millis());
    // The history the card waits for: drawn once it is here (a finger on the screen holds that back), asked for
    // again every 30 s, and after 8 s without it (an app from before 0.2.59, Home Assistant away) the card says so.
    if(history_chart.status&&!history_chart.ready){
      const uint32_t now=esphome::millis();
      if(history_fits(t))refresh_detail(detail_index);
      else if(now-history_asked_at>30000)history_request(t.entity,history_hours);
      else if(now-history_asked_at>8000)label(history_chart.status,tr(txt::history_unavailable));
    }
    for(unsigned i=0;i<detail_action_count;++i){if(waiting||!fresh()||!t.available())lv_obj_add_state(detail_actions[i],LV_STATE_DISABLED);else lv_obj_remove_state(detail_actions[i],LV_STATE_DISABLED);}
    std::string status=waiting?std::string(tr(t.confirmed?txt::tile_confirmed:txt::tile_command_sent)):card_status(t,detail_status_brief);
    if(detail_status)label(detail_status,waiting?status:screen_text::with_unit(status,t.unit));
    // The vacuum card lays its state out with the room and battery beside it, so a new text draws the
    // card again; once Home Assistant answered, the new state says enough.
    if(detail_badge_status && t.domain()=="vacuum"){
      status=waiting && !t.confirmed?std::string(tr(txt::tile_command_sent)):detail_state(t);
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
    else if(esphome::millis()-failed_at>5000){failed_at=0;ota_status::now={};ota_forget();refresh_all();}
  }
  // The starting screen follows every step as it happens (firmware 0.38.0): drawn again whenever what it says changes,
  // the seconds of a step that takes long included.
  if(room_label && !model.configured && model.refusal.empty() && protocol_problem==ProtocolProblem::none && !wifi_shown){
    static std::string said;
    const auto view=boot_view(esphome::millis());
    std::string now_said=view.title+'\x1f'+view.facts+'\x1f'+view.hint;
    if(now_said!=said || !boot_panel){said=std::move(now_said);boot_status(lv_obj_get_parent(room_label),view.title.c_str(),true,false,view.facts,view.hint);}
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
        if(kind!=header_bar::Kind::wifi && kind!=header_bar::Kind::battery)continue;
        const auto now_shown=header_bar::device_item(bar->items[i],device);
        now_said+=std::to_string(now_shown.shown)+':'+std::to_string(now_shown.icon)+':'+now_shown.text+'\x1f';
      }
      if(now_said!=said){said=std::move(now_said);refresh_header_only();}
    }
  }
  media_library::tick(esphome::millis());
  // Only the cards that change are drawn again: a clock or a finished command redraws its own card.
  bool redraw=false;
  auto card=[&](size_t index){ mark_tile(index); redraw=true; };
  // HA dropping or returning and the feed timing out change every card at once.
  bool now_fresh=fresh();
  if(now_fresh!=was_fresh){was_fresh=now_fresh;mark_all();redraw=true;}
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
    if(!t.pending || t.waiting(esphome::millis()) || t.tap_held(esphome::millis()))continue;
    // A vacuum chip Home Assistant never confirmed goes back to what the robot reports.
    bool sent=false;if(auto *x=t.extra_ptr())for(auto &c:x->choices)sent=sent||!c.sent.empty();
    end_wait(i);card(i);
    if(sent)refresh_detail(i);
  }
  // A -/+ edit goes out as one call once the finger rests; a value HA never reports is dropped after a while.
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];if(!std::isfinite(t.edit_value)&&!std::isfinite(t.edit_high))continue;
    uint32_t now=esphome::millis();
    if(!t.edit_sent){
      if(now-t.edit_since<700 || t.waiting(now))continue;
      auto a=tile_controls::edit_action(t,t.edit_value);
      if(a.valid()){t.edit_sent=true;t.edit_since=now;action(a.service,t.entity,a.key,a.value,true,a.key2,a.value2);}else{t.edit_value=NAN;t.edit_high=NAN;}
    }else if(now-t.edit_since>10000){t.edit_value=NAN;t.edit_high=NAN;card(i);}
  }
  // Running timers advance once per second without any HA traffic; clocks show hours and minutes,
  // so they are drawn again only when the minute (or the time's validity) changes.
  uint32_t second=esphome::millis()/1000;
  if(second!=last_live_second){
    last_live_second=second;
    // The media card's bar runs on while the track plays (firmware 0.2.64+).
    // A cover that waited for its ground long enough is asked for without it.
    if(media_ground_pending && detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) && detail_index<model.count &&
       esphome::millis()-media_ground_since>=MEDIA_GROUND_WAIT_MS)refresh_detail(detail_index);
    if(media_progress_fill && !media_seeking && detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) && detail_index<model.count){
      const auto &t=model.tiles[detail_index];
      media_bar_at(media_elapsed(t),t.extra().media_duration,media_progress_fill,media_elapsed_label,media_bar_width);
    }
    auto now=now_time?now_time():esphome::ESPTime{};
    int minute=now.is_valid()?now.day_of_year*1440+now.hour*60+now.minute:-1;
    bool new_minute=minute!=last_clock_minute;last_clock_minute=minute;
    for(size_t slot=0;slot<grid.slots();++slot){
      auto &w=widgets[slot];if(!w.tile || w.index>=model.count || lv_obj_has_flag(w.tile,LV_OBJ_FLAG_HIDDEN))continue;
      const auto &t=model.tiles[w.index];
      if(((t.is_clock() || t.is_bedside()) && new_minute) || (t.domain()=="timer" && t.state=="active") || (t.domain()=="sun" && second%60==0))card(w.index);
      // An alarm's delay counts down on its tile; its heartbeat stops while the screen sleeps and starts when it wakes.
      if(t.domain()=="alarm_control_panel"){if(alarm_left(t))card(w.index);alarm_tile_look(slot,&t);}
      if(t.domain()=="lock")alarm_tile_look(slot,&t);
      // A favourite whose start never came stops saying it starts (firmware 0.24.0+).
      if(t.favorite()&&w.index<TILES_MAX&&favorite_started_at[w.index]&&!favorite_starting(w.index,t))card(w.index);
      // A media tile over the whole page: its bar runs on while the track plays (firmware 0.2.64+).
      if(w.extra_mode=="media" && w.extra && !lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN) && w.parts[5] && !lv_obj_has_flag(w.parts[5],LV_OBJ_FLAG_HIDDEN))media_progress(t,w.parts[5],w.parts[6],w.media_bar_w);
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
    settings_screen::page_dots(nav_number, model.page_data.ordinal(applied_page), model.page_data.count(), ui::large());
  header_renderer.restyle();
  if (room_label) { mark_all(); render(room_label); }
  if (detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN) && detail_index < model.count) show_detail(detail_index);
  media_library::restyle();
}
inline std::string vacuum_option(unsigned index) {
  if (active_index < 0 || static_cast<size_t>(active_index) >= model.count) return {};
  auto &tile = model.tiles[active_index];
  const auto &speeds = tile.extra().fan_speeds;
  return index < speeds.size() ? speeds[index] : "";
}
}

// ---- Camera images (firmware 0.2.57+) ----
// A camera or image tile, and an alert's image, open the camera full screen: the image as large as fits, the round back
// key at the top left like on every card, the name beside it. ESP Screen Manager fetches the snapshot, sizes it for this
// screen and serves it on its own port; camera_view::Feed decides when to ask for a link and when to load it again. The
// board binds the two online_images (the full view and the alert's frame) through ImageHooks; a board without them (the
// CYD) never opens the view. Nothing here exists while no camera is open, apart from the alert's small frame.
namespace runtime_tiles {
struct ImageHooks {
  std::function<void(const std::string &)> load;  // set the online_image's URL and download it
  std::function<void()> release;                  // free the decoded image
  std::function<lv_image_dsc_t *()> source;       // the decoded image for LVGL
};
inline ImageHooks camera_full, camera_thumb;
inline camera_view::Feed camera;
// What a picture costs this board (firmware 0.2.83+). Every picture goes the same way: the app sends a BMP of
// exactly the pixels the screen asked for and online_image decodes it to RGB565, so the room it takes is
// `width * height * 2`. ESPHome's RAMAllocator asks for that with PREFER_INTERNAL, which means a picture small
// enough to fit inside the chip takes memory the Wi-Fi link, the API and LVGL also want; a larger one lands in
// PSRAM and costs nothing inside. Which is why the number that decides a board's picture sizes is not how much
// PSRAM it has, but what one load does to both heaps. One line per stage of one load, for every kind of picture,
// so the four boards can be compared with the same instrument.
// `pixels` is what the picture holds when the screen knows it (a cover asks for its own square), 0 when only the
// app knows (a camera's box comes from the board shape); then only the heaps are worth reading.
// Free sizes only, no largest block (firmware 0.3.2+): finding the largest block walks every block of that heap with
// its lock held and the interrupts of this core off. On the 4-inch Guition a walk of the PSRAM took 1.7 ms with one
// page built and 2.3 ms with eight (2026-09-26, 3,300 and 4,600 blocks), while the RGB panel's bounce buffer is
// refilled by an interrupt on this core every 0.34 ms: every picture that loaded shifted a frame on the glass.
inline void picture_memory(const char *stage, const char *what, int pixels) {
#ifdef USE_ESP32
  ESP_LOGI("picture", "%s %s: %d px wants %d B; inside free=%u, psram free=%u", stage, what, pixels, pixels * 2,
           (unsigned) heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned) heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
#else
  (void) stage; (void) what; (void) pixels;
#endif
}
// Freeing the image waits for the next tick: ending a download under way can take a few hundred ms, and Back should
// show the page below at once.
inline bool camera_release_due = false;
inline lv_obj_t *camera_root = nullptr, *camera_picture = nullptr, *camera_note = nullptr, *camera_back = nullptr, *camera_title = nullptr;
// Turns in the middle until the first image is there (firmware 0.2.73+); a note (no image) takes its place.
inline lv_obj_t *camera_spinner = nullptr;
// The alert's image: the frame across the top of the card (features/camera.yaml), the camera the app announced for the
// next alert and the one the card on screen shows.
inline lv_obj_t *alert_frame = nullptr, *alert_picture = nullptr, *alert_frame_icon = nullptr;
// The parts of the alert card the shared tree draws (packages/core.yaml binds them at boot); alert_place puts them.
struct AlertParts {
  lv_obj_t *card = nullptr, *icon = nullptr, *title = nullptr, *subtitle = nullptr, *button = nullptr;
  lv_obj_t *label = nullptr, *button2 = nullptr, *label2 = nullptr;  // the words on the button, the second button (0.3.3+)
};
inline AlertParts alert_parts;
// Whether the alert on screen has a second button (show_alert_choice, firmware 0.3.3+); alert_show sets it.
inline bool alert_two_buttons = false;
// A button in a key colour of its own (theme::KEY_SWATCHES), or back to its paint for 0.
inline void alert_key(lv_obj_t *button, lv_obj_t *label, uint32_t key) {
  if (!button) return;
  if (!key) {
    lv_obj_remove_local_style_prop(button, LV_STYLE_BG_COLOR, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_remove_local_style_prop(button, LV_STYLE_BG_COLOR, LV_PART_MAIN | LV_STATE_PRESSED);
    if (label) lv_obj_remove_local_style_prop(label, LV_STYLE_TEXT_COLOR, LV_PART_MAIN | LV_STATE_DEFAULT);
    return;
  }
  lv_obj_set_style_bg_color(button, theme::rgb(key), LV_PART_MAIN | LV_STATE_DEFAULT);
  lv_obj_set_style_bg_color(button, theme::rgb(theme::key_pressed(key)), LV_PART_MAIN | LV_STATE_PRESSED);
  if (label) lv_obj_set_style_text_color(label, theme::rgb(theme::key_text(key)), LV_PART_MAIN | LV_STATE_DEFAULT);
}
// Lays the alert card out on this screen's glass (screen_alert::layout, firmware 0.2.103+), with room for a picture of
// `aw` x `ah` proportions or without one: at boot, when an alert comes (with a picture's frame of a camera's 16:9 until
// the picture is there), and once more when the picture arrives, for that picture's own proportions.
inline screen_alert::Layout alert_place(bool image, int aw = screen_alert::PICTURE_W, int ah = screen_alert::PICTURE_H) {
  const auto &p = alert_parts;
  if (!p.card || !p.icon || !p.title || !p.subtitle || !p.button) return {};
  const auto l = screen_alert::layout(overlay_card::screen_width(), overlay_card::screen_height(),
                                      lv_font_get_line_height(lv_obj_get_style_text_font(p.title, LV_PART_MAIN)),
                                      lv_font_get_line_height(lv_obj_get_style_text_font(p.subtitle, LV_PART_MAIN)),
                                      image && alert_frame, aw, ah);
  lv_obj_set_size(p.card, l.card_w, l.card_h);
  lv_obj_set_pos(p.icon, l.icon_x, l.icon_y);
  lv_obj_set_pos(p.title, l.text_x, l.title_y);
  lv_obj_set_size(p.title, l.text_w, l.title_h);
  lv_obj_set_pos(p.subtitle, l.text_x, l.subtitle_y);
  lv_obj_set_size(p.subtitle, l.text_w, l.subtitle_h);
  // From the card's bottom right, as the card's content area (inside its border) is measured from there too. A second
  // button stands on the left of the first (screen_alert::buttons); the words on each end in dots when they are too long.
  const bool two = alert_two_buttons && p.button2;
  const auto b = screen_alert::buttons(l, two);
  const int pad = ui::px(ui::large() ? 12 : 8);
  const auto place = [&](lv_obj_t *button, lv_obj_t *label, int x, int w) {
    lv_obj_set_size(button, w, l.button_h);
    lv_obj_align(button, LV_ALIGN_BOTTOM_RIGHT, -(l.card_w - x - w), -(l.card_h - l.button_y - l.button_h));
    // One line high: LVGL only ends a DOT label in dots when its text is taller than the label.
    if (label) lv_obj_set_size(label, std::max(0, w - 2 * pad), lv_font_get_line_height(lv_obj_get_style_text_font(label, LV_PART_MAIN)));
  };
  place(p.button, p.label, b.x, b.w);
  if (p.button2) {
    if (two) {
      place(p.button2, p.label2, b.x2, b.w2);
      lv_obj_remove_flag(p.button2, LV_OBJ_FLAG_HIDDEN);
    } else {
      lv_obj_add_flag(p.button2, LV_OBJ_FLAG_HIDDEN);
    }
  }
  if (!alert_frame) return l;
  if (l.image_w > 0 && l.image_h > 0) {
    lv_obj_set_pos(alert_frame, l.image_x, l.image_y);
    lv_obj_set_size(alert_frame, l.image_w, l.image_h);
  } else {
    // No picture, or no room for one on this glass: the frame stays hidden and the image is never fetched for it.
    lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
  }
  return l;
}
inline std::string alert_announced, alert_camera, alert_url;
inline uint32_t alert_announced_at = 0, alert_retry_at = 0, alert_shown_at = 0;
inline uint8_t alert_retries = 0;
inline bool alert_thumb_loading = false;
constexpr uint8_t ALERT_IMAGE_RETRIES = 3;  // an alert's picture is worth another try after a failed connection
// One picture loads at a time (firmware 0.2.64+): a download shares ESPHome's loop with touch and drawing, and two at
// once (a cover and an alert's picture) would double the time a tap can wait. An alert closes every card (wake_display
// runs close_cards), so the card's cover goes with it; a media tile over the whole page stays under the alert. Its
// cover waits while the alert's picture is announced, on its way or about to be tried again; a cover already on its
// way finishes and the alert's picture starts right after it. A full camera and the cover share one image, so they
// never load together. Memory is not the limit here: the pictures live in PSRAM (a cover ~70 KB, the alert's 172 KB).
inline bool alert_image_due() {
  if (alert_camera.empty() || alert_picture) return false;
  if (alert_thumb_loading || alert_retry_at) return true;
  // The link has not come yet: wait for it as long as an announced camera still belongs to its alert.
  return alert_url.empty() && esphome::millis() - alert_shown_at < camera_view::PENDING_MS;
}

inline bool camera_supported() { return static_cast<bool>(camera_full.load); }
inline bool camera_visible() { return camera_root != nullptr; }

// ---- Pictures kept until they change (firmware 0.3.2+, picture_store.h) ----
// On a board with PSRAM every picture a card draws (a page's strip, an album cover) is the store's own copy, never the
// online_image buffer the next download overwrites: a kept page keeps its pictures, a cover is fetched once per track,
// and a camera shows its last picture at once when its page comes back. A board without PSRAM stores nothing and draws
// from the download as before.
inline picture_store::Store<lv_image_dsc_t> pictures;
inline bool pictures_kept() {
  if (!pictures.allocate) {
#ifdef USE_ESP32
    // At most 1.5 MB, a fifth of the PSRAM: a 4-inch page of tall covers is one 480x400 strip of 384 KB.
    const size_t psram = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    pictures.budget = std::min<size_t>(1536u << 10, psram / 5);
#endif
    pictures.allocate = kept_allocate;
    pictures.release = kept_free;
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
  each_card([&](Widgets &w) { on(w.picture); if (w.extra_mode == "media") on(w.parts[MEDIA_PICTURE]); });
  on(media_detail_picture);
  on(camera_picture);
  if (media_library::draws(image)) shown = true;
  return shown;
#else
  (void) image;
  return false;
#endif
}
inline void pictures_collect() { if (pictures_kept()) pictures.collect(picture_shown); }

// ---- The album cover of the media card (firmware 0.2.64+) ----
// The card, or a media tile over the whole page, says which cover it wants: the player, the mark of its picture, the
// size and the colour behind the rounded corners (cover_want). The app answers `esphome.screen_camera` with a link to
// a BMP of exactly that (op "camera", t "cover"); the board's full online_image loads it once and the picture stays
// until the mark changes, the owner goes (the card closes, the page turns) or a camera opens full screen: the camera
// and the cover share that one image buffer, and the camera wins. Everything runs from camera_tick().
struct CoverWish { std::string entity, picture; int size = 0; uint32_t background = 0; CoverOwner owner = CoverOwner::NONE; size_t slot = 0; };
inline CoverWish cover_wish;
// The cover on its way (firmware 0.3.2+): a page turned away while it loads still keeps it once it lands, so the next
// visit shows it instead of fetching it again.
inline std::string cover_in_flight;
// A cover is the same picture as long as the player, its picture's mark, the size and the colour behind it are.
inline std::string cover_key(const std::string &entity, const std::string &mark, int size, uint32_t background) {
  char tail[24];
  snprintf(tail, sizeof(tail), "|%d|%06X", size, (unsigned) background);
  return "cover|" + entity + "|" + mark + tail;
}
inline std::string cover_key(const CoverWish &w) { return cover_key(w.entity, w.picture, w.size, w.background); }
inline std::string cover_key(const Widgets &w) { return cover_key(w.cover_entity, w.cover_mark, w.cover_size, w.cover_ground); }
// The cover a media card wants, when the store has it.
inline lv_image_dsc_t *kept_cover(const Widgets &w) {
  return pictures_kept() && !w.cover_entity.empty() ? pictures.find(cover_key(w)) : nullptr;
}
inline camera_view::Feed cover;
inline void camera_release();
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
inline void camera_map_sheet(const MapSheet &next);
inline void camera_request(const std::string &entity, int size = 0, uint32_t background = 0);
// The pictures on screen go before their buffer does.
inline void cover_forget_pictures() {
  if (media_detail_picture) { lv_obj_delete(media_detail_picture); media_detail_picture = nullptr; }
  for (auto &w : widgets) if (w.extra_mode == "media" && w.parts[MEDIA_PICTURE]) { lv_obj_delete(w.parts[MEDIA_PICTURE]); w.parts[MEDIA_PICTURE] = nullptr; }
}
inline void cover_release() {
  const bool had = cover.open();
  cover = camera_view::Feed{};
  // A kept copy stays on its cards; only a picture drawn from the download goes with the download.
  if (!pictures_kept()) cover_forget_pictures();
  if (had && !camera_root) camera_release_due = true;
}
inline void cover_want(const std::string &entity, const std::string &picture, int size, uint32_t background, CoverOwner owner, size_t slot) {
  if (!camera_supported()) return;
  const bool same = cover_wish.entity == entity && cover_wish.picture == picture && cover_wish.size == size && cover_wish.background == background;
  cover_wish = CoverWish{entity, picture, size, background, owner, slot};
  if (same) return;
  cover_release();  // another cover: asked for on the next tick
}
inline lv_image_dsc_t *cover_ready(const std::string &entity, int size, uint32_t background) {
  if (pictures_kept()) {
    if (cover_wish.entity != entity || cover_wish.size != size || cover_wish.background != background) return nullptr;
    return pictures.find(cover_key(cover_wish));
  }
  if (!cover.loaded || cover.entity != entity || cover_wish.size != size || cover_wish.background != background) return nullptr;
  auto *src = camera_full.source();
  return src && src->data ? src : nullptr;
}
inline void cover_drop() { cover_wish = CoverWish{}; cover_release(); }
// Whether the owner still shows the cover: the card open on that player, or the tile on screen in its slot.
inline bool cover_visible() {
  if (cover_wish.owner == CoverOwner::DETAIL)
    return detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN) && detail_index < model.count && model.tiles[detail_index].entity == cover_wish.entity;
  if (cover_wish.owner == CoverOwner::TILE && cover_wish.slot < widgets.size()) {
    if (detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN)) return false;  // a card covers the page
    auto &w = widgets[cover_wish.slot];
    return w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) && w.index < model.count && model.tiles[w.index].entity == cover_wish.entity && w.extra_mode == "media";
  }
  // Fetched ahead: as long as a card, kept or back on the glass by now, still wants exactly this cover.
  if (cover_wish.owner == CoverOwner::PREFETCH) {
    const std::string key = cover_key(cover_wish);
    bool wanted = false;
    each_card([&](Widgets &w) { if (w.extra_mode == "media" && cover_key(w) == key) wanted = true; });
    return wanted;
  }
  return false;
}
// Nobody holds the cover and a media tile with a picture is on the page (the card over it just closed, or the
// page turned): the tile draws itself again and asks.
inline void cover_offer() {
  if (detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN)) return;
  for (auto &w : widgets) {
    if (!w.tile || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) || w.index >= model.count || w.extra_mode != "media") continue;
    const auto &t = model.tiles[w.index];
    if (t.extra().media_picture.empty() || !media_card::has_track(t.state)) continue;
    // A kept page that came back with its cover on the card needs no new drawing (firmware 0.3.2+).
    if (w.cover_mark == t.extra().media_picture) if (auto *kept = kept_cover(w)) if (draws(w.parts[MEDIA_PICTURE], kept)) continue;
    refresh_tile(w.index);
    return;
  }
}
// Covers the app said it has none of: not asked for ahead again (a new track is a new key).
inline std::array<std::string, 8> cover_none;
inline size_t cover_none_next = 0;
// The screen is idle and a media card on a kept page lacks its cover: fetch it now, one at a time, so the page shows it
// the moment it comes back (firmware 0.3.2+). Not while pages are being prepared.
inline bool cover_prefetch() {
  if (!pictures_kept() || prepare_busy()) return false;
  for (auto *set : kept_sets) {
    if (!set) continue;
    for (const auto &w : *set) {
      if (w.extra_mode != "media" || w.cover_entity.empty() || w.index >= model.count) continue;
      const auto &t = model.tiles[w.index];
      const std::string key = cover_key(w);
      if (t.entity != w.cover_entity || t.extra().media_picture != w.cover_mark || pictures.entry(key)) continue;
      if (std::find(cover_none.begin(), cover_none.end(), key) != cover_none.end()) continue;
      cover_wish = CoverWish{w.cover_entity, w.cover_mark, w.cover_size, w.cover_ground, CoverOwner::PREFETCH, 0};
      ESP_LOGI("camera", "cover of %s fetched ahead", w.cover_entity.c_str());
      return true;
    }
  }
  return false;
}
// The cover is here: onto the card at once, or the tile draws itself again with it.
inline void cover_arrived() {
  if (!cover_visible()) return;
  lv_image_dsc_t *src = camera_full.source();
  if (pictures_kept() && src && src->data) {
    src = pictures.put(cover_key(cover_wish), *src, esphome::millis());
    if (!src) ESP_LOGW("camera", "no room to keep the cover of %s", cover.entity.c_str());
  }
  if (cover_wish.owner == CoverOwner::DETAIL) media_detail_picture = media_picture_show(detail_root, media_detail_picture, media_art_rect, src);
  else if (cover_wish.owner == CoverOwner::PREFETCH) {
    // Onto the cards that want it (a kept one shows it when its page comes back), and the next one may go.
    const std::string key = cover_key(cover_wish);
    each_card([&](Widgets &w) {
      if (src && w.extra_mode == "media" && cover_key(w) == key) w.parts[MEDIA_PICTURE] = media_picture_show(w.extra, w.parts[MEDIA_PICTURE], w.cover_rect, src);
    });
    ESP_LOGI("camera", "cover of %s kept ahead", cover.entity.c_str());
    cover_drop();
    return;
  }
  else refresh_tile(widgets[cover_wish.slot].index);
  ESP_LOGI("camera", "cover of %s shown", cover.entity.c_str());
  picture_memory("after", "cover", cover_wish.size * cover_wish.size);
}
inline void cover_tick(uint32_t now) {
  // The library over the card has the image to itself while it is open (firmware 0.24.0+).
  if (camera_root || !camera_supported() || media_library::visible()) return;
  if (cover_wish.owner == CoverOwner::NONE) { cover_offer(); if (cover_wish.owner == CoverOwner::NONE && !cover_prefetch()) return; }
  if (cover_wish.owner == CoverOwner::NONE) return;
  if (!cover_visible()) { cover_drop(); return; }
  // A cover on the glass loads while the tiles are seen, a dimmed screen too (firmware 0.40.0+); one fetched ahead for
  // another page waits for a screen in use.
  if (cover_wish.owner == CoverOwner::PREFETCH ? !awake() : !tiles_seen()) return;
  // A cover kept from before is on the card already: nothing to fetch until the track changes.
  if (pictures_kept() && pictures.entry(cover_key(cover_wish))) return;
  if (!cover.open()) cover.open(cover_wish.entity, true);
  if (alert_image_due()) return;  // the alert's picture first
  if (cover.should_ask(now)) {
    if (!fresh()) return;
    cover.ask(now);
    camera_request(cover.entity, cover_wish.size, cover_wish.background);
  } else if (cover.should_load(now)) {
    auto *input = lv_indev_get_next(nullptr);
    if (input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED) return;
    if (!camera_view::settled(now, last_turn_ms)) return;  // not between two quick page turns
    cover.start(now);
    cover_in_flight = pictures_kept() ? cover_key(cover_wish) : std::string();
    ESP_LOGI("camera", "cover load %s", cover.entity.c_str());
    picture_memory("before", "cover", cover_wish.size * cover_wish.size);
    camera_full.load(cover.url);
  }
}

// ---- Live pictures on camera tiles (firmware 0.2.77+) and album covers on media tiles (0.2.78+) ----
// A camera tile with "display": "live" shows a small picture of its camera in the icon's place, a media tile with
// "display": "cover" the album cover of what plays. The pictured tiles of the page on screen share one image: the
// screen asks for them together (the entities in slot order, the size of the icon's circle and the colour of each tile
// behind the rounded corners) and the app serves one strip of squares, top to bottom, that every tile takes its own
// square out of (LVGL's image offset). One download per page at the pace of the fastest camera, 5 to 30 s, in the
// board's third online_image; a page of covers alone loads once. It waits for the alert's picture, a cover or the
// camera full screen: one picture loads at a time. A page turn, a card over the page, another look or another track
// (the picture's mark in the media state) changes what is wanted: the strip is dropped and asked for again.
// `tiles`: the tiles' own indexes in the same order (firmware 0.16.0+): one entity may be on several tiles of a page,
// each with its own square and settings, and the app takes each tile's own settings by its index.
// `dark` (firmware 0.20.0+): the look the screen is in. A map is drawn in the screen's own colours, light or dark, so the
// look is part of what is asked for and of the name a kept picture goes under: turning the look asks for the other map.
// `drawn` (firmware 0.30.0+): a picture on the page that the app draws itself (a map), so there is always one to be had
// and an answer without a picture is asked for again.
struct LiveWish { std::string entities, tiles, grounds, marks, atlas; int size = 0, atlas_x = 0, atlas_y = 0, atlas_scale = picture_store::SCALE_ONE; uint32_t every = 15000; bool cameras = false, dark = false, drawn = false; };
inline LiveWish live_wish;
inline camera_view::Feed live;  // entity: the list asked for
inline std::string live_have;   // the list the strip on screen holds, "" for a tile without a picture
inline ImageHooks camera_live;
inline bool live_supported() { return static_cast<bool>(camera_live.load); }
inline bool card_open() { return detail_root && !lv_obj_has_flag(detail_root, LV_OBJ_FLAG_HIDDEN); }
// The n-th item of a comma list, or -1 when it is not in it.
inline int list_index(const std::string &list, const std::string &item) {
  int n = 0;
  for (size_t start = 0;; ++n) {
    const size_t comma = list.find(',', start);
    if (list.compare(start, comma == std::string::npos ? std::string::npos : comma - start, item) == 0 && (comma == std::string::npos ? list.size() - start : comma - start) == item.size()) return n;
    if (comma == std::string::npos) return -1;
    start = comma + 1;
  }
}
// The app's answer names the same tiles in the same order, with "" where it has no picture.
inline bool same_list(const std::string &asked, const std::string &answered) {
  size_t a = 0, b = 0;
  for (;;) {
    const size_t ca = asked.find(',', a), cb = answered.find(',', b);
    const std::string x = asked.substr(a, ca == std::string::npos ? std::string::npos : ca - a), y = answered.substr(b, cb == std::string::npos ? std::string::npos : cb - b);
    if (!y.empty() && x != y) return false;
    if ((ca == std::string::npos) != (cb == std::string::npos)) return false;
    if (ca == std::string::npos) return true;
    a = ca + 1; b = cb + 1;
  }
}
// What the page on screen wants: its live camera tiles in slot order, with the colour under each picture's corners.
inline LiveWish live_wanted() {
  LiveWish want;
  want.dark = theme::dark;
  if (!model.ready()) return want;
  bool atlas=false;
  for(const auto &w:widgets)
    if(w.tile&&!lv_obj_has_flag(w.tile,LV_OBJ_FLAG_HIDDEN)&&w.index<model.count&&card_art(model.tiles[w.index]))atlas=true;
  if(atlas){
    lv_obj_update_layout(tile_grid);want.atlas="[";
    // The atlas starts at the top left of its pictures, not of the glass: a picture at the bottom right would
    // otherwise bring a canvas of empty pixels with it on every refresh (firmware 0.3.1).
    want.atlas_x=want.atlas_y=INT32_MAX;
    int right=0,bottom=0;
    for(auto &w:widgets){
      if(!w.tile||lv_obj_has_flag(w.tile,LV_OBJ_FLAG_HIDDEN)||w.index>=model.count||!model.tiles[w.index].pictured())continue;
      lv_area_t b;lv_obj_get_coords(card_art(model.tiles[w.index])?w.tile:w.circle,&b);
      want.atlas_x=std::min<int>(want.atlas_x,b.x1);want.atlas_y=std::min<int>(want.atlas_y,b.y1);
      right=std::max<int>(right,b.x2+1);bottom=std::max<int>(bottom,b.y2+1);
    }
    if(want.atlas_x==INT32_MAX)want.atlas_x=want.atlas_y=0;
    // Pictures over the cap come smaller, each in the middle of its own place (picture_store::MAX_BYTES, GitHub #68).
    want.atlas_scale=picture_store::fit_scale(right-want.atlas_x,bottom-want.atlas_y);
  }
  for (auto &w : widgets) {
    if (!w.tile || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) || w.index >= model.count) continue;
    const auto &t = model.tiles[w.index];
    if (!t.pictured()) continue;
    if (!want.entities.empty()) { want.entities += ','; want.tiles += ','; want.grounds += ','; want.marks += ','; }
    want.entities += t.entity;
    want.tiles += std::to_string(w.index);
    char ground[8];
    uint32_t behind=(t.transparent||card_art(t)) ? theme::hex(theme::PAGE) : theme::surface(t.background);
    if(atlas){
      lv_area_t bounds;lv_obj_get_coords(card_art(t)?w.tile:w.circle,&bounds);
      const int scale=want.atlas_scale,x=bounds.x1-want.atlas_x,y=bounds.y1-want.atlas_y;
      const int width=lv_area_get_width(&bounds),height=lv_area_get_height(&bounds);
      const int radius=card_art(t)?lv_obj_get_style_radius(w.tile,LV_PART_MAIN):width/6;
      const int fx=picture_store::scaled(x,scale),fy=picture_store::scaled(y,scale);
      const int fw=std::max(1,picture_store::scaled(x+width,scale)-fx),fh=std::max(1,picture_store::scaled(y+height,scale)-fy);
      char frame[96];snprintf(frame,sizeof(frame),"%s[%d,%d,%d,%d,%d,%d]",want.atlas.size()>1?",":"",
        fx,fy,fw,fh,std::min(picture_store::scaled(radius,scale),std::min(fw,fh)/2),card_art(t)&&(t.cover_tile()||t.favorite())?170:0);
      want.atlas+=frame;
      // A smaller picture sits on the dark card (live_place), so its rounded corners are rounded over that.
      if(card_art(t)&&(fw<width||fh<height))behind=theme::hex(theme::CAMERA_PAGE);
    }
    snprintf(ground, sizeof(ground), "%06X", (unsigned) behind);
    want.grounds += ground;
    if (t.cover_tile()) want.marks += t.extra().media_picture;
    // A favourite's picture is what it plays (firmware 0.24.0+): its own mark, never the player's cover.
    if (t.favorite()) want.marks += t.extra().fav_mark;
    // A map's mark is what makes it another picture (app 0.4.33). It sets no pace: a page of maps and covers loads
    // once and then waits for someone to move.
    if (t.is_map()) { want.marks += t.extra().map_mark; want.drawn = true; }
    if (!want.size) want.size = lv_obj_get_style_width(w.circle, LV_PART_MAIN);
    // The page's pace is its quickest camera's: a page of 30 s cameras loaded every 15 s before firmware 0.3.7.
    if (t.live()) { want.every = want.cameras ? std::min<uint32_t>(want.every, t.refresh * 1000u) : t.refresh * 1000u; want.cameras = true; }
  }
  if(atlas)want.atlas+="]";
  return want;
}
// A strip is the same picture as long as the tiles, their colours, their covers' marks and the frames are: a camera's
// next picture keeps the key and is written over the last one.
inline std::string live_key_head(const LiveWish &w) { return "live|" + w.entities + "|" + w.tiles + "|" + w.grounds + "|"; }
inline std::string live_key_tail(const LiveWish &w) {
  char size[12];
  snprintf(size, sizeof(size), "%d", w.size);
  return "|" + w.atlas + "|" + size + (w.dark ? "|d" : "|l");
}
inline std::string live_key(const LiveWish &w) { return live_key_head(w) + w.marks + live_key_tail(w); }
// Whether a kept strip is this page's with other marks (someone on its map moved, another track plays): the same tiles
// in the same frames and colours, so a card can keep drawing its square of it (firmware 0.30.0+).
inline bool live_same_page(const std::string &key, const LiveWish &w) {
  const std::string head = live_key_head(w), tail = live_key_tail(w);
  return key.size() >= head.size() + tail.size() && key.compare(0, head.size(), head) == 0 &&
         key.compare(key.size() - tail.size(), tail.size(), tail) == 0;
}
// Whether the n-th item of a comma list is this one.
inline bool list_has_at(const std::string &list, int n, const std::string &item) {
  size_t start = 0;
  for (int i = 0; i < n; ++i) { start = list.find(',', start); if (start == std::string::npos) return false; ++start; }
  const size_t comma = list.find(',', start);
  return list.compare(start, comma == std::string::npos ? std::string::npos : comma - start, item) == 0 &&
         (comma == std::string::npos ? list.size() - start : comma - start) == item.size();
}
// The strip's square for a tile, or nullptr while the strip is not here (or has no picture of this camera). The square
// is the tile's own place in the wish, found by its index: an entity on several tiles has a square on each.
inline lv_image_dsc_t *live_ready(size_t index, const std::string &entity, int size, int &square) {
  square = list_index(live_wish.tiles, std::to_string(index));
  if (square < 0) return nullptr;
  if (pictures_kept()) {
    if (live_wish.atlas.empty() && live_wish.size != size) return nullptr;
    auto *kept = pictures.entry(live_key(live_wish));
    if (kept) {
      // The tiles the app answered for, "" where it had no picture.
      if (!list_has_at(kept->note, square, entity)) return nullptr;
      return !live_wish.atlas.empty() || kept->image.header.h >= (square + 1) * size ? &kept->image : nullptr;
    }
    // Not kept (no room in the store): the download itself, as on a board without PSRAM, until the page turns
    // (live_release). Before firmware 0.9.0 such a page showed no picture at all (GitHub #68).
  }
  if (!live.loaded || (live_wish.atlas.empty() && live_wish.size != size) || !list_has_at(live_have, square, entity)) return nullptr;
  auto *src = camera_live.source();
  return src && src->data && (!live_wish.atlas.empty() || src->header.h >= (square + 1) * size) ? src : nullptr;
}
// Whether a camera card still waits for its picture: until the page's strip has had its first try at this camera. One the
// app has no picture of, or a load that failed, stops the spinner; a refresh of a picture on screen never starts it.
// A screen that cannot ask right now (after a restart, before the app has sent the layout again; Home Assistant away)
// is not waiting for anything: the card shows its head as every card does then, not a spinner that never ends.
inline bool live_waiting(const Tile &t) {
  if (!live_supported() || !fresh() || !tiles_seen()) return false;
  return !(live.open() && list_index(live.entity, t.entity) >= 0 && live.animation_ready());
}
// Draws the camera cards again once their wait is over without a picture (a failed load, an app with none).
inline void live_redraw() {
  for (auto &w : widgets)
    if (w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) && w.index < model.count && model.tiles[w.index].pictured()) refresh_tile(w.index);
}
// The pictures go before their buffer does (as the cover's do); the tiles draw their circle again.
inline void live_release() {
  const bool had = live.open();
  live = camera_view::Feed{};
  live_have.clear();
  // Kept copies stay on their cards (a page that comes back shows them); only the download goes, and a card that drew
  // the download itself because the store had no room for it (live_ready) lets it go first.
  if (pictures_kept()) {
#if LV_USE_IMAGE
    if (auto *download = camera_live.source ? camera_live.source() : nullptr) {
      each_card([&](Widgets &w) {
        if (!draws(w.picture, download)) return;
        lv_image_set_src(w.picture, nullptr);
        lv_obj_add_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
        // A card on the glass draws its circle again; a kept page's card when its pictures come again (live_loaded).
        if (&w >= widgets.data() && &w < widgets.data() + widgets.size() && w.index < model.count) refresh_tile(w.index);
      });
    }
#endif
    if (had && camera_live.release) camera_live.release();
    return;
  }
  for (auto &w : widgets) {
    if (!w.picture || lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN)) continue;
#if LV_USE_IMAGE
    lv_image_set_src(w.picture, nullptr);
#endif
    lv_obj_add_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
    refresh_tile(w.index);
  }
  if (had && camera_live.release) camera_live.release();
}
// The tile's square in the icon's place, or the circle again while the strip is not here (render_slot).
inline void live_place(Widgets &w, const Tile &t, int size, int x, int y) {
#if LV_USE_IMAGE
  int square = -1;
  lv_image_dsc_t *src = t.pictured() ? live_ready(w.index, t.entity, size, square) : nullptr;
  // A map whose next picture is not here keeps the one it shows (firmware 0.30.0+): this page's strip from before
  // someone moved, until the new one has loaded, and for as long as the app cannot draw one. Before, the card fell
  // back to the plain tile in between.
  if (!src && square >= 0 && t.is_map() && w.picture && pictures_kept()) {
    auto *held = pictures.holder(static_cast<const lv_image_dsc_t *>(lv_image_get_src(w.picture)));
    if (held && live_same_page(held->key, live_wish) && list_has_at(held->note, square, t.entity)) src = &held->image;
  }
  if (src) {
    if (!w.picture) {
      w.picture = lv_image_create(w.tile);
      lv_obj_remove_flag(w.picture, LV_OBJ_FLAG_CLICKABLE);
      // From the top left, so the offset picks the square: LVGL's default centres a source larger than its object.
      lv_image_set_inner_align(w.picture, LV_IMAGE_ALIGN_TOP_LEFT);
    }
    lv_image_set_src(w.picture, src);
    if(!live_wish.atlas.empty()){
      lv_area_t tile;lv_obj_get_coords(w.tile,&tile);
      const bool background=card_art(t);
      const int left=lv_obj_get_style_space_left(w.tile,LV_PART_MAIN),top=lv_obj_get_style_space_top(w.tile,LV_PART_MAIN);
      const int ax=tile.x1+(background?0:left+x)-live_wish.atlas_x,ay=tile.y1+(background?0:top+y)-live_wish.atlas_y;
      const int width=background?lv_obj_get_width(w.tile):size,height=background?lv_obj_get_height(w.tile):size;
      // The frame as live_wanted asked for it; a picture over the cap is smaller and sits in the middle of its place.
      const int scale=live_wish.atlas_scale,fx=picture_store::scaled(ax,scale),fy=picture_store::scaled(ay,scale);
      const int fw=std::max(1,picture_store::scaled(ax+width,scale)-fx),fh=std::max(1,picture_store::scaled(ay+height,scale)-fy);
      if(ax<0||ay<0||fx+fw>(int)src->header.w||fy+fh>(int)src->header.h){lv_obj_add_flag(w.picture,LV_OBJ_FLAG_HIDDEN);return;}
      lv_image_set_offset_x(w.picture,-fx);lv_image_set_offset_y(w.picture,-fy);
      lv_obj_set_pos(w.picture,(background?-left:x)+(width-fw)/2,(background?-top:y)+(height-fh)/2);lv_obj_set_size(w.picture,fw,fh);
      if(background)lv_obj_move_to_index(w.picture,0);
      // The card behind a smaller picture: dark while it is smaller, the card's own colour again once it fills it.
      if(background){
        const bool dark=fw<width||fh<height;
        set_color(w.tile,LV_STYLE_BG_COLOR,dark?theme::color(theme::CAMERA_PAGE):lv_color_hex(theme::surface(t.background)));
        set_number(w.tile,LV_STYLE_BG_OPA,t.transparent&&!dark?LV_OPA_TRANSP:LV_OPA_COVER);
      }
    }else{
      lv_image_set_offset_x(w.picture,0);lv_image_set_offset_y(w.picture, -square * size);
      lv_obj_set_pos(w.picture, x, y);lv_obj_set_size(w.picture, size, size);
    }
    lv_obj_remove_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
    lv_obj_invalidate(w.picture);
  } else if (w.picture) lv_obj_add_flag(w.picture, LV_OBJ_FLAG_HIDDEN);
  set_hidden(w.circle, src != nullptr && !card_art(t));
#else
  (void) w; (void) t; (void) size; (void) x; (void) y;
#endif
}
// Background downloads share the drawing loop. Keep the title readable but still
// until the picture is placed (or the load has failed), then reuse LVGL's reading
// pause. No extra animation or per-tile timer is needed.
inline bool live_marquee_ready(const Widgets &w, const Tile &t) {
  if (!card_art(t) || !live_supported()) return true;
  // A picture already on the glass keeps its title scrolling through a refresh: pausing it for every camera round
  // started a long title from its first letter again, so it was never read to the end (firmware 0.3.1).
  if (w.picture && !lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN) && list_index(live_have, t.entity) >= 0) return true;
  if (list_index(live_wish.entities, t.entity) < 0 || !live.animation_ready()) return false;
  return !live.loaded || list_index(live_have, t.entity) < 0 ||
         (w.picture && !lv_obj_has_flag(w.picture, LV_OBJ_FLAG_HIDDEN));
}
inline void live_marquees() {
  for (auto &w : widgets) {
    if (!w.tile || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) || w.index >= model.count || w.extra_mode != "tall") continue;
    const auto &t = model.tiles[w.index];
    if (card_art(t)) marquee(w.parts[0], true, live_marquee_ready(w, t));
  }
}
// Asks for the page's strip: `esphome.screen_camera` with the tiles, the size and the grounds (app 0.2.91+).
inline void live_request() {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_camera");
  request.is_event = true;
  char size_text[12];
  snprintf(size_text, sizeof(size_text), "%d", live_wish.size);
  // `idx` (firmware 0.16.0+): each square's tile by its index, so the app prepares it the way that tile asks.
  // `dark` (firmware 0.20.0+): the look a map is drawn in. The app reads the keys it knows, so an older one ignores it.
  const std::string keys[] = {"inbox", "tiles", "idx", "size", "bg", "session", "rev", "view", "dark", "atlas"}, values[] = {inbox, live_wish.entities, live_wish.tiles, size_text, live_wish.grounds, protocol_key(transfer.lease), layout_rev, std::to_string(++live_view_id), live_wish.dark ? "1" : "0", live_wish.atlas};
  const int count=live_wish.atlas.empty()?9:10;
  request.data.init(count);
  for (int i = 0; i < count; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("camera", "asked for the live tiles %s", live_wish.entities.c_str());
}
inline void live_tick(uint32_t now) {
  if (!live_supported()) return;
  LiveWish want = live_wanted();
  if (want.entities != live_wish.entities || want.tiles != live_wish.tiles || want.grounds != live_wish.grounds || want.marks != live_wish.marks || want.size != live_wish.size || want.atlas != live_wish.atlas ||
      want.atlas_x != live_wish.atlas_x || want.atlas_y != live_wish.atlas_y || want.atlas_scale != live_wish.atlas_scale || want.dark != live_wish.dark) {
    live_wish = want;
    live_release();
    // A strip kept from before goes on the tiles at once: covers alone are then done, a camera loads its next picture
    // when the kept one is as old as its pace (firmware 0.3.2+). Otherwise covers alone load once per link (a new
    // track is a new wish) and a camera sets the pace.
    auto *kept = pictures_kept() && !want.entities.empty() ? pictures.entry(live_key(want)) : nullptr;
    if (kept) {
      live_have = kept->note;
      for (auto &w : widgets)
        if (w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) && w.index < model.count && model.tiles[w.index].pictured() &&
            !draws(w.picture, &kept->image)) refresh_tile(w.index);
    }
    if (!want.entities.empty() && (!kept || want.cameras)) {
      live.open(want.entities, !want.cameras, want.every, want.drawn);
      if (kept) live.resume(kept->stored_at);
    }
  }
  live_marquees();
  // While the tiles are seen, a dimmed screen without a screensaver too (firmware 0.40.0+, GitHub #161).
  if (!live.open() || camera_root || card_open() || !tiles_seen()) return;
  if (alert_image_due() || alert_thumb_loading || cover.loading || camera.loading) return;  // one picture at a time
  if (live.should_ask(now)) {
    if (!fresh()) return;
    live.ask(now);
    live_request();
  } else if (live.should_load(now)) {
    auto *input = lv_indev_get_next(nullptr);
    if (input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED) return;
    if (!camera_view::settled(now, last_turn_ms)) return;  // not between two quick page turns
    live.start(now);
    live_marquees();  // Stop before the download can block the drawing loop.
    camera_live.load(live.url);
  }
}
// The board's third online_image: the strip is here (or unchanged, 304), or failed.
inline void live_loaded(bool cached) {
  if (!live.loading) return;
  live.finish(esphome::millis(), true);
  ESP_LOGI("camera", "live tiles %s", cached ? "unchanged" : "loaded");
  if (auto *strip = camera_live.source()) {
    picture_memory("after", "strip", strip->header.w * strip->header.h);
    const std::string key = live_key(live_wish);
    if (pictures_kept() && strip->data && !pictures.put(key, *strip, esphome::millis(), live_have))
      ESP_LOGW("camera", "no room to keep the live tiles");
    // This page's strips with other marks are done with (firmware 0.30.0+): a map that follows someone made a new
    // one at every move, and small ones never passed the budget, so they stayed until the store had no place left.
    if (pictures_kept()) pictures.retire_if([&](const auto &e) { return e.key != key && live_same_page(e.key, live_wish); });
  }
  for (auto &w : widgets)
    if (w.tile && !lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) && w.index < model.count && model.tiles[w.index].pictured()) refresh_tile(w.index);
}
inline void live_failed() {
  if (!live.loading) return;
  live.finish(esphome::millis(), false);
  live_marquees();
  live_redraw();
  ESP_LOGI("camera", "live tiles failed");
}

// Asks ESP Screen Manager for a link (app 0.2.66+ answers with op "camera"). An event, like history_request.
// A cover (firmware 0.2.64+) adds the size it wants and the colour behind its rounded corners; the app bakes both in.
inline void camera_request(const std::string &entity, int size, uint32_t background) {
  if (inbox.empty()) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_camera");
  request.is_event = true;
  char size_text[12] = "", background_text[8] = "";
  if (size > 0) { snprintf(size_text, sizeof(size_text), "%d", size); snprintf(background_text, sizeof(background_text), "%06X", (unsigned) background); }
  // A map's full view (firmware 0.21.0+) adds its tile's index and the look, which the app draws it in; an older app
  // reads the keys it knows.
  const bool map = size <= 0 && camera_map_index >= 0;
  // The screensaver's picture (firmware 0.29.0+): the full view's request with what it shows, "camera" or "media".
  const bool saver = size <= 0 && saver_camera;
  const std::string keys[] = {"inbox", "entity", "size", "bg", "session", "rev", "view", "idx", "dark", "focus"}, values[] = {inbox, entity, size_text, background_text, protocol_key(transfer.lease), layout_rev, std::to_string(size > 0 ? ++cover_view_id : ++camera_view_id), std::to_string(camera_map_index), theme::dark ? "1" : "0", map_focus};
  const int count = map ? 10 : 7;
  request.data.init(count + (saver ? 1 : 0));
  if (saver) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef("saver");
    entry.value = esphome::StringRef(saver_now.kind);
    request.data.push_back(entry);
  }
  for (int i = 0; i < count; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
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

// The camera full screen's copy in the store (camera_loaded).
inline std::string camera_key(const std::string &entity) { return "camera|" + entity; }

inline void camera_close() {
  if (!camera_root) return;
  lv_obj_delete(camera_root);
  camera_root = camera_picture = camera_note = camera_back = camera_title = camera_spinner = map_card_obj = nullptr;
  saver_first = saver_second = nullptr;  // they went with the view
  saver_keys = {};
  map_focus.clear();
  map_pinned = false;
  map_sheet = MapSheet{};
  camera_release_due = true;
  // Its copy goes with it, on the next tick (pictures_collect), as the download's buffer does.
  pictures.retire(camera_key(camera.entity));
  ESP_LOGI("camera", "closed %s", camera.entity.c_str());
  camera = camera_view::Feed{};
}

// The map's card at the bottom of its full view: the name, the state since when, and the day's changes with their
// times, in the card's own colours as a tile's card (firmware 0.21.0+). Every word comes ready from the app.
// The card over the bottom of a focused map: the effects page's card of rows (effects_page::card, its Metrics, its fonts,
// an icon at the left, the name, the value at the right), and the one picked as the top bar's name, as a deeper card
// names what it shows. Every word and icon comes ready from the app, from Home Assistant.
inline std::string camera_name;  // the tile's own name, the top bar's when nobody is picked
inline void map_sheet_draw() {
  if (map_card_obj) { lv_obj_delete(map_card_obj); map_card_obj = nullptr; }
  const bool picked = camera_root && !map_focus.empty() && map_sheet.focus == map_focus && !map_sheet.title.empty();
  if (camera_title) lv_label_set_text(camera_title, (picked ? map_sheet.title : camera_name).c_str());
  if (!picked || map_sheet.rows.empty() || !effects_page::row_font) return;
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
}

inline void camera_map_sheet(const MapSheet &next) {
  if (!camera_root || camera_map_index < 0 || camera.entity != next.entity) return;
  // An answer for another focus than the one picked since is not this one's.
  if (next.focus != map_focus) return;
  map_sheet = next;
  map_sheet_draw();
}

// Focus a marker (or everyone again with ""): the card goes at once, the new picture and card come with the answer.
inline void map_focus_on(const std::string &entity) {
  map_focus = entity;
  map_sheet.focus.clear();
  map_sheet_draw();
  if (!camera_root || !fresh()) return;
  camera.ask(esphome::millis());
  camera_request(camera.entity);
}

inline void camera_open(const std::string &entity, const std::string &name, int map_index, const std::string &focus) {
  cover_in_flight.clear();  // the full camera takes the cover's image buffer
  if (!camera_supported() || !valid_entity(entity)) return;
  camera_close();
  camera_map_index = map_index;
  // Opened on someone (a person tile tapped): focused from the start, and Back closes the map at once.
  map_focus = focus;
  map_pinned = !focus.empty();
  // The last camera's image, or a media card's cover, goes before this one loads into the same online_image; the
  // cover is asked for again once the camera closes (cover_tick).
  cover_release();
  if (camera_release_due) camera_release();
  camera.open(entity);
  const int width = lv_display_get_horizontal_resolution(lv_display_get_default());
  const bool large = ui::large();
  // On the top layer: above the tiles, every card and an alert, which is there again after Back.
  camera_root = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(camera_root);
  lv_obj_set_size(camera_root, lv_pct(100), lv_pct(100));
  lv_obj_remove_flag(camera_root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(camera_root, LV_OBJ_FLAG_CLICKABLE);  // nothing reaches the tiles below
  lv_obj_set_style_bg_color(camera_root, theme::color(theme::CAMERA_PAGE), 0);
  lv_obj_set_style_bg_opa(camera_root, LV_OPA_COVER, 0);
  camera_note = lv_label_create(camera_root);
  if (detail_font) lv_obj_set_style_text_font(camera_note, detail_font, 0);
  lv_obj_set_style_text_color(camera_note, theme::color(theme::CAMERA_NOTE), 0);
  lv_obj_center(camera_note);
  camera_note_text("");
  // The starting screen's spinner, its ring dark on the black page in both looks.
  camera_spinner = spinner_create(camera_root, ui::px(large ? 48 : 32), ui::px(large ? 5 : 4));
  if (camera_spinner) {
    lv_obj_set_style_arc_color(camera_spinner, theme::color(theme::CAMERA_TRACK), LV_PART_MAIN);
    lv_obj_center(camera_spinner);
  }
  // The same top bar as a tile's card: a round back arrow at the left, the name centred.
  const int bar = ui::px(large ? 60 : 40), bar_x = ui::px(large ? 16 : 10), bar_y = ui::px(large ? 16 : 8);
  camera_back = lv_obj_create(camera_root);
  lv_obj_remove_style_all(camera_back);
  lv_obj_set_pos(camera_back, bar_x, bar_y);
  lv_obj_set_size(camera_back, bar, bar);
  lv_obj_add_flag(camera_back, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_radius(camera_back, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(camera_back, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(camera_back, theme::color(theme::KEY), 0);
  lv_obj_set_style_bg_color(camera_back, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  auto *arrow = lv_label_create(camera_back);
  if (mini_icon_font) lv_obj_set_style_text_font(arrow, mini_icon_font, 0);
  lv_obj_set_style_text_color(arrow, theme::color(theme::INK), 0);
  lv_label_set_text(arrow, "\U000F004D");
  lv_obj_center(arrow);
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
    if (!input || !camera_picture) return;
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
  lv_obj_set_pos(camera_title, bar_x + bar + 8, bar_y + (bar - (title_font ? lv_font_get_line_height(title_font) : 20)) / 2);
  lv_obj_set_size(camera_title, width - 2 * (bar_x + bar + 8), title_font ? lv_font_get_line_height(title_font) : 20);
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
    lv_obj_set_style_max_width(camera_title, width - 2 * (bar_x + bar + 8), 0);
    lv_obj_set_size(camera_title, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_align(camera_title, LV_ALIGN_TOP_MID, 0, bar_y);
  }
  ESP_LOGI("camera", "open %s", entity.c_str());
  // Asked for now rather than on the next tick (firmware 0.2.73+): the answer is most of the wait.
  const uint32_t now = esphome::millis();
  if (pictures_awake() && fresh() && camera.should_ask(now)) {
    camera.ask(now);
    camera_request(entity);
  }
}

// The next image, never under a finger: a load that starts now would hold up the tap on its way.
inline void camera_load(uint32_t now) {
  auto *input = lv_indev_get_next(nullptr);
  if (input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED) return;
  camera.start(now);
  picture_memory("before", "camera", 0);
  camera_full.load(camera.url);
}

// The board's interval (250 ms): ask for a link, or load the image again when it is time. Loading happens here, in
// ESPHome's loop, and never while the screen is in standby.
inline void camera_tick() {
  const uint32_t now = esphome::millis();
  if (camera_release_due && !camera_root) camera_release();
  pictures_collect();  // copies no card shows any more, and the oldest over the budget
  // A retry, or an alert's picture that waited for a cover on its way (one picture at a time).
  if (alert_retry_at && now >= alert_retry_at && !cover.loading) {
    alert_retry_at = 0;
    if (!alert_camera.empty() && !alert_url.empty() && camera_thumb.load) {
      alert_thumb_loading = true;
      ESP_LOGI("camera", "alert picture load");
      camera_thumb.load(alert_url);
    }
  }
  cover_tick(now);
  live_tick(now);
  saver_tick(now);
  if (!camera_root || !pictures_awake()) return;
  if (camera.should_ask(now)) {
    if (!fresh()) return;
    camera.ask(now);
    camera_request(camera.entity);
  } else if (camera.should_load(now)) {
    camera_load(now);
  }
}

inline void alert_picture_clear() {
  alert_retry_at = 0;
  if (alert_picture) { lv_obj_delete(alert_picture); alert_picture = nullptr; }
  if (alert_frame_icon) lv_obj_remove_flag(alert_frame_icon, LV_OBJ_FLAG_HIDDEN);
  if (alert_thumb_loading || alert_camera.size()) { if (camera_thumb.release) camera_thumb.release(); }
  alert_thumb_loading = false;
}

// alert_show: the card gets its frame when the app announced a camera for it just before. A new alert closes the camera.
inline void alert_prepare() {
  camera_close();
  alert_picture_clear();
  const bool with_image = camera_supported() && alert_frame && !alert_announced.empty() &&
                          esphome::millis() - alert_announced_at < camera_view::PENDING_MS;
  alert_camera = with_image ? alert_announced : std::string();
  alert_shown_at = esphome::millis();
  alert_url.clear();
  alert_announced.clear();
  if (alert_frame) {
    if (with_image) lv_obj_remove_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
  }
  alert_place(with_image);
}

// alert_dismiss: the frame goes, and so does its image.
inline void alert_clear() {
  alert_picture_clear();
  alert_camera.clear();
  alert_url.clear();
  if (alert_frame) lv_obj_add_flag(alert_frame, LV_OBJ_FLAG_HIDDEN);
}

inline void camera_answer(const std::string &view, const std::string &entity, const std::string &url) {
  if (!camera_supported()) return;
  if (view == "full" || view == "saver") {
    // "saver" (firmware 0.29.0+): the screensaver's picture, into the full view it opened without its keys.
    if (!camera_root || camera.entity != entity || (view == "saver") != saver_camera) return;
    camera.link(url);
    if (url.empty()) {
      if (!camera.shown && !saver_camera) camera_note_text(tr(txt::camera_no_image));
      return;
    }
    // Loaded now rather than on the next tick (firmware 0.2.73+), as an alert's image is.
    const uint32_t now = esphome::millis();
    if (pictures_awake() && camera.should_load(now)) camera_load(now);
    return;
  }
  if (view == "cover") {  // the media card's album cover (firmware 0.2.64+)
    if (!cover.open() || cover.entity != entity) return;
    cover.link(url);
    if (url.empty()) ESP_LOGI("camera", "no cover for %s", entity.c_str());
    if (url.empty() && cover_wish.owner == CoverOwner::PREFETCH) {
      cover_none[cover_none_next++ % cover_none.size()] = cover_key(cover_wish);
      cover_drop();  // the next card's cover may go
    }
    return;
  }
  if (view == "lib") {  // the covers of a page of a player's library (firmware 0.24.0+)
    media_library::art_answer(entity, url);
    return;
  }
  if (view == "live") {  // the page's camera tiles (firmware 0.2.77+): the list as asked, "" where a picture is missing
    if (!live.open() || !same_list(live.entity, entity)) return;
    live_have = entity;
    live.link(url);
    if (url.empty()) { ESP_LOGI("camera", "no live pictures"); live_redraw(); }
    return;
  }
  if (url.empty()) {  // announced before its alert
    alert_announced = entity;
    alert_announced_at = esphome::millis();
    return;
  }
  if (entity != alert_camera || !alert_frame || lv_obj_has_flag(alert_frame, LV_OBJ_FLAG_HIDDEN)) return;
  alert_picture_clear();
  alert_url = url;
  alert_retries = 0;
  // A cover on its way finishes first, and a dropped one is closed first (on the next tick); camera_tick starts this
  // one right after.
  if (cover.loading || camera_release_due) {
    alert_retry_at = esphome::millis() | 1;
    ESP_LOGI("camera", "alert picture waits for the cover");
    return;
  }
  alert_thumb_loading = true;
  ESP_LOGI("camera", "alert picture load");
  camera_thumb.load(url);
}

// LVGL's image widget is only built for a board whose profile draws images (the Guition's hidden seed); the CYD's has none.
// `radius` rounds the picture's corners (the alert's, firmware 0.2.73+): LVGL 9.5's software renderer clips an image
// to its own radius row by row with a one-row mask (radius_only in lv_draw_sw_img.c), without a layer; clip_corner on
// the frame would draw the frame into a layer of its size instead.
inline void camera_show(lv_obj_t *parent, lv_obj_t *&picture, lv_image_dsc_t *source, bool fresh_pixels, int32_t radius = 0) {
#if LV_USE_IMAGE
  if (!source || !source->data) return;
  if (!picture) {
    picture = lv_image_create(parent);
    lv_obj_remove_flag(picture, LV_OBJ_FLAG_CLICKABLE);
    if (radius > 0) lv_obj_set_style_radius(picture, radius, LV_PART_MAIN);
    lv_image_set_src(picture, source);
    lv_obj_center(picture);
    return;
  }
  if (!fresh_pixels) return;
  // The same buffer with new pixels. LVGL keeps no decoded copy of an RGB565 image (its image cache is off in
  // ESPHome's build), so drawing the area again shows them.
  lv_image_set_src(picture, source);
  lv_obj_invalidate(picture);
#else
  (void) parent; (void) picture; (void) source; (void) fresh_pixels; (void) radius;
#endif
}

// The board's online_image triggers. `thumb`: the alert's frame; `cached`: the app answered 304, the image is unchanged.
inline void camera_loaded(bool thumb, bool cached) {
  if (thumb) {
    alert_thumb_loading = false;
    // Only for the alert on screen: a picture that arrives after its alert was dismissed or replaced is not shown.
    if (alert_camera.empty() || !alert_frame || lv_obj_has_flag(alert_frame, LV_OBJ_FLAG_HIDDEN)) return;
    auto *source = camera_thumb.source();
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
    camera_show(alert_frame, alert_picture, source, !cached, lv_obj_get_style_radius(alert_frame, LV_PART_MAIN));
    if (alert_picture && alert_frame_icon) lv_obj_add_flag(alert_frame_icon, LV_OBJ_FLAG_HIDDEN);
    ESP_LOGI("camera", "alert picture shown");
    return;
  }
  if (!camera_root) {
    // The covers of a page of a player's library (firmware 0.24.0+): the same online_image while the library is open.
    if (media_library::art_loading()) { cover_in_flight.clear(); media_library::art_loaded(true); return; }
    // The media card's cover (firmware 0.2.64+): the same online_image, loaded once.
    if (cover.loading) { cover.finish(esphome::millis(), true); ESP_LOGI("camera", "cover loaded"); cover_arrived(); }
    else if (!cover_in_flight.empty()) {
      auto *src = camera_full.source();
      if (src && src->data && pictures.put(cover_in_flight, *src, esphome::millis())) ESP_LOGI("camera", "cover kept for later");
    }
    cover_in_flight.clear();
    return;
  }
  cover_in_flight.clear();      // the buffer is the camera's now: whatever lands next is not that cover
  if (!camera.loading) return;  // a cover's download that ended after the camera opened: not this camera's picture
  camera.finish(esphome::millis(), true);
  lv_image_dsc_t *src = camera_full.source();
  if (src) picture_memory("after", "camera", src->header.w * src->header.h);
  // Drawn from the store's copy, never from the download (firmware 0.13.0+). A download that breaks off halfway (Home
  // Assistant or ESP Screens restarting) makes online_image free its buffer while the view still shows it: the glass
  // kept the old picture, but every part of it drawn again after that, a tile changing underneath, came out black. The
  // copy stays whole until the next picture is. An unchanged picture (304) has its copy already. Without room in the
  // store the view draws the download, as a board without PSRAM does.
  if (!cached && pictures_kept() && src && src->data) {
    if (auto *kept = pictures.put(camera_key(camera.entity), *src, esphome::millis())) src = kept;
    else ESP_LOGW("camera", "no room to keep the picture of %s", camera.entity.c_str());
  }
  const bool first = camera_picture == nullptr;
  camera_show(camera_root, camera_picture, src, !cached);
  if (first && camera_picture && saver_camera) {
    // The screensaver's picture is the whole glass; one that came smaller (the size cap, picture_store::MAX_BYTES) is
    // scaled to it, the same proportions. Its words lie over it.
    lv_obj_set_size(camera_picture, lv_pct(100), lv_pct(100));
    lv_image_set_inner_align(camera_picture, LV_IMAGE_ALIGN_COVER);
    saver_words();
  } else if (camera_picture && saver_camera && saver_words_due) {
    // The next track's picture is on the glass: its words come with it (saver_follow).
    saver_words();
  } else if (first && camera_picture) {
    camera_note_text("");
    if (camera_back) lv_obj_move_foreground(camera_back);
    lv_obj_move_foreground(camera_title);
    // A map's card (firmware 0.21.0+) may have come before its first picture: it lies over the map as the bar does.
    if (map_card_obj) lv_obj_move_foreground(map_card_obj);
  }
  saver_follow_pending();
}

inline void camera_failed(bool thumb) {
  if (thumb) {
    alert_thumb_loading = false;
    ESP_LOGI("camera", "alert picture failed");
    if (!alert_camera.empty() && !alert_picture && alert_retries < ALERT_IMAGE_RETRIES) {
      ++alert_retries;
      alert_retry_at = esphome::millis() + 1500;
    }
    return;
  }
  if (!camera_root) {
    cover_in_flight.clear();
    if (media_library::art_loading()) { media_library::art_loaded(false); return; }
    if (cover.loading) { cover.finish(esphome::millis(), false); ESP_LOGI("camera", "cover failed"); }  // tried again after the gap, three times at most
    return;
  }
  if (!camera.loading) return;
  camera.finish(esphome::millis(), false);
  if (!camera.shown && !saver_camera) camera_note_text(tr(txt::camera_no_image));
  saver_follow_pending();
}

// ---------------------------------------------------------------------------------------------------------
// The screensaver (firmware 0.29.0+, app 0.4.48). When Auto standby dims the screen, a screen whose ESP Screen Manager
// chose a screensaver shows it over the dimmed tiles, at the standby level: the cover of what plays, a camera, or the
// clock. The app decides which (screen_manager/app/screen_saver.py) and says so in a small message whenever that
// changes; the screen keeps the last word and shows it the next time it goes into standby. A cover and a camera are the
// camera's full view without its keys, holding one picture of the whole glass the app made for it (darkened, the cover
// in its colour on long glass, camera_feed.encode_saver) with a line or two of words over it (saver_view.h); the clock
// takes the bedside clock's digits. Nothing on it takes a tap: it lies on the top layer without one clickable object,
// so a finger falls through to dim_wake_overlay and only wakes the screen, the way it always did in standby (and
// wake_tap leaves the tile it lay over alone).
inline std::function<void()> saver_changed;  // the profile's apply_screen_settings, which ends in saver_sync
inline bool saver_lit = false;               // in standby with the backlight on (the standby or night level)
inline uint32_t saver_ticked = 0;
// A camera in standby loads at a live tile's default pace rather than the full view's four seconds: a screensaver can
// stand there all evening, and the Wi-Fi and Home Assistant need not fetch a picture every four seconds for it.
constexpr uint32_t SAVER_CAMERA_MS = 15000;

inline bool saver_wanted() {
  const auto &kind = saver_next.kind;
  return kind == "clock" || ((kind == "media" || kind == "camera") && camera_supported() && valid_entity(saver_next.entity));
}
inline lv_obj_t *saver_text(lv_obj_t *parent, const lv_font_t *font, uint32_t color, const media_card::Rect &r, const std::string &text,
                            lv_text_align_t align = LV_TEXT_ALIGN_CENTER) {
  auto *label = lv_label_create(parent);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  if (font) lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, theme::rgb(color), 0);
  lv_obj_set_style_text_align(label, align, 0);
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_set_pos(label, r.x, r.y);
  // Its own room and no more (firmware 0.30.0+): what does not fit ends in dots instead of running over the next line.
  lv_obj_set_size(label, r.w, r.h);
  lv_label_set_text(label, text.c_str());
  return label;
}

// The clock: the time in the bedside clock's digits where they fit, else the largest digit step that does, and the date
// under it in the card heading's font, white on black whatever the look. In 12 hours AM or PM stands after the time, and
// the outside temperature the app sends stands small in the middle at the bottom (firmware 0.31.0+).
inline void saver_clock_draw() {
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const auto now = now_time ? now_time() : esphome::ESPTime{};
  const std::string time = time_text(now), date = date_text(now), ampm = am_pm(now);
  const std::string &degrees = saver_next.weather;
  const bool large = ui::large();
  const int margin = ui::px(large ? 24 : 10), gap = ui::px(large ? 12 : 6), space = ui::px(large ? 8 : 4);
  const lv_font_t *date_font = watch_font ? watch_font : detail_font;
  const lv_font_t *small = control_font ? control_font : detail_font;
  const int date_h = date_font ? lv_font_get_line_height(date_font) : 24;
  const int small_h = small ? lv_font_get_line_height(small) : 20;
  // AM or PM stands after the time in the small font, and the outside temperature keeps a line at the bottom
  // (firmware 0.31.0+): the digits get the room that is left.
  const int ampm_w = ampm.empty() || !small ? 0 : text_width(ampm, small);
  const int room_w = width - 2 * margin - (ampm_w ? space + ampm_w : 0);
  // The temperature in the date's font: small beside the digits, and as easy to read across a room as the date.
  const int below = degrees.empty() ? 0 : date_h + gap;
  const lv_font_t *digits = bedside_digits();
  if (!digits || text_width(time, digits) > room_w) digits = largest_digits(time.c_str(), room_w, height - 2 * margin - gap - date_h - 2 * below);
  if (!digits) digits = clock_font;
  int top = 0, digits_h = 40;
  if (digits) digit_box(digits, top, digits_h);
  // Black with white digits in both looks (firmware 0.31.0+): a screensaver gives as little light as it can. Before,
  // the clock stood on the page's own colour, a lit white glass in the light look.
  lv_obj_set_style_bg_color(saver_root, theme::color(theme::CAMERA_PAGE), 0);
  const uint32_t ink = media_ink(), soft = theme::mix(ink, theme::hex(theme::CAMERA_PAGE), 150);
  const auto l = saver_view::clock(width, height, digits_h, date.empty() ? 0 : date_h, date.empty() ? 0 : gap);
  const int time_w = digits ? text_width(time, digits) : width;
  const auto row = saver_view::clock_row(width, time_w, ampm_w, space);
  saver_text(saver_root, digits, ink, {row.time_x, l.time.y - top, time_w + 2, digits ? (int) lv_font_get_line_height(digits) : digits_h}, time, LV_TEXT_ALIGN_LEFT);
  if (ampm_w) {
    // On the digits' baseline, as the clock card's own AM and PM.
    int small_top = 0, small_digits = small_h;
    digit_box(small, small_top, small_digits);
    saver_text(saver_root, small, soft, {row.ampm_x, l.time.y + digits_h - small_digits - small_top, ampm_w + 2, small_h}, ampm, LV_TEXT_ALIGN_LEFT);
  }
  if (!date.empty()) saver_text(saver_root, date_font, soft, {margin, l.date.y, width - 2 * margin, date_h}, date);
  if (!degrees.empty() && date_font) saver_text(saver_root, date_font, soft, saver_view::temperature(width, height, margin, date_h), degrees);
}

// Where a player's keys stand on this glass (saver_view::keys), the sizes the media card's keys have: the play key when
// the player can play or pause, the volume keys when it has a volume. A screensaver that is no player has none.
inline saver_view::Keys saver_key_layout() {
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const bool large = ui::large(), media = saver_now.kind == "media";
  using namespace tile_controls;
  media_card::Metrics m;
  m.large = large;
  return saver_view::keys(width, height, ui::px(large ? 28 : 12), m.key_h(), m.play_h(), ui::px(large ? 14 : 8),
                          media && (saver_now.features & (feature::MEDIA_PLAY | feature::MEDIA_PAUSE)),
                          media && (saver_now.features & (feature::MEDIA_VOLUME_SET | feature::ha::media_player::VOLUME_STEP)));
}
// The words over the picture, once it is there: a cover's title with its artist and album, a camera's name alone, in
// white over the darkened picture or the cover's colour.
inline void saver_words() {
  if (!camera_root || !saver_camera) return;
  const auto &c = saver_now;
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  const bool large = ui::large();
  const int margin = ui::px(large ? 28 : 12), gap = ui::px(large ? 4 : 2);
  const lv_font_t *first_font = watch_font ? watch_font : detail_font;
  const lv_font_t *second_font = control_font ? control_font : detail_font;
  const bool media = c.kind == "media";
  const std::string first = media && !c.title.empty() ? c.title : c.name;
  const std::string second = media ? media_card::subtitle(c.artist, c.album) : std::string();
  const lv_font_t *font = media ? first_font : second_font;
  const int first_h = font ? lv_font_get_line_height(font) : 24;
  const int second_h = second.empty() || !second_font ? 0 : lv_font_get_line_height(second_font);
  const auto shape = media ? saver_view::shape(width, height) : saver_view::Shape::fill;
  auto w = saver_view::words(shape, width, height, margin, first_h, second_h, gap);
  // A player's keys stand in the bottom right corner, and the words end before them (firmware 0.33.0+).
  const auto keys = saver_key_layout();
  saver_view::before_keys(w, keys, margin);
  // A long title takes a second line, and the words are laid out again around the taller title (saver_view.h).
  if (font) {
    lv_point_t need;
    lv_text_get_size(&need, first.c_str(), font, 0, 0, w.first.w, LV_TEXT_FLAG_NONE);
    const int lines = saver_view::title_lines(need.y, first_h);
    if (lines > 1) {
      const auto taller = saver_view::words(shape, width, height, margin, lines * first_h, second_h, gap);
      if (saver_view::fits(shape, taller, width, height)) { w = taller; saver_view::before_keys(w, keys, margin); }
    }
  }
  for (lv_obj_t **words : {&saver_first, &saver_second}) if (*words) { lv_obj_delete(*words); *words = nullptr; }
  saver_words_due = false;
  saver_first = saver_text(camera_root, font, media_ink(), w.first, first, LV_TEXT_ALIGN_LEFT);
  if (second_h) saver_second = saver_text(camera_root, second_font, theme::mix(media_ink(), 0, 200), w.second, second, LV_TEXT_ALIGN_LEFT);
  saver_keys_draw();
}
// The keys: white rounds over the darkened cover, the play key whole and the two volume keys a haze with a white sign,
// as the media card's keys stand over its cover. Each takes its own tap (the touch guard first, as every key), sends its
// action for the player on the glass and leaves the screen in standby. The play key turns at once and Home Assistant's
// word follows (saver_tick puts it back when none came).
// Volume down held for a second and a half mutes the player, where Home Assistant says it can be muted; the key then shows the
// muted speaker. The next tap on either volume key takes the mute off and changes nothing else, and after that the two
// are the volume again.
constexpr uint32_t SAVER_MUTE_HOLD_MS = MEDIA_MUTE_HOLD_MS;
inline uint32_t saver_pressed = 0;  // when the finger came down on volume down; 0 once this hold has muted
inline void saver_faces() {
  auto face = [](lv_obj_t *key, const char *glyph) {
    auto *icon = key ? lv_obj_get_child(key, 0) : nullptr;
    if (!icon) return;
    lv_label_set_text(icon, glyph);
    lv_obj_center(icon);
  };
  face(saver_keys[1], saver_now.muted ? tile_controls::glyph::MUTED : tile_controls::glyph::MINUS);
  face(saver_keys[2], saver_now.state == "playing" ? tile_controls::glyph::PAUSE : tile_controls::glyph::PLAY);
}
inline void saver_send(const char *service, const char *key = nullptr, const char *value = nullptr) {
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(service);
  request.data.init(key ? 2 : 1);
  esphome::api::HomeassistantServiceMap target;
  target.key = esphome::StringRef("entity_id");
  target.value = esphome::StringRef(saver_now.entity);
  request.data.push_back(target);
  if (key) {
    esphome::api::HomeassistantServiceMap field;
    field.key = esphome::StringRef(key);
    field.value = esphome::StringRef(value);
    request.data.push_back(field);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("saver", "key %s%s%s for %s", service, value ? " " : "", value ? value : "", saver_now.entity.c_str());
}
inline void saver_mute(bool muted, uint32_t now) {
  saver_send("media_player.volume_mute", "is_volume_muted", muted ? "true" : "false");
  saver_now.muted = muted;
  saver_flipped = now ? now : 1;
  saver_faces();
}
inline void saver_key_event(lv_event_t *e) {
  const int n = (int) (intptr_t) lv_event_get_user_data(e);
  const auto code = lv_event_get_code(e);
  const uint32_t now = esphome::millis();
  if (!saver_camera || saver_now.kind != "media" || !fresh() || !valid_entity(saver_now.entity)) return;
  if (code == LV_EVENT_PRESSED) { saver_pressed = now ? now : 1; return; }
  if (code == LV_EVENT_PRESSING) {
    if (!saver_pressed || now - saver_pressed < SAVER_MUTE_HOLD_MS || saver_now.muted ||
        !(saver_now.features & tile_controls::feature::MEDIA_VOLUME_MUTE)) return;
    saver_pressed = 0;
    if (allowed(now, 703, "screensaver mute")) saver_mute(true, now);
    return;
  }
  if (n == 2) {
    if (!allowed(now, 700, "screensaver play")) return;
    saver_send("media_player.media_play_pause");
    saver_now.state = saver_now.state == "playing" ? "paused" : "playing";
    saver_flipped = now ? now : 1;
    saver_faces();
    return;
  }
  // A volume key, on the release: the hold that muted used this contact up, so it does not also step.
  if (!screen_input::touch_guard.accept_repeat(now, 701 + n)) return;
  if (saver_now.muted) { saver_mute(false, now); return; }
  saver_send(n == 0 ? "media_player.volume_up" : "media_player.volume_down");
}
inline void saver_keys_draw() {
  for (lv_obj_t *&key : saver_keys) if (key) { lv_obj_delete(key); key = nullptr; }
  if (!camera_root || !saver_camera || saver_now.kind != "media") return;
  const auto l = saver_key_layout();
  const uint32_t ink = media_ink();
  const lv_font_t *small = mini_icon_font ? mini_icon_font : detail_font;
  auto key = [&](int n, const media_card::Rect &r, const char *glyph, const lv_font_t *font, bool primary) {
    if (r.w <= 0) return;
    auto *o = lv_obj_create(camera_root);
    lv_obj_remove_style_all(o);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_ext_click_area(o, ui::px(6));
    lv_obj_set_pos(o, r.x, r.y);
    lv_obj_set_size(o, r.w, r.h);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(o, theme::rgb(ink), 0);
    lv_obj_set_style_bg_opa(o, primary ? LV_OPA_COVER : 56, 0);
    lv_obj_set_style_bg_color(o, theme::rgb(primary ? theme::mix(ink, 0, 200) : ink), LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(o, primary ? LV_OPA_COVER : 110, LV_STATE_PRESSED);
    auto *icon = lv_label_create(o);
    lv_obj_remove_flag(icon, LV_OBJ_FLAG_CLICKABLE);
    if (font) lv_obj_set_style_text_font(icon, font, 0);
    lv_obj_set_style_text_color(icon, primary ? theme::color(theme::CAMERA_PAGE) : theme::rgb(ink), 0);
    lv_label_set_text(icon, glyph);
    lv_obj_center(icon);
    // The play key takes a short tap, as every play key; a volume key its release, so a slow press still steps, and
    // volume down also the hold that mutes.
    lv_obj_add_event_cb(o, saver_key_event, n == 2 ? LV_EVENT_SHORT_CLICKED : LV_EVENT_CLICKED, (void *) (intptr_t) n);
    if (n == 1) {
      lv_obj_add_event_cb(o, saver_key_event, LV_EVENT_PRESSED, (void *) (intptr_t) n);
      lv_obj_add_event_cb(o, saver_key_event, LV_EVENT_PRESSING, (void *) (intptr_t) n);
    }
    saver_keys[n] = o;
  };
  key(0, l.plus, tile_controls::glyph::PLUS, small, false);
  key(1, l.minus, saver_now.muted ? tile_controls::glyph::MUTED : tile_controls::glyph::MINUS, small, false);
  key(2, l.play, saver_now.state == "playing" ? tile_controls::glyph::PAUSE : tile_controls::glyph::PLAY, tile_icon_font(), true);
}

inline void saver_hide() {
  saver_follow_due = false;
  if (saver_root) lv_obj_delete(saver_root);
  saver_root = nullptr;
  if (saver_camera) camera_close();
  saver_camera = false;
  saver_now = SaverChoice{};
  saver_pictures = false;
}
inline void saver_show() {
  saver_now = saver_next;
  saver_pictures = saver_now.kind != "clock";
  if (saver_pictures) {
    // The full view, asked for as the screensaver's picture (camera_request adds what it shows), then stripped of its
    // keys, its name and its spinner, and laid under an alert that may come.
    saver_camera = true;
    camera_open(saver_now.entity, saver_now.name, -1, "");
    if (!camera_root) { saver_camera = false; return; }
    lv_obj_remove_flag(camera_root, LV_OBJ_FLAG_CLICKABLE);
    for (lv_obj_t **part : {&camera_back, &camera_title, &camera_spinner}) if (*part) { lv_obj_delete(*part); *part = nullptr; }
    lv_obj_move_to_index(camera_root, 0);
    // A camera refreshes at its pace; a cover loads once, and a new track is a new picture (saver_sync).
    if (saver_now.kind == "media") camera.once = true;
    else camera.every = SAVER_CAMERA_MS;
    ESP_LOGI("saver", "%s %s", saver_now.kind.c_str(), saver_now.entity.c_str());
    return;
  }
  saver_root = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(saver_root);
  lv_obj_remove_flag(saver_root, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(saver_root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(saver_root, lv_pct(100), lv_pct(100));
  lv_obj_set_style_bg_opa(saver_root, LV_OPA_COVER, 0);
  lv_obj_move_to_index(saver_root, 0);
  saver_clock_draw();
  ESP_LOGI("saver", "clock");
}
// Another track, another cover or another picture step while a picture stands (firmware 0.32.0+): the view stays, with
// the picture and its words, and the next picture loads under it; the words change when it has come. Before, the view
// closed and opened again, and the glass stood black for as long as the next picture took.
inline void saver_follow() {
  const std::string before = camera.entity;
  // The same picture with other words (the title came before the cover's colour, or the other way round): the words
  // alone, nothing loads; while that picture is still on its way, they come with it.
  // The cover's colour only shows beside a cover on long glass (saver_view::shape): on square glass it is no new picture.
  const bool ground_shows = saver_view::shape(overlay_card::screen_width(), overlay_card::screen_height()) != saver_view::Shape::fill;
  if (saver_next.kind == saver_now.kind && saver_next.entity == saver_now.entity && saver_next.picture == saver_now.picture &&
      (saver_next.ground == saver_now.ground || !ground_shows)) {
    saver_now = saver_next;
    if (!saver_words_due) saver_words();
    else saver_keys_draw();
    return;
  }
  if (camera.loading) { saver_follow_due = true; return; }
  saver_follow_due = false;
  saver_now = saver_next;
  saver_keys_draw();  // the keys are the next player's at once; its words wait for its picture
  camera.open(saver_now.entity);
  if (saver_now.kind == "media") camera.once = true;
  else camera.every = SAVER_CAMERA_MS;
  // The last one's copy goes once its picture has made way for the next (pictures_collect).
  if (before != saver_now.entity) pictures.retire(camera_key(before));
  saver_words_due = true;
  ESP_LOGI("saver", "%s %s, the last picture stays until it comes", saver_now.kind.c_str(), saver_now.entity.c_str());
}
inline void saver_follow_pending() {
  if (!std::exchange(saver_follow_due, false)) return;
  if (saver_lit && saver_camera && camera_root && camera_picture && !(saver_next == saver_now) &&
      (saver_next.kind == "media" || saver_next.kind == "camera")) saver_follow();
}
// apply_screen_settings, after every change and every minute: `lit` is standby with a backlight that is on.
inline void saver_sync(bool lit) {
  saver_lit = lit;
  const bool shown = saver_root || saver_camera;
  if (!lit || !saver_wanted()) { if (shown) saver_hide(); return; }
  // The camera and the cover stand as they are while nothing changed; the clock is drawn again, a minute later.
  if (shown && saver_next == saver_now && saver_now.kind != "clock") return;
  if (saver_camera && camera_root && camera_picture && (saver_next.kind == "media" || saver_next.kind == "camera")) { saver_follow(); return; }
  saver_hide();
  saver_show();
}
// wake_display: the screensaver goes, and the touch that woke the screen does nothing else.
inline void saver_wake() {
  saver_lit = false;
  saver_woke = saver_root || saver_camera;
  saver_hide();
}
// A new layout on its way (cancel_layout_input): every picture goes; saver_tick draws the screensaver again.
inline void saver_forget() { saver_hide(); }
// The app's word (page_receiver.cpp). In standby the glass follows at once, through apply_screen_settings.
inline void saver_receive(const SaverChoice &next) {
  if (next == saver_next) return;
  saver_next = next;
  if (!awake() && saver_changed) saver_changed();
}
inline void saver_tick(uint32_t now) {
  if (now - saver_ticked < 1000) return;
  saver_ticked = now;
  // A play key that turned ahead of Home Assistant and heard nothing shows what the app last said again.
  if (saver_flipped && now - saver_flipped > 5000) {
    saver_flipped = 0;
    if (saver_camera && saver_now.entity == saver_next.entity &&
        (saver_now.state != saver_next.state || saver_now.muted != saver_next.muted)) {
      saver_now.state = saver_next.state;
      saver_now.muted = saver_next.muted;
      saver_faces();
    }
  }
  // Gone under it (a new layout, an alert that closed the camera): drawn again.
  if (saver_lit && !saver_root && !saver_camera && saver_wanted()) saver_show();
}

// ---------------------------------------------------------------------------------------------------------
// What a finger on the glass does (firmware 0.2.80). ESPHome gives a board three touchscreen triggers, and
// what they did used to be copied into every board file: 55 of the Waveshare's 62 lines were word for word the
// Guition's. A new board took `on_touch` and not the other two, so one tap worked and nothing after it -- the
// guard waited for a release that was never reported. It is behaviour, not hardware, so it lives here once and
// a board's triggers are one line each. The boot lambda of packages/core.yaml hands over the four things that
// live in the YAML.
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

// The edge swipe of every board, in the touchscreen's own coordinates: where a touch starts, where it goes, and when
// it ends. The capacitive boards feed it from pressed, moved and released below; the resistive ones call these three
// from their own triggers (features/resistive-touch.yaml), where only the top and the bottom band are armed.
inline void edge_press(int x, int y) {
  int sx = x, sy = y;
  screen_point(sx, sy);
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
  const auto gesture = screen_input::edge_swipe.update(sx, sy);
  if (gesture == Gesture::none) return;
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
  if (screen_input::edge_swipe.armed() && screen_input::edge_swipe.inward() > 0)
    ESP_LOGI("touch", "edge swipe not fired: %d px travelled, %d px across", screen_input::edge_swipe.inward(), screen_input::edge_swipe.sideways());
  screen_input::edge_swipe.end();
}

inline void pressed(int x, int y, int id, bool calibrating) {
  if (contact) contact(true);
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
  // Swiping in from an edge ("Swiping between pages"); the tap under the finger is consumed and LVGL waits for the
  // release. LVGL 9.5 sends no PRESSING to the input device, hence the touchscreen trigger.
  edge_move(x, y);
}

inline void released() {
  if (contact) contact(false);
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
  cover_drop();
  live_release();
  history_asked_entity.clear();
  history = History{};
  if (invalidate_widgets) {
    for (auto &w : widgets) { w.index = grid.max_tiles(); w.cached_active = -1; }
    forget_kept();
    if (layout_changed) layout_changed();
  }
}
}  // namespace runtime_tiles
