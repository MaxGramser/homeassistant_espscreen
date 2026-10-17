"""Disposable editor hints learned from real firmware handshakes.

This cache never restores a delivery session. Every connection still negotiates
with the running firmware. Missing or corrupt cache data only restricts offline
editing until the next handshake; it cannot affect the saved page document.
"""
import re
import logging
from pathlib import Path

import atomic
from core import STORE_MAX_BAR_ITEMS, STORE_MAX_PAGES, STORE_MAX_TILES
from page_delivery import ceiling_of, grids_of, memory_of

LOG = logging.getLogger('screen_manager')
SIZES = {'single', 'wide', 'full', 'tall', 'square'}
# A span such as "3x2" (firmware 0.19.0, app 0.4.32): the sizes a screen's grid takes besides the names.
SPAN = re.compile(r'^[1-9]x[1-9]$')

def known_size(size):
    return isinstance(size, str) and (size in SIZES or SPAN.match(size) is not None)


def identity(screen):
    """What makes a screen the one its capabilities were learned from. Of its shape only the glass counts (its density,
    its look and its size whichever way it hangs): the grid it runs on and the way it hangs change while it runs
    (firmware 0.53.0+), and a session must not end because ESP Screens gave it another grid."""
    marker = {key: screen.get(key) for key in ('device_id', 'firmware_known', 'node', 'board')
              if screen.get(key) not in (None, '', 'unknown', 'unavailable')}
    shape = screen.get('shape')
    if isinstance(shape, dict):
        glass = {key: shape.get(key) for key in ('dpi', 'look') if shape.get(key) is not None}
        if isinstance(shape.get('width'), int) and isinstance(shape.get('height'), int):
            glass['size'] = sorted((shape['width'], shape['height']))
        if glass: marker['shape'] = glass
    return marker


class CapabilityCache:
    def __init__(self, path):
        self.path = Path(path)
        data = atomic.read_json(self.path, 1)
        self.records = data['screens'] if data and isinstance(data.get('screens'), dict) else {}

    def restore(self, inbox, screen, sender):
        record = self.records.get(inbox)
        current = identity(screen)
        if not current.get('device_id') or not isinstance(record, dict): return
        saved = record.get('identity')
        if not isinstance(saved, dict) or any(saved.get(key) != value for key, value in current.items()): return
        protocol, sizes = record.get('protocol'), record.get('sizes')
        if type(protocol) is not int or protocol not in (1, 2) or not isinstance(sizes, list): return
        if not all(known_size(size) for size in sizes): return
        sender.last_protocol, sender.last_tile_sizes = protocol, set(sizes)
        # Its own ceilings and memory (firmware 0.34.0+), for editing while it is offline; an older record has none.
        sender.last_max_tiles = ceiling_of(record.get('tiles'), STORE_MAX_TILES)
        sender.last_max_pages = ceiling_of(record.get('pages'), STORE_MAX_PAGES)
        sender.last_max_bar_items = ceiling_of(record.get('bar_items'), STORE_MAX_BAR_ITEMS)
        sender.last_memory = memory_of({'memory': record.get('memory')})
        # The grids it takes and keeps (firmware 0.53.0+): the editor offers them while it is offline, and the grid a save
        # gives it then waits for it.
        sender.last_grids = grids_of({'grids': record.get('grids')})

    def remember(self, inbox, screen, sender):
        marker = identity(screen)
        if not marker.get('device_id') or sender.protocol not in (1, 2): return
        record = {'identity': marker, 'protocol': sender.protocol, 'sizes': sorted(size for size in sender.tile_sizes if known_size(size))}
        if sender.max_tiles: record['tiles'] = sender.max_tiles
        if sender.max_pages: record['pages'] = sender.max_pages
        if sender.max_bar_items: record['bar_items'] = sender.max_bar_items
        # The figures it last measured: not "still measuring" (firmware 0.51.0), which says nothing for an offline screen.
        measured = sender.memory if sender.memory and sender.memory.get('room') is not None else sender.last_memory
        if measured: record['memory'] = {key: value for key, value in measured.items() if key != 'short'}
        grids = sender.grids or sender.last_grids
        if grids: record['grids'] = grids
        if self.records.get(inbox) == record: return
        self.records[inbox] = record
        self._save()

    def forget(self, inbox):
        if self.records.pop(inbox, None) is not None: self._save()

    def _save(self):
        try:
            atomic.write_json(self.path, {'version': 1, 'screens': self.records})
        except OSError as error:
            LOG.warning('Could not retain offline screen capabilities (%s)', type(error).__name__)
