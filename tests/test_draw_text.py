"""A text a card paints in its draw event is copied by LVGL (components/smart_display/draw_text.h): LVGL draws a label
after the draw event returned, from a pointer, so a text in a local of the draw code is gone by then. The meter's icon
was such a text and its disc stood empty when a page came back (a Guition 10.1, 2026-11-15)."""
from pathlib import Path
import re
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / 'components/smart_display'


class DrawText(unittest.TestCase):
    def test_every_label_a_card_draws_itself_goes_through_draw_text(self):
        direct = [path.name for path in sorted(COMPONENT.iterdir()) if path.suffix in ('.h', '.cpp')
                  and path.name != 'draw_text.h' and re.search(r'\blv_draw_label\(', path.read_text())]
        self.assertEqual(direct, [], 'draw a label with draw_text::label, which has LVGL copy the text')

    def test_draw_text_has_lvgl_copy_the_text(self):
        source = (COMPONENT / 'draw_text.h').read_text()
        self.assertLess(source.index('dsc.text_local = 1;'), source.index('lv_draw_label(layer, &dsc, &area);'))


if __name__ == '__main__':
    unittest.main()
