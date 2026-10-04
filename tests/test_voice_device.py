"""Real panel WebSocket framing, fake providers/HA, and actual PCM conversion."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import WSServerHandshakeError, WSMsgType, web
from aiohttp.test_utils import TestServer

import test_voice_preview as base
import test_voice_claude as claude_base
import page_delivery
import voice_device
import voice_openai_relay
from voice_output import pcm_wav
from voice_pcm import Resampler, Utterance, decode_reply


class PCMTests(unittest.TestCase):
    def test_stream_resampling_preserves_duration_and_decodes_reply(self):
        pcm = struct.pack('<16000h', *[1000 if n%40<20 else -1000 for n in range(16000)])
        resampler = Resampler(16000, 24000)
        result = b''.join(resampler.push(pcm[n:n+640]) for n in range(0,len(pcm),640)) + resampler.finish()
        self.assertEqual(len(result), 48000)
        decoded = decode_reply(pcm_wav(result), 'audio/wav')
        self.assertEqual(len(decoded), 32000)
        self.assertGreater(max(struct.unpack('<16000h', decoded)), 900)

    def test_bounded_speech_endpoint_and_silence(self):
        utterance = Utterance()
        for _ in range(500):
            self.assertEqual(utterance.push(b'\0'*640), (None,False))
        self.assertLessEqual(utterance.samples,4800)
        for _ in range(20):
            self.assertTrue(utterance.push(b'\0\x10'*320)[1])
        result = None
        for _ in range(50):
            value, _ = utterance.push(b'\0'*640)
            if value: result = value
        self.assertIsNotNone(result)
        self.assertLess(len(result),64000)

    def test_rejects_invalid_and_oversized_reply(self):
        with self.assertRaises(ValueError): decode_reply(b'data','text/html')
        with self.assertRaises(ValueError): decode_reply(pcm_wav(b'\0\0'*16000*46,16000),'audio/wav')


class DeviceHarness:
    async def setup_device(self):
        self.service = self.manager.device_voice
        self.owner = self.service.owner
        self.screen = {'id':'text_sensor.panel','device_id':'device-a','board':'wavesharep4','name':'Panel'}
        self.record = {'format':'pages-v2','layout':base.panel()['layout'],'sourceGrid':base.panel()['shape']}
        self.manager.screen = lambda inbox: self.screen if inbox==self.screen['id'] else None
        self.manager.screens = lambda:[self.screen]
        self.manager.feedback_board = lambda screen: screen.get('board')
        self.manager.store = SimpleNamespace(get=lambda inbox:self.record)
        self.manager.page_region = lambda:{}
        media = web.Application()
        self.service.register(None,media)
        self.media = TestServer(media); await self.media.start_server()

    async def pairing(self):
        response=await self.client.post('/api/voice-devices/text_sensor.panel/pair',json={'url':'ws://panel-manager.local:8098'})
        self.assertEqual(response.status,200,await response.text())
        return await response.json()

    async def connect(self,pair=None,revision=None):
        pair=pair or await self.pairing()
        ws=await self.http.ws_connect(self.media.make_url('/voice-devices/'+pair['device']),
                                      headers={'Authorization':'Bearer '+pair['token']})
        await ws.send_json({'type':'start','version':1,'rate':16000,'page':0,
                           'revision':revision or page_delivery.configuration(self.record,{})})
        return ws

    async def prepare(self, pair=None):
        pair = pair or await self.pairing()
        ws = await self.http.ws_connect(self.media.make_url('/voice-devices/' + pair['device']),
            headers={'Authorization': 'Bearer ' + pair['token']})
        await ws.send_json({'type': 'prepare', 'version': 2, 'rate': 16000, 'page': 0,
            'revision': page_delivery.configuration(self.record, {})})
        return ws

    async def activate(self, ws):
        await ws.send_json({'type': 'start', 'page': 0,
            'revision': page_delivery.configuration(self.record, {})})
        await self.until(ws, 'listen')

    async def until(self,ws,kind):
        async with asyncio.timeout(20):
            while True:
                event=await ws.receive_json()
                if event['type']==kind:return event


class DeviceTests(DeviceHarness, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await base.VoiceTests.asyncSetUp(self)
        await self.setup_device()
        self.provider_events=[]; self.provider_audio=[]; self.realtime_closed=asyncio.Event()
        self.answer = True
        self.wait_only = False
        self.connections = 0
        async def realtime(request):
            self.connections += 1
            ws=web.WebSocketResponse(); await ws.prepare(request)
            first=await ws.receive_json()
            self.provider_events.append(first)
            await ws.send_json({'type':'session.updated'})
            answered=False
            async for message in ws:
                if message.type!=WSMsgType.TEXT: break
                event=message.json(); self.provider_events.append(event)
                if event['type']=='input_audio_buffer.append':
                    self.provider_audio.append(base64.b64decode(event['audio']))
                    if self.answer and not answered:
                        answered=True
                        await ws.send_json({'type':'response.created','response':{'id':'response-a'}})
                        await ws.send_json({'type':'response.done','response':{'id':'response-a','status':'completed',
                            'output':[{'type':'function_call','call_id':'test-call',
                                       'name':'wait_for_user' if self.wait_only else 'control_switch',
                                       'arguments':json.dumps({} if self.wait_only else
                                           {'name':'Reading light','area':'','action':'turn_on'})}]}})
                elif event['type']=='response.create':
                    await ws.send_json({'type':'response.created','response':{'id':'response-b'}})
                    await ws.send_json({'type':'response.output_audio.delta','response_id':'response-b',
                                       'delta':base64.b64encode(b'\0\x10'*4800).decode()})
                    await ws.send_json({'type':'response.done','response':{'id':'response-b','status':'completed',
                                        'output':[{'type':'message','content':[{'type':'audio'}]}]}})
            self.realtime_closed.set()
            return ws
        provider=web.Application(); provider.router.add_get('/realtime',realtime)
        self.realtime=TestServer(provider); await self.realtime.start_server()
        self.realtime_patch=patch.object(voice_openai_relay,'REALTIME_URL',str(self.realtime.make_url('/realtime')).replace('http:','ws:'))
        self.realtime_patch.start()

    async def asyncTearDown(self):
        await self.media.close(); await self.realtime.close()
        self.realtime_patch.stop()
        await base.VoiceTests.asyncTearDown(self)

    async def test_pairing_hash_only_and_revoke_rejects_token(self):
        pair=await self.pairing()
        saved=self.service.path.read_text()
        self.assertNotIn(pair['token'],saved)
        self.assertIn(hashlib.sha256(pair['token'].encode()).hexdigest(),saved)
        self.assertEqual(self.service.path.stat().st_mode & 0o777,0o600)
        response=await self.client.delete('/api/voice-devices/text_sensor.panel')
        self.assertEqual(response.status,200)
        with self.assertRaises(WSServerHandshakeError):await self.connect(pair)
        self.ha.call.assert_not_awaited()

    async def test_prepared_provider_waits_silently_and_wake_reuses_connection(self):
        self.answer = False
        self.owner.idle_seconds = 1
        ws = await self.prepare()
        await self.until(ws, 'prepared')
        self.assertEqual(self.connections, 1)
        self.assertIsNone(self.provider_events[0]['session']['audio']['input']['turn_detection'])
        self.assertFalse(self.owner.sessions)
        await ws.send_bytes(b'\0\x10' * 320)  # A premature client packet cannot reach a provider.
        await asyncio.sleep(1.1)
        self.assertFalse(ws.closed)
        self.assertFalse(self.provider_audio)
        self.ha.call.assert_not_awaited()
        await self.activate(ws)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.owner.sessions), 1)
        await ws.send_bytes(b'\0\x10' * 1600)
        async with asyncio.timeout(2):
            while not self.provider_audio: await asyncio.sleep(.01)
        await ws.send_json({'type': 'stop'})
        await asyncio.wait_for(self.realtime_closed.wait(), 2)
        await ws.close()

    async def test_start_during_preparation_is_preserved(self):
        self.answer = False
        connect = voice_openai_relay.OpenAIRelay.connect
        began, release = asyncio.Event(), asyncio.Event()
        async def delayed(relay, context, **kwargs):
            began.set()
            await release.wait()
            await connect(relay, context, **kwargs)
        with patch.object(voice_openai_relay.OpenAIRelay, 'connect', delayed):
            ws = await self.prepare()
            await asyncio.wait_for(began.wait(), 2)
            await ws.send_json({'type': 'start', 'page': 0,
                'revision': page_delivery.configuration(self.record, {})})
            release.set()
            await self.until(ws, 'listen')
            self.assertEqual(self.connections, 1)
            await ws.send_json({'type': 'stop'})
            await ws.close()

    async def test_warm_connection_does_not_block_settings_and_closes_on_change(self):
        ws = await self.prepare()
        await self.until(ws, 'prepared')
        response = await self.client.put('/api/voice-preview/config', json={'provider': 'claude'})
        self.assertEqual(response.status, 200, await response.text())
        async with asyncio.timeout(2):
            while not ws.closed: await ws.receive()
        self.ha.call.assert_not_awaited()

    async def test_prepared_session_expires_without_sending_audio(self):
        with patch.object(voice_device, 'WARM_SECONDS', .1):
            ws = await self.prepare()
            await self.until(ws, 'prepared')
            async with asyncio.timeout(2):
                while not ws.closed: await ws.receive()
        self.assertFalse(self.owner.sessions)
        self.assertFalse(self.provider_audio)
        self.ha.call.assert_not_awaited()

    async def test_prepared_stop_cancels_handshake(self):
        began, cancelled = asyncio.Event(), asyncio.Event()
        async def delayed(relay, context, **kwargs):
            began.set()
            try: await asyncio.Future()
            finally: cancelled.set()
        with patch.object(voice_openai_relay.OpenAIRelay, 'connect', delayed):
            ws = await self.prepare()
            await asyncio.wait_for(began.wait(), 2)
            await ws.send_json({'type': 'stop'})
            await asyncio.wait_for(cancelled.wait(), 2)
            await ws.close()

    async def test_new_conversation_uses_fresh_prepared_session(self):
        self.answer = False
        pair = await self.pairing()
        ws = await self.prepare(pair)
        await self.until(ws, 'prepared')
        await self.activate(ws)
        await ws.send_json({'type': 'stop'})
        async with asyncio.timeout(2):
            while not ws.closed: await ws.receive()
            while self.service.active: await asyncio.sleep(.01)
        ws = await self.prepare(pair)
        await self.until(ws, 'prepared')
        self.assertEqual(self.connections, 2)
        self.assertFalse(self.owner.sessions)
        await ws.close()

    async def test_consecutive_conversations_do_not_reuse_audio_or_provider_history(self):
        self.answer = False
        pair = await self.pairing()
        for number, sample in enumerate((2000, -2000), start=1):
            ws = await self.prepare(pair)
            await self.until(ws, 'prepared')
            self.assertEqual(self.connections, number)
            self.assertFalse(self.owner.sessions)
            self.provider_audio.clear()
            self.provider_events.clear()
            await self.activate(ws)
            await ws.send_bytes(struct.pack('<1600h', *([sample] * 1600)))
            async with asyncio.timeout(2):
                while not self.provider_audio: await asyncio.sleep(.01)
            received = self.provider_audio[0]
            samples = struct.unpack('<' + 'h' * (len(received)//2), received)
            self.assertTrue(all(value * sample >= 0 for value in samples))
            self.assertTrue(any(abs(value) > 1500 for value in samples))
            events = [event['type'] for event in self.provider_events]
            self.assertLess(events.index('input_audio_buffer.clear'), events.index('input_audio_buffer.append'))
            self.assertNotIn('conversation.item.create', events)
            await ws.send_json({'type': 'stop'})
            async with asyncio.timeout(2):
                while not ws.closed: await ws.receive()
                while self.service.active: await asyncio.sleep(.01)
        self.ha.call.assert_not_awaited()

    async def test_provider_pause_blocks_inflight_audio_before_panel_pause_finishes(self):
        self.answer = False
        ws = await self.connect()
        await self.until(ws, 'listen')
        session = next(iter(self.service.active.values()))
        # response.created disables upstream capture before its async pause has
        # reached the panel. Late packets must not repopulate the cleared buffer.
        session.relay.input_enabled = False
        await ws.send_bytes(b'\0\x10' * 1600)
        await ws.send_json({'type': 'page', 'page': 1,
            'revision': page_delivery.configuration(self.record, {})})
        async with asyncio.timeout(2):
            while session.page != 1: await asyncio.sleep(.01)
        self.assertEqual(session.audio_bytes, 0)
        self.assertFalse(self.provider_audio)
        await ws.send_json({'type': 'stop'})
        await ws.close()

    async def test_offline_board_uses_the_existing_profile_resolver(self):
        self.screen['board'] = 'unknown'
        self.manager.feedback_board = lambda screen: 'wavesharep4'
        pair = await self.pairing()
        self.assertTrue(pair['token'])
        self.manager.feedback_board = lambda screen: 'guition'
        response = await self.client.post('/api/voice-devices/text_sensor.panel/pair', json={'url': 'ws://panel.local:8098'})
        self.assertEqual(response.status, 400)

    async def test_unknown_wrong_and_browser_tokens_are_rejected(self):
        pair=await self.pairing()
        for token,extra in [('x'*43,{}),(pair['token'],{'Origin':'http://example.test'})]:
            with self.assertRaises(WSServerHandshakeError):
                await self.http.ws_connect(self.media.make_url('/voice-devices/'+pair['device']),
                    headers={'Authorization':'Bearer '+token,**extra})
        self.assertFalse(self.owner.sessions)

    async def test_wrong_layout_revision_is_rejected_before_microphone(self):
        ws=await self.connect(revision='0000000000000000')
        self.assertEqual((await ws.receive_json())['type'],'error')
        await ws.close()
        self.assertFalse(self.provider_events)
        self.ha.call.assert_not_awaited()

    async def test_openai_uses_shared_tools_pcm_and_speaker_backpressure(self):
        ws=await self.connect()
        await self.until(ws,'listen')
        await ws.send_bytes(b'\0\x10'*1600)
        play=await self.until(ws,'play')
        self.assertEqual(play['rate'],16000)
        self.assertEqual(play['bytes'],6400)
        self.ha.call.assert_awaited_once_with('light.turn_on',{'entity_id':'light.a'})
        await ws.send_json({'type':'ready'})
        received=bytearray()
        async with asyncio.timeout(5):
            while True:
                message=await ws.receive()
                if message.type==WSMsgType.BINARY:
                    self.assertLessEqual(len(message.data),2048)
                    received.extend(message.data)
                    await ws.send_json({'type':'credit','bytes':len(received)})
                elif message.type==WSMsgType.TEXT and message.json()['type']=='finish':break
        self.assertEqual(len(received),play['bytes'])
        await ws.send_json({'type':'done'})
        await self.until(ws,'listen')
        await ws.send_json({'type':'stop'})
        await ws.close()
        await asyncio.wait_for(self.realtime_closed.wait(),2)
        self.assertTrue(self.provider_audio)
        for item in self.provider_events:
            settings = item.get('session', {})
            self.assertNotIn('input_audio_transcription', settings)
            self.assertNotIn('transcription', settings.get('audio', {}).get('input', {}))

    async def test_disconnect_and_silence_release_sessions(self):
        self.answer=False; self.owner.idle_seconds=1
        ws=await self.connect(); await self.until(ws,'listen')
        async with asyncio.timeout(3):
            while not ws.closed:await ws.receive()
        await asyncio.wait_for(self.realtime_closed.wait(),2)
        for _ in range(10):
            if not self.owner.sessions:break
            await asyncio.sleep(.01)
        self.assertFalse(self.owner.sessions)
        self.ha.call.assert_not_awaited()

    async def test_wake_only_resumes_silently_without_resetting_idle_budget(self):
        self.wait_only = True
        self.owner.idle_seconds = 2
        ws = await self.connect()
        await self.until(ws, 'listen')
        session = next(iter(self.service.active.values()))
        activity = session.activity
        await ws.send_bytes(b'\0\0' * 1600)  # Fake provider classifies this as activation only.
        async with asyncio.timeout(2):
            while True:
                event = await ws.receive_json()
                self.assertNotIn(event['type'], ('play', 'error'))
                if event['type'] == 'listen': break
        self.assertEqual(session.activity, activity)
        self.assertTrue(session.relay.input_enabled)
        self.assertNotIn('response.create', [event['type'] for event in self.provider_events])
        outputs = [event['item'] for event in self.provider_events if event['type'] == 'conversation.item.create']
        self.assertEqual(json.loads(outputs[0]['output']), {'status': 'ok', 'wait_for_user': True})
        async with asyncio.timeout(3):
            while not ws.closed: await ws.receive()
        self.ha.call.assert_not_awaited()

    async def test_ha_loss_stops_capture_and_no_action(self):
        self.answer=False
        ws=await self.connect(); await self.until(ws,'listen')
        self.ha.online=False
        async with asyncio.timeout(3):
            while not ws.closed:await ws.receive()
        self.ha.call.assert_not_awaited()

    async def test_page_change_context_and_bad_pcm(self):
        self.answer=False
        ws=await self.connect(); await self.until(ws,'listen')
        await ws.send_json({'type':'page','page':1,'revision':page_delivery.configuration(self.record,{})})
        await asyncio.sleep(.02)
        self.assertEqual(next(iter(self.service.active.values())).panel()['page'],1)
        await ws.send_bytes(b'x')
        await self.until(ws,'error')
        await ws.close()
        self.ha.call.assert_not_awaited()

    async def test_stop_cancels_provider_handshake(self):
        began = asyncio.Event()
        cancelled = asyncio.Event()
        async def slow_connect(relay, context):
            began.set()
            try: await asyncio.Future()
            finally: cancelled.set()
        with patch.object(voice_openai_relay.OpenAIRelay, 'connect', slow_connect):
            ws = await self.connect()
            await asyncio.wait_for(began.wait(), 2)
            await ws.send_json({'type': 'stop'})
            await asyncio.wait_for(cancelled.wait(), 2)
            await ws.close()
        self.ha.call.assert_not_awaited()

    async def test_stop_during_speaker_backpressure_releases_provider(self):
        ws = await self.connect(); await self.until(ws, 'listen')
        await ws.send_bytes(b'\0\x10'*1600)
        await self.until(ws, 'play')
        await ws.send_json({'type': 'ready'})
        async with asyncio.timeout(2):
            while (await ws.receive()).type != WSMsgType.BINARY: pass
        # No credit: the device is full or its speaker stalled. Stop still works.
        await ws.send_json({'type': 'stop'})
        await asyncio.wait_for(self.realtime_closed.wait(), 2)
        await ws.close()
        self.ha.call.assert_awaited_once()

    async def test_replacing_pairing_closes_capture_and_old_token(self):
        pair = await self.pairing()
        self.answer = False
        ws = await self.connect(pair); await self.until(ws, 'listen')
        replacement = await self.pairing()
        self.assertNotEqual(pair['token'], replacement['token'])
        async with asyncio.timeout(3):
            while not ws.closed: await ws.receive()
        with self.assertRaises(WSServerHandshakeError): await self.connect(pair)
        self.ha.call.assert_not_awaited()


class DeviceClaudeTests(DeviceHarness, unittest.IsolatedAsyncioTestCase):
    answer = staticmethod(claude_base.ClaudeTests.answer)

    async def asyncSetUp(self):
        await claude_base.ClaudeTests.asyncSetUp(self)
        await self.setup_device()
        await claude_base.ClaudeTests.setup_claude(self)

    async def asyncTearDown(self):
        await self.media.close()
        await claude_base.ClaudeTests.asyncTearDown(self)

    async def test_device_uses_ha_speech_and_shared_claude_actions(self):
        self.reply_audio = pcm_wav(b'\0\x10'*6400, 16000)
        self.answers = [claude_base.ClaudeTests.tool(), self.answer('Het licht is aan.')]
        ws = await self.connect(); await self.until(ws, 'listen')
        for _ in range(20): await ws.send_bytes(b'\0\x10'*320)
        for _ in range(46): await ws.send_bytes(b'\0'*640)
        play = await self.until(ws, 'play')
        self.assertEqual(play['bytes'], 12800)
        await ws.send_json({'type': 'ready'})
        size = 0
        async with asyncio.timeout(5):
            while True:
                message = await ws.receive()
                if message.type == WSMsgType.BINARY:
                    size += len(message.data)
                    await ws.send_json({'type': 'credit', 'bytes': size})
                elif message.type == WSMsgType.TEXT and message.json()['type'] == 'finish': break
        await ws.send_json({'type': 'done'})
        await self.until(ws, 'listen')
        await ws.send_json({'type': 'stop'}); await ws.close()
        self.assertEqual(size, 12800)
        self.assertEqual([stage['start_stage'] for stage in self.stages], ['stt', 'tts'])
        self.assertEqual(len(self.audio), 1)
        self.assertEqual(len(self.messages), 2)
        self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a'})

    async def test_claude_prepare_does_not_start_speech_until_wake(self):
        ws = await self.prepare()
        await self.until(ws, 'prepared')
        self.assertFalse(self.stages)
        self.assertFalse(self.messages)
        self.assertFalse(self.owner.sessions)
        await self.activate(ws)
        self.assertEqual(len(self.owner.sessions), 1)
        await ws.send_json({'type': 'stop'})
        await ws.close()
        self.assertFalse(self.stages)


if __name__=='__main__':unittest.main()
