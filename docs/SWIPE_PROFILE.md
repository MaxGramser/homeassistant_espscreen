# Page swipe profile (2026-09-15, app 0.2.42 / firmware 0.2.36)

Why a page swipe on the Guition blocked the main loop for 300+ ms, what changed, and how to
measure it again. ESPHome 2026.6.2, LVGL 9.5, bench boards on USB.

## How to measure

- Build with `-DSWIPE_PROFILE=1` in `esphome: platformio_options: build_flags` (the bench package
  only; release builds never carry it). Without the define every hook in
  `components/smart_display/swipe_profile.h` is an empty inline.
- One INFO line per page switch, tag `swipe_prof`, times in ms from the swipe (`show_page`):
  `fill` CPU of the swipe pass (firmware 0.2.93+: the whole page; before: `skel` for the
  skeleton pass and `fill` with `steps` for the later fill steps), `first` swipe to
  the first frame on the glass, `done` swipe to the frame that completes the page, `gap` the
  longest main-loop gap until then (touch is polled once per loop), `frames` per LVGL refresh
  `+start:layout/render/flush:flush calls:pixels`, `slots` CPU per card, `parts` CPU per step
  of the passes. The first swipe also logs the object count (Guition: 251 on the screen).
- Render and flush come from `lv_display_add_event_cb` (`LV_EVENT_RENDER_START/READY`,
  `LV_EVENT_FLUSH_START/FINISH`); the loop gap from an `lv_timer` that runs at the start of
  every `lv_timer_handler` call. ESPHome's "took a long time" warning only fires on a new
  maximum, so it is not the metric.
- Without a finger: the diagnostic build accepts
  `{"v":1,"op":"swipe_test","n":12,"ms":1400}` through the `screen_message` action (page switch
  every `ms`; `"back": 150` swipes straight back, `"cards": 3` changes the fill step). It runs
  inside `lv_timer_handler` instead of the touch loop; both land in the same loop iteration.

Layout on a bench Guition: 10 tiles on 2 pages. Page 1: climate, analog clock
without background, two scripts, wide light with a mini slider. Page 2: script, vacuum, two
scripts, wide light with brightness controls.

## Results (median / p90, ms)

| Build | n | first | done | gap | skel CPU | fill CPU | frame 1 render | frame 1 flush | worst frame | frames |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 baseline (0.2.35) | 33 | 80 / 84 | 400 / 412 | 276 / 283 | 26 / 29 | 92 / 209 | 51 / 53 | 26 / 27 | 95 / 100 | 2 / 2 |
| 2 custom parts and panels kept | 12 | 84 / 86 | 285 / 302 | 163 / 170 | 29 / 30 | 91 / 100 | 49 / 52 | 25 / 26 | 94 / 100 | 2 / 2 |
| 3 fill in steps, grey skeleton | 30 | 100 / 107 | 237 / 253 | 125 / 138 | 30 / 36 | 33 / 40 | 61 / 66 | 24 / 25 | 69 / 72 | 3 / 3 |
| 7 final (0.2.36) | 12 | 52 / 54 | 244 / 250 | 74 / 75 | 12 / 13 | 45 / 46 | 38 / 40 | 19 / 21 | 40 / 42 | 4 / 4 |
| 7 final, CYD | 12 | 83 / 84 | 250 / 256 | 109 / 110 | 9 / 9 | 20 / 20 | 67 / 68 | 29 / 30 | 74 / 75 | 3 / 3 |

Builds 1–3 are touch swipes by the owner (build 3 includes taps on the page buttons, which
run inside `lv_timer_handler` and show about 30 ms more gap); build 7 is `swipe_test`.
`worst frame` is layout plus render of the slowest refresh. The CYD had no baseline run in
this round; its log once showed `lvgl took a long time (397 ms)` before.

CPU per card in the content pass, median, baseline → final: to page 1 `11.8, 105.0, 44.8,
12.1, 31.6` → `4.9, 10.1, 3.4, 3.5, 20.3`; to page 2 `12.0, 13.8, 12.9, 12.1, 30.8` →
`4.9, 7.8, 3.4, 3.1, 21.4`.

## What the numbers showed

- The stall was mostly our own content pass, not LVGL's drawing: 207 ms CPU on page 1 before
  a single pixel, then an 80 ms frame. The clock card's 18 parts were deleted when the slot
  showed another card and created again on the way back (105 ms); the next card paid the
  layout of those new objects (45 ms); the wide light rebuilt its control panel (30 ms).
- Every LVGL mutation costs about 0.3 ms on the Guition (objects and styles live in PSRAM,
  16 KB instruction cache, 32 KB data cache), and `lv_obj_update_layout()` walks the whole
  screen. A `lv_obj_set_style_*` with the value the object already has still refreshes and
  invalidates it.
- Flush is about a third of a frame (19–26 ms per ~110–150k px, including LVGL's RGB565 byte
  swap), rendering the rest.

