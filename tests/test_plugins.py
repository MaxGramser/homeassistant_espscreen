"""Plugins (docs/PLUGINS.md): the manifest check, the map language, fetch's rules, the plugins file, a plugin tile in a
layout, and one plugin API version in the firmware, the component and the add-on."""
import asyncio
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import core  # noqa: E402
from build_queue import BuildQueue  # noqa: E402
import page_layout  # noqa: E402
import plugin_fetch  # noqa: E402
import plugin_manifest as pm  # noqa: E402
import plugin_pictures  # noqa: E402
import tile_art  # noqa: E402
from firmware import Firmware  # noqa: E402
from page_delivery import plugins_of  # noqa: E402

ENGLISH = {'app': {'name': 'Bus', 'summary': 'Next bus.', 'tile': 'Next', 'stop': 'Stop', 'line': 'Line',
                   'walk': 'Walk', 'key': 'Key'}, 'screen': {'now': 'now'}}


def manifest(**changes):
    data = {
        'id': 'bus', 'version': '1.0.0', 'api': '0.4', 'icon': 'bus', 'maintainer': 'someone', 'license': 'MIT', 'topics': ['travel'],
        'permissions': {'network': ['api.example.org']}, 'attributes': ['cloud'], 'privacy': 'https://example.org/p',
        'tiles': [{'id': 'next', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900,
                   'data': 'departures', 'options': [
                       {'id': 'stop', 'kind': 'text', 'label': 'stop'},
                       {'id': 'line', 'kind': 'choice', 'options_from': 'lines', 'label': 'line'},
                       {'id': 'walk', 'kind': 'number', 'min': 0, 'max': 20, 'default': 3, 'label': 'walk'}]}],
        'fetch': [
            {'id': 'departures', 'url': 'https://api.example.org/stops/{stop}', 'every': '60s',
             'map': {'items': '$.{stop}.passes[*]', 'fields': {'line': 'line', 'at': {'path': 'when', 'as': 'epoch'}},
                     'where': {'line': '{line}'}, 'sort': 'at', 'limit': 2}},
            {'id': 'lines', 'url': 'https://api.example.org/stops/{stop}', 'every': '1h',
             'map': {'items': '$.{stop}.passes[*]', 'value': 'line', 'label': ['line', 'to']}}],
    }
    data.update(changes)
    return data


class Manifest(unittest.TestCase):
    def test_a_complete_manifest_passes(self):
        out = pm.check(manifest(), ENGLISH)
        self.assertEqual(out['tiles'][0]['options'][2]['default'], 3)
        self.assertEqual(out['fetch'][0]['every'], 60)
        self.assertEqual(out['fetch'][0]['placeholders'], ['stop'])

    def test_the_real_plugins_pass(self):
        plugins = ROOT.parent / 'tessera-plugins'
        for folder in [*(plugins / 'plugins').glob('*'), plugins / 'template', *(ROOT / 'tests' / 'fixtures' / 'plugins').glob('*')]:
            if (folder / 'tessera-plugin.yaml').is_file():
                import yaml
                with self.subTest(folder.name):
                    pm.check(yaml.safe_load((folder / 'tessera-plugin.yaml').read_text()),
                             json.loads((folder / 'translations' / 'en.json').read_text()))

    def test_a_new_kind_of_right_does_not_ask_everyone_again(self):
        import hashlib
        out = pm.check(manifest(), ENGLISH)
        # The fingerprint as plugin API 0.1 made it, before ha_commands existed: an installed plugin keeps its consent.
        before = {'permissions': {'read_entities': [], 'home_assistant_actions': [], 'network': ['api.example.org']},
                  'attributes': ['cloud']}
        self.assertEqual(pm.permission_hash(out), hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()[:16])
        asking = pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']}), ENGLISH)
        self.assertNotEqual(pm.permission_hash(asking), pm.permission_hash(out))

    def test_a_preview_names_fields_of_its_data(self):
        def with_preview(preview):
            data = manifest()
            data['tiles'][0]['preview'] = preview
            return data
        self.assertEqual(pm.check(with_preview({'badge': '{line}', 'countdown': 'at'}), ENGLISH)['tiles'][0]['preview'],
                         {'badge': '{line}', 'countdown': 'at'})
        for wrong in ({'title': '{nowhere}'}, {'countdown': 'line'}, {'value': '{line}', 'countdown': 'at'}, {'colour': 'x'}):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                pm.check(with_preview(wrong), ENGLISH)

    def test_stage_is_the_makers_word_and_beta_without_one(self):
        self.assertEqual(pm.check(manifest(), ENGLISH)['stage'], 'beta')
        for stage in pm.STAGES:
            with self.subTest(stage):
                self.assertEqual(pm.check(manifest(stage=stage), ENGLISH)['stage'], stage)

    def test_mistakes_say_where(self):
        cases = [
            (manifest(colour='red'), 'unknown field'),
            (manifest(api='1'), 'api'),
            (manifest(id='Bus'), 'id'),
            (manifest(license='Proprietary'), 'license'),
            (manifest(privacy=None, attributes=['cloud']), 'privacy'),
            (manifest(attributes=[]), 'cloud'),
            (manifest(attributes=['cloud', 'experimental']), 'attributes'),
            (manifest(stage='test'), 'stage'),
            (manifest(permissions={'network': ['192.168.1.2']}), 'public host'),
            (manifest(permissions={'network': ['router.local']}), 'public host'),
        ]
        bad_fetch = manifest()
        bad_fetch['fetch'][0]['url'] = 'https://other.example.org/x'
        cases.append((bad_fetch, 'permissions.network'))
        often = manifest()
        often['fetch'][0]['every'] = '5s'
        cases.append((often, '30s'))
        secret_in_path = manifest(inputs=[{'id': 'key', 'kind': 'secret', 'label': 'key'}])
        secret_in_path['fetch'][0]['url'] = 'https://api.example.org/{key}/stops/{stop}'
        cases.append((secret_in_path, 'never in the path'))
        secret_over_http = manifest(inputs=[{'id': 'key', 'kind': 'secret', 'label': 'key'}])
        secret_over_http['fetch'][0]['url'] = 'http://api.example.org/stops/{stop}?key={key}'
        cases.append((secret_over_http, 'https'))
        unknown = manifest()
        unknown['fetch'][0]['url'] = 'https://api.example.org/stops/{nope}'
        cases.append((unknown, '{nope}'))
        for data, words in cases:
            with self.subTest(words):
                with self.assertRaises(pm.ManifestError) as caught:
                    pm.check(data, ENGLISH)
                self.assertIn(words, str(caught.exception))

    def test_every_text_is_in_english(self):
        english = {'app': dict(ENGLISH['app']), 'screen': {}}
        del english['app']['walk']
        with self.assertRaises(pm.ManifestError) as caught:
            pm.check(manifest(), english)
        self.assertIn('walk', str(caught.exception))

    def test_api_versions(self):
        self.assertTrue(pm.api_fits('0.1', (0, 1)))
        self.assertTrue(pm.api_fits('0.1', (0, 2)))    # something new raises the minor and breaks nothing
        self.assertFalse(pm.api_fits('0.3', (0, 2)))   # a plugin that needs a newer core says so
        self.assertTrue(pm.api_fits('1.1', (1, 3)))
        self.assertFalse(pm.api_fits('1.4', (1, 3)))
        self.assertFalse(pm.api_fits('2.0', (1, 3)))
        # While the major is 0 a minor may change a name: a plugin written before it does not fit what comes after.
        self.assertFalse(pm.api_fits('0.3', (0, 8)))
        self.assertTrue(pm.api_fits('0.4', (0, 8)))
        self.assertTrue(pm.api_fits('0.7', (0, 8)))
        self.assertFalse(pm.api_fits('0.2', (0, 5), {0: (3,)}))
        self.assertTrue(pm.api_fits('0.2', (0, 2), {0: (3,)}))

    def test_one_plugin_api_everywhere(self):
        header = (ROOT / 'components/smart_display/plugin_api.h').read_text()
        major, minor = re.search(r'PLUGIN_API_MAJOR = (\d+), PLUGIN_API_MINOR = (\d+)', header).groups()
        component = (ROOT / 'components/smart_display/__init__.py').read_text()
        self.assertIn(f'PLUGIN_API = ({major}, {minor})', component)
        self.assertEqual(pm.PLUGIN_API, (int(major), int(minor)))
        self.assertIn(f'PLUGIN_API_BREAKS = {pm.PLUGIN_API_BREAKS!r}', component)
        # The docs name the same number, once, and the host probe is written for it: it uses the newest moments.
        doc = (ROOT / 'docs/PLUGINS.md').read_text()
        self.assertEqual(re.findall(r'the plugin API is (\d+\.\d+) now', doc), [f'{major}.{minor}'])
        import yaml
        probe = yaml.safe_load((ROOT / 'tests/fixtures/plugins/host_probe/tessera-plugin.yaml').read_text())
        self.assertEqual(probe['api'], f'{major}.{minor}')

    def test_a_tile_may_have_places_for_pictures(self):
        """`pictures` (0.10): how many places a tile has at most, 0 without; the screen asks for as many at most."""
        self.assertEqual(pm.check(manifest(), ENGLISH)['tiles'][0]['pictures'], 0)
        tiles = manifest()['tiles']
        tiles[0]['pictures'] = 8
        self.assertEqual(pm.check(manifest(tiles=tiles), ENGLISH)['tiles'][0]['pictures'], 8)
        for bad in (9, -1, 'two', 2.5, True):
            tiles[0]['pictures'] = bad
            with self.assertRaises(pm.ManifestError) as caught:
                pm.check(manifest(tiles=tiles), ENGLISH)
            self.assertIn('tiles[0].pictures', str(caught.exception))
        header = (ROOT / 'components/smart_display/tile_picture.h').read_text()
        self.assertIn(f'constexpr size_t MAX_PARTS = {pm.MAX_PICTURES};', header)

    def test_the_two_ticks_have_two_names(self):
        """A plugin's 250 ms moment with millis() is on_interval; on_tick is a tile's or a card's second with the clock."""
        header = (ROOT / 'components/smart_display/plugin_api.h').read_text()
        plugin = header[header.index('class Plugin {'):header.index('// The register.')]
        self.assertIn('virtual void on_interval(uint32_t now_ms)', plugin)
        self.assertNotIn('void on_tick', plugin)

    def test_placeholder_price_is_the_screens(self):
        host = (ROOT / 'components/smart_display/plugin_host.h').read_text()
        self.assertIn(f'PLACEHOLDER_BYTES = {core.PLUGIN_PLACEHOLDER_BYTES};', host)


