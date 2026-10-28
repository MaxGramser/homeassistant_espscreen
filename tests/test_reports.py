"""My screen doesn't work right (app 0.4.91): the troubleshooting report, reports.py and redaction.py."""
import asyncio
import importlib.util
import io
import logging
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import redaction  # noqa: E402
import reports  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha


class Redaction(unittest.TestCase):
    def test_secrets_addresses_and_names_leave_a_log_line(self):
        text = ('wifi: ssid: MyHome password: hunter2\n[I][api:120] Connected to 192.168.1.23 (fe80::1a2b:3c4d) mac AA:BB:CC:DD:EE:FF\n'
                'noise_psk: "abcDEF123=" key: Zm9v\nlatitude: 52.37 longitude=4.89\nOffice 1 @ 10.0.0.5 at 10:40:25 version 2026.9.0 idf v5.5.5')
        out = redaction.redact_text(text, names=['Office 1', 'office-1'])
        for secret in ('MyHome', 'hunter2', '192.168.1.23', 'fe80::1a2b:3c4d', 'AA:BB:CC:DD:EE:FF', 'abcDEF123=', 'Zm9v', '52.37', '4.89', 'Office 1', '10.0.0.5'):
            self.assertNotIn(secret, out, secret)
        self.assertIn('[I][api:120] Connected to [ip]', out)
        self.assertIn('<screen> @ [ip] at 10:40:25 version 2026.9.0 idf v5.5.5', out)

    def test_a_json_document_redacts_the_keys_home_assistant_does_and_more(self):
        data = {'config': {'data': {'host': '10.0.0.5', 'noise_psk': 'x', 'device_name': 'office-1', 'port': 6053}, 'unique_id': 'aa:bb:cc:dd:ee:ff'},
                'home_assistant': {'version': '2026.10.2', 'latitude': 1.5}, 'list': [{'password': 'p'}, 'fine']}
        out = redaction.redact_data(data, names=['office-1'])
        self.assertEqual(out['config']['data'], {'host': '**REDACTED**', 'noise_psk': '**REDACTED**', 'device_name': '<screen>', 'port': 6053})
        self.assertEqual(out['config']['unique_id'], '**REDACTED**')
        self.assertEqual(out['home_assistant'], {'version': '2026.10.2', 'latitude': '**REDACTED**'})
        self.assertEqual(out['list'], [{'password': '**REDACTED**'}, 'fine'])


class FakeScreenApi:
    """The parts of aioesphomeapi's APIClient a report's read of a screen's log takes, with a Debug mode switch."""

    def __init__(self, *args, with_switch=True, debug=False, **kwargs):
        self.with_switch, self.debug, self.commands, self.subscribed_with_debug = with_switch, debug, [], None

    async def connect(self, login=True):
        pass

    async def device_info(self):
        return None

    async def list_entities_services(self):
        SwitchInfo = type('SwitchInfo', (), {})
        switch = SwitchInfo()
        switch.object_id, switch.key = 'debug_mode', 7
        other = types.SimpleNamespace(object_id='dark_mode', key=3)
        return ([other, switch] if self.with_switch else [other]), []

    def subscribe_states(self, on_state):
        on_state(types.SimpleNamespace(key=3, state=True))
        on_state(types.SimpleNamespace(key=7, state=self.debug))

    def switch_command(self, key, state):
        self.commands.append((key, state))
        if key == 7:
            self.debug = state

    def subscribe_logs(self, on_log, log_level=None, dump_config=True):
        self.subscribed_with_debug = self.debug
        on_log(types.SimpleNamespace(message=b'[I][live:581]: stream 0: 15.5 pictures/s'))

    async def disconnect(self):
        pass


