"""How a live camera travels to a screen (docs/CAMERA.md, "Live on the P4 boards"; docs/PICTURE_ARCHITECTURE.md,
section 4).

A P4 screen opens a camera full screen and asks for it with `live`: the room below its top bar, "1280x728". This app
answers with a link on its camera port, `/camera/<token>.mjpeg`: a stream of baseline JPEGs (multipart/x-mixed-replace,
one picture a part with its Content-Length). The screen decodes each in its hardware JPEG decoder and its PPA scales it
to fill that room, so this app never makes a picture larger than the camera's own, and every picture is the newest the
camera gave when the screen had taken the last one: a slow Wi-Fi gets fewer pictures, never older ones.

The pictures come from the camera's source (camera_source), made for the screen's room (live_pictures). Here are the
links on the camera port, the stream each serves with the camera's sound beside its pictures, and the pace a camera tile
set to Live is sent.
"""
import asyncio
import logging
import re
import secrets
import socket
import time

import camera_source
import live_pictures

LOG = logging.getLogger(__name__)

MAX_STREAMS = 8           # streams at once: a page of live tiles and a camera full screen, of every screen together
LINK_SECONDS = 60         # a link nobody opened for this long goes; a stream keeps its link while it runs
FRAME_SECONDS = 15        # nothing new from the camera for this long: the stream ends and the screen asks again
DEFAULT_PACE = 15         # picture_sources.TILE_PACE: the pace of a camera tile on a screen that does not stream
SOUND_QUEUE = 50          # parts of sound that may wait for a screen (about a second); older ones go
SEND_BUFFER = 65536       # what may wait in this host's socket for a screen: a picture, not a queue of them
REFUSAL_LOG_SECONDS = 60  # a refused tile asks again within seconds: the log says each screen's camera once a minute
ROOM = re.compile(r'(\d{2,4})x(\d{2,4})')  # a link made before its screen asked: the room its stream says, ?room=WxH


def room_of(text):
    """(w, h) of a stream's `?room=WxH`, each 64 to 4096; None for anything else."""
    found = ROOM.fullmatch(text or '')
    if not found:
        return None
    w, h = int(found[1]), int(found[2])
    return (w, h) if 64 <= w <= 4096 and 64 <= h <= 4096 else None
# A live tile's pictures are a few KB, so the full view's buffer held a dozen of them for a screen that read slower than
# its camera, and the screen's own TCP window as many again: a tile showed pictures a second or two old (a reTerminal
# D1001, 2026-10-28, X-Made). Its link keeps two or three of them here; the screen shows the newest of what reached it.
TILE_SEND_BUFFER = 16384
# A live tile on firmware that asks for each picture (pull, below): an ask waits this long for a frame newer than the one
# its link had, then answers 204 and the screen asks again; a link nobody asked for this long after its last answer
# lets its camera go, as a stream that ended.
PULL_SECONDS = 2.0
PULL_LEASE = 3.0
# What a screen that streams says in its hello (live_view.h): a camera tile set to Live, pace 0, streams there, and Live
# is the default pace of its camera tiles.
SCREEN_FEATURE = 'live'
LIVE_PACE = 0


def made():
    """X-Made of a picture or a piece of sound: this host's clock in ms as it leaves for the screen (wrapping at 2^32),
    which the screen sets beside its own to see how long its pictures and sound wait on the way (live_view.cpp)."""
    return int(time.monotonic() * 1000) & 0xFFFFFFFF


def part_head(content_type, length, still=False, turn=0):
    """The head of one part of a stream: its type, whether it is a camera's still from before its stream came, how its
    picture is turned for a turned glass (X-Turn, live_pictures.TURNS), its length and its X-Made."""
    return b'--frame\r\nContent-Type: %s\r\n%s%sContent-Length: %d\r\nX-Made: %d\r\n\r\n' % (
        content_type, b'X-Picture: still\r\n' if still else b'', b'X-Turn: %d\r\n' % turn if turn else b'', length,
        made())


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


class Link:
    __slots__ = ('entity', 'box', 'used', 'streaming', 'made', 'cover', 'sound', 'warm', 'screen', 'tile', 'turn',
                 'pulled', 'until', 'lease', 'held', 'began', 'sent', 'size')

    def __init__(self, entity, box, now, cover=False, sound=False, warm=False, screen=None, tile=False, turn=0):
        self.entity, self.box, self.used, self.streaming, self.made = entity, box, now, 0, now
        self.cover, self.sound, self.warm, self.screen, self.tile = cover, sound, warm, screen, tile
        # A screen whose glass is turned and that takes its live pictures so (caps picture_turn): they go out turned.
        self.turn = turn if turn in live_pictures.TURNS else 0
        # Pulled one picture an ask (LiveFeed.pull): the frame it had last, until when its lease runs, the task that ends
        # it, the cameras it holds, and its count for the log.
        self.pulled, self.until, self.lease, self.held, self.began, self.sent, self.size = 0, 0.0, None, [], now, 0, 0


