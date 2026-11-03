"""A doorbell's ring on the screens (docs/DOORBELL.md), from an event of Home Assistant's, as the alerts are.

An automation fires `esp_screens_doorbell` with the doorbell's camera, its trigger whatever rings at that house (a
doorbell's event entity, Reolink's Visitor sensor, a button, a motion sensor), and the screens it names, every screen when
it names none. A screen whose hello says `doorbell` (module doorbell, a P4 that streams) wakes, chimes and opens the camera
live with its sound; any other screen gets the camera's alert with its picture. `esp_screens_dismiss_doorbell` closes it.

A screen reports how the ring ended there (esphome.screen_doorbell): the first that answers it (a touch, or its close key)
closes it on the others; when nobody answered, the ring is missed, and the top bar of the doorbell screens shows it
("2 min ago") until someone opens it again there or a later ring of that camera is answered.

The event may name a door: a lock entity, or an action of the automation's own (a script, a gate's button). The view then
has a door key, which opens after a second tap and reports `door`; the app performs lock.unlock on the lock, or the action,
as it performs an alert's button, and sends the lock's state to the screens while the ring shows.
"""
import re
import secrets
import time

import tile_icons
from core import _whole, alert_action
from i18n import t

FEATURE = 'doorbell'
SHOW, DISMISS = 'esp_screens_doorbell', 'esp_screens_dismiss_doorbell'
EVENTS = (SHOW, DISMISS)
EVENT = 'esphome.screen_doorbell'
# Once per ring, what an automation of its own follows (a phone's notification of a missed ring): the app fires one of
# these when the first screen answers it, or when nobody did before its timeout, with its camera, title and the screen.
ANSWERED, MISSED = 'esp_screens_doorbell_answered', 'esp_screens_doorbell_missed'
# What the screen reports (module_doorbell.cpp). answered and closed end a ring for every screen.
ENDINGS = (('answered', 'Someone touched the view: the ring is answered and closes on the other screens'),
           ('closed', 'Its close key, or something else that closed it, such as a new alert'),
           ('missed', 'Nobody touched it before its timeout'),
           ('seen', 'A missed ring was opened again from the top bar'))
