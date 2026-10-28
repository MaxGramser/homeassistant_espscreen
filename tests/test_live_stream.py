"""How a live camera travels to a screen (screen_manager/app/live_stream.py, docs/CAMERA.md "Live on the P4 boards"):
the pace a camera tile set to Live is sent, the links, the tiles' cameras a full view keeps running, and the stream
itself (a snapshot camera through a real aiohttp server, read the way the screen reads it). The WebRTC route needs aiortc
and a Home Assistant; it is proven on the bench (docs/CAMERA.md)."""
import asyncio
import io
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import camera_source  # noqa: E402
import live_stream  # noqa: E402
from PIL import Image  # noqa: E402


def jpeg(width, height, **options):
    out = io.BytesIO()
    Image.new('RGB', (width, height), (40, 120, 200)).save(out, 'JPEG', **options)
    return out.getvalue()


class LiveTiles(unittest.TestCase):

    def message(self, options, features):
        message = {'v': 1, 'op': 'state', 'i': 0, 'o': {'display': 'live'}}
        live_stream.live_pace(message, {'entity': 'camera.door', 'options': options}, features)
        return message['o'].get('refresh')

    def test_live_goes_only_to_a_screen_that_streams(self):
        streams, older = frozenset({'live', 'plugins'}), frozenset({'plugins'})
        # Live is the default where the screen streams, and what the tile says.
        self.assertEqual(self.message({'display': 'live'}, streams), 0)
        self.assertEqual(self.message({'display': 'live', 'refresh': 0}, streams), 0)
        # A screen that does not stream refreshes a Live tile at the pace every camera tile has by default.
        self.assertEqual(self.message({'display': 'live', 'refresh': 0}, older), live_stream.DEFAULT_PACE)
        self.assertIsNone(self.message({'display': 'live'}, older))
        # A pace of its own stays, everywhere; the editor's preview (no hello) runs the newest firmware.
        self.assertIsNone(self.message({'display': 'live', 'refresh': 10}, streams))
        self.assertEqual(self.message({'display': 'live'}, None), 0)
        # Only a camera's live picture: an image entity, a camera tile without a picture, are left alone.
        message = {'o': {}}
        live_stream.live_pace(message, {'entity': 'image.door', 'options': {'display': 'live'}}, streams)
        live_stream.live_pace(message, {'entity': 'camera.door', 'options': {}}, streams)
        self.assertEqual(message, {'o': {}})

    def test_a_tile_link_says_whether_its_picture_is_whole(self):
        feed = live_stream.LiveFeed(None, None, lambda e: True)
        token = feed.link('camera.door', (434, 244), cover=True)
        self.assertTrue(feed.links[token].cover)
        self.assertFalse(feed.links[feed.link('camera.door', (1280, 715))].cover)


class Held(unittest.TestCase):
    def test_a_full_view_keeps_the_cameras_of_its_screens_tiles_running(self):
        async def main():
            feed = live_stream.LiveFeed(None, None, lambda e: True)
            feed.link('camera.yard', (434, 244), cover=True, screen='a', tile=True)
            feed.link('camera.door', (240, 135), cover=True, screen='a', tile=True)
            feed.link('camera.shed', (434, 244), cover=True, screen='b', tile=True)
            for entity in ('camera.yard', 'camera.door', 'camera.shed'):
                feed.source(entity).task = asyncio.create_task(asyncio.sleep(5))
            # The full view of camera.door on screen a: its own camera runs anyway, and screen b's tiles are not its own.
            held = feed.hold(feed.links[feed.link('camera.door', (1280, 715), screen='a')])
            self.assertEqual([source.entity for source in held], ['camera.yard'])
            self.assertEqual(held[0].viewers, 1)
            # A tile holds nothing; a tile that streamed long ago is not held either.
            self.assertEqual(feed.hold(feed.links[feed.link('camera.door', (240, 135), screen='a', tile=True)]), [])
            for link in feed.links.values():
                link.used -= camera_source.LINGER_SECONDS
            self.assertEqual(feed.hold(feed.links[feed.link('camera.door', (1280, 715), screen='a')]), [])
            feed.let_go(held)
            self.assertEqual(held[0].viewers, 0)
            self.assertTrue(held[0].watched())  # and then the usual linger
            for source in feed.sources.values():
                source.task.cancel()

        asyncio.run(main())



