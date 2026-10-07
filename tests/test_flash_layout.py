"""The wide partition table of a board with 4 MB of flash (app 0.4.56, firmware 0.33.1 of those boards; docs/FLASH_LAYOUT.md).

Three things must agree, and a screen out there pays when they don't: the table a build takes
(components/flash_layout/partitions-4mb-wide.csv), the numbers the firmware moves a screen by (flash_layout.h), and
what ESP Screen Manager does around it: the line in a screen's own YAML, the table after an update, and the bridge
for a firmware too large for the old table's slot. The bench run with a real board is in docs/FLASH_LAYOUT.md.
"""
import asyncio
import csv
import json
import re
import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import core  # noqa: E402
from core import FIRMWARE_VERSION, SHAPES, installation_yaml  # noqa: E402
import firmware as firmware_module  # noqa: E402
from firmware import Firmware, LenientLoader  # noqa: E402
from manager_fixtures import with_screen_grid  # noqa: E402

COMPONENT = ROOT / 'components/flash_layout'
MB4 = 4 * 1024 * 1024
# ESPHome's own table for 4 MB of flash with ESP-IDF (esphome/components/esp32, get_partition_csv): the sizes it
# writes, placed the way its partition tool places them. The first update slot starts at the next 64 KB.
ESPHOME_TABLE = {'otadata': (0x9000, 0x2000), 'phy_init': (0xB000, 0x1000), 'app0': (0x10000, 0x1C0000),
                 'app1': (0x1D0000, 0x1C0000), 'nvs': (0x390000, 0x70000)}
WIDE_BOARDS = sorted(board for board in profiles.BOARDS if profiles.wide_slots(board))


def load(text):
    return yaml.load(text, Loader=LenientLoader)


def wide_table():
    rows = csv.reader(line for line in (COMPONENT / 'partitions-4mb-wide.csv').read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith('#'))
    return {row[0].strip(): (row[1].strip(), row[2].strip(), int(row[3], 0), int(row[4], 0)) for row in rows}


def header_tables():
    text = (COMPONENT / 'flash_layout.h').read_text()
    found = {name: tuple(int(n, 0) for n in re.findall(r'0x[0-9A-Fa-f]+', body))
             for name, body in re.findall(r'constexpr Table (\w+)\{([^}]*)\}', text)}
    found['FIRST_SLOT'] = int(re.search(r'FIRST_SLOT = (0x[0-9A-Fa-f]+)', text)[1], 0)
    return found


class TheTable(unittest.TestCase):
    def test_it_is_a_table_the_bootloader_and_esphome_take(self):
        table = wide_table()
        self.assertEqual(list(table), ['otadata', 'phy_init', 'nvs', 'app0', 'app1', 'nvs_more'])
        end = 0x9000  # behind the bootloader and the table itself
        for name, (kind, subtype, offset, size) in table.items():
            self.assertGreaterEqual(offset, end, f'{name} overlaps what is before it')
            self.assertEqual(offset % 0x1000, 0, name)
            self.assertEqual(size % 0x1000, 0, name)
            if kind == 'app':
                self.assertEqual(offset % 0x10000, 0, f'{name}: an app starts on 64 KB')
            end = offset + size
        self.assertEqual(end, MB4, 'the table fills 4 MB and not a byte more')
        # What ESPHome's updater asks of a table it takes over Wi-Fi: two app slots, otadata, and "nvs".
        self.assertEqual([(table[n][0], table[n][1]) for n in ('app0', 'app1')], [('app', 'ota_0'), ('app', 'ota_1')])
        self.assertEqual(table['otadata'][:2], ('data', 'ota'))
        self.assertEqual(table['nvs'][:2], ('data', 'nvs'))
        self.assertEqual(table['app0'][3], table['app1'][3], 'both slots the same size')
        # ESP-IDF's settings code needs three pages and one spare.
        self.assertGreaterEqual(table['nvs'][3], 4 * 0x1000)

    def test_what_stays_where_it_was(self):
        """The bootloader's own data and the first slot start where ESPHome's table has them: a screen that runs from
        its first slot keeps running the same bytes when the table changes under it."""
        table = wide_table()
        for name in ('otadata', 'phy_init'):
            self.assertEqual(table[name][2:], ESPHOME_TABLE[name], name)
        self.assertEqual(table['app0'][2], ESPHOME_TABLE['app0'][0])
        self.assertGreater(table['app0'][3], ESPHOME_TABLE['app0'][1], 'the point of it: a wider slot')

    def test_the_settings_go_where_esphome_s_table_has_nothing(self):
        """The copy is made while the old table is in use, so its place must be free there."""
        offset, size = wide_table()['nvs'][2:]
        for name, (start, length) in ESPHOME_TABLE.items():
            self.assertFalse(start < offset + size and start + length > offset, f'the wide nvs lies in the old {name}')
        self.assertGreaterEqual(offset, 0x9000)

    def test_the_firmware_knows_the_same_numbers(self):
        table, header = wide_table(), header_tables()
        self.assertEqual(header['WIDE'], (table['nvs'][2], table['nvs'][3], table['app0'][3], table['app1'][2]))
        self.assertEqual(header['NARROW'], (*ESPHOME_TABLE['nvs'], ESPHOME_TABLE['app0'][1], ESPHOME_TABLE['app1'][0]))
        self.assertEqual(header['FIRST_SLOT'], table['app0'][2])
        self.assertEqual(Firmware.NARROW_SLOT, ESPHOME_TABLE['app0'][1])

    def test_esphome_still_writes_the_table_this_was_measured_against(self):
        """With ESPHome installed (the firmware checks): its own 4 MB table is the one NARROW describes."""
        try:
            from esphome.components import esp32
        except ImportError:
            self.skipTest('ESPHome is not installed here')
        self.assertEqual(esp32.IDF_NVS_SIZE, ESPHOME_TABLE['nvs'][1])
        self.assertEqual((esp32.OTADATA_SIZE, esp32.PHY_INIT_SIZE), (ESPHOME_TABLE['otadata'][1], ESPHOME_TABLE['phy_init'][1]))


