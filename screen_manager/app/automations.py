"""Automations the editor's Events page puts into Home Assistant for the person (docs/DOORBELL.md, "Into Home Assistant").

The wizard of Events builds an automation (a trigger the person picked, and one of our own events as its action: a
doorbell's ring or an alert) and the app saves it the way Home Assistant's own automation editor does: POST
/api/config/automation/config/<id>, which writes automations.yaml and reloads the automations, so no restart is needed.
The app only writes automations whose every action fires one of our events, and only under ids of its own (`tessera_`),
so it never touches an automation the person made. Home Assistant lets only an administrator write them; the add-on's
token is one.
"""
import re
import secrets

# The events an automation of this app may fire, by the wizard's kind.
KINDS = {'doorbell': ('esp_screens_doorbell',), 'alert': ('esp_screens_show_alert',)}
PREFIX = 'tessera_'
# Every automation of this app is called "Tessera: <name>" in Home Assistant, so its list shows which ones came from here.
TITLE = 'Tessera: '
ID = re.compile(r'^tessera_(doorbell|alert)_[a-z0-9]{8}$')
MAX_TRIGGERS = 8


def new_id(kind):
    return f'{PREFIX}{kind}_{secrets.token_hex(4)}'


def kind_of(automation_id):
    """The wizard's kind of one of our ids, None for any other id."""
    found = ID.match(str(automation_id or ''))
    return found.group(1) if found else None


def checked(kind, config):
    """The automation to save, as Home Assistant's editor sends it, or a ValueError: an alias, triggers, and actions that
    each fire one of `kind`'s events with their data. Nothing else may come in through here."""
    if kind not in KINDS or not isinstance(config, dict):
        raise ValueError('unknown kind')
    alias = config.get('alias')
    triggers, actions = config.get('triggers'), config.get('actions')
    if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
        raise ValueError('alias')
    if not isinstance(triggers, list) or not 0 < len(triggers) <= MAX_TRIGGERS or not all(isinstance(t, dict) and t.get('trigger') for t in triggers):
        raise ValueError('triggers')
    if not isinstance(actions, list) or not actions:
        raise ValueError('actions')
    for action in actions:
        if not isinstance(action, dict) or set(action) - {'event', 'event_data'} or action.get('event') not in KINDS[kind]:
            raise ValueError('actions')
        if not isinstance(action.get('event_data', {}), dict):
            raise ValueError('actions')
    name = alias.strip()
    name = name[len(TITLE):].strip() if name.lower().startswith(TITLE.lower()) else name
    out = {'alias': TITLE + name, 'description': str(config.get('description') or '')[:400], 'triggers': triggers,
           'conditions': [], 'actions': actions, 'mode': 'single'}
    return out


def listed(states, kind=None):
    """The automations of Tessera in Home Assistant's states (an automation entity carries its id and name): the ones this
    app saved (an id of ours) and any whose name starts with "Tessera:". Entity, id, kind (None for one this app did not
    save, which it never changes), name, whether it is on and when it last ran, by name. With `kind`, only that kind's."""
    out = []
    for entity, state in states.items():
        if not entity.startswith('automation.'):
            continue
        attributes = (state or {}).get('attributes') or {}
        name = str(attributes.get('friendly_name') or entity)
        found = kind_of(attributes.get('id'))
        if not found and not name.lower().startswith(TITLE.strip().lower()):
            continue
        if kind is not None and found != kind:
            continue
        out.append({'entity': entity, 'id': attributes.get('id'), 'kind': found, 'name': name,
                    'on': (state or {}).get('state') == 'on', 'last': attributes.get('last_triggered')})
    return sorted(out, key=lambda item: item['name'].lower())
