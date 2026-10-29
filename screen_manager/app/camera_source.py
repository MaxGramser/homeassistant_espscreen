"""What a camera gives (docs/CAMERA.md, "Live on the P4 boards"; docs/PICTURE_ARCHITECTURE.md, section 4): its newest
picture and its sound, for every screen that watches it live.

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
  the camera's still, each such part marked `X-Picture: still`: the screen turns a loader over it until the first part
  without the mark (live_view.h, "Until it is live"). A screen that knows no mark shows it as any picture.
- Any other camera (a snapshot camera, an ESPHome camera, a picture an integration draws) gives its snapshot, asked
  again as soon as the last came. A JPEG the P4 decodes as it is (baseline, at most MAX_SIDE a side) goes out untouched,
  which costs this app nothing; anything else is made into one.

One source per camera, shared by every screen that watches it; it stops a few seconds after the last one stops. What a
screen gets of a frame is live_pictures', how it travels live_stream's.

Every decoded WebRTC frame is looked at before a screen gets it (FrameWatch): one the decoder marks corrupt is left out
and the one before stays; a gap in the frames' timestamps, a frame much brighter than the one before and the one after
(a "flash"), the packets lost on the way, the NACKs and PLIs this app sent back and the frames live_pictures could not
make into a JPEG the screen takes are counted, and said every FRAME_REPORT_SECONDS when any is not 0. With the file
DUMP_MARK in Home Assistant's config folder, each flagged frame and the two before and after it are kept as JPEGs.
"""
import asyncio
import collections
import logging
import os
from pathlib import Path
import time

import catalogue
import live_pictures

LOG = logging.getLogger(__name__)


def webrtc_here():
    """Whether this install can take WebRTC at all (aiortc): without it a camera's snapshots never try it again."""
    try:
        import aiortc  # noqa: F401
    except ImportError:
        return False
    return True

LINGER_SECONDS = 5        # a camera nobody watches any more stops after this (a screen that asks again at once finds it)
SNAPSHOT_FPS = 15         # a camera without a stream is asked no more often than this
WEBRTC_FIRST_SECONDS = 20  # a WebRTC session without a frame by then gives way to the snapshots
WEBRTC_RETRY_SECONDS = 60  # a camera on its snapshots while watched tries WebRTC again this often
LAG_REPORT_SECONDS = 60   # how often a camera's WebRTC pictures say how far behind the camera they are (Lag)
STILL_SECONDS = 2          # the camera's still, again this often, until WebRTC's first frame (the screen's
                           # live_view::QUIET_MS closes a stream silent for 6 s)
SOUND_RATE = 16000        # a full view's sound: 16-bit mono at this rate (the board's resampler makes it its bus's)
# A camera with a stream of its own (CameraEntityFeature.STREAM, by its name in Home Assistant's source).
STREAM_FEATURE = catalogue.bits('camera', 'STREAM')
# The frame watch (FrameWatch): its line at most this often, only when something was counted, and its totals this often
# whatever they are, so a quiet log still says the watch runs.
FRAME_REPORT_SECONDS = 10
FRAME_TOTALS_SECONDS = 300
# A flash: the picture at least FLASH_RISE times as bright as before it (the median of its last frames) and FLASH_STEPS of
# 255 brighter, falling back at least halfway within FLASH_FRAMES frames. One frame or a second of them: Max saw the
# flash on every tile of the living room's camera at once (2026-10-28), and a camera's own jump of exposure lasts
# frames, not one. A change of light that stays (a lamp, the camera's night mode) is no flash.
FLASH_RISE, FLASH_STEPS, FLASH_FRAMES = 1.25, 8, 15
# A gap: frames this many times the usual step between their timestamps apart.
GAP_STEPS = 1.8
# Evidence, on the bench: with this file in Home Assistant's config folder each flagged frame, the two before and the two
# after it go to DUMP_DIR as JPEGs, at most DUMP_MOST files in all (the oldest go).
HA_CONFIG = Path(os.environ.get('HA_CONFIG', '/homeassistant'))
DUMP_MARK = HA_CONFIG / 'tessera_frame_dump'
DUMP_DIR = HA_CONFIG / 'tessera_diagnostics' / 'frames'
DUMP_MOST = 50


