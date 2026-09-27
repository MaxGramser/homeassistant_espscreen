"""Release lint (app 0.2.78): the version numbers of a release agree, and the packages fetch only fonts that exist.

Every push to main is a release (docs/RELEASING.md), so these run with the rest of the suite in tools/check.sh and CI.
Standard library only.
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
from core import BOARD_KEYS, FIRMWARE_VERSION, SHAPES, firmware_target, parse_firmware  # noqa: E402

CHANGELOG = ROOT / 'screen_manager/CHANGELOG.md'
# An app release: "## 0.2.76 (firmware 0.2.63)"; the oldest ones name no firmware. The two "## Firmware 0.2.1x"
# sections are firmware-only releases between app 0.2.11 and 0.2.12 and carry no app version, so they don't count.
APP_HEADING = re.compile(r'^## (\d+)\.(\d+)\.(\d+)\b(.*)$', re.M)
# A firmware for some boards alone names them (app 0.3.20): "(firmware 0.3.10 for waveshare4b)".
FIRMWARE_IN_HEADING = re.compile(r'\(firmware (\d+\.\d+\.\d+)(?: for ([a-z0-9]+(?:, [a-z0-9]+)*))?\)')
# The published entries (packages/<board>.yaml) point ${FONT_DIR} at the raw GitHub URL of fonts/ on main.
FONT_URL = re.compile(r'https://raw\.githubusercontent\.com/MaxGramser/homeassistant_espscreen/[^/\s"\']+/(fonts/[^"\'\s]+)')


def app_headings():
    """[(version tuple, text after the version)] of the CHANGELOG, top to bottom."""
    return [((int(a), int(b), int(c)), rest) for a, b, c, rest in APP_HEADING.findall(CHANGELOG.read_text())]


def dotted(version):
    return '.'.join(map(str, version))


# The last shared firmware counted in the last number. From the next one on (app 0.3.20) the middle number counts the
# core and the last one a board's revisions on top of it: a shared release is X.Y.0, a board's fix X.Y.1, X.Y.2.
LAST_OLD_COUNT = (0, 3, 10)


def firmware_series(headings):
    """(problem or None, the newest shared firmware) of CHANGELOG headings, top to bottom (docs/BOARD_RELEASES.md "How
    the version numbers work"). Oldest first:
    - a heading names the shared firmware again (a release of the app alone), or a newer one; after LAST_OLD_COUNT a new
      shared number raises the core (the middle number) and ends in .0, and before it just rises, as it always did;
    - a firmware for some boards alone keeps the core of the shared firmware, takes a revision above it and above each
      of those boards' own revision so far on that core, and names real board keys."""
    shared, revisions = None, {}
    for version, rest in reversed(headings):
        firmware = FIRMWARE_IN_HEADING.search(rest)
        if not firmware:
            continue
        number, boards, where = parse_firmware(firmware.group(1)), firmware.group(2), f'CHANGELOG {dotted(version)}'
        if boards:
            names = boards.split(', ')
            unknown = [board for board in names if board not in BOARD_KEYS]
            if unknown:
                return f'{where} names firmware for {", ".join(unknown)}, which is no board key', None
            if shared is None or number[:2] != shared[:2] or number[2] <= shared[2]:
                return (f'{where}: a fix for {boards} is a board revision on the shared core, '
                        f'{dotted((*shared[:2], shared[2] + 1)) if shared else "X.Y.1"} or higher, not {firmware.group(1)}'), None
            for board in names:
                if board in revisions and number <= revisions[board]:
                    return (f'{where}: {board} was at {dotted(revisions[board])} already; its next fix takes a higher '
                            f'revision than {firmware.group(1)}'), None
                revisions[board] = number
        elif number != shared:
            highest = max([shared, *revisions.values()], default=None) if shared else None
            if highest is not None and number <= highest:
                return (f'{where}: shared firmware {firmware.group(1)} is neither the one before ({dotted(shared)}) nor '
                        f'above {dotted(highest)}, the highest so far'), None
            if number > LAST_OLD_COUNT and (number[2] != 0 or (shared and number[:2] <= shared[:2])):
                return (f'{where}: a new shared firmware raises the core and starts at .0, '
                        f'{dotted((shared[0], shared[1] + 1, 0)) if shared else "X.Y.0"}, not {firmware.group(1)}'), None
            shared, revisions = number, {}
    return None, dotted(shared) if shared else None


class ReleaseVersionTests(unittest.TestCase):
    def test_config_version_is_the_newest_changelog_entry(self):
        match = re.search(r'^version:\s*["\']?([^"\'\s]+)["\']?\s*$', (ROOT / 'screen_manager/config.yaml').read_text(), re.M)
        self.assertIsNotNone(match, 'screen_manager/config.yaml has no version line')
        headings = app_headings()
        self.assertTrue(headings, 'screen_manager/CHANGELOG.md has no "## x.y.z" heading')
        self.assertEqual(match.group(1), dotted(headings[0][0]),
                         'Home Assistant offers the update by config.yaml: bump it together with a new CHANGELOG entry')

    def test_newest_entry_names_the_shipped_firmware(self):
        version, rest = app_headings()[0]
        firmware = FIRMWARE_IN_HEADING.search(rest)
        if firmware and not firmware.group(2):
            self.assertEqual(firmware.group(1), FIRMWARE_VERSION,
                             f'CHANGELOG {dotted(version)} names firmware {firmware.group(1)}, core.FIRMWARE_VERSION is {FIRMWARE_VERSION}')
        elif firmware:
            # A release of a fix for some boards alone: exactly what those boards build now.
            for board in firmware.group(2).split(', '):
                self.assertEqual(firmware.group(1), firmware_target(board),
                                 f'CHANGELOG {dotted(version)} names firmware {firmware.group(1)} for {board}, '
                                 f'which builds {firmware_target(board)}')

    def test_firmware_numbers_follow_the_core_and_board_count(self):
        """The middle number counts the core and the last one a board's revisions on it, so a feature gate (a shared
        X.Y.0) never reads a board fix as a newer core, and a board fix is never mistaken for what another board has."""
        problem, shared = firmware_series(app_headings())
        self.assertIsNone(problem)
        self.assertEqual(shared, FIRMWARE_VERSION, 'the newest shared firmware in the CHANGELOG is core.FIRMWARE_VERSION')

    def test_the_series_rule_on_made_up_histories(self):
        """The rule on made-up histories, so a change to it can't quietly turn it into a test of nothing."""
        def heading(app, firmware):
            return (tuple(map(int, app.split('.'))), f' (firmware {firmware})')
        board, other = BOARD_KEYS[-1], BOARD_KEYS[0]
        # The way over, as it went: shared 0.3.10 is the last of the old count, a board fix on it is 0.3.11, the next
        # shared release is 0.4.0, then board revisions count per board on core 4 (two boards may both be at 0.4.1).
        good = [heading('0.3.26', '0.5.0'), heading('0.3.25', f'0.4.2 for {board}'), heading('0.3.24', f'0.4.1 for {other}'),
                heading('0.3.23', f'0.4.1 for {board}'), heading('0.3.22', '0.4.0'), heading('0.3.21', f'0.3.11 for {board}'),
                heading('0.3.20', '0.3.10'), heading('0.3.19', '0.3.9'), heading('0.3.18', '0.3.8')]
        self.assertEqual(firmware_series(good), (None, '0.5.0'))
        # An app release while a board is ahead names the shared firmware again, which is fine.
        self.assertEqual(firmware_series([heading('0.3.27', '0.5.0'), *good]), (None, '0.5.0'))
        # A shared release in the old count after the change: it would read as a board revision.
        self.assertIn('raises the core', firmware_series([heading('0.3.21', '0.3.11'), *good[6:]])[0])
        self.assertIn('raises the core', firmware_series([heading('0.3.27', '0.5.1'), *good])[0])
        # A shared release that takes the number of a board fix: that board's screens would stay behind.
        self.assertIn('neither', firmware_series([heading('0.3.22', '0.3.11'), *good[5:]])[0])
        # A board fix on another core, at the core's own number, or at a revision its board already had.
        self.assertIn('board revision on the shared core', firmware_series([heading('0.3.27', f'0.4.3 for {board}'), *good])[0])
        self.assertIn('board revision on the shared core', firmware_series([heading('0.3.27', f'0.5.0 for {board}'), *good])[0])
        self.assertIn('already', firmware_series([heading('0.3.25', f'0.4.1 for {board}'), *good[3:]])[0])
        # A board key the catalog does not have.
        self.assertIn('nosuchboard', firmware_series([heading('0.3.27', '0.5.1 for nosuchboard'), *good])[0])

    def test_a_board_ahead_of_the_shared_firmware_has_its_release_notes(self):
        """A board file that sets its own SCREEN_FIRMWARE_VERSION went out with a heading saying so, which is also what
        What's new shows its screens."""
        named = set()
        for _, rest in app_headings():
            firmware = FIRMWARE_IN_HEADING.search(rest)
            if firmware and firmware.group(2):
                named |= {(firmware.group(1), board) for board in firmware.group(2).split(', ')}
        for board in BOARD_KEYS:
            if firmware_target(board) != FIRMWARE_VERSION:
                self.assertIn((firmware_target(board), board), named,
                              f'{board} builds firmware {firmware_target(board)}: the CHANGELOG needs '
                              f'"(firmware {firmware_target(board)} for {board})"')

    def test_changelog_versions_are_unique_and_newest_first(self):
        versions = [version for version, _ in app_headings()]
        duplicates = sorted({dotted(v) for v in versions if versions.count(v) > 1})
        self.assertEqual(duplicates, [], 'a CHANGELOG version appears twice')
        for newer, older in zip(versions, versions[1:]):
            self.assertGreater(newer, older, f'CHANGELOG {dotted(newer)} stands above {dotted(older)}')


class PackageFontTests(unittest.TestCase):
    def test_every_font_a_package_fetches_is_in_the_tree(self):
        seen = 0
        for package in profiles.PACKAGES:
            # The shared core names its fonts as ${FONT_DIR}/...; the published entry says where that is (app 0.2.84+).
            for path in FONT_URL.findall(profiles.merged(package)):
                seen += 1
                self.assertTrue((ROOT / path).is_file(), f'{package} fetches {path}, which is not in the tree')
        # A changed URL form must not turn this into a test of nothing.
        self.assertGreater(seen, 0, 'no fonts/... URL found in packages/*.yaml')


if __name__ == '__main__':
    unittest.main()
