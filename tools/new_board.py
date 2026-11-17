"""Add a board: its board file, its catalog entry, its two entry files and an override case, from a board we have.

usage: new_board.py NAME --from BOARD --width W --height H --inch D [--cols C --rows R] [--rotation 0|90|180|270]
                     [--portrait-cols C --portrait-rows R] [--dpi D] [--look standard|compact]
                     [--title NAME] [--model TEXT] [--status new|experimental]

A board file is small since app 0.2.127: its hardware, the facts of its glass and its grid, and the packages it
includes (docs/PROFILES.md). Every size comes from the look, which scales it by DISPLAY_DPI so a tile, a letter and a
key keep their size in millimetres; nothing is copied or scaled here. What this writes:

- packages/boards/NAME.yaml: the template board's `packages:` (its build, hardware, look and features); the new
  board's word (BOARD_ID), its panel (the canvas lying down, turned back by --rotation), its
  density, and its grid both ways up (the proposal of tools/propose_grid.py, or --cols/--rows); and, like the
  template's hardware sections, the template's own substitutions that are not about its glass (the hardware values an
  override may change, and the code the board hands the shared lambdas), which are the template's until replaced;
- NAME's entry in boards.yaml (what New screen shows: --title, --model and --status, experimental unless said), then
  the entry files packages/NAME.yaml and checkout/NAME.yaml (tools/generate_entries.py) and boards.json
  (tools/generate_board_shapes.py);
- tests/fixtures/overrides/NAME-contract.yaml: an override of the parts every board names the same way, which
  tools/check.sh --firmware has ESPHome read on this board, the way a screen's Override YAML loads it.

What is left by hand is the board's own hardware: the sections below its banner, and the values copied from the
template. Nothing is fitted to the glass here: what depends on the canvas (the cells, the page bar, the alert card)
the firmware works out on the glass itself.

--width and --height are the canvas of the screen lying down and --rotation the LVGL angle that lays the panel out that
way. A board only tried out is best called lab-<name>: Git ignores those, it gets only its board file, and it stays out
of the catalog. The cards of its grid are made at boot, one per cell (runtime_tiles::make_cells).
"""
import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402
import propose_grid  # noqa: E402

BANNER = '# ============================================================\n# No need to edit below this line.'
# The substitutions this writes itself: the board's word and names, its glass and its grid. Every other substitution
# of the template's own is about its hardware, and is copied the way its hardware sections are.
GLASS = {'BOARD_ID', 'DEVICE_NAME', 'DEVICE_FRIENDLY_NAME', 'PANEL_W', 'PANEL_H', 'DISPLAY_DPI', 'ROTATION_LANDSCAPE',
         'GRID_COLS', 'GRID_ROWS', 'GRID_COLS_PORTRAIT', 'GRID_ROWS_PORTRAIT', 'LVGL_BUFFER_SIZE'}
CONTRACT = """# Written by tools/new_board.py: the parts every board names the same way (docs/PROFILES.md, "What an override may
# rely on"), extended the way a screen's Override YAML does it. tools/check.sh --firmware has ESPHome read it on this
# board. Add the cases people with this board share, one file each.
light:
  - id: !extend back_light
    default_transition_length: 200ms
"""


