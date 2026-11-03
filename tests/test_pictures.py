"""The pictures of every screen, one way (docs/PICTURES.md): the question a screen asks (picture_question), every shape of
older firmware read into it (picture_legacy), the rules of each source for each owner (picture_sources.Sources.may), the
links on the camera port with their 304s (picture_links) and the service that answers (picture_service): a still, a
stream, or no answer while a picture is on its way."""
import asyncio
import dataclasses
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import picture_legacy  # noqa: E402
import picture_links  # noqa: E402
import picture_paint  # noqa: E402
import picture_question as pq  # noqa: E402
import picture_service  # noqa: E402
import picture_sources  # noqa: E402
from picture_question import Owner, Place, Question, Source  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
GUITION = {'board': 'guition', 'firmware': '0.52.0', 'name': 'Hall'}     # 480 x 480 glass, 8-bit pictures, 304s
OLD_GUITION = {'board': 'guition', 'firmware': '0.2.77', 'name': 'Hall'}  # 24-bit pictures only
P4 = {'board': 'jc8012p4a1', 'firmware': '0.52.0', 'name': 'Wall'}       # 1280 x 800 glass, streams


def png(size=(64, 48), colour=(200, 30, 90)):
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', size, colour).save(out, 'PNG')
    return out.getvalue()


def places(*sources, box=(100, 100)):
    return Question(Owner('view'), sources, box, tuple(Place(0, 0, *box) for _ in sources))


# ----- the question (picture_question) -----

class Sources(unittest.TestCase):
    def test_every_kind_of_source_and_what_is_not_one(self):
        good = {
            'tile:3': Source('tile', '3'),
            'map:2?focus=person.sam&move=1,-2': Source('map', '2', (('focus', 'person.sam'), ('move', '1,-2'))),
            'camera:camera.porch': Source('camera', 'camera.porch'),
            'camera:image.doorbell': Source('camera', 'image.doorbell'),
            'cover:media_player.kitchen': Source('cover', 'media_player.kitchen'),
            'entity:person.alex': Source('entity', 'person.alex'),
            'vacuum:vacuum.robo': Source('vacuum', 'vacuum.robo'),
            'library:media_player.spotify/12': Source('library', 'media_player.spotify/12'),
            'photos:': Source('photos'),
            'step:': Source('step'),
            'https://api.example.org/a.jpg': Source('url', 'https://api.example.org/a.jpg'),
            '/api/image/serve/abc/512x512': Source('ha', '/api/image/serve/abc/512x512'),
            '/api/image_proxy/image.door?token=1': Source('ha', '/api/image_proxy/image.door?token=1'),
            '/local/me.png': Source('ha', '/local/me.png'),
        }
        for text, source in good.items():
            self.assertEqual(pq.source(text), source, text)
        # Its text again, as a log and a question name it.
        for text in ('tile:3', 'map:2?focus=person.sam&move=1,-2', 'camera:camera.porch', 'photos:', 'step:', '/local/me.png'):
            self.assertEqual(pq.source(text).text, text)
        self.assertIsNone(pq.source('saver:picture'))   # its name in plugin API 0.14 to 0.16, gone in 0.24: one form
        for bad in (None, '', 42, 'x' * 600, 'nope:1', 'tile', 'tile:256', 'tile:x', 'tile:3?focus=person.sam',
                    'map:2?zoom=1', 'map:2?focus', 'camera:media_player.kitchen', 'camera:Camera.porch', 'cover:camera.porch',
                    'vacuum:camera.porch', 'entity:nothing', 'library:media_player.spotify', 'library:media_player.spotify/abc',
                    'library:camera.porch/1', 'ftp://example.org/a.jpg', '/api/states', '/api/camera_proxy/camera.porch',
                    '/api/image/serve/../x', '/local//x', 'camera:camera.porch?focus=person.sam'):
            self.assertIsNone(pq.source(bad), bad)


class Parse(unittest.TestCase):
    BASE = {'o': 'tile', 'i': 3, 'src': ['tile:3'], 'box': [480, 270], 'at': [[0, 0, 480, 270, 12, 0]], 'fit': ['cover'],
            'bg': '1C1C1E', 'look': 'd', 'cap': 1310720, 'fmt': ['bmp8', 'bmp24'], 'pace': 15000, 'live': [480, 270]}

    def parse(self, canvas=(480, 480), **changes):
        q = {**self.BASE, **changes}
        for name in [name for name, value in changes.items() if value is None]:
            del q[name]
        return pq.parse(json.dumps(q), 42, canvas)

    def test_a_question_as_the_screen_asks_it(self):
        self.assertEqual(self.parse(), Question(
            Owner('tile', 3), (Source('tile', '3'),), (480, 270), (Place(0, 0, 480, 270, 12, 0, 'cover', 0x1C1C1E),),
            look='d', cap=(pq.MAX_SIDE, pq.MAX_BYTES), formats=('bmp8', 'bmp24'), pace=15000, live=(480, 270), number=42))
        # A question of a plugin's card: a source per place, each with its own fit, ground and effects.
        q = self.parse(o='plugin_card', i=None, p='plugin:bus.release', **{'for': 'media_player.kitchen'},
                       src=['cover:media_player.kitchen', 'https://api.example.org/a.jpg'], box=[300, 160],
                       at=[[0, 10, 90, 140, 6, 0], [105, 0, 90, 156, 6, 170]], fit=['cover', 'contain'], bg=['101010', '202020'],
                       fx=[{'turn': 'right', 'mirror': 1}, {'fade': 1, 'dim': 30, 'move': 8}], sound=1, live=None, look='l')
        self.assertEqual(q.owner, Owner('plugin_card', -1, 'plugin:bus.release', 'media_player.kitchen'))
        self.assertEqual(q.places, (Place(0, 10, 90, 140, 6, 0, 'cover', 0x101010, turn='right', mirror=True),
                                    Place(105, 0, 90, 156, 6, 170, 'contain', 0x202020, fade=True, dim=30, move=8)))
        self.assertEqual((q.look, q.dark, q.live, q.sound), ('l', False, (), True))
        # One source for every place.
        q = self.parse(src='photos:', o='saver', i=None, fit='cover', at=[[0, 0, 240, 270, 0, 0], [240, 0, 240, 270, 0, 0]])
        self.assertEqual(q.sources, (Source('photos'), Source('photos')))

    def test_formats_and_the_cap(self):
        self.assertEqual(self.parse(fmt=['webp', 'jpeg']).formats, ('jpeg',))
        self.assertEqual(self.parse(fmt=['webp']).formats, ('bmp24',))
        self.assertEqual(self.parse(fmt=None).formats, ('bmp24',))
        self.assertEqual(self.parse(fmt=['jpeg']).format, 'jpeg')
        self.assertEqual(self.parse(cap=3 << 20).cap, (pq.LARGE_SIDE, 3 << 20))
        self.assertEqual(self.parse(cap=64 << 20).cap, (pq.LARGE_SIDE, pq.LARGE_BYTES))
        self.assertEqual(self.parse(cap=None).cap, (pq.MAX_SIDE, pq.MAX_BYTES))
        self.assertEqual(self.parse(pace=None).pace, 0)
        self.assertEqual(self.parse(look='x').look, 'l')

    def test_what_is_no_question(self):
        for text in (None, 123, '{' + ' ' * 16384 + '}', 'nope', '[]', '"q"'):
            self.assertIsNone(pq.parse(text, 1, (480, 480)), text)
        self.assertIsNone(self.parse(canvas=(0, 480)))
        bad = [dict(o='stranger'), dict(o=None), dict(i=None), dict(i='3'), dict(i=256), dict(i=True),
               dict(o='plugin_tile', p=None), dict(o='plugin_tile', p='bus.next'), dict(o='plugin_card', p='plugin:Bus.next'),
               {'for': 'not an entity'},
               dict(box=[0, 270]), dict(box=[4096, 10]), dict(box=[480.0, 270]), dict(box=None),
               dict(at=[]), dict(at=[[0, 0, 4, 4, 0, 0]] * 65), dict(at='x'), dict(at=[[0, 0, 480, 270, 12]]),
               dict(src=['tile:3', 'tile:4']), dict(src=['camera:light.hall']), dict(src=None),
               dict(at=[[400, 0, 100, 270, 0, 0]]), dict(at=[[0, 0, 480, 270, 136, 0]]), dict(at=[[0, 0, 480, 270, 0, 100]]),
               dict(at=[[-1, 0, 100, 100, 0, 0]]),
               dict(fit=['stretch']), dict(fit=['cover', 'cover']), dict(bg='white'), dict(bg=['1C1C1E', '000000']),
               dict(fx=[{'spin': 1}]), dict(fx=[{'turn': 'up'}]), dict(fx=[{'dim': 95}]), dict(fx=[{'move': 30}]), dict(fx=['x']),
               dict(live=[480]), dict(live=[10, 10]), dict(live='x'),
               dict(pace=-1), dict(pace=3600001), dict(pace=1.5)]
        for changes in bad:
            self.assertIsNone(self.parse(**changes), changes)

    def test_the_answer(self):
        q = self.parse()
        self.assertEqual(pq.answer(q, 'http://192.168.1.57:8098/camera/t.bmp'),
                         {'v': 1, 'op': 'camera', 't': 'q', 'e': '', 'u': 'http://192.168.1.57:8098/camera/t.bmp', 'n': 42})
        self.assertEqual(pq.answer(q, '', meta={'f': ''}), {'v': 1, 'op': 'camera', 't': 'q', 'e': '', 'u': '', 'n': 42, 'm': {'f': ''}})
        # An older shape keeps its own `t` and `e`, without the number.
        self.assertEqual(pq.answer(q, '', 'full', 'camera.porch'), {'v': 1, 'op': 'camera', 't': 'full', 'e': 'camera.porch', 'u': ''})

    def test_a_question_over_the_cap_is_scaled_as_the_screen_scales_it(self):
        q = Question(Owner('view'), (Source('camera', 'camera.porch'),) * 2, (1280, 800),
                     (Place(0, 0, 1280, 800, 40), Place(640, 400, 640, 400, 200)))
        self.assertEqual(pq.scale_for(q.box, q.cap), 0.8)
        scaled = q.scaled(pq.scale_for(q.box, q.cap))
        self.assertEqual((scaled.box, scaled.places), ((1024, 640), (Place(0, 0, 1024, 640, 32), Place(512, 320, 512, 320, 160))))
        self.assertIs(q.scaled(1), q)
        self.assertEqual(pq.scale_for((1280, 800), pq.cap_of(str(2 << 20))), 1.0)


