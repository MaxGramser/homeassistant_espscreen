# Waveshare ESP32-P4-WIFI6-Touch-LCD-7, experimental

This is the **ESP32-P4-WIFI6-Touch-LCD-7** (SKU 33147), the 7-inch board of Waveshare's ESP32-P4-WIFI6-Touch-LCD 7, 8
and 10.1-inch series: a 720 x 1280 panel with an ILI9881C MIPI-DSI driver, GT9271 capacitive touch, an ESP32-P4 with
32 MB flash and 32 MB PSRAM, an ESP32-C6 beside it for Wi-Fi, and a speaker (ES8311) and microphones (ES7210). Tessera
runs it lying down at 1280 x 720, a quarter turn of the panel.

It is not the [ESP32-P4-WIFI6-Touch-LCD-7B](WAVESHAREP47B.md) (1024 x 600, another panel) and not the ESP32-S3-Touch-LCD-7.
The 8 and 10.1-inch boards of the same series share its main board with other glass, and this board file is not for
them; the 10.1-inch has [a board file of its own](WAVESHARE101.md).

A community member ran this board file on the board (see "Who tried what" below). The project has not tried it on one,
so the board is **experimental**.

## Which silicon

Waveshare's ESP32-P4 boards come with two revisions of the chip, and firmware for one does not start on the other. This
board file builds for the earlier silicon ("chip revision: v1.3" in the first lines of the USB log), which the board it
was run on has. A board that reports v3.0 or higher needs this in its screen's Override YAML:

```yaml
esp32:
  engineering_sample: false
```

Nobody has tried this board file on rev3 silicon yet.

## Install

Update Tessera Screen Manager and choose **Waveshare · 7 inch, ESP32-P4-WIFI6-Touch-LCD-7** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Keep an existing working profile if the board is already installed.

The remote package is `packages/wavesharep47.yaml` and the checkout entry `checkout/wavesharep47.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/wavesharep47.yaml`.

## Layout and capabilities

- 1280 x 720 at 210 dpi, the standard look, four columns of four cells lying down and two columns of eight standing up.
  The panel is 720 x 1280 itself; lying down is a quarter turn, which the screen's Rotation setting can change.
- The backlight is a PWM pin (GPIO26, not inverted) at 5 kHz, at most 95 % of its range as in Waveshare's examples:
  brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes are enabled.
- The touch panel reports pixels, with no calibration.
- Camera tiles, full-screen snapshots and the live camera of the P4 boards, camera alerts and media artwork use the
  shared PSRAM implementation. The board's own camera connector is not configured.
- The speaker and the two microphones are the screen's audio, experimental: a media player in Home Assistant for
  announcements and music, Volume, Microphone, Microphone gain, Automatic gain and Echo cancellation under Screen
  settings, and what audio plugins (a voice assistant) need. See "Speaker and microphones" below.
- The microSD slot is not configured.

## Speaker and microphones

Waveshare's schematic of the ESP32-P4-WIFI6-Touch-LCD-X main board, which this 7-inch and the 10.1-inch share, wires
the audio exactly as on the [Waveshare ESP32-P4 86 panel](WAVESHAREP4.md): an ES8311 for the speaker (its ADC is not
wired), an ES7210 with the two microphones on its MIC1 and MIC2 and the speaker circuit's output, through an
attenuator, on its MIC3 as the echo cancellation's reference, one I2S bus for both, and an NS4150B amplifier. So the
board takes the 86 panel's audio (`packages/hardware/wavesharep4-audio/`): its codecs, its transport with echo
cancellation by default, and its Extras. [P4_AUDIO.md](P4_AUDIO.md) says how the echo cancellation works and how to
choose the plain half-duplex transport instead:

```yaml
substitutions:
  P4_AUDIO_TRANSPORT: "i2s"
```

This is **experimental**: the contributor ran the same audio on the board (below), the project has not.

## Who tried what

[@Nulifier](https://github.com/Nulifier) ran the board file of #274 on the board, with pre-v3 silicon
([wish 153](https://tessera-maxgramser.on-forge.com/wishlist/153)): it starts, the picture is right and turns, the touch
works, the backlight dims and Wi-Fi connects. That file also carried the 86 panel's audio, the same codecs, transport
and amplifier this board file now has: the speaker played music, the microphones captured, playback and capture worked
together and echo cancellation worked well. Not tried yet: camera pictures, rev3 silicon, and a full page of tiles over
a long run.

## Hardware references

- [Waveshare's product page for the series](https://www.waveshare.com/esp32-p4-wifi6-touch-lcd-7-8-10.1.htm), its
  [documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-X), its
  [schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-X/ESP32-P4-WIFI6-Touch-LCD-X-Schematic.pdf) and its
  [examples](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-X).
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/): the panel is ESPHome's
  `model: WAVESHARE-7-DSI-TOUCH-A`, the ILI9881C at 720 x 1280, with the reset on GPIO27.
- The pins:
  - Wi-Fi: ESP32-C6 over four-bit SDIO, reset GPIO54, clock GPIO18, command GPIO19, data GPIO14 to GPIO17.
  - The chip's internal regulator on channel 3 at 2.5 V for the MIPI-DSI PHY.
  - I2C: SDA GPIO7, SCL GPIO8, 400 kHz, for the touch panel and the audio codecs (ES8311 at 0x18, ES7210 at 0x40).
  - Touch: reset GPIO23 and interrupt GPIO33, as on the board this file was run on.
  - Backlight: GPIO26, PWM.
  - Audio: I2S MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, speaker data GPIO9, microphone data GPIO11; amplifier enable
    GPIO53, high for on, with a pull-down that keeps it off at reset.
- Waveshare's board support package for the series
  ([Waveshare-ESP32-components](https://github.com/waveshareteam/Waveshare-ESP32-components),
  `esp32_p4_wifi6_touch_lcd_x`) has the same audio pins.
- This board needs ESPHome 2026.9.0 or newer for its audio.

## What to report while testing

1. The silicon revision from the first lines of the USB log, a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes, a restart from the screen's settings, an update
   over the air and a cold start.
3. Taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. A text-to-speech announcement and music on the screen's media player, the Volume setting from low to high, and
   whether the speaker stays quiet between sounds.
6. The microphones, with a voice assistant plugin: whether the wake word is heard from across the room, also while
   music plays, and the **Echo cancellation status** entity (Enabled, Bypass, Starting or Error).
7. `sensor.<screen>_heap_free` with a full layout, any reset, Wi-Fi drop or I2C error, and how long the screen stayed
   running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
