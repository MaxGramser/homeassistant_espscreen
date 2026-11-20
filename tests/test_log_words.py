"""Log-only headers (components/smart_display/*_log.h): their words are read in the log, never shown on a screen.

The translations' lint (tools/i18n.py lint) leaves them out by rule, so a log's words need no line each in LINT_KEEP.
That rule may hide nothing a screen shows: here, a *_log.h knows nothing that draws or translates, and every other
header is still read by the lint."""
import re
import unittest
from pathlib import Path

from tool_modules import tool

ROOT = Path(__file__).resolve().parents[1]
i18n = tool('i18n')  # the lint's script, not the app's module of the same name

COMPONENT = ROOT / 'components' / 'smart_display'
# What a header needs to put words on the glass: LVGL, the translations (tr(), txt::), or another part of the firmware
# that does (an include of anything but the standard library).
DRAWS = re.compile(r'\blv_|lvgl|\btr\(|\btxt::|#include\s+"')


class LogOnlyHeaders(unittest.TestCase):
    def test_a_log_header_knows_nothing_that_draws_or_translates(self):
        logs = sorted(COMPONENT.glob('*_log.h'))
        self.assertIn(COMPONENT / 'redraw_log.h', logs)
        for path in logs:
            code = '\n'.join(line.split('//')[0] for line in path.read_text().splitlines())
            self.assertIsNone(DRAWS.search(code), f'{path.name} is a log-only header, so the translations lint skips it; '
                                                  'it may not draw or translate, nor include a part that does')

    def test_the_lint_reads_every_other_header(self):
        linted = set(i18n.linted_files())
        for path in COMPONENT.glob('*.h'):
            self.assertEqual(path in linted, not path.name.endswith('_log.h'), path.name)


if __name__ == '__main__':
    unittest.main()
