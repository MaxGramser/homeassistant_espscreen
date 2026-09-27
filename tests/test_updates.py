from manager_fixtures import with_screen_grid, seed_layout
"""Firmware update offers, profile matching and the one-at-a-time update round."""
import asyncio
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import FIRMWARE_VERSION, discover
import firmware
from firmware import Firmware
import updates
from updates import Updater, parse_version

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None


class VersionSourceTests(unittest.TestCase):
    def test_app_target_matches_shipped_firmware(self):
        for name in ('packages/cyd.yaml', 'packages/guition.yaml', 'checkout/cyd.yaml', 'checkout/guition.yaml'):
            text = profiles.text(name)
            self.assertIn(f'SCREEN_FIRMWARE_VERSION: "{FIRMWARE_VERSION}"', text, name)
            self.assertIn('name: "Device name"', text, name)
            self.assertIn('platform: wifi_info', text, name)
        self.assertEqual(parse_version(FIRMWARE_VERSION), tuple(int(p) for p in FIRMWARE_VERSION.split('.')))
        self.assertIsNone(parse_version('unknown'))
        self.assertIsNone(parse_version('1.2'))

    def test_discovery_reports_node_and_address(self):
        registry = [{'entity_id': 'text.screen', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                    {'entity_id': 'text.node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                    {'entity_id': 'text.ip', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd1'},
                    {'entity_id': 'text.fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'}]
        states = {'text.screen': {'state': 'Ready'}, 'text.node': {'state': 'living-room'},
                  'text.ip': {'state': '192.168.1.50'}, 'text.fw': {'state': '0.2.16'}}
        screens, _ = discover(registry, states, [{'id': 'd1', 'name': 'Living room'}], [])
        self.assertEqual(screens[0]['node'], 'living-room')
        self.assertEqual(screens[0]['ip'], '192.168.1.50')
        self.assertEqual(screens[0]['device'], 'Living room')
        states['text.ip']['state'] = 'unavailable'
        states['text.node']['state'] = '../evil'
        screens, _ = discover(registry, states, [{'id': 'd1', 'name': 'Living room'}], [])
        self.assertIsNone(screens[0]['ip'])
        self.assertIsNone(screens[0]['node'])


class ProfileNameTests(unittest.TestCase):
    def test_profiles_are_read_without_resolving_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            (Path(tmp) / 'secrets.yaml').write_text('wifi_ssid: example-net\nwifi_password: example-pw\n')
            f.create({'board': 'cyd', 'name': 'living-room', 'friendly_name': 'Living room'})
            (Path(tmp) / 'manual.yaml').write_text('substitutions:\n  DEVICE_NAME: "kitchen"\n  DEVICE_FRIENDLY_NAME: "Kitchen"\n'
                                                   'esphome:\n  name: ${DEVICE_NAME}\n  friendly_name: ${DEVICE_FRIENDLY_NAME}\n'
                                                   'packages:\n  a: !include other.yaml\napi:\n  encryption:\n    key: !secret api\n')
            (Path(tmp) / 'broken.yaml').write_text('esphome: [\n')
            names = f.profile_names()
            # 'package' (app 0.2.94) is the board package the profile builds from: what the screen looks like.
            # 'rotation' (app 0.2.107) is the angle it was built at, which says which way it hangs; a screen lying
            # down carries no such line, and then the board file's own angle is the answer.
            self.assertEqual(names['living-room.yaml'], {'node': 'living-room', 'friendly': 'Living room', 'screen': True,
                                                         'api_key': names['living-room.yaml']['api_key'],
                                                         'package': 'packages/cyd.yaml', 'rotation': None})
            self.assertEqual(len(names['living-room.yaml']['api_key']), 44)
            # A manual profile (no board package from this repo, key behind !secret) is not an ESP Screens profile.
            self.assertEqual(names['manual.yaml'], {'node': 'kitchen', 'friendly': 'Kitchen', 'screen': False, 'api_key': None,
                                                    'package': None, 'rotation': None})
            self.assertNotIn('broken.yaml', names)
            self.assertNotIn('secrets.yaml', names)

    def test_profiles_are_parsed_only_when_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Firmware(tmp, tmp)
            a, b = Path(tmp) / 'a.yaml', Path(tmp) / 'b.yaml'
            a.write_text('esphome:\n  name: a\n  friendly_name: A\n')
            b.write_text('esphome:\n  name: b\n  friendly_name: B\n')
            parsed = []
            original = firmware.profile_meta
            firmware.profile_meta = lambda text: parsed.append(text) or original(text)
            try:
                self.assertEqual(set(f.profile_names()), {'a.yaml', 'b.yaml'})
                self.assertEqual(len(parsed), 2)
                self.assertEqual(set(f.profile_names()), {'a.yaml', 'b.yaml'})
                self.assertEqual(len(parsed), 2, 'unchanged files must not be parsed again')
                b.write_text('esphome:\n  name: b2\n  friendly_name: B2\n')
                os.utime(b, ns=(b.stat().st_atime_ns, b.stat().st_mtime_ns + 1_000_000))
                names = f.profile_names()
                self.assertEqual(len(parsed), 3, 'only the changed file is parsed')
                self.assertEqual(names['b.yaml'], {'node': 'b2', 'friendly': 'B2', 'screen': False, 'api_key': None,
                                                   'package': None, 'rotation': None})
                a.unlink()
                self.assertEqual(set(f.profile_names()), {'b.yaml'})
                self.assertEqual(len(parsed), 3)
            finally:
                firmware.profile_meta = original


class FakeFirmware:
    """Stands in for the ESPHome CLI: records jobs and flips the screen to the target version."""
    def __init__(self, ha, outcome='success'):
        self.ha, self.outcome, self.calls, self.task, self.job = ha, outcome, [], None, None
        self.names = {'living-room.yaml': {'node': 'living-room', 'friendly': 'Living room'},
                      'kitchen.yaml': {'node': 'kitchen', 'friendly': 'Kitchen'}}

    def profile_names(self): return self.names

    def start(self, data):
        if self.task and not self.task.done(): raise ValueError('A build or install is already running.')
        self.calls.append(data)
        self.job = {'state': 'running', **data}
        self.task = asyncio.create_task(self.run(data))
        return self.job

    async def run(self, data):
        await asyncio.sleep(0)
        if self.outcome == 'success':
            for entity, node in (('text.fw1', 'living-room'), ('text.fw2', 'kitchen')):
                if data['file'] == node + '.yaml': self.ha.states[entity] = {'state': FIRMWARE_VERSION}
        self.job['state'] = self.outcome


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class UpdaterTests(unittest.IsolatedAsyncioTestCase):
    def setup_manager(self, path, outcome='success'):
        from server import Manager
        class HA:
            online = True
            time_zone = timezone.utc
            registry = [{'entity_id': 'text.screen1', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                        {'entity_id': 'text.node1', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                        {'entity_id': 'text.ip1', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd1'},
                        {'entity_id': 'text.fw1', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                        {'entity_id': 'text.screen2', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd2'},
                        {'entity_id': 'text.fw2', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd2'}]
            devices = [{'id': 'd1', 'name': 'Living room'}, {'id': 'd2', 'name': 'Kitchen'}]
            areas = []
            states = {'text.screen1': {'state': 'Ready'}, 'text.node1': {'state': 'living-room'}, 'text.ip1': {'state': '10.0.0.5'},
                      'text.fw1': {'state': '0.2.16'}, 'text.screen2': {'state': 'Ready'}, 'text.fw2': {'state': '0.2.16'}}
            changed = asyncio.Event()
            def __init__(self): self.messages, self.calls = [], []
            async def send(self, inbox, message, action=None): self.messages.append((inbox, message))
            async def request(self, kind, **data): self.calls.append((kind, data))
        manager = Manager(with_screen_grid(HA()), Path(path) / 'screens.json')
        manager.firmware = FakeFirmware(manager.ha, outcome)
        for attr in ('verify_timeout', 'settle_seconds', 'pause_seconds', 'poll_seconds'):
            setattr(manager.updates, attr, 0.01 if attr == 'verify_timeout' else 0)
        return manager

    async def test_offer_matching_and_manual_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            first, second = m.inventory()[0]
            self.assertEqual(m.updates.state_for(first)['profile'], 'living-room.yaml')
            self.assertEqual(m.updates.state_for(first)['host'], '10.0.0.5')
            self.assertTrue(m.updates.state_for(first)['available'])
            # Older firmware: no node name, so the friendly name decides; no address yet.
            self.assertEqual(m.updates.state_for(second)['profile'], 'kitchen.yaml')
            self.assertIsNone(m.updates.state_for(second)['host'])
            self.assertEqual(m.updates.pending(), ['text.screen1'])
            with self.assertRaisesRegex(ValueError, 'IP address'): m.updates.start('text.screen2')
            with self.assertRaises(ValueError): m.updates.start('text.screen2', host='bad host!')
            m.updates.start('text.screen2', host='10.0.0.6')
            await m.updates.task
            self.assertEqual(m.firmware.calls, [{'file': 'kitchen.yaml', 'action': 'install', 'target': '10.0.0.6'}])
            self.assertEqual(m.updates.results['text.screen2']['state'], 'success')
            self.assertEqual(json.loads((Path(tmp) / 'updates.json').read_text())['hosts'], {'text.screen2': '10.0.0.6'})
            with self.assertRaisesRegex(ValueError, 'latest'): m.updates.start('text.screen2')
            m.ha.states['text.fw1'] = {'state': FIRMWARE_VERSION}
            self.assertEqual(m.updates.pending(), [])

    async def test_a_fix_for_one_board_is_offered_to_that_board_alone(self):
        """A board file that went ahead of the shared firmware (app 0.3.21): its screens are offered its version, a screen
        of any other board on the shared version is up to date, and the round waits for the board's version."""
        import core
        ahead = '.'.join(map(str, (*parse_version(FIRMWARE_VERSION)[:2], parse_version(FIRMWARE_VERSION)[2] + 1)))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(core.SHAPES['waveshare4b'], {'firmware': ahead}):
            m = self.setup_manager(tmp)
            m.firmware.names['living-room.yaml']['package'] = 'packages/waveshare4b.yaml'
            # Any board that builds the shared firmware (the CYD went ahead with its own fix in app 0.4.2).
            other = next(b for b in core.BOARD_KEYS if b != 'waveshare4b' and core.SHAPES[b]['firmware'] == FIRMWARE_VERSION)
            m.firmware.names['kitchen.yaml']['package'] = f'packages/{other}.yaml'
            m.updates.hosts['text.screen2'] = '10.0.0.6'
            m.ha.states.update({'text.fw1': {'state': FIRMWARE_VERSION}, 'text.fw2': {'state': FIRMWARE_VERSION}})
            first, second = m.inventory()[0]
            self.assertEqual(m.updates.state_for(first)['target'], ahead)
            self.assertTrue(m.updates.state_for(first)['available'])
            self.assertEqual(m.updates.state_for(second)['target'], FIRMWARE_VERSION)
            self.assertFalse(m.updates.state_for(second)['available'])
            self.assertEqual(m.updates.pending(), ['text.screen1'])
            # What an update flashes decides: the profile's board, over the board a screen reports.
            self.assertEqual(m.updates.target_for({**second, 'board': 'waveshare4b'}), FIRMWARE_VERSION)
            # Without a profile here, the board the screen reports; an unknown board gets the shared version.
            m.firmware.names = {}
            self.assertEqual(m.updates.target_for({**second, 'board': 'waveshare4b'}), ahead)
            self.assertEqual(m.updates.target_for({**second, 'board': 'nothing'}), FIRMWARE_VERSION)
            m.firmware.names = {'living-room.yaml': {'node': 'living-room', 'friendly': 'Living room', 'package': 'packages/waveshare4b.yaml'}}
            # A build that only reaches the shared version is no success for this board.
            m.updates.start('text.screen1')
            await m.updates.task
            self.assertEqual(m.updates.results['text.screen1']['state'], 'failed')
            self.assertIn(ahead, m.updates.results['text.screen1']['message'])
            async def to_board_version(data):
                await asyncio.sleep(0)
                m.ha.states['text.fw1'] = {'state': ahead}
                m.firmware.job['state'] = 'success'
            m.firmware.run = to_board_version
            m.updates.start('text.screen1')
            await m.updates.task
            self.assertEqual(m.updates.results['text.screen1'], {**m.updates.results['text.screen1'], 'state': 'success', 'version': ahead})
            self.assertEqual(m.updates.pending(), [])

    def test_firmware_target_is_never_below_the_shared_version(self):
        import core
        self.assertEqual(core.firmware_target('nothing'), FIRMWARE_VERSION)
        self.assertEqual(core.firmware_target(None), FIRMWARE_VERSION)
        with mock.patch.dict(core.SHAPES['cyd'], {'firmware': '0.0.1'}):
            self.assertEqual(core.firmware_target('cyd'), FIRMWARE_VERSION)
        with mock.patch.dict(core.SHAPES['cyd'], {'firmware': 'broken'}):
            self.assertEqual(core.firmware_target('cyd'), FIRMWARE_VERSION)

    async def test_round_stops_after_failure_and_notifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp, outcome='failed')
            m.updates.hosts['text.screen2'] = '10.0.0.6'
            self.assertEqual(m.updates.start_all(), ['text.screen1', 'text.screen2'])
            with self.assertRaises(ValueError): m.updates.start_all()
            await m.updates.task
            self.assertEqual(len(m.firmware.calls), 1, 'a failed screen must end the round')
            self.assertEqual(m.updates.results['text.screen1']['state'], 'failed')
            self.assertNotIn('text.screen2', m.updates.results)
            self.assertEqual(m.ha.calls, [], 'manual rounds do not notify')
            await m.updates.run_round(['text.screen1'], automatic=True)
            self.assertEqual(m.ha.calls[0][1]['domain'], 'persistent_notification')
            self.assertIn('Living room', m.ha.calls[0][1]['service_data']['message'])

    async def test_screen_that_never_returns_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            m.firmware.outcome = 'success'
            original = m.firmware.run
            async def silent(data):
                await asyncio.sleep(0); m.firmware.job['state'] = 'success'
            m.firmware.run = silent
            m.updates.start('text.screen1')
            await m.updates.task
            self.assertEqual(m.updates.results['text.screen1']['state'], 'failed')
            self.assertIn(FIRMWARE_VERSION, m.updates.results['text.screen1']['message'])
            m.firmware.run = original

    async def test_language_update_is_verified_by_the_screen_language(self):
        """A screen on the current firmware that speaks another language than Settings -> Language & region gets an
        update, and the update counts once its "Screen language" sensor says the new language (app 0.2.90). The cached
        screen list must see that sensor: without it the check waited in vain and every night rebuilt the screen."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            m.ha.registry = m.ha.registry + [{'entity_id': 'sensor.lang1', 'platform': 'esphome', 'original_name': 'Screen language',
                                              'device_id': 'd1'}]
            m.ha.states.update({'text.fw1': {'state': FIRMWARE_VERSION}, 'sensor.lang1': {'state': 'en'}})
            m.ha.ha_language = 'nl'
            first = m.screen('text.screen1')
            self.assertEqual(first['language'], 'en')
            self.assertEqual(m.updates.state_for(first)['language'], True)
            self.assertIn('sensor.lang1', m.watched_entities())
            self.assertEqual(m.updates.pending(), ['text.screen1'])
            async def speaks_dutch(data):
                await asyncio.sleep(0)
                m.ha.states['sensor.lang1'] = {'state': 'nl'}
                m.firmware.job['state'] = 'success'
            m.firmware.run = speaks_dutch
            m.updates.start('text.screen1')
            await m.updates.task
            self.assertEqual(m.updates.results['text.screen1']['state'], 'success')
            self.assertEqual(m.screen('text.screen1')['language'], 'nl')
            self.assertEqual(m.updates.pending(), [])

    async def test_nightly_window_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            night, day = datetime(2026, 9, 14, 3, 30, tzinfo=timezone.utc), datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)
            self.assertFalse(m.updates.due(night))
            m.updates.set_auto(True)
            self.assertTrue(m.updates.due(night))
            self.assertFalse(m.updates.due(day))
            m.updates.last_round = '2026-09-14'
            self.assertFalse(m.updates.due(night))
            self.assertTrue(m.updates.due(datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc)))
            m.updates.save()
            again = self.setup_manager(tmp)
            self.assertTrue(again.updates.auto)
            self.assertEqual(again.updates.last_round, '2026-09-14')
            (Path(tmp) / 'updates.json').write_text('{"version": 9}')
            with self.assertRaises(ValueError): self.setup_manager(tmp)
            with self.assertRaises(ValueError): m.updates.set_auto('yes')

    async def test_manager_watches_only_layout_and_screen_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            seed_layout(m, 'text.screen1', {'title': 'Home', 'tiles': [{'entity': 'light.lamp'}]})
            watched = m.watched_entities()
            self.assertEqual(watched, {'light.lamp', 'text.screen1', 'text.node1', 'text.ip1', 'text.fw1', 'text.screen2', 'text.fw2', 'sensor.test_grid_text_screen1', 'sensor.test_grid_text_screen2'})

    async def test_http_endpoints(self):
        from server import create_app
        from aiohttp.test_utils import TestClient, TestServer
        with tempfile.TemporaryDirectory() as tmp:
            m = self.setup_manager(tmp)
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory')).json()
                self.assertEqual(inventory['updates']['target'], FIRMWARE_VERSION)
                self.assertTrue(inventory['screens'][0]['update']['available'])
                self.assertIn('entities', inventory)
                light = await (await client.get('/api/inventory?light=1')).json()
                async with client.get('/api/events') as stream:
                    self.assertEqual(stream.headers['Content-Type'], 'text/event-stream')
                    line = await asyncio.wait_for(stream.content.readline(), 1)  # first event is immediate
                    pushed = json.loads(line.decode().removeprefix('data: '))
                    self.assertEqual([x['id'] for x in pushed['screens']], [x['id'] for x in light['screens']])
                    self.assertEqual(len(m.listeners), 1)
                for _ in range(50):  # the stream notices the closed client at its next write
                    if not m.listeners: break
                    await asyncio.sleep(0.1)
                self.assertEqual(len(m.listeners), 0)
                self.assertNotIn('entities', light)
                self.assertNotIn('icons', light)
                self.assertEqual([x['id'] for x in light['screens']], [x['id'] for x in inventory['screens']])
                self.assertEqual(light['updates'], inventory['updates'])
                headers = {'X-Screen-CSRF': inventory['csrf']}
                self.assertEqual((await client.put('/api/updates', headers=headers, json={'auto': True})).status, 200)
                self.assertTrue(m.updates.auto)
                response = await client.post('/api/screens/text.screen2/update', headers=headers, json={})
                self.assertEqual(response.status, 400)
                response = await client.post('/api/screens/text.screen1/update', headers=headers, json={})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['state'], 'running')
                await m.updates.task
                self.assertEqual(m.updates.results['text.screen1']['state'], 'success')


if __name__ == '__main__': unittest.main()
