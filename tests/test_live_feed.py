"""A camera live on a P4 screen (screen_manager/app/live_feed.py, docs/CAMERA.md "Live on the P4 boards"): the room a
screen asks for, the size a frame goes out at, which JPEGs the P4's decoder takes as they are, and the stream itself
(a snapshot camera through a real aiohttp server, read the way the screen reads it). The WebRTC route needs aiortc and
a Home Assistant; it is proven on the bench (docs/CAMERA.md)."""
import asyncio
import io
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import live_feed  # noqa: E402
from PIL import Image  # noqa: E402


def jpeg(width, height, **options):
    out = io.BytesIO()
    Image.new('RGB', (width, height), (40, 120, 200)).save(out, 'JPEG', **options)
    return out.getvalue()


class Sizes(unittest.TestCase):
    def test_the_room_a_screen_asks_for(self):
        self.assertEqual(live_feed.parse_box('1280x728'), (1280, 728))
        self.assertEqual(live_feed.parse_box('800X1137'), (800, 1137))
        for bad in (None, '', '1280', 'x', '12x800', '1280x99999', 'axb', '1280x728x2'):
            self.assertIsNone(live_feed.parse_box(bad), bad)

    def test_a_frame_goes_out_at_its_own_size_when_it_fits(self):
        # A substream stays small: the screen's PPA scales it up, and Home Assistant's host does a fraction of the work.
        self.assertEqual(live_feed.size_for(512, 288, (1280, 728)), (512, 288))
        self.assertEqual(live_feed.size_for(1280, 720, (1280, 728)), (1280, 720))
        # A larger one is scaled down to the room, in whole JPEG blocks, its proportions kept.
        self.assertEqual(live_feed.size_for(1920, 1080, (1280, 715)), (1264, 704))
        self.assertEqual(live_feed.size_for(2560, 1440, (1280, 728)), (1280, 720))
        self.assertEqual(live_feed.size_for(1080, 1920, (1280, 728)), (400, 720))
        # Never beyond what the screen takes as it is.
        width, height = live_feed.size_for(3000, 2000, (4096, 4096))
        self.assertLessEqual(max(width, height), live_feed.MAX_SIDE)

    def test_the_jpegs_the_decoder_takes_as_they_are(self):
        self.assertEqual(live_feed.jpeg_size(jpeg(640, 360)), (640, 360))  # Pillow's default: baseline 4:2:0
        self.assertEqual(live_feed.jpeg_size(jpeg(640, 360, subsampling=0)), (640, 360))  # 4:4:4
        grey = io.BytesIO()
        Image.new('L', (320, 240), 90).save(grey, 'JPEG')
        self.assertEqual(live_feed.jpeg_size(grey.getvalue()), (320, 240))
        # Progressive, too large, sides whose product is not a multiple of eight, and anything that is no JPEG: remade.
        self.assertIsNone(live_feed.jpeg_size(jpeg(640, 360, progressive=True)))
        self.assertIsNone(live_feed.jpeg_size(jpeg(live_feed.MAX_SIDE + 16, 100)))
        self.assertIsNone(live_feed.jpeg_size(jpeg(9, 7)))
        png = io.BytesIO()
        Image.new('RGB', (64, 64)).save(png, 'PNG')
        self.assertIsNone(live_feed.jpeg_size(png.getvalue()))
        self.assertIsNone(live_feed.jpeg_size(b''))

    def test_what_the_decoder_does_not_take_is_remade_to_fit(self):
        for raw in (jpeg(640, 360, progressive=True), jpeg(3840, 2160)):
            made, ms = live_feed.remake(raw, (1280, 728))
            self.assertGreaterEqual(ms, 0)
            size = live_feed.jpeg_size(made)
            self.assertIsNotNone(size)
            self.assertLessEqual(size[0], 1280)
            self.assertLessEqual(size[1], 728)


class Stream(unittest.TestCase):
    """A snapshot camera through LiveFeed on a real socket, read like the screen reads it: HTTP/1.0, then parts."""

    def run_stream(self, entity='camera.door', parts=3, token=None, streams_open=0):
        from aiohttp import web
        picture = jpeg(512, 288)
        asked = []

        async def fetch(name):
            asked.append(name)
            await asyncio.sleep(0.01)
            return picture

        async def main():
            live = live_feed.LiveFeed(fetch, None, lambda name: False)
            async def stream(request):
                return await live.serve(request, request.match_info['token'])

            app = web.Application()
            app.router.add_get(r'/camera/{token:[A-Za-z0-9_-]{16,64}}.mjpeg', stream)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            link = token or live.link(entity, (1280, 728))
            for _ in range(streams_open):
                live.links[live.link(entity, (1280, 728))].streaming = 1
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.write(f'GET /camera/{link}.mjpeg HTTP/1.0\r\nHost: test\r\n\r\n'.encode())
            await writer.drain()
            data, got = b'', []
            while len(got) < parts:
                chunk = await asyncio.wait_for(reader.read(65536), 5)
                if not chunk:
                    break
                data += chunk
                while True:
                    found = re.search(rb'Content-Length: (\d+)\r\n\r\n', data)
                    if not found or len(data) < found.end() + int(found.group(1)):
                        break
                    got.append(data[found.end():found.end() + int(found.group(1))])
                    data = data[found.end() + int(found.group(1)):]
            writer.close()
            await asyncio.sleep(0.1)
            await runner.cleanup()
            return data, got

        return asyncio.run(main()), picture, asked

    def test_a_snapshot_camera_streams_its_jpegs_untouched(self):
        (head, got), picture, asked = self.run_stream()
        self.assertEqual(len(got), 3)
        # The P4 takes the camera's own JPEG as it is: this app spent nothing on it.
        self.assertTrue(all(part == picture for part in got))
        self.assertTrue(set(asked) == {'camera.door'})

    def test_an_unknown_link_and_too_many_streams_are_refused(self):
        (head, got), _, asked = self.run_stream(token='x' * 24, parts=1)
        self.assertEqual(got, [])
        self.assertIn(b'404', head)
        (head, got), _, asked = self.run_stream(parts=1, streams_open=live_feed.MAX_STREAMS)
        self.assertEqual(got, [])
        self.assertIn(b'503', head)
        self.assertEqual(asked, [])


class Encoder(unittest.TestCase):
    def test_frames_become_jpegs_the_decoder_takes(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')
        frame = av.VideoFrame.from_image(Image.new('RGB', (1920, 1080), (200, 80, 30)))
        encoder = live_feed.Encoder(*live_feed.size_for(1920, 1080, (1280, 728)))
        made, ms = encoder.encode(frame)
        self.assertEqual(live_feed.jpeg_size(made), (1280, 720))
        self.assertGreaterEqual(ms, 0)


class P4Build(unittest.TestCase):
    """The P4 boards build with the larger TCP window and the live view, keyed on the chip in the component."""

    def test_the_window_and_the_live_view_are_the_p4s_alone(self):
        source = (ROOT / 'components/smart_display/__init__.py').read_text()
        self.assertIn('"CONFIG_LWIP_TCP_WND_DEFAULT": 65534', source)
        self.assertRegex(source, r'if _esp32_p4\(\):\n\s+await _p4\(config\)')
        self.assertIn('return get_esp32_variant() == VARIANT_ESP32P4', source)
        self.assertIn('-Wl,--wrap=esp_lcd_new_panel_dpi', source)
        # A screen's own sdkconfig_options keep the last word.
        self.assertIn('if name not in own', source)


if __name__ == '__main__':
    unittest.main()
