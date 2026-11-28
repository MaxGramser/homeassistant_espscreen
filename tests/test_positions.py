from manager_fixtures import edit_layout
"""Grid positions (app 0.2.31 / firmware 0.2.26): explicit slots, empty cells, in-order fallback."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
import test_portal
from core import MAX_SLOTS, has_gaps, pack_slots, validate_layout

def tiles(*specs):
    out = []
    for spec in specs:
        entity, slot, wide = (spec + (None, False))[:3]
        tile = {'entity': entity}
        if slot is not None: tile['slot'] = slot
        if wide: tile['options'] = {'size': 'wide'}
        out.append(tile)
    return out

class Positions(unittest.TestCase):
    def test_layout_without_positions_packs_in_order(self):
        layout = validate_layout({'title': 'Home', 'tiles': tiles(('light.a',), ('weather.w', None, True), ('light.b',), ('light.c',))})
        self.assertEqual([t['slot'] for t in layout['tiles']], [0, 2, 4, 5])
        self.assertEqual(pack_slots(layout['tiles']), [0, 2, 4, 5])
        self.assertFalse(has_gaps(layout['tiles']))

    def test_explicit_positions_keep_gaps_and_sort_by_slot(self):
        layout = validate_layout({'title': 'Home', 'tiles': tiles(('light.b', 7), ('light.a', 1), ('weather.w', 4, True), ('light.c', 46))})
        self.assertEqual([(t['entity'], t['slot']) for t in layout['tiles']], [('light.a', 1), ('weather.w', 4), ('light.b', 7), ('light.c', 46)])
        self.assertTrue(has_gaps(layout['tiles']))
        # A second pass (reload from disk) is stable.
        self.assertEqual(validate_layout(layout), layout)

    def test_invalid_positions_are_refused(self):
        for bad in [tiles(('light.a', 0), ('light.b', 0)),            # same cell
                    tiles(('light.a', 1), ('weather.w', 0, True)),    # wide covers 0 and 1
                    tiles(('weather.w', 3, True)),                    # wide in the right column
                    tiles(('light.a', MAX_SLOTS)),                    # beyond page eight
                    tiles(('light.a', -1)), tiles(('light.a', '2')), tiles(('light.a', 2.0)),
                    tiles(('light.a', 0), ('light.b',))]:              # some tiles without a position
            with self.assertRaises(ValueError, msg=bad): validate_layout({'title': 'Home', 'tiles': bad})
        # Forecast forces a wide card, so the right column is refused there too.
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Home', 'tiles': [{'entity': 'weather.w', 'slot': 1, 'options': {'display': 'forecast'}}]})

    def test_pages_kept_on_purpose(self):
        layout = validate_layout({'title': 'Home', 'tiles': tiles(('light.a', 0)), 'pages': 3})
        self.assertEqual(layout['pages'], 3)
        self.assertNotIn('pages', validate_layout({'title': 'Home', 'tiles': []}))
        for bad in [0, 9, '2', 2.0, True]:
            with self.assertRaises(ValueError, msg=bad): validate_layout({'title': 'Home', 'tiles': [], 'pages': bad})

    def test_a_page_may_say_something_else_than_the_screen(self):
        # A title of its own per page (app 0.2.105): an empty entry means the screen's own title, and trailing
        # empty ones are dropped, so a screen where nobody set one carries nothing at all.
        base = {'title': 'Home', 'tiles': tiles(('light.a', 0))}
        self.assertEqual(validate_layout({**base, 'page_titles': ['', 'Kitchen', '']})['page_titles'], ['', 'Kitchen'])
        self.assertNotIn('page_titles', validate_layout({**base, 'page_titles': ['', '']}))
        self.assertNotIn('page_titles', validate_layout(base))
        self.assertEqual(validate_layout({**base, 'page_titles': ['', '  Hall  ']})['page_titles'], ['', 'Hall'])
        # Page 1 carries a title of its own like any other page (app 0.2.123): the firmware falls back to the
        # screen's title per page, so a title that belongs to its page survives a reorder of the row.
        self.assertEqual(validate_layout({**base, 'page_titles': ['Hall']})['page_titles'], ['Hall'])
        self.assertEqual(validate_layout({**base, 'page_titles': ['Hall', 'Kitchen']})['page_titles'], ['Hall', 'Kitchen'])
        # The screen's own title is a thing of its own and stays what it was.
        self.assertEqual(validate_layout({**base, 'page_titles': ['Hall']})['title'], 'Home')
        for bad in ['Hall', {'1': 'Hall'}, [None], [1], ['x' * 97], [''] * 9]:
            with self.assertRaises(ValueError, msg=bad): validate_layout({**base, 'page_titles': bad})

    def test_last_cell_of_page_eight_and_wide_on_last_row(self):
        layout = validate_layout({'title': 'Home', 'tiles': tiles(('light.a', MAX_SLOTS - 1), ('weather.w', MAX_SLOTS - 4, True))})
        self.assertEqual([t['slot'] for t in layout['tiles']], [MAX_SLOTS - 4, MAX_SLOTS - 1])

class PositionsOnTheWire(unittest.IsolatedAsyncioTestCase):
    async def test_layout_message_carries_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_portal.ManagerTests().setup_manager(Path(tmp) / 'screens.json')
            m.ha.states['light.b'] = {'state': 'off', 'attributes': {}}
            edit_layout(m, 'text.screen', {'title': 'Home', 'tiles': tiles(('light.b', 7), ('light.a', 2))})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            wire = m.ha.messages[0][1]
            self.assertEqual(wire['entities'], ['light.a', 'light.b'])
            self.assertEqual(wire['slots'], [2, 7])
            # State messages index the entity list, in slot order.
            self.assertEqual([(msg['i'], msg['entity']) for _, msg in m.ha.messages[1:]], [(0, 'light.a'), (1, 'light.b')])
            # Moving a tile changes the layout message, so the whole layout goes out again.
            m.ha.messages.clear()
            edit_layout(m, 'text.screen', {'title': 'Home', 'tiles': tiles(('light.b', 6), ('light.a', 2))})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(m.ha.messages[0][1]['slots'], [2, 6])
            self.assertEqual(len(m.ha.messages), 3)
            self.assertEqual(m.ha.messages[0][1]['pages'], 2)
            m.ha.messages.clear()
            edit_layout(m, 'text.screen', {'title': 'Home', 'tiles': tiles(('light.b', 6), ('light.a', 2)), 'pages': 4})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(m.ha.messages[0][1]['pages'], 4)

    async def test_old_storage_gets_positions_and_old_editor_keeps_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            legacy = {'title': 'Home', 'tiles': [{'entity': 'light.a', 'name': ''}, {'entity': 'light.b', 'name': '', 'options': {'size': 'wide'}}]}
            path.write_text(json.dumps({'version': 1, 'screens': {'text.screen': legacy}}))
            m = test_portal.ManagerTests().setup_manager(path)
            self.assertEqual([t['slot'] for t in m.layouts['text.screen']['tiles']], [0, 2])
            m.ha.states['light.b'] = {'state': 'off', 'attributes': {}}
            # The editor moves light.b to page two; an older editor that saves without positions packs again.
            edit_layout(m, 'text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.a', 'slot': 1}, {'entity': 'light.b', 'slot': 6, 'options': {'size': 'wide'}}]})
            self.assertEqual([t['slot'] for t in m.layouts['text.screen']['tiles']], [1, 6])
            self.assertEqual(m.layouts['text.screen']['tiles'][1]['slot'], 6)
            before = m.store.get('text.screen')
            with self.assertRaisesRegex(ValueError, 'Reload the editor'):
                m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'light.b'}, {'entity': 'light.a'}]})
            self.assertEqual(m.store.get('text.screen'), before, 'an old structural save cannot repack migrated pages')

if __name__ == '__main__':
    unittest.main()
