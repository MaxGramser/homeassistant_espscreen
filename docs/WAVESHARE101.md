# Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1, experimental

This is the **ESP32-P4-WIFI6-Touch-LCD-10.1** (SKU 33150), the 10.1-inch board of Waveshare's ESP32-P4-WIFI6-Touch-LCD
7, 8 and 10.1-inch series: an 800 x 1280 panel with a JD9365 MIPI-DSI driver, GT9271 capacitive touch, an ESP32-P4 with
32 MB flash and 32 MB PSRAM, and an ESP32-C6 beside it for Wi-Fi. Tessera runs it lying down at 1280 x 800 with a grid of
five by five cells, the glass and grid of the 10.1-inch Guition JC8012P4A1.

Its display, touch and backlight settings are those of a configuration a community member runs on the board (see "Where
it comes from" below). Nobody has reported running this board file itself on one, and the project has not tried it, so
the board is **experimental**.

## Which silicon

Waveshare's ESP32-P4 boards come with two revisions of the chip, and firmware for one does not start on the other. This
board file builds for the earlier silicon ("chip revision: v1.3" in the first lines of the USB log), which the board the
configuration runs on has. A board that reports v3.0 or higher needs this in its screen's Override YAML:

```yaml
esp32:
  engineering_sample: false
```

## Install

Update Tessera Screen Manager and choose **Waveshare · 10.1 inch, ESP32-P4-WIFI6-Touch-LCD-10.1** (marked
Experimental) in **New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi
references and unique API/OTA keys. Keep an existing working profile if the board is already installed.

The remote package is `packages/waveshare101.yaml` and the checkout entry `checkout/waveshare101.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/waveshare101.yaml`.

## Layout and capabilities

- 1280 x 800 at 149 dpi, the standard look, five columns of five cells either way up. The panel is 800 x 1280 itself;
  lying down is LVGL's 270 degrees, with the board's camera at the top. A screen hung the other way round takes another
  angle from the Rotation setting, without a new build.
- The backlight is a PWM pin (GPIO26, not inverted) at 20 kHz, with a lowest level of 1 %: brightness is a percentage,
  and standby, night mode, Sleep, Wake and the alert's flashes are enabled.
- The touch panel reports pixels, with no calibration. Its interrupt and reset are not wired to the P4, so it is polled.
- Camera tiles, full-screen snapshots and the live camera of the P4 boards, camera alerts and media artwork use the
  shared PSRAM implementation. The board's own camera connector is not configured.
- The speaker and the two microphones are the screen's audio, experimental: a media player in Home Assistant for
  announcements and music, Volume, Microphone, Microphone gain, Automatic gain and Echo cancellation under Screen
  settings, and what audio plugins (a voice assistant) need. See "Speaker and microphones" below.
- The microSD slot is not configured.

## Speaker and microphones

This board shares its main board, the ESP32-P4-WIFI6-Touch-LCD-X, with the
[7-inch ESP32-P4-WIFI6-Touch-LCD-7](WAVESHAREP47.md), and Waveshare's schematic of it wires the audio exactly as on the
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

This is **experimental**: it follows from the shared main board, and nobody has tried the audio on this board yet. The
same audio worked on the 7-inch of the series.

## Where it comes from

- Amazingwun runs a hand-written ESPHome 2026.9.1 configuration on the board
  ([wish 125](https://tessera-maxgramser.on-forge.com/wishlist/125)): display, touch, backlight, Wi-Fi and the picture
  lying down work. Two things it needed: PSRAM at hex mode and 200 MHz (the P4 boards' setting here), and the panel's
  reset on GPIO27, which ESPHome's panel model does not bring. The backlight's 20 kHz and 1 % come from it.
- [@icodeforyou](https://github.com/icodeforyou) wrote a board file from it (#281). The pull request reports a build of
  it flashed from a checkout and updated over Wi-Fi, with touch in the corners, colours, backlight levels, standby and
  the wake, and page switches tried; its commit message says it was not yet installed through ESP Screens. Its backlight
  (1 kHz, lowest level 15 %) is not that of the configuration that runs, and it also carried the 86 panel's audio,
  which nobody tried on this board.
- This board file has the display and touch of both, the backlight of the configuration that runs, and the 86 panel's
  audio, as the 7-inch of the series runs it. So this exact file has not been run on the glass yet; please report how
  it goes.

## Hardware references

- [Waveshare's documentation for the series](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-X), its
  [product page](https://www.waveshare.com/esp32-p4-wifi6-touch-lcd-7-8-10.1.htm), its
  [schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-X/ESP32-P4-WIFI6-Touch-LCD-X-Schematic.pdf) and
  its board support package ([Waveshare-ESP32-components](https://github.com/waveshareteam/Waveshare-ESP32-components),
  `esp32_p4_wifi6_touch_lcd_x`).
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/): the panel is ESPHome's
  `model: WAVESHARE-P4-NANO-10.1`, the JD9365 at 800 x 1280 on two lanes, with the reset on GPIO27.
- The pins:
  - Wi-Fi: ESP32-C6 over four-bit SDIO, reset GPIO54, clock GPIO18, command GPIO19, data GPIO14 to GPIO17.
  - The chip's internal regulator on channel 3 at 2.5 V for the MIPI-DSI PHY.
  - I2C: SDA GPIO7, SCL GPIO8, for the touch panel and the audio codecs (ES8311 at 0x18, ES7210 at 0x40).
  - Backlight: GPIO26, PWM.
  - Audio: I2S MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, speaker data GPIO9, microphone data GPIO11; amplifier enable
    GPIO53, high for on, with a pull-down that keeps it off at reset.
- This board needs ESPHome 2026.9.0 or newer for its audio.

## What to report while testing

1. The silicon revision from the first lines of the USB log, a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes, a restart from the screen's settings, an update
   over the air and a cold start.
3. Taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, and night mode.
5. Camera tile pictures, full-screen camera images and camera alerts.
6. A text-to-speech announcement and music on the screen's media player, the Volume setting from low to high, and
   whether the speaker stays quiet between sounds.
7. The microphones, with a voice assistant plugin: whether the wake word is heard from across the room, also while
   music plays, and the **Echo cancellation status** entity (Enabled, Bypass, Starting or Error).
8. `sensor.<screen>_heap_free` with a full layout, any reset, Wi-Fi drop or I2C error, and how long the screen stayed
   running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
