"""Render native round screenshots with diagnostics/send_layout.py's canonical demo devices.

Uses the committed firmware WASM, without Home Assistant, browser rendering or custom widgets.
    python3 tools/render/round.py --out .esphome/render/round
    python3 tools/render/round.py --fixture   # the same wire fixture for the WASM regression test
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'diagnostics'), str(ROOT / 'screen_manager/app')]


def fixture():
    from send_layout import Grid, configuration
    _, values, bars, region = configuration(Grid(2, 2, pages=24, tiles=128), controls=True,
                                           now=datetime(2026, 9, 15, 8, 8, tzinfo=timezone.utc))
    entities = ['light.demo_table_lamp', 'light.demo_ceiling', 'climate.demo_heating',
                'media_player.demo_radio', 'weather.demo_outside']
    tiles = []
    for i, entity in enumerate(entities):
        tile = next(t for t in values if t['entity'] == entity)
        tile = {**tile, 'o': dict(tile.get('o', {})), 'slot': i}
        if i < 4:
            tile['o'].pop('size', None)
            tile['o'].pop('controls', None)
        tiles.append(tile)
    # The ordinary full-size light card on its own page, through the existing tile size option.
    tiles.append({**tiles[0], 'slot': 8, 'o': {**tiles[0]['o'], 'size': 'full'}})
    return dict(tiles=tiles, items=bars[0], region=region)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT / '.esphome/render/round')
    args = parser.parse_args()
    if args.fixture:
        print(json.dumps(fixture(), ensure_ascii=False))
        return
    from PIL import Image, ImageDraw
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['node', str(ROOT / 'web/wasm/test_round_display.mjs')], check=True,
                   env={**os.environ, 'PYTHON': sys.executable, 'ROUND_RENDER_DIR': str(out)})
    # Only remove the unlit corners. Preserve every native pixel at the panel's real resolution.
    mask = Image.new('L', (466, 466))
    ImageDraw.Draw(mask).ellipse((0, 0, 465, 465), fill=255)
    for raw in sorted(out.glob('lilygo175-*.rgba')):
        image = Image.frombytes('RGBA', (466, 466), raw.read_bytes())
        image.putalpha(mask)
        image.save(raw.with_suffix('.png'))
        raw.unlink()
        print(raw.with_suffix('.png'))


if __name__ == '__main__':
    main()
