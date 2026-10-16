"""Pictures on a plugin's tile (plugin API 0.10, docs/PLUGINS.md "Pictures") and on a plugin's card over the page
(0.13): the app's side of the question a plugin tile or card asks for its places (tile_picture.h "parts",
plugin_host.cpp).

The screen asks with the event every tile picture is asked with (`esphome.screen_camera` with `tiles`, `idx`, `bg`,
`dark`, `atlas`), plus `src`, the address of each frame, and `fit`, how each fills its frame. The app checks that the
tile is a plugin tile of the screen's layout whose manifest gives it places, and each address against what the manifest
allows (`allowed`): a host of `permissions.network`, or a picture of Home Assistant's own for a tile of an entity. A
card's question has `card` and `for` (the entity it shows) beside them, and is a card of a plugin on that screen whose
manifest gives it places; Home Assistant's own pictures are for a card shown for an entity of the screen's layout. It
fetches each address once (a cache by address, so a page that comes back costs no fetch), paints the atlas as every
tile picture is painted (tile_art.encode) and answers with a link to it, as it answers a camera tile. Nothing of the
plugin runs here: the manifest is read, the addresses are data.
"""
import asyncio
import json
import logging
import re
import time
from collections import OrderedDict

import core
import plugin_fetch
import plugin_manifest as pm
import tile_art

LOG = logging.getLogger('plugins')

FITS = ('cover', 'contain')
MAX_URL = 512                  # an address, as a fetch's URL
PICTURE_BYTES = 2 * 1024 * 1024  # one picture as it comes from its host; a poster is a few tens of KB
CACHE_BYTES = 16 * 1024 * 1024   # pictures kept by address, the least used going first
KEEP_SECONDS = 6 * 3600        # a picture is fetched again after this long (a poster at the same address rarely changes)
FAIL_SECONDS = 60              # an address that did not come is not tried again sooner
# The pictures of Home Assistant's own a tile may show: an entity's `entity_picture` as the map takes a person's
# (server.HomeAssistant.entity_picture reads exactly these, with the app's own token).
HA_PICTURES = ('/api/image/serve/', '/api/image_proxy/', '/local/')


class Question:
    """What one plugin tile asked for."""
    __slots__ = ('entity', 'plugin', 'tile', 'index', 'atlas', 'sources', 'fits', 'ground', 'dark', 'turns', 'mirrors',
                 'card', 'of')

    def __init__(self, entity, plugin, tile, index, atlas, sources, fits, ground, dark, turns=None, mirrors=None,
                 card=False, of=''):
        self.entity, self.plugin, self.tile, self.index = entity, plugin, tile, index
        self.atlas, self.sources, self.fits, self.ground, self.dark = atlas, sources, fits, ground, dark
        self.turns = turns or [''] * len(sources)
        self.mirrors = mirrors or [False] * len(sources)
        # A card's question (0.13): `tile` is then the card's id, `index` None, `of` the entity it shows ('' for none).
        self.card, self.of = card, of

    def styles(self):
        """How each frame is painted (tile_art.layers): its fit, its turn and whether a reflection goes under it."""
        return [('fill' if fit == 'cover' else 'within', turn, mirror)
                for fit, turn, mirror in zip(self.fits, self.turns, self.mirrors)]


def parse(request, canvas):
    """The Question a plugin tile's request carries, or None when it is not one the app can serve: `tiles` one plugin
    tile, `idx` its index, `atlas` its frames within `canvas` (the screen's shape), `src` one address per frame and
    `fit` one of FITS per frame (cover without), `bg` the card's colour behind the corners; and, when a place asks
    for them, `turn` one of tile_art.TURNS per frame and `mirror` 0 or 1 per frame. The frames may overlap: they are the
    layers of one card."""
    if not isinstance(request, dict):
        return None
    entity = request.get('tiles')
    parts = core.plugin_tile(entity) if isinstance(entity, str) else None
    idx, ground = request.get('idx'), request.get('bg')
    card = request.get('card') == '1'
    of = request.get('for') or ''
    if card and (not isinstance(of, str) or of and not core.plugin_entity(of)):
        return None
    if not parts or not card and (not isinstance(idx, str) or not idx.isdigit() or len(idx) > 3):
        return None
    if not isinstance(ground, str) or not re.fullmatch(r'[0-9A-Fa-f]{6}', ground):
        return None
    try:
        sources = json.loads(request.get('src') or '')
        fits = json.loads(request.get('fit') or '[]')
    except (ValueError, TypeError):
        return None
    if not isinstance(sources, list) or not 1 <= len(sources) <= pm.MAX_PICTURES or not isinstance(fits, list):
        return None
    if not all(isinstance(s, str) and 0 < len(s) <= MAX_URL for s in sources):
        return None
    fits = fits or ['cover'] * len(sources)
    if len(fits) != len(sources) or any(f not in FITS for f in fits):
        return None
    try:
        turns = json.loads(request['turn']) if request.get('turn') else [''] * len(sources)
        mirrors = json.loads(request['mirror']) if request.get('mirror') else [0] * len(sources)
    except (ValueError, TypeError):
        return None
    if not isinstance(turns, list) or len(turns) != len(sources) or any(t not in tile_art.TURNS for t in turns):
        return None
    if not isinstance(mirrors, list) or len(mirrors) != len(sources) or any(m not in (0, 1) for m in mirrors):
        return None
    atlas = tile_art.parse(request.get('atlas'), canvas, len(sources), overlap=True)
    if atlas is None:
        return None
    return Question(entity, parts[0], parts[1], None if card else int(idx), atlas, sources, fits, int(ground, 16),
                    str(request.get('dark') or '') == '1', turns, [bool(m) for m in mirrors], card, of)