class Pictures(unittest.IsolatedAsyncioTestCase):
    """The pictures of a plugin tile (plugin API 0.10, plugin_pictures): the question as the screen asks it, where a
    picture may come from, and a cache by address."""
    ATLAS = '[[0,0,60,90,6,0],[70,0,60,90,6,0]]'
    SRC = '["https://api.example.org/a.jpg","https://api.example.org/b.jpg"]'

    def question(self, **changes):
        request = {'tiles': 'plugin:bus.next', 'idx': '3', 'bg': '202020', 'dark': '1', 'atlas': self.ATLAS, 'src': self.SRC,
                   'fit': '["cover","contain"]'}
        request.update(changes)
        return plugin_pictures.parse(request, (480, 480))

    def test_the_question_names_the_tile_its_frames_and_their_addresses(self):
        q = self.question()
        self.assertEqual((q.entity, q.plugin, q.tile, q.index, q.ground, q.dark), ('plugin:bus.next', 'bus', 'next', 3, 0x202020, True))
        self.assertEqual(q.atlas, (130, 90, ((0, 0, 60, 90, 6, 0), (70, 0, 60, 90, 6, 0))))
        self.assertEqual(q.sources, ['https://api.example.org/a.jpg', 'https://api.example.org/b.jpg'])
        self.assertEqual(q.fits, ['cover', 'contain'])
        self.assertEqual(self.question(fit=None).fits, ['cover', 'cover'])   # cover without a word
        for bad in (dict(tiles='camera.front'), dict(idx='x'), dict(bg='red'), dict(src='["one"]'), dict(src='[1,2]'),
                    dict(fit='["cover"]'), dict(fit='["fill","cover"]'), dict(atlas='[[0,0,60,90,6,0]]'), dict(src='[]'),
                    dict(src='[' + ','.join(['"https://api.example.org/x.jpg"'] * 9) + ']'), dict(atlas='[[0,0,600,90,6,0],[70,0,60,90,6,0]]')):
            self.assertIsNone(self.question(**bad), bad)

    def test_places_may_overlap_turn_and_mirror(self):
        """The places of one card are its layers (0.10): their frames may overlap, each may turn and have a reflection."""
        q = self.question(atlas='[[0,0,60,90,6,0],[40,0,60,90,6,0]]', turn='["right",""]', mirror='[0,1]')
        self.assertEqual((q.turns, q.mirrors), (['right', ''], [False, True]))
        self.assertEqual(q.styles(), [('fill', 'right', False), ('within', '', True)])
        self.assertEqual(self.question().turns, ['', ''])   # a flat card asks without them
        for bad in (dict(turn='["up",""]'), dict(turn='["left"]'), dict(mirror='[2,0]'), dict(mirror='{}'), dict(turn='x')):
            self.assertIsNone(self.question(**bad), bad)
        # Covers of different tiles still never overlap.
        self.assertIsNone(tile_art.parse('[[0,0,60,90,6,0],[40,0,60,90,6,0]]', (480, 480), 2))

    def test_the_reflection_is_the_screens_share(self):
        header = (ROOT / 'components/smart_display/plugin_api.h').read_text()
        self.assertIn(f'constexpr int MIRROR_PERCENT = {tile_art.MIRROR_PERCENT};', header)

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'Pillow')
    def test_layers_overlap_turn_and_mirror(self):
        from PIL import Image
        import io
        def picture(colour):
            raw = io.BytesIO()
            Image.new('RGB', (100, 150), colour).save(raw, 'PNG')
            return raw.getvalue()
        red, blue = picture((255, 0, 0)), picture((0, 0, 255))
        atlas = tile_art.parse('[[0,0,60,90,8,0],[40,0,60,117,8,0]]', (480, 480), 2, overlap=True)
        body = tile_art.layers([red, blue], 0x202020, atlas, [('fill', '', False), ('fill', '', True)])
        with Image.open(io.BytesIO(body)) as image:
            rgb = image.convert('RGB')
            self.assertEqual(rgb.getpixel((20, 45)), (255, 0, 0))      # the first, where nothing lies over it
            self.assertEqual(rgb.getpixel((50, 45)), (0, 0, 255))      # the later place lies over the earlier
            self.assertGreater(rgb.getpixel((40, 1))[0], 245)          # its rounded corner shows the red under it
            self.assertEqual(rgb.getpixel((99, 0)), (0x20, 0x20, 0x20))  # and the card where nothing lies under it
            below = rgb.getpixel((70, 92))                            # the reflection: faint blue on the card
            self.assertTrue(below[2] > 0x40 and below[2] < 160 and below[0] < 0x30, below)
            self.assertTrue(all(abs(c - 0x20) <= 3 for c in rgb.getpixel((70, 116))))   # faded out at its foot
        # Turned to face the right: the left edge near (full height), the right edge far (lower and shorter).
        atlas = tile_art.parse('[[0,0,40,100,0,0]]', (480, 480), 1)
        body = tile_art.layers([red], 0x202020, atlas, [('fill', 'right', False)])
        with Image.open(io.BytesIO(body)) as image:
            rgb = image.convert('RGB')
            self.assertEqual(rgb.getpixel((1, 2))[0], 255)
            self.assertEqual(rgb.getpixel((38, 2)), (0x20, 0x20, 0x20))
            self.assertEqual(rgb.getpixel((38, 50))[0], 255)

    def test_where_a_picture_may_come_from(self):
        checked = pm.check(manifest(), ENGLISH)
        tile = dict(checked['tiles'][0], pictures=2)
        allowed = lambda url, t=tile: plugin_pictures.allowed(url, checked, t)
        self.assertEqual(allowed('https://api.example.org/a.jpg'), 'network')
        self.assertIsNone(allowed('https://image.tmdb.org/a.jpg'))         # a host the manifest does not name
        self.assertIsNone(allowed('https://10.0.0.5/a.jpg'))
        self.assertIsNone(allowed('ftp://api.example.org/a.jpg'))
        # Home Assistant's own pictures: on a tile of an entity only, and only the paths a map marker takes.
        self.assertIsNone(allowed('/api/image/serve/abc/512x512'))
        entity_tile = dict(tile, domains=['person'])
        self.assertEqual(allowed('/api/image/serve/abc/512x512', entity_tile), 'home_assistant')
        self.assertEqual(allowed('/api/image_proxy/image.door?token=1', entity_tile), 'home_assistant')
        self.assertEqual(allowed('/local/me.png', entity_tile), 'home_assistant')
        for bad in ('/api/camera_proxy/camera.x', '/api/image/serve/../x', '/local//x', '/api/states'):
            self.assertIsNone(allowed(bad, entity_tile), bad)
        # A tile without places shows nothing, whatever the address.
        self.assertIsNone(allowed('https://api.example.org/a.jpg', dict(tile, pictures=0)))
        q = self.question()
        self.assertIsNone(plugin_pictures.refused(q, checked, tile))
        self.assertIn('allows 1', plugin_pictures.refused(q, checked, dict(tile, pictures=1)))
        self.assertIn('no pictures', plugin_pictures.refused(q, checked, checked['tiles'][0]))
        self.assertIn('not an address', plugin_pictures.refused(self.question(src='["https://x.org/a","https://api.example.org/b"]'), checked, tile))
        self.assertIn('does not run', plugin_pictures.refused(q, None, None))

    async def test_a_picture_is_fetched_once_and_a_failure_waits(self):
        checked = pm.check(manifest(), ENGLISH)
        tile = dict(checked['tiles'][0], pictures=2, domains=['person'])
        asked, now = [], [1000.0]

        class Fetcher:
            check_host = staticmethod(plugin_fetch.Fetcher.check_host)

            async def download_bytes(self, url, headers, network, limit):
                asked.append(url)
                if url.endswith('gone.jpg'):
                    raise OSError('HTTP 404')
                return b'JPEG' + url.encode()
        ha = []

        async def ha_picture(path):
            ha.append(path)
            return b'PNG'
        pictures = plugin_pictures.Pictures(Fetcher(), ha_picture, clock=lambda: now[0])
        self.assertEqual(await pictures.fetch('https://api.example.org/a.jpg', checked, tile), b'JPEGhttps://api.example.org/a.jpg')
        self.assertEqual(await pictures.fetch('https://api.example.org/a.jpg', checked, tile), b'JPEGhttps://api.example.org/a.jpg')
        self.assertEqual(asked, ['https://api.example.org/a.jpg'])   # the second time from the cache
        self.assertEqual(await pictures.fetch('/local/me.png', checked, tile), b'PNG')
        self.assertEqual(ha, ['/local/me.png'])
        self.assertIsNone(await pictures.fetch('https://other.org/a.jpg', checked, tile))   # refused: never asked
        self.assertEqual(len(asked), 1)
        # A picture that does not come is not asked again within the minute, then it is.
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertEqual(asked.count('https://api.example.org/gone.jpg'), 1)
        now[0] += plugin_pictures.FAIL_SECONDS + 1
        self.assertIsNone(await pictures.fetch('https://api.example.org/gone.jpg', checked, tile))
        self.assertEqual(asked.count('https://api.example.org/gone.jpg'), 2)
        # A picture that came is fetched again after a long while.
        now[0] += plugin_pictures.KEEP_SECONDS
        await pictures.fetch('https://api.example.org/a.jpg', checked, tile)
        self.assertEqual(asked.count('https://api.example.org/a.jpg'), 2)

    @unittest.skipUnless(__import__('importlib').util.find_spec('PIL'), 'Pillow')
    async def test_the_atlas_paints_each_frame_as_asked(self):
        from PIL import Image
        import io
        q = self.question()
        wide = io.BytesIO()
        Image.new('RGB', (200, 100), (255, 0, 0)).save(wide, 'PNG')
        pictures = plugin_pictures.Pictures(None)
        body = await pictures.atlas(q, [wide.getvalue(), wide.getvalue()])
        with Image.open(io.BytesIO(body)) as atlas:
            self.assertEqual(atlas.size, (130, 90))
            rgb = atlas.convert('RGB')
            self.assertEqual(rgb.getpixel((30, 45)), (255, 0, 0))     # cover: the frame is filled
            self.assertEqual(rgb.getpixel((30, 2)), (255, 0, 0))
            self.assertEqual(rgb.getpixel((100, 45))[0], 255)        # contain: the picture whole, in the middle
            self.assertEqual(rgb.getpixel((100, 4)), (0x20, 0x20, 0x20))   # on the card's own colour, not black
            self.assertTrue(all(abs(c - 0x20) <= 2 for c in rgb.getpixel((0, 0))))  # a corner, rounded over the card's colour
        # Without any picture the frames stay the card's colour.
        body = await pictures.atlas(q, [None, None])
        with Image.open(io.BytesIO(body)) as atlas:
            self.assertEqual(atlas.convert('RGB').getpixel((30, 45)), (0x20, 0x20, 0x20))


class Everywhere(unittest.TestCase):
    """Plugins are on in every app since 0.4.87: the stable app (added from the repository URL), the dev app and a copy
    without a Supervisor all have the Plugins page, its routes and its loops."""

    def test_every_channel_has_plugins(self):
        before = core.channel()
        self.addCleanup(core.set_channel, before)
        for channel in ('main', 'dev', None):
            core.set_channel(channel)
            self.assertTrue(core.plugins_enabled(), channel)


class Boards(unittest.TestCase):
    """A plugin for one board's hardware (P4 panel audio) is offered to that board's screens only, and to a screen
    whose core is too old for its API to none."""

    def test_a_board_plugin_fits_its_board_only(self):
        import plugins as plugin_service
        entry = type('Entry', (), {'manifest': pm.check(manifest(boards=['wavesharep4'], api='0.4',
                                                                 requires={'psram': True}), ENGLISH)})()
        service = type('Service', (), {'blocked': lambda self, entry: False})()
        fits = lambda screen: plugin_service.Plugins.fits(service, entry, screen)  # noqa: E731
        self.assertIsNone(fits({'board': 'wavesharep4', 'pictures': True}))
        self.assertEqual(fits({'board': 'guition', 'pictures': True}), 'board')
        self.assertEqual(fits({'board': 'waveshare4b', 'pictures': True}), 'board')
        # The editor names the boards as people know them.
        self.assertEqual(plugin_service.board_name('wavesharep4'), 'Waveshare ESP32-P4-86-Panel-ETH-2RO')
        self.assertEqual(plugin_service.board_name('nonexistent'), 'nonexistent')
        # PSRAM comes from the board when the screen says nothing about it (a KeyError before).
        self.assertIsNone(fits({'board': 'wavesharep4'}))
        entry.manifest = pm.check(manifest(requires={'psram': True}), ENGLISH)
        self.assertEqual(fits({'board': 'cyd'}), 'psram')
        self.assertIsNone(fits({'board': 'guition'}))


class ReadWhole(unittest.IsolatedAsyncioTestCase):
    """The index arrives in pieces: every piece is read, and a body past the limit is refused (the index of three
    plugins, 25 KB, came back cut off with content.read(n))."""

    async def test_every_piece_and_the_limit(self):
        import plugins as plugin_service

        class Content:
            def __init__(self, pieces):
                self.pieces = pieces

            async def iter_chunked(self, size):
                for piece in self.pieces:
                    yield piece

        response = type('Response', (), {'content': Content([b'{"a": ', b'"' + b'x' * 20000 + b'"', b'}'])})()
        self.assertEqual(len(json.loads(await plugin_service.read_whole(response, 1 << 20))['a']), 20000)
        with self.assertRaises(ValueError):
            await plugin_service.read_whole(type('Response', (), {'content': Content([b'x' * 10, b'x' * 10])})(), 15)


