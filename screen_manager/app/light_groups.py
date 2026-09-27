"""A light group's lamps (app 0.3.16 / firmware 0.3.9): what the screen's lamp page shows of each lamp of a group.

Home Assistant lists a group's lamps in the group's `entity_id` attribute (the light group helper and the old group
platform both do). Each lamp travels with its name as Home Assistant shows it, whether it is on, its brightness, the
colour it is on in (hue and saturation, app 0.4.0), and
what it can take besides that, from its own `supported_color_modes`: a colour (hs, xy, rgb, rgbw, rgbww), a white
shade (color_temp, with the lamp's own range), only dimming (brightness), or only switching (onoff). A lamp Home
Assistant no longer knows is left out; one that is unavailable is sent as such, so the screen can grey it.

The lamps go only to a screen that said it takes them (`group_lamps` in its hello), and never more than fit the
message: MAX_LAMPS at most, and within LAMPS_BYTES of JSON, so the tile's own state and its other extras still fit the
4096 bytes of one message.
"""
import json

MAX_LAMPS = 24
LAMPS_BYTES = 2400
NAME_LIMIT = 32
COLOR_MODES = ('hs', 'xy', 'rgb', 'rgbw', 'rgbww')


def lamp_ids(entity, states):
    """The lamps of a light group in Home Assistant's order: light entities only, never the group itself, each once."""
    if not entity.startswith('light.'):
        return []
    members = ((states.get(entity) or {}).get('attributes') or {}).get('entity_id')
    if not isinstance(members, (list, tuple)):
        return []
    seen, out = set(), []
    for eid in members:
        if isinstance(eid, str) and eid.startswith('light.') and eid != entity and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _int(value, low, high):
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def lamp(eid, state):
    """One lamp as the screen reads it (group_page.h, page_receiver.cpp): short keys, only what is there."""
    attrs = state.get('attributes') or {}
    name = attrs.get('friendly_name')
    item = {'e': eid, 'n': (name if isinstance(name, str) and name.strip() else eid.split('.', 1)[1])[:NAME_LIMIT]}
    raw = state.get('state')
    if raw == 'on':
        item['s'] = 1
    if raw in ('unavailable', 'unknown') or raw is None:
        item['u'] = 1
    modes = [m for m in attrs.get('supported_color_modes') or [] if isinstance(m, str)]
    color = any(m in COLOR_MODES for m in modes)
    temperature = 'color_temp' in modes
    # A lamp that only switches has no slider; every other mode dims (Home Assistant's brightness_supported).
    if modes and any(m != 'onoff' for m in modes):
        item['d'] = 1
    caps = (1 if color else 0) | (2 if temperature else 0)
    if caps:
        item['c'] = caps
    brightness = _int(attrs.get('brightness'), 0, 255)
    if raw == 'on' and brightness is not None:
        item['b'] = max(1, round(brightness * 100 / 255))
    # The colour a lamp is on in (app 0.4.0 / firmware 0.4.0): its hue and saturation, so its card paints in the colour
    # its tile shows (tile_controls::lamp_color). Home Assistant reports hs_color for a lamp showing a white shade too.
    hs = attrs.get('hs_color')
    if isinstance(hs, (list, tuple)) and hs:
        hue = _int(hs[0], 0, 360)
        saturation = _int(hs[1], 0, 100) if len(hs) > 1 else None
        if hue is not None and (color or (raw == 'on' and saturation)):
            item['h'] = hue % 360
        if hue is not None and raw == 'on' and saturation:
            item['sa'] = saturation
    if temperature:
        for key, attr in (('k', 'color_temp_kelvin'), ('lo', 'min_color_temp_kelvin'), ('hi', 'max_color_temp_kelvin')):
            value = _int(attrs.get(attr), 1000, 15000)
            if value is not None:
                item[key] = value
    return item


def lamps(entity, states):
    """The `lamps` extra of a light group, or None for a light that is not one. Lamps Home Assistant does not know are
    left out; the list stops at MAX_LAMPS and at LAMPS_BYTES of JSON."""
    out, size = [], 2
    for eid in lamp_ids(entity, states):
        state = states.get(eid)
        if not isinstance(state, dict):
            continue
        item = lamp(eid, state)
        cost = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) + 1
        if len(out) == MAX_LAMPS or size + cost > LAMPS_BYTES:
            break
        out.append(item)
        size += cost
    return out or None
