"""The tile catalogue (app 0.4.32): catalogue/*.yaml checked as it is generated, and what catalogue.py answers.

docs/CATALOGUE.md is the guide. The files are the list of what a tile can show: a type exists only where it has one, a
new one says from which firmware a screen draws it, every action and feature an option names is one Home Assistant has
for the type (catalogue/_ha.json, read from its source), every control has words. And what the add-on asks of it: what
may be chosen for an entity, what a card of a size draws, what a screen gets, what a layout asks of its firmware.
"""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
from core import span_of  # noqa: E402

# The generator by its file: tools/ on the path would put tools/i18n.py before the add-on's own i18n.
_spec = importlib.util.spec_from_file_location('generate_catalogue', ROOT / 'tools/generate_catalogue.py')
generate_catalogue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_catalogue)


def state(flags=None, **attributes):
    return {'state': 'on', 'attributes': {**({'supported_features': flags} if flags is not None else {}), **attributes}}


class Generated(unittest.TestCase):
    def setUp(self):
        self.tile, self.types = generate_catalogue.load()
        self.translations = json.loads((ROOT / 'screen_manager/translations/en.json').read_text())
        self.facts = json.loads((ROOT / 'catalogue/_ha.json').read_text())

    def normalise(self, types=None, facts=None):
        return generate_catalogue.normalise(self.tile, types or self.types, self.translations, facts or self.facts)

    def test_the_outputs_are_what_the_files_say(self):
        self.assertEqual(json.loads((ROOT / 'screen_manager/app/catalogue.json').read_text()), self.normalise())
        self.assertEqual((ROOT / 'web/src/model/catalogue.json').read_text(), (ROOT / 'screen_manager/app/catalogue.json').read_text())

    def test_the_files_are_the_list_of_types_and_home_assistant_adds_none(self):
        # Home Assistant has many more types (valve, humidifier, water_heater, ...): none of them is a tile without a file.
        self.assertEqual(set(self.normalise()['domains']), {path.stem for path in (ROOT / 'catalogue').glob('*.yaml') if not path.name.startswith('_')})
        self.assertNotIn('valve', catalogue.DOMAINS)
        self.assertEqual(set(self.facts['domains']), set(catalogue.DOMAINS) - {'screen'})

    def test_a_new_type_says_from_which_firmware_a_screen_draws_it(self):
        types = copy.deepcopy(self.types)
        types['valve'] = {'domain': 'valve', 'displays': {'standard': {}}}
        facts = copy.deepcopy(self.facts)
        facts['domains']['valve'] = {'enum': 'ValveEntityFeature', 'features': {'OPEN': 1}, 'actions': {'open_valve': [['OPEN']]}}
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'from which firmware'):
            self.normalise(types, facts)
        types['valve']['firmware'] = '0.20.0'
        # And what one tile of it keeps in the screen's memory (firmware 0.34.0+, docs/TILE_MEMORY.md): no type leaves the
        # budget guessing.
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'memory'):
            self.normalise(types, facts)
        for wrong in ({'bytes': 100}, {'bytes': -1, 'extras': False}, {'bytes': 100, 'extras': 'yes'}, {'bytes': 100, 'extras': False, 'more': 1}):
            types['valve']['memory'] = wrong
            with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'memory'):
                self.normalise(types, facts)
        types['valve']['memory'] = {'bytes': 160, 'extras': False}
        self.assertEqual(self.normalise(types, facts)['domains']['valve']['firmware'], '0.20.0')
        self.assertEqual(self.normalise(types, facts)['domains']['valve']['memory'], {'bytes': 160, 'extras': False})

    def test_an_action_or_feature_home_assistant_does_not_have_stops_it(self):
        types = copy.deepcopy(self.types)
        types['climate']['controls']['mode']['needs'] = {'actions': ['climate.set_mood']}
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'registers no climate.set_mood'):
            self.normalise(types)
        types = copy.deepcopy(self.types)
        types['climate']['controls']['mode']['needs'] = {'actions': ['climate.set_hvac_mode'], 'features': ['WARP_DRIVE']}
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'WARP_DRIVE is no feature of climate'):
            self.normalise(types)

    def test_a_control_without_words_or_an_unknown_key_stops_it(self):
        types = copy.deepcopy(self.types)
        types['switch']['controls']['blink'] = {'needs': {'actions': ['switch.toggle']}}
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'addon.labels.controls.switch.blink'):
            self.normalise(types)
        types = copy.deepcopy(self.types)
        types['switch']['controls']['toggle']['colour'] = 'red'
        with self.assertRaisesRegex(generate_catalogue.CatalogueError, 'unknown colour'):
            self.normalise(types)


