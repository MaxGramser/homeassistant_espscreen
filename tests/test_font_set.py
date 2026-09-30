"""The fonts are a fixed set (firmware 0.17.0): every board renders the same short list of text, digit and icon steps, and a
new card takes the largest step that fits instead of bringing a size of its own. Adding a font means changing this set
on purpose; one that slips in with a feature fails here."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from firmware_sources import runtime_source  # noqa: E402

TEXT = {'sublabel', 'label', 'sublabel_big', 'headline', 'watch_value'}          # S, M, L, XL and the large value
DIGITS = {'clock_digits', 'setpoint_digits', 'display_digits', 'bedside_digits'}  # the clock card, the setpoint, half a page, a page
ICONS = {'materialdesign_icons_mini', 'materialdesign_icons', 'materialdesign_icons_big', 'watch_icon', 'materialdesign_icons_back'}
MARK = {'brand_wordmark'}


def fonts(name):
    return re.findall(r'^  - file: .*\n    id: (\w+)\n    size: (\d+)', profiles.resolved(name), re.M)


class FontSetTests(unittest.TestCase):
    def test_every_board_renders_the_set_and_nothing_else(self):
        for name in profiles.PROFILES:
            with self.subTest(name):
                self.assertEqual({font for font, _ in fonts(name)}, TEXT | DIGITS | ICONS | MARK)

    def test_the_bedside_clock_takes_the_display_step_where_its_own_would_be_barely_larger(self):
        # A 4-inch Guition and a CYD: the page takes digits less than a fifth larger than half its width, so the clock
        # shares the flip clock's display step and its own font stays an 8 px place holder.
        for name in ('checkout/guition.yaml', 'checkout/cyd.yaml'):
            sizes = dict(fonts(name))
            self.assertEqual(sizes['bedside_digits'], '8', name)
            self.assertGreater(int(sizes['display_digits']), int(sizes['setpoint_digits']), name)
        # Wherever the clock keeps a step of its own, that step is at least a fifth larger than the display step.
        for name in profiles.PROFILES:
            sizes = {font: int(size) for font, size in fonts(name)}
            if sizes['bedside_digits'] > 8:
                self.assertGreaterEqual(sizes['bedside_digits'], 1.2 * sizes['display_digits'] - 1, name)

    def test_large_digits_come_from_the_steps(self):
        source = runtime_source()
        self.assertIn('inline std::array<const lv_font_t *,3> digit_steps(){return {display_font,setpoint_font,clock_font};}', source)
        self.assertIn('const lv_font_t *font=largest_digits("88",bw*88/100,bh*72/100);', source)
        # The bedside clock's own step is used only where it is larger than the display step.
        self.assertIn('lv_font_get_line_height(bedside_font)>lv_font_get_line_height(display_font)', source)


if __name__ == '__main__':
    unittest.main()
