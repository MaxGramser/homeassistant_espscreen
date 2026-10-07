"""The tile catalogue (app 0.4.32): what a tile of each entity type can do, and what a screen gets of it.

catalogue/*.yaml, one file per entity type, is the source; tools/generate_catalogue.py writes catalogue.json beside this
file, which is what this module reads. docs/CATALOGUE.md is the guide. Three questions, each answered here once:

- what may be chosen for an entity (`offers`): the options of its type whose `needs` its Home Assistant entity meets,
  the actions Home Assistant lists for it (get_services_for_target), their fields, its feature bits and its history;
- what a card of a given size draws (`resolve_controls`): the chosen control or the type's default, and on a card one
  row high what fits there (`one_row`);
- what a screen gets (`drawn_controls`): what that entity can draw (`fallback`) on that screen (`screen`, its hello).

And what a layout asks of a screen's firmware (`gates`), for core.min_firmware. The editor asks the same of
web/src/model/catalogue.ts, which reads the same file; tests/test_catalogue.py and its fixture keep the two alike.
"""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).with_name('catalogue.json')).read_text())
TILE = DATA['tile']
TYPES = DATA['domains']
DOMAINS = frozenset(TYPES)
# What a tile keeps in the memory inside a screen's chip (catalogue `memory`, firmware 0.34.0+, docs/TILE_MEMORY.md): each
# type's entry, the dearest for a type the catalogue does not know, and what a tile's own choices add.
MEMORY = {domain: data['memory'] for domain, data in TYPES.items()}
DEAREST = max(MEMORY.values(), key=lambda entry: entry['bytes'])
# The screen's own cards that keep more than their type (the energy card), by entity.
CARD_MEMORY = {entity: price for data in TYPES.values() for entity, price in data.get('cards', {}).items()}
CHOICE_MEMORY = TILE['memory']
# The commands a remote of each integration takes, read from Home Assistant's source and the libraries it pins
# (tools/read_remote_commands.py, GitHub #117): {integration: {'from': [...], 'commands': [...]}}.
REMOTE_COMMANDS = json.loads((Path(__file__).with_name('remote_commands.json')).read_text())['platforms']


KEYPAD_KEYS = ('up', 'down', 'left', 'right', 'ok', 'back', 'home', 'play', 'volume_up', 'volume_down', 'mute')


def remote_keypad(platform):
    """The commands of a remote's keypad for its integration (catalogue/remote.yaml keypad, firmware 0.22.0), in the order
    the screen takes them and an empty one for a key it lacks; None for an integration without one."""
    keys = ((TYPES.get('remote') or {}).get('keypad') or {}).get(platform)
    return [keys.get(key, '') for key in KEYPAD_KEYS] if keys else None


def remote_commands(platform):
    """The commands a remote of this integration takes, in its source's order; None where only the device, the hub or
    the user's own configuration knows them (Harmony, Broadlink) or any text goes (Samsung)."""
    return (REMOTE_COMMANDS.get(platform) or {}).get('commands')


def parse_version(text):
    return tuple(int(part) for part in text.split('.')) if text else None


def of_type(domain):
    """The catalogue's entry of an entity type, or None for one it does not have."""
    return TYPES.get(domain)


def option(domain, group, key):
    """One option of a type ('controls', 'displays'), or None."""
    entry = TYPES.get(domain)
    return next((item for item in (entry or {}).get(group, []) if item['key'] == key), None)


def control_keys(domain):
    """The controls of a type in the catalogue's order, the default first."""
    return [item['key'] for item in (TYPES.get(domain) or {}).get('controls', [])]


def display_keys(domain):
    return [item['key'] for item in (TYPES.get(domain) or {}).get('displays', [])]


# ---- Home Assistant's side: does an entity meet what an option needs ----

def bits(domain, *names):
    """Home Assistant's feature bits of a type by the names its source gives them (catalogue/_ha.json), joined: the add-on's
    counterpart of catalogue.ts `bits`. A name Home Assistant does not have for the type is a KeyError, never a 0."""
    features = TYPES[domain]['features']
    out = 0
    for name in names:
        out |= features[name]
    return out


