"""The media card (app 0.2.77, firmware 0.2.64): what the app pre-computes for it, and the album cover the app serves
like a camera image (camera_feed), at the size the card asks for, with the corners rounded over the colour behind them."""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import io
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import camera_feed  # noqa: E402
from core import COVER_MIN_FIRMWARE, extras, media_cover, media_extras, state_message  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager

TILES = runtime_source()
MODEL = (ROOT / 'components/smart_display/runtime_model.h').read_text()
CARD = (ROOT / 'components/smart_display/media_card.h').read_text()
SONOS = {'friendly_name': 'Office', 'media_title': 'Woman at the Loom', 'media_artist': 'KATZROAR', 'media_album_name': 'Invocation',
         'media_duration': 270, 'media_position': 0, 'media_position_updated_at': '2026-09-18T10:09:49.068667+00:00',
         'volume_level': 0.14, 'is_volume_muted': False, 'supported_features': 8321599,
         'entity_picture': '/api/media_player_proxy/media_player.office?token=5674b25e&cache=556b49fd9c3e8ccd'}


def picture(size=(640, 640), mode='RGB', fmt='JPEG'):
    from PIL import Image
    out = io.BytesIO()
    Image.new(mode, size, (200, 30, 90) if mode == 'RGB' else None).save(out, fmt)
    return out.getvalue()


class Extras(unittest.TestCase):
    def test_the_card_gets_artist_album_length_position_and_a_picture_mark(self):
        extra = media_extras(SONOS)
        self.assertEqual(extra['artist'], 'KATZROAR')
        self.assertEqual(extra['album'], 'Invocation')
        self.assertEqual(extra['dur'], 270)
        self.assertEqual(extra['pos'], 0)
        self.assertEqual(extra['at'], 1789726189)  # 2026-09-18T10:09:49Z
        self.assertTrue(re.fullmatch(r'[0-9a-f]{10}', extra['pic']))
        # The mark follows the picture and nothing else: a new cache token is a new picture.
        other = media_extras({**SONOS, 'entity_picture': SONOS['entity_picture'].replace('556b49fd9c3e8ccd', '1')})
        self.assertNotEqual(other['pic'], extra['pic'])
        self.assertEqual(media_extras({**SONOS, 'volume_level': 0.5})['pic'], extra['pic'])
        # Home Assistant's access token in the link changes every few minutes while the picture stays (app 0.3.7): the
        # mark does not, so no screen fetches the same cover again.
        picture = SONOS['entity_picture']
        self.assertIn('token=', picture)
        rotated = re.sub(r'token=[^&]*', 'token=0123456789abcdef', picture)
        self.assertNotEqual(rotated, picture)
        self.assertEqual(media_extras({**SONOS, 'entity_picture': rotated})['pic'], extra['pic'])
        self.assertEqual(media_extras({'entity_picture': '/api/media_player_proxy/a?cache=1&token=b'})['pic'],
                         media_extras({'entity_picture': '/api/media_player_proxy/a?cache=1&token=c'})['pic'])
        self.assertNotEqual(media_extras({'entity_picture': '/api/media_player_proxy/a?token=b&cache=1'})['pic'],
                            media_extras({'entity_picture': '/api/media_player_proxy/a?token=b&cache=2'})['pic'])

    def test_a_player_without_a_track_gets_no_extras(self):
        self.assertIsNone(media_extras({'friendly_name': 'Bedroom', 'supported_features': 8321599}))
        self.assertIsNone(media_extras({'media_artist': None, 'media_duration': None, 'media_position_updated_at': None}))
        # A stream: a title, no length, no picture. The card shows an empty bar and no times.
        self.assertIsNone(media_extras({'media_title': 'NPO Radio 2', 'media_content_type': 'channel'}))

    def test_odd_values_stay_away(self):
        extra = media_extras({**SONOS, 'media_duration': -5, 'media_position': float('nan'), 'media_position_updated_at': 'yesterday',
                              'media_artist': '  ', 'entity_picture': 42})
        self.assertNotIn('dur', extra)
        self.assertNotIn('pos', extra)
        self.assertNotIn('at', extra)
        self.assertNotIn('artist', extra)
        self.assertNotIn('pic', extra)
        self.assertEqual(extra['album'], 'Invocation')
        # Long names are cut like every text on a screen; a picture the state names as local counts too.
        extra = media_extras({'media_artist': 'x' * 200, 'entity_picture_local': '/api/media_player_proxy/a?token=b'})
        self.assertEqual(len(extra['artist']), 80)
        self.assertIn('pic', extra)

    def test_the_cover_comes_through_home_assistant_when_it_can(self):
        proxy = '/api/media_player_proxy/media_player.office?token=abc&cache=123'
        # A player whose picture lies elsewhere hands out Home Assistant's proxy beside it: the proxy goes first.
        self.assertEqual(media_cover({'entity_picture': 'https://i.scdn.co/image/x', 'entity_picture_local': proxy}), proxy)
        self.assertEqual(media_cover({'entity_picture': proxy}), proxy)
        self.assertEqual(media_cover({'entity_picture': 'https://example.com/x.jpg', 'entity_picture_local': None}),
                         'https://example.com/x.jpg')
        self.assertEqual(media_cover({'entity_picture': 42}), '')
        # The mark the screen watches follows the same address.
        self.assertEqual(media_extras({'entity_picture': 'https://i.scdn.co/image/x', 'entity_picture_local': proxy})['pic'],
                         media_extras({'entity_picture': proxy})['pic'])

    def test_the_state_message_carries_them_and_stays_small(self):
        states = {'media_player.office': {'state': 'playing', 'attributes': SONOS}}
        tile = {'entity': 'media_player.office', 'name': ''}
        message = state_message(0, tile, states, extras(tile, states))
        self.assertEqual(message['x']['artist'], 'KATZROAR')
        self.assertEqual(message['a']['media_title'], 'Woman at the Loom')
        self.assertLess(len(str(message)), 700)