# ----- older firmware's questions (picture_legacy) -----

class Legacy(unittest.TestCase):
    def read(self, request, screen=GUITION, index_of=None):
        return picture_legacy.read(request, screen, index_of)

    def test_a_full_view(self):
        found = self.read({'entity': 'camera.porch', 'view': '9'})
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner, q.sources, q.number), ('full', 'camera.porch', Owner('view'),
                                                                                    (Source('camera', 'camera.porch'),), 9))
        self.assertEqual((q.box, q.places, q.pace, q.formats, q.live), ((480, 480), (Place(0, 0, 480, 480, fit='shrink'),),
                                                                        picture_legacy.FULL_VIEW_PACE, ('bmp24',), ()))
        # A P4 names the room below its top bar and may stream it, with the camera's sound; at its own pixels with its cap.
        found = self.read({'entity': 'camera.porch', 'live': '1280x744', 'sound': '1', 'cap': str(2 << 20)}, P4)
        self.assertEqual((found.question.live, found.question.sound, found.question.box), ((1280, 744), True, (1280, 800)))
        self.assertEqual(self.read({'entity': 'camera.porch', 'live': '1280x744'}, P4).question.box, (1024, 640))
        # An image entity has no stream; a room the screen cannot name is none.
        self.assertEqual(self.read({'entity': 'image.door', 'live': '1280x744', 'sound': '1'}, P4).question.live, ())
        for live in ('wide', '10x10', '99999x10'):
            self.assertEqual(self.read({'entity': 'camera.porch', 'live': live}, P4).question.live, (), live)
        # A board without pictures has no full view.
        self.assertIsNone(self.read({'entity': 'camera.porch'}, {'board': 'cyd', 'firmware': '0.52.0'}))

    def test_a_cover(self):
        found = self.read({'entity': 'media_player.kitchen', 'size': '96', 'bg': '1C1C1E'})
        self.assertEqual((found.kind, found.entity, found.question.owner.kind, found.question.box), ('cover', 'media_player.kitchen', 'card', (96, 96)))
        self.assertEqual(found.question.places, (Place(0, 0, 96, 96, 8, fit='cover', ground=0x1C1C1E),))
        self.assertEqual(self.read({'entity': 'media_player.kitchen', 'size': '48', 'bg': '000000'}).question.places[0].radius, 4)
        for bad in ({'size': '47', 'bg': '000000'}, {'size': '321', 'bg': '000000'}, {'size': '96'}, {'size': '96', 'bg': 'black'}):
            self.assertIsNone(self.read({'entity': 'media_player.kitchen', **bad}), bad)

    def test_a_map(self):
        index_of = {'person.alex': 2, 'screen.map': 8}.get
        found = self.read({'entity': 'person.alex', 'idx': '2', 'focus': 'person.sam', 'move': '1,-2', 'dark': '1', 'view': '5'},
                          index_of=index_of)
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner), ('full', 'person.alex', Owner('view', of='person.alex')))
        self.assertEqual(q.sources, (Source('map', '2', (('entity', 'person.alex'), ('focus', 'person.sam'), ('move', '1,-2'))),))
        self.assertEqual((q.box, q.places, q.look, q.formats), ((480, 480), (Place(0, 0, 480, 480, fit='exact'),), 'd', ('bmp8', 'bmp24')))
        # A focus or a move the map cannot take is left out; the look is light unless the screen says dark.
        q = self.read({'entity': 'person.alex', 'idx': '2', 'focus': 'Not One', 'move': 'up'}).question
        self.assertEqual((q.sources[0].params, q.look), ((('entity', 'person.alex'),), 'l'))
        # Without a tile's index: the first map tile of that entity, and none when it has none.
        self.assertEqual(self.read({'entity': 'screen.map'}, index_of=index_of).question.sources[0].ref, '8')
        self.assertIsNone(self.read({'entity': 'person.sam'}, index_of=index_of))
        self.assertIsNone(self.read({'entity': 'person.alex'}))
        # A person's tile with a size is no map (that is a cover's shape, and a person has none).
        self.assertIsNone(self.read({'entity': 'person.alex', 'size': '96', 'bg': '000000'}))

    def test_the_screensaver(self):
        media = self.read({'saver': 'media', 'entity': 'media_player.living_room', 'cap': '1000'})
        self.assertEqual((media.kind, media.entity, media.question.owner.kind, media.question.formats), ('saver', 'media_player.living_room', 'saver', ('bmp8',)))
        self.assertEqual((media.question.sources[0], media.question.places[0], media.question.pace),
                         (Source('cover', 'media_player.living_room'), Place(0, 0, 480, 480, fit='saver', dim=picture_legacy.SAVER_DIM), 0))
        camera = self.read({'saver': 'camera', 'entity': 'camera.door'})
        self.assertEqual((camera.question.sources[0], camera.question.places[0].fit, camera.question.pace),
                         (Source('camera', 'camera.door'), 'cover', picture_legacy.SAVER_PACE))
        photos = self.read({'saver': 'photos', 'entity': 'saver.photos'})
        self.assertEqual((photos.kind, photos.question.sources[0], photos.question.places[0]),
                         ('saver', Source('photos'), Place(0, 0, 480, 480, fit='auto', move=picture_legacy.MOTION_OVERSCAN)))
        for bad in ({'saver': 'media', 'entity': 'camera.door'}, {'saver': 'camera', 'entity': 'media_player.living_room'},
                    {'saver': 'media'}, {'saver': 'camera', 'entity': 'light.hall'}):
            self.assertIsNone(self.read(bad), bad)
        self.assertIsNone(self.read({'saver': 'media', 'entity': 'media_player.living_room'}, {'board': 'cyd', 'firmware': '0.52.0'}))

    def test_a_vacuums_map(self):
        found = self.read({'vmap': '300x200', 'bg': '101010', 'entity': 'vacuum.robo', 'dark': '1'})
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner.kind, q.sources, q.box), ('vmap', 'vacuum.robo', 'card', (Source('vacuum', 'vacuum.robo'),), (300, 200)))
        self.assertEqual((q.places, q.look, q.cap), ((Place(0, 0, 300, 200, fit='exact', ground=0x101010),), 'd', (pq.LARGE_SIDE, pq.LARGE_BYTES)))
        # 8 bits for a screen whose decoder reads them, as every other picture (it went in 24 before the one painter).
        self.assertEqual((q.formats, self.read({'vmap': '300x200', 'bg': '101010', 'entity': 'vacuum.robo'}, OLD_GUITION).question.formats),
                         (('bmp8', 'bmp24'), ('bmp24',)))
        for bad in ({'vmap': '10x10'}, {'vmap': '3000x10'}, {'vmap': '2000x2000'}, {'vmap': 'wide'}, {'bg': 'black'}, {'entity': 'camera.porch'}):
            self.assertIsNone(self.read({'vmap': '300x200', 'bg': '101010', 'entity': 'vacuum.robo', **bad}), bad)

    def test_a_page_of_a_library(self):
        atlas = '[[0,0,100,100,8,0],[110,0,100,100,8,0]]'
        found = self.read({'entity': 'media_player.spotify', 'lib': '3,4', 'atlas': atlas, 'bg': 'E7E7E7'})
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner.kind, q.box), ('lib', 'media_player.spotify', 'library', (210, 100)))
        self.assertEqual(q.sources, (Source('library', 'media_player.spotify/3'), Source('library', 'media_player.spotify/4')))
        self.assertEqual({p.ground for p in q.places}, {0xE7E7E7})
        for bad in ({'lib': 'abc'}, {'lib': '3'}, {'lib': ''}, {'atlas': 'x'}, {'entity': 'camera.porch'}):
            self.assertIsNone(self.read({'entity': 'media_player.spotify', 'lib': '3,4', 'atlas': atlas, 'bg': 'E7E7E7', **bad}), bad)

    def test_a_pages_tiles_alone_in_an_atlas_and_in_a_strip(self):
        # Each tile alone (firmware 0.52.0): one frame at the top left, by its index, its tile the owner.
        found = self.read({'tiles': 'camera.porch', 'idx': '4', 'size': '54', 'bg': '101010', 'dark': '1',
                           'atlas': '[[0,0,236,236,18,170]]', 'view': '40'})
        q = found.question
        self.assertEqual((found.kind, found.entity, q.owner, q.number, q.look), ('live', 'camera.porch', Owner('tile', 4), 40, 'd'))
        self.assertEqual((q.sources, q.box, q.places), ((Source('tile', '4', (('entity', 'camera.porch'),)),), (236, 236),
                                                        (Place(0, 0, 236, 236, 18, 170, ground=0x101010),)))
        # The tiles of a page in one atlas (0.3.1): no owner tile of its own.
        found = self.read({'tiles': 'camera.porch,media_player.spotify', 'idx': '0,4', 'size': '54', 'bg': '101010,E7E7E7',
                           'atlas': '[[0,0,200,100,12,0],[210,0,100,100,12,170]]'})
        self.assertEqual((found.entity, found.question.owner, found.question.box), ('camera.porch,media_player.spotify', Owner('tile', -1), (310, 100)))
        self.assertEqual([p.ground for p in found.question.places], [0x101010, 0xE7E7E7])
        # A strip of squares (0.2.77): one per tile, top to bottom.
        found = self.read({'tiles': 'camera.porch,person.alex', 'idx': '0,2', 'size': '60', 'bg': 'FFFFFF,000000'}, OLD_GUITION)
        self.assertEqual((found.question.box, [(p.x, p.y, p.w, p.h, p.radius) for p in found.question.places], found.question.formats),
                         ((60, 120), [(0, 0, 60, 60, 10), (0, 60, 60, 60, 10)], ('bmp24',)))
        # Older firmware names its tiles by entity alone: the layout's first pictured tile of each.
        found = self.read({'tiles': 'camera.porch', 'size': '54', 'bg': 'FFFFFF'}, index_of={'camera.porch': 7}.get)
        self.assertEqual(found.question.sources[0].ref, '7')
        self.assertIsNone(self.read({'tiles': 'camera.porch', 'size': '54', 'bg': 'FFFFFF'}))
        # A P4 streams one camera tile into its card's size; a page of two never.
        found = self.read({'tiles': 'camera.porch', 'idx': '0', 'size': '54', 'bg': 'FFFFFF', 'atlas': '[[0,0,300,200,12,0]]',
                           'live': '300x200', 'sound': '1'}, P4)
        self.assertEqual((found.question.live, found.question.sound), ((300, 200), True))
        found = self.read({'tiles': 'camera.porch,camera.shed', 'idx': '0,1', 'size': '54', 'bg': 'FFFFFF,FFFFFF',
                           'atlas': '[[0,0,300,200,12,0],[310,0,300,200,12,0]]', 'live': '300x200'}, P4)
        self.assertEqual(found.question.live, ())
        for bad in ({'tiles': 'light.hall'}, {'bg': 'FFFFFF,FFFFFF'}, {'size': '200'}, {'idx': '0,1'}, {'idx': 'x'},
                    {'atlas': '[[0,0,481,100,0,0]]'}, {'tiles': ','.join(['camera.porch'] * 7), 'bg': ','.join(['FFFFFF'] * 7), 'idx': None}):
            request = {'tiles': 'camera.porch', 'idx': '0', 'size': '54', 'bg': 'FFFFFF', **bad}
            self.assertIsNone(self.read({k: v for k, v in request.items() if v is not None}), bad)

    def test_a_plugins_tile_card_and_screensaver(self):
        base = {'tiles': 'plugin:bus.next', 'bg': '202020', 'src': '["https://api.example.org/a.jpg","cover:media_player.kitchen"]',
                'atlas': '[[0,0,60,90,6,0],[40,0,60,90,6,0]]', 'fit': '["cover","contain"]', 'turn': '["right",""]', 'mirror': '[0,1]'}
        tile = self.read({**base, 'idx': '3'})
        self.assertEqual((tile.kind, tile.entity, tile.question.owner), ('live', 'plugin:bus.next', Owner('plugin_tile', 3, 'plugin:bus.next')))
        self.assertEqual(tile.question.sources, (Source('url', 'https://api.example.org/a.jpg'), Source('cover', 'media_player.kitchen')))
        self.assertEqual(tile.question.places, (Place(0, 0, 60, 90, 6, 0, 'cover', 0x202020, turn='right'),
                                                Place(40, 0, 60, 90, 6, 0, 'within', 0x202020, mirror=True)))
        card = self.read({**base, 'card': '1', 'for': 'media_player.kitchen'})
        self.assertEqual((card.kind, card.question.owner), ('pcard', Owner('plugin_card', -1, 'plugin:bus.next', 'media_player.kitchen')))
        saver = self.read({**base, 'saver': '1', 'for': 'weather.home', 'src': '["step:","step:"]'})
        self.assertEqual((saver.kind, saver.question.owner, saver.question.sources),
                         ('psaver', Owner('plugin_saver', -1, 'plugin:bus.next', 'weather.home'), (Source('step'), Source('step'))))
        for bad in ({'idx': 'x'}, {'card': '1', 'saver': '1'}, {'card': '1', 'for': 'screen.clock'}, {'bg': 'red'},
                    {'src': '["/api/states"]'}, {'fit': '["fill","cover"]'}, {'turn': '["up",""]'}, {'mirror': '[2,0]'},
                    {'atlas': '[[0,0,60,90,6,0]]'}):
            self.assertIsNone(self.read({**base, 'idx': '3', **bad}), bad)

    def test_what_older_firmware_never_asked(self):
        for request in (None, 'nonsense', {}, {'entity': 'light.hall'}, {'entity': 'sensor.porch', 'size': '96', 'bg': '000000'}):
            self.assertIsNone(self.read(request), request)
        self.assertIsNone(picture_legacy.read({'entity': 'camera.porch'}, None))


