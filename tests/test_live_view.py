"""The build facts of the pictures (components/smart_display/p4_build.py and engine_build.py; docs/PICTURE_ARCHITECTURE.md,
section 3.9): the network options a P4 gets less the screen's own, which picture engine, glass and streams a build gets
from the chip, LVGL and PSRAM (never a board), and that the wraps the P4 engine and the glass need are the ones the build
adds and the ones the code defines.

What the component adds to a build is read by running its own to_code() and _sockets() on a stand-in for ESPHome
(FakeBuild), for a P4, an S3 with and without PSRAM, a plain ESP32 and a host build. How a writer waits for the glass and
how the streams are counted is tests/test_live_view.cpp (glass::wait_as_writer, live_view::Census)."""
import asyncio
import contextlib
import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components' / 'smart_display'
spec = importlib.util.spec_from_file_location('smart_display_p4_build', COMPONENT / 'p4_build.py')
p4_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p4_build)
spec = importlib.util.spec_from_file_location('smart_display_engine_build', COMPONENT / 'engine_build.py')
engine_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine_build)


class _Loader(yaml.SafeLoader):
    """ESPHome's own tags (!include, !lambda, !secret) read as plain values: the structure is what is checked."""


_Loader.add_multi_constructor('!', lambda loader, suffix, node: loader.construct_scalar(node)
                              if isinstance(node, yaml.ScalarNode) else None)


