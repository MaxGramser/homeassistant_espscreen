"""Write packages/cells/<n>.yaml: the cards of a board's grid, and the line that binds them.

A screen draws one card per cell of its grid (GRID_COLS x GRID_ROWS). The cards are LVGL widgets, so they are
written in YAML, and ESPHome has no loop: this script writes one file per cell count, and every board includes
the file for its own count. The file carries the cards themselves (as children of the shared `tile_scroll`, the
grid) and `BIND_CELLS`, the line the shared boot lambda runs to hand them to the runtime. The circle, the name and
the state carry no place: the runtime puts them where the cell they got asks (runtime_tiles::head_row).

    python3 tools/generate_cells.py            # the cards of every board that ships (tools/profiles.py)
    python3 tools/generate_cells.py --lab      # and of the boards tried out here (packages/boards/lab-*.yaml)
    python3 tools/generate_cells.py --check    # fail when a shipped board's file is out of date (tools/check.sh)

The card itself is one template, the same for every board: the board's sizes reach it through substitutions. The
files of the shipped boards are in Git, because a screen builds from them over GitHub; a lab board's file is
written on this machine only, which is why the lab boards are asked for by name.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402

ROOT = profiles.ROOT
CELLS = ROOT / 'packages' / 'cells'

HEAD = '''############################################################
# ESP Screens - the cards of a grid of {count} cells.
#
# Written by tools/generate_cells.py; do not edit. A board includes the file for its own number of cells
# (GRID_COLS x GRID_ROWS) and the shared tree in packages/core.yaml places them: the container `tile_scroll`
# is an LVGL grid and runtime_tiles::place_page gives every card its cell and span. A card carries no
# coordinate, only the size its board's grid gives it; its circle, name and state are placed by the runtime
# on the cell it got (runtime_tiles::head_row), so a board states the icon's size and nothing else of the head.
############################################################
substitutions:
  # The shared boot lambda hands the cards to the runtime with this line (packages/core.yaml).
  BIND_CELLS: |-
{binds}

lvgl:
  pages:
    - id: !extend home_page
      widgets:
        - obj:
            id: !extend tile_scroll
            widgets:
'''

CARD = '''              # ---------- CARD {n} ----------
              - obj:
                  id: tile{n}
                  grid_cell_row_pos: 0
                  grid_cell_column_pos: 0
                  # A seed: runtime_tiles::bind puts the card in a cell of the grid and LVGL stretches it to
                  # that cell, whichever way the glass hangs (firmware 0.2.92+).
                  width: 1
                  height: 1
                  styles: style_tile
                  scrollable: false
                  scrollbar_mode: 'OFF'
                  widgets:
                    - obj:
                        id: tile{n}_icon_circle
                        width: ${{TILE_ICON_SIZE}}
                        height: ${{TILE_ICON_SIZE}}
                        styles: style_icon_circle
                        clickable: false
                        scrollable: false
                        scrollbar_mode: 'OFF'
                        widgets:
                          - label:
                              id: tile{n}_icon_lbl
                              align: CENTER
                              text_font: materialdesign_icons
                              text: "\\U000F002A"
                              clickable: false
                    - label:
                        id: t{n}_title
                        text: "Tile {n}"
                        styles: style_title
                        clickable: false
                    - label:
                        id: t{n}_value
                        text: "—"
                        styles: style_value
                        clickable: false
'''


def text(count):
    binds = '\n'.join(
        f'    runtime_tiles::bind({n - 1}, id(tile{n}), id(t{n}_title), id(t{n}_value), id(tile{n}_icon_circle), id(tile{n}_icon_lbl));'
        for n in range(1, count + 1))
    return HEAD.format(count=count, binds=binds) + ''.join(CARD.format(n=n) for n in range(1, count + 1))


def counts(lab=False):
    """Every cell count the shipped boards ask for (GRID_COLS x GRID_ROWS), and the lab boards' with `lab`."""
    boards = [(profiles.CATALOG[key].get('choices') or {}, path) for key, path in profiles.BOARDS.items()]
    if lab:
        boards += [({}, path) for path in sorted((ROOT / 'packages' / 'boards').glob('lab-*.yaml'))]
    found = set()
    for choices, board in boards:
        values = profiles.evaluate(profiles.raw_substitutions(board))
        if 'GRID_COLS' in values and 'GRID_ROWS' in values:
            # One file serves a board either way up, so it holds the cells of whichever page asks for most.
            found.add(max(int(values['GRID_COLS']) * int(values['GRID_ROWS']),
                          int(values.get('GRID_COLS_PORTRAIT', values['GRID_COLS'])) * int(values.get('GRID_ROWS_PORTRAIT', values['GRID_ROWS']))))
            # A grid someone may choose when the screen is built (boards.yaml `choices`) needs its own file too; such a
            # board names its cards file by GRID_CELLS, so the screen takes the file of the grid it was built with.
            for rows in choices.get('GRID_ROWS', []):
                found.add(int(values['GRID_COLS']) * int(rows))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--lab', action='store_true', help='also the cards of the lab boards (packages/boards/lab-*.yaml)')
    args = parser.parse_args()
    CELLS.mkdir(parents=True, exist_ok=True)
    stale = []
    for count in counts(args.lab):
        path = CELLS / f'{count}.yaml'
        want = text(count)
        if args.check:
            if not path.exists() or path.read_text() != want:
                stale.append(path.name)
        else:
            path.write_text(want)
            print(f'{path.relative_to(ROOT)}: {count} cards')
    if args.check:
        if stale:
            print('out of date, run tools/generate_cells.py: ' + ', '.join(stale), file=sys.stderr)
            return 1
        print(f'cells: {len(counts(args.lab))} files up to date')
    return 0


if __name__ == '__main__':
    sys.exit(main())
