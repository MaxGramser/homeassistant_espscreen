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
#include <algorithm>
#include <functional>
#include <memory>
#include <vector>

namespace rt = runtime_tiles;
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
  if (!service || !rt::valid_entity(entity) || entity.rfind("plugin:", 0) == 0) return false;
  return rt::action(service, entity, key ? key : "", value);
}

bool open_card(const char *plugin_id, const char *card, const std::string &entity, int tile, const std::string &title) {
  return plugin_host::open_card(std::string("plugin:") + (plugin_id ? plugin_id : "") + "." + (card ? card : ""), entity,
                                tile, title);
}

void close_card() { plugin_host::close_card(); }

uint32_t send(const Plugin *plugin, JsonObjectConst request) {
  static uint32_t next = 0;
  if (!plugin || rt::inbox.empty() || !esphome::api::global_api_server) return 0;
  JsonDocument doc;
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
  }
  // Before boot handed them over (never on a screen: plugins are made after on_boot), the nearest that is there.
  if (!face) face = rt::small_font ? rt::small_font : rt::control_font ? rt::control_font : rt::detail_font;
  return face;
}

int text_width(const std::string &text, Font f) {
  const lv_font_t *face = font(f);
  return face ? rt::text_width(text, face) : 0;
}

lv_obj_t *label(lv_obj_t *parent, Font f, theme::Role role) {
  lv_obj_t *l = lv_label_create(parent);
  lv_obj_remove_flag(l, LV_OBJ_FLAG_CLICKABLE);
  lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
  lv_label_set_text(l, "");
  if (const lv_font_t *face = font(f)) lv_obj_set_style_text_font(l, face, 0);
  lv_obj_set_style_text_color(l, theme::color(role), 0);
  return l;
}

void set_text(lv_obj_t *l, const std::string &text) { if (l) rt::label(l, text); }
void set_font(lv_obj_t *l, Font f) {
  if (const lv_font_t *face = font(f)) if (l) rt::set_font(l, face);
}
void set_color(lv_obj_t *l, theme::Role role) {
  if (l) rt::set_color(l, LV_STYLE_TEXT_COLOR, theme::color(role));
}

void set_tone(lv_obj_t *l, Tone tone, theme::Role normal) {
  if (!l) return;
  uint32_t color = 0;
  if (!tone_color(tone, color)) return set_color(l, normal);
  rt::set_color(l, LV_STYLE_TEXT_COLOR, lv_color_hex(color));
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

struct Card {
  std::unique_ptr<tessera::Tile> tile;
  std::string entity;          // what the card was made for: the tile type,
  size_t index = SIZE_MAX;     // the tile of the layout,
  int width = 0, height = 0;   // its room,
  size_t options = 0;          // and its options (a hash)
  size_t state = 0;            // the data it was last given (a hash), 0 for none yet
  bool dark = false;           // the look it last coloured itself for
};

static size_t hash(const std::string &text) { return std::hash<std::string>{}(text) | 1; }

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
  const size_t options = hash(extra.plugin_options + "|" + extra.plugin_entity);
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
    JsonDocument doc;
    if (extra.plugin_options.empty() || deserializeJson(doc, extra.plugin_options)) doc.to<JsonObject>();
    tessera::TileContext context{w.extra, width, height, static_cast<uint8_t>(t.column_span()),
                                 static_cast<uint8_t>(t.row_span()), t.name.c_str(), extra.plugin_entity.c_str(),
                                 static_cast<int>(w.index), doc.as<JsonObjectConst>()};
    card->tile->create(context);
  }
  const size_t state = hash(extra.plugin_state);
  if (card->state != state) {
    card->state = state;
    JsonDocument doc;
    if (extra.plugin_state.empty() || deserializeJson(doc, extra.plugin_state)) doc.to<JsonObject>();
    card->tile->on_state(doc.as<JsonObjectConst>());
    card->tile->on_tick(rt::now_epoch());
  }
  if (card->dark != theme::dark) {
    card->dark = theme::dark;
    card->tile->on_theme();
  }
}

void tap(rt::Widgets &w) {
  if (w.plugin && w.plugin->tile) w.plugin->tile->on_tap();
}

static void tick_card(uint32_t epoch);

void tick_cards(uint32_t epoch) {
  tick_card(epoch);
  for (auto &w : rt::widgets) {
    if (!w.plugin || !w.tile || !w.extra || w.extra_mode != "plugin" || w.index >= rt::model.count) continue;
    if (lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN) || lv_obj_has_flag(w.extra, LV_OBJ_FLAG_HIDDEN)) continue;
    w.plugin->tile->on_tick(epoch);
  }
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
};
static OpenCard *shown = nullptr;
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
  run(*open->card);
  --calling;
  const bool still = shown == open;  // `open` is not deleted yet: the card waits in `retired` until this point
  bury();
  return still;
}

// What the tile a card was opened from says now: a plugin tile's data, or an entity's state and name.
static std::string card_data(int tile) {
  if (tile < 0 || static_cast<size_t>(tile) >= rt::model.count) return "";
  const auto &t = rt::model.tiles[tile];
  if (t.is_plugin()) return t.extra().plugin_state;
  JsonDocument doc;
  doc["state"] = t.state;
  doc["name"] = t.name;
  std::string out;
  serializeJson(doc, out);
  return out;
}

static void card_state(OpenCard &open, bool force) {
  const std::string data = card_data(open.tile);
  const size_t state = hash(data);
  if (!force && state == open.state) return;
  open.state = state;
  JsonDocument doc;
  if (data.empty() || deserializeJson(doc, data)) doc.to<JsonObject>();
  open.card->on_state(doc.as<JsonObjectConst>());
}

bool card_open() { return shown != nullptr; }

void close_card() {
  if (!shown) return;
  OpenCard *open = shown;
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
  }
  call(open, [&](tessera::Card &card) { card.on_tick(epoch); });
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
void tap(runtime_tiles::Widgets &) {}
void tick_cards(uint32_t) {}
uint16_t bytes(const std::string &) { return PLACEHOLDER_BYTES; }
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
