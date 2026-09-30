"""One entity on several tiles (app 0.4.26, firmware 0.16.0, GitHub #83): a light as a small tile on page 1 and with
its slider on page 3. Every copy is a tile of its own, with its own index on the screen and its own settings; only the
bedside clock stays once, as its keys name it. A layout with copies needs firmware 0.16.0, which says so in its hello
(`tile_repeats`), so an older screen gets the usual "Install screen firmware" refusal. From that firmware
`esp_screens_add_tile` always puts a new tile on the screen; remove and move name the copy they mean by its spot or page.
"""
import asyncio
from copy import deepcopy
import importlib.util
import itertools
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import (ENTITY_REPEAT_MIN_FIRMWARE, NIGHTSTAND, Grid, firmware_features, layout_snapshot, min_firmware,  # noqa: E402
                  run_tile_event, state_message, validate_layout)
from layout_migrations import migrate_legacy  # noqa: E402
from page_layout import compile_tiles, replace_tiles  # noqa: E402
import page_delivery  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from manager_fixtures import with_screen_grid
    import test_tile_events
    from server import Manager


def tile(entity, slot, **options):
    item = {'entity': entity, 'name': '', 'slot': slot}
    if options:
        item['options'] = options
    return item


def layout(*tiles):
    return {'title': 'Hall', 'tiles': [dict(t) for t in tiles]}


def places(result):
    return [(t['entity'], t.get('slot')) for t in sorted(result['tiles'], key=lambda t: t.get('slot', 99))]


CLOCK = {'entity': NIGHTSTAND, 'name': '', 'slot': 0, 'options': {'size': 'full', 'background': 'none'}}
KEY = {'entity': 'light.bedside', 'name': 'Lamp', 'in': NIGHTSTAND, 'key': 0}
# A lamp on page 1 and again, with its slider and a name of its own, on page 2.
LAMPS = layout(tile('light.a', 0), tile('light.b', 1), tile('light.a', 6, inline='slider'))


class Layouts(unittest.TestCase):
    def test_any_entity_may_be_on_several_tiles_from_firmware_0_16_0(self):
        result = validate_layout(LAMPS)
        self.assertEqual(places(result), [('light.a', 0), ('light.b', 1), ('light.a', 6)])
        self.assertEqual(result['tiles'][2]['options'], {'inline': 'slider'})
        self.assertEqual(ENTITY_REPEAT_MIN_FIRMWARE, (0, 16, 0))
        self.assertEqual(min_firmware(result), (0, 16, 0))
        self.assertIsNone(min_firmware(validate_layout(layout(tile('light.a', 0)))), 'one copy: as before')
        self.assertTrue(firmware_features((0, 16, 0))['entity_tiles_repeat'])
        self.assertFalse(firmware_features((0, 15, 0))['entity_tiles_repeat'])

    def test_the_bedside_clock_is_once_on_a_screen(self):
        with self.assertRaisesRegex(ValueError, 'bedside clock can only be on a screen once'):
            validate_layout(layout(CLOCK, {**CLOCK, 'slot': 6}))

    def test_the_sensor_lists_every_copy(self):
        snapshot = layout_snapshot({'name': 'Hall', 'node': 'hall'}, validate_layout(LAMPS))
        self.assertEqual([(t['entity'], t['page'], t['slot']) for t in snapshot['tiles']],
                         [('light.a', 1, 0), ('light.b', 1, 1), ('light.a', 2, 6)])

    def test_a_v1_layout_keeps_one_tile_of_an_entity_as_it_always_showed(self):
        counter = itertools.count(1)
        migrated = migrate_legacy({'title': 'Hall', 'tiles': deepcopy(LAMPS['tiles'])}, Grid(), lambda: f'{next(counter):016x}', recover=True)
        tiles = compile_tiles(migrated['layout'], Grid())
        self.assertEqual([t['entity'] for t in tiles], ['light.a', 'light.b'])


