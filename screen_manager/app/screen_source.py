"""A screen's own camera as a source of live pictures (docs/CALLS.md, "Media"): the add-on reads the screen's RTSP server
itself (Screen camera's Video, H.264 over TCP), straight from the screen, without Home Assistant's go2rtc and WebRTC in the
way, and gets its pictures out as any camera's (camera_source.Source: decoded here, JPEG for the receiving glass). Video
only: the screen encodes no Opus for a call, the voice goes up its own path (talk_uplink.h, talk_bridge.Voice).

An entity `screen:<node>` is such a source; `urls` (set by Manager, or a bench) says where its RTSP lives.
"""
import asyncio
import hashlib
import logging
import threading
import time

import camera_source

LOG = logging.getLogger(__name__)

PREFIX = 'screen:'
PASSWORD_SALT = 'tessera-video:'   # as Screen camera (its screen_video component) and Home Assistant's tessera_video
PASSWORD_LENGTH = 24
USER = 'tessera'
PORT = 8554
VOICE_PART = 640                   # 20 ms of 16 kHz samples
RETRY_SECONDS = 2                  # the stream broke and someone still watches
# FFmpeg's reader as short as it goes (a frame in, a frame out) over TCP, which the screen's server needs.
OPTIONS = {'rtsp_transport': 'tcp', 'allowed_media_types': 'video', 'fflags': 'nobuffer', 'flags': 'low_delay',
           'max_delay': '0', 'reorder_queue_size': '0', 'probesize': '65536', 'analyzeduration': '0', 'timeout': '5000000'}

urls = {}   # entity -> rtsp url (only for screen: and a bench's own names)


def rtsp_url(host, api_key):
    """The screen's stream: the password is worked out of its API key, as the firmware and tessera_video work it out."""
    password = hashlib.sha256((PASSWORD_SALT + (api_key or '')).encode()).hexdigest()[:PASSWORD_LENGTH]
    return f'rtsp://{USER}:{password}@{host}:{PORT}/'


def url_of(entity):
    return urls.get(entity)


class ScreenSource(camera_source.Source):
    """The newest picture of a screen's camera, and its voice for every screen that listens (the call's other end)."""

    def __init__(self, feed, entity, url):
        super().__init__(feed, entity, True)
        self.url, self.route = url, 'rtsp'
        self.stopped = threading.Event()
        self.frames = 0

    def voice(self, data):
        """A part of the screen's voice for whoever listens; a listener that fell behind loses its oldest part."""
        for queue in list(self.listeners):
            if queue.full():
                queue.get_nowait()
                self.sound_dropped += 1
            queue.put_nowait(data)

    def read(self, loop):
        """The screen's pictures on a thread of its own, one at a time: FFmpeg blocks while it reads."""
        import av
        container = av.open(self.url, options=dict(OPTIONS))
        try:
            stream = container.streams.video[0]
            stream.thread_count = 1
            first = True
            for frame in container.decode(stream):
                if self.stopped.is_set() or not self.watched():
                    return
                self.frames += 1
                if first:
                    self.mark('first')
                    first = False
                asyncio.run_coroutine_threadsafe(self.publish(video=frame), loop)
        finally:
            container.close()

    async def run(self):
        self.stopped.clear()
        loop = asyncio.get_running_loop()
        try:
            while self.watched() and not self.stopped.is_set():
                try:
                    await loop.run_in_executor(None, self.read, loop)
                except Exception as err:  # noqa: BLE001 - a screen that went away: try again while it is watched
                    LOG.warning('Live %s: %s', self.entity, err)
                    await asyncio.sleep(RETRY_SECONDS)
        finally:
            self.stopped.set()
            LOG.info('Live %s: read %d frames in all', self.entity, self.frames)

    def listen(self, queue):  # the voice comes from talk_bridge, no session of its own
        self.listeners.add(queue)

    def unlisten(self, queue):
        self.listeners.discard(queue)
