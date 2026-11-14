"""The to-do card's items (screen_manager/app/todo_feed.py, docs/TODO.md): the order, what the screen may do, the
numbers that stand for Home Assistant's uids, what a screen's request becomes, and the subscriptions."""
import asyncio
import json
import sys
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import page_delivery  # noqa: E402
import todo_feed  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ALL = todo_feed.CREATE | todo_feed.DELETE | todo_feed.UPDATE


def item(uid, summary, done=False, due=None, completed=None):
    return {'uid': uid, 'summary': summary, 'status': 'completed' if done else 'needs_action', 'due': due,
            'description': None, 'completed': completed}


LIST = [item('a', 'Oat milk'), item('b', 'bananas'), item('c', 'Butter', True, completed='2026-11-09T10:00:00+00:00'),
        item('d', 'Call the plumber', due='2026-11-10'), item('e', 'Renew passport', due='2026-11-06'),
        item('f', 'Apples', True, completed='2026-11-10T08:00:00+00:00')]
TILE = {'entity': 'todo.shopping'}


def numbers(items):
    return todo_feed.Numbers().update('todo.shopping', items)


class Card(unittest.TestCase):
    def card(self, options=None, items=LIST, features=ALL, most=todo_feed.KEEPS):
        tile = {**TILE, 'options': options or {}}
        return todo_feed.card(tile, items, numbers(items), features, UTC, NOW, most)

    def test_open_first_then_done_in_home_assistants_order(self):
        card = self.card()
        self.assertEqual([row[2] for row in card['i']], ['Oat milk', 'bananas', 'Call the plumber', 'Renew passport', 'Butter', 'Apples'])
        self.assertEqual((card['n'], card['d']), (4, 2))

    def test_alphabetical_ignores_case(self):
        names = [row[2] for row in self.card({'todo_order': 'alpha_asc'})['i']]
        self.assertEqual(names, ['bananas', 'Call the plumber', 'Oat milk', 'Renew passport', 'Apples', 'Butter'])

    def test_by_due_date_puts_the_undated_last_going_up_and_first_going_down(self):
        up = [row[2] for row in self.card({'todo_order': 'duedate_asc'})['i'][:4]]
        down = [row[2] for row in self.card({'todo_order': 'duedate_desc'})['i'][:4]]
        self.assertEqual(up, ['Renew passport', 'Call the plumber', 'Oat milk', 'bananas'])
        self.assertEqual(down[2:], ['Call the plumber', 'Renew passport'])

    def test_a_due_date_travels_as_days_from_today_and_late_as_a_flag(self):
        rows = {row[2]: row for row in self.card()['i']}
        self.assertEqual(rows['Call the plumber'][3], 0)
        self.assertFalse(rows['Call the plumber'][1] & todo_feed.LATE)   # a day without a time is due until it ends
        self.assertEqual(rows['Renew passport'][3], -4)
        self.assertTrue(rows['Renew passport'][1] & todo_feed.LATE)
        self.assertEqual(len(rows['Oat milk']), 3)

    def test_a_time_that_has_passed_today_is_late(self):
        rows = self.card(items=[item('a', 'Call', due='2026-11-10T09:00:00+00:00')])['i']
        self.assertEqual(rows[0][3], 0)
        self.assertTrue(rows[0][1] & todo_feed.LATE)

    def test_the_tiles_choices(self):
        self.assertEqual(len(self.card({'todo_completed': False})['i']), 4)
        self.assertEqual(self.card({'todo_completed': False})['d'], 2)   # still counted
        self.assertTrue(all(len(row) == 3 for row in self.card({'todo_due': False})['i']))
        self.assertFalse(self.card({'todo_add': False})['f'] & todo_feed.MAY_ADD)
        self.assertNotIn('s', self.card({'todo_add': False}))
        self.assertNotIn('s', self.card({'todo_suggest': False}))
        self.assertFalse(self.card({'todo_clear': False})['f'] & todo_feed.MAY_CLEAR)

    def test_what_the_screen_may_do_follows_the_lists_features(self):
        self.assertEqual(self.card(features=0)['f'], 0)
        self.assertEqual(self.card(features=todo_feed.CREATE)['f'], todo_feed.MAY_ADD)
        self.assertEqual(self.card(features=todo_feed.UPDATE)['f'], todo_feed.MAY_TICK | todo_feed.MAY_RENAME)
        self.assertEqual(self.card(features=todo_feed.DELETE)['f'], todo_feed.MAY_REMOVE | todo_feed.MAY_CLEAR)

    def test_suggestions_are_what_was_done_last_first(self):
        self.assertEqual(self.card()['s'], ['Apples', 'Butter'])
        again = LIST + [item('g', 'butter')]   # open again under the same name: no longer offered
        self.assertEqual(self.card(items=again)['s'], ['Apples'])

    def test_a_long_list_is_cut_and_still_counted(self):
        many = [item(str(n), f'Item {n} ' + 'x' * 70) for n in range(200)]
        card = self.card(items=many, most=todo_feed.KEEPS_MAX)
        self.assertEqual(card['n'], 200)
        self.assertLess(len(card['i']), 200)
        self.assertLessEqual(len(json.dumps(card, separators=(',', ':'), ensure_ascii=False).encode()), todo_feed.BUDGET)
        self.assertTrue(all(len(row[2].encode()) <= todo_feed.SUMMARY_BYTES for row in card['i']))
        self.assertEqual(len(self.card(items=many, most=10)['i']), 10)

    def test_a_list_not_known_yet_says_so(self):
        self.assertEqual(self.card(items=None), {'v': 1, 'w': 1})

    def test_the_card_leaves_room_for_the_rest_of_the_message(self):
        self.assertLessEqual(todo_feed.BUDGET + 512, page_delivery.MAX_MESSAGE)