ANSWERS = ('answered', 'closed')
# A second tap on the view's door key: the app opens the ring's door (its lock, or its action). Not an ending.
DOOR = 'door'
# The op's `d`: what the door key is (module_doorbell.cpp, doorbell_door.h).
DOOR_LOCK, DOOR_ACTION = 1, 2
# How long after a ring its door may still be opened from a screen that shows it, and the app sends that lock's state:
# the view closes five minutes after its last touch, and every touch keeps it open, so a quarter of an hour at most.
DOOR_LIFE = 900
# Two door reports of one ring within this many seconds are one (a screen whose report Home Assistant delivered twice).
DOOR_AGAIN = 3
# How long a ring nobody touches stays on the glass, in seconds; the app counts it as missed a little after, also when no
# screen could report (one that may not send events to Home Assistant).
TIMEOUT, TIMEOUT_MIN, TIMEOUT_MAX, MISSED_GRACE = 60, 10, 600, 5
# How long a missed ring stays in the top bars after it rang, in minutes (`keep_minutes`): 0 or none until someone opens
# it, as before; the wizard offers KEEP_CHOICES and writes KEEP_NEW into a new automation. The screens count it
# themselves from the ring's moment (header_bar::Item::until), in standby too.
KEEP_MAX, KEEP_CHOICES, KEEP_NEW = 1440, (10, 30, 60, 240, 0), 30
# The alert of a screen without the doorbell's view: its icon.
ALERT_ICON = 'doorbell'
# The top bar's item of a missed ring: the doorbell's icon and how long ago it rang, which the screen counts itself.
ICON = tile_icons.ICONS['doorbell'][0]
# (field, type, label, explanation, example) as ALERT_FIELDS, in English as the Claude skill writes them; the editor gets
# them in its language (reference).
FIELDS = (
    ('camera', 'string', 'Camera', 'The camera entity of the doorbell. A screen that streams (an ESP32-P4) shows it live with its sound; any other screen shows its picture in an alert. Required.', 'camera.front_door'),
    ('title', 'string', 'Title', 'What the screen calls the doorbell, at the top of its view and as the alert\'s title. Empty takes the camera\'s name.', 'Front door'),
    ('screen', 'string', 'Screen', 'Which screens get the ring: a device name (such as kitchen-screen), the name Home Assistant shows, or a room, which reaches every screen in it. A list reaches several. Leave it out for every screen. A name that matches no screen sends nothing.', 'kitchen-screen'),
    ('timeout', 'int', 'Timeout', f'Seconds the ring stays when nobody touches it, {TIMEOUT_MIN} to {TIMEOUT_MAX}. Empty is {TIMEOUT}. A touch keeps it open.', TIMEOUT),
    ('keep_minutes', 'int', 'Keep missed', f'Minutes a ring nobody answered stays in the top bar of the screens with its view, counted from the ring, 1 to {KEEP_MAX}. Empty or 0: until someone opens it.', KEEP_NEW),
    ('sound', 'bool', 'Sound', 'Whether the doorbell\'s own sound plays at once when it rings, where the screen has a speaker. Empty or true: the view opens with Sound on. false: it opens quiet (a studio, a bedroom), and a tap on Sound turns it on.', True),
    ('chime', 'bool', 'Chime', 'Whether the screen plays its chime when it rings, where it has a speaker. Empty or true: it chimes. false: it rings without one, the view opens all the same.', True),
    ('lock', 'string', 'Lock', 'A lock entity the view\'s door key unlocks, after a second tap; the key shows its state. A lock that asks for a code needs a default code in Home Assistant (the lock\'s settings). Leave it out for no door key.', 'lock.front_door'),
    ('door_action', 'string', 'Door action', 'Instead of a lock: a Home Assistant action the door key performs after a second tap, such as script.open_gate or button.press. `door_data` gives its fields (entity_id, ...).', 'script.open_gate'),
    ('door_data', 'object', 'Door data', 'The fields of `door_action`, such as entity_id.', {'entity_id': 'button.gate_open'}),
)
LOCK_ENTITY = re.compile(r'lock\.[a-z0-9_]+')


def request(data):
    """(camera, title, timeout, unusable) of an esp_screens_doorbell event's data; camera None when it names none."""
    data = data if isinstance(data, dict) else {}
    unusable = []
    camera = data.get('camera')
    if not (isinstance(camera, str) and camera.startswith('camera.') and len(camera) <= 120):
        camera = None
        unusable.append('camera')
    title = data.get('title')
    if title is None or title == '':
        title = ''
    elif isinstance(title, (str, int, float)) and not isinstance(title, bool):
        title = str(title).strip()[:60]
    else:
        title = ''
        unusable.append('title')
    timeout = TIMEOUT
    if data.get('timeout') not in (None, ''):
        whole = _whole(data.get('timeout'))
        if whole is None:
            unusable.append('timeout')
        else:
            timeout = max(TIMEOUT_MIN, min(TIMEOUT_MAX, whole))
    return camera, title, timeout, unusable


def keep_of(data):
    """(minutes, unusable): how long a missed ring of the event stays in the top bars (`keep_minutes`), 0 for until
    someone opens it, at most KEEP_MAX."""
    value = (data if isinstance(data, dict) else {}).get('keep_minutes')
    if value in (None, ''):
        return 0, []
    whole = _whole(value)
    if whole is None or whole < 0:
        return 0, ['keep_minutes']
    return min(KEEP_MAX, whole), []


