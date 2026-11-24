# Chip revisions

Some chips change their silicon in a way one firmware cannot cross. An ESP32-P4 before revision 3 (the boot log says
"chip revision: v1.3") and one of revision 3 ("v3.0" and up) need different builds: ESP-IDF lays out memory differently
for the two, so a firmware for the one never starts on the other. Boards sold under one name carry either, and nothing
on the outside says which: a 4.3-inch Guition JC4880P443 bought in October 2026 had rev3 silicon without a V3 marking
(GitHub #336), and so did 7-inch JC1060P470 boards (#397, #462).

So Tessera does not guess the silicon from the board. It reads the chip, and builds every firmware of a screen for the
revision it found. This page says how, and what to do when a chip family adds a revision that matters.

## One number in the screen's own YAML

A screen's own YAML (the one Tessera writes for it) carries one fact about its chip:

```yaml
substitutions:
  CHIP_REVISION: "302"
```

The number is ESP-IDF's full revision, major x 100 + minor, so `302` is v3.2 and `103` is v1.3. It is a fact about the
chip, not a choice. The packages decide what a revision needs, next to the setting each rule changes:
`packages/hardware/esp32p4-core.yaml` turns it into the ESP32-P4's `engineering_sample` switch and the display driver
(below). Nothing else in the add-on, the editor or the firmware knows what a revision means.

A screen's YAML without the line builds the board's own default. For most ESP32-P4 boards that is `"0"`, the earlier
silicon the first units of every P4 model carried. A board whose units all carry rev3 states `CHIP_REVISION: "301"` in
its board file (the JC8012P4A1 V3, the Waveshare 10.1-inch V3 and 7B): rev3 from v3.1 on, ESP-IDF's own default
minimum. The screen's own line always wins over both.

## Where the number comes from

Most certain first (`screen_manager/app/chip_revision.py`):

1. **The chip on the USB cable, while Tessera installs.** The editor's browser installer reads it with esptool-js right
   after it reads the MAC (`readRevision` in `web/src/flasher/esptool.ts`) and sends it with the request; New screen
   writes it into the new YAML, Firmware & USB into the existing one. A port on Home Assistant's own machine is read with
   esptool right before the build (`chip_revision.read_usb`).
2. **The screen itself, once it runs.** Every firmware has a "Screen chip" sensor, for example "ESP32-P4 v3.2"
   (`components/smart_display/chip_revision.h`), read from the chip's eFuses. Before every build of a screen
   (`Firmware.start`), Tessera writes what that sensor says into the screen's YAML, so an update is built right also for
   a screen that was installed some other way.
3. **An Override YAML that switched an ESP32-P4 to rev3 by hand**, with `esp32: engineering_sample: false`. That was the
   way around this before Tessera read the chip, and it says rev3 as plainly as the chip does, so a screen running on
   that workaround gets `CHIP_REVISION: "300"` at its next update: the widest rev3 build, from v3.0 on, which runs on
   every v3.x. Its firmware then reports the real number, and the update after builds for that.

When none of them says anything, the YAML stays as it is. The line is written only when it changes, and nothing else in
the file moves (`Firmware.set_chip_revision`). `CHIP_REVISION` is one of the substitutions an Override YAML may not
set, since its value comes from the chip.

## The last check before anything is written

ESP-IDF writes the range of chip revisions an image runs on into its header (`min_chip_rev_full`,
`max_chip_rev_full`), and its bootloader refuses a chip outside it. The browser installer compares that range with the
chip on the cable before it writes (`imageRevisions` and `revisionFits` in `web/src/flasher/logic.ts`). A firmware for
other silicon is not written, and the page says which revisions it was built for and which the chip is. This check knows
no chip family: it holds for any revision rule ESP-IDF has or adds.

## The ESP32-P4

`packages/hardware/esp32p4-core.yaml` holds both rules:

- `engineering_sample: true` below revision 300, `false` from 300 on. This is ESP-IDF's
  `CONFIG_ESP32P4_SELECTS_REV_LESS_V3`.
- `DSI_PLATFORM`: ESPHome's own `mipi_dsi` below 300, the repository's `mipi_dsi_v3` from 300 on. ESPHome's driver up to
  2026.9.0 names a display clock that only the earlier silicon has, so on rev3 it aborts while the display starts and
  the screen restarts until safe mode (GitHub #52, #462). `mipi_dsi_v3` is that driver with the clock left to ESP-IDF,
  which picks the right one on either revision (esphome/esphome#18984, in ESPHome 2026.9.1). Every P4 board's display
  says `platform: ${DSI_PLATFORM}`. Once the app and every P4 board's `min_version` are at 2026.9.1 or newer, the rule
  goes and every board takes `mipi_dsi` again.
- `P4_EV_BOARD`: ESPHome's name of Espressif's function EV board for the revision, for a hardware file that names a
  board (the Tab5's). ESPHome refuses a pre-v3 board name on a rev3 build, and the other way round. The other P4 boards
  name none.
- The lowest revision in the image's header (`CONFIG_ESP32P4_REV_MIN_300` or `_301`). ESP-IDF builds rev3 for v3.1 and up
  unless told otherwise, and Espressif's errata list a v3.0 with its own chip marking (X F XX,
  [chip revision identification](https://docs.espressif.com/projects/esp-chip-errata/en/latest/esp32p4/01-chip-identification/index.html)).
  So a chip read as v3.0 (`300`) gets an image that runs from v3.0 on, and every other rev3 reading, the boards'
  default `301` included, gets ESP-IDF's default. Without this a v3.0 chip would be given a rev3 build its own header
  refuses. Pre-v3 builds set neither.

The CPU runs at 360 MHz on both, the most the earlier silicon takes. `tests/test_p4_core.py` keeps the rules in the core
file alone: no board or hardware file sets `engineering_sample`, names a DSI driver or an ESP32-P4 board itself.

## A new revision rule

When a chip family adds silicon that a firmware cannot cross (a new ESP32-P4 revision, another chip doing the same):

1. Find what changes between the revisions in ESP-IDF: its `Kconfig` for the chip (`CONFIG_<CHIP>_REV_MIN`,
   `..._SELECTS_REV_...`) and ESPHome's `esp32` component, and how ESPHome exposes it.
2. Write the rule in the chip's core hardware file, from `CHIP_REVISION`, as a substitution with a Jinja expression
   next to the setting it changes, the way `esp32p4-core.yaml` does. Give the core file a default `CHIP_REVISION` for
   boards where nobody read the chip, and let a board file whose units all carry the newer silicon state its own.
3. Check both builds with `esphome config` on the add-on's ESPHome and the packages' `min_version`, with a screen YAML
   that sets `CHIP_REVISION` around the board's checkout entry, and look at the rendered setting.
4. Extend `tests/test_p4_core.py` (or a test of its own for the new chip) so the rule stays in the core file.

Nothing in the add-on, the editor or the firmware changes for a new rule: they only carry the number.

## A board with the newer silicon

A board that is only sold with the newer silicon now needs no file of its own for that: Tessera reads the chip, and the
board's existing file builds for it. A board file of its own is for hardware that really differs (another LCD, other
pins), as the JC8012P4A1 V2 and V3 still have their own keys because screens are installed under them. Their shared
parts live once in a hardware file (`hardware/guition-jc8012p4a1-newer-lcd.yaml`, `hardware/waveshare101.yaml`).

## The places a change of this kind touches

- `packages/hardware/<chip>-core.yaml`: the rule, from `CHIP_REVISION`.
- `tests/test_p4_core.py`: the rule stays in the core.
- `screen_manager/app/chip_revision.py`: only when the number comes from somewhere new.
- `components/smart_display/chip_revision.h`, `web/src/flasher/`: only when reading the chip changes.
- This page, and `screen_manager/CHANGELOG.md` when users notice it.
