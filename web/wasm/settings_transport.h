#pragma once
#include <array>
#include <deque>
#include <set>
#include <utility>

// Browser bindings for the firmware's settings_screen. No widgets or layout live here: core rows
// come from the firmware, and board rows use its Row/Own interface with the existing Extras data.
namespace preview_settings_host {
inline bool controls = false, receiving = false, online = false;
inline std::string name, version, last_action;
inline std::set<std::string> booleans;
inline std::deque<std::string> outgoing;

inline void enqueue(const JsonDocument &doc) {
  std::string encoded;
  serializeJson(doc, encoded);
  outgoing.push_back(std::move(encoded));
}
inline void bind() {
  settings_screen::quarter_turns = lv_display_get_horizontal_resolution(nullptr) == lv_display_get_vertical_resolution(nullptr);
  settings_screen::may_open = [] { return runtime_tiles::enabled; };
  settings_screen::drift = [] { return screen_input::touch_guard.distance(); };
  settings_screen::before_open = [] { runtime_tiles::hide_detail(); };
  settings_screen::name_text = [] { return name; };
  settings_screen::firmware_text = [] { return version; };
  settings_screen::link_text = [] { return std::string(screen_text::tr(online
      ? screen_text::txt::settings_connected : screen_text::txt::settings_not_connected)); };
  settings_screen::apply = [] {
    theme::set_dark(settings_screen::dark_mode != 0);
    runtime_tiles::page_buttons_changed();
  };
  settings_screen::report = [](const char *key, int32_t value) {
    if (receiving || !controls) return;
    JsonDocument doc;
    doc["key"] = key;
    if (booleans.count(key)) doc["value"] = value != 0;
    else doc["value"] = value;
    enqueue(doc);
  };
  runtime_tiles::open_this_screen = [] { settings_screen::open(4); };
}
inline void receive(const char *message) {
  JsonDocument doc;
  if (deserializeJson(doc, message ? message : "")) return;
  receiving = true;
  name = doc["name"] | "";
  version = doc["firmware"] | "";
  online = doc["online"] | false;
  settings_screen::dimmable = doc["dimmable"] | true;
  settings_screen::can_standby = doc["standby"] | true;
  booleans.clear();
  for (JsonPairConst entry : doc["values"].as<JsonObjectConst>()) {
    if (entry.value().isNull()) continue;  // unavailable is not zero/off
    if (entry.value().is<bool>()) booleans.insert(entry.key().c_str());
    settings_screen::set(entry.key().c_str(), entry.value().as<int32_t>());
  }
  receiving = false;
  settings_screen::refresh();
}

struct Extra {
  std::string key, entity, label, kind, unit, status;
  std::vector<std::string> options;
  std::vector<const char *> option_words;
  bool available = false;
  int32_t value = 0;
  settings_screen::Own own;
};
inline std::array<Extra, 12> extras;
inline std::string extras_schema;
template <size_t I> bool enabled() { return controls && extras[I].available; }
template <size_t... I> constexpr auto enablers(std::index_sequence<I...>) {
  return std::array<settings_screen::Shown, sizeof...(I)>{enabled<I>...};
}
inline constexpr auto enabled_at = enablers(std::make_index_sequence<12>{});

inline bool integral(JsonVariantConst value) {
  return value.is<double>() && value.as<double>() == double(value.as<int32_t>());
}
inline void receive_extras(const char *message) {
  JsonDocument doc;
  if (deserializeJson(doc, message ? message : "")) return;
  JsonDocument schema = doc;
  for (auto row : schema.as<JsonArray>()) {
    row.remove("value"); row.remove("status");
  }
  std::string shape;
  serializeJson(schema, shape);
  const bool rebuild = shape != extras_schema;
  extras_schema = std::move(shape);
  settings_screen::board_rows.clear();
  for (JsonObjectConst source : doc.as<JsonArrayConst>()) {
    const size_t index = settings_screen::board_rows.size();
    if (index == extras.size()) break;
    auto &e = extras[index];
    e.key = source["key"] | ""; e.entity = source["entity"] | "";
    e.label = source["label"] | e.key; e.kind = source["kind"] | "";
    e.unit = source["unit"] | ""; e.status = source["status"] | "";
    e.available = (source["available"] | false) && !e.entity.empty();
    e.value = source["value"].as<int32_t>();
    e.options.clear(); e.option_words.clear();
    for (auto option : source["options"].as<JsonArrayConst>()) e.options.push_back(option.as<std::string>());
    for (const auto &option : e.options) e.option_words.push_back(option.c_str());
    if (e.kind == "select") {
      auto selected = std::find(e.options.begin(), e.options.end(), source["value"].as<std::string>());
      e.value = selected == e.options.end() ? -1 : int(selected - e.options.begin());
    }
    e.own = {};
    e.own.ctx = &e;
    e.own.words = e.label.c_str();
    e.own.read = [](void *ctx) { return static_cast<Extra *>(ctx)->value; };
    e.own.text = [](void *ctx) { return static_cast<Extra *>(ctx)->status; };
    e.own.write = [](void *ctx, int32_t value) {
      auto &e = *static_cast<Extra *>(ctx);
      if (!controls || !e.available) return;
      JsonDocument request;
      request["entity"] = e.entity;
      if (e.kind == "switch" || e.kind == "button") request["value"] = value != 0;
      else if (e.kind == "select") {
        if (value < 0 || size_t(value) >= e.options.size()) return;
        request["value"] = e.options[value];
      } else request["value"] = value;
      e.value = value;
      enqueue(request);
    };
    e.own.run = [](void *ctx) { auto &e = *static_cast<Extra *>(ctx); e.own.write(ctx, 1); };
    settings_screen::Row row;
    row.own = &e.own;
    row.enabled = enabled_at[index];
    row.unit = e.unit.c_str();
    if (e.kind == "switch") row.kind = settings_screen::Kind::toggle;
    else if (e.kind == "number" && integral(source["min"]) && integral(source["max"]) && integral(source["step"])) {
      row.kind = settings_screen::Kind::number;
      row.low = source["min"]; row.high = source["max"]; row.step = source["step"];
    } else if (e.kind == "select") {
      row.kind = settings_screen::Kind::choice;
      row.options = e.option_words.data(); row.option_count = std::min<size_t>(e.options.size(), 48);
    } else if (e.kind == "button") row.kind = settings_screen::Kind::action;
    else {
      // No separate text editor or fractional-number renderer: unsupported rows remain read-only.
      row.kind = settings_screen::Kind::info;
      e.status = source["password"] == true ? "" : source["value"].as<std::string>();
      e.available = false;
    }
    if (!(source["available"] | false)) {
      row.kind = settings_screen::Kind::info;
      e.status = screen_text::tr(screen_text::txt::ha_unavailable);
    }
    settings_screen::board_rows.push_back(row);
  }
  if (rebuild) settings_screen::restyle();
  else settings_screen::refresh();
}
}  // namespace preview_settings_host
