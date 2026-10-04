"""Authenticated physical-panel transport over the existing LAN media port.

The panel supplies PCM and its displayed revision/page. Credentials, current
layout, provider orchestration and HA permission checks stay in the manager.
"""
import asyncio
import contextlib
import hashlib
import json
import logging
import math
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientError, WSMsgType, web

from assistant_conversation import Conversation
from assistant_tools import INSTRUCTIONS, panel_context
import camera_feed
import page_delivery
from voice_claude import ClaudeSessions
from voice_ha_speech import HASpeech
from voice_openai_relay import OpenAIRelay
from voice_pcm import Resampler, Utterance, decode_reply
from voice_providers import TEXT_PROVIDERS

MAX_SECONDS = 600
MAX_CALLS = 4
WARM_SECONDS = 50 * 60
LOG = logging.getLogger(__name__)


class DeviceVoice:
    def __init__(self, owner, write_private):
        self.owner, self.manager, self.write_private = owner, owner.manager, write_private
        self.path = Path(self.manager.path).parent / 'voice-devices.json'
        self.devices, self.active = {}, {}
        self.sequence = 0
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(self.path.read_text())
            if isinstance(data, dict) and data.get('version') == 1:
                self.devices = data['devices']

    def screen(self, inbox):
        screen = self.manager.screen(inbox)
        if not screen or not screen.get('device_id') or self.manager.feedback_board(screen) != 'wavesharep4':
            raise ValueError('Choose a supported physical voice panel.')
        return screen

    async def status(self, request):
        self.owner.require_enabled()
        base = await camera_feed.base_url(self.manager.ha.request)
        url = (base.replace('https://', 'wss://').replace('http://', 'ws://') if base else '')
        return web.json_response({'url': url, 'screens': [
            {'id': screen['id'], 'name': screen['name'],
             'paired': any(pair['device'] == screen.get('device_id') for pair in self.devices.values())}
            for screen in self.manager.screens() if screen.get('device_id') and self.manager.feedback_board(screen) == 'wavesharep4']})

    async def pair(self, request):
        self.owner.require_enabled()
        screen = self.screen(request.match_info['inbox'])
        body = await request.json()
        url = body.get('url', '').rstrip('/')
        parsed = urlsplit(url)
        if parsed.scheme not in ('ws', 'wss') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Enter the panel-reachable ws:// or wss:// address of the media port.')
        await self.revoke_device(screen['device_id'])
        device, token = secrets.token_hex(8), secrets.token_urlsafe(32)
        self.devices[device] = {'inbox': screen['id'], 'device': screen['device_id'],
                                'hash': hashlib.sha256(token.encode()).hexdigest()}
        self.save()
        # Returned once through authenticated ingress. Never in status or logs.
        return web.json_response({'device': device, 'token': token, 'url': url + '/voice-devices/' + device})

    def save(self):
        self.write_private(self.path, json.dumps({'version': 1, 'devices': self.devices}))

    async def revoke_device(self, device):
        for key, pair in list(self.devices.items()):
            if pair['device'] == device:
                if key in self.active:
                    await self.active[key].ws.close()
                self.devices.pop(key)

    async def revoke(self, request):
        self.owner.require_enabled()
        screen = self.screen(request.match_info['inbox'])
        await self.revoke_device(screen['device_id'])
        self.save()
        return web.json_response({'removed': True})

    async def stream(self, request):
        self.owner.require_enabled()
        device = request.match_info['device']
        pair = self.devices.get(device)
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if request.headers.get('Origin') or not pair or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token) or not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), pair['hash']):
            raise web.HTTPUnauthorized()
        screen = self.screen(pair['inbox'])
        if screen.get('device_id') != pair['device']:
            raise web.HTTPUnauthorized()
        if device in self.active or len(self.active) >= MAX_CALLS or len(self.owner.sessions) >= MAX_CALLS:
            raise web.HTTPConflict(text='Voice session already active or capacity reached.')
        session = DeviceSession(self, device, pair)
        self.active[device] = session
        try:
            return await session.serve(request)
        finally:
            self.active.pop(device, None)

    def register(self, editor, media=None):
        if editor is not None:
            editor.router.add_get('/api/voice-devices', self.status)
            editor.router.add_post('/api/voice-devices/{inbox}/pair', self.pair)
            editor.router.add_delete('/api/voice-devices/{inbox}', self.revoke)
            editor.on_cleanup.append(self.cleanup)
        if media is not None:
            media.router.add_get(r'/voice-devices/{device:[a-f0-9]{16}}', self.stream)

    async def cleanup(self, app):
        await asyncio.gather(*(session.ws.close() for session in list(self.active.values())))


