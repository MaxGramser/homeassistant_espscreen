"""A humidifier or dehumidifier as a tile (firmware 0.42.0, GitHub #128): the thermostat's parts in percent, its modes and
its action as Home Assistant has them (its 2026.10 core: humidifier/__init__.py, const.py, icons.json; frontend:
more-info-humidifier.ts, ha-state-control-humidifier-humidity.ts). tests/test_tile_controls.cpp checks the firmware's
words, keys and actions; these keep the app in step with it and with Home Assistant.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
import core  # noqa: E402
import header_bar  # noqa: E402
import tile_icons  # noqa: E402

LAUNDRY = {'state': 'on', 'attributes': {
    'friendly_name': 'Laundry room', 'device_class': 'dehumidifier', 'action': 'drying', 'current_humidity': 68,
    'humidity': 55, 'min_humidity': 30, 'max_humidity': 80, 'available_modes': ['normal', 'away'], 'mode': 'normal',
    'supported_features': 1}}


class TheApp(unittest.TestCase):
    def test_a_humidifier_is_a_tile_from_firmware_0_40_0(self):
        self.assertIn('humidifier', core.DOMAINS)
        self.assertEqual(catalogue.of_type('humidifier')['firmware'], '0.42.0')

    def test_the_screen_gets_what_it_draws(self):
        message = core.state_message(0, {'entity': 'humidifier.laundry', 'name': ''}, {'humidifier.laundry': LAUNDRY})
        a = message['a']
        self.assertEqual((a['humidity'], a['current_humidity'], a['min_humidity'], a['max_humidity']), (55, 68, 30, 80))
        self.assertEqual((a['available_modes'], a['mode'], a['action']), (['normal', 'away'], 'normal', 'drying'))

    def test_only_a_humidifier_sends_its_own_attributes(self):
        # An automation has a `mode` too (single, restart): it means something else and stays behind.
        automation = {'state': 'on', 'attributes': {'mode': 'single', 'current': 0}}
        message = core.state_message(0, {'entity': 'automation.lights', 'name': ''}, {'automation.lights': automation})
        self.assertNotIn('mode', message['a'])

    def test_controls_follow_home_assistants_actions(self):
        controls = {control['key']: control for control in catalogue.of_type('humidifier')['controls']}
        self.assertEqual(list(controls), ['setpoint', 'slider', 'mode', 'setpoint_mode', 'toggle'])
        # The modes only where Home Assistant registers set_mode for it: with MODES.
        self.assertEqual(controls['mode']['needs'], {'actions': [{'action': 'humidifier.set_mode'}], 'features': ['MODES']})

    def test_icons_and_colours_are_home_assistants(self):
        self.assertEqual(tile_icons.DEFAULTS['humidifier'], 'air-humidifier')
        self.assertIn('air-humidifier-off', tile_icons.BIG_GLYPHS)
        for icon in ('water-percent', 'leaf', 'account-arrow-right', 'rocket-launch', 'sofa', 'home', 'power-sleep',
                     'refresh-auto', 'baby-carriage', 'circle-medium'):
            self.assertIn(icon, tile_icons.GLYPHS)
        self.assertEqual(header_bar.DOMAIN_ICONS['humidifier'], 'air-humidifier')
        self.assertEqual(header_bar.accent('humidifier.a', {'state': 'on'}), header_bar.BLUE)
        self.assertIsNone(header_bar.accent('humidifier.a', {'state': 'off'}))


if __name__ == '__main__':
    unittest.main()
