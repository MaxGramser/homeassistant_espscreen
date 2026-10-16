"""A Valetudo robot's map on a camera tile.

Valetudo hands Home Assistant its map as a camera (MQTT, topic `MapData/map-data-hass`) whose picture is a placeholder
that says to install a Lovelace card: the map itself rides along in the PNG, as JSON deflated into a zTXt chunk named
`ValetudoMap` (Valetudo's backend/lib/mqtt/handles/MapNodeMqttHandle.js). A screen would show the placeholder, so the
app reads that chunk and draws the map itself, once per map Valetudo sends (camera_feed.Feed.fetch_one), and the
picture then goes the way of any camera's.

The map (backend/lib/entities/map/): `pixelSize` centimetres per map pixel; `layers` of type floor, segment (a room)
and wall, their pixels in map pixels as runs of [x, y, count] (`compressedPixels`; older maps a flat `pixels` list);
`entities` in centimetres: the robot and the charger as one point, the path as a line, virtual walls as two points and
the no-go, no-mop and cleaning zones as polygons.

The ground stays transparent, so the map stands on the tile's own colour in light and in dark.
"""
import asyncio
from collections import OrderedDict
import hashlib
import io
import json
import math
import struct
import zlib

from map_card import PEOPLE

KEYWORD = b'ValetudoMap'
SIGNATURE = b'\x89PNG\r\n\x1a\n'
# A big flat's map is a few hundred kilobytes of JSON; anything far larger is not one Valetudo made.
MAX_JSON = 32 * 1024 * 1024
# The long side of the drawn map in pixels: the largest tile on the largest glass, and the full view, take it smaller.
SIDE = 800
MARGIN = 2  # map pixels around the walls

