"""A cover group's covers (firmware 0.57.0): what the screen's group page shows of each cover of a group, as
light_groups.py does for a light group's lamps.

Home Assistant lists a group's members in the group's `entity_id` attribute (the cover group helper and the old group
platform both do), and its own more-info dialog shows each of them as a tile with the cover-position feature. Each cover
travels with its name as Home Assistant shows it, its state, its position and its tilt where it reports them, its own
`supported_features` (the screen reads them with the rules of every cover tile: tile_controls::cover_card) and its
device class (a curtain's and a gate's keys point sideways). A cover Home Assistant no longer knows is left out; one that
is unavailable is sent as such, so the screen can grey it.

The covers go only to a screen whose hello lists `group_covers`, and never more than fit the message: MAX_COVERS at
most, and within COVERS_BYTES of JSON, so the tile's own state and its other extras still fit the 4096 bytes of one
message.
"""
import json

from light_groups import LAMPS_BYTES as COVERS_BYTES, MAX_LAMPS as MAX_COVERS, NAME_LIMIT, _int

FEATURE = 'group_covers'


def cover_ids(entity, states):
    """The covers of a cover group in Home Assistant's order: cover entities only, never the group itself, each once."""
    if not entity.startswith('cover.'):
        return []
    members = ((states.get(entity) or {}).get('attributes') or {}).get('entity_id')
    if not isinstance(members, (list, tuple)):
        return []
    seen, out = set(), []
    for eid in members:
        if isinstance(eid, str) and eid.startswith('cover.') and eid != entity and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def cover(eid, state):
    """One cover as the screen reads it (group_page.h, page_receiver.cpp): short keys, only what is there."""
    attrs = state.get('attributes') or {}
    name = attrs.get('friendly_name')
    item = {'e': eid, 'n': (name if isinstance(name, str) and name.strip() else eid.split('.', 1)[1])[:NAME_LIMIT]}
    raw = state.get('state')
    if raw in ('unavailable', 'unknown') or raw is None:
        item['u'] = 1
    elif isinstance(raw, str):
        item['s'] = raw[:16]
    features = _int(attrs.get('supported_features'), 0, 2 ** 31 - 1)
    if features:
        item['f'] = features
    for key, attr in (('p', 'current_position'), ('t', 'current_tilt_position')):
        value = _int(attrs.get(attr), 0, 100)
        if value is not None:
            item[key] = value
    device_class = attrs.get('device_class')
    if isinstance(device_class, str) and device_class:
        item['dc'] = device_class[:16]
    return item


def covers(entity, states):
    """The `covers` extra of a cover group, or None for a cover that is not one. Covers Home Assistant does not know are
    left out; the list stops at MAX_COVERS and at COVERS_BYTES of JSON."""
    out, size = [], 2
    for eid in cover_ids(entity, states):
        state = states.get(eid)
        if not isinstance(state, dict):
            continue
        item = cover(eid, state)
        cost = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) + 1
        if len(out) == MAX_COVERS or size + cost > COVERS_BYTES:
            break
        out.append(item)
        size += cost
    return out or None
