# Sections on a page: the build plan

A plan for titled groups of tiles on the larger screens, written 2026-11-15 after the design study on the local branch
`sections-study` (never pushed). Version 1 is built from it on dev (2026-11-15): what is built is described in
docs/PAGES.md "Sections" and the other documents named at the end, and this file keeps the reasoning and what is still
open. Changed after the plan (the maintainer, 2026-11-15): no band across the page; a section takes its header and
padding from its own cells, so tiles outside it keep their height (docs/PAGES.md "Sections", "Room"); and a per-section
contrast background, off by default. Built beyond this plan: a tile dropped onto a section goes in as an app goes into a folder, the section growing by
rows, or wider where the page has no rows left. Still open: the grid control beside the pages (it stays in the screen's
settings), a section's price in the memory budget, and a rename through the `appearance` packet without the loading
screen.

## What is decided

- **A section is a block on the page's grid**, like one big tile: a rectangle of cells with a title, an icon and a soft
  panel behind it, holding its own tiles placed inside it. A section never holds another section.
- **Loose tiles stay exactly as today**: on the page's own cells, with their row and column, gaps where they were left,
  and they never reflow. An updated layout has only loose tiles, so every screen shows what it showed, pixel for pixel.
- **The look (C3 of the study).** The panel is the `SECTION` role (light `#F4F4F4`, dark `#101010`), its corner the
  card's radius plus the padding, the padding the grid's gap on every side. The title stands in a band above the
  section's first row, in the tile name's font and ink, as far from the panel's top as from its side, measured to the
  capitals, with its icon from the small icon font before it, centred on the capitals. A short summary may stand at the
  band's right end, on the title's line, in the small grey font (Home Assistant's heading badge: one entity's state).
- **The editor draws a section as the screen does**: the same band, panel, padding, title, icon and summary, from the
  firmware's own numbers, so building a page in the editor is building it on the glass.
- **Making a section**: select tiles (⌘ or Ctrl-click, Shift-click, or a frame drawn over empty space), then
  "Make a section" beside the selection, which asks for the name at once in an inline field. The selection becomes a
  block where it stands; the other loose tiles stay loose around it.
- **A grid change or a turn** keeps `adaptGrid`, with a section taking part as one unit of several cells.
- **Only the full tier draws sections** (docs/MODULES.md): the 4 MB boards, the CYD first, get none of it, not in the
  firmware and not in the editor.
- **In the editor a click on a section's title edits it** (its name and icon, in place); on the glass a title takes no
  tap.
- **A page that a grid change filled with what no longer fitted stays** when the grid comes back, as today.

The measured price of a band: on the 10.1-inch at 6 x 5 a single tile goes from 198 x 136 pixels to about 190 x 118;
on the 4-inch at 2 x 3 from 126 to about 90 high. Grids of three rows or fewer get a warning, never a block.

## 1. The document

A page keeps `tiles` (its loose tiles, unchanged) and may get `sections`:

```json
{
  "id": "4f0c2a9e1b7d3c55",
  "title": "Lights",
  "icon": "lightbulb-group",
  "summary": "sensor.living_room_temperature",
  "placement": {"row": 0, "column": 0, "columns": 2, "rows": 3},
  "tiles": [{"id": "...", "placement": {"row": 0, "column": 0, "columns": 1, "rows": 1}, "...": "..."}]
}
```

- `title` 1 to 48 bytes in the text fonts' glyphs; `icon` optional, a name a page's own icon may take
  (`tile_icons.ICONS`); `summary` optional, an entity whose state the band shows.
- `placement` is the block on the page's grid; every tile of the section lies inside it, relative to its top-left
  corner. Sections and loose tiles never overlap; a full-page tile is never in a section.
- A page without sections has no `sections` key, so a document from before is unchanged and every compiled message and
  revision is byte for byte what it was.
- **Storage**: the store stays at version 2 while no screen has a section, so going back to an older app costs nothing
  for anyone who never made one. The first save with a section writes `screens.v2.backup.json` beside the store and the
  store as version 3; an older app refuses version 3 without rewriting it (docs/PAGES.md "Storage and recovery").
- **Compiling**: a section's tile gets its absolute cell (the block's corner plus its own place), so its `slot` is a
  slot like any other, and `compile_tiles` orders all tiles by their cells as now.
- **An automation's tile command** (`tile_from_fields`, a slot) lands as a loose tile, as now; a cell a section holds is
  taken.

Files: `page_layout.py` (schema, validation, compile, copy and delete of a page), `layout_store.py` (versions, the
backup), `core.py` (`SECTIONS_FEATURE`), `web/src/types.ts`, `web/src/model/pages.ts`, `tools/generate_page_rules.py`.
Tests: new cases in `tests/fixtures/page-conformance.json` (run by Python and the editor alike),
`tests/test_page_layout.py`, the store's tests, and `tests/test_compat_0431.py` unchanged.

## 2. A grid change and a turn

`adaptGrid` (`web/src/model/pages.ts`) stays the one rule; a section is one of the units it walks in reading order:

1. It keeps its place when its block is inside the new grid and free.
2. Else it goes whole to the first free place of its size on its page, then to a new page right after it (the
   page's top bar, as tiles do now).
3. Only a section wider than the new grid becomes narrower: as wide as the grid, its tiles laid out again in reading
   order (each at the first free place, shrunk where it is wider than the section), the block as tall as they need.
   A section taller than a page after that is cut at a row: the rest is a section of its own with the same title and
   icon, on the next page.

Loose tiles keep today's rule exactly. The add-on only ever grows a grid (`grown`), where every block keeps its place.
Tests: `web/tests/pages.spec.ts`, with sections that keep their place, move whole, go to a new page and get narrower.

## 3. Protocol

- A full-tier screen names `sections` in its hello's `features`; the add-on keeps it (`Sender.features`) and tells the
  editor (`screen.sections`).
- The tiles go as now, each at its absolute slot. A screen without the feature gets exactly these tiles and no more.
- The page's own message carries its sections, only to a screen with the feature and only for a page that has some:
  `"sections": [[column, row, columns, rows, "icon codepoint", "title", "summary"], ...]`, at most 16, each title at
  most 48 bytes, so a page message stays far under 4096 bytes.
- A summary that changes goes as `{"op": "sums", "p": page, "t": ["20.5 °C", ""]}`, one text per section of the page,
  whenever the entity changes (`page_service`, beside the top bar's values).
- The screen refuses a page whose sections leave the grid or overlap (`Error: sections`), as it refuses a grid.

## 4. Firmware

- `components/smart_display/section_layout.h` (pure, `tests/test_section_layout.cpp`): a page's sections as the
  receiver keeps them, their check, and the rows: a band of fixed height above a row where a section starts, a row of
  no height below a row where a section ends, `LV_GRID_FR(1)` for every tile row, so every tile row of a page keeps
  the same height; and the grid row of every tile row.
- `components/smart_display/module_sections.h` (`SD_MOD_SECTIONS`, full tier only): the panel behind the block, the
  title and icon placed by their ink, the summary at the band's right end, the margin of the grid's gap on the cards at
  a block's sides. The decorations of a page are made once and kept with it, hidden and shown with its cards, so a page
  switch stays a switch; a new layout or grid lets them all go.
- `page_protocol.h` (`Page::sections`), `page_receiver.cpp` (the key and `sums`), `runtime_tiles.h` (`place_page` sets
  the page's rows and places every card at its grid row), `theme.h` (`SECTION`), `modules.py`, `packages/core.yaml`
  (the hello's feature).
- No new font: the title is the tile name's font (`label_font`), the icon the small icon font, the summary
  `small_font`.
- Checks: host renders of a sectioned layout light and dark, and of layouts without sections unchanged.

## 5. Editor

- **Drawing**: `DevicePage.vue` sets its grid's rows by the same rule as the firmware (`sectionRows` in
  `web/src/model/sections.ts`, the band's height from `boards.json`'s `section` metrics, worked out from the fonts by
  `tools/generate_board_shapes.py`), draws each block's panel, title, icon and summary in the glass's pixels, and the
  cards at a block's sides keep the gap's margin. `cardHeight` learns the band, so a card's content is laid out at the
  height the glass gives it.
- **Make a section**: the floating action beside a selection of loose tiles, an inline name field focused at once,
  Enter applies, Escape cancels. A selection that is not a rectangle gets a rectangle at its first tile, as wide as the
  selection (at most the grid), as tall as its tiles need in reading order; loose tiles in the way move aside as a drag
  moves them now.
- **A section** is chosen by its band: its inspector holds the title, the icon, the summary's entity, Remove section
  (its tiles stay, loose, where they are) and Remove with its tiles. A click on the title opens the name and icon in
  place. Its band drags it as one block (loose tiles make room as for a tile); a handle at its right edge makes it wider
  or narrower, its tiles reflowing in reading order when it gets too narrow for them.
- **Tiles** drag within a section, into one, out of one onto the page, and from the library into one; a drop that does
  not fit is refused in red as now.
- **Hints, never blocks**: loose tiles beside a section get a hint to make them a row of their own above the
  sections; a page with sections on a grid of three rows or fewer gets a note with the card height it costs.
- The editor offers none of this on a screen whose board is not of the full tier.

## 6. Order of work, and the checks

1. Document and compile (add-on and editor types), with the conformance cases and the compatibility checks.
2. Firmware: rows, panels, titles, summaries; host renders.
3. Protocol: sections and summaries to screens that name the feature.
4. Editor: drawing, make a section, the section's inspector, dragging and the width handle, the grid change.
5. Hints, docs, CHANGELOG, the editor's build; merge to dev, push, the house (deploy-home), the boards it concerns
   flashed with the maintainer's yes, and the maintainer's look at the glass and the editor.

## Documents that change

docs/PAGES.md (a chapter "Sections", storage version 3), docs/RESPONSIVE.md (the band and rows of no height in the
grid), docs/KEPT_PAGES.md (decorations kept with a page), docs/THEME.md (`SECTION`), docs/MODULES.md (the module),
AGENTS.md's table, and `screen_manager/CHANGELOG.md` under Unreleased.
