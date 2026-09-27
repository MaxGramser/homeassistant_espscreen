"""Tiles take Home Assistant's state colours and its rule for what is off (app 0.2.85 / firmware 0.2.71).

Home Assistant's frontend decides with stateActive() (src/common/entity/state_active.ts) whether a card shows an
entity in its colour or grey, and stateColorCss() (src/common/entity/state_color.ts) picks the colour from the
--state-*-color variables of its theme. The screen ports both: Tile::active() and tile_controls::accent(). These
checks keep the tables in step with each other and with Home Assistant's palette; tests/test_runtime_model.cpp and
tests/test_tile_controls.cpp check the rules state by state.
"""
from firmware_sources import runtime_source
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import tile_icons  # noqa: E402

COMPONENT = ROOT / 'components/smart_display'
CONTROLS = (COMPONENT / 'tile_controls.h').read_text()
TILES = runtime_source()
MODEL = (COMPONENT / 'runtime_model.h').read_text()
THEME = (COMPONENT / 'theme.h').read_text()

# Home Assistant's palette (frontend src/resources/theme/color/color.globals.ts), as its 2026.9 frontend serves it.
HA_PALETTE = {'RED': 'F44336', 'PURPLE': '926BC7', 'DEEP_PURPLE': '6E41AB', 'INDIGO': '3F51B5', 'BLUE': '2196F3',
              'LIGHT_BLUE': '03A9F4', 'CYAN': '00BCD4', 'TEAL': '009688', 'GREEN': '4CAF50', 'LIME': 'CDDC39',
              'YELLOW': 'FFEB3B', 'AMBER': 'FFC107', 'ORANGE': 'FF9800', 'DEEP_ORANGE': 'FF6F22', 'LIGHT_GREY': 'BDBDBD',
              'GREY': '9E9E9E', 'BLUE_GREY': '607D8B', 'ICE': 'C0E0FF'}
# The binary sensor classes with a red --state-binary_sensor-<class>-on-color in that theme.
HA_ALARM_CLASSES = {'battery', 'carbon_monoxide', 'gas', 'heat', 'lock', 'moisture', 'problem', 'safety', 'smoke', 'sound',
                    'tamper'}


def function(source, signature):
    return source.split(signature, 1)[1].split('\n}\n', 1)[0]


class StateColours(unittest.TestCase):
    def test_the_theme_holds_home_assistants_palette(self):
        ha = THEME.split('namespace ha {', 1)[1].split('}  // namespace ha', 1)[0]
        values = dict(re.findall(r'\b([A-Z_]+) = 0x([0-9A-F]{6})', ha))
        for name, value in HA_PALETTE.items():
            self.assertEqual(values.get(name), value, name)

    def test_alarms_are_red_on_the_tile_and_in_the_top_bar(self):
        firmware = set(re.findall(r'"(\w+)"', function(CONTROLS, 'inline bool alarm_class(const std::string &device_class) {')))
        self.assertEqual(firmware, HA_ALARM_CLASSES)
        self.assertEqual(set(header_bar.ALARM_CLASSES), HA_ALARM_CLASSES)
        for device_class in sorted(HA_ALARM_CLASSES):
            state = {'state': 'on', 'attributes': {'device_class': device_class}}
            self.assertEqual(header_bar.accent('binary_sensor.a', state), header_bar.RED, device_class)
        self.assertEqual(header_bar.accent('binary_sensor.a', {'state': 'on', 'attributes': {'device_class': 'door'}}),
                         header_bar.AMBER)

    def test_every_weather_condition_has_its_colour(self):
        body = function(CONTROLS, 'inline uint32_t weather_color(const std::string &condition) {')
        self.assertEqual(set(re.findall(r'condition == "([\w-]+)"', body)), set(tile_icons.WEATHER))

    def test_the_tile_greys_and_lights_up_by_home_assistants_rule(self):
        self.assertIn('uint32_t accent=tile_controls::accent(t);', TILES)
        # A full-page card is white or its own pastel like every other card (firmware 0.2.77+; 0.2.62-0.2.76 tinted it).
        self.assertNotIn('lights_up()', TILES)
        self.assertNotIn('lights_up', MODEL)
        self.assertIn('press_ground(w.tile,lv_color_hex(theme::surface(t.background)));', TILES)
        self.assertIn('const uint32_t fill=slider_on?accent:theme::STATE_OFF;', TILES)
        self.assertNotIn('domain_accent', TILES)
        self.assertIn('frontend src/common/entity/state_active.ts', MODEL)

    def test_a_pale_lamp_takes_home_assistants_contrast_rule(self):
        # Home Assistant lifts a lamp colour under 40 % saturation to 40 % before it paints a tile
        # (hui-tile-card._computeStateColor). Under 10 % there is nothing left to lift and it only dims the white,
        # which on a dark card or a card with a colour of its own says what the grey of something off says, so such
        # a lamp keeps the amber of tile_controls::accent (firmware 0.2.98+).
        # Since firmware 0.4.0 the rule lives once in tile_controls::lamp_color, which the lamp page of a group asks
        # too, with LVGL's own conversion ported bit for bit (tests/test_group_page.cpp checks both).
        self.assertIn('if(d=="light" && on && t.has_hs_color)\n    accent=tile_controls::lamp_color(t.hue,t.saturation);', TILES)
        self.assertIn('if (saturation < 10) return theme::ha::AMBER;', CONTROLS)
        self.assertIn('std::min(100, std::max(40, saturation))', CONTROLS)

    def test_an_airco_that_is_off_says_so(self):
        self.assertIn('else if (d == "climate" && t.state == "off") { value = tile_controls::climate_mode_text(t.state);', TILES)
        off = TILES.index('d == "climate" && t.state == "off"')
        self.assertLess(off, TILES.index('d == "climate" && std::isfinite(t.target)'), 'before the setpoint line')


if __name__ == '__main__':
    unittest.main()