class TheBoards(unittest.TestCase):
    def test_every_board_with_4_mb_and_no_other(self):
        self.assertTrue(WIDE_BOARDS)
        for board in profiles.BOARDS:
            self.assertEqual(profiles.wide_slots(board), profiles.flash_mb(board) <= 4, board)
            self.assertEqual(SHAPES[board]['wide_slots'], profiles.wide_slots(board), board)

    def test_their_entries(self):
        for board in profiles.BOARDS:
            wide = profiles.wide_slots(board)
            checkout = load((ROOT / 'checkout' / f'{board}.yaml').read_text())
            package = load((ROOT / 'packages' / f'{board}.yaml').read_text())
            self.assertEqual(checkout['ota'][0].get('allow_partition_access', False), wide, board)
            for entry in (checkout, package):
                self.assertEqual('flash_layout' in entry['external_components'][0]['components'], wide, board)

    def test_the_package_is_the_component_and_nothing_that_merges(self):
        """A package's `esphome: on_boot:` or `ota:` would take the place of the core's or lose against the screen's own
        (the first version of this did both); the component starts by itself."""
        package = load((ROOT / 'packages/hardware/flash-4mb.yaml').read_text())
        self.assertEqual(list(package), ['flash_layout', 'text_sensor'])
        self.assertEqual([sensor['name'] for sensor in package['text_sensor']], list(core.NAME_SCREEN_FLASH))

    def test_no_other_board_s_firmware_changes(self):
        """The component is its own, and what it says goes through a sensor of its own: nothing every board builds
        knows about it, so a board with more flash builds what it built before."""
        for path in [ROOT / 'packages/core.yaml', *sorted((ROOT / 'components/smart_display').glob('*.[hc]*'))]:
            self.assertNotIn('flash_layout', path.read_text(), path.name)

    def test_one_bridge_fits_them_all(self):
        """The bridge is built for a plain ESP32; every board that takes the wide table is one."""
        for board in WIDE_BOARDS:
            blocks = [load(path.read_text()).get('esp32') or {} for path in profiles.chain(profiles.BOARDS[board])]
            self.assertIn('esp32dev', [block.get('board') for block in blocks], board)
            self.assertIn('esp32', [str(block.get('variant')).lower() for block in blocks], board)
        for name in ('packages/bridge.yaml', 'checkout/bridge.yaml'):
            bridge = load((ROOT / name).read_text())
            self.assertNotIn('api', bridge, f'{name}: Home Assistant removes the entities a device stops offering')
            self.assertEqual((bridge['esp32']['board'], bridge['esp32']['variant']), ('esp32dev', 'esp32'), name)
            self.assertEqual(bridge['external_components'][0]['components'], ['flash_layout'], name)
            self.assertIn('logger', bridge)
            for key in ('display', 'lvgl', 'smart_display', 'captive_portal'):
                self.assertNotIn(key, bridge, name)
        text = (ROOT / 'packages/bridge.yaml').read_text()
        self.assertEqual(re.findall(r'!include (\S+)', text), ['hardware/esp-idf.yaml'])
        for name in ('packages/bridge.yaml', 'checkout/bridge.yaml'):
            bridge = load((ROOT / name).read_text())
            self.assertIn('flash_layout', bridge, name)
            self.assertNotIn('text_sensor', bridge, name)


