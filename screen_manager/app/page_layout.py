"""Page-owned configuration, independent of HA state and firmware delivery.

This module is the current document boundary. Historic storage readers live in
layout_migrations.py and never run during normal document edits. Renderers may use the compiled tile list, but it is not another
editable layout. The board's Grid remains the authority for all capacity.
"""
from copy import deepcopy
from collections.abc import Mapping
import hashlib
import json
import re
import secrets

from i18n import t
from core import Grid, header_items, page_target, tile_size, validate_header, validate_layout

FORMAT = "pages-v2"
PAGE_ID = re.compile(r"[0-9a-f]{16}\Z")
INSTANCE_ID = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")
APPEARANCE = {
    "display": "display", "icon": "icon", "background": "background",
    "historyHours": "history_hours", "refresh": "refresh", "subtitle": "sub", "fit": "fit", "overlay": "overlay",
}
INTERACTION = {"tap": "tap", "inline": "inline", "controls": "controls", "action": "action"}


class LayoutError(ValueError):
    """A document cannot be represented without losing the user's choices."""


class CompiledLayouts(Mapping):
    """Immutable derived inputs for existing tile formatting/card functions.

    Construct once per committed content revision. Callers get their own values,
    so mutating an old API projection cannot edit the document or this cache.
    """
    def __init__(self, records):
        self._values = {key: legacy_projection(record, require_representable=False)
                        for key, record in records.items() if record['format'] == FORMAT}
        self._legacy = {key for key, record in records.items()
                        if record['format'] == FORMAT and legacy_compatible(record['layout'], grid_of_record(record))}

    def __getitem__(self, key): return deepcopy(self._values[key])
    def __iter__(self): return iter(self._values)
    def __len__(self): return len(self._values)

    def legacy(self, key):
        if key not in self._legacy:
            raise LayoutError(t('editor.pages.update_notice'))
        return self[key]


def new_id():
    return secrets.token_hex(8)


