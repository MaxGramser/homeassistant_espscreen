"""Generate the editor's validation choices from the add-on's authoritative tables."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import (DOMAINS, HEADER_ONLY_DOMAINS, CAMERA_DOMAINS, HEADER_BUILTIN,
                  HEADER_CONTENTS, HEADER_SHOWS, WIFI_CONTENTS, WIFI_SHOWS, BATTERY_CONTENTS, BATTERY_SHOWS, PLUGIN_ITEM_CONTENTS,
                  DISPLAYS, WIDE_ONLY, CONTROLS,
                  TILE_BACKGROUNDS, LIVE_REFRESH, PICTURE_OPTIONS, KEY_HOLDERS, KEY_DOMAINS, BUILTIN,
                  FAVORITE_SHUFFLES, FAVORITE_REPEATS, ENERGY_FLOWS, ENERGY_PERIODS)
from tile_icons import ICONS
import calendar_feed
import meter


def rules():
    return {'domains': sorted(DOMAINS - {'screen'}),
            'headerDomains': sorted((DOMAINS - {'screen'} - CAMERA_DOMAINS) | HEADER_ONLY_DOMAINS),
            'headerBuiltin': list(HEADER_BUILTIN), 'headerContents': list(HEADER_CONTENTS),
            'headerShows': list(HEADER_SHOWS),
            # The screen's own items (firmware 0.38.0): the link takes nothing, Wi-Fi what it shows and when.
            'headerLink': 'link', 'headerWifi': 'wifi', 'wifiContents': list(WIFI_CONTENTS), 'wifiShows': list(WIFI_SHOWS),
            # And its battery (firmware 0.41.0): the percentage beside its icon or not, and always or only while low.
            'headerBattery': 'battery', 'batteryContents': list(BATTERY_CONTENTS), 'batteryShows': list(BATTERY_SHOWS),
            # A plugin's item (plugin API 0.8): its icon and words, or its icon alone.
            'pluginContents': list(PLUGIN_ITEM_CONTENTS),
            'displays': DISPLAYS, 'wideOnly': list(WIDE_ONLY),
            'controls': {domain: [key for key, _ in values] for domain, values in CONTROLS.items()},
            'backgrounds': list(TILE_BACKGROUNDS), 'refresh': list(LIVE_REFRESH),
            'picture': {key: list(values) for key, values in PICTURE_OPTIONS.items()}, 'icons': sorted(ICONS),
            # The built-in cards of a page document (content.name) and the tiles that hold keys, with how many.
            'builtins': sorted(entity[7:] for entity in BUILTIN if not entity.startswith('screen.page_')),
            'keyHolders': KEY_HOLDERS, 'keyDomains': sorted(KEY_DOMAINS),
            # A favourite's own shuffle and repeat (app 0.4.84).
            'favoriteShuffles': list(FAVORITE_SHUFFLES), 'favoriteRepeats': list(FAVORITE_REPEATS),
            # How the energy card shows power along a line, the first the default.
            'energyFlow': list(ENERGY_FLOWS),
            # What it shows: the power now (the default) or the energy of a period.
            'energyPeriod': list(ENERGY_PERIODS),
            # A calendar card's choices (firmware 0.56.0, calendar_feed.validate): what it shows, the view its full
            # screen opens on, how many calendars and words it takes and how far it looks, each first or default the one
            # never stored.
            'calendar': {'styles': list(calendar_feed.STYLES), 'startViews': list(calendar_feed.START_VIEWS),
                         'calendars': calendar_feed.MAX_CALENDARS - 1, 'words': calendar_feed.MAX_WORDS,
                         'ahead': [calendar_feed.AHEAD_DEFAULT, calendar_feed.AHEAD_MAX],
                         'weekStarts': list(calendar_feed.WEEK_STARTS), 'bookText': calendar_feed.BOOK_TEXT},
            # A sensor's meter (firmware 0.56.0, meter.validate): its looks, how many colours, the colours a segment may
            # have (Home Assistant's, by name) and the ones each count starts with, and where the thresholds start.
            'meter': {'styles': list(meter.STYLES), 'segments': list(meter.SEGMENTS),
                      'colors': {name: f'#{value:06X}' for name, value in meter.COLORS.items()},
                      'defaultColors': {str(k): list(v) for k, v in meter.DEFAULT_COLORS.items()}, 'shares': list(meter.SHARES)}}


def output():
    return json.dumps(rules(), ensure_ascii=False, indent=2) + '\n'


if __name__ == '__main__':
    path = ROOT / 'web/src/model/page-rules.json'
    if '--check' in sys.argv:
        if not path.exists() or path.read_text() != output():
            sys.exit('Page rules are stale. Run tools/generate_page_rules.py.')
    else:
        path.write_text(output())
