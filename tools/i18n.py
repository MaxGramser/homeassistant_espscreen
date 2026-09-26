#!/usr/bin/env python3
"""The translations in screen_manager/translations/ (app 0.2.90); docs/TRANSLATING.md says how they work.

    python3 tools/i18n.py check            every language against English: keys, placeholders, plural forms, letters
                                            the screens can't draw, screen texts much longer than the English
    python3 tools/i18n.py lint             English words left in the firmware's code instead of the translations
    python3 tools/i18n.py header [--check]  write (or compare) the key header and the tests' English table that the
                                            firmware's `screen` texts need, after changing the keys of en.json
    python3 tools/i18n.py cldr [--write]    day and month names, date orders and the decimal mark from the Unicode CLDR
                                            (Node's Intl), into every language's screen.date and screen.number, and the
                                            clock and numbers of every Home Assistant language (screen_manager/app/regions.json)
    python3 tools/i18n.py ha-words [--write] Home Assistant's own words for states (screen.ha) in every language, from a
                                            Home Assistant (HA_URL and HA_TOKEN); needs aiohttp
    python3 tools/i18n.py new CODE NAME ENGLISH PLURAL
                                            a new language file, such as `new sv Svenska Swedish one_other`
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'screen_manager' / 'translations'
KEYS_HEADER = ROOT / 'components' / 'smart_display' / 'screen_text_keys.h'
TESTS_HEADER = ROOT / 'tests' / 'screen_text_en.h'
CORE = ROOT / 'packages' / 'core.yaml'


def generator():
    """components/smart_display/screen_text_gen.py, which the firmware build itself uses."""
    spec = importlib.util.spec_from_file_location('screen_text_gen', ROOT / 'components' / 'smart_display' / 'screen_text_gen.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def languages():
    """{code: data} of every language file, English first."""
    found = {path.stem: json.loads(path.read_text(encoding='utf-8')) for path in sorted(FOLDER.glob('*.json'))
             if re.fullmatch(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?', path.stem)}
    return dict(sorted(found.items(), key=lambda item: (item[0] != 'en', item[0])))


def header(check):
    gen = generator()
    wanted = {KEYS_HEADER: gen.keys_header([key for key, _ in gen.screen_pairs(gen.load('en', FOLDER))]),
              TESTS_HEADER: gen.english_header(FOLDER)}
    stale = [path for path, text in wanted.items() if not path.exists() or path.read_text(encoding='utf-8') != text]
    if check:
        for path in stale:
            print(f'{path.relative_to(ROOT)} is out of date: run python3 tools/i18n.py header')
        return 1 if stale else 0
    for path in stale:
        path.write_text(wanted[path], encoding='utf-8')
        print(f'wrote {path.relative_to(ROOT)}')
    return 0


PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')
FORMS = {'one_other': 2, 'one_upto_1': 2, 'slavic_pl': 3, 'east_slavic': 3, 'none': 1}


def font_letters():
    """The characters every text font of the screens carries: what a `screen` text may use."""
    text = CORE.read_text(encoding='utf-8')
    sets = []
    for block in re.finditer(r'(?ms)^  - file: "\$\{FONT_DIR\}/Roboto-\d+\.ttf"\n(.*?)(?=^  - |^\S|\Z)', text):
        body = block.group(1)
        if not re.search(r'(?m)^\s+id: (headline|label|sublabel|sublabel_big|watch_value)\s*$', body):
            continue
        glyphs = re.search(r'(?s)glyphs:\s*\[(.*?)\]', body)
        if glyphs:
            letters = set()
            for item in re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", glyphs.group(1)):
                letters.update(item[0] or item[1])
            sets.append(letters)
    return set.intersection(*sets) if sets else set()


def check():
    gen = generator()
    langs = languages()
    english = langs['en']
    problems, notes = [], []
    base = dict(gen.flatten({k: v for k, v in english.items() if k != '_meta'}))
    drawable = font_letters()
    width = text_width()
    if width is None:
        notes.append('Pillow is missing: tile texts were not measured')
    for code, data in langs.items():
        meta = data.get('_meta', {})
        for field in ('name', 'english', 'script', 'plural', 'checked'):
            if field not in meta:
                problems.append(f'{code}: _meta.{field} is missing')
        forms = FORMS.get(meta.get('plural'))
        if forms is None:
            problems.append(f'{code}: _meta.plural must be one of {", ".join(FORMS)}')
        own = dict(gen.flatten({k: v for k, v in data.items() if k != '_meta'}))
        for key in own.keys() - base.keys():
            problems.append(f'{code}: {key} is not in en.json')
        missing = [key for key in base if key not in own]
        # Regional variants intentionally override only their base language,
        # for example British spelling over en. Full languages must be complete.
        if '-' in code and code.split('-')[0] in langs:
            parent = dict(gen.flatten({k: v for k, v in langs[code.split('-')[0]].items() if k != '_meta'}))
            missing = [key for key in missing if key not in parent]
        if code != 'en' and missing:
            problems.append(f'{code}: missing translations: {", ".join(missing)}')
        for key, text in own.items():
            if key not in base or not isinstance(text, str):
                continue
            source = base[key]
            if key in EITHER_PLACEHOLDER:
                if not set(PLACEHOLDER.findall(text)) <= EITHER_PLACEHOLDER[key]:
                    problems.append(f'{code}: {key} has placeholders beyond {sorted(EITHER_PLACEHOLDER[key])}')
            elif set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(source)):
                problems.append(f'{code}: {key} has placeholders {sorted(set(PLACEHOLDER.findall(text)))}, '
                                f'English {sorted(set(PLACEHOLDER.findall(source)))}')
            plural = ' | ' in source
            if plural and forms and len(text.split('|')) not in (1, forms):
                problems.append(f'{code}: {key} needs {forms} forms separated by " | "')
            if not plural and '|' in text:
                problems.append(f'{code}: {key} has a | that isn\'t a plural form')
            # The editor's vue-i18n reads { } and @ as instructions: only placeholders and its {'x'} literals are allowed.
            if key.startswith('editor.') and re.search(r"[{}@]", re.sub(r"\{'[^']*'\}", '', PLACEHOLDER.sub('', text))):
                problems.append(f'{code}: {key} has {{, }} or @ outside a placeholder; the editor would misread it')
            # The app's own words for the screens (addon.screen) are drawn by the same fonts.
            if key.startswith(('screen.', 'addon.screen.')) and drawable:
                shown = PLACEHOLDER.sub('', text).replace('|', '')
                unknown = sorted(set(shown) - drawable - {'\n'})
                if unknown:
                    problems.append(f'{code}: {key} uses letters the screens can\'t draw: {"".join(unknown)}')
                # Home Assistant's words and the calendar's are what they are; our own texts should stay about as short.
                ours = not key.startswith(('screen.ha.', 'screen.date.', 'screen.number.'))
                if ours and code != 'en' and len(text) > max(8, len(source) * 1.6) and not plural:
                    notes.append(f'{code}: {key} is much longer than the English ({len(text)} vs {len(source)})')
                if width and key in TILE_LINES:
                    shown_text = text
                    for name, sample in TILE_SAMPLES.items():
                        shown_text = shown_text.replace('{' + name + '}', sample)
                    for board, (size, room) in TILE_LINES[key].items():
                        if width(size, shown_text) > room:
                            problems.append(f'{code}: {key} "{shown_text}" is too wide for a tile on the {board} '
                                            f'({width(size, shown_text):.0f} of {room} px); make it shorter')
                # The weather columns of the CYD hold a day of two letters beside its icon.
                if key.startswith('screen.date.weekdays_min.') and len(text) > 2:
                    problems.append(f'{code}: {key} "{text}" is longer than two letters; the CYD\'s weather columns cut it')
    for line in notes:
        print('note:', line)
    for line in problems:
        print('problem:', line)
    print(f'{len(langs)} languages, {len(base)} texts: {len(problems)} problems')
    return 1 if problems else 0


# One line under a tile's name, and the room it has there: Roboto 400 at the CYD's 11 px in about 88 px, at the
# Guition's 16 px in about 128 px (packages/boards: TILE_W, FONT_SUBLABEL_SIZE). A longer text is cut; `check` fails.
TILE_ROOM = {'CYD': (11, 88), 'Guition': (16, 128)}
# Camera tiles are the Guition's alone.
TILE_LINES = {'screen.tile.tap_to_open': TILE_ROOM, 'screen.script.never_run': TILE_ROOM, 'screen.script.running': TILE_ROOM,
              'screen.media.not_playing': TILE_ROOM, 'screen.timer.paused': TILE_ROOM,
              'screen.script.last_time': TILE_ROOM, 'screen.script.yesterday_time_short': TILE_ROOM,
              'screen.camera.tap_to_view': {'Guition': TILE_ROOM['Guition']},
              'screen.camera.no_image_yet': {'Guition': TILE_ROOM['Guition']}}
# What a placeholder stands for while a tile line is measured: the widest clock a screen writes is a 12-hour one
# with its AM/PM ("Yesterday 9:15 PM" is why screen.script.yesterday_time_short exists).
TILE_SAMPLES = {'time': '9:15 PM'}


def text_width():
    """(size, text) -> pixels in the screens' Roboto 400, or None without Pillow (the check then skips widths)."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    fonts = {}
    def width(size, text):
        if size not in fonts:
            fonts[size] = ImageFont.truetype(str(ROOT / 'fonts' / 'Roboto-400.ttf'), size)
        return fonts[size].getlength(text)
    return width


