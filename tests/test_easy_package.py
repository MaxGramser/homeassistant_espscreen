"""The packages a screen builds from: one shared core plus a board file, runtime tiles only (app 0.2.84+)."""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402

BOARDS = {'cyd': 'checkout/cyd.yaml', 'guition': 'checkout/guition.yaml',
          'waveshare7': 'checkout/waveshare7.yaml'}
# The old manual profile bound tiles to fixed entities in the YAML. ESP Screens sends the tiles now, so
# none of this may come back: the fixed subscriptions, its tap handlers and scripts, its own vacuum card.
GONE = ['ha_state_tile1', 'tile1_brightness', 'tile6_climate_humidity', 'tile6_cover_state', 'smartdisplay_action',
        'publish_action', 'do_tile_action', 'open_vacuum_overlay', 'vacuum_action', 'vacuum_fan_speed', 'vacuum_overlay',
        'vacspd_quiet', 'vacuum_actions', 'DYNAMIC_TILES', 'TILE_COUNT', 'DIRECT_ACTIONS', 'TILE1_ENTITY',
        'light_controls::subscribe']


def load_checker():
    spec = importlib.util.spec_from_file_location('check_packages', ROOT / 'tools/check_packages.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_the_packages_fit_together(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/check_packages.py')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_entry_is_the_shared_core_plus_its_board(self):
        checker = load_checker()
        for board, profile in BOARDS.items():
            for name in (profile, f'packages/{board}.yaml'):
                self.assertEqual(sorted(checker.included(ROOT / name)), sorted(['packages/core.yaml', str(profiles.BOARDS[board].relative_to(ROOT))]), name)
                # The board brings the cards of its grid.
                cells = profiles.cells_of(profiles.BOARDS[board])
                self.assertEqual(len(cells), 1, board)
                grid = profiles.board_values(board)
                self.assertEqual(cells[0].name, f"{int(grid['GRID_COLS']) * int(grid['GRID_ROWS'])}.yaml", board)

    def test_the_published_entry_takes_everything_from_github(self):
        for board in BOARDS:
            package = (ROOT / 'packages' / f'{board}.yaml').read_text()
            self.assertNotIn('!secret', package)
            self.assertNotIn('type: local', package)
            self.assertIn('url: https://github.com/MaxGramser/homeassistant_espscreen.git', package)
            self.assertIn('FONT_DIR: "https://raw.githubusercontent.com/MaxGramser/homeassistant_espscreen/main/fonts"', package)
            # The fonts of the shared core come from that place; a checkout entry takes them from the checkout's own fonts/.
            self.assertIn('file: "${FONT_DIR}/Roboto-500.ttf"', profiles.CORE.read_text())
            self.assertIn('FONT_DIR: "../fonts"', (ROOT / BOARDS[board]).read_text())

    def test_no_secret_or_local_path_under_packages(self):
        for path in sorted((ROOT / 'packages').rglob('*.yaml')):
            text = '\n'.join(line for line in path.read_text().split('\n') if not line.lstrip().startswith('#'))
            self.assertNotIn('!secret', text, path.name)
            self.assertNotIn('type: local', text, path.name)
            for section in ('sensor', 'binary_sensor', 'text_sensor'):
                block = re.search(r'^' + section + r':\n.*?(?=^[a-zA-Z_]+:|\Z)', text, re.M | re.S)
                self.assertFalse(block and re.search(r'^  - platform: homeassistant$', block[0], re.M), f'{path.name}: a {section} subscribes to Home Assistant')

    def test_the_wifi_never_dozes_but_stays_the_owners(self):
        # Firmware 0.2.74+: the core keeps Wi-Fi awake for every screen, and nothing else of Wi-Fi lives in a package;
        # the network, its password and the fallback hotspot stay in the screen's own YAML, which also wins on the mode.
        for path in sorted((ROOT / 'packages').rglob('*.yaml')):
            text = path.read_text()
            block = re.search(r'^wifi:\n(.*?)(?=^[a-zA-Z_]+:|\Z)', text, re.M | re.S)
            if path == profiles.CORE:
                self.assertIsNotNone(block, 'packages/core.yaml has no wifi: block')
                lines = [line for line in block[1].split('\n') if line.strip() and not line.lstrip().startswith('#')]
                self.assertEqual(lines, ['  power_save_mode: none'])
            else:
                self.assertIsNone(block, f'{path.name} has a wifi: block')
        # The YAML ESP Screens writes says so too (since app 0.2.24), so an older package changes nothing for those.
        self.assertIn('  power_save_mode: none\n', (ROOT / 'screen_manager/app/core.py').read_text())

    def test_the_manual_profile_is_gone_from_profiles_and_packages(self):
        for board, name in BOARDS.items():
            for entry in (name, f'packages/{board}.yaml'):
                text = '\n'.join(line for line in profiles.text(entry).split('\n') if not line.lstrip().startswith('#'))
                for key in GONE:
                    self.assertNotIn(key, text, f'{entry} still carries {key}')

    def test_a_board_says_whether_its_screen_can_go_dark(self):
        # CAN_STANDBY (firmware 0.2.91+): every board file says it, and a board that cannot go dark keeps the ten
        # entities of standby and night out of Home Assistant with ESPHome's own !extend, so the flag and that list
        # never drift apart. The Waveshare's backlight boost browns the board out when it switches on from a dark
        # screen. The experimental 7-inch profile also keeps standby disabled pending physical wake tests.
        entities = ['setting_auto_standby', 'setting_night_mode', 'setting_home_on_standby', 'setting_standby_brightness',
                    'setting_night_brightness', 'setting_standby_seconds', 'setting_night_start', 'setting_night_end',
                    'wake_button', 'sleep_button']
        seen = {}
        for board, path in profiles.BOARDS.items():
            # What the screen sees: the core's default, or features/backlight-always-on.yaml's false.
            values = profiles.board_values(board)
            self.assertIn('CAN_STANDBY', values, f'{path.name} does not say CAN_STANDBY')
            self.assertIn(values['CAN_STANDBY'].strip('"'), ('true', 'false'), path.name)
            can = values['CAN_STANDBY'].strip('"') == 'true'
            seen[board] = can
            text = profiles.text(profiles.PROFILES[list(profiles.BOARDS).index(board)])
            for entity in entities:
                # The entity follows the flag, so a board modded to go dark (an override with CAN_STANDBY "true") shows it.
                extended = re.search(rf'^  - id: !extend {entity}\n    internal: \$\{{ \(CAN_STANDBY \| string \| lower\) != "true" \}}\n',
                                     text, re.M) is not None
                self.assertEqual(extended, not can, f'{path.name}: {entity} {"stays visible" if can else "must be internal"}')
            # The one way a board says it cannot: it includes features/backlight-always-on.yaml.
            always_on = any(item.name == 'backlight-always-on.yaml' for item in profiles.chain(path))
            self.assertEqual(can, not always_on, path.name)
        self.assertFalse(seen['waveshare43'])
        self.assertFalse(seen['waveshare7'])
        self.assertTrue(seen['guition'] and seen['cyd'])
        # boards.json carries the same answer for the add-on (tools/generate_board_shapes.py).
        import json
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for board, can in seen.items():
            self.assertEqual(shapes[board]['can_standby'], can, board)

    def test_runtime_tiles_keep_what_they_bind_and_open(self):
        for board in BOARDS:
            package = profiles.text(f'packages/{board}.yaml')
            # One card per cell of the board's grid, and the parts every screen has.
            grid = profiles.board_values(board)
            cells = int(grid['GRID_COLS']) * int(grid['GRID_ROWS'])
            for key in [f'runtime_tiles::bind({cells - 1}, id(tile{cells})', 'runtime_tiles::enabled = true;', 'id: open_value_overlay',
                        'id: ui_refresh', 'runtime_tiles::render(id(lbl_room));', 'id: color_detail_overlay']:
                self.assertIn(key, package, board)
        # The CYD keeps its resistive calibration on the screen itself; the Guition's GT911 needs none.
        self.assertIn('screen_calibration::setup(', profiles.resolved('packages/cyd.yaml'))
        self.assertNotIn('screen_calibration::setup(', profiles.resolved('packages/guition.yaml'))

    def test_the_core_carries_no_board_number_and_every_board_the_same_names(self):
        core = profiles.CORE.read_text()
        for needle in ('esp32:', 'platform: xpt2046', 'platform: gt911', 'platform: st7701s', 'platform: mipi_spi', 'psram:',
                       'set_raw_correction', 'camera_image', 'GPIO'):
            self.assertNotIn(needle, core, f'{needle} is a board\'s, not the core\'s')
        # How the firmware is built is the same on every board (firmware 0.2.75+): packages/hardware/esp-idf.yaml,
        # which every board includes, directly or through its hardware.
        for board, path in profiles.BOARDS.items():
            chain = profiles.chain(path)
            self.assertIn(ROOT / 'packages/hardware/esp-idf.yaml', chain, board)
        self.assertIn('      assertion_level: SILENT\n', (ROOT / 'packages/hardware/esp-idf.yaml').read_text())
        # Every screen sees the same names, whatever board it is: a board states values, never names of its own.
        # A floor, not a count: the list gets shorter every time the firmware works something out from the live
        # canvas instead of reading it (the cells, the page bar and the settings strip went that way in firmware
        # 0.2.92), and it must never get shorter because one board started going its own way.
        names = {board: set(profiles.board_values(board)) for board in profiles.BOARDS}
        shared = set.intersection(*names.values())
        self.assertGreater(len(shared), 90)
        for board, defined in names.items():
            own = defined - shared
            # What a feature brings (the resistive panel's calibration, the capacitive one's edge swipe, camera images)
            # and the hardware a screen's own YAML may change on the board that has it.
            self.assertTrue(all(re.match(r'(TOUCH_AFFINE_|TOUCH_CAL_|EDGE_SWIPE_|ALERT_\w*IMAGE|CAMERA_|DISPLAY_MODEL$|DISPLAY_DATA_RATE$|DISPLAY_INVERT_COLORS$|BACKLIGHT_FREQUENCY$|HOSTED_SDIO_FREQUENCY$)', n) for n in own), f'{board}: {sorted(own)}')

    def test_the_checker_refuses_a_fixed_home_assistant_subscription(self):
        source = (ROOT / 'tools/check_packages.py').read_text()
        self.assertIn("re.search(r'^  - platform: homeassistant$', match[0], re.M)", source)
        self.assertIn("for section in ('sensor', 'binary_sensor', 'text_sensor'):", source)


if __name__ == '__main__':
    unittest.main()