class DeviceSession:
    def __init__(self, service, device, pair):
        self.service, self.owner, self.pair = service, service.owner, pair
        service.sequence += 1
        self.sequence = service.sequence
        self.key = secrets.token_urlsafe(24)
        self.ws = web.WebSocketResponse(heartbeat=5, timeout=2, max_msg_size=8192)
        self.page, self.revision = 0, ''
        self.phase = 'connecting'
        self.started = self.activity = self.last_audio = time.monotonic()
        self.utterance = Utterance()
        self.ready, self.done, self.credited = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.credit = self.sent = 0
        self.relay = None
        self.worker = None
        self.tasks = []
        self.reply_played = False
        self.turn_deadline = None
        self.finish_sent = False
        self.activation = asyncio.Event()
        self.warming = False
        self.configuration = self.settings()
        self.end_reason = 'peer_closed'
        self.audio_bytes = 0
        self.data = {'provider': self.owner.provider, 'receipts': {}, 'lock': asyncio.Lock(),
                     'expires': self.started + MAX_SECONDS, 'reply_speaker': self.owner.reply_speaker,
                     'reply_volume': self.owner.reply_volume}

    def settings(self):
        # A prepared connection must not retain replaced credentials or settings.
        return (self.owner.provider, self.owner.key, self.owner.claude_key, self.owner.model,
                self.owner.claude_model, self.owner.voice, self.owner.pipeline,
                self.owner.reply_speaker, self.owner.reply_volume)

    def panel(self):
        manager = self.owner.manager
        screen = manager.screen(self.pair['inbox'])
        record = manager.store.get(self.pair['inbox'])
        if not screen or screen.get('device_id') != self.pair['device'] or not record or record.get('format') != 'pages-v2':
            raise ValueError('Panel layout is unavailable.')
        if self.revision != page_delivery.configuration(record, manager.page_region()):
            raise ValueError('Panel layout changed. Wait for the tiles to update and start again.')
        if type(self.page) is not int or not 0 <= self.page < len(record['layout']['pages']):
            raise ValueError('Invalid displayed page.')
        return {'shape': record['sourceGrid'], 'layout': record['layout'], 'page': self.page}

    async def command(self, kind, **values):
        if kind in ('prepared', 'listen', 'pause', 'play', 'error'):
            LOG.info('Device voice #%d provider=%s event=%s elapsed=%.2fs input=%.2fs',
                     self.sequence, self.data['provider'], kind, time.monotonic()-self.started, self.audio_bytes/32000)
        async with asyncio.timeout(3):
            await self.ws.send_json({'type': kind, **values})

    async def listen(self, *, waiting=False):
        if self.data.get('end_voice'):
            await self.ws.close()
            return
        self.utterance.reset()
        if self.relay:
            self.resampler = await asyncio.to_thread(Resampler, 16000, 24000)
            await self.relay.upstream.send_json({'type': 'input_audio_buffer.clear'})
            await self.relay.upstream.send_json({'type': 'session.update', 'session': {
                'type': 'realtime', 'audio': {'input': {'turn_detection': {'type': 'semantic_vad'}}}}})
            self.relay.input_enabled = True
        self.phase = 'listening'
        self.turn_deadline = None
        self.last_audio = time.monotonic()
        if not waiting:
            self.activity = self.last_audio
        remaining = self.owner.idle_seconds - (self.last_audio-self.activity)
        if remaining <= 0:
            self.end_reason = 'silence_or_audio_timeout'
            await self.ws.close()
            return
        await self.command('listen', idle_seconds=max(1, math.ceil(remaining)))

    async def serve(self, request):
        try:
            await self.ws.prepare(request)
            async with asyncio.timeout(5):
                hello = await self.ws.receive_json()
            if not isinstance(hello, dict) or (hello.get('type'), hello.get('version')) not in {
                    ('start', 1), ('prepare', 2)} or hello.get('rate') != 16000:
                raise ValueError('Unsupported device voice protocol.')
            self.warming = hello['type'] == 'prepare'
            if self.warming:
                self.phase = 'warming'
            else:
                self.activation.set()
                self.owner.sessions[self.key] = self.data
            self.page, self.revision = hello.get('page'), hello.get('revision')
            self.data['panel'] = self.panel()
            context = await panel_context(self.owner.manager, self.data['panel'], music=self.owner.music)
            self.owner.output.validate(self.data['reply_speaker'], available=True)
            self.tasks = [asyncio.create_task(self.receive()), asyncio.create_task(self.monitor())]
            setup = asyncio.create_task(self.connect_provider(context))
            self.tasks.append(setup)
            done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            if setup not in done or self.ws.closed or any(task.done() for task in self.tasks if task is not setup):
                return self.ws
            self.tasks.remove(setup)
            if self.relay:
                self.tasks.append(asyncio.create_task(self.relay.upstream_events()))
            if self.warming:
                await self.command('prepared')
                activation = asyncio.create_task(self.activation.wait())
                self.tasks.append(activation)
                done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if activation not in done or self.ws.closed or any(task.done() for task in self.tasks if task is not activation):
                    return self.ws
                self.tasks.remove(activation)
                if len(self.owner.sessions) >= MAX_CALLS or self.settings() != self.configuration:
                    raise ValueError('Voice settings changed or capacity reached.')
                # A wake starts a fresh conversation on the already-connected provider.
                self.warming = False
                self.started = time.monotonic()
                self.data['expires'] = self.started + MAX_SECONDS
                self.owner.sessions[self.key] = self.data
                self.data['panel'] = self.panel()
                if self.relay:
                    context = await panel_context(self.owner.manager, self.data['panel'], music=self.owner.music)
                    await self.relay.upstream.send_json({'type': 'session.update', 'session': {
                        'type': 'realtime', 'instructions': INSTRUCTIONS + '\nPANEL_CONTEXT_DATA:\n' +
                        json.dumps(context, ensure_ascii=False)}})
            await self.listen()
            done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ValueError, ClientError, ConnectionError, TimeoutError, TypeError) as error:
            self.end_reason = type(error).__name__
            # Exception messages can contain provider URLs, tokens or user data.
            LOG.warning('Device voice #%d failed phase=%s type=%s', self.sequence, self.phase, self.end_reason)
            if not self.ws.closed:
                with contextlib.suppress(ConnectionError, TimeoutError):
                    await self.command('error')
        finally:
            LOG.info('Device voice #%d ended phase=%s reason=%s input=%.2fs',
                     self.sequence, self.phase, self.end_reason, self.audio_bytes/32000)
            for task in self.tasks + ([self.worker] if self.worker else []):
                task.cancel()
            await asyncio.gather(*self.tasks, *([self.worker] if self.worker else []), return_exceptions=True)
            await self.owner.close(self.key)
            if self.relay:
                await self.relay.close()
            await self.ws.close()
        return self.ws

    async def connect_provider(self, context):
        async with asyncio.timeout(30):
            if self.data['provider'] == 'openai':
                if not self.owner.key:
                    raise ValueError('Configure the OpenAI key in the editor.')
                self.relay = OpenAIRelay(self.owner, self.key, self.data)
                self.data['relay'] = self.relay
                self.relay.browser = DeviceEvents(self)
                if self.warming:
                    await self.relay.connect(context, listening=False)
                else:
                    await self.relay.connect(context)
            else:
                await self.owner.load_pipelines()
                if not self.owner.configuration()['configured']:
                    raise ValueError('Configure Claude and HA speech in the editor.')
                self.data.update(speech=HASpeech(self.owner.manager.ha, self.owner.pipeline),
                    conversation=Conversation(TEXT_PROVIDERS['claude'], self.owner.manager.ha.session,
                                              self.owner.claude_key, self.owner.claude_model))

    async def receive(self):
        async for message in self.ws:
            if message.type == WSMsgType.BINARY:
                pcm = message.data
                if not pcm or len(pcm) > 4096 or len(pcm) % 2:
                    raise ValueError('Invalid microphone packet.')
                if self.phase != 'listening' or (self.relay and not self.relay.input_enabled):
                    continue  # In-flight capture from before pause is discarded.
                self.audio_bytes += len(pcm)
                self.last_audio = time.monotonic()
                utterance, speaking = self.utterance.push(pcm)
                if speaking:
                    self.activity = self.last_audio
                if self.relay:
                    import base64
                    converted = self.resampler.push(pcm)
                    if converted:
                        async with asyncio.timeout(3):
                            await self.relay.upstream.send_json({'type': 'input_audio_buffer.append',
                                                               'audio': base64.b64encode(converted).decode('ascii')})
                elif utterance:
                    self.phase = 'thinking'
                    await self.command('pause')
                    self.worker = asyncio.create_task(self.claude_turn(utterance))
            elif message.type == WSMsgType.TEXT:
                data = message.json()
                if not isinstance(data, dict):
                    raise ValueError('Invalid voice event.')
                kind = data.get('type')
                if kind == 'stop':
                    self.end_reason = 'stop'
                    return
                if kind == 'start' and self.warming and not self.activation.is_set():
                    self.page, self.revision = data.get('page'), data.get('revision')
                    self.data['panel'] = self.panel()
                    self.activation.set()
                elif kind == 'page':
                    self.page, self.revision = data.get('page'), data.get('revision')
                    self.data['panel'] = self.panel()
                    if self.relay and self.relay.upstream:
                        context = await panel_context(self.owner.manager, self.data['panel'], music=self.owner.music)
                        async with asyncio.timeout(3):
                            await self.relay.upstream.send_json({'type': 'session.update', 'session': {
                                'type': 'realtime', 'instructions': INSTRUCTIONS + '\nPANEL_CONTEXT_DATA:\n' +
                                json.dumps(context, ensure_ascii=False)}})
                elif kind == 'ready' and self.phase == 'speaking':
                    self.ready.set()
                elif kind == 'credit' and self.phase == 'speaking':
                    value = data.get('bytes')
                    if type(value) is not int or value % 2 or not self.credit <= value <= self.sent:
                        raise ValueError('Invalid speaker acknowledgement.')
                    self.credit = value
                    self.credited.set()
                elif kind == 'done' and self.phase == 'speaking' and self.finish_sent and self.credit == self.sent:
                    self.done.set()
                elif kind not in ('page', 'listening', 'pong'):
                    raise ValueError('Unexpected voice device event.')
            elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                return

    async def monitor(self):
        while not self.ws.closed:
            now = time.monotonic()
            if not self.owner.manager.ha.online or not self.owner.enabled:
                self.end_reason = 'ha_offline_or_disabled'
                return
            if now-self.started >= (WARM_SECONDS if self.warming else MAX_SECONDS):
                self.end_reason = 'session_limit'
                return
            if self.warming and self.settings() != self.configuration:
                self.end_reason = 'settings_changed'
                return
            if self.turn_deadline is not None and now >= self.turn_deadline:
                self.end_reason = 'response_timeout'
                return
            if self.phase == 'listening' and (now-self.activity >= self.owner.idle_seconds or now-self.last_audio > 5):
                self.end_reason = 'silence_or_audio_timeout'
                return
            if self.worker and self.worker.done():
                self.worker.result()
                self.worker = None
            await self.command('ping')
            await asyncio.sleep(.5)

    async def playback(self, audio, mime):
        pcm = await asyncio.to_thread(decode_reply, audio, mime)
        self.phase = 'speaking'
        self.ready.clear(); self.done.clear(); self.credited.clear()
        self.credit = self.sent = 0
        self.finish_sent = False
        await self.command('play', bytes=len(pcm), rate=16000)
        async with asyncio.timeout(5):
            await self.ready.wait()
        # One bounded chunk in flight. The speaker acknowledges accepted bytes;
        # short hardware writes never skip audio or require a whole reply in PSRAM.
        async with asyncio.timeout(len(pcm)/32000 + 10):
            for offset in range(0, len(pcm), 2048):
                chunk = pcm[offset:offset+2048]
                self.sent += len(chunk)
                await self.ws.send_bytes(chunk)
                while self.credit < self.sent:
                    self.credited.clear()
                    await self.credited.wait()
            self.finish_sent = True
            await self.command('finish')
            await self.done.wait()

    async def prepared_reply(self, reply):
        if reply.speaker:
            self.phase = 'speaking'
            await self.command('pause')
            await self.owner.output.play(reply)
            async with asyncio.timeout(reply.seconds + 25):
                while reply.state not in ('done', 'error', 'cancelled'):
                    await asyncio.sleep(.1)
            if reply.state != 'done':
                raise ValueError('External reply failed.')
        else:
            await self.playback(reply.data, reply.mime)

    async def claude_turn(self, pcm):
        try:
            async with asyncio.timeout(120):
                self.data['panel'] = self.panel()
                result = await ClaudeSessions(self.owner, MAX_SECONDS, MAX_CALLS).run_turn(self.key, self.data, pcm)
                if result.get('reply'):
                    await self.prepared_reply(self.owner.output.get(self.key, result['reply']['id']))
                elif self.data.get('reply_audio'):
                    await self.playback(*self.data.pop('reply_audio'))
                elif result.get('audio_error'):
                    raise ValueError('Spoken reply unavailable.')
                await self.listen(waiting=result.get('wait_for_user') is True)
        except (ValueError, ClientError, ConnectionError, TimeoutError):
            await self.command('error')
            await self.ws.close()


