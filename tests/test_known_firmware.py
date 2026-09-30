"""The firmware a screen's features go by, and what the editor may offer it (app 0.2.78).

A screen whose "Screen firmware" sensor had no version (offline, restarting) counted as firmware 0.0.0: a save of more
than ten tiles or of a newer kind of tile was refused, and the editor capped the screen at ten tiles. Home Assistant's
device registry keeps the version ESPHome reported, "<project version> (ESPHome <version>)" for our firmware, and the app
now falls back to that. Only a plain X.Y.Z counts, as before: "0.2.65-dev" is no release.

Each screen in the inventory says what that means for the editor: `firmware_known`, `tile_limit`, `full_page` and
`page_tiles_repeat` (the contract with web/src/store.ts).
"""
from manager_fixtures import with_screen_grid
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import camera_feed  # noqa: E402
from core import (alert_targets, discover_screens, firmware_features, known_firmware, parse_firmware, registry_firmware,  # noqa: E402
                  screen_firmware, tile_limit)
import updates  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import test_scaling
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app

REGISTRY = '0.2.63 (ESPHome 2026.6.2)'


class Versions(unittest.TestCase):
    def test_only_a_plain_version_counts(self):
        self.assertEqual(parse_firmware('0.2.63'), (0, 2, 63))
        self.assertEqual(parse_firmware('1.10.0'), (1, 10, 0))
        for text in ('0.2.65-dev', '0.2', '0.2.63.1', ' 0.2.63', '0.2.+63', REGISTRY, 'unknown', 'unavailable', '', None, 63):
            self.assertIsNone(parse_firmware(text), text)
        self.assertIs(updates.parse_version, parse_firmware, 'update offers follow the same strict rule')

    def test_the_registry_version_of_our_firmware(self):
        self.assertEqual(registry_firmware(REGISTRY), '0.2.63')
        # Firmware without `esphome: project:` has ESPHome's own version there, which is no screen firmware.
        for text in ('2026.6.2 (Sep 17 2026, 10:00:00)', '2026.6.2', '0.2.65-dev (ESPHome 2026.6.2)', 'v0.2.63 (ESPHome 2026.6.2)', '', None):
            self.assertIsNone(registry_firmware(text), text)
        self.assertEqual(known_firmware('0.2.64', REGISTRY), '0.2.64', 'the sensor comes first')
        for sensor in ('unavailable', 'unknown', '0.2.65-dev', None):
            self.assertEqual(known_firmware(sensor, REGISTRY), '0.2.63', sensor)
        self.assertIsNone(known_firmware('unavailable', None))

    def test_what_a_firmware_may_be_offered(self):
        self.assertEqual([tile_limit(v) for v in (None, (0, 2, 6), (0, 2, 7), (0, 2, 61), (0, 2, 62), (0, 3, 0))], [10, 10, 20, 20, 48, 48])
        self.assertEqual(firmware_features((0, 2, 64)), {'tile_limit': 48, 'page_limit': 8, 'full_page': True, 'page_tiles_repeat': False, 'entity_tiles_repeat': False, 'no_title': False})
        self.assertEqual(firmware_features((0, 2, 65)), {'tile_limit': 48, 'page_limit': 8, 'full_page': True, 'page_tiles_repeat': True, 'entity_tiles_repeat': False, 'no_title': False})
        self.assertEqual(firmware_features((0, 16, 0)), {'tile_limit': 48, 'page_limit': 8, 'full_page': True, 'page_tiles_repeat': True, 'entity_tiles_repeat': True, 'no_title': False})
        self.assertEqual(firmware_features((0, 17, 0)), {'tile_limit': 48, 'page_limit': 8, 'full_page': True, 'page_tiles_repeat': True, 'entity_tiles_repeat': True, 'no_title': True})
        self.assertEqual(firmware_features(None), {'tile_limit': 10, 'page_limit': 8, 'full_page': False, 'page_tiles_repeat': False, 'entity_tiles_repeat': False, 'no_title': False})

    def test_discovery_falls_back_to_the_registry(self):
        registry = [{'entity_id': 'text.hall_tile_settings', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                    {'entity_id': 'sensor.hall_screen_firmware', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'}]
        devices = [{'id': 'd1', 'name': 'Hall', 'sw_version': REGISTRY}]
        for sensor, known in (('0.2.64', '0.2.64'), ('unavailable', '0.2.63'), ('0.2.65-dev', '0.2.63')):
            screen, = discover_screens(registry, {'sensor.hall_screen_firmware': {'state': sensor}}, devices, [])
            self.assertEqual((screen['firmware'], screen['firmware_known']), (sensor, known))
            self.assertEqual(screen_firmware(screen), parse_firmware(known))
        screen, = discover_screens(registry, {}, [{'id': 'd1', 'name': 'Hall'}], [])
        self.assertEqual((screen['firmware'], screen['firmware_known'], screen_firmware(screen)), ('unknown', None, None))

    def test_alerts_and_camera_images_go_by_the_same_version(self):
        restarting = {'id': 'text.hall', 'name': 'Hall', 'node': 'hall', 'online': True, 'board': 'guition',
                      'firmware': 'unknown', 'firmware_known': '0.2.63'}
        self.assertEqual(alert_targets([restarting]), ([restarting], []))
        self.assertTrue(camera_feed.can_show(restarting))
        unknown = {**restarting, 'firmware_known': None}
        self.assertEqual(alert_targets([unknown])[1], [(unknown, 'firmware unknown')])
        self.assertFalse(camera_feed.can_show(unknown))


def tiles(count, prefix='light.l'):
    return [{'entity': f'{prefix}{i}', 'name': ''} for i in range(count)]


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Saving(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, sensor, sw_version=None, online=True):
        ha = test_scaling.fake_ha(firmware=sensor)
        for tile in tiles(30):
            ha.registry.append({'entity_id': tile['entity'], 'platform': 'hue'})
            ha.states[tile['entity']] = {'state': 'on', 'attributes': {}}
        if sw_version:
            ha.devices[0]['sw_version'] = sw_version
        if not online:
            ha.states['text.screen']['state'] = 'unavailable'
        return Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')

    async def test_an_offline_screen_keeps_its_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, 'unavailable', REGISTRY, online=False)
            m.save('text.screen', {'title': 'Hall', 'tiles': tiles(30)})
            self.assertEqual(len(m.layouts['text.screen']['tiles']), 30)
            self.assertEqual(m.status['text.screen'], 'Saved; waiting for sync')
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, 'unavailable', online=False)
            with self.assertRaisesRegex(ValueError, 'Install screen firmware 0.2.62 or newer first'):
                m.save('text.screen', {'title': 'Hall', 'tiles': tiles(30)})

    async def test_a_development_version_is_no_release(self):
        back = [{'entity': 'screen.page_1', 'name': '', 'slot': 6}, {'entity': 'screen.page_1', 'name': '', 'slot': 12}]
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.2.65-dev')
            with self.assertRaisesRegex(ValueError, 'Install screen firmware 0.2.65 or newer first'):
                m.save('text.screen', {'title': 'Hall', 'tiles': back})
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, 'unknown', '0.2.65 (ESPHome 2026.6.2)')
            m.save('text.screen', {'title': 'Hall', 'tiles': back})
            self.assertEqual([t['slot'] for t in m.layouts['text.screen']['tiles']], [6, 12])

    async def test_every_screen_in_the_inventory_says_what_the_editor_may_offer(self):
        cases = (('0.2.6', None, '0.2.6', 10, False, False), ('0.2.7', None, '0.2.7', 20, False, False),
                 ('0.2.62', None, '0.2.62', 48, True, False), ('0.2.65', None, '0.2.65', 48, True, True),
                 ('unavailable', REGISTRY, '0.2.63', 48, True, False), ('0.2.65-dev', None, None, 10, False, False))
        for sensor, sw_version, known, limit, full, repeat in cases:
            with tempfile.TemporaryDirectory() as tmp:
                m = self.manager(tmp, sensor, sw_version)
                async with TestClient(TestServer(create_app(m, True))) as client:
                    for path in ('/api/inventory', '/api/inventory?light=1'):
                        screen, = (await (await client.get(path)).json())['screens']
                        self.assertEqual((screen['firmware'], screen['firmware_known'], screen['tile_limit'], screen['full_page'],
                                          screen['page_tiles_repeat']), (sensor, known, limit, full, repeat), (path, sensor))


if __name__ == '__main__':
    unittest.main()
