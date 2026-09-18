"""Camera images on a Guition screen (app 0.2.66, firmware 0.2.57).

A screen never asks Home Assistant for a camera itself. This app fetches the snapshot with its own token (a
camera's access token changes every five minutes), makes it exactly as large as the screen shows it and serves
it as an uncompressed 24-bit BMP on its own port on the LAN, where the screen's ESPHome `online_image` loads it.
ESPHome decodes a BMP piece by piece while it downloads; a JPEG of the full screen held the Guition's main loop for
0.6 s (measured 2026-09-17), long enough to lose a tap. On the LAN the larger file costs nothing that matters.

Links are random and short-lived, and only a camera on the screen's layout or in a recent alert gets one. A screen
that loads a link gets the last snapshot at once, however long the camera takes to answer (ESPHome's HTTP client waits
in the screen's main loop, where touch and drawing wait with it), and the load starts fetching the next snapshot.
"""
import asyncio
import hashlib
import io
import logging
import os
import re
import secrets
import time

from core import screen_firmware

LOG = logging.getLogger(__name__)

DOMAINS = ('camera', 'image')
MIN_FIRMWARE = (0, 2, 57)
# Album covers on the media card (app 0.2.77, firmware 0.2.64): the same port serves a media player's picture, square,
# at the size the screen asks for, with the rounded corners baked in over the colour the screen names (the card's
# page or the tile's own colour), so the screen draws it as it is. A cover is fetched when the screen loads its link
# and again only when Home Assistant's picture changes; the screen asks for a new link then.
COVER_DOMAINS = ('media_player',)
COVER_MIN_FIRMWARE = (0, 2, 64)
COVER_SIZES = (48, 320)  # the smallest and largest cover a screen may ask for, in pixels
COVER_RADIUS_SHARE = 12  # the corner is a twelfth of the size, at least 4 px (media_card.h radius_for)
PORT = 8098
# A camera nobody loaded a picture of for this long is forgotten, its last snapshot with it.
WATCH_SECONDS = 30
# A link to a live camera nobody used for this long is forgotten; the screen asks for a new one.
LINK_SECONDS = 120
# An alert's still stays loadable this long, and its camera may be opened full screen that long.
STILL_SECONDS = 1800
FIRST_FRAME_SECONDS = 8
FETCH_SECONDS = 15
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_LINKS = 64
# What the screens load (online_image `format: BMP`).
CONTENT_TYPE = 'image/bmp'
# The pixel box per board and view; the image keeps its proportions inside it. Equal to the CAMERA_*
# substitutions of packages/guition.yaml (tests/test_camera.py).
BOXES = {
    'guition': {'full': (480, 480), 'thumb': (392, 220)},
    'jc8012p4a1': {'full': (1280, 800), 'thumb': (900, 506)},
}


def supported(entity):
    """True for a camera or image entity id."""
    return (isinstance(entity, str) and len(entity) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', entity) is not None
            and entity.split('.')[0] in DOMAINS)


def can_show(screen):
    """A paired Guition with firmware that draws camera images (the version feature gates go by, core.screen_firmware)."""
    return bool(screen) and screen.get('board') in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= MIN_FIRMWARE


def cover_supported(entity):
    """True for a media player entity id: its cover can be served."""
    return (isinstance(entity, str) and len(entity) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', entity) is not None
            and entity.split('.')[0] in COVER_DOMAINS)


def can_show_cover(screen):
    """A paired Guition with firmware that draws the media card's cover."""
    return bool(screen) and screen.get('board') in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= COVER_MIN_FIRMWARE


def cover_request(request):
    """(size, background) a screen asked for, or None when the request is not a cover request the app can serve:
    `size` in pixels within COVER_SIZES, `bg` six hex digits of the colour behind the corners."""
    try:
        size = int(request.get('size'))
    except (TypeError, ValueError):
        return None
    background = request.get('bg')
    if not COVER_SIZES[0] <= size <= COVER_SIZES[1] or not isinstance(background, str) or not re.fullmatch(r'[0-9A-Fa-f]{6}', background):
        return None
    return size, int(background, 16)


