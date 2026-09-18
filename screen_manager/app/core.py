"""Pure validation, firmware generation and bounded display protocol."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import secrets

import tile_icons

DOMAINS = frozenset('light switch input_boolean scene script climate vacuum fan cover sensor binary_sensor input_select select number input_number weather media_player button input_button sun timer person screen camera image'.split())
# Built-in cards without a Home Assistant entity; firmware 0.2.14+ renders them.
BUILTIN = {'screen.clock': 'Clock', 'screen.settings': 'Settings', **{f'screen.page_{n}': f'Go to page {n}' for n in range(1, 9)}}
# A navigation tile (firmware 0.2.62+): screen.page_<n> goes to page n. Firmware 0.2.65+ takes the same one on several
# pages (a "Back to page 1" on every page); every other entity still appears once on a screen.
PAGE_TILE = 'screen.page_'
PAGE_TILE_REPEAT_MIN_FIRMWARE = (0, 2, 65)

def page_target(entity):
    """The page a navigation tile opens, counted from one; 0 for any other entity."""
    return int(entity[len(PAGE_TILE):]) if isinstance(entity, str) and entity in BUILTIN and entity.startswith(PAGE_TILE) else 0
NEW_DOMAINS = frozenset('sun timer person screen'.split())
# A camera or an image entity opens full screen on a Guition with firmware 0.2.57+ (camera_feed.py).
CAMERA_DOMAINS = frozenset(('camera', 'image'))
CAMERA_MIN_FIRMWARE = (0, 2, 57)
# The media card with its cover (app 0.2.77): firmware from here draws it and asks for the cover.
COVER_MIN_FIRMWARE = (0, 2, 64)
# Forty-eight tiles (one per slot), a tile over the whole page and the screen.page tile (firmware 0.2.62+).
MAX_TILES = 48
LEGACY_MAX_TILES = 20
FULL_PAGE_MIN_FIRMWARE = (0, 2, 62)
# Twenty tiles from firmware 0.2.7, ten before.
TWENTY_TILES_MIN_FIRMWARE = (0, 2, 7)
FIRST_MAX_TILES = 10
WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
REPO = 'https://github.com/MaxGramser/homeassistant_espscreen'
REFS = {'cyd': 'main', 'guition': 'main', 'jc8012p4a1': 'main'}
# Firmware shipped with this app release; screens below it get an update offer.
FIRMWARE_VERSION = '0.2.70'
# The Auto standby switch a screen offers Home Assistant automations.
AUTO_STANDBY_MIN_FIRMWARE = '0.2.41'
# The settings page the screen opens itself, and the screen.settings tile that opens it.
SETTINGS_PAGE_MIN_FIRMWARE = '0.2.44'
# The Wake and Sleep buttons a screen offers Home Assistant automations.
WAKE_SLEEP_MIN_FIRMWARE = '0.2.45'
# Every screen setting as an entity of the screen, which owns them (see SETTING_ENTITIES).
SETTING_ENTITIES_MIN_FIRMWARE = '0.2.49'
# Dark mode: the screen's dark look, a setting and entity of its own (components/smart_display/theme.h).
DARK_MODE_MIN_FIRMWARE = '0.2.54'
# Page buttons: the Previous and Next bar under the tiles, a setting and entity of its own; off, the tiles take its room.
PAGE_BUTTONS_MIN_FIRMWARE = '0.2.69'
ATTRS = frozenset('brightness percentage current_position current_tilt_position current_temperature temperature current_humidity min_temp max_temp target_temp_step supported_color_modes hvac_modes hvac_action hs_color color_temp_kelvin min_color_temp_kelvin max_color_temp_kelvin fan_speed_list unit_of_measurement battery_level fan_speed volume_level is_volume_muted media_title options min max step temperature_unit supported_features device_class next_rising next_setting finishes_at duration remaining humidity wind_speed wind_speed_unit apparent_temperature fan_modes swing_modes fan_mode swing_mode effect'.split())
# Attributes whose boolean value the screen needs; every other bool stays behind.
BOOL_ATTRS = frozenset(['is_volume_muted'])


TILE_BACKGROUNDS = {
    'auto': {'label': 'Default', 'color': None},
    # No card behind the tile: contents keep their size and place on the screen background.
    'none': {'label': 'None', 'color': None},
    'red': {'label': 'Red', 'color': '#FADADD'},
    'orange': {'label': 'Orange', 'color': '#FFE1C6'},
    'yellow': {'label': 'Yellow', 'color': '#FFF0C2'},
    'green': {'label': 'Green', 'color': '#D9EEDC'},
    'mint': {'label': 'Mint', 'color': '#D5F0EA'},
    'blue': {'label': 'Blue', 'color': '#D9EAFB'},
    'purple': {'label': 'Purple', 'color': '#E9DDF5'},
    'pink': {'label': 'Pink', 'color': '#F7DDEC'},
    'gray': {'label': 'Gray', 'color': '#E5E7EB'},
}

# Display modes per domain; everything else offers standard and watch (large value).
DISPLAYS = {'weather': ('standard', 'watch', 'forecast'), 'sensor': ('standard', 'watch', 'graph'), 'screen': ('digital', 'analog'), 'sun': ('standard', 'watch', 'sunpath')}
# Displays that only work on a double-width card.
WIDE_ONLY = ('forecast', 'sunpath')

# Grid positions: two columns, three rows per page, at most eight pages. A tile's
# `slot` is its absolute cell (page * 6 + row * 2 + column); a wide tile starts in
# the left column and also covers the cell to its right. Empty cells are allowed.
SLOTS_PER_PAGE = 6
MAX_PAGES = 8
MAX_SLOTS = MAX_PAGES * SLOTS_PER_PAGE

TILE_SIZES_ON_SCREEN = ('single', 'wide', 'full')

def tile_size(tile):
    """'single', 'wide' (a row) or 'full' (the whole page, firmware 0.2.62+)."""
    size = tile.get('options', {}).get('size', 'single')
    return size if size in TILE_SIZES_ON_SCREEN else 'single'

def is_wide(tile):
    """Double width or the whole page: the card spans both columns."""
    return tile_size(tile) != 'single'

def is_full(tile):
    return tile_size(tile) == 'full'

def cells_of(size):
    return SLOTS_PER_PAGE if size == 'full' else 2 if size in ('wide', True) else 1

def page_start(slot):
    return slot - slot % SLOTS_PER_PAGE

def footprint(slot, size):
    """The cells a tile of `size` takes from `slot` (True still means wide)."""
    if size == 'full':
        return tuple(range(page_start(slot), page_start(slot) + SLOTS_PER_PAGE))
    return (slot, slot + 1) if size in ('wide', True) else (slot,)

def pack_slots(tiles):
    """In-order packing, the rule before explicit positions and what firmware without
    `slots` still does: fill left to right, a wide card starts a new row, a full one a new page."""
    position, slots = 0, []
    for tile in tiles:
        size = tile_size(tile)
        if size == 'full' and position % SLOTS_PER_PAGE:
            position += SLOTS_PER_PAGE - position % SLOTS_PER_PAGE
        elif size == 'wide' and position % 2:
            position += 1
        slots.append(position)
        position += cells_of(size)
    return slots

def packed_slots(tiles):
    """pack_slots for tiles that must fit on the screen: ValueError when the packing runs past the last page (48
    tiles with one of them double-width, or 43 with one full-page tile), before a save or an event stores it (app
    0.2.78; the save used to fail later with "Invalid tile position")."""
    slots = pack_slots(tiles)
    if any(footprint(slot, tile_size(tile))[-1] >= MAX_SLOTS for tile, slot in zip(tiles, slots)):
        raise ValueError("These tiles don't fit on eight pages; remove a tile or make one smaller.")
    return slots

def has_gaps(tiles):
    """True when the stored positions differ from the in-order packing, so firmware
    before 0.2.26 (which ignores `slots`) would show another arrangement."""
    return [t.get('slot') for t in tiles] != pack_slots(tiles)

# Direct controls on the right half of a double-width card (firmware 0.2.19+), like
# Home Assistant's own entity rows. The first choice is what a wide card shows
# when the tile has no explicit choice; 'none' keeps the plain card.
CONTROLS = {
    'climate': (('setpoint', 'Temperature − / +'), ('mode', 'Off, heat, cool')),
    'switch': (('toggle', 'On/off switch'),),
    'input_boolean': (('toggle', 'On/off switch'),),
    'light': (('toggle', 'On/off switch'), ('brightness', 'Brightness slider')),
    'fan': (('toggle', 'On/off switch'), ('speed', 'Speed slider')),
    'vacuum': (('buttons', 'Start, stop, dock'),),
    'cover': (('buttons', 'Open, stop, close'), ('position', 'Position slider')),
    'media_player': (('volume', 'Volume and mute'), ('playback', 'Previous, play/pause, next')),
    'number': (('stepper', 'Value − / +'), ('slider', 'Slider')),
    'input_number': (('stepper', 'Value − / +'), ('slider', 'Slider')),
    'select': (('stepper', 'Previous / next choice'),),
    'input_select': (('stepper', 'Previous / next choice'),),
    'timer': (('buttons', 'Start/pause and cancel'),),
    'scene': (('run', 'Activate button'),),
    'script': (('run', 'Run button'),),
    'button': (('run', 'Press button'),),
    'input_button': (('run', 'Press button'),),
}

def controls_catalogue():
    """Editor choices per domain: the default first, then 'none'."""
    return {domain: {'default': choices[0][0], 'choices': [{'key': key, 'label': label} for key, label in choices] + [{'key': 'none', 'label': 'None'}]}
            for domain, choices in CONTROLS.items()}

def resolve_controls(tile):
    """Control set a card shows on the screen, or None: only wide cards in the standard layout have room for one."""
    options = tile.get('options', {})
    domain = tile['entity'].split('.')[0]
    if domain not in CONTROLS or options.get('size') not in ('wide', 'full') or options.get('display', 'standard') != 'standard' or options.get('inline') == 'slider':
        return None
    # A full-page card is one big button unless a control was chosen for it; a wide card shows its usual one.
    choice = options.get('controls', 'none' if options.get('size') == 'full' else CONTROLS[domain][0][0])
    return None if choice == 'none' else choice

# Diagnostic entities every ESP Screens firmware exposes; the manager watches them for screens.
# Firmware built before the English translation still registers the Dutch originals, so both
# forms are recognised until every board has been reflashed with an English `name:`.
NAME_TILE_SETTINGS = ('Tile settings', 'Tegelinstellingen')
NAME_SCREEN_FIRMWARE = ('Screen firmware', 'Schermfirmware')
NAME_GUITION_TYPE = ('Guition screen type', 'Guition schermtype')
NAME_JC8012_TYPE = ('JC8012P4A1 screen type',)
NAME_DEVICE_NAME = ('Device name', 'Apparaatnaam')
NAME_IP_ADDRESS = ('IP address', 'IP-adres')
SCREEN_ENTITY_NAMES = frozenset(NAME_TILE_SETTINGS + NAME_SCREEN_FIRMWARE + NAME_GUITION_TYPE + NAME_JC8012_TYPE + NAME_DEVICE_NAME + NAME_IP_ADDRESS)

def parse_firmware(text):
    """(major, minor, patch) of a screen firmware version such as "0.2.63"; None for anything else. Strict on purpose:
    the firmware reports exactly its project version, and anything with a suffix is not a release."""
    match = re.fullmatch(r'([0-9]+)\.([0-9]+)\.([0-9]+)', text) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None

# Home Assistant's device registry keeps an ESPHome device's version while the device is offline or restarting. With
# `esphome: project:` (both board profiles) the ESPHome integration writes "<project version> (ESPHome <version>)".
REGISTRY_FIRMWARE = re.compile(r'^([0-9]+\.[0-9]+\.[0-9]+) \(ESPHome ')

def registry_firmware(sw_version):
    """The screen firmware in a device registry sw_version, or None. Firmware built without a project has only
    ESPHome's own version there, which must never read as a screen firmware."""
    match = REGISTRY_FIRMWARE.match(sw_version) if isinstance(sw_version, str) else None
    return match.group(1) if match else None

