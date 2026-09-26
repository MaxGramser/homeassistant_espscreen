"""Does this screen work as you expect (app 0.3.10): one shared answer per board, sent to the Tessera website.

Nothing here reaches the website: the transport is a stand-in that records what it was given and answers as the website
would. The rules come from the website's integration guide: a random key per board, stored with the answer and its
revision before the first request; one request at a time per board; retries that never resurrect an older or deleted
answer; nothing sent when the card only shows, on Later, or on Don't ask again.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import feedback
    from feedback import Feedback
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app
    from test_screen_owned_settings import fake_ha

DAY = 24 * 3600


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class Website:
    """The website as far as the add-on can tell: one latest answer per key."""

    def __init__(self):
        self.requests, self.rows, self.answers = [], {}, []
        self.gate = None

    async def __call__(self, session, token, payload=None, *, delete=False):
        self.requests.append(('DELETE' if delete else 'POST', token, payload))
        if self.gate:
            await self.gate.wait()
        if self.answers:
            return self.answers.pop(0)
        if delete:
            self.rows.pop(token, None)
            return {'state': 'deleted'}
        row = self.rows.get(token)
        if row and (payload['revision'] < row['revision'] or (payload['revision'] == row['revision'] and payload != row)):
            return {'state': 'conflict'}
        self.rows[token] = payload
        return {'state': 'saved', 'revision': payload['revision']}


async def catalogue(session):
    return {'cyd', 'guition', 'waveshare43'}


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class SharingAnAnswer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'feedback.json'
        self.clock, self.site = Clock(), Website()

    def store(self):
        store = Feedback(self.path, clock=self.clock, transport=self.site, catalogue=catalogue)
        self.addAsyncCleanup(store.close)
        return store

    async def test_a_yes_goes_out_once_with_a_random_key_and_nothing_else(self):
        store = self.store()
        await store.answer('device-1', 'guition', 'working', versions={'firmware_version': '0.3.4', 'addon_version': '0.3.10'})
        [(method, token, payload)] = self.site.requests
        self.assertEqual(method, 'POST')
        self.assertRegex(token, r'^[0-9a-f]{64}$')
        self.assertEqual(payload, {'board_id': 'guition', 'outcome': 'working', 'revision': 1, 'consent': True,
                                   'firmware_version': '0.3.4', 'addon_version': '0.3.10'})
        self.assertNotIn('device-1', json.dumps(payload))
        view = store.view('device-1')
        self.assertEqual((view['state'], view['shared']['outcome']), ('idle', 'working'))
        self.assertNotIn(token, json.dumps(view))
        self.assertNotIn('revision', json.dumps(view))

    async def test_the_key_and_revision_are_on_disk_before_the_request(self):
        seen = {}
        async def transport(session, token, payload=None, *, delete=False):
            seen.update(json.loads(self.path.read_text())['boards']['device-1'])
            return {'state': 'saved', 'revision': payload['revision']}
        store = Feedback(self.path, clock=self.clock, transport=transport, catalogue=catalogue)
        self.addAsyncCleanup(store.close)
        await store.answer('device-1', 'guition', 'not_working')
        self.assertRegex(seen['token'], r'^[0-9a-f]{64}$')
        self.assertEqual(seen['pending']['payload']['revision'], 1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    async def test_details_are_a_new_revision_under_the_same_key(self):
        store = self.store()
        await store.answer('device-1', 'guition', 'not_working')
        await store.answer('device-1', 'guition', 'not_working', ['touch', 'connection', 'touch'], '  Touch misses taps after waking.  ')
        (_, first, one), (_, second, two) = self.site.requests
        self.assertEqual(first, second)
        self.assertEqual((one['revision'], two['revision']), (1, 2))
        self.assertNotIn('issues', one)
        self.assertEqual(two['issues'], ['touch', 'connection'])
        self.assertEqual(two['comment'], 'Touch misses taps after waking.')
        self.assertEqual(len(self.site.rows), 1)

    async def test_two_boards_of_one_model_get_two_keys_and_a_restart_keeps_them(self):
        store = self.store()
        await store.answer('device-1', 'cyd', 'working')
        await store.answer('device-2', 'cyd', 'working')
        self.assertEqual(len({token for _, token, _ in self.site.requests}), 2)
        again = self.store()
        await again.answer('device-1', 'cyd', 'not_working')
        self.assertEqual(self.site.requests[2][1], self.site.requests[0][1])
        self.assertEqual(self.site.requests[2][2]['revision'], 2)

    async def test_a_working_answer_carries_no_problems(self):
        store = self.store()
        await store.answer('device-1', 'guition', 'working', ['touch'])
        self.assertNotIn('issues', self.site.requests[0][2])

    async def test_bad_answers_are_refused_before_anything_is_stored(self):
        store = self.store()
        for outcome, issues, comment in (('online', [], None), ('working', ['battery'], None), ('working', [], 'x' * 1001),
                                         ('working', 'touch', None)):
            with self.assertRaises(ValueError):
                await store.answer('device-1', 'guition', outcome, issues, comment)
        self.assertEqual(self.site.requests, [])
        self.assertFalse(self.path.exists())

    async def test_a_model_the_website_does_not_know_is_not_sent(self):
        store = self.store()
        with self.assertRaisesRegex(ValueError, 'board'):
            await store.answer('device-1', 'jc1060p470', 'working')
        self.assertEqual(self.site.requests, [])

    async def test_a_version_the_website_would_refuse_stays_home(self):
        store = self.store()
        await store.answer('device-1', 'guition', 'working', versions={'firmware_version': 'http://x/y', 'addon_version': None})
        payload = self.site.requests[0][2]
        self.assertNotIn('firmware_version', payload)
        self.assertNotIn('addon_version', payload)

    async def test_a_network_failure_keeps_the_exact_answer_and_retries_it(self):
        store = self.store()
        self.site.answers = [{'state': 'retry'}]
        await store.answer('device-1', 'guition', 'working')
        view = store.view('device-1')
        self.assertEqual((view['state'], view['shared']), ('waiting', None))
        self.assertIn('device-1', store.timers)
        await store.retry('device-1')
        (_, token1, first), (_, token2, second) = self.site.requests
        self.assertEqual((token1, first), (token2, second))
        self.assertEqual(store.view('device-1')['state'], 'idle')

    async def test_retry_after_is_honoured_and_a_day_of_failures_stops(self):
        store = self.store()
        self.site.answers = [{'state': 'retry', 'after': 900}]
        await store.answer('device-1', 'guition', 'working')
        record = store.boards['device-1']
        self.assertGreaterEqual(record['retry_at'] - self.clock.now, 900)
        self.clock.now += DAY
        self.site.answers = [{'state': 'retry'}]
        store.cancel_timer('device-1')
        async with store.lock('device-1'):
            await store._send_locked('device-1')
        self.assertEqual(store.view('device-1')['state'], 'failed')
        self.assertNotIn('device-1', store.timers)

    async def test_a_new_answer_replaces_one_still_waiting(self):
        store = self.store()
        self.site.answers = [{'state': 'retry'}]
        await store.answer('device-1', 'guition', 'working')
        await store.answer('device-1', 'guition', 'not_working')
        self.assertEqual(self.site.rows[self.site.requests[0][1]]['outcome'], 'not_working')
        # The old revision is gone for good: a retry now sends nothing.
        await store.retry('device-1')
        self.assertEqual(len(self.site.requests), 2)

    async def test_a_conflict_stops_without_a_new_key_or_a_higher_number(self):
        store = self.store()
        self.site.answers = [{'state': 'conflict'}]
        await store.answer('device-1', 'guition', 'working')
        view = store.view('device-1')
        self.assertEqual((view['state'], view['problem'], view['pending']), ('idle', 'conflict', None))
        self.assertNotIn('device-1', store.timers)
        self.assertEqual(store.boards['device-1']['next_revision'], 2)

    async def test_a_restart_tries_what_was_waiting_again(self):
        store = self.store()
        self.site.answers = [{'state': 'retry'}]
        await store.answer('device-1', 'guition', 'working')
        await store.close()
        again = self.store()
        again.start()
        self.assertIn('device-1', again.timers)
        self.assertEqual(again.view('device-1')['pending']['outcome'], 'working')

    async def test_a_double_click_sends_one_row(self):
        store = self.store()
        await asyncio.gather(store.answer('device-1', 'guition', 'working'), store.answer('device-1', 'guition', 'working'))
        self.assertEqual(len(self.site.rows), 1)
        self.assertEqual([payload['revision'] for _, _, payload in self.site.requests], [1, 2])


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class AskingAndDeleting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'feedback.json'
        self.clock, self.site = Clock(), Website()
        self.store = Feedback(self.path, clock=self.clock, transport=self.site, catalogue=catalogue)
        self.addAsyncCleanup(self.store.close)

    def test_the_card_asks_a_day_after_the_board_first_worked(self):
        self.assertFalse(self.store.asks('device-1'))
        self.store.seen_usable('device-1')
        self.assertFalse(self.store.asks('device-1'))
        self.clock.now += DAY - 1
        self.store.seen_usable('device-1')  # a later visit doesn't move the start
        self.assertFalse(self.store.asks('device-1'))
        self.clock.now += 1
        self.assertTrue(self.store.asks('device-1'))
        self.assertEqual(self.site.requests, [])

    def test_later_waits_two_weeks_once_and_then_stops_asking(self):
        self.store.seen_usable('device-1')
        self.clock.now += DAY
        self.store.later('device-1')
        self.assertFalse(self.store.asks('device-1'))
        self.clock.now += 14 * DAY
        self.assertTrue(self.store.asks('device-1'))
        self.store.later('device-1')
        self.clock.now += 365 * DAY
        self.assertFalse(self.store.asks('device-1'))
        self.assertEqual(self.site.requests, [])

    def test_dont_ask_again_holds_after_a_restart(self):
        self.store.seen_usable('device-1')
        self.clock.now += DAY
        self.store.never('device-1')
        again = Feedback(self.path, clock=self.clock, transport=self.site, catalogue=catalogue)
        self.assertFalse(again.asks('device-1'))
        self.assertEqual(self.site.requests, [])

    async def test_an_answer_ends_the_asking_also_after_a_deletion(self):
        self.store.seen_usable('device-1')
        self.clock.now += DAY
        await self.store.answer('device-1', 'guition', 'working')
        self.assertFalse(self.store.asks('device-1'))
        await self.store.delete('device-1')
        self.assertFalse(self.store.asks('device-1'))

    async def test_deleting_waits_for_a_request_under_way_and_clears_what_was_shared(self):
        await self.store.answer('device-1', 'guition', 'working')
        self.site.gate = asyncio.Event()
        posting = asyncio.create_task(self.store.answer('device-1', 'guition', 'not_working'))
        await asyncio.sleep(0)
        deleting = asyncio.create_task(self.store.delete('device-1'))
        await asyncio.sleep(0)
        self.site.gate.set()
        await asyncio.gather(posting, deleting)
        self.assertEqual([method for method, _, _ in self.site.requests], ['POST', 'POST', 'DELETE'])
        self.assertEqual(self.site.rows, {})
        view = self.store.view('device-1')
        self.assertEqual((view['shared'], view['deleted'], view['state']), (None, True, 'idle'))

    async def test_deleting_cancels_a_waiting_retry_and_stays_pending_offline(self):
        self.site.answers = [{'state': 'retry'}, {'state': 'retry'}]
        await self.store.answer('device-1', 'guition', 'working')
        self.assertIn('device-1', self.store.timers)
        await self.store.delete('device-1')
        record = self.store.boards['device-1']
        self.assertTrue(record['deletion_pending'])
        self.assertIsNone(record['pending'])
        self.assertRegex(record['token'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.store.view('device-1')['state'], 'deleting')
        # A new answer waits until the deletion is confirmed.
        with self.assertRaisesRegex(ValueError, 'deleting'):
            await self.store.answer('device-1', 'guition', 'working')
        await self.store.retry('device-1')
        self.assertEqual(self.site.requests[-1][0], 'DELETE')
        self.assertFalse(self.store.boards['device-1']['deletion_pending'])

    def test_an_unknown_storage_version_is_left_alone(self):
        self.path.write_text(json.dumps({'version': 99, 'boards': {}}))
        store = Feedback(self.path, clock=self.clock, transport=self.site, catalogue=catalogue)
        self.assertTrue(store.readonly)
        store.seen_usable('device-1')
        self.assertEqual(json.loads(self.path.read_text())['version'], 99)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class TheEditorsRoute(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_gets_a_view_without_the_key_and_answers_through_the_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'screens.json').write_text(json.dumps({'version': 1, 'screens': {'text.screen': {'title': 'Office', 'tiles': []}}}))
            manager = Manager(fake_ha(), Path(tmp) / 'screens.json')
            site = Website()
            manager.feedback.transport, manager.feedback.catalogue = site, catalogue
            async with TestClient(TestServer(create_app(manager, True))) as client:
                payload = await (await client.get('/api/inventory?light=1')).json()
                view = payload['screens'][0]['feedback']
                self.assertEqual((view['board'], view['ask'], view['available']), ('guition', False, True))
                self.assertEqual(site.requests, [])
                response = await client.post('/api/screens/text.screen/feedback', headers={'X-Screen-CSRF': payload['csrf']},
                                             json={'action': 'answer', 'outcome': 'not_working', 'issues': ['touch'],
                                                   'token': 'f' * 64, 'revision': 99, 'board_id': 'cyd'})
                self.assertEqual(response.status, 200)
                body = await response.text()
                [(_, token, sent)] = site.requests
                self.assertNotIn(token, body)
                self.assertNotEqual(token, 'f' * 64)
                self.assertEqual((sent['board_id'], sent['revision'], sent['issues']), ('guition', 1, ['touch']))
                self.assertEqual(sent['firmware_version'], '0.2.104')
                refused = await client.post('/api/screens/text.screen/feedback', json={'action': 'later'})
                self.assertEqual(refused.status, 403)
                unknown = await client.post('/api/screens/text.other/feedback', headers={'X-Screen-CSRF': payload['csrf']},
                                            json={'action': 'answer', 'outcome': 'working'})
                self.assertEqual(unknown.status, 400)
                stored = json.loads((Path(tmp) / 'feedback.json').read_text())
                self.assertEqual(list(stored['boards']), ['d1'])


if __name__ == '__main__':
    unittest.main()
