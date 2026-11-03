"""A light's presets (module light_presets, docs/LIGHT_PRESETS.md): how the app keeps them, what it sends, and which
screen draws them.

A preset is a brightness with a white shade or a colour (or neither: the colour the light has), at most four per tile,
kept in the tile's options and sent as they are. The controls `presets` and `brightness_presets` (catalogue/light.yaml)
reach only a screen whose hello says light_presets (every board with 8 MB of flash or more); another gets the slider.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
import core  # noqa: E402
import light_presets  # noqa: E402
import page_layout  # noqa: E402

LIGHT = {'state': 'on', 'attributes': {'friendly_name': 'Living room', 'brightness': 200, 'color_mode': 'color_temp',
                                       'color_temp_kelvin': 2700, 'supported_color_modes': ['color_temp', 'hs'],
                                       'min_color_temp_kelvin': 2200, 'max_color_temp_kelvin': 6500}}
PRESETS = [{'b': 30, 'k': 2200}, {'b': 80, 'k': 2700}, {'b': 60, 'h': 280, 's': 41}, {'b': 45}]


def layout(options, entity='light.living_room'):
    return {'title': 'Home', 'tiles': [{'entity': entity, 'slot': 0, 'options': options}]}


class Validation(unittest.TestCase):
    def test_kept_as_stored(self):
        out = core.validate_layout(layout({'size': 'wide', 'controls': 'presets', 'presets': PRESETS}))
        self.assertEqual(out['tiles'][0]['options']['presets'], PRESETS)

    def test_keys_in_the_editor_s_order(self):
        # web/src/model/light-presets.ts cleanPreset builds the same order; 0.4.91 wrote the effect and the device's
        # settings first, and the editor then refused every save of a page with such a preset.
        full = light_presets.preset({'b': 70, 'rw': {'number.desk_speed': 128}, 'fx': 'Aurora', 'h': 220, 's': 100})
        self.assertEqual(list(full), ['b', 'h', 's', 'fx', 'rw'])
        self.assertEqual(list(light_presets.preset({'rw': {'number.desk_speed': 90}, 'fx': 'Candle', 'b': 100})),
                         ['b', 'fx', 'rw'])
        self.assertEqual(list(light_presets.preset({'fx': 'Candle', 'k': 2700, 'b': 40})), ['b', 'k', 'fx'])

    def test_whole_floats_become_ints_and_hue_wraps(self):
        self.assertEqual(light_presets.preset({'b': 80.0, 'h': 360, 's': 100.0}), {'b': 80, 'h': 0, 's': 100})

    def test_empty_list_is_not_stored(self):
        out = core.validate_layout(layout({'presets': []}))
        self.assertNotIn('options', out['tiles'][0]) if 'options' not in out['tiles'][0] else \
            self.assertNotIn('presets', out['tiles'][0]['options'])

    def test_another_domain_keeps_none(self):
        out = core.validate_layout(layout({'presets': PRESETS}, entity='switch.kettle'))
        self.assertNotIn('presets', out['tiles'][0].get('options', {}))

    def test_wrong_ones_are_refused(self):
        wrong = [
            PRESETS + [{'b': 10}],                 # five
            [{'k': 2700}],                         # no brightness
            [{'b': 0}], [{'b': 101}], [{'b': True}], [{'b': 50.5}],
            [{'b': 50, 'k': 2700, 'h': 10, 's': 10}],   # both a white shade and a colour
            [{'b': 50, 'k': 900}], [{'b': 50, 'k': 16000}],
            [{'b': 50, 'h': 10}], [{'b': 50, 'h': 10, 's': 101}],
            [{'b': 50, 'x': 1}], ['warm'], {'b': 50},
        ]
        for presets in wrong:
            with self.subTest(presets=presets), self.assertRaises(ValueError):
                core.validate_layout(layout({'presets': presets}))


class Levels(unittest.TestCase):
    """Whether the discs show their brightness: off unless chosen, stored only when on, a light's alone."""
    def test_off_is_not_stored(self):
        out = core.validate_layout(layout({'presets': PRESETS, 'preset_levels': False}))
        self.assertNotIn('preset_levels', out['tiles'][0]['options'])

    def test_on_is_kept(self):
        out = core.validate_layout(layout({'presets': PRESETS, 'preset_levels': True}))
        self.assertIs(out['tiles'][0]['options']['preset_levels'], True)

    def test_only_a_light_and_only_a_bool(self):
        out = core.validate_layout(layout({'preset_levels': True}, entity='switch.kettle'))
        self.assertNotIn('preset_levels', out['tiles'][0].get('options', {}))
        with self.assertRaises(ValueError):
            core.validate_layout(layout({'preset_levels': 'yes'}))


