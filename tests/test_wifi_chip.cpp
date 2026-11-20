// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_wifi_chip.cpp -o /tmp/test_wifi_chip && /tmp/test_wifi_chip
// The Wi-Fi co-processor's firmware (components/smart_display/wifi_chip.h, FirmwareOnce): asked once, never before Wi-Fi
// is up, and never again once it answered.
#include "../components/smart_display/wifi_chip.h"
#include <cassert>
#include <cstdio>

int main() {
  wifi_chip::FirmwareOnce once;
  bool up = false;
  int asks = 0;
  auto ask = [&asks] { ++asks; return std::string("ESP-Hosted 2.3.2 (host 2.12.12)"); };
  // Before Wi-Fi is up: "unknown", and the C6 is not asked (the question goes over the link Wi-Fi brings up).
  for (int i = 0; i < 3; ++i) assert(once.get([&up] { return up; }, ask) == "unknown");
  assert(asks == 0 && once.asked == 0);
  // Up: asked once, and its words are the answer from then on, also when Wi-Fi goes again.
  up = true;
  assert(once.get([&up] { return up; }, ask) == "ESP-Hosted 2.3.2 (host 2.12.12)");
  up = false;
  for (int i = 0; i < 5; ++i) assert(once.get([&up] { return up; }, ask) == "ESP-Hosted 2.3.2 (host 2.12.12)");
  assert(asks == 1 && once.asked == 1);
  std::puts("wifi chip: asked once, never before Wi-Fi");
  return 0;
}
