"""Screensavers of plugins and the photos step (plugin API 0.14, app 0.4.89; docs/PLUGINS.md "A screensaver",
docs/SCREENSAVER.md "Photos").

- A choice keeps a plugin's face per step and a plugin's steps of their own in the order, with their options; a saved
  choice of before reads unchanged, with the photos step right after the music.
- The app shows a plugin's face only to a screen that has it (its hello), and a plugin's step only while it has
  something to show; a plugin that left the screen leaves the step's own face, never a black glass.
- A face gets its step's contract in full words; a photo is one of a folder of Home Assistant's media, walked without a
  repeat, fetched before its turn, and cut to exactly the screen's box.
- The manifest says what a saver is, and refuses one written for an older plugin API.
"""
import asyncio
import io
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import page_delivery  # noqa: E402
import picture_legacy  # noqa: E402
import picture_paint  # noqa: E402
import picture_question as pq  # noqa: E402
import picture_service  # noqa: E402
from picture_sources import Resolved  # noqa: E402
import plugin_manifest as pm  # noqa: E402
import plugin_pictures  # noqa: E402
import saver_photos  # noqa: E402
import screen_saver  # noqa: E402
from core import media_extras, short  # noqa: E402

PLAYER = 'media_player.living_room'
PLAYING = {'state': 'playing', 'attributes': {'friendly_name': 'Living room', 'media_title': 'Song', 'media_artist': 'Band',
                                              'media_duration': 200, 'media_position': 20, 'volume_level': 0.42,
                                              'media_position_updated_at': '2026-10-17T08:00:00+00:00',
                                              'supported_features': 4127, 'entity_picture': '/api/media_player_proxy/x?cache=1'}}
DECK, DIAL, RAIN = 'plugin:vinyl.deck', 'plugin:vinyl.dial', 'plugin:weather_art.rain'


def message(choice, states, plugins=None, photos=None, faces=False):
    return screen_saver.message(screen_saver.validate(choice), states, True, short, media_extras, keys=True, now=0,
                                faces=faces, photos=photos, plugins=plugins)


class Choice(unittest.TestCase):
    def test_faces_steps_and_their_options_are_kept(self):
        choice = screen_saver.validate({
            'show': True, 'order': ['media', 'photos', RAIN, 'camera', 'clock'], 'off': [RAIN],
            'face': DIAL, 'media_face': DECK,
            'plugins': {DECK: {'options': {'spin': True}}, RAIN: {'options': {}, 'entity': 'weather.home'}},
            'photos': {'source': 'media-source://immich/abc|albums|xyz', 'every': 300, 'order': 'in_order', 'fit': 'whole'}})
        self.assertEqual(choice['order'][2], RAIN)
        self.assertEqual(choice['off'], [RAIN])
        self.assertEqual(choice['plugins'][RAIN]['entity'], 'weather.home')
        self.assertEqual(choice['photos']['every'], 300)
        for wrong in ({'media_face': 'vinyl.deck'}, {'face': 'plugin:Vinyl.deck'}, {'order': ['media', 'photos', 'camera', 'clock', 'tv']},
                      {'order': ['media', 'photos', 'camera', 'clock'] + [f'plugin:p{i}.s' for i in range(5)]},
                      {'plugins': {DECK: {'options': {'Bad key': 1}}}}, {'plugins': {'deck': {}}},
                      {'photos': {'source': 'http://example.org/x'}}, {'photos': {'every': 7}}, {'photos': {'fit': 'stretch'}},
                      {'off': [RAIN]}):
            with self.assertRaises(ValueError, msg=wrong):
                screen_saver.validate(wrong)

    def test_a_choice_of_before_reads_unchanged(self):
        old = {'show': True, 'media': PLAYER, 'camera': '', 'order': ['clock', 'media', 'camera'], 'off': ['camera'],
               'weather': 'auto', 'more': [], 'items': [], 'face': 'glass', 'numerals': 12, 'seconds': False, 'look': 'light'}
        choice = screen_saver.validate(old)
        self.assertEqual(choice['order'], ['clock', 'media', 'photos', 'camera'])
        self.assertEqual({k: choice[k] for k in old if k != 'order'}, {k: v for k, v in old.items() if k != 'order'})


