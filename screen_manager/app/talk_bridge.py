"""A screen's voice to a doorbell's speaker (docs/DOORBELL.md, "Talk"; docs/CALLS.md).

A screen's microphone comes here as plain 16 kHz, 16-bit mono PCM (`/camera/<token>/talk`, picture_links), and this
bridge sends it to the camera through Home Assistant's two-way audio (Settings, Labs, 2026.11 and later): a second WebRTC
session of Home Assistant's beside the one the picture comes on, with one `sendonly` audio track and nothing else, the
way Home Assistant's own companion apps stream a microphone (frontend src/external_app/camera_microphone_stream.ts).

What the facts make of it:
- go2rtc matches a client's codec exactly and does not transcode its audio, and a Reolink's backchannel is PCMA (go2rtc
  #331), so the offer has PCMA/8000 first and PCMU/8000 second, and nothing else. Hence `addTransceiver` with
  `sendonly`: an `addTrack` would offer the track's codecs as Opus first and would also send its sound back to no one.
- A backchannel left open blocks the next talker (go2rtc #1860): the session closes the moment Talk goes off.
- One talker per doorbell, as a Reolink takes one talk connection at a time: a second screen hears 409.

Pure parts first (decimate, Pcm8k): tests/test_talk_bridge.py drives them without aiortc.
"""
import array
import asyncio
import fractions
import logging
import pathlib
import secrets
import sys
import time
import wave

LOG = logging.getLogger(__name__)

SCREEN_RATE = 16000       # what comes from a screen
DOOR_RATE = 8000          # G.711, what a backchannel takes
PACKET_MS = 20            # one RTP packet of G.711
PACKET_SAMPLES = DOOR_RATE * PACKET_MS // 1000
QUEUE_PACKETS = 15        # 300 ms of voice may wait for the session; older ones go, a voice is never late
# A camera's small speaker distorts near full scale, where G.711 has its coarsest steps: a spoken sentence at 70 % of full
# scale came out of a Reolink "a little too loud, a little distorted" (2026-11-10). 6 dB down, for every voice.
DOOR_LEVEL = 0.5
ANSWER_SECONDS = 15       # Home Assistant's answer and the connection (go2rtc adds the camera's backchannel first)
LINK_SECONDS = 900        # a talk link lives as long as a ring may be answered (doorbell.DOOR_LIFE)
# The offer's codecs, best first (the module's head): names as aiortc's capabilities have them.
CODECS = ('audio/PCMA', 'audio/PCMU')


