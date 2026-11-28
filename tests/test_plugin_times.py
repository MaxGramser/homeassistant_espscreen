"""A time a plugin's data gives without an offset (plugin_fetch.epoch_of; docs/PLUGINS.md, "Times", and the plugins
repository's docs/FETCH.md): it is read in the field's own `tz`, else in Home Assistant's zone as the app knows it,
else in UTC, and never in the zone of the machine the app runs on.

Every test here runs with the machine in several zones, set for the test and put back after: CI stands in UTC, a
developer's machine wherever it is, a container wherever its host is. A test that only passes where it was written
proves nothing about the others, which is how this rule was found (app 0.4.102: an example's moments were an hour off
on a machine in UTC).
"""
import contextlib
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import plugin_examples  # noqa: E402
import plugin_fetch  # noqa: E402
import plugin_manifest  # noqa: E402

# Where the machine stands: CI's zone, the zone most of this was written in, and two far from both, one on each side.
MACHINES = ('UTC', 'Europe/Amsterdam', 'Pacific/Auckland', 'America/Los_Angeles')
NOON = '2026-11-24T12:00:00'             # a time as a web service or an entity writes it: no offset
SUMMER = '2026-07-01T12:00:00'           # and one in summer time


def utc(*parts):
    return int(datetime(*parts, tzinfo=timezone.utc).timestamp())


@contextlib.contextmanager
def machine(zone):
    """The process in `zone`, as a container started there, for the length of the block."""
    before = os.environ.get('TZ')
    os.environ['TZ'] = zone
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = before
        time.tzset()


def everywhere(test):
    """Runs a test once per machine zone, each as a case of its own."""
    def run(self):
        for zone in MACHINES:
            with self.subTest(machine=zone), machine(zone):
                # The machine really is there: its own reading of the same text is another moment in most of them.
                self.assertEqual(time.tzname[0] != 'UTC', zone != 'UTC')
                test(self)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


@unittest.skipUnless(hasattr(time, 'tzset'), 'needs a machine whose zone a process can set')
class TheRule(unittest.TestCase):
    @everywhere
    def test_the_field_s_own_zone_reads_it(self):
        self.assertEqual(plugin_fetch.epoch_of(NOON, 'Europe/Amsterdam'), utc(2026, 11, 24, 11))
        self.assertEqual(plugin_fetch.epoch_of(SUMMER, 'Europe/Amsterdam'), utc(2026, 7, 1, 10))
        self.assertEqual(plugin_fetch.epoch_of(NOON, 'Asia/Tokyo'), utc(2026, 11, 24, 3))

    @everywhere
    def test_else_home_assistant_s_zone_as_a_name_or_as_the_zone_the_app_keeps(self):
        """The app keeps Home Assistant's zone as a zone, not as its name (server.py); both read the same moment."""
        for zone in ('Asia/Tokyo', ZoneInfo('Asia/Tokyo')):
            self.assertEqual(plugin_fetch.epoch_of(NOON, None, zone), utc(2026, 11, 24, 3), zone)
        self.assertEqual(plugin_fetch.epoch_of(NOON, None, timezone.utc), utc(2026, 11, 24, 12))
        # The field's own zone goes before Home Assistant's, and a name that is no zone is no zone.
        self.assertEqual(plugin_fetch.epoch_of(NOON, 'America/New_York', ZoneInfo('Asia/Tokyo')), utc(2026, 11, 24, 17))
        self.assertEqual(plugin_fetch.epoch_of(NOON, 'Nowhere/At_All', ZoneInfo('Asia/Tokyo')), utc(2026, 11, 24, 3))

    @everywhere
    def test_else_utc_never_the_machine(self):
        self.assertEqual(plugin_fetch.epoch_of(NOON), utc(2026, 11, 24, 12))
        self.assertEqual(plugin_fetch.epoch_of(NOON, '', None), utc(2026, 11, 24, 12))
        self.assertEqual(plugin_fetch.epoch_of(NOON, 'Nowhere/At_All'), utc(2026, 11, 24, 12))

    @everywhere
    def test_a_time_that_says_its_offset_is_that_moment_whatever_the_zones(self):
        for text in ('2026-11-24T12:00:00Z', '2026-11-24T13:00:00+01:00', '2026-11-24T21:00:00+0900'):
            self.assertEqual(plugin_fetch.epoch_of(text, 'America/New_York', ZoneInfo('Asia/Tokyo')), utc(2026, 11, 24, 12), text)
        self.assertEqual(plugin_fetch.epoch_of(1795521600, 'Asia/Tokyo'), 1795521600)        # a number is seconds already
        self.assertEqual(plugin_fetch.epoch_of(1795521600000), 1795521600)                  # or milliseconds
        self.assertIsNone(plugin_fetch.epoch_of('soon', 'Asia/Tokyo'))


