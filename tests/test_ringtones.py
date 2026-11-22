"""A call's ringtone and the files a screen downloads (docs/CALLS.md "Ringtone", docs/SCREEN_FILES.md): ringtones.py and
screen_files.py whole, the /files/ path of the camera port, and the ring's `rt`. The screen's side, reading the WAV and
the link, is tests/test_wav.cpp; the editor's cut, filter and level is web/src/model/ringtone.test.ts.
"""
import io
import math
import re
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import calls  # noqa: E402
import picture_links  # noqa: E402
import ringtones  # noqa: E402
import screen_files  # noqa: E402

try:
    import aiohttp  # noqa: F401
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


def a_wav(seconds, rate=ringtones.RATE, channels=1, width=2):
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b'\x10\x00' * int(seconds * rate) * channels * (width // 2 or 1))
    return out.getvalue()


def read(data):
    with wave.open(io.BytesIO(data), 'rb') as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()


class Files(unittest.TestCase):
    def test_a_file_is_named_by_its_content_and_kept(self):
        folder = tempfile.mkdtemp()
        files = screen_files.ScreenFiles(folder)
        name = files.add(b'RIFF one', 'wav')
        self.assertTrue(re.fullmatch(r'[0-9a-f]{64}', name))
        self.assertEqual(files.add(b'RIFF one', 'wav'), name)
        self.assertEqual(files.link('http://10.0.0.2:8098', name), f'http://10.0.0.2:8098/files/{name}.wav')
        # After a restart, from the data folder; a file the app makes itself is not written there.
        made = files.add(b'RIFF made', 'wav', keep=False)
        again = screen_files.ScreenFiles(folder)
        self.assertEqual(again.get(name), (b'RIFF one', 'wav'))
        self.assertIsNone(again.get(made))
        self.assertEqual(sorted(p.name for p in (Path(folder) / 'files').iterdir()), [f'{name}.wav'])
        # The answer: the name is the ETag.
        status, body, etag, kind = again.serve(name)
        self.assertEqual((status, body, kind), (200, b'RIFF one', 'audio/wav'))
        self.assertEqual(again.serve(name, etag)[0], 304)
        self.assertEqual(again.serve('0' * 64)[0], 404)
        self.assertEqual(again.serve('../ringtones')[0], 404)
        again.remove(name)
        self.assertIsNone(again.get(name))
        with self.assertRaises(ValueError):
            files.add(b'x', 'exe')

    @unittest.skipUnless(HAS_AIOHTTP, 'needs aiohttp')
    def test_the_files_path_of_the_camera_port(self):
        import asyncio
        from aiohttp.test_utils import TestClient, TestServer
        files = screen_files.ScreenFiles(tempfile.mkdtemp())
        name = files.add(a_wav(0.5), 'wav')

        async def run():
            async with TestClient(TestServer(picture_links.web_app(picture_links.Links(), files=files))) as client:
                response = await client.get(f'/files/{name}.wav')
                body = await response.read()
                self.assertEqual((response.status, response.content_type, int(response.headers['Content-Length'])), (200, 'audio/wav', len(body)))
                self.assertEqual((await client.get(f'/files/{name}.wav', headers={'If-None-Match': response.headers['ETag']})).status, 304)
                self.assertEqual((await client.get(f'/files/{"0" * 64}.wav')).status, 404)
                self.assertEqual((await client.get('/files/short.wav')).status, 404)
                self.assertEqual((await client.post(f'/files/{name}.wav')).status, 405)
        asyncio.run(run())


class Tones(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.files = screen_files.ScreenFiles(self.folder)
        self.tones = ringtones.Ringtones(self.folder, self.files)

    def test_the_built_in_tones_are_what_a_screen_plays(self):
        self.assertEqual(list(ringtones.BUILT_IN), ['classic', 'marimba', 'digital', 'bell'])
        for key, name in self.tones.built.items():
            channels, width, rate, frames = read(self.files.get(name)[0])
            self.assertEqual((channels, width, rate), (1, 2, ringtones.RATE), key)
            self.assertLessEqual(frames, ringtones.MAX_SECONDS * rate, key)
            self.assertGreaterEqual(frames, ringtones.MIN_SECONDS * rate, key)
            # The same bytes at every start: a screen keeps a tone by its name.
            self.assertEqual(ringtones.Ringtones(tempfile.mkdtemp(), screen_files.ScreenFiles(tempfile.mkdtemp())).built[key], name, key)

    def test_classic_is_the_screens_own_ring(self):
        # module_call.cpp, make_ring: 1400 and 1900 Hz, a burst of 0.42 s, the second at 0.56 s, the next ring 3 s on.
        source = (ROOT / 'components/smart_display/module_call.cpp').read_text()
        self.assertIn('LENGTH = 1.1f, LOW = 1400.0f, HIGH = 1900.0f, BURST = 0.42f, GAP = 0.56f', source)
        self.assertIn('RING_EVERY_MS = 3000', source)
        with wave.open(io.BytesIO(self.files.get(self.tones.built['classic'])[0])) as w:
            self.assertEqual(w.getnframes(), 3 * ringtones.RATE)
            samples = w.readframes(w.getnframes())
        loud = [abs(int.from_bytes(samples[i:i + 2], 'little', signed=True)) for i in range(0, len(samples), 2)]
        rate = ringtones.RATE
        self.assertGreater(max(loud[:int(0.42 * rate)]), 20000)
        self.assertEqual(max(loud[int(0.43 * rate):int(0.55 * rate)]), 0)
        self.assertGreater(max(loud[int(0.57 * rate):int(0.98 * rate)]), 20000)
        self.assertEqual(max(loud[int(1.1 * rate):]), 0)

    def test_an_own_tone_is_checked_kept_and_chosen(self):
        tone = self.tones.add('  Our   bell ', a_wav(2.0))
        self.assertTrue(tone.startswith(ringtones.OWN))
        view = self.tones.view([{'id': 'kitchen', 'name': 'Kitchen'}])
        mine = next(t for t in view['tones'] if t['id'] == tone)
        self.assertEqual((mine['name'], mine['built_in']), ('Our bell', False))
        self.assertEqual((view['default'], view['screens']), ('classic', [{'id': 'kitchen', 'name': 'Kitchen', 'tone': ''}]))
        self.assertEqual(view['max_seconds'], ringtones.MAX_SECONDS)
        # Every screen, then one screen of its own, then that one back to every screen's.
        self.tones.choose('', tone)
        self.assertEqual(self.tones.tone_of('kitchen'), tone)
        self.tones.choose('kitchen', 'bell')
        self.assertEqual(self.tones.tone_of('kitchen'), 'bell')
        self.assertEqual(self.tones.tone_of('hall'), tone)
        self.tones.choose('kitchen', '')
        self.assertEqual(self.tones.tone_of('kitchen'), tone)
        self.assertEqual(self.tones.link('http://h:8098', 'kitchen'), f'http://h:8098/files/{self.tones.file_of(tone)}.wav')
        # Kept over a restart.
        again = ringtones.Ringtones(self.folder, screen_files.ScreenFiles(self.folder))
        self.assertEqual((again.default, again.wav(tone) is not None), (tone, True))
        # Gone: what rang with it rings with the classic tone, and its file goes.
        self.tones.choose('kitchen', tone)
        self.tones.remove(tone)
        self.assertEqual((self.tones.default, self.tones.tone_of('kitchen')), ('classic', 'classic'))
        self.assertEqual(list((Path(self.folder) / 'files').iterdir()), [])
        with self.assertRaises(ValueError):
            self.tones.remove('classic')
        with self.assertRaises(ValueError):
            self.tones.choose('', 'nothing')

    def test_what_is_no_ringtone(self):
        for data, why in ((a_wav(4.0), 'long'), (a_wav(0.1), 'short'), (a_wav(1.0, rate=44100), 'format'),
                          (a_wav(1.0, channels=2), 'format'), (b'not a wav', 'format')):
            with self.assertRaises(ValueError) as caught:
                self.tones.add('x', data)
            self.assertEqual(str(caught.exception), why)
        with self.assertRaises(ValueError) as caught:
            self.tones.add('   ', a_wav(1.0))
        self.assertEqual(str(caught.exception), 'name')
        for i in range(ringtones.MAX_OWN):
            self.tones.add(f'tone {i}', a_wav(0.5 + i / 100))
        with self.assertRaises(ValueError) as caught:
            self.tones.add('one more', a_wav(1.5))
        self.assertEqual(str(caught.exception), 'many')

    def test_a_screen_that_goes_forgets_its_choice(self):
        self.tones.choose('kitchen', 'bell')
        self.tones.forget_screen('kitchen')
        self.assertEqual(self.tones.screens, {})


class TheRing(unittest.TestCase):
    def test_rt_is_an_additive_field_of_the_ring(self):
        # calls.message makes no `rt`; server.call_send adds it to a ring only, so an older screen never sees it, and
        # page_receiver.cpp reads it for that state.
        say = calls.Say('kitchen', 'k1', calls.RING, 'hall', False)
        self.assertNotIn('rt', calls.message(say))
        server = (ROOT / 'screen_manager/app/server.py').read_text()
        self.assertIn("if out.state == calls.RING:", server)
        self.assertIn("message['rt'] = self.ringtones.link(base, mine['screen']['id'])", server)
        receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
        self.assertIn('string(root["rt"], 200)', receiver)

    def test_the_screen_takes_what_the_app_sends(self):
        # module_call.cpp: TONE_MOST holds the longest tone; the screen rings with its own when none comes.
        source = (ROOT / 'components/smart_display/module_call.cpp').read_text()
        most = int(re.search(r'TONE_MOST = (\d+) \* 1024', source).group(1)) * 1024
        self.assertGreater(most, ringtones.MAX_SECONDS * ringtones.RATE * 2 + 44)
        self.assertTrue(math.isclose(ringtones.MAX_SECONDS, 3.0))


if __name__ == '__main__':
    unittest.main()