def playing_features(domain, platform):
    """What an integration reports while it plays, where it reports less while it plays nowhere (catalogue/_ha.json
    `playing`, read from its source: Spotify's SUPPORT_SPOTIFY, GitHub #88), joined; 0 for any other."""
    names = ((TYPES.get(domain) or {}).get('playing') or {}).get(platform)
    return bits(domain, *names) if names else 0


def features_hold(domain, names, attributes, strict=False):
    """Any of these features, where Home Assistant reports the entity's. What may be chosen or drawn (`needs`) is not
    held against an entity that reports none, as one that is unavailable; a condition (`strict`, a range's `when`) only
    holds on what Home Assistant does report."""
    flags = attributes.get('supported_features')
    if not names:
        return True
    if not isinstance(flags, int) or isinstance(flags, bool):
        return not strict
    bits = TYPES[domain]['features']
    return any(flags & bits[name] for name in names)


def holds(domain, needs, entity_id, state, actions=None, services=None, fields=None, history=None):
    """Whether an entity meets `needs`. `actions`: the actions Home Assistant lists for it (None: not asked, only its
    features and attributes count, as when a screen is sent its tiles). `fields(action, field)`: whether Home
    Assistant offers that field of that action for it. `history(entity_id, state)`: its history's kind."""
    if not needs:
        return True
    attributes = (state or {}).get('attributes') or {}
    if actions is not None and 'actions' in needs:
        if not any(item['action'] in actions and (not item.get('field') or (fields and fields(item['action'], item['field'])))
                   for item in needs['actions']):
            return False
    if not features_hold(domain, needs.get('features'), attributes):
        return False
    if any(attributes.get(name) is None for name in needs.get('attributes', [])):
        return False
    if needs.get('history') and history is not None and history(entity_id, state) != needs['history']:
        return False
    if 'unless' in needs and holds_strictly(domain, needs['unless'], attributes):
        return False
    return True


def condition(domain, when, attributes):
    """A variant's `when`: its features reported (any of them), its attributes present, and not its `unless`."""
    if not when:
        return True
    if not features_hold(domain, when.get('features'), attributes, strict=True):
        return False
    if any(attributes.get(name) is None for name in when.get('attributes', [])):
        return False
    return not ('unless' in when and holds_strictly(domain, when['unless'], attributes))


def holds_strictly(domain, needs, attributes):
    """`unless`: every feature named reported, every attribute present; an entity that reports no features meets none."""
    flags = attributes.get('supported_features')
    bits = TYPES[domain]['features']
    if needs.get('features') and not (isinstance(flags, int) and all(flags & bits[name] for name in needs['features'])):
        return False
    return all(attributes.get(name) is not None for name in needs.get('attributes', []))


def offers(entity_id, state, actions, services=None, fields=None, history=None):
    """What the editor may offer for an entity, in Home Assistant's own terms: On / off as a tap, a small slider, the
    direct controls and the displays its type has and it meets. The shape ha_catalogue.capabilities always had."""
    domain = entity_id.split('.', 1)[0]
    entry = TYPES.get(domain) or {}
    actions = set(actions or ())

    def meets(item):
        return holds(domain, item.get('needs'), entity_id, state, actions, services, fields, history)

    controls, met = [], {}
    for item in entry.get('controls', []):
        met[item['key']] = meets(item) if 'of' not in item else all(met.get(part) for part in item['of'])
        if met[item['key']]:
            controls.append(item['key'])
    toggle = entry.get('toggle') or {'actions': [{'action': f'{domain}.toggle'}]}
    found = {
        'toggle': holds(domain, toggle, entity_id, state, actions, services, fields, history),
        'inline': bool(entry.get('inline')) and meets(entry['inline']),
        'controls': controls,
        'displays': [item['key'] for item in entry.get('displays', []) if meets(item)],
    }
    # What a favourite of it may set as it starts (app 0.4.84): its shuffle and repeat.
    if 'favorite' in entry:
        found['favorite'] = [item['key'] for item in entry['favorite'] if meets(item)]
    return found


# ---- The card's side: what a card of a size draws ----

def size_rows(size, spans):
    """Rows a size is high on the card (tall and square two, a span its own, the rest one)."""
    span = spans(size)
    return span[1] if span else 2 if size in ('tall', 'square') else 1