# Texts whose placeholders a language picks from a set: the top bar's date takes the weekday's abbreviation ({weekday},
# "sam.") or its two letters ({weekday_min}, "Sa" in English).
EITHER_PLACEHOLDER = {'screen.date.top_bar': {'weekday', 'weekday_min', 'day', 'month'}}

# English that stays in the firmware on purpose, with why. Everything else a screen shows comes from the translations,
# and `lint` fails on a new English text in the code, so it never slips back in.
LINT_KEEP = {
    # Statuses the app reads and acts on (screen_manager/app/server.py RESEND_STATES, the "Error" prefix): protocol.
    'Synced', 'Loading tiles', 'Layout received', 'Resend needed', 'Ready for tile configuration',
    'Use the Easy Setup profile', 'Swipe test started', 'Heap walked', 'Kept pages set', 'no answer', 'Error: message too large',
    'Error: invalid message', 'Error: protocol version', 'Error: screen settings', 'Error: outdated tile',
    'Error: no memory for ', 'Error: incomplete message', 'Error: invalid encoding',
    # Protocol 2 handshakes/refusals stay stable across screen languages. The
    # configuration problem shown on the glass uses a translated key below.
    'Configuration problem. Update add-on.', 'Session:', 'Error: obsolete message',
    'Error: layout', 'Error: invalid layout', 'Error: incomplete layout', 'Error: insufficient layout memory',
    'Error: outdated tile or configuration in state',
    # Only a log line or the rate limiter's reason shows these.
    'history range', 'card button ', 'header navigation', 'media key ', 'let go', 'too short (', 'already handled in this contact',
    'same button within the debounce window', 'no runtime tiles', 'setting off', 'screen dimmed', 'card open',
    'detail card open', 'camera open', 'a slider is being dragged', 'USB calibration ready; no tile actions',
    'GT911 touch test ready; no tile actions',
    'configuration not ready',
    'UI_TEST START: page/overlay render stress, no HA actions', 'Color', 'Color temperature', 'Brightness',
    # Home Assistant's own values and units the code compares with, not words it shows.
    'None', 'Auto', 'Wh',
    # Placeholders of the YAML tree that the runtime tiles replace before a screen shows them, and profile defaults.
    'Lamp', 'Plug', 'Evening', 'All off', 'AC', 'Vacuum', 'Tile 7', 'Tile 8', 'Tile 9', 'Tile 10', 'Light', 'Light Color',
    'Climate', 'Example lamp', 'My CYD', 'My Guition', 'My Guition 10', 'My Guition 7', 'My Guition 7 V2', 'My Waveshare', 'My Waveshare 7', 'My Waveshare 4B',
}
LINT_FILES = ('components/smart_display/*.h', 'packages/core.yaml', 'packages/boards/*.yaml', 'packages/looks/*.yaml',
              'packages/features/*.yaml', 'packages/hardware/*.yaml')


