"""HA supplies only STT and TTS. Its conversation agent never executes a turn."""
import asyncio
import re
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientTimeout, WSMsgType

MAX_PCM = 16000 * 2 * 30
MAX_AUDIO = 4 * 1024 * 1024


async def pipelines(ha):
    result = await ha.request('assist_pipeline/pipeline/list')
    engines = {}
    for stage in ('stt', 'tts'):
        try:
            listed = await ha.request(stage + '/engine/list')
            engines[stage] = {p['engine_id']: p for p in listed.get('providers', [])}
        except (ConnectionError, ValueError, TimeoutError):
            engines[stage] = {}
    choices = []
    for pipeline in result.get('pipelines', []):
        ready = {}
        for stage in ('stt', 'tts'):
            key = pipeline.get(stage + '_engine')
            engine = engines[stage].get(key)
            language = pipeline.get(stage + '_language') or pipeline['language']
            ready[stage + '_ready'] = bool(engine and language in engine.get('supported_languages', [])
                and ha.states.get(key, {}).get('state') != 'unavailable')
        choices.append({'id': pipeline['id'], 'name': pipeline['name'], 'language': pipeline['language'],
                        'ready': all(ready.values()), **ready})
    return choices


class HASpeech:
    def __init__(self, ha, pipeline):
        self.ha, self.pipeline = ha, pipeline

    async def stage(self, stage, *, pcm=None, text=None):
        # A separate connection owns each pipeline subscription. Closing it on
        # cancellation also cancels the HA run and releases its binary handler.
        url = ('ws://supervisor/core/websocket' if self.ha.base == 'http://supervisor/core/api'
               else self.ha.base.replace('http://', 'ws://').replace('https://', 'wss://') + '/websocket')
        try:
            async with asyncio.timeout(90):
                async with self.ha.session.ws_connect(url, heartbeat=20, max_msg_size=1024*1024) as ws:
                    await ws.receive_json(timeout=10)
                    await ws.send_json({'type': 'auth', 'access_token': self.ha.token})
                    if (await ws.receive_json(timeout=10)).get('type') != 'auth_ok':
                        raise ConnectionError('Home Assistant speech authentication failed.')
                    await ws.send_json({'id': 1, 'type': 'assist_pipeline/run', 'pipeline': self.pipeline,
                        'start_stage': stage, 'end_stage': stage, 'timeout': 85,
                        'input': {'sample_rate': 16000} if stage == 'stt' else {'text': text}})
                    prefix, output, sent = None, None, False
                    async for message in ws:
                        if message.type != WSMsgType.TEXT:
                            break
                        data = message.json()
                        if data.get('id') != 1:
                            continue
                        if data.get('type') == 'result' and not data.get('success'):
                            raise ValueError('Home Assistant refused the speech stage. Check the selected voice assistant.')
                        event = data.get('event', {})
                        kind, fields = event.get('type'), event.get('data', {})
                        if kind == 'run-start':
                            handler = fields.get('runner_data', {}).get('stt_binary_handler_id')
                            if isinstance(handler, int) and 0 <= handler <= 255:
                                prefix = bytes([handler])
                        elif kind == 'stt-start' and stage == 'stt' and not sent:
                            if prefix is None:
                                raise ValueError('Home Assistant supplied no speech input channel.')
                            sent = True
                            for offset in range(0, len(pcm), 4096):
                                await ws.send_bytes(prefix + pcm[offset:offset + 4096])
                            await ws.send_bytes(prefix)
                        elif kind == stage + '-end':
                            output = fields.get(stage + '_output')
                        elif kind == 'error':
                            if fields.get('code') == 'stt-no-text-recognized':
                                return {'text': ''}
                            raise ValueError(f'Home Assistant {stage.upper()} failed. Check its voice assistant settings and logs.')
                        elif kind == 'run-end':
                            if isinstance(output, dict):
                                return output
                            break
        except (ClientError, TimeoutError):
            raise ConnectionError('Home Assistant speech did not respond in time.') from None
        raise ConnectionError('Home Assistant speech ended without a result.')

    async def transcribe(self, pcm):
        if not 3200 <= len(pcm) <= MAX_PCM or len(pcm) % 2:
            raise ValueError('Speech must be 0.1 to 30 seconds of 16 kHz mono PCM audio.')
        text = (await self.stage('stt', pcm=pcm)).get('text', '')
        if not isinstance(text, str) or len(text) > 8000:
            raise ValueError('Home Assistant returned an invalid transcript.')
        return text.strip()

    async def synthesize(self, text):
        output = await self.stage('tts', text=text)
        parsed = urlsplit(output.get('url', ''))
        # HA may return its external hostname. Fetch only its generated TTS
        # resource through the configured HA API origin, never that hostname.
        if not re.fullmatch(r'/api/tts_proxy/[a-zA-Z0-9_.-]+', parsed.path) or '..' in parsed.path or parsed.query or parsed.fragment:
            raise ValueError('Home Assistant returned an unsupported speech URL.')
        url = self.ha.base.removesuffix('/api') + parsed.path
        try:
            async with self.ha.session.get(url, headers={'Authorization': 'Bearer ' + self.ha.token},
                    allow_redirects=False, timeout=ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise ValueError('The spoken reply could not be downloaded from Home Assistant.')
                mime = response.headers.get('Content-Type', '').split(';')[0]
                if mime not in {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/ogg', 'audio/flac', 'audio/x-flac'}:
                    raise ValueError('Home Assistant returned an unsupported speech format.')
                audio = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    audio.extend(chunk)
                    if len(audio) > MAX_AUDIO:
                        raise ValueError('The spoken reply is too large.')
                return bytes(audio), mime
        except (ClientError, TimeoutError):
            raise ConnectionError('The spoken reply could not be downloaded from Home Assistant.') from None
