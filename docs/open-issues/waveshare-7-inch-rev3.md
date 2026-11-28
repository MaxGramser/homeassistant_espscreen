# The Waveshare 7-inch P4 (ESP32-P4-WIFI6-Touch-LCD-7) on rev3 silicon

## Symptom

None seen yet: nobody has run `packages/boards/wavesharep47.yaml` on a board with rev3 silicon. The board file builds for
pre-v3 silicon ("chip revision: v1.3"), and Waveshare now ships its P4 boards with rev3 ("chip revision: v3.x").

## What we know

- The board file runs on pre-v3 silicon (a community member, picture, touch, audio; docs/WAVESHAREP47.md).
- On the 10.1-inch of the same series (2026-11-16, c24a281d), a unit of chip revision v3.2 did not start with
  `engineering_sample: false` alone: the USB log reached "Performing bus recovery" and then stopped in
  `esp_lcd_new_dsi_bus`, over and over. With the repository's `components/mipi_dsi_v3` as well it started, joined Wi-Fi,
  drew its pages and took touches. That board is now two board files (waveshare101, waveshare101v3).
- The 7B (`wavesharep47b.yaml`, another panel on the same family of main board) builds for rev3 with `mipi_dsi_v3`
  and a community member ran it on rev3 silicon.
- This board file uses ESPHome's `mipi_dsi` with `model: WAVESHARE-7-DSI-TOUCH-A`; `mipi_dsi_v3` is ESPHome 2026.9.0's
  `mipi_dsi` with one line changed, and it has the same model (`components/mipi_dsi_v3/models/waveshare.py`).

## Ruled out

Nothing: there is no rev3 7-inch on the bench.

## Candidates

1. The 10.1's way: `engineering_sample: false` and `platform: mipi_dsi_v3`, a board file of its own (as waveshare101v3).
2. The chip revision alone is enough on this panel (unlikely after the 10.1, not excluded).

## The deciding experiment, and what a report needs

From an owner of a rev3 7-inch, in a GitHub issue:

1. The first lines of the USB log: the "chip revision" line, and the board's SKU or the sticker on the back.
2. With the board file as it is plus `engineering_sample: false` in the screen's Override YAML: the USB log from boot
   until it restarts or settles. A restart right after "Performing bus recovery" with `esp_lcd_new_dsi_bus` in the
   backtrace is the display driver; a restart straight after the bootloader is the chip revision.
3. If someone can build from a clone: the same with the display block's `platform: mipi_dsi` changed to
   `platform: mipi_dsi_v3`, and whether the picture, touch and backlight then work.

A rev3 board file is added only once one has been seen to run.

## Pointers

docs/WAVESHAREP47.md ("Which silicon"), docs/WAVESHARE101.md, packages/boards/wavesharep47.yaml,
packages/boards/waveshare101-v3.yaml, packages/boards/wavesharep47b.yaml, components/mipi_dsi_v3/.
