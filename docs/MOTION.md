# Motion

`components/smart_display/screen_motion.h` is the one layer the UI asks for anything that moves, or that changes the whole
glass. A card, the Dock or a plugin says what happens, and the layer picks how this screen does it. Nothing outside it
writes a dim, a release or a change of the whole glass by hand.

## Why a layer

LVGL keeps no picture of what it drew. To put a dim over a page, or to take a screensaver off it, it draws every tile
again, strip by strip, and on a large glass that shows as a wipe from one edge to the other. A phone moves layers it
already has; a screen here has one frame buffer and a CPU. So each block below is a way to get the same result without
drawing the page again, or without the drawing being seen.

## The hard rule

A screen has motion only when `hw::caps().motion` is true (`hw.h`): a full-tier screen (8 MB of flash or more) whose
frame buffer a task may write (`glass::direct()`). That is every ESP32-P4 board and the ESP32-S3 boards with an RGB
panel and pictures. A lite screen, the CYD first, never has it, and neither does a board that draws over SPI.

The same calls work on every screen. Without motion they do what the code did before: LVGL shows and hides the
overlay, and a change is made at once. No caller asks which kind of screen it is on, and a new board takes its side of
the rule from its hardware, with no line in its board file.

## The blocks

| Call | What it does with motion | Without |
|---|---|---|
| `screen_motion::show(over, card)`, `screen_motion::hide(over, card)` | The card is drawn first and whole, then the page dims around it on the glass itself; the way back in the same order | LVGL shows or hides `over` |
| `screen_motion::dim(over, opa, keep, on)` | The dim alone, all of the glass but `keep`, for an overlay that moves its own part; the caller tells LVGL inside `screen_motion::quietly` | Returns false; the caller sets the style |
| `screen_motion::settle(obj, set, from, to, speed, full, shortest, longest)` | What a finger let go travels on at the finger's speed and comes to rest | The same: it is plain LVGL |

## What each block rests on

- **The dim** is `glass::veil`: every pixel in the frame buffer mixed with the scrim's colour, to the bit what LVGL
  draws for the same layer (`glass::veiled` copies `lv_color_16_16_mix`). On a reTerminal D1001 a veiled page compared
  with LVGL's own redraw of it differed in 0 of 1,024,000 pixels (2026-11-10). It takes 36 ms for 800 x 1280, more
  than the 17 ms of a frame, and the memory is the limit: a second core gave nothing. So it goes through the glass in
  four passes of every fourth row, and what shows on the way is a dim that deepens evenly. It never runs while a
  stream writes the glass or while LVGL is paused; then the overlay comes the plain way.
- **The card first.** A card drawn after its dim comes in pieces of it. `show` has LVGL draw the card at once, then
  dims around it; `hide` takes the card off first, then brightens the page.
  What the dim keeps off is the area LVGL draws for the card, which is the card's place through the display's own
  rounding (ESPHome's `draw_rounding`, two pixels by default): a card on an odd pixel has a rim of a pixel that LVGL
  drew, dim and all, and with the card's bare place kept the veil dimmed that rim twice, a dark line around the card.
  Read back from a Guition 10.1's frame buffer with `glass_part` (2026-11-22): one pixel wide on two sides of an
  alert, gone with the rounded room.
- **The release** is `sheet_motion.h`: a cubic that starts at the finger's speed and ends at rest, never past its
  place, in a time between a shortest and a longest that follows the way left.

## Who uses it

The Dock (`dim`, `settle`), and alerts and plugin popups (`show`, `hide`).

The screensaver does not: a finger on it takes it off at once, the light comes up without a fade and the page is drawn
in sight, on every board. Drawing the page behind a dark backlight first (a block `cut`, until 2026-11) hid the
drawing but kept the glass black for as long as it took, and waited for the finger to lift, which read as a tap that
was not heard. An answer the moment the finger lands is worth more here than a page that arrives whole.

## Adding a block or a user

A new overlay calls `show` and `hide` and is done. A new kind of motion gets a block here, with its plain way for a
screen without motion in the same function, and a line in the table above. If it needs a fact about the hardware, that
fact goes into `hw::Caps`, never into the caller. Measure on real glass before it ships, and write the number here.

## Places a change touches

`screen_motion.h`, `glass.h` and `glass_core.cpp` (the veil), `sheet_motion.h`, `hw.h` and `hw.cpp` (the rule),
`tests/test_sheet_motion.cpp`, `tests/test_hw.cpp`, this document, and docs/ARCHITECTURE.md when a rule changes.