## What changed

1. **Fill in steps** (task step 2). `render()` is split into `render_slot()`. The swipe pass
   places the page (page number, card widths) and shows every card as a skeleton; each LVGL
   refresh after that draws the next two cards (`fill_cards`, one step per `LV_EVENT_REFR_READY`,
   40 ms fallback when a step changed no pixel). A new swipe cancels the fill. `render()` leaves
   waiting cards to the fill; state messages, commands and ticks now draw only their own card
   (`refresh_tile`), the top bar only the bar (`refresh_header_only`); a refresh from the board
   YAML (minute tick, time sync) still draws every card.
2. **One cheap skeleton** (step 3). The skeleton is the empty card: contents hidden under a
   sheet in the card's colour over the content area (plain rectangle, no corners, border or
   layer). The card itself is not restyled and restored any more. First frame 80 → 52 ms.
3. **Less work per card.** Custom parts and control panels are hidden instead of deleted when
   a slot shows another card and reused when the same kind comes back. Colours and opacities go
   through guarded setters (`set_color`, `set_number`) that skip unchanged values. Card content
   sizes come from the styles, so no layout pass per card. Swiping past the first or last page
   draws nothing. Clock cards redraw when the minute changes instead of every second.
4. **Draw buffer** (step 4): not changed. Frames flush 1–10 areas of at most ~20k px each,
   below the 25 % buffer (57.6k px), so a larger buffer would not merge them. Direct mode into
   the RGB framebuffer would need glue around ESPHome's `lvgl`/`st7701s` components, and the
   owner prefers staying on ESPHome's and LVGL's defaults. Dropping LVGL's byte swap
   (`byte_order: little_endian` with a 16-pin `data_pins` list) was not tried for the same
   reason (colour risk on every Guition). `LV_OBJ_STYLE_CACHE=1` was built but not measured
   and is not enabled.
5. **Styles** (step 5): the guarded setters above. Not done: widget `opa` on the disabled
   state of panel keys and detail buttons (only while a command is under way; replacing it
   with `bg_opa`/`text_opa` does not look identical for checked keys), pre-mixed graph and sun
   fills (no graph on the bench layout), a separate measurement of rounded corner masks.

Tried and dropped: a fade-in of each card under a fading sheet (150–180 ms). Completion went to
390–550 ms with 50–100 ms frames (about 10–12 fps) because fading cards redraw completely every
frame; the owner preferred speed.

## Remaining

- CYD: the longest gap is the skeleton frame itself over SPI (51.6k px, 67 ms render incl.
  29 ms flush), about 110 ms.
- A wide card that alternates between a mini slider and a control panel in the same slot still
  costs about 20 ms CPU per switch (real geometry and font changes).

## Update: firmware 0.2.93 (app 0.2.109)

The skeleton and the fill in steps are gone: `show_page` places the page and draws every card
in the same pass, and the refresh after it puts the complete page on the glass in one frame
while the old page stays until then. The steps were introduced above so the loop could poll
touch between them; after the content pass shrank (57 ms CPU for a page on the Guition, 29 ms
on the CYD in build 7) the visible fill cost more in feel than the blocked touch did. The
`swipe_prof` line lost `skel` and `steps`; `fill` is the whole pass. The frame counts in the
table above are therefore two for a switch now (the old page, then the new one), not three or
four. A fade or a slide stays out for the reason measured above: a screen-wide animation is a
full software redraw per frame, 50 to 110 ms on these boards.

## Update: firmware 0.3.2, kept and prepared pages

A board with PSRAM now keeps every page it has built and builds them all before the first page opens
([KEPT_PAGES.md](KEPT_PAGES.md)). Measured on the 4-inch Guition with an eight-page stress layout (median, ms):

| Build | fill | first | slots drawn |
| --- | --- | --- | --- |
| Firmware 0.2.104 (app 0.2.133), every page built on the switch | 49 | 134 | every card |
| Firmware 0.3.1, every page built on the switch | 54 | 134 | every card |
| Firmware 0.3.2, first tour after the start | 28 | 104 | only a card whose tile changed |

`first` still holds the frame itself, which the cards cannot shorten: 55 to 70 ms of rendering and 20 to 25 ms of
flush for most pages, about 200 ms for a page with a graph and a sun path. The media card over the whole page went
from 250 ms to 90 ms, as its cover is kept.

Two things this round found about measuring:

- `swipe_test` is now handled before the add-on's session is checked, so a bench script can send it again (since
  firmware 0.3.0 it sat behind the session and never ran). It does not count as using the screen: "Back to page 1"
  brings an untouched screen home in the middle of a test. The screen's own `show_page` action counts as use and gives
  the same `swipe_prof` lines.
- The firmware 0.2.104 comparison above came from that firmware on the same board with the add-on's legacy delivery,
  which sent it only four of the eight pages, so only those four pages are compared.

