"""A camera live, full screen, on the P4 boards (docs/CAMERA.md, "Live on the P4 boards").

A P4 screen opens a camera full screen and asks for it with `live`: the room below its top bar, "1280x728". This app
answers with a link on its camera port, `/camera/<token>.mjpeg`: a stream of baseline JPEGs (multipart/x-mixed-replace,
one picture a part with its Content-Length). The screen decodes each in its hardware JPEG decoder and its PPA scales it
to fill that room, so this app never makes a picture larger than the camera's own, and every picture is the newest the
camera gave when the screen had taken the last one: a slow Wi-Fi gets fewer pictures, never older ones.

Most of the work a live camera costs lands on Home Assistant's host, often a Raspberry Pi, so each kind of camera takes
the cheapest road there is (measured 2026-10-10 on an EZVIZ, 1080p main stream and 512 x 288 substream):

- A camera with a stream (an RTSP camera through generic, ONVIF, Reolink, UniFi and others) comes through Home
  Assistant's own WebRTC (its built-in go2rtc relays the camera's H.264 as it is): 0.12 s behind the camera, frame by
  frame, where Home Assistant's LL-HLS was 0.6 to 1.2 s behind and came in bursts of a second. The H.264 is decoded
  here (aiortc, PyAV), the only place that can: the P4 has an H.264 encoder, no decoder. Decoding costs what the
  camera's resolution costs, so a camera's low-resolution stream (its substream entity) is the light one. Its JPEG is
  made straight from the decoder's YUV with ffmpeg's encoder, at the camera's own size (1 ms for 512 x 288 on a PC,
  where Pillow from RGB took 3), or scaled down to the room where the camera is larger (7 ms for 1080p to 720p, Pillow
  19). Until WebRTC's first frame (it waits for the camera's next key frame, seconds on some cameras) the screen gets
  the camera's still.
- Any other camera (a snapshot camera, an ESPHome camera, a picture an integration draws) gives its snapshot, asked
  again as soon as the last came. A JPEG the P4 decodes as it is (baseline, at most MAX_SIDE a side) goes out untouched,
  which costs this app nothing; anything else is made into one.

One source per camera, shared by every screen that watches it; it stops a few seconds after the last one stops.
"""
import asyncio
import fractions
import io
import logging
import secrets
import socket
import time

import catalogue

LOG = logging.getLogger(__name__)

# The largest picture a screen takes as it is (firmware live_view::MAX_SIDE is 2048 and MAX_PICTURE 1 MB), and larger
# frames are scaled down to the room the screen asked for.
MAX_SIDE = 1920
MAX_BYTES = 1024 * 1024
MIN_SIDE, MAX_BOX = 64, 4096
MAX_STREAMS = 8           # streams at once: a page of live tiles and a camera full screen, of every screen together
LINK_SECONDS = 60         # a link nobody opened for this long goes; a stream keeps its link while it runs
FRAME_SECONDS = 15        # nothing new from the camera for this long: the stream ends and the screen asks again
LINGER_SECONDS = 5        # a camera nobody watches any more stops after this (a screen that asks again at once finds it)
SNAPSHOT_FPS = 15         # a camera without a stream is asked no more often than this
WEBRTC_FIRST_SECONDS = 20  # a WebRTC session without a frame by then gives way to the snapshots
DEFAULT_PACE = 15         # camera_feed.LIVE_REFRESH_DEFAULT: the pace of a camera tile on a screen that does not stream
QSCALE = 5                # ffmpeg's mjpeg quality (2 best, 31 worst): about 80 KB a 1280 x 720 camera picture
SEND_BUFFER = 65536       # what may wait in this host's socket for a screen: a picture, not a queue of them
# A camera with a stream of its own (CameraEntityFeature.STREAM, by its name in Home Assistant's source).
STREAM_FEATURE = catalogue.bits('camera', 'STREAM')
# What a screen that streams says in its hello (live_view.h): a camera tile set to Live, pace 0, streams there, and Live
# is the default pace of its camera tiles.
SCREEN_FEATURE = 'live'
LIVE_PACE = 0


