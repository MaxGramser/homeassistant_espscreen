"""The screen owns its settings, answers its pings, and three fixes around them (app 0.2.57 / firmware 0.2.49).

- A screen with firmware 0.2.49 offers every setting as an entity. ESP Screens reads and changes them there
  and leaves them out of the layout message, so it never undoes a change made on the screen or by an
  automation. Older firmware keeps getting them with the layout, but a change it reports is no longer sent
  back to it.
- The screen answers a ping with its status (`api.respond`), so ESP Screens knows at once when it lacks
  the layout or a tile.
- The layout sensors come back after Home Assistant restarts, the settings tile opens without Home
  Assistant, and a weather entity is only asked for the forecasts it has.
"""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import importlib.util
import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import core  # noqa: E402
from core import (FIRMWARE_VERSION, SETTING_ENTITIES, SETTING_ENTITIES_MIN_FIRMWARE, SETTING_RULES, forecast_kinds,  # noqa: E402
                  setting_action, setting_entities, setting_from_state, validate_settings)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import server
    from aiohttp import WSMsgType
    from aiohttp.test_utils import TestClient, TestServer
    from server import ANSWER_RETRY_SECONDS, HomeAssistant, Manager, Refused, create_app

PROFILES = {'cyd': 'checkout/cyd.yaml', 'guition': 'checkout/guition.yaml', 'waveshare43': 'checkout/waveshare43.yaml',
            'jc8012p4a1': 'checkout/jc8012p4a1.yaml', 'tab5': 'checkout/tab5.yaml', 'waveshare7': 'checkout/waveshare7.yaml',
            'waveshare4b': 'checkout/waveshare4b.yaml'}
PACKAGES = {'cyd': 'packages/cyd.yaml', 'guition': 'packages/guition.yaml', 'waveshare43': 'packages/waveshare43.yaml',
            'jc8012p4a1': 'packages/jc8012p4a1.yaml', 'tab5': 'packages/tab5.yaml', 'waveshare7': 'packages/waveshare7.yaml',
            'waveshare4b': 'packages/waveshare4b.yaml'}
RUNTIME = runtime_source()
SCREEN_PAGE = (ROOT / 'components/smart_display/settings_screen.h').read_text()
STATIC = ROOT / 'screen_manager/app/static'

# The entity ids Home Assistant gives the settings of a screen named "Office 1".
ENTITY_IDS = {
    'brightness': 'number.office_1_normal_brightness', 'standby_enabled': 'switch.office_1_auto_standby',
    'standby_seconds': 'number.office_1_standby_after', 'standby_brightness': 'number.office_1_standby_brightness',
    'night_enabled': 'switch.office_1_night_mode', 'night_start': 'time.office_1_night_starts',
    'night_end': 'time.office_1_night_ends', 'night_brightness': 'number.office_1_night_brightness',
    'auto_home': 'switch.office_1_back_to_page_1',
    'auto_home_seconds': 'number.office_1_back_to_page_1_after', 'home_on_standby': 'switch.office_1_back_to_page_1_on_standby',
    'swipe_pages': 'switch.office_1_swipe_between_pages', 'rotation': 'select.office_1_rotation',
    'dark_mode': 'switch.office_1_dark_mode', 'page_buttons': 'switch.office_1_page_buttons',
    'home_button': 'switch.office_1_show_home_button',
}
STATES = {'brightness': '80.0', 'standby_enabled': 'on', 'standby_seconds': '600.0', 'standby_brightness': '20.0',
          'night_enabled': 'on', 'night_start': '22:30:00', 'night_end': '07:00:00', 'night_brightness': '5.0',
          'auto_home': 'on', 'auto_home_seconds': '120.0', 'home_on_standby': 'off',
          'swipe_pages': 'on', 'rotation': '90°', 'dark_mode': 'off', 'page_buttons': 'on', 'home_button': 'on'}


def top_block(text, key):
    match = re.search(rf'^{key}:\n(.*?)(?=^[a-z_]+:|\Z)', text, re.M | re.S)
    return match.group(1) if match else ''


