"""Exercise the shared voice HTTP entry and a real local MCP HTTP endpoint."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

import test_voice_preview as fixtures
import voice_preview
from voice_openai_relay import log_usage


class AssistTests(unittest.IsolatedAsyncioTestCase):
    session = fixtures.VoiceTests.session
    command = fixtures.VoiceTests.command

    async def asyncSetUp(self):
        await fixtures.VoiceTests.asyncSetUp(self)
        self.mcp_calls = []
        self.http_status = 200
        self.receipt_override = None
        self.tool_names = ['intent__HassTurnOn', 'intent__HassTurnOff']

        async def mcp(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer test-ha-secret')
            self.assertIn('application/json', request.headers['Accept'])
            message = await request.json()
            self.mcp_calls.append(message)
            if self.http_status != 200:
                return web.Response(status=self.http_status)
            if message['method'] == 'tools/list':
                result = {'tools': [{'name': name, 'inputSchema': {'type': 'object', 'properties': {
                    'name': {'type': 'string'}, 'domain': {'type': 'array', 'items': {'type': 'string'}}}}}
                    for name in self.tool_names]}
            else:
                self.assertEqual(message['method'], 'tools/call')
                receipt = self.receipt_override if self.receipt_override is not None else {
                    'response_type': 'action_done', 'data': {'success': [{'type': 'entity',
                        'id': message['params']['arguments']['name']}], 'failed': []}}
                result = {'content': [{'type': 'text', 'text': json.dumps(receipt)}]}
            return web.json_response({'jsonrpc': '2.0', 'id': message['id'], 'result': result})

        app = web.Application()
        app.router.add_post('/api/mcp/assist', mcp)
        self.mcp = TestServer(app)
        await self.mcp.start_server()
        self.ha.base, self.ha.token = str(self.mcp.make_url('/api')), 'test-ha-secret'
        self.owner = self.manager.device_voice.owner

    async def asyncTearDown(self):
        await self.mcp.close()
        await fixtures.VoiceTests.asyncTearDown(self)

    async def select(self, backend):
        return await self.client.put('/api/voice-preview/config', json={'light_backend': backend})

    async def test_default_and_other_settings_preserve_explicit_backend(self):
        self.assertEqual(self.owner.configuration()['light_backend'], 'direct')
        self.assertEqual((await self.select('assist')).status, 200)
        self.owner.save_settings(idle_seconds=7)
        saved = json.loads(self.owner.voice_path.read_text())
        self.assertEqual(saved['light_backend'], 'assist')
        self.assertEqual(voice_preview.VoicePreview(self.manager).light_backend, 'assist')
        self.assertNotIn('test-ha-secret', self.owner.voice_path.read_text())
        self.assertEqual((await self.select('unknown')).status, 400)
        self.assertEqual((await self.select([])).status, 400)
        session = await self.session()
        self.assertEqual((await self.select('direct')).status, 400)
        await self.owner.close(session)
        self.assertEqual((await self.select('direct')).status, 200)

    async def test_assist_resolves_tile_label_to_exact_id_and_deduplicates(self):
        self.assertEqual((await self.select('assist')).status, 200)
        session = await self.session()
        with self.assertLogs('voice_preview', level='INFO') as logged:
            responses = await asyncio.gather(*[self.command(session, complete_request=True) for _ in range(2)])
        for response in responses:
            self.assertEqual(await response.json(), {'status': 'accepted', 'entity_id': 'light.a',
                'action': 'turn_on', 'complete_request': True})
        calls = [call for call in self.mcp_calls if call['method'] == 'tools/call']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['params'], {'name': 'intent__HassTurnOn',
            'arguments': {'name': 'light.a', 'domain': ['light']}})
        self.ha.call.assert_not_awaited()
        self.assertEqual(len(logged.output), 1)
        self.assertIn('route=assist accepted=True', logged.output[0])
        for private in ('light.a', 'Reading light', session, 'test-ha-secret'):
            self.assertNotIn(private, logged.output[0])

    async def test_off_and_legacy_intent_names(self):
        self.tool_names = ['HassTurnOn', 'HassTurnOff']
        await self.select('assist')
        session = await self.session()
        result = await (await self.command(session, action='turn_off')).json()
        self.assertEqual(result['action'], 'turn_off')
        self.assertEqual(self.mcp_calls[-1]['params']['name'], 'HassTurnOff')

    async def test_direct_route_and_switches_keep_existing_service_calls(self):
        session = await self.session()
        await self.command(session)
        self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a'})
        self.assertEqual(self.mcp_calls, [])
        await self.owner.close(session)
        await self.select('assist')
        self.exposure['switch.private'] = {'conversation': True}
        self.ha.entity_actions.return_value = {'switch.turn_on'}
        self.ha.call.reset_mock()
        session = await self.session()
        result = await (await self.command(session, name='Private switch')).json()
        self.assertEqual(result['status'], 'accepted')
        self.ha.call.assert_awaited_once_with('switch.turn_on', {'entity_id': 'switch.private'})
        self.assertFalse(any(c['method'] == 'tools/call' for c in self.mcp_calls))

    async def test_revoked_exposure_does_not_match_another_same_named_light(self):
        await self.select('assist')
        session = await self.session()
        self.exposure['light.a']['conversation'] = False
        result = await (await self.command(session)).json()
        self.assertEqual(result['status'], 'not_exposed')
        self.assertFalse(any(c['method'] == 'tools/call' for c in self.mcp_calls))
        self.ha.call.assert_not_awaited()

    async def test_entity_id_alias_collision_is_refused_before_action(self):
        await self.select('assist')
        self.ha.registry[1]['aliases'] = ['light.a']
        result = await (await self.command(await self.session())).json()
        self.assertEqual(result['status'], 'ambiguous')
        self.assertFalse(any(c['method'] == 'tools/call' for c in self.mcp_calls))

    async def test_missing_integration_or_tools_cannot_enable_assist(self):
        self.http_status = 404
        self.assertEqual((await self.select('assist')).status, 400)
        self.assertEqual(self.owner.light_backend, 'direct')
        self.http_status = 200
        self.tool_names = ['intent__HassTurnOn']
        self.assertEqual((await self.select('assist')).status, 400)
        self.assertEqual(self.owner.light_backend, 'direct')

    async def test_error_or_wrong_receipt_never_falls_back_or_silently_completes(self):
        await self.select('assist')
        session = await self.session()
        for index, receipt in enumerate([
            {'response_type': 'error', 'data': {}},
            {'response_type': 'action_done', 'data': {'success': [{'id': 'light.b', 'type': 'entity'}]}},
            {'response_type': 'action_done', 'data': {'success': [{'id': 'light.a', 'type': 'entity'}], 'failed': [{}]}},
            {'response_type': 'action_done', 'data': []},
            {'response_type': 'action_done', 'data': {'success': 'wrong'}},
        ]):
            self.receipt_override = deepcopy(receipt)
            result = await (await self.command(session, call=f'bad_{index}', complete_request=True)).json()
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('complete_request', result)
        self.http_status = 503
        result = await (await self.command(session, call='uncertain', complete_request=True)).json()
        self.assertEqual(result['status'], 'error')
        before = len(self.mcp_calls)
        await self.command(session, call='uncertain', complete_request=True)
        self.assertEqual(len(self.mcp_calls), before)
        self.ha.call.assert_not_awaited()

    async def test_logs_usage_without_content_and_missing_is_not_zero(self):
        with self.assertLogs('voice_openai_relay', level='INFO') as logs:
            log_usage({'usage': {'input_tokens': 120, 'output_tokens': 12,
                'input_token_details': {'cached_tokens': 90, 'audio_tokens': 20, 'text_tokens': 100}},
                'id': 'private-id', 'output': [{'text': 'private utterance'}]})
        self.assertIn('input=120 output=12 cached_input=90 audio_input=20 text_input=100', logs.output[0])
        self.assertNotIn('private', logs.output[0])
        with self.assertNoLogs('voice_openai_relay', level='INFO'):
            log_usage({'usage': {'input_tokens': 12}})


if __name__ == '__main__':
    unittest.main()
