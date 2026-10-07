# How many tiles a screen holds

A screen holds as many tiles as two things allow: the ceiling its board states, and the memory its tiles take. The
ceiling is a fixed number per board. The memory is measured by the screen itself, and the editor shows it beside the
tile count, so a layout that would not fit is stopped before it is saved (firmware 0.34.0+).

## The ceilings per board

Every table in the firmware with one entry per tile or per page is sized from two build flags,
`SCREEN_MAX_TILES` and `SCREEN_MAX_PAGES` (`components/smart_display/page_protocol.h`). `packages/core.yaml` gives them
64 and 8, the numbers every screen had before; a board file states more when its board has the memory for them.

| Board class | Tiles | Pages | Why |
| --- | --- | --- | --- |
| ESP32 without PSRAM (CYD, CYD ILI9342, Hosyond 4-inch) | 64 | 8 | everything a tile holds stays inside the chip |
| ESP32-S3 with 8 MB PSRAM (Guition 4-inch, Waveshare, Sunton, JC3248W535) | 128 | 24 | the tile list, the cards and a tile's extras live in PSRAM |
| ESP32-P4 (Guition 7-inch and 10.1-inch) | 256 | 16 | PSRAM, and several times the memory inside the chip of an S3 |

A page's cells still count: a screen holds no more tiles than its pages have cells, so a two by two grid holds 96 tiles
over 24 pages. A board's numbers reach the add-on and the editor through `screen_manager/app/boards.json`
(`max_tiles`, `max_pages`), and New screen shows them; a screen also says its own in its hello reply (`max_tiles`,
`max_pages`), which is what a save is held to.

Pages beyond nine take two digits in a navigation tile (`screen.page_10` to `screen.page_32`). A pager shows dots up to
eight pages and "3 / 12" past that. Every page beside the one on the glass is kept whole, up to the ceiling and
as far as the PSRAM goes (docs/KEPT_PAGES.md).

## The top bar

Every page has its own top bar, and its items count like the tiles. A page's bar holds six items, or what the board file
states as `SCREEN_MAX_BAR_ITEMS` (firmware 0.34.0+): twelve on every board with PSRAM, six on the boards without. The
screen says its number in its hello (`max_bar_items`), the add-on and the editor hold every page to it, and the glass's
width still decides how many of them show: items that do not fit leave from the left, and the editor marks them.

A changed value in a top bar goes out as one message for every page that shows it, its targets numbered page × items +
index. Six is what every screen reads; an app that numbers by more says so in the message (`w`), and only to a screen
whose hello said it takes more, so an older screen or an older app still means the same slot.

An entity item shows its status, when it last changed, or its icon alone (`content: icon`), which takes the least width:
the icon follows the state and its colour as on a tile.

## The memory budget

What runs out first is not PSRAM but the memory inside the chip. A board with PSRAM keeps megabytes free there in every
test; the memory inside the chip holds the Wi-Fi link, the API, LVGL's draw buffer and, per tile, the text of its state
and what only some tiles carry (a forecast, a player's sources, a thermostat's modes). On a board without PSRAM the
whole tile lives there.

What a tile costs comes from the tile catalogue, the one place every type is described (docs/CATALOGUE.md):

- Every `catalogue/<type>.yaml` states `memory: {bytes, extras}`: what one tile of the type keeps in the memory inside
  the chip, measured on a board with PSRAM, and whether it keeps a block of extras. `tools/generate_catalogue.py` refuses
  a type without it. A screen card that keeps more than its type has a price of its own in `catalogue/screen.yaml`
  (`cards`), counted by its entity first: the energy card (docs/ENERGY.md).
- `catalogue/_tile.yaml` states what a tile's own choices add: `action` for a tap that runs an action of its own, `line`
  for a second line set to one of its values. Each also keeps a block of extras on a tile whose type keeps none. It also
  states what a page keeps (`page`, its title) and an item of its top bar that shows an entity (`bar_text`, its text).
- On a board with PSRAM a tile costs its type's bytes plus what its choices add. On a board without PSRAM it also pays
  the tile itself and, where it keeps one, its block of extras, which live inside the chip there. Their sizes are the
  firmware's (`sizeof(Tile)`, `sizeof(Extra)`), so the screen says them.

The firmware, the add-on and the editor price a tile with this one rule (`tile_memory::cost`, `core.tile_cost`,
`web/src/model/memory.ts`), and `tests/fixtures/memory-conformance.json` holds the cases all three must answer alike.

