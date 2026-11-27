"""Where a glass that is lit and a glass of ink part (docs/GLASS_KINDS.md): in one layer, and nowhere else.

The firmware is one set of pages, cards and controls for every glass. What differs between a lit glass and a glass of
ink differs in a few named files:

  glass_kind.h           the one fact (the panel's inks) and what follows from it, each under its own name
  theme.h                the tones: a role as a colour or as an ink
  theme_parts.h          the parts a card is made of, and the one fork between the two stylesheets
  theme_lit.h            every part on a glass that is lit
  theme_ink.h            every part on a glass of ink
  still_glass_lvgl.h     the form LVGL's own widgets take on a glass where nothing moves
  screen_motion.h        the one place that asks whether the glass is still

Everything else asks for a part (theme::state_disc, theme::mark, theme::gone) or a consequence (screen_motion::still,
theme::shades) and never which glass it is on. These tests hold that: a new card cannot quietly write "if paper", and
the two stylesheets cannot drift apart. tests/test_theme_parts.cpp holds what each part is on each glass,
tests/test_glass_kind.cpp the fact and its consequences, tests/test_glass_lit.cpp that a lit build carries no ink.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / 'components' / 'smart_display'
PACKAGES = ROOT / 'packages'

# The layer: the only files that may know which glass this is.
LAYER = {'glass_kind.h', 'theme.h', 'theme_parts.h', 'theme_lit.h', 'theme_ink.h', 'still_glass_lvgl.h'}
# Asking outright which glass this is, in any spelling.
ASKS_THE_GLASS = re.compile(r'\b(?:theme::inked\s*\(|glass_kind::ink\s*\(|glass_kind::inks\s*\(|theme::paper\b|paper::\w+\s*\(|'
                            r'on_ink::|on_lit::|theme::PAPER_RIM\b|theme::Ink::|theme::ink_value\s*\(|theme::set_paper\b)')
# The consequences, and who may ask each. The binder (packages/core.yaml) hands them to the parts that depend on them.
CONSEQUENCES = {
    'glass_kind::still': {'screen_motion.h', 'still_glass_lvgl.h'},
    'glass_kind::keeps': {'core.yaml'},
    'glass_kind::lit': {'core.yaml'},
}
# theme::shades() is for leaving something out, or putting it elsewhere, where the glass shows no shade. It is no way
# to choose a colour or a ground: those come from a part. Each asker and what it leaves out or moves.
SHADES = {
    'climate_card_lvgl.h': 'a humidity ring at half strength round the number',
    'runtime_tiles.h': 'a favourite as a card on its picture',
    'tile_picture_lvgl.h': 'a picture under a tile\'s words',
    'saver_lvgl.h': 'the screensaver\'s words on the picture itself (they stand on a band)',
}


def code(path):
    """A file's code without its comments: a comment may name anything."""
    text = path.read_text()
    if path.suffix == '.yaml':
        return '\n'.join(re.sub(r'(?<!:)//.*', '', re.sub(r'^\s*#.*', '', line)) for line in text.splitlines())
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return '\n'.join(re.sub(r'(?<!:)//.*', '', line) for line in text.splitlines())


def sources():
    yield from sorted(COMPONENT.glob('*.h'))
    yield from sorted(COMPONENT.glob('*.cpp'))
    yield from sorted(PACKAGES.rglob('*.yaml'))


class OneLayer(unittest.TestCase):
    def test_nothing_outside_the_layer_asks_which_glass_it_is_on(self):
        for path in sources():
            # hw.cpp reads the inks for the hello to the app, which is how the app and the editor learn the kind.
            if path.name in LAYER or path.name == 'hw.cpp':
                continue
            for number, line in enumerate(code(path).splitlines(), 1):
                found = ASKS_THE_GLASS.search(line)
                self.assertIsNone(found, f'{path.relative_to(ROOT)}:{number}: `{found and found.group(0)}` asks which glass this is. '
                                         'Ask theme_parts.h for the part instead (a new part goes into both stylesheets), '
                                         'or screen_motion::still() for what moves: docs/GLASS_KINDS.md')
        hw = code(COMPONENT / 'hw.cpp')
        self.assertEqual(len(ASKS_THE_GLASS.findall(hw)), 1, 'hw.cpp reads glass_kind::inks() once, for the hello')

    def test_each_consequence_is_asked_where_it_belongs(self):
        for name, allowed in CONSEQUENCES.items():
            for path in sources():
                if path.name == 'glass_kind.h' or name not in code(path):
                    continue
                self.assertIn(path.name, allowed, f'{path.relative_to(ROOT)} asks {name}(): {sorted(allowed)} do, and hand it on '
                                                  '(screen_motion::still(), the binder\'s hooks): docs/GLASS_KINDS.md')

    def test_shades_is_asked_by_the_few_that_leave_something_out(self):
        askers = {path.name for path in sources() if path.name not in LAYER and 'theme::shades()' in code(path)}
        self.assertEqual(askers, set(SHADES), 'theme::shades() is for leaving a part out where the glass shows no shade, never for '
                                              'a colour or a ground (those are parts of theme_parts.h). A new asker is named in '
                                              'SHADES with what it leaves out.')

    def test_the_binder_hands_the_kind_on_and_names_no_paper(self):
        core = code(PACKAGES / 'core.yaml')
        self.assertIn('glass.keeps = []() { return glass_kind::keeps(); };', core)
        self.assertIn('settings_screen::lit = glass_kind::lit();', core)
        self.assertNotIn('set_paper', core, 'the theme reads the kind of glass itself (theme::inked)')
        self.assertIn('glass_moment::finger(true', core)
        self.assertIn('glass_moment::finger(false', core)
        self.assertFalse((COMPONENT / 'paper_screen.h').exists(), 'glass_kind.h is the one way to the paper glass')


