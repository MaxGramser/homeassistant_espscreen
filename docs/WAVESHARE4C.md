# Waveshare ESP32-P4-WIFI6-Touch-LCD-4C (round)

The `waveshare4c` board file supports Waveshare's round 4-inch ESP32-P4 screen, 720 × 720 pixels
behind a circular glass, with the shared screen UI in two columns and two rows. The board is
experimental.

The 4C shares its main board with the square ESP32-P4-WIFI6-Touch-LCD-4B and the 86 panel
(`wavesharep4`, [WAVESHAREP4.md](WAVESHAREP4.md)): the chip, the memory, the ESP32-C6 for Wi-Fi,
the touch panel, the backlight and the audio are wired alike, and the two board files include the
same hardware files for them (`hardware/esp32p4-c6.yaml`, `hardware/wavesharep4-4inch.yaml`,
`hardware/wavesharep4-audio.yaml`). What is its own is the glass: a round JD9365 panel, and a page
that keeps inside the circle.

## Hardware

| Part | Configuration |
| --- | --- |
| Processor | ESP32-P4, pre-v3 silicon (the board tried reported chip revision v1.0) |
| Memory | 32 MB flash, 32 MB PSRAM |
| Display | JD9365, round, ESPHome `mipi_dsi` model `WAVESHARE-ESP32-P4-WIFI6-TOUCH-LCD-4C`, reset GPIO27, no enable pin |
| Backlight | Inverted PWM on GPIO26 at 200 Hz |
| Touch | GT911 on the touch bus (SDA GPIO7, SCL GPIO8), reset GPIO23, polled every 20 ms |
| Wi-Fi | ESP32-C6 over SDIO, as on the square board |
| Audio | ES8311 speaker codec and ES7210 microphones as on the square board (`hardware/wavesharep4-audio.yaml`) |

ESPHome supplies the display's initialization and timings through its built-in panel model,
which is in ESPHome 2026.9.0; the board file asks for that version.

Like the square board, this one builds for pre-v3 P4 silicon. A 4C that reports v3.0 or higher in
the serial installation output needs `engineering_sample: false` under `esp32:` in the screen's
Override YAML.

## The round glass

A round panel shows only the circle inscribed in its 720 × 720 canvas, so the corners of a square
page fall outside the glass. The board file sets `SAFE_INSET: "96"`: the top bar, the grid of
cards, the page dots and the page arrows all stand 96 pixels in from every edge of the canvas,
close to the inscribed square's (720 − 720/√2)/2 ≈ 105 pixels; the cards round their corners, so a
little less is enough. `SAFE_INSET` is 0 in both looks, so every other board lays out as before.

The inset is applied where the canvas is divided up: the header's margin (`HEADER_INSET` in the
looks), the grid container (`runtime_tiles.h`), the page bar (`page_bar.h`), the page arrows and
the bedside sizes (`looks/shared/digits.yaml`). The firmware's self test checks the grid against
the same inset.

Known gap: the pull-up page drawer still spans the full width of the canvas, so its corners are
cut off by the glass. It works; it is the next thing to fit inside the circle.

## Installation

1. Install a release of ESP Screen Manager that lists this board and open **New screen**.
2. Select **Waveshare ESP32-P4-WIFI6-Touch-LCD-4C** and enter the screen's name and Wi-Fi
   details.
3. Connect the board's USB port with a data cable and select that port for installation.
4. ESP Screen Manager adds the screen to Home Assistant's ESPHome integration and allows its
   actions by itself ([Easy Setup](EASY_SETUP.md), chapter 3).
5. Add the screen's tiles in ESP Screen Manager.

Before the board is in a published release, developers can use `checkout/waveshare4c.yaml` with the
[checkout instructions](../checkout/README.md). Credentials belong in ignored
`checkout/secrets.yaml`, never in the board file.

## What has been tried

On one board (chip revision v1.0, 32 MB flash), built with ESPHome 2026.9.0:

- picture, touch, backlight, Wi-Fi and an over-the-air update;
- the demo layout, and the firmware's self test on the glass: every page and overlay, every card
  inside the round safe area;
- added to Home Assistant and given a layout from ESP Screen Manager;
- `tools/render/run.py waveshare4c` passes.

The speaker and the microphones are declared as on the square board and start without errors, but
have not been listened to. Standing up (portrait) has not been tried on the glass.
