"""The board profiles as the tests and tools read them (app 0.2.84+, packages layered since app 0.2.127).

A screen is an entry (`checkout/cyd.yaml` or `packages/cyd.yaml` for a CYD, `checkout/guition.yaml` or
`packages/guition.yaml` for a Guition, ...) that includes `packages/core.yaml`, which every board shares, and the
board's own file under `packages/boards/`. The board file includes packages of its own in turn: the cards of its grid
(`packages/cells/`), its look (`packages/looks/`) and its features (`packages/features/`). docs/PROFILES.md says how.

`files(name)` is that whole chain, `text(name)` all of it one file after the other, so a check that looks for a line
finds it wherever it lives. `substitutions(name)` is every `${NAME}` the chain defines, with the precedence ESPHome
gives them (the entry over the board over the board's own packages over the core) and worked out the way ESPHome
works them out (Jinja, for the sizes a look computes). `resolved(name)` is `text(name)` with those filled in, for a
check that needs the numbers or the whole lambda. None of this is what ESPHome builds: that is the merge ESPHome's
packages component makes; the firmware check in tools/check.sh compiles the real thing.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'packages/core.yaml'

# The boards that ship: boards.yaml, the catalog, in the order New screen offers them. Each entry is keyed by the word
# ESP Screens knows a board by and names its file under packages/boards/. A screen installed from ESP Screens builds
# from packages/<key>.yaml over GitHub, and a build from a checkout from checkout/<key>.yaml (checkout/README.md).
# Adding a board is one entry there (docs/ADDING_A_BOARD.md).
CATALOG = yaml.safe_load((ROOT / 'boards.yaml').read_text())
BOARD_TABLE = tuple((board, entry['file'], f'checkout/{board}.yaml') for board, entry in CATALOG.items())
BOARDS = {board: ROOT / 'packages/boards' / file for board, file, _ in BOARD_TABLE}
# The names the entry files are known by: the checkout profiles in the order above, then the published packages.
PROFILES = tuple(profile for _, _, profile in BOARD_TABLE)
PACKAGES = tuple(f'packages/{board}.yaml' for board, _, _ in BOARD_TABLE)
NAMES = PROFILES + PACKAGES
ENTRIES = {**{profile: board for board, _, profile in BOARD_TABLE},
           **{f'packages/{board}.yaml': board for board, _, _ in BOARD_TABLE}}


def board_of(name):
    return ENTRIES[str(name).replace(str(ROOT) + '/', '')]


def packages_of(path):
    """The files a file's `packages:` block includes, in its order, resolved against that file's folder."""
    block = re.search(r'^packages:\n(.*?)(?=^[a-z_0-9]+:|\Z)', Path(path).read_text(), re.M | re.S)
    if not block:
        return []
    return [(Path(path).parent / include).resolve() for include in re.findall(r'!include (\S+)', block[1])]


def chain(path):
    """A file and everything it includes, depth first: each package's own packages before it, the file itself last.
    That is the order ESPHome merges them in, and the reverse of the order their substitutions win."""
    found = []
    for package in packages_of(path):
        for item in chain(package):
            if item not in found:
                found.append(item)
    found.append(Path(path).resolve())
    return found


def cells_of(board_file):
    """The cells package a board file brings: the cards of its grid (packages/cells/<number>.yaml)."""
    return [path for path in packages_of(board_file) if path.parent.name == 'cells']


def files(name):
    """The entry, the core, and the board file's chain (its cells, its look, its features, itself), in that order."""
    board = BOARDS[board_of(name)]
    return [ROOT / name, CORE, *chain(board)]


def text(name):
    return '\n'.join(path.read_text() for path in files(name))


def substitutions_of(path):
    """The `substitutions:` block of one file as written, block scalars included."""
    return substitutions_in(Path(path).read_text())


def substitutions_in(text):
    """The `substitutions:` block of a file's text as written (substitutions_of for text from elsewhere, such as the
    same file in an older commit). YAML reads the values, so either kind of quote is gone."""
    block = re.search(r'^substitutions:\n(.*?)(?=^[a-z_0-9]+:|\Z)', text, re.M | re.S)
    if not block:
        return {}
    values = yaml.safe_load('substitutions:\n' + block[1])['substitutions'] or {}
    return {key: '' if value is None else str(value) for key, value in values.items()}


