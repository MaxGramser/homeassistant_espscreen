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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import profiles  # noqa: E402
import core  # noqa: E402
import generate_cells  # noqa: E402
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

    def test_the_guitions_four_rows_bring_the_cards_they_need(self):
        # A Guition built with four rows (app 0.4.31, firmware 0.18.1): one line in the screen's YAML, and the board
        # file's cards follow it (cells/${GRID_CELLS}.yaml), as ESPHome works the path out when it builds.
        text = core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall', 'choices': {'GRID_ROWS': '4'}})
        self.assertIn('  GRID_ROWS: "4"', re.search(r'(?ms)^substitutions:\n(.*?)\n\n', text)[1].split('\n'))
        self.assertNotIn('GRID_ROWS', core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'}))
        board = profiles.BOARDS['guition']
        include = re.search(r'cells: !include (\S+)', board.read_text())[1]
        for rows, cards in (('3', 6), ('4', 8)):
            values = profiles.evaluate({**profiles.substitutions_of(board), 'GRID_ROWS': rows})
            path = (board.parent / profiles._render(include, values, strict=True)).resolve()
            self.assertEqual(path.name, f'{cards}.yaml')
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.read_text().count('runtime_tiles::bind('), cards)
        self.assertIn(8, generate_cells.counts())
        # Offline, the screen's own YAML says it has four rows: the app counts its cells on 2 x 4, not the catalog's 2 x 3.
        import firmware
        self.assertEqual(firmware.profile_meta(text)['grid_rows'], 4)
        self.assertIsNone(firmware.profile_meta(core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall'}))['grid_rows'])
        self.assertEqual(core.grid_of({'board': 'guition', 'grid_rows': 4}), core.Grid(2, 4))
        self.assertEqual(core.grid_of({'board': 'guition', 'grid_rows': None}), core.Grid(2, 3))
        # What the screen reports itself still wins.
        reported = {'width': 480, 'height': 480, 'columns': 2, 'rows': 3, 'dpi': 170, 'look': 'standard'}
        self.assertEqual(core.grid_of({'board': 'guition', 'grid_rows': 4, 'shape': reported}), core.Grid(2, 3))

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
