"""Which way a screen hangs (app 0.2.107): a build choice, not a setting.

Glass that is not square is two different screens. Lying down a Waveshare is 800 x 480 with nine cells a page;
standing up it is 480 x 800 with four, because a card keeps its size in millimetres. The canvas, the grid and every
size on it follow from the angle LVGL draws at, so the choice is made when the screen is built and lives in one
line of its profile: LVGL_ROTATION. A screen that is online reports the canvas and the grid it ended up with, in
the sensor it has had since firmware 0.2.80, so nothing on the wire changes; a screen that is offline is known by
the YAML of its own profile.

These checks cover the add-on's half: the board files reaching boards.json with both orientations, a shape, a grid
and the camera boxes per orientation, the line New screen writes, and the line an owner's own override may not
fight over.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import profiles  # noqa: E402
import core  # noqa: E402
import firmware as firmware_module  # noqa: E402
import generate_board_shapes  # noqa: E402
import camera_feed  # noqa: E402

# What each board becomes standing up, read off the board files as they ship. Written out here rather than
# computed, so a board file that quietly changes its panel or its portrait grid is noticed.
STANDING_UP = {'cyd': (240, 320, 1, 4, 180),
               'guition': (480, 480, 2, 3, 0),
               'waveshare43': (480, 800, 1, 4, 90),
               'jc8012p4a1': (800, 1280, 5, 5, 180),
               'waveshare7': (480, 800, 2, 7, 90),
               'waveshare4b': (480, 480, 2, 3, 0)}


class BoardShapes(unittest.TestCase):
    def test_boards_json_is_what_the_board_files_say(self):
        self.assertEqual(generate_board_shapes.main.__doc__, None)  # the generator writes; this only compares
        written = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        self.assertEqual(written, generate_board_shapes.shapes(), 'run tools/generate_board_shapes.py')

    def test_every_board_carries_both_ways_it_can_hang(self):
        for board, (width, height, columns, rows, rotation) in STANDING_UP.items():
            entry = core.SHAPES[board]
            lying, standing = entry['orientations']['landscape'], entry['orientations']['portrait']
            # The landscape numbers stay at the top level, so everything that only ever knew one shape per board
            # keeps reading the file it always read.
            self.assertEqual((entry['width'], entry['height'], entry['columns'], entry['rows']),
                             (lying['width'], lying['height'], lying['columns'], lying['rows']), board)
            self.assertEqual((standing['width'], standing['height'], standing['columns'], standing['rows'],
                              standing['rotation']), (width, height, columns, rows, rotation), board)
            # Standing up is the canvas on its side, and a quarter turn further than lying down, unless the glass
            # is square: then there is no second way to hang and both entries are the same build.
            if lying['width'] == lying['height']:
                self.assertEqual(lying, standing, board)
            else:
                self.assertEqual((standing['width'], standing['height']), (lying['height'], lying['width']), board)
                self.assertEqual(standing['rotation'], (lying['rotation'] + 90) % 360, board)

    def test_a_shape_is_the_way_the_screen_hangs(self):
        for board, (width, height, columns, rows, _) in STANDING_UP.items():
            shape = core.shape_of({'board': board, 'orientation': 'portrait'})
            self.assertEqual((shape['width'], shape['height'], shape['columns'], shape['rows']),
                             (width, height, columns, rows), board)
            # Everything that is the board and not the way it hangs travels along unchanged.
            self.assertEqual((shape['dpi'], shape['look'], shape['board']),
                             (core.SHAPES[board]['dpi'], core.SHAPES[board]['look'], board), board)
            self.assertEqual(core.grid_of({'board': board, 'orientation': 'portrait'}), core.Grid(columns, rows), board)
        # A word that is not one of the two, and no word at all, mean the board's own default: lying down.
        for said in (None, '', 'sideways', 90, {}):
            self.assertEqual(core.shape_of({'board': 'waveshare43', 'orientation': said})['columns'], 3, repr(said))
        # What an online screen reports still wins over all of it: it knows what it was built and turned into.
        told = core.shape_of({'board': 'waveshare43', 'orientation': 'portrait',
                              'shape': {'width': 800, 'height': 480, 'columns': 3, 'rows': 3}})
        self.assertEqual((told['width'], told['columns']), (800, 3))

    def test_the_angle_of_a_profile_says_which_way_it_hangs(self):
        # A half turn keeps the canvas, so both angles of a pair mean the same way up; the CYD lies down at 90.
        for angle, wanted in ((90, 'landscape'), (270, 'landscape'), (180, 'portrait'), (0, 'portrait'),
                              (None, 'landscape'), ('ninety', 'landscape')):
            self.assertEqual(core.orientation_at(core.SHAPES['cyd'], angle), wanted, angle)
        # Square glass hangs one way whatever the angle, and a board this app has never heard of lies down.
        self.assertEqual(core.orientation_at(core.SHAPES['guition'], 90), 'landscape')
        self.assertEqual(core.orientation_at({}, 180), 'landscape')


class CameraBoxes(unittest.TestCase):
    """A picture is shaped for the glass it lands on, so a board that draws them states a box per orientation."""

    def test_a_board_keeps_its_own_numbers_lying_down(self):
        # Lying down, the full view is the canvas features/camera.yaml states, and the still the frame the alert card
        # makes on that canvas (tests/test_alert_layout.py checks that one against the firmware).
        for board, path in sorted(profiles.BOARDS.items()):
            # What a screen of this board sees: features/camera.yaml's boxes, or none on a board without it.
            values = profiles.board_values(board)
            entry = core.SHAPES[board]
            if 'CAMERA_FULL_W' not in values:
                # A board with no camera has none either way up, and is refused a camera tile before it is saved.
                self.assertNotIn('camera', entry, board)
                for way in core.ORIENTATIONS:
                    self.assertNotIn('camera', entry['orientations'][way], f'{board} {way}')
                self.assertNotIn(board, camera_feed.BOXES, board)
                continue
            stated = {'full': [int(values['CAMERA_FULL_W']), int(values['CAMERA_FULL_H'])],
                      'thumb': entry['orientations']['landscape']['camera']['thumb']}
            self.assertEqual(entry['camera'], stated, board)
            self.assertEqual(entry['orientations']['landscape']['camera'], stated, board)
            self.assertEqual(camera_feed.BOXES[board], {view: tuple(box) for view, box in stated.items()}, board)

    def test_a_screen_standing_up_gets_a_picture_standing_up(self):
        for board, (width, height, *_) in STANDING_UP.items():
            entry = core.SHAPES[board]
            if 'camera' not in entry:
                continue
            self.assertEqual(entry['orientations']['portrait']['camera']['full'], [width, height], board)
        # The full view is the whole canvas, so it costs the screen the same pixels either way up.
        self.assertEqual(core.SHAPES['waveshare43']['orientations']['portrait']['camera']['full'], [480, 800])
        self.assertEqual(core.SHAPES['jc8012p4a1']['orientations']['portrait']['camera']['full'], [800, 1280])

    def test_the_still_of_an_alert_fits_the_card_that_screen_draws(self):
        # The firmware lays the alert card out on the glass it draws on (screen_alert::layout, firmware 0.2.103+) and
        # the frame for the still goes with it: the still must fit inside the card on that glass, either way up.
        for board, path in sorted(profiles.BOARDS.items()):
            entry = core.SHAPES[board]
            if 'camera' not in entry:
                continue
            for way in core.ORIENTATIONS:
                side = entry['orientations'][way]
                thumb_w, thumb_h = side['camera']['thumb']
                self.assertGreater(thumb_w, 0, f'{board} {way}')
                self.assertLessEqual(thumb_w, side['width'] - 2 * 14, f'{board} {way}: the still is wider than its card')
                self.assertLessEqual(thumb_h, side['height'] - 2 * 14, f'{board} {way}: the still is taller than its card')
        # Standing up, the 4.3-inch's 480 px of glass narrows the card; a 16:9 still is as wide as what is left.
        self.assertEqual(core.SHAPES['waveshare43']['orientations']['portrait']['camera']['thumb'], [386, 217])
        # The 10.1-inch standing up: the still keeps its size in millimetres, above the words.
        self.assertEqual(core.SHAPES['jc8012p4a1']['orientations']['portrait']['camera']['thumb'], [343, 193])

    def test_the_box_a_screen_is_served_follows_that_screen(self):
        lying = {'board': 'waveshare43'}
        standing = {'board': 'waveshare43', 'orientation': 'portrait'}
        self.assertEqual(camera_feed.box(lying, 'full'), (800, 480))
        self.assertEqual(camera_feed.box(standing, 'full'), (480, 800))
        self.assertEqual(camera_feed.box(standing, 'thumb'), (386, 217))
        # What an online screen reports decides too, whatever its profile says: the canvas it names is one of its
        # board's two, and a screen flashed by hand has no profile here to be read.
        online = {'board': 'waveshare43', 'shape': {'width': 480, 'height': 800, 'columns': 1, 'rows': 4}}
        self.assertEqual(camera_feed.box(online, 'full'), (480, 800))
        self.assertEqual(camera_feed.box({**online, 'orientation': 'landscape'}, 'full'), (480, 800))
        # A board that draws no pictures has no box either way up, and nothing else changes for it.
        for screen in ({'board': 'cyd'}, {'board': 'cyd', 'orientation': 'portrait'}):
            self.assertIsNone(camera_feed.box(screen, 'full'), screen)
            self.assertIsNone(camera_feed.boxes(screen), screen)
        # Square glass is served the same picture whichever word it is given.
        self.assertEqual(camera_feed.box({'board': 'guition'}, 'thumb'),
                         camera_feed.box({'board': 'guition', 'orientation': 'portrait'}, 'thumb'))


class NewScreen(unittest.TestCase):
    def profile(self, **extra):
        return core.installation_yaml({'board': 'waveshare43', 'name': 'hall', 'friendly_name': 'Hall', **extra})

    def test_only_a_screen_standing_up_gets_the_line(self):
        # The board file already lays its panel down, so a screen lying down is the profile it always was: no line,
        # and nothing in the file to go stale when the board file's own angle changes.
        self.assertNotIn('LVGL_ROTATION', self.profile())
        self.assertNotIn('LVGL_ROTATION', self.profile(orientation='landscape'))
        # Standing up is the board's own portrait angle, quoted: ESPHome takes substitutions as text.
        self.assertIn('\n  LVGL_ROTATION: "90"\n', self.profile(orientation='portrait'))
        self.assertIn('\n  LVGL_ROTATION: "180"\n',
                      core.installation_yaml({'board': 'cyd', 'name': 'hall', 'friendly_name': 'Hall',
                                              'orientation': 'portrait'}))
        # Square glass has nothing to choose: asking for it standing up builds the screen it already was.
        square = core.installation_yaml({'board': 'guition', 'name': 'hall', 'friendly_name': 'Hall',
                                         'orientation': 'portrait'})
        self.assertNotIn('LVGL_ROTATION', square)
        # The rest of the profile is untouched by the choice: one line more and nothing else moved. (Every profile
        # gets its own keys, so the lines that carry a secret are compared by their name and not their value.)
        shape = lambda text: [line.split(':')[0] for line in text.splitlines()]
        self.assertEqual([line for line in shape(self.profile(orientation='portrait')) if 'LVGL_ROTATION' not in line],
                         shape(self.profile()))

    def test_anything_but_the_two_words_is_refused(self):
        for said in ('sideways', 'Portrait', '', 90, True, None, ['portrait']):
            with self.assertRaises(ValueError, msg=repr(said)):
                self.profile(orientation=said)


class ExistingScreen(unittest.TestCase):
    """A profile that is already in the ESPHome folder: read back, rewritten, and defended from an override."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.firmware = firmware_module.Firmware(self.tmp.name, Path(self.tmp.name) / 'data')

    def write(self, name='hall.yaml', **extra):
        path = Path(self.tmp.name) / name
        path.write_text(core.installation_yaml({'board': 'waveshare43', 'name': path.stem,
                                                'friendly_name': 'Hall', **extra}))
        return path

    def test_a_profile_says_the_angle_it_was_built_at(self):
        self.assertIsNone(firmware_module.profile_meta(self.write().read_text())['rotation'])
        meta = firmware_module.profile_meta(self.write(name='tall.yaml', orientation='portrait').read_text())
        self.assertEqual((meta['rotation'], meta['package']), (90, 'packages/waveshare43.yaml'))
        self.assertEqual(core.orientation_at(core.SHAPES['waveshare43'], meta['rotation']), 'portrait')

    def test_a_rebuild_can_stand_a_screen_up_and_lay_it_down_again(self):
        self.write()
        self.assertTrue(self.firmware.set_orientation('hall.yaml', 'portrait'))
        self.assertIn('\n  LVGL_ROTATION: "90"\n', (Path(self.tmp.name) / 'hall.yaml').read_text())
        # Twice is once: the line is written only when it is not already what it should be.
        self.assertFalse(self.firmware.set_orientation('hall.yaml', 'portrait'))
        self.assertTrue(self.firmware.set_orientation('hall.yaml', 'landscape'))
        self.assertIn('\n  LVGL_ROTATION: "0"\n', (Path(self.tmp.name) / 'hall.yaml').read_text())
        # A profile that never had the line and is asked to lie down needs no line at all.
        self.write(name='other.yaml')
        self.assertFalse(self.firmware.set_orientation('other.yaml', 'landscape'))
        self.assertNotIn('LVGL_ROTATION', (Path(self.tmp.name) / 'other.yaml').read_text())
        # Square glass, and a word that is not one of the two, change nothing and say so.
        self.write(name='square.yaml')
        (Path(self.tmp.name) / 'square.yaml').write_text(
            core.installation_yaml({'board': 'guition', 'name': 'square', 'friendly_name': 'Square'}))
        self.assertFalse(self.firmware.set_orientation('square.yaml', 'portrait'))
        self.assertFalse(self.firmware.set_orientation('hall.yaml', 'sideways'))
        # And the language still travels in its own line, next to this one.
        self.assertTrue(self.firmware.set_language('hall.yaml', 'nl'))
        text = (Path(self.tmp.name) / 'hall.yaml').read_text()
        self.assertIn('LANGUAGE: "nl"', text)
        self.assertIn('LVGL_ROTATION: "0"', text)

    def test_an_override_is_told_where_the_choice_lives(self):
        self.write()
        with self.assertRaises(ValueError) as refused:
            self.firmware.save_override('hall.yaml', 'substitutions:\n  LVGL_ROTATION: "90"\n')
        # Not the general "these stay managed" sentence: people were told to override display settings, so the
        # message has to name the route instead (New screen, and a rebuild).
        self.assertNotIn('These substitutions', str(refused.exception))
        self.assertIn('New screen', str(refused.exception))
        # Everything else about a display an owner writes is still theirs.
        saved = self.firmware.save_override('hall.yaml', 'display:\n  - id: !extend screen_display\n    update_interval: 1s\n')
        self.assertTrue(saved['attached'])


if __name__ == '__main__':
    unittest.main()
