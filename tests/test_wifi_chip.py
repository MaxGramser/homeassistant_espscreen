"""The Wi-Fi co-processor of an ESP32-P4 screen (components/smart_display/wifi_chip.h).

On the P4 ESP-IDF's esp_restart() resets only the CPUs, and the SDIO link to the C6 now and then came out of that stuck:
the screen restarted every 13 seconds until its power went off (the bench Guition V3, about one restart in five,
2026-10-26). Every restart now ends in a reset of the whole digital system, and a diagnostic sensor says what the C6
runs, which the troubleshooting report reads."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHIP = ROOT / 'components' / 'smart_display' / 'wifi_chip.cpp'
CORE = ROOT / 'packages' / 'hardware' / 'esp32p4-core.yaml'
REPORTS = ROOT / 'screen_manager' / 'app' / 'reports.py'


def hosted_part():
    """The part of wifi_chip.cpp that a build with esp_hosted compiles."""
    text = CHIP.read_text()
    start = text.index('#ifdef USE_ESP32_HOSTED')
    return text[start:text.rindex('\n#else')]


class TheRestart(unittest.TestCase):
    def test_every_restart_ends_in_a_reset_of_the_whole_system(self):
        part = hosted_part()
        self.assertIn('void reset_whole_system() { esp_rom_software_reset_system(); }', part)
        self.assertIn('__attribute__((constructor)) void restart_whole() { '
                      'esp_register_shutdown_handler(reset_whole_system); }', part)

    def test_the_c6_reset_line_is_left_to_esp_hosted(self):
        self.assertNotIn('gpio_', CHIP.read_text())


class TheFirmware(unittest.TestCase):
    def test_the_c6_is_asked_once_with_wifi_up(self):
        part = hosted_part()
        firmware = part[part.index('std::string firmware()'):]
        self.assertLess(firmware.index('if (!told.empty())'), firmware.index('is_connected()'))
        self.assertLess(firmware.index('is_connected()'), firmware.index('esp_hosted_get_coprocessor_fwversion'))
        self.assertEqual(part.count('esp_hosted_get_coprocessor_fwversion('), 1)
        self.assertIn('"Wi-Fi co-processor: %s"', firmware)

    def test_every_p4_screen_has_the_sensor_and_the_report_reads_it(self):
        core = CORE.read_text()
        self.assertRegex(core, r'name: "Wi-Fi co-processor"\s+entity_category: diagnostic\s+'
                               r"lambda: 'return \{wifi_chip::firmware\(\)\};'")
        self.assertIn("'wi-fi co-processor'", REPORTS.read_text())


if __name__ == '__main__':
    unittest.main()