def fake_ha(firmware='0.2.104', owned=True, guition=True):
    class HA:
        online = True

        def __init__(self):
            self.registry = [{'entity_id': 'text.screen', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                             {'entity_id': 'sensor.fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                             {'entity_id': 'sensor.node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                             {'entity_id': 'light.a', 'platform': 'hue', 'original_name': 'Lamp A'}]
            self.states = {'text.screen': {'state': 'Synced'}, 'sensor.fw': {'state': firmware}, 'sensor.node': {'state': 'office-1'},
                           'light.a': {'state': 'on', 'attributes': {'friendly_name': 'Lamp A'}}}
            if guition:
                self.registry.append({'entity_id': 'sensor.board', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': 'd1'})
                self.states['sensor.board'] = {'state': 'guition'}
            if owned:
                for key, entity in ENTITY_IDS.items():
                    if key == 'rotation' and not guition:
                        continue
                    self.registry.append({'entity_id': entity, 'platform': 'esphome', 'original_name': SETTING_ENTITIES[key][1], 'device_id': 'd1'})
                    self.states[entity] = {'state': STATES[key]}
            else:
                # Firmware 0.2.41-0.2.48: five of them already existed, which says nothing yet.
                for key in ('brightness', 'standby_enabled', 'standby_seconds', 'standby_brightness', 'night_brightness'):
                    self.registry.append({'entity_id': ENTITY_IDS[key], 'platform': 'esphome', 'original_name': SETTING_ENTITIES[key][1], 'device_id': 'd1'})
                    self.states[ENTITY_IDS[key]] = {'state': STATES[key]}
            self.devices, self.areas = [{'id': 'd1', 'name': 'Office 1'}], []
            self.changed, self.dirty, self.relevant, self.setting_events = asyncio.Event(), set(), None, []
            self.messages, self.calls, self.answers, self.published = [], [], [], {}
            self.responses = {'esphome.office_1_screen_message'} if owned else set()

        async def send(self, inbox, message, action=None, respond=False):
            self.messages.append((message, respond))
            if message.get('v') == 2 and message.get('op') == 'hello':
                return {'status': 'Error: protocol version'}
            if respond:
                return self.answers.pop(0) if self.answers else {'status': 'Synced', 'rev': message.get('rev')}
            return None

        async def call(self, action, data):
            self.calls.append((action, data))

        async def set_state(self, entity_id, state, attributes):
            self.published[entity_id] = (state, attributes)
    return HA()


class CoreSettings(unittest.TestCase):
    def test_every_setting_the_editor_offers_has_an_entity(self):
        # 12 or 24 hours is Settings -> Language & region's, for every screen at once (app 0.2.90).
        self.assertEqual(set(SETTING_ENTITIES), set(SETTING_RULES) - {'show_clock', 'clock_24h'})
        self.assertEqual(SETTING_ENTITIES_MIN_FIRMWARE, '0.2.49')
        self.assertLessEqual(tuple(map(int, SETTING_ENTITIES_MIN_FIRMWARE.split('.'))), tuple(map(int, FIRMWARE_VERSION.split('.'))))

    def test_the_entities_are_named_as_in_both_board_profiles(self):
        blocks = {'switch': 'switch', 'number': 'number', 'time': 'datetime', 'select': 'select'}
        for board, path in [*PROFILES.items(), *PACKAGES.items()]:
            text = profiles.text(path)
            for key, (domain, name) in SETTING_ENTITIES.items():
                block = top_block(text, blocks[domain])
                self.assertIn(f'name: "{name}"', block, f'{path}: {key}')
                at = block.index(f'name: "{name}"')
                entry = block[max(0, at - 200):at + 900]
                self.assertIn('entity_category: config', entry, f'{path}: {key}')
                self.assertRegex(entry, rf'settings_screen::set\("{key}"', f'{path}: {key} changes through set()')
            self.assertIn('type: time', top_block(text, 'datetime'), path)

    def test_a_screen_owns_its_settings_only_with_firmware_0_2_49_entities(self):
        old = [{'entity_id': ENTITY_IDS['brightness'], 'platform': 'esphome', 'original_name': 'Normal brightness'},
               {'entity_id': ENTITY_IDS['standby_enabled'], 'platform': 'esphome', 'original_name': 'Auto standby'}]
        self.assertIsNone(setting_entities(old))
        new = old + [{'entity_id': ENTITY_IDS['night_start'], 'platform': 'esphome', 'original_name': 'Night starts'},
                     {'entity_id': 'time.other_night_starts', 'platform': 'template', 'original_name': 'Night starts'},
                     {'entity_id': 'switch.office_1_rotation', 'platform': 'esphome', 'original_name': 'Rotation'}]
        found = setting_entities(new)
        self.assertEqual(found, {'brightness': ENTITY_IDS['brightness'], 'standby_enabled': ENTITY_IDS['standby_enabled'],
                                 'night_start': ENTITY_IDS['night_start']}, 'only ESPHome entities of the right domain')

    def test_reading_a_setting_from_its_state(self):
        read = lambda key, state: setting_from_state(key, {'state': state})
        self.assertEqual((read('auto_home', 'on'), read('auto_home', 'off'), read('auto_home', 'unknown')), (True, False, None))
        self.assertEqual((read('brightness', '80.0'), read('brightness', '79.6'), read('brightness', 'nan')), (80, 80, None))
        self.assertEqual((read('night_start', '22:30:00'), read('night_start', '25:00:00'), read('night_start', 'soon')), (1350, None, None))
        self.assertEqual((read('rotation', '270°'), read('rotation', '45°')), (270, None))
        self.assertIsNone(setting_from_state('brightness', {'state': 'unavailable'}))
        self.assertIsNone(setting_from_state('brightness', None))

    def test_the_action_that_changes_a_setting(self):
        self.assertEqual(setting_action('auto_home', 'switch.x', True), ('switch.turn_on', {'entity_id': 'switch.x'}))
        self.assertEqual(setting_action('auto_home', 'switch.x', False), ('switch.turn_off', {'entity_id': 'switch.x'}))
        self.assertEqual(setting_action('brightness', 'number.x', 40), ('number.set_value', {'entity_id': 'number.x', 'value': 40}))
        self.assertEqual(setting_action('night_end', 'time.x', 425), ('time.set_value', {'entity_id': 'time.x', 'time': '07:05:00'}))
        self.assertEqual(setting_action('rotation', 'select.x', 180), ('select.select_option', {'entity_id': 'select.x', 'option': '180°'}))

    def test_a_weather_entity_is_asked_only_for_the_forecasts_it_has(self):
        self.assertEqual(forecast_kinds({'supported_features': 1}), {'daily'})
        self.assertEqual(forecast_kinds({'supported_features': 2}), {'hourly'})
        self.assertEqual(forecast_kinds({'supported_features': 7}), {'daily', 'hourly'})
        self.assertEqual(forecast_kinds({'supported_features': 4}), set(), 'twice daily only')
        for unknown in ({}, {'supported_features': None}, {'supported_features': True}, None):
            self.assertEqual(forecast_kinds(unknown), {'daily', 'hourly'})


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class OwnedSettings(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, **kw):
        m = Manager(with_screen_grid(fake_ha(**kw)), Path(tmp) / 'screens.json')
        m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}],
                               'settings': validate_settings({'brightness': 10, 'standby_brightness': 10, 'night_brightness': 10})})
        return m

    async def test_the_editor_reads_the_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            self.assertNotIn('settings', m.layouts['text.screen'], 'a screen that owns its settings has none stored')
            view = m.settings_view(m.screen('text.screen'))
            self.assertEqual((view['owner'], view['unavailable']), ('screen', []))
            self.assertEqual(view['keys'], [key for key in SETTING_RULES if key not in ('show_clock', 'clock_24h')])
            self.assertEqual({key: view['values'][key] for key in ('brightness', 'night_start', 'rotation', 'home_on_standby')},
                             {'brightness': 80, 'night_start': 1350, 'rotation': 90, 'home_on_standby': False})
            m.ha.states[ENTITY_IDS['night_end']] = {'state': 'unavailable'}
            view = m.settings_view(m.screen('text.screen'))
            self.assertEqual((view['unavailable'], view['values']['night_end']), (['night_end'], None), 'unknown, not a default')
            # Offline: every value is unknown, also one a layout from before the update still carries.
            seed_layout(m, 'text.screen', {**m.layouts['text.screen'], 'settings': validate_settings({'brightness': 10, 'standby_brightness': 10, 'night_brightness': 10})})
            for entity in ENTITY_IDS.values():
                m.ha.states[entity] = {'state': 'unavailable'}
            view = m.settings_view(m.screen('text.screen'))
            self.assertEqual((set(view['values'].values()), view['unavailable']), ({None}, view['keys']))
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, guition=False)
            self.assertNotIn('rotation', m.settings_view(m.screen('text.screen'))['keys'])
            # A setting whose entity this screen does not have (added in later firmware) is left out, not unknown.
            m.ha.registry = [item for item in m.ha.registry if item['entity_id'] != ENTITY_IDS['home_on_standby']]
            view = m.settings_view(m.screen('text.screen'))
            self.assertNotIn('home_on_standby', view['keys'] + view['unavailable'])
            with self.assertRaises(ValueError):
                await m.change_settings('text.screen', {'home_on_standby': True})

    async def test_a_backlight_without_levels_shows_switches_instead_of_percentages(self):
        # The Waveshare's backlight is one line on an I2C expander, lit or dark (app 0.2.105). Its board file says
        # so, boards.json carries it and the firmware reads the same fact, so the panel and the screen's own
        # settings page agree: no normal brightness, and standby and night as the switch they really are.
        self.assertTrue(core.dimmable({'board': 'guition'}))
        self.assertTrue(core.dimmable({'board': 'cyd'}))
        self.assertTrue(core.dimmable({'board': 'jc8012p4a1'}))
        self.assertFalse(core.dimmable({'board': 'waveshare43'}))
        self.assertTrue(core.dimmable({'board': 'a board this app never heard of'}))
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            view = m.settings_view(screen)
            self.assertIn('brightness', view['keys'])
            self.assertEqual(view['switches'], [])
            waveshare = {**screen, 'board': 'waveshare43'}
            view = m.settings_view(waveshare)
            self.assertNotIn('brightness', view['keys'])
            self.assertEqual(view['switches'], ['standby_brightness', 'night_brightness'])
            # The two switches would be the same numbers underneath, but the Waveshare cannot go dark at all
            # (app 0.2.106, CAN_STANDBY), so neither is a setting of that screen any more.
            self.assertNotIn('standby_brightness', view['keys'])
            self.assertNotIn('night_brightness', view['keys'])

    async def test_a_screen_that_cannot_go_dark_has_no_standby_and_no_night(self):
        # The Waveshare's backlight boost browns the board out when it switches on from a dark screen (app 0.2.106),
        # so its board file says CAN_STANDBY false and boards.json carries it: no standby, no night (standby with a
        # clock), no going back to page 1 on standby. The firmware hides the same rows and keeps their entities
        # internal, so the panel, Home Assistant and the screen's own page agree; the editor drops an empty group.
        self.assertTrue(core.can_standby({'board': 'guition'}))
        self.assertTrue(core.can_standby({'board': 'cyd'}))
        self.assertTrue(core.can_standby({'board': 'jc8012p4a1'}))
        self.assertFalse(core.can_standby({'board': 'waveshare43'}))
        self.assertTrue(core.can_standby({'board': 'a board this app never heard of'}))
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            view = m.settings_view(screen)
            for key in core.STANDBY_KEYS:
                self.assertIn(key, view['keys'], key)
            waveshare = {**screen, 'board': 'waveshare43'}
            view = m.settings_view(waveshare)
            for key in core.STANDBY_KEYS:
                self.assertNotIn(key, view['keys'] + view['unavailable'], key)
            # What it can still do stays.
            for key in ('dark_mode', 'auto_home', 'auto_home_seconds', 'swipe_pages', 'page_buttons'):
                self.assertIn(key, view['keys'], key)

    async def test_a_screen_says_itself_what_it_can_do(self):
        # A board can be changed: a Waveshare whose backlight was rewired to a PWM pin (docs/WAVESHARE7.md) really
        # does dim, and the table this app keeps per board would keep saying it cannot. So a screen reports its own
        # abilities (firmware 0.2.99, the "Screen features" sensor) and those win; the table is only for firmware
        # from before it and for a screen that is offline, which reports nothing at all.
        core_yaml = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn('name: "Screen features"', core_yaml)
        sensor = core_yaml.split('name: "Screen features"', 1)[1].split('update_interval', 1)[0]
        # The sensor only publishes; the list of abilities lives in the component, where tests/test_settings_screen.cpp
        # walks every combination of it.
        self.assertIn("lambda: 'return {settings_screen::features()};'", sensor)
        words = SCREEN_PAGE.split('inline std::string features() {', 1)[1].split('\n}', 1)[0]
        # One row per ability on both sides, and the same words: the firmware's list and core.FEATURES are one table
        # in two places, so adding an ability is a line there and a row here.
        self.assertEqual(set(re.findall(r'\{\w+, "(\w+)"\}', words)), set(core.FEATURES))
        self.assertIn('words.empty() ? "none" : words', words)
        for feature, key in core.FEATURES.items():
            for board, shape in core.SHAPES.items():
                self.assertIn(key, shape, f'{board} says nothing about {feature}')
        # Silence is not an answer: the board decides.
        self.assertFalse(core.dimmable({'board': 'waveshare7'}))
        self.assertFalse(core.can_standby({'board': 'waveshare7'}))
        self.assertIsNone(core.features_of({'board': 'waveshare7'}))
        # The modded one, in its own words.
        modded = {'board': 'waveshare7', 'features': 'dimmable'}
        self.assertTrue(core.dimmable(modded))
        self.assertFalse(core.can_standby(modded), 'standby stays off until that board reports it too')
        self.assertTrue(core.can_standby({'board': 'waveshare7', 'features': 'dimmable standby'}))
        # A screen that can do none of them says so, which is an answer.
        self.assertEqual(core.features_of({'features': 'none'}), set())
        self.assertFalse(core.dimmable({'board': 'cyd', 'features': 'none'}))
        self.assertFalse(core.can_standby({'board': 'cyd', 'features': 'none'}))
        # A word this app has never heard of changes nothing and does not spoil the rest: newer firmware may report
        # an ability an older app knows nothing about.
        ahead = {'board': 'waveshare7', 'features': 'dimmable standby pictures wifi7'}
        self.assertEqual(core.features_of(ahead), {'dimmable', 'standby', 'pictures', 'wifi7'})
        self.assertTrue(core.dimmable(ahead))
        # Nonsense is silence.
        for words in ('', 'DIMMABLE', 'dimmable!', 'a b c d e f g h i', None, 42):
            self.assertIsNone(core.features_of({'features': words}), words)
        self.assertTrue(core.dimmable({'board': 'cyd', 'features': 'DIMMABLE'}))
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            self.assertIsNone(screen['features'], 'no such sensor: the board decides')
            waveshare = {**screen, 'board': 'waveshare7'}
            self.assertNotIn('brightness', m.settings_view(waveshare)['keys'])
            view = m.settings_view({**waveshare, 'features': 'dimmable'})
            self.assertIn('brightness', view['keys'], 'a modded board gets its brightness row')
            self.assertEqual(view['switches'], [])
            for key in core.STANDBY_KEYS:
                self.assertNotIn(key, view['keys'] + view['unavailable'], key)
            # The whole way through: the sensor Home Assistant holds becomes the screen's own word.
            m.ha.registry = m.ha.registry + [{'entity_id': 'sensor.features', 'platform': 'esphome',
                                              'original_name': 'Screen features', 'device_id': 'd1'}]
            m.ha.states['sensor.features'] = {'state': 'dimmable standby'}
            self.assertEqual(m.screen('text.screen')['features'], 'dimmable standby')
            self.assertTrue(core.dimmable(m.screen('text.screen')))
            # A screen that restarts says "unavailable", which is silence and not an answer.
            m.ha.states['sensor.features'] = {'state': 'unavailable'}
            self.assertIsNone(m.screen('text.screen')['features'])

    async def test_the_layout_message_leaves_them_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            message = m.layout_message('text.screen', {**m.layouts['text.screen'], 'settings': validate_settings({})}, m.screen('text.screen'))
            for key in ('settings', 'swipe_pages', 'auto_home', 'auto_home_seconds', 'rotation'):
                self.assertNotIn(key, message)
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, owned=False)
            message = m.layout_message('text.screen', m.layouts['text.screen'], m.screen('text.screen'))
            self.assertEqual(message['settings']['brightness'], 10, 'older firmware still gets them')
            self.assertIn('auto_home', message)

    async def test_a_change_goes_to_the_screen_s_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            # Brightness first: the screen keeps both dim levels at or below it. Unchanged values send nothing.
            await m.change_settings('text.screen', {'standby_brightness': 60, 'brightness': 90, 'night_enabled': True})
            self.assertEqual(m.ha.calls, [('number.set_value', {'entity_id': ENTITY_IDS['brightness'], 'value': 90}),
                                          ('number.set_value', {'entity_id': ENTITY_IDS['standby_brightness'], 'value': 60})])
            m.ha.calls.clear()
            # A lower brightness is fine with higher dim levels: the screen pulls them down itself.
            await m.change_settings('text.screen', {'brightness': 10})
            self.assertEqual(m.ha.calls, [('number.set_value', {'entity_id': ENTITY_IDS['brightness'], 'value': 10})])
            m.ha.calls.clear()
            await m.change_settings('text.screen', {'night_start': 1320, 'rotation': 270})
            self.assertEqual(m.ha.calls, [('time.set_value', {'entity_id': ENTITY_IDS['night_start'], 'time': '22:00:00'}),
                                          ('select.select_option', {'entity_id': ENTITY_IDS['rotation'], 'option': '270°'})])
            m.ha.calls.clear()
            for bad in ({'standby_brightness': 95}, {'show_clock': False}, {'clock_24h': False}, {'beep': True}, {}, None, {'brightness': '50'}):
                with self.assertRaises(ValueError):
                    await m.change_settings('text.screen', bad)
            m.ha.states[ENTITY_IDS['night_end']] = {'state': 'unavailable'}
            with self.assertRaisesRegex(ValueError, 'Night ends'):
                await m.change_settings('text.screen', {'night_end': 480})
            # The others still change; a setting Home Assistant cannot read is checked at its default.
            m.ha.states[ENTITY_IDS['standby_brightness']] = {'state': 'unavailable'}
            await m.change_settings('text.screen', {'brightness': 15, 'night_start': 1380})
            self.assertEqual(m.ha.calls, [('number.set_value', {'entity_id': ENTITY_IDS['brightness'], 'value': 15}),
                                          ('time.set_value', {'entity_id': ENTITY_IDS['night_start'], 'time': '23:00:00'})])
            m.ha.calls.clear()
            m.ha.states['text.screen'] = {'state': 'unavailable'}
            with self.assertRaisesRegex(ValueError, 'offline'):
                await m.change_settings('text.screen', {'brightness': 50})
            self.assertEqual(m.ha.calls, [], 'nothing sent for a refused change')

    async def test_a_page_from_before_still_saving_settings_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}],
                                   'settings': validate_settings({'brightness': 5, 'standby_brightness': 5, 'night_brightness': 5})})
            self.assertNotIn('settings', m.layouts['text.screen'])
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=m.screen('text.screen'), dirty=set())
            layout = next(message for message, _ in m.ha.messages if message['op'] == 'layout')
            self.assertNotIn('settings', layout)

    async def test_a_setting_the_screen_reports_leaves_its_layout_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            before = (Path(tmp) / 'screens.json').read_bytes()
            m.screen_setting_event({'inbox': 'text.screen', 'key': 'brightness', 'value': '33'})
            self.assertEqual((Path(tmp) / 'screens.json').read_bytes(), before)

    async def test_the_editor_hears_a_change_made_on_the_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            self.assertIn(ENTITY_IDS['night_start'], m.watched_entities())
            listener = asyncio.Event()
            m.listeners.add(listener)
            task = asyncio.create_task(m.run())
            m.ha.changed.set()
            await asyncio.sleep(0.6)
            listener.clear()
            m.ha.states[ENTITY_IDS['night_start']] = {'state': '21:00:00'}
            m.ha.dirty.add(ENTITY_IDS['night_start'])
            m.ha.changed.set()
            await asyncio.sleep(0.6)
            task.cancel()
            self.assertTrue(listener.is_set())
            self.assertEqual(m.settings_view(m.screen('text.screen'))['values']['night_start'], 1260)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class OlderFirmware(unittest.IsolatedAsyncioTestCase):
    async def test_a_change_is_kept_with_the_layout_and_only_the_layout_goes_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha(firmware='0.2.48', owned=False)), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}]})
            screen = m.screen('text.screen')
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set())
            m.ha.messages.clear()
            view = await m.change_settings('text.screen', {'standby_seconds': 1800})
            self.assertEqual((view['owner'], view['values']['standby_seconds']), ('layout', 1800))
            self.assertEqual(m.layouts['text.screen']['settings']['standby_seconds'], 1800)
            self.assertEqual(m.ha.calls, [])
            self.assertTrue(await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set()))
            self.assertEqual([message['op'] for message, _ in m.ha.messages], ['layout'], 'the tiles are not sent again')
            self.assertEqual(m.ha.messages[0][0]['settings']['standby_seconds'], 1800)

    async def test_dark_mode_needs_a_screen_that_owns_its_settings(self):
        # Firmware that gets its settings with the layout has no dark look: no row, no key on the wire, no change.
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha(firmware='0.2.48', owned=False)), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}],
                                   'settings': validate_settings({'dark_mode': True})})
            screen = m.screen('text.screen')
            self.assertNotIn('dark_mode', m.settings_view(screen)['keys'])
            message = m.layout_message('text.screen', m.layouts['text.screen'], screen)
            self.assertNotIn('dark_mode', message)
            self.assertNotIn('dark_mode', message['settings'], 'never inside the frozen eleven-key block')
            self.assertEqual(len(message['settings']), 11)
            with self.assertRaises(ValueError):
                await m.change_settings('text.screen', {'dark_mode': True})
        # Firmware 0.2.49-0.2.53 owns its settings but lacks the switch: left out, not unknown.
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha(firmware='0.2.53')), Path(tmp) / 'screens.json')
            m.ha.registry = [item for item in m.ha.registry if item['entity_id'] != ENTITY_IDS['dark_mode']]
            view = m.settings_view(m.screen('text.screen'))
            self.assertNotIn('dark_mode', view['keys'] + view['unavailable'])
        # Firmware 0.2.54: the switch of the screen itself.
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha()), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}]})
            self.assertFalse(m.settings_view(m.screen('text.screen'))['values']['dark_mode'])
            await m.change_settings('text.screen', {'dark_mode': True})
            self.assertEqual(m.ha.calls, [('switch.turn_on', {'entity_id': ENTITY_IDS['dark_mode']})])

    async def test_back_to_page_1_needs_firmware_0_2_44(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha(firmware='0.2.43', owned=False, guition=False)), Path(tmp) / 'screens.json')
            keys = m.settings_view(m.screen('text.screen'))['keys']
            self.assertNotIn('auto_home', keys)
            self.assertNotIn('rotation', keys)
            with self.assertRaises(ValueError):
                await m.change_settings('text.screen', {'auto_home': False})


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class LayoutSensors(unittest.IsolatedAsyncioTestCase):
    async def test_they_are_published_again_after_home_assistant_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha()), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}]})
            await m.publish_layouts()
            self.assertIn('sensor.esp_screens_office_1', m.ha.published)
            m.ha.published.clear()
            await m.publish_layouts()
            self.assertEqual(m.ha.published, {}, 'an unchanged layout is not written twice')
            # Home Assistant restarts: the connection drops, and the states made over REST are gone.
            task = asyncio.create_task(m.run())
            m.ha.online = False
            m.ha.changed.set()
            await asyncio.sleep(0.4)
            m.ha.online = True
            m.ha.changed.set()
            await asyncio.sleep(0.6)
            task.cancel()
            self.assertIn('sensor.esp_screens_office_1', m.ha.published)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class WeatherForecasts(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_forecasts_the_entity_offers_are_asked_for(self):
        for features, expected in ((1, ['daily']), (2, ['hourly']), (3, ['daily', 'hourly']), (None, ['daily', 'hourly'])):
            with tempfile.TemporaryDirectory() as tmp:
                ha = fake_ha()
                asked = []

                async def forecast(entity, kind='daily'):
                    asked.append(kind)
                    return []
                ha.forecast = forecast
                ha.states['weather.home'] = {'state': 'sunny', 'attributes': {} if features is None else {'supported_features': features}}
                m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
                tile = {'entity': 'weather.home', 'name': ''}
                await m.tile_message(0, tile)
                await m.tile_message(0, tile)
                self.assertEqual(asked, expected, f'features {features}')
                self.assertFalse(m.forecast_due('weather.home'), 'what it lacks still counts as fetched')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Answers(unittest.IsolatedAsyncioTestCase):
    async def test_home_assistant_asks_for_the_answer_and_returns_it(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        seen = []

        async def request(kind, **data):
            seen.append(data)
            return {'context': {}, 'response': {'status': 'Synced', 'rev': 'abc'}}
        ha.request = request
        self.assertEqual(await ha.send('text.screen', {'v': 1, 'op': 'ping'}, 'esphome.x_screen_message', respond=True),
                         {'status': 'Synced', 'rev': 'abc'})
        self.assertTrue(seen[-1]['return_response'])
        self.assertIsNone(await ha.send('text.screen', {'v': 1, 'op': 'ping'}, 'esphome.x_screen_message'))
        self.assertNotIn('return_response', seen[-1])

        async def slow(kind, **data):
            await asyncio.sleep(1)
        ha.request = slow
        with patch.object(server, 'ANSWER_TIMEOUT_SECONDS', 0.05):
            with self.assertRaises(TimeoutError):
                await ha.send('text.screen', {'v': 1, 'op': 'ping'}, 'esphome.x_screen_message', respond=True)

    async def test_which_actions_answer_comes_from_home_assistant(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')

        async def request(kind, **data):
            return {'esphome': {'office_1_screen_message': {'fields': {}, 'response': {'optional': True}},
                                'office_1_show_alert': {'fields': {}}}, 'light': {'turn_on': {'response': {'optional': True}}}}
        ha.request = request
        await ha.fetch_services()
        self.assertEqual(ha.responses, {'esphome.office_1_screen_message'})

    async def test_a_refusal_carries_home_assistant_s_reason(self):
        ha = HomeAssistant(None, 'http://ha/api', 'token')
        future = asyncio.get_running_loop().create_future()
        ha.pending[7] = future

        class Message:
            type = WSMsgType.TEXT
            def json(self):
                return {'id': 7, 'type': 'result', 'success': False, 'error': {'code': 'service_validation_error', 'message': 'does not support responses'}}

        class Socket:
            def __aiter__(self):
                async def messages():
                    yield Message()
                return messages()
        ha.ws = Socket()
        with self.assertRaises(ConnectionError):
            await ha.read()
        with self.assertRaises(Refused) as refused:
            await future
        self.assertEqual((str(refused.exception), refused.exception.detail), ('Home Assistant refused the command.', 'does not support responses'))

    def manager(self, tmp, **kw):
        m = Manager(with_screen_grid(fake_ha(**kw)), Path(tmp) / 'screens.json')
        m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'light.a', 'name': ''}]})
        return m

    async def test_a_new_layout_is_confirmed_by_an_answered_ping(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set())
            self.assertEqual([(message['op'], respond) for message, respond in m.ha.messages],
                             [('hello', True), ('layout', False), ('header', False), ('state', False), ('ping', True)])
            ping = m.ha.messages[-1][0]
            self.assertEqual(ping['rev'], m.sent['text.screen']['rev'])
            m.ha.messages.clear()
            # A tile that changes is not followed by a ping.
            m.ha.states['light.a']['state'] = 'off'
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty={'light.a'})
            self.assertEqual([message['op'] for message, _ in m.ha.messages], ['state'])
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, firmware='0.2.48', owned=False)
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=m.screen('text.screen'), dirty=set())
            self.assertNotIn('ping', [message['op'] for message, _ in m.ha.messages], 'older firmware cannot answer')

    async def test_an_answer_that_something_is_missing_sends_everything_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            # Right after a full send the screen lacks a tile: everything again, after a short wait.
            m.ha.answers.append({'status': 'Loading tiles', 'rev': 'x'})
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set())
            self.assertIn('text.screen', m.sent)
            self.assertAlmostEqual(m.retry_at['text.screen'] - m.last['text.screen'], ANSWER_RETRY_SECONDS, delta=0.1)
            # The wait is over: the loop drops what it thought the screen had, so it sends everything.
            m.retry_at['text.screen'] = time.monotonic() - 1
            m.ha.messages.clear()
            task = asyncio.create_task(m.run())
            m.ha.changed.set()
            await asyncio.sleep(0.6)
            task.cancel()
            self.assertEqual([message['op'] for message, _ in m.ha.messages][:3], ['layout', 'header', 'state'])
            self.assertNotIn('text.screen', m.retry_at)
            self.assertNotIn('text.screen', m.retries, 'the resend was answered with Synced: the count starts again')
            # A keepalive long after the last full send that finds the layout gone: everything again at once.
            m.last['text.screen'] = time.monotonic() - 3600
            m.ha.answers.append({'status': 'Resend needed', 'rev': 'x'})
            await m.ping('text.screen', screen)
            self.assertNotIn('text.screen', m.sent)
            self.assertEqual(m.retries['text.screen'], 1)
            # The resend fails too: the next try waits twice as long.
            m.ha.answers.append({'status': 'Loading tiles', 'rev': 'x'})
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set())
            self.assertEqual(m.retries['text.screen'], 2)
            self.assertAlmostEqual(m.retry_at['text.screen'] - m.last['text.screen'], 2 * ANSWER_RETRY_SECONDS, delta=0.1)

    async def test_home_assistant_that_will_not_answer_gets_plain_pings(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            await m.sync_one('text.screen', m.layouts['text.screen'], screen=screen, dirty=set())
            original = m.ha.send

            async def refuse(inbox, message, action=None, respond=False):
                if respond:
                    raise Refused('An action which does not return responses can\'t be called with return_response=True')
                return await original(inbox, message, action)
            m.ha.send = refuse
            m.ha.messages.clear()
            with self.assertLogs('screen_manager', 'WARNING'):
                await m.ping('text.screen', screen)
            self.assertEqual([(message['op'], respond) for message, respond in m.ha.messages], [('ping', False)])
            self.assertFalse(m.answers('text.screen', screen))

            async def broken(inbox, message, action=None, respond=False):
                raise Refused('ESPHome device is not connected')
            m.no_answers.clear()
            m.ha.send = broken
            with self.assertRaises(Refused):
                await m.ping('text.screen', screen)
            self.assertTrue(m.answers('text.screen', screen), 'another refusal is an ordinary failure')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class SettingsRoute(unittest.IsolatedAsyncioTestCase):
    async def test_the_editor_changes_one_setting_at_a_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Manager(with_screen_grid(fake_ha()), Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory?light=1')).json()
                self.assertEqual(inventory['screens'][0]['settings']['owner'], 'screen')
                url = '/api/screens/text.screen/settings'
                self.assertEqual((await client.put(url, json={'settings': {'brightness': 55}})).status, 403, 'CSRF')
                headers = {'X-Screen-CSRF': inventory['csrf']}
                response = await client.put(url, headers=headers, json={'settings': {'brightness': 55}})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['owner'], 'screen')
                self.assertEqual(m.ha.calls, [('number.set_value', {'entity_id': ENTITY_IDS['brightness'], 'value': 55})])
                response = await client.put(url, headers=headers, json={'settings': {'standby_seconds': 5}})
                self.assertEqual(response.status, 400)
                self.assertIn('standby_seconds', (await response.json())['error'])

                async def refuse(action, data):
                    raise Refused('Entity is not available')
                m.ha.call = refuse
                response = await client.put(url, headers=headers, json={'settings': {'brightness': 60}})
                self.assertEqual(response.status, 400)
                self.assertIn('Entity is not available', (await response.json())['error'])


class Editor(unittest.TestCase):
    def setUp(self):
        import editor_sources
        self.html = editor_sources.PAGE
        self.script = editor_sources.SCRIPT
        self.css = editor_sources.CSS
        self.tab = editor_sources.component('SettingsTab')

    def test_the_panel_replaces_the_form(self):
        self.assertIn('<div class="settings" id="general-settings"', self.tab)
        for element in ('settings-groups', 'settings-status'):
            self.assertEqual(self.html.count(f'id="{element}"'), 1)
        self.assertNotIn('settings-fields', self.html + self.script)
        self.assertNotIn('settingDefinitions', self.script)
        for rule in ('.set-card', '.srow', '.switch[aria-checked="true"]', '.switch.unknown::after', '.step', '.step output'):
            self.assertIn(rule, self.css)
        # A value Home Assistant does not have (offline, entity off) shows as unknown, not as a default.
        self.assertIn('if (value === null || value === undefined) return "—";', self.script)
        self.assertIn(':class="{ unknown: values[row.key] === null || values[row.key] === undefined }"', self.tab)

    def test_the_rows_are_the_settings_of_the_screen_page(self):
        import editor_sources
        keys = re.findall(r'\{ key: "(\w+)", kind: "(\w+)"', self.script)
        # 12 or 24 hours is Settings -> Language & region's, for every screen at once (app 0.2.90).
        self.assertEqual({key for key, _ in keys}, set(SETTING_RULES) - {'show_clock', 'clock_24h'})
        # Labels and steps as on the screen: the same rows, the same -/+ steps, the same duration ladder.
        # The labels are keys into the translations since app 0.2.90; English is the reference.
        english = json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))['screen']['settings']
        page_labels = {english[key] for key in re.findall(r'(?:number|toggle|duration|moment|choice)\(screen_text::txt::settings_(\w+)', SCREEN_PAGE)}
        script_labels = {editor_sources.text(f'screen_settings.rows.{key}') for key, _ in keys}
        # The screen page has two rows the editor has no row for (app 0.2.105): on a board whose backlight is lit
        # or dark, standby and night are drawn as a switch. It is the same setting and the same key underneath,
        # so the editor keeps one row and the manager says to draw it as a switch (settings_view `switches`).
        switch_labels = {english['standby_lit'], english['night_lit']}
        self.assertTrue(switch_labels <= page_labels)
        self.assertEqual(page_labels - switch_labels, script_labels)
        for key, step in (('brightness', 5), ('standby_brightness', 5), ('night_brightness', 5)):
            self.assertRegex(self.script, rf'key: "{key}", [^}}]*step: {step}')
        ladder = re.search(r'if \(seconds < 300\) return 30;\s+if \(seconds < 900\) return 60;\s+if \(seconds < 3600\) return 300;\s+'
                           r'if \(seconds < 7200\) return 900;\s+return 1800;', SCREEN_PAGE)
        self.assertTrue(ladder, 'the ladder in settings_screen.h changed: change ladderStep in web/src/store.ts with it')
        self.assertIn('seconds < 300 ? 30 : seconds < 900 ? 60 : seconds < 3600 ? 300 : seconds < 7200 ? 900 : 1800', self.script)

    def test_settings_have_their_own_call_and_save_leaves_them_out(self):
        self.assertIn('api(`screens/${encodeURIComponent(screen)}/settings`', self.script)
        self.assertIn('submitted = pages.clone(state.document)', self.script)
        self.assertIn('format: "pages-v2", revision: state.documentRevision, layout: submitted', self.script)
        from pathlib import Path
        types = (Path(__file__).resolve().parents[1] / 'web/src/types.ts').read_text()
        page_layout = types.split('export type PageLayout = ', 1)[1].split(';', 4)[:4]
        self.assertNotIn('settings', ''.join(page_layout), 'device settings are not part of the page document')
        # The top bar's clock follows the one clock of Settings → Language & region (app 0.2.90).
        import editor_sources
        self.assertIn('state.inventory.language?.clock_effective !== "12"', self.script)
        self.assertNotIn("setSetting('clock_24h'", self.script)
        self.assertIn('<a href="#settings">', editor_sources.component('TopbarInspector'))


