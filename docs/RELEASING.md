# Publishing updates without replacing user configuration

## Layout of the code and data

- `main` is the only distribution branch for the app **and all** firmware packages.
  The old Guition branch is no longer updated; all board work goes to main.
- `screen_manager/config.yaml` holds the app version. Bump it on every app release.
  A Git push alone isn't enough to offer an existing app an update.
- The app image contains only code (and the CHANGELOG, for the Update badge's What's new). Layouts live in `/data/screens.json`
  (`version: 2`, `screens: {...}` since 0.3.0). An update/rebuild preserves this volume data.
  Version 1 is backed up and migrated per screen when its source grid is known; see [Pages](PAGES.md).
- The device's own ESPHome YAML contains the name, Wi-Fi references, and unique API/OTA keys.
  Shared packages contain no secrets, fixed owner entities, or Wi-Fi.
- CYD calibration lives in ESP32 preferences. Preserve the preference key, structure,
  and partition layout, or write an explicit migration.
- Firmware 0.3.0 uses only protocol `v: 2`. The add-on retains a wire adapter for older screens.
  Firmware updated before its add-on shows an update message; matching versions activate automatically.
  A changed storage version must get a tested migration with a backup.
  The app refuses unknown versions instead of overwriting the data blank.

## For every release

1. Update `packages/core.yaml` (shared by every board), the board files under `packages/boards/` and the
   shared components; docs/PROFILES.md says what goes where. `python3 tools/check_packages.py` checks that the
   boards define every name the core uses (tools/check.sh runs it).
   The editor is the Vue app in `web/`: after a change under `web/src`, run
   `cd web && npm ci && npm test && npm run check && npm run build` and commit
   `screen_manager/app/static` with it (that folder is the build output; never edit it by hand).
