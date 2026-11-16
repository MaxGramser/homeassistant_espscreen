from manager_fixtures import seed_layout
"""What a layout of forty-eight tiles runs into, refused when it is saved instead of later (app 0.2.78).

- The screen takes the layout in one message of at most 4096 bytes that lists every entity id: 48 tiles with long ids
  passed Save and then never reached the screen.
- Tiles without positions are packed in order: 48 with one double-width, or 43 with a full-page one that isn't first,
  ran past the eighth page and failed later with "Invalid tile position".
- The request limit was 16 KB from the twenty-tile days, and a valid 48-tile layout with tap actions is larger.
- The layout sensor keeps under the 16 KB Home Assistant's recorder stores of a state's attributes.
"""
from manager_fixtures import with_screen_grid
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import (ACTION_MAX_BYTES, MAX_TILES, apply_tile_event, encode, layout_snapshot, pack_slots, packed_slots,  # noqa: E402
                  validate_layout, validate_tap_action, action_for_screen)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import test_scaling
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app

TOO_LONG = "These tiles' entity IDs are too long together to fit in one message to the screen; remove a few tiles."
NO_ROOM = "These tiles don't fit on this screen's pages; remove a tile or make one smaller."
# Home Assistant's recorder keeps a state's attributes up to this many bytes of JSON.
RECORDER_ATTRIBUTES = 16384


def entity(index, length, domain='light'):
    stem = f'{domain}.tile_{index:02d}_'
    return stem + 'x' * (length - len(stem))


def tiles(count, length=12, **options):
    return [{'entity': entity(i, length), 'name': '', **({'options': dict(options)} if options else {})} for i in range(count)]


class Packing(unittest.TestCase):
    def test_tiles_that_run_past_the_last_page_are_refused_at_once(self):
        wide = tiles(MAX_TILES)
        wide[5]['options'] = {'size': 'wide'}
        self.assertGreaterEqual(max(pack_slots(wide)), 48, 'what used to be stored')
        with self.assertRaisesRegex(ValueError, NO_ROOM):
            validate_layout({'title': 'Hall', 'tiles': wide})
        full = tiles(43)
        full[1]['options'] = {'size': 'full'}
        with self.assertRaisesRegex(ValueError, NO_ROOM):
            packed_slots(full)
        with self.assertRaisesRegex(ValueError, NO_ROOM):
            validate_layout({'title': 'Hall', 'tiles': full})
        # The same tiles fit with the full page first, and 48 single tiles fill every spot.
        first = [full[1]] + full[:1] + full[2:]
        self.assertEqual(validate_layout({'title': 'Hall', 'tiles': first})['tiles'][-1]['slot'], 47)
        self.assertEqual(packed_slots(tiles(MAX_TILES)), list(range(48)))

    def test_ordering_the_whole_screen_says_so_too(self):
        placed = [{**tile, 'slot': slot} for tile, slot in zip(tiles(43), [0] + list(range(6, 48)))]
        placed[0]['options'] = {'size': 'full'}
        layout = validate_layout({'title': 'Hall', 'tiles': placed})
        with self.assertRaisesRegex(ValueError, NO_ROOM):
            apply_tile_event(layout, 'order', {'entities': [entity(1, 12)]})


class Snapshot(unittest.TestCase):
    def test_the_layout_sensor_stays_within_what_the_recorder_keeps(self):
        action = {'action': 'light.turn_on', 'data': {'brightness_pct': 40, 'transition': 2, 'color_name': 'warm' + 'x' * 40}}
        layout = validate_layout({'title': 'T' * 96, 'tiles': [
            {'entity': entity(i, 60), 'name': 'N' * 30, 'slot': i,
             'options': {'size': 'single', 'controls': 'none', 'display': 'standard', 'tap': 'action' if i % 12 == 0 else 'detail',
                         **({'action': action} if i % 12 == 0 else {})}} for i in range(MAX_TILES)]})
        snapshot = layout_snapshot({'name': 'Living room screen', 'node': 'living-room-screen'}, layout)
        # What publish_layouts hands Home Assistant.
        attributes = {'friendly_name': 'Living room screen tiles', 'icon': 'mdi:view-dashboard-outline', **snapshot}
        size = len(json.dumps(attributes, ensure_ascii=False, separators=(',', ':')).encode())
        self.assertLess(size, RECORDER_ATTRIBUTES, size)
        self.assertEqual(set(snapshot), {'screen', 'node', 'title', 'columns', 'rows', 'max_pages', 'max_tiles', 'pages', 'tiles'})
        documented = {'entity', 'name', 'page', 'row', 'column', 'slot', 'size', 'controls', 'display', 'tap', 'action', 'to_page'}
        for item in snapshot['tiles']:
            self.assertLessEqual(set(item), documented)
        self.assertEqual(sum('action' in item for item in snapshot['tiles']), 4)


