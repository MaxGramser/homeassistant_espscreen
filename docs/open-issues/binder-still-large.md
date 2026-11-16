# The binder is still 4,500 lines

## Where it stands
`components/smart_display/runtime_tiles.h` was one file of 14,333 lines. On 2026-11-16 its sections moved
into thirty-three `*_lvgl.h` parts (thirty-four with the page pictures) beside it (docs/ARCHITECTURE.md, "The binder and its parts"), which left about 4,550 lines.
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
- `vacuum_card_lvgl.h`: the segmented control every card uses (55), `fit_value`, `detail_shape`.
- `weather_tile_lvgl.h`: a sensor's graph on a tile and the sun tile (56). `optimistic_lvgl.h`: `cover_go` and
  `cover_key` (34), which send a plain action. `picture_store_lvgl.h`: the map view's state (43).
  `picture_rounds_lvgl.h`: the screensaver's drift (33).
- A few lines each: `card_status` and `climate_round_key` in the cover card, `detail_text` and `detail_card` in the
  weather card, `power_key_paint` in the select card, `security_card_shape` in the lock panel, the icon fonts in the
  media card, `detail_shown` in a tile's picture, `bind_pages` in the colour card.

Most of these are helpers several cards share. They want one part of their own (`card_parts_lvgl.h`: the status line,
the round key, the segmented control, the text and frame of a card) placed before the first card, which changes the
order and so is proven by the builds and the layout audit, not by the line-for-line comparison.

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
