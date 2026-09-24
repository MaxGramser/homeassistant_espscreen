"""Live values on the mockup, Identify, the test alert and the changelog for the Update badge (app 0.2.73).

The editor asks /api/states for the tiles it shows and draws Home Assistant's values on the mockup; Identify and
Try it call a screen's own show_alert action, with the same field rules as an alert event; the full inventory
carries the CHANGELOG sections so the badge can say what a screen gets.
"""
import contextlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import changelog  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None

SAMPLE = '''## 0.2.74 (firmware 0.2.62)

A new editor.

- **One workspace.** Sidebar, pages, [library](docs/X.md) with `code`.
- Second line.

## 0.2.71 (firmware 0.2.60)

- **Slider stays.** Text.
'''


class Changelog(unittest.TestCase):
    def test_sections_carry_plain_bullet_lines(self):
        sections = changelog.parse(SAMPLE)
        self.assertEqual([(s['app'], s['firmware']) for s in sections], [('0.2.74', '0.2.62'), ('0.2.71', '0.2.60')])
        self.assertEqual(sections[0]['lines'], ['One workspace. Sidebar, pages, library with code.', 'Second line.'])
        self.assertEqual(changelog.parse(SAMPLE, limit=1)[0]['app'], '0.2.74')

    def test_italics_go_and_lone_asterisks_and_code_stay(self):
        # What's new showed "*Full page*" (app 0.2.78).
        self.assertEqual(changelog.plain('A size can be *Full page*: (*26.0 °C*, *Off*).'), 'A size can be Full page: (26.0 °C, Off).')
        self.assertEqual(changelog.plain('5 * 3 * 2, a*b*c, snake_case_name, camera.* or image.*'), '5 * 3 * 2, a*b*c, snake_case_name, camera.* or image.*')
        self.assertEqual(changelog.plain('**Bold** with `code *x*` and [a *link*](docs/X.md)'), 'Bold with code *x* and a link')

    def test_other_headings_star_bullets_and_wrapped_lines(self):
        text = '''# Changelog

## 0.2.80 (firmware 0.2.66)

Intro, not a bullet.

- **First.** It goes on
  on an indented line
and on a line right under it.
* A star bullet.
- Third.

  A second paragraph of the third one.

A paragraph after the list, not a bullet.

### Details

- Under a smaller heading, still this release.

## Unreleased

- Not in any release.

## 0.2.79 (firmware 0.2.65)

- Older.
'''
        sections = changelog.parse(text)
        self.assertEqual([s['app'] for s in sections], ['0.2.80', '0.2.79'])
        self.assertEqual(sections[0]['lines'], ['First. It goes on on an indented line and on a line right under it.', 'A star bullet.',
                                                'Third. A second paragraph of the third one.', 'Under a smaller heading, still this release.'])
        self.assertEqual(sections[1]['lines'], ['Older.'], 'a bullet under an unknown heading belongs to no release')

    def test_a_changelog_that_cant_be_read_leaves_the_notes_empty(self):
        # Updater() reads it when the app starts; a broken file must never stop the app (app 0.2.78).
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'CHANGELOG.md'
            folder.mkdir()
            latin = Path(tmp) / 'latin.md'
            latin.write_bytes('## 0.2.80 (firmware 0.2.66)\n\n- caf\xe9\n'.encode('latin-1'))
            for path in (folder, latin, Path(tmp) / 'missing.md'):
                with self.assertLogs('screen_manager', 'WARNING') if path.exists() else contextlib.nullcontext():
                    self.assertEqual(changelog.load(path), [], path)

    def test_the_real_changelog_is_found_and_shipped(self):
        sections = changelog.load()
        self.assertTrue(sections and sections[0]['lines'], 'CHANGELOG.md one folder up from the app')
        self.assertIn('COPY CHANGELOG.md /app/CHANGELOG.md', (ROOT / 'screen_manager/Dockerfile').read_text())


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Endpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import test_scaling
        from aiohttp.test_utils import TestClient, TestServer
        from server import Manager, create_app
        self.ha = test_scaling.fake_ha(firmware='0.2.60', node='office-1')
        self.ha.calls = []
        async def call(action, data):
            self.ha.calls.append((action, data))
        self.ha.call = call
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = Manager(self.ha, Path(self.tmp.name) / 'screens.json')
        self.client = TestClient(TestServer(create_app(self.manager, True)))
        await self.client.start_server()
        inventory = await (await self.client.get('/api/inventory')).json()
        self.csrf = inventory['csrf']
        self.screen = inventory['screens'][0]
        self.headers = {'X-Screen-CSRF': self.csrf}

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    async def test_states_give_the_value_word_and_attributes_per_entity(self):
        response = await self.client.get('/api/states?entity=light.a&entity=sensor.t&entity=light.nope&entity=screen.clock')
        states = (await response.json())['states']
        self.assertEqual(set(states), {'light.a', 'sensor.t'}, 'unknown entities and built-ins are left out')
        self.assertEqual(states['light.a']['state'], 'on')
        self.assertEqual(states['sensor.t']['state'], '21.5')
        self.assertEqual(states['sensor.t']['a']['unit_of_measurement'], '°C')
        self.assertIn('word', states['light.a'])

    async def test_firmware_preview_uses_device_packets_without_saving_or_actions(self):
        from core import validate_layout, Grid
        data = {'shape': {'width': 720, 'height': 720, 'columns': 2, 'rows': 3},
                'layout': {'title': 'Preview', 'pages': 2, 'tiles': [
                    {'entity': 'light.a', 'name': 'Desk', 'slot': 0, 'options': {'background': 'green'}},
                    {'entity': 'sensor.t', 'name': 'Temperature', 'slot': 6}]}}
        before = dict(self.manager.layouts)
        response = await self.client.post('/api/firmware-preview', json=data, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        messages = (await response.json())['messages']
        layout = validate_layout(data['layout'], grid=Grid(2, 3))
        self.assertEqual(messages[0], self.manager.layout_message('', layout, {'id': 'virtual.preview', 'shape': data['shape']}))
        self.assertEqual(messages[1], self.manager.header_message(layout))
        for i, tile in enumerate(layout['tiles']):
            self.assertEqual(messages[i + 2], await self.manager.tile_message(i, tile))
        self.assertEqual(self.manager.layouts, before)
        self.assertEqual(self.ha.calls, [])
        data['shape']['columns'] = 0
        response = await self.client.post('/api/firmware-preview', json=data, headers=self.headers)
        self.assertEqual(response.status, 400)

    async def test_preview_policy_allows_wasm_without_javascript_eval(self):
        response = await self.client.get('/')
        policy = response.headers['Content-Security-Policy']
        self.assertIn("script-src 'self' 'wasm-unsafe-eval'", policy)
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertNotIn("'unsafe-inline'", policy)

    async def test_preview_relays_entity_commands_and_returns_ha_errors(self):
        from server import Refused
        async def entity_actions(entity):
            return {'light.turn_on', 'light.turn_off'}
        self.ha.entity_actions = entity_actions
        command = {'service': 'light.turn_on', 'call_id': 42, 'event': False,
                   'data': {'entity_id': 'light.a', 'brightness': '180'}, 'templates': {}}
        response = await self.client.post('/api/firmware-preview/action', json=command, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual(await response.json(), {'success': True})
        self.assertEqual(self.ha.calls, [('light.turn_on', command['data'])])
        self.assertFalse(self.manager.layouts, 'commands never save a preview layout')

        async def refused(*args):
            raise Refused('The device rejected this value')
        self.ha.call = refused
        response = await self.client.post('/api/firmware-preview/action', json=command, headers=self.headers)
        self.assertEqual(response.status, 400)
        self.assertIn('The device rejected this value', (await response.json())['error'])

        async def disconnected(*args):
            raise ConnectionError()
        self.ha.call = disconnected
        response = await self.client.post('/api/firmware-preview/action', json=command, headers=self.headers)
        self.assertEqual(response.status, 503)

    async def test_preview_commands_require_csrf_and_an_action_for_an_existing_entity(self):
        async def entity_actions(entity):
            return {'light.turn_on'}
        self.ha.entity_actions = entity_actions
        command = {'service': 'light.turn_on', 'data': {'entity_id': 'light.a'}}
        response = await self.client.post('/api/firmware-preview/action', json=command)
        self.assertEqual(response.status, 403)
        for invalid in [None, {}, {**command, 'service': 'homeassistant.restart'},
                        {**command, 'data': {'entity_id': 'light.missing'}},
                        {**command, 'data': {'entity_id': ['light.a']}},
                        {**command, 'event': True}, {**command, 'templates': {'brightness': '{{ 1 }}'}}]:
            response = await self.client.post('/api/firmware-preview/action', json=invalid, headers=self.headers)
            self.assertEqual(response.status, 400, await response.text())
        self.assertEqual(self.ha.calls, [])

    async def test_identify_blinks_the_screen_through_its_alert_action(self):
        response = await self.client.post(f"/api/screens/{self.screen['id']}/identify", headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        (action, data), = self.ha.calls
        self.assertEqual(action, 'esphome.office_1_show_alert')
        self.assertEqual((data['title'], data['flash'], data['timeout'], data['icon']), (f"This is {self.screen['name']}", True, 8, 'bell-ring'))
        missing = await self.client.post('/api/screens/text.nope/identify', headers=self.headers)
        self.assertEqual(missing.status, 400)

    async def test_the_test_alert_reaches_one_screen_or_all_with_the_event_rules(self):
        body = {'screen': self.screen['id'], 'data': {'title': 'Door', 'timeout': 'soon', 'flash': 'yes'}}
        response = await self.client.post('/api/alerts/test', headers=self.headers, json=body)
        result = await response.json()
        self.assertEqual((response.status, result['sent'], result['unusable']), (200, 1, ['timeout']), result)
        action, data = self.ha.calls[-1]
        self.assertEqual(action, 'esphome.office_1_show_alert')
        self.assertEqual((data['title'], data['timeout'], data['flash'], data['subtitle']), ('Door', 0, True, ''))
        everyone = await self.client.post('/api/alerts/test', headers=self.headers, json={'screen': 'all', 'data': {'title': 'Hi'}})
        self.assertEqual(everyone.status, 200, await everyone.text())
        self.assertEqual((await everyone.json())['sent'], 1)
        self.assertEqual(len(self.ha.calls), 2)
        bad = await self.client.post('/api/alerts/test', headers=self.headers, json={'screen': 'text.nope'})
        self.assertEqual(bad.status, 400)

    async def test_home_assistant_saying_no_or_not_answering_is_a_sentence_not_a_500(self):
        # Identify and Try it answered a bare 500 with a traceback in the log (app 0.2.78).
        from server import Refused
        cases = ((Refused('Action esphome.office_1_show_alert not found'), 400,
                  "Home Assistant didn't take it: Action esphome.office_1_show_alert not found."),
                 (Refused(''), 400, "Home Assistant didn't take it: no reason given."),
                 (ConnectionError("Home Assistant isn't connected."), 503, "Home Assistant isn't reachable right now. Try again in a moment."),
                 (TimeoutError(), 503, "Home Assistant isn't reachable right now. Try again in a moment."))
        for error, status, sentence in cases:
            async def call(action, data, error=error):
                raise error
            self.ha.call = call
            for response in (await self.client.post(f"/api/screens/{self.screen['id']}/identify", headers=self.headers),
                             await self.client.post('/api/alerts/test', headers=self.headers,
                                                    json={'screen': self.screen['id'], 'data': {'title': 'Door'}})):
                self.assertEqual((response.status, await response.json()), (status, {'error': sentence}), repr(error))

    async def test_the_full_inventory_carries_the_changelog(self):
        # Only the full inventory (app 0.2.78): the live payload goes out every few seconds and needs no notes.
        inventory = await (await self.client.get('/api/inventory')).json()
        sections = inventory['changelog']
        self.assertTrue(sections)
        self.assertEqual(set(sections[0]), {'app', 'firmware', 'lines'})
        self.assertNotIn('changelog', inventory['updates'])
        light = await (await self.client.get('/api/inventory?light=1')).json()
        self.assertNotIn('changelog', light)
        self.assertNotIn('changelog', light['updates'])


class Editor(unittest.TestCase):
    """The page side of the same features, read from the Vue sources."""
    def setUp(self):
        import editor_sources
        self.store = editor_sources.source('store.ts')
        self.page = editor_sources.PAGE

    def test_the_mockup_polls_live_values_and_draws_them(self):
        self.assertIn('getJson(`states?${query}`)', self.store)
        self.assertIn('if (!document.hidden && state.layout && state.tab === "layout" && route.value === "") loadStates();', self.store)
        for marker in ('liveOf(props.tile.entity)', 'lit: isOn', ':style="sliderStyle"', "class=\"tog\" :class=\"{ off: !on }\""):
            self.assertIn(marker, self.page, marker)

    def test_identify_and_the_test_alert_have_their_buttons(self):
        self.assertIn('send(`screens/${encodeURIComponent(screen.id)}/identify`, "POST")', self.store)
        self.assertIn('send("alerts/test", "POST", { screen: target, data })', self.store)
        self.assertIn('id="identify"', self.page)
        self.assertIn('id="alerts-try"', self.page)
        self.assertIn('id="try-send"', self.page)

    def test_layouts_can_be_copied_exported_and_imported(self):
        for name in ('export function copyLayoutFrom', 'export function exportLayout', 'export function importLayout'):
            self.assertIn(name, self.store)
        for marker in ('id="copy-layout"', 'id="export-layout"', 'id="import-layout"', 'accept="application/json,.json"'):
            self.assertIn(marker, self.page, marker)
        self.assertIn('.slice(0, tileLimit.value)', self.store, 'an imported layout never exceeds the firmware limit')

    def test_the_library_filters_by_room_and_placement_and_the_palette_exists(self):
        for marker in ('id="room"', 'id="hide-placed"', 'id="open-palette"', 'id="palette-input"', "e.key.toLowerCase() === \"k\""):
            self.assertIn(marker, self.page, marker)

    def test_updates_show_their_notes_and_progress(self):
        self.assertIn('export function whatsNew', self.store)
        self.assertIn('export function updateProgress', self.store)
        for marker in ('class="whatsnew"', 'role="progressbar"', "go('#firmware')"):
            self.assertIn(marker, self.page, marker)

    def test_full_page_and_navigation_tiles_are_in_the_editor(self):
        import editor_sources
        layout = editor_sources.source('model/layout.ts')
        for marker in ('export const SIZES: Size[] = ["single", "wide", "full"];', 'export const pageTarget', 'versionAtLeast(firmware, "0.2.62") ? MAX_SLOTS'):
            self.assertIn(marker, layout, marker)
        drawer = editor_sources.component('TileInspector')
        for marker in ('["single", "wide", "full"]', 't("editor.tile.goes_to.label")', 'retargetPageTile(tile, Number(v))'):
            self.assertIn(marker, drawer, marker)
        self.assertEqual((editor_sources.text('tile.size.full'), editor_sources.text('tile.goes_to.label')), ('Full page', 'Goes to page'))
        self.assertIn(':class="{ wide, full, bare, placeholder: placeholder || !live, chosen }"', editor_sources.component('TileCard'))
        self.assertIn('"timer", "screen",', editor_sources.component('Library'))
        self.assertEqual(editor_sources.text('library.filters.screen'), 'Screen')


if __name__ == '__main__':
    unittest.main()
