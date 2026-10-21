#include "boot_guard.h"

#include "esphome/core/application.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#ifdef USE_API
#include "esphome/components/api/api_server.h"
#endif
#include "esphome/components/wifi/wifi_component.h"

#include <esp_ota_ops.h>

namespace esphome::boot_guard {

static const char *const TAG = "boot_guard";

#ifdef USE_BOOT_GUARD_HOMETILES_DESCRIPTOR
// Why this exists: HomeTiles' web OTA (src/web/server/handlers/web_admin_ota.cpp, validateRawOtaImageMetadata) accepts an
// image only if bytes 288..411 of it are HomeTiles' own firmware descriptor, and no ESPHome image has one. This puts
// those bytes there, so HomeTiles' web OTA accepts this image once, for the crossover from HomeTiles to this firmware.
// The values are copied from an installed HomeTiles image (guition_jc8012p4a1, pre_v3, revisions 1 to 199).
// ESP-IDF's linker script places .rodata_custom_desc straight after the 256-byte app description, which sits at image
// offset 32: 24 (image header) + 8 (segment header) + 256 = 288. Nothing reads it at run time. `retain` keeps the
// linker's --gc-sections from dropping it (`used` alone does not).
namespace {
struct HomeTilesDescriptor {
  // firmware_meta::DeviceDescriptor
  uint32_t magic_word;  // "DVP4" little endian
  char project_key[32];
  char device_key[32];
  char display_name[32];
  // firmware_meta::SiliconRevisionDescriptor
  uint32_t silicon_magic_word;  // "4VRS" little endian
  uint16_t minimum_revision;
  uint16_t maximum_revision;
  char variant[16];
} __attribute__((packed));
static_assert(sizeof(HomeTilesDescriptor) == 124, "the descriptor is 100 + 24 bytes");

const HomeTilesDescriptor HOMETILES_DESCRIPTOR __attribute__((used, retain, section(".rodata_custom_desc"))) = {
    0x44565034u, "esp32_p4_homeassistant_display", "guition_jc8012p4a1", "Guition JC8012P4A1",
    0x53525634u, 1,                                199,                  "pre_v3",
};
}  // namespace
#endif

static const char *state_name(esp_ota_img_states_t s) {
  switch (s) {
    case ESP_OTA_IMG_NEW: return "new";
    case ESP_OTA_IMG_PENDING_VERIFY: return "pending verify";
    case ESP_OTA_IMG_VALID: return "valid";
    case ESP_OTA_IMG_INVALID: return "invalid";
    case ESP_OTA_IMG_ABORTED: return "aborted";
    default: return "undefined";
  }
}

void BootGuard::publish_(const char *state) {
#ifdef USE_TEXT_SENSOR
  if (this->state_sensor_ != nullptr)
    this->state_sensor_->publish_state(state);
#endif
}

void BootGuard::setup() {
  const esp_partition_t *running = esp_ota_get_running_partition();
  esp_ota_img_states_t st = ESP_OTA_IMG_UNDEFINED;
  if (running == nullptr || esp_ota_get_state_partition(running, &st) != ESP_OK || st != ESP_OTA_IMG_PENDING_VERIFY) {
    ESP_LOGI(TAG, "image already valid (OTA state: %s); the guard does nothing", state_name(st));
    this->publish_("valid");
    this->disable_loop();
    return;
  }
  ESP_LOGW(TAG, "image is pending verification: confirm after %us with Wi-Fi%s, or roll back at %us",
           (unsigned) (this->cfg_.confirm_after_ms / 1000), this->cfg_.require_api_client ? " and an API client" : "",
           (unsigned) (this->cfg_.deadline_ms / 1000));
  this->publish_("pending");
}

bool BootGuard::confirm_() {
  const esp_partition_t *running = esp_ota_get_running_partition();
  if (running != esp_ota_get_boot_partition()) {
    // The next boot is not this image: marking would act on another one.
    ESP_LOGE(TAG, "running partition is not the boot partition; cannot confirm");
    return false;
  }
#ifdef USE_SAFE_MODE_PRESENT_FOR_BOOT_GUARD
  if (this->safe_mode_ != nullptr)
    this->safe_mode_->mark_successful();
#endif
  esp_err_t err = esp_ota_mark_app_valid_cancel_rollback();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "esp_ota_mark_app_valid_cancel_rollback failed: %s", esp_err_to_name(err));
    return false;
  }
  esp_ota_img_states_t st = ESP_OTA_IMG_UNDEFINED;
  if (esp_ota_get_state_partition(running, &st) == ESP_OK && st != ESP_OTA_IMG_VALID) {
    ESP_LOGE(TAG, "image state is '%s' after confirming", state_name(st));
    return false;
  }
  return true;
}

void BootGuard::roll_back_(const char *why) {
  ESP_LOGE(TAG, "not confirmed by the deadline (%s); rolling back to the previous firmware", why);
  this->publish_("rolling back");
  delay(200);  // NOLINT: let the log and the state go out
  esp_ota_mark_app_invalid_rollback_and_reboot();
  // Only returns when there is nothing to go back to.
  ESP_LOGE(TAG, "no rollback possible; restarting");
  App.reboot();
}

void BootGuard::loop() {
  const uint32_t uptime = millis();
#ifdef USE_API
  if (!this->api_seen_ && api::global_api_server != nullptr && api::global_api_server->is_connected()) {
    this->api_seen_ = true;
    ESP_LOGI(TAG, "an API client has connected");
  }
#else
  this->api_seen_ = true;
#endif
  const bool wifi_up = wifi::global_wifi_component != nullptr && wifi::global_wifi_component->is_connected();

  Decision d = decide(uptime, wifi_up, this->api_seen_, this->cfg_);
  if (d == Decision::CONFIRM && this->confirm_failed_)
    d = uptime >= this->cfg_.deadline_ms ? Decision::ROLLBACK : Decision::WAIT;

  switch (d) {
    case Decision::CONFIRM:
      if (this->confirm_()) {
        ESP_LOGI(TAG, "image confirmed after %us", (unsigned) (uptime / 1000));
        this->publish_("confirmed");
        this->disable_loop();
      } else {
        this->confirm_failed_ = true;
      }
      break;
    case Decision::ROLLBACK: {
      const char *m = missing(uptime, wifi_up, this->api_seen_, this->cfg_);
      this->roll_back_(m != nullptr ? m : "the image could not be marked valid");
      break;
    }
    case Decision::WAIT:
      if (uptime - this->last_report_ms_ >= 60000) {
        this->last_report_ms_ = uptime;
        const char *m = missing(uptime, wifi_up, this->api_seen_, this->cfg_);
        ESP_LOGI(TAG, "waiting (%us): %s", (unsigned) (uptime / 1000), m != nullptr ? m : "all conditions hold");
      }
      break;
  }
}

void BootGuard::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Boot guard:\n"
                "  Confirm after: %us\n"
                "  Deadline: %us\n"
                "  Require API client: %s",
                (unsigned) (this->cfg_.confirm_after_ms / 1000), (unsigned) (this->cfg_.deadline_ms / 1000),
                YESNO(this->cfg_.require_api_client));
#ifdef USE_BOOT_GUARD_HOMETILES_DESCRIPTOR
  ESP_LOGCONFIG(TAG, "  HomeTiles OTA descriptor: yes");
#endif
}

}  // namespace esphome::boot_guard