def lint():
    """English words in the firmware's code that should be a key of the translations' `screen` section."""
    literal = re.compile(r'"((?:[^"\\]|\\.)*)"')
    found = []
    for pattern in LINT_FILES:
        for path in sorted(ROOT.glob(pattern)):
            # Lab boards (packages/boards/lab-*.yaml) are written by the responsive lab and never released.
            if path.name.startswith('lab-'):
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                stripped = line.strip()
                # Comments, logs, and Home Assistant's entity names (renaming one gives it a new entity id).
                if stripped.startswith(('//', '#', '*')) or 'ESP_LOG' in line or 'static_assert' in line or re.match(r'\s*name: "', line):
                    continue
                code = line.split('//')[0]
                if path.suffix == '.yaml':
                    code = re.split(r'\s#', code)[0]
                for match in literal.finditer(code):
                    text = match.group(1)
                    if text in LINT_KEEP or re.search(r'[();]|::|->|\$\{', text):
                        continue
                    if re.match(r'^[A-Z][a-z]', text) or re.search(r'[A-Za-z]{2,} [a-z]{2,}', text):
                        found.append(f'{path.relative_to(ROOT)}:{number}: "{text}"')
    for line in found:
        print('English in the firmware (a key of screen_manager/translations/en.json, or tools/i18n.py LINT_KEEP):', line)
    return 1 if found else 0