class Options(unittest.TestCase):
    """A face whose options change while it is on the glass is made anew (GitHub: a plugin clock kept its old colour
    until its screensaver was turned off and on): the app sends the new options, and the screen compares them."""

    def test_the_app_sends_other_options(self):
        def options(colour):
            choice = {'show': True, 'order': ['clock', 'media', 'photos', 'camera'], 'face': DIAL, 'plugins': {DIAL: {'options': {'colour': colour}}}}
            return message(choice, {}, plugins={'faces': {DIAL: 'clock'}, 'steps': {}}, faces=True)['pf']['o']
        self.assertEqual(options('green'), {'colour': 'green'})
        self.assertNotEqual(options('green'), options('blue'))

    def test_the_screen_makes_the_saver_anew_for_other_options(self):
        receiver = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
        self.assertIn('serializeJson(pf["o"], next.plugin_options);', receiver)
        runtime = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()
        in_place = runtime[runtime.index('// The same plugin\'s saver for the same step with a new word'):]
        in_place = in_place[:in_place.index('{\n')]
        self.assertIn('saver_next.plugin_options == saver_now.plugin_options', in_place)


class Pick(unittest.TestCase):
    def test_a_plugin_face_goes_only_to_a_screen_that_has_it(self):
        choice = {'show': True, 'media': PLAYER, 'media_face': DECK, 'plugins': {DECK: {'options': {'spin': True}}}}
        states = {PLAYER: PLAYING}
        plain = message(choice, states)
        self.assertNotIn('pf', plain)
        self.assertEqual(plain['k'], 'media')
        drawn = message(choice, states, plugins={'faces': {DECK: 'media'}, 'steps': {}})
        self.assertEqual(drawn['pf']['p'], DECK)
        self.assertEqual(drawn['pf']['o'], {'spin': True})
        # The words and marks of the screen's own face still go: a screen that lost the plugin draws its own face.
        self.assertEqual(drawn['t'], 'Song')
        # A face of another step is no face of this one.
        self.assertNotIn('pf', message(choice, states, plugins={'faces': {DECK: 'clock'}, 'steps': {}}))

    def test_the_music_contract_in_full_words(self):
        choice = {'show': True, 'media': PLAYER, 'media_face': DECK}
        x = message(choice, {PLAYER: PLAYING}, plugins={'faces': {DECK: 'media'}, 'steps': {}})['pf']['x']
        self.assertEqual(x['entity'], PLAYER)
        self.assertEqual((x['title'], x['artist'], x['state'], x['volume'], x['muted']), ('Song', 'Band', 'playing', 0.42, False))
        self.assertEqual((x['duration'], x['position'], x['position_at']), (200, 20, 1792224000))
        self.assertEqual(x['picture'], 'step:')
        self.assertTrue(x['mark'])
        self.assertEqual(x['features'], 4127)

    def test_the_clock_contract(self):
        states = {'weather.home': {'state': 'sunny', 'attributes': {'temperature': 20.6}}}
        choice = {'show': True, 'order': ['clock', 'media', 'photos', 'camera'], 'face': DIAL}
        plain = message(choice, states, faces=True)
        self.assertNotIn('pf', plain)
        self.assertNotIn('cf', plain)  # a plugin's face is no face of the module: the digital clock where it lacks
        drawn = message(choice, states, plugins={'faces': {DIAL: 'clock'}, 'steps': {}}, faces=True)
        self.assertEqual(drawn['pf']['x'], {'temperature': '21°', 'items': []})
        self.assertNotIn('cf', drawn)

    def test_a_plugin_step_shows_while_it_has_something(self):
        choice = {'show': True, 'order': [RAIN, 'media', 'photos', 'camera', 'clock'],
                  'plugins': {RAIN: {'options': {'alpha': 2}, 'entity': 'weather.home'}}}
        faces = {RAIN: 'own'}
        self.assertEqual(message(choice, {}, plugins={'faces': faces, 'steps': {RAIN: None}})['k'], 'clock')
        shown = message(choice, {}, plugins={'faces': faces, 'steps': {RAIN: {'state': 'rainy'}}})
        self.assertEqual(shown, {'op': 'saver', 'k': 'plugin',
                                 'pf': {'p': RAIN, 'o': {'alpha': 2}, 'x': {'state': 'rainy'}}})
        # A screen without the plugin goes on to the next step.
        self.assertEqual(message(choice, {}, plugins=None)['k'], 'clock')

    def test_photos_need_a_screen_that_takes_them_and_a_photo_here(self):
        choice = {'show': True, 'order': ['photos', 'clock', 'media', 'camera'],
                  'photos': {'source': 'media-source://media_source/local/family'}}
        self.assertEqual(message(choice, {}, photos=None)['k'], 'clock')
        self.assertEqual(message(choice, {}, photos={'ready': False})['k'], 'clock')
        shown = message(choice, {}, photos={'ready': True, 'mark': 'abc', 'index': 3, 'count': 9, 'album': 'Family'})
        self.assertEqual(shown, {'op': 'saver', 'k': 'photos', 'e': 'saver.photos', 'n': '', 'x': {'pic': 'abc'}})


