# Waveshare ESP32-S3-Touch-AMOLED-2.41, 600 × 450

This is the **ESP32-S3-Touch-AMOLED-2.41**: a 2.41-inch 450 x 600 AMOLED panel with an RM690B0 driver over QSPI
(ESPHome's `qspi_dbi` component, model `RM690B0`) and **FT6336 capacitive touch** over I2C, on an ESP32-S3 with 16 MB
flash and 8 MB of octal PSRAM. The panel's native orientation is 450 x 600 portrait; the board file lays it down
(600 x 450) with a 90° rotation, and the screen stands it up a quarter further. The board is experimental: it boots,
joins Home Assistant, takes its layout, dims and shows camera pictures on a real unit, and the rest of the list below
is still to be walked.

## Install

Update Tessera Screen Manager and choose **Waveshare · 2.41 inch** (ESP32-S3-Touch-AMOLED-2.41) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it
is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshareamoled241.yaml`; the checkout entry is `checkout/waveshareamoled241.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshareamoled241.yaml`.

A screen flashed from its own YAML instead (a build from a clone) must give its name as the `DEVICE_NAME`
substitution, not as `esphome: name:`. Tessera finds the screen's action from its **Device name** sensor, which reports
`DEVICE_NAME`; when the two differ, Tessera calls an action that does not exist and the screen waits for Tessera.

## Layout and capabilities

- Lying down: 600 x 450, two columns of two cells. Standing up: 450 x 600, one column of four cells.
- The glass is about 49 x 37 mm, smaller than the CYD's, so the board takes the **compact look**, at 311.2 dpi
  (750 diagonal pixels over 2.41 inches). A screen takes up to three by three cells lying down and two by five
  standing up. A saved layout whose grid is larger than that is not sent: choose a grid within it in the screen's
  settings in Tessera.
- Camera pictures (`features/camera.yaml`): camera tiles, their live picture and the full-screen picture. Standing
  up, an alert shows its picture above the words; lying down the alert card has no room for one, so it shows without.
- An AMOLED has no backlight. `features/backlight.yaml` drives a template output, `gpio_backlight_pwm`, that hands
  each level to the panel's own brightness command (DCS `0x51`, `qspi_dbi`'s `set_brightness`). The panel shows nothing
  below about 20 of 255, so a lit screen starts there and 0 is dark. Dimming and standby work through it.
- FT6336 reports pixel coordinates, with no calibration. The touch transform needs none of `packages/core.yaml`'s
  `false` defaults changed: taps land where they are made on a unit standing up, turned half way.
- LVGL uses a 12% draw buffer in the chip's own memory.
- The panel draws from its own memory while it is written, so a frame that LVGL sends in strips could show half old
  and half new. On Rev 2.0 the panel's tearing signal (`OLED_TE`) is on GPIO21, and `features/panel-sync.yaml` makes the
  first strip of every frame wait for it. Rev 1 has the panel's reset on GPIO21 and is not supported by this board file.

## Known limits lying down

The glass is 37 mm high lying down, and two cards that stack keys a finger can use do not fit in that height. Both
fit standing up, which is the way to hang this screen for now.

- **A light's colour card**: its three rows (colour, white shade and brightness) each keep a finger's height and
  their words, and with the card's top bar they need about 48 mm. The brightness row ends below the glass.
- **An alarm panel's keypad**: its bottom row of keys is cut off, and the keys cover the panel's state line.

The render (`tools/render/run.py waveshareamoled241`) reports both; standing up
(`waveshareamoled241-portrait`) it passes.

## The panel's offset

The RM690B0 has 480 columns and this glass shows 450 of them, from column 16. The board file gives the display
`offset_width: 16`, as Waveshare's own demo for this board does. Without it the picture stands 16 pixels off one side
of the glass and is cut off at the other: the page bar's arrow on that side is clipped and the tiles reach the edge.
LVGL turns the picture in software, so the one offset holds in every orientation.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-AMOLED-2.41).
- [ESPHome `qspi_dbi`](https://esphome.io/components/display/qspi_dbi/), model `RM690B0`.
- QSPI: CLK GPIO10, data GPIO11 to GPIO14, CS GPIO9.
- I2C: SDA GPIO47, SCL GPIO48, shared by the FT6336 (address `0x38`, interrupt on GPIO3) and the TCA9554 expander
  (address `0x20`).
- The display's reset runs through the expander on EXIO0 and the touch panel's on EXIO1. This is the pinout of
  Rev 2.0 of the board; an earlier revision without the expander needs other reset pins.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. A stable picture with an even margin on both sides, across several page changes and cold starts.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up.
4. Brightness, standby after the timeout and wake by touch, and night mode, several times in a row.
5. An alert: the card, its blinks, and closing it.
6. A camera tile with its live picture, and the picture full screen.
7. Free internal heap and free PSRAM with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
