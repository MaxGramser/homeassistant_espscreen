"""The shape a screen reports (firmware 0.2.80): "<width>x<height> <columns>x<rows>".

The add-on reads it from the screen's own diagnostic sensor, so the editor draws the glass and the cells of
the screen in front of it instead of guessing from the board it was built for. Firmware from before says
nothing, and then the two boards that shipped first decide.
"""
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import core


class Shape(unittest.TestCase):
    def test_a_screen_reports_its_canvas_and_its_grid(self):
        self.assertEqual(core.parse_shape('800x480 3x2'),
                         {'width': 800, 'height': 480, 'columns': 3, 'rows': 2})
        self.assertEqual(core.parse_shape(' 320x240 2x3 '),
                         {'width': 320, 'height': 240, 'columns': 2, 'rows': 3})
        # Since firmware 0.2.80 the density and the look follow, so a board this app never heard of still draws right.
        self.assertEqual(core.parse_shape('800x480 3x3 217dpi standard'),
                         {'width': 800, 'height': 480, 'columns': 3, 'rows': 3, 'dpi': 217, 'look': 'standard'})
        self.assertEqual(core.parse_shape('320x240 2x3 143dpi compact')['look'], 'compact')

    def test_anything_else_is_no_shape(self):
        for text in ('', None, 'unavailable', '800x480', '800 x 480 3x2', '0x0 2x3', '800x480 0x3',
                     '800x480 13x2', '800x480 9x9', '800x480 3x3 217 standard', '800x480 3x3 217dpi tiny'):
            self.assertIsNone(core.parse_shape(text), text)

    def test_a_screen_without_the_sensor_falls_back_to_its_board(self):
        # The board's own entry, lying down, which is how a board file builds a screen unless it is told otherwise.
        # The table of both orientations stays behind: it says something about the board, not about this screen.
        lying = lambda board: core.board_shape(core.SHAPES[board])
        self.assertEqual(core.shape_of({'board': 'guition'}), lying('guition'))
        self.assertEqual(core.shape_of({'board': 'unknown'}), lying('cyd'))
        self.assertEqual(core.shape_of({'board': 'guition', 'shape': None}), lying('guition'))
        self.assertEqual(core.shape_of({'board': 'unknown', 'package': 'packages/waveshare43.yaml'}), lying('waveshare43'))
        self.assertNotIn('orientations', core.shape_of({'board': 'guition'}))

    def test_what_the_screen_reports_wins_and_the_board_fills_in_the_rest(self):
        # The canvas and the grid are the screen's (it knows its rotation); the density, the look and the camera
        # sizes come from the board when the screen did not say them.
        reported = {'width': 480, 'height': 480, 'columns': 3, 'rows': 3}
        shape = core.shape_of({'board': 'guition', 'shape': reported})
        self.assertEqual((shape['columns'], shape['rows'], shape['dpi'], shape['look'], shape['board']), (3, 3, 170, 'standard', 'guition'))
        self.assertEqual(shape['camera'], core.SHAPES['guition']['camera'])
        told = core.shape_of({'board': 'unknown', 'shape': {**reported, 'dpi': 133, 'look': 'standard'}})
        self.assertEqual((told['dpi'], told['look'], told['width']), (133, 'standard', 480))

    def test_every_shape_holds_a_page_of_cells(self):
        for board, shape in core.SHAPES.items():
            for way in ('landscape', 'portrait'):
                side = core.board_shape(shape, way)
                self.assertLessEqual(side['columns'] * side['rows'], core.FIRMWARE_MAX_TILES, f'{board} {way}')
                self.assertGreaterEqual(min(side['width'], side['height']), 180, f'{board} {way}')
            self.assertIn(shape['look'], ('standard', 'compact'), board)

    def test_the_firmware_publishes_the_sensor_the_manager_reads(self):
        # Unchanged since firmware 0.2.80: the canvas, the grid, the density and the look. The canvas and the grid
        # are read off the display and the live grid, so a screen standing up reports its own numbers with no new
        # sensor and no new format for ESP Screens to learn.
        core_yaml = (ROOT / 'packages' / 'core.yaml').read_text()
        self.assertIn('name: "Screen layout"', core_yaml)
        self.assertIn('runtime_tiles::grid.columns', core_yaml)
        self.assertIn('lv_display_get_horizontal_resolution', core_yaml)
        self.assertIn('"%dx%d %dx%d %ddpi %s"', core_yaml)
        self.assertIn('Screen layout', str(core.NAME_SCREEN_LAYOUT))
        self.assertIn('Screen layout', core.SCREEN_ENTITY_NAMES)


if __name__ == '__main__':
    unittest.main()
