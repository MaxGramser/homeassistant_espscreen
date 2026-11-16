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
                # And a board with a Wi-Fi fallback hotspot its QR code (firmware 0.38.0); a board with 4 MB of flash has none.
                hotspot = ['packages/features/hotspot.yaml'] if profiles.hotspot(board) else []
                self.assertEqual(sorted(checker.included(ROOT / name)),
                                 sorted(['packages/core.yaml', str(profiles.BOARDS[board].relative_to(ROOT)), *hotspot]), name)

    def test_the_published_entry_takes_everything_from_github(self):
        for board in BOARDS:
            package = (ROOT / 'packages' / f'{board}.yaml').read_text()
            self.assertNotIn('!secret', package)
            self.assertNotIn('type: local', package)
            self.assertIn('url: https://github.com/MaxGramser/homeassistant_espscreen.git', package)
            # From main, unless the screen's own YAML names another branch (GITHUB_REF, the app's dev channel).
            self.assertIn('GITHUB_REF: "main"', package)
            self.assertIn('FONT_DIR: "https://raw.githubusercontent.com/MaxGramser/homeassistant_espscreen/${GITHUB_REF}/fonts"', package)
            # A checkout entry takes the fonts from the checkout's own fonts/.
            self.assertIn('FONT_DIR: "../fonts"', (ROOT / BOARDS[board]).read_text())
        # Every font a package names comes from that place, so a published screen and a checkout build the same letters.
        for path in sorted((ROOT / 'packages').rglob('*.yaml')):
            for line in re.findall(r'(?m)^\s*-?\s*file:\s*"?([^"\s]+\.(?:ttf|otf))', path.read_text()):
                self.assertTrue(line.startswith('${FONT_DIR}/'), f'{path.name}: read the font {line} from ${{FONT_DIR}}/')

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
        sys.path.insert(0, str(ROOT / 'screen_manager/app'))
        import core
        screen = core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'})
        wifi = re.search(r'^wifi:\n(.*?)(?=^[a-zA-Z_]+:|\Z)', screen, re.M | re.S)[1]
        self.assertIn('  power_save_mode: none\n', wifi)

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

    def test_a_resistive_panel_and_no_other_sets_up_its_calibration(self):
        # The cards of the grid made at boot, bound and drawn (firmware 0.53.0+) are the real boot's: tools/render/run.py
        # starts each board's firmware and its self test checks every page's cells (page_check).
        # A resistive panel keeps its calibration on the screen itself; a capacitive one reports pixels and needs none.
        for board in profiles.BOARDS:
            resistive = 'resistive-touch.yaml' in [path.name for path in profiles.chain(profiles.BOARDS[board])]
            self.assertEqual('screen_calibration::setup(' in profiles.resolved(f'packages/{board}.yaml'), resistive,
                             f'{board}: set the calibration up exactly on a resistive panel (features/resistive-touch.yaml)')

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
            # The old names of the ES7210's transport (parts/es7210.yaml, AUDIO_TRANSPORT), which the Waveshare P4 and
            # the Tab5 keep until the release after firmware 0.58 (tests/test_board_declarations.py, STILL_TO_MOVE).
            own -= {n for n in own if re.match(r'(P4|TAB5)_AUDIO_TRANSPORT$', n)}
            # A choice the board offers in New screen (boards.yaml `choices`) is a name the screen's own YAML sets.
            own -= set(profiles.CATALOG.get(board, {}).get('choices') or {})
            # What a feature brings (the resistive panel's calibration, the capacitive one's edge swipe, camera images,
            # a battery's voltage, a board's audio parts and their wiring, packages/hardware/parts/) and the
            # hardware a screen's own YAML may change on the board that has it (the pins of an ESP32-P4's Wi-Fi link
            # and touch bus, hardware/esp32p4-c6.yaml).
            self.assertTrue(all(re.match(r'(TOUCH_AFFINE_|TOUCH_CAL_|TOUCH_CONTROLLER$|EDGE_SWIPE_|ALERT_\w*IMAGE|CAMERA_|BATTERY_|AUDIO_|DISPLAY_MODEL$|DISPLAY_DATA_RATE$|FLASH_SIZE$|DISPLAY_INVERT_COLORS$|BACKLIGHT_FREQUENCY$|HOSTED_SDIO_FREQUENCY$|HOSTED_\w+_PIN$|TOUCH_SDA$|TOUCH_SCL$)', n) for n in own), f'{board}: {sorted(own)}')


