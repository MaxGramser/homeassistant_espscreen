# Hosyond ES3C28P, 2.8 inch, experimental

The **ES3C28P** is LCDWiki's (QDtech's) 2.8-inch ESP32-S3 display board, sold as the Hosyond 2.8" ESP32-S3: a 240 x
320 IPS panel with an ILI9341V controller over 4-wire SPI, FT6336G capacitive touch over I2C, and an ESP32-S3 with 16 MB
flash and 8 MB octal PSRAM. Tessera runs it lying down at 320 x 240, a quarter turn of the panel.

It has the CYD's glass and resolution, so it gets the CYD's compact look and grid, but it is **not the CYD**
(ESP32-2432S028): another chip, other pins and a capacitive touch panel. A CYD profile or the Waveshare 3.5-inch profile
shows nothing or a noisy picture on it. The **ES3N28P** is the same board without touch and is not this file.

A community member runs this board file on his own boards (see "Who tried what" below). The project has not tried it on
one, so the board is **experimental**.

## Install

Update Tessera Screen Manager and choose **Hosyond · 2.8 inch, ES3C28P** (marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, and
flash it over USB.

After the first flash over USB, take the power away once and give it back: without that power cycle LVGL can hang half
drawn on the first start.

The remote package is `packages/es3c28p.yaml` and the checkout entry `checkout/es3c28p.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/es3c28p.yaml`, which declares the board and includes its
hardware, `packages/hardware/lcdwiki-es3c28p.yaml`.

## Layout and capabilities

- Lying down 320 x 240, two columns of three cells; standing up 240 x 320, one column of four. The compact look at
  143 dpi, as on the CYD.
- With its PSRAM the board holds 128 tiles on up to 24 pages, where the CYD holds 64 on eight.
- The backlight is a PWM pin (GPIO45) at 1 kHz, ESPHome's default as on the CYD: brightness is a percentage, and standby,
  night mode, Sleep, Wake and the alert's flashes are enabled. `zero_means_zero` keeps a dark standby dark.
- The FT6336G reports pixels, so there is no touch calibration. Its interrupt and reset wiring (GPIO17, GPIO18) is
  the Freenove FNK0104S's.
- The panel needs inverted colours (without them every colour is its complement); the board file sets them. Its reset
  is tied to the chip's reset, so the display has no `reset_pin`.
- The log goes over the native USB-C port (USB-Serial-JTAG).
- No camera package yet: camera tiles, snapshots and media artwork are not included. The board has the PSRAM for them,
  but nobody has tried them on it.

GPIO45 and GPIO46 are strapping pins of the ESP32-S3. On this board they are wired to the backlight and to the panel's
data/command line, so the board file tells ESPHome not to warn about them.

## Who tried what

[StefanHAJ](https://github.com/StefanHAJ) runs two of these boards: one with a plain ESPHome configuration on the same
pins, and one as a Tessera screen built from this board file (first from his fork, with Tessera's core and component
from the release, ESPHome 2026.10), joined to Home Assistant with a layout and a plugin. Touch, colours and the backlight
are right lying down. Not tried yet: standing up, camera pictures, and a long run with a full layout.

## Hardware references

| Part | Pins |
| --- | --- |
| Display (ILI9341V, SPI) | clock GPIO12, data GPIO11, MISO GPIO13 (unused), data/command GPIO46, chip select GPIO10, 40 MHz; reset on the chip's reset |
| Touch (FT6336G, I2C at 0x38) | SDA GPIO16, SCL GPIO15, 400 kHz, interrupt GPIO17, reset GPIO18 |
| Backlight | GPIO45, PWM at 1 kHz, high is lit |

- [LCDWiki: 2.8inch ESP32-S3 Display (ES3C28P / ES3N28P)](https://www.lcdwiki.com/2.8inch_ESP32-S3_Display).
- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), with its `ILI9341` model.

## What to report while testing

1. A successful boot and appearance in Tessera, with a layout of a few pages.
2. Correct colours lying down and standing up.
3. Taps near each corner, slider drags and edge swipes, both ways up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
