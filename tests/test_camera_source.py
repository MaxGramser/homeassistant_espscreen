"""What a camera gives (screen_manager/app/camera_source.py, docs/CAMERA.md "Live on the P4 boards"): a camera with a
stream until WebRTC's first frame, its stills first, and an offer Home Assistant refuses giving way to the snapshots."""
import asyncio
import contextlib
import importlib.util
import io
from pathlib import Path
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


class Picture:
    """A decoded frame as the watch reads it: its timestamp, the decoder's corrupt and key flags, and its brightness."""

    def __init__(self, pts, y=100.0, corrupt=False, key=False):
        self.pts, self.y, self.is_corrupt, self.key_frame = pts, y, corrupt, key


class FrameWatch(unittest.TestCase):
    """Every decoded WebRTC frame before a screen gets it (camera_source.FrameWatch): corrupt ones left out, gaps in the
    timestamps and flash frames counted, and one line every FRAME_REPORT_SECONDS when anything was."""

    def watch(self):
        self.now = [0.0]
        return camera_source.FrameWatch('camera.porch', clock=lambda: self.now[0], brightness=lambda frame: frame.y)

    def test_a_steady_stream_shows_every_frame_and_says_nothing(self):
        watch = self.watch()
        self.assertTrue(all(watch.feed(Picture(i * 6000, y=100 + (i % 3))) for i in range(30)))
        self.now[0] = camera_source.FRAME_REPORT_SECONDS
        self.assertIsNone(watch.line(), 'quiet while only frames came')
        self.assertEqual((watch.total['frames'], watch.total['gaps'], watch.total['flashes']), (30, 0, 0))

    def test_a_corrupt_frame_is_left_out_and_counted(self):
        watch = self.watch()
        self.assertTrue(watch.feed(Picture(0)))
        with self.assertLogs(camera_source.LOG, 'INFO'):
            self.assertFalse(watch.feed(Picture(6000, corrupt=True)))
        self.assertTrue(watch.feed(Picture(12000)))
        self.now[0] = camera_source.FRAME_REPORT_SECONDS
        self.assertIn('1 corrupt', watch.line())

    def test_a_flash_is_a_bright_frame_or_a_second_of_them_that_falls_back(self):
        watch = self.watch()
        for i, y in enumerate((80, 80, 80, 130, 81, 80)):
            if y == 81:
                with self.assertLogs(camera_source.LOG, 'WARNING') as said:
                    watch.feed(Picture(i * 6000, y=y))
                self.assertIn('flash at pts 18000, 1 frame(s)', said.output[0])
            else:
                watch.feed(Picture(i * 6000, y=y))
        self.assertEqual(watch.total['flashes'], 1)
        # Half a second of a brighter picture, as a camera's exposure jumps, then back.
        longer = self.watch()
        with self.assertLogs(camera_source.LOG, 'WARNING') as said:
            for i, y in enumerate((70, 72, 71, 70, 110, 140, 150, 140, 120, 100, 80, 72, 71)):
                longer.feed(Picture(i * 6000, y=y))
        self.assertEqual(longer.total['flashes'], 1)
        self.assertIn('5 frame(s): brightness 71, up to 150, then 100', said.output[0])
        # A light that goes on and stays on is no flash; nor is a small step on a dark picture.
        steady = self.watch()
        for i, y in enumerate([80] * 5 + [130] * 30 + [20, 20, 20, 26, 20]):
            steady.feed(Picture(i * 6000, y=y))
        self.assertEqual(steady.total['flashes'], 0)

    def test_missing_frames_are_counted_from_the_usual_step(self):
        watch = self.watch()
        for i in range(10):
            watch.feed(Picture(i * 6000))
        watch.feed(Picture(9 * 6000 + 3 * 6000))  # two frames never came
        watch.feed(Picture(13 * 6000))
        self.assertEqual(watch.total['gaps'], 2)
        self.assertTrue(watch.feed(Picture(None)), 'a frame without a timestamp is shown and not measured')

    def test_the_line_has_the_transport_and_the_jpegs_and_the_totals_come_anyway(self):
        watch = self.watch()
        watch.feed(Picture(0, key=True))
        self.assertIsNone(watch.line(lost=3), 'not before its time')
        self.now[0] = camera_source.FRAME_REPORT_SECONDS
        told = watch.line(lost=5, nacks=4, plis=1, refused=2, stills=1)
        self.assertIn('1 frames (1 key)', told)
        self.assertIn('5 packets lost, 4 NACKs and 1 PLIs sent; 2 JPEGs the screen would refuse, 1 stills', told)
        self.assertNotIn('not turned', told)
        self.now[0] += camera_source.FRAME_REPORT_SECONDS
        self.assertIsNone(watch.line(lost=5, nacks=4, plis=1, refused=2, stills=1), 'nothing new: quiet')
        # Pictures for a turned glass that went upright (live_pictures.not_turned) are said when there are any.
        self.now[0] += camera_source.FRAME_REPORT_SECONDS
        told = watch.line(lost=5, nacks=4, plis=1, refused=2, stills=1, not_turned=3)
        self.assertIn('0 stills, 3 pictures not turned for a turned glass in', told)
        self.now[0] = camera_source.FRAME_TOTALS_SECONDS
        self.assertIn('since the stream began', watch.line(lost=5))

    def test_the_brightness_of_a_real_frame(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')
        dark = av.VideoFrame.from_image(Image.new('RGB', (1280, 720), (20, 20, 20)))
        bright = av.VideoFrame.from_image(Image.new('RGB', (1280, 720), (240, 240, 240)))
        self.assertLess(camera_source.luma(dark), 40)
        self.assertGreater(camera_source.luma(bright), 200)


class FrameDump(unittest.TestCase):
    """The evidence of a flagged frame: it, the two before it and the two after it as JPEGs, at most DUMP_MOST in all."""

    def test_a_flash_keeps_five_frames_and_the_oldest_go(self):
        try:
            import av
        except ImportError:
            self.skipTest('PyAV is not installed here (the add-on image has it)')
        import tempfile

        def frame(pts, grey):
            made = av.VideoFrame.from_image(Image.new('RGB', (64, 36), (grey, grey, grey)))
            made.pts = pts
            return made

        async def run(folder):
            dump = camera_source.FrameDump('camera.porch', folder=folder, most=6)
            watch = camera_source.FrameWatch('camera.porch', dump=dump)
            for i, grey in enumerate((60, 60, 60, 220, 60, 60, 60, 60)):
                watch.feed(frame(i, grey))
            # A frame of 1080p is kept small.
            self.assertEqual(dump.recent[-1].width, min(camera_source.FrameDump.THUMB_WIDTH, 64))
            await asyncio.sleep(0.5)  # the JPEGs are written in a thread
            return watch

        with tempfile.TemporaryDirectory() as folder, self.assertLogs(camera_source.LOG, 'WARNING'):
            watch = asyncio.run(run(folder))
            written = sorted(int(path.stem) for path in Path(folder).glob('camera_porch/*.jpg'))
        self.assertEqual(watch.total['flashes'], 1)
        self.assertEqual(written, [1, 2, 3, 4, 5, 6], 'the flash at 3, the two before, the frame it fell back on and two after')

    def test_aiortcs_receiver_has_the_two_senders_the_watch_counts(self):
        try:
            from aiortc import RTCRtpReceiver
        except ImportError:
            self.skipTest('aiortc is not installed here (the add-on image has it)')
        self.assertTrue(hasattr(RTCRtpReceiver, '_send_rtcp_nack') and hasattr(RTCRtpReceiver, '_send_rtcp_pli'))


class Lag(unittest.TestCase):
    """How far a camera's pictures come behind the camera (camera_source.Lag): this host's clock against the frames'."""

    def test_pictures_that_keep_up_are_not_behind_and_a_backlog_is(self):
        now = [100.0]
        lag = camera_source.Lag(clock=lambda: now[0])
        for i in range(10):  # 10 a second, as the camera makes them
            now[0] = 100.0 + i / 10
            self.assertAlmostEqual(lag.feed(i / 10), 0.0)
        now[0] += 2.0  # the app was busy: the frames of the second after come at once, two seconds late
        for i in range(10, 20):
            self.assertGreater(lag.feed(i / 10), 0.9)
        self.assertAlmostEqual(lag.feed(1.95), (now[0] - 100.0) - 1.95)

    def test_a_jump_of_the_cameras_clock_starts_the_count_again(self):
        now = [0.0]
        lag = camera_source.Lag(clock=lambda: now[0])
        lag.feed(0.0)
        now[0] = 1.0
        self.assertEqual(lag.feed(50.0), 0.0)  # timestamps leapt ahead (a new key frame): the new origin
        now[0] = 1.5
        self.assertAlmostEqual(lag.feed(50.5), 0.0)

    def test_it_reports_once_a_minute_with_the_average_and_the_most(self):
        now = [0.0]
        lag = camera_source.Lag(clock=lambda: now[0])
        lag.feed(0.0)
        now[0] = 2.0
        lag.feed(1.0)  # one second behind
        self.assertIsNone(lag.report())
        now[0] = camera_source.LAG_REPORT_SECONDS
        average, most, pictures = lag.report()
        self.assertEqual(pictures, 2)
        self.assertAlmostEqual(most, 1.0)
        self.assertAlmostEqual(average, 0.5)
        self.assertIsNone(lag.report())  # nothing new since


class WaitForWebRTC(unittest.TestCase):
    """A camera with a stream until WebRTC's first frame: its stills keep the screen's stream going (the screen closes one
    silent for 6 s, live_view::QUIET_MS), and an offer Home Assistant refuses gives way to the snapshots at once."""

    def test_the_still_comes_again_until_the_first_frame(self):
        async def main():
            stills = []

            async def fetch(entity):
                stills.append(entity)
                return jpeg(64, 36)

            source = camera_source.Source(live_stream.LiveFeed(fetch, None, lambda e: True), 'camera.door', True)
            source.viewers = 1

            async def rtc(kinds, take, keep, quiet=False):
                await asyncio.sleep(0.35)  # a camera's key frame that takes its time
                await take('video', object())
                return True
            source.rtc = rtc
            before = camera_source.STILL_SECONDS
            camera_source.STILL_SECONDS = 0.1
            try:
                self.assertTrue(await source.webrtc())
                came = len(stills)
                await asyncio.sleep(0.3)
            finally:
                camera_source.STILL_SECONDS = before
            # A still every STILL_SECONDS while WebRTC waited, the first at once; none once its frame came.
            self.assertGreaterEqual(came, 3)
            self.assertEqual(len(stills), came)
            self.assertIsNotNone(source.frame.video)

        asyncio.run(main())

    def test_a_camera_on_its_snapshots_tries_webrtc_again_and_says_once_that_it_works(self):
        """A camera whose WebRTC gave no frame (its privacy mode, a go2rtc that was away) sends its snapshots and tries
        WebRTC again every WEBRTC_RETRY_SECONDS while it is watched, its snapshots going on meanwhile; only the first
        failure is in the log, and one line says when it works again."""
        async def main():
            fetched, quiet_asked = [], []

            async def fetch(entity):
                fetched.append(asyncio.get_running_loop().time())
                return jpeg(64, 36)

            source = camera_source.Source(live_stream.LiveFeed(fetch, None, lambda e: True), 'camera.door', True)
            source.viewers = 1

            async def rtc(kinds, take, keep, quiet=False):
                quiet_asked.append(quiet)
                await asyncio.sleep(0.1)
                if len(quiet_asked) < 3:
                    return False
                await take('video', object())
                return True
            source.rtc = rtc
            saved = camera_source.WEBRTC_RETRY_SECONDS, camera_source.webrtc_here
            camera_source.WEBRTC_RETRY_SECONDS, camera_source.webrtc_here = 0.3, lambda: True
            try:
                with self.assertLogs('camera_source', 'INFO') as logged:
                    await source.run()
            finally:
                camera_source.WEBRTC_RETRY_SECONDS, camera_source.webrtc_here = saved
            return fetched, quiet_asked, logged.output, source

        fetched, quiet_asked, output, source = asyncio.run(main())
        self.assertEqual(quiet_asked, [False, True, True])
        works = [line for line in output if 'WebRTC works again' in line]
        self.assertEqual(len(works), 1, output)
        self.assertIn('Live camera.door: WebRTC works again at try 3, after', works[0])
        # Snapshots between the tries and during the last one, at the snapshots' pace, not a still every 2 s.
        self.assertGreater(len(fetched), 10)
        self.assertIsNotNone(source.frame.video)

    def test_the_sounds_own_session_ends_when_the_pictures_bring_the_sound(self):
        """A tile first (pictures without sound), then the full view with sound: the listener's own sound session goes,
        so the sound comes once, not twice shifted (2026-10-29); it comes back when the pictures' session ends."""
        async def main():
            source = camera_source.Source(live_stream.LiveFeed(lambda e: None, None, lambda e: True), 'camera.door', True)
            source.viewers = 1
            sessions = []

            async def rtc(kinds, take, keep, quiet=False):
                sessions.append(kinds)
                if 'video' in kinds:
                    await take('video', object())
                    await asyncio.sleep(0.2)
                    return True
                await asyncio.sleep(10)  # the sound's own session, until it is cancelled
                return True
            source.rtc = rtc
            source.listen(asyncio.Queue(maxsize=4))
            await asyncio.sleep(0.05)
            self.assertEqual(sessions, [('audio',)])
            own = source.sound
            source.wants_sound = True
            self.assertTrue(await source.webrtc())
            self.assertTrue(own.cancelled() or own.done())
            self.assertEqual(sessions[1], ('video', 'audio'))
            await asyncio.sleep(0.05)
            # The pictures' session ended with a listener still there: the sound's own session again.
            self.assertEqual(sessions[2], ('audio',))
            source.sound.cancel()

        asyncio.run(main())

    @unittest.skipUnless(importlib.util.find_spec('aiortc'), 'needs aiortc (the app has it)')
    def test_a_refused_offer_gives_way_at_once(self):
        class Message:
            def json(self):
                return {'id': 1, 'type': 'result', 'success': False,
                        'error': {'message': 'Camera does not support WebRTC'}}

        sent = []

        class Socket:
            async def send_json(self, data):
                sent.append(asyncio.get_running_loop().time())

            def __aiter__(self):
                async def messages():
                    yield Message()
                    await asyncio.sleep(60)
                return messages()

        @contextlib.asynccontextmanager
        async def websocket():
            yield Socket()

        async def main():
            source = camera_source.Source(live_stream.LiveFeed(None, websocket, lambda e: True), 'camera.door', True)
            started = asyncio.get_running_loop().time()
            with self.assertLogs('camera_source', 'INFO') as logged:
                gave = await source.rtc(('video',), None, lambda: True)
            done = asyncio.get_running_loop().time()
            return gave, sent[0] - started, done - sent[0], logged.output

        gave, offering, refused, output = asyncio.run(main())
        self.assertFalse(gave)
        # The offer goes out at once (no STUN server to wait for, about five seconds before), and the refusal ends the
        # session at once, not after WEBRTC_FIRST_SECONDS.
        self.assertLess(offering, 1.5)
        self.assertLess(refused, 1.5)
        self.assertTrue(any('Camera does not support WebRTC' in line for line in output), output)


if __name__ == '__main__':
    unittest.main()
