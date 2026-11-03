"""A board Home Assistant already has, flashed again under a new name (app 0.4.96, server.py known_board).

Home Assistant keeps one ESPHome device per board, keyed on its MAC: a board flashed with a new profile cannot be added
while its old device is there (the discovery aborts with already_configured, and Home Assistant then asks the old
device's key of the new firmware for ever). New screen asks the add-on, with the MAC esptool read from the chip, whether
the board is known and as what, and offers to install that screen again or to replace it: after the image is on the
board, the old device's integration leaves Home Assistant and the new screen pairs.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from firmware import Firmware
    from manager_fixtures import with_screen_grid
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha

MAC = 'aa:bb:cc:dd:ee:ff'


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp is not installed')
class AKnownBoard(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp):
        (Path(tmp) / 'screens.json').write_text(json.dumps({'version': 1, 'screens': {}}))
        ha = with_screen_grid(fake_ha())
        # The board's camera on a device of its own with the same MAC, listed first and once renamed by hand (a reTerminal
        # D1001, 2026-11-03): the screen's device names the board, the camera's integration goes with it.
        ha.devices = [{'id': 'd-cam', 'name': 'Living room camera', 'name_by_user': 'tablet', 'config_entries': ['E-other'],
                       'connections': [['mac', MAC]]},
                      {'id': 'd-old', 'name': 'Living room', 'name_by_user': None, 'config_entries': ['E1', 'E-other'],
                       'connections': [['mac', MAC.upper()]]},
                      {'id': 'd-lamp', 'name': 'Lamp', 'config_entries': ['E2'], 'connections': [['mac', '11:22:33:44:55:66']]}]
        self.deleted = []

        async def esphome_entries():
            return {'E1': {'entry_id': 'E1', 'domain': 'esphome', 'title': 'Living room', 'state': 'loaded'}}

        async def delete_config_entry(entry_id):
            self.deleted.append(entry_id)
            return False
        self.refreshed = 0

        async def registries():
            # Home Assistant's registry as it is now: the device's list of integrations may be behind in the app.
            self.refreshed += 1
            ha.devices[1]['config_entries'] = ['E-other']
            ha.registry = [{'entity_id': 'text.living_room_tile_settings', 'device_id': 'd-old', 'config_entry_id': 'E1'}]
        ha.esphome_entries, ha.delete_config_entry, ha.registries = esphome_entries, delete_config_entry, registries
        manager = Manager(ha, Path(tmp) / 'screens.json')
        manager.firmware = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
        manager.firmware.create({'board': 'cyd', 'name': 'hall-2', 'friendly_name': 'Hall 2',
                                 'wifi_ssid': 'ssid', 'wifi_password': 'password'})
        return manager

    def test_the_board_is_found_by_its_mac_whatever_the_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            known = manager.known_board(MAC)
            # No screen of the app's has these devices (the fake's screens are others), so the first device names it,
            # and the entries of both devices with the MAC are known.
            self.assertEqual((known['known'], known['name'], known['device_ids'], known['entries']),
                             (True, 'tablet', ['d-cam', 'd-old'], ['E-other', 'E1']))
            self.assertEqual(manager.known_board(MAC.upper())['name'], 'tablet')
            self.assertIsNone(manager.known_board('11:22:33:44:55:67'))
            # Nothing that is not a MAC is looked up: the page sends what esptool read, nothing else.
            self.assertIsNone(manager.known_board('../etc/passwd'))
            self.assertIsNone(manager.known_board(None))

    async def test_the_page_asks_and_replaces_through_the_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            async with TestClient(TestServer(create_app(manager, True))) as client:
                first = await (await client.get('/api/inventory?light=1')).json()
                known = await (await client.get(f'/api/boards/known?mac={MAC}')).json()
                self.assertEqual((known['known'], known['name']), (True, 'tablet'))
                self.assertEqual(await (await client.get('/api/boards/known?mac=11:22:33:44:55:67')).json(), {'known': False})
                # Replacing takes the old device's ESPHome integration out, and only that one (E-other is another
                # integration of the device, a camera's say), once the new profile is one this app wrote.
                refused = await client.post('/api/boards/replace', json={'mac': MAC, 'by': 'stranger.yaml'},
                                            headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(refused.status, 400)
                self.assertEqual(self.deleted, [])
                answer = await client.post('/api/boards/replace', json={'mac': MAC, 'by': 'hall-2.yaml'},
                                           headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(answer.status, 200)
                self.assertEqual(await answer.json(), {'replaced': 'tablet', 'by': 'hall-2.yaml', 'entries': 1})
                # Found through the device's entities after the registry was read again (the device's own list of
                # integrations was behind): the stale list found nothing to remove on 2026-11-03.
                self.assertEqual(self.deleted, ['E1'])
                self.assertGreaterEqual(self.refreshed, 2)  # once for the question, once for the replacing
                # A board that is a screen of this app's goes the way its own Remove takes it: out of Home Assistant,
                # its YAML out of the ESPHome folder, everything the app kept (app 0.4.97; a profile left behind showed
                # as a screen still waiting for its firmware).
                removed = []

                async def remove_screen(inbox):
                    removed.append(inbox)
                    return {'removed': True, 'name': 'Living room', 'profile': 'living-room.yaml', 'kept': []}
                manager.remove_screen = remove_screen
                manager.screens = lambda: [{'id': 'inbox-old', 'device_id': 'd-old', 'name': 'Living room', 'node': 'living-room'}]
                answer = await client.post('/api/boards/replace', json={'mac': MAC, 'by': 'hall-2.yaml'},
                                           headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(answer.status, 200)
                self.assertEqual(await answer.json(), {'replaced': 'Living room', 'by': 'hall-2.yaml', 'entries': 1, 'profile': 'living-room.yaml'})
                self.assertEqual((removed, self.deleted), (['inbox-old'], ['E1']))
                manager.screens = lambda: []
                # A board Home Assistant does not have cannot be replaced.
                missing = await client.post('/api/boards/replace', json={'mac': '11:22:33:44:55:67', 'by': 'hall-2.yaml'},
                                            headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(missing.status, 400)


if __name__ == '__main__':
    unittest.main()
