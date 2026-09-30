"""Download screen files: a screen's YAML, its Override YAML and the secrets they use, to build it on your own computer."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from firmware import Firmware  # noqa: E402

PROFILE = {'board': 'cyd', 'name': 'kitchen', 'friendly_name': 'Kitchen', 'wifi_ssid': 'Home', 'wifi_password': 'pass word'}


def unpacked(body):
    with zipfile.ZipFile(io.BytesIO(body)) as bundle:
        return {info.filename: bundle.read(info).decode() for info in bundle.infolist()}


class ScreenFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'esphome'
        self.firmware = Firmware(self.root, Path(self.tmp.name) / 'data')

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_three_files_build_the_screen_as_the_app_does(self):
        self.firmware.create(PROFILE)
        body, name = self.firmware.files('kitchen.yaml')
        files = unpacked(body)
        self.assertEqual(name, 'kitchen.zip')
        self.assertEqual(sorted(files), ['kitchen/kitchen.local.yaml', 'kitchen/kitchen.yaml', 'kitchen/secrets.yaml'])
        # The YAML as the app keeps it, with its keys, and the override it includes.
        self.assertEqual(files['kitchen/kitchen.yaml'], (self.root / 'kitchen.yaml').read_text())
        self.assertIn('local_overrides: !include kitchen.local.yaml', files['kitchen/kitchen.yaml'])
        self.assertEqual(files['kitchen/kitchen.local.yaml'], '{}\n')
        self.assertEqual(yaml.safe_load(files['kitchen/secrets.yaml']), {'wifi_ssid': 'Home', 'wifi_password': 'pass word'})

    def test_only_the_secrets_the_screen_uses_leave_the_shared_file(self):
        self.firmware.create(PROFILE)
        secrets = self.root / 'secrets.yaml'
        secrets.write_text(secrets.read_text() + 'garage_code: "1234"\nmqtt_password: other\n')
        (self.root / 'kitchen.local.yaml').write_text('mqtt:\n  password: !secret mqtt_password\n')
        files = unpacked(self.firmware.files('kitchen.yaml')[0])
        self.assertEqual(yaml.safe_load(files['kitchen/secrets.yaml']),
                         {'wifi_ssid': 'Home', 'wifi_password': 'pass word', 'mqtt_password': 'other'})
        self.assertNotIn('garage_code', files['kitchen/secrets.yaml'])
        self.assertIn('!secret mqtt_password', files['kitchen/kitchen.local.yaml'])

    def test_a_profile_outside_the_folder_is_refused(self):
        self.firmware.create(PROFILE)
        for name in ('../kitchen.yaml', 'secrets', 'missing.yaml'):
            with self.assertRaises(ValueError):
                self.firmware.files(name)

    def test_a_screen_without_override_or_secrets_file_still_downloads(self):
        self.root.mkdir(parents=True)
        (self.root / 'hall.yaml').write_text('esphome:\n  name: hall\nwifi:\n  ssid: !secret wifi_ssid\n')
        files = unpacked(self.firmware.files('hall.yaml')[0])
        self.assertEqual(files['hall/hall.local.yaml'], '{}\n')
        self.assertEqual(files['hall/secrets.yaml'], '{}\n')


if __name__ == '__main__':
    unittest.main()
