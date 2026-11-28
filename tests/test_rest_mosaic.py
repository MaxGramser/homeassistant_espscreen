"""A player at rest shows its library (rest_mosaic.py): the covers of a folder as a mosaic over its cover tile.

- Only a player's `cover` tile whose picture fills the card (two rows or more), only while it has nothing to show (no
  song and no picture of its own), and only to a screen that draws the player's extras.
- The folder is the first of the library's top that holds songs, else albums, else playlists; each picture once.
- The covers stay square and one size, two along the card's shorter side, and what reaches past the card is cut off,
  never squeezed; the mosaic is darkened as much as the screen asks for a cover.
- Every turn one cover moves on to the next of the folder, the one longest on the card goes, and none shows twice.
The shapes are what Home Assistant 2026.10's Spotify integration answers.
"""
from manager_fixtures import with_screen_grid, seed_layout
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import media_library  # noqa: E402
import rest_mosaic  # noqa: E402
from core import validate_layout  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import lan_address
    from server import Manager

PLAYER = 'media_player.spotify'
AT_REST = 2048     # SELECT_SOURCE alone: what Spotify reports while it plays nowhere
FOLDERS = (('Playlists', 'playlist', 'current_user_playlists'), ('Artists', 'artist', 'current_user_followed_artists'),
           ('Albums', 'album', 'current_user_saved_albums'), ('Liked songs', 'track', 'current_user_saved_tracks'),
           ('Podcasts', 'podcast', 'current_user_saved_shows'), ('Recently played', 'track', 'current_user_recently_played'))
TOP = {'title': 'Media Library', 'media_class': 'directory', 'media_content_type': 'spotify://library', 'media_content_id': 'library',
       'can_play': False, 'can_expand': True, 'children': [
           {'title': name, 'media_class': 'directory', 'children_media_class': kind, 'media_content_type': f'spotify://{key}',
            'media_content_id': key, 'can_play': key == 'current_user_saved_tracks', 'can_expand': True, 'thumbnail': None}
           for name, kind, key in FOLDERS]}
# Twelve liked songs of nine albums: three albums twice.
ALBUMS = [0, 1, 2, 0, 3, 4, 5, 1, 6, 7, 2, 8]
LIKED = {'title': 'Liked songs', 'media_class': 'directory', 'children': [
    {'title': f'Song {n}', 'media_class': 'track', 'media_content_type': 'spotify://track', 'media_content_id': f'spotify:track:{n}',
     'can_play': True, 'can_expand': False, 'thumbnail': f'https://i.scdn.co/image/album{album}'} for n, album in enumerate(ALBUMS)]}
COLOURS = [(230, 40, 40), (40, 200, 60), (40, 80, 230), (240, 220, 40), (200, 40, 220), (40, 220, 220), (250, 140, 30),
           (120, 70, 30), (250, 250, 250)]


