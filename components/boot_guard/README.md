# boot_guard

A strict way to confirm a new firmware image on a panel that is out of reach.

ESP-IDF's bootloader can roll back to the firmware before when a freshly flashed image resets before it is marked
valid (`ESP_OTA_IMG_PENDING_VERIFY`). ESPHome's `safe_mode` marks it valid after `boot_is_good_after` of uptime
(a minute by default) whether or not the panel has a network, and on any orderly shutdown (`boot_is_good_on_shutdown`).
A panel that cannot reach Wi-Fi would be confirmed and stranded. `boot_guard` confirms only a firmware that proved it
can be reached.

```yaml
external_components:
  - source: {type: local, path: components}
    components: [boot_guard]

boot_guard:
  confirm_after: 180s          # default
  deadline: 15min              # default
  require_api_client: true     # default
  hometiles_ota_descriptor: false
  state:                       # optional text sensor
    name: "Boot guard"

# What a strict install also wants (the guard needs rollback and safe_mode):
safe_mode:
  boot_is_good_after: 30min    # longer than the deadline, so the guard decides first
  boot_is_good_on_shutdown: false
esp32:
  framework:
    advanced:
      enable_ota_rollback: true
```

## What it does

It acts only when the running partition is `ESP_OTA_IMG_PENDING_VERIFY`. Any other state logs "image already valid"
and the guard goes to sleep. Otherwise, in `loop()`:

- **Confirm** when all hold: uptime is at least `confirm_after`, Wi-Fi is connected right now, and (with
  `require_api_client`) a native API client has connected at least once since boot (latched). It calls safe_mode's
  `mark_successful()` when there is a safe_mode, then `esp_ota_mark_app_valid_cancel_rollback()` when the running
  partition is the boot partition, and checks the state afterwards.
- **Roll back** when that has not happened by `deadline`: it logs what was missing and calls
  `esp_ota_mark_app_invalid_rollback_and_reboot()`, then `App.reboot()` if that returns (nothing to go back to).

The decision is a pure function, `boot_guard::decide(uptime_ms, wifi_up, api_seen, cfg)` in
`boot_guard_decision.h`, tested on a computer by `tests/test_boot_guard.cpp`.

`state` publishes `pending`, `confirmed`, `valid` (it was never pending) or `rolling back`.

What the guard does not stop: an OTA started through ESPHome marks the running image valid first
(`ota_backend_esp_idf.cpp`), so do not send one before the guard has confirmed. With `boot_is_good_on_shutdown: false`
any reset before the confirmation, including ESPHome's own reboot timeouts, is a rollback.

## hometiles_ota_descriptor

HomeTiles' web OTA accepts an image only if bytes 288 to 411 are its own firmware descriptor
(`firmware_meta::DeviceDescriptor` and `SiliconRevisionDescriptor`: project `esp32_p4_homeassistant_display`, device
`guition_jc8012p4a1`, silicon `pre_v3`, revisions 1 to 199). With this option the component puts exactly those 124 bytes
in `.rodata_custom_desc`, where ESP-IDF's linker script places them straight after the app description, so HomeTiles
accepts the image once, for the crossover. Leave it off for a panel that never ran HomeTiles. It is the JC8012P4A1's
descriptor: another board needs its own values.