class Links(unittest.IsolatedAsyncioTestCase):
    """A plugin added with a link follows its repository's releases: a new release is read and offered as an update,
    the same one costs two calls of GitHub's API and nothing more, and nothing of it goes through Tessera."""

    async def test_a_new_release_is_read_the_same_one_is_not(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        manager = type('Manager', (), {'page_senders': {}})()
        service = plugin_service.Plugins(manager, Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        installed = plugin_service.Entry(manifest(), {'en': ENGLISH}, {}, 'link', 'community',
                                         repo='https://github.com/someone/tessera-bus', path='.', ref='a' * 40)
        service.keep_snapshot(installed)
        service.store.put('kitchen', {'id': 'bus', 'version': '1.0.0', 'source': 'link', 'ref': 'a' * 40})
        newest = {'sha': 'a' * 40}
        asked, read = [], []

        async def github(url, text=False):
            asked.append(url)
            return {'tag_name': 'v1.0.0'} if url.endswith('/releases/latest') else dict(newest)

        async def resolve_link(url, branch=None, folder=None, path=None):
            read.append((url, path))
        service._github, service.resolve_link = github, resolve_link
        await service.refresh_links(force=True)
        self.assertEqual((len(asked), read), (2, []))
        self.assertIs(service.links['bus'], installed)
        newest['sha'] = 'b' * 40   # the maker published a release
        await service.refresh_links()           # within the hour: nothing asked
        self.assertEqual(len(asked), 2)
        await service.refresh_links(force=True)
        self.assertEqual(read, [('https://github.com/someone/tessera-bus', '.')])

    async def test_an_update_builds_the_new_release_in(self):
        """#260: the plugins file of an update named the new release, not nothing. A release added with a link is not
        in the index and its snapshot is kept only after the file is written, so the link it was read from stands in."""
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                async def build():
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        for version, ref in (('1.0.0', 'a' * 40), ('1.1.0', 'b' * 40)):
            service.links['bus'] = plugin_service.Entry(manifest(version=version), {'en': ENGLISH}, {}, 'link', 'community',
                                                        repo='https://github.com/someone/tessera-bus', path='.', ref=ref)
            await service.apply('hall', {'add': [{'id': 'bus', 'source': 'link', 'consent': True}]})
            await service.manager.build_queue.idle()
            with self.subTest(version):
                self.assertIn(f'ref: {ref}  # bus {version}', (config / 'hall.plugins.yaml').read_text())
                self.assertEqual(service.store.get('hall', 'bus')['state'], 'active')


class LinkPath(unittest.IsolatedAsyncioTestCase):
    """The folder in a link goes into the screen's plugins file and into git's path: only plain names, never a step up."""

    async def test_a_strange_folder_is_refused_before_github_is_asked(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        manager = type('Manager', (), {'page_senders': {}})()
        service = plugin_service.Plugins(manager, Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        asked = []

        async def github(url, text=False):
            asked.append(url)
            raise AssertionError('GitHub was asked')
        service._github = github
        for folder in ('plugins/../secrets', 'a b', "x'y", 'plugins/bus:', 'plugins/bus #'):
            with self.subTest(folder):
                with self.assertRaises(ValueError):
                    await service.resolve_link(f'https://github.com/someone/repo/tree/main/{folder}')
        self.assertEqual(asked, [])


class LinkFolder(unittest.IsolatedAsyncioTestCase):
    """A link copied from GitHub to a plugin's folder (.../tree/main/plugins/bus) builds the newest release of that
    folder; a repository without a release keeps the link's own commit."""

    async def test_the_folder_of_the_newest_release(self):
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        released = {'v2.0.0': 'r' * 40, 'main': 'm' * 40}
        release = {'tag_name': 'v2.0.0'}
        asked = []

        async def github(url, text=False):
            asked.append(url)
            if url.endswith('/releases/latest'):
                if not release:
                    raise ValueError('not found')
                return release
            if '/commits/' in url:
                return {'sha': released[url.rsplit('/', 1)[1]]}
            if url.endswith('tessera-plugin.yaml'):
                return yaml.safe_dump(manifest())
            if '/contents/' in url and 'translations' in url:
                return [{'name': 'en.json'}]
            if url.endswith('translations/en.json'):
                return json.dumps(ENGLISH)
            return []
        service._github = github
        entry = await service.resolve_link('https://github.com/someone/plugins/tree/main/plugins/bus')
        self.assertEqual((entry.path, entry.ref, entry.label), ('plugins/bus', 'r' * 40, 'community'))
        self.assertTrue(any(u.endswith(f"{'r' * 40}/plugins/bus/tessera-plugin.yaml") for u in asked))
        release.clear()
        entry = await service.resolve_link('https://github.com/someone/plugins/tree/main/plugins/bus')
        self.assertEqual(entry.ref, 'm' * 40)

    async def test_its_picture_for_the_plugins_page(self):
        # store.png beside the manifest, at most a megabyte, is the plugin's picture; the app fetches it when shown.
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        listing = [{'name': 'README.md', 'size': 10}, {'name': 'store.png', 'size': 300_000}]

        async def github(url, text=False):
            if url.endswith('/releases/latest'):
                return {'tag_name': 'v1.0.0'}
            if '/commits/' in url:
                return {'sha': 'r' * 40}
            if url.endswith('tessera-plugin.yaml'):
                return yaml.safe_dump(manifest())
            if '/contents/' in url and 'translations' in url:
                return [{'name': 'en.json'}]
            if url.endswith('translations/en.json'):
                return json.dumps(ENGLISH)
            if '/contents/' in url:
                return listing
            return '# Bus'
        service._github = github
        entry = await service.resolve_link('https://github.com/someone/tessera-bus')
        self.assertEqual(service.editor_plugin(entry)['image'], f'api/plugins/{entry.id}/image?v={"r" * 40}')
        listing[1]['size'] = 2_000_000
        entry = await service.resolve_link('https://github.com/someone/tessera-bus')
        self.assertIsNone(entry.image, 'larger than the page takes')


class ImageRoom(unittest.TestCase):
    """The editor's room for a plugin on a 4 MB board comes from the screen's own last image and its slot."""

    def test_the_slot_follows_the_screen_table(self):
        firmware = Firmware.__new__(Firmware)
        firmware.wide_slots = lambda name: name == 'cyd.yaml'
        firmware.image_size = lambda name: 1_879_231
        self.assertEqual(firmware.image_room('cyd.yaml', 'wide'), {'size': 1_879_231, 'slot': 2_031_616})
        self.assertEqual(firmware.image_room('cyd.yaml', 'old'), {'size': 1_879_231, 'slot': 0x1C0000})
        self.assertIsNone(firmware.image_room('guition.yaml', 'wide'))   # 16 MB: no meter
        firmware.image_size = lambda name: None
        self.assertIsNone(firmware.image_room('cyd.yaml'))               # not built here yet


class Map(unittest.TestCase):
    ANSWER = {'30003025': {'passes': {
        'b': {'line': '7', 'to': 'Slotermeer', 'when': '2026-10-07T17:30:00', 'state': 'DRIVING'},
        'a': {'line': '15', 'to': 'Sloterdijk', 'when': '2026-10-07T17:20:00+02:00', 'state': 'PASSED'},
        'c': {'line': '15', 'to': 'Sloterdijk', 'when': '2026-10-07T17:25:00', 'state': 'PLANNED'}}}}

    def spec(self, **extra):
        return pm.check_map({'items': '$.{stop}.passes[*]', 'fields': {
            'line': 'line', 'at': {'path': 'when', 'as': 'epoch', 'tz': 'Europe/Amsterdam'}, 'state': 'state'}, **extra},
            'map', False)

    def test_items_of_an_object_sorted_filtered_and_cut(self):
        out = plugin_fetch.apply_map(self.spec(skip={'state': ['PASSED']}, sort='at', limit=1), self.ANSWER,
                                     {'stop': '30003025'})
        self.assertEqual([i['line'] for i in out['items']], ['15'])
        self.assertEqual(out['items'][0]['at'], 1791386700)    # 17:25 in Amsterdam (CEST), 15:25 UTC

    def test_where_with_an_empty_option_keeps_everything(self):
        spec = self.spec(where={'line': '{line}'}, sort='at')
        everything = plugin_fetch.apply_map(spec, self.ANSWER, {'stop': '30003025', 'line': ''})
        only = plugin_fetch.apply_map(spec, self.ANSWER, {'stop': '30003025', 'line': '7'})
        self.assertEqual(len(everything['items']), 3)
        self.assertEqual([i['line'] for i in only['items']], ['7'])

    def test_choices_once_each(self):
        spec = pm.check_map({'items': '$.{stop}.passes[*]', 'value': 'line', 'label': ['line', 'to']}, 'map', True)
        self.assertEqual(plugin_fetch.apply_choices(spec, self.ANSWER, {'stop': '30003025'}),
                         [{'value': '7', 'label': '7 · Slotermeer'}, {'value': '15', 'label': '15 · Sloterdijk'}])

    def test_paths(self):
        self.assertEqual(pm.parse_path('$.a[*].b[:2][0]'), [('key', 'a'), ('all',), ('key', 'b'), ('first', 2), ('at', 0)])
        for bad in ('a.b', '$.a[?(@.x)]', '$..a'):
            with self.subTest(bad), self.assertRaises(ValueError):
                pm.parse_path(bad)

    def test_text_is_bounded(self):
        spec = pm.check_map({'fields': {'name': 'name'}}, 'map', False)
        self.assertEqual(len(plugin_fetch.apply_map(spec, {'name': 'é' * 100})['name'].encode()), 48)


class Fetch(unittest.TestCase):
    def test_fill_encodes_and_needs_every_value(self):
        fetch = pm.check(manifest(), ENGLISH)['fetch'][0]
        url, _ = plugin_fetch.fill(fetch, {'stop': 'a b/c'}, {})
        self.assertEqual(url, 'https://api.example.org/stops/a%20b%2Fc')
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill(fetch, {'stop': ''}, {})

    def test_home_addresses_are_refused(self):
        for address in ('192.168.1.10', '10.0.0.1', '127.0.0.1', '::1', 'fe80::1', '169.254.1.1', '::ffff:192.168.1.1'):
            with self.subTest(address):
                self.assertTrue(plugin_fetch.blocked_address(address))
        self.assertFalse(plugin_fetch.blocked_address('195.201.197.190'))

    def test_a_failure_keeps_the_last_answer_and_waits(self):
        clock = [1000.0]
        fetcher = plugin_fetch.Fetcher(clock=lambda: clock[0])
        answers = [{'x': 1}, OSError('HTTP 503')]

        async def download(url, headers, network):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        fetcher.download = download
        checked = pm.check(manifest(), ENGLISH)
        fetch = checked['fetch'][0]

        async def run():
            _, first = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})
            self.assertEqual(first['data'], {'x': 1})
            clock[0] += 30
            _, same = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})   # not due yet: no ask
            self.assertEqual(len(answers), 1)
            clock[0] += 60
            _, failed = await fetcher.get('bus', checked, fetch, {'stop': '1'}, {})
            self.assertTrue(failed['stale'])
            self.assertEqual(failed['data'], {'x': 1})
            self.assertEqual(failed['retry'], clock[0] + 60)
        asyncio.run(run())

    def test_secrets_are_redacted(self):
        self.assertEqual(plugin_fetch.redact('GET /x?key=abc123 failed', {'key': 'abc123'}), 'GET /x?key=*** failed')


