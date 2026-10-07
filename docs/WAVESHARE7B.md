# Waveshare ESP32-S3-Touch-LCD-7B, experimental

Added in app 0.4.14, on the shared firmware 0.9.0, for [issue #25](https://github.com/MaxGramser/homeassistant_espscreen/issues/25).
This is the **ESP32-S3-Touch-LCD-7B**: a 7-inch 1024 x 600 IPS panel over RGB, GT911 capacitive touch, 8 MB octal
PSRAM and 16 MB flash. It is not the 800 x 480 ESP32-S3-Touch-LCD-7 without the "B" ([its own page](WAVESHARE7.md)),
which has another expander chip. Physical acceptance has not been performed.

## Install

Update Tessera Screen Manager and choose **Waveshare · 7 inch** (ESP32-S3-Touch-LCD-7B, marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshare7b.yaml`; the checkout entry is `checkout/waveshare7b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-7b.yaml`.
The board needs ESPHome 2026.7.0 or newer, the first release with a component for its expander. Tessera Screen Manager
builds with a newer one; a build of your own in ESPHome Device Builder needs at least that version.
The board's one USB-C port goes through a USB-to-UART chip, and the logs go out over it.

## Layout and capabilities

- Landscape: 1024 x 600, four columns of four cells. Portrait: 600 x 1024, two columns of seven cells.
- The standard look at 170 dpi, the density of the 4-inch Guition, so a tile keeps the size it has there.
- The backlight takes levels: brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes
  are enabled. The level is the PWM output of the board's expander. Its enable line goes high once, at start, and
  never low again, so a dark standby is the darkest the PWM gives rather than a backlight switched off. The 4.3-inch
  Waveshare browned out when it switched its backlight on from fully dark; this board never does that, but the wake
  from standby has not been seen on this hardware yet.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM implementation.
  Their operation on this board still needs physical verification.
- GT911 reports pixel coordinates, with no resistive calibration. The existing touch filter and action guard remain in use.
- LVGL uses an 8 % draw buffer, about the same amount of internal memory as the 800 x 480 boards use.
- The SD card slot, the CAN and RS485 ports, the battery connector and the clock chip on the board stay unused.

## Hardware references

- [Waveshare documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-7B) and its pin tables.
- [ESPHome Waveshare CH32V003 I/O Expander](https://esphome.io/components/waveshare_io_ch32v003/): the expander at
  I2C address 0x24, with eight lines, one PWM output and one ADC.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/). ESPHome has no model for this board: its
  `WAVESHARE-5-1024X600` model expects a CH422G, so the board file uses the `RPI` model (an RGB panel without an init
  sequence) with this board's pins and timings.
- The timings follow Waveshare's demo, as a community configuration that runs this board with ESPHome has them
  ([agillis/esphome-modular-lvgl-buttons](https://github.com/agillis/esphome-modular-lvgl-buttons)).
- I2C: SDA GPIO8, SCL GPIO9, shared by the GT911 and the expander. The GT911's interrupt line is GPIO4.
- Expander lines: EXIO1 touch reset, EXIO2 backlight enable, EXIO3 panel reset, EXIO6 panel supply.
- RGB: DE GPIO5, PCLK GPIO7, HSYNC GPIO46, VSYNC GPIO3, 30 MHz pixel clock, the same data pins as the 4.3-inch and
  7-inch Waveshare boards.
- Backlight: the expander's PWM output, inverted, between the levels 1 and 247 that ESPHome gives for this board.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts. A picture that drifts sideways,
   flickers or has shifted colours points at the display block and its pixel clock.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up. Touch that lands mirrored
   or swapped points at the touch transform.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
