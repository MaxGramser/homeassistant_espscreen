# CYD 3.5 inch, Sunton ESP32-3248S035R and 035C, 480 × 320 (experimental)

The 3.5-inch "Cheap Yellow Display" by Sunton: a 320 x 480 panel with an **ST7796** driver over SPI, on an ESP32
(ESP32-D0WD-V3) with 4 MB flash and no PSRAM. It comes two ways, and **New screen** has both:

| Board | Touch | In New screen |
| --- | --- | --- |
| ESP32-3248S035**R** | XPT2046 resistive, on the display's SPI bus | CYD · ESP32-3248S035R (`cyd35r`) |
| ESP32-3248S035**C** | GT911 capacitive, over I2C | CYD · ESP32-3248S035C (`cyd35c`) |

The R is the same family as the 2.8-inch CYD (ESP32-2432S028) and the Hosyond 4-inch: the same chip, the same kind
of touch and the same calibration on the first start, on bigger glass. Both boards are **experimental**: their files
come from configurations community members ran on their own boards in ESPHome with LVGL, and they build and render
with the others, but the project has not tried Tessera on a real unit yet. If you have one,
[tell others how it went](https://tessera-maxgramser.on-forge.com/community/share?type=installation&board=cyd35r).

## Install

Update Tessera Screen Manager and choose the board with your touch in **New screen** (the letter at the end of the
model printed on the back, R or C). Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi
references and unique API/OTA keys, then flash it over USB or download the firmware for ESPHome Web. The R shows its
touch calibration on the first start: tap the crosshairs ([Calibrating](CALIBRATING.md)). The C needs none.

The remote packages are `packages/cyd35r.yaml` and `packages/cyd35c.yaml`; the checkout entries are
`checkout/cyd35r.yaml` and `checkout/cyd35c.yaml`. Each combines `packages/core.yaml` with its board file, and both
board files include `packages/hardware/sunton-3248s035.yaml`, the part the two share.

## Layout and capabilities

- Lying down: 480 x 320, two columns of three cells. Standing up: 320 x 480, one column of four.
- The compact look at 165 dpi (577 diagonal pixels over 3.5 inches), with the fonts of the 2.8-inch CYD
  (`FONT_DPI: "143"`): at the glass's own density they did not fit the update slot of a board with 4 MB of flash.
  Letters are so a little smaller in millimetres than on the 2.8-inch CYD; tiles, keys and gaps keep the glass's size.
- The backlight is a PWM pin (GPIO27): dimming, standby, night and an alert's flashes work as on the CYD.
- The RGB LED on the back is the **LED** light in Home Assistant.
- No camera pictures and no media artwork, as on the CYD: there is no PSRAM.
- LVGL draws through an 8 % buffer (24 KB), as on the Hosyond 4-inch. Read `sensor.<screen>_heap_free` with a full
  layout; under 40 KB is too little.
- The display's SPI clock is 80 MHz, as the shared configuration ran it. A screen that shows noise or stripes can set
  `DISPLAY_DATA_RATE: "40MHz"` in its own YAML ([Hardware-specific YAML overrides](EASY_SETUP.md)).

## Pins

| Part | Pins |
| --- | --- |
| SPI bus | CLK GPIO14, MOSI GPIO13, MISO GPIO12 |
| Display (ST7796) | CS GPIO15, DC GPIO2 |
| Touch, 035R (XPT2046) | on the SPI bus, CS GPIO33; its interrupt (GPIO36) stays unused, as on the CYD |
| Touch, 035C (GT911) | I2C SDA GPIO33, SCL GPIO32, reset GPIO25 |
| Backlight | GPIO27, lit at a high level |
| RGB LED | red GPIO4, green GPIO17, blue GPIO16, lit at a low level |
| Light sensor | GPIO34 (not used yet) |

## Tried on a real unit

An ESP32-3248S035R ran this board's firmware: it starts, joins Wi-Fi, shows the picture the right way and in the right
colours, and after the calibration wizard a tap lands where the finger is.

## Still to check on a real unit

- On the R: whether the touch threshold of the 2.8-inch CYD suits this film over a longer use.
- On the C: the picture and the rotation, which it shares with the R but no one has tried on its glass.
- On the C: the touch pins and axes, from one community member's working configuration only. A screen whose taps land
  mirrored can set `TOUCH_MIRROR_X` or `TOUCH_MIRROR_Y` to `"true"` in its own YAML.
- Which LED pin is green and which is blue.
- The free memory with a full layout, and whether the draw buffer can go to 12 %.
