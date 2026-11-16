"""Firmware 0.17.0: an on/off or run card two rows tall is one big key, the flip clock fills a card as wide as the page,
the bedside clock puts AM or PM under its time (GitHub #93), and a key under the clock can hide its name."""
from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from core import NIGHTSTAND, Grid, validate_layout  # noqa: E402
from firmware_sources import runtime_source  # noqa: E402
from layout_migrations import migrate_legacy  # noqa: E402
from page_layout import compile_tiles, validate_document  # noqa: E402

SOURCE = runtime_source()
CLOCK = {'entity': NIGHTSTAND, 'name': '', 'slot': 0, 'options': {'size': 'full'}}


class Firmware(unittest.TestCase):
    """What the screen draws is read from the real firmware in web/wasm/test_tile_shapes.mjs (tools/check.sh): the big
    key for the eight domains that switch or run and for none of five that have controls, not with a slider or a bar,
    a tap low on it switching; the flip clock's two blocks and its line; the bedside clock's AM or PM; a key without
    its name in its place."""

    def test_the_prototype_switches_are_gone(self):
        # Rule: the design study's switches (firmware 0.16) do not come back into the firmware.
        for word in ('design_variant', 'DESIGN PROTOTYPE'):
            self.assertNotIn(word, SOURCE, f'{word}: the 0.17.0 shapes are the product, not a prototype to switch')


class KeyNameTests(unittest.TestCase):
    def test_a_key_saves_its_name_hidden_and_drops_the_default(self):
        key = {'entity': 'light.bed', 'name': 'Bed', 'in': NIGHTSTAND, 'key': 0, 'options': {'overlay': 'none'}}
        tiles = validate_layout({'title': 'Bed', 'tiles': [deepcopy(CLOCK), key]})['tiles']
        self.assertEqual(tiles[1]['options'], {'overlay': 'none'})
        shown = validate_layout({'title': 'Bed', 'tiles': [deepcopy(CLOCK), {**key, 'options': {'overlay': 'name'}}]})['tiles']
        self.assertNotIn('overlay', shown[1].get('options', {}))
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Bed', 'tiles': [deepcopy(CLOCK), {**key, 'options': {'overlay': 'maybe'}}]})
        # A placed tile that is no picture still has no use for it.
        plain = validate_layout({'title': 'Bed', 'tiles': [{'entity': 'light.bed', 'name': '', 'slot': 0, 'options': {'overlay': 'none'}}]})
        self.assertNotIn('overlay', plain['tiles'][0].get('options', {}))

    def test_the_page_document_keeps_it_on_the_child(self):
        counter = itertools.count(1)
        key = {'entity': 'light.bed', 'name': 'Bed', 'in': NIGHTSTAND, 'key': 0, 'options': {'overlay': 'none'}}
        document = migrate_legacy({'title': 'Bed', 'tiles': [deepcopy(CLOCK), key]}, Grid(), lambda: f'{next(counter):016x}')['layout']
        child = document['pages'][0]['tiles'][0]['children'][0]
        self.assertEqual(child['appearance'], {'label': 'Bed', 'overlay': 'none'})
        self.assertEqual(compile_tiles(validate_document(document, Grid()), Grid())[1]['options'], {'overlay': 'none'})


if __name__ == '__main__':
    unittest.main()
