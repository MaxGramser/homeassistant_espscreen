"""Layoutbot, the editor's chat, a PROTOTYPE (docs/open-issues/layoutbot.md): one sentence in, a proposed page document
out, made by the LLM the person has already connected to Home Assistant.

What it knows: the screen's page document and grid, the entities the inventory lists (id, name, area) and the icons a
page or section may take. It asks Home Assistant's AI Task (`ai_task.generate_data`, HA 2025.8+) for a small *plan* in a
fixed structure (pages, their sections, entity ids), never for a document: ids, placements and sizes are made here,
and the result goes through `validate_document` like any save. The plan can only add pages, sections and tiles of
entities that exist, take tiles off and rename; it has no word for an action, so nothing it says can switch a device.
Nothing is saved: the editor shows the proposal and the person takes it (one undo step) or leaves it.

What it does not know: the editor's per-type defaults (startTile: sizes, cover controls), the memory budget, plugins.
Those stay with the editor when this is built for real; here every new tile is one cell. tests/test_layoutbot.py.
"""
from copy import deepcopy
import json
import math
import time

import catalogue
import tile_icons
from page_layout import LayoutError, all_tiles, new_id, placed_tiles, sections_of, validate_document

# The longest sentence the editor sends, and how long an answer may take: an AI Task of a cloud model answered in 2 to
# 15 seconds on a home of 1000 entities (docs/LAYOUTBOT.md, "Measured"); a local model on small hardware takes longer.
PROMPT_CHARS = 500
WAIT_SECONDS = 120
GENERATE_DATA = 1  # AITaskEntityFeature.GENERATE_DATA (homeassistant/components/ai_task/const.py)


def agents(states):
    """The AI Tasks of this Home Assistant that can make data: [{id, name}], by name. None: the editor shows no bot."""
    found = [{"id": eid, "name": (state.get("attributes") or {}).get("friendly_name") or eid}
             for eid, state in (states or {}).items()
             if eid.startswith("ai_task.") and isinstance((state.get("attributes") or {}).get("supported_features"), int)
             and state["attributes"]["supported_features"] & GENERATE_DATA and state.get("state") != "unavailable"]
    return sorted(found, key=lambda agent: agent["name"].lower())


async def preferred(request, found):
    """The AI Task the person chose in Home Assistant for "generate data" (ai_task/preferences/get), when it is one
    that can; else the first one."""
    try:
        chosen = ((await request("ai_task/preferences/get")) or {}).get("gen_data_entity_id")
    except Exception:  # noqa: BLE001 - an older Home Assistant without the preference: the first one does
        chosen = None
    ids = [agent["id"] for agent in found]
    return chosen if chosen in ids else (ids[0] if ids else None)


# How a new page is dressed (_Plan.ladder): which control of one row a wide card of a type shows first, of those the
# entity offers (the rest of the catalogue's order follows); the types whose larger card is a larger picture; and which
# types grow first when there is room, the ones with the most to show.
PREFERRED = {"light": ("brightness",), "media_player": ("playback", "volume"), "climate": ("setpoint", "mode"),
             "cover": ("buttons", "position"), "fan": ("speed",), "vacuum": ("buttons",)}
PICTURES = {"camera", "image"}
RANK = {"media_player": 0, "climate": 0, "camera": 1, "vacuum": 1, "light": 2, "cover": 2, "fan": 3, "humidifier": 3,
        "water_heater": 3, "valve": 4, "lock": 4}