def photo_question(box, fit='auto', cap=None):
    """The photos step's question as an older screen asks it (firmware 0.29.0+, `saver` photos): the whole glass, the photo
    cut MOTION_OVERSCAN percent larger where it moves, in 8 bits."""
    place = pq.Place(0, 0, *box, fit=fit, move=picture_legacy.MOTION_OVERSCAN)
    return pq.Question(pq.Owner('saver'), (pq.Source('photos'),), box, (place,), cap=cap or (pq.MAX_SIDE, pq.MAX_BYTES),
                       formats=('bmp8',))


def moved(box, cap=None, moves=True):
    """The place a photo is painted for on glass of `box`: the service lets a photo the choice moves (`moves`) move only
    where the larger picture fits the screen's picture memory (picture_service.Service._painted)."""
    question = photo_question(box, cap=cap)
    service = picture_service.Service(None, None, types.SimpleNamespace(render=None))
    return service._painted(question, question.places[0], Resolved(b'', 'photos:x', move=moves))


def moved_box(box, cap=None):
    """The box a moving photo is cut to for glass of `box`, or None where it stands still."""
    move = moved(box, cap).move
    return (round(box[0] * (1 + move / 100)), round(box[1] * (1 + move / 100))) if move else None


class Motion(unittest.TestCase):
    def test_a_moving_photo_is_cut_larger_where_it_fits(self):
        self.assertEqual(moved_box((480, 480)), (518, 518))
        self.assertEqual(moved_box((1024, 600), (2048, 2 * 1024 * 1024)), (1106, 648))
        # The 10-inch's full glass has no room for a larger photo in its picture memory: its photos stand still.
        self.assertIsNone(moved_box((1280, 800), (2048, 2 * 1024 * 1024)))
        # A photo the choice keeps still is not cut larger.
        self.assertEqual(moved((480, 480), moves=False).move, 0)
        from PIL import Image
        bmp = picture_paint.paint(photo_question((800, 480), 'cover'), [jpeg((4000, 3000))])
        with Image.open(io.BytesIO(bmp)) as image:
            self.assertEqual(image.size, (864, 518))
        # A photo shown whole is never cut larger: it does not move.
        bmp = picture_paint.paint(photo_question((800, 480), 'whole'), [jpeg((3000, 4000))])
        with Image.open(io.BytesIO(bmp)) as image:
            self.assertEqual(image.size, (800, 480))
        # Nor is one shown whole because it is not of the glass's shape (`auto`).
        bmp = picture_paint.paint(photo_question((800, 480)), [jpeg((3000, 4000))])
        with Image.open(io.BytesIO(bmp)) as image:
            self.assertEqual(image.size, (800, 480))

    def test_the_word_says_it_moves(self):
        choice = {'show': True, 'order': ['photos', 'clock', 'media', 'camera'],
                  'photos': {'source': 'media-source://media_source/local/family', 'motion': 'slow'}}
        shown = message(choice, {}, photos={'ready': True, 'mark': 'abc'})
        self.assertEqual(shown['x'], {'pic': 'abc', 'mv': 1})
        with self.assertRaises(ValueError):
            screen_saver.validate({'photos': {'motion': 'fast'}})