class Offers(unittest.TestCase):
    def offers(self, entity, flags=None, actions=(), **attributes):
        return catalogue.offers(entity, state(flags, **attributes), actions)

    def test_a_thermostat_has_its_setpoint_with_a_temperature_to_set_of_either_kind(self):
        actions = ['climate.set_temperature', 'climate.set_hvac_mode']
        self.assertEqual(self.offers('climate.a', 385, actions)['controls'], ['setpoint', 'mode', 'setpoint_mode'])
        self.assertEqual(self.offers('climate.a', 442, actions)['controls'], ['setpoint', 'mode', 'setpoint_mode'])   # a range only
        self.assertEqual(self.offers('climate.a', 8, actions)['controls'], ['mode'])                                   # fan only
        self.assertEqual(self.offers('climate.a', None, actions)['controls'], ['setpoint', 'mode', 'setpoint_mode'])  # says nothing yet

    def test_a_pair_needs_both_its_parts(self):
        tilt = ['cover.open_cover', 'cover.close_cover', 'cover.set_cover_tilt_position']
        self.assertEqual(self.offers('cover.a', 0, tilt)['controls'], ['buttons', 'tilt', 'buttons_tilt'])

    def test_a_field_decides_where_an_action_is_not_enough(self):
        fields = lambda action, field: False
        self.assertFalse(catalogue.offers('light.a', state(), ['light.turn_on'], fields=fields)['inline'])
        self.assertTrue(catalogue.offers('light.a', state(), ['light.turn_on'], fields=lambda action, field: True)['inline'])

    def test_displays_follow_what_the_entity_has(self):
        self.assertEqual(self.offers('weather.a', 2)['displays'], ['standard', 'watch'])        # hourly only: no days
        self.assertEqual(self.offers('weather.a', 1)['displays'], ['standard', 'watch', 'forecast'])
        self.assertEqual(self.offers('weather.a')['displays'], ['standard', 'watch', 'forecast'])  # unavailable keeps it
        line = catalogue.offers('sensor.t', state(), [], history=lambda entity, st: 'line')['displays']
        text = catalogue.offers('sensor.s', state(), [], history=lambda entity, st: 'state')['displays']
        self.assertEqual((line, text), (['standard', 'watch', 'graph', 'meter'], ['standard', 'watch']))


class Cards(unittest.TestCase):
    def resolve(self, entity, size, **options):
        return catalogue.resolve_controls({'entity': entity, 'options': {'size': size, **options}}, span_of)

    def test_a_wider_card_has_its_types_default_and_a_taller_one_none_unless_chosen(self):
        self.assertEqual(self.resolve('light.a', 'wide'), 'toggle')
        self.assertIsNone(self.resolve('light.a', 'tall'))
        self.assertIsNone(self.resolve('light.a', 'single'))
        self.assertEqual(self.resolve('light.a', 'tall', controls='brightness'), 'brightness')
        self.assertIsNone(self.resolve('light.a', 'wide', inline='slider'))

    def test_a_card_one_row_high_draws_what_fits_there(self):
        self.assertEqual(self.resolve('climate.a', 'wide', controls='setpoint_mode'), 'setpoint')
        self.assertEqual(self.resolve('climate.a', '3x1', controls='setpoint_mode'), 'setpoint')
        self.assertEqual(self.resolve('cover.a', 'square', controls='buttons_tilt'), 'buttons_tilt')
        self.assertEqual(self.resolve('cover.a', 'full', controls='buttons_tilt'), 'buttons_tilt')

    def test_a_cover_lays_out_its_controls_by_its_room(self):
        # A cover's controls stay whole on a card of one row and of one cell (firmware 0.57.0, `room`): a screen that
        # says cover_rows draws what fits, and an older one gets what it always got (roomless).
        self.assertEqual(self.resolve('cover.a', 'wide', controls='buttons_tilt'), 'buttons_tilt')
        self.assertEqual(self.resolve('cover.a', '3x1', controls='position_tilt'), 'position_tilt')
        self.assertEqual(self.resolve('cover.a', 'single', controls='position'), 'position')
        self.assertEqual(self.resolve('cover.a', '1x1', controls='tilt'), 'tilt')
        self.assertIsNone(self.resolve('cover.a', 'single'))
        self.assertIsNone(self.resolve('light.a', 'single', controls='brightness'))
        roomless = lambda key, size: catalogue.roomless('cover', key, size, span_of)
        self.assertEqual((roomless('buttons_tilt', 'wide'), roomless('tilt', 'wide'), roomless('position_tilt', '3x1')), ('buttons', 'none', 'position'))
        self.assertEqual((roomless('position', 'single'), roomless('position_tilt', 'square')), ('none', 'position_tilt'))
        sent = lambda size, controls, features: catalogue.drawn_controls(
            {'entity': 'cover.a', 'o': {'size': size, 'controls': controls}, 'a': {'supported_features': 255}}, features, span_of)['o']['controls']
        self.assertEqual(sent('wide', 'position_tilt', frozenset({'cover_rows'})), 'position_tilt')
        self.assertEqual(sent('wide', 'position_tilt', frozenset()), 'position')
        older = catalogue.drawn_controls({'entity': 'cover.a', 'o': {'size': 'single', 'controls': 'position'}, 'a': {}}, frozenset(), span_of)
        self.assertNotIn('controls', older['o'])                                    # as resolve_controls sent it before
        self.assertEqual(sent('single', 'position', None), 'position')              # the hello not known: as it is


