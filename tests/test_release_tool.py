"""tools/release.py (docs/RELEASING.md): the edits of a release commit, and the candidate the upgrade test builds.

Every edit runs on the real files of this tree, so a changed line format fails here before a release day.
Standard library and PyYAML only.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import firmware_count  # noqa: E402
import profiles  # noqa: E402
import release  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import changelog as whats_new  # noqa: E402
sys.path.insert(0, str(ROOT / 'tests'))
import test_release_lint  # noqa: E402

CHANGELOG = (ROOT / 'screen_manager/CHANGELOG.md').read_text()
CONFIG = (ROOT / 'screen_manager/config.yaml').read_text()
CORE_YAML = profiles.CORE.read_text()
CORE_PY = (ROOT / 'screen_manager/app/core.py').read_text()
WORK = '## Unreleased\n\n- **A new card.** It shows a thing.\n- A fix.\n\n'
SHARED = {'kind': 'shared', 'firmware': '0.99.0', 'boards': sorted(profiles.BOARDS)}


def without_unreleased(text):
    """The CHANGELOG as main has it: dev's "## Unreleased" section left out whole, its notes with its heading."""
    match = release.UNRELEASED.search(text)
    if not match:
        return text
    end = release.SECTION.search(text, match.end())
    return (text[:match.start()] + (text[end.start():] if end else '')).lstrip('\n')


class TheChangelog(unittest.TestCase):
    def test_the_notes_under_unreleased(self):
        self.assertEqual(release.unreleased(WORK + CHANGELOG), '- **A new card.** It shows a thing.\n- A fix.')
        self.assertIsNone(release.unreleased(without_unreleased(CHANGELOG)))

    def test_unreleased_becomes_the_release_heading(self):
        text = release.named(WORK + without_unreleased(CHANGELOG), release.heading('9.9.9', SHARED))
        self.assertTrue(text.startswith('## 9.9.9 (firmware 0.99.0)\n\n- **A new card.**'))
        # The lint and What's new read it as a release: the newest app heading, with its notes.
        self.assertEqual(test_release_lint.APP_HEADING.search(text).group(1, 2, 3), ('9', '9', '9'))
        newest = whats_new.parse(text)[0]
        self.assertEqual((newest['app'], newest['firmware'], newest['boards']), ('9.9.9', '0.99.0', []))
        self.assertEqual(newest['lines'], ['A new card. It shows a thing.', 'A fix.'])

    def test_whats_new_leaves_unreleased_out(self):
        """A test Home Assistant runs dev, whose CHANGELOG starts with "## Unreleased": What's new shows releases only."""
        parsed = whats_new.parse(WORK + without_unreleased(CHANGELOG))
        self.assertEqual(parsed[0]['app'], firmware_count.dotted(test_release_lint.app_headings()[0][0]))
        self.assertNotIn('A fix.', [line for section in parsed for line in section['lines']])

    def test_a_board_release_names_its_boards(self):
        line = release.heading('9.9.9', {'kind': 'boards', 'firmware': '0.51.1', 'boards': ['cyd', 'guition']})
        self.assertEqual(line, '## 9.9.9 (firmware 0.51.1 for cyd, guition)')
        self.assertEqual(test_release_lint.FIRMWARE_IN_HEADING.search(line).group(1, 2), ('0.51.1', 'cyd, guition'))
        self.assertEqual(release.title(line), 'Tessera 9.9.9 · firmware 0.51.1 for cyd, guition')
        self.assertEqual(release.title('## 9.9.9 (firmware 0.52.0)'), 'Tessera 9.9.9 · firmware 0.52.0')

    def test_no_notes_no_release(self):
        with self.assertRaisesRegex(release.Refusal, 'no "## Unreleased"'):
            release.named(without_unreleased(CHANGELOG), '## 9.9.9 (firmware 0.99.0)')
        with self.assertRaisesRegex(release.Refusal, 'no notes'):
            release.named('## Unreleased\n\n' + without_unreleased(CHANGELOG), '## 9.9.9 (firmware 0.99.0)')
        with self.assertRaisesRegex(release.Refusal, 'twice'):
            release.named(WORK + WORK + without_unreleased(CHANGELOG), '## 9.9.9 (firmware 0.99.0)')

    def test_the_section_of_a_version(self):
        version = firmware_count.dotted(test_release_lint.app_headings()[0][0])
        line, notes = release.section(CHANGELOG, version)
        self.assertTrue(line.startswith(f'## {version} '))
        self.assertTrue(notes)
        self.assertNotIn('\n## ', notes)


class TheIssues(unittest.TestCase):
    def test_the_issues_a_section_names(self):
        notes = ('- **A fix** ([#169](https://github.com/MaxGramser/homeassistant_espscreen/issues/169)). Also #170 and '
                 'again #169, a pull request https://github.com/MaxGramser/homeassistant_espscreen/pull/151, not '
                 'a colour like &#35;1 or a heading anchor docs/PAGES.md#updating, nor another repository '
                 'https://github.com/esphome/esphome/issues/9999.')
        self.assertEqual(release.issues_in(notes), [169, 170, 151])

    def test_a_real_section_reads(self):
        """The newest CHANGELOG section of this tree, so a changed link form fails here first."""
        version = firmware_count.dotted(test_release_lint.app_headings()[0][0])
        self.assertIsInstance(release.issues_in(release.section(CHANGELOG, version)[1]), list)


