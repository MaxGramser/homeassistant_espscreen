"""Firmware for one board (app 0.3.20, docs/BOARD_RELEASES.md): which boards a change reaches, what version a board may
state of its own, and the release plan tools/affected_boards.py prints from both.

Standard library and PyYAML only.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import affected_boards  # noqa: E402
import check_packages  # noqa: E402
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import FIRMWARE_VERSION, SHAPES, firmware_target  # noqa: E402

EVERY = set(profiles.BOARDS)


def reach(*paths):
    return affected_boards.sort(list(paths), 'HEAD')


class WhatAChangeReaches(unittest.TestCase):
    def test_a_board_file_reaches_its_board_alone(self):
        for board, path in profiles.BOARDS.items():
            name = str(path.relative_to(ROOT))
            self.assertEqual(reach(name)[name], {board}, name)

    def test_a_boards_entry_files_reach_that_board_alone(self):
        for board in profiles.BOARDS:
            for name in (f'checkout/{board}.yaml', f'packages/{board}.yaml'):
                self.assertEqual(reach(name)[name], {board}, name)

    def test_the_shared_parts_reach_every_board(self):
        for name in ('packages/core.yaml', 'components/smart_display/theme.h', 'components/smart_display/__init__.py',
                     'fonts/Roboto-400.ttf'):
            self.assertEqual(reach(name)[name], EVERY, name)

    def test_a_package_reaches_the_boards_that_include_it(self):
        """A feature, look, hardware or cells file reaches exactly the boards whose chain names it."""
        seen = 0
        for folder in ('features', 'looks', 'hardware', 'cells'):
            for path in sorted((ROOT / 'packages' / folder).glob('*.yaml')):
                name = str(path.relative_to(ROOT))
                wanted = {board for board in profiles.BOARDS
                          if path.resolve() in [p.resolve() for p in profiles.files(f'checkout/{board}.yaml')]}
                self.assertEqual(reach(name)[name], wanted, name)
                seen += 1
        self.assertGreater(seen, 10)
        # And one that really splits them: the resistive touch of the CYD is not the capacitive touch of the others.
        touch = reach('packages/features/capacitive-touch.yaml')['packages/features/capacitive-touch.yaml']
        self.assertTrue(touch and touch != EVERY and 'cyd' not in touch, touch)

    def test_the_app_the_editor_docs_and_tools_are_no_firmware(self):
        for name in ('screen_manager/app/core.py', 'screen_manager/config.yaml', 'screen_manager/CHANGELOG.md',
                     'web/src/store.ts', 'docs/BOARD_RELEASES.md', 'README.md', 'tools/check.sh', 'tests/test_updates.py',
                     'boards.yaml', 'screen_manager/app/boards.json', '.github/ISSUE_TEMPLATE/bug_report.yml',
                     'tools/generate_issue_templates.py'):
            self.assertEqual(reach(name)[name], set(), name)

    def test_a_translation_reaches_the_screens_only_through_its_screen_texts(self):
        """The firmware compiles the `screen` section in (components/smart_display/screen_text_gen.py); the add-on's own
        texts are no firmware."""
        name = 'screen_manager/translations/nl.json'
        now = json.loads((ROOT / name).read_text())
        editor_only = json.dumps({**now, 'addon': {**now.get('addon', {}), 'made_up': 'x'}})
        screen_too = json.dumps({**now, 'screen': {**now['screen'], 'made_up': 'x'}})
        with mock.patch.object(affected_boards, 'git', return_value=editor_only):
            self.assertEqual(reach(name)[name], set())
        with mock.patch.object(affected_boards, 'git', return_value=screen_too):
            self.assertEqual(reach(name)[name], EVERY)


class TheReleasePlan(unittest.TestCase):
    def following(self):
        highest = max(number for number, _ in affected_boards.firmware_numbers())
        return affected_boards.dotted((*highest[:2], highest[2] + 1))

    def test_no_firmware_is_an_app_release(self):
        text = affected_boards.plan(reach('screen_manager/app/core.py'))
        self.assertIn('No firmware change for a screen that exists', text)
        self.assertIn(f'(firmware {FIRMWARE_VERSION})', text)
        self.assertNotIn('--firmware --board', text)

    def test_one_board_gets_its_own_number_and_its_own_build(self):
        board = 'waveshare4b'
        path = str(profiles.BOARDS[board].relative_to(ROOT))
        text = affected_boards.plan(reach(path))
        self.assertIn(f'Firmware for {board} alone', text)
        self.assertIn(f'{path}: SCREEN_FIRMWARE_VERSION: "{self.following()}"', text)
        self.assertIn(f'(firmware {self.following()} for {board})', text)
        self.assertIn(f'tools/check.sh --firmware --board {board}', text)
        self.assertIn('Leave packages/core.yaml', text)

    def test_a_new_board_takes_no_number_and_updates_nothing(self):
        """A board no screen runs yet: built and rendered on its own, and the release is the app's (the catalog grows)."""
        board = 'hosyond40'
        paths = (str(profiles.BOARDS[board].relative_to(ROOT)), f'checkout/{board}.yaml', f'packages/{board}.yaml', 'boards.yaml')
        text = affected_boards.plan(reach(*paths), new={board})
        self.assertIn(f'New board: {board}', text)
        self.assertIn(f'tools/check.sh --firmware --board {board}', text)
        self.assertIn('No firmware change for a screen that exists', text)
        self.assertIn(f'(firmware {FIRMWARE_VERSION})', text)
        self.assertNotIn('SCREEN_FIRMWARE_VERSION: "', text)
        # A new board that also fixes an existing one: that one still gets its own number.
        text = affected_boards.plan(reach(*paths, 'checkout/cyd.yaml'), new={board})
        self.assertIn('Firmware for cyd alone', text)
        self.assertIn(f'(firmware {self.following()} for cyd)', text)

    def test_new_boards_are_the_ones_the_base_lacks(self):
        with mock.patch.object(affected_boards, 'git', return_value='packages/boards/cyd-2432s028.yaml\n'):
            self.assertEqual(affected_boards.new_boards('base'), EVERY - {'cyd'})

    def test_two_boards_are_named_together(self):
        text = affected_boards.plan(reach('checkout/cyd.yaml', 'checkout/guition.yaml'))
        self.assertIn(f'(firmware {self.following()} for cyd, guition)', text)
        self.assertIn('--board cyd --board guition', text)

    def test_a_shared_change_is_a_shared_release(self):
        text = affected_boards.plan(reach('packages/core.yaml', 'packages/boards/cyd-2432s028.yaml'))
        self.assertIn('Shared firmware: every board', text)
        self.assertIn(f'FIRMWARE_VERSION: "{self.following()}"', text)
        self.assertIn('tools/check.sh --firmware (every board', text)

    def test_the_next_number_is_above_every_number_so_far(self):
        numbers = [number for number, _ in affected_boards.firmware_numbers()]
        self.assertGreater(tuple(map(int, self.following().split('.'))), max(numbers))