# Where screen.ha's words come from: Home Assistant's own translations (frontend/get_translations, `entity_component`),
# so a screen says what Home Assistant says in the same language.
def ha_sources():
    sources = {'on': 'component.switch.entity_component._.state.on', 'off': 'component.switch.entity_component._.state.off'}
    for mode in ('off', 'heat', 'cool', 'heat_cool', 'auto', 'dry', 'fan_only'):
        sources[f'climate.{mode}'] = f'component.climate.entity_component._.state.{mode}'
    for action in ('heating', 'cooling', 'idle', 'off', 'drying', 'fan', 'preheating', 'defrosting'):
        sources[f'hvac_action.{action}'] = f'component.climate.entity_component._.state_attributes.hvac_action.state.{action}'
    # The fan and swing settings Home Assistant names itself; an integration's own modes stay as it reports them.
    for mode in ('auto', 'low', 'medium', 'high', 'middle', 'focus', 'diffuse', 'top', 'on', 'off'):
        sources[f'climate_fan.{mode}'] = f'component.climate.entity_component._.state_attributes.fan_mode.state.{mode}'
    for mode in ('on', 'off', 'both', 'vertical', 'horizontal'):
        sources[f'climate_swing.{mode}'] = f'component.climate.entity_component._.state_attributes.swing_mode.state.{mode}'
    for state in ('open', 'closed', 'opening', 'closing'):
        sources[f'cover.{state}'] = f'component.cover.entity_component._.state.{state}'
    for state in ('playing', 'paused', 'idle', 'standby'):
        sources[f'media.{state}'] = f'component.media_player.entity_component._.state.{state}'
    for state in ('home', 'not_home'):
        sources[f'person.{state}'] = f'component.person.entity_component._.state.{state}'
    for state in ('above_horizon', 'below_horizon'):
        sources[f'sun.{state}'] = f'component.sun.entity_component._.state.{state}'
    for state in ('docked', 'cleaning', 'paused', 'returning', 'idle'):
        sources[f'vacuum.{state}'] = f'component.vacuum.entity_component._.state.{state}'
    for state in ('disarmed', 'armed_home', 'armed_away', 'armed_night', 'armed_vacation', 'armed_custom_bypass', 'pending',
                  'arming', 'disarming', 'triggered'):
        sources[f'alarm.{state}'] = f'component.alarm_control_panel.entity_component._.state.{state}'
    english = json.loads((FOLDER / 'en.json').read_text(encoding='utf-8'))['screen']['ha']
    for key in english['weather']:
        sources[f'weather.{key}'] = f'component.weather.entity_component._.state.{key.replace("_", "-") if key != "partlycloudy" else key}'
    for key in english['binary']:
        device_class, state = key.rsplit('_', 1)
        sources[f'binary.{key}'] = f'component.binary_sensor.entity_component.{device_class}.state.{state}'
    return sources


