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

### Made ahead

A picture from the glass needs its page to have been on the glass. So a page that lacks one is made ahead, off the
glass, the way the kept pages build the cards of pages nobody has opened: in idle moments, nearest to the glass first
(the page after, the page before, and outward; `Shelf::next_ahead`), one page a step. `warm_page` puts the page's
kept cards in the glass's place with LVGL's invalidation off and brings them up to date; LVGL then draws the screen
into a buffer in PSRAM instead of the panel (`lv_snapshot_take_to_draw_buf`, which every board with pictures has
compiled in), and the page's room goes into the picture turned as the panel is (`page_pictures::turned`, the inverse
of `glass::on_panel`). The buffer is 2 MB more, held while pages still lack a picture and given back after.

- **When.** Not before a layout has stood for 15 seconds (its values, covers and first pictures are still arriving)
  and its pages are prepared; never while the glass is dark, the screensaver shows or LVGL is paused; then three
  seconds after the last touch, pages settled, nothing over the page, no stream writing the glass, the governor at
  rest, at most one page a second. Each is logged with what it held the main loop for ("page 3 made ahead: ... ms of
  the loop"). The governor is told the hold was the screen's own choice (`Governor::own_work`): the held-up loop
  reported right after it is no sign of a busy screen. Before that was so, pages made ahead a second apart raised the
  governor's step by their own doing, and it held the rest of them back, and with them every take, for as long as
  someone kept turning pages (a Guition 10.1 after a second change of look, 2026-11-17). One page is one draw LVGL
  cannot be stopped in, about as long as a page turn's own; a touch that comes meanwhile waits for it. After a start that is once per page, after another look once
  more.
- **What is true in it.** Everything but the cards that may look otherwise on the glass, by one rule
  (`page_picture_ahead_true`): a plugin's tile; a card that shows time (a playing track, a clock, a timer:
  `shows_time`), since a bar drawn a while ago would be a stale value; a tile whose look depends on being seen
  (`Tile::seen_to_look_right`: a camera, an image, a player, anything with a picture, since pictures load and spinners
  turn only while their card is seen); and a card on which anything moves by itself. A page of five camera tiles made
  ahead and called whole differed from the glass in 40 pixels at its first turn (a Guition 10.1, 2026-11-16); that is
  what the third part of the rule is for. Its change number is the one of that moment, so a tile that changes before the page is ever seen
  makes its card untrue, by the same rule as any other.
- **Not remade for a part.** A picture with some blocks untrue stays as it is until its page is on the glass; only a
  page with no picture, or with nothing true after everything was asked to be drawn again, is made ahead.
- **What it costs.** On a Guition 10.1 with rev 3.2 silicon, seven pages, no plugins (2026-11-16): a page made ahead
  holds the main loop for 147 to 220 ms, 60 to 131 ms drawing it and 66 ms turning it into the panel's lie (109 ms
  while each pixel's place was worked out on its own; with the sums per row, `page_pictures::turned`, 3.2 to 4.1 times
  as fast on a PC and 40 % less on the board, where the memory is the rest). Six pages were made in six seconds. The
  loop task's stack was untouched (its low mark 10,108 B before and after every page; one draw of a page on the glass
  the off-glass way took it from 10,108 to 9,868 B), internal RAM within 100 B, and seven pictures hold 12.3 MB of
  PSRAM.
- **Proven so.** Then twice round the seven pages in order: 14 turns, 14 puts, 14 compares, every one 0 pixels
  differing, the first turn to a page of five camera tiles among them (55 of its 240 blocks were true: the ground
  around the tiles). No dry frame, no restart.
- **After another look.** Dark mode switched off and on again on that board, each followed by a walk twice round:
  six pages made ahead each time, 14 puts and 14 compares each time, all 0 pixels differing, the governor's "main loop
  held up" five times in each stretch (the page turns' own), seven pictures kept at the end, no dry frame, no restart
  (2026-11-17). The loop task's stack read 9,528 B at its lowest after the night's runs on that layout, 10,108 at
  their start: worth watching that it settles.
