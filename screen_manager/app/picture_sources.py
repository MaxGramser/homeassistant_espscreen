"""The sources a picture can be of (docs/PICTURES.md, "Sources"): whether a screen may have one, and getting it.

One rule set for the core and for plugins. A source is named by its screen (picture_question.Source); `Sources.may`
says why a screen may not have it (None when it may) and `Sources.get` gets what to paint: the picture's bytes, or a
picture a source draws itself at the place's size (a map), with a mark of what it shows now, and what the source says
about how it is painted (a camera tile's own fit and shade, the colour beside a cover on the screensaver).

A camera and a player's cover each have one watch here (Snapshots), shared by every screen and every route: the still
on a tile, the full view, the screensaver and an alert read the same snapshot, fetched in the screen's own rhythm.
"""
import asyncio
from dataclasses import dataclass, field
import hashlib
import logging
import time

import picture_question as pq
import rest_mosaic

LOG = logging.getLogger(__name__)

# A camera nobody loaded a picture of for this long is forgotten, its last snapshot with it.
WATCH_SECONDS = 30
FIRST_FRAME_SECONDS = 8
FETCH_SECONDS = 15
# A player's cover that could not be fetched is fetched again by the app itself this long after.
COVER_RETRY_SECONDS = 60
# The next fetch of a camera starts this long before the screen's next load, less what the camera took to answer, so the
# load finds a snapshot a fraction of a second old (GitHub #183); a load whose fetch is still on its way waits this long.
AHEAD_MARGIN = 0.5
AHEAD_WAIT = 1.5
# A camera tile's pace when it names none, in seconds (catalogue camera.picture.refresh).
TILE_PACE = 15
# Firmware whose camera tile fills its card with the tile's own fit and shade (app 0.3.8): 1x2 and 2x2 from 0.3.3, every
# size from 0.3.7. Older firmware gets the camera filled and plain.
CAMERA_ART_FIRMWARE = (0, 3, 3)
CAMERA_CARD_FIRMWARE = (0, 3, 7)


@dataclass
class Resolved:
    """What a source gives: `raw` bytes, or a picture it drew (a Pillow image), or None; `mark` what it shows now (another
    mark is another picture); what it says about how its place is painted (`fit`, `fade`, `ground`, `move`; None leaves
    the place's own); `state` 'ok', 'none' (nothing to show now) or 'pending' (on its way: no answer yet, the screen asks
    again); `stream` whether it may stream, and with which fit; `meta` what goes with the picture (a map's markers)."""
    raw: object = None
    mark: str = ''
    fit: str = None
    fade: bool = None
    ground: int = None
    move: bool = None
    state: str = 'ok'
    stream: str = ''
    meta: dict = field(default_factory=dict)

    @property
    def volatile(self):
        """Whether the same source shows another picture later by itself (a camera, a map someone moves on)."""
        return self.mark.startswith(('camera:', 'map:'))


NONE = Resolved(state='none')
PENDING = Resolved(state='pending')


class Watch:
    """One camera or media player: its last picture and the fetch on its way. For a media player `picture` is the
    address the raw picture came from, so a changed picture is fetched again."""

    def __init__(self, now):
        self.used = now
        self.raw, self.digest = None, ''
        self.picture, self.fetching = None, None
        self.size, self.size_of = None, ''  # the last picture's (width, height), and the digest it was measured for
        self.failures = 0
        self.retry_at = 0.0
        self.failed = None  # a media player's picture address whose last fetch failed, until one of it comes
        self.fetched_at = 0.0
        self.task = None
        self.took = None            # how long the camera took to answer, smoothed: the lead of the next fetch ahead
        self.ahead, self.ahead_at = None, 0.0  # the fetch ahead waiting for its moment, and that moment


