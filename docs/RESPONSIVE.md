# One firmware, any board: how the screens fit their glass

Since app 0.2.94 (firmware 0.2.80) a board says what its glass is and the firmware, the add-on and the editor
follow: the tile grid, the size of everything drawn, the cards a tap opens. The CYD and the Guition were the
first two boards and render as they did before; the Waveshare ESP32-S3-Touch-LCD-4.3 (800 x 480, three by
three) was the first board added this way. The rule for every change here: the two first boards keep their
pixels, and nothing is written that knows a board by its name.

## The idea

A screen hangs on a wall and is used from arm's length whatever its size. So a tile, a letter and a
key keep their **physical size**; a larger or sharper panel does not get bigger tiles, it gets **more
tiles**. Everything the firmware draws is therefore defined in a *look* (millimetres, expressed as the
pixels of a reference board) and scaled to the board's pixel density.

## What a board declares

In its board file under `packages/boards/`, next to its hardware:

| Substitution | Meaning |
|---|---|
| `PANEL_W`, `PANEL_H` | the panel's own pixels; the display block always drives it at this size |
| `ROTATION_LANDSCAPE` | the LVGL angle that lays that panel out lying down (a CYD 90, a Waveshare 0) |
| `LVGL_ROTATION` | which way this screen hangs; ESP Screens writes it when the screen is built |
| `DISPLAY_DPI` | diagonal pixels / diagonal inches (the CYD 2.8″: 143, the Guition 4.0″: 170) |
| the look (`packages/looks/`) | `standard` (the Guition's sizes) or `compact` (the CYD's, for glass too small for the standard); the board file includes one |
| `GRID_COLS`, `GRID_ROWS` | the cells of a page lying down; the shared tree places every cell from these |
| `GRID_COLS_PORTRAIT`, `GRID_ROWS_PORTRAIT` | the cells of a page standing up (a square board repeats the first pair) |
| `GRID_MARGIN`, `GRID_GAP_X`, `GRID_GAP_Y` | the side margin and the gaps between cells, in pixels |
| the sizes (`TILE_ICON_SIZE`, `FONT_*_SIZE`, …) | worked out by the look at this board's density; a board states one only when its glass asks for another |

A board states no size that follows from its canvas. The tile area, the cells, the page keys, the strip that
opens the settings, the crosses of the touch test and the alert card are all measured at boot from the canvas
LVGL hands the screen, which is why one firmware serves a board either way round.

`tools/propose_grid.py` proposes the grid from the resolution and the diagonal: as many cells as hold a
standard tile of about 33 × 16 mm, never smaller than 30 × 12 mm. `tools/new_board.py` writes a board file
for a new panel from the nearest real board; its sizes come from the look (docs/ADDING_A_BOARD.md).

## The cards are cells of an LVGL grid

