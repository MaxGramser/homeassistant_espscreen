"""The settings page on the screen itself (app 0.2.52, firmware 0.2.44).

Two halves have to agree without ever seeing each other: the row table in settings_screen.h writes keys
that only mean something if ESP Screens knows them, and the eleven-key `settings` block older firmware
insists on may never grow. Both are checked here, against the real files.
"""
from firmware_sources import runtime_source
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import test_portal
from core import (BUILTIN, SETTING_RULES, SETTINGS_BESIDE_BLOCK, entity_id, min_firmware, validate_layout,
                  validate_settings)

SCREEN = (ROOT / 'components/smart_display/settings_screen.h').read_text()
RUNTIME = runtime_source()
CORE = (ROOT / 'packages/core.yaml').read_text()
# The keys the firmware's own block still carries; everything newer travels as its own key.
FROZEN = {'standby_enabled', 'standby_seconds', 'brightness', 'standby_brightness', 'night_enabled',
          'night_start', 'night_end', 'night_brightness', 'show_clock', 'clock_24h', 'home_on_standby'}
assert FROZEN == set(SETTING_RULES) - set(SETTINGS_BESIDE_BLOCK)


class SettingsPage(unittest.TestCase):
    def test_every_key_the_screen_reports_is_a_setting_the_app_knows(self):
        # Rows write through set(key, value) (firmware 0.2.49+), which reports the key it was given.
        rows = set(re.findall(r'\bset\("(\w+)"', SCREEN))
        self.assertTrue(rows, 'no rows found in settings_screen.h')
        self.assertLessEqual(rows, set(SETTING_RULES), 'the screen writes a key ESP Screens would drop')
        handled = set(re.findall(r'key == "(\w+)"', SCREEN))
        self.assertLessEqual(rows, handled, 'a row writes a key set() does not handle')
        self.assertEqual(handled, set(SETTING_RULES) - {'show_clock'}, 'set() handles every setting the app knows')

    def test_the_frozen_settings_block_keeps_exactly_eleven_keys(self):
        # Firmware before 0.2.44 refuses a `settings` object of any other size; that is why the newer
        # settings travel as their own keys.
        self.assertEqual(len(FROZEN), 11)
        self.assertNotIn('parse_settings(', RUNTIME, 'new firmware has no legacy settings decoder')
        self.assertEqual(FROZEN, set(SETTING_RULES) & FROZEN)

    def test_new_settings_default_and_validate(self):
        clean = validate_settings({})
        self.assertEqual(clean['auto_home'], True)
        self.assertEqual(clean['auto_home_seconds'], 120)
        self.assertEqual(validate_settings({'auto_home_seconds': 30})['auto_home_seconds'], 30)
        for bad in ({'auto_home_seconds': 29}, {'auto_home_seconds': 3601}, {'auto_home': 1},
                    {'auto_home_seconds': True}):
            with self.assertRaises(ValueError):
                validate_settings(bad)

    def test_the_settings_tile_is_a_builtin_that_needs_new_firmware(self):
        self.assertIn('screen.settings', BUILTIN)
        self.assertTrue(entity_id('screen.settings'))
        self.assertEqual(min_firmware({'tiles': [{'entity': 'screen.settings'}]}), (0, 2, 44))
        self.assertLess(min_firmware({'tiles': [{'entity': 'screen.clock'}]}), (0, 2, 44))
        layout = validate_layout({'title': 'Home', 'tiles': [{'entity': 'screen.settings', 'name': 'Settings'}]})
        self.assertEqual(layout['tiles'][0]['entity'], 'screen.settings')


