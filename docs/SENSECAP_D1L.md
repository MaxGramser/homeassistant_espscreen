# Seeed SenseCAP Indicator D1L, experimental

The **SenseCAP Indicator D1L**, SKU 114993070, has a 3.95-inch 480 x 480 RGB display, FT6336U capacitive touch,
an ESP32-S3 with 8 MB flash and 8 MB octal PSRAM, and a separate RP2040. This profile supports the
**GX/ST7701S display variant** only. Seeed's SDK also lists DX panels; those are not covered by this board file.
Check the label and hardware revision before installing.

Wi-Fi, display, touch and backlight have been tested on a community-owned GX unit. The board remains experimental;
physical acceptance by the project has not been performed.

## Install

For a build from this repository, use `checkout/sensecapd1l.yaml` and follow [the checkout guide](../checkout/README.md).
The remote package is `packages/sensecapd1l.yaml`. Both combine `packages/core.yaml` with
`packages/boards/seeed-sensecap-indicator-d1l.yaml`, which takes the ESP32-S3 and PSRAM settings from
`packages/hardware/esp32s3-rgb.yaml`. The board key is `sensecapd1l`.

The remote entry needs the board support published in the selected repository branch. Until then, use the checkout
entry rather than the default remote package.

The Indicator exposes two USB serial interfaces through a hub: CH340 for the ESP32 and a separate RP2040 interface,
which may report `INDICATOR RP2040`. Identify the ESP32 interface and confirm ESP32-S3 before writing.
This profile programs only the ESP32 and leaves the RP2040 firmware unchanged.

Keep a private flash backup and check [Seeed's recovery instructions](https://wiki.seeedstudio.com/SenseCAP_Indicator_How_To_Flash_The_Default_Firmware/)
before replacing existing firmware. The board uses ESPHome's 8 MB flash layout, not the project's special
[4 MB migration layout](FLASH_LAYOUT.md). A factory reset button is not a replacement for a recovery image.

## Layout and capabilities

- A square 480 x 480 canvas, starting with two columns of three cells. Rotation changes both the picture and touch.
- The standard look at 171.85 dpi, rounded to 172 dpi in the catalog, so controls keep their size in millimetres.
- The shared S3 PSRAM ceilings of 128 tiles, 24 pages and 12 top bar items. The runtime memory budget still limits
  what a layout takes ([Tile memory](TILE_MEMORY.md)); these ceilings are not a measured full-capacity guarantee.
- The backlight is a PWM pin at 100 Hz. Brightness, standby and night controls use the shared backlight feature.
  Override YAML can change the frequency with `BACKLIGHT_FREQUENCY`.
- Capacitive touch reports pixels, with no resistive calibration. Page swipes start at the left or right edge of
  the glass, not in the middle of a tile.
- LVGL uses a 12 % draw buffer, an eighth of the frame under ESPHome's buffer rules. Octal PSRAM runs at 80 MHz.
- Camera pictures and snapshots are not enabled in this profile.
- LoRa, Grove, SD, the buzzer and the physical user button are not configured. Grove, SD and the buzzer belong to
  the RP2040. There is no battery.

The D1L is the LoRa variant, not the D1S environmental-sensor variant. This profile does not add sensor support or
cover the separate Meshtastic product.

## Hardware notes

| Part | Pins or address |
| --- | --- |
| I2C bus | SDA GPIO39, SCL GPIO40 |
| PCA9535 expander | I2C 0x20, native `pca9554` with `pin_count: 16` |
| LCD SPI | clock GPIO41, MOSI GPIO48 |
| LCD CS / reset | expander 4 / 5 |
| FT6336U touch | `ft5x06`, I2C 0x48 |
| Touch reset | expander 7, held high |
| Backlight | GPIO45, active high, LEDC 100 Hz |
| Unused LoRa CS | expander 0, held high to deselect the radio |
| RP2040 reset | expander 8, not configured |

ESPHome's native `mipi_rgb` model `SEEED-INDICATOR-D1` supplies the RGB data pins and porches; pixel clock is 16 MHz.
Touch polls every 20 ms because its interrupt is on expander bit 6, not an internal ESP32 GPIO.
Both touch axes are mirrored to match the display preset. Do not add a second correction in LVGL.

## Tried on the glass

Community testing of the packaged profile confirmed the display and colours, touch in the corners and centre,
slider drags, page buttons and edge swipes, settings and detail cards, rotation, brightness, standby and wake,
cold boot, settings persistence and normal-use stability. Wi-Fi, encrypted API connectivity and layout delivery
were also confirmed. These are reports from one GX unit, not project-maintainer acceptance or verification of
other hardware revisions.

OTA updates and maximum-capacity layouts have not been separately validated. When testing another unit, report its
revision, the layout size, time running and any display glitches, missed touches, resets or Wi-Fi drops.
Do not publish credentials or device identifiers with a report.

## Hardware references

- [Seeed D1L product PDF, SKU114993070](https://files.seeedstudio.com/Bazaar/product_pdf/114993070.pdf).
- [Seeed hardware diagram](https://files.seeedstudio.com/wiki/SenseCAP/SenseCAP_Indicator/SenseCAP_Indicator_6.png).
- [Seeed SDK panel selection](https://github.com/Seeed-Solution/SenseCAP_Indicator_ESP32/blob/77edb8d2b9a92fc67965c1b2d4a838f0d09a1800/components/bsp/Kconfig.projbuild).
- [ESPHome 2026.9.0 native display preset](https://github.com/esphome/esphome/blob/2026.9.0/esphome/components/mipi_rgb/models/st7701s.py).
- [Published ESPHome Indicator configuration](https://devices.esphome.io/devices/seeed-sensecap/).