def largest_tap_action():
    """A tap action as large as validate_tap_action allows: eight fields, ACTION_MAX_BYTES on the wire."""
    data = {f'field_{n}': '' for n in range(8)}
    while True:
        for key in data:
            trial = {**data, key: data[key] + 'v'}
            act = action_for_screen({'action': 'light.turn_on', 'data': trial})
            if len(json.dumps(act, separators=(',', ':')).encode()) > ACTION_MAX_BYTES:
                return validate_tap_action({'action': 'light.turn_on', 'data': data})
            data = trial


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Saving(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, layout_tiles):
        ha = test_scaling.fake_ha(firmware='0.2.63')
        for tile in layout_tiles:
            ha.registry.append({'entity_id': tile['entity'], 'platform': 'hue'})
            ha.states[tile['entity']] = {'state': 'on', 'attributes': {}}
        return Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')

    async def test_long_entity_ids_are_refused_when_saved(self):
        long_ids, short_ids = tiles(MAX_TILES, 80), tiles(MAX_TILES)
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, long_ids + short_ids)
            with self.assertRaisesRegex(ValueError, TOO_LONG):
                m.save('text.screen', {'title': 'Hall', 'tiles': long_ids})
            self.assertNotIn('text.screen', m.layouts)
            m.save('text.screen', {'title': 'Hall', 'tiles': short_ids})
            self.assertEqual(len(m.layouts['text.screen']['tiles']), 48)
            self.assertTrue(await m.sync_one('text.screen', m.layouts['text.screen']))
            # A layout an older app stored anyway gets a status, not a retry every pass.
            stored = validate_layout({'title': 'Hall', 'tiles': long_ids})
            seed_layout(m, 'text.screen', stored)
            m.sent.clear()
            self.assertFalse(await m.sync_one('text.screen', stored))
            self.assertIn('too large for one message', m.status['text.screen'])

    async def test_the_largest_valid_layout_is_accepted_and_a_huge_request_is_refused_plainly(self):
        # 70-character ids are about the longest 48 tiles can have in one message.
        action = largest_tap_action()
        layout_tiles = [{'entity': entity(i, 70), 'name': 'é' * 40, 'slot': i,
                         'options': {'tap': 'action', 'action': action, 'background': 'purple', 'icon': 'lightbulb', 'size': 'single',
                                     'inline': 'none', 'display': 'standard'}} for i in range(MAX_TILES)]
        body = {'title': 'T' * 96, 'tiles': layout_tiles}
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, layout_tiles)
            async with TestClient(TestServer(create_app(m, True))) as client:
                headers = {'X-Screen-CSRF': (await (await client.get('/api/inventory?light=1')).json())['csrf']}
                from layout_migrations import migrate_legacy
                from core import Grid
                document = migrate_legacy(body, Grid())
                raw = json.dumps({'format': 'pages-v2', 'revision': None, 'layout': document['layout']}).encode()
                self.assertGreater(len(raw), 48 * 1024, 'far past the old 16 KB')
                response = await client.put('/api/screens/text.screen', data=raw, headers={**headers, 'Content-Type': 'application/json'})
                result = await response.json()
                self.assertEqual(response.status, 200, result)
                self.assertTrue(result['saved'])
                self.assertEqual(result['document']['layout'], document['layout'])
                self.assertEqual(len(m.layouts['text.screen']['tiles']), 48)
                encode(m.layout_message('text.screen', m.layouts['text.screen'], m.screen('text.screen')))
                huge = json.dumps({'title': 'Hall', 'tiles': [], 'filler': 'x' * (128 * 1024)}).encode()
                response = await client.put('/api/screens/text.screen', data=huge, headers={**headers, 'Content-Type': 'application/json'})
                self.assertEqual((response.status, await response.json()), (413, {'error': 'That request is too large.'}))


if __name__ == '__main__':
    unittest.main()
