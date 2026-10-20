"""What a screen's own override YAML hangs on stays where it is (app 0.2.127+).

Owners change their hardware through Override YAML (docs/EASY_SETUP.md): a package loaded after the board's, that
`!extend`s or `!remove`s a part by its id or sets a substitution. Those overrides live on the owners' own Home Assistant,
where no test of ours can see them, so the ids and names they hang on are a promise: a board may move a part to another
file (ESPHome finds an id wherever it is), but not rename it or take it away. The overrides people shared in GitHub
issues are kept in tests/fixtures/overrides/, one file per board and case; tools/check.sh --firmware has ESPHome read
each of them on its board, and this test keeps what they name.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures' / 'overrides'
# The parts every board names the same way, for overrides and for the shared tree: its display, its touch panel, the
# output that drives its backlight and the light on it.
EVERY_BOARD = ('my_display', 'ts_touch', 'gpio_backlight_pwm', 'back_light')
# And what one family of boards has on top, named by the hardware file that brings it: the Waveshare's backlight line on
# its CH422G expander (GitHub #22).
SOME_BOARDS = {'backlight_line': 'waveshare-ch422g.yaml'}
# The substitutions a screen's own YAML may set, per board that offers them (docs/EASY_SETUP.md).
KNOBS = {
    'cyd': ('DISPLAY_MODEL', 'DISPLAY_DATA_RATE', 'DISPLAY_INVERT_COLORS', 'BACKLIGHT_FREQUENCY'),
    'guition': ('BACKLIGHT_FREQUENCY',),
    'waveshare4b': ('BACKLIGHT_FREQUENCY',),
    'tab5': ('DISPLAY_MODEL',),
    'waveshare43': ('FLASH_SIZE',),
}


def board_of_fixture(path):
    return max((board for board in profiles.BOARDS if path.stem.startswith(board + '-')), key=len)


def defined_ids(board):
    """Every id the board's chain defines (not an !extend or !remove of one)."""
    text = profiles.text(profiles.PROFILES[list(profiles.BOARDS).index(board)])
    text = '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('#'))
    return set(re.findall(r'(?m)^\s*(?:- )?id: ([a-z_0-9]+)\s*$', text))


class Overrides(unittest.TestCase):
    def test_there_is_a_case_for_every_board(self):
        boards = {board_of_fixture(path) for path in FIXTURES.glob('*.yaml')}
        self.assertEqual(boards, set(profiles.BOARDS))

    def test_every_part_an_override_names_is_there(self):
        for path in sorted(FIXTURES.glob('*.yaml')):
            board = board_of_fixture(path)
            text = path.read_text()
            ids = defined_ids(board)
            for named in re.findall(r'id: !(?:extend|remove) ([a-z_0-9]+)', text):
                self.assertIn(named, ids, f'{path.name}: {board} no longer has {named}')
            for named in re.findall(r'(?m)^\s+output: ([a-z_0-9]+)$', text):
                self.assertIn(named, ids, f'{path.name}: {board} no longer has {named}')

    def test_every_substitution_an_override_sets_is_read(self):
        # A substitution nobody reads is set without a word from ESPHome, and the override quietly does nothing.
        for path in sorted(FIXTURES.glob('*.yaml')):
            board = board_of_fixture(path)
            block = re.search(r'^substitutions:\n(.*?)(?=^[a-z_0-9]+:|\Z)', path.read_text(), re.M | re.S)
            if not block:
                continue
            values = profiles.board_values(board)
            for name in re.findall(r'(?m)^  ([A-Z_0-9]+):', block[1]):
                self.assertIn(name, values, f'{path.name}: {board} does not read {name}')

    def test_the_parts_every_board_names_the_same_way(self):
        for board in profiles.BOARDS:
            ids = defined_ids(board)
            for part in EVERY_BOARD:
                self.assertIn(part, ids, f'{board} has no {part}')
            chain = [path.name for path in profiles.chain(profiles.BOARDS[board])]
            for part, hardware in SOME_BOARDS.items():
                self.assertEqual(part in ids, hardware in chain, f'{board}: {part}')
        # The boards that have it today, and so the overrides of GitHub #22.
        self.assertIn('backlight_line', defined_ids('waveshare43'))
        self.assertIn('backlight_line', defined_ids('waveshare7'))

    def test_the_knobs_a_board_offers_reach_its_hardware(self):
        for board, knobs in KNOBS.items():
            values = profiles.board_values(board)
            own = profiles.BOARDS[board].read_text()
            for knob in knobs:
                self.assertIn(knob, values, f'{board} does not offer {knob}')
                self.assertIn('${' + knob + '}', own, f'{board} offers {knob} but no part of it reads it')


if __name__ == '__main__':
    unittest.main()
