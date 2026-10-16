"""What a vacuum's card shows beyond its own state, for a screen with the card's module (its hello says vacuum_card).

Home Assistant is the source of all of it, and the card shows only what a robot offers:

- the map: an image or camera entity on the robot's device (Roborock and Ecovacs keep theirs as an image, Neato and
  Tuya as a camera; Home Assistant's MAP flag is set by almost none, so the device decides). Its state, the moment the
  picture last changed, is the mark the screen asks a new picture by; the picture itself goes through this app's
  picture port, cleaned up and in the screen's colours (vacuum_map.py).
- the rooms: the areas someone linked to the robot's segments in Home Assistant (the vacuum's entity options,
  `vacuum.area_mapping`), in Home Assistant's order, grouped by floor as its own "clean by area" view groups them.
  `vacuum.clean_area` cleans them (Home Assistant 2026.3+, VacuumEntityFeature.CLEAN_AREA). A robot with more than one
  map skips segments of a map it is not on, so only the areas of the map it has now are offered.
- the routines: the buttons the robot's integration puts on its device (Roborock's routines from its app, an Ecovacs
  station's actions), without the ones that reset a consumable or set something up.
- why it stopped: the error sensor of its device, in Home Assistant's words, while there is one.
- how far it is: the cleaning progress and the floor it cleaned, while it cleans.

Everything is short and capped: a state message is at most 4096 bytes.
"""
import math
import re

import catalogue
import core
from light_effects import entity_name, strip_device_name

# The hello flag of a screen that draws the vacuum card of the module (module_vacuum.h).
FEATURE = 'vacuum_card'
MAX_ROOMS = 24
MAX_FLOORS = 6
MAX_ROUTINES = 24
AREA_ID = re.compile(r'[A-Za-z0-9_-]{1,40}')
# An error sensor says "nothing wrong" in one of these.
NO_ERROR = frozenset(('', 'none', 'no_error', 'ok', 'normal', 'unknown', 'unavailable', '0'))
# The keys integrations give an error sensor, a progress sensor and a sensor of the floor cleaned this run.
ERROR_KEYS = ('vacuum_error', 'error', 'operational_error', 'dock_error')
PROGRESS_KEYS = ('clean_percent', 'cleaning_progress', 'clean_progress')
AREA_KEYS = ('cleaning_area', 'clean_area', 'cleaned_area')


def _usable(item):
    return isinstance(item, dict) and not item.get('disabled_by') and not item.get('hidden_by')


def _key_of(item, keys):
    """Whether a registry entry is one of these by its translation key, or by its entity id's end."""
    key = item.get('translation_key') or ''
    eid = item.get('entity_id') or ''
    return key in keys or eid.endswith(tuple('_' + k for k in keys))


def map_entity(entity, device, states):
    """The robot's map on its device: an image entity first, then a camera; with several maps (one per floor) the one
    of the map it is on now, when a `selected_map` select says which. None without one."""
    found = [item for item in device or () if _usable(item) and str(item.get('entity_id', '')).split('.')[0] in ('image', 'camera')
             and item.get('entity_id') != entity]
    if not found:
        return None
    selected = None
    for item in device or ():
        if _usable(item) and str(item.get('entity_id', '')).startswith('select.') and _key_of(item, ('selected_map', 'active_map')):
            selected = (states.get(item['entity_id']) or {}).get('state')
    def rank(item):
        eid = item['entity_id']
        name = item.get('original_name') or item.get('name') or ''
        on_map = 0 if selected and name == selected else 1
        return (on_map, 0 if eid.startswith('image.') else 1, eid)
    found.sort(key=rank)
    eid = found[0]['entity_id']
    state = states.get(eid) or {}
    if state.get('state') in (None, 'unavailable', 'unknown') and eid.startswith('image.'):
        return None
    # The mark: an image's state is the moment its picture last changed; a camera's the moment it last reported.
    mark = state.get('state') if eid.startswith('image.') else state.get('last_updated') or state.get('last_changed') or ''
    return {'e': eid, 'm': core.short(str(mark), 40)}


def _active_group(options, entity, device, states):
    """The name of the map the robot is on now (the segments' `group`), when it has more than one and says which."""
    groups = {segment.get('group') for segment in options.get('last_seen_segments') or () if isinstance(segment, dict)}
    groups.discard(None)
    if len(groups) <= 1:
        return None
    for item in device or ():
        if _usable(item) and str(item.get('entity_id', '')).startswith('select.') and _key_of(item, ('selected_map', 'active_map')):
            current = (states.get(item['entity_id']) or {}).get('state')
            if current in groups:
                return current
    return None


