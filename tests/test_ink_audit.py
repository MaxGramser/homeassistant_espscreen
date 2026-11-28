"""The ink audit of the host render (tools/render/ink_audit.py, docs/GLASS_KINDS.md "The audit"): a glyph or a word on
a glass of ink stands on ink or on paper, never on a raster and never on a picture.

The render gives it, for every picture of a paper board, what the host program saw LVGL draw
(components/smart_display/ink_audit.h) and where the paper glass's ink step printed a raster. Here it judges pictures
made by hand, one for each thing it has to tell apart. tests/test_paper_ink.cpp holds the other half: that the ink
step says a raster where it printed one.
"""
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'render'))
import ink_audit  # noqa: E402

W, H = 200, 120


def raster(*fields):
    """A picture of where the ink step printed a raster: white in each (x1, y1, x2, y2) of `fields`."""
    image = Image.new('L', (W, H), 0)
    draw = ImageDraw.Draw(image)
    for field in fields:
        draw.rectangle(field, fill=255)
    return image


class Faults(unittest.TestCase):
    def judge(self, mask, seen):
        return ink_audit.faults('page', mask, seen)

    def test_words_on_ink_or_on_paper_are_no_fault(self):
        found, judged = self.judge(raster(), [('G', (0, 0, W - 1, H - 1), ''), ('T', (20, 20, 99, 43), 'Living room')])
        self.assertEqual((found, judged), ([], 1))

    def test_words_on_a_raster_are_a_fault(self):
        # A tint under an icon, a faded key: the ground under the text is a tone between ink and paper.
        found, judged = self.judge(raster((10, 10, 150, 60)), [('T', (20, 20, 99, 43), 'Living room')])
        self.assertEqual(judged, 1)
        self.assertEqual(len(found), 1)
        self.assertIn('"Living room" stands in a raster at 20,20', found[0])

    def test_words_of_a_raster_are_a_fault(self):
        # Grey letters: the raster is in the strokes alone, a quarter of the box.
        mask = raster(*[(20 + n * 8, 20, 21 + n * 8, 43) for n in range(10)])
        found, _ = self.judge(mask, [('T', (20, 20, 99, 43), 'Unavailable')])
        self.assertEqual(len(found), 1)

    def test_the_rim_of_a_neighbour_is_no_fault(self):
        # The area under a graph's line ends a pixel or two inside a label's box.
        found, judged = self.judge(raster((20, 42, 26, 43)), [('T', (20, 20, 99, 43), 'set 10:08')])
        self.assertEqual((found, judged), ([], 1))
        # The soft edge of the disc a glyph stands in: a few pixels at each side of a box as large as the disc (a
        # tick in a to-do list's round box, on a reTerminal Sticky's render).
        rim = raster((36, 20, 39, 20), (36, 55, 39, 55), (20, 36, 20, 39), (55, 36, 55, 39))
        self.assertEqual(self.judge(rim, [('T', (20, 20, 55, 55), 'tick')]), ([], 1))

    def test_a_text_something_covers_is_not_on_the_glass(self):
        # A page's label under an alert's card, or under a picture over the whole glass: not judged.
        seen = [('T', (20, 20, 99, 43), 'Kitchen'), ('G', (0, 0, W - 1, H - 1), '')]
        self.assertEqual(self.judge(raster((0, 0, W - 1, H - 1)), seen), ([], 0))
        seen = [('T', (20, 20, 99, 43), 'Kitchen'), ('P', (0, 0, W - 1, H - 1), '')]
        self.assertEqual(self.judge(raster(), seen), ([], 0))

    def test_words_on_a_picture_are_a_fault(self):
        # A picture arrives in the panel's inks already, so no raster says it: the picture under the words does.
        seen = [('P', (0, 0, W - 1, H - 1), ''), ('T', (20, 80, 99, 103), 'Evening Drive')]
        found, judged = self.judge(raster(), seen)
        self.assertEqual(judged, 1)
        self.assertEqual(found, ['page: "Evening Drive" stands on a picture at 20,80'])

    def test_a_ground_between_the_picture_and_the_words_carries_them(self):
        # The screensaver's band of black across a picture's foot.
        seen = [('P', (0, 0, W - 1, H - 1), ''), ('G', (0, 70, W - 1, H - 1), ''), ('T', (20, 80, 99, 103), 'Evening Drive')]
        self.assertEqual(self.judge(raster(), seen), ([], 1))
        # A ground that does not hold the whole text is none.
        seen = [('P', (0, 0, W - 1, H - 1), ''), ('G', (0, 90, W - 1, H - 1), ''), ('T', (20, 80, 99, 103), 'Evening Drive')]
        self.assertEqual(len(self.judge(raster(), seen)[0]), 1)

    def test_words_in_the_room_a_picture_leaves_stand_on_paper(self):
        # A picture's box may be larger than what it shows: a robot's map with room under it, and the room's name there.
        seen = [('P', (0, 0, W - 1, H - 1), ''), ('T', (20, 80, 99, 103), 'Living room')]
        glass = Image.new('RGB', (W, H), (255, 255, 255))
        ImageDraw.Draw(glass).rectangle((10, 5, 190, 60), fill=(0, 0, 0))  # the map itself, above the words
        self.assertEqual(ink_audit.faults('page', raster(), seen, glass), ([], 1))
        # With the picture's grain around the words they stand on the picture.
        for y in range(70, H):
            for x in range(0, W, 2):
                glass.putpixel((x + y % 2, y), (0, 0, 0))
        self.assertEqual(len(ink_audit.faults('page', raster(), seen, glass)[0]), 1)

    def test_words_beside_a_picture_are_no_fault(self):
        seen = [('P', (0, 0, 99, 59), ''), ('T', (110, 20, 189, 43), 'Front door')]
        self.assertEqual(self.judge(raster(), seen), ([], 1))

    def test_a_text_is_judged_once_however_often_it_was_drawn(self):
        seen = [('T', (20, 20, 99, 43), 'Off')] * 3
        found, judged = self.judge(raster((10, 10, 150, 60)), seen)
        self.assertEqual((len(found), judged), (1, 1))