class Firmware(unittest.TestCase):
    def test_the_firmware_reads_what_the_app_sends(self):
        for key in ('extra["artist"]', 'extra["album"]', 'extra["pic"]', 'extra["dur"]', 'extra["pos"]', 'extra["at"]'):
            self.assertIn(key, TILES, key)
        for field in ('media_artist', 'media_album', 'media_picture', 'media_duration', 'media_position', 'media_position_at'):
            self.assertIn(field, MODEL, field)
            self.assertIn(field, MODEL[MODEL.index('bool empty() const'):], f'{field} counted in Extra::empty')

    def test_the_card_asks_for_a_cover_with_size_and_background(self):
        self.assertIn('"size", "bg"', TILES)
        self.assertIn('view != "cover"', TILES)
        self.assertIn('if (view == "cover")', TILES)
        # The keys of the card and of the tile over the whole page share one action table.
        self.assertIn('inline void media_action(Tile &t,int cmd)', TILES)
        self.assertIn('media_player.volume_mute', TILES)
        # A picture drawn from a download lets it go before another picture loads into the same buffer (the camera after a
        # cover), and comes back from the store, or is asked for again, after (picture_loader.h, firmware 0.52.0).
        self.assertIn('if (slot_key[static_cast<int>(slot)] != key) slot_letgo(slot);', TILES)
        self.assertIn('cover_forget_pictures();', TILES.split('inline void slot_letgo(picture_loader::Slot slot) {', 1)[1].split('\n}\n', 1)[0])

    def test_the_layout_has_no_colour_of_its_own(self):
        self.assertIsNone(re.search(r'0x[0-9A-Fa-f]{6}', CARD))
        self.assertNotIn('lv_', CARD)


