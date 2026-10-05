"""The geometry of every card on every glass, without drawing a picture (app 0.4.32).

The firmware's own layout code (runtime_tiles.h with LVGL, built to WebAssembly for the editor's preview) lays out
each card the way a screen does; web/wasm/layout_audit.mjs asks it where every object, text and control ended up
(preview_layout). This test builds the layouts, one card a page, for every board lying down and standing up, every
type of the tile catalogue (catalogue/*.yaml) with each face (`displays`) and control set (`controls`) it offers, every
size the grid takes (the five names and its spans) and a short and a very long name. Each card's message is the one the
app sends a screen (core.state_message with core.extras and drawn_controls), and the checks are what the renders were for:

- nothing leaves its card, and no card leaves the glass or runs into another;
- no two texts of a card lie over each other;
- a text wider than its line has dots or rolls by (a marquee), never a hard cut; a line fits its box's height, and
  wrapped text fits its box;
- a text keeps a margin from its card's edge;
- a control a finger works inside a card keeps its drawn size from shrinking below the floor recorded for its type
  (TOUCH_FLOORS; the rule is ui::touch_min(), 7 mm of glass, components/smart_display/ui_scale.h);
- a full page of cards (every cell a card, and every row one wide card) lays out without one running into another.

The types are read from catalogue/*.yaml: a new type, face or control set fails here until it has a case in KINDS (or
an entry in EXCLUDED with the reason the preview cannot draw it). The checks themselves are tested on made-up reports
below (Checks), so a check that can never fail shows up.

It needs Node and web/src/wasm/firmware_preview.wasm (web/wasm/build.sh). Without them it is skipped on a laptop, loudly,
and fails in CI (the environment variable CI set). A preview older than the firmware sources it was built from fails
everywhere (web/wasm/generate_renderer_manifest.py --check, and the fingerprint inside the binary): checking old code
would pass for the wrong reason. LAYOUT_AUDIT_BOARDS=cyd,guition limits the boards; LAYOUT_AUDIT_OUT=<file> keeps the
raw report; LAYOUT_AUDIT_JOBS=<n> sets how many Node processes run side by side (the CPUs by default).
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
from core import BUILTIN, Grid, drawn_controls, extras, span_of, span_offered, state_message  # noqa: E402

WASM = ROOT / 'web/src/wasm/firmware_preview.wasm'
MANIFEST = ROOT / 'web/wasm/generated/firmware_renderer_manifest.h'
SHORT, LONG = 'Lamp', 'The ceiling light above the long dining table in the back room'
# The moment the preview's clock stands on (web/wasm/layout_audit.mjs, preview_time): timers, forecasts and "last run"
# are written against it, so a card shows what it would on a screen at that moment.
NOW = datetime.fromtimestamp(1789401840, timezone.utc)


def iso(**delta):
    return (NOW + timedelta(**delta)).isoformat()


def forecast():
    conditions = ['sunny', 'partlycloudy', 'rainy', 'cloudy', 'lightning-rainy', 'snowy']
    return [{'datetime': iso(days=i), 'condition': conditions[i], 'temperature': 21 - i, 'templow': 11 + i,
             'precipitation': [0, 0, 4.2, 0.3, 11.5, 2][i], 'precipitation_probability': [5, 20, 80, 30, 95, 60][i]} for i in range(6)]


def hourly():
    return [{'datetime': iso(hours=i), 'condition': ['rainy', 'partlycloudy', 'sunny', 'cloudy'][i % 4], 'temperature': 18.4 + i * 0.6,
             'precipitation': [0.4, 0, 0, 2.1][i % 4], 'precipitation_probability': [70, 10, 0, 85][i % 4]} for i in range(10)]


HISTORY = {'hours': 24, 'values': [round(18 + 4 * ((k * 7) % 11) / 10, 2) if k % 5 else None for k in range(24)]}

# One card of each kind, with what Home Assistant says about it: `entity`, `state` and `attributes` as Home Assistant has
# them; `options` the tile's own choices beside its size; `sizes` where the type takes fewer than every size; `forecast`,
# `hourly` and `history` what the app fetches beside the state. The kind named after a type is that type's case: its
# other faces and control sets (from the catalogue) are laid out from it. The others are states worth a look of their own.
KINDS = {
    'alarm_control_panel': {'entity': 'alarm_control_panel.audit', 'state': 'armed_home',
                            'attributes': {'code_format': 'number', 'code_arm_required': True, 'supported_features': 63,
                                           'changed_by': 'Someone with a remarkably long name'}},
    'automation': {'entity': 'automation.audit', 'state': 'on', 'attributes': {'last_triggered': iso(hours=-2), 'current': 0}},
    'binary_sensor': {'entity': 'binary_sensor.audit', 'state': 'on', 'attributes': {'device_class': 'door'}},
    'button': {'entity': 'button.audit', 'state': iso(hours=-3), 'attributes': {}},
    'camera': {'entity': 'camera.audit', 'state': 'idle', 'attributes': {'supported_features': 2}},
    'climate': {'entity': 'climate.audit', 'state': 'heat',
                'attributes': {'current_temperature': 20.5, 'temperature': 21.5, 'hvac_modes': ['off', 'heat', 'cool', 'auto'],
                               'min_temp': 7, 'max_temp': 35, 'target_temp_step': 0.5, 'supported_features': 385}},
    'climate-range': {'entity': 'climate.range', 'state': 'heat_cool',
                      'attributes': {'current_temperature': 73, 'target_temp_low': 70, 'target_temp_high': 75, 'target_temp_step': 1,
                                     'hvac_modes': ['off', 'heat_cool', 'cool'], 'min_temp': 45, 'max_temp': 95, 'supported_features': 442}},
    'climate-range-halves': {'entity': 'climate.halves', 'state': 'heat_cool',
                             'attributes': {'current_temperature': 21.5, 'target_temp_low': 19.5, 'target_temp_high': 23,
                                            'target_temp_step': 0.5, 'hvac_modes': ['off', 'heat_cool'], 'min_temp': 7,
                                            'max_temp': 35, 'supported_features': 442}},
    # A thermostat's modes on their own and under its -/+ (firmware 0.19.0: one bar, climate_tile::bar_room), six of them.
    'climate-modes': {'entity': 'climate.modes', 'state': 'cool', 'options': {'controls': 'mode'},
                      'attributes': {'current_temperature': 73, 'target_temp_low': 61, 'target_temp_high': 75,
                                     'hvac_modes': ['off', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only'],
                                     'min_temp': 45, 'max_temp': 95, 'target_temp_step': 1, 'supported_features': 442}},
    'climate-both': {'entity': 'climate.both', 'state': 'heat', 'options': {'controls': 'setpoint_mode'},
                     'attributes': {'current_temperature': 20.5, 'temperature': 21.5,
                                    'hvac_modes': ['off', 'heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only'],
                                    'min_temp': 7, 'max_temp': 35, 'target_temp_step': 0.5, 'supported_features': 387}},
    'cover': {'entity': 'cover.audit', 'state': 'open',
              'attributes': {'current_position': 70, 'current_tilt_position': 40, 'supported_features': 255}},
    'fan': {'entity': 'fan.audit', 'state': 'on', 'attributes': {'percentage': 60, 'supported_features': 49}},
    # A dehumidifier with every standard mode (firmware 0.42.0): the thermostat's parts in percent.
    'humidifier': {'entity': 'humidifier.audit', 'state': 'on',
                   'attributes': {'device_class': 'dehumidifier', 'action': 'drying', 'current_humidity': 68.5, 'humidity': 55,
                                  'min_humidity': 30, 'max_humidity': 80, 'supported_features': 1, 'mode': 'comfort',
                                  'available_modes': ['normal', 'eco', 'away', 'boost', 'comfort', 'home', 'sleep', 'auto']}},
    'image': {'entity': 'image.audit', 'state': iso(hours=-1), 'attributes': {}},
    'input_boolean': {'entity': 'input_boolean.audit', 'state': 'on', 'attributes': {}},
    'input_button': {'entity': 'input_button.audit', 'state': iso(minutes=-20), 'attributes': {}},
    'input_number': {'entity': 'input_number.audit', 'state': '21.5',
                     'attributes': {'min': 10, 'max': 30, 'step': 0.5, 'unit_of_measurement': '°C'}},
    'input_select': {'entity': 'input_select.audit', 'state': 'Comfort with a rather long name',
                     'attributes': {'options': ['Eco', 'Comfort with a rather long name', 'Boost']}},
    'light': {'entity': 'light.audit', 'state': 'on',
              'attributes': {'brightness': 200, 'color_mode': 'brightness', 'supported_color_modes': ['brightness']}},
    'lock': {'entity': 'lock.audit', 'state': 'locked', 'attributes': {'supported_features': 1}},
    'media_player': {'entity': 'media_player.audit', 'state': 'playing',
                     'attributes': {'media_title': 'A remarkably long title for a song that keeps going on',
                                    'media_artist': 'An artist with a long name as well', 'volume_level': 0.3,
                                    'supported_features': 8321599}},
    'number': {'entity': 'number.audit', 'state': '55', 'attributes': {'min': 30, 'max': 70, 'step': 5, 'unit_of_measurement': '%'}},
    'person': {'entity': 'person.audit', 'state': 'home', 'attributes': {}},
    'person-away': {'entity': 'person.away', 'state': 'A place with a very long name far from home', 'attributes': {}},
    # A remote (firmware 0.22.0): the activity it runs is its second line, long names included.
    'remote': {'entity': 'remote.audit', 'state': 'on',
               'attributes': {'supported_features': 4, 'current_activity': 'Watch a film on the big screen downstairs',
                              'activity_list': ['Watch TV', 'Watch a film on the big screen downstairs', 'Listen to music']}},
    'scene': {'entity': 'scene.audit', 'state': 'scening', 'attributes': {}},
    'scene-ran': {'entity': 'scene.ran', 'state': iso(hours=-26), 'attributes': {}},
    # The screen's own cards: the clock is the type's case (its faces come from the catalogue), the others beside it.
    'screen': {'entity': 'screen.clock', 'state': 'ok', 'attributes': {}},
    'screen-settings': {'entity': 'screen.settings', 'state': 'ok', 'attributes': {}},
    # A card that goes to page 2 needs a page 2 (`pages`: the layout has that many).
    'screen-page': {'entity': 'screen.page_2', 'state': 'ok', 'attributes': {}, 'pages': 2},
    # The bedside clock fills its page and nothing else (core.validate_layout).
    'screen-nightstand': {'entity': 'screen.nightstand', 'state': 'ok', 'attributes': {}, 'sizes': ('full',)},
    # The map tile is a map and nothing else (core.validate_layout), its frame here without the picture.
    'screen-map': {'entity': 'screen.map', 'state': 'ok', 'attributes': {}, 'options': {'display': 'map'}},
    # The energy card (app 0.4.77) with a busy house: seven devices, a car charging, every source; `energy` is Home
    # Assistant's Energy settings and the states of their sensors (tests/fixtures/energy). A size too low for the diagram
    # shows the house's use alone, which is laid out too.
    'screen-energy': {'entity': 'screen.energy', 'state': 'ok', 'attributes': {},
                      'energy': json.loads((ROOT / 'tests/fixtures/energy/full-busy.json').read_text())},
    'script': {'entity': 'script.audit', 'state': 'off', 'attributes': {'last_triggered': iso(hours=-2, minutes=-8)}},
    'select': {'entity': 'select.audit', 'state': 'Comfort', 'attributes': {'options': ['Eco', 'Comfort', 'Boost']}},
    'sensor': {'entity': 'sensor.audit', 'state': '21.4', 'attributes': {'unit_of_measurement': '°C', 'device_class': 'temperature'},
               'history': HISTORY},
    'sensor-text': {'entity': 'sensor.text', 'state': 'A status that Home Assistant reports as a long sentence', 'attributes': {}},
    'sun': {'entity': 'sun.sun', 'state': 'above_horizon', 'attributes': {'next_rising': iso(hours=9), 'next_setting': iso(hours=2)}},
    'switch': {'entity': 'switch.audit', 'state': 'on', 'attributes': {}},
    'timer': {'entity': 'timer.audit', 'state': 'active',
              'attributes': {'finishes_at': iso(minutes=5), 'duration': '0:05:00', 'remaining': '0:05:00'}},
    'vacuum': {'entity': 'vacuum.audit', 'state': 'docked', 'attributes': {'battery_level': 80, 'supported_features': 30524}},
    'weather': {'entity': 'weather.audit', 'state': 'partlycloudy',
                'attributes': {'temperature': 18.4, 'temperature_unit': '°C', 'humidity': 92, 'wind_speed': 12.2,
                               'wind_speed_unit': 'km/h', 'apparent_temperature': 17.1, 'supported_features': 3},
                'forecast': forecast(), 'hourly': hourly()},
}

# What the preview cannot lay out, with the reason; everything else in the catalogue has a case above.
# A type: {'type': reason}. A face or control set of a type: {'type/display/key': reason}, {'type/controls/key': reason}.
# A screen card: {'screen/card/<id>': reason}. Empty today: the picture faces (a camera or image live, an album cover, a
# map) are laid out too, as the frame that waits for its picture, since the preview has no app to send one (the
# pictures themselves are web/wasm/test_images.mjs's, tests/test_camera.py's and tests/test_map_card.py's).
EXCLUDED = {}

# The screen's own cards that have a case above; an EXCLUDED 'screen/card/<id>' names one that has none.
SCREEN_CARDS = {kind['entity'] for kind in KINDS.values() if kind['entity'].startswith('screen.')}


def catalogue_types():
    """Every type of the tile catalogue: a file of catalogue/ that is not a shared one (_tile.yaml, _ha.json)."""
    return sorted(path.stem for path in (ROOT / 'catalogue').glob('*.yaml') if not path.stem.startswith('_'))


def type_of(kind):
    return KINDS[kind]['entity'].split('.', 1)[0]


def uncovered(kinds=None, excluded=None):
    """The catalogue types with neither a case in `kinds` nor a reason in `excluded`."""
    kinds, excluded = KINDS if kinds is None else kinds, EXCLUDED if excluded is None else excluded
    covered = {case['entity'].split('.', 1)[0] for case in kinds.values()}
    return [domain for domain in catalogue_types() if domain not in covered and domain not in excluded]


def boards():
    """The glass and grids of every board as the editor's preview has them, one per distinct shape and density, and every
    row count a board offers when it is built (boards.yaml `choices: GRID_ROWS`, app 0.4.59): New screen lets someone
    pick it, so its cards must fit as well as the default's. The rows apply lying down (core.shape_of)."""
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
    wanted = [key for key in os.environ.get('LAYOUT_AUDIT_BOARDS', '').split(',') if key]
    seen, found = {}, []
    for key, shape in shapes.items():
        if key.startswith('checkout/') or key.startswith('packages/') or (wanted and key not in wanted):
            continue
        choices = [int(rows) for rows in (shape.get('catalog', {}).get('choices') or {}).get('GRID_ROWS', [])]
        for side in ('landscape', 'portrait'):
            o = shape['orientations'].get(side)
            if not o:
                continue
            grids = [o['rows']] + ([rows for rows in choices if rows != o['rows']] if o['width'] >= o['height'] else [])
            for rows in grids:
                # A board without pictures draws its cards without a cover's place (firmware 0.46.0), so it is a shape of
                # its own even on the glass of a board with them.
                pictures = bool(shape.get('camera'))
                shape_key = (o['width'], o['height'], o['columns'], rows, shape['dpi'], pictures)
                if shape_key in seen:
                    continue
                name = f'{key}-{side}' if rows == o['rows'] else f'{key}-{side}-{rows}rows'
                seen[shape_key] = {'key': name, 'width': o['width'], 'height': o['height'], 'columns': o['columns'],
                                   'rows': rows, 'dpi': shape['dpi'], 'pictures': pictures}
                found.append(seen[shape_key])
    return found


