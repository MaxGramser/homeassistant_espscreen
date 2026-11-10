"""What the library's search knows of an entity beside its name: what it measures, in Home Assistant's own words."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import discover, kind_words  # noqa: E402

KEY = 'component.sensor.entity_component.temperature.name'


class KindWords(unittest.TestCase):
    def test_a_device_class_in_each_language_the_app_holds(self):
        words = kind_words('sensor.a1', {'device_class': 'temperature'}, [{KEY: 'Temperatuur'}, {KEY: 'Temperature'}])
        self.assertEqual(words, 'temperature Temperatuur Temperature')

    def test_without_home_assistants_words_the_device_class_itself(self):
        self.assertEqual(kind_words('binary_sensor.d', {'device_class': 'garage_door'}, []), 'garage door')

    def test_nothing_for_an_entity_without_a_device_class(self):
        self.assertEqual(kind_words('light.a', {}, [{KEY: 'Temperatuur'}]), '')
        self.assertEqual(kind_words('light.a', None, []), '')

    def test_the_inventory_carries_them_only_where_there_are_any(self):
        states = {'sensor.a1': {'state': '21', 'attributes': {'device_class': 'temperature'}},
                  'light.a': {'state': 'on', 'attributes': {}}}
        registry = [{'entity_id': 'sensor.a1'}]
        _, entities = discover(registry, states, [], [], [{KEY: 'Temperatuur'}])
        by_id = {entity['id']: entity for entity in entities}
        self.assertEqual(by_id['sensor.a1']['words'], 'temperature Temperatuur')
        self.assertNotIn('words', by_id['light.a'])


if __name__ == '__main__':
    unittest.main()
