"""Issue #314: climate entities with preset modes (state message attributes, catalogue offers, and icon glyphs)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
import core  # noqa: E402
import tile_icons  # noqa: E402


class ClimatePresets(unittest.TestCase):
    def test_state_message_includes_preset_modes_for_climate_only(self):
        states = {
            'climate.chambre_ami': {
                'state': 'heat',
                'attributes': {
                    'friendly_name': 'Chambre Ami',
                    'supported_features': 17,
                    'hvac_modes': ['off', 'heat'],
                    'preset_modes': ['none', 'eco', 'comfort', 'boost'],
                    'preset_mode': 'comfort',
                    'temperature': 20,
                },
            },
            'fan.bedroom': {
                'state': 'on',
                'attributes': {
                    'friendly_name': 'Bedroom Fan',
                    'supported_features': 9,
                    'preset_modes': ['nature', 'sleep'],
                    'preset_mode': 'nature',
                },
            },
        }
        climate_msg = core.state_message(0, {'entity': 'climate.chambre_ami', 'name': '', 'options': {}}, states)
        self.assertEqual(climate_msg['a']['preset_mode'], 'comfort')
        self.assertEqual(climate_msg['a']['preset_modes'], ['none', 'eco', 'comfort', 'boost'])

        fan_msg = core.state_message(1, {'entity': 'fan.bedroom', 'name': '', 'options': {}}, states)
        self.assertNotIn('preset_mode', fan_msg['a'])
        self.assertNotIn('preset_modes', fan_msg['a'])

    def test_catalogue_offers_mode_and_setpoint_mode_for_preset_thermostats(self):
        state = {'state': 'heat', 'attributes': {'supported_features': 17, 'hvac_modes': ['heat'], 'preset_modes': ['eco', 'comfort']}}
        offered = catalogue.offers('climate.heater', state, {'climate.set_temperature', 'climate.set_preset_mode'})
        self.assertIn('mode', offered['controls'])
        self.assertIn('setpoint_mode', offered['controls'])

    def test_preset_icons_are_present_in_font_glyphs(self):
        codepoints = dict(tile_icons.ALL_CODEPOINTS) if hasattr(tile_icons, 'ALL_CODEPOINTS') else {
            name: cp for _, items in tile_icons.GROUPS for name, cp, _ in items
        } | dict(tile_icons.FIXED) | dict(tile_icons.HA_DEFAULTS)
        expected = {
            'close-circle-outline': 'F015A',
            'leaf': 'F032A',
            'account-arrow-right': 'F0B53',
            'rocket-launch': 'F14DE',
            'sofa': 'F04B9',
            'home': 'F02DC',
            'power-sleep': 'F0904',
            'motion-sensor': 'F0D91',
            'circle-medium': 'F09DE',
        }
        for name, cp in expected.items():
            self.assertEqual(codepoints.get(name), cp, name)


if __name__ == '__main__':
    unittest.main()