class Boards(unittest.TestCase):
    def test_only_a_screen_with_the_card_takes_a_layout_with_a_list(self):
        tiles = [{'entity': 'light.desk'}, {'entity': 'todo.shopping'}]
        self.assertTrue(todo_feed.unsupported(tiles, frozenset({'text_card'})))
        self.assertTrue(todo_feed.unsupported(tiles, None))
        self.assertFalse(todo_feed.unsupported(tiles, frozenset({todo_feed.FEATURE})))
        self.assertFalse(todo_feed.unsupported([{'entity': 'light.desk'}], frozenset()))

    def test_the_boards_with_4_mb_lack_the_module_and_every_other_board_has_it(self):
        boards = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        lite = {key for key, board in boards.items() if todo_feed.MODULE not in board.get('modules', [])}
        self.assertEqual({key for key in lite if '/' not in key}, {'cyd', 'cyd9342', 'hosyond40'})
        self.assertTrue(all(boards[key].get('tier') == 'lite' for key in lite))


class Numbers(unittest.TestCase):
    def test_an_item_keeps_its_number_and_a_number_is_never_given_twice(self):
        book = todo_feed.Numbers()
        first = book.update('todo.a', [item('x', 'One'), item('y', 'Two')])
        second = book.update('todo.a', [item('y', 'Two'), item('z', 'Three')])
        self.assertEqual(first['y'], second['y'])
        self.assertNotIn(second['z'], first.values())
        self.assertIsNone(book.uid('todo.a', first['x']))
        self.assertEqual(book.uid('todo.a', second['z']), 'z')
        self.assertIsNone(book.uid('todo.b', second['z']))