class Read(unittest.TestCase):
    def test_the_host_programs_lines(self):
        seen = ink_audit.read('G 0 0 479 799 \nP 10 20 109 119 \nT 30 40 129 63 Living room now\nT 5 5 4 4 gone\n')
        self.assertEqual(seen, [('G', (0, 0, 479, 799), ''), ('P', (10, 20, 109, 119), ''), ('T', (30, 40, 129, 63), 'Living room now')])

    def test_the_host_program_writes_them_beside_a_snapshot_of_a_glass_of_ink(self):
        host = (ROOT / 'tools/render/host.py').read_text()
        self.assertIn('const bool audit = glass_kind::ink();', host)
        self.assertIn('ink_audit::watch(lv_screen_active());', host)
        self.assertIn('ink_audit::watch(lv_layer_top());', host)
        run = (ROOT / 'tools/render/run.py').read_text()
        self.assertIn("run.failures += [f'ink: {fault}' for fault in ink]", run, 'a fault of the audit fails the round')
        # A text a card paints itself has no object: draw_text.h tells of it, in the host build alone.
        draw = (ROOT / 'components/smart_display/draw_text.h').read_text()
        self.assertRegex(draw, r'#ifdef USE_HOST\n\s*ink_audit::text\(area, layer->_clip_area, dsc\);')
        audit = (ROOT / 'components/smart_display/ink_audit.h').read_text()
        self.assertRegex(audit, r'(?s)#ifdef USE_HOST.*namespace ink_audit.*#endif\s*$', 'a screen carries none of the audit')


if __name__ == '__main__':
    unittest.main()
