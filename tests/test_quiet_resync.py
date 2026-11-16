"""A colour slider on Studio 1 turned red on release (app 0.2.55, firmware 0.2.47).

An automation set a screen setting to the value it already had on every light change. The screen reported
it, ESP Screen Manager saved the layout and resent the whole screen, and the screen drew its whole page
again while a finger was on a slider. Touch input stalled, and the GT911's stray (0, 0) contact became
the finger's last position, so LVGL moved the slider to its end on release. Each link is checked here.
"""
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import validate_settings  # noqa: E402



@unittest.skipUnless(importlib.util.find_spec('aiohttp'), 'Run using .venv-portal/bin/python for server tests')
class SettingEvents(unittest.IsolatedAsyncioTestCase):
    async def run_loop_for(self, manager, seconds):
        task = asyncio.create_task(manager.run())
        await asyncio.sleep(seconds)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_a_setting_the_screen_already_has_is_not_saved_or_resent(self):
        import test_scaling
        from server import Manager
        with tempfile.TemporaryDirectory() as tmp:
            ha = test_scaling.fake_ha(firmware='0.2.47')
            ha.setting_events = []
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Studio', 'tiles': [{'entity': 'light.a', 'name': ''}],
                                   'settings': validate_settings({'standby_seconds': 86400})})
            ha.changed.set()
            await self.run_loop_for(m, 0.6)
            self.assertEqual([msg['op'] for _, msg, _ in ha.messages], ['layout', 'header', 'state'], 'first pass sends everything')
            ha.messages.clear()
            stored = m.store.get('text.screen')
            persisted = m.path.read_bytes()
            # An automation sets "Standby after" to 86400 on every light change; the screen reports it.
            ha.setting_events.append({'inbox': 'text.screen', 'key': 'standby_seconds', 'value': '86400'})
            ha.changed.set()
            await self.run_loop_for(m, 0.6)
            self.assertEqual(ha.messages, [], 'nothing changed: no resend of the whole screen')
            self.assertEqual(m.store.get('text.screen'), stored, 'and no saved revision change')
            self.assertEqual(m.path.read_bytes(), persisted, 'and no storage rewrite')
            self.assertEqual(ha.setting_events, [], 'the event is handled all the same')
            # A real change is kept (app 0.2.57), and not sent back: the screen has it already, and an echo that
            # arrives after the screen stepped further would undo that step (a held + on its settings page).
            rev = m.sent['text.screen']['rev']
            ha.setting_events.append({'inbox': 'text.screen', 'key': 'standby_seconds', 'value': '600'})
            ha.changed.set()
            await self.run_loop_for(m, 0.6)
            self.assertEqual(m.layouts['text.screen']['settings']['standby_seconds'], 600)
            self.assertEqual(ha.messages, [], 'nothing goes back to the screen')
            self.assertEqual(m.sent['text.screen']['layout']['settings']['standby_seconds'], 600, 'what the screen holds follows')
            self.assertEqual(m.sent['text.screen']['rev'], rev, 'the ping keeps the revision the screen has')
            # So is a brightness that pulls the standby brightness down with it.
            ha.setting_events.append({'inbox': 'text.screen', 'key': 'brightness', 'value': '10'})
            ha.changed.set()
            await self.run_loop_for(m, 0.6)
            settings = m.layouts['text.screen']['settings']
            self.assertEqual((settings['brightness'], settings['standby_brightness']), (10, 10))
            self.assertEqual(ha.messages, [])
            # The hourly repeat carries the kept values, so the screen and the stored layout agree.
            await m.sync_one('text.screen', m.layouts['text.screen'], force=True, screen=m.screen('text.screen'), dirty=set())
            layout = next(msg for _, msg, _ in ha.messages if msg['op'] == 'layout')
            self.assertEqual((layout['settings']['brightness'], layout['settings']['standby_seconds']), (10, 600))


class Firmware(unittest.TestCase):
    """Rules every board keeps for the links of this story. What the firmware does with them is proven by running it:
    a setting set to the value it has stores, applies and reports nothing (tests/test_settings_screen.cpp); a layout
    that comes again keeps a held finger's tap and the glass, and the GT911's stray (0, 0) is no swipe
    (web/wasm/test_quiet_resync.mjs); the ghost filter and the jump on release (tests/test_screen_input.cpp)."""
    TEXTS = {board: profiles.resolved(profile) for board, _, profile in profiles.BOARD_TABLE}

    def test_every_setting_entity_writes_through_settings_screen_set(self):
        # Every writer goes through settings_screen::set() (AGENTS.md, "Settings live in one table"), which stores,
        # applies and reports only a real change: Home Assistant setting the value a screen has is then nothing.
        for board, text in self.TEXTS.items():
            for key in ('brightness', 'standby_brightness', 'night_brightness', 'standby_seconds'):
                self.assertRegex(text, r'set_action:\s*- lambda:[^\n]*settings_screen::set\("%s"' % key,
                                 f'{board}: the {key} entity must set it through settings_screen::set')
            self.assertNotIn('runtime_tiles::setting_event("', text, f'{board}: a setting is reported through settings_screen::set only')

    def test_every_gt911_board_hides_its_stray_contact(self):
        # The GT911 reports a stray (0, 0) as the last sample before lift-off (measured on Studio 1). Every board with one
        # filters it before LVGL sees it, and hands every contact to the shared handler, which leaves (0, 0) out of the
        # edge swipe; the resistive XPT2046 boards (the CYD) have a filter of their own.
        for board, text in self.TEXTS.items():
            if 'platform: gt911' in text:
                for wiring in ('screen_input::ghost_touch.filter(', 'lv_indev_set_read_cb(indev, filtered);', 'runtime_tiles::touch_input::moved('):
                    self.assertIn(wiring, text, f'{board} has a GT911: filter its stray (0, 0) with screen_input::ghost_touch '
                                                f'and hand every contact to runtime_tiles::touch_input::moved')
            if 'platform: xpt2046' in text:
                self.assertNotIn('screen_input::ghost_touch', text, f'{board} has the resistive XPT2046, which has a filter of its own')


if __name__ == '__main__':
    unittest.main()
