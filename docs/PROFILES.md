# How a screen is put together: the core, looks, features, hardware and boards

A screen's ESPHome configuration is a handful of small files that ESPHome's own
[packages](https://esphome.io/components/packages/) mechanism puts together. Everything a screen does lives once, in
`packages/core.yaml` or in a file every board that needs it includes. A board file is what is left: the board's own
hardware, the facts of its glass, and the list of what it has. A change to how screens behave is made once and reaches
every board; a new board is a short file.

This is the layout since app 0.2.127. Before 0.2.84 each board was one 5,000-line profile; from 0.2.84 to 0.2.126 a
board file was 550 to 720 lines, most of it the same as the other boards' and filled in by copying one and scaling its
numbers.

## The files

| Folder | What a file there holds | Who includes it |
|---|---|---|
| `packages/core.yaml` | Everything every screen shares: the LVGL tree (tiles, cards, overlays, the touch test page), the scripts, the API actions, the entities, the fonts, the globals, the Rotation select. It names no board and no hardware, and gives a default for every value a board may change. | The entry files |
| `packages/looks/` | How big everything is: `standard.yaml` (drawn on the 4-inch Guition at 170 dpi) and `compact.yaml` (drawn on the CYD at 143 dpi). Every size is written at the look's own density and scaled to the board's `DISPLAY_DPI`, so a tile, a letter and a key keep their size in millimetres. | Every board, exactly one |
| `packages/features/` | What a board can do, once for every board that can: `capacitive-touch.yaml` or `resistive-touch.yaml` (how its touch panel is read), `backlight.yaml` (a backlight the firmware dims) and `backlight-always-on.yaml` (one that must never go dark), `camera.yaml` (camera images, needs PSRAM), `self-test.yaml` (the UI self test with its geometry check), `snapshot.yaml` (a picture of the screen over the log). | Board files |
| `packages/hardware/` | Hardware that several boards share: `esp-idf.yaml` (how every firmware is built), `esp32s3-rgb.yaml` (an ESP32-S3 with octal PSRAM driving an RGB panel), `waveshare-ch422g.yaml` (the Waveshare boards whose panel, touch and backlight hang on a CH422G expander). | Board files, and each other |
| `packages/boards/` | One board: its word (`BOARD_ID`), its glass (`PANEL_W`, `PANEL_H`, `DISPLAY_DPI`, `ROTATION_LANDSCAPE`), its grid, its draw buffer, the packages it includes, and its own hardware sections. | The entry files |
| `packages/cells/` | The cards of a grid, one per cell, written by `tools/generate_cells.py`. | Board files |
| `packages/<board>.yaml` | The entry a screen installed from ESP Screens builds from over GitHub. ESP Screen Manager writes every screen's YAML with `files: [packages/<board>.yaml]`, so these names never change. | A screen's own YAML |
| `checkout/<board>.yaml` | The same entry for a build from a clone of this repository (checkout/README.md), with the secrets from `checkout/secrets.yaml` and the components of the checkout. | You |

A board file reads like this (the 4-inch Guition, without its comments):

```yaml
packages:
  build: !include ../hardware/esp-idf.yaml
  cells: !include ../cells/6.yaml
  look: !include ../looks/standard.yaml
  touch: !include ../features/capacitive-touch.yaml
  backlight: !include ../features/backlight.yaml
  camera: !include ../features/camera.yaml
  self_test: !include ../features/self-test.yaml
  snapshot: !include ../features/snapshot.yaml

substitutions:
  BOARD_ID: "guition"
  DEVICE_NAME: "guition-new"
  DEVICE_FRIENDLY_NAME: "My Guition"
  PANEL_W: "480"
  PANEL_H: "480"
  DISPLAY_DPI: "170"
  GRID_COLS: "2"
  GRID_ROWS: "3"
  LVGL_BUFFER_SIZE: "25%"
  BACKLIGHT_FREQUENCY: "20000Hz"

# ... then esp32, psram, logger, the buses, the backlight output, the touch panel and the display
```

## Which value wins

ESPHome merges the files in this order: the core, then the board file's own packages (each one's packages before it),
then the board file, then the entry, then a screen's own YAML and its override file. For a value set in more than one
place, the later one wins:

1. a screen's own YAML and its Override YAML (`<name>.local.yaml`, docs/EASY_SETUP.md);
2. the board file;
3. the board file's packages, a later one over an earlier one (a feature over the look, `backlight-always-on.yaml` over
   `backlight.yaml`);
4. the core's default.

So the core says what holds unless someone says otherwise, a look or a feature says what holds on every board that
has it, and a board file only states what is its own. `tools/check_packages.py` refuses a board file line that
repeats what the board would get anyway: a change to a default then reaches that board too.

A mapping merges key by key. A list of components with ids merges by id: `!extend` adds to a widget, a script or a
component defined anywhere in the chain, and `!remove` takes one away (`backlight-always-on.yaml` removes the
`alert_flash` of `backlight.yaml` and defines its own). Any other list is joined, the earlier file's items first.
A list and a mapping under the same key are not joined: the later one replaces the other whole. That is why a board
file has no `esphome: on_boot:` of its own. The core writes its boot steps as one trigger, and a board's list there
threw all of them away (the Waveshare 4B up to firmware 0.3.9 never took its tiles); `tools/check_packages.py`
refuses it. A step that belongs to one board's hardware goes in that board's own sections, or in a hook.
`esphome config checkout/<board>.yaml` shows the result.

