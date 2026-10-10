"""The board catalog (app 0.2.129): boards.yaml says what the hardware files cannot, and everything else is worked out.

boards.yaml names each board, says what is printed on it and how far it has been tried, and lists the choices made
when a screen of it is built. tools/generate_board_shapes.py adds what the board's own files say (the size of its
glass in inches, its touch controller, whether it asks for a touch calibration) and writes it into boards.json, which
the add-on reads. New screen and the screen list draw every board from that, so a board is added in the catalog and
its files, never in the editor or its translations. These checks keep that promise.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import profiles  # noqa: E402
import core  # noqa: E402
import firmware as firmware_module  # noqa: E402

SHAPES = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())


class Catalog(unittest.TestCase):
    def test_every_board_of_the_catalog_has_its_files(self):
        self.assertEqual(list(profiles.CATALOG), list(profiles.BOARDS))
        for board, entry in profiles.CATALOG.items():
            self.assertTrue((ROOT / 'packages/boards' / entry['file']).is_file(), board)
            self.assertTrue((ROOT / 'packages' / f'{board}.yaml').is_file(), board)
            self.assertTrue((ROOT / 'checkout' / f'{board}.yaml').is_file(), board)
            self.assertEqual(profiles.board_values(board)['BOARD_ID'].strip('"'), board, 'the word its firmware reports')

    def test_the_add_on_offers_the_catalog_in_its_order(self):
        self.assertEqual(list(core.BOARD_KEYS), list(profiles.CATALOG))
        self.assertEqual(list(firmware_module.BOARD_CHOICES), list(profiles.CATALOG))
        cyd = firmware_module.BOARD_CHOICES['cyd']
        self.assertEqual((cyd['name'], cyd['model'], cyd['inch'], cyd['touch'], cyd['calibrate'], cyd['camera']),
                         ('CYD', 'ESP32-2432S028', 2.8, 'XPT2046', True, False))
        big = firmware_module.BOARD_CHOICES['jc8012p4a1']
        self.assertEqual((big['name'], big['inch'], big['touch'], big['status'], big['calibrate']),
                         ('Guition', 10.1, 'GSL3670', 'new', False))
        tab5 = firmware_module.BOARD_CHOICES['tab5']
        self.assertEqual((tab5['name'], tab5['model'], tab5['inch'], tab5['touch'], tab5['status'], tab5['calibrate'],
                          tab5['camera']),
                         ('M5Stack Tab5', 'Tab5 ST7121', 5.0, 'ST7121', 'new', False, True))
        source = profiles.BOARDS['tab5'].read_text()
        self.assertIn('model: M5STACK-TAB5-ST7121', source)
        self.assertIn('platform: st7123', source)
        self.assertIn('TOUCH_CONTROLLER: "ST7121"', source)

    def test_what_the_files_say_is_worked_out_not_written(self):
        for board in profiles.CATALOG:
            catalog, values = SHAPES[board]['catalog'], profiles.board_values(board)
            # The glass: its diagonal in pixels over its density.
            side = SHAPES[board]['orientations']['landscape']
            self.assertAlmostEqual(catalog['inch'], (side['width'] ** 2 + side['height'] ** 2) ** 0.5 / float(values['DISPLAY_DPI']),
                                   delta=0.05, msg=board)
            # A resistive panel is measured on the glass on the first start; a capacitive one reports pixels.
            chain = [path.name for path in profiles.chain(profiles.BOARDS[board])]
            self.assertEqual(catalog['calibrate'], 'resistive-touch.yaml' in chain, board)
            self.assertIn(catalog['status'], ('stable', 'new', 'experimental'), board)
            for key, options in catalog['choices'].items():
                self.assertEqual(options[0], values[key].strip('"'), f'{board} {key}: the board file\'s own value first')

    def test_tab5_exposes_its_battery_level_from_the_ina226(self):
        class IncludeLoader(yaml.SafeLoader):
            pass

        IncludeLoader.add_constructor('!include', lambda loader, node: loader.construct_scalar(node))
        hardware = yaml.load((ROOT / 'packages/hardware/m5stack-tab5.yaml').read_text(), Loader=IncludeLoader)
        ina226 = next(sensor for sensor in hardware['sensor'] if sensor.get('platform') == 'ina226')
        level = next(sensor for sensor in hardware['sensor'] if sensor.get('name') == 'Battery Level')

        self.assertEqual((ina226['address'], ina226['i2c_id']), (0x41, 'tab5_bus'))
        self.assertEqual(ina226['bus_voltage']['name'], 'Battery Voltage')
        self.assertEqual(ina226['bus_voltage']['entity_category'], 'diagnostic')
        self.assertEqual((level['device_class'], level['state_class'], level['unit_of_measurement']),
                         ('battery', 'measurement', '%'))
        self.assertEqual(level['filters'][1]['calibrate_linear']['datapoints'][0], '6.00 -> 0')
        self.assertEqual(level['filters'][1]['calibrate_linear']['datapoints'][-1], '8.40 -> 100')

    def test_waveshare_lcd4_uses_its_settled_gt911_driver(self):
        class IncludeLoader(yaml.SafeLoader):
            pass

        IncludeLoader.add_constructor('!include', lambda loader, node: loader.construct_scalar(node))
        board = yaml.load((ROOT / 'packages/boards/waveshare-esp32s3-lcd-4.yaml').read_text(),
                          Loader=IncludeLoader)
        touch = board['touchscreen'][0]
        external = board['external_components'][0]

        self.assertEqual(external['source'],
                         'github://leonardospina/homeassistant_espscreen@2649adae176577c114c8c0491f888469ede59302')
        self.assertEqual(external['components'], ['gt911'])
        self.assertNotIn('use_primary_i2c_addr', touch)
        self.assertNotIn('setup_priority', touch)
        self.assertEqual((touch['reset_pin']['waveshare_io_ch32v003'], touch['reset_pin']['number']),
                         ('expander', 1))
        self.assertEqual((touch['power_pin']['waveshare_io_ch32v003'], touch['power_pin']['number']),
                         ('expander', 5))
        self.assertIn('interrupt_pin', touch)
        self.assertEqual((touch['interrupt_pin']['waveshare_io_ch32v003'], touch['interrupt_pin']['number']),
                         ('expander', 2))
        self.assertNotIn('power_supply', board)
        self.assertNotIn('power_supply', board['output'][0])

        for entry in (ROOT / 'packages/wavesharelcd4.yaml', ROOT / 'checkout/wavesharelcd4.yaml'):
            self.assertNotIn('components: [gt911, smart_display]', entry.read_text())

        driver = (ROOT / 'components/gt911/touchscreen/gt911_touchscreen.cpp').read_text()
        setup = driver[driver.index('void GT911Touchscreen::setup()'):driver.index('bool GT911Touchscreen::init_sequence_')]
        self.assertLess(setup.index('init_sequence_'), setup.index('setup_internal_'))
        self.assertIn('GT911_INIT_ATTEMPTS = 3', driver)
        self.assertIn('for (uint8_t attempt = 1; attempt <= GT911_INIT_ATTEMPTS; attempt++)', setup)
        self.assertIn('configuration_valid_()', setup)
        self.assertLess(setup.index('init_sequence_'), setup.index('configuration_valid_()'))
        self.assertIn('Invalid GT911 configuration after power cycle', setup)
        sequence = driver[driver.index('bool GT911Touchscreen::init_sequence_'):
                          driver.index('void GT911Touchscreen::setup_internal_')]
        address_low = sequence.index('this->interrupt_pin_->digital_write(false);')
        power_off = sequence.index('this->power_pin_->digital_write(false);')
        reset_low = sequence.index('this->reset_pin_->digital_write(false);')
        first_wait = sequence.index('delay(200);', reset_low)
        power_on = sequence.index('this->power_pin_->digital_write(true);', first_wait)
        reset_high = sequence.index('this->reset_pin_->digital_write(true);', power_on)
        second_wait = sequence.index('delay(200);', reset_high)
        self.assertLess(address_low, power_off)
        self.assertLess(power_off, reset_low)
        self.assertLess(reset_low, first_wait)
        self.assertLess(first_wait, power_on)
        self.assertLess(power_on, reset_high)
        self.assertLess(reset_high, second_wait)
        self.assertNotIn('this->interrupt_pin_->pin_mode(gpio::FLAG_INPUT);', sequence)
        self.assertIn('probe_address_(SECONDARY_ADDRESS', driver)
        validation = driver[driver.index('bool GT911Touchscreen::configuration_valid_()'):
                            driver.index('void GT911Touchscreen::setup_internal_')]
        self.assertIn('GET_MAX_VALUES', validation)
        self.assertIn('x_res != 0 && y_res != 0', validation)


class Choices(unittest.TestCase):
    def profile(self, **extra):
        return core.installation_yaml({'board': 'cyd', 'name': 'hall', 'friendly_name': 'Hall', **extra})

    def test_a_choice_other_than_the_board_files_own_is_a_line_of_the_screens_substitutions(self):
        text = self.profile(choices={'DISPLAY_MODEL': 'ST7789V'})
        substitutions = re.search(r'(?ms)^substitutions:\n(.*?)\n\n', text)[1]
        self.assertIn('  DISPLAY_MODEL: "ST7789V"', substitutions.split('\n'))
        # The board file's own value writes nothing, as lying down does: the profile reads as it did before this choice.
        same = lambda text: re.sub(r'(?m)^(\s+(?:key|password)): ".*"$', r'\1: ""', text)  # noqa: E731 (random keys)
        self.assertEqual(same(self.profile(choices={'DISPLAY_MODEL': 'ILI9341'})), same(self.profile()))
        self.assertNotIn('DISPLAY_MODEL', self.profile())

    def test_another_grid_from_new_screen_is_lines_in_the_screens_yaml(self):
        # New screen's Advanced (app 0.4.85): the grid a screen starts with, within the range of the way it hangs, as
        # lines of its own YAML; the board's own grid writes nothing. The editor changes it later without a build.
        def subs(text): return re.search(r'(?ms)^substitutions:\n(.*?)\n\n', text)[1].split('\n')
        best = core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall', 'grid': {'columns': 2, 'rows': 3}})
        self.assertNotIn('GRID_', best)
        four = core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall', 'grid': {'columns': 2, 'rows': 4}})
        self.assertIn('  GRID_ROWS: "4"', subs(four))
        self.assertNotIn('GRID_COLS', four)
        # Standing up on glass that is not square: that way's lines, and the angle.
        tall = core.installation_yaml({'board': 'cyd', 'name': 'hall', 'friendly_name': 'Hall', 'orientation': 'portrait',
                                       'grid': {'columns': 2, 'rows': 5}})
        self.assertIn('  GRID_COLS_PORTRAIT: "2"', subs(tall))
        self.assertIn('  GRID_ROWS_PORTRAIT: "5"', subs(tall))
        self.assertIn(f'  LVGL_ROTATION: "{SHAPES["cyd"]["orientations"]["portrait"]["rotation"]}"', subs(tall))
        # Past what that way takes, or not a grid at all: refused.
        for grid in ({'columns': 4, 'rows': 3}, {'columns': 0, 'rows': 3}, {'columns': 2}, {'columns': '2', 'rows': 3}, [2, 3]):
            with self.assertRaises(ValueError, msg=grid):
                core.installation_yaml({'board': 'cyd', 'name': 'hall', 'friendly_name': 'Hall', 'grid': grid})
        # Offline, the screen's own YAML says the grid it starts with, the way it hangs: the app counts its cells on it.
        import firmware
        self.assertEqual(firmware.profile_meta(four)['built_grid'], {'rows': 4})
        self.assertEqual(firmware.profile_meta(best)['built_grid'], {})
        self.assertEqual(firmware.profile_meta(tall)['built_grid'], {'columns_portrait': 2, 'rows_portrait': 5})
        self.assertEqual(core.grid_of({'board': 'guition', 'built_grid': {'rows': 4}}), core.Grid(2, 4))
        self.assertEqual(core.grid_of({'board': 'guition', 'built_grid': {}}), core.Grid(2, 3))
        self.assertEqual(core.grid_of({'board': 'cyd', 'orientation': 'portrait', 'built_grid': {'columns_portrait': 2, 'rows_portrait': 5}}),
                         core.Grid(2, 5))
        # What the screen reports itself still wins.
        reported = {'width': 480, 'height': 480, 'columns': 2, 'rows': 3, 'dpi': 170, 'look': 'standard'}
        self.assertEqual(core.grid_of({'board': 'guition', 'built_grid': {'rows': 4}, 'shape': reported}), core.Grid(2, 3))

    def test_no_board_offers_its_grid_as_a_choice_any_more(self):
        # The grid is every screen's to choose within its range (app 0.4.85), not a choice of a few boards (app 0.4.31).
        for board, shape in SHAPES.items():
            if board.startswith(('checkout/', 'packages/')):
                continue
            self.assertNotIn('GRID_ROWS', (shape.get('catalog') or {}).get('choices') or {}, board)
            for way in ('landscape', 'portrait'):
                side = shape['orientations'][way]
                self.assertTrue(side['min'][0] <= side['columns'] <= side['max'][0] and side['min'][1] <= side['rows'] <= side['max'][1], board)
        # The 64 tiles of a screen without PSRAM fill a grid of any size the same way.
        for rows in (3, 4):
            grid = core.grid_of({'board': 'tab5', 'built_grid': {'rows': rows}})
            self.assertEqual((grid.pages, grid.max_tiles), (8, 64))
            tiles = [{'entity': f'light.tab5_{n}', 'name': ''} for n in range(64)]
            self.assertEqual(len(core.validate_layout({'title': 'Tab5', 'tiles': tiles}, grid=grid)['tiles']), 64)

    def test_a_choice_the_board_does_not_offer_is_refused(self):
        for choices in ({'DISPLAY_MODEL': 'GC9A01'}, {'DISPLAY_DATA_RATE': '20MHz'}, ['DISPLAY_MODEL'], 'ST7789V'):
            with self.assertRaises(ValueError, msg=choices):
                self.profile(choices=choices)
        with self.assertRaises(ValueError):
            core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall', 'choices': {'DISPLAY_MODEL': 'ST7789V'}})
        with self.assertRaises(ValueError):
            core.installation_yaml({'board': 'lab-thing', 'name': 'hall', 'friendly_name': 'Hall'})


class ChoiceAndOverride(unittest.TestCase):
    def test_the_override_may_not_set_what_the_screens_own_yaml_chose(self):
        # The screen's own substitutions win over the override (a package), so the same line there would quietly lose.
        with tempfile.TemporaryDirectory() as tmp:
            firmware = firmware_module.Firmware(tmp, Path(tmp) / 'data')
            for name, choices in (('st.yaml', {'DISPLAY_MODEL': 'ST7789V'}), ('ili.yaml', {})):
                (Path(tmp) / name).write_text(core.installation_yaml({'board': 'cyd', 'name': name[:-5], 'friendly_name': name,
                                                                      'choices': choices}))
            with self.assertRaises(ValueError) as refused:
                firmware.save_override('st.yaml', 'substitutions:\n  DISPLAY_MODEL: "ILI9341"\n')
            self.assertIn('DISPLAY_MODEL', str(refused.exception))
            # Anything else the board offers, and the same line on a screen that chose nothing, are the override's.
            firmware.save_override('st.yaml', 'substitutions:\n  DISPLAY_DATA_RATE: "20MHz"\n')
            firmware.save_override('ili.yaml', 'substitutions:\n  DISPLAY_MODEL: "ST7789V"\n')


class NoBoardInTheEditor(unittest.TestCase):
    def test_new_screen_and_the_screen_list_name_no_board(self):
        words = [board for board in profiles.CATALOG] + sorted({entry['name'] for entry in profiles.CATALOG.values()})
        for name in ('components/InstallerView.vue', 'components/Sidebar.vue', 'model/boards.ts'):
            text = (ROOT / 'web/src' / name).read_text()
            for word in words:
                self.assertIsNone(re.search(rf'["\'`]{re.escape(word)}["\'`]|\b{re.escape(word)}\b(?=\s*[:=])', text, re.I),
                                  f'{name} names {word}')

    def test_the_translations_have_no_text_per_board(self):
        for path in (ROOT / 'screen_manager/translations').glob('*.json'):
            installer = json.loads(path.read_text()).get('editor', {}).get('installer', {})
            for key in installer:
                self.assertFalse(any(board in key for board in profiles.CATALOG), f'{path.name}: editor.installer.{key}')


if __name__ == '__main__':
    unittest.main()