# Pure greys, which the glass's 16-bit colour keeps grey (map_card.py), readable on a light and on a dark tile.
FLOOR = (0x9A, 0x9A, 0x9A, 255)
WALL = (0x55, 0x55, 0x55, 255)
PATH = (0xFF, 0xFF, 0xFF, 230)
PREDICTED = (0xFF, 0xFF, 0xFF, 120)
# The rooms take the tile palette's strong half, as the people on a map do; the restricted parts its red.
ROOMS = tuple(((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF) for c in PEOPLE)
RED = ROOMS[6]
BLUE = ROOMS[0]
ROBOT = (0xFF, 0xFF, 0xFF, 255)
ROBOT_EDGE = (0x1B, 0x1B, 0x1B, 255)
CHARGER = ROOMS[2]


# The maps drawn last, by the digest of what Valetudo sent: Home Assistant hands out the same bytes until the map
# changes, and a live tile or the editor asks again every few seconds.
DRAWN = OrderedDict()
DRAWN_KEPT = 4


async def prepared(raw):
    """A camera's picture as a screen should get it: a Valetudo placeholder becomes the map it carries, drawn once per
    map, and any other picture stays as it is."""
    if KEYWORD not in raw:
        return raw
    digest = hashlib.sha1(raw).digest()
    drawn = DRAWN.get(digest)
    if drawn is None:
        drawn = await asyncio.get_running_loop().run_in_executor(None, render, raw) or raw
        DRAWN[digest] = drawn
        while len(DRAWN) > DRAWN_KEPT:
            DRAWN.popitem(last=False)
    DRAWN.move_to_end(digest)
    return drawn


def map_json(raw):
    """The ValetudoMap JSON a PNG carries, as bytes, or None for any other picture."""
    if not isinstance(raw, (bytes, bytearray)) or not raw.startswith(SIGNATURE) or KEYWORD not in raw:
        return None
    at = len(SIGNATURE)
    while at + 8 <= len(raw):
        length, kind = struct.unpack('>I4s', raw[at:at + 8])
        data = raw[at + 8:at + 8 + length]
        if kind == b'zTXt' and data.startswith(KEYWORD + b'\0'):
            inflater = zlib.decompressobj()
            text = inflater.decompress(data[len(KEYWORD) + 2:], MAX_JSON)
            return None if inflater.unconsumed_tail else text
        if kind == b'IEND':
            break
        at += 12 + length
    return None


def runs(layer):
    """A layer's pixels as (x, y, count) runs."""
    packed = layer.get('compressedPixels')
    if packed:
        return [tuple(packed[i:i + 3]) for i in range(0, len(packed) - 2, 3)]
    flat = layer.get('pixels') or []
    return [(flat[i], flat[i + 1], 1) for i in range(0, len(flat) - 1, 2)]


def render(raw):
    """The map a Valetudo placeholder carries, drawn as a PNG, or None when `raw` is not one (or not readable)."""
    text = map_json(raw)
    if text is None:
        return None
    try:
        return draw(json.loads(text))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None


def draw(valetudo):
    """A ValetudoMap (the JSON as a dict) drawn as a PNG on a transparent ground."""
    from PIL import Image, ImageDraw
    cell = float(valetudo.get('pixelSize') or 5)
    layers = [(layer.get('type'), layer, runs(layer)) for layer in valetudo.get('layers') or []]
    spans = [run for _, _, rs in layers for run in rs if run[2] > 0]
    if not spans:
        raise ValueError('an empty map')
    left = min(x for x, _, _ in spans) - MARGIN
    right = max(x + n for x, _, n in spans) + MARGIN
    top = min(y for _, y, _ in spans) - MARGIN
    bottom = max(y for _, y, _ in spans) + 1 + MARGIN
    width, height = right - left, bottom - top
    # Every map pixel the same whole number of picture pixels: walls stay crisp.
    k = max(1, SIDE // max(width, height))

    plan = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    pen = ImageDraw.Draw(plan)
    rooms = 0
    for order in ('floor', 'segment', 'wall'):
        for kind, layer, rs in layers:
            if kind != order:
                continue
            if kind == 'segment':
                colour = ROOMS[rooms % len(ROOMS)] + (255,)
                rooms += 1
            else:
                colour = WALL if kind == 'wall' else FLOOR
            for x, y, n in rs:
                pen.line((x - left, y - top, x - left + n - 1, y - top), fill=colour)
    image = plan.resize((width * k, height * k), Image.Resampling.NEAREST)

    def at(x, y):
        return ((x / cell - left) * k, (y / cell - top) * k)

    def points(entity):
        flat = entity.get('points') or []
        return [at(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]

    shade = Image.new('RGBA', image.size, (0, 0, 0, 0))
    shading = ImageDraw.Draw(shade)
    line = max(2, round(k * 0.6))
    entities = valetudo.get('entities') or []
    for entity in entities:
        kind, ps = entity.get('type'), points(entity)
        if kind in ('no_go_area', 'no_mop_area', 'active_zone') and len(ps) >= 3:
            colour = BLUE if kind == 'active_zone' else RED
            shading.polygon(ps, fill=colour + (70,), outline=colour + (255,), width=line)
        elif kind == 'virtual_wall' and len(ps) >= 2:
            shading.line(ps, fill=RED + (255,), width=line * 2)
    image = Image.alpha_composite(image, shade)
    pen = ImageDraw.Draw(image)
    for kind, colour in (('predicted_path', PREDICTED), ('path', PATH)):
        for entity in entities:
            ps = points(entity)
            if entity.get('type') == kind and len(ps) >= 2:
                pen.line(ps, fill=colour, width=line, joint='curve')
    dot = max(6, k * 3)
    for entity in entities:
        ps = points(entity)
        if not ps:
            continue
        x, y = ps[0]
        if entity.get('type') == 'charger_location':
            pen.ellipse((x - dot * 0.8, y - dot * 0.8, x + dot * 0.8, y + dot * 0.8), fill=CHARGER + (255,), outline=ROBOT, width=max(1, line // 2))
    for entity in entities:
        ps = points(entity)
        if entity.get('type') != 'robot_position' or not ps:
            continue
        x, y = ps[0]
        pen.ellipse((x - dot, y - dot, x + dot, y + dot), fill=ROBOT, outline=ROBOT_EDGE, width=max(2, line // 2))
        # Valetudo's angle: 0 points up (north on the map), clockwise.
        angle = math.radians(float((entity.get('metaData') or {}).get('angle') or 0))
        tip = (x + math.sin(angle) * dot * 0.75, y - math.cos(angle) * dot * 0.75)
        pen.line((x, y) + tip, fill=ROBOT_EDGE, width=max(2, line // 2))
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()