def known_firmware(sensor, sw_version):
    """The version text discover_screens gives a screen as `firmware_known`: the "Screen firmware" sensor when it holds
    one, else the device registry's; None when neither does."""
    return sensor if parse_firmware(sensor) else registry_firmware(sw_version)

def screen_firmware(screen):
    """The firmware a screen's feature gates go by (app 0.2.78): its "Screen firmware" sensor, or while that has no
    version (the screen is offline or restarting) the one Home Assistant's device registry kept; None when neither
    says. Before, an offline screen counted as firmware 0.0.0 and a save of more than ten tiles was refused."""
    screen = screen or {}
    return parse_firmware(screen.get('firmware_known')) or parse_firmware(screen.get('firmware'))

def version_text(version):
    """"0.2.65" for (0, 2, 65); None for None."""
    return '.'.join(str(part) for part in version) if version else None

def tile_limit(version):
    """How many tiles firmware `version` (a tuple, or None when unknown) takes."""
    version = version or (0, 0, 0)
    return MAX_TILES if version >= FULL_PAGE_MIN_FIRMWARE else LEGACY_MAX_TILES if version >= TWENTY_TILES_MIN_FIRMWARE else FIRST_MAX_TILES

def firmware_features(version):
    """What the editor may offer a screen with firmware `version` (a tuple, or None): the tile limit, full-page and
    navigation tiles, and the same navigation tile on several pages."""
    version = version or (0, 0, 0)
    return {'tile_limit': tile_limit(version), 'full_page': version >= FULL_PAGE_MIN_FIRMWARE,
            'page_tiles_repeat': version >= PAGE_TILE_REPEAT_MIN_FIRMWARE}

def entity_slug(name):
    """The end of an entity id Home Assistant derives from an entity name (ASCII names)."""
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')

# An inbox entity id is text.<device>_tile_settings, or text.<device>_tegelinstellingen before firmware 0.2.34.
INBOX_SUFFIXES = tuple('_' + entity_slug(name) for name in NAME_TILE_SETTINGS)

def inbox_prefix(entity):
    """The device part of an inbox entity id ('office_1' for text.office_1_tile_settings), or None."""
    if isinstance(entity, str) and entity.startswith('text.'):
        for suffix in INBOX_SUFFIXES:
            if entity.endswith(suffix) and len(entity) > len('text.') + len(suffix):
                return entity[len('text.'):-len(suffix)]
    return None

def device_prefixes(registry, device_id):
    """Entity id prefixes Home Assistant gave the ESPHome entities of one device: the device name when each
    entity was created. Entities whose name never changed keep the prefix an older inbox id carried."""
    prefixes = set()
    for item in registry:
        name = item.get('original_name')
        if item.get('device_id') != device_id or item.get('platform') != 'esphome' or not isinstance(name, str):
            continue
        object_id, suffix = item['entity_id'].split('.', 1)[-1], '_' + entity_slug(name)
        if len(suffix) > 1 and object_id.endswith(suffix) and len(object_id) > len(suffix):
            prefixes.add(object_id[:-len(suffix)])
    return prefixes

# Additive schema 1 extension. An absent object retains old firmware/YAML defaults.
SETTING_RULES = {
    'standby_enabled': (True, None, None),
    'standby_seconds': (600, 60, 86400),
    'brightness': (100, 5, 100),
    'standby_brightness': (20, 0, 100),
    'night_enabled': (True, None, None),
    'night_start': (1320, 0, 1439),
    'night_end': (420, 0, 1439),
    'night_brightness': (10, 0, 100),
    'show_clock': (True, None, None),
    'clock_24h': (True, None, None),
    'home_on_standby': (False, None, None),
    'swipe_pages': (False, None, None),
    'rotation': (0, 0, 270),
    # Back to page 1 by itself (firmware 0.2.44+): closes an open card and any page but the first
    # after this many seconds without a touch. Older firmware ignores both keys.
    'auto_home': (True, None, None),
    'auto_home_seconds': (120, 30, 3600),
    # The dark look for a screen beside a bed (firmware 0.2.54+). Only a screen that owns its settings has it: it
    # never travels in the layout message.
    'dark_mode': (False, None, None),
    # The Previous and Next bar under the tiles (firmware 0.2.69+); off, the tiles grow into its room. Only a screen
    # that owns its settings has it, like dark_mode.
    'page_buttons': (True, None, None),
}
# Firmware before 0.2.44 accepts a `settings` object with exactly its own eleven keys and refuses any
# other size, so everything added after it travels as its own key in the layout message. Old firmware
# ignores a key it does not know; a new screen with an old add-on keeps what it saved itself.
# docs/SETTINGS.md walks through adding one.
SETTINGS_BESIDE_BLOCK = ('swipe_pages', 'rotation', 'auto_home', 'auto_home_seconds', 'dark_mode', 'page_buttons')

# ----- The screen owns its settings (firmware 0.2.49+) -----
# A screen offers every setting as an entity of its own device, and the settings page on the screen, Home
# Assistant and ESP Screens all change them there. ESP Screens reads them from those entities, changes them
# with the entity's own action, and leaves them out of the layout message, so it never overwrites what
# someone changed on the screen or in an automation. A screen without these entities (older firmware) gets
# its settings in the layout message as before. `show_clock` has no entity: the top bar decides the clock.
# key: (Home Assistant domain, the entity's name in the board profiles)
SETTING_ENTITIES = {
    'brightness': ('number', 'Normal brightness'),
    'standby_enabled': ('switch', 'Auto standby'),
    'standby_seconds': ('number', 'Standby after'),
    'standby_brightness': ('number', 'Standby brightness'),
    'night_enabled': ('switch', 'Night mode'),
    'night_start': ('time', 'Night starts'),
    'night_end': ('time', 'Night ends'),
    'night_brightness': ('number', 'Night brightness'),
    'clock_24h': ('switch', '24-hour clock'),
    'auto_home': ('switch', 'Back to page 1'),
    'auto_home_seconds': ('number', 'Back to page 1 after'),
    'home_on_standby': ('switch', 'Back to page 1 on standby'),
    'swipe_pages': ('switch', 'Swipe between pages'),
    'rotation': ('select', 'Rotation'),
    'dark_mode': ('switch', 'Dark mode'),
    'page_buttons': ('switch', 'Page buttons'),
}
# Entities firmware 0.2.49 added; one of them on a device means the screen owns its settings. The first five
# existed before, so they cannot tell.
OWNED_SETTINGS_MARKERS = frozenset(('Night mode', 'Night starts', 'Night ends', '24-hour clock', 'Back to page 1',
                                    'Back to page 1 after', 'Back to page 1 on standby', 'Swipe between pages'))
ROTATION_OPTIONS = ('0°', '90°', '180°', '270°')


def setting_entities(items):
    """{key: entity_id} of a screen's setting entities, from the registry entries of its device (disabled ones
    included), or None when the screen does not own its settings yet (firmware before 0.2.49)."""
    found, owned = {}, False
    for item in items:
        if item.get('platform') != 'esphome':
            continue
        name, domain = item.get('original_name'), item['entity_id'].split('.', 1)[0]
        owned = owned or name in OWNED_SETTINGS_MARKERS
        for key, (wanted_domain, wanted_name) in SETTING_ENTITIES.items():
            if name == wanted_name and domain == wanted_domain and key not in found:
                found[key] = item['entity_id']
    return found if owned else None


def setting_from_state(key, state):
    """The value of one setting from its entity's state, or None while Home Assistant has none."""
    value = (state or {}).get('state')
    if not isinstance(value, str) or value in ('', 'unknown', 'unavailable'):
        return None
    domain = SETTING_ENTITIES[key][0]
    try:
        if domain == 'switch':
            return {'on': True, 'off': False}.get(value)
        if domain == 'number':
            number = float(value)
            return int(round(number)) if math.isfinite(number) else None
        if domain == 'time':
            hour, minute = (int(part) for part in value.split(':')[:2])
            return hour * 60 + minute if 0 <= hour < 24 and 0 <= minute < 60 else None
        if domain == 'select':
            return int(value.rstrip('°')) if value in ROTATION_OPTIONS else None
    except ValueError:
        return None
    return None


def setting_action(key, entity, value):
    """(action, data) that gives one setting entity `value`."""
    domain = SETTING_ENTITIES[key][0]
    if domain == 'switch':
        return ('switch.turn_on' if value else 'switch.turn_off'), {'entity_id': entity}
    if domain == 'number':
        return 'number.set_value', {'entity_id': entity, 'value': value}
    if domain == 'time':
        return 'time.set_value', {'entity_id': entity, 'time': f'{value // 60:02d}:{value % 60:02d}:00'}
    return 'select.select_option', {'entity_id': entity, 'option': f'{value}°'}


