# Kept pages, prepared pages, kept pictures and page pictures

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
| `components/smart_display/page_pictures.h`, `page_pictures_lvgl.h` | A page's picture from the glass, put back on it at a turn ("Page pictures" below) |

## Kept cards

`widgets` is always the set of cards on the glass. A page that leaves the glass takes its set onto the shelf, hidden,
and a page that comes back brings its own set with it (`keep_page`). The board's own cards (`make_cells`, at boot)
are the first set; `make_card` builds more of the same card, with the styles `packages/core.yaml` hands over at boot
(`runtime_tiles::card_look`) and the sizes of the first card, so a new set never lays out the grid to measure itself.
Both go through `build_card`, so there is one card to change.

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

A page's sections (docs/PAGES.md "Sections") are drawn once, when the page is first placed on the glass or prepared off
it, and kept: their panels, titles and icons are hidden while another page is on the glass and shown with their page, so
a page switch stays a switch. They are made again when what they show changes, and a new layout or grid lets them go
(`module_sections.h`).

A layout change forgets every kept page (`forget_kept`); the sets stay and are reused for the next pages, and their
pictures go with what they showed, and so do the cards' own drawings (their custom parts, their points, a calendar's
events, a meter's texts: `end_extra`). A card that next shows a tile without custom parts would only hide them
(`hide_extra`, made for paging a slot back and forth), so before, every layout left kept cards holding a hidden one: on a
4-inch Guition two pages added and taken away took the memory inside the chip from 49 to 20 KB, until the screen refused
layouts. A card's points (`new_points`, a kilobyte each) take PSRAM first. Measure it on the bench with a page added and
taken away a few times: the free memory inside the chip comes back to where it was. How many pages a board keeps is `kept_capacity()`: every page but the one on the
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

- **Every layout** is prepared on screen: "Preparing pages 3/8" over everything, with a
  line of fun about what the next page holds (`screen.preparing` in the translations; every line only looks, none
  sounds like the screen does something to a device). One page per step of an LVGL timer, 70 to 250 ms each on an S3.
  After the last one the screen stays up to 3 s (`SETTLE_MAX_MS`) while the data Tessera sends after a layout (a
  graph's history, a player's details) lands on the cards it belongs to. A save in the editor goes the same way as
  the first layout since the start: from the moment the new layout begins to arrive ("Loading tiles") until its pages
  are prepared, the loading screen covers the glass, and it goes in one step, so nothing half drawn ever shows.
  A board that keeps no pages (the CYD) takes the cover away as soon as the layout is complete and its page is drawn.
  A change of names or colours alone (`appearance`) is no new layout and shows at once, without the loading screen.
- **A page still unbuilt after that** is built in the background, one page every 300 ms while
  nobody touches the screen (`PREPARE_QUIET_MS`).
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

## Page pictures

Kept cards save building a page; they do not save drawing it. On a 10.1-inch glass LVGL draws a million pixels in
software for every page turn, and that is where the time goes: 248 ms from the swipe to the page on the glass,
of which the cards take 40 to 70 ms. So a screen with a steady glass (below) also keeps a picture of the pages it has
shown, in PSRAM: the pixels of the page's own room as LVGL last drew them, copied from the frame buffer while the page
stood still. When the screen turns to such a page, the picture goes on the glass at once, past LVGL, in 47 ms.
LVGL then draws the page as it always did, underneath, and that changes no pixel.

| File | What it holds |
| --- | --- |
| `components/smart_display/page_pictures.h` | The rules: which blocks of a picture are true, what a page that comes back lacks, which pages hold a picture, how many a board keeps (pure, `tests/test_page_pictures.cpp`) |
| `components/smart_display/page_pictures_lvgl.h` | Taking a picture from the glass, putting one on it, and what tells it LVGL drew (a part of `runtime_tiles.h`) |
| `components/smart_display/glass.h` | The copies between the frame buffer and a picture (`taken`, `laid`, `shown`), what LVGL has waiting (`waiting`), and `steady` |

### True per block, never as a whole

A picture is never shown because it is recent. It is shown where it is true: where it holds exactly what LVGL would
draw there now. The glass is cut into blocks of 64 pixels, and each block of a picture is true or not
(`page_pictures::Map`). A turn puts the true blocks and leaves every other block as it is on the glass, for LVGL to
draw a moment later, as before. So a page whose thermometer moved while it was away comes back at once with every card
but that one, and no value the screen no longer holds is ever shown.

What makes a block untrue:

- **On the glass, anything LVGL draws.** At every refresh the areas LVGL is about to draw make the blocks under them
  untrue for the page on the glass (`glass::waiting`, read at `LV_EVENT_RENDER_START`). That sees what no change number
  sees: a title that scrolls, a spinner, a pressed key, a plugin's own timer. A card that never stands still is simply
  never in its page's picture.
