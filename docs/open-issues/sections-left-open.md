# Sections: what version 1 leaves open

Sections on a page (docs/PAGES.md "Sections") are built and on dev since 2026-11-15. This file holds what they still
leave open, so the build plan they came from no longer has to be kept among the documents.

## A section's price in the memory budget

### The symptom
None seen yet. A section's decorations (its panel, icon, title and summary: up to four LVGL objects each, sixteen
sections a page) are made when a page is first placed and kept for every page visited until another layout arrives
(`module_sections.h`, `drawn`, `made`). The memory budget that decides how many tiles a layout takes
(docs/TILE_MEMORY.md) does not count them.

### What we know
Only boards of the full tier draw sections, and those have PSRAM, so the cost has not shown. Nobody measured it.

### The deciding experiment
The free internal and PSRAM heap of a 10.1 inch after a tour of eight pages with sixteen sections each, against the
same tour without sections (the governor's own numbers, never a heap walk while the panel is lit). If the difference
is worth a tile, a section gets a price in `ui_scale.h`'s tile memory table and the editor's `model/memory.ts`.

### Pointers
`module_sections.h` (`make`, `drop`, `forget`), docs/TILE_MEMORY.md, `web/src/model/memory.ts`.

## The header's height is worked out three times

### The symptom
None seen. The height of a section's header is worked out by the firmware from its fonts
(`module_sections.h` `header`, `title_top`), again by `tools/generate_board_shapes.py` with Pillow for `boards.json`'s
`section`, and read from there by the editor (`web/src/model/sections.ts` `sectionMetrics`, with a fallback of its own
for a board without the numbers). They were matched by hand once, against the host render's log line
`[sections] band ...` on the 10.1 inch.

### The deciding experiment
A check that fails when they differ: the host render prints the header and the title's top for each look, and a test
compares them with `boards.json` for every board shape of the full tier, as `tests/test_editor_parity.py` does for the
other sizes. The editor's fallback then goes, since every board that draws sections has the numbers.

### Pointers
`module_sections.h:57-82`, `tools/generate_board_shapes.py` (`section`), `web/src/model/sections.ts`,
`tests/test_editor_parity.py`.

## Not tested at the receiver

The screen's own reading of a page's `sections` and of a `sums` update (`page_receiver.cpp`, about lines 310 and 345)
and the change of a screen's hello in the middle of a delivery (`page_delivery.py`, the `sections` feature turning on)
are only exercised whole, by `tools/render/sections.py`. A malformed `sections` array, a section past the grid and a
`sums` update for a page without sections have no test of their own.

## Smaller things the plan named

- A section's title changed through the `appearance` packet, without the loading screen a new layout brings.
- The grid's columns and rows chosen beside the pages instead of in the screen's settings.
- A section inside a section, and a section across two pages: neither is built, and the document has no room for
  either; both would need a new storage version.