- **Not while a sound plays.** A loop held for a fifth of a second is the class that made a sound stutter, so nothing
  is made ahead while the speaker or the microphone is held (`audio_owner`).
- **Its proof.** The compare at the first turn to that page (below), and `{"v":2,"op":"page_pictures","prove":1}`,
  which makes the picture of the page on the glass the off-glass way and compares it with the glass at once.
- **Off until proven.** LVGL draws a whole page from inside a timer of the loop task, and the loop task's stack had no
  room to spare on a real layout (2026-11-16). Until boards have shown what that draw needs, pictures are made ahead
  only after `{"v":2,"op":"page_pictures","ahead":1}` with Debug mode on, until the next start; each page made logs
  the stack's low mark before and after. Without it a page gets its picture when it has rested on the glass once.

### How many, and where

Two bytes a pixel of the panel, PSRAM only: 2 MB a page on a glass of 1280 x 800. A layout has a picture for every
page, as it has the cards of every page, under one ceiling: page pictures never hold more than half of the PSRAM heap
(`page_pictures::share`), so the kept cards, LVGL's objects, the picture store and the streams always have the other
half. A P4 board's 32 MB chip gives a heap of about 29.3 MB: 14.6 MB, seven pages, so a layout of six has all of them
and a layout of sixteen keeps the seven nearest the glass; a heap of 16 MB holds three. Each picture's memory is taken
when it is first made, and only while the picture store's whole budget and the kept pages' reserve stay free after it
(`page_pictures::reserve`: 7.9 MB on that board). A board that cannot keep two keeps none. They are also the first thing a screen gives
up (`page_pictures::Yield`), one picture at a time, the page farthest from the glass first:

- **For a refusal.** When an allocation from PSRAM is refused anywhere (a cover, a camera's full view, a stream, a
  call, a plugin's picture: the heap watch counts every one and keeps its size, `heap_watch::psram_refused`), and the
  ask was for no more than what is free and what the pictures hold together, one picture goes. One refusal costs one
  picture; whoever asked asks again, and a second refusal costs the next. An ask that no picture could help costs
  none: 40 MB refused on a board with 20 MB free and 4 MB of pictures let both pictures go before this was the rule
  (a Guition 10.1, 2026-11-16).
- **Under the floor.** While less PSRAM is free than the kept pages' reserve (2 MB), one picture goes each second.
  With 17 MB held on that board, 1.0 MB was free, one picture went, 3.1 MB were free and the other two stayed.

After either, no picture takes memory again for 30 seconds. The governor's first step already stops any take.

**Why a picture for every page.** A picture taken from the glass needs its page to have been there, and the page
farthest from the glass lets go first. With a quarter of the heap, as it was at first, six pages had three pictures,
and walking the pages in order never turned to a kept page (the page ahead was on the glass five turns ago): 57 puts
in 142 random turns on a Guition 10.1 (2026-11-16). With a picture for every page, each page has rested on the glass
once and from then on every turn is a put, whichever way one walks; made ahead ("Made ahead" above), not even that
first rest is needed.

**A layout with more pages than pictures.** A page is made ahead only where that takes no nearer page's picture. With
sixteen pages and seven pictures the glass's page and the three on each side have one; walking on, the page that comes
into reach is made ahead and the one that falls out of reach lets go. The page on the glass takes the place of the
page farthest from it, counted around the end when the pages loop, so the neighbours of the page in sight stay.
Inside the chip the whole of it is one pointer, one LVGL timer and one event hook.

A screen has page pictures when `hw::caps().page_pictures` says so: a screen with motion (docs/MOTION.md) whose glass
is steady (`glass::steady`), which today is a MIPI-DSI panel, every ESP32-P4 board. Its DMA repeats the frame by
itself, and 2 MB copied under the glass lock cost no dry frame (below). The ESP32-S3 boards with an RGB panel are left
out on purpose: their panel is fed from an interrupt and must never be held up, their screens are small enough for LVGL
to draw in time, and their PSRAM is the pictures'. They, and every other board, carry none of this code and turn
their pages as before.

### On a loaded screen

A screen that runs a camera with video, a wake word and Bluetooth has less of everything, and page pictures are what
it has less of first. A Guition 10.1 with those three plugins had 11.7 to 16.3 MB of PSRAM free where it has 25 MB
without them (2026-11-16), so of seven pages it keeps the pictures of two to four, the nearest to the glass, and the
others turn as before. Two rules were wrong for such a screen and are right now:

- **The store's own use is in its budget.** A picture's memory is taken while the rest of the store's budget and the
  kept pages' reserve stay free after it (`page_pictures::reserve` with what the store holds), not the whole budget
  on top of what the store already holds; that kept all but one picture out. The buffer a page is drawn into off
  the glass is held for moments and needs only the kept pages' reserve beside it (`affords_scratch`).
- **A take is not held back by the turn that came before it.** On that screen every page turn holds the main loop up
  long enough for the governor's first step ("the main loop held up"), which rests ten seconds, so no page was ever
  taken. A take is five steps of about 10 ms and holds the loop up for nobody: it runs at rest, and at any step when
  the main loop held up is the sign (`page_pictures::take_may`), which a walk through the pages brings turn after
  turn. For a panel that ran dry or a wake word that fell behind it waits. A picture made ahead is a whole draw and
  waits for rest.

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
- On a Guition 10.1 with rev 3.2 silicon, a normal build, a layout of six pages with sections and a live camera tile,
  from one start: internal RAM 417,984 B free without page pictures (lowest 394,568) and 417,540 B (lowest 394,084)
  with three kept, 444 B less; PSRAM 24,988,528 B free without and 18,827,260 B with, and all of it back when they
  were switched off. Puts of 216 of 240 blocks in 40.7 ms and, on the live camera's page, 83 in 15.7 ms, each with 0
  pixels differing.
- The same board, ten minutes of turns to a random other page every 2 to 6 seconds while the house did what it does (a
  live camera tile, a player playing), three pictures for six pages as the share then was: 142 turns, 57 puts, every
  one of the 57 compares 0 pixels differing; a put took 44.4 ms (12.3 to 47.3); the panel never ran dry, no allocation
  was refused, the governor at rest at the end, no restart; internal RAM 415,056 B free, 386,248 B at its lowest.

### The proof on a board

With Debug mode on (and in a build with `-DSWIPE_PROFILE=1`) the screen compares the glass with the picture after every
turn's redraw, block by block, and says how many pixels differ (`page_pic`, "compared with the glass after LVGL drew
it: 0 px differ"); a line that is not 0 names the rectangle on the panel. That costs about 50 ms of the main loop after
a turn, which is why it is Debug mode's. The log's `page_pic` lines say each put ("page 2: 232 of 240 blocks put in
45.2 ms") and each take ("page 2 taken: ..."). A profiling build's `swipe_prof` line also has `picture` (ms from the
swipe to the picture on the glass) and `put` (true blocks of the room's).

Three messages through the `screen_message` action, on a screen with page pictures and only with Debug mode on, each
answered by one `report:` line (pictures kept, blocks true, internal RAM free and its lowest, PSRAM free, PSRAM asks
refused, read from the heaps' counters at once):

| Message | What it does |
| --- | --- |
| `{"v":2,"op":"page_pictures"}` | The report alone |
| `{"v":2,"op":"page_pictures","n":0}` | Page pictures off (`1`: on again), for an A/B on one firmware: a turn's time, the internal RAM |
| `{"v":2,"op":"page_pictures","ahead":1}` | Pictures made ahead on (`0`: off) until the next start |
| `{"v":2,"op":"page_pictures","prove":1}` | Draws the page on the glass off the glass and compares it with the glass: the proof of "Made ahead" |
| `{"v":2,"op":"page_pictures","mb":20,"s":60}` | Holds 20 MB of PSRAM for 60 s, to watch the pictures give memory up and come back; more than is free is refused, which is the other way a picture goes |

 What step two would take, LVGL
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
