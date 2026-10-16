import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "screen_manager/app"))
from core import Grid
from layout_migrations import migrate_legacy
import tile_icons
from page_delivery import Sender, DeliveryError, Refused, Superseded, configuration, bar_value_messages, grids_of, page_message


class Screen:
    """A wire-level test peer; physical/host-render tests cover the real parser."""
    def __init__(self):
        self.messages = []
        self.session = 0
        self.revision = "0" * 16
        self.active = False
        self.initial = []
        self.pages = []
        self.sequence = 0
        self.failure = None
        self.delayed = None

    async def send(self, message):
        self.messages.append(deepcopy(message))
        await asyncio.sleep(0)
        op = message["op"]
        if self.failure == op:
            self.failure = None
            raise TimeoutError("simulated lost connection")
        if self.delayed:
            answer, self.delayed = self.delayed, None
            return answer
        if op == "hello":
            self.session += 1
            self.sequence = 0
            return {"protocol": 2, "session": f"{self.session:016x}", "request": message["request"],
                    "status": f"Session:{self.session:016x}"}
        assert message["session"] == f"{self.session:016x}"
        assert message["seq"] > self.sequence
        self.sequence = message["seq"]
        if op == "begin":
            if not self.active or self.revision != message["rev"]:
                self.active = False
                self.initial, self.pages = [], []
            self.begin = message
            self.revision = message["rev"]
        if op == 'appearance':
            assert self.active and message['base'] == self.revision
            self.revision = message['rev']
        assert message["rev"] == self.revision
        if op == "tile":
            assert not self.active
            self.initial.append(message)
        elif op == "page":
            assert not self.active
            self.pages.append(message)
        elif op == "commit":
            assert len(self.initial) == self.begin["tiles"] and len(self.pages) == self.begin["pages"]
            self.active = True
        elif op == "state":
            assert self.active and "o" not in message and "slot" not in message
        return {"protocol": 2, "session": message["session"], "seq": self.sequence, "rev": self.revision,
                "applied": self.active, "status": "Synced" if self.active else "Loading tiles"}


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def enable_appearance_updates(self):
        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer['appearance_updates'] = 1
            return answer
        self.sender = Sender(newer)
        await self.sync()
        self.screen.messages.clear()

    async def test_cosmetic_save_uses_negotiated_atomic_edit_without_begin(self):
        await self.enable_appearance_updates()
        previous = self.sender.confirmed
        self.record['layout']['title'] = 'New title'
        self.record['layout']['pages'][0]['topbar']['title'] = {'source': 'text', 'text': 'Room'}
        self.record['layout']['pages'][0]['tiles'][0]['appearance'].update(label='New desk', background='blue')
        self.values[0]['name'] = 'New desk'
        await self.sync()
        ops = [m['op'] for m in self.screen.messages]
        self.assertEqual(ops, ['appearance', 'state'])
        edit = self.screen.messages[0]
        self.assertEqual(edit['base'], previous)
        self.assertEqual(edit['tiles'], [{'i': 0, 'name': 'New desk', 'background': 'blue'}])
        self.assertEqual(edit['pages'], [{'p': 0, 'title': 'Room'}])
        self.assertEqual(self.sender.confirmed, self.screen.revision)
        self.assertNotEqual(self.sender.confirmed, previous)
        self.assertTrue(await self.sender.ping())

    async def test_unnegotiated_cosmetic_save_and_structural_edits_keep_full_transaction(self):
        await self.sync()
        self.screen.messages.clear()
        self.record['layout']['title'] = 'Old peer'
        await self.sync()
        self.assertIn('begin', [m['op'] for m in self.screen.messages])
        await self.enable_appearance_updates()
        self.record['layout']['pages'][0]['navigation']['excludeFromPagination'] = True
        await self.sync()
        self.assertIn('begin', [m['op'] for m in self.screen.messages])
        self.assertNotIn('appearance', [m['op'] for m in self.screen.messages])

    async def test_interrupted_cosmetic_save_recovers_the_saved_document(self):
        await self.enable_appearance_updates()
        self.record['layout']['title'] = 'Retry title'
        self.screen.failure = 'appearance'
        with self.assertRaises(TimeoutError): await self.sync()
        await self.sync()
        self.assertEqual(self.sender.confirmed, configuration(self.record, self.region))
        self.assertTrue(self.screen.active)

    def test_cosmetic_tile_indexes_follow_wire_placement_order(self):
        from page_delivery import appearance_configuration
        doc = deepcopy(self.record)
        tile = doc['layout']['pages'][0]['tiles'][0]
        other = deepcopy(tile)
        other['placement']['column'] = 1
        other['appearance']['background'] = 'red'
        tile['appearance']['background'] = 'blue'
        doc['layout']['pages'][0]['tiles'] = [other, tile]
        _, paint = appearance_configuration(doc, self.region, [{'name': 'First'}, {'name': 'Second'}, {'name': 'Home'}])
        self.assertEqual([t['background'] for t in paint['tiles']][:2], ['blue', 'red'])

    async def test_large_cosmetic_batch_falls_back_before_sending_a_patch(self):
        from core import state_message
        from page_layout import compile_tiles
        grid = Grid(2, 4)
        self.record = migrate_legacy({'title': 'Many', 'tiles': [
            {'entity': f'light.test_{i}', 'name': 'Before', 'slot': i} for i in range(64)]}, grid)
        self.values = [state_message(i, tile, {}) for i, tile in enumerate(compile_tiles(self.record['layout'], grid))]
        self.bars = [[] for _ in self.record['layout']['pages']]
        await self.enable_appearance_updates()
        for page in self.record['layout']['pages']:
            for tile in page['tiles']: tile['appearance']['label'] = 'é' * 40
        self.values = [state_message(i, tile, {}) for i, tile in enumerate(compile_tiles(self.record['layout'], grid))]
        await self.sync()
        ops = [message['op'] for message in self.screen.messages]
        self.assertIn('begin', ops)
        self.assertNotIn('appearance', ops)

    async def test_shared_bar_values_use_one_negotiated_packet(self):
        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer['bar_values'] = 1
            return answer
        self.sender = Sender(newer)
        self.bars = [[{'k': 'text', 't': '21 °C'}] for _ in self.bars]
        await self.sync()
        self.screen.messages.clear()
        for bar in self.bars: bar[0]['t'] = '22 °C'
        await self.sync()
        self.assertEqual(len(self.screen.messages), 1)
        message = self.screen.messages[0]
        self.assertEqual(message['op'], 'bar_value')
        self.assertEqual(message['targets'], [0, 6])
        self.assertEqual(message['item']['t'], '22 °C')
        self.screen.messages.clear()
        await self.sync()
        self.assertEqual(self.screen.messages, [])
        self.sender.disconnected()
        self.assertFalse(self.sender.bar_values)

    def test_eight_bars_group_identical_values_but_keep_format_choices(self):
        before = [[{'k': 'text', 't': '21 °C'}, {'k': 'text', 't': '21'}] for _ in range(8)]
        after = [[{'k': 'text', 't': '22 °C'}, {'k': 'text', 't': '22'}] for _ in range(8)]
        messages = list(bar_value_messages(after, before))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['targets'], list(range(0, 48, 6)))
        self.assertEqual(messages[1]['targets'], list(range(1, 48, 6)))

    def test_conditional_visibility_replaces_the_bar_when_item_count_changes(self):
        value = {'k': 'text', 't': 'Motion'}
        self.assertEqual(list(bar_value_messages([[]], [[value]])), [{'op': 'bar', 'p': 0, 'items': []}])
        self.assertEqual(list(bar_value_messages([[value]], [[]])), [{'op': 'bar', 'p': 0, 'items': [value]}])

    async def test_disconnect_keeps_capabilities_for_offline_editing_only(self):
        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer['tile_sizes'] = ['single', 'wide', 'full', 'tall', 'square']
            return answer
        sender = Sender(newer)
        await sender.probe()
        sender.disconnected()
        self.assertIsNone(sender.protocol)
        self.assertIsNone(sender.session)
        self.assertEqual(sender.last_protocol, 2)
        self.assertIn('square', sender.last_tile_sizes)

    async def test_taller_tiles_are_refused_before_replacing_an_older_screen(self):
        tile = self.record['layout']['pages'][0]['tiles'][0]
        tile['placement']['rows'] = 2
        tile['appearance']['presentation'] = 'square'
        self.values[0]['o']['size'] = 'square'
        with self.assertRaisesRegex(Refused, 'these tile sizes'):
            await self.sync()
        self.assertEqual([message['op'] for message in self.screen.messages], ['hello'])

        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer['tile_sizes'] = ['single', 'wide', 'full', 'tall', 'square']
            return answer
        self.sender = Sender(newer)
        await self.sync()
        self.assertEqual(self.screen.initial[0]['o']['size'], 'square')
        self.assertTrue(self.screen.active)
        self.sender.disconnected()
        self.assertNotIn('square', self.sender.tile_sizes)

    async def test_more_pages_than_older_firmware_takes_wait_for_its_update(self):
        # A 5 x 4 page on firmware before 0.18.0 had three pages (64 / 20); four go only to a screen whose hello says
        # it takes eight on every grid (`free_pages`), and nothing replaces the layout on an older one.
        self.record = migrate_legacy({"title": "Wall", "pages": 4, "tiles": [
            {"entity": "light.test", "name": "Desk", "slot": 61}]}, Grid(5, 4))
        self.values = [{"v": 1, "op": "state", "i": 0, "entity": "light.test", "name": "Desk", "state": "on", "a": {}}]
        self.bars = [[{"k": "clock"}]] * 4
        with self.assertRaisesRegex(Refused, '0.18.0'):
            await self.sync()
        self.assertEqual([message['op'] for message in self.screen.messages], ['hello'])

        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer['free_pages'] = 1
            return answer
        self.sender = Sender(newer)
        await self.sync()
        self.assertEqual(self.screen.begin['pages'], 4)
        self.assertTrue(self.screen.active)
        self.sender.disconnected()
        self.assertFalse(self.sender.free_pages)

    async def test_the_hello_says_what_else_it_takes_as_a_list_and_nothing_else_counts(self):
        # Firmware 0.19.0 lists what it takes beyond the older flags (`features`); a value that happens to be 1 (applied is
        # true, page 1, home 1) is no flag of it, or every change of it would send every tile again.
        async def newer(message):
            answer = await self.screen.send(message)
            if message['op'] == 'hello': answer.update(features=['climate_range', 7], applied=True, page=1, home=1)
            return answer
        self.sender = Sender(newer)
        await self.sync()
        self.assertEqual(self.sender.features, {'climate_range'})
        self.sender.disconnected()
        self.assertEqual(self.sender.features, set())

    def setUp(self):
        self.record = migrate_legacy({"title": "Test", "pages": 2, "tiles": [
            {"entity": "light.test", "name": "Desk", "slot": 0, "options": {"size": "wide"}},
            {"entity": "screen.page_1", "name": "Home", "slot": 6}]}, Grid(2, 3))
        self.values = [
            {"v": 1, "op": "state", "i": 0, "entity": "light.test", "name": "Desk", "state": "on",
             "a": {"brightness": 200}, "o": {"size": "wide", "tap": "toggle", "inline": "brightness"}},
            {"v": 1, "op": "state", "i": 1, "entity": "screen.page_1", "name": "Home", "state": "on", "a": {}}]
        self.bars = [[{"k": "clock"}], [{"k": "text", "t": "21 °C"}]]
        self.region = {"clock_24h": True, "numbers": "english", "group_min": 1,
                       "percent_space": False, "keepalive": 120}
        self.screen = Screen()
        self.sender = Sender(self.screen.send)

    async def sync(self, alive=lambda: True):
        return await self.sender.synchronize("text.test_inbox", self.record, self.region, self.values, self.bars, alive)

    GRIDS = {'upright': False, 'landscape': {'columns': 2, 'rows': 3, 'min': [1, 1], 'max': [3, 5]},
             'portrait': {'columns': 1, 'rows': 4, 'min': [1, 1], 'max': [2, 6]}}

    async def test_a_screen_that_takes_another_grid_gets_the_layouts_grid_with_begin(self):
        # Firmware 0.53.0+: the grid the layout is counted on goes with begin, so the screen changes to it before the
        # tiles come; a grid the way its glass hangs does not take is refused before anything but the hello.
        async def newer(message):
            answer = await self.screen.send(message)
            answer['grids'] = deepcopy(self.GRIDS)
            return answer
        self.sender = Sender(newer)
        await self.sync()
        self.assertEqual(self.screen.begin['grid'], [2, 3])
        self.assertEqual(self.sender.grids, self.GRIDS)
        self.assertEqual(self.sender.last_grids, self.GRIDS)
        self.screen.messages.clear()
        self.record = {**deepcopy(self.record), 'sourceGrid': {'columns': 4, 'rows': 3}}
        with self.assertRaises(Refused):
            await self.sync()
        self.assertEqual([message['op'] for message in self.screen.messages], ['hello'])

    async def test_a_screen_stood_up_gets_the_way_and_the_grid_of_that_way(self):
        # App 0.4.85: the way a screen is to hang goes in begin (region "upright") and its grid is held to that way's
        # range; the screen answers that it starts again, which is no applied layout yet.
        async def turning(message):
            answer = await self.screen.send(message)
            answer['grids'] = deepcopy(self.GRIDS)
            if message['op'] == 'begin' and message.get('upright'):
                answer['status'] = 'Restarting'
            return answer
        self.sender = Sender(turning)
        self.record = {**deepcopy(self.record), 'sourceGrid': {'columns': 2, 'rows': 6}}
        self.region = {**self.region, 'upright': True}
        with self.assertRaisesRegex(DeliveryError, 'Restarting'):
            await self.sync()
        self.assertEqual(self.screen.begin['upright'], True)
        self.assertEqual(self.screen.begin['grid'], [2, 6])
        self.assertNotIn('commit', [message['op'] for message in self.screen.messages])
        # Two columns of six lying down are past that way's range: refused before begin.
        self.screen.messages.clear()
        self.region = {**self.region, 'upright': False}
        with self.assertRaises(Refused):
            await self.sync()
        self.assertEqual([message['op'] for message in self.screen.messages], ['hello'])

    async def test_a_screen_given_another_grid_takes_the_sizes_of_that_grid(self):
        # Its hello names the sizes of the grid it is on (two columns of three: no 3x1); the layout's grid of three
        # columns of two takes a tile three columns wide, and the screen takes it with that grid (firmware 0.53.0+).
        self.record = {**deepcopy(self.record), 'sourceGrid': {'columns': 3, 'rows': 2}}
        tile = self.record['layout']['pages'][0]['tiles'][0]
        tile['placement']['columns'] = 3
        tile['appearance']['presentation'] = '3x1'
        self.values[0]['o']['size'] = '3x1'
        on_two_by_three = ['single', 'wide', 'full', 'tall', 'square', '1x3']

        def screen(grids):
            async def answer(message):
                reply = await self.screen.send(message)
                if grids: reply['grids'] = deepcopy(self.GRIDS)
                if message['op'] == 'hello': reply['tile_sizes'] = list(on_two_by_three)
                return reply
            return answer
        self.sender = Sender(screen(grids=False))
        with self.assertRaisesRegex(Refused, 'these tile sizes'):
            await self.sync()
        self.sender = Sender(screen(grids=True))
        await self.sync()
        self.assertEqual(self.screen.begin['grid'], [3, 2])
        self.assertEqual(self.screen.initial[0]['o']['size'], '3x1')

    async def test_a_screen_that_keeps_its_grid_gets_no_grid(self):
        await self.sync()
        self.assertNotIn('grid', self.screen.begin)
        self.assertIsNone(self.sender.grids)

    def test_only_a_whole_and_sane_grids_answer_counts(self):
        self.assertEqual(grids_of({'grids': self.GRIDS}), self.GRIDS)
        for broken in (None, [], {'upright': 1}, {**self.GRIDS, 'portrait': None},
                       {**self.GRIDS, 'landscape': {**self.GRIDS['landscape'], 'max': [10, 5]}},
                       {**self.GRIDS, 'landscape': {**self.GRIDS['landscape'], 'columns': 4}},
                       {**self.GRIDS, 'landscape': {**self.GRIDS['landscape'], 'min': [1]}}):
            self.assertIsNone(grids_of({'grids': broken}), broken)

    async def test_complete_configuration_precedes_activation(self):
        await self.sync()
        ops = [m["op"] for m in self.screen.messages]
        self.assertEqual(ops[:7], ["hello", "begin", "page", "page", "tile", "tile", "commit"])
        self.assertEqual(self.screen.initial[0]["o"]["size"], "wide")
        self.assertEqual(self.screen.initial[0]["o"]["tap"], "toggle")
        self.assertEqual(self.sender.phase, "applied")
        self.assertEqual(self.sender.confirmed, configuration(self.record, self.region))

    async def test_live_values_do_not_replace_configuration(self):
        await self.sync()
        self.screen.messages.clear()
        self.values[0]["a"]["brightness"] = 123
        self.bars[1][0]["t"] = "22 °C"
        await self.sync()
        self.assertEqual([m["op"] for m in self.screen.messages], ["state", "bar"])
        self.assertNotIn("o", self.screen.messages[0])
        self.assertEqual(self.screen.messages[1]["p"], 1)
        self.screen.messages.clear()
        await self.sync()
        self.assertEqual(self.screen.messages, [])

    async def test_future_protocol_error_never_selects_legacy_delivery(self):
        async def future(_):
            return {"status": "Error: protocol version", "protocol": 99}
        sender = Sender(future)
        with self.assertRaises(DeliveryError):
            await sender.probe()
        self.assertIsNone(sender.protocol)
        self.assertIsNone(sender.session)

    async def test_same_revision_recovers_every_interruption_without_edit(self):
        for op in ["hello", "begin", "page", "tile", "commit", "state", "bar"]:
            with self.subTest(op=op):
                self.screen = Screen()
                self.sender = Sender(self.screen.send)
                self.screen.failure = op
                with self.assertRaises(TimeoutError): await self.sync()
                self.assertIsNone(self.sender.confirmed)
                await self.sync()
                self.assertTrue(self.screen.active)
                self.assertEqual(self.sender.phase, "applied")

    async def test_manager_restart_resumes_active_layout_without_initialization(self):
        await self.sync()
        self.screen.messages.clear()
        self.sender = Sender(self.screen.send)
        await self.sync()
        ops = [m["op"] for m in self.screen.messages]
        self.assertEqual(ops[:2], ["hello", "begin"])
        self.assertNotIn("tile", ops)
        self.assertNotIn("page", ops)
        self.assertNotIn("commit", ops)

    async def test_device_reboot_reinitializes_same_revision(self):
        await self.sync()
        self.screen.active = False
        with self.assertRaises(DeliveryError): await self.sender.ping()
        self.screen.messages.clear()
        await self.sync()
        self.assertIn("commit", [m["op"] for m in self.screen.messages])

    async def test_save_during_delivery_cannot_acknowledge_newer_save(self):
        def current():
            return not any(m["op"] == "tile" for m in self.screen.messages)
        with self.assertRaises(Superseded): await self.sync(current)
        self.assertFalse(self.screen.active)
        self.assertIsNone(self.sender.confirmed)
        self.record["layout"]["title"] = "New saved title"
        await self.sync()
        self.assertEqual(self.screen.begin["title"], "New saved title")

    async def test_stale_ack_is_not_an_applied_configuration(self):
        await self.sync()
        self.screen.delayed = {"protocol": 2, "session": "a" * 16, "seq": 99,
                               "rev": self.sender.confirmed, "applied": True, "status": "Synced"}
        with self.assertRaises(DeliveryError): await self.sender.ping()
        self.assertIsNone(self.sender.confirmed)

    async def test_old_firmware_requires_actual_response_not_cached_version(self):
        async def old(_): return {"status": "Error: protocol version", "rev": "123"}
        self.assertEqual(await Sender(old).probe(), 1)
        async def stale(_): return {"status": "Synced", "rev": "123", "protocol": 2}
        with self.assertRaises(DeliveryError): await Sender(stale).probe()

    async def test_messages_preflight_before_any_replacement(self):
        self.values[0]["o"]["act"] = {"s": "light.turn_on", "d": [["data", "x" * 5000]]}
        with self.assertRaises(Refused): await self.sync()
        self.assertEqual(self.screen.messages, [])

    async def test_workspace_revision_and_settings_do_not_reload_firmware(self):
        await self.sync()
        before = self.sender.confirmed
        self.record.update(revision="new-save-revision", workspace={"positions": {}}, settings={"brightness": 20})
        await self.sync()
        self.assertEqual(self.sender.confirmed, before)

    async def test_auxiliary_replies_are_serialized_and_bound_to_request(self):
        await self.sync()
        old_session, old_revision = self.sender.session, self.sender.confirmed
        message = {"v": 1, "op": "history", "entity": "light.test", "hours": 24}
        self.screen.messages.clear()
        self.assertTrue(await self.sender.auxiliary(message, session=old_session, revision=old_revision))
        self.record["layout"]["title"] = "Changed"
        await self.sync()
        count = len(self.screen.messages)
        self.assertFalse(await self.sender.auxiliary(message, session=old_session, revision=old_revision))
        self.assertEqual(len(self.screen.messages), count)