class DebugModeForTheLog(unittest.IsolatedAsyncioTestCase):
    """A screen logs its warnings and errors alone while its Debug mode is off (settings_screen.h); the report's read
    turns it on, reads, and turns it off again, and leaves alone a screen that was in Debug mode or has no switch."""

    async def read(self, **screen):
        made = []

        def client(*args, **kwargs):
            made.append(FakeScreenApi(**screen))
            return made[-1]

        fake = types.ModuleType('aioesphomeapi')
        fake.APIClient = client
        fake.LogLevel = types.SimpleNamespace(LOG_LEVEL_DEBUG=5)
        saved = sys.modules.get('aioesphomeapi')
        sys.modules['aioesphomeapi'] = fake
        try:
            lines, _ = await reports.screen_log('screen.local', None, 0.05, debug=True)
        finally:
            if saved is None:
                del sys.modules['aioesphomeapi']
            else:
                sys.modules['aioesphomeapi'] = saved
        return lines, made[0]

    async def test_debug_mode_is_on_for_the_read_and_off_after_it(self):
        lines, api = await self.read()
        self.assertEqual(api.commands, [(7, True), (7, False)])
        self.assertTrue(api.subscribed_with_debug)
        self.assertFalse(api.debug)
        self.assertEqual(lines, ['[I][live:581]: stream 0: 15.5 pictures/s'])

    async def test_a_screen_already_in_debug_mode_stays_in_it(self):
        _, api = await self.read(debug=True)
        self.assertEqual(api.commands, [])
        self.assertTrue(api.debug)

    async def test_a_screen_without_the_switch_is_read_as_it_is(self):
        lines, api = await self.read(with_switch=False)
        self.assertEqual(api.commands, [])
        self.assertEqual(len(lines), 1)


class HomeAssistantLog(unittest.TestCase):
    LOG = ('2026-10-23 10:40:20.001 INFO (MainThread) [homeassistant.setup] Setting up esphome\n'
           '2026-10-23 10:40:21.002 WARNING (MainThread) [aioesphomeapi.reconnect_logic] Can\'t connect to ESPHome API for office-1 @ 10.0.0.5: timeout\n'
           '2026-10-23 10:40:22.003 ERROR (MainThread) [homeassistant.components.esphome.manager] Office 1: [E][api:100] boom\n'
           'Traceback (most recent call last):\n  File "x.py", line 1\n'
           '2026-10-23 10:40:23.004 INFO (MainThread) [homeassistant.components.esphome.manager] Kitchen: fine\n'
           '2026-10-23 10:40:24.005 ERROR (MainThread) [homeassistant.components.hue] unrelated\n')

    def test_only_the_lines_about_this_screen_with_their_tracebacks(self):
        lines = reports.ha_log_lines(self.LOG, ['Office 1', 'office-1', '10.0.0.5'])
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith('2026-10-23 10:40:21'))
        self.assertIn('Traceback', lines[2])
        self.assertFalse(any('Kitchen' in l or 'hue' in l or 'setup' in l for l in lines))

    def test_the_full_report_keeps_every_esphome_line(self):
        lines = reports.ha_log_lines(self.LOG, ['Office 1'], everything=True)
        self.assertTrue(any('Kitchen' in l for l in lines))
        self.assertFalse(any('hue' in l for l in lines))

    def test_system_log_entries_become_text(self):
        text = reports.system_log_text([{'name': 'homeassistant.components.esphome.manager', 'message': ['a', 'b'], 'level': 'ERROR',
                                         'source': ['esphome/manager.py', 12], 'timestamp': 1_800_000_000, 'exception': 'Trace\n  x', 'count': 3},
                                        {'name': 'homeassistant.components.hue', 'message': ['c'], 'level': 'WARNING', 'timestamp': 1, 'count': 1}])
        self.assertIn('x3 esphome/manager.py:12', text)
        self.assertIn('  a\n  b\n  Trace\n    x', text)
        self.assertNotIn('hue', text)
        self.assertIn('hue', reports.system_log_text([{'name': 'homeassistant.components.hue', 'message': ['c'], 'level': 'WARNING', 'timestamp': 1}], everything=True))