class FakeBuild:
    """What the component asks of ESPHome while it is built for one chip, written down: the defines, the build flags,
    the sdkconfig options, the IDF components, the code it adds and the sockets it counts. `variant` as ESPHome names it
    ('ESP32P4'), or None for a host build."""

    def __init__(self, variant, lvgl=True, psram=True, own=None):
        self.defines, self.flags, self.components, self.added, self.sockets = [], [], [], [], []
        self.sdkconfig = {}
        config = {}
        if variant:
            config['esp32'] = {'framework': {'sdkconfig_options': dict(own or {})}}
        if lvgl:
            config['lvgl'] = [{'id': 'lvgl_component'}]
        if psram:
            config['psram'] = {}
        self.config = config
        core = types.SimpleNamespace(is_esp32=variant is not None, config=config,
                                     data={'esp32': {'flash_size': '16MB'}})
        codegen = types.SimpleNamespace(
            add_define=lambda name, value=None: self.defines.append(name),
            add_build_flag=self.flags.append, add_global=lambda statement: None, RawStatement=lambda text: text,
            RawExpression=lambda text: text, add=self.added.append, get_variable=self._variable)
        validation = types.SimpleNamespace(Schema=lambda schema: schema, Optional=lambda key, default=None: key,
                                           positive_int=int, string_strict=str, int_=int, Invalid=ValueError)
        esp32 = types.SimpleNamespace(
            get_esp32_variant=lambda: variant, KEY_ESP32='esp32', KEY_FLASH_SIZE='flash_size',
            add_idf_sdkconfig_option=self.sdkconfig.__setitem__,
            add_idf_component=lambda name, ref: self.components.append((name, ref)))
        socket = types.SimpleNamespace(consume_sockets=lambda count, owner: lambda conf: self.sockets.append(count))
        names = {
            'esphome': {}, 'esphome.codegen': vars(codegen), 'esphome.config_validation': vars(validation),
            'esphome.core': {'CORE': core, 'ID': object, 'HexInt': int},
            'esphome.components': {}, 'esphome.components.socket': vars(socket), 'esphome.components.esp32': vars(esp32),
            'esphome.components.esp32.const': {'VARIANT_ESP32P4': 'ESP32P4'},
            'esphome.final_validate': {'full_config': types.SimpleNamespace(get=lambda: config)},
            'esphome.const': {'CONF_ID': 'id'},
        }
        self.modules = {name: types.ModuleType(name) for name in names}
        for name, attributes in names.items():
            for key, value in attributes.items():
                setattr(self.modules[name], key, value)
            parent, _, child = name.rpartition('.')
            if parent:
                setattr(self.modules[parent], child, self.modules[name])

    @staticmethod
    async def _variable(name):
        return name

    @contextlib.contextmanager
    def component(self):
        """components/smart_display as ESPHome loads it, with this build's ESPHome standing in."""
        with mock.patch.dict(sys.modules, self.modules):
            spec = importlib.util.spec_from_file_location('smart_display_under_test', COMPONENT / '__init__.py',
                                                          submodule_search_locations=[str(COMPONENT)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            yield module

    def run(self):
        with self.component() as component:
            asyncio.run(component.to_code({'language': 'en', 'camera_orientation': 0}))
            component.FINAL_VALIDATE_SCHEMA({})
            self.diagnostic = component.DIAGNOSTIC_WRAPS
        return self


def wraps(names):
    return [f'-Wl,--wrap={name}' for name in names]


class P4Build(unittest.TestCase):
    def test_the_component_applies_them_on_a_p4_alone(self):
        # A P4 with LVGL and PSRAM: its network, the P4 engine's defines and wraps, LVGL bound to the glass.
        p4 = FakeBuild('ESP32P4').run()
        self.assertEqual(p4.sdkconfig, p4_build.P4_NETWORK)
        engine = engine_build.ENGINES['p4']
        for define in engine['defines']:
            self.assertIn(define, p4.defines)
        self.assertEqual(p4.flags, wraps(p4.diagnostic) + wraps(engine['wraps']), 'the wraps come from the tables alone')
        self.assertEqual(p4.components, [])
        self.assertEqual(p4.added, ['glass::bind(lvgl_component)'])
        # An S3 with LVGL and PSRAM: the S3 engine and its decoder component, none of the P4's network.
        s3 = FakeBuild('ESP32S3').run()
        self.assertEqual(s3.sdkconfig, {})
        self.assertEqual(s3.flags, wraps(s3.diagnostic) + wraps(engine_build.ENGINES['s3']['wraps']))
        self.assertEqual(s3.components, [('espressif/esp_new_jpeg', '1.0.2')])
        self.assertEqual(s3.added, ['glass::bind(lvgl_component)'])
        # Without PSRAM, a plain ESP32 (a CYD) and a host build: no engine, no glass, no streams.
        for build in (FakeBuild('ESP32S3', psram=False), FakeBuild('ESP32'), FakeBuild('ESP32P4', lvgl=False)):
            build.run()
            self.assertEqual(build.flags, wraps(build.diagnostic), 'every ESP32 keeps what an abort said')
            self.assertFalse(set(build.defines) & {'USE_LIVE_VIEW', 'PICTURE_ENGINE_P4', 'PICTURE_ENGINE_S3', 'GLASS_DSI',
                                                   'GLASS_RGB'})
            self.assertEqual((build.components, build.added), ([], []))
        self.assertEqual(FakeBuild('ESP32P4', lvgl=False).run().sdkconfig, p4_build.P4_NETWORK,
                         'the network is the chip\'s, LVGL or not')
        host = FakeBuild(None).run()
        self.assertEqual((host.flags, host.sdkconfig, host.components, host.added), ([], {}, [], []))
        # A screen's own sdkconfig_options keep the last word.
        own = FakeBuild('ESP32P4', own={'CONFIG_LWIP_TCP_WND_DEFAULT': '32768'}).run()
        self.assertNotIn('CONFIG_LWIP_TCP_WND_DEFAULT', own.sdkconfig)
        self.assertEqual(own.sdkconfig['CONFIG_LWIP_TCP_SND_BUF_DEFAULT'], 65534)

    def test_every_p4_board_waits_twenty_seconds_on_its_main_loop(self):
        # The main loop's waits for the C6's answers (5 s each in esp_hosted) must fit the task watchdog, or a busy SDIO
        # link restarts the screen instead of failing a call (2026-10-24, the D1001, a Tab5 and a Guition 10.1).
        core = yaml.load((ROOT / 'packages/hardware/esp32p4-core.yaml').read_text(), Loader=_Loader)
        self.assertEqual(core['esp32'].get('watchdog_timeout'), '20s',
                         'packages/hardware/esp32p4-core.yaml sets the task watchdog to 20s for every P4 board')
        # A board is a P4 only through that file, so none goes without it, and none sets a watchdog of its own.
        for package in sorted((ROOT / 'packages').rglob('*.yaml')):
            parsed = yaml.load(package.read_text(), Loader=_Loader)
            esp32 = parsed.get('esp32') if isinstance(parsed, dict) else None
            if not isinstance(esp32, dict) or package.name == 'esp32p4-core.yaml':
                continue
            self.assertNotEqual(str(esp32.get('variant', '')).lower(), 'esp32p4',
                                f'{package.relative_to(ROOT)} names the P4 itself: a P4 board includes '
                                'packages/hardware/esp32p4-core.yaml instead, which names the chip and its watchdog')
            if 'esp32p4-core.yaml' in str(parsed.get('packages')):
                self.assertNotIn('watchdog_timeout', esp32, f'{package.relative_to(ROOT)} keeps the task watchdog '
                                                            'esp32p4-core.yaml sets')

    def test_the_screens_own_options_keep_the_last_word(self):
        self.assertEqual(p4_build.network_options({}), p4_build.P4_NETWORK)
        # The window and the send buffer of 64 KB, all of it in PSRAM first, and each packet copied out of the driver's.
        self.assertEqual(p4_build.P4_NETWORK['CONFIG_LWIP_TCP_WND_DEFAULT'], 65534)
        self.assertTrue(p4_build.P4_NETWORK['CONFIG_LWIP_L2_TO_L3_COPY'])
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
        # The build adds the wraps the tables name and nothing else (test_the_component_applies_them_on_a_p4_alone); the
        # engine's and the glass's own files define them, and no file defines one the table does not name.
        defined = set()
        for name in ('glass_dsi.cpp', 'glass_dsi_refresh.cpp', 'ppa_guard.cpp', 'live_view.cpp', 'picture_engine_p4.cpp'):
            defined |= set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / name).read_text()))
        self.assertEqual(defined, set(engine_build.ENGINES['p4']['wraps']))
        s3 = set()
        for name in ('glass_rgb.cpp', 'picture_engine_s3.cpp'):
            s3 |= set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / name).read_text()))
        self.assertEqual(s3, set(engine_build.ENGINES['s3']['wraps']))
        # The diagnostic wraps every ESP32 gets come from their own table, and abort_record.cpp defines exactly those.
        with FakeBuild('ESP32').component() as component:
            diagnostic = set(component.DIAGNOSTIC_WRAPS)
        self.assertEqual(set(re.findall(r'__wrap_(\w+)\(', (COMPONENT / 'abort_record.cpp').read_text())), diagnostic)
        # The defines the table gives are the ones the code builds under: the engines in picture_engine.h and their own
        # files, the glasses in glass.h and their own files, the streams in live_view.h and live_view.cpp.
        for define, names in (('PICTURE_ENGINE_P4', ('picture_engine.h', 'picture_engine_p4.cpp', 'ppa_guard.cpp')),
                              ('PICTURE_ENGINE_S3', ('picture_engine.h', 'picture_engine_s3.cpp')),
                              ('GLASS_DSI', ('glass.h', 'glass_dsi.cpp', 'glass_dsi_refresh.cpp')),
                              ('GLASS_RGB', ('glass.h', 'glass_rgb.cpp')),
                              ('USE_LIVE_VIEW', ('live_view.h', 'live_view.cpp'))):
            for name in names:
                self.assertIn(define, (COMPONENT / name).read_text(), name)