def allowed(url, manifest, tile, of_entity=None):
    """Where a picture of a tile (or a card, 0.13) with this manifest may come from: 'network' for an address on a host
    the manifest names under permissions.network, 'home_assistant' for a picture of Home Assistant's own (HA_PICTURES)
    on a tile of an entity (`of_entity`: a card shown for one), None for anything else (the app fetches nothing it does
    not name)."""
    if not manifest or not tile or not tile.get('pictures'):
        return None
    of_entity = bool(tile.get('domains')) if of_entity is None else of_entity
    if url.startswith('/'):
        path = url.split('?', 1)[0]
        if of_entity and path.startswith(HA_PICTURES) and '..' not in path and '//' not in url[1:]:
            return 'home_assistant'
        return None
    try:
        plugin_fetch.Fetcher.check_host(url, manifest['permissions']['network'])
    except plugin_fetch.FetchRefused:
        return None
    return 'network'


def refused(question, manifest, tile, of_entity=None):
    """Why a question is not answered with pictures, as a sentence for the log; None when it may be. `tile` is the
    manifest's tile, or its card for a card's question."""
    what = 'card' if question.card else 'tile'
    if not manifest or not tile:
        return f'the screen does not run the plugin, or the plugin has no such {what}'
    if not tile.get('pictures'):
        return f'the manifest gives the {what} no pictures'
    if len(question.sources) > tile['pictures']:
        return f'{len(question.sources)} pictures asked, the manifest allows {tile["pictures"]}'
    for url in question.sources:
        if not allowed(url, manifest, tile, of_entity):
            return f'{url[:80]} is not an address the plugin may show'
    return None


class Pictures:
    """The pictures of every plugin tile: fetched through the plugins' own session (plugin_fetch.Fetcher: public hosts
    only, no redirects) or Home Assistant's (`ha_picture(path)`, the app's own token), kept by address."""

    def __init__(self, fetcher, ha_picture=None, clock=time.monotonic):
        self.fetcher, self.ha_picture, self.clock = fetcher, ha_picture, clock
        self.cache = OrderedDict()   # url -> {'raw': bytes or None, 'at': when it came, or failed}
        self.locks = {}

    def _bytes(self):
        return sum(len(e['raw'] or b'') for e in self.cache.values())

    def _keep(self, url, raw):
        self.cache[url] = {'raw': raw, 'at': self.clock()}
        self.cache.move_to_end(url)
        while len(self.cache) > 256 or self._bytes() > CACHE_BYTES:
            self.cache.popitem(last=False)

    async def fetch(self, url, manifest, tile, of_entity=None):
        """The picture at `url` for a tile (or card) with this manifest, or None when it does not come (logged once;
        tried again after FAIL_SECONDS). A picture that came is kept KEEP_SECONDS, by address: a card that shows the
        cover its tile shows costs no fetch."""
        where = allowed(url, manifest, tile, of_entity)
        if not where:
            return None
        entry = self.cache.get(url)
        if entry is not None:
            age = self.clock() - entry['at']
            if entry['raw'] is not None and age < KEEP_SECONDS or entry['raw'] is None and age < FAIL_SECONDS:
                self.cache.move_to_end(url)
                return entry['raw']
        lock = self.locks.setdefault(url, asyncio.Lock())
        async with lock:
            entry = self.cache.get(url)
            if entry is not None and self.clock() - entry['at'] < FAIL_SECONDS:
                return entry['raw']
            raw = None
            try:
                if where == 'home_assistant':
                    if self.ha_picture is None:
                        raise OSError('no Home Assistant')
                    raw = await asyncio.wait_for(self.ha_picture(url), plugin_fetch.TIMEOUT)
                else:
                    raw = await self.fetcher.download_bytes(url, {}, manifest['permissions']['network'], PICTURE_BYTES)
                if not raw:
                    raise OSError('empty')
            except Exception as error:   # the network, the host, its answer
                raw = None
                LOG.info('Plugin %s: no picture from %s (%s)', manifest['id'], url[:120], str(error)[:120] or type(error).__name__)
            self._keep(url, raw)
            if len(self.locks) > 64:
                self.locks.pop(next(iter(self.locks)))
        return raw

    async def atlas(self, question, raws, compact=False):
        """The BMP of a question's frames with their pictures (None where one did not come: the frame stays the card's
        colour), painted as every tile picture is."""
        return await asyncio.get_running_loop().run_in_executor(
            None, tile_art.layers, raws, question.ground, question.atlas, question.styles(), compact)

    def forget(self):
        self.cache.clear()
        self.locks.clear()
