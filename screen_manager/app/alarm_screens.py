"""What the screens do when an alarm goes off, set once per alarm on the editor's Events page (docs/ALARM_PANEL.md).

Per alarm panel of Home Assistant this keeps two choices:

- `screens`: which screens open the keypad by themselves when the panel goes off or counts someone in. "all" (the
  default, also for a screen added later) or a list of screen ids. A chosen screen without the panel on a tile gets it
  as a tile without a cell (`bar: True`, core.BAR_CARDS_FEATURE, the way an entity of the top bar comes), so its card
  can open; a screen that is not chosen gets `alarm_wake: "off"` on the panel's tiles and stays quiet.
- `send_after`: after how many digits the code sends itself, "off" (the OK key, the default) or 4 to 8
  (catalogue/alarm_control_panel.yaml). Home Assistant never says how long a code is, and one alarm has the same codes
  on every screen, so it is the alarm's, not a tile's.

A panel nobody set keeps the defaults and is not stored. The screen itself decides the rest: it wakes when a state
arrives (alarm_state_arrived in the firmware), so nothing here waits on Home Assistant's events.
"""
import json
import threading
from pathlib import Path

import atomic
import catalogue

VERSION = 1
DOMAIN = 'alarm_control_panel'
ALL = 'all'
# off, then the lengths a code may have; the screen takes the same range (alarm_panel::send_after).
SEND_AFTER = tuple(catalogue.of_type(DOMAIN)['send_after'])


def is_alarm(entity):
    return isinstance(entity, str) and entity.startswith(DOMAIN + '.')


class AlarmScreens:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'alarm_screens.json'
        self.lock = threading.RLock()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        alarms = data.get('alarms') if isinstance(data, dict) else None
        self.alarms = {entity: self.clean(choice) for entity, choice in (alarms or {}).items() if is_alarm(entity) and isinstance(choice, dict)}
        self.alarms = {entity: choice for entity, choice in self.alarms.items() if choice}

    @staticmethod
    def clean(choice):
        """What of `choice` differs from the defaults, in the stored shape: {} for an alarm that keeps them."""
        out = {}
        screens = choice.get('screens', ALL)
        if isinstance(screens, list):
            out['screens'] = sorted({str(s) for s in screens if isinstance(s, str) and s})
        send_after = str(choice.get('send_after', SEND_AFTER[0]))
        if send_after in SEND_AFTER[1:]:
            out['send_after'] = send_after
        return out

    def save(self):
        with self.lock:
            atomic.write_text(self.path, json.dumps({'version': VERSION, 'alarms': self.alarms}, separators=(',', ':')), 0o644)

    def key(self):
        """Changes whenever a choice does: a screen's messages are written anew then (page_service.sync_pages)."""
        return json.dumps(self.alarms, sort_keys=True)

    # ---- one alarm ----
    def choice(self, entity):
        stored = self.alarms.get(entity) or {}
        return {'screens': stored.get('screens', ALL), 'send_after': stored.get('send_after', SEND_AFTER[0])}

    def set(self, entity, screens, send_after):
        """Keep the choices of one alarm; ValueError for a choice that is none."""
        if not is_alarm(entity):
            raise ValueError('not an alarm panel')
        if screens != ALL and not (isinstance(screens, list) and all(isinstance(s, str) and s for s in screens)):
            raise ValueError('screens')
        if str(send_after) not in SEND_AFTER:
            raise ValueError('send_after')
        choice = self.clean({'screens': screens, 'send_after': str(send_after)})
        with self.lock:
            if choice:
                self.alarms[entity] = choice
            else:
                self.alarms.pop(entity, None)
            self.save()
        return self.choice(entity)

    def wakes(self, entity, inbox):
        """Whether this screen opens the keypad by itself when the alarm goes off."""
        screens = self.choice(entity)['screens']
        return screens == ALL or inbox in screens

    # ---- what a screen gets ----
    def options(self, entity, inbox):
        """What every tile of the alarm on this screen carries besides its own options."""
        choice = self.choice(entity)
        return {**({'send_after': choice['send_after']} if choice['send_after'] != SEND_AFTER[0] else {}),
                **({} if self.wakes(entity, inbox) else {'alarm_wake': 'off'})}

    def with_options(self, tile, inbox):
        """`tile` with the alarm's options, unchanged for any other tile."""
        if not is_alarm(tile.get('entity')):
            return tile
        extra = self.options(tile['entity'], inbox)
        return {**tile, 'options': {**(tile.get('options') or {}), **extra}} if extra else tile

    @staticmethod
    def panels(states):
        """The alarm panels Home Assistant has, in the order of their ids."""
        return sorted(entity for entity in states if is_alarm(entity))

    def watched(self, inbox, states):
        """The alarms this screen opens by itself when they go off, on a tile or not."""
        return [entity for entity in self.panels(states) if self.wakes(entity, inbox)]

    def tiles(self, inbox, states, placed):
        """The tiles without a cell this screen gets for its alarms: one per alarm it watches that is not on one of
        `placed` (its tiles and the tiles of its top bar)."""
        on = {tile.get('entity') for tile in placed}
        return [self.with_options({'entity': entity, 'name': '', 'bar': True}, inbox)
                for entity in self.watched(inbox, states) if entity not in on]

    def view(self, states):
        """For the Events page: every alarm panel with its choices, and the code lengths that may be chosen. The screens
        to choose from are the editor's own list (its inventory)."""
        return {'alarms': [{'entity': entity, 'name': (states.get(entity, {}).get('attributes') or {}).get('friendly_name') or entity,
                            'code': bool((states.get(entity, {}).get('attributes') or {}).get('code_format')), **self.choice(entity)}
                           for entity in self.panels(states)],
                'send_after': list(SEND_AFTER)}
