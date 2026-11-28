"""Contact sheets of a folder of renders, to leaf through them: several pictures side by side on one sheet.

    python3 tools/render/sheets.py SOURCE OUT [PER]

SOURCE is a folder of PNGs that tools/render/run.py made (.esphome/render/out/<variant>), OUT the folder the sheets go
to (emptied of older sheets first), PER how many pictures a sheet holds: 6 (three by two, each at two thirds of its
size, the default) or 4 (two by two at full size, for looking closely). Each picture has its name under it. Needs
Pillow: `uv run --no-project --python 3.13 --with pillow python tools/render/sheets.py ...`.

Made for a board whose glass is e-paper (docs/PAPER.md, "Seeing it without a screen"), where a design is judged by
eye on the renders before it goes to a real glass; it works on any folder of pictures of one size.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def sheets(source, out, per=6):
    """Write the sheets of `source` into `out`; returns (pictures, sheets)."""
    columns, rows, scale = (3, 2, (2, 3)) if per == 6 else (2, 2, (1, 1))
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*.png'):
        old.unlink()
    names = sorted(source.glob('*.png'))
    made = 0
    for start in range(0, len(names), per):
        group = names[start:start + per]
        with Image.open(group[0]) as first:
            w, h = first.width * scale[0] // scale[1], first.height * scale[0] // scale[1]
        sheet = Image.new('RGB', (columns * (w + 12) + 12, rows * (h + 34) + 12), (120, 120, 120))
        draw = ImageDraw.Draw(sheet)
        for n, path in enumerate(group):
            image = Image.open(path).convert('RGB')
            if image.size != (w, h):
                image = image.resize((w, h), Image.LANCZOS)
            x, y = 12 + (n % columns) * (w + 12), 12 + (n // columns) * (h + 34)
            sheet.paste(image, (x, y))
            draw.text((x, y + h + 6), path.stem[:46], fill=(255, 255, 255))
        sheet.save(out / f'{start // per + 1:02d}.png')
        made += 1
    return len(names), made


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    if per not in (4, 6):
        raise SystemExit('PER is 4 or 6')
    pictures, made = sheets(Path(sys.argv[1]), Path(sys.argv[2]), per)
    print(f'{pictures} pictures on {made} sheets in {sys.argv[2]}')


if __name__ == '__main__':
    main()