class Manifest(unittest.TestCase):
    BASE = {'id': 'vinyl', 'version': '1.0.0', 'api': '0.14', 'icon': 'album', 'maintainer': 'someone', 'license': 'MIT',
            'topics': ['media']}
    ENGLISH = {'app': {'name': 'Vinyl', 'summary': 'A record player', 'deck': 'Deck', 'rain': 'Rain'}}

    def check(self, savers, **more):
        return pm.check({**self.BASE, 'savers': savers, **more}, self.ENGLISH)

    def test_a_face_and_a_step(self):
        out = self.check([{'id': 'deck', 'name': 'deck', 'step': 'media', 'memory': 900, 'pictures': 1, 'taps': True},
                          {'id': 'rain', 'name': 'rain', 'step': 'own', 'memory': 600, 'domains': ['weather'],
                           'when': {'state': ['rainy', 'pouring']}}])
        self.assertEqual([(s['id'], s['step'], s['taps'], s['moves']) for s in out['savers']],
                         [('deck', 'media', True, False), ('rain', 'own', False, False)])
        self.assertEqual(out['savers'][1]['when'], {'state': ['rainy', 'pouring']})
        self.assertEqual(pm.plugin_type(out), 'screensavers')

    def test_a_face_over_its_steps_picture(self):
        out = self.check([{'id': 'deck', 'name': 'deck', 'step': 'photos', 'memory': 500, 'backdrop': True}])
        self.assertTrue(out['savers'][0]['backdrop'])
        with self.assertRaises(pm.ManifestError):
            self.check([{'id': 'deck', 'name': 'deck', 'step': 'clock', 'memory': 500, 'backdrop': True}])

    def test_what_is_refused(self):
        bad = [
            [{'id': 'deck', 'name': 'deck', 'step': 'radio', 'memory': 900}],
            [{'id': 'deck', 'name': 'deck', 'step': 'media', 'memory': 900, 'domains': ['weather']}],
            [{'id': 'rain', 'name': 'rain', 'step': 'own', 'memory': 600}],
            [{'id': 'rain', 'name': 'rain', 'step': 'own', 'memory': 600, 'domains': ['weather'], 'when': 'data'}],
            [{'id': 'rain', 'name': 'rain', 'step': 'own', 'memory': 600, 'domains': ['weather'], 'when': 'sometimes'}],
            [{'id': 'deck', 'name': 'deck', 'step': 'media', 'memory': 900, 'taps': 'yes'}],
            [{'id': f's{i}', 'name': 'deck', 'step': 'clock', 'memory': 100} for i in range(5)],
            # An option of kind entity is a tile's (plugin API 0.15): a step of an entity names its domains instead.
            [{'id': 'rain', 'name': 'rain', 'step': 'own', 'memory': 600, 'domains': ['weather'],
              'options': [{'id': 'other', 'kind': 'entity', 'label': 'rain', 'domains': ['sensor']}]}],
        ]
        for savers in bad:
            with self.assertRaises(pm.ManifestError, msg=savers):
                self.check(savers)
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check({**self.BASE, 'api': '0.13', 'savers': [{'id': 'deck', 'name': 'deck', 'step': 'media', 'memory': 900}]},
                     self.ENGLISH)
        self.assertIn('0.14', str(caught.exception))

    def test_the_hello_names_a_plugins_savers(self):
        api, plugins = page_delivery.plugins_of({'plugin_api': '0.14', 'plugins': [
            {'id': 'vinyl', 'version': '1.0.0', 'tiles': [], 'savers': ['deck', 'Bad', 'rain']}]})
        self.assertEqual(plugins[0]['savers'], ['deck', 'rain'])

    def test_the_step_picture_is_the_apps_own(self):
        face = {'pictures': 1, 'step': 'media', 'domains': []}
        manifest = {'id': 'vinyl', 'permissions': {'network': []}}
        self.assertEqual(plugin_pictures.allowed('step:', manifest, face), 'saver')
        self.assertIsNone(plugin_pictures.allowed('step:', manifest, {**face, 'step': 'clock'}))
        self.assertIsNone(plugin_pictures.allowed('saver:picture', manifest, face))   # its old name, gone in 0.24
        found = picture_legacy.read({'tiles': DECK, 'saver': '1', 'bg': '000000', 'src': '["step:"]',
                                     'atlas': '[[0,0,100,100,0,0]]'}, {'board': 'guition', 'firmware': '0.50.0'})
        self.assertEqual((found.kind, found.entity), ('psaver', DECK))
        self.assertEqual((found.question.owner.kind, found.question.owner.key, found.question.owner.index), ('plugin_saver', DECK, -1))
        self.assertEqual(found.question.sources, (pq.Source('step'),))