# The plan, in Home Assistant's own structure words (ai_task services.yaml `structure`: a field per key, each with a
# selector). An object selector with `fields` and `multiple` becomes an array of objects, an entity selector with
# `multiple` an array of strings, in the JSON schema every provider receives (helpers/llm.py selector_serializer), so
# OpenAI, Anthropic, Google and Ollama all get the same one. A field inside an object selector takes only `label`,
# `required` and `selector` (helpers/selector.py ObjectSelectorField, HA 2026.11): what each field means is said in RULES.
#
# Nested and declarative on purpose: a flat list of operations with optional fields made gpt-4o-mini stop after the
# first one, writing `},{` into a text field (docs/open-issues/layoutbot.md, "Measured").
TEXT = {"selector": {"text": {}}}
ENTITIES = {"selector": {"entity": {"multiple": True}}}
STRUCTURE = {
    "reply": {"description": "One or two short sentences to the person, in their language: what you changed, or why "
                             "you could not.", "required": True, "selector": {"text": {}}},
    "pages": {
        "description": "The pages to add or change. Empty when nothing should change.",
        "required": True,
        "selector": {"object": {"multiple": True, "fields": {
            "screen": TEXT, "page": TEXT, "title": TEXT, "icon": TEXT,
            "sections": {"selector": {"object": {"multiple": True, "fields": {
                "title": {"required": True, **TEXT}, "icon": TEXT, "entities": {"required": True, **ENTITIES}}}}},
            "tiles": ENTITIES,
        }}},
    },
    "remove": {"description": "Entity ids whose tiles come off the screen. Usually empty.", **ENTITIES},
}

RULES = """You arrange the pages of a wall-mounted Home Assistant touch screen. You never control devices: you only \
change the layout, by returning pages.

The screen: {columns} columns x {rows} rows of cells per page, at most {pages} pages and {tiles} tiles in all. \
A page holds tiles; every tile shows one entity in one cell. {sections_rule}

Each item of `pages` is one page:
- screen: empty for this screen. Only when the person asks for other screens or for all of them: the name of another \
screen from the list of other screens, or "all" for every screen, this one included.
- page: empty for a NEW page (never a number for a new page), or the number of an existing page to add to.
- title: the page's title (a new page always has one; for an existing page only when the person asks to rename it).
- icon: one name from the icon list.
- sections: titled groups of tiles on that page, each with title, icon and entities (entity ids, in the order to show). \
For an existing page, a section with the title of one it has adds to that one.
- tiles: entity ids that stand on the page outside any section.
`remove`: entity ids to take off the screen, only when the person asks.

Use only entity ids from the list below, exactly as written. When the person names a kind of device ("all blinds", \
"the lights in the kitchen"), take every matching entity from the list, by its domain, name and area. Leave out \
entities that are clearly settings or diagnostics unless asked. If nothing matches, or the person asks you to control \
a device, return no pages and say so. Titles are short (at most 3 words) and in the person's language. Keep existing \
pages as they are unless the person asks to change them.

Icons: {icons}

Existing pages of this screen ("{name}"):
{pages_text}
{others_text}

Entities (id | name | area):
{entities_text}

The person asks: {prompt}"""

SECTIONS_RULE = "A section is a titled block of tiles on a page."
NO_SECTIONS_RULE = "This screen has no sections: put every entity in `tiles`."


def entity_lines(entities, domains=None):
    """One line per entity the inventory lists: `light.kitchen | Kitchen spots | Kitchen`, sorted by area then id.

    `domains`: only these domains (None: all). The name is left out when the id already says it, to keep the prompt
    small; a 1000-entity home is about 60 kB of text this way (docs/open-issues/layoutbot.md, "Measured")."""
    lines = []
    for item in sorted(entities, key=lambda e: (e.get("area") or "~", e["id"])):
        domain = item["id"].split(".", 1)[0]
        if domains is not None and domain not in domains:
            continue
        name = (item.get("name") or "").strip()
        shown = "" if name.lower().replace(" ", "_") == item["id"].split(".", 1)[1] else name
        lines.append(" | ".join([item["id"], shown, item.get("area") or ""]).rstrip(" |"))
    return "\n".join(lines)


def _shown(tile):
    return tile["content"].get("entityId") or tile["content"].get("kind")


def page_lines(document):
    """The existing pages, numbered as the editor numbers them, with their sections and the entities on them."""
    out = []
    for number, page in enumerate(document["pages"], 1):
        title = page["topbar"]["title"].get("text")
        parts = [f'page {number} "{title}"' if title else f"page {number} (no title of its own)"]
        if page["tiles"]:
            parts.append("tiles: " + ", ".join(map(_shown, page["tiles"])))
        parts += [f'section "{s["title"]}": ' + ", ".join(map(_shown, s["tiles"])) for s in sections_of(page)]
        out.append("; ".join(parts))
    return "\n".join(out)


