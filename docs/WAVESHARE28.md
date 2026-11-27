# Waveshare ESP32-S3-Touch-LCD-2.8 (V1), 2.8 inch, experimental

The **ESP32-S3-Touch-LCD-2.8** from Waveshare is a 2.8-inch 240 x 320 board: an ST7789 panel over SPI, CST328
capacitive touch over I2C, and an ESP32-S3R8 with 16 MB flash and 8 MB octal PSRAM. This file is for the **V1** board.
Waveshare ships a V2 since June 2026 with a CST3530 touch controller instead, which this board file does not drive. The
label on the back of the board says which version it is.

The display settings come from an ESPHome configuration that runs on a V1 board, the pins from Waveshare's own V1 demo.
This board file has run on one V1 board, lying down: the picture, and taps in all four corners and the middle and a
swipe from the edge, landed where they should. Standing up, dimming, standby and a full layout over a long run have
not been tried yet, so the board is **experimental**.

## Install

Update Tessera Screen Manager and choose **Waveshare · 2.8 inch, ESP32-S3-Touch-LCD-2.8** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys, then flash it over USB or download the firmware for ESPHome Web. There is no touch calibration: the touch
panel reports pixels.

The board builds with ESPHome 2026.9.0 or newer, the first with the `cst328` touch platform.

The remote package is `packages/waveshare28.yaml` and the checkout entry `checkout/waveshare28.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/waveshare28.yaml`.

## Layout and capabilities

- Lying down 320 x 240, two columns of three cells; standing up 240 x 320, one column of four. The compact look at
  143 dpi, the size and resolution of the CYD.
- The panel is driven through ESPHome's `mipi_spi` model `S3BOX`, with its colours inverted and in RGB order, at 8 MHz.
  It scans 320 x 240; the board file swaps its axes onto a 240 x 320 canvas standing up and turns that a quarter
  (`ROTATION_LANDSCAPE: "90"`) to lie down, as on the CYD with an ILI9342. Waveshare's demo drives it at 80 MHz with a
  reset line on GPIO39; neither has been tried with this model yet, so a full redraw is slow.
- The backlight is a PWM pin (GPIO5) at 1220 Hz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The CST328 reports pixels in the canvas's axes, each the other way round (`TOUCH_MIRROR_X` and `TOUCH_MIRROR_Y`),
  and is read through its interrupt line. It cannot swap its axes: ESPHome's `cst328` driver replaces a `calibration`
  with the resolution the chip reports, in the chip's own axes, so a swapped touch lands at three quarters of the
  height. That is why the canvas stands up.
- No camera pictures: lying down, the alert card on 320 x 240 has no room for one. Full-screen snapshots use the PSRAM.
- No standby key. The BOOT key (GPIO0) and the PWR key (GPIO6) are left alone.
- Not used yet: the battery (ADC on GPIO8, divider 3.0) and the power hold line (GPIO7) that keeps the board on when it
  runs on its battery, the speaker (PCM5101 on I2S), the QMI8658 motion sensor, the PCF85063 clock and the SD card. On
  its battery alone the board may switch off, since nothing holds GPIO7 high.

## Hardware references

| Part | Pins |
| --- | --- |
| Display bus (SPI) | clock GPIO40, MOSI GPIO45 (MISO GPIO46, unused) |
| Display control | data/command GPIO41, chip select GPIO42 (reset GPIO39, unused) |
| Touch (CST328, I2C 0x1A) | SDA GPIO1, SCL GPIO3, interrupt GPIO4, reset GPIO2 |
| Backlight | GPIO5, PWM |
| Second I2C bus (QMI8658, PCF85063 at 0x51) | SDA GPIO11, SCL GPIO10, unused |
| Speaker (PCM5101, I2S) | bit clock GPIO48, word select GPIO38, data GPIO47, unused |
| Battery | ADC GPIO8, divider 3.0; power hold GPIO7; PWR key GPIO6, unused |

GPIO3 and GPIO45 are strapping pins of the ESP32-S3, wired to the touch panel and the display on this board.

- [Waveshare's wiki for the board](https://docs.waveshare.com/ESP32-S3-Touch-LCD-2.8), with the V1 and V2 demos.
- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), model `S3BOX`.

## What to report while testing

1. A successful boot and appearance in Tessera.
2. Correct colours lying down and standing up.
3. Taps near each corner, slider drags and edge swipes, both ways up.
4. Dimming, standby and waking by a touch.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
