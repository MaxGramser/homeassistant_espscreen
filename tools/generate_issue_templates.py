"""Generate the bug report template's board dropdown from boards.yaml.

Write bug_report.yml with the catalog's board names and order, so adding a board also updates the issue form.
Questions use Discussions; their retired issue template is no longer generated. `--check` fails when the bug
report template is out of date, which tools/check.sh runs.

usage: generate_issue_templates.py [--check]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402

OUT_DIR = profiles.ROOT / '.github' / 'ISSUE_TEMPLATE'

TRAILING_BOARD_OPTIONS = ('Other / not listed here',)


def board_options(extra_trailing=()):
    """The board dropdown options, in boards.yaml's own order, as YAML list items indented for a `body:` entry."""
    lines = [f'{entry["name"]} ({entry["model"]})' for entry in profiles.CATALOG.values()]
    lines += list(TRAILING_BOARD_OPTIONS) + list(extra_trailing)
    return '\n'.join(f'        - {line}' for line in lines)


def bug_report():
    return f'''name: Bug report
description: Something isn't working, a screen, the add-on, or the editor.
title: "[Bug]: "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting a problem. Please fill in as much as you can, it saves a lot of back and forth.
  - type: dropdown
    id: board
    attributes:
      label: Board
      description: Which board is this about?
      options:
{board_options(extra_trailing=('Not board-specific (add-on, editor, documentation)',))}
    validations:
      required: true
  - type: input
    id: versions
    attributes:
      label: Add-on and firmware version
      description: The add-on version from Settings > Add-ons > ESP Screen Manager, and the firmware version shown on the screen's own Settings page (or in the ESPHome logs).
      placeholder: "e.g. add-on 0.3.19, firmware 0.3.9"
    validations:
      required: true
  - type: textarea
    id: what-happened
    attributes:
      label: What happened
      description: Describe the problem you are seeing.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What you expected instead
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      description: What did you do, in order, right before the problem showed up?
      placeholder: |
        1.
        2.
        3.
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Logs, screenshots, or a photo of the screen
      description: Add-on logs, ESPHome logs, screenshots of the editor, or a photo of the physical screen. Drag and drop files here.
    validations:
      required: false
  - type: checkboxes
    id: checks
    attributes:
      label: Before submitting
      options:
        - label: I checked the README, README_EXTENDED.md, and the guides under docs/ for this
          required: true
        - label: I searched the existing issues and this has not already been reported
          required: true
'''


FILES = {'bug_report.yml': bug_report}


def main():
    check = '--check' in sys.argv
    stale = []
    for name, build in FILES.items():
        path = OUT_DIR / name
        text = build()
        if check:
            current = path.read_text() if path.exists() else ''
            if current != text:
                stale.append(name)
            continue
        path.write_text(text)
    if check:
        if stale:
            print(f'Out of date: {", ".join(stale)}; run tools/generate_issue_templates.py')
            return 1
        print('Issue templates match boards.yaml')
        return 0
    print(f'wrote {", ".join(FILES)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
