"""Direct OpenAI audio for external speakers, without a transcription/TTS stage.

Browser PCM goes to Realtime. Its generated PCM goes to the shared reply output.
Tool calls still use the existing authenticated dispatch endpoint and receipts.
"""
import asyncio
import base64
import json
import secrets
import time
from urllib.parse import urlencode

from aiohttp import ClientError, WSMsgType, web

from assistant_tools import INSTRUCTIONS, TOOLS, panel_context
from voice_output import MAX_SECONDS as REPLY_SECONDS, pcm_wav

REALTIME_URL = 'wss://api.openai.com/v1/realtime'
FORWARD = {'session.update', 'input_audio_buffer.clear', 'response.create', 'response.cancel', 'conversation.item.create'}
EVENTS = {'response.created', 'response.done', 'input_audio_buffer.speech_started',
          'input_audio_buffer.speech_stopped', 'response.output_audio_transcript.delta', 'error'}


class OpenAIRelay:
    def __init__(self, owner, key, session):
        self.owner, self.key, self.session = owner, key, session
        self.upstream = self.browser = None
        self.attached = False
        self.audio = bytearray()
        self.response_id = ''
        self.input_enabled = True

    async def connect(self, context, *, listening=True):
        self.upstream = await self.owner.manager.ha.session.ws_connect(
            REALTIME_URL + '?' + urlencode({'model': self.owner.model}),
            headers={'Authorization': 'Bearer ' + self.owner.key}, heartbeat=20, max_msg_size=2*1024*1024)
        await self.upstream.send_json({'type': 'session.update', 'session': {
            'type': 'realtime', 'instructions': INSTRUCTIONS + '\nPANEL_CONTEXT_DATA:\n' + json.dumps(context, ensure_ascii=False),
            'tools': [{'type': 'function', **tool} for tool in TOOLS], 'tool_choice': 'auto', 'max_output_tokens': 1024,
            'audio': {'input': {'format': {'type': 'audio/pcm', 'rate': 24000},
                                'turn_detection': {'type': 'semantic_vad'} if listening else None},
                      'output': {'format': {'type': 'audio/pcm', 'rate': 24000}, 'voice': self.owner.voice}}}})
        async with asyncio.timeout(20):
            while True:
                event = await self.upstream.receive_json()
                if event.get('type') == 'error':
                    raise ValueError('OpenAI refused the audio session. Check the API key and model access.')
                if event.get('type') == 'session.updated':
                    self.input_enabled = listening
                    return

    async def upstream_events(self):
        async for message in self.upstream:
            if message.type != WSMsgType.TEXT:
                break
            event = message.json()
            kind = event.get('type')
            if kind == 'response.created':
                self.audio.clear()
                self.response_id = event.get('response', {}).get('id', '')
                self.input_enabled = False
                await self.upstream.send_json({'type': 'session.update', 'session': {
                    'type': 'realtime', 'audio': {'input': {'turn_detection': None}}}})
                await self.upstream.send_json({'type': 'input_audio_buffer.clear'})
            elif kind == 'response.output_audio.delta':
                if event.get('response_id') != self.response_id:
                    raise ValueError('Unexpected reply audio.')
                self.audio.extend(base64.b64decode(event.get('delta', ''), validate=True))
                if len(self.audio) > 24000 * 2 * REPLY_SECONDS:
                    raise ValueError('The spoken reply is too long.')
            elif kind == 'response.done':
                response = event.get('response', {})
                calls = any(item.get('type') == 'function_call' for item in response.get('output', []))
                if response.get('status') == 'completed' and not calls and self.audio:
                    # Music confirmations stay local; general replies use the
                    # configured external speaker, independently of media tiles.
                    speaker = '' if self.session.get('end_voice') else self.session['reply_speaker']
                    reply = self.owner.output.prepare(self.key, pcm_wav(self.audio), 'audio/wav', speaker,
                                                      self.session['reply_volume'])
                    await self.browser.send_json({'type': 'reply.ready', 'response_id': self.response_id, 'reply': reply})
                self.audio.clear()
            if kind in EVENTS:
                await self.browser.send_json(event)
            if kind == 'error':
                break

    async def browser_events(self):
        async for message in self.browser:
            if message.type == WSMsgType.BINARY:
                if len(message.data) > 16384 or len(message.data) % 2:
                    raise ValueError('Invalid microphone audio.')
                if self.input_enabled and message.data:
                    await self.upstream.send_json({'type': 'input_audio_buffer.append',
                                                  'audio': base64.b64encode(message.data).decode('ascii')})
            elif message.type == WSMsgType.TEXT:
                event = message.json()
                if not isinstance(event, dict) or event.get('type') not in FORWARD:
                    raise ValueError('Unsupported audio event.')
                if event['type'] == 'session.update':
                    session = event.get('session', {})
                    if set(session) - {'type', 'instructions', 'audio'}:
                        raise ValueError('Unsupported audio settings.')
                    if 'audio' in session:
                        audio = session['audio']
                        if audio not in ({'input': {'turn_detection': None}}, {'input': {'turn_detection': {'type': 'semantic_vad'}}}):
                            raise ValueError('Unsupported microphone settings.')
                        self.input_enabled = audio['input']['turn_detection'] is not None
                await self.upstream.send_json(event)

    async def serve(self, request):
        if self.attached:
            raise ValueError('This voice connection is already open.')
        self.attached = True
        self.browser = web.WebSocketResponse(heartbeat=20, max_msg_size=65536)
        await self.browser.prepare(request)
        tasks = [asyncio.create_task(self.upstream_events()), asyncio.create_task(self.browser_events())]
        try:
            await self.browser.send_json({'type': 'relay.ready'})
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ValueError, ConnectionError, ClientError, TimeoutError):
            if not self.browser.closed:
                await self.browser.send_json({'type': 'error'})
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.owner.close(self.key)
        return self.browser

    async def close(self):
        self.audio.clear()
        if self.upstream:
            await self.upstream.close()
        if self.browser:
            await self.browser.close()


