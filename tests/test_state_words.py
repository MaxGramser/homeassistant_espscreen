"""Home Assistant's numbers and words (app 0.2.67, firmware 0.2.58): a sensor's value rounded by its display precision,
and Home Assistant's word where a tile, the top bar, a history timeline or a vacuum card's chip showed the raw state
("open", "playing", "rinsing", "vac_and_mop"). WORDS are real entries of frontend/get_translations (English) of Home
Assistant 2026.9.2."""
from datetime import timezone
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import ha_catalogue  # noqa: E402
import header_bar  # noqa: E402
import history_card  # noqa: E402
from core import rounded_state, state_message, vacuum_extras  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager
    from test_ha_capabilities import fake_ha

WORDS = {
    'component.cover.entity_component._.state.open': 'Open',
    'component.cover.entity_component._.state.closing': 'Closing',
    'component.media_player.entity_component._.state.playing': 'Playing',
    'component.vacuum.entity_component._.state.returning': 'Returning to dock',
    'component.binary_sensor.entity_component.motion.state.on': 'Detected',
    'component.sensor.entity_component._.state.on': 'On',
    'component.roborock.entity.sensor.status.state.charging': 'Charging',
    'component.roborock.entity.sensor.zeo_state.state.rinsing': 'Rinsing',
    'component.roborock.entity.select.cleaning_mode.state.vac_and_mop': 'Vacuum and mop',
    'component.roborock.entity.select.cleaning_mode.state.vacuum': 'Vacuum only',
    'component.roborock.entity.select.mop_intensity.state.mild': 'Mild',
    'component.roborock.entity.select.mop_intensity.state.vac_followed_by_mop': 'Vacuum followed by mop',
    'component.roborock.entity.vacuum.roborock.state_attributes.fan_speed.state.balanced': 'Balanced',
    'component.roborock.entity.vacuum.roborock.state_attributes.fan_speed.state.off_raise_main_brush': 'Off (raised brush)',
    'component.climate.entity_component._.state.heat_cool': 'Heat/Cool',
}
CLEANING = {'platform': 'roborock', 'translation_key': 'cleaning_mode'}


class Rounding(unittest.TestCase):
    def test_display_precision(self):
        self.assertEqual(rounded_state('21.456', 1), '21.5')
        self.assertEqual(rounded_state('21.45', 1), '21.5', 'half up, as the frontend rounds')
        self.assertEqual(rounded_state('1249.6', 0), '1250', 'no thousands separator: the screen reads the number')
        self.assertEqual(rounded_state('-0.04', 1), '0.0')
        self.assertEqual(rounded_state('1e30', 1), '1e30', 'too many digits to round: the value stays and the sync goes on')
        self.assertEqual(rounded_state('123456789012345678901234567890.5', 1), '123456789012345678901234567890.5')
        self.assertEqual(rounded_state('3', 2), '3.00')
        for value in ('unavailable', 'on', '', 'nan', 'inf'):
            self.assertEqual(rounded_state(value, 1), value)
        self.assertEqual(rounded_state('21.456', None), '21.456', 'without a precision Home Assistant shows the state as it is')
        self.assertEqual(rounded_state('21.456', True), '21.456')

    def test_only_sensor_states_are_rounded(self):
        states = {'sensor.t': {'state': '21.456', 'attributes': {'unit_of_measurement': '°C'}},
                  'number.n': {'state': '21.456', 'attributes': {}}}
        self.assertEqual(state_message(0, {'entity': 'sensor.t', 'name': ''}, states, precision=1)['state'], '21.5')
        self.assertEqual(state_message(0, {'entity': 'number.n', 'name': ''}, states, precision=1)['state'], '21.456')
        self.assertEqual(state_message(0, {'entity': 'sensor.t', 'name': ''}, states)['state'], '21.456')


