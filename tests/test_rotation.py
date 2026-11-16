import re
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import profiles  # noqa: E402
import test_portal
from core import turns_of, validate_settings

class RotationTests(unittest.IsolatedAsyncioTestCase):
    def test_the_turns_a_screen_takes_follow_its_glass(self):
        # A half turn keeps the canvas and the grid, so any glass takes it; a quarter turn only a square one.
        self.assertEqual(turns_of({'width': 480, 'height': 480}), (0, 90, 180, 270))
        self.assertEqual(turns_of({'width': 800, 'height': 480}), (0, 180))
        self.assertEqual(turns_of({'width': 320, 'height': 240}), (0, 180))
        # A screen built standing up is glass that is not square either, so it takes the half turn and no more:
        # standing it down again is another build, not a setting (app 0.2.107).
        self.assertEqual(turns_of({'width': 480, 'height': 800}), (0, 180))
        self.assertEqual(turns_of({'width': 240, 'height': 320}), (0, 180))

    async def test_a_wide_screen_turns_upside_down_but_not_a_quarter(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_portal.ManagerTests().setup_manager(Path(tmp) / 'screens.json')
            # An 800 x 480 screen on firmware that turns (0.2.80), telling its own shape.
            m.ha.registry.append({'entity_id': 'sensor.fw', 'device_id': m.ha.registry[0].get('device_id'), 'platform': 'esphome', 'original_name': 'Screen firmware'})
            m.ha.states['sensor.fw'] = {'state': '0.2.80'}
            m.ha.registry.append({'entity_id': 'sensor.shape', 'device_id': m.ha.registry[0].get('device_id'), 'platform': 'esphome', 'original_name': 'Screen layout'})
            m.ha.states['sensor.shape'] = {'state': '800x480 3x3 217dpi standard'}
            m._screens_key = None
            screen = m.screen('text.screen')
            self.assertEqual(m.turns(screen), (0, 180))
            self.assertEqual(m.settings_view(screen)['rotations'], [0, 180])
            self.assertIn('rotation', m.settings_view(screen)['keys'])
            layout = {'title': 'Home', 'tiles': [{'entity': 'light.a'}], 'settings': {'rotation': 180}}
            m.save('text.screen', layout)
            self.assertEqual(m.layouts['text.screen']['settings']['rotation'], 180)
            with self.assertRaisesRegex(ValueError, 'square'):
                m.save('text.screen', {**layout, 'settings': {'rotation': 90}})
            # Firmware from before 0.2.80 on a board that is not a Guition turns not at all.
            m.ha.states['sensor.fw'] = {'state': '0.2.78'}
            m._screens_key = None
            with self.assertRaisesRegex(ValueError, '0.2.80'):
                m.save('text.screen', {**layout, 'settings': {'rotation': 180}})

    def test_only_quarter_turns(self):
        for angle in (0,90,180,270):
            self.assertEqual(validate_settings({'rotation':angle})['rotation'],angle)
        for angle in (-90,45,360,True,90.0,'90'):
            with self.assertRaises(ValueError):validate_settings({'rotation':angle})

    async def test_legacy_wire_and_saved_rotation_survive_old_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=test_portal.ManagerTests().setup_manager(Path(tmp)/'screens.json')
            layout={'title':'Home','tiles':[{'entity':'light.a'}],'settings':{'rotation':90}}
            with self.assertRaises(ValueError):m.save('text.screen',layout)
            m.ha.registry[0]['device_id']='guition'
            next(item for item in m.ha.registry if item.get('original_name') == 'Screen layout')['device_id'] = 'guition'
            m.ha.states[next(item['entity_id'] for item in m.ha.registry if item.get('original_name') == 'Screen layout')] = {'state': '480x480 2x3 170dpi standard'}
            m.ha.registry.append({'entity_id':'sensor.board','device_id':'guition','platform':'esphome','original_name':'Guition screen type'})
            # Capability stays discoverable with the panel offline or renamed.
            m.ha.states['sensor.board']={'state':'unavailable'}
            m.save('text.screen',layout)
            await m.sync_one('text.screen',m.layouts['text.screen'])
            wire=m.ha.messages[0][1]
            self.assertEqual(wire['rotation'],90)
            self.assertEqual(len(wire['settings']),11)
            self.assertNotIn('rotation',wire['settings'])
            m.save('text.screen',{'title':'Different','tiles':layout['tiles'],'settings':{'brightness':80}})
            self.assertEqual(m.layouts['text.screen']['settings']['rotation'],90)
            fresh=test_portal.ManagerTests().setup_manager(m.path)
            self.assertEqual(fresh.layouts['text.screen']['settings']['rotation'],90)


class EdgeBandTests(unittest.TestCase):
    """The band a page swipe starts in is a band of the glass, whatever the panel behind it.

    A board's DISPLAY_W is the canvas after LVGL's turn; ESPHome's touchscreen reports in the panel's own
    pixels. The firmware used to redo that turn itself from DISPLAY_W/DISPLAY_H, which is right on a square
    panel and on one that is not turned, and wrong on a portrait panel drawn in landscape: the 800 x 1280
    ten-inch Guition armed its right-hand band from x = 772 of 1280, so two fifths of the glass turned a page
    on any leftward drag and nothing turned back (firmware 0.2.82). ESPHome's own rotate_coordinates does the
    turn now, so the only number left here is the width of the glass.
    """

    ROOT = Path(__file__).resolve().parent.parent

    def test_every_board_gives_the_edge_swipe_only_its_own_two_bands(self):
        # The width of the glass is not a number in the board file any more (firmware 0.2.92+): the same file builds
        # a screen lying down and standing up, and only the firmware knows which one it became, so it reads the width
        # off the live canvas. What a board still says is how wide its bands are and how far a finger has to travel.
        #
        # The boards that ship (tools/profiles.py), not every file in the folder: a lab board is generated,
        # disposable and gitignored (docs/RESPONSIVE.md), so an old one on a developer's machine would fail a
        # check that CI, which has none of them, calls green. Every other generated-file check scopes this way.
        for board in sorted(profiles.BOARDS.values()):
            text = board.read_text()
            for call in re.findall(r'screen_input::edge_swipe\.configure\(([^)]*)\)', text):
                self.assertEqual(len(call.split(',')), 2, f'{board.name}: {call}')
                self.assertNotIn('DISPLAY_W', call, f'{board.name}: {call}')

    def test_the_shared_tree_turns_a_touch_with_esphomes_own_call(self):
        # Rule (AGENTS.md, "Touch and navigation"): a touch is turned once, by ESPHome's own call, never also by ours.
        core = (self.ROOT / 'packages' / 'core.yaml').read_text()
        self.assertIn('runtime_tiles::touch_input::to_screen', core, 'core.yaml hands every touch to touch_input::to_screen')
        self.assertIn('rotate_coordinates', core, "and turns it with ESPHome's rotate_coordinates")
        swipe = (self.ROOT / 'components' / 'smart_display' / 'screen_input.h').read_text()
        self.assertNotIn('rotation_', swipe, 'screen_input.h keeps no rotation of its own: the touch arrives turned')
        # The edge band is armed against the live canvas, not a number from the board file (firmware 0.2.92+): the
        # same preview build swipes at the right edge of 480 x 480, 720 x 720, 800 x 480 and 480 x 800 standing up
        # in web/wasm/test_runtime.mjs (tools/check.sh).