def resolve_controls(tile, spans):
    """The control set a card draws, or None. Only a card with room beside or under its name has one; a full page and a
    card one column wide and taller draw none unless one was chosen, a wider card its type's default (the first).
    A card one row high draws what fits there (`one_row`): the buttons of buttons and slats, the setpoint of both."""
    options = tile.get('options', {})
    domain = tile['entity'].split('.')[0]
    keys = control_keys(domain)
    size = options.get('size')
    span = spans(size)
    if not keys or (size not in ('wide', 'tall', 'square', 'full') and span is None) \
            or options.get('display', 'standard') not in ('standard', 'cover') or options.get('inline') == 'slider':
        return None
    default = 'none' if size in ('tall', 'full') or (span or (0,))[0] == 1 else keys[0]
    choice = options.get('controls', default)
    item = option(domain, 'controls', choice)
    if item and item.get('one_row') and size_rows(size, spans) == 1 and size != 'full':
        choice = item['one_row']
    return None if choice == 'none' else choice


# ---- The screen's side: what a screen gets ----

def screen_holds(requirement, features=None, version=None, pictures=None):
    """Whether a screen meets `screen`: the firmware version it runs, a feature its hello lists, pictures on its board.
    What is not known (None) is not held against it."""
    if not requirement:
        return True
    if 'feature' in requirement and features is not None and requirement['feature'] not in features:
        return False
    if 'firmware' in requirement and version is not None and version < parse_version(requirement['firmware']):
        return False
    if requirement.get('pictures') and pictures is False:
        return False
    return True


def drawable(domain, key, attributes, features):
    """The control a screen draws for this entity in place of `key`: `key` itself, its type's `fallback` where the
    entity does not meet its features, the `else` of its range where the screen does not draw one, and of a pair the
    part that is left."""
    item = option(domain, 'controls', key)
    if item is None:
        return key
    if 'of' in item:
        parts = [drawable(domain, part, attributes, features) for part in item['of']]
        if parts == item['of']:
            return key
        kept = [part for part, drawn in zip(item['of'], parts) if drawn == part]
        return kept[0] if len(kept) == 1 else 'none' if not kept else key
    if not features_hold(domain, (item.get('needs') or {}).get('features'), attributes):
        return item.get('fallback', 'none')
    ranged = item.get('range')
    if ranged and condition(domain, ranged.get('when'), attributes) and not screen_holds(ranged.get('screen'), features=features):
        return ranged['screen'].get('else', 'none')
    return key


def drawn_controls(message, features):
    """The state message a screen gets, its controls cut to what it draws right (app 0.4.32): the entity's features and
    the screen's hello (`features`, the list it said; None where not known, as for the editor's preview, which runs
    the newest firmware)."""
    domain = message.get('entity', '').split('.', 1)[0]
    options = message.get('o')
    if not isinstance(options, dict) or not options.get('controls') or domain not in TYPES:
        return message
    drawn = drawable(domain, options['controls'], (message.get('a') or {}), features)
    if drawn != options['controls']:
        options['controls'] = drawn
    return message


# ---- What a layout asks of a screen's firmware ----

def gates(tile):
    """(firmware, reason) for every hard requirement this tile's type and chosen options have: an option whose screen
    requirement has no `else` needs that firmware to be sent at all. Soft ones (with `else`) degrade instead."""
    domain = tile['entity'].split('.')[0]
    entry = TYPES.get(domain)
    if not entry:
        return []
    found = []
    if entry.get('firmware'):
        found.append((parse_version(entry['firmware']), f'type {domain}'))
    options = tile.get('options', {})
    for group, key in (('controls', options.get('controls')), ('displays', options.get('display'))):
        item = option(domain, group, key) if key else None
        requirement = (item or {}).get('screen') or {}
        if requirement.get('firmware') and 'else' not in requirement:
            found.append((parse_version(requirement['firmware']), f'{group[:-1]} {key}'))
    return found


def taps(domain):
    """The taps a tile of this type may have: every tile's, and its own (an automation's run)."""
    return list(TILE['taps']) + list((TYPES.get(domain) or {}).get('taps', []))


def key_domains():
    """The types that may stand as a key under a bedside clock."""
    return frozenset(domain for domain, entry in TYPES.items() if entry.get('key', True) and domain != 'screen')
