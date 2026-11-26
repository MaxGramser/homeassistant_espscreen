# The Tab5 does not build in the render harness

## The symptom

`tools/render/run.py tab5` (and `tab5-portrait`) ends with `BUILD FAILED`: ESPHome refuses the host configuration the
harness writes for the board, so no picture of the Tab5's glass (1280 x 720 at 294 dpi, the only board with that glass)
can be made on a computer. Found on 2026-11-26 while rendering the thermostat's card on every glass.

## What we know

The harness (`tools/render/host.py`) takes a board's ESP32 hardware out of its packages. The Tab5 brings four things it
did not know, each found as the next error once the one before was gone:

1. `hardware/parts/amplifier.yaml` kept an empty `packages:` after its only package (audio) was left out. Fixed: an
   empty `packages:` is dropped.
2. `hardware/parts/echo-cancel.yaml` (`esp_aec`) and the codec's transport through it (`es7210/aec.yaml`,
   `esp_audio_stack`) are audio by another name. Fixed: `audio_package` leaves them out.
3. The board's IO expander `pi4ioe5v6408` and what hangs on its pins. Fixed: it is a hardware block, and an item on one
   of its pins goes with it. The speaker's amplifier, whose pin is the expander's, is left out as audio.
4. After those, ESPHome prints the whole `esphome:` block as failed (`esphome: None`) without a sentence that names
   the fault in the part of the log that was read. Open.

The same round fixed the Waveshare 3.5 (`waveshare35`), whose standby key is on an expander's pin
(`STANDBY_KEY: {pca9554: ...}`): on the host the key stands as a plain pin, and both its variants render.

## Ruled out

- The firmware: the Tab5 builds for its chip in CI (2026-11-26, the release commit of 0.4.106, on the app's ESPHome and
  the newest one).
- The other boards: `cyd` and `wavesharep4` render as before with the changes above.

## Candidates

- Something in `esphome: on_boot:` of the Tab5's hardware file that names the expander or a part that was left out (a
  boot step that sets an expander's pin), which `host_file` only drops when it says `id(expander)`.
- A substitution a left-out audio part defined and the board file or the core still names.

## The deciding experiment

Read the whole of `.esphome/render/build/logs/compile-render-tab5.log` after `esphome: None` for the line ESPHome marks
(it prints the fault inside the block, far down for a block this long), or run
`esphome config .esphome/render/build/render-tab5.yaml` and read its last lines.

## Pointers

`tools/render/host.py` (`HARDWARE_BLOCKS`, `ON_I2C`, `audio_package`, `host_file`, `walk`), `packages/boards/tab5.yaml`,
`packages/hardware/m5stack-tab5.yaml`, `tests/test_render_host.py`.