class Layout(unittest.TestCase):
    DOC = {'title': 'T', 'homePageId': 'aaaaaaaaaaaaaaaa', 'pages': [{
        'id': 'aaaaaaaaaaaaaaaa', 'navigation': {'excludeFromPagination': False},
        'topbar': {'leading': [], 'title': {'source': 'screen'}, 'trailing': []},
        'tiles': [{'id': 't1', 'content': {'kind': 'plugin', 'plugin': 'bus', 'tile': 'next',
                                            'options': {'stop': '30003025', 'walk': 3}},
                   'placement': {'row': 0, 'column': 0, 'columns': 2, 'rows': 1}, 'appearance': {'label': ''},
                   'interaction': {}}]}]}

    def test_a_plugin_tile_round_trips(self):
        page_layout.validate_document(json.loads(json.dumps(self.DOC)), core.DEFAULT_GRID)
        flat = page_layout.compile_tiles(self.DOC, core.DEFAULT_GRID)[0]
        self.assertEqual(flat['entity'], 'plugin:bus.next')
        self.assertEqual(flat['options']['plugin'], {'stop': '30003025', 'walk': 3})
        back = page_layout.tile_from_fields(flat, core.DEFAULT_GRID, ['aaaaaaaaaaaaaaaa'], id_factory=lambda: 't1')
        self.assertEqual(back['content'], self.DOC['pages'][0]['tiles'][0]['content'])

    def test_a_tile_of_an_entity_round_trips(self):
        doc = json.loads(json.dumps(self.DOC))
        doc['pages'][0]['tiles'][0]['content']['entityId'] = 'sensor.waste_next'
        page_layout.validate_document(json.loads(json.dumps(doc)), core.DEFAULT_GRID)
        flat = page_layout.compile_tiles(doc, core.DEFAULT_GRID)[0]
        self.assertEqual(flat['options']['plugin_entity'], 'sensor.waste_next')
        back = page_layout.tile_from_fields(flat, core.DEFAULT_GRID, ['aaaaaaaaaaaaaaaa'], id_factory=lambda: 't1')
        self.assertEqual(back['content'], doc['pages'][0]['tiles'][0]['content'])
        for wrong in ('screen.clock', 'not an entity'):
            with self.subTest(wrong), self.assertRaises(ValueError):
                core.validate_layout({'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                                              'options': {'plugin_entity': wrong}}]})

    def test_only_the_shape_is_checked(self):
        ok = {'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                      'options': {'plugin': {'a': 'x', 'b': 2, 'c': True}, 'tap': 'none'}}]}
        core.validate_layout(ok)
        for options in ({'plugin': {'a': {'nested': 1}}}, {'plugin': {'a': 'x' * 65}}, {'display': 'watch'},
                        {'plugin': {str(i): 1 for i in range(13)}}):
            with self.subTest(options), self.assertRaises(ValueError):
                core.validate_layout({'title': '', 'tiles': [{'entity': 'plugin:bus.next', 'name': '', 'slot': 0,
                                                              'options': options}]})
        self.assertFalse(core.entity_id('plugin:bus.next'))   # commands and events keep Home Assistant's ids

    def test_price(self):
        memory = {'psram': False, 'tile': 300, 'extra': 200}
        core.PLUGIN_MEMORY['plugin:bus.next'] = 900
        try:
            self.assertEqual(core.tile_cost({'entity': 'plugin:bus.next'}, memory), 1400)
            self.assertEqual(core.tile_cost({'entity': 'plugin:gone.tile'}, {**memory, 'psram': True}),
                             core.PLUGIN_PLACEHOLDER_BYTES)
        finally:
            core.PLUGIN_MEMORY.pop('plugin:bus.next')


class EntityTile(unittest.IsolatedAsyncioTestCase):
    async def test_state_name_and_named_attributes_only(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {'sensor.waste_next': {'state': 'paper', 'attributes': {
                'friendly_name': 'Next collection', 'next_date': '2026-10-09', 'days': 2, 'secret': 'no'}}},
                'time_zone': 'Europe/Amsterdam', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        kind = {'id': 'next', 'domains': ['sensor'], 'attributes': ['next_date', 'days']}
        entity, part = service.entity_part(kind, {'options': {'plugin_entity': 'sensor.waste_next'}})
        self.assertEqual(entity, 'sensor.waste_next')
        self.assertEqual(part['state'], 'paper')
        self.assertEqual(part['name'], 'Next collection')
        self.assertEqual(set(part['attributes']), {'next_date', 'days'})
        self.assertIsInstance(part['attributes']['next_date'], int)   # a date as seconds, for the screen's own words
        _, wrong = service.entity_part(kind, {'options': {'plugin_entity': 'light.kitchen'}})
        self.assertEqual(wrong, {'wait': 'wrong_entity'})


class BlamedBuilds(unittest.TestCase):
    """A screen's update that stops on a plugin's code says which plugin, and its update when one is on offer."""

    def test_compiler_error_in_a_plugin_names_it(self):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), Path(tmp.name) / 'data',
                                         Path(tmp.name) / 'esphome')
        logs = ["../src/esphome/components/smart_display/page_bar.h:169:36: warning: '%d' directive output may be truncated",
                "../src/esphome/components/tap_sound/tap_sound.h:19:8: error: 'void esphome::tap_sound::TapSound::on_step()'"
                " marked 'override', but does not override",
                'ninja: build stopped: subcommand failed.', 'ESPHome compile failed; see the log.']
        self.assertEqual(plugin_service.failed_components(logs), {'tap_sound'})
        self.assertIsNone(service.blame('tablet', logs))   # not a plugin of this screen
        service.store.put('tablet', {'id': 'tap_sound', 'version': '0.2.0', 'source': 'index', 'ref': 'a' * 40})
        self.assertEqual(service.blame('tablet', logs),
                         {'id': 'tap_sound', 'name': 'tap_sound', 'version': '0.2.0', 'update': None})
        service.index['tap_sound'] = type('Entry', (), {'version': '0.2.1', 'ref': 'b' * 40, 'text': lambda self, key: 'Tap sound'})()
        self.assertEqual(service.blame('tablet', logs), {'id': 'tap_sound', 'name': 'Tap sound', 'version': '0.2.0', 'update': '0.2.1'})
        # An error in Tessera's own code, or none at all, blames no plugin.
        self.assertIsNone(service.blame('tablet', [logs[0].replace('warning', 'error'), logs[-1]]))
        self.assertIsNone(service.blame('tablet', ['Succeeded: install']))


class Questions(unittest.IsolatedAsyncioTestCase):
    """A plugin asks Home Assistant something through the app: only what its manifest names, the answer bounded."""

    async def test_named_commands_only_and_bounded(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'calendar_peek', Path(tmp.name) / 'tessera-plugins' / 'calendar_peek')
        asked, sent = [], []

        class FakeHA:
            states, changed, dirty = {}, asyncio.Event(), set()

            async def request(self, kind, **data):
                asked.append((kind, data))
                return {'response': {'calendar.waste': {'events': [{'summary': 'Paper ' * 20, 'start': '2026-10-09'}] * 100}}}

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'name': 'Kitchen', 'board': 'guition', 'online': True}

            def transport(self, inbox, screen=None):
                return 'action'

            async def send_auxiliary(self, inbox, message, action, request):
                sent.append(message)
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'calendar_peek', 'source': 'folder', 'state': 'active'})
        body = {'re': 7, 'ask': 'call_service:calendar.get_events', 'data': {'entity_id': 'calendar.waste', 'duration': {'days': 28}}}
        await service.answer({'inbox': 'kitchen', 'plugin': 'calendar_peek', 'body': json.dumps(body)})
        self.assertEqual(asked[0][0], 'call_service')
        self.assertEqual(asked[0][1]['target'], {'entity_id': 'calendar.waste'})
        self.assertTrue(asked[0][1]['return_response'])
        reply = sent[0]['m']
        self.assertEqual((sent[0]['op'], sent[0]['p'], reply['re'], reply['ok']), ('plugin', 'calendar_peek', 7, True))
        self.assertLessEqual(len(json.dumps(reply)), 3400)
        await service.answer({'inbox': 'kitchen', 'plugin': 'calendar_peek', 'body': json.dumps({'re': 8, 'ask': 'get_states'})})
        self.assertEqual(sent[1]['m'], {'re': 8, 'ok': False, 'error': 'not_allowed'})
        self.assertEqual(len(asked), 1)
        # A plugin the screen does not run gets nothing at all.
        await service.answer({'inbox': 'kitchen', 'plugin': 'other', 'body': json.dumps(body)})
        self.assertEqual(len(sent), 2)

    async def test_settings_of_the_screens_own_entities_only(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'calendar_peek', Path(tmp.name) / 'tessera-plugins' / 'calendar_peek')
        calls = []

        class FakeHA:
            changed, dirty = asyncio.Event(), set()
            registry = [{'entity_id': 'switch.kitchen_peek_in_bar', 'device_id': 'dev1'},
                        {'entity_id': 'number.kitchen_peek_days', 'device_id': 'dev1'},
                        {'entity_id': 'switch.hall_peek_in_bar', 'device_id': 'dev2'}]
            states = {'switch.kitchen_peek_in_bar': {'state': 'on'},
                      'number.kitchen_peek_days': {'state': '2.0', 'attributes': {'min': 0, 'max': 3, 'step': 1}}}

            async def call_service(self, domain, service, data):
                calls.append((domain, service, data))

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'device_id': 'dev1', 'online': True}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'calendar_peek', 'source': 'folder', 'state': 'active'})
        groups = service.settings_for('kitchen')
        rows = groups[0]['rows']
        self.assertEqual([(r['entity'], r['kind'], r['value']) for r in rows],
                         [('switch.kitchen_peek_in_bar', 'switch', True), ('number.kitchen_peek_days', 'number', 2.0)])
        await service.set_setting('kitchen', 'number.kitchen_peek_days', 3)
        self.assertEqual(calls, [('number', 'set_value', {'entity_id': 'number.kitchen_peek_days', 'value': 3})])
        for entity, value in (('switch.hall_peek_in_bar', True), ('light.kitchen', True), ('switch.kitchen_peek_in_bar', 'yes')):
            with self.subTest(entity), self.assertRaises(ValueError):
                await service.set_setting('kitchen', entity, value)

    def test_the_manifest_refuses_commands_that_reach_home_assistant_itself(self):
        for wrong in ('call_service', 'config/entity_registry/update', 'auth/sign_path', 'fire_event', 'supervisor/api'):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': [wrong]}), ENGLISH)
        pm.check(manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']}), ENGLISH)


class Hello(unittest.TestCase):
    def test_plugins_of_a_hello(self):
        self.assertEqual(plugins_of({}), (None, []))
        api, plugins = plugins_of({'plugin_api': '0.1', 'plugins': [
            {'id': 'bus', 'version': '1.0.0', 'tiles': ['next', 'Bad!']}, {'id': 'Nope'}, 'junk']})
        self.assertEqual(api, '0.1')
        self.assertEqual(plugins, [{'id': 'bus', 'version': '1.0.0', 'tiles': ['next']}])


class Sidecar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'esphome'
        root.mkdir()
        (root / 'kitchen.yaml').write_text('esphome:\n  name: kitchen\npackages:\n  display:\n    url: x\n'
                                           '  local_overrides: !include kitchen.local.yaml\napi:\n')
        self.firmware = Firmware(root, Path(self.tmp.name) / 'data')

    def tearDown(self):
        self.tmp.cleanup()

    def test_written_then_attached_once_and_hidden(self):
        content = '# Written by Tessera.\npackages:\n  plugin_bus: !include ../tessera-plugins/bus/plugin.yaml\n'
        self.firmware.save_plugins('kitchen.yaml', content)
        self.firmware.save_plugins('kitchen.yaml', content)
        text = (self.firmware.root / 'kitchen.yaml').read_text()
        self.assertEqual(text.count('tessera_plugins: !include kitchen.plugins.yaml'), 1)
        self.assertLess(text.index('tessera_plugins'), text.index('api:'))
        self.assertEqual([p['file'] for p in self.firmware.profiles()], ['kitchen.yaml'])
        self.assertTrue(self.firmware.plugins_file('kitchen.yaml')['attached'])

    def test_only_packages_and_components(self):
        with self.assertRaises(ValueError):
            self.firmware.save_plugins('kitchen.yaml', 'wifi:\n  ssid: x\n')
        self.assertFalse((self.firmware.root / 'kitchen.plugins.yaml').exists())


class Queue(unittest.IsolatedAsyncioTestCase):
    """Ticking several screens builds them one after the other, never two at once and never a refusal."""

    async def test_screens_build_one_after_the_other(self):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', Path(tmp.name) / 'tessera-plugins' / 'clock_words')
        started, running = [], []

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                assert not (self.task and not self.task.done()), 'two builds at once'
                started.append(data['file'])

                async def build():
                    running.append(data['file'])
                    await asyncio.sleep(0.01)
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        for inbox in ('one', 'two', 'three'):
            result = await service.apply(inbox, {'add': [{'id': 'clock_words', 'source': 'folder'}]})
            self.assertTrue(result['built'])
        await service.manager.build_queue.idle()
        self.assertEqual(started, ['one.yaml', 'two.yaml', 'three.yaml'])
        self.assertEqual({i: service.store.get(i, 'clock_words')['state'] for i in ('one', 'two', 'three')},
                         {'one': 'active', 'two': 'active', 'three': 'active'})
        self.assertIn('../tessera-plugins/clock_words/plugin.yaml', (config / 'one.plugins.yaml').read_text())

    async def test_every_update_of_a_screen_in_one_build_keeps_what_was_filled_in(self):
        """Update all on this screen: two plugins in one request build the screen once, and an update that sends no
        values keeps the ones given when the plugin was added (a calendar, an optional part)."""
        import shutil
        import yaml
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folders = Path(tmp.name) / 'tessera-plugins'
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', folders / 'clock_words')
        shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / 'clock_words', folders / 'city_words')
        manifest = yaml.safe_load((folders / 'city_words' / 'tessera-plugin.yaml').read_text())
        manifest.update(id='city_words', inputs=[{'id': 'city', 'kind': 'text', 'label': 'tile'}],
                        parts=[{'id': 'extra', 'file': 'extra.yaml', 'label': 'tile', 'flash_kb': 4}])
        (folders / 'city_words' / 'tessera-plugin.yaml').write_text(yaml.safe_dump(manifest))
        started = []

        class FakeFirmware:
            task = None
            job = None

            def save_plugins(self, profile, text):
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                started.append(data['file'])

                async def build():
                    self.job = {'state': 'success'}
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', '10.0.0.1')})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        await service.apply('hall', {'add': [{'id': 'city_words', 'source': 'folder', 'values': {'city': 'Utrecht'},
                                              'parts': ['extra']}]})
        await service.manager.build_queue.idle()
        started.clear()
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}, {'id': 'city_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(started, ['hall.yaml'])
        record = service.store.get('hall', 'city_words')
        self.assertEqual((record['values'], record['parts']), ({'city': 'Utrecht'}, ['extra']))
        text = (config / 'hall.plugins.yaml').read_text()
        self.assertIn('"CITY": "Utrecht"', text)
        self.assertIn('extra.yaml', text)
        self.assertIn('clock_words/plugin.yaml', text)


class BuildOutcome(unittest.IsolatedAsyncioTestCase):
    """What a build's end and a change during a build do to a screen's plugins (plugins.py apply, _build_queue,
    _settle_build): nothing asked is lost, and a failed build leaves a plugins file that builds."""

    def make(self, results=None, host='10.0.0.1', refuse=False):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folders = Path(tmp.name) / 'tessera-plugins'
        for name in ('clock_words', 'calendar_peek'):
            shutil.copytree(ROOT / 'tests' / 'fixtures' / 'plugins' / name, folders / name)
        outcomes = list(results or [])
        started = []

        class FakeFirmware:
            task = None
            job = None
            gate = None
            logs = []

            def save_plugins(self, profile, text):
                if refuse:
                    raise ValueError('another include')
                (config / profile.replace('.yaml', '.plugins.yaml')).write_text(text)

            def start(self, data):
                assert not (self.task and not self.task.done()), 'two builds at once'
                started.append((config / 'hall.plugins.yaml').read_text())
                state = outcomes.pop(0) if outcomes else 'success'

                async def build():
                    if self.gate:
                        await self.gate.wait()
                    self.job = {'state': state}
                    self.logs = ['ESPHome: compile'] + ([] if state == 'success' else ['compile failed'])
                self.task = asyncio.get_running_loop().create_task(build())

        class FakeManager:
            firmware = FakeFirmware()

            def __init__(self):
                self.build_queue = BuildQueue(self)
            ha = type('HA', (), {'changed': asyncio.Event(), 'dirty': set()})()
            page_senders = {}

            def screen(self, inbox):
                return {'id': inbox, 'node': inbox, 'name': inbox.title(), 'board': 'guition'}

            def notify(self):
                pass
        FakeManager.updates = type('U', (), {'resolve': lambda self, screen: (screen['id'] + '.yaml', host)})()
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        return service, config, started

    async def test_a_change_while_the_screen_builds_gets_a_build_of_its_own(self):
        service, config, started = self.make()
        service.manager.firmware.gate = asyncio.Event()
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        while not service.manager.build_queue.running:
            await asyncio.sleep(0)
        await service.apply('hall', {'add': [{'id': 'calendar_peek', 'source': 'folder'}]})
        service.manager.firmware.gate.set()
        await service.manager.build_queue.idle()
        self.assertEqual(len(started), 2)
        self.assertIn('calendar_peek', started[1])
        self.assertEqual({p: service.store.get('hall', p)['state'] for p in ('clock_words', 'calendar_peek')},
                         {'clock_words': 'active', 'calendar_peek': 'active'})
        self.assertFalse(service.manager.build_queue.busy())

    async def test_a_plugin_asked_while_the_screen_s_update_waits_comes_with_that_update(self):
        """A plugin build and an update of one screen are one build (build_queue): the update builds the plugins file
        too, and its install settles the plugin."""
        service, config, started = self.make()
        line = service.manager.build_queue
        service.manager.firmware.gate = asyncio.Event()

        async def other(build):
            return 'success' if await line.step({'file': 'desk.yaml', 'action': 'install', 'target': '10.0.0.2'}) else 'failed'

        async def update(build):
            return 'success' if await line.step({'file': 'hall.yaml', 'action': 'install', 'target': '10.0.0.1'}) else 'failed'
        line.add('update', 'desk.yaml', other, screen='desk')
        waiting = line.add('update', 'hall.yaml', update, screen='hall')
        result = await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertEqual(result['queued'], 1)
        self.assertEqual((waiting.by, waiting.plugins['add']), ('update', ['clock_words']))
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'building')
        service.manager.firmware.gate.set()
        await line.idle()
        self.assertEqual(len(started), 2, 'desk, then hall once')
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'active')

    async def test_a_new_plugin_that_fails_leaves_the_file(self):
        service, config, _ = self.make(['failed'])
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual((record['state'], record['reason']), ('failed', 'compile failed'))
        self.assertNotIn('clock_words', (config / 'hall.plugins.yaml').read_text())
        # Trying again puts it back in the file and builds.
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        await service.manager.build_queue.idle()
        self.assertEqual(service.store.get('hall', 'clock_words')['state'], 'active')
        self.assertNotIn('reason', service.store.get('hall', 'clock_words'))
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())

    async def test_an_update_that_fails_goes_back_to_what_worked(self):
        service, config, _ = self.make(['success', 'failed'])
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder', 'parts': []}]})
        await service.manager.build_queue.idle()
        before = service.store.get('hall', 'clock_words')
        await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder', 'parts': ['missing']}]})
        self.assertEqual(service.store.get('hall', 'clock_words')['previous']['version'], before['version'])
        await service.manager.build_queue.idle()
        record = service.store.get('hall', 'clock_words')
        self.assertEqual(record['state'], 'active')
        self.assertEqual(record['failed_update']['reason'], 'compile failed')
        self.assertNotIn('previous', record)
        self.assertIn('clock_words', (config / 'hall.plugins.yaml').read_text())

    async def test_a_file_that_cannot_be_written_changes_nothing(self):
        service, config, started = self.make(refuse=True)
        with self.assertRaises(ValueError):
            await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertIsNone(service.store.get('hall', 'clock_words'))
        self.assertEqual(started, [])

    async def test_a_screen_without_an_address_is_not_changed(self):
        service, config, started = self.make(host=None)
        with self.assertRaises(ValueError) as caught:
            await service.apply('hall', {'add': [{'id': 'clock_words', 'source': 'folder'}]})
        self.assertIn('Hall', str(caught.exception))
        self.assertIsNone(service.store.get('hall', 'clock_words'))
        self.assertFalse((config / 'hall.plugins.yaml').exists())

    def test_a_failed_build_says_why_in_one_line(self):
        from plugins import build_reason
        self.assertEqual(build_reason(['INFO x', 'src/a.cpp:3:1: error: foo', 'ninja: build stopped: subcommand failed.',
                                       'ESPHome compile failed; see the log.']), 'src/a.cpp:3:1: error: foo')
        self.assertEqual(build_reason(['ninja failed with exit code 1', 'The compiler ran out of memory: more is needed.']),
                         'The compiler ran out of memory: more is needed.')
        self.assertEqual(build_reason(None), 'build')

    def test_a_screen_that_goes_forgets_its_own_secrets(self):
        from plugin_store import PluginSecrets
        secrets = PluginSecrets(Path(tempfile.mkdtemp()) / 'secrets.json')
        secrets.set('bus', 'key', 'one', 'hall')
        secrets.set('bus', 'key', 'all', 'all')
        secrets.drop_scope('bus', 'hall')
        self.assertEqual(secrets.of('bus', 'hall'), {'key': 'all'})

    def test_a_secret_kept_before_origins_is_handed_out_after_the_update(self):
        # The files of app 0.4.86: a plugin added with a link, and its key with no origin. A plugin of the same id from
        # another repository still gets nothing, and a key whose plugin is on no screen stays without an origin.
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / 'data'
        data.mkdir()
        (data / 'plugins.json').write_text(json.dumps({'version': 1, 'screens': {'hall': {'plugins': [
            {'id': 'bus', 'source': 'link', 'repo': 'https://github.com/Maker/Bus-Plugin.git', 'path': '.', 'ref': 'v1.0.0',
             'version': '1.0.0', 'state': 'active'}]}}}))
        (data / 'plugin_secrets.json').write_text(json.dumps({'version': 1, 'values': {
            'bus/key/all': 'abc', 'bus/token/hall': 'def', 'gone/key/all': 'ghi'}}))
        service = plugin_service.Plugins(type('Manager', (), {'page_senders': {}})(), data, Path(tmp.name) / 'esphome')
        origin = plugin_service.origin_of('https://github.com/maker/bus-plugin')
        self.assertEqual(service.secrets.of('bus', 'hall', origin), {'key': 'abc', 'token': 'def'})
        self.assertTrue(service.secrets.has('bus', 'key', origin=origin))
        self.assertEqual(service.secrets.of('bus', 'hall', plugin_service.origin_of('https://github.com/fork/bus')), {})
        kept = json.loads((data / 'plugin_secrets.json').read_text())
        self.assertEqual(kept['origins'], {'bus/key/all': origin, 'bus/token/hall': origin})