class Events(unittest.TestCase):
    """An automation's or an assistant's tile event: the presets as a list or as JSON, the levels as words."""
    def test_list_and_json(self):
        self.assertEqual(core.tile_options({'presets': PRESETS})['presets'], PRESETS)
        self.assertEqual(core.tile_options({'presets': json.dumps(PRESETS)})['presets'], PRESETS)
        self.assertIs(core.tile_options({'preset_levels': 'on'})['preset_levels'], True)


class Wire(unittest.TestCase):
    def test_the_screen_gets_them_as_stored(self):
        tile = {'entity': 'light.living_room', 'name': '', 'options': {'size': 'wide', 'controls': 'presets', 'presets': PRESETS}}
        message = core.state_message(0, tile, {'light.living_room': LIGHT})
        self.assertEqual(message['o']['presets'], PRESETS)
        self.assertEqual(message['o']['controls'], 'presets')

    def test_the_page_document_keeps_them(self):
        self.assertEqual(page_layout.INTERACTION['presets'], 'presets')
        self.assertEqual(core.TILE_EVENT_OPTIONS['presets'], 'presets')


def spans(size):
    return {'single': (1, 1), 'wide': (2, 1), 'tall': (1, 2), 'square': (2, 2)}.get(size)


class Controls(unittest.TestCase):
    """What a card draws (resolve_controls), and what a screen gets of it (drawn_controls)."""

    def resolved(self, size, controls):
        return catalogue.resolve_controls({'entity': 'light.a', 'options': {'size': size, 'controls': controls}}, spans)

    def drawn(self, size, controls, features):
        message = {'entity': 'light.a', 'o': {'size': size, 'controls': controls}, 'a': LIGHT['attributes']}
        return catalogue.drawn_controls(json.loads(json.dumps(message)), features, spans)['o'].get('controls')

    def test_a_card_of_one_cell_keeps_its_presets(self):
        self.assertEqual(self.resolved('single', 'presets'), 'presets')

    def test_both_on_one_row_is_the_presets(self):
        self.assertEqual(self.resolved('wide', 'brightness_presets'), 'presets')
        self.assertEqual(self.resolved('square', 'brightness_presets'), 'brightness_presets')

    def test_a_screen_with_the_module_draws_them(self):
        for size, controls in (('wide', 'presets'), ('single', 'presets'), ('square', 'brightness_presets')):
            with self.subTest(size=size):
                self.assertEqual(self.drawn(size, controls, ['light_presets', 'cover_rows']), controls)

    def test_another_screen_draws_the_slider(self):
        self.assertEqual(self.drawn('wide', 'presets', ['cover_rows']), 'brightness')
        self.assertEqual(self.drawn('square', 'brightness_presets', ['cover_rows']), 'brightness')
        # A card of one cell had no control before: it gets none.
        self.assertIsNone(self.drawn('single', 'presets', ['cover_rows']))

    def test_offered_where_the_light_dims(self):
        offers = catalogue.offers('light.living_room', LIGHT, ['light.turn_on', 'light.toggle'],
                                  fields=lambda action, field: field == 'brightness_pct')['controls']
        self.assertIn('presets', offers)
        self.assertIn('brightness_presets', offers)
        switched = catalogue.offers('light.living_room', LIGHT, ['light.turn_on', 'light.toggle'], fields=lambda a, f: False)
        self.assertNotIn('presets', switched['controls'])


class Boards(unittest.TestCase):
    def test_only_boards_with_room(self):
        boards = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        for key, board in boards.items():
            with self.subTest(board=key):
                self.assertEqual('light_presets' in board['modules'], board['tier'] == 'full')
        self.assertNotIn('light_presets', boards['cyd']['modules'])
        self.assertIn('light_presets', boards['guition']['modules'])