class AForgottenNumber(unittest.TestCase):
    """tools/affected_boards.py --verify (a WARN in tools/check.sh): a fix whose board builds no higher number reaches new
    screens only, never the ones that already run it."""
    CORE = str(profiles.CORE.relative_to(ROOT))
    FOURB = str(profiles.BOARDS['waveshare4b'].relative_to(ROOT))

    def files(self, core, fourb=None):
        texts = {self.CORE: f'substitutions:\n  SCREEN_FIRMWARE_VERSION: "{core}"\n',
                 self.FOURB: 'substitutions:\n  BOARD_ID: "waveshare4b"\n'
                             + (f'  SCREEN_FIRMWARE_VERSION: "{fourb}"\n' if fourb else '')}
        return lambda path: texts.get(path, 'substitutions:\n')

    def test_built_versions_take_the_board_files_own_over_the_core(self):
        versions = affected_boards.built_versions(self.files('0.3.9', '0.3.10'))
        self.assertEqual(versions['waveshare4b'], (0, 3, 10))
        self.assertEqual(versions['cyd'], (0, 3, 9))

    def verdict(self, reached, before, after):
        with mock.patch.object(affected_boards, 'built_versions',
                               side_effect=[affected_boards.built_versions(before), affected_boards.built_versions(after)]):
            return affected_boards.unraised({'x': set(reached)}, 'base')

    def test_a_board_fix_without_a_new_number_is_caught(self):
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.3.9'), self.files('0.3.9')), ['waveshare4b'])
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.3.9'), self.files('0.3.9', '0.3.10')), [])
        # A second fix for a board that is already ahead needs the next number again.
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.3.9', '0.3.10'), self.files('0.3.9', '0.3.10')),
                         ['waveshare4b'])

    def test_a_shared_change_needs_every_board_raised(self):
        self.assertEqual(self.verdict(EVERY, self.files('0.3.9', '0.3.10'), self.files('0.3.11')), [])
        # The core went up but the board that was ahead kept a line at or below it: that board stayed where it was.
        self.assertEqual(self.verdict(EVERY, self.files('0.3.9', '0.3.10'), self.files('0.3.10', '0.3.10')), ['waveshare4b'])
        self.assertEqual(sorted(self.verdict(EVERY, self.files('0.3.9'), self.files('0.3.9'))), sorted(EVERY))

    def test_a_new_board_needs_no_number(self):
        with mock.patch.object(affected_boards, 'built_versions',
                               side_effect=[affected_boards.built_versions(self.files('0.3.9')),
                                            affected_boards.built_versions(self.files('0.3.9'))]):
            self.assertEqual(affected_boards.unraised({'x': {'waveshare4b'}}, 'base', new={'waveshare4b'}), [])


