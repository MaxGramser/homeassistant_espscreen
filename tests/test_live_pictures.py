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


def on_panel(x, y, w, h, turn, pw, ph):
    """glass::on_panel (components/smart_display/glass.h) of a rectangle, as the firmware turns one: x, y, w, h."""
    return {90: (pw - y - h, x, h, w), 180: (pw - x - w, ph - y - h, w, h), 270: (y, ph - x - w, h, w)}.get(turn, (x, y, w, h))


class Turned(unittest.TestCase):
    """Live pictures for a screen whose glass is turned (caps picture_turn): turned so that the screen copies them onto
    its glass straight. Each pixel of a tile's card lands where the firmware's glass::on_panel puts it, with the card as
    the panel."""

    def card(self, width, height):
        # Four colours in the four quarters, so a turn shows where each went.
        image = Image.new('RGB', (width, height))
        for (x, y), colour in {(0, 0): (255, 0, 0), (1, 0): (0, 255, 0), (0, 1): (0, 0, 255), (1, 1): (255, 255, 255)}.items():
            image.paste(colour, (x * width // 2, y * height // 2, (x + 1) * width // 2, (y + 1) * height // 2))
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=95)
        return out.getvalue(), image

    def test_each_pixel_lands_where_the_glass_puts_it(self):
        raw, upright = self.card(496, 280)
        for turn in live_pictures.TURNS:
            made, _ = live_pictures.remake(raw, (496, 280), cover=True, turn=turn)
            self.assertEqual(live_pictures.jpeg_size(made), live_pictures.turned((496, 280), turn))
            picture = Image.open(io.BytesIO(made)).convert('RGB')
            pw, ph = picture.size
            for x, y in ((40, 30), (450, 30), (40, 250), (450, 250), (200, 100)):
                gx, gy, _, _ = on_panel(x, y, 1, 1, turn, pw, ph)
                want, got = upright.getpixel((x, y)), picture.getpixel((gx, gy))
                self.assertTrue(all(abs(a - b) < 40 for a, b in zip(want, got)), (turn, (x, y), want, got))

    def test_the_size_turns_and_stays_one_the_decoder_takes(self):
        self.assertEqual(live_pictures.turned((496, 280), 90), (280, 496))
        self.assertEqual(live_pictures.turned((496, 280), 180), (496, 280))
        self.assertEqual(live_pictures.turned((496, 280), 270), (280, 496))
        self.assertEqual(live_pictures.turned((496, 280), 0), (496, 280))
        self.assertEqual(live_pictures.turned((496, 280), 45), (496, 280))  # no turn the glass has

    def test_an_upright_glass_changes_nothing(self):
        raw = jpeg(496, 280)
        self.assertEqual(live_pictures.remake(raw, (496, 280), cover=True)[0], live_pictures.remake(raw, (496, 280), True, 0)[0])

    def test_a_camera_jpeg_that_fits_is_turned_too(self):
        # Untouched on an upright glass; on a turned one remade turned, though the decoder would take it as it is.
        import asyncio
        frame = type('Frame', (), {'jpeg': jpeg(496, 280), 'video': None, 'number': 1, 'still': False})()
        pictures = live_pictures.Pictures()
        upright, turn = asyncio.run(pictures.picture(frame, (496, 280), True))
        self.assertEqual(turn, 0)
        self.assertIs(upright, frame.jpeg)
        turned, turn = asyncio.run(pictures.picture(frame, (496, 280), True, 270))
        self.assertEqual((live_pictures.jpeg_size(turned), turn), ((280, 496), 270))
        # Made once per frame, room and turn.
        self.assertEqual(asyncio.run(pictures.picture(frame, (496, 280), True, 270)), (turned, 270))
        self.assertEqual(pictures.made, 2)

    def test_a_picture_that_cannot_be_turned_goes_upright_and_is_counted(self):
        # Whatever fails in turning (here Pillow's transpose), the screen gets the picture upright with turn 0, which it
        # turns itself, and never goes without one; the camera's count says it (camera_source's frame watch).
        import asyncio
        from unittest import mock
        frame = type('Frame', (), {'jpeg': jpeg(496, 280), 'video': None, 'number': 1, 'still': False})()
        pictures = live_pictures.Pictures('camera.door')
        live_pictures.not_turned.pop('camera.door', None)
        with mock.patch.object(live_pictures, 'turn_image', side_effect=ValueError('no such filter')):
            with self.assertLogs(live_pictures.LOG, 'WARNING') as told:
                made, turn = asyncio.run(pictures.picture(frame, (496, 280), True, 270))
            frame.number = 2
            asyncio.run(pictures.picture(frame, (496, 280), True, 270))
        self.assertEqual((made, turn), (frame.jpeg, 0))
        self.assertEqual(live_pictures.not_turned['camera.door'], 2)
        self.assertEqual(len(told.output), 1, 'said once')
        # An upright picture that fails fails as before: nothing to fall back on.
        with mock.patch.object(live_pictures, 'remake', side_effect=OSError('broken')):
            with self.assertRaises(OSError):
                asyncio.run(pictures.picture(type(frame)(), (100, 100), True))


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

    def test_a_turned_glass_gets_its_frames_turned(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')
        upright = Image.new('RGB', (496, 280), (0, 0, 255))
        upright.paste((255, 0, 0), (0, 0, 248, 140))  # the top left quarter red
        for turn in live_pictures.TURNS:
            encoder = live_pictures.Encoder(496, 280, turn=turn)
            for _ in range(2):  # the filters keep their state from frame to frame
                made, _ = encoder.encode(av.VideoFrame.from_image(upright))
            picture = Image.open(io.BytesIO(made)).convert('RGB')
            self.assertEqual(picture.size, live_pictures.turned((496, 280), turn))
            gx, gy, _, _ = on_panel(60, 40, 1, 1, turn, *picture.size)
            self.assertGreater(picture.getpixel((gx, gy))[0], 200, turn)


if __name__ == '__main__':
    unittest.main()
