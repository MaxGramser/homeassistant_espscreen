"""Opt-in browser voice experiment. Audio uses WebRTC; HA credentials stay here.

This is a host transport, not a tile renderer or a physical microphone driver.
Only Assist-exposed entities enter the context. Tool execution resolves names
again on the server and never accepts an arbitrary service or entity ID.
"""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

from aiohttp import web

from assistant_tools import prompt, TOOLS, execute, panel_context
from voice_providers import AUDIO_PROVIDERS, LOOKUP_PROVIDERS, TEXT_PROVIDERS
from voice_ha_speech import pipelines
from voice_claude import ClaudeSessions
import voice_lookup
import voice_music
import voice_openai_relay
from voice_output import ReplyOutput

MAX_SECONDS = 600
MAX_CALLS = 4
LOG = logging.getLogger(__name__)


def voice_enabled(data):
    """Supervisor's saved option wins; a missing or invalid option stays off."""
    try:
        options = json.loads((data / 'options.json').read_text())
    except FileNotFoundError:
        if os.environ.get('SUPERVISOR_TOKEN') and os.environ.get('SCREEN_DEV') != '1':
            return False
        # Standalone Docker and older development setups have no Supervisor.
        return os.environ.get('SCREEN_VOICE_ENABLED', os.environ.get('SCREEN_VOICE_POC', '0')) == '1'
    except (OSError, ValueError):
        return False
    return isinstance(options, dict) and options.get('voice_assistant') is True