class Crashes(unittest.TestCase):
    CRASH = ['[E][esp32.crash:430] *** CRASH DETECTED ON PREVIOUS BOOT ***', '[E][esp32.crash:440] Reason: Fault - LoadProhibited (cause 28)',
             '[E][esp32.crash:450] PC: 0x400d1234', '[E][esp32.crash:460] BT0: 0x400d5678', '[E][esp32.crash:470] Use: addr2line -pfiaC -e firmware.elf 0x400d1234',
             '[C][debug:020]   Reset Reason: exception/panic', '[I][app:100] ESPHome version 2026.9.0']

    def test_the_screens_own_prefix_keeps_the_reason_and_the_addresses(self):
        # The screen writes `[E][esp32.crash:437]:   Reason: ...`, a colon after the brackets, which the stored records
        # dropped: every report said "unknown" and had no address to decode (TR-4EFBDE, 2026-10-23).
        lines = ['[E][esp32.crash:432]: *** CRASH DETECTED ON PREVIOUS BOOT ***', '[E][esp32.crash:437]:   Reason: Task wdt',
                 '[E][esp32.crash:439]:   Crashed core: 1', '[E][esp32.crash:446]:   PC:  0x4FF039FC  (fault location)',
                 '[E][esp32.crash:355]:   BT0: 0x4FF039FC  (backtrace)', '[E][esp32.crash:471]: Use: addr2line -pfiaC -e firmware.elf 0x4FF039FC',
                 '[I][app:151]: ESPHome version 2026.9.0 compiled on 2026-10-23 12:06:01 +0200']
        crash = reports.crash_summary(lines, clock=lambda: 1_800_000_000)
        self.assertEqual(crash['reason'], 'Task wdt')
        self.assertEqual(len(crash['lines']), 6)
        self.assertIn('0x4FF039FC', ' '.join(crash['lines']))

    def test_the_main_loops_stack_at_a_task_watchdog_rides_with_the_crash(self):
        lines = self.CRASH[:3] + ['[E][loop_record:044]: *** THE MAIN LOOP AT THE LAST TASK WATCHDOG *** (it waited; 2048 words of its stack in use; newest first)',
                                  '[E][loop_record:049]:   LOOP0: 0x4FF23BEA', '[E][loop_record:049]:   LOOP1: 0x4812ABCD',
                                  '[E][loop_record:054]:   Use: addr2line -pfiaC -e firmware.elf 0x4FF23BEA 0x4812ABCD',
                                  '[I][picture:368]: live: loaded, 21064 bytes in 73 ms']
        crash = reports.crash_summary(lines, clock=lambda: 1_800_000_000)
        self.assertEqual(len(crash['lines']), 7)
        self.assertTrue(any('LOOP1: 0x4812ABCD' in l for l in crash['lines']))
        self.assertFalse(any('picture' in l for l in crash['lines']))
        self.assertEqual(sorted(set(a for l in crash['lines'] for a in reports.ADDRESS.findall(l))),
                         ['0x400d1234', '0x4812ABCD', '0x4FF23BEA'])

    def test_the_esp_timer_task_at_a_task_watchdog_rides_with_the_crash(self):
        # loop_record.h: the esp_timer task, which runs the PPA watch, its state and stack beside the main loop's.
        lines = self.CRASH[:3] + ['[E][loop_record:070]: *** THE ESP_TIMER TASK AT THE LAST TASK WATCHDOG *** (it was blocked; newest first)',
                                  '[E][loop_record:073]:   TIMER0: 0x4FF0A564', '[E][loop_record:073]:   TIMER1: 0x4812D5D0',
                                  '[E][loop_record:078]:   Use: addr2line -pfiaC -e firmware.elf 0x4FF0A564 0x4812D5D0',
                                  '[I][picture:368]: live: loaded, 21064 bytes in 73 ms']
        crash = reports.crash_summary(lines, clock=lambda: 1_800_000_000)
        self.assertEqual(len(crash['lines']), 7)
        self.assertTrue(any('ESP_TIMER TASK' in l for l in crash['lines']))
        self.assertTrue(any('TIMER1: 0x4812D5D0' in l for l in crash['lines']))
        self.assertFalse(any('picture' in l for l in crash['lines']))

    def test_the_last_ppa_calls_ride_with_the_crash(self):
        # ppa_trace.h: the calls to the P4's PPA of the boot before, the one that never came back the stop.
        trace = ['[W][ppa_guard:120]: The last PPA calls of the previous boot, the newest last:',
                 '[W][ppa_guard:126]:   #1376 at 62271 ms, live_view: 492x269 turned 0 to 0,0, 1 piece(s), came back',
                 '[W][ppa_guard:126]:   #1377 at 62289 ms, loopTask: 872x6 turned 90 to 794,0, 0 piece(s), NEVER CAME BACK',
                 '[W][ppa_guard:094]: a turned copy of 46x4 would hang the 2D-DMA (DIG-734): copied in 2 pieces']
        crash = reports.crash_summary(self.CRASH[:3] + trace, clock=lambda: 1_800_000_000)
        self.assertTrue(any('NEVER CAME BACK' in l for l in crash['lines']))
        self.assertTrue(any('The last PPA calls' in l for l in crash['lines']))
        self.assertFalse(any('copied in 2 pieces' in l for l in crash['lines']))

    def test_the_internal_ram_of_the_boot_before_rides_with_the_crash_and_alone_is_none(self):
        heap = ['[E][heap_watch:105]: *** INTERNAL RAM ON PREVIOUS BOOT ***',
                '[E][heap_watch:106]:   Lowest: 20372 bytes free, 5321 s after boot',
                '[E][heap_watch:059]:   Failed: 3 allocations; the last 65536 bytes (caps 0x1800) in tcp_alloc, task tiT, '
                '18000 bytes internal free, 5400 s after boot',
                '[I][heap_watch:111]: Internal RAM: 248380 bytes free, 162344 at the lowest since boot (290 s after it), 0 failed allocations']
        crash = reports.crash_summary(self.CRASH[:3] + heap, clock=lambda: 1_800_000_000)
        self.assertEqual(len(crash['lines']), 6)
        self.assertTrue(any('Failed: 3 allocations' in l for l in crash['lines']))
        self.assertFalse(any('Internal RAM: 248380' in l for l in crash['lines']))
        # A restart that was no crash keeps its record to itself.
        self.assertIsNone(reports.crash_summary(heap, clock=lambda: 1_800_000_000))

    def test_what_an_abort_said_rides_with_the_crash(self):
        abort = ['[E][abort_record:047]: *** ABORT ON PREVIOUS BOOT *** (in task loopTask)',
                 '[E][abort_record:048]:   Details: assert failed: 0x48002d48',
                 '[E][abort_record:052]:   AT0: 0x4FF19D94', '[E][abort_record:052]:   AT1: 0x480D3270',
                 '[E][abort_record:057]:   Use: addr2line -pfiaC -e firmware.elf 0x4FF19D94 0x480D3270']
        crash = reports.crash_summary(self.CRASH[:3] + abort, clock=lambda: 1_800_000_000)
        self.assertEqual(len(crash['lines']), 8)
        self.assertTrue(any('Details: assert failed: 0x48002d48' in l for l in crash['lines']))
        self.assertIn('0x480D3270', reports.ADDRESS.findall(' '.join(crash['lines'])))

    def test_a_crash_block_is_a_crash_and_a_power_on_is_not(self):
        crash = reports.crash_summary(self.CRASH, clock=lambda: 1_800_000_000)
        self.assertEqual(crash['reason'], 'Fault - LoadProhibited (cause 28)')
        self.assertEqual(crash['reset'], 'exception/panic')
        self.assertEqual(len(crash['lines']), 6)
        self.assertNotIn('ESPHome version', '\n'.join(crash['lines']))
        self.assertIsNone(reports.crash_summary(['[C][debug:020]   Reset Reason: power on', '[I][app:100] hello']))
        self.assertIsNone(reports.crash_summary(['[C][debug:020]   Reset Reason: Reboot request from ota']))
        watchdog = reports.crash_summary(['[C][debug:020]   Reset Reason: task watchdog'])
        self.assertEqual(watchdog['reason'], 'task watchdog')

    def test_an_assert_address_counts_and_the_elf_sha_is_kept(self):
        crash = reports.crash_summary(['assert failed: 0x48016bb4', 'MEPC    : 0x4ff097d4  RA      : 0x4ff093a0', 'ELF file SHA256: 46e622f5f'])
        self.assertEqual(crash['elf'], '46e622f5f')
        self.assertEqual(crash['reason'], 'unknown')

    def test_the_store_counts_a_week_and_keeps_ten(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = reports.CrashStore(Path(tmp) / 'crashes.json')
            now = 1_800_000_000
            for i in range(12):
                store.add('text.screen', {'at': reports.now_iso(lambda: now - i * 86400), 'reason': f'r{i}', 'lines': []})
            last = store.last('text.screen', clock=lambda: now)
            self.assertEqual(last['reason'], 'r11')
            self.assertEqual(len(store.record('text.screen')['crashes']), 10)
            again = reports.CrashStore(Path(tmp) / 'crashes.json')
            self.assertEqual(len(again.record('text.screen')['crashes']), 10)
            self.assertEqual(again.last('text.screen', clock=lambda: now + 20 * 86400)['count'], 0)

    def test_decoding_without_an_elf_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            decoder = reports.Decoder(tmp)
            decoded, why = asyncio.run(decoder.decode('office-1', 'esp32p4', self.CRASH))
            self.assertEqual((decoded, why), ([], 'no_elf'))
            elf = Path(tmp) / 'build' / 'office-1' / 'build' / 'firmware.elf'
            elf.parent.mkdir(parents=True)
            elf.write_bytes(b'not an elf')
            decoded, why = asyncio.run(decoder.decode('office-1', 'esp32p4', self.CRASH, expected_sha='000000000'))
            self.assertEqual((decoded, why), ([], 'elf_mismatch'))


class Cleaning(unittest.TestCase):
    def test_note_and_email(self):
        self.assertIsNone(reports.clean_note('  '))
        self.assertEqual(reports.clean_note(' hi '), 'hi')
        with self.assertRaises(ValueError):
            reports.clean_note('x' * 2001)
        self.assertEqual(reports.clean_email(' a@b.co '), 'a@b.co')
        self.assertIsNone(reports.clean_email(''))
        with self.assertRaises(ValueError):
            reports.clean_email('not an address')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class PluginLines(unittest.TestCase):
    """report.md names the plugins the app installed and the ones the screen's hello said it runs; a screen that said
    no hello while the report was made (it was restarting: TR-4EFBDE, nine plugins, "none") has the installed ones
    stand in, and the report says so."""
    INSTALLED = [{'id': 'buienradar', 'version': '0.3.6', 'state': 'active'}, {'id': 'timers', 'version': '0.2.1', 'state': 'failed'}]

    def test_a_hello_lists_what_runs_beside_what_is_installed(self):
        lines = reports.Reports._plugin_lines({'plugins_installed': self.INSTALLED, 'plugins_source': 'hello',
                                               'plugins': [{'id': 'buienradar', 'version': '0.3.6'}]})
        self.assertEqual(lines, ['- Plugins installed: buienradar 0.3.6, timers 0.2.1 (failed)',
                                 "- Plugins running (the screen's hello): buienradar 0.3.6"])

    def test_without_a_hello_the_installed_ones_stand_in_and_the_report_says_so(self):
        summary = {'plugins_installed': self.INSTALLED, 'plugins_source': 'installed',
                   'plugins': reports.Reports._plugin_summary(self.INSTALLED)}
        self.assertEqual(summary['plugins'], [{'id': 'buienradar', 'version': '0.3.6'}, {'id': 'timers', 'version': '0.2.1'}])
        self.assertEqual(reports.Reports._plugin_lines(summary)[1],
                         "- Plugins running (the screen's hello): not heard (the screen said no hello while the report was made; the installed ones stand in)")

    def test_a_screen_without_plugins_says_none_twice(self):
        self.assertEqual(reports.Reports._plugin_lines({'plugins': [], 'plugins_installed': [], 'plugins_source': None}),
                         ['- Plugins installed: none', "- Plugins running (the screen's hello): none"])


class DeviceSensors(unittest.TestCase):
    """The firmware's diagnostic sensors ride in the report; on an ESP32-P4 that includes what its Wi-Fi co-processor
    runs (wifi_chip.h), so the reports tell which C6 firmwares are out there."""

    def test_the_wifi_co_processor_rides_along_and_other_devices_do_not(self):
        registry = [{'entity_id': 'sensor.a_heap_free', 'original_name': 'Heap Free', 'device_id': 'a'},
                    {'entity_id': 'text_sensor.a_wifi_co_processor', 'original_name': 'Wi-Fi co-processor', 'device_id': 'a'},
                    {'entity_id': 'text_sensor.b_wifi_co_processor', 'original_name': 'Wi-Fi co-processor', 'device_id': 'b'},
                    {'entity_id': 'sensor.a_other', 'original_name': 'Something else', 'device_id': 'a'}]
        states = {'sensor.a_heap_free': {'state': '236132.0'},
                  'text_sensor.a_wifi_co_processor': {'state': 'ESP-Hosted 2.3.2 (host 2.12.12)'},
                  'text_sensor.b_wifi_co_processor': {'state': 'ESP-Hosted 2.12.12 (host 2.12.12)'}}
        service = reports.Reports.__new__(reports.Reports)
        service.manager = types.SimpleNamespace(ha=types.SimpleNamespace(registry=registry, states=states))
        self.assertEqual(service._device_sensors({'device_id': 'a'}),
                         {'heap free': '236132.0', 'wi-fi co-processor': 'ESP-Hosted 2.3.2 (host 2.12.12)'})


class TheRoute(unittest.IsolatedAsyncioTestCase):
    async def test_a_report_is_collected_read_downloaded_and_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            esphome = Path(tmp) / 'esphome'
            esphome.mkdir()
            (esphome / 'office-1.yaml').write_text('esphome:\n  name: office-1\n  friendly_name: Office 1\napi:\n  encryption:\n    key: "c2VjcmV0a2V5"\n'
                                                   'wifi:\n  ssid: MyHome\n  password: hunter2\npackages:\n  screen: github://x/packages/guition.yaml@dev\n')
            (data / 'screens.json').write_text(json.dumps({'version': 1, 'screens': {'text.screen': {'title': 'Office', 'tiles': []}}}))
            import os
            os.environ['ESPHOME_CONFIG'] = str(esphome)
            try:
                ha = fake_ha()
                ha.registry.append({'entity_id': 'sensor.ip', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd1'})
                ha.states['sensor.ip'] = {'state': '10.0.0.5'}
                ha.registry.append({'entity_id': 'sensor.boot', 'platform': 'esphome', 'original_name': 'Last boot', 'device_id': 'd1'})
                ha.states['sensor.boot'] = {'state': '2026-10-23T08:00:00+00:00'}
                ha.session, ha.base, ha.token = None, None, None

                async def request(kind, **data):
                    if kind == 'system_log/list':
                        return [{'name': 'homeassistant.components.esphome.manager', 'message': ['Office 1: boom at 10.0.0.5'], 'level': 'ERROR', 'timestamp': 1, 'count': 1}]
                    raise ConnectionError('no')
                ha.request = request
                manager = Manager(ha, data / 'screens.json')
                captured, gate = {}, asyncio.Event()

                # Two plugins the app installed on the screen; the screen says hello only while its log is being read
                # (it was restarting as the report began), so the report must ask once more after the log.
                for record in ({'id': 'buienradar', 'version': '0.3.6', 'ref': 'd249c2e', 'state': 'active', 'source': 'index'},
                               {'id': 'timers', 'version': '0.2.1', 'ref': '857fb48', 'state': 'active', 'source': 'index'}):
                    manager.plugins.store.put('text.screen', record)

                async def fake_screen_log(host, key, seconds, **kw):
                    captured['host'], captured['key'] = host, key
                    if 'hello' not in captured:  # the first report's screen comes back while its log is read
                        captured['hello'] = True
                        manager.page_senders['text.screen'] = types.SimpleNamespace(
                            plugin_api='0.18', plugins=[{'id': 'timers', 'version': '0.2.1', 'tiles': ['timer']}])
                    await gate.wait()
                    return Crashes.CRASH + ['[I][wifi:200] IP 10.0.0.5 MAC AA:BB:CC:DD:EE:FF ssid: MyHome'], None
                reports.screen_log = fake_screen_log
                sent = []

                async def transport(token, fields, blob, filename):
                    sent.append((token, fields, blob, filename))
                    return {'state': 'sent', 'reference': 'TR-7K3M9Q', 'expires_at': '2026-11-22T00:00:00Z', 'retention_days': 30}
                manager.reports.transport = transport
                async with TestClient(TestServer(create_app(manager, True))) as client:
                    csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                    status = await (await client.get('/api/screens/text.screen/report')).json()
                    self.assertEqual((status['ready'], status['blockers'], status['crash'], status['last']), (True, [], None, None))
                    started = await client.post('/api/screens/text.screen/report', headers={'X-Screen-CSRF': csrf}, json={'depth': 'basic'})
                    self.assertEqual(started.status, 202)
                    id = (await started.json())['id']
                    busy = await (await client.get('/api/screens/text.screen/report')).json()
                    self.assertIn('collecting', busy['blockers'], await (await client.get(f'/api/reports/{id}')).json())
                    gate.set()
                    for _ in range(100):
                        view = await (await client.get(f'/api/reports/{id}')).json()
                        if view['state'] != 'collecting':
                            break
                        await asyncio.sleep(0.05)
                    self.assertEqual(view['state'], 'ready', view)
                    self.assertEqual((captured['host'], captured['key']), ('10.0.0.5', 'c2VjcmV0a2V5'))
                    names = [f['name'] for f in view['files']]
                    self.assertEqual(names[:3], ['report.md', 'summary.json', 'profile.yaml'])
                    self.assertIn('screen.log', names)
                    self.assertIn('home-assistant.log', names)
                    self.assertIn('addon.log', names)
                    self.assertEqual(view['summary']['board'], 'guition')
                    self.assertEqual(view['summary']['crash']['reason'], 'Fault - LoadProhibited (cause 28)')
                    self.assertIn('no_elf', view['warnings'])
                    self.assertEqual(view['summary']['plugins'], [{'id': 'timers', 'version': '0.2.1'}])
                    facts = await (await client.get(f'/api/reports/{id}/files/report.md')).text()
                    self.assertIn('- Plugins installed: buienradar 0.3.6, timers 0.2.1\n', facts)
                    self.assertIn("- Plugins running (the screen's hello): timers 0.2.1\n", facts)
                    data_json = json.loads(await (await client.get(f'/api/reports/{id}/files/summary.json')).text())
                    self.assertEqual((data_json['plugins_source'], len(data_json['plugins_installed'])), ('hello', 2))
                    profile = await (await client.get(f'/api/reports/{id}/files/profile.yaml')).text()
                    self.assertNotIn('hunter2', profile)
                    self.assertNotIn('MyHome', profile)
                    self.assertNotIn('c2VjcmV0a2V5', profile)
                    self.assertIn('<screen>', profile)
                    log = await (await client.get(f'/api/reports/{id}/files/screen.log')).text()
                    self.assertIn('CRASH DETECTED', log)
                    self.assertNotIn('10.0.0.5', log)
                    self.assertNotIn('AA:BB:CC:DD:EE:FF', log)
                    ha_log = await (await client.get(f'/api/reports/{id}/files/home-assistant.log')).text()
                    self.assertIn('<screen>: boom at [ip]', ha_log)
                    missing = await client.get(f'/api/reports/{id}/files/secrets.yaml')
                    self.assertEqual(missing.status, 400)
                    download = await client.get(f'/api/reports/{id}.zip')
                    self.assertEqual(download.status, 200)
                    self.assertTrue(download.headers['Content-Disposition'].startswith('attachment; filename="tessera-report-office-1-'))
                    with zipfile.ZipFile(io.BytesIO(await download.read())) as bundle:
                        self.assertEqual(bundle.namelist(), names)
                        self.assertIn('# Tessera troubleshooting report', bundle.read('report.md').decode())
                    refused = await client.post(f'/api/reports/{id}/send', headers={'X-Screen-CSRF': csrf}, json={'consent': False})
                    self.assertEqual(refused.status, 400)
                    bad_mail = await client.post(f'/api/reports/{id}/send', headers={'X-Screen-CSRF': csrf}, json={'consent': True, 'email': 'nope'})
                    self.assertEqual(bad_mail.status, 400)
                    self.assertEqual(sent, [])
                    answer = await (await client.post(f'/api/reports/{id}/send', headers={'X-Screen-CSRF': csrf},
                                                      json={'consent': True, 'note': 'It reboots when Video opens.', 'email': 'me@example.com', 'remember_email': True})).json()
                    self.assertEqual(answer, {'state': 'sent', 'reference': 'TR-7K3M9Q', 'expires_at': '2026-11-22T00:00:00Z'})
                    [(token, fields, blob, filename)] = sent
                    self.assertRegex(token, r'[0-9a-f]{64}')
                    self.assertEqual((fields['board_id'], fields['depth'], fields['consent'], fields['note'], fields['email']),
                                     ('guition', 'basic', 'true', 'It reboots when Video opens.', 'me@example.com'))
                    self.assertEqual(fields['firmware_version'], '0.2.104')
                    summary = json.loads(fields['summary'])
                    self.assertEqual(summary['crash']['reason'], 'Fault - LoadProhibited (cause 28)')
                    self.assertEqual(summary['files'], names)
                    self.assertTrue(zipfile.is_zipfile(io.BytesIO(blob)))
                    after = await (await client.get('/api/screens/text.screen/report')).json()
                    self.assertEqual(after['last']['reference'], 'TR-7K3M9Q')
                    self.assertEqual(after['email'], 'me@example.com')
                    self.assertEqual(after['crash']['reason'], 'Fault - LoadProhibited (cause 28)')
                    self.assertEqual(after['crash']['count'], 1)
                    # The feedback key of the board is the bearer, and it stays the same for a later answer.
                    self.assertEqual(json.loads((data / 'feedback.json').read_text())['boards']['d1']['token'], token)
                    # A restart of the app keeps the sent report and its reference (index.json beside the zips).
                    again = reports.Reports(manager, data)
                    self.assertEqual(again.status('text.screen', manager.screen('text.screen'))['last']['reference'], 'TR-7K3M9Q')
                    self.assertEqual(again.file(id, 'report.md'), manager.reports.file(id, 'report.md'))
                    logging.getLogger().removeHandler(again.buffer)
                    # A screen that says no hello at all while its report is made: the installed plugins stand in, and
                    # the report says they do.
                    manager.page_senders.pop('text.screen')
                    second = (await (await client.post('/api/screens/text.screen/report', headers={'X-Screen-CSRF': csrf},
                                                       json={'depth': 'basic'})).json())['id']
                    for _ in range(100):
                        view = await (await client.get(f'/api/reports/{second}')).json()
                        if view['state'] != 'collecting':
                            break
                        await asyncio.sleep(0.05)
                    self.assertEqual(view['state'], 'ready', view)
                    self.assertEqual(view['summary']['plugins'], [{'id': 'buienradar', 'version': '0.3.6'}, {'id': 'timers', 'version': '0.2.1'}])
                    facts = await (await client.get(f'/api/reports/{second}/files/report.md')).text()
                    self.assertIn("- Plugins running (the screen's hello): not heard (the screen said no hello", facts)
                    self.assertEqual(json.loads(await (await client.get(f'/api/reports/{second}/files/summary.json')).text())['plugins_source'], 'installed')
                    gone = await client.delete(f'/api/reports/{id}', headers={'X-Screen-CSRF': csrf})
                    self.assertEqual(gone.status, 204)
                    self.assertEqual((await client.get(f'/api/reports/{id}')).status, 400)
            finally:
                os.environ.pop('ESPHOME_CONFIG', None)

    async def test_a_screen_without_a_profile_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            os.environ['ESPHOME_CONFIG'] = str(Path(tmp) / 'none')
            try:
                manager = Manager(fake_ha(), Path(tmp) / 'screens.json')
                async with TestClient(TestServer(create_app(manager, True))) as client:
                    csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                    status = await (await client.get('/api/screens/text.screen/report')).json()
                    self.assertEqual((status['ready'], status['blockers']), (False, ['no_profile']))
                    refused = await client.post('/api/screens/text.screen/report', headers={'X-Screen-CSRF': csrf}, json={'depth': 'basic'})
                    self.assertEqual(refused.status, 400)
            finally:
                os.environ.pop('ESPHOME_CONFIG', None)


if __name__ == '__main__':
    unittest.main()