class TheNumbers(unittest.TestCase):
    def test_the_app_version_goes_up_by_one(self):
        version = release.version_of(CONFIG)
        following = release.next_version(version)
        self.assertGreater(firmware_count.parse(following), firmware_count.parse(version))
        changed = release.with_version(CONFIG, following)
        self.assertEqual(release.version_of(changed), following)
        self.assertIn(f'version: "{following}"', changed)
        self.assertEqual(len(changed.splitlines()), len(CONFIG.splitlines()))

    def test_the_shared_number_in_both_places(self):
        core = release.with_core_number(CORE_YAML, '0.99.0')
        self.assertEqual(profiles.substitutions_in(core)['SCREEN_FIRMWARE_VERSION'].strip('"'), '0.99.0')
        self.assertEqual(core.count('0.99.0'), 1)
        core_py = release.with_core_py_number(CORE_PY, '0.99.0')
        self.assertIn("\nFIRMWARE_VERSION = '0.99.0'\n", core_py)
        self.assertEqual(len(core_py.splitlines()), len(CORE_PY.splitlines()))

    def test_a_board_number_is_added_under_board_id_and_taken_out_again(self):
        for key, path in profiles.BOARDS.items():
            with self.subTest(board=key):
                text = path.read_text()
                own = release.with_board_number(text, '0.51.1', '9.9.9')
                self.assertEqual(profiles.substitutions_in(own)['SCREEN_FIRMWARE_VERSION'].strip('"'), '0.51.1')
                self.assertEqual(profiles.substitutions_in(own)['BOARD_ID'], profiles.substitutions_in(text)['BOARD_ID'])
                # Once more raises the same line instead of adding another.
                again = release.with_board_number(own, '0.51.2', '9.9.10')
                self.assertEqual(again.count('SCREEN_FIRMWARE_VERSION:'), own.count('SCREEN_FIRMWARE_VERSION:'))
                self.assertEqual(profiles.substitutions_in(again)['SCREEN_FIRMWARE_VERSION'].strip('"'), '0.51.2')
                # A shared release takes the line and its comment out, and nothing else.
                if 'SCREEN_FIRMWARE_VERSION' not in profiles.substitutions_in(text):
                    self.assertEqual(release.without_board_number(own), text)

    def test_the_form_a_board_number_had_in_a_release(self):
        """The Tab5's own line as app 0.4.66 shipped it, with the comment the next shared release took out with it."""
        before = ('substitutions:\n  # The key of this board file.\n  BOARD_ID: "tab5"\n'
                  "  # This board's own firmware revision (docs/BOARD_RELEASES.md): the ESP32-C6 (#150).\n"
                  '  # The next shared release takes this line out again.\n  SCREEN_FIRMWARE_VERSION: "0.39.1"\n'
                  '  DEVICE_NAME: "tab5-new"\n')
        self.assertEqual(release.without_board_number(before),
                         'substitutions:\n  # The key of this board file.\n  BOARD_ID: "tab5"\n  DEVICE_NAME: "tab5-new"\n')


class TheCandidate(unittest.TestCase):
    def test_every_published_entry_fetches_from_the_candidate(self):
        for package in [*profiles.PACKAGES, 'packages/bridge.yaml']:
            with self.subTest(package=package):
                text, changed = release.pointed_at((ROOT / package).read_text(), release.CANDIDATE)
                self.assertGreaterEqual(changed, 1)
                self.assertNotRegex(text, release.REF_MAIN)
                self.assertNotRegex(text, release.FONTS_MAIN)
                self.assertNotRegex(text, release.GITHUB_REF_MAIN)
                # The components and the fonts follow GITHUB_REF, whose default is now the candidate.
                self.assertIn(f'GITHUB_REF: "{release.CANDIDATE}"', text)
                self.assertIn('ref: ${GITHUB_REF}', text)
        cyd, _ = release.pointed_at((ROOT / 'packages/cyd.yaml').read_text(), release.CANDIDATE)
        self.assertIn('homeassistant_espscreen/${GITHUB_REF}/fonts', cyd)

    def test_nothing_else_in_the_packages_fetches_from_main(self):
        """The candidate only rewrites the published entries: any other package that named main would build main's."""
        for path in sorted((ROOT / 'packages').rglob('*.yaml')):
            if path.parent == ROOT / 'packages':
                continue
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_text()
                self.assertNotRegex(text, release.REF_MAIN)
                self.assertNotRegex(text, release.FONTS_MAIN)

    @unittest.skipUnless(shutil.which('git') and (ROOT / '.git').exists(), 'needs the git history')
    def test_the_candidate_commit_is_head_with_the_entries_pointed(self):
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / 'clone'
            subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(ROOT), str(clone)], check=True)
            # A commit wants a name: CI's runner has none of its own, where the maintainer's machine does.
            for key, value in (('user.name', 'Release test'), ('user.email', 'release-test@example.invalid')):
                subprocess.run(['git', 'config', key, value], cwd=clone, check=True)
            head = release.git('rev-parse', 'HEAD', cwd=clone)
            commit, pointed = release.candidate_commit(head, cwd=clone)
            self.assertEqual(release.git('rev-parse', f'{commit}^', cwd=clone), head)
            changed = release.git('diff', '--name-only', head, commit, cwd=clone).split()
            self.assertEqual(len(changed), pointed)
            self.assertTrue(all(path.startswith('packages/') and path.count('/') == 1 for path in changed))
            for path in changed:
                text = release.git('show', f'{commit}:{path}', cwd=clone)
                self.assertNotRegex(text, release.REF_MAIN)
                self.assertIn(release.CANDIDATE, text)


if __name__ == '__main__':
    unittest.main()
