"""The tests, as a package only so that `python -m unittest tests.test_x` works from the root of a working copy.

A test imports its helpers (firmware_sources, manager_fixtures, another test's fakes) by their plain name, one way,
and none puts tests/ on sys.path itself. Every way of running them has tests/ there: `python -m unittest discover -s
tests` (tools/check.sh) and `python tests/test_x.py` put it there, and `python -m unittest tests.test_x` (one test,
the way tools/release.py and tools/check.sh run single tests) gets it here. docs/TESTING.md, "Running a test"."""
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
