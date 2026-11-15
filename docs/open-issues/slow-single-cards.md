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

## Pointers
`runtime_tiles.h` `render()` (the log line), `render_slot`, `card_shaped()`, docs/CARD_PARTS.md.