class Covers(unittest.TestCase):
    def test_a_media_player_may_ask_for_a_cover_and_a_camera_may_not(self):
        self.assertTrue(camera_feed.cover_supported('media_player.office'))
        self.assertFalse(camera_feed.cover_supported('camera.front_door'))
        self.assertFalse(camera_feed.cover_supported('media_player.Office'))
        self.assertFalse(camera_feed.supported('media_player.office'))
        self.assertEqual(camera_feed.COVER_MIN_FIRMWARE, COVER_MIN_FIRMWARE)
        self.assertTrue(camera_feed.can_show_cover({'board': 'guition', 'firmware': '0.2.64'}))
        self.assertFalse(camera_feed.can_show_cover({'board': 'guition', 'firmware': '0.2.63'}))
        self.assertFalse(camera_feed.can_show_cover({'board': 'cyd', 'firmware': '0.2.64'}))

    def test_the_card_never_asks_for_a_cover_the_app_will_not_serve(self):
        # The card asks for exactly the pixels it draws and the screen draws what comes back one to one, so a square
        # the app refuses is a square that stays empty, silently: cover_request returns None, answer_camera falls
        # through (a media player is no camera) and returns without a word. The two numbers are one number.
        ceiling = int(re.search(r'static int cover_max\(\) \{ return (\d+); \}', CARD)[1])
        self.assertEqual(ceiling, camera_feed.COVER_SIZES[1])
        self.assertIsNone(camera_feed.cover_request({'size': str(ceiling + 1), 'bg': 'E7E7E7'}))
        self.assertIsNotNone(camera_feed.cover_request({'size': str(ceiling), 'bg': 'E7E7E7'}))
        # art_cap takes the smaller of the room and that ceiling; nothing else sizes the cover.
        self.assertIn('std::min(cover_max(), std::max(max_art()', CARD)
        self.assertNotIn('m.max_art(), above,', CARD)

    def test_the_request_names_a_size_and_a_background(self):
        self.assertEqual(camera_feed.cover_request({'size': '160', 'bg': 'E7E7E7'}), (160, 0xE7E7E7))
        self.assertEqual(camera_feed.cover_request({'size': 200, 'bg': '1a1a1a'}), (200, 0x1A1A1A))
        for bad in ({'size': '9999', 'bg': 'FFFFFF'}, {'size': '10', 'bg': 'FFFFFF'}, {'size': '160', 'bg': 'white'},
                    {'size': '160'}, {'bg': 'FFFFFF'}, {'size': 'x', 'bg': 'FFFFFF'}):
            self.assertIsNone(camera_feed.cover_request(bad), bad)

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_the_cover_is_square_at_the_size_asked_with_rounded_corners_over_the_background(self):
        from PIL import Image
        out = camera_feed.encode_cover(picture((640, 640), fmt='PNG'), 160, 0x1A1A1A)
        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual((image.format, image.size, image.mode), ('BMP', (160, 160), 'RGB'))
            self.assertEqual(image.getpixel((0, 0)), (26, 26, 26))       # the corner: the background
            self.assertEqual(image.getpixel((80, 80)), (200, 30, 90))    # the middle: the picture
            self.assertEqual(image.getpixel((0, 80)), (200, 30, 90))     # the edge between the corners: the picture
        # A wide picture is cut to its middle; a PNG with transparency lands on the background.
        with Image.open(io.BytesIO(camera_feed.encode_cover(picture((900, 300)), 48, 0xFFFFFF))) as image:
            self.assertEqual(image.size, (48, 48))
        with Image.open(io.BytesIO(camera_feed.encode_cover(picture((100, 100), 'RGBA', 'PNG'), 48, 0x00FF00))) as image:
            self.assertEqual(image.size, (48, 48))

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_a_cover_is_fetched_when_the_picture_changes_and_served_at_a_link(self):
        pictures = {'media_player.office': '/api/media_player_proxy/media_player.office?token=a&cache=1'}
        fetched = []

        async def fetch_cover(entity):
            fetched.append(pictures[entity])
            return picture((640, 640)) if 'cache=1' in pictures[entity] else picture((300, 300))

        async def scenario():
            feed = camera_feed.CameraFeed(lambda entity: None, fetch_cover=fetch_cover, picture=lambda entity: pictures.get(entity, ''))
            # No picture: no cover, nothing fetched.
            self.assertIsNone(await feed.cover('media_player.bedroom', 160, 0))
            self.assertEqual(fetched, [])
            # The first load fetches; the next load of the same picture serves what it has.
            tag, image = await feed.cover('media_player.office', 160, 0xFFFFFF)
            self.assertEqual(len(fetched), 1)
            self.assertTrue(tag.endswith('-c160-FFFFFF"'))
            again = await feed.cover('media_player.office', 160, 0xFFFFFF)
            self.assertEqual(len(fetched), 1)
            self.assertEqual(again, (tag, image))
            # Another size or background: the same picture, sized again.
            other_tag, other = await feed.cover('media_player.office', 192, 0x1A1A1A)
            self.assertEqual(len(fetched), 1)
            self.assertNotEqual(other_tag, tag)
            self.assertNotEqual(other, image)
            # A new picture in Home Assistant: fetched again on the next load.
            pictures['media_player.office'] = '/api/media_player_proxy/media_player.office?token=a&cache=2'
            new_tag, _ = await feed.cover('media_player.office', 160, 0xFFFFFF)
            self.assertEqual(len(fetched), 2)
            self.assertNotEqual(new_tag, tag)
            # The link: a screen loads it, and the link answers with the cover of this moment.
            token = feed.link('media_player.office', (160, 160), cover=(160, 0xFFFFFF))
            status, body, etag = await feed.serve(token)
            self.assertEqual((status, etag), (200, new_tag))
            self.assertEqual(body[:2], b'BM')
            self.assertEqual((await feed.serve(token, etag))[0], 304)
            # A player whose picture went away: no cover.
            pictures['media_player.office'] = ''
            self.assertIsNone(await feed.cover('media_player.office', 160, 0xFFFFFF))
            self.assertEqual((await feed.serve(token))[0], 503)

        asyncio.run(scenario())

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_a_failing_fetch_gives_no_cover(self):
        async def failing(entity):
            raise ConnectionError('gone')

        async def scenario():
            feed = camera_feed.CameraFeed(lambda entity: None, fetch_cover=failing, picture=lambda entity: '/api/x')
            self.assertIsNone(await feed.cover('media_player.office', 160, 0))
            self.assertEqual(feed.watches['media_player.office'].failures, 1)

        asyncio.run(scenario())


