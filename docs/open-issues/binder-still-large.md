# The binder is still 4,500 lines

## Where it stands
`components/smart_display/runtime_tiles.h` was one file of 14,333 lines. On 2026-11-16 its sections moved
into thirty-three `*_lvgl.h` parts beside it (docs/ARCHITECTURE.md, "The binder and its parts"), which left about 4,550 lines.
Only the sections whose every line is what their heading says were moved. A first cut by every heading put the
widgets of a tile, the settings and a page's history into a file named after card parts, and the main loop's tick into
one named after prepared pages, so those stayed.

## What is left in it
- Its head: the model's glue, the widgets of a tile, a card's look and ground, the settings the screen remembers.
- Card parts (`card_bind`, `card_shaped`), kept pages, the screen's requests to the app (a picture, the library, a
  history), the memory the tiles take, and pages prepared ahead: each a section under a heading, each with lines of
  something else in it that want sorting first.
- The stretch from a favourite's tile to the page that is applied, about 2,170 lines without a heading: `render_slot`
  and what it calls, the camera and media cards on a tile, the boot and update screens, the steps of a page being
  prepared, placing a page.
- The touch input at its end.

## Strays inside the parts
The first cut went by headings, and a heading did not always own every line under it. A second cut the same day gave
the large strays files of their own (a tile's widgets, its tap, its words, opening a card, the full view, the remote
card, an answer with a picture, the screensaver's state). What a read of every part still found, each too small or too
much in the middle of its file to move without changing the order of definitions:

- `tile_controls_lvgl.h`: the media player's tile over a whole page (about 120 lines in the middle), the spinner and
  the busy sheet (50), the cover tile's layout.
- `detail_lvgl.h`: a tile strip's slider (about 130 lines in the middle), `travel_look`, `key_press`.
- `camera_view_lvgl.h`: the alert card's layout (70) and the doorbell's and a call's bindings (50).
- `vacuum_card_lvgl.h`: `vacuum_chip_paint` and `vacuum_segments`, the vacuum's own wrappers of the segmented control.
- `weather_tile_lvgl.h`: a sensor's graph on a tile and the sun tile (56). `optimistic_lvgl.h`: `cover_go` and
  `cover_key` (34), which send a plain action. `picture_store_lvgl.h`: the map view's state (43).
  `picture_rounds_lvgl.h`: the screensaver's drift (33).
- A few lines each: `power_key_paint` in the select card, `security_card_shape` in the lock panel, the icon fonts in the
  media card, `detail_shown` in a tile's picture, `bind_pages` in the colour card.

### Solved: the helpers several cards share (2026-11-16)
`card_parts_lvgl.h`, included before the first card, holds what several cards share: `detail_text`, `detail_card` and
`line_of` (from the weather card), `detail_shape`, `face_covers`, `fit_value`, `button_words` and the segmented control
(from the vacuum card), and `card_status` with `climate_round_key` (from the cover card). It is a move of 149 lines in
seven blocks, with two forward declarations dropped, that changes the order of definitions. A script proved the move:
every line taken from the three parts is in the new part, in order, and every other line is as it was. No moved name
has a second definition that an earlier place could now pick. The builds of tools/profiles.py SAMPLE on ESPHome
2026.9.0 gave the same size to the byte for the Guition, the jc8012p4a1 and the Waveshare 7. The CYD came out 16 bytes
smaller: two functions each 4 bytes shorter, which is Xtensa's call and literal relaxation over a new layout. On the
packages' min_version (2026.6.2, an older compiler) the Guition grew by 1,472 bytes. Every symbol has the same count,
and their sizes changed by a few bytes each, also in code that calls no moved helper (the doorbell, the colour card,
`camera_open`). That is the older compiler's code depending on the order it reads, not a call resolved differently.
The preview's WASM kept its size to the byte, and the layout audit and all 32 preview tests passed before and after.

## What to do
- Read each of those, cut it where it is one thing, and prove the cut the way the first was proven: the parts read
  back in their places give the old file line for line (the comparison is in the message of the commit that made the
  split, and `tests/firmware_sources.py` reads the parts in place).
- `render_slot` is one function of several hundred lines that decides what a tile is and draws it. The rules in it
  that need no LVGL belong in plain headers with tests, as `tile_controls.h` and `tile_palette.h` hold some already.
  That is a change of code, not a move: card by card, each with the layout audit and the preview's tests before and
  after.
- `screen_manager/app/server.py` is 6,300 lines and `plugins.py` 2,300. The same waits there; `plugins.py` has a seam
  (what a tile gets: its parts, their room, the fetch's answer).

## Pointers
`tests/firmware_sources.py` (`runtime_source`), docs/TESTING.md ("A test reads behaviour, not lines").