class Builds(unittest.IsolatedAsyncioTestCase):
    """Manager.builds: one record per screen for whatever is being built for it, whoever asked (the build line,
    build_queue), so the editor tracks every build in one place."""

    def manager(self):
        manager = type('M', (), {})()
        manager.updates = type('U', (), {'resolve': lambda self, screen, profiles=None: (screen['id'] + '.yaml', '10.0.0.1')})()
        manager.firmware = type('F', (), {'job': None, 'logs': [], 'profile_names': lambda self: [],
                                          'check': lambda self, data: None})()
        manager.build_queue = BuildQueue(manager)
        self.gate = asyncio.Event()
        self.addAsyncCleanup(self.finish, manager)
        return manager

    async def finish(self, manager):
        for build in list(manager.build_queue.line):
            manager.build_queue.drop(build)
        self.gate.set()
        await manager.build_queue.idle()

    async def held(self, build):
        await self.gate.wait()
        return 'success'

    def builds(self, manager):
        import server
        screens = [{'id': name} for name in ('hall', 'kitchen', 'desk')]
        return server.Manager.builds(manager, screens, [])

    async def test_nothing_on_the_way_is_no_record(self):
        self.assertEqual(self.builds(self.manager()), {})

    async def test_every_kind_of_build_once_per_screen(self):
        m = self.manager()
        line = m.build_queue
        hall = line.add('update', 'hall.yaml', self.held, screen='hall')
        hall.phase = 'install'
        kitchen = line.add('plugins', 'kitchen.yaml', self.held, screen='kitchen', plugins={'add': ['bus']})
        desk = line.add('update', 'desk.yaml', self.held, screen='desk')
        # A plugin asked for a screen whose update waits joins that update: one build, which brings the plugin too.
        self.assertIs(line.add('plugins', 'desk.yaml', self.held, screen='desk', plugins={'add': ['waste']}), desk)
        out = self.builds(m)
        self.assertEqual(out['hall'], {'id': hall.id, 'by': 'update', 'state': 'running', 'phase': 'install',
                                       'file': 'hall.yaml', 'stage': None})
        self.assertEqual(out['kitchen'], {'id': kitchen.id, 'by': 'plugins', 'state': 'queued', 'plugins': ['bus'],
                                          'file': 'kitchen.yaml', 'stage': None, 'place': 1})
        self.assertEqual(out['desk'], {'id': desk.id, 'by': 'update', 'state': 'queued', 'phase': None, 'plugins': ['waste'],
                                       'file': 'desk.yaml', 'stage': None, 'place': 2})

    async def test_an_install_from_firmware_and_usb_counts_and_a_check_does_not(self):
        m = self.manager()
        m.build_queue.add('update', 'hall.yaml', self.held, screen='hall')
        check = m.build_queue.attended({'file': 'kitchen.yaml', 'action': 'validate'})
        install = m.build_queue.attended({'file': 'desk.yaml', 'action': 'install', 'target': '10.0.0.9'})
        out = self.builds(m)
        self.assertNotIn('kitchen', out)
        self.assertEqual((check.by, install.by), ('check', 'install'))
        self.assertEqual(out['desk'], {'id': install.id, 'by': 'install', 'state': 'queued', 'file': 'desk.yaml',
                                       'stage': None, 'place': 2})


