"""Cards from the top bar (firmware 0.56.0, core.BAR_CARDS_FEATURE): an entity's item in the top bar opens the card
holding its tile opens, and nothing else. Its tile is one on a page, or, for an entity on no tile, a tile of the top bar:
a tile without a cell that only a screen whose hello names the feature gets, after every other tile, as many as its tile
ceiling leaves room for. Each item names the tile whose card it opens (`d`). The saved layout does not change."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import header_bar  # noqa: E402
from core import BAR_CARDS_FEATURE, Grid, bar_cards, bar_entities, layout_cost  # noqa: E402
from layout_migrations import migrate_legacy  # noqa: E402
from page_delivery import Sender, Superseded, configuration, prepare, tile_message  # noqa: E402
from page_layout import compile_tiles  # noqa: E402
from page_service import top_bar_tiles  # noqa: E402
from test_page_delivery import Screen  # noqa: E402

REGION = {"clock_24h": True, "numbers": "english", "group_min": 1, "language": "en"}
MEMORY = {"room": 52048, "used": 1200, "psram": False, "tile": 524, "extra": 1056, "page": 336}


def item(entity):
    return {'type': 'entity', 'entity': entity, 'icon': 'auto', 'content': 'state', 'show': 'always'}


def record_with(bar):
    """A page with a lamp and a thermostat on tiles, and `bar` (entity ids) in its top bar."""
    record = migrate_legacy({"title": "Kitchen", "pages": 1, "tiles": [
        {"entity": "light.desk", "name": "", "slot": 0}, {"entity": "climate.hall", "name": "", "slot": 1}]}, Grid(2, 3))
    record['layout']['pages'][0]['topbar']['trailing'] = [{'id': f'{i:016x}', **item(e)} for i, e in enumerate(bar)]
    return record


def values(tiles):
    return [{"v": 1, "op": "state", "i": i, "entity": t['entity'], "name": t['entity'], "state": "on", "a": {},
             **({"o": t['options']} if t.get('options') else {})} for i, t in enumerate(tiles)]


class WhichEntities(unittest.TestCase):
    def test_an_entity_on_no_tile_once_and_only_a_type_with_a_card(self):
        record = record_with(['switch.coffee', 'light.desk', 'sensor.left', 'switch.coffee', 'zone.home', 'screen.clock'])
        tiles = compile_tiles(record['layout'], Grid(2, 3))
        # The lamp has its tile already; the switch comes once; a zone has no card on the screen; a built-in is no entity.
        self.assertEqual(bar_entities(record['layout']['pages'], tiles), ['switch.coffee', 'sensor.left'])

    def test_each_item_names_the_first_tile_of_its_entity(self):
        tiles = [{'entity': 'light.desk'}, {'entity': 'climate.hall'}, {'entity': 'light.desk'}, {'entity': 'switch.coffee', 'bar': True}]
        self.assertEqual(bar_cards(tiles), {'light.desk': 0, 'climate.hall': 1, 'switch.coffee': 3})
        wire, _ = header_bar.entity_item(item('switch.coffee'), {'switch.coffee': {'state': 'on', 'attributes': {}}}, card=3)
        self.assertEqual(wire['d'], 3)
        # Whatever the item shows: its icon alone (GitHub #252) and when it last changed open the card too.
        for content in ('icon', 'last_changed'):
            states = {'switch.coffee': {'state': 'on', 'attributes': {}, 'last_changed': '2026-10-14T08:00:00+00:00'}}
            wire, _ = header_bar.entity_item({**item('switch.coffee'), 'content': content}, states, card=3)
            self.assertEqual(wire['d'], 3, content)
        # Without a card (an older screen, the preview) the item is as it always was.
        wire, _ = header_bar.entity_item(item('switch.coffee'), {'switch.coffee': {'state': 'on', 'attributes': {}}})
        self.assertNotIn('d', wire)
        states = {'switch.coffee': {'state': 'on', 'attributes': {}}}
        bar = header_bar.message({'header': {'items': [item('switch.coffee')]}}, states, cards={'switch.coffee': 3})
        self.assertEqual(bar['items'][0]['d'], 3)


class OnlyToAScreenThatTakesThem(unittest.TestCase):
    def test_the_hello_decides_and_the_ceiling_bounds_them(self):
        record = record_with(['switch.coffee', 'sensor.left'])
        tiles = compile_tiles(record['layout'], Grid(2, 3))
        sender = type('S', (), {'max_tiles': None, 'last_max_tiles': None})()
        self.assertEqual(top_bar_tiles(record, tiles, sender, frozenset()), [])
        self.assertEqual(top_bar_tiles(record, tiles, sender, frozenset({BAR_CARDS_FEATURE})),
                         [{'entity': 'switch.coffee', 'name': '', 'bar': True}, {'entity': 'sensor.left', 'name': '', 'bar': True}])
        # A screen with room for one tile more gets one; one that is full gets none, and its items open nothing.
        sender.max_tiles = 3
        self.assertEqual([t['entity'] for t in top_bar_tiles(record, tiles, sender, frozenset({BAR_CARDS_FEATURE}))], ['switch.coffee'])
        sender.max_tiles = 2
        self.assertEqual(top_bar_tiles(record, tiles, sender, frozenset({BAR_CARDS_FEATURE})), [])

    def test_a_tile_of_the_top_bar_has_no_cell(self):
        message = tile_message({"v": 1, "op": "state", "i": 2, "entity": "switch.coffee", "name": "", "state": "on", "a": {}},
                               {'entity': 'switch.coffee', 'name': '', 'bar': True}, initial=True)
        self.assertEqual((message['op'], message['bar'], 'slot' in message, 'in' in message), ('tile', 1, False, False))

    def test_they_change_the_revision_and_follow_every_other_tile(self):
        record = record_with(['switch.coffee'])
        bar = [{'entity': 'switch.coffee', 'name': '', 'bar': True}]
        self.assertNotEqual(configuration(record, REGION, bar), configuration(record, REGION))
        self.assertEqual(configuration(record, REGION, []), configuration(record, REGION), 'nothing changes for a screen without them')
        tiles = compile_tiles(record['layout'], Grid(2, 3)) + bar
        begin, initial, _, _ = prepare('text.inbox', record, REGION, values(tiles), [[]], bar)
        self.assertEqual(begin['tiles'], 3)
        self.assertEqual([m.get('slot', 'bar' if m.get('bar') else None) for m in initial], [0, 1, 'bar'])


class Memory(unittest.TestCase):
    def test_they_count_on_a_screen_that_gets_them(self):
        record = record_with(['switch.coffee', 'light.desk'])
        tiles, pages = compile_tiles(record['layout'], Grid(2, 3)), record['layout']['pages']
        without, with_bar = layout_cost(tiles, MEMORY, pages), layout_cost(tiles, {**MEMORY, 'bar_cards': True}, pages)
        from core import tile_cost
        self.assertEqual(with_bar - without, tile_cost({'entity': 'switch.coffee'}, MEMORY))


class Delivery(unittest.IsolatedAsyncioTestCase):
    async def test_a_screen_that_names_them_gets_them_and_one_that_no_longer_does_gets_the_layout_without(self):
        peer = Screen()
        names = {'bar_cards'}
        async def screen(message):
            answer = await peer.send(message)
            if message['op'] == 'hello':
                answer.update(features=sorted(names), tile_keys=1)
            return answer
        sender = Sender(screen)
        record = record_with(['switch.coffee'])
        bar = [{'entity': 'switch.coffee', 'name': '', 'bar': True}]
        tiles = compile_tiles(record['layout'], Grid(2, 3)) + bar
        await sender.synchronize('text.inbox', record, REGION, values(tiles), [[{'k': 'text', 't': 'On', 'd': 2}]], bar=bar)
        self.assertEqual(peer.begin['tiles'], 3)
        self.assertEqual([m['entity'] for m in peer.initial if m.get('bar') == 1], ['switch.coffee'])
        self.assertEqual(sender.confirmed, configuration(record, REGION, bar))
        # Flashed back to a firmware without them: the next session's hello says so, and the round gives way to one without.
        names.clear()
        sender.session = None
        with self.assertRaises(Superseded):
            await sender.synchronize('text.inbox', record, REGION, values(tiles), [[]], bar=bar)
        tiles = tiles[:2]
        await sender.synchronize('text.inbox', record, REGION, values(tiles), [[]])
        self.assertEqual(peer.begin['tiles'], 2)
        self.assertFalse(any(m.get('bar') for m in peer.initial))


if __name__ == '__main__':
    unittest.main()
