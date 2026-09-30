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
        self.assertEqual(sections[0]['boards'], [])

    def test_a_firmware_for_some_boards_names_them(self):
        """A fix for one board alone (app 0.3.21): `(firmware x for <board>, <board>)` with the keys of boards.yaml."""
        text = '## 0.3.21 (firmware 0.3.11 for waveshare4b, cyd)\n\n- Fix.\n\n## 0.3.20 (firmware 0.3.10 for waveshare4b)\n\n- Fix.\n'
        sections = changelog.parse(text)
        self.assertEqual([(s['firmware'], s['boards']) for s in sections],
                         [('0.3.11', ['waveshare4b', 'cyd']), ('0.3.10', ['waveshare4b'])])

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

    async def test_media_preview_hides_source_urls_and_preserves_image_proportions(self):
        import io
        from PIL import Image
        from unittest.mock import AsyncMock
        attributes = {'media_title': 'A track', 'media_artist': 'An artist',
                      'entity_picture': '/api/media/artwork?token=private', 'access_token': 'private'}
        self.ha.states['media_player.test'] = {'state': 'playing', 'attributes': attributes}
        response = await self.client.get('/api/states?entity=media_player.test')
        result = await response.json()
        self.assertEqual(response.status, 200)
        self.assertNotIn('private', str(result))
        self.assertEqual(result['states']['media_player.test']['a']['media_title'], 'A track')
        self.assertEqual(len(result['states']['media_player.test']['a']['artwork_mark']), 10)
        source = io.BytesIO()
        Image.new('RGB', (1200, 600), (80, 130, 210)).save(source, 'JPEG')
        self.manager.camera.picture = lambda entity: attributes['entity_picture']
        self.manager.camera.fetch_cover = AsyncMock(return_value=source.getvalue())
        response = await self.client.get('/api/media-art?entity=media_player.test')
        self.assertEqual(response.status, 200)
        tag = response.headers['ETag']
        with Image.open(io.BytesIO(await response.read())) as image:
            self.assertEqual(image.size, (512, 256))
        response = await self.client.get('/api/media-art?entity=media_player.test', headers={'If-None-Match': tag})
        self.assertEqual(response.status, 304)
        self.assertEqual((await self.client.get('/api/media-art?entity=light.a')).status, 404)
        self.assertEqual((await self.client.get('/api/media-art?entity=media_player.unknown')).status, 404)
        # A camera that fills a taller tile on the mockup (app 0.3.8): prepared pixels too, never a camera URL.
        self.ha.states['camera.garden'] = {'state': 'idle', 'attributes': {'access_token': 'private', 'entity_picture': '/api/camera_proxy/camera.garden?token=private'}}
        self.manager.camera.fetch = AsyncMock(return_value=source.getvalue())
        response = await self.client.get('/api/camera-preview?entity=camera.garden')
        self.assertEqual(response.status, 200)
        with Image.open(io.BytesIO(await response.read())) as image:
            self.assertEqual(image.size, (512, 256))
        self.assertEqual((await self.client.get('/api/camera-preview?entity=media_player.test')).status, 404)
        self.assertEqual((await self.client.get('/api/camera-preview?entity=camera.unknown')).status, 404)

    async def test_firmware_preview_stream_follows_only_its_entities_and_cleans_up(self):
        import asyncio
        from preview_events import Changes
        self.ha.state_events = Changes()
        response = await self.client.get('/api/firmware-preview/events?entity=media_player.test&entity=sensor.t')
        self.assertEqual(response.status, 200)
        self.assertIn('text/event-stream', response.headers['Content-Type'])
        async def event():
            return await asyncio.wait_for(response.content.readuntil(b'\n\n'), 1)
        self.assertEqual(await event(), b'data: {}\n\n', 'initial and reconnect invalidation, no raw HA data')
        pending = asyncio.create_task(event())
        self.ha.state_events.notify('light.other')
        await asyncio.sleep(.02)
        self.assertFalse(pending.done(), 'unrelated entities must not rebuild the preview')
        self.ha.state_events.notify('media_player.test')
        self.assertEqual(await pending, b'data: {}\n\n')
        self.ha.state_events.notify('sensor.t')
        self.assertEqual(await event(), b'data: {}\n\n', 'top-bar entities also wake the preview')
        self.ha.state_events.notify()
        self.assertEqual(await event(), b'data: {}\n\n', 'HA reconnect refreshes every subscriber')
        response.close()
        for _ in range(30):
            self.ha.state_events.notify()
            await asyncio.sleep(.01)
            if not self.ha.state_events.listeners: break
        self.assertFalse(self.ha.state_events.listeners)
        self.assertEqual(self.ha.calls, [])
        for query in ('', '?entity=bad', '?' + '&'.join(['entity=light.a'] * 129)):
            self.assertEqual((await self.client.get('/api/firmware-preview/events' + query)).status, 400)

    async def test_ha_changes_wake_unsaved_previews_outside_physical_screen_filter(self):
        import asyncio
        from types import SimpleNamespace
        from aiohttp import WSMsgType
        from server import HomeAssistant
        ha = HomeAssistant(None, 'http://ha/api', 'unused')
        ha.relevant = {'light.physical'}
        wake = asyncio.Event()
        ha.state_events.listeners[wake] = frozenset({'media_player.test'})
        class Events:
            def __init__(self, state): self.state = state
            async def __aiter__(self):
                yield SimpleNamespace(type=WSMsgType.TEXT, json=lambda: {
                    'type': 'event', 'event': {'event_type': 'state_changed',
                    'data': {'entity_id': 'media_player.test', 'new_state': self.state}}})
        for state in ({'state': 'playing', 'attributes': {'media_title': 'Next track'}}, None):
            wake.clear()
            ha.ws = Events(state)
            with self.assertRaises(ConnectionError): await ha.read()
            self.assertTrue(wake.is_set())
            self.assertEqual(ha.states.get('media_player.test'), state)
            self.assertFalse(ha.changed.is_set(), 'physical-screen filtering stays unchanged')

    async def test_firmware_image_transport_uses_device_cover_bytes(self):
        import io
        from PIL import Image
        from unittest.mock import AsyncMock
        self.ha.states['media_player.test'] = {'state': 'playing', 'attributes': {'entity_picture': '/private?token=secret'}}
        self.manager.camera.picture = lambda entity: '/private?token=secret'
        source = io.BytesIO()
        Image.new('RGB', (160, 80), (220, 30, 70)).save(source, 'PNG')
        self.manager.camera.fetch_cover = AsyncMock(return_value=source.getvalue())
        command = {'service': 'esphome.screen_camera', 'event': True, 'data': {
            'entity': 'media_player.test', 'size': '120', 'bg': '123456',
            'session': '1111111111111111', 'rev': '2222222222222222', 'view': '3'}}
        body = {'request': command, 'shape': {'width': 720, 'height': 720}}
        self.assertEqual((await self.client.post('/api/firmware-preview/image', json=body)).status, 403)
        response = await self.client.post('/api/firmware-preview/image', json=body, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        packet = await response.json()
        self.assertEqual((packet['op'], packet['t'], packet['view']), ('camera', 'cover', 3))
        self.assertEqual(packet['session'], command['data']['session'])
        self.assertNotIn('secret', str(packet))
        self.assertNotIn('/private', str(packet))
        token = packet['u'].rsplit('/', 1)[1]
        pixels = await self.client.get('/api/firmware-preview/images/' + token)
        self.assertEqual(pixels.status, 200)
        expected = await self.manager.camera.cover('media_player.test', 120, 0x123456)
        raw = await pixels.read()
        self.assertEqual(raw, expected[1], 'the preview transports the device bytes without a second image renderer')
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size, (120, 120))
            self.assertEqual(image.getpixel((0, 0)), (0x12, 0x34, 0x56))
        self.assertEqual(self.ha.calls, [])
        self.assertFalse(self.manager.layouts)
        for change in [{'size': '10000'}, {'entity': 'light.a'}, {'entity': 'media_player.unknown'},
                       {'url': 'http://example.com'}, {'view': '-1'}, {'session': 'bad'}, {'bg': 'white'}]:
            invalid = {**body, 'request': {**command, 'data': {**command['data'], **change}}}
            response = await self.client.post('/api/firmware-preview/image', json=invalid, headers=self.headers)
            self.assertEqual(response.status, 400, await response.text())
        self.assertEqual((await self.client.get('/api/firmware-preview/images/abcdefghijklmnop.bmp')).status, 404)

    async def test_firmware_cover_strip_uses_the_shared_atlas_and_missing_art_placeholder(self):
        import io
        import json
        from PIL import Image
        from unittest.mock import AsyncMock
        self.ha.states['media_player.test'] = {'state': 'playing', 'attributes': {}}
        self.manager.camera.picture = lambda entity: '/private'
        source = io.BytesIO()
        Image.new('RGB', (160, 80), (50, 120, 200)).save(source, 'PNG')
        self.manager.camera.fetch_cover = AsyncMock(return_value=source.getvalue())
        # Firmware 0.16.0+ names each square's tile by index (`idx`); the preview takes the request with it.
        fields = {'tiles': 'media_player.test', 'idx': '0', 'size': '64', 'bg': '123456', 'session': '1111111111111111',
                  'rev': '2222222222222222', 'view': '4', 'atlas': json.dumps([[0, 0, 120, 80, 8, 0]])}
        body = {'request': {'service': 'esphome.screen_camera', 'event': True, 'data': fields},
                'shape': {'width': 720, 'height': 720}}
        response = await self.client.post('/api/firmware-preview/image', json=body, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        packet = await response.json()
        self.assertEqual((packet['t'], packet['e']), ('live', 'media_player.test'))
        pixels = await self.client.get('/api/firmware-preview/images/' + packet['u'].rsplit('/', 1)[1])
        with Image.open(io.BytesIO(await pixels.read())) as image:
            self.assertEqual(image.size, (120, 80))
        self.manager.camera.picture = lambda entity: ''
        body['request']['data'] = {'entity': 'media_player.test', 'size': '120', 'bg': '123456',
                                  'session': '1111111111111111', 'rev': '2222222222222222', 'view': '5'}
        response = await self.client.post('/api/firmware-preview/image', json=body, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual((await response.json())['u'], '')

    async def test_states_give_the_value_word_and_attributes_per_entity(self):
        response = await self.client.get('/api/states?entity=light.a&entity=sensor.t&entity=light.nope&entity=screen.clock')
        states = (await response.json())['states']
        self.assertEqual(set(states), {'light.a', 'sensor.t'}, 'unknown entities and built-ins are left out')
        self.assertEqual(states['light.a']['state'], 'on')
        self.assertEqual(states['sensor.t']['state'], '21.5')
        self.assertEqual(states['sensor.t']['a']['unit_of_measurement'], '°C')
        self.assertIn('word', states['light.a'])

    async def test_firmware_preview_uses_device_packets_without_saving_or_actions(self):
        from core import Grid
        from page_layout import compile_tiles, bar_items
        import page_delivery
        legacy = {'title': 'Preview', 'pages': 2, 'tiles': [
            {'entity': 'light.a', 'name': 'Desk', 'slot': 0, 'options': {'background': 'green'}},
            {'entity': 'sensor.t', 'name': 'Temperature', 'slot': 6}]}
        before = dict(self.manager.layouts)
        imported = await self.client.post('/api/firmware-preview/import', json={
            'document': legacy, 'sourceGrid': {'columns': 2, 'rows': 3}}, headers=self.headers)
        self.assertEqual(imported.status, 200, await imported.text())
        record = await imported.json()
        data = {'shape': {'width': 720, 'height': 720, 'columns': 2, 'rows': 3}, 'layout': record['layout']}
        response = await self.client.post('/api/firmware-preview', json=data, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        bundle = await response.json()
        values = [await self.manager.tile_message(i, tile, lamps=True)
                  for i, tile in enumerate(compile_tiles(record['layout'], Grid(2, 3)))]
        bars = [self.manager.header_message({'header': {'items': bar_items(page)}})['items']
                for page in record['layout']['pages']]
        region = self.manager.page_region()
        begin, tiles, pages, states = page_delivery.prepare('', record, region, values, bars)
        self.assertEqual(bundle['revision'], page_delivery.configuration(record, region))
        self.assertEqual(bundle['configuration'], [begin, *pages, *tiles, {'op': 'commit'}])
        self.assertEqual(bundle['values'], [*states, *[page_delivery.page_message(page, i, bar, initial=False)
            for i, (page, bar) in enumerate(zip(record['layout']['pages'], bars))]])
        self.assertEqual(len(pages), 2)
        self.assertEqual([tile['slot'] for tile in tiles], [0, 6])
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
        self.assertEqual(set(sections[0]), {'app', 'firmware', 'boards', 'lines'})
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
        for name in ('export function copyLayoutFrom', 'export function exportLayout', 'export async function importLayout'):
            self.assertIn(name, self.store)
        for marker in ('id="copy-layout"', 'id="export-layout"', 'id="import-layout"', 'accept="application/json,.json"'):
            self.assertIn(marker, self.page, marker)
        self.assertIn('pages.remapLayout(record.layout, state.documentGrid)', self.store)
        self.assertNotIn('.slice(0, tileLimit.value)', self.store, 'an incompatible import must be reviewed, never silently truncated')

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
        for marker in ('export const SIZES: Size[] = ["single", "wide", "tall", "square", "full"];', 'export const pageTarget', 'versionAtLeast(firmware, "0.18.0")) return Math.min(FIRMWARE_MAX_TILES, grid.maxSlots)'):
            self.assertIn(marker, layout, marker)
        drawer = editor_sources.component('TileInspector')
        for marker in ('tileSizeChoices(props.tile)', 't("editor.tile.goes_to.label")', 'retargetPageTile(tile, Number(v))'):
            self.assertIn(marker, drawer, marker)
        self.assertEqual((editor_sources.text('tile.size.full'), editor_sources.text('tile.goes_to.label')), ('Full page', 'Goes to page'))
        self.assertIn(':class="{ wide, full, tall,', editor_sources.component('TileCard'))
        self.assertIn('"timer", "screen",', editor_sources.component('Library'))
        self.assertEqual(editor_sources.text('library.filters.screen'), 'Screen')


if __name__ == '__main__':
    unittest.main()
