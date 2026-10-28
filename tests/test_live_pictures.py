"""What a screen gets of a camera's frame (screen_manager/app/live_pictures.py, docs/CAMERA.md "Live on the P4 boards"):
the room a screen asks for, the size a frame goes out at (filling the room or covering a live tile's card), which JPEGs
the P4's decoder takes as they are, what is remade, and the JPEGs made of video frames."""
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import live_pictures  # noqa: E402
from PIL import Image  # noqa: E402


def jpeg(width, height, **options):
    out = io.BytesIO()
    Image.new('RGB', (width, height), (40, 120, 200)).save(out, 'JPEG', **options)
    return out.getvalue()


class Sizes(unittest.TestCase):
    def test_the_room_a_screen_asks_for(self):
        self.assertEqual(live_pictures.parse_box('1280x728'), (1280, 728))
        self.assertEqual(live_pictures.parse_box('800X1137'), (800, 1137))
        for bad in (None, '', '1280', 'x', '12x800', '1280x99999', 'axb', '1280x728x2'):
            self.assertIsNone(live_pictures.parse_box(bad), bad)

    def test_a_frame_goes_out_at_its_own_size_when_it_fits(self):
        # A substream stays small: the screen's PPA scales it up, and Home Assistant's host does a fraction of the work.
        self.assertEqual(live_pictures.size_for(512, 288, (1280, 728)), (512, 288))
        self.assertEqual(live_pictures.size_for(1280, 720, (1280, 728)), (1280, 720))
        # A larger one is scaled down to the room, in whole JPEG blocks, its proportions kept.
        self.assertEqual(live_pictures.size_for(1920, 1080, (1280, 715)), (1264, 704))
        self.assertEqual(live_pictures.size_for(2560, 1440, (1280, 728)), (1280, 720))
        self.assertEqual(live_pictures.size_for(1080, 1920, (1280, 728)), (400, 720))
        # Never beyond what the screen takes as it is.
        width, height = live_pictures.size_for(3000, 2000, (4096, 4096))
        self.assertLessEqual(max(width, height), live_pictures.MAX_SIDE)

    def test_the_jpegs_the_decoder_takes_as_they_are(self):
        self.assertEqual(live_pictures.jpeg_size(jpeg(640, 360)), (640, 360))  # Pillow's default: baseline 4:2:0
        self.assertEqual(live_pictures.jpeg_size(jpeg(640, 360, subsampling=0)), (640, 360))  # 4:4:4
        grey = io.BytesIO()
        Image.new('L', (320, 240), 90).save(grey, 'JPEG')
        self.assertEqual(live_pictures.jpeg_size(grey.getvalue()), (320, 240))
        # Progressive, too large, sides whose product is not a multiple of eight, and anything that is no JPEG: remade.
        self.assertIsNone(live_pictures.jpeg_size(jpeg(640, 360, progressive=True)))
        self.assertIsNone(live_pictures.jpeg_size(jpeg(live_pictures.MAX_SIDE + 16, 100)))
        self.assertIsNone(live_pictures.jpeg_size(jpeg(9, 7)))
        png = io.BytesIO()
        Image.new('RGB', (64, 64)).save(png, 'PNG')
        self.assertIsNone(live_pictures.jpeg_size(png.getvalue()))
        self.assertIsNone(live_pictures.jpeg_size(b''))

    def test_what_the_decoder_does_not_take_is_remade_to_fit(self):
        for raw in (jpeg(640, 360, progressive=True), jpeg(3840, 2160)):
            made, ms = live_pictures.remake(raw, (1280, 728))
            self.assertGreaterEqual(ms, 0)
            size = live_pictures.jpeg_size(made)
            self.assertIsNotNone(size)
            self.assertLessEqual(size[0], 1280)
            self.assertLessEqual(size[1], 728)

    def test_a_tile_that_fills_its_card_gets_as_little_as_covers_it(self):
        self.assertEqual(live_pictures.size_to_cover(1920, 1080, (434, 244)), (440, 248))
        self.assertEqual(live_pictures.size_to_cover(1920, 1080, (434, 434)), (776, 440))
        # Smaller than the card: as it is (to the multiple of 8 below), the screen scales it up.
        self.assertEqual(live_pictures.size_to_cover(512, 288, (868, 488)), (512, 288))
        self.assertEqual(live_pictures.size_to_cover(511, 287, (868, 488)), (504, 280))

    def test_a_covering_picture_is_one_the_decoder_takes(self):
        # The Guition 10.1's right-hand tiles (2026-10-27): 494 x 278 was refused, width times height not a multiple of 8.
        self.assertEqual(live_pictures.size_to_cover(1920, 1080, (494, 277)), (496, 280))
        self.assertEqual(live_pictures.size_to_cover(1920, 1080, (495, 277)), (496, 280))
        for frame in ((1920, 1080), (1280, 720), (640, 360), (512, 288), (511, 287)):
            for bw in range(200, 700, 7):
                for bh in range(100, 500, 9):
                    w, h = live_pictures.size_to_cover(*frame, (bw, bh))
                    self.assertEqual(w * h % 8, 0, (frame, bw, bh, w, h))
                    self.assertLessEqual(w, frame[0]); self.assertLessEqual(h, frame[1])
                    if frame[0] > bw and frame[1] > bh:
                        self.assertTrue(w >= bw - 7 or h >= bh - 7, (frame, bw, bh, w, h))


class Encoder(unittest.TestCase):
    def test_frames_become_jpegs_the_decoder_takes(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')
        frame = av.VideoFrame.from_image(Image.new('RGB', (1920, 1080), (200, 80, 30)))
        encoder = live_pictures.Encoder(*live_pictures.size_for(1920, 1080, (1280, 728)))
        made, ms = encoder.encode(frame)
        self.assertEqual(live_pictures.jpeg_size(made), (1280, 720))
        self.assertGreaterEqual(ms, 0)


if __name__ == '__main__':
    unittest.main()
