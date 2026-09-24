# Firmware preview

The browser runs the repository's `runtime_tiles.h` in WebAssembly with LVGL 9.5.0.
Vue copies its RGBA framebuffer to one canvas and forwards pointer events. It does
not draw cards, icons, forecast columns, page dots or detail screens.

`generate_host_ui.py` takes the shared firmware's fonts, styles, home-page widgets
and cell prototype through ESPHome's code generator. It also builds the actual
ESPHome `font.cpp` font renderer; there is no converted weather-only icon font.
The only platform replacements are display flush, pointer input, time, preferences
and the ESPHome API transport. The preview endpoint uses the manager's regular
`layout_message`, `header_message` and `tile_message` functions.

Resolution and grid are runtime inputs (160–2560 pixels per axis, 1–8 columns and
rows, at most 64 cells). Font/style densities come from the shared board catalog,
plus a 254 dpi profile for the 720 × 720 Waveshare ESP32-P4-WIFI6-Touch-LCD-4B design
target. That target is preview-only, not new physical board support. Regenerating
the preview includes newly added catalog densities without new card rendering code.
`web/src/wasm/renderer.json` records the compiled firmware version and profiles.

In **New screen → Virtual preview**, choose a name and profile, optionally override
the resolution/grid, then add entities in the regular tile editor. **Firmware preview**
opens the canvas; **Tile editor** returns to editing. Layouts are saved in this browser's
local storage. Export a layout before clearing browser data or moving to another browser.

## Building

Use Python 3.12–3.14 with the ESPHome version pinned in `screen_manager/Dockerfile`,
PyYAML and Jinja2, plus Emscripten on PATH:

```sh
PYTHON=/path/to/venv/bin/python sh web/wasm/build.sh
node web/wasm/test_runtime.mjs
node web/wasm/test_profiles.mjs
PREVIEW_WIDTH=720 PREVIEW_HEIGHT=720 PREVIEW_DPI=254 node web/wasm/test_runtime.mjs
PREVIEW_WIDTH=800 PREVIEW_HEIGHT=480 PREVIEW_COLUMNS=3 node web/wasm/test_runtime.mjs
cd web
npm test
npm run build
```

The builder downloads pinned LVGL 9.5.0 and ArduinoJson 7.4.3 into `PREVIEW_CACHE`
(default: `../.cache`). `ARDUINO_JSON` can point to an existing ArduinoJson checkout.
No physical board build or private device YAML is needed. Emscripten object caching
includes the compiler version and LVGL configuration. The add-on ships the compiled
assets, so its users do not need a compiler or a host-side rendering container.
Third-party notices ship in `web/public/firmware-preview-licenses.txt`; update
them alongside dependency versions when rebuilding for a newer firmware release.

The source manifest and runtime smoke test reject stale WASM artifacts. Tests execute
the actual binary, checking tile placement, full-width forecast, colour differences,
forward/back navigation, framebuffer restoration, and firmware edge swipes.

## Current limits

The preview reads live Home Assistant data and relays firmware service calls to the
Home Assistant connected to Screen Manager. Its normal action responses and updated
entity states drive the firmware's confirmation/refusal behaviour. Taps can therefore
operate real devices connected to that instance.

Hardware, persistent device settings, camera/image transport, ESPHome event requests
(history/options/settings) and custom actions with data templates are not emulated. Runtime
detail screens such as the weather card are firmware-rendered; board/YAML-specific
overlays such as the light colour picker are not yet connected. This is a UI runtime,
not an ESP32 CPU or peripheral emulator. Browser speed is not a hardware benchmark.