# The words Home Assistant's frontend itself shows (its own translation files, not the backend's).
FRONTEND_SOURCES = {'unavailable': 'state.default.unavailable', 'button.activate': 'ui.card.scene.activate',
                    'button.run': 'ui.card.script.run', 'button.press': 'ui.card.button.press',
                    # The alarm panel's modes and keys, as its dialog and its alarm panel card name them (firmware 0.3.3+).
                    **{f'alarm_mode.{mode}': f'ui.card.alarm_control_panel.modes.{mode}'
                       for mode in ('armed_home', 'armed_away', 'armed_night', 'armed_vacation', 'armed_custom_bypass', 'disarmed')},
                    **{f'alarm_action.{key}': f'ui.card.alarm_control_panel.{key}'
                       for key in ('disarm', 'arm_home', 'arm_away', 'arm_night', 'arm_vacation', 'arm_custom_bypass')},
                    'alarm_action.enter_code': 'ui.dialogs.enter_code.title'}


def frontend_words(url, codes):
    """{code: {key: word}} from the translation files Home Assistant's frontend loads (their names carry a hash that the
    frontend's app script lists)."""
    import urllib.request
    page = urllib.request.urlopen(url + '/', timeout=20).read().decode('utf-8', 'replace')
    found = {}
    for script in dict.fromkeys(re.findall(r'(/frontend_latest/app\.[\w.]+\.js)', page)):
        text = urllib.request.urlopen(url + script, timeout=30).read().decode('utf-8', 'replace')
        for code in codes:
            match = re.search(r'"' + re.escape(code) + r'":\{"nativeName":"[^"]*","hash":"([0-9a-f]+)"', text)
            if match and code not in found:
                data = json.loads(urllib.request.urlopen(f'{url}/static/translations/{code}-{match.group(1)}.json', timeout=30).read())
                flat = dict(generator().flatten(data))
                found[code] = {key: flat[source] for key, source in FRONTEND_SOURCES.items() if isinstance(flat.get(source), str)}
    return found