def raw_substitutions(path):
    """Every substitution a file and its packages define, as written, with the one that wins: the file's own over its
    packages', a later package's over an earlier one's (ESPHome's packages component, "higher-priority sources win")."""
    values = dict(substitutions_of(path))
    # A package that is not there yet (the cards of a new board's grid before tools/generate_cells.py ran) adds nothing;
    # tools/check_packages.py is what says it is missing.
    for package in reversed([p for p in packages_of(path) if p.exists()]):
        for key, value in raw_substitutions(package).items():
            values.setdefault(key, value)
    return values


_JINJA = None


def _jinja():
    """A Jinja environment set up the way ESPHome sets up its own (esphome/components/substitutions/jinja.py):
    `${` and `}` around an expression, an unknown name an error, and the math module at hand."""
    global _JINJA
    if _JINJA is None:
        try:
            import jinja2
        except ImportError as error:  # pragma: no cover - a setup problem, said plainly
            raise SystemExit('tools/profiles.py needs jinja2 to work out the sizes a look computes: pip install jinja2 '
                             '(or run with PYTHON=.venv-portal/bin/python)') from error
        import math
        _JINJA = jinja2.Environment(variable_start_string='${', variable_end_string='}', block_start_string='<%',
                                    block_end_string='%>', undefined=jinja2.StrictUndefined)
        _JINJA.globals.update({'math': math, 'ord': ord, 'chr': chr, 'len': len})
    return _JINJA


EXPRESSION = re.compile(r'\$\{([^{}]*)\}')


def _render(source, values, strict):
    """`${NAME}` and `${ expression }` in a text filled in from values. strict=False leaves anything it cannot work out
    as it is (a text); 'names' does that only for a name nobody defines and raises on a broken expression (a
    substitution's value); True raises on both."""
    import jinja2

    def one(match):
        try:
            return str(_jinja().from_string('${' + match[1] + '}').render(values))
        except jinja2.UndefinedError:
            if strict is True:
                raise
            return match[0]
        except (jinja2.TemplateSyntaxError, TypeError, ValueError):
            # In a text, not every ${...} is an expression ESPHome reads: a comment may say "the place named ${...}"
            # or show one as an example. A substitution's own value is always read (strict).
            if strict:
                raise
            return match[0]
    return EXPRESSION.sub(one, source)


def _names(value):
    """The substitutions an expression in a value reads."""
    from jinja2 import TemplateSyntaxError, meta
    found = set()
    for match in EXPRESSION.finditer(value):
        try:
            found |= meta.find_undeclared_variables(_jinja().parse('${' + match[1] + '}'))
        except TemplateSyntaxError:
            pass  # words in a comment, not an expression
    return found


def evaluate(values):
    """The substitutions worked out: a value's `${...}` filled in once every name it reads is worked out itself, so
    a size computed from LOOK_SCALE never sees LOOK_SCALE's own expression. A name nobody defines stays as written."""
    done, busy = {}, set()

    def value_of(key):
        if key in done:
            return done[key]
        if key in busy:
            raise ValueError(f'substitution {key} refers to itself')
        busy.add(key)
        raw = values[key]
        context = {name: value_of(name) for name in _names(raw) if name in values}
        done[key] = _render(raw, context, strict='names')
        busy.discard(key)
        return done[key]
    for key in values:
        value_of(key)
    return done


def substitutions(name):
    """Every substitution a screen built from this entry sees, worked out."""
    return evaluate(raw_substitutions(ROOT / name) if (ROOT / name).exists() else {})


def board_values(board):
    """A board's substitutions as a screen of that board sees them, through its checkout entry."""
    return substitutions(PROFILES[[b for b, _, _ in BOARD_TABLE].index(board)])


def resolve(source, values):
    """`${NAME}` and `${ expression }` filled in, until nothing is left to fill (a hook's code names sizes of its own)."""
    for _ in range(4):
        before = source
        source = _render(source, values, strict=False)
        if source == before:
            break
    return source


def resolved(name):
    return resolve(text(name), substitutions(name))


def merged(name):
    """Closer to what ESPHome builds: the chain's files without their substitutions blocks, every ${NAME} filled in.
    For a check that counts things, so a hook's definition in a board or feature file is not counted next to its use."""
    without = [re.sub(r'^substitutions:\n(.*?)(?=^[a-z_0-9]+:|\Z)', '', path.read_text(), count=1, flags=re.M | re.S) for path in files(name)]
    return resolve('\n'.join(without), substitutions(name))
