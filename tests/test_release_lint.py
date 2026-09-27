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


def firmware_series(headings):
    """(problem or None, the newest shared firmware) of CHANGELOG headings, top to bottom: oldest first, a heading names
    the shared firmware again (a release of the app alone) or a number above every one before it; a firmware for some
    boards alone always takes a new number and names real board keys (app 0.3.20, docs/BOARD_RELEASES.md)."""
    shared, highest = None, None
    for version, rest in reversed(headings):
        firmware = FIRMWARE_IN_HEADING.search(rest)
        if not firmware:
            continue
        number, boards = parse_firmware(firmware.group(1)), firmware.group(2)
        fresh = highest is None or number > highest
        if boards:
            if not fresh:
                return (f'CHANGELOG {dotted(version)}: a fix for {boards} needs a firmware number above '
                        f'{dotted(highest)}, the highest one so far'), None
            for board in boards.split(', '):
                if board not in BOARD_KEYS:
                    return f'CHANGELOG {dotted(version)} names firmware for {board}, which is no board key', None
        else:
            if not (number == shared or fresh):
                return (f'CHANGELOG {dotted(version)}: shared firmware {firmware.group(1)} is neither the one before '
                        f'({dotted(shared) if shared else "none"}) nor above {dotted(highest)}, the highest so far'), None
            shared = number
        highest = number if highest is None else max(highest, number)
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

    def test_firmware_numbers_are_one_rising_series(self):
        """Oldest first, a heading names the shared firmware it ships with again (a release of the app alone) or a number
        above every one before it. A number is never used twice: a screen on a board's own fix would otherwise read as
        up to date, and its feature gates as newer, when the next shared release takes the same number (app 0.3.20)."""
        problem, shared = firmware_series(app_headings())
        self.assertIsNone(problem)
        self.assertEqual(shared, FIRMWARE_VERSION, 'the newest shared firmware in the CHANGELOG is core.FIRMWARE_VERSION')

    def test_the_series_rule_catches_a_number_used_twice(self):
        """The rule on made-up histories, so a change to it can't quietly turn it into a test of nothing."""
        def heading(app, firmware):
            return (tuple(map(int, app.split('.'))), f' (firmware {firmware})')
        board = BOARD_KEYS[-1]
        good = [heading('0.3.22', '0.3.12'), heading('0.3.21', f'0.3.11 for {board}'), heading('0.3.20', '0.3.10'),
                heading('0.3.19', '0.3.10'), heading('0.3.18', '0.3.9')]
        self.assertEqual(firmware_series(good), (None, '0.3.12'))
        # The shared release after a board's own 0.3.11 took 0.3.11 again: that board's screens would stay behind.
        reused = [heading('0.3.22', '0.3.11'), *good[1:]]
        self.assertIn('neither', firmware_series(reused)[0])
        # A board fix that takes a number already out.
        behind = [heading('0.3.21', f'0.3.10 for {board}'), *good[2:]]
        self.assertIn('above 0.3.10', firmware_series(behind)[0])
        # A board key the catalog does not have.
        unknown = [heading('0.3.21', '0.3.11 for nosuchboard'), *good[2:]]
        self.assertIn('nosuchboard', firmware_series(unknown)[0])
        # An app release while a board is ahead names the shared firmware again, which is fine.
        self.assertEqual(firmware_series([heading('0.3.22', '0.3.10'), *good[1:]]), (None, '0.3.10'))

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
