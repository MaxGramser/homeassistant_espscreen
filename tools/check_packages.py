"""Check that the packages a screen builds from fit together (app 0.2.84+, layered since 0.2.127; tools/check.sh runs this).

A screen is packages/core.yaml plus one board file under packages/boards/, included by an entry file: packages/<board>.yaml
for a screen that builds over GitHub, <profile>.yaml in the repository root for a build from a checkout. The board file
includes its grid's cards (packages/cells/), one look (packages/looks/) and the features it has (packages/features/).
This checks what ESPHome would only tell one build at a time, and what no build tells at all:

- every entry names files that exist, and the published entry and the checkout entry of a board include the same two;
- nothing under packages/ carries a secret, a local component path or a fixed Home Assistant subscription: a screen
  gets its values from ESP Screen Manager while it runs, and its keys from its own YAML;
- every ${NAME} a screen's files use is defined somewhere in its chain: a new board that forgets a size, a hook or its
  look fails here, not in the first build of a user;
- a board file holds what is its own: no block or hook that another board file carries word for word (that belongs in
  a feature, once), no value that only repeats the default of its look, a feature or the core, and nothing that the
  core or a feature already owns;
- nothing the shared files define is dead: a substitution nobody reads goes, instead of being copied to the next board.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402

ROOT = profiles.ROOT
PLACEHOLDER = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')
# Defined by the entry files (the fonts' place) or by ESP Screen Manager's screen YAML.
FROM_ENTRY = {'FONT_DIR'}
# Read by the tools rather than by the YAML: tools/generate_board_shapes.py hands them to the add-on (boards.json).
READ_BY_TOOLS = {'CAMERA_FULL_W', 'CAMERA_FULL_H'}
# A block of a board file this long that another board file carries word for word is behaviour, not hardware.
SHARED_BLOCK_LINES = 6


def included(path):
    return [str(p.relative_to(ROOT)) for p in profiles.packages_of(path)]


def fail(message):
    raise SystemExit(f'check_packages: {message}')


def without_comments(text):
    return '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('#'))


def used_names(text):
    """Every substitution a text reads: `${NAME}` and the names inside a `${ expression }`."""
    names = set(PLACEHOLDER.findall(text))
    for match in profiles.EXPRESSION.finditer(text):
        names |= profiles._names(match[0])
    return names


def own_blocks(path):
    """A board file's top-level sections, and the items of its lists, as text without comments: what it carries."""
    text = without_comments(re.sub(r'^substitutions:\n(.*?)(?=^[a-z_0-9]+:|\Z)', '', path.read_text(), count=1,
                                   flags=re.M | re.S))
    blocks = {}
    for section in re.finditer(r'^([a-z_0-9]+):\n(.*?)(?=^[a-z_0-9]+:|\Z)', text, re.M | re.S):
        key, body = section[1], section[2]
        if key == 'packages':
            continue
        items = re.split(r'(?m)^(?=  - )', body)
        for item in items:
            item = item.strip('\n')
            if len([line for line in item.split('\n') if line.strip()]) >= SHARED_BLOCK_LINES:
                blocks[f'{key}: {item.strip().splitlines()[0][:60]}'] = item
    return blocks


def firmware_problem(shared, own):
    """What is wrong with the boards' own firmware versions, or None. `shared` is the core's SCREEN_FIRMWARE_VERSION,
    `own` maps a board file to the one it sets ('' for none). A board's own version is strict X.Y.Z (the add-on reads
    nothing else as a firmware) and above the shared one: equal or below, the board would report a firmware it does
    not have, and the feature gates would believe it."""
    version = lambda text: tuple(map(int, text.split('.'))) if re.fullmatch(r'\d+\.\d+\.\d+', text) else None
    if not version(shared):
        return f'packages/core.yaml has SCREEN_FIRMWARE_VERSION "{shared}", not X.Y.Z'
    for path, value in sorted(own.items()):
        if value and not (version(value) and version(value) > version(shared)):
            return (f'{path} sets SCREEN_FIRMWARE_VERSION "{value}", which is not above the shared {shared}: '
                    f'a shared release overtook the board, so remove the line (docs/BOARD_RELEASES.md)')
    return None


