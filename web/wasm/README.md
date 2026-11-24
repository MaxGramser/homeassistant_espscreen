# Firmware preview

The browser runs the repository's `runtime_tiles.h` in WebAssembly with LVGL 9.5.0.
Vue copies its RGBA framebuffer to one canvas and forwards pointer events. It does
not draw cards, icons, forecast columns, page dots or detail screens.

`generate_host_ui.py` takes the shared firmware's fonts, styles, home-page widgets
and cell prototype through ESPHome's code generator. It also builds the actual
ESPHome `font.cpp` font renderer; there is no converted weather-only icon font.
The only platform replacements are display flush, pointer input, time, preferences
and the ESPHome API transport. The preview endpoint uses the manager's regular
`page_delivery.prepare`, `header_message` and `tile_message` functions. The browser
negotiates a protocol 2 session with the real firmware decoder and forwards the
same page transaction and value updates as a physical device.

An ingress event stream subscribes to the draft's tile and top-bar entities on
the manager's existing Home Assistant connection. A state change prompts a fresh
read of those firmware packets, so track changes do not wait for a polling cycle.
The ten-second refresh remains a fallback if the stream is unavailable.

Images use the firmware's `esphome.screen_camera` requests and existing image hooks.
The manager's regular cover/strip preparation supplies the same BMP bytes as for a
device, through authenticated ingress. `generate_image_decoder.py` compiles the
pinned ESPHome BMP decoder with a host RGB565 buffer; LVGL and the firmware place
the image. Browser code only transports bytes, including in the expanded media
player. Track changes and discarded downloads follow the firmware's image lifetime.

Resolution and grid are runtime inputs (160–2560 pixels per axis, 1–8 columns and
rows, at most 64 cells). The preview holds as many pages, tiles and top bar items as the
largest board in `boards.json` (`core.PREVIEW_CEILINGS`, the `SCREEN_MAX_*` flags in `build.py`). Font/style densities come from the shared board catalog,
plus a 254 dpi profile for the 720 × 720 Waveshare ESP32-P4-WIFI6-Touch-LCD-4B design
target. That target is preview-only, not new physical board support. Regenerating
the preview includes newly added catalog densities without new card rendering code.
`web/src/wasm/renderer.json` records the compiled firmware version and profiles.

The editor shows it in two places. The home page draws every screen's saved home page
with its own firmware, without touch, a few frames a second while it is in view. **Preview**
in the layout editor opens the draft being edited in the firmware, to tap, hold and swipe.
A tap reaches Home Assistant only after **Taps control devices** is switched on. A board whose
density or look the compiled preview does not know keeps the editor's drawn mockup.
In both places the firmware draws the screen in the language ESP Screens builds the screens in (Settings -> Language & region)
and in its Dark mode: the preview carries every language's texts and picks one while it runs.

In **New screen → Virtual preview**, choose a name and profile, optionally override
the resolution/grid, then add entities in the regular tile editor and open **Preview**.
Layouts are saved in this browser's local storage. Existing virtual layouts are migrated through the manager's normal
page-document importer. Export a layout before clearing browser data or moving to another browser.
The virtual device enables the firmware's Swipe between pages setting at startup.

## Building

CI rebuilds it: `.github/workflows/preview.yml` runs on every push that touches the firmware
sources, and when `generate_renderer_manifest.py --check` finds the preview stale it builds it
with the pinned Emscripten (`build.sh`), runs its tests (`test.sh`), and lands the result on the
head the branch has by then, with the editor built on that head (`land.py`; docs/RELEASING.md,
"Firmware preview", has the rules). By hand:

Use Python 3.12–3.14 with the ESPHome version pinned in `screen_manager/Dockerfile`,
PyYAML and Jinja2, plus Emscripten on PATH:

```sh
PYTHON=/path/to/venv/bin/python sh web/wasm/build.sh
sh web/wasm/test.sh
cd web
npm test
npm run build
```

`test.sh` is the one list of the preview's tests: a new `test_*.mjs` gets its line there, and
then runs in `tools/check.sh` and in CI's job alike.

The builder downloads pinned LVGL 9.5.0 and ArduinoJson 7.4.3 into `PREVIEW_CACHE`
(default: `../.cache`). `ARDUINO_JSON` can point to an existing ArduinoJson checkout.
No physical board build or private device YAML is needed. Emscripten object caching
includes the compiler version and LVGL configuration. The add-on ships the compiled
assets, so its users do not need a compiler or a host-side rendering container.
Third-party notices ship in `web/public/firmware-preview-licenses.txt`; update
them alongside dependency versions when rebuilding for a newer firmware release.

## A plugin's module

A plugin's own tile is drawn in the preview by the plugin's own code, built into a module the preview loads
(docs/EMULATOR_ARCHITECTURE.md, "Plugins"). With the same Emscripten on PATH and PyYAML:

```sh
python web/wasm/build_plugin.py <plugin folder>            # writes <plugin folder>/.preview/<id>.wasm
python web/wasm/build_plugin.py <plugin folder> --out <file>
node web/wasm/test_plugin_module.mjs                       # the preview probe, built, loaded and read back
```

It prints what it built (`{id, version, api, abi, file, bytes}`), or one sentence and exit 2 when the plugin has
nothing a browser can run. A module fits the preview whose number (`abi`) it carries, which is `plugin_abi` in
`web/src/wasm/renderer.json`; a plugin in a test folder beside the ESPHome folder (`tessera-plugins/<id>/`) is shown
by its own code in the editor as soon as its `.preview/<id>.wasm` is there.

The source manifest and runtime smoke test reject stale WASM artifacts. Tests execute
the actual binary, checking tile placement, full-width forecast, colour differences,
forward/back navigation, framebuffer restoration, and firmware edge swipes.

## Current limits

The preview reads live Home Assistant data and relays firmware service calls to the
Home Assistant connected to Screen Manager. Its normal action responses and updated
entity states drive the firmware's confirmation/refusal behaviour. Taps can therefore
operate real devices connected to that instance.

Hold the preview's title bar for 1.5 seconds to open the firmware's Settings menu. Its fonts, hold geometry,
rows and navigation come from the firmware. The selected panel's core settings and board Extras are supplied
through the existing settings APIs. Extras use server-sent events, including the initial and reconnect snapshots;
there is no settings polling. Enable **Taps control devices** to change those settings on the physical panel.
With it off, core settings can be tried locally and hardware Extras are read-only. Virtual screens have no
hardware Extras. Restart and calibration are not offered in the browser.

Hardware, device preferences stored inside WASM, non-image ESPHome event requests
(history/options) and custom actions with data templates are not emulated. Text and fractional-number Extras
are read-only. A plugin's tiles, cards and settings rows are there for the plugins whose module the preview has; a
plugin that needs hardware, or whose `plugin.yaml` makes ESPHome entities of its own, has none. Runtime
detail screens such as the weather card are firmware-rendered; board/YAML-specific
overlays such as the light colour picker are not yet connected. This is a UI runtime,
not an ESP32 CPU or peripheral emulator. Browser speed is not a hardware benchmark.