def sizes(grid):
    """The five names this grid takes, and its spans."""
    out = ['single']
    if grid.columns >= 2: out.append('wide')
    if grid.rows >= 2: out.append('tall')
    if grid.columns >= 2 and grid.rows >= 2: out.append('square')
    out.append('full')
    out += [f'{c}x{r}' for c in range(1, grid.columns + 1) for r in range(1, grid.rows + 1) if span_offered(c, r, grid)]
    return out


def two_columns(size, grid):
    """Whether a card of this size is two columns wide or more: where a `wide` face (the forecast, the sun's path) fits."""
    return size in ('wide', 'square') or (size == 'full' and grid.columns >= 2) or (span_of(size) or (0,))[0] >= 2


def variants(domain):
    """The faces and control sets of a type beside its standard one, from the catalogue: [(group, key, item)]."""
    entry = catalogue.of_type(domain) or {}
    displays = entry.get('displays', [])
    controls = entry.get('controls', [])
    return [('display', item['key'], item) for item in displays[1:]] + [('controls', item['key'], item) for item in controls[1:]]


def message(kind, size, name, display=None, controls=None):
    """The tile as the app sends it to a screen (server.tile_message, page_delivery.tile_message): its state message
    with the extras and history the app adds, the controls cut to what the entity can draw."""
    case = KINDS[kind]
    options = {'size': size, **case.get('options', {})}
    if display:
        options['display'] = display
    if controls:
        options['controls'] = controls
    tile = {'entity': case['entity'], 'name': name, 'slot': 0, 'options': options}
    states = {case['entity']: {'state': case['state'], 'attributes': case['attributes']}}
    if case.get('energy'):
        states = case['energy']['states']
        extra = extras(tile, states, energy=case['energy']['prefs'])
    else:
        extra = None if case['entity'] in BUILTIN else extras(tile, states, case.get('forecast'), None, case.get('hourly'), now=NOW)
    out = drawn_controls(state_message(0, tile, states, extra), None)
    if case.get('history') and case['entity'].startswith('sensor.'):
        out['history'] = case['history']
    out.pop('v', None)
    out.pop('op', None)
    out.pop('i', None)
    out['slot'] = 0
    return out


