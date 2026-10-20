# Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, experimental

This is the **ESP32-P4-WIFI6-Touch-LCD-7B**: a 7-inch 1024 x 600 IPS panel with an EK79007 MIPI-DSI driver, GT911
capacitive touch, an ESP32-P4 with 32 MB flash and 32 MB PSRAM, and an ESP32-C6 beside it for Wi-Fi. It is not the
ESP32-S3-Touch-LCD-7B ([its own page](WAVESHARE7B.md)): that one is an RGB panel behind a CH32V003 expander, while this
board drives its panel over MIPI-DSI and has no expander.

A community member ran this board file on a board with rev3 silicon (see "Who tried what" below). The project has not
tried it on one, so the board is **experimental**.

## Which silicon

Waveshare sells this board with two revisions of the ESP32-P4 under one name, and firmware for one does not start on the
other. This board file builds for **rev3 silicon** ("chip revision: v3.x" in the first lines of the USB log,
`engineering_sample: false`), which is what Waveshare ships now. A board with earlier silicon ("chip revision: v1.3")
needs this in its screen's Override YAML:

```yaml
esp32:
  engineering_sample: true
```

Nobody has tried this board file on earlier silicon yet; please report how it goes.

## Install

Update Tessera Screen Manager and choose **Waveshare · 7 inch, ESP32-P4-WIFI6-Touch-LCD-7B** (marked Experimental, the
one with the ESP32-P4) in **New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name,
Wi-Fi references and unique API/OTA keys. Keep an existing working profile if the board is already installed.

The board has two USB-C ports. The one the firmware flashes and logs over is the chip's own USB ("USB OTG", a `usbmodem`
device); its other port, "USB TO UART", is behind a bridge chip. A screen flashed over that one wants
`hardware_uart: UART0` under `logger:` in its Override YAML.

The remote package is `packages/wavesharep47b.yaml` and the checkout entry `checkout/wavesharep47b.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/wavesharep47b.yaml`. The board needs ESPHome 2026.9.0 or
newer: its display platform is the repository's copy of that version's driver.

## Layout and capabilities

- 1024 x 600 at 170 dpi, the standard look, four columns of four cells lying down and two columns of seven standing up.
  The panel is 1024 x 600 itself, so it lies down without a turn. If the picture is upside down for the way the board
  hangs, the Rotation setting (180°) turns the picture and the touch together.
- The backlight is a PWM pin (GPIO32, inverted) at 1 kHz: brightness is a percentage, and standby, night mode, Sleep,
  Wake and the alert's flashes are enabled.
- The GT911 reports pixel coordinates, with no calibration. Its axes are mirrored against the glass (`TOUCH_MIRROR_X`
  and `TOUCH_MIRROR_Y`), as Waveshare's BSP compensates for this panel. Its interrupt ends at a test point, so it is
  polled.
- Camera tiles, full-screen snapshots and the live camera of the P4 boards, camera alerts and media artwork use the
  shared PSRAM implementation. The board has no camera of its own configured.
- The display runs on `components/mipi_dsi_v3`, ESPHome's driver with the DSI clock left to ESP-IDF: the stock driver's
  fixed clock stops rev3 silicon while the display starts, as on the Guition JC8012P4A1 V3.
- The speaker and the two microphones are the screen's audio, experimental: a media player in Home Assistant for
  announcements and music, Volume, Microphone, Microphone gain, Automatic gain and Echo cancellation under Screen
  settings, and what audio plugins (a voice assistant) need. See "Speaker and microphones" below.
- The microSD slot, the RS485 and CAN ports and the camera connector stay unused.

## Speaker and microphones

Waveshare's schematic wires the audio of this board exactly as on the
[Waveshare ESP32-P4 86 panel](WAVESHAREP4.md): an ES8311 for the speaker (its ADC is not wired), an ES7210 with the two
microphones on its MIC1 and MIC2 and the speaker circuit's output, through an attenuator, on its MIC3 as the echo
cancellation's reference, one I2S bus for both, and an NS4150B amplifier. So the board takes the 86 panel's audio
(`packages/hardware/wavesharep4-audio/`): its codecs, its transport with echo cancellation by default, and its
Extras. [P4_AUDIO.md](P4_AUDIO.md) says how the echo cancellation works and how to choose the plain half-duplex
transport instead:

```yaml
substitutions:
  P4_AUDIO_TRANSPORT: "i2s"
```

This is **experimental**. The echo cancellation's libraries were first built for earlier silicon; this board file
builds them for rev3, where they resolve a newer esp_audio_effects (1.4.3, against 1.3.0~1 on earlier silicon).
Nobody has tried this file's audio on the board yet.

## Who tried what

- [@tomvanoosterwyck](https://github.com/tomvanoosterwyck) ran this board file on a board with rev3 silicon
  ("chip revision: v3.2", 32 MB flash) (#271): a stable picture in the right colours lying down, tiles and pages, taps in
  the right places with the mirrored axes, the brightness setting across its range, and standby with the wake by touch.
- A second owner ran a board file of their own on a board with PCB revision 1.1
  ([wish 136](https://tessera-maxgramser.on-forge.com/wishlist/136)): display, backlight, Wi-Fi, the API, touch targets
  with the X axis mirrored, and an update over Wi-Fi. That file used ESPHome's stock display driver and was built for
  the earlier silicon, so boards of both revisions are out there.
- [@Axellum](https://github.com/Axellum) had the speaker play and the microphone capture on this board with a
  configuration of their own (#271).

Not tried yet with this file: the speaker and microphones, echo cancellation, camera pictures, standing up, earlier
silicon, and a full page of tiles over a long run.

## Hardware references

- [Waveshare documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-7B) and its
  [schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-7B/ESP32-P4-WIFI6-Touch-LCD-7B.pdf).
- Waveshare's own BSP ([Waveshare-ESP32-components](https://github.com/waveshareteam/Waveshare-ESP32-components),
  `esp32_p4_wifi6_touch_lcd_7b`) is the reference for the pins below.
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/): the panel is ESPHome's own
  `model: WAVESHARE-ESP32-P4-WIFI6-TOUCH-LCD-7B`, the EK79007 at 1024 x 600 on two lanes.
- The pins:
  - Wi-Fi: ESP32-C6 over four-bit SDIO, reset GPIO54, clock GPIO18, command GPIO19, data GPIO14 to GPIO17.
  - The chip's internal regulator on channel 3 at 2.5 V for the MIPI-DSI PHY.
  - I2C: SDA GPIO7, SCL GPIO8, 400 kHz, for the GT911 and the audio codecs (ES8311 at 0x18, ES7210 at 0x40).
  - Touch: GT911, reset GPIO23, polled.
  - Backlight: GPIO32, PWM, inverted.
  - Display reset: GPIO33.
  - Audio: I2S MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, speaker data GPIO9, microphone data GPIO11; amplifier enable
    GPIO53, high for on, with a pull-down that keeps it off at reset.
- The 86 panel's two relays are not on this board: its GPIO32 is this board's backlight.

## What to report while testing

1. The silicon revision from the first lines of the USB log, a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes, a restart from the screen's settings, an update
   over the air and a cold start.
3. Taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode.
5. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
6. A text-to-speech announcement and music on the screen's media player, the Volume setting from low to high, and
   whether the speaker stays quiet between sounds.
7. The microphones, with a voice assistant plugin: whether the wake word is heard from across the room, also while
   music plays, and the **Echo cancellation status** entity (Enabled, Bypass, Starting or Error).
8. `sensor.<screen>_heap_free` with a full layout, any reset, Wi-Fi drop or I2C error, and how long the screen stayed
   running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