@unittest.skipUnless(importlib.util.find_spec('aiohttp'), 'Run using .venv-portal/bin/python for server tests')
class LayoutMessage(unittest.IsolatedAsyncioTestCase):
    async def test_the_new_keys_ride_beside_the_frozen_block(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = test_portal.ManagerTests().setup_manager(Path(temp) / 'screens.json')
            layout = {'title': 'Home', 'tiles': [{'entity': 'light.a'}],
                      'settings': validate_settings({'auto_home': False, 'auto_home_seconds': 600})}
            manager.save('text.screen', layout)
            message = manager.layout_message('text.screen', manager.layouts['text.screen'], {})
            self.assertEqual(set(message['settings']), FROZEN, 'older firmware refuses any other size')
            self.assertEqual(message['auto_home'], False)
            self.assertEqual(message['auto_home_seconds'], 600)
            # A screen that never stored settings still gets the defaults, not a missing key.
            plain = manager.layout_message('text.screen', {**manager.layouts['text.screen'],
                                                           'settings': validate_settings({})}, {})
            self.assertEqual((plain['auto_home'], plain['auto_home_seconds']), (True, 120))
            self.assertLess(len(json.dumps(message)), 4096, 'the screen refuses a message over 4 KB')


class Firmware(unittest.TestCase):
    """The board profiles have to carry the page, its way in, and the timer that closes it."""

    def setUp(self):
        self.profiles = {name: profiles.text(name)
                         for name in ('checkout/cyd.yaml', 'checkout/guition.yaml')}

    def test_both_boards_wire_the_page_and_its_gesture(self):
        for name, text in self.profiles.items():
            self.assertIn('settings_screen::attach_hold', text, name)
            self.assertIn('settings_screen::report', text, name)
            self.assertIn('settings_screen::may_open', text, name)
            self.assertIn('- action: open_settings', text, name)
            self.assertIn('- id: go_home', text, name)
            self.assertIn('runtime_tiles::auto_home', text, name)
            version = re.search(r'SCREEN_FIRMWARE_VERSION: "([0-9.]+)"', text)[1]
            self.assertGreaterEqual(tuple(map(int, version.split('.'))), (0, 2, 44), name)

    def test_the_hold_strip_covers_the_top_bar_and_no_more(self):
        """The strip is as wide as the glass less the band it starts in on each side, measured on the live canvas
        (overlay_card::screen_width), so it is right whichever way the screen was built to hang."""
        self.assertIn('overlay_card::screen_width() - ${SETTINGS_HOLD_X} * 2, ${SCROLL_Y}', CORE)
        for name, text in self.profiles.items():
            values = profiles.substitutions(name)
            # The narrowest canvas this board can be built with: the shorter side of its panel.
            width, scroll = min(int(values['PANEL_W']), int(values['PANEL_H'])), int(values['SCROLL_Y'])
            x = int(values['SETTINGS_HOLD_X'])
            self.assertGreater(width - 2 * x, 0, f'{name}: the two bands leave no strip')
            self.assertGreater(scroll, 20, name)
            # The page swipe owns both side bands; the hold may not start there. Resistive glass has only the bands
            # along the top and the bottom (firmware 0.28.0+) and turns its pages by a flick anywhere: its hold keeps
            # the whole strip.
            if 'EDGE_SWIPE_BAND_PX' in values and 'without_sides()' not in values.get('BOOT_TOUCH', ''):
                self.assertGreaterEqual(x, int(values['EDGE_SWIPE_BAND_PX']), name)

    def test_the_hold_strip_lies_under_every_card(self):
        # Firmware 0.2.44-0.2.47 created the strip after the cards, so it lay on top of them: a card's
        # back button and its action at the top right lost their taps to it. (The wake overlay of a dimmed
        # screen was not affected: apply_screen_settings moves it to the foreground.)
        self.assertIn('lv_obj_move_to_index(hold_area, lv_obj_get_index(below));', SCREEN)
        # Every card is made in C++ since app 0.4.86 (the colour card was the last one in YAML): each is made the
        # first time it opens and comes to the front when it does, so the strip made at boot lies under all of them.
        for root in ('detail_root', 'colour_root'):
            self.assertIn(f'lv_obj_move_foreground({root});', RUNTIME, root)
        for name, text in self.profiles.items():
            call = re.search(r'settings_screen::attach_hold\(id\(home_page\)->obj, [^;]*\);', text)
            self.assertTrue(call, f'{name}: the hold strip is attached')
            self.assertNotIn('color_detail_overlay', text, name)
            page = text[text.index('- id: home_page'):]
            self.assertLess(page.index('id: page_next\n'), page.index('id: dim_wake_overlay\n'), f'{name}: the page controls stay under the wake overlay')


if __name__ == '__main__':
    unittest.main()
