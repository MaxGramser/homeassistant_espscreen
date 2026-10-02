"""Reply routing and cleanup with fake HA and an HTTP speaker, never real audio."""
import asyncio
import base64
import unittest
import zlib
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

import test_voice_preview as base
import voice_output
import voice_preview

SPEAKER = 'media_player.reply_speaker'
WAV = voice_output.pcm_wav(b'\0' * 4800)


def add_speaker(ha):
    ha.registry.append({'entity_id': SPEAKER, 'platform': 'sonos'})
    ha.states[SPEAKER] = {'state': 'idle', 'attributes': {'friendly_name': 'Reply speaker'}}


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.VoiceTests.asyncSetUp
    asyncTearDown = base.VoiceTests.asyncTearDown
    session = base.VoiceTests.session

    async def test_selection_is_separate_from_tiles_exposure_spotify_and_provider(self):
        add_speaker(self.ha)
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertEqual(status['reply_speaker'], '')
        self.assertEqual(status['reply_speakers'], [{'id': SPEAKER, 'name': 'Reply speaker', 'available': True}])
        self.assertNotIn(SPEAKER, self.exposure)
        response = await self.client.put('/api/voice-preview/config', json={'reply_speaker': SPEAKER, 'reply_volume': 23})
        self.assertEqual(response.status, 200)
        restored = voice_preview.VoicePreview(self.manager)
        self.assertEqual((restored.reply_speaker, restored.reply_volume), (SPEAKER, 23))
        for change in [{'idle_seconds': 9}, {'voice': 'cedar'}, {'provider': 'claude'}]:
            response = await self.client.put('/api/voice-preview/config', json=change)
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['reply_speaker'], SPEAKER)
        self.ha.call.assert_not_awaited()

    async def test_invalid_outputs_and_active_session_changes_are_rejected(self):
        add_speaker(self.ha)
        for speaker, volume in [('light.a', 30), ('media_player.made_up', 30), (SPEAKER, 0), (SPEAKER, 101), (SPEAKER, True), (SPEAKER, 1.5)]:
            response = await self.client.put('/api/voice-preview/config', json={'reply_speaker': speaker, 'reply_volume': volume})
            self.assertEqual(response.status, 400)
        await self.session()
        response = await self.client.put('/api/voice-preview/config', json={'reply_speaker': SPEAKER, 'reply_volume': 30})
        self.assertEqual(response.status, 400)
        self.ha.call.assert_not_awaited()


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ha = SimpleNamespace(registry=[], states={}, online=True, request=AsyncMock(), call=AsyncMock())
        add_speaker(self.ha)
        self.output = voice_output.ReplyOutput(self.ha)
        app = web.Application()
        self.output.register_media(app)
        self.server = TestServer(app)
        await self.server.start_server()
        self.http = ClientSession()
        self.address = patch.object(voice_output.camera_feed, 'base_url', AsyncMock(return_value=str(self.server.make_url('')).rstrip('/')))
        self.address.start()
        self.margin = patch.object(voice_output, 'PLAYBACK_MARGIN', .01)
        self.margin.start()

    async def asyncTearDown(self):
        await self.output.shutdown()
        await self.http.close(); await self.server.close()
        self.address.stop(); self.margin.stop()

    def reply(self, owner='session', speaker=SPEAKER):
        view = self.output.prepare(owner, WAV, 'audio/wav', speaker, 23)
        return self.output.get(owner, view['id'])

    async def download(self, action, data):
        self.assertEqual(action, 'media_player.play_media')
        self.assertEqual(data['entity_id'], SPEAKER)
        self.assertTrue(data['announce'])
        self.assertEqual(data['extra'], {'volume': 23})
        self.url = data['media_content_id']
        async with self.http.get(self.url) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), WAV)

    async def test_waits_for_download_then_duration_and_never_replays_on_duplicate_post(self):
        self.ha.call.side_effect = self.download
        reply = self.reply()
        before = await self.http.get(self.server.make_url(f'/voice/{reply.token}.wav'))
        self.assertEqual(before.status, 404)
        with self.assertRaises(web.HTTPNotFound): self.output.get('other-session', reply.token)
        await self.output.play(reply)
        await self.output.play(reply)
        await reply.fetched.wait()
        self.assertNotEqual(reply.state, 'done')
        await reply.task
        self.assertEqual(reply.state, 'done')
        self.assertFalse(reply.data)
        await self.output.play(reply)
        self.ha.call.assert_awaited_once()
        self.assertEqual((await self.http.get(self.url)).status, 404)

    async def test_service_acceptance_and_head_request_are_not_playback_completion(self):
        reply = self.reply()
        with patch.object(voice_output, 'FETCH_SECONDS', .03):
            await self.output.play(reply)
            response = await self.http.head(self.server.make_url(f'/voice/{reply.token}.wav'))
            self.assertEqual(response.status, 200)
            self.assertFalse(reply.fetched.is_set())
            await reply.task
        self.assertEqual(reply.state, 'error')
        self.assertFalse(reply.data)
        self.assertFalse(self.output.busy)

    async def test_stop_revokes_audio_and_reserves_already_fetched_reply_until_guard_finishes(self):
        self.ha.call.side_effect = self.download
        reply = self.reply()
        await self.output.play(reply)
        await reply.fetched.wait()
        await self.output.close('session')
        self.assertEqual((await self.http.get(self.url)).status, 404)
        with self.assertRaises(ValueError): self.output.validate(SPEAKER, available=True)
        await reply.task
        self.output.validate(SPEAKER, available=True)
        self.ha.call.assert_awaited_once()  # Stop does not stop unrelated music.

    async def test_output_is_revalidated_and_concurrent_sessions_cannot_share_speaker(self):
        reply = self.reply()
        self.ha.states[SPEAKER]['state'] = 'unavailable'
        with self.assertRaises(ValueError): await self.output.play(reply)
        self.ha.call.assert_not_awaited()
        self.ha.states[SPEAKER]['state'] = 'idle'
        await self.output.play(reply)
        with self.assertRaises(ValueError): await self.output.play(self.reply('other'))
        await self.output.close('session')
        self.assertFalse(self.output.busy)

    def test_invalid_truncated_and_unbounded_audio_are_rejected(self):
        for audio in (b'', b'bad audio', WAV[:-100], voice_output.pcm_wav(b'\0'*48000)[:44]):
            with self.assertRaises(ValueError): self.output.prepare('session', audio, 'audio/wav', SPEAKER, 30)
        with self.assertRaises(ValueError): self.output.prepare('session', b'ogg', 'audio/ogg', SPEAKER, 30)
        with self.assertRaises(ValueError): voice_output.pcm_wav(b'odd')

    def test_mp3_speech_duration_is_read_and_invalid_mp3_rejected(self):
        # Locally generated 150 ms of silence, MPEG-2 Layer III, 24 kHz mono.
        audio = zlib.decompress(base64.b64decode(
            'eJzzdDFmYQABpZDgYFcgzcfAwOyTWJZmZqRnrGdoYMCAAP8/uxwBUsweII6Po68rWEEoFQDEMJD5wTDzqWQyuvnLaGz+mlHzB8B8CEAxn9qG08F8ALPdGVg='))
        seconds = voice_output.duration(audio, 'audio/mpeg')
        self.assertGreater(seconds, .15)
        self.assertLess(seconds, .3)
        with self.assertRaises(ValueError): voice_output.duration(b'invalid mp3', 'audio/mpeg')


if __name__ == '__main__': unittest.main()
