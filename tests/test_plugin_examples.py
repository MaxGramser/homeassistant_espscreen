"""A plugin's own example of its tiles, for the editor's library (screen_manager/app/plugin_examples.py,
docs/EMULATOR_ARCHITECTURE.md "The page editor's own cards"): a tile that is on no page yet is shown with the plugin's
preview.yaml, through the app's own shaping, and never through a web service or Home Assistant."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import plugin_examples  # noqa: E402

NOW = 1795500000
ENGLISH = {'app': {'name': 'Bus', 'summary': 'Next bus.', 'tile': 'Next', 'stop': 'Stop', 'line': 'Line', 'walk': 'Walk'},
           'screen': {'now': 'now'}}
MANIFEST = {
    'id': 'bus', 'version': '1.0.0', 'api': '0.4', 'icon': 'bus', 'maintainer': 'someone', 'license': 'MIT', 'topics': ['travel'],
    'permissions': {'network': ['api.example.org']}, 'attributes': ['cloud'], 'privacy': 'https://example.org/p',
    'tiles': [{'id': 'next', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900, 'data': 'departures',
               'options': [{'id': 'stop', 'kind': 'text', 'label': 'stop'},
                           {'id': 'walk', 'kind': 'number', 'min': 0, 'max': 20, 'default': 3, 'label': 'walk'}]}],
    'fetch': [{'id': 'departures', 'url': 'https://api.example.org/stops/{stop}', 'every': '60s',
               'map': {'items': '$.{stop}.passes[*]', 'fields': {'line': 'line', 'at': {'path': 'when', 'as': 'epoch'}},
                       'sort': 'at', 'limit': 2}}],
}
# What a maker writes for the bench (the plugins repository's docs/PREVIEW.md): the web service's own answer, with
# moments from now.
PREVIEW = '''
tiles:
  - tile: next
    name: Central Station
    options: { stop: "4711", walk: 5 }
  - tile: next
    name: No departures
    options: { stop: "4711" }
    sizes: [1x1]
    answers: { departures: { "4711": { passes: [] } } }
  - tile: next
    name: Asking
    sizes: [2x2]
    data: { wait: asking }
answers:
  departures:
    "4711":
      passes:
        - { line: "12", when: "{now+7m}" }
        - { line: "2", when: "{now+4m}" }
        - { line: "28", when: "{now+11m}" }
time_zone: Europe/Amsterdam
'''
TILE = {'entity': 'plugin:bus.next', 'name': '', 'slot': 0, 'options': {'size': 'wide'}}


def entry(folder=None):
    import plugins as plugin_service
    return plugin_service.Entry(dict(MANIFEST), {'en': ENGLISH}, {}, 'folder' if folder else 'index', 'tessera',
                                repo='https://github.com/someone/tessera-bus', path='.', ref='a' * 40, folder=folder)


class Moments(unittest.TestCase):
    def test_a_moment_is_written_from_now(self):
        local = datetime.fromtimestamp(NOW + 240, ZoneInfo('Europe/Amsterdam')).strftime('%Y-%m-%dT%H:%M:%S')
        self.assertEqual(plugin_examples.moments('{now+4m}', 'Europe/Amsterdam', NOW), local)
        self.assertEqual(plugin_examples.moments('{epoch-2h}', 'Europe/Amsterdam', NOW), NOW - 7200)
        self.assertEqual(plugin_examples.moments('at {epoch+1d}', 'Europe/Amsterdam', NOW), f'at {NOW + 86400}')
        self.assertEqual(plugin_examples.moments({'a': ['{epoch}', 3, None]}, 'Europe/Amsterdam', NOW), {'a': [NOW, 3, None]})


class Reading(unittest.TestCase):
    def test_what_is_no_preview_yaml_is_none(self):
        for text in ('- a list', 'tiles: [unclosed', 'x' * (plugin_examples.MAX_BYTES + 1), None):
            self.assertIsNone(plugin_examples.read(text))
        self.assertEqual(plugin_examples.read(PREVIEW)['tiles'][0]['name'], 'Central Station')

    def test_the_example_of_a_tile_is_the_one_shown_at_its_size_else_the_first(self):
        spec = plugin_examples.read(PREVIEW)
        self.assertEqual(plugin_examples.example_of(spec, 'next')['name'], 'Central Station')
        self.assertEqual(plugin_examples.example_of(spec, 'next', '2x1')['name'], 'Central Station')
        self.assertIsNone(plugin_examples.example_of(spec, 'lines'))
        only = {'tiles': [{'tile': 'next', 'name': 'Small', 'sizes': ['1x1']}, {'tile': 'next', 'name': 'Large', 'sizes': ['2x2']}]}
        self.assertEqual(plugin_examples.example_of(only, 'next', '2x2')['name'], 'Large')
        self.assertEqual(plugin_examples.example_of(only, 'next', '3x1')['name'], 'Small')


class Message(unittest.IsolatedAsyncioTestCase):
    async def test_the_example_goes_through_the_app_s_own_shaping(self):
        """Its options as the screen gets them (the manifest's defaults filled in), its answer through the fetch's map
        (sorted, limited, a moment as seconds since 1970), and the name its maker gave it."""
        shown = await plugin_examples.message(entry(), plugin_examples.read(PREVIEW), 3, TILE, '2x1', now=NOW)
        self.assertEqual((shown['i'], shown['entity'], shown['state']), (3, 'plugin:bus.next', 'ok'))
        self.assertEqual(shown['name'], 'Central Station')
        self.assertEqual(shown['o']['plugin'], {'stop': '4711', 'walk': 5})
        self.assertEqual(shown['o']['size'], 'wide')
        self.assertEqual(shown['x'], {'items': [{'line': '2', 'at': NOW + 240}, {'line': '12', 'at': NOW + 420}]})
        self.assertLess(len(json.dumps(shown)), 4096)

    async def test_asked_again_within_a_minute_an_example_is_the_same_message(self):
        """Its moments are written from the start of the minute, so a refresh brings no change the screen would draw."""
        spec = plugin_examples.read(PREVIEW)
        first = await plugin_examples.message(entry(), spec, 0, TILE)
        again = await plugin_examples.message(entry(), spec, 0, TILE)
        if first != again:   # the minute turned between the two: the next two are within one
            first, again = again, await plugin_examples.message(entry(), spec, 0, TILE)
        self.assertEqual(first, again)
        self.assertEqual(first['x']['items'][0]['at'] % 60, 0)

    async def test_a_tile_s_own_name_stays(self):
        shown = await plugin_examples.message(entry(), plugin_examples.read(PREVIEW), 0, {**TILE, 'name': 'Work'}, now=NOW)
        self.assertEqual(shown['name'], 'Work')

    async def test_an_example_s_own_answer_and_its_data_as_it_is(self):
        # An example without `sizes` is shown at every size, so it comes first wherever it stands first; here the first
        # one is kept to its row of two, and the others show at their own sizes.
        spec = plugin_examples.read(PREVIEW)
        spec['tiles'][0]['sizes'] = ['2x1']
        self.assertEqual((await plugin_examples.message(entry(), spec, 0, TILE, '2x1', now=NOW))['name'], 'Central Station')
        # The example of 1 x 1 answers with an empty stop: its own answer goes over the plugin's.
        empty = await plugin_examples.message(entry(), spec, 0, {**TILE, 'options': {}}, '1x1', now=NOW)
        self.assertEqual((empty['name'], empty['x']), ('No departures', {'items': []}))
        # `data` is what the screen gets, past the map: a state the map cannot reach.
        waiting = await plugin_examples.message(entry(), spec, 0, {**TILE, 'options': {'size': 'square'}}, '2x2', now=NOW)
        self.assertEqual(waiting['x'], {'wait': 'asking'})

    async def test_a_plugin_that_shows_no_example_of_a_tile_has_none(self):
        self.assertIsNone(await plugin_examples.message(entry(), {'tiles': [{'tile': 'other'}]}, 0, TILE, now=NOW))
        self.assertIsNone(await plugin_examples.message(entry(), {'tiles': []}, 0, {**TILE, 'entity': 'plugin:bus.lines'}, now=NOW))


class FromThePlugin(unittest.IsolatedAsyncioTestCase):
    def service(self, preview):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'bus').mkdir()
        if preview is not None:
            (root / 'bus' / 'preview.yaml').write_text(preview)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), root / 'data', root / 'esphome')
        service.folders['bus'] = entry(str(root / 'bus'))
        return service, root

    async def test_a_folder_s_preview_yaml_is_read_and_read_again_when_it_changes(self):
        service, root = self.service(PREVIEW)
        shown = await service.example_message(1, TILE, '2x1')
        self.assertEqual((shown['name'], len(shown['x']['items'])), ('Central Station', 2))
        import os
        (root / 'bus' / 'preview.yaml').write_text(PREVIEW.replace('Central Station', 'Harbour'))
        os.utime(root / 'bus' / 'preview.yaml', ns=(10 ** 18, 10 ** 18))
        self.assertEqual((await service.example_message(1, TILE, '2x1'))['name'], 'Harbour')

    async def test_a_plugin_without_an_example_or_with_a_broken_one_is_never_an_error(self):
        for preview in (None, 'tiles: [unclosed', 'tiles:\n  - tile: next\n    options: 7\n', 'answers: 3\ntiles:\n  - tile: next\n'):
            service, _ = self.service(preview)
            with self.subTest(preview):
                shown = await service.example_message(0, TILE)
                # None, or a message the screen takes: never an exception that would take the whole preview with it.
                self.assertTrue(shown is None or shown['entity'] == 'plugin:bus.next')
        service, _ = self.service(PREVIEW)
        self.assertIsNone(await service.example_message(0, {**TILE, 'entity': 'plugin:tram.next'}))


if __name__ == '__main__':
    unittest.main()