class LiveFeed:
    """The live links and their sources. `fetch(entity)` is a snapshot (the app's own camera_proxy fetch),
    `websocket()` an authenticated websocket of Home Assistant (an async context manager), `streams(entity)` whether
    the camera has a stream."""

    def __init__(self, fetch, websocket, streams, clock=time.monotonic, live_tiles=None, screen_name=None):
        self.fetch, self.websocket, self.streams, self.clock = fetch, websocket, streams, clock
        # `live_tiles(screen)`: how many live tiles that screen streams at once, from its hello (the firmware's
        # picture_engine::limits, the app's page_delivery.caps_of), or None for a screen that did not say (an older
        # firmware, which keeps its own count). `screen_name(screen)`: the name the log gives a screen.
        self.live_tiles = live_tiles or (lambda screen: None)
        self.screen_name = screen_name or (lambda screen: screen)
        self.links, self.sources = {}, {}
        # When the log last said a refusal, by screen, camera and why (REFUSAL_LOG_SECONDS).
        self.refusals_said = {}
        # Each source's pictures (live_pictures.Pictures), made once per frame and room for every screen that watches it.
        self.pictures = {}

    def prune(self):
        now = self.clock()
        for token in [t for t, link in self.links.items() if not link.streaming and now - link.used > LINK_SECONDS]:
            del self.links[token]

    def link(self, entity, box, cover=False, sound=False, warm=False, screen=None, tile=False, turn=0):
        """A new link's token: the full view's (`box` its room, or None for a ring's link made as the event came,
        before the screen asked: its stream says the room, ?room=WxH; `sound` with the camera's sound for a screen with a
        speaker), or a live `tile`'s (`box` its card, `cover` when its picture fills the card rather than showing whole,
        `warm` when its screen has a speaker: the camera's sound comes along in the source, for the full view). `turn`:
        the glass's, for a screen that takes its live pictures turned so. `screen` is the inbox of the screen that
        asked."""
        self.prune()
        token = secrets.token_urlsafe(18)
        self.links[token] = Link(entity, box, self.clock(), cover, sound, warm, screen, tile, turn)
        return token

    def hold(self, link):
        """The cameras the live tiles of `link`'s screen showed until a moment ago, kept running while its full view
        streams: a screen stops its tiles' streams under a camera full screen, and they are back at once when it closes,
        rather than after the seconds a WebRTC session takes to start (2026-10-10, the D1001). For as long as the full
        view streams, as the tiles cost while they were on the glass; then the usual camera_source.LINGER_SECONDS."""
        now, held = self.clock(), []
        if link.tile or link.screen is None:
            return held
        for other in self.links.values():
            if not other.tile or other.screen != link.screen or other.entity == link.entity:
                continue
            if not other.streaming and now - other.used >= camera_source.LINGER_SECONDS:
                continue
            source = self.sources.get(other.entity)
            if source is None or source in held or source.task is None or source.task.done():
                continue
            source.viewers += 1
            source.idle_since = None
            held.append(source)
        return held

    def warm(self, entity):
        """A camera about to be watched (a ring's, whose screens open their links within a moment): its source starts
        now and lingers camera_source.LINGER_SECONDS for the first of them, so its first picture is on its way already."""
        source = self.source(entity)
        if not source.viewers:
            source.idle_since = time.monotonic()
        source.start()

    @staticmethod
    def let_go(held):
        for source in held:
            source.viewers -= 1
            if not source.viewers:
                source.idle_since = time.monotonic()

    def streaming(self):
        return sum(link.streaming for link in self.links.values())

    def usage(self):
        """The streams of every screen together against the most the app serves, for the editor's camera card."""
        return {'used': self.streaming(), 'most': MAX_STREAMS}

    def tiles_streaming(self, screen):
        """How many live tiles of `screen` stream now (the full view is not a tile)."""
        return sum(link.streaming for link in self.links.values() if link.tile and link.screen == screen)

    async def latest(self, entity, fresh=2.0):
        """The JPEG of a camera's newest frame while a stream of it runs (docs/PICTURES.md: one source per camera for
        stills and streams), at the camera's own size up to MAX_SIDE; None while none runs or its last frame is older than
        `fresh` seconds, and the caller takes Home Assistant's snapshot."""
        source = self.sources.get(entity)
        if source is None or source.task is None or source.task.done() or source.frame is None:
            return None
        frame = source.frame
        if time.monotonic() - frame.at > fresh:
            return None
        if frame.jpeg is not None:
            return frame.jpeg
        return (await self.pictures_of(entity).picture(frame, (live_pictures.MAX_SIDE, live_pictures.MAX_SIDE)))[0]

    def source(self, entity):
        source = self.sources.get(entity)
        if source is None or (source.task and source.task.done() and not source.viewers):
            source = self.sources[entity] = camera_source.Source(self, entity, self.streams(entity))
            self.pictures[entity] = live_pictures.Pictures()
        return source

    def pictures_of(self, entity):
        return self.pictures.setdefault(entity, live_pictures.Pictures(entity))

    def refused(self, link):
        """Why a stream of `link` may not start now (a text for 503), or None. The log says which screen's camera was
        refused and why, once a minute for each."""
        why = self.why_refused(link)
        if why:
            key, now = (link.screen, link.entity, why), self.clock()
            if now - self.refusals_said.get(key, -REFUSAL_LOG_SECONDS) >= REFUSAL_LOG_SECONDS:
                self.refusals_said[key] = now
                where = self.screen_name(link.screen) if link.screen is not None else 'a screen'
                LOG.info('Live %s refused for %s (%s): %s; %d of %d streams in use, of every screen', link.entity,
                         where, 'a tile' if link.tile else 'full screen', why, self.streaming(), MAX_STREAMS)
        return why

    def why_refused(self, link):
        """Why a stream of `link` may not start now, or None (refused says it)."""
        # A full view (a camera opened, a doorbell's ring) of a screen whose own live tiles still stream goes through:
        # the view covers those tiles, and they end the moment it opens. A ring on the bench Guition with four live tiles
        # and the D1001's own was refused here at its first ask, and its picture came 1.9 s after the view opened
        # instead of under one (2026-10-28, docs/PLATFORM_PLAN.md 4.9).
        if self.streaming() >= MAX_STREAMS and (link.tile or link.screen is None or not self.tiles_streaming(link.screen)):
            return 'Too many live cameras'
        # A screen's own count (picture_engine::limits, docs/PLATFORM_PLAN.md 4.1): its tile past the count is refused
        # here as the firmware refuses it there, so a screen whose firmware and app disagree never streams more than the
        # lower says.
        cap = self.live_tiles(link.screen) if link.tile and link.screen is not None else None
        if cap is not None and self.tiles_streaming(link.screen) >= cap:
            return f'This screen plays {cap} cameras live at once' if cap != 1 else 'This screen plays one camera live'
        return None

    def begin(self, link, sound=False):
        """A link starts to stream, by a screen's stream or its first ask for a picture: it counts as streaming, its
        camera runs and is held, and a full view holds the cameras of its screen's tiles. Its camera's source."""
        link.streaming += 1
        source = self.source(link.entity)
        source.wants_sound = source.wants_sound or sound or link.warm
        source.viewers += 1
        source.idle_since = None
        source.start()
        link.held, link.began, link.sent, link.size = self.hold(link), self.clock(), 0, 0
        return source

    def end(self, link, source, how):
        """A link's stream is over: what it held goes, and the log says what it sent (`how`: as a stream, or a picture
        an ask)."""
        link.streaming -= 1
        link.used = self.clock()
        self.let_go(link.held)
        link.held = []
        source.viewers -= 1
        if not source.viewers:
            source.idle_since = time.monotonic()
        seconds = max(0.001, self.clock() - link.began)
        jpegs = self.pictures_of(link.entity)
        LOG.info('Live %s (%s, %s): %d pictures in %.0f s, %.1f a second, %d KB a picture, %.1f ms CPU to make one',
                 link.entity, source.route, how, link.sent, seconds, link.sent / seconds,
                 link.size // max(1, link.sent) // 1024, jpegs.made_ms / max(1, jpegs.made))

    async def pull(self, request, token):
        """A live tile's next picture, one an ask over a kept connection (GET /camera/<token>.jpg on the same link as
        the stream; firmware that asks so, live_view.cpp): the JPEG of the camera's newest frame for its card once that
        is newer than the one the link had, or after PULL_SECONDS without one 204, and the screen asks again. Nothing
        waits between here and the screen, so its pictures are as new as the camera's, and the bytes are what it shows:
        a screen that asks less, by its own pace or a busy screen's, gets less. The first ask starts the link as a
        stream would (the same limits, the camera held, the tiles of its screen held), and the link counts as streaming
        until PULL_LEASE after its last answer."""
        from aiohttp import web
        link = self.links.get(token)
        if link is None:
            return web.Response(status=404, text='Unknown link')
        if link.lease is None:
            why = self.refused(link)
            if why:
                return web.Response(status=503, text=why)
            link.lease = asyncio.create_task(self.lease(link, self.begin(link)))
        source = self.sources[link.entity]
        source.start()  # again if its camera ended meanwhile, as a screen's new stream would
        link.until = self.clock() + PULL_SECONDS + PULL_LEASE
        frame = await source.next(link.pulled, PULL_SECONDS)
        jpeg, turn = await self.pictures_of(link.entity).picture(frame, link.box, link.cover, link.turn) \
            if frame is not None else (None, 0)
        link.until = self.clock() + PULL_LEASE
        if not jpeg:
            return web.Response(status=204, headers={'Cache-Control': 'no-cache'})
        link.pulled = frame.number
        link.sent += 1
        link.size += len(jpeg)
        headers = {'Cache-Control': 'no-cache', 'X-Made': str(made())}
        if frame.still:
            headers['X-Picture'] = 'still'
        if turn:
            headers['X-Turn'] = str(turn)
        return web.Response(body=jpeg, content_type='image/jpeg', headers=headers)

    async def lease(self, link, source):
        """A pulled link's stream, from its first ask until PULL_LEASE after its last answer: then it lets its camera go
        as an ended stream does."""
        try:
            while self.clock() < link.until:
                await asyncio.sleep(min(0.5, max(0.05, link.until - self.clock())))
        finally:
            link.lease = None
            self.end(link, source, 'a picture an ask')

    async def serve(self, request, token):
        from aiohttp import web
        link = self.links.get(token)
        if link is None:
            return web.Response(status=404, text='Unknown link')
        why = self.refused(link)
        if why:
            return web.Response(status=503, text=why)
        if link.box is None:
            link.box = room_of(request.query.get('room'))
            if link.box is None:
                return web.Response(status=400, text='No room for its pictures (?room=WxH)')
        source = self.begin(link, sound=link.sound)
        jpegs = self.pictures_of(link.entity)
        response = web.StreamResponse(headers={'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
                                               'Cache-Control': 'no-cache'})
        writing = asyncio.Lock()
        sound = asyncio.Queue(maxsize=SOUND_QUEUE) if link.sound else None

        async def write(head, body):
            async with writing:
                await response.write(head + body + b'\r\n')

        async def pictures():
            last = 0
            while True:
                frame = await source.next(last, FRAME_SECONDS)
                if frame is None or request.transport is None:
                    return
                last = frame.number
                jpeg, turn = await jpegs.picture(frame, link.box, link.cover, link.turn)
                if not jpeg:
                    continue
                await write(part_head(b'image/jpeg', len(jpeg), frame.still, turn), jpeg)
                if not link.sent:
                    LOG.info('Live %s: first picture %.1f s after the link went out (the screen came %.1f s after it); '
                             'its source: %s', link.entity, self.clock() - link.made, link.began - link.made,
                             ', '.join(f'{what} {at:.1f} s' for what, at in sorted(source.marks.items(), key=lambda m: m[1]))
                             or 'running already')
                link.sent += 1
                link.size += len(jpeg)
                # The next picture is made once this one has left this host: the newest, never a queue of old ones.
                while request.transport is not None and request.transport.get_write_buffer_size():
                    await asyncio.sleep(0.005)

        async def sounds():
            # As it comes, a few parts at once: the sound never waits for a picture's turn.
            while True:
                data = await sound.get()
                while not sound.empty() and len(data) < 3200:
                    data += sound.get_nowait()
                await write(part_head(b'audio/x-s16le;rate=%d' % camera_source.SOUND_RATE, len(data)), data)

        listening = None
        try:
            await response.prepare(request)
            sock = request.transport.get_extra_info('socket') if request.transport else None
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, TILE_SEND_BUFFER if link.tile else SEND_BUFFER)
            if sound is not None:
                source.listen(sound)
                listening = asyncio.create_task(sounds())
            await pictures()
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if listening is not None:
                listening.cancel()
                source.unlisten(sound)
            self.end(link, source, 'a stream')
        return response
