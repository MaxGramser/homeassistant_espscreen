"""Voice boundaries with real HTTP transport and fake OpenAI/HA, never paid calls."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import voice_preview as voice
import assistant_tools
import voice_providers


def tile(eid, label, column=0):
    return {'id': f'tile_{eid.replace(".", "_")}_{column}', 'content': {'kind': 'entity', 'entityId': eid},
            'placement': {'row': 0, 'column': column, 'columns': 1, 'rows': 1},
            'appearance': {'label': label}, 'interaction': {}}


def page(name, tiles):
    return {'id': name, 'navigation': {'excludeFromPagination': False},
            'topbar': {'leading': [], 'title': {'source': 'screen'}, 'trailing': []}, 'tiles': tiles}


def panel():
    return {'shape': {'columns': 2, 'rows': 3}, 'page': 0,
            'layout': {'title': 'Test panel', 'homePageId': '0000000000000001', 'pages': [
                page('0000000000000001', [tile('light.a', 'Reading light')]),
                page('0000000000000002', [tile('light.b', 'Desk')])]}}


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.exposure = {'light.a': {'conversation': True}, 'light.b': {'conversation': True}}
        self.ha = SimpleNamespace(online=True, registry=[
            {'entity_id': 'light.a', 'aliases': ['Armchair'], 'area_id': 'living'},
            {'entity_id': 'light.b', 'aliases': [], 'area_id': 'study'}], devices=[],
            areas=[{'area_id': 'living', 'name': 'Living room', 'aliases': ['Lounge']}, {'area_id': 'study', 'name': 'Study'}],
            states={'light.a': {'state': 'off', 'attributes': {'friendly_name': 'Corner lamp'}},
                    'light.b': {'state': 'on', 'attributes': {'friendly_name': 'Reading light'}},
                    'switch.private': {'state': 'off', 'attributes': {'friendly_name': 'Private switch'}}},
            request=AsyncMock(side_effect=lambda _: {'exposed_entities': deepcopy(self.exposure)}),
            call=AsyncMock(), entity_actions=AsyncMock(return_value={'light.turn_on', 'light.turn_off'}))
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = SimpleNamespace(ha=self.ha, path=Path(self.tmp.name) / 'screens.json')
        self.provider_calls = []
        self.hangups = []
        async def start(request):
            self.assertEqual(request.content_type, 'multipart/form-data')
            form = await request.post()
            self.provider_calls.append((form['sdp'], json.loads(form['session'])))
            return web.Response(status=201, text='v=0\r\nanswer', headers={'Location': '/v1/realtime/calls/rtc_test'})
        async def hangup(request):
            self.hangups.append(request.match_info['call'])
            return web.Response()
        provider = web.Application()
        provider.router.add_post('/calls', start)
        provider.router.add_post('/calls/{call}/hangup', hangup)
        self.provider = TestServer(provider)
        await self.provider.start_server()
        self.http = ClientSession()
        self.ha.session = self.http
        self.environment = patch.dict('os.environ', {'SCREEN_VOICE_POC': '1', 'OPENAI_API_KEY': 'test-only-not-a-key'})
        self.environment.start()
        self.url = patch.object(voice_providers, 'CALLS_URL', str(self.provider.make_url('/calls')))
        self.url.start()
        @web.middleware
        async def errors(request, handler):
            try:
                return await handler(request)
            except (ValueError, ConnectionError) as error:
                return web.json_response({'error': str(error)}, status=400)
        app = web.Application(middlewares=[errors])
        voice.register(app, self.manager)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.http.close()
        await self.provider.close()
        self.url.stop()
        self.environment.stop()
        self.tmp.cleanup()

    async def session(self, context=None):
        response = await self.client.post('/api/voice-preview/sessions', json={'sdp': 'v=0\r\noffer', 'context': context or panel()})
        self.assertEqual(response.status, 200, await response.text())
        return (await response.json())['id']

    async def command(self, session, call='call_1', context=None, **arguments):
        return await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': call, 'name': 'control_switch',
            'arguments': {'name': 'Reading light', 'area': '', 'action': 'turn_on', **arguments},
            'context': context or panel()})

    async def lookup(self, session, call='lookup_1', query='Current weather in Amsterdam?'):
        return await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': call, 'name': 'lookup_current_information', 'arguments': {'query': query}})

    async def test_lookup_is_independent_of_ha_and_duplicate_requests_search_once(self):
        session = await self.session()
        self.ha.online = False
        self.ha.request.reset_mock()
        result = {'status': 'ok', 'answer': 'Cloudy.', 'sources': [{'url': 'https://weather.example', 'title': 'Weather'}]}
        with patch.object(voice.voice_lookup, 'lookup', new_callable=AsyncMock, return_value=result) as search:
            requests = await asyncio.gather(self.lookup(session), self.lookup(session))
            self.assertEqual([await r.json() for r in requests], [result, result])
            search.assert_awaited_once_with(self.http, 'test-only-not-a-key',
                                          {'query': 'Current weather in Amsterdam?'}, model=voice.voice_lookup.DEFAULT_MODEL)
            self.assertEqual((await self.lookup(session, query='A different question')).status, 400)
        self.ha.call.assert_not_awaited()
        self.ha.request.assert_not_awaited()

    async def test_failed_lookup_keeps_device_commands_available(self):
        session = await self.session()
        with patch.object(voice.voice_lookup, 'lookup', new_callable=AsyncMock, return_value=voice.voice_lookup.UNAVAILABLE):
            self.assertEqual((await (await self.lookup(session)).json())['status'], 'unavailable')
        self.assertEqual((await (await self.command(session)).json())['status'], 'accepted')

    async def test_stop_cancels_inflight_search_and_refuses_later_lookup(self):
        session = await self.session()
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def pending(*args, **kwargs):
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        with patch.object(voice.voice_lookup, 'lookup', side_effect=pending) as search:
            request = asyncio.create_task(self.lookup(session))
            await asyncio.wait_for(started.wait(), 2)
            await self.client.delete(f'/api/voice-preview/sessions/{session}')
            result = await asyncio.wait_for(request, 2)
            self.assertEqual((await result.json())['status'], 'cancelled')
            self.assertTrue(cancelled.is_set())
            self.assertEqual((await self.lookup(session, call='late')).status, 400)
            search.assert_awaited_once()
        self.ha.call.assert_not_awaited()

    async def test_screen_help_reads_current_page_without_operating_devices(self):
        session = await self.session()
        data = panel(); data['page'] = 1
        result = await (await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': 'help', 'name': 'get_panel_context', 'arguments': {}, 'context': data})).json()
        self.assertEqual(result['visible'][0]['label'], 'Desk')
        self.ha.call.assert_not_awaited()

    async def test_audio_adapter_receives_shared_context_and_neutral_tool_schemas(self):
        connection = SimpleNamespace(connect=AsyncMock(return_value='v=0\r\nfake answer'), close=AsyncMock())
        provider = SimpleNamespace(id='test-audio', label='Test audio', default_model='test-model',
                                   voices=('test-voice',), session=lambda http, key: connection)
        service = voice.VoicePreview(self.manager, audio_provider=provider)
        request = SimpleNamespace(json=AsyncMock(return_value={'sdp': 'v=0\r\noffer', 'context': panel()}))
        response = await service.start(request)
        try:
            data = json.loads(response.text)
            self.assertEqual(data['sdp'], 'v=0\r\nfake answer')
            self.assertEqual(service.configuration()['audio_provider'], 'test-audio')
            options = connection.connect.call_args.kwargs
            self.assertIn('Reading light', options['instructions'])
            self.assertEqual(options['voice'], 'test-voice')
            self.assertTrue(all('type' not in tool and 'parameters' in tool for tool in options['tools']))
            self.assertIn('control_switch', [tool['name'] for tool in options['tools']])
            self.assertEqual(self.provider_calls, [], 'A different adapter must not call OpenAI')
            context = await assistant_tools.panel_context(self.manager, panel(), private=True)
            result = await assistant_tools.execute(self.manager, 'control_switch',
                {'name': 'Reading light', 'area': '', 'action': 'turn_on'}, context)
            self.assertEqual(result['status'], 'accepted')
            self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a'})
        finally:
            await service.cleanup(None)
        connection.close.assert_awaited_once()

    async def test_visible_name_wins_over_conflicting_ha_name_and_alias_is_fallback(self):
        context = await assistant_tools.panel_context(self.manager, panel())
        self.assertEqual(assistant_tools.resolve(context, '  READING light ')['matches'][0]['entity_id'], 'light.a')
        self.assertEqual(assistant_tools.resolve(context, 'Corner lamp')['matches'][0]['entity_id'], 'light.a')
        self.assertEqual(assistant_tools.resolve(context, 'Armchair')['source'], 'home_assistant')
        self.assertNotIn('switch.private', json.dumps(context))
        self.assertEqual(assistant_tools.resolve(context, 'Reading light', 'Study')['matches'][0]['entity_id'], 'light.b')

    async def test_page_change_and_name_changes_refresh_context(self):
        data = panel(); data['page'] = 1
        context = await assistant_tools.panel_context(self.manager, data)
        self.assertEqual(assistant_tools.resolve(context, 'Reading light')['matches'][0]['entity_id'], 'light.b')
        self.assertEqual(context['visible'][0]['label'], 'Desk')
        data['layout']['pages'][1]['tiles'][0]['appearance']['label'] = ''
        self.assertEqual((await assistant_tools.panel_context(self.manager, data))['visible'][0]['label'], 'Reading light')
        data['page'] = -1
        with self.assertRaises(ValueError): await assistant_tools.panel_context(self.manager, data)

    async def test_duplicate_labels_require_clarification_and_do_not_call_ha(self):
        data = panel()
        data['layout']['pages'][1]['tiles'] = []
        data['layout']['pages'][0]['tiles'].append(tile('light.b', 'Reading light', 1))
        result = await (await self.command(await self.session(), context=data)).json()
        self.assertEqual(result['status'], 'ambiguous')
        self.ha.call.assert_not_awaited()

    async def test_direct_audio_configuration_and_close(self):
        session = await self.session()
        config = self.provider_calls[0][1]
        self.assertEqual(config['type'], 'realtime')
        self.assertTrue(all(tool['type'] == 'function' for tool in config['tools']))
        self.assertNotIn('transcription', config['audio']['input'])
        self.assertNotIn('whisper', json.dumps(config).lower())
        self.assertEqual(config['audio']['output']['voice'], 'marin')
        self.assertIn('Reading light', config['instructions'])
        await self.client.delete(f'/api/voice-preview/sessions/{session}')
        self.assertEqual(self.hangups, ['rtc_test'])
        self.assertEqual((await self.command(session)).status, 400)

    async def test_duplicate_delivery_calls_ha_once_and_reports_observed_state(self):
        session = await self.session()
        results = await asyncio.gather(self.command(session), self.command(session))
        first, second = [await r.json() for r in results]
        self.assertEqual(first, second)
        self.assertEqual(first, {'status': 'accepted', 'entity_id': 'light.a', 'action': 'turn_on', 'observed_state': 'off'})
        self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a'})
        self.assertEqual((await self.command(session, action='turn_off')).status, 400)

    async def test_revoked_exposure_and_arbitrary_entity_ids_cannot_be_controlled(self):
        session = await self.session()
        self.exposure.clear()
        result = await (await self.command(session)).json()
        self.assertEqual(result['status'], 'not_exposed')
        result = await (await self.command(session, call='call_2', name='switch.private')).json()
        self.assertEqual(result['status'], 'not_found')
        self.ha.call.assert_not_awaited()

    async def test_hidden_visible_target_does_not_fall_through_to_another_ha_entity(self):
        session = await self.session()
        self.exposure.pop('light.a')
        result = await (await self.command(session)).json()
        self.assertEqual(result['status'], 'not_exposed')
        self.ha.call.assert_not_awaited()

    async def test_disconnect_and_toggle_fail_without_actions(self):
        session = await self.session()
        self.assertEqual((await (await self.command(session, action='toggle')).json())['status'], 'error')
        self.ha.online = False
        self.assertEqual((await (await self.command(session, call='call_2')).json())['status'], 'error')
        self.ha.call.assert_not_awaited()

    async def test_ambiguous_ha_timeout_is_not_retried(self):
        session = await self.session()
        self.ha.call.side_effect = TimeoutError
        result = await (await self.command(session)).json()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(await (await self.command(session)).json(), result)
        self.ha.call.assert_awaited_once()

    async def test_key_absent_still_allows_local_context_check(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': '', 'OPENAI_API_KEY_FILE': ''}):
            instance = voice.VoicePreview(self.manager)
            self.assertFalse(instance.key)
            self.assertTrue(instance.enabled)
        result = await (await self.client.post('/api/voice-preview/context', json=panel())).json()
        self.assertEqual(result['context']['page'], 1)
        self.assertEqual(self.provider_calls, [])

    async def test_editor_key_is_private_persistent_and_never_returned(self):
        fake = 'sk-test-not-a-real-key-for-local-tests'
        response = await self.client.put('/api/voice-preview/config', json={'api_key': fake})
        self.assertEqual(response.status, 200)
        self.assertNotIn(fake, await response.text())
        self.assertEqual((await response.json())['source'], 'editor')
        self.assertEqual(self.provider_calls, [], 'Saving credentials must not start a paid session')
        path = Path(self.tmp.name) / 'voice-api-key'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(voice.VoicePreview(self.manager).key, fake)
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertTrue(status['configured'])
        self.assertNotIn(fake, json.dumps(status))
        await self.client.delete('/api/voice-preview/config')
        self.assertFalse(path.exists())
        status = await (await self.client.get('/api/voice-preview/status')).json()
        self.assertEqual(status['source'], 'server', 'The separately configured environment key is left intact')

    async def test_invalid_key_leaves_existing_credentials_unchanged(self):
        response = await self.client.put('/api/voice-preview/config', json={'api_key': 'invalid\nkey'})
        self.assertEqual(response.status, 400)
        self.assertFalse((Path(self.tmp.name) / 'voice-api-key').exists())
        await self.session()
        response = await self.client.put('/api/voice-preview/config', json={'api_key': 'sk-test-not-a-real-key-for-local-tests'})
        self.assertEqual(response.status, 400, 'Do not replace credentials while a call is active')

    async def test_key_write_route_uses_existing_editor_csrf_guard(self):
        from server import Manager, create_app
        from test_scaling import fake_ha
        client = TestClient(TestServer(create_app(Manager(fake_ha(), Path(self.tmp.name) / 'screens.json'), True)))
        await client.start_server()
        try:
            response = await client.put('/api/voice-preview/config', json={'api_key': 'sk-test-not-a-real-key-for-local-tests'})
            self.assertEqual(response.status, 403)
            self.assertFalse((Path(self.tmp.name) / 'voice-api-key').exists())
            response = await client.put('/api/voice-preview/config', json={'voice': 'cedar'})
            self.assertEqual(response.status, 403)
            self.assertFalse((Path(self.tmp.name) / 'voice-settings.json').exists())
        finally:
            await client.close()

    async def test_idle_timeout_is_validated_persisted_and_preserved_by_other_settings(self):
        self.assertEqual((await (await self.client.get('/api/voice-preview/status')).json())['idle_seconds'], 5)
        for seconds in (1, 12, 300):
            response = await self.client.put('/api/voice-preview/config', json={'idle_seconds': seconds})
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['idle_seconds'], seconds)
            self.assertEqual(voice.VoicePreview(self.manager).idle_seconds, seconds)
        for value in (0, -1, 301, 1.5, True, '5', None):
            response = await self.client.put('/api/voice-preview/config', json={'idle_seconds': value})
            self.assertEqual(response.status, 400)
        await self.client.put('/api/voice-preview/config', json={'voice': 'cedar'})
        self.assertEqual(voice.VoicePreview(self.manager).idle_seconds, 300)
        self.assertEqual(self.provider_calls, [])

    async def test_legacy_disabled_timeout_uses_default_and_is_saved_with_other_settings(self):
        settings = Path(self.tmp.name) / 'voice-settings.json'
        settings.write_text(json.dumps({'idle_seconds': 0, 'voice': 'cedar', 'provider': 'claude', 'pipeline': 'speech'}))
        restored = voice.VoicePreview(self.manager)
        self.assertEqual(restored.configuration()['idle_seconds'], 5)
        restored.save_settings(voice='marin')
        self.assertEqual(json.loads(settings.read_text()), {
            'idle_seconds': 5, 'voice': 'marin', 'provider': 'claude', 'pipeline': 'speech',
            'reply_speaker': '', 'reply_volume': 30})

    async def test_voice_selection_persists_and_only_changes_new_sessions(self):
        old_session = await self.session()
        self.assertEqual(self.provider_calls[-1][1]['audio']['output']['voice'], 'marin')
        response = await self.client.put('/api/voice-preview/config', json={'voice': 'cedar'})
        self.assertEqual(response.status, 200)
        status = await response.json()
        self.assertEqual(status['voice'], 'cedar')
        self.assertIn('cedar', status['voices'])
        self.assertEqual(voice.VoicePreview(self.manager).voice, 'cedar')
        self.assertEqual(self.hangups, [])
        self.assertEqual(len(self.provider_calls), 1, 'Saving a voice does not make an OpenAI call')
        self.assertEqual((await self.command(old_session)).status, 200)
        await self.session()
        self.assertEqual(self.provider_calls[-1][1]['audio']['output']['voice'], 'cedar')
        response = await self.client.put('/api/voice-preview/config', json={'voice': 'invented'})
        self.assertEqual(response.status, 400)
        self.assertEqual(voice.VoicePreview(self.manager).voice, 'cedar')
        await self.client.delete(f'/api/voice-preview/sessions/{old_session}')

    def media_panel(self):
        self.exposure['media_player.music'] = {'conversation': True}
        self.ha.states['media_player.music'] = {'state': 'playing', 'attributes': {
            'friendly_name': 'Music account', 'source': 'Kitchen', 'source_list': ['Kitchen', 'Bedroom'],
            'volume_level': 0.42, 'media_title': 'A track', 'media_artist': 'An artist',
            'entity_picture': '/api/artwork?secret=private'}}
        self.media_actions = {'media_player.media_play', 'media_player.media_pause', 'media_player.media_stop',
                              'media_player.media_next_track', 'media_player.media_previous_track',
                              'media_player.volume_set', 'media_player.volume_up', 'media_player.volume_down',
                              'media_player.volume_mute', 'media_player.select_source', 'media_player.repeat_set'}
        self.ha.entity_actions.side_effect = lambda eid: self.media_actions if eid.startswith('media_player.') else {'light.turn_on', 'light.turn_off'}
        data = panel()
        data['layout']['pages'][0]['tiles'].append(tile('media_player.music', 'Spotify', 1))
        return data

    async def media_command(self, session, context, call='media_1', **args):
        return await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': call, 'name': 'control_media',
            'arguments': {'name': 'Spotify', 'area': '', 'action': 'pause', **args}, 'context': context})

    async def test_media_context_shares_current_metadata_and_only_supported_actions(self):
        data = self.media_panel()
        self.media_actions = {'media_player.select_source'}
        self.ha.states['media_player.music']['state'] = 'idle'
        context = await assistant_tools.panel_context(self.manager, data)
        entity = assistant_tools.resolve(context, 'Spotify')['matches'][0]
        self.assertTrue(entity['can_control'])
        self.assertEqual(entity['available_actions'], ['select_source'])
        self.assertEqual(entity['media']['volume_percent'], 42)
        self.assertEqual(entity['media']['media_title'], 'A track')
        self.assertEqual(entity['media']['source_list'], ['Kitchen', 'Bedroom'])
        self.assertNotIn('secret', json.dumps(context))
        self.exposure.pop('media_player.music')
        self.assertNotIn('An artist', json.dumps(await assistant_tools.panel_context(self.manager, data)))

    async def test_media_playback_volume_and_source_use_existing_ha_services(self):
        data = self.media_panel()
        session = await self.session(data)
        cases = [
            ({'action': 'play'}, 'media_play', {}),
            ({'action': 'pause'}, 'media_pause', {}),
            ({'action': 'stop'}, 'media_stop', {}),
            ({'action': 'next'}, 'media_next_track', {}),
            ({'action': 'previous'}, 'media_previous_track', {}),
            ({'action': 'repeat', 'repeat_mode': 'one'}, 'repeat_set', {'repeat': 'one'}),
            ({'action': 'repeat', 'repeat_mode': 'all'}, 'repeat_set', {'repeat': 'all'}),
            ({'action': 'repeat', 'repeat_mode': 'off'}, 'repeat_set', {'repeat': 'off'}),
            ({'action': 'volume', 'volume_percent': 25}, 'volume_set', {'volume_level': 0.25}),
            ({'action': 'volume_up'}, 'volume_up', {}),
            ({'action': 'volume_down'}, 'volume_down', {}),
            ({'action': 'mute'}, 'volume_mute', {'is_volume_muted': True}),
            ({'action': 'unmute'}, 'volume_mute', {'is_volume_muted': False}),
            ({'action': 'select_source', 'source': '  bedroom '}, 'select_source', {'source': 'Bedroom'}),
        ]
        for i, (arguments, service, fields) in enumerate(cases):
            with self.subTest(arguments=arguments):
                self.ha.call.reset_mock()
                result = await (await self.media_command(session, data, call=f'media_{i}', **arguments)).json()
                self.assertEqual(result['status'], 'accepted')
                self.assertEqual(result.get('end_voice', False), arguments['action'] in {'play', 'next', 'previous'})
                self.assertEqual(result['observed_state'], 'playing')
                self.assertEqual(result['observed_media']['media_title'], 'A track')
                self.ha.call.assert_awaited_once_with('media_player.' + service, {'entity_id': 'media_player.music', **fields})

    async def test_media_rechecks_capabilities_exposure_and_source_choices(self):
        data = self.media_panel()
        session = await self.session(data)
        self.media_actions = {'media_player.select_source'}
        result = await (await self.media_command(session, data)).json()
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(result['available_actions'], ['select_source'])
        result = await (await self.media_command(session, data, call='bad_source', action='select_source', source='Garage')).json()
        self.assertEqual(result['status'], 'invalid_source')
        self.assertEqual(result['source_list'], ['Kitchen', 'Bedroom'])
        self.exposure.pop('media_player.music')
        result = await (await self.media_command(session, data, call='revoked')).json()
        self.assertEqual(result['status'], 'not_exposed')
        self.ha.call.assert_not_awaited()

    async def test_media_rejects_out_of_range_values_extra_fields_and_wrong_domains(self):
        data = self.media_panel()
        session = await self.session(data)
        invalid = [{'action': 'volume', 'volume_percent': v} for v in (-1, 101, True, '30', None, float('nan'), float('inf'))]
        invalid += [{'action': 'volume'}, {'action': 'play_media', 'source': 'invented'}, {'name': 'Reading light'},
                    {'entity_id': 'media_player.private'}, {'action': 'pause', 'volume_percent': 30},
                    {'action': 'select_source', 'source': ''}, {'action': 'repeat'},
                    {'action': 'repeat', 'repeat_mode': 'track'}, {'action': 'repeat', 'repeat_mode': True},
                    {'action': 'repeat', 'repeat_mode': []}, {'action': 'pause', 'repeat_mode': 'one'},
                    {'action': 'seek', 'position': 60}]
        for i, args in enumerate(invalid):
            result = await (await self.media_command(session, data, call=f'invalid_{i}', **args)).json()
            self.assertEqual(result['status'], 'error', args)
        self.ha.call.assert_not_awaited()

    async def test_repeat_reports_observed_mode_and_rechecks_capability_and_exposure(self):
        data = self.media_panel()
        self.ha.states['media_player.music']['attributes']['repeat'] = 'off'
        session = await self.session(data)
        result = await (await self.media_command(session, data, action='repeat', repeat_mode='one')).json()
        self.assertEqual(result['status'], 'accepted')
        # Service acceptance is not evidence that the new state already arrived.
        self.assertEqual(result['observed_media']['repeat_mode'], 'off')
        self.ha.call.reset_mock()
        self.media_actions.remove('media_player.repeat_set')
        result = await (await self.media_command(session, data, call='lost_capability', action='repeat', repeat_mode='all')).json()
        self.assertEqual(result['status'], 'unsupported')
        self.exposure.pop('media_player.music')
        result = await (await self.media_command(session, data, call='lost_exposure', action='repeat', repeat_mode='off')).json()
        self.assertEqual(result['status'], 'not_exposed')
        self.ha.call.assert_not_awaited()

    async def test_media_skip_is_not_repeated_on_duplicate_delivery_or_timeout(self):
        data = self.media_panel()
        session = await self.session(data)
        requests = await asyncio.gather(*(self.media_command(session, data, action='next') for _ in range(2)))
        first, second = [await response.json() for response in requests]
        self.assertEqual(first, second)
        self.ha.call.assert_awaited_once_with('media_player.media_next_track', {'entity_id': 'media_player.music'})
        self.ha.call.reset_mock()
        self.ha.call.side_effect = TimeoutError
        first = await (await self.media_command(session, data, call='timeout', action='next')).json()
        second = await (await self.media_command(session, data, call='timeout', action='next')).json()
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'error')
        self.ha.call.assert_awaited_once()

    def dimmable_light(self):
        self.ha.services = {'light': {'turn_on': {'fields': {'brightness_pct': {
            'filter': {'attribute': {'supported_color_modes': ['brightness', 'color_temp', 'rgb']}}}}}}}
        self.ha.states['light.a'] = {'state': 'on', 'attributes': {
            'friendly_name': 'Corner lamp', 'supported_color_modes': ['brightness'], 'brightness': 102}}

    async def brightness_command(self, session, level, call='brightness_1', **args):
        return await self.client.post(f'/api/voice-preview/sessions/{session}/tools', json={
            'call_id': call, 'name': 'set_light_brightness',
            'arguments': {'name': 'Reading light', 'area': '', 'brightness_percent': level, **args}, 'context': panel()})

    async def test_light_brightness_percent_uses_ha_field_and_reports_observed_level(self):
        self.dimmable_light()
        context = await assistant_tools.panel_context(self.manager, panel())
        entity = assistant_tools.resolve(context, 'Reading light')['matches'][0]
        self.assertIn('brightness', entity['available_actions'])
        self.assertEqual(entity['light']['brightness_percent'], 40)
        session = await self.session()
        for i, value in enumerate([0, 40, 100]):
            self.ha.call.reset_mock()
            result = await (await self.brightness_command(session, value, call=f'brightness_{i}')).json()
            self.assertEqual(result['status'], 'accepted')
            self.assertEqual(result['observed_light']['brightness_percent'], 40, 'Do not fabricate the requested state')
            self.ha.call.assert_awaited_once_with('light.turn_on', {'entity_id': 'light.a', 'brightness_pct': value})

    async def test_light_brightness_rejects_invalid_levels_and_on_off_only_lights(self):
        self.dimmable_light()
        session = await self.session()
        for i, value in enumerate([-1, 101, True, '40', None, float('nan')]):
            result = await (await self.brightness_command(session, value, call=f'invalid_{i}')).json()
            self.assertEqual(result['status'], 'error')
        self.ha.states['light.a']['attributes']['supported_color_modes'] = ['onoff']
        result = await (await self.brightness_command(session, 40)).json()
        self.assertEqual(result['status'], 'unsupported')
        context = await assistant_tools.panel_context(self.manager, panel())
        self.assertNotIn('brightness', assistant_tools.resolve(context, 'Reading light')['matches'][0]['available_actions'])
        self.ha.call.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
