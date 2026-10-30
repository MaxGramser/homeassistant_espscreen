"""The build facts of the pictures (components/smart_display/p4_build.py and engine_build.py; docs/PICTURE_ARCHITECTURE.md,
section 3.9): the network options a P4 gets less the screen's own, which picture engine, glass and streams a build gets
from the chip, LVGL and PSRAM (never a board), and that the wraps the P4 engine and the glass need are the ones the build
adds and the ones the code defines."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components' / 'smart_display'
spec = importlib.util.spec_from_file_location('smart_display_p4_build', COMPONENT / 'p4_build.py')
p4_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p4_build)
spec = importlib.util.spec_from_file_location('smart_display_engine_build', COMPONENT / 'engine_build.py')
engine_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine_build)


class P4Build(unittest.TestCase):
    def test_the_component_applies_them_on_a_p4_alone(self):
        # The P4 boards build with the larger TCP window and the live view, keyed on the chip in the component.
        source = (COMPONENT / '__init__.py').read_text()
        facts = (COMPONENT / 'p4_build.py').read_text()
        self.assertIn('"CONFIG_LWIP_TCP_WND_DEFAULT": 65534', facts)
        self.assertRegex(source, r'if _esp32_p4\(\):\n\s+_p4\(config\)')
        self.assertIn('return get_esp32_variant() == VARIANT_ESP32P4', source)
        # The engine on every ESP32 build, from the table (engine_build.py); its wraps the panel as ESP-IDF makes it and
        # the panel watch's frame callback and every PPA burst shorter (glass_dsi.cpp), a turned copy in pieces (ppa_guard.cpp).
        self.assertRegex(source, r'if CORE\.is_esp32:\n\s+await _engine\(config\)')
        engines = (COMPONENT / 'engine_build.py').read_text()
        for wrap in ('esp_lcd_new_panel_dpi', 'esp_lcd_dpi_panel_register_event_callbacks', 'ppa_register_client',
                     'ppa_do_scale_rotate_mirror'):
            self.assertIn(f'"{wrap}"', engines)
        self.assertIn('cg.add_build_flag(f"-Wl,--wrap={wrap}")', source)
        self.assertIn('add_idf_component(name=name, ref=ref)', source)
        # The main loop's waits for the C6's answers (5 s each in esp_hosted) must fit the task watchdog, or a busy SDIO
        # link restarts the screen instead of failing a call (2026-10-24, the D1001, a Tab5 and a Guition 10.1).
        hardware = (ROOT / 'packages/hardware/esp32p4-core.yaml').read_text()
        self.assertRegex(hardware, r'(?m)^esp32:\n(?:  .*\n)*?  watchdog_timeout: 20s\n', 'every P4 board waits 20 s on its main loop')
        # A screen's own sdkconfig_options keep the last word.
        self.assertIn('if name not in own', facts)

    def test_the_screens_own_options_keep_the_last_word(self):
        self.assertEqual(p4_build.network_options({}), p4_build.P4_NETWORK)
        own = {'CONFIG_LWIP_TCP_WND_DEFAULT': '32768', 'CONFIG_SOMETHING_ELSE': 'y'}
        got = p4_build.network_options(own)
        self.assertNotIn('CONFIG_LWIP_TCP_WND_DEFAULT', got)
        self.assertEqual(got['CONFIG_LWIP_TCP_SND_BUF_DEFAULT'], 65534)
        self.assertTrue(got['CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP'])

    def test_the_engine_follows_the_chip_lvgl_and_psram_not_a_board(self):
        self.assertEqual(engine_build.picture_engine('esp32p4', True), 'p4')
        self.assertEqual(engine_build.picture_engine('esp32p4', False), 'software')
        self.assertEqual(engine_build.picture_engine('esp32s3', True, True), 's3')
        self.assertEqual(engine_build.picture_engine('esp32s3', True, False), 'software')  # nowhere to decode into
        self.assertEqual(engine_build.picture_engine('esp32s3', False, True), 'software')
        for variant in ('esp32', 'esp32c3', 'host'):
            self.assertEqual(engine_build.picture_engine(variant, True, True), 'software')
        # Three things, each its own define: the engine, the glass and the streams; a P4 and an S3 have all three, each
        # its own glass.
        self.assertEqual(engine_build.ENGINES['p4']['defines'], ('PICTURE_ENGINE_P4', 'GLASS_DSI', 'USE_LIVE_VIEW'))
        self.assertEqual(engine_build.ENGINES['s3']['defines'], ('PICTURE_ENGINE_S3', 'GLASS_RGB', 'USE_LIVE_VIEW'))
        self.assertEqual(engine_build.ENGINES['s3']['components'], (('espressif/esp_new_jpeg', '1.0.2'),))
        self.assertEqual(engine_build.ENGINES['software'], {'defines': (), 'wraps': (), 'components': ()})

    def test_the_wraps_are_the_engines_and_the_glasss(self):
        # __init__.py adds the wraps an engine names, from the table and nowhere else; the engine's and the glass's own
        # files define them, and no file defines one the table does not name.
        init = (COMPONENT / '__init__.py').read_text()
        self.assertIn('for wrap in engine["wraps"]:', init)
        self.assertIn('cg.add_build_flag(f"-Wl,--wrap={wrap}")', init)
        self.assertEqual(re.findall(r'-Wl,--wrap=(\w+)', init), [])
        defined = set()
        for name in ('glass_dsi.cpp', 'ppa_guard.cpp', 'live_view.cpp', 'picture_engine_p4.cpp'):
            defined |= set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / name).read_text()))
        self.assertEqual(defined, set(engine_build.ENGINES['p4']['wraps']))
        s3 = set()
        for name in ('glass_rgb.cpp', 'picture_engine_s3.cpp'):
            s3 |= set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / name).read_text()))
        self.assertEqual(s3, set(engine_build.ENGINES['s3']['wraps']))
        # The diagnostic wraps every ESP32 gets come from their own table, and abort_record.cpp defines exactly those.
        self.assertIn('for wrap in DIAGNOSTIC_WRAPS:', init)
        diagnostic = set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / 'abort_record.cpp').read_text()))
        self.assertEqual(diagnostic, set(re.search(r'DIAGNOSTIC_WRAPS = \(([^)]*)\)', init)[1].replace('"', '').replace(',', ' ').split()))
        # The defines the table gives are the ones the code builds under: the engines in picture_engine.h and their own
        # files, the glasses in glass.h and their own files, the streams in live_view.h and live_view.cpp.
        for define, names in (('PICTURE_ENGINE_P4', ('picture_engine.h', 'picture_engine_p4.cpp', 'ppa_guard.cpp')),
                              ('PICTURE_ENGINE_S3', ('picture_engine.h', 'picture_engine_s3.cpp')),
                              ('GLASS_DSI', ('glass.h', 'glass_dsi.cpp')),
                              ('GLASS_RGB', ('glass.h', 'glass_rgb.cpp')),
                              ('USE_LIVE_VIEW', ('live_view.h', 'live_view.cpp'))):
            for name in names:
                self.assertIn(define, (COMPONENT / name).read_text(), name)


class Sockets(unittest.TestCase):
    """A P4 screen counts its streams and downloads into ESPHome's socket total (smart_display/__init__.py, _sockets):
    the count follows live_view.h's MAX_STREAMS, and the downloads are picture_fetch's three slots."""

    def test_the_count_follows_the_code(self):
        init = (COMPONENT / '__init__.py').read_text()
        streams = re.search(r'constexpr int MAX_STREAMS = (\d+);', (COMPONENT / 'live_view.h').read_text())
        self.assertIn(f'P4_STREAM_SOCKETS = {streams[1]}', init)
        slots = re.findall(r'^Slot &(\w+)\(\);', (COMPONENT / 'picture_fetch.h').read_text(), re.M)
        self.assertIn(f'PICTURE_SOCKETS = {len(slots)}', init)
        self.assertIn('FINAL_VALIDATE_SCHEMA = _sockets', init)


class ChipFactsBehindTheEngine(unittest.TestCase):
    """The P4's facts live behind the picture engine (docs/PLATFORM_PLAN.md 3.2): outside the engine's own files the
    code names no sixteenths, no PPA, no JPEG driver and no panel driver; it asks picture_engine (limits, fit, cut,
    blit) and glass, whose panel files (glass_dsi.cpp, glass_rgb.cpp) are the only ones to name ESP-IDF's panels.
    Comments and strings may name them."""
    ALLOWED = {'picture_engine.h', 'picture_engine_p4.cpp', 'ppa_guard.h', 'ppa_guard.cpp', 'picture_jpeg.h',
               'glass_dsi.cpp', 'glass_rgb.cpp'}
    RULES = {'sixteenths': r'\bsixteenths\b', 'PPA': r'\bppa_\w+\s*\(|\bPPA_[A-Z0-9_]+',
             'JPEG driver': r'\bjpeg_(?:decoder|decode|alloc|new|del)\w*', 'MIPI': r'\bmipi\w*|\bMIPI\w*|\besp_lcd_\w+'}

    @staticmethod
    def code(text):
        text = re.sub(r'//[^\n]*', '', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)

    def test_no_chip_fact_outside_the_engine(self):
        found = []
        for path in sorted(COMPONENT.glob('*')):
            if path.suffix not in ('.h', '.cpp') or path.name in self.ALLOWED:
                continue
            body = self.code(path.read_text())
            for name, rx in self.RULES.items():
                found += [f'{path.name}: {name} ({m.group(0)})' for m in re.finditer(rx, body)]
        self.assertEqual(found, [])



class GlassTurns(unittest.TestCase):
    """The glass is a mutex FreeRTOS gives to its highest waiter (glass.h): a still's download, at priority 1, waited
    for it behind four live tiles for up to two minutes (a reTerminal D1001, 2026-10-25, "11011 ms waiting for the
    glass, 2 ms holding it"). Every writer waits at one priority."""

    def test_a_still_waits_at_the_streams_priority(self):
        self.assertIn('constexpr unsigned WRITER_PRIORITY = 5;', (COMPONENT / 'glass.h').read_text())
        live = (COMPONENT / 'live_view.cpp').read_text()
        # A stream's task runs below the wake word and asks for the glass at the writers' priority, back once it let go.
        self.assertIn('constexpr unsigned STREAM_PRIORITY = 2;', live)
        self.assertIn('"live_view", STACK_BYTES, s, STREAM_PRIORITY,\n                          picture_engine::limits().stream_core)', live)
        take = live[live.index('static uint32_t take_glass() {'):live.index('static void turn_loader(Stream &s) {')]
        steps = ['vTaskPrioritySet(nullptr, glass::WRITER_PRIORITY);', 'glass::hold_counted();', 'glass::release();',
                 'vTaskPrioritySet(nullptr, STREAM_PRIORITY);']
        self.assertEqual([take.index(step) for step in steps], sorted(take.index(step) for step in steps))
        engine = (COMPONENT / 'picture_engine_p4.cpp').read_text()
        decode = engine[engine.index('uint8_t *decode('):engine.index('// ---- The PPA ----')]
        # Raised before the wait, held only around the glass, and back at its own once it let go.
        order = ['vTaskPrioritySet(nullptr, glass::WRITER_PRIORITY);', 'glass::hold();', 'glass::release();',
                 'vTaskPrioritySet(nullptr, own);']
        self.assertEqual([decode.index(step) for step in order], sorted(decode.index(step) for step in order))
        # A slow still says where its time went.
        fetch = (COMPONENT / 'picture_fetch.cpp').read_text()
        self.assertIn('waiting for the glass, %u ms holding it)', fetch)


class LiveTileName(unittest.TestCase):
    """A live tile's name lies over its pictures as the picture card lays it (render_camera_card): the tile's font, left,
    at the bottom of the card's content, in the picture's ink. A copy of the card's own label lay dark and halfway up
    over every picture of a card that had no still yet and stood in its plain layout (a wallbox, 2026-10-28)."""

    def test_the_name_is_drawn_as_the_picture_card_lays_it(self):
        tiles = (COMPONENT / 'runtime_tiles.h').read_text()
        opened = tiles[tiles.index('inline live_view::Handle live_spot_open('):]
        opened = opened[:opened.index('\n  Widgets *card = nullptr;')]
        self.assertIn('live_name(look, *card, spot.room)', opened)
        self.assertNotIn('lv_snapshot_take(card->title', opened)
        name = tiles[tiles.index('inline lv_draw_buf_t *live_name('):tiles.index('// A tile\'s spot: its card\'s room')]
        for step in ('theme::color(theme::CAMERA_INK)', 'LV_TEXT_ALIGN_LEFT', 'lv_obj_get_content_coords(card.tile, &content)',
                     'look.name_y = content.y2 + 1 - h - ext - room.y;', 'lv_obj_delete(off);'):
            self.assertIn(step, name)
        # The picture card lays its name the same way.
        camera = tiles[tiles.index('inline bool render_camera_card('):]
        self.assertIn('set_text_align(w.title,LV_TEXT_ALIGN_LEFT);', camera)
        self.assertIn('lv_obj_set_pos(w.title,0,height-name_h);', camera)


class OneConnectionAtATime(unittest.TestCase):
    """A camera opened full screen streams after the page's live tiles have ended, never beside them: an S3 has internal
    RAM for one stream's network buffers (docs/CAMERA.md, "Live on an ESP32-S3"). The full view is always the stream;
    stills only when it cannot open, and the log says so."""

    def test_the_full_view_waits_for_the_tiles_streams_to_end(self):
        tiles = (COMPONENT / 'runtime_tiles.h').read_text()
        begin = tiles[tiles.index('inline void live_begin(const std::string &link) {'):]
        begin = begin[:begin.index('\n}\n')]
        # Its own copy of the link first: live_tick hands it live_link_waiting, which it clears before it opens, and
        # opened with the cleared one the view asked ":80" and tried again 10 s later (0.4.91, 0.4.92).
        steps = ['const std::string url = link;', 'live_tiles_halt();', 'if (live_view::ending()) {',
                 'live_link_waiting = url;', 'live_link_waiting.clear();', 'camera.stream.opened(live_view::open(url,']
        self.assertEqual([begin.index(step) for step in steps], sorted(begin.index(step) for step in steps))
        self.assertNotIn('open(link', begin)
        # A view beside a stream still ending only where the engine holds a second (a P4); an S3 waits (2026-10-30).
        self.assertIn('return !live_view::ending() || (live_view::beside() && now - live_link_waiting_at >= LIVE_LINK_WAIT_MS);',
                      tiles)
        self.assertIn('bool beside() { return picture_engine::limits().streams > 1; }',
                      (COMPONENT / 'live_view.cpp').read_text())
        self.assertIn('the full view could not stream', begin)
        self.assertIn('constexpr uint32_t LIVE_LINK_WAIT_MS = 2000;', tiles)
        tick = tiles[tiles.index('inline void live_tick() {'):]
        self.assertIn('live_begin(live_link_waiting);', tick[:tick.index('live_view::tick(')])
        # A closed stream counts until the tick frees it, its connection and its memory with it.
        live = (COMPONENT / 'live_view.cpp').read_text()
        ending = live[live.index('bool ending() {'):live.index('static void report(')]
        self.assertIn('s->stopping.load(', ending)


if __name__ == '__main__':
    unittest.main()
