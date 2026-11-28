#!/bin/sh
# The firmware preview's tests: the one list. tools/check.sh ("Firmware preview: WASM") and the job that rebuilds the
# preview (.github/workflows/preview.yml) both run this file, so a test added here runs in both, and a test that is in
# no line here runs nowhere (tests/test_preview_land.py holds every web/wasm/test_*.mjs against this file).
#
#   sh web/wasm/test.sh
#
# The tests load the built preview (web/src/wasm) in Node; nothing here builds it (web/wasm/build.sh does) or asks
# whether it is older than the firmware sources (web/wasm/generate_renderer_manifest.py --check does).
# PYTHON is the Python a test may start, python3 by default.
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
export PYTHON="${PYTHON:-python3}"
set -x

node web/wasm/test_profiles.mjs
node web/wasm/test_runtime.mjs
node web/wasm/test_card_parts.mjs
node web/wasm/test_card_paint.mjs
node web/wasm/test_card_labels.mjs
node web/wasm/test_page_keys.mjs
node web/wasm/test_quiet_resync.mjs
node web/wasm/test_settings_hold.mjs
node web/wasm/test_settings_tile.mjs
node web/wasm/test_state_look.mjs
node web/wasm/test_binary_words.mjs
node web/wasm/test_tile_icons.mjs
node web/wasm/test_remote_card.mjs
node web/wasm/test_media_library.mjs
node web/wasm/test_history_card.mjs
node web/wasm/test_tile_shapes.mjs
node web/wasm/test_lock_card.mjs
node web/wasm/test_alarm_card.mjs
node web/wasm/test_media_card.mjs
node web/wasm/test_automation_tile.mjs
node web/wasm/test_dark_switch.mjs
node web/wasm/test_cover_card.mjs
node web/wasm/test_page_frame.mjs
node web/wasm/test_look.mjs
node web/wasm/test_colour_card.mjs
node web/wasm/test_light_group_key.mjs
node web/wasm/test_kept_colour.mjs
node web/wasm/test_cover_keys.mjs
node web/wasm/test_top_bar_cards.mjs
node web/wasm/test_weather_detail.mjs
node web/wasm/test_climate_detail.mjs
# The grid a layout brings (firmware 0.53.0+): begin changes it, a card per cell, a grid it does not take refused.
node web/wasm/test_grid.mjs
# The firmware's own Settings page in the preview: hold, Extras, a write only with Taps control devices, Back.
node web/wasm/test_settings.mjs

# Pictures and the runtime again at other glass: a square 720 px at 254 dpi, three columns lying down, standing up.
node web/wasm/test_images.mjs
PREVIEW_WIDTH=720 PREVIEW_HEIGHT=720 PREVIEW_DPI=254 node web/wasm/test_images.mjs
PREVIEW_WIDTH=720 PREVIEW_HEIGHT=720 PREVIEW_DPI=254 node web/wasm/test_runtime.mjs
PREVIEW_WIDTH=800 PREVIEW_HEIGHT=480 PREVIEW_COLUMNS=3 node web/wasm/test_runtime.mjs
PREVIEW_WIDTH=480 PREVIEW_HEIGHT=800 node web/wasm/test_runtime.mjs

# A plugin's own code in the preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"): the preview probe built into a module,
# loaded into the preview and read back. Building the probe needs Emscripten; where em++ is not on the PATH the test
# says so and passes, and the job that rebuilds the preview, which has just used it, runs it whole.
node web/wasm/test_plugin_module.mjs