def write_private(path, value):
    """Replace one manager-owned setting without leaving a partially written file."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.voice-key-', delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(value + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            with contextlib.suppress(OSError): temporary.unlink(missing_ok=True)


class VoicePreview:
    def __init__(self, manager, *, audio_provider=None, lookup_provider=None):
        self.manager = manager
        self.audio = audio_provider or AUDIO_PROVIDERS['openai']
        self.lookup = lookup_provider or LOOKUP_PROVIDERS['openai']
        data = Path(getattr(manager, 'path', '/data/screens.json')).parent
        self.enabled = voice_enabled(data)
        self.key = os.environ.get('OPENAI_API_KEY', '') if self.enabled else ''
        if self.enabled and not self.key and os.environ.get('OPENAI_API_KEY_FILE'):
            with contextlib.suppress(OSError):
                self.key = Path(os.environ['OPENAI_API_KEY_FILE']).read_text().strip()
        self.server_key = self.key
        self.key_path = data / 'voice-api-key'
        self.saved_key = ''
        if self.enabled:
            with contextlib.suppress(OSError):
                self.saved_key = self.key_path.read_text().strip()
        self.key = self.saved_key or self.server_key
        self.voice_path = self.key_path.with_name('voice-settings.json')
        self.voice = self.audio.voices[0]
        self.provider, self.pipeline = 'openai', ''
        self.idle_seconds = 5
        self.reply_speaker, self.reply_volume = '', 30
        self.output = ReplyOutput(manager.ha)
        manager.voice_output = self.output
        self.speech_pipelines = []
        if self.enabled:
            with contextlib.suppress(OSError, ValueError):
                settings = json.loads(self.voice_path.read_text())
                if isinstance(settings, dict):
                    if settings.get('voice') in self.audio.voices:
                        self.voice = settings['voice']
                    if settings.get('provider') in {'openai', 'claude'}:
                        self.provider = settings['provider']
                    if isinstance(settings.get('pipeline'), str):
                        self.pipeline = settings['pipeline']
                    idle = settings.get('idle_seconds')
                    # Older previews allowed 0 to disable this timer. Treat it
                    # as the default, so every new session has a silence limit.
                    if type(idle) is int and 1 <= idle <= 300:
                        self.idle_seconds = idle
                    if isinstance(settings.get('reply_speaker'), str):
                        self.reply_speaker = settings['reply_speaker']
                    if type(settings.get('reply_volume')) is int and 1 <= settings['reply_volume'] <= 100:
                        self.reply_volume = settings['reply_volume']
        self.claude_key_path = self.key_path.with_name('voice-claude-api-key')
        self.claude_saved_key = self.claude_server_key = ''
        if self.enabled:
            self.claude_server_key = os.environ.get('ANTHROPIC_API_KEY', '')
            if not self.claude_server_key and os.environ.get('ANTHROPIC_API_KEY_FILE'):
                with contextlib.suppress(OSError):
                    self.claude_server_key = Path(os.environ['ANTHROPIC_API_KEY_FILE']).read_text().strip()
            with contextlib.suppress(OSError):
                self.claude_saved_key = self.claude_key_path.read_text().strip()
        self.claude_key = self.claude_saved_key or self.claude_server_key
        self.claude_model = os.environ.get('ANTHROPIC_MODEL', TEXT_PROVIDERS['claude'].default_model)
        self.model = os.environ.get('OPENAI_REALTIME_MODEL', self.audio.default_model)
        self.search_model = os.environ.get('OPENAI_WEB_SEARCH_MODEL', self.lookup.default_model)
        self.music_path = self.key_path.with_name('voice-spotify.json')
        self.music = voice_music.SpotifyCatalogue()
        if self.enabled:
            with contextlib.suppress(OSError, ValueError):
                self.music = voice_music.SpotifyCatalogue(json.loads(self.music_path.read_text()))
        self.sessions = {}

    def require_enabled(self):
        if not self.enabled:
            raise web.HTTPNotFound()

    async def status(self, request):
        if self.enabled:
            await self.load_pipelines()
        return web.json_response(self.configuration())

    async def load_pipelines(self):
        try:
            self.speech_pipelines = await pipelines(self.manager.ha)
        except (ValueError, ConnectionError, TimeoutError):
            self.speech_pipelines = []

    def save_settings(self, **changes):
        settings = {'voice': self.voice, 'provider': self.provider, 'pipeline': self.pipeline,
                    'idle_seconds': self.idle_seconds, 'reply_speaker': self.reply_speaker,
                    'reply_volume': self.reply_volume, **changes}
        try:
            write_private(self.voice_path, json.dumps(settings))
        except OSError:
            raise ValueError('Voice settings could not be saved in Screen Manager data.') from None
        for name, value in settings.items():
            setattr(self, name, value)

    def configuration(self):
        # No part of the secret, including a masked prefix/suffix, is returned.
        result = {'enabled': self.enabled, 'configured': bool(self.key), 'saved_key': bool(self.saved_key),
                'source': 'editor' if self.saved_key else 'server' if self.server_key else '',
                'audio_provider': self.audio.id, 'lookup_provider': self.lookup.id,
                'model': self.model, 'voice': self.voice, 'voices': self.audio.voices, 'max_seconds': MAX_SECONDS,
                'idle_seconds': self.idle_seconds, 'spotify': self.music.status(),
                'reply_speaker': self.reply_speaker, 'reply_volume': self.reply_volume,
                'reply_speakers': self.output.speakers()}
        result.update(provider=self.provider, pipeline=self.pipeline, pipelines=self.speech_pipelines,
            providers={'openai': {'configured': bool(self.key), 'model': self.model},
                       'claude': {'configured': bool(self.claude_key), 'model': self.claude_model}})
        if self.provider == 'claude':
            ready = any(p['id'] == self.pipeline and p['ready'] for p in self.speech_pipelines)
            result.update(configured=bool(self.claude_key) and ready, saved_key=bool(self.claude_saved_key),
                source='editor' if self.claude_saved_key else 'server' if self.claude_server_key else '',
                audio_provider='ha', lookup_provider='claude', model=self.claude_model, voices=(),
                key_configured=bool(self.claude_key), speech_ready=ready)
        else:
            result.update(key_configured=bool(self.key), speech_ready=True)
        return result

    async def configure_music(self, request):
        self.require_enabled()
        if self.sessions:
            raise ValueError('Stop active voice sessions before changing Spotify search settings.')
        data = voice_music.credentials(await request.json()) if request.method == 'PUT' else None
        try:
            if data:
                write_private(self.music_path, json.dumps(data))
            else:
                self.music_path.unlink(missing_ok=True)
        except OSError:
            raise ValueError('Spotify settings could not be saved in Screen Manager data.') from None
        self.music = voice_music.SpotifyCatalogue(data)
        return web.json_response(self.configuration())

    async def configure(self, request):
        self.require_enabled()
        data = await request.json() if request.method == 'PUT' else {}
        if request.method == 'PUT' and isinstance(data, dict) and set(data) == {'reply_speaker', 'reply_volume'}:
            if self.sessions:
                raise ValueError('Stop active voice sessions before changing the reply speaker.')
            self.output.validate(data['reply_speaker'])
            if type(data['reply_volume']) is not int or not 1 <= data['reply_volume'] <= 100:
                raise ValueError('Choose a reply volume from 1 to 100 percent.')
            self.save_settings(**data)
            return web.json_response(self.configuration())
        if request.method == 'PUT' and isinstance(data, dict) and set(data) == {'idle_seconds'}:
            if type(data['idle_seconds']) is not int or not 1 <= data['idle_seconds'] <= 300:
                raise ValueError('Choose a whole number of seconds from 1 to 300.')
            self.save_settings(idle_seconds=data['idle_seconds'])
            return web.json_response(self.configuration())
        if request.method == 'PUT' and isinstance(data, dict) and set(data) == {'voice'}:
            if data['voice'] not in self.audio.voices:
                raise ValueError('Choose one of the available voices.')
            self.save_settings(voice=data['voice'])
            # Active calls retain their voice. OpenAI locks it after audio starts.
            self.voice = data['voice']
            return web.json_response(self.configuration())
        if self.sessions:
            raise ValueError('Stop active voice sessions before changing the API key.')
        if request.method == 'PUT' and isinstance(data, dict) and set(data) == {'provider'}:
            if data['provider'] not in {'openai', 'claude'}:
                raise ValueError('Choose OpenAI or Claude.')
            self.save_settings(provider=data['provider'])
            await self.load_pipelines()
            return web.json_response(self.configuration())
        if request.method == 'PUT' and isinstance(data, dict) and set(data) == {'pipeline'}:
            await self.load_pipelines()
            if not any(p['id'] == data['pipeline'] and p['ready'] for p in self.speech_pipelines):
                raise ValueError('Choose a Home Assistant voice assistant with both speech-to-text and text-to-speech.')
            self.save_settings(pipeline=data['pipeline'])
            return web.json_response(self.configuration())
        provider = request.match_info.get('provider', 'openai')
        if provider not in {'openai', 'claude'}:
            raise ValueError('Unknown voice provider.')
        path = self.key_path if provider == 'openai' else self.claude_key_path
        try:
            if request.method == 'PUT':
                if not isinstance(data, dict) or set(data) != {'api_key'} or not isinstance(data['api_key'], str):
                    raise ValueError('An API key is required.')
                key = data['api_key'].strip()
                if not 20 <= len(key) <= 1024 or not key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in key):
                    raise ValueError('Enter a complete API key without spaces or control characters.')
                write_private(path, key)
            else:
                path.unlink(missing_ok=True)
                key = ''
        except OSError:
            raise ValueError('The API key could not be saved in Screen Manager data.') from None
        if provider == 'openai':
            self.saved_key = key
            self.key = key or self.server_key
        else:
            self.claude_saved_key = key
            self.claude_key = key or self.claude_server_key
        return web.json_response(self.configuration())

    async def context(self, request):
        self.require_enabled()
        context = await panel_context(self.manager, await request.json(), music=self.music)
        return web.json_response({'context': context,
            'instructions': prompt(context)})

    async def start(self, request):
        self.require_enabled()
        if self.provider != 'openai':
            raise ValueError('The voice provider changed. Reopen the preview.')
        if self.reply_speaker:
            raise ValueError('The reply speaker changed. Reopen the preview.')
        if not self.key:
            raise ValueError('Set the OpenAI API key in editor Settings, under OpenAI voice.')
        if len(self.sessions) >= MAX_CALLS:
            raise ValueError('Close an existing voice session before starting another.')
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('A voice session request is required.')
        context = await panel_context(self.manager, data.get('context'), music=self.music)
        sdp = data.get('sdp')
        if not isinstance(sdp, str) or not sdp.startswith('v=0') or len(sdp) > 64000:
            raise ValueError('Invalid audio connection offer.')
        if len(self.sessions) >= MAX_CALLS:
            raise ValueError('Close an existing voice session before starting another.')
        session_id = secrets.token_urlsafe(24)
        session = {'provider': 'openai', 'audio': self.audio.session(self.manager.ha.session, self.key), 'receipts': {}, 'lock': asyncio.Lock(), 'expires': time.monotonic() + MAX_SECONDS}
        self.sessions[session_id] = session
        try:
            answer = await session['audio'].connect(sdp, model=self.model, voice=self.voice,
                instructions=prompt(context), tools=TOOLS)
            session['timer'] = asyncio.get_running_loop().call_later(MAX_SECONDS, lambda: asyncio.create_task(self.close(session_id)))
            return web.json_response({'id': session_id, 'sdp': answer, 'context': context, 'max_seconds': MAX_SECONDS})
        except BaseException:
            await self.close(session_id)
            raise

    async def tools(self, request):
        self.require_enabled()
        session = self.sessions.get(request.match_info['session'])
        if not session or session.get('provider') != 'openai' or session['expires'] <= time.monotonic():
            raise ValueError('Voice session ended. Start a new conversation.')
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('A voice tool request is required.')
        async with session['lock']:
            result = await self.dispatch(request.match_info['session'], data.get('call_id'), data.get('name'),
                                         data.get('arguments'), data.get('context'))
        return web.json_response(result)

    async def dispatch(self, session_id, call_id, name, args, panel):
        session = self.sessions.get(session_id)
        if not session or session['expires'] <= time.monotonic():
            raise ValueError('Voice session ended.')
        if not isinstance(call_id, str) or not re.fullmatch(r'[\w-]{1,160}', call_id) or not isinstance(args, dict):
            raise ValueError('Invalid voice tool call.')
        signature = json.dumps([name, args], sort_keys=True)
        previous = session['receipts'].get(call_id)
        if previous:
            if previous[0] != signature:
                raise ValueError('A voice tool call ID cannot be reused for another action.')
            return previous[1]
        if session.get('end_voice_immediately'):
            raise ValueError('Voice session ended.')
        if len(session['receipts']) >= 256:
            raise ValueError('Start a new voice conversation.')
        try:
            if name == 'wait_for_user':
                if args:
                    raise ValueError('Waiting takes no arguments.')
                result = {'status': 'ok', 'wait_for_user': True}
            elif name == 'end_conversation':
                if args:
                    raise ValueError('Ending the conversation takes no arguments.')
                result = {'status': 'ok', 'end_voice': True, 'end_voice_immediately': True}
            elif name == 'lookup_current_information':
                provider, key, model = ((self.lookup, self.key, self.search_model) if session['provider'] == 'openai'
                    else (LOOKUP_PROVIDERS['claude'], self.claude_key, self.claude_model))
                task = asyncio.create_task(provider.lookup(self.manager.ha.session, key, args, model=model))
                session['lookup'] = task
                started = time.monotonic()
                try:
                    result = await task
                except asyncio.CancelledError:
                    if session_id in self.sessions or session['provider'] == 'claude':
                        raise
                    result = {'status': 'cancelled', 'sources': []}
                finally:
                    session.pop('lookup', None)
                    # Measure the external lookup without logging questions,
                    # retrieved answers, session IDs or provider credentials.
                    LOG.info('Voice current-information lookup provider=%s elapsed=%.2fs',
                             session['provider'], time.monotonic()-started)
            else:
                async def refresh_context():
                    return await panel_context(self.manager, panel, private=True, music=self.music)
                context = await refresh_context()
                # Stop may have been pressed while HA exposure was being read.
                if session_id not in self.sessions:
                    raise asyncio.CancelledError()
                task = asyncio.create_task(execute(self.manager, name, args, context, music=self.music,
                    music_results=session.setdefault('music_results', {}), refresh_context=refresh_context))
                session['action_task'] = task
                try:
                    result = await task
                finally:
                    session.pop('action_task', None)
        except (ValueError, ConnectionError, TimeoutError):
            result = dict(voice_lookup.UNAVAILABLE) if name == 'lookup_current_information' else {
                'status': 'error', 'message': 'Action not confirmed. Check the target and HA connection before trying again.'}
        session['receipts'][call_id] = (signature, result)
        if result.get('end_voice'):
            session['end_voice'] = True
        if result.get('end_voice_immediately'):
            session['end_voice_immediately'] = True
        return result

    def live_session(self, request):
        self.require_enabled()
        key = request.match_info['session']
        session = self.sessions.get(key)
        if not session or session['expires'] <= time.monotonic():
            raise ValueError('Voice session ended. Start a new conversation.')
        return key, session

    async def reply(self, request):
        key, _ = self.live_session(request)
        reply = self.output.get(key, request.match_info['reply'])
        if request.method == 'POST':
            return web.json_response(await self.output.play(reply))
        return web.json_response(reply.view())

    async def reply_audio(self, request):
        key, _ = self.live_session(request)
        reply = self.output.get(key, request.match_info['reply'])
        if reply.speaker or not reply.data:
            raise web.HTTPNotFound()
        return web.Response(body=reply.data, content_type=reply.mime)

    async def close(self, session_id):
        session = self.sessions.pop(session_id, None)
        if not session:
            return
        if session.get('timer'):
            session['timer'].cancel()
        if task := session.get('turn_task'):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if task := session.get('lookup'):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if task := session.get('action_task'):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if session.get('audio'):
            await session['audio'].close()
        if session.get('relay'):
            await session['relay'].close()
        await self.output.close(session_id)

    async def stop(self, request):
        self.require_enabled()
        await self.close(request.match_info['session'])
        return web.json_response({'stopped': True})

    async def cleanup(self, app):
        await asyncio.gather(*(self.close(key) for key in list(self.sessions)))
        await self.output.shutdown()


def register(app, manager):
    voice = VoicePreview(manager)
    from voice_device import DeviceVoice
    manager.device_voice = DeviceVoice(voice, write_private)
    manager.device_voice.register(app)
    app.router.add_get('/api/voice-preview/status', voice.status)
    app.router.add_put('/api/voice-preview/spotify', voice.configure_music)
    app.router.add_delete('/api/voice-preview/spotify', voice.configure_music)
    app.router.add_put('/api/voice-preview/config', voice.configure)
    app.router.add_delete('/api/voice-preview/config', voice.configure)
    app.router.add_put('/api/voice-preview/config/{provider}', voice.configure)
    app.router.add_delete('/api/voice-preview/config/{provider}', voice.configure)
    ClaudeSessions(voice, MAX_SECONDS, MAX_CALLS).register(app)
    voice_openai_relay.register(app, voice, MAX_SECONDS, MAX_CALLS)
    app.router.add_post('/api/voice-preview/context', voice.context)
    app.router.add_post('/api/voice-preview/sessions', voice.start)
    app.router.add_post('/api/voice-preview/sessions/{session}/tools', voice.tools)
    app.router.add_delete('/api/voice-preview/sessions/{session}', voice.stop)
    reply = '/api/voice-preview/sessions/{session}/replies/{reply}'
    app.router.add_get(reply, voice.reply)
    app.router.add_post(reply, voice.reply)
    app.router.add_get(reply + '/audio', voice.reply_audio)
    app.on_cleanup.append(voice.cleanup)
