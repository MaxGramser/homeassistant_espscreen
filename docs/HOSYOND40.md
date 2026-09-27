# Hosyond 4.0-inch ESP32-32E display, 480 × 320 (experimental)

This is the 4-inch "CYD" sold by Hosyond, and elsewhere as the **4.0inch ESP32-32E Display** (lcdwiki SKU
**E32R40T** with touch): a 320 x 480 panel with an **ST7796S** driver and **XPT2046 resistive touch** on one SPI
bus, on an ESP32 (ESP32-32E module) with 4 MB flash and no PSRAM. It is the same family as the CYD
ESP32-2432S028: the same chip, the same kind of touch, the same calibration on the first start, on bigger glass.

The board is **experimental**: its file was built from the configuration a community member shared for it
(GitHub #42) and from the manufacturer's pin table, and it builds and renders with the others, but the project has
not tried it on a real unit yet. If you have one, [tell others how it went](https://tessera-maxgramser.on-forge.com/community/share?type=installation&board=hosyond40).

## Install

Update ESP Screen Manager and choose **Hosyond · 4 inch** (ESP32-32E E32R40T) in **New screen**. Follow
[Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, then
flash it over USB or download the firmware for ESPHome Web. The screen shows its touch calibration on the first
start: tap the crosshairs ([Calibrating](CALIBRATING.md)).

The remote package is `packages/hosyond40.yaml`; the checkout entry is `checkout/hosyond40.yaml`. Both combine
`packages/core.yaml` with `packages/boards/hosyond40.yaml`.

Take the variant with touch (E32R40T). The E32N40T is the same board without a touch panel.

## Layout and capabilities

- Lying down: 480 x 320, two columns of three cells, like the CYD with bigger tiles. Standing up: 320 x 480, one
  column of four.
- The compact look at 146 dpi (577 diagonal pixels over the 3.95-inch display area), which is the CYD's own
  density, so letters and keys have the CYD's size in millimetres.
- Resistive touch: the calibration wizard runs on the first start and can be started again from the screen's
  settings page or with the **Calibrate touch** button in Home Assistant.
- The backlight is a PWM pin (GPIO27): dimming, standby, night and an alert's flashes work as on the CYD.
- The RGB LED on the board is the **LED** light in Home Assistant.
- No camera pictures and no media artwork, as on the CYD: there is no PSRAM.
- LVGL draws through an 8 % buffer (24 KB) instead of the 12 % other boards take, since everything shares the
  chip's own memory. Read `sensor.<screen>_heap_free` with a full layout; under 40 KB is too little.

## Pins

| Part | Pins |
| --- | --- |
| SPI bus (display and touch) | CLK GPIO14, MOSI GPIO13, MISO GPIO12 |
| Display (ST7796S) | CS GPIO15, DC GPIO2, reset on EN |
| Touch (XPT2046) | CS GPIO33; its interrupt (GPIO36) stays unused, as on the CYD |
| Backlight | GPIO27, lit at a high level |
| RGB LED | red GPIO22, green GPIO16, blue GPIO17, lit at a low level |

GPIO4 is the speaker amplifier's enable on this board, not the red LED as on the 2.8-inch CYD.

## Still to check on a real unit

- The colours (`DISPLAY_INVERT_COLORS`) and the mirroring of the picture.
- Which way the touch axes run. The board takes none of them mirrored, as the shared configuration found them;
  a screen whose taps land mirrored can set `TOUCH_MIRROR_X: "true"` in its own YAML
  ([Hardware-specific YAML overrides](EASY_SETUP.md)).
- The free memory with a full layout, and whether the draw buffer can go back to 12 %.