def validate_settings(data):
    if not isinstance(data, dict) or set(data) - SETTING_RULES.keys():
        raise ValueError('Unknown screen settings; refresh the management page.')
    clean = {}
    for key, (default, minimum, maximum) in SETTING_RULES.items():
        value = data.get(key, default)
        if minimum is None:
            valid = type(value) is bool
        else:
            valid = type(value) is int and minimum <= value <= maximum
        if key == "rotation": valid = valid and value in (0, 90, 180, 270)
        if not valid:
            raise ValueError(f'Invalid value for {key}.')
        clean[key] = value
    if max(clean['standby_brightness'], clean['night_brightness']) > clean['brightness']:
        raise ValueError('Standby and night brightness may not be higher than normal.')
    return clean

def entity_id(value):
    if not (isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value)):
        return False
    return value in BUILTIN if value.startswith('screen.') else value.split('.')[0] in DOMAINS

# ----- Top bar (firmware 0.2.32+): the screen name on the left, up to six items on the right.
# Without a `header` the screen keeps its name and the clock of `show_clock`. -----
HEADER_MIN_FIRMWARE = (0, 2, 32)
# Firmware 0.2.33+ takes a whole message in one API action (esphome.<node>_screen_message)
# and answers a keepalive ping with its layout revision; older firmware gets base64
# chunks in the text inbox and a full repeat every keepalive.
TRANSPORT_MIN_FIRMWARE = (0, 2, 33)
MESSAGE_ACTION = 'screen_message'
HEADER_MAX_ITEMS = 6
# Items the screen draws on its own clock, without Home Assistant.
HEADER_BUILTIN = {'clock': 'Time', 'analog': 'Analog clock', 'date': 'Date'}
# Only shown, never controlled: the top bar takes these besides every tile domain.
HEADER_ONLY_DOMAINS = frozenset('device_tracker zone lock alarm_control_panel counter event input_datetime input_text water_heater humidifier'.split())
HEADER_CONTENTS = ('state', 'last_changed')
HEADER_SHOWS = ('always', 'active')

def header_entity(value):
    return (isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value) is not None
            and value.split('.')[0] in (DOMAINS - {'screen'} - CAMERA_DOMAINS) | HEADER_ONLY_DOMAINS)

def header_items(layout):
    """Items the top bar shows: the stored ones, else what firmware before the top bar drew (the clock)."""
    if 'header' in layout:
        return layout['header']['items']
    return [{'type': 'clock'}] if layout.get('settings', {}).get('show_clock', True) else []

def validate_header(data):
    if not isinstance(data, dict) or set(data) - {'items'} or not isinstance(data.get('items'), list):
        raise ValueError('Invalid top bar; refresh the management page.')
    if len(data['items']) > HEADER_MAX_ITEMS:
        raise ValueError(f'The top bar has room for at most {HEADER_MAX_ITEMS} items.')
    items, seen = [], set()
    for item in data['items']:
        kind = item.get('type') if isinstance(item, dict) else None
        if kind in HEADER_BUILTIN:
            if set(item) != {'type'}:
                raise ValueError('Invalid setting in the top bar.')
            clean = {'type': kind}
        elif kind == 'entity':
            if set(item) - {'type', 'entity', 'content', 'icon', 'show'}:
                raise ValueError('Unknown setting in the top bar; refresh the management page.')
            if not header_entity(item.get('entity')):
                raise ValueError("This entity can't go in the top bar.")
            clean = {'type': 'entity', 'entity': item['entity'], 'content': item.get('content', 'state'),
                     'icon': item.get('icon', 'auto'), 'show': item.get('show', 'always')}
            if clean['content'] not in HEADER_CONTENTS or clean['show'] not in HEADER_SHOWS:
                raise ValueError('Invalid setting in the top bar.')
            if not (clean['icon'] in ('auto', 'none') or isinstance(clean['icon'], str) and clean['icon'] in tile_icons.ICONS):
                raise ValueError('Choose an icon from the list.')
        else:
            raise ValueError('Unknown item in the top bar; refresh the management page.')
        key = json.dumps(clean, sort_keys=True)
        if key in seen:
            raise ValueError('This item is already in the top bar.')
        seen.add(key)
        items.append(clean)
    return {'items': items}

def repeated_page_tiles(tiles):
    """True when a navigation tile to the same page is on the screen more than once (firmware 0.2.65+)."""
    pages = [tile['entity'] for tile in tiles if page_target(tile['entity'])]
    return len(pages) != len(set(pages))

def min_firmware(layout):
    """Oldest firmware that still accepts this layout; None when any version works."""
    if repeated_page_tiles(layout['tiles']):
        return PAGE_TILE_REPEAT_MIN_FIRMWARE
    if len(layout['tiles']) > LEGACY_MAX_TILES or any(is_full(t) or page_target(t['entity']) for t in layout['tiles']):
        return FULL_PAGE_MIN_FIRMWARE
    if any(t['entity'].split('.')[0] in CAMERA_DOMAINS for t in layout['tiles']):
        return CAMERA_MIN_FIRMWARE
    if any(t['entity'] == 'screen.settings' for t in layout['tiles']):
        return (0, 2, 44)
    if any(t.get('options', {}).get('background') == 'none' for t in layout['tiles']):
        return (0, 2, 16)
    if any(t['entity'].split('.')[0] in NEW_DOMAINS for t in layout['tiles']):
        return (0, 2, 14)
    if len(layout['tiles']) > FIRST_MAX_TILES:
        return TWENTY_TILES_MIN_FIRMWARE
    return None

def short(value, limit):
    return str(value).encode('utf-8')[:limit].decode('utf-8', errors='ignore')

# ----- Tiles from a Home Assistant event (app 0.2.51) -----
# Claude in Home Assistant, or any automation, can put something on a screen without opening the editor:
# it fires one of these events and the app changes that screen's layout, with the same validation and the
# same push. The app answers with TILE_RESULT_EVENT, and publishes every layout as a sensor
# (layout_snapshot) so an assistant can see what is where before it changes anything.
TILE_EVENTS = {'esp_screens_add_tile': 'add', 'esp_screens_remove_tile': 'remove',
               'esp_screens_move_tile': 'move', 'esp_screens_order_tiles': 'order'}
TILE_RESULT_EVENT = 'esp_screens_tile_result'
# What an event may set on a tile: the editor's own settings, with `color` as a friendlier name for the
# pastel background.
TILE_EVENT_OPTIONS = {'size': 'size', 'controls': 'controls', 'display': 'display', 'icon': 'icon',
                      'color': 'background', 'background': 'background', 'tap': 'tap', 'inline': 'inline',
                      'history_hours': 'history_hours'}
TILE_SIZES = {'full': 'full', 'fullscreen': 'full', 'full screen': 'full', 'full-screen': 'full', 'page': 'full', 'whole page': 'full',
              'wide': 'wide', 'double': 'wide', 'large': 'wide', 'big': 'wide',
              'single': 'single', 'small': 'single', 'normal': 'single'}

def loose(text):
    """A name as people write it: case, spaces, dashes and underscores don't matter."""
    return re.sub(r'[\s_-]+', ' ', str(text or '')).strip().casefold()

def match_screen(screens, wanted, layouts=None):
    """The screen an event means: by its device name, the name Home Assistant shows, or its title.
    With one screen paired, an event doesn't have to name it."""
    listing = ', '.join(sorted(screen['name'] for screen in screens)) or 'none yet'
    if not loose(wanted):
        if len(screens) == 1:
            return screens[0]
        raise ValueError(f'Name the screen. Paired: {listing}.')
    key = loose(wanted)
    def names(screen):
        title = (layouts or {}).get(screen['id'], {}).get('title', '')
        return [loose(value) for value in (screen.get('node'), screen.get('name'), screen.get('device'), title, screen.get('area')) if value]
    found = [s for s in screens if key in names(s)] or [s for s in screens if any(key in name for name in names(s))]
    if not found:
        raise ValueError(f'No screen called "{wanted}". Paired: {listing}.')
    if len(found) > 1:
        raise ValueError(f'"{wanted}" fits more than one screen: ' + ', '.join(sorted(s['name'] for s in found)) + '.')
    return found[0]

def occupied_cells(tiles, skip=None):
    cells = set()
    for tile in tiles:
        if tile is skip or 'slot' not in tile:
            continue
        cells.update(footprint(tile['slot'], tile_size(tile)))
    return cells

def free_slot(tiles, size, page=None, skip=None):
    """The first cell a tile of this size fits in, on `page` or anywhere; None when there is no room."""
    cells = occupied_cells(tiles, skip)
    size = 'wide' if size is True else size
    first = 0 if page is None else page * SLOTS_PER_PAGE
    last = MAX_SLOTS if page is None else min(MAX_SLOTS, first + SLOTS_PER_PAGE)
    for slot in range(first, last):
        if size == 'full' and slot % SLOTS_PER_PAGE:
            continue
        if size == 'wide' and (slot % 2 or slot + 1 >= last):
            continue
        if not set(footprint(slot, size)) & cells:
            return slot
    return None

def place_tile(tile, tiles, page=None, slot=None):
    """Give a tile its cell: the one asked for when it is free, else the first free one (on `page`)."""
    size = tile_size(tile)
    if slot is not None:
        if size == 'full':
            slot = page_start(slot)
        elif size == 'wide' and slot % 2:
            slot -= 1
        wanted = set(footprint(slot, size))
        taken = next((t for t in tiles if t is not tile and 'slot' in t and wanted & set(footprint(t['slot'], tile_size(t)))), None)
        if taken:
            raise ValueError(f"That spot is taken by {taken['entity']}; give another spot or move that one first.")
        tile['slot'] = slot
        return
    free = free_slot(tiles, size, page, skip=tile)
    if free is None:
        if size == 'full':
            raise ValueError(f'Page {page + 1} is not empty; a full-page tile needs a page of its own.' if page is not None
                             else 'No page is empty; a full-page tile needs a page of its own.')
        raise ValueError(f'Page {page + 1} is full.' if page is not None else 'This screen has no room left.')
    tile['slot'] = free

def tile_options(data, current=None):
    """The settings an event asks for, on top of what the tile already has. A direct control, a forecast
    and a sun path only fit a double-width card, so they widen the tile themselves."""
    options = dict(current or {})
    for key, name in TILE_EVENT_OPTIONS.items():
        if key not in data or data[key] in (None, ''):
            continue
        value = data[key]
        if name == 'history_hours':
            options[name] = int(value) if str(value).isdigit() else value
        elif name == 'size':
            options[name] = TILE_SIZES.get(loose(value), str(value))
        else:
            options[name] = str(value).strip()
    # Perform action (app 0.2.67): `action` names Home Assistant's action and `data` its fields; the tap follows.
    if data.get('action') not in (None, ''):
        options['action'] = {'action': str(data['action']).strip(), **({'data': data['data']} if isinstance(data.get('data'), dict) and data['data'] else {})}
        if data.get('tap') in (None, ''):
            options['tap'] = 'action'
    if (options.get('controls', 'none') != 'none' or options.get('display') in WIDE_ONLY) and options.get('size') != 'full':
        options['size'] = 'wide'
    return {key: value for key, value in options.items() if value not in (None, '')}

