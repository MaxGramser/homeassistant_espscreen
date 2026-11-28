"""The keyboard layout of a screen follows the language it is built in (docs/KEYBOARD.md, "The layout of a screen").

components/smart_display/keyboard_build.py picks it from the LANGUAGE substitution and gives the build its define,
keyboard.h takes that table as keyboard::standard(), and keyboard::layout_for() makes the same choice for the browser
preview, which carries every language. Here: the choice, and that the three places agree.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components/smart_display'


def keyboard_build():
    spec = importlib.util.spec_from_file_location('keyboard_build', COMPONENT / 'keyboard_build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KeyboardLayoutTests(unittest.TestCase):
    def setUp(self):
        self.build = keyboard_build()
        self.header = (COMPONENT / 'keyboard.h').read_text(encoding='utf-8')

    def test_german_screens_type_on_qwertz_and_every_other_on_qwerty(self):
        for code in ('de', 'de-AT', 'de-CH'):
            self.assertEqual(self.build.layout(code), 'qwertz', code)
            self.assertEqual(self.build.defines(code), ['SCREEN_KEYBOARD_QWERTZ'], code)
        for code in ('en', 'nl', 'fr', 'pt-BR', 'ru', 'deu', '', None):
            self.assertEqual(self.build.layout(code), 'qwerty', code)
            self.assertEqual(self.build.defines(code), [], code)

    def test_every_language_with_a_layout_of_its_own_has_its_translation(self):
        for code in self.build.LAYOUTS:
            self.assertTrue((ROOT / f'screen_manager/translations/{code}.json').is_file(),
                            f'keyboard_build.LAYOUTS names {code}, which ESP Screens does not build screens in')

    def test_the_component_applies_the_defines(self):
        source = (COMPONENT / '__init__.py').read_text(encoding='utf-8')
        self.assertRegex(source, r'for define in keyboard_build\.defines\(wanted\):\s+cg\.add_define\(define\)',
                         'components/smart_display/__init__.py must add the defines keyboard_build.defines() gives, '
                         'or a German screen types on QWERTY')

    def test_keyboard_h_has_every_layout_and_its_define(self):
        names = set(re.findall(r'static const Layout LAYOUT\{"(\w+)"', self.header))
        found = set(re.findall(r'if \(name == (\w+)\(\)\.name\) return &\1\(\);', self.header))
        self.assertEqual(names, found, 'keyboard::layout() finds every table of keyboard.h by its name')
        for language, layout in self.build.LAYOUTS.items():
            self.assertIn(layout, names, f'{language} types on {layout}, which keyboard.h has no table for')
        for layout, define in self.build.DEFINES.items():
            self.assertRegex(self.header, rf'#elif defined\({define}\)\s+return {layout}\(\);',
                             f'keyboard::standard() takes {layout} when the build defines {define}')

    def test_the_preview_makes_the_same_choice(self):
        own = re.search(r'OWN\[\]\[2\] = \{(.*?)\};', self.header)
        self.assertIsNotNone(own, 'keyboard::layout_for() lists the languages that do not type on QWERTY')
        self.assertEqual(dict(re.findall(r'\{"([a-z]+)", "([a-z]+)"\}', own.group(1))), self.build.LAYOUTS,
                         'keyboard::layout_for() (keyboard.h) and keyboard_build.LAYOUTS name the same languages and layouts')
        preview = (ROOT / 'web/wasm/firmware_preview.cpp').read_text(encoding='utf-8')
        self.assertIn('keyboard::shown_layout() = keyboard::layout(keyboard::layout_for(code));', preview,
                      'the preview shows the keyboard of the language it shows (preview_language)')


if __name__ == '__main__':
    unittest.main()
