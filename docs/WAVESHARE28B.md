# Waveshare ESP32-S3-Touch-LCD-2.8B, experimental

This is the **ESP32-S3-Touch-LCD-2.8B** ("Type B"): a 2.8-inch 480 x 640 IPS panel with an ST7701S driver over RGB,
GT911 capacitive touch, 8 MB octal PSRAM and 16 MB flash. It is not the ESP32-S3-Touch-LCD-2.8 without the "B", a
240 x 320 SPI panel.
Tried on one board by the contributor: the picture and its colours on a test page (gradients, sixteen grey steps and
the tile colours of the theme), and Tessera running on it. The other points of "What to report while testing" are open.

## Install

Update Tessera Screen Manager and choose **Waveshare · 2.8 inch** (ESP32-S3-Touch-LCD-2.8B, marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.

The remote package is `packages/waveshare28b.yaml`; the checkout entry is `checkout/waveshare28b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare28b.yaml` (which includes
`packages/hardware/waveshare-esp32s3-28b.yaml`), and load `components/mipi_rgb_ws28b`.
The board has one USB-C port, on the chip's own USB; the log goes out over it.

## The display, and why it has a driver of its own

The board's display block is `platform: mipi_rgb_ws28b`, ESPHome 2026.9.0's `mipi_rgb` with one option more,
`send_colmod: false` (components/mipi_rgb_ws28b/README.md). ESPHome always sends COLMOD (0x3A) after a board's init
sequence. With 0x55 (16 bit) or 0x66 (18 bit), this panel reads the RGB lines shifted: on a test page of single bits the
top two bits of every channel stayed dark, gradients repeated four times, greys came out green or purple, and the
pastel tile colours of the theme could not be told apart (a yellow tile looked light green, a grey one purple). No order
of the data pins and no COLCTRL (0xCD 0x08) gave more than three or four working bits per channel. Waveshare's own
example never sends COLMOD; the panel keeps its power-on format, and without it the same test page is right with
Waveshare's pin order.

Everything else follows Waveshare's example (Arduino `Display_ST7701.cpp` and `.h`): the init sequence byte for byte,
the timings and the data lines DATA0..15 = GPIO5, 45, 48, 47, 21, 14, 13, 12, 11, 10, 9, 46, 3, 8, 18, 17. The pixel
clock is 16 MHz instead of the example's 30 MHz.

## Layout and capabilities

- The glass is as large as the CYD's 2.8 inches at twice its density (286 dpi), so it takes the CYD's compact look
  and grid: two columns of three cells lying down, one column of four standing up. An owner may choose up to 3 x 4
  lying down and 2 x 6 standing up; the standard look's 20 mm cell would leave one column standing up. The panel is 480 x 640 standing;
  `ROTATION_LANDSCAPE` 90 lays it down.
- The backlight is a PWM pin of the chip (GPIO6, 20 kHz). Brightness is a percentage; standby, night mode and the
  alert's flashes are enabled.
- Lying down the glass is too low for a picture on an alert, so an alert shows without one (alert_layout); standing
  up it shows one. Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation.
- GT911 reports pixel coordinates, with no resistive calibration.
- The battery charger, the buzzer, the motion sensor (QMI8658), the clock chip (PCF85063) and the SD card stay unused.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2.8B), its pin table and its Arduino and ESP-IDF
  examples.
- I2C: SDA GPIO15, SCL GPIO7, shared by the GT911 (0x5D), the TCA9554 expander (0x20) and the other chips.
- The expander: EXIO1 resets the panel, EXIO2 the touch panel, EXIO3 selects the panel for its setup.
- The ST7701S setup goes over three-wire SPI on GPIO2 (clock) and GPIO1 (data), shared with the SD card.
- RGB: DE GPIO40, PCLK GPIO41, HSYNC GPIO38, VSYNC GPIO39. Touch interrupt GPIO16. Backlight GPIO6.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts. Shifted or inverted colours point
   at the display block.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up. Touch that lands mirrored
   or swapped points at the touch transform.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
