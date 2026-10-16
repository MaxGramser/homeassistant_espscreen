// The plugin API's core side (plugin_api.h, plugin_host.h, docs/PLUGINS.md). Apart from main.cpp, as energy_view.cpp
// and page_receiver.cpp are: main.cpp's literal pool is close to the S3's l32r range.
// USE_TESSERA_PLUGINS: set by smart_display.register_plugin() when the build has a plugin. Without one this file holds
// only the stubs at its end, and leaves runtime_tiles.h out: every file that includes it pays for its globals' start-up.
#ifndef ESP_SCREEN_HOST  // the WASM preview has no ESPHome defines (and no plugins)
#include "esphome/core/defines.h"
#endif
#ifdef USE_TESSERA_PLUGINS
#include "esphome/core/application.h"
#include "runtime_tiles.h"
#include "plugin_host.h"
#include "plugin_api.h"
#include "touch_feedback_lvgl.h"
#include "plugin_action.h"
#include <algorithm>
#include <functional>
#include <memory>
#include <string_view>
#include <vector>

// The documents the host parses a plugin tile's options and data into, and builds a question in: PSRAM first, as the
// texts they come from (roomy.h).
namespace {
struct RoomyJson : ArduinoJson::Allocator {
  void *allocate(size_t size) override { return roomy::allocate(size); }
  void deallocate(void *pointer) override { roomy::release(pointer); }
  void *reallocate(void *pointer, size_t size) override { return roomy::reallocate(pointer, size); }
};
RoomyJson json_memory;
}  // namespace

namespace rt = runtime_tiles;
namespace plugin_host { extern tessera::Point tapped; }
// ---- The register (plugin_api.h) ----
namespace tessera {

std::vector<Plugin *> &plugins() {
  static std::vector<Plugin *> list;
  return list;
}
std::vector<TileType> &tile_types() {
  static std::vector<TileType> list;
  return list;
}
const TileType *tile_type(const std::string &key) {
  for (const auto &type : tile_types())
    if (type.key == key) return &type;
  return nullptr;
}

std::vector<CardType> &card_types() {
  static std::vector<CardType> list;
  return list;
}
std::vector<TapAction> &tap_actions() {
  static std::vector<TapAction> list;
  return list;
}

std::vector<BarItemType> &bar_items() {
  static std::vector<BarItemType> list;
  return list;
}

Plugin::Plugin() { plugins().push_back(this); }

void Plugin::add_bar_item(const char *id, std::function<BarItem()> read) {
  std::string key = std::string("plugin:") + plugin_id() + "." + id;
  for (auto &item : bar_items())
    if (item.key == key) { item.read = std::move(read); return; }
  bar_items().push_back({this, id, std::move(key), std::move(read)});
}

void Plugin::add_card(const char *id, std::function<Card *()> make, bool wide) {
  std::string key = std::string("plugin:") + plugin_id() + "." + id;
  for (auto &type : card_types())
    if (type.key == key) { type.make = std::move(make); type.wide = wide; return; }
  card_types().push_back({this, id, std::move(key), wide, std::move(make)});
}

void Plugin::add_tap_action(const char *id, std::function<void(const TapContext &)> run) {
  std::string key = std::string("plugin:") + plugin_id() + "." + id;
  for (auto &action : tap_actions())
    if (action.key == key) { action.run = std::move(run); return; }
  tap_actions().push_back({this, id, std::move(key), std::move(run)});
}

void Plugin::add_tile(const char *id, std::function<Tile *()> make) {
  std::string key = std::string("plugin:") + plugin_id() + "." + id;
  for (auto &type : tile_types())
    if (type.key == key) { type.make = std::move(make); return; }
  tile_types().push_back({this, id, std::move(key), std::move(make)});
}

const char *Plugin::text(const char *key) const {
  for (const auto &pair : texts_)
    if (strcmp(pair.first, key) == 0) return pair.second;
  return "";
}

uint16_t Plugin::memory(const std::string &tile) const {
  for (const auto &pair : memory_)
    if (tile == pair.first) return pair.second;
  return 1024;
}

SettingsPage &SettingsPage::toggle(const char *label, std::function<bool()> read, std::function<void(bool)> write) {
  Item item{Item::TOGGLE};
  item.label = label ? label : "";
  item.read = [read]() { return read && read() ? 1 : 0; };
  item.write = [write](int on) { if (write) write(on != 0); };
  items.push_back(std::move(item));
  return *this;
}
SettingsPage &SettingsPage::number(const char *label, int low, int high, int step, const char *unit,
                                   std::function<int()> read, std::function<void(int)> write) {
  Item item{Item::NUMBER};
  item.label = label ? label : "";
  item.low = low; item.high = high; item.step = step > 0 ? step : 1;
  item.unit = unit ? unit : "";
  item.read = std::move(read); item.write = std::move(write);
  items.push_back(std::move(item));
  return *this;
}
SettingsPage &SettingsPage::choice(const char *label, std::vector<std::string> options, std::function<int()> read,
                                   std::function<void(int)> write) {
  Item item{Item::CHOICE};
  item.label = label ? label : "";
  item.options = std::move(options);
  item.read = std::move(read); item.write = std::move(write);
  items.push_back(std::move(item));
  return *this;
}
SettingsPage &SettingsPage::action(const char *label, const char *icon, std::function<void()> run, const char *confirm,
                                   std::function<std::string()> text) {
  Item item{Item::ACTION};
  item.label = label ? label : "";
  item.icon = icon ? icon : "";
  item.confirm = confirm ? confirm : "";
  item.run = std::move(run);
  item.text = std::move(text);
  items.push_back(std::move(item));
  return *this;
}
SettingsPage &SettingsPage::active(std::function<bool()> running) {
  if (!items.empty() && items.back().kind == Item::ACTION) items.back().active = std::move(running);
  return *this;
}
SettingsPage &SettingsPage::info(const char *label, std::function<std::string()> text) {
  Item item{Item::INFO};
  item.label = label ? label : "";
  item.text = std::move(text);
  items.push_back(std::move(item));
  return *this;
}
SettingsPage &SettingsPage::card(const char *label, const char *icon, const char *card) {
  Item item{Item::CARD};
  item.label = label ? label : "";
  item.icon = icon ? icon : "";
  item.card = card ? card : "";
  items.push_back(std::move(item));
  return *this;
}

uint32_t epoch() { return rt::now_epoch(); }

LocalTime local_time(uint32_t when) {
  const esphome::ESPTime t = esphome::ESPTime::from_epoch_local(when);
  return {t.year, t.month, t.day_of_month, t.hour, t.minute, t.second, t.day_of_week};
}

std::string clock_text(uint32_t when) {
  if (!when) return "";
  const esphome::ESPTime moment = esphome::ESPTime::from_epoch_local(when);
  return screen_text::clock_text(rt::hhmm(moment), screen_settings::current.clock_24h != 0);
}

std::string format(const char *text, long n) {
  std::string all = text ? text : "", form = all;
  if (all.find('|') != std::string::npos) {
    int wanted = screen_text::plural_index(static_cast<int>(n));
    size_t start = 0;
    for (int i = 0; i < wanted; ++i) {
      size_t bar = all.find('|', start);
      if (bar == std::string::npos) break;
      start = bar + 1;
    }
    size_t end = all.find('|', start);
    form = all.substr(start, end == std::string::npos ? std::string::npos : end - start);
    size_t first = form.find_first_not_of(' '), last = form.find_last_not_of(' ');
    form = first == std::string::npos ? std::string() : form.substr(first, last - first + 1);
  }
  return screen_text::fill(form, "n", std::to_string(n));
}

// Days since 1970 of a civil date (Howard Hinnant's days_from_civil), so two local dates subtract to whole days.
static int32_t civil_days(int year, unsigned month, unsigned day) {
  year -= month <= 2;
  const int era = (year >= 0 ? year : year - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(year - era * 400);
  const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + static_cast<int32_t>(doe) - 719468;
}
static int32_t local_day(uint32_t epoch) {
  const esphome::ESPTime t = esphome::ESPTime::from_epoch_local(epoch);
  return civil_days(t.year, t.month, t.day_of_month);
}

int32_t days_from_today(uint32_t when) {
  const uint32_t now = rt::now_epoch();
  if (!now || !when) return INT32_MIN;
  return local_day(when) - local_day(now);
}

std::string date_text(uint32_t when) {
  if (!when) return "";
  const esphome::ESPTime t = esphome::ESPTime::from_epoch_local(when);
  return header_bar::date_text(t.day_of_week, t.day_of_month, t.month);
}

std::string days_text(int32_t days) {
  if (days == 1) return screen_text::tr(screen_text::txt::time_tomorrow);
  if (days > 1) return screen_text::plural(screen_text::txt::time_in_days, days);
  return "";
}

std::string fill(const char *text, const char *name, const std::string &value) {
  return screen_text::fill(std::string(text ? text : ""), name, value);
}

bool action(const char *service, const std::string &entity, const char *key, const std::string &value) {
  if (!service || !rt::entity_id(entity) || entity.rfind("screen.", 0) == 0) return false;
  return rt::action(service, entity, key ? key : "", value);
}

// An action with fields of any JSON type (0.12): each field as plugin_action.h writes it for Home Assistant, through
// the screen's own route as a tap's action goes (the screen must be allowed to perform actions).
bool action(const char *service, const std::string &entity, JsonVariantConst fields) {
  static const char *const TAG = "plugin_action";
  if (!service || !plugin_action::service_name(service) || !fields.is<JsonObjectConst>()) {
    ESP_LOGW(TAG, "Not sent: %s needs a service as domain.action and its fields as an object", service ? service : "");
    return false;
  }
  if (!entity.empty() && (!rt::entity_id(entity) || entity.rfind("screen.", 0) == 0)) return false;
  std::vector<plugin_action::Field> list;
  for (JsonPairConst pair : fields.as<JsonObjectConst>()) {
    plugin_action::Field field{pair.key().c_str(), pair.value().is<const char *>(), ""};
    if (field.text) field.value = pair.value().as<const char *>();
    else serializeJson(pair.value(), field.value);
    list.push_back(std::move(field));
  }
  plugin_action::Encoded encoded;
  const char *why = "";
  if (!plugin_action::encode(entity, list, encoded, &why)) {
    ESP_LOGW(TAG, "Not sent: %s %s", service, why);
    return false;
  }
  if (!rt::fresh()) return false;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef(service);
  request.data.init(encoded.data.size());
  for (const auto &pair : encoded.data) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(pair.first);
    entry.value = esphome::StringRef(pair.second);
    request.data.push_back(entry);
  }
  request.data_template.init(encoded.templates.size());
  for (const auto &pair : encoded.templates) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(pair.first);
    entry.value = esphome::StringRef(pair.second);
    request.data_template.push_back(entry);
  }
  // With an entity its tiles wait for the answer as for a tap; without one (the fields name their own target, or
  // there is none) nobody waits.
  if (entity.empty()) esphome::api::global_api_server->send_homeassistant_action(request);
  else rt::send_action(request, entity, true);
  ESP_LOGI(TAG, "Sent service=%s entity=%s (%u values)", service, entity.c_str(),
           (unsigned) (encoded.data.size() + encoded.templates.size()));
  return true;
}