class TwoStylesheets(unittest.TestCase):
    def setUp(self):
        self.parts = (COMPONENT / 'theme_parts.h').read_text()
        self.lit = (COMPONENT / 'theme_lit.h').read_text()
        self.ink = (COMPONENT / 'theme_ink.h').read_text()

    def test_every_part_is_in_both_stylesheets(self):
        forked = set(re.findall(r'THEME_ON_GLASS\((\w+)\(', self.parts))
        self.assertGreater(len(forked), 40, 'the parts of theme_parts.h')
        for name in sorted(forked):
            for sheet, text in (('theme_lit.h', self.lit), ('theme_ink.h', self.ink)):
                self.assertRegex(text, rf'(?m)^(?:inline|constexpr) [\w:]+ {name}\(', f'{sheet} has no `{name}`: a part is in both stylesheets')

    def test_a_stylesheet_has_no_part_the_vocabulary_lacks(self):
        forked = set(re.findall(r'THEME_ON_GLASS\((\w+)\(', self.parts))
        # What a stylesheet keeps for itself: the tones it builds its parts from.
        own = {'theme_lit.h': {'tone', 'calendar_past'}, 'theme_ink.h': {'paper', 'ink', 'under'}}
        for sheet, text in (('theme_lit.h', self.lit), ('theme_ink.h', self.ink)):
            for name in set(re.findall(r'(?m)^(?:inline|constexpr) [\w:]+ (\w+)\(', text)) - own[sheet]:
                self.assertIn(name, forked, f'{sheet}: `{name}` is no part of theme_parts.h, so no card can ask for it')

    def test_the_fork_is_one_macro_and_a_lit_build_has_one_arm(self):
        self.assertIn('#define THEME_ON_GLASS(part) (inked() ? on_ink::part : on_lit::part)', self.parts)
        self.assertIn('#define THEME_ON_GLASS(part) (on_lit::part)', self.parts)
        self.assertRegex(self.parts, r'#ifdef GLASS_MAY_BE_INK\n#include "theme_ink\.h"', 'the ink stylesheet only where the build may be ink')
        # ESPHome includes every header of a component by itself too. Read alone the three part files are empty: each
        # is fenced by a word only its reader says, and none uses `#pragma once`, which would make a first, empty
        # reading the last.
        self.assertIn('#if defined(THEME_READS_ITS_PARTS) && !defined(THEME_PARTS_READ)', self.parts)
        self.assertIn('#if defined(THEME_READS_A_STYLESHEET) && !defined(THEME_LIT_STYLESHEET)', self.lit)
        self.assertIn('#if defined(THEME_READS_A_STYLESHEET) && defined(GLASS_MAY_BE_INK) && !defined(THEME_INK_STYLESHEET)', self.ink)
        for name, text in (('theme_parts.h', self.parts), ('theme_lit.h', self.lit), ('theme_ink.h', self.ink)):
            self.assertNotIn('#pragma once', text, f'{name} is read where the theme reads it, and is empty anywhere else')
        # Nothing in the vocabulary decides by itself: every line that names a stylesheet goes through the fork.
        for number, line in enumerate(code(COMPONENT / 'theme_parts.h').splitlines(), 1):
            if 'on_ink::' in line or 'on_lit::' in line:
                self.assertIn('#define THEME_ON_GLASS', line, f'theme_parts.h:{number}: a part names its stylesheet through THEME_ON_GLASS')
        self.assertNotIn('inked()', code(COMPONENT / 'theme_lit.h'), 'the lit stylesheet does not ask: it is the lit one')
        self.assertNotIn('inked()', code(COMPONENT / 'theme_ink.h'), 'the ink stylesheet does not ask: it is the ink one')

    def test_the_still_pass_is_only_in_a_build_that_may_be_ink(self):
        still = (COMPONENT / 'still_glass_lvgl.h').read_text()
        self.assertRegex(still, r'#include "glass_kind\.h"\n\n#ifdef GLASS_MAY_BE_INK')
        self.assertIn('inline void watch() {}', still, 'an empty call on a build that is never ink')


if __name__ == '__main__':
    unittest.main()
