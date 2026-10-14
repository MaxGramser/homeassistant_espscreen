#include "usb_network.h"
#include "esphome/core/application.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/network/util.h"
#include "esp_mac.h"
#include "esp_netif_defaults.h"
#include "esp_netif_net_stack.h"
#include "lwip/etharp.h"
#include "tinyusb_default_config.h"
#include "tinyusb_net.h"
#include "mdns.h"
#include <cstdlib>
#include <cstring>

#ifndef ESPHOME_NETWORK_USB_EXTENSION
#error "Select the matching external network component alongside usb_network"
#endif

// Reuse Espressif's NCM device/configuration descriptors at both USB speeds.
namespace {
const char LANGUAGE[] = {0x09, 0x04};
}

extern "C" void tud_suspend_cb(bool) {
  if (esphome::usb_network::global_usb_network)
    esphome::usb_network::global_usb_network->usb_suspended(true);
}
extern "C" void tud_resume_cb(void) {
  if (esphome::usb_network::global_usb_network)
    esphome::usb_network::global_usb_network->usb_suspended(false);
}

namespace esphome::usb_network {
static const char *const TAG = "usb_network";
USBNetwork *global_usb_network = nullptr;
USBNetwork::USBNetwork() { global_usb_network = this; }

void USBNetwork::fail_(const char *operation, esp_err_t result) {
  ESP_LOGE(TAG, "%s: %s", operation, esp_err_to_name(result));
  if (ip_handler_) {
    esp_event_handler_instance_unregister(IP_EVENT, ESP_EVENT_ANY_ID, ip_handler_);
    ip_handler_ = nullptr;
  }
  if (netif_) {
    esp_netif_destroy(netif_);
    netif_ = nullptr;
  }
  this->mark_failed();
}

void USBNetwork::setup() {
  uint8_t base[6];
  auto result = esp_read_mac(base, ESP_MAC_ETH);
  if (result != ESP_OK) { fail_("Read MAC", result); return; }
  memcpy(device_mac_, base, 6);
  device_mac_[0] = (device_mac_[0] | 2) & 0xFE;  // local, unicast
  memcpy(host_mac_, device_mac_, 6);
  host_mac_[5] ^= 0x80;  // distinct ends of this point-to-point Ethernet link
  snprintf(serial_, sizeof(serial_), "%02X%02X%02X%02X%02X%02X",
           base[0], base[1], base[2], base[3], base[4], base[5]);
  snprintf(mac_string_, sizeof(mac_string_), "%02X%02X%02X%02X%02X%02X",
           host_mac_[0], host_mac_[1], host_mac_[2], host_mac_[3], host_mac_[4], host_mac_[5]);

  esp_netif_inherent_config_t inherent = ESP_NETIF_INHERENT_DEFAULT_ETH();
  inherent.if_key = "USB_NCM";
  inherent.if_desc = "usb";
  inherent.route_prio = 200;  // network core chooses USB once its gateway answers
  if (manual_)
    inherent.flags = static_cast<esp_netif_flags_t>(inherent.flags & ~ESP_NETIF_DHCP_CLIENT);
  esp_netif_config_t config = ESP_NETIF_DEFAULT_ETH();
  config.base = &inherent;
  netif_ = esp_netif_new(&config);
  if (!netif_) { fail_("Create network interface", ESP_ERR_NO_MEM); return; }
  esp_netif_driver_ifconfig_t driver{};
  driver.handle = this;
  driver.transmit = transmit_;
  driver.driver_free_rx_buffer = free_receive_;
  result = esp_netif_set_driver_config(netif_, &driver);
  if (result != ESP_OK) { fail_("Attach transport", result); return; }
  result = esp_netif_set_mac(netif_, device_mac_);
  if (result != ESP_OK) { fail_("Set MAC", result); return; }
  esp_netif_set_hostname(netif_, App.get_name().c_str());
  result = esp_event_handler_instance_register(IP_EVENT, ESP_EVENT_ANY_ID, ip_event_, this, &ip_handler_);
  if (result != ESP_OK) { fail_("Watch IP changes", result); return; }
  if (manual_) {
    esp_netif_ip_info_t ip{};
    ip.ip = manual_ip_;
    ip.gw = gateway_;
    ip.netmask = mask_;
    result = esp_netif_set_ip_info(netif_, &ip);
    if (result != ESP_OK) { fail_("Set address", result); return; }
    esp_netif_dns_info_t dns{};
    dns.ip.type = ESP_IPADDR_TYPE_V4;
    dns.ip.u_addr.ip4 = dns_;
    esp_netif_set_dns_info(netif_, ESP_NETIF_DNS_MAIN, &dns);
  }

  strings_[0] = LANGUAGE;
  strings_[1] = "ESPHome";
  strings_[2] = "ESPHome USB network";
  strings_[3] = serial_;
  strings_[4] = "CDC NCM Ethernet";
  strings_[5] = mac_string_;
  tinyusb_config_t usb = TINYUSB_DEFAULT_CONFIG();
  usb.port = TINYUSB_PORT_HIGH_SPEED_0;
  usb.descriptor.string = strings_;
  usb.descriptor.string_count = 6;
  usb.event_cb = usb_event_;
  usb.event_arg = this;
  result = tinyusb_driver_install(&usb);
  if (result != ESP_OK) { fail_("Install USB HS driver", result); return; }
  tinyusb_net_config_t transport{};
  memcpy(transport.mac_addr, host_mac_, 6);
  transport.on_recv_callback = receive_;
  transport.user_context = this;
  result = tinyusb_net_init(&transport);
  if (result != ESP_OK) {
    tinyusb_driver_uninstall();
    fail_("Install NCM transport", result);
    return;
  }
  ESP_LOGI(TAG, "USB OTG ready; connect the native OTG port to a host sharing its network");
}

void USBNetwork::usb_event_(tinyusb_event_t *event, void *context) {
  auto *self = static_cast<USBNetwork *>(context);
  if (event->id == TINYUSB_EVENT_ATTACHED) {
    self->suspended_.store(false);
    self->mounted_.store(true);
  } else if (event->id == TINYUSB_EVENT_DETACHED) {
    self->mounted_.store(false);
  }
}

void USBNetwork::ip_event_(void *context, esp_event_base_t, int32_t, void *) {
  // IP events arrive on IDF's task; inspect the netif only on ESPHome's main loop.
  // Other interfaces' IP events are harmless and allow route/DNS changes to settle.
  static_cast<USBNetwork *>(context)->address_dirty_.store(true);
}

esp_err_t USBNetwork::receive_(void *buffer, uint16_t length, void *context) {
  auto *self = static_cast<USBNetwork *>(context);
  if (!self->mounted_.load() || length < 14 || length > 1514) return ESP_ERR_INVALID_SIZE;
  if (is_gateway_reply(static_cast<const uint8_t *>(buffer), length,
                       self->probe_gateway_.load(), self->probe_address_.load(), self->device_mac_))
    self->gateway_reply_.store(true);
  // TinyUSB reuses its RX buffer as soon as this callback returns. lwIP owns
  // this copy until driver_free_rx_buffer, including on failed packet input.
  void *copy = malloc(length);
  if (!copy) return ESP_ERR_NO_MEM;
  memcpy(copy, buffer, length);
  return esp_netif_receive(self->netif_, copy, length, nullptr);
}

void USBNetwork::free_receive_(void *, void *buffer) { free(buffer); }

esp_err_t USBNetwork::transmit_(void *context, void *buffer, size_t length) {
  auto *self = static_cast<USBNetwork *>(context);
  if (!self->mounted_.load() || self->suspended_.load()) return ESP_ERR_INVALID_STATE;
  if (length < 14 || length > 1514) return ESP_ERR_INVALID_SIZE;
  // lwIP serializes TX. The synchronous API copies into TinyUSB before returning,
  // so lwIP can release its buffer. Bounded wait, no unbounded frame queue.
  return tinyusb_net_send_sync(buffer, length, nullptr, pdMS_TO_TICKS(20));
}

void USBNetwork::update_link_(bool up) {
  link_up_ = up;
  address_dirty_.store(true);
  if (up) {
    esp_netif_action_start(netif_, nullptr, 0, nullptr);
    esp_netif_action_connected(netif_, nullptr, 0, nullptr);
    ESP_LOGI(TAG, "USB attached; %s", manual_ ? "using static address" : "waiting for host DHCP");
  } else {
    connected_ = false;
    addresses_ = {};
    probe_gateway_.store(0);
    probe_address_.store(0);
    gateway_reply_.store(false);
    gateway_health_.reset();
    esp_netif_action_disconnected(netif_, nullptr, 0, nullptr);
    esp_netif_action_stop(netif_, nullptr, 0, nullptr);
    ESP_LOGI(TAG, "USB detached or suspended");
  }
}

void USBNetwork::update_address_() {
  esp_netif_ip_info_t ip{};
  bool has_ip = link_up_ && esp_netif_is_netif_up(netif_) &&
                esp_netif_get_ip_info(netif_, &ip) == ESP_OK && ip.ip.addr != 0;
  const network::IPAddress address(&ip.ip);
  if (probe_address_.load() != (has_ip ? ip.ip.addr : 0) ||
      probe_gateway_.load() != (has_ip ? ip.gw.addr : 0)) {
    probe_gateway_.store(0);
    probe_address_.store(has_ip ? ip.ip.addr : 0);
    gateway_reply_.store(false);
    gateway_health_.reset();
    probe_gateway_.store(has_ip ? ip.gw.addr : 0);
    addresses_ = {};
    if (has_ip) {
      addresses_[0] = address;
      char text[network::IP_ADDRESS_BUFFER_SIZE];
      address.str_to(text);
      ESP_LOGI(TAG, "USB address: %s", text);
    }
  }
}

void USBNetwork::check_gateway_() {
  const uint32_t gateway = probe_gateway_.load();
  if (!link_up_ || !probe_address_.load() || !gateway) return;
  const uint32_t now = App.get_loop_component_start_time();
  if (gateway_reply_.exchange(false)) gateway_health_.reply();
  gateway_health_.tick(now);
  if (gateway_health_.probe_due(now)) {
    gateway_health_.sent(now);
    // lwIP creates the request and sends it on USB even while Wi-Fi is the
    // default route. No blocking network waits and no extra task or socket.
    ip4_addr_t target{};
    target.addr = gateway;
    LwIPLock lock;
    auto *interface = static_cast<struct netif *>(esp_netif_get_netif_impl(netif_));
    if (interface != nullptr) etharp_request(interface, &target);
  }
}

void USBNetwork::publish_connection_() {
  const bool usable = link_up_ && probe_address_.load() && gateway_health_.ready();
  if (usable != connected_) {
    connected_ = usable;
    ESP_LOGI(TAG, "%s", usable ? "USB gateway reachable; USB preferred" :
                               "USB gateway unavailable; using Wi-Fi when connected");
  }
  if (mdns_registered_ && usable != mdns_up_) {
    const auto action = usable ? MDNS_EVENT_ENABLE_IP4 : MDNS_EVENT_DISABLE_IP4;
    if (mdns_netif_action(netif_, action) == ESP_OK) mdns_up_ = usable;
  }
}

void USBNetwork::register_mdns_() {
#ifdef USE_MDNS
  const auto result = mdns_register_netif(netif_);
  if (result == ESP_OK) {
    mdns_registered_ = true;
    address_dirty_.store(true);
  } else {
    ESP_LOGW(TAG, "USB mDNS registration: %s", esp_err_to_name(result));
    this->set_timeout("mdns_retry", 5000, [this]() { this->register_mdns_(); });
  }
#endif
}

void USBNetwork::loop() {
  const bool up = mounted_.load() && !suspended_.load();
  if (up != link_up_) update_link_(up);
  // All components have completed setup now, including mDNS.
  if (!mdns_attempted_) {
    mdns_attempted_ = true;
    register_mdns_();
  }
  if (address_dirty_.exchange(false)) update_address_();
  check_gateway_();
  publish_connection_();
}

void USBNetwork::dump_config() {
  ESP_LOGCONFIG(TAG, "USB network:\n  Port: native USB OTG HS\n  Class: CDC-NCM\n  Address: %s\n"
                     "  Routing: USB with reachable gateway, Wi-Fi fallback\n"
                     "  Gateway: ARP every 3 s, 3 misses to fall back, 2 replies to recover",
                     manual_ ? "static" : "host DHCP");
}

}  // namespace esphome::usb_network