def ha_words(write):
    """screen.ha of every language from a Home Assistant (HA_URL and HA_TOKEN, or .esphome/ha_url and ha_token): its own
    words for states, English included, so a screen says what Home Assistant says (Max, app 0.2.90)."""
    import asyncio
    import os
    try:
        import aiohttp
    except ImportError:
        raise SystemExit('ha-words needs aiohttp (.venv-portal/bin/python has it)')
    def setting(name, file):
        value = os.environ.get(name)
        for folder in (ROOT, ROOT.parent / 'esphome-cyd-display'):
            if not value and (folder / '.esphome' / file).exists():
                value = (folder / '.esphome' / file).read_text().strip()
        if not value:
            raise SystemExit(f'Set {name} or .esphome/{file}')
        return value
    url, token = setting('HA_URL', 'ha_url').rstrip('/'), setting('HA_TOKEN', 'ha_token')
    sources = ha_sources()

    async def fetch(codes):
        found = {}
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url.replace('http', 'ws', 1) + '/api/websocket') as ws:
                await ws.receive_json()
                await ws.send_json({'type': 'auth', 'access_token': token})
                if (await ws.receive_json()).get('type') != 'auth_ok':
                    raise SystemExit('Home Assistant refused the token')
                for number, code in enumerate(codes, 1):
                    await ws.send_json({'id': number, 'type': 'frontend/get_translations', 'language': code, 'category': 'entity_component'})
                    answer = await ws.receive_json()
                    found[code] = (answer.get('result') or {}).get('resources') or {}
        return found

    langs = languages()
    found = asyncio.run(fetch(list(langs)))
    frontend = frontend_words(url, list(langs))
    status = 0
    for code, data in langs.items():
        words = found.get(code) or {}
        own = {}
        for key, source in sources.items():
            if isinstance(words.get(source), str) and words[source]:
                own[key] = words[source]
            else:
                print(f'{code}: Home Assistant has no {source}')
        own.update(frontend.get(code, {}))
        reference = dict(generator().flatten(data.get('screen', {}).get('ha', {})))
        if code == 'en':
            for key, word in own.items():
                if reference.get(key) != word:
                    print(f'en: screen.ha.{key} "{reference.get(key)}" becomes Home Assistant\'s "{word}"')
        tree = {}
        for key, word in own.items():
            node = tree
            parts = key.split('.')
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = word
        before = json.dumps(data, ensure_ascii=False)
        merge(data.setdefault('screen', {}).setdefault('ha', {}), tree)
        if json.dumps(data, ensure_ascii=False) != before:
            changed = sum(1 for key, word in own.items() if reference.get(key) != word)
            print(f'{code}: {"wrote" if write else "would change"} {changed} of {len(own)} words from Home Assistant')
            if write:
                write_language(code, data)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('lint')
    head = sub.add_parser('header')
    head.add_argument('--check', action='store_true')
    cldr = sub.add_parser('cldr')
    cldr.add_argument('--write', action='store_true')
    words = sub.add_parser('ha-words')
    words.add_argument('--write', action='store_true')
    fresh = sub.add_parser('new')
    fresh.add_argument('code')
    fresh.add_argument('name')
    fresh.add_argument('english')
    fresh.add_argument('plural')
    args = parser.parse_args()
    if args.command == 'new':
        return new_language(args.code, args.name, args.english, args.plural)
    if args.command == 'check':
        return check()
    if args.command == 'lint':
        return lint()
    if args.command == 'header':
        return header(args.check)
    if args.command == 'cldr':
        return cldr_dates(args.write)
    if args.command == 'ha-words':
        return ha_words(args.write)
    return 2


# The CLDR locale of a file where it differs: Portuguese is Home Assistant's pt, the one of Portugal.
CLDR_LOCALE = {'pt': 'pt-PT'}
# Every language Home Assistant's frontend offers (2026.9: the languages of its translationMetadata). A language ESP
# Screens has no file for still writes the clock and numbers as Home Assistant does (regions.json); its texts fall back
# to English.
HA_LANGUAGES = ('af ar bg bn bs ca cs cy da de el en en-GB eo es et eu fa fi fy fr ga gl gsw he hi hr hu hy id it is ja '
                'ka ko lb lt lv mk ml nl nb nn pl pt pt-BR ro ru sk sl sr sr-Latn sv sq ta te th tr uk ur vi zh-Hans '
                'zh-Hant').split()
# The languages that put a space between a number and "%" ("54 %"), as Home Assistant's frontend does
# (src/common/translations/blank_before_unit.ts, blankBeforePercent); every other one writes "54%".
HA_PERCENT_BLANK = ('cs', 'de', 'fi', 'fr', 'sk', 'sv')
REGIONS = ROOT / 'screen_manager' / 'app' / 'regions.json'


def percent_space(code):
    return code.split('-')[0] in HA_PERCENT_BLANK


