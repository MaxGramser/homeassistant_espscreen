"""Generate the editor's validation choices from the add-on's authoritative tables."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import (DOMAINS, HEADER_ONLY_DOMAINS, CAMERA_DOMAINS, HEADER_BUILTIN,
                  HEADER_CONTENTS, HEADER_SHOWS, WIFI_CONTENTS, WIFI_SHOWS, BATTERY_CONTENTS, BATTERY_SHOWS, DISPLAYS, WIDE_ONLY, CONTROLS,
                  TILE_BACKGROUNDS, LIVE_REFRESH, PICTURE_OPTIONS, KEY_HOLDERS, KEY_DOMAINS, BUILTIN,
                  FAVORITE_SHUFFLES, FAVORITE_REPEATS)
from tile_icons import ICONS


def rules():
    return {'domains': sorted(DOMAINS - {'screen'}),
            'headerDomains': sorted((DOMAINS - {'screen'} - CAMERA_DOMAINS) | HEADER_ONLY_DOMAINS),
            'headerBuiltin': list(HEADER_BUILTIN), 'headerContents': list(HEADER_CONTENTS),
            'headerShows': list(HEADER_SHOWS),
            # The screen's own items (firmware 0.38.0): the link takes nothing, Wi-Fi what it shows and when.
            'headerLink': 'link', 'headerWifi': 'wifi', 'wifiContents': list(WIFI_CONTENTS), 'wifiShows': list(WIFI_SHOWS),
            # And its battery (firmware 0.41.0): the percentage beside its icon or not, and always or only while low.
            'headerBattery': 'battery', 'batteryContents': list(BATTERY_CONTENTS), 'batteryShows': list(BATTERY_SHOWS),
            'displays': DISPLAYS, 'wideOnly': list(WIDE_ONLY),
            'controls': {domain: [key for key, _ in values] for domain, values in CONTROLS.items()},
            'backgrounds': list(TILE_BACKGROUNDS), 'refresh': list(LIVE_REFRESH),
            'picture': {key: list(values) for key, values in PICTURE_OPTIONS.items()}, 'icons': sorted(ICONS),
            # The built-in cards of a page document (content.name) and the tiles that hold keys, with how many.
            'builtins': sorted(entity[7:] for entity in BUILTIN if not entity.startswith('screen.page_')),
            'keyHolders': KEY_HOLDERS, 'keyDomains': sorted(KEY_DOMAINS),
            # A favourite's own shuffle and repeat (app 0.4.84).
            'favoriteShuffles': list(FAVORITE_SHUFFLES), 'favoriteRepeats': list(FAVORITE_REPEATS)}


def output():
    return json.dumps(rules(), ensure_ascii=False, indent=2) + '\n'


if __name__ == '__main__':
    path = ROOT / 'web/src/model/page-rules.json'
    if '--check' in sys.argv:
        if not path.exists() or path.read_text() != output():
            sys.exit('Page rules are stale. Run tools/generate_page_rules.py.')
    else:
        path.write_text(output())
