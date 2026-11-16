"""The keyboard's characters are the screens' own (docs/KEYBOARD.md, "A new layout").

Every key of every layout in components/smart_display/keyboard.h, its accents and the labels of its page keys, is a
character of the five text fonts of packages/core.yaml, so a key never types or shows a box. The icons it draws (close,
backspace, shift, the check) are in the fixed set of screen_manager/app/tile_icons.py, which every screen carries. A
layout of another script fails here until its letters are in the fonts (and their flash is paid for).
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.append(str(ROOT / 'tools'))  # after the app: tools/i18n.py is not the app's i18n
import profiles  # noqa: E402
import tile_icons  # noqa: E402

TEXT_FONTS = ('headline', 'watch_value', 'label', 'sublabel', 'sublabel_big')
HEADER = ROOT / 'components/smart_display/keyboard.h'


def literals(source):
    """The C string literals of `source` outside its comments, decoded."""
    code = re.sub(r'//[^\n]*', '', source)
    out = []
    for raw in re.findall(r'"((?:[^"\\]|\\.)*)"', code):
        text = re.sub(r'\\U([0-9A-Fa-f]{8})', lambda m: chr(int(m.group(1), 16)), raw)
        out.append(text.replace('\\"', '"').replace('\\\\', '\\'))
    return out


class KeyboardGlyphTests(unittest.TestCase):
    def setUp(self):
        self.found = literals(HEADER.read_text(encoding='utf-8'))
        self.assertGreater(len(self.found), 4 * 26, 'the layout tables were not read')

    def test_every_character_of_every_layout_is_in_the_text_fonts(self):
        typed = {char for text in self.found for char in text if ord(char) < 0xF0000}
        self.assertIn('€', typed)
        self.assertIn('ł', typed)
        core = (ROOT / 'packages/core.yaml').read_text(encoding='utf-8')
        for font in TEXT_FONTS:
            glyphs = profiles.glyphs(core, font)
            self.assertIsNotNone(glyphs, font)
            self.assertEqual(sorted(typed - glyphs), [], f'keyboard.h types characters the {font} font has not')

    def test_every_icon_is_one_every_screen_carries(self):
        icons = {f'{ord(char):05X}' for text in self.found for char in text if ord(char) >= 0xF0000}
        self.assertEqual(len(icons), 4)  # close, backspace, shift, check
        carried = {codepoint for _, codepoint in tile_icons.FIXED} | {codepoint for codepoint, _ in tile_icons.ICONS.values()}
        self.assertEqual(sorted(icons - carried), [])


if __name__ == '__main__':
    unittest.main()
