"""Likes, ratings and counting of plugins (docs/PLUGINS.md, "Likes, ratings and counting"; plugin_likes.py): what goes
to Tessera's website and when, the stars card's timing, counting's day, and the file an older app also reads."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager' / 'app'))

import plugin_likes  # noqa: E402
import plugins as plugin_service  # noqa: E402

DAY = 86400
KEY = 'a' * 64


class Website:
    """Tessera's website as far as the add-on talks to it: it notes every request and answers as the real one does."""

    def __init__(self):
        self.requests = []
        self.down = False
        self.ratings = {}

    async def handle(self, request):
        body = await request.json() if request.can_read_body else None
        self.requests.append((request.method, request.path, request.headers.get('Authorization'), body))
        if self.down:
            return web.json_response({'message': 'Server Error'}, status=500)
        plugin = request.match_info.get('plugin')
        if request.path.endswith('/rating'):
            if request.method == 'PUT':
                self.ratings[plugin] = body['stars']
            else:
                self.ratings.pop(plugin, None)
            count = len(self.ratings)
            return web.json_response({'data': {'plugin': plugin, 'stars': self.ratings.get(plugin), 'rating': 4.5 if count >= 3 else None,
                                               'ratings': count}})
        if request.path.endswith('/like'):
            return web.json_response({'data': {'plugin': plugin, 'liked': request.method == 'PUT', 'likes': 3}})
        return web.json_response({'data': {'plugins': len((body or {}).get('plugins') or [])}})


class SharingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.site = Website()
        app = web.Application()
        app.router.add_route('*', '/api/v1/addon/plugins/usage', self.site.handle)
        app.router.add_route('*', '/api/v1/addon/plugins/{plugin}/rating', self.site.handle)
        app.router.add_route('*', '/api/v1/addon/plugins/{plugin}/like', self.site.handle)
        self.server = TestServer(app)
        await self.server.start_server()
        base = str(self.server.make_url('/api/v1/addon'))
        self.urls = {name: getattr(plugin_likes, name) for name in ('LIKE_URL', 'RATE_URL', 'USAGE_URL')}
        plugin_likes.LIKE_URL = f'{base}/plugins/{{plugin}}/like'
        plugin_likes.RATE_URL = f'{base}/plugins/{{plugin}}/rating'
        plugin_likes.USAGE_URL = f'{base}/plugins/usage'
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000.0
        self.path = Path(self.tmp.name) / 'plugin_likes.json'
        self.likes = plugin_likes.Likes(self.path, clock=lambda: self.now)

    async def asyncTearDown(self):
        for name, value in self.urls.items():
            setattr(plugin_likes, name, value)
        await self.server.close()
        self.tmp.cleanup()

    def stored(self):
        return json.loads(self.path.read_text())


class Ratings(SharingTest):
    async def test_stars_go_with_the_version_and_the_screen_model_and_a_rating_is_taken_back(self):
        result = await self.likes.rate('waste_collection', 4, '1.0.7', 'cyd')
        self.assertEqual(result, {'stars': 4, 'rating': None, 'ratings': 1})
        method, path, bearer, body = self.site.requests[-1]
        self.assertEqual((method, path, body), ('PUT', '/api/v1/addon/plugins/waste_collection/rating',
                                                {'stars': 4, 'version': '1.0.7', 'board_id': 'cyd'}))
        key = self.stored()['key']
        self.assertEqual(bearer, f'Bearer {key}')
        self.assertEqual(self.likes.stars('waste_collection'), 4)
        self.assertEqual(self.stored()['rated'], {'waste_collection': {'stars': 4, 'version': '1.0.7', 'board': 'cyd'}})

        self.assertEqual((await self.likes.rate('waste_collection', None))['stars'], None)
        self.assertEqual(self.site.requests[-1][:2], ('DELETE', '/api/v1/addon/plugins/waste_collection/rating'))
        self.assertIsNone(self.likes.stars('waste_collection'))

    async def test_only_one_to_five_stars_and_a_failure_keeps_what_was_there(self):
        for stars in (0, 6, 4.5, True, '4'):
            with self.assertRaises(ValueError):
                await self.likes.rate('waste_collection', stars)
        self.assertEqual(self.site.requests, [])
        await self.likes.rate('waste_collection', 5, 'v 1 (dirty)', 'Not A Board')
        self.assertEqual(self.site.requests[-1][3], {'stars': 5})
        self.site.down = True
        with self.assertRaisesRegex(ValueError, 'rate_failed'):
            await self.likes.rate('waste_collection', 2)
        self.assertEqual(self.likes.stars('waste_collection'), 5)

    async def test_a_like_needs_no_screen_that_runs_the_plugin(self):
        result = await self.likes.send('vinyl_deck', True, consent=True)
        self.assertEqual(result, {'liked': True, 'likes': 3})
        self.assertTrue(self.likes.liked('vinyl_deck'))