OLD = '''# Keep this file safe: it contains the unique keys for this screen.
substitutions:
  DEVICE_NAME: "kitchen"
  DEVICE_FRIENDLY_NAME: "Kitchen"
  LANGUAGE: "nl"

esphome:
  name: "kitchen"
  friendly_name: "Kitchen"

packages:
  display:
    url: https://github.com/MaxGramser/homeassistant_espscreen
    ref: main
    files: [packages/BOARD.yaml]
    refresh: 0s
  local_overrides: !include kitchen.local.yaml

api:
  encryption:
    key: "c2VjcmV0LWtleS1mb3ItdGhlLWtpdGNoZW4tc2NyZWVuIQ=="
ota:
  - platform: esphome
    password: "kitchen-ota"
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
'''


class ANewScreen(unittest.TestCase):
    def test_its_yaml_lets_the_table_be_replaced_on_these_boards_alone(self):
        for board in profiles.BOARDS:
            data = load(installation_yaml({'board': board, 'name': 'hall', 'friendly_name': 'Hall'}))
            self.assertEqual(len(data['ota']), 1, board)
            self.assertEqual(data['ota'][0].get('allow_partition_access', False), profiles.wide_slots(board), board)
            self.assertEqual(data['ota'][0]['platform'], 'esphome')
            self.assertTrue(data['ota'][0]['password'])
            self.assertIn('ssid', data['wifi'])


