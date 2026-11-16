# LCDWiki ES3C28P, 2.8 inch, experimental

The **LCDWiki ES3C28P** (sold by QDtech/LCDWiki as "2.8inch ESP32-S3 Display") is a 240 x 320 IPS panel with an
ILI9341V controller over 4-wire SPI, FT6336G capacitive touch over I2C, and an ESP32-S3 with 16 MB flash and 8 MB octal
PSRAM. Tessera runs it lying down at 320 x 240, a quarter turn of the panel, with the compact look and the CYD's grid.

It has the CYD's glass and resolution, but it is not the CYD (ESP32-2432S028): that board has an ESP32 without PSRAM,
resistive touch and other pins, and the CYD's board file does not run on it. The ES3N28P is the same board without touch;
this board file is not for it.

The board file was written and run by an owner (see "Who tried what" below). The project has not tried it on one, so the
board is **experimental**.

## Install

Update Tessera Screen Manager and choose **LCDWiki · 2.8 inch, ES3C28P** (marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, and
flash it over the board's USB-C port.

The remote package is `packages/es3c28p.yaml` and the checkout entry `checkout/es3c28p.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/es3c28p.yaml`.

## Layout and capabilities

- Lying down 320 x 240, two columns of three cells; standing up 240 x 320, one column of four. The compact look at
  143 dpi.
- With PSRAM it takes 128 tiles on 24 pages, as the other ESP32-S3 boards with PSRAM.
- The backlight is a PWM pin (GPIO45) at 1 kHz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled. `zero_means_zero` keeps a dark standby dark.
- The FT6336G reports pixels, so there is no touch calibration. Its interrupt (GPIO17) and reset (GPIO18) are wired as on
  the Freenove FNK0104S, and both boards take the panel from `hardware/parts/ft63x6.yaml`.
- The panel needs inverted colours (without them every colour is its complement); the board file sets them. RGB order
  is right as it is.
- The USB-C port is the chip's own USB-Serial-JTAG, so the log goes there (`logger: hardware_uart: USB_SERIAL_JTAG`).
- No camera package yet: camera tiles, snapshots and media artwork are not included. The board has the PSRAM for them,
  but nobody has tried them on it.

GPIO45 and GPIO46 are strapping pins of the ESP32-S3. On this board they are wired to the backlight and to the panel's
data/command line, so the board file tells ESPHome not to warn about them. The LCD's reset is tied to the chip's reset,
so the display has no `reset_pin`.

## Pins

| Part | Pins |
|---|---|
| SPI (display) | CLK GPIO12, MOSI GPIO11, MISO GPIO13, CS GPIO10, DC GPIO46 |
| I2C (touch, `touch_bus`, FT6336G at 0x38) | SDA GPIO16, SCL GPIO15, INT GPIO17, RST GPIO18 |
| Backlight | GPIO45 (PWM, high is lit) |

From LCDWiki's pin table, confirmed by an owner's ESPHome configuration that runs on the board.

## Known quirks

- After flashing over USB the board wants one power cycle (pull the cable), or LVGL can hang half drawn.

## Who tried what

[@StefanHAJ](https://github.com/StefanHAJ) ran this board file on two ES3C28P boards with Tessera (firmware 0.59.0 and
0.60.0, built from his fork with ESPHome 2026.10): the screen joined Home Assistant, showed its pages lying down with the
right colours, and touch, the backlight and page switching worked. Not tried yet: standing up, camera pictures and a long
run.
