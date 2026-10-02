"""Real HTTP voice-to-catalogue-to-HA boundaries, with simulated services only."""
import asyncio
from base64 import b64decode
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

import test_voice_preview as base
import assistant_tools
import voice_music
import voice_preview

SETTINGS = {'client_id': 'client-for-local-testing', 'client_secret': 'secret-for-local-testing', 'market': 'NL'}
TRACK = {'id': 'a'*22, 'type': 'track', 'uri': 'spotify:track:' + 'a'*22,
         'name': 'Example song', 'artists': [{'name': 'Example artist'}], 'album': {'name': 'Example album'}, 'is_playable': True}


class MusicTests(unittest.IsolatedAsyncioTestCase):
    session = base.VoiceTests.session
    media_panel = base.VoiceTests.media_panel

    async def asyncSetUp(self):
        await base.VoiceTests.asyncSetUp(self)
        self.context = self.media_panel()
        self.ha.registry.append({'entity_id': 'media_player.music', 'platform': 'sonos'})
        self.media_actions.add('media_player.play_media')
        self.searches, self.tokens = [], 0
        self.search_status, self.token_status = 200, 200
        self.search_data = {'tracks': {'items': [deepcopy(TRACK)]}}
        self.delay, self.started = None, asyncio.Event()

        async def token(request):
            self.tokens += 1
            self.assertEqual(b64decode(request.headers['Authorization'].removeprefix('Basic ')).decode(), SETTINGS['client_id'] + ':' + SETTINGS['client_secret'])
            self.assertEqual(dict(await request.post()), {'grant_type': 'client_credentials'})
            return web.json_response({'access_token': 'catalogue-test-token', 'expires_in': 3600}, status=self.token_status)

        async def search(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer catalogue-test-token')
            self.searches.append(dict(request.query))
            self.started.set()
            if self.delay: await self.delay.wait()
            return web.json_response(self.search_data, status=self.search_status)

        app = web.Application()
        app.router.add_post('/token', token)
        app.router.add_get('/search', search)
        self.spotify = TestServer(app)
        await self.spotify.start_server()
        self.urls = patch.multiple(voice_music, TOKEN_URL=str(self.spotify.make_url('/token')), SEARCH_URL=str(self.spotify.make_url('/search')))
        self.urls.start()

    async def asyncTearDown(self):
        if self.delay: self.delay.set()
        self.urls.stop()
        await self.spotify.close()
        await base.VoiceTests.asyncTearDown(self)

    async def configure(self):
        response = await self.client.put('/api/voice-preview/spotify', json=SETTINGS)
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def command(self, session, name, arguments=None, call='search_1'):
        response = await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': call, 'name': name, 'arguments': {'name': 'Spotify', 'area': '', **(arguments or {})}, 'context': self.context})
        return await response.json()

    async def search(self, session, call='search_1'):
        return await self.command(session, 'search_music', {'title': 'Example song', 'artist': 'Example artist'}, call)

    async def play(self, session, result_id, call='play_1'):
        return await self.command(session, 'play_music', {'result_id': result_id}, call)

    async def test_private_settings_persist_and_remove_without_touching_ai_keys(self):
        status = await self.configure()
        self.assertEqual(status['spotify'], {'configured': True, 'market': 'NL'})
        self.assertNotIn(SETTINGS['client_secret'], json.dumps(status))
        self.assertNotIn(SETTINGS['client_id'], json.dumps(status))
        path = Path(self.tmp.name) / 'voice-spotify.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        restored = voice_preview.VoicePreview(self.manager)
        self.assertEqual(restored.music.settings, SETTINGS)
        self.assertEqual(restored.key, 'test-only-not-a-key')
        with patch.dict('os.environ', {'SCREEN_VOICE_POC': '0'}):
            self.assertFalse(voice_preview.VoicePreview(self.manager).music.configured)
        response = await self.client.delete('/api/voice-preview/spotify')
        self.assertFalse((await response.json())['spotify']['configured'])
        self.assertFalse(path.exists())
        self.assertEqual(self.tokens, 0)

    async def test_invalid_settings_and_active_sessions_cannot_replace_configuration(self):
        await self.configure()
        for bad in ({**SETTINGS, 'client_secret': 'short'}, {**SETTINGS, 'market': 'NLD'}, {**SETTINGS, 'token': 'injected'}):
            self.assertEqual((await self.client.put('/api/voice-preview/spotify', json=bad)).status, 400)
        await self.session(self.context)
        self.assertEqual((await self.client.delete('/api/voice-preview/spotify')).status, 400)
        self.assertEqual(json.loads((Path(self.tmp.name) / 'voice-spotify.json').read_text()), SETTINGS)

    async def test_search_is_read_only_and_caches_catalogue_token(self):
        await self.configure()
        session = await self.session(self.context)
        context = await (await self.client.post('/api/voice-preview/context', json=self.context)).json()
        player = assistant_tools.resolve(context['context'], 'Spotify')['matches'][0]
        self.assertIn('search_music', player['available_actions'])
        result = await self.search(session)
        self.assertEqual(result['status'], 'ok')
        self.assertNotIn('end_voice', result)
        self.assertEqual(result['tracks'][0]['artists'], ['Example artist'])
        self.assertNotIn('uri', result['tracks'][0])
        self.assertNotIn('secret', json.dumps(result))
        await self.search(session, 'second_search')
        self.assertEqual(self.tokens, 1)
        self.assertEqual(self.searches[0], {'q': 'track:"Example song" artist:"Example artist"', 'type': 'track', 'limit': '5', 'market': 'NL'})
        self.ha.call.assert_not_awaited()

    async def test_play_uses_server_held_result_and_duplicate_delivery_calls_ha_once(self):
        await self.configure()
        session = await self.session(self.context)
        result_id = (await self.search(session))['tracks'][0]['result_id']
        results = await asyncio.gather(self.play(session, result_id), self.play(session, result_id))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]['status'], 'accepted')
        self.assertTrue(results[0]['end_voice'])
        self.ha.call.assert_awaited_once_with('media_player.play_media', {
            'entity_id': 'media_player.music', 'media_content_id': TRACK['uri'], 'media_content_type': 'music'})

    async def test_result_cannot_be_invented_reused_across_sessions_or_sent_to_another_target(self):
        await self.configure()
        session = await self.session(self.context)
        result_id = (await self.search(session))['tracks'][0]['result_id']
        other = await self.session(self.context)
        self.assertEqual((await self.play(other, result_id))['status'], 'error')
        self.assertEqual((await self.play(session, TRACK['uri']))['status'], 'error')
        result = await self.command(session, 'play_music', {'result_id': result_id, 'media_content_id': 'https://untrusted.example/song'}, 'extra')
        self.assertEqual(result['status'], 'error')
        with patch.object(voice_music.time, 'monotonic', return_value=0):
            cached = {}; choice = voice_music.remember(cached, 'media_player.music', [dict(uri=TRACK['uri'], title='Song')])[0]['result_id']
        # Keep every lookup on the same fake clock. A fresh CI runner can have
        # less uptime than RESULT_SECONDS, so the real clock does not prove expiry.
        with patch.object(voice_music.time, 'monotonic', return_value=voice_music.RESULT_SECONDS - 1):
            self.assertEqual(voice_music.selection(cached, 'media_player.music', choice)['uri'], TRACK['uri'])
            with self.assertRaises(ValueError): voice_music.selection(cached, 'media_player.other', choice)
        with patch.object(voice_music.time, 'monotonic', return_value=voice_music.RESULT_SECONDS):
            with self.assertRaises(ValueError): voice_music.selection(cached, 'media_player.music', choice)
        self.ha.call.assert_not_awaited()

    async def test_capability_and_exposure_are_rechecked_before_playback(self):
        await self.configure()
        session = await self.session(self.context)
        result_id = (await self.search(session))['tracks'][0]['result_id']
        self.media_actions.remove('media_player.play_media')
        self.assertEqual((await self.play(session, result_id))['status'], 'unsupported')
        self.media_actions.add('media_player.play_media')
        self.exposure.pop('media_player.music')
        self.assertEqual((await self.play(session, result_id, 'hidden'))['status'], 'not_exposed')
        self.ha.call.assert_not_awaited()

    async def test_unconfigured_search_and_other_players_do_not_resume_music(self):
        session = await self.session(self.context)
        self.assertEqual((await self.search(session))['status'], 'not_configured')
        self.ha.registry[-1]['platform'] = 'cast'
        self.assertEqual((await self.search(session, 'unsupported'))['status'], 'unsupported')
        result = await self.command(session, 'control_media', {'action': 'pause'}, 'pause')
        self.assertEqual(result['status'], 'accepted')
        self.ha.call.assert_awaited_once_with('media_player.media_pause', {'entity_id': 'media_player.music'})
        self.assertEqual(self.tokens, 0)

    async def test_bad_catalogue_ids_and_unplayable_results_are_discarded(self):
        await self.configure()
        session = await self.session(self.context)
        self.search_data['tracks']['items'] = [
            {**TRACK, 'uri': 'https://untrusted.example'}, {**TRACK, 'is_playable': False},
            {**TRACK, 'restrictions': {'reason': 'market'}}, {**TRACK, 'type': 'album'}, {**TRACK, 'artists': []}]
        self.assertEqual((await self.search(session))['status'], 'not_found')
        self.ha.call.assert_not_awaited()

    async def test_idle_spotify_cannot_silently_choose_a_device(self):
        await self.configure()
        self.ha.registry[-1]['platform'] = 'spotify'
        session = await self.session(self.context)
        result_id = (await self.search(session))['tracks'][0]['result_id']
        self.ha.states['media_player.music']['attributes'].pop('source')
        result = await self.play(session, result_id)
        self.assertEqual(result['status'], 'output_required')
        self.assertEqual(result['source_list'], ['Kitchen', 'Bedroom'])
        self.ha.call.assert_not_awaited()

    async def test_catalogue_failure_does_not_retry_or_report_playback_success(self):
        await self.configure()
        session = await self.session(self.context)
        for status in (401, 403, 429, 500):
            self.search_status = status
            result = await self.search(session, f'failure_{status}')
            self.assertEqual(result['status'], 'unavailable')
            self.assertNotIn('catalogue-test-token', json.dumps(result))
        self.assertEqual(len(self.searches), 4)
        self.ha.call.assert_not_awaited()

    async def test_stop_cancels_pending_search_and_never_starts_playback(self):
        await self.configure()
        session = await self.session(self.context)
        self.delay = asyncio.Event()
        pending = asyncio.create_task(self.search(session))
        await asyncio.wait_for(self.started.wait(), 2)
        await self.client.delete(f'/api/voice-preview/sessions/{session}')
        self.delay.set()
        await asyncio.gather(pending, return_exceptions=True)
        self.ha.call.assert_not_awaited()