@unittest.skipUnless(HAS_AIOHTTP and HAS_PIL, 'aiohttp and Pillow')
class Answer(unittest.TestCase):
    """The app's answer to a screen's request, through Manager.answer_camera with a Home Assistant stand-in."""

    def setUp(self):
        # base_url keeps the last address for ten minutes; another test's Home Assistant may have left one behind.
        camera_feed.base_url.__defaults__[0].clear()

    class HA:
        online = True

        def __init__(self, firmware='0.2.64', guition=True):
            self.registry = [{'entity_id': 'text.hall_tile_settings', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                             {'entity_id': 'sensor.hall_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                             {'entity_id': 'sensor.hall_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'}]
            if guition:
                self.registry.append({'entity_id': 'select.hall_type', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': 'd1'})
            self.devices, self.areas = [{'id': 'd1', 'name': 'Hall'}], []
            self.states = {'text.hall_tile_settings': {'state': 'Synced'}, 'sensor.hall_node': {'state': 'hall'}, 'sensor.hall_fw': {'state': firmware},
                           'media_player.office': {'state': 'playing', 'attributes': SONOS},
                           'media_player.radio': {'state': 'playing', 'attributes': {'media_title': 'Radio 2', 'supported_features': 8321599}}}
            self.sent, self.responses, self.time_zone, self.changed = [], set(), None, asyncio.Event()

        async def send(self, inbox, message, action=None, respond=False):
            self.sent.append((inbox, message))

        async def request(self, kind, **data):
            return {'adapters': [{'default': True, 'ipv4': [{'address': '192.168.1.5'}]}]} if kind == 'network' else {}

        def media_picture(self, entity):
            attrs = self.states.get(entity, {}).get('attributes', {})
            return attrs.get('entity_picture') or ''

        async def media_image(self, entity):
            return picture()

    def manager(self, ha):
        import tempfile
        manager = Manager(with_screen_grid(ha), Path(tempfile.mkdtemp()) / 'screens.json')
        manager.save('text.hall_tile_settings', {'title': 'Hall', 'tiles': [{'entity': 'media_player.office', 'name': ''}, {'entity': 'media_player.radio', 'name': ''}]})
        return manager

    def test_a_guition_card_gets_a_link_a_stream_an_empty_one_and_a_stranger_nothing(self):
        ha = self.HA()
        manager = self.manager(ha)

        async def scenario():
            await manager.answer_camera({'inbox': 'text.hall_tile_settings', 'entity': 'media_player.office', 'size': '160', 'bg': 'E7E7E7'})
            self.assertEqual(len(ha.sent), 1)
            message = ha.sent[0][1]
            self.assertEqual((message['op'], message['t'], message['e']), ('camera', 'cover', 'media_player.office'))
            self.assertTrue(message['u'].startswith('http://192.168.1.5:') and message['u'].endswith('.bmp'))
            token = message['u'].rsplit('/', 1)[1][:-4]
            status, body, _ = await manager.camera.serve(token)
            self.assertEqual(status, 200)
            from PIL import Image
            with Image.open(io.BytesIO(body)) as image:
                self.assertEqual(image.size, (160, 160))
                self.assertEqual(image.getpixel((0, 0)), (0xE7, 0xE7, 0xE7))
            # A stream without a picture: an empty link, so the card keeps its placeholder and stops asking.
            await manager.answer_camera({'inbox': 'text.hall_tile_settings', 'entity': 'media_player.radio', 'size': '160', 'bg': 'E7E7E7'})
            self.assertEqual(ha.sent[1][1], {'v': 1, 'op': 'camera', 't': 'cover', 'e': 'media_player.radio', 'u': ''})
            # A player that is not on the screen's layout, a size out of range, a request without a size: no answer.
            for request in ({'inbox': 'text.hall_tile_settings', 'entity': 'media_player.other', 'size': '160', 'bg': 'E7E7E7'},
                            {'inbox': 'text.hall_tile_settings', 'entity': 'media_player.office', 'size': '2000', 'bg': 'E7E7E7'},
                            {'inbox': 'text.hall_tile_settings', 'entity': 'media_player.office'}):
                await manager.answer_camera(request)
            self.assertEqual(len(ha.sent), 2)

        asyncio.run(scenario())

    def test_older_firmware_and_a_cyd_get_no_cover(self):
        for ha in (self.HA(firmware='0.2.63'), self.HA(guition=False)):
            manager = self.manager(ha)
            asyncio.run(manager.answer_camera({'inbox': 'text.hall_tile_settings', 'entity': 'media_player.office', 'size': '160', 'bg': 'E7E7E7'}))
            self.assertEqual(ha.sent, [])


if __name__ == '__main__':
    unittest.main()
