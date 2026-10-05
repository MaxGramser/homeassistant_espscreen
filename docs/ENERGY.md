# The energy card

The energy card (app 0.4.77, firmware 0.47.0) shows the power of a house right now, the way Home Assistant's own live
Energy view (the power sankey) and power-flow-card-plus show it: a circle for solar, the grid and the battery around a
circle for the house, a line for each flow with dots that run along it, and the devices that draw the most power.

It needs nothing of its own. Everything comes from the Energy settings in Home Assistant (Settings, Dashboards, Energy).

## What it reads

The add-on asks Home Assistant for its Energy settings (`energy/get_prefs`) and reads them again every five minutes:

- a power sensor (`stat_rate`) for each grid connection, solar array and battery. Home Assistant itself turns an
  inverted sensor or a pair of import and export sensors into one `stat_rate`;
- the battery's charge (`stat_soc`), combined as Home Assistant's energy distribution card combines it: weighted by each
  battery's usable capacity (`capacity`), a battery without one counting as the mean of the others;
- the devices with a power sensor (`device_consumption`). Only the top of Home Assistant's device tree counts: a device
  that is part of another one (`included_in_stat`) is already in that one's value.

`screen_manager/app/energy_flow.py` works out the moment step for step as Home Assistant's frontend does
(`_computePowerData` in hui-power-sankey-card.ts):

- a sensor's value in W is `getPowerFromState`, the number scaled by its unit's prefix (kW, MW);
- solar counts only while it produces;
- the grid splits into import and export, and the batteries into discharge and charge;
- the flows between them are routed in Home Assistant's order;
- a device under 0.1 % of the house is left out, as the sankey's threshold does.

A device is named as Home Assistant names it in the Energy view: its display name there, else the sensor's name. Its icon
is the sensor's own, else a lightning bolt. The house is named after the home, its name in Home Assistant
(`location_name`), as Home Assistant's live power view names it. Numbers are written the way the screen writes every
number (Settings, Language & region): a decimal comma where the language takes one.

When a sensor changes, the card gets the new moment. A house without any power sensor in its Energy settings gets one
sentence on the card that says where to add them, as Home Assistant hides its own live view then.

## On the glass

`components/smart_display/energy_card.h` places everything and `energy_view.cpp` paints it. The whole diagram is one
LVGL object that draws in its draw event, so a card costs one object however many circles it has.

- The geometry is power-flow-card-plus's: circles of the same size, the house's ring split by where its power comes
  from, lines a circle's fifth apart, and quarter turns where a line bends.
- The colours are Home Assistant's energy colours, as `theme.h` roles (`ENERGY_*`).
- A dot's pace follows power-flow-card-plus: six seconds along its line at no power, three quarters of a second from
  2 kW up.
- The dots run on their own timer, 25 frames a second. Each frame redraws only the pixels a dot leaves and enters. A
  dot is a small alpha picture placed to the sub-pixel, so it stays in the middle of its line while it moves.
- Nothing runs while the screen sleeps, while the card is off the glass, or while a card is open over it.

The card is responsive the way every card is: it takes the richest form and the largest of the board's fonts that fit.

1. Both directions of a flow, then one direction.
2. Without arrows, then without names.
3. A compact form with the numbers in the names' place.

It turns the diagram upright when that leaves bigger circles, which is how a screen standing up shows it. It shows up to
four devices. When there are more devices than places, the biggest keep a place and the smallest share the last one as
Other, at least two of them, as Home Assistant's sankey groups its smallest devices. The devices that keep a place stand
in the order of the Energy settings, as Home Assistant shows them.
What no device measures stays in the house's own number, as in power-flow-card-plus; Home Assistant's sankey draws it
as a node of its own ("Untracked consumption"), which a card of four places has no room for.

A device's name wraps to two lines before the card drops a device. Only when no device fits with its whole name are the
names cut with three dots, as power-flow-card-plus cuts them.

Room is kept for the widest number the card has shown, so a car that charges at 11 kW does not make the circles grow
and shrink.

### Sizes

The diagram needs at least 30 mm of width and 25 mm of height on the compact look, 32 mm on the standard look
(`MIN_WIDTH_MM` and `MIN_HEIGHT_MM_*` in `energy_card.h`). `tests/test_energy_card.cpp` proves it fits from there up
on every density and look a board has, with seven devices and a car at 11 kW. The editor offers only sizes that big
(`energyFits` in `web/src/model/ui-scale.ts`, the same numbers, measured with a page bar under the tiles). A new card
starts 2 × 2 where that fits, else at the smallest size that does: a page of its own on the CYD lying down, three rows on
the CYD standing up. A card lower than that, which the editor does not offer, shows the house's use alone.

### A tap

A tap on a circle with a sensor behind it opens that sensor's history card, as a circle of Home Assistant's live view
opens its more-info. The house and Other have no sensor of their own, so a tap on them does nothing. A source with
more than one sensor (two solar arrays) has no single sensor to open either. The add-on answers the history of a
sensor in the Energy settings of a screen that has an energy card, as it answers the history of a tile.

## On the wire

The card is a screen card, `screen.energy`, whose state message carries the moment in `x` (`energy_flow.payload`,
read by `page_receiver.cpp`):

| key | what |
|---|---|
| `h` | what the house has: 1 solar, 2 grid, 4 battery |
| `p` | power in W: solar, from the grid, to the grid, from the battery, to the battery, the house |
| `f` | the flows in W: solar to the house, to the grid, to the battery; grid to the house, to the battery; battery to the house, to the grid |
| `c` | the batteries' charge in %, where they report one |
| `e`, `u` | the sensor behind each source (solar, grid, battery) and its state and unit, for the history card |
| `d` | the eight biggest devices at most, in the order of the Energy settings: name `n`, sensor `e`, icon `i`, power `w`, state `s`, unit `u` |
| `n` | the home's name in Home Assistant |
| `o` | the power of the devices beyond those eight |

## Memory

The card keeps the moment, its diagram and a small picture per running dot, about 4 to 8 KB depending on the glass.
Its price in the memory budget is its own (`cards` in `catalogue/screen.yaml`, docs/TILE_MEMORY.md), not the 32 bytes of
the other screen cards.

## Places a change touches

- `screen_manager/app/energy_flow.py` and `tests/test_energy_flow.py` (with `tests/fixtures/energy/`) for what the card
  says.
- `components/smart_display/energy_card.h` and `tests/test_energy_card.cpp` for where things go.
- `energy_view.cpp` for how it is painted.
- `web/src/model/ui-scale.ts` (`ENERGY_MIN_MM`) together with `MIN_*_MM`: a parity test compares them.
- `tools/render/energy_tiles.py` renders the card on any board with the real firmware.