class Firmware(unittest.TestCase):
    def test_a_board_without_pictures_asks_for_none(self):
        # The CYD's flash (docs/RELEASING.md step 2): the question's text is built only where a picture can show, as the
        # picture store keeps none there (picture_store.h); the host builds (the render, the WASM preview) still ask.
        tiles = (ROOT / 'components/smart_display/runtime_tiles.h').read_text()
        ask = tiles[tiles.index('inline void picture_ask('):]
        ask = ask[:ask.index('\n}\n')]
        self.assertIn('#if defined(USE_ESP32) && !defined(SCREEN_PICTURES)', ask)
        self.assertLess(ask.index('#if defined(USE_ESP32) && !defined(SCREEN_PICTURES)'), ask.index('picture_question::json(asked)'))
        store = (ROOT / 'components/smart_display/picture_store.h').read_text()
        self.assertIn('#if defined(USE_ESP32) && !defined(SCREEN_PICTURES)', store)


class Frames(unittest.TestCase):
    """The frames of an atlas (picture_legacy.frames): bounded by the screen's own canvas, never overlapping for the
    tiles of a page, painted at their own pixels (the shared tile image buffer of before, app 0.3.1)."""

    def test_reject_unbounded_malformed_and_overlapping_frames(self):
        for frames in (None, {}, [[0, 0, 481, 480, 8, 170]], [[-1, 0, 40, 40, 4, 0]],
                       [[0, 0, 40, 40, 21, 0]], [[0, 0, 40, 40, 4, 255]],
                       [[False, 0, 40, 40, 4, 0]], [[0, 0, 40, 40, 4]],
                       [[0, 0, 40, 40, 4, 0], [20, 20, 40, 40, 4, 0]]):
            count = len(frames) if isinstance(frames, list) else 1
            self.assertIsNone(picture_legacy.frames(json.dumps(frames), (480, 480), count), frames)
        self.assertIsNone(picture_legacy.frames('[]', (480, 480), 0))
        self.assertIsNone(picture_legacy.frames('not json', (480, 480), 1))
        self.assertIsNone(picture_legacy.frames('[[0,0,40,40,4,0]]', (480, 480), 2))
        # The places of one plugin card may lie over each other.
        self.assertIsNotNone(picture_legacy.frames('[[0,0,40,40,4,0],[20,20,40,40,4,0]]', (480, 480), 2, overlap=True))

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_native_dimensions_rounding_and_readability_scrim(self):
        from PIL import Image
        frames = [[4, 8, 80, 40, 8, 170], [90, 8, 30, 70, 4, 0]]
        atlas = picture_legacy.frames(json.dumps(frames), (1280, 800), 2)
        self.assertEqual(atlas[:2], (120, 78))
        raw = io.BytesIO()
        Image.new('RGB', (200, 200), 'white').save(raw, 'PNG')
        grounds = [0xEEEEEE, 0x123456]
        question = Question(Owner('tile', -1), (Source('tile', '0'), Source('tile', '1')), atlas[:2],
                            tuple(Place(*frame, ground=ground) for frame, ground in zip(atlas[2], grounds)))
        result = picture_paint.paint(question, [raw.getvalue(), None], 'bmp24')
        with Image.open(io.BytesIO(result)) as im:
            self.assertEqual(im.size, (120, 78))
            self.assertTrue(all(84 <= channel <= 85 for channel in im.getpixel((44, 28))))
            self.assertEqual(im.getpixel((4, 8)), (238, 238, 238))
            self.assertEqual(im.getpixel((105, 30)), (18, 52, 86))

    def test_board_canvas_is_the_allocation_limit(self):
        self.assertIsNone(picture_legacy.frames('[[0,0,800,480,8,170]]', (480, 800), 1))
        self.assertIsNotNone(picture_legacy.frames('[[0,0,800,480,8,170]]', (800, 480), 1))
        self.assertIsNotNone(picture_legacy.frames('[[0,0,1280,800,8,170]]', (1280, 800), 1))
        # A tile's question on a screen is bounded by that screen's own glass.
        request = {'tiles': 'camera.porch', 'idx': '0', 'size': '54', 'bg': 'FFFFFF', 'atlas': '[[0,0,800,480,8,170]]'}
        self.assertIsNone(picture_legacy.read(request, GUITION))
        self.assertIsNotNone(picture_legacy.read(request, P4))