class AScreenFromBefore(unittest.TestCase):
    def write(self, tmp, name, text):
        path = Path(tmp) / name
        path.write_bytes(text.encode())
        return path

    def test_the_line_is_added_and_nothing_else_changes(self):
        cases = {
            'cyd': OLD.replace('BOARD', 'cyd'),
            'cyd9342 crlf': OLD.replace('BOARD', 'cyd9342').replace('\n', '\r\n'),
            'hosyond40 four spaces': OLD.replace('BOARD', 'hosyond40')
                .replace('  - platform: esphome\n    password: "kitchen-ota"\n', '    - platform: esphome\n      password: "kitchen-ota"\n'),
            'cyd quoted, with a comment and a port': OLD.replace('BOARD', 'cyd')
                .replace('  - platform: esphome\n', '  - platform: "esphome"  # ours\n    port: 3232\n'),
            'cyd ota last': OLD.replace('BOARD', 'cyd').replace('ota:\n  - platform: esphome\n    password: "kitchen-ota"\n', '')
                + 'ota:\n  - platform: esphome\n    password: "kitchen-ota"\n',
            'cyd with a second platform': OLD.replace('BOARD', 'cyd')
                .replace('    password: "kitchen-ota"\n', '    password: "kitchen-ota"\n  - platform: web_server\n'),
        }
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, text) in enumerate(cases.items()):
                with self.subTest(name):
                    path = self.write(tmp, f'p{index}.yaml', text)
                    before = load(text)
                    self.assertTrue(firmware.allow_table_update(path.name))
                    out = path.read_bytes().decode()
                    self.assertEqual('\r\n' in out, '\r\n' in text, 'line ends stay as they were')
                    after = load(out)
                    ours = [item for item in after['ota'] if item['platform'] == 'esphome']
                    self.assertIs(ours[0]['allow_partition_access'], True)
                    for item in after['ota']:
                        item.pop('allow_partition_access', None)
                    self.assertEqual(after, before, 'only that one line')
                    self.assertEqual(len(out.splitlines()), len(text.splitlines()) + 1)
                    # A second build finds it done.
                    self.assertFalse(firmware.allow_table_update(path.name))
                    self.assertEqual(path.read_bytes().decode(), out)

    def test_what_it_leaves_alone(self):
        cases = {
            'a board with more flash': OLD.replace('BOARD', 'guition'),
            'said already': OLD.replace('BOARD', 'cyd').replace('    password: "kitchen-ota"\n', '    password: "kitchen-ota"\n    allow_partition_access: false\n'),
            'no ota of ours': OLD.replace('BOARD', 'cyd').replace('  - platform: esphome\n    password: "kitchen-ota"\n', '  - platform: web_server\n'),
            'an old ota block': OLD.replace('BOARD', 'cyd').replace('  - platform: esphome\n    password: "kitchen-ota"\n', '  password: "kitchen-ota"\n'),
            'two of ours': OLD.replace('BOARD', 'cyd').replace('    password: "kitchen-ota"\n', '    password: "kitchen-ota"\n  - platform: esphome\n    port: 3233\n'),
            'platform not first': OLD.replace('BOARD', 'cyd').replace('  - platform: esphome\n    password: "kitchen-ota"\n', '  - password: "kitchen-ota"\n    platform: esphome\n'),
            'not a screen of ours': OLD.replace('url: https://github.com/MaxGramser/homeassistant_espscreen', 'url: https://example.org/other').replace('BOARD', 'cyd'),
        }
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, text) in enumerate(cases.items()):
                with self.subTest(name):
                    path = self.write(tmp, f'q{index}.yaml', text)
                    self.assertFalse(firmware.allow_table_update(path.name))
                    self.assertEqual(path.read_bytes().decode(), text)

    def test_a_build_writes_it_and_a_table_does_not_touch_the_yaml(self):
        """Firmware.start adds the line before it builds; sending the table goes with the build that was made, so it
        changes nothing, and runs ESPHome's upload with --partition-table and nothing before it."""
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                firmware = Firmware(tmp, tmp)
                path = self.write(tmp, 'kitchen.yaml', OLD.replace('BOARD', 'cyd'))
                commands = []

                class Process:
                    returncode = 0
                    pid = 0
                    class stdout:
                        def __aiter__(self): return self
                        async def __anext__(self): raise StopAsyncIteration
                    stdout = stdout()
                    async def wait(self): return 0

                async def fake_exec(*cmd, **kwargs):
                    commands.append(list(cmd))
                    return Process()

                real_exec, real_which = asyncio.create_subprocess_exec, firmware_module.shutil.which
                asyncio.create_subprocess_exec = fake_exec
                firmware_module.shutil.which = lambda name: '/usr/bin/' + name
                firmware.retire_platformio = firmware.seed_cache = lambda *a, **k: asyncio.sleep(0)
                try:
                    firmware.start({'file': 'kitchen.yaml', 'action': 'build'})
                    await firmware.task
                    built = path.read_text()
                    self.assertIs(load(built)['ota'][0]['allow_partition_access'], True)
                    firmware.start({'file': 'kitchen.yaml', 'action': 'widen', 'target': '10.0.0.5'})
                    await firmware.task
                    self.assertEqual(path.read_text(), built)
                    with self.assertRaises(ValueError):
                        firmware.start({'file': 'kitchen.yaml', 'action': 'widen', 'target': '/dev/ttyUSB0'})
                finally:
                    asyncio.create_subprocess_exec, firmware_module.shutil.which = real_exec, real_which
                self.assertEqual(commands, [['esphome', 'compile', str(path.resolve())],
                                            ['esphome', 'upload', '--partition-table', str(path.resolve()), '--device', '10.0.0.5']])
                self.assertEqual(firmware.job['state'], 'success')
        asyncio.run(run())


