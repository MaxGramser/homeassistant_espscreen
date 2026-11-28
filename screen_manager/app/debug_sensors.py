"""A screen's measuring sensors in Home Assistant, on while its Debug mode is on (docs/SETTINGS.md, "Debug mode").

A screen measures itself: its heap, its PSRAM, the loop task's stack, and on some boards the panel and the governor.
Those figures are for a diagnosis, and as entities that are always on they give Home Assistant a row to record every
few minutes for every screen, for nobody. So the firmware marks them `disabled_by_default` (packages/core.yaml and the
hardware files): Home Assistant has them, switched off, and anyone can switch one on there.

This module does that for a person who is looking into a screen. While a screen's Debug mode has been on for HOLD
seconds, its diagnostic entities that Home Assistant holds switched off are switched on; when Debug mode goes off, the
ones this app switched on are switched off again. It only undoes its own work:

- An entity a person switched on stays on, with Debug mode off too.
- An entity a person switched off while Debug mode is on stays off, and is no longer this app's.
- A screen that had these sensors on before the firmware marked them keeps them on: Home Assistant only reads the mark
  when it first meets an entity.

HOLD keeps a troubleshooting report out of it: the report turns Debug mode on for its 45 seconds of log and reads the
figures from the screen itself (reports.debug_on), so it needs nothing in Home Assistant. Switching an entity on makes
Home Assistant load the screen's integration again half a minute later, which takes the screen's link down for a
moment; that is fine for someone who asked for Debug mode and not for a report.

Home Assistant's registry takes "switched off by a person" and nothing else from outside (config/entity_registry/update),
so what this app switched off looks like a person's choice there. The store says which ones are this app's.
"""
import logging
import time

import atomic

LOG = logging.getLogger('screen_manager')

# How often the app looks.
INTERVAL = 15
# How long Debug mode has to be on before the sensors follow: longer than a report's read of the log (reports.py).
HOLD = 90
DEBUG_SWITCH = 'Debug mode'   # the name of the screen's switch (packages/core.yaml)
ON, OFF = 'on', 'off'


class DebugSensors:
    def __init__(self, path, clock=time.monotonic):
        self.path, self.clock = path, clock
        data = atomic.read_json(path, 1)
        ours = data.get('entities') if data else None
        # entity_id -> ON (this app switched it on, Debug mode is on) or OFF (this app switched it off again).
        self.ours = {str(k): v for k, v in (ours or {}).items() if v in (ON, OFF)}
        self.since = {}   # device -> when its Debug mode was first seen on

    def debug_of(self, device, registry, states):
        """True while the screen's Debug mode has been on for HOLD seconds, False when it is off, None when nobody can
        say (no switch, the screen away, or on for a shorter time)."""
        switch = next((item for item in registry if item.get('device_id') == device and item.get('platform') == 'esphome'
                       and item.get('original_name') == DEBUG_SWITCH and str(item.get('entity_id', '')).startswith('switch.')), None)
        state = (states.get(switch['entity_id']) or {}).get('state') if switch else None
        if state == 'off':
            self.since.pop(device, None)
            return False
        if state != 'on':
            return None   # away: it comes back as it was, so the count goes on
        began = self.since.setdefault(device, self.clock())
        return True if self.clock() - began >= HOLD else None

    async def run(self, ha, devices):
        """One look: the diagnostic entities of the screens `devices`, against each screen's Debug mode."""
        registry = [item for item in (ha.registry or []) if isinstance(item, dict)]
        before = dict(self.ours)
        for device in devices:
            debug = self.debug_of(device, registry, ha.states)
            if debug is None:
                continue
            for item in registry:
                if (item.get('device_id') != device or item.get('platform') != 'esphome'
                        or item.get('entity_category') != 'diagnostic'):
                    continue
                entity, off_by, mark = item.get('entity_id'), item.get('disabled_by'), self.ours.get(item.get('entity_id'))
                if debug and (off_by == 'integration' or (off_by == 'user' and mark == OFF)):
                    await self._switch(ha, item, None)
                    self.ours[entity] = ON
                elif not debug and mark == ON and off_by is None:
                    await self._switch(ha, item, 'user')
                    self.ours[entity] = OFF
                elif (debug and mark == ON and off_by == 'user') or (not debug and mark == OFF and off_by is None):
                    del self.ours[entity]   # a person chose otherwise: theirs from here on
        known = {item.get('entity_id') for item in registry}
        for entity in [entity for entity in self.ours if entity not in known]:
            del self.ours[entity]
        for device in [device for device in self.since if device not in devices]:
            del self.since[device]
        if self.ours != before:
            self._save()

    @staticmethod
    async def _switch(ha, item, off_by):
        await ha.request('config/entity_registry/update', entity_id=item['entity_id'], disabled_by=off_by)
        # The registry is read again when Home Assistant announces the change; until then this look's copy says it.
        item['disabled_by'] = off_by
        LOG.info('%s is switched %s in Home Assistant, with its screen\'s Debug mode', item['entity_id'], 'off' if off_by else 'on')

    def _save(self):
        try:
            atomic.write_json(self.path, {'version': 1, 'entities': self.ours})
        except OSError as error:
            LOG.warning('Could not keep which sensors follow Debug mode (%s)', type(error).__name__)