@unittest.skipUnless(hasattr(time, 'tzset'), 'needs a machine whose zone a process can set')
class AFetchAnswer(unittest.TestCase):
    """A web service's answer through a fetch's map (plugin_fetch.apply_map): a field without `tz` is read in Home
    Assistant's zone, which the app hands to the map."""
    # A map as a manifest's check leaves it (plugin_manifest.check_map): `at` names no zone, `plan` its own.
    MAP = plugin_manifest.check_map({'items': '$.passes[*]', 'sort': 'at', 'limit': 4, 'fields': {
        'line': 'line', 'at': {'path': 'when', 'as': 'epoch'},
        'plan': {'path': 'planned', 'as': 'epoch', 'tz': 'America/New_York'}}}, 'map', False)
    ANSWER = {'passes': [{'line': '12', 'when': NOON, 'planned': NOON}, {'line': '2', 'when': '2026-11-24T11:30:00', 'planned': NOON}]}

    @everywhere
    def test_a_list_and_one_object(self):
        home = ZoneInfo('Europe/Amsterdam')
        self.assertEqual(plugin_fetch.apply_map(self.MAP, self.ANSWER, zone=home), {'items': [
            {'line': '2', 'at': utc(2026, 11, 24, 10, 30), 'plan': utc(2026, 11, 24, 17)},
            {'line': '12', 'at': utc(2026, 11, 24, 11), 'plan': utc(2026, 11, 24, 17)}]})
        one = plugin_manifest.check_map({'fields': {'at': {'path': 'when', 'as': 'epoch'}}}, 'map', False)
        self.assertEqual(plugin_fetch.apply_map(one, {'when': NOON}, zone=home), {'at': utc(2026, 11, 24, 11)})
        # A home on the other side of the world reads the same answer as its own noon.
        self.assertEqual(plugin_fetch.apply_map(one, {'when': NOON}, zone=ZoneInfo('Asia/Tokyo')), {'at': utc(2026, 11, 24, 3)})

    @everywhere
    def test_the_answers_of_a_fetch_with_each(self):
        answers = [(self.ANSWER, {}, {'value': 'a', 'label': 'A'}), ({'passes': [{'line': '7', 'when': '2026-11-24T10:00:00'}]}, {}, None)]
        got = plugin_fetch.apply_each(self.MAP, answers, ZoneInfo('Europe/Amsterdam'))
        self.assertEqual([(item['line'], item['at']) for item in got['items']],
                         [('7', utc(2026, 11, 24, 9)), ('2', utc(2026, 11, 24, 10, 30)), ('12', utc(2026, 11, 24, 11))])


def entry():
    import plugins as plugin_service
    manifest = {
        'id': 'bus', 'version': '1.0.0', 'api': '0.4', 'icon': 'bus', 'maintainer': 'someone', 'license': 'MIT', 'topics': ['travel'],
        'permissions': {'network': ['api.example.org']}, 'attributes': ['cloud'], 'privacy': 'https://example.org/p',
        'tiles': [{'id': 'next', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900, 'data': 'departures',
                   'options': [{'id': 'stop', 'kind': 'text', 'label': 'stop'}]}],
        'fetch': [{'id': 'departures', 'url': 'https://api.example.org/stops/{stop}', 'every': '60s',
                   'map': {'items': '$.passes[*]', 'fields': {'line': 'line', 'at': {'path': 'when', 'as': 'epoch'}}}}],
    }
    english = {'app': {'name': 'Bus', 'summary': 'Next bus.', 'tile': 'Next', 'stop': 'Stop', 'line': 'Line'}, 'screen': {}}
    return plugin_service.Entry(manifest, {'en': english}, {}, 'index', 'tessera', repo='https://github.com/someone/tessera-bus',
                                path='.', ref='a' * 40)


