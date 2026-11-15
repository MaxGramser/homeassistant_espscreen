"""The facts a first layout reads of a home (home_facts.py, docs/AUTO_LAYOUT.md): what the registries say beside the
inventory, in Home Assistant's order, with the screens' own entities marked and nothing disabled."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import home_facts  # noqa: E402

REGISTRY = [
    {'entity_id': 'light.living_ceiling', 'device_id': 'd-lamp', 'platform': 'hue'},
    {'entity_id': 'light.living', 'area_id': 'living', 'platform': 'group'},
    {'entity_id': 'sensor.lamp_signal', 'device_id': 'd-lamp', 'entity_category': 'diagnostic', 'platform': 'hue'},
    {'entity_id': 'switch.lamp_hidden', 'device_id': 'd-lamp', 'hidden_by': 'user', 'platform': 'hue'},
    {'entity_id': 'switch.gone', 'device_id': 'd-lamp', 'disabled_by': 'user'},
    {'entity_id': 'switch.screen_backlight', 'device_id': 'd-screen', 'platform': 'esphome'},
    {'entity_id': 'device_tracker.phone', 'platform': 'mobile_app'},
]
STATES = {
    'light.living_ceiling': {'state': 'on', 'attributes': {'supported_features': 44}},
    'light.living': {'state': 'on', 'attributes': {'entity_id': ['light.living_ceiling', 'light.living_floor']}},
    'sensor.lamp_signal': {'state': '-60', 'attributes': {'device_class': 'signal_strength', 'unit_of_measurement': 'dBm'}},
    'sensor.outdoor': {'state': '12', 'attributes': {'device_class': 'temperature', 'state_class': 'measurement', 'unit_of_measurement': '°C'}},
}
DEVICES = [{'id': 'd-lamp', 'name': 'Ceiling', 'name_by_user': 'Big lamp', 'area_id': 'living', 'model': 'LCT015', 'manufacturer': 'Signify'},
           {'id': 'd-screen', 'name': 'Hall screen', 'area_id': 'hall'}, {'id': 'd-unused', 'name': 'Elsewhere'}]
AREAS = [{'area_id': 'living', 'name': 'Living room', 'floor_id': 'ground', 'icon': 'mdi:sofa', 'temperature_entity_id': 'sensor.outdoor'},
         {'area_id': 'hall', 'name': 'Hall'}]
FLOORS = [{'floor_id': 'ground', 'name': 'Ground floor', 'level': 0}]


class HomeFacts(unittest.TestCase):
    def setUp(self):
        self.found = home_facts.facts(REGISTRY, STATES, DEVICES, AREAS, FLOORS, {'d-screen'})
        self.by_id = {e['id']: e for e in self.found['entities']}

    def test_an_entity_takes_its_devices_area(self):
        self.assertEqual(self.by_id['light.living_ceiling']['area'], 'living')
        self.assertEqual(self.by_id['light.living_ceiling']['features'], 44)

    def test_categories_hidden_and_screens_are_marked_not_dropped(self):
        self.assertEqual(self.by_id['sensor.lamp_signal']['category'], 'diagnostic')
        self.assertTrue(self.by_id['switch.lamp_hidden']['hidden'])
        self.assertTrue(self.by_id['switch.screen_backlight']['screen'])

    def test_disabled_and_untileable_entities_are_left_out(self):
        self.assertNotIn('switch.gone', self.by_id)
        self.assertNotIn('device_tracker.phone', self.by_id)

    def test_a_group_lists_its_members(self):
        self.assertEqual(self.by_id['light.living']['members'], ['light.living_ceiling', 'light.living_floor'])

    def test_an_entity_without_registry_entry_keeps_its_state_facts(self):
        self.assertEqual(self.by_id['sensor.outdoor'], {'id': 'sensor.outdoor', 'area': '', 'device': '', 'class': 'temperature',
                                                        'stateClass': 'measurement', 'unit': '°C'})

    def test_areas_floors_and_devices(self):
        self.assertEqual(self.found['areas'][0], {'id': 'living', 'name': 'Living room', 'floor': 'ground', 'icon': 'mdi:sofa',
                                                  'temperature': 'sensor.outdoor'})
        self.assertEqual([a['id'] for a in self.found['areas']], ['living', 'hall'])
        self.assertEqual(self.found['floors'], [{'id': 'ground', 'name': 'Ground floor', 'level': 0}])
        self.assertEqual(self.found['devices']['d-lamp'], {'name': 'Big lamp', 'area': 'living', 'model': 'LCT015', 'maker': 'Signify'})
        self.assertNotIn('d-unused', self.found['devices'])


if __name__ == '__main__':
    unittest.main()