class TheBridge(unittest.TestCase):
    def test_it_is_the_screen_s_name_wifi_and_ota_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            text = OLD.replace('BOARD', 'cyd').replace('  power_save_mode: none\n', '  power_save_mode: none\n  manual_ip:\n    static_ip: 10.0.0.9\n')
            path = Path(tmp) / 'kitchen.yaml'
            path.write_text(text)
            with self.assertRaises(ValueError, msg='not before the screen lets its table be replaced'):
                firmware.bridge('kitchen.yaml')
            self.assertTrue(firmware.allow_table_update('kitchen.yaml'))
            name = firmware.bridge('kitchen.yaml')
            self.assertEqual(name, 'kitchen.bridge.yaml')
            own, bridge = load(path.read_text()), load((Path(tmp) / name).read_text())
            self.assertEqual(set(bridge), {'substitutions', 'esphome', 'packages', 'ota', 'wifi'})
            self.assertNotIn('api', bridge)
            self.assertEqual(bridge['esphome'], {'name': 'kitchen', 'friendly_name': 'Kitchen'})
            self.assertEqual(bridge['ota'], own['ota'])
            self.assertIs(bridge['ota'][0]['allow_partition_access'], True)
            self.assertEqual(bridge['wifi'], own['wifi'])
            self.assertEqual(bridge['wifi']['manual_ip'], {'static_ip': '10.0.0.9'})
            self.assertEqual(bridge['packages'], {'bridge': {'url': core.REPO, 'ref': core.REF, 'files': ['packages/bridge.yaml'], 'refresh': '0s'}})
            self.assertIn('!secret wifi_password', (Path(tmp) / name).read_text())
            # It is no screen: the list of profiles leaves it out, and a build of it writes nothing into it.
            self.assertEqual([p['file'] for p in firmware.profiles()], ['kitchen.yaml'])
            self.assertEqual(firmware.profile(name).name, name)
            self.assertEqual(firmware.ota_port('kitchen.yaml'), 3232)
            # What it built and the file itself go together.
            build = Path(tmp) / 'build' / 'kitchen.bridge' / 'kitchen' / 'build'
            build.mkdir(parents=True)
            (build / 'firmware.ota.bin').write_bytes(b'x' * 1000)
            self.assertEqual(firmware.image_size(name), 1000)
            self.assertIsNone(firmware.image_size('kitchen.yaml'))
            asyncio.run(firmware.drop_bridge('kitchen.yaml'))
            self.assertFalse((Path(tmp) / name).exists())
            self.assertFalse((Path(tmp) / 'build' / 'kitchen.bridge').exists())
            self.assertTrue(path.exists())

    def test_a_profile_it_cannot_bridge_says_so(self):
        cases = {
            'a board with more flash': OLD.replace('BOARD', 'guition'),
            'wifi somewhere else': OLD.replace('BOARD', 'cyd').replace('wifi:\n  ssid: !secret wifi_ssid\n  password: !secret wifi_password\n  power_save_mode: none\n', 'wifi: !include wifi.yaml\n'),
            'no name': OLD.replace('BOARD', 'cyd').replace('  name: "kitchen"\n', ''),
        }
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, text) in enumerate(cases.items()):
                with self.subTest(name):
                    (Path(tmp) / f'b{index}.yaml').write_text(text)
                    firmware.allow_table_update(f'b{index}.yaml')
                    with self.assertRaises(ValueError):
                        firmware.bridge(f'b{index}.yaml')
                    self.assertFalse((Path(tmp) / f'b{index}.bridge.yaml').exists())


class WhatAScreenSays(unittest.TestCase):
    def test_the_word_comes_from_its_own_sensor(self):
        registry = [{'entity_id': 'text.a', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'a'},
                    {'entity_id': 'sensor.a_flash', 'platform': 'esphome', 'original_name': 'Screen flash', 'device_id': 'a'},
                    {'entity_id': 'text.b', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'b'}]
        devices = [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}]
        for state, word in (('wide', 'wide'), ('widen', 'widen'), ('widen_next', 'widen_next'), ('old', 'old'),
                            ('other', 'other'), ('unavailable', None), ('unknown', None), ('Wide!', None)):
            states = {'text.a': {'state': 'Ready'}, 'sensor.a_flash': {'state': state}, 'text.b': {'state': 'Ready'}}
            first, second = core.discover_screens(registry, states, devices, [])
            self.assertEqual(first['flash'], word, state)
            self.assertIsNone(second['flash'], 'a board with more flash has no such sensor')

    def test_a_screen_without_the_wide_table_is_updated_in_tessera(self):
        # Its firmware no longer fits ESPHome's slot, so ESPHome Device Builder's update is refused; Tessera moves the
        # table on the way (app 0.4.82). Firmware from before the sensor says nothing, and counts as the old table.
        for board in WIDE_BOARDS:
            for word, expected in ((None, True), ('old', True), ('widen', True), ('widen_next', True), ('wide', False), ('other', False)):
                self.assertIs(core.update_in_tessera({'online': True, 'board': board, 'flash': word}), expected, (board, word))
            self.assertFalse(core.update_in_tessera({'online': False, 'board': board, 'flash': None}), 'away says nothing')
        self.assertFalse(core.update_in_tessera({'online': True, 'board': 'guition', 'flash': None}))
        self.assertFalse(core.update_in_tessera({'online': True, 'board': 'unknown', 'flash': None}))
        self.assertTrue(core.update_in_tessera({'online': True, 'package': 'packages/cyd.yaml', 'flash': None}))


