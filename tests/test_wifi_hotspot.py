"""The Wi-Fi fallback hotspot and captive portal per board (app 0.4.2): a board with 4 MB of flash has no room for them
in its 1.75 MB update slot, so a new screen of it is written without them and an older screen's YAML loses them before
its next build. Every other board keeps them."""
import asyncio
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tools'))
import yaml  # noqa: E402
import profiles  # noqa: E402
from core import REPO, SHAPES, installation_yaml  # noqa: E402
from firmware import Firmware, LenientLoader  # noqa: E402

# A screen's YAML as ESP Screens wrote it up to app 0.4.1, for any board.
OLD = f'''# Keep this file safe: it contains the unique keys for this screen.
# Wi-Fi comes from the secrets.yaml of ESPHome Device Builder.
substitutions:
  DEVICE_NAME: "kitchen"
  DEVICE_FRIENDLY_NAME: "Kitchen"
  LANGUAGE: "nl"

esphome:
  name: "kitchen"
  friendly_name: "Kitchen"

packages:
  display:
    url: {REPO}
    ref: main
    files: [packages/BOARD.yaml]
    refresh: 0s
  local_overrides: !include kitchen.local.yaml

api:
  encryption:
    key: "a2l0Y2hlbi1rZXktZm9yLXRoZS10ZXN0LW9ubHktMzI="
ota:
  - platform: esphome
    password: "kitchen-ota-password-for-the-test"
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  ap:
    ssid: "kitchen Setup"
    password: "kitchen-ap-pw"
captive_portal:
'''


def load(text):
    return yaml.load(text.replace('\r\n', '\n'), Loader=LenientLoader)


class Boards(unittest.TestCase):
    def test_only_boards_with_4_mb_of_flash_go_without(self):
        without = sorted(board for board in profiles.BOARDS if not profiles.hotspot(board))
        self.assertEqual(without, ['cyd', 'cyd9342', 'hosyond40'])
        for board in profiles.BOARDS:
            self.assertEqual(SHAPES[board]['hotspot'], profiles.flash_mb(board) > 4, board)

    def test_a_new_screen_gets_it_where_its_board_has_room(self):
        for board in profiles.BOARDS:
            with self.subTest(board):
                text = installation_yaml({'board': board, 'name': 'hall', 'friendly_name': 'Hall'})
                data = load(text)
                self.assertEqual('ap' in data['wifi'], SHAPES[board]['hotspot'])
                self.assertEqual('captive_portal' in data, SHAPES[board]['hotspot'])
                self.assertEqual(data['wifi']['power_save_mode'], 'none')
                self.assertTrue(text.endswith('\n'))

    def test_the_checkout_entries_match(self):
        for board in profiles.BOARDS:
            data = load((ROOT / 'checkout' / f'{board}.yaml').read_text())
            self.assertEqual('ap' in data['wifi'], SHAPES[board]['hotspot'], board)
            self.assertEqual('captive_portal' in data, SHAPES[board]['hotspot'], board)


class OlderScreens(unittest.TestCase):
    def write(self, tmp, name, text):
        path = Path(tmp) / name
        path.write_bytes(text.encode())
        return path

    def test_both_go_and_nothing_else_changes(self):
        cases = {
            'cyd': OLD.replace('BOARD', 'cyd'),
            'cyd9342 crlf': OLD.replace('BOARD', 'cyd9342').replace('\n', '\r\n'),
            'hosyond40 with more': OLD.replace('BOARD', 'hosyond40')
                .replace('    password: "kitchen-ap-pw"\n', '    password: "kitchen-ap-pw"\n\n  # kept\n  fast_connect: true\n')
                .replace('captive_portal:\n', 'captive_portal:\n\nlogger:\n  level: DEBUG\n'),
            'cyd ap first': OLD.replace('BOARD', 'cyd').replace(
                '  ssid: !secret wifi_ssid\n', '  ap:\n    ssid: "x"\n  ssid: !secret wifi_ssid\n', 1)
                .replace('  ap:\n    ssid: "kitchen Setup"\n    password: "kitchen-ap-pw"\n', ''),
        }
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, text) in enumerate(cases.items()):
                with self.subTest(name):
                    path = self.write(tmp, f'p{index}.yaml', text)
                    before = load(text)
                    self.assertTrue(firmware.drop_hotspot(path.name))
                    out = path.read_bytes().decode()
                    self.assertEqual('\r\n' in out, '\r\n' in text, 'line ends stay as they were')
                    after = load(out)
                    self.assertNotIn('captive_portal', after)
                    self.assertNotIn('ap', after['wifi'])
                    before.pop('captive_portal')
                    before['wifi'].pop('ap')
                    self.assertEqual(after, before)
                    self.assertFalse(firmware.drop_hotspot(path.name), 'nothing to do the second time')

    def test_other_profiles_stay_as_they_are(self):
        cases = {
            'a board with room': OLD.replace('BOARD', 'guition'),
            'not one of ours': OLD.replace(REPO, 'https://example.com/other').replace('BOARD', 'cyd'),
            'a checkout build': OLD.replace(f'    url: {REPO}\n    ref: main\n    files: [packages/BOARD.yaml]\n    refresh: 0s\n',
                                            '    core: !include packages/core.yaml\n'),
            'no hotspot any more': OLD.replace('BOARD', 'cyd').replace(
                '  ap:\n    ssid: "kitchen Setup"\n    password: "kitchen-ap-pw"\ncaptive_portal:\n', ''),
        }
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            for index, (name, text) in enumerate(cases.items()):
                with self.subTest(name):
                    path = self.write(tmp, f'p{index}.yaml', text)
                    self.assertFalse(firmware.drop_hotspot(path.name))
                    self.assertEqual(path.read_bytes().decode(), text)

    def test_every_build_takes_it_out_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Firmware(tmp, tmp)
            path = self.write(tmp, 'kitchen.yaml', OLD.replace('BOARD', 'cyd'))
            firmware.run = lambda *args: asyncio.sleep(0)
            with unittest.mock.patch('shutil.which', return_value='/usr/bin/esphome'):
                async def start():
                    firmware.start({'file': 'kitchen.yaml', 'action': 'validate'})
                    self.assertIn('captive_portal:', path.read_text(), 'validating changes nothing')
                    await firmware.task
                    firmware.start({'file': 'kitchen.yaml', 'action': 'build'})
                    await firmware.task
                asyncio.run(start())
            self.assertNotIn('captive_portal', load(path.read_text()))
            self.assertTrue(any('hotspot' in line for line in firmware.logs))


if __name__ == '__main__':
    unittest.main()
