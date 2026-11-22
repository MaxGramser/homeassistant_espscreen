"""A screen's measuring sensors follow its Debug mode in Home Assistant (debug_sensors.py, docs/SETTINGS.md).

The firmware marks its measuring sensors `disabled_by_default`; the app switches them on in Home Assistant while a
screen's Debug mode is on and undoes only its own work. The fake registry below holds what Home Assistant's
config/entity_registry/list gives: `disabled_by` is None, "integration" (the firmware's mark) or "user"."""
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
import debug_sensors  # noqa: E402
import reports  # noqa: E402


def entity(entity_id, name, off_by=None, device='a', category='diagnostic'):
    return {'entity_id': entity_id, 'original_name': name, 'device_id': device, 'platform': 'esphome',
            'entity_category': category, 'disabled_by': off_by}


class FakeHa:
    def __init__(self, registry, debug):
        self.registry, self.calls = registry, []
        self.states = {'switch.a_debug_mode': {'state': debug}}

    async def request(self, kind, **data):
        self.calls.append((kind, data['entity_id'], data['disabled_by']))
        # Home Assistant announces the change and the app reads the registry again: a new list each time.
        self.registry = [dict(item, disabled_by=data['disabled_by']) if item['entity_id'] == data['entity_id'] else dict(item)
                         for item in self.registry]


class FollowsDebugMode(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.now = 0.0
        self.registry = [entity('switch.a_debug_mode', 'Debug mode'),
                         entity('sensor.a_heap_free', 'Heap Free', 'integration'),
                         entity('sensor.a_psram_free', 'Psram Free', 'integration'),
                         entity('sensor.a_screen_firmware', 'Screen firmware'),
                         entity('sensor.a_hidden', 'Hidden', 'integration', category=None),
                         entity('sensor.b_heap_free', 'Heap Free', 'integration', device='b')]

    def sensors(self):
        return debug_sensors.DebugSensors(Path(self.folder.name) / 'debug-sensors.json', clock=lambda: self.now)

    async def look(self, sensors, ha, after=debug_sensors.HOLD):
        await sensors.run(ha, {'a'})
        self.now += after
        await sensors.run(ha, {'a'})

    async def test_debug_mode_on_switches_the_measuring_sensors_on_and_off_takes_them_back(self):
        sensors, ha = self.sensors(), FakeHa(self.registry, 'on')
        await self.look(sensors, ha)
        self.assertEqual(ha.calls, [('config/entity_registry/update', 'sensor.a_heap_free', None),
                                    ('config/entity_registry/update', 'sensor.a_psram_free', None)])
        ha.calls.clear()
        ha.states['switch.a_debug_mode'] = {'state': 'off'}
        await sensors.run(ha, {'a'})
        self.assertEqual(ha.calls, [('config/entity_registry/update', 'sensor.a_heap_free', 'user'),
                                    ('config/entity_registry/update', 'sensor.a_psram_free', 'user')])
        # The next time, from a new start of the app: what it switched off is still its own.
        ha.calls.clear()
        ha.states['switch.a_debug_mode'] = {'state': 'on'}
        await self.look(self.sensors(), ha)
        self.assertEqual([call[1:] for call in ha.calls], [('sensor.a_heap_free', None), ('sensor.a_psram_free', None)])

    async def test_a_report_s_short_debug_mode_changes_nothing(self):
        sensors, ha = self.sensors(), FakeHa(self.registry, 'on')
        await self.look(sensors, ha, after=reports.CAPTURE_SECONDS + debug_sensors.INTERVAL)
        ha.states['switch.a_debug_mode'] = {'state': 'off'}
        await sensors.run(ha, {'a'})
        self.assertEqual(ha.calls, [])
        self.assertGreater(debug_sensors.HOLD, reports.CAPTURE_SECONDS + debug_sensors.INTERVAL)

    async def test_what_a_person_chose_stays(self):
        # On before the firmware marked it, or switched on by hand: never touched with Debug mode off.
        self.registry[1]['disabled_by'] = None
        sensors, ha = self.sensors(), FakeHa(self.registry, 'off')
        await sensors.run(ha, {'a'})
        self.assertEqual(ha.calls, [])
        # Switched off by hand: Debug mode does not bring it back.
        self.registry[1]['disabled_by'] = 'user'
        ha = FakeHa(self.registry, 'on')
        await self.look(sensors, ha)
        self.assertEqual([call[1:] for call in ha.calls], [('sensor.a_psram_free', None)])

    async def test_a_sensor_a_person_took_over_is_no_longer_the_app_s(self):
        sensors, ha = self.sensors(), FakeHa(self.registry, 'on')
        await self.look(sensors, ha)
        # Switched off by hand while Debug mode is on: stays off when Debug mode comes again.
        ha.registry = [dict(item, disabled_by='user') if item['entity_id'] == 'sensor.a_heap_free' else item for item in ha.registry]
        await sensors.run(ha, {'a'})
        ha.states['switch.a_debug_mode'] = {'state': 'off'}
        await sensors.run(ha, {'a'})
        # Switched on by hand while Debug mode is off: stays on from here.
        ha.registry = [dict(item, disabled_by=None) if item['entity_id'] == 'sensor.a_psram_free' else item for item in ha.registry]
        await sensors.run(ha, {'a'})
        ha.calls.clear()
        ha.states['switch.a_debug_mode'] = {'state': 'on'}
        await self.look(sensors, ha)
        ha.states['switch.a_debug_mode'] = {'state': 'off'}
        await sensors.run(ha, {'a'})
        self.assertEqual(ha.calls, [])
        self.assertEqual(sensors.ours, {})

    async def test_a_screen_that_is_away_keeps_what_it_has(self):
        sensors, ha = self.sensors(), FakeHa(self.registry, 'on')
        await self.look(sensors, ha)
        ha.calls.clear()
        ha.states['switch.a_debug_mode'] = {'state': 'unavailable'}
        await sensors.run(ha, {'a'})
        self.assertEqual(ha.calls, [])


class TheFirmwareSMarks(unittest.TestCase):
    """What the firmware switches off by default is a diagnostic sensor the app never reads through Home Assistant."""

    def marked(self):
        found = {}
        for path in sorted((ROOT / 'packages').rglob('*.yaml')):
            lines = path.read_text().splitlines()
            for at, line in enumerate(lines):
                if line.strip() == 'disabled_by_default: true':
                    name = re.fullmatch(r'\s*name: "(.+)"', lines[at - 1])
                    self.assertIsNotNone(name, f'{path.name}:{at + 1}: the mark stands right under the name')
                    found[name.group(1)] = path.name
        return found

    def test_the_measuring_sensors_are_marked(self):
        marked = self.marked()
        for name in ('Heap Free', 'Heap Fragmentation', 'Heap Largest Block', 'Heap Minimum Free', 'Psram Free',
                     'Psram Largest Block', 'Loop Stack Free', 'Panel misses', 'Panel watch'):
            self.assertIn(name, marked)

    def test_nothing_the_app_reads_is_marked(self):
        needed = set(core.SCREEN_ENTITY_NAMES) | {name for _, name in core.SETTING_ENTITIES.values()} | {debug_sensors.DEBUG_SWITCH}
        self.assertEqual(needed & set(self.marked()), set())


if __name__ == '__main__':
    unittest.main()
