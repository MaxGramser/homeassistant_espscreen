# Kept pages, prepared pages and kept pictures (firmware 0.3.2)

A screen with PSRAM keeps the cards of every page it has built, builds every page before the first one opens, and keeps
the pictures its cards draw until they change. A page switch then hides one set of cards and shows another: on the
4-inch Guition the first frame of the new page is on the glass 70 to 160 ms after the switch, where building the page
took 120 to 250 ms before, and 450 ms for a media card over the whole page while its cover loaded. A board without
PSRAM (the CYD) keeps nothing and builds every page when it is shown, exactly as before; both go through the same
`show_page`.

The code is in three places:

| File | What it holds |
| --- | --- |
| `components/smart_display/kept_pages.h` | Which kept set holds which page, and the change numbers (pure, `tests/test_kept_pages.cpp`) |
| `components/smart_display/picture_store.h` | The picture copies and their budget (pure, `tests/test_picture_store.cpp`) |
| `components/smart_display/runtime_tiles.h` | The cards, the exchange, preparing and the picture paths (search for `kept_pages` and `pictures`) |

## Kept cards

`widgets` is always the set of cards on the glass. A page that leaves the glass takes its set onto the shelf, hidden,
and a page that comes back brings its own set with it (`keep_page`). The board's own cards (`packages/cells/<n>.yaml`)
are the first set; `make_card` builds more of the same card, with the styles `packages/core.yaml` hands over at boot
(`runtime_tiles::card_look`) and the sizes of the first card, so a new set never lays out the grid to measure itself.
Keep the two in step: a change to the card in `tools/generate_cells.py` belongs in `make_card` too.

Three rules keep this safe:

- **A card keeps its index in every set.** Its callbacks name that index or `&widgets[index]`, and a callback only fires
  on the glass, where `widgets[index]` is that very card. A set is only ever exchanged whole.
- **A card is only drawn while it is on the glass** (or while `warm_page` has put it there for one pass, below).
- **What a kept page lacks follows from change numbers, not from flags.** Every change a card could show takes the next
  number when it is asked for (`kept_pages::Changes`): a tile's state, everything at once (Home Assistant going or
  coming back, the look, the page bar), or a minute on a card that shows the time (`shows_time`: clocks, timers, the
  sun, graphs, a playing track, "5 min ago"). Every kept set remembers the number it was drawn up to, and a card is
  drawn again when it comes back only when its tile took a later number. A drawing that was asked for before a page was
  built, and ran after, is then no change that page lacks; the flags this replaced got that wrong.

