"""A screen's chip revision goes into its own YAML before a build (screen_manager/app/chip_revision.py,
docs/CHIP_REVISIONS.md).

An ESP32-P4 of revision 3 stays black on a firmware for the earlier silicon, and boards sold under one name carry either
(GitHub #336, #397, #462). So the app reads the chip: on the USB cable while it installs, from the screen's "Screen chip"
sensor after that, from an Override YAML that switched the P4 to rev3 by hand before the app did. These tests prove the
readings, the line New screen writes, the line a build writes first, and that the readings are kept apart from the
rules, which live in the packages (tests/test_p4_core.py)."""
import asyncio
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import chip_revision  # noqa: E402
import core  # noqa: E402
import yaml  # noqa: E402
from firmware import Firmware, LenientLoader  # noqa: E402

PROFILE = ('substitutions:\n  DEVICE_NAME: "hall"\n\nesphome:\n  name: "hall"\n\npackages:\n  display:\n'
           '    url: https://github.com/MaxGramser/homeassistant_espscreen\n    ref: main\n'
           '    files: [packages/jc4880p443.yaml]\n    refresh: 0s\n  local_overrides: !include hall.local.yaml\n')


def substitutions(path):
    return yaml.load(path.read_text(), Loader=LenientLoader)['substitutions']


class Readings(unittest.TestCase):
    def test_the_sensor_says_the_chip_and_its_revision(self):
        self.assertEqual(chip_revision.from_sensor('ESP32-P4 v3.2'), 302)
        self.assertEqual(chip_revision.from_sensor('ESP32-P4 v1.3'), 103)
        self.assertEqual(chip_revision.from_sensor('ESP32-S3 v0.2'), 2)
        for nothing in ('unknown', '', None, 'v3.2', 'ESP32-P4 3.2'):
            self.assertIsNone(chip_revision.from_sensor(nothing), nothing)

    def test_esptool_says_it_on_connecting_in_either_version(self):
        self.assertEqual(chip_revision.from_esptool('Connecting....\nChip type:          ESP32-P4 (revision v3.2)\n'), 302)
        self.assertEqual(chip_revision.from_esptool('Chip is ESP32-P4 (revision v1.3)\nFeatures: ...'), 103)
        self.assertIsNone(chip_revision.from_esptool('A fatal error occurred: Failed to connect to Espressif device'))

    def test_an_override_that_switched_a_p4_to_rev3_by_hand_says_rev3(self):
        self.assertEqual(chip_revision.from_override('esp32:\n  engineering_sample: false\n'), 300)
        self.assertEqual(chip_revision.from_override('esp32:\n  engineering_sample: false\n  cpu_frequency: 400MHz\n'
                                                     'logger:\n  hardware_uart: USB_SERIAL_JTAG\n'), 300)
        for nothing in ('{}\n', 'esp32:\n  engineering_sample: true\n', 'logger:\n  level: INFO\n', ': [', None):
            self.assertIsNone(chip_revision.from_override(nothing), nothing)

    def test_the_sensor_wins_over_the_override(self):
        self.assertEqual(chip_revision.known({'chip': 'ESP32-P4 v1.3'}, 'esp32:\n  engineering_sample: false\n'), 103)
        self.assertEqual(chip_revision.known({'chip': None}, 'esp32:\n  engineering_sample: false\n'), 300)
        self.assertIsNone(chip_revision.known(None, '{}\n'))

    def test_only_a_whole_number_goes_into_a_yaml(self):
        self.assertEqual([chip_revision.valid(v) for v in (302, '302', ' 0 ', 9999)], [302, 302, 0, 9999])
        for bad in (-1, 10000, '3.2', 'v3.2', '302; rm', True, None, 3.2):
            self.assertIsNone(chip_revision.valid(bad), bad)


class NewScreen(unittest.TestCase):
    def test_a_chip_read_on_the_cable_is_a_line_of_the_new_yaml(self):
        text = core.installation_yaml({'board': 'jc4880p443', 'name': 'hall', 'friendly_name': 'Hall', 'chip_revision': 302})
        self.assertEqual(yaml.load(text, Loader=LenientLoader)['substitutions']['CHIP_REVISION'], '302')

    def test_no_chip_read_writes_no_line_and_the_board_default_builds(self):
        text = core.installation_yaml({'board': 'jc4880p443', 'name': 'hall', 'friendly_name': 'Hall'})
        self.assertNotIn('CHIP_REVISION', text)
        text = core.installation_yaml({'board': 'jc4880p443', 'name': 'hall', 'friendly_name': 'Hall', 'chip_revision': None})
        self.assertNotIn('CHIP_REVISION', text)

    def test_anything_else_is_refused(self):
        with self.assertRaises(ValueError):
            core.installation_yaml({'board': 'jc4880p443', 'name': 'hall', 'friendly_name': 'Hall', 'chip_revision': '3.2"\nx: y'})


class EveryBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = self.root / 'hall.yaml'
        self.profile.write_text(PROFILE)
        (self.root / 'hall.local.yaml').write_text('{}\n')
        self.firmware = Firmware(self.root, self.root)
        self.firmware.run = lambda *args: asyncio.sleep(0)

    def start(self, data):
        with unittest.mock.patch('shutil.which', return_value='/usr/bin/esphome'):
            async def go():
                self.firmware.start(data)
                await self.firmware.task
            asyncio.run(go())

    def test_the_line_changes_nothing_else_and_only_once(self):
        before = yaml.load(PROFILE, Loader=LenientLoader)
        self.assertTrue(self.firmware.set_chip_revision('hall.yaml', 302))
        self.assertFalse(self.firmware.set_chip_revision('hall.yaml', 302))
        after = yaml.load(self.profile.read_text(), Loader=LenientLoader)
        self.assertEqual(after['substitutions'].pop('CHIP_REVISION'), '302')
        self.assertEqual(after, before)
        self.assertEqual(self.firmware.chip_revision('hall.yaml'), 302)
        # Another chip on the same screen's YAML (a board swapped under its name) changes the line.
        self.assertTrue(self.firmware.set_chip_revision('hall.yaml', 103))
        self.assertEqual(substitutions(self.profile)['CHIP_REVISION'], '103')

    def test_the_chip_on_the_cable_goes_into_the_yaml_before_the_build(self):
        self.firmware.chip_of = lambda name: 103   # the screen said otherwise before: the cable wins
        self.start({'file': 'hall.yaml', 'action': 'download', 'chip_revision': 302})
        self.assertEqual(substitutions(self.profile)['CHIP_REVISION'], '302')

    def test_without_a_cable_the_screen_says_it(self):
        self.firmware.chip_of = lambda name: 302 if name == 'hall.yaml' else None
        self.start({'file': 'hall.yaml', 'action': 'build'})
        self.assertEqual(substitutions(self.profile)['CHIP_REVISION'], '302')

    def test_nothing_known_leaves_the_yaml_as_it_is(self):
        self.firmware.chip_of = lambda name: None
        self.start({'file': 'hall.yaml', 'action': 'build'})
        self.assertNotIn('CHIP_REVISION', self.profile.read_text())

    def test_a_check_of_the_yaml_writes_nothing(self):
        self.start({'file': 'hall.yaml', 'action': 'validate', 'chip_revision': 302})
        self.assertNotIn('CHIP_REVISION', self.profile.read_text())

    def test_an_override_cannot_set_it(self):
        with self.assertRaises(ValueError):
            self.firmware.save_override('hall.yaml', 'substitutions:\n  CHIP_REVISION: "302"\n')

    def test_a_port_of_home_assistants_machine_is_read_before_the_build(self):
        async def read(port):
            self.assertEqual(port, '/dev/ttyACM0')
            return 302
        firmware = self.firmware
        del firmware.run   # the real run, up to the first ESPHome step

        async def stop(*args, **kwargs):
            raise RuntimeError('no ESPHome here')
        firmware.retire_platformio = stop
        with unittest.mock.patch.object(chip_revision, 'read_usb', read), \
                unittest.mock.patch.object(Firmware, 'ports', lambda self: ['/dev/ttyACM0']):
            self.start({'file': 'hall.yaml', 'action': 'install', 'target': '/dev/ttyACM0'})
        self.assertEqual(substitutions(self.profile)['CHIP_REVISION'], '302')
        self.assertIn('The chip on /dev/ttyACM0 is revision v3.2.', list(firmware.logs))


class Screens(unittest.TestCase):
    def test_a_screen_reports_its_chip(self):
        registry = [{'entity_id': 'text.hall_tile_settings', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                    {'entity_id': 'sensor.hall_screen_chip', 'platform': 'esphome', 'original_name': 'Screen chip', 'device_id': 'd1'}]
        devices = [{'id': 'd1', 'name': 'Hall'}]
        states = {'text.hall_tile_settings': {'state': 'Applied'}, 'sensor.hall_screen_chip': {'state': 'ESP32-P4 v3.2'}}
        self.assertEqual(core.discover_screens(registry, states, devices, [])[0]['chip'], 'ESP32-P4 v3.2')
        for said in ('unavailable', 'unknown', 'garbage'):
            states['sensor.hall_screen_chip']['state'] = said
            self.assertIsNone(core.discover_screens(registry, states, devices, [])[0]['chip'], said)


if __name__ == '__main__':
    unittest.main()