class Snapshots:
    """The cameras' snapshots and the players' covers, fetched once for every screen.

    A camera is fetched in the screen's own rhythm: a load sets the next fetch for just before the next load (ahead), so
    each load gets a snapshot of that moment and the picture changes in the screen's steady rhythm. A fetch that ran on
    its own clock next to the screen's made the picture change after 1.5 s one time and after 6 s the next (measured
    2026-09-17 with an EZVIZ camera that takes a steady 2.4 s per snapshot). Nobody loading means nothing fetched, beyond
    the one fetch ahead the last load set. A player's picture is fetched when its address changes, never on a clock."""

    def __init__(self, fetch, clock=time.monotonic, fetch_cover=None, picture=None, sleep=asyncio.sleep):
        """`fetch(entity)` gives a camera's snapshot; `fetch_cover(entity)` a media player's picture and `picture(entity)`
        the address that picture has in its state right now ('' without one)."""
        self.fetch, self.clock, self.sleep = fetch, clock, sleep
        self.fetch_cover, self.picture = fetch_cover, picture
        self.watches = {}
        # A vacuum's map (vacuum_map.py), per map entity: the mark it was fetched at and the map read once.
        self.vacuum_maps = {}

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

    def ahead(self, entity, watch, pace):
        """After a load at `pace` seconds: the next fetch, timed to be done just before the next load. A fetch ahead
        already set for sooner stays (a quicker tile of the same camera)."""
        if pace <= 0:
            return
        delay = max(0.0, pace - (watch.took if watch.took is not None else 1.0) - AHEAD_MARGIN)
        at = self.clock() + delay
        if watch.ahead is not None and not watch.ahead.done():
            if watch.ahead_at <= at:
                return
            watch.ahead.cancel()
        watch.ahead_at = at

        async def later():
            await self.sleep(delay)
            if self.watches.get(entity) is watch:  # still watched: someone loaded it lately (a failing camera keeps its pause)
                self.refresh(entity, watch)
        watch.ahead = asyncio.ensure_future(later())

    async def fresh(self, entity, watch, pace):
        """Before a load at `pace` seconds: a snapshot older than the pace is fetched now, and a fetch on its way is waited
        for a moment, so the load gets the snapshot of now, not the last."""
        if self.clock() - watch.fetched_at >= pace:
            self.refresh(entity, watch)
        if watch.task is not None and not watch.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(watch.task), AHEAD_WAIT)
            except asyncio.TimeoutError:
                pass

    async def fetch_one(self, entity, watch):
        started = self.clock()
        try:
            raw = await asyncio.wait_for(self.fetch(entity), FETCH_SECONDS)
            if not raw:
                raise ValueError('empty image')
            took = self.clock() - started
            watch.took = took if watch.took is None else (watch.took + took) / 2
            digest = hashlib.sha1(raw).hexdigest()
            if digest != watch.digest:
                watch.raw, watch.digest = raw, digest
            if watch.failures:
                LOG.info('Camera %s answers again', entity)
            watch.failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - any camera's trouble
            watch.failures += 1
            # A camera that fails is asked again after a pause, up to half a minute.
            watch.retry_at = self.clock() + min(30, 5 * watch.failures)
            if watch.failures in (1, 30):
                LOG.info('No image from %s (%s)', entity, type(error).__name__)

    async def still(self, entity, pace=0, now=False, wait=FIRST_FRAME_SECONDS):
        """(raw, digest) of a camera's snapshot for a load at `pace` seconds, or None when it has none (yet). The first
        snapshot is waited for; a pace gets the snapshot of now and sets the next fetch for just before the next load;
        `now` (an alert) waits for a snapshot whose fetch starts now or is already on its way, never one kept from
        before."""
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
        elif pace > 0:
            await self.fresh(entity, watch, pace)
        if watch.raw is None:
            return None
        if pace > 0:
            self.ahead(entity, watch, pace)
        return watch.raw, watch.digest

    async def size(self, entity, wait=FIRST_FRAME_SECONDS):
        """(width, height) of the camera's snapshot of this moment, fetched now or already on its way, or None. Measured
        once per snapshot."""
        import picture_paint
        if await self.still(entity, now=True, wait=wait) is None:
            return None
        watch = self.watch(entity)
        if watch.size_of != watch.digest:
            try:
                watch.size = await asyncio.get_running_loop().run_in_executor(None, picture_paint.size_of, watch.raw)
            except Exception as error:  # noqa: BLE001
                LOG.info('The image of %s cannot be read (%s)', entity, type(error).__name__)
                return None
            watch.size_of = watch.digest
        return watch.size

    # ----- covers -----
    async def fetch_cover_one(self, entity, watch, picture):
        try:
            raw = await asyncio.wait_for(self.fetch_cover(entity), FETCH_SECONDS)
            if not raw:
                raise ValueError('empty picture')
            digest = hashlib.sha1(raw).hexdigest()
            if digest != watch.digest:
                watch.raw, watch.digest = raw, digest
            watch.picture = picture
            if watch.failures:
                LOG.info('The cover of %s comes again', entity)
            watch.failures, watch.failed = 0, None
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            watch.failures += 1
            watch.failed, watch.retry_at = picture, self.clock() + COVER_RETRY_SECONDS
            if watch.failures in (1, 30):
                LOG.info('No cover from %s (%s)', entity, type(error).__name__)

    def cover_broken(self, entity):
        """Whether the player's picture of this moment could not be fetched: the last fetch of this very address failed.
        The screensaver then shows its next step rather than a black glass where a cover never comes. The app fetches it
        again by itself every COVER_RETRY_SECONDS, and once it comes the player counts again."""
        watch = self.watches.get(entity)
        if watch is None or watch.failed is None or not self.picture or self.picture(entity) != watch.failed:
            return False
        picture = watch.failed
        watch.used = self.clock()
        if (watch.task is None or watch.task.done()) and self.clock() >= watch.retry_at:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return True
            watch.fetching = picture
            watch.task = asyncio.ensure_future(self.fetch_cover_one(entity, watch, picture))
        return True

    def cover_pending(self, entity):
        """Whether the player's picture of this moment is still on its way, longer than a screen's load waits."""
        watch = self.watches.get(entity)
        picture = self.picture(entity) if self.picture else None
        return bool(watch and picture and watch.fetching == picture and watch.task is not None and not watch.task.done())

    async def cover(self, entity, wait=FIRST_FRAME_SECONDS):
        """(raw, digest) of the player's picture as Home Assistant hands it out, fetched again only when its address
        changed; None when the player shows no picture or it cannot be fetched (yet)."""
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
        return watch.raw, watch.digest

    async def cover_raw(self, entity, wait=FIRST_FRAME_SECONDS):
        found = await self.cover(entity, wait)
        return found[0] if found else None

    # ----- a vacuum's map -----
    async def vacuum(self, entity, mark):
        """(drawing, digest) of a vacuum's map (vacuum_map.read), fetched and read once per mark; None when it cannot be
        had."""
        import vacuum_map
        held = self.vacuum_maps.get(entity)
        if held is None or held['mark'] != mark:
            try:
                raw = await self.fetch(entity)
                drawing = await asyncio.get_running_loop().run_in_executor(None, vacuum_map.read, raw)
            except Exception as error:  # noqa: BLE001 - a map that cannot be had leaves the card without one
                LOG.info('The map %s cannot be read (%s)', entity, type(error).__name__)
                return None
            held = self.vacuum_maps[entity] = {'mark': mark, 'drawing': drawing, 'digest': hashlib.sha1(raw).hexdigest()[:12]}
            while len(self.vacuum_maps) > 8:
                del self.vacuum_maps[next(iter(self.vacuum_maps))]
        return held['drawing'], held['digest']

    def vacuum_warm(self, entity, mark):
        """Fetch and read a vacuum's map ahead, in both looks, when its card's tile goes out with a new mark: the card
        that opens then only waits for its own size. Once per mark; a fetch on its way is not started twice."""
        held = self.vacuum_maps.get(entity)
        if held is not None and held['mark'] == mark:
            return
        pending = self.__dict__.setdefault('_vacuum_warming', {})
        task = pending.get(entity)
        if task is not None and not task.done():
            return

        async def warm():
            found = await self.vacuum(entity, mark)
            if found is not None:
                await asyncio.get_running_loop().run_in_executor(None, found[0].styled, True)
        try:
            pending[entity] = asyncio.ensure_future(warm())
        except RuntimeError:
            pass


