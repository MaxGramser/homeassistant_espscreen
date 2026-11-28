"""Calibrate touch from the app (app 0.2.117).

A resistive panel reads a voltage off the film and has to be told what that voltage means in pixels; it runs its
wizard the first time it is switched on, and the screen's own settings page has a row to run it again. The panel
in the app offers the same thing, and it does it by pressing the screen's own Calibrate touch button in Home
Assistant, the one that row and this button share. Whether that button is on the device is also the whole answer
to "can this screen be calibrated": a capacitive panel has no button, no row and no card.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.append(str(ROOT / 'tools'))  # after the app: tools/i18n.py is not the app's i18n
from core import CALIBRATE_BUTTON, calibrate_entity  # noqa: E402
import profiles  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha

INBOX = 'text.screen'
BUTTON = {'entity_id': 'button.office_1_calibrate_touch', 'platform': 'esphome',
          'original_name': 'Calibrate touch', 'device_id': 'd1'}


class TheButtonOnTheDevice(unittest.TestCase):
    def test_it_is_named_as_the_board_profile_names_it(self):
        domain, name = CALIBRATE_BUTTON
        self.assertEqual(domain, 'button')
        # The wizard of a resistive panel brings the button (features/resistive-touch.yaml), and the CYD has one.
        board = profiles.text('checkout/cyd.yaml')
        self.assertIn(f'name: "{name}"', board)

    def test_it_is_found_on_the_device_that_has_it(self):
        self.assertEqual(calibrate_entity([BUTTON]), BUTTON['entity_id'])
        self.assertIsNone(calibrate_entity([]))
        # Not another integration's button of the same name, and not another domain's entity.
        self.assertIsNone(calibrate_entity([{**BUTTON, 'platform': 'hue'}]))
        self.assertIsNone(calibrate_entity([{**BUTTON, 'entity_id': 'switch.office_1_calibrate_touch'}]))


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class CalibrateFromTheApp(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, wizard=True, online=True):
        ha = fake_ha()
        if wizard:
            ha.registry.append(BUTTON)
        if not online:
            ha.states['text.screen'] = {'state': 'unavailable'}
            ha.states['sensor.fw'] = {'state': 'unavailable'}
        (Path(tmp) / 'screens.json').write_text(json.dumps({'version': 1, 'screens': {INBOX: {'title': 'Office', 'tiles': []}}}))
        return Manager(ha, Path(tmp) / 'screens.json')

    async def press(self, manager):
        async with TestClient(TestServer(create_app(manager, True))) as client:
            csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
            response = await client.post(f'/api/screens/{INBOX}/calibrate', headers={'X-Screen-CSRF': csrf})
            return response.status, await response.json()

    async def test_the_panel_offers_it_only_where_there_is_a_wizard(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            self.assertIs(manager.settings_view(manager.screen(INBOX))['calibrate'], True)
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, wizard=False)
            self.assertIs(manager.settings_view(manager.screen(INBOX))['calibrate'], False)

    async def test_pressing_it_presses_the_screen_s_own_button(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            status, body = await self.press(manager)
            self.assertEqual((status, body), (200, {'ok': True}))
            self.assertEqual(manager.ha.calls, [('button.press', {'entity_id': BUTTON['entity_id']})])

    async def test_a_panel_with_nothing_to_measure_is_told_so_and_nothing_is_pressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, wizard=False)
            status, body = await self.press(manager)
            self.assertEqual(status, 400)
            self.assertIn('nothing to measure', body['error'])
            self.assertEqual(manager.ha.calls, [])

    async def test_a_screen_that_is_off_shows_no_crosses_so_it_is_not_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp, online=False)
            status, body = await self.press(manager)
            self.assertEqual(status, 400)
            self.assertIn('offline', body['error'])
            self.assertEqual(manager.ha.calls, [])


if __name__ == '__main__':
    unittest.main()
