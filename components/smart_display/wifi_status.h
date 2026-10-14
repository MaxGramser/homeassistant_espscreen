#pragma once
// Wi-Fi as the glass tells it (firmware 0.19.0). A screen that cannot reach its network can reach nobody to say so:
// no Home Assistant, no ESP Screens. So the screen says it itself, on the loading screen over everything, with what
// fixes it. A board with a hotspot (ESPHome's `ap:`, which starts some 90 seconds after the network is gone) names that
// hotspot and its password: join it with a phone and pick the right network on the page that opens. A board without
// one (4 MB of flash, no room for it) says to check the name and password and to install the screen again over USB.
// On the host (the preview and the tests) there is no Wi-Fi to lose, and nothing is ever shown.
//
// What the screen knows of its network at any moment (firmware 0.38.0): the loading screen says each step while it
// starts, the top bar's Wi-Fi item draws the signal, and the settings page's "This screen" names the network. All of it
// is ESPHome's own: the network it tries (get_sta), whether it holds it (is_connected), the signal (wifi_rssi), the
// address, and after every scan whether the network was there and how strong (ESPHome's scan results listener). One
// fact ESPHome only writes to its log: why the access point let the screen go. That comes from ESP-IDF's own event, the
// one ESPHome reads too, so the glass can tell a network that is not there from a password that is not taken.
#include <algorithm>
#include <cstdint>
#include <string>
#if defined(USE_NETWORK) && !defined(ESP_SCREEN_HOST)
#include "esphome/components/network/util.h"
#endif
#if defined(USE_WIFI) && !defined(ESP_SCREEN_HOST)
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/core/hal.h"
#if defined(USE_ESP32) && __has_include(<esp_wifi.h>)
#include <esp_event.h>
#include <esp_wifi.h>
#define SCREEN_WIFI_EVENTS 1
#endif
#endif

// A build without a network of its own to read (ESPHome's host platform for the renders, the WASM preview) draws what
// these say instead, so every state of the starting screen and the top bar can be looked at without hardware.
#if defined(USE_HOST) || defined(ESP_SCREEN_HOST)
#define SCREEN_HOST_LINK 1
#endif

