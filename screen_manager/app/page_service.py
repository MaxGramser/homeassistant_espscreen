"""Page save and delivery policy, separate from HTTP and HA event routing.

The manager argument supplies discovery, formatting, storage and notification
services. This module owns capability gates and commit-before-delivery order;
it does not import the server or keep another copy of a page document.
"""
import time
import camera_feed
import page_delivery
from core import BUILTIN, CAMERA_DOMAINS, FREE_PAGES_MIN_FIRMWARE, board_of, firmware_features, page_target, state_message, version_text
from i18n import t, shown, english
from page_layout import (FORMAT as PAGE_FORMAT, LayoutError, bar_items, compile_tiles,
                         grid_of_record, grown, legacy_projection, validate_document)


def preflight_update(manager, inbox):
    """Do not install firmware that cannot use this screen's saved data."""
    inbox = manager.aliases.get(inbox, inbox)
    record = manager.store.retry_migrations().get(inbox)
    if record is None: return  # A newly installed screen has no saved layout yet.
    if record['format'] != PAGE_FORMAT:
        raise LayoutError(t('addon.errors.pages.migration_pending'))
    grid = manager.verified_grid(inbox)
    if grid is None or grid != grid_of_record(record):
        raise LayoutError(t('addon.errors.pages.adaptation'))
    validate_document(record['layout'], grid)
    manager.preflight_pages(inbox, record)


def preflight_pages(manager, inbox, record):
    """Bound immutable options and current values before save or install."""
    flat = compile_tiles(record['layout'], grid_of_record(record))
    values = [state_message(i, tile, manager.ha.states) for i, tile in enumerate(flat)]
    bars = [manager.header_message({'header': {'items': bar_items(page)}})['items'] for page in record['layout']['pages']]
    try: page_delivery.prepare(inbox, record, manager.page_region(), values, bars)
    except page_delivery.Refused as error: raise LayoutError(shown(error.message)) from error


def preflight_profile(manager, data):
    if not isinstance(data, dict) or data.get('action') != 'install': return
    profiles = manager.firmware.profile_names()
    for screen in manager.screens():
        profile, _ = manager.updates.resolve(screen, profiles)
        if profile and profile == data.get('file'):
            manager.preflight_update(screen['id'])


def save_pages(manager, inbox, data):
    """Commit a validated page document before any delivery is scheduled."""
    if not isinstance(data, dict) or set(data) - {'format', 'layout', 'revision', 'workspace', 'adaptation'} or data.get('format') != PAGE_FORMAT:
        raise LayoutError(t('addon.errors.editor_reload'))
    inbox = manager.aliases.get(inbox, inbox)
    screen = manager.screen(inbox)
    if screen is None: raise LayoutError(t('addon.errors.not_paired'))
    previous = manager.store.get(inbox)
    grid = manager.verified_grid(inbox) or (grid_of_record(previous) if previous and previous['format'] == PAGE_FORMAT else None)
    if grid is None: raise LayoutError(t('addon.errors.pages.source_grid'))
    adaptation = data.get('adaptation')
    if adaptation is not None:
        expected = {'from': previous.get('sourceGrid') if previous else None, 'to': {'columns': grid.columns, 'rows': grid.rows}}
        if not previous or previous['format'] != PAGE_FORMAT or adaptation != expected or manager.verified_grid(inbox) is None:
            raise LayoutError(t('addon.errors.pages.adaptation'))
    document = validate_document(data.get('layout'), grid)
    candidate = {'format': PAGE_FORMAT, 'sourceGrid': {'columns': grid.columns, 'rows': grid.rows}, 'layout': document}
    sender = manager.page_sender(inbox, screen)
    verified_protocol = (sender.protocol if sender.protocol is not None else sender.last_protocol) if sender else None
    if verified_protocol != 2:
        # An existing v2-only document survives disconnects and downgrades.
        # Introducing new-only features first requires proof from the board.
        already_requires_v2 = False
        if previous and previous['format'] == PAGE_FORMAT:
            try: legacy_projection(previous)
            except LayoutError: already_requires_v2 = True
        if not already_requires_v2:
            try: legacy_projection(candidate)
            except LayoutError:
                raise LayoutError(t('editor.pages.update_notice')) from None
    flat = legacy_projection(candidate, require_representable=False)
    required_sizes = {tile.get('options', {}).get('size', 'single') for tile in flat['tiles']} & {'tall', 'square'}
    supported_sizes = getattr(sender, 'tile_sizes' if sender.protocol is not None else 'last_tile_sizes', set()) if sender else set()
    if required_sizes and not required_sizes <= supported_sizes:
        raise LayoutError(t('addon.errors.pages.update_tall'))
    features = firmware_features(manager.firmware_version(inbox, screen), grid)
    if len(flat['tiles']) > features['tile_limit']:
        raise LayoutError(t('addon.errors.layout.tiles_max', n=features['tile_limit']))
    # More pages than 64 tiles fill needs firmware 0.18.0, and a screen that said so in its hello has it.
    if len(document['pages']) > features['page_limit'] and not (sender and sender.free_pages):
        raise LayoutError(t('addon.errors.layout.firmware_first', version=version_text(FREE_PAGES_MIN_FIRMWARE)))
    if any(tile['entity'].split('.')[0] in CAMERA_DOMAINS for tile in flat['tiles']) and board_of(screen) not in camera_feed.BOXES:
        raise LayoutError(t('addon.errors.layout.camera_unsupported'))
    needed = manager.needs_firmware(inbox, flat, screen)
    if needed: raise LayoutError(t('addon.errors.layout.firmware_first', version=needed))
    _, entities = manager.inventory()
    known = {e['id'] for e in entities} | set(BUILTIN)
    existing = {tile['entity'] for tile in manager.layouts.get(inbox, {}).get('tiles', [])}
    if any(tile['entity'] not in known and tile['entity'] not in existing and not page_target(tile['entity']) for tile in flat['tiles']):
        raise LayoutError(t('addon.errors.layout.entity_gone'))
    existing_headers = {item['entity'] for page in previous['layout']['pages'] for item in bar_items(page)
                        if item['type'] == 'entity'} if previous and previous['format'] == PAGE_FORMAT else set()
    for page in document['pages']:
        if any(item['type'] == 'entity' and item['entity'] not in known and item['entity'] not in manager.ha.states
               and item['entity'] not in existing_headers
               for item in bar_items(page)):
            raise LayoutError(t('addon.errors.top_bar.entity_gone'))
    # Configuration options, including explicit actions, must fit before a
    # durable save. Delivery checks the full refreshed state again because
    # forecasts, history and HA attributes can change independently.
    manager.preflight_pages(inbox, candidate)
    record = manager.store.save(inbox, document, data.get('revision'), data.get('workspace'), adapt_grid=adaptation is not None)
    manager.sent.pop(inbox, None)
    manager.status[inbox] = 'Saved, waiting for screen'
    manager.history_wake.set()
    manager.ha.changed.set()
    manager.notify()
    return record


