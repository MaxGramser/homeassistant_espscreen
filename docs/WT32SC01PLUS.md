# Wireless-Tag WT32-SC01 Plus, 3.5 inch, experimental

The **WT32-SC01 Plus** from Wireless-Tag is a 3.5-inch 480 x 320 board: an ST7796UI panel on an 8-bit bus, FT6336U
capacitive touch over I2C, and an ESP32-S3 with 16 MB flash and 8 MB octal PSRAM. It is not the older WT32-SC01 without
"Plus", which has an ESP32 and other pins.

Community members have run this board file on the board (see "Who tried what" below). The project has not tried it on
one, so the board is **experimental**.

## Install

Update Tessera Screen Manager and choose **WT32 · 3.5 inch, WT32-SC01 Plus** (marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, then
flash it over USB or download the firmware for ESPHome Web. There is no touch calibration: the touch panel reports
pixels.

The remote package is `packages/wt32sc01plus.yaml` and the checkout entry `checkout/wt32sc01plus.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/wt32sc01plus.yaml`.

## Layout and capabilities

- Lying down 480 x 320, two columns of two cells; standing up 320 x 480, one column of three. The standard look at
  165 dpi, the size and resolution of the Guition JC3248W535 and the Waveshare 3.5-inch.
- The backlight is a PWM pin (GPIO45) at 150 Hz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The FT6336U reports pixels and is read through its interrupt line.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation. They have not been tried on this board yet.
- LVGL draws through a quarter of the screen (`LVGL_BUFFER_SIZE: "25%"`).

## Who tried what

[@cjd](https://github.com/cjd) ran this board file on a WT32-SC01 Plus with ESPHome 2026.9.0, flashed over USB and over
Wi-Fi (#238): the touch lands where it should, the colours are right, and dimming and standby work.
[@wiktorschmidt](https://github.com/wiktorschmidt) reported it working on their own board. Not tried yet: camera
pictures, standing up, and a full layout over a long run.

## Hardware references

| Part | Pins |
| --- | --- |
| Display bus (8 data lines) | write clock GPIO47, data GPIO9, GPIO46, GPIO3, GPIO8, GPIO18, GPIO17, GPIO16, GPIO15 |
| Display control | data/command GPIO0 and reset GPIO4, from ESPHome's model |
| Touch (FT6336U, I2C 0x38) | SDA GPIO6, SCL GPIO5, interrupt GPIO7 |
| Backlight | GPIO45, PWM |

GPIO0, GPIO3, GPIO45 and GPIO46 are strapping pins of the ESP32-S3, wired to the panel and the backlight on this board.

- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), model `WT32-SC01-PLUS`: the panel's init
  sequence, its size, its colour order and its control pins.
- [A shop page for the board](https://www.seeedstudio.com/WT32-3-5-Inch-Display-p-5542.html).

## What to report while testing

1. A successful boot and appearance in Tessera.
2. Correct colours lying down and standing up.
3. Taps near each corner, slider drags and edge swipes, both ways up.
4. Camera tile pictures, full-screen camera images and camera alerts.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
