"""A plugin's manifest (`tessera-plugin.yaml`): read it, check it, and turn it into what the editor shows.

One file, no imports from the rest of the add-on, so the plugins repository runs the very same check on every plugin
(github.com/MaxGramser/tessera-plugins, `tools/check.py` fetches this file). The rules are in that repository's
docs/MANIFEST.md; every rule here has a line there.

A manifest holds no code and no words: names, labels and hints are keys into the plugin's `translations/<lang>.json`
(part `app`), so the editor shows them in its own language. Nothing in a manifest is ever run by the add-on: a fetch is
a description the add-on carries out with its own code (plugin_fetch.py).
"""
import ipaddress
import re
from urllib.parse import urlsplit

# The plugin API this core offers (components/smart_display/plugin_api.h, PLUGIN_API_MAJOR/MINOR; a test keeps them
# equal). A plugin names the API it was written for; it builds on every core with the same major and at least its minor.
# Something new raises the minor; a plugin builds on the same major from its own minor up. Only a break raises the major.
PLUGIN_API = (0, 8)
# Major 0 is the time before that promise: a minor may still change a name or a signature. The minors that did are
# listed here (and in __init__.py's PLUGIN_API_BREAKS; a test keeps them equal), so a plugin written before one is told
# so in one sentence instead of failing in the compiler. 0.4: Plugin::on_tick became on_interval.
PLUGIN_API_BREAKS = {0: (4,)}

