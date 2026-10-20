"""The manual firmware workspace reuses the paired-screen updater's target, without guessing."""
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from test_screen_owned_settings import fake_ha, Manager, with_screen_grid
from server import create_app


class FirmwareAddresses(unittest.IsolatedAsyncioTestCase):
    def manager(self, directory):
        ha = fake_ha()
        ha.registry.append({'entity_id': 'sensor.ip', 'platform': 'esphome',
                            'original_name': 'IP address', 'device_id': 'd1'})
        ha.states['sensor.ip'] = {'state': '192.0.2.10'}
        m = Manager(with_screen_grid(ha), Path(directory) / 'screens.json')
        m.firmware.root = Path(directory) / "esphome"
        m.firmware.root.mkdir(parents=True, exist_ok=True)
        for file, node in [('office.yaml', 'office-1'), ('spare.yaml', 'spare')]:
            (m.firmware.root / file).write_text(f'esphome:\n  name: {node}\n')
        return m

    async def test_known_address_tracks_the_selected_profile_and_falls_back_to_saved_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.updates.hosts['text.screen'] = 'office.example.test'
            async with TestClient(TestServer(create_app(m, True))) as client:
                async def profiles():
                    response = await client.get('/api/firmware')
                    self.assertEqual(response.status, 200)
                    return {p['file']: p for p in (await response.json())['profiles']}

                first = await profiles()
                self.assertEqual(first['office.yaml']['host'], '192.0.2.10')
                self.assertNotIn('host', first['spare.yaml'])
                m.ha.states['sensor.ip']['state'] = '192.0.2.11'
                self.assertEqual((await profiles())['office.yaml']['host'], '192.0.2.11')
                m.ha.states['sensor.ip']['state'] = 'unavailable'
                self.assertEqual((await profiles())['office.yaml']['host'], 'office.example.test')
                m.updates.hosts.clear()
                self.assertNotIn('host', (await profiles())['office.yaml'])

    async def test_ambiguous_profile_does_not_suggest_either_devices_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.ha.registry += [
                {'entity_id': 'text.second', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd2'},
                {'entity_id': 'sensor.second_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd2'},
                {'entity_id': 'sensor.second_ip', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd2'},
            ]
            m.ha.states.update({'text.second': {'state': 'Synced'}, 'sensor.second_node': {'state': 'office-1'},
                                'sensor.second_ip': {'state': '192.0.2.12'}})
            async with TestClient(TestServer(create_app(m, True))) as client:
                profiles = (await (await client.get('/api/firmware')).json())['profiles']
                self.assertTrue(profiles)
                self.assertTrue(all('host' not in p for p in profiles))