if __name__ == '__main__':
    unittest.main()


class Effects(unittest.TestCase):
    """A preset with an effect and settings of the light's device (a WLED's palette, speed, intensity), or a preset of
    the lamp itself (a WLED's own preset or playlist)."""
    WLED = {'b': 70, 'h': 280, 's': 41, 'fx': 'Colorloop',
            'rw': {'select.desk_color_palette': 'Party', 'number.desk_speed': 180, 'number.desk_intensity': 128}}

    def test_kept_as_stored(self):
        out = core.validate_layout(layout({'presets': [self.WLED, {'rw': {'select.desk_preset': 'Film'}}, {'b': 90, 'fx': 'Rainbow'}]}))
        self.assertEqual(out['tiles'][0]['options']['presets'],
                         [self.WLED, {'rw': {'select.desk_preset': 'Film'}}, {'b': 90, 'fx': 'Rainbow'}])

    def test_the_screen_gets_pairs(self):
        tile = {'entity': 'light.living_room', 'name': '', 'options': {'size': 'wide', 'controls': 'presets', 'presets': [self.WLED]}}
        sent = core.state_message(0, tile, {'light.living_room': LIGHT})['o']['presets'][0]
        self.assertEqual(sent['rw'], [['select.desk_color_palette', 'Party'], ['number.desk_speed', 180], ['number.desk_intensity', 128]])
        self.assertEqual(sent['fx'], 'Colorloop')

    def test_wrong_ones_are_refused(self):
        wrong = [
            {'fx': 'Rainbow'},                                   # an effect needs a brightness
            {'rw': {'select.desk_preset': 'Film'}, 'k': 2700},   # a colour needs one too
            {'b': 50, 'fx': ''}, {'b': 50, 'fx': 7},
            {'b': 50, 'rw': {}}, {'b': 50, 'rw': {'light.desk': 'x'}}, {'b': 50, 'rw': {'select.desk_preset': ''}},
            {'b': 50, 'rw': {'number.desk_speed': 'fast'}}, {'b': 50, 'rw': {'number.desk_speed': True}},
            {'b': 50, 'rw': {f'number.n{i}': i for i in range(5)}},
        ]
        for preset in wrong:
            with self.subTest(preset=preset), self.assertRaises(ValueError):
                core.validate_layout(layout({'presets': [preset]}))

    def test_the_choices_of_a_wled(self):
        import light_effects
        states = {
            'light.desk': {'state': 'on', 'attributes': {'supported_features': light_effects.EFFECT, 'effect_list': ['Solid', 'Rainbow', 'Aurora']}},
            'select.desk_color_palette': {'state': 'Default', 'attributes': {'options': ['Default', 'Party']}},
            'select.desk_preset': {'state': 'Film', 'attributes': {'options': ['Film', 'Lezen']}},
            'select.desk_live_override': {'state': '0', 'attributes': {'options': ['0', '1', '2']}},
            'number.desk_speed': {'state': '128', 'attributes': {'min': 0, 'max': 255, 'step': 1}},
        }
        device = [{'entity_id': e, 'translation_key': k} for e, k in (('light.desk', 'main'), ('select.desk_color_palette', 'color_palette'),
                  ('select.desk_preset', 'preset'), ('select.desk_live_override', 'live_override'), ('number.desk_speed', 'speed'))]
        out = light_effects.choices('light.desk', device, states)
        self.assertEqual(out['effects'], ['Solid', 'Aurora', 'Rainbow'])
        self.assertEqual([r['key'] for r in out['rows']], ['color_palette', 'preset', 'speed'])  # not the numeric live override
        self.assertEqual(out['rows'][1]['options'], ['Film', 'Lezen'])
        self.assertEqual((out['rows'][2]['min'], out['rows'][2]['max'], out['rows'][2]['value']), (0, 255, 128))
        self.assertEqual(light_effects.choices('light.desk', [], {'light.desk': {'state': 'off', 'attributes': {}}}), {'effects': [], 'rows': []})
