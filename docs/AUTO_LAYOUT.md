# A first layout made for you

The editor can make a whole layout for a screen from the home's own Home Assistant: its areas, its devices and what each
entity can do. It is offered at once on a screen that has no tiles yet ("Shall I make a first layout for you?"), and the
toolbar's **Auto layout** makes one for any screen. The dialog draws every proposed page small, as the screen will show
it, before anything changes. On a screen that has tiles it asks whether the new pages replace its pages or come after
them (then only with what is not on the screen yet, in the pages and tiles it has left). The layout goes into the draft
as one edit: Undo takes it back, and nothing reaches the screen until Save.

The layout is worked out in the editor, by a pure model: `web/src/model/auto-layout.ts` (tests:
`web/tests/auto-layout.spec.ts`, with fake homes in `web/tests/auto-layout.fixture.ts`). The add-on gives it the facts
of Home Assistant's registries that the inventory leaves out (`api/home-facts`, `screen_manager/app/home_facts.py`,
`tests/test_home_facts.py`); what each candidate can do comes from `api/capabilities`, as for the tile inspector. The
glue to the stores is `web/src/editor/auto-layout.ts`, the dialog `web/src/components/AutoLayoutDialog.vue`.

## What it takes

It follows Home Assistant's own generated dashboards (the frontend's areas and home strategies,
`src/panels/lovelace/strategies/` in home-assistant/frontend):

- **Left out**: an entity with a category (config, diagnostic), a hidden one, a disabled one, an unavailable one, the
  screens' own entities and their video, a type the screen's firmware does not draw, and the kinds Home Assistant's
  dashboards leave out too (automations, scripts, buttons, input helpers, device trackers). A rain radar picture of a
  weather integration is not a camera of the house.
- **Kept**: lights, covers, climate, humidifiers, fans, players, locks, scenes and switches in their room; door, window
  and garage sensors and smoke or leak sensors; temperature, humidity, CO2 and fine dust as a room's summary; and the
  house's own things: the weather (one), the alarm, the people, the power meter (one, the house's own: no room, a
  meter's integration, what is taken rather than given back), the cameras, the vacuum, to-do lists and calendars.
  Cameras and to-do lists only on a board that draws them.

## Rooms and groups

- A **room** is a Home Assistant area, in Home Assistant's order, by floor. An entity takes its device's area. An entity
  without an area takes the area most members of its group are in (a light group or a scene of one room), else the area
  its own name or its device's name holds as a word ("LG Oled Living room"), for kinds that stand on their own in a room
  (a lamp, a player, a camera), never a device's own switches.
- Within a room the groups stand in the order of Home Assistant's area view: lights, covers, climate, media, security,
  scenes, other devices. A room's light group comes first, then a speaker before a television.
- The **screen's own area** comes first and is Home. Then the house: weather, security (the alarm), who is home, energy,
  cameras, the vacuum, lists, the calendar (one card, the other calendars in it). In a home of rooms, what has no room
  joins the house by kind (lights, climate, media, covers, locks, scenes); a device's own switches and sensors without a
  room stay in the library.
- A **home without areas** is grouped by the word its names share at their start or end (two or more names, not most of
  them), then by device, then by kind.

## Sizes and pages

How a screen is filled follows its grid, from `boards.json` and its hello:

- **Four by four cells and more** (the 7 and 10 inch boards): sections of two cards or more, one per room, several rooms on a page before the
  next page begins; a room that fills most of a page gets pages of its own, a section per group, and a group of one small
  tile joins another. Larger cards where they pay off: a room's light group 2 × 2 with brightness and presets, the first
  thermostat 2 × 2 with setpoint and modes, the first player 2 × 2 with its album cover and the others wide with their
  keys, the weather 2 × 2 with its forecast, the vacuum 3 × 2 with its map and rooms, a list 2 × 3, the calendar
  2 × 2, a camera 2 × 2 (live as many as the screen streams at once), the alarm 2 × 2, the meter wide with its graph. A room's other sensors start as the meter that suits them where the screen draws one (docs/METER.md, "The first look").
- **Three by three**: sections too, with wide or tall cards instead of squares.
- **Smaller grids** (the CYD, the 4 inch boards) and every board without the `sections` module: plain tiles, one room or
  the house to a page, continued on the next page where it runs over, the weather wide with its forecast. Rooms that each
  fill little share a page only when the screen has fewer pages than rooms, and a room that would run one or two tiles
  onto a page of its own leaves its least wanted ones to the library then.

