# Adding a board

The recipe, in the order the work actually goes: the hardware is looked up, the layout is computed, and only the
grid is a choice. `docs/RESPONSIVE.md` says why the layout works the way it does.

## 1. The board's details

Its name and SKU, its resolution, its diagonal in inches, its chip (ESP32, S3, P4), how much flash and PSRAM it
has, and what its touch panel is. The shop page or `devices.esphome.io` has all of it.

## 2. Look it up in ESPHome

ESPHome supports many panels by name, and then one line sets the pins, the timings and the dimensions:

| Driver | For | Example models |
|---|---|---|
| `mipi_spi` | small SPI panels | `ESP32-2432S028` (the CYD), `JC4827W543`, `WT32-SC01-PLUS`, `T-DISPLAY-S3` |
| `mipi_rgb` | 16-bit parallel panels | `ST7701S` with a board's own pins (the Waveshare 4B), `GUITION-4848S040`, `ESP32-S3-TOUCH-LCD-4.3`, `ESP32-S3-TOUCH-LCD-7-800X480`, `ESP32-8048S070`, `WAVESHARE-5-1024X600` |
| `mipi_dsi` | ESP32-P4 panels | `WAVESHARE-P4-86-PANEL`, `M5STACK-TAB5`, `JC8012P4A1`, `JC8012P4A1-V2`, `JC1060P470` |

A board that is not in those lists needs its pins, its init sequence and its timings from the manufacturer's
example, which is the one genuinely difficult part of a new board.

## 3. A base configuration from ESPHome

A board file is its hardware, the facts of its glass, and the packages it includes (docs/PROFILES.md). Step 4 writes
it from the board that resembles the new one most; what you replace by hand are its hardware sections: `display`,
`touchscreen`, the `output` that drives the backlight (always `id: gpio_backlight_pwm`), `i2c`/`spi`, `esp32` (board,
variant, flash size) and `psram`. Keep the ids the other boards use (`my_display`, `ts_touch`, `gpio_backlight_pwm`):
the shared tree, the features and owners' overrides find the parts by them.

Then choose what the board includes:

- `hardware/esp-idf.yaml`, always (directly, or through a hardware file that includes it);
- a hardware file of its family when it has one: `hardware/esp32s3-rgb.yaml` for an ESP32-S3 with octal PSRAM that
  drives an RGB panel, `hardware/waveshare-ch422g.yaml` for a Waveshare with the CH422G expander. A family file names
  what its boards share; the board file adds its flash size and names its panel with `display: - id: !extend
  my_display`. When a second board turns out to share hardware with one that has no family file yet, move the shared
  part into one instead of copying it (`tools/check_packages.py` refuses a block two board files carry word for word);
- one look: `looks/standard.yaml`, or `looks/compact.yaml` for glass too small for it;
- how its touch panel is read: `features/capacitive-touch.yaml` (GT911, GSL3670: pixels, no calibration) or
  `features/resistive-touch.yaml` (XPT2046: calibrated on the glass, and the board states the raw range it measured,
  `TOUCH_CAL_*`);
- `features/backlight.yaml`, and `features/backlight-always-on.yaml` after it for a backlight that must never go dark;
- with PSRAM: `features/camera.yaml`, `features/self-test.yaml`, and `features/snapshot.yaml` when there is memory for
  a second frame.

One number to look at on a parallel (RGB) panel: `LVGL_BUFFER_SIZE`. The picture lives in PSRAM, but LVGL's draw
buffer lives in the memory inside the chip, next to Wi-Fi, the API and the panel's bounce buffers, and a quarter of
800 × 480 is 192 KB of it. The Waveshare 4.3 ran on 15 KB free that way and hung under a large layout; at 12 % it
boots with 112 KB. Read `sensor.<screen>_heap_free` after the first boot with a full layout: under 40 KB is too
little.

## 4. The layout: two grids, and sizes the look works out

```
python3 tools/propose_grid.py             # what grid the resolution and the diagonal ask for, each way up
python3 tools/new_board.py <name> --from waveshare43 --width 800 --height 480 --inch 4.3 [--cols 3 --rows 2] \
                                  [--portrait-cols 1 --portrait-rows 4] [--rotation 0|90|180|270] [--look compact] \
                                  [--title Waveshare] [--model ESP32-S3-Touch-LCD-4.3] [--status new|experimental]
```

`tools/new_board.py` adds the whole board in one go: its board file, its entry in `boards.yaml`, its two entry files
(`packages/<name>.yaml` and `checkout/<name>.yaml`, written by `tools/generate_entries.py`), the cards of its grid
(`tools/generate_cells.py`), `boards.json` (`tools/generate_board_shapes.py`), and an override case in
`tests/fixtures/overrides/<name>-contract.yaml`. A board only tried out is called `lab-<name>`: it gets its board file
and its cards and stays out of the catalog and out of Git.