class TheCard(SharingTest):
    def test_it_asks_five_days_after_a_screen_first_ran_the_plugin_longest_first(self):
        self.likes.saw('kitchen', ['waste_collection'])
        self.now += DAY
        self.likes.saw('kitchen', ['waste_collection', 'ov_departures'])
        self.likes.saw('hall', ['ov_departures'])
        self.now += 4 * DAY - 1
        self.assertIsNone(self.likes.ask_for('kitchen', ['waste_collection', 'ov_departures']))
        self.now += 1
        self.assertEqual(self.likes.ask_for('kitchen', ['waste_collection', 'ov_departures']), ('waste_collection', 5))
        self.assertIsNone(self.likes.ask_for('hall', ['ov_departures']))
        self.now += DAY
        self.assertEqual(self.likes.ask_for('hall', ['ov_departures']), ('ov_departures', 5))
        # A plugin the screen no longer has is not asked about, however long it ran.
        self.assertEqual(self.likes.ask_for('kitchen', ['ov_departures']), ('ov_departures', 5))

    async def test_a_rating_ends_it_later_waits_fourteen_days_twice_and_never_stops_every_card(self):
        self.likes.saw('kitchen', ['waste_collection', 'ov_departures'])
        self.now += 6 * DAY
        await self.likes.rate('waste_collection', 5)
        self.assertEqual(self.likes.ask_for('kitchen', ['waste_collection', 'ov_departures'])[0], 'ov_departures')
        self.likes.later('ov_departures')
        self.assertIsNone(self.likes.ask_for('kitchen', ['ov_departures']))
        self.now += 14 * DAY
        self.assertEqual(self.likes.ask_for('kitchen', ['ov_departures'])[0], 'ov_departures')
        self.likes.later('ov_departures')
        self.now += 100 * DAY
        self.assertIsNone(self.likes.ask_for('kitchen', ['ov_departures']))

        self.likes.saw('kitchen', ['tap_sound'])
        self.now += 6 * DAY
        self.likes.never()
        self.assertIsNone(self.likes.ask_for('kitchen', ['tap_sound']))
        self.assertFalse(self.likes.view()['asking'])
        self.likes.never(asking=True)
        self.assertEqual(self.likes.ask_for('kitchen', ['tap_sound', 'ov_departures'])[0], 'ov_departures')


class Counting(SharingTest):
    PLUGINS = [{'id': 'waste_collection', 'version': '1.0.7', 'boards': ['cyd', 'guition']}]

    async def test_off_until_turned_on_then_once_a_day_and_soon_after_a_change(self):
        self.assertFalse(self.likes.usage_due(self.PLUGINS))
        await self.likes.set_counting(True)
        self.assertEqual(self.site.requests, [])
        self.assertTrue(self.likes.usage_due(self.PLUGINS))
        self.assertTrue(await self.likes.send_usage(self.PLUGINS))
        self.assertEqual(self.site.requests[-1][:2], ('PUT', '/api/v1/addon/plugins/usage'))
        self.assertEqual(self.site.requests[-1][3], {'plugins': self.PLUGINS})
        self.now += 2 * 3600
        self.assertFalse(self.likes.usage_due(self.PLUGINS))
        changed = [*self.PLUGINS, {'id': 'tap_sound', 'version': '0.2.1', 'boards': ['guition']}]
        self.assertTrue(self.likes.usage_due(changed))
        self.now += DAY
        self.assertTrue(self.likes.usage_due(self.PLUGINS))

    async def test_one_that_did_not_go_waits_an_hour_and_off_deletes_what_was_counted(self):
        await self.likes.set_counting(True)
        self.site.down = True
        self.assertFalse(await self.likes.send_usage(self.PLUGINS))
        self.now += 3599
        self.assertFalse(self.likes.usage_due(self.PLUGINS))
        self.now += 1
        self.assertTrue(self.likes.usage_due(self.PLUGINS))
        self.site.down = False
        await self.likes.send_usage(self.PLUGINS)
        await self.likes.set_counting(False)
        self.assertEqual(self.site.requests[-1][:2], ('DELETE', '/api/v1/addon/plugins/usage'))
        self.assertEqual(self.likes.view()['counting'], False)
        self.assertIsNone(self.stored()['counted'])
        self.assertFalse(self.likes.usage_due(self.PLUGINS))

    async def test_turning_off_what_never_went_asks_nothing(self):
        await self.likes.set_counting(True)
        await self.likes.set_counting(False)
        self.assertEqual(self.site.requests, [])
        self.assertTrue(self.likes.view()['counting_asked'])


