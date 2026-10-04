"""Turn-based browser transport around HA speech and the shared conversation."""
import asyncio
import hashlib
import logging
import secrets
import time

from aiohttp import web

from assistant_conversation import Conversation
from assistant_tools import panel_context
from voice_ha_speech import HASpeech, MAX_PCM
from voice_providers import TEXT_PROVIDERS

LOG = logging.getLogger(__name__)
TURN_SECONDS = 120


class ClaudeSessions:
    def __init__(self, owner, max_seconds, max_calls):
        self.owner, self.max_seconds, self.max_calls = owner, max_seconds, max_calls

    def session(self, request):
        self.owner.require_enabled()
        session = self.owner.sessions.get(request.match_info['session'])
        if not session or session.get('provider') != 'claude' or session['expires'] <= time.monotonic():
            raise ValueError('Voice session ended. Start a new conversation.')
        return session

    async def start(self, request):
        owner = self.owner
        owner.require_enabled()
        if owner.provider != 'claude':
            raise ValueError('The voice provider changed. Reopen the preview.')
        if not owner.claude_key:
            raise ValueError('Set the Claude API key in editor Settings, under Voice assistant.')
        await owner.load_pipelines()
        if not owner.configuration()['speech_ready']:
            raise ValueError('Select a Home Assistant voice assistant with speech-to-text and text-to-speech in Settings.')
        owner.output.validate(owner.reply_speaker, available=True)
        data = await request.json()
        await panel_context(owner.manager, data.get('context'))
        if len(owner.sessions) >= self.max_calls:
            raise ValueError('Close an existing voice session before starting another.')
        key = secrets.token_urlsafe(24)
        session = {'provider': 'claude', 'panel': data['context'], 'receipts': {}, 'turns': {},
            'lock': asyncio.Lock(), 'expires': time.monotonic() + self.max_seconds,
            'reply_speaker': owner.reply_speaker, 'reply_volume': owner.reply_volume,
            'speech': HASpeech(owner.manager.ha, owner.pipeline),
            'conversation': Conversation(TEXT_PROVIDERS['claude'], owner.manager.ha.session, owner.claude_key, owner.claude_model)}
        owner.sessions[key] = session
        session['timer'] = asyncio.get_running_loop().call_later(self.max_seconds, lambda: asyncio.create_task(owner.close(key)))
        return web.json_response({'id': key, 'max_seconds': self.max_seconds})

    async def context(self, request):
        session = self.session(request)
        data = await request.json()
        await panel_context(self.owner.manager, data)
        self.session(request)
        session['panel'] = data
        return web.json_response({'updated': True})

    async def run_turn(self, key, session, pcm):
        speech = session['speech']
        self.phase(session, 'transcribing')
        text = await speech.transcribe(pcm)
        if not text:
            return {'text': '', 'sources': [], 'action': False}
        context = await panel_context(self.owner.manager, session['panel'], music=self.owner.music)
        self.phase(session, 'thinking')
        async def dispatch(call_id, name, arguments):
            if name in {'lookup_current_information', 'search_music'}:
                self.phase(session, 'searching')
            result = await self.owner.dispatch(key, call_id, name, arguments, session['panel'])
            if key in self.owner.sessions:
                self.phase(session, 'thinking')
            return result
        result = await session['conversation'].reply(text, context, dispatch)
        result['heard'] = text
        if result.get('wait_for_user'):
            return result
        self.phase(session, 'preparing_speech')
        try:
            audio, mime = await speech.synthesize(result['text'])
            session['reply_audio'] = (audio, mime)
            result['audio'] = True
            if session['reply_speaker'] and not result.get('end_voice'):
                result['reply'] = self.owner.output.prepare(key, audio, mime, session['reply_speaker'], session['reply_volume'])
                session.pop('reply_audio', None)
        except (ValueError, ConnectionError, TimeoutError):
            # The command may already have succeeded. Keep the text, do not
            # replay the turn just because the speaker failed.
            result['audio_error'] = 'The spoken reply is unavailable. Open Text and sources to read the reply.'
            result.pop('audio', None)
            if session['reply_speaker']:
                result['end_voice'] = True
        return result

    @staticmethod
    def phase(session, phase):
        now = time.monotonic()
        previous = session.get('progress')
        if previous:
            # Timings only. No transcripts, audio, keys or session identifiers.
            LOG.info('Claude voice %s: %.1fs', previous['phase'], now - previous['since'])
        session['progress'] = {'phase': phase, 'since': now}

    async def progress(self, request):
        session = self.session(request)
        if request.match_info['turn'] != session.get('current_turn'):
            return web.json_response({'phase': 'uploading'})
        progress = session.get('progress', {})
        return web.json_response({'phase': progress.get('phase', 'uploading')})

    async def turn(self, request):
        session = self.session(request)
        if session['lock'].locked():
            raise ValueError('A voice turn is already being processed.')
        turn_id = request.match_info['turn']
        if not turn_id.isascii() or not turn_id.isdecimal() or len(turn_id) > 8:
            raise ValueError('Invalid voice turn number.')
        if request.content_type != 'application/octet-stream':
            raise ValueError('Raw PCM audio is required.')
        async with session['lock']:
            session['current_turn'] = turn_id
            self.phase(session, 'uploading')
            pcm = bytearray()
            async with asyncio.timeout(15):
                async for chunk in request.content.iter_chunked(16384):
                    pcm.extend(chunk)
                    if len(pcm) > MAX_PCM:
                        raise ValueError('Speak for at most 30 seconds per turn.')
            self.session(request)
            digest = hashlib.sha256(pcm).hexdigest()
            previous = session['turns'].get(turn_id)
            if previous:
                if previous[0] != digest:
                    raise ValueError('A turn number cannot be reused for different audio.')
                self.phase(session, 'complete')
                return web.json_response(previous[1])
            if len(session['turns']) >= 60:
                raise ValueError('Start a new voice conversation.')
            session.pop('reply_audio', None)
            task = asyncio.create_task(self.run_turn(request.match_info['session'], session, bytes(pcm)))
            session['turn_task'] = task
            try:
                async with asyncio.timeout(TURN_SECONDS):
                    result = await task
            except asyncio.CancelledError:
                if request.match_info['session'] in self.owner.sessions:
                    raise
                return web.json_response({'error': 'Voice session ended.'}, status=410)
            except (ValueError, ConnectionError, TimeoutError):
                stage = session.get('progress', {}).get('phase')
                messages = {
                    'transcribing': 'Home Assistant could not finish speech recognition. Check the STT service and microphone, then try again.',
                    'searching': 'The current-information search did not finish. Try again later.',
                    'preparing_speech': 'Home Assistant could not finish the spoken reply. Check the TTS service.',
                }
                result = {'error': messages.get(stage, 'Claude could not finish its reply. Check API access and device state before trying again.')}
            finally:
                session.pop('turn_task', None)
                self.phase(session, 'complete')
            # Cache failures too: a repeated upload must never repeat an action.
            session['turns'][turn_id] = (digest, result)
            session['audio_turn'] = turn_id
            return web.json_response(result)

    async def audio(self, request):
        session = self.session(request)
        if request.match_info['turn'] != session.get('audio_turn') or not session.get('reply_audio'):
            raise web.HTTPNotFound()
        data, mime = session['reply_audio']
        return web.Response(body=data, content_type=mime)

    def register(self, app):
        app.router.add_post('/api/voice-preview/claude/sessions', self.start)
        root = '/api/voice-preview/claude/sessions/{session}'
        app.router.add_put(root + '/context', self.context)
        app.router.add_post(root + '/turns/{turn}', self.turn)
        app.router.add_get(root + '/turns/{turn}/status', self.progress)
        app.router.add_get(root + '/turns/{turn}/audio', self.audio)