def event_page(data):
    """The page an event names, counted from one as people do; None when it doesn't name one."""
    page = data.get('page')
    if page in (None, ''):
        return None
    if not str(page).strip().isdigit() or not 1 <= int(page) <= MAX_PAGES:
        raise ValueError(f'Choose a page between 1 and {MAX_PAGES}.')
    return int(page) - 1

def event_slot(data, page):
    """An exact spot: `slot` as the editor counts it, or `row` and `column` within a page."""
    if data.get('slot') not in (None, ''):
        if not str(data['slot']).strip().isdigit() or not 0 <= int(data['slot']) < MAX_SLOTS:
            raise ValueError(f'Choose a spot between 0 and {MAX_SLOTS - 1}.')
        return int(data['slot'])
    if data.get('row') in (None, '') and data.get('column') in (None, ''):
        return None
    if page is None:
        raise ValueError('Name the page for that row or column.')
    row = str(data.get('row', 1)).strip()
    if not row.isdigit() or not 1 <= int(row) <= SLOTS_PER_PAGE // 2:
        raise ValueError(f'Choose a row between 1 and {SLOTS_PER_PAGE // 2}.')
    column = loose(data.get('column') or 'left')
    if column not in ('left', 'right'):
        raise ValueError('The column is left or right.')
    return page * SLOTS_PER_PAGE + (int(row) - 1) * 2 + (1 if column == 'right' else 0)

def page_of(tile):
    return tile.get('slot', 0) // SLOTS_PER_PAGE

def copies_of(tiles, entity):
    """The tiles of one entity in slot order: one, or several copies of a navigation tile (firmware 0.2.65+)."""
    return sorted((tile for tile in tiles if tile['entity'] == entity), key=lambda tile: tile.get('slot', 0))

def pick_copy(found, page=None, slot=None):
    """The copy an event means: the one covering `slot`, else the first on `page`, else the first; None when none is
    there. Only a navigation tile has several; an event that doesn't say which acts on the first (app 0.2.78)."""
    if slot is not None:
        return next((tile for tile in found if 'slot' in tile and slot in footprint(tile['slot'], tile_size(tile))), None)
    if page is not None:
        return next((tile for tile in found if page_of(tile) == page), None)
    return found[0] if found else None

