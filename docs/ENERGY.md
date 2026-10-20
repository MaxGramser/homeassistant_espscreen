# The energy card

The energy card (app 0.4.77, firmware 0.47.0) shows the power of a house right now, the way Home Assistant's own live
Energy view (the power sankey) and power-flow-card-plus show it: a circle for solar, the grid and the battery around a
circle for the house, a line for each flow with dots that run along it, and the devices that draw the most power.

It needs nothing of its own. Everything comes from the Energy settings in Home Assistant (Settings, Dashboards, Energy).

## What it reads

The add-on asks Home Assistant for its Energy settings (`energy/get_prefs`) and reads them again every five minutes:

- a power sensor (`stat_rate`) for each grid connection, solar array and battery. Home Assistant itself turns an
  inverted sensor or a pair of import and export sensors into one `stat_rate`. Before Home Assistant 2026.3 a grid kept
  its power sensors in a list of its own (`power`), and the card adds those up as Home Assistant's frontend did then;
- the battery's charge (`stat_soc`), combined as Home Assistant's energy distribution card combines it: weighted by each
  battery's usable capacity (`capacity`), a battery without one counting as the mean of the others;
- the devices with a power sensor (`device_consumption`), split as Home Assistant's live view splits them
  (`buildSankeyDeviceNodes` in common/sankey.ts): a device that is part of another one (`included_in_stat`) is already
  in the value of the first device up its chain that the view draws; with none drawn above it, it stands under the
  house itself. A sensor without a number counts as 0 W.

`screen_manager/app/energy_flow.py` works out the moment step for step as Home Assistant's frontend does
(`_computePowerData` in hui-power-sankey-card.ts):

- a sensor's value in W is `getPowerFromState`, the number scaled by its unit's prefix (kW, MW);
- solar counts only while it produces;
- the grid splits into import and export, and the batteries into discharge and charge;
- the flows between them are routed in Home Assistant's order;
- a device under 0.1 % of the house has no place of its own, as the sankey's threshold does, and counts in Other.

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
- Each dot keeps its own place on its line and moves on by the time since its last frame, at its line's pace now. A
  new value changes how fast a dot runs, never where it is: a dot belongs to its line, so a line that stays keeps its
  dot, and only a new line starts one.
- A new value is painted in place (docs/CARD_PARTS.md): while every circle, line and turn stays where it was, only the
  words that changed and the house's ring are drawn again. The form, fonts and places the card chose are kept
  (`ChoiceCache`) until its shape changes (its size, its sources, its devices' names) or a number outgrows the room it
  was given. The search behind that choice took about 300 ms on an ESP32-S3 and held the whole screen at every value;
  a new value now takes a few milliseconds. `tests/test_energy_card.cpp` proves a kept choice draws what a fresh
  search draws.
- Nothing runs while the screen sleeps, while the card is off the glass, or while a card is open over it.

### Dots or lines

The editor's Flow choice (the tile's `flow`, `energy` in catalogue/screen.yaml) sets how power shows along a line.
Moving dots is the default and is never stored. Lines and arrows is calm: no dot runs and no timer ticks. A line that
carries power grows thicker in two steps up to 2 kW, the power at which a dot runs its fastest, and has an arrow halfway
along it in its colour, pointing the way the power goes (`flow_width` and `Arrow` in `energy_card.h`). Each step adds
the same even number of pixels, so a line stays centred on the pixel grid of its turns. No line grows past a quarter of
the room between two neighbours, and an arrow is never longer than half the part of its line that shows between two
circles. A firmware that doesn't know the choice keeps the dots.

The card is responsive the way every card is: it takes the richest form and the largest of the board's fonts that fit.

1. Both directions of a flow, then one direction.
2. Without arrows, then without names.
3. A compact form with the numbers in the names' place.

It turns the diagram upright when that leaves bigger circles, which is how a screen standing up shows it. It shows up to
four devices. When there are more devices than places, the biggest keep a place and the smallest share the last one as
Other, at least two of them, as Home Assistant's sankey groups its smallest devices. The devices that keep a place stand
in the order of the Energy settings, as Home Assistant shows them.

