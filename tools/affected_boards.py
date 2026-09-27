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

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firmware_count  # noqa: E402
import profiles  # noqa: E402

ROOT = profiles.ROOT
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


def yaml_tokens(text):
    """What ESPHome reads of a YAML file: its tokens, without the comments YAML itself drops. A lambda's lines stay as
    they are, `#ifdef` included, because inside a block scalar they are its text. None when it doesn't scan."""
    try:
        return [(type(token).__name__, getattr(token, 'value', None)) for token in yaml.scan(text)]
    except yaml.YAMLError:
        return None


def only_comments(path, base):
    """Whether a YAML file changed in comments or layout alone since the base, so the firmware is the same (a board
    file whose explanation got better is no update for its screens)."""
    try:
        before = git('show', f'{base}:{path}')
    except subprocess.CalledProcessError:
        return False
    now = read_now(path)
    tokens = yaml_tokens(before)
    return now is not None and tokens is not None and tokens == yaml_tokens(now)


def sort(paths, base):
    """{path: set of boards it reaches}; an empty set for a path that is no firmware."""
    every, table, reach = set(profiles.BOARDS), chains(), {}
    for path in paths:
        if path.endswith('.yaml') and path.startswith(('packages/', 'checkout/')) and only_comments(path, base):
            reach[path] = set()
        elif path.startswith(SHARED_TREES) or path == str(profiles.CORE.relative_to(ROOT)):
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


dotted = firmware_count.dotted


def read_now(path):
    """A file's text in the working tree, or None."""
    return (ROOT / path).read_text() if (ROOT / path).exists() else None


def read_at(base):
    """A reader of files as they are in `base`: None for a file the base does not have."""
    def read(path):
        try:
            return git('show', f'{base}:{path}')
        except subprocess.CalledProcessError:
            return None
    return read


def next_numbers(boards=(), read=read_now):
    """(the next shared number, the next number for `boards`) after the firmware `read` shows, which is the base the
    change starts from (docs/BOARD_RELEASES.md "How the version numbers work"): the middle number counts the core and
    the last one a board's revisions on top of it. A shared release raises the core and starts at .0; a board release
    keeps the core and takes a revision above what each of those boards builds (several boards share one number, so it
    is above the highest of them)."""
    core = firmware_count.parse(VERSION_LINE.search(read(str(profiles.CORE.relative_to(ROOT))) or '').group(1))
    built = built_versions(read)
    return firmware_count.next_shared(core), firmware_count.next_board(core, [built.get(board) for board in boards])


