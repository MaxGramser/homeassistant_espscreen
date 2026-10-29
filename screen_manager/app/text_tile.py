"""The template tile (`screen.text`, module text_card, firmware 0.58.0): a text with Home Assistant templates in it,
rendered by Home Assistant and drawn by the screen as a few rows of text. docs/TEXT_TILE.md says why it is built so.

Home Assistant renders the template (websocket `render_template`, one subscription per tile, template_service.py): it
knows which entities the template reads and sends a new result when one of them changes, and it paces templates that
read the time or every state. This module is the pure half: the tile's own option, and the result turned into rows for
the screen. The screen gets rows, never markdown or Jinja, so no screen parses anything and the editor's preview, which
runs the same firmware, shows exactly what the screen shows.

The wire form, `x.md` of the tile's state message:
    {"v": 1, "r": [row, ...]}      rows to draw; an empty list draws nothing (the cells stay empty)
    {"v": 1, "e": "message"}       Home Assistant could not render the template
A row is [kind, runs]: kind "h" a heading, "p" text, "li" a bullet; or ["t", [runs, ...]] a table row (one runs per
cell) and "th" the row over a table's |---| line. Runs are [[tone, text], ...]: tone 0 plain, 1 bold, 2 good,
3 alert, 4 accent (the plugin API's tones). `v` grows when a later syntax needs the screen to read something new.
"""
from __future__ import annotations

import json
import re

TEXT_TILE = 'screen.text'
# The module whose screens draw it (components/smart_display/modules.py), named in their hello.
FEATURE = 'text_card'
# A screen draws the tile when its hello says FEATURE (a full-tier build, docs/MODULES.md), not from a firmware number:
# dev builds have it before a release numbers them. Another screen is told it needs this firmware.
FIRMWARE = '0.58.0'
VERSION = 1

# The tile's own option: the template, as typed. Home Assistant takes far longer ones; a tile shows 24 rows at most.
OPTION = 'template'
MAX_TEMPLATE = 4000

# What a tile shows at most (docs/TEXT_TILE.md, "Limits"). A screen's hello may state a smaller budget for its rows.
MAX_ROWS = 24
MAX_COLUMNS = 4
MAX_RUNS = 4
MAX_ROW_TEXT = 240
MAX_ERROR = 160
# The bytes of a tile's rows as they travel (compact JSON): a screen says its own in its hello (`text_bytes`), else this.
# A state message is 4096 bytes at most (page_delivery.MAX_MESSAGE); the rest of it (name, entity, options) stays below 512.
DEFAULT_BYTES = 2048
MAX_BYTES = 3584
# Template tiles per screen: each is a subscription in Home Assistant. A screen may state fewer (`text_tiles`).
DEFAULT_TILES = 8
ELLIPSIS = '…'

# Typography the screens' fonts have no glyph for (they would show an empty box), as the nearest character they have:
# the minus sign of a negative power, the dashes, the curly quotes and the spaces of a formatted number.
PLAIN_CHARACTERS = str.maketrans({'\u2212': '-', '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-', '\u2014': '-',
                                  '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u00a0': ' ', '\u202f': ' ',
                                  '\u2009': ' '})

PLAIN, BOLD, GOOD, ALERT, ACCENT = range(5)
TONES = {'good': GOOD, 'alert': ALERT, 'accent': ACCENT}
_INLINE = re.compile(r'\*\*(.+?)\*\*|:(good|alert|accent)\[(.+?)\]')
_HEADING = re.compile(r'^#{1,3}\s+')
_BULLET = re.compile(r'^[-*]\s+')
_RULE = re.compile(r'^\|?(\s*:?-{2,}:?\s*\|)*\s*:?-{2,}:?\s*\|?$')


def unsupported(tiles, features):
    """Whether a layout has a template tile a screen with these hello `features` (None: not known yet) cannot draw."""
    return any(tile.get('entity') == TEXT_TILE for tile in tiles) and FEATURE not in (features or ())


def validate(value):
    """The tile's template, or ValueError: text, not empty, at most MAX_TEMPLATE characters."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEMPLATE:
        raise ValueError(OPTION)
    return value


def inline(text):
    """Runs of one row's text: **bold** and :good[..], :alert[..], :accent[..]; at most MAX_RUNS, the rest plain."""
    runs, last = [], 0
    for match in _INLINE.finditer(text):
        if match.start() > last:
            runs.append([PLAIN, text[last:match.start()]])
        runs.append([BOLD, match.group(1)] if match.group(1) is not None else [TONES[match.group(2)], match.group(3)])
        last = match.end()
    if last < len(text):
        runs.append([PLAIN, text[last:]])
    if len(runs) > MAX_RUNS:
        runs = runs[:MAX_RUNS - 1] + [[PLAIN, ''.join(part for _, part in runs[MAX_RUNS - 1:])]]
    return _clip(runs, MAX_ROW_TEXT)