def other_lines(others):
    """The other screens of the home, each with its grid and pages, for a question about several or all of them."""
    if not others:
        return ""
    out = ["Other screens of this home:"]
    for other in others:
        grid = other["grid"]
        out.append(f'screen "{other["name"]}" ({grid.columns} x {grid.rows} cells, '
                   f'{"sections" if other["sections"] else "no sections"}):')
        out += ["  " + line for line in page_lines(other["document"]).splitlines()]
    return "\n".join(out) + "\n"


def instructions(prompt, document, grid, entities, sections=True, domains=None, name="", others=()):
    return RULES.format(columns=grid.columns, rows=grid.rows, pages=grid.page_cap, tiles=grid.tile_cap,
                        sections_rule=SECTIONS_RULE if sections else NO_SECTIONS_RULE,
                        icons=", ".join(tile_icons.ICONS), pages_text=page_lines(document), name=name,
                        others_text=other_lines(others), entities_text=entity_lines(entities, domains),
                        prompt=prompt.strip())


def for_screens(plan, others):
    """The plan split by screen: (this screen's plan, {other screen's id: its plan}). An item without `screen` (or with
    this screen's name) is this screen's; "all" goes to every screen; a name no screen has stays with this one."""
    names = {other["name"].strip().lower(): other["id"] for other in others}
    here, there = {"reply": plan.get("reply"), "pages": [], "remove": plan.get("remove") or []}, {}
    for item in plan.get("pages") or []:
        if not isinstance(item, dict):
            continue
        target = (item.get("screen") or "").strip().lower() if isinstance(item.get("screen"), str) else ""
        ids = list(names.values()) if target in ("all", "*", "every screen") else [names[target]] if target in names else []
        if not ids or target in ("all", "*", "every screen"):
            here["pages"].append(item)
        for screen in ids:
            there.setdefault(screen, {"pages": []})["pages"].append(item)
    return here, there


async def ask(request, prompt, document, grid, entities, sections=True, agent=None, domains=None, name="", others=()):
    """Ask Home Assistant's AI Task for a plan. `request` is the add-on's HA websocket request (HomeAssistant.request).

    Returns (plan, seconds). `agent`: an ai_task entity; None takes the one the person set as default in Home
    Assistant (Settings > System > General > AI suggestions), and Home Assistant refuses when there is none."""
    data = {"task_name": "ESP Screens layoutbot", "structure": STRUCTURE,
            "instructions": instructions(prompt, document, grid, entities, sections, domains, name, others)}
    if agent:
        data["entity_id"] = agent
    started = time.monotonic()
    result = await request("call_service", domain="ai_task", service="generate_data", service_data=data,
                           return_response=True, wait=WAIT_SECONDS)
    seconds = time.monotonic() - started
    response = (result or {}).get("response") if isinstance(result, dict) else None
    plan = (response or {}).get("data")
    if isinstance(plan, str):  # a provider that gave text after all
        plan = json.loads(plan)
    if not isinstance(plan, dict):
        raise LayoutError("Layoutbot got no plan.")
    return plan, seconds


# ----- the plan becomes a document -----

def _icon(value):
    """An icon the screen has, or None: a model may run on past the name (`curtains},{`) or add `mdi:`."""
    if not isinstance(value, str):
        return None
    value = value.split("}")[0].split(",")[0].strip().removeprefix("mdi:")
    return value if value in tile_icons.ICONS else None


def _text(value, most):
    return value.strip()[:most] if isinstance(value, str) else ""


def _cells(page, grid):
    """The cells of a page that no tile and no section takes."""
    taken = set()
    for tile, row, column in placed_tiles(page):
        p = tile["placement"]
        taken |= {(r, c) for r in range(row, row + p["rows"]) for c in range(column, column + p["columns"])}
    for section in sections_of(page):
        p = section["placement"]
        taken |= {(r, c) for r in range(p["row"], p["row"] + p["rows"]) for c in range(p["column"], p["column"] + p["columns"])}
    return [(r, c) for r in range(grid.rows) for c in range(grid.columns) if (r, c) not in taken]


