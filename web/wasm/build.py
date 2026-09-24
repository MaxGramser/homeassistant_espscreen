"""Build the browser platform adapter with pinned LVGL/ArduinoJson dependencies."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get('PREVIEW_CACHE', ROOT / '../.cache')).resolve()
CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('EM_CACHE', str(CACHE / 'emscripten'))
os.environ.setdefault('EMSDK_PYTHON', sys.executable)


def source(name, version, url):
    folder = CACHE / f'{name}-{version}'
    if not folder.is_dir():
        archive = CACHE / f'{name}-{version}.tar.gz'
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive) as package:
            package.extractall(CACHE, filter='data')
        if not folder.is_dir():
            raise RuntimeError(f'Archive did not contain {folder.name}')
    return folder


def run(args):
    subprocess.run([str(arg) for arg in args], check=True)


if not shutil.which('em++'):
    raise SystemExit('Emscripten is required; activate emsdk before building the preview.')
lvgl = source('lvgl', '9.5.0', 'https://github.com/lvgl/lvgl/archive/refs/tags/v9.5.0.tar.gz')
arduino = Path(os.environ['ARDUINO_JSON']) if 'ARDUINO_JSON' in os.environ else source(
    'ArduinoJson', '7.4.3', 'https://github.com/bblanchon/ArduinoJson/archive/refs/tags/v7.4.3.tar.gz')
run([sys.executable, ROOT / 'web/wasm/generate_host_ui.py'])
run([sys.executable, ROOT / 'web/wasm/generate_renderer_manifest.py', ROOT])
flags = ['-O2', '-DESP_SCREEN_HOST', '-DUSE_API_HOMEASSISTANT_ACTION_RESPONSES', '-DLIGHT_CONTROLS_TEST', '-DGRID_COLS=8', '-DGRID_ROWS=8',
         '-DLV_CONF_INCLUDE_SIMPLE', '-DLV_FONT_FMT_TXT_LARGE=1']
for folder in (ROOT / 'web/wasm/host_include', ROOT / 'components/smart_display', ROOT / 'web/wasm',
               lvgl, lvgl / 'src', arduino / 'src', ROOT / 'components'):
    flags.append(f'-I{folder}')
key = hashlib.sha256((ROOT / 'web/wasm/lv_conf.h').read_bytes() +
                     subprocess.check_output(['emcc', '--version']) + b'lvgl9.5.0-O2').hexdigest()[:16]
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
for name, filename in [('adapter', 'firmware_preview.cpp'), ('font', 'generated/font.cpp')]:
    obj = objects / f'{name}.o'
    run(['em++', *flags, '-std=c++17', '-c', ROOT / 'web/wasm' / filename, '-o', obj])
    compiled.append(obj)
exports = ['init', 'receive', 'next_action', 'action_response', 'time', 'touch', 'cancel', 'render', 'frame', 'page', 'diagnostics']
import json
out = ROOT / 'web/src/wasm'
out.mkdir(exist_ok=True)
run(['em++', '-O2', *compiled, '-sWASM=1', '-sASSERTIONS=1', '-sSTACK_SIZE=1048576', '-sALLOW_MEMORY_GROWTH=1',
     '-sEXPORTED_FUNCTIONS=' + json.dumps(['_preview_' + name for name in exports]),
     '-sEXPORTED_RUNTIME_METHODS=["ccall","HEAPU8"]', '-sINCOMING_MODULE_JS_API=["wasmBinary","locateFile"]',
     '-sENVIRONMENT=web,node', '-sMODULARIZE=1', '-sEXPORT_ES6=1', '-o', out / 'firmware_preview.js'])