# ----- the rules of each source (picture_sources.Sources.may) -----

class Manager:
    """What Sources and the service ask of the app's Manager: one screen's layout, what it may show, its screensaver."""
    TILES = [
        {'entity': 'camera.porch', 'name': '', 'options': {'display': 'live'}},                        # 0
        {'entity': 'camera.shed', 'name': '', 'options': {}},                                           # 1: its icon
        {'entity': 'person.alex', 'name': '', 'options': {'display': 'map'}},                           # 2
        {'entity': 'person.sam', 'name': '', 'options': {}},                                            # 3: a person's own
        {'entity': 'media_player.spotify', 'name': '', 'options': {'display': 'cover'}},                # 4
        {'entity': 'media_player.kitchen', 'name': '', 'options': {'display': 'favorite', 'play': {'thumb': 'https://i.scdn.co/x'}}},
        {'entity': 'plugin:bus.next', 'name': '', 'options': {'plugin_entity': 'media_player.kitchen'}},  # 6
        {'entity': 'light.hall', 'name': '', 'options': {}},                                            # 7
        {'entity': 'screen.map', 'name': '', 'options': {'display': 'map'}},                            # 8
        {'entity': 'camera.drive', 'name': '', 'options': {'display': 'live', 'fit': 'contain'}},       # 9
    ]

    def __init__(self, snapshots=None, screen=GUITION):
        self.tiles = [dict(tile) for tile in self.TILES]
        self.allowed = {'camera.porch', 'camera.shed', 'camera.drive', 'image.door', 'media_player.spotify', 'vacuum.robo'}
        self.saver = {'camera.door', 'media_player.living_room'}
        self.plugin_problem = None
        self.base = 'http://192.168.1.57:8098'
        self.player = dict(screen, id='text.hall', online=True)
        self.ha = types.SimpleNamespace(states={})
        self.rest_pools = {}
        self.photos = types.SimpleNamespace(raw=lambda inbox: None)
        self.snapshots = snapshots or picture_sources.Snapshots(None)
        self.sources = picture_sources.Sources(picture_sources.Providers.of(self), self.snapshots)
        self.links = picture_links.Links()
        self.service = picture_service.Service(self, self.sources, self.links)

    def layout_tiles(self, inbox):
        return self.tiles

    def camera_allowed(self, inbox, entity):
        return entity in self.allowed

    def saver_entities(self, inbox):
        return self.saver

    def plugin_picture_refused(self, inbox, screen, question, source):
        return self.plugin_problem

    def screen(self, inbox):
        return self.player

    async def link_base(self, screen):
        return self.base

    def followed(self, entity):
        return entity

    def player_ground(self, entity, attributes):
        return '204060,FFFFFF'


class May(unittest.TestCase):
    def may(self, owner, source, manager=None):
        manager = manager or Manager()
        question = Question(owner, (source,), (100, 100), (Place(0, 0, 100, 100),))
        return manager.sources.may('text.hall', manager.player, question, source)

    def test_a_tile_of_the_layout_that_shows_a_picture(self):
        tile = Owner('tile', 0)
        for n in ('0', '2', '4', '5', '8', '9'):
            self.assertIsNone(self.may(tile, Source('tile', n)), n)
        self.assertIsNone(self.may(tile, Source('tile', '0', (('entity', 'camera.porch'),))))
        for source in (Source('tile', '1'), Source('tile', '3'), Source('tile', '6'), Source('tile', '7'), Source('tile', '99'),
                       Source('tile', '0', (('entity', 'camera.shed'),))):
            self.assertIn('not a pictured tile', self.may(tile, source), source)
        # A favourite without its picture shows none.
        manager = Manager()
        manager.tiles[5]['options'] = {'display': 'favorite', 'play': {}}
        self.assertIsNotNone(self.may(tile, Source('tile', '5'), manager))

    def test_a_map_tile_or_a_persons_own(self):
        view = Owner('view', 2)
        for source in (Source('map', '2'), Source('map', '3'), Source('map', '8'), Source('map', '2', (('entity', 'person.alex'),)),
                       Source('map', '2', (('focus', 'person.sam'),))):
            self.assertIsNone(self.may(view, source), source)
        for source in (Source('map', '7'), Source('map', '0'), Source('map', '99'), Source('map', '2', (('entity', 'person.sam'),))):
            self.assertIn('not a map', self.may(view, source), source)

    def test_a_camera_a_cover_and_a_vacuum_by_owner(self):
        # An alert's camera is the alert's (Manager.alert_images sends it); the screensaver's what it follows; anything else
        # what the screen's layout (or a recent alert) has.
        self.assertIsNone(self.may(Owner('alert'), Source('camera', 'camera.anywhere')))
        self.assertIsNone(self.may(Owner('saver'), Source('camera', 'camera.door')))
        self.assertIsNone(self.may(Owner('saver'), Source('cover', 'media_player.living_room')))
        self.assertIn('not on the screensaver', self.may(Owner('saver'), Source('camera', 'camera.porch')))
        for owner in (Owner('view'), Owner('card'), Owner('tile', 0)):
            self.assertIsNone(self.may(owner, Source('camera', 'camera.porch')))
            self.assertIsNone(self.may(owner, Source('camera', 'image.door')))
            self.assertIsNone(self.may(owner, Source('cover', 'media_player.spotify')))
            self.assertIsNone(self.may(owner, Source('vacuum', 'vacuum.robo')))
            for source in (Source('camera', 'camera.garden'), Source('cover', 'media_player.other'), Source('vacuum', 'vacuum.other')):
                self.assertIn('not on the layout', self.may(owner, source), (owner, source))

    def test_a_library_photos_and_what_is_a_plugins(self):
        self.assertIsNone(self.may(Owner('library'), Source('library', 'media_player.spotify/3')))
        self.assertIn('not on the layout', self.may(Owner('library'), Source('library', 'media_player.other/3')))
        self.assertIsNone(self.may(Owner('saver'), Source('photos')))
        self.assertIn('screensaver', self.may(Owner('view'), Source('photos')))
        for source in (Source('step'), Source('url', 'https://api.example.org/a.jpg'), Source('ha', '/local/me.png'),
                       Source('entity', 'person.alex')):
            for owner in (Owner('view'), Owner('tile', 0), Owner('saver'), Owner('alert')):
                self.assertIn("is a plugin's", self.may(owner, source), (owner, source))

    def test_a_plugins_places(self):
        tile = Owner('plugin_tile', 6, 'plugin:bus.next')
        for source in (Source('url', 'https://api.example.org/a.jpg'), Source('ha', '/local/me.png'), Source('step'),
                       Source('cover', 'media_player.kitchen'), Source('entity', 'media_player.kitchen')):
            self.assertIsNone(self.may(tile, source), source)
        # The core's sources only of the place's own entity (plugin API 0.17).
        for source in (Source('camera', 'camera.porch'), Source('cover', 'media_player.spotify')):
            self.assertIn("not this plugin place's entity", self.may(tile, source), source)
        # The layout's own pictures are no plugin's.
        for source in (Source('tile', '0'), Source('map', '2'), Source('library', 'media_player.kitchen/1'), Source('photos'),
                       Source('vacuum', 'vacuum.robo')):
            self.assertIn("not a plugin's", self.may(tile, source), source)
        # What the plugin's manifest refuses (plugin_pictures.refused_source) is refused, whatever the source.
        manager = Manager()
        manager.plugin_problem = 'https://x is not an address the plugin may show'
        self.assertEqual(self.may(tile, Source('url', 'https://x.org/a.jpg'), manager), manager.plugin_problem)
        # A card or a screensaver step shown for an entity: that entity's pictures.
        card = Owner('plugin_card', -1, 'plugin:bus.release', 'media_player.kitchen')
        self.assertIsNone(self.may(card, Source('cover', 'media_player.kitchen')))
        self.assertIsNotNone(self.may(card, Source('cover', 'media_player.spotify')))
        self.assertIsNotNone(self.may(Owner('plugin_card', -1, 'plugin:bus.release'), Source('cover', 'media_player.kitchen')))
        saver = Owner('plugin_saver', -1, 'plugin:weather_art.rain', 'weather.home')
        self.assertIsNone(self.may(saver, Source('entity', 'weather.home')))
        self.assertIsNone(self.may(saver, Source('step')))