class Words(unittest.TestCase):
    def test_home_assistants_word_as_its_frontend_picks_it(self):
        word = lambda entity, state, attributes=None, entry=None: ha_catalogue.state_word(entity, state, attributes, entry, WORDS)
        self.assertEqual(word('cover.blind', 'open'), 'Open')
        self.assertEqual(word('binary_sensor.hall', 'on', {'device_class': 'motion'}), 'Detected')
        self.assertEqual(word('sensor.washer', 'rinsing', {'device_class': 'enum'}, {'platform': 'roborock', 'translation_key': 'zeo_state'}), 'Rinsing')
        self.assertEqual(word('sensor.robot', 'charging', {}, {'platform': 'roborock', 'translation_key': 'status'}), 'Charging')
        self.assertIsNone(word('sensor.robot', 'charging', {}, {'platform': 'roborock'}), 'without a translation key there is no entity word')
        self.assertIsNone(word('cover.blind', 'jammed'))
        self.assertIsNone(word('binary_sensor.hall', 'on', {}, {'original_device_class': 'motion'}), 'the device class comes from the state, as in the frontend')
        self.assertEqual(ha_catalogue.attribute_word('vacuum.s8', 'fan_speed', 'balanced', {}, {'platform': 'roborock', 'translation_key': 'roborock'}, WORDS), 'Balanced')
        self.assertIsNone(ha_catalogue.state_word('cover.blind', 'open', {}, {}, {}))

    def test_tiles_get_a_word_only_where_they_showed_the_raw_state(self):
        screen = lambda entity, state, attributes=None, entry=None: ha_catalogue.screen_word(entity, state, attributes, entry, WORDS)
        self.assertEqual(screen('cover.blind', 'open'), 'Open')
        self.assertEqual(screen('media_player.sonos', 'playing'), 'Playing')
        self.assertEqual(screen('vacuum.s8', 'returning'), 'Returning to dock')
        self.assertEqual(screen('select.s8_mode', 'vac_and_mop', {}, {'platform': 'roborock', 'translation_key': 'cleaning_mode'}), 'Vacuum and mop')
        self.assertIsNone(screen('binary_sensor.hall', 'on', {'device_class': 'motion'}), 'binary sensors keep the words of firmware 0.2.53')
        self.assertIsNone(screen('sensor.power', '12.5'), 'a number keeps its number')
        self.assertIsNone(screen('light.lamp', 'on'))


