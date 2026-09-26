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
from email.utils import formatdate
import hashlib
import io
import logging
import os
import re
import secrets
import time

import tile_art
import alert_layout
from core import SHAPES, board_of, screen_firmware, shape_of

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
# Live pictures on camera tiles (app 0.2.91, firmware 0.2.77): a tile with "display": "live" shows a small square of its
# camera in the icon's place. The camera tiles of a page share one image: the screen asks for them together and the
# app serves one strip of squares, top to bottom in the screen's order, each cut to the middle of its snapshot with
# the corners rounded over that tile's own colour. A camera is fetched again only when its tile's pace (15 or 30 s)
# has passed since the last fetch, so a page loading every 15 s leaves a 30 s camera alone in between.
LIVE_MIN_FIRMWARE = (0, 2, 77)
# A media tile's album cover in the same strip (app 0.2.92, firmware 0.2.78): "display": "cover" on a single or wide
# media tile. A cover is fetched when the player's picture address changes, never on a clock; the screen asks for the
# page again when the picture's mark in the player's state changes.
COVER_TILE_MIN_FIRMWARE = (0, 2, 78)
# A camera on a 1x2 or 2x2 tile fills the card (app 0.3.8, firmware 0.3.3): the tile's own `fit` and `overlay` say how
# the app cuts its picture and whether it shades the bottom for the name. Older firmware draws the small square there.
CAMERA_ART_FIRMWARE = (0, 3, 3)
# The same firmware is built with an ESPHome whose BMP decoder reads 8-bit pictures: a page's pictures go to it in 8-bit
# colour (tile_art.bmp), a third of the bytes of 24-bit. Older screens keep 24-bit.
LIVE_SIZES = (24, 160)   # a square's side, in pixels
LIVE_MAX_TILES = 6       # one page
LIVE_REFRESH = (15, 30)  # the paces a tile may choose, in seconds
LIVE_RADIUS_SHARE = 6    # a rounder corner than a cover's: the square is small
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
# The pixel box per board and view, for the board lying down; the image keeps its proportions inside it. Straight
# from the CAMERA_* substitutions of the board's own YAML (tools/generate_board_shapes.py writes them into
# boards.json), so a new board that draws cameras is served without a line here (tests/test_camera.py). Whether a
# board is in here at all is the question of whether it draws pictures, which does not depend on the way it hangs:
# a board without them, like the CYD, has no camera either way up, `can_show` is false and a camera tile is refused
# before it is saved.
BOXES = {shape['board']: {view: tuple(box) for view, box in shape['camera'].items()}
         for shape in SHAPES.values() if shape.get('camera')}


def boxes(screen):
    """The pixel boxes for one screen's pictures, or None when its board draws none (app 0.2.107).

    Not BOXES[board]: a screen built standing up has the canvas of the other side, so a full-screen picture shaped
    for the board lying down would arrive turned a quarter and letterboxed, and the still in its alert card would be
    wider than the card the firmware brought back to fit. Those numbers come from the board file for each way it can
    hang (core.shape_of), so a screen whose orientation nothing has said keeps exactly the boxes it got before.
    """
    found = shape_of(screen).get('camera') if isinstance(screen, dict) else None
    if not found:
        return BOXES.get(board_of(screen))
    return {view: tuple(box) for view, box in found.items()}


def box(screen, view):
    """One of them ('full' or 'thumb'), or None on a screen whose board draws no pictures."""
    return (boxes(screen) or {}).get(view)


# Firmware 0.2.103 lays its alert out again for the picture it gets, in that picture's own proportions
# (screen_alert::layout), so from there on the picture is sent at the size that layout gives it. Older firmware has a
# frame of one fixed size and gets the picture for that frame, as before.
ALERT_FIT_FIRMWARE = (0, 2, 103)


def alert_box(screen, picture):
    """The size to send the picture of an alert at, for one screen: the frame its alert card makes for a picture of
    `picture` (width, height) proportions on its glass (alert_layout, the firmware's own rule), so the picture fills
    that frame pixel for pixel. The frame for a camera's 16:9 (box 'thumb') when the picture is not known, the
    firmware is older, or the glass has no room for a picture of those proportions; None when the board draws none."""
    default = box(screen, 'thumb')
    if not default or not picture or not isinstance(screen, dict):
        return default
    if (screen_firmware(screen) or (0, 0, 0)) < ALERT_FIT_FIRMWARE:
        return default
    board = SHAPES.get(board_of(screen)) or {}
    lines, shape = board.get('alert'), shape_of(screen)
    if not lines or not shape.get('width') or not shape.get('height') or not board.get('dpi'):
        return default
    # The density and the look the screen reports (its "Screen layout") win over its board's, so an Override YAML that
    # changes DISPLAY_DPI or the look is followed: the card's fonts are then worked out for what the screen was built
    # with. As the board was built, its own line heights hold, measured from the board's exact density.
    dpi, look = shape.get('dpi') or board['dpi'], shape.get('look') or board.get('look', 'standard')
    if (dpi, look) == (board['dpi'], board.get('look', 'standard')):
        title_line, line = lines['title_line'], lines['line']
    else:
        title_line, line = alert_layout.lines(dpi, look)
    card = alert_layout.layout(shape['width'], shape['height'], title_line, line, True, dpi, look, picture[0], picture[1])
    return (card.image_w, card.image_h) if card.image_w > 0 and card.image_h > 0 else default


