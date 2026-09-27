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


CORE = tuple(map(int, FIRMWARE_VERSION.split('.')))


class TheReleasePlan(unittest.TestCase):
    def following(self):
        """A board's next number while no board is ahead: the core's, one board revision up."""
        return affected_boards.dotted((*CORE[:2], CORE[2] + 1))

    def test_the_core_counts_in_the_middle_and_a_board_at_the_end(self):
        """docs/BOARD_RELEASES.md "How the version numbers work": a shared release raises the core and starts at .0, a
        board release keeps the core and takes a revision above what those boards build now."""
        shared, board = affected_boards.next_numbers(['cyd'])
        self.assertEqual(shared, (CORE[0], CORE[1] + 1, 0))
        self.assertEqual(board, (*CORE[:2], CORE[2] + 1))
        # Counted from what a base shows: core 0.4.0 with the Waveshare 4B at its second fix.
        fourb = str(profiles.BOARDS['waveshare4b'].relative_to(ROOT))
        base = {str(profiles.CORE.relative_to(ROOT)): 'substitutions:\n  SCREEN_FIRMWARE_VERSION: "0.4.0"\n',
                fourb: 'substitutions:\n  BOARD_ID: "waveshare4b"\n  SCREEN_FIRMWARE_VERSION: "0.4.2"\n'}
        read = lambda path: base.get(path, 'substitutions:\n')
        # The board that is ahead counts on from its own revision; with another board, both take the one number.
        self.assertEqual(affected_boards.next_numbers(['waveshare4b'], read)[1], (0, 4, 3))
        self.assertEqual(affected_boards.next_numbers(['cyd', 'waveshare4b'], read)[1], (0, 4, 3))
        self.assertEqual(affected_boards.next_numbers(['cyd'], read)[1], (0, 4, 1))
        # The shared release overtakes them all, and from the old count 0.3.9 it is 0.4.0.
        self.assertEqual(affected_boards.next_numbers(['cyd', 'waveshare4b'], read)[0], (0, 5, 0))
        old = {str(profiles.CORE.relative_to(ROOT)): 'substitutions:\n  SCREEN_FIRMWARE_VERSION: "0.3.9"\n'}
        self.assertEqual(affected_boards.next_numbers((), lambda path: old.get(path, ''))[0], (0, 4, 0))

    def test_the_plan_says_when_the_number_is_set(self):
        """Counted from the base, so a bump already made reads as done, not as the next one after it."""
        core, fourb = str(profiles.CORE.relative_to(ROOT)), str(profiles.BOARDS['waveshare4b'].relative_to(ROOT))
        tree = lambda core_version, board_version=None: (lambda path: {
            core: f'substitutions:\n  SCREEN_FIRMWARE_VERSION: "{core_version}"\n',
            fourb: 'substitutions:\n  BOARD_ID: "waveshare4b"\n'
                   + (f'  SCREEN_FIRMWARE_VERSION: "{board_version}"\n' if board_version else '')}.get(path, 'substitutions:\n'))
        with mock.patch.object(affected_boards, 'read_now', tree('0.5.0')):
            text = affected_boards.plan(reach('packages/core.yaml'), read_base=tree('0.4.0', '0.4.2'))
        self.assertIn('the number is 0.5.0 (set: every board builds it)', text)
        with mock.patch.object(affected_boards, 'read_now', tree('0.4.0', '0.4.3')):
            text = affected_boards.plan(reach(fourb), read_base=tree('0.4.0', '0.4.2'))
        self.assertIn('the board revision goes up: 0.4.3 (set: those boards build it)', text)
        with mock.patch.object(affected_boards, 'read_now', tree('0.4.0', '0.4.2')):
            self.assertNotIn('(set:', affected_boards.plan(reach(fourb), read_base=tree('0.4.0', '0.4.2')))

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
        self.assertIn(f'FIRMWARE_VERSION: "{affected_boards.dotted((CORE[0], CORE[1] + 1, 0))}"', text)
        self.assertIn('tools/check.sh --firmware (every board', text)


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
        versions = affected_boards.built_versions(self.files('0.4.0', '0.4.1'))
        self.assertEqual(versions['waveshare4b'], (0, 4, 1))
        self.assertEqual(versions['cyd'], (0, 4, 0))

    def verdict(self, reached, before, after):
        with mock.patch.object(affected_boards, 'built_versions',
                               side_effect=[affected_boards.built_versions(before), affected_boards.built_versions(after)]):
            return affected_boards.unraised({'x': set(reached)}, 'base')

    def test_a_board_fix_without_a_new_number_is_caught(self):
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.4.0'), self.files('0.4.0')), ['waveshare4b'])
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.4.0'), self.files('0.4.0', '0.4.1')), [])
        # A second fix for a board that is already ahead needs the next number again.
        self.assertEqual(self.verdict({'waveshare4b'}, self.files('0.4.0', '0.4.1'), self.files('0.4.0', '0.4.1')),
                         ['waveshare4b'])

    def test_a_shared_change_needs_every_board_raised(self):
        self.assertEqual(self.verdict(EVERY, self.files('0.4.0', '0.4.1'), self.files('0.5.0')), [])
        # The core went up but the board that was ahead kept its old line: that board stayed where it was.
        self.assertEqual(self.verdict(EVERY, self.files('0.4.0', '0.4.1'), self.files('0.5.0', '0.4.1')), ['waveshare4b'])
        self.assertEqual(sorted(self.verdict(EVERY, self.files('0.4.0'), self.files('0.4.0'))), sorted(EVERY))

    def test_a_new_board_needs_no_number(self):
        with mock.patch.object(affected_boards, 'built_versions',
                               side_effect=[affected_boards.built_versions(self.files('0.4.0')),
                                            affected_boards.built_versions(self.files('0.4.0'))]):
            self.assertEqual(affected_boards.unraised({'x': {'waveshare4b'}}, 'base', new={'waveshare4b'}), [])


class ABoardsOwnVersion(unittest.TestCase):
    def test_a_board_revision_on_the_shared_core(self):
        """The core's X.Y with a revision above its Z: the core it is built on, and one step on top."""
        problem = check_packages.firmware_problem
        self.assertIsNone(problem('0.4.0', {'packages/boards/a.yaml': '', 'packages/boards/b.yaml': '0.4.1', 'packages/boards/c.yaml': '0.4.1'}))
        self.assertIsNone(problem('0.4.0', {'packages/boards/b.yaml': '0.4.7'}))
        # The same number or lower is no revision.
        self.assertIn('no board revision', problem('0.4.0', {'packages/boards/b.yaml': '0.4.0'}))
        # A shared release took the board along: the old line names another core.
        self.assertIn('another core', problem('0.5.0', {'packages/boards/b.yaml': '0.4.1'}))
        # A board can't claim a core that has not shipped.
        self.assertIn('another core', problem('0.4.0', {'packages/boards/b.yaml': '0.5.1'}))
        self.assertIn('not X.Y.Z', problem('0.4.0', {'packages/boards/b.yaml': '0.4.1-fix'}))
        # The old count, before the core moved to the middle number: a board fix on 0.3.9 is 0.3.10.
        self.assertIsNone(problem('0.3.9', {'packages/boards/b.yaml': '0.3.10'}))
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