def sound_of(data, field='sound'):
    """(on, unusable): whether the view opens with its sound on (`field` sound), or chimes (`chime`): True unless the
    event's field says false."""
    value = (data if isinstance(data, dict) else {}).get(field)
    if value is None or value == '':
        return True, []
    if isinstance(value, bool):
        return value, []
    if isinstance(value, str) and value.strip().lower() in ('true', 'on', 'yes', 'false', 'off', 'no'):
        return value.strip().lower() in ('true', 'on', 'yes'), []
    return True, [field]


def door_of(data):
    """(door, unusable): the event's door, {'lock': entity} or {'action': action, 'data': fields}, None without one. A lock
    goes before an action when the event names both."""
    data = data if isinstance(data, dict) else {}
    lock = data.get('lock')
    if lock not in (None, ''):
        if isinstance(lock, str) and LOCK_ENTITY.fullmatch(lock.strip()) and len(lock) <= 120:
            return {'lock': lock.strip()}, []
        return None, ['lock']
    action, usable = alert_action(data, 'door_action', 'door_data')
    if not usable:
        return None, ['door_action']
    return ({'action': action[0], 'data': action[1]} if action else None), []


def door_blocked(lock, states, entry):
    """Why the door key cannot unlock `lock`, None when it can: a lock that asks for a code (its code_format) without a
    default code in its registry options (core.lock_extras); the view has no keypad, nothing may lie over its picture."""
    attributes = ((states.get(lock) or {}).get('attributes') or {})
    options = (entry or {}).get('options') if isinstance(entry, dict) else None
    saved = isinstance(options, dict) and isinstance(options.get('lock'), dict) and bool(options['lock'].get('default_code'))
    if attributes.get('code_format') and not saved:
        return 'asks for a code and has no default code'
    return None


def name_of(camera, device_name, states):
    """What the screen calls the doorbell when the event says nothing: its camera's device as Home Assistant names it,
    else the camera's own name."""
    if device_name:
        return device_name
    friendly = ((states.get(camera) or {}).get('attributes') or {}).get('friendly_name')
    return friendly or camera


# How a trigger entity starts the automation, by what it is (the editor's wizard writes the trigger from it):
# `doorbell`, an event entity of Home Assistant's doorbell class (its trigger doorbell.rang); `event`, any other event
# entity (a new state); `on`, a sensor or switch that turns on while someone rings (Reolink's Visitor); `press`, a button.
TRIGGER_DOMAINS = {'event': 'event', 'binary_sensor': 'on', 'switch': 'on', 'input_boolean': 'on', 'button': 'press', 'input_button': 'press'}
# The binary sensors Home Assistant's integrations make for a doorbell's button, by integration and translation key (read
# from their binary_sensor.py): Reolink's Visitor, UniFi Protect's Doorbell, Yale's and August's Ding, Skybell's Button.
PRESS_KEYS = {('reolink', 'visitor'), ('unifiprotect', 'doorbell'), ('yale', 'ding'), ('august', 'ding'), ('skybell', 'button')}


def trigger_kind(entity, attributes=None):
    """How `entity` starts the automation (TRIGGER_DOMAINS), `doorbell` for an event entity of the doorbell class."""
    domain = str(entity).split('.', 1)[0]
    if domain == 'event' and (attributes or {}).get('device_class') == 'doorbell':
        return 'doorbell'
    return TRIGGER_DOMAINS.get(domain)


def suggestions(states, registry, device_entries):
    """The doorbells this Home Assistant has, for the wizard to offer first: every event entity of the doorbell class and
    every press sensor of PRESS_KEYS, each with the camera on its device (camera_of) and its name. Only an offer: the
    automation is the person's own, and any entity can start it."""
    out = []
    for entity, state in sorted(states.items()):
        attributes = (state or {}).get('attributes') or {}
        entry = registry.get(entity) or {}
        if entity.startswith('event.') and attributes.get('device_class') == 'doorbell':
            kind = 'doorbell'
        elif entity.startswith('binary_sensor.') and (entry.get('platform'), entry.get('translation_key')) in PRESS_KEYS:
            kind = 'on'
        else:
            continue
        out.append({'trigger': entity, 'kind': kind, 'camera': camera_of(device_entries(entity), states),
                    'name': attributes.get('friendly_name') or entity})
    return out