What no device measures is Untracked consumption, as Home Assistant's sankey draws it (`common/sankey.ts`): the house
less every device and Other, shown from 1 W, in the last place. The devices, Other and it add up to the house. It takes
a place where the devices before it all fit, or from three places on with Other beside it; two places for more devices
than one stay the biggest and Other, so no device goes missing from the sum. The card works it out from the moment it
has; a house without a measured device keeps it in the house's own number, where a circle of its own would only repeat
it. Its name is Home Assistant's short word for it (`energy_devices_detail_graph.untracked`, "Untracked"), which fits
where a device's name fits; the long one takes two lines that a card seldom has. Other and Untracked are grey, Home
Assistant's `--state-unavailable-color`, and have no sensor, so a tap on them does nothing.

The battery's charge stands beside its glyph, as Home Assistant's energy distribution card shows it. In the compact form,
whose circles hold their icon alone, it stands before the battery's number under the circle. Only where even that does
not fit is the glyph, which fills with the charge, left to show it; no card the editor offers is that small.

Every name stands centred under or over its own circle; only a name that would cross the card's edge moves in, as far
as it must. A device's name wraps to two lines before the card drops a device. Only when no device fits with its whole name are the
names cut with three dots, as power-flow-card-plus cuts them.

Room is kept for the widest number the card has shown, so a car that charges at 11 kW does not make the circles grow
and shrink.

### Sizes

The diagram needs at least 30 mm of width and 25 mm of height on the compact look, 32 mm on the standard look
(`MIN_WIDTH_MM` and `MIN_HEIGHT_MM_*` in `energy_card.h`). `tests/test_energy_card.cpp` proves it fits from there up
on every density and look a board has, with seven devices and a car at 11 kW. The editor offers only sizes that big
(`energyFits` in `web/src/model/ui-scale.ts`, the same numbers, measured with a page bar under the tiles). A new card
starts 2 × 2 where that fits, else at the smallest size that does: a page of its own on the CYD lying down, three rows on
the CYD standing up, two columns of the whole height on the Waveshare 4.3-inch. A card lower than that, which the editor does not offer, shows the house's use alone.

### A tap

A tap on a circle with a sensor behind it opens that sensor's history card, as a circle of Home Assistant's live view
opens its more-info. The house and Other have no sensor of their own, so a tap on them does nothing. A source with
more than one power sensor (two solar arrays, two grid connections) opens their sum, as Home Assistant's "Power
sources" graph adds them up (power-sources-graph-data.ts): the add-on sends a key of its own for the sum
(`energy_flow.SUMS`) and answers its history from the sensors' hourly statistics for a day or a week and from their
changes for an hour, in W. The add-on answers the history of a sensor in the Energy settings of a screen that has an
energy card, as it answers the history of a tile.

## Energy over a period

The tile's **Show** choice (its `period`, `energy` in catalogue/screen.yaml) is **Power now**, the default and never
stored, or **Today**, **This week**, **This month** or **This year**. A card of a period shows the same diagram with
how much each source gave and took in kWh, and each device's use, the way Home Assistant's energy dashboard shows that
period in its energy distribution and energy sankey cards.

### What it reads

The energy statistics of the Energy settings: each grid's import and export (`stat_energy_from`, `stat_energy_to`),
each solar array, each battery's discharge and charge, and each device's use (`stat_consumption`). The add-on asks the
recorder for their `change` in kWh (`recorder/statistics_during_period`, as `getEnergyData` in data/energy.ts asks), per
hour for a day, per day for a week or a month, and per month for a year (`getSuggestedPeriod`).

`energy_flow.period_moment` splits each of those hours, days or months on its own, in Home Assistant's order
(`computeConsumptionSingle`, the same `route()` the power now uses), and adds them up. Split once over the whole period,
solar sent to the grid at noon and energy taken from it at night would look like solar used in the house. A device's
use is the sum of its changes (`calculateStatisticSumGrowth`), split under the house as the energy sankey card splits
it: a device inside another counts in that one, and a device under 0.1 % of the house goes to Other.

A period begins at midnight in Home Assistant's time zone. A week begins on the first day of the week of the screen's
language, as Home Assistant's frontend begins it (`firstWeekdayIndex`, `Intl.Locale` weekInfo): Sunday for English and
Portuguese, Monday for British English and the other languages. The period now is read again every five minutes, as
often as the Energy settings. A period gone by is kept for six hours. Like Home Assistant's own dashboard, today's
numbers come from the hourly statistics, so the hour that is running is not in them yet.

### On the glass

