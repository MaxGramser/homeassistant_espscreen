## Easy Setup and releases

The preferred route for new users is docs/EASY_SETUP.md: ESP Screen Manager
plus remote ESPHome packages. No token or blueprint needed. Tiles live in the
persistent add-on data; Wi-Fi/API/OTA stay in the device's own ESPHome YAML. Read
docs/RELEASING.md before publishing updates. Main distributes every board in tools/profiles.py.
Every push to GitHub is a release: always also bump the add-on version in
screen_manager/config.yaml (with a CHANGELOG line), otherwise HA won't see an update.
The firmware number is core and board (from shared firmware 0.4.0; 0.3.10 was the last of the old count, and
`tools/firmware_count.py` holds the rule): X.Y.Z with Y the core (a shared release is the next X.Y.0)
and Z a board's revision on it (a fix for one board alone is X.Y.1, X.Y.2 in that board file only). Before any
release run `tools/affected_boards.py`, which says whether the change reaches no screen, a new board, one or a few
boards, or every board, and prints the number, the CHANGELOG heading and the checks. A new board takes no firmware
number and makes no screen update; a board fix makes only that board's screens update and builds only that board
(`tools/check.sh --firmware --affected`). docs/BOARD_RELEASES.md is the recipe.
A screen's YAML is packages/core.yaml (shared by every board) plus one file under packages/boards/;
packages/<board>.yaml and the two profiles in the root only include them. Read docs/PROFILES.md before
touching them: a board-dependent number is a `${NAME}` in the board file, board-only code inside a shared
lambda is a hook substitution there, and `tools/check_packages.py` (run by tools/check.sh) keeps the boards
complete.
A screen gets its tiles from the add-on while it runs: every card works in every cell of every page
(one tile per cell, at most eight pages and 64 tiles, firmware 0.2.62+; the board's grid decides how many,
docs/RESPONSIVE.md), and no Home Assistant entity belongs in a board profile.
Preserve the data schema, protocol compatibility, unique keys, and CYD preferences.
Test updates against existing data. Don't publish an unknown storage version without
a migration. Production Ingress needs no long-lived token or public port.

## Guition board

The Guition 4848S040 has its own board file `packages/boards/guition-4848s040.yaml` with
480×480, ST7701S RGB, and GT911 (`guition-4848s040.yaml` in the root only includes it). Read
docs/GUITION.md. Don't carry over the CYD layout or the XPT2046 calibration.
Verify touch with tools/verify_gt911.py and keep the CYD regressions green.
Don't configure wallbox relays as part of display support.

# Working instructions for LLMs and developers

This project drives the boards in tools/profiles.py: the CYD ESP32-2432S028 with ILI9341 + XPT2046 (320×240,
LVGL 90°, two columns of three), the Guition above (480×480, two by three) and the Waveshare ESP32-S3-Touch-LCD-4.3
(800×480, three by three, `packages/boards/waveshare-esp32s3-43.yaml`). A board file holds hardware and sizes;
behaviour lives once, in packages/core.yaml or components/smart_display (docs/RESPONSIVE.md, docs/ADDING_A_BOARD.md).
Read README.md, README_EXTENDED.md and docs/ before installing. The owner can
physically tap; an agent cannot replace that with software coordinates.

## Installing a new screen

1. Install it from ESP Screens (docs/EASY_SETUP.md): the add-on writes the screen's
   own ESPHome YAML with its name, Wi-Fi reference and unique keys, and flashes it
   over USB. Identify the USB port and board variant first, and check whether a
   profile for this screen already exists; never overwrite a working one.
   The add-on builds with ESPHome 2026.9.0 (`screen_manager/Dockerfile`, Python 3.12-3.14); the packages also build with
   their `min_version` (2026.6.2). Don't show keys in logs or chat.
2. CYD: the screen shows its calibration on first boot; the owner taps the
   crosshairs. `tools/calibrate.py` with docs/CALIBRATING.md is the USB route for a
   panel that needs measuring; ask for physical taps per target, and wait for
   confirmation that the measurement screen is visible. A successful build is not a flash.
   Guition: GT911 reports pixels; verify with tools/verify_gt911.py, no ADC calibration.
3. Pair with the owner's own Home Assistant through the ESPHome integration.
   Read real entity IDs and supported attributes; don't make up entities.
4. Choose the tiles in ESP Screens. Don't test real device actions without the
   owner's permission, and report which checks were actually carried out,
   the limitations, and how long the screen stayed up.

## Writing README and docs text

README.md, README_EXTENDED.md and everything under docs/ ships to production and is
public: people across the open source community read it. Write plain English, not Dutch.
Never quote the owner or anyone else, in any language. Don't name the owner, or use names,
IPs, entity ids, or other strings tied to one person's setup; use generic examples instead.
Don't use em dashes; write a plain comma, period, or "and"/"but" instead.

## Replying to issues and pull requests

A reply on GitHub goes out under the project owner's own account, so every comment on an issue or
a pull request ends with the same signature: a blank line, a `---` rule, and two italic lines, each its
own paragraph.

```
---

_Got a screen running? Tell others which board you have and what works on the [Tessera website](https://tessera-maxgramser.on-forge.com/community/share?type=installation). It helps everyone pick a screen that works._

_Like my work? Consider [buying me a coffee](https://buymeacoffee.com/f5j9jnkmhpv), much appreciated!_
```

