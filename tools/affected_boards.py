"""Which boards a change reaches, and what its release is (app 0.3.20; docs/BOARD_RELEASES.md is the recipe).

A screen's firmware is built from packages/core.yaml plus its board file's chain (tools/profiles.py), the components
under components/, the fonts, and the `screen` section of screen_manager/translations. This compares the working tree
(committed, staged, unstaged and new files) with a base, by default where HEAD left origin/main, and sorts every
changed path:

- a file in one board's chain only (its board file, its entry files, a feature or hardware file no other board
  includes) reaches that board;
- the core, components/, fonts/, a translation's `screen` texts, or a package several boards include reaches all of
  them;
- anything else (the add-on, the editor, docs, tests, tools) is no firmware at all.

A board whose board file is not in the base yet is new: no screen runs it, so it needs no firmware number of its own and
its release is one of the app (the catalog grows); only the boards that already exist decide the firmware release.

    tools/affected_boards.py              what changed, which boards it reaches, and the release that follows
    tools/affected_boards.py --keys       only the board keys, space separated, empty for none (tools/check.sh --affected)
    tools/affected_boards.py --base REF   compare with REF instead

Standard library and PyYAML only.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402

ROOT = profiles.ROOT
CHANGELOG = ROOT / 'screen_manager/CHANGELOG.md'
FIRMWARE_IN_HEADING = re.compile(r'^## \d+\.\d+\.\d+ \(firmware (\d+\.\d+\.\d+)(?: for ([a-z0-9]+(?:, [a-z0-9]+)*))?\)', re.M)
# Everything a build of every board reads, whichever board file names it.
SHARED_TREES = ('components/', 'fonts/')
TRANSLATIONS = 'screen_manager/translations/'


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def default_base():
    try:
        return git('merge-base', 'HEAD', 'origin/main').strip()
    except subprocess.CalledProcessError:
        return 'HEAD'


def changed_paths(base):
    """Every path that differs from `base` in the working tree, new untracked files included."""
    paths = set(git('diff', '--name-only', base).split())
    paths |= set(git('ls-files', '--others', '--exclude-standard').split())
    return sorted(paths)


def chains():
    """{board: the repository paths a build of that board reads from packages/ and its entry files}."""
    found = {}
    for board in profiles.BOARDS:
        paths = set()
        for entry in (f'checkout/{board}.yaml', f'packages/{board}.yaml'):
            paths |= {str(p.resolve().relative_to(ROOT)) for p in profiles.files(entry)}
        found[board] = paths
    return found


def screen_texts(text):
    try:
        return json.loads(text).get('screen')
    except (ValueError, AttributeError):
        return object()  # unreadable reads as changed


def translation_reaches_screens(path, base):
    """Whether a translation file's `screen` section, the part the firmware compiles in, differs from the base."""
    try:
        before = git('show', f'{base}:{path}')
    except subprocess.CalledProcessError:
        before = '{}'
    now = (ROOT / path).read_text() if (ROOT / path).exists() else '{}'
    return screen_texts(before) != screen_texts(now)


def new_boards(base):
    """The boards whose board file the base does not have: added by this change, with no screen that runs them yet."""
    try:
        known = set(git('ls-tree', '-r', '--name-only', base, 'packages/boards/').split())
    except subprocess.CalledProcessError:
        return set()
    return {board for board, path in profiles.BOARDS.items() if str(path.relative_to(ROOT)) not in known}


def sort(paths, base):
    """{path: set of boards it reaches}; an empty set for a path that is no firmware."""
    every, table, reach = set(profiles.BOARDS), chains(), {}
    for path in paths:
        if path.startswith(SHARED_TREES) or path == str(profiles.CORE.relative_to(ROOT)):
            reach[path] = set(every)
        elif path.startswith(TRANSLATIONS) and path.endswith('.json'):
            reach[path] = set(every) if translation_reaches_screens(path, base) else set()
        elif path.startswith('packages/') and path.endswith('.yaml'):
            boards = {board for board, files in table.items() if path in files}
            # A package no board includes yet (a new feature file) reaches none; a deleted one reached some before,
            # which the board files that stopped including it show on their own.
            reach[path] = boards
        elif path.startswith('checkout/') and path.endswith('.yaml') and Path(path).stem in every:
            reach[path] = {Path(path).stem}
        else:
            reach[path] = set()
    return reach


def firmware_numbers():
    """[(firmware tuple, boards or None)] of the CHANGELOG, newest first."""
    return [(tuple(map(int, number.split('.'))), boards.split(', ') if boards else None)
            for number, boards in FIRMWARE_IN_HEADING.findall(CHANGELOG.read_text())]


def dotted(version):
    return '.'.join(map(str, version))


