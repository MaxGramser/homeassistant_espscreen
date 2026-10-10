# Waveshare ESP32-S3-Touch-LCD-4, experimental

This is the **ESP32-S3-Touch-LCD-4**, the board *without* the "B": a 4-inch 480 x 480 IPS panel, GT911 capacitive
touch, an ESP32-S3 with 16 MB flash and 8 MB of octal PSRAM, and a CH32V003 I/O expander. The
[4B](WAVESHARE4B.md) carries a TCA9554 expander and other pins, so the two board files are not interchangeable.

A screen built from this profile has started, drawn the Tessera interface and joined a Wi-Fi network. The rest of the
hardware acceptance (touch across the whole glass, brightness, standby and wake, and a long run without a restart) is
still open, so the board ships as **experimental**.

## Install

Update Tessera Screen Manager and choose **Waveshare · 4 inch** (ESP32-S3-Touch-LCD-4, marked Experimental) in
**New screen**. Take care not to pick the 4B by mistake: the two sit next to each other in the list and differ by one
letter. Follow [Easy setup](EASY_SETUP.md) for the rest: the screen gets its own name, Wi-Fi references and unique
API/OTA keys. Keep an existing working profile if the board is already installed.

The remote package is `packages/wavesharelcd4.yaml`; the checkout entry is `checkout/wavesharelcd4.yaml`. Both
combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-lcd-4.yaml`.

This board needs ESPHome 2026.7.0 or later, which is where the `waveshare_io_ch32v003` component and the
`WAVESHARE-4-480X480` display model arrived.

## Layout and capabilities

- The glass has the size and resolution of the 4-inch Guition and the 4B, so the screen looks the same: two columns
  of three cells, the standard look at 170 dpi, the same tiles in millimetres. The glass is square, so it turns a
  quarter as well as a half.
- The backlight is the CH32V003's own hardware PWM, so brightness is a percentage and standby, night mode, Sleep,
  Wake and the alert's flashes all work. The output is inverted and `zero_means_zero`, so 0 stays dark.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation.
- GT911 reports pixel coordinates, so there is no touch calibration on the first start. The shared touch filter and
  action guard stay in use.
- Touch needs this board's own startup sequence. Waveshare's factory firmware drives the expander's touch
  address-select, supply and reset lines low, waits 200 ms, raises the supply and the reset while address-select
  stays low, and waits another 200 ms before it talks to the controller. Without it the GT911 answers at its
  secondary address and reports no usable size, so touch stays dead while the rest of the screen looks healthy.
  `components/gt911_wavesharelcd4` is a copy of ESPHome's `gt911` that performs that sequence, checks the size the
  controller reports and repeats the power cycle up to three times. It carries a name of its own so that only this
  board loads it: every other GT911 board keeps the platform ESPHome ships.
- The battery charger, the audio chips, the microphone, the speaker connector and the clock chip on the board stay
  unused. The screen runs from USB; a battery on the connector is neither read nor managed.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-4) and its schematic.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/) with the `WAVESHARE-4-480X480` model, which
  carries this board's RGB pins and panel timings. The model belongs to this board and does not fit the 4B.
- I2C: SDA GPIO15, SCL GPIO7 at 400 kHz, shared by the GT911 and the CH32V003 expander (0x24).
- The panel takes its setup over SPI: clock GPIO2, data GPIO1.
- Expander lines: EXIO1 touch reset, EXIO2 touch interrupt, EXIO3 panel reset, EXIO5 the LCD supply, EXIO6 the buzzer.
- The LCD supply is a `power_supply` the backlight output switches on, and the display starts after it at setup
  priority -100. An earlier attempt that drove EXIO1, 2, 3 and 5 from a boot step instead left the panel black with
  no backlight and the buzzer sounding, so that route is not used.
- The buzzer line is held low by an unused output, which keeps the board silent.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts. Coloured bars, a shifted picture
   or inverted colours point at the display block.
3. Physical taps near each corner and in the middle, slider drags and edge swipes, and the quarter-turn setting.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
