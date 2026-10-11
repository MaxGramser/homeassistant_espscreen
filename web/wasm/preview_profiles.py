"""Font/style profiles used by both code generation and source fingerprinting."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# How far a board has been tried, most first (STATUSES in tools/generate_board_shapes.py, boards.yaml `status`).
TRIED = ('stable', 'new', 'experimental')


def variants():
    # Read actual board densities from the shared catalog, rather than maintaining
    # a second list of hardware profiles in the browser renderer.
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
    # The preview is built once per density and look, with the frame and fonts of one board that has them: the one
    # tried furthest, then the first by name. A board added later with the density of one people already use (an
    # experimental 4.3-inch at the Waveshare 4.3-inch's 217 dpi) leaves that board's preview as it was.
    entries = sorted((entry for entry in shapes if entry.startswith('checkout/')),
                     key=lambda entry: (TRIED.index(shapes[entry]['catalog']['status']), entry))
    profiles = {}
    for entry in entries:
        shape = shapes[entry]
        profiles.setdefault((shape['dpi'], shape['look']), entry)
    # A custom 720px/4-inch display can be designed before hardware support exists.
    profiles.setdefault((254, 'standard'), 'checkout/guition.yaml')
    return [(dpi, look, entry) for (dpi, look), entry in sorted(profiles.items())]
