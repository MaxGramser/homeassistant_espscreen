"""The app's own texts in the translations (app 0.2.90): its messages, statuses and labels in the editor's language, the
words it sends to the screens in theirs.

Every key the code asks for is in en.json with the placeholders the code fills in, and the English tables the Claude skill
writes from (backgrounds, direct controls, the alert reference, the icons) say what en.json says. A made-up language, xx,
shows that another language reaches the editor through the request's X-ESP-Screens-Language header and the screens
through Settings -> Language & region, while what the app hands Home Assistant as data stays English.
"""
from manager_fixtures import with_screen_grid
import ast
import asyncio
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'screen_manager/app'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / 'tests'))
import core  # noqa: E402
import header_bar  # noqa: E402
import history_card  # noqa: E402
import i18n  # noqa: E402
from i18n import REQUEST_LANGUAGE, TRANSLATIONS, english, shown, t  # noqa: E402
import tile_icons  # noqa: E402
import updates  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import test_scaling
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app

ENGLISH = TRANSLATIONS.flat['en']
PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')
KEY = re.compile(r'(addon|screen)(\.[a-z0-9_]+){2,}')


def lookups():
    """(where, key, params) of every t(), english() and screen_t() with a written-out key in the app's code."""
    for path in sorted(APP.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('t', 'english', 'screen_t')
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                yield f'{path.name}:{node.lineno}', node.args[0].value, {keyword.arg for keyword in node.keywords}


def written_keys():
    """(where, key) of every other translation key the code names in full, such as the tables of words by key."""
    for path in sorted(APP.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and KEY.fullmatch(node.value):
                yield f'{path.name}:{node.lineno}', node.value


class Language:
    """xx for as long as a test runs: the texts under `prefixes` marked "[xx] ", every other one in English."""

    def __init__(self, *prefixes):
        self.prefixes = prefixes

    def __enter__(self):
        TRANSLATIONS.data['xx'] = {'_meta': {'name': 'Xx', 'english': 'Xx', 'plural': 'one_other', 'clock': '24'}}
        TRANSLATIONS.flat['xx'] = {key: ' | '.join(f'[xx] {form.strip()}' for form in text.split('|'))
                                   for key, text in ENGLISH.items() if key.startswith(self.prefixes)}
        return self

    def __exit__(self, *_):
        del TRANSLATIONS.data['xx'], TRANSLATIONS.flat['xx']
        i18n.set_screens('en', 'point')


class Keys(unittest.TestCase):
    def test_every_key_the_app_asks_for_is_in_english_with_its_placeholders(self):
        found = list(lookups())
        self.assertGreater(len(found), 150)
        for where, key, params in found:
            self.assertIn(key, ENGLISH, where)
            # `n` picks a plural form; every other placeholder is filled in by name.
            self.assertEqual(set(PLACEHOLDER.findall(ENGLISH[key])), params, f'{where}: {key}')
        for where, key in written_keys():
            self.assertIn(key, ENGLISH, where)

    def test_the_app_s_texts_are_whole_and_keep_the_editor_s_characters_out(self):
        for key, text in ENGLISH.items():
            if key.startswith('addon.'):
                self.assertTrue(text.strip(), key)
                self.assertNotIn('@', text, key)
                self.assertFalse(re.search(r'[{}]', PLACEHOLDER.sub('', text)), key)
                # A plural has English's two forms, each with its own words.
                self.assertIn(len(text.split('|')), (1, 2), key)

    def test_the_english_tables_the_claude_skill_writes_from_say_what_english_says(self):
        self.assertEqual({name: item['label'] for name, item in core.backgrounds().items()},
                         {name: item['label'] for name, item in core.TILE_BACKGROUNDS.items()})
        catalogue = core.controls_catalogue()
        for domain, choices in core.CONTROLS.items():
            self.assertEqual([(c['key'], c['label']) for c in catalogue[domain]['choices']], [*choices, ('none', 'None')], domain)
        reference = core.alert_reference()
        self.assertEqual([(f['name'], f['label'], f['help'], f['example']) for f in reference['fields']],
                         [(name, label, help_, example) for name, _, label, help_, example in core.ALERT_FIELDS])
        self.assertEqual(tuple(reference['camera'].values()), core.ALERT_CAMERA_FIELD)
        self.assertEqual([(e['action'], e['label']) for e in reference['endings']], list(core.ALERT_ENDINGS))
        picker = tile_icons.editor()['groups']
        self.assertEqual([(group['label'], [(i['name'], i['cp'], i['label']) for i in group['icons']]) for group in picker],
                         [(group, list(icons)) for group, icons in tile_icons.GROUPS])
        for entity, name in core.BUILTIN.items():
            self.assertEqual(core.builtin_name(entity, english), name)
            self.assertEqual(core.builtin_name(entity, t), name)

    def test_the_binary_words_are_home_assistant_s_from_the_translations(self):
        for device_class, (on, off) in header_bar.BINARY_STATES.items():
            self.assertEqual((on, off), (ENGLISH[f'screen.ha.binary.{device_class}_on'], ENGLISH[f'screen.ha.binary.{device_class}_off']))
            self.assertEqual(header_bar.binary_words(device_class), (on, off))
        self.assertEqual(header_bar.binary_words('future_class'), ('On', 'Off'))


class Texts(unittest.TestCase):
    def test_a_text_keeps_its_key_and_can_be_written_again(self):
        made = english('addon.errors.alerts.cannot_show', name='Hall', reason=english('addon.errors.alerts.offline'))
        self.assertEqual(made, "Hall can't show an alert: offline.")
        self.assertEqual((made.key, set(made.params)), ('addon.errors.alerts.cannot_show', {'name', 'reason'}))
        self.assertEqual(json.dumps({'error': made}), json.dumps({'error': "Hall can't show an alert: offline."}))
        with Language('addon.'):
            self.assertEqual(made.into('xx'), "[xx] Hall can't show an alert: [xx] offline.")
            token = REQUEST_LANGUAGE.set('xx')
            try:
                self.assertEqual(shown(made), "[xx] Hall can't show an alert: [xx] offline.")
                self.assertEqual(t('addon.errors.unknown_screen'), '[xx] Unknown screen.')
                self.assertEqual(shown('Synced'), 'Synced', 'a word the screen reported stays as it came')
            finally:
                REQUEST_LANGUAGE.reset(token)
            # Outside a request, as for a tile event's answer to Home Assistant: English.
            self.assertEqual(t('addon.errors.unknown_screen'), 'Unknown screen.')

    def test_a_count_picks_its_plural_form(self):
        self.assertEqual(t('addon.errors.layout.tiles_max', n=48), 'Choose at most 48 tiles.')
        self.assertEqual(t('addon.errors.layout.tiles_max', n=1), 'Choose at most 1 tile.')

    def test_the_reasons_a_screen_can_t_show_an_alert_are_english_for_the_log(self):
        _, skipped = core.alert_targets([{'name': 'A', 'online': True}, {'name': 'B', 'node': 'b', 'online': False},
                                         {'name': 'C', 'node': 'c', 'online': True, 'firmware': 'unknown'}])
        self.assertEqual([reason for _, reason in skipped], ['device name unknown', 'offline', 'firmware unknown'])
        with Language('addon.'):
            token = REQUEST_LANGUAGE.set('xx')
            try:
                self.assertEqual([shown(reason) for _, reason in skipped],
                                 ['[xx] device name unknown', '[xx] offline', '[xx] firmware [xx] unknown'])
            finally:
                REQUEST_LANGUAGE.reset(token)


class ScreenWords(unittest.TestCase):
    """What the app sends to the screens, in the language of Settings -> Language & region."""

    def test_the_screens_get_the_app_s_words_in_their_language(self):
        with Language('addon.screen.', 'screen.ha.', 'screen.date.', 'screen.settings.', 'screen.vacuum.', 'screen.script.'):
            i18n.set_screens('xx', 'comma')
            self.assertEqual(core.state_message(0, {'entity': 'screen.page_2', 'name': ''}, {})['name'], '[xx] Go to page 2')
            self.assertEqual(core.state_message(0, {'entity': 'screen.settings', 'name': ''}, {})['name'], '[xx] Settings')
            self.assertEqual(core.state_message(0, {'entity': 'screen.clock', 'name': 'Kitchen'}, {})['name'], 'Kitchen')
            self.assertEqual([core.vacuum_label(v) for v in ('vac_and_mop', 'quiet', 'off', 'some_thing')],
                             ['[xx] Vac & mop', '[xx] Quiet', '[xx] Off', 'Some thing'])
            day = {'datetime': '2026-09-14T12:00:00+00:00', 'condition': 'sunny'}
            self.assertEqual(core.extras({'entity': 'weather.home'}, {}, forecast=[day])['days'][0]['d'], '[xx] Mo')
            value = lambda entity, raw, **attributes: header_bar.value(entity, {'state': raw, 'attributes': attributes})[0]
            self.assertEqual(value('sensor.power', '1234.5', unit_of_measurement='W'), '1.234,5 W')
            self.assertEqual(value('lock.front', 'jammed'), '[xx] Jammed')
            self.assertEqual(value('climate.hall', 'heat_cool'), '[xx] Auto')
            self.assertEqual(value('binary_sensor.door', 'on', device_class='door'), '[xx] Open')
            self.assertEqual(value('binary_sensor.x', 'off'), '[xx] Off')
            self.assertEqual(value('script.night', 'off'), '[xx] Never run')
            self.assertEqual(value('input_datetime.alarm', '2026-09-15', has_date=True), '[xx] 15 [xx] Sep')
            self.assertEqual(history_card.state_label('person', 'not_home', {}), '[xx] Away')
            self.assertEqual(history_card.state_label('sensor', 'unknown', {}), '[xx] Unknown')
            self.assertEqual(history_card.tick_text(2500.0, 500, 'W'), '2.500')
        # Back in English, as before this app version.
        self.assertEqual(core.state_message(0, {'entity': 'screen.page_2', 'name': ''}, {})['name'], 'Go to page 2')
        self.assertEqual(header_bar.number_text(1234.5, 1), '1,234.5')
        self.assertEqual(header_bar.short_date(datetime(2026, 9, 15)), '15 Sep')

    def test_a_timeline_s_other_states_take_the_screens_word(self):
        start, end = 0, 24 * 3600
        changes = [(i * 600, f'state_{i % 8}') for i in range(144)]
        with Language('addon.screen.'):
            i18n.set_screens('xx', 'point')
            message = history_card.timeline('sensor.status', 24, changes, start, end, timezone.utc, {})
            # Folded to the letters the screen draws, like every label of the card: the brackets go.
            self.assertEqual(message['states'][-1][0], 'xx Other')


class Updates(unittest.IsolatedAsyncioTestCase):
    def updater(self, tmp, start):
        class HA:
            def __init__(self):
                self.calls = []
            async def request(self, kind, **data):
                self.calls.append(data)
        class Firmware:
            def profile_names(self):
                return {'hall.yaml': {'node': 'hall', 'friendly': 'Hall'}}
        class Owner:
            def preflight_update(self, inbox):
                pass  # This translation fixture has no stored layout.
            def __init__(self):
                self.ha, self.firmware = HA(), Firmware()
                self.firmware.start = start
            def screen(self, inbox):
                return {'id': inbox, 'name': 'Hall', 'node': 'hall', 'online': True, 'ip': '10.0.0.5', 'firmware': '0.2.1'}
            def screens(self):
                return [self.screen('text.hall')]
        return updates.Updater(Owner(), Path(tmp) / 'updates.json')

    async def test_a_result_keeps_its_key_and_shows_in_the_editor_s_language(self):
        def refuse(data):
            raise ValueError(t('addon.errors.firmware.no_esphome'))
        with tempfile.TemporaryDirectory() as tmp, Language('addon.'):
            updater = self.updater(tmp, refuse)
            # A round started from an editor in xx: the refusal is made in xx, and kept in English with its key.
            token = REQUEST_LANGUAGE.set('xx')
            try:
                self.assertEqual(await updater.update_one('text.hall'), 'failed')
            finally:
                REQUEST_LANGUAGE.reset(token)
            kept = json.loads((Path(tmp) / 'updates.json').read_text())['results']['text.hall']
            self.assertEqual((kept['message'], kept['key'], kept['params']),
                             ('The ESPHome CLI is missing from this installation.', 'addon.errors.firmware.no_esphome', {}))
            self.assertEqual(updater.state_for(updater.screen('text.hall'))['result']['message'],
                             'The ESPHome CLI is missing from this installation.')
            token = REQUEST_LANGUAGE.set('xx')
            try:
                self.assertEqual(updater.state_for(updater.screen('text.hall'))['result']['message'],
                                 '[xx] The ESPHome CLI is missing from this installation.')
                updater.record('text.hall', 'success', english('addon.updates.updated', version='0.2.99'))
                self.assertEqual(updater.results['text.hall']['message'], 'Updated to firmware 0.2.99.')
                self.assertEqual(updater.state_for(updater.screen('text.hall'))['result']['message'], '[xx] Updated to firmware 0.2.99.')
                # A result an app before 0.2.90 kept has no key: it shows as it was kept.
                updater.results['text.hall'] = {'time': 0, 'state': 'failed', 'message': 'Build or install failed.', 'version': '0.2.70'}
                self.assertEqual(updater.state_for(updater.screen('text.hall'))['result']['message'], 'Build or install failed.')
            finally:
                REQUEST_LANGUAGE.reset(token)

    async def test_the_notification_of_a_stopped_round_speaks_the_screens_language(self):
        def refuse(data):
            raise ValueError(t('addon.errors.firmware.no_esphome'))
        with tempfile.TemporaryDirectory() as tmp, Language('addon.'):
            updater = self.updater(tmp, refuse)
            i18n.set_screens('xx', 'point')
            await updater.run_round(['text.hall'], automatic=True)
            message = updater.manager.ha.calls[0]['service_data']['message']
            self.assertEqual(message, '[xx] Automatic update stopped at Hall: [xx] The ESPHome CLI is missing from this installation. '
                                      'The remaining screens were not touched.')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Editor(unittest.IsolatedAsyncioTestCase):
    async def test_the_editor_gets_the_app_s_texts_in_its_language(self):
        with tempfile.TemporaryDirectory() as tmp, Language('addon.'):
            manager = Manager(with_screen_grid(test_scaling.fake_ha(firmware=core.FIRMWARE_VERSION)), Path(tmp) / 'screens.json')
            xx = {'X-ESP-Screens-Language': 'xx'}
            async with TestClient(TestServer(create_app(manager, True))) as client:
                full = await (await client.get('/api/inventory', headers=xx)).json()
                self.assertEqual(full['backgrounds']['red']['label'], '[xx] Red')
                self.assertEqual(full['controls']['light']['choices'][0]['label'], '[xx] On/off switch')
                self.assertEqual(full['alerts']['fields'][0]['label'], '[xx] Title')
                self.assertEqual(full['alerts']['fields'][0]['example'], '[xx] Someone is at the door')
                self.assertEqual(full['alerts']['fields'][2]['example'], 'doorbell', 'an icon name is typed as it is')
                self.assertEqual(full['icons']['groups'][0]['label'], '[xx] Lighting')
                self.assertEqual(full['icons']['groups'][0]['icons'][0]['label'], '[xx] Light bulb')
                self.assertEqual(full['header']['builtin'][0]['label'], '[xx] Time')
                self.assertEqual({item['id']: (item['name'], item['device']) for item in full['builtin']}['screen.page_3'],
                                 ('[xx] Go to page 3', '[xx] Built into the screen'))
                self.assertEqual(full['screens'][0]['delivery'], '[xx] Choose your first tiles')
                csrf = full['csrf']
                # The delivery is kept in English and shown in the language of whoever looks.
                manager.save('text.screen', {'title': 'Office', 'tiles': [{'entity': 'light.a', 'name': ''}]})
                self.assertEqual(manager.status['text.screen'], 'Saved; waiting for sync')
                light = await (await client.get('/api/inventory?light=1', headers=xx)).json()
                self.assertEqual(light['screens'][0]['delivery'], '[xx] Saved; waiting for sync')
                light = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(light['screens'][0]['delivery'], 'Saved; waiting for sync')
                # Nothing to report only once the layout went out and the screen says it holds it (app 0.2.108): the
                # editor then shows no delivery line, and a line for anything else.
                self.assertFalse(light['screens'][0]['in_sync'])
                manager.status['text.screen'] = i18n.english('addon.status.sent')
                synced = await (await client.get('/api/inventory?light=1')).json()
                self.assertTrue(synced['screens'][0]['in_sync'])
                manager.ha.states['text.screen'] = {'state': 'Layout received'}
                self.assertFalse((await (await client.get('/api/inventory?light=1')).json())['screens'][0]['in_sync'])
                manager.ha.states['text.screen'] = {'state': 'Synced'}
                manager.status['text.screen'] = i18n.english('addon.status.saved')
                # The live updates: an EventSource sends no headers, so the language comes in the address.
                async with client.get('/api/events?language=xx') as stream:
                    line = await asyncio.wait_for(stream.content.readline(), 1)
                    self.assertEqual(json.loads(line.decode().removeprefix('data: '))['screens'][0]['delivery'], '[xx] Saved; waiting for sync')
                refused =await client.put('/api/screens/text.gone', json={'title': 'T', 'tiles': []}, headers={**xx, 'X-Screen-CSRF': csrf})
                self.assertEqual((refused.status, (await refused.json())['error']),
                                 (400, "[xx] This isn't a paired ESP screen. Refresh the overview."))
                refused = await client.put('/api/screens/text.gone', json={'title': 'T', 'tiles': []}, headers={'X-Screen-CSRF': csrf})
                self.assertEqual((await refused.json())['error'], "This isn't a paired ESP screen. Refresh the overview.")
                forbidden = await client.put('/api/screens/text.screen', json={}, headers=xx)
                self.assertEqual((forbidden.status, await forbidden.text()), (403, '[xx] Refresh this page and try again.'))

    async def test_identify_speaks_the_screens_language(self):
        with tempfile.TemporaryDirectory() as tmp, Language('addon.screen.', 'screen.alert.'):
            ha = test_scaling.fake_ha(firmware=core.FIRMWARE_VERSION)
            ha.calls = []
            async def call(action, data):
                ha.calls.append((action, data))
            ha.call = call
            manager = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            i18n.set_screens('xx', 'point')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                # Firmware from before the languages speaks English, whatever the screens' language is.
                answer = await client.post('/api/screens/text.screen/identify', headers={'X-Screen-CSRF': csrf})
                self.assertEqual(answer.status, 200)
                # Firmware that says it speaks the screens' language gets the card in it.
                ha.registry = ha.registry + [{'entity_id': 'sensor.language', 'platform': 'esphome', 'original_name': 'Screen language',
                                              'device_id': 'd1'}]
                ha.states['sensor.language'] = {'state': 'xx'}
                answer = await client.post('/api/screens/text.screen/identify', headers={'X-Screen-CSRF': csrf})
                self.assertEqual(answer.status, 200)
            texts = [(action, data['title'], data['subtitle'], data['button_text']) for action, data in ha.calls]
            self.assertEqual(texts, [('esphome.office_1_show_alert', 'This is Office 1', 'Identify, from Tessera', 'OK'),
                                     ('esphome.office_1_show_alert', '[xx] This is Office 1', '[xx] Identify, from Tessera', '[xx] OK')])
            i18n.set_screens('en', 'point')

    async def test_a_tile_event_answers_home_assistant_in_english(self):
        with tempfile.TemporaryDirectory() as tmp, Language('addon.'):
            ha = test_scaling.fake_ha(firmware=core.FIRMWARE_VERSION)
            manager = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            i18n.set_screens('xx', 'point')
            with self.assertRaises(ValueError) as caught:
                await manager.tile_event('esp_screens_add_tile', {'entity': 'foo.bar'})
            self.assertEqual(str(caught.exception), 'foo.bar cannot go on a screen.')


if __name__ == '__main__':
    unittest.main()
