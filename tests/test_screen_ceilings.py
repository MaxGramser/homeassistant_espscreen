"""A screen's own ceilings and memory (firmware 0.34.0+): a board with PSRAM takes more than 64 tiles over eight pages and
says so in its hello, with the memory its tiles may take; the add-on keeps to what each screen says, and to 64 and eight
for one that says nothing (docs/TILE_MEMORY.md)."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
import header_bar
from core import (BUILTIN, FIRMWARE_MAX_BAR_ITEMS, validate_header, FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES, Grid, STORE_MAX_PAGES, STORE_MAX_TILES,
                  layout_snapshot, page_target, validate_layout)
from layout_migrations import migrate_legacy
from page_capabilities import CapabilityCache
from page_delivery import Refused, Sender, bar_value_messages, ceiling_of, memory_of
from page_layout import grid_of_record, screen_grid_of_record, validate_document

REGION = {"clock_24h": True, "numbers": "english", "group_min": 1, "language": "en"}
MEMORY = {"room": 52048, "used": 1200, "psram": True, "tile": 524, "extra": 1056, "page": 336}


class Grids(unittest.TestCase):
    def test_a_grid_takes_the_ceilings_its_screen_states(self):
        self.assertEqual((FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES), (8, 64))
        self.assertEqual((Grid(2, 3).pages, Grid(2, 3).max_tiles), (8, 48))
        guition = Grid(2, 3, 24, 128)
        self.assertEqual((guition.pages, guition.max_slots, guition.max_tiles), (24, 144, 128))
        ten_inch = Grid(5, 5, 16, 256)
        self.assertEqual((ten_inch.pages, ten_inch.max_tiles), (16, 256))
        # The cells still decide where they take fewer: four by four over sixteen pages is 256 cells.
        self.assertEqual(Grid(2, 2, 24, 128).max_tiles, 96)
        # Equality is the cells only, so a new ceiling never asks for a layout to be adapted.
        self.assertEqual(Grid(2, 3, 24, 128), Grid(2, 3))
        # Nothing beyond what any board may state.
        self.assertEqual((Grid(2, 3, 99, 9999).pages, Grid(2, 3, 99, 9999).tile_cap), (STORE_MAX_PAGES, STORE_MAX_TILES))

    def test_older_firmware_keeps_its_own_numbers(self):
        grid = Grid(3, 3, 24, 128)
        self.assertEqual((grid.for_firmware((0, 34, 0)).pages, grid.for_firmware((0, 34, 0)).max_tiles), (24, 128))
        self.assertEqual((grid.for_firmware((0, 2, 70)).pages, grid.for_firmware((0, 2, 70)).max_tiles), (7, 63))

    def test_a_stored_layout_is_held_to_what_any_board_takes_and_a_save_to_its_screen(self):
        record = {"sourceGrid": {"columns": 2, "rows": 3}}
        self.assertEqual((grid_of_record(record).pages, grid_of_record(record).tile_cap), (STORE_MAX_PAGES, STORE_MAX_TILES))
        self.assertEqual((screen_grid_of_record(record).pages, screen_grid_of_record(record).max_tiles), (8, 48))

    def test_navigation_reaches_page_32(self):
        self.assertEqual([page_target('screen.page_9'), page_target('screen.page_24'), page_target('screen.page_32')], [9, 24, 32])
        self.assertNotIn('screen.page_33', BUILTIN)
        self.assertEqual(page_target('screen.page_33'), 0)

    def test_a_layout_of_more_than_64_tiles_and_eight_pages_validates_on_a_screen_that_takes_it(self):
        tiles = [{'entity': f'light.l{i}', 'name': f'L{i}', 'slot': i} for i in range(100)]
        tiles.append({'entity': 'screen.page_17', 'name': 'Seventeen', 'slot': 100})
        layout = {'title': 'Big', 'pages': 17, 'tiles': tiles}
        self.assertEqual(len(validate_layout(layout, grid=Grid(2, 3, 24, 128))['tiles']), 101)
        with self.assertRaises(ValueError):
            validate_layout(layout, grid=Grid(2, 3))
        record = migrate_legacy(layout, Grid(2, 3, 24, 128))
        self.assertEqual(len(record['layout']['pages']), 17)
        validate_document(record['layout'], Grid(2, 3, 24, 128))
        validate_document(record['layout'], grid_of_record(record))  # how the store loads it
        with self.assertRaises(Exception):
            validate_document(record['layout'], Grid(2, 3))


class Memory(unittest.TestCase):
    def test_the_figures_of_a_hello_are_checked(self):
        self.assertEqual(memory_of({"memory": {**MEMORY, "short": 1}})["short"], True)
        self.assertEqual(memory_of({"memory": MEMORY}), {**MEMORY, "short": False})
        for broken in ({"memory": {**MEMORY, "room": -1}}, {"memory": {**MEMORY, "tile": 0}}, {"memory": {**MEMORY, "used": "1"}},
                       {"memory": {**MEMORY, "psram": 1}}, {"memory": {k: v for k, v in MEMORY.items() if k != "extra"}},
                       {"memory": "lots"}, {}, None):
            self.assertIsNone(memory_of(broken))
        self.assertEqual([ceiling_of(128, 1024), ceiling_of(0, 1024), ceiling_of(2000, 1024), ceiling_of("8", 32)], [128, None, None, None])

    def test_a_screen_still_measuring_says_no_room_and_keeps_the_last_it_measured(self):
        # Firmware 0.51.0 samples its room only once a layout has settled and leaves `room` out before: still measuring,
        # not a room of nothing (GitHub #169).
        measuring = {"memory": {k: v for k, v in MEMORY.items() if k != "room"}}
        self.assertEqual(memory_of(measuring), {**MEMORY, "room": None, "short": False})
        self.assertIsNone(memory_of({"memory": {**MEMORY, "room": None}}))
        sender = Sender(lambda message: None)
        sender.heard({"memory": MEMORY})
        sender.heard(measuring)
        self.assertIsNone(sender.memory["room"])
        self.assertEqual(sender.last_memory["room"], MEMORY["room"])
        with tempfile.TemporaryDirectory() as folder:
            screen = {'device_id': 'd1', 'firmware_known': '0.51.0', 'node': 'wall', 'board': 'guition'}
            sender.protocol = 2
            CapabilityCache(Path(folder) / 'caps.json').remember('text.wall', screen, sender)
            later = Sender(lambda message: None)
            CapabilityCache(Path(folder) / 'caps.json').restore('text.wall', screen, later)
            self.assertEqual(later.last_memory["room"], MEMORY["room"])
        # Firmware without a budget still drops the figures.
        sender.heard({})
        self.assertEqual((sender.memory, sender.last_memory), (None, None))


    def test_a_big_layout_sensor_leaves_out_its_defaults_to_stay_recorded(self):
        def snapshot(count):
            tiles = [{'entity': f'light.living_room_ceiling_light_{i:03}', 'name': 'Living room ceiling ' + str(i), 'slot': i,
                      'options': {'size': 'single', 'controls': '', 'display': 'standard', 'tap': 'auto'}} for i in range(count)]
            return layout_snapshot({'name': 'Wall', 'node': 'wall'}, {'title': 'Wall', 'tiles': tiles}, Grid(2, 3, 24, 128))
        small, big = snapshot(20), snapshot(128)
        self.assertEqual(small['tiles'][0]['size'], 'single')
        self.assertNotIn('size', big['tiles'][0])
        self.assertEqual(big['max_tiles'], 128)
        size = len(json.dumps({'friendly_name': 'Wall tiles', 'icon': 'mdi:view-dashboard-outline', **big}, separators=(',', ':')).encode())
        self.assertLess(size, 16384, size)


class Hello(unittest.IsolatedAsyncioTestCase):
    async def test_a_screen_says_its_ceilings_and_memory_and_they_outlive_a_disconnect(self):
        async def screen(message):
            answer = {"protocol": 2, "request": message.get("request"), "session": "0" * 16, "status": "Session:" + "0" * 16,
                      "max_tiles": 128, "max_pages": 24, "memory": MEMORY}
            return answer
        sender = Sender(screen)
        await sender.probe()
        self.assertEqual((sender.max_tiles, sender.max_pages, sender.memory["room"]), (128, 24, 52048))
        sender.disconnected()
        self.assertEqual((sender.max_tiles, sender.max_pages, sender.memory), (None, None, None))
        self.assertEqual((sender.last_max_tiles, sender.last_max_pages, sender.last_memory["tile"]), (128, 24, 524))

    async def test_a_screen_that_says_nothing_keeps_64_and_eight(self):
        async def older(message):
            return {"protocol": 2, "request": message.get("request"), "session": "1" * 16, "status": "Session:" + "1" * 16}
        sender = Sender(older)
        await sender.probe()
        self.assertEqual((sender.max_tiles, sender.max_pages, sender.memory), (None, None, None))

    async def test_a_screen_flashed_back_to_an_older_release_loses_its_budget(self):
        # Bench 2026-10-03: a CYD flashed back to the release before kept the memory bar of the build it ran before.
        said = {"memory": MEMORY, "max_tiles": 128}
        async def screen(message):
            return {"protocol": 2, "request": message.get("request"), "session": "2" * 16, "status": "Session:" + "2" * 16, **said}
        sender = Sender(screen)
        await sender.probe()
        self.assertEqual(sender.last_memory["room"], 52048)
        said.clear()
        sender.disconnected()
        await sender.probe()
        self.assertEqual((sender.memory, sender.last_memory, sender.last_max_tiles), (None, None, None))

    async def test_more_tiles_than_the_screen_takes_are_refused_before_a_begin(self):
        from test_page_delivery import Screen
        peer = Screen()
        async def small(message):
            answer = await peer.send(message)
            if message['op'] == 'hello': answer.update(max_tiles=1, max_pages=8, free_pages=1)
            return answer
        record = migrate_legacy({"title": "T", "pages": 1, "tiles": [
            {"entity": "light.a", "name": "A", "slot": 0}, {"entity": "light.b", "name": "B", "slot": 1}]}, Grid(2, 3))
        values = [{"v": 1, "op": "state", "i": i, "entity": e, "name": e, "state": "on", "a": {}} for i, e in enumerate(("light.a", "light.b"))]
        sender = Sender(small)
        with self.assertRaisesRegex(Refused, '1 tile'):
            await sender.synchronize("text.test_inbox", record, REGION, values, [[{"k": "clock"}]])
        self.assertEqual([message['op'] for message in peer.messages], ['hello'])


class Cache(unittest.TestCase):
    def test_offline_editing_keeps_the_last_ceilings_and_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'caps.json'
            screen = {'device_id': 'd1', 'firmware_known': '0.34.0', 'node': 'wall', 'board': 'guition'}
            sender = Sender(lambda message: None)
            sender.protocol, sender.max_tiles, sender.max_pages, sender.memory = 2, 128, 24, memory_of({"memory": MEMORY})
            CapabilityCache(path).remember('text.wall', screen, sender)
            later = Sender(lambda message: None)
            CapabilityCache(path).restore('text.wall', screen, later)
            self.assertEqual((later.last_max_tiles, later.last_max_pages, later.last_memory['room']), (128, 24, 52048))
            # A newer firmware is another screen as far as the cache goes.
            fresh = Sender(lambda message: None)
            CapabilityCache(path).restore('text.wall', {**screen, 'firmware_known': '0.35.0'}, fresh)
            self.assertEqual((fresh.last_max_tiles, fresh.last_memory), (None, None))


class TopBar(unittest.TestCase):
    """A board with room for more states more top-bar items a page (firmware 0.34.0+, max_bar_items); six otherwise."""
    def test_a_grid_carries_the_items_a_bar_takes(self):
        self.assertEqual((Grid(2, 3).bar_items, Grid(2, 3, 24, 128, 12).bar_items), (6, 12))
        self.assertEqual(Grid(2, 3, 24, 128, 12).for_firmware((0, 2, 70)).bar_items, FIRMWARE_MAX_BAR_ITEMS)
        items = [{'type': 'entity', 'entity': f'sensor.s{n}'} for n in range(12)]
        self.assertEqual(len(validate_header({'items': items}, 12)['items']), 12)
        with self.assertRaises(ValueError):
            validate_header({'items': items})

    def test_a_value_names_the_items_it_was_numbered_by(self):
        bars, previous = [[{'k': 'text', 't': 'a'}] * 8, [{'k': 'text', 't': 'b'}] * 8], [[{'k': 'text', 't': 'x'}] * 8] * 2
        wide = bar_value_messages(bars, previous, 12)
        self.assertEqual([(m['w'], m['targets'][:2]) for m in wide], [(12, [0, 1]), (12, [12, 13])])
        narrow = bar_value_messages([[{'k': 'text', 't': 'a'}] * 2], [[{'k': 'text', 't': 'x'}] * 2])
        self.assertNotIn('w', narrow[0])
        self.assertEqual(narrow[0]['targets'], [0, 1])

    def test_an_item_can_show_its_icon_alone(self):
        clean = validate_header({'items': [{'type': 'entity', 'entity': 'light.a', 'content': 'icon'}]})['items'][0]
        wire, shown = header_bar.entity_item(clean, {'light.a': {'state': 'on', 'attributes': {}}})
        self.assertEqual(wire['t'], '')
        self.assertIn('i', wire)
        with self.assertRaises(ValueError):
            validate_header({'items': [{'type': 'entity', 'entity': 'light.a', 'content': 'icon', 'icon': 'none'}]})

    def test_a_document_of_twelve_items_validates_where_the_screen_takes_them(self):
        tiles = [{'entity': 'light.a', 'name': 'A', 'slot': 0}]
        record = migrate_legacy({'title': 'T', 'tiles': tiles}, Grid(2, 3))
        record['layout']['pages'][0]['topbar']['trailing'] = [{'id': f'{n:016x}', 'type': 'entity', 'entity': f'sensor.s{n}'} for n in range(12)]
        validate_document(record['layout'], Grid(2, 3, 24, 128, 12))
        validate_document(record['layout'], grid_of_record(record))
        with self.assertRaises(Exception):
            validate_document(record['layout'], Grid(2, 3))


class TopBarHello(unittest.IsolatedAsyncioTestCase):
    async def test_a_screen_says_the_items_its_bar_takes(self):
        async def screen(message):
            return {"protocol": 2, "request": message.get("request"), "session": "2" * 16, "status": "Session:" + "2" * 16, "max_bar_items": 12}
        sender = Sender(screen)
        await sender.probe()
        self.assertEqual(sender.max_bar_items, 12)
        sender.disconnected()
        self.assertEqual((sender.max_bar_items, sender.last_max_bar_items), (None, 12))


if __name__ == '__main__':
    unittest.main()