class ProvidersAlone(unittest.IsolatedAsyncioTestCase):
    """Sources reads the app through Providers alone (docs/PICTURE_ARCHITECTURE.md, section 4): built from fakes, with
    every fact a test does not hand in failing when it is read, the rules and the getting work without a Manager."""

    def providers(self, **facts):
        def missing(name):
            def read(*args, **options):
                raise AssertionError(f'Sources read {name}, which this test did not hand in')
            return read
        names = [f.name for f in dataclasses.fields(picture_sources.Providers)]
        self.assertFalse(set(facts) - set(names), 'a fact Providers does not have')
        return picture_sources.Providers(**{name: facts.get(name) or missing(name) for name in names})

    async def test_a_camera_tile_and_a_cover_tile_from_fakes(self):
        tiles = [{'entity': 'camera.porch', 'name': '', 'options': {'display': 'live'}},
                 {'entity': 'media_player.spotify', 'name': '', 'options': {'display': 'cover'}}]

        async def fetch(entity):
            return b'still of ' + entity.encode()

        async def fetch_cover(entity):
            return b'cover of ' + entity.encode()
        snapshots = picture_sources.Snapshots(fetch, fetch_cover=fetch_cover, picture=lambda e: '/api/media_player_proxy/' + e)
        app = self.providers(tiles=lambda inbox: tiles, camera_allowed=lambda inbox, entity: entity == 'camera.porch',
                             states=lambda: {}, followed=lambda entity: entity)
        sources = picture_sources.Sources(app, snapshots)

        def question(owner, source):
            return Question(owner, (source,), (100, 100), (Place(0, 0, 100, 100),))
        # The rules: a pictured tile of the layout, a camera the layout has.
        self.assertIsNone(sources.may('text.hall', GUITION, question(Owner('tile', 0), Source('tile', '0')), Source('tile', '0')))
        self.assertIsNone(sources.may('text.hall', GUITION, question(Owner('view'), Source('camera', 'camera.porch')),
                                      Source('camera', 'camera.porch')))
        self.assertIn('not on the layout', sources.may('text.hall', GUITION, question(Owner('view'), Source('camera', 'camera.yard')),
                                                       Source('camera', 'camera.yard')))
        # The getting: the camera's still with its stream, the player's cover (not at rest: no mosaic).
        place = Place(0, 0, 100, 100)
        still = await sources.get('text.hall', GUITION, question(Owner('tile', 0), Source('tile', '0')), Source('tile', '0'), place)
        self.assertEqual((still.raw, still.stream, still.mark.startswith('camera:camera.porch:')), (b'still of camera.porch', 'cover', True))
        cover = await sources.get('text.hall', GUITION, question(Owner('tile', 1), Source('tile', '1')), Source('tile', '1'), place)
        self.assertEqual((cover.raw, cover.mark.startswith('cover:')), (b'cover of media_player.spotify', True))

    def test_the_manager_binding_reads_as_it_is_called(self):
        # Providers.of reads the Manager when a fact is asked, never before: its states as they are then, a method
        # replaced later.
        manager = Manager()
        app = picture_sources.Providers.of(manager)
        manager.ha.states['light.hall'] = {'state': 'on'}
        self.assertEqual(app.state('light.hall'), {'state': 'on'})
        manager.ha = types.SimpleNamespace(states={'light.hall': {'state': 'off'}})
        self.assertEqual(app.state('light.hall'), {'state': 'off'})
        manager.layout_tiles = lambda inbox: ['replaced']
        self.assertEqual(app.tiles('text.hall'), ['replaced'])
        manager.rest_pools['media_player.spotify'] = (1.0, ['a'])
        self.assertEqual(app.rest_pool('media_player.spotify'), (1.0, ['a']))


class StreamOf(unittest.TestCase):
    """Which camera a question of one place streams, and how its picture fits its room (picture_service.stream_of)."""

    def test_the_full_view_a_live_tile_and_a_plugins_place(self):
        def question(owner, source, fit='cover'):
            return Question(owner, (source,), (100, 100), (Place(0, 0, 100, 100, fit=fit),))
        of = picture_service.stream_of
        # The full view of a camera: whole.
        self.assertEqual(of(question(Owner('view'), Source('camera', 'camera.porch'))), ('camera.porch', 'contain'))
        self.assertIsNone(of(question(Owner('view'), Source('camera', 'image.door'))))
        # A camera tile set to Live: as its tile says.
        live = {'entity': 'camera.drive', 'options': {'display': 'live'}}
        self.assertEqual(of(question(Owner('tile', 9), Source('tile', '9')), live), ('camera.drive', 'cover'))
        self.assertEqual(of(question(Owner('tile', 9), Source('tile', '9')), dict(live, options={'display': 'live', 'fit': 'contain'})),
                         ('camera.drive', 'contain'))
        for tile in (None, {'entity': 'camera.drive', 'options': {}}, {'entity': 'image.door', 'options': {'display': 'live'}}):
            self.assertIsNone(of(question(Owner('tile', 9), Source('tile', '9')), tile), tile)
        # A plugin tile's place set live: as the place's fit says.
        place = Owner('plugin_tile', 6, 'plugin:door.view')
        self.assertEqual(of(question(place, Source('camera', 'camera.porch'))), ('camera.porch', 'cover'))
        for fit in ('contain', 'within', 'whole'):
            self.assertEqual(of(question(place, Source('camera', 'camera.porch'), fit)), ('camera.porch', 'contain'), fit)
        # Anything else streams not: a cover, a camera of a card.
        self.assertIsNone(of(question(Owner('view'), Source('cover', 'media_player.spotify'))))
        self.assertIsNone(of(question(Owner('card'), Source('camera', 'camera.porch'))))


# ----- the links on the camera port (picture_links) -----

class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