class BoardRules(unittest.TestCase):
    """Rules every board keeps, read from its whole package chain (profiles.resolved): what the hardware packages share
    reaches each board that uses them, and nothing of one kind of hardware reaches another."""
    TEXTS = {board: profiles.resolved(profile) for board, _, profile in profiles.BOARD_TABLE}
    RGB_PANEL = re.compile(r'platform: (?:st7701s|mipi_rgb)\b')

    def test_every_rgb_panel_board_has_the_shared_esp32_s3_panel_settings(self):
        # packages/hardware/esp32s3-rgb.yaml (firmware 0.3.1): the panel's interrupt in IRAM, the 64-byte data cache line
        # and code run from PSRAM, or an RGB panel tears while flash is written.
        for board, text in self.TEXTS.items():
            if not self.RGB_PANEL.search(text):
                continue
            for needed in ('CONFIG_LCD_RGB_ISR_IRAM_SAFE: "y"', 'CONFIG_ESP32S3_DATA_CACHE_LINE_64B: "y"', 'execute_from_psram: true'):
                self.assertIn(needed, text, f'{board} has an RGB panel: include packages/hardware/esp32s3-rgb.yaml, which sets {needed}')

    def test_no_board_restarts_the_rgb_panel_in_vsync(self):
        # Only ever named in a comment (packages/hardware/esp32s3-rgb.yaml says why it stays off).
        for board, text in self.TEXTS.items():
            self.assertNotRegex(text, r'(?m)^\s*CONFIG_LCD_RGB_RESTART_IN_VSYNC:',
                                f'{board} sets CONFIG_LCD_RGB_RESTART_IN_VSYNC: leave it off, packages/hardware/esp32s3-rgb.yaml says why')

    def test_only_a_resistive_touch_is_corrected_from_raw_values(self):
        # The affine correction is applied once, on filtered raw values of a resistive panel (AGENTS.md, "Touch and
        # navigation"); a capacitive one reports pixels and is never corrected (docs/CALIBRATING.md).
        for board, text in self.TEXTS.items():
            if 'set_raw_correction' in text:
                self.assertIn('platform: xpt2046', text, f'{board} corrects raw touch values but has no resistive XPT2046: a capacitive panel needs none')

    def test_square_glass_has_the_same_cells_either_way_it_hangs(self):
        # A square board hangs the same way whichever way it is screwed to the wall, so its page has the same cells
        # standing up and it is never asked about (core.board_shape).
        for board, _, profile in profiles.BOARD_TABLE:
            values = profiles.substitutions(profile)
            if values.get('PANEL_W') != values.get('PANEL_H'):
                continue
            self.assertEqual((values.get('GRID_COLS_PORTRAIT', values['GRID_COLS']), values.get('GRID_ROWS_PORTRAIT', values['GRID_ROWS'])),
                             (values['GRID_COLS'], values['GRID_ROWS']), f'{board} is square: give it the same grid standing up as lying down')

    def test_every_board_waits_ten_minutes_before_standby(self):
        # The default standby is at least 600 seconds (AGENTS.md, "Touch and navigation").
        for board, profile in ((board, profile) for board, _, profile in profiles.BOARD_TABLE):
            seconds = int(profiles.substitutions(profile)['AUTO_DIM_TIMEOUT'])
            self.assertGreaterEqual(seconds, 600, f'{board} goes to standby after {seconds} s: the default is at least 600')

if __name__ == '__main__':
    unittest.main()