The card names its period over the diagram ("Today", "19 – 25 Oct", "October 2026", "2026"), in the smallest font, where
that leaves the diagram the room it needs (the CYD's page has none to spare, so there the name shows only full screen).
The lines keep one width and carry an arrow the way the energy went; no dot runs and no timer ticks. The grid and the
battery show both directions, the house's ring the shares of what fed it, and the numbers are written as Home Assistant
writes energy (`formatConsumptionShort`): kWh with at most two decimals below 10 and one below 100, Wh below 1 kWh and
MWh from 1000 kWh. The battery's charge, a moment, is not shown for a period.

A tap on the card opens its full screen, as a tap on a calendar card does. Its header is the calendar card's: a close
key, the card's name with the period under it, the units Day, Week, Month and Year as keys (the chosen one blue; every
choice shows, there is no menu), Today, and back and forward. The ranges and the stepping follow Home Assistant's energy
period selector: a step back or forward is a whole day, week, month or year, forward stops at the period now, and back
goes up to about ten years (`MAX_BACK`). Today goes back to the period now of the unit on show. Narrow glass puts the
units on a row of their own under the rest, and then turns Today into a round key with the calendar icon. A tap on a
circle with a sensor behind it opens that sensor's history, as on the card of the power now.

The full screen opens on the tile's own period, now, and follows the tile's numbers while it shows them. Any other
period it asks the add-on for (`esphome.screen_energy`: `inbox`, `unit`, `offset`), which answers with op `energy` and
the period's `x`. While it waits the last diagram stays and the line under the name is empty.

A screen says it draws a period in its hello (`energy_period`, packages/core.yaml). The add-on sends a screen without it
the power now, whatever the card's choice, as the choice's hint in the editor says.

## On the wire

The card is a screen card, `screen.energy`, whose state message carries the moment in `x` (`energy_flow.payload`,
read by `page_receiver.cpp`):

| key | what |
|---|---|
| `h` | what the house has: 1 solar, 2 grid, 4 battery |
| `p` | power in W: solar, from the grid, to the grid, from the battery, to the battery, the house |
| `f` | the flows in W: solar to the house, to the grid, to the battery; grid to the house, to the battery; battery to the house, to the grid |
| `c` | the batteries' charge in %, where they report one |
| `e`, `u` | the sensor behind each source (solar, grid, battery), or the key of their sum, and its state and unit, for the history card |
| `d` | the eight biggest devices at most, in the order of the Energy settings: name `n`, sensor `e`, icon `i`, power `w`, state `s`, unit `u` |
| `n` | the home's name in Home Assistant |
| `o` | the power of the devices beyond those eight and of those under 0.1 % of the house (Other) |

A card of a period (`energy_flow.period_payload`) has the same keys with every number in kWh and no `c`, and these:

| key | what |
|---|---|
| `k` | the unit: `day`, `week`, `month` or `year` |
| `r` | its first and last day: year, month and day of each |
| `z` | how many units it lies back: 0 for the period now, -1 for the one before |
| `y` | the year now, so a day or a week of another year says its year |
| `w` | 1 while the add-on has not read the period yet; the card then shows nothing and waits |

## Memory

The card keeps the moment, its diagram and a small picture per running dot, about 4 to 8 KB depending on the glass.
Its price in the memory budget is its own (`cards` in `catalogue/screen.yaml`, docs/TILE_MEMORY.md), not the 32 bytes of
the other screen cards.

## Places a change touches

- `screen_manager/app/energy_flow.py` and `tests/test_energy_flow.py` (with `tests/fixtures/energy/`) for what the card
  says; `tests/test_energy_period.py` for a period, and `Manager.energy_period`, `answer_energy` and `energy_loop` in
  `server.py` for how the add-on reads and sends one.
- `catalogue/screen.yaml` (`energy`: `flow`, `period`), then tools/generate_catalogue.py and tools/generate_page_rules.py.
- `page_receiver.cpp` (`parse_energy`, op `energy`) and the `energy_period` feature in packages/core.yaml.
- `components/smart_display/energy_card.h` and `tests/test_energy_card.cpp` for where things go, the full screen's
  header (`header`) and a period's numbers and name (`energy`, `period_text`) included.
- `energy_view.cpp` for how it is painted, and for the full screen (`open`, `receive`).
- `web/src/components/TileInspector.vue` (Show and Flow), `web/src/components/tile/TileEnergy.vue` (the mockup), and the
  `editor.tile.energy` and `screen.energy` texts of every language.
- `web/src/model/ui-scale.ts` (`ENERGY_MIN_MM`) together with `MIN_*_MM`: a parity test compares them.
- `tools/render/energy_tiles.py` renders the card on any board with the real firmware.
