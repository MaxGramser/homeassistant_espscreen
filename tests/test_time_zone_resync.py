"""Home Assistant's ESPHome integration reads the time zone once, when it connects to a screen, and answers every later
time request with it. When Home Assistant moves to another zone (a screen in a van), the app loads each screen's
integration again, so the screen connects anew and takes the new zone."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp is needed for the server module')
class TimeZoneResyncTests(unittest.TestCase):
    def ha(self, zone):
        import server
        ha = server.HomeAssistant.__new__(server.HomeAssistant)
        ha.time_zone, ha.ha_language, ha.units, ha.location_name = None, 'en', {}, ''
        ha.config_stale, ha.on_config = False, lambda: None
        ha.moves = []
        ha.on_time_zone = lambda: ha.moves.append(ha.time_zone.key)
        ha.zone = zone

        async def request(kind, **_):
            return {'time_zone': ha.zone, 'language': 'en'}
        ha.request = request
        return ha

    def test_only_a_change_of_zone_resyncs(self):
        ha = self.ha('Europe/Amsterdam')
        asyncio.run(ha.read_config())
        self.assertEqual(ha.moves, [], 'the first read is no move')
        asyncio.run(ha.read_config())
        self.assertEqual(ha.moves, [], 'the same zone again is no move')
        ha.zone = 'America/Denver'
        asyncio.run(ha.read_config())
        self.assertEqual(ha.moves, ['America/Denver'])
        self.assertEqual(ha.time_zone, ZoneInfo('America/Denver'))

    def test_every_screen_reconnects(self):
        import server
        manager = server.Manager.__new__(server.Manager)
        reloaded = []

        async def reload_entry(entry):
            reloaded.append(entry)
        manager.ha = mock.Mock(time_zone=ZoneInfo('Asia/Tokyo'), reload_entry=reload_entry)
        manager.screens = lambda: [{'name': 'Kitchen', 'device_id': 'a'}, {'name': 'Hall', 'device_id': 'b'},
                                   {'name': 'Lost', 'device_id': 'c'}]

        async def entry_of(screen, missing=''):
            if screen['device_id'] == 'c':
                raise ValueError('no entry')
            return 'entry-' + screen['device_id']
        manager.entry_of = entry_of
        asyncio.run(manager.resync_clocks())
        self.assertEqual(reloaded, ['entry-a', 'entry-b'], 'a screen without an entry does not stop the others')


if __name__ == '__main__':
    unittest.main()