class Screens(unittest.TestCase):
    def drawn(self, controls, flags, features, **attributes):
        message = {'entity': 'climate.a', 'o': {'size': 'wide', 'controls': controls}, 'a': {'supported_features': flags, **attributes}}
        return catalogue.drawn_controls(message, features)['o']['controls']

    def test_what_an_entity_cannot_draw_falls_back(self):
        self.assertEqual(self.drawn('setpoint', 8, None), 'none')
        self.assertEqual(self.drawn('setpoint_mode', 8, None), 'mode')

    def test_a_range_goes_to_a_screen_whose_hello_says_it_draws_one(self):
        self.assertEqual(self.drawn('setpoint', 442, frozenset({'climate_range'})), 'setpoint')
        self.assertEqual(self.drawn('setpoint', 442, frozenset()), 'none')
        self.assertEqual(self.drawn('setpoint_mode', 442, frozenset()), 'mode')
        self.assertEqual(self.drawn('setpoint', 442, None), 'setpoint')            # the hello not known: as it is
        self.assertEqual(self.drawn('setpoint', 3, frozenset()), 'setpoint')        # a single temperature too: drawn
        message = {'entity': 'climate.a', 'o': {'controls': 'setpoint'}, 'a': {}}  # says nothing: as it is
        self.assertEqual(catalogue.drawn_controls(message, frozenset())['o']['controls'], 'setpoint')

    def test_what_a_layout_asks_of_a_screens_firmware(self):
        gate = lambda entity, **options: sorted(version for version, _ in catalogue.gates({'entity': entity, 'options': options}))
        self.assertEqual(gate('lock.a'), [(0, 5, 0)])
        self.assertEqual(gate('cover.a', controls='buttons_tilt'), [(0, 3, 1)])
        self.assertEqual(gate('media_player.a', display='cover'), [(0, 2, 78)])
        self.assertEqual(gate('camera.a', display='live'), [(0, 2, 57), (0, 2, 77)])
        # The dial draws as the digital clock on older firmware: it asks for none (`else`).
        self.assertEqual(gate('screen.clock', display='dial'), [(0, 2, 14)])
        self.assertEqual(gate('light.a'), [])


class Conformance(unittest.TestCase):
    def test_the_editors_cases_are_what_catalogue_py_answers(self):
        # web/tests/catalogue.spec.ts holds catalogue.ts to the same file: the two answer alike.
        conformance = importlib.util.spec_from_file_location('catalogue_conformance', ROOT / 'tests/catalogue_conformance.py')
        module = importlib.util.module_from_spec(conformance)
        conformance.loader.exec_module(module)
        self.assertEqual(module.FIXTURE.read_text(), module.output(), 'run tests/catalogue_conformance.py')


if __name__ == '__main__':
    unittest.main()
