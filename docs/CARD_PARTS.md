# Cards that paint themselves

A card (the view a tile opens) is built once and then changes in place. Building a whole card takes up to half a second
on a 4-inch screen, and during that time the screen does nothing else: a title stops rolling, a tap waits. So when a
value on an open card changes, through a finger (docs/OPTIMISTIC.md) or through a state from Home Assistant, only the
parts that show that value are painted again, and LVGL redraws only the pixels that changed.

This follows LVGL's own advice (create objects once, change their properties, never delete and recreate them for an
update) and the idea of its observer module, where a widget is bound to a value and follows it. Home Assistant's
frontend works the same way: a state change updates the bindings that read it, not the whole dialog.

## How a card does it

While it builds, a card binds every part that shows a value:

```cpp
card_bind(key, t, climate_mode_paint, mode);         // a mode key, and the mode it stands for
card_bind(number, t, climate_number_paint);          // the number between - and +
```

- `card_bind(obj, t, paint, value, arg)` stores the part and paints it once, so the first look and every later one come
  from the same function and can never differ.
- `paint(obj, t, part)` reads the tile and sets what the part shows: a text through `label()`, a colour through
  `set_color()`, a state, a hidden flag. These helpers change a property only when it differs, so a paint that finds
  nothing new costs nothing on the glass. `part.value` and `part.arg` say what the part stands for (the mode of a mode
  key, the kind of a row).

At its end the card names its shape:

```cpp
card_shaped(t, climate_card_shape);
```

The shape is a fingerprint of everything that decides which parts exist and where they stand: which modes and rows a
thermostat has, whether a player is off or at rest, which keys it has. It leaves out what the parts paint.

On every change `card_repaint(t)` compares the shape with the one the card was built with. The same shape runs every
paint function; another shape builds the card again, as every card did before. A card that binds nothing names no
shape and is always built again: correct, only slower. So a card moves onto this one at a time.

## Rules

- A part that shows a value binds it. Never set that value on the object in the builder as well.
- A value that changes which parts exist, their size or their place belongs in the shape. When in doubt, put it in the
  shape: the card is built again, which is slow but never wrong.
- A paint function only reads the tile and sets properties of its own object. It creates and deletes nothing, so it is
  safe under a finger and inside a key's own event.
- A part a value hides is built anyway and hidden by its paint (the dot under the shuffle key), so showing it is a
  paint and not a new shape.
- A wish (docs/OPTIMISTIC.md) writes its value into the tile and calls `card_repaint`; nothing else is needed for a card
  that paints itself.

## Writing a paint function

- Change a property only when it differs: `label()` for text, `set_color()`, `set_number()`, `set_hidden()`,
  `paint_state()` for a state such as `LV_STATE_DISABLED`, `paint_glyph()` for a key's icon (it measures the glyph to
  centre it, so only a new glyph pays for that). Calling `lv_obj_set_style_*` directly restyles the object even when
  nothing changed: twenty parts of the climate card took 77 ms that way and take 2 to 11 ms with these helpers.
- Work something out once per paint of the card, not once per part: `card_pass` counts the paints, so a row of six
  segments reads the thermostat's rows once (`climate_row_paint`).
- A key that fades for a reason of its own (- at the end of the span, a blind at its end stop) also fades while the
  card waits: `paint_state(key, LV_STATE_DISABLED, card_blocked || own_reason)`. `tick()` sets `card_blocked` and
  repaints the card when it changes, so the two never fight over the key.
- Building the card calls the same paint through `card_bind`, so the builder leaves out what the paint sets.

## Testing

`web/wasm/test_card_parts.mjs` runs the real firmware in the WASM preview on the smallest, a middle and the largest
glass. For every case it opens a card, sends a state with the same shape, and wants two things: the card was not built
again (`preview_card_builds`), and the glass is pixel for pixel the card built anew with that state (`preview_card`).
A part that shows a value but was never bound, or a value missing from the shape, fails it with the pixels that differ.
A new card that paints itself adds its cases there. `tests/test_optimistic_rule.py` checks that the bound cards name
their shape and that a change tries a paint before it builds.

## Security cards

The lock and alarm cards paint only their status line in place. Every state (locked, unlocking, arming), every step of a
code, an attempt on its way, a second tap asked for and a lockout are their shape (`security_card_shape`), so each of
those builds the card exactly as it always did, with the ring that beats while it moves and the spring when it arrives.
A message that changes nothing they draw (who locked it last) is painted. A test wants a new state to build the card.

## Picture cards

The weather card and the history card are pictures of their values: the days, a sensor's graph and the scale under it.
Their shape is the whole message from Home Assistant, the page or range they show and the history they drew
(`picture_card_shape`), so they are built again when one of those changes and skip a message that changes nothing.

## The pages over a card

A light group's lamp page and a light's effects page (`group_page.h`, `effects_page.h`) are built when they open and
paint themselves from the tile on every change (`updated`): they rebuild only when the lamps or rows change. Their
changes are wishes (docs/OPTIMISTIC.md, "Parts of an entity"), so they show what the tile holds and keep no hold of
their own.

## Which cards paint themselves

- **Climate and humidifier:** the mode keys, the fan and swing rows, the number, the - and + at the ends of the span,
  the power key and the status line. A range's band and a humidifier's ring draw their values into their shape, so
  they are built again when those change.
- **Media player:** play or pause, the title and the artist (a new text starts its roll again, the same text rolls on),
  shuffle and its dot, repeat, mute, the volume slider, the progress bar and its times, the cover and the card's colour.
  A new track paints the card: the words and the bar at once, the cover and its colour together once the new cover is
  here, the old ones until then (`MediaFace` in `runtime_tiles.h`). Only a track of an hour or more, whose times need
  more room beside the bar, builds it again.
- **Light and fan:** the power key, the slider, the round field of a light that only switches, the icon and the value.
- **Cover:** the position and tilt sliders and their values (they follow the blind as it moves), the keys with the
  direction it moves in and its end stops, the icon of a door that only opens and closes.
- **Select:** the chosen option and its tick. **Remote:** the power key and the chosen activity.
- **Vacuum:** the chips of its rows and its state line.
- **Timer and sun:** their words.
- **Every card's status line** under the name.

- **Lock and alarm:** their status line; everything else is their shape (see "Security cards").
- **Weather and history:** built from their values (see "Picture cards").

Every card the runtime builds names a shape. A new card does the same, or it is built again on every change.
