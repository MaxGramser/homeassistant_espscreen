#include "components/usb_network/gateway_health.h"
#include <array>
#include <cassert>
#include <cstring>
using namespace esphome::usb_network;

int main() {
  GatewayHealth health;
  uint32_t now = 0;
  auto answer = [&]() {
    assert(health.probe_due(now));
    health.sent(now);
    health.reply();
    now += GatewayHealth::INTERVAL_MS;
  };
  auto miss = [&]() {
    assert(health.probe_due(now));
    health.sent(now);
    health.tick(now + GatewayHealth::TIMEOUT_MS - 1);
    assert(!health.probe_due(now + GatewayHealth::TIMEOUT_MS - 1));
    health.tick(now + GatewayHealth::TIMEOUT_MS);
    now += GatewayHealth::INTERVAL_MS;
  };
  // An address and unsolicited traffic alone do not make USB usable.
  health.reply();
  assert(!health.ready());
  answer(); assert(!health.ready());
  answer(); assert(health.ready());
  // A lost packet does not flap the route. Stopping sharing with the lease and
  // cable still present eventually falls back, then requires stable recovery.
  miss(); assert(health.ready());
  answer(); assert(health.ready());
  miss(); assert(health.ready());
  miss(); assert(health.ready());
  miss(); assert(!health.ready());
  health.reply(); assert(!health.ready());  // late reply after timeout
  answer(); assert(!health.ready());
  miss(); assert(!health.ready());
  answer(); assert(!health.ready());
  answer(); assert(health.ready());
  // Disconnect/address changes discard previous success; millis wrap is safe.
  health.reset(); assert(!health.ready());
  now = UINT32_MAX - 100;
  miss(); answer(); answer(); assert(health.ready());

  const uint8_t mac[] = {2, 3, 4, 5, 6, 7};
  const uint8_t gateway_bytes[] = {192, 168, 2, 1}, local_bytes[] = {192, 168, 2, 2};
  uint32_t gateway, local;
  memcpy(&gateway, gateway_bytes, 4); memcpy(&local, local_bytes, 4);
  std::array<uint8_t, 42> frame{};
  const uint8_t arp_reply[] = {0x08, 0x06, 0, 1, 0x08, 0, 6, 4, 0, 2};
  memcpy(frame.data(), mac, 6); memcpy(frame.data() + 12, arp_reply, 10);
  memcpy(frame.data() + 28, &gateway, 4); memcpy(frame.data() + 32, mac, 6);
  memcpy(frame.data() + 38, &local, 4);
  assert(is_gateway_reply(frame.data(), frame.size(), gateway, local, mac));
  for (size_t length = 0; length < frame.size(); ++length)
    assert(!is_gateway_reply(frame.data(), length, gateway, local, mac));
  assert(!is_gateway_reply(frame.data(), frame.size(), local, gateway, mac));
  assert(!is_gateway_reply(frame.data(), frame.size(), 0, local, mac));
  for (size_t offset : {0, 12, 14, 16, 18, 20, 21, 28, 32, 38}) {
    frame[offset] ^= 1;
    assert(!is_gateway_reply(frame.data(), frame.size(), gateway, local, mac));
    frame[offset] ^= 1;
  }
}
