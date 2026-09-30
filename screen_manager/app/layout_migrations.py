"""Historic storage/export readers, used only at an explicit import boundary.

Current documents never pass through this module. A future release can retire
this reader with a documented minimum source version and upgrade route without
changing normal saves, state delivery or the firmware.
"""
from copy import deepcopy

from core import header_items, is_key, page_target, placed, tile_size, validate_layout
from i18n import screen_t, t
from page_layout import APPEARANCE, INTERACTION, FORMAT, LayoutError, _object, attach_keys, new_id, tile_from_fields, validate_document


def _recover_tiles(raw, grid):
    """Salvage stored v1 tiles independently; never relocate an explicit slot.

    The caller has an exact durable backup. Unknown option keys remain in that
    backup and do not prevent known card fields from entering the new document.
    Imports can retain strict validation by not selecting this recovery path.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("tiles"), list):
        raise LayoutError(t('addon.errors.layout.invalid'))
    base = {'title': screen_t('screen.status.home'), 'tiles': []}
    adjusted = []
    for key in ('title', 'pages', 'page_titles', 'header', 'settings'):
        if key not in raw: continue
        # No stored layout had an empty title before firmware 0.17.0 took one: it said "Home", and still does.
        if key == 'title' and isinstance(raw[key], str) and not raw[key].strip():
            adjusted.append(key); continue
        try:
            validate_layout({**base, key: raw[key]}, grid=grid)
        except (ValueError, TypeError, KeyError, OverflowError):
            adjusted.append(key)
        else:
            base[key] = deepcopy(raw[key])
    if set(raw) - {'title', 'tiles', 'pages', 'page_titles', 'header', 'settings'}:
        adjusted.append('other')
    kept, dropped = [], []
    for tile in raw["tiles"]:
        try:
            _object(tile, {"entity", "name", "slot", "options"}, {"entity"})
            if isinstance(tile.get('entity'), str) and page_target(tile['entity']) > grid.pages:
                raise LayoutError(t('addon.errors.pages.adapt_pages'))
            # A v1 layout comes from firmware that had an entity on a screen once (a navigation tile once per page):
            # a second tile of it was never shown, so it stays out, as it always did (app 0.4.26).
            if any(other['entity'] == tile.get('entity') for other in kept) and not page_target(tile.get('entity')):
                raise LayoutError(t('addon.errors.layout.once'))
            tile = deepcopy(tile)
            if isinstance(tile.get("options"), dict):
                known = {*APPEARANCE.values(), *INTERACTION.values(), "size"}
                tile["options"] = {key: value for key, value in tile["options"].items() if key in known}
            # The old stored=True escape hatch skips placement checks for
            # unknown options. Strip only unknown keys, then validate normally
            # so one malformed card cannot poison the canonical document.
            validate_layout({**base, "tiles": [*kept, tile]}, grid=grid)
        except (ValueError, TypeError, KeyError, OverflowError):
            item = tile if isinstance(tile, dict) else {}
            dropped.append({"entity": item.get("entity") if isinstance(item.get("entity"), str) else "",
                            "name": item.get("name") if isinstance(item.get("name"), str) else "",
                            "reason": "invalid_legacy_tile"})
        else:
            kept.append(tile)
    return {**base, "tiles": kept}, dropped, adjusted


def migrate_legacy(raw, grid, id_factory=new_id, *, recover=False):
    """Convert an original v1 payload with a known source grid, or refuse.

    Call before a legacy loader packs missing slots on its default grid. The
    caller retains the original payload when conversion is not lossless.
    """
    dropped, adjusted = [], []
    if recover:
        raw, dropped, adjusted = _recover_tiles(raw, grid)
    _object(raw, {"title", "tiles", "pages", "page_titles", "header", "settings"}, {"title", "tiles"})
    if not isinstance(raw["tiles"], list):
        raise LayoutError(t('addon.errors.layout.invalid'))
    for tile in raw["tiles"]:
        _object(tile, {"entity", "name", "slot", "options", "in", "key"}, {"entity"})
    legacy = validate_layout(deepcopy(raw), stored=recover, grid=grid)
    used = max((tile["slot"] + grid.cells(tile_size(tile)) for tile in placed(legacy["tiles"])), default=0)
    count = max(1, legacy.get("pages", 1), (used + grid.slots - 1) // grid.slots)
    if recover:
        count = max(count, max((page_target(tile['entity']) for tile in legacy['tiles']), default=0))
    if count > grid.pages:
        raise LayoutError(t('addon.errors.pages.adapt_full'))
    ids = [id_factory() for _ in range(count)]
    titles = legacy.get("page_titles", [])
    pages = []
    for index, page_id in enumerate(ids):
        title = titles[index] if index < len(titles) else ""
        pages.append({
            "id": page_id, "navigation": {"excludeFromPagination": False},
            "topbar": {
                "leading": [{"id": id_factory(), "kind": "home"}],
                "title": {"source": "text", "text": title} if title else {"source": "screen"},
                "trailing": [{"id": id_factory(), **deepcopy(item)} for item in header_items(legacy)],
            }, "tiles": [],
        })
    for tile in placed(legacy["tiles"]):
        pages[tile["slot"] // grid.slots]["tiles"].append(tile_from_fields(tile, grid, ids, id_factory))
    document = {"title": legacy["title"], "homePageId": ids[0], "pages": pages}
    layout = validate_document(attach_keys(document, [tile for tile in legacy["tiles"] if is_key(tile)], id_factory), grid)
    record = {"format": FORMAT, "sourceGrid": {"columns": grid.columns, "rows": grid.rows}, "layout": layout}
    if "settings" in legacy:
        record["settings"] = deepcopy(legacy["settings"])
    if len(titles) > count:
        record["migration"] = {"inactivePageTitles": deepcopy(titles[count:])}
    if dropped:
        record.setdefault("migration", {})["droppedTiles"] = dropped
    if adjusted:
        record.setdefault("migration", {})["adjustedFields"] = adjusted
    return record
