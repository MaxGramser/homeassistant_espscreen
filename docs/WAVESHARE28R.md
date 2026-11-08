# Waveshare ESP32-S3-LCD-Driver-Board with the 2.8-inch round LCD, experimental

This is Waveshare's **ESP32-S3-LCD-Driver-Board** (ESP32-S3-WROOM-1-N8R8: 8 MB flash, 8 MB octal PSRAM) driving the
**2.8-inch round** 480 × 480 IPS panel, an ST7701S over RGB with GT911 capacitive touch. Waveshare sold the two as a kit,
together with 2.1-inch round and 4-inch square RGB panels for the same board; the kit is no longer listed. The board
alone is still sold, and its current examples cover only small SPI panels. It is neither the ESP32-S3-Touch-LCD-2.8B
(480 × 640) nor the 240 × 320 Waveshare 2.8-inch with an SPI panel. Only the 2.8-inch round panel has been tried.

## Install

Choose **Waveshare · ESP32-S3-LCD-Driver-Board (2.8inch round)** (marked Experimental) in **New screen** and follow
[Easy setup](EASY_SETUP.md). The remote package is `packages/waveshare28r.yaml`; the checkout entry is
`checkout/waveshare28r.yaml`. Both combine `packages/core.yaml` with `packages/boards/waveshare28r.yaml`.

## Round glass

The firmware lays out a square, and the circle cuts its corners. The board file insets the grid, and the top bar with
it, to the largest square inside the circle: `GRID_MARGIN` 70 px a side (480 / √2 = 339 px), two by two cells of about
24 mm. What stays outside the circle:

- the page bar's chevrons, at the grid margin along the bottom edge. The page dots sit inside the circle and open the
  page switcher, and the edge swipe (Swipe between pages, on by default for a new screen) changes pages from the left
  and right edges at mid-height, where the circle reaches the edge;
- the parts the firmware measures from the whole canvas: cards, the settings page and the alert card reach the corners.

The 2.8 inches are the circle's diameter, which is the panel's 480 px width, so the density is 480 / 2.8 = 171.4 dpi,
the standard look's own size. The catalog works a board's size out from the square's diagonal and so lists this one
as 4.0 inches; the model name says 2.8-inch round.

## Hardware

- **Display:** the `st7701s` platform with Waveshare's pins, porches and init sequence (the 2.8inch_RGB_LCD demo:
  ESP-IDF `main.c` and Arduino `ESP_Panel_Board_Custom.h` agree), 16 MHz pixel clock, `color_order: bgr`. Colour ramps
  (grey, red, green, blue) are smooth on the glass with this pin order.
- **Not `mipi_rgb`:** with no `reset_pin`, ESPHome 2026.10's `mipi_rgb` puts a software reset (0x01, 10 ms) in front of
  the init sequence. On this panel that gave blue and green vertical streaks, which stayed through a flash of known
  good firmware until the panel was left unpowered. The same `mipi_rgb` block drew correctly on ESPHome 2026.7.4.
- **Touch:** GT911 on I2C (SDA 15, SCL 7), interrupt GPIO16, reset on the TCA9554 (P0, schematic EXIO1).
- **Expander:** TCA9554 at 0x20 (PCA9554 registers). Schematic EXIOn is `number: n-1`: P0 touch reset, P1 backlight
  enable, P2 LCD reset (held released by an output).
- **Backlight:** always on. Sweeping GPIO6's PWM over its whole range and holding the backlight enable (P1) low both
  left it fully lit, so the board includes `features/backlight-always-on.yaml`: no standby, no night, no alert blinks,
  and `BACKLIGHT_DIMMABLE` false.
- **Memory:** `LVGL_BUFFER_SIZE` 25 %. With three pages the screen ran with about 73 KB of internal RAM free at its
  lowest.

## Tried on the glass

On one board (November 2026, firmware 0.60.0): the picture and its colours, Wi-Fi, the ESPHome API, pages sent from
Tessera, the edge swipe, the page switcher. Not yet tried: touch accuracy near the circle's edge, the screen turned
a quarter (Grid standing up), cards, alerts and the settings page on the round glass, a long run.