def fingerprint(value):
    """Content revision only; callers must not include live values or credentials."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()[:16]


def legacy_edit(record, data):
    """Preserve identities for unambiguous edits from an already-open old client.

    Old clients identify tiles by entity/slot and cannot safely express structural
    page edits. Keep page-specific fields verbatim and require a reload for those.
    """
    before = legacy_projection(record, require_representable=False)
    grid = grid_of_record(record)
    after = validate_layout(data, grid=grid)
    structure = lambda value: [(tile["entity"], tile["slot"]) for tile in value["tiles"]]
    if structure(after) != structure(before) or after.get("pages", before["pages"]) != before["pages"]:
        raise LayoutError(t('addon.errors.editor_reload'))
    for field in ("header", "page_titles"):
        if field in after and after[field] != before.get(field):
            raise LayoutError(t('addon.errors.editor_reload'))
    result = deepcopy(record["layout"])
    result["title"] = after["title"]
    page_ids = [page["id"] for page in result["pages"]]
    for wire in after["tiles"]:
        page = result["pages"][wire["slot"] // grid.slots]
        local = wire["slot"] % grid.slots
        saved = next(tile for tile in page["tiles"] if
                     tile["placement"]["row"] * grid.columns + tile["placement"]["column"] == local)
        changed = tile_from_fields(wire, grid, page_ids, lambda: saved["id"])
        for key in ("appearance", "interaction", "placement"): saved[key] = changed[key]
    return validate_document(result, grid)


def replace_tiles(record, flat):
    """Apply a validated entity-addressed tile event without rewriting pages.

    These events edit tiles and their cells, never the page order or bars. Stable
    IDs follow an existing tile; ambiguous repeated navigation sources require
    a more specific event instead of choosing an arbitrary instance.
    """
    grid = grid_of_record(record)
    flat = validate_layout(flat, grid=grid)
    result = deepcopy(record['layout'])
    used = max((tile['slot'] + grid.cells(tile_size(tile)) for tile in flat['tiles']), default=0)
    count = max(1, flat.get('pages', 1), (used + grid.slots - 1) // grid.slots)
    while len(result['pages']) < count:
        result = copy_page(result, result['pages'][-1]['id'], grid, empty=True)
    existing = []
    indexes = {page['id']: i for i, page in enumerate(result['pages'])}
    for p, page in enumerate(result['pages']):
        for tile in page['tiles']:
            existing.append((tile, _tile(tile, p, grid, indexes, result['homePageId'], set())))
        page['tiles'] = []
    page_ids = [page['id'] for page in result['pages']]
    incoming = [(wire['slot'] // grid.slots, tile_from_fields(wire, grid, page_ids), wire) for wire in flat['tiles']]
    used, assigned = set(), {}
    # Unchanged positions consume their own IDs before a moved duplicate is considered.
    for n, (_, _, wire) in enumerate(incoming):
        match = next((old for old, view in existing if view['entity'] == wire['entity'] and view['slot'] == wire['slot']), None)
        if match is not None:
            assigned[n] = match
            used.add(match['id'])
    for n, (p, tile, wire) in enumerate(incoming):
        old = assigned.get(n)
        if old is None:
            candidates = [old for old, view in existing if old['id'] not in used and view['entity'] == wire['entity']]
            if len(candidates) > 1: raise LayoutError(t('addon.errors.pages.ambiguous_tile'))
            old = candidates[0] if candidates else None
        if old is not None:
            tile['id'] = old['id']
            used.add(old['id'])
            # A Home tile follows the designation, rather than becoming a fixed link.
            if old['content'] == {'kind': 'navigation', 'target': {'kind': 'home'}}:
                tile['content'] = deepcopy(old['content'])
        result['pages'][p]['tiles'].append(tile)
    return validate_document(result, grid)


def _object(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise LayoutError(t('addon.errors.pages.fields'))
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise LayoutError(t('addon.errors.layout.position'))
    return value


def _identity(value, seen, page=False):
    if not isinstance(value, str) or not (PAGE_ID if page else INSTANCE_ID).fullmatch(value) or value in seen:
        raise LayoutError(t('addon.errors.pages.identity'))
    seen.add(value)
    return value


def grid_of_record(record):
    source = _object(record.get("sourceGrid"), {"columns", "rows"}, {"columns", "rows"})
    columns = _integer(source["columns"], 1, 64)
    rows = _integer(source["rows"], 1, 64)
    if columns * rows > 64:
        raise LayoutError(t('addon.errors.layout.position'))
    return Grid(columns, rows)


def _entity(content, page_indexes, home):
    _object(content, {"kind", "entityId", "name", "target"}, {"kind"})
    if content["kind"] == "entity":
        _object(content, {"kind", "entityId"}, {"kind", "entityId"})
        entity = content["entityId"]
        if not isinstance(entity, str) or entity.startswith("screen."):
            raise LayoutError(t('addon.errors.layout.unsupported'))
        return entity
    if content["kind"] == "builtin":
        _object(content, {"kind", "name"}, {"kind", "name"})
        if content["name"] not in ("clock", "settings"):
            raise LayoutError(t('addon.errors.layout.unsupported'))
        return "screen." + content["name"]
    if content["kind"] == "navigation":
        _object(content, {"kind", "target"}, {"kind", "target"})
        target = _object(content["target"], {"kind", "pageId"}, {"kind"})
        if target["kind"] == "home":
            _object(target, {"kind"}, {"kind"})
            destination = home
        elif target["kind"] == "page":
            _object(target, {"kind", "pageId"}, {"kind", "pageId"})
            destination = target["pageId"]
        else:
            raise LayoutError(t('addon.errors.pages.navigation'))
        if not isinstance(destination, str) or destination not in page_indexes:
            raise LayoutError(t('addon.errors.pages.page_missing'))
        return f"screen.page_{page_indexes[destination] + 1}"
    raise LayoutError(t('addon.errors.layout.unsupported'))


def footprint_size(columns, rows, grid, presentation=None):
    """Current rendering capability, separate from the persistent rectangle.

    Future sizes can extend this resolver and the renderer without
    changing page/tile identity, storage positions or the board's fixed grid.
    """
    if presentation is not None:
        supported = {"single": (1, 1), "wide": (grid.wide_span, 1), "tall": (1, 2), "square": (2, 2), "full": (grid.columns, grid.rows)}
        if not isinstance(presentation, str) or presentation not in supported or supported[presentation] != (columns, rows):
            raise LayoutError(t('addon.errors.pages.footprint'))
        return presentation
    if (columns, rows) == (1, 1): return "single"
    if (columns, rows) == (grid.wide_span, 1): return "wide"
    if (columns, rows) == (grid.columns, grid.rows): return "full"
    if (columns, rows) == (1, 2): return "tall"
    if (columns, rows) == (2, 2): return "square"
    raise LayoutError(t('addon.errors.pages.footprint'))


def _tile(tile, page_index, grid, page_indexes, home, seen):
    _object(tile, {"id", "content", "placement", "appearance", "interaction"},
            {"id", "content", "placement", "appearance", "interaction"})
    _identity(tile["id"], seen)
    placement = _object(tile["placement"], {"row", "column", "columns", "rows"}, {"row", "column", "columns", "rows"})
    row = _integer(placement["row"], 0, grid.rows - 1)
    column = _integer(placement["column"], 0, grid.columns - 1)
    columns = _integer(placement["columns"], 1, grid.columns)
    rows = _integer(placement["rows"], 1, grid.rows)
    appearance = _object(tile["appearance"], {"label", "presentation", *APPEARANCE}, {"label"})
    if 'presentation' in appearance and not isinstance(appearance['presentation'], str):
        raise LayoutError(t('addon.errors.pages.size'))
    size = footprint_size(columns, rows, grid, appearance.get("presentation"))
    interaction = _object(tile["interaction"], INTERACTION)
    options = {wire: deepcopy(appearance[key]) for key, wire in APPEARANCE.items() if key in appearance}
    options.update({wire: deepcopy(interaction[key]) for key, wire in INTERACTION.items() if key in interaction})
    if size != "single":
        options["size"] = size
    return {
        "entity": _entity(tile["content"], page_indexes, home),
        "name": appearance["label"],
        "slot": page_index * grid.slots + row * grid.columns + column,
        **({"options": options} if options else {}),
    }


def tile_from_fields(tile, grid, page_ids, id_factory=new_id):
    """Map validated entity-addressed tile fields into one page-owned instance.

    Used by HA tile commands and historic import readers. Page identity, order,
    Home and top bars are owned by the caller and cannot be rewritten here.
    """
    entity, options = tile["entity"], tile.get("options", {})
    target = page_target(entity)
    if target:
        if target > len(page_ids):
            raise LayoutError(t('addon.errors.pages.page_missing'))
        content = {"kind": "navigation", "target": {"kind": "page", "pageId": page_ids[target - 1]}}
    elif entity.startswith("screen."):
        content = {"kind": "builtin", "name": entity.split(".", 1)[1]}
    else:
        content = {"kind": "entity", "entityId": entity}
    local, size = tile["slot"] % grid.slots, tile_size(tile)
    return {
        "id": id_factory(), "content": content,
        "placement": {"row": local // grid.columns, "column": local % grid.columns,
                      "columns": grid.dimensions(size)[0], "rows": grid.dimensions(size)[1]},
        "appearance": {"label": tile["name"], **({"presentation": size} if size != "single" else {}),
                       **{key: deepcopy(options[wire]) for key, wire in APPEARANCE.items() if wire in options}},
        "interaction": {key: deepcopy(options[wire]) for key, wire in INTERACTION.items() if wire in options},
    }


def bar_items(page):
    """Resolve documented defaults at the formatter boundary, without IDs."""
    items = [{key: deepcopy(value) for key, value in item.items() if key != "id"}
             for item in page["topbar"]["trailing"]]
    return validate_header({"items": items})['items']


def compile_tiles(layout, grid):
    """Compact render/protocol input; all pages keep their full-order indexes."""
    indexes = {page["id"]: i for i, page in enumerate(layout["pages"])}
    seen = set(indexes)
    return [_tile(tile, i, grid, indexes, layout["homePageId"], seen)
            for i, page in enumerate(layout["pages"])
            for tile in sorted(page["tiles"], key=lambda t: (t["placement"]["row"], t["placement"]["column"]))]


def validate_document(data, grid):
    """Validate once against a verified grid, returning an independent document.

    Existing card validation is reused through a lossless projection. If that
    validator would change an incompatible combination, refuse it instead of
    silently changing the canonical document's appearance or footprint.
    """
    _object(data, {"title", "homePageId", "pages"}, {"title", "homePageId", "pages"})
    pages = data["pages"]
    if not isinstance(pages, list) or not 1 <= len(pages) <= grid.pages:
        raise LayoutError(t('addon.errors.pages.pages_full'))
    seen = set()
    for page in pages:
        _object(page, {"id", "navigation", "topbar", "tiles"}, {"id", "navigation", "topbar", "tiles"})
        _identity(page["id"], seen, page=True)
    page_ids = seen.copy()
    if not isinstance(data["homePageId"], str) or data["homePageId"] not in page_ids:
        raise LayoutError(t('addon.errors.pages.home_invalid'))
    for page in pages:
        navigation = _object(page["navigation"], {"excludeFromPagination"}, {"excludeFromPagination"})
        if type(navigation["excludeFromPagination"]) is not bool:
            raise LayoutError(t('addon.errors.pages.navigation'))
        bar = _object(page["topbar"], {"leading", "title", "trailing"}, {"leading", "title", "trailing"})
        title = _object(bar["title"], {"source", "text"}, {"source"})
        if title["source"] == "screen":
            _object(title, {"source"}, {"source"})
        elif title["source"] == "text":
            _object(title, {"source", "text"}, {"source", "text"})
            if not isinstance(title["text"], str) or not title["text"].strip() or len(title["text"].encode()) > 96:
                raise LayoutError(t('addon.errors.layout.page_title'))
        else:
            raise LayoutError(t('addon.errors.top_bar.invalid_setting'))
        if not isinstance(bar["leading"], list) or len(bar["leading"]) > 1:
            raise LayoutError(t('addon.errors.top_bar.invalid_setting'))
        for control in bar["leading"]:
            _object(control, {"id", "kind"}, {"id", "kind"})
            _identity(control["id"], seen)
            if control["kind"] != "home":
                raise LayoutError(t('addon.errors.top_bar.invalid_setting'))
        if not isinstance(bar["trailing"], list):
            raise LayoutError(t('addon.errors.top_bar.invalid'))
        for item in bar["trailing"]:
            if not isinstance(item, dict):
                raise LayoutError(t('addon.errors.top_bar.invalid'))
            _identity(item.get("id"), seen)
        bar_items(page)
        if not isinstance(page["tiles"], list):
            raise LayoutError(t('addon.errors.layout.invalid'))
        for tile in page["tiles"]:
            _tile(tile, 0, grid, {p["id"]: i for i, p in enumerate(pages)}, data["homePageId"], seen)
    flat = {"title": data["title"], "tiles": compile_tiles(data, grid), "pages": len(pages)}
    checked = validate_layout(flat, grid=grid)
    # The legacy validator sorts by slot and normalizes documented defaults.
    # Incompatible size/action combinations must not escape into a document.
    if checked["title"] != data["title"] or checked["tiles"] != flat["tiles"]:
        raise LayoutError(t('addon.errors.pages.normalization'))
    return deepcopy(data)



def legacy_compatible(layout, grid):
    """Whether a validated page document fits the older firmware's behaviour."""
    pages = layout['pages']
    items = bar_items(pages[0])
    return (layout['homePageId'] == pages[0]['id']
            and all(not page['navigation']['excludeFromPagination'] and page['topbar']['leading']
                    and bar_items(page) == items for page in pages)
            and all(footprint_size(tile['placement']['columns'], tile['placement']['rows'], grid, tile['appearance'].get('presentation'))
                    not in ('tall', 'square') and tile['interaction'].get('controls') not in ('tilt', 'buttons_tilt', 'position_tilt', 'setpoint_mode')
                    for page in pages for tile in page['tiles']))