class ABoardsOwnVersion(unittest.TestCase):
    def test_only_above_the_shared_version(self):
        self.assertIsNone(check_packages.firmware_problem('0.3.9', {'packages/boards/a.yaml': '', 'packages/boards/b.yaml': '0.3.10'}))
        self.assertIn('not above', check_packages.firmware_problem('0.3.9', {'packages/boards/b.yaml': '0.3.9'}))
        self.assertIn('not above', check_packages.firmware_problem('0.3.11', {'packages/boards/b.yaml': '0.3.10'}))
        self.assertIn('not above', check_packages.firmware_problem('0.3.9', {'packages/boards/b.yaml': '0.3.10-fix'}))
        self.assertIn('X.Y.Z', check_packages.firmware_problem('0.3', {}))

    def test_what_a_board_builds_is_what_the_manager_offers(self):
        """boards.json carries each board's SCREEN_FIRMWARE_VERSION as its build works it out, and the manager offers
        exactly that; tools/generate_board_shapes.py --check keeps the file in step with the board files."""
        for board in profiles.BOARDS:
            built = profiles.board_values(board)['SCREEN_FIRMWARE_VERSION'].strip('"')
            self.assertEqual(SHAPES[board]['firmware'], built, board)
            self.assertEqual(firmware_target(board), built, board)
        self.assertEqual(profiles.substitutions_of(profiles.CORE)['SCREEN_FIRMWARE_VERSION'].strip('"'), FIRMWARE_VERSION)

    def test_a_board_files_own_version_wins_over_the_cores(self):
        """The precedence the manager's numbers rest on: a board file's substitution over the core's, as ESPHome merges
        them (docs/PROFILES.md "Which value wins"; checked against a real ESPHome config for app 0.3.20)."""
        board = 'waveshare4b'
        own = profiles.substitutions_of(profiles.BOARDS[board])
        with mock.patch.object(profiles, 'substitutions_of',
                               side_effect=lambda path, real=profiles.substitutions_of: (
                                   {**own, 'SCREEN_FIRMWARE_VERSION': '"9.9.9"'} if Path(path) == profiles.BOARDS[board]
                                   else real(path))):
            self.assertEqual(profiles.board_values(board)['SCREEN_FIRMWARE_VERSION'].strip('"'), '9.9.9')
            self.assertEqual(profiles.board_values('cyd')['SCREEN_FIRMWARE_VERSION'].strip('"'), FIRMWARE_VERSION)


if __name__ == '__main__':
    unittest.main()
