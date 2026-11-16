"""The capability record's build half (components/smart_display/hw_build.py; docs/PLATFORM_PLAN.md 3.3): which HW_*
defines a configuration earns, that the component applies them, that the hello carries the record, and that the app
reads it (page_delivery.caps_of)."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components' / 'smart_display'
spec = importlib.util.spec_from_file_location('smart_display_hw_build', COMPONENT / 'hw_build.py')
hw_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw_build)
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))
import page_delivery  # noqa: E402


class Defines(unittest.TestCase):
    def test_a_configuration_earns_its_defines_from_its_components(self):
        # The Tab5 as its parts build it: a speaker, a microphone, Espressif's AEC and the camera of Screen camera.
        tab5 = {'speaker': [{'platform': 'esp_audio_stack', 'id': 'ts_speaker_out'}, {'platform': 'mixer', 'id': 'ts_mixer'}],
                'microphone': [{'platform': 'esp_audio_stack', 'id': 'ts_microphone'}],
                'esp_aec': {'id': 'board_aec'}, 'esp_video_camera': [{'id': 'ts_camera'}], 'lvgl': [{}]}
        self.assertEqual(hw_build.defines(tab5), ['HW_SPEAKER', 'HW_MICROPHONE', 'HW_ECHO_CANCEL', 'HW_CAMERA'])
        # A Waveshare P4 on the plain I2S transport: no canceller, and no camera plugin built in.
        plain = {'speaker': [{'platform': 'i2s_audio', 'id': 'ts_speaker_out'}], 'microphone': [{'platform': 'i2s_audio'}]}
        self.assertEqual(hw_build.defines(plain), ['HW_SPEAKER', 'HW_MICROPHONE'])
        # A CYD: nothing of it.
        self.assertEqual(hw_build.defines({'lvgl': [{}], 'display': [{}]}), [])
        # An empty list is no component.
        self.assertEqual(hw_build.defines({'speaker': []}), [])

    def test_no_define_reads_a_name_a_chip_or_a_pin(self):
        source = (COMPONENT / 'hw_build.py').read_text()
        for word in ('esp32p4', 'ESP32P4', 'tab5', 'guition', 'waveshare', 'reterminal', 'GPIO', 'ts_speaker', 'ts_microphone'):
            self.assertNotIn(word, source.replace("'camera')", ''), f'hw_build.py must not know {word}')


class Wiring(unittest.TestCase):
    """What only the build shows. That the hello carries the record, with the keys hw.cpp writes and the template tile's
    numbers, is proven on the real firmware by tools/render/run.py's self test (hello_record): it reads the record the
    app's own Sender took from the host build's hello. Here: the rules over the files."""

    def test_the_component_applies_every_define_it_earns(self):
        source = (COMPONENT / '__init__.py').read_text()
        self.assertRegex(source, r'for define in hw_build\.defines\(CORE\.config\):\s+cg\.add_define\(define\)',
                         'components/smart_display/__init__.py must add every define hw_build.defines() gives (cg.add_define), '
                         'or the firmware never hears of its speaker, microphone or camera')

    # glass: a P4 screen's hello names "live" among its features, so an app older than the record still offers live
    # cameras; the host build has no live view, so only a P4 shows it. The rule here: the hello says it where it can.
    def test_the_hello_says_live_for_an_older_app(self):
        self.assertRegex((ROOT / 'packages' / 'core.yaml').read_text(), r'if \(live_view::available\(\)\)\s*features\.add\("live"\)',
                         'packages/core.yaml: the hello adds "live" to its features when live_view::available(), for an app '
                         'older than the hardware record')
        for header in ('smart_display.h', 'plugin_api.h'):
            self.assertIn('#include "hw.h"', (COMPONENT / header).read_text(),
                          f'{header} includes hw.h: the firmware and every plugin read the hardware record (hw::caps) from it')

    def test_every_text_tile_fits_a_state_message(self):
        # A template tile's rows (module text_card), at the most bytes any board keeps, with the room the message's own
        # fields take, fit in one state message of page_delivery.MAX_MESSAGE.
        card = (COMPONENT / 'module_text_card.h').read_text()
        limits = [int(n) for n in re.findall(r'constexpr unsigned MAX_BYTES = (\d+);', card)]
        self.assertTrue(limits, 'module_text_card.h states MAX_BYTES for each board kind')
        for limit in limits:
            self.assertLessEqual(limit + 512, page_delivery.MAX_MESSAGE,
                                 f'a template tile of {limit} bytes and its message\'s own 512 must fit page_delivery.MAX_MESSAGE')

    def test_the_live_tiles_are_the_engines(self):
        # How many live tiles a screen streams at once is its picture engine's (picture_engine::limits, the fourth number):
        # four on a P4, as docs/PLATFORM_PLAN.md 4.1 and the editor's text say; one on an S3, whose CPU decodes it; none
        # elsewhere. hw.h keeps no number of its own.
        engine = (COMPONENT / 'picture_engine.h').read_text()
        live = [int(n) for n in re.findall(r'constexpr Limits limits\(\) \{ return \{[^,]+,[^,]+,[^,]+, (\d+),', engine)]
        self.assertEqual(live, [4, 1, 0], 'picture_engine.h: the live tiles of a P4, an S3 and a board without pictures '
                                          'are 4, 1 and 0; change docs/PLATFORM_PLAN.md 4.1 and the editor with them')
        self.assertIn('four', (ROOT / 'docs' / 'PLATFORM_PLAN.md').read_text(), 'docs/PLATFORM_PLAN.md names the four of a P4')
        self.assertNotRegex((COMPONENT / 'hw.h').read_text(), r'\bLIVE_TILES\s*=',
                            'hw.h keeps no live-tile count of its own: it is picture_engine::limits().live_tiles')


class AppSide(unittest.TestCase):
    def test_the_app_reads_the_record_and_falls_back_on_the_features(self):
        answer = {'features': ['live', 'doorbell', 'pictures'],
                  'caps': {'live': True, 'speaker': True, 'microphone': False, 'echo_cancel': False, 'camera': True,
                           'live_tiles': 4, 'psram_kb': 32768, 'internal_kb': 768}}
        caps = page_delivery.caps_of(answer)
        self.assertIsNone(caps['text_tiles'])  # a screen without the template tile's module says none
        self.assertEqual(page_delivery.caps_of({'caps': {'text_tiles': 8, 'text_bytes': 3584}})['text_bytes'], 3584)
        self.assertEqual(caps['live'], True)
        self.assertEqual(caps['live_tiles'], 4)
        self.assertEqual(caps['speaker'], True)
        self.assertEqual(caps['microphone'], False)
        self.assertEqual(caps['psram_kb'], 32768)
        # A tile of the screen's own camera drawn on the screen (plugin API 0.22): only when the hello says so.
        self.assertEqual(caps['own_camera'], False)
        self.assertEqual(page_delivery.caps_of({'caps': {'own_camera': True}})['own_camera'], True)
        # Which camera is a screen's own (server.Manager.own_camera_of): the tessera_video camera on its device, or on a
        # device of its own with the screen's MAC; and only for a screen whose hello says own_camera.
        import types
        import server
        sender = types.SimpleNamespace(caps={'own_camera': True})
        registry = {'camera.tablet_video': {'platform': 'tessera_video', 'device_id': 'cam'},
                    'camera.door': {'platform': 'generic', 'device_id': 'cam'},
                    'camera.other': {'platform': 'tessera_video', 'device_id': 'elsewhere'}}
        devices = [{'id': 'screen', 'connections': [['mac', 'AA:BB:CC:00:11:22']]},
                   {'id': 'cam', 'connections': [['mac', 'aa:bb:cc:00:11:22']]},
                   {'id': 'elsewhere', 'connections': [['mac', 'aa:bb:cc:99:99:99']]}]
        manager = types.SimpleNamespace(page_senders={'text.tablet': sender}, aliases={}, registry_index=lambda: registry,
                                        ha=types.SimpleNamespace(devices=devices))
        own = lambda entity, screen={'device_id': 'screen'}: server.Manager.own_camera_of(manager, 'text.tablet', screen, entity)
        self.assertTrue(own('camera.tablet_video'))
        self.assertFalse(own('camera.door') or own('camera.other') or own('camera.tablet_video', {}))
        sender.caps = {'own_camera': False}
        self.assertFalse(own('camera.tablet_video'))
        # A glass turned so that the screen takes its live pictures turned (picture_turn): only a turn a glass has.
        self.assertEqual(caps['picture_turn'], 0)
        self.assertEqual(page_delivery.caps_of({'caps': {'picture_turn': 270}})['picture_turn'], 270)
        for odd in (45, True, '90', -90, 360):
            self.assertEqual(page_delivery.caps_of({'caps': {'picture_turn': odd}})['picture_turn'], 0, odd)
        manager.page_senders['text.tablet'].caps = {'picture_turn': 90}
        self.assertEqual(server.Manager.picture_turn_of(manager, 'text.tablet'), 90)
        self.assertEqual(server.Manager.picture_turn_of(manager, 'text.other'), 0)
        # An older firmware sends no record: live follows the feature, the counts are unknown (None), the rest False.
        old = page_delivery.caps_of({'features': ['live', 'pictures']})
        self.assertEqual(old['live'], True)
        self.assertIsNone(old['live_tiles'])
        self.assertEqual(old['speaker'], False)
        older = page_delivery.caps_of({'features': ['pictures']})
        self.assertEqual(older['live'], False)
        # Garbage is no record.
        self.assertEqual(page_delivery.caps_of({'features': ['live'], 'caps': 'yes'})['live'], True)
        self.assertEqual(page_delivery.caps_of({'caps': {'live_tiles': 'many', 'live': 1}})['live_tiles'], None)

    def test_the_senders_record_follows_its_hello(self):
        # The app's own Sender, given a screen's hello: its record is what caps_of reads of it, said once in the log when
        # it changes (a reTerminal D1001 on glass, 2026-10-25, where nothing showed what the app had read), not again.
        import asyncio

        def hello(caps):
            async def send(message):
                return {'protocol': page_delivery.PROTOCOL, 'request': message['request'], 'session': 'a' * 16,
                        'status': 'Session:' + 'a' * 16, 'features': ['live', 'pictures'], 'caps': caps}
            return send

        record = {'live': True, 'speaker': True, 'microphone': False, 'echo_cancel': False, 'camera': True, 'live_tiles': 4,
                  'psram_kb': 32768, 'internal_kb': 768}
        sender = page_delivery.Sender(hello(record), name='Kitchen')
        self.assertEqual(sender.caps, page_delivery.caps_of({}))
        with self.assertLogs(page_delivery.LOG, 'INFO') as said:
            asyncio.run(sender._hello())
        self.assertEqual(sender.caps, page_delivery.caps_of({'features': ['live', 'pictures'], 'caps': record}))
        self.assertEqual(said.output, [f'INFO:{page_delivery.LOG.name}:Kitchen: {page_delivery.caps_line(sender.caps)}'])
        with self.assertNoLogs(page_delivery.LOG, 'INFO'):
            asyncio.run(sender._hello())
        sender.send = hello({**record, 'live_tiles': 1})
        with self.assertLogs(page_delivery.LOG, 'INFO'):
            asyncio.run(sender._hello())
        self.assertEqual(sender.caps['live_tiles'], 1)

    def test_the_record_in_one_line(self):
        caps = page_delivery.caps_of({'caps': {'live': True, 'speaker': True, 'microphone': True, 'echo_cancel': False,
                                               'camera': True, 'live_tiles': 4, 'psram_kb': 28272, 'internal_kb': 519}})
        self.assertEqual(page_delivery.caps_line(caps), 'live, 4 live tiles, speaker, microphone, camera, no echo '
                         'cancellation, 28272 KB PSRAM, 519 KB internal RAM')
        self.assertEqual(page_delivery.caps_line(page_delivery.caps_of({'features': ['pictures']})), 'no echo cancellation')
        self.assertEqual(page_delivery.caps_line(page_delivery.caps_of({'caps': {'picture_turn': 270}})),
                         "no echo cancellation, live pictures turned 270")



class Inventory(unittest.IsolatedAsyncioTestCase):
    """The editor gets the record: the inventory's screen carries the record of its last hello (server.Manager.caps_of_screen),
    which the editor reads to mark a live camera beyond caps.live_tiles (web/tests/live-tiles.spec.ts, pausedLive)."""

    async def test_the_inventory_carries_the_record_of_the_last_hello(self):
        import tempfile
        from aiohttp.test_utils import TestClient, TestServer
        import test_portal
        from server import create_app
        with tempfile.TemporaryDirectory() as temp:
            manager = test_portal.ManagerTests.setup_manager(self, Path(temp) / 'screens.json')
            manager.save('text.screen', {'title': 'Test', 'tiles': [{'entity': 'light.a', 'name': '', 'slot': 0}], 'pages': 1})
            async with TestClient(TestServer(create_app(manager, True))) as client:
                before = await (await client.get('/api/inventory')).json()
                self.assertIsNone(next(s for s in before['screens'] if s['id'] == 'text.screen')['caps'],
                                  'a screen without a hello in this run has no record yet')
                sender = manager.page_sender('text.screen', manager.screen('text.screen'))
                sender.protocol = page_delivery.PROTOCOL
                sender.caps = page_delivery.caps_of({'caps': {'live': True, 'live_tiles': 4, 'psram_kb': 32768}})
                after = await (await client.get('/api/inventory')).json()
                caps = next(s for s in after['screens'] if s['id'] == 'text.screen')['caps']
                self.assertEqual((caps['live'], caps['live_tiles'], caps['psram_kb']), (True, 4, 32768))


if __name__ == '__main__':
    unittest.main()
