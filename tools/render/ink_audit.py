"""The ink audit: the first rule of a glass of ink, held for a picture (docs/GLASS_KINDS.md, "The audit").

A glyph or a word stands on ink or on paper, never on a raster and never on a picture. On a glass that prints with two
inks a tone between them is a pattern of dots, and a letter in or on such a pattern is broken: every fault the first
paper screen showed was one of these (a faded key, a tint under an icon, words on a cover).

It needs two things of a picture, and run.py gives both for every picture of a board whose glass is ink:

  seen     what the host program saw LVGL draw (components/smart_display/ink_audit.h), in drawing order:
           'T' the box a text's ink lies in, 'G' a ground that covers what is under it, 'P' a picture
  raster   where the paper glass's own ink step printed a raster (tools/render/paper_ink_tool.cpp, `raster`):
           a picture of the glass, white where a pixel lay between two inks in an even stretch of its tone

Free of the render and of ESPHome, so tests/test_ink_audit.py runs it on pictures of its own.
"""
from collections import Counter


def flat(glass, box, reach=3):
    """Whether the glass around `box` is one tone: the ring `reach` pixels wide around it, nine tenths of it at least.
    A text on a picture has the picture's grain around it; one on paper or on ink has that tone."""
    outer = (max(0, box[0] - reach), max(0, box[1] - reach), min(glass.width - 1, box[2] + reach), min(glass.height - 1, box[3] + reach))
    ring = Counter()
    pixels = glass.load()
    for y in range(outer[1], outer[3] + 1):
        for x in range(outer[0], outer[2] + 1):
            if not (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
                ring[pixels[x, y]] += 1
    return not ring or ring.most_common(1)[0][1] * 10 >= sum(ring.values()) * 9


def read(text):
    """The host program's lines as (kind, (x1, y1, x2, y2), words), in the order they were drawn."""
    seen = []
    for line in text.splitlines():
        kind, x1, y1, x2, y2, *words = line.split(' ', 5)
        box = (int(x1), int(y1), int(x2), int(y2))
        if box[2] >= box[0] and box[3] >= box[1]:
            seen.append((kind, box, words[0] if words else ''))
    return seen


def inside(inner, outer):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def faults(name, raster, seen, glass=None):
    """What breaks the rule in one picture, as lines for a person, and how many texts were judged. `glass` is the
    picture itself, as LVGL drew it.

    A text is judged where it shows: one that a later ground or picture covers whole is not on the glass. It stands on
    a picture when a picture drawn before it lies under its middle, no ground drawn between the two covers it (a
    band of black under a screensaver's words is such a ground), and the glass around the text is not one tone: a
    picture's box may be larger than what it shows (a map with room under it), and words in that room stand on paper. It stands in a raster when the ink step printed a
    raster inside its box: its own colour is a tone between ink and paper, or its ground is. A raster under a text is
    most of its box, and letters of a raster are a tenth of it or more. Under a twentieth of the box (and under six
    pixels) is no fault: that is the rim of what lies beside the text or around it, the soft edge of the disc a glyph
    stands in, the end of the area under a graph's line."""
    found, judged, said = [], 0, set()
    for at, (kind, box, words) in enumerate(seen):
        if kind != 'T' or (words, box) in said:
            continue
        said.add((words, box))
        if any(k in 'GP' and inside(box, b) for k, b, _ in seen[at + 1:]):
            continue
        judged += 1
        middle = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
        under = [n for n, (k, b, _) in enumerate(seen[:at]) if k == 'P' and b[0] <= middle[0] <= b[2] and b[1] <= middle[1] <= b[3]]
        if under and not any(k == 'G' and inside(box, b) for k, b, _ in seen[under[-1] + 1:at]) and not (glass and flat(glass, box)):
            found.append(f'{name}: "{words[:40]}" stands on a picture at {box[0]},{box[1]}')
            continue
        core = (max(0, box[0] + 1), max(0, box[1] + 1), min(raster.width, box[2]), min(raster.height, box[3]))
        if core[2] <= core[0] or core[3] <= core[1]:
            continue
        dots = sum(raster.crop(core).histogram()[128:])
        if dots > max(6, (core[2] - core[0]) * (core[3] - core[1]) // 20):
            found.append(f'{name}: "{words[:40]}" stands in a raster at {box[0]},{box[1]} '
                         f'({dots} pixels of it in a box of {box[2] - box[0] + 1} x {box[3] - box[1] + 1})')
    return found, judged
