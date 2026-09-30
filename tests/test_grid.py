"""The grid of a screen's pages (app 0.2.94): every slot, page and tile count follows the screen, not the first boards.

The firmware derives its grid from the board (GRID_COLS x GRID_ROWS, runtime_model.h); the add-on used to count with
six cells and 48 tiles whatever the screen, so on a 3 x 3 panel a wide tile in the second row, a full tile on page 2
and anything from page 6 on were refused at save. `core.Grid` holds the firmware's rules once; `grid_of(screen)` gives
the grid of the screen in hand; everything that counts cells takes it.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
from core import (DEFAULT_GRID, FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES, Grid, apply_tile_event, event_slot,  # noqa: E402
                  firmware_features, grid_of, layout_snapshot, pack_slots, packed_slots, tile_limit, validate_layout)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager

WIDE = Grid(3, 3)      # the Waveshare 800 x 480
TALL = Grid(1, 4)      # a CYD in portrait, one column
BIG = Grid(4, 4)       # a seven-inch panel


def tile(entity, slot=None, **options):
    item = {'entity': entity, 'name': ''}
    if slot is not None:
        item['slot'] = slot
    if options:
        item['options'] = options
    return item


class Rules(unittest.TestCase):
    def test_the_first_boards_keep_their_numbers(self):
        self.assertEqual((DEFAULT_GRID.columns, DEFAULT_GRID.rows, DEFAULT_GRID.slots, DEFAULT_GRID.pages, DEFAULT_GRID.max_tiles), (2, 3, 6, 8, 48))
        self.assertEqual((core.SLOTS_PER_PAGE, core.MAX_PAGES, core.MAX_SLOTS, core.MAX_TILES), (6, 8, 48, 48))

    def test_every_grid_has_eight_pages_and_sixty_four_tiles(self):
        # components/smart_display/runtime_model.h (firmware 0.18.0+): eight pages whatever the grid, 64 tiles over them.
        self.assertEqual((WIDE.pages, WIDE.max_slots, WIDE.max_tiles), (8, 72, 64))
        self.assertEqual((TALL.pages, TALL.max_slots, TALL.max_tiles), (8, 32, 32))
        self.assertEqual((BIG.pages, BIG.max_slots, BIG.max_tiles), (8, 128, 64))
        self.assertEqual((Grid(8, 8).pages, Grid(8, 8).max_tiles), (8, 64))
        self.assertEqual((Grid(5, 5).pages, Grid(5, 5).max_slots, Grid(5, 5).max_tiles), (8, 200, 64))
        # Older firmware had as many pages as 64 tiles fill: seven of nine cells, three of twenty.
        self.assertEqual((WIDE.legacy_pages, BIG.legacy_pages, Grid(5, 4).legacy_pages, Grid(8, 8).legacy_pages), (7, 4, 3, 1))
        for columns, rows in ((0, 3), (2, 0), (9, 8), (13, 5)):
            with self.assertRaises(ValueError):
                Grid(columns, rows)
        self.assertEqual((FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES), (8, 64))

    def test_a_wide_tile_needs_a_cell_beside_it_in_the_same_row(self):
        self.assertEqual([slot for slot in range(9) if WIDE.wide_fits(slot)], [0, 1, 3, 4, 6, 7])
        self.assertEqual(WIDE.footprint(4, 'wide'), (4, 5))
        self.assertEqual(WIDE.footprint(9, 'full'), tuple(range(9, 18)))
        # One column: a wide tile is the cell itself, everywhere.
        self.assertEqual((TALL.wide_span, TALL.footprint(2, 'wide'), TALL.wide_fits(3)), (1, (2,), True))
        self.assertEqual(DEFAULT_GRID.footprint(2, True), (2, 3))

    def test_packing_starts_a_wide_tile_on_the_next_row_and_a_full_one_on_the_next_page(self):
        tiles = [tile('a'), tile('b'), tile('w', size='wide'), tile('c'), tile('f', size='full'), tile('d')]
        self.assertEqual(pack_slots(tiles, WIDE), [0, 1, 3, 5, 9, 18])
        self.assertEqual(pack_slots(tiles, TALL), [0, 1, 2, 3, 4, 8])
        self.assertEqual(pack_slots(tiles), [0, 1, 2, 4, 6, 12])
        # Past the last page the packing is refused, on this screen's pages.
        with self.assertRaises(ValueError):
            packed_slots([tile(f'light.{i}') for i in range(73)], WIDE)
        self.assertEqual(len(packed_slots([tile(f'light.{i}') for i in range(72)], WIDE)), 72)

    def test_rows_columns_and_pages_are_read_back_from_a_slot(self):
        self.assertEqual((WIDE.page_of(13), WIDE.row_of(13), WIDE.column_of(13), WIDE.column_word(13)), (1, 2, 2, 2))
        self.assertEqual((DEFAULT_GRID.row_of(5), DEFAULT_GRID.column_word(5), DEFAULT_GRID.column_word(4)), (3, 'right', 'left'))
        self.assertEqual(WIDE.slot_at(1, 2, 2), 13)
        self.assertEqual(TALL.slot_at(2, 3, 1), 10)

    def test_holds_says_whether_stored_positions_belong_to_a_grid(self):
        made_on_wide = [tile('a', 3, size='wide'), tile('f', 9, size='full'), tile('b', 62)]
        self.assertTrue(WIDE.holds(made_on_wide))
        self.assertFalse(DEFAULT_GRID.holds(made_on_wide))
        self.assertTrue(DEFAULT_GRID.holds([tile('a', 2, size='wide'), tile('f', 6, size='full')]))
        self.assertFalse(TALL.holds([tile('a', 32)]))


class Screens(unittest.TestCase):
    def test_the_grid_of_a_screen_comes_from_its_shape(self):
        self.assertEqual(grid_of({'shape': {'width': 800, 'height': 480, 'columns': 3, 'rows': 3}}), WIDE)
        self.assertEqual(grid_of({'board': 'waveshare43'}), WIDE)
        self.assertEqual(grid_of({'package': 'packages/waveshare43.yaml'}), WIDE)
        self.assertEqual(grid_of({'board': 'guition'}), DEFAULT_GRID)
        self.assertEqual(grid_of({}), DEFAULT_GRID)
        self.assertEqual(grid_of(None), DEFAULT_GRID)
        # A shape nothing could hold falls back rather than stopping the app.
        self.assertEqual(grid_of({'shape': {'width': 800, 'height': 480, 'columns': 0, 'rows': 3}}), DEFAULT_GRID)

    def test_the_tile_limit_is_the_smaller_of_the_firmware_and_the_grid(self):
        self.assertEqual(tile_limit((0, 2, 80), WIDE), 63)
        self.assertEqual(tile_limit((0, 2, 80), TALL), 32)
        self.assertEqual(tile_limit((0, 2, 80)), 48)
        self.assertEqual(tile_limit((0, 2, 40), WIDE), 20)
        self.assertEqual(firmware_features((0, 2, 80), WIDE)['tile_limit'], 63)
        # Eight pages on every grid (firmware 0.18.0+): 64 tiles on nine cells a page, eight pages where it had seven.
        self.assertEqual(tile_limit((0, 18, 0), WIDE), 64)
        self.assertEqual((firmware_features((0, 17, 0), WIDE)['page_limit'], firmware_features((0, 18, 0), WIDE)['page_limit']), (7, 8))
        self.assertEqual(firmware_features((0, 17, 0), Grid(5, 5))['page_limit'], 2)


class Layouts(unittest.TestCase):
    def test_a_layout_is_checked_on_the_screens_own_grid(self):
        data = {'title': 'Hall', 'tiles': [tile('light.a', 3, size='wide'), tile('light.b', 9, size='full'), tile('light.c', 62)]}
        layout = validate_layout(data, grid=WIDE)
        self.assertEqual([t['slot'] for t in layout['tiles']], [3, 9, 62])
        # The same positions mean something else on two columns, and are refused there.
        with self.assertRaisesRegex(ValueError, 'left column'):
            validate_layout(data, grid=DEFAULT_GRID)
        for bad, why in (({'title': 'Hall', 'tiles': [tile('light.a', 2, size='wide')]}, 'left column'),
                         ({'title': 'Hall', 'tiles': [tile('light.a', 10, size='full')]}, 'top of its page'),
                         ({'title': 'Hall', 'tiles': [tile('light.a', 72)]}, 'position'),
                         ({'title': 'Hall', 'tiles': [tile('light.a', 4, size='wide'), tile('light.b', 5)]}, 'same spot'),
                         ({'title': 'Hall', 'tiles': [], 'pages': 9}, 'pages')):
            with self.assertRaisesRegex(ValueError, why):
                validate_layout(bad, grid=WIDE)
        self.assertEqual(validate_layout({'title': 'Hall', 'tiles': [], 'pages': 8}, grid=WIDE)['pages'], 8)
        # Without positions the tiles are packed on that grid.
        packed = validate_layout({'title': 'Hall', 'tiles': [tile('light.a'), tile('light.b'), tile('light.c', size='wide')]}, grid=WIDE)
        self.assertEqual([t['slot'] for t in packed['tiles']], [0, 1, 3])

    def test_the_store_keeps_positions_it_cannot_yet_place(self):
        # At start-up no screen is in hand, so a layout made on a 3 x 3 screen is kept as it is; the screen's grid
        # checks it again at the next save.
        stored = validate_layout({'title': 'Hall', 'tiles': [tile('light.a', 3, size='wide'), tile('light.b', 62)], 'pages': 7}, stored=True, grid=None)
        self.assertEqual([t['slot'] for t in stored['tiles']], [3, 62])
        with self.assertRaisesRegex(ValueError, 'position'):
            validate_layout({'title': 'Hall', 'tiles': [tile('light.a', 64)]}, stored=True, grid=None)
        sixty_four = validate_layout({'title': 'Hall', 'tiles': [tile(f'light.a{i}', i) for i in range(64)]}, stored=True, grid=None)
        self.assertEqual(len(sixty_four['tiles']), 64)
        # Without a screen the first boards' grid is the rule, as it always was.
        with self.assertRaisesRegex(ValueError, 'left column'):
            validate_layout({'title': 'Hall', 'tiles': [tile('light.a', 3, size='wide')]})


class Events(unittest.TestCase):
    def test_a_spot_is_named_by_row_and_column_on_the_screens_grid(self):
        self.assertEqual(event_slot({'row': 2, 'column': 'right'}, 0, WIDE), 5)
        self.assertEqual(event_slot({'row': 2, 'column': 2}, 1, WIDE), 13)
        self.assertEqual(event_slot({'row': 3, 'column': 'middle'}, 0, WIDE), 7)
        self.assertEqual(event_slot({'row': 4, 'column': 'left'}, 1, TALL), 7)
        self.assertEqual(event_slot({'slot': 62}, None, WIDE), 62)
        for data, why in (({'row': 4, 'column': 'left'}, 'row between 1 and 3'), ({'row': 1, 'column': 4}, 'column between 1 and 3'),
                          ({'row': 1, 'column': 'top'}, 'column between 1 and 3'), ({'slot': 72}, 'spot between 0 and 71')):
            with self.assertRaisesRegex(ValueError, why):
                event_slot(data, 0, WIDE)
        # Two columns keep their words, and their message.
        with self.assertRaisesRegex(ValueError, 'left or right'):
            event_slot({'row': 1, 'column': 'middle'}, 0, DEFAULT_GRID)
        with self.assertRaisesRegex(ValueError, 'row between 1 and 4'):
            event_slot({'row': 5}, 0, TALL)

    def test_events_place_tiles_on_the_screens_grid(self):
        start = {'title': 'Hall', 'tiles': [tile('light.a', 0), tile('light.b', 1), tile('light.c', 2)]}
        # The first row is full: a wide tile starts the second row, not the last cell of the first.
        result = apply_tile_event(start, 'add', {'entity': 'light.w', 'size': 'wide'}, grid=WIDE)
        self.assertEqual(sorted((t['entity'], t['slot']) for t in result['tiles'])[-1], ('light.w', 3))
        result = apply_tile_event(start, 'add', {'entity': 'light.f', 'size': 'full'}, grid=WIDE)
        self.assertEqual(next(t['slot'] for t in result['tiles'] if t['entity'] == 'light.f'), 9)
        result = apply_tile_event(start, 'add', {'entity': 'light.d', 'page': 7, 'row': 3, 'column': 3}, grid=WIDE)
        self.assertEqual(next(t['slot'] for t in result['tiles'] if t['entity'] == 'light.d'), 62)
        with self.assertRaisesRegex(ValueError, 'page between 1 and 8'):
            apply_tile_event(start, 'add', {'entity': 'light.d', 'page': 9}, grid=WIDE)
        # A wide tile dropped on the last column moves one column left, into the same row.
        result = apply_tile_event({'title': 'Hall', 'tiles': []}, 'add', {'entity': 'light.w', 'size': 'wide', 'slot': 5}, grid=WIDE)
        self.assertEqual(result['tiles'][0]['slot'], 4)
        # A single column: a wide tile is one cell, a page is four.
        result = apply_tile_event({'title': 'Hall', 'tiles': [tile('light.a', 0)]}, 'add', {'entity': 'light.w', 'size': 'wide'}, grid=TALL)
        self.assertEqual(next(t['slot'] for t in result['tiles'] if t['entity'] == 'light.w'), 1)
        full = {'title': 'Hall', 'tiles': [tile(f'light.{i}', i) for i in range(64)]}
        with self.assertRaisesRegex(ValueError, '64 tiles'):
            apply_tile_event(full, 'add', {'entity': 'light.extra'}, grid=WIDE)

    def test_the_sensor_reads_back_in_the_screens_own_grid(self):
        screen = {'name': 'Hall', 'node': 'hall', 'shape': {'width': 800, 'height': 480, 'columns': 3, 'rows': 3}}
        data = {'title': 'Hall', 'tiles': [tile('light.a', 0), tile('light.w', 4, size='wide'), tile('light.b', 13)]}
        snapshot = layout_snapshot(screen, data)
        self.assertEqual((snapshot['columns'], snapshot['rows'], snapshot['max_pages'], snapshot['pages']), (3, 3, 8, 2))
        self.assertEqual([(t['entity'], t['page'], t['row'], t['column']) for t in snapshot['tiles']],
                         [('light.a', 1, 1, 1), ('light.w', 1, 2, 2), ('light.b', 2, 2, 2)])
        # The first boards keep left and right.
        two = layout_snapshot({'name': 'Kitchen', 'board': 'cyd'}, {'title': 'Kitchen', 'tiles': [tile('light.a', 5)]})
        self.assertEqual((two['columns'], two['rows'], two['max_pages'], two['tiles'][0]['column']), (2, 3, 8, 'right'))


def fake_ha(shape='800x480 3x3 217dpi standard', board='waveshare43'):
    """One paired screen that says what it looks like, and a few entities."""
    class HA:
        online = True

        def __init__(self):
            self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_shape', 'platform': 'esphome', 'original_name': 'Screen layout', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_board', 'platform': 'esphome', 'original_name': 'Screen board', 'device_id': 'd1'}]
            self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'hall'}, 'sensor.d1_fw': {'state': '0.2.80'},
                           'sensor.d1_shape': {'state': shape}, 'sensor.d1_board': {'state': board}}
            for i in range(70):
                entity = f'light.l{i}'
                self.registry.append({'entity_id': entity, 'platform': 'demo', 'original_name': f'Lamp {i}', 'device_id': 'd9'})
                self.states[entity] = {'state': 'on', 'attributes': {'friendly_name': f'Lamp {i}'}}
            self.devices = [{'id': 'd1', 'name': 'Hall screen'}, {'id': 'd9', 'name': 'Lamps'}]
            self.areas = []
            self.log = []
            self.changed = asyncio.Event()

        async def call(self, *args):
            self.log.append(('call', args))
    return HA()


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp is not installed')
class OnTheManager(unittest.TestCase):
    def manager(self, ha):
        m = Manager(ha, Path(self.tmp) / 'screens.json')
        m.write_layouts = lambda layouts: None
        m.notify = lambda: None
        return m

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = self.tmp_dir.name

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_a_three_by_three_screen_saves_what_its_editor_places(self):
        ha = fake_ha()
        m = self.manager(ha)
        screen = m.screens()[0]
        self.assertEqual((screen['board'], screen['shape']['columns'], screen['shape']['dpi'], screen['shape']['look']), ('waveshare43', 3, 217, 'standard'))
        self.assertEqual(core.grid_of(screen), WIDE)
        tiles = [tile('light.l0', 3, size='wide'), tile('light.l1', 9, size='full'), tile('light.l2', 62)]
        m.save('text.d1_tiles', {'title': 'Hall', 'tiles': tiles, 'pages': 7})
        saved = m.layouts['text.d1_tiles']
        self.assertEqual([t['slot'] for t in saved['tiles']], [3, 9, 62])
        message = m.layout_message('text.d1_tiles', saved, screen)
        self.assertEqual(message['slots'], [3, 9, 62])
        with self.assertRaisesRegex(ValueError, 'position'):
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.l0', 63)]})
        with self.assertRaisesRegex(ValueError, 'pages'):
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [], 'pages': 8})
        with self.assertRaisesRegex(ValueError, '63 tiles'):
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile(f'light.l{i}') for i in range(64)]})
        # The editor learns the same limits.
        self.assertEqual(core.firmware_features(m.firmware_version('text.d1_tiles', screen), core.grid_of(screen))['tile_limit'], 63)

    def test_an_offline_screen_is_known_by_the_yaml_its_profile_builds_from(self):
        # Every sensor unavailable: the screen says nothing about its shape or board. Its profile in the ESPHome folder
        # names the board package, and that is what the save counts with (Manager.grid_of), so an offline Waveshare
        # still takes the layout its editor drew on three columns.
        ha = fake_ha(shape='unavailable', board='unavailable')
        (Path(self.tmp) / 'hall.yaml').write_text('esphome:\n  name: hall\n  friendly_name: Hall screen\n'
                                                 'packages:\n  display:\n    url: https://github.com/MaxGramser/homeassistant_espscreen\n'
                                                 '    files: [packages/waveshare43.yaml]\n    ref: main\n'
                                                 'api:\n  encryption:\n    key: "Y2hlY2stYnVpbGQtcGxhY2Vob2xkZXIta2V5LTMyYnk="\n')
        import os
        before = os.environ.get('ESPHOME_CONFIG')
        os.environ['ESPHOME_CONFIG'] = self.tmp
        try:
            m = self.manager(ha)
        finally:
            if before is None:
                os.environ.pop('ESPHOME_CONFIG', None)
            else:
                os.environ['ESPHOME_CONFIG'] = before
        screen = m.screens()[0]
        self.assertIsNone(screen.get('shape'))
        self.assertEqual(m.package_of(screen), 'packages/waveshare43.yaml')
        self.assertEqual(m.orientation_of(screen), 'landscape')
        self.assertEqual(m.grid_of(screen), WIDE)
        m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.l0', 3, size='wide'), tile('light.l1', 62)]})
        self.assertEqual([t['slot'] for t in m.layouts['text.d1_tiles']['tiles']], [3, 62])

    def test_an_offline_screen_standing_up_gets_the_grid_it_was_built_with(self):
        # The same Waveshare, built standing up (app 0.2.107): its profile carries the angle, so while the screen
        # says nothing the editor draws one column of four and a save counts those cells. Placing a tile on the
        # ninth cell of the page it had lying down is refused, because standing up that cell is on another page.
        ha = fake_ha(shape='unavailable', board='unavailable')
        (Path(self.tmp) / 'hall.yaml').write_text('substitutions:\n  LVGL_ROTATION: "90"\n'
                                                  'esphome:\n  name: hall\n  friendly_name: Hall screen\n'
                                                  'packages:\n  display:\n    url: https://github.com/MaxGramser/homeassistant_espscreen\n'
                                                  '    files: [packages/waveshare43.yaml]\n    ref: main\n'
                                                  'api:\n  encryption:\n    key: "Y2hlY2stYnVpbGQtcGxhY2Vob2xkZXIta2V5LTMyYnk="\n')
        import os
        before = os.environ.get('ESPHOME_CONFIG')
        os.environ['ESPHOME_CONFIG'] = self.tmp
        try:
            m = self.manager(ha)
        finally:
            if before is None:
                os.environ.pop('ESPHOME_CONFIG', None)
            else:
                os.environ['ESPHOME_CONFIG'] = before
        screen = m.screens()[0]
        self.assertEqual(m.orientation_of(screen), 'portrait')
        self.assertEqual(m.grid_of(screen), TALL)
        shape = core.shape_of({**screen, 'package': m.package_of(screen), 'orientation': m.orientation_of(screen)})
        self.assertEqual((shape['width'], shape['height'], shape['columns'], shape['rows']), (480, 800, 1, 4))
        m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.l0', 3), tile('light.l1', 31)]})
        self.assertEqual([t['slot'] for t in m.layouts['text.d1_tiles']['tiles']], [3, 31])
        with self.assertRaisesRegex(ValueError, 'position'):
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.l0', 32)]})

    def test_a_layout_from_another_grid_goes_out_packed_in_order(self):
        # The screen was flashed as another board and kept its name: its stored positions no longer exist. It gets its
        # tiles in order rather than a message it would refuse.
        ha = fake_ha()
        m = self.manager(ha)
        screen = m.screens()[0]
        made_on_two_columns = {'title': 'Hall', 'tiles': [tile('light.l0', 2, size='wide'), tile('light.l1', 47)]}
        message = m.layout_message('text.d1_tiles', made_on_two_columns, screen)
        self.assertEqual(message['slots'], [0, 2])
        # A screen that has not said its shape is trusted with what was stored.
        message = m.layout_message('text.d1_tiles', made_on_two_columns, {'board': 'cyd'})
        self.assertEqual(message['slots'], [2, 47])


if __name__ == '__main__':
    unittest.main()