class Firmware(unittest.TestCase):
    def test_the_message_action_answers_a_caller_that_asks(self):
        for path in [*PROFILES.values(), *PACKAGES.values()]:
            text = profiles.text(path)
            action = text[text.index('- action: screen_message'):]
            # Up to the next key of the api block or the next top-level block (the packages carry no keys).
            action = action[:re.search(r'\n(?:  [a-z_]+:|[a-z_]+:)', action).start()]
            self.assertIn('supports_response: optional', action, path)
            self.assertIn("lambda: 'return call_id != 0;'", action, f'{path}: no answer, no warning, for a caller without a call id')
            self.assertIn('api.respond:', action, path)
            self.assertIn('root["status"] = id(dashboard_inbox).state;', action, path)
            self.assertIn('root["rev"] = runtime_tiles::layout_rev;', action, path)

    def test_the_settings_tile_opens_without_home_assistant(self):
        event = RUNTIME[RUNTIME.index('inline void event(lv_event_t *event) {'):]
        event = event[:event.index('\n}\n')]
        self.assertLess(event.index('builtin()'), event.index('if (!fresh()) return;'))
        self.assertIn('settings_screen::open();', event[:event.index('if (!fresh()) return;')])
        self.assertIn('card.tap == "none"', event)

    def test_home_assistant_sees_every_setting_change(self):
        for board, path in PROFILES.items():
            text = profiles.text(path)
            script = text[text.index('- id: apply_screen_settings'):]
            script = script[:script.index('\n  - id: ', 10)]
            for entity in ('setting_brightness', 'setting_standby_brightness', 'setting_night_brightness', 'setting_standby_seconds',
                           'setting_auto_home_seconds'):
                # One loop publishes every number that lacks a state or changed (firmware 0.2.50, see test_cover_card).
                self.assertIn(f'std::make_pair(id({entity}),', script, f'{path}: {entity}')
            self.assertIn('if (!entity->has_state() || entity->state != value) entity->publish_state(value);', script, path)
            self.assertIn('std::make_pair(id(setting_night_start), settings.night_start)', script, path)
            self.assertIn('settings_screen::refresh();', script, f'{path}: an open settings page follows Home Assistant')
            # Every board turns since firmware 0.2.80 (a half turn at least): the shared script keeps the entity in step.
            self.assertIn('id(setting_rotation)->update();', text, path)

    def test_the_page_and_every_entity_change_settings_the_same_way(self):
        self.assertRegex(SCREEN_PAGE, r'enum class SetResult : uint8_t \{ unknown, same, changed \};')
        for path in PROFILES.values():
            text = profiles.text(path)
            self.assertNotIn('settings_preference.save(&s)', text, f'{path}: saving goes through settings_screen::set()')
            self.assertNotIn('update_interval: never\n    lambda: return settings_screen::swipe_pages', text, 'a template switch has no update_interval')


if __name__ == '__main__':
    unittest.main()
