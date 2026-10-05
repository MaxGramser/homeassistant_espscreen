"""The tile catalogue (app 0.4.32): catalogue/*.yaml, one file per entity type, to what the add-on, the editor and the
firmware read.

    screen_manager/app/catalogue.json        the add-on's (screen_manager/app/catalogue.py evaluates it)
    web/src/model/catalogue.json             the editor's (web/src/model/catalogue.ts evaluates it)
    components/smart_display/tile_catalogue.h  the firmware's: the types it draws and Home Assistant's feature bits by name

tools/generate_catalogue.py writes them, `--check` fails when one is out of date (tools/check.sh). Every file is checked
first: an unknown key, an action or a feature Home Assistant does not have for the type (catalogue/_ha.json, read from its
source by tools/read_ha_source.py), a control without its words in the translations or an option that names one that
does not exist stops it. docs/CATALOGUE.md is the guide.
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'catalogue'
OUTPUTS = {'addon': ROOT / 'screen_manager/app/catalogue.json', 'editor': ROOT / 'web/src/model/catalogue.json',
           'firmware': ROOT / 'components/smart_display/tile_catalogue.h',
           # The commands a remote of each integration takes (catalogue/_remote_commands.json, read from Home Assistant
           # and the libraries it pins by tools/read_remote_commands.py): the add-on offers them in Send command.
           'remote_commands': ROOT / 'screen_manager/app/remote_commands.json'}
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
# The types there were when the catalogue began (app 0.4.32). A type added after them is one the firmware learned to
# draw at some version, and says which (`firmware:`): the add-on then waits for that firmware before it sends one, and
# nothing reaches the editor that no screen can draw. docs/CATALOGUE.md: first the firmware's UI, then this file.
FIRST_TYPES = frozenset('alarm_control_panel automation binary_sensor button camera climate cover fan image input_boolean input_button '
                        'input_number input_select light lock media_player number person scene screen script select sensor sun switch '
                        'timer vacuum weather'.split())
TOP = {'domain', 'firmware', 'displays', 'controls', 'inline', 'toggle', 'taps', 'guards', 'picture', 'map', 'key', 'keypad', 'memory', 'cards'}
# What one tile of a type keeps in the memory inside a screen's chip (firmware 0.34.0+, docs/TILE_MEMORY.md): `bytes`
# measured on a board with PSRAM, `extras` whether it keeps a block of extras. Every type says it, so a new one cannot
# leave the screen's memory budget guessing; the most a tile may keep is a sanity bound, not a rule.
MEMORY = {'bytes', 'extras'}
MOST_BYTES = 16384
# The keys of a remote's card (keypad): up, down, left, right and OK always, the rest where the remote has them.
KEYPAD_KEYS = ('up', 'down', 'left', 'right', 'ok', 'back', 'home', 'play', 'volume_up', 'volume_down', 'mute')
OPTION = {'needs', 'screen', 'sizes', 'wide', 'rows', 'of', 'one_row', 'fallback', 'range'}
NEEDS = {'actions', 'features', 'history', 'attributes', 'unless'}
SCREEN = {'firmware', 'feature', 'pictures', 'else'}


class CatalogueError(ValueError):
    pass


def fail(where, message):
    raise CatalogueError(f'{where}: {message}')


def check_keys(where, value, allowed):
    if not isinstance(value, dict):
        fail(where, 'must be a mapping')
    unknown = set(value) - allowed
    if unknown:
        fail(where, f'unknown {", ".join(sorted(unknown))} (allowed: {", ".join(sorted(allowed))})')


def version(where, value):
    if not isinstance(value, str) or not VERSION.match(value):
        fail(where, f'{value!r} is no firmware version such as 0.19.0')
    return value


def actions_needed(where, entries):
    """[[feature, ...], ...] from ["A", "B+C"]: any one item, every feature of it (Home Assistant's rule)."""
    if not isinstance(entries, list):
        fail(where, 'must be a list')
    return [str(item).split('+') for item in entries]


def load():
    """Every type, checked, as {domain: its file's content}, and what every tile has (_tile.yaml)."""
    files = sorted(SOURCE.glob('*.yaml'))  # _tile.yaml and _ha.json are not types
    tile = yaml.safe_load((SOURCE / '_tile.yaml').read_text())
    types = {}
    for path in files:
        if path.name.startswith('_'):
            continue
        data = yaml.safe_load(path.read_text())
        where = f'catalogue/{path.name}'
        check_keys(where, data, TOP)
        if data.get('domain') != path.stem:
            fail(where, f'domain must be {path.stem}')
        types[path.stem] = data
    return tile, types


def keypad(where, value, commands):
    """A remote's keypad per integration, every command one that integration takes (catalogue/_remote_commands.json)."""
    if not isinstance(value, dict):
        fail(where, 'must be a mapping of integrations')
    out = {}
    for platform, keys in value.items():
        check_keys(f'{where} {platform}', keys, set(KEYPAD_KEYS))
        if platform not in commands:
            fail(where, f'{platform} has no commands in catalogue/_remote_commands.json: give it a rule in tools/read_remote_commands.py')
        missing = {'up', 'down', 'left', 'right', 'ok'} - set(keys)
        if missing:
            fail(f'{where} {platform}', f'needs {", ".join(sorted(missing))}')
        for key, command in keys.items():
            if command not in commands[platform]['commands']:
                fail(f'{where} {platform} {key}', f'{platform} takes no {command!r} (catalogue/_remote_commands.json)')
        out[platform] = {key: keys[key] for key in KEYPAD_KEYS if key in keys}
    return out


def normalise(tile, types, translations, facts, commands=None):
    """The catalogue as its readers get it, checked across files and against Home Assistant's own facts
    (catalogue/_ha.json, read from its source by tools/read_ha_source.py): every action an option needs is one Home
    Assistant registers for that type, every feature one of its flags, every option named by another exists, every
    control has words."""
    if commands is None:
        commands = json.loads((SOURCE / '_remote_commands.json').read_text())['platforms']
    ha = {}
    for domain in types:
        known = facts['domains'].get(domain)
        if known is None and domain != 'screen':
            fail(f'catalogue/{domain}.yaml', f'Home Assistant has no {domain} in catalogue/_ha.json: run tools/read_ha_source.py')
        ha[domain] = {'features': dict((known or {}).get('features') or {}), 'actions': dict((known or {}).get('actions') or {}),
                      'playing': dict((known or {}).get('playing') or {})}
        for integration, flags in ha[domain]['playing'].items():
            if set(flags) - set(ha[domain]['features']):
                fail('catalogue/_ha.json', f'{integration} plays with flags {domain} does not have')

    def needs(where, domain, value):
        if value is None:
            return None
        check_keys(where, value, NEEDS)
        out = {}
        if 'actions' in value:
            out['actions'] = []
            for entry in value['actions']:
                action, field = (entry['action'], entry.get('field')) if isinstance(entry, dict) else (entry, None)
                owner, _, name = str(action).partition('.')
                if owner not in ha or name not in ha[owner]['actions']:
                    fail(where, f'Home Assistant registers no {action} (catalogue/_ha.json)')
                out['actions'].append({'action': action, **({'field': field} if field else {})})
        for key in ('features', 'attributes'):
            if key in value:
                if key == 'features' and set(value[key]) - set(ha[domain]['features']):
                    fail(where, f'{", ".join(sorted(set(value[key]) - set(ha[domain]["features"])))} is no feature of {domain}')
                out[key] = list(value[key])
        if 'history' in value:
            if value['history'] != 'line':
                fail(where, 'history is line')
            out['history'] = 'line'
        if 'unless' in value:
            out['unless'] = needs(f'{where} unless', domain, value['unless'])
        return out

    def screen(where, value):
        if value is None:
            return None
        check_keys(where, value, SCREEN)
        out = {}
        if 'firmware' in value:
            out['firmware'] = version(where, value['firmware'])
        if 'feature' in value:
            out['feature'] = str(value['feature'])
        if 'pictures' in value:
            out['pictures'] = bool(value['pictures'])
        if 'else' in value:
            out['else'] = str(value['else'])
        return out

    def option(where, domain, key, value, siblings):
        value = value or {}
        check_keys(where, value, OPTION)
        out = {'key': key}
        if 'needs' in value:
            out['needs'] = needs(f'{where} needs', domain, value['needs'])
        if 'screen' in value:
            out['screen'] = screen(f'{where} screen', value['screen'])
        if 'sizes' in value:
            check_keys(f'{where} sizes', value['sizes'], {'full'})
            out['sizes'] = {'full': bool(value['sizes']['full'])}
        if value.get('wide'):
            out['wide'] = True
        if 'rows' in value:
            out['rows'] = int(value['rows'])
        if 'of' in value:
            if set(value['of']) - set(siblings):
                fail(where, f'of names {", ".join(sorted(set(value["of"]) - set(siblings)))}, which is not an option here')
            out['of'] = list(value['of'])
        for name in ('one_row', 'fallback'):
            if name in value:
                if value[name] != 'none' and value[name] not in siblings:
                    fail(where, f'{name} names {value[name]}, which is not an option here')
                out[name] = value[name]
        if 'range' in value:
            check_keys(f'{where} range', value['range'], {'when', 'screen'})
            out['range'] = {'when': needs(f'{where} range when', domain, value['range'].get('when')),
                            'screen': screen(f'{where} range screen', value['range'].get('screen'))}
        return out

    words = translations['addon']['labels']['controls']
    domains = {}
    for domain, data in sorted(types.items()):
        where = f'catalogue/{domain}.yaml'
        if domain not in FIRST_TYPES and 'firmware' not in data:
            fail(where, 'a new type says from which firmware a screen draws it (firmware: x.y.z); first its UI, then this file')
        firmware = version(f'{where} firmware', data['firmware']) if 'firmware' in data else None
        displays = data.get('displays') or {}
        controls = data.get('controls') or {}
        for key in controls:
            if key not in (words.get(domain) or {}):
                fail(where, f'control {key} has no words: add addon.labels.controls.{domain}.{key} to the translations')
        picture = data.get('picture')
        if picture is not None:
            check_keys(f'{where} picture', picture, {'fit', 'overlay', 'refresh'})
        # A map card (app 0.4.33): its framings, distances and name choice, the first of each the default, and who may
        # ride along on it (docs/MAP.md).
        map_options = data.get('map')
        if map_options is not None:
            check_keys(f'{where} map', map_options, {'framing', 'distance', 'overlay', 'follow', 'markers', 'names', 'zones', 'streets',
                                                     'look', 'with', 'max'})
            if 'map' not in displays:
                fail(where, 'map options need the map display')
        memory = data.get('memory')
        if memory is None:
            fail(where, 'says what one tile of it keeps in the memory inside the chip (memory: {bytes: N, extras: true or '
                        'false}), measured as docs/TILE_MEMORY.md says')
        check_keys(f'{where} memory', memory, MEMORY)
        if set(memory) != MEMORY or type(memory['bytes']) is not int or not 0 <= memory['bytes'] <= MOST_BYTES \
                or type(memory['extras']) is not bool:
            fail(f'{where} memory', f'needs bytes (0 to {MOST_BYTES}) and extras (true or false)')
        # The screen's own cards that keep more than their type (the energy card's diagram, app 0.4.77): priced by their
        # entity, screen.<card>, before the type's price.
        cards = data.get('cards') or {}
        if cards and domain != 'screen':
            fail(where, 'only the screen\'s own cards have a price of their own (cards)')
        for card, price in cards.items():
            if set(price) != MEMORY or type(price['bytes']) is not int or not 0 <= price['bytes'] <= MOST_BYTES or type(price['extras']) is not bool:
                fail(f'{where} cards {card}', f'needs bytes (0 to {MOST_BYTES}) and extras (true or false)')
        domains[domain] = {
            'firmware': firmware,
            'memory': {'bytes': memory['bytes'], 'extras': memory['extras']},
            **({'cards': {f'{domain}.{card}': {'bytes': price['bytes'], 'extras': price['extras']} for card, price in cards.items()}} if cards else {}),
            'key': bool(data.get('key', True)),
            'features': ha[domain]['features'],
            'actions': ha[domain]['actions'],
            **({'playing': ha[domain]['playing']} if ha[domain]['playing'] else {}),
            'displays': [option(f'{where} displays {key}', domain, key, value, displays) for key, value in displays.items()],
            'controls': [option(f'{where} controls {key}', domain, key, value, controls) for key, value in controls.items()],
            'inline': option(f'{where} inline', domain, 'slider', data['inline'], {}) if 'inline' in data else None,
            'toggle': needs(f'{where} toggle', domain, data['toggle']) if 'toggle' in data else None,
            'taps': list(data.get('taps') or []),
            'guards': list(data.get('guards') or []),
            'picture': picture,
            'map': map_options,
            'keypad': keypad(f'{where} keypad', data['keypad'], commands) if 'keypad' in data else None,
        }
    check_keys('catalogue/_tile.yaml', tile, {'taps', 'sizes', 'history_hours', 'memory'})
    choice = tile.get('memory')
    if not isinstance(choice, dict) or set(choice) != {'action', 'line', 'page', 'bar_text'} or \
            not all(type(choice[k]) is int and 0 <= choice[k] <= MOST_BYTES for k in choice):
        fail('catalogue/_tile.yaml memory', f'needs action, line, page and bar_text, in bytes (0 to {MOST_BYTES})')
    return {'version': 1, 'ha': facts['source'], 'tile': tile, 'domains': domains}


def header(catalogue):
    """The firmware's: the types it draws, and each type's Home Assistant feature bits by the names its source gives them."""
    lines = ['#pragma once',
             '// Generated by tools/generate_catalogue.py from catalogue/*.yaml (the tile catalogue, app 0.4.32); do not edit.',
             '// The entity types a screen draws, and Home Assistant\'s feature bits of each by the names its source gives them',
             '// (catalogue/_ha.json, read from Home Assistant core by tools/read_ha_source.py), so no firmware code counts bits by hand.',
             '#include <cstdint>', '', 'namespace tile_catalogue {', '',
             '// Every type a tile can show, the screen\'s own cards (screen.*) included.',
             'inline constexpr const char *DOMAINS[] = {' + ', '.join(f'"{d}"' for d in catalogue['domains']) + '};', '']
    lines += ['// What one tile of each type keeps in the memory inside the chip besides the tile itself, in bytes, measured on a board',
              '// with PSRAM, and whether it keeps a block of extras (catalogue `memory`, docs/TILE_MEMORY.md): tile_memory.h works out',
              '// what a tile costs on this board from it.',
              'struct Memory { const char *domain; uint16_t bytes; bool extras; };',
              '// What a tile\'s own choices add (catalogue/_tile.yaml `memory`): a tap that runs its own action, a second line set',
              '// to one of its values. Each also keeps a block of extras on a tile whose type keeps none.',
              f'inline constexpr uint16_t ACTION_BYTES = {catalogue["tile"]["memory"]["action"]}, LINE_BYTES = {catalogue["tile"]["memory"]["line"]};',
              '// What a page keeps (its title) and an item of its top bar that shows an entity (its text).',
              f'inline constexpr uint16_t PAGE_BYTES = {catalogue["tile"]["memory"]["page"]}, BAR_TEXT_BYTES = {catalogue["tile"]["memory"]["bar_text"]};',
              'inline constexpr Memory MEMORY[] = {' + ', '.join(
                  f'{{"{d}", {data["memory"]["bytes"]}, {"true" if data["memory"]["extras"] else "false"}}}'
                  for d, data in catalogue['domains'].items()) + '};',
              '// The screen\'s own cards that keep more than their type, priced by their entity first (catalogue/screen.yaml `cards`).',
              'inline constexpr Memory CARDS[] = {' + ', '.join(
                  f'{{"{e}", {price["bytes"]}, {"true" if price["extras"] else "false"}}}'
                  for data in catalogue['domains'].values() for e, price in data.get('cards', {}).items()) + '};', '']
    keywords = {'switch', 'case', 'default', 'delete', 'new', 'register', 'template', 'this', 'union', 'volatile'}
    for domain, data in catalogue['domains'].items():
        if not data['features']:
            continue
        space = domain + '_' if domain in keywords else domain
        lines.append(f'namespace {space} {{')
        for feature, bit in data['features'].items():
            lines.append(f'inline constexpr uint32_t {feature} = {bit};')
        lines.append(f'}}  // namespace {space}')
    lines += ['', '}  // namespace tile_catalogue', '']
    return '\n'.join(lines)


def outputs():
    tile, types = load()
    translations = json.loads((ROOT / 'screen_manager/translations/en.json').read_text())
    facts = json.loads((SOURCE / '_ha.json').read_text())
    commands = json.loads((SOURCE / '_remote_commands.json').read_text())
    catalogue = normalise(tile, types, translations, facts, commands['platforms'])
    text = json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n'
    return {'addon': text, 'editor': text, 'firmware': header(catalogue),
            'remote_commands': json.dumps(commands, ensure_ascii=False, indent=1) + '\n'}


if __name__ == '__main__':
    try:
        wanted = outputs()
    except CatalogueError as error:
        sys.exit(f'The tile catalogue: {error}')
    stale = [name for name, path in OUTPUTS.items() if not path.exists() or path.read_text() != wanted[name]]
    if '--check' in sys.argv:
        if stale:
            sys.exit('The tile catalogue is out of date: ' + ', '.join(str(OUTPUTS[name].relative_to(ROOT)) for name in stale)
                     + '. Run tools/generate_catalogue.py.')
    else:
        for name, path in OUTPUTS.items():
            path.write_text(wanted[name])
        print('wrote ' + ', '.join(str(path.relative_to(ROOT)) for path in OUTPUTS.values()))
