"""Font/style profiles used by both code generation and source fingerprinting."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def variants():
    # Read actual board densities from the shared catalog, rather than maintaining
    # a second list of hardware profiles in the browser renderer.
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
    profiles = {}
    for entry, shape in shapes.items():
        if entry.startswith('checkout/'):
            profiles.setdefault((shape['dpi'], shape['look']), entry)
    # A custom 720px/4-inch display can be designed before hardware support exists.
    profiles.setdefault((254, 'standard'), 'checkout/guition.yaml')
    return [(dpi, look, entry) for (dpi, look), entry in sorted(profiles.items())]