if __name__ == '__main__':
    unittest.main()


# ---- A day of prices or a forecast (plugin API 0.5) ----
# Real day-ahead prices (two days of 96 quarters) in the shapes the integrations give them, as their source builds
# them: an attribute list of numbers or of objects, or an action's answer, with every way of writing a moment seen.

PRICES = json.loads((ROOT / 'tests/fixtures/plugins/prices/nordpool_nl.json').read_text())


def moments(day, step=None, offset='+02:00', space=False, utc=False):
    """The start of every slot of a day of PRICES as Home Assistant writes it: ISO with an offset (a datetime the
    websocket serialises), str(datetime) with a space (energyzero, easyenergy, ENTSO-e), or UTC."""
    from datetime import datetime, timedelta, timezone
    start = datetime.fromisoformat(day['start'])
    zone = timezone.utc if utc else timezone(timedelta(hours=int(offset[:3]), minutes=int(offset[4:])))
    out = []
    for i in range(len(day['prices'])):
        moment = (start + timedelta(minutes=(step or day['minutes']) * i)).astimezone(zone)
        out.append(str(moment) if space else moment.isoformat())
    return out


def series_sources():
    """{source: (where, data, fields)}: where 'attributes' (the entity's) or 'answer' (an action's response), and the
    fields a plugin maps to get the day as one list of numbers plus its first moment."""
    today, tomorrow = PRICES['days'][1], PRICES['days'][0]
    kwh = [round(p / 1000, 3) for p in today['prices']]
    at = moments(today)
    half = lambda values: values[::2]          # 48 slots of half an hour
    price_fields = lambda path, first: {'prices': {'path': path, 'as': 'numbers'}, 'start': {'path': first, 'as': 'epoch'}}
    return {
        'nordpool (HACS), raw_today': ('attributes', {
            'today': kwh, 'tomorrow': [round(p / 1000, 3) for p in tomorrow['prices']], 'unit_of_measurement': 'EUR/kWh',
            'raw_today': [{'start': s, 'end': s, 'value': v} for s, v in zip(at, kwh)]},
            price_fields('raw_today[*].value', 'raw_today[0].start')),
        'entsoe (HACS)': ('attributes', {
            'prices_today': [{'time': s, 'price': round(p / 1000, 5)} for s, p in zip(moments(today, space=True), today['prices'])]},
            price_fields('prices_today[*].price', 'prices_today[0].time')),
        'frank_energie (HACS)': ('attributes', {'prices': [{'from': s, 'till': s, 'price': v} for s, v in zip(at, kwh)]},
            price_fields('prices[*].price', 'prices[0].from')),
        'zonneplan_one (HACS)': ('attributes', {'forecast': [
            {'start_date': s, 'end_date': s, 'price_tax_included': {'amount': int(v * 1e7)}, 'tariff_group': 'normal'}
            for s, v in zip(at, kwh)]}, price_fields('forecast[*].price_tax_included.amount', 'forecast[0].start_date')),
        'octopus_energy (HACS), event': ('attributes', {'rates': [
            {'start': s, 'end': s, 'value_inc_vat': v, 'is_capped': False} for s, v in zip(half(moments(today, offset='+01:00')), half(kwh))]},
            price_fields('rates[*].value_inc_vat', 'rates[0].start')),
        'solcast_solar (HACS)': ('attributes', {'detailedForecast': [
            {'period_start': s, 'pv_estimate': v * 10, 'pv_estimate10': v, 'pv_estimate90': v * 12} for s, v in zip(half(at), half(kwh))]},
            price_fields('detailedForecast[*].pv_estimate', 'detailedForecast[0].period_start')),
        'amberelectric': ('attributes', {'forecasts': [
            {'duration': 30, 'per_kwh': v, 'spot_per_kwh': v, 'start_time': s, 'end_time': s, 'descriptor': 'low'}
            for s, v in zip(half(moments(today, utc=True)), half(kwh))]},
            price_fields('forecasts[*].per_kwh', 'forecasts[0].start_time')),
        'nordpool, get_prices_for_date': ('answer', {'NL': [
            {'start': s, 'end': s, 'price': p} for s, p in zip(moments(today, utc=True), today['prices'])]},
            price_fields('[*][*].price', '[*][0].start')),
        'energyzero, get_energy_prices (quarter)': ('answer', {'prices': [
            {'price': v, 'timestamp': s, 'start': s, 'end': s} for s, v in zip(moments(today, space=True, utc=True), kwh)]},
            price_fields('prices[*].price', 'prices[0].start')),
        'easyenergy, get_energy_usage_prices (quarter)': ('answer', {'prices': [
            {'timestamp': s, 'price': v} for s, v in zip(moments(today, space=True, utc=True), kwh)]},
            price_fields('prices[*].price', 'prices[0].timestamp')),
        'tibber, get_prices': ('answer', {'prices': {'Home': [
            {'start_time': s.replace('+02:00', '.000+02:00'), 'price': v} for s, v in zip(at, kwh)]}},
            price_fields('prices[*][*].price', 'prices[*][0].start_time')),
        'weather, get_forecasts (hourly)': ('answer', {'weather.home': {'forecast': [
            {'datetime': s, 'condition': 'cloudy', 'temperature': 12 + v * 10, 'precipitation': 0.0} for s, v in zip(at[::4], kwh[::4])]}},
            price_fields('[*].forecast[*].temperature', '[*].forecast[0].datetime')),
    }


class Series(unittest.IsolatedAsyncioTestCase):
    """A day of prices or a forecast reaches a plugin whole, from every shape an integration gives it in."""

    def service(self, states, request=None):
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeHA:
            changed, dirty, time_zone, registry = asyncio.Event(), set(), 'Europe/Amsterdam', []

            async def request(self, kind, **data):
                return await request(kind, **data)
        FakeHA.states = states

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}
        return plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')

    def test_every_source_gives_its_whole_day_as_numbers(self):
        from datetime import datetime
        first_slot = int(datetime.fromisoformat(PRICES['days'][1]['start']).timestamp())
        for source, (where, data, fields) in series_sources().items():
            with self.subTest(source):
                spec = pm.check_fields(fields, 'fields')
                got = {name: plugin_fetch.field_value(data, {**field, 'tz': 'Europe/Amsterdam'}) for name, field in spec.items()}
                slots = 24 if source.startswith('weather') else 48 if any(s in source for s in ('octopus', 'solcast', 'amber')) else 96
                self.assertEqual(len(got['prices']), slots)
                self.assertTrue(all(isinstance(p, (int, float)) for p in got['prices']))
                self.assertEqual(got['start'], first_slot)
                # The day as numbers fits a screen's message with room to spare, an answer and a tile alike.
                self.assertLess(len(json.dumps(got['prices'], separators=(',', ':'))), 1300)

    def test_a_tile_of_an_entity_gets_two_days_whole(self):
        _, attrs, _ = series_sources()['nordpool (HACS), raw_today']
        service = self.service({'sensor.price': {'state': '0.1', 'attributes': attrs}})
        kind = pm.check(yaml_manifest('price_peek'), None)['tiles'][0]
        _, part = service.entity_part(kind, {'options': {'plugin_entity': 'sensor.price'}})
        got = part['attributes']
        self.assertEqual((len(got['today']), len(got['tomorrow']), len(got['today_raw'])), (96, 96, 96))  # 16 before 0.5
        self.assertEqual(got['today_raw'], attrs['today'])
        self.assertEqual(got['unit_of_measurement'], 'EUR/kWh')
        self.assertIsInstance(got['starts_at'], int)
        self.assertNotIn('raw_today', got)            # 8 KB of objects never go to the screen
        self.assertLessEqual(len(json.dumps(part, separators=(',', ':'))), 2600)

    def test_lists_too_large_together_are_shortened_alike_from_the_end(self):
        effects = [f'Effect number {i}' for i in range(218)]
        service = self.service({'light.strip': {'state': 'on', 'attributes': {'effect_list': effects, 'options': list(range(300))}}})
        kind = {'id': 't', 'domains': ['light'], 'attributes': ['effect_list', 'options'], 'fields': {}}
        _, part = service.entity_part(kind, {'options': {'plugin_entity': 'light.strip'}})
        got = part['attributes']
        self.assertEqual(len(got['effect_list']), len(got['options']))
        self.assertEqual(got['effect_list'], effects[:len(got['effect_list'])])
        self.assertGreater(len(got['options']), 16)
        self.assertLessEqual(len(json.dumps(part, separators=(',', ':'))), 2600)

    def test_the_entity_list_keeps_to_the_attributes_a_tile_needs(self):
        _, attrs, _ = series_sources()['nordpool (HACS), raw_today']
        service = self.service({'sensor.price': {'attributes': attrs}, 'sensor.temperature': {'attributes': {'unit_of_measurement': 'C'}},
                                'sensor.average': {'attributes': {'raw_today': []}}, 'light.raw': {'attributes': {'raw_today': []}}})
        self.assertEqual(service.entities_with(['sensor'], ['raw_today']), ['sensor.average', 'sensor.price'])
        self.assertEqual(service.entities_with(['sensor'], ['raw_today', 'tomorrow']), ['sensor.price'])

    async def test_an_answer_the_manifest_maps_goes_as_its_fields(self):
        import shutil
        _, answer, _ = series_sources()['nordpool, get_prices_for_date']
        _, quarter, _ = series_sources()['energyzero, get_energy_prices (quarter)']
        sent = []

        async def request(kind, **data):
            return {'response': answer if data['domain'] == 'nordpool' else quarter}
        service = self.service({}, request)
        service.manager.screen = lambda inbox: {'id': inbox, 'node': inbox, 'name': 'Kitchen', 'online': True}
        service.manager.transport = lambda inbox, screen=None: 'action'

        async def send_auxiliary(inbox, message, action, request):
            sent.append(message)
        service.manager.send_auxiliary = send_auxiliary
        plugins_dir = service.folder_root()
        plugins_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / 'tests/fixtures/plugins/price_peek', plugins_dir / 'price_peek')
        service.scan_folders()
        service.store.put('kitchen', {'id': 'price_peek', 'source': 'folder', 'state': 'active'})
        ask = lambda n, command: service.answer({'inbox': 'kitchen', 'plugin': 'price_peek', 'body': json.dumps(
            {'re': n, 'ask': command, 'data': {'config_entry': 'x', 'date': '2026-10-09'}})})
        await ask(1, 'call_service:nordpool.get_prices_for_date')
        result = sent[0]['m']['result']
        self.assertEqual(set(result), {'prices', 'start'})
        self.assertEqual(result['prices'], PRICES['days'][1]['prices'])        # all 96; 24 objects before 0.5
        # An answer without a map goes as it came, bounded by bytes: as many whole slots as fit, never cut open.
        await ask(2, 'call_service:energyzero.get_energy_prices')
        raw = sent[1]['m']['result']['prices']
        self.assertTrue(24 <= len(raw) < 96)
        self.assertEqual(raw[0], quarter['prices'][0])
        for message in sent:
            self.assertLessEqual(len(json.dumps(message['m'])), 3400)


def yaml_manifest(name):
    import yaml
    return yaml.safe_load((ROOT / 'tests/fixtures/plugins' / name / 'tessera-plugin.yaml').read_text())


