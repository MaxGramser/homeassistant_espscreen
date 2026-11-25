# Seeed SenseCAP Indicator D1 series, GX panel, experimental

The **SenseCAP Indicator** from Seeed is a 3.95-inch 480 x 480 touch screen with two chips inside: an ESP32-S3 with
8 MB flash and 8 MB octal PSRAM that drives the display, and an RP2040 beside it. It comes as four models: the **D1**,
the **D1S** with CO2 and air quality sensors, the **D1L** with a LoRa radio, and the **D1Pro** with both. Tessera runs on
the ESP32-S3 and uses the display, the FT6336U capacitive touch and the dimmable backlight.

A community member ran this board file on a D1L with the GX panel (see "Who tried what" below). The project has not
tried it on an Indicator, so the board is **experimental**.

## Which board

- **The four models share one board file.** The display, the touch panel, the PCA9535 expander and the backlight are
  wired the same on all four, as ESPHome's device page for the Indicator and Seeed's own firmware describe them; what
  tells the models apart is on the RP2040 (the sensors) or unused here (the LoRa radio of the D1L and the D1Pro). Only
  the D1L has been tried.
- **The GX panel only.** Seeed fits the Indicator with a GX or a DX panel, and its own firmware asks which one at build
  time. This board file drives the GX panel, through ESPHome's `SEEED-INDICATOR-D1` model. A DX panel is not covered:
  if the screen stays dark or shows wrong colours after a successful flash, it may have the DX panel.

## Install

Update Tessera Screen Manager and choose **SenseCAP · 4 inch, Indicator D1, D1S, D1L, D1Pro (GX)** (marked
Experimental) in **New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi
references and unique API/OTA keys.

The Indicator shows two USB serial devices through its one USB-C port: a CH340 for the ESP32-S3, and the RP2040's own,
which may call itself `INDICATOR RP2040`. Choose the CH340 one for the screen itself. Keep Seeed's
[recovery instructions](https://wiki.seeedstudio.com/SenseCAP_Indicator_How_To_Flash_The_Default_Firmware/) at hand
before you replace the factory firmware.

## The buzzer

The RP2040 drives the buzzer. After the installation New screen offers one more step, **Give the buzzer its sound**:
two clicks put Tessera's firmware on the RP2040 through its own USB port, over the same cable
([BOARD_STEPS.md](BOARD_STEPS.md)). From then on the buzzer is the screen's speaker: it plays the doorbell's chime, the
sounds of alerts chosen under Events and a plugin's sounds, at the **Volume** under Extras
([SECOND_CHIP.md](SECOND_CHIP.md)). The step can be put off; the screen works without it, without sound, and the step
waits in the screen's menu. Seeed's firmware on the RP2040 is replaced by it and goes back the same way. Tessera's
firmware does not read the sensors of a D1S or a D1Pro yet.

In the browser's list the CH340 is called `USB Serial`. When the RP2040's port is chosen in **New screen**, the page
says at once that it is the board's second chip and asks for the port again: it knows the port by its USB ids
(2886:0050). That port takes no bytes at all, so a flasher that waits for its write to end waits for ever on it, which
is why the page gives the chip on any port 20 seconds to answer.

The remote package is `packages/sensecapd1.yaml` and the checkout entry `checkout/sensecapd1.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/seeed-sensecap-indicator-d1.yaml`, which takes the ESP32-S3's
memory settings from `packages/hardware/esp32s3-rgb.yaml`.

## Layout and capabilities

- A square 480 x 480 canvas at 172 dpi, the standard look, two columns of three cells. It turns a quarter as well as a
  half, and the touch turns with the picture.
- The backlight is a PWM pin (GPIO45) at 100 Hz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The FT6336U reports pixels, so there is no touch calibration. Both of its axes run opposite to the display's, which the
  board states once (`TOUCH_MIRROR_X`, `TOUCH_MIRROR_Y`); do not add a second correction in an Override YAML.
- LVGL draws through an eighth of the screen (`LVGL_BUFFER_SIZE: "12%"`), which keeps room inside the chip.
- Pictures: camera tiles, an alert's snapshot and media artwork, and with them the sounds the screen downloads.
- The user button on the side (GPIO38, low while pressed) is the standby key: a press puts the screen in standby or
  wakes it (`features/standby-key.yaml`, firmware 0.64.0+).
- Not configured: the LoRa radio, and on the RP2040 the sensors, the Grove ports and the microSD slot. The Indicator
  has no battery.

## Who tried what

[@sillevl](https://github.com/sillevl) ran this board file on a D1L with the GX panel (SKU 114993070) and checked the
colours, taps in the corners and the middle, sliders, page buttons and edge swipes, the settings and detail cards,
rotation, brightness, standby and the wake by touch, a cold start, settings that stay after a restart, Wi-Fi, the
encrypted API, layouts from Tessera and normal use over time (#277). An update over Wi-Fi and a layout at the screen's
largest have not been tried, and neither has any other model or the DX panel.

## Hardware references

| Part | Pins or address |
| --- | --- |
| I2C bus | SDA GPIO39, SCL GPIO40, 100 kHz |
| PCA9535 expander | 0x20, ESPHome's `pca9554` with `pin_count: 16` |
| Panel setup (SPI) | clock GPIO41, data GPIO48 |
| Panel chip select and reset | expander lines 4 and 5 |
| FT6336U touch | ESPHome's `ft5x06`, 0x48, polled every 20 ms (its interrupt is expander line 6) |
| Touch reset | expander line 7, held high |
| Backlight | GPIO45, PWM, active high |
| LoRa chip select | expander line 0, held high so a radio stays off the bus |
| RP2040 reset | expander line 8, held high |
| Serial line to the RP2040 | GPIO19 out, GPIO20 in, 921600 baud |

- [ESPHome's device page for the Indicator](https://devices.esphome.io/devices/seeed-sensecap/), with the four models.
- [Seeed's product sheet for the D1L](https://files.seeedstudio.com/Bazaar/product_pdf/114993070.pdf).
- [Seeed's ESP32 firmware](https://github.com/Seeed-Solution/SenseCAP_Indicator_ESP32), whose board options list the
  D1 and D1S, the D1L and D1Pro, and the GX and DX panels.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/), model `SEEED-INDICATOR-D1`: the panel's init
  sequence, its RGB pins and its porches; the pixel clock is 16 MHz.

## What to report while testing

1. Which model it is (D1, D1S, D1L or D1Pro), a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts.
3. Taps near each corner and in the middle, slider drags and edge swipes, and the quarter-turn setting.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