2. Run `tools/check.sh` (with `PYTHON=.venv-portal/bin/python` on a development machine). It runs all
   Python tests with aiohttp, PyYAML, Pillow, fontTools and jinja2 installed, every `tests/*.cpp` with
   `clang++ -std=c++17 -Wall -Wextra -Werror -I.`, `tools/check_packages.py`, `tools/generate_icons.py --check`, and the editor's
   `npm ci`, `npm test`, `npm run check` and `npm run build`, and fails when that fresh build differs from the
   `screen_manager/app/static` in Git (committed or staged). For a firmware change, `tools/check.sh --firmware --affected`
   compiles the boards the change reaches with placeholder secrets from a temporary folder (never the real
   `secrets.yaml`) and applies the flash budget below. A change that reaches one board or a few builds only those
   (docs/BOARD_RELEASES.md); one that reaches every board builds the sample in `tools/profiles.py`
   `SAMPLE` (the CYD and the Guition always, plus boards that differ in chip, flash layout, glass or hardware): with the list of
   boards growing, a full build of every board is kept for when a change needs it (`--firmware` alone, or
   `--affected --every-board`). `--sample` builds the sample directly. `tools/check.sh --render` builds every board as a program for
   this computer (tools/render/run.py, needs SDL2; `--render --sample` uses `RENDER_SAMPLE`): its self test must pass lying down and standing up, and it saves
   what every board draws under `.esphome/render/out`. Run it by hand when a change reaches what a screen draws; CI does
   not run it (a run took up to four hours, and the next push nearly always cancelled it). What the renders were mostly
   for, whether cards fit, is checked on every run without drawing: tests/test_layout_audit.py lays out every type of
   the tile catalogue with each of its faces and control sets, in every size, on every board, through the firmware
   preview, and checks where every object and text ended up and that no control shrinks below its type's touch floor.
   A new catalogue type fails it until it has a case (or a reason it has none); what the firmware does today that the
   checks would flag is listed in its `KNOWN` and `TOUCH_FLOORS` with the code behind it. Without Node or the preview
   it is skipped on a laptop and fails in CI, and a preview older than the firmware sources fails everywhere.
   **Firmware preview.** The editor's preview is the shared firmware compiled to WebAssembly (web/wasm/README.md), and
   `tools/check.sh` fails when it is older than the firmware sources, which every firmware number bump makes it. Push a
   firmware change to its own branch first: `.github/workflows/preview.yml` rebuilds the preview there and commits it
   (a few minutes); pull that commit, then push to main. Locally, `sh web/wasm/build.sh` with Emscripten does the same.
   docs/TESTING.md describes the levels of testing, up to the whole chain through a real Home Assistant. Compile sequentially: profiles with the same `DEVICE_NAME` share one build folder,
   and a parallel build can make an upload pick the wrong `firmware.bin` (the check builds are called `check-<board>` and
   build under `.esphome/check`, apart from the profiles of real screens). Check that no secrets are in Git.

   **Flash budget of the CYD and every 4 MB board** (app 0.2.78). The CYD has 4 MB of flash and two update slots of
   2,031,616 bytes since it builds with the wide partition table (app 0.4.56, docs/FLASH_LAYOUT.md); with ESPHome's
   own table they were 1,835,008 bytes. A screen that still has that table gets the wide one after an update, and a
   firmware that no longer fits its old slot reaches it over a bridge, so the budget goes by the wide slot. The
   Guition's 16 MB leave it far from any limit. The same budget holds for every board with 4 MB
   of flash (`flash_mb` in tools/profiles.py: the CYD, its ILI9342 variant `cyd9342` and the Hosyond 4.0-inch
   `hosyond40`), and `tools/check.sh --firmware` applies it to each one it builds. A change that reaches every board
   builds the sample, which has the CYD only: the other two share its chip, code and look and sit within a few KB of
   it, so the nightly build of every board gates them, and when the CYD is over 90 % the check warns until they are
   built too (`tools/check.sh --firmware --board cyd9342 --board hosyond40`). Measure the CYD on the build users get: the YAML
   `core.installation_yaml()` writes has the Wi-Fi fallback access point (`wifi: ap:`) and `captive_portal:` only on a
   board with more than 4 MB of flash (`hotspot` in boards.json, app 0.4.5+). On the CYD they cost 97 KB (1,720,768
   against 1,623,552 bytes with ESPHome 2026.9), so a screen of a 4 MB board is written without them, and the manager
   takes them out of an older screen's YAML before it builds (`Firmware.drop_hotspot`). The checkout profiles follow
   the same flag (tools/generate_entries.py), and `tools/check.sh --firmware` refuses one that doesn't, so it measures
   that shape; it reads the slot from the build's `partitions.csv` (`app0`, `ota_0`) and the image from
   `firmware.ota.bin`, and `--baseline <bytes>` prints the delta against the last release. A check build without the shape users get reads
   low: at 0.2.72 one without the hotspot read 1,453,647 bytes (79.2 %) where the user-shaped build was 1,538,032
   bytes (83.8 %). Build with the add-on's pinned ESPHome (`screen_manager/Dockerfile`)
   and, when the ESPHome Device Builder ships a newer ESPHome, with that one too (`ESPHOME=<its esphome command>`),
   because users build their updates there.

   | Image of a 4 MB board, share of its 2,031,616-byte slot | Rule |
   |---|---|
   | up to 90 % | normal |
   | 90-93 % | tight: every release states its flash delta; a delta over 8 KB needs a matching saving or the maintainer's explicit OK |
   | 93-97 % | only fixes ship |
   | over 97 % | never: that keeps about 60 KB for ESPHome upgrades and users' own overrides |

   **The Xtensa literal range** (app 0.3.8). On the ESP32 and the ESP32-S3 an `l32r` instruction loads a constant
   from at most 256 KB back, and ESP-IDF puts a function's literals in front of the code that follows them. Every
   header of the component compiles into `main.cpp`, so growing code there can push a function out of reach. The build
   then fails at the link step with `dangerous relocation: l32r: literal target out of range`, often on an S3 board
   while the CYD still links. The fix is its own compilation unit for a large part (the protocol parser has lived in
   `components/smart_display/page_receiver.cpp` since 0.3.8), not a global compiler flag. To see the margin, compare
   in a build's `.map` the address of a function's `.literal.<name>` with the end of its `.text.<name>`: 0.3.8 left
   about 14 KB on the S3 boards and 66 KB on the CYD. The ESP32-P4 is RISC-V and has no such limit.