class TheFile(unittest.TestCase):
    def test_an_older_apps_file_keeps_its_likes_and_gains_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plugin_likes.json'
            path.write_text(json.dumps({'version': 1, 'key': KEY, 'consented': True, 'liked': ['tap_sound']}))
            likes = plugin_likes.Likes(path)
            self.assertTrue(likes.liked('tap_sound') and likes.consented())
            self.assertEqual(likes.view(), {'consented': True, 'counting': False, 'counting_asked': False, 'asking': True,
                                            'counted': None, 'usable': True})
            likes.later('tap_sound')
            data = json.loads(path.read_text())
            self.assertEqual((data['version'], data['key'], data['liked']), (1, KEY, ['tap_sound']))
            self.assertNotIn('key', likes.view())

    def test_a_newer_apps_file_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plugin_likes.json'
            path.write_text(json.dumps({'version': 2, 'key': KEY}))
            likes = plugin_likes.Likes(path)
            self.assertFalse(likes.usable)
            likes.saw('kitchen', ['tap_sound'])
            self.assertIsNone(likes.ask_for('kitchen', ['tap_sound']))
            self.assertEqual(json.loads(path.read_text()), {'version': 2, 'key': KEY})


class TheApp(unittest.IsolatedAsyncioTestCase):
    """Plugins: which plugins a rating and counting speak of, and the card's view for a screen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        screens = [{'id': 'kitchen', 'board': 'cyd', 'name': 'Kitchen'}, {'id': 'hall', 'board': 'guition', 'name': 'Hall'}]
        sender = type('Sender', (), {'plugin_api': '0.16', 'plugins': [{'id': 'waste_collection', 'version': '1.0.7'}]})()

        class Manager:
            page_senders = {'kitchen': sender}

            def screens(self):
                return screens
        self.service = plugin_service.Plugins(Manager(), Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'esphome')
        repo = 'https://github.com/maxgramser/tessera-plugins'

        def entry(plugin, path):
            return type('Entry', (), {'id': plugin, 'origin': plugin_service.origin_of(repo, path), 'repo': repo,
                                      'texts': {'name': {'en': plugin.title()}}, 'label': 'tessera', 'image': None,
                                      'manifest': {'maintainer': 'MaxGramser'}})()
        self.service.index = {'waste_collection': entry('waste_collection', 'plugins/waste_collection'),
                              'tap_sound': entry('tap_sound', 'plugins/tap_sound')}
        record = lambda plugin, version, **extra: {'id': plugin, 'version': version, 'source': 'index', 'repo': repo,
                                                   'path': f'plugins/{plugin}', 'state': 'active', **extra}
        self.service.store.put('kitchen', record('waste_collection', '1.0.7'))
        self.service.store.put('hall', record('waste_collection', '1.0.7'))
        self.service.store.put('hall', record('tap_sound', '0.2.1', state='building'))
        self.service.store.put('hall', record('ov_departures', '1.2.4'))
        # The same id from a fork is not the plugin others count.
        self.service.store.put('kitchen', {**record('tap_sound', '0.2.1'), 'source': 'link', 'repo': 'https://github.com/someone/fork'})

    def test_counting_speaks_of_the_index_plugins_from_its_own_origin_with_every_screen_model(self):
        self.assertEqual(self.service.usage(), [{'id': 'waste_collection', 'version': '1.0.7', 'boards': ['cyd', 'guition']}])

    def test_the_card_asks_on_the_screen_that_ran_it_five_days(self):
        now = [1_800_000_000.0]
        self.service.liker.clock = lambda: now[0]
        self.assertIsNone(self.service.ask_card({'id': 'kitchen'}))
        now[0] += 5 * DAY
        card = self.service.ask_card({'id': 'kitchen'})
        self.assertEqual({k: card[k] for k in ('plugin', 'days', 'version', 'board', 'ask_counting', 'maintainer', 'issues')},
                         {'plugin': 'waste_collection', 'days': 5, 'version': '1.0.7', 'board': 'cyd', 'ask_counting': True,
                          'maintainer': 'MaxGramser', 'issues': 'https://github.com/maxgramser/tessera-plugins/issues/new'})
        # The hall has it too, but has not said so in a hello: no card there.
        self.assertIsNone(self.service.ask_card({'id': 'hall'}))

    async def test_a_like_of_a_plugin_no_screen_runs_goes_and_one_outside_the_index_does_not(self):
        sent = []

        async def send(plugin, like, consent=False):
            sent.append((plugin, like, consent))
            return {'liked': like, 'likes': 1}
        self.service.liker.send = send
        self.service.index['vinyl_deck'] = self.service.index['tap_sound']
        self.assertEqual(await self.service.like('vinyl_deck', True, True), {'liked': True, 'likes': 1})
        with self.assertRaises(ValueError):
            await self.service.like('weather_radar', True, True)
        self.assertEqual(sent, [('vinyl_deck', True, True)])

    async def test_stars_need_a_screen_that_runs_it_and_take_that_screens_model(self):
        rated = []

        async def rate(plugin, stars, version=None, board=None):
            rated.append((plugin, stars, version, board))
            return {'stars': stars, 'rating': None, 'ratings': 1}
        self.service.liker.rate = rate
        with self.assertRaises(ValueError):
            await self.service.rate('tap_sound', 4)
        result = await self.service.rate('waste_collection', 4, 'hall')
        self.assertEqual(rated, [('waste_collection', 4, '1.0.7', 'guition')])
        self.assertEqual((result['stars'], result['ratings']), (4, 1))


if __name__ == '__main__':
    unittest.main()