def fit(size, box):
    """The largest size with the proportions of `size` that fits `box`, at least one pixel each way."""
    width, height = size
    scale = min(box[0] / width, box[1] / height)
    return max(1, min(box[0], round(width * scale))), max(1, min(box[1], round(height * scale)))


def encode(raw, box):
    """Any snapshot Home Assistant hands out (JPEG, PNG, GIF, WebP) as a 24-bit BMP that fits `box`, the size of the
    screen's buffer."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        # A JPEG decodes at a half, quarter or eighth of its size while that is still larger than the box.
        source.draft('RGB', box)
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            ground = Image.new('RGB', image.size)
            ground.paste(image, mask=image.getchannel('A'))
            image = ground
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        size = fit(image.size, box)
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, 'BMP')
    return out.getvalue()


def encode_cover(raw, size, background):
    """A media player's picture as a square 24-bit BMP of `size` pixels with rounded corners, the corners filled with
    `background` (0xRRGGBB): what the screen draws on its card without any work of its own. A picture that is not
    square is cut to its middle."""
    from PIL import Image, ImageDraw, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        source.draft('RGB', (size, size))
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            ground = Image.new('RGB', image.size, tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
            ground.paste(image, mask=image.getchannel('A'))
            image = ground
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        width, height = image.size
        side = min(width, height)
        if width != height:
            left, top = (width - side) // 2, (height - side) // 2
            image = image.crop((left, top, left + side, top + side))
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        radius = max(4, size // COVER_RADIUS_SHARE)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
        ground = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        ground.paste(image, mask=mask)
        out = io.BytesIO()
        ground.save(out, 'BMP')
    return out.getvalue()


class Watch:
    """One camera or media player: its last picture, the sizes made of it and the fetch on its way. For a media
    player `picture` is the address the raw picture came from, so a changed picture is fetched again."""

    def __init__(self, now):
        self.used = now
        self.raw, self.digest = None, ''
        self.picture, self.fetching = None, None
        self.frames = {}
        self.failures = 0
        self.retry_at = 0.0
        self.task = None


class Link:
    __slots__ = ('entity', 'box', 'still', 'etag', 'used', 'lifetime', 'cover')

    def __init__(self, entity, box, now, still=None, cover=None):
        self.entity, self.box, self.used = entity, box, now
        self.still = still
        self.cover = cover  # (size, background) of a media player's cover, else None
        self.etag = f'"{hashlib.sha1(still).hexdigest()[:16]}"' if still else ''
        self.lifetime = STILL_SECONDS if still else LINK_SECONDS


class CameraFeed:
    def __init__(self, fetch, clock=time.monotonic, fetch_cover=None, picture=None):
        """`fetch(entity)` gives a camera's snapshot; `fetch_cover(entity)` a media player's picture and
        `picture(entity)` the address that picture has in its state right now ('' without one)."""
        self.fetch, self.clock = fetch, clock
        self.fetch_cover, self.picture = fetch_cover, picture
        self.watches, self.links = {}, {}

    # ----- fetching -----
    # A camera is fetched when a screen loads its picture: serving one starts fetching the next, so each load gets a
    # picture exactly one load younger and the picture changes in the screen's own steady rhythm. A fetch that ran on
    # its own clock next to the screen's made the picture change after 1.5 s one time and after 6 s the next (measured
    # 2026-09-17 with an EZVIZ camera that takes a steady 2.4 s per snapshot). Nobody loading means nothing fetched.
    def watch(self, entity):
        now = self.clock()
        for old in [e for e, w in self.watches.items() if now - w.used > WATCH_SECONDS and (w.task is None or w.task.done())]:
            del self.watches[old]
        watch = self.watches.get(entity)
        if watch is None:
            watch = self.watches[entity] = Watch(now)
        watch.used = now
        return watch

    def refresh(self, entity, watch):
        """Start fetching the next snapshot, unless one is on its way or the camera failed a moment ago."""
        if (watch.task is None or watch.task.done()) and self.clock() >= watch.retry_at:
            watch.task = asyncio.ensure_future(self.fetch_one(entity, watch))

    async def fetch_one(self, entity, watch):
        try:
            raw = await asyncio.wait_for(self.fetch(entity), FETCH_SECONDS)
            if not raw:
                raise ValueError('empty image')
            digest = hashlib.sha1(raw).hexdigest()
            if digest != watch.digest:
                watch.raw, watch.digest, watch.frames = raw, digest, {}
            if watch.failures:
                LOG.info('Camera %s answers again', entity)
            watch.failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as error:
            watch.failures += 1
            # A camera that fails is asked again after a pause, up to half a minute.
            watch.retry_at = self.clock() + min(30, 5 * watch.failures)
            if watch.failures in (1, 30):
                LOG.info('No image from %s (%s)', entity, type(error).__name__)

    async def frame(self, entity, box, wait=FIRST_FRAME_SECONDS, fresh=True, now=False):
        """(etag, BMP) of the camera's last snapshot at `box`, or None when it has none (yet). The first snapshot is
        waited for; `fresh` starts fetching the next one for the next load. `now` (an alert) waits for a snapshot whose
        fetch starts now or is already on its way, never one kept from an earlier load."""
        watch = self.watch(entity)
        if now:
            if watch.task is None or watch.task.done():
                watch.retry_at = 0.0
                self.refresh(entity, watch)
            try:
                await asyncio.wait_for(asyncio.shield(watch.task), wait)
            except asyncio.TimeoutError:
                return None
            if watch.failures:
                return None
        elif watch.raw is None:
            self.refresh(entity, watch)
            if watch.task is not None and not watch.task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(watch.task), wait)
                except asyncio.TimeoutError:
                    return None
        raw, digest = watch.raw, watch.digest
        if raw is None:
            return None
        if fresh:
            self.refresh(entity, watch)
        cached = watch.frames.get(box)
        if cached is None or cached[0] != digest:
            try:
                image = await asyncio.get_running_loop().run_in_executor(None, encode, raw, box)
            except Exception as error:
                LOG.info('The image of %s cannot be read (%s)', entity, type(error).__name__)
                return None
            cached = watch.frames[box] = (digest, image)
        return f'"{digest[:16]}-{box[0]}x{box[1]}"', cached[1]

    # ----- covers -----
    # A media player's picture is fetched when a screen loads its cover link and Home Assistant's picture is another
    # one than the last fetched (or none was fetched yet): a cover never changes on its own between two loads, and the
    # screen loads again only when the state's picture mark changed. So a load waits for the picture of this moment.
    async def fetch_cover_one(self, entity, watch, picture):
        try:
            raw = await asyncio.wait_for(self.fetch_cover(entity), FETCH_SECONDS)
            if not raw:
                raise ValueError('empty picture')
            digest = hashlib.sha1(raw).hexdigest()
            if digest != watch.digest:
                watch.raw, watch.digest, watch.frames = raw, digest, {}
            watch.picture = picture
            if watch.failures:
                LOG.info('The cover of %s comes again', entity)
            watch.failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as error:
            watch.failures += 1
            if watch.failures in (1, 30):
                LOG.info('No cover from %s (%s)', entity, type(error).__name__)

    async def cover(self, entity, size, background, wait=FIRST_FRAME_SECONDS):
        """(etag, BMP) of the player's cover at `size` with `background` behind its corners, or None when the player
        shows no picture or it cannot be fetched."""
        if self.fetch_cover is None or self.picture is None:
            return None
        picture = self.picture(entity)
        if not picture:
            return None
        watch = self.watch(entity)
        if watch.picture != picture or watch.raw is None:
            if watch.task is None or watch.task.done() or watch.fetching != picture:
                if watch.task is not None and not watch.task.done():
                    watch.task.cancel()
                watch.fetching = picture
                watch.task = asyncio.ensure_future(self.fetch_cover_one(entity, watch, picture))
            try:
                await asyncio.wait_for(asyncio.shield(watch.task), wait)
            except asyncio.TimeoutError:
                return None
            if watch.picture != picture or watch.raw is None:
                return None
        key = ('cover', size, background)
        cached = watch.frames.get(key)
        if cached is None or cached[0] != watch.digest:
            try:
                image = await asyncio.get_running_loop().run_in_executor(None, encode_cover, watch.raw, size, background)
            except Exception as error:
                LOG.info('The cover of %s cannot be read (%s)', entity, type(error).__name__)
                return None
            cached = watch.frames[key] = (watch.digest, image)
        return f'"{watch.digest[:16]}-c{size}-{background:06X}"', cached[1]

    # ----- links -----
    def prune(self):
        now = self.clock()
        for token in [token for token, link in self.links.items() if now - link.used > link.lifetime]:
            del self.links[token]
        while len(self.links) >= MAX_LINKS:
            del self.links[min(self.links, key=lambda token: self.links[token].used)]

    def link(self, entity, box, still=None, cover=None):
        """A new random token for one camera at one size; `still` makes it one fixed image (an alert's), `cover`
        (size, background) a media player's cover."""
        self.prune()
        token = secrets.token_urlsafe(18)
        self.links[token] = Link(entity, box, self.clock(), still, cover)
        return token

    async def serve(self, token, etag=None):
        """(HTTP status, BMP or None, etag) for one request of a screen."""
        link = self.links.get(token)
        now = self.clock()
        if link is None or now - link.used > link.lifetime:
            self.links.pop(token, None)
            return 404, None, ''
        link.used = now
        if link.still:
            return (304, None, link.etag) if etag == link.etag else (200, link.still, link.etag)
        found = await self.cover(link.entity, *link.cover) if link.cover else await self.frame(link.entity, link.box)
        if found is None:
            return 503, None, ''
        tag, image = found
        return (304, None, tag) if etag == tag else (200, image, tag)


def web_app(feed):
    """The camera port: GET /camera/<token>.bmp and nothing else, open to the LAN like the screens are."""
    from aiohttp import web

    async def image(request):
        status, body, etag = await feed.serve(request.match_info['token'], request.headers.get('If-None-Match'))
        headers = {'Cache-Control': 'no-cache', **({'ETag': etag} if etag else {})}
        if status == 200:
            return web.Response(body=body, content_type=CONTENT_TYPE, headers=headers)
        if status == 304:
            return web.Response(status=304, headers=headers)
        return web.Response(status=status, text='No image' if status == 503 else 'Unknown link', headers=headers)

    app = web.Application(client_max_size=1024)
    app.router.add_get(r'/camera/{token:[A-Za-z0-9_-]{16,64}}.bmp', image)
    return app


def port():
    try:
        value = int(os.environ.get('SCREEN_CAMERA_PORT', PORT))
    except ValueError:
        return PORT
    return value if 0 < value < 65536 else PORT


async def base_url(request, cache={}):
    """http://<address>:<port> where screens reach this app: SCREEN_CAMERA_URL when set, else Home Assistant's
    own LAN address (the add-on's port is published on the host). `request` is HomeAssistant.request."""
    override = os.environ.get('SCREEN_CAMERA_URL', '').rstrip('/')
    if override:
        return override
    now = time.monotonic()
    if cache.get('url') and now - cache.get('at', 0) < 600:
        return cache['url']
    host = None
    try:
        network = await request('network')
        for adapter in (network or {}).get('adapters', []):
            addresses = [item.get('address') for item in adapter.get('ipv4') or [] if item.get('address')]
            if adapter.get('default') and addresses:
                host = addresses[0]
                break
    except Exception as error:
        LOG.info('Reading the network adapters failed (%s)', type(error).__name__)
    if host is None:
        try:
            from urllib.parse import urlparse
            host = urlparse((await request('network/url') or {}).get('internal') or '').hostname
        except Exception as error:
            LOG.info('Reading the internal URL failed (%s)', type(error).__name__)
    if not host:
        return None
    cache.update(url=f'http://{host}:{port()}', at=now)
    return cache['url']
