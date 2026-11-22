"""The sounds a screen plays and the files it downloads (docs/SOUNDS.md, docs/SCREEN_FILES.md): sounds.py and
screen_files.py whole, the /files/ path of the camera port, a ring's `rt`, a doorbell's `ch` and the op `sound`. The
screen's side, reading the WAV and the link, is tests/test_wav.cpp; the editor's cut, filter and level is
web/tests/ringtone.spec.ts.
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
import sounds  # noqa: E402
import screen_files  # noqa: E402

try:
    import aiohttp  # noqa: F401
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


def a_wav(seconds, rate=sounds.RATE, channels=1, width=2):
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


class Library(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.files = screen_files.ScreenFiles(self.folder)
        self.sounds = sounds.Sounds(self.folder, self.files)

    def test_the_built_in_sounds_are_what_a_screen_plays(self):
        self.assertEqual(list(sounds.BUILT_IN), ['classic', 'marimba', 'digital', 'bell', 'chime', 'notice'])
        for key, name in self.sounds.built.items():
            channels, width, rate, frames = read(self.files.get(name)[0])
            self.assertEqual((channels, width, rate), (1, 2, sounds.RATE), key)
            self.assertGreaterEqual(frames, sounds.MIN_SECONDS * rate, key)
            # And is heard, without driving the speaker into distortion: the levelled ones at LEVEL, the chime its own.
            self.assertGreater(max(self.samples(key)), 0.25 * 32767, key)
            self.assertLessEqual(max(self.samples(key)), sounds.LEVEL * 32767 + 1, key)
            # Every built-in sound fits every kind, and comes out the same at every start: a screen keeps it by its name.
            self.assertLessEqual(frames, min(k['max_seconds'] for k in sounds.KINDS.values()) * rate, key)
            self.assertEqual(sounds.Sounds(tempfile.mkdtemp(), screen_files.ScreenFiles(tempfile.mkdtemp())).built[key], name, key)

    def test_nothing_changes_by_itself(self):
        # A call rings Classic, a doorbell chimes Ding-dong, an alert stays silent.
        self.assertEqual({kind: self.sounds.sound_of(kind, 'kitchen') for kind in sounds.KINDS},
                         {'call': 'classic', 'doorbell': 'chime', 'alert': sounds.NONE})
        self.assertEqual(self.sounds.link('alert', 'http://h:8098', 'kitchen'), sounds.NONE)

    def test_classic_is_the_screens_own_ring(self):
        # module_call.cpp, make_ring: 1400 and 1900 Hz, a burst of 0.42 s, the second at 0.56 s, the next ring 3 s on.
        source = (ROOT / 'components/smart_display/module_call.cpp').read_text()
        self.assertIn('LENGTH = 1.1f, LOW = 1400.0f, HIGH = 1900.0f, BURST = 0.42f, GAP = 0.56f', source)
        self.assertIn('RING_EVERY_MS = 3000', source)
        loud = self.samples('classic')
        rate = sounds.RATE
        self.assertEqual(len(loud), 3 * rate)
        self.assertGreater(max(loud[:int(0.42 * rate)]), 0.45 * 32767)
        self.assertEqual(max(loud[int(0.43 * rate):int(0.55 * rate)]), 0)
        self.assertGreater(max(loud[int(0.57 * rate):int(0.98 * rate)]), 0.45 * 32767)
        self.assertEqual(max(loud[int(1.1 * rate):]), 0)

    def test_chime_is_the_screens_own_ding_dong(self):
        # module_doorbell.cpp, make_chime: E5 then C5 0.55 s later over 1.9 s, at a third of full scale, not levelled.
        source = (ROOT / 'components/smart_display/module_doorbell.cpp').read_text()
        self.assertIn('LENGTH = 1.9f, SECOND = 0.55f, DECAY = 0.42f, ATTACK = 0.006f', source)
        self.assertIn('NOTES[2] = {659.25f, 523.25f}', source)
        self.assertIn('sum * 0.33f', source)
        loud = self.samples('chime')
        self.assertEqual(len(loud), int(1.9 * sounds.RATE))
        self.assertLess(max(loud), 0.6 * 32767)

    def samples(self, sound):
        with wave.open(io.BytesIO(self.sounds.wav(sound))) as w:
            data = w.readframes(w.getnframes())
        return [abs(int.from_bytes(data[i:i + 2], 'little', signed=True)) for i in range(0, len(data), 2)]

    def test_an_own_sound_is_checked_kept_and_chosen_per_kind(self):
        sound = self.sounds.add('  Our   bell ', a_wav(2.0))
        self.assertTrue(sound.startswith(sounds.OWN))
        view = self.sounds.view({'call': [{'id': 'kitchen', 'name': 'Kitchen'}]})
        mine = next(t for t in view['sounds'] if t['id'] == sound)
        self.assertEqual((mine['name'], mine['built_in'], mine['seconds']), ('Our bell', False, 2.0))
        self.assertEqual(view['kinds']['call']['screens'], [{'id': 'kitchen', 'name': 'Kitchen', 'sound': ''}])
        self.assertEqual(view['kinds']['doorbell']['screens'], [])
        self.assertEqual({kind: v['max_seconds'] for kind, v in view['kinds'].items()}, {'call': 3.0, 'doorbell': 5.0, 'alert': 3.0})
        # Every screen, then one screen of its own, then that one back to every screen's; each kind on its own.
        self.sounds.choose('call', '', sound)
        self.sounds.choose('alert', 'kitchen', 'notice')
        self.assertEqual((self.sounds.sound_of('call', 'kitchen'), self.sounds.sound_of('alert', 'kitchen'), self.sounds.sound_of('alert', 'hall')),
                         (sound, 'notice', sounds.NONE))
        self.sounds.choose('call', 'kitchen', 'bell')
        self.assertEqual(self.sounds.sound_of('call', 'kitchen'), 'bell')
        self.sounds.choose('call', 'kitchen', '')
        self.assertEqual(self.sounds.sound_of('call', 'kitchen'), sound)
        self.assertEqual(self.sounds.link('call', 'http://h:8098', 'kitchen'), f'http://h:8098/files/{self.sounds.at_volume(self.sounds.file_of(sound), sounds.VOLUME)}.wav')
        self.sounds.choose('doorbell', '', sounds.NONE)
        self.assertEqual(self.sounds.link('doorbell', 'http://h:8098', 'kitchen'), sounds.NONE)
        # Kept over a restart.
        again = sounds.Sounds(self.folder, screen_files.ScreenFiles(self.folder))
        self.assertEqual((again.sound_of('call', 'hall'), again.sound_of('doorbell', 'hall'), again.wav(sound) is not None), (sound, sounds.NONE, True))
        # Gone: what played it plays its kind's own sound again, and its file goes.
        self.sounds.choose('alert', '', sound)
        self.sounds.remove(sound)
        self.assertEqual((self.sounds.sound_of('call', 'kitchen'), self.sounds.sound_of('alert', 'hall')), ('classic', sounds.NONE))
        self.assertEqual(list((Path(self.folder) / 'files').iterdir()), [])
        with self.assertRaises(ValueError):
            self.sounds.remove('classic')
        with self.assertRaises(ValueError):
            self.sounds.choose('call', '', 'nothing')
        with self.assertRaises(ValueError):
            self.sounds.choose('siren', '', 'classic')

    def test_a_sound_longer_than_a_kind_allows_is_not_offered_for_it(self):
        long = self.sounds.add('Westminster', a_wav(4.5))
        self.sounds.choose('doorbell', '', long)
        for kind in ('call', 'alert'):
            with self.assertRaises(ValueError):
                self.sounds.choose(kind, '', long)

    def test_what_is_no_sound(self):
        for data, why in ((a_wav(5.5), 'long'), (a_wav(0.1), 'short'), (a_wav(1.0, rate=44100), 'format'),
                          (a_wav(1.0, channels=2), 'format'), (b'not a wav', 'format')):
            with self.assertRaises(ValueError) as caught:
                self.sounds.add('x', data)
            self.assertEqual(str(caught.exception), why)
        with self.assertRaises(ValueError) as caught:
            self.sounds.add('   ', a_wav(1.0))
        self.assertEqual(str(caught.exception), 'name')
        for i in range(sounds.MAX_OWN):
            self.sounds.add(f'sound {i}', a_wav(0.5 + i / 100))
        with self.assertRaises(ValueError) as caught:
            self.sounds.add('one more', a_wav(1.5))
        self.assertEqual(str(caught.exception), 'many')

    def test_a_screen_plays_each_kind_at_its_volume(self):
        # -20 dB unless someone moves the slider: the file a screen gets has its loudest sample there (the owner chose
        # -20 dB of -10, -14 and -20 on the Guition 10.1, 2026-11-22).
        # The doorbell's chime starts as loud as the screen's own ding-dong was: it plays at the screen's own volume.
        self.assertEqual({kind: v['volume'] for kind, v in self.sounds.view({})['kinds'].items()}, {'call': -20, 'doorbell': -7, 'alert': -20})
        link = self.sounds.link('call', 'http://h:8098', 'kitchen')
        name = link.rsplit('/', 1)[1].split('.')[0]
        peak = max(abs(int.from_bytes(self.files.get(name)[0][44:][i:i + 2], 'little', signed=True)) for i in range(0, 2 * sounds.RATE, 2))
        self.assertAlmostEqual(20 * math.log10(peak / 32767), -20, delta=0.1)
        self.assertNotEqual(name, self.sounds.built['classic'])
        # Another volume is another file, so a screen takes it with its next ring; the same volume is the same file.
        self.sounds.set_volume('call', -30)
        quieter = self.sounds.link('call', 'http://h:8098', 'kitchen')
        self.assertNotEqual(quieter, link)
        self.assertEqual(self.sounds.link('call', 'http://h:8098', 'hall'), quieter)
        self.assertEqual(self.sounds.link('doorbell', 'http://h:8098', 'kitchen').rsplit('/', 1)[1].split('.')[0],
                         self.sounds.at_volume(self.sounds.built['chime'], -7))
        self.assertEqual(sounds.Sounds(self.folder, screen_files.ScreenFiles(self.folder)).kinds['call']['volume'], -30)
        for bad in (-41, 1, 'loud', True, None):
            with self.assertRaises(ValueError):
                self.sounds.set_volume('call', bad)
        self.assertIsNotNone(self.sounds.wav('classic', -10))

    def test_a_volume_is_kept_only_once_set(self):
        # A choice of sound saves the store; the volumes nobody set stay unset, so a kind follows where it starts.
        self.sounds.choose('call', 'kitchen', 'bell')
        import json
        stored = json.loads((Path(self.folder) / 'sounds.json').read_text())
        self.assertNotIn('volume', stored['kinds']['doorbell'])
        self.sounds.set_volume('doorbell', -12)
        again = sounds.Sounds(self.folder, screen_files.ScreenFiles(self.folder))
        self.assertEqual((again.volume_of('doorbell'), again.volume_of('alert')), (-12, -20))

    def test_the_test_key_plays_as_for_real(self):
        # A call's test is a ring of its own (state ring, its `rt`) ended by the app; the others the op `sound`.
        server = (ROOT / 'screen_manager/app/server.py').read_text()
        test = server[server.index('    async def sound_test(self, kind, screen_id):'):server.index('    async def alert_sounds(self')]
        for needle in ("'s': calls.RING", "'rt': self.sounds.link('call', base, screen_id)", "'s': calls.END", 'sounds.sound_message(link)',
                       "raise ValueError('none')", "raise ValueError('busy')"):
            self.assertIn(needle, test)

    def test_a_screen_that_goes_forgets_its_choices(self):
        self.sounds.choose('call', 'kitchen', 'bell')
        self.sounds.choose('alert', 'kitchen', 'notice')
        self.sounds.forget_screen('kitchen')
        self.assertEqual([mine['screens'] for mine in self.sounds.kinds.values()], [{}, {}, {}])

    def test_the_first_store_on_dev_is_read(self):
        # ringtones.json, a call's ringtone alone, became the call's choice in sounds.json.
        import json
        own = self.files.add(a_wav(1.0), 'wav')
        (Path(self.folder) / 'ringtones.json').write_text(json.dumps({'version': 1, 'default': 'own-' + own[:12], 'screens': {'kitchen': 'bell'},
                                                                      'own': [{'id': 'own-' + own[:12], 'name': 'Ours', 'file': own}]}))
        moved = sounds.Sounds(self.folder, screen_files.ScreenFiles(self.folder))
        self.assertEqual((moved.sound_of('call', 'hall'), moved.sound_of('call', 'kitchen')), ('own-' + own[:12], 'bell'))


class TheMessages(unittest.TestCase):
    def test_each_link_is_an_additive_field(self):
        # calls.message makes no `rt`; server.call_send adds it to a ring only, so an older screen never sees it.
        say = calls.Say('kitchen', 'k1', calls.RING, 'hall', False)
        self.assertNotIn('rt', calls.message(say))
        server = (ROOT / 'screen_manager/app/server.py').read_text()
        self.assertIn("if out.state == calls.RING:", server)
        self.assertIn("message['rt'] = self.sounds.link('call', base, mine['screen']['id'])", server)
        receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
        for field in ('string(root["rt"], 200)', 'string(root["ch"], 200)', 'kept_sound::play(string(root["u"], 200))'):
            self.assertIn(field, receiver)
        self.assertEqual(sounds.sound_message('http://h/files/a.wav'), {'v': 1, 'op': 'sound', 'u': 'http://h/files/a.wav'})
        # The screen says `sounds` where it plays them, and the app sends a chime or an alert's tone only there.
        self.assertIn('features.add("sounds")', (ROOT / 'packages/core.yaml').read_text())
        self.assertIn('sounds.FEATURE in', server)

    def test_a_doorbell_ring_carries_its_chime(self):
        import doorbell
        rings = doorbell.Doorbells()
        key = rings.start('camera.door', 'Door', 60, ['s1'])
        self.assertEqual(rings.message(key, chime='http://h/files/a.wav')['ch'], 'http://h/files/a.wav')
        self.assertNotIn('ch', rings.message(key))
        quiet = rings.start('camera.door', 'Door', 60, ['s1'], chime=False)
        self.assertNotIn('ch', rings.message(quiet, chime='http://h/files/a.wav'))

    def test_the_screen_takes_what_the_app_sends(self):
        source = (ROOT / 'components/smart_display/kept_sound.h').read_text()
        most = int(re.search(r'MOST = (\d+) \* 1024', source).group(1)) * 1024
        self.assertGreater(most, sounds.MAX_SECONDS * sounds.RATE * 2 + 44)
        self.assertIn('return link == "none";', source)
        self.assertEqual(sounds.NONE, 'none')
        self.assertTrue(math.isclose(sounds.MAX_SECONDS, 5.0))


if __name__ == '__main__':
    unittest.main()
