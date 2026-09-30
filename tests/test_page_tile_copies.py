"""The same navigation tile on several pages (app 0.2.78, firmware 0.2.65): a "Back to page 1" on every page.

Every other entity is on a screen once. A layout with copies needs firmware 0.2.65, so an older screen gets the usual
"Install screen firmware" refusal. A tile event from Claude in Home Assistant names the copy it means by its spot or its
page (`from_slot`/`from_page` for a move) and acts on the first copy, in spot order, when it doesn't; the answer says
which tile it was, and the layout sensor lists every copy.
"""
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import (PAGE_TILE_REPEAT_MIN_FIRMWARE, TILE_RESULT_EVENT, apply_tile_event, layout_snapshot, min_firmware,  # noqa: E402
                  run_tile_event, validate_layout)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import test_tile_events
    from server import Manager

BACK = 'screen.page_1'


def tile(entity, slot, **options):
    item = {'entity': entity, 'name': '', 'slot': slot}
    if options:
        item['options'] = options
    return item


def layout(*tiles):
    return {'title': 'Hall', 'tiles': [dict(t) for t in tiles]}


def places(result):
    return [(t['entity'], t['slot']) for t in sorted(result['tiles'], key=lambda t: t['slot'])]


# A light on page 1, and the way back on pages 2 and 3.
MENU = layout(tile('light.a', 0), tile(BACK, 6, icon='home'), tile('light.b', 7), tile(BACK, 12))


class Layouts(unittest.TestCase):
    def test_copies_of_a_navigation_tile_need_firmware_0_2_65(self):
        result = validate_layout(MENU)
        self.assertEqual(places(result), [('light.a', 0), (BACK, 6), ('light.b', 7), (BACK, 12)])
        self.assertEqual(PAGE_TILE_REPEAT_MIN_FIRMWARE, (0, 2, 65))
        self.assertEqual(min_firmware(result), (0, 2, 65))
        self.assertEqual(min_firmware(validate_layout(layout(tile('light.a', 0), tile(BACK, 6)))), (0, 2, 62), 'one copy: as before')
        # Two on one page is odd but harmless, and what the editor allows too.
        validate_layout(layout(tile(BACK, 0), tile(BACK, 1)))
        # Any other entity on several tiles is firmware 0.16.0's (GitHub #83).
        for entity in ('light.a', 'screen.clock', 'screen.settings'):
            self.assertEqual(min_firmware(validate_layout(layout(tile(entity, 0), tile(entity, 6)))), (0, 16, 0), entity)

    def test_the_sensor_lists_every_copy(self):
        snapshot = layout_snapshot({'name': 'Hall', 'node': 'hall'}, validate_layout(MENU))
        self.assertEqual([(t['entity'], t['page'], t['slot'], t.get('to_page')) for t in snapshot['tiles']],
                         [('light.a', 1, 0, None), (BACK, 2, 6, 1), ('light.b', 2, 7, None), (BACK, 3, 12, 1)])