def register(app, owner, max_seconds, max_calls):
    async def start(request):
        owner.require_enabled()
        if owner.provider != 'openai' or not owner.reply_speaker:
            raise ValueError('Voice settings changed. Reopen the preview.')
        if not owner.key:
            raise ValueError('Set the OpenAI API key in Voice assistant settings.')
        owner.output.validate(owner.reply_speaker, available=True)
        data = await request.json()
        context = await panel_context(owner.manager, data.get('context'), music=owner.music)
        if len(owner.sessions) >= max_calls:
            raise ValueError('Close an existing voice session before starting another.')
        key = secrets.token_urlsafe(24)
        session = {'provider': 'openai', 'receipts': {}, 'lock': asyncio.Lock(),
                   'expires': time.monotonic() + max_seconds, 'reply_speaker': owner.reply_speaker,
                   'reply_volume': owner.reply_volume}
        relay = session['relay'] = OpenAIRelay(owner, key, session)
        owner.sessions[key] = session
        try:
            async with asyncio.timeout(30):
                await relay.connect(context)
            session['timer'] = asyncio.get_running_loop().call_later(max_seconds, lambda: asyncio.create_task(owner.close(key)))
            return web.json_response({'id': key, 'max_seconds': max_seconds})
        except (ClientError, ConnectionError, TimeoutError) as error:
            await owner.close(key)
            raise ValueError('OpenAI audio could not connect. Check the connection and API access.') from error
        except BaseException:
            await owner.close(key)
            raise

    async def stream(request):
        _, session = owner.live_session(request)
        if not session.get('relay'):
            raise web.HTTPNotFound()
        return await session['relay'].serve(request)

    app.router.add_post('/api/voice-preview/openai/sessions', start)
    app.router.add_get('/api/voice-preview/sessions/{session}/stream', stream)