A section groups: it always holds two cards or more. A room, a group or a house's group of one card is that card alone,
a loose tile on the page at the place its section would have had, without a title (the weather, the alarm without
cameras, a room's only thermostat). The alarm and the cameras share one Security section. This is the first layout's own
rule; a section of one card made by hand is the person's to keep.

## Placing

The groups go on the pages through `placeUnits` in `web/src/model/placement.ts` (tests: `web/tests/placement.spec.ts`),
the one path that puts groups of tiles on pages, which Layoutbot uses too. It knows no rooms and no home: units of tiles
come in, each with a title, an icon, its tiles' sizes and how much each matters, the page it heads for and which units
may share a page; pages come out with every tile at its own cell and a section block around each group of two tiles or
more, held to the screen's grid, pages, tiles and memory (`proposalHolds`). What found no room comes back as data, each
tile with its unit and why (the tile ceiling, the cells, the memory, the pages), so each caller says it in its own words.

A unit's place on a page is the first free one in reading order for any width its tiles fit, the least empty cells
there; a page takes later units of its share that fit before the next page begins, and units that fill (the house's own
groups) take what is left of another share's page. A unit taller than a page is cut into parts with the same title. A
section then grows a row to meet the one beside it, and into a gap of one column or row. Without sections each share's
tiles run on pages of their own (Auto layout gives each room, and the house, its own share there), and neighbouring
pages are put together only when the screen has fewer pages.

A unit marked `loose` never gets a section. With `grow` (Layoutbot asks for it, the first layout does not), a new page's
tiles then step up through the larger cards they were given while the page still holds everything: alike tiles together
first (every light of a room as large as the others), then single tiles where room is left, the more wanted first;
never a size made up to fill a hole. `placeUnits` makes new pages only: a page the person already has changes through
the editor's own edits (a free cell, a new section, a drop into a section), as Layoutbot does it.

What a caller gives each tile comes from `auto-layout.ts`: `facesFor` says the cards an entity can take on the screen,
plainest first (one cell, then wide or tall, then the large card), and the one the first layout gives it; `placeTileFor`
makes that a tile at its plainest card with the others to grow into. So Layoutbot dresses the entities it was given
exactly as the first layout dresses its own. `placeTarget` says what a screen holds for a proposal.

Auto layout's own part is which units there are: a room or a group is a unit, the house's groups share pages and wait for
the rooms' holes, a room of its own shares its pages with nothing else, and a page of several rooms is named after them.

What a card shows comes from the catalogue, never from this model: a control set or display is chosen only where the
entity's capabilities offer it, the catalogue says it fits the card's size and the screen draws it (its firmware, its
features such as `light_presets`, `vacuum_tile` and `live_camera`, its `tile_sizes` and whether it draws pictures).

## Limits

The layout stays within the screen's pages and tiles, and keeps about one tile in seven of the screen's ceiling free for
what the person adds. On a screen that reports its memory for tiles (docs/TILE_MEMORY.md) it holds to the rule every add
holds to, `memoryLine` in `web/src/model/memory.ts`: the whole draft after the proposal, its new pages' top bars included,
against the whole draft before it, crossing no line the editor would ask about (nine tenths of the room, or all of it), and ending no higher than it started
(`proposalHolds`): a draft past nine tenths gets pages that keep it within its room, one past its room nothing that costs
memory.
Pages that go after the screen's own are priced beside them. A screen still measuring its room has no say yet. When room
runs short, the least wanted go first, in this order: binary sensors, sensors and scenes, the calendar,
people and switches, covers, locks, cameras and lists, lights and players, and the alarm and climate last; the dialog
says how many found no room. Every layout passes the editor's `validatePages` and the add-on's `validate_document`
(`tests/test_auto_layout.py` checks the documents of `tests/fixtures/auto-layout-documents.json`, which the editor's test
writes).

## Labels and titles

A tile's label is short and without its room: "Living room Ceiling" in the living room is "Ceiling". Where an entity is
the one of its device in its group and its name is the device's with a word added, it takes the device's name ("Spot 1
Light" is "Spot 1"); a name that would say only a number keeps its room ("Bathroom 1"); a player named after its room
takes its maker's name; a room's light group is "All lights"; people go by their first name where no one else has it.
A section takes its room's name and its area's icon from the fixed set (`tile_icons.ICONS`), or its group's name and
icon; its summary is the temperature Home Assistant shows for the area, else the room's own temperature or humidity
sensor. A page of one room takes its name, one of several rooms their names or their floor's.

## Places a change touches

- `web/src/model/placement.ts` and `web/tests/placement.spec.ts` for how units go on pages (Layoutbot places by it too: ask
  whoever works on Layoutbot before changing what it takes or gives).
- `web/src/model/auto-layout.ts` and its test with the fake homes; run `npx vitest run tests/auto-layout.spec.ts -u`
  after a change that moves tiles, so the documents the add-on's test checks follow.
- `screen_manager/app/home_facts.py` and `tests/test_home_facts.py` for a new fact of the registries.
- `editor.auto.*` in every language of `screen_manager/translations/` (docs/TRANSLATING.md).
- This document.