class Events(unittest.TestCase):
    def test_add_puts_a_copy_on_a_page_without_one_and_changes_the_one_that_is_there(self):
        result, placed = run_tile_event(MENU, 'add', {'entity': BACK, 'page': 4, 'name': 'Back'}, repeat_pages=True)
        self.assertEqual(places(result)[-1], (BACK, 18))
        self.assertEqual((placed['slot'], placed['name']), (18, 'Back'))
        # Named by the page it is on: that copy changes and stays where it is.
        result, changed = run_tile_event(MENU, 'add', {'entity': BACK, 'page': 3, 'color': 'blue'}, repeat_pages=True)
        self.assertEqual(places(result), places(MENU))
        self.assertEqual((changed['slot'], changed['options']), (12, {'background': 'blue'}))
        self.assertEqual(next(t for t in result['tiles'] if t['slot'] == 6)['options'], {'icon': 'home'}, 'the other copy is untouched')
        # Named by nothing: the first copy.
        result, changed = run_tile_event(MENU, 'add', {'entity': BACK, 'name': 'Home'}, repeat_pages=True)
        self.assertEqual((changed['slot'], len(result['tiles'])), (6, 4))

    def test_older_firmware_keeps_one_and_adding_it_again_moves_it(self):
        start = layout(tile('light.a', 0), tile(BACK, 6))
        result, moved = run_tile_event(start, 'add', {'entity': BACK, 'page': 3})
        self.assertEqual(places(result), [('light.a', 0), (BACK, 12)])
        self.assertEqual(moved['slot'], 12)
        self.assertEqual(places(apply_tile_event(start, 'add', {'entity': BACK, 'page': 3})), places(result), 'the old call is the same')

    def test_remove_takes_the_copy_named_or_the_first(self):
        self.assertEqual(places(apply_tile_event(MENU, 'remove', {'entity': BACK})), [('light.a', 0), ('light.b', 7), (BACK, 12)])
        self.assertEqual(places(apply_tile_event(MENU, 'remove', {'entity': BACK, 'page': 3})), [('light.a', 0), (BACK, 6), ('light.b', 7)])
        result, removed = run_tile_event(MENU, 'remove', {'entity': BACK, 'slot': 12})
        self.assertEqual((removed['slot'], len(result['tiles'])), (12, 3))
        self.assertEqual(places(apply_tile_event(MENU, 'remove', {'entity': BACK, 'from_slot': 12})), places(result))
        with self.assertRaisesRegex(ValueError, 'screen.page_1 is not on page 4'):
            apply_tile_event(MENU, 'remove', {'entity': BACK, 'page': 4})
        with self.assertRaisesRegex(ValueError, 'screen.page_1 is not on spot 7'):
            apply_tile_event(MENU, 'remove', {'entity': BACK, 'slot': 7})

    def test_move_takes_the_copy_named_by_from_page_or_from_slot_or_the_first(self):
        self.assertEqual(places(apply_tile_event(MENU, 'move', {'entity': BACK, 'page': 5})),
                         [('light.a', 0), ('light.b', 7), (BACK, 12), (BACK, 24)])
        self.assertEqual(places(apply_tile_event(MENU, 'move', {'entity': BACK, 'from_page': 3, 'page': 5})),
                         [('light.a', 0), (BACK, 6), ('light.b', 7), (BACK, 24)])
        result, moved = run_tile_event(MENU, 'move', {'entity': BACK, 'from_slot': 12, 'slot': 13})
        self.assertEqual((moved['slot'], places(result)[-1]), (13, (BACK, 13)))
        with self.assertRaisesRegex(ValueError, 'is not on page 1'):
            apply_tile_event(MENU, 'move', {'entity': BACK, 'from_page': 1, 'page': 5})
        with self.assertRaisesRegex(ValueError, 'page between 1 and 8'):
            apply_tile_event(MENU, 'move', {'entity': BACK, 'from_page': 9, 'page': 5})

    def test_order_takes_the_next_copy_each_time_it_is_named(self):
        # The whole screen: named once, the first copy leads and the other keeps its place in the order.
        self.assertEqual(places(apply_tile_event(MENU, 'order', {'entities': [BACK]})),
                         [(BACK, 0), ('light.a', 1), ('light.b', 2), (BACK, 3)])
        self.assertEqual(places(apply_tile_event(MENU, 'order', {'entities': [BACK, 'light.b', BACK]})),
                         [(BACK, 0), ('light.b', 1), (BACK, 2), ('light.a', 3)])
        with self.assertRaisesRegex(ValueError, 'Named more often than it is on this screen: screen.page_1'):
            apply_tile_event(MENU, 'order', {'entities': [BACK, BACK, BACK]})
        # One page: only the copy on that page.
        self.assertEqual(places(apply_tile_event(MENU, 'order', {'page': 2, 'entities': ['light.b', BACK]})),
                         [('light.a', 0), ('light.b', 6), (BACK, 7), (BACK, 12)])
        with self.assertRaisesRegex(ValueError, 'Named more often than it is on page 2'):
            apply_tile_event(MENU, 'order', {'page': 2, 'entities': [BACK, BACK]})
        self.assertIsNone(run_tile_event(MENU, 'order', {'entities': [BACK]})[1], 'an order acts on no single tile')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Through(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, firmware):
        ha = test_tile_events.fake_ha()
        ha.states['sensor.d1_fw']['state'] = firmware
        ha.registry.append({'entity_id': 'light.a', 'platform': 'demo', 'original_name': 'A', 'device_id': 'd9'})
        ha.states['light.a'] = {'state': 'on', 'attributes': {'friendly_name': 'A'}}
        return Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')

    async def events(self, m, *events):
        for data in events:
            m.ha.tile_events.put_nowait(('esp_screens_add_tile', data))
        worker = asyncio.create_task(m.tile_loop())
        for _ in range(300):
            await asyncio.sleep(0.01)
            if len(m.ha.fired) == len(events):
                break
        worker.cancel()
        return [answer for _, answer in m.ha.fired]

    async def test_firmware_0_2_65_takes_a_copy_on_every_page_and_the_answer_says_where(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.2.65')
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.a', 0), tile('light.reading', 6)]})
            answers = await self.events(m, {'entity': BACK, 'page': 2, 'name': 'Back'}, {'entity': BACK, 'page': 3, 'name': 'Back'})
            self.assertEqual([(a['ok'], a['page'], a['slot']) for a in answers], [(True, 2, 7), (True, 3, 12)], answers)
            self.assertEqual(answers[0]['event'], 'esp_screens_add_tile')
            saved = m.layouts['text.d1_tiles']['tiles']
            self.assertEqual([(t['entity'], t['slot']) for t in saved], [('light.a', 0), ('light.reading', 6), (BACK, 7), (BACK, 12)])
            _, attributes = m.ha.published['sensor.esp_screens_living_room']
            self.assertEqual([t['slot'] for t in attributes['tiles'] if t['entity'] == BACK], [7, 12])
            self.assertTrue(all(fired == TILE_RESULT_EVENT for fired, _ in m.ha.fired))

    async def test_older_firmware_moves_the_one_it_has_and_refuses_copies_from_the_editor(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.2.63')
            m.save('text.d1_tiles', {'title': 'Hall', 'tiles': [tile('light.a', 0), tile(BACK, 6)]})
            answers = await self.events(m, {'entity': BACK, 'page': 3})
            self.assertEqual((answers[0]['ok'], answers[0]['page'], answers[0]['slot']), (True, 3, 12), answers)
            self.assertEqual([t['slot'] for t in m.layouts['text.d1_tiles']['tiles'] if t['entity'] == BACK], [12])
            with self.assertRaisesRegex(ValueError, 'Install screen firmware 0.2.65 or newer first'):
                m.save('text.d1_tiles', MENU)

    async def test_each_copy_keeps_its_own_settings_when_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, '0.2.65')
            m.ha.registry.append({'entity_id': 'light.b', 'platform': 'demo', 'original_name': 'B', 'device_id': 'd9'})
            m.ha.states['light.b'] = {'state': 'on', 'attributes': {'friendly_name': 'B'}}
            m.save('text.d1_tiles', layout(tile('light.a', 0), tile(BACK, 6), tile('light.b', 7), tile(BACK, 12, icon='home')))
            # Both copies sent without options keep none: a page from before an option existed gets its old options back,
            # but such a page never sends copies, and one copy must never take another's icon.
            m.save('text.d1_tiles', layout(tile('light.a', 0), tile(BACK, 6), tile('light.b', 7), tile(BACK, 12)))
            self.assertEqual([t.get('options') for t in m.layouts['text.d1_tiles']['tiles'] if t['entity'] == BACK], [None, None])
            m.save('text.d1_tiles', MENU)
            self.assertEqual([t.get('options') for t in m.layouts['text.d1_tiles']['tiles'] if t['entity'] == BACK], [{'icon': 'home'}, None])
            m.ha.messages = []

            async def send(inbox, message, action=None, respond=False):
                m.ha.messages.append(message)
            m.ha.send = send
            await m.sync_one('text.d1_tiles', m.layouts['text.d1_tiles'])
            self.assertEqual(m.ha.messages[0]['entities'], ['light.a', BACK, 'light.b', BACK])
            self.assertEqual(m.ha.messages[0]['slots'], [0, 6, 7, 12])
            self.assertEqual([msg['i'] for msg in m.ha.messages if msg['op'] == 'state' and msg['entity'] == BACK], [1, 3])


if __name__ == '__main__':
    unittest.main()
