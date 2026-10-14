#pragma once

#include <atomic>
#include "esphome/core/component.h"
#include "esphome/components/network/ip_address.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "tinyusb.h"
#include "gateway_health.h"

namespace esphome::usb_network {

class USBNetwork : public Component {
 public:
  USBNetwork();
  void setup() override;
  void loop() override;
  void dump_config() override;
  // NetworkComponent initializes esp_netif at AFTER_BLUETOOTH (300).
  float get_setup_priority() const override { return 255.0f; }
  bool is_connected() const { return connected_; }
  bool is_link_up() const { return link_up_; }
  esp_netif_t *get_esp_netif() const { return netif_; }
  network::IPAddresses get_ip_addresses() const { return addresses_; }
  const char *get_use_address() const { return use_address_; }
  void set_use_address(const char *value) { use_address_ = value; }
  void set_manual_ip(network::IPAddress ip, network::IPAddress gateway, network::IPAddress mask,
                     network::IPAddress dns) {
    manual_ = true; manual_ip_ = ip; gateway_ = gateway; mask_ = mask; dns_ = dns;
  }
  void usb_suspended(bool value) { suspended_.store(value); }

 protected:
  static void usb_event_(tinyusb_event_t *event, void *context);
  static void ip_event_(void *context, esp_event_base_t base, int32_t id, void *data);
  static esp_err_t receive_(void *buffer, uint16_t length, void *context);
  static esp_err_t transmit_(void *context, void *buffer, size_t length);
  static void free_receive_(void *context, void *buffer);
  void update_link_(bool up);
  void update_address_();
  void check_gateway_();
  void publish_connection_();
  void register_mdns_();
  void fail_(const char *operation, esp_err_t result);
  esp_netif_t *netif_{nullptr};
  std::atomic<bool> mounted_{false};
  std::atomic<bool> suspended_{false};
  std::atomic<bool> address_dirty_{true};
  std::atomic<bool> gateway_reply_{false};
  std::atomic<uint32_t> probe_gateway_{0}, probe_address_{0};
  GatewayHealth gateway_health_;
  esp_event_handler_instance_t ip_handler_{nullptr};
  bool link_up_{false};
  bool connected_{false};
  bool manual_{false};
  bool mdns_registered_{false};
  bool mdns_up_{false};
  bool mdns_attempted_{false};
  network::IPAddresses addresses_{};
  network::IPAddress manual_ip_, gateway_, mask_, dns_;
  const char *use_address_{nullptr};
  uint8_t device_mac_[6]{};
  uint8_t host_mac_[6]{};
  char serial_[13]{};
  char mac_string_[13]{};
  const char *strings_[6]{};
};

extern USBNetwork *global_usb_network;

}  // namespace esphome::usb_network