- **Away, a change number.** A page off the glass changes only through `kept_pages::Changes`, the rule the kept cards
  are drawn again by. When the page comes back, the blocks of a card whose tile took a number since it left are
  untrue, and every block when everything was asked for (the look, Home Assistant gone or back, a setting). Whatever
  changes a card off the glass without drawing it takes a number for this (a cover fetched ahead), or says so
  (`page_pictures_untrue`: a section's summary).
- **Another layout, grid, turn or room.** A layout or a grid forgets every picture; a picture of another rotation, or
  of a room that changed with the page bar, has no true block.
- **A plugin's tile, always.** A plugin draws by rules of its own; its blocks are left to LVGL.

A picture holds the page's own room only: the rectangle of the tile grid. The top bar and the page bar are objects
every page shares, they change while a page is away with nothing to tell its picture (the clock, a title, the back
key), so they are never taken and never put.

The turn's own redraw is the one drawing that leaves the put blocks true: LVGL draws the very pixels they hold. A card
whose tile takes a number between the put and that redraw is drawn with its change, and its blocks are untrue.

### Taking and putting

- **Taken** while the page rests: a second after the last touch and the last turn, with nothing over the page's room
  (found as the live tiles find it, by walking what LVGL would draw there, so an overlay needs no line of its own),
  LVGL not paused and the governor at rest. Only the blocks that are untrue are copied, and only once LVGL has not
  drawn them for a second and a half (`page_pictures::Stillness`): what draws every second, a playing track's bar or a
  title that scrolls, would be untrue again before anyone turned back, so it is never copied. What LVGL has waiting to
  draw is left for the next step. At
  most 400 KB in a step of the main loop (about 10 ms on a P4), so a page whose clock card ticked costs a few blocks
  and a whole glass is taken in five steps. Where a stream writes the glass the blocks wait until it is gone.
  Never in a turn.
- **Put** in `show_page`, before a card is exchanged or placed, under the glass lock, never while a stream writes the
  glass, never with something over the room, never with LVGL paused. The cards' places are the ones the page left the
  glass with.
- **Where it was not put**, the glass keeps what the page before showed until LVGL draws there, as the whole glass did
  before. Chosen over a blank ground and over putting nothing: nothing is made up, and the rest of the page is there.

### How many, and where

Two bytes a pixel of the panel, PSRAM only: 2 MB a page on a glass of 1280 x 800. Page pictures may take a quarter of
the board's PSRAM (`page_pictures::share`, 8 MB of 32: four pages), each picture's memory is taken when its page first
rests on the glass, and only while the picture store's whole budget and the kept pages' reserve stay free after it
(`page_pictures::reserve`). A board that cannot keep two keeps none. They are also the first thing a screen gives
up (`page_pictures::must_yield`): when an allocation from PSRAM is refused anywhere (the heap watch counts every one,
`heap_watch::psram_refused`: a cover, a camera's full view, a stream, a call, a plugin's picture) or less is free than
the kept pages' reserve, the picture of the page farthest from the glass gives its memory back, one a step, and none
takes memory again for 30 seconds. The governor's first step already stops any take. The page on the glass takes the place of the
page farthest from it, counted around the end when the pages loop, so the neighbours of the page in sight stay.
Inside the chip the whole of it is one pointer, one LVGL timer and one event hook.

A screen has page pictures when `hw::caps().page_pictures` says so: a screen with motion (docs/MOTION.md) whose glass
is steady (`glass::steady`), which today is a MIPI-DSI panel, every ESP32-P4 board. Its DMA repeats the frame by
itself, and 2 MB copied under the glass lock cost no dry frame (below). The ESP32-S3 boards with an RGB panel are left
out on purpose: their panel is fed from an interrupt and must never be held up, their screens are small enough for LVGL
to draw in time, and their PSRAM is the pictures'. They, and every other board, carry none of this code and turn
their pages as before.

### Measured

A Waveshare ESP32-P4 10.1 inch (1280 x 800, chip revision 3.2, ESPHome 2026.9.0, LVGL 9.5, a draw buffer of half the
glass in PSRAM), three pages of 16, 8 and 12 cards with sections, three media cards with a playing track and a title
that scrolls, and a live camera tile, 2026-11-16, with the profiler:

| | Without page pictures | With |
| --- | --- | --- |
| Swipe to the page on the glass, 24 turns | 248 ms (161 to 264) | 47 ms (23 to 51) for the picture |
| Swipe until LVGL is done | 248 ms | 296 ms (205 to 330): the put comes on top |
| Pixels LVGL's redraw changed in what was put | | 0, in every one of more than 90 compared turns |
| Dry frames of the panel (`Panel misses`) | 0 | 0 |

- A whole room (240 blocks, 1,772 KB) is put in 46 to 50 ms and half of one in 23 ms: about 38 MB a second, the memory
  is the limit. It is taken in five steps of 9 to 11 ms of the main loop, spread over a quarter of a second.
- On the page with the playing tracks 123 to 232 of 240 blocks were put, on the page with the live camera 192 to 195:
  what moves is left out, the rest comes at once. Filmed at 30 frames a second, the blocks that were not put show the
  old page for about 165 ms more, until LVGL draws them, which is what the whole glass did before.
- A light switched while its page was away: 228 of 240 blocks put, its card drawn by LVGL. The look changed while a
  page was away: nothing of it put, and its picture taken again once it rested. A card opened over a page, standby and
  waking: no block put that LVGL had not drawn. Turns every 200 and 400 ms and there and back within 250 ms: a picture
  at every turn, 0 pixels differing.
- The second-level cache's autoload over the source and the target of the copy (the chip's ROM calls) took a copy of
  2 MB from 50 to 39 ms. It is not used: the calls are marked as not for applications, they change a setting both
  cores share, and 11 ms is not worth finding out over months what that costs.
- Three pictures took 6.0 MB of PSRAM (20.3 MB free with the layout, 14.2 MB with them).

### The proof on a board

A build with `-DSWIPE_PROFILE=1` compares the glass with the picture after every turn's redraw, block by block, and
says how many pixels differ (`page_pic`, "compared with the glass after LVGL drew it: 0 px differ"). The `swipe_prof`
line has `picture` (ms from the swipe to the picture on the glass) and `put` (true blocks of the room's). The message
`{"v":2,"op":"page_pictures","n":0}` switches them off for an A/B on one firmware. What step two would take, LVGL
leaving the true blocks alone, is in docs/open-issues/page-pictures-step-two.md.

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
| `{"v":2,"op":"page_pictures","n":0}` | Page pictures off (`0`) or on (`1`), for an A/B on one firmware |

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