def _corner(free, grid, columns, rows):
    """The first top left corner, in reading order, where a block of columns x rows has only free cells."""
    free = set(free)
    for r in range(grid.rows - rows + 1):
        for c in range(grid.columns - columns + 1):
            if all((r + dr, c + dc) in free for dr in range(rows) for dc in range(columns)):
                return r, c
    return None


def _tile(entity):
    return {"id": new_id(), "content": {"kind": "entity", "entityId": entity},
            "placement": {"row": 0, "column": 0, "columns": 1, "rows": 1}, "appearance": {"label": ""}, "interaction": {}}


def _new_page(document, title, icon=None):
    """A new page with the Home page's top bar (Page menu, "New empty page with this top bar") and its own title."""
    home = next(p for p in document["pages"] if p["id"] == document["homePageId"])
    bar = deepcopy(home["topbar"])
    for item in bar["leading"] + bar["trailing"]:
        item["id"] = new_id()
    bar["title"] = {"source": "text", "text": title} if title else {"source": "screen"}
    page = {"id": new_id(), "navigation": {"excludeFromPagination": False}, "topbar": bar, "tiles": []}
    if icon:
        page["icon"] = icon
    return page


class _Plan:
    """One plan applied to a copy of a document; `notes` says what was left out and why, each as a key of
    addon.layoutbot.notes with its values, so the editor says it in its own language."""

    def __init__(self, document, grid, entities, sections, offers=None):
        self.doc, self.grid, self.sections, self.offers = deepcopy(document), grid, sections, offers
        self.known = {e["id"] for e in entities}
        self.notes = []
        self.placed = set()  # entities this plan has put somewhere: one tile each

    def note(self, key, **values):
        if {"key": key, **values} not in self.notes:
            self.notes.append({"key": key, **values})

    def entities(self, values):
        out = []
        for entity in values or []:
            if not isinstance(entity, str):
                continue
            if entity not in self.known:
                self.note("unknown", entity=entity)
            elif entity not in self.placed:
                self.placed.add(entity)
                out.append(entity)
        return out

    def continuation(self, page):
        if len(self.doc["pages"]) >= self.grid.page_cap:
            self.note("pages_full", pages=self.grid.page_cap)
            return None
        title = page["topbar"]["title"].get("text") or ""
        following = _new_page(self.doc, f"{title} 2"[:96] if title else "", page.get("icon"))
        self.doc["pages"].insert(self.doc["pages"].index(page) + 1, following)
        self.note("continued", page=title)
        return following

    def section(self, page, title, icon, entities, grow=True):
        """A new section: as wide as its tiles (at most the grid), at the first free block; what does not fit on the
        page continues as a section of the same title on a page after it (as adaptGrid does)."""
        while entities and page is not None:
            free = _cells(page, self.grid)
            # The widest block that holds all of them here; else the widest part that fits; else a page after it.
            shapes = [(w, min(math.ceil(len(entities) / w), self.grid.rows))
                      for w in range(min(self.grid.columns, len(entities)), 0, -1)]
            whole = [(w, r) for w, r in shapes if w * r >= len(entities) and _corner(free, self.grid, w, r)]
            width, rows = whole[0] if whole else shapes[0]
            corner = _corner(free, self.grid, width, rows)
            while rows and corner is None:
                rows -= 1  # the part that fits here; the rest goes on
                corner = _corner(free, self.grid, width, rows) if rows else None
            if corner is None:
                if not grow:
                    self.note("page_full", page=self.doc["pages"].index(page) + 1, count=len(entities))
                    return page
                page = self.continuation(page)
                continue
            part, entities = entities[:width * rows], entities[width * rows:]
            tiles = [_tile(entity) for entity in part]
            for i, tile in enumerate(tiles):
                tile["placement"].update(row=i // width, column=i % width)
            block = {"id": new_id(), "title": title, "placement":
                     {"row": corner[0], "column": corner[1], "columns": width, "rows": math.ceil(len(part) / width)},
                     "tiles": tiles}
            if icon:
                block["icon"] = icon
            page.setdefault("sections", []).append(block)
        return page

    def into_section(self, section, entities):
        """More tiles in an existing section's free cells (growing it is the editor's own drop rule)."""
        p = section["placement"]
        taken = {(t["placement"]["row"], t["placement"]["column"]) for t in section["tiles"]}
        free = [(r, c) for r in range(p["rows"]) for c in range(p["columns"]) if (r, c) not in taken]
        for entity, (r, c) in zip(entities, free):
            tile = _tile(entity)
            tile["placement"].update(row=r, column=c)
            section["tiles"].append(tile)
        if len(entities) > len(free):
            self.note("section_full", section=section["title"], count=len(entities) - len(free))

    def loose(self, page, entities, grow=True):
        """Tiles in a page's free cells in reading order; what does not fit goes on a page after it (`grow`), or, on a
        page the person already has, is left out with a note, so no page of theirs moves to another number."""
        while entities and page is not None:
            free = _cells(page, self.grid)
            if not free:
                if not grow:
                    self.note("page_full", page=self.doc["pages"].index(page) + 1, count=len(entities))
                    return
                page = self.continuation(page)
                continue
            for entity, (r, c) in zip(list(entities), free):
                tile = _tile(entity)
                tile["placement"].update(row=r, column=c)
                page["tiles"].append(tile)
                entities.pop(0)

    def page(self, item):
        number = _text(str(item.get("page") or ""), 4)
        title, icon = _text(item.get("title"), 96), _icon(item.get("icon"))
        if title.strip("() ").lower() in ("screen title", "no title of its own"):
            title = ""  # the words the question uses for a page without a title, read back as one
        if number.isdigit() and int(number) > len(self.doc["pages"]):
            number = ""  # a model that numbers the page it makes: the next number is a new page
        if number.isdigit():
            if not 1 <= int(number) <= len(self.doc["pages"]):
                self.note("no_page", page=number)
                return
            page = self.doc["pages"][int(number) - 1]
            # A title for a page the person has only when renaming is all the item does: models put a title on every
            # page they add to ("the alarm on page 1" renamed every page 1 "Security").
            adds = item.get("tiles") or any(isinstance(x, dict) and x.get("entities") for x in item.get("sections") or [])
            if title and not adds:
                page["topbar"]["title"] = {"source": "text", "text": title}
            # An entity this plan puts in a section of a page it already stands on moves into it; one it names as a
            # loose tile there stays where it stands (models restate a page's tiles). A page never shows it twice.
            moved = {e for section in item.get("sections") or [] if isinstance(section, dict)
                     for e in section.get("entities") or []}
            self.take_off(page, moved)
            self.placed |= {t["content"].get("entityId") for t in all_tiles(page)} - moved
        else:
            if not item.get("tiles") and not any(isinstance(x, dict) and x.get("entities") for x in item.get("sections") or []):
                return  # a new page with nothing on it is never what was asked
            if len(self.doc["pages"]) >= self.grid.page_cap:
                self.note("pages_full", pages=self.grid.page_cap)
                return
            page = _new_page(self.doc, title, icon)
            self.doc["pages"].append(page)
            new = page
        if not number.isdigit():
            blocks = [(_text(x.get("title"), 48) or "Section", _icon(x.get("icon")), self.entities(x.get("entities")))
                      for x in item.get("sections") or [] if isinstance(x, dict)]
            if not self.sections:
                blocks = [(None, None, [e for block in blocks for e in block[2]])]
            blocks.append((None, None, self.entities(item.get("tiles"))))
            self.compose(new, [block for block in blocks if block[2]])
            if not any(all_tiles(p) for p in self.doc["pages"] if p is new):  # everything it named stands elsewhere
                self.doc["pages"].remove(new)
            return
        for section in item.get("sections") or []:
            if not isinstance(section, dict):
                continue
            name, entities = _text(section.get("title"), 48), self.entities(section.get("entities"))
            if not self.sections:
                self.loose(page, entities, grow=False)
                continue
            existing = next((s for s in sections_of(page) if s["title"].lower() == name.lower()), None)
            if existing:
                self.into_section(existing, entities)
            else:
                self.section(page, name or "Section", _icon(section.get("icon")), entities, grow=False)
        self.loose(page, self.entities(item.get("tiles")), grow=False)

    # ----- a new page, dressed: as many controls as fit, as large as the page allows -----

    def ladder(self, entity):
        """The faces a tile of this entity can take, plainest first: one cell, then wide with a control of one row, then
        2 x 2 with the richest control (one of two rows) or the larger picture. Only what the entity offers (`offers`,
        Home Assistant's actions through the catalogue) and the grid takes."""
        domain = entity.split(".", 1)[0]
        offered = (self.offers or {}).get(entity)
        steps = [("single", None)]
        keys = [key for key in catalogue.control_keys(domain) if key in (offered or ())] if domain not in PICTURES else []
        if not keys:
            # Without a control a larger card is a larger picture, state or name: wide, then 2 x 2, where there is room.
            if self.grid.columns >= 2:
                steps.append(("wide", None))
                if self.grid.rows >= 2:
                    steps.append(("square", None))
            return steps
        two = [key for key in keys if (catalogue.option(domain, "controls", key) or {}).get("rows") == 2]
        one = [key for key in PREFERRED.get(domain, ()) if key in keys] or [key for key in keys if key not in two]
        if self.grid.columns >= 2 and one:
            steps.append(("wide", one[0]))
        if self.grid.columns >= 2 and self.grid.rows >= 2 and two:
            steps.append(("square", two[-1]))
        return steps

    def dressed(self, entity, rung):
        size, control = self.ladder(entity)[rung]
        tile = _tile(entity)
        columns, rows = self.grid.dimensions(size)
        tile["placement"].update(columns=columns, rows=rows)
        if size != "single":
            tile["appearance"]["presentation"] = size
        if control:
            tile["interaction"]["controls"] = control
        return tile

    def pack(self, blocks, rungs):
        """Blocks on a page, each at the first place in reading order where it fits (side by side when they are
        narrow), its tiles in reading order at the first place they fit inside it, at most as wide as the grid:
        [(title, icon, tiles placed in the block, columns, rows, top, left)], or None when they do not fit on one page."""
        out, page = [], set()
        for title, icon, entities in blocks:
            taken, tiles = set(), []
            for entity in entities:
                tile = self.dressed(entity, rungs[entity])
                w, h = tile["placement"]["columns"], tile["placement"]["rows"]
                spot = next(((r, c) for r in range(self.grid.rows) for c in range(self.grid.columns - w + 1)
                             if all((r + dr, c + dc) not in taken for dr in range(h) for dc in range(w))), None)
                if spot is None:
                    return None
                taken |= {(spot[0] + dr, spot[1] + dc) for dr in range(h) for dc in range(w)}
                tile["placement"].update(row=spot[0], column=spot[1])
                tiles.append(tile)
            rows = 1 + max(r for r, _ in taken)
            columns = 1 + max(c for _, c in taken)
            corner = _corner([(r, c) for r in range(self.grid.rows) for c in range(self.grid.columns) if (r, c) not in page],
                             self.grid, columns, rows)
            if corner is None:
                return None
            page |= {(corner[0] + r, corner[1] + c) for r in range(rows) for c in range(columns)}
            out.append((title, icon, tiles, columns, rows, *corner))
        return out

    def compose(self, page, blocks):
        """Put blocks on a new page: start every tile plain, then give one tile after the other its next face, the
        richest kinds first, while the page still holds everything. Blocks that do not fit even plain go on a page
        after it."""
        while blocks:
            rungs = {entity: 0 for _, _, entities in blocks for entity in entities}
            fitting = len(blocks)
            while fitting and self.pack(blocks[:fitting], rungs) is None:
                fitting -= 1
            if not fitting:  # one block alone is taller than a page: it is cut, as adaptGrid cuts a section
                title, icon, entities = blocks[0]
                if title is None:
                    self.loose(page, list(entities))
                else:
                    self.section(page, title, icon, list(entities))
                blocks = blocks[1:]
                if blocks:
                    page = self.continuation(page)
                    if page is None:
                        return
                continue
            here = blocks[:fitting]
            order = sorted({e for _, _, entities in here for e in entities},
                           key=lambda e: (RANK.get(e.split(".", 1)[0], 9), [x for _, _, es in here for x in es].index(e)))
            # Alike tiles of a block grow together first (every light of a room as large as the others), then single
            # tiles where room is left; one rung for every group or tile before any gets two.
            groups = {}
            for index, (_, _, entities) in enumerate(here):
                for entity in entities:
                    groups.setdefault((index, entity.split(".", 1)[0]), []).append(entity)
            alike = sorted(groups.values(), key=lambda group: order.index(group[0]))
            for steps in (alike, [[entity] for entity in order]):
                grown = True
                while grown:
                    grown = False
                    for group in steps:
                        if all(rungs[e] == rungs[group[0]] and rungs[e] + 1 < len(self.ladder(e)) for e in group):
                            for e in group:
                                rungs[e] += 1
                            if self.pack(here, rungs) is None:
                                for e in group:
                                    rungs[e] -= 1
                            else:
                                grown = True
            for title, icon, tiles, columns, rows, top, left in self.pack(here, rungs):
                if title is None:
                    for tile in tiles:
                        tile["placement"]["row"] += top
                        tile["placement"]["column"] += left
                    page["tiles"] += tiles
                    continue
                block = {"id": new_id(), "title": title, "placement": {"row": top, "column": left, "columns": columns, "rows": rows},
                         "tiles": tiles}
                if icon:
                    block["icon"] = icon
                page.setdefault("sections", []).append(block)
            blocks = blocks[fitting:]
            if blocks:
                page = self.continuation(page)
                if page is None:
                    return

    def remove(self, values):
        gone = {value for value in values or [] if isinstance(value, str)}
        for page in self.doc["pages"]:
            self.take_off(page, gone)

    @staticmethod
    def take_off(page, gone):
        if gone:
            page["tiles"] = [t for t in page["tiles"] if t["content"].get("entityId") not in gone]
        for section in sections_of(page):
            section["tiles"] = [t for t in section["tiles"] if t["content"].get("entityId") not in gone]
        # A section left without tiles goes, as "Remove section" leaves nothing behind.
        if "sections" in page:
            page["sections"] = [s for s in page["sections"] if s["tiles"]]
            if not page["sections"]:
                del page["sections"]


def summary(before, after):
    """What a change does to a screen, in numbers the editor puts in words: pages added, tiles added and taken off, and
    the numbers of the existing pages it changed."""
    ids = lambda document: {t["id"] for page in document["pages"] for t in all_tiles(page)}
    old_pages = {page["id"]: page for page in before["pages"]}
    return {"pages": sum(1 for page in after["pages"] if page["id"] not in old_pages),
            "added": len(ids(after) - ids(before)), "removed": len(ids(before) - ids(after)),
            "changed": [n for n, page in enumerate(after["pages"], 1) if page["id"] in old_pages and page != old_pages[page["id"]]]}


def plan_entities(plan):
    """Every entity id a plan names for a tile, once each, for the caller to ask what each offers."""
    found = []
    for item in plan.get("pages") or []:
        if isinstance(item, dict):
            for section in item.get("sections") or []:
                found += (section.get("entities") or []) if isinstance(section, dict) else []
            found += item.get("tiles") or []
    return list(dict.fromkeys(e for e in found if isinstance(e, str)))


def apply_plan(document, plan, grid, entities, sections=True, offers=None):
    """The plan on a copy of the document: (validated document, notes: [{key, values...}]). `offers`: the controls
    each entity offers ({entity: [keys]}, catalogue.offers through Home Assistant), which a new page dresses its tiles
    with; without it every tile is one cell. Raises LayoutError when the result is not a
    valid document (the editor then shows the reason and keeps the page as it was)."""
    work = _Plan(document, grid, entities, sections, offers)
    work.remove(plan.get("remove"))
    for item in plan.get("pages") or []:
        if isinstance(item, dict):
            work.page(item)
    total = sum(len(all_tiles(p)) for p in work.doc["pages"])
    if total > grid.tile_cap:
        raise LayoutError(f"The screen takes {grid.tile_cap} tiles; this would make {total}.")
    return validate_document(work.doc, grid), work.notes