def plan(reach, new=frozenset(), read_base=read_now):
    """The release that follows from what each path reaches, counted from the base (`read_base`); `new` are boards no
    screen runs yet (new_boards). Once the working tree builds the numbers it asks for, it says so."""
    reached = set().union(*reach.values()) if reach else set()
    boards = reached - set(new)
    every = set(profiles.BOARDS)
    shared, board = next_numbers(sorted(boards) if boards != every else (), read_base)
    shared_next, board_next = dotted(shared), dotted(board)
    now = built_versions(read_now)
    ahead = {board: profiles.substitutions_of(path).get('SCREEN_FIRMWARE_VERSION', '').strip('"')
             for board, path in profiles.BOARDS.items()}
    ahead = {board: version for board, version in ahead.items() if version}
    lines = ['Changed:']
    for path, these in reach.items():
        if these:
            lines.append(f'  {path}: {"every board" if these == every else ", ".join(sorted(these))}')
    others = sum(1 for these in reach.values() if not these)
    if others:
        lines.append(f'  {others} other file{"s" if others != 1 else ""}: no firmware')
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
        done = all(now[b] == shared for b in every)
        lines += [f'Shared firmware: every board. The core goes up, so the number is {shared_next}'
                  + (f' (set: every board builds it).' if done else '.'),
                  f'- packages/core.yaml SCREEN_FIRMWARE_VERSION and screen_manager/app/core.py FIRMWARE_VERSION: "{shared_next}".']
        if ahead:
            lines.append('- Remove SCREEN_FIRMWARE_VERSION from the board files that went ahead, the shared release overtakes '
                         'them: ' + ', '.join(f'{board} ({version})' for board, version in sorted(ahead.items())) + '.')
        lines += ['- tools/generate_board_shapes.py, then bump screen_manager/config.yaml with the CHANGELOG entry',
                  f'  "## <app> (firmware {shared_next})".',
                  '- Run tools/check.sh and tools/check.sh --firmware (every board, the CYD flash budget).']
    else:
        done = all(now[b] == board for b in boards)
        lines += [f'Firmware for {", ".join(sorted(boards))} alone: every other screen is left alone. The core stays, '
                  f'the board revision goes up: {board_next}' + (' (set: those boards build it).' if done else '.')]
        for board in sorted(boards):
            path = profiles.BOARDS[board].relative_to(ROOT)
            now = f' (now "{ahead[board]}")' if board in ahead else ''
            lines.append(f'- {path}: SCREEN_FIRMWARE_VERSION: "{board_next}"{now}, under BOARD_ID.')
        lines += ['- Leave packages/core.yaml and core.FIRMWARE_VERSION as they are.',
                  '- tools/generate_board_shapes.py, then bump screen_manager/config.yaml with the CHANGELOG entry',
                  f'  "## <app> (firmware {board_next} for {", ".join(sorted(boards))})".',
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
        found[board] = firmware_count.parse((own or core).group(1)) if (own or core) else None
    return found


def unraised(reach, base, new=frozenset()):
    """The existing boards a change reaches whose firmware number did not go up: their screens would never be offered
    the change. Empty when every reached board builds a higher number than in the base."""
    before, after = built_versions(read_at(base)), built_versions(read_now)
    reached = set().union(*reach.values()) if reach else set()
    return sorted(board for board in reached - set(new)
                  if before.get(board) is not None and not (after.get(board) and after[board] > before[board]))


APP_VERSION = re.compile(r'(?m)^version:\s*["\']?([^"\'\s]+)')


def releasing(base):
    """Whether this change is a release: screen_manager/config.yaml names another app version than the base. That is
    the moment a firmware change without its number would reach Home Assistant."""
    config = 'screen_manager/config.yaml'
    before, now = (APP_VERSION.search(read_at(base)(config) or ''), APP_VERSION.search(read_now(config) or ''))
    return bool(now) and (not before or before.group(1) != now.group(1))


def known(base):
    try:
        git('rev-parse', '--verify', '--quiet', f'{base}^{{commit}}')
        return True
    except subprocess.CalledProcessError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--base', help='compare with this ref (default: where HEAD left origin/main)')
    parser.add_argument('--keys', action='store_true', help='print only the board keys a change reaches')
    parser.add_argument('--verify', action='store_true',
                        help='exit 1 when a board the change reaches builds no higher firmware number than the base and '
                             'this is a release (or --strict); exit 3 when it is not a release yet, a warning')
    parser.add_argument('--strict', action='store_true', help='with --verify: fail whether or not it is a release (CI)')
    args = parser.parse_args(argv)
    base = args.base or default_base()
    if not known(base):
        # A push that starts a branch has no commit before it; there is nothing to compare with.
        if args.keys:
            # Nothing to compare with: build every board rather than none.
            print(' '.join(profiles.BOARDS))
            return 0
        print(f'No base to compare with ({base[:12] or "none"}): nothing checked')
        return 0
    reach = sort(changed_paths(base), base)
    new = new_boards(base)
    if args.verify:
        missing = unraised(reach, base, new)
        if missing:
            print(f'Firmware changed for {", ".join(missing)} without a higher firmware number, so screens that run it '
                  f'are never offered the change. tools/affected_boards.py says which number to set.')
            return 1 if args.strict or releasing(base) else 3
        print('Every board the change reaches builds a higher firmware number' if set().union(*reach.values()) - new
              else 'No firmware change for a screen that exists')
        return 0
    if args.keys:
        boards = set().union(*reach.values()) if reach else set()
        print(' '.join(board for board in profiles.BOARDS if board in boards))
    else:
        print(f'Against {base[:12]}\n')
        print(plan(reach, new, read_at(base)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
