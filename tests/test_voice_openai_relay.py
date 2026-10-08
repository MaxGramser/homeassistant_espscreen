"""Direct audio relay through fake WebSockets; tools and speaker delivery stay separate."""
import asyncio
import base64
import json
import unittest
from unittest.mock import patch

from aiohttp import web, WSMsgType
from aiohttp.test_utils import TestServer

import test_voice_preview as base
from test_voice_output import SPEAKER, add_speaker
import voice_openai_relay


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await base.VoiceTests.asyncSetUp(self)
        add_speaker(self.ha)
        self.incoming = asyncio.Queue()
        self.config = None
        self.upstream = None

        async def audio(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer test-only-not-a-key')
            ws = self.upstream = web.WebSocketResponse()
            await ws.prepare(request)
            self.config = await ws.receive_json()
            await ws.send_json({'type': 'session.updated'})
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    await self.incoming.put(message.json())
            return ws

        app = web.Application()
        app.router.add_get('/audio', audio)
        self.audio_server = TestServer(app)
        await self.audio_server.start_server()
        self.audio_url = patch.object(voice_openai_relay, 'REALTIME_URL', str(self.audio_server.make_url('/audio')))
        self.audio_url.start()
        result = await self.client.put('/api/voice-preview/config', json={'reply_speaker': SPEAKER, 'reply_volume': 25})
        self.assertEqual(result.status, 200)

    async def asyncTearDown(self):
        await base.VoiceTests.asyncTearDown(self)
        self.audio_url.stop()
        await self.audio_server.close()

    async def start(self, context=None):
        result = await self.client.post('/api/voice-preview/openai/sessions', json={'context': context or base.panel()})
        self.assertEqual(result.status, 200, await result.text())
        key = (await result.json())['id']
        browser = await self.client.ws_connect(f'/api/voice-preview/sessions/{key}/stream')
        self.assertEqual((await browser.receive_json())['type'], 'relay.ready')
        return key, browser

    async def emit(self, kind, **fields):
        await self.upstream.send_json({'type': kind, **fields})

    async def reply(self, browser, response='r1'):
        await self.emit('response.created', response={'id': response})
        self.assertEqual((await browser.receive_json())['type'], 'response.created')
        await self.emit('response.output_audio.delta', response_id=response, delta=base64.b64encode(b'\0'*4800).decode())
        await self.emit('response.done', response={'id': response, 'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'audio', 'transcript': 'Answer.'}]}]})
        result = await browser.receive_json()
        self.assertEqual(result['type'], 'reply.ready')
        self.assertEqual((await browser.receive_json())['type'], 'response.done')
        return result['reply']

    async def test_pcm_is_native_audio_and_generated_reply_uses_configured_output(self):
        key, browser = await self.start()
        audio = self.config['session']['audio']
        self.assertEqual(audio['input']['format'], {'type': 'audio/pcm', 'rate': 24000})
        self.assertNotIn('transcription', audio['input'])
        self.assertEqual(audio['output']['voice'], 'marin')
        await browser.send_bytes(b'\0'*1600)
        event = await self.incoming.get()
        self.assertEqual(event['type'], 'input_audio_buffer.append')
        self.assertEqual(base64.b64decode(event['audio']), b'\0'*1600)
        reply = await self.reply(browser)
        self.assertEqual(reply['output'], 'sonos')
        root = f'/api/voice-preview/sessions/{key}/replies/{reply["id"]}'
        self.assertEqual((await self.client.get(root)).status, 200)
        self.assertEqual((await self.client.get(root + '/audio')).status, 404)
        self.ha.call.assert_not_awaited()
        await self.client.delete(f'/api/voice-preview/sessions/{key}')
        self.assertEqual((await self.client.get(root)).status, 400)

    async def test_music_confirmation_is_local_and_shared_tools_execute_once(self):
        context = base.VoiceTests.media_panel(self)
        key, browser = await self.start(context)
        command = {'call_id': 'play_1', 'name': 'control_media', 'context': context,
                   'arguments': {'name': 'Spotify', 'area': '', 'action': 'play'}}
        for _ in range(2):
            result = await self.client.post(f'/api/voice-preview/sessions/{key}/tools', json=command)
            self.assertTrue((await result.json())['end_voice'])
        self.ha.call.assert_awaited_once_with('media_player.media_play', {'entity_id': 'media_player.music'})
        reply = await self.reply(browser)
        self.assertEqual(reply['output'], 'local')
        response = await self.client.get(f'/api/voice-preview/sessions/{key}/replies/{reply["id"]}/audio')
        self.assertEqual((await response.read())[:4], b'RIFF')

    async def test_generated_audio_with_tool_calls_is_not_announced_as_a_separate_preamble(self):
        _, browser = await self.start()
        await self.emit('response.created', response={'id': 'tools'})
        await browser.receive_json()
        await self.emit('response.output_audio.delta', response_id='tools', delta=base64.b64encode(b'\0'*480).decode())
        await self.emit('response.done', response={'id': 'tools', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'search_1', 'name': 'lookup_current_information', 'arguments': '{}'}]})
        self.assertEqual((await browser.receive_json())['type'], 'response.done')
        self.assertFalse(self.manager.voice_output.replies)

    async def test_disallowed_audio_settings_end_the_session_without_device_actions(self):
        _, browser = await self.start()
        await browser.send_json({'type': 'session.update', 'session': {'type': 'realtime', 'tools': []}})
        self.assertEqual((await browser.receive_json())['type'], 'error')
        await browser.receive()
        self.ha.call.assert_not_awaited()

    async def test_usage_is_counted_once_per_response_including_cancelled_responses(self):
        _, browser = await self.start()
        usage = {'input_tokens': 120, 'output_tokens': 12,
            'input_token_details': {'cached_tokens': 90, 'audio_tokens': 20, 'text_tokens': 100}}
        with self.assertLogs('voice_openai_relay', level='INFO') as logs:
            for identity, status in [('private-a', 'completed'), ('private-a', 'cancelled'),
                                     ('private-b', 'cancelled')]:
                await self.emit('response.done', response={'id': identity, 'status': status, 'usage': usage, 'output': []})
                self.assertEqual((await browser.receive_json())['type'], 'response.done')
        self.assertEqual(len(logs.output), 2)
        self.assertTrue(all('input=120 output=12' in line for line in logs.output))
        self.assertNotIn('private-', '\n'.join(logs.output))
        self.ha.call.assert_not_awaited()

    async def test_unavailable_speaker_fails_before_opening_paid_audio_connection(self):
        self.ha.states[SPEAKER]['state'] = 'unavailable'
        response = await self.client.post('/api/voice-preview/openai/sessions', json={'context': base.panel()})
        self.assertEqual(response.status, 400)
        self.assertIsNone(self.config)


if __name__ == '__main__': unittest.main()