class DeviceEvents:
    """Consumes the shared Realtime relay's events instead of a browser channel."""
    def __init__(self, session):
        self.session = session

    async def close(self):
        await self.session.ws.close()

    async def send_json(self, event):
        session = self.session
        kind = event.get('type')
        if session.warming:
            # No prompt, tools, responses or microphone traffic while on standby.
            if kind in ('error', 'response.created', 'response.done', 'reply.ready'):
                raise ValueError('Unexpected response before voice activation.')
            return
        if kind == 'input_audio_buffer.speech_started':
            session.activity = time.monotonic()
        elif kind in ('input_audio_buffer.speech_stopped', 'response.created'):
            session.phase = 'thinking'
            if session.turn_deadline is None:
                session.turn_deadline = time.monotonic() + 120
            await session.command('pause')
        elif kind == 'reply.ready':
            reply = session.owner.output.get(session.key, event['reply']['id'])
            await session.prepared_reply(reply)
        elif kind == 'response.done':
            response = event.get('response', {})
            if response.get('status') != 'completed':
                raise ValueError('Incomplete voice response.')
            calls = [item for item in response.get('output', []) if item.get('type') == 'function_call']
            if len(calls) > 8:
                raise ValueError('Too many voice actions.')
            waiting = bool(calls)
            for call in calls:
                result = await session.owner.dispatch(session.key, call['call_id'], call['name'],
                                                      json.loads(call['arguments']), session.panel())
                waiting &= call['name'] == 'wait_for_user' and result.get('wait_for_user') is True
                await session.relay.upstream.send_json({'type': 'conversation.item.create', 'item': {
                    'type': 'function_call_output', 'call_id': call['call_id'], 'output': json.dumps(result)}})
            if calls and not waiting:
                await session.relay.upstream.send_json({'type': 'response.create'})
            else:
                await session.listen(waiting=waiting)
        elif kind == 'error':
            raise ValueError('Voice provider error.')
