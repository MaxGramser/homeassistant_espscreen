"""The exact same document cases also run in the editor's Vitest suite."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import Grid
from page_layout import validate_document, pagination, delete_page, compile_tiles


class PageConformanceTests(unittest.TestCase):
    def test_shared_documents(self):
        for case in json.loads((ROOT / 'tests/fixtures/page-conformance.json').read_text()):
            with self.subTest(case=case['name']):
                doc, grid = deepcopy(case['document']), Grid(**case['grid'])
                if case['valid']:
                    self.assertEqual(validate_document(doc, grid), doc)
                    if 'pagination' in case:
                        self.assertEqual([doc['pages'][i]['id'] for i in pagination(doc)], case['pagination'])
                    if 'delete' in case:
                        result = delete_page(doc, case['delete']['id'], grid)
                        self.assertEqual([t['entity'] for t in compile_tiles(result, grid)], case['delete']['entities'])
                else:
                    with self.assertRaises((ValueError, TypeError, KeyError)):
                        validate_document(doc, grid)
                self.assertEqual(doc, case['document'], 'Validation must not modify a draft')

    def test_a_refused_tile_is_named_with_its_page(self):
        cases = {case['name']: case for case in json.loads((ROOT / 'tests/fixtures/page-conformance.json').read_text())}
        doc = deepcopy(cases['minimal canonical page']['document'])
        second = deepcopy(cases['stale refresh']['document']['pages'][0])
        second['id'], second['tiles'][0]['id'] = '0000000000000002', 'lamp'
        for item in second['topbar']['leading'] + second['topbar']['trailing']:
            item['id'] += '-2'
        second['tiles'][0]['appearance']['label'] = 'Reading lamp'
        doc['pages'].append(second)
        with self.assertRaises(ValueError) as caught:
            validate_document(doc, Grid(**cases['minimal canonical page']['grid']))
        self.assertIn('Page 2', str(caught.exception))
        self.assertIn('Reading lamp', str(caught.exception))

    def test_editor_choices_match_authoritative_tables(self):
        spec = importlib.util.spec_from_file_location('page_rules_generator', ROOT / 'tools/generate_page_rules.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual((ROOT / 'web/src/model/page-rules.json').read_text(), module.output())