def plan(reach, new=frozenset()):
    """The release that follows from what each path reaches; `new` are boards no screen runs yet (new_boards)."""
    reached = set().union(*reach.values()) if reach else set()
    boards = reached - set(new)
    every = set(profiles.BOARDS)
    numbers = firmware_numbers()
    highest = max(number for number, _ in numbers)
    following = dotted((*highest[:2], highest[2] + 1))
    ahead = {board: profiles.substitutions_of(path).get('SCREEN_FIRMWARE_VERSION', '').strip('"')
             for board, path in profiles.BOARDS.items()}
    ahead = {board: version for board, version in ahead.items() if version}
    lines = ['Changed:']
    for path, these in reach.items():
        what = 'every board' if these == every else ', '.join(sorted(these)) if these else 'no firmware'
        lines.append(f'  {path}: {what}')
    lines.append('')
    if reached & set(new):
        added = sorted(reached & set(new))
        lines += [f'New board: {", ".join(added)}. No screen runs it yet, so it takes no firmware number of its own and',
                  'nothing else updates: it builds the shared firmware from main (docs/BOARD_RELEASES.md, "A new board").',
                  f'- Build and render it: tools/check.sh --firmware --board {" --board ".join(added)}, and',
                  '  tools/render/run.py <board> (with <board>-portrait for glass that is not square).', '']
    if not boards:
        lines += ['No firmware change for a screen that exists: an app release (or a docs push, docs/RELEASING.md).',
                  '- Bump screen_manager/config.yaml and write the CHANGELOG entry with the shared firmware it ships with:',
                  f'  "## <app> (firmware {profiles.substitutions_of(profiles.CORE)["SCREEN_FIRMWARE_VERSION"].strip(chr(34))})".',
                  '- Run tools/check.sh (no --firmware: no screen gets anything new).']
    elif boards == every:
        lines += [f'Shared firmware: every board. The next firmware number is {following}.',
                  f'- packages/core.yaml SCREEN_FIRMWARE_VERSION and screen_manager/app/core.py FIRMWARE_VERSION: "{following}".']
        if ahead:
            lines.append('- Remove SCREEN_FIRMWARE_VERSION from the board files that went ahead, the shared release overtakes '
                         'them: ' + ', '.join(f'{board} ({version})' for board, version in sorted(ahead.items())) + '.')
        lines += ['- tools/generate_board_shapes.py, then bump screen_manager/config.yaml with the CHANGELOG entry',
                  f'  "## <app> (firmware {following})".',
                  '- Run tools/check.sh and tools/check.sh --firmware (every board, the CYD flash budget).']
    else:
        lines += [f'Firmware for {", ".join(sorted(boards))} alone: every other screen is left alone. '
                  f'The next firmware number is {following}.']
        for board in sorted(boards):
            path = profiles.BOARDS[board].relative_to(ROOT)
            now = f' (now "{ahead[board]}")' if board in ahead else ''
            lines.append(f'- {path}: SCREEN_FIRMWARE_VERSION: "{following}"{now}, under BOARD_ID.')
        lines += ['- Leave packages/core.yaml and core.FIRMWARE_VERSION as they are.',
                  '- tools/generate_board_shapes.py, then bump screen_manager/config.yaml with the CHANGELOG entry',
                  f'  "## <app> (firmware {following} for {", ".join(sorted(boards))})".',
                  f'- Run tools/check.sh and tools/check.sh --firmware --board {" --board ".join(sorted(boards))}'
                  f' (or --affected).']
    return '\n'.join(lines)


VERSION_LINE = re.compile(r'(?m)^  SCREEN_FIRMWARE_VERSION: "?([0-9.]+)"?')


def built_versions(read):
    """{board: the firmware it builds}, from `read(path)` giving a file's text (or None when it has none): the board
    file's own SCREEN_FIRMWARE_VERSION, else the core's."""
    core = VERSION_LINE.search(read(str(profiles.CORE.relative_to(ROOT))) or '')
    found = {}
    for board, path in profiles.BOARDS.items():
        own = VERSION_LINE.search(read(str(path.relative_to(ROOT))) or '')
        found[board] = tuple(map(int, (own or core).group(1).split('.'))) if (own or core) else None
    return found


def unraised(reach, base, new=frozenset()):
    """The existing boards a change reaches whose firmware number did not go up: their screens would never be offered
    the change. Empty when every reached board builds a higher number than in the base."""
    def at_base(path):
        try:
            return git('show', f'{base}:{path}')
        except subprocess.CalledProcessError:
            return None
    def now(path):
        return (ROOT / path).read_text() if (ROOT / path).exists() else None
    before, after = built_versions(at_base), built_versions(now)
    reached = set().union(*reach.values()) if reach else set()
    return sorted(board for board in reached - set(new)
                  if before.get(board) is not None and not (after.get(board) and after[board] > before[board]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--base', help='compare with this ref (default: where HEAD left origin/main)')
    parser.add_argument('--keys', action='store_true', help='print only the board keys a change reaches')
    parser.add_argument('--verify', action='store_true',
                        help='exit 1 when a board the change reaches builds no higher firmware number than the base')
    args = parser.parse_args(argv)
    base = args.base or default_base()
    reach = sort(changed_paths(base), base)
    new = new_boards(base)
    if args.verify:
        missing = unraised(reach, base, new)
        if missing:
            print(f'Firmware changed for {", ".join(missing)} without a higher firmware number, so screens that run it '
                  f'are never offered the change. tools/affected_boards.py says which number to set.')
            return 1
        print('Every board the change reaches builds a higher firmware number' if set().union(*reach.values()) - new
              else 'No firmware change for a screen that exists')
        return 0
    if args.keys:
        boards = set().union(*reach.values()) if reach else set()
        print(' '.join(board for board in profiles.BOARDS if board in boards))
    else:
        print(f'Against {base[:12]}\n')
        print(plan(reach, new))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
