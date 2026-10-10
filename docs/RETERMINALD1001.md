# Seeed reTerminal D1001

An 8-inch 800 x 1280 MIPI-DSI panel with GSL3670 capacitive touch, on an ESP32-P4 with 32 MB of flash and PSRAM and an
ESP32-C6 for Wi-Fi, running on a 2500 mAh battery. Board key `reterminald1001`, status experimental, board file
`packages/boards/reterminald1001.yaml`. The pins come from Seeed's BSP
([Seeed-Studio/reTerminal-D1001](https://github.com/Seeed-Studio/reTerminal-D1001), `esp32_p4_re_terminal_d1001.h`).

## What it has, and where Tessera configures it

| Part | Chip, pins | In Tessera |
|---|---|---|
| Panel | JD9365, 2 MIPI-DSI lanes | ESPHome's `mipi_dsi` preset `SEEED-RETERMINAL-D1001` |
| Touch | GSL3670 on GPIO37/38 (`touch_bus`) | ESPHome's `gsl3670` preset of the same name |
| Wi-Fi | ESP32-C6 over SDIO, GPIO6-11, reset GPIO13 | `hardware/esp32p4-c6.yaml` with this board's pins |
| Power, resets | XL9535 expander on GPIO20/21 (`board_bus`) | the board file |
| Backlight | PWM on GPIO14, at 1220 Hz | `features/backlight.yaml` |
| Battery | voltage on GPIO18 through a divider of two, charging on GPIO15 | `features/battery-adc.yaml` with Seeed's discharge curve |
| Speaker | ES8311 and an NS4150B, on its own I2S bus | `features/audio.yaml` |
| Microphones | two, through an ES7210, on a second I2S bus | `features/audio.yaml` |
| Motion | LSM6DS3TR-C at 0x6A | its temperature, and Wake when moved |
| Clock | PCF8563 at 0x51 | keeps the time while Home Assistant is away |
| Button | GPIO3, high while pressed | the core's Wake and Sleep |
| RGB LED | GPIO22, 36, 23, lit low | `features/rgb-led.yaml` |
| Camera | SC2356, 1 MIPI-CSI lane, SCCB 0x36 | not yet (below) |
| SD card, LTE, LoRa | | not configured |

## Things to know

- **The expander's numbers.** ESPHome numbers the XL9535's two ports 0-7 and 10-17, Seeed's BSP its sixteen lines 0-15.
  The BSP's line 8 (the power hold) is pin 10 in ESPHome, its line 10 (the charger) pin 12, its line 12 (the touch
  reset) pin 14.
- **The power hold.** On the battery, the board turns itself off unless pin 10 stays high; the board file holds it on.
- **The log is on USB.** `hardware/esp32p4-c6.yaml` puts the log on UART0, whose pins on the ESP32-P4 are GPIO37 and
  GPIO38, the touch bus on this board; UART0 there crashed the first boot. The board file moves the log to the USB port.
- **16 MB of the 32.** ESPHome takes OTA on 32 MB of flash only with ESP-IDF's experimental features, so the firmware
  uses the first 16 MB, as the other P4 boards do.
- **Wake when moved** feels the board itself: picked up, moved or knocked. It does not see someone walking past.

## The camera

The SC2356's driver is in Seeed's copy of Espressif's `esp_cam_sensor` (1.2.0), not in Espressif's own (2.6.0). The
driver's interface is the same in both, and a sensor registers itself through a linker section every library takes
part in, so the driver can be built as a component of its own beside the current `esp_video`. What is still open is
the ISP tuning (`esp_ipa`), without which the picture is unprocessed. Until ESPHome has a MIPI-CSI camera of its own
(pull requests #19480 and #16944), the camera belongs in a plugin.

## Tried on the glass

Picture, colours, the way up, touch in every corner, a card held open, the settings strip, Wi-Fi, the battery, the
button, the LED, Home Assistant's TTS through the speaker, the Extras page and card. Firmware 0.53.0 from the `d1001`
branch, chip revision v1.3.
