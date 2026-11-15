"""Sections on a page (docs/PAGES.md "Sections"): what the add-on sends a screen that draws them, and that a layout
without sections reaches every screen exactly as before (the same messages, the same revision)."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import Grid  # noqa: E402
import page_delivery  # noqa: E402
from page_layout import FORMAT, compile_tiles, validate_document  # noqa: E402
from layout_store import LayoutStore  # noqa: E402

CASES = {case['name']: case for case in json.loads((ROOT / 'tests/fixtures/page-conformance.json').read_text())}
SECTIONED = CASES["a section's tiles stand at its block's corner plus their own place"]
REGION = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)


def record_of(case):
    return {'format': FORMAT, 'sourceGrid': dict(case['grid']), 'layout': deepcopy(case['document']), 'revision': 'r1'}


def prepared(record, sections, sums=None):
    grid = Grid(**record['sourceGrid'])
    tiles = compile_tiles(record['layout'], grid)
    values = [{'v': 2, 'op': 'state', 'i': i, 'state': 'on', 'o': {}} for i, _ in enumerate(tiles)]
    bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
    return page_delivery.prepare('text.screen', record, REGION, values, bars, (), sections, sums)


class Sections(unittest.TestCase):
    def test_a_layout_without_sections_reaches_every_screen_as_before(self):
        for name, case in CASES.items():
            if not case['valid'] or any(page.get('sections') for page in case['document']['pages']):
                continue
            with self.subTest(case=name):
                record = record_of(case)
                self.assertEqual(prepared(record, True), prepared(record, False))
                self.assertEqual(page_delivery.configuration(record, REGION, (), True), page_delivery.configuration(record, REGION))

    def test_a_screen_that_draws_sections_gets_them_in_the_page_message(self):
        record = record_of(SECTIONED)
        _, _, pages, _ = prepared(record, True, [['8.6 °C']])
        self.assertEqual(pages[0]['sections'], [[1, 0, 2, 2, pages[0]['sections'][0][4], 'Lights', '8.6 °C', 0]])
        contrast = deepcopy(record)
        contrast['layout']['pages'][0]['sections'][0]['contrast'] = True
        self.assertEqual(prepared(contrast, True, [['']])[2][0]['sections'][0][7], 1)
        contrast['layout']['pages'][0]['sections'][0]['contrastTiles'] = True
        self.assertEqual(prepared(contrast, True, [['']])[2][0]['sections'][0][7], 3)
        # Tiles that follow a contrast the section does not have are refused.
        del contrast['layout']['pages'][0]['sections'][0]['contrast']
        with self.assertRaises(ValueError):
            validate_document(contrast['layout'], Grid(**contrast['sourceGrid']))
        self.assertTrue(pages[0]['sections'][0][4], 'the icon travels as its codepoint')
        # A screen without the feature gets the same tiles, without the sections.
        _, tiles, plain, _ = prepared(record, False)
        self.assertNotIn('sections', plain[0])
        self.assertEqual(tiles, prepared(record, True)[1])
        self.assertNotEqual(page_delivery.configuration(record, REGION, (), True), page_delivery.configuration(record, REGION))

    def test_summaries_go_only_when_they_change(self):
        pages = record_of(SECTIONED)['layout']['pages']
        self.assertEqual(page_delivery.sums_messages(pages, [['8.6 °C']], [['8.6 °C']]), [])
        self.assertEqual(page_delivery.sums_messages(pages, [['9.0 °C']], [['8.6 °C']]), [{'op': 'sums', 'p': 0, 't': ['9.0 °C']}])

    def test_the_store_moves_to_version_3_only_with_a_section_and_keeps_version_2(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'screens.json'
            plain = record_of(CASES['minimal canonical page'])
            path.write_text(json.dumps({'version': 2, 'screens': {'text.screen': plain}}))
            store = LayoutStore(path, lambda inbox: Grid(**plain['sourceGrid']))
            self.assertEqual(json.loads(path.read_text())['version'], 2)
            sectioned = record_of(SECTIONED)
            store._replace({'text.screen': sectioned})
            self.assertEqual(json.loads(path.read_text())['version'], 3)
            backup = path.with_name('screens.v2.backup.json')
            self.assertEqual(json.loads(backup.read_text())['version'], 2)
            # Read again, version 3 is taken and every document still validates.
            again = LayoutStore(path, lambda inbox: Grid(**sectioned['sourceGrid']))
            validate_document(again.get('text.screen')['layout'], Grid(**sectioned['sourceGrid']))


if __name__ == '__main__':
    unittest.main()
