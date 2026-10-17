"""SenseCAP Indicator D1L GX hardware and catalog contracts, not bench tests."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles

ENTRY = 'checkout/sensecapd1l.yaml'
SOURCE = profiles.resolved(ENTRY)
VALUES = profiles.substitutions(ENTRY)
BOARD = ROOT / 'packages/boards/seeed-sensecap-indicator-d1l.yaml'


class SenseCAPD1L(unittest.TestCase):
    def test_uses_the_proven_native_gx_display_and_touch(self):
        for text in ('platform: mipi_rgb', 'model: SEEED-INDICATOR-D1',
                     'platform: ft5x06', 'address: 0x48', 'pclk_frequency: 16MHz',
                     'mode: octal', 'speed: 80MHz', 'flash_size: 8MB'):
            self.assertIn(text, SOURCE)
        self.assertEqual(VALUES['BOARD_ID'], 'sensecapd1l')
        self.assertEqual(VALUES['TOUCH_CONTROLLER'], 'FT6336U')
        self.assertEqual(VALUES['TOUCH_MIRROR_X'], 'true')
        self.assertEqual(VALUES['TOUCH_MIRROR_Y'], 'true')
        self.assertEqual(VALUES['TOUCH_SWAP_XY'], 'false')

    def test_preserves_expander_reset_and_backlight_wiring(self):
        own = BOARD.read_text()
        for text in ('id: touch_bus', 'sda: GPIO39', 'scl: GPIO40', 'address: 0x20',
                     'pin_count: 16', 'clk_pin: GPIO41', 'mosi_pin: GPIO48',
                     'number: GPIO45', 'id: gpio_backlight_pwm'):
            self.assertIn(text, own)
        self.assertIn('reset_pin:\n      pca9554: indicator_io\n      number: 5', own)
        self.assertIn('id: unused_radio_cs_high', own)
        self.assertIn('id: touch_reset_released', own)
        self.assertIn('BACKLIGHT_FREQUENCY: "100Hz"', own)
        self.assertIn('frequency: 100Hz', SOURCE)

    def test_is_a_hardware_adapter_not_the_bench_profile(self):
        own = BOARD.read_text()
        for forbidden in ('on_boot:', '!secret', 'type: local', 'platform: homeassistant',
                          'sx126x:', 'rp2040:', '\nuart:', 'number: 8',
                          'poc_mode_button', 'CALIBRATION_ON_BOOT:', 'AUTO_DIM:'):
            self.assertNotIn(forbidden, own)
        self.assertEqual(VALUES['CALIBRATION_ON_BOOT'], 'false')
        self.assertEqual(VALUES['AUTO_DIM_TIMEOUT'], '600')
        self.assertEqual(VALUES['SCREEN_MAX_TILES'], '128')
        self.assertEqual(VALUES['SCREEN_MAX_PAGES'], '24')
        self.assertEqual(VALUES['SCREEN_MAX_BAR_ITEMS'], '12')
        self.assertEqual(VALUES['LVGL_BUFFER_SIZE'], '12%')
        self.assertNotIn('set_raw_correction', SOURCE)

    def test_reuses_the_shared_hardware_ui_and_features(self):
        chain = {p.relative_to(ROOT).as_posix() for p in profiles.files(ENTRY)}
        for path in ('packages/core.yaml', 'packages/hardware/esp32s3-rgb.yaml',
                     'packages/looks/standard.yaml', 'packages/features/capacitive-touch.yaml',
                     'packages/features/backlight.yaml', 'packages/features/self-test.yaml'):
            self.assertIn(path, chain)
        self.assertNotIn('packages/features/camera.yaml', chain)
        self.assertNotIn('packages/features/snapshot.yaml', chain)
        self.assertIn('id: back_light', SOURCE)
        self.assertIn('id: screen_lvgl', SOURCE)

    def test_generated_catalog_exposes_the_same_geometry_and_limits(self):
        shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
        shape = shapes['sensecapd1l']
        self.assertEqual((shape['width'], shape['height']), (480, 480))
        self.assertEqual((shape['columns'], shape['rows']), (2, 3))
        self.assertEqual((shape['max_tiles'], shape['max_pages']), (128, 24))
        self.assertEqual(shape['max_bar_items'], 12)
        self.assertEqual(shape['catalog']['name'], 'SenseCAP Indicator')
        self.assertEqual(shape['catalog']['touch'], 'FT6336U')
        self.assertEqual(shape['catalog']['status'], 'experimental')
        self.assertIn('(GX)', shape['catalog']['model'])
        self.assertEqual(shape['chip'], 'ESP32-S3')
        self.assertEqual(shape['dpi'], 172)
        self.assertEqual(shapes['checkout/sensecapd1l.yaml'], shape)
        self.assertEqual(shapes['packages/sensecapd1l.yaml'], shape)


if __name__ == '__main__':
    unittest.main()
