# Waveshare ESP32-S3-Touch-LCD-4B, experimental

Added in app 0.2.126, firmware 0.2.102.
This is the **ESP32-S3-Touch-LCD-4B**: a 4-inch 480 x 480 IPS panel with an ST7701S driver over RGB, GT911 capacitive
touch, 8 MB octal PSRAM and 16 MB flash. It is not the older ESP32-S3-Touch-LCD-4 without the "B", which has other pins.
Physical acceptance has not been performed.

Up to firmware 0.3.9 this board started without its tiles: a light page with only the page buttons, and every save
answered with "Use the Easy Setup profile". Its board file had a boot step of its own that replaced the shared boot
steps (docs/PROFILES.md, "Which value wins"). Firmware 0.3.10 removed that step, and from then until 0.6.1 the panel
only drew after a restart that kept the board powered: after a cold start the backlight lit a black screen while touch
worked. ESPHome's software SPI claims the panel's setup lines before the expander starts, and the expander starts with
every line an input, so the setup never reached the panel (ESPHome issue #11748). Firmware 0.6.1 parks those lines
with three outputs that start after the expander and before the display, and keeps the shared boot steps. Update such
a screen to 0.6.1 or later.

## Install

Update Tessera Screen Manager and choose **Waveshare · 4 inch** (ESP32-S3-Touch-LCD-4B, marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshare4b.yaml`; the checkout entry is `checkout/waveshare4b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-4b.yaml`.
The board has two USB-C ports. Logs go out over the one with the USB-to-UART chip, as on the 4-inch Guition.

## Layout and capabilities

- The glass has the size and resolution of the 4-inch Guition, so the screen looks the same: two columns of three cells,
  the same tiles in millimetres, the standard look at 170 dpi. The glass is square, so it turns a quarter as well as a half.
- The backlight hangs on a PWM pin of the chip (GPIO4), not on an I2C expander as on the 4.3-inch and 7-inch Waveshares.
  Brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes are enabled, as on the Guition.
  GPIO4 is the analog dim input of the LED driver (an AP3032), not a switch for the LEDs: it reaches the driver's feedback
  pin through a 160 Hz filter, and the driver stops altogether once that level passes about 1.78 V. So the pin runs at
  300 kHz, the dimmest step stays just inside the steady range, 0 stays dark, and the light skips ESPHome's gamma
  (firmware 0.39.0; before, everything under 74 % brightness was dark).
  The 4.3-inch browned out when it switched its backlight on from dark; on this board only the PWM duty falls, but the
  wake from a dark standby has not been seen on this hardware yet.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM implementation.
- GT911 reports pixel coordinates, with no resistive calibration. The existing touch filter and action guard remain in use.
- The battery charger (AXP2101), the audio chips, the microphone, the speaker connector, the motion sensor and the clock chip
  on the board stay unused. The screen runs from USB; a battery on the connector is neither read nor managed.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-4B) and its schematic.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/), with the generic `ST7701S` model and this board's pins.
  ESPHome's `WAVESHARE-4-480X480` model belongs to the board without the "B" and does not fit this one.
- The pins and timings follow a community configuration that runs this board with ESPHome
  ([alaltitov/Waveshare-ESP32-S3-Touch-LCD-4B](https://github.com/alaltitov/Waveshare-ESP32-S3-Touch-LCD-4B)).
- I2C: SDA GPIO47, SCL GPIO48, shared by the GT911, the TCA9554 expander (0x20) and the other chips.
- The ST7701S takes its setup over three-wire SPI on the expander: CS on EXIO0, data on EXIO1, clock on EXIO2.
  EXIO3 enables the speaker amplifier and stays off.
- RGB: DE GPIO17, PCLK GPIO9, HSYNC GPIO46, VSYNC GPIO3, 16 MHz pixel clock, 18-bit pixel mode, inverted colours.
- Backlight: GPIO4, PWM at 300 kHz, inverted, `min_power: 0.52` (duty 48 % at the dimmest), `zero_means_zero`, gamma 1.0.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts. Shifted, mirrored or inverted
   colours point at the display block.
3. Physical taps near each corner, slider drags and edge swipes, and the quarter-turn setting. Touch that lands mirrored
   or swapped points at the touch transform.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