class DockMessageTests(unittest.TestCase):
    def test_only_a_page_left_out_of_the_dock_says_so(self):
        # Every other page message stays as it was, so firmware from before the Dock and every saved fingerprint agree.
        page = {"id": "0000000000000001", "navigation": {"excludeFromPagination": False},
                "topbar": {"leading": [], "title": {"source": "screen"}, "trailing": []}, "tiles": []}
        self.assertNotIn("dock", page_message(page, 0, [], initial=True))
        page["navigation"]["showInDock"] = True
        self.assertNotIn("dock", page_message(page, 0, [], initial=True))
        page["navigation"]["showInDock"] = False
        self.assertIs(page_message(page, 0, [], initial=True)["dock"], False)
        self.assertNotIn("dock", page_message(page, 0, [], initial=False))

    def test_a_page_icon_travels_as_its_codepoint(self):
        page = {"id": "0000000000000001", "navigation": {"excludeFromPagination": False},
                "topbar": {"leading": [], "title": {"source": "screen"}, "trailing": []}, "tiles": []}
        self.assertNotIn("icon", page_message(page, 0, [], initial=True))
        page["icon"] = "sofa"
        self.assertEqual(page_message(page, 0, [], initial=True)["icon"], tile_icons.GLYPHS["sofa"])
        self.assertNotIn("icon", page_message(page, 0, [], initial=False))


if __name__ == "__main__": unittest.main()
