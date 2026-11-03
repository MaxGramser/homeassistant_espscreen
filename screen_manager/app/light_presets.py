"""A light's presets (module light_presets, docs/LIGHT_PRESETS.md): up to four round keys on its tile and its card, each
setting the light to a brightness and, where the preset has one, a white shade or a colour, in one light.turn_on.

Home Assistant keeps favourite colours per light (the entity registry's `light.favorite_colors`, shown as round keys in
its more-info dialog), but without a brightness. A preset is that colour with the brightness it goes with, chosen per
tile in the editor and kept in the tile's options:

    {"b": 80, "k": 2700}          80 %, white at 2700 K
    {"b": 60, "h": 280, "s": 41}  60 %, hue 280 at 41 % saturation (Home Assistant's hs_color)
    {"b": 30}                     30 %, the colour the light has
    {"b": 70, "h": 280, "s": 41, "fx": "Colorloop", "rw": {"select.desk_color_palette": "Party", "number.desk_speed": 180}}
                                  with an effect of the light's and settings of its device (its effects page's rows)
    {"rw": {"select.desk_preset": "Film"}}   a preset of the lamp itself (a WLED's own): that sets everything

The screen gets them as they are stored (`o.presets`), and draws them only where its hello says light_presets; another
screen draws the brightness slider in their place (catalogue/light.yaml).
"""
from __future__ import annotations

import math
import re

OPTION = 'presets'
# The settings of the light's device a preset may set (the effects page's rows, light_effects.py): at most this many.
ROWS = 4
NAME_LIMIT = 64
ROW_ENTITY = re.compile(r'(select|number)\.[a-z0-9_]+\Z')
# Whether each disc shows its preset's brightness, small in its middle (off unless chosen; a preset of a brightness alone
# always shows it, as it has no colour to tell it by).
LEVELS = 'preset_levels'
# As many as a row of round keys holds on a tile one row high (module_light_presets.h works out how many fit a card).
MAX = 4
# The white shades a preset may name, in kelvin: Home Assistant's light takes 1000 to 40000; a screen keeps 1000 to 15000.
KELVIN = (1000, 15000)


def _int(value, low, high):
    """An int of JSON (not a bool, a whole float allowed) within low..high, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value % 1:
        return None
    value = int(value)
    return value if low <= value <= high else None


def preset(item):
    """One preset in its stored form, or ValueError."""
    if not isinstance(item, dict) or set(item) - {'b', 'k', 'h', 's', 'fx', 'rw'}:
        raise ValueError(OPTION)
    out = {}
    # The settings of the light's device: a select's option or a number's value each, by entity.
    if 'rw' in item:
        rows = item['rw']
        if not isinstance(rows, dict) or not rows or len(rows) > ROWS:
            raise ValueError(OPTION)
        out['rw'] = {}
        for entity, value in rows.items():
            if not isinstance(entity, str) or not ROW_ENTITY.match(entity):
                raise ValueError(OPTION)
            if entity.startswith('select.'):
                if not isinstance(value, str) or not value.strip() or len(value) > NAME_LIMIT:
                    raise ValueError(OPTION)
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(OPTION)
            out['rw'][entity] = value
    if 'fx' in item:
        if not isinstance(item['fx'], str) or not item['fx'].strip() or len(item['fx']) > NAME_LIMIT:
            raise ValueError(OPTION)
        out['fx'] = item['fx']
    # A preset of the lamp itself (its device's settings alone) needs no brightness; every other one has one.
    if 'b' not in item and 'rw' in out and not ({'k', 'h', 's', 'fx'} & set(item)):
        return out
    level = _int(item.get('b'), 1, 100)
    if level is None:
        raise ValueError(OPTION)
    # In the editor's order (web/src/model/light-presets.ts cleanPreset): the brightness, the shade or colour, then the
    # effect and the device's settings.
    extra, out = out, {'b': level}
    if 'k' in item:
        if 'h' in item or 's' in item:
            raise ValueError(OPTION)
        kelvin = _int(item['k'], *KELVIN)
        if kelvin is None:
            raise ValueError(OPTION)
        out['k'] = kelvin
    elif 'h' in item or 's' in item:
        hue, saturation = _int(item.get('h'), 0, 360), _int(item.get('s'), 0, 100)
        if hue is None or saturation is None:
            raise ValueError(OPTION)
        out['h'], out['s'] = hue % 360, saturation
    if 'fx' in extra:
        out['fx'] = extra['fx']
    if 'rw' in extra:
        out['rw'] = extra['rw']
    return out


def screen_presets(items):
    """The presets as a screen reads them: the device's settings as a list of [entity, value] (page_receiver.cpp)."""
    return [{**p, 'rw': [[e, v] for e, v in p['rw'].items()]} if isinstance(p.get('rw'), dict) else p for p in items]


def validate(options, domain):
    """A tile's options with its presets checked: a light's list of at most MAX, none on any other tile, and none stored
    when the list is empty; whether they show their brightness, stored only when they do. ValueError on a wrong one."""
    out = {k: v for k, v in options.items() if k not in (OPTION, LEVELS)}
    if domain != 'light':
        return out
    if LEVELS in options:
        if not isinstance(options[LEVELS], bool):
            raise ValueError(LEVELS)
        if options[LEVELS]:
            out[LEVELS] = True
    if OPTION not in options:
        return out
    items = options[OPTION]
    if not isinstance(items, list) or len(items) > MAX:
        raise ValueError(OPTION)
    items = [preset(item) for item in items]
    if items:
        out[OPTION] = items
    return out