class Screen:
    """A screen with 4 MB of flash, as the updater meets it: what ESPHome's upload answers, and what the screen says in
    Home Assistant after each step. It follows the rules the bench board showed (docs/FLASH_LAYOUT.md)."""
    # Firmware from before the component, one with it that an update is on offer for, today's, and the bridge.
    OLD, WITH, NEW, BRIDGE = '0.2.16', '0.2.17', core.firmware_target('cyd'), 'bridge'

    def __init__(self, ha, runs=OLD, wide=False, slot=0, size=1_700_000, slow_chip=False, speaks=True):
        self.ha, self.runs, self.wide, self.slot, self.size = ha, runs, wide, slot, size
        self.slow_chip, self.speaks, self.comes_back = slow_chip, speaks, True
        self.report()

    def word(self):
        if self.runs == self.OLD or not self.speaks: return None
        return 'wide' if self.wide else 'widen' if self.slot == 0 else 'widen_next'

    def report(self):
        """What Home Assistant shows: nothing of a screen on its bridge, which has no api."""
        away = self.runs == self.BRIDGE or not self.comes_back
        word = self.word()
        self.ha.states.update({
            'text.screen1': {'state': 'unavailable' if away else 'Ready'},
            'text.fw1': {'state': 'unavailable' if away else self.runs},
            'text.flash1': {'state': 'unavailable' if away or self.runs == self.OLD else word or 'old'}})

    def install(self, image, size):
        if size > (0x1F0000 if self.wide else 0x1C0000): return False   # refused, nothing written
        self.runs, self.slot = image, 1 - self.slot
        self.report()
        return True

    def table(self):
        if self.runs == self.OLD: return False                          # cannot take a table
        if self.wide: return True
        if self.slot == 1 and self.slow_chip: return False              # the copy ran into the watchdog
        self.wide, self.slot = True, 0
        self.report()
        return True


class FakeFirmware:
    """Stands in for firmware.Firmware and the ESPHome CLI behind it."""
    NARROW_SLOT = Firmware.NARROW_SLOT

    def __init__(self, screen, bridge_size=900_000):
        self.screen, self.calls, self.task, self.job, self.bridges, self.bridge_size = screen, [], None, None, set(), bridge_size
        self.names = {'living-room.yaml': {'node': 'living-room', 'friendly': 'Living room', 'package': 'packages/cyd.yaml'}}
        self.fail = set()

    def profile_names(self): return self.names
    def wide_slots(self, name): return True
    def image_size(self, name): return self.bridge_size if name.endswith('.bridge.yaml') else self.screen.size

    def bridge(self, name):
        self.bridges.add(name)
        return name.replace('.yaml', '.bridge.yaml')

    async def drop_bridge(self, name): self.bridges.discard(name)

    def start(self, data):
        if self.task and not self.task.done(): raise ValueError('A build or install is already running.')
        step = (data['file'].replace('living-room', '').replace('.yaml', '').strip('.') or 'firmware', data['action'])
        self.calls.append(step)
        self.job = {'state': 'running', **data}
        self.task = asyncio.create_task(self.run(step))
        return self.job

    async def run(self, step):
        await asyncio.sleep(0)
        what, action = step
        ok = step not in self.fail
        if ok and action == 'install':
            ok = self.screen.install(Screen.NEW if what == 'firmware' else Screen.BRIDGE,
                                     self.image_size('living-room.yaml' if what == 'firmware' else 'living-room.bridge.yaml'))
        elif ok and action == 'widen':
            ok = self.screen.table()
        self.job['state'] = 'success' if ok else 'failed'