class Frame:
    """A camera's picture; `still` when it is the camera's still from before its stream came."""
    __slots__ = ('number', 'jpeg', 'video', 'at', 'still')

    def __init__(self, number, jpeg=None, video=None, still=False):
        self.number, self.jpeg, self.video, self.at, self.still = number, jpeg, video, time.monotonic(), still


class Lag:
    """How far a camera's pictures come behind the camera: the time since the first picture on this host's clock less
    the time since it on the camera's (a frame's `time`, which aiortc starts at 0 with the first frame). A frame that
    came ahead of the first one's pace (the camera's timestamps jumped, as after a new key frame) starts the count again.
    Measured first, before anything acts on it: whether the pictures fall behind a screen over hours (2026-10-25, a
    D1001 with two live tiles, by eye), and where (`waiting`: decoded frames aiortc holds for this app)."""

    def __init__(self, clock=time.monotonic):
        self.clock, self.origin, self.seen, self.reported = clock, None, [], clock()

    def feed(self, at):
        """The seconds behind the camera of a frame of camera time `at`."""
        now = self.clock()
        if self.origin is None:
            self.origin = (now, at)
        behind = (now - self.origin[0]) - (at - self.origin[1])
        if behind < 0:
            self.origin, behind = (now, at), 0.0
        self.seen.append(behind)
        return behind

    def report(self):
        """(average, most, pictures) since the last report once LAG_REPORT_SECONDS went by, else None."""
        if not self.seen or self.clock() - self.reported < LAG_REPORT_SECONDS:
            return None
        seen, self.seen, self.reported = self.seen, [], self.clock()
        return sum(seen) / len(seen), max(seen), len(seen)


def luma(frame):
    """The mean brightness (0 to 255) of a decoded frame, from a grid of 40 x 24 of its pixels: swscale picks them in grey,
    without RGB and without numpy (0.05 ms for 1080p)."""
    small = frame.reformat(width=40, height=24, format='gray', interpolation='POINT')
    plane = small.planes[0]
    data, stride = bytes(plane), plane.line_size
    return sum(sum(data[row * stride:row * stride + 40]) for row in range(24)) / 960


