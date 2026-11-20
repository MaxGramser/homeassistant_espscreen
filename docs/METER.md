# The meter

A display for a sensor tile that shows where its value stands in a range: a ring, a tape or a bar of cells. It fits any
size a screen takes, from one cell to the whole page, lying down and standing up, and grows with the room it gets. Any
sensor whose state is a number can show it (the same sensors that can show a graph).

## The three looks

| Look | What you see |
|---|---|
| Ring | A ring open at the bottom, filled to the value on a grey track, with the tile's icon in its tinted circle in the middle. The value and its unit stand under the ring's ends, the name quiet under them; on a long, low card they stand beside the ring. On a roomy long card (360 px of the look and more) the right half shows the last 24 hours as a line with a soft fill. |
| Tape | The name in small capitals and the value large, over a still ruler of hairline marks across the tile's range, with one pointer at the value. The two ends of the range are named small under their marks; a percentage names none, since everyone knows its ends. |
| Bar | The value and the name at the top, and under them narrow cells over all the room that is left, lit in the value's colour, the rest a dim tint of the same colour. A standing card stands the bar up beside the words. A big card gets wider cells, never more than 60, as a real LED bar graph has. |

Every look takes the largest of the board's fixed fonts that fits, up to the large digits of the thermostat's
setpoint, so a meter on a large card is readable across a room. Nothing else is drawn: no numbers along a percentage,
no gradients, no extra lines. The ring's icon takes its size from the card's own icon font, never from another card on
the glass, and always a face that has the glyph: the largest that fits the circle, else the smallest that has it.

## The first look

A sensor that is added to a screen starts as a meter, so the meter is seen without being looked for
(`web/src/model/sensor-look.ts`). The look follows what Home Assistant says the sensor measures:

| The sensor | Starts as | Its range |
|---|---|---|
| A battery | Bar | 0 to 100 % |
| A percentage (humidity, moisture, a level) | Ring | 0 to 100 % |
| A temperature | Tape | a room's, 10 to 30 °C or 50 to 86 °F, widened in steps of 5 to hold the value now |
| Any other number (power, CO2, light) | Bar | from 0 to a round number above the value now (840 W: 0 to 1000) |

It keeps the plain value when the sensor is a counter (state class `total` or `total_increasing`, such as an energy
meter's kWh, where a meter would only fill up), when its state is no number, and on a screen whose firmware draws no
meter (older than 0.56.0). The same rule gives Auto layout's one-cell sensors their look (docs/AUTO_LAYOUT.md).

Beside a sensor just added as a meter, a tip asks how it should look: the ring, the tape, the bar, its graph, the large
value or just the value. A look the pointer rests on is drawn on the tile, a click keeps it, and the meter's looks keep the range it
started with. "Don't show again" puts the tip away for good (the browser remembers it); the Display field of the
tile's settings has every look as before. `web/tests/sensor-look.spec.ts` proves the rule and the tip.

## The range

**From Home Assistant** is the default. A percentage runs from 0 to 100. Home Assistant states no range for any other
sensor, so it runs from 0 to 100 as Home Assistant's own gauge card does, and a temperature, a CO2 level or a power
needs a range of its own: the editor says so when the value falls outside the range, and fills in a range to start
from. **Custom** sets a minimum and a maximum for the tile. A value outside the range stands at its end.

## The decimals

The value shows as many decimals as Home Assistant's own Display precision for the sensor says, as on its dashboards.
The editor offers that setting beside the sensor's tile, as Home Assistant's entity settings do (Default, or 0 to 6),
and changes it in Home Assistant. A duration in minutes, hours or days reads as Home Assistant writes it ("1h 30m").

## The colour

One, two or three segments:

- **One**: one colour, by default the tile's own (Home Assistant's colour for the sensor), or one you choose.
- **Two**: green up to a threshold, red from it.
- **Three**: green, orange from the first threshold, red from the second.

Each colour is one of Home Assistant's theme colours, and each threshold is a value in the sensor's own unit (800 ppm,
24 °C, 2400 W). When you choose two or three segments the editor puts the thresholds at 80 % and 90 % of the tile's
range, which you can change; a screen that gets no thresholds puts them there too. A battery that should be red when
low is the same choice with the colours the other way round.

The ring fills in the colour of the segment the value is in, the tape's pointer takes it (one segment keeps the tape's
orange pointer, unless a colour was chosen), and every cell of the bar wears the colour of its own place, lit or dim,
so the bar shows where orange and red begin.

## How it reaches the screen

The tile's options (`screen_manager/app/meter.py` checks them and leaves out the defaults):

| Option | Values | Default |
|---|---|---|
| `meter` | `ring`, `tape`, `bar` | `ring` |
| `min`, `max` | numbers, both or neither, `min` below `max` | the range from Home Assistant |
| `segments` | 1, 2, 3 | 1 |
| `colors` | one of Home Assistant's theme colours by name per segment | the tile's own; green and red; green, orange and red |
| `thresholds` | one number fewer than the segments, rising, in the sensor's unit | 80 % and 90 % of the range |

The app sends the colours as numbers, so the screen keeps no table of names. The meter needs firmware 0.56.0; the app
asks an older screen to update first. The screen plans each card in `components/smart_display/meter_card.h` and paints
it in one object per card (`meter_paint.h`, `meter_view.cpp`), so a bar of 60 cells or a ruler of 50 marks costs one
object, and draws every text through `draw_text::label`, which has LVGL keep a copy until it draws. `tools/render/meter_firmware.py` renders the same planner and painter on every board's grid, every span and
both looks, and counts any word that had to be shortened and anything outside its card; `tests/test_meter_card.cpp`
checks the plans on every span of the boards' grids.
