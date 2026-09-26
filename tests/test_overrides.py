"""Per-device YAML overrides stay local, validated, and out of the profile list."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from firmware import Firmware  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha


class OverrideTests(unittest.TestCase):
    def make_firmware(self, tmp):
        f = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
        f.create({'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen',
                  'wifi_ssid': 'ssid', 'wifi_password': 'password'})
        return f

    def test_new_profiles_get_a_hidden_empty_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            profile = f.profile('kitchen.yaml').read_text()
            self.assertIn('local_overrides: !include kitchen.local.yaml', profile)
            self.assertEqual((f.root / 'kitchen.local.yaml').read_text(), '{}\n')
            self.assertEqual(f.profiles(), [{'file': 'kitchen.yaml'}])

    def test_override_is_attached_without_reformatting_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            original = f.profile('kitchen.yaml').read_text()
            content = 'display:\n  - id: my_display\n    model: ST7789V\n'
            saved = f.save_override('kitchen.yaml', content)
            self.assertEqual(saved['content'], content)
            self.assertTrue(saved['attached'])
            self.assertEqual(f.profile('kitchen.yaml').read_text(), original)
            fresh = Firmware(f.root, f.data)
            self.assertEqual(fresh.override('kitchen.yaml')['content'], content)
            self.assertEqual(fresh.profiles(), [{'file': 'kitchen.yaml'}])

    def test_existing_profile_gets_sidecar_on_first_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'esphome'
            root.mkdir()
            profile = root / 'existing.yaml'
            profile.write_text('esphome:\n  name: existing\n\npackages:\n  display: !include board.yaml\n\napi:\n')
            f = Firmware(root, Path(tmp) / 'data')
            f.save_override('existing.yaml', 'display:\n  - id: my_display\n    model: ST7789V\n')
            text = profile.read_text()
            self.assertIn('  local_overrides: !include existing.local.yaml\n', text)
            self.assertIn('\napi:\n', text)

    def test_managed_sections_and_bad_yaml_are_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            path = f.root / 'kitchen.local.yaml'
            before = path.read_text()
            for content in ('api:\n  encryption: {}\n', 'substitutions:\n  DEVICE_NAME: bad\n', 'display: [\n'):
                with self.assertRaises(ValueError):
                    f.save_override('kitchen.yaml', content)
                self.assertEqual(path.read_text(), before)

    def test_extend_of_a_package_component_is_accepted(self):
        # ESPHome appends package lists, so the way to change the shared display is !extend; LenientLoader
        # reads the tag as None and the file is stored as typed.
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            content = 'display:\n  - id: !extend my_display\n    model: ST7789V\n'
            self.assertEqual(f.save_override('kitchen.yaml', content)['content'], content)

    def test_empty_text_and_missing_newline_are_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            self.assertEqual(f.save_override('kitchen.yaml', '   \n')['content'], '{}\n')
            self.assertEqual(f.save_override('kitchen.yaml', 'logger:\n  level: DEBUG')['content'], 'logger:\n  level: DEBUG\n')

    def test_oversized_override_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            big = 'logger:\n' + ''.join(f'  # padding line {i}\n' for i in range(700))
            self.assertGreater(len(big), Firmware.OVERRIDE_LIMIT)
            with self.assertRaisesRegex(ValueError, 'too large'):
                f.save_override('kitchen.yaml', big)

    def test_a_symlinked_sidecar_is_never_read_or_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.make_firmware(tmp)
            secret = Path(tmp) / 'secret.txt'
            secret.write_text('wifi_password: hunter2\n')
            link = f.root / 'kitchen.local.yaml'
            link.unlink()
            link.symlink_to(secret)
            with self.assertRaises(ValueError):
                f.override('kitchen.yaml')
            with self.assertRaises(ValueError):
                f.save_override('kitchen.yaml', 'logger:\n  level: DEBUG\n')
            self.assertEqual(secret.read_text(), 'wifi_password: hunter2\n')
            self.assertTrue(link.is_symlink())

    def test_include_is_appended_when_packages_is_the_last_section_without_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'esphome'
            root.mkdir()
            profile = root / 'tail.yaml'
            profile.write_text('esphome:\n  name: tail\npackages:\n  display: !include board.yaml')
            f = Firmware(root, Path(tmp) / 'data')
            f.save_override('tail.yaml', 'logger:\n  level: DEBUG\n')
            self.assertEqual(profile.read_text(),
                             'esphome:\n  name: tail\npackages:\n  display: !include board.yaml\n  local_overrides: !include tail.local.yaml\n')

    def test_a_foreign_local_overrides_include_leaves_the_profile_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'esphome'
            root.mkdir()
            profile = root / 'other.yaml'
            text = 'esphome:\n  name: other\npackages:\n  local_overrides: !include elsewhere.yaml\n'
            profile.write_text(text)
            f = Firmware(root, Path(tmp) / 'data')
            with self.assertRaises(ValueError):
                f.save_override('other.yaml', 'logger:\n  level: DEBUG\n')
            self.assertEqual(profile.read_text(), text)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class OverrideRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_reads_saves_and_is_told_when_the_text_is_too_big(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'ESPHOME_CONFIG': str(Path(tmp) / 'esphome')}):
                m = Manager(fake_ha(), Path(tmp) / 'screens.json')
            m.firmware.create({'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen',
                               'wifi_ssid': 'ssid', 'wifi_password': 'password'})
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory')).json()
                headers = {'X-Screen-CSRF': inventory['csrf']}
                url = '/api/firmware/profiles/kitchen.yaml/override'
                data = await (await client.get(url)).json()
                self.assertEqual((data['override_file'], data['attached'], data['content']), ('kitchen.local.yaml', True, '{}\n'))
                self.assertEqual((await client.put(url, json={'content': 'logger: {}\n'})).status, 403, 'CSRF')
                response = await client.put(url, json={'content': 'display:\n  - id: !extend my_display\n    model: ST7789V\n'}, headers=headers)
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['content'], 'display:\n  - id: !extend my_display\n    model: ST7789V\n')
                response = await client.put(url, json={'content': 'api:\n  reboot_timeout: 0s\n'}, headers=headers)
                self.assertEqual(response.status, 400)
                self.assertIn('api', (await response.json())['error'])
                # The override keeps its own 12 KB limit; the request limit is far above it (app 0.2.78).
                response = await client.put(url, json={'content': 'logger:\n' + '  # p\n' * 4000}, headers=headers)
                self.assertEqual(response.status, 400)
                self.assertIn('12 KB', (await response.json())['error'])
                response = await client.put(url, json={'content': 'logger:\n' + '  # p\n' * 40000}, headers=headers)
                self.assertEqual((response.status, (await response.json())['error']), (413, 'That request is too large.'))
                self.assertEqual((await (await client.get(url)).json())['content'], 'display:\n  - id: !extend my_display\n    model: ST7789V\n')
                self.assertEqual([p['file'] for p in (await (await client.get('/api/firmware')).json())['profiles']], ['kitchen.yaml'])


if __name__ == '__main__':
    unittest.main()
