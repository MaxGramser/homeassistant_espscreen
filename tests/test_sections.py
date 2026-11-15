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
from page_layout import FORMAT, LayoutError, compile_tiles, flattened, section_of, tiles_in, validate_document  # noqa: E402
from layout_store import LayoutStore  # noqa: E402

CASES = {case['name']: case for case in json.loads((ROOT / 'tests/fixtures/page-conformance.json').read_text())}
SECTIONED = CASES["a section's tiles are its page's own, in its block"]
# The same page as sections first kept it on dev (2026-11-15, never released): each section holding its own tiles,
# placed from its block's corner.
NESTED = CASES["a section that holds tiles of its own, the first form of sections, is refused"]
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

    def test_a_tile_belongs_to_the_section_whose_block_it_lies_in(self):
        page = record_of(SECTIONED)['layout']['pages'][0]
        lights = page['sections'][0]
        homes = {tile['id']: (section_of(page, tile) or {}).get('title') for tile in page['tiles']}
        self.assertEqual(homes, {'lock': None, 'tv': None, 'ceiling': 'Lights', 'sofa': 'Lights', 'desk': 'Lights'})
        self.assertEqual([tile['id'] for tile in tiles_in(page, lights)], ['ceiling', 'sofa', 'desk'])
        # A page's tiles are one list: nothing that counts or walks them has to know sections.
        self.assertEqual(len(page['tiles']), 5)
        self.assertNotIn('tiles', lights)

    def test_sections_that_held_tiles_of_their_own_become_the_form_kept_now(self):
        grid = Grid(**NESTED['grid'])
        with self.assertRaises(LayoutError):
            validate_document(deepcopy(NESTED['document']), grid)
        layout, changed = flattened(deepcopy(NESTED['document']))
        self.assertTrue(changed)
        self.assertEqual(validate_document(layout, grid), layout)
        # The same tiles in the same cells as the page kept flat from the start, so a screen gets the same layout.
        self.assertEqual(sorted((t['entity'], t['slot']) for t in compile_tiles(layout, grid)),
                         sorted((t['entity'], t['slot']) for t in compile_tiles(SECTIONED['document'], grid)))
        self.assertEqual(flattened(layout), (layout, False))
        # A store written in that first form is read, kept as it was beside it, and written in the form kept now.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'screens.json'
            first = json.dumps({'version': 3, 'screens': {'text.screen': record_of(NESTED)}})
            path.write_text(first)
            store = LayoutStore(path, lambda inbox: grid)
            kept = store.get('text.screen')['layout']
            self.assertEqual(len(kept['pages'][0]['tiles']), 5)
            self.assertNotIn('tiles', kept['pages'][0]['sections'][0])
            self.assertEqual(path.with_name('screens.v3.backup.json').read_text(), first)
            self.assertNotIn('"tiles":[{"id":"ceiling"', path.read_text().split('"sections"')[1])
            # Read once more: nothing left to convert, no second backup.
            LayoutStore(path, lambda inbox: grid)
            self.assertEqual(len(list(Path(temp).glob('*.backup.json'))), 1)


if __name__ == '__main__':
    unittest.main()
