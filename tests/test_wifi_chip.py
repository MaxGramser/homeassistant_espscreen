"""The Wi-Fi co-processor of an ESP32-P4 screen (components/smart_display/wifi_chip.h).

On the P4 ESP-IDF's esp_restart() resets only the CPUs, and the SDIO link to the C6 now and then came out of that stuck:
the screen restarted every 13 seconds until its power went off (the bench Guition V3, about one restart in five,
2026-10-26). Every restart now ends in a reset of the whole digital system, and a diagnostic sensor says what the C6
runs, which the troubleshooting report reads.

What the C6 is asked and when is FirmwareOnce's, proven by tests/test_wifi_chip.cpp; that the report carries the
sensor is tests/test_reports.py's DeviceSensors. Here: the rules over the files, and what only a screen can show."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHIP = ROOT / 'components' / 'smart_display' / 'wifi_chip.cpp'
HARDWARE = ROOT / 'packages' / 'hardware'
CORE = HARDWARE / 'esp32p4-core.yaml'


class _Loader(yaml.SafeLoader):
    """ESPHome's own tags (!include, !lambda, !secret) read as plain values: the structure is what is checked."""


_Loader.add_multi_constructor('!', lambda loader, suffix, node: loader.construct_scalar(node)
                              if isinstance(node, yaml.ScalarNode) else None)


def hosted_part():
    """The part of wifi_chip.cpp that a build with esp_hosted compiles."""
    text = CHIP.read_text()
    start = text.index('#ifdef USE_ESP32_HOSTED')
    return text[start:text.rindex('\n#else')]


class TheRestart(unittest.TestCase):
    # glass: a P4 screen restarted from Home Assistant (or by an update) comes back on its own; its log starts with a
    # full reset of the chip, not a CPU reset that leaves the C6 link stuck. A PC cannot run ESP-IDF's restart path, so
    # this checks the mechanism by its parts, whatever the lines look like.
    def test_every_restart_ends_in_a_reset_of_the_whole_system(self):
        part = hosted_part()
        registered = re.search(r'__attribute__\(\(constructor\)\)[^{]*\{[^}]*esp_register_shutdown_handler\(\s*(\w+)\s*\)', part)
        self.assertTrue(registered, 'wifi_chip.cpp must register a shutdown handler before app_main (a constructor), so '
                                    'it runs last of every esp_restart() handler')
        handler = re.search(r'void\s+' + registered.group(1) + r'\s*\(\s*\)\s*\{([^}]*)\}', part)
        self.assertTrue(handler and 'esp_rom_software_reset_system(' in handler.group(1),
                        f'the shutdown handler {registered.group(1)} must end the restart in esp_rom_software_reset_system(), '
                        'the reset of the whole digital system')

    def test_the_c6_reset_line_is_left_to_esp_hosted(self):
        self.assertNotIn('gpio_', CHIP.read_text(),
                         'wifi_chip.cpp drives no GPIO: the C6 reset line is esp_hosted\'s, which holds it at start')


class TheFirmware(unittest.TestCase):
    def test_the_c6_is_asked_in_one_place_by_the_tested_rule(self):
        part = hosted_part()
        self.assertEqual(part.count('esp_hosted_get_coprocessor_fwversion('), 1,
                         'one place asks the C6 for its firmware; firmware() reaches it only through FirmwareOnce')
        self.assertIn('FirmwareOnce', part, 'firmware() asks through wifi_chip::FirmwareOnce, the rule '
                                            'tests/test_wifi_chip.cpp proves (once, never before Wi-Fi is up)')

    def test_every_p4_screen_has_the_sensor(self):
        core = yaml.load(CORE.read_text(), Loader=_Loader)
        sensors = [s for s in core.get('text_sensor') or [] if s.get('name') == 'Wi-Fi co-processor']
        self.assertEqual(len(sensors), 1, 'packages/hardware/esp32p4-core.yaml names one "Wi-Fi co-processor" sensor')
        self.assertEqual(sensors[0].get('entity_category'), 'diagnostic', 'the co-processor sensor is a diagnostic one')
        self.assertIn('wifi_chip::firmware()', str(sensors[0].get('lambda')), 'the sensor says wifi_chip::firmware()')
        for hardware in HARDWARE.glob('*.yaml'):
            parsed = yaml.load(hardware.read_text(), Loader=_Loader) or {}
            if 'esp32_hosted' in parsed:
                self.assertIn('esp32p4-core.yaml', str(parsed.get('packages')),
                              f'{hardware.name} has a Wi-Fi co-processor (esp32_hosted) and must include esp32p4-core.yaml, '
                              'whose sensor and restart every such screen needs')


if __name__ == '__main__':
    unittest.main()