namespace wifi_status {

struct Problem {
  bool shown = false;
  bool hotspot = false;   // the board opens a hotspot, and it is up now
  std::string ssid, password;
};

// How long the network may be gone before a board without a hotspot says so: long enough for a router that restarts.
constexpr uint32_t NO_HOTSPOT_AFTER_MS = 60000;

// The signal in bars, the way a phone draws it (4 down to 1), and as ESPHome's documentation turns dBm into a
// percentage (wifi_signal: 2 * (dBm + 100), from 0 to 100). One bar is weak: below it a screen loses messages, and the
// top bar's item that shows only then (show: weak) appears.
constexpr int WEAK_DBM = -78;
inline int bars(int rssi) {
  if (rssi >= 0) return 0;  // 0 dBm or more is no reading: ESPHome says 0 or 31 while it holds no network
  return rssi >= -60 ? 4 : rssi >= -70 ? 3 : rssi >= WEAK_DBM ? 2 : 1;
}
inline int percent(int rssi) {
  if (rssi >= 0) return 0;
  const int p = 2 * (rssi + 100);
  return p < 0 ? 0 : p > 100 ? 100 : p;
}
inline bool weak(int rssi) { return rssi < WEAK_DBM; }

struct Link {
  bool wifi = false;        // the board has Wi-Fi and it is switched on
  bool wired = false;       // the selected connection has no Wi-Fi signal
  bool connected = false;   // ESPHome holds the network: joined and an address
  bool joined = false;      // the access point took the screen, the address may still be on its way
  bool hotspot = false;     // the board's own hotspot is up (ESPHome's ap:)
  std::string ssid;         // the network it tries or holds
  std::string address;      // its address while connected
  int rssi = 0;             // dBm while connected
  // The last scan: whether it found the network, and its signal there.
  bool scanned = false, seen = false;
  int seen_rssi = 0;
  // The last time the access point let it go: ESP-IDF's reason and the signal at that moment, and how often.
  uint8_t reason = 0;
  int reason_rssi = 0;
  uint16_t failures = 0;
};

// What keeps the screen off its network, said in words a person can act on.
enum class Trouble : uint8_t { none, not_found, password, weak, failed };
// ESP-IDF's disconnect reasons (esp_wifi_types.h), as numbers so the tests need no ESP-IDF.
inline bool not_found_reason(uint8_t r) { return r == 201 || r == 210 || r == 211 || r == 212; }
// Authentication that failed or timed out in the handshake, where a wrong password ends; a weak signal ends there too,
// so a weak one says weak first.
inline bool password_reason(uint8_t r) { return r == 2 || r == 14 || r == 15 || r == 202 || r == 204; }
inline Trouble trouble(const Link &l) {
  if (!l.wifi || l.connected) return Trouble::none;
  const int signal = l.seen ? l.seen_rssi : l.reason_rssi;
  if (l.scanned && !l.seen) return Trouble::not_found;
  if (signal < 0 && weak(signal) && (l.failures || l.seen)) return Trouble::weak;
  if (password_reason(l.reason)) return Trouble::password;
  if (not_found_reason(l.reason)) return Trouble::not_found;
  return l.failures ? Trouble::failed : Trouble::none;
}

#if defined(USE_WIFI) && !defined(ESP_SCREEN_HOST)
// What the listeners heard. ESP-IDF's event arrives on its own task: a few plain words, each written whole.
struct Heard {
  volatile bool joined = false, scanned = false, seen = false;
  volatile int8_t seen_rssi = 0, reason_rssi = 0;
  volatile uint8_t reason = 0;
  volatile uint16_t failures = 0;
};
inline Heard heard;
#ifdef USE_WIFI_SCAN_RESULTS_LISTENERS
class ScanListener : public esphome::wifi::WiFiScanResultsListener {
 public:
  void on_wifi_scan_results(const esphome::wifi::wifi_scan_vector_t<esphome::wifi::WiFiScanResult> &results) override {
    // ESPHome calls its listeners as the scan ends, before it marks the results that match its networks
    // (get_matches is still false then), so each result is held against the network it tries, with ESPHome's own
    // comparison.
    auto *wifi = esphome::wifi::global_wifi_component;
    if (wifi == nullptr) return;
    const auto wanted = wifi->get_sta();
    if (wanted.get_ssid().size() == 0) return;
    bool seen = false;
    int best = -127;
    for (const auto &result : results)
      if (result.matches(wanted)) { seen = true; best = std::max<int>(best, result.get_rssi()); }
    heard.seen_rssi = seen ? best : 0;
    heard.seen = seen;
    heard.scanned = true;
  }
};
#endif
#ifdef SCREEN_WIFI_EVENTS
inline void on_event(void *, esp_event_base_t base, int32_t id, void *data) {
  if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
    heard.joined = true;
  } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED && data) {
    const auto *it = static_cast<const wifi_event_sta_disconnected_t *>(data);
    heard.joined = false;
    if (it->reason == WIFI_REASON_ROAMING) return;  // a hop to the next access point, nothing wrong
    heard.reason = it->reason;
    heard.reason_rssi = it->rssi;
    if (heard.failures < 0xFFFF) heard.failures = heard.failures + 1;
  }
}
#endif
// Once, from the first look: ESPHome's scan results listener (smart_display's __init__.py asks ESPHome for its slot)
// and ESP-IDF's event beside ESPHome's own handler.
inline void watch(esphome::wifi::WiFiComponent *wifi) {
  static bool watching = false;
  if (watching) return;
  watching = true;
#ifdef USE_WIFI_SCAN_RESULTS_LISTENERS
  static ScanListener listener;
  wifi->add_scan_results_listener(&listener);
#endif
#ifdef SCREEN_WIFI_EVENTS
  esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, nullptr, nullptr);