class Stream(unittest.TestCase):
    """A snapshot camera through LiveFeed on a real socket, read like the screen reads it: HTTP/1.0, then parts."""

    def run_stream(self, entity='camera.door', parts=3, token=None, streams_open=0, rtc=None):
        """`rtc`: the camera has a stream, and this stands in for its WebRTC session (Source.rtc)."""
        from aiohttp import web
        picture = jpeg(512, 288)
        asked = []
        self.heads = []

        async def fetch(name):
            asked.append(name)
            await asyncio.sleep(0.01)
            return picture

        async def main():
            live = live_stream.LiveFeed(fetch, None, lambda name: rtc is not None)
            if rtc is not None:
                source = live.source(entity)
                source.rtc = lambda kinds, take, keep: rtc(source, take)

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
                    # A part's head in any order of its lines, as the screen reads it (picture_fetch::parse_head).
                    end = data.find(b'\r\n\r\n', data.find(b'--frame'))
                    length = re.search(rb'Content-Length: (\d+)\r\n', data[:end + 2]) if end >= 0 else None
                    if not length or len(data) < end + 4 + int(length.group(1)):
                        break
                    body = end + 4
                    self.heads.append(data[:body])
                    got.append(data[body:body + int(length.group(1))])
                    data = data[body + int(length.group(1)):]
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

    def test_every_picture_says_when_it_left(self):
        """X-Made: the app's clock in ms as a picture leaves, which the screen sets beside its own to see how long its
        pictures wait on the way (live_view.cpp)."""
        (_, got), _, _ = self.run_stream(parts=2)
        made = [re.search(rb'\r\nX-Made: (\d+)\r\n', head) for head in self.heads]
        self.assertTrue(len(got) == 2 and all(made), self.heads)
        self.assertLessEqual(int(made[0].group(1)), int(made[1].group(1)))

    def test_a_snapshot_camera_is_live_from_its_first_picture(self):
        self.run_stream()
        # No part is marked as a still: the screen shows no loader (live_view.h, "Until it is live").
        self.assertTrue(self.heads and not any(b'X-Picture' in head for head in self.heads), self.heads)

    def test_the_stills_before_webrtc_are_marked_and_its_frames_are_not(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')

        async def rtc(source, take):
            await asyncio.sleep(0.45)  # the camera's next key frame
            for _ in range(3):
                await take('video', av.VideoFrame.from_image(Image.new('RGB', (320, 180), (200, 80, 30))))
                await asyncio.sleep(0.05)
            await asyncio.sleep(5)
            return True
        before = camera_source.STILL_SECONDS
        camera_source.STILL_SECONDS = 0.1
        try:
            (_, got), _, asked = self.run_stream(parts=6, rtc=rtc)
        finally:
            camera_source.STILL_SECONDS = before
        marks = [b'X-Picture: still\r\n' in head for head in self.heads]
        # The stills first, each marked; then WebRTC's frames, none marked, and no still after them.
        self.assertTrue(marks[0], self.heads)
        self.assertFalse(marks[-1], self.heads)
        self.assertEqual(marks, sorted(marks, reverse=True), marks)
        # The mark is a line of the part's own head, before its length, as picture_fetch::parse_head reads it.
        self.assertRegex(self.heads[0], rb'--frame\r\nContent-Type: image/jpeg\r\nX-Picture: still\r\nContent-Length: \d+')

    def test_a_screens_fifth_live_tile_is_refused_by_its_own_count(self):
        """hw.h LIVE_TILES (docs/PLATFORM_PLAN.md 4.1): a screen's hello says how many live tiles it streams at once, and
        the app refuses the next tile stream of that screen, not another screen's and not its full view."""
        counts = {'a': 4, 'b': None}
        feed = live_stream.LiveFeed(None, None, lambda e: True, live_tiles=lambda screen: counts.get(screen))
        for camera in ('camera.one', 'camera.two', 'camera.three', 'camera.four'):
            feed.links[feed.link(camera, (434, 244), cover=True, screen='a', tile=True)].streaming = 1
        self.assertEqual(feed.tiles_streaming('a'), 4)
        self.assertEqual(feed.tiles_streaming('b'), 0)
        fifth = feed.link('camera.five', (434, 244), cover=True, screen='a', tile=True)
        answer = asyncio.run(feed.serve(None, fifth))  # refused before the request is read
        self.assertEqual(answer.status, 503)
        self.assertIn('4 cameras live at once', answer.text)
        # Another screen, a screen whose firmware did not say, and this screen's full view are not held to it.
        self.assertIsNone(feed.live_tiles('b'))
        for token in (feed.link('camera.six', (434, 244), cover=True, screen='b', tile=True),
                      feed.link('camera.one', (1280, 715), screen='a')):
            link = feed.links[token]
            cap = feed.live_tiles(link.screen) if link.tile and link.screen is not None else None
            self.assertTrue(cap is None or feed.tiles_streaming(link.screen) < cap)

    def test_a_full_view_goes_past_the_limit_while_its_own_tiles_still_stream(self):
        """A ring or a camera opened full screen covers the screen's live tiles, which end as it opens: at MAX_STREAMS
        it goes through when that screen's own tiles hold some of them, and is refused otherwise, as a tile is."""
        feed = live_stream.LiveFeed(None, None, lambda e: True)
        for i in range(live_stream.MAX_STREAMS):
            screen = 'guition' if i < 4 else 'd1001'
            feed.links[feed.link(f'camera.c{i}', (434, 244), cover=True, screen=screen, tile=True)].streaming = 1
        refused = (feed.link('camera.door', (946, 710), screen='kitchen'),
                   feed.link('camera.door', (434, 244), cover=True, screen='guition', tile=True),
                   feed.link('camera.door', (946, 710)))
        for token in refused:
            answer = asyncio.run(feed.serve(None, token))
            self.assertEqual(answer.status, 503)
        view = feed.links[feed.link('camera.door', (946, 710), screen='guition')]
        self.assertTrue(feed.streaming() >= live_stream.MAX_STREAMS and feed.tiles_streaming('guition'))
        self.assertFalse(view.tile or view.screen is None or not feed.tiles_streaming(view.screen), 'the ring of the Guition goes through')

    def test_an_unknown_link_and_too_many_streams_are_refused(self):
        (head, got), _, asked = self.run_stream(token='x' * 24, parts=1)
        self.assertEqual(got, [])
        self.assertIn(b'404', head)
        (head, got), _, asked = self.run_stream(parts=1, streams_open=live_stream.MAX_STREAMS)
        self.assertEqual(got, [])
        self.assertIn(b'503', head)
        self.assertEqual(asked, [])


if __name__ == '__main__':
    unittest.main()
