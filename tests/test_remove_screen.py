from manager_fixtures import with_screen_grid
"""Removing a screen for good (app 0.2.112): the mirror of New screen.

The editor's list is Home Assistant's, so a screen only leaves it when its ESPHome integration goes. One request
removes that integration, the screen's own YAML with what it built, and everything this app kept for it. Home
Assistant goes first: while it refuses, nothing here is lost.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from firmware import Firmware  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, Refused, create_app
    from test_screen_owned_settings import fake_ha

INBOX = 'text.screen'
LAYOUT = {'title': 'Office', 'tiles': [{'entity': 'light.a', 'name': 'Lamp', 'slot': 0}]}


def with_entries(ha, entry='e1', refuse=None):
    """The Home Assistant side of a removal: its ESPHome integrations and what a Delete does to them."""
    ha.devices = [{'id': 'd1', 'name': 'Office 1', 'config_entries': [entry]}]
    ha.entries = {'e1': {'entry_id': 'e1', 'domain': 'esphome', 'title': 'Office 1'}}
    ha.deleted, ha.states_removed, ha.registries_read = [], [], 0

    async def esphome_entries():
        return ha.entries

    async def delete_config_entry(entry_id):
        if refuse:
            raise refuse
        ha.deleted.append(entry_id)
        # Home Assistant drops the device with its entities.
        ha.registry = [item for item in ha.registry if item.get('device_id') != 'd1']
        ha.devices = []
        return False

    async def remove_state(entity_id):
        ha.states_removed.append(entity_id)
        return True

    async def registries():
        ha.registries_read += 1

    ha.esphome_entries, ha.delete_config_entry = esphome_entries, delete_config_entry
    ha.remove_state, ha.registries = remove_state, registries
    return ha


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class RemoveScreenTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, stored=None, updates=None, ha=None):
        if stored is not None:
            (Path(tmp) / 'screens.json').write_text(json.dumps({'version': 1, 'screens': stored}))
        if updates is not None:
            (Path(tmp) / 'updates.json').write_text(json.dumps({'version': 1, 'auto': False, **updates}))
        manager = Manager(with_screen_grid(with_entries(ha or fake_ha())), Path(tmp) / 'screens.json')
        manager.firmware = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
        return manager

    def profile(self, manager, node='office-1'):
        """A screen this app installed itself: its YAML, its sidecar and a build folder from a build."""
        manager.firmware.create({'board': 'guition', 'name': node, 'friendly_name': 'Office 1',
                                 'wifi_ssid': 'ssid', 'wifi_password': 'password'})
        build = manager.firmware.data / 'build' / node
        build.mkdir(parents=True)
        (build / 'firmware.bin').write_bytes(b'0')
        return build

    async def test_a_screen_this_app_installed_goes_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT}, {'hosts': {INBOX: '10.0.0.5'},
                                                          'results': {INBOX: {'state': 'success', 'message': 'Updated.'}}})
            build = self.profile(manager)
            self.assertEqual([screen['id'] for screen in manager.screens()], [INBOX])
            answer = await manager.remove_screen(INBOX)
            self.assertEqual((answer['removed'], answer['name'], answer['profile'], answer['kept']),
                             (True, 'Office 1', 'office-1.yaml', []))
            # Out of Home Assistant, and the layout sensor this app published with it.
            self.assertEqual(manager.ha.deleted, ['e1'])
            self.assertEqual(manager.ha.states_removed, ['sensor.esp_screens_office_1'])
            self.assertEqual(manager.screens(), [])
            # Out of the ESPHome folder: the profile, its sidecar and what it built.
            self.assertEqual(manager.firmware.profiles(), [])
            self.assertFalse((manager.firmware.root / 'office-1.local.yaml').exists())
            self.assertFalse(build.exists())
            # Out of this app: the layout and the update history, on disk as well.
            self.assertEqual(manager.layouts, {})
            self.assertEqual(json.loads((Path(tmp) / 'screens.json').read_text())['screens'], {})
            self.assertEqual((manager.updates.hosts, manager.updates.results), ({}, {}))
            self.assertEqual(json.loads((Path(tmp) / 'updates.json').read_text())['hosts'], {})

    async def test_the_layout_sensor_of_an_offline_screen_goes_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            # Offline: the screen's own "Device name" sensor says nothing, so its node is unknown. The layout
            # sensor this app published carries the screen's name, which finds it anyway.
            manager.ha.states['sensor.node'] = {'state': 'unavailable'}
            manager.ha.states['sensor.esp_screens_office_1'] = {'state': '1', 'attributes': {'friendly_name': 'Office 1 tiles'}}
            manager.ha.states['sensor.esp_screens_kitchen'] = {'state': '3', 'attributes': {'friendly_name': 'Kitchen tiles'}}
            await manager.remove_screen(INBOX)
            self.assertEqual(manager.ha.states_removed, ['sensor.esp_screens_office_1'])

    async def test_a_screen_from_elsewhere_keeps_the_esphome_folder_as_it_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            manager.firmware.create({'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen',
                                     'wifi_ssid': 'ssid', 'wifi_password': 'password'})
            answer = await manager.remove_screen(INBOX)
            self.assertEqual((answer['profile'], answer['kept']), (None, []))
            self.assertEqual(manager.firmware.profiles(), [{'file': 'kitchen.yaml'}], "another screen's profile stays")
            self.assertEqual(manager.layouts, {})

    async def test_home_assistant_refusing_leaves_everything_where_it_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT}, ha=fake_ha())
            with_entries(manager.ha, refuse=Refused('not allowed'))
            self.profile(manager)
            with self.assertRaises(Refused):
                await manager.remove_screen(INBOX)
            self.assertEqual([screen['id'] for screen in manager.screens()], [INBOX])
            self.assertEqual(manager.layouts, {INBOX: manager.layouts[INBOX]})
            self.assertEqual(manager.firmware.profiles(), [{'file': 'office-1.yaml'}])

    async def test_a_profile_that_cannot_go_is_named_in_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            self.profile(manager)

            async def refuse(name):
                raise OSError('read-only folder')
            manager.firmware.delete_profile = refuse
            answer = await manager.remove_screen(INBOX)
            # Home Assistant already let the screen go, so the rest goes too; the page says what stayed.
            self.assertEqual((answer['removed'], answer['profile'], answer['kept']), (True, None, ['office-1.yaml']))
            self.assertEqual(manager.ha.deleted, ['e1'])
            self.assertEqual(manager.layouts, {})

    async def test_a_screen_that_is_not_an_esphome_device_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            manager.ha.entries = {}
            with self.assertRaises(ValueError):
                await manager.remove_screen(INBOX)
            self.assertEqual(manager.layouts[INBOX]['tiles'], LAYOUT['tiles'])
            self.assertEqual(manager.layouts[INBOX]['title'], LAYOUT['title'])

    async def test_it_waits_for_a_build_of_the_screen_that_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            gate = asyncio.Event()

            async def held(build):
                await gate.wait()
                return 'success'
            manager.build_queue.add('update', None, held, screen=INBOX)
            try:
                with self.assertRaises(ValueError):
                    await manager.remove_screen(INBOX)
            finally:
                gate.set()
                await manager.build_queue.idle()
            self.assertEqual(manager.ha.deleted, [])
            self.assertEqual(manager.layouts[INBOX]['tiles'], LAYOUT['tiles'])
            self.assertEqual(manager.layouts[INBOX]['title'], LAYOUT['title'])

    async def test_another_screen_s_build_does_not_keep_it_and_its_own_waiting_build_goes_with_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            gate = asyncio.Event()

            async def held(build):
                await gate.wait()
                return 'success'
            manager.build_queue.add('update', 'other.yaml', held, screen='text.other')
            waiting = manager.build_queue.add('update', None, held, screen=INBOX)
            try:
                await manager.remove_screen(INBOX)
            finally:
                gate.set()
                await manager.build_queue.idle()
            self.assertEqual(waiting.state, 'skipped')
            self.assertNotIn(INBOX, manager.layouts)

    async def test_the_page_removes_a_screen_over_its_own_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            async with TestClient(TestServer(create_app(manager, True))) as client:
                first = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual([screen['id'] for screen in first['screens']], [INBOX])
                # A page without the token cannot remove a screen.
                refused = await client.delete(f'/api/screens/{INBOX}')
                self.assertEqual(refused.status, 403)
                self.assertEqual(manager.ha.deleted, [])
                answer = await client.delete(f'/api/screens/{INBOX}', headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(answer.status, 200)
                self.assertEqual((await answer.json())['name'], 'Office 1')
                after = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(after['screens'], [])

    async def test_a_screen_that_never_got_its_firmware_can_be_removed_and_a_paired_one_cannot_this_way(self):
        # GitHub #114: New screen wrote a profile, the build was cancelled, and the sidebar kept it waiting.
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            self.profile(manager)   # Office 1, paired
            manager.firmware.create({'board': 'cyd', 'name': 'kitchen-2', 'friendly_name': 'Kitchen 2',
                                     'wifi_ssid': 'ssid', 'wifi_password': 'password'})
            async with TestClient(TestServer(create_app(manager, True))) as client:
                first = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual([p['file'] for p in first['pending']], ['kitchen-2.yaml'])
                headers = {'X-Screen-CSRF': first['csrf']}
                paired = await client.delete('/api/firmware/profiles/office-1.yaml', headers=headers)
                self.assertEqual(paired.status, 400)
                self.assertTrue((manager.firmware.root / 'office-1.yaml').is_file())
                answer = await client.delete('/api/firmware/profiles/kitchen-2.yaml', headers=headers)
                self.assertEqual(answer.status, 200)
                self.assertFalse((manager.firmware.root / 'kitchen-2.yaml').exists())
                after = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(after['pending'], [])

    async def test_nothing_waits_before_home_assistant_answered_once(self):
        # Right after a start (an update of the app), no paired screen is known yet: its profile must not look like one
        # that never got its firmware, or its Remove would take a working screen's YAML and keys.
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, {INBOX: LAYOUT})
            self.profile(manager)   # Office 1, paired
            registry, manager.ha.registry, manager.ha.online = manager.ha.registry, [], False
            async with TestClient(TestServer(create_app(manager, True))) as client:
                first = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(first['pending'], [])
                answer = await client.delete('/api/firmware/profiles/office-1.yaml', headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(answer.status, 400)
                self.assertTrue((manager.firmware.root / 'office-1.yaml').is_file())
                # Home Assistant answers: the paired screen is known, and still nothing waits.
                manager.ha.registry, manager.ha.online = registry, True
                after = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(after['pending'], [])


if __name__ == '__main__':
    unittest.main()
