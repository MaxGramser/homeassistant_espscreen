# Elecrow CrowPanel Advanced 10.1 inch, ESP32-P4, experimental

This is the **Elecrow CrowPanel Advanced 10.1-inch ESP32-P4 HMI display** (SKU DHE04310D): a 10.1-inch 1024 x 600 IPS
panel with an EK79007 MIPI-DSI driver, GT911 capacitive touch, an ESP32-P4 with 16 MB flash and 32 MB PSRAM, an
ESP32-C6 beside it for Wi-Fi, a loudspeaker and a PDM microphone.

A community member ran this configuration on a V1.2 board: pages, tiles, swiping between pages, dimming and waking by
touch work. The speaker, the microphone, standby, night mode, camera pictures and a long run with a full layout have not
been checked yet (see "What to report while testing" below).

## Which board

- **Hardware revision V1.1 or V1.2.** From V1.1 on, Elecrow runs the Wi-Fi link's data lines the other way round
  (D0 on GPIO17 to D3 on GPIO14), and this board file follows that. A V1.0 board has them on GPIO14 to GPIO17 and does
  not get Wi-Fi with this file. The revision is printed on the back of the board.
- **An ESP32-P4 before silicon revision 3.** The firmware is built for the earlier silicon (`engineering_sample: true`,
  360 MHz), as Elecrow's own example is. A board with rev3 silicon does not boot it, and a successful flash over USB
  does not mean otherwise. The chip revision is in the first lines of the USB log ("chip revision: v1.3").

## Install

Update Tessera Screen Manager and choose **CrowPanel · 10.1 inch, Advanced 10.1 ESP32-P4** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it
is on your Wi-Fi; then add its tiles.

The remote package is `packages/crowpanel101.yaml` and the checkout entry `checkout/crowpanel101.yaml`. Each combines
`packages/core.yaml` with the board file `packages/boards/crowpanel101.yaml`. The ESP32-P4, its memory and its ESP32-C6
come from `packages/hardware/esp32p4-c6.yaml`, with this board's own pins in the board file.

## Layout and capabilities

- 1024 x 600 at 117 dpi, the standard look. A screen starts with five columns of five lying down, as on the 10.1-inch
  Guition, and four columns of six standing up; the editor's Grid button gives it another.
- The panel is 1024 x 600 itself, so it lies down without a turn.
- The backlight is a PWM pin (GPIO31), with the panel's power on GPIO29 kept on: brightness is a percentage, and
  standby, night mode, Sleep, Wake and the alert's flashes are enabled.
- The loudspeaker and the microphone are the screen's audio: a media player in Home Assistant for announcements and
  music, Volume and Microphone under Screen settings, and what audio plugins (a voice assistant) need. The amplifier has
  no volume register, so the volume is turned down in software.
- Camera tiles, full-screen snapshots and the live camera of the P4 boards, camera alerts and media artwork use the
  shared PSRAM implementation. The board has no camera of its own.
- The GT911 reports pixel coordinates, with no calibration.

## Hardware references

- [Elecrow's wiki for this board](https://www.elecrow.com/wiki/CrowPanel_Advanced_10.1inch_ESP32-P4_HMI_AI_Display_1024x600_IPS.html)
  and Elecrow's ESPHome example for the CrowPanel Advanced P4 boards, which this board file follows.
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/): the panel uses ESPHome's own
  `model: WAVESHARE-ESP32-P4-WIFI6-TOUCH-LCD-7B`, the EK79007 at 1024 x 600, with the reset on GPIO41.
- The pins:
  - Wi-Fi: ESP32-C6 over four-bit SDIO, reset GPIO32, CMD GPIO19, CLK GPIO18, D0 to D3 on GPIO17 to GPIO14.
  - The chip's internal regulators on channels 3 and 4, both at 2.5 V.
  - I2C: SDA GPIO45, SCL GPIO46, 400 kHz, for the GT911 (reset GPIO40, interrupt GPIO42).
  - Backlight: GPIO31, PWM; panel power GPIO29.
  - Speaker: I2S LRCLK GPIO21, BCLK GPIO22, data GPIO23, amplifier enable GPIO30 (low is on).
  - Microphone: PDM, clock GPIO24, data GPIO26.
- The LoRa socket, the SD card, the UARTs and the external I2C port are not configured.

## What to report while testing

1. The board's hardware revision, the chip revision from the first lines of the USB log, a successful boot and
   appearance in Tessera.
2. Correct colours and a stable picture across several page changes, a restart from the screen's settings, an update
   over the air and a cold start.
3. Physical taps near each corner, slider drags and edge swipes. Touch that lands mirrored or swapped points at the touch
   transform (`TOUCH_SWAP_XY`, `TOUCH_MIRROR_X`, `TOUCH_MIRROR_Y`).
4. The picture standing up as well, built that way from New screen.
5. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode.
6. A text-to-speech announcement and music on the screen's media player, the Volume setting from low to high, and
   whether the speaker stays quiet between sounds.
7. The microphone, with a voice assistant plugin: whether the wake word is heard from across the room.
8. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
9. `sensor.<screen>_heap_free` with a full layout, any reset, Wi-Fi drop or I2C error, and how long the screen stayed
   running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
