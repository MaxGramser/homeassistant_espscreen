"""Settings that are ESPHome entities of a screen's own device: a plugin's settings (docs/PLUGINS.md, "A plugin's settings
on a screen") and a board's extras (docs/SETTINGS.md, "A board's own settings").

Both are the same kind of row: found in Home Assistant's entity registry by the name the entity has in its YAML, drawn
in the editor as the screen's own rows are, and changed through Home Assistant at once, so the screen's settings page,
Home Assistant and the app show one value. This module is the one way both go.
"""
import re

import core
from i18n import english, t

SETTING_DOMAINS = ('switch', 'number', 'select', 'text', 'button')
STATUS_DOMAINS = ('sensor',)       # an ESPHome text sensor is a sensor in Home Assistant


def object_id(name):
    """An entity's name as ESPHome writes it in an id ("Tap sound" is tap_sound): its snake_case and sanitize."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', str(name).replace(' ', '_').lower())


def entities(manager, screen, settings):
    """{key: entity_id} of these settings and their status sensors on this screen. Found in Home Assistant's entity
    registry by the name the entity has in its YAML (`original_name`, which a rename in Home Assistant leaves alone) on
    the screen's own device; an entity without one is found by the end of its entity id. Never by `unique_id`, whose
    shape changes with the ESPHome integration's versions."""
    device = (screen or {}).get('device_id')
    registry = [item for item in getattr(manager.ha, 'registry', None) or []
                if isinstance(item, dict) and isinstance(item.get('entity_id'), str) and device
                and item.get('device_id') == device]
    wanted = {}
    for setting in settings:
        wanted[setting['key']] = SETTING_DOMAINS
        if setting.get('status'):
            wanted[setting['status']] = STATUS_DOMAINS
    found = {}
    for key, domains in wanted.items():
        ours = [item for item in registry if item['entity_id'].split('.')[0] in domains]
        by_name = [item['entity_id'] for item in ours
                   if item.get('platform') == 'esphome' and item.get('original_name')
                   and object_id(item['original_name']) == key]
        by_end = [item['entity_id'] for item in ours if item['entity_id'].endswith('_' + key)]
        if by_name or by_end:
            found[key] = (by_name or by_end)[0]
    return found


def row(setting, found, states, label, hint, online):
    """One row as the editor draws it: {key, entity, kind, label, hint, value, available} and what its kind needs."""
    eid = found.get(setting['key'])
    state = states.get(eid) or {} if eid else {}
    attrs = state.get('attributes') or {}
    kind = eid.split('.')[0] if eid else None
    value = state.get('state')
    # A button's state is when it was last pressed: it is there when it is not unavailable.
    available = bool(eid) and value not in (None, 'unavailable') and (kind == 'button' or value != 'unknown') and online
    out = {'key': setting['key'], 'entity': eid, 'kind': kind, 'label': label, 'hint': hint, 'available': bool(available)}
    if kind == 'switch':
        out['value'] = value == 'on'
    elif kind == 'number':
        try:
            out['value'] = float(value)
        except (TypeError, ValueError):
            out['value'] = None
        out.update(min=attrs.get('min'), max=attrs.get('max'), step=attrs.get('step') or 1,
                   unit=attrs.get('unit_of_measurement') or '')
    elif kind == 'select':
        out.update(value=value, options=[o for o in attrs.get('options') or [] if isinstance(o, str)][:48])
    elif kind == 'text':
        out.update(value=value if value not in (None, 'unknown', 'unavailable') else '',
                   min=attrs.get('min') or 0, max=min(int(attrs.get('max') or 255), 255),
                   password=attrs.get('mode') == 'password')
    elif kind == 'button' and setting.get('status'):
        status = states.get(found.get(setting['status'])) or {}
        words = status.get('state')
        out['status'] = core.short(words, 64) if words not in (None, '', 'unknown', 'unavailable') else None
    return out


async def change(manager, entity, value, refused):
    """Change one such entity through Home Assistant, in the way its domain takes: a switch on or off, a number, an
    option, a text within its length, a button pressed (value true). `refused` is the error for anything else."""
    domain = entity.split('.')[0]
    attrs = ((getattr(manager.ha, 'states', {}) or {}).get(entity) or {}).get('attributes') or {}
    if domain == 'switch' and isinstance(value, bool):
        await manager.ha.call_service('switch', 'turn_on' if value else 'turn_off', {'entity_id': entity})
    elif domain == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool):
        await manager.ha.call_service('number', 'set_value', {'entity_id': entity, 'value': value})
    elif domain == 'select' and isinstance(value, str) and len(value) <= 64:
        await manager.ha.call_service('select', 'select_option', {'entity_id': entity, 'option': value})
    elif domain == 'text' and isinstance(value, str) and \
            int(attrs.get('min') or 0) <= len(value) <= min(int(attrs.get('max') or 255), 255):
        await manager.ha.call_service('text', 'set_value', {'entity_id': entity, 'value': value})
    elif domain == 'button' and value is True:
        await manager.ha.call_service('button', 'press', {'entity_id': entity})
    else:
        raise ValueError(refused)
    return {'ok': True}


# ---- A board's extras ----

def extras_of(screen):
    """The settings a screen's board lists (boards.yaml `settings`, through boards.json), in their order."""
    board = core.board_of(screen) if screen else None
    return [{'key': key} for key in (core.SHAPES.get(board, {}).get('catalog', {}).get('settings') or [])]


def extras_for(manager, inbox, language='en'):
    """A screen's extras as the editor draws them: [{key, entity, kind, label, hint, value, available, ...}], with
    their words from the app's translations (addon.labels.extras)."""
    screen = manager.screen(inbox)
    if screen is None:
        raise ValueError(t('addon.errors.not_paired'))
    settings = extras_of(screen)
    if not settings:
        return []
    found = entities(manager, screen, settings)
    states = getattr(manager.ha, 'states', {}) or {}
    rows = []
    for setting in settings:
        base = f"addon.labels.extras.{setting['key']}"
        label = {'en': english(f'{base}.label'), language: t(f'{base}.label')}
        hint = {'en': english(f'{base}.hint'), language: t(f'{base}.hint')}
        rows.append(row(setting, found, states, label, hint, screen.get('online')))
    return rows


async def set_extra(manager, inbox, entity, value):
    """Change one extra of this screen through Home Assistant: only an entity its board lists, of its own device."""
    screen = manager.screen(inbox)
    if screen is None:
        raise ValueError(t('addon.errors.not_paired'))
    refused = t('addon.errors.extras.request')
    if not isinstance(entity, str) or entity not in entities(manager, screen, extras_of(screen)).values():
        raise ValueError(refused)
    return await change(manager, entity, value, refused)
