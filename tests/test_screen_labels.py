"""A screen's own name in this app (app 0.4.2): a label only the editor shows, so a rename needs no flash.

Home Assistant keeps its own name (`ha_name`), the ESPHome name and the YAML stay, and an empty label gives
Home Assistant's name back. The label outlives a restart and goes with the screen when it is removed.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from screen_labels import ScreenLabels  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import create_app
    from test_remove_screen import INBOX, LAYOUT, RemoveScreenTests


class ScreenLabelStoreTests(unittest.TestCase):
    def test_a_label_survives_a_restart_and_empty_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screen-labels.json'
            labels = ScreenLabels(path)
            self.assertEqual(labels.set('d1', '  Kitchen   wall '), 'Kitchen wall')
            self.assertEqual(ScreenLabels(path).get('d1'), 'Kitchen wall')
            self.assertIsNone(labels.set('d1', ''))
            self.assertIsNone(ScreenLabels(path).get('d1'))

    def test_a_broken_file_reads_as_no_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'screen-labels.json'
            path.write_text('{nope')
            self.assertIsNone(ScreenLabels(path).get('d1'))


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class RenameScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_renames_a_screen_and_home_assistant_keeps_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = RemoveScreenTests.manager(None, tmp, {INBOX: LAYOUT})
            async with TestClient(TestServer(create_app(manager, True))) as client:
                csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                answer = await client.put(f'/api/screens/{INBOX}/name', json={'name': 'Hallway'}, headers={'X-Screen-CSRF': csrf})
                self.assertEqual((await answer.json())['name'], 'Hallway')
                screen = (await (await client.get('/api/inventory?light=1')).json())['screens'][0]
                self.assertEqual((screen['name'], screen['ha_name']), ('Hallway', 'Office 1'))
                # What the app itself goes by (logs, alerts, Home Assistant) keeps Home Assistant's name.
                self.assertEqual(manager.screen(INBOX)['name'], 'Office 1')
                await client.put(f'/api/screens/{INBOX}/name', json={'name': ''}, headers={'X-Screen-CSRF': csrf})
                screen = (await (await client.get('/api/inventory?light=1')).json())['screens'][0]
                self.assertEqual(screen['name'], 'Office 1')

    async def test_removing_a_screen_forgets_its_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = RemoveScreenTests.manager(None, tmp, {INBOX: LAYOUT})
            manager.labels.set('d1', 'Hallway')
            await manager.remove_screen(INBOX)
            self.assertIsNone(manager.labels.get('d1'))


if __name__ == '__main__':
    unittest.main()
