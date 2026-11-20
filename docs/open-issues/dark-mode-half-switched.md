# Dark mode that switches only half

## The symptom

Since 0.4.98 (the card look, docs/THEME.md "A card's look") users report that a change of Dark mode leaves a screen half
switched: the page around the cards turns, the cards do not, or turning back leaves part of the page in the other look.
One report is a 4-inch Guition (2 x 4, graph tiles) whose top-left tile shows only its graph on a black card in the
light look. A 10-inch Waveshare P4 on its home page showed the same: only the frame around the cards went dark.

## What we know

2026-11-18, dev at 75ff7db3 (nothing that touches the look changed since 0.4.98), built with ESPHome 2026.9.0. The glass
was read back after every step and compared with LVGL's own render of the same moment (`glass_snapshot` against
`ui_snapshot`, both of the whole glass, docs/PICTURE_ARCHITECTURE.md), and `glass_burst` caught the first second after
each change. Not reproduced, on a Guition 10.1 (P4) and a Guition 4-inch (S3), both on a test Home Assistant with the app:

- four pages with sections (plain, contrast, contrast with following tiles), graph tiles top left, meters, blinds, eight
  album covers and live cameras;
- Dark mode from the screen's switch in Home Assistant, from the API, and on the screen's settings page;
- page turns in both looks (kept pages and page pictures), quick changes back and forth, a stream of state changes;
- Dark mode changed while the screen slept in standby (LVGL paused), then woken: the first frame after waking is whole;
- the host render with a mirror of every flush (`tools/render`), 10-inch and 4-inch.

After every change the glass equals LVGL's render, but for live pictures and the minute. What a change does show: every
album cover and camera still is asked again in the new look (the look is part of a picture's key), so those cards are
empty for about a second and come back one by one.

Later the same night, with plugins and the rest a busy home has: the 4-inch with air quality, plane radar, new music,
picture frame, departures and the flip clock and photo clock screensavers (installed from the plugin index through the
app), plugin tiles in a contrast section with following tiles; the 10.1 with the same and its own Screen camera live on
the page. Dark mode was changed while the screensaver showed (standby brightness above 0) and the screen was then woken,
while Home Assistant was frozen for 20 s and for 100 s (the screen lost it), and right before Home Assistant restarted.
The released firmware (main, 0.4.98) on the 4-inch went through the same rounds. Every time the glass equalled LVGL's
render once the change was drawn; the only differences were live pictures, a radar's sweep and the minute.

## Ruled out

- The order of drawing in `theme::set_dark()` and the redraw: the first refresh after a change is already whole.
- The settings page's way out, page pictures put on a turn, the veil: all measured whole.
- LVGL 9.6 (ESPHome 2026.11): firmware 0.61.0 did not build there at all before 2026-11-18, so no user ran it.
- A touch during a measurement looked like a reproduction once; the log showed edge swipes. Nobody touches the glass
  during a run.

## Candidates left

- Something only the reporters' setups have: an automation that changes Dark mode together with another setting, a
  layout bigger than the test's, a plugin not tried here, or a board not tried here (the Waveshare 10.1 turns LVGL 270
  degrees, the Guitions 90, and has its own panel timing).
- A firmware older than 0.61.0 on the screen with a newer app, or a build with another ESPHome than 2026.9 or 2026.11.

## The deciding experiment

From a reporter: the board, the firmware number (the screen's Firmware sensor), the ESPHome that built it, how Dark mode
is changed (on the screen, in Home Assistant, an automation), whether the screen was asleep then, and whether a page turn
mends it. Then the same on a bench board with that layout (the app's report from that screen carries it), read back with
`glass_snapshot` and `glass_burst`.

## Pointers

`theme.h` (`set_dark`), `runtime_tiles.h` (`restyle`, `warm_page`), `screen_power.h`,
`screen_diagnostics.h` (the snapshots and the burst).

## Solved: page pictures (2026-11-19)

Caught on the Guition 10.1 with plugins and its Screen camera, after page turns back and forth and a tap on a tile that
opens a card (a plugin's radar, the climate card): the glass showed the page as it was, in blocks of 64 pixels, with
the open card only where streams and pictures had their rooms, while LVGL's own render showed the card whole. The log
showed no put, but a page's picture being taken from the glass ("page 4 taken: 1497 KB in 5 steps") in the second
before the card opened. A take read the frame buffer past the processor's cache (`esp_cache_msync` towards the
processor, which drops what the cache held of those rows), and so threw away what LVGL had just drawn there: LVGL took
it as drawn, the panel never got it. A change of Dark mode is the same whole redraw, which explains a page whose frame
turned and whose cards did not. With page pictures switched off on the same firmware (the diagnostic message
`page_pictures` 0) the owner could not make it happen again. Page pictures were then removed altogether (the commit
that adds this section). They only ever ran on boards with a MIPI-DSI panel (the ESP32-P4 boards); a report from an S3
board (the 4-inch Guition) has another cause and stays to be found from that reporter's details above.