def event_source(data):
    """(page, slot) of the copy a move event means: `from_page` counted from one, or `from_slot`; None when not named."""
    page = event_page({'page': data.get('from_page')})
    slot = event_slot({'slot': data.get('from_slot')}, None)
    return (slot // SLOTS_PER_PAGE if slot is not None else page), slot

def where(page, slot):
    """The place an event named, as its answer says it: "spot 12" or "page 3"."""
    return f'spot {slot}' if slot is not None else f'page {page + 1}'

def pack_page(tiles, page):
    """Give these tiles the cells of one page, in the order they are in."""
    position = page * SLOTS_PER_PAGE
    last = position + SLOTS_PER_PAGE
    for tile in tiles:
        size = tile_size(tile)
        if size == 'full' and (position != page * SLOTS_PER_PAGE or len(tiles) > 1):
            raise ValueError(f'A full-page tile takes all of page {page + 1}; nothing else fits there.')
        if size == 'wide' and position % 2:
            position += 1
        if position + cells_of(size) > last:
            raise ValueError(f'That does not fit on page {page + 1}; a double-width tile takes two spots.')
        tile['slot'] = position
        position += cells_of(size)

def run_tile_event(layout, action, data, repeat_pages=False):
    """(layout, tile): the layout after one tile event and the tile it placed, changed, moved or removed (None for an
    order). Raises ValueError with the sentence the log and the answer show.

    Only a navigation tile can be on a screen more than once, and only when its firmware takes that (`repeat_pages`,
    0.2.65+). An event then names the copy it means by a spot it covers or by its page: `slot` or `page` for add and
    remove, `from_slot` or `from_page` for a move (whose `slot` and `page` say where to), and each mention in an order
    takes the next copy. Without that it acts on the first copy in spot order (app 0.2.78)."""
    result = {key: value for key, value in layout.items() if key != 'tiles'}
    tiles = [dict(tile) for tile in layout.get('tiles', [])]
    entity = str(data.get('entity') or '').strip()
    page = event_page(data)
    slot = event_slot(data, page)
    if slot is not None and page is None:
        page = slot // SLOTS_PER_PAGE
    if action == 'order':
        wanted = data.get('entities') or data.get('order') or []
        if isinstance(wanted, str):
            wanted = [part.strip() for part in wanted.split(',')]
        wanted = [str(item).strip() for item in wanted if str(item).strip()]
        if not wanted:
            raise ValueError('Give the entities in the order you want them.')
        picked, taken, missing, elsewhere, extra = [], set(), [], [], []
        for name in wanted:
            copies = copies_of(tiles, name)
            here = [tile for tile in copies if page is None or page_of(tile) == page]
            free = [tile for tile in here if id(tile) not in taken]
            if not copies:
                missing.append(name)
            elif not here:
                elsewhere.append(name)
            elif not free:
                extra.append(name)
            else:
                picked.append(free[0])
                taken.add(id(free[0]))
        if missing:
            raise ValueError('Not on this screen: ' + ', '.join(missing) + '.')
        if elsewhere:
            raise ValueError('Not on page %d: %s. Move it there first.' % (page + 1, ', '.join(elsewhere)))
        if extra:
            raise ValueError('Named more often than it is on %s: %s.' % ('this screen' if page is None else f'page {page + 1}',
                                                                        ', '.join(dict.fromkeys(extra))))
        if page is None:
            tiles = picked + [tile for tile in tiles if id(tile) not in taken]
            for tile, cell in zip(tiles, packed_slots(tiles)):
                tile['slot'] = cell
        else:
            pack_page(picked + [tile for tile in tiles if page_of(tile) == page and id(tile) not in taken], page)
        result['tiles'] = tiles
        return result, None
    if not entity:
        raise ValueError('Name the entity.')
    copies = copies_of(tiles, entity)
    found = copies[0] if copies else None
    if action == 'remove':
        source_page, source_slot = event_source(data)
        if source_page is None:
            source_page, source_slot = page, slot
        if not found:
            raise ValueError(f'{entity} is not on this screen.')
        found = pick_copy(copies, source_page, source_slot)
        if not found:
            raise ValueError(f'{entity} is not on {where(source_page, source_slot)}.')
        # The copy that was named itself, not the first tile equal to it.
        tiles = [tile for tile in tiles if tile is not found]
    elif action == 'move':
        if not found:
            raise ValueError(f'{entity} is not on this screen; add it first.')
        source_page, source_slot = event_source(data)
        found = pick_copy(copies, source_page, source_slot)
        if not found:
            raise ValueError(f'{entity} is not on {where(source_page, source_slot)}.')
        if page is None and slot is None:
            raise ValueError('Name the page or the spot to move it to.')
        found.pop('slot', None)
        place_tile(found, tiles, page, slot)
    else:
        if not entity_id(entity) and entity not in BUILTIN:
            raise ValueError(f'{entity} cannot go on a screen.')
        # A navigation tile the firmware takes more than once: the copy on the named spot or page changes, and anywhere
        # else a new copy goes (app 0.2.78). Every other tile, or one without a place, is the one that is there.
        chosen = False
        if copies and repeat_pages and page_target(entity) and (page is not None or slot is not None):
            found = pick_copy(copies, page, slot)
            chosen = found is not None
        was_size, had_slot = tile_size(found) if found else 'single', (found or {}).get('slot')
        options = tile_options(data, (found or {}).get('options'))
        tile = found or {'entity': entity, 'name': ''}
        if data.get('name') not in (None, ''):
            tile['name'] = str(data['name']).strip()
        if options:
            tile['options'] = options
        elif found:
            tile.pop('options', None)
        if found is None:
            if len(tiles) >= MAX_TILES:
                raise ValueError(f'This screen already has {MAX_TILES} tiles; remove one first.')
            tiles.append(tile)
        size = tile_size(tile)
        move = found is None or had_slot is None or (not chosen and (page is not None or slot is not None))
        if not move and size != was_size:
            # A tile that just grew keeps its spot when the cells it needs are free.
            start = page_start(had_slot) if size == 'full' else had_slot - had_slot % 2 if size == 'wide' else had_slot
            move = start != had_slot or bool(set(footprint(start, size)) & occupied_cells([t for t in tiles if t is not tile]))
        if move:
            tile.pop('slot', None)
            if size == 'full' and had_slot is not None and ((page is None and slot is None) or chosen):
                # A tile that grew to the whole page stays on its page when the page is otherwise empty.
                try:
                    place_tile(tile, tiles, had_slot // SLOTS_PER_PAGE)
                except ValueError:
                    place_tile(tile, tiles)
            elif chosen:
                place_tile(tile, tiles, page_of({'slot': had_slot}))
            else:
                place_tile(tile, tiles, page, slot)
        found = tile
    result['tiles'] = tiles
    return result, found

def apply_tile_event(layout, action, data, repeat_pages=False):
    """The layout after one tile event (run_tile_event without the tile it acted on)."""
    return run_tile_event(layout, action, data, repeat_pages)[0]

def layout_snapshot(screen, layout):
    """What a screen shows, for the sensor the app publishes in Home Assistant: one entry per tile with
    the page and the spot it is in, so an assistant can read the screen before it changes it."""
    tiles = []
    for tile in sorted(layout.get('tiles', []), key=lambda item: item.get('slot', 0)):
        slot, options = tile.get('slot', 0), tile.get('options', {})
        tiles.append({'entity': tile['entity'], 'name': tile.get('name') or '',
                      'page': slot // SLOTS_PER_PAGE + 1, 'row': slot % SLOTS_PER_PAGE // 2 + 1,
                      'column': 'right' if slot % 2 else 'left', 'slot': slot,
                      'size': options.get('size', 'single'), 'controls': options.get('controls', ''),
                      'display': options.get('display', 'standard'), 'tap': options.get('tap', 'auto'),
                      **({'action': options['action']} if options.get('tap') == 'action' and 'action' in options else {}),
                      **({'to_page': page_target(tile['entity'])} if page_target(tile['entity']) else {})})
    return {'screen': screen.get('name', ''), 'node': screen.get('node') or '', 'title': layout.get('title', ''),
            'pages': max([tile['page'] for tile in tiles], default=1), 'tiles': tiles}

# A tap's own action (app 0.2.67): Home Assistant's `domain.action` with data for its fields. It always acts on the tile's
# entity, so the keys that name a target stay out of the data. Text travels as data and every other value as a template
# Home Assistant renders back into that value (ESPHome's action data is text only); both stay small for the CYD.
ACTION_NAME = re.compile(r'[a-z0-9_]+\.[a-z0-9_]+')
ACTION_FIELD = re.compile(r'[a-z0-9_]{1,32}')
TARGET_KEYS = frozenset(('entity_id', 'device_id', 'area_id', 'floor_id', 'label_id'))
ACTION_MAX_FIELDS = 8
ACTION_MAX_VALUE = 400
ACTION_MAX_BYTES = 800

def action_for_screen(value):
    """A tap's own action as the firmware sends it (0.2.58+): {"s": action, "d": [[key, text]], "t": [[key, template]]}."""
    pairs, templates = [], []
    for key, item in (value.get('data') or {}).items():
        if isinstance(item, str):
            pairs.append([key, item])
        else:
            templates.append([key, '{{ %s | from_json }}' % json.dumps(json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False), ensure_ascii=False)])
    act = {'s': value['action']}
    if pairs:
        act['d'] = pairs
    if templates:
        act['t'] = templates
    return act

def validate_tap_action(value):
    """The stored form of a tap's own action; ValueError with what to change."""
    if not isinstance(value, dict) or set(value) - {'action', 'data'}:
        raise ValueError('Choose an action from the list.')
    name, data = value.get('action'), value.get('data', {})
    if not isinstance(name, str) or len(name) > 64 or not ACTION_NAME.fullmatch(name):
        raise ValueError('Choose an action from the list.')
    if not isinstance(data, dict) or len(data) > ACTION_MAX_FIELDS:
        raise ValueError(f'An action on a tap sets at most {ACTION_MAX_FIELDS} fields.')
    for key in data:
        if not isinstance(key, str) or not ACTION_FIELD.fullmatch(key) or key in TARGET_KEYS:
            raise ValueError(f'{key} is not a field an action on a tap can set.')
    clean = {'action': name, **({'data': dict(data)} if data else {})}
    try:
        act = action_for_screen(clean)
        size = len(json.dumps(act, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())
    except (TypeError, ValueError):
        raise ValueError('A value of the action is something the screen cannot send.') from None
    if size > ACTION_MAX_BYTES or any(len(item[1].encode()) > ACTION_MAX_VALUE for item in act.get('d', []) + act.get('t', [])):
        raise ValueError('The values of the action are too long for the screen.')
    return clean

def validate_layout(data, stored=False):
    """A layout as the editor, a tile event or the storage gives it. `stored`: loaded from the app's own data, where a
    tile setting this version doesn't know (saved by a newer app) stays as it is instead of stopping the app."""
    if not isinstance(data, dict):
        raise ValueError('Invalid layout.')
    title, tiles = data.get('title'), data.get('tiles')
    if not isinstance(title, str) or not title.strip() or len(title.encode()) > 96:
        raise ValueError('Give the screen a title of at most 96 bytes.')
    if not isinstance(tiles, list) or len(tiles) > MAX_TILES:
        raise ValueError(f'Choose at most {MAX_TILES} tiles.')
    clean, seen = [], set()
    for tile in tiles:
        if not isinstance(tile, dict) or not entity_id(tile.get('entity')):
            raise ValueError("This entity isn't supported.")
        # A navigation tile may go on several pages (min_firmware asks 0.2.65 for that); anything else appears once.
        if tile['entity'] in seen and not page_target(tile['entity']):
            raise ValueError('An entity can only appear once on a screen.')
        name = tile.get('name', '')
        if not isinstance(name, str) or len(name.encode()) > 80:
            raise ValueError('A tile name may contain at most 80 bytes.')
        seen.add(tile['entity'])
        item = {'entity': tile['entity'], 'name': name.strip()}
        if stored and 'options' in tile:
            try:
                validate_layout({'title': 'stored', 'tiles': [{'entity': tile['entity'], 'options': tile['options']}]})
            except ValueError:
                # The screen ignores what its firmware doesn't know either.
                item['options'] = dict(tile['options']) if isinstance(tile['options'], dict) else {}
                clean.append(item)
                continue
        if 'options' in tile:
            options = tile['options']
            if not isinstance(options, dict) or set(options) - {'tap', 'display', 'inline', 'history_hours', 'background', 'size', 'icon', 'controls', 'action'}:
                raise ValueError('Unknown tile settings.')
            # A navigation tile (screen.page_<n>, firmware 0.2.62+) has a name, an icon, a colour and a width; never the page.
            if page_target(tile['entity']):
                if options.get('size') == 'full':
                    raise ValueError('A navigation tile is single or double width.')
                options = {k: v for k, v in options.items() if k not in ('display', 'inline', 'controls', 'history_hours')}
            if 'background' in options and (not isinstance(options['background'],str) or options['background'] not in TILE_BACKGROUNDS):
                raise ValueError('Choose a pastel background color from the palette.')
            if 'icon' in options and not (options['icon'] == 'auto' or isinstance(options['icon'], str) and options['icon'] in tile_icons.ICONS):
                raise ValueError('Choose an icon from the list.')
            domain = tile['entity'].split('.')[0]
            displays = DISPLAYS.get(domain, ('standard', 'watch'))
            choices = {'tap': ('auto', 'detail', 'toggle', 'none', 'action'), 'display': displays, 'inline': ('none', 'slider'), 'size': TILE_SIZES_ON_SCREEN}
            for key, allowed in choices.items():
                if key in options and options[key] not in allowed:
                    raise ValueError('Invalid tile setting: ' + key)
            # The five-day strip and the sun path only fit a double-width card (or the whole page).
            if options.get('display') in WIDE_ONLY and options.get('size') != 'full':
                options = {**options, 'size': 'wide'}
            # On / off sends <domain>.toggle. Whether Home Assistant offers that for the entity is checked when saving
            # (Manager.check_supported, app 0.2.67); the built-in cards have nothing to switch.
            if options.get('tap') == 'toggle' and domain == 'screen':
                raise ValueError("This entity doesn't support an on/off action.")
            # Perform action (app 0.2.67) keeps its action; another tap choice leaves a stale one behind.
            if options.get('tap') == 'action':
                if domain == 'screen':
                    raise ValueError("A built-in card can't perform an action.")
                options = {**options, 'action': validate_tap_action(options.get('action'))}
            elif 'action' in options:
                options = {key: value for key, value in options.items() if key != 'action'}
            if options.get('inline') == 'slider' and domain not in {'light','fan','cover','number','input_number','media_player'}:
                raise ValueError("This entity doesn't support a mini-slider.")
            if 'history_hours' in options and (type(options['history_hours']) is not int or options['history_hours'] not in (1,6,24)):
                raise ValueError('History: choose 1, 6, or 24 hours.')
            if options.get('display') == 'watch' and options.get('inline') == 'slider':
                raise ValueError('Choose large value or mini-slider.')
            if 'controls' in options:
                allowed = ('none',) + tuple(key for key, _ in CONTROLS.get(domain, ()))
                if not isinstance(options['controls'], str) or options['controls'] not in allowed:
                    raise ValueError("This entity doesn't support that direct control.")
            item['options'] = dict(options)
        clean.append(item)
    # Positions: every tile or none (an older editor sends none and keeps its order).
    given = [tile.get('slot') for tile in tiles]
    if any(slot is not None for slot in given):
        occupied = set()
        for item, slot in zip(clean, given):
            if type(slot) is not int or not 0 <= slot < MAX_SLOTS:
                raise ValueError('Invalid tile position; refresh the management page.')
            size = tile_size(item)
            if size == 'full' and slot % SLOTS_PER_PAGE:
                raise ValueError('A full-page tile starts at the top of its page.')
            if size == 'wide' and slot % 2:
                raise ValueError('A double-width tile starts in the left column.')
            for cell in footprint(slot, size):
                if cell in occupied:
                    raise ValueError('Two tiles are in the same spot.')
                occupied.add(cell)
            item['slot'] = slot
        clean.sort(key=lambda item: item['slot'])
    else:
        for item, slot in zip(clean, packed_slots(clean)):
            item['slot'] = slot
    result = {'title': title.strip(), 'tiles': clean}
    # Pages kept on purpose, empty ones included; the screen shows at least what the tiles need.
    if 'pages' in data:
        if type(data['pages']) is not int or not 1 <= data['pages'] <= MAX_PAGES:
            raise ValueError(f'A screen has 1 to {MAX_PAGES} pages.')
        result['pages'] = data['pages']
    if 'settings' in data:
        result['settings'] = validate_settings(data['settings'])
    if 'header' in data:
        result['header'] = validate_header(data['header'])
    return result

def local_clock(value, tz):
    """HH:MM in the home's time zone for an ISO timestamp; '' when unusable."""
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return ''
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz or timezone.utc).strftime('%H:%M')

def forecast_kinds(attributes):
    """The forecasts a weather entity offers, from its supported_features (WeatherEntityFeature: 1 daily,
    2 hourly). Asking for one it lacks makes Home Assistant log an error; an entity that reports no features
    (unavailable) is asked for both, as before."""
    features = (attributes or {}).get('supported_features')
    if not isinstance(features, int) or isinstance(features, bool):
        return frozenset(('daily', 'hourly'))
    return frozenset(kind for kind, bit in (('daily', 1), ('hourly', 2)) if features & bit)

def forecast_number(entry, name):
    value = entry.get(name)
    return round(value, 1) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

def forecast_time(entry, tz):
    try:
        return datetime.fromisoformat(str(entry.get('datetime')).replace('Z', '+00:00')).astimezone(tz or timezone.utc)
    except (ValueError, TypeError):
        return None

def epoch(value):
    """Unix time of an ISO timestamp (a scene's state, a script's last_triggered); None when unusable."""
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())

