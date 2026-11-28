"""Build the browser platform adapter with pinned LVGL/ArduinoJson dependencies."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolchain
from toolchain import CACHE, ROOT, run

toolchain.prepare()
if not shutil.which('em++'):
    raise SystemExit('Emscripten is required; activate emsdk before building the preview.')
toolchain.check_compiler()
lvgl = toolchain.lvgl()
toolchain.arduino_json()
run([sys.executable, ROOT / 'web/wasm/generate_host_ui.py'])
run([sys.executable, ROOT / 'web/wasm/generate_image_decoder.py'])
run([sys.executable, ROOT / 'web/wasm/generate_renderer_manifest.py', ROOT])
# The flags, the ceilings and the modules the preview is built with: toolchain.py, shared with a plugin's module.
flags = toolchain.flags()
preview_modules = toolchain.modules().preview_modules()
key = hashlib.sha256((ROOT / 'web/wasm/lv_conf.h').read_bytes() +
                     subprocess.check_output(['emcc', '--version']) + b'lvgl9.5.0-O2-visible').hexdigest()[:16]
objects = CACHE / f'wasm-{key}'
objects.mkdir(exist_ok=True)


def compile_c(path):
    obj = objects / (str(path.relative_to(lvgl)).replace('/', '_') + '.o')
    if not obj.exists() or path.stat().st_mtime > obj.stat().st_mtime:
        run(['emcc', *flags, '-c', path, '-o', obj])
    return obj


sources = sorted((lvgl / 'src').rglob('*.c'))
with ThreadPoolExecutor(max_workers=4) as pool:
    compiled = list(pool.map(compile_c, sources))
for name, source_path in [('adapter', ROOT / 'web/wasm/firmware_preview.cpp'),
                          ('font', ROOT / 'web/wasm/generated/font.cpp'),
                          ('bmp_decoder', ROOT / 'web/wasm/generated/image/bmp_decoder.cpp'),
                          ('image_decoder', ROOT / 'web/wasm/generated/image/image_decoder.cpp'),
                          ('receiver', ROOT / 'components/smart_display/page_receiver.cpp'),
                          ('picture_loader', ROOT / 'components/smart_display/picture_loader.cpp'),
                          ('library', ROOT / 'components/smart_display/media_library.cpp'),
                          ('panel', ROOT / 'components/smart_display/tile_panel.cpp'),
                          ('energy', ROOT / 'components/smart_display/energy_view.cpp'),
                          ('calendar', ROOT / 'components/smart_display/calendar_view.cpp'),
                          ('meter', ROOT / 'components/smart_display/meter_view.cpp'),
                          *[(name, ROOT / f'components/smart_display/module_{name}.cpp') for name in preview_modules
                            if (ROOT / f'components/smart_display/module_{name}.cpp').is_file()],
                          ('plugins', ROOT / 'components/smart_display/plugin_host.cpp'),
                          ('hooks', ROOT / 'components/smart_display/screen_hooks.cpp')]:
    obj = objects / f'{name}.o'
    run(['em++', *flags, '-std=c++17', '-c', source_path, '-o', obj])
    compiled.append(obj)
exports = ['init', 'receive', 'next_action', 'action_response', 'time', 'touch', 'cancel', 'render', 'frame', 'page', 'diagnostics', 'layout']
exports += ['next_image', 'image_buffer', 'image_ready', 'pictures', 'card', 'card_builds', 'dark', 'language']
exports += ['settings', 'extras', 'settings_controls', 'next_setting', 'keep_pages']
exports += ['plugin', 'plugin_abi', 'show', 'cards']
out = ROOT / 'web/src/wasm'
out.mkdir(exist_ok=True)
# MAIN_MODULE=1: a main module that keeps every symbol, so a plugin's module finds LVGL, the plugin API and the C++
# library in it, whatever it calls. The browser writes a plugin's module into the preview's own file system (FS) and
# loads it from there (loadDynamicLibrary): the editor fetched the bytes itself, once for every preview on the page.
run(['em++', '-O2', *compiled, '-sWASM=1', '-sASSERTIONS=1', '-sSTACK_SIZE=1048576', '-sALLOW_MEMORY_GROWTH=1',
     '-sMAIN_MODULE=1',
     '-sEXPORTED_FUNCTIONS=' + json.dumps(['_preview_' + name for name in exports]),
     '-sEXPORTED_RUNTIME_METHODS=["ccall","HEAPU8","loadDynamicLibrary","FS"]', '-sINCOMING_MODULE_JS_API=["wasmBinary","locateFile"]',
     '-sENVIRONMENT=web,node', '-sMODULARIZE=1', '-sEXPORT_ES6=1', '-o', out / 'firmware_preview.js'])
