# A few cards take 17 to 44 ms to draw

## The symptom
On a Guition 10.1 inch (dev, 2026-11-15) the render log of a2e6d57e named the same slow cards in passes that drew only
a few: a scene card 17 to 18 ms every time it was drawn ("8 cards drawn in 36 ms, slowest tile 41, a scene", 12:42:01,
12:42:13, 12:45:01) and a light card 44 ms in a pass of two cards (12:47:19). Most cards draw in 2 to 8 ms.

## What we know
The scene card's passes are ones where a change repainted all eight cards of a section that follows the contrast, which
the card look in design removes; the time of the scene card itself is not explained by that. The light card's 44 ms
stood alone.

## The deciding experiment
The render log's slowest tile, per card type, on the 10.1 and a 4 inch: the same scene and light card drawn on their
own (a state change of that entity only), with the time split into the card's build (card_shaped false) and its paint.
A card that is built again for a change of value breaks docs/CARD_PARTS.md and is the first thing to look for.

## A player of two by two cells, 33 ms (2026-11-16)
### What was seen
A 10.1 inch logged, with the page opened from Home Assistant inside its service call (builds of 19:57 and
20:19), each time one to four seconds after page 5 opened:

    20:07:41 navigation: page 5 of 6 open from Home Assistant
    20:07:42 page_pic: memory for another page's picture (1 of 3, 2000 KB)
    20:07:43 render: 1 cards drawn in 33 ms, slowest tile 39 (media_player.<player>), 33 ms
    20:07:43 ppa_guard: a copy of 56x194 turned 270 at 16/16 would hang the 2D-DMA (DIG-734): copied in 2 pieces
    20:09:01 render: 1 cards drawn in 32 ms, slowest tile 39 (media_player.<player>), 32 ms

Tile 39 is a square player with `volume_playback`, playing a TV input ("TV", no picture), its volume standing at its
right, in a plain section. The 56 x 194 copy is the volume's strip being put on the turned glass.

With the page built from the loop instead (b8e887c6, the loop's stack fix), the same page and player logged no slow
pass at all: on the build of 22:08 none of 30 ms in two tries of two minutes each, and on the build of 23:55 (the line
speaking from 10 ms in Debug mode, fc5ed36f) none in 100 s across a minute turn; only the page's picture ("page 5: 195
of 240 blocks put in 40.0 ms") and the navigation line. So the 33 ms draw is gone with the page built from the loop.
What it was is not proven: the slow-pass line that would have named its steps came after it was gone.

### Still open: a paint that sets every value again
In the browser preview the same tile is never built again on a change: every object keeps its address and
`card_builds` stays. Its paint costs three to four times a plain tile's, 0.15 against 0.04 ms in a CPU profile with
LVGL's object asserts off, as on the board. That time is the `lv_obj_set_*` calls of `render_tall`, `layout_panel` and
`style_tall`, which set the values the card already has: positions (`lv_obj_set_pos`, `lv_obj_align`, `lv_obj_set_y`),
fonts (`lv_obj_set_style_text_font`) and `center_icon`. LVGL does not compare: each call stores the style, refreshes it
and invalidates the object, and LVGL 9.5 then walks every object of the screen and its layers for a blurred one over
the area (`blur_walk_cb` in `obj_invalidate_area_internal`, src/core/lv_obj_pos.c), hidden ones included. A paint
therefore costs (calls) x (objects on the screen), and the kept pages' objects stand on that screen. Not measured on the
board: the slow-pass line now says the objects on the screen for any pass of 10 ms in Debug mode.

The fix, when it is done, belongs where the guarded setters are (`tile_widgets_lvgl.h`: `set_color`, `set_number`,
`set_hidden`, `set_font`, which set only what changes), never in one card:
1. A test that fails first. The preview counts invalidations: a counter in `web/wasm/firmware_preview.cpp` on
   `lv_obj_invalidate` cannot be had by the linker (`-Wl,--wrap` broke the WASM build, 2026-11-16), so it goes through
   LVGL's own display event instead, `LV_EVENT_INVALIDATE_AREA` (it did not fire in a first try: check in
   `lv_inv_area` of LVGL 9.5 when it is sent), or through a count kept by the guarded setters themselves. A new
   `web/wasm/test_paint_in_place.mjs` sends each kind of tile a state that changes nothing it shows (a square player
   with `volume_playback`, a light with its slider, a cover, a thermostat, a single card) and wants no invalidation.
2. Guarded setters for what is set on every paint and not yet guarded: position (`set_pos` comparing
   `lv_obj_get_style_x`/`_y`), size, align, and the text font where `set_font` is not used yet; `center_icon` sets its
   offset only when the glyph or the box changed.
3. `render_tall`, `layout_panel` (tile_panel.cpp) and `style_tall` call those instead of `lv_obj_set_*`, card by card,
   each with the preview's tests, the layout audit and the paint test before and after, and the CYD's bytes.
4. Whether a kept page's subtree can be left out of LVGL's walk is LVGL's: the walk does not look at
   `LV_OBJ_FLAG_HIDDEN`. Ask upstream (or read a later LVGL) before changing anything there; the project stays on
   LVGL's own code.

## Pointers
`runtime_tiles.h` `render()` (the log line), `render_slot`, `card_shaped()`, docs/CARD_PARTS.md.