class Request(unittest.TestCase):
    def test_ticking_and_unticking(self):
        self.assertEqual(todo_feed.request('tick', LIST, 'a', None, ALL), ('update_item', {'item': 'a', 'status': 'completed'}))
        self.assertEqual(todo_feed.request('untick', LIST, 'c', None, ALL), ('update_item', {'item': 'c', 'status': 'needs_action'}))
        self.assertIsNone(todo_feed.request('tick', LIST, None, None, ALL))
        self.assertIsNone(todo_feed.request('tick', LIST, 'a', None, todo_feed.CREATE))

    def test_adding(self):
        self.assertEqual(todo_feed.request('add', LIST, None, '  Coffee   beans ', ALL), ('add_item', {'item': 'Coffee beans'}))
        self.assertIsNone(todo_feed.request('add', LIST, None, '   ', ALL))
        self.assertIsNone(todo_feed.request('add', LIST, None, 'Tea', todo_feed.UPDATE))

    def test_adding_what_is_done_brings_it_back_and_what_is_open_does_nothing(self):
        self.assertEqual(todo_feed.request('add', LIST, None, 'butter', ALL), ('update_item', {'item': 'c', 'status': 'needs_action'}))
        self.assertIsNone(todo_feed.request('add', LIST, None, 'OAT MILK', ALL))
        # A list that cannot change an item gets a second one.
        self.assertEqual(todo_feed.request('add', LIST, None, 'butter', todo_feed.CREATE), ('add_item', {'item': 'butter'}))

    def test_renaming_removing_and_clearing(self):
        self.assertEqual(todo_feed.request('rename', LIST, 'a', 'Soy milk', ALL), ('update_item', {'item': 'a', 'rename': 'Soy milk'}))
        self.assertIsNone(todo_feed.request('rename', LIST, 'a', '', ALL))
        self.assertEqual(todo_feed.request('remove', LIST, 'a', None, ALL), ('remove_item', {'item': 'a'}))
        self.assertEqual(todo_feed.request('clear', LIST, None, None, ALL), ('remove_completed_items', {}))
        self.assertIsNone(todo_feed.request('clear', LIST[:2], None, None, ALL))
        self.assertIsNone(todo_feed.request('explode', LIST, 'a', None, ALL))


class Validate(unittest.TestCase):
    def test_defaults_are_dropped_and_wrong_values_refused(self):
        self.assertEqual(todo_feed.validate({'todo_order': 'none', 'todo_completed': True, 'tap': 'detail'}), {'tap': 'detail'})
        self.assertEqual(todo_feed.validate({'todo_order': 'alpha_asc', 'todo_add': False}), {'todo_order': 'alpha_asc', 'todo_add': False})
        for wrong in ({'todo_order': 'random'}, {'todo_due': 'yes'}, {'todo_clear': 1}):
            with self.assertRaises(ValueError):
                todo_feed.validate(wrong)


class FakeHa:
    def __init__(self):
        self.online, self.connection, self.dirty, self.changed = True, 1, set(), asyncio.Event()
        self.subs, self.ended, self.next = {}, [], 10
        self.missing = set()

    async def subscribe_todo(self, entity, callback):
        if entity in self.missing:
            error = ConnectionError('no such list')
            error.detail = 'Entity not found'
            raise error
        self.next += 1
        self.subs[self.next] = (entity, callback)
        return self.next

    async def unsubscribe_todo(self, key):
        self.ended.append(self.subs.pop(key)[0])


class Service(unittest.IsolatedAsyncioTestCase):
    async def test_a_list_is_subscribed_once_and_ended_when_no_screen_shows_it(self):
        ha = FakeHa()
        service = todo_feed.TodoService(ha)
        await service.sync({'todo.a', 'todo.b'})
        await service.sync({'todo.a', 'todo.b'})
        self.assertEqual(sorted(entity for entity, _ in ha.subs.values()), ['todo.a', 'todo.b'])
        await service.sync({'todo.a'})
        self.assertEqual(ha.ended, ['todo.b'])

    async def test_a_new_list_marks_its_tiles_and_the_same_list_does_not(self):
        ha = FakeHa()
        service = todo_feed.TodoService(ha)
        await service.sync({'todo.a'})
        callback = next(iter(ha.subs.values()))[1]
        self.assertIsNone(service.of('todo.a'))
        callback({'items': LIST})
        self.assertEqual(ha.dirty, {'todo.a'})
        self.assertTrue(ha.changed.is_set())
        self.assertEqual(len(service.numbers.of('todo.a')), len(LIST))
        ha.dirty.clear()
        callback({'items': list(LIST)})
        self.assertEqual(ha.dirty, set())
        callback({'items': LIST[:2]})
        self.assertEqual(ha.dirty, {'todo.a'})

    async def test_a_new_connection_subscribes_again_and_keeps_the_items_meanwhile(self):
        ha = FakeHa()
        service = todo_feed.TodoService(ha)
        await service.sync({'todo.a'})
        next(iter(ha.subs.values()))[1]({'items': LIST})
        ha.connection, ha.subs = 2, {}
        await service.sync({'todo.a'})
        self.assertEqual([entity for entity, _ in ha.subs.values()], ['todo.a'])
        self.assertEqual(ha.ended, [])
        self.assertEqual(service.of('todo.a'), LIST)

    async def test_a_list_home_assistant_does_not_have_is_not_asked_again_each_pass(self):
        ha = FakeHa()
        ha.missing = {'todo.gone'}
        service = todo_feed.TodoService(ha)
        await service.sync({'todo.gone', 'todo.a'})
        await service.sync({'todo.gone', 'todo.a'})
        self.assertEqual([entity for entity, _ in ha.subs.values()], ['todo.a'])

    def test_the_lists_of_the_screens(self):
        tiles = [[{'entity': 'todo.a'}, {'entity': 'light.x'}], [{'entity': 'todo.b'}, {'entity': 'todo.a'}], None]
        self.assertEqual(todo_feed.wanted_lists(tiles), {'todo.a', 'todo.b'})