class Links(unittest.IsolatedAsyncioTestCase):
    async def test_a_still_and_its_304(self):
        clock = Clock()
        links = picture_links.Links(clock=clock)
        token = links.add(still=b'BMstill')
        status, body, etag, kind = await links.serve(token)
        self.assertEqual((status, body, kind), (200, b'BMstill', 'image/bmp'))
        self.assertEqual(await links.serve(token, etag), (304, None, etag, 'image/bmp'))
        self.assertEqual((await links.serve(token, '"other"'))[0], 200)
        # Firmware before 0.49.0 logged a 304 as a failed load: its links never answer one.
        old = links.add(still=b'BMstill', revalidate=False)
        self.assertEqual((await links.serve(old, etag))[:2], (200, b'BMstill'))
        # A JPEG for a screen whose decoder takes one.
        self.assertEqual((await links.serve(links.add(still=b'\xff\xd8', suffix='jpg')))[3], 'image/jpeg')
        # A still stays STILL_SECONDS after its last load.
        clock.now += picture_links.STILL_SECONDS - 1
        self.assertEqual((await links.serve(token))[0], 200)
        clock.now += picture_links.STILL_SECONDS + 1
        self.assertEqual(await links.serve(token), (404, None, '', ''))
        self.assertNotIn(token, links)

    async def test_a_recipe_is_painted_again_at_every_load(self):
        clock = Clock()
        painted = []

        async def render(recipe):
            painted.append(recipe)
            return recipe['found']
        links = picture_links.Links(render, clock=clock)
        recipe = {'found': ('"a"', b'BMa')}
        token = links.add(recipe=recipe)
        self.assertEqual(await links.serve(token), (200, b'BMa', '"a"', 'image/bmp'))
        self.assertEqual(await links.serve(token, '"a"'), (304, None, '"a"', 'image/bmp'))
        recipe['found'] = ('"b"', b'BMb')
        self.assertEqual(await links.serve(token, '"a"'), (200, b'BMb', '"b"', 'image/bmp'))
        self.assertEqual(len(painted), 3)
        # Nothing to show now: 503, and the screen asks again.
        recipe['found'] = None
        self.assertEqual((await links.serve(token))[0], 503)
        # Without a 304 for older firmware, the same picture comes whole.
        recipe['found'] = ('"a"', b'BMa')
        self.assertEqual((await links.serve(links.add(recipe=recipe, revalidate=False), '"a"'))[0], 200)
        # A link that paints again lives LINK_SECONDS after its last load; one nobody loads goes sooner than a still.
        clock.now += picture_links.LINK_SECONDS + 1
        self.assertEqual((await links.serve(token))[0], 404)
        self.assertEqual((await picture_links.Links(clock=clock).serve('x'))[0], 404)
        nothing = picture_links.Links(clock=clock)
        self.assertEqual((await nothing.serve(nothing.add(recipe=recipe)))[0], 503, 'no painter behind the links')

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    async def test_the_service_answers_304_only_where_the_screen_reads_one(self):
        async def fetch(entity):
            return png()

        async def never(delay):
            await asyncio.Event().wait()
        for screen, owner_request, revalidate in (
                ({**GUITION, 'firmware': '0.48.0'}, {'tiles': 'camera.porch', 'idx': '0', 'size': '54', 'bg': 'FFFFFF'}, False),
                ({**GUITION, 'firmware': '0.49.0'}, {'tiles': 'camera.porch', 'idx': '0', 'size': '54', 'bg': 'FFFFFF'}, True),
                ({**GUITION, 'firmware': '0.48.0'}, {'entity': 'camera.porch'}, True)):
            manager = Manager(picture_sources.Snapshots(fetch, sleep=never), screen)
            question = picture_legacy.read(owner_request, manager.player, manager.sources.index_of('text.hall')).question
            found = await manager.service.answer('text.hall', manager.player, question)
            token = found.url.rsplit('/', 1)[1][:-4]
            self.assertEqual(manager.links.links[token].revalidate, revalidate, (screen['firmware'], owner_request))
            _, _, etag, _ = await manager.links.serve(token)
            self.assertEqual((await manager.links.serve(token, etag))[0], 304 if revalidate else 200)


# ----- the service (picture_service) -----

class Stream:
    def __init__(self):
        self.calls = []

    def link(self, entity, box, **options):
        self.calls.append((entity, box, options))
        return 'S' * 24


