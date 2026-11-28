"""Home Assistant's default icons on tiles and in the top bar (app 0.2.67, firmware 0.2.58). ICONS is a subset of what
Home Assistant 2026.9.2 answers frontend/get_icons with; the firmware fonts carry the icons Home Assistant uses for the
domains a screen shows, so a closed blind, a playing speaker and a door that is open look as they do in Home Assistant."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import tile_icons  # noqa: E402
import header_bar  # noqa: E402
from core import discover, screen_options  # noqa: E402

ICONS = json.loads('''{"entity_component":{"cover":{"_":{"default":"mdi:window-open","state":{"closed":"mdi:window-closed","closing":"mdi:arrow-down-box","opening":"mdi:arrow-up-box"}},"blind":{"default":"mdi:blinds-horizontal","state":{"closed":"mdi:blinds-horizontal-closed","closing":"mdi:arrow-down-box","opening":"mdi:arrow-up-box"}},"garage":{"default":"mdi:garage-open","state":{"closed":"mdi:garage","closing":"mdi:arrow-down-box","opening":"mdi:arrow-up-box"}}},"light":{"_":{"default":"mdi:lightbulb","state":{"off":"mdi:lightbulb-off"}}},"climate":{"_":{"default":"mdi:thermostat"}},"scene":{"_":{"default":"mdi:palette"}},"script":{"_":{"default":"mdi:script-text","state":{"on":"mdi:script-text-play"}}},"binary_sensor":{"_":{"default":"mdi:radiobox-blank","state":{"on":"mdi:checkbox-marked-circle"}},"door":{"default":"mdi:door-closed","state":{"on":"mdi:door-open"}},"smoke":{"default":"mdi:smoke-detector-variant","state":{"on":"mdi:smoke-detector-variant-alert"}}},"sensor":{"_":{"default":"mdi:eye"},"temperature":{"default":"mdi:thermometer"},"battery":{"default":"mdi:battery-unknown","range":{"0":"mdi:battery-alert","10":"mdi:battery-10","20":"mdi:battery-20","30":"mdi:battery-30","40":"mdi:battery-40","50":"mdi:battery-50","60":"mdi:battery-60","70":"mdi:battery-70","80":"mdi:battery-80","90":"mdi:battery-90","100":"mdi:battery"}},"wind_direction":{"default":"mdi:compass-rose","range":{"0":"mdi:arrow-down","22.5":"mdi:arrow-bottom-left","67.5":"mdi:arrow-left","112.5":"mdi:arrow-top-left","157.5":"mdi:arrow-up","202.5":"mdi:arrow-top-right","247.5":"mdi:arrow-right","292.5":"mdi:arrow-bottom-right","337.5":"mdi:arrow-down"}}},"device_tracker":{"_":{"default":"mdi:account","state":{"not_home":"mdi:account-arrow-right"}}},"update":{"_":{"default":"mdi:package-up","state":{"off":"mdi:package"}}},"media_player":{"_":{"default":"mdi:cast","state":{"off":"mdi:cast-off","paused":"mdi:cast-connected","playing":"mdi:cast-connected"}},"speaker":{"default":"mdi:speaker","state":{"off":"mdi:speaker-off","paused":"mdi:speaker-pause","playing":"mdi:speaker-play"}},"tv":{"default":"mdi:television","state":{"off":"mdi:television-off","paused":"mdi:television-pause","playing":"mdi:television-play"}}},"lock":{"_":{"default":"mdi:lock","state":{"jammed":"mdi:lock-alert","locking":"mdi:lock-clock","open":"mdi:lock-open-variant","opening":"mdi:lock-clock","unlocked":"mdi:lock-open-variant","unlocking":"mdi:lock-clock"}}},"weather":{"_":{"default":"mdi:weather-partly-cloudy","state":{"rainy":"mdi:weather-rainy"}}}},"entity":{"zha":{"binary_sensor":{"hand_open":{"default":"mdi:hand-wave"}}}}}''')


def glyph(name):
    return tile_icons.GLYPHS[name]


class Resolution(unittest.TestCase):
    def test_as_home_assistants_frontend_picks_it(self):
        name = lambda entity, state, attributes=None, entry=None: tile_icons.ha_default_icon(entity, state, attributes or {}, entry, ICONS)
        self.assertEqual(name('cover.office', 'closed', {'device_class': 'blind'}), 'blinds-horizontal-closed')
        self.assertEqual(name('cover.office', 'open', {'device_class': 'blind'}), 'blinds-horizontal')
        self.assertEqual(name('cover.skylight', 'opening'), 'arrow-up-box', 'a class without an entry uses the domain')
        self.assertEqual(name('light.lamp', 'off'), 'lightbulb-off')
        self.assertEqual(name('media_player.sonos', 'playing', {'device_class': 'speaker'}), 'speaker-play')
        self.assertEqual(name('binary_sensor.front', 'on', {'device_class': 'door'}), 'door-open')
        self.assertEqual(name('sensor.hall', '21.5', {}, {'original_device_class': 'temperature'}), 'eye',
                         "the frontend reads the device class from the state, which carries the registry's")
        self.assertEqual(name('cover.gate', 'opening', {'device_class': 'gate'}), 'arrow-up-box')
        self.assertEqual(name('binary_sensor.hand', 'on', {}, {'platform': 'zha', 'translation_key': 'hand_open'}), 'hand-wave',
                         "an integration's own icon comes first")
        self.assertIsNone(tile_icons.ha_default_icon('cover.x', 'open', {}, {}, {}))
        self.assertEqual(name('cover.x', None), 'window-open', 'an entity without a state gets the default, as in the entity list')

    def test_a_number_picks_its_step_of_the_range(self):
        name = lambda entity, state, device_class: tile_icons.ha_default_icon(entity, state, {'device_class': device_class}, None, ICONS)
        for level, icon in (('45', 'battery-40'), ('40', 'battery-40'), ('9.9', 'battery-alert'), ('5', 'battery-alert'),
                            ('100', 'battery'), ('250', 'battery'), (' 71 ', 'battery-70'), ('-1', 'battery-unknown'),
                            ('unavailable', 'battery-unknown'), ('unknown', 'battery-unknown')):
            self.assertEqual(name('sensor.phone_battery', level, 'battery'), icon, level)
        for degrees, icon in (('0', 'arrow-down'), ('22.5', 'arrow-bottom-left'), ('100', 'arrow-left'), ('350', 'arrow-down'),
                              ('2.1e2', 'arrow-top-right'), ('north', 'compass-rose')):
            self.assertEqual(name('sensor.wind', degrees, 'wind_direction'), icon, degrees)
        self.assertEqual(tile_icons.js_number(''), 0.0, 'Number("") is 0')
        self.assertIsNone(tile_icons.js_number('0x1'), 'not a decimal state')

    def test_the_icons_the_frontend_picks_in_code(self):
        name = lambda entity, state, attributes: tile_icons.ha_default_icon(entity, state, attributes, None, ICONS)
        self.assertEqual(name('device_tracker.phone', 'home', {'source_type': 'router'}), 'lan-connect')
        self.assertEqual(name('device_tracker.phone', 'not_home', {'source_type': 'router'}), 'lan-disconnect')
        self.assertEqual(name('device_tracker.tag', 'home', {'source_type': 'bluetooth_le'}), 'bluetooth-connect')
        self.assertEqual(name('device_tracker.tag', 'not_home', {'source_type': 'bluetooth'}), 'bluetooth')
        self.assertEqual(name('device_tracker.car', 'not_home', {'source_type': 'gps'}), 'account-arrow-right')
        self.assertEqual(name('device_tracker.car', 'Work', {'source_type': 'gps'}), 'account')
        self.assertEqual(name('input_datetime.alarm', '07:00:00', {'has_date': False, 'has_time': True}), 'clock')
        self.assertEqual(name('input_datetime.trip', '2026-09-20', {'has_date': True, 'has_time': False}), 'calendar')
        self.assertIsNone(name('input_datetime.moment', '2026-09-20 07:00:00', {'has_date': True, 'has_time': True}),
                          'Home Assistant has no icons of its own for input_datetime')
        self.assertEqual(name('update.core', 'off', {'in_progress': True}), 'package-down')
        self.assertEqual(name('update.core', 'on', {'in_progress': False}), 'package-up')
        platform = {'entity': {'demo': {'device_tracker': {'phone': {'default': 'mdi:cellphone'}}}}}
        self.assertEqual(tile_icons.ha_default_icon('device_tracker.phone', 'home', {'source_type': 'router'},
                                                    {'platform': 'demo', 'translation_key': 'phone'}, platform), 'cellphone',
                         "an integration's own icon comes before the frontend's")

    def test_the_screen_gets_only_what_its_fonts_carry(self):
        glyph_of = lambda entity, state, attributes=None, entry=None: tile_icons.default_glyph(entity, state, attributes or {}, entry, ICONS)
        self.assertEqual(glyph_of('cover.office', 'closed', {'device_class': 'blind'}), glyph('blinds-horizontal-closed'))
        self.assertEqual(glyph_of('climate.airco', 'cool'), glyph('thermostat'))
        self.assertEqual(glyph_of('scene.evening', '2026-09-17T08:00:00+00:00'), glyph('palette'))
        self.assertEqual(glyph_of('script.wake', 'on'), glyph('script-text-play'))
        self.assertEqual(glyph_of('sensor.phone_battery', '64', {'device_class': 'battery'}), glyph('battery-60'))
        self.assertEqual(glyph_of('device_tracker.phone', 'home', {'source_type': 'router'}), glyph('lan-connect'))
        self.assertIsNone(glyph_of('update.core', 'off', {'in_progress': True}), 'package-down: no update tiles yet')
        self.assertIsNone(glyph_of('binary_sensor.hand', 'on', {}, {'platform': 'zha', 'translation_key': 'hand_open'}),
                          'hand-wave is not in the fonts: the screen keeps its own icon')
        self.assertIsNone(glyph_of('binary_sensor.plain', 'off'), 'radiobox-blank is not in the icon font either')
        for entity in ('weather.home', 'sun.sun', 'screen.clock'):
            self.assertIsNone(glyph_of(entity, 'rainy'), 'the screen draws these from the state itself')

    def test_every_default_icon_of_home_assistant_for_these_domains_is_in_the_fonts(self):
        wanted = set()
        for spec in ICONS['entity_component'].values():
            for entry in spec.values():
                wanted.add(entry['default'][4:])
                wanted.update(icon[4:] for icon in (entry.get('state') or {}).values())
                wanted.update(icon[4:] for icon in (entry.get('range') or {}).values())
        wanted.update(('lan-connect', 'lan-disconnect', 'bluetooth-connect', 'bluetooth', 'account-arrow-right', 'account', 'clock', 'calendar'))
        self.assertEqual(sorted(wanted - set(tile_icons.GLYPHS)), ['radiobox-blank'], 'the one icon the MDI font of this repo lacks')
        self.assertFalse(set(dict(tile_icons.HA_DEFAULTS)) & set(tile_icons.ICONS), 'the defaults are not pickable')


class Everywhere(unittest.TestCase):
    def setUp(self):
        tile_icons.use_ha_icons(ICONS)

    def tearDown(self):
        tile_icons.use_ha_icons({})

    def test_tile_top_bar_and_editor_show_the_same_icon(self):
        state = {'state': 'closed', 'attributes': {'device_class': 'blind', 'friendly_name': 'Office blind'}}
        auto = {'entity': 'cover.office', 'name': ''}
        self.assertEqual(screen_options(auto, state['attributes'], 'closed')['icon'], glyph('blinds-horizontal-closed'))
        chosen = {'entity': 'cover.office', 'name': '', 'options': {'icon': 'lamp'}}
        self.assertEqual(screen_options(chosen, state['attributes'], 'closed')['icon'], tile_icons.ICONS['lamp'][0], 'a chosen icon wins')
        own = {**state['attributes'], 'icon': 'mdi:curtains'}
        self.assertEqual(screen_options(auto, own, 'closed')['icon'], glyph('curtains'), "an entity's own icon wins")
        self.assertEqual(header_bar.auto_icon('cover.office', state), glyph('blinds-horizontal-closed'))
        _, entities = discover([{'entity_id': 'cover.office', 'platform': 'demo'}], {'cover.office': {**state, 'entity_id': 'cover.office'}}, [], [])
        self.assertEqual(entities[0]['icon'], glyph('blinds-horizontal-closed'))
        self.assertEqual(header_bar.auto_icon('weather.home', {'state': 'rainy', 'attributes': {}}), glyph('weather-rainy'))

    def test_an_entity_without_a_registry_entry_shows_the_screens_icon_in_the_editor(self):
        # A player or a lock of YAML (no unique id, so no registry entry) gets the icon the screen draws, not the power.
        state = {'entity_id': 'media_player.kitchen', 'state': 'playing', 'attributes': {'friendly_name': 'Kitchen'}}
        _, entities = discover([], {'media_player.kitchen': state, 'lock.front': {'entity_id': 'lock.front', 'state': 'locked', 'attributes': {}}}, [], [])
        icons = {e['id']: e['icon'] for e in entities}
        self.assertEqual(icons['media_player.kitchen'], glyph('cast-connected'))
        self.assertEqual(icons['media_player.kitchen'], screen_options({'entity': 'media_player.kitchen', 'name': ''}, state['attributes'], 'playing')['icon'])
        self.assertEqual(icons['lock.front'], glyph('lock'))

    def test_without_home_assistants_icons_everything_is_as_before(self):
        tile_icons.use_ha_icons({})
        self.assertNotIn('icon', screen_options({'entity': 'cover.office', 'name': ''}, {'device_class': 'blind'}, 'closed') or {})
        self.assertEqual(header_bar.auto_icon('climate.airco', {'state': 'cool', 'attributes': {}}), glyph('thermostat'))


if __name__ == '__main__':
    unittest.main()
