"""The screensaver's photos (app 0.4.89, docs/SCREENSAVER.md "Photos"): one photo of a folder of Home Assistant's media
after the other, each over the whole glass.

The folder is any media source Home Assistant has: an album, a person or a tag of Immich, a folder under /media,
Synology Photos. The app reads it through Home Assistant's own websocket (`media_source/browse_media`, a few levels deep,
at most MAX_PHOTOS photos), keeps the list for an hour, and per screen walks it: shuffled without a repeat until every
photo stood once, or in the folder's order. The next photo is fetched and read before its turn (`media_source/
resolve_media` names its address, Home Assistant serves it with the app's own token), so the screen changes at once when
its time comes: the message's mark changes only once the photo is here, and the screen loads it under the one that
stands, as a player's next cover.

Nothing of a photo is logged: no name, no address, no folder. The photos are kept in memory only, the two of each
screen (the one on the glass and the next), and a link to one ends as every camera link does."""
import asyncio
import hashlib
import logging
import random
import time

LOG = logging.getLogger(__name__)

# How many photos of a folder the app walks, how deep it looks into folders in it, and how many folders it opens.
MAX_PHOTOS = 500
MAX_DEPTH = 3
MAX_BROWSES = 40
# How long a folder's list is kept before the app reads it again (new photos in an album).
LIST_SECONDS = 3600
# A photo as Home Assistant serves it: a telephone's full JPEG or HEIC is a few megabytes, a camera's raw export more.
MAX_PHOTO_BYTES = 25 * 1024 * 1024
# A photo that cannot be had (gone from the album, a format the app cannot read) is passed over; after this many in a
# row the folder is read again, and the step waits (FAIL_SECONDS) before it tries once more.
MAX_MISSES = 5
FAIL_SECONDS = 60
FETCH_SECONDS = 30


def is_photo(child):
    """A child of a browse answer that is a photo: Home Assistant's media class `image`, or an image's content type."""
    if not isinstance(child, dict) or child.get('can_expand'):
        return False
    kind = str(child.get('media_content_type') or '')
    return child.get('media_class') == 'image' or kind.startswith('image/')


def is_folder(child):
    return isinstance(child, dict) and bool(child.get('can_expand')) and isinstance(child.get('media_content_id'), str)


def mark(content_id):
    """A short mark of one photo for the screen: changes with the photo, says nothing of it."""
    return hashlib.sha1(content_id.encode()).hexdigest()[:10]


class Folder:
    __slots__ = ('photos', 'title', 'read_at', 'task', 'failed_at')

    def __init__(self):
        self.photos, self.title, self.read_at = [], '', 0.0
        self.task, self.failed_at = None, 0.0


class Show:
    """One screen's walk through its folder: the photo on the glass and the next one, each with its picture."""
    __slots__ = ('source', 'order', 'deck', 'at', 'current', 'current_raw', 'shown_at', 'next', 'next_raw', 'task',
                 'misses', 'waited_at', 'every')

    def __init__(self, source, order):
        self.source, self.order = source, order
        self.deck, self.at = [], 0
        self.current, self.current_raw, self.shown_at = None, None, 0.0
        self.next, self.next_raw, self.task = None, None, None
        self.misses, self.waited_at = 0, 0.0
        self.every = 60