class Sockets(unittest.TestCase):
    """A screen that streams counts its streams, downloads and talk into ESPHome's socket total (smart_display/__init__.py,
    _sockets): the count follows live_view.h's MAX_STREAMS, and the downloads are picture_fetch's slots."""

    def test_the_count_follows_the_code(self):
        p4, s3 = FakeBuild('ESP32P4').run(), FakeBuild('ESP32S3').run()
        with FakeBuild('ESP32P4').component() as component:
            # The streams, the downloads, the talk, and a direct call's own server (call_serve.h): its door and its viewer.
            counts = (component.P4_STREAM_SOCKETS, component.PICTURE_SOCKETS, component.TALK_SOCKETS, component.CALL_SOCKETS)
        self.assertEqual(p4.sockets, [sum(counts)])
        self.assertEqual(s3.sockets, [sum(counts)], 'an S3 that streams counts the same sockets')
        for build in (FakeBuild('ESP32'), FakeBuild('ESP32S3', psram=False), FakeBuild(None)):
            self.assertEqual(build.run().sockets, [], 'a screen without streams counts none')
        streams = re.search(r'constexpr int MAX_STREAMS = (\d+);', (COMPONENT / 'live_view.h').read_text())
        self.assertEqual(counts[0], int(streams[1]), 'P4_STREAM_SOCKETS is live_view::MAX_STREAMS')
        slots = re.findall(r'^Slot &(\w+)\(\);', (COMPONENT / 'picture_fetch.h').read_text(), re.M)
        self.assertEqual(counts[1], len(slots), 'PICTURE_SOCKETS is picture_fetch\'s slots, one download each')


