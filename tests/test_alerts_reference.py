"""The Alerts cheatsheet in ESP Screens must describe exactly what the firmware compiles."""
import asyncio
import importlib.util
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
import tile_icons  # noqa: E402
from core import (ALERT_CHOICE_ORDER, ALERT_LIMITS, ALERT_MIN_FIRMWARE, FIRMWARE_VERSION, TILE_BACKGROUNDS, alert_reference,  # noqa: E402
                  alert_service)
from updates import parse_version  # noqa: E402

PROFILES = {'cyd': 'checkout/cyd.yaml', 'guition': 'checkout/guition.yaml'}
STATIC = ROOT / 'screen_manager/app/static'

class ReferenceTests(unittest.TestCase):
    def test_fields_and_limits_match_both_board_profiles(self):
        reference = alert_reference()
        for board, name in PROFILES.items():
            text = profiles.text(name)
            block = text.split('    - action: show_alert\n', 1)[1].split('    - action: show_alert_choice\n', 1)[0]
            self.assertEqual(re.findall(r'^        (\w+): (\w+)$', block, re.M), [(f['name'], f['type']) for f in reference['fields']], name)
            choice = text.split('    - action: show_alert_choice\n', 1)[1].split('    - action: dismiss_alert\n', 1)[0]
            order = [(f, t) for f, t in re.findall(r'^        (\w+): (\w+)$', choice, re.M)]
            self.assertEqual([f for f, _ in order], list(ALERT_CHOICE_ORDER), name)
            self.assertEqual({f: t for f, t in order if f in {c['name'] for c in reference['choice']['fields']}},
                             {c['name']: c['type'] for c in reference['choice']['fields']}, name)
            for needle in ('event: esphome.screen_alert', 'execute("replaced")', 'reason: "timeout"', 'reason: "remote"', 'reason: "ok"', 'reason: "button2"'):
                self.assertIn(needle, text, (name, needle))
        self.assertEqual(reference['event'], 'esphome.screen_alert')
        self.assertEqual([e['action'] for e in reference['endings']], ['ok', 'button2', 'timeout', 'replaced', 'remote'])
        self.assertEqual(reference['limits'], ALERT_LIMITS)

    def test_the_limits_are_the_looks_and_name_the_boards_of_each(self):
        # Bytes per field per look (ALERT_*_MAX in packages/looks/), with the catalog's names of the boards that have it.
        reference = alert_reference()
        for look in ('compact', 'standard'):
            text = (ROOT / f'packages/looks/{look}.yaml').read_text()
            for field, key in (('title', 'ALERT_TITLE_MAX'), ('subtitle', 'ALERT_SUBTITLE_MAX'), ('button_text', 'ALERT_BUTTON_MAX')):
                self.assertEqual(ALERT_LIMITS[look][field], int(re.search(rf'^  {key}: "(\d+)"', text, re.M)[1]), (look, field))
        self.assertEqual(reference['limit_boards']['compact'], ['CYD'])
        self.assertEqual(reference['limit_boards']['standard'], ['Guition', 'Waveshare'])

    def test_colours_icons_and_fallback_match_the_firmware_headers(self):
        reference = alert_reference()
        palette = (ROOT / 'components/smart_display/theme.h').read_text().split('SWATCHES[] = {', 1)[1].split('};', 1)[0]
        keys = (ROOT / 'components/smart_display/theme.h').read_text().split('KEY_SWATCHES[] = {', 1)[1].split('};', 1)[0]
        # A button's colour (firmware 0.3.3+) takes the same names as the card's.
        self.assertEqual(re.findall(r'\{"(\w+)", 0x', keys), [c['name'] for c in reference['colors']])
        self.assertEqual([c['name'] for c in reference['colors']], re.findall(r'\{"(\w+)", 0x[0-9A-F]{6}, 0x[0-9A-F]{6}\}', palette))
        for colour in reference['colors']:
            self.assertRegex(palette, rf'\{{"{colour["name"]}", 0x{colour["color"][1:]}, 0x[0-9A-F]{{6}}\}}')
            self.assertEqual(colour['label'], TILE_BACKGROUNDS[colour['name']]['label'])
        header = (ROOT / 'components/smart_display/alert_overlay.h').read_text()
        self.assertIn(f'FALLBACK_ICON = "{reference["fallback_icon"]}"', header)
        self.assertEqual(reference['fallback_cp'], tile_icons.GLYPHS[reference['fallback_icon']])
        for icon in reference['suggested_icons']:
            self.assertEqual(icon['cp'], tile_icons.GLYPHS[icon['name']], icon)
        self.assertEqual([(i['name'], i['cp']) for i in reference['extra_icons']], list(tile_icons.FIXED))
        self.assertEqual(len(reference['suggested_icons']), len({i['name'] for i in reference['suggested_icons']}))

    def test_action_names_follow_home_assistant_and_the_firmware_is_current(self):
        self.assertEqual(alert_service('studio-1'), 'esphome.studio_1_show_alert')
        self.assertEqual(alert_service('kitchen-screen', 'dismiss_alert'), 'esphome.kitchen_screen_dismiss_alert')
        for missing in (None, '', 3):
            self.assertIsNone(alert_service(missing))
        self.assertLessEqual(parse_version(ALERT_MIN_FIRMWARE), parse_version(FIRMWARE_VERSION))

    def test_page_carries_the_cheatsheet(self):
        import editor_sources
        html = editor_sources.PAGE
        for marker in ('id="open-alerts"', 'id="alerts-dialog"', 'id="close-alerts"', 'id="alerts-screens"', 'id="alerts-icons"', 'id="alerts-colors"', 'id="alerts-fields"', 'id="alerts-example"'):
            self.assertIn(marker, html, marker)
        for marker in ('inventory.alerts', 'alert_action', 'dismiss_action', 'AlertsView', 'go(\'#alerts\')'):
            self.assertIn(marker, editor_sources.SCRIPT, marker)
        self.assertIn('.alert-icon-grid', editor_sources.CSS)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager, create_app
    from aiohttp.test_utils import TestClient, TestServer