class TheUpdater(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp, **screen):
        from server import Manager

        class HA:
            online = True
            time_zone = timezone.utc
            registry = [{'entity_id': 'text.screen1', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                        {'entity_id': 'text.node1', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                        {'entity_id': 'text.ip1', 'platform': 'esphome', 'original_name': 'IP address', 'device_id': 'd1'},
                        {'entity_id': 'text.fw1', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                        {'entity_id': 'text.flash1', 'platform': 'esphome', 'original_name': 'Screen flash', 'device_id': 'd1'}]
            devices = [{'id': 'd1', 'name': 'Living room'}]
            areas = []
            states = {'text.screen1': {'state': 'Ready'}, 'text.node1': {'state': 'living-room'}, 'text.ip1': {'state': '10.0.0.5'},
                      'text.fw1': {'state': Screen.OLD}}
            changed = asyncio.Event()
            def __init__(self): self.messages, self.calls = [], []
            async def send(self, inbox, message, action=None): self.messages.append((inbox, message))
            async def request(self, kind, **data): self.calls.append((kind, data))

        manager = Manager(with_screen_grid(HA()), Path(tmp) / 'screens.json')
        manager.firmware = FakeFirmware(Screen(manager.ha, **screen))
        for attr in ('settle_seconds', 'pause_seconds', 'poll_seconds', 'bridge_pause', 'bridge_trial'):
            setattr(manager.updates, attr, 0)
        manager.updates.verify_timeout = manager.updates.word_timeout = 0.05
        return manager

    async def update(self, m):
        m.updates.start('text.screen1')
        await m.updates.task
        return m.updates.results['text.screen1']['state'], m.firmware.calls

    async def test_a_screen_from_before_is_updated_and_then_widened(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, slot=1)                       # the update lands in its first slot
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('firmware', 'install'), ('firmware', 'widen')])
            self.assertEqual(state, 'success')
            self.assertTrue(m.firmware.screen.wide)
            self.assertEqual(m.firmware.screen.runs, Screen.NEW)
            self.assertEqual(m.updates.bridging, {})

    async def test_from_the_second_slot_it_takes_one_more_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, slot=0)                       # the update lands in its second slot: "widen_next"
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('firmware', 'install'), ('firmware', 'install'), ('firmware', 'widen')])
            self.assertEqual(state, 'success')
            self.assertTrue(m.firmware.screen.wide)

    async def test_a_screen_that_asks_already_gets_the_table_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, runs=Screen.WITH, slot=0)
            self.assertEqual(m.updates.slot_word('text.screen1'), 'widen')
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('firmware', 'widen'), ('firmware', 'install')])
            self.assertEqual(state, 'success')
            self.assertEqual((m.firmware.screen.runs, m.firmware.screen.wide), (Screen.NEW, True))

    async def test_a_wide_screen_is_updated_as_any_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, runs=Screen.WITH, wide=True)
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('firmware', 'install')])
            self.assertEqual(state, 'success')

    async def test_a_screen_that_says_nothing_keeps_its_table(self):
        """Someone's own partition table, or a YAML this app could not add the line to: updated, and left alone."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, speaks=False)
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('firmware', 'install')])
            self.assertEqual(state, 'success')
            self.assertFalse(m.firmware.screen.wide)

    async def test_a_table_that_does_not_take_fails_the_update_only_when_the_screen_stays_away(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, slot=1)
            m.firmware.fail.add(('firmware', 'widen'))          # ESPHome's upload says no: the screen still runs
            state, calls = await self.update(m)
            self.assertEqual(calls[-1], ('firmware', 'widen'))
            self.assertEqual(state, 'failed')
            self.assertFalse(m.firmware.screen.wide)
            self.assertEqual(m.firmware.screen.runs, Screen.NEW, 'the firmware itself is on')

    async def test_a_firmware_too_large_for_the_old_slot_goes_over_the_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, size=1_900_000, slot=1)       # the bridge lands in its first slot
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('bridge', 'build'), ('bridge', 'install'), ('bridge', 'widen'),
                                     ('firmware', 'install')])
            self.assertEqual(state, 'success')
            screen = m.firmware.screen
            self.assertEqual((screen.runs, screen.wide), (Screen.NEW, True))
            self.assertEqual(m.updates.bridging, {})
            self.assertEqual(m.firmware.bridges, set(), 'the bridge is removed again')
            self.assertNotIn('bridging', json.loads((Path(tmp) / 'updates.json').read_text()))

    async def test_on_a_slow_flash_chip_the_bridge_moves_to_its_first_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, size=1_900_000, slot=0, slow_chip=True)   # the bridge lands in its second slot
            state, calls = await self.update(m)
            self.assertEqual(calls, [('firmware', 'build'), ('bridge', 'build'), ('bridge', 'install'),
                                     ('bridge', 'widen'), ('bridge', 'install'),      # refused; the bridge once more
                                     ('firmware', 'install'), ('bridge', 'widen'),    # still too large; now the table takes
                                     ('firmware', 'install')])
            self.assertEqual(state, 'success')
            self.assertEqual((m.firmware.screen.runs, m.firmware.screen.wide), (Screen.NEW, True))

    async def test_a_round_that_stopped_on_the_bridge_is_picked_up_again(self):
        """The app restarts while the screen runs its bridge: Home Assistant shows it away, the note is on disk, and
        the next round finishes it from whatever step it is at."""
        for wide in (False, True):
            with self.subTest(wide=wide), tempfile.TemporaryDirectory() as tmp:
                m = self.manager(tmp, size=1_900_000, slot=1)
                m.firmware.fail.update({('bridge', 'widen'), ('firmware', 'install')})   # everything after the bridge fails
                m.updates.bridge_attempts = 1
                state, _ = await self.update(m)
                self.assertEqual(state, 'failed')
                self.assertEqual(m.firmware.screen.runs, Screen.BRIDGE)
                note = json.loads((Path(tmp) / 'updates.json').read_text())['bridging']
                self.assertEqual(note['text.screen1']['profile'], 'living-room.yaml')
                self.assertEqual(note['text.screen1']['host'], '10.0.0.5')
                self.assertFalse(m.inventory()[0][0]['online'])
                # A new app process: the note is read back, and its nightly loop would launch this round.
                from updates import Updater
                again = Updater(m, Path(tmp) / 'updates.json')
                for attr in ('settle_seconds', 'pause_seconds', 'poll_seconds', 'bridge_pause', 'bridge_trial'):
                    setattr(again, attr, 0)
                again.verify_timeout = again.word_timeout = 0.05
                self.assertEqual(set(again.bridging), {'text.screen1'})
                m.firmware.fail.clear(); m.firmware.calls.clear(); m.firmware.screen.wide = wide
                again.launch(['text.screen1'], automatic=True)
                await again.task
                self.assertEqual(again.results['text.screen1']['state'], 'success')
                self.assertEqual(m.firmware.calls[:2], [('firmware', 'build'), ('bridge', 'build')])
                self.assertEqual(('bridge', 'widen') in m.firmware.calls, not wide, 'a table that is wide is not sent again')
                self.assertEqual((m.firmware.screen.runs, m.firmware.screen.wide), (Screen.NEW, True))
                self.assertEqual(again.bridging, {})

    async def test_a_restart_in_the_firmware_s_first_minute_brings_the_bridge_back_and_the_note_finishes_it(self):
        """ESPHome keeps a new firmware on trial for a minute; a restart in that minute puts the one before back, and
        after the bridge that is the bridge. The note is kept until the screen is through that minute, so the next
        round installs the firmware again."""
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, size=1_900_000, slot=1)
            screen = m.firmware.screen
            real = screen.install

            def rolled_back(image, size):
                done = real(image, size)
                if done and image == Screen.NEW:           # the power goes in its first minute
                    screen.runs, screen.slot = Screen.BRIDGE, 1 - screen.slot
                    screen.report()
                return done
            screen.install = rolled_back
            state, calls = await self.update(m)
            self.assertEqual(state, 'failed')
            self.assertEqual(calls[-1], ('firmware', 'install'))
            self.assertEqual((screen.runs, screen.wide), (Screen.BRIDGE, True))
            self.assertEqual(set(m.updates.bridging), {'text.screen1'}, 'the note stays')
            self.assertEqual(m.firmware.bridges, {'living-room.yaml'}, 'and so does the bridge')
            screen.install = real
            m.firmware.calls.clear()
            m.updates.launch(['text.screen1'], automatic=True)
            await m.updates.task
            self.assertEqual(m.updates.results['text.screen1']['state'], 'success')
            self.assertEqual(m.firmware.calls, [('firmware', 'build'), ('bridge', 'build'), ('firmware', 'install')])
            self.assertEqual((screen.runs, screen.wide), (Screen.NEW, True))
            self.assertEqual(m.updates.bridging, {})
            self.assertEqual(m.firmware.bridges, set())

    async def test_a_bridge_that_cannot_be_installed_leaves_the_screen_as_it_was(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, size=1_900_000)
            m.firmware.fail.add(('bridge', 'install'))
            state, calls = await self.update(m)
            self.assertEqual(state, 'failed')
            self.assertEqual(calls, [('firmware', 'build'), ('bridge', 'build'), ('bridge', 'install')])
            self.assertEqual(m.firmware.screen.runs, Screen.OLD)
            self.assertEqual(m.updates.bridging, {})
            self.assertEqual(m.firmware.bridges, set())


if __name__ == '__main__':
    unittest.main()
