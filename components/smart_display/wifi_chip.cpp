// The Wi-Fi co-processor's restart and firmware (wifi_chip.h says why).
#include "wifi_chip.h"
#include "esphome/core/defines.h"

#ifdef USE_ESP32_HOSTED
#include <cinttypes>
#include <cstdio>

#include <esp_hosted.h>
#include <esp_hosted_host_fw_ver.h>
#include <esp_rom_sys.h>
#include <esp_system.h>

#include "esphome/components/wifi/wifi_component.h"
#include "esphome/core/log.h"

namespace wifi_chip {

namespace {

constexpr const char *TAG = "wifi_chip";

void reset_whole_system() { esp_rom_software_reset_system(); }

// Before app_main, so before every other handler: esp_restart() runs them newest first, this one last.
__attribute__((constructor)) void restart_whole() { esp_register_shutdown_handler(reset_whole_system); }

std::string told;

}  // namespace

std::string firmware() {
  if (!told.empty())
    return told;
  auto *wifi = esphome::wifi::global_wifi_component;
  if (wifi == nullptr || !wifi->is_connected())
    return "unknown";
  esp_hosted_coprocessor_fwver_t ver{};
  char text[64];
  if (esp_hosted_get_coprocessor_fwversion(&ver) == ESP_OK) {
    snprintf(text, sizeof(text), "ESP-Hosted %" PRIu32 ".%" PRIu32 ".%" PRIu32 " (host %d.%d.%d)", ver.major1,
             ver.minor1, ver.patch1, ESP_HOSTED_VERSION_MAJOR_1, ESP_HOSTED_VERSION_MINOR_1,
             ESP_HOSTED_VERSION_PATCH_1);
  } else {
    snprintf(text, sizeof(text), "ESP-Hosted unknown (host %d.%d.%d)", ESP_HOSTED_VERSION_MAJOR_1,
             ESP_HOSTED_VERSION_MINOR_1, ESP_HOSTED_VERSION_PATCH_1);
  }
  told = text;
  ESP_LOGI(TAG, "Wi-Fi co-processor: %s", text);
  return told;
}

}  // namespace wifi_chip

#else

namespace wifi_chip {

std::string firmware() { return "unknown"; }

}  // namespace wifi_chip

#endif