@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class InventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_carries_the_reference_and_each_screen_its_action_names(self):
        class HA:
            online = True
            registry = [{'entity_id': 'text.studio_1_tegelinstellingen', 'platform': 'esphome', 'original_name': 'Tegelinstellingen', 'device_id': 'd1'},
                        {'entity_id': 'sensor.studio_1_apparaatnaam', 'platform': 'esphome', 'original_name': 'Apparaatnaam', 'device_id': 'd1'},
                        {'entity_id': 'sensor.studio_1_schermfirmware', 'platform': 'esphome', 'original_name': 'Schermfirmware', 'device_id': 'd1'},
                        {'entity_id': 'text.oud_tegelinstellingen', 'platform': 'esphome', 'original_name': 'Tegelinstellingen', 'device_id': 'd2'}]
            devices = [{'id': 'd1', 'name': 'Studio 1'}, {'id': 'd2', 'name': 'Old screen'}]
            areas = []
            states = {'text.studio_1_tegelinstellingen': {'state': 'Ready'}, 'sensor.studio_1_apparaatnaam': {'state': 'studio-1'},
                      'sensor.studio_1_schermfirmware': {'state': '0.2.31'}, 'text.oud_tegelinstellingen': {'state': 'Ready'}}
            changed = asyncio.Event()
            async def send(self, inbox, message, action=None): pass
        with tempfile.TemporaryDirectory() as temp:
            manager = Manager(HA(), Path(temp) / 'screens.json')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                full = await (await client.get('/api/inventory')).json()
                self.assertEqual(full['alerts'], alert_reference())
                by_id = {s['id']: s for s in full['screens']}
                self.assertEqual(by_id['text.studio_1_tegelinstellingen']['alert_action'], 'esphome.studio_1_show_alert')
                self.assertEqual(by_id['text.studio_1_tegelinstellingen']['dismiss_action'], 'esphome.studio_1_dismiss_alert')
                self.assertIsNone(by_id['text.oud_tegelinstellingen']['alert_action'])
                light = await (await client.get('/api/inventory?light=1')).json()
                self.assertNotIn('alerts', light)
                self.assertEqual(light['screens'][0]['alert_action'], 'esphome.studio_1_show_alert')

if __name__ == '__main__':
    unittest.main()