class Photos:
    def __init__(self, request, fetch, clock=time.monotonic, rng=None):
        """`request(kind, **data)` asks Home Assistant's websocket; `fetch(address)` gives the bytes of an address
        `media_source/resolve_media` named (Home Assistant's own, with the app's token)."""
        self.request, self.fetch, self.clock = request, fetch, clock
        self.rng = rng or random.Random()
        self.folders, self.shows = {}, {}

    # ----- the folder -----
    async def browse(self, content_id=''):
        """One level of Home Assistant's media sources, for the editor's picker: the folders in it and how many photos
        it holds right there. Raises what Home Assistant said when it cannot be browsed."""
        answer = await self.request('media_source/browse_media', media_content_id=content_id)
        children = (answer or {}).get('children') or []
        return {'id': (answer or {}).get('media_content_id', content_id), 'title': (answer or {}).get('title', ''),
                'folders': [{'id': c['media_content_id'], 'title': c.get('title') or '', 'thumbnail': bool(c.get('thumbnail'))}
                            for c in children if is_folder(c)],
                'photos': sum(1 for c in children if is_photo(c))}

    async def read(self, source):
        """Every photo of a folder and the folders in it, a few levels deep, in the order Home Assistant lists them."""
        photos, title, seen = [], '', 0
        queue = [(source, 0)]
        while queue and len(photos) < MAX_PHOTOS and seen < MAX_BROWSES:
            content_id, depth = queue.pop(0)
            seen += 1
            answer = await self.request('media_source/browse_media', media_content_id=content_id)
            if not title:
                title = str((answer or {}).get('title') or '')
            for child in (answer or {}).get('children') or []:
                if is_photo(child) and isinstance(child.get('media_content_id'), str):
                    photos.append(child['media_content_id'])
                    if len(photos) >= MAX_PHOTOS:
                        break
                elif is_folder(child) and depth + 1 < MAX_DEPTH:
                    queue.append((child['media_content_id'], depth + 1))
        return photos, title

    def folder(self, source):
        """The folder's list as it stands; a read starts when there is none, or it is older than LIST_SECONDS."""
        folder = self.folders.setdefault(source, Folder())
        now = self.clock()
        stale = not folder.read_at or now - folder.read_at >= LIST_SECONDS
        waiting = folder.failed_at and now - folder.failed_at < FAIL_SECONDS
        if stale and not waiting and (folder.task is None or folder.task.done()):
            try:
                folder.task = asyncio.ensure_future(self._read(source, folder))
            except RuntimeError:  # no loop (a test of the pure parts)
                pass
        return folder

    async def _read(self, source, folder):
        try:
            photos, title = await self.read(source)
            folder.photos, folder.title, folder.read_at, folder.failed_at = photos, title, self.clock(), 0.0
            LOG.info('Screensaver photos: a folder of %d photo%s', len(photos), '' if len(photos) == 1 else 's')
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - Home Assistant may not have the source (yet)
            folder.failed_at = self.clock()
            LOG.info('Screensaver photos: the folder cannot be read (%s)', type(error).__name__)
        if self.changed:
            self.changed()

    changed = None  # set by the app: a pass of every screen, for a folder read or a photo that came

    # ----- one screen -----
    def _deal(self, show, photos):
        """The next round through the folder: shuffled (never the photo on the glass first), or in its order."""
        deck = list(photos)
        if show.order == 'shuffle':
            self.rng.shuffle(deck)
            if len(deck) > 1 and show.current and deck[0] == show.current:
                deck.append(deck.pop(0))
        show.deck, show.at = deck, 0

    def _upcoming(self, show, photos):
        if show.at >= len(show.deck) or set(show.deck) - set(photos):
            self._deal(show, photos)
        return show.deck[show.at] if show.deck else None

    def state(self, inbox, choice, every=None):
        """What the photos step of a screen shows now ({'ready', 'mark', 'index', 'count', 'album'}), and the walk on:
        the next photo is fetched ahead, and takes the glass once it is here and the one before stood its time."""
        source = (choice or {}).get('source', '')
        if not source:
            self.forget(inbox)
            return {'ready': False}
        order = (choice or {}).get('order', 'shuffle')
        every = every if every is not None else (choice or {}).get('every', 60)
        show = self.shows.get(inbox)
        if show is None or show.source != source or show.order != order:
            self.forget(inbox)
            show = self.shows[inbox] = Show(source, order)
        show.every = every
        folder = self.folder(source)
        photos = folder.photos
        now = self.clock()
        if not photos:
            return {'ready': False}
        if show.next is None and show.misses < MAX_MISSES:
            show.next = self._upcoming(show, photos)
            show.at += 1
        due = show.current is None or now - show.shown_at >= every
        if due and show.next_raw is not None:
            show.current, show.current_raw, show.shown_at = show.next, show.next_raw, now
            show.next, show.next_raw = None, None
            show.misses = 0
            if show.misses < MAX_MISSES:
                show.next = self._upcoming(show, photos)
                show.at += 1
        if show.next is not None and show.next_raw is None and (show.task is None or show.task.done()):
            if show.misses < MAX_MISSES or now - show.waited_at >= FAIL_SECONDS:
                if show.misses >= MAX_MISSES:
                    show.misses = 0
                try:
                    show.task = asyncio.ensure_future(self._fetch_next(inbox, show))
                except RuntimeError:
                    pass
        if show.current is None:
            return {'ready': False}
        index = photos.index(show.current) + 1 if show.current in photos else 0
        return {'ready': True, 'mark': mark(show.current), 'index': index, 'count': len(photos), 'album': folder.title}

    async def _fetch_next(self, inbox, show):
        wanted = show.next
        try:
            resolved = await self.request('media_source/resolve_media', media_content_id=wanted)
            address = (resolved or {}).get('url')
            if not isinstance(address, str) or not address:
                raise ValueError('no address')
            raw = await asyncio.wait_for(self.fetch(address), FETCH_SECONDS)
            if not raw:
                raise ValueError('empty photo')
            if len(raw) > MAX_PHOTO_BYTES:
                raise ValueError('photo too large')
            readable(raw)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - one photo that cannot be had is passed over
            if self.shows.get(inbox) is show and show.next == wanted:
                show.misses += 1
                show.next = None
                # What went wrong, never which photo (its name or address).
                LOG.info('Screensaver photos: a photo was passed over (%s%s)', type(error).__name__,
                         f' {error.status}' if isinstance(getattr(error, 'status', None), int) else '')
                if show.misses >= MAX_MISSES:
                    show.waited_at = self.clock()
                    folder = self.folders.get(show.source)
                    if folder:
                        folder.read_at = 0.0  # read the folder again: photos may have gone
                    LOG.info('Screensaver photos: %d photos in a row could not be had (%s)', show.misses, type(error).__name__)
            return
        if self.shows.get(inbox) is show and show.next == wanted:
            show.next_raw = raw
            if self.changed and show.current is None:
                self.changed()

    def raw(self, inbox, wanted=''):
        """The bytes of the photo a screen's glass shows now (its mark `wanted`, '' for whichever), or None."""
        show = self.shows.get(inbox)
        if not show or show.current is None or (wanted and mark(show.current) != wanted):
            return None
        return show.current_raw

    def forget(self, inbox):
        show = self.shows.pop(inbox, None)
        if show and show.task is not None and not show.task.done():
            show.task.cancel()

    def due(self):
        """Whether a screen's next photo is here and its turn has come (or the first one is here): a pass then."""
        now = self.clock()
        return any(show.next_raw is not None and (show.current is None or now - show.shown_at >= show.every)
                   for show in self.shows.values())


