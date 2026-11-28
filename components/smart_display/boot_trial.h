#pragma once
// A firmware on trial (docs/CAMERA.md, "A new firmware's first minute"). After an update ESPHome's safe mode confirms the
// new firmware once it has run boot_is_good_after (a minute); a restart before that and the bootloader puts the old
// firmware back. Live streams wait for that confirmation: on a P4 the first streams of a boot load the SDIO link to the
// Wi-Fi co-processor at the moment the Wi-Fi itself is set up over it, and a Tab5 with two live tiles restarted inside
// that minute on every boot of a new firmware, so the rollback took every fix away with it, and the crash record and
// loop_record's lines with it. Waiting, the tiles show their stills for that minute; a restart after it leaves the new
// firmware in place, and its next boot logs where the main loop was.
//
// Only an update puts a firmware on trial: an ordinary restart starts the streams as before. Without rollback (a
// build without safe mode, the host) nothing is ever on trial.
#include <cstdint>

#if defined(USE_ESP32) && defined(USE_OTA_ROLLBACK)
#include <esp_ota_ops.h>
#include "esphome/core/log.h"
#endif

namespace boot_trial {

// How often the partition's state is read while on trial: it lives in the otadata sectors of the flash.
inline constexpr uint32_t CHECK_MS = 2000;

// Whether the running firmware still waits for its confirmation. Once confirmed it stays so until the next boot.
inline bool on(uint32_t now) {
#if defined(USE_ESP32) && defined(USE_OTA_ROLLBACK)
  static bool confirmed = false, said = false;
  static uint32_t checked_at = 0;
  static bool trial = false;
  if (confirmed) return false;
  if (said && now - checked_at < CHECK_MS) return trial;
  checked_at = now;
  esp_ota_img_states_t state;
  const esp_partition_t *running = esp_ota_get_running_partition();
  trial = running && esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY;
  if (trial && !said) ESP_LOGI("boot_trial", "A new firmware on trial: live streams wait until it is confirmed");
  if (!trial) {
    confirmed = true;
    if (said) ESP_LOGI("boot_trial", "The new firmware is confirmed: live streams may start");
  }
  said = true;
  return trial;
#else
  (void) now;
  return false;
#endif
}

}  // namespace boot_trial
