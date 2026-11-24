"""Home Assistant's states through `subscribe_entities` (screen_manager/app/ha_entities.py, GitHub #315, #392, #399,
#428): the compressed messages become the same states `get_states` gave, a change carries only what changed, and the
connection keeps the states, wakes what follows an entity, falls back on an older Home Assistant and is made
again when Home Assistant answers no ping."""
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager' / 'app'))
import ha_entities  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None

FIRST = {'a': {
    'light.kitchen': {'s': 'on', 'a': {'brightness': 180, 'friendly_name': 'Kitchen'}, 'c': '01JABC', 'lc': 1764000000.5,
                      'lu': 1764000100.25},
    'sensor.scores': {'s': '3', 'a': {'standings': ['x'] * 3, 'unit_of_measurement': 'pt'}, 'c': {'id': '01JDEF', 'user_id': 'u'},
                      'lc': 1764000000},
}}


class Messages(unittest.TestCase):
    def test_the_first_list_is_what_get_states_gives(self):
        states = {}
        self.assertEqual(ha_entities.apply(states, FIRST), {'light.kitchen', 'sensor.scores'})
        light = states['light.kitchen']
        self.assertEqual(light['entity_id'], 'light.kitchen')
        self.assertEqual((light['state'], light['attributes']['brightness']), ('on', 180))
        self.assertEqual(light['last_changed'], '2025-11-24T16:00:00.500000+00:00')
        self.assertEqual(light['last_updated'], '2025-11-24T16:01:40.250000+00:00')
        self.assertEqual(light['context'], {'parent_id': None, 'user_id': None, 'id': '01JABC'})
        scores = states['sensor.scores']
        self.assertEqual(scores['last_updated'], scores['last_changed'], 'without lu the update is the change')
        self.assertEqual(scores['context'], {'id': '01JDEF', 'user_id': 'u'})

    def test_a_change_carries_only_what_changed(self):
        states = {}
        ha_entities.apply(states, FIRST)
        before = states['sensor.scores']
        touched = ha_entities.apply(states, {'c': {
            'sensor.scores': {'+': {'a': {'unit_of_measurement': 'points'}, 'lu': 1764000200}},
            'light.kitchen': {'+': {'s': 'off', 'lc': 1764000300, 'c': '01JXYZ'}, '-': {'a': ['brightness']}}}})
        self.assertEqual(touched, {'sensor.scores', 'light.kitchen'})
        scores = states['sensor.scores']
        self.assertEqual(scores['attributes'], {'standings': ['x'] * 3, 'unit_of_measurement': 'points'})
        self.assertEqual(scores['last_changed'], before['last_changed'], 'an attribute alone changes last_updated only')
        self.assertEqual(scores['last_updated'], '2025-11-24T16:03:20+00:00')
        self.assertIsNot(scores, before, 'a new state: whoever holds the old one keeps it as it was')
        self.assertEqual(before['attributes']['unit_of_measurement'], 'pt')
        light = states['light.kitchen']
        self.assertEqual((light['state'], light['attributes']), ('off', {'friendly_name': 'Kitchen'}))
        self.assertEqual(light['last_changed'], light['last_updated'])
        self.assertEqual(light['context']['id'], '01JXYZ')

    def test_removed_and_unknown_entities(self):
        states = {}
        ha_entities.apply(states, FIRST)
        self.assertEqual(ha_entities.apply(states, {'r': ['light.kitchen', 'light.gone']}), {'light.kitchen'})
        self.assertNotIn('light.kitchen', states)
        self.assertEqual(ha_entities.apply(states, {'c': {'light.gone': {'+': {'s': 'on'}}}}), set(),
                         'a change of an entity without a state is left out, as the frontend does')


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Connection(unittest.IsolatedAsyncioTestCase):
    def home(self):
        from server import HomeAssistant
        ha = HomeAssistant(None, 'http://ha/api', 'unused')
        ha.relevant = {'light.kitchen'}
        return ha

    async def test_the_first_list_replaces_the_states_and_later_changes_wake_their_entity(self):
        from aiohttp import WSMsgType
        ha = self.home()
        ha.states = {'light.old': {'state': 'on'}}
        ha.entities_sub, ha.entities_ready = 7, asyncio.get_running_loop().create_future()
        woken = asyncio.Event()
        ha.state_events.listeners[woken] = frozenset({'sensor.scores'})

        class Socket:
            def __init__(self, *events): self.events = events
            async def __aiter__(self):
                for event in self.events:
                    yield SimpleNamespace(type=WSMsgType.TEXT, json=lambda event=event: {'id': 7, 'type': 'event', 'event': event})
        ha.ws = Socket(FIRST)
        with self.assertRaises(ConnectionError):
            await ha.read()
        self.assertTrue(ha.entities_ready.done())
        self.assertEqual(set(ha.states), {'light.kitchen', 'sensor.scores'}, 'what was kept from before is gone')
        self.assertFalse(woken.is_set() or ha.changed.is_set(), 'the first list is told at once by run()')
        ha.ws = Socket({'c': {'sensor.scores': {'+': {'s': '4'}}}})
        with self.assertRaises(ConnectionError):
            await ha.read()
        self.assertTrue(woken.is_set())
        self.assertFalse(ha.changed.is_set(), 'an entity no screen shows rebuilds nothing')
        ha.ws = Socket({'c': {'light.kitchen': {'+': {'s': 'off'}}}})
        with self.assertRaises(ConnectionError):
            await ha.read()
        self.assertTrue(ha.changed.is_set())
        self.assertIn('light.kitchen', ha.dirty)
        self.assertEqual(ha.states['light.kitchen']['state'], 'off')

    async def test_an_older_home_assistant_gets_every_state_the_old_way(self):
        from server import Refused
        ha = self.home()
        asked = []

        async def request(kind, wait=15, **data):
            asked.append((kind, data.get('event_type')))
            if kind == 'subscribe_entities':
                raise Refused('Unknown command.')
            if kind == 'get_states':
                return [{'entity_id': 'light.kitchen', 'state': 'on', 'attributes': {}}]
        ha.request = request
        await ha.follow_entities()
        self.assertEqual(asked, [('subscribe_entities', None), ('subscribe_events', 'state_changed'), ('get_states', None)])
        self.assertIsNone(ha.entities_sub)
        self.assertEqual(ha.states['light.kitchen']['state'], 'on')

    async def test_a_lost_link_ends_the_wait_for_the_first_list(self):
        ha = self.home()

        async def request(kind, wait=15, **data):
            return None
        ha.request = request

        async def lost():
            raise ConnectionError('Home Assistant connection lost.')
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(ha.follow_entities(asyncio.ensure_future(lost())), 2)

    async def test_a_slow_action_keeps_the_link_and_a_missing_pong_closes_it(self):
        """GitHub #399: Home Assistant that stops listening is found by its own ping; a call_service that takes long
        (it is answered when the action is done) says nothing about that."""
        import server
        from unittest import mock
        from aiohttp import WSMsgType
        ha = self.home()
        closed, sent = [], []

        class Socket:
            closed = False
            def __init__(self): self.answers = asyncio.Queue()
            async def send_json(self, data):
                sent.append(data['type'])
                if data['type'] == 'ping' and pongs:
                    self.answers.put_nowait({'id': data['id'], 'type': 'pong'})
            async def close(self): closed.append(True)
            async def __aiter__(self):
                while True:
                    answer = await self.answers.get()
                    yield SimpleNamespace(type=WSMsgType.TEXT, json=lambda answer=answer: answer)
        ha.ws = Socket()
        reader = asyncio.ensure_future(ha.read())
        for _ in range(4):
            with self.assertRaises(TimeoutError):
                await ha.request('call_service', wait=0.01)
        self.assertEqual(closed, [], 'slow actions never close the link')
        with mock.patch.object(server, 'PING_SECONDS', 0.01), mock.patch.object(server, 'PONG_SECONDS', 0.05):
            pongs = True
            prober = asyncio.ensure_future(ha.listen_for_answers())
            await asyncio.sleep(0.1)
            self.assertGreaterEqual(sent.count('ping'), 2)
            self.assertEqual(closed, [], 'a pong keeps the link')
            pongs = False
            await asyncio.wait_for(prober, 1)
            self.assertEqual(closed, [True], 'a missing pong closes the link, and run() connects again')
        reader.cancel()

if __name__ == '__main__':
    unittest.main()
