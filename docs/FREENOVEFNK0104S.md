# Freenove FNK0104S, 4 inch, experimental

The **Freenove FNK0104S** is the 4-inch board of Freenove's ESP32-S3 display series: a 320 x 480 panel with an ST7796
controller over SPI, FT6336 capacitive touch over I2C, and an ESP32-S3 with 16 MB flash and octal PSRAM. Tessera runs it
lying down at 480 x 320, a quarter turn of the panel. The 2.8-inch and 3.5-inch boards of the same series (FNK0104A,
FNK0104B and FNK0104N) have other glass and other controllers, and this board file is not for them.

A community member ran this board file on an FNK0104S (see "Who tried what" below). The project has not tried it on
one, so the board is **experimental**.

## Install

Update Tessera Screen Manager and choose **Freenove · 4 inch, FNK0104S** (marked Experimental) in **New screen**. Follow
[Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, and flash it
over USB.

The remote package is `packages/freenovefnk0104s.yaml` and the checkout entry `checkout/freenovefnk0104s.yaml`. Both
combine `packages/core.yaml` with the board file `packages/boards/freenove-fnk0104s.yaml`.

## Layout and capabilities

- Lying down 480 x 320, two columns of two cells; standing up 320 x 480, one column of four. The standard look at
  144 dpi.
- The backlight is a PWM pin (GPIO45) at 20 kHz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The FT6336 reports pixels, so there is no touch calibration.
- The panel needs BGR colour order and inverted colours; the board file sets both.
- No camera package yet: camera tiles, snapshots and media artwork are not included. The board has the PSRAM for them,
  but nobody has tried them on it.

GPIO45 and GPIO46 are strapping pins of the ESP32-S3. On this board they are wired to the backlight and to the panel's
data/command line, so the board file tells ESPHome not to warn about them.

## Who tried what

[@bwalshin](https://github.com/bwalshin) built this board file with ESPHome 2026.9.0 and 2026.6.2 and ran it on an
FNK0104S (#285): the screen started, taps in the middle and in all four corners landed where they should lying down, and
the colours were right once the panel had BGR order and inverted colours. Not tried yet: joining Home Assistant with a
real layout, the brightness setting, standby and the wake by touch, standing up, and a long run.

## Hardware references

| Part | Pins |
| --- | --- |
| Display (ST7796, SPI) | clock GPIO12, data GPIO11, data/command GPIO46, chip select GPIO10, 10 MHz |
| Touch (FT6336, I2C) | SDA GPIO16, SCL GPIO15, interrupt GPIO17, reset GPIO18 |
| Backlight | GPIO45, PWM at 20 kHz |

- [Freenove's documentation for the FNK0104 series](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/Freenove_ESP32S3_Display.html).
- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), with its `ST7796` model.

## What to report while testing

1. A successful boot and appearance in Tessera, with a layout of a few pages.
2. Correct colours lying down and standing up.
3. Taps near each corner, slider drags and edge swipes, both ways up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