def camera_modes(firmware, options):
    """(fit, fade) of a camera tile's picture: its own choices on every card the screen's firmware fills with it (1x2 and
    2x2 from 0.3.3, every size from 0.3.7); otherwise filled and plain."""
    firmware = firmware or (0, 0, 0)
    sizes = None if firmware >= CAMERA_CARD_FIRMWARE else ('tall', 'square') if firmware >= CAMERA_ART_FIRMWARE else ()
    if options.get('display') == 'live' and (sizes is None or options.get('size') in sizes):
        return ('contain' if options.get('fit') == 'contain' else 'cover'), options.get('overlay', 'name') != 'none'
    return 'cover', False


@dataclass
class Providers:
    """What the sources read of the app (docs/PICTURE_ARCHITECTURE.md, section 4): one callable per fact, so a source's
    rules and getting name what they need and their tests hand in fakes. `Providers.of(manager)` binds them to
    server.Manager, each read when it is called: a dict the Manager keeps (its states, its shelves) is read as it is then,
    and a method a test replaces later is the one called."""
    # The layout and what a screen may show.
    tiles: object              # (inbox) -> the layout's tiles
    camera_allowed: object     # (inbox, entity) -> whether a screen may show that camera (a tile of it, a recent alert)
    saver_entities: object     # (inbox) -> the entities the screensaver shows
    # Home Assistant's facts.
    states: object             # () -> every entity's state, as Home Assistant reported it last
    followed: object           # (entity) -> the player a card shows (it may follow a speaker)
    player_ground: object      # (entity, attributes) -> the colours beside a player's cover
    device_entries: object     # (entity) -> the entities of the entity's device
    registry_index: object     # () -> the entity registry, indexed
    # The pictures the app draws itself.
    map_render: object         # (tile, shape, dark, full=, focus=, move=) -> (mark, draw)
    map_meta: object           # async (mark, width, height, focus) -> a map's markers
    mosaic: object             # (entity, rows) -> (mark, draw): a player's covers at rest
    rest_pool: object          # (entity) -> (when, covers) a player at rest shows, or None
    # The library and the photos.
    thumbnail: object          # async (entity, url, title) -> a library item's picture
    shelf: object              # (inbox) -> a screen's library shelf, or None
    photo: object              # (inbox) -> the screensaver's photo of now, or None
    photo_state: object        # (inbox, options) -> the photo's state (its mark)
    # The screensaver.
    saver_choice: object       # (screen) -> what the screen's screensaver shows
    step_picture: object       # async (inbox, screen, kind) -> a plugin step's picture
    plugin_saver_kind: object  # (inbox, key) -> the kind of a plugin's screensaver step
    # The plugins.
    plugin_refused: object     # (inbox, screen, question, source) -> why a plugin's place may not have it, or None
    plugin_picture: object     # async (inbox, screen, question, source) -> a plugin's picture

    @classmethod
    def of(cls, manager):
        m = manager
        return cls(
            tiles=lambda inbox: m.layout_tiles(inbox),
            camera_allowed=lambda inbox, entity: m.camera_allowed(inbox, entity),
            saver_entities=lambda inbox: m.saver_entities(inbox),
            states=lambda: m.ha.states,
            followed=lambda entity: m.followed(entity),
            player_ground=lambda entity, attributes: m.player_ground(entity, attributes),
            device_entries=lambda entity: m.device_entries(entity),
            registry_index=lambda: m.registry_index(),
            map_render=lambda *args, **options: m.map_render(*args, **options),
            map_meta=lambda mark, width, height, focus: m.map_meta(mark, width, height, focus),
            mosaic=lambda entity, rows: m.rest_render(entity, rows),
            rest_pool=lambda entity: m.rest_pools.get(entity),
            thumbnail=lambda entity, url, title='': m.thumbnail(entity, url, title),
            shelf=lambda inbox: m.shelves.get(inbox),
            photo=lambda inbox: m.photos.raw(inbox),
            photo_state=lambda inbox, options: m.photos.state(inbox, options),
            saver_choice=lambda screen: m.saver_choice(screen),
            step_picture=lambda inbox, screen, kind: m.saver_picture(inbox, screen, kind),
            plugin_saver_kind=lambda inbox, key: m.plugin_saver_kind(inbox, key),
            plugin_refused=lambda inbox, screen, question, source: m.plugin_picture_refused(inbox, screen, question, source),
            plugin_picture=lambda inbox, screen, question, source: m.plugin_picture(inbox, screen, question, source),
        )

    def state(self, entity):
        return self.states().get(entity)


