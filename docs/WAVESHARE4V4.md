# Waveshare ESP32-S3-Touch-LCD-4 V4.0, experimental

This is revision 4.0 of the **Waveshare ESP32-S3-Touch-LCD-4**, the 4-inch board without the "B": a 480 x 480 IPS
panel with an ST7701S driver over RGB, GT911 capacitive touch, an ESP32-S3 with 16 MB flash and 8 MB octal PSRAM, and
Waveshare's own CH32V003 as its IO expander.

Community members have run this board file on revision 4.0 boards (see "Who tried what" below). The project has not
tried it on one, so the board is **experimental**.

## Which board

- **Revision 4.0 only.** Waveshare prints the revision on the board, under the screen. Revision 4.0 has the CH32V003
  expander at address 0x24 on the touch bus (GPIO15 and GPIO7). Earlier revisions of the same name have a TCA9554
  expander, which this board file does not drive.
- **Not the 4B.** The [ESP32-S3-Touch-LCD-4B](WAVESHARE4B.md) has a TCA9554 at 0x20, other I2C pins and a panel set up
  over lines of its expander. The two sit next to each other in New screen and differ by one letter.

## Install

Update Tessera Screen Manager and choose **Waveshare · 4 inch, ESP32-S3-Touch-LCD-4 V4.0** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Keep an existing working profile if the board is already installed.

The board has one USB-C port, the chip's own USB (a computer sees it as an Espressif device, 303a:1001). It powers the
board, flashes it and carries the log.

The remote package is `packages/waveshare4v4.yaml` and the checkout entry `checkout/waveshare4v4.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/waveshare-esp32s3-4v4.yaml`. The board needs ESPHome 2026.7.0
or newer, where ESPHome's `waveshare_io_ch32v003` expander arrived.

## Layout and capabilities

- The glass has the size and resolution of the 4-inch Guition and the 4B, so the screen looks the same: two columns of
  three cells, the standard look at 170 dpi. The glass is square, so it turns a quarter as well as a half.
- The backlight is the CH32V003's PWM output (inverted), so brightness is a percentage, and standby, night mode, Sleep,
  Wake and the alert's flashes are enabled. A level of 0 stays dark.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation.
- The GT911 reports pixel coordinates, so there is no touch calibration on the first start. Its lines are on the
  expander, so it is polled every 20 ms.
- The buzzer is held silent. The board's clock chip, its microSD slot and its other connectors are not configured.

## How the board starts

Two things only showed up on real boards, and the board file handles both with ESPHome's own components:

- **The touch needs its interrupt line driven.** The GT911 takes its I2C address from that line at its reset. The
  expander comes up with every line high, and a reset taken then leaves the chip at the wrong address or not answering
  at all ("Calibration error" in the log). The board file drives the interrupt line low as an output, and the reset on
  EXIO1 puts the chip on 0x5D.
- **A cold start needs the panel and the touch held in reset while the power comes up**, as Waveshare's own bring-up
  does. Without it the backlight lights a black screen, or the touch stays dead until the next reset, and not on every
  start. Two internal switches hold EXIO1 and EXIO3 low from the moment the expander is up; the display lets its reset
  go later through `enable_pin`, which waits 10 ms before the first command, and the touch comes up last.

## Who tried what

- [Simismin](https://tessera-maxgramser.on-forge.com/wishlist/117) wrote this board file and ran it on a revision 4.0
  board: display and touch on every cold start from unplugged USB, after the reset button, and after two resets in a
  row while the screen was still starting, with no errors in the serial log.
- [@PedanticAvenger](https://github.com/PedanticAvenger) brought it to a pull request (#275), built it with the ESPHome
  command line and ran it on a board: it joined Home Assistant, took several pages of tiles, turned with the Rotation
  setting, and the touch landed where it should.
- [@leonardospina](https://github.com/leonardospina) ran the same board with a board file of their own (#213), which
  found the same start-up needs.

Not tried by anyone yet: the brightness setting across its range, standby and the wake by touch, camera pictures, a
full page of tiles over a long run, and an update over Wi-Fi.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-4) and the revision 4.0 schematic.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/), model `WAVESHARE-4-480X480`: the panel's init
  sequence, its RGB pins, its 12 MHz pixel clock and its three-wire SPI setup.
- I2C: SDA GPIO15, SCL GPIO7 at 400 kHz, shared by the GT911, the CH32V003 (0x24) and the clock chip.
- The panel's setup over SPI: clock GPIO2, data GPIO1.
- Expander lines: EXIO1 touch reset, EXIO2 touch interrupt, EXIO3 panel reset, EXIO4 microSD chip select, EXIO5 the
  supply of the panel and the touch, EXIO6 the buzzer's enable, EXIO7 the clock chip's interrupt, and its PWM output
  the backlight.

## What to report while testing

1. The revision printed on the board, a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts.
3. Taps near each corner and in the middle, slider drags and edge swipes, and the quarter-turn setting.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode.
5. Camera tile pictures, full-screen camera images and camera alerts.
6. `sensor.<screen>_heap_free` with a full layout, any reset or I2C error, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
