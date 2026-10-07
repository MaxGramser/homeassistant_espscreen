"""Disposable editor hints learned from real firmware handshakes.

This cache never restores a delivery session. Every connection still negotiates
with the running firmware. Missing or corrupt cache data only restricts offline
editing until the next handshake; it cannot affect the saved page document.
"""
import json
import re
import logging
import os
from pathlib import Path
import tempfile

from core import STORE_MAX_BAR_ITEMS, STORE_MAX_PAGES, STORE_MAX_TILES
from page_delivery import ceiling_of, memory_of

LOG = logging.getLogger('screen_manager')
SIZES = {'single', 'wide', 'full', 'tall', 'square'}
# A span such as "3x2" (firmware 0.19.0, app 0.4.32): the sizes a screen's grid takes besides the names.
SPAN = re.compile(r'^[1-9]x[1-9]$')

def known_size(size):
    return isinstance(size, str) and (size in SIZES or SPAN.match(size) is not None)


def identity(screen):
    return {key: screen.get(key) for key in ('device_id', 'firmware_known', 'node', 'board', 'shape')
            if screen.get(key) not in (None, '', 'unknown', 'unavailable')}


class CapabilityCache:
    def __init__(self, path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text())
            self.records = data['screens'] if data.get('version') == 1 and isinstance(data.get('screens'), dict) else {}
        except (OSError, ValueError, AttributeError, TypeError):
            self.records = {}

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
        if self.records.get(inbox) == record: return
        self.records[inbox] = record
        self._save()

    def forget(self, inbox):
        if self.records.pop(inbox, None) is not None: self._save()

    def _save(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
                temporary = handle.name
                json.dump({'version': 1, 'screens': self.records}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            LOG.warning('Could not retain offline screen capabilities (%s)', type(error).__name__)
        finally:
            if temporary and os.path.exists(temporary): os.unlink(temporary)