class Sources:
    """The rules and the getting, for every source kind, over what the app provides (Providers): its layouts, Home
    Assistant's states, the screensavers, the plugins and the caches it keeps."""

    def __init__(self, providers, snapshots):
        self.app, self.snapshots = providers, snapshots

    # ----- the layout's pictured tiles -----
    def pictured(self, tile):
        """Whether a saved tile shows a picture of its own: a camera set to a live picture, a media player set to its
        cover, a favourite with a thumbnail, a person's or the screen's map."""
        options = tile.get('options') or {}
        entity, display = tile.get('entity', ''), options.get('display')
        if display == 'map':
            return entity.startswith('person.') or entity == 'screen.map'
        if display == 'favorite':
            return pq.valid_entity(entity, pq.COVER_DOMAINS) and bool((options.get('play') or {}).get('thumb'))
        if display == 'live':
            return pq.valid_entity(entity, pq.CAMERA_DOMAINS)
        if display == 'cover':
            return pq.valid_entity(entity, pq.COVER_DOMAINS)
        return False

    def index_of(self, inbox):
        """For firmware that named a page's tiles by entity alone (before 0.16.0): the index of the first pictured tile
        of that entity, or -1."""
        tiles = self.app.tiles(inbox)

        def find(entity):
            return next((n for n, tile in enumerate(tiles) if tile.get('entity') == entity and self.pictured(tile)), -1)
        return find

    def _tile(self, inbox, source):
        tiles = self.app.tiles(inbox)
        n = int(source.ref)
        if n >= len(tiles):
            return None
        tile = tiles[n]
        entity = source.param('entity')
        if entity and tile.get('entity') != entity:
            return None
        return tile

    # ----- may -----
    def may(self, inbox, screen, question, source):
        """None when this screen may have this source for this question's owner; else a sentence for the log."""
        owner, kind = question.owner, source.kind
        m = self.app
        plugin = owner.kind.startswith('plugin')
        if plugin:
            # A plugin's place: what its manifest allows (how many places, which hosts, Home Assistant's own pictures of
            # its entity, the step's picture), and the core's sources only for its own entity (plugin API 0.17).
            problem = m.plugin_refused(inbox, screen, question, source)
            if problem:
                return problem
            if kind in ('camera', 'cover', 'entity') and source.ref not in self._plugin_entities(inbox, question):
                return f'{source.ref} is not this plugin place\'s entity'
            return None if kind in ('camera', 'cover', 'entity', 'step', 'url', 'ha') else f'a {kind} picture is not a plugin\'s'
        if kind == 'tile':
            tile = self._tile(inbox, source)
            if tile is None or not self.pictured(tile):
                return f'tile {source.ref} is not a pictured tile of the layout'
            return None
        if kind == 'map':
            # The tile of that index, and of the entity an older screen named with it (picture_legacy).
            tile = self._tile(inbox, source)
            if tile is None or not ((tile.get('options') or {}).get('display') == 'map' or tile.get('entity', '').startswith('person.')):
                return f'tile {source.ref} is not a map'
            return None
        if kind in ('camera', 'cover', 'vacuum'):
            if owner.kind == 'alert':
                return None
            if owner.kind == 'saver':
                return None if source.ref in m.saver_entities(inbox) else f'{source.ref} is not on the screensaver'
            return None if m.camera_allowed(inbox, source.ref) else f'{source.ref} is not on the layout'
        if kind == 'library':
            entity = source.ref.split('/', 1)[0]
            return None if entity in {t['entity'] for t in m.tiles(inbox)} else f'{entity} is not on the layout'
        if kind == 'photos':
            return None if owner.kind == 'saver' else 'the photos are the screensaver\'s'
        if kind in ('step', 'url', 'ha', 'entity'):
            return f'a {kind} picture is a plugin\'s'
        return f'no source {kind}'

    def _plugin_entities(self, inbox, question):
        """The entities whose pictures a plugin's place may show: its tile's entity, or the entity its card or step shows."""
        owner = question.owner
        if owner.kind == 'plugin_tile':
            tiles = self.app.tiles(inbox)
            tile = tiles[owner.index] if 0 <= owner.index < len(tiles) else {}
            return {e for e in (tile.get('entity'), (tile.get('options') or {}).get('plugin_entity')) if e}
        return {owner.of} if owner.of else set()

    # ----- get -----
    async def get(self, inbox, screen, question, source, place):
        """What `source` gives for `place` of `question` (Resolved)."""
        kind, m = source.kind, self.app
        if kind == 'camera':
            # An alert reads the snapshot its pictures were measured from (Snapshots.size fetched it just now).
            found = await self.snapshots.still(source.ref, pace=question.pace / 1000)
            if found is None:
                return NONE
            return Resolved(found[0], f'camera:{source.ref}:{found[1][:16]}')
        if kind == 'cover':
            # The player a card shows may follow a speaker: Snapshots fetches that one's picture (server.followed).
            found = await self.snapshots.cover(source.ref)
            if found is None:
                return PENDING if question.owner.kind == 'saver' and self.snapshots.cover_pending(source.ref) else NONE
            ground = None
            if place.fit == 'saver':
                colours = m.player_ground(source.ref, (m.state(source.ref) or {}).get('attributes') or {})
                ground = int(colours.split(',')[0], 16) if colours and colours != '-' else 0
            return Resolved(found[0], f'cover:{found[1][:16]}', ground=ground)
        if kind == 'tile':
            return await self._tile_picture(inbox, screen, question, source, place)
        if kind == 'map':
            return await self._map(inbox, screen, question, source, place)
        if kind == 'vacuum':
            return await self._vacuum(inbox, question, source, place)
        if kind == 'library':
            entity, token = source.ref.split('/', 1)
            shelf = m.shelf(inbox)
            item = shelf.get(entity, int(token)) if shelf is not None else None
            url = (item or {}).get('thumb')
            if not url:
                return NONE
            raw = await m.thumbnail(entity, url, (item or {}).get('title', ''))
            return Resolved(raw, f'library:{url}') if raw is not None else NONE
        if kind == 'photos':
            raw = m.photo(inbox)
            if raw is None:
                return PENDING
            choice = m.saver_choice(screen)
            state = m.photo_state(inbox, choice['photos'])
            fit = {'fill': 'cover', 'whole': 'whole'}.get(choice['photos'].get('fit', 'auto'), 'auto')
            moving = choice['photos'].get('motion') == 'slow'
            return Resolved(raw, f'photos:{state.get("mark")}', fit=fit, move=moving)
        if kind == 'step':
            raw = await m.step_picture(inbox, screen, m.plugin_saver_kind(inbox, question.owner.key))
            return Resolved(raw, f'step:{hashlib.sha1(raw).hexdigest()[:16]}') if raw else NONE
        if kind in ('url', 'ha', 'entity'):
            raw = await m.plugin_picture(inbox, screen, question, source)
            return Resolved(raw, f'{kind}:{source.ref}') if raw is not None else NONE
        return NONE

    async def _tile_picture(self, inbox, screen, question, source, place):
        m = self.app
        tile = self._tile(inbox, source)
        options = tile.get('options') or {}
        entity, display = tile['entity'], options.get('display')
        if display == 'map':
            mark, draw = m.map_render(tile, pq.shape_of(screen), question.dark)
            return Resolved(_Drawn(draw), f'map:{mark()}')
        if display == 'favorite':
            play = options['play']
            raw = await m.thumbnail(entity, play['thumb'], play.get('title'))
            return Resolved(raw, f'favorite:{play["thumb"]}') if raw is not None else NONE
        if display == 'cover':
            if rest_mosaic.wants(options) and rest_mosaic.at_rest(m.state(m.followed(entity))) and \
                    (m.rest_pool(entity) or (0, []))[1]:
                mark, draw = m.mosaic(entity, rest_mosaic.rows_for(options))
                return Resolved(_Drawn(draw), f'mosaic:{mark()}')
            found = await self.snapshots.cover(entity)
            return Resolved(found[0], f'cover:{found[1][:16]}') if found else NONE
        # A camera at its tile's pace (Live streams on a P4; its still keeps the default pace).
        refresh = options.get('refresh') or TILE_PACE
        found = await self.snapshots.still(entity, pace=refresh)
        fit, fade = camera_modes(pq.screen_firmware(screen), options)
        stream = ('contain' if options.get('fit') == 'contain' else 'cover') if display == 'live' and entity.startswith('camera.') else ''
        if found is None:
            return Resolved(state='none', stream=stream, fit=fit, fade=fade)
        return Resolved(found[0], f'camera:{entity}:{found[1][:16]}', fit=fit, fade=fade, stream=stream)

    async def _map(self, inbox, screen, question, source, place):
        m = self.app
        tiles = m.tiles(inbox)
        n = int(source.ref)
        tile = tiles[n]
        if (tile.get('options') or {}).get('display') != 'map':
            # A person's own tile tapped (firmware 0.21.0+): where that person is, on a map of them alone.
            tile = {'entity': tile['entity'], 'name': tile.get('name', ''), 'options': {'display': 'map', 'distance': 'neighbourhood'}}
        focus = source.param('focus')
        import map_card
        focus = focus if focus in map_card.shown(tile, m.states(), m.registry_index()) else ''
        move = map_card.move_of(source.param('move') or None)
        mark, draw = m.map_render(tile, pq.shape_of(screen), question.dark, full=True, focus=focus, move=move)
        return Resolved(_Drawn(draw, meta=lambda w, h: m.map_meta(mark(), w, h, focus)), f'map:{mark()}')

    async def _vacuum(self, inbox, question, source, place):
        m = self.app
        import vacuum_card
        import vacuum_map
        found = vacuum_card.map_entity(source.ref, m.device_entries(source.ref), m.states())
        if not found:
            return NONE
        held = await self.snapshots.vacuum(found['e'], found['m'])
        if held is None:
            return NONE
        drawing, digest = held
        dark, w, h, ground = question.dark, place.w, place.h, place.ground

        async def draw(width, height):
            # The map fitted in the middle of its place, on the card's colour (a BMP, read by the painter as any picture).
            return await asyncio.get_running_loop().run_in_executor(None, vacuum_map.render, drawing, (width, height), ground, dark)
        return Resolved(_Drawn(draw), f'vacuum:{digest}:{"d" if dark else "l"}')


class _Drawn:
    """A picture a source draws itself at its place's size (a map, the covers of a player at rest, a vacuum's map), and
    what goes with it (`meta(width, height)`: a map's markers)."""

    def __init__(self, draw, meta=None):
        self.draw, self.meta = draw, meta