@unittest.skipUnless(HAS_PIL, 'Pillow')
class Service(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fetched = []

        async def fetch(entity):
            self.fetched.append(entity)
            return png((640, 360))

        async def never(delay):
            await asyncio.Event().wait()
        self.manager = Manager(picture_sources.Snapshots(fetch, sleep=never), P4)
        self.stream = Stream()
        self.service = picture_service.Service(self.manager, self.manager.sources, self.manager.links, self.stream)

    def read(self, request):
        return picture_legacy.read(request, self.manager.player, self.manager.sources.index_of('text.hall')).question

    async def test_a_vacuums_map_is_drawn_at_its_place(self):
        # The whole way of a vacuum card's map: its map entity, the map read once (Snapshots.vacuum), drawn at the place
        # on the card's colour (vacuum_map.render) and painted; the drawing function once had another name.
        import vacuum_map
        from PIL import Image
        drawing = vacuum_map.read(png((80, 80), (40, 160, 90)))  # square: the card beside it
        manager = self.manager
        manager.device_entries = lambda entity: [{'entity_id': 'image.robo_map'}]

        async def held(entity, mark):
            return drawing, 'abc123'
        manager.snapshots.vacuum = held
        question = picture_legacy.read({'entity': 'vacuum.robo', 'vmap': '300x200', 'bg': 'FFFFFF', 'dark': '0'},
                                       manager.player).question
        with mock.patch('vacuum_card.map_entity', return_value={'e': 'image.robo_map', 'm': '1'}):
            found = await self.service.picture('text.hall', manager.player, question)
        self.assertEqual(found.state, 'ok')
        image = Image.open(io.BytesIO(found.body))
        self.assertEqual(image.size, (300, 200))
        self.assertEqual(image.convert('RGB').getpixel((2, 100)), (255, 255, 255), 'the card\'s colour beside the map')

    async def test_a_plugin_tiles_live_place_streams_its_own_camera(self):
        # A plugin tile's place set live (plugin API 0.17, ui::live): its own camera streams into the place, filled or
        # whole as the place's fit says; another camera is not the place's to show, live or not.
        self.manager.tiles[6]['options']['plugin_entity'] = 'camera.porch'
        owner = Owner('plugin_tile', 6, 'plugin:bus.next')
        for fit, suffix in (('cover', '.mjpeg'), ('contain', '.mjpeg?fit=contain')):
            question = Question(owner, (Source('camera', 'camera.porch'),), (320, 180), (Place(0, 0, 320, 180, radius=12, fit=fit),),
                                live=(320, 180))
            found = await self.service.answer('text.hall', self.manager.player, question)
            self.assertTrue(found.stream and found.url.endswith(suffix), (fit, found))
        self.assertEqual(self.stream.calls[-1], ('camera.porch', (320, 180), {'cover': False, 'screen': 'text.hall', 'tile': True,
                                                                               'turn': 0}))
        # On a screen that takes its live pictures turned, a plugin's place gets them turned too.
        self.manager.picture_turn_of = lambda inbox: 270
        await self.service.answer('text.hall', self.manager.player, question)
        self.assertEqual(self.stream.calls[-1][2]['turn'], 270)
        del self.manager.picture_turn_of
        other = Question(owner, (Source('camera', 'camera.drive'),), (320, 180), (Place(0, 0, 320, 180),), live=(320, 180))
        found = await self.service.answer('text.hall', self.manager.player, other)
        self.assertTrue(found.problem and not found.url)

    async def test_a_camera_that_streams(self):
        found = await self.service.answer('text.hall', self.manager.player, self.read({'entity': 'camera.porch', 'live': '1280x744', 'sound': '1'}))
        self.assertEqual((found.url, found.stream, found.shown), (f'http://192.168.1.57:8098/camera/{"S" * 24}.mjpeg', True, ('camera.porch',)))
        self.assertEqual(self.stream.calls, [('camera.porch', (1280, 744), {'sound': True, 'screen': 'text.hall', 'turn': 0})])
        self.assertEqual(self.fetched, [], 'a stream needs no still')
        # A camera tile set to Live streams into its card's size, filled or whole as the tile says.
        found = await self.service.answer('text.hall', self.manager.player, self.read(
            {'tiles': 'camera.drive', 'idx': '9', 'size': '54', 'bg': 'FFFFFF', 'atlas': '[[0,0,300,200,12,0]]', 'live': '300x200', 'sound': '1'}))
        self.assertTrue(found.stream)
        self.assertTrue(found.url.endswith('.mjpeg?fit=contain'))
        self.assertEqual(self.stream.calls[-1], ('camera.drive', (300, 200), {'cover': False, 'warm': True, 'screen': 'text.hall', 'tile': True,
                                                                               'turn': 0}))

    async def test_a_turned_glass_gets_its_live_pictures_turned(self):
        # A screen whose glass is turned and whose hello says it takes its live pictures so (caps picture_turn, Manager.
        # picture_turn_of): the links of its live tiles and of its full view turn them.
        self.manager.picture_turn_of = lambda inbox: 270 if inbox == 'text.hall' else 0
        await self.service.answer('text.hall', self.manager.player, self.read(
            {'tiles': 'camera.drive', 'idx': '9', 'size': '54', 'bg': 'FFFFFF', 'atlas': '[[0,0,300,200,12,0]]', 'live': '300x200'}))
        self.assertEqual(self.stream.calls[-1][2]['turn'], 270)
        await self.service.answer('text.hall', self.manager.player, self.read({'entity': 'camera.porch', 'live': '1280x744'}))
        self.assertEqual(self.stream.calls[-1][2]['turn'], 270)

    async def test_a_tile_of_the_screens_own_camera_is_drawn_by_the_screen(self):
        # The screen's own camera on a tile of its own (plugin API 0.22): the screen draws it from the camera, so the
        # answer is "own:" (with the tile's fit), no link and no stream; any other camera tile streams as before.
        self.manager.own_camera_of = lambda inbox, screen, entity: entity == 'camera.drive'
        request = {'tiles': 'camera.drive', 'idx': '9', 'size': '54', 'bg': 'FFFFFF', 'atlas': '[[0,0,300,200,12,0]]',
                   'live': '300x200'}
        found = await self.service.answer('text.hall', self.manager.player, self.read(request))
        self.assertEqual((found.url, found.stream), ('own:?fit=contain', True))
        self.assertEqual(self.stream.calls, [])
        self.manager.own_camera_of = lambda inbox, screen, entity: False  # a camera of another screen, or none
        found = await self.service.answer('text.hall', self.manager.player, self.read(request))
        self.assertTrue(found.url.endswith('.mjpeg?fit=contain'))

    async def test_what_does_not_stream_gets_a_still(self):
        # An image entity, a page of two, a screen that does not stream (no `live`), an app without a stream source.
        for request in ({'entity': 'image.door', 'live': '1280x744'},
                        {'tiles': 'camera.porch,camera.drive', 'idx': '0,9', 'size': '54', 'bg': 'FFFFFF,FFFFFF',
                         'atlas': '[[0,0,300,200,12,0],[310,0,300,200,12,0]]', 'live': '300x200'},
                        {'entity': 'camera.porch'}):
            found = await self.service.answer('text.hall', self.manager.player, self.read(request))
            self.assertFalse(found.stream, request)
            self.assertTrue(found.url.endswith('.bmp'), request)
        found = await self.manager.service.answer('text.hall', self.manager.player, self.read({'entity': 'camera.porch', 'live': '1280x744'}))
        self.assertTrue(found.url.endswith('.bmp'))
        self.assertEqual(len(self.stream.calls), 0)
        # A refused camera is refused before any stream: an answer without a link.
        found = await self.service.answer('text.hall', self.manager.player, self.read({'entity': 'camera.garden', 'live': '1280x744'}))
        self.assertEqual((found.url, found.stream, self.stream.calls), ('', False, []))
        self.assertIn('camera.garden', found.problem)

    async def test_a_picture_on_its_way_gets_no_answer_yet(self):
        # The photos step before its photo is here: no answer, so the screen asks again (camera_view::ASK_AGAIN_MS).
        saver = self.read({'saver': 'photos', 'entity': 'saver.photos'})
        self.assertIsNone(await self.service.answer('text.hall', self.manager.player, saver))
        # The screensaver's cover on its way longer than a load waits: no answer either, where a card is told there is none.
        gate = asyncio.Event()

        async def slow_cover(entity):
            await gate.wait()
            return png((300, 300))
        snapshots = self.manager.snapshots
        snapshots.fetch_cover, snapshots.picture = slow_cover, lambda entity: '/api/media_player_proxy/x?cache=1'
        cover = self.read({'saver': 'media', 'entity': 'media_player.living_room'})
        with mock.patch.object(picture_sources.Snapshots.cover, '__defaults__', (0.05,)):
            self.assertIsNone(await self.service.answer('text.hall', self.manager.player, cover))
            self.assertTrue(snapshots.cover_pending('media_player.living_room'))
            # Once it came, the answer is its link.
            gate.set()
            await asyncio.sleep(0)
            found = await self.service.answer('text.hall', self.manager.player, cover)
        self.assertTrue(found.url.endswith('.bmp'))
        # A source on its way among others (a page of tiles) does not hold the others back.
        gate.clear()
        snapshots.picture = lambda entity: '/api/media_player_proxy/x?cache=2'
        both = Question(Owner('saver'), (Source('cover', 'media_player.living_room'), Source('camera', 'camera.door')), (200, 100),
                        (Place(0, 0, 100, 100), Place(100, 0, 100, 100)))
        with mock.patch.object(picture_sources.Snapshots.cover, '__defaults__', (0.05,)):
            found = await self.service.answer('text.hall', self.manager.player, both)
        self.assertEqual(found.shown, ('', 'camera.door'))
        self.assertTrue(found.url)
        gate.set()

    async def test_a_picture_painted_once_for_what_it_shows(self):
        question = self.read({'entity': 'camera.porch'})
        first = await self.manager.service.picture('text.hall', self.manager.player, question)
        again = await self.manager.service.picture('text.hall', self.manager.player, question)
        self.assertEqual((first.state, first.etag, first.body), ('ok', again.etag, again.body))
        self.assertEqual(len(self.manager.service.kept), 1)
        self.assertTrue(first.volatile, 'a camera shows another picture by itself')
        # Without an address for this app on the LAN there is no link to give.
        self.manager.base = None
        with self.assertLogs(picture_service.LOG, 'WARNING'):
            self.assertEqual(await self.manager.service.answer('text.hall', self.manager.player, question), picture_service.Answer())


# ----- the firmware's question, both ways -----

class FirmwareQuestions(unittest.TestCase):
    """Every owner's question as the firmware builds it (tests/fixtures/picture_questions.cpp): its JSON read as this app
    reads a question, and its old fields read as this app reads an older screen, give the same question."""

    @classmethod
    def setUpClass(cls):
        import os
        import shutil
        import subprocess
        import tempfile
        compiler = shutil.which(os.environ.get('CXX', 'clang++')) or shutil.which('g++')
        if not compiler:
            raise unittest.SkipTest('no C++ compiler')
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / 'questions'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', f'-I{ROOT}',
                            str(ROOT / 'tests/fixtures/picture_questions.cpp'), '-o', str(program)], check=True)
            out = subprocess.run([str(program)], check=True, capture_output=True, text=True).stdout
        cls.lines = [line.split('\t') for line in out.splitlines() if line]

    def both(self, name, text, old, screen):
        canvas = tuple(pq.box(screen, 'full'))
        new = pq.parse(text, 7, canvas)
        self.assertIsNotNone(new, f'{name}: the app cannot read its question')
        index_of = lambda entity: 3 if entity in ('camera.porch', 'media_player.kitchen') else -1
        legacy = picture_legacy.read({**json.loads(old), 'view': '7'}, screen, index_of)
        self.assertIsNotNone(legacy, f'{name}: the app cannot read its old fields')
        return new, legacy.question

    def test_every_owner_reads_the_same_both_ways(self):
        self.assertEqual(len(self.lines), 14)
        for name, text, old in self.lines:
            with self.subTest(name):
                screen = P4 if 'full view' in name else GUITION
                new, old_q = self.both(name, text, old, screen)
                self.assertEqual((new.owner.kind, new.owner.index), (old_q.owner.kind, old_q.owner.index))
                self.assertEqual([s.text for s in new.sources], [s.text for s in old_q.sources])
                self.assertEqual(new.box, old_q.box)
                self.assertEqual(new.look, old_q.look)
                self.assertEqual((new.live, new.sound), (old_q.live, old_q.sound))
                self.assertEqual(len(new.places), len(old_q.places))
                for a, b in zip(new.places, old_q.places):
                    self.assertEqual((a.x, a.y, a.w, a.h, a.radius, a.shade, a.ground), (b.x, b.y, b.w, b.h, b.radius, b.shade, b.ground))
                    self.assertEqual((a.turn, a.mirror), (b.turn, b.mirror))
                    self.assertEqual((a.fit, a.dim, a.move, a.fade), (b.fit, b.dim, b.move, b.fade))
                # A tile's pace is its layout's (Sources reads the tile's refresh); an older screen never said it.
                if new.owner.kind != 'tile':
                    self.assertEqual(new.pace, old_q.pace)


# ----- every source for every owner, the whole way -----

class Shelf:
    """A player's library page as the app keeps it (server.shelves): its items by their token."""
    def get(self, entity, token):
        return {'thumb': f'https://i.scdn.co/{token}', 'title': f'Album {token}'}