The screen sends, in the reply to a hello and a ping (`memory`):

- **room**: what is free inside the chip now, plus what the tiles on the screen already take, less a reserve. On a
  board without PSRAM the room the tile list holds for more tiles counts too. The reported room is the smallest of the
  last five samples, one a minute, so it stays steady. A sample is taken only once a layout has been on the screen for a
  minute (`SETTLE_MS`, firmware 0.51.0): the first minute after a start or a new layout sits some 25 KB below where the
  screen settles, while Home Assistant sends every state and the cards are built, and on a board with little to spare
  that minute fell below the reserve and read as no room at all. Until the first sample the reply leaves `room` out,
  and the add-on and the editor show that the screen is still measuring.
- **used**: what the tiles on the screen take by the catalogue's prices.
- **psram**, **tile**, **extra**, **page**: whether the board has PSRAM, and the size of a tile, of its block of extras
  and of a page's record (which holds its top bar). A board without PSRAM keeps all three inside the chip.

The add-on and the editor count a layout as the screen does, the keys of a bedside clock included. The editor shows the
share of the room in a thin bar beside the tile count, amber from 80 % and red when it is full. Past ten times the room,
or with no room at all, it says "No room" in words instead of a share, and the pop-up says the same. The budget is a
warning, not a rule (app 0.4.61): a tile that takes the layout past nine tenths of the room, or past all of it, asks
first in a pop-up, and whoever answers yes gets it, from a click or a drag in the library alike. The add-on saves
whatever the editor sends, an automation's tile event included. A screen measured far less room than the bench screens
the prices come from (GitHub #157), and a screen protects itself when it runs short (below), so trying is safe. A screen
that says nothing about its memory (older firmware) is not asked: it keeps its old tile limit. While a screen is still
measuring, the bar says so and nothing asks.

The reserve (`RESERVE`, 40 KB) covers what the screen needs beyond its tiles at its busiest: a layout switch dips about
20 KB below where it settles, a picture that loads takes 20 to 25 KB for a moment, and the Wi-Fi link and the API need
room to breathe. Below it, a screen stopped answering on the bench before it restarted.

How close the estimate comes, measured on the bench with layouts filled to the budget: on a board with PSRAM the prices
count about a tenth more than the tiles take (128 tiles of a heavy mix: 48 KB counted, 43 KB taken); on the CYD they
count about 80 bytes a tile less (3 KB on a full budget), which the reserve covers. Once a layout is on the screen, its
room is measured again, so the editor's bar follows what the screen really has. Every bench screen held a full budget
for a quarter of an hour without a restart.

## When memory runs short anyway

A layout past the room is saved and sent when someone chose to (above). Should the screen not have the room after all,
it stops taking it as soon as the memory inside the chip falls below `LOW_WATER` halfway
through: it lets go of the tiles it took, answers "insufficient layout memory" and stays reachable. Before, it ran on
without a working Wi-Fi link until someone reset it.

A layout that fits can still meet a moment without room: a picture loads while a big state arrives. Below `LOW_WATER`
(16 KB free inside the chip), a state still sets a tile's state and attributes, but no tile gets a new block of extras,
the tiles off the glass give up theirs (their next state brings them back), and a block that cannot be had is no block
rather than a restart (`Tile::set_extra`, `extra_block`, `shed_extras`). The tile then shows what a tile without extras
shows. The screen says so for ten minutes (`short`), and the editor puts a small amber dot
beside its memory bar.

The extras of a tile live in PSRAM on a board that has it (ESPHome's `RAMAllocator`, PSRAM first), as the tile list
does. That alone took about a kilobyte per tile of weather, media or climate out of the memory inside the chip.

Should LVGL itself be refused memory while it draws, nothing can carry on: its check stops the loop, and ESPHome's task
watchdog restarts the screen within seconds and keeps a crash report.

## Pricing a type

A type's `bytes` is what one tile of it keeps with rich content, as real devices have it: a player with a long title and
sixteen sources, a select with many long options, a forecast of five days and eight hours. Home Assistant's demo
entities are thin and price a type up to ten times too low.

**Estimate it.** `python tools/estimate_tile_memory.py <type>` builds the tile's state message with the add-on's own code
from an example state (`tools/tile_memory_examples.json`, or `--state` with an entity of your own) and prices what the
screen keeps of it. It reads what to price from the firmware's own source: the attributes and extras
`page_receiver.cpp` takes, the longest text it keeps of each, and the lists it keeps as one text. Its constants (a heap
block's overhead, the size of a list's slots, a std::vector doubling its room as it grows) come from the bench, and it
comes within about 15 bytes of the measured prices on average. `tests/test_tile_memory.py` holds every catalogue price
within 15 % (or 48 bytes) of its estimate, so a firmware that starts keeping more cannot leave a price behind.

**Measure it**, when a bench is at hand: the slope of the free memory inside the chip over layouts of 1 and 41 tiles of
the type, on a board with PSRAM, twice:

1. Build a screen's firmware with the heap figures every 10 seconds (`debug: update_interval: 10s` in its own YAML) and
   flash it.
2. Save a layout of one tile of the type, wait until the screen has applied it, wait 10 seconds and take the median of the
   **Heap Free** sensor over 25 seconds.
3. Do the same with 41 tiles, then 1 and 41 again. The mean of the two differences, divided by 40, is the price; the two
   agree within a few bytes. A step during which the screen restarted is done again.

The catalogue takes the higher of the two, rounded up to 16 bytes and at least 32. `extras` says whether a tile of the
type keeps a block of extras on a board without PSRAM: there the tile costs its bytes, the tile itself and, where `extras`
is true, the block. The tile list keeps the room of its largest layout, so a slope measured on such a board leaves the
tile itself out.

On the classic ESP32 the **Heap Free** sensor also counts IRAM that only takes 32-bit words, about 54 KB on a CYD, which
no text or list can use. The `health` lines in the screen's log say `free_8bit`, the memory that counts, and `room`, the
room the editor is told.

## Compatibility

- A screen with older firmware says nothing of its ceilings or memory: the add-on and the editor keep to 64 tiles over
  eight pages (fewer on firmware before 0.18.0), as before.
- An older add-on with newer firmware never sends more than 64 tiles over eight pages, which the newer firmware takes.
- A stored layout is checked against the most any board may state (32 pages, 1024 tiles) when the add-on starts, so a
  layout made for a big screen never keeps the others from loading. A save is checked against what its screen takes.
- The Home Assistant sensor of a screen's layout (`sensor.esp_screens_<node>`) carries `max_tiles` beside
  `max_pages`. A layout of many tiles leaves out each tile's defaults (single, no controls, the standard display, the
  automatic tap) to stay under the 16 KB Home Assistant's recorder keeps.

## Places a change of this kind touches

- A type's price: `catalogue/<type>.yaml` (`memory`), what a tile's choices add: `catalogue/_tile.yaml`. Then
  `tools/generate_catalogue.py` (it writes the prices into `tile_catalogue.h` and both `catalogue.json` files) and
  `python tests/memory_conformance.py` (it rewrites `tests/fixtures/memory-conformance.json`).
- The rule: `components/smart_display/tile_memory.h` (`cost`, the reserve, the low water), `screen_manager/app/core.py`
  (`tile_cost`), `web/src/model/memory.ts` (`tileCost`); the fixture holds all three to the same answers.
- The screen: `components/smart_display/page_protocol.h` (the ceilings), `runtime_tiles.h` (`layout_cost`,
  `memory_room`, `spare_tiles`), `runtime_model.h` (the extras in PSRAM, `heap_room`), `page_receiver.cpp` (the lean
  state), `packages/core.yaml` (build flags, the hello reply, the health line), the board files (`SCREEN_MAX_*`).
- The add-on: `page_delivery.py` (`memory_of`, the Sender's ceilings), `core.py` (`Grid`, `STORE_MAX_*`), `server.py`
  (`ceilings`, `memory`), `page_capabilities.py` (kept for offline editing).
- The editor: `web/src/components/MemoryMeter.vue`, `web/src/store.ts` (`memory`, `confirmMemory`), `web/src/drag.ts`,
  `web/src/model/memory.ts` (`memoryCrossing`), `Library.vue`.
- `tools/generate_board_shapes.py` (`max_tiles`, `max_pages` in `boards.json`), and the tests:
  `tests/test_tile_memory.cpp`, `tests/test_tile_memory.py`, `tests/test_screen_ceilings.cpp`,
  `tests/test_screen_ceilings.py`, `web/tests/memory.spec.ts`.