A layout change forgets every kept page (`forget_kept`); the sets stay and are reused for the next pages, and their
pictures go with what they showed. How many pages a board keeps is `kept_capacity()`: every page but the one on the
glass, up to the board's page ceiling (`kept_pages::MAX_KEPT`, GitHub #183: with only seven kept, paging through a long
layout was quick on one page and slow on the next), none without PSRAM, and no new set once the free PSRAM falls under
`KEEP_RESERVE` (2 MB, for pictures, a full camera and an alert's picture). The price is the first opening of a layout,
which prepares every page (below).
A set of six empty cards takes about 17 KB of PSRAM; eight pages of the stress layout below left 5.5 MB of 8 MB free.

## Prepared pages

`warm_page` builds a page off the glass in one pass: with LVGL's invalidation off
(`lv_display_enable_invalidation`), the page's set takes the glass's place, the grid lays it out, its cards are drawn
into their objects, and the glass's own set comes back before anything reaches the panel. The page must be on the glass
for that pass: LVGL's grid gives a hidden card no size (`lv_grid.c` skips `LV_OBJ_FLAG_HIDDEN`), and a card is laid out
from its size. Its cards ask for no pictures while it runs (`warming`).

- **The first layout since the start** is prepared on screen: "Preparing pages 3/8" over everything, with a
  line of fun about what the next page holds (`screen.preparing` in the translations; every line only looks, none
  sounds like the screen does something to a device). One page per step of an LVGL timer, 70 to 250 ms each on an S3.
  After the last one the screen stays up to 3 s (`SETTLE_MAX_MS`) while the data Tessera sends after a layout (a
  graph's history, a player's details) lands on the cards it belongs to.
- **A later layout** (a save in the editor) is prepared in the background, one page every 300 ms while nobody touches
  the screen (`PREPARE_QUIET_MS`).
- **From then on** a kept page that is behind is brought up to date while the screen is idle, at most one page a
  second (`FRESHEN_QUIET_MS`, `FRESHEN_GAP_MS`), so a lamp switched elsewhere is already right on its page before
  anyone turns to it.

## Kept pictures

Every picture a card draws on a board with PSRAM is the store's own copy, never the download's buffer
(`picture_fetch`) that the next download overwrites: each tile's own picture under its tile, entity, frame, colours and
mark (`tile_picture.h`), and a media card's cover under its player, track, size and colour. A cover is fetched once
per track; a camera page that comes back shows its last pictures at once and loads the next one of each camera when
its picture is as old as its tile's pace. A picture that is still on some card, on the glass or kept, is never freed;
the budget for the rest is a fifth of the PSRAM, at most 6 MB (about 1.2 MB on a board with 8 MB). Two more rules:

- **No download starts between two quick page turns** (`camera_view::SETTLE_MS`, 800 ms after the last turn), so a
  picture never lands in the middle of someone paging through.
- **Pictures that do not refresh are fetched ahead** while the screen is in use and the store is under three quarters
  of its budget, for the cards on kept pages (a cover, a favourite, a map), after everything on the glass and broken off
  for it (`card_picture_wants`, docs/CAMERA.md "One route for every picture"). A camera on a kept page loads when its
  page comes back, showing its last picture meanwhile.
- **Over the budget, a page out of sight makes way.** What the glass shows is never freed. When every picture is on
  some card and the store is over its budget, the picture used longest ago that only a kept page draws goes
  (`picture_away`, `picture_let_go`): its card lets go of it and asks for it again when its page comes back. Every page
  can be kept that way without its pictures filling the PSRAM.

## Never walk the PSRAM heap while the glass is lit

Finding the largest free block (`heap_caps_get_largest_free_block`, and `heap_caps_get_info` under it) walks every
block of that heap with its lock held and the interrupts of that core off. On the 4-inch Guition a walk of the PSRAM
took 1.7 ms with one page built and 2.3 ms with eight (3,300 and 4,600 blocks, measured 2026-09-26 with the
diagnostic `heap_walk` below), while an RGB panel refills its ten-line bounce buffer from an interrupt every 0.34 ms.
Every walk put a shifted frame on the glass: stripes and doubled text while a camera picture or a cover loaded, and
once every five minutes from the "Psram Largest Block" sensor. The picture log now reads free sizes only, and that
sensor measures only while the glass is dark. A walk of the internal heap took 0.12 ms and stays in ESPHome's
`debug` sensor. Espressif's FAQ on RGB "screen drift" says the same: the bounce buffer is refilled from an interrupt,
so anything that keeps interrupts off for long shifts the picture.

## Measuring

A build with `-DSWIPE_PROFILE=1` (docs/SWIPE_PROFILE.md) takes three diagnostic messages through the `screen_message`
action, outside the add-on's session so a bench script can send them:

| Message | What it does |
| --- | --- |
| `{"v":2,"op":"swipe_test","n":12,"ms":700}` | Page switches without a finger |
| `{"v":2,"op":"kept_pages","n":0}` | At most `n` pages kept (`-1`: as many as fit), for an A/B on one firmware |
| `{"v":2,"op":"heap_walk"}` | How long one walk of each heap takes, and how many blocks it has |

`swipe_test` does not count as using the screen, so "Back to page 1" takes a screen that nobody touched since its start
back home in the middle of a test. The screen's own `show_page` action does count: a tour through it measures the same
`swipe_prof` lines. The `kept` log lines say when a set is made, how long each prepared page took, and the PSRAM left;
the health line every five minutes adds `kept_pages`, the bytes of kept pictures and the free PSRAM.

On this computer, `KEPT_PAGES_HOST=1 python3 tools/render/run.py` builds the host programs with kept and prepared
pages (a host build keeps none otherwise). Its renders must match a run without it pixel for pixel
(`tools/compare_renders.py` over the two output folders): that proves a kept or prepared page shows what a page built
on the switch shows, on every board and both ways the glass hangs.

The numbers above come from a stress layout of eight pages on the Guition (clock, forecast, climate with modes, a
graph, lights, a media card over the whole page with its cover, tall media tiles, two live cameras, cover, vacuum and
the sun path) and seven on the 4.3-inch Waveshare.