When the thread is about one board, append `&board=<key>` to that link, with the board's key from
boards.yaml (`cyd`, `guition`, `waveshare43`, ...): the website uses the same keys and opens the
report for that board. Keep the blank line above the `---`. Without it, markdown reads the rule as underlining and turns the
last line of the reply into a heading instead of drawing a separator. The signature belongs under
comments only, never in commit messages, release notes, the README or the docs, where the button
under the title already does this.

## Owner's machine

On the owner's machine, git-ignored `.esphome/owner-access.md` says how to reach his Home Assistant
and screens for lookups and tests. If that file is missing you are not on his machine: ask, don't guess.

## Code and regressions

- The page-owned layout release deliberately replaces the old firmware decoder.
  Future protocol extensions must be negotiated, as with `tile_sizes`, rather
  than requiring another protocol break. Keep legacy delivery in the add-on,
  never as a second configuration or decoder on the screen.
- Keep the shared UI in `packages/core.yaml` and a board's hardware and sizes in its file under
  `packages/boards/`; the cards of a board's grid are `packages/cells/<count>.yaml`, written by
  `tools/generate_cells.py`, and what the add-on knows of a board is `screen_manager/app/boards.json`, written by
  `tools/generate_board_shapes.py` (both checked by tools/check.sh). Personal data belongs in the gitignored local
  profiles. A size decision in C++ goes through `ui::px()`/`ui::mm()` and the class through `ui::large()`, never
  through a pixel count of the glass or a board's name.
- The editor is `web/` (Vue 3 + Vite, TypeScript; app 0.2.73+). `screen_manager/app/static` is its build
  output: change `web/src`, run `cd web && npm test && npm run build`, and commit both. Keep every URL the page asks for
  relative (`api/...`), so it works behind Home Assistant's ingress path. Tests read the source through
  `tests/editor_sources.py`; docs/RELEASING.md "Local development" has the dev-server recipe.
- Colours live in one table: `components/smart_display/theme.h` (firmware 0.2.54+). Every role has a
  light and a dark value, board profiles name paints (`styles: paint_card`) instead of writing a colour,
  and firmware code asks for a role (`theme::color(theme::INK)`). Never write a hex colour in a profile or
  another header; docs/THEME.md is the recipe, tests/test_theme.py and tests/test_theme.cpp guard it.
- Screen settings live in one table: `components/smart_display/settings_screen.h` draws the
  page on the screen, `SETTING_RULES` in the add-on validates the same keys. Firmware 0.2.49+
  owns them: every writer (the page, the entities in `packages/core.yaml`) goes through
  `settings_screen::set()`, and the add-on changes them through the entities in
  `SETTING_ENTITIES`, never through the layout message. docs/SETTINGS.md is the end-to-end
  recipe for adding one; never widen the eleven-key `settings` block older firmware insists on.
- Pages kept whole, pages prepared ahead and pictures kept until they change (firmware 0.3.2+) follow
  docs/KEPT_PAGES.md: a card is drawn only while it is on the glass, a card set is exchanged whole, and what a kept page
  lacks follows from change numbers (`kept_pages::Changes`), never from flags handed around. Never walk the PSRAM heap
  (`heap_caps_get_largest_free_block`, `heap_caps_get_info`) while an RGB panel is lit: it shifts a frame.
- Preserve fixed pages, hidden navigation at six tiles or fewer, and a
  minimum default standby of 600 seconds. Don't reintroduce free scrolling
  without physically testing for touch/navigation regressions.
- Preserve the touch filter and event guard before actions; calibration processes
  filtered physical ADC values. Don't apply the affine correction twice, in both the driver and the UI.
- The calibration wizard assumes swap_xy=false, mirror_x=true, mirror_y=false,
  and LVGL 90°. A changed orientation also requires a new projection/tests.
- Run `tools/check.sh` on code changes (the Python tests, every C++ test, the package check, the icon
  generator's check, the editor's tests, types and build); on a firmware change also `tools/check.sh --firmware`, which
  compiles every board and applies the CYD's flash budget (docs/RELEASING.md step 2); a change that reaches one board
  or a few builds only those with `tools/check.sh --firmware --affected` (docs/BOARD_RELEASES.md). CI runs the
  same script. Firmware tests and hardware acceptance are different checks.
- `diagnostics/run_ui_test.py` renders without HA actions; don't touch the screen
  during that test. Use `--name` for the expected device identity.
  `diagnostics/send_layout.py` pushes a demo layout with every card type to a
  screen via the API inbox (no HA actions); the manager restores the real
  layout within ~25 s. Guition: `capture_ui.py` saves the LVGL render as a PNG.
  Without a screen: `tools/render_topbar.py` renders the real top-bar code for both
  boards via the ESPHome host + SDL2 to `.esphome/render-topbar/out/sheet.png`.
- Share through Git. Don't stage secrets, measurements, binaries, logs, build
  caches, or local device profiles.
- No automatic firmware upload to an arbitrary connected port.
  With multiple boards, first determine the intended port.
- Profiles with the same `DEVICE_NAME` share `.esphome/build/<name>`.
  Never compile or upload them concurrently; check
  the `firmware.bin` path in the upload log, and then the compile time via
  `device_info`. A wrong profile knocks the screen out of ESP Screen Manager.

Historical diagnostics are background context, not proof that a new panel
works correctly. During onboarding, don't make claims about physical tests that weren't actually performed.