# Vacuum cards (app 0.2.46, firmware 0.2.39+): how a robot cleans is often a select on its own device,
# not an attribute. Roborock has "Cleaning mode" (vacuum, vac_and_mop, mop, custom, smart_mode) and
# "Mop intensity" since HA 2026.8; Ecovacs calls its mode work_mode. They are found by translation key
# or by the end of their entity id. HA 2026.8 also dropped battery_level from vacuum entities, so the
# battery comes from the device's battery sensor.
VACUUM_MODE_KEYS = ('cleaning_mode', 'work_mode', 'clean_mode')
VACUUM_WATER_KEYS = ('mop_intensity', 'water_flow', 'water_amount', 'water_flow_level', 'water_volume', 'mop_water_level')
# Short chip labels; anything else shows its own words.
VACUUM_LABELS = {
    'vacuum': 'Vacuum', 'sweeping': 'Vacuum', 'vac_and_mop': 'Vac & mop', 'vacuum_and_mop': 'Vac & mop',
    'sweeping_and_mopping': 'Vac & mop', 'mop_after_vacuum': 'Vac, then mop', 'mopping_after_sweeping': 'Vac, then mop',
    'mop': 'Mop', 'mopping': 'Mop', 'custom': 'Custom', 'smart_mode': 'Smart',
    'off': 'Off', 'min': 'Min', 'slight': 'Slight', 'low': 'Low', 'mild': 'Mild', 'medium': 'Medium', 'moderate': 'Moderate',
    'standard': 'Standard', 'high': 'High', 'intense': 'Intense', 'extreme': 'Extreme', 'ultrahigh': 'Ultra high',
    'quiet': 'Quiet', 'silent': 'Silent', 'gentle': 'Gentle', 'balanced': 'Normal', 'turbo': 'Turbo', 'strong': 'Strong',
    'max': 'Max', 'max_plus': 'Max+', 'auto': 'Auto',
}
# What a cleaning mode does, one letter per option for the firmware: v vacuum only, m mop only, b both,
# a automatic (the robot or its app picks suction and water). Unknown modes count as both.
VACUUM_ROLES = {'vacuum': 'v', 'sweeping': 'v', 'mop': 'm', 'mopping': 'm', 'custom': 'a', 'smart_mode': 'a'}
# With a cleaning mode select these speeds and water levels belong to a mode: suction off is mop only,
# water off is vacuum only, and custom or smart settings are the Custom and Smart modes.
MODE_COVERED = frozenset(('off', 'off_raise_main_brush', 'custom', 'custom_water_flow', 'smart_mode', 'vac_followed_by_mop'))
VACUUM_CHOICES = 6

def vacuum_label(value):
    return short(VACUUM_LABELS.get(value) or str(value).replace('_', ' ').capitalize(), 24)

def vacuum_related(entity, device, states):
    """Entities on the vacuum's device that its card reads, by role: the 'mode' and 'water' selects, the
    'battery' and 'room' sensors and the 'charging' binary sensor; absent roles are left out.

    `device` holds the registry entries of the vacuum's device. Entity ids follow Home Assistant's
    language (select.s8_intensiteit_van_dweilen), so translation keys come first."""
    found = {}
    for item in device or ():
        eid = item.get('entity_id') or ''
        if eid == entity or item.get('disabled_by'):
            continue
        key = item.get('translation_key') or ''
        attrs = states.get(eid, {}).get('attributes', {})
        role = None
        if eid.startswith('select.'):
            if key in VACUUM_MODE_KEYS or eid.endswith(tuple('_' + k for k in VACUUM_MODE_KEYS)):
                role = 'mode'
            elif key in VACUUM_WATER_KEYS or eid.endswith(tuple('_' + k for k in VACUUM_WATER_KEYS)):
                role = 'water'
        elif eid.startswith('sensor.'):
            if attrs.get('device_class') == 'battery':
                role = 'battery'
            elif key == 'current_room' or eid.endswith('_current_room'):
                role = 'room'
        elif eid.startswith('binary_sensor.') and attrs.get('device_class') == 'battery_charging':
            role = 'charging'
        if role and role not in found:
            found[role] = eid
    return found

def device_power(attrs, related, states):
    """`bat` from the device's battery sensor when the entity has no battery_level of its own, and `chg` while its
    charging sensor is on; empty without them."""
    result = {}
    if not isinstance(attrs.get('battery_level'), (int, float)) and 'battery' in related:
        try:
            level = float(states[related['battery']].get('state'))
        except (TypeError, ValueError, KeyError):
            level = math.nan
        if math.isfinite(level):
            result['bat'] = max(0, min(100, round(level)))
    if states.get(related.get('charging'), {}).get('state') == 'on':
        result['chg'] = 1
    return result

def cover_related(entity, device, states):
    """A cover's battery and charging sensors on its device (app 0.2.58): battery-powered blinds such as
    Motionblinds report the battery there."""
    return {role: eid for role, eid in vacuum_related(entity, device, states).items() if role in ('battery', 'charging')}

def vacuum_extras(tile, states, device):
    """The vacuum card's rows and details: the mode and water selects (`e` entity, `s` state, `o` options,
    `l` labels, `r` a role per mode), the suction speeds to offer (`fan`), the battery (`bat`), charging
    (`chg`) and the room the robot is in (`room`)."""
    entity = tile['entity']
    attrs = states.get(entity, {}).get('attributes', {})
    related = vacuum_related(entity, device, states)
    result = {}
    def row(values):
        values = [short(v, 48) for v in values][:VACUUM_CHOICES]
        return {'o': values, 'l': [vacuum_label(v) for v in values]} if values else None
    def select(eid, keep):
        state = states.get(eid) or {}
        options = state.get('attributes', {}).get('options')
        current = state.get('state') if isinstance(state.get('state'), str) else ''
        found = row([o for o in options if isinstance(o, str) and keep(o, current)]) if isinstance(options, list) else None
        return {'e': eid, 's': short(current, 48), **found} if found else None
    # Custom runs the per-room settings made in the robot's app: listed only while it is in use.
    mode = select(related['mode'], lambda o, current: o != 'custom' or o == current) if 'mode' in related else None
    covered = MODE_COVERED if mode else frozenset()
    if mode:
        mode['r'] = ''.join(VACUUM_ROLES.get(v, 'b') for v in mode['o'])
        result['mode'] = mode
    water = select(related['water'], lambda o, current: o not in covered) if 'water' in related else None
    if water:
        result['water'] = water
    speeds = attrs.get('fan_speed_list')
    fan = row([s for s in speeds if isinstance(s, str) and s not in covered]) if isinstance(speeds, list) else None
    if fan:
        result['fan'] = fan
    result.update(device_power(attrs, related, states))
    room = states.get(related.get('room'), {}).get('state')
    if isinstance(room, str) and room not in ('', 'unknown', 'unavailable', 'none'):
        result['room'] = short(room, 32)
    return result or None

def media_extras(attrs):
    """The media card (app 0.2.77, firmware 0.2.64+): the artist and the album, the track's length and where it was
    when Home Assistant last said so (seconds; that moment as an epoch), and a short mark of the cover picture. The
    mark changes with the picture and says nothing else: the screen asks the app for the picture itself."""
    result = {}
    for key, name in (('artist', 'media_artist'), ('album', 'media_album_name')):
        value = attrs.get(name)
        if isinstance(value, str) and value.strip():
            result[key] = short(value.strip(), 80)
    for key, name in (('dur', 'media_duration'), ('pos', 'media_position')):
        value = attrs.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10_000_000:
            if key == 'dur' and value <= 0:
                continue
            result[key] = int(value)
    moment = attrs.get('media_position_updated_at')
    if isinstance(moment, str) and moment:
        try:
            parsed = datetime.fromisoformat(moment.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            result['at'] = int(parsed.timestamp())
        except ValueError:
            pass
    picture = attrs.get('entity_picture') or attrs.get('entity_picture_local')
    if isinstance(picture, str) and picture:
        result['pic'] = hashlib.sha1(picture.encode()).hexdigest()[:10]
    return result or None


def extras(tile, states, forecast=None, tz=None, hourly=None, now=None, device=None, entries=None, words=None, icon_of=None, device_name=None):
    """Small, pre-computed values the firmware cannot derive itself (time zones, forecasts, a vacuum's device, the rows of
    a light's effects page)."""
    domain = tile['entity'].split('.')[0]
    attrs = states.get(tile['entity'], {}).get('attributes', {})
    if domain == 'light':
        # The effects page (app 0.2.83): the select and number entities of the light's device, named as Home Assistant
        # names them; the effect itself travels as the `effect` attribute.
        import light_effects
        return light_effects.rows(tile['entity'], device, states, entries, words, icon_of, device_name) or None
    if domain == 'vacuum':
        return vacuum_extras(tile, states, device)
    if domain == 'cover':
        return device_power(attrs, cover_related(tile['entity'], device, states), states) or None
    if domain == 'media_player':
        return media_extras(attrs)
    if domain == 'weather' and (forecast or hourly):
        result = {}
        days = []
        for entry in forecast or []:
            if not isinstance(entry, dict) or len(days) == 5:
                continue
            day = forecast_time(entry, tz)
            if day is None:
                continue
            item = {'d': WEEKDAYS[day.weekday()], 'c': short(entry.get('condition') or '', 20)}
            # h/l: high and low; p: chance of rain in %; r: rain in the entity's unit (mm).
            for key, name in (('h', 'temperature'), ('l', 'templow'), ('p', 'precipitation_probability'), ('r', 'precipitation')):
                value = forecast_number(entry, name)
                if value is not None:
                    item[key] = value
            days.append(item)
        if days:
            result['days'] = days
        # The next eight hours from now, for the weather card's hourly strip.
        hours = []
        # The running hour still counts: an entry stays until its hour has passed.
        start = (now or datetime.now(timezone.utc)) - timedelta(minutes=59)
        for entry in hourly or []:
            if not isinstance(entry, dict) or len(hours) == 8:
                continue
            moment = forecast_time(entry, tz)
            if moment is None or moment < start:
                continue
            item = {'t': moment.strftime('%H:%M'), 'c': short(entry.get('condition') or '', 20)}
            for key, name in (('h', 'temperature'), ('p', 'precipitation_probability'), ('r', 'precipitation')):
                value = forecast_number(entry, name)
                if value is not None:
                    item[key] = value
            hours.append(item)
        if hours:
            result['hours'] = hours
        return result or None
    if domain in ('scene', 'script', 'button', 'input_button', 'image'):
        # When it last ran: scripts report last_triggered; scenes and buttons carry the time as their state, and so does
        # an image entity (when its picture last changed).
        last = epoch(attrs.get('last_triggered') if domain == 'script' else states.get(tile['entity'], {}).get('state'))
        return {'last': last} if last else None
    if domain == 'sun':
        rise, down = local_clock(attrs.get('next_rising'), tz), local_clock(attrs.get('next_setting'), tz)
        return {'rise': rise, 'set': down} if rise or down else None
    if domain == 'timer':
        result = {}
        try:
            end = datetime.fromisoformat(str(attrs.get('finishes_at')).replace('Z', '+00:00'))
            result['end'] = int(end.timestamp())
        except (ValueError, TypeError):
            pass
        for key, name in (('dur', 'duration'), ('rem', 'remaining')):
            if isinstance(attrs.get(name), str):
                result[key] = short(attrs[name], 16)
        return result or None
    return None

def tile_icon(tile, attrs, state=None, entry=None):
    """Codepoint the screen shows: the chosen icon, else HA's own mdi icon, else the icon Home Assistant's frontend shows
    for this state (app 0.2.67); None keeps the firmware default."""
    choice = tile.get('options', {}).get('icon', 'auto')
    if choice in tile_icons.ICONS:
        return tile_icons.ICONS[choice][0]
    return tile_icons.ha_icon(attrs) or tile_icons.default_glyph(tile['entity'], state, attrs, entry)

def screen_options(tile, attrs, state=None, entry=None):
    """Stored options on the wire; `icon` travels as the resolved codepoint (firmware 0.2.18+, ignored before)
    and `controls` only as the set the card really shows (firmware 0.2.19+, ignored before)."""
    options = {k: v for k, v in tile.get('options', {}).items() if k not in ('icon', 'controls', 'action')}
    icon = tile_icon(tile, attrs, state, entry)
    if icon:
        options['icon'] = icon
    controls = resolve_controls(tile)
    if controls:
        options['controls'] = controls
    # Perform action travels in the firmware's compact form (0.2.58+); older firmware taps automatically.
    action = tile.get('options', {}).get('action')
    if options.get('tap') == 'action' and isinstance(action, dict):
        try:
            options['act'] = action_for_screen(validate_tap_action(action))
        except ValueError:
            pass
    return options if options or 'options' in tile else None

def rounded_state(value, precision):
    """A sensor's state as Home Assistant shows it with a display precision (app 0.2.67): "21.456" at 1 becomes "21.5".
    No thousands separators, so the screen still reads the number; anything that isn't a number stays as it is."""
    if type(precision) is not int or not 0 <= precision <= 6:
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number):
        return value
    from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
    try:
        text = format(Decimal(str(value)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP), 'f')
    except InvalidOperation:  # more digits than Decimal's context holds, such as 1e30: the value is fine as it is
        return value
    return text[1:] if text.startswith('-') and not text.strip('-0.') else text

