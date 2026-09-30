"""Firmware 0.17.0: an on/off or run card two rows tall is one big key, the flip clock fills a card as wide as the page,
the bedside clock puts AM or PM under its time (GitHub #93), and a key under the clock can hide its name."""
from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import NIGHTSTAND, Grid, validate_layout  # noqa: E402
from firmware_sources import runtime_source  # noqa: E402
from layout_migrations import migrate_legacy  # noqa: E402
from page_layout import compile_tiles, validate_document  # noqa: E402

SOURCE = runtime_source()
CLOCK = {'entity': NIGHTSTAND, 'name': '', 'slot': 0, 'options': {'size': 'full'}}


class BigKeyTests(unittest.TestCase):
    def test_only_cards_that_switch_or_run_and_have_no_other_control(self):
        rule = SOURCE[SOURCE.index('inline bool big_key(const Tile &t){'):]
        rule = rule[:rule.index('}\n')]
        for domain in ('light', 'switch', 'input_boolean', 'fan', 'script', 'scene', 'button', 'input_button'):
            self.assertIn(f'd=="{domain}"', rule)
        for domain in ('cover', 'media_player', 'vacuum', 'climate', 'lock'):
            self.assertNotIn(f'd=="{domain}"', rule)
        self.assertIn('t.inline_control!="slider"', rule)
        self.assertIn('t.controls=="toggle"||t.controls=="run"', rule)

    def test_two_rows_tall_but_not_a_whole_page(self):
        self.assertIn('if(t.row_span()>=2&&!w.full&&big_key(t)){', SOURCE)
        # The whole card is the key: its switch or run key is not drawn.
        block = SOURCE[SOURCE.index('if(t.row_span()>=2&&!w.full&&big_key(t)){'):][:400]
        self.assertIn('hide_panel(w);hide_extra(w);', block)

    def test_the_prototype_switches_are_gone(self):
        self.assertNotIn('design_variant', SOURCE)
        self.assertNotIn('DESIGN PROTOTYPE', SOURCE)


class FlipAndBedsideTests(unittest.TestCase):
    def test_the_flip_clock_fills_a_card_as_wide_as_the_page(self):
        self.assertIn('if(w.full || (w.wide && t.row_span()>=2)){', SOURCE)
        # Room above the blocks and under the day's line, so a low card never has them touch its edge.
        self.assertIn('air=std::max(ui::px(6),height/20);', SOURCE)
        self.assertIn('const int bh=std::min(height-2*air-line_gap-sh,bw*92/100);', SOURCE)

    def test_am_or_pm_stands_under_the_end_of_the_time(self):
        self.assertIn('auto *p=digit_label(w,2,small,end-aw,last+ui::px(10),aw,LV_TEXT_ALIGN_LEFT,ampm);', SOURCE)

    def test_a_key_without_its_name_keeps_its_place(self):
        self.assertIn('names.push_back(!t.overlay?std::string():t.name.empty()?t.entity:t.name);', SOURCE)
        self.assertIn('if(i<l.keys && l.names && !names[i].empty()){', SOURCE)


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
