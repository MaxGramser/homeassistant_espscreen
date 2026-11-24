// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_chip_revision.cpp -o /tmp/test_chip_revision && /tmp/test_chip_revision
// The words of the "Screen chip" sensor (components/smart_display/chip_revision.h): the chip as esptool names it and
// ESP-IDF's revision as v<major>.<minor>, which ESP Screen Manager reads back (screen_manager/app/chip_revision.py).
#include "../components/smart_display/chip_revision.h"
#include <cassert>
#include <cstdio>

int main() {
  assert(chip_revision::words("esp32p4", 302) == "ESP32-P4 v3.2");
  assert(chip_revision::words("esp32p4", 103) == "ESP32-P4 v1.3");
  assert(chip_revision::words("esp32p4", 300) == "ESP32-P4 v3.0");
  assert(chip_revision::words("esp32s3", 2) == "ESP32-S3 v0.2");
  assert(chip_revision::words("esp32", 301) == "ESP32 v3.1");
  assert(chip_revision::words("esp32c61", 100) == "ESP32-C61 v1.0");
  // Off the chip the sensor says so instead of a revision.
  assert(chip_revision::said() == "unknown");
  std::puts("chip revision: ESP32-P4 v3.2 for 302, unknown off the chip");
  return 0;
}