def grow_record(manager, inbox, record):
    """The saved layout on the grid the screen now reports, when that grid only grew; else the record as it was.

    Only the screen's own report counts: a board's catalog grid may be newer than the firmware still on the screen."""
    grid = manager.reported_grid(inbox)
    if grid is None or grid == grid_of_record(record):
        return record
    try:
        layout = grown(record['layout'], grid_of_record(record), grid)
        if layout is None: return record
        record = manager.store.save(inbox, layout, record['revision'], adapt_grid=True)
    except LayoutError:
        return record
    manager.sent.pop(inbox, None)
    manager.notify()
    return record


async def sync_pages(manager, inbox, record, screen, dirty=None, force=False, context=None):
    record = grow_record(manager, inbox, record)
    grid = manager.verified_grid(inbox)
    if grid is None or grid != grid_of_record(record):
        manager.status[inbox] = english('addon.errors.pages.adaptation')
        return False
    sender = manager.page_sender(inbox, screen)
    flat = manager.layouts[inbox]
    cached = manager.page_values.get(inbox)
    # A light group's lamps go to a screen that said it takes them (firmware 0.3.9+); the first hello can change that.
    lamps = getattr(sender, 'group_lamps', False)
    full = (force or dirty is None or not cached or cached['revision'] != record['revision'] or cached['context'] != context
            or cached.get('lamps') != lamps)
    if full:
        dependencies = [{item['entity'] for item in bar_items(page) if item['type'] == 'entity'} for page in record['layout']['pages']]
    else:
        dependencies = cached['dependencies']
    values = []
    for i, tile in enumerate(flat['tiles']):
        reuse = not full and tile['entity'] not in dirty and dirty.isdisjoint(manager.related_entities(tile))
        if reuse and tile['entity'].startswith('weather.') and manager.forecast_due(tile['entity']): reuse = False
        values.append(cached['values'][i] if reuse else await manager.tile_message(i, tile, lamps=lamps))
    bars = [cached['bars'][i] if not full and dirty.isdisjoint(dependencies[i]) else
            manager.header_message({'header': {'items': bar_items(page)}})['items'] for i, page in enumerate(record['layout']['pages'])]
    expected = record['revision']
    def current():
        saved = manager.store.get(inbox)
        return saved is not None and saved.get('revision') == expected
    before = sender.confirmed
    if before != page_delivery.configuration(record, manager.page_region()):
        manager.status[inbox] = 'Applying'
        manager.notify()
    try:
        rev = await sender.synchronize(inbox, record, manager.page_region(), values, bars, current)
    except page_delivery.Superseded:
        manager.ha.changed.set()
        return True
    except page_delivery.Refused as error:
        manager.status[inbox] = error.message
        return False
    if not current():
        manager.ha.changed.set()
        return True
    manager.sent[inbox] = {'protocol': 2, 'rev': rev, 'saved_revision': expected}
    manager.page_values[inbox] = {'revision': expected, 'context': context, 'dependencies': dependencies, 'values': values, 'bars': bars,
                                  'lamps': lamps}
    # The hello of this delivery told us the screen takes lamps: the next round sends them.
    if getattr(sender, 'group_lamps', False) != lamps: manager.ha.changed.set()
    manager.status[inbox] = 'Applied'
    manager.last[inbox] = time.monotonic()
    if before != rev: manager.pinged[inbox] = manager.last[inbox]
    return before != rev