3. Test app start, saving, restarting/updating with existing layouts,
   reconnecting to HA, and an ESP restart. Test a new card on real
   hardware. A good build doesn't replace physical touch acceptance.
4. Bump the app version and, for a firmware change, the firmware number; write the CHANGELOG and concrete
   test results. Which firmware number goes where depends on the boards the change reaches: the shared one in
   `packages/core.yaml` and `FIRMWARE_VERSION`, or a board file's own for a fix for that board alone.
   `tools/affected_boards.py` prints the number and the heading, and docs/BOARD_RELEASES.md is the recipe.
   Only publish compatible changes directly to main. `tests/test_release_lint.py`
   (part of `tools/check.sh`) holds `config.yaml`'s version, the first CHANGELOG heading and the
   firmware it names, keeps the CHANGELOG headings unique and newest first, holds the firmware numbers to core and
   board (a shared release the next X.Y.0, a board fix a revision on it), and checks that every `fonts/...` file the packages fetch from GitHub is in the tree.
5. Commit and push main (the only release branch). Create an immutable tag
   `screens-vX.Y.Z` from the same commit, and a GitHub release on that tag with the release notes in English
   (`gh release create screens-vX.Y.Z --notes-file ...`). Test the remote YAML in an empty folder:
   all components/fonts must be fetchable via GitHub.
6. The user checks the App store for updates and updates Tessera Screen Manager.
   For new screen features: **Update** on the screen in Tessera (or the nightly round); ESPHome Device
   Builder's Install → Wirelessly on the existing device works too.
   The existing YAML stays in place; `refresh: 0s` fetches current code on every build.

## ESPHome versions

Screens build their firmware from the packages on main (`refresh: 0s`), with whatever ESPHome builds them: this
add-on's (`screen_manager/Dockerfile`), an add-on not updated yet, or the owner's ESPHome Device Builder. So a release
uses nothing the packages' `min_version` (in `packages/core.yaml`) lacks, and CI's firmware job builds with both the
add-on's ESPHome and `min_version` to catch a form that is too new. On `min_version` a change that reaches every board
builds the CYD alone (`MIN_VERSION_SAMPLE` in `tools/profiles.py`), plus a board for each changed file the CYD doesn't
build: the shared code is the same on every board. Raise `min_version` only in a release of its own.
Two moves wait for that release: the camera images' `image: - platform: online_image` form (ESPHome 2027.1 drops the
top-level `online_image:`, `packages/features/camera.yaml`), and `ota:` with `encryption:` and the api key in
`core.installation_yaml()` in place of the OTA password. A board that needs a newer ESPHome states its own
`min_version` in its board file; `tools/check.sh` then skips it on an older ESPHome instead of failing.

## Compile caches made ahead

A build in the app compiles some 1,500 files for a board, and all but a few are the same for every screen of that
board: `main.cpp` holds the screen's own name, keys, Wi-Fi and language. `.github/workflows/build-cache.yml` builds
every board each night and on every push that changes `screen_manager/config.yaml` (every release), in the app's own
image (the `FROM` of `screen_manager/Dockerfile`) with the app's own paths, through the app's own `Firmware` class
(`tools/build_cache.py`). Each board's ccache becomes `ccache-<board>-esphome-<version>.tar.gz` on the pre-release
`build-cache`; a board that fails keeps its previous one.