class SeriesManifest(unittest.TestCase):
    """The manifest's side of plugin API 0.5: fields of an entity and of an answer, has_attributes, the kind numbers."""

    def tile(self, **changes):
        tile = {'id': 'day', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 900, 'domains': ['sensor']}
        tile.update(changes)
        return manifest(tiles=[tile], fetch=[])

    def test_the_price_plugin_passes(self):
        checked = pm.check(yaml_manifest('price_peek'), json.loads(
            (ROOT / 'tests/fixtures/plugins/price_peek/translations/en.json').read_text()))
        self.assertEqual(checked['tiles'][0]['has_attributes'], ['raw_today'])
        self.assertEqual(checked['answers'][0]['fields']['prices']['as'], 'numbers')
        self.assertEqual(checked['answers'][0]['fields']['prices']['path'], [('all',), ('all',), ('key', 'price')])

    def test_wrong_ones_are_refused_with_a_reason(self):
        wrong = {
            'fields without domains': self.tile(domains=[], fields={'p': 'a[*].b'}),
            'has_attributes without domains': self.tile(domains=[], has_attributes=['raw_today']),
            'a field named as an attribute': self.tile(attributes=['today'], fields={'today': {'path': 'raw[*].v', 'as': 'numbers'}}),
            'a field named state': self.tile(fields={'state': 'a'}),
            'an unknown kind': self.tile(fields={'p': {'path': 'a', 'as': 'list'}}),
            'a path with a filter': self.tile(fields={'p': {'path': 'a[?(@.x)]', 'as': 'numbers'}}),
            'a countdown to numbers': self.tile(fields={'p': {'path': 'a[*].t', 'as': 'numbers'}}, preview={'countdown': 'p'}),
            'an answer of a command not allowed': manifest(answers=[{'command': 'call_service:nordpool.get_prices_for_date', 'fields': {'p': 'a'}}]),
            'an answer mapped twice': manifest(permissions={'network': ['api.example.org'], 'ha_commands': ['history/history_during_period']},
                                               answers=[{'command': 'history/history_during_period', 'fields': {'p': 'a'}}] * 2),
        }
        for reason, data in wrong.items():
            with self.subTest(reason), self.assertRaises(pm.ManifestError):
                pm.check(data, ENGLISH)

    def test_a_field_path_may_start_with_a_list_step(self):
        self.assertEqual(pm.parse_path('[*].price', root=False), [('all',), ('key', 'price')])
        self.assertEqual(pm.parse_path('[0]', root=False), [('at', 0)])
        for wrong in ('.price', '$.price', ''):
            with self.subTest(wrong), self.assertRaises(ValueError):
                pm.parse_path(wrong, root=False)

    def test_numbers_keep_gaps_and_refuse_what_json_cannot_carry(self):
        field = {'path': pm.parse_path('[*]', root=False), 'as': 'numbers'}
        self.assertEqual(plugin_fetch.field_value([0.1, None, '0,25', 'x', True, float('nan'), 3], field),
                         [0.1, None, 0.25, None, 1, None, 3])


class PanelSettings(unittest.IsolatedAsyncioTestCase):
    """A plugin's settings on a screen (plugin API 0.6): found by their name in plugin.yaml through the entity registry,
    so a rename in Home Assistant keeps them; a text and a button with its status; only the screen's own entities."""

    def service(self, registry, states):
        import shutil
        import plugins as plugin_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Path(tmp.name) / 'esphome'
        config.mkdir()
        folder = Path(tmp.name) / 'tessera-plugins' / 'voice_probe'
        (folder / 'translations').mkdir(parents=True)
        (folder / 'tessera-plugin.yaml').write_text(
            'id: voice_probe\nversion: 1.0.0\napi: "0.6"\nicon: microphone\nmaintainer: someone\nlicense: MIT\ntopics: [voice]\n'
            'settings:\n  - { key: wake_word, label: word }\n  - { key: spotify_market, label: market }\n'
            '  - { key: test_wake, label: test, status: test_wake_result }\n')
        (folder / 'translations' / 'en.json').write_text(json.dumps(
            {'app': {'name': 'Voice', 'summary': 'Voice.', 'word': 'Word', 'market': 'Market', 'test': 'Test'}, 'screen': {}}))
        calls = []

        class FakeHA:
            changed, dirty = asyncio.Event(), set()

            async def call_service(self, domain, service, data):
                calls.append((domain, service, data))
        FakeHA.registry, FakeHA.states = registry, states

        class FakeManager:
            ha = FakeHA()
            page_senders, aliases = {}, {}

            def screen(self, inbox):
                return {'id': inbox, 'device_id': 'dev1', 'online': True}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', config)
        service.scan_folders()
        service.store.put('kitchen', {'id': 'voice_probe', 'source': 'folder', 'state': 'active'})
        return service, calls

    def esphome(self, entity_id, name, device='dev1'):
        return {'entity_id': entity_id, 'device_id': device, 'platform': 'esphome', 'original_name': name}

    async def test_found_by_name_after_a_rename_and_never_on_another_device(self):
        registry = [self.esphome('select.my_kitchen_word', 'Wake word'),          # renamed in Home Assistant
                    self.esphome('text.kitchen_spotify_market', 'Spotify market'),
                    self.esphome('button.kitchen_test_wake', 'Test wake'),
                    self.esphome('sensor.kitchen_test_wake_result', 'Test wake result'),
                    self.esphome('select.hall_wake_word', 'Wake word', device='dev2')]
        states = {'select.my_kitchen_word': {'state': 'Okay Nabu', 'attributes': {'options': ['Okay Nabu', 'Hey Jarvis']}},
                  'text.kitchen_spotify_market': {'state': 'NL', 'attributes': {'min': 2, 'max': 2, 'mode': 'text'}},
                  'button.kitchen_test_wake': {'state': 'unknown'},
                  'sensor.kitchen_test_wake_result': {'state': 'Heard: Okay Nabu'}}
        service, calls = self.service(registry, states)
        rows = {row['key']: row for row in service.settings_for('kitchen')[0]['rows']}
        self.assertEqual(rows['wake_word']['entity'], 'select.my_kitchen_word')
        self.assertEqual(rows['wake_word']['options'], ['Okay Nabu', 'Hey Jarvis'])
        self.assertEqual((rows['spotify_market']['kind'], rows['spotify_market']['value'], rows['spotify_market']['max']), ('text', 'NL', 2))
        self.assertEqual((rows['test_wake']['kind'], rows['test_wake']['status']), ('button', 'Heard: Okay Nabu'))
        self.assertTrue(rows['test_wake']['available'])            # a button that was never pressed is there
        await service.set_setting('kitchen', 'button.kitchen_test_wake', True)
        await service.set_setting('kitchen', 'text.kitchen_spotify_market', 'BE')
        await service.set_setting('kitchen', 'select.my_kitchen_word', 'Hey Jarvis')
        self.assertEqual(calls, [('button', 'press', {'entity_id': 'button.kitchen_test_wake'}),
                                 ('text', 'set_value', {'entity_id': 'text.kitchen_spotify_market', 'value': 'BE'}),
                                 ('select', 'select_option', {'entity_id': 'select.my_kitchen_word', 'option': 'Hey Jarvis'})])
        for entity, value in (('text.kitchen_spotify_market', 'NLD'),            # longer than the entity takes
                              ('button.kitchen_test_wake', 'yes'),
                              ('sensor.kitchen_test_wake_result', 'x'),          # a status is shown, never set
                              ('select.hall_wake_word', 'Hey Jarvis')):           # another screen's entity
            with self.subTest(entity), self.assertRaises(ValueError):
                await service.set_setting('kitchen', entity, value)

    def test_the_object_id_is_esphomes(self):
        import plugins as plugin_service
        for name, key in (('Tap sound', 'tap_sound'), ('Mic gain (dB)', 'mic_gain__db_'), ('AEC', 'aec'), ('Wake-word', 'wake-word')):
            self.assertEqual(plugin_service.Plugins.object_id(name), key)

    def test_a_status_is_an_id_too(self):
        good = manifest(settings=[{'key': 'test_wake', 'label': 'tile', 'status': 'test_wake_result'}])
        self.assertEqual(pm.check(good, ENGLISH)['settings'][0]['status'], 'test_wake_result')
        with self.assertRaises(pm.ManifestError):
            pm.check(manifest(settings=[{'key': 'test_wake', 'label': 'tile', 'status': 'Test wake result'}]), ENGLISH)


MUSIC_ENGLISH = {'app': {'name': 'New music', 'summary': 'New releases.', 'tile': 'Releases', 'artists': 'Artists',
                         'kinds': 'Kinds', 'album': 'Albums', 'single': 'Singles', 'tags': 'Tags'}, 'screen': {}}


def music(**changes):
    """New music (plugin API 0.12): artists found by searching, one ask per artist, the answers as one list."""
    data = {
        'id': 'music', 'version': '1.0.0', 'api': '0.12', 'icon': 'music', 'maintainer': 'someone', 'license': 'MIT',
        'topics': ['media'], 'permissions': {'network': ['api.deezer.com'], 'home_assistant_actions': ['music_assistant.play_media']},
        'attributes': ['cloud'], 'privacy': 'https://example.org/p',
        'tiles': [{'id': 'releases', 'name': 'tile', 'sizes': {'min': '1x1', 'max': '2x2'}, 'memory': 1200,
                   'data': 'releases', 'preview': {'title': '{title}', 'badge': '{artist}'}, 'options': [
                       {'id': 'artists', 'kind': 'choice', 'multiple': 8, 'options_from': 'artist_search', 'search': True,
                        'label': 'artists'},
                       {'id': 'kinds', 'kind': 'choice', 'multiple': 2, 'label': 'kinds',
                        'choices': [{'value': 'album', 'label': 'album'}, {'value': 'single', 'label': 'single'}]},
                       {'id': 'tags', 'kind': 'text', 'multiple': 4, 'label': 'tags', 'default': ['new']}]}],
        'fetch': [
            {'id': 'releases', 'each': 'artists', 'url': 'https://api.deezer.com/artist/{artists}/albums?limit=25',
             'every': '6h', 'map': {'items': '$.data[*]', 'fields': {
                 'title': 'title', 'date': {'path': 'release_date', 'as': 'epoch', 'tz': 'UTC'}, 'kind': 'record_type',
                 'artist': {'each': 'label'}, 'id': {'each': 'value'}}, 'sort': '-date', 'limit': 4}},
            {'id': 'artist_search', 'url': 'https://api.deezer.com/search/artist?q={search}', 'every': '1d',
             'map': {'items': '$.data[*]', 'value': 'id', 'label': 'name'}}],
    }
    data.update(changes)
    return data