def parse_box(text):
    """'1280x728' from a screen: (width, height), or None for anything else."""
    try:
        width, height = (int(part) for part in str(text).lower().split('x'))
    except (TypeError, ValueError):
        return None
    return (width, height) if MIN_SIDE <= width <= MAX_BOX and MIN_SIDE <= height <= MAX_BOX else None


def size_for(width, height, box):
    """The size a frame of width x height goes out at: its own where it fits the room (the screen scales it up), else as
    large as fits, its proportions kept. Even sides, and a multiple of 16 when scaled, as the JPEG's blocks are."""
    bw, bh = box
    if width <= bw and height <= bh and width <= MAX_SIDE and height <= MAX_SIDE:
        return width - width % 2, height - height % 2
    scale = min(bw / width, bh / height, MAX_SIDE / width, MAX_SIDE / height)
    return max(16, int(width * scale) // 16 * 16), max(16, int(height * scale) // 16 * 16)


def size_to_cover(width, height, box):
    """The size a frame of width x height goes out at for a live tile that fills its card: as small as still covers the
    card, its proportions kept (the screen cuts the middle of it), and never larger than the frame: a smaller one the
    screen's PPA scales up."""
    bw, bh = box
    if width <= bw or height <= bh:
        return width - width % 2, height - height % 2
    scale = max(bw / width, bh / height)
    even_up = lambda n: min(int(-(-n // 2) * 2), 4096)
    return min(even_up(width * scale), width - width % 2), min(even_up(height * scale), height - height % 2)


def live_pace(message, tile, features):
    """A camera tile set to Live (pace 0, firmware dev) in a tile's message: a screen whose hello says it streams (or
    the editor's preview, `features` None) gets pace 0, also for a tile without a pace of its own, where Live is the
    default; any other screen gets the pace every camera tile has by default, whatever the tile says."""
    options = tile.get('options') or {}
    if not tile.get('entity', '').startswith('camera.') or options.get('display') != 'live':
        return
    refresh = options.get('refresh')
    if refresh not in (None, LIVE_PACE):
        return
    streams = features is None or SCREEN_FEATURE in features
    if streams:
        message.setdefault('o', {})['refresh'] = LIVE_PACE
    elif refresh == LIVE_PACE:
        message.setdefault('o', {})['refresh'] = DEFAULT_PACE


def jpeg_size(raw):
    """(width, height) of a JPEG the P4's hardware decoder takes as it is (baseline, 8 bits, one or three components
    sampled 4:4:4, 4:2:2 or 4:2:0, ESP-IDF's jpeg_parse_marker.c), at most MAX_SIDE a side; None for anything else."""
    if not isinstance(raw, (bytes, bytearray)) or raw[:2] != b'\xff\xd8' or len(raw) > MAX_BYTES:
        return None
    at = 2
    while at + 4 <= len(raw):
        if raw[at] != 0xFF:
            return None
        marker = raw[at + 1]
        if marker == 0xFF:
            at += 1
            continue
        length = int.from_bytes(raw[at + 2:at + 4], 'big')
        if marker == 0xC0:
            segment = raw[at + 4:at + 2 + length]
            if len(segment) < 6 or segment[0] != 8:
                return None
            height, width, count = int.from_bytes(segment[1:3], 'big'), int.from_bytes(segment[3:5], 'big'), segment[5]
            if count not in (1, 3) or len(segment) < 6 + 3 * count:
                return None
            if count == 3:
                factors = [segment[7 + 3 * i] for i in range(3)]
                if factors[0] not in (0x11, 0x21, 0x22) or factors[1] != 0x11 or factors[2] != 0x11:
                    return None
            if not width or not height or width > MAX_SIDE or height > MAX_SIDE or width * height % 8:
                return None
            return width, height
        if 0xC1 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return None  # progressive, lossless, arithmetic: the decoder takes baseline only
        if marker == 0xDA:
            return None  # the picture's data, and no SOF0 before it
        at += 2 + length
    return None


def remake(raw, box, cover=False):
    """A picture the P4 does not take as it is (a progressive JPEG, a PNG, one too large) as a baseline JPEG that fits,
    or that covers a live tile's card: (JPEG, CPU ms this thread spent on it)."""
    from PIL import Image
    started = time.thread_time()
    image = Image.open(io.BytesIO(raw))
    width, height = (size_to_cover if cover else size_for)(image.width, image.height, box)
    if image.format == 'JPEG':
        image.draft('RGB', (width, height))  # decoded at a fraction of its size where that is enough
    image = image.convert('RGB')
    if image.size != (width, height):
        image = image.resize((width, height), Image.BILINEAR)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=80, subsampling='4:2:0')
    return out.getvalue(), (time.thread_time() - started) * 1000


class Encoder:
    """JPEGs of decoded video frames at one size, made straight from the decoder's YUV (ffmpeg's mjpeg)."""

    def __init__(self, width, height):
        import av
        self.size = (width, height)
        self.codec = av.CodecContext.create('mjpeg', 'w')
        self.codec.width, self.codec.height, self.codec.pix_fmt = width, height, 'yuvj420p'
        self.codec.time_base = fractions.Fraction(1, 90000)
        # A fixed quality: the encoder's quantiser held at QSCALE (PyAV leaves -q:v's global_quality alone for mjpeg).
        self.codec.qmin = self.codec.qmax = QSCALE
        self.count = 0

    def encode(self, frame):
        """(JPEG, CPU ms this thread spent on it)."""
        started = time.thread_time()
        width, height = self.size
        scaled = (frame.width, frame.height) != (width, height)
        picture = frame.reformat(width=width, height=height, format='yuvj420p',
                                 interpolation='BILINEAR' if scaled else None)
        self.count += 1
        picture.pts = self.count
        jpeg = b''.join(bytes(packet) for packet in self.codec.encode(picture))
        return jpeg, (time.thread_time() - started) * 1000


class Frame:
    __slots__ = ('number', 'jpeg', 'video', 'at')

    def __init__(self, number, jpeg=None, video=None):
        self.number, self.jpeg, self.video, self.at = number, jpeg, video, time.monotonic()


class Source:
    """The newest picture of one camera, for every screen that watches it."""

    def __init__(self, feed, entity, streams):
        self.feed, self.entity, self.streams = feed, entity, streams
        self.frame, self.number, self.viewers = None, 0, 0
        self.changed = asyncio.Condition()
        self.task, self.idle_since = None, None
        self.encoders, self.pictures = {}, {}
        self.making = asyncio.Lock()  # one picture at a time: an encoder is not for two threads
        self.route = 'snapshot'
        self.made = self.made_ms = 0
        # When the way to the first picture went by, in seconds after the source started (the log of the first picture).
        self.started, self.marks = time.monotonic(), {}

    def mark(self, what):
        self.marks.setdefault(what, time.monotonic() - self.started)

    async def publish(self, jpeg=None, video=None):
        self.number += 1
        self.frame = Frame(self.number, jpeg, video)
        async with self.changed:
            self.changed.notify_all()

    async def next(self, after, timeout):
        """The newest picture after `after`, or None when the camera gave none for `timeout` seconds."""
        try:
            async with self.changed:
                await asyncio.wait_for(self.changed.wait_for(lambda: self.frame and self.frame.number > after), timeout)
        except asyncio.TimeoutError:
            return None
        return self.frame

    async def picture(self, frame, box, cover=False):
        """The JPEG of `frame` for a screen with room `box` (a live tile that fills its card: `cover`), made once per
        frame and room."""
        async with self.making:
            made = self.pictures.get((box, cover))
            if made and made[0] == frame.number:
                return made[1]
            jpeg = await self.make(frame, box, cover)
            self.pictures[(box, cover)] = (frame.number, jpeg)
            return jpeg

    async def make(self, frame, box, cover=False):
        loop = asyncio.get_running_loop()
        sizing = size_to_cover if cover else size_for
        if frame.jpeg is not None:
            size = jpeg_size(frame.jpeg)
            # A JPEG the P4 takes as it is goes out untouched, when it is no larger than it needs to be: the screen
            # scales and cuts it itself.
            jpeg, ms = (frame.jpeg, 0.0) if size and size == sizing(*size, box) else \
                await loop.run_in_executor(None, remake, frame.jpeg, box, cover)
        else:
            size = sizing(frame.video.width, frame.video.height, box)
            encoder = self.encoders.get(size)
            if encoder is None:
                encoder = self.encoders[size] = Encoder(*size)
            jpeg, ms = await loop.run_in_executor(None, encoder.encode, frame.video)
        self.made += 1
        self.made_ms += ms
        return jpeg

    def start(self):
        if self.task is None or self.task.done():
            self.started, self.marks = time.monotonic(), {}
            self.task = asyncio.create_task(self.run())

    async def run(self):
        """Pictures while anyone watches: WebRTC for a camera with a stream, its still until the first frame and if
        WebRTC fails; snapshots for any other camera."""
        try:
            if self.streams and await self.webrtc():
                return
            await self.snapshots()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - a camera that fails ends its streams; screens ask again
            LOG.warning('Live %s ended: %s', self.entity, error)

    def watched(self):
        return self.viewers > 0 or (self.idle_since and time.monotonic() - self.idle_since < LINGER_SECONDS)

    async def snapshots(self):
        self.route = 'snapshot'
        failures = 0
        while self.watched():
            started = time.monotonic()
            try:
                raw = await self.feed.fetch(self.entity)
                failures = 0
                if raw:
                    await self.publish(jpeg=raw)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - tried again, a little later each time
                failures += 1
                if failures == 1:
                    LOG.info('Live %s: no snapshot (%s)', self.entity, type(error).__name__)
                await asyncio.sleep(min(10, failures))
            await asyncio.sleep(max(0.0, 1 / SNAPSHOT_FPS - (time.monotonic() - started)))

    async def webrtc(self):
        """Home Assistant's WebRTC of the camera until nobody watches; False when it gave no frame (no WebRTC here, no
        aiortc in this install, a camera go2rtc cannot relay): the snapshots take over."""
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription
            from aiortc.sdp import candidate_from_sdp
        except ImportError:
            return False
        self.route = 'webrtc'
        first = asyncio.Event()
        connection = RTCPeerConnection()
        connection.addTransceiver('video', direction='recvonly')
        pulls = []

        @connection.on('track')
        def on_track(track):
            async def pull():
                while True:
                    frame = await track.recv()
                    self.mark('first WebRTC frame')
                    first.set()
                    await self.publish(video=frame)
            pulls.append(asyncio.create_task(pull()))

        # The camera's still until its first frame: WebRTC waits for the camera's next key frame.
        still = asyncio.create_task(self.still_until(first))
        try:
            await connection.setLocalDescription(await connection.createOffer())
            self.mark('offer')
            async with self.feed.websocket() as ws:
                await ws.send_json({'id': 1, 'type': 'camera/webrtc/offer', 'entity_id': self.entity,
                                    'offer': connection.localDescription.sdp})

                async def signals():
                    async for message in ws:
                        data = message.json()
                        if data.get('type') == 'result' and not data.get('success'):
                            raise ConnectionError((data.get('error') or {}).get('message') or 'refused')
                        event = data.get('event') or {}
                        if event.get('type') == 'answer':
                            self.mark('answer')
                            await connection.setRemoteDescription(RTCSessionDescription(event['answer'], 'answer'))
                        elif event.get('type') == 'candidate' and (event.get('candidate') or {}).get('candidate'):
                            found = event['candidate']
                            candidate = candidate_from_sdp(found['candidate'].split(':', 1)[1])
                            candidate.sdpMid, candidate.sdpMLineIndex = found.get('sdpMid'), found.get('sdpMLineIndex')
                            await connection.addIceCandidate(candidate)
                        elif event.get('type') == 'error':
                            raise ConnectionError(event.get('message') or 'error')

                listening = asyncio.create_task(signals())
                try:
                    await asyncio.wait_for(first.wait(), WEBRTC_FIRST_SECONDS)
                except asyncio.TimeoutError:
                    LOG.info('Live %s: no WebRTC frame in %d s; snapshots instead', self.entity, WEBRTC_FIRST_SECONDS)
                    return False
                while self.watched() and not listening.done() and all(not p.done() for p in pulls):
                    await asyncio.sleep(1)
                if listening.done() and listening.exception():
                    LOG.info('Live %s: WebRTC ended (%s)', self.entity, listening.exception())
                listening.cancel()
                return True
        except (ConnectionError, OSError, asyncio.TimeoutError) as error:
            LOG.info('Live %s: no WebRTC (%s); snapshots instead', self.entity, error)
            return False
        finally:
            still.cancel()
            for task in pulls:
                task.cancel()
            await connection.close()

    async def still_until(self, first):
        try:
            raw = await self.feed.fetch(self.entity)
            self.mark('still')
            if raw and not first.is_set():
                await self.publish(jpeg=raw)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - only a first picture; the stream follows
            pass


class Link:
    __slots__ = ('entity', 'box', 'used', 'streaming', 'made', 'cover')

    def __init__(self, entity, box, now, cover=False):
        self.entity, self.box, self.used, self.streaming, self.made, self.cover = entity, box, now, 0, now, cover


class LiveFeed:
    """The live links and their sources. `fetch(entity)` is a snapshot (the app's own camera_proxy fetch),
    `websocket()` an authenticated websocket of Home Assistant (an async context manager), `streams(entity)` whether
    the camera has a stream."""

    def __init__(self, fetch, websocket, streams, clock=time.monotonic):
        self.fetch, self.websocket, self.streams, self.clock = fetch, websocket, streams, clock
        self.links, self.sources = {}, {}

    def prune(self):
        now = self.clock()
        for token in [t for t, link in self.links.items() if not link.streaming and now - link.used > LINK_SECONDS]:
            del self.links[token]

    def link(self, entity, box, cover=False):
        """A new link's token: the full view's (`box` its room), or a live tile's (`box` its card, `cover` when its
        picture fills the card rather than showing whole)."""
        self.prune()
        token = secrets.token_urlsafe(18)
        self.links[token] = Link(entity, box, self.clock(), cover)
        return token

    def streaming(self):
        return sum(link.streaming for link in self.links.values())

    def source(self, entity):
        source = self.sources.get(entity)
        if source is None or (source.task and source.task.done() and not source.viewers):
            source = self.sources[entity] = Source(self, entity, self.streams(entity))
        return source

    async def serve(self, request, token):
        from aiohttp import web
        link = self.links.get(token)
        if link is None:
            return web.Response(status=404, text='Unknown link')
        if self.streaming() >= MAX_STREAMS:
            return web.Response(status=503, text='Too many live cameras')
        link.streaming += 1
        source = self.source(link.entity)
        source.viewers += 1
        source.idle_since = None
        source.start()
        response = web.StreamResponse(headers={'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
                                               'Cache-Control': 'no-cache'})
        sent = size = 0
        began = self.clock()
        try:
            await response.prepare(request)
            sock = request.transport.get_extra_info('socket') if request.transport else None
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SEND_BUFFER)
            last = 0
            while True:
                frame = await source.next(last, FRAME_SECONDS)
                if frame is None or request.transport is None:
                    break
                last = frame.number
                jpeg = await source.picture(frame, link.box, link.cover)
                if not jpeg:
                    continue
                await response.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n' % len(jpeg)
                                     + jpeg + b'\r\n')
                if not sent:
                    LOG.info('Live %s: first picture %.1f s after the link went out (the screen came %.1f s after it); '
                             'its source: %s', link.entity, self.clock() - link.made, began - link.made,
                             ', '.join(f'{what} {at:.1f} s' for what, at in sorted(source.marks.items(), key=lambda m: m[1]))
                             or 'running already')
                sent += 1
                size += len(jpeg)
                # The next picture is made once this one has left this host: the newest, never a queue of old ones.
                while request.transport is not None and request.transport.get_write_buffer_size():
                    await asyncio.sleep(0.005)
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            link.streaming -= 1
            link.used = self.clock()
            source.viewers -= 1
            if not source.viewers:
                source.idle_since = time.monotonic()
            seconds = max(0.001, self.clock() - began)
            LOG.info('Live %s (%s): %d pictures in %.0f s, %.1f a second, %d KB a picture, %.1f ms CPU to make one',
                     link.entity, source.route, sent, seconds, sent / seconds, size // max(1, sent) // 1024,
                     source.made_ms / max(1, source.made))
        return response