def rooms(entity, entry, device, states, areas, floors, glyph=None):
    """(rooms, floor names, unmapped): the areas linked to the robot's segments, each [area id, name, icon, floor],
    in Home Assistant's order of floors and areas; `unmapped` when the robot cleans by area but nobody linked any yet."""
    attrs = (states.get(entity) or {}).get('attributes') or {}
    if not (attrs.get('supported_features') or 0) & catalogue.bits('vacuum', 'CLEAN_AREA'):
        return [], [], False
    options = ((entry or {}).get('options') or {}).get('vacuum') or {}
    mapping = options.get('area_mapping')
    if not isinstance(mapping, dict) or not any(mapping.values()):
        return [], [], True
    group = _active_group(options, entity, device, states)
    if group:
        on_map = {segment.get('id') for segment in options.get('last_seen_segments') or ()
                  if isinstance(segment, dict) and segment.get('group') == group}
        mapping = {area: segments for area, segments in mapping.items() if any(s in on_map for s in segments or ())}
    by_id = {area.get('area_id'): area for area in areas or () if isinstance(area, dict)}
    floor_order = [floor for floor in floors or () if isinstance(floor, dict) and floor.get('floor_id')]
    floor_index = {floor['floor_id']: i for i, floor in enumerate(floor_order)}
    picked = []
    for position, (area_id, area) in enumerate(by_id.items()):
        if area_id not in mapping or not mapping.get(area_id) or not isinstance(area_id, str) or not AREA_ID.fullmatch(area_id):
            continue
        floor = area.get('floor_id')
        picked.append((floor_index.get(floor, len(floor_order)), position, area))
    picked.sort(key=lambda item: (item[0], item[1]))
    used = sorted({item[0] for item in picked})
    # Floors only when the rooms lie on more than one: "Other areas" (Home Assistant's own words) for those on none.
    several = len(used) > 1
    names = [floor_order[i]['name'] if i < len(floor_order) else None for i in used] if several else []
    out = []
    for floor, _, area in picked[:MAX_ROOMS]:
        icon = area.get('icon')
        codepoint = glyph(icon) if glyph and isinstance(icon, str) else None
        out.append([area['area_id'], core.short(str(area.get('name') or area['area_id']), 24),
                    str(codepoint) if codepoint else '', used.index(floor) if several else 0])
    return out, [core.short(name or '', 24) for name in names][:MAX_FLOORS], False


def routines(entity, device, states, words=None, device_name=None):
    """The buttons on the robot's device that run something: no reset of a consumable, nothing that sets it up, each
    [entity, name] as Home Assistant names it."""
    out = []
    for item in device or ():
        eid = str(item.get('entity_id', ''))
        if not eid.startswith('button.') or not _usable(item) or item.get('entity_category'):
            continue
        if (states.get(eid) or {}).get('state') == 'unavailable':
            continue
        name = strip_device_name(entity_name(eid, item, states, words), device_name)
        out.append([eid, core.short(name, 32)])
    out.sort(key=lambda row: row[1].casefold())
    return out[:MAX_ROUTINES]


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def payload(entity, states, device, entries, areas=None, floors=None, words=None, device_name=None, glyph=None):
    """The `vc` block of a vacuum's state message; None when there is nothing beyond its own state."""
    entry = (entries or {}).get(entity) or {}
    state = (states.get(entity) or {}).get('state')
    result = {}
    found = map_entity(entity, device, states)
    if found:
        result['map'] = found
    rows, floor_names, unmapped = rooms(entity, entry, device, states, areas, floors, glyph)
    if rows:
        result['rooms'] = rows
    if floor_names:
        result['floors'] = floor_names
    if unmapped:
        result['unmapped'] = 1
    buttons = routines(entity, device, states, words, device_name)
    if buttons:
        result['rt'] = buttons
    for item in device or ():
        eid = str(item.get('entity_id', ''))
        if not eid.startswith('sensor.') or not _usable(item):
            continue
        sensor = states.get(eid) or {}
        value, attrs = sensor.get('state'), sensor.get('attributes') or {}
        if _key_of(item, ERROR_KEYS) and 'err' not in result and isinstance(value, str) and value.lower() not in NO_ERROR:
            word = core.state_word(eid, value, attrs, item, words) or value.replace('_', ' ').capitalize()
            result['err'] = core.short(word, 48)
        elif state == 'cleaning' and _key_of(item, PROGRESS_KEYS) and 'pg' not in result:
            number = _number(value)
            if number is not None and 0 <= number <= 100:
                result['pg'] = int(round(number))
        elif state == 'cleaning' and _key_of(item, AREA_KEYS) and 'ar' not in result:
            number = _number(value)
            if number is not None and 0 <= number < 100000:
                result['ar'] = round(number, 1)
    return result or None


def related(entity, device, states):
    """The entities whose change changes the block: the map, the error, progress and area sensors, the routines and the
    map select (a robot that changes floor offers other rooms)."""
    out = []
    found = map_entity(entity, device, states)
    if found:
        out.append(found['e'])
    for item in device or ():
        eid = str(item.get('entity_id', ''))
        if not _usable(item):
            continue
        if eid.startswith('sensor.') and _key_of(item, ERROR_KEYS + PROGRESS_KEYS + AREA_KEYS):
            out.append(eid)
        elif eid.startswith('select.') and _key_of(item, ('selected_map', 'active_map')):
            out.append(eid)
        elif eid.startswith('button.') and not item.get('entity_category'):
            out.append(eid)
    return out