def camera_of(entries, states):
    """The camera on a doorbell's device (`entries`: the registry entries of that device), one that is not disabled, and
    the first that Home Assistant has a state for; None without one."""
    cameras = [item.get('entity_id') for item in entries or () if isinstance(item, dict)
               and str(item.get('entity_id', '')).startswith('camera.') and not item.get('disabled_by')]
    usable = [entity for entity in cameras if (states.get(entity) or {}).get('state') not in (None, 'unavailable')]
    return (usable or cameras or [None])[0]


def reference():
    """What the editor's Events page shows of the doorbell, in the editor's language."""
    return {'show': SHOW, 'dismiss': DISMISS, 'event': EVENT, 'feature': FEATURE, 'answered': ANSWERED, 'missed': MISSED,
            'trigger_domains': TRIGGER_DOMAINS,
            'timeout': {'default': TIMEOUT, 'min': TIMEOUT_MIN, 'max': TIMEOUT_MAX},
            'keep': {'choices': list(KEEP_CHOICES), 'new': KEEP_NEW, 'max': KEEP_MAX},
            'fields': [{'name': name, 'type': kind, 'label': t(f'addon.doorbell.fields.{name}.label'),
                        'help': t(f'addon.doorbell.fields.{name}.help', min=TIMEOUT_MIN, max=TIMEOUT_MAX, default=TIMEOUT,
                                  most=KEEP_MAX),
                        'example': value} for name, kind, _, _, value in FIELDS],
            'endings': [{'action': action, 'label': t(f'addon.doorbell.endings.{action}')} for action, _ in ENDINGS]}