class JsonValues(unittest.IsolatedAsyncioTestCase):
    """Plugin API 0.12: an option keeps a list (texts, or picks of a choice with their words), a choice is found by
    searching, a fetch asks once per value and puts the answers together, and a list joins into one ask."""

    def test_the_manifest_takes_lists_searches_and_each(self):
        out = pm.check(music(), MUSIC_ENGLISH)
        artists, kinds, tags = out['tiles'][0]['options']
        self.assertEqual((artists['multiple'], artists['search'], artists['default']), (8, True, []))
        self.assertTrue(pm.keeps_picks(artists) and pm.keeps_picks(kinds) and not pm.keeps_picks(tags))
        self.assertEqual(tags['default'], ['new'])
        self.assertEqual(out['fetch'][0]['each'], 'artists')
        self.assertEqual(out['fetch'][1]['placeholders'], ['search'])

    def test_wrong_ones_say_why(self):
        tile = music()['tiles'][0]
        artist, kinds, tags = tile['options']

        def with_options(*options, fetch=None):
            changed = json.loads(json.dumps(music()))
            changed['tiles'][0]['options'] = list(options)
            if fetch:
                changed['fetch'][0].update(fetch)
            return changed
        cases = {
            'only a text or a choice keeps several values': with_options({**tags, 'kind': 'toggle', 'default': False}),
            'must be between 2 and 16': with_options(artist, kinds, {**tags, 'multiple': 17}),
            'starts empty': with_options({**artist, 'default': [{'value': '1', 'label': 'x'}]}, kinds, tags),
            'search': with_options(artist, {**kinds, 'search': True}, tags),
            '"each" asks once per value': with_options({k: v for k, v in artist.items() if k != 'multiple'}, kinds, tags),
            'joins them': with_options(artist, kinds, tags, fetch={'each': None, 'url': 'https://api.deezer.com/a/{artists}'}),
            'is not this fetch\'s "each"': with_options(artist, kinds, tags, fetch={'url': 'https://api.deezer.com/a/{artists|,}'}),
            'only in a fetch with "each"': with_options(artist, kinds, tags, fetch={'each': None, 'url': 'https://api.deezer.com/a/{artists|,}'}),
        }
        for reason, manifest in cases.items():
            manifest['fetch'][0] = {k: v for k, v in manifest['fetch'][0].items() if v is not None}
            with self.subTest(reason), self.assertRaises(pm.ManifestError) as caught:
                pm.check(manifest, MUSIC_ENGLISH)
            if reason == '"each" asks once per value':
                self.assertIn('"multiple"', str(caught.exception))
            elif reason != 'search':
                self.assertIn(reason, str(caught.exception))

    def test_a_value_fits_its_option_or_not(self):
        artists, kinds, tags = pm.check(music(), MUSIC_ENGLISH)['tiles'][0]['options']
        picks = [{'value': '9635624', 'label': 'Billie Eilish'}, {'value': '27'}]
        self.assertEqual(pm.option_value(artists, picks), [picks[0], {'value': '27', 'label': '27'}])
        self.assertEqual(pm.option_value(kinds, [{'value': 'single', 'label': 'Singles'}]), [{'value': 'single', 'label': 'Singles'}])
        self.assertEqual(pm.option_value(tags, ['a', 'b']), ['a', 'b'])
        single = {**artists, 'multiple': None}
        self.assertEqual(pm.option_value(single, {'value': '1', 'label': 'One'}), {'value': '1', 'label': 'One'})
        self.assertEqual(pm.option_value(single, ''), '')
        for option, value in ((artists, ['9635624']), (artists, picks * 5), (artists, [picks[0], picks[0]]),
                              (kinds, [{'value': 'ep', 'label': 'EP'}]), (tags, ['a', '']), (tags, 'a'),
                              (tags, ['x' * 65]), (artists, [{'value': '1', 'label': 'x', 'more': 1}]), (single, '1')):
            with self.subTest(value=value), self.assertRaises(pm.ManifestError):
                pm.option_value(option, value)

    def test_the_stored_shape(self):
        ok = {'artists': [{'value': '1', 'label': 'One'}], 'tags': ['a'], 'pick': {'value': '2', 'label': ''},
              'n': 3, 'on': True, 'word': 'x'}
        self.assertTrue(core.plugin_options(ok))
        for wrong in ({'a': [[1]]}, {'a': [{'value': ''}]}, {'a': ['x'] * 17}, {'a': {'value': '1', 'deep': {}}},
                      {'a': [{'value': '1', 'label': 'é' * 65}]}, {'a': [1]},
                      {f'o{i}': [{'value': f'{i}{j}', 'label': 'l' * 60} for j in range(4)] for i in range(5)}):
            with self.subTest(wrong=str(wrong)[:60]):
                self.assertFalse(core.plugin_options(wrong))

    def test_one_number_everywhere(self):
        self.assertEqual((core.PLUGIN_LIST_MAX, core.PLUGIN_OPTIONS_BYTES), (pm.MAX_MULTIPLE, pm.OPTIONS_BYTES))
        model = (ROOT / 'web/src/model/plugins.ts').read_text()
        self.assertTrue(f'PLUGIN_OPTIONS_BYTES = {pm.OPTIONS_BYTES}' in model, 'the editor keeps another budget')
        self.assertTrue(f'PLUGIN_LIST_MAX = {pm.MAX_MULTIPLE}' in model, 'the editor keeps another list length')

    def test_words_and_joins(self):
        self.assertEqual(plugin_fetch.words_of({'on': True, 'off': False, 'n': 3.0, 'x': 2.5, 'pick': {'value': '7', 'label': 'L'},
                                                'list': [{'value': 'a'}, 'b', {'value': ''}]}),
                         {'on': 'true', 'off': 'false', 'n': '3', 'x': '2.5', 'pick': '7', 'list': ['a', 'b']})
        fetch = {'url': 'https://api.example.org/q?ids={ids|,}&k={key}', 'headers': {'X-Ids': '{ids|;}'},
                 'placeholders': ['ids', 'key']}
        url, headers = plugin_fetch.fill(fetch, {'ids': ['a b', 'c,d']}, {'key': 's'})
        self.assertEqual(url, 'https://api.example.org/q?ids=a%20b,c%2Cd&k=s')
        self.assertEqual(headers, {'X-Ids': 'a b;c,d'})
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill(fetch, {'ids': []}, {'key': 's'})
        with self.assertRaises(plugin_fetch.FetchRefused):
            plugin_fetch.fill({'url': 'https://x.org/{ids}', 'headers': {}, 'placeholders': ['ids']}, {'ids': ['a']}, {})

    def service(self, answers):
        import plugins as plugin_service
        from types import SimpleNamespace
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class FakeManager:
            ha = type('HA', (), {'states': {}, 'time_zone': 'UTC', 'changed': asyncio.Event(), 'dirty': set()})()
            page_senders, layouts = {}, {}
        service = plugin_service.Plugins(FakeManager(), Path(tmp.name) / 'data', Path(tmp.name) / 'esphome')
        asked = []

        async def download(url, headers, network):
            asked.append(url)
            answer = answers.get(url)
            if isinstance(answer, Exception) or answer is None:
                raise answer or OSError('HTTP 404')
            return answer
        service.fetcher.download = download
        service.secret_values = lambda entry, inbox=None: {}
        checked = pm.check(music(), MUSIC_ENGLISH)
        entry = SimpleNamespace(id='music', manifest=checked, fetch=lambda i: next(f for f in checked['fetch'] if f['id'] == i),
                                tile=lambda i: checked['tiles'][0], text=lambda key, language='en': key)
        return service, entry, checked['tiles'][0], asked

    ALBUMS = 'https://api.deezer.com/artist/{}/albums?limit=25'

    async def test_one_ask_per_artist_and_one_list_newest_first(self):
        answers = {self.ALBUMS.format('1'): {'data': [{'title': 'Old', 'release_date': '2024-01-01', 'record_type': 'album'},
                                                      {'title': 'Newest', 'release_date': '2026-10-01', 'record_type': 'single'}]},
                   self.ALBUMS.format('2'): {'data': [{'title': 'Middle', 'release_date': '2025-05-05', 'record_type': 'album'}]}}
        service, entry, tile, asked = self.service(answers)
        chosen = service.values_of(entry, tile, {'artists': [{'value': '1', 'label': 'One'}, {'value': '2', 'label': 'Two'}]})
        data = await service.tile_data(entry, tile, chosen)
        self.assertEqual(sorted(asked), sorted(answers))
        self.assertEqual([(i['title'], i['artist'], i['id']) for i in data['items']],
                         [('Newest', 'One', '1'), ('Middle', 'Two', '2'), ('Old', 'One', '1')])
        self.assertNotIn('stale', data)
        # A second tile with one of the same artists shares its ask.
        await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [{'value': '2', 'label': 'Two'}]}))
        self.assertEqual(len(asked), 2)

    async def test_an_artist_that_fails_is_left_out_and_the_list_is_stale(self):
        service, entry, tile, _ = self.service({self.ALBUMS.format('1'): {'data': [{'title': 'A', 'release_date': '2026-01-01'}]},
                                                self.ALBUMS.format('2'): OSError('HTTP 503')})
        data = await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [
            {'value': '1', 'label': 'One'}, {'value': '2', 'label': 'Two'}]}))
        self.assertEqual([i['title'] for i in data['items']], ['A'])
        self.assertTrue(data['stale'])
        none = await service.tile_data(entry, tile, service.values_of(entry, tile, {'artists': [{'value': '2', 'label': 'Two'}]}))
        self.assertEqual(none, {'wait': 'failed'})
        empty = await service.tile_data(entry, tile, service.values_of(entry, tile, {}))
        self.assertEqual(empty, {'wait': 'not_filled'})

    async def test_a_search_asks_with_what_was_typed(self):
        url = 'https://api.deezer.com/search/artist?q=billie%20e'
        service, entry, _, asked = self.service({url: {'data': [{'id': 9635624, 'name': 'Billie Eilish'}]}})
        service.known = lambda plugin, inbox=None: entry
        out = await service.choices('music', 'artist_search', {'kinds': [{'value': 'album', 'label': 'Albums'}]}, search=' billie e ')
        self.assertEqual(out, {'choices': [{'value': '9635624', 'label': 'Billie Eilish'}]})
        self.assertEqual(asked, [url])
        self.assertEqual(service.fetcher.cache[next(iter(service.fetcher.cache))]['every'], 600)
        self.assertEqual(await service.choices('music', 'artist_search', {}), {'choices': [], 'wait': 'not_filled'})

    async def test_the_options_count_in_the_message(self):
        service, entry, tile, _ = self.service({})
        service.known = lambda plugin, inbox=None: entry
        long = [{'value': f'{i:02d}' * 30, 'label': 'L' * 60} for i in range(8)]
        items = {'items': [{'title': 'x' * 40, 'n': i} for i in range(60)]}

        async def data(*args, **kwargs):
            return dict(items)
        service.tile_data = data
        message = await service.tile_message(0, {'entity': 'plugin:music.releases', 'name': 'N' * 80,
                                                 'options': {'plugin': {'artists': long}}})
        import page_delivery
        size = len(json.dumps({**message, 'v': 2, 'session': '0' * 16, 'seq': 0xFFFFFFFF, 'rev': '0' * 16, 'slot': 63},
                              ensure_ascii=False, separators=(',', ':')).encode())
        self.assertLessEqual(size, page_delivery.MAX_MESSAGE)
        self.assertGreater(len(message['x']['items']), 10)


class CardPictures(unittest.TestCase):
    """Pictures on a plugin's card over the page (plugin API 0.13): the manifest's `pictures` of a card, the card's
    question, and where its pictures may come from."""

    def checked(self, **card):
        data = manifest(api='0.13', cards=[{'id': 'release', 'name': 'tile', **card}])
        return pm.check(data, ENGLISH)

    def question(self, **changes):
        request = {'tiles': 'plugin:bus.release', 'idx': '0', 'card': '1', 'for': '', 'bg': '202020', 'dark': '0',
                   'atlas': '[[300,0,160,160,8,0]]', 'src': '["https://api.example.org/cover.jpg"]', 'fit': '["cover"]'}
        request.update(changes)
        return plugin_pictures.parse(request, (480, 480))

    def test_a_card_may_have_places(self):
        self.assertEqual(self.checked(pictures=1)['cards'][0]['pictures'], 1)
        self.assertEqual(self.checked()['cards'][0]['pictures'], 0)           # none without the field, as before
        for wrong in (9, -1, 1.5, 'one'):
            with self.subTest(wrong), self.assertRaises(pm.ManifestError):
                self.checked(pictures=wrong)

    def test_the_question_names_the_card_and_what_it_shows(self):
        q = self.question()
        self.assertEqual((q.card, q.plugin, q.tile, q.index, q.of), (True, 'bus', 'release', None, ''))
        self.assertEqual(self.question(**{'for': 'media_player.kitchen'}).of, 'media_player.kitchen')
        self.assertEqual(self.question(idx='').index, None)                    # a card has no index of its own
        for bad in ({'for': 'screen.clock'}, {'for': 'not an entity'}, {'tiles': 'media_player.kitchen'}):
            self.assertIsNone(self.question(**bad), bad)
        tile = plugin_pictures.parse({'tiles': 'plugin:bus.next', 'idx': '3', 'bg': '202020', 'atlas': '[[0,0,60,90,6,0]]',
                                      'src': '["https://api.example.org/a.jpg"]'}, (480, 480))
        self.assertFalse(tile.card)   # a tile's question as before

    def test_where_a_cards_picture_may_come_from(self):
        checked = self.checked(pictures=1)
        card = checked['cards'][0]
        self.assertEqual(plugin_pictures.allowed('https://api.example.org/cover.jpg', checked, card, False), 'network')
        self.assertIsNone(plugin_pictures.allowed('https://image.tmdb.org/cover.jpg', checked, card, False))
        # Home Assistant's own pictures only for a card shown for an entity of the layout.
        self.assertIsNone(plugin_pictures.allowed('/api/image_proxy/media_player.kitchen', checked, card, False))
        self.assertEqual(plugin_pictures.allowed('/api/image_proxy/media_player.kitchen', checked, card, True), 'home_assistant')
        self.assertIsNone(plugin_pictures.allowed('https://api.example.org/cover.jpg', checked, self.checked()['cards'][0], False))
        q = self.question()
        self.assertIsNone(plugin_pictures.refused(q, checked, card, False))
        self.assertIn('no pictures', plugin_pictures.refused(q, self.checked(), self.checked()['cards'][0], False))
        self.assertIn('no such card', plugin_pictures.refused(q, checked, None, False))
        self.assertIn('allows 1', plugin_pictures.refused(self.question(atlas='[[0,0,60,60,0,0],[100,0,60,60,0,0]]',
                                                                        src='["https://api.example.org/a.jpg","https://api.example.org/b.jpg"]',
                                                                        fit='["cover","cover"]'), checked, card, False))