def ha_word(entity_id, suffix, attributes, entry, words):
    """Home Assistant's English word for `suffix` (`state.<state>`, or `state_attributes.<attribute>.state.<value>`) as its
    frontend picks it: the integration's word for the entity's translation key, then the domain's word for the state's
    device class, then the domain's. None when Home Assistant has none (frontend/get_translations `entity` and
    `entity_component`, app 0.2.67)."""
    if not isinstance(words, dict) or not words or not isinstance(entity_id, str):
        return None
    domain = entity_id.split('.', 1)[0]
    entry = entry if isinstance(entry, dict) else {}
    device_class = attributes.get('device_class') if isinstance(attributes, dict) else None
    keys = []
    if entry.get('platform') and entry.get('translation_key'):
        keys.append(f"component.{entry['platform']}.entity.{domain}.{entry['translation_key']}.{suffix}")
    if isinstance(device_class, str) and device_class:
        keys.append(f'component.{domain}.entity_component.{device_class}.{suffix}')
    keys.append(f'component.{domain}.entity_component._.{suffix}')
    return next((words[key] for key in keys if isinstance(words.get(key), str) and words[key]), None)

def state_word(entity_id, state, attributes, entry, words):
    """Home Assistant's word for a state ("rinsing" is "Rinsing", "heat_cool" is "Heat/Cool"), or None."""
    return ha_word(entity_id, f'state.{state}', attributes, entry, words) if isinstance(state, str) and state else None

def attribute_word(entity_id, attribute, value, attributes, entry, words):
    """Home Assistant's word for an attribute's value, such as a robot's suction level, or None."""
    if not isinstance(value, str) or not value:
        return None
    return ha_word(entity_id, f'state_attributes.{attribute}.state.{value}', attributes, entry, words)

def state_message(index, tile, states, extra=None, precision=None, entry=None):
    if tile['entity'] in BUILTIN:
        message = {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
                   'name': short(tile['name'] or BUILTIN[tile['entity']], 80), 'state': 'ok', 'a': {}}
        # The same wire form as any tile, so a chosen icon travels as its codepoint (app 0.2.74+).
        options = screen_options(tile, {})
        if options is not None:
            message['o'] = options
        return message
    state = states.get(tile['entity'], {})
    attrs = state.get('attributes', {})
    bounded = {}
    for key in ATTRS:
        value = attrs.get(key)
        if isinstance(value, bool):
            if key in BOOL_ATTRS:
                bounded[key] = value
            continue
        if value is None:
            continue
        if isinstance(value, (int, float)):
            # supported_features is a bit field (media players exceed 8 million); other numbers are display values.
            if math.isfinite(value) and abs(value) <= (2**31 if key == 'supported_features' else 1000000):
                bounded[key] = value
        elif isinstance(value, str):
            bounded[key] = short(value, 48)
        elif isinstance(value, list):
            # Attribute lists have bounded lengths, strings and numeric ranges.
            limit = 2 if key == 'hs_color' else 4 if key == 'fan_speed_list' else 8
            bounded[key] = [short(v, 48) if isinstance(v, str) else v for v in value[:limit]
                            if isinstance(v, str) or isinstance(v, (float, int)) and math.isfinite(v) and abs(v) <= 1000000]
    options = screen_options(tile, attrs, state.get('state'), entry)
    return {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
            'name': short(tile['name'] or attrs.get('friendly_name') or tile['entity'], 80),
            'state': short(rounded_state(state.get('state', 'unavailable'), precision) if tile['entity'].startswith('sensor.') else state.get('state', 'unavailable'), 160), 'a': bounded,
            **({'o': options} if options is not None else {}), **({'x': extra} if extra else {})}

