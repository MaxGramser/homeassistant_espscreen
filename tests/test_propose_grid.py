"""tools/propose_grid.py, which tools/new_board.py takes a new board's grid from: never a grid the firmware refuses."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import propose_grid  # noqa: E402


class TheCeiling(unittest.TestCase):
    def test_it_is_the_firmwares(self):
        # Every one of the four ceilings in grid.yaml is the same number, and the proposal takes it from there.
        grid = (ROOT / 'packages/looks/shared/grid.yaml').read_text()
        ceilings = re.findall(r'GRID_MAX_(?:COLUMNS|ROWS)(?:_PORTRAIT)?: \$\{ \[(\d+),', grid)
        self.assertEqual(len(ceilings), 4)
        self.assertEqual({int(c) for c in ceilings}, {propose_grid.GRID_CEILING})

    def test_tall_glass_stops_there(self):
        # The reTerminal D1001 standing up (800 x 1280 at 8 inches) would take nine rows of the standard look's cards.
        tall = propose_grid.propose(800, 1280, 8, look='standard')
        self.assertEqual((tall['cols'], tall['rows']), (3, propose_grid.GRID_CEILING))
        for w, h, inch in ((800, 1280, 8), (720, 1280, 5), (600, 1920, 7), (1920, 1200, 10.1), (2560, 1600, 13)):
            with self.subTest(glass=(w, h, inch)):
                proposal = propose_grid.propose(w, h, inch)
                self.assertLessEqual(max(proposal['cols'], proposal['rows']), propose_grid.GRID_CEILING)


if __name__ == '__main__':
    unittest.main()
