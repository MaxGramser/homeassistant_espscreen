"""The tile catalogue's memory prices (firmware 0.34.0+, docs/TILE_MEMORY.md): every type states one, the add-on prices a
tile as the screen does, and the cases the three readers answer alike are current."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
from core import layout_cost, tile_cost  # noqa: E402

PSRAM = {'room': 50000, 'used': 0, 'psram': True, 'tile': 524, 'extra': 1056, 'page': 336}
INSIDE = {**PSRAM, 'psram': False}


class Prices(unittest.TestCase):
    def test_every_type_states_its_price(self):
        for domain, data in catalogue.TYPES.items():
            self.assertEqual(set(data['memory']), {'bytes', 'extras'}, domain)
            self.assertGreater(data['memory']['bytes'], 0, domain)
        self.assertEqual(set(catalogue.CHOICE_MEMORY), {'action', 'line', 'page', 'bar_text', 'section'})

    def test_a_tile_costs_its_type_its_choices_and_without_psram_itself(self):
        weather, switch = catalogue.MEMORY['weather'], catalogue.MEMORY['switch']
        self.assertEqual(tile_cost({'entity': 'weather.home'}, PSRAM), weather['bytes'])
        self.assertEqual(tile_cost({'entity': 'weather.home'}, INSIDE), weather['bytes'] + 524 + (1056 if weather['extras'] else 0))
        acting = {'entity': 'switch.a', 'options': {'tap': 'action', 'sub': 'attr:power'}}
        self.assertEqual(tile_cost(acting, INSIDE), switch['bytes'] + catalogue.CHOICE_MEMORY['action'] + catalogue.CHOICE_MEMORY['line'] + 524 + 1056)
        self.assertEqual(tile_cost({'entity': 'nonsense.a'}, PSRAM), catalogue.DEAREST['bytes'])
        self.assertEqual(layout_cost([{'entity': 'weather.a'}, {'entity': 'switch.b'}], PSRAM), weather['bytes'] + switch['bytes'])

    def test_every_price_is_near_its_estimate(self):
        # tools/estimate_tile_memory.py prices a type's rich example from the add-on's own message and the firmware's own
        # source (what page_receiver.cpp reads and keeps). A price far below its estimate is a firmware that keeps more
        # than the catalogue says: measure the type again (docs/TILE_MEMORY.md) and write its new price. Far above is a
        # price that can come down. A type of the screen's own (screen.*) keeps next to nothing and takes the floor.
        spec = importlib.util.spec_from_file_location('estimate_tile_memory', ROOT / 'tools/estimate_tile_memory.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        examples = __import__('json').loads(module.EXAMPLES.read_text())
        self.assertEqual(set(examples), set(catalogue.TYPES), 'every type has an example in tools/tile_memory_examples.json')
        for domain, estimate in module.estimates(examples).items():
            price = catalogue.MEMORY[domain]['bytes']
            with self.subTest(domain=domain, price=price, estimate=estimate):
                self.assertLessEqual(abs(price - estimate), max(48, estimate * 0.15))

    def test_the_cases_the_screen_and_the_editor_check_are_current(self):
        spec = importlib.util.spec_from_file_location('memory_conformance', ROOT / 'tests/memory_conformance.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.FIXTURE.read_text(), module.output(), 'run tests/memory_conformance.py')


if __name__ == '__main__':
    unittest.main()
