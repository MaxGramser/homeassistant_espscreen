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
    def test_the_component_applies_the_defines_and_the_hello_carries_the_record(self):
        source = (COMPONENT / '__init__.py').read_text()
        self.assertRegex(source, r'for define in hw_build\.defines\(CORE\.config\):\n\s+cg\.add_define\(define\)')
        core = (ROOT / 'packages' / 'core.yaml').read_text()
        self.assertIn('hw::hello(root);', core)
        # The record is written after the plugins' part of the hello and beside the features an older app reads.
        self.assertLess(core.index('plugin_host::hello(root);'), core.index('hw::hello(root);'))
        self.assertIn('if (live_view::available()) features.add("live");', core)
        header = (COMPONENT / 'hw.cpp').read_text()
        for key in ('"live"', '"speaker"', '"microphone"', '"echo_cancel"', '"camera"', '"live_tiles"', '"psram_kb"', '"internal_kb"'):
            self.assertIn(key, header)
        # The template tile's numbers (module text_card), only where the module is: how many, and the bytes of rows each
        # keeps, an S3's and a P4's, both under a state message's 4096 bytes (tests/test_text_tile.py, Limits).
        guarded = header[header.index('#ifdef SD_MOD_TEXT_CARD\n  //'):]
        self.assertIn('caps["text_tiles"] = text_card::MAX_TILES;', guarded)
        self.assertIn('caps["text_bytes"] = text_card::MAX_BYTES;', guarded)
        card = (COMPONENT / 'module_text_card.h').read_text()
        self.assertIn('constexpr unsigned MAX_BYTES = 3584;', card)
        self.assertIn('constexpr unsigned MAX_BYTES = 2048;', card)
        self.assertLessEqual(3584 + 512, page_delivery.MAX_MESSAGE)
        self.assertIn('#include "hw.h"', (COMPONENT / 'smart_display.h').read_text())
        self.assertIn('#include "hw.h"', (COMPONENT / 'plugin_api.h').read_text())

    def test_the_live_tiles_are_the_engines(self):
        # How many live tiles a screen streams at once is its picture engine's (picture_engine::limits): four on a P4, as
        # docs/PLATFORM_PLAN.md 4.1 and the add-on's editor text say; one on an S3, whose CPU decodes it; none elsewhere.
        engine = (COMPONENT / 'picture_engine.h').read_text()
        self.assertIn('constexpr Limits limits() { return {64, 1024 * 1024, 384 * 1024, 4, true, 0, 24, 1, 7}; }', engine)
        self.assertIn('constexpr Limits limits() { return {0, 256 * 1024, 128 * 1024, 1, false, 8, 8, 0, 1}; }', engine)
        self.assertIn('constexpr Limits limits() { return {0, 0, 0, 0, false, 0, 0, 1, 0}; }', engine)
        self.assertIn('f.live_tiles = picture_engine::limits().live_tiles;', (COMPONENT / 'hw.cpp').read_text())
        self.assertNotIn('LIVE_TILES =', (COMPONENT / 'hw.h').read_text())

    def test_the_cpp_test_is_in_the_runner(self):
        self.assertTrue((ROOT / 'tests' / 'test_hw.cpp').exists())


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
        source = (ROOT / 'screen_manager' / 'app' / 'page_delivery.py').read_text()
        self.assertIn('caps = caps_of(answer)', source)
        self.assertIn('self.caps = caps', source)
        self.assertRegex(source, r'self\.caps = caps_of\(\{\}\)')
        # One line in the log when a screen's record changes, so every report has it (a reTerminal D1001 on glass,
        # 2026-10-25, where nothing showed what the app had read).
        self.assertIn('LOG.info("%s: %s", self.name or "A screen", caps_line(caps))', source)

    def test_the_record_in_one_line(self):
        caps = page_delivery.caps_of({'caps': {'live': True, 'speaker': True, 'microphone': True, 'echo_cancel': False,
                                               'camera': True, 'live_tiles': 4, 'psram_kb': 28272, 'internal_kb': 519}})
        self.assertEqual(page_delivery.caps_line(caps), 'live, 4 live tiles, speaker, microphone, camera, no echo '
                         'cancellation, 28272 KB PSRAM, 519 KB internal RAM')
        self.assertEqual(page_delivery.caps_line(page_delivery.caps_of({'features': ['pictures']})), 'no echo cancellation')
        self.assertEqual(page_delivery.caps_line(page_delivery.caps_of({'caps': {'picture_turn': 270}})),
                         "no echo cancellation, live pictures turned 270")

    def test_the_editor_gets_the_record(self):
        # The inventory's screen carries it (server.py, caps_of_screen) and the editor marks a live camera beyond
        # caps.live_tiles (web/src/model/live-tiles.ts, tests/live-tiles.spec.ts).
        source = (ROOT / 'screen_manager' / 'app' / 'server.py').read_text()
        self.assertIn("screen['caps'] = manager.caps_of_screen(screen)", source)
        model = (ROOT / 'web' / 'src' / 'model' / 'live-tiles.ts').read_text()
        self.assertIn('export function pausedLive(', model)

    def test_the_apps_503_is_a_safety_net(self):
        # A screen that reads its own record streams at most caps.live_tiles at once (runtime_tiles live_tiles_round), so
        # the app's 503 for a stream beyond them (live_stream.py) is never reached by such a firmware: it is the net for
        # one that does not cap, and no proof on glass can show it.
        source = (ROOT / 'screen_manager' / 'app' / 'live_stream.py').read_text()
        self.assertIn("return f'This screen plays {cap} cameras live at once' if cap != 1", source)
        # The stream and a tile's picture at a time both answer it (LiveFeed.refused).
        self.assertEqual(source.count('return web.Response(status=503, text=why)'), 2)


if __name__ == '__main__':
    unittest.main()