`--from` is the key of the board that resembles the new one most (its entry in `boards.yaml`): the new file starts with
its packages, its hardware sections and its own hardware values (a backlight frequency, a display model, calibration
figures), which stay the template's until you replace them; `tools/check_packages.py` refuses a hardware section that
is still the template's word for word. `--width` and `--height` are the canvas of the screen lying down and `--rotation`
the LVGL angle that lays the panel out that way, so the board file states the panel's own pixels (`PANEL_W`,
`PANEL_H`) and that angle (`ROTATION_LANDSCAPE`). It then states its density (`DISPLAY_DPI`, with the decimals it has)
and its grid the two ways the screen can hang (`GRID_COLS`, `GRID_ROWS`, `GRID_COLS_PORTRAIT`, `GRID_ROWS_PORTRAIT`).
Every size comes from the look, scaled to that density, so a tile, a letter and a key keep their size in millimetres,
and what depends on the canvas the firmware works out on the glass (see below).

The grid is the one real choice: the proposal keeps a tile at about 33 × 16 mm and never smaller than 30 × 12 mm,
but a board of the same size can be read as "more tiles" or "bigger tiles". Render both and look. It is two
choices on glass that is not square, because a card keeps its size in millimetres: a screen that holds three
columns lying down may hold one standing up, and ESP Screens offers the owner both when the screen is built.

Two things to weigh for the standing grid. `tools/generate_cells.py` gives a board the cards of whichever of its
two grids is larger, so a standing grid with more cells than the lying one costs every screen of that board those
extra cards, whichever way it hangs; the four boards that ship are all at the larger of their two, so none of them
pays for the second way round. And a screen holds 64 tiles in all, one dirty bit each, so a page of 32 cells leaves
room for two pages and a page of 44 for only one. That is why the 10.1-inch stands at four columns of five rather
than the four of eleven the millimetres would allow.

State no number in the board file that follows from the canvas. The tile area, the cells, the page keys, the strip
that opens the settings, the crosses of the touch test and the card of an alert are all measured at boot from the
canvas LVGL hands the screen. That is what lets one firmware serve the board either way round, and a board file
that states such a number would be right one way and wrong the other.

## 5. Look at it before it ever reaches the glass

`tools/render/run.py <board>` builds the real firmware of the board as a program for this computer and draws it into
an SDL window (it needs ESPHome and SDL2; run it with ESPHome's Python). It sends the demo layout of every kind of card,
runs the firmware's own self test (`ui_self_test`: every page and overlay, each page's cards and bar, and the check that
nothing falls outside its area), and saves every page, the alerts (a camera picture included, on a board that draws
pictures) and Dark mode as PNGs under `.esphome/render/out/<board>/`, with a sheet of all of them. A board whose glass
is not square is done standing up as well (`<board>-portrait`). That catches a cramped forecast, a clipped name or a
card that falls outside its area without a board on the desk. `tools/check.sh --render` does it for every board, and
CI does it on every push and pull request. docs/TESTING.md says what it checks and what only the glass shows.

## 6. Then the board itself

Flash it once: touch (the corners and a drag), the backlight, the colour order, the rotation, and a page switch.
What a render cannot show is exactly what the hardware check is for. Then flash it standing up, which is the same
build with `LVGL_ROTATION` a quarter further than `ROTATION_LANDSCAPE`, and walk the same list again.

## 7. Write it down

Say what the backlight can do. `BACKLIGHT_DIMMABLE` is true unless the board states false: a PWM pin takes levels,
a line on an expander is lit or dark, and the percentages become switches. A board that cannot go dark at all, as the
Waveshare 4.3 browns out when its backlight boost switches on again, includes `features/backlight-always-on.yaml`:
that sets `CAN_STANDBY` to false, keeps the entities of standby and night internal, and takes the blinks out of an
alert. `tools/generate_board_shapes.py` writes both flags into boards.json for the add-on, and
`tests/test_easy_package.py` keeps the flag and the entities together.

A screen also says what it can do while it runs, in its **Screen features** sensor (firmware 0.2.99): one word per
ability, so the add-on follows the screen itself and only falls back to boards.json for firmware from before that
sensor and for a screen that is offline. That matters for a board that was changed after it was built: a Waveshare
whose backlight was rewired to a PWM pin (`docs/WAVESHARE7.md`) really does dim, and a table per board would keep
saying it cannot. An ability is one row on each side: a line in the `features` list of the sensor in
`packages/core.yaml`, and a row in `FEATURES` in `screen_manager/app/core.py` naming the boards.json key it falls
back to. A word the add-on does not know is skipped, so new firmware may report one an older add-on never heard of.

The board file carries its own `BOARD_ID` (the screen reports it; `tools/new_board.py` sets it). The Rotation select
comes from the core, with the angles the glass allows. Its entry in `boards.yaml`, the catalog, says what the board is
called, what is printed on it, how far it has been tried (`stable`, `new` or `experimental`), and, for a part that
differs between boards sold under one name, the `choices` someone makes when a screen of it is built. That is all ESP
Screens needs: New screen and the screen list draw every board from the catalog and the board's own files (the size in
inches from its pixels and density, the touch controller from its `touchscreen:`, a touch calibration on the first
start from `features/resistive-touch.yaml`), so no board is written into the editor or its translations. After a
change to its board file, run `tools/generate_cells.py` and `tools/generate_board_shapes.py` again, and
`tools/check.sh --all --render`, which from then on checks, compiles and renders it with the others.
