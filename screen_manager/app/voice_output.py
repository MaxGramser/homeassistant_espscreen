"""Shared reply delivery. AI providers never choose the output entity or volume."""
import asyncio
import io
import secrets
import wave
from dataclasses import dataclass, field

from aiohttp import ClientError, web

import camera_feed

MAX_AUDIO = 4 * 1024 * 1024
MAX_SECONDS = 60
FETCH_SECONDS = 15
PLAYBACK_MARGIN = 1.5


def duration(data, mime):
    if not data or len(data) > MAX_AUDIO:
        raise ValueError('The spoken reply is empty or too large.')
    try:
        if mime in {'audio/wav', 'audio/x-wav'}:
            with wave.open(io.BytesIO(data)) as audio:
                if audio.getcomptype() != 'NONE':
                    raise ValueError('Unsupported WAV encoding.')
                seconds = audio.getnframes() / audio.getframerate()
                if len(audio.readframes(audio.getnframes())) != audio.getnframes() * audio.getnchannels() * audio.getsampwidth():
                    raise ValueError('Incomplete reply audio.')
        elif mime == 'audio/mpeg':
            from mutagen import MutagenError
            from mutagen.mp3 import MP3
            try:
                seconds = MP3(io.BytesIO(data)).info.length
            except MutagenError as error:
                raise ValueError('The reply audio could not be read.') from error
        else:
            raise ValueError('Choose an HA speech engine that produces WAV or MP3 for Sonos replies.')
    except (EOFError, wave.Error, ZeroDivisionError, ImportError) as error:
        raise ValueError('The reply audio could not be read.') from error
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError('Spoken replies must be shorter than one minute.')
    return seconds


def pcm_wav(data, rate=24000):
    if not data or len(data) % 2 or len(data) > rate * 2 * MAX_SECONDS:
        raise ValueError('Invalid reply audio.')
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(rate)
        audio.writeframes(data)
    return out.getvalue()


@dataclass
class Reply:
    token: str
    owner: str
    speaker: str
    volume: int
    data: bytes
    mime: str
    seconds: float
    state: str = 'ready'
    error: str = ''
    fetched: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def view(self):
        return {'id': self.token, 'output': 'sonos' if self.speaker else 'local',
                'state': self.state, 'error': self.error}


class ReplyOutput:
    def __init__(self, ha):
        self.ha = ha
        self.replies = {}
        self.busy = {}
        self.tasks = set()

    def speakers(self):
        choices = []
        for entity in self.ha.registry:
            eid = entity.get('entity_id', '')
            if entity.get('platform') != 'sonos' or not eid.startswith('media_player.') or entity.get('disabled_by'):
                continue
            state = self.ha.states.get(eid, {})
            choices.append({'id': eid, 'name': state.get('attributes', {}).get('friendly_name') or eid,
                            'available': state.get('state') not in {None, 'unknown', 'unavailable'}})
        return sorted(choices, key=lambda item: item['name'].casefold())

    def validate(self, speaker, *, available=False):
        if not isinstance(speaker, str):
            raise ValueError('Choose a reply speaker.')
        if not speaker:
            return
        choice = next((item for item in self.speakers() if item['id'] == speaker), None)
        if not choice:
            raise ValueError('Choose an available Sonos entity in Voice assistant settings.')
        if available and (not self.ha.online or not choice['available']):
            raise ValueError('The reply speaker is unavailable. Choose another output or try again later.')
        if available and speaker in self.busy:
            raise ValueError('The reply speaker is finishing another voice reply. Try again shortly.')

    def prepare(self, owner, data, mime, speaker, volume):
        seconds = duration(data, mime)
        # One conversational reply at a time. Replaced audio is not retained.
        for token, old in list(self.replies.items()):
            if old.owner == owner:
                if old.task and not old.task.done():
                    raise ValueError('Wait for the previous reply to finish.')
                self.replies.pop(token)
        reply = Reply(secrets.token_urlsafe(32), owner, speaker, volume, data, mime, seconds)
        self.replies[reply.token] = reply
        return reply.view()

    def get(self, owner, token):
        reply = self.replies.get(token)
        if not reply or reply.owner != owner:
            raise web.HTTPNotFound()
        return reply

    async def play(self, reply):
        if reply.state != 'ready':
            return reply.view()  # Repeated POSTs never replay an announcement.
        if not reply.speaker:
            raise ValueError('This reply uses the local speaker.')
        self.validate(reply.speaker, available=True)
        base = await camera_feed.base_url(self.ha.request)
        if not base:
            raise ValueError('Home Assistant could not find the Screen Manager audio address.')
        if reply.state != 'ready':
            return reply.view()
        # Recheck after the address lookup, before reserving this output.
        self.validate(reply.speaker, available=True)
        self.busy[reply.speaker] = reply.token
        reply.state = 'preparing_speech'
        reply.task = asyncio.create_task(self._play(reply, base))
        self.tasks.add(reply.task)
        reply.task.add_done_callback(self.tasks.discard)
        return reply.view()

    async def _play(self, reply, base):
        try:
            extension = 'mp3' if reply.mime == 'audio/mpeg' else 'wav'
            async with asyncio.timeout(20):
                await self.ha.call('media_player.play_media', {
                    'entity_id': reply.speaker, 'media_content_id': f'{base}/voice/{reply.token}.{extension}',
                    'media_content_type': 'music', 'announce': True, 'extra': {'volume': reply.volume}})
            await asyncio.wait_for(reply.fetched.wait(), FETCH_SECONDS)
            if reply.state != 'cancelled':
                reply.state = 'speaking'
            # HA does not expose a Sonos clip-finished event. Start this guard
            # after the full download, never from service acceptance alone.
            await asyncio.sleep(reply.seconds + PLAYBACK_MARGIN)
            if reply.state != 'cancelled':
                reply.state = 'done'
        except (ClientError, ConnectionError, TimeoutError, ValueError):
            reply.state = 'error'
            reply.error = 'The reply speaker could not play the answer. Check its connection and audio access.'
        finally:
            reply.data = b''
            if self.busy.get(reply.speaker) == reply.token:
                self.busy.pop(reply.speaker, None)

    async def serve(self, request):
        reply = self.replies.get(request.match_info['token'])
        if not reply or not reply.data or reply.state not in {'preparing_speech', 'speaking'}:
            raise web.HTTPNotFound()
        response = web.StreamResponse(headers={'Content-Type': reply.mime,
            'Content-Length': str(len(reply.data)), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        await response.prepare(request)
        if request.method != 'HEAD':
            await response.write(reply.data)
            await response.write_eof()
            reply.fetched.set()
        return response

    def register_media(self, app):
        app.router.add_get(r'/voice/{token:[A-Za-z0-9_-]{43}}.{ext:wav|mp3}', self.serve)

    async def close(self, owner):
        for token, reply in list(self.replies.items()):
            if reply.owner != owner:
                continue
            self.replies.pop(token)
            reply.data = b''
            reply.state = 'cancelled'
            # A Sonos clip already fetched may finish. Keep its output reserved
            # until the guard expires, so a new session cannot hear that reply.
            if reply.task and not reply.fetched.is_set():
                reply.task.cancel()
                await asyncio.gather(reply.task, return_exceptions=True)
                if self.busy.get(reply.speaker) == reply.token:
                    self.busy.pop(reply.speaker, None)

    async def shutdown(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.replies.clear(); self.busy.clear()