#endif
  (void) wifi;
}
#endif

#ifdef SCREEN_HOST_LINK
// The preview and the host renders set these to draw a starting screen in any state; by default a good network, so the
// top bar's Wi-Fi item has bars to show there, and no problem.
inline Link host_link = [] { Link l; l.wifi = l.connected = l.joined = true; l.rssi = -58; return l; }();
inline Problem host_problem;
#endif

inline Link link() {
#ifdef SCREEN_HOST_LINK
  return host_link;
#else
  Link l;
#ifdef USE_USB_NETWORK
  auto *usb = esphome::usb_network::global_usb_network;
  if (usb != nullptr && usb->is_connected()) {
    l.wired = l.connected = l.joined = true;
    l.ssid = "USB";
    char address[esphome::network::IP_ADDRESS_BUFFER_SIZE];
    usb->get_ip_addresses()[0].str_to(address);
    l.address = address;
    return l;
  }
#endif
#if defined(USE_WIFI)
  auto *wifi = esphome::wifi::global_wifi_component;
  if (wifi != nullptr && !wifi->is_disabled()) {
    watch(wifi);
    l.wifi = true;
    l.connected = wifi->is_connected();
    const auto sta = wifi->get_sta();
    l.ssid = std::string(sta.get_ssid().c_str(), sta.get_ssid().size());
#ifdef USE_WIFI_AP
    l.hotspot = wifi->has_ap() && wifi->is_ap_active();
#endif
    if (l.connected) {
      l.rssi = wifi->wifi_rssi();
      for (const auto &ip : wifi->wifi_sta_ip_addresses()) {
        if (!ip.is_set()) continue;
        char text[esphome::network::IP_ADDRESS_BUFFER_SIZE];
        ip.str_to(text);
        l.address = text;
        break;
      }
      // A new start of the story for the next time the network goes.
      heard.scanned = heard.seen = false;
      heard.reason = 0;
      heard.failures = 0;
    }
    l.joined = l.connected || heard.joined;
    l.scanned = heard.scanned;
    l.seen = heard.seen;
    l.seen_rssi = heard.seen_rssi;
    l.reason = heard.reason;
    l.reason_rssi = heard.reason_rssi;
    l.failures = heard.failures;
  }
#endif
#ifdef USE_USB_NETWORK
  if (!l.connected && usb != nullptr && usb->is_link_up()) {
    l = Link{};
    l.wired = l.joined = true;
    l.ssid = "USB";
  }
#endif
  return l;
#endif
}

inline Problem problem() {
#ifdef SCREEN_HOST_LINK
  return host_problem;
#endif
  Problem p;
#if defined(USE_WIFI) && !defined(ESP_SCREEN_HOST)
  static uint32_t lost_at = 0;
  auto *wifi = esphome::wifi::global_wifi_component;
  if (wifi == nullptr || wifi->is_disabled()) return p;
  const uint32_t now = esphome::millis();
  if (esphome::network::is_connected()) { lost_at = 0; return p; }
  if (lost_at == 0) lost_at = now ? now : 1;
#ifdef USE_WIFI_AP
  // ESPHome has the hotspot's settings only on a board built with one (USE_WIFI_AP).
  if (wifi->has_ap()) {
    // Said once the hotspot is there to join, not before: until then the screen is still trying its network.
    if (!wifi->is_ap_active()) return p;
    auto ap = wifi->get_ap();
    p.shown = p.hotspot = true;
    p.ssid = std::string(ap.get_ssid().c_str(), ap.get_ssid().size());
    p.password = std::string(ap.get_password().c_str(), ap.get_password().size());
    return p;
  }
#endif
  p.shown = now - lost_at > NO_HOTSPOT_AFTER_MS;
#endif
  return p;
}

}  // namespace wifi_status
