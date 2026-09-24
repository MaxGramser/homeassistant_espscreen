#pragma once
#ifdef ESP_SCREEN_HOST
// Deterministic host services for the firmware renderer. This file contains no UI logic.
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include <ctime>
#include <cstring>
#include <deque>
#include <functional>
#include <map>
#include <ArduinoJson.h>

namespace esphome {
inline uint32_t host_millis = 1000;
inline uint32_t millis() { return host_millis; }
inline uint64_t millis_64() { return host_millis; }
struct ESPPreferenceObject {
  template <typename T> bool load(T *) const { return false; }
  template <typename T> bool save(const T &) { return true; }
};
struct ESPTime {
  int year = 2026, month = 1, day_of_month = 1, day_of_year = 1, day_of_week = 4, hour = 12, minute = 0, second = 0;
  uint32_t timestamp = 0;
  bool is_valid() const { return year >= 2019; }
  static ESPTime from_epoch_local(uint32_t epoch) {
    time_t time = epoch;
    auto *t = std::gmtime(&time);
    ESPTime result;
    if (!t) return result;
    result.timestamp = epoch; result.year = t->tm_year + 1900; result.month = t->tm_mon + 1;
    result.day_of_month = t->tm_mday; result.day_of_year = t->tm_yday + 1; result.day_of_week = t->tm_wday + 1;
    result.hour = t->tm_hour; result.minute = t->tm_min; result.second = t->tm_sec;
    return result;
  }
};
struct PreferenceStore {
  template <typename T> ESPPreferenceObject make_preference(uint32_t) { return {}; }
};
inline PreferenceStore host_preferences;
inline PreferenceStore *global_preferences = &host_preferences;
struct StringRef {
  const char *value = "";
  size_t length = 0;
  const char *c_str() const { return value; }
  size_t size() const { return length; }
  StringRef() = default;
  StringRef(const char *text) : value(text), length(std::strlen(text)) {}
  StringRef(const char *text, size_t n) : value(text), length(n) {}
  explicit StringRef(const std::string &text) : value(text.c_str()), length(text.size()) {}
};
namespace api {
struct HomeAssistantStateSubscription {};
struct HomeassistantServiceMap { StringRef key, value; };
struct StringList {
  std::vector<HomeassistantServiceMap> values;
  void init(size_t n) { values.clear(); values.reserve(n); }
  void push_back(const HomeassistantServiceMap &item) { values.push_back(item); }
};
struct HomeassistantActionRequest { StringRef service; uint32_t call_id = 0; bool is_event = false; StringList data, data_template; };
struct ActionResponse {
  bool success = false;
  StringRef error;
  bool is_success() const { return success; }
  StringRef get_error_message() const { return error; }
};
struct HostApiServer {
  std::deque<std::string> outgoing;
  std::map<uint32_t, std::function<void(const ActionResponse &)>> callbacks;
  void send_homeassistant_action(const HomeassistantActionRequest &request) {
    if (outgoing.size() >= 64) {
      handle_action_response(request.call_id, false, StringRef("preview_queue_full"));
      return;
    }
    JsonDocument packet;
    packet["service"] = std::string(request.service.c_str(), request.service.size());
    packet["call_id"] = request.call_id;
    packet["event"] = request.is_event;
    const auto copy = [&](const char *name, const StringList &items) {
      auto data = packet[name].to<JsonObject>();
      for (const auto &entry : items.values)
        data[std::string(entry.key.c_str(), entry.key.size())] = std::string(entry.value.c_str(), entry.value.size());
    };
    copy("data", request.data); copy("templates", request.data_template);
    std::string message; serializeJson(packet, message);
    outgoing.push_back(std::move(message));
  }
  void register_action_response_callback(uint32_t id, std::function<void(const ActionResponse &)> callback) {
    callbacks[id] = std::move(callback);
  }
  void handle_action_response(uint32_t id, bool success, StringRef error) {
    auto entry = callbacks.find(id);
    if (entry == callbacks.end()) return;
    auto callback = std::move(entry->second);
    callbacks.erase(entry);
    callback(ActionResponse{success, error});
  }
};
inline HostApiServer host_api_server;
inline HostApiServer *global_api_server = &host_api_server;
}
inline bool api_is_connected() { return true; }
namespace json {
template <typename Callback> bool parse_json(const std::string &payload, Callback callback) {
  JsonDocument document;
  if (deserializeJson(document, payload)) return false;
  return callback(document.as<JsonObject>());
}
}
}

#ifndef ESP_LOGE
#define ESP_LOGE(...) do {} while (0)
#define ESP_LOGW(...) do {} while (0)
#define ESP_LOGI(...) do {} while (0)
#define ESP_LOGD(...) do {} while (0)
#endif
#endif  // ESP_SCREEN_HOST: ESPHome also includes component headers in device builds.
