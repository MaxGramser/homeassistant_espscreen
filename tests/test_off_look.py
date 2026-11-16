"""An off light and an off binary sensor look off, as in Home Assistant (app 0.2.62 / firmware 0.2.53).

Home Assistant's own light icon is a bulb that is crossed out while off (`mdi:lightbulb-off`), and every entity that is
off is grey. An icon of its own, or one chosen in ESP Screens, stays the same and turns grey, as in Home Assistant.

What the screen draws is read from the real firmware in web/wasm/test_state_look.mjs (the crossed-out bulb, the grey of
an off light and of every other off entity, the colour of one that is on). Here: the glyph the fonts must carry, and the
top bar, which the add-on draws the same way.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import tile_icons  # noqa: E402


class OffLook(unittest.TestCase):
    def test_the_fonts_carry_the_bulb_that_is_off(self):
        # Every board's icon fonts are written from GLYPHS (tools/generate_icons.py, checked by `--check`).
        self.assertEqual(tile_icons.GLYPHS['lightbulb-off'], 'F0E4F')

    def test_the_top_bar_does_the_same(self):
        light = lambda state, **attrs: {'state': state, 'attributes': attrs}
        self.assertEqual(header_bar.auto_icon('light.hall', light('off')), tile_icons.GLYPHS['lightbulb-off'])
        self.assertEqual(header_bar.auto_icon('light.hall', light('on')), tile_icons.GLYPHS['lightbulb'])
        self.assertEqual(header_bar.auto_icon('light.hall', light('unavailable')), tile_icons.GLYPHS['lightbulb'])
        self.assertEqual(header_bar.auto_icon('light.lamp', light('off', icon='mdi:lamp')), tile_icons.GLYPHS['lamp'])
        self.assertIsNone(header_bar.accent('light.hall', light('off')))


if __name__ == '__main__':
    unittest.main()
