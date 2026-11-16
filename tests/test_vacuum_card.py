"""Vacuum card rows (app 0.2.46 / firmware 0.2.39): the cleaning mode and water selects of the robot's
device, the suction speeds to offer and the battery sensor, as Home Assistant 2026.9 reports a Roborock."""
from manager_fixtures import with_screen_grid
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from core import encode, extras, state_message, vacuum_related

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager
    from test_scaling import fake_ha

VACUUM = 'vacuum.s8'


def roborock():
    """(states, device registry entries) of a Roborock S8 on HA 2026.9.1 in Dutch, as read from a real home:
    entity ids in the UI language, no battery attribute on the vacuum, the mop settings as selects."""
    states = {
        VACUUM: {'state': 'docked', 'attributes': {'friendly_name': 'Pippa', 'fan_speed': 'max', 'supported_features': 30524,
                                                  'fan_speed_list': ['quiet', 'balanced', 'turbo', 'max', 'max_plus', 'off', 'custom']}},
        'select.woonkamer_s8_schoonmaakmodus': {'state': 'vac_and_mop', 'attributes': {'options': ['vacuum', 'vac_and_mop', 'mop', 'custom']}},
        'select.s8_intensiteit_van_dweilen': {'state': 'intense', 'attributes': {'options': ['off', 'mild', 'standard', 'intense', 'custom']}},
        'select.s8_mop_mode': {'state': 'standard', 'attributes': {'options': ['standard', 'deep', 'deep_plus', 'fast', 'custom']}},
        'select.s8_selected_map': {'state': 'Thuis', 'attributes': {'options': ['Thuis']}},
        'sensor.s8_batterij': {'state': '78', 'attributes': {'device_class': 'battery', 'unit_of_measurement': '%'}},
        'binary_sensor.s8_opladen': {'state': 'on', 'attributes': {'device_class': 'battery_charging'}},
        'sensor.s8_huidige_kamer': {'state': 'Living room', 'attributes': {'device_class': 'enum', 'options': ['Corridor', 'Kitchen', 'Living room', 'Bedroom']}},
        'sensor.s8_status': {'state': 'charging', 'attributes': {'device_class': 'enum'}},
        'button.s8_vac_followed_by_mop': {'state': 'unknown', 'attributes': {}},
    }
    keys = {VACUUM: 'roborock', 'select.woonkamer_s8_schoonmaakmodus': 'cleaning_mode', 'select.s8_intensiteit_van_dweilen': 'mop_intensity',
            'select.s8_mop_mode': 'mop_mode', 'select.s8_selected_map': 'selected_map', 'sensor.s8_batterij': None,
            'binary_sensor.s8_opladen': None, 'sensor.s8_huidige_kamer': 'current_room', 'sensor.s8_status': 'status',
            'button.s8_vac_followed_by_mop': None}
    device = [{'entity_id': eid, 'platform': 'roborock', 'device_id': 'robot', 'translation_key': key} for eid, key in keys.items()]
    return states, device