def picture(colour, size=(64, 64), right=None):
    """A picture of one colour, or of two halves side by side."""
    from PIL import Image
    image = Image.new('RGB', size, colour)
    if right:
        image.paste(Image.new('RGB', (size[0] // 2, size[1]), right), (size[0] // 2, 0))
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def top():
    return media_library.folder_of(TOP)


class TheTile(unittest.TestCase):
    def test_every_cover_tile_whose_picture_fills_the_card(self):
        # The cover fills the card on every size (one row too, since the picture system), so every cover tile has one.
        for options, wanted in (({'display': 'cover', 'size': 'tall'}, True), ({'display': 'cover', 'size': 'square'}, True),
                                ({'display': 'cover', 'size': '3x2'}, True), ({'display': 'cover', 'size': 'wide'}, True),
                                ({'display': 'cover'}, True), ({'display': 'favorite', 'size': 'square'}, False),
                                ({'size': 'square'}, False), (None, False)):
            self.assertEqual(rest_mosaic.wants(options), wanted, options)

    def test_one_row_of_covers_on_a_card_of_one_row(self):
        for options, rows in (({'display': 'cover', 'size': 'wide'}, 1), ({'display': 'cover'}, 1),
                              ({'display': 'cover', 'size': '3x1'}, 1), ({'display': 'cover', 'size': 'tall'}, 2),
                              ({'display': 'cover', 'size': 'square'}, 2), ({'display': 'cover', 'size': '3x2'}, 2), (None, 1)):
            self.assertEqual(rest_mosaic.rows_for(options), rows, options)

    def test_at_rest_is_nothing_to_show(self):
        cover = '/api/media_player_proxy/media_player.spotify?token=x&cache=1'
        for state, rest in ((('idle', {}), True), (('off', {}), True), (('on', {}), True), (('standby', {}), True),
                            (('paused', {}), True), (('paused', {'media_title': 'Dreams'}), False),
                            (('paused', {'entity_picture': cover}), False), (('playing', {}), False),
                            (('buffering', {}), False), (('unavailable', {}), False), (('idle', {'entity_picture': cover}), False)):
            self.assertEqual(rest_mosaic.at_rest({'state': state[0], 'attributes': state[1]}), rest, state)
        self.assertFalse(rest_mosaic.at_rest(None))


class TheFolder(unittest.TestCase):
    def test_the_first_folder_of_songs(self):
        self.assertEqual(rest_mosaic.folder_for(top())['title'], 'Liked songs')

    def test_else_albums_then_playlists_then_the_top_itself(self):
        def without(*kinds):
            return media_library.folder_of({**TOP, 'children': [c for c in TOP['children'] if c['children_media_class'] not in kinds]})
        self.assertEqual(rest_mosaic.folder_for(without('track'))['title'], 'Albums')
        self.assertEqual(rest_mosaic.folder_for(without('track', 'album'))['title'], 'Playlists')
        self.assertIsNone(rest_mosaic.folder_for(without('track', 'album', 'playlist')))
        # Music Assistant's top, as its media browser names it.
        music_assistant = media_library.folder_of({'title': 'Music Library', 'children': [
            {'title': title, 'media_class': 'directory', 'children_media_class': kind, 'media_content_type': 'music',
             'media_content_id': key, 'can_play': False, 'can_expand': True}
            for title, kind, key in (('Artists', 'artist', 'artists'), ('Albums', 'album', 'albums'), ('Tracks', 'track', 'tracks'))]})
        self.assertEqual(rest_mosaic.folder_for(music_assistant)['title'], 'Tracks')

    def test_each_picture_once_and_enough_of_them(self):
        pool = rest_mosaic.pool_of(media_library.folder_of(LIKED))
        self.assertEqual([thumb[-6:] for thumb, _ in pool], [f'album{n}' for n in range(9)])
        self.assertEqual(pool[0][1], 'Song 0')
        few = {**LIKED, 'children': LIKED['children'][:4]}
        self.assertEqual(rest_mosaic.pool_of(media_library.folder_of(few)), [], 'three covers are no mosaic')
        self.assertEqual(rest_mosaic.pool_of(top()), [], 'folders without pictures')


class TheMosaic(unittest.TestCase):
    def test_square_covers_that_cover_the_card(self):
        for width, height in ((448, 268), (218, 268), (495, 288), (383, 207), (187, 207), (700, 300), (120, 120)):
            columns, rows, side, left, top_ = rest_mosaic.grid_of(width, height)
            self.assertEqual(side, min(width, height) // 2)
            self.assertGreaterEqual(columns * side, width)
            self.assertGreaterEqual(rows * side, height)
            self.assertLess((columns - 1) * side, width)
            self.assertLess((rows - 1) * side, height)
            # Cut off evenly at both ends.
            self.assertLessEqual(abs((columns * side - width) - 2 * left), 1)
            self.assertLessEqual(abs((rows * side - height) - 2 * top_), 1)
        self.assertEqual(rest_mosaic.grid_of(448, 268)[:2], (4, 2))
        self.assertEqual(rest_mosaic.grid_of(218, 268)[:2], (2, 3))
        # A card of one row: one strip of covers as high as the card, cut off evenly at both ends.
        columns, rows, side, left, top_ = rest_mosaic.grid_of(456, 130, 1)
        self.assertEqual((columns, rows, side, top_), (4, 1, 130, 0))
        self.assertLessEqual(abs((columns * side - 456) - 2 * left), 1)
        strip = rest_mosaic.draw([picture((250, 0, 0))], 456, 130, 1)
        self.assertEqual(strip.size, (456, 130))

    def test_one_cover_moves_on_at_a_time_and_none_shows_twice(self):
        for cells in range(1, 13):
            for count in range(cells + 1, cells + 20):
                before = None
                for step in range(3 * count):
                    now = rest_mosaic.shown(count, cells, step)
                    self.assertEqual(sorted(now), sorted((step + n) % count for n in range(cells)), (cells, count, step))
                    if before is not None:
                        self.assertEqual(sum(a != b for a, b in zip(now, before)), 1, (cells, count, step))
                    before = now

    def test_a_small_folder_keeps_still(self):
        self.assertEqual(rest_mosaic.shown(5, 8, 0), rest_mosaic.shown(5, 8, 41))
        self.assertEqual(set(rest_mosaic.shown(5, 8, 0)), set(range(5)))

    def test_the_mark_changes_with_the_turn_and_the_folder(self):
        pool = [(f'https://i.scdn.co/image/{n}', '') for n in range(6)]
        marks = {rest_mosaic.mark(pool, 7), rest_mosaic.mark(pool, 8), rest_mosaic.mark(pool[1:], 7)}
        self.assertEqual(len(marks), 3)
        self.assertTrue(all(len(m) <= 16 for m in marks), 'the screen keeps 16 characters of a mark')
        self.assertEqual(rest_mosaic.step_at(119.0), rest_mosaic.step_at(61.0))
        self.assertNotEqual(rest_mosaic.step_at(120.0), rest_mosaic.step_at(119.0))

    @unittest.skipUnless(HAS_PIL, 'Pillow')
    def test_covers_keep_their_shape(self):
        # A wide picture of two halves: cut square from its middle, so every cell is half red, half blue, split in
        # its own middle, never a squeezed whole.
        wide = picture((230, 30, 30), (200, 100), right=(30, 30, 230))
        image = rest_mosaic.draw([wide], 448, 268)
        self.assertEqual(image.size, (448, 268))
        columns, rows, side, left, top_ = rest_mosaic.grid_of(448, 268)
        y = side // 2 - top_
        for c in range(columns):
            middle = c * side + side // 2 - left
            for x, red in ((middle - side // 4, True), (middle + side // 4, False)):
                if 0 <= x < 448:
                    r, _, b = image.getpixel((x, y))
                    self.assertEqual(r > b, red, (c, x))
        # A picture that did not come leaves its cell dark; none at all, a dark card.
        gaps = rest_mosaic.draw([picture((250, 250, 250)), None], 448, 268)
        self.assertEqual(gaps.getpixel((side + side // 2 - left, side // 2 - top_)), (0, 0, 0))


@unittest.skipUnless(HAS_AIOHTTP and HAS_PIL, 'aiohttp and Pillow')
class TheApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        lan_address.base_url.__defaults__[0].clear()

    def ha(self, refuse=False):
        class HA:
            online = True

            def __init__(self):
                self.registry = [{'entity_id': 'text.d1_tiles', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_node', 'platform': 'esphome', 'original_name': 'Device name', 'device_id': 'd1'},
                                 {'entity_id': 'sensor.d1_fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd1'},
                                 {'entity_id': 'select.d1_type', 'platform': 'esphome', 'original_name': 'Guition screen type', 'device_id': 'd1'}]
                self.devices, self.areas = [{'id': 'd1', 'name': 'Hall'}], []
                self.states = {'text.d1_tiles': {'state': 'Synced'}, 'sensor.d1_node': {'state': 'hall'}, 'sensor.d1_fw': {'state': '0.60.0'},
                               PLAYER: {'state': 'idle', 'attributes': {'friendly_name': 'Spotify', 'supported_features': AT_REST,
                                                                        'source_list': ['Kitchen']}}}
                self.changed, self.dirty, self.log, self.responses = asyncio.Event(), set(), [], set()

            async def send(self, inbox, message, action=None, respond=False):
                self.log.append(('send', inbox, dict(message)))

            async def call_answer(self, domain, service, data):
                self.log.append(('answer', service, data.get('media_content_id')))
                return {PLAYER: LIKED if data.get('media_content_id') == 'current_user_saved_tracks' else TOP}

            async def call_service(self, domain, service, data):
                self.log.append(('call', service, data))

            async def browse_image(self, entity, url):
                self.log.append(('thumbnail', url))
                if refuse:
                    raise ValueError('unsafe picture address')
                return picture(COLOURS[int(url.rsplit('album', 1)[1])])

            async def request(self, kind, **data):
                if kind == 'network':
                    return {'adapters': [{'name': 'end0', 'default': True, 'ipv4': [{'address': '192.168.1.57'}]}]}
                raise ConnectionError(kind)
        return HA()

    def manager(self, ha, tmp, size='square'):
        m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
        seed_layout(m, 'text.d1_tiles', validate_layout({'title': 'Music', 'tiles': [
            {'entity': PLAYER, 'name': 'Spotify', 'options': {'display': 'cover', 'size': size}}]}))
        return m

    async def message(self, m, rounds=1):
        """The tile's message, after `rounds` passes: the app asks once whether the library opens, and once it does reads
        its folder, each time drawing the player again (ha.dirty) as the pass after it would."""
        tile = m.layouts['text.d1_tiles']['tiles'][0]
        for _ in range(rounds):
            found = await m.tile_message(0, tile, features=frozenset({media_library.FEATURE}))
            for _ in range(20):
                await asyncio.sleep(0.01)
        return found

    async def strip(self, m, ha, frame=(448, 268)):
        """The tile's picture as the screen asks for it: its frame, the shade it asks for over a cover."""
        ha.log.clear()
        with self.assertLogs('screen_manager', 'INFO'):
            await m.answer_camera({'inbox': 'text.d1_tiles', 'tiles': PLAYER, 'idx': '0', 'size': '54', 'bg': 'E7E7E7',
                                   'atlas': json.dumps([[0, 0, frame[0], frame[1], 14, 170]])})
        (sent,) = [entry[2] for entry in ha.log if entry[0] == 'send']
        if not sent['u']:
            return None
        status, raw, _, _ = await m.links.serve(sent['u'].rsplit('/', 1)[1][:-4])
        self.assertEqual(status, 200)
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            return image.convert('RGB')

    async def test_a_player_at_rest_shows_its_liked_songs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            m = self.manager(ha, tmp)
            first = await self.message(m, 2)
            self.assertNotIn('pic', first.get('x', {}), 'nothing until its folder is read')
            self.assertIn(('answer', 'browse_media', 'current_user_saved_tracks'), ha.log)
            self.assertIn(PLAYER, ha.dirty, 'the covers that came draw the player again')
            # At the first turn the newest song's cover stands at the top left.
            with mock.patch('time.time', return_value=0.0):
                message = await self.message(m)
                image = await self.strip(m, ha)
            self.assertTrue(message['x']['pic'].startswith('rest'))
            self.assertEqual(image.size, (448, 268))
            # Four covers along, two down; darkened as the screen asks (170 of 255).
            red = image.getpixel((134 // 2 - 44, 30))
            self.assertGreater(red[0], 2 * red[1])
            self.assertLess(red[0], 120, 'darkened')
            thumbnails = [entry[1] for entry in ha.log if entry[0] == 'thumbnail']
            self.assertEqual(len(thumbnails), len(set(thumbnails)), 'each picture fetched once')

    async def test_one_cover_moves_on_every_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            m = self.manager(ha, tmp)
            await self.message(m, 2)
            now = 1_000_000 * rest_mosaic.ROTATE_SECONDS
            with mock.patch('time.time', return_value=now):
                m.rest_turn(set())
                before = (await self.message(m))['x']['pic']
                image = await self.strip(m, ha)
                dirty = m.rest_turn(set())
            with mock.patch('time.time', return_value=now + rest_mosaic.ROTATE_SECONDS):
                self.assertEqual(m.rest_turn(set()), {PLAYER}, 'the turn draws the player again')
                after = (await self.message(m))['x']['pic']
                later = await self.strip(m, ha)
            self.assertNotEqual(before, after)
            self.assertEqual(dirty, set(), 'the same turn draws nothing again')
            cells = [(x, y) for x in (20, 150, 280, 410) for y in (60, 200)]
            moved = sum(image.getpixel(cell) != later.getpixel(cell) for cell in cells)
            self.assertEqual(moved, 1, 'one cover moved on')

    async def test_what_plays_shows_its_own_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            m = self.manager(ha, tmp)
            self.assertTrue((await self.message(m, 3))['x']['pic'].startswith('rest'))
            ha.states[PLAYER] = {'state': 'playing', 'attributes': {
                'friendly_name': 'Spotify', 'supported_features': 444983, 'media_title': 'Dreams',
                'entity_picture': '/api/media_player_proxy/media_player.spotify?token=x&cache=dreams'}}
            message = await self.message(m)
            self.assertFalse(message['x']['pic'].startswith('rest'), 'the cover of what plays, not the library')

    async def test_a_card_of_one_row_too_and_no_mosaic_where_it_is_not_drawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha()
            # A cover fills a card of one row too (the picture system): its library comes as a strip of covers.
            m = self.manager(ha, tmp, size='wide')
            await self.message(m, 2)
            self.assertTrue((await self.message(m)).get('x', {}).get('pic', '').startswith('rest'))
            self.assertTrue(any(entry[0] == 'answer' and entry[2] == 'current_user_saved_tracks' for entry in ha.log))
            m = self.manager(ha, tmp)
            tile = m.layouts['text.d1_tiles']['tiles'][0]
            old = await m.tile_message(0, tile, features=frozenset())
            self.assertNotIn('pic', old.get('x', {}), 'an older screen gets what it got before')

    async def test_a_library_whose_pictures_do_not_come_keeps_the_tile(self):
        with tempfile.TemporaryDirectory() as tmp:
            ha = self.ha(refuse=True)
            m = self.manager(ha, tmp)
            await self.message(m, 2)
            self.assertNotIn('pic', (await self.message(m)).get('x', {}))
            self.assertEqual(m.rest_pools[PLAYER][1], [])


if __name__ == '__main__':
    unittest.main()