def cases():
    """[(kind, display, controls, names)]: every kind in its own form, and each face and control set of the type's case."""
    out = [(kind, None, None, (SHORT, LONG)) for kind in KINDS]
    for kind in KINDS:
        domain = type_of(kind)
        if kind != domain:
            continue
        for group, key, item in variants(domain):
            if f'{domain}/{group}/{key}' in EXCLUDED:
                continue
            # A face or control set is about where things go, so the long name, which runs into most, is enough.
            out.append((kind, key if group == 'display' else None, key if group == 'controls' else None, (LONG,)))
    return out


def layouts(screen):
    grid = Grid(screen['columns'], screen['rows'])
    out, seen = [], set()
    for kind, display, controls, names in cases():
        item = catalogue.option(type_of(kind), 'displays', display) if display else None
        for size in KINDS[kind].get('sizes') or sizes(grid):
            if item and item.get('wide') and not two_columns(size, grid):
                continue
            if item and (item.get('sizes') or {}).get(size) is False:
                continue
            for name in names:
                tile = message(kind, size, name, display, controls)
                # A control set a card of this size has no room for is the card without one: laid out once is enough.
                fingerprint = json.dumps(tile, sort_keys=True)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                label = kind + (f'-{display}' if display else '') + (f'-{controls}' if controls else '')
                out.append({'key': f'{label} {size} {"long" if name == LONG else "short"}', 'tiles': [tile],
                            'pages': KINDS[kind].get('pages', 1)})
    # Full pages: a card in every cell, and one wide card a row, the kinds taking turns, every name the long one.
    kinds = [kind for kind in KINDS if not KINDS[kind].get('sizes') and not KINDS[kind].get('pages')]
    cells = grid.columns * grid.rows
    out.append({'key': 'every cell', 'tiles': [{**message(kinds[i % len(kinds)], 'single', LONG), 'slot': i} for i in range(cells)]})
    if grid.columns >= 2:
        out.append({'key': 'wide rows', 'tiles': [{**message(kinds[i % len(kinds)], 'wide', LONG), 'slot': i * grid.columns}
                                                  for i in range(grid.rows)]})
    return out