def picture_size(raw):
    """(width, height) of a snapshot as the screen will see it, read from its header without decoding it: a camera
    that writes its picture turned and says so in EXIF (orientations 5 to 8) is measured the way it will be shown."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as source:
        width, height = source.size
        try:
            turned = source.getexif().get(0x0112) in (5, 6, 7, 8)
        except Exception:
            turned = False
    return (height, width) if turned else (width, height)


def supported(entity):
    """True for a camera or image entity id."""
    return (isinstance(entity, str) and len(entity) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', entity) is not None
            and entity.split('.')[0] in DOMAINS)


def can_show(screen):
    """A paired Guition with firmware that draws camera images (the version feature gates go by, core.screen_firmware)."""
    return bool(screen) and board_of(screen) in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= MIN_FIRMWARE


def cover_supported(entity):
    """True for a media player entity id: its cover can be served."""
    return (isinstance(entity, str) and len(entity) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', entity) is not None
            and entity.split('.')[0] in COVER_DOMAINS)


def can_show_cover(screen):
    """A paired Guition with firmware that draws the media card's cover."""
    return bool(screen) and board_of(screen) in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= COVER_MIN_FIRMWARE


def can_show_live(screen):
    """A paired Guition with firmware that draws live pictures on camera tiles."""
    return bool(screen) and board_of(screen) in BOXES and (screen_firmware(screen) or (0, 0, 0)) >= LIVE_MIN_FIRMWARE


def picture_modes(screen, options_of, entities):
    """(fit, fade) per tile of a live strip: how the app prepares each picture. A camera on a taller card gets its own
    choices once the screen's firmware draws it there; everything else is filled and left alone."""
    art = (screen_firmware(screen) or (0, 0, 0)) >= CAMERA_ART_FIRMWARE
    modes = []
    for entity in entities:
        options = options_of(entity) or {}
        if art and supported(entity) and options.get('display') == 'live' and options.get('size') in ('tall', 'square'):
            modes.append((options.get('fit', 'fill'), options.get('overlay', 'name') != 'none'))
        else:
            modes.append(('fill', False))
    return modes


def compact_pictures(screen):
    """Whether a screen gets its live pictures in 8-bit colour (app 0.3.8)."""
    return (screen_firmware(screen) or (0, 0, 0)) >= CAMERA_ART_FIRMWARE


def live_request(request, atlas=False):
    """(entities, size, grounds) a screen asked live pictures for, or None when it is not a request the app can serve:
    `tiles` the camera tiles of its page as a comma-separated list, `size` the square's side within LIVE_SIZES and
    `bg` one colour of six hex digits per tile, the tile's own, behind the corners."""
    tiles, grounds = request.get('tiles'), request.get('bg')
    if not isinstance(tiles, str) or not isinstance(grounds, str):
        return None
    entities, colours = tiles.split(','), grounds.split(',')
    try:
        size = int(request.get('size'))
    except (TypeError, ValueError):
        return None
    if not 1 <= len(entities) <= (64 if atlas else LIVE_MAX_TILES) or len(colours) != len(entities) or (not atlas and len(set(entities)) != len(entities)):
        return None
    if not LIVE_SIZES[0] <= size <= LIVE_SIZES[1] or not all(supported(e) or cover_supported(e) for e in entities) or not all(re.fullmatch(r'[0-9A-Fa-f]{6}', c) for c in colours):
        return None
    return entities, size, [int(c, 16) for c in colours]


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


def encode(raw, box, exact=False):
    """Any snapshot Home Assistant hands out (JPEG, PNG, GIF, WebP) as a 24-bit BMP that fits `box`, the size of the
    screen's buffer. `exact` makes it exactly `box`: for a box that already has the picture's proportions to within a
    pixel of rounding (alert_box), so the picture and the frame the screen made for it are the same pixels."""
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
        size = tuple(box) if exact else fit(image.size, box)
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


