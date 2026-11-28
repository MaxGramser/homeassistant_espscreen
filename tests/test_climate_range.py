"""A thermostat set to a range (app 0.4.32, firmware 0.19.0): the app sends both ends, and the step Home Assistant's own
controls use when the thermostat names none (1 degree in Fahrenheit, half a degree otherwise)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from core import drawn_controls, state_message  # noqa: E402

ECOBEE = {'climate.ecobee': {'state': 'heat_cool', 'attributes': {
    'supported_features': 442, 'current_temperature': 73, 'target_temp_low': 70, 'target_temp_high': 75, 'min_temp': 45, 'max_temp': 95}}}
TILE = {'entity': 'climate.ecobee', 'name': ''}


class ClimateRange(unittest.TestCase):
    def test_both_ends_go_to_the_screen(self):
        a = state_message(0, TILE, ECOBEE)['a']
        self.assertEqual((a['target_temp_low'], a['target_temp_high']), (70, 75))

    def test_the_step_is_home_assistants_when_the_thermostat_names_none(self):
        self.assertEqual(state_message(0, TILE, ECOBEE, units={'temperature': '°F'})['a']['target_temp_step'], 1)
        self.assertEqual(state_message(0, TILE, ECOBEE, units={'temperature': '°C'})['a']['target_temp_step'], 0.5)
        own = {'climate.ecobee': {**ECOBEE['climate.ecobee'], 'attributes': {**ECOBEE['climate.ecobee']['attributes'], 'target_temp_step': 0.1}}}
        self.assertEqual(state_message(0, TILE, own, units={'temperature': '°F'})['a']['target_temp_step'], 0.1)
        self.assertNotIn('target_temp_step', state_message(0, TILE, ECOBEE)['a'])   # without Home Assistant's units: as before

    def test_a_screen_before_firmware_0_19_gets_no_range_controls_it_would_draw_wrong(self):
        # Backward compatibility: an older screen drew "--" on the -/+ of a thermostat with only a range and stepped from
        # its lowest temperature. It gets the thermostat without them; a screen whose hello says climate_range keeps them.
        tile = {'entity': 'climate.ecobee', 'name': '', 'options': {'size': 'wide', 'controls': 'setpoint'}}
        old = drawn_controls(state_message(0, tile, ECOBEE), features=frozenset({'group_lamps'}))
        self.assertEqual(old['o']['controls'], 'none')
        new = drawn_controls(state_message(0, tile, ECOBEE), features=frozenset({'climate_range'}))
        self.assertEqual(new['o']['controls'], 'setpoint')
        both = drawn_controls(state_message(0, {**tile, 'options': {'size': 'square', 'controls': 'setpoint_mode'}}, ECOBEE), features=frozenset())
        self.assertEqual(both['o']['controls'], 'mode')
        # One with a single temperature is untouched, and so is everything when the screen's hello is not known.
        single = {'climate.ecobee': {'state': 'heat', 'attributes': {**ECOBEE['climate.ecobee']['attributes'], 'supported_features': 385, 'temperature': 21}}}
        self.assertEqual(drawn_controls(state_message(0, tile, single), features=frozenset())['o']['controls'], 'setpoint')
        self.assertEqual(drawn_controls(state_message(0, tile, ECOBEE), features=None)['o']['controls'], 'setpoint')
        # A thermostat without a temperature to set (a fan-only device) never gets the -/+, on any screen.
        fan = {'climate.ecobee': {'state': 'fan_only', 'attributes': {'supported_features': 8, 'current_temperature': 21}}}
        self.assertEqual(drawn_controls(state_message(0, tile, fan), features=None)['o']['controls'], 'none')


if __name__ == '__main__':
    unittest.main()