def inside(inner, outer, slack=1):
    return (inner['x1'] >= outer['x1'] - slack and inner['y1'] >= outer['y1'] - slack
            and inner['x2'] <= outer['x2'] + slack and inner['y2'] <= outer['y2'] + slack)


def overlap(a, b):
    return a['x1'] <= b['x2'] and b['x1'] <= a['x2'] and a['y1'] <= b['y2'] and b['y1'] <= a['y2']


MARGIN = 2  # px a text keeps from its card's edge

# What the audit finds today that the firmware does on purpose or has not fixed yet: (`layout`, `problem`) are regular
# expressions on "<screen>: <layout>" and on the problem's line, `cause` the code behind it. Each one must still occur
# on a run over every board, so a fix shows up here as an entry to remove. A firmware change fixes these, not this test.
KNOWN = [
    {'layout': r': (screen(-dial)? |every cell$)', 'problem': r"^texts '\d+:\d+' and '[^']+' lie over each other$",
     'cause': 'by design: the date stands under the digits\' ink, c.digits, which ends above the time\'s line box '
              '(runtime_tiles.h:4390 place_face_text, firmware 0.3.6); the boxes overlap, the letters do not'},
    {'layout': r': screen-flip ', 'problem': r"^texts '\d+' and '[^']+' lie over each other$",
     'cause': 'by design: a flip clock\'s digits stand in their flaps with their line box reaching under the flap, where the '
              'date stands (runtime_tiles.h render_flip); the digits stay inside the flap (rendered 2026-10-03 at six and '
              'eight rows on the 10.1-inch)'},
    {'layout': r': screen-nightstand ', 'problem': r"^texts '\d+' and '\d+' lie over each other$",
     'cause': 'by design: standing up, the minutes stand a digit height under the hours (runtime_tiles.h:4700 render_bedside, '
              'l.digit_h), inside the hours\' line box; the digits do not touch'},
    {'layout': r': [a-z_]+-watch ', 'problem': "^text '[\U000f0000-\U000fffff]' is cut by its object$",
     'cause': 'the watch face\'s circle is half the board\'s icon disc (runtime_tiles.h:6245) while its glyph keeps '
              'watch_icon_font\'s line (runtime_tiles.h:6275): a line box a pixel or two taller than the circle'},
    {'layout': r': screen-analog ', 'problem': r"^text '\d+' is cut by its object$",
     'cause': 'the dial\'s numerals stand on a ring 11 px inside it in a box a line high and wide (runtime_tiles.h:4786); '
              'standing up on the 4.3-inch the 3 o\'clock box passes the dial\'s edge by 2 px'},
    {'layout': r': sun-sunpath ', 'problem': r"^text '.+' is cut without dots",
     'cause': 'the sun path\'s name is a part_label (runtime_tiles.h:5007), which is LV_LABEL_LONG_CLIP '
              '(runtime_tiles.h:4291): a long name is cut, not dotted'},
    {'layout': r'^jc8012p4a1-portrait: input_number ', 'problem': r"^text '[\d.]+ °C' is cut without dots",
     'cause': 'the stepper falls back to text_font when no face fits its room (runtime_tiles.h:5153 stepper_keys), and the '
              'number is clipped: "21.5 °C" in 45 px between the keys'},
    {'layout': r'^(jc3248w535|waveshare35)-landscape: weather-watch full ', 'problem': r"^text '[\d.]+ °C' (leaves its card by \d+ px|is -\d+ px from its card's edge)$",
     'cause': 'a full card stacks circle, name and value without giving any up when they are taller than the card '
              '(runtime_tiles.h:5960 render_full): the watch face\'s value ends 5 px under the card; the 3.5-inch glass with '
              'pictures and the one without are audited apart since firmware 0.46.0'},
]