class FrameDump:
    """The JPEGs of a flagged moment (DUMP_DIR/<entity>/<pts>.jpg): a corrupt frame or a flash, with the two frames before
    it and the two after it, made in a thread of their own, at most DUMP_MOST files in all. Every frame is kept as a copy
    of THUMB_WIDTH pixels wide while the dump is on, so a flash of a second of 1080p does not hold seconds of 1080p."""

    THUMB_WIDTH = 480

    def __init__(self, entity, folder=None, most=DUMP_MOST):
        self.folder = Path(folder or DUMP_DIR) / entity.replace('.', '_')
        self.most, self.recent, self.after = most, collections.deque(maxlen=FLASH_FRAMES + 4), 0

    def frame(self, frame, flagged=0):
        """Every frame the watch keeps; `flagged` the number of frames up to this one that make the moment (1 for this
        frame alone): those and the two before them go out now, the two after them as they come."""
        try:
            width = min(self.THUMB_WIDTH, frame.width)
            thumb = frame.reformat(width=width, height=max(2, frame.height * width // frame.width // 2 * 2), format='rgb24')
        except Exception:  # noqa: BLE001 - only evidence
            return
        thumb.pts = frame.pts
        self.recent.append(thumb)
        if flagged:
            self.write(list(self.recent)[-(flagged + 2):])
            self.after = 2
        elif self.after:
            self.after -= 1
            self.write([thumb])

    def write(self, frames):
        def save():
            self.folder.mkdir(parents=True, exist_ok=True)
            for each in frames:
                each.to_image().save(self.folder / f'{each.pts if each.pts is not None else id(each)}.jpg', 'JPEG', quality=90)
            files = sorted(self.folder.parent.glob('*/*.jpg'), key=lambda path: path.stat().st_mtime)
            for old in files[:max(0, len(files) - self.most)]:
                old.unlink(missing_ok=True)
        task = asyncio.get_running_loop().run_in_executor(None, save)
        task.add_done_callback(lambda done: done.exception() and LOG.warning('Live frame dump failed: %s', done.exception()))


class FrameWatch:
    """Every decoded frame of a camera's WebRTC before a screen gets it (Max saw a white flash on a live tile now and then,
    2026-10-28): `feed` says whether to show it. A frame the decoder marks corrupt is left out and counted; a gap in the
    timestamps, a flash (FLASH_RISE) and the key frames are counted; `line` says it all every FRAME_REPORT_SECONDS when
    any of it is not 0, with the transport's packets lost, NACKs, PLIs and live_pictures' JPEGs the screen would refuse."""

    COUNTS = ('frames', 'corrupt', 'gaps', 'flashes', 'keys', 'lost', 'nacks', 'plis', 'refused', 'stills', 'not_turned')

    def __init__(self, entity, clock=time.monotonic, brightness=luma, dump=None):
        self.entity, self.clock, self.brightness, self.dump = entity, clock, brightness, dump
        self.now = dict.fromkeys(self.COUNTS, 0)
        self.total = dict.fromkeys(self.COUNTS, 0)
        self.last_pts, self.steps = None, collections.deque(maxlen=30)
        # The brightness of the last frames before any flash, and the flash going on: {'pts', 'base', 'peak', 'frames',
        # 'key'} from its first bright frame.
        self.calm, self.bright = collections.deque(maxlen=8), None
        self.reported = self.totaled = clock()

    def count(self, what, n=1):
        self.now[what] += n
        self.total[what] += n

    def feed(self, frame):
        """True to show `frame`; False for a corrupt one (the screen keeps the one before)."""
        self.count('frames')
        corrupt, key = bool(getattr(frame, 'is_corrupt', False)), bool(getattr(frame, 'key_frame', False))
        pts = getattr(frame, 'pts', None)
        if key:
            self.count('keys')
        if pts is not None and self.last_pts is not None and pts > self.last_pts:
            step = pts - self.last_pts
            usual = sorted(self.steps)[len(self.steps) // 2] if len(self.steps) >= 5 else None
            if usual and step > GAP_STEPS * usual:
                self.count('gaps', max(1, round(step / usual) - 1))
            else:
                self.steps.append(step)
        if pts is not None:
            self.last_pts = pts
        if corrupt:
            self.count('corrupt')
            LOG.info('Live %s: corrupt frame left out (pts %s%s)', self.entity, pts, ', a key frame' if key else '')
            if self.dump:
                self.dump.frame(frame, flagged=1)
            return False
        try:
            y = self.brightness(frame)
        except Exception:  # noqa: BLE001 - only for the count: the frame is shown whatever happens here
            return True
        flagged = 0
        flash = self.bright
        if flash is None:
            base = sorted(self.calm)[len(self.calm) // 2] if len(self.calm) >= 3 else None
            if base is not None and y >= base * FLASH_RISE and y - base >= FLASH_STEPS:
                self.bright = {'pts': pts, 'base': base, 'peak': y, 'frames': 1, 'key': key}
            else:
                self.calm.append(y)
        else:
            flash['frames'] += 1
            flash['peak'] = max(flash['peak'], y)
            if y <= flash['base'] + (flash['peak'] - flash['base']) / 2:
                self.count('flashes')
                flagged = flash['frames']  # its bright frames and this one it fell back on
                LOG.warning('Live %s: a flash at pts %s%s, %d frame(s): brightness %.0f, up to %.0f, then %.0f', self.entity,
                            flash['pts'], ', a key frame' if flash['key'] else '', flash['frames'] - 1, flash['base'],
                            flash['peak'], y)
                self.bright = None
                self.calm.append(y)
            elif flash['frames'] > FLASH_FRAMES:
                # The light changed and stays: the new light is calm.
                self.bright = None
                self.calm.clear()
                self.calm.append(y)
        if self.dump:
            self.dump.frame(frame, flagged=flagged)
        return True

    def due(self):
        return self.clock() - self.reported >= FRAME_REPORT_SECONDS

    def line(self, lost=0, nacks=0, plis=0, refused=0, stills=0, not_turned=0):
        """The report since the last one once FRAME_REPORT_SECONDS went by, when anything but frames was counted (and
        the totals every FRAME_TOTALS_SECONDS whatever they are); None otherwise. The transport's and the JPEGs' counts
        are handed in as totals since the session began."""
        now = self.clock()
        for what, value in (('lost', lost), ('nacks', nacks), ('plis', plis), ('refused', refused), ('stills', stills),
                            ('not_turned', not_turned)):
            if value > self.total[what]:
                self.count(what, value - self.total[what])
        if now - self.reported < FRAME_REPORT_SECONDS:
            return None
        counts, self.now, self.reported = self.now, dict.fromkeys(self.COUNTS, 0), now
        if now - self.totaled >= FRAME_TOTALS_SECONDS:
            self.totaled = now
            return f'Live {self.entity}: {self.words(self.total)} since the stream began'
        if not any(counts[what] for what in self.COUNTS if what not in ('frames', 'keys')):
            return None
        return f'Live {self.entity}: {self.words(counts)} in {FRAME_REPORT_SECONDS} s'

    @staticmethod
    def words(c):
        return (f"{c['frames']} frames ({c['keys']} key), {c['corrupt']} corrupt, {c['gaps']} missing, {c['flashes']} flashes; "
                f"{c['lost']} packets lost, {c['nacks']} NACKs and {c['plis']} PLIs sent; {c['refused']} JPEGs the screen "
                f"would refuse, {c['stills']} stills" + (f", {c['not_turned']} pictures not turned for a turned glass"
                                                          if c['not_turned'] else ''))


class Source:
    """The newest picture of one camera, for every screen that watches it."""

    def __init__(self, feed, entity, streams):
        self.feed, self.entity, self.streams = feed, entity, streams
        self.frame, self.number, self.viewers = None, 0, 0
        self.changed = asyncio.Condition()
        self.task, self.idle_since = None, None
        self.route = 'snapshot'
        # When the way to the first picture went by, in seconds after the source started (the log of the first picture).
        self.started, self.marks = time.monotonic(), {}
        # The screens that listen to the camera's sound (a queue each), its WebRTC session of its own, and whether the
        # pictures' session brings it along (a screen with a speaker watches: `wants_sound`).
        self.listeners, self.sound, self.quiet_since = set(), None, None
        self.wants_sound = self.sound_along = False
        self.resampler = None
        self.sound_dropped = 0  # parts of sound a listener's full queue lost since the last report (Lag)
        self.watch, self.stills = None, 0  # the frame watch of its WebRTC pictures; the stills among them
        self.webrtc_tries = 0  # WebRTC sessions that gave no frame since it last did, while watched (run)
        self.snapshots_since = None  # when its snapshots took over from WebRTC

    def mark(self, what):
        self.marks.setdefault(what, time.monotonic() - self.started)

    async def publish(self, jpeg=None, video=None, still=False):
        # A still after the stream's first frame would stand between live pictures: counted (the frame watch says it).
        self.stills += bool(still and self.watch is not None and self.watch.total['frames'])
        self.number += 1
        self.frame = Frame(self.number, jpeg, video, still)
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

    def start(self):
        if self.task is None or self.task.done():
            self.started, self.marks = time.monotonic(), {}
            self.task = asyncio.create_task(self.run())

    async def run(self):
        """Pictures while anyone watches: WebRTC for a camera with a stream, its still until the first frame and if
        WebRTC fails; snapshots for any other camera. A camera whose WebRTC gave no frame sends its snapshots and tries
        WebRTC again every WEBRTC_RETRY_SECONDS while it is watched: a camera back from its privacy mode, or a go2rtc that
        came back, plays live again without anyone closing it."""
        try:
            if not self.streams or not webrtc_here():
                await self.snapshots()
                return
            self.webrtc_tries = 0
            while not await self.webrtc():
                self.webrtc_tries += 1
                if self.webrtc_tries == 1:
                    self.snapshots_since = time.monotonic()
                if not await self.snapshots(until=time.monotonic() + WEBRTC_RETRY_SECONDS):
                    return
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - a camera that fails ends its streams; screens ask again
            LOG.warning('Live %s ended: %s', self.entity, error)

    def watched(self):
        return self.viewers > 0 or (self.idle_since and time.monotonic() - self.idle_since < LINGER_SECONDS)

    async def snapshots(self, until=None, stop=None):
        """The camera's snapshots while it is watched, or `until` that time: True when it stopped for `until`. With
        `stop`, until that event: the snapshots of a camera that tries WebRTC again go on until its first frame."""
        if stop is None:
            self.route = 'snapshot'
        failures = 0
        while self.watched() and not (stop and stop.is_set()):
            if until is not None and time.monotonic() >= until:
                return True
            started = time.monotonic()
            try:
                raw = await self.feed.fetch(self.entity)
                failures = 0
                if raw and not (stop and stop.is_set()):
                    await self.publish(jpeg=raw)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - tried again, a little later each time
                failures += 1
                if failures == 1:
                    LOG.info('Live %s: no snapshot (%s)', self.entity, type(error).__name__)
                await asyncio.sleep(min(10, failures))
            await asyncio.sleep(max(0.0, 1 / SNAPSHOT_FPS - (time.monotonic() - started)))
        return False

    async def webrtc(self):
        """Home Assistant's WebRTC of the camera's pictures until nobody watches; False when it gave no frame (no WebRTC
        here, no aiortc in this install, a camera go2rtc cannot relay): the snapshots take over. The camera's stills go
        first: WebRTC waits for the camera's next key frame."""
        first = asyncio.Event()
        # Until its first frame: the camera's still every STILL_SECONDS, or on a try again its snapshots as they went.
        still = asyncio.create_task(self.snapshots(stop=first) if self.webrtc_tries else self.stills_until(first))

        async def take(kind, frame):
            if kind == 'audio':
                self.heard(frame)
                return
            self.mark('first WebRTC frame')
            if not first.is_set() and self.webrtc_tries:
                LOG.info('Live %s: WebRTC works again at try %d, after %.0f s of snapshots', self.entity,
                         self.webrtc_tries + 1, time.monotonic() - self.snapshots_since)
            first.set()
            if self.watch.feed(frame):
                await self.publish(video=frame)
        try:
            self.route = 'webrtc'
            self.watch = FrameWatch(self.entity, dump=FrameDump(self.entity) if DUMP_MARK.exists() else None)
            live_pictures.refused.pop(self.entity, None)
            live_pictures.not_turned.pop(self.entity, None)
            self.stills = 0
            # The sound along in the same session when a screen with a speaker watches: the full view has it at once.
            self.sound_along = self.wants_sound
            # A session of the sound's own (hear, started by a listener while the pictures went without sound: a tile,
            # then the full view) ends now: with both, every listener got the sound twice, shifted, and heard small
            # snippets out of joint (a Guition 10.1 showing a reTerminal D1001 full screen, 2026-10-29).
            if self.sound_along and self.sound is not None and not self.sound.done():
                self.sound.cancel()
            # A try again after the first says nothing of its failure: the log said it once, and says it works again.
            return await self.rtc(('video', 'audio') if self.sound_along else ('video',), take, self.watched,
                                  quiet=self.webrtc_tries > 0)
        finally:
            self.sound_along = False
            still.cancel()
            # The sound went along with this session: listeners that stay get a session of the sound's own again.
            if self.listeners and self.streams and (self.sound is None or self.sound.done()):
                self.sound = asyncio.create_task(self.hear())

    async def rtc(self, kinds, take, keep, quiet=False):
        """One WebRTC session of Home Assistant's for the camera's `kinds` ('video', 'audio'): `take(kind, frame)` for
        each frame while `keep()`. False when no frame of the first kind came within WEBRTC_FIRST_SECONDS or the session
        could not start; `quiet` leaves out the log line that says so."""
        try:
            from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
            from aiortc.sdp import candidate_from_sdp
        except ImportError:
            return False
        kind = kinds[0]
        first = asyncio.Event()
        # No STUN server: this app and Home Assistant share a network (the Supervisor's, or the LAN), where the host's
        # own addresses reach each other. aiortc asks Google's STUN server by default and the offer waited for its answer,
        # about five seconds on a LAN without one, before every live camera started (2026-10-20, a full view and a tile).
        connection = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        for each in kinds:
            connection.addTransceiver(each, direction='recvonly')
        pulls = []
        # The pictures' session counts what its receiver asks back: NACKs (the packets it lost) and PLIs (a new key frame
        # after a loss it could not mend; aiortc's jitter buffer asks one), through aiortc's own two senders.
        watch = self.watch if kind == 'video' else None
        asked = {'nacks': 0, 'plis': 0}
        receiver = connection.getTransceivers()[0].receiver if watch else None
        if receiver is not None:
            send_nack, send_pli = receiver._send_rtcp_nack, receiver._send_rtcp_pli

            async def nack(media_ssrc, lost):
                asked['nacks'] += len(lost)
                await send_nack(media_ssrc, lost)

            async def pli(media_ssrc):
                asked['plis'] += 1
                await send_pli(media_ssrc)
            receiver._send_rtcp_nack, receiver._send_rtcp_pli = nack, pli

        @connection.on('track')
        def on_track(track):
            if track.kind not in kinds:
                return

            async def pull():
                lag = Lag()
                while True:
                    frame = await track.recv()
                    if track.kind == kind:
                        first.set()
                    # The sound measured as the pictures are: both behind together is this app (its loop) slow, the
                    # pictures alone behind is the host's H.264 decoder. The sound is never skipped.
                    if frame.time is not None:
                        lag.feed(frame.time)
                        told = lag.report()
                        if told:
                            # aiortc's own queue of decoded frames, read for the log alone (no public way to it).
                            waiting = getattr(track, '_queue', None)
                            dropped = ''
                            if track.kind == 'audio':
                                dropped = f'; {self.sound_dropped} parts dropped for a screen that fell behind'
                                self.sound_dropped = 0
                            LOG.info('Live %s %s: %.2f s behind the camera on average, %.2f s at most, over %d frames; '
                                     '%s decoded waiting%s', self.entity, 'video' if track.kind == 'video' else 'sound',
                                     *told, waiting.qsize() if waiting is not None else '?', dropped)
                    await take(track.kind, frame)
            pulls.append(asyncio.create_task(pull()))

        try:
            await connection.setLocalDescription(await connection.createOffer())
            if kind == 'video':
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
                            if kind == 'video':
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
                arrived = asyncio.create_task(first.wait())
                try:
                    # The first frame, or the end of the session before it: Home Assistant refuses the offer of a
                    # camera without WebRTC at once (a camera with HLS alone), and the snapshots take over then, not
                    # after WEBRTC_FIRST_SECONDS.
                    await asyncio.wait((arrived, listening), timeout=WEBRTC_FIRST_SECONDS,
                                       return_when=asyncio.FIRST_COMPLETED)
                    if not first.is_set():
                        why = ended(listening) or f'nothing in {WEBRTC_FIRST_SECONDS} s'
                        if not quiet:
                            LOG.info('Live %s: no WebRTC %s (%s); its snapshots meanwhile, WebRTC again every %d s',
                                     self.entity, kind, why, WEBRTC_RETRY_SECONDS)
                        return False
                    while keep() and not listening.done() and all(not p.done() for p in pulls):
                        await asyncio.sleep(1)
                        if watch is not None:
                            await self.watch_report(watch, receiver, asked)
                    why = ended(listening)
                    if why:
                        LOG.info('Live %s: WebRTC %s ended (%s)', self.entity, kind, why)
                    return True
                finally:
                    arrived.cancel()
                    listening.cancel()
        except (ConnectionError, OSError, asyncio.TimeoutError) as error:
            if not quiet:
                LOG.info('Live %s: no WebRTC %s (%s); its snapshots meanwhile, WebRTC again every %d s', self.entity,
                         kind, error, WEBRTC_RETRY_SECONDS)
            return False
        finally:
            for task in pulls:
                ended(task)
                task.cancel()
            await connection.close()

    async def watch_report(self, watch, receiver, asked):
        """The frame watch's line when one is due, with the packets the receiver lost (its inbound-rtp stats)."""
        if not watch.due():
            return
        lost = 0
        try:
            for stats in (await receiver.getStats()).values():
                if getattr(stats, 'type', None) == 'inbound-rtp':
                    lost += max(0, getattr(stats, 'packetsLost', 0) or 0)
        except Exception:  # noqa: BLE001 - the stats only for the log
            pass
        told = watch.line(lost=lost, nacks=asked['nacks'], plis=asked['plis'], refused=live_pictures.refused.get(self.entity, 0),
                          stills=self.stills, not_turned=live_pictures.not_turned.get(self.entity, 0))
        if told:
            LOG.info('%s', told)

    # ---- The camera's sound, for a full view with a speaker: 16-bit mono at SOUND_RATE, in parts as it comes ----
    def listening(self):
        return bool(self.listeners) or (self.quiet_since and time.monotonic() - self.quiet_since < LINGER_SECONDS)

    def listen(self, queue):
        self.listeners.add(queue)
        self.quiet_since = None
        # Sound that comes along with the pictures already needs no session of its own.
        if self.streams and not self.sound_along and (self.sound is None or self.sound.done()):
            self.sound = asyncio.create_task(self.hear())

    def heard(self, frame):
        """A frame of the camera's sound, made 16-bit mono at SOUND_RATE and handed to every listener; a listener that
        falls behind loses its oldest part. Nobody listening: dropped."""
        if not self.listeners:
            return
        if self.resampler is None:
            import av
            self.resampler = av.AudioResampler(format='s16', layout='mono', rate=SOUND_RATE)
        for out in self.resampler.resample(frame):
            data = bytes(out.planes[0])[:out.samples * 2]
            for queue in list(self.listeners):
                if queue.full():
                    queue.get_nowait()
                    self.sound_dropped += 1
                queue.put_nowait(data)

    def unlisten(self, queue):
        self.listeners.discard(queue)
        if not self.listeners:
            self.quiet_since = time.monotonic()

    async def hear(self):
        """The camera's sound through Home Assistant's WebRTC (a session of its own, only while someone listens),
        made 16-bit mono at SOUND_RATE and handed to every listener; a listener that falls behind loses its oldest."""
        async def take(kind, frame):
            self.heard(frame)
        try:
            await self.rtc(('audio',), take, self.listening)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - no sound, the pictures go on
            LOG.info('Live %s: no sound (%s)', self.entity, error)

    async def stills_until(self, first):
        """The camera's still, again every STILL_SECONDS, until WebRTC's first frame. A single still left the screen
        without a byte while a camera took longer for its key frame than the screen waits (live_view::QUIET_MS): it
        closed the stream, went black and asked again, over and over."""
        while not first.is_set():
            started = time.monotonic()
            try:
                raw = await self.feed.fetch(self.entity)
                self.mark('still')
                if raw and not first.is_set():
                    await self.publish(jpeg=raw, still=True)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - only the pictures before the stream's; the next is tried
                pass
            await asyncio.sleep(max(0.0, STILL_SECONDS - (time.monotonic() - started)))


def ended(task):
    """What ended a finished task (its exception, read so asyncio never logs it as never retrieved); None while it runs,
    when it was cancelled or ended without one."""
    if not task.done() or task.cancelled():
        return None
    return task.exception()