class Events(unittest.TestCase):
    def test_add_always_puts_a_new_tile_on_the_screen(self):
        result, added = run_tile_event(LAMPS, 'add', {'entity': 'light.a', 'page': 2, 'name': 'Again'}, True, Grid(), True)
        self.assertEqual(places(result), [('light.a', 0), ('light.b', 1), ('light.a', 6), ('light.a', 7)])
        self.assertEqual((added['slot'], added['name']), (7, 'Again'))
        # Without a place: the first free spot, and the tiles already there keep their settings.
        result, added = run_tile_event(LAMPS, 'add', {'entity': 'light.a', 'color': 'blue'}, True, Grid(), True)
        self.assertEqual(added['slot'], 2)
        self.assertEqual([t.get('options') for t in result['tiles'] if t['entity'] == 'light.a' and t['slot'] != 2],
                         [None, {'inline': 'slider'}])

    def test_older_firmware_keeps_one_and_adding_it_again_moves_it(self):
        start = layout(tile('light.a', 0), tile('light.b', 1))
        result, moved = run_tile_event(start, 'add', {'entity': 'light.a', 'page': 2}, True, Grid(), False)
        self.assertEqual(places(result), [('light.b', 1), ('light.a', 6)])
        self.assertEqual(moved['slot'], 6)

    def test_remove_and_move_take_the_copy_named_or_the_first(self):
        result, removed = run_tile_event(LAMPS, 'remove', {'entity': 'light.a', 'page': 2}, True, Grid(), True)
        self.assertEqual((places(result), removed['slot']), ([('light.a', 0), ('light.b', 1)], 6))
        result, removed = run_tile_event(LAMPS, 'remove', {'entity': 'light.a'}, True, Grid(), True)
        self.assertEqual(removed['slot'], 0)
        result, moved = run_tile_event(LAMPS, 'move', {'entity': 'light.a', 'from_slot': 6, 'page': 3}, True, Grid(), True)
        self.assertEqual(places(result), [('light.a', 0), ('light.b', 1), ('light.a', 12)])
        self.assertEqual(moved['options'], {'inline': 'slider'}, 'the copy it moved, with its own settings')

    def test_the_bedside_clock_added_again_is_the_one_there(self):
        start = validate_layout(layout(CLOCK, KEY))
        result, found = run_tile_event(start, 'add', {'entity': NIGHTSTAND, 'name': 'Night'}, True, Grid(), True)
        self.assertEqual([t['entity'] for t in result['tiles']].count(NIGHTSTAND), 1)
        self.assertEqual(found['name'], 'Night')

    def test_a_key_is_removed_but_not_moved_and_adding_its_entity_places_a_tile(self):
        start = validate_layout(layout(CLOCK, KEY))
        result, removed = run_tile_event(start, 'remove', {'entity': 'light.bedside'}, True, Grid(), True)
        self.assertEqual([t['entity'] for t in result['tiles']], [NIGHTSTAND])
        self.assertEqual(removed['in'], NIGHTSTAND)
        with self.assertRaisesRegex(ValueError, 'stands under the bedside clock'):
            run_tile_event(start, 'move', {'entity': 'light.bedside', 'page': 2}, True, Grid(), True)
        result, added = run_tile_event(start, 'add', {'entity': 'light.bedside', 'page': 2}, True, Grid(), True)
        self.assertEqual((added['entity'], added['slot']), ('light.bedside', 6))
        self.assertEqual(min_firmware(result), (0, 16, 0))
        # With a placed copy too, an event acts on the placed tile and leaves the key where it is.
        result, removed = run_tile_event(result, 'remove', {'entity': 'light.bedside'}, True, Grid(), True)
        self.assertEqual(removed['slot'], 6)
        self.assertIn(KEY, result['tiles'])

    def test_an_order_that_moves_both_copies_keeps_their_ids(self):
        counter = itertools.count(1)
        record = migrate_legacy(layout(tile('light.a', 0), tile('light.b', 1), tile('light.a', 2)), Grid(), lambda: f'{next(counter):016x}')
        record['revision'] = 'r1'
        ids = [t['id'] for t in record['layout']['pages'][0]['tiles']]
        ordered = run_tile_event(compile_flat(record), 'order', {'entities': ['light.b', 'light.a', 'light.a']}, True, Grid(), True)[0]
        after = replace_tiles(record, ordered)
        self.assertEqual(sorted(t['id'] for t in after['pages'][0]['tiles']), sorted(ids))
        self.assertEqual([t['content']['entityId'] for t in after['pages'][0]['tiles']], ['light.b', 'light.a', 'light.a'])


def compile_flat(record):
    return {'title': record['layout']['title'], 'tiles': compile_tiles(record['layout'], Grid())}