bool open_card(const char *plugin_id, const char *card, const std::string &entity, int tile, const std::string &title) {
  return plugin_host::open_card(std::string("plugin:") + (plugin_id ? plugin_id : "") + "." + (card ? card : ""), entity,
                                tile, title);
}

void close_card() { plugin_host::close_card(); }

Point tap_point() { return plugin_host::tapped; }

uint32_t send(const Plugin *plugin, JsonObjectConst request) {
  static uint32_t next = 0;
  if (!plugin || rt::inbox.empty() || !esphome::api::global_api_server) return 0;
  JsonDocument doc(&json_memory);
  doc.set(request);
  const uint32_t number = ++next;
  doc["re"] = number;
  std::string body;
  serializeJson(doc, body);
  if (body.size() > 512) return 0;
  esphome::api::HomeassistantActionRequest action;
  action.service = esphome::StringRef("esphome.screen_plugin");
  action.is_event = true;
  const std::string session = rt::protocol_key(rt::transfer.lease);
  const std::string keys[] = {"inbox", "plugin", "session", "rev", "body"};
  const std::string values[] = {rt::inbox, plugin->plugin_id(), session, rt::layout_rev, body};
  action.data.init(5);
  for (int i = 0; i < 5; ++i) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(keys[i]);
    entry.value = esphome::StringRef(values[i]);
    action.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(action);
  return number;
}

// A tone as the screen's colours (plugin API 0.8): the accent of the look, Home Assistant's amber and red made readable
// in it; false for NORMAL, which keeps what the place has.
static bool tone_color(Tone tone, uint32_t &color) {
  switch (tone) {
    case Tone::ACCENT: color = theme::hex(theme::ACCENT); return true;
    case Tone::BUSY: color = theme::foreground(theme::ha::AMBER); return true;
    case Tone::ALERT: color = theme::foreground(theme::ha::RED); return true;
    case Tone::GOOD: color = theme::foreground(theme::ha::GREEN); return true;
    default: return false;
  }
}

void refresh() {
  for (auto &w : rt::widgets)
    if (w.plugin && w.index < rt::model.count) rt::mark_tile(w.index);
  if (rt::refresh) rt::refresh();
}

