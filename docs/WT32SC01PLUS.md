# Wireless-Tag WT32-SC01 Plus, 3.5 inch, 480 × 320 (experimental)

A 3.5-inch development board from Wireless-Tag (**WT32-SC01 Plus**): a 480 × 320 LCD panel with an **ST7796UI** driver over an 8-line octal SPI bus, **capacitive touch** via an **FT6336U** over I2C, on an ESP32-S3 with 16 MB flash and 8 MB octal PSRAM.

The board is **experimental**. Tested and verified on real hardware running ESPHome and Tessera.

## Install

Update Tessera Screen Manager and choose **Wireless-Tag · WT32-SC01 Plus** in **New screen**. Follow
[Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, then
flash it over USB or download the firmware for ESPHome Web. There is no touch calibration: the touch panel reports
pixels.

The remote package is `packages/wt32sc01plus.yaml`; the checkout entry is `checkout/wt32sc01plus.yaml`. Both combine
`packages/core.yaml` with `packages/boards/wt32sc01plus.yaml`.

A screen you set up by hand from the shared packages needs the board's `BOARD_ID` and a `DEVICE_NAME` equal to its
`esphome: name:`: Tessera knows a screen by the two, and a screen without them can be seen but never takes tiles.
Building from `packages/wt32sc01plus.yaml` sets both.

## Layout and capabilities

- Lying down: 480 × 320, two by two cells. Standing up: 320 × 480, one column of three.
- The standard look at 165 dpi (577 diagonal pixels over 3.5 inches).
- Capacitive touch (FT6336U), polled every 20 ms.
- The backlight is a PWM pin (GPIO45) at 150 Hz: dimming, standby, night and alert flashes work.
- Camera pictures, live camera tiles and media artwork, from the 8 MB PSRAM.
- LVGL draws through a 25 % buffer.

## Pins

| Part | Pins |
| --- | --- |
| Octal SPI bus (display) | CLK GPIO39, CS GPIO42, D0–D7: GPIO41, GPIO40, GPIO38, GPIO47, GPIO48, GPIO46, GPIO2, GPIO1 |
| I2C bus (touch, 0x38) | SDA GPIO6, SCL GPIO5, Reset GPIO7 |
| Backlight | GPIO45 |

## Tried on a real unit

- Flashed over OTA and USB on ESPHome 2026.9.0 / Tessera 0.55.0.
- Touch coordinates, colors, dimming, and standby verified on physical hardware.