def known(screen, layout, line):
    """The KNOWN entry this problem is, or None."""
    where = f'{screen}: {layout}'
    return next((entry for entry in KNOWN if re.search(entry['layout'], where) and re.search(entry['problem'], line)), None)


def problems(report):
    """What is wrong in one layout's report, as readable lines."""
    found = []
    if 'error' in report:
        return [f"refused: {report['error']}"]
    objects = {o['id']: o for o in report.get('objects', [])}
    glass = {'x1': 0, 'y1': 0, 'x2': report['width'] - 1, 'y2': report['height'] - 1}
    cards = report.get('cards', [])
    for card in cards:
        box = objects[card['object']]
        if not inside(box, glass):
            found.append(f"card {card['entity']} leaves the glass")
        members = [o for o in objects.values() if o['card'] == cards.index(card) and o['id'] != card['object']]
        # A picture may be cut to its card on purpose (a camera, an album cover filling it): only what is not.
        for o in members:
            if o['type'] != 'image' and o['x2'] > o['x1'] and o['y2'] > o['y1'] and not inside(o, box):
                what = f"text '{o['text'][:30]}'" if o['type'] == 'label' else o['type']
                found.append(f"{what} leaves its card by {max(box['x1'] - o['x1'], o['x2'] - box['x2'], box['y1'] - o['y1'], o['y2'] - box['y2'])} px")
        for o in members:
            parent = objects.get(o['parent'])
            if parent and parent['id'] != box['id'] and parent['clips'] and o['type'] != 'image' and not inside(o, parent):
                what = f"text '{o['text'][:30]}'" if o['type'] == 'label' else o['type']
                found.append(f"{what} is cut by its {parent['type']}")
        # In reading order (top, then left), not in the order the objects were made: a card drawn after another face of
        # the same card keeps parts made before, so the same two texts came in either order and KNOWN missed one of them.
        texts = sorted((o for o in members if o['type'] == 'label' and o['text'].strip() and not o['icon']),
                       key=lambda o: (o['y1'], o['x1'], o['id']))
        for o in texts:
            edge = min(o['x1'] - box['x1'], box['x2'] - o['x2'], o['y1'] - box['y1'], box['y2'] - o['y2'])
            if edge < MARGIN:
                found.append(f"text '{o['text'][:30]}' is {edge} px from its card's edge")
            if 0 < o['content_height'] < o['line_height'] - 1:
                found.append(f"text '{o['text'][:30]}' is cut at the bottom ({o['content_height']} of {o['line_height']} px)")
        for i, a in enumerate(texts):
            for b in texts[i + 1:]:
                if overlap(a, b):
                    found.append(f"texts '{a['text'][:24]}' and '{b['text'][:24]}' lie over each other")
        for o in texts:
            if o['mode'] in ('clip', 'wrap') and '\n' not in o['text']:
                if o['mode'] == 'clip' and o['text_width'] > o['content_width'] + 1:
                    found.append(f"text '{o['text'][:30]}' is cut without dots ({o['text_width']} of {o['content_width']} px)")
                if o['mode'] == 'wrap' and o['wrapped_height'] > o['content_height'] + 1 and o['content_height'] > 0:
                    found.append(f"wrapped text '{o['text'][:30]}' is higher than its box ({o['wrapped_height']} of {o['content_height']} px)")
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            if overlap(objects[a['object']], objects[b['object']]):
                found.append(f"cards {a['entity']} and {b['entity']} run into each other")
    return found


# ---- Touch targets ----
#
# ui::touch_min() is 7 mm of glass (components/smart_display/ui_scale.h:44): the smallest thing a finger must be able to
# hit. preview_layout reports every object LVGL takes a press on (`clickable`) with its drawn box, but not the touch area
# the firmware grows around it (lv_obj_set_ext_click_area, overlay_card::touchable), so a control drawn smaller than 7 mm
# may still be hit at 7 mm. What is held here is therefore a floor per type, in millimetres of drawn glass: the
# smallest side any control of that type is drawn at, on any board, as the firmware is today. A control that shrinks
# below it, or a type that gains a control under 7 mm without an entry, fails, and the entry says where the size comes
# from. The card itself (the whole tile) and an object filling it are its own target and always far above 7 mm.
TOUCH_MM = 7


def touch_min(dpi):
    """ui::touch_min() on a board of this density: ui::mm(7) = (dpi * 7 + 12) / 25 pixels."""
    return (dpi * TOUCH_MM + 12) // 25


def to_mm(pixels, dpi):
    return pixels * 25.4 / dpi


# The types whose tile draws a control smaller than 7 mm on some board, today. `floor` is the smallest side in mm of
# drawn glass the audit measured on any board (rounded down to a tenth); `cause` the code that sizes it, and what grows
# its touch area where something does.
_TOGGLE = ('the panel\'s switch, 48x26 px of the compact look and 76x40 of the standard (runtime_tiles.h:5047 panel_metrics, '
           'toggle_h in look pixels, not ui::touch_min()); its touch area grows by m.ext only (runtime_tiles.h:5084 panel_key)')
_KEY = ('the panel\'s keys, 34 px high in the compact look and 46 in the standard (runtime_tiles.h:5047 panel_metrics, key_h in look '
        'pixels, not ui::touch_min()); their touch area grows by m.ext only (runtime_tiles.h:5084 panel_key)')
_STEPPER = ('the round - and + keys inside the stepper\'s pill, its height less two insets (runtime_tiles.h:5144 stepper_keys); the '
            'click area grows by the inset only')