def number_style(number):
    """point (1,234.5), comma (1.234,5) or space (1 234,5): the choices of Settings -> Language & region."""
    if number['decimal'] != ',':
        return 'point'
    return 'space' if number['group'].strip() == '' else 'comma'


def regions():
    """{code: {clock, numbers, group_min, percent_space}} for every Home Assistant language, from Node's Intl."""
    locales = [CLDR_LOCALE.get(code, code) for code in HA_LANGUAGES]
    found = json.loads(subprocess.run(['node', str(ROOT / 'tools' / 'i18n_cldr.mjs'), *locales], check=True,
                                      capture_output=True, text=True).stdout)
    table = {}
    for code, locale in zip(HA_LANGUAGES, locales):
        cldr = found[locale]
        table[code] = {'clock': cldr['clock'], 'numbers': number_style(cldr['number']),
                       'group_min': int(cldr['number']['group_min']), 'percent_space': percent_space(code)}
    return table


def write_language(code, data):
    (FOLDER / f'{code}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def merge(target, source):
    """`source` into `target` in place, keeping the order of what `target` already has."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value


def cldr_dates(write, codes=None):
    """Day and month names, date orders, AM/PM, the number marks and the clock of every language but English (whose
    texts are the source) from Node's Intl, into screen.date, screen.time, screen.number and _meta.clock."""
    codes = codes or [code for code in languages() if not code.startswith('en')]
    if not codes:
        return 0
    locales = [CLDR_LOCALE.get(code, code) for code in codes]
    found = json.loads(subprocess.run(['node', str(ROOT / 'tools' / 'i18n_cldr.mjs'), *locales], check=True,
                                      capture_output=True, text=True).stdout)
    for code, locale in zip(codes, locales):
        path = FOLDER / f'{code}.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        cldr = found[locale]
        before = json.dumps(data, ensure_ascii=False)
        data.setdefault('_meta', {})['clock'] = cldr['clock']
        number = {**cldr['number'], 'percent': ' %' if percent_space(code) else '%'}
        date = dict(cldr['date'])
        # The two letters of the weather columns are the language's own choice once it has them (the CLDR's short
        # width, which Node's Intl doesn't give): only a new language starts from the abbreviation.
        if data.get('screen', {}).get('date', {}).get('weekdays_min'):
            date.pop('weekdays_min')
        merge(data.setdefault('screen', {}), {'number': number, 'time': cldr['time'], 'date': date})
        if json.dumps(data, ensure_ascii=False) != before:
            print(f'{code}: {"wrote" if write else "would change"} the CLDR texts')
            if write:
                write_language(code, data)
    table = regions()
    text = json.dumps({'_about': 'GENERATED by tools/i18n.py cldr: how every Home Assistant language writes the clock and '
                                 'numbers (Unicode CLDR, Home Assistant\'s own rule for the space before %). The app takes '
                                 'it for Settings -> Language & region set to Automatic.', **table},
                      ensure_ascii=False, indent=1) + '\n'
    if not REGIONS.exists() or REGIONS.read_text(encoding='utf-8') != text:
        print(f'regions.json: {"wrote" if write else "would change"} the clock and numbers of {len(table)} languages')
        if write:
            REGIONS.write_text(text, encoding='utf-8')
    return 0


def new_language(code, name, english, plural):
    """A new language file: its _meta and the CLDR texts, every other text still English until someone translates it."""
    if not re.fullmatch(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?', code) or (FOLDER / f'{code}.json').exists():
        raise SystemExit(f'{code}: not a new language code')
    if plural not in FORMS:
        raise SystemExit(f'plural must be one of {", ".join(FORMS)}')
    write_language(code, {'_meta': {'name': name, 'english': english, 'script': 'latin', 'plural': plural, 'clock': '24',
                                    'checked': False}, 'screen': {}, 'addon': {}, 'editor': {}})
    return cldr_dates(True, [code])


if __name__ == '__main__':
    sys.exit(main())