namespace ui {
// The screen's fixed fonts (docs/RESPONSIVE.md, "Fonts"), the ones packages/core.yaml hands runtime_tiles at boot: the
// same ids on every board, sized by its look. Nothing here depends on which tiles happen to stand on the glass.
const lv_font_t *font(Font f) {
  const lv_font_t *face = nullptr;
  switch (f) {
    case Font::VALUE: face = rt::watch_value_font; break;       // watch_value
    case Font::HEADLINE: face = rt::watch_font; break;          // headline
    case Font::TITLE: face = rt::label_font; break;             // label: a tile's name
    case Font::BODY_LARGE: face = rt::control_font; break;      // sublabel_big: the words on a key
    case Font::BODY: face = rt::small_font; break;              // sublabel: a tile's value, a card's second line
    case Font::ICON: face = rt::tile_icon_font(); break;        // materialdesign_icons
    case Font::ICON_SMALL: face = rt::mini_icon_font; break;    // materialdesign_icons_mini
    case Font::DIGITS: face = rt::setpoint_font ? rt::setpoint_font : rt::watch_value_font; break;  // setpoint_digits
  }
  // Before boot handed them over (never on a screen: plugins are made after on_boot), the nearest that is there.
  if (!face) face = rt::small_font ? rt::small_font : rt::control_font ? rt::control_font : rt::detail_font;
  return face;
}

int text_width(const std::string &text, Font f) {
  const lv_font_t *face = font(f);
  return face ? rt::text_width(text, face) : 0;
}

bool covers(const std::string &text, Font f) {
  const lv_font_t *face = font(f);
  return face && rt::face_covers(face, text);
}

lv_obj_t *label(lv_obj_t *parent, Font f, theme::Role role) {
  lv_obj_t *l = lv_label_create(parent);
  lv_obj_remove_flag(l, LV_OBJ_FLAG_CLICKABLE);
  lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
  lv_label_set_text(l, "");
  if (const lv_font_t *face = font(f)) {
    lv_obj_set_style_text_font(l, face, 0);
    // One line high, as the label promises: with LVGL's own height a text too long for its width wraps onto a second
    // line (outside a tile) instead of ending in dots.
    lv_obj_set_height(l, lv_font_get_line_height(face));
  }
  lv_obj_set_style_text_color(l, theme::color(role), 0);
  return l;
}

void set_text(lv_obj_t *l, const std::string &text) { if (l) rt::label(l, text); }
void set_font(lv_obj_t *l, Font f) {
  const lv_font_t *face = font(f);
  if (!face || !l) return;
  // A label one line of its old font high stays one line high in the new one; a height of the plugin's own stays.
  const lv_font_t *was = lv_obj_get_style_text_font(l, LV_PART_MAIN);
  const bool one_line = was && lv_obj_get_style_height(l, LV_PART_MAIN) == lv_font_get_line_height(was);
  rt::set_font(l, face);
  if (one_line && lv_obj_get_style_height(l, LV_PART_MAIN) != lv_font_get_line_height(face))
    lv_obj_set_height(l, lv_font_get_line_height(face));
}
void set_color(lv_obj_t *l, theme::Role role) {
  if (l) rt::set_color(l, LV_STYLE_TEXT_COLOR, theme::color(role));
}

void set_tone(lv_obj_t *l, Tone tone, theme::Role normal) {
  if (!l) return;
  uint32_t color = 0;
  if (!::tessera::tone_color(tone, color)) return set_color(l, normal);
  rt::set_color(l, LV_STYLE_TEXT_COLOR, lv_color_hex(color));
}

lv_color_t tone_color(Tone tone, theme::Role normal) {
  uint32_t color = 0;
  return ::tessera::tone_color(tone, color) ? lv_color_hex(color) : theme::color(normal);
}

void set_fill(lv_obj_t *block, Tone tone, theme::Role normal) {
  if (block) rt::set_color(block, LV_STYLE_BG_COLOR, tone_color(tone, normal));
}

lv_obj_t *block(lv_obj_t *parent, theme::Role fill) {
  lv_obj_t *b = lv_obj_create(parent);
  lv_obj_remove_style_all(b);
  lv_obj_remove_flag(b, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(b, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(b, theme::color(fill), 0);
  lv_obj_set_style_radius(b, ::ui::px(::ui::large() ? 12 : 8), 0);
  return b;
}

std::string icon(uint32_t codepoint) { return tile_icon::utf8(codepoint); }
}  // namespace ui

}  // namespace tessera

// ---- Plugin tiles in cards (plugin_host.h) ----
namespace plugin_host {

// A place for a picture on a plugin tile's card (plugin API 0.10, ui::picture): the block the plugin laid out, the
// image object that draws its piece of the card's atlas once that is here, and what it shows.
struct Place {
  lv_obj_t *place = nullptr, *image = nullptr;
  std::string url;
  bool contain = false;
  uint8_t turn = 0;      // tessera::Turn
  bool mirror = false;
};
struct Card : tessera::InPsram {   // PSRAM first, as the plugin's own objects (roomy.h)
  std::unique_ptr<tessera::Tile> tile;
  std::string entity;          // what the card was made for: the tile type,
  size_t index = SIZE_MAX;     // the tile of the layout,
  int width = 0, height = 0;   // its room,
  size_t options = 0;          // and its options (a hash)
  size_t state = 0;            // the data it was last given (a hash), 0 for none yet
  bool dark = false;           // the look it last coloured itself for
  std::vector<Place> places;   // its places for pictures, in the order the tile made them
};

// A text's hash, never 0 (0 is "nothing yet"), for a string of any allocator (roomy.h).
template <class S> static size_t hash(const S &text) { return std::hash<std::string_view>{}(std::string_view(text.data(), text.size())) | 1; }

// The card whose tile is in a call of the host (create, on_state, on_tick, on_theme, on_tap): a place the tile makes
// in that call is this card's. Nothing else of a tile's runs (a plugin's own moments are the plugin's, not a tile's).
static Card *making = nullptr;
// The places a call of the host makes pictures in (ui::picture): the tile's in a call of a tile, the open card's in a
// call of a card (0.13), nullptr outside both.
static std::vector<Place> *placing = nullptr;
struct Making {
  Card *was;
  std::vector<Place> *had;
  explicit Making(Card *card) : was(making), had(placing) { making = card; placing = card ? &card->places : nullptr; }
  ~Making() { making = was; placing = had; }
};
// The places of the plugin card open over the page (0.13), nullptr when none is (defined with the cards below).
static std::vector<Place> *card_places();

bool known(const rt::Tile &t) { return tessera::tile_type(t.entity) != nullptr; }

void release(rt::Widgets &w) {
  if (!w.plugin) return;
  delete w.plugin;  // the plugin's parts are the extra layer's children: whoever releases the card cleans that
  w.plugin = nullptr;
}

void render(rt::Widgets &w, const rt::Tile &t, int width, int height) {
  const tessera::TileType *type = tessera::tile_type(t.entity);
  if (!type || !type->make) return;
  rt::begin_extra(w, "plugin", width, height);
  const auto &extra = t.extra();
  const size_t options = (hash(extra.plugin_options) * 31u ^ hash(extra.plugin_entity)) | 1;
  Card *card = w.plugin;
  if (card && (card->entity != t.entity || card->index != w.index || card->width != width || card->height != height ||
               card->options != options)) {
    release(w);
    lv_obj_clean(w.extra);
    card = nullptr;
  }
  if (!card) {
    lv_obj_clean(w.extra);
    std::unique_ptr<tessera::Tile> tile(type->make());
    if (!tile) return;
    card = w.plugin = new Card();
    card->tile = std::move(tile);
    card->entity = t.entity;
    card->index = w.index;
    card->width = width;
    card->height = height;
    card->options = options;
    card->dark = theme::dark;
    JsonDocument doc(&json_memory);
    if (extra.plugin_options.empty() || deserializeJson(doc, extra.plugin_options.data(), extra.plugin_options.size()))
      doc.to<JsonObject>();
    tessera::TileContext context{w.extra, width, height, static_cast<uint8_t>(t.column_span()),
                                 static_cast<uint8_t>(t.row_span()), t.name.c_str(), extra.plugin_entity.c_str(),
                                 static_cast<int>(w.index), doc.as<JsonObjectConst>()};
    Making call(card);
    card->tile->create(context);
  }
  Making call(card);
  const size_t state = hash(extra.plugin_state);
  if (card->state != state) {
    card->state = state;
    JsonDocument doc(&json_memory);
    if (extra.plugin_state.empty() || deserializeJson(doc, extra.plugin_state.data(), extra.plugin_state.size()))
      doc.to<JsonObject>();
    card->tile->on_state(doc.as<JsonObjectConst>());
    card->tile->on_tick(rt::now_epoch());
  }
  if (card->dark != theme::dark) {
    card->dark = theme::dark;
    card->tile->on_theme();
    // The blocks under the pictures follow the look as every block does; the pictures themselves are asked again in
    // it (the look is in their key), with the card's ground of that look behind their corners.
    for (auto &p : card->places) rt::set_color(p.place, LV_STYLE_BG_COLOR, theme::color(theme::TRACK));
  }
  // Its pictures, from the store when it has them (a page that comes back, a card made anew for the same tile).
  if (!card->places.empty()) rt::tile_picture_place(w, t, 0, 0, 0);
}

// Where the finger of the tap under way was, in the tile's own pixels (tessera::tap_point).
tessera::Point tapped;

void tap(rt::Widgets &w, int x, int y) {
  if (!w.plugin || !w.plugin->tile) return;
  tapped = {-1, -1};
  if (x >= 0 && y >= 0 && w.extra) {
    lv_area_t area;
    lv_obj_get_coords(w.extra, &area);
    tapped = {x - area.x1, y - area.y1};
  }
  Making call(w.plugin);
  w.plugin->tile->on_tap();
}

static void tick_card(uint32_t epoch);

void tick_cards(uint32_t epoch) {
  tick_card(epoch);
  for (auto &w : rt::widgets) {
    if (!w.plugin || !w.tile || !w.extra || w.extra_mode != "plugin" || w.index >= rt::model.count) continue;
    if (lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) || lv_obj_has_flag(w.extra, LV_OBJ_FLAG_HIDDEN)) continue;
    Making call(w.plugin);
    w.plugin->tile->on_tick(epoch);
  }
}

// ---- A plugin tile's pictures (plugin API 0.10, tile_picture.h "parts") ----
// The places with an address that lie within the card, as the parts of one picture, in the order the tile made them,
// and the place each part is; the atlas's scale for them (a card over the cap comes smaller as a whole). The card's
// layout is brought up to date first, so a place moved in on_tick is measured where it is now.
// `frame` is what the places are measured from: a tile's card, or a plugin card's room (0.13).
static int measure(lv_obj_t *frame, std::vector<Place> &places, std::vector<tile_picture::Part> &parts,
                   std::vector<Place *> &owners) {
  parts.clear();
  owners.clear();
  if (!frame) return picture_store::SCALE_ONE;
  lv_obj_update_layout(frame);
  lv_area_t card;
  lv_obj_get_coords(frame, &card);
  const int cw = lv_area_get_width(&card), ch = lv_area_get_height(&card);
  int right = 0, bottom = 0;
  for (auto &p : places) {
    if (p.url.empty() || !p.place || lv_obj_has_flag(p.place, LV_OBJ_FLAG_HIDDEN)) continue;
    lv_area_t at;
    lv_obj_get_coords(p.place, &at);
    tile_picture::Part part;
    // Where the tile laid the place out: a slide (ui::slide_pictures) moves it only until its next picture is here.
    part.x = at.x1 - card.x1 - lv_obj_get_style_translate_x(p.place, LV_PART_MAIN);
    part.y = at.y1 - card.y1;
    part.w = lv_area_get_width(&at);
    part.h = lv_area_get_height(&at);
    // A place outside the card, or over its edge, is not asked for: the app refuses a frame beyond the glass, and
    // the card would cut it anyway.
    if (part.w <= 0 || part.h <= 0 || part.x < 0 || part.y < 0 || part.x + part.w > cw || part.y + part.h > ch) continue;
    part.radius = lv_obj_get_style_radius(p.place, LV_PART_MAIN);
    part.url = p.url;
    part.contain = p.contain;
    part.turn = p.turn;
    part.mirror = p.mirror;
    parts.push_back(std::move(part));
    owners.push_back(&p);
    right = std::max(right, part.x + part.w);
    bottom = std::max(bottom, part.y + part.h);
    if (parts.size() == tile_picture::MAX_PARTS) break;
  }
  return picture_store::fit_scale(right, bottom, rt::picture_cap());
}
static int measure(const rt::Widgets &w, std::vector<tile_picture::Part> &parts, std::vector<Place *> &owners) {
  if (!w.plugin || !w.tile) { parts.clear(); owners.clear(); return picture_store::SCALE_ONE; }
  return measure(w.tile, w.plugin->places, parts, owners);
}

bool pictured(const rt::Widgets &w) {
  if (!w.plugin) return false;
  for (const auto &p : w.plugin->places) if (!p.url.empty() && p.place) return true;
  return false;
}

bool picture_ask(const rt::Widgets &w, const rt::Tile &t, tile_picture::Ask &a) {
  std::vector<tile_picture::Part> parts;
  std::vector<Place *> owners;
  measure(w, parts, owners);
  if (parts.empty()) return false;
  // Behind the pictures' corners the card's own colour, as behind a tile's picture over its whole card.
  const uint32_t ground = t.transparent ? theme::hex(theme::PAGE) : theme::surface(t.background);
  tile_picture::set_parts(a, std::move(parts), ground, rt::picture_cap());
  a.index = w.index;
  a.entity = t.entity;
  a.dark = theme::dark;
  return true;
}

// A place without its picture: its block again, drawing nothing of the store.
static void place_clear(Place &p) {
#if LV_USE_IMAGE
  if (p.image) {
    lv_image_set_src(p.image, nullptr);
    lv_obj_add_flag(p.image, LV_OBJ_FLAG_HIDDEN);
  }
#endif
  if (p.place) rt::set_number(p.place, LV_STYLE_BG_OPA, LV_OPA_COVER);
}

// The places back where the tile laid them out, the moment another picture (or none) takes the place of what they
// showed during a slide.
static void slide_back(std::vector<Place> &places) {
  for (auto &p : places) {
    if (!p.place) continue;
    lv_anim_delete(p.place, nullptr);
    if (lv_obj_get_style_translate_x(p.place, LV_PART_MAIN)) lv_obj_set_style_translate_x(p.place, 0, 0);
  }
}

// The places of `frame` each with their piece of the atlas `picture` (nullptr: none, the blocks again).
static void lay(lv_obj_t *frame, std::vector<Place> &places, void *picture) {
#if LV_USE_IMAGE
  auto *src = static_cast<lv_image_dsc_t *>(picture);
  std::vector<tile_picture::Part> parts;
  std::vector<Place *> owners;
  const int scale = measure(frame, places, parts, owners);
  for (auto &p : places) {
    const auto at = std::find(owners.begin(), owners.end(), &p);
    if (!src || !src->data || at == owners.end()) { place_clear(p); continue; }
    const tile_picture::Piece f = tile_picture::piece(parts[at - owners.begin()], scale);
    if (f.x + f.w > static_cast<int>(src->header.w) || f.y + f.h > static_cast<int>(src->header.h)) { place_clear(p); continue; }
    if (!p.image) {
      p.image = lv_image_create(p.place);
      lv_obj_remove_flag(p.image, LV_OBJ_FLAG_CLICKABLE);
      // The offset counts from the atlas's top left, as the library's covers do: LVGL's default aligns a picture larger
      // than its object in the middle, and the piece would lie outside the place.
      lv_image_set_inner_align(p.image, LV_IMAGE_ALIGN_TOP_LEFT);
    }
    // Its piece of the atlas, in the middle of its place: a piece over the cap is smaller than the place.
    lv_image_set_src(p.image, src);
    lv_image_set_offset_x(p.image, -f.x);
    lv_image_set_offset_y(p.image, -f.y);
    lv_obj_set_pos(p.image, (lv_obj_get_width(p.place) - f.w) / 2, (lv_obj_get_height(p.place) - f.h) / 2);
    lv_obj_set_size(p.image, f.w, f.h);
    lv_obj_remove_flag(p.image, LV_OBJ_FLAG_HIDDEN);
    // The block goes under its picture: the piece carries the card's colour behind its corners already.
    rt::set_number(p.place, LV_STYLE_BG_OPA, LV_OPA_TRANSP);
    lv_obj_invalidate(p.image);
  }
#else
  (void) frame;
  for (auto &p : places) place_clear(p);
  (void) picture;
#endif
}
// The picture the places draw now (their last atlas), nullptr for none.
static const void *drawn(const std::vector<Place> &places) {
#if LV_USE_IMAGE
  for (const auto &p : places)
    if (p.image && !lv_obj_has_flag(p.image, LV_OBJ_FLAG_HIDDEN))
      if (const void *src = lv_image_get_src(p.image)) return src;
#else
  (void) places;
#endif
  return nullptr;
}
static bool draws(const std::vector<Place> &places, const void *picture) {
  if (!picture) return false;
  for (const auto &p : places)
    if (p.image && rt::draws(p.image, static_cast<const lv_image_dsc_t *>(picture))) return true;
  return false;
}

void picture_place(rt::Widgets &w, void *picture) {
  if (!w.plugin) return;
  if (picture != picture_drawn(w)) slide_back(w.plugin->places);
  lay(w.tile, w.plugin->places, picture);
}

const void *picture_drawn(const rt::Widgets &w) { return w.plugin ? drawn(w.plugin->places) : nullptr; }

bool picture_draws(const rt::Widgets &w, const void *picture) { return w.plugin && draws(w.plugin->places, picture); }

bool picture_let_go(rt::Widgets &w, const void *picture) {
  if (!w.plugin) return false;
  bool took = false;
  for (auto &p : w.plugin->places) {
    if (!p.image || (picture && !rt::draws(p.image, static_cast<const lv_image_dsc_t *>(picture)))) continue;
    place_clear(p);
    took = true;
  }
  return took;
}

// The place `obj` is, of the tile or card in a call of the host first, else on any tile's card or the open card (a
// plugin that kept the place and sets its picture from on_message); nullptr for an object that is no place.
static Place *find_place(lv_obj_t *obj) {
  if (!obj) return nullptr;
  if (placing) for (auto &p : *placing) if (p.place == obj) return &p;
  Place *found = nullptr;
  rt::each_card([&](rt::Widgets &w) {
    if (found || !w.plugin) return;
    for (auto &p : w.plugin->places) if (p.place == obj) { found = &p; return; }
  });
  if (!found) if (auto *places = card_places()) for (auto &p : *places) if (p.place == obj) return &p;
  return found;
}

uint16_t bytes(const std::string &entity) {
  const tessera::TileType *type = tessera::tile_type(entity);
  return type ? type->plugin->memory(type->id) : PLACEHOLDER_BYTES;
}

// ---- A plugin's card over the page ----
struct OpenCard {
  std::unique_ptr<tessera::Card> card;
  std::string key, entity;
  int tile = -1;
  size_t state = 0;
  bool dark = false;
  lv_obj_t *backdrop = nullptr, *root = nullptr;
  lv_obj_t *room = nullptr;      // the card's own room (CardContext::parent), what its places are measured from
  std::vector<Place> places;     // its places for pictures (0.13), in the order the card made them
  std::string art_key;           // the picture its places want (tile_picture::card_key), "" for none
};
static OpenCard *shown = nullptr;
static std::vector<Place> *card_places() { return shown ? &shown->places : nullptr; }
static void card_pictures_end(OpenCard &open);
// The touch guard's keys of a card's spots (card_tap), apart from the tiles' (rt::TILE_TOUCH) and the keys'.
constexpr int CARD_TOUCH = 300000;
// A card may close itself, or open another in its place, from any call the host makes into it (tessera::close_card,
// tessera::open_card in its open, on_state, on_tick, on_theme or on_back). A card that closes while such a call is under
// way leaves the glass at once and waits here until the outermost call returns, so neither the card's own code nor
// the host's after it runs on in freed memory.
static std::vector<OpenCard *> retired;
static int calling = 0;

static void destroy(OpenCard *open) {
  ++calling;           // a card's destructor is a call into it too: what it closes waits as well
  open->card.reset();  // its parts are the root's children: deleted with it, never by the card
  --calling;
  if (open->root) lv_obj_delete(open->root);
  if (open->backdrop) lv_obj_delete(open->backdrop);
  delete open;
}
static void bury() {
  while (!retired.empty() && !calling) {
    OpenCard *open = retired.back();
    retired.pop_back();
    destroy(open);
  }
}
// One call into the card `open`: true when it is still the card shown afterwards, so the caller may go on with it.
template<typename Run> static bool call(OpenCard *open, Run &&run) {
  ++calling;
  std::vector<Place> *had = placing;
  placing = &open->places;   // a place the card makes in this call is its own (ui::picture, 0.13)
  run(*open->card);
  placing = had;
  --calling;
  const bool still = shown == open;  // `open` is not deleted yet: the card waits in `retired` until this point
  bury();
  return still;
}

// What the tile a card was opened from says now: a plugin tile's data, or an entity's state and name.
static roomy::Text card_data(int tile) {
  if (tile < 0 || static_cast<size_t>(tile) >= rt::model.count) return {};
  const auto &t = rt::model.tiles[tile];
  if (t.is_plugin()) return t.extra().plugin_state;
  JsonDocument doc(&json_memory);
  doc["state"] = t.state;
  doc["name"] = t.name;
  roomy::Text out;
  serializeJson(doc, out);
  return out;
}

static void card_state(OpenCard &open, bool force) {
  const roomy::Text data = card_data(open.tile);
  const size_t state = hash(data);
  if (!force && state == open.state) return;
  open.state = state;
  JsonDocument doc(&json_memory);
  if (data.empty() || deserializeJson(doc, data.data(), data.size())) doc.to<JsonObject>();
  open.card->on_state(doc.as<JsonObjectConst>());
}

bool card_open() { return shown != nullptr; }

// A tap on the open card's room (Card::on_tap, 0.12). The guard is a tile's (rt::allowed: the finger did not move, was
// long enough, and no bounce), with the spot as its key: a cell of 8 mm, so a bounce on one row is one tap and the next
// row right after it is its own. Where the finger let go must be on the room, as for a tile (LVGL clicks an object
// wherever a finger that pressed it lets go when the board sets no limit to a finger's drift).
static void card_tap(lv_event_t *event) {
  auto *room = static_cast<lv_obj_t *>(lv_event_get_current_target(event));
  lv_point_t at{-1, -1};
  if (!rt::finger_at(at)) at = {-1, -1};
  lv_area_t area;
  lv_obj_get_coords(room, &area);
  const bool known = at.x >= 0 && at.y >= 0;
  if (known && (at.x < area.x1 || at.x > area.x2 || at.y < area.y1 || at.y > area.y2)) return;
  const int cell = std::max(1, ::ui::mm(8));
  const int spot = known ? ((at.y - area.y1) / cell) * 64 + (at.x - area.x1) / cell : 0;
  if (!shown || !rt::allowed(esphome::millis(), CARD_TOUCH + spot, "plugin card")) return;
  tapped = known ? tessera::Point{at.x - area.x1, at.y - area.y1} : tessera::Point{-1, -1};
  call(shown, [](tessera::Card &card) { card.on_tap(); });
}

void close_card() {
  if (!shown) return;
  OpenCard *open = shown;
  card_pictures_end(*open);
  shown = nullptr;  // first: a card that closes or opens a card from its destructor finds nothing open
  if (!calling) return destroy(open);
  if (open->backdrop) lv_obj_add_flag(open->backdrop, LV_OBJ_FLAG_HIDDEN);
  if (open->root) lv_obj_add_flag(open->root, LV_OBJ_FLAG_HIDDEN);
  retired.push_back(open);
}

bool open_card(const std::string &key, const std::string &entity, int tile, const std::string &title) {
  // A copy of what makes it: a plugin may register while the cards close (on_cards_closed), which moves the list.
  std::function<tessera::Card *()> make;
  bool wide = false;
  for (const auto &t : tessera::card_types())
    if (t.key == key) { make = t.make; wide = t.wide; }
  if (!make) return false;
  // One card at a time, as Tessera's own: the one open now, and a detail card of a tile, go first.
  close_card();
  if (rt::dismiss) rt::dismiss();
  ++calling;
  std::unique_ptr<tessera::Card> card(make());
  --calling;
  // A plugin that opened a card while the others closed (on_cards_closed), or from this card's constructor: this one
  // takes its place, as the card asked last.
  close_card();
  bury();
  if (!card) return false;
  auto *open = new OpenCard();
  open->card = std::move(card);
  open->key = key;
  open->entity = entity;
  open->tile = tile;
  open->dark = theme::dark;
  const bool large = ::ui::large();
  // The page's ground over everything, taking every press so nothing reaches the page under it.
  open->backdrop = lv_obj_create(lv_screen_active());
  lv_obj_remove_style_all(open->backdrop);
  lv_obj_set_size(open->backdrop, lv_pct(100), lv_pct(100));
  lv_obj_remove_flag(open->backdrop, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(open->backdrop, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_color(open->backdrop, theme::color(theme::PAGE), 0);
  lv_obj_set_style_bg_opa(open->backdrop, LV_OPA_COVER, 0);
  open->root = lv_obj_create(lv_screen_active());
  lv_obj_remove_style_all(open->root);
  lv_obj_remove_flag(open->root, LV_OBJ_FLAG_SCROLLABLE);
  // The whole glass high, as every card's root (detail_root): overlay_card::frame gives the width only, and a root of
  // LVGL's default height cut off what the card draws under its top bar (GitHub #226).
  lv_obj_set_height(open->root, lv_pct(100));
  const auto kind = wide ? overlay_card::picture : overlay_card::controls;
  overlay_card::frame(open->root, kind, 1);
  const int width = overlay_card::content_width(kind, 1), height = overlay_card::screen_height();
  // The top bar of every page a tap opens (detail_bar): the back key, which a card may take for a step back of its own
  // (on_back), and the title in the middle.
  std::string words = title;
  if (words.empty() && tile >= 0 && static_cast<size_t>(tile) < rt::model.count) words = rt::model.tiles[tile].name;
  detail_bar::make(open->root, words, {detail_bar::BACK, [](lv_event_t *) {
    if (!shown || !rt::allowed(esphome::millis(), 14, "plugin card back")) return;
    // on_back may close the card or open another: only the card still shown closes when it lets go.
    OpenCard *open = shown;
    bool keep = false;
    if (call(open, [&](tessera::Card &card) { keep = card.on_back(); }) && !keep) close_card();
  }});
  // The card's own room, under the bar, with the card's padding at the sides and the foot.
  const int pad = overlay_card::pad(), top = detail_bar::bottom() + ::ui::px(large ? 12 : 6);
  auto *area = lv_obj_create(open->root);
  lv_obj_remove_style_all(area);
  lv_obj_remove_flag(area, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(area, pad, top);
  lv_obj_set_size(area, std::max(1, width - 2 * pad), std::max(1, height - top - pad));
  // A tap on the room goes to the card (0.12), through the guard every tile's tap passes.
  lv_obj_add_flag(area, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(area, card_tap, LV_EVENT_SHORT_CLICKED, nullptr);
  open->room = area;
  shown = open;
  tessera::CardContext context{area, std::max(1, width - 2 * pad), std::max(1, height - top - pad), open->entity.c_str(),
                               tile};
  // Each step goes to the card only while it is still the one shown: it may have closed itself in the step before.
  if (!call(open, [&](tessera::Card &card) { card.open(context); })) return true;
  if (!call(open, [&](tessera::Card &) { card_state(*open, true); })) return true;
  call(open, [](tessera::Card &card) { card.on_tick(rt::now_epoch()); });
  return true;
}

static void tick_card(uint32_t epoch) {
  OpenCard *open = shown;
  if (!open) return;
  // As in open_card: the card may close itself (or open another) in on_state or on_theme.
  if (!call(open, [&](tessera::Card &) { card_state(*open, false); })) return;
  if (open->dark != theme::dark) {
    open->dark = theme::dark;
    if (!call(open, [](tessera::Card &card) { card.on_theme(); })) return;
    // The blocks under its pictures follow the look; the pictures are asked again in it (the look is in their key).
    for (auto &p : open->places) rt::set_color(p.place, LV_STYLE_BG_COLOR, theme::color(theme::TRACK));
  }
  call(open, [&](tessera::Card &card) { card.on_tick(epoch); });
}

// ---- Pictures on a plugin's card (plugin API 0.13) ----
// The places a card lays out in its room come the way a plugin tile's do: one question for all of them (the atlas of
// their frames from the room's top left, tile_picture::set_parts), the app fetches each address within the manifest's
// rights and paints the frames, the loader downloads it as the media card's cover goes (Rank::CARD, the full view's
// slot), and the store keeps it beside the page's pictures: what the glass under the card shows stays, a page out of
// sight makes room first. When the card closes its picture goes with it, as a tile's goes with its tile; the app keeps
// the source pictures by address, so a card that opens again, or shows the cover its tile shows, costs no fetch there.
static const picture_loader::Owner CARD_OWNER{picture_loader::Kind::CARD, 1};
static uint32_t card_number = 0;   // the number of the open card's last question; its answer carries it

static bool card_ask(OpenCard &open, tile_picture::Ask &a) {
  std::vector<tile_picture::Part> parts;
  std::vector<Place *> owners;
  measure(open.room, open.places, parts, owners);
  if (parts.empty()) return false;
  tile_picture::set_parts(a, std::move(parts), theme::hex(theme::PAGE), rt::picture_cap());
  a.index = open.tile >= 0 ? static_cast<size_t>(open.tile) : 0;
  a.entity = open.key;
  a.dark = theme::dark;
  return true;
}
static void card_request(const tile_picture::Ask &a, const std::string &entity) {
  if (rt::inbox.empty() || !esphome::api::global_api_server) return;
  esphome::api::HomeassistantActionRequest request;
  request.service = esphome::StringRef("esphome.screen_camera");
  request.is_event = true;
  auto fields = tile_picture::card_fields(a, entity);
  fields.insert(fields.begin(), {{"inbox", rt::inbox}, {"session", rt::protocol_key(rt::transfer.lease)},
                                 {"rev", rt::layout_rev}, {"view", std::to_string(++card_number)}});
  request.data.init(fields.size());
  for (const auto &field : fields) {
    esphome::api::HomeassistantServiceMap entry;
    entry.key = esphome::StringRef(field.first);
    entry.value = esphome::StringRef(field.second);
    request.data.push_back(entry);
  }
  esphome::api::global_api_server->send_homeassistant_action(request);
  ESP_LOGI("camera", "asked for the pictures of the card %s", a.entity.c_str());
}
// The card's picture onto its places, when it is the one they want now. Until the next is here, the places keep the
// one they show of the same layout (a card that steps to the next item), as a tile's do.
static void card_place(OpenCard &open) {
  lv_image_dsc_t *src = rt::picture_of(open.art_key);
  if (!src) return;
  if (src != drawn(open.places)) slide_back(open.places);
  lay(open.room, open.places, src);
  ESP_LOGI("picture", "card %s: its pictures are shown", open.key.c_str());
}

void card_picture_want() {
  OpenCard *open = shown;
  if (!open || !open->room || !rt::tile_pictures_supported()) return;
  // Not while the screen is dark: what it wants waits, and a download of it breaks off (not wanted this round).
  if (!rt::tiles_seen()) return;
  tile_picture::Ask a;
  if (!card_ask(*open, a)) {
    // No place with an address now (a card that took its picture away): its last picture goes.
    if (!open->art_key.empty()) { rt::loader.release(CARD_OWNER); open->art_key.clear(); }
    return;
  }
  const std::string key = tile_picture::card_key(a, open->key, open->entity);
  if (key != open->art_key) {
    open->art_key = key;
    if (rt::picture_of(key)) card_place(*open);
  }
  picture_loader::Want want;
  want.key = key;
  want.tag = tile_picture::card_tag(open->key);
  want.slot = picture_loader::Slot::FULL;
  want.rank = picture_loader::Rank::CARD;
  want.drawn = true;  // the app fetches them: an answer without a picture (a slow host) is asked again, later each time
  const std::string entity = open->entity;
  want.ask = [a, entity] { card_request(a, entity); };
  want.done = [](picture_loader::Outcome o) { if (rt::shows(o) && shown) card_place(*shown); };
  rt::loader.want(CARD_OWNER, std::move(want));
}

void card_picture_answer(const std::string &card, const std::string &url, uint32_t number) {
  if (!shown || card != shown->key || number != card_number) return;
  if (url.empty()) ESP_LOGI("picture", "card %s: no pictures now", card.c_str());
  rt::loader.answer(tile_picture::card_tag(card), url, esphome::millis());
}
bool card_question(uint32_t number) { return shown && number == card_number; }
bool card_draws(const void *picture) { return shown && draws(shown->places, picture); }
void card_letgo(const void *download) {
  if (!shown || !download) return;
  for (auto &p : shown->places) if (p.image && rt::draws(p.image, static_cast<const lv_image_dsc_t *>(download))) place_clear(p);
}
// The card closes: its places let go of their picture and the loader of its question, so the store frees it now.
static void card_pictures_end(OpenCard &open) {
  for (auto &p : open.places) place_clear(p);
  if (open.art_key.empty()) return;
  rt::loader.release(CARD_OWNER);
  open.art_key.clear();
  rt::pictures_collect();
}

bool tap_action(size_t index) {
  if (index >= rt::model.count) return false;
  const auto &t = rt::model.tiles[index];
  for (const auto &action : tessera::tap_actions())
    if (action.key == t.tap && action.run) {
      // The action and the tile's words are copies: what the action does (a layout it asks for, an action it adds)
      // may move the list it came from, or the tile.
      const auto run = action.run;
      const std::string entity = t.entity, name = t.name;
      tessera::TapContext context{entity.c_str(), name.c_str(), static_cast<int>(index)};
      run(context);
      return true;
    }
  return false;
}

// ---- The plugins' pages on the settings page ----
// Built once: the rows point into these, so nothing here moves afterwards.
struct SettingsStore {
  std::vector<std::unique_ptr<tessera::SettingsPage>> pages;   // what each plugin added
  std::vector<std::unique_ptr<std::vector<settings_screen::Row>>> rows;
  std::vector<std::unique_ptr<std::vector<const char *>>> options;
  std::vector<std::unique_ptr<settings_screen::Own>> owns;        // each plugin row's words and functions
  std::vector<std::pair<tessera::Plugin *, std::string>> cards;  // a card row: its plugin and card
};
static SettingsStore &settings_store() {
  static SettingsStore store;
  return store;
}

static void build_settings() {
  auto &store = settings_store();
  std::vector<std::pair<tessera::Plugin *, tessera::SettingsPage *>> added;
  for (auto *p : tessera::plugins()) {
    auto page = std::make_unique<tessera::SettingsPage>();
    if (!p->settings(*page) || page->items.empty()) continue;
    if (page->title.empty()) page->title = *p->text("name") ? p->text("name") : p->plugin_id();
    if (page->icon.empty()) page->icon = "\U000F0A66";
    added.push_back({p, page.get()});
    store.pages.push_back(std::move(page));
  }
  if (added.empty()) return;
  using settings_screen::Row;
  using settings_screen::Kind;
  // The list of plugins: one row per plugin, opening its page.
  auto list = std::make_unique<std::vector<Row>>();
  for (size_t i = 0; i < added.size(); ++i) {
    Row row{};
    row.kind = Kind::page;
    auto own = std::make_unique<settings_screen::Own>();
    own->words = added[i].second->title.c_str();
    row.own = own.get();
    store.owns.push_back(std::move(own));
    row.icon = added[i].second->icon.c_str();
    row.opens = static_cast<uint8_t>(settings_screen::PLUGINS_PAGE + 1 + i);
    list->push_back(row);
  }
  // The settings page draws twelve rows at most (settings_screen::draw): a thirteenth plugin's page is out of reach.
  if (list->size() > 12)
    ESP_LOGW("plugins", "%u plugins have settings; the settings page lists the first 12", (unsigned) list->size());
  settings_screen::plugin_pages.push_back({screen_text::txt::settings_plugins, list->data(),
                                           static_cast<uint8_t>(std::min<size_t>(list->size(), 12)), 0, nullptr});
  store.rows.push_back(std::move(list));
  for (auto &[plugin, page] : added) {
    auto rows = std::make_unique<std::vector<Row>>();
    for (auto &item : page->items) {
      Row row{};
      auto own = std::make_unique<settings_screen::Own>();
      own->words = item.label.c_str();
      own->ctx = &item;
      using Item = tessera::SettingsPage::Item;
      switch (item.kind) {
        case Item::TOGGLE: row.kind = Kind::toggle; break;
        case Item::NUMBER:
          row.kind = Kind::number; row.low = item.low; row.high = item.high; row.step = item.step;
          row.unit = item.unit.c_str();
          break;
        case Item::CHOICE: {
          row.kind = Kind::choice;
          auto words = std::make_unique<std::vector<const char *>>();
          for (auto &option : item.options) words->push_back(option.c_str());
          row.options = words->data();
          row.option_count = static_cast<uint8_t>(std::min<size_t>(words->size(), 255));
          store.options.push_back(std::move(words));
          break;
        }
        case Item::ACTION:
        case Item::CARD:
          row.kind = Kind::action;
          row.icon = item.icon.c_str();
          if (!item.confirm.empty()) own->confirm = item.confirm.c_str();
          break;
        case Item::INFO: row.kind = Kind::info; break;
      }
      if (item.kind == Item::CARD) {
        store.cards.push_back({plugin, item.card});
        item.run = [plugin = plugin, card = item.card]() {
          settings_screen::close();
          tessera::open_card(plugin->plugin_id(), card.c_str());
        };
      }
      own->read = [](void *c) -> int32_t { auto *i = static_cast<Item *>(c); return i->read ? i->read() : 0; };
      own->write = [](void *c, int32_t v) { auto *i = static_cast<Item *>(c); if (i->write) i->write(v); };
      own->run = [](void *c) { auto *i = static_cast<Item *>(c); if (i->run) i->run(); };
      if (item.text) own->text = [](void *c) -> std::string { return static_cast<Item *>(c)->text(); };
      if (item.active) own->active = [](void *c) { return static_cast<Item *>(c)->active(); };
      row.own = own.get();
      store.owns.push_back(std::move(own));
      rows->push_back(row);
      if (rows->size() == 12 && page->items.size() > 12) {   // what one page draws (settings_screen::draw)
        ESP_LOGW("plugins", "%s added %u settings rows; the page draws the first 12", plugin->plugin_id(),
                 (unsigned) page->items.size());
        break;
      }
    }
    settings_screen::plugin_pages.push_back({0, rows->data(), static_cast<uint8_t>(rows->size()),
                                             settings_screen::PLUGINS_PAGE, page->title.c_str()});
    store.rows.push_back(std::move(rows));
  }
}

static header_bar::Shown bar_item(const std::string &key) {
  header_bar::Shown shown;
  auto &items = tessera::bar_items();
  for (size_t i = 0; i < items.size(); ++i)
    if (items[i].key == key && items[i].read) {
      const auto read = items[i].read;  // a copy: a plugin that adds an item while it reads moves the list
      const tessera::BarItem now = read();
      shown.shown = now.shown && (now.icon || !now.text.empty());
      shown.icon = now.icon && rt::has_icon_glyph(now.icon) ? now.icon : 0;
      // At most the bar's bytes and never half a character, as runtime_tiles::string cuts what the app sends.
      size_t size = std::min(now.text.size(), header_bar::TEXT_BYTES);
      while (size > 0 && size < now.text.size() && (static_cast<unsigned char>(now.text[size]) & 0xC0) == 0x80) --size;
      shown.text = now.text.substr(0, size);
      shown.has_color = tessera::tone_color(now.tone, shown.color);
      break;
    }
  return shown;
}

void message(const std::string &plugin, JsonObjectConst body) {
  for (auto *p : tessera::plugins())
    if (plugin == p->plugin_id()) p->on_message(body);
}

// The plugins' moments start once ESPHome has set up every component, not at on_boot. packages/core.yaml calls ready()
// in on_boot at priority -100, the setup priority LATE that a plugin with hardware of its own takes as well (a sound, a
// camera, a microphone), and ESPHome sets up the components of one priority in the order they were registered: the
// on_boot automation is registered before any plugin's component (ESPHome generates automations before components), so
// on_ready() and settings() ran before such a plugin's setup(), where it adds its tiles, cards and items. The first
// tick after setup (every 250 ms) starts them instead; until then no moment reaches a plugin, on_interval included,
// which a slow component could otherwise call during setup.
static bool asked = false, started = false;
static void start() {
  started = true;
  header_bar::plugin_item = bar_item;
  // The plugins in the screen's moments (screen_hooks.h), beside the board's own features: a card of a plugin counts as
  // away from page 1, as a camera full screen does, so Back to page 1 closes it in time.
  screen_hooks::cards_closed().push_back([]() { for (auto *p : tessera::plugins()) p->on_cards_closed(); });
  screen_hooks::alert_show().push_back([]() { for (auto *p : tessera::plugins()) p->on_alert(); });
  screen_hooks::touched().push_back([]() { for (auto *p : tessera::plugins()) p->on_touch(); });
  // Feedback the moment a finger lands or a value under it steps (touch_feedback.h), heard by the plugins only.
  touch_feedback::pressed().push_back([]() { for (auto *p : tessera::plugins()) p->on_press(); });
  touch_feedback::stepped().push_back([](const touch_feedback::Step &s) {
    const tessera::Step step{s.direction, s.edge};
    for (auto *p : tessera::plugins()) p->on_step(step);
  });
  touch_feedback::lvgl::listen();
  screen_hooks::away().push_back([]() { return card_open(); });
  build_settings();
  for (auto *p : tessera::plugins()) p->on_ready();
}
static bool set_up() {
  if (!started && asked && esphome::App.is_setup_complete()) start();
  return started;
}
void ready() {
  asked = true;
  set_up();
}
void tick(uint32_t now_ms, bool dimmed) {
  if (!set_up()) return;
  static bool was_dimmed = false;
  if (dimmed != was_dimmed) {
    was_dimmed = dimmed;
    standby(dimmed);
  }
  for (auto *p : tessera::plugins()) p->on_interval(now_ms);
  // A plugin's page of the settings says again what its rows read (a test that runs, a level), once a second.
  static uint32_t said = 0;
  if (settings_screen::root && settings_screen::current_page >= settings_screen::PAGE_COUNT && now_ms - said >= 1000) {
    said = now_ms;
    settings_screen::refresh();
  }
}
void standby(bool dark) { for (auto *p : tessera::plugins()) p->on_standby(dark); }
void before_update() { for (auto *p : tessera::plugins()) p->before_update(); }

void hello(JsonObject root) {
  char api[8];
  snprintf(api, sizeof api, "%u.%u", tessera::PLUGIN_API_MAJOR, tessera::PLUGIN_API_MINOR);
  root["plugin_api"] = std::string(api);
  auto list = root["plugins"].to<JsonArray>();
  for (auto *p : tessera::plugins()) {
    auto item = list.add<JsonObject>();
    item["id"] = std::string(p->plugin_id());
    item["version"] = std::string(p->plugin_version());
    auto tiles = item["tiles"].to<JsonArray>();
    for (const auto &type : tessera::tile_types())
      if (type.plugin == p) tiles.add(type.id);
  }
}

}  // namespace plugin_host

namespace tessera::ui {
lv_obj_t *text(lv_obj_t *parent, Font f, theme::Role role) {
  // A label's dots (LV_LABEL_LONG_DOT) wrap at the width and end the last line that fits the height with dots: two
  // lines to start with, the plugin's height after that.
  lv_obj_t *l = label(parent, f, role);
  if (const lv_font_t *face = font(f)) lv_obj_set_height(l, 2 * lv_font_get_line_height(face));
  return l;
}

bool pictures() { return rt::tile_pictures_supported(); }

lv_obj_t *picture(lv_obj_t *parent) {
  lv_obj_t *place = block(parent, theme::TRACK);
  lv_obj_remove_flag(place, LV_OBJ_FLAG_SCROLLABLE);
  if (plugin_host::placing) plugin_host::placing->push_back({place});
  else ESP_LOGW("plugins", "ui::picture outside a call of a tile or a card: the place shows no picture");
  return place;
}

void set_picture(lv_obj_t *place, const std::string &url, Fit fit) { set_picture(place, url, fit, Turn::NONE, false); }

static void slide_exec(void *obj, int32_t x) { lv_obj_set_style_translate_x(static_cast<lv_obj_t *>(obj), x, 0); }

void slide_pictures(int dx, uint32_t ms) {
  std::vector<plugin_host::Place> *places = plugin_host::placing;
  if (!places) {
    ESP_LOGW("plugins", "ui::slide_pictures outside a call of a tile or a card");
    return;
  }
  for (auto &p : *places) {
    if (!p.place || lv_obj_has_flag(p.place, LV_OBJ_FLAG_HIDDEN)) continue;
    lv_anim_delete(p.place, nullptr);
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, p.place);
    lv_anim_set_values(&a, lv_obj_get_style_translate_x(p.place, LV_PART_MAIN), dx);
    lv_anim_set_duration(&a, ms);
    lv_anim_set_exec_cb(&a, slide_exec);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
    lv_anim_start(&a);
  }
}

void set_picture(lv_obj_t *place, const std::string &url, Fit fit, Turn turn, bool mirror) {
  plugin_host::Place *p = plugin_host::find_place(place);
  if (!p) return;
  const bool contain = fit == Fit::CONTAIN;
  const uint8_t turned = static_cast<uint8_t>(turn);
  if (p->url == url && p->contain == contain && p->turn == turned && p->mirror == mirror) return;
  p->url = url;
  p->contain = contain;
  p->turn = turned;
  p->mirror = mirror;
  // Another picture: the next round asks for it (the address is in the picture's key), and the place keeps what it
  // showed until it is here (tile_picture_place), so a row of posters turns without a flash of blocks; "" takes the
  // picture away at once, and a place that showed none keeps its block.
  if (url.empty()) plugin_host::place_clear(*p);
}
}  // namespace tessera::ui
#else
#include <cstdio>
#include "plugin_host.h"
#include "plugin_api.h"
// A build without a plugin (docs/PLUGINS.md, "What it costs"): the core only says it offers the plugin API and draws a
// plugin's tile as a plain card that says the plugin is missing. Everything else of the API is left out, so a screen
// pays nothing for plugins it does not have (21 KB on the CYD otherwise).
namespace plugin_host {
bool known(const runtime_tiles::Tile &) { return false; }
void render(runtime_tiles::Widgets &, const runtime_tiles::Tile &, int, int) {}
void release(runtime_tiles::Widgets &) {}   // no plugin card is ever made in this build
void tap(runtime_tiles::Widgets &, int, int) {}
void tick_cards(uint32_t) {}
uint16_t bytes(const std::string &) { return PLACEHOLDER_BYTES; }
bool pictured(const runtime_tiles::Widgets &) { return false; }
bool picture_ask(const runtime_tiles::Widgets &, const runtime_tiles::Tile &, tile_picture::Ask &) { return false; }
void picture_place(runtime_tiles::Widgets &, void *) {}
const void *picture_drawn(const runtime_tiles::Widgets &) { return nullptr; }
bool picture_draws(const runtime_tiles::Widgets &, const void *) { return false; }
bool picture_let_go(runtime_tiles::Widgets &, const void *) { return false; }
void card_picture_want() {}
void card_picture_answer(const std::string &, const std::string &, uint32_t) {}
bool card_question(uint32_t) { return false; }
bool card_draws(const void *) { return false; }
void card_letgo(const void *) {}
bool open_card(const std::string &, const std::string &, int, const std::string &) { return false; }
void close_card() {}
bool card_open() { return false; }
bool tap_action(size_t) { return false; }
void message(const std::string &, JsonObjectConst) {}
void ready() {}
void tick(uint32_t, bool) {}
void standby(bool) {}
void before_update() {}
void hello(JsonObject root) {
  char api[8];
  snprintf(api, sizeof api, "%u.%u", tessera::PLUGIN_API_MAJOR, tessera::PLUGIN_API_MINOR);
  root["plugin_api"] = std::string(api);
  root["plugins"].to<JsonArray>();
}
}  // namespace plugin_host
#endif
