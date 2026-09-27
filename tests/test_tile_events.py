from manager_fixtures import with_screen_grid
"""Tiles from a Home Assistant event (app 0.2.51): Claude in Home Assistant, or any automation, puts
something on a screen, moves it or orders a page, and the app saves and pushes it like the editor does."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import (MAX_PAGES, SLOTS_PER_PAGE, TILE_EVENTS, TILE_RESULT_EVENT,  # noqa: E402
                  apply_tile_event, layout_snapshot, match_screen)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager

SCREENS = [{'id': 'text.kitchen_tiles', 'name': 'Kitchen screen', 'node': 'kitchen-screen', 'device': 'Kitchen screen', 'area': 'Kitchen'},
           {'id': 'text.living_tiles', 'name': 'CYD 2.8in', 'node': 'cyd-2432s028', 'device': 'CYD 2.8in', 'area': 'Living room'}]
LAYOUTS = {'text.living_tiles': {'title': 'Living room', 'tiles': []}}


def layout(*tiles):
    return {'title': 'Living room', 'tiles': [dict(tile) for tile in tiles]}


def tile(entity, slot, **options):
    item = {'entity': entity, 'name': '', 'slot': slot}
    if options:
        item['options'] = options
    return item


def places(result):
    return [(item['entity'], item['slot']) for item in sorted(result['tiles'], key=lambda t: t['slot'])]


class ScreenByName(unittest.TestCase):
    def test_device_name_friendly_name_area_and_title(self):
        for wanted in ('cyd-2432s028', 'CYD 2.8in', 'living room', 'Living Room', 'cyd 2432s028'):
            self.assertEqual(match_screen(SCREENS, wanted, LAYOUTS)['id'], 'text.living_tiles', wanted)
        self.assertEqual(match_screen(SCREENS, 'kitchen', LAYOUTS)['id'], 'text.kitchen_tiles')

    def test_one_screen_needs_no_name_and_unknown_names_say_which_exist(self):
        self.assertEqual(match_screen(SCREENS[:1], '', LAYOUTS)['id'], 'text.kitchen_tiles')
        with self.assertRaisesRegex(ValueError, 'Name the screen.*Kitchen screen'):
            match_screen(SCREENS, None, LAYOUTS)
        with self.assertRaisesRegex(ValueError, 'No screen called "attic".*Paired'):
            match_screen(SCREENS, 'attic', LAYOUTS)
        with self.assertRaisesRegex(ValueError, 'fits more than one screen'):
            match_screen([{'id': 'a', 'name': 'Screen one'}, {'id': 'b', 'name': 'Screen two'}], 'screen')


class AddAndUpdate(unittest.TestCase):
    def test_a_new_tile_takes_the_first_free_spot(self):
        result = apply_tile_event(layout(tile('light.a', 0), tile('switch.b', 2)), 'add', {'entity': 'vacuum.s8'})
        self.assertEqual(places(result), [('light.a', 0), ('vacuum.s8', 1), ('switch.b', 2)])

    def test_a_control_or_a_forecast_widens_the_tile_itself(self):
        result = apply_tile_event(layout(), 'add', {'entity': 'light.living', 'controls': 'brightness'})
        self.assertEqual(result['tiles'][0]['options'], {'controls': 'brightness', 'size': 'wide'})
        result = apply_tile_event(layout(), 'add', {'entity': 'weather.home', 'display': 'forecast'})
        self.assertEqual(result['tiles'][0]['options'], {'display': 'forecast', 'size': 'wide'})
        result = apply_tile_event(layout(), 'add', {'entity': 'light.living', 'size': 'double', 'color': 'orange'})
        self.assertEqual(result['tiles'][0]['options'], {'size': 'wide', 'background': 'orange'})

    def test_a_wide_tile_starts_in_the_left_column(self):
        result = apply_tile_event(layout(tile('light.a', 0)), 'add', {'entity': 'weather.home', 'display': 'forecast'})
        self.assertEqual(places(result), [('light.a', 0), ('weather.home', 2)])

    def test_the_same_entity_again_changes_that_tile(self):
        start = layout(tile('light.a', 0), tile('switch.b', 1))
        result = apply_tile_event(start, 'add', {'entity': 'light.a', 'controls': 'brightness', 'name': 'Reading lamp'})
        self.assertEqual(len(result['tiles']), 2)
        changed = next(t for t in result['tiles'] if t['entity'] == 'light.a')
        self.assertEqual((changed['name'], changed['options']), ('Reading lamp', {'controls': 'brightness', 'size': 'wide'}))
        self.assertEqual(changed['slot'], 2, 'it needs two cells now, so it moves to a row where it fits')

    def test_an_exact_spot_and_a_page(self):
        start = layout(tile('light.a', 0))
        self.assertEqual(places(apply_tile_event(start, 'add', {'entity': 'vacuum.s8', 'page': 2}))[-1], ('vacuum.s8', 6))
        self.assertEqual(places(apply_tile_event(start, 'add', {'entity': 'vacuum.s8', 'page': 1, 'row': 2, 'column': 'right'}))[-1], ('vacuum.s8', 3))
        with self.assertRaisesRegex(ValueError, 'taken by light.a'):
            apply_tile_event(start, 'add', {'entity': 'vacuum.s8', 'page': 1, 'row': 1, 'column': 'left'})

    def test_what_it_refuses(self):
        for data, message in (({'entity': 'zone.home'}, 'cannot go on a screen'),
                              ({'entity': ''}, 'Name the entity'),
                              ({'entity': 'light.a', 'page': 9}, 'page between 1 and 8'),
                              ({'entity': 'light.a', 'row': 4, 'page': 1}, 'row between 1 and 3'),
                              ({'entity': 'light.a', 'page': 1, 'column': 'middle'}, 'column is left or right')):
            with self.assertRaisesRegex(ValueError, message):
                apply_tile_event(layout(), 'add', data)
        full = layout(*[tile(f'light.a{n}', n) for n in range(48)])
        with self.assertRaisesRegex(ValueError, '48 tiles'):
            apply_tile_event(full, 'add', {'entity': 'light.extra'})


class MoveRemoveAndOrder(unittest.TestCase):
    def test_moving_to_a_page_takes_its_first_free_spot(self):
        start = layout(tile('light.a', 0), tile('vacuum.s8', 13))
        self.assertEqual(places(apply_tile_event(start, 'move', {'entity': 'vacuum.s8', 'page': 1})),
                         [('light.a', 0), ('vacuum.s8', 1)])
        with self.assertRaisesRegex(ValueError, 'Name the page or the spot'):
            apply_tile_event(start, 'move', {'entity': 'vacuum.s8'})
        with self.assertRaisesRegex(ValueError, 'not on this screen'):
            apply_tile_event(start, 'move', {'entity': 'light.missing', 'page': 1})

    def test_a_full_page_says_so(self):
        start = layout(*[tile(f'light.a{n}', n) for n in range(6)], tile('vacuum.s8', 6))
        with self.assertRaisesRegex(ValueError, 'Page 1 is full'):
            apply_tile_event(start, 'move', {'entity': 'vacuum.s8', 'page': 1})

    def test_removing_keeps_the_others_where_they_are(self):
        start = layout(tile('light.a', 0), tile('vacuum.s8', 1), tile('switch.b', 4))
        result = apply_tile_event(start, 'remove', {'entity': 'vacuum.s8'})
        self.assertEqual(places(result), [('light.a', 0), ('switch.b', 4)])
        with self.assertRaisesRegex(ValueError, 'is not on this screen'):
            apply_tile_event(result, 'remove', {'entity': 'vacuum.s8'})

    def test_ordering_the_whole_screen_packs_it_again(self):
        start = layout(tile('script.night', 0), tile('light.a', 3), tile('vacuum.s8', 8))
        result = apply_tile_event(start, 'order', {'entities': ['light.a', 'vacuum.s8']})
        self.assertEqual(places(result), [('light.a', 0), ('vacuum.s8', 1), ('script.night', 2)])

    def test_ordering_one_page_leaves_the_other_pages_alone(self):
        start = layout(tile('script.night', 0), tile('light.a', 1), tile('vacuum.s8', 2), tile('switch.b', 7))
        result = apply_tile_event(start, 'order', {'page': 1, 'entities': 'light.a, vacuum.s8'})
        self.assertEqual(places(result), [('light.a', 0), ('vacuum.s8', 1), ('script.night', 2), ('switch.b', 7)])
        with self.assertRaisesRegex(ValueError, 'Not on page 1: switch.b'):
            apply_tile_event(start, 'order', {'page': 1, 'entities': ['switch.b']})
        with self.assertRaisesRegex(ValueError, 'Not on this screen: light.gone'):
            apply_tile_event(start, 'order', {'entities': ['light.gone']})
        with self.assertRaisesRegex(ValueError, 'in the order you want'):
            apply_tile_event(start, 'order', {})

    def test_ordering_a_page_keeps_wide_tiles_in_the_left_column(self):
        start = layout(tile('light.a', 0), tile('weather.home', 2, size='wide', display='forecast'))
        result = apply_tile_event(start, 'order', {'page': 1, 'entities': ['weather.home', 'light.a']})
        self.assertEqual(places(result), [('weather.home', 0), ('light.a', 2)])


class Snapshot(unittest.TestCase):
    def test_a_screen_reads_back_as_pages_rows_and_columns(self):
        data = layout(tile('light.a', 0), tile('weather.home', 2, size='wide', display='forecast'), tile('vacuum.s8', 7))
        snapshot = layout_snapshot(SCREENS[1], data)
        self.assertEqual((snapshot['screen'], snapshot['node'], snapshot['title'], snapshot['pages']),
                         ('CYD 2.8in', 'cyd-2432s028', 'Living room', 2))
        self.assertEqual([(t['entity'], t['page'], t['row'], t['column'], t['size']) for t in snapshot['tiles']],
                         [('light.a', 1, 1, 'left', 'single'), ('weather.home', 1, 2, 'left', 'wide'), ('vacuum.s8', 2, 1, 'right', 'single')])
        self.assertEqual(snapshot['tiles'][1]['display'], 'forecast')


def fake_ha():
    """One paired screen and the entities a tile can show."""
    class HA:
        online = True

        def __init__(self):
            self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                             {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'}]
            self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'living-room'}, 'sensor.d1_fw': {'state': '0.2.43'}}
            for entity, name in (('light.reading', 'Reading lamp'), ('vacuum.s8', 'S8'), ('weather.home', 'Home')):
                self.registry.append({'entity_id': entity, 'platform': 'demo', 'original_name': name, 'device_id': 'd9'})
                self.states[entity] = {'state': 'on', 'attributes': {'friendly_name': name}}
            self.devices = [{'id': 'd1', 'name': 'Living room screen'}, {'id': 'd9', 'name': 'Demo'}]
            self.areas = []
            self.changed = asyncio.Event()
            self.tile_events = asyncio.Queue()
            self.fired, self.published = [], {}

        async def fire(self, event_type, data):
            self.fired.append((event_type, data))

        async def set_state(self, entity_id, state, attributes):
            self.published[entity_id] = (state, attributes)
    return HA()


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Through(unittest.IsolatedAsyncioTestCase):
    async def test_an_event_saves_the_layout_and_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            m = Manager(with_screen_grid(fake_ha()), path)
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'vacuum.s8', 'screen': 'living room'}))
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'light.reading', 'controls': 'brightness'}))
            worker = asyncio.create_task(m.tile_loop())
            for _ in range(200):
                await asyncio.sleep(0.01)
                if len(m.ha.fired) == 2:
                    break
            worker.cancel()
            saved = m.layouts['text.d1_tiles']
            self.assertEqual([(t['entity'], t['slot']) for t in saved['tiles']], [('vacuum.s8', 0), ('light.reading', 2)])
            self.assertEqual(saved['tiles'][1]['options'], {'controls': 'brightness', 'size': 'wide'})
            self.assertEqual([(event, answer['ok'], answer['entity']) for event, answer in m.ha.fired],
                             [(TILE_RESULT_EVENT, True, 'vacuum.s8'), (TILE_RESULT_EVENT, True, 'light.reading')])
            state, attributes = m.ha.published['sensor.esp_screens_living_room']
            self.assertEqual(state, 2)
            self.assertEqual([t['entity'] for t in attributes['tiles']], ['vacuum.s8', 'light.reading'])

    async def test_a_refused_event_changes_nothing_and_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screens.json'
            m = Manager(with_screen_grid(fake_ha()), path)
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', {'entity': 'light.reading', 'screen': 'attic'}))
            worker = asyncio.create_task(m.tile_loop())
            with self.assertLogs('screen_manager', 'INFO') as logs:
                for _ in range(200):
                    await asyncio.sleep(0.01)
                    if m.ha.fired:
                        break
            worker.cancel()
            self.assertFalse(path.exists())
            event, answer = m.ha.fired[0]
            self.assertEqual((event, answer['ok']), (TILE_RESULT_EVENT, False))
            self.assertIn('No screen called "attic"', answer['error'])
            self.assertTrue(any('refused' in line for line in logs.output), logs.output)

    async def test_every_event_name_is_handled(self):
        self.assertEqual(set(TILE_EVENTS), {'esp_screens_add_tile', 'esp_screens_remove_tile', 'esp_screens_move_tile', 'esp_screens_order_tiles'})
        self.assertEqual((MAX_PAGES, SLOTS_PER_PAGE), (8, 6))


if __name__ == '__main__':
    unittest.main()
