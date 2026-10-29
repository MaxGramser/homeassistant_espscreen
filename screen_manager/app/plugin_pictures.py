"""What a plugin's places may show, and the pictures at their addresses (plugin API 0.10 a tile, 0.13 a card, 0.14 a
screensaver; docs/PLUGINS.md "Pictures", docs/PICTURES.md).

A plugin's place asks like every place of the screen (picture_question, or picture_legacy for older firmware) and is
answered by the one service (picture_service). What is a plugin's own is here: the rules its manifest sets (how many
places, which hosts under `permissions.network`, Home Assistant's own pictures for a place of an entity, the screensaver
step's own picture for a face of that step) and the fetching of its addresses, through the plugins' own session
(plugin_fetch.Fetcher: public hosts only, no redirects) or Home Assistant's, kept by address. Nothing of the plugin runs
here: the manifest is read, the addresses are data.
"""
import asyncio
from collections import OrderedDict
import logging
import time

import plugin_fetch
import picture_question as pq

LOG = logging.getLogger('plugins')

PICTURE_BYTES = 2 * 1024 * 1024  # one picture as it comes from its host; a poster is a few tens of KB
CACHE_BYTES = 16 * 1024 * 1024   # pictures kept by address, the least used going first
KEEP_SECONDS = 6 * 3600        # a picture is fetched again after this long (a poster at the same address rarely changes)
FAIL_SECONDS = 60              # an address that did not come is not tried again sooner
# The screensaver step's own picture (`step:`): the cover of the music on the glass, the photo of the photos step. A face
# of that step names it instead of an address, and the app cuts the step's own picture to the place.
SAVER_PICTURE_STEPS = ('media', 'photos')


def allowed(url, manifest, tile, of_entity=None):
    """Where a picture of a plugin's place with this manifest may come from: 'network' for an address on a host the
    manifest names under permissions.network, 'home_assistant' for a picture of Home Assistant's own
    (picture_question.HA_PICTURES) on a place of an entity (`of_entity`: a card or step shown for one, else the tile's
    `domains` say), 'saver' for the step's own picture on a face of that step, None for anything else (the app fetches
    nothing it does not name). `tile` is the manifest's tile, card or screensaver."""
    if not manifest or not tile or not tile.get('pictures'):
        return None
    source = pq.source(url)
    if source is None:
        return None
    if source.kind == 'step':
        return 'saver' if tile.get('step') in SAVER_PICTURE_STEPS else None
    of_entity = bool(tile.get('domains')) if of_entity is None else of_entity
    if source.kind == 'ha':
        return 'home_assistant' if of_entity else None
    if source.kind != 'url':
        return None
    try:
        plugin_fetch.Fetcher.check_host(url, manifest['permissions']['network'])
    except plugin_fetch.FetchRefused:
        return None
    return 'network'


def refused_source(source, count, manifest, tile, of_entity=None):
    """Why a plugin's place may not show `source` (one of `count` places), as a sentence for the log; None when it may.
    The core's sources (`camera`, `cover`, `entity`, plugin API 0.17) are a place's of an entity; picture_sources checks
    that it is the place's own entity."""
    if not manifest or not tile:
        return 'the screen does not run the plugin, or the plugin has no such place'
    if not tile.get('pictures'):
        return 'the manifest gives the place no pictures'
    if count > tile['pictures']:
        return f'{count} pictures asked, the manifest allows {tile["pictures"]}'
    if source.kind in ('camera', 'cover', 'entity'):
        of = bool(tile.get('domains')) if of_entity is None else of_entity
        return None if of else f'{source.text[:80]}: the place shows no entity'
    if not allowed(source.text, manifest, tile, of_entity):
        return f'{source.text[:80]} is not an address the plugin may show'
    return None


class Pictures:
    """The pictures at plugins' addresses: fetched through the plugins' own session (plugin_fetch.Fetcher: public hosts
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
        """The picture at `url` for a place with this manifest, or None when it does not come (logged once; tried again
        after FAIL_SECONDS). A picture that came is kept KEEP_SECONDS, by address: a card that shows the cover its tile
        shows costs no fetch."""
        where = allowed(url, manifest, tile, of_entity)
        if not where or where == 'saver':  # the step's own picture comes from the app (server.saver_picture)
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

    def forget(self):
        self.cache.clear()
        self.locks.clear()
