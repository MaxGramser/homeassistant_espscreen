"""Propose columns x rows for a board from its resolution and its diagonal (docs/ADDING_A_BOARD.md).

Physical targets come from the two boards we have: the Guition (4.0", 480x480, ~170 dpi)
is the *standard* look, the CYD (2.8", 320x240, ~143 dpi) the *compact* look. Everything
is expressed in millimetres so that a tile keeps its size on the wall whatever the glass.
"""
import math
import re
from pathlib import Path

MM = 25.4
# The most columns or rows a grid takes, either way the glass hangs: the firmware's own ceiling in
# packages/looks/shared/grid.yaml (GRID_MAX_ROWS and its three siblings), so a proposal is never a grid the firmware
# refuses at its build ("the board's own grid is out of its range", runtime_model.h).
GRID_CEILING = int(re.search(r'GRID_MAX_ROWS: \$\{ \[(\d+),',
                             (Path(__file__).resolve().parents[1] / 'packages/looks/shared/grid.yaml').read_text())[1])

# Physical spec of a look: everything in mm, measured back from the two existing boards.
LOOKS = {
    # name: (tile_w_pref, tile_h_pref, tile_w_min, tile_h_min, gap_col, gap_row, margin, top_bar, page_bar)
    "standard": (218 / 6.69, 108 / 6.69, 30.0, 12.0, 12 / 6.69, 12 / 6.69, 16 / 6.69, 72 / 6.69, 60 / 6.69),
    "compact": (147 / 5.63, 52 / 5.63, 22.0, 8.0, 8 / 5.63, 4 / 5.63, 9 / 5.63, 40 / 5.63, 36 / 5.63),
}

# Font reference: label 18 pt at 170 dpi (standard), 11 pt at 143 dpi (compact) -> mm
LABEL_MM = {"standard": 18 / 6.69, "compact": 11 / 5.63}


def count(usable, pref, minimum, gap):
    n = round((usable + gap) / (pref + gap))
    cap = min(math.floor((usable + gap) / (minimum + gap)), GRID_CEILING)
    return max(1, min(n, cap))


def propose(w, h, inch, look=None):
    dpi = math.hypot(w, h) / inch
    ppm = dpi / MM
    w_mm, h_mm = w / ppm, h / ppm
    looks = [look] if look else ["standard", "compact"]
    for name in looks:
        tw, th, tw_min, th_min, gc, gr, margin, top, bar = LOOKS[name]
        usable_w = w_mm - 2 * margin
        usable_h = h_mm - top - bar
        cols = count(usable_w, tw, tw_min, gc)
        rows = count(usable_h, th, th_min, gr)
        # Glass with room for only one card of the minimum width, stacking at least three of them: one standard
        # column the full width is the right answer there, not a reason to drop to the compact look. That is how a
        # screen standing up is laid out (the Waveshare's 480 x 800 is 56 mm wide, where two standard cards would be
        # 26 mm each and one is 51 mm, and it holds four of them). Three is where the single column earns its place:
        # on glass that stacks only two, a page of two cards is worse than the denser compact grid, which is why a
        # 3.2-inch CYD and a CYD standing up stay compact.
        one_column = math.floor((usable_w + gc) / (tw_min + gc)) < 2
        if cols >= 2 and rows >= 2 or one_column and rows >= 3 or name == "compact" or look:
            tile_w_mm = (usable_w - (cols - 1) * gc) / cols
            tile_h_mm = (usable_h - (rows - 1) * gr) / rows
            return dict(
                dpi=round(dpi), look=name, cols=cols, rows=rows,
                tile_px=(round(tile_w_mm * ppm), round(tile_h_mm * ppm)),
                tile_mm=(round(tile_w_mm), round(tile_h_mm)),
                label_pt=round(LABEL_MM[name] * ppm),
                glass_mm=(round(w_mm), round(h_mm)),
            )


# The panels, each by the canvas it draws on. A board that ships is here twice when its glass is not square: once
# lying down and once standing up, because those are two different screens with two different grids (the board file
# states both, GRID_COLS and GRID_COLS_PORTRAIT). The square Guition has one row only: standing it up gives back the
# screen it already is.
BOARDS = [
    ("Sunton 2432S028 (CYD 2.8\")", 320, 240, 2.8),
    ("Sunton 2432S032 (CYD 3,2\")", 320, 240, 3.2),
    ("Sunton 2432S028 standing up (CYD 2.8\")", 240, 320, 2.8),
    ("Guition JC3248W535 / WT32-SC01 Plus (3,5\")", 480, 320, 3.5),
    ("Guition JC4827W543 / Sunton 4827S043 (4,3\")", 480, 272, 4.3),
    ("Guition 4848S040 / Seeed Indicator / Waveshare 4\" (4,0\")", 480, 480, 4.0),
    ("Waveshare ESP32-S3-Touch-LCD-4.3 (4,3\")", 800, 480, 4.3),
    ("Waveshare ESP32-S3-Touch-LCD-4.3 standing up (4,3\")", 480, 800, 4.3),
    ("Sunton 8048S050 (5\")", 800, 480, 5.0),
    ("Sunton 8048S070 / Waveshare 7\" / CrowPanel 7 (7\")", 800, 480, 7.0),
    ("Waveshare ESP32-S3-Touch-LCD-5 (5\")", 1024, 600, 5.0),
    ("Waveshare 7\" 1024x600 (7\")", 1024, 600, 7.0),
    ("Waveshare ESP32-P4 4B/4C (4,0\")", 720, 720, 4.0),
    ("M5Stack Tab5 (5\")", 1280, 720, 5.0),
    ("Waveshare 7-DSI, landscape (7\")", 1280, 720, 7.0),
    ("Waveshare 10.1-DSI, landscape (10,1\")", 1280, 800, 10.1),
    ("Guition JC8012P4A1 standing up (10,1\")", 800, 1280, 10.1),
]

if __name__ == "__main__":
    print(f"{'board':58} {'res':9} {'dpi':>4} {'look':8} {'grid':6} {'tile px':10} {'tile mm':9} {'label pt':8} glass mm")
    for name, w, h, inch in BOARDS:
        p = propose(w, h, inch)
        print(f"{name:58} {w}x{h:<5} {p['dpi']:>4} {p['look']:8} {p['cols']}x{p['rows']:<4} "
              f"{p['tile_px'][0]}x{p['tile_px'][1]:<6} {p['tile_mm'][0]}x{p['tile_mm'][1]:<6} {p['label_pt']:>8} {p['glass_mm'][0]}x{p['glass_mm'][1]}")
    print()
    print("standard look forced on the 3.5\" and 4.3\" boards, for comparison:")
    for name, w, h, inch in BOARDS[3:5]:
        p = propose(w, h, inch, look="standard")
        print(f"  {name}: {p['cols']}x{p['rows']} tiles {p['tile_px']} px = {p['tile_mm']} mm, label {p['label_pt']} pt")
