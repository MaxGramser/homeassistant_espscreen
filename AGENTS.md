# Working instructions for LLMs and developers

ESP Screens turns ESP32 touch screens into Home Assistant control panels. Four parts, one product:

- **Firmware**: `packages/core.yaml` (the shared UI, every board) plus the C++ in `components/smart_display/`.
- **Boards**: `boards.yaml` is the catalog of every board that ships (key, name, status stable/new/experimental).
  Each board has one file under `packages/boards/` with its hardware and sizes, nothing else.
- **Add-on**: `screen_manager/` (ESP Screen Manager, Python), which stores the tiles and sends them to the screens.
- **Editor**: `web/` (Vue 3 + Vite, TypeScript), which shows a screen while you build its pages.

A screen gets its tiles from the add-on while it runs: every card works in every cell of every page (one tile per
cell, at most eight pages and 64 tiles, or what a board with PSRAM states, with the screen's memory budget deciding how
many a layout takes: docs/TILE_MEMORY.md), the board's grid decides how many fit on a page (docs/RESPONSIVE.md), and no
Home Assistant entity belongs in a board file. docs/README.md lists every doc and says which ones are recipes.

## Where to start for a change

| You want to | Read first | The source of truth |
|---|---|---|
| support a new entity type, or a new control on a tile | docs/CATALOGUE.md | `catalogue/<type>.yaml`, `catalogue/_ha.json` |
| add a screen setting | docs/SETTINGS.md | `settings_screen.h`, `SETTING_RULES` in `screen_manager/app/core.py` |
| add a board | docs/ADDING_A_BOARD.md, then docs/BOARD_RELEASES.md | `boards.yaml`, `packages/boards/<file>.yaml` |
| change sizes, fonts or the grid | docs/RESPONSIVE.md | `ui_scale.h`, `packages/looks/`, `packages/cells/` |
| give a board a battery in the top bar | docs/BATTERY.md | the board's `battery` sensors, `battery_status.h` |
| change how a picture reaches the screen | docs/CAMERA.md | `picture_loader.h`, `picture_fetch.h`, `camera_view.h`, `screen_manager/app/camera_feed.py` |
| change how a screen joins Home Assistant | docs/EASY_SETUP.md, chapter 3 | `screen_manager/app/ha_pairing.py`, Home Assistant's esphome config flow |
| change a colour | docs/THEME.md | `components/smart_display/theme.h` |
| change how pages are kept or prepared | docs/KEPT_PAGES.md, docs/PAGES.md | `kept_pages.h`, `page_protocol.h` |
| make a control show its change before Home Assistant confirms it | docs/OPTIMISTIC.md | `optimistic.h`, `wish()` in `runtime_tiles.h` |
| make a card follow a change without being built again | docs/CARD_PARTS.md | `card_bind()`, `card_shaped()` in `runtime_tiles.h` |
| touch the flash of a board with 4 MB | docs/FLASH_LAYOUT.md | `components/flash_layout/`, `packages/hardware/flash-4mb.yaml` |
| add or change a text | docs/TRANSLATING.md | `screen_manager/translations/en.json` |
| touch the YAML package layers | docs/PROFILES.md | `packages/`, `checkout/` |
| know which test proves what | docs/TESTING.md | `tools/check.sh` |
| release what is on dev | docs/RELEASING.md, docs/BOARD_RELEASES.md | `tools/release.py`, `tools/affected_boards.py` |

Each recipe ends with the list of places a change of that kind touches. Follow it; a check fails on most you forget.

## How the YAML is put together

