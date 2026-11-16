"""The Alerts cheatsheet in ESP Screens must describe exactly what the firmware compiles.

The add-on's alert_reference() is compared with the firmware it describes: the actions' fields as the parsed packages
declare them, the limits as the looks set them, and the colours, the fallback icon and the longest timeout as a little
program over the firmware's own headers prints them. The endings the screen reports are tests/test_alert.py's.
What the editor shows of the reference is web/tests/alerts-cheatsheet.spec.ts, which mounts the Alerts page with
tests/fixtures/alert-reference.json; this test keeps that fixture equal to alert_reference(). Write it again with
`python3 tests/test_alerts_reference.py --write`."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import package_yaml  # noqa: E402
import tile_icons  # noqa: E402
from core import (ALERT_CHOICE_ORDER, ALERT_ENDINGS, ALERT_LIMITS, ALERT_MAX_TIMEOUT, ALERT_MIN_FIRMWARE, FIRMWARE_VERSION,  # noqa: E402
                  TILE_BACKGROUNDS, alert_reference, alert_service)
from updates import parse_version  # noqa: E402

FIXTURE = ROOT / 'tests/fixtures/alert-reference.json'


def firmware_facts():
    """What the firmware's headers hold for an alert, as compiled: the card colours (theme::SWATCHES, name and light
    value), the button colours (theme::KEY_SWATCHES), screen_alert::FALLBACK_ICON and MAX_TIMEOUT_SECONDS. None without a
    C++ compiler."""
    compiler = shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++')
    if not compiler:
        return None
    source = r'''#include "screen_text_en.h"
#define THEME_TEST
#include "components/smart_display/alert_overlay.h"
#include <cstdio>
int main() {
  std::printf("{\"swatches\": [");
  bool first = true;
  for (const auto &s : theme::SWATCHES) { std::printf("%s[\"%s\", \"#%06X\"]", first ? "" : ", ", s.name, (unsigned) s.light); first = false; }
  std::printf("], \"keys\": [");
  first = true;
  for (const auto &k : theme::KEY_SWATCHES) { std::printf("%s\"%s\"", first ? "" : ", ", k.name); first = false; }
  std::printf("], \"fallback_icon\": \"%s\", \"max_timeout\": %d}\n", screen_alert::FALLBACK_ICON, screen_alert::MAX_TIMEOUT_SECONDS);
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'facts.cpp'
        path.write_text(source)
        subprocess.run([compiler, '-std=c++17', f'-I{ROOT}', f'-I{ROOT / "tests"}', str(path), '-o', str(Path(tmp) / 'facts')],
                       check=True)
        return json.loads(subprocess.run([str(Path(tmp) / 'facts')], check=True, capture_output=True, text=True).stdout)


def fixture_text():
    return json.dumps(alert_reference(), indent=1, ensure_ascii=False) + '\n'


class ReferenceTests(unittest.TestCase):
    def test_the_fields_are_the_actions(self):
        reference = alert_reference()
        actions = package_yaml.actions()
        self.assertEqual(list(actions['show_alert']['variables'].items()), [(f['name'], f['type']) for f in reference['fields']],
                         'the cheatsheet\'s fields are show_alert\'s in packages/core.yaml, by name, type and order: change both')
        choice = actions['show_alert_choice']['variables']
        self.assertEqual(list(choice), list(ALERT_CHOICE_ORDER), 'core.ALERT_CHOICE_ORDER is show_alert_choice\'s order')
        self.assertEqual({f['name']: choice[f['name']] for f in reference['choice']['fields']},
                         {f['name']: f['type'] for f in reference['choice']['fields']},
                         'the second button\'s fields have show_alert_choice\'s types')
        self.assertEqual(reference['event'], 'esphome.screen_alert')
        self.assertEqual([e['action'] for e in reference['endings']], [ending for ending, _ in ALERT_ENDINGS])
        self.assertEqual(reference['limits'], ALERT_LIMITS)

    def test_the_limits_are_the_looks_and_name_the_boards_of_each(self):
        # Bytes per field per look (ALERT_*_MAX in packages/looks/), with the catalog's names of the boards that have it.
        reference = alert_reference()
        for look in ('compact', 'standard'):
            values = profiles.substitutions_of(ROOT / f'packages/looks/{look}.yaml')
            for field, key in (('title', 'ALERT_TITLE_MAX'), ('subtitle', 'ALERT_SUBTITLE_MAX'), ('button_text', 'ALERT_BUTTON_MAX')):
                self.assertEqual(ALERT_LIMITS[look][field], int(values[key]),
                                 f'core.ALERT_LIMITS[{look!r}][{field!r}] is the {look} look\'s {key}: change both')
        self.assertEqual(reference['limit_boards']['compact'], ['CYD', 'Hosyond'])
        self.assertEqual(reference['limit_boards']['standard'], ['Guition', 'Waveshare', 'Sunton', 'M5Stack Tab5', 'reTerminal D1001', 'CrowPanel', 'SenseCAP', 'Freenove', 'WT32'])

    def test_colours_icons_and_the_timeout_are_the_firmwares(self):
        facts = firmware_facts()
        if facts is None:
            self.skipTest('no C++ compiler')
        reference = alert_reference()
        self.assertEqual([[c['name'], c['color'].upper()] for c in reference['colors']], facts['swatches'],
                         'the cheatsheet\'s card colours are theme::SWATCHES, by name and light value, in its order')
        # A button's colour (firmware 0.3.3+) takes the same names as the card's.
        self.assertEqual(facts['keys'], [c['name'] for c in reference['colors']], 'theme::KEY_SWATCHES has the card colours\' names')
        for colour in reference['colors']:
            self.assertEqual(colour['label'], TILE_BACKGROUNDS[colour['name']]['label'])
        self.assertEqual(facts['fallback_icon'], reference['fallback_icon'], 'screen_alert::FALLBACK_ICON is the cheatsheet\'s')
        self.assertEqual(facts['max_timeout'], ALERT_MAX_TIMEOUT, 'screen_alert::MAX_TIMEOUT_SECONDS is core.ALERT_MAX_TIMEOUT')
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

    def test_the_editors_fixture_is_the_reference(self):
        # The editor's test of the page (web/tests/alerts-cheatsheet.spec.ts) mounts it with this reference.
        self.assertEqual(FIXTURE.read_text() if FIXTURE.exists() else '', fixture_text(),
                         'tests/fixtures/alert-reference.json is alert_reference(): write it again with '
                         '`python3 tests/test_alerts_reference.py --write` and run web/tests/alerts-cheatsheet.spec.ts')


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
    if '--write' in sys.argv:
        FIXTURE.write_text(fixture_text())
        print(f'wrote {FIXTURE.relative_to(ROOT)}')
    else:
        unittest.main()