def legacy_projection(record, require_representable=True):
    """Derive v1 input without making it authoritative or silently flattening bars."""
    grid = grid_of_record(record)
    layout = validate_document(record["layout"], grid)
    pages = layout["pages"]
    items = bar_items(pages[0])
    if require_representable and not legacy_compatible(layout, grid):
        raise LayoutError(t('editor.pages.update_notice'))
    titles = [page["topbar"]["title"].get("text", "") for page in pages]
    titles += record.get("migration", {}).get("inactivePageTitles", [])
    while titles and not titles[-1]:
        titles.pop()
    return {
        "title": layout["title"], "pages": len(pages), "tiles": compile_tiles(layout, grid),
        "header": {"items": items}, **({"page_titles": titles} if titles else {}),
        **({"settings": deepcopy(record["settings"])} if "settings" in record else {}),
    }


def pagination(layout):
    return [i for i, page in enumerate(layout["pages"]) if not page["navigation"]["excludeFromPagination"]]


def sequential_target(layout, current, direction):
    sequence = pagination(layout)
    if current not in sequence or direction not in (-1, 1):
        return current
    index = sequence.index(current) + direction
    return sequence[index] if 0 <= index < len(sequence) else current


def delete_page(layout, page_id, grid):
    """One operation, including incoming links and Home; caller owns undo."""
    result = deepcopy(layout)
    if len(result["pages"]) == 1 or page_id not in {p["id"] for p in result["pages"]}:
        raise LayoutError(t('addon.errors.pages.delete'))
    result["pages"] = [p for p in result["pages"] if p["id"] != page_id]
    if result["homePageId"] == page_id:
        result["homePageId"] = result["pages"][0]["id"]
    for page in result["pages"]:
        page["tiles"] = [tile for tile in page["tiles"] if tile["content"].get("target") != {"kind": "page", "pageId": page_id}]
    return validate_document(result, grid)


def copy_page(layout, page_id, grid, empty=False, id_factory=new_id):
    """Duplicate only if device constraints allow it; never omit conflicts."""
    result = deepcopy(layout)
    source = next((p for p in result["pages"] if p["id"] == page_id), None)
    if source is None:
        raise LayoutError(t('addon.errors.pages.page_missing'))
    copied = deepcopy(source)
    copied["id"] = id_factory()
    if empty:
        copied["tiles"] = []
        copied["navigation"]["excludeFromPagination"] = False
    for item in copied["topbar"]["leading"] + copied["topbar"]["trailing"] + copied["tiles"]:
        item["id"] = id_factory()
    for tile in copied["tiles"]:
        if tile["content"].get("target") == {"kind": "page", "pageId": page_id}:
            tile["content"]["target"]["pageId"] = copied["id"]
    result["pages"].insert(result["pages"].index(source) + 1, copied)
    return validate_document(result, grid)
