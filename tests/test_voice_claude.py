"""Exercise Claude, HA speech framing and shared controls with local fake servers."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web, WSMsgType
from aiohttp.test_utils import TestServer

import test_voice_preview as base

panel = base.panel
import voice_anthropic
import voice_ha_speech
import voice_preview
import voice_claude
import voice_music


class ClaudeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await base.VoiceTests.asyncSetUp(self)
        self.messages, self.stages, self.audio = [], [], []
        self.answers = []
        self.tts_url = '/api/tts_proxy/test.wav'
        self.reply_audio = b'test-audio'
        self.speech_choices = [{'id': 'speech', 'name': 'Local speech', 'language': 'nl',
                               'stt_engine': 'stt.test', 'tts_engine': 'tts.test'}]
        self.ha.request.side_effect = lambda kind: (
            {'pipelines': self.speech_choices} if kind == 'assist_pipeline/pipeline/list' else
            {'providers': [{'engine_id': kind[:3] + '.test', 'supported_languages': ['nl']}]} if kind.endswith('/engine/list') else
            {'exposed_entities': deepcopy(self.exposure)})

        async def messages(request):
            self.assertEqual(request.headers['x-api-key'], 'claude-test-key-not-real')
            self.assertNotIn('Authorization', request.headers)
            self.messages.append(await request.json())
            result = self.answers.pop(0) if self.answers else self.answer('Het licht is aan.')
            if callable(result): result = result()
            return web.json_response(result)

        async def speech(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({'type': 'auth_required'})
            self.assertEqual((await ws.receive_json())['access_token'], 'fake-ha-token')
            await ws.send_json({'type': 'auth_ok'})
            data = await ws.receive_json()
            self.stages.append(data)
            stage = data['start_stage']
            self.assertEqual(data['end_stage'], stage)
            self.assertIn(stage, ('stt', 'tts'), 'HA must not process intent')
            await ws.send_json({'id': 1, 'type': 'result', 'success': True})
            async def event(kind, fields):
                await ws.send_json({'id': 1, 'type': 'event', 'event': {'type': kind, 'data': fields}})
            await event('run-start', {'runner_data': {'stt_binary_handler_id': 7}})
            if stage == 'stt':
                await event('stt-start', {})
                pcm = bytearray()
                async for chunk in ws:
                    self.assertEqual(chunk.type, WSMsgType.BINARY)
                    self.assertEqual(chunk.data[:1], b'\x07')
                    if len(chunk.data) == 1: break
                    pcm.extend(chunk.data[1:])
                self.audio.append(bytes(pcm))
                await event('stt-end', {'stt_output': {'text': 'Zet Reading light aan.'}})
            else:
                await event('tts-end', {'tts_output': {'url': self.tts_url, 'mime_type': 'audio/wav'}})
            await event('run-end', {})
            await ws.close()
            return ws

        async def audio(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer fake-ha-token')
            return web.Response(body=self.reply_audio, content_type='audio/wav')
        app = web.Application()
        app.router.add_post('/messages', messages)
        app.router.add_get('/api/websocket', speech)
        app.router.add_get('/api/tts_proxy/test.wav', audio)
        self.services = TestServer(app)
        await self.services.start_server()
        self.ha.base, self.ha.token = str(self.services.make_url('/api')), 'fake-ha-token'
        self.claude_url = patch.object(voice_anthropic, 'MESSAGES_URL', str(self.services.make_url('/messages')))
        self.claude_url.start()

    async def asyncTearDown(self):
        await base.VoiceTests.asyncTearDown(self)
        self.claude_url.stop()
        await self.services.close()

    @staticmethod
    def answer(text):
        return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': text}]}

    @staticmethod
    def tool(call='tool_1', name='control_switch', arguments=None):
        return {'stop_reason': 'tool_use', 'content': [{'type': 'tool_use', 'id': call, 'name': name,
            'input': arguments or {'name': 'Reading light', 'area': '', 'action': 'turn_on'}}]}

    async def setup_claude(self):
        for path, body in [('config/claude', {'api_key': 'claude-test-key-not-real'}),
                           ('config', {'provider': 'claude'}), ('config', {'pipeline': 'speech'})]:
            response = await self.client.put('/api/voice-preview/' + path, json=body)
            self.assertEqual(response.status, 200, await response.text())

    async def session(self):
        await self.setup_claude()
        response = await self.client.post('/api/voice-preview/claude/sessions', json={'context': panel()})
        self.assertEqual(response.status, 200, await response.text())
        return (await response.json())['id']

    async def turn(self, session, number=1, pcm=None):
        return await self.client.post(f'/api/voice-preview/claude/sessions/{session}/turns/{number}',
            data=pcm if pcm is not None else b'\x00\x10'*8000, headers={'Content-Type': 'application/octet-stream'})

    async def test_settings_keep_both_keys_private_and_survive_restart(self):
        await self.setup_claude()
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertEqual(status['provider'], 'claude')
        self.assertTrue(status['configured'])
        self.assertTrue(status['providers']['openai']['configured'])
        self.assertNotIn('claude-test-key', json.dumps(status))
        self.assertEqual((Path(self.tmp.name) / 'voice-claude-api-key').stat().st_mode & 0o777, 0o600)
        restored = voice_preview.VoicePreview(self.manager)
        self.assertEqual((restored.provider, restored.pipeline, restored.claude_key), ('claude', 'speech', 'claude-test-key-not-real'))
        await self.client.put('/api/voice-preview/config', json={'provider': 'openai'})
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertEqual(status['voice'], 'marin')
        self.assertTrue(status['configured'])
        await self.client.delete('/api/voice-preview/config/claude')
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertFalse(status['providers']['claude']['configured'])
        self.assertTrue(status['providers']['openai']['configured'])
        self.assertEqual(self.messages, [])

    async def test_general_reply_uses_shared_output_without_replacing_ha_speech(self):
        from test_voice_output import add_speaker, SPEAKER, WAV
        add_speaker(self.ha)
        self.reply_audio = WAV
        await self.client.put('/api/voice-preview/config', json={'reply_speaker': SPEAKER, 'reply_volume': 23})
        session = await self.session()
        self.answers = [self.answer('An answer.')]
        result = await (await self.turn(session)).json()
        self.assertEqual(result['reply']['output'], 'sonos')
        self.assertTrue(result['audio'])
        self.assertEqual([stage['start_stage'] for stage in self.stages], ['stt', 'tts'])
        self.assertEqual((await self.client.get(f'/api/voice-preview/claude/sessions/{session}/turns/1/audio')).status, 404)
        self.ha.call.assert_not_awaited()  # Explicit reply delivery starts playback separately.

    async def test_music_confirmation_stays_local_with_external_output_selected(self):
        from test_voice_output import add_speaker, SPEAKER, WAV
        add_speaker(self.ha)
        self.reply_audio = WAV
        context = base.VoiceTests.media_panel(self)
        await self.client.put('/api/voice-preview/config', json={'reply_speaker': SPEAKER, 'reply_volume': 23})
        session = await self.session()
        await self.client.put(f'/api/voice-preview/claude/sessions/{session}/context', json=context)
        self.answers = [self.tool('next_1', 'control_media', {'name': 'Spotify', 'area': '', 'action': 'next'}), self.answer('Next.')]
        result = await (await self.turn(session)).json()
        self.assertTrue(result['end_voice'])
        self.assertNotIn('reply', result)
        response = await self.client.get(f'/api/voice-preview/claude/sessions/{session}/turns/1/audio')
        self.assertEqual(await response.read(), WAV)

    async def test_missing_key_never_falls_back_to_openai(self):
        await self.client.put('/api/voice-preview/config', json={'provider': 'claude'})
        response = await self.client.post('/api/voice-preview/claude/sessions', json={'context': panel()})
        self.assertEqual(response.status, 400)
        self.assertIn('Claude API key', (await response.json())['error'])
        self.assertEqual(self.messages + self.provider_calls + self.stages, [])

    async def test_checks_installed_engines_language_and_availability(self):
        await self.setup_claude()
        for change in ({'tts_engine': None}, {'tts_engine': 'tts.removed'}, {'tts_language': 'xx'}):
            original = deepcopy(self.speech_choices[0]); self.speech_choices[0].update(change)
            status = await (await self.client.get('/api/voice-preview/status')).json()
            self.assertTrue(status['key_configured']); self.assertFalse(status['configured'])
            self.assertTrue(status['pipelines'][0]['stt_ready']); self.assertFalse(status['pipelines'][0]['tts_ready'])
            self.speech_choices[0] = original
        self.ha.states['stt.test'] = {'state': 'unavailable'}
        response = await self.client.post('/api/voice-preview/claude/sessions', json={'context': panel()})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.messages + self.stages, [])

    async def test_complete_turn_uses_ha_audio_shared_tools_and_no_openai(self):
        session = await self.session()
        self.answers = [self.tool(), self.answer('Het licht is aan.')]
        response = await self.turn(session)
        result = await response.json()
        self.assertEqual(result['text'], 'Het licht is aan.')
        self.assertTrue(result['audio']); self.assertTrue(result['action'])
        self.assertEqual(len(self.audio[0]), 16000)
        self.assertEqual([s['start_stage'] for s in self.stages], ['stt', 'tts'])
        self.assertEqual(self.stages[1]['input']['text'], result['text'])
        self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a'})
        self.assertIn('Reading light', self.messages[0]['system'])
        self.assertIn('input_schema', self.messages[0]['tools'][0])
        output = self.messages[1]['messages'][-1]['content'][0]
        self.assertEqual(json.loads(output['content'])['entity_id'], 'light.a')
        audio = await self.client.get(f'/api/voice-preview/claude/sessions/{session}/turns/1/audio')
        self.assertEqual(await audio.read(), b'test-audio')
        self.assertEqual(self.provider_calls, [])
        self.assertEqual((await (await self.turn(session)).json()), result)
        self.ha.call.assert_awaited_once()
        self.assertEqual(len(self.messages), 2)
        self.assertEqual((await self.turn(session, pcm=b'\x01\x00'*8000)).status, 400)

    async def test_revoked_exposure_is_rechecked_before_a_claude_action(self):
        session = await self.session()
        def revoke():
            self.exposure.clear()
            return self.tool()
        self.answers = [revoke, self.answer('Geen toegang.')]
        await self.turn(session)
        self.ha.call.assert_not_awaited()
        result = json.loads(self.messages[1]['messages'][-1]['content'][0]['content'])
        self.assertEqual(result['status'], 'not_exposed')

    async def test_claude_searches_and_plays_through_the_shared_music_tools(self):
        context = base.VoiceTests.media_panel(self)
        self.ha.registry.append({'entity_id': 'media_player.music', 'platform': 'sonos'})
        self.media_actions.add('media_player.play_media')
        response = await self.client.put('/api/voice-preview/spotify', json={
            'client_id': 'test-spotify-client-id', 'client_secret': 'test-spotify-secret', 'market': 'NL'})
        self.assertEqual(response.status, 200)
        session = await self.session()
        response = await self.client.put(f'/api/voice-preview/claude/sessions/{session}/context', json=context)
        self.assertEqual(response.status, 200)
        def play_result():
            result = json.loads(self.messages[-1]['messages'][-1]['content'][0]['content'])
            return self.tool('play_1', 'play_music', {'name': 'Spotify', 'area': '', 'result_id': result['tracks'][0]['result_id']})
        self.answers = [self.tool('search_1', 'search_music', {'name': 'Spotify', 'area': '', 'title': 'Song', 'artist': 'Artist'}),
                        play_result, self.tool('repeat_1', 'control_media', {'name': 'Spotify', 'area': '', 'action': 'repeat', 'repeat_mode': 'one'}),
                        self.answer('Opdracht verstuurd.')]
        with patch.object(voice_music.SpotifyCatalogue, 'search', new_callable=AsyncMock, return_value={
                'status': 'ok', 'tracks': [{'title': 'Song', 'artists': ['Artist'], 'album': 'Album', 'uri': 'spotify:track:' + 'a'*22}]}):
            result = await (await self.turn(session)).json()
        self.assertTrue(result['action'])
        self.assertEqual(self.ha.call.await_count, 2)
        self.assertTrue(result['end_voice'])
        self.ha.call.assert_any_await('media_player.play_media', {'entity_id': 'media_player.music', 'media_content_id': 'spotify:track:' + 'a'*22, 'media_content_type': 'music'})
        self.ha.call.assert_any_await('media_player.repeat_set', {'entity_id': 'media_player.music', 'repeat': 'one'})
        self.assertNotIn('test-spotify-secret', json.dumps(self.messages))
        self.assertEqual(self.provider_calls, [])

    async def test_tts_failure_preserves_successful_action_and_text(self):
        session = await self.session()
        self.answers = [self.tool(), self.answer('Aan.')]
        self.tts_url = 'https://untrusted.example/api/secrets'
        result = await (await self.turn(session)).json()
        self.assertEqual(result['text'], 'Aan.')
        self.assertIn('audio_error', result)
        self.assertNotIn('audio', result)
        self.ha.call.assert_awaited_once()
        await self.turn(session)
        self.ha.call.assert_awaited_once()

    async def test_stop_cancels_speech_and_later_tools(self):
        session = await self.session()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def transcribe(*args):
            started.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        with patch.object(voice_ha_speech.HASpeech, 'transcribe', transcribe):
            task = asyncio.create_task(self.turn(session))
            await asyncio.wait_for(started.wait(), 2)
            await self.client.delete(f'/api/voice-preview/sessions/{session}')
            self.assertTrue(cancelled.is_set())
            self.assertEqual((await task).status, 410)
        self.ha.call.assert_not_awaited()
        self.assertEqual((await self.turn(session)).status, 400)
        self.assertEqual(self.messages, [])

    async def test_oversized_or_malformed_audio_does_not_reach_services(self):
        session = await self.session()
        self.assertEqual((await self.turn(session, pcm=b'0'*(voice_ha_speech.MAX_PCM+2))).status, 400)
        result = await (await self.turn(session, number=2, pcm=b'0'*3201)).json()
        self.assertIn('error', result)
        self.assertEqual(self.messages + self.stages, [])

    async def test_stop_during_lookup_does_not_start_another_model_request(self):
        session = await self.session()
        self.answers = [self.tool(name='lookup_current_information', arguments={'query': 'Weather now?'})]
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def lookup(*args, **kwargs):
            started.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        with patch.object(voice_anthropic.ClaudeLookup, 'lookup', lookup):
            turn = asyncio.create_task(self.turn(session))
            await asyncio.wait_for(started.wait(), 2)
            progress = await (await self.client.get(f'/api/voice-preview/claude/sessions/{session}/turns/1/status')).json()
            self.assertEqual(progress, {'phase': 'searching'})
            await self.client.delete(f'/api/voice-preview/sessions/{session}')
            self.assertEqual((await turn).status, 410)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(len(self.messages), 1)
        self.ha.call.assert_not_awaited()

    async def test_slow_recognition_reports_progress_and_timeout_cancels_without_retry(self):
        session = await self.session()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def transcribe(*args):
            started.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        with patch.object(voice_ha_speech.HASpeech, 'transcribe', transcribe), patch.object(voice_claude, 'TURN_SECONDS', 0.15):
            task = asyncio.create_task(self.turn(session))
            await asyncio.wait_for(started.wait(), 2)
            root = f'/api/voice-preview/claude/sessions/{session}/turns/1'
            self.assertEqual(await (await self.client.get(root + '/status')).json(), {'phase': 'transcribing'})
            result = await (await task).json()
            self.assertIn('speech recognition', result['error'])
            self.assertTrue(cancelled.is_set())
            self.assertEqual(await (await self.client.get(root + '/status')).json(), {'phase': 'complete'})
            self.assertEqual(await (await self.turn(session)).json(), result)
        self.assertEqual(self.messages, [])
        self.ha.call.assert_not_awaited()

    async def test_claude_lookup_requires_citations_and_receives_no_ha_context(self):
        lookup = voice_anthropic.ClaudeLookup()
        self.answers = [{'stop_reason': 'end_turn', 'content': [
            {'type': 'web_search_tool_result', 'content': [{'type': 'web_search_result', 'url': 'https://weather.example'}]},
            {'type': 'text', 'text': 'Cloudy.', 'citations': [
                {'type': 'web_search_result_location', 'url': 'https://weather.example', 'title': 'Weather'},
                {'type': 'web_search_result_location', 'url': 'javascript:alert(1)', 'title': 'Bad'}]}]}]
        result = await lookup.lookup(self.http, 'claude-test-key-not-real', {'query': 'Weather now?'}, model='test-model')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['sources'], [{'url': 'https://weather.example', 'title': 'Weather'}])
        self.assertNotIn('Reading light', json.dumps(self.messages))
        self.answers = [self.answer('Sunny without a source.')]
        result = await lookup.lookup(self.http, 'claude-test-key-not-real', {'query': 'Weather now?'}, model='test-model')
        self.assertEqual(result['status'], 'unavailable')

    async def test_incomplete_provider_tool_call_is_not_executed(self):
        session = await self.session()
        answer = self.tool(); answer['stop_reason'] = 'max_tokens'
        self.answers = [answer]
        result = await (await self.turn(session)).json()
        self.assertIn('error', result)
        self.ha.call.assert_not_awaited()
        await self.turn(session)
        self.assertEqual(len(self.messages), 1, 'Failed turns are never automatically replayed')