TOUCH_FLOORS = {
    **{domain: {'floor': 4.6, 'cause': _TOGGLE} for domain in ('automation', 'fan', 'input_boolean', 'light', 'remote', 'switch')},
    **{domain: {'floor': 6.0, 'cause': _KEY} for domain in ('button', 'input_button', 'input_select', 'scene', 'script', 'select',
                                                             'timer', 'vacuum')},
    **{domain: {'floor': 5.3, 'cause': _STEPPER} for domain in ('input_number', 'number')},
    'cover': {'floor': 5.3, 'cause': 'the position slider, slider_h of the look (runtime_tiles.h:5047 panel_metrics), touch area '
                                     'grown by m.ext + 2 (runtime_tiles.h:5241); its keys are the panel\'s (panel_metrics)'},
    'humidifier': {'floor': 4.6, 'cause': 'its on/off switch is the shared toggle (the automation, fan and light entry), its '
                                          'mode bar and -/+ keys the thermostat\'s (the climate entry)'},
    'climate': {'floor': 4.9, 'cause': 'the mode bar\'s segments and the -/+ keys take the panel\'s key_h as their finger '
                                       '(runtime_tiles.h:5041 bar_metrics, cm.touch=m.key_h), not ui::touch_min()'},
    'media_player': {'floor': 2.0, 'cause': 'the full card\'s volume slider is drawn as a 12 px track (media_card.h) and grows '
                                            'by ui::px(8) a side (runtime_tiles.h:3501 media_slider): about 5 mm of glass to hit'},
}


def touch_findings(report, dpi):
    """{type: smallest drawn side in mm} of the controls inside a card that are under 7 mm, and readable lines."""
    found, smallest = [], {}
    objects = {o['id']: o for o in report.get('objects', [])}
    cards = report.get('cards', [])
    least = touch_min(dpi)
    for index, card in enumerate(cards):
        box = objects[card['object']]
        domain = card['entity'].split('.', 1)[0]
        for o in objects.values():
            if o['card'] != index or o['id'] == card['object'] or not o.get('clickable') or o['type'] == 'label':
                continue
            width, height = o['x2'] - o['x1'] + 1, o['y2'] - o['y1'] + 1
            # A clickable object as large as its card is the card's own target (a layer of the card, not a control).
            if width >= box['x2'] - box['x1'] and height >= box['y2'] - box['y1']:
                continue
            side = min(width, height)
            if side >= least:
                continue
            millimetres = to_mm(side, dpi)
            smallest[domain] = min(smallest.get(domain, millimetres), millimetres)
            found.append((domain, millimetres, f"{o['type']} {width}x{height} px ({millimetres:.1f} mm) in {card['entity']}"))
    return smallest, found


def label(ident, text, box, **more):
    x1, y1, x2, y2 = box
    return {'id': ident, 'parent': 1, 'card': 0, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'clips': True, 'type': 'label',
            'text': text, 'mode': 'dots', 'text_width': x2 - x1, 'content_width': x2 - x1 + 1, 'content_height': y2 - y1 + 1,
            'line_height': y2 - y1 + 1, 'wrapped_height': y2 - y1 + 1, 'icon': False, **more}


def report(*objects, cards=((0, 0, 99, 59),)):
    boxes = [{'id': 1 + i * 100, 'parent': 0, 'card': i, 'x1': c[0], 'y1': c[1], 'x2': c[2], 'y2': c[3], 'clips': True,
              'type': 'object', 'clickable': True} for i, c in enumerate(cards)]
    return {'width': 320, 'height': 240, 'objects': [*boxes, *objects],
            'cards': [{'object': b['id'], 'entity': f'light.{i}'} for i, b in enumerate(boxes)]}


def key(ident, box):
    x1, y1, x2, y2 = box
    return {'id': ident, 'parent': 1, 'card': 0, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'clips': True, 'type': 'object',
            'clickable': True}


class Checks(unittest.TestCase):
    """Each check finds what it is there for, and a good card passes them all."""

    def test_a_good_card_passes(self):
        self.assertEqual(problems(report(label(2, 'Lamp', (10, 10, 60, 25)), label(3, 'On', (10, 30, 60, 45)))), [])

    def test_each_fault_is_found(self):
        faults = {
            'leaves its card': label(2, 'Lamp', (10, 10, 120, 25)),
            'lie over each other': [label(2, 'Lamp', (10, 10, 60, 25)), label(3, 'On', (10, 20, 60, 35))],
            'cut without dots': label(2, 'Lamp', (10, 10, 60, 25), mode='clip', text_width=80),
            'higher than its box': label(2, 'Lamp', (10, 10, 60, 25), mode='wrap', wrapped_height=40),
            "from its card's edge": label(2, 'Lamp', (1, 10, 60, 25)),
            'cut at the bottom': label(2, 'Lamp', (10, 10, 60, 25), line_height=24),
            'is cut by its': [{'id': 5, 'parent': 1, 'card': 0, 'x1': 10, 'y1': 10, 'x2': 40, 'y2': 40, 'clips': True, 'type': 'object'},
                              label(6, 'Lamp', (20, 20, 60, 30), parent=5)],
        }
        for words, objects in faults.items():
            with self.subTest(words):
                found = problems(report(*(objects if isinstance(objects, list) else [objects])))
                self.assertTrue(any(words in line for line in found), found)
        self.assertTrue(any('leaves the glass' in line for line in problems(report(cards=((300, 0, 399, 59),)))))
        self.assertTrue(any('run into each other' in line for line in problems(report(cards=((0, 0, 99, 59), (50, 0, 149, 59))))))

    def test_touch_min_is_the_firmwares(self):
        # ui::mm(7) on the CYD (143 dpi) and the Guition (170 dpi), as ui_scale.h computes it.
        self.assertEqual((touch_min(143), touch_min(170)), (40, 48))
        source = (ROOT / 'components/smart_display/ui_scale.h').read_text()
        self.assertIn(f'inline int touch_min() {{ return mm({TOUCH_MM}); }}', source)
        self.assertIn('inline int mm(int millimetres) { return (dpi * millimetres + 12) / 25; }', source)

    def test_a_small_control_is_found_and_a_large_one_is_not(self):
        small, found = touch_findings(report(key(2, (10, 10, 39, 39))), 170)  # 30 px at 170 dpi: 4.5 mm
        self.assertEqual(list(small), ['light'])
        self.assertAlmostEqual(small['light'], 30 * 25.4 / 170)
        self.assertEqual(touch_findings(report(key(2, (10, 10, 57, 57))), 170), ({}, []))  # 48 px: 7.2 mm
        # A text and the card's own layer are no controls.
        self.assertEqual(touch_findings(report(label(2, 'Lamp', (10, 10, 30, 20), clickable=True), key(3, (0, 0, 99, 59))), 170), ({}, []))


    def test_a_known_problem_is_only_itself(self):
        self.assertIsNotNone(known('cyd-landscape', 'screen wide long', "texts '18:04' and 'Monday 14 September' lie over each other"))
        self.assertIsNone(known('cyd-landscape', 'light wide long', "texts '18:04' and 'Monday 14 September' lie over each other"))
        self.assertIsNone(known('cyd-landscape', 'screen wide long', 'text \'18:04\' leaves its card by 3 px'))
        self.assertIsNone(known('cyd-landscape', 'sun-sunpath wide long', "texts 'Sun' and 'rise 06:12' lie over each other"))


    def test_a_binary_from_other_sources_is_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            wasm, manifest = Path(folder) / 'preview.wasm', Path(folder) / 'manifest.h'
            manifest.write_text('#define ESP_SCREEN_FIRMWARE_RENDERER_SOURCE_SHA256 "' + 'a' * 64 + '"\n')
            wasm.write_bytes(b'\0asm' + b'b' * 64)
            self.assertIn(STALE, stale_reason(wasm, manifest, sources=False))
            wasm.write_bytes(b'\0asm' + b'a' * 64)
            self.assertIsNone(stale_reason(wasm, manifest, sources=False))
            manifest.write_text('')
            self.assertIn('no fingerprint', stale_reason(wasm, manifest, sources=False))