def own_substitutions(source):
    """The template's own substitutions that are not about its glass, as written: each with the comment lines above
    it and the lines of a block value (a hook's code), in the template's order."""
    block = re.search(r'(?ms)^substitutions:\n(.*?)(?=^\S)', source)
    groups, comment, current = [], [], None
    for line in (block[1] if block else '').split('\n'):
        key = re.match(r'^  ([A-Z_0-9]+):', line)
        if key:
            current = [*comment, line]
            groups.append((key[1], current))
            comment = []
        elif line.startswith('   ') and current is not None:
            current.append(line)
        elif line.startswith('  #'):
            comment.append(line)
            current = None
        else:
            comment = []
    return [lines for key, lines in groups if key not in GLASS]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('name')
    ap.add_argument('--from', dest='template', required=True, choices=sorted(profiles.BOARDS))
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--height', type=int, required=True)
    ap.add_argument('--inch', type=float, required=True)
    ap.add_argument('--cols', type=int)
    ap.add_argument('--rows', type=int)
    ap.add_argument('--portrait-cols', dest='portrait_cols', type=int)
    ap.add_argument('--portrait-rows', dest='portrait_rows', type=int)
    ap.add_argument('--rotation', type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument('--dpi', type=float)
    ap.add_argument('--shape', choices=('rectangle', 'round'), default='rectangle')
    ap.add_argument('--look', choices=('standard', 'compact'))
    ap.add_argument('--title', help='what people call the board (boards.yaml name); the template\'s by default')
    ap.add_argument('--model', help='what is printed on the board (boards.yaml model); NAME in capitals by default')
    ap.add_argument('--status', choices=('new', 'experimental'), default='experimental')
    a = ap.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]*', a.name):
        raise SystemExit('The name is the file name and the board\'s word: lower case, digits and dashes.')
    lab = a.name.startswith('lab-')
    if not lab and (a.name in profiles.CATALOG or (profiles.ROOT / 'packages' / f'{a.name}.yaml').exists()):
        raise SystemExit(f'{a.name} is a board already (boards.yaml, packages/{a.name}.yaml).')

    template = profiles.BOARDS[a.template]
    source = template.read_text()
    W, H = a.width, a.height
    if a.shape == 'round' and W != H:
        raise SystemExit('Circular glass needs a square pixel canvas; --inch is its diameter.')
    diagonal = max(W, H) if a.shape == 'round' else math.hypot(W, H)
    dpi = a.dpi or diagonal / a.inch
    proposal_inch = a.inch * math.sqrt(2) if a.shape == 'round' else a.inch
    look = a.look or profiles.evaluate(profiles.raw_substitutions(template))['LOOK']
    if a.cols and a.rows:
        cols, rows = a.cols, a.rows
    else:
        lying = propose_grid.propose(W, H, proposal_inch, look=look)
        cols, rows = lying['cols'], lying['rows']
    # The grid of a page when this screen stands up: the same proposal for the turned canvas, which on square glass
    # is the same answer again. A card keeps its size in millimetres, so glass that holds three columns lying down
    # may hold one standing up.
    if a.portrait_cols and a.portrait_rows:
        tall_cols, tall_rows = a.portrait_cols, a.portrait_rows
    else:
        tall = propose_grid.propose(H, W, proposal_inch, look=look)
        tall_cols, tall_rows = tall['cols'], tall['rows']
    if W == H:
        tall_cols, tall_rows = cols, rows
    # The panel's own pixels: the canvas lying down, turned back by the angle that lays it out that way. The display
    # block drives the panel at this size whichever way the screen hangs; LVGL turns the picture.
    native_w, native_h = (H, W) if a.rotation in (90, 270) else (W, H)

    packages = re.search(r'^packages:\n(.*?)(?=^[a-z_0-9]+:|\Z)', source, re.M | re.S)[0].rstrip('\n') + '\n'
    packages = re.sub(r'(look: !include \.\./looks/)\w+(\.yaml)', rf'\g<1>{look}\g<2>', packages)
    lines = [
        f'# ESP Screens - {a.name}: a {a.inch}-inch {W} x {H} panel. Written by tools/new_board.py from the {a.template}',
        '# board: its packages and its hardware sections are the template\'s until they are replaced by this board\'s',
        '# (docs/ADDING_A_BOARD.md). docs/PROFILES.md says how the files of a screen fit together.',
        packages,
        'substitutions:',
        '  # The key of this board file; the firmware reports it so ESP Screens knows what board a screen is.',
        f'  BOARD_ID: "{a.name}"',
        f'  DEVICE_NAME: "{a.name}-new"',
        f'  DEVICE_FRIENDLY_NAME: "My {a.name}"',
        '',
        f'  # The glass: {diagonal:.0f} {"diameter" if a.shape == "round" else "diagonal"} pixels over {a.inch} inches.',
        f'  PANEL_W: "{native_w}"',
        f'  PANEL_H: "{native_h}"',
        f'  DISPLAY_DPI: "{dpi:.3f}"',
    ]
    if a.shape == 'round':
        lines += ['  DISPLAY_SHAPE: "round"']
    if a.rotation:
        lines += [f'  # The LVGL angle that lays this panel out lying down ({W} x {H}). Standing up is a quarter further.',
                  f'  ROTATION_LANDSCAPE: "{a.rotation}"']
    lines += ['  # The tile grid: columns and rows of cells lying down, and standing up.',
              f'  GRID_COLS: "{cols}"', f'  GRID_ROWS: "{rows}"']
    if (tall_cols, tall_rows) != (cols, rows):
        lines += [f'  GRID_COLS_PORTRAIT: "{tall_cols}"', f'  GRID_ROWS_PORTRAIT: "{tall_rows}"']
    buffer = profiles.substitutions_of(template).get('LVGL_BUFFER_SIZE', '12%')
    lines += [f'  LVGL_BUFFER_SIZE: "{buffer}"                       # LVGL\'s draw buffer as a share of the screen', '']
    copied = own_substitutions(source)
    if copied:
        lines += [f'  # From the {a.template} board: its hardware values and the code it hands the shared lambdas. Replace them',
                  '  # with this board\'s, as the hardware sections below.']
        for group in copied:
            lines += group
        lines.append('')

    dest = profiles.ROOT / 'packages' / 'boards' / f'{a.name}.yaml'
    if dest.exists():
        raise SystemExit(f'{dest.relative_to(profiles.ROOT)} is there already.')
    hardware = source[source.index(BANNER):] if BANNER in source else ''
    # The display block drives the panel at its own size.
    hardware, n = re.subn(r'(?s)(dimensions:\s*\n\s*width:\s*)\d+(\s*\n\s*height:\s*)\d+', rf'\g<1>{native_w}\g<2>{native_h}',
                          hardware, count=1)
    if not n:
        hardware = re.sub(r'(dimensions: \{width: )\d+(, height: )\d+', rf'\g<1>{native_w}\g<2>{native_h}', hardware, count=1)
    dest.write_text('\n'.join(lines) + '\n' + hardware)

    print(f'{dest.relative_to(profiles.ROOT)}: panel {native_w} x {native_h}, {dpi:.1f} dpi, the {look} look, grid {cols} x {rows} '
          f'lying down and {tall_cols} x {tall_rows} standing up')
    run = lambda *tool: subprocess.run([sys.executable, *tool], cwd=profiles.ROOT, check=True)  # noqa: E731
    if lab:
        print('Next: replace the hardware sections and the values copied from the template, then render it '
              '(docs/ADDING_A_BOARD.md). A lab board stays out of the catalog and out of Git.')
        return
    entry = profiles.CATALOG[a.template]
    catalog = profiles.ROOT / 'boards.yaml'
    catalog.write_text(catalog.read_text().rstrip('\n') + '\n\n' + '\n'.join([
        f'{a.name}:', f'  file: {a.name}.yaml', f'  name: {a.title or entry["name"]}',
        f'  model: {a.model or a.name.upper()}', f'  status: {a.status}']) + '\n')
    contract = profiles.ROOT / 'tests' / 'fixtures' / 'overrides' / f'{a.name}-contract.yaml'
    contract.write_text(CONTRACT)
    run('tools/generate_entries.py')
    run('tools/generate_board_shapes.py')
    print(f'Added to boards.yaml, with packages/{a.name}.yaml, checkout/{a.name}.yaml and {contract.relative_to(profiles.ROOT)}.')
    print('Next: replace the hardware sections and the values copied from the template with this board\'s, run '
          'tools/check.sh --firmware, and render it (docs/ADDING_A_BOARD.md).')

if __name__ == '__main__':
    main()