Before a build the app (`screen_manager/app/build_cache.py`) fetches its board's cache when the release has a newer
one than it unpacked last, unpacks it into `/data/idf/ccache` and builds as before. Two ccache options in
`Firmware.build_env` let that cache answer here: `-fmacro-prefix-map`, `-fdebug-prefix-map` and `-DLV_CONF_PATH` stay
out of the hash (they carry the screen's build folder and only map paths), and the compiler is known by its
`--version` instead of its file date. Without them a cache made elsewhere answers none of the compiles.

- It only ever adds speed. No cache for the board or this ESPHome, no network, a download past five minutes
  (`build_cache.TIME_LIMIT`) or a broken file: the build runs as before. ccache answers a compile only for its exact
  inputs, so a stale cache costs time and never changes the firmware.
- `ESP_SCREENS_BUILD_CACHE` points the app at another release list (a local test) or turns the fetch off (`off`,
  which the tests and `tools/build_cache.py` set).
- The ESPHome Device Builder builds in its own container with its own cache, so its builds don't get this.
- To test locally with Docker: `docker build -t esp-screens:test screen_manager`, then
  `docker run --rm -v "$PWD":/repo:ro -v /tmp/out:/out esp-screens:test python3 /repo/tools/build_cache.py cyd /out`
  makes the cache GitHub would. Serve it next to a JSON file shaped like GitHub's release (`assets` with `name`,
  `updated_at`, `size` and `browser_download_url`) and build in a second container with an empty `/data` and
  `ESP_SCREENS_BUILD_CACHE` set to that file's URL.

## Small rules

- Images in `screen_manager/README.md` (the App store description) use absolute
  `https://raw.githubusercontent.com/...` URLs: the App store does not resolve relative paths.
- A change to README.md, README_EXTENDED.md or `docs/` alone may go to main without a version bump: Home Assistant
  installs nothing new for it, and `tools/affected_boards.py` reports no firmware change.

## Local development

Editor experiments are controlled separately from the development HTTP server. Set
`SCREEN_EDITOR_ENV=development` on the add-on process and restart it to expose
experimental editor features. Omit the variable for the normal editor. No feature
is experimental at the moment; taller tiles became standard in 0.3.1. The server advertises named flags in
`inventory.editor_features`; future editor experiments can add flags there.
This variable does not change authentication, networking, storage or firmware.
Do not set it in the distributed Dockerfile. `SCREEN_DEV` continues to control
the local development server independently.

Copy only `screen_manager/` to the shared `addons/esp_screen_manager/`.
Reload the App store, install the local version, and rebuild after code changes.
A local test version has a different add-on identity than the GitHub version; the
data doesn't move over automatically. For the final installation, test the
GitHub version and turn off the local version to avoid two writers.

For backend tests on a development machine:

```sh
python3 -m venv .venv-portal
.venv-portal/bin/pip install aiohttp PyYAML Pillow fonttools jinja2
.venv-portal/bin/python -m unittest discover -s tests
```

For the editor (`web/`, Vue 3 + Vite + TypeScript): `cd web && npm ci`, then `npm run dev` serves
http://localhost:5173 with hot reload and proxies `/api` to a server on 127.0.0.1:8099 (SCREEN_DEV or a demo
home). `npm test` runs the Vitest suite in `web/tests` (grid and top bar rules, the store, the components in jsdom),
`npm run check` type-checks, `npm run build` writes the page into `screen_manager/app/static`
(clearing `assets/` first). Vite names every file after a hash of its content, which is what keeps a browser
from combining an old script with a new page; `server.py` serves `index.html` as built and `/assets/`.
Everything the page asks for is a relative URL (`api/...`, `./assets/...`), so it works under Home
Assistant's ingress path as well as on a bare localhost. The Python tests read the source through
`tests/editor_sources.py`.

A temporary development server supports `SCREEN_DEV=1`, `HA_API` (ending in
`/api`), `HA_TOKEN_FILE`, and `SCREEN_DATA`. It only binds on localhost. Never put a
token in source code, URLs, or Git. Production uses Supervisor and only accepts
the Ingress proxy address; there is no additional public port.
