"""A device's extras in the editor's library (docs/PAGES.md, "The library"): what Home Assistant's device page puts apart
from the controls, a setting (entity_category config), a reading for diagnosis and an entity hidden there, reaches the
editor marked, so the library lists it folded under the rest of its room. Everything else reaches it as before."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import discover  # noqa: E402


def entities(registry):
    states = {item['entity_id']: {'entity_id': item['entity_id'], 'state': 'on', 'attributes': {}} for item in registry}
    return {e['id']: e for e in discover(registry, states, [], [])[1]}


class LibraryExtrasTest(unittest.TestCase):
    def test_settings_diagnosis_and_hidden_entities_are_marked(self):
        found = entities([
            {'entity_id': 'light.hue', 'platform': 'hue'},
            {'entity_id': 'select.hue_power_on', 'platform': 'hue', 'entity_category': 'config'},
            {'entity_id': 'sensor.hue_signal', 'platform': 'hue', 'entity_category': 'diagnostic'},
            {'entity_id': 'switch.hidden', 'platform': 'demo', 'hidden_by': 'user'},
        ])
        self.assertNotIn('category', found['light.hue'])
        self.assertNotIn('hidden', found['light.hue'])
        self.assertEqual(found['select.hue_power_on']['category'], 'config')
        self.assertEqual(found['sensor.hue_signal']['category'], 'diagnostic')
        self.assertIs(found['switch.hidden']['hidden'], True)

    def test_a_disabled_entity_stays_out(self):
        self.assertNotIn('switch.off', entities([{'entity_id': 'switch.off', 'platform': 'demo', 'disabled_by': 'user'}]))


if __name__ == '__main__':
    unittest.main()