class Manager(unittest.IsolatedAsyncioTestCase):
    """The app around the feed (server.Manager): a tile's `x.todo`, and a screen's request turned into Home Assistant's
    action, only where the tile's choices and the list's features allow it."""

    async def asyncSetUp(self):
        import tempfile
        sys.path.insert(0, str(ROOT / 'tests'))
        import test_scaling
        from manager_fixtures import with_screen_grid
        from server import Manager as AppManager
        self.ha = test_scaling.fake_ha(firmware='0.61.0')
        self.ha.states['todo.shopping'] = {'state': '4', 'attributes': {'friendly_name': 'Shopping', 'supported_features': ALL}}
        self.calls = []

        async def request(kind, **data):
            self.calls.append((kind, data))
            return {}
        self.ha.request = request
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.manager = AppManager(with_screen_grid(self.ha), Path(self.folder.name) / 'screens.json')
        self.manager.todos.received('todo.shopping', {'items': LIST})

    async def test_a_tile_carries_its_list_and_a_screen_without_the_module_gets_none(self):
        tile = {'entity': 'todo.shopping', 'name': '', 'options': {}}
        with_list = await self.manager.tile_message(0, tile, features=frozenset({todo_feed.FEATURE}))
        self.assertEqual(with_list['x']['todo']['n'], 4)
        self.assertEqual(len(with_list['x']['todo']['i']), 6)
        without = await self.manager.tile_message(0, tile, features=frozenset())
        self.assertNotIn('todo', without.get('x') or {})
        self.assertLessEqual(len(json.dumps(with_list, separators=(',', ':'), ensure_ascii=False).encode()), page_delivery.MAX_MESSAGE)

    async def ask(self, options=None, **request):
        inbox = 'text.screen_inbox'
        layouts = {inbox: {'tiles': [{'entity': 'todo.shopping', 'name': '', 'options': options or {}}]}}
        self.manager.screen = lambda _inbox: {'online': True}
        self.calls.clear()
        with mock.patch.object(type(self.manager), 'layouts', new_callable=mock.PropertyMock, return_value=layouts):
            await self.manager.answer_todo({'inbox': inbox, 'entity': 'todo.shopping', 'i': '0', **request})
        return list(self.calls)

    async def test_a_request_becomes_home_assistants_action(self):
        number = self.manager.todos.numbers.of('todo.shopping')['a']
        calls = await self.ask(a='tick', n=str(number))
        self.assertEqual(calls, [('call_service', {'domain': 'todo', 'service': 'update_item',
                                                   'service_data': {'item': 'a', 'status': 'completed'},
                                                   'target': {'entity_id': 'todo.shopping'}})])
        calls = await self.ask(a='add', n='0', t='Coffee')
        self.assertEqual(calls[0][1]['service'], 'add_item')

    async def test_what_the_tile_does_not_offer_is_not_done(self):
        self.assertEqual(await self.ask({'todo_add': False}, a='add', n='0', t='Coffee'), [])
        self.assertEqual(await self.ask({'todo_clear': False}, a='clear', n='0'), [])
        self.assertEqual(await self.ask(a='tick', n='999999'), [])        # a number of no item
        self.assertEqual(await self.ask(a='format', n='0'), [])
        self.ha.states['todo.shopping']['attributes']['supported_features'] = 0
        number = self.manager.todos.numbers.of('todo.shopping')['a']
        self.assertEqual(await self.ask(a='tick', n=str(number)), [])


if __name__ == '__main__':
    unittest.main()
