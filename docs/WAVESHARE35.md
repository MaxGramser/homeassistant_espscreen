# Waveshare ESP32-S3-Touch-LCD-3.5, 480 × 320

This is the **ESP32-S3-Touch-LCD-3.5**: a 3.5-inch 320 x 480 panel with an ST7796 driver over SPI
(ESPHome's `mipi_spi` component covers it natively) and **FT6336 capacitive touch** over I2C, on an
ESP32-S3 with 16 MB flash. The panel's native orientation is 320 x 480 portrait; the board file runs
it landscape (480 x 320) via a 90° rotation. Confirmed booting, connecting to Home Assistant, and
correct on all four physical corners on a real unit.

## Install

Update Tessera Screen Manager and choose **Waveshare · 3.5 inch** (ESP32-S3-Touch-LCD-3.5) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshare35.yaml`; the checkout entry is `checkout/waveshare35.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-35.yaml`.

## Layout and capabilities

- Landscape: 480 x 320, two columns of two cells. Portrait: 320 x 480, one column of three cells.
- Standard look at 165 dpi, following the existing physical size rules.
- No camera package yet: camera tiles, snapshots and media artwork are not included. The board has the memory
  for them (see "PSRAM" below), but the package has not been added and tested on this glass.
- FT6336 reports pixel coordinates, with no resistive calibration. The touch transform (`TOUCH_SWAP_XY`,
  `TOUCH_MIRROR_X`, `TOUCH_MIRROR_Y`) needs none of `packages/core.yaml`'s `false` defaults changed,
  confirmed on real hardware, see "Testing touch" below.
- The backlight is a direct PWM GPIO (no I2C expander involved): dimming, standby, night mode and the
  alert's flashes all work as on the Guition.
- LVGL uses a 12% draw buffer in the chip's own memory.

## PSRAM

The board's 8 MB of embedded PSRAM is enabled, in octal mode at 80MHz, and confirmed working on a real unit.
An earlier version of this profile left it off, after a boot that hung right after the bootloader with PSRAM
enabled. That hang could not be reproduced later, with the app's ESPHome or with a desktop ESPHome, so it most
likely came from something else in that early configuration. If a unit does hang at boot, removing the `psram:`
block from the board file (or overriding it in the screen's own YAML) is the way back, over USB.

The profile also inverts the panel's colours (`invert_colors: true`): without it every colour shows as its
complement, orange as blue and purple as green.

## Testing touch

No calibration wizard exists for the FT6336 (same as the Guition's GT911: this codebase only has an
affine calibration wizard for the CYD's resistive XPT2046). Confirming touch-coordinate accuracy on a
new unit means reading raw coordinates from the serial log and comparing them against known tap points.
The reliable method: temporarily set the board's rotation substitution to `0` (removes LVGL's rotation
compositing, so the touch controller's own `touch.x`/`touch.y` map directly to the panel's native pixel
grid), then tap known corners in two different physical orientations and log the raw `on_touch`
coordinates. Compare which raw axis tracks which physical axis by holding one axis fixed and varying
the other. A genuine `swap_xy` need shows up as cross-talk (the "wrong" axis changes when it
shouldn't); a `mirror_x`/`mirror_y` need shows up as the same axis moving opposite to the physical tap.
Once derived, set the rotation substitution back to its real value (`90`) and re-verify in the actual
landscape mounting before calling it confirmed. Values found this way: `swap_xy: false`,
`mirror_x: false`, `mirror_y: false`. All three already match `packages/core.yaml`'s defaults, so the
board file overrides none of them.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5) and its
  [schematic](https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5/ESP32-S3-Touch-LCD-3.5-Schematic.pdf).
- [ESPHome `mipi_spi`](https://esphome.io/components/display/mipi_spi/), model `ST7796`.
- SPI: CLK GPIO5, MOSI GPIO1, MISO GPIO2 (wired on the schematic; unused by the write-only display).
- I2C: SDA GPIO8, SCL GPIO7, shared by the FT6336 and the TCA9554 expander (address `0x20`). An RTC and
  an IMU are also on this bus per the schematic but are not used by this profile.
- The display's CS and reset lines are not native GPIOs: both run through the TCA9554 expander (CS on
  EXIO2, reset on EXIO1). `dc_pin` is GPIO3, an ESP32-S3 strapping pin. ESPHome warns about it, but
  it's harmless in practice on this board.
- `color_order: bgr` (not `rgb`) and `spi_mode: 1` as a bare integer are both required for the display
  to respond correctly; confirmed on real hardware, not assumptions from the datasheet.
- Backlight: GPIO6, direct GPIO via PWM (`ledc`), 20 kHz.
- Touch has no interrupt line wired; the FT6336 is polled at a 20 ms interval, confirmed responsive
  enough in practice.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts.
3. Physical taps near each corner, slider drags and edge swipes, in both orientations.
4. Brightness, standby after the timeout and wake by touch, and night mode, several times in a row.
5. A full page of tiles, opening and closing the settings and detail cards, and the quarter/half-turn setting.
6. Free internal heap and free PSRAM with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