def _clip(runs, limit):
    """Runs cut to `limit` characters in all, with an ellipsis where it cut."""
    out, left = [], limit
    for tone, part in runs:
        if len(part) > left:
            out.append([tone, part[:left].rstrip() + ELLIPSIS])
            break
        out.append([tone, part])
        left -= len(part)
    return [run for run in out if run[1]] or [[PLAIN, '']]


def rows(text):
    """The rendered template as rows (the module's docstring): empty lines go, at most MAX_ROWS rows, MAX_COLUMNS cells."""
    out = []
    for raw in str(text).translate(PLAIN_CHARACTERS).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('|') and _RULE.match(line) and '-' in line:
            # The line under a table's head: the row before it is the head.
            if out and out[-1][0] == 't':
                out[-1][0] = 'th'
            continue
        if line.startswith('|'):
            cells = line.strip('|').split('|')[:MAX_COLUMNS]
            out.append(['t', [inline(cell.strip()) for cell in cells]])
        elif _HEADING.match(line):
            out.append(['h', inline(_HEADING.sub('', line))])
        elif _BULLET.match(line):
            out.append(['li', inline(_BULLET.sub('', line))])
        else:
            out.append(['p', inline(line)])
        if len(out) > MAX_ROWS:
            return _ellipsis(out[:MAX_ROWS])
    return out


def _ellipsis(out):
    """The last row ends in an ellipsis: there was more than the tile takes."""
    row = out[-1]
    runs = row[1][-1] if row[0] in ('t', 'th') else row[1]
    runs[-1][1] = runs[-1][1].rstrip() + ELLIPSIS
    return out


def size(block):
    """The bytes a block takes on its way to the screen (compact JSON, as encode sends it)."""
    return len(json.dumps(block, ensure_ascii=False, separators=(',', ':')).encode())


def block(text, budget=DEFAULT_BYTES):
    """The tile's `md` for a rendered template: its rows, dropped from the end until they fit `budget` bytes."""
    out = rows(text)
    budget = max(256, min(int(budget or DEFAULT_BYTES), MAX_BYTES))
    cut = False
    while out and size({'v': VERSION, 'r': out}) > budget:
        out.pop()
        cut = True
    if cut and out:
        _ellipsis(out)
        while len(out) > 1 and size({'v': VERSION, 'r': out}) > budget:
            out.pop()
            _ellipsis(out)
    return {'v': VERSION, 'r': out}


def error(message):
    """The tile's `md` when Home Assistant could not render its template: one short line of why."""
    text = ' '.join(str(message or '').split()) or 'Template error'
    return {'v': VERSION, 'e': text[:MAX_ERROR - 1] + ELLIPSIS if len(text) > MAX_ERROR else text}


def entity_facts(state, most=60, chars=80):
    """What the template editor's completion offers for one entity (docs/TEXT_TILE.md, "Writing a template"): its
    state, its attributes with their values written short, and the states it may take where Home Assistant lists them
    (a select's `options`, a climate's `hvac_modes`, a fan's `preset_modes`, ...)."""
    state = state if isinstance(state, dict) else {}
    attributes = state.get('attributes') if isinstance(state.get('attributes'), dict) else {}

    def short(value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= chars else text[:chars - 1] + ELLIPSIS
    states = []
    for key in ('options', 'hvac_modes', 'preset_modes', 'fan_modes', 'swing_modes', 'effect_list', 'source_list',
                'sound_mode_list', 'operation_list', 'available_modes'):
        if isinstance(attributes.get(key), list):
            states += [str(item) for item in attributes[key] if isinstance(item, (str, int, float))][:40]
    return {'state': short(state.get('state', '')),
            'attributes': {str(key): short(value) for key, value in list(attributes.items())[:most]},
            'states': list(dict.fromkeys(states))}


def budget_of(features, caps=None):
    """(bytes, tiles) a screen takes: what its hello states (`text_bytes`, `text_tiles`), else the defaults."""
    caps = caps if isinstance(caps, dict) else {}
    def number(key, default, top):
        value = caps.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= top else default
    return number('text_bytes', DEFAULT_BYTES, MAX_BYTES), number('text_tiles', DEFAULT_TILES, 32)