class WordsBeyondTiles(unittest.TestCase):
    def test_the_top_bar_takes_home_assistants_word_where_it_showed_the_state_as_it_came(self):
        washer = {'state': 'rinsing', 'attributes': {'device_class': 'enum'}}
        self.assertEqual(header_bar.value('sensor.washer', washer, {'platform': 'roborock', 'translation_key': 'zeo_state'}, words=WORDS), ('Rinsing', None))
        mode = {'state': 'vac_and_mop', 'attributes': {'options': ['vacuum', 'vac_and_mop']}}
        self.assertEqual(header_bar.value('select.s8_mode', mode, CLEANING, words=WORDS), ('Vacuum and mop', None))
        self.assertEqual(header_bar.value('select.s8_mode', mode, CLEANING), ('vac_and_mop', None), 'without words as before')
        # The bar's own short words stay until Max chooses: Returning, Auto. A binary sensor says what its tile says, Home
        # Assistant's word for its class from the translations (screen.ha.binary, app 0.2.90).
        self.assertEqual(header_bar.value('vacuum.s8', {'state': 'returning', 'attributes': {}}, None, words=WORDS), ('Returning', None))
        self.assertEqual(header_bar.value('climate.hall', {'state': 'heat_cool', 'attributes': {}}, None, words=WORDS), ('Auto', None))
        motion = {'state': 'on', 'attributes': {'device_class': 'motion'}}
        self.assertEqual(header_bar.value('binary_sensor.hall', motion, None, words=WORDS), ('Detected', None))
        layout = {'header': {'items': [{'type': 'entity', 'entity': 'select.s8_mode', 'content': 'state', 'icon': 'none', 'show': 'always'}]}}
        bar = header_bar.message(layout, {'select.s8_mode': mode}, {'select.s8_mode': CLEANING}, words=WORDS)
        self.assertEqual(bar['items'], [{'k': 'text', 't': 'Vacuum and mop'}])
        self.assertEqual(header_bar.preview(layout['header'], {'select.s8_mode': mode}, {'select.s8_mode': CLEANING}, words=WORDS)[0]['t'], 'Vacuum and mop')

    def test_a_history_timeline_speaks_the_same_words(self):
        changes = [(0, 'vacuum'), (3600, 'vac_and_mop'), (7200, 'custom')]
        message = history_card.timeline('select.s8_mode', 24, changes, 0, 24 * 3600, timezone.utc, {}, entry=CLEANING, translations=WORDS)
        self.assertEqual(sorted(label for label, _, _ in message['states']), ['Custom', 'Vacuum and mop', 'Vacuum only'])
        self.assertEqual(dict(message['words']), {'vacuum': 'Vacuum only', 'vac_and_mop': 'Vacuum and mop', 'custom': 'Custom'})
        before = history_card.timeline('select.s8_mode', 24, changes, 0, 24 * 3600, timezone.utc, {})
        self.assertEqual(dict(before['words']), {'vacuum': 'Vacuum', 'vac_and_mop': 'Vac and mop', 'custom': 'Custom'}, 'without words as before')
        door = history_card.timeline('binary_sensor.front', 24, [(0, 'off'), (60, 'on')], 0, 3600, timezone.utc, {'device_class': 'door'},
                                     entry=None, translations={'component.binary_sensor.entity_component.door.state.on': 'Open'})
        self.assertEqual(dict(door['words'])['on'], 'Open')

    def test_vacuum_chips_take_home_assistants_word_where_the_screen_has_no_label(self):
        device = [{'entity_id': 'vacuum.s8', 'platform': 'roborock', 'translation_key': 'roborock'},
                  {'entity_id': 'select.s8_mop_intensity', 'platform': 'roborock', 'translation_key': 'mop_intensity'}]
        states = {'vacuum.s8': {'state': 'docked', 'attributes': {'fan_speed_list': ['quiet', 'balanced', 'off_raise_main_brush']}},
                  'select.s8_mop_intensity': {'state': 'mild', 'attributes': {'options': ['mild', 'vac_followed_by_mop']}}}
        extra = vacuum_extras({'entity': 'vacuum.s8'}, states, device)
        self.assertEqual((extra['fan']['l'], extra['water']['l']), (['Quiet', 'Normal', 'Off raise main brush'], ['Mild', 'Vac followed by mop']))
        ha_catalogue.chip_words(extra, 'vacuum.s8', states, device, WORDS)
        self.assertEqual(extra['fan']['l'], ['Quiet', 'Normal', 'Off (raised brush)'], "the screen's own Normal stays")
        self.assertEqual(extra['water']['l'], ['Mild', 'Vacuum followed by mop'])
        self.assertEqual(extra['fan']['o'], ['quiet', 'balanced', 'off_raise_main_brush'], 'the values the screen sends stay')
        self.assertIsNone(ha_catalogue.chip_words(None, 'vacuum.s8', states, device, WORDS))


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class TileMessages(unittest.IsolatedAsyncioTestCase):
    async def test_the_tile_message_carries_the_word_and_the_rounded_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.state_words = WORDS
            ha.states['sensor.living_temperature'] = {'state': '21.456', 'attributes': {'unit_of_measurement': '°C', 'state_class': 'measurement'}}
            ha.registry.append({'entity_id': 'sensor.living_temperature', 'platform': 'demo', 'options': {'sensor': {'display_precision': 1}}})
            ha.states['sensor.washer'] = {'state': 'rinsing', 'attributes': {'device_class': 'enum'}}
            ha.registry.append({'entity_id': 'sensor.washer', 'platform': 'roborock', 'translation_key': 'zeo_state'})
            m = Manager(ha, Path(tmp) / 'screens.json')
            temperature = await m.tile_message(0, {'entity': 'sensor.living_temperature', 'name': ''})
            self.assertEqual((temperature['state'], temperature.get('x', {}).get('w')), ('21.5', None))
            washer = await m.tile_message(1, {'entity': 'sensor.washer', 'name': ''})
            self.assertEqual((washer['state'], washer['x']['w']), ('rinsing', 'Rinsing'))
            curtains = await m.tile_message(2, {'entity': 'cover.curtains', 'name': ''})
            self.assertEqual(curtains['x']['w'], 'Open')
            ha.state_words = {}
            self.assertNotIn('x', await m.tile_message(2, {'entity': 'cover.curtains', 'name': ''}), 'no words: the raw state, as before')

    async def test_the_top_bar_timeline_and_vacuum_card_get_the_words_from_the_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            ha.state_words = WORDS
            ha.states['select.s8_mode'] = {'state': 'vac_and_mop', 'attributes': {'options': ['vacuum', 'vac_and_mop']}}
            ha.states['vacuum.s8'] = {'state': 'docked', 'attributes': {'fan_speed_list': ['balanced', 'off_raise_main_brush']}}
            # The mode select sits on another device here: with one on the robot's device, suction off belongs to Mop.
            ha.registry += [{'entity_id': 'select.s8_mode', 'device_id': 'hall', **CLEANING},
                            {'entity_id': 'vacuum.s8', 'device_id': 's8', 'platform': 'roborock', 'translation_key': 'roborock'}]
            m = Manager(ha, Path(tmp) / 'screens.json')
            layout = {'tiles': [], 'header': {'items': [{'type': 'entity', 'entity': 'select.s8_mode', 'content': 'state', 'icon': 'none', 'show': 'always'}]}}
            self.assertEqual(m.header_message(layout)['items'], [{'k': 'text', 't': 'Vacuum and mop'}])
            vacuum = await m.tile_message(0, {'entity': 'vacuum.s8', 'name': ''})
            self.assertEqual(vacuum['x']['fan']['l'], ['Normal', 'Off (raised brush)'], "the screen's own Normal stays")
            async def state_changes(entity, hours):
                return [(0, 'vacuum'), (60, 'vac_and_mop')]
            ha.state_changes = state_changes
            timeline = await m.build_card_history('select.s8_mode', 24, 'timeline')
            self.assertEqual(dict(timeline['words'])['vac_and_mop'], 'Vacuum and mop')


if __name__ == '__main__':
    unittest.main()