A screen's entry is `packages/<key>.yaml` (a screen installed from ESP Screens, over GitHub) or `checkout/<key>.yaml`
(a build from a clone). Both are written by `tools/generate_entries.py` from `boards.yaml`: don't edit them. An entry
includes `packages/core.yaml` and the board file. The board file includes its hardware (`packages/hardware/`), its
look (`packages/looks/standard.yaml` or `compact.yaml`, sizes in mm scaled by the glass's density), its features
(`packages/features/`) and the cards of its grid (`packages/cells/<count>.yaml`, written by `tools/generate_cells.py`).
What the add-on and the editor know of a board is `screen_manager/app/boards.json`, written by
`tools/generate_board_shapes.py`. A board-dependent number is a `${NAME}` in the board file, board-only code inside a
shared lambda is a hook substitution there, and `tools/check_packages.py` keeps every board complete. YAML files in the
root of a working copy (`cyd-2432s028.yaml`, `guition-wallbox.yaml`, ...) are git-ignored local profiles of one
person's screens: never edit, build or ship them as if they were the product.

## Rules the code keeps

Most of these are guarded by a test; the test names the doc to read when it fails.

- **Capabilities come from the catalogue.** What a tile of each entity type can do lives in `catalogue/<type>.yaml`,
  generated into the add-on, the editor and the firmware by `tools/generate_catalogue.py`, with Home Assistant's own
  facts read from its source by `tools/read_ha_source.py` into `catalogue/_ha.json`. A type exists only where it has a
  file, and only after the firmware draws it. Never write a capability rule (a feature bit, an allowed control, a
  firmware gate for an option) by hand in the add-on, the editor or the firmware: use the generated constants.
- **Home Assistant is the reference.** Actions, state words, icons, names and feature support follow Home Assistant
  one to one. Read its source (a sparse clone of home-assistant/core or its frontend) before inventing anything.
- **Behaviour lives once.** Shared UI in `packages/core.yaml` and `components/smart_display`; a board file holds
  hardware and sizes only. A size decision in C++ goes through `ui::px()`/`ui::mm()` and the class through
  `ui::large()`, never through a pixel count of the glass or a board's name.
- **A fixed set of fonts.** Every board has the same font ids, sized by its look (docs/RESPONSIVE.md, "Fonts"). A new
  card takes the largest step that fits instead of bringing a size of its own: every font costs flash, and the 4 MB
  boards (the CYD first) are close to their budget.
- **Colours live in one table**, `components/smart_display/theme.h`. Every role has a light and a dark value, board
  files name paints (`styles: paint_card`), firmware code asks for a role (`theme::color(theme::INK)`). Never write a
  hex colour anywhere else; `tests/test_theme.py` holds the few allowed exceptions.
- **Settings live in one table.** `settings_screen.h` draws the settings page and `SETTING_RULES` in the add-on
  validates the same keys. Every writer goes through `settings_screen::set()`, and the add-on changes a setting through
  the entities in `SETTING_ENTITIES`, never through the layout message. Never widen the eleven-key `settings` block
  older firmware insists on.
- **One editor, the firmware's numbers.** The editor's mockup ports the firmware's sizes to TypeScript
  (`web/src/model/`); a parity test compares them with the C++, so change both or the check fails. The WASM preview
  (`web/wasm/`, docs/EMULATOR_ARCHITECTURE.md) is the real firmware code.
- **Compatibility.** Preserve the data schema, protocol compatibility, unique keys and screen preferences. Test updates
  against existing data (`tests/test_compat_0431.py` keeps every layout saved by 0.4.31). Don't publish an unknown
  storage version without a migration. Future protocol extensions are negotiated, as with `tile_sizes`, never another
  protocol break; legacy delivery stays in the add-on, never as a second decoder on the screen.
- **A finger's change shows at once, one way** (docs/OPTIMISTIC.md). A control that changes a value of an entity calls
  `wish()`: the value shows on every tile and card of the entity, the action goes out at once (taps while it is on
  its way fold into one), and Home Assistant's reports, answers and silence square it, by the rules of its own
  frontend. Never write a value into the model before an action, never add a hold or flag of a control's own, and
  never show a value the screen cannot know (a lock's end state, the next track). A card binds the parts that show a
  value and is painted in place, never built again for a change of value (docs/CARD_PARTS.md).
- **Kept pages** (docs/KEPT_PAGES.md): a card is drawn only while it is on the glass, a card set is exchanged whole,
  and what a kept page lacks follows from change numbers (`kept_pages::Changes`), never from flags handed around.
- **Memory.** Never walk the PSRAM heap (`heap_caps_get_largest_free_block`, `heap_caps_get_info`) while an RGB panel
  is lit: it shifts a frame. Pictures share one budget worked out from the board's PSRAM. The firmware check gates the
  flash use of every 4 MB board.
- **Touch and navigation.** Keep fixed pages: the page bar appears only when there is more than one page, and free
  scrolling stays out unless it is tested on real glass. Keep the touch filter and the event guard before actions;
  calibration works on filtered raw values, and the affine correction is applied once, never in both the driver and
  the UI. The default standby is at least 600 seconds.
- **The editor** is `web/src`; `screen_manager/app/static` is its build output: run `cd web && npm test && npm run
  build` and commit both. Keep every URL the page asks for relative (`api/...`) so it works behind ingress.
- Production ingress needs no long-lived token or public port.

## Checks

How much is checked follows the branch (next section): work on dev moves fast and is proven on real screens, a
release is checked fully, once a week. docs/TESTING.md says what each layer proves.

- **On dev the proof is the bench**: the three real boards on the owner's bench Home Assistant and its local app
  (`.esphome/bench/README.md` on the owner's machine). Put the app on it, flash the change to the boards it concerns,
  and have the owner look and tap. Run a single test when that is the quickest way to see a piece of logic work. No
  `tools/check.sh`, no builds of other boards and no renders on dev, and a push to dev starts no CI. After a change
  under `web/src`, `cd web && npm run build` (the app serves that build) and commit `screen_manager/app/static` with it.
- **At a release** (and a hotfix) everything runs, on the commit that goes out: `tools/check.sh`, CI on that commit
  (`tools/release.py ci`: every board on both ESPHome versions), the renders when the release changes what screens
  draw, and the upgrade test on the bench (docs/TESTING.md, "6. The upgrade"). What fails there is fixed in the release.
- `tools/check.sh`: Python and C++ tests, package and generator checks, translations, the editor's tests, types and
  build, the WASM preview tests and the layout audit of every card on every board shape.
- Its firmware builds: `tools/check.sh --firmware --affected` builds the boards a change reaches; a change that reaches
  every board builds `SAMPLE` in `tools/profiles.py` (four boards that differ in chip, flash and glass). On the
  packages' older `min_version` ESPHome the same `--affected` build is the CYD alone (`MIN_VERSION_SAMPLE`), plus a
  board for each changed file the CYD doesn't build. CI builds every board each night on main and at a release. Renders
  use `RENDER_SAMPLE`, the smallest, a middle and the largest glass (`tools/check.sh --render --sample`), by hand.
- A firmware change makes the committed WASM preview stale: CI's preview job rebuilds it after the push to dev and
  commits it there (pull before the next push), or `web/wasm/build.sh` does it locally.
- Firmware tests and hardware acceptance are different checks: report which ones actually ran.

## Branches and releases

Two branches, and the difference between them is the most important rule in this file.

- **dev is where all work goes**: features, fixes, issues, boards, experiments. Commit on dev (or on a branch of your
  own that you merge into dev) and push to `origin dev`. Only testers who ask for it install dev (the `#dev` repository URL,
  docs/RELEASING.md "Testing dev"), and a push reaches them when they rebuild that app or reinstall a screen: it is
  proven on the bench boards first (see Checks). Bump no app version and no firmware number on dev. Anything a user would notice gets a line
  under `## Unreleased` at the top of `screen_manager/CHANGELOG.md` (add the heading when it is missing); the release
  turns that section into its version heading.
- **main is what every user gets**: Home Assistant installs the add-on from it, and every screen builds its firmware
  from its packages. main changes only in a release, a hotfix, or a change to README.md, README_EXTENDED.md or docs/
  alone; after a docs change on main, merge main into dev.
- **A release is explicit.** Prepare or publish one only when the maintainer asks for a release in so many words.
  "Add this", "fix this issue" or "try this" means: on dev, on the bench. When a request could mean either, ask
  whether it is a release or work to test on the bench, before anything goes near main.
- **The release**, about once a week: `tools/release.py` with docs/RELEASING.md, "The release", step by step. It counts
  everything since the last release as one: one app version, one CHANGELOG section, one firmware number, tested as an
  upgrade from main on the bench, and then main moves to that exact commit with its tag and GitHub release.
- **A hotfix** is for something broken for users now: a screen that doesn't start, an add-on that doesn't start, data
  that is lost. Branch from main (`hotfix-<what>`), fix it, release it alone with the same steps, then merge main into
  dev.

`tools/affected_boards.py` says whether the work since main reaches no screen, a new board, some boards or every
board, and prints the firmware number, the CHANGELOG heading and the checks; `tools/release.py prepare` writes them.
The firmware number is X.Y.Z: Y counts the core (a shared release is the next X.Y.0) and Z a board's own revision on
it (`tools/firmware_count.py` holds the rule). A new board takes no firmware number. docs/BOARD_RELEASES.md is the
recipe for the numbers, docs/RELEASING.md for the rest.

## Installing a screen and working with hardware

The preferred route for new users is docs/EASY_SETUP.md: ESP Screen Manager plus remote ESPHome packages, no token or
blueprint. Tiles live in the add-on's data; Wi-Fi, API and OTA stay in the screen's own ESPHome YAML.

1. Install from ESP Screens: the add-on writes the screen's own YAML with its name, Wi-Fi reference and unique keys,
   and flashes it over USB. Identify the USB port and board first, and check whether a profile for this screen
   already exists; never overwrite a working one. The add-on builds with the ESPHome in `screen_manager/Dockerfile`;
   the packages also build with their `min_version` (`packages/core.yaml`). Don't show keys in logs or chat.
2. Touch: a resistive board (the CYD) shows its calibration on first boot and someone taps the crosshairs;
   `tools/calibrate.py` with docs/CALIBRATING.md is the USB route. Capacitive boards report pixels and need none
   (GT911: `tools/verify_gt911.py`). Only a person can tap the glass; an agent cannot replace that with software
   coordinates, and a successful build is not a flash.
3. Home Assistant: the add-on adds a screen whose YAML is in its ESPHome folder to the ESPHome integration by itself
   and allows its actions (`screen_manager/app/ha_pairing.py`, docs/EASY_SETUP.md chapter 3); a screen built elsewhere
   is added by hand. Read real entity ids and attributes; don't make up entities, and don't run real device actions
   without the owner's permission.
4. Per board, docs/<BOARD>.md has the hardware notes. Display support never configures relays or other peripherals
   on the board.

- No automatic firmware upload to an arbitrary connected port: with several boards, first find the intended port.
- Builds with the same `DEVICE_NAME` share `.esphome/build/<name>`: never compile or upload them at the same time.
  Check the `firmware.bin` path in the upload log and the compile time via `device_info`.
- `diagnostics/run_ui_test.py` renders without Home Assistant actions (don't touch the screen meanwhile; `--name` for
  the expected device). `diagnostics/send_layout.py` pushes a demo layout with every card type; the add-on restores the
  real one within about 25 s. `tools/render/run.py` renders the real firmware of a board on the host, without a screen.
- Share through Git. Don't stage secrets, measurements, binaries, logs, build caches or local profiles.
- Historical diagnostics are background, not proof that a new panel works. Never claim a physical test that wasn't
  performed.

## Writing README and docs text

README.md, README_EXTENDED.md and everything under docs/ ship to production and are public: people across the open
source community read them. Write plain English. Never quote the owner or anyone else, in any language. Don't name the
owner, or use names, IPs, MAC addresses, entity ids or other strings tied to one person's setup; use generic examples.
Don't use em dashes; write a plain comma, period, or "and"/"but" instead. docs/ holds current rules and recipes, not
test logs: what a release changed goes in `screen_manager/CHANGELOG.md` and its release notes.

## Replying to issues and pull requests

A fix or a change that is done goes to dev first and reaches users with the next release, about once a week (Branches
and releases). So a reply about it says what was done and how it was tested, and that it comes with the next release,
usually within a week; it names no date and promises nothing that is not built yet. The issue stays open until that
release is out. Then a short reply says which version has it and how to get it (update the app, then the screen's
Update), and the issue is closed: `tools/release.py publish` lists the issues the release's CHANGELOG section names.

A reply on GitHub goes out under the project owner's own account, so every comment on an issue or a pull request ends
with the same signature: a blank line, a `---` rule, and two italic lines, each its own paragraph.

```
---

_Got a screen running? Tell others which board you have and what works on the [Tessera website](https://tessera-maxgramser.on-forge.com/community/share?type=installation). It helps everyone pick a screen that works._

_Want me to keep building? Consider [supporting monthly](https://buymeacoffee.com/f5j9jnkmhpv/membership) or [buying me a coffee](https://buymeacoffee.com/f5j9jnkmhpv), much appreciated!_
```

When the thread is about one board, append `&board=<key>` to that link, with the board's key from boards.yaml (`cyd`,
`guition`, `waveshare43`, ...): the website uses the same keys and opens the report for that board. Keep the blank line
above the `---`. Without it, markdown reads the rule as underlining and turns the last line of the reply into a heading
instead of drawing a separator. The signature belongs under comments only, never in commit messages, release notes,
the README or the docs, where the button under the title already does this.

## Owner's machine

On the owner's machine, git-ignored `.esphome/owner-access.md` says how to reach their Home Assistant and screens for
lookups and tests. If that file is missing you are not on the owner's machine: ask, don't guess.