def encode(message):
    """The message as the firmware parses it: compact JSON, at most 4096 bytes."""
    raw = json.dumps(message, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 4096:
        raise ValueError('The screen message is too large.')
    return raw

def revision(message):
    """Short fingerprint of a layout message; the screen echoes it back on every ping."""
    return hashlib.sha256(json.dumps(message, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:12]

def packets(message, token=None):
    """The message as base64 chunks for the 255-character text inbox (firmware before 0.2.33)."""
    encoded = base64.b64encode(encode(message).encode()).decode('ascii')
    token = token or secrets.token_hex(8)
    chunks = [encoded[i:i+200] for i in range(0, len(encoded), 200)]
    return [f'{token}|{i}|{int(i == len(chunks)-1)}|{part}' for i, part in enumerate(chunks)]

def message_action(node):
    """Home Assistant action that hands a screen one whole message, or None without a node name."""
    return alert_service(node, MESSAGE_ACTION)

# ----- Alerts (firmware 0.2.31+): the reference the cheatsheet shows. tests/test_alerts_reference.py
# keeps every value here equal to what the board profiles compile. -----
ALERT_MIN_FIRMWARE = '0.2.31'
ALERT_EVENT = 'esphome.screen_alert'
ALERT_ENDINGS = (('ok', 'The button was pressed'), ('timeout', 'The timeout ran out'),
                 ('replaced', 'A new alert came over it'), ('remote', 'dismiss_alert from Home Assistant'))
ALERT_FALLBACK_ICON = 'alert-outline'
# (field, ESPHome type, label, explanation, example) in the order Home Assistant shows them.
ALERT_FIELDS = (
    ('title', 'string', 'Title', 'A single line at the top of the card; what doesn\'t fit gets an ellipsis. Empty becomes "Notification".', 'Someone is at the door'),
    ('subtitle', 'string', 'Subtitle', 'Explanation under the title, across multiple lines; a line break is fine. Empty is fine.', 'Door 3, back'),
    ('icon', 'string', 'Icon', 'A name from the list, also as mdi:name or as a hex codepoint (F12E6). Unknown or empty gives the warning triangle.', 'doorbell'),
    ('color', 'string', 'Color', 'One of the nine pastel colors of the tiles. Empty gives the white card.', 'orange'),
    ('button_text', 'string', 'Button text', 'The text on the button. Empty is "OK".', 'Coming'),
    ('timeout', 'int', 'Timeout', 'Seconds after which the card disappears on its own. 0 waits for the button, however long that takes. The button always closes it immediately, even with a timeout.', 0),
    ('flash', 'bool', 'Blinking', 'On makes the backlight blink four times when the alert arrives; the screen then just stays on.', True),
)
# Bytes per field the firmware keeps (the profiles' ALERT_*_MAX); an accented letter takes two.
ALERT_LIMITS = {'cyd': {'title': 48, 'subtitle': 160, 'button_text': 12},
                'guition': {'title': 64, 'subtitle': 240, 'button_text': 16},
                'jc8012p4a1': {'title': 64, 'subtitle': 240, 'button_text': 16}}
ALERT_SUGGESTED_ICONS = ('doorbell', 'bell', 'bell-ring', 'alert-outline', 'alarm-light', 'lock', 'lock-open-variant', 'door-open',
                         'window-closed-variant', 'motion-sensor', 'cctv', 'smoke-detector', 'water-alert', 'fire', 'mailbox', 'car',
                         'account', 'account-group', 'washing-machine', 'robot-vacuum', 'timer-outline', 'check')
# Not an argument of show_alert: the app sends the image itself to screens that can draw it (app 0.2.66, a Guition with
# firmware 0.2.57+) and leaves it out for the others. (name, label, explanation, example) like ALERT_FIELDS.
ALERT_CAMERA_FIELD = ('camera', 'Camera', 'A camera or image entity. A Guition with firmware 0.2.57+ shows its picture of that moment across the top of the card; a tap on it opens the camera full screen. Other screens show the alert without it. Only through the esp_screens_show_alert event.', 'camera.front_door')
# The firmware's MAX_TIMEOUT_SECONDS.
ALERT_MAX_TIMEOUT = 86400
# One alert for every screen (app 0.2.45): an automation fires one of these Home Assistant events and the
# app calls the matching action on each screen that can show it, screens added later included.
BROADCAST_SHOW, BROADCAST_DISMISS = 'esp_screens_show_alert', 'esp_screens_dismiss_alert'
BROADCAST_EVENTS = {BROADCAST_SHOW: 'show_alert', BROADCAST_DISMISS: 'dismiss_alert'}

def alert_service(node, action='show_alert'):
    """Home Assistant registers a device's actions as esphome.<node>_<action>, dashes as underscores."""
    return f"esphome.{node.replace('-', '_')}_{action}" if isinstance(node, str) and node else None

def alert_reference():
    """Everything the Alerts cheatsheet shows besides the screens themselves."""
    return {'min_firmware': ALERT_MIN_FIRMWARE, 'event': ALERT_EVENT,
            'broadcast': {'show': BROADCAST_SHOW, 'dismiss': BROADCAST_DISMISS},
            'endings': [{'action': action, 'label': label} for action, label in ALERT_ENDINGS],
            'fallback_icon': ALERT_FALLBACK_ICON, 'fallback_cp': tile_icons.GLYPHS[ALERT_FALLBACK_ICON],
            'fields': [{'name': name, 'type': kind, 'label': label, 'help': help_, 'example': example} for name, kind, label, help_, example in ALERT_FIELDS],
            'camera': dict(zip(('name', 'label', 'help', 'example'), ALERT_CAMERA_FIELD)),
            'limits': ALERT_LIMITS,
            'colors': [{'name': name, 'label': item['label'], 'color': item['color']} for name, item in TILE_BACKGROUNDS.items() if item['color']],
            'suggested_icons': [{'name': name, 'cp': tile_icons.GLYPHS[name]} for name in ALERT_SUGGESTED_ICONS],
            'extra_icons': [{'name': name, 'cp': cp} for name, cp in tile_icons.FIXED]}

def _whole(value):
    """A whole number from an int, a finite float or a numeric string; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    return value if isinstance(value, int) else None

def _flag(value):
    """True/False from a bool, 0/1 or the words Home Assistant accepts; None for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = value.strip().lower() if isinstance(value, str) else None
    return True if text in ('true', 'on', 'yes', '1') else False if text in ('false', 'off', 'no', '0') else None

def alert_data(data):
    """(service data, unusable field names): the seven show_alert fields from an event's data, typed the way
    Home Assistant validates ESPHome actions. A missing field is empty; so is an unusable one (YAML turns a bare
    `Yes` into a boolean), so one bad value never loses the whole alert. The firmware clips texts itself."""
    data = data if isinstance(data, dict) else {}
    service, unusable = {}, []
    for name, kind, *_ in ALERT_FIELDS:
        value = data.get(name)
        missing = value is None or value == ''
        if kind == 'string':
            usable = isinstance(value, (str, int, float)) and not isinstance(value, bool)
            service[name] = str(value) if usable and not missing else ''
        elif kind == 'int':
            number = _whole(value)
            usable = number is not None
            service[name] = min(max(number, 0), ALERT_MAX_TIMEOUT) if usable else 0
        else:
            flag = _flag(value)
            usable = flag is not None
            service[name] = bool(flag)
        if not usable and not missing:
            unusable.append(name)
    return service, unusable

def alert_camera(data):
    """(entity, usable): the alert's `camera` field when it names a camera or image entity; ('', True) without one."""
    value = data.get(ALERT_CAMERA_FIELD[0]) if isinstance(data, dict) else None
    if value is None or value == '':
        return '', True
    usable = isinstance(value, str) and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value.strip()) is not None and value.strip().split('.')[0] in CAMERA_DOMAINS
    return (value.strip(), True) if usable else ('', False)

def alert_targets(screens):
    """(ready, skipped): the paired screens that can show an alert now, and the others with the reason.

    One call per device: a screen that shows up twice (an old inbox next to a renamed one) counts once."""
    minimum = parse_firmware(ALERT_MIN_FIRMWARE)
    ready, skipped, nodes = [], [], set()
    for screen in screens:
        version = screen_firmware(screen)
        node = screen.get('node')
        if node in nodes:
            continue
        if not node:
            skipped.append((screen, 'device name unknown'))
        elif not screen.get('online'):
            skipped.append((screen, 'offline'))
        elif version is None or version < minimum:
            skipped.append((screen, f"firmware {screen.get('firmware') or 'unknown'}"))
        else:
            ready.append(screen)
            nodes.add(node)
    return ready, skipped

def screen_items(registry):
    """The ESPHome entities that describe a screen; the subset `discover_screens` needs."""
    return [item for item in registry if item.get('platform') == 'esphome' and item.get('original_name') in SCREEN_ENTITY_NAMES]

def discover_screens(registry, states, devices, areas):
    """Paired screens: every enabled ESPHome inbox with the diagnostics of its device."""
    device_map = {d['id']: d for d in devices}
    area_map = {a['area_id']: a['name'] for a in areas}
    versions = {item.get('device_id'): states.get(item['entity_id'], {}).get('state', 'unknown') for item in registry
                if item.get('platform') == 'esphome' and item.get('original_name') in NAME_SCREEN_FIRMWARE}
    boards = {item.get("device_id"): "guition" for item in registry
              if item.get("platform") == "esphome" and item.get("original_name") in NAME_GUITION_TYPE}
    boards.update({item.get("device_id"): "jc8012p4a1" for item in registry
                   if item.get("platform") == "esphome" and item.get("original_name") in NAME_JC8012_TYPE})
    def diagnostic(names, pattern):
        found = {}
        for item in registry:
            if item.get('platform') == 'esphome' and item.get('original_name') in names:
                value = states.get(item['entity_id'], {}).get('state', '')
                # A screen that restarts reports "unavailable", which reads like a device name.
                if isinstance(value, str) and value not in ('unknown', 'unavailable') and re.fullmatch(pattern, value):
                    found[item.get('device_id')] = value
        return found
    nodes = diagnostic(NAME_DEVICE_NAME, r'[a-z0-9][a-z0-9-]{0,30}')
    addresses = diagnostic(NAME_IP_ADDRESS, r'\d{1,3}(\.\d{1,3}){3}')
    screens = []
    for item in registry:
        eid = item['entity_id']
        if not (item.get('platform') == 'esphome' and eid.startswith('text.') and item.get('original_name') in NAME_TILE_SETTINGS and not item.get('disabled_by')):
            continue
        device = device_map.get(item.get('device_id'), {})
        state = states.get(eid, {})
        area = area_map.get(item.get('area_id') or device.get('area_id'), '')
        firmware = versions.get(item.get('device_id'), 'unknown')
        screens.append({'id': eid, 'name': device.get('name_by_user') or device.get('name') or eid,
                        'device_id': item.get('device_id'),
                        'firmware': firmware,
                        # What feature gates go by: the sensor, or Home Assistant's device registry while the screen is
                        # offline or restarting (app 0.2.78).
                        'firmware_known': known_firmware(firmware, device.get('sw_version')),
                        'board': boards.get(item.get('device_id'), 'unknown'),
                        'node': nodes.get(item.get('device_id')), 'ip': addresses.get(item.get('device_id')),
                        'device': device.get('name') or '',
                        'area': area, 'online': state.get('state') not in (None, 'unknown', 'unavailable'),
                        'status': state.get('state', 'Not connected')})
    return screens

def discover(registry, states, devices, areas):
    """(screens, entities): the paired screens and every entity a tile or the top bar can show."""
    device_map = {d['id']: d for d in devices}
    area_map = {a['area_id']: a['name'] for a in areas}
    screens = discover_screens(registry, states, devices, areas)
    entities = []
    for item in registry:
        eid = item['entity_id']
        tile = entity_id(eid)
        if not (tile or header_entity(eid)) or item.get('disabled_by'):
            continue
        device = device_map.get(item.get('device_id'), {})
        state = states.get(eid, {})
        area = area_map.get(item.get('area_id') or device.get('area_id'), '')
        entities.append({'id': eid, 'name': state.get('attributes', {}).get('friendly_name') or item.get('name') or item.get('original_name') or eid,
                         'device': device.get('name_by_user') or device.get('name') or '', 'area': area,
                         'state': state.get('state', 'unavailable'),
                         'icon': tile_icons.ha_icon(state.get('attributes')) or tile_icons.default_glyph(eid, state.get('state'), state.get('attributes'), item),
                         # Top-bar-only domains (a phone's tracker, a lock) stay out of the tile picker.
                         **({} if tile else {'tile': False})})
    # YAML entities may not have an entity-registry entry.
    registered = {e['id'] for e in entities}
    in_registry = {r['entity_id'] for r in registry}
    for eid, state in states.items():
        tile = entity_id(eid)
        if (tile or header_entity(eid)) and eid not in registered and eid not in in_registry:
            entities.append({'id': eid, 'name': state.get('attributes', {}).get('friendly_name', eid), 'device': '', 'area': '', 'state': state['state'],
                             'icon': tile_icons.ha_icon(state.get('attributes')), **({} if tile else {'tile': False})})
    return screens, sorted(entities, key=lambda e: e['name'].casefold())

def installation_yaml(data):
    board, name, friendly = data.get('board'), data.get('name'), data.get('friendly_name')
    if board not in REFS or not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,29}', name):
        raise ValueError('Choose a board and a unique name (lowercase letters, digits, dashes; 30 characters max).')
    if not isinstance(friendly, str) or not friendly.strip() or len(friendly) > 60:
        raise ValueError('Give the screen a recognizable name (60 characters max).')
    quote = lambda s: json.dumps(s, ensure_ascii=False)
    key, ota, ap = base64.b64encode(secrets.token_bytes(32)).decode(), secrets.token_urlsafe(24), secrets.token_urlsafe(12)
    return f'''# Keep this file safe: it contains the unique keys for this screen.
# Wi-Fi comes from the secrets.yaml of ESPHome Device Builder.
substitutions:
  DEVICE_NAME: {quote(name)}
  DEVICE_FRIENDLY_NAME: {quote(friendly.strip())}

esphome:
  name: {quote(name)}
  friendly_name: {quote(friendly.strip())}

packages:
  display:
    url: {REPO}
    ref: {REFS[board]}
    files: [packages/{board}.yaml]
    refresh: 0s
  local_overrides: !include {name}.local.yaml

api:
  encryption:
    key: {quote(key)}
ota:
  - platform: esphome
    password: {quote(ota)}
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  ap:
    ssid: {quote(name + ' Setup')}
    password: {quote(ap)}
captive_portal:
'''