class Catalogue(unittest.TestCase):
    """Every type, face and control set of the catalogue has a case here or a reason it has none."""

    def test_the_catalogue_files_are_the_types_the_app_reads(self):
        self.assertEqual(catalogue_types(), sorted(catalogue.TYPES))

    def test_every_type_has_a_case_or_a_reason(self):
        self.assertEqual(uncovered(), [], 'a catalogue type without a case in KINDS: add one, or an EXCLUDED entry with the reason')
        # The rule finds a type without either, and takes a reason for one.
        without = {kind: case for kind, case in KINDS.items() if not case['entity'].startswith('weather.')}
        self.assertEqual(uncovered(without, {}), ['weather'])
        self.assertEqual(uncovered(without, {'weather': 'a reason'}), [])
        covered = {type_of(kind) for kind in KINDS}
        excluded = {name for name in EXCLUDED if '/' not in name}
        # A type is its own case's name, so its faces and control sets have a card to be laid out on.
        self.assertEqual([domain for domain in covered if domain not in KINDS], [])
        self.assertEqual(sorted(covered & excluded), [])

    def test_every_face_and_control_set_is_laid_out_or_excluded(self):
        laid_out = {(type_of(kind), 'display', display) for kind, display, _, _ in cases() if display}
        laid_out |= {(type_of(kind), 'controls', controls) for kind, _, controls, _ in cases() if controls}
        for domain in catalogue_types():
            for group, name, _ in variants(domain):
                with self.subTest(f'{domain}/{group}/{name}'):
                    self.assertTrue((domain, group, name) in laid_out or f'{domain}/{group}/{name}' in EXCLUDED)

    def test_no_reason_outlives_its_case(self):
        """An EXCLUDED entry names what is still in the catalogue, and nothing that has a case."""
        for name in EXCLUDED:
            parts = name.split('/')
            with self.subTest(name):
                self.assertIn(parts[0], catalogue_types())
                if len(parts) == 3 and parts[1] in ('display', 'controls'):
                    group = 'displays' if parts[1] == 'display' else 'controls'
                    self.assertIsNotNone(catalogue.option(parts[0], group, parts[2]))
                elif len(parts) == 3:
                    self.assertEqual(parts[1], 'card')
                    self.assertIn(parts[2], BUILTIN)
                    self.assertNotIn(parts[2], SCREEN_CARDS)

    def test_every_case_is_a_message_the_app_sends(self):
        """Each case goes through the app's own message builder, with what makes its face worth a look."""
        for kind, display, controls, _ in cases():
            with self.subTest(kind=kind, display=display, controls=controls):
                tile = message(kind, 'wide', LONG, display, controls)
                self.assertEqual(tile['entity'], KINDS[kind]['entity'])
                if display:
                    self.assertEqual(tile['o'].get('display'), display)
        self.assertIn('days', message('weather', 'wide', LONG, 'forecast')['x'])
        self.assertIn('history', message('sensor', 'wide', LONG, 'graph'))
        self.assertIn('end', message('timer', 'wide', LONG)['x'])
        self.assertIn('rise', message('sun', 'wide', LONG)['x'])


def missing_reason():
    """Why the audit cannot run here, or None."""
    if not shutil.which('node'):
        return 'Node is not installed'
    if not WASM.exists():
        return f'{WASM.relative_to(ROOT)} is missing (web/wasm/build.sh)'
    return None


STALE = 'WASM preview is stale, rebuild with web/wasm/build.sh or let preview.yml do it'


def stale_reason(wasm=WASM, manifest=MANIFEST, sources=True):
    """Why the committed preview is not the firmware this tree has, or None: its sources moved past the manifest
    (generate_renderer_manifest.py --check, the check preview.yml and tools/check.sh run), or the binary carries
    another fingerprint than the manifest (built before the manifest was written; test_runtime.mjs asks the same of
    preview_diagnostics, here it is read from the binary itself)."""
    if sources:
        run = subprocess.run([sys.executable, str(ROOT / 'web/wasm/generate_renderer_manifest.py'), '--check'],
                             capture_output=True, text=True, cwd=ROOT, timeout=300)
        if run.returncode:
            return f'{STALE}: its firmware sources changed ({(run.stderr or run.stdout).strip()[-300:]})'
    found = re.search(r'SHA256 "([0-9a-f]{64})"', manifest.read_text()) if manifest.exists() else None
    if not found:
        return f'{STALE}: {manifest.name} has no fingerprint'
    if found[1].encode() not in wasm.read_bytes():
        return f'{STALE}: the binary was built from other sources than {manifest.name} names'
    return None


