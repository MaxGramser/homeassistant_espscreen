"""What the preview and a plugin's module are both built with: the pinned sources, the flags, and the number that says
whether a module fits a preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"). build.py builds the preview with it,
build_plugin.py a plugin's module; a module is loaded into the preview's own memory, so the two must agree to the byte."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get('PREVIEW_CACHE', ROOT / '../.cache')).resolve()
LVGL_VERSION = '9.5.0'
ARDUINO_JSON_VERSION = '7.4.3'
# What a plugin's code may include of the core, by ESPHome's path for it (web/wasm/host_include): the plugin API and
# the few headers of ESPHome a tile needs. The number below is taken over these and everything they include.
PLUGIN_HEADERS = ('esphome/components/smart_display/plugin_api.h', 'esphome/core/component.h', 'esphome/core/hal.h',
                  'esphome/core/log.h', 'esphome/core/time.h', 'esphome/core/helpers.h')


def prepare():
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


def lvgl():
    return source('lvgl', LVGL_VERSION, f'https://github.com/lvgl/lvgl/archive/refs/tags/v{LVGL_VERSION}.tar.gz')


def arduino_json():
    if 'ARDUINO_JSON' in os.environ:
        return Path(os.environ['ARDUINO_JSON'])
    return source('ArduinoJson', ARDUINO_JSON_VERSION,
                  f'https://github.com/bblanchon/ArduinoJson/archive/refs/tags/v{ARDUINO_JSON_VERSION}.tar.gz')


def modules():
    spec = importlib.util.spec_from_file_location('smart_display_modules', ROOT / 'components/smart_display/modules.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def defines():
    """The defines of the preview, without the folders: what the code is compiled as."""
    # The most pages, tiles and top bar items any board takes (boards.json, as the add-on's core.PREVIEW_CEILINGS): the
    # preview shows a screen of any board, so it holds what the largest one holds.
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text()).values()
    ceilings = {name: max([shape.get(key, low) for shape in shapes] + [low]) for name, key, low in
                (('PAGES', 'max_pages', 8), ('TILES', 'max_tiles', 64), ('BAR_ITEMS', 'max_bar_items', 6))}
    # The modules the preview is built with (components/smart_display/modules.py, the table's `preview` column).
    table = modules()
    # USE_TESSERA_PLUGINS: the plugin host whole, as on a screen that has a plugin. A plugin's own code comes later, as a
    # module of its own that the browser loads into this one (build_plugin.py).
    # -fvisibility=default: the preview is a main module that a plugin's module links against, and only a visible
    # symbol is one it can find (Emscripten hides them unless the code is compiled for dynamic linking).
    return ['-O2', '-fvisibility=default', '-DESP_SCREEN_HOST', '-DUSE_TESSERA_PLUGINS',
            *[f'-DSCREEN_MAX_{name}={value}' for name, value in ceilings.items()], '-DSCREEN_TEXT_LANGUAGES',
            '-DUSE_API_HOMEASSISTANT_ACTION_RESPONSES',
            *[f'-D{table.MODULES[name]["define"]}' for name in table.preview_modules()], '-DGRID_COLS=8', '-DGRID_ROWS=8',
            '-DLV_CONF_INCLUDE_SIMPLE', '-DLV_FONT_FMT_TXT_LARGE=1']


def includes():
    return [ROOT / 'web/wasm/host_include', ROOT / 'components/smart_display', ROOT / 'web/wasm',
            lvgl(), lvgl() / 'src', arduino_json() / 'src', ROOT / 'components']


def flags():
    return [*defines(), *[f'-I{folder}' for folder in includes()]]


def compiler():
    """The Emscripten the preview is built with, as CI pins it (.github/workflows/preview.yml): another one lays the
    same code out differently, so it is part of the number below."""
    return re.search(r'EMSDK_VERSION:\s*"([^"]+)"', (ROOT / '.github/workflows/preview.yml').read_text())[1]


def check_compiler():
    """Refuses to build with another Emscripten than the pinned one: its modules would carry a number they do not keep."""
    have = subprocess.check_output(['emcc', '--version']).splitlines()[0].decode()
    if f' {compiler()} ' not in f'{have} ':
        raise SystemExit(f'Use Emscripten {compiler()} (emsdk install {compiler()}), as CI does; this is: {have}')


def plugin_abi():
    """The number a plugin's module and a preview must share (16 hex): the compiler, LVGL and ArduinoJson, the defines,
    LVGL's configuration, and every header of the core a plugin can reach through the plugin API, as they are written.
    A module is loaded into the preview's memory and calls straight into it, so a struct that grew or a role that moved
    in theme.h makes an older module wrong without any error; the number makes it unfit instead."""
    folders = [ROOT / 'web/wasm/host_include', ROOT / 'components/smart_display', ROOT / 'web/wasm', ROOT / 'components']
    seen, pending = set(), [ROOT / 'web/wasm/host_include' / name for name in PLUGIN_HEADERS]
    while pending:
        path = pending.pop().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for name in re.findall(r'^\s*#\s*include\s+["<]([^">]+)[">]', path.read_text(errors='replace'), re.M):
            for folder in (path.parent, *folders):
                candidate = (folder / name).resolve()
                if candidate.is_file() and candidate.is_relative_to(ROOT):
                    pending.append(candidate)
                    break
    digest = hashlib.sha256()
    for part in (compiler(), LVGL_VERSION, ARDUINO_JSON_VERSION, ' '.join(defines())):
        digest.update(part.encode() + b'\0')
    for path in sorted(seen | {ROOT / 'web/wasm/lv_conf.h'}):
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()[:16]
