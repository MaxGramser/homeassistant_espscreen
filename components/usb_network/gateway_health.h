#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace esphome::usb_network {

// A DHCP lease can outlive host Internet Sharing. Probe its local gateway over
// this USB interface, not via the default route (which may already be Wi-Fi).
// ARP works even when the host firewall blocks ICMP echo. It does not test WAN.
class GatewayHealth {
 public:
  static constexpr uint32_t INTERVAL_MS = 3000;
  static constexpr uint32_t TIMEOUT_MS = 1000;
  bool ready() const { return ready_; }
  bool probe_due(uint32_t now) const { return !waiting_ && (!started_ || now - sent_ >= INTERVAL_MS); }
  void sent(uint32_t now) { started_ = waiting_ = true; sent_ = now; }
  void reply() {
    if (!waiting_) return;
    waiting_ = false;
    failures_ = 0;
    if (successes_ < 2) ++successes_;
    if (successes_ == 2) ready_ = true;
  }
  void tick(uint32_t now) {
    if (!waiting_ || now - sent_ < TIMEOUT_MS) return;
    waiting_ = false;
    successes_ = 0;
    if (failures_ < 3) ++failures_;
    if (failures_ == 3) ready_ = false;
  }
  void reset() { *this = GatewayHealth{}; }

 private:
  bool ready_{false}, waiting_{false}, started_{false};
  uint8_t failures_{0}, successes_{0};
  uint32_t sent_{0};
};

// IP arguments are in network byte order, as supplied by esp_netif. Only a
// reply addressed to this device for the current gateway counts, not arbitrary
// host traffic or a cached ARP entry left over from when sharing was enabled.
inline bool is_gateway_reply(const uint8_t *frame, size_t length, uint32_t gateway,
                             uint32_t local, const uint8_t *mac) {
  if (!gateway || !local || length < 42) return false;
  const uint8_t header[] = {0x08, 0x06, 0x00, 0x01, 0x08, 0x00, 0x06, 0x04, 0x00, 0x02};
  return memcmp(frame + 12, header, sizeof(header)) == 0 &&
         memcmp(frame, mac, 6) == 0 && memcmp(frame + 32, mac, 6) == 0 &&
         memcmp(frame + 28, &gateway, 4) == 0 && memcmp(frame + 38, &local, 4) == 0;
}

}  // namespace esphome::usb_network
