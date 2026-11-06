# Waveshare ESP32-S3-Touch-LCD-2.8B, experimental

This is the **ESP32-S3-Touch-LCD-2.8B**: a 2.8-inch 480 x 640 IPS panel (standing up by nature) with an ST7701S driver
over RGB, GT911 capacitive touch, 8 MB octal PSRAM and 16 MB flash. It is neither the 4-inch 4B
([WAVESHARE4B.md](WAVESHARE4B.md)) nor the 240 x 320 Waveshare 2.8-inch with an SPI panel.
Physical acceptance with this firmware has not been performed. The panel, touch, Wi-Fi and a full LVGL interface were
run on a real board with a plain ESPHome configuration that uses the same `mipi_rgb` display block as the board file
here; the Tessera build itself passes ESPHome's configuration check but no screen has run it yet.

## Install

Update Tessera Screen Manager and choose **Waveshare · 2.8 inch** (ESP32-S3-Touch-LCD-2.8B, marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. The remote package is `packages/waveshare28b.yaml`; the checkout entry is `checkout/waveshare28b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare28b.yaml`.

## Layout and capabilities

- The glass is 57 x 43 mm lying down, so the screen takes the compact look (the CYD's) at 286 dpi: two columns of three
  cells lying down, one column of four standing up. The panel is 480 wide and 640 tall by nature, so standing up is its
  own way round and lying down is a quarter turn (`ROTATION_LANDSCAPE: 90`, as on the CYD).
- The backlight is a plain PWM line on GPIO6 (2 kHz, high for light), so brightness, standby, night mode, Sleep, Wake and
  the alert's flashes are enabled, as on the Guition.
- No camera pictures, snapshots or live tile pictures: on this glass an alert card has no room for a picture, as on the
  Waveshare 3.5.
- GT911 reports pixel coordinates, with no calibration. LVGL turns the touch with the picture.
- `LVGL_BUFFER_SIZE` is 12 % (an eighth of the screen, 77 KB of the memory inside the chip). Read
  `sensor.<screen>_heap_free` after the first boot with a full layout: well over 40 KB free leaves room to try 25 %.

## Where the board file comes from

The pins, the panel's init sequence (Waveshare's demo code) and the touch wiring are those of a community ESPHome
configuration that runs on this board with ESPHome's older `st7701s` platform. The board file moves it onto `mipi_rgb`
with the `CUSTOM` model, so the panel gets that sequence and no other. Three things differ from the old configuration:

- **Data pins and colours.** Measured on a real board: the lines do not have the weights the wiki's names suggest, so the
  board file lists them in the order that gave right colours (below). Only eight of the sixteen data lines had a visible
  effect (GPIO46, 3, 14, 13, 12, 11, 45, 5). Red and blue therefore only switch on or off, green has about sixteen
  steps. Pure colours, black and white are exact; grays get a tint and soft gradients show bands. Expect this in
  Tessera's look too: gray cards and dim text will tint, saturated colours are fine.
- **Panel reset.** The expander's EXIO0 is the panel's reset and is now pulsed at boot (`reset_pin` of the display).
  The old configuration never drove it, and waited 10 seconds before starting Wi-Fi instead.
- **No boot delay.** A board file may not have a boot step of its own (docs/PROFILES.md), so the 10-second wait before
  Wi-Fi is gone. If the picture shows artifacts or flat colours once Wi-Fi starts, that wait is the first suspect.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2.8B) and its schematic.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/).
- I2C: SDA GPIO15, SCL GPIO7, shared by the GT911 and the expander (0x20, PCA9554 registers).
- Expander: EXIO0 panel reset, EXIO1 touch reset, EXIO2 panel chip select. GT911 interrupt: GPIO16.
- Panel setup over three-wire SPI (nine bits per word): CLK GPIO2, MOSI GPIO1, mode 1, 8 MHz.
- RGB: DE GPIO40, PCLK GPIO41, HSYNC GPIO38, VSYNC GPIO39, 16 MHz pixel clock (inverted), 16-bit pixel mode.
  Data lines, lowest bit first as `mipi_rgb` wires them: blue GPIO21, 47, 48, 45, 5; green GPIO9, 10, 14, 13, 12, 11; red GPIO17, 18, 8, 3, 46 (colour order RGB).
- Backlight: GPIO6, PWM at 2 kHz.

## What to report while testing

- Whether the colours match what was drawn (saturated colours exact, grays tinted, as above), the picture is
  sharp and stable, and it survives a cold start (unplug, plug in) as well as a restart.
- Whether touch lands where the finger is in both orientations, in all four corners and on a drag.
- Whether the backlight dims and wakes from a dark standby.
- `sensor.<screen>_heap_free` after the first boot with a full layout.
