"""The capacitive S3 panel keeps its hardware and on-glass touch correction."""
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import profiles
from core import SHAPES, installation_yaml
from firmware import Firmware, profile_meta


class BoardLoader(yaml.SafeLoader):
    pass


BoardLoader.add_constructor('!include', lambda loader, node: loader.construct_scalar(node))
BOARD = yaml.load(profiles.BOARDS['jc4827w543c'].read_text(), Loader=BoardLoader)
DATA = {'board': 'jc4827w543c', 'name': 'panel-test', 'friendly_name': 'Panel test',
        'wifi_ssid': 'validation-only', 'wifi_password': 'validation-only'}


class JC4827W543CTests(unittest.TestCase):
    def test_touch_orientation_is_a_board_default_not_a_user_override(self):
        values = profiles.substitutions('checkout/jc4827w543c.yaml')
        self.assertEqual(values['TOUCH_SWAP_XY'], 'false')
        self.assertEqual(values['TOUCH_MIRROR_X'], 'true')
        self.assertEqual(values['TOUCH_MIRROR_Y'], 'true')
        touch = BOARD['touchscreen'][0]
        self.assertEqual((touch['platform'], touch['id'], touch['i2c_id']),
                         ('gt911', 'ts_touch', 'touch_bus'))
        self.assertEqual((touch['address'], touch['reset_pin'], touch['interrupt_pin']),
                         (0x5D, 'GPIO38', 'GPIO3'))
        self.assertEqual((BOARD['i2c']['sda'], BOARD['i2c']['scl']), ('GPIO8', 'GPIO4'))

    def test_display_and_memory_hardware(self):
        self.assertEqual(BOARD['esp32']['variant'], 'esp32s3')
        self.assertEqual(BOARD['esp32']['flash_size'], '4MB')
        self.assertEqual(BOARD['psram'], {'mode': 'octal', 'speed': '80MHz'})
        self.assertEqual(BOARD['spi']['type'], 'quad')
        self.assertEqual(BOARD['spi']['clk_pin'], 'GPIO47')
        self.assertEqual(BOARD['spi']['data_pins'], ['GPIO21', 'GPIO48', 'GPIO40', 'GPIO39'])
        self.assertEqual(BOARD['display'][0]['model'], 'JC4827W543')
        self.assertEqual(BOARD['output'][0]['pin'], 'GPIO1')
        shape = SHAPES['jc4827w543c']
        self.assertEqual(shape['chip'], 'ESP32-S3')
        self.assertEqual((shape['width'], shape['height'], shape['columns'], shape['rows']), (480, 272, 3, 3))
        self.assertEqual(shape['catalog']['touch'], 'GT911')
        self.assertFalse(shape['catalog']['calibrate'])
        self.assertTrue(shape['wide_slots'])
        self.assertTrue(shape['dimmable'])
        self.assertFalse(shape['hotspot'])
        chain = {path.name for path in profiles.chain(profiles.BOARDS['jc4827w543c'])}
        self.assertIn('flash-4mb.yaml', chain)
        self.assertNotIn('camera.yaml', chain)

    def test_normal_upstream_install_and_update_preserve_keys_and_overrides(self):
        text = installation_yaml(DATA)
        self.assertIn('files: [packages/jc4827w543c.yaml]', text)
        self.assertNotIn('/opt/homeassistant_espscreen/', text)
        self.assertTrue(profile_meta(text)['screen'])
        self.assertEqual(profile_meta(text)['package'], 'packages/jc4827w543c.yaml')
        with tempfile.TemporaryDirectory() as temp:
            manager = Firmware(Path(temp) / 'config', Path(temp) / 'data')
            result = manager.create(DATA)
            profile = manager.root / result['file']
            initial = profile_meta(profile.read_text())
            override = 'substitutions:\n  TOUCH_MIRROR_X: "false"\n'
            manager.save_override(result['file'], override)
            manager.set_language(result['file'], 'de')
            updated = profile_meta(profile.read_text())
            self.assertEqual(updated['api_key'], initial['api_key'])
            self.assertEqual(updated['package'], initial['package'])
            self.assertEqual(manager.override(result['file'])['content'], override)
            self.assertTrue(manager.wide_slots(result['file']))


if __name__ == '__main__':
    unittest.main()