class FullManager(Manager):
    """The Manager with every source's own getting: maps, the covers at rest, thumbnails, a library page, the photos, the
    screensaver's step, a plugin's pictures and a vacuum's map."""

    def __init__(self, screen):
        async def fetch(entity):
            return png((640, 360), (20, 90, 160))

        async def fetch_cover(entity):
            return png((300, 300), (160, 40, 40))

        async def never(delay):
            await asyncio.Event().wait()
        super().__init__(picture_sources.Snapshots(fetch, fetch_cover=fetch_cover, picture=lambda e: '/api/media_player_proxy/' + e,
                                                    sleep=never), screen)
        self.tiles.append({'entity': 'media_player.radio', 'name': '', 'options': {'display': 'cover', 'rest': 'liked'}})  # 10
        self.saver |= {'camera.door'}
        self.shelves = {'text.hall': Shelf()}
        self.photos = types.SimpleNamespace(raw=lambda inbox: png((900, 1200), (60, 120, 60)),
                                            state=lambda inbox, choice: {'mark': 'p1'})
        self.ha.states.update({'media_player.radio': {'state': 'idle', 'attributes': {}}})
        self.rest_pools = {'media_player.radio': (0, ['x'])}
        self.drawn = []

    def drawer(self, what):
        async def draw(width, height):
            from PIL import Image
            self.drawn.append((what, width, height))
            return Image.new('RGB', (width, height), (90, 90, 200))
        return (lambda: what), draw

    def map_render(self, tile, shape, dark, full=False, focus='', move=None):
        return self.drawer('map')

    def rest_render(self, entity, rows=2):
        self.rest_rows = rows
        return self.drawer('mosaic')

    def map_meta(self, mark, width, height, focus):
        return {'p': []}

    def registry_index(self):
        return {}

    async def thumbnail(self, entity, url, title=''):
        return png((200, 200), (200, 160, 40))

    def saver_choice(self, screen):
        return {'photos': {'fit': 'auto', 'motion': 'still'}}

    async def saver_picture(self, inbox, screen, kind):
        return png((300, 300), (30, 30, 30))

    def plugin_saver_kind(self, inbox, key):
        return 'media'

    async def plugin_picture(self, inbox, screen, question, source):
        return png((400, 600), (120, 20, 160))

    def device_entries(self, entity):
        return [{'entity_id': 'image.robo_map'}]


@unittest.skipUnless(HAS_PIL, 'Pillow')
class EverySource(unittest.IsolatedAsyncioTestCase):
    """Each kind of source for each owner that may have it, as a screen asks and loads it: the answer's link, and behind
    it a picture of exactly the question's box in the format the screen asked for first. A source that is drawn (a map, the
    covers at rest, a vacuum's map) is drawn at its place's size."""

    CASES = [
        # (owner, sources, box, fit)
        (Owner('tile', 0), ('tile:0',), (200, 120), 'cover'),                     # a camera's tile
        (Owner('tile', 2), ('tile:2',), (200, 200), 'cover'),                     # a person's map
        (Owner('tile', 4), ('tile:4',), (96, 96), 'cover'),                       # a player's cover
        (Owner('tile', 5), ('tile:5',), (96, 96), 'cover'),                       # a favourite's thumbnail
        (Owner('tile', 8), ('tile:8',), (300, 200), 'cover'),                     # the screen's map
        (Owner('tile', 10), ('tile:10',), (200, 200), 'cover'),                   # the covers at rest
        (Owner('view'), ('camera:camera.porch',), (480, 300), 'contain'),         # a camera's full view
        (Owner('view'), ('map:2?focus=person.alex&move=0',), (480, 480), 'exact'),  # a map opened
        (Owner('card'), ('cover:media_player.spotify',), (160, 160), 'cover'),    # the media card's cover
        (Owner('card'), ('vacuum:vacuum.robo',), (300, 200), 'exact'),            # a vacuum's map
        (Owner('saver'), ('cover:media_player.living_room',), (480, 480), 'saver'),
        (Owner('saver'), ('camera:camera.door',), (480, 480), 'saver'),
        (Owner('saver'), ('photos:',), (480, 480), 'auto'),
        (Owner('library'), ('library:media_player.spotify/1', 'library:media_player.spotify/2'), (220, 100), 'cover'),
        (Owner('alert'), ('camera:camera.drive',), (392, 220), 'shrink'),
        (Owner('plugin_tile', 6, 'plugin:bus.next'), ('https://image.tmdb.org/p.jpg', 'cover:media_player.kitchen'), (240, 120), 'cover'),
        (Owner('plugin_tile', 6, 'plugin:bus.next'), ('entity:media_player.kitchen',), (120, 120), 'contain'),
        (Owner('plugin_card', -1, 'plugin:bus.release', 'media_player.kitchen'), ('cover:media_player.kitchen',), (200, 200), 'cover'),
        (Owner('plugin_saver', -1, 'plugin:vinyl.face'), ('step:',), (300, 300), 'cover'),
    ]

    async def answer(self, screen, owner, sources, box, fit, formats):
        import vacuum_map
        manager = FullManager(screen)
        drawing = vacuum_map.read(png((80, 80), (40, 160, 90)))

        async def held(entity, mark):
            return drawing, 'abc123'
        manager.snapshots.vacuum = held
        n = len(sources)
        width = box[0] // n
        places = tuple(Place(i * width, 0, width, box[1], radius=8, fit=fit, ground=0x123456) for i in range(n))
        question = Question(owner, tuple(pq.source(s) for s in sources), box, places, formats=formats)
        self.assertTrue(all(question.sources), sources)
        with mock.patch.object(picture_sources.rest_mosaic, 'wants', return_value=True), \
                mock.patch.object(picture_sources.rest_mosaic, 'at_rest', return_value=True), \
                mock.patch('map_card.shown', return_value={'person.alex'}), \
                mock.patch('vacuum_card.map_entity', return_value={'e': 'image.robo_map', 'm': '1'}):
            found = await manager.service.answer('text.hall', manager.player, question)
            self.assertIsNotNone(found, f'{owner.kind} {sources}: no answer yet')
            self.assertFalse(found.problem, f'{owner.kind} {sources}: {found.problem}')
            self.assertTrue(found.url and not found.stream, f'{owner.kind} {sources}: {found}')
            status, body, etag, kind = await manager.links.serve(found.url.rsplit('/', 1)[1].split('.')[0])
        for watch in manager.snapshots.watches.values():
            for task in (watch.task, watch.ahead):
                if task is not None:
                    task.cancel()
        self.assertEqual(status, 200, f'{owner.kind} {sources}')
        return manager, body, kind

    def size(self, image, box, fit):
        # `shrink` keeps the picture's own proportions within the box (the alert's 16:9 frame of older firmware): one
        # side is the box's, the other no larger. Every other fit fills the box exactly.
        if fit != 'shrink':
            return image.size == box
        return image.size[0] <= box[0] and image.size[1] <= box[1] and (image.size[0] == box[0] or image.size[1] == box[1])

    async def test_every_source_for_every_owner(self):
        from PIL import Image
        for screen, formats, mode in ((GUITION, ('bmp8', 'bmp24'), 'P'), (OLD_GUITION, ('bmp24',), 'RGB')):
            for owner, sources, box, fit in self.CASES:
                with self.subTest(screen=screen['firmware'], owner=owner.kind, sources=sources):
                    manager, body, kind = await self.answer(screen, owner, sources, box, fit, formats)
                    self.assertEqual(kind, 'image/bmp')
                    with Image.open(io.BytesIO(body)) as image:
                        self.assertTrue(self.size(image, box, fit), image.size)
                        self.assertEqual(image.mode, mode)
                    # What is drawn is drawn at its place's size (a map, the covers at rest), never at the box's.
                    for what, width, height in manager.drawn:
                        self.assertEqual((width, height), (box[0] // len(sources), box[1]), what)

    async def test_a_jpeg_where_the_screen_takes_one(self):
        # A P4 names JPEG first: photographs come as JPEG, a drawn map (lines and words) as the screen's first BMP.
        from PIL import Image
        drawn = {'tile:2', 'tile:8', 'map:2?focus=person.alex&move=0', 'vacuum:vacuum.robo'}
        for owner, sources, box, fit in self.CASES:
            with self.subTest(owner=owner.kind, sources=sources):
                manager, body, kind = await self.answer(P4, owner, sources, box, fit, ('jpeg', 'bmp8', 'bmp24'))
                with Image.open(io.BytesIO(body)) as image:
                    if drawn & set(sources):
                        self.assertTrue(self.size(image, box, fit), image.size)
                        self.assertEqual((kind, image.format, image.mode), ('image/bmp', 'BMP', 'P'))
                    else:
                        # Whole MCUs for the P4's decoder, shown at the size its APP15 segment names (picture_paint).
                        self.assertEqual((kind, image.format), ('image/jpeg', 'JPEG'))
                        self.assertFalse(image.info.get('progressive'), 'the P4 decoder takes baseline JPEG only')
                        self.assertEqual((image.size[0] % 16, image.size[1] % 16), (0, 0))
                        shown = picture_paint.jpeg_size(body)
                        self.assertTrue(self.size(types.SimpleNamespace(size=shown), box, fit), shown)


if __name__ == '__main__':
    unittest.main()