def _square(image, size, background, radius_share):
    """The middle of `image` as a square of `size` pixels with rounded corners over `background` (0xRRGGBB)."""
    from PIL import Image, ImageDraw
    width, height = image.size
    side = min(width, height)
    if width != height:
        left, top = (width - side) // 2, (height - side) // 2
        image = image.crop((left, top, left + side, top + side))
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    radius = max(4, size // radius_share)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    ground = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
    ground.paste(image, mask=mask)
    return ground


def _opaque(source, background):
    """An RGB image from any picture Home Assistant hands out, transparency landing on `background`."""
    from PIL import Image, ImageOps
    image = ImageOps.exif_transpose(source)
    if image.mode in ('RGBA', 'LA', 'P', 'PA'):
        image = image.convert('RGBA')
        ground = Image.new('RGB', image.size, tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        ground.paste(image, mask=image.getchannel('A'))
        return ground
    return image if image.mode == 'RGB' else image.convert('RGB')


def encode_live(raws, size, grounds, compact=False):
    """The strip a page's camera tiles share: one square of `size` pixels per tile, top to bottom, each the middle of
    its snapshot with rounded corners over that tile's colour (`grounds`, 0xRRGGBB each); a tile without a snapshot
    (None) gets a plain square of its colour. A 24-bit BMP of `size` by `size` times the number of tiles."""
    from PIL import Image
    strip = Image.new('RGB', (size, size * len(raws)))
    for n, (raw, background) in enumerate(zip(raws, grounds)):
        if raw is None:
            square = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        else:
            with Image.open(io.BytesIO(raw)) as source:
                source.draft('RGB', (size * 2, size * 2))
                square = _square(_opaque(source, background), size, background, LIVE_RADIUS_SHARE)
        strip.paste(square, (0, n * size))
    return tile_art.bmp(strip, compact)


class Watch:
    """One camera or media player: its last picture, the sizes made of it and the fetch on its way. For a media
    player `picture` is the address the raw picture came from, so a changed picture is fetched again. `fetched_at`
    is when the last fetch started: a live tile fetches again only when its own pace has passed."""

    def __init__(self, now):
        self.used = now
        self.raw, self.digest = None, ''
        self.picture, self.fetching = None, None
        self.frames = {}
        self.size, self.size_of = None, ''  # the last picture's (width, height), and the digest it was measured for
        self.failures = 0
        self.retry_at = 0.0
        self.fetched_at = 0.0
        self.task = None


class Link:
    __slots__ = ('entity', 'box', 'still', 'etag', 'used', 'lifetime', 'cover', 'live')

    def __init__(self, entity, box, now, still=None, cover=None, live=None):
        self.entity, self.box, self.used = entity, box, now
        self.still = still
        self.cover = cover  # (size, background) of a media player's cover, else None
        self.live = live    # (entities, size, grounds, paces[, {atlas, modes, compact}]) of a page's live tiles, else None
        self.etag = f'"{hashlib.sha1(still).hexdigest()[:16]}"' if still else ''
        self.lifetime = STILL_SECONDS if still else LINK_SECONDS


class CameraFeed:
    def __init__(self, fetch, clock=time.monotonic, fetch_cover=None, picture=None):
        """`fetch(entity)` gives a camera's snapshot; `fetch_cover(entity)` a media player's picture and
        `picture(entity)` the address that picture has in its state right now ('' without one)."""
        self.fetch, self.clock = fetch, clock
        self.fetch_cover, self.picture = fetch_cover, picture
        self.watches, self.links = {}, {}
        self.strips = {}

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
            watch.fetched_at = self.clock()
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

    async def frame(self, entity, box, wait=FIRST_FRAME_SECONDS, fresh=True, now=False, exact=False):
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
        if box is None:  # only the snapshot was asked for (snapshot_size)
            return digest, None
        key = (box, 'exact') if exact else box
        cached = watch.frames.get(key)
        if cached is None or cached[0] != digest:
            try:
                image = await asyncio.get_running_loop().run_in_executor(None, encode, raw, box, exact)
            except Exception as error:
                LOG.info('The image of %s cannot be read (%s)', entity, type(error).__name__)
                return None
            cached = watch.frames[key] = (digest, image)
        return f'"{digest[:16]}-{box[0]}x{box[1]}"', cached[1]

    async def snapshot_size(self, entity, wait=FIRST_FRAME_SECONDS):
        """(width, height) of the camera's snapshot of this moment, fetched now or already on its way (as frame with
        `now`), or None when it has none. Measured once per snapshot; the frames made from it after this reuse it."""
        if await self.frame(entity, None, wait=wait, fresh=False, now=True) is None:
            return None
        watch = self.watch(entity)
        if watch.raw is None:
            return None
        if watch.size_of != watch.digest:
            try:
                watch.size = await asyncio.get_running_loop().run_in_executor(None, picture_size, watch.raw)
            except Exception as error:
                LOG.info('The image of %s cannot be read (%s)', entity, type(error).__name__)
                return None
            watch.size_of = watch.digest
        return watch.size

    # ----- live tiles -----
    # A page's strip is made when the screen loads its link, out of the last snapshot of every tile's camera, and
    # serving it starts the next fetch of the cameras whose pace has passed: a 15 s page fetches a 30 s camera every
    # other load. The first load waits for the cameras that have no snapshot yet, all at once.
    async def live_one(self, entity, pace, wait):
        if cover_supported(entity):
            return await self.cover_raw(entity, wait)
        watch = self.watch(entity)
        if watch.raw is None:
            self.refresh(entity, watch)
            if watch.task is not None and not watch.task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(watch.task), wait)
                except asyncio.TimeoutError:
                    return None
        elif self.clock() - watch.fetched_at >= pace:
            self.refresh(entity, watch)
        return watch.raw

    async def live(self, entities, size, grounds, paces, wait=FIRST_FRAME_SECONDS, *, atlas=None, modes=None, compact=False):
        """(etag, BMP, entities with '' where a camera has no snapshot) of the strip for a page's camera tiles at
        `size` with `grounds` behind the corners and `paces` in seconds per tile, or None when no camera has one."""
        raws = await asyncio.gather(*(self.live_one(entity, pace, wait) for entity, pace in zip(entities, paces)))
        if all(raw is None for raw in raws):
            return None
        digests = [self.watches[entity].digest if raw is not None else '' for entity, raw in zip(entities, raws)]
        key = ('live', size, tuple(grounds), tuple(digests), atlas, tuple(modes or ()), compact)
        tag = f'"{hashlib.sha1(repr(key).encode()).hexdigest()[:16]}-l{size}"'  # names the strip; not sent
        cached = self.strips.get(key)
        if cached is None:
            try:
                image = await asyncio.get_running_loop().run_in_executor(None, tile_art.encode, raws, grounds, atlas, modes, compact) if atlas else await asyncio.get_running_loop().run_in_executor(None, encode_live, raws, size, grounds, compact)
            except Exception as error:
                LOG.info('The live pictures of %s cannot be read (%s)', ', '.join(entities), type(error).__name__)
                return None
            self.strips = {key: image}  # the last strip only: the next load makes another anyway
        else:
            image = cached
        return tag, image, [entity if raw is not None else '' for entity, raw in zip(entities, raws)]

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

    async def cover_raw(self, entity, wait=FIRST_FRAME_SECONDS):
        """The player's picture as Home Assistant hands it out, fetched again only when its address changed; None when
        the player shows no picture or it cannot be fetched (yet)."""
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
        return watch.raw

    async def cover_preview(self, entity):
        """Bounded editor pixels with source proportions intact for CSS cover crop."""
        raw = await self.cover_raw(entity, FIRST_FRAME_SECONDS)
        if raw is None:
            return None
        watch = self.watch(entity)
        key = ('editor', 512)
        cached = watch.frames.get(key)
        if cached is None or cached[0] != watch.digest:
            try:
                image = await asyncio.get_running_loop().run_in_executor(None, encode, raw, (512, 512))
            except Exception:
                return None
            cached = watch.frames[key] = (watch.digest, image)
        return f'"{watch.digest[:16]}-editor"', cached[1]

    async def cover(self, entity, size, background, wait=FIRST_FRAME_SECONDS):
        """(etag, BMP) of the player's cover at `size` with `background` behind its corners, or None when the player
        shows no picture or it cannot be fetched."""
        if await self.cover_raw(entity, wait) is None:
            return None
        watch = self.watch(entity)
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

    def link(self, entity, box, still=None, cover=None, live=None):
        """A new random token for one camera at one size; `still` makes it one fixed image (an alert's), `cover`
        (size, background) a media player's cover, `live` (entities, size, grounds, paces) a page's live tiles."""
        self.prune()
        token = secrets.token_urlsafe(18)
        self.links[token] = Link(entity, box, self.clock(), still, cover, live)
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
        if link.live:
            # Always the whole strip, never a 304: ESPHome's http_request logs a 304 as a failed request and raises its
            # error flag every time, and a page of slow cameras (a radar every five minutes) would do that every 15 s.
            # The strip is small; the screen draws its squares again either way. The tag still goes out as an ETag:
            # online_image warns at every load about a missing one.
            found = await self.live(*link.live[:4], **(link.live[4] if len(link.live) > 4 else {}))
            return (503, None, '') if found is None else (200, found[1], found[0])
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
        # Last-Modified with every picture: online_image warns at every load about a missing one (it never sends
        # If-Modified-Since on its own; only the ETag decides a 304 here).
        headers = {'Cache-Control': 'no-cache', 'Last-Modified': formatdate(usegmt=True), **({'ETag': etag} if etag else {})}
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
