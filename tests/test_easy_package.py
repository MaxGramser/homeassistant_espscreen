"""The packages a screen builds from: generated from the board profiles, runtime tiles only."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARDS = {
    'cyd': 'home-like-2432s028.yaml',
    'guition': 'guition-4848s040.yaml',
    'jc8012p4a1': 'jc8012p4a1.yaml',
}
# The old manual profile bound tiles to fixed entities in the YAML. ESP Screens sends the tiles now, so
# none of this may come back: the fixed subscriptions, its tap handlers and scripts, its own vacuum card.
GONE = ['ha_state_tile1', 'tile1_brightness', 'tile6_climate_humidity', 'tile6_cover_state', 'smartdisplay_action',
        'publish_action', 'do_tile_action', 'open_vacuum_overlay', 'vacuum_action', 'vacuum_fan_speed', 'vacuum_overlay',
        'vacspd_quiet', 'vacuum_actions', 'DYNAMIC_TILES', 'TILE_COUNT', 'DIRECT_ACTIONS', 'TILE1_ENTITY',
        'light_controls::subscribe']


def load_generator():
    spec = importlib.util.spec_from_file_location('generate_packages', ROOT / 'tools/generate_packages.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_packages_are_current(self):
        generator = load_generator()
        for board in BOARDS:
            self.assertEqual((ROOT / 'packages' / f'{board}.yaml').read_text(), generator.generate(board), board)

    def test_no_secrets_and_no_local_paths(self):
        for board in BOARDS:
            package = (ROOT / 'packages' / f'{board}.yaml').read_text()
            self.assertNotIn('!secret', package)
            self.assertNotIn('type: local', package)
            self.assertIn('url: https://github.com/MaxGramser/homeassistant_espscreen.git', package)

    def test_the_manual_profile_is_gone_from_profiles_and_packages(self):
        for board, name in BOARDS.items():
            for path in (ROOT / name, ROOT / 'packages' / f'{board}.yaml'):
                text = '\n'.join(line for line in path.read_text().split('\n') if not line.lstrip().startswith('#'))
                for key in GONE:
                    self.assertNotIn(key, text, f'{path.name} still carries {key}')

    def test_runtime_tiles_keep_what_they_bind_and_open(self):
        for board in BOARDS:
            package = (ROOT / 'packages' / f'{board}.yaml').read_text()
            for key in ['runtime_tiles::bind(9, id(tile10)', 'runtime_tiles::enabled = true;', 'id: open_value_overlay',
                        'id: ui_refresh', 'runtime_tiles::render(id(lbl_room));', 'id: climate_detail_overlay',
                        'id: color_detail_overlay']:
                self.assertIn(key, package, board)
        # The CYD keeps its resistive calibration on the screen itself; the Guition's GT911 needs none.
        self.assertIn('screen_calibration::setup(', (ROOT / 'packages/cyd.yaml').read_text())

    def test_generator_refuses_a_fixed_home_assistant_subscription(self):
        generator = load_generator()
        text = (ROOT / BOARDS['cyd']).read_text()
        stray = '  - platform: homeassistant\n    id: stray\n    entity_id: sensor.stray\n\nbinary_sensor:\n'
        with self.assertRaises(ValueError):
            generator.generate('cyd', text.replace('binary_sensor:\n', stray, 1))


if __name__ == '__main__':
    unittest.main()