class VacuumExtras(unittest.TestCase):
    def test_roborock_gets_mode_water_suction_battery_charging_and_room(self):
        states, device = roborock()
        extra = extras({'entity': VACUUM}, states, device=device)
        self.assertEqual(extra['mode'], {'e': 'select.woonkamer_s8_schoonmaakmodus', 's': 'vac_and_mop', 'o': ['vacuum', 'vac_and_mop', 'mop'],
                                         'l': ['Vacuum', 'Vac & mop', 'Mop'], 'r': 'vbm'}, 'Custom runs app settings: only listed while in use')
        self.assertEqual(extra['water'], {'e': 'select.s8_intensiteit_van_dweilen', 's': 'intense', 'o': ['mild', 'standard', 'intense'],
                                          'l': ['Mild', 'Standard', 'Intense']}, 'off and custom belong to the cleaning modes')
        self.assertEqual(extra['fan'], {'o': ['quiet', 'balanced', 'turbo', 'max', 'max_plus'], 'l': ['Quiet', 'Normal', 'Turbo', 'Max', 'Max+']})
        self.assertEqual((extra['bat'], extra['chg'], extra['room']), (78, 1, 'Living room'))
        message = state_message(0, {'entity': VACUUM, 'name': 'Stofzuiger'}, states, extra)
        self.assertEqual(message['a']['fan_speed_list'], ['quiet', 'balanced', 'turbo', 'max'], 'older firmware keeps its four speeds')
        self.assertLess(len(encode(message)), 1024)
        # Custom in use: listed, so the card shows what the robot does.
        states['select.woonkamer_s8_schoonmaakmodus']['state'] = 'custom'
        states['binary_sensor.s8_opladen']['state'] = 'off'
        extra = extras({'entity': VACUUM}, states, device=device)
        self.assertEqual((extra['mode']['o'], extra['mode']['r']), (['vacuum', 'vac_and_mop', 'mop', 'custom'], 'vbma'))
        self.assertNotIn('chg', extra)

    def test_without_a_mode_select_water_and_suction_keep_off(self):
        states, device = roborock()
        device = [d for d in device if d['translation_key'] != 'cleaning_mode']
        extra = extras({'entity': VACUUM}, states, device=device)
        self.assertNotIn('mode', extra)
        self.assertEqual(extra['water']['o'], ['off', 'mild', 'standard', 'intense', 'custom'], 'water off is the only way to vacuum only')
        self.assertEqual(extra['fan']['o'], ['quiet', 'balanced', 'turbo', 'max', 'max_plus', 'off'], 'suction off is the only way to mop only')

    def test_a_plain_vacuum_gets_only_its_labelled_speeds(self):
        states = {'vacuum.old': {'state': 'docked', 'attributes': {'battery_level': 64, 'fan_speed_list': ['silent', 'standard', 'strong']}}}
        self.assertEqual(extras({'entity': 'vacuum.old'}, states), {'fan': {'o': ['silent', 'standard', 'strong'], 'l': ['Silent', 'Standard', 'Strong']}},
                         'no device, no rows; a battery attribute needs no sensor')
        states['vacuum.old']['attributes'].pop('fan_speed_list')
        self.assertIsNone(extras({'entity': 'vacuum.old'}, states))

    def test_entity_id_endings_disabled_entities_and_unknown_modes(self):
        states = {
            'vacuum.deebot': {'state': 'cleaning', 'attributes': {}},
            'select.deebot_work_mode': {'state': 'mop_after_vacuum', 'attributes': {'options': ['vacuum', 'mop', 'vacuum_and_mop', 'mop_after_vacuum', 'scrubbing']}},
            'select.deebot_water_flow_level': {'state': 'high', 'attributes': {'options': ['low', 'medium', 'high', 'ultrahigh']}},
            'select.old_cleaning_mode': {'state': 'x', 'attributes': {'options': ['x']}},
            'sensor.deebot_battery': {'state': 'unavailable', 'attributes': {'device_class': 'battery'}},
        }
        device = [{'entity_id': 'vacuum.deebot', 'device_id': 'd'},
                  {'entity_id': 'select.old_cleaning_mode', 'device_id': 'd', 'translation_key': 'cleaning_mode', 'disabled_by': 'user'},
                  {'entity_id': 'select.deebot_work_mode', 'device_id': 'd'},
                  {'entity_id': 'select.deebot_water_flow_level', 'device_id': 'd'},
                  {'entity_id': 'sensor.deebot_battery', 'device_id': 'd'}]
        self.assertEqual(vacuum_related('vacuum.deebot', device, states),
                         {'mode': 'select.deebot_work_mode', 'water': 'select.deebot_water_flow_level', 'battery': 'sensor.deebot_battery'})
        extra = extras({'entity': 'vacuum.deebot'}, states, device=device)
        self.assertEqual(extra['mode']['l'], ['Vacuum', 'Mop', 'Vac & mop', 'Vac, then mop', 'Scrubbing'])
        self.assertEqual(extra['mode']['r'], 'vmbbb')
        self.assertEqual(extra['water']['l'], ['Low', 'Medium', 'High', 'Ultra high'])
        self.assertNotIn('bat', extra, 'an unavailable battery sends nothing')

    def test_options_are_bounded(self):
        states, device = roborock()
        states['select.woonkamer_s8_schoonmaakmodus']['attributes']['options'] = [f'mode_{i}' for i in range(12)]
        extra = extras({'entity': VACUUM}, states, device=device)
        self.assertEqual(len(extra['mode']['o']), 6)
        self.assertEqual(extra['mode']['l'][0], 'Mode 0')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class VacuumSync(unittest.IsolatedAsyncioTestCase):
    async def test_a_select_change_resends_the_vacuum_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = fake_ha()
            states, device = roborock()
            ha.states.update(states)
            ha.registry = ha.registry + device
            m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
            m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': VACUUM, 'name': ''}, {'entity': 'light.a', 'name': ''}]})
            layout = m.layouts['text.screen']
            watched = m.watched_entities()
            self.assertTrue({'select.woonkamer_s8_schoonmaakmodus', 'select.s8_intensiteit_van_dweilen', 'sensor.s8_batterij', 'binary_sensor.s8_opladen', 'sensor.s8_huidige_kamer'} <= watched)
            self.assertNotIn('select.s8_mop_mode', watched)
            await m.sync_one('text.screen', layout, dirty=set())
            sent = [msg for _, msg, _ in ha.messages if msg.get('entity') == VACUUM]
            self.assertEqual(sent[0]['x']['mode']['s'], 'vac_and_mop')
            ha.messages.clear()
            # Mop only in the Roborock app: the select changes, the vacuum entity itself does not.
            ha.states['select.woonkamer_s8_schoonmaakmodus']['state'] = 'mop'
            self.assertTrue(await m.sync_one('text.screen', layout, dirty={'select.woonkamer_s8_schoonmaakmodus'}))
            self.assertEqual([(msg['op'], msg.get('entity')) for _, msg, _ in ha.messages], [('state', VACUUM)])
            self.assertEqual(ha.messages[0][1]['x']['mode']['s'], 'mop')
            ha.messages.clear()
            self.assertFalse(await m.sync_one('text.screen', layout, dirty={'select.s8_mop_mode'}), 'the route is not on the card')


if __name__ == '__main__':
    unittest.main()