PIECES = 16  # the pieces a screen's layouts are cut into at most, on every machine (audit)


def audit(screens):
    """Every screen's layouts through layout_audit.mjs, a few screens to a Node process, side by side."""
    jobs = max(1, int(os.environ.get('LAYOUT_AUDIT_JOBS') or os.cpu_count() or 2))
    # Each screen's layouts in pieces, the pieces dealt round the processes heaviest first (a ten-inch glass takes
    # longer a layout than a CYD's), so they finish close together. A piece is one firmware, laid out one layout after
    # another as a screen is, so where the pieces start must not depend on the machine: a fixed count, never the
    # number of processors, or one computer sees a layout follow another that a second computer never does.
    pieces = []
    for screen in screens:
        step = max(50, -(-len(screen['layouts']) // PIECES))
        pieces += [{**screen, 'layouts': screen['layouts'][i:i + step]} for i in range(0, len(screen['layouts']), step)]
    pieces.sort(key=lambda s: -len(s['layouts']) * s['width'] * s['height'])
    groups = [[] for _ in range(jobs)]
    load = [0] * jobs
    for piece in pieces:
        i = load.index(min(load))
        groups[i].append(piece)
        load[i] += len(piece['layouts']) * piece['width'] * piece['height']

    def one(group):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(group, f)
        try:
            run = subprocess.run(['node', str(ROOT / 'web/wasm/layout_audit.mjs'), f.name], capture_output=True, text=True, timeout=1800)
        finally:
            os.unlink(f.name)
        if run.returncode:
            raise RuntimeError(run.stderr[-2000:])
        return json.loads(run.stdout)

    with ThreadPoolExecutor(jobs) as pool:
        return [r for part in pool.map(one, [g for g in groups if g]) for r in part]


class LayoutAudit(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        reason = missing_reason()
        if reason:
            if os.environ.get('CI'):
                raise RuntimeError(f'The layout audit cannot run in CI: {reason}.')
            sys.stderr.write('\n' + '!' * 78 + f'\n!! LAYOUT AUDIT SKIPPED: {reason}.\n!! CI fails on this; '
                             'locally nothing about card geometry was checked.\n' + '!' * 78 + '\n')
            raise unittest.SkipTest(reason)
        stale = stale_reason()
        if stale:
            raise RuntimeError(stale)
        screens = boards()
        for screen in screens:
            screen['layouts'] = layouts(screen)
        cls.screens = {screen['key']: screen for screen in screens}
        cls.reports = audit(screens)
        if os.environ.get('LAYOUT_AUDIT_OUT'):
            Path(os.environ['LAYOUT_AUDIT_OUT']).write_text(json.dumps(cls.reports))

    def test_every_layout_was_laid_out(self):
        self.assertTrue(self.reports)
        self.assertEqual([f"{r['screen']}: {r.get('layout')}: {r['error']}" for r in self.reports if 'error' in r], [])
        self.assertEqual(len(self.reports), sum(len(s['layouts']) for s in self.screens.values()))
        # Every layout drew its card: an empty page means the firmware refused it.
        empty = [f"{r['screen']}: {r['layout']}" for r in self.reports if not r.get('cards')]
        self.assertEqual(empty, [])

    def test_every_type_was_drawn(self):
        """A card of every type the audit has a case for came back from the firmware, not only a message sent."""
        drawn = {card['entity'].split('.', 1)[0] for r in self.reports for card in r.get('cards', [])}
        self.assertEqual(sorted({type_of(kind) for kind in KINDS} - drawn), [])

    def test_nothing_leaves_its_card_or_runs_into_another(self):
        found, seen = {}, set()
        for r in self.reports:
            for line in problems(r):
                entry = known(r['screen'], r['layout'], line)
                if entry:
                    seen.add(KNOWN.index(entry))
                else:
                    found.setdefault(f"{r['screen']}: {r['layout']}", []).append(line)
        self.assertEqual(found, {})
        # A known problem that no longer occurs was fixed: its entry goes (only where every board was laid out).
        if not os.environ.get('LAYOUT_AUDIT_BOARDS'):
            self.assertEqual([entry['cause'] for i, entry in enumerate(KNOWN) if i not in seen], [],
                             'fixed: remove these from KNOWN')

    def test_controls_keep_their_touch_floor(self):
        """No control is drawn smaller than 7 mm (ui::touch_min) unless its type's floor allows it, and never below it."""
        smallest, worse, examples = {}, [], {}
        for r in self.reports:
            dpi = self.screens[r['screen']]['dpi']
            sizes_mm, found = touch_findings(r, dpi)
            for domain, millimetres in sizes_mm.items():
                smallest[domain] = min(smallest.get(domain, millimetres), millimetres)
            for domain, millimetres, line in found:
                floor = TOUCH_FLOORS.get(domain, {}).get('floor', TOUCH_MM)
                if millimetres < floor:
                    worse.append(f"{r['screen']}: {r['layout']}: {line}, under {floor} mm")
                examples.setdefault(domain, f"{r['screen']}: {r['layout']}: {line}")
        self.assertEqual(worse, [], 'a control under its touch floor: give it ui::touch_min() of glass, or record why in TOUCH_FLOORS')
        # A floor that no control comes near any more is lowered too far: raise it to what the firmware draws now
        # (only where every board was laid out: one board alone need not reach a floor another sets).
        if os.environ.get('LAYOUT_AUDIT_BOARDS'):
            return
        loose = {domain: (entry['floor'], round(smallest.get(domain, TOUCH_MM), 2)) for domain, entry in TOUCH_FLOORS.items()
                 if smallest.get(domain, TOUCH_MM) - entry['floor'] >= 0.5}
        self.assertEqual(loose, {}, 'raise these TOUCH_FLOORS to the size the firmware draws now')


if __name__ == '__main__':
    unittest.main()