def jpeg(size, colour=(200, 40, 40), orientation=None):
    from PIL import Image
    out = io.BytesIO()
    image = Image.new('RGB', size, colour)
    if orientation:
        exif = image.getexif()
        exif[0x0112] = orientation
        image.save(out, 'JPEG', exif=exif)
    else:
        image.save(out, 'JPEG')
    return out.getvalue()


class Photos(unittest.TestCase):
    def test_a_photo_fills_glass_of_its_shape_and_shows_whole_on_other_glass(self):
        self.assertTrue(picture_paint.fills((4000, 3000), (800, 480)))   # 4:3 on 5:3 glass: within five to four
        self.assertFalse(picture_paint.fills((3000, 4000), (800, 480)))  # standing on lying glass
        # `fill` always cuts (fit `cover`), `whole` never does: a standing red photo fills lying glass to its edges, and
        # a lying one shown whole leaves its own darker colour beside it.
        from PIL import Image
        with Image.open(io.BytesIO(picture_paint.paint(photo_question((800, 480), 'cover'), [jpeg((3000, 4000))]))) as image:
            self.assertGreater(image.convert('RGB').getpixel((10, 240))[0], 150)
        with Image.open(io.BytesIO(picture_paint.paint(photo_question((800, 480), 'whole'), [jpeg((4000, 3000))]))) as image:
            self.assertLess(image.convert('RGB').getpixel((10, 240))[0], 120)

    def test_a_photo_is_cut_to_exactly_the_box_in_eight_bits(self):
        from PIL import Image
        for raw, fit in ((jpeg((4000, 3000)), 'auto'), (jpeg((3000, 4000)), 'auto'), (jpeg((3000, 4000), orientation=6), 'whole')):
            question = photo_question((800, 480), fit)
            bmp = picture_paint.paint(pq.Question(question.owner, question.sources, question.box,
                                                  (pq.Place(0, 0, 800, 480, fit=fit),), formats=question.formats), [raw])
            with Image.open(io.BytesIO(bmp)) as image:
                self.assertEqual(image.size, (800, 480))
                self.assertEqual(image.mode, 'P')

    def test_a_folder_is_walked_without_a_repeat_and_fetched_ahead(self):
        async def run():
            listing = {'title': 'Family', 'children': [
                {'media_content_id': f'media-source://x/{i}.jpg', 'media_class': 'image', 'can_expand': False} for i in range(4)
            ] + [{'media_content_id': 'media-source://x/movie.mp4', 'media_class': 'video', 'can_expand': False},
                 {'media_content_id': 'media-source://x/sub', 'media_class': 'directory', 'can_expand': True}]}
            sub = {'title': 'Sub', 'children': [{'media_content_id': 'media-source://x/sub/5.jpg',
                                                 'media_content_type': 'image/jpeg', 'can_expand': False}]}
            fetched = []

            async def request(kind, **data):
                if kind == 'media_source/browse_media':
                    return sub if data['media_content_id'].endswith('/sub') else listing
                return {'url': '/media/local/' + data['media_content_id'].rsplit('/', 1)[1], 'mime_type': 'image/jpeg'}

            async def fetch(address):
                fetched.append(address)
                return jpeg((40, 30))

            now = [0.0]
            photos = saver_photos.Photos(request, fetch, clock=lambda: now[0])
            choice = {'source': 'media-source://x', 'order': 'shuffle', 'every': 60}
            self.assertFalse(photos.state('screen', choice)['ready'])   # the folder is read first
            for _ in range(5):
                await asyncio.sleep(0)
            seen = []
            for step in range(10):
                state = photos.state('screen', choice)
                for _ in range(5):
                    await asyncio.sleep(0)
                state = photos.state('screen', choice)
                if state['ready']:
                    seen.append(state['mark'])
                    self.assertEqual(state['count'], 5)
                now[0] += 61
            # Five photos (the video is none), each once before any comes again.
            self.assertEqual(len(set(seen[:5])), 5)
            self.assertTrue(all(address.startswith('/media/local/') for address in fetched))
            self.assertIsNotNone(photos.raw('screen'))
        asyncio.run(run())

    def test_a_photo_that_cannot_be_had_is_passed_over(self):
        async def run():
            listing = {'children': [{'media_content_id': f'media-source://x/{i}.jpg', 'media_class': 'image'} for i in range(2)]}

            async def request(kind, **data):
                if kind == 'media_source/browse_media':
                    return listing
                return {'url': '/media/local/' + data['media_content_id'].rsplit('/', 1)[1]}

            async def fetch(address):
                if address.endswith('0.jpg'):
                    raise OSError('gone')
                return jpeg((40, 30))

            photos = saver_photos.Photos(request, fetch, clock=lambda: 0.0, rng=__import__('random').Random(1))
            choice = {'source': 'media-source://x', 'order': 'in_order', 'every': 60}
            state = {'ready': False}
            for _ in range(6):
                photos.state('screen', choice)
                for _ in range(5):
                    await asyncio.sleep(0)
                state = photos.state('screen', choice)
            self.assertTrue(state['ready'])
            self.assertEqual(state['mark'], saver_photos.mark('media-source://x/1.jpg'))
        asyncio.run(run())

    def test_a_heic_may_have_fewer_pixels_than_a_jpeg(self):
        # A JPEG is read small (draft); a HEIC is decoded whole, so a telephone's 48 MP passes and little more.
        from types import SimpleNamespace
        self.assertEqual(saver_photos.pixel_limit(SimpleNamespace(format='JPEG')), saver_photos.MAX_PIXELS)
        self.assertEqual(saver_photos.pixel_limit(SimpleNamespace(format='HEIF')), saver_photos.MAX_PIXELS_HEIF)
        self.assertGreaterEqual(saver_photos.MAX_PIXELS_HEIF, 48_000_000)
        self.assertLess(saver_photos.MAX_PIXELS_HEIF, saver_photos.MAX_PIXELS)
        # The painter reads the same limit, so a photo readable() let through is not refused later.
        source = (ROOT / 'screen_manager/app/picture_paint.py').read_text()
        self.assertIn('saver_photos.pixel_limit(source)', source)

    def test_a_crafted_picture_of_too_many_pixels_is_refused(self):
        from PIL import Image
        out = io.BytesIO()
        Image.new('1', (12000, 12000)).save(out, 'PNG')
        with self.assertRaises(Exception):
            saver_photos.readable(out.getvalue())
        # And by the painter, from its header, before it is decoded, whatever source brought it.
        with self.assertRaisesRegex(ValueError, 'too large'):
            picture_paint.paint(photo_question((800, 480)), [out.getvalue()])


if __name__ == '__main__':
    unittest.main()