The firmware version is one of these values too. `SCREEN_FIRMWARE_VERSION` in the core is the version every board
builds; a board file may set its own under `BOARD_ID` after a fix for that board alone (the core's 0.4.0 becomes
0.4.1 for that board), and that board then builds and reports its own number (docs/BOARD_RELEASES.md). Only the core
and a board file may set it, and a board's own number keeps the core's X.Y with a higher last number;
`tools/check_packages.py` holds both.

## Sizes: the look works them out

A size is a line in the look, for example:

```yaml
  LOOK_SCALE: ${ (DISPLAY_DPI | float) / 170 }
  TILE_ICON_SIZE: ${ (54 * LOOK_SCALE | float) | round | int }
```

That is 54 px at 170 dpi, scaled to the board's density; ESPHome works the sum out when it reads the file (its Jinja
expressions, in every ESPHome since the packages' `min_version`). A board states `DISPLAY_DPI` with the decimals it has
(diagonal pixels over diagonal inches); the firmware itself takes the nearest whole number.

A board can still state any size itself, and its value wins. Do that only for a size set on the glass, and say why next
to it: a few boards keep a value that was set by hand before this layout existed.

What depends on the canvas is not in the look at all: the firmware measures it at boot on the glass LVGL hands it,
lying down or standing up. The tile area and its cells, the page bar, the strip that opens the settings, and the alert
card (screen_alert::layout, firmware 0.2.103+: the look's card fitted to the glass, its title one line of its font, a
camera picture in the camera's own proportions above the words or on their left, docs/CAMERA.md). ESP Screens sizes
the alert's picture with the same rule (screen_manager/app/alert_layout.py, kept equal to the firmware's by
tests/test_alert_layout.py).

To make something bigger or smaller on every board of a look, change the number in the look.

## Hooks: board code inside a shared lambda

Some of the core's lambdas have a line that differs between boards, for instance what the first boot step does with
the touch panel, or the camera images a board with PSRAM sets up. The core writes a `${NAME}` there, a *hook*, and
gives it a default (empty, or what most boards do). The feature that needs a hook sets it: `features/camera.yaml` sets
`BOOT_CAMERA_HOOKS`, `CLOSE_CARDS_HOOK`, `TICK_HOOK` and the other camera lines; `features/capacitive-touch.yaml` and
`features/resistive-touch.yaml` set `BOOT_TOUCH` and `BOOT_PAGE_GESTURE`; `features/backlight.yaml` sets
`APPLY_BACKLIGHT`. Every screen reads a touch panel and lights a backlight, so those three have no default and a board
without them does not build. A board file would set a hook only for code no other board has; since app 0.2.129 none
does (the CYD used to drive its backlight and run its self test its own way).

Hooks are a stretch of C++ inside a shared lambda because ESPHome cannot merge two lambdas into one. A feature that
needs a step of its own rather than a line inside a shared one brings its own script or automation instead.

## What an override may rely on

An owner's Override YAML hangs on names in these files, and it lives on the owner's own Home Assistant where no test of
ours sees it. These stay, whichever file they move to:

- on every board: `my_display` (the display), `ts_touch` (the touch panel), `gpio_backlight_pwm` (the output that drives
  the backlight) and `back_light` (the light on it); on the Waveshare 4.3 and 7, `backlight_line` as well;
- the substitutions a board offers for its hardware: `DISPLAY_MODEL`, `DISPLAY_DATA_RATE` and `DISPLAY_INVERT_COLORS`
  on the CYD, `BACKLIGHT_FREQUENCY` on the boards with a PWM backlight, and `BACKLIGHT_DIMMABLE`, `LVGL_ROTATION` and the
  `TOUCH_*` values on every board.

The overrides people shared in GitHub issues are kept in `tests/fixtures/overrides/`. `tests/test_overrides.py` keeps
the names they use, and `tools/check.sh --firmware` has ESPHome read each of them on its board, the way a screen's own
YAML loads it.

## Adding a board

docs/ADDING_A_BOARD.md is the whole recipe. In short: `tools/new_board.py` writes the board file from the board that
resembles it most, you replace its hardware sections, add its entry to `boards.yaml` (the catalog New screen is drawn from) and the
entries (`packages/<board>.yaml`, `checkout/<board>.yaml`), and run `tools/generate_cells.py`, `tools/generate_board_shapes.py`
and `tools/check.sh --firmware`. A board that shares a family's hardware includes that family's file under
`packages/hardware/` and states only what differs; a board with hardware like no other keeps it in its own file until
a second board shares it.

A variant of a board that is sold with other parts (a CYD with another display controller, a panel of another size in
the same family) is the same thing: a choice in `boards.yaml`, for a part the board offers a substitution for and people
with that board confirmed (New screen then asks, and writes the value into the screen's own YAML), a line in a
screen's Override YAML for anything else the board offers a substitution for, or a board file of its own that includes
the same hardware and states what differs.

## How this layout was checked

The move to this layout changed no firmware. For every board, through every way a screen is built (a checkout, the
package a screen builds from over GitHub, standing up, and with each override from `tests/fixtures/overrides/`), the
validated configuration of `esphome config` and the C++ that `esphome compile --only-generate` writes were compared with
those of app 0.2.126, with ESPHome 2026.9.0 and the packages' `min_version` 2026.6.2. Every size resolved to the same
number, every component and lambda was the same, and the generated C++ held the same statements. What differs is the
order in which ESPHome registers components and API actions, which follows the order of the files, and the numbers
ESPHome gives what it names itself. docs/TEST_RESULTS_02127.md has the details.