def main():
    boards = profiles.BOARDS
    for board in boards:
        entries = [name for name, b in profiles.ENTRIES.items() if b == board]
        wanted = {'packages/core.yaml', str(boards[board].relative_to(ROOT))}
        for name in entries:
            if not (ROOT / name).exists():
                fail(f'{name} does not exist, but tools/profiles.py lists it for {board}')
            files = included(ROOT / name)
            if set(files) != wanted:
                fail(f'{name} includes {files}, expected {sorted(wanted)}')
            for file in files:
                if not (ROOT / file).exists():
                    fail(f'{name} includes a file that does not exist: {file}')
    for path in sorted((ROOT / 'packages').rglob('*.yaml')):
        text = without_comments(path.read_text())
        for needle, why in (('!secret', 'a secret'), ('type: local', 'a local component path')):
            if needle in text:
                fail(f'{path.relative_to(ROOT)} carries {why} ({needle})')
        # A screen gets its values from ESP Screen Manager while it runs: no fixed subscription (time: is the exception).
        for section in ('sensor', 'binary_sensor', 'text_sensor'):
            match = re.search(r'^' + section + r':\n.*?(?=^[a-zA-Z_]+:|\Z)', text, re.M | re.S)
            if match and re.search(r'^  - platform: homeassistant$', match[0], re.M):
                fail(f'{path.relative_to(ROOT)}: a {section} subscribes to Home Assistant; runtime tiles bring their own values')

    # Every name a screen's files read is defined somewhere in its chain.
    for board, path in boards.items():
        entry = profiles.PROFILES[list(boards).index(board)]
        defined = set(profiles.raw_substitutions(ROOT / entry)) | FROM_ENTRY
        chain = profiles.files(entry)
        looks = [p for p in chain if p.parent.name == 'looks']
        if len(looks) != 1:
            fail(f'{path.relative_to(ROOT)} includes {len(looks)} looks; a board has exactly one (packages/looks/)')
        for file in chain:
            text = without_comments(file.read_text())
            missing = used_names(text) - defined
            if missing:
                fail(f'{path.relative_to(ROOT)}: {file.relative_to(ROOT)} uses {sorted(missing)}, which neither the board, '
                     f'its look and features nor the core define')

    # What the core and the features own stays theirs.
    core_ids = set(re.findall(r'(?m)^\s+(?:- )?id: (setting_rotation|screen_lvgl)$', profiles.CORE.read_text()))
    for path in sorted((ROOT / 'packages' / 'boards').glob('*.yaml')):
        own = without_comments(path.read_text())
        for name in core_ids:
            if re.search(r'(?m)^\s+(?:- )?id: ' + name + '$', own):
                fail(f'{path.relative_to(ROOT)} defines {name}, which packages/core.yaml owns for every board')

    # A board file holds what is its own.
    blocks = {board: own_blocks(path) for board, path in boards.items()}
    seen = {}
    for board, found in blocks.items():
        for label, body in found.items():
            if body in seen and seen[body] != board:
                fail(f'{boards[board].relative_to(ROOT)} and {boards[seen[body]].relative_to(ROOT)} carry the same block '
                     f'({label}): behaviour two boards share belongs in a feature (packages/features/), once')
            seen.setdefault(body, board)
    hooks = {}
    for board, path in boards.items():
        for key, value in profiles.substitutions_of(path).items():
            if '\n' in value or ';' in value:
                if value in hooks and hooks[value][0] != board:
                    fail(f'{path.relative_to(ROOT)} and {boards[hooks[value][0]].relative_to(ROOT)} define {key} with the '
                         f'same code: a hook two boards share belongs in a feature (packages/features/), once')
                hooks.setdefault(value, (board, key))
    for board, path in boards.items():
        entry = profiles.PROFILES[list(boards).index(board)]
        own = profiles.substitutions_of(path)
        everything = profiles.raw_substitutions(ROOT / entry)
        below = dict(everything)
        for key in own:
            below.pop(key, None)
        # What the value would be without the board's own line: its look's, a feature's or the core's.
        lower = {}
        for package in reversed(profiles.packages_of(path)):
            for key, value in profiles.raw_substitutions(package).items():
                lower.setdefault(key, value)
        for key, value in profiles.substitutions_of(profiles.CORE).items():
            lower.setdefault(key, value)
        for key, value in own.items():
            if key in lower:
                mine = profiles.evaluate({**everything})[key]
                theirs = profiles.evaluate({**everything, key: lower[key]})[key]
                if mine == theirs:
                    fail(f'{path.relative_to(ROOT)} states {key}: "{value}", which is what it gets without that line; '
                         f'leave it out, so a change to the default reaches this board too')

    # Every board file, not only the ones the manager ships: a new panel starts life as packages/boards/lab-*.yaml
    # (tools/new_board.py) and is flashed and rendered long before it is registered.
    seen_ids = {}
    for path in sorted((ROOT / 'packages' / 'boards').glob('*.yaml')):
        values = profiles.evaluate({**profiles.raw_substitutions(profiles.CORE), **profiles.raw_substitutions(path)})
        # As many cards as the page that holds most has cells, lying down or standing up: one file serves both. A board
        # that raised its rows but kept the cells file of the old grid drew nothing in the cells it gained
        # (Waveshare 3 x 2 -> 3 x 3, 2026-09-20).
        if 'GRID_COLS' in values and 'GRID_ROWS' in values:
            need = max(int(values['GRID_COLS']) * int(values['GRID_ROWS']),
                       int(values['GRID_COLS_PORTRAIT']) * int(values['GRID_ROWS_PORTRAIT']))
            for cells in profiles.cells_of(path):
                if cells.stem.isdigit() and int(cells.stem) != need:
                    fail(f'{path.relative_to(ROOT)} includes cells/{cells.name} but its larger page holds {need} cells: '
                         f'the cards for the cells it gained are missing. Run tools/generate_cells.py and include '
                         f'cells/{need}.yaml')
        else:
            fail(f'{path.relative_to(ROOT)} has no GRID_COLS / GRID_ROWS: every board says what its page holds')
        # And a word of its own for what it is. The screen reports it and ESP Screens goes by it (boards.json,
        # camera sizes); a board that kept the word of the board it was copied from would answer for that one.
        board_id = profiles.substitutions_of(path).get('BOARD_ID', '').strip('"')
        if not board_id:
            fail(f'{path.relative_to(ROOT)} does not define BOARD_ID: the screen reports it so the manager '
                 f'knows which board it is')
        elif board_id in seen_ids:
            fail(f'{path.relative_to(ROOT)} and {seen_ids[board_id]} both call themselves "{board_id}": a board '
                 f'copied from another keeps its word unless tools/new_board.py sets it')
        else:
            seen_ids[board_id] = path.relative_to(ROOT)
    for board, path in boards.items():
        found = profiles.substitutions_of(path).get('BOARD_ID', '').strip('"')
        if found and found != board:
            fail(f'{path.relative_to(ROOT)} says BOARD_ID "{found}" but the manager knows it as "{board}" '
                 f'(tools/profiles.py): boards.json and the screen would not agree')

    # A board's own firmware version (app 0.3.20, docs/RELEASING.md "Firmware for one board"): only a board file sets
    # one, and only above the core's. The core's version is what every feature gate compares against, so a board at or
    # below it would report a firmware it does not have; the next shared release takes the number back out.
    for path in (ROOT / 'packages').rglob('*.yaml'):
        if path != profiles.CORE and path not in boards.values() and 'SCREEN_FIRMWARE_VERSION' in profiles.substitutions_of(path):
            fail(f'{path.relative_to(ROOT)} sets SCREEN_FIRMWARE_VERSION: only packages/core.yaml and a board file do')
    problem = firmware_problem(profiles.substitutions_of(profiles.CORE)['SCREEN_FIRMWARE_VERSION'].strip('"'),
                               {str(path.relative_to(ROOT)): profiles.substitutions_of(path).get('SCREEN_FIRMWARE_VERSION', '').strip('"')
                                for path in boards.values()})
    if problem:
        fail(problem)

    # Nothing the shared files define is dead.
    shared = [profiles.CORE, *sorted((ROOT / 'packages' / 'looks').glob('*.yaml')),
              *sorted((ROOT / 'packages' / 'features').glob('*.yaml'))]
    everywhere = '\n'.join(without_comments(p.read_text()) for p in (ROOT / 'packages').rglob('*.yaml'))
    everywhere += '\n'.join(without_comments(p.read_text()) for p in ROOT.glob('*.yaml'))
    read = used_names(everywhere) | READ_BY_TOOLS
    for path in shared:
        dead = set(profiles.substitutions_of(path)) - read
        if dead:
            fail(f'{path.relative_to(ROOT)} defines {sorted(dead)}, which nothing reads')

    names = set().union(*(profiles.raw_substitutions(ROOT / entry) for entry in profiles.PROFILES))
    own = {board: len(profiles.substitutions_of(path)) for board, path in boards.items()}
    print(f'packages: {len(names)} names across {len(boards)} boards; a board file states '
          + ', '.join(f'{board} {count}' for board, count in own.items()))


if __name__ == '__main__':
    main()