ID = re.compile(r'^[a-z][a-z0-9_]{0,31}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
API = re.compile(r'^(\d+)\.(\d+)$')
SIZE = re.compile(r'^([1-9])x([1-9])$')
EVERY = re.compile(r'^(\d+)(s|m|h|d)$')
HOST = re.compile(r'^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')
MDI = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
PLACEHOLDER = re.compile(r'\{([a-z][a-z0-9_]*)\}')
TEXT_KEY = re.compile(r'^[a-z][a-z0-9_]{0,47}$')

TOP = {'id', 'version', 'api', 'icon', 'maintainer', 'license', 'stage', 'topics', 'requires', 'provides', 'boards',
       'flash_kb', 'permissions', 'attributes', 'privacy', 'inputs', 'parts', 'tiles', 'fetch', 'answers', 'cards',
       'tap_actions', 'bar_items', 'settings'}
ATTRIBUTES = ('cloud', 'commercial', 'ai-developed')
# How far along a plugin is, in the maker's word: ready for every day, still finding its feet, or there to show what a
# plugin can do and to learn from. The editor shows a badge for the last two; a manifest without it is beta.
STAGES = ('stable', 'beta', 'example')
# What a plugin is about, in the maker's word (0.7): one or two of these, so a person finds a countdown among weather,
# departures and games. The topics small always-on displays have in common (TRMNL, Tidbyt, LaMetric, AWTRIX,
# MagicMirror²), without a catch-all: a plugin that fits none asks for a new topic in the plugins repository. What a
# plugin adds (tiles, something for the whole screen, a board's hardware) is no topic: the app reads it from the
# manifest (plugin_type).
TOPICS = ('time', 'weather', 'calendar', 'home', 'energy', 'travel', 'money', 'sports', 'news', 'media', 'photos',
          'fun', 'voice', 'tech')
MAX_TOPICS = 2
# What a screen can have that a plugin may need (0.7), each a promise about one ESPHome component and its id, the way
# ESPHome's voice_assistant takes whatever speaker there is: a plugin that needs a speaker finds `ts_speaker`, whether a
# board brings it (boards.yaml) or a plugin (`provides`). One screen has one of each.
# 0.8: `camera`, the screen's own camera as an ESPHome camera (Home Assistant shows it, another plugin may use it), and
# `camera_sensor`, a board's own: the sensor a camera plugin drives. A board-only feature (no component) is hardware a
# plugin cannot bring; its promise is a substitution of the board file that a plugin's ESPHome file uses, here
# CAMERA_I2C, the I2C bus the sensor answers on. The board powers the sensor itself.
FEATURES = {'speaker': ('speaker', 'ts_speaker'), 'microphone': ('microphone', 'ts_microphone'),
            'media_player': ('media_player', 'ts_media_player'), 'camera': ('esp_video_camera', 'ts_camera'),
            'camera_sensor': (None, 'CAMERA_I2C')}
BOARD_ONLY = tuple(name for name, (domain, _) in FEATURES.items() if domain is None)
INPUT_KINDS = ('secret', 'text', 'gpio', 'entity')
OPTION_KINDS = ('text', 'choice', 'number', 'toggle')
# `numbers` (0.5): every value the path reaches, as one list of numbers (a price per quarter of an hour, a forecast).
FIELD_KINDS = ('text', 'number', 'epoch', 'numbers')
UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
# Licences that go with AGPL-3.0, the licence the firmware a plugin is built into carries.
LICENSES = ('MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', 'MPL-2.0', 'LGPL-2.1-or-later',
            'LGPL-3.0-or-later', 'GPL-3.0-or-later', 'AGPL-3.0-or-later', 'AGPL-3.0-only', 'GPL-3.0-only', 'Unlicense',
            '0BSD', 'CC0-1.0')

# How the editor draws a tile with data (it cannot run the plugin's C++): the first item's fields in a badge, a title
# and a value, or a countdown to a moment. Templates name fields as {field}.
PREVIEW = ('badge', 'title', 'value', 'countdown')
# What a plugin may ask Home Assistant through the app (tessera::send): a websocket command, or an action that answers
# (call_service:<domain>.<service>, sent with return_response). Never one that reads or changes Home Assistant itself.
HA_COMMAND = re.compile(r'^(call_service:[a-z_]+\.[a-z0-9_]+|[a-z_]+(/[a-z_]+)*)$')
FORBIDDEN_COMMANDS = ('auth', 'config', 'subscribe_events', 'subscribe_trigger', 'execute_script', 'call_service',
                      'fire_event', 'render_template', 'supervisor', 'hassio', 'get_config', 'lovelace', 'person', 'backup',
                      'cloud', 'application_credentials', 'repairs', 'blueprint', 'trace', 'validate_config')
MAX_ATTRIBUTES = 16
MAX_HAS_ATTRIBUTES = 8      # attributes an entity must have to be offered for a tile
MAX_ANSWERS = 8             # answers of Home Assistant commands a plugin maps
MAX_TILES = 8
MAX_OPTIONS = 12
MAX_FETCHES = 8
MAX_INPUTS = 8
MAX_ITEMS = 48              # a list from a fetch: 24 hourly prices fit twice
MAX_FIELDS = 8
MIN_EVERY = 30              # seconds between two asks for the same thing
MAX_TILE_BYTES = 16384      # what one plugin tile may say it costs of the screen's tile memory
MAX_TEXT = 64               # a text option's value


class ManifestError(ValueError):
    """What is wrong, as a path into the manifest and a sentence a maker understands."""

    def __init__(self, where, message):
        super().__init__(f'{where}: {message}' if where else message)
        self.where = where
        self.message = message


def seconds(every):
    """`30s`, `5m`, `1h`, `1d` in seconds; None for anything else."""
    match = EVERY.match(str(every or ''))
    return int(match.group(1)) * UNITS[match.group(2)] if match else None


def api_fits(wanted, offered=PLUGIN_API, breaks=None):
    """Whether a plugin written for API `wanted` ("0.1") builds on a core that offers `offered`: the same major, at
    least its minor, and no minor between them that changed a name (PLUGIN_API_BREAKS)."""
    match = API.match(str(wanted or ''))
    if not match:
        return False
    major, minor = int(match.group(1)), int(match.group(2))
    breaks = PLUGIN_API_BREAKS if breaks is None else breaks
    return (major == offered[0] and minor <= offered[1]
            and not any(minor < broke <= offered[1] for broke in breaks.get(major, ())))


def span(size):
    match = SIZE.match(str(size or ''))
    return (int(match.group(1)), int(match.group(2))) if match else None


def is_private_host(host):
    """A literal address on the home network, or a name that only lives there. Names are resolved again at connect
    time (plugin_fetch.py); this check only refuses what is visibly local."""
    host = (host or '').lower()
    if host in ('localhost', 'homeassistant', 'hassio', 'supervisor') or host.endswith(('.local', '.lan', '.home',
                                                                                        '.internal', '.localdomain')):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved


# ---- The path language of a fetch's map: $, .name, .{placeholder}, [*], [n], [:n]. No filters, no expressions. ----
STEP = re.compile(r'\.([A-Za-z_][A-Za-z0-9_-]*)|\.\{([a-z][a-z0-9_]*)\}|\[\*\]|\[(\d+)\]|\[:(\d+)\]')


def parse_path(path, root=True):
    """The steps of a path as tuples: ('key', name), ('var', placeholder), ('all',), ('at', n), ('first', n). A field
    path (root=False) starts without `$`, with a name or a list step: `a.b[0]`, `[*].price` (0.5, for an answer that
    files its list under a name the plugin cannot know, such as Nord Pool's area)."""
    text = str(path or '')
    if root:
        if not text.startswith('$'):
            raise ValueError('a path starts with $')
        text = text[1:]
    else:
        if not text or text.startswith(('.', '$')):
            raise ValueError('a field path starts with the name of a field or a list step such as [*]')
        if not text.startswith('['):
            text = '.' + text
    steps, at = [], 0
    while at < len(text):
        match = STEP.match(text, at)
        if not match:
            raise ValueError(f'cannot read the path at "{text[at:]}"')
        name, var, index, first = match.groups()
        if name is not None:
            steps.append(('key', name))
        elif var is not None:
            steps.append(('var', var))
        elif index is not None:
            steps.append(('at', int(index)))
        elif first is not None:
            steps.append(('first', int(first)))
        else:
            steps.append(('all',))
        at = match.end()
    return steps


def _where(where):
    return f'{where}.' if where else ''


def _object(value, where, allowed, required=()):
    if not isinstance(value, dict):
        raise ManifestError(where, 'must be a mapping')
    unknown = [key for key in value if key not in allowed and not str(key).startswith('x-')]
    if unknown:
        raise ManifestError(where, f'unknown field "{unknown[0]}" (fields: {", ".join(sorted(allowed))})')
    missing = [key for key in required if key not in value]
    if missing:
        raise ManifestError(where, f'"{missing[0]}" is required')
    return value


def _id(value, where):
    if not isinstance(value, str) or not ID.match(value):
        raise ManifestError(where, 'an id is 1 to 32 of a-z, 0-9 and _, starting with a letter')
    return value


def _features(value, where, strict, keep_unknown=False):
    """A list of features of FEATURES. One this app does not know: refused when `strict`; else kept when a plugin needs
    it (`keep_unknown`, so it fits no screen) and left out when a plugin brings it."""
    names = list(dict.fromkeys(_strings(value, where, len(FEATURES) + 4)))
    for i, name in enumerate(names):
        if not ID.match(name) or (strict and name not in FEATURES):
            raise ManifestError(f'{where}[{i}]', f'one of {", ".join(FEATURES)}')
    return [name for name in names if keep_unknown or name in FEATURES]


def plugin_type(manifest):
    """What a plugin adds, read from its manifest so a maker cannot say it wrong (the editor's tabs): `tiles` for one
    with tiles to put on a page, `hardware` for one that makes a part of a board work (it brings a feature, asks for a
    pin, or is made for certain boards), `functions` for the rest (the top bar, tap actions, a voice, a sound)."""
    if manifest['tiles']:
        return 'tiles'
    if manifest['provides'] or manifest['boards'] != 'any' or any(i['kind'] == 'gpio' for i in manifest['inputs']):
        return 'hardware'
    return 'functions'


def _list(value, where, most):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError(where, 'must be a list')
    if len(value) > most:
        raise ManifestError(where, f'at most {most} entries')
    return value


def _unique(items, where):
    seen = set()
    for i, item in enumerate(items):
        if item['id'] in seen:
            raise ManifestError(f'{where}[{i}].id', f'"{item["id"]}" is used twice')
        seen.add(item['id'])


def _text_key(value, where, keys):
    if not isinstance(value, str) or not TEXT_KEY.match(value):
        raise ManifestError(where, 'must be the key of a text in translations/en.json, part "app"')
    keys.add(value)
    return value


def _number(value, where, low=None, high=None, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (whole and not isinstance(value, int)):
        raise ManifestError(where, 'must be a whole number' if whole else 'must be a number')
    if (low is not None and value < low) or (high is not None and value > high):
        raise ManifestError(where, f'must be between {low} and {high}')
    return value


def _strings(value, where, most=32):
    items = _list(value, where, most)
    if not all(isinstance(item, str) and item for item in items):
        raise ManifestError(where, 'must be a list of words')
    return items


def check_option(option, where, keys, fetch_ids):
    option = _object(option, where, {'id', 'kind', 'label', 'hint', 'default', 'choices', 'options_from', 'min',
                                     'max', 'step', 'unit'}, ('id', 'kind', 'label'))
    _id(option['id'], f'{where}.id')
    kind = option['kind']
    if kind not in OPTION_KINDS:
        raise ManifestError(f'{where}.kind', f'one of {", ".join(OPTION_KINDS)}')
    _text_key(option['label'], f'{where}.label', keys)
    if 'hint' in option:
        _text_key(option['hint'], f'{where}.hint', keys)
    out = {'id': option['id'], 'kind': kind, 'label': option['label'], 'hint': option.get('hint')}
    if kind == 'choice':
        if ('choices' in option) == ('options_from' in option):
            raise ManifestError(where, 'a choice has either "choices" or "options_from"')
        if 'choices' in option:
            choices = _list(option['choices'], f'{where}.choices', 48)
            out['choices'] = []
            for i, choice in enumerate(choices):
                choice = _object(choice, f'{where}.choices[{i}]', {'value', 'label'}, ('value', 'label'))
                if not isinstance(choice['value'], str) or not 0 < len(choice['value']) <= MAX_TEXT:
                    raise ManifestError(f'{where}.choices[{i}].value', f'a text of 1 to {MAX_TEXT} characters')
                out['choices'].append({'value': choice['value'],
                                       'label': _text_key(choice['label'], f'{where}.choices[{i}].label', keys)})
        else:
            if option['options_from'] not in fetch_ids:
                raise ManifestError(f'{where}.options_from', 'must name a fetch of this plugin')
            out['options_from'] = option['options_from']
    elif kind == 'number':
        for key in ('min', 'max'):
            if key not in option:
                raise ManifestError(where, f'a number needs "{key}"')
        out['min'] = _number(option['min'], f'{where}.min')
        out['max'] = _number(option['max'], f'{where}.max')
        if out['min'] >= out['max']:
            raise ManifestError(where, '"min" must be less than "max"')
        out['step'] = _number(option.get('step', 1), f'{where}.step')
        if out['step'] <= 0:
            raise ManifestError(f'{where}.step', 'must be more than 0')
        if 'unit' in option:
            if not isinstance(option['unit'], str) or len(option['unit']) > 8:
                raise ManifestError(f'{where}.unit', 'a unit of at most 8 characters')
            out['unit'] = option['unit']
    for key in ('choices', 'options_from', 'min', 'max', 'step', 'unit'):
        if key in option and key not in out:
            raise ManifestError(f'{where}.{key}', f'does not belong to an option of kind {kind}')
    if 'default' in option:
        out['default'] = option_value(out, option['default'], f'{where}.default')
    return out


def option_value(option, value, where='value'):
    """A tile's value for one option, as the screen gets it; raises ManifestError when it does not fit the option."""
    kind = option['kind']
    if kind == 'toggle':
        if not isinstance(value, bool):
            raise ManifestError(where, 'must be true or false')
        return value
    if kind == 'number':
        _number(value, where, option['min'], option['max'])
        return value
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ManifestError(where, f'a text of at most {MAX_TEXT} characters')
    if kind == 'choice' and option.get('choices') and value and value not in [c['value'] for c in option['choices']]:
        raise ManifestError(where, 'is not one of the choices')
    return value


def check_fields(fields, where):
    """The fields of a map, of a tile of an entity or of an answer: {name: {path, as, tz}}."""
    fields = _object(fields, where, set(fields) if isinstance(fields, dict) else ())
    if not fields or len(fields) > MAX_FIELDS:
        raise ManifestError(where, f'1 to {MAX_FIELDS} fields')
    out = {}
    for name, field in fields.items():
        at = f'{where}.{name}'
        _id(name, at)
        if isinstance(field, str):
            field = {'path': field}
        field = _object(field, at, {'path', 'as', 'tz'}, ('path',))
        kind = field.get('as', 'text')
        if kind not in FIELD_KINDS:
            raise ManifestError(f'{at}.as', f'one of {", ".join(FIELD_KINDS)}')
        if 'tz' in field and (kind != 'epoch' or not isinstance(field['tz'], str)):
            raise ManifestError(f'{at}.tz', 'a time zone such as Europe/Amsterdam, only for "as: epoch"')
        try:
            path = parse_path(field['path'], root=False)
        except ValueError as error:
            raise ManifestError(f'{at}.path', str(error))
        out[name] = {'path': path, 'as': kind, 'tz': field.get('tz')}
    return out


def check_map(spec, where, has_items):
    spec = _object(spec, where, {'items', 'fields', 'where', 'skip', 'sort', 'limit', 'value', 'label'})
    out = {}
    if 'items' in spec:
        try:
            out['items'] = parse_path(spec['items'])
        except ValueError as error:
            raise ManifestError(f'{where}.items', str(error))
        out['items_text'] = spec['items']
    elif has_items:
        raise ManifestError(where, '"items" is required for a list of choices')
    if 'value' in spec or 'label' in spec:
        if 'fields' in spec or not has_items:
            raise ManifestError(where, '"value" and "label" belong to a fetch that fills a list of choices')
        for key in ('value', 'label'):
            paths = spec.get(key, spec.get('value'))
            paths = paths if isinstance(paths, list) else [paths]
            try:
                out[key] = [parse_path(path, root=False) for path in paths]
            except ValueError as error:
                raise ManifestError(f'{where}.{key}', str(error))
        return out
    if 'fields' not in spec:
        raise ManifestError(where, '"fields" names what the screen gets')
    out['fields'] = check_fields(spec['fields'], f'{where}.fields')
    for key in ('where', 'skip'):
        if key in spec:
            rules = _object(spec[key], f'{where}.{key}', set(out['fields']))
            out[key] = {}
            for name, values in rules.items():
                values = values if isinstance(values, list) else [values]
                if not values or not all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in values):
                    raise ManifestError(f'{where}.{key}.{name}', 'a value or a list of values')
                out[key][name] = [str(v) for v in values]
    if 'sort' in spec:
        sort = str(spec['sort'])
        if sort.lstrip('-') not in out['fields']:
            raise ManifestError(f'{where}.sort', 'must name a field (with - in front for the other way round)')
        out['sort'] = sort
    out['limit'] = _number(spec.get('limit', MAX_ITEMS), f'{where}.limit', 1, MAX_ITEMS, whole=True)
    if 'items' not in out and any(key in spec for key in ('where', 'skip', 'sort', 'limit')):
        raise ManifestError(where, '"where", "skip", "sort" and "limit" work on "items"')
    return out


def check_fetch(fetch, where, network, inputs, option_ids, choice_lists):
    fetch = _object(fetch, where, {'id', 'url', 'headers', 'every', 'map'}, ('id', 'url', 'every', 'map'))
    _id(fetch['id'], f'{where}.id')
    url = fetch['url']
    if not isinstance(url, str) or len(url) > 512:
        raise ManifestError(f'{where}.url', 'a URL of at most 512 characters')
    parts = urlsplit(url.replace('{', 'x').replace('}', 'x'))
    host = urlsplit(url).hostname or ''
    if parts.scheme not in ('https', 'http') or not host or '{' in host:
        raise ManifestError(f'{where}.url', 'an https URL with a fixed host')
    if host not in network:
        raise ManifestError(f'{where}.url', f'the host {host} must be named in permissions.network')
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        raise ManifestError(f'{where}.url', 'no user, password or port of its own')
    headers = fetch.get('headers') or {}
    _object(headers, f'{where}.headers', set(headers) if isinstance(headers, dict) else ())
    if len(headers) > 8 or not all(isinstance(k, str) and isinstance(v, str) and len(v) <= 512
                                   for k, v in headers.items()):
        raise ManifestError(f'{where}.headers', 'at most 8 headers, each a text')
    secrets = {i['id'] for i in inputs if i['kind'] == 'secret'}
    known = option_ids | {i['id'] for i in inputs}
    used = set(PLACEHOLDER.findall(url))
    for value in headers.values():
        used |= set(PLACEHOLDER.findall(value))
    unknown = sorted(used - known)
    if unknown:
        raise ManifestError(where, f'{{{unknown[0]}}} is no option of a tile that uses this fetch and no input')
    path = urlsplit(url).path
    if any(name in secrets for name in PLACEHOLDER.findall(path)):
        raise ManifestError(f'{where}.url', 'a secret goes in a header or the query, never in the path')
    if parts.scheme == 'http' and used & secrets:
        raise ManifestError(f'{where}.url', 'a fetch that carries a secret must use https')
    every = seconds(fetch['every'])
    if every is None or every < MIN_EVERY:
        raise ManifestError(f'{where}.every', f'30s or more, written as 30s, 5m, 1h or 1d')
    out = {'id': fetch['id'], 'url': url, 'headers': dict(headers), 'every': every,
           'map': check_map(fetch['map'], f'{where}.map', fetch['id'] in choice_lists),
           'placeholders': sorted(used)}
    if out['map'].get('fields') is not None:
        for name, rules in [(n, r) for key in ('where', 'skip') for n, r in out['map'].get(key, {}).items()]:
            for value in rules:
                for var in PLACEHOLDER.findall(value):
                    if var not in known:
                        raise ManifestError(f'{where}.map', f'{{{var}}} is no option or input')
    for step in out['map'].get('items', []):
        if step[0] == 'var' and step[1] not in known:
            raise ManifestError(f'{where}.map.items', f'{{{step[1]}}} is no option or input')
    return out


def check(manifest, english=None, strict=True):
    """The manifest as the add-on uses it, or ManifestError. `english` is the plugin's translations/en.json; when it is
    given, every text the manifest names must be in its part "app". `strict` (a maker's check, a folder being made)
    refuses a topic or feature this file does not know; the app reading the index (strict=False) leaves an unknown topic
    out and keeps an unknown feature a plugin needs, which then fits no screen, so a newer index never hides a plugin."""
    if not isinstance(manifest, dict):
        raise ManifestError('', 'the manifest must be a mapping')
    manifest = _object(manifest, '', TOP, ('id', 'version', 'api', 'icon', 'maintainer', 'license'))
    keys = {'name', 'summary'}
    out = {'id': _id(manifest['id'], 'id')}
    if not isinstance(manifest['version'], str) or not VERSION.match(manifest['version']):
        raise ManifestError('version', 'three numbers, such as 1.0.0 (quote it in YAML)')
    out['version'] = manifest['version']
    if not isinstance(manifest['api'], str) or not API.match(manifest['api']):
        raise ManifestError('api', 'major.minor in quotes, such as "0.1"')
    out['api'] = manifest['api']
    if not isinstance(manifest['icon'], str) or not MDI.match(manifest['icon']):
        raise ManifestError('icon', 'a Material Design Icons name, such as bus-clock')
    out['icon'] = manifest['icon']
    if not isinstance(manifest['maintainer'], str) or not 0 < len(manifest['maintainer']) <= 39:
        raise ManifestError('maintainer', 'the GitHub name of whoever looks after the plugin')
    out['maintainer'] = manifest['maintainer']
    if manifest['license'] not in LICENSES:
        raise ManifestError('license', f'an SPDX name that goes with AGPL-3.0: {", ".join(LICENSES)}')
    out['license'] = manifest['license']
    stage = manifest.get('stage', 'beta')
    if stage not in STAGES:
        raise ManifestError('stage', f'one of {", ".join(STAGES)}')
    out['stage'] = stage

    topics = _strings(manifest.get('topics'), 'topics', MAX_TOPICS)
    if strict and any(topic not in TOPICS for topic in topics) or not all(ID.match(topic) for topic in topics):
        raise ManifestError('topics', f'one or two of {", ".join(TOPICS)}')
    # A maker names one or two; the app never leaves a plugin out for a missing word (it shows under no topic).
    if not topics and strict:
        raise ManifestError('topics', f'what the plugin is about: one or two of {", ".join(TOPICS)}')
    # A topic this app does not know yet (a newer plugins repository) is left out, not the plugin.
    out['topics'] = list(dict.fromkeys(topic for topic in topics if topic in TOPICS))

    requires = _object(manifest.get('requires') or {}, 'requires', {'esphome', 'psram', 'plugins', 'features'})
    out['requires'] = {'psram': bool(requires.get('psram', False)),
                       'plugins': [_id(p, f'requires.plugins[{i}]')
                                   for i, p in enumerate(_list(requires.get('plugins'), 'requires.plugins', 8))],
                       'features': _features(requires.get('features'), 'requires.features', strict, keep_unknown=True)}
    if out['id'] in out['requires']['plugins']:
        raise ManifestError('requires.plugins', 'a plugin cannot need itself')
    # What it brings for others (0.7): a feature of FEATURES, as the ESPHome component and id the feature promises.
    out['provides'] = _features(manifest.get('provides'), 'provides', strict)
    for i, name in enumerate(out['provides']):
        if name in BOARD_ONLY:
            raise ManifestError(f'provides[{i}]', 'a board brings this one itself, never a plugin')
    if set(out['provides']) & set(out['requires']['features']):
        raise ManifestError('provides', 'a plugin cannot need a feature it brings itself')
    if 'esphome' in requires:
        if not isinstance(requires['esphome'], str) or not re.match(r'^\d{4}\.\d+\.\d+$', requires['esphome']):
            raise ManifestError('requires.esphome', 'an ESPHome version such as 2026.6.2')
        out['requires']['esphome'] = requires['esphome']
    if 'psram' in requires and not isinstance(requires['psram'], bool):
        raise ManifestError('requires.psram', 'true or false')

    boards = manifest.get('boards', 'any')
    if boards != 'any':
        boards = _strings(boards, 'boards')
        if not boards or not all(ID.match(b) for b in boards):
            raise ManifestError('boards', '"any", or a list of board keys from boards.yaml')
    out['boards'] = boards
    out['flash_kb'] = _number(manifest.get('flash_kb', 0), 'flash_kb', 0, 8192)

    permissions = _object(manifest.get('permissions') or {}, 'permissions',
                          {'read_entities', 'home_assistant_actions', 'network', 'ha_commands'})
    network = [host.lower() for host in _strings(permissions.get('network'), 'permissions.network', 8)]
    for i, host in enumerate(network):
        if not HOST.match(host) or is_private_host(host):
            raise ManifestError(f'permissions.network[{i}]', 'a public host name, such as api.example.org')
    out['permissions'] = {
        'read_entities': _strings(permissions.get('read_entities'), 'permissions.read_entities'),
        'home_assistant_actions': _strings(permissions.get('home_assistant_actions'),
                                           'permissions.home_assistant_actions'),
        'network': network,
        'ha_commands': _strings(permissions.get('ha_commands'), 'permissions.ha_commands', 8),
    }
    for i, command in enumerate(out['permissions']['ha_commands']):
        plain = ':' not in command
        if not HA_COMMAND.match(command) or (plain and command.split('/')[0] in FORBIDDEN_COMMANDS):
            raise ManifestError(f'permissions.ha_commands[{i}]', 'a Home Assistant websocket command such as '
                                                                  'history/history_during_period, or call_service:<domain>.<service> '
                                                                  'for an action that answers')
    attributes = _strings(manifest.get('attributes'), 'attributes', len(ATTRIBUTES))
    if any(a not in ATTRIBUTES for a in attributes):
        raise ManifestError('attributes', f'only {", ".join(ATTRIBUTES)}')
    out['attributes'] = attributes
    if 'cloud' in attributes or network:
        privacy = manifest.get('privacy')
        if not isinstance(privacy, str) or not privacy.startswith('https://'):
            raise ManifestError('privacy', 'a plugin that reaches a service outside the home links its privacy '
                                           'statement (https://...)')
        out['privacy'] = privacy
    if network and 'cloud' not in attributes:
        raise ManifestError('attributes', 'a plugin with permissions.network has the attribute cloud')

    inputs = []
    for i, item in enumerate(_list(manifest.get('inputs'), 'inputs', MAX_INPUTS)):
        where = f'inputs[{i}]'
        item = _object(item, where, {'id', 'kind', 'scope', 'label', 'hint', 'domains'}, ('id', 'kind', 'label'))
        if item['kind'] not in INPUT_KINDS:
            raise ManifestError(f'{where}.kind', f'one of {", ".join(INPUT_KINDS)}')
        # An entity the plugin's ESPHome part reads itself (a `homeassistant` sensor): which domains it takes.
        domains = _strings(item.get('domains'), f'{where}.domains', 8)
        if (item['kind'] == 'entity') != bool(domains) or not all(re.match(r'^[a-z_]+$', d) for d in domains):
            raise ManifestError(f'{where}.domains', 'an input of kind entity names its domains, such as [calendar]')
        scope = item.get('scope', 'all' if item['kind'] == 'secret' else 'screen')
        if scope not in ('all', 'screen'):
            raise ManifestError(f'{where}.scope', 'all or screen')
        inputs.append({'id': _id(item['id'], f'{where}.id'), 'kind': item['kind'], 'scope': scope, 'domains': domains,
                       'label': _text_key(item['label'], f'{where}.label', keys),
                       'hint': _text_key(item['hint'], f'{where}.hint', keys) if 'hint' in item else None})
    _unique(inputs, 'inputs')
    out['inputs'] = inputs

    parts = []
    for i, item in enumerate(_list(manifest.get('parts'), 'parts', 4)):
        where = f'parts[{i}]'
        item = _object(item, where, {'id', 'file', 'label', 'hint', 'flash_kb', 'default', 'features'},
                       ('id', 'file', 'label'))
        if not isinstance(item['file'], str) or not re.match(r'^[a-z0-9_/-]+\.yaml$', item['file']) \
                or '..' in item['file']:
            raise ManifestError(f'{where}.file', 'a .yaml file inside the plugin, such as parts/tests.yaml')
        parts.append({'id': _id(item['id'], f'{where}.id'), 'file': item['file'],
                      'label': _text_key(item['label'], f'{where}.label', keys),
                      'hint': _text_key(item['hint'], f'{where}.hint', keys) if 'hint' in item else None,
                      'flash_kb': _number(item.get('flash_kb', 0), f'{where}.flash_kb', 0, 8192),
                      'default': bool(item.get('default', False)),
                      # A part that uses a feature when the screen has one (0.7): offered, and built, only then. A
                      # voice plugin answers out loud with a part that needs a speaker, and listens without one.
                      'features': _features(item.get('features'), f'{where}.features', strict, keep_unknown=True)})
    _unique(parts, 'parts')
    out['parts'] = parts

    raw_fetches = _list(manifest.get('fetch'), 'fetch', MAX_FETCHES)
    fetch_ids = set()
    for i, item in enumerate(raw_fetches):
        if isinstance(item, dict) and isinstance(item.get('id'), str):
            fetch_ids.add(item['id'])

    tiles, choice_lists, option_ids_of = [], set(), {}
    for i, item in enumerate(_list(manifest.get('tiles'), 'tiles', MAX_TILES)):
        where = f'tiles[{i}]'
        item = _object(item, where, {'id', 'name', 'icon', 'sizes', 'memory', 'domains', 'data', 'options',
                                     'example', 'preview', 'attributes', 'has_attributes', 'fields'},
                       ('id', 'name', 'sizes', 'memory'))
        tile = {'id': _id(item['id'], f'{where}.id'), 'name': _text_key(item['name'], f'{where}.name', keys)}
        icon = item.get('icon', out['icon'])
        if not isinstance(icon, str) or not MDI.match(icon):
            raise ManifestError(f'{where}.icon', 'a Material Design Icons name')
        tile['icon'] = icon
        sizes = _object(item['sizes'], f'{where}.sizes', {'min', 'max', 'full'}, ('min', 'max'))
        low, high = span(sizes['min']), span(sizes['max'])
        if not low or not high:
            raise ManifestError(f'{where}.sizes', 'min and max as columns x rows, such as 1x1 and 2x2')
        if low[0] > high[0] or low[1] > high[1]:
            raise ManifestError(f'{where}.sizes', 'min must not be larger than max')
        tile.update(min=sizes['min'], max=sizes['max'], full=bool(sizes.get('full', False)))
        memory = item['memory']
        if isinstance(memory, dict):
            memory = _object(memory, f'{where}.memory', {'bytes'}, ('bytes',))['bytes']
        tile['memory'] = _number(memory, f'{where}.memory', 64, MAX_TILE_BYTES, whole=True)
        # A tile that belongs to an entity names the domains it takes, as a tap action and an input of kind entity do
        # (`domains: [calendar]`); the inspector then offers the entities of those domains.
        domains = _strings(item.get('domains'), f'{where}.domains', 8)
        if not all(re.match(r'^[a-z_]+$', domain) for domain in domains):
            raise ManifestError(f'{where}.domains', 'Home Assistant domains, such as [climate]')
        tile['domains'] = domains
        # What the tile gets of its entity besides its state: the attributes it names, bounded as every tile's.
        attributes = _strings(item.get('attributes'), f'{where}.attributes', MAX_ATTRIBUTES)
        if attributes and not domains:
            raise ManifestError(f'{where}.attributes', 'only a tile with "domains" belongs to an entity and gets attributes')
        if not all(re.match(r'^[a-z_][a-z0-9_]{0,47}$', a) for a in attributes):
            raise ManifestError(f'{where}.attributes', 'attribute names such as next_date')
        tile['attributes'] = attributes
        # The attributes an entity must have to be offered for the tile (0.5): `[raw_today]` keeps the inspector's list
        # to the price sensors among a home's hundreds of sensors. Only the list: a tile keeps its entity when an
        # attribute is gone for a while (an entity that is unavailable has none).
        has = _strings(item.get('has_attributes'), f'{where}.has_attributes', MAX_HAS_ATTRIBUTES)
        if has and not domains:
            raise ManifestError(f'{where}.has_attributes', 'only a tile with "domains" belongs to an entity')
        if not all(re.match(r'^[a-z_][a-z0-9_]{0,47}$', a) for a in has):
            raise ManifestError(f'{where}.has_attributes', 'attribute names such as raw_today')
        tile['has_attributes'] = has
        # Fields taken out of the entity's attributes (0.5), with the map's paths and kinds: `raw_today[*].value` as
        # numbers is one list of prices instead of a list of objects the screen has no room for.
        if 'fields' in item:
            if not domains:
                raise ManifestError(f'{where}.fields', 'only a tile with "domains" belongs to an entity and gets fields')
            tile['fields'] = check_fields(item['fields'], f'{where}.fields')
            for name in tile['fields']:
                if name in attributes or name in ('state', 'name'):
                    raise ManifestError(f'{where}.fields.{name}', 'a field is named apart from the attributes, state and name')
        else:
            tile['fields'] = {}
        if 'data' in item:
            if item['data'] not in fetch_ids:
                raise ManifestError(f'{where}.data', 'must name a fetch of this plugin')
            tile['data'] = item['data']
        options = [check_option(option, f'{where}.options[{j}]', keys, fetch_ids)
                   for j, option in enumerate(_list(item.get('options'), f'{where}.options', MAX_OPTIONS))]
        _unique(options, f'{where}.options')
        tile['options'] = options
        for option in options:
            if option.get('options_from'):
                choice_lists.add(option['options_from'])
        if 'example' in item:
            tile['example'] = _text_key(item['example'], f'{where}.example', keys)
        if 'preview' in item:
            if 'data' not in tile and not tile['domains']:
                raise ManifestError(f'{where}.preview', 'a preview is drawn from the tile\'s data or entity: it needs '
                                                        '"data" or "domains"')
            preview = _object(item['preview'], f'{where}.preview', set(PREVIEW))
            for key, value in preview.items():
                if not isinstance(value, str) or not 0 < len(value) <= 64:
                    raise ManifestError(f'{where}.preview.{key}', 'a text of at most 64 characters')
            if 'value' in preview and 'countdown' in preview:
                raise ManifestError(f'{where}.preview', 'either "value" or "countdown"')
            tile['preview'] = dict(preview)
        option_ids_of[tile['id']] = {option['id'] for option in options}
        tiles.append(tile)
    _unique(tiles, 'tiles')
    out['tiles'] = tiles

    fetches = []
    for i, item in enumerate(raw_fetches):
        users = [t for t in tiles if t.get('data') == (item or {}).get('id')
                 or any(o.get('options_from') == (item or {}).get('id') for o in t['options'])]
        option_ids = set().union(*(option_ids_of[t['id']] for t in users)) if users else set()
        fetches.append(check_fetch(item, f'fetch[{i}]', network, inputs, option_ids, choice_lists))
    _unique(fetches, 'fetch')
    for fetch in fetches:
        if fetch['id'] in choice_lists and 'value' not in fetch['map']:
            raise ManifestError(f'fetch.{fetch["id"]}.map', 'a fetch that fills a list of choices maps "value" '
                                                           'and "label"')
        if fetch['id'] not in choice_lists and 'fields' not in fetch['map']:
            raise ManifestError(f'fetch.{fetch["id"]}.map', 'a fetch a tile shows maps "fields"')
    out['fetch'] = fetches
    for i, tile in enumerate(tiles):
        if 'preview' not in tile:
            continue
        if tile.get('data'):
            fields = dict(next(f for f in fetches if f['id'] == tile['data'])['map'].get('fields') or {})
        else:
            # A tile of an entity: its state, its name, and the attributes it names (a moment as seconds, see below).
            fields = {name: {'as': 'text'} for name in ('state', 'name', *tile['attributes'])}
            fields.update({name: {'as': 'epoch'} for name in tile['attributes'] if name.endswith(('_at', '_time', 'date'))})
            fields.update(tile['fields'])
        for key, value in tile['preview'].items():
            names = [value] if key == 'countdown' else PLACEHOLDER.findall(value)
            for name in names:
                if name not in fields:
                    raise ManifestError(f'tiles[{i}].preview.{key}', f'"{name}" is no field of the tile\'s data')
            if key == 'countdown' and fields[value]['as'] != 'epoch':
                raise ManifestError(f'tiles[{i}].preview.countdown', f'"{value}" must be a field with "as: epoch"')
    for name in sorted(fetch_ids - {f['id'] for f in fetches}):
        raise ManifestError('fetch', f'"{name}" is used but not described')

    # What the screen gets of an answer to a command of `permissions.ha_commands` (0.5): its fields, as a fetch's, so
    # 96 prices of a quarter of an hour arrive as one list of numbers instead of 8 KB of objects cut to a quarter.
    # A command without an entry here sends its answer as it is, bounded.
    answers = []
    for i, item in enumerate(_list(manifest.get('answers'), 'answers', MAX_ANSWERS)):
        where = f'answers[{i}]'
        item = _object(item, where, {'command', 'fields'}, ('command', 'fields'))
        if item['command'] not in out['permissions']['ha_commands']:
            raise ManifestError(f'{where}.command', 'must be a command of permissions.ha_commands')
        if item['command'] in [a['command'] for a in answers]:
            raise ManifestError(f'{where}.command', f'"{item["command"]}" is mapped twice')
        answers.append({'command': item['command'], 'fields': check_fields(item['fields'], f'{where}.fields')})
    out['answers'] = answers

    cards = []
    for i, item in enumerate(_list(manifest.get('cards'), 'cards', 8)):
        where = f'cards[{i}]'
        item = _object(item, where, {'id', 'name', 'wide'}, ('id', 'name'))
        if 'wide' in item and not isinstance(item['wide'], bool):
            raise ManifestError(f'{where}.wide', 'true or false')
        cards.append({'id': _id(item['id'], f'{where}.id'), 'name': _text_key(item['name'], f'{where}.name', keys),
                      'wide': bool(item.get('wide', False))})
    _unique(cards, 'cards')
    out['cards'] = cards
    taps = []
    for i, item in enumerate(_list(manifest.get('tap_actions'), 'tap_actions', 8)):
        where = f'tap_actions[{i}]'
        item = _object(item, where, {'id', 'label', 'domains', 'card'}, ('id', 'label', 'domains'))
        domains = _strings(item['domains'], f'{where}.domains', 16)
        if not domains or not all(re.match(r'^[a-z_]+$', d) for d in domains):
            raise ManifestError(f'{where}.domains', 'Home Assistant domains, such as climate')
        if 'card' in item and item['card'] not in {c['id'] for c in cards}:
            raise ManifestError(f'{where}.card', 'must name a card of this plugin')
        taps.append({'id': _id(item['id'], f'{where}.id'), 'label': _text_key(item['label'], f'{where}.label', keys),
                     'domains': domains, 'card': item.get('card')})
    _unique(taps, 'tap_actions')
    out['tap_actions'] = taps
    bar = []
    for i, item in enumerate(_list(manifest.get('bar_items'), 'bar_items', 4)):
        where = f'bar_items[{i}]'
        item = _object(item, where, {'id', 'label', 'icon', 'example'}, ('id', 'label'))
        icon = item.get('icon', out['icon'])
        if not isinstance(icon, str) or not MDI.match(icon):
            raise ManifestError(f'{where}.icon', 'a Material Design Icons name')
        bar.append({'id': _id(item['id'], f'{where}.id'), 'label': _text_key(item['label'], f'{where}.label', keys),
                    'icon': icon, 'example': _text_key(item['example'], f'{where}.example', keys) if 'example' in item else None})
    _unique(bar, 'bar_items')
    out['bar_items'] = bar
    # The plugin's settings as the editor shows them under Screen settings: ESPHome entities of its plugin.yaml (a
    # template switch, number or select), by the end of their entity id on the screen's device ("waste_in_top_bar").
    # A key is the entity's name in plugin.yaml as ESPHome writes it in an id ("Tap sound" is tap_sound), which is also
    # the end of its entity id until someone renames it. A switch, number, select, text or button (0.6); `status` (0.6)
    # names a text sensor the row shows beside a button, live ("Heard: Okay Nabu").
    settings = []
    for i, item in enumerate(_list(manifest.get('settings'), 'settings', 8)):
        where = f'settings[{i}]'
        item = _object(item, where, {'key', 'label', 'hint', 'status'}, ('key', 'label'))
        for field in ('key', 'status'):
            if field in item and (not isinstance(item[field], str) or not re.match(r'^[a-z0-9_]{1,64}$', item[field])):
                raise ManifestError(f'{where}.{field}', 'the name of the entity in plugin.yaml as an id: "Tap sound" is '
                                                        'tap_sound')
        settings.append({'key': item['key'], 'label': _text_key(item['label'], f'{where}.label', keys),
                         'hint': _text_key(item['hint'], f'{where}.hint', keys) if 'hint' in item else None,
                         'status': item.get('status')})
    out['settings'] = settings

    out['text_keys'] = sorted(keys)
    if english is not None:
        missing_texts(out, english)
    return out


def missing_texts(manifest, english):
    """Raise when translations/en.json lacks a text the manifest names."""
    app = (english or {}).get('app') if isinstance(english, dict) else None
    if not isinstance(app, dict):
        raise ManifestError('translations/en.json', 'needs a part "app" with the texts the editor shows')
    for key in manifest['text_keys']:
        if not isinstance(app.get(key), str) or not app[key].strip():
            raise ManifestError('translations/en.json', f'part "app" lacks "{key}"')
    screen = english.get('screen', {})
    if not isinstance(screen, dict) or not all(isinstance(v, str) for v in screen.values()):
        raise ManifestError('translations/en.json', 'part "screen" holds texts only')


def texts(manifest, translations):
    """The words the editor shows for this plugin, per key and language: {key: {lang: text}}. English is always there
    (checked); another language may lack a key, and the editor then falls back to English and says so."""
    out = {}
    for key in manifest['text_keys']:
        out[key] = {lang: data['app'][key] for lang, data in translations.items()
                    if isinstance(data, dict) and isinstance(data.get('app'), dict)
                    and isinstance(data['app'].get(key), str)}
    return out


def complete_languages(manifest, translations):
    """The languages whose part "app" has every key the manifest names, and whose part "screen" has every key English
    has."""
    english = set((translations.get('en') or {}).get('screen') or {})
    done = []
    for lang, data in sorted(translations.items()):
        if not isinstance(data, dict):
            continue
        app, screen = data.get('app') or {}, data.get('screen') or {}
        if all(key in app for key in manifest['text_keys']) and english <= set(screen):
            done.append(lang)
    return done


def permission_hash(manifest):
    """What a person agreed to, as one short fingerprint: when an update asks for more, it differs."""
    import hashlib
    import json
    # The rights of plugin API 0.1 always count; a kind of right added since counts only when the plugin asks for it,
    # so a new kind in this app never makes every installed plugin ask again.
    first = ('read_entities', 'home_assistant_actions', 'network')
    permissions = {key: value for key, value in manifest['permissions'].items() if key in first or value}
    data = {'permissions': permissions, 'attributes': sorted(manifest['attributes'])}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