class ChipFactsBehindTheEngine(unittest.TestCase):
    """The P4's facts live behind the picture engine (docs/PLATFORM_PLAN.md 3.2): outside the engine's own files the
    code names no sixteenths, no PPA, no JPEG driver and no panel driver; it asks picture_engine (limits, fit, cut,
    blit) and glass, whose panel files (glass_dsi.cpp, glass_dsi_refresh.cpp, glass_rgb.cpp) are the only ones to name ESP-IDF's panels.
    Comments and strings may name them."""
    ALLOWED = {'picture_engine.h', 'picture_engine_p4.cpp', 'ppa_guard.h', 'ppa_guard.cpp', 'picture_jpeg.h',
               'glass_dsi.cpp', 'glass_dsi_refresh.cpp', 'glass_rgb.cpp'}
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
    glass, 2 ms holding it"). Every writer waits at one priority: the order is glass::wait_as_writer and leave_as_writer,
    and the priorities live_view.h's static_asserts, both proven by tests/test_live_view.cpp. Here: that every writer
    goes through them."""

    def code(self, name):
        return ChipFactsBehindTheEngine.code((COMPONENT / name).read_text())

    def test_every_writer_of_the_glass_waits_at_the_writers_priority(self):
        # A task's priority changes only in the glass's writer helpers: anywhere else it would wait for the glass at its
        # own priority again, or stay raised after it let go.
        for path in sorted(COMPONENT.glob('*.[hc]*')):
            if path.suffix in ('.h', '.cpp') and 'vTaskPrioritySet' in self.code(path.name):
                for call in re.finditer(r'vTaskPrioritySet\(', self.code(path.name)):
                    line = self.code(path.name)[:call.start()].rsplit('\n', 1)[-1] + \
                        self.code(path.name)[call.start():].split('\n', 1)[0]
                    self.assertRegex(line, r'set_priority|\[\]\(unsigned priority\)',
                                     f'{path.name}: a task\'s priority is set only by the `set` it hands '
                                     'glass::wait_as_writer and leave_as_writer')
        for name, hold in (('live_view.cpp', 'glass::hold_counted'), ('picture_engine_p4.cpp', 'glass::hold();')):
            body = self.code(name)
            self.assertIn('glass::wait_as_writer(', body, f'{name} waits for the glass through glass::wait_as_writer')
            self.assertIn('glass::leave_as_writer(', body, f'{name} lets go of the glass through glass::leave_as_writer')
            self.assertEqual(body.count(hold), 1, f'{name} asks for the glass in one place, inside wait_as_writer')

    def test_a_streams_task_runs_at_the_streams_priority(self):
        # Every task live_view.cpp starts runs at STREAM_PRIORITY, below the wake word (live_view.h).
        live = self.code('live_view.cpp')
        starts = []
        for call in re.finditer(r'(?:psram_task::start|xTaskCreate\w*)\(', live):
            depth, at = 1, call.end()
            while depth:
                depth += {'(': 1, ')': -1}.get(live[at], 0)
                at += 1
            starts.append(live[call.end():at - 1])
        self.assertTrue(starts, 'live_view.cpp starts its streams\' tasks')
        for arguments in starts:
            self.assertIn('STREAM_PRIORITY', arguments, 'a stream\'s task starts at live_view::STREAM_PRIORITY')

    # glass: a still that took long on a P4 with live tiles says in the log how long it waited for the glass and how
    # long it held it, so a wait behind the streams shows.
    def test_a_slow_still_says_where_its_time_went(self):
        fetch = (COMPONENT / 'picture_fetch.cpp').read_text()
        slow = re.search(r'if \(took > SLOW_MS\)\s*ESP_LOGW\(([^;]*)\);', fetch)
        self.assertTrue(slow, 'picture_fetch.cpp warns of a still slower than SLOW_MS')
        for field in ('slot.waited_ms', 'slot.held_ms'):
            self.assertIn(field, slow.group(1), f'the slow still\'s line says {field}')


class LiveTileName(unittest.TestCase):
    """A live tile's name lies over its pictures as the picture card lays it (render_camera_card): the tile's font, left,
    at the bottom of the card's content, in the picture's ink. A copy of the card's own label lay dark and halfway up
    over every picture of a card that had no still yet and stood in its plain layout (a wallbox, 2026-10-28).

    The place is camera_view::name_box, which both the card and the live picture's copy ask, proven by
    tests/test_camera_view.cpp. Here: the rule that both ask it and that the copy is never the card's own label."""

    def test_the_card_and_the_live_name_lay_the_name_in_one_place(self):
        parts = {path.name: path.read_text() for path in COMPONENT.glob('*.h')}
        askers = sorted(name for name, code in parts.items() if 'camera_view::name_box(' in code)
        self.assertEqual(askers, ['live_spots_lvgl.h', 'runtime_tiles.h'],
                         'the picture card (render_camera_card) and the live name (live_name) both ask camera_view::name_box')
        # glass: on a screen with a live tile that has no still yet, its name lies at the bottom left over the picture in
        # the picture's ink, not dark and halfway up.
        for name, code in parts.items():
            self.assertNotIn('lv_snapshot_take(card->title', code, f'{name}: the live name is drawn off the glass, never a '
                                                                   'copy of the card\'s own label')