def decimate(samples, last=0):
    """16 kHz to 8 kHz, 16-bit mono: each pair through the filter 1/4, 1/2, 1/4 and every second one kept, which takes
    away what G.711's half rate would fold back and costs nothing on a Raspberry Pi. `samples` an array('h') of an even
    number of samples, `last` the sample before it. (the samples at 8 kHz, the new `last`)."""
    out = array.array('h', bytes(len(samples)))  # half as many samples of two bytes each
    previous = last
    for i in range(0, len(samples) - 1, 2):
        out[i // 2] = (previous + 2 * samples[i] + samples[i + 1]) >> 2
        previous = samples[i + 1]
    return out, previous


class Pcm8k:
    """Bytes of a screen at 16 kHz in, whole packets at 8 kHz out: a piece of any length, cut on whole samples and whole
    pairs (a part cut in the middle of a sample turns the rest to noise, docs/CAMERA.md), the newest QUEUE_PACKETS kept."""

    def __init__(self, most=QUEUE_PACKETS, level=DOOR_LEVEL):
        self.most, self.spare, self.last, self.ready, self.dropped = most, b'', 0, array.array('h'), 0
        self.level = level

    def feed(self, data):
        data = self.spare + bytes(data)
        whole = len(data) - len(data) % 4  # pairs of two-byte samples
        self.spare = data[whole:]
        if not whole:
            return
        samples = array.array('h')
        samples.frombytes(data[:whole])
        if sys.byteorder == 'big':
            samples.byteswap()
        out, self.last = decimate(samples, self.last)
        if self.level != 1:
            out = array.array('h', (int(value * self.level) for value in out))
        self.ready.extend(out)
        over = len(self.ready) - self.most * PACKET_SAMPLES
        if over > 0:
            del self.ready[:over]
            self.dropped += over

    def packet(self):
        """The next packet of PACKET_SAMPLES samples as little-endian bytes; silence when nothing waits, so the camera's
        clock goes on through a pause."""
        if len(self.ready) < PACKET_SAMPLES:
            return bytes(PACKET_SAMPLES * 2)
        out = self.ready[:PACKET_SAMPLES]
        del self.ready[:PACKET_SAMPLES]
        if sys.byteorder == 'big':
            out.byteswap()
        return out.tobytes()


def _voice_track(source):
    """An aiortc audio track of `source` (Pcm8k), one packet every PACKET_MS of real time."""
    import av
    from aiortc import MediaStreamTrack

    class Voice(MediaStreamTrack):
        kind = 'audio'

        def __init__(self):
            super().__init__()
            self.sent, self.started = 0, None

        async def recv(self):
            if self.started is None:
                self.started = time.monotonic()
            self.sent += 1
            wait = self.started + self.sent * PACKET_MS / 1000 - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            frame = av.AudioFrame(format='s16', layout='mono', samples=PACKET_SAMPLES)
            frame.planes[0].update(source.packet())
            frame.sample_rate = DOOR_RATE
            frame.pts = (self.sent - 1) * PACKET_SAMPLES
            frame.time_base = fractions.Fraction(1, DOOR_RATE)
            return frame

    return Voice()


class Talk:
    """One screen's talk to one camera: `open` until Home Assistant's WebRTC is connected, `feed` the screen's PCM,
    `close` the moment Talk goes off. `websocket()` is an authenticated websocket of Home Assistant (an async context
    manager), as for the pictures (camera_source)."""

    def __init__(self, websocket, entity):
        self.websocket, self.entity = websocket, entity
        self.source = Pcm8k()
        self.connection = self.ws = self.context = self.listening = None
        self.codec = None

    def feed(self, data):
        self.source.feed(data)

    async def open(self):
        """True once the session stands; False (and closed) when Home Assistant refused it or it did not connect."""
        try:
            await asyncio.wait_for(self.start(), ANSWER_SECONDS)
        except (asyncio.TimeoutError, ConnectionError, OSError, ValueError) as err:
            LOG.warning('Talk to %s failed: %s', self.entity, err or 'no answer in time')
            await self.close()
            return False
        LOG.info('Talk to %s: connected, %s', self.entity, self.codec)
        return True

    async def start(self):
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpSender, RTCSessionDescription
        from aiortc.sdp import candidate_from_sdp
        # No STUN: this app and Home Assistant share a network (camera_source says what a STUN server cost).
        self.connection = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        transceiver = self.connection.addTransceiver(_voice_track(self.source), direction='sendonly')
        offered = RTCRtpSender.getCapabilities('audio').codecs
        chosen = [codec for name in CODECS for codec in offered if codec.mimeType.lower() == name.lower()]
        if not chosen:
            raise ValueError('aiortc offers neither PCMA nor PCMU')
        transceiver.setCodecPreferences(chosen)
        connected, failed = asyncio.Event(), asyncio.Event()

        @self.connection.on('connectionstatechange')
        async def state_changed():
            state = self.connection.connectionState if self.connection else 'closed'
            if state == 'connected':
                connected.set()
            elif state in ('failed', 'closed'):
                failed.set()

        await self.connection.setLocalDescription(await self.connection.createOffer())
        self.context = self.websocket()
        self.ws = await self.context.__aenter__()
        await self.ws.send_json({'id': 1, 'type': 'camera/webrtc/offer', 'entity_id': self.entity,
                                 'offer': self.connection.localDescription.sdp})
        answered = asyncio.Event()

        async def signals():
            async for message in self.ws:
                data = message.json()
                if data.get('type') == 'result' and not data.get('success'):
                    LOG.warning('Talk to %s refused: %s', self.entity, data.get('error'))
                    failed.set()
                    return
                event = data.get('event') or {}
                if event.get('type') == 'answer':
                    await self.connection.setRemoteDescription(RTCSessionDescription(event['answer'], 'answer'))
                    self.codec = negotiated_codec(event['answer'])
                    answered.set()
                elif event.get('type') == 'candidate' and (event.get('candidate') or {}).get('candidate'):
                    found = event['candidate']
                    candidate = candidate_from_sdp(found['candidate'].split(':', 1)[1])
                    candidate.sdpMid, candidate.sdpMLineIndex = found.get('sdpMid'), found.get('sdpMLineIndex')
                    await self.connection.addIceCandidate(candidate)
                elif event.get('type') == 'error':
                    LOG.warning('Talk to %s: %s', self.entity, event.get('message'))
                    failed.set()
                    return

        self.listening = asyncio.create_task(signals())
        self.listening.add_done_callback(lambda done: done.cancelled() or not done.exception() or
                                         LOG.warning('Talk to %s: signalling stopped: %r', self.entity, done.exception()))
        waits = [asyncio.create_task(connected.wait()), asyncio.create_task(failed.wait())]
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for each in waits:
                each.cancel()
        if failed.is_set() or not answered.is_set():
            raise ConnectionError('Home Assistant did not connect the talk session')

    async def close(self):
        connection, self.connection = self.connection, None
        if self.listening is not None:
            self.listening.cancel()
            self.listening = None
        if connection is not None:
            try:
                await connection.close()
            except Exception as err:  # noqa: BLE001 - closing what may never have opened
                LOG.debug('Talk close: %s', err)
        context, self.context, self.ws = self.context, None, None
        if context is not None:
            try:
                await context.__aexit__(None, None, None)
            except Exception as err:  # noqa: BLE001 - as above
                LOG.debug('Talk close: %s', err)


def negotiated_codec(sdp):
    """The codec Home Assistant's answer settled on, 'PCMA/8000', from its first audio line's first payload."""
    payload, codecs = None, {}
    for line in (sdp or '').splitlines():
        if line.startswith('m=audio') and payload is None:
            parts = line.split()
            payload = parts[3] if len(parts) > 3 else None
        elif line.startswith('a=rtpmap:'):
            name, _, rest = line[len('a=rtpmap:'):].partition(' ')
            codecs[name] = rest
    return codecs.get(payload, '')


class Sink:
    """The bench's stand-in for a camera (Links with `sink`, SCREEN_TALK_SINK): the voice lands in a WAV file in that
    folder, so the screen's half is proven without a doorbell."""

    def __init__(self, folder, entity):
        self.folder, self.entity, self.codec, self.wave = pathlib.Path(folder), entity, 'wav', None
        self.source = Pcm8k()

    async def open(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f'talk-{time.strftime("%H%M%S")}.wav'
        self.wave = wave.open(str(path), 'wb')
        self.wave.setnchannels(1)
        self.wave.setsampwidth(2)
        self.wave.setframerate(SCREEN_RATE)
        LOG.info('Talk to %s goes to %s', self.entity, path)
        return True

    def feed(self, data):
        self.wave.writeframes(bytes(data))

    async def close(self):
        if self.wave is not None:
            self.wave.close()
            self.wave = None


class Links:
    """The talk links of this app's lifetime. `open(token)` hands out the bridge of a token's camera, one talker per
    camera; a screen that may not talk (no token, a second talker) gets the reason."""

    def __init__(self, websocket, clock=time.monotonic, sink=None):
        self.websocket, self.clock, self.sink = websocket, clock, sink
        self.links = {}   # token -> {'entity', 'screen', 'made'}
        self.talking = {}  # entity -> token

    def link(self, entity, screen=None):
        now = self.clock()
        for token in [t for t, item in self.links.items() if now - item['made'] > LINK_SECONDS]:
            del self.links[token]
        token = secrets.token_urlsafe(18)
        self.links[token] = {'entity': entity, 'screen': screen, 'made': now}
        return token

    def busy(self, token):
        """Why `token` may not start talking now: 'unknown' or 'busy', or None."""
        item = self.links.get(token)
        if item is None:
            return 'unknown'
        holder = self.talking.get(item['entity'])
        return 'busy' if holder is not None and holder != token else None

    def begin(self, token):
        item = self.links[token]
        self.talking[item['entity']] = token
        return Sink(self.sink, item['entity']) if self.sink else Talk(self.websocket, item['entity'])

    def end(self, token):
        item = self.links.get(token)
        if item is not None and self.talking.get(item['entity']) == token:
            del self.talking[item['entity']]

    async def serve(self, request, token):
        """POST /camera/<token>/talk: the screen's PCM as it comes (chunked). The answer's head goes out once the session
        to the camera stands, so the screen's key says Talking only then; 200, 404 unknown link, 409 someone else talks,
        503 Home Assistant did not connect. It ends when the screen stops sending."""
        from aiohttp import web
        why = self.busy(token)
        if why == 'unknown':
            return web.Response(status=404, text='Unknown link')
        if why == 'busy':
            return web.Response(status=409, text='Someone else is talking to this camera')
        talk = self.begin(token)
        total = 0
        try:
            if not await talk.open():
                return web.Response(status=503, text='No talk session')
            response = web.StreamResponse(headers={'Content-Type': 'text/plain', 'Connection': 'close'})
            await response.prepare(request)
            await response.write(b'live\n')
            async for data in request.content.iter_any():
                talk.feed(data)
                total += len(data)
            await response.write_eof()
            return response
        except (ConnectionResetError, asyncio.CancelledError, ConnectionError):
            return web.Response(status=499, text='Gone')
        finally:
            LOG.info('Talk to %s ended: %.1f s of voice, %d samples dropped', self.links[token]['entity'],
                     total / (2 * SCREEN_RATE), talk.source.dropped)
            await talk.close()
            self.end(token)
