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

### Solved
2026-11-16. Measured by the sizes on the chip (riscv32 build of the records): a section keeps 60 bytes in its page's
list and 20 in the list of what is drawn, both now reserved exactly (`page_receiver.cpp`, `sections::make`), and its title
and summary, a heap block each once longer than 15 bytes, at most 216 bytes inside the chip. Its four LVGL objects are
about 1 KB in PSRAM, where LVGL allocates on the boards that draw sections, and stay out of the budget. A section costs
224 bytes (`catalogue/_tile.yaml` `section`, `tile_memory::page_cost`, `core.page_cost`, `pageCost` in
`web/src/model/memory.ts`), counted where the screen's hello says it draws sections; `tests/fixtures/memory-conformance.json`
holds the three to the same answers and `module_sections.h` stops a 32-bit build whose sizes outgrow the price
(docs/TILE_MEMORY.md, "The memory budget"). The heap tour on a 10.1 inch was not run: what a section keeps is fixed by
its records, not by its contents, so the sizes say it.

## The header's height was worked out three times

Solved 2026-11-15. The firmware works a section's header out from its fonts, `tools/generate_board_shapes.py` works the
same out for `boards.json`, and the editor draws from that; they had been matched by hand once. `tests/test_editor_parity.py`
(`Sections`) now lays a card out in a section in the firmware preview on every board shape that draws sections and holds
the editor's numbers to the same pixels, and the editor's guess for a board without the numbers is gone. Writing that
check showed that the preview drew no sections at all (its build named three modules by hand): the modules the preview
is built with are now a column of `components/smart_display/modules.py`. One difference is left and named in the test:
the JC4880P443 shares the preview's 217 dpi look with the Waveshare 4.3 inch, whose rows stand a pixel further apart.

## Not tested at the receiver

The screen's own reading of a page's `sections` and of a `sums` update (`page_receiver.cpp`, about lines 310 and 345)
and the change of a screen's hello in the middle of a delivery (`page_delivery.py`, the `sections` feature turning on)
are only exercised whole, by `tools/render/sections.py`. A malformed `sections` array, a section past the grid and a
`sums` update for a page without sections have no test of their own.

Solved 2026-11-16. `tools/render/sections.py` has a receiver round: on the real firmware on the host, sent as the add-on's
Sender sends them, a page with two sections is drawn with two; a `sums` update is taken, and one with a count that is not
the page's, one for a page without sections, one for a page that is not there and one that is not a list are refused and
change nothing; a page whose sections are not a list, have a section of five fields, a place that is text or past any
grid, a section past the grid, two sections over each other, a section without a title or seventeen sections is refused
with "Error: sections" (a list that was not one, or too long, said "invalid message" before) and the layout comes back
whole with its next delivery; a layout from an app that knows no sections (its hello says none) leaves page 0 without
decorations, and sections come back after it. The round failed when the receiver's check of the blocks was taken out.
The hello that changes in the middle of a delivery has its own test, `tests/test_sections.py` (`HelloInTheRound`): a
screen last heard without sections that now draws them gets its pages with them in the same round, and one flashed back
gets them without and no summaries, each under the revision of what it got; both fail without that switch in
`page_delivery.py`.

## Smaller things the plan named

- A section's title changed through the `appearance` packet, without the loading screen a new layout brings.
- The grid's columns and rows chosen beside the pages instead of in the screen's settings.
- A section inside a section, and a section across two pages: neither is built, and the document has no room for
  either; both would need a new storage version.