class OneConnectionAtATime(unittest.TestCase):
    """A camera opened full screen streams after the page's live tiles have ended, never beside them: an S3 has internal
    RAM for one stream's network buffers (docs/CAMERA.md, "Live on an ESP32-S3"). The full view is always the stream;
    stills only when it cannot open, and the log says so. How the streams are counted (one still ending counts, a second
    only where the engine holds one) is live_view::Census, room_for and beside, proven by tests/test_live_view.cpp."""

    def test_the_streams_are_counted_by_the_tested_rules(self):
        live = GlassTurns.code(self, 'live_view.cpp')
        for function, rule in (('bool room_for_another()', 'room_for(census(streams)'), ('bool beside()', 'beside(picture_engine'),
                               ('bool ending()', 'census(streams).ending')):
            body = re.search(re.escape(function) + r' \{([^\n]*)\}', live)
            self.assertTrue(body and rule in body.group(1), f'live_view.cpp\'s {function} answers through {rule}')

    def test_the_full_view_waits_by_the_tested_rule(self):
        # The wait itself (at once with no stream ending, beside one still ending only on a P4 and after 2 s, its own
        # copy of the link so it never opens an empty one) is live_view::ViewWait, proven by tests/test_live_view.cpp.
        # glass: a camera opened full screen from a page with a live tile streams once the tile's stream has ended, and
        # the page's tiles stop before the view's stream opens (live_begin halts them, then reads ending()); on an S3 the
        # log says the view waits, on a P4 that it opened beside the stream after 2 s.
        parts = {path.name: path.read_text() for path in COMPONENT.glob('*.h')}
        self.assertFalse([name for name, code in parts.items() if re.search(r'\blive_link_waiting\b', code)],
                         "the full view's waiting link lives in live_view::ViewWait alone")
        self.assertTrue([name for name, code in parts.items() if 'view_wait.begin(' in code], 'live_begin asks ViewWait::begin')

if __name__ == '__main__':
    unittest.main()
