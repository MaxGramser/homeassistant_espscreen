# A camera tile's last picture stays on the next page

## The symptom
On a Guition 10.1 inch (JC8012P4A1 V3, firmware 0.61.0 from dev 016e0825) a swipe from a page with a live camera tile
to the next page left part of the camera's picture standing on the new page (2026-11-15, 10:38): the part of the tile's
spot where the new page drew nothing of its own (no card, no section). The rest of the spot showed the new page.

## What was measured
The screen's log over the API: the stream started at 10:38:38 ("stream 0 into 746x421 at 520,50 (a tile)", first
picture after 783 ms) and ended at 10:38:41 with the tap that changed the page. The picture left behind lay inside that
spot. Repeated by `show_page` 2 then 1, 3 or 4 after 0.7 to 3 s, ten times, filmed with the Mac camera: no picture left
behind, but by then every one of those pages covered the camera's whole spot with cards or a section.

## What changed
A full view's stream already drew the whole glass again once its task had ended (`glass::redraw_all`), because its
last picture could land after the redraw at closing. A tile's stream did not. Since this commit `live_view::tick` asks
`glass::redraw(room)` for a tile's stream once its task has ended, so LVGL draws the tile's spot again whatever came
before.

## The deciding experiment
A page with nothing in the camera tile's spot (an empty cell or a short page) after the camera's page: swipe there 1
to 3 s after the stream started, twenty times, with and without the redraw, filmed. If the picture never stays with the
redraw and does without it, this is solved; if it stays with it, a copy reaches the glass after the task has ended, and
the PPA's or the cache's write order is next (`picture_engine_p4.cpp`, `glass_core.cpp` `written`).

## Pointers
`components/smart_display/live_view.cpp` (`close`, `tick`), `glass_core.cpp` (`disarm`, `redraw`), docs/PICTURE_ARCHITECTURE.md.
