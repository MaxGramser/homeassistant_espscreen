"""The editor's first layouts (web/src/model/auto-layout.ts, docs/AUTO_LAYOUT.md) pass the add-on's own document check.

tests/fixtures/auto-layout-documents.json holds the layouts the editor's tests make for fake homes on a large screen with
sections, a middle one and the CYD (web/tests/auto-layout.spec.ts writes it); each must pass validate_document on its grid,
the same check a save goes through, so the editor never offers a layout the add-on refuses."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import page_layout  # noqa: E402

DOCUMENTS = json.loads((ROOT / 'tests/fixtures/auto-layout-documents.json').read_text())


class FirstLayouts(unittest.TestCase):
    def test_every_layout_passes_the_add_ons_check(self):
        self.assertGreaterEqual(len(DOCUMENTS), 6)
        for case in DOCUMENTS:
            with self.subTest(grid=case['grid']):
                grid = page_layout.grid_of_record({'format': 'pages-v2', 'sourceGrid': case['grid'], 'layout': case['layout']})
                page_layout.validate_document(case['layout'], grid)

    def test_a_section_groups_two_cards_or_more(self):
        # A lone card stands loose on its page: the first layout never proposes a section of one card.
        for case in DOCUMENTS:
            for page in case['layout']['pages']:
                for section in page_layout.sections_of(page):
                    self.assertGreater(len(page_layout.tiles_in(page, section)), 1, section['title'])

    def test_sections_only_where_the_grid_has_room(self):
        for case in DOCUMENTS:
            sections = [s for page in case['layout']['pages'] for s in page_layout.sections_of(page)]
            if min(case['grid']['columns'], case['grid']['rows']) < 3:
                self.assertEqual(sections, [])


if __name__ == '__main__':
    unittest.main()
