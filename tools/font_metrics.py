"""What a font of the screens measures, read from the TrueType file itself (no FreeType needed).

`line_height(font, size)` is the line height LVGL gets for an ESPHome font: FreeType's size height ('hhea' ascender -
descender + line gap, scaled to the pixel size and rounded to whole pixels), which ESPHome's font component hands to
`lv_font_t.line_height`. Checked against the generated code of every board (the `font::Font(..., height, ...)` line of
main.cpp) when the alert started taking its title height from its font (app 0.2.128).
"""
import re
import struct
from pathlib import Path


def line_height(font, size):
    data = Path(font).read_bytes()
    tables = {}
    for i in range(struct.unpack('>H', data[4:6])[0]):
        tag, _, offset, _ = struct.unpack('>4sIII', data[12 + 16 * i:28 + 16 * i])
        tables[tag] = offset
    units_per_em = struct.unpack('>H', data[tables[b'head'] + 18:tables[b'head'] + 20])[0]
    ascender, descender, line_gap = struct.unpack('>hhh', data[tables[b'hhea'] + 4:tables[b'hhea'] + 10])
    scale = ((size * 64) << 16) // units_per_em                          # 16.16
    height = ((ascender - descender + line_gap) * scale + 0x8000) >> 16  # 26.6 pixels
    return (height + 32) // 64


def font_file(core_text, font_id):
    """The TrueType file packages/core.yaml builds a font from, by its id, relative to the repository."""
    found = re.search(r'- file: "\$\{FONT_DIR\}/([^"]+)"\n    id: ' + re.escape(font_id) + r'\n', core_text)
    if not found:
        raise KeyError(f'no font {font_id} in packages/core.yaml')
    return 'fonts/' + found[1]


def ink_top(font, size, char='H'):
    """From the top of a line of an ESPHome font to the top of a glyph's ink, as LVGL gets it: ESPHome's offset_y of that
    glyph, its ascender (FreeType's size ascender, rounded up to whole pixels) less the rendered glyph's top
    (font/__init__.py glyph_to_glyphinfo). Pillow renders with the same FreeType and the same hinting. The sections'
    band (docs/PAGES.md "Sections") puts a title's capitals by this; a host build logs the firmware's own figure."""
    from PIL import ImageFont
    face = ImageFont.truetype(str(font), size)
    ascender = face.getmetrics()[0]
    top = face.getbbox(char, anchor='ls')[1]  # the glyph's top above the baseline, negative
    return ascender + top
