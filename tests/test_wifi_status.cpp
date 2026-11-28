// What the screen says of its network (firmware 0.38.0): the bars and percentage of a signal, what keeps it off its
// network, and the top bar's own items (wifi_status.h, header_bar.h).
#include "screen_text_en.h"
#include "components/smart_display/header_bar.h"
#include <cassert>
#include <cstdio>
using namespace wifi_status;
using header_bar::Device;
using header_bar::Item;
using header_bar::Kind;

static Link trying(const char *ssid) {
  Link l;
  l.wifi = true;
  l.ssid = ssid;
  return l;
}

int main() {
  // Bars as a phone draws them; no reading is no bars.
  assert(bars(0) == 0 && bars(31) == 0);
  assert(bars(-40) == 4 && bars(-60) == 4 && bars(-61) == 3 && bars(-70) == 3 && bars(-71) == 2 && bars(-78) == 2);
  assert(bars(-79) == 1 && bars(-95) == 1);
  // ESPHome's documented percentage: 2 * (dBm + 100), held between 0 and 100.
  assert(percent(-50) == 100 && percent(-40) == 100 && percent(-75) == 50 && percent(-100) == 0 && percent(-110) == 0);
  assert(percent(0) == 0);
  assert(weak(-79) && !weak(-78) && !weak(-50));

  // Nothing is wrong before anything happened, and nothing while connected.
  assert(trouble(Link{}) == Trouble::none);
  Link l = trying("Home");
  assert(trouble(l) == Trouble::none);
  l.connected = true;
  l.failures = 3;
  l.reason = 202;
  assert(trouble(l) == Trouble::none);

  // A scan without the network: not found, whatever the last reason was.
  l = trying("Home");
  l.scanned = true;
  assert(trouble(l) == Trouble::not_found);
  l.reason = 202;
  l.failures = 1;
  assert(trouble(l) == Trouble::not_found);
  // ESP-IDF's own "no access point" reasons say the same without a scan.
  for (uint8_t reason : {201, 210, 211, 212}) {
    l = trying("Home");
    l.reason = reason;
    l.failures = 1;
    assert(trouble(l) == Trouble::not_found);
  }

  // The network is there and strong, the handshake fails: the password.
  for (uint8_t reason : {2, 14, 15, 202, 204}) {
    l = trying("Home");
    l.scanned = l.seen = true;
    l.seen_rssi = -55;
    l.reason = reason;
    l.reason_rssi = -55;
    l.failures = 2;
    assert(trouble(l) == Trouble::password);
  }
  // The same failure on a weak signal says weak: a weak signal times out the handshake too.
  l = trying("Home");
  l.scanned = l.seen = true;
  l.seen_rssi = -86;
  l.reason = 15;
  l.failures = 1;
  assert(trouble(l) == Trouble::weak);
  // Without a scan the signal of the disconnect decides.
  l = trying("Home");
  l.reason = 204;
  l.reason_rssi = -88;
  l.failures = 1;
  assert(trouble(l) == Trouble::weak);
  // Anything else after a failure: it could not connect and tries again.
  l = trying("Home");
  l.reason = 205;
  l.reason_rssi = -60;
  l.failures = 1;
  assert(trouble(l) == Trouble::failed);

  // The top bar's Wi-Fi item: the icon alone, a percentage or dBm, the bars by the signal.
  Item wifi;
  wifi.kind = header_bar::kind("wifi");
  assert(wifi.kind == Kind::wifi && header_bar::kind("link") == Kind::link);
  Device good{true, -58, true}, weak_signal{true, -84, true}, none{false, 0, true};
  auto shown = header_bar::device_item(wifi, good);
  assert(shown.shown && shown.icon == header_bar::WIFI_GLYPHS[4] && shown.text.empty());
  wifi.text = "%";
  assert(header_bar::device_item(wifi, good).text == "84%");
  wifi.text = "dBm";
  assert(header_bar::device_item(wifi, good).text == "-58 dBm");
  shown = header_bar::device_item(wifi, weak_signal);
  assert(shown.icon == header_bar::WIFI_GLYPHS[1] && shown.text == "-84 dBm");
  // Without a network: the bars struck through and no number.
  shown = header_bar::device_item(wifi, none);
  assert(shown.shown && shown.icon == header_bar::WIFI_OFF_GLYPH && shown.text.empty());
  // Only when weak: gone on a good signal, there on a weak one or without a network.
  wifi.only_weak = true;
  assert(!header_bar::device_item(wifi, good).shown);
  assert(header_bar::device_item(wifi, weak_signal).shown && header_bar::device_item(wifi, none).shown);

  // The link: only while Home Assistant or Tessera is away.
  Item link;
  link.kind = Kind::link;
  assert(!header_bar::device_item(link, good).shown);
  shown = header_bar::device_item(link, Device{true, -58, false});
  assert(shown.shown && shown.icon == header_bar::LINK_GLYPH && shown.text.empty());
  // Every other item is none of these.
  Item clock;
  clock.kind = Kind::clock;
  assert(!header_bar::device_item(clock, good).shown);

  // The signal is asked of the radio at most every RSSI_MS and remembered in between; a lost network forgets it, so the
  // first look after joining asks at once (Signal: on an ESP32-P4 every question is an RPC to the Wi-Fi chip).
  Signal s;
  int asked = 0;
  auto ask = [&asked] { ++asked; return -61; };
  assert(s.read(1000, ask) == -61 && asked == 1);                 // the first look asks
  assert(s.read(1000 + RSSI_MS - 1, ask) == -61 && asked == 1);   // within RSSI_MS it remembers
  assert(s.read(1000 + RSSI_MS, ask) == -61 && asked == 2);       // then it asks again
  assert(s.read(1000 + RSSI_MS + 1, ask) == -61 && asked == 2);
  s.forget();
  assert(s.rssi == 0);
  assert(s.read(1000 + RSSI_MS + 2, ask) == -61 && asked == 3);   // joined again: asked at once
  // millis() wrapping round neither stops the asking nor forces it.
  Signal w;
  w.read(0xFFFFFF00u, ask);
  assert(w.read(0x00000100u, ask) == -61 && asked == 4);          // 512 ms later: remembered
  assert(w.read(0x00001500u, ask) == -61 && asked == 5);          // 5632 ms later: asked

  std::puts("test_wifi_status: PASS");
  return 0;
}