@unittest.skipUnless(hasattr(time, 'tzset'), 'needs a machine whose zone a process can set')
class TheApp(unittest.IsolatedAsyncioTestCase):
    """The app's own plugin side (plugins.Plugins: tile_message, tile_data, entity_part), with Home Assistant's zone as
    the app keeps it: a zone, the way server.py sets `ha.time_zone`, not a name."""
    TILE = {'entity': 'plugin:bus.next', 'name': '', 'slot': 0, 'options': {'plugin': {'stop': '4711'}}}

    async def test_a_tile_s_fetched_times_are_home_assistant_s(self):
        for zone in MACHINES:
            with self.subTest(machine=zone), machine(zone):
                for home, hour in ((ZoneInfo('Europe/Amsterdam'), 11), (ZoneInfo('Asia/Tokyo'), 3), (timezone.utc, 12), (None, 12)):
                    app = plugin_examples.ExampleApp(entry(), {}, {'departures': {'passes': [{'line': '12', 'when': NOON}]}}, home)
                    shown = await app.tile_message(0, self.TILE)
                    self.assertEqual(shown['x'], {'items': [{'line': '12', 'at': utc(2026, 11, 24, hour)}]}, home)

    async def test_an_entity_s_times_are_home_assistant_s(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        states = {'calendar.waste': {'state': 'on', 'last_updated': '2026-11-24T09:00:00+00:00', 'attributes': {
            'friendly_name': 'Waste', 'start_time': NOON.replace('T', ' '), 'next_date': '2026-11-25', 'end': NOON}}}
        kind = {'id': 'next', 'domains': ['calendar'], 'attributes': ['start_time', 'next_date'],
                'fields': plugin_manifest.check_map({'fields': {'ends': {'path': 'end', 'as': 'epoch'}}}, 'map', False)['fields']}
        for zone in MACHINES:
            with self.subTest(machine=zone), machine(zone):
                ha = type('HA', (), {'states': states, 'time_zone': ZoneInfo('Asia/Tokyo'), 'changed': None, 'dirty': set()})()
                manager = type('Manager', (), {'ha': ha, 'page_senders': {}})()
                service = plugin_service.Plugins(manager, Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
                _, part = service.entity_part(kind, {'options': {'plugin_entity': 'calendar.waste'}})
                self.assertEqual(part['attributes'], {'start_time': utc(2026, 11, 24, 3), 'next_date': utc(2026, 11, 24, 15),
                                                      'ends': utc(2026, 11, 24, 3)})


@unittest.skipUnless(hasattr(time, 'tzset'), 'needs a machine whose zone a process can set')
class AnExample(unittest.IsolatedAsyncioTestCase):
    """A plugin's own example of a tile (plugin_examples.message): its moments are written in the example's zone and
    read back in it, so "in four minutes" is four minutes from now on every machine."""
    NOW = 1795500000
    TILE = {'entity': 'plugin:bus.next', 'name': '', 'slot': 0, 'options': {}}
    PREVIEW = 'tiles:\n  - tile: next\n    options: { stop: "4711" }\nanswers:\n  departures:\n    passes:\n      - { line: "2", when: "{now+4m}" }\n'

    async def test_in_four_minutes_is_in_four_minutes_everywhere(self):
        for zone in MACHINES:
            with self.subTest(machine=zone), machine(zone):
                for written in ('', 'time_zone: Asia/Tokyo\n', 'time_zone: Nowhere/At_All\n'):
                    shown = await plugin_examples.message(entry(), plugin_examples.read(self.PREVIEW + written), 0, self.TILE, now=self.NOW)
                    self.assertEqual(shown['x'], {'items': [{'line': '2', 'at': self.NOW + 240}]}, written)


if __name__ == '__main__':
    unittest.main()
