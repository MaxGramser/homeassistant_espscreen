"""A Valetudo robot's map camera (screen_manager/app/valetudo_map.py): the placeholder PNG Valetudo hands Home Assistant
carries the map as deflated JSON in a zTXt chunk, and the app draws that map instead of showing the placeholder."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import valetudo_map  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)


def placeholder(valetudo):
    """A PNG as Valetudo's MapNodeMqttHandle makes it: its wrapper image with the map's zTXt chunk before IEND."""
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (40, 30), (0, 80, 200)).save(out, 'PNG')
    image = out.getvalue()
    text = chunk(b'zTXt', b'ValetudoMap\0\0' + zlib.compress(json.dumps(valetudo).encode()))
    return image[:-12] + text + image[-12:]


def flat():
    """Two rooms side by side in a wall box, a path, the charger, the robot and a no-go zone (5 cm per pixel)."""
    def box(x0, y0, x1, y1):
        return [v for y in range(y0, y1) for v in (x0, y, x1 - x0)]
    wall = box(100, 100, 161, 101) + box(100, 140, 161, 141) + [v for y in range(101, 140) for v in (100, y, 1, 160, y, 1)]
    return {
        '__class': 'ValetudoMap', 'pixelSize': 5, 'size': {'x': 5000, 'y': 5000},
        'layers': [
            {'type': 'segment', 'compressedPixels': box(101, 101, 130, 140), 'metaData': {'segmentId': '1', 'name': 'Kitchen'}},
            {'type': 'segment', 'compressedPixels': box(130, 101, 160, 140), 'metaData': {'segmentId': '2', 'name': 'Hall'}},
            {'type': 'wall', 'compressedPixels': wall},
        ],
        'entities': [
            {'type': 'path', 'points': [550, 550, 700, 550, 700, 650]},
            {'type': 'charger_location', 'points': [520, 680]},
            {'type': 'robot_position', 'points': [700, 650], 'metaData': {'angle': 90}},
            {'type': 'no_go_area', 'points': [720, 520, 780, 520, 780, 580, 720, 580]},
        ],
    }


@unittest.skipUnless(HAS_PIL, 'Pillow draws the map')
class ValetudoMapTest(unittest.TestCase):
    def test_reads_the_map_out_of_the_placeholder(self):
        raw = placeholder(flat())
        self.assertEqual(json.loads(valetudo_map.map_json(raw))['pixelSize'], 5)

    def test_another_picture_is_none_of_its_business(self):
        from PIL import Image
        out = io.BytesIO()
        Image.new('RGB', (10, 10)).save(out, 'PNG')
        self.assertIsNone(valetudo_map.map_json(out.getvalue()))
        self.assertIsNone(valetudo_map.render(out.getvalue()))
        self.assertEqual(asyncio.run(valetudo_map.prepared(out.getvalue())), out.getvalue())

    def test_draws_rooms_walls_and_the_robot_cropped_to_the_flat(self):
        from PIL import Image
        drawn = valetudo_map.render(placeholder(flat()))
        with Image.open(io.BytesIO(drawn)) as image:
            image = image.convert('RGBA')
            # 61 x 41 map pixels and a margin of 2 each side, every map pixel 12 picture pixels (800 // 65).
            k = valetudo_map.SIDE // 65
            self.assertEqual(image.size, (65 * k, 45 * k))
            self.assertEqual(image.getpixel((0, 0))[3], 0)  # the ground is the tile's
            at = lambda x, y: image.getpixel(((x - 98) * k + k // 2, (y - 98) * k + k // 2))  # noqa: E731
            self.assertEqual(at(110, 110)[:3], valetudo_map.ROOMS[0])
            self.assertEqual(at(152, 135)[:3], valetudo_map.ROOMS[1])
            self.assertEqual(at(100, 120), valetudo_map.WALL)
            self.assertEqual(at(140, 130), valetudo_map.ROBOT)  # the robot at 700, 650 cm

    def test_a_broken_map_keeps_the_placeholder(self):
        raw = placeholder({'layers': [], 'entities': []})
        self.assertIsNone(valetudo_map.render(raw))
        self.assertEqual(asyncio.run(valetudo_map.prepared(raw)), raw)

    def test_draws_each_map_once(self):
        raw = placeholder(flat())
        calls = []
        real = valetudo_map.render
        valetudo_map.render = lambda r: calls.append(r) or real(r)
        try:
            valetudo_map.DRAWN.clear()
            first = asyncio.run(valetudo_map.prepared(raw))
            again = asyncio.run(valetudo_map.prepared(raw))
        finally:
            valetudo_map.render = real
        self.assertEqual(len(calls), 1)
        self.assertEqual(first, again)
        self.assertNotEqual(first, raw)


if __name__ == '__main__':
    unittest.main()
