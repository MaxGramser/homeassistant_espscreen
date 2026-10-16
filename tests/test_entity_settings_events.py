"""Live settings follow HA events, including status sensors, without polling for values."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager' / 'app'))
import entity_settings
import preview_events


class LiveSettings(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = {'switch.hall_microphone': {'state': 'on'},
                      'sensor.hall_test_status': {'state': 'Idle'}}
        self.screen = {'id': 'text.hall_tiles', 'device_id': 'hall', 'online': True}
        self.manager = SimpleNamespace(
            screen=lambda inbox: self.screen if inbox == 'text.hall_tiles' else None,
            listeners=set(), ha=SimpleNamespace(state_events=preview_events.Changes(), states=self.state,
                registry=[{'entity_id': eid, 'device_id': 'hall'} for eid in self.state]
                    + [{'entity_id': 'switch.other_microphone', 'device_id': 'other'}]))
        self.output = asyncio.Queue()
        self.prepared = False
        self.reads = 0
        self.task = None
        owner = self

        class Response:
            def __init__(self, **kwargs):
                self.headers = kwargs['headers']

            async def prepare(self, request):
                owner.prepared = True

            async def write(self, data):
                owner.output.put_nowait(data)

        self.patch = patch.object(entity_settings.web, 'StreamResponse', Response)
        self.patch.start()

    async def asyncTearDown(self):
        if self.task:
            self.task.cancel()
            await self.task
        self.patch.stop()
        self.assertFalse(self.manager.listeners)
        self.assertFalse(self.manager.ha.state_events.listeners)

    def values(self):
        self.reads += 1
        if self.screen is None:
            raise ValueError('Screen removed')
        return [entity_settings.row({'key': 'microphone'}, {'microphone': 'switch.hall_microphone'}, self.state,
                                    {'en': 'Microphone'}, None, self.screen['online']),
                entity_settings.row({'key': 'test', 'status': 'test_status'},
                                    {'test': 'button.hall_test', 'test_status': 'sensor.hall_test_status'}, self.state,
                                    {'en': 'Test'}, None, self.screen['online'])]

    async def start(self):
        request = SimpleNamespace(match_info={'inbox': 'text.hall_tiles'})
        self.task = asyncio.create_task(entity_settings.stream(self.manager, request, self.values))
        return await self.next()

    async def next(self):
        payload = await asyncio.wait_for(self.output.get(), 1)
        self.assertTrue(payload.startswith(b'data: '))
        return json.loads(payload[6:])

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0)

    async def test_initial_snapshot_then_panel_change_and_test_status(self):
        first = await self.start()
        self.assertTrue(first[0]['value'])
        self.state['switch.hall_microphone']['state'] = 'off'
        self.manager.ha.state_events.notify('switch.hall_microphone')
        self.assertFalse((await self.next())[0]['value'])
        self.state['sensor.hall_test_status']['state'] = 'Heard'
        self.manager.ha.state_events.notify('sensor.hall_test_status')
        self.assertEqual((await self.next())[1]['status'], 'Heard')

    async def test_other_devices_and_unchanged_notifications_send_no_settings(self):
        await self.start()
        before = self.reads
        self.manager.ha.state_events.notify('switch.other_microphone')
        await self.settle()
        self.assertEqual(self.reads, before)
        self.assertTrue(self.output.empty())
        self.manager.ha.state_events.notify('switch.hall_microphone')
        await self.settle()
        self.assertEqual(self.reads, before + 1)
        self.assertTrue(self.output.empty())

    async def test_registry_and_availability_changes_refresh_subscription(self):
        await self.start()
        self.manager.ha.registry.append({'entity_id': 'sensor.hall_new', 'device_id': 'hall'})
        self.screen['online'] = False
        for wake in self.manager.listeners:
            wake.set()
        self.assertFalse((await self.next())[0]['available'])
        self.assertIn('sensor.hall_new', next(iter(self.manager.ha.state_events.listeners.values())))

    async def test_reconnect_sends_current_state_and_closing_releases_listeners(self):
        await self.start()
        self.task.cancel()
        await self.task
        self.assertFalse(self.manager.listeners)
        self.assertFalse(self.manager.ha.state_events.listeners)
        self.state['switch.hall_microphone']['state'] = 'off'
        self.assertFalse((await self.start())[0]['value'])

    async def test_removing_screen_clears_rows_and_closes_subscription(self):
        await self.start()
        self.screen = None
        for wake in self.manager.listeners:
            wake.set()
        self.assertEqual(await self.next(), [])
        await self.task

    async def test_missing_screen_is_refused_before_stream_is_opened(self):
        self.screen = None
        request = SimpleNamespace(match_info={'inbox': 'text.hall_tiles'})
        with self.assertRaises(ValueError):
            await entity_settings.stream(self.manager, request, self.values)
        self.assertFalse(self.prepared)


if __name__ == '__main__':
    unittest.main()