class Doorbells:
    """The rings of this app's lifetime: the ones going on, and the last one nobody answered (for the top bars)."""

    def __init__(self):
        # key -> {'camera', 'name', 'at', 'timeout', 'screens': inboxes with the view, 'alerts': nodes with the alert,
        # 'answered', 'since', 'door': door_of's door or None, 'nodes': the nodes with the view, 'gone': those whose view
        # closed, 'door_at': the last door report}
        self.rings = {}
        self.missed = None   # {'key', 'camera', 'name', 'at', 'keep'} or None

    def start(self, camera, name, timeout, screens, alerts=(), door=None, nodes=(), sound=True, chime=True, keep=0):
        key = secrets.token_hex(4)
        self.rings[key] = {'camera': camera, 'name': name, 'at': int(time.time()), 'timeout': timeout, 'screens': list(screens),
                           'alerts': list(alerts), 'answered': False, 'since': time.monotonic(), 'door': door,
                           'nodes': list(nodes), 'gone': set(), 'door_at': None, 'sound': sound, 'chime': chime,
                           'keep': keep}
        # Rings older than their longest life are history.
        for old in [k for k, ring in self.rings.items() if time.monotonic() - ring['since'] > max(TIMEOUT_MAX * 2, DOOR_LIFE)]:
            del self.rings[old]
        return key

    def message(self, key, close=False, door_state=None, link=None):
        """The op of ring `key`, or its close. A ring with a door says what its key is (`d`), and a lock its state (`ds`);
        one that opens quiet says so (`m`), one without its chime too (`nc`); `link`, the stream the app made for that
        screen as the event came (`l`), which its view opens at once instead of asking for one."""
        ring = self.rings.get(key)
        if close or ring is None:
            return {'v': 1, 'op': 'doorbell', 'k': key, 'c': 1}
        message = {'v': 1, 'op': 'doorbell', 'e': ring['camera'], 'n': ring['name'], 'k': key, 'r': ring['at'], 't': ring['timeout']}
        if ring.get('sound') is False:
            message['m'] = 1
        if ring.get('chime') is False:
            message['nc'] = 1
        if link:
            message['l'] = link
        door = ring.get('door')
        if door and door.get('lock'):
            message.update(d=DOOR_LOCK, ds=str(door_state or '')[:16])
        elif door:
            message['d'] = DOOR_ACTION
        return message

    @staticmethod
    def door_message(key, state):
        """A lock's new state for the door key of ring `key`, while its view shows."""
        return {'v': 1, 'op': 'doorbell', 'k': key, 'ds': str(state or '')[:16]}

    def gone(self, key, nodes):
        """The view of ring `key` closed on `nodes` (their report, or the app closed it there)."""
        ring = self.rings.get(key)
        if ring is not None:
            ring['gone'].update(nodes)

    def back(self, key, node):
        """A screen opened ring `key` again (the missed ring from its top bar)."""
        ring = self.rings.get(key)
        if ring is not None:
            ring['gone'].discard(node)
            ring['since_seen'] = time.monotonic()

    def showing(self, key):
        """The nodes whose view of ring `key` may still show, within the door's life."""
        ring = self.rings.get(key)
        if ring is None or time.monotonic() - ring.get('since_seen', ring['since']) > DOOR_LIFE:
            return []
        return [node for node in ring['nodes'] if node not in ring['gone']]

    def door_press(self, key, node):
        """A screen's door report: the door to open (the ring's lock or action), or None when it may not: no such ring or
        no door, a screen that did not show it or whose view closed, past the door's life, or a repeat within
        DOOR_AGAIN seconds."""
        ring = self.rings.get(key)
        if ring is None or not ring.get('door') or node not in self.showing(key):
            return None
        now = time.monotonic()
        if ring['door_at'] is not None and now - ring['door_at'] < DOOR_AGAIN:
            return None
        ring['door_at'] = now
        return ring['door']

    def ring(self, key):
        return self.rings.get(key)

    def answered(self, key):
        """A screen answered or closed ring `key`: (the screens with its view, the nodes with its alert) to close it on,
        once."""
        ring = self.rings.get(key)
        if ring is None or ring['answered']:
            return [], []
        ring['answered'] = True
        if self.missed and self.missed['camera'] == ring['camera']:
            self.missed = None
        return ring['screens'], ring['alerts']

    def open(self):
        """The rings nobody answered yet, newest first: what esp_screens_dismiss_doorbell closes."""
        return [key for key, ring in sorted(self.rings.items(), key=lambda item: -item[1]['since']) if not ring['answered']]

    def unanswered(self, key):
        """A ring's timeout after it rang: True when it became the missed ring (nobody answered it)."""
        ring = self.rings.get(key)
        if ring is None or ring['answered']:
            return False
        self.missed = {'key': key, 'camera': ring['camera'], 'name': ring['name'], 'at': ring['at'],
                       'keep': ring.get('keep', 0)}
        return True

    def seen(self):
        """Someone opened the missed ring again on a screen: it leaves every top bar. True when there was one."""
        was = self.missed is not None
        self.missed = None
        return was

    def bar_item(self, now=None):
        """The top bar's item of the missed ring, for a screen whose hello says `doorbell`; None without one. A ring kept
        for a while says until when (`x`), and the screens take it away then by their own clock; past it, it is gone here
        too."""
        if not self.missed:
            return None
        until = self.missed['at'] + 60 * self.missed['keep'] if self.missed.get('keep') else 0
        if until and (time.time() if now is None else now) >= until:
            self.missed = None
            return None
        item = {'k': 'ago', 'i': ICON, 'e': self.missed['at'], 'b': 1}
        if until:
            item['x'] = until
        return item


def with_missed(items, item, limit):
    """A page's bar items with the missed ring's item first, at most `limit` (the screen refuses a longer bar)."""
    if not item:
        return items
    return [item, *items][:limit]
