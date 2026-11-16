"""Tiles take Home Assistant's state colours and its rule for what is off (app 0.2.85 / firmware 0.2.71).

Home Assistant's frontend decides with stateActive() (src/common/entity/state_active.ts) whether a card shows an
entity in its colour or grey, and stateColorCss() (src/common/entity/state_color.ts) picks the colour from the
--state-*-color variables of its theme. The screen ports both: Tile::active() and tile_controls::accent(), checked state
by state in tests/test_runtime_model.cpp and tests/test_tile_controls.cpp (which also checks the alarm classes, every
weather condition and a lamp's contrast rule); tests/test_theme.cpp holds Home Assistant's palette as static_asserts;
web/wasm/test_state_look.mjs reads the real cards (off is grey, on is coloured, a lamp's own colour, a slider, an airco
that is off, a card over the whole page). Here: the add-on's side, the top bar.
"""
from firmware_sources import runtime_source
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import tile_icons  # noqa: E402

# The binary sensor classes with a red --state-binary_sensor-<class>-on-color in Home Assistant's theme.
HA_ALARM_CLASSES = {'battery', 'carbon_monoxide', 'gas', 'heat', 'lock', 'moisture', 'problem', 'safety', 'smoke', 'sound',
                    'tamper'}
# Home Assistant's weather conditions (weather/const.py ATTR_CONDITION_*), which tests/test_tile_controls.cpp walks too.
HA_CONDITIONS = {'clear-night', 'cloudy', 'exceptional', 'fog', 'hail', 'lightning', 'lightning-rainy', 'partlycloudy', 'pouring',
                 'rainy', 'snowy', 'snowy-rainy', 'sunny', 'windy', 'windy-variant'}


class StateColours(unittest.TestCase):
    def test_alarms_are_red_in_the_top_bar(self):
        self.assertEqual(set(header_bar.ALARM_CLASSES), HA_ALARM_CLASSES)
        for device_class in sorted(HA_ALARM_CLASSES):
            state = {'state': 'on', 'attributes': {'device_class': device_class}}
            self.assertEqual(header_bar.accent('binary_sensor.a', state), header_bar.RED, device_class)
        self.assertEqual(header_bar.accent('binary_sensor.a', {'state': 'on', 'attributes': {'device_class': 'door'}}),
                         header_bar.AMBER)

    def test_the_add_on_knows_every_weather_condition(self):
        self.assertEqual(set(tile_icons.WEATHER), HA_CONDITIONS)

    def test_a_camera_picture_smaller_than_its_card_is_dark_around_it(self):
        # Kept as a quote: the firmware preview asks no picture for a camera tile, so it cannot show a picture smaller
        # than its card (the picture cap, firmware 0.9.0) yet; to be replaced by the host render (tools/render).
        self.assertIn('press_ground(w.tile,letterboxed(w)?theme::color(theme::CAMERA_PAGE):lv_color_hex(theme::surface(',
                      runtime_source())


if __name__ == '__main__':
    unittest.main()