`packages/core.yaml` gives the tile area (`tile_scroll`) an LVGL grid layout; `runtime_tiles::grid_bind` fills in
the board's columns and rows as free units (`lv_obj_set_grid_dsc_array`), so LVGL divides the area over the cells
and keeps the gaps (`pad_row`, `pad_column`) and the side margin (the container's padding). `place_page` says only
which cell a card takes and how many it spans: `lv_obj_set_grid_cell(tile, STRETCH, column, columns, STRETCH, row, rows)`,
a wide card two columns, the 0.3.1 taller cards two rows, and a full card the whole page. No coordinate is computed in C++ any more, and the cards grow
by themselves when the page bar goes (the container then reaches the bottom edge, keeping the side margin).

The cards themselves are LVGL widgets, so they live in YAML, and ESPHome has no loop: `tools/generate_cells.py`
writes one file per number of cells (`packages/cells/6.yaml` for a 2 x 3 board) with the cards and the line that
binds them, and a board includes the file for its own grid. A board therefore carries exactly the cards it can
show: a CYD six, a 4 x 4 board sixteen. `tools/check.sh` fails when a file is out of date.

## What the firmware does with it

- `ui::configure(dpi, look)` at boot (`components/smart_display/ui_scale.h`): one scale for every
  size the C++ decides itself, `ui::px(n)`, where `n` is in the reference look's pixels. On the CYD
  and the Guition the scale is exactly 100.
- `ui::large()`: the class of cards and pages is the look's, never a cell's momentary height. (A class
  that flipped when the rows grew reused a clock's numeral labels as tick lines: the lab's crash.)
- `GRID_COLS`/`GRID_ROWS` reach the C++ as build flags; `SLOTS_PER_PAGE` follows, `MAX_PAGES` is
  capped so a screen never holds more than 64 tiles (one dirty bit each: seven pages of nine, four of
  sixteen), and `runtime_tiles::widgets` holds exactly one entry per cell. The add-on (`core.Grid`) and
  the editor (`setGrid`) count with the same rule, so a page, a slot and a tile limit mean the same in
  all three.
- A card's head (the icon circle, the name and the state beside it) is one computed row on every board
  (`runtime_tiles::head_row`): centred on the cell the card really got, whether that is two rows or three on
  the same glass. The circle keeps `TILE_ICON_SIZE` while it leaves a few pixels to the card's border, standing a
  little into the padding for that, and shrinks only on a cell shorter than that; the two lines keep the look's
  spacing. A full-page card's head is one cell of the look (`ui::cell_height()`), never more than 30 % of the
  card, not one row of the board. A strip card (a slider or a graph under the head) keeps its two lines while
  the value's letters stay above the strip; when the strip would cover them, the name and the value share one
  line, the value at the right. The strip and the head are laid out for the look's cell (`ui::cell_height()`);
  a taller cell has surplus, and a graph, the card's picture rather than a control, takes all of it: on the
  10.1-inch Guition (162 px where the look wants 108) the name and the value keep the look's place at the top
  and the graph runs under them to the bottom of the card, instead of standing thin under a head centred in the
  air. A slider keeps its thumb-thick strip and its head stands in the room that is left. A big-value card (`display: watch`) keeps its icon and
  name above the number while the three fit; on a shorter cell the number stands big in the middle and the name
  small in the top-left corner. On a cell with room to spare the number takes the setpoint's digits, the largest
  face a board carries, when they fit under the name and beside the unit and the value has no letter that face
  lacks (a word keeps the value's own face); a 4-inch Guition has no such room and keeps its face. A cell at
  least twice the look's cell height stacks the icon above the name and state.
- **A control that fills its room is one cell wide** (`runtime_tiles::cell_content_width`). A double-width card
  is two cells of its row: its slider, its - / + pill and a player's volume with its mute key take the second
  one, so their edges stand where the cards in the rows above and below have theirs. A row of keys divides that
  same cell between three of them, never above the key size the look gives and never under `ui::touch_min()`;
  a switch and a run key keep their own size against the same edge. The look's numbers in `panel_metrics` are
  what one cell of a CYD and a 4-inch Guition measures, give or take two pixels - which is why writing them as
  a rule changes nothing there, and why a board whose grid divides its glass differently needs it: on the
  Waveshare's three columns that number was a slider of 251 px on a card of 478, leaving the name 28 % of the
  card where a Guition leaves it 36 %.
- What does not fit is left out: the forecast shows as many day columns as the width holds (five at
  most, none below two), a single clock card drops its date when it has no room beside the dial, a
  wide card gets a control panel only when the panel, the icon and some name fit.
- The weather tile (`forecast_tile.h`, firmware 0.3.3) takes one of three forms. A card of one row puts the
  weather now at the left and a column per day beside it; a taller card puts the weather now on top and a row
  per day under it, the day's range drawn as a bar on one scale for the week; a tall card with no room for four
  rows keeps the columns under the weather now. A short column gives up its chance of rain first, then the day
  name on a line of its own. Today's column stands on a pill that keeps its padding: every column is as wide as
  the pill around the widest text, so a card shows one day fewer rather than a pill that touches its digits.
- A thermostat tile of more than one row (`climate_tile.h`) has two groups: the number between - and +, and a
  bar with one segment per mode. Off is not on the bar; the tile's circle switches the thermostat on and off.
  With room the number stands large with the bar under it; otherwise the stepper and the bar share one row, or
  on a narrow card the bar goes under the stepper. The bar shows heat and cool first and always the mode the
  thermostat is in; what does not fit is behind "…".
- The icon circle's size is `TILE_ICON_SIZE`, the only size of the head a board states; the forecast's
  weather now uses that circle as every other card does.

## Overlays: one frame for every card

`components/smart_display/overlay_card.h` is the frame a card a tap opens gets, and it holds two rules on every
board:

- **The content is never wider than a hand spans** (`ui::control_max_width`, 110 mm of the reference look). A
  thermostat whose − and + sit at the far edges of a ten-inch panel takes two hands. On a CYD and a Guition the
  glass is narrower than the cap, so nothing changes there.
- **What is capped, is centred**: left to right by `overlay_card::frame`, top to bottom by
  `overlay_card::centre(root, pinned)`, which leaves the first `pinned` children (the back key and the name)
  where they are: the card's top bar stays at the top, the content under it sits in the middle. A page that
  places itself rather than hanging on `centre` keeps the same rule in its own arithmetic and the same
  condition, "only when more than a finger is left over": the effects page in `place()`, the colour card in
  `light_controls::open`. One behaviour, one rule, wherever it is written.

A card that is a *picture* or a *graph* asks for `overlay_card::picture` or `overlay_card::graph` and is not
capped: the media card's cover art, a camera's image and a day of a sensor are nicer the bigger they are, and
none of them is worked with a finger across its whole width. What such a card *does* work with a finger keeps a
hand's width all the same and stands in the middle of the card: `overlay_card::reach(card_width, room)` gives
back the x and the width for that row. So on a ten-inch panel the graph runs from edge to edge while the range
keys under it, the volume slider of a player and the words of a track stay within one hand.

A picture has a second ceiling that a drawing does not: what the add-on will hand over. A media player's cover is
cut, rounded and resized by the app to exactly the size the card asked for, and the screen draws what comes back one
to one, so a square larger than `camera_feed.COVER_SIZES[1]` stays empty - the app answers such a request with
nothing at all, and an add-on older than the firmware never grows its ceiling. `media_card::Metrics::cover_max()`
holds the same number and `tests/test_media_card.py` keeps the two equal; raising it is a change in both, the app
first.

A full-screen backdrop behind a card keeps the page covered, and it **takes every press**: LVGL looks on under
an overlay that takes none, so a tap in the room a narrow card leaves would reach the tiles and the page keys
behind it. The effects page and the colour card do the same on their own roots.

Anything a finger must hit keeps at least `ui::touch_min()` (7 mm of glass, from the board's density) as its
touch area, however thin it is drawn: `overlay_card::touchable(object, drawn_thickness)` grows the click area
instead of the drawing, so a blind's slider on a small panel stays usable.

## Designing a card or a page here

Every card is drawn on glass we have never seen: 2.8 to 10 inches, 143 to 294 dpi, landscape, portrait
and everything between. A design that was drawn for one panel and then patched for the next is how the
climate card ended up as six tables of pixels, and how a light's effects page pushed its sliders off a
800 x 480 screen. These are the rules that keep that from happening again. They are about **how to
think about a design**, not about which pixel goes where.

**Build a component, not a screen.** A card is two parts: a header of pure arithmetic that says where
everything goes (`media_card.h`, `climate_card.h`, `effects_page.h`'s `place()`), and a draw step in
`runtime_tiles.h` that hangs LVGL objects on those numbers. The arithmetic knows nothing about LVGL or
ESPHome, so `tests/test_*_card.cpp` can check every shape on a PC in a second. If you cannot test a
layout without a board, it is not a component yet.

**Ask the area, never the board.** The only things a layout may read are the width and height it was
given, the density and the look (`ui::`), and the content itself. There is no `if (board == guition)`,
no `if (width == 480)`, and no substitution in a board file that positions something the shared tree
draws. A board file says what the hardware is and how dense it is; everything else is derived.

**Sizes are physical.** `ui::px(n)` is a design size in the reference look's pixels, scaled to this
panel. `ui::mm(n)` is for anything the human body decides: `ui::touch_min()` (7 mm) for what a finger
must hit, `ui::column_gap()` between two columns, `ui::control_max_width()` (110 mm) for a row of
controls that must stay inside one hand's reach. A number that is neither a design size nor a physical
one is usually a mistake.

**More pixels is not more room.** A denser panel draws the same design larger, so what a card has to
work with is what is left after that scaling, not what the resolution suggests. The Waveshare's
800 x 480 is *shorter* than a Guition's 480 x 480: 55 mm of glass against 71, with every letter, key and
icon 28 % bigger. A stack drawn on the Guition and moved over therefore ran out of height on the
board that sounds bigger, and the weather card's coming days came out 51 px tall with five rows in
them (2026-09-21). Ask the area for its height, and try the *shortest* glass first, never the widest.

**Say what may give, and in what order.** A stack that must fit calls `ui::shrink({...}, over)` with
its blocks, each with the least it can be and how much of the stack one of its pixels is worth. The
*order is the design decision*, and every card makes its own: a robot gives up its portrait before its
keys, a thermostat its status word before its modes, the effects page its rows before its sliders.
And the concessions are **states, not a ratchet**: a card that has given up a whole block has room for
the small things again. So write the states down in the order you would like them, try them in turn and
take the first that holds everything, instead of giving one thing after another and never taking
anything back. The weather card's order is the rain under its hours, then its heading, then the hour
strip; on 800 x 480 the strip buys so much room that the heading comes back with it and every day keeps
a row (`weather_card::layout`). Write the order down in a comment with the reason. Nothing may ever be drawn past the glass: if the
cascade runs out, the last resort is scrolling or leaving content out, never overflow.

**Does a list not fit? Then it gets a pager, the way the settings page has one.** A stack of items that
is one too long is not a reason to squeeze the items: a row that falls under the height of its own
letters is unreadable on every board, and one drawn over the next is worse than one a tap away. So a
list of items that repeat — settings rows, the coming days, the effects of a light — shows as many as
fit at their honest minimum and puts the rest on a next page, with the same chevrons-and-dots pager as
the tile pages (`settings_screen::page_dots`, `settings_screen::fitting_rows`, `weather_card::layout`).
Reserve the pager's room only when there is really a second page, so a list that just fits keeps its
one page. And when a page turns, make only the rows again, not the card around them.

**Let the shape choose the form.** Screens differ more in *proportion* than in size. A card that is one
column on a square panel should stand in two on wide glass, because the height it lacks is width it
has: the cover card's sliders, the effects page's speed and intensity, the media card's art beside its
texts. Decide on the ratio of the area (`width * 2 >= height * 3`), never on a pixel count or a board
name, and keep one code path that both forms come out of.

**Prefer LVGL's own layout where it fits.** The tile grid is an LVGL grid (`lv_obj_set_grid_dsc_array`),
so LVGL divides the page and we only say which cell a card takes. Flex rows with `flex_grow` and
`min_width`/`max_width` in `ui::px()` do the same for a row inside a card. Computed coordinates are for
what LVGL cannot express, not for what is easier to write today. Watch the cost, though: a widget that
clips its children to a rounded corner makes LVGL allocate a layer of tens of kilobytes on every
redraw, which a board without PSRAM cannot pay. And asking LVGL where something ended up
(`lv_obj_update_layout`) lays out every object on the screen, so a card that can say where its parts go
by arithmetic should: compute it once, place the parts, and when something changes make only those
objects again - the day rows of a page, not the cards around them.

**Reuse the frame.** Anything a tap opens goes through `overlay_card`: the padding, the cap, the
centring, the two-column split and `touchable()` are there so that a new card inherits the rules
instead of restating them. A fix that belongs to all cards belongs in that file, once.

**Text is not a fixed width.** The firmware speaks nine languages, and a German or Polish label is
often half again as long as its English original ("Standby" against "Bereitschaftsmodus"). So: never
size a column to an English word, ask the font for the line height instead of assuming one
(`lv_font_get_line_height`), give every label a long mode (dots or scroll) and enough room that the
dots are rare, and prefer a layout that can take a longer word over one that looks perfect in English.
Check a card in English and in one long language before calling it done. The words themselves come
from `screen_text` (`docs/TRANSLATING.md`); state words, units and entity names come from Home
Assistant and are never composed in the firmware.

**Prove it before you flash it.** A new card ships with a test that walks every shape it can land on
(zero to six rows, one to three columns, 240 x 320 to 1024 x 600) and asserts that nothing leaves the
area and nothing a finger needs falls under `ui::touch_min()`. Then render it on every board, lying down and
standing up (`tools/render/run.py`, docs/ADDING_A_BOARD.md step 5), and look at it. A test says it fits; only the
render says it is worth looking at.

## What the screen tells the add-on

A screen reports two diagnostic sensors (firmware 0.2.80+): **Screen layout**, `800x480 3x3 217dpi standard`
(the canvas after rotation, the grid, the density, the look), and **Screen board**, the key of its board file.
The add-on (`core.shape_of`, `core.grid_of`) takes what the screen says first, then the board the screen's
profile YAML builds from (`screen_manager/app/boards.json`, written from the board files by
`tools/generate_board_shapes.py`), and the smallest screen there is when it knows nothing. Firmware from
before the sensors says nothing, and every screen that ran it is a two by three board. The editor draws the
mockup at that aspect with that grid and the top bar at that density, and places tiles on it; a save, a tile
event and the layout sensor count rows, columns and pages the same way.

## What is still open, and the way it becomes durable

- The sizes in `runtime_tiles.h` and the metric tables of the settings, effects, media and light cards go
  through `ui::px()` one by one. The durable form is LVGL's own: flex rows and columns with `flex_grow`,
  `min_width`/`max_width` in `ui::px()`, and `LV_EVENT_SIZE_CHANGED` for a card that changes shape with
  its width. The first component to rebuild that way is the tile row (circle | text column | panel); the
  forecast strip and the clock follow.
- The light and fan card was the first of these to go: since 0.2.94 it is `light_card.h` with the standing
  slider, and its eight sizes left every board file (with the five of the colour key it carried). The alert and
  the touch test still take their pixels from the board file and are the two left to compute.
- A card with two groups (the colour card: brightness and colour; climate: setpoint, modes, fan) could stand in
  two columns on wide glass instead of one capped column. Same components, another flex flow.
- Which way a screen hangs is chosen when it is built (firmware 0.2.92+). ESP Screens writes one substitution
  into the profile, `LVGL_ROTATION`, the way it writes the language: `ROTATION_LANDSCAPE` for a screen lying
  down and a quarter further for one standing up. Nothing else in the build differs, and the two grids the
  board states are both compiled in, so the screen picks one at boot from its canvas (`runtime_tiles::grid_select`).
- The calibration wizard of a resistive panel (the CYD; capacitive glass reports absolute coordinates and is
  never calibrated) works on the canvas the person is looking at, and measures rather than derives. Every tap
  gives it two numbers: the panel's raw reading, and the point the screen itself reported for that same touch
  through ESPHome's own turn. Five taps say what the whole chain does, so the wizard never has to work out what
  a rotation, a mirror or a swapped axis did, which is an arithmetic that was right lying down and upside down
  standing up. The correction it fits describes the panel, so one made standing up is within about ten pixels
  lying down, measured on the bench.
- Turning at runtime follows the shape (firmware 0.2.80+): a half turn keeps the canvas, the grid and the whole
  size table, so every board offers it; a quarter turn only a square screen (`settings_screen::quarter_turns`,
  set from `PANEL_W == PANEL_H` at boot). A quarter turn on other glass would be a different grid, and a layout
  made for six cells does not fit four, so that is a rebuild and not a setting. The shared tree applies the angle
  on top of the board's own `LVGL_ROTATION`, and each board's Rotation select offers the angles its glass allows.
- The lab boards (`packages/boards/lab-*.yaml`) are generated and disposable; a real board gets a hardware
  section checked on glass and an entry in `tools/profiles.py`.


### Optional cover slat controls

Taller and full-page cover tiles can explicitly select a slat group alongside
an optional primary control. The editor keeps those choices separate; resizing
never enables the extra group. Supported HA actions determine whether the group
contains a tilt-position slider or individual open, stop and close tilt keys.

`cover_tile.h` lays out the selected groups using measured body dimensions,
caption height and the active look's physical touch size. It changes a vertical
key stack to a row when that makes the groups fit. If space is insufficient,
only the primary controls remain on the tile, and the existing detail overlay
keeps the supported slat controls. No board identity or fixed glass resolution
participates in this decision.

The tile and overlay share `cover_slider`, `cover_tilt_keys`, and
`cover_position_action`. Position fills the closed part of the blind; slat tilt
uses the HA tilt percentage directly. The tile also uses the existing captured
slider lifecycle, so a lost press cannot send an action. Capability and pending
checks run again when an interaction commits.
