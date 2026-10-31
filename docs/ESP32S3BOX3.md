# Espressif ESP32-S3-BOX-3, 2.4 inch, experimental

The **ESP32-S3-BOX-3** from Espressif is a 2.4-inch 320 x 240 board: an ILI9342C panel over SPI, GT911 capacitive touch
over I2C, and an ESP32-S3 with 16 MB flash and 16 MB octal PSRAM. It has the CYD's resolution on smaller glass, with
PSRAM and a backlight that dims.

The board file has been built and its pins checked against ESPHome's own BOX-3 package and Espressif's board support
package, but it has not run on a BOX-3 yet, so the board is **experimental**.

This board file makes the BOX-3 a screen only. Its microphones (ES7210), its speaker (ES8311 and an amplifier), the
mute button and the sensors of its dock are not used yet. A BOX-3 that runs a voice assistant today stops being one when
it is flashed with this firmware. Keep that firmware to flash it back.

## Which BOX-3

Early BOX-3 units have a TT21100 touch controller and an ST7789 panel instead of the GT911 and the ILI9342C. Espressif's
board support package tells the two apart by which chip answers on the I2C bus. This board file is for the GT911 units.
The boot log tells you which one you have: the GT911 answers at 0x5D or 0x14, the TT21100 at 0x24.

## Install

Update Tessera Screen Manager and choose **Espressif · 2.4 inch, ESP32-S3-BOX-3** (marked Experimental) in **New
screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA
keys, then flash it over USB-C or download the firmware for ESPHome Web. There is no touch calibration: the touch panel
reports pixels.

The remote package is `packages/esp32s3box3.yaml` and the checkout entry `checkout/esp32s3box3.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/espressif-esp32-s3-box-3.yaml`.

## Layout and capabilities

- Lying down 320 x 240, two columns of two cells; standing up 240 x 320, one column of four. The compact look at
  167 dpi. The CYD's two by three would leave rows of about 7 mm on this smaller glass, under the 12 mm a tile keeps;
  a screen can still be given that grid in the editor.
- The backlight is a PWM pin (GPIO47) at 1 kHz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The GT911 reports pixels lying down and is read through its interrupt line.
- 128 tiles on up to 24 pages, as on the other ESP32-S3 boards with PSRAM.
- No camera pictures yet. The PSRAM would hold them, but lying down an alert card on 320 x 240 glass has no room for a
  picture, and every board with camera pictures shows one both ways up.
- LVGL draws through a quarter of the screen (`LVGL_BUFFER_SIZE: "25%"`).

## Hardware references

| Part | Pins |
| --- | --- |
| Display bus (SPI) | clock GPIO7, data GPIO6, 40 MHz |
| Display control | chip select GPIO5 and data/command GPIO4, from ESPHome's model; reset GPIO48, active high |
| Touch (GT911, I2C 0x5D or 0x14) | SDA GPIO8, SCL GPIO18, interrupt GPIO3; its reset is the display's |
| Backlight | GPIO47, PWM |

The touch panel's I2C bus also carries the audio codecs (ES8311 and ES7210), which this board file leaves alone. GPIO3
is a strapping pin of the ESP32-S3, wired to the touch panel's interrupt on this board.

- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), model `S3BOX`: the panel's init sequence, its
  size, its mirroring and its chip select and data/command pins.
- [ESPHome's BOX-3 package](https://github.com/esphome/wake-word-voice-assistants/tree/main/esp32-s3-box-3): the
  display, the backlight, the I2C bus and the PSRAM.
- [Espressif's board support package](https://github.com/espressif/esp-bsp/tree/master/bsp/esp-box-3): the touch
  controller and its interrupt pin.

## What to report while testing

1. A successful boot and appearance in Tessera.
2. Correct colours lying down and standing up (red and blue not swapped), and nothing shifted at the edges.
3. Taps near each corner and in the middle, slider drags and edge swipes, both ways up.
4. Dimming from 10 to 100 %, standby going dark and waking on a touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
