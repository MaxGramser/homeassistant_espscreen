"""Exercise the real network helpers and route arbiter with fake link events."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NetworkRouting(unittest.TestCase):
    def test_usb_priority_fallback_and_plain_wifi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def put(name, text):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text)

            for name in ("util.h", "util.cpp", "network_component.h", "network_component.cpp"):
                put("esphome/components/network/" + name,
                    (ROOT / "components/network" / name).read_text())
            put("esphome/core/defines.h", "#pragma once\n#define ESPHOME_ALWAYS_INLINE\n")
            put("esphome/core/component.h", """#pragma once
#include <cstdint>
namespace esphome {
namespace setup_priority { constexpr float AFTER_BLUETOOTH = 300; }
class Component { public: virtual void setup() {} virtual void loop() {} virtual void dump_config() {}
virtual float get_setup_priority() const { return 0; } void mark_failed() {} };
}
""")
            put("esphome/core/application.h", """#pragma once
#include <string>
#include <cstdint>
namespace esphome { struct Application {
uint32_t now = 0; std::string name = "panel";
const std::string &get_name() const { return name; }
uint32_t get_loop_component_start_time() const { return now; }
}; inline Application App; }
""")
            put("esphome/core/helpers.h", """#pragma once
#include <cstdio>
namespace esphome {
struct LwIPLock {};
inline void make_name_with_suffix_to(char *out, size_t size, const char *name, size_t, char,
                                     const char *suffix, size_t) { snprintf(out, size, "%s.%s", name, suffix); }
}
""")
            put("esphome/core/log.h", """#pragma once
#define ESP_LOGE(...)
#define ESP_LOGW(...)
#define ESP_LOGI(...)
#define ESP_LOGCONFIG(...)
""")
            put("esp_err.h", """#pragma once
using esp_err_t = int;
constexpr int ESP_OK = 0, ESP_ERR_INVALID_STATE = 1;
""")
            put("esp_event.h", '#include "esp_err.h"\ninline int esp_event_loop_create_default() { return 0; }\n')
            put("esp_netif.h", """#pragma once
#include "esp_err.h"
struct esp_netif_obj { int value; };
using esp_netif_t = esp_netif_obj;
inline void *netif_default = nullptr;
inline int route_changes = 0;
inline int esp_netif_init() { return 0; }
inline int esp_netif_set_default_netif(esp_netif_t *n) { netif_default = n; ++route_changes; return 0; }
inline const char *esp_netif_get_desc(esp_netif_t *) { return "test"; }
inline void *esp_netif_get_netif_impl(esp_netif_t *n) { return n; }
""")
            put("esp_netif_net_stack.h", '#include "esp_netif.h"\n')
            put("lwip/netif.h", '#include "esp_netif.h"\n')
            put("lwip/opt.h", '#define TCP_SND_BUF 5744\n')
            put("esphome/components/network/ip_address.h", """#pragma once
#include <array>
namespace esphome::network {
struct IPAddress { int value = 0; bool is_set() const { return value != 0; } };
using IPAddresses = std::array<IPAddress, 5>;
}
""")
            for component, cls, global_name in (("wifi", "WiFiComponent", "global_wifi_component"),
                                                ("usb_network", "USBNetwork", "global_usb_network")):
                name = "wifi_component.h" if component == "wifi" else "usb_network.h"
                put(f"esphome/components/{component}/{name}", f"""#pragma once
#include "esphome/components/network/ip_address.h"
#include "esp_netif.h"
namespace esphome::{component} {{
struct {cls} {{
bool online = false, failed = false, disabled = false;
network::IPAddresses addresses{{}}; esp_netif_t netif{{0}}; const char *address = nullptr;
bool is_connected() const {{ return online; }}
bool is_disabled() const {{ return disabled; }}
bool is_failed() const {{ return failed; }}
const char *get_use_address() const {{ return address; }}
network::IPAddresses get_ip_addresses() const {{ return addresses; }}
esp_netif_t *get_esp_netif() {{ return &netif; }}
esp_netif_t *get_esp_netif_sta() {{ return &netif; }}
}};
inline {cls} *{global_name} = nullptr;
}}
""")
            put("test.cpp", """
#include "esphome/components/network/util.h"
#include "esphome/components/network/network_component.h"
#include "esphome/core/application.h"
#include <cassert>
#include <cstring>
using namespace esphome;
int main() {
  wifi::WiFiComponent wifi;
  wifi::global_wifi_component = &wifi;
  wifi.online = true; wifi.addresses[0].value = 42; wifi.address = "wifi.local";
#ifdef USE_USB_NETWORK
  usb_network::USBNetwork usb;
  usb_network::global_usb_network = &usb;
  usb.addresses[0].value = 43; usb.address = "usb.local";
#endif
  network::NetworkComponent routes;
  routes.setup(); routes.loop();
  char name[network::USE_ADDRESS_BUFFER_SIZE];
  assert(network::is_connected());
  assert(!network::is_disabled());
  assert(network::get_ip_addresses()[0].value == 42);
  assert(!strcmp(network::get_use_address_to(name), "wifi.local"));
  assert(netif_default == &wifi.netif);
#ifdef USE_USB_NETWORK
  // USB's cable alone is not enough: it does not become online before DHCP.
  usb.online = true; routes.loop();
  assert(netif_default == &usb.netif);
  assert(network::get_ip_addresses()[0].value == 43);
  assert(!strcmp(network::get_use_address_to(name), "usb.local"));
  wifi.online = false;
  assert(network::is_connected());  // USB alone satisfies API/provisioning
  // Wi-Fi returns while USB is still up: USB remains preferred.
  wifi.online = true; routes.loop();
  assert(netif_default == &usb.netif);
  usb.online = false; routes.loop();
  assert(netif_default == &wifi.netif);
  assert(network::get_ip_addresses()[0].value == 42);
  assert(!strcmp(network::get_use_address_to(name), "wifi.local"));
  // The same IP after reconnect must still restore the route.
  usb.online = true; routes.loop();
  assert(netif_default == &usb.netif);
#endif
  auto *winner = netif_default;
  const int changes = route_changes;
  routes.loop(); assert(route_changes == changes);
  netif_default = nullptr; App.now += 1001; routes.loop();
  assert(netif_default == winner && route_changes == changes + 1);
  wifi.online = false;
#ifdef USE_USB_NETWORK
  usb.online = false;
#endif
  assert(!network::is_connected()); routes.loop();
  wifi.online = true; routes.loop(); assert(netif_default == &wifi.netif);
}
""")
            for usb in (False, True):
                with self.subTest(usb=usb):
                    binary = root / ("usb" if usb else "wifi")
                    command = [shutil.which("c++"), "-std=c++20", "-I" + str(root),
                               "-DUSE_NETWORK", "-DUSE_ESP32", "-DUSE_WIFI", "-DUSE_NETWORK_DEFAULT_ROUTE"]
                    if usb:
                        command += ["-DUSE_USB_NETWORK"]
                    command += [str(root / "test.cpp"), str(root / "esphome/components/network/util.cpp"),
                                str(root / "esphome/components/network/network_component.cpp"), "-o", str(binary)]
                    compiled = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
