from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'jc8012p4a1.yaml').read_text()
VALUES = dict(re.findall(r'^  (\w+): "([^"]*)"', SOURCE, re.M))


class JC8012P4A1Tests(unittest.TestCase):
    def test_hardware_profile_uses_p4_mipi_and_gsl3680(self):
        self.assertIn('variant: esp32p4', SOURCE)
        self.assertIn('variant: esp32c6', SOURCE)
        self.assertIn('platform: mipi_dsi', SOURCE)
        self.assertIn('model: JC8012P4A1', SOURCE)
        self.assertIn('platform: gsl3680', SOURCE)
        self.assertNotIn('platform: st7701s', SOURCE)
        self.assertNotIn('platform: gt911', SOURCE)
        self.assertEqual(VALUES['DISPLAY_W'], '1280')
        self.assertEqual(VALUES['DISPLAY_H'], '800')
        self.assertEqual(VALUES['TOUCH_MIRROR_X'], 'true')

    def test_package_fetches_the_vendored_hardware_components(self):
        package = (ROOT / 'packages' / 'jc8012p4a1.yaml').read_text()
        self.assertIn('url: https://github.com/MaxGramser/homeassistant_espscreen.git', package)
        self.assertIn('components: [smart_display, mipi_dsi, gsl3680]', package)


if __name__ == '__main__':
    unittest.main()
