"""Full-page tiles, navigation tiles and forty-eight tiles per screen (app 0.2.74, firmware 0.2.62)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from core import (BUILTIN, FULL_PAGE_MIN_FIRMWARE, MAX_PAGES, MAX_TILES, SLOTS_PER_PAGE, apply_tile_event,  # noqa: E402
                  footprint, free_slot, layout_snapshot, min_firmware, pack_slots, page_target, place_tile, resolve_controls,
                  state_message, tile_size, validate_layout)
import tile_icons  # noqa: E402


def tile(entity, slot=None, **options):
    item = {'entity': entity, 'name': ''}
    if slot is not None:
        item['slot'] = slot
    if options:
        item['options'] = options
    return item


class Sizes(unittest.TestCase):
    def test_footprints(self):
        self.assertEqual(tile_size(tile('light.a')), 'single')
        self.assertEqual(tile_size(tile('light.a', size='wide')), 'wide')
        self.assertEqual(tile_size(tile('light.a', size='full')), 'full')
        self.assertEqual(tile_size(tile('light.a', size='huge')), 'single')
        self.assertEqual(footprint(3, 'single'), (3,))
        self.assertEqual(footprint(2, 'wide'), (2, 3))
        self.assertEqual(footprint(2, True), (2, 3))
        # A full tile takes its page whatever cell it is named by.
        self.assertEqual(footprint(9, 'full'), (6, 7, 8, 9, 10, 11))

    def test_in_order_packing_gives_a_full_tile_its_own_page(self):
        tiles = [tile('light.a'), tile('light.b', size='full'), tile('light.c'), tile('light.d', size='wide')]
        self.assertEqual(pack_slots(tiles), [0, 6, 12, 14])
        tiles = [tile('light.b', size='full'), tile('light.c')]
        self.assertEqual(pack_slots(tiles), [0, 6])

    def test_free_slot_for_a_full_tile_is_an_empty_page(self):
        tiles = [tile('light.a', 0), tile('light.b', 7)]
        self.assertEqual(free_slot(tiles, 'full'), 12)
        self.assertIsNone(free_slot(tiles, 'full', page=1))
        self.assertEqual(free_slot(tiles, 'full', page=2), 12)
        self.assertEqual(free_slot(tiles, 'wide', page=0), 2)

    def test_place_tile_snaps_a_full_tile_to_its_page_start(self):
        tiles = [tile('light.a', 0)]
        full = tile('light.b', size='full')
        tiles.append(full)
        place_tile(full, tiles, slot=9)
        self.assertEqual(full['slot'], 6)
        with self.assertRaisesRegex(ValueError, 'taken by light.b'):
            place_tile(tile('light.c'), tiles, slot=10)
        with self.assertRaisesRegex(ValueError, 'page of its own'):
            place_tile(tile('light.d', size='full'), tiles, page=0)


class Layouts(unittest.TestCase):
    def test_forty_eight_tiles_and_the_firmware_they_need(self):
        forty_eight = validate_layout({'title': 'Home', 'tiles': [tile(f'light.a{i}') for i in range(MAX_TILES)]})
        self.assertEqual(len(forty_eight['tiles']), 48)
        self.assertEqual([t['slot'] for t in forty_eight['tiles']][-1], 47)
        self.assertEqual(min_firmware(forty_eight), FULL_PAGE_MIN_FIRMWARE)
        twenty = validate_layout({'title': 'Home', 'tiles': [tile(f'light.a{i}') for i in range(20)]})
        self.assertEqual(min_firmware(twenty), (0, 2, 7))
        with self.assertRaisesRegex(ValueError, 'at most 48'):
            validate_layout({'title': 'Home', 'tiles': [tile(f'light.a{i}') for i in range(49)]})

    def test_full_tile_positions(self):
        layout = validate_layout({'title': 'Home', 'tiles': [tile('light.a', 0), tile('light.b', 6, size='full'), tile('light.c', 12)]})
        self.assertEqual([t['slot'] for t in layout['tiles']], [0, 6, 12])
        self.assertEqual(min_firmware(layout), FULL_PAGE_MIN_FIRMWARE)
        with self.assertRaisesRegex(ValueError, 'top of its page'):
            validate_layout({'title': 'Home', 'tiles': [tile('light.b', 8, size='full')]})
        with self.assertRaisesRegex(ValueError, 'same spot'):
            validate_layout({'title': 'Home', 'tiles': [tile('light.a', 6, size='full'), tile('light.c', 11)]})
        # A full-page card is one big button unless a control was chosen; a wide card shows its usual one.
        self.assertIsNone(resolve_controls(tile('light.a', 0, size='full')))
        self.assertEqual(resolve_controls(tile('light.a', 0, size='full', controls='brightness')), 'brightness')
        self.assertEqual(resolve_controls(tile('light.a', 0, size='wide')), 'toggle')
        # A forecast keeps a full tile full; on a single tile it still widens to a row.
        full = validate_layout({'title': 'Home', 'tiles': [tile('weather.home', 0, display='forecast', size='full')]})
        self.assertEqual(full['tiles'][0]['options']['size'], 'full')
        wide = validate_layout({'title': 'Home', 'tiles': [tile('weather.home', 0, display='forecast')]})
        self.assertEqual(wide['tiles'][0]['options']['size'], 'wide')

    def test_navigation_tile(self):
        # One built-in entity per page it goes to, so an entity still appears once on a screen.
        self.assertEqual(BUILTIN['screen.page_3'], 'Go to page 3')
        self.assertEqual([page_target(e) for e in ('screen.page_1', 'screen.page_8', 'screen.page_9', 'screen.page', 'light.a')], [1, 8, 0, 0, 0])
        layout = validate_layout({'title': 'Home', 'tiles': [tile('screen.page_3', 0, icon='radiator'), tile('screen.page_5', 1)]})
        self.assertEqual(layout['tiles'][0]['options'], {'icon': 'radiator'})
        self.assertEqual(min_firmware(layout), FULL_PAGE_MIN_FIRMWARE)
        # A display or control makes no sense on it and is dropped; the whole page is not for it.
        layout = validate_layout({'title': 'Home', 'tiles': [tile('screen.page_2', 0, display='digital', size='wide')]})
        self.assertEqual(layout['tiles'][0]['options'], {'size': 'wide'})
        with self.assertRaisesRegex(ValueError, 'single or double width'):
            validate_layout({'title': 'Home', 'tiles': [tile('screen.page_2', 0, size='full')]})
        for entity in ('screen.page_9', 'screen.page', 'screen.page_0'):
            with self.assertRaisesRegex(ValueError, "isn't supported"):
                validate_layout({'title': 'Home', 'tiles': [tile(entity, 0)]})
        # The same navigation tile on several pages is firmware 0.2.65's (app 0.2.78), any other entity 0.16.0's.
        twice = validate_layout({'title': 'Home', 'tiles': [tile('screen.page_2', 0), tile('screen.page_2', 7)]})
        self.assertEqual(min_firmware(twice), (0, 2, 65))
        lamps = validate_layout({'title': 'Home', 'tiles': [tile('light.a', 0), tile('light.a', 1)]})
        self.assertEqual(min_firmware(lamps), (0, 16, 0))

    def test_snapshot_and_wire(self):
        layout = validate_layout({'title': 'Home', 'tiles': [tile('screen.page_3', 0, icon='radiator'), tile('light.a', 6, size='full')]})
        snapshot = layout_snapshot({'name': 'Hall', 'node': 'hall'}, layout)
        self.assertEqual(snapshot['tiles'][0]['to_page'], 3)
        self.assertEqual(snapshot['tiles'][1]['size'], 'full')
        self.assertNotIn('to_page', snapshot['tiles'][1])
        self.assertEqual(snapshot['pages'], 2)
        # A built-in tile's chosen icon travels as its codepoint, like every other tile's, and the page with it.
        message = state_message(0, layout['tiles'][0], {})
        self.assertEqual(message['o'], {'icon': tile_icons.ICONS['radiator'][0]})
        self.assertEqual(message['name'], 'Go to page 3')
        # Without a chosen icon nothing travels: the screen draws the arrow itself, the editor shows the same one.
        self.assertNotIn('o', state_message(0, tile('screen.page_2', 0), {}))
        self.assertEqual(tile_icons.editor()['builtin']['screen.page_2'], tile_icons.GLYPHS['arrow-right'])
        # The big icon font carries the domain icons and the built-in cards' icons, every name a real glyph.
        for name in tile_icons.BIG_GLYPHS:
            self.assertIn(name, tile_icons.GLYPHS)
        self.assertIn(tile_icons.BUILTIN_TILES['screen.page_1'], tile_icons.BIG_GLYPHS)
        self.assertIn('lightbulb-off', tile_icons.BIG_GLYPHS)


class Events(unittest.TestCase):
    def test_add_a_full_tile_and_a_navigation_tile(self):
        layout = validate_layout({'title': 'Home', 'tiles': [tile('light.a', 0), tile('light.b', 1)]})
        result = apply_tile_event(layout, 'add', {'entity': 'light.c', 'size': 'full screen'})
        self.assertEqual(next(t for t in result['tiles'] if t['entity'] == 'light.c'), {'entity': 'light.c', 'name': '', 'options': {'size': 'full'}, 'slot': 6})
        result = apply_tile_event(result, 'add', {'entity': 'screen.page_2', 'name': 'Heating', 'page': 1})
        page_tile = next(t for t in result['tiles'] if t['entity'] == 'screen.page_2')
        self.assertEqual((page_tile['name'], page_tile.get('options'), page_tile['slot']), ('Heating', None, 2))
        with self.assertRaisesRegex(ValueError, 'cannot go on a screen'):
            apply_tile_event(result, 'add', {'entity': 'screen.page_9'})
        # A tile that grows to the whole page keeps its page when nothing else is there, else moves to an empty page.
        result = apply_tile_event(result, 'add', {'entity': 'light.a', 'size': 'full'})
        self.assertEqual(next(t for t in result['tiles'] if t['entity'] == 'light.a')['slot'], 12)
        with self.assertRaisesRegex(ValueError, 'not empty'):
            apply_tile_event(result, 'move', {'entity': 'light.c', 'page': 1})
        # Ordering the page of a full tile keeps it at the page start.
        result = apply_tile_event(result, 'order', {'page': 2, 'entities': ['light.c']})
        self.assertEqual(next(t for t in result['tiles'] if t['entity'] == 'light.c')['slot'], 6)

    def test_forty_eight_is_the_limit(self):
        layout = validate_layout({'title': 'Home', 'tiles': [tile(f'light.a{i}', i) for i in range(MAX_TILES)]})
        with self.assertRaisesRegex(ValueError, f'{MAX_TILES} tiles'):
            apply_tile_event(layout, 'add', {'entity': 'light.extra'})
        self.assertEqual(SLOTS_PER_PAGE * MAX_PAGES, MAX_TILES)


if __name__ == '__main__':
    unittest.main()