class Delivery(unittest.TestCase):
    def sync(self, hello):
        counter = itertools.count(1)
        record = migrate_legacy(deepcopy(LAMPS), Grid(), lambda: f'{next(counter):016x}')
        record['revision'] = 'r1'
        tiles = compile_tiles(record['layout'], Grid())
        values = [state_message(i, t, {'light.a': {'state': 'on', 'attributes': {}}}) for i, t in enumerate(tiles)]
        sent = []

        async def send(message):
            sent.append(message)
            if message['op'] == 'hello':
                return {'protocol': 2, 'request': message['request'], 'session': 'a' * 16, 'status': 'Session:' + 'a' * 16, 'tile_keys': 1, **hello}
            return {'protocol': 2, 'session': 'a' * 16, 'seq': message.get('seq'), 'rev': message.get('rev'), 'status': 'Synced', 'applied': False}
        try:
            asyncio.run(page_delivery.Sender(send).synchronize('inbox', record, {}, values, [[] for _ in record['layout']['pages']]))
        except page_delivery.Refused:
            raise
        except page_delivery.DeliveryError:
            pass  # this fake screen never confirms the commit; what went out before it is what counts here
        return sent

    def test_a_screen_without_tile_repeats_is_refused_before_anything_is_sent(self):
        with self.assertRaisesRegex(page_delivery.Refused, '0.16.0'):
            self.sync({})

    def test_each_copy_gets_its_own_index_and_state(self):
        sent = self.sync({'tile_repeats': 1})
        tiles = [m for m in sent if m['op'] == 'tile']
        self.assertEqual([(m['i'], m['entity'], m['slot']) for m in tiles], [(0, 'light.a', 0), (1, 'light.b', 1), (2, 'light.a', 6)])
        self.assertEqual(tiles[2]['o'], {'inline': 'slider'})
        # Every copy has a value message of its own, by its index, so a change of the lamp reaches both.
        counter = itertools.count(1)
        record = migrate_legacy(deepcopy(LAMPS), Grid(), lambda: f'{next(counter):016x}')
        tiles = compile_tiles(record['layout'], Grid())
        values = [state_message(i, t, {}) for i, t in enumerate(tiles)]
        live = page_delivery.prepare('inbox', {**record, 'revision': 'r1'}, {}, values, [[] for _ in record['layout']['pages']])[3]
        self.assertEqual([(m['op'], m['i']) for m in live if m['entity'] == 'light.a'], [('state', 0), ('state', 2)])


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Through(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, firmware):
        ha = test_tile_events.fake_ha()
        ha.states['sensor.d1_fw']['state'] = firmware
        for entity in ('light.a', 'light.b'):
            ha.registry.append({'entity_id': entity, 'platform': 'demo', 'original_name': entity, 'device_id': 'd9'})
            ha.states[entity] = {'state': 'on', 'attributes': {'friendly_name': entity}}
        return Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')

    async def events(self, m, *events):
        for event, data in events:
            m.ha.tile_events.put_nowait((event, data))
        worker = asyncio.create_task(m.tile_loop())
        for _ in range(300):
            await asyncio.sleep(0.01)
            if len(m.ha.fired) == len(events):
                break
        worker.cancel()
        return [answer for _, answer in m.ha.fired]

    async def test_firmware_0_16_0_takes_a_second_tile_and_the_answer_says_where(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.16.0')
            m.save('text.d1_tiles', layout(tile('light.a', 0), tile('light.b', 1)))
            answers = await self.events(m, ('esp_screens_add_tile', {'entity': 'light.a', 'page': 2, 'name': 'Hall lamp'}),
                                        ('esp_screens_remove_tile', {'entity': 'light.a', 'page': 1}))
            self.assertEqual([(a['ok'], a['page'], a['slot']) for a in answers], [(True, 2, 6), (True, 1, 0)], answers)
            self.assertEqual(places(m.layouts['text.d1_tiles']), [('light.b', 1), ('light.a', 6)])
            self.assertEqual(m.layouts['text.d1_tiles']['tiles'][1]['name'], 'Hall lamp')

    async def test_older_firmware_moves_the_one_it_has_and_refuses_copies_from_the_editor(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.15.0')
            m.save('text.d1_tiles', layout(tile('light.a', 0), tile('light.b', 1)))
            answers = await self.events(m, ('esp_screens_add_tile', {'entity': 'light.a', 'page': 2}))
            self.assertEqual((answers[0]['ok'], answers[0]['slot']), (True, 6), answers)
            self.assertEqual(places(m.layouts['text.d1_tiles']), [('light.b', 1), ('light.a', 6)])
            with self.assertRaisesRegex(ValueError, 'Install screen firmware 0.16.0 or newer first'):
                m.save('text.d1_tiles', LAMPS)

    async def test_a_setting_one_copy_has_passes_on_another(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.16.0')
            m.save('text.d1_tiles', LAMPS)
            self.assertEqual([t.get('options') for t in m.layouts['text.d1_tiles']['tiles'] if t['entity'] == 'light.a'],
                             [None, {'inline': 'slider'}])
            await m.check_supported('text.d1_tiles', validate_layout(layout(tile('light.a', 0, inline='slider'), tile('light.a', 6, inline='slider'))))


if __name__ == '__main__':
    unittest.main()
