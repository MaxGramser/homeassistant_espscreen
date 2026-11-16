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
The same 10.1 inch logged "1 cards drawn in 33 ms, slowest tile 39 (a media player)" one to four seconds after its page
opened, twice. The tile is a square player with `volume_playback`, playing, its volume standing at its right, in a
section. In the browser preview the same tile is never built again on a change: every object keeps its address, and
`card_builds` stays where it was. Its paint costs three to four times a plain tile's, 0.15 against 0.04 ms in a CPU
profile with LVGL's object asserts off, as on the board. That time is the `lv_obj_set_*` calls of `render_tall`,
`layout_panel` and `style_tall`, which set the values a card already has again. Each such call refreshes the style and
invalidates the object, and LVGL 9.5 then walks every object on the screen and its layers (`blur_walk_cb` in
`obj_invalidate_area_internal`, looking for a blurred object over the area). A paint therefore costs (calls) x
(objects on the screen), and with kept pages the objects of every page stay on the screen. The preview did not grow
with six pages of tiles, so the 33 ms is not proven from it yet.

What the board's line says now: a pass of 30 ms or more names its slowest card's steps in ms (render_slot's laps:
text, busy, layout, custom, panel, geometry, palette), what asked for that card to be drawn (`redraw_log::TileWhy`: a
state, a wish, a picture, the minute, its wait, a finger, ...), and how many objects stand on the screen:
"N cards drawn in T ms, slowest tile I (entity), S ms: <step> <ms>, ... ms, marked by <reason>; O objects on the
screen". A playing player shows the time (`shows_time`), so the minute marks it too.

## Pointers
`runtime_tiles.h` `render()` (the log line), `render_slot`, `card_shaped()`, docs/CARD_PARTS.md.
