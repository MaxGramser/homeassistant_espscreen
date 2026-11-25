#pragma once
// The chip a screen runs on and its silicon revision, for the "Screen chip" sensor (packages/core.yaml) and so for ESP
// Screen Manager, which builds every later firmware of the screen for that revision (docs/CHIP_REVISIONS.md).
//
// Why it matters: a chip family can change its silicon in a way a firmware cannot cross. An ESP32-P4 before revision 3
// and one of revision 3 need different builds (hardware/esp32p4-core.yaml, CHIP_REVISION), and the boards look the same
// from outside, label included. The app reads the revision from the chip on the USB cable while it installs; this
// sensor tells it for a screen that was installed another way, or before the app read it, so its next update is built
// right as well.
//
// It knows the chip and the revision ESP-IDF reads from the eFuses, nothing about a board or what a revision means:
// the YAML layer of a chip family decides that. tests/test_chip_revision.cpp proves the words on a PC.
#include <cstdio>
#include <string>

#if defined(ESP_PLATFORM)
#include "hal/efuse_hal.h"
#include "sdkconfig.h"
#endif

namespace chip_revision {

// The chip as esptool names it ("esp32p4" -> "ESP32-P4", "esp32" -> "ESP32") and its revision as ESP-IDF numbers it,
// major x 100 + minor: "ESP32-P4 v3.2" for 302. The app reads the number back from the "v<major>.<minor>".
inline std::string words(const char *target, unsigned full) {
  std::string chip;
  for (const char *c = target; c && *c; ++c) chip += (*c >= 'a' && *c <= 'z') ? char(*c - 'a' + 'A') : *c;
  if (chip.size() > 5 && chip.compare(0, 5, "ESP32") == 0) chip.insert(5, "-");
  char text[48];
  std::snprintf(text, sizeof(text), "%s v%u.%u", chip.c_str(), full / 100, full % 100);
  return text;
}

// This chip, from its eFuses; "unknown" off the chip (the host builds and the editor's preview).
inline std::string said() {
#if defined(ESP_PLATFORM)
  return words(CONFIG_IDF_TARGET, efuse_hal_chip_revision());
#else
  return "unknown";
#endif
}

}  // namespace chip_revision
