import json
import tempfile
from pathlib import Path
import unittest

from test_schedules import FakeBackend, ENTITY, programme, projected
import schedules
import schedule_transport as wire


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.adapter = schedules.Adapter(self.backend, lambda: self.backend.states,
                                         lambda: {'temperature': '°C'})

    async def send(self, **fields):
        return await wire.exchange(self.adapter, json.dumps({'v': 1, 'rid': 17, 'entity': ENTITY, **fields}), {ENTITY})

    async def test_request_identity_and_complete_programme_packets(self):
        loaded = await self.send(op='load')
        saved = await self.send(op='save', revision=loaded[0]['revision'], programme=programme())
        self.assertEqual([p['stage'] for p in saved], ['begin', 'programme', 'end'])
        self.assertEqual(saved[1]['programme'], projected(programme()))
        self.assertTrue(all(p['rid'] == 17 and p['entity'] == ENTITY for p in saved))
        self.assertTrue(all(len(json.dumps(p).encode()) < 4096 for p in saved))

    async def test_stale_save_returns_error_and_performs_no_writes(self):
        result = await self.send(op='save', revision='stale', programme=programme())
        self.assertEqual(result[0]['stage'], 'error')
        self.assertEqual(result[0]['code'], 'conflict')
        self.assertEqual(self.backend.writes, [])

    async def test_unbound_or_oversized_requests_never_reach_backend(self):
        for payload, targets in [(json.dumps({'v': 1, 'rid': 1, 'entity': ENTITY, 'op': 'load'}), set()),
                                  (' ' * 4097, {ENTITY}),
                                  (json.dumps({'v': True, 'rid': 1, 'entity': ENTITY, 'op': 'load'}), {ENTITY})]:
            with self.assertRaises(ValueError):
                await wire.exchange(self.adapter, payload, targets)
        self.assertEqual(self.backend.writes, [])

    async def test_only_explicit_climate_schedule_tiles_bind(self):
        layout = {'tiles': [{'entity': ENTITY, 'options': {'tap': 'schedule'}},
                            {'entity': 'climate.other', 'options': {'tap': 'detail'}},
                            {'entity': 'switch.other', 'options': {'tap': 'schedule'}}]}
        self.assertEqual(wire.bound_entities(layout), {ENTITY})

    async def test_partial_write_is_not_an_acknowledgement(self):
        view = await self.send(op='load')
        self.backend.fail = 'schedule/update'
        result = await self.send(op='save', revision=view[0]['revision'], programme=programme())
        self.assertEqual([p['stage'] for p in result], ['error'])
        self.assertEqual(result[0]['code'], 'unconfirmed')


class DeviceEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from server import Manager
        from page_delivery import Sender
        from test_scaling import fake_ha
        from test_page_delivery import Screen
        from manager_fixtures import seed_layout, with_screen_grid
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backend = FakeBackend()
        ha = fake_ha(firmware='0.7.0')
        ha.states.update(self.backend.states)
        ha.units = {'temperature': '°C'}
        ha.schedule_api = self.backend
        self.manager = Manager(with_screen_grid(ha), Path(self.directory.name) / 'screens.json')
        seed_layout(self.manager, 'text.screen', {'title': 'Heating', 'tiles': [
            {'entity': ENTITY, 'slot': 0, 'options': {'tap': 'schedule'}}]})
        self.peer = Screen()
        async def send(message):
            answer = await self.peer.send(message)
            if message['op'] == 'hello':
                answer['schedule'] = 1
            return answer
        self.sender = Sender(send)
        await self.sender.probe()
        self.sender.confirmed = self.peer.revision
        self.peer.active = True
        self.manager.page_senders['text.screen'] = self.sender

    def request(self, op='load', **fields):
        return {'inbox': 'text.screen', 'session': self.sender.session,
                'rev': self.sender.confirmed, 'payload': json.dumps(
                    {'v': 1, 'rid': 23, 'entity': ENTITY, 'op': op, **fields})}

    async def test_device_event_uses_negotiated_transport_and_confirms_save(self):
        await self.manager.answer_schedule(self.request())
        responses = [m for m in self.peer.messages if m['op'] == 'schedule']
        self.assertEqual([m['stage'] for m in responses], ['begin', 'end'])
        self.assertTrue(all(m['v'] == 2 and m['session'] == self.sender.session for m in responses))
        await self.manager.answer_schedule(self.request('day', revision=responses[0]['revision'],
                                                       day='mon', slots=programme()['slots']))
        self.assertTrue(self.backend.writes)
        self.assertEqual(self.peer.messages[-1]['stage'], 'end')

    async def test_obsolete_or_unnegotiated_device_events_cannot_write(self):
        view = await self.manager.schedules.load(ENTITY)
        request = self.request('day', revision=view['revision'], day='mon', slots=programme()['slots'])
        for field in ('session', 'rev'):
            await self.manager.answer_schedule({**request, field: 'f' * 16})
            self.assertEqual(self.backend.writes, [])
        self.sender.schedule = False
        await self.manager.answer_schedule(request)
        self.assertEqual(self.backend.writes, [])
        self.sender.schedule = True
        self.sender.disconnected()
        self.assertFalse(self.sender.schedule)
        await self.manager.answer_schedule(request)
        self.assertEqual(self.backend.writes, [])

    async def test_current_device_cannot_save_an_unbound_thermostat(self):
        from manager_fixtures import seed_layout
        view = await self.manager.schedules.load(ENTITY)
        seed_layout(self.manager, 'text.screen', {'title': 'Heating', 'tiles': [
            {'entity': ENTITY, 'slot': 0, 'options': {'tap': 'detail'}}]})
        with self.assertRaises(ValueError):
            await self.manager.answer_schedule(self.request('day', revision=view['revision'],
                                                           day='mon', slots=programme()['slots']))
        self.assertEqual(self.backend.writes, [])