def readable(raw):
    """Raises unless Pillow can open the photo (HEIC through pillow-heif, which the app registers when it has it)."""
    import io
    from PIL import Image
    heif()
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > pixel_limit(image):
            raise ValueError('photo too large')


# A photo of more pixels than this is refused before it is read: a 108 MP telephone's photo still passes, a crafted
# picture of a billion pixels does not (Pillow's own warning starts at 89 MP).
MAX_PIXELS = 120_000_000
# A JPEG is decoded small (Image.draft, picture_paint.opened), a HEIC is not: pillow-heif decodes it whole, three
# bytes a pixel, before anything is scaled. 50 MP, the most a telephone takes, is 150 MB on a Raspberry Pi; more is not
# a photo from a telephone.
MAX_PIXELS_HEIF = 50_000_000


def pixel_limit(image):
    """The pixels a photo may have, by how Pillow reads its format: small for a JPEG, whole for a HEIC."""
    return MAX_PIXELS_HEIF if image.format in ('HEIF', 'AVIF') else MAX_PIXELS

_heif = None


def heif():
    """Teach Pillow HEIC and HEIF, a telephone's own format, once; False where pillow-heif is missing."""
    global _heif
    if _heif is None:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
            _heif = True
        except Exception:  # noqa: BLE001 - without it a HEIC photo is passed over
            _heif = False
    return _heif
