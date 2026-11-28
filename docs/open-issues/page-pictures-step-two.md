# Page pictures, step two: LVGL still draws the whole page after a picture was put

## The symptom

A page turn on a 10.1-inch ESP32-P4 screen shows the page in 47 ms where its picture is true (docs/KEPT_PAGES.md,
"Page pictures"), and then LVGL draws the whole page again underneath, which changes no pixel and takes as long as
before: 296 ms from the swipe until LVGL is done. Until then the main loop does nothing else. The touch panel is
read once per loop, so a second swipe within that time waits for it, and someone paging quickly through three pages
still feels LVGL's pace from the second turn on. Step two would let LVGL leave alone what the picture already put.

Since 2026-11-16 a page that was never on the glass can have its picture made ahead, off the glass (docs/KEPT_PAGES.md,
"Made ahead"): built and proven on a Guition 10.1 without plugins (six pages made in six seconds at 147 to 220 ms of
the loop each, then 14 turns in order with 14 puts and 0 pixels differing, the loop task's stack untouched), and
after two changes of look in a row (six pages made again each time, 14 puts of 14 turns, 0 pixels differing), and
switched off by default until the owner decides. Not yet seen: its start by itself after a boot or a new layout, a
screen with a camera plugin, the wake word and
Bluetooth making pictures ahead (its PSRAM leaves room for two pictures, so little is made there), and a sound
playing through an idle screen at the moment a page is made (the rule keeps the two apart; nobody has listened). A page whose cards changed while it was away still has
those cards drawn by LVGL at the turn.

## What is known (Waveshare ESP32-P4 10.1 inch, 1280 x 800, chip revision 3.2, ESPHome 2026.9.0, LVGL 9.5, 2026-11-16)

- Without page pictures a turn takes 248 ms (161 to 264) from the swipe to the page: 40 to 70 ms for the cards, 113
  to 186 ms of LVGL rendering about 900,000 pixels, 46 to 51 ms flushing them.
- With them the picture is on the glass 47 ms (23 to 51) after the swipe, and LVGL is done 296 ms (205 to 330) after
  it: the put's 46 to 50 ms come on top of what LVGL takes. The main loop's longest gap in a turn stays about 195 ms.
- In more than 90 turns compared (three pages, sections, playing tracks, a live camera tile, lights switched while away,
  both looks, standby, turns every 200 ms) LVGL's redraw changed 0 pixels of the blocks that were put.
- A page with a playing track or a live tile has 123 to 232 of its 240 blocks put; the others show the old page for
  about 165 ms more (filmed at 30 frames a second).

## Ruled out

- A draw buffer of an eighth of the glass in internal RAM (162 to 199 ms a turn against 250 to 295): 256 KB of internal
  RAM, rejected.
- `-O2` instead of `-Os`: 3 to 4 %.
- A quarter of the glass as the draw buffer: it lands in PSRAM and is as slow as a half.
- The second-level cache's autoload over the copy: 50 to 39 ms for 2 MB, through ROM calls marked as not for
  applications. Not used.

## Candidates

1. **Cut the true blocks out of what LVGL draws in the turn's redraw.** The glass already does this for a stream's
   room (`keep_out` in `glass_core.cpp`, at `LV_EVENT_RENDER_START`): LVGL's areas are cut against rectangles and what
   lies inside goes. The same cut against a picture's true blocks, for the one refresh that follows a put, leaves LVGL
   the top bar, the page bar and the blocks that were not put. The pieces must fit LVGL's list of 32 areas
   (`LV_INV_BUF_SIZE`), so runs of blocks have to be joined into few rectangles, or the list made longer.
2. **A picture made off the glass, for a changed card too.** Pages never shown get their picture this way now. The
   same draw could give a kept page that was brought up to date a whole picture again, at about a page turn's time of
   the main loop each; whether that is worth it for a sensor that changes every half minute is the question, and
   drawing one card's rectangle instead of the screen is the cheaper form.
3. **Both**: then a turn to any page whose cards are up to date is a copy and a top bar.

## The experiment that decides

Candidate 1 is right only if the redraw it skips would have changed nothing, every time. Debug mode measures exactly
that on any screen with page pictures: after every turn's redraw it compares the glass with the picture, block by block, and logs the pixels
that differ (`page_pic`, "compared with the glass after LVGL drew it"). Run it for days on screens in use, with every
card type, plugins, a screensaver and both looks, and collect the lines. If it reads 0 every time, the cut is safe and
the turn becomes the put plus what LVGL has left. A single line that is not 0 names the rectangle on the panel and so
the card that changed without a change number; that card is the thing to fix first, and it is a bug in step one too.

Step one's code cannot run on a PC as it is: a host render has no frame buffer a task may write. A host glass that
mirrors what LVGL flushes would let tools/render run the compare over every card type of every board shape, and is
the cheapest way to that long run.

For candidate 2, measure what LVGL takes to draw one page into PSRAM while idle (about what a turn's render takes,
180 to 250 ms of the main loop) against what the governor allows, and whether a sound that plays meanwhile stutters, as
it did when a freshen drew the whole glass (docs/KEPT_PAGES.md, "Prepared pages").

## Pointers

- `components/smart_display/page_pictures.h`: the rules, `page_pictures_lvgl.h`: `page_pictures_drawing` (where the
  turn's redraw is recognised), `page_picture_compare`.
- `components/smart_display/glass_core.cpp`: `keep_out`, `cut_out`.
- `components/smart_display/swipe_profile.h`: `picture`, `put`, `done`.
- docs/KEPT_PAGES.md, "Page pictures"; docs/SWIPE_PROFILE.md.

## Solved: page pictures are gone (2026-11-19)

Page pictures were taken out of the firmware (docs/KEPT_PAGES.md, "Nothing past LVGL at a turn"): reading the frame
buffer for a picture threw away what LVGL had just drawn (docs/open-issues/dark-mode-half-switched.md), and as this file
measured, LVGL drew the whole page after the put anyway. There is no step two to take. This file goes with the next
release.
