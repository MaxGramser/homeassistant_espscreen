# A glass of e-paper

A panel of e-paper is a glass that prints. It has a few inks instead of sixty thousand colours, it takes a part of a
second to several seconds to change, and it keeps its picture without a light and without power. The firmware treats
it as one more kind of panel: the pages, the tiles, the cards, the settings and the plugins are the same code as on a
lit glass, and what differs is written in the few places this page names. The first board with such a glass is the
Seeed reTerminal Sticky (docs/RETERMINAL_STICKY.md).

## Why a layer

LVGL draws as if every frame were free. On a lit glass that is true: a pressed card darkens for a moment, a slider
follows the finger, a spinner turns, and sixty frames a second hide every step on the way. On paper each of those is a
refresh the eye sees, the panel is busy for as long as it lasts, and a partial refresh leaves a faint trace of what
stood there. ESPHome's own e-paper driver also cuts every colour to the nearest ink, so a pale tint and a word at
40 % simply vanish.

So paper gets a layer of its own between LVGL and the driver, which turns colours into inks and decides when the panel
refreshes, and three small rules above it: the theme names tones instead of colours, LVGL's own widgets take a form
that needs no motion, and the standby is rest instead of dark. Nothing that makes a tile or a card asks which glass it
is on.

## The three seams

Paper uses seams the firmware already had (docs/ARCHITECTURE.md), and adds no fourth.

- **The glass, per panel kind.** `components/paper_glass/` is a display platform, `paper_glass`: the display LVGL draws
  on (`my_display`), wrapped around a display of ESPHome's `epaper_spi`, which stays ESPHome's own, untouched: its
  models, its partial refresh, its busy pin. A build whose display is that platform gets the software picture engine on
  any chip, no direct glass and no streams (`engine_build.py`, `picture_engine(..., paper=True)`;
  `tests/test_live_view.py`).
- **The capability record.** `hw::caps()` carries `inks` (0 on a glass that is lit and shows colours, 2 for black and
  white, 4 for four greys) and `still` (true on a glass of ink: a change is a print, so nothing on it runs by itself).
  A glass of ink has no `motion`, whatever else the build has. The hello to the app carries `inks`
  (`hw.cpp`; `tests/test_hw.cpp`).
- **Theme, motion and standby.** `theme.h` has an ink table beside its colour table. `screen_motion.h`, which does the
  plain thing on a glass without motion as it does on a CYD, also holds the other end of its rule: on a still glass
  nothing moves (`still()`, `start()`). And `screen_standby.h` knows a glass that keeps its picture.

```
  ┌──────────────────────────────────────────────────────────────┐
  │ the binder, the cards, the settings, plugins: as on any glass │
  │   theme.h: roles as tones of ink (set_paper)                  │
  │   still_glass_lvgl.h: a slider is a level, nothing runs       │
  ├──────────────────────────────────────────────────────────────┤
  │ LVGL: draws while the panel is free, turns picture and touch  │
  │                          │  a flush of RGB565                 │
  │                          ▼                                    │
  │ paper glass (components/paper_glass, the display my_display)  │
  │   paper_ink.h: every pixel to an ink, by its place            │
  │   paper_print.h: when the panel refreshes, a part or whole    │
  │                          │  pixels that are inks, update()    │
  │                          ▼                                    │
  │ ESPHome's epaper_spi (the display paper_panel): the model,    │
  │   the partial refresh, the busy pin                           │
  │                          │  SPI                               │
  │                          ▼                                    │
  │ the panel                                                     │
  └──────────────────────────────────────────────────────────────┘
```

To LVGL the paper glass is an ordinary display that is busy while its panel refreshes: ESPHome's
`update_when_display_idle` holds LVGL's drawing for exactly that long and calls the glass after every round of
drawing. To the driver the paper glass is the only one that draws on it and the only one that updates it. The panel is
never turned: LVGL turns what it draws and what a finger touches together, as on every other board, so there is one
way of turning for every glass.

The firmware around the glass reaches it through `paper.h` (this screen's inks and its one printer) and never through
the component. `components/smart_display/paper_screen.h` includes that file when the build has a paper glass and
gives the same calls as empty ones when it has not, so the binder, the standby and `packages/core.yaml` say that a
finger lifted or a key was pressed without asking which glass they are on.

## Ink

`paper_ink.h` is what a pixel LVGL drew becomes on the panel. It is free of LVGL and ESPHome, the paper glass runs it
at every flush, and `tests/test_paper_ink.cpp` walks it.

- **An ink stays an ink.** A colour near enough one of the panel's inks prints as that ink alone (`NEAR`: 20 of the
  255 steps between two inks). RGB565 and LVGL's mixing lose a few steps, and a page that is white but for one dot in
  sixteen reads as dirt.
- **An area between two inks is a raster.** A see-through layer, a tint, a picture: everything else between two inks
  prints as a fixed pattern of the two, so a grey is its share of dots and nothing the UI draws vanishes. Measured on
  a reTerminal Sticky (2026-11-27): greys of 25, 50 and 75 % and a word at 40 % read as rasters where the driver's own
  cut at half brightness left white, white, black and no word.
- **The raster is ordered and hangs on the pixel's place.** It is a 4 x 4 Bayer matrix read at the pixel's own x and y
  on the glass, never at what was drawn around it or before it. A part LVGL draws again prints the same dots it printed
  last time, so a partial refresh, which moves only the pixels that changed, has nothing to move in a raster that
  stayed. An error-diffusing dither spreads each pixel's rest over its neighbours: its dots would shift with every
  redraw and the area would shimmer at each partial refresh.
- **An edge is cut.** The soft pixels LVGL draws along a rounded corner, a slanted line or a letter are a step between
  the ink on one side and the ink on the other, not an area. Rastered they frayed into loose dots on the Sticky's
  glass (the corners of a card, 2026-11-27). So a pixel with one neighbour clearly darker and one clearly lighter (40
  steps or more, `EDGE`) prints as the nearer ink, and only a pixel in an even stretch of its own tone gets the
  raster. A word at 40 % over white is no edge: its pixels have white beside them and nothing darker.
- **The driver reads the same ink.** The lightness is Rec. 601 luma, the weights ESPHome's e-paper drivers cut on, and
  what the step writes is the middle of the band the driver reads as that ink: black and white for two inks, and for
  four the middles of ESPHome's four bands (under 32, 32 to 95, 96 to 159, 160 and up).

The paper glass makes the ink a band of sixteen rows at a time, so a flush of any shape reaches the driver in pieces
and the band costs a few tens of KB whatever the panel (25.6 KB on 800 x 480).

Every pixel LVGL draws passes through this step, a whole glass at a turn of a page, so it is written for speed: a row
is walked with one pointer, a luma that is an ink is read from a table (`PLAIN2`, `PLAIN4`) and only a pixel between
two inks looks around itself, and `paper_glass.cpp` is built for speed where the rest of a firmware is built for size.
The glass logs what a page's worth of pixels took, as ink and into the driver. On a reTerminal Sticky (384 000 pixels,
2026-11-27) the first version took 280 ms as ink and 100 ms into the driver's buffer of each turn; this one takes
93 ms as ink.

### Pictures

A camera's still, a cover and a map reach a paper screen the way they reach every screen without a picture engine, as
a picture of exactly the size they are drawn at. For a glass of ink the app makes that picture in the screen's inks
before it sends it (`picture_paint.inked`, `core.inks_of`; `tests/test_picture_paint.py`): its tones are spread from
black to white, and then every pixel becomes one of the inks, with what it lost handed on to its neighbours
(Floyd-Steinberg). A photo keeps its shades as grain that way. The screen's own raster is made for a tint under a
word and would lay its pattern over a face, and the app is where the whole picture is known. The screen prints an ink
as that ink, so what the app made is what stands on the glass, and whatever LVGL draws over a picture (a name on a
shade) still goes through the ink step.

### The theme's ink table

On paper a role of `theme.h` is no shade of grey or blue but one of four tones (`theme::Ink`): `PAPER`, `INK`, and two
between them, `SOFT` (the lighter) and `FIRM` (the darker), which a panel of two inks prints as a raster and one of
four as a grey. Dark mode trades paper and ink, as it trades white and graphite on a lit glass. `theme::set_paper()`
says once at boot, before the first paint, that the glass prints; from then on `theme::hex()` and every helper answer
in tones. A role takes the tone the table `INKS` names for it, and a role the table does not name takes the tone
nearest its colour, where near white is clean paper and near black is ink.

What the table says, and why:

- **Only ink is a line.** What sets a card or a key off from the page is a pale line on a lit glass; on paper it is
  ink (`LINE`, `RAISED_LINE`).
- **Words and glyphs are ink**, whatever grey ranks them on a lit glass: a raster through a letter breaks it.
- **The accent is ink, and what stands on it is paper**: a chosen segment, a toggle that is on, a key that acts.
- **What carries a glyph, a word or a knob is paper with a rim of ink**, never a raster. A glyph on a ground of raster
  fell away into it on the Sticky's glass (the - and + of a thermostat, a power key, 2026-11-27). Such a ground would
  be no shape on a page of paper, so it takes a line of ink around it, two pixels (`PAPER_RIM`). `theme::rimmed()`
  lists them: a key, a track, an empty toggle, a knob, the mark of a chosen row. `theme::ground()` sets a ground's
  colour and its rim together, `theme::rim()` puts the rim on or takes it off, and a paint whose ground is rimmed
  takes the rim with it unless it names a line of its own.
- **`SOFT` is for lines and arcs with nothing on them** (a grid, a spinner's ring, an empty history), the pale share
  of a state's colour and a calendar's blocks. **`FIRM` is for what is not there**: the glyph of something that is
  off, a tick.
- **Colour carries no state; a shape does.** A state's colour is ink for any state and the tone of what is not there
  for "off" (`theme::state`). A tile that is on is a disc of ink with its glyph left open in it; a tile that is off
  is its glyph in ink inside a ring (`theme::disc`, `theme::on_disc`, and the rim in `render_slot`). A round key that
  is on is a disc of ink too (`KEY_ON`, `KEY_ON_ICON`).
- **A card of a colour of its own is a card.** A pastel would be a raster under every word on it
  (`theme::surface`, `theme::outline`).
- **A press has no shade** (`theme::pressed`): nothing prints under a finger, and a shade drawn for nobody would only
  be a second refresh.

`tests/test_theme.cpp` holds each of these in both looks.

A panel of coloured inks would join in the same two places, with nothing above them changing. In `paper_ink.h` it is
a palette: the nearest ink first, then the same raster between the two nearest. In the theme it is more tones with a
name for what each is for (an accent, a warning), because the roles already say what a colour means and not what it
looks like.

## Printing

`paper_print.h` decides when the panel refreshes and whether it refreshes only what changed or all of itself. It
knows no LVGL, no driver and no clock of its own: the paper glass tells it what happened with the time it happened at
(a round of drawing and how much of the glass it changed, a finger, a refresh that ended) and does what it is told.
Every rule has its case in `tests/test_paper_print.cpp`.

What it was measured against: on a reTerminal Sticky (an SSD1677, 800 x 480) with ESPHome 2026.11.0 a whole refresh
takes 1.8 to 2.0 s and a partial one 0.70 s.

| Rule | Its number in `Rules` |
|---|---|
| A change waits a short quiet for more of them | `quiet_ms`, 350 ms |
| and never longer than a most from the first of them | `most_ms`, 1.5 s |
| What comes by itself prints no sooner than this after the last print ended | `stream_ms`, 5 s |
| What is drawn soon after a finger lifted or a key was pressed is its answer | `finger_ms`, within 1.2 s |
| An answer prints once the drawing has stood still | `finger_quiet_ms`, 80 ms |
| and never later than a most after the finger | `finger_most_ms`, 400 ms |
| A finger that stays down is shown where it is | `down_most_ms`, after 1.5 s |
| A hold lets go by itself | `hold_most_ms`, after 10 s |
| Past this the next print is whole, rest or no rest | `must_area`, thirty glasses |
| A panel without a partial refresh gathers longer | `poster()`: a quiet of 3 s, a most of 15 s |

- **A burst is one print.** Four values from Home Assistant within a second, a card's parts, a page's tiles: each
  restarts the quiet, and one refresh shows all of them. A stream that never leaves a quiet prints at the most.
- **A stream takes its turn.** What comes by itself and keeps coming, a meter's watts or a clock, prints no sooner
  than a few seconds after the last print ended: a value every second would be a refresh every second, on a glass
  that wears a little with each. A finger's answer does not wait for that turn, nor does news the screen was told
  to show (`paper::news`: an alert, a ring at the door, a call, a page Home Assistant asked for), nor a whole
  refresh that was asked for.
- **Nothing prints under a finger.** What LVGL draws while a finger lies on the glass is the look of a press, which is
  gone again when it lifts. A refresh takes longer than a tap, so printing it would show the press after the fact and
  make every tap two refreshes. A finger that stays (a hold, a drag) is shown after a most of its own.
- **A finger's answer does not wait for the quiet of a burst.** It prints as soon as the drawing has stood still for a
  few frames, so a short fade ends before its print and never is one. Home Assistant's confirmation a moment after the
  tap is still the finger's. A key's press counts as a finger that lifted.
- **Nothing prints while the panel refreshes.** What is drawn meanwhile waits and prints once the panel is free.
- **Something that is only whole at its end prints once.** While a hold is on (a layout on its way, a page being
  built) nothing prints; a hold that never ends lets go by itself.
- **The first print after a start is a whole one.** The panel still shows what it showed before the restart, which no
  partial refresh can take off cleanly.
- **Traces are tidied where it bothers nobody.** A partial refresh leaves a trace of what stood there, and a whole
  refresh takes the traces off. But a whole refresh flashes the whole panel black and white, which draws the eye from
  across a room: every few minutes, as the first rule had it on a page with a camera, was far too often for the owner
  of the first paper screen (2026-11-27), and so was a whole refresh on any clock. So the glass refreshes whole by
  itself at one moment only: as the screen comes to rest, its standby, when nobody has touched it for the whole
  standby time. Beyond that a whole refresh comes with something that changes the whole glass anyway (a start, a new
  layout, a change of look, the screensaver), and only when the count of traces runs far past enough does a print
  that changes the glass become the whole one.
- **A panel that cannot refresh a part** prints every time whole, after a longer quiet.

How the firmware tells it: the board's touch listener says when a finger lands and lifts and a page key says it was
pressed (`paper::finger`, `paper::key`, in `packages/core.yaml` and `features/page-keys.yaml`), and the paper glass
says after every round of LVGL's drawing how many per mille of the glass it changed. The standby says whether the
screen is at rest (`paper::rest`, once a second from `packages/core.yaml`). `paper::hold` is on while a
layout's pages are being built (`prepare_start` to `prepare_done` in `runtime_tiles.h`), so the first page is one
print, and `paper::whole_next` asks for a whole refresh where the whole glass changes or stays long: that first page,
a change of look (`restyle`), and the screensaver a glass shows while it rests.

## A still glass

A change on paper is a print that takes a part of a second. So nothing there can follow a finger, and nothing runs
by itself: no hand that steps each second, no bar that creeps, no ring that turns, no dot that travels. The capability
record says which glass that is (`hw::caps().still`), `screen_motion::still()` is the one place the firmware asks it,
and three files hold what follows from it.

### The pass: LVGL's own widgets

`still_glass_lvgl.h` is one pass over the objects on the glass (the page, the top layer and the system layer), before
each round of drawing. It gives every widget of a kind its still form wherever it was made: a tile, a card, the
settings, a plugin's card. A widget that is hidden is dressed when it shows.

- **A slider is a level** (next section). It stays the `lv_slider` it was, with its range, its value and every
  listener it had; only what it draws and what a finger's place means are replaced.
- **A spinner stands still.** An arc that turns would be a refresh every frame; the pass takes its animation off.
- **A label that would roll its words is cut with dots.**
- **A list that is let go stops where the finger left it.** Gliding on and springing back would be a row of prints,
  so the pass takes both off anything that scrolls.

`still_glass::watch()` starts the pass once at boot on a glass of ink (`packages/core.yaml`). On every other screen it
is an empty call: a lit glass keeps the slider it had, and a build without a paper glass does not carry the rest of
the file.

### What moves

An animation is started with `screen_motion::start()` in place of LVGL's own call. On a glass that is lit it is LVGL's
own. On a still glass it does not run:

- one that would run for ever (a heartbeat, a ring that turns) is left standing as it was made;
- one that would end stands at its end at once, with its last call made, so whatever the end hides or opens still
  happens;
- one that goes there and back rests where it began.

An animation that keeps time for something, such as a key held long enough, is not motion and is started with LVGL's
own call. Whatever else draws again by itself, once a frame or once a second, asks `screen_motion::still()` and leaves
it: a clock's second hand, the dots that travel on the energy card, the stripe of a cover on its way, a screensaver's
photo that moves and the drift of its clock face, the glow at the edge of a page, the bars of a doorbell's Talk, and
the fade of a card after a press, which is its own colour again at once.

### What counts time

`still_glass.h` holds the sums, free of LVGL, with `tests/test_still_glass.cpp`. What counts time counts it in steps a
print can keep up with, and says a time that is true at the moment it is printed.

- **A time that counts down** (`counted()`) shows whole minutes while more than one is left and steps of ten seconds
  inside the last. It is rounded up, so the glass never says less than there is, and it is exact at the moment it
  changes: "5:00" stands from 5:00 down to 4:01, "0:50" from fifty seconds to forty-one. A timer's tile and an alarm's
  delay are drawn when their step changes, not each second.
- **What a lit glass does each second, a still glass does each minute**: the bar of a track that plays, and the tick
  every plugin card gets.
- **A picture that is fetched again and again** (`picture_every()`), a camera's still, comes every ten seconds at most,
  where a lit glass takes one every few: each is a print of a part of the glass. A tile set to a slower pace in the
  editor keeps its own. A glass of ink streams nothing, so a camera tile set to Live shows stills at that pace.
- **What a page tells again and again**, the network and the links on the settings page's This screen, is told every
  thirty seconds, where a lit glass tells it every two.

### The rule for whoever makes a control

Make it as on any screen. Never check the board, the chip or `paper::is()` to draw something else. A widget of LVGL's
that needs a still form gets it in the pass, an animation goes through `screen_motion::start()`, something that draws
by itself asks `screen_motion::still()`, and a rule that needs no LVGL goes into a plain header beside it with a test,
as `level_bar.h` and `still_glass.h` do.

Because the glass answers a part of a second after a tap, a board may answer at once another way:
`features/buzzer.yaml` ticks a buzzer on a pin the moment a finger lands on something that takes it or a key is
pressed (`touch_feedback.h` says when), with a switch Tap sound in Home Assistant, on the screen's own settings page
and under Screen settings in the app (a board's own setting, docs/SETTINGS.md).

## A level

A refresh takes longer than a drag, so a knob that slides shows nothing while the finger moves and jumps when it
lifts. On a still glass a slider is a level: a row of blocks, filled up to the value, and where the control is thick
enough for a finger, a key at each end. It is what e-readers and watches do with a value on a slow glass: fixed
steps, set by a tap, a key at each side for one step. `level_bar.h` holds the rules, free of LVGL, with
`tests/test_level_bar.cpp`; `still_glass_lvgl.h` draws them and hears the finger.

- **The blocks of a range.** Ten, or one for each whole value of a range that spans twelve or fewer: a fan of four
  speeds is four blocks, not ten of which six mean nothing.
- **The real ends.** A slider's range often reaches a little past its real ends, so that its least fill is still a
  stub to hold (-40 to 1000, or a blind's past both ends). A level has no stub, so it counts between the real ends,
  nothing and a hundred or a thousand (`real_end()`), and its blocks are whole tenths: a tap on the fourth is 40 %.
- **Keys.** A control at least 5 mm thick, and long enough for two keys and its blocks, has a key at each end, as
  long as the control is thick: minus at the left and plus at the right of one lying down, minus at the bottom and
  plus at the top of one standing up. A thin one, the slider under a tile's name, is blocks alone. A range that counts
  down lies the other way round, as LVGL draws it.
- **What a tap picks.** A block picks its level. The first quarter of the first block, and anything before it, picks
  none, so a control without keys can still be set to nothing. A finger that drifted off an end still means that end.
- **A value and its blocks.** A value fills the nearest count of blocks, and never none for a value above the range's
  start: a lamp at 3 % is on and shows one block.
- **A key takes one step**, to the next whole block that way and never past an end. From between two blocks (Home
  Assistant says 71 %) up goes to 80 and down to 70, not past it to 60. The last block down is nothing. A key steps
  from the value the finger found, however long it is held.
- **What listeners hear.** The level's own values, never one between two blocks, and never the same one twice. A value
  the firmware sets, from Home Assistant, shows as it is.
- **No end at the glass's edge.** A slider on a lit glass takes a finger let go near the edge of the glass for its
  end, because a drag cannot reach it (`screen_input::edge_snap`). A level is not dragged and its end there is a
  key, so a still glass has no such band: with it, every tap on minus or plus was the lowest or the highest (seen on
  the Sticky, 2026-11-27).

Each tap is one refresh. The blocks and keys are drawn in the card's own look, ink on the card's ground with the
theme's rim, and the keys' minus and plus are bars, so they need no font.

## A colour by its name

A level is right for a value that is more or less of something. A light's colour and its white shade are not: on a lit
glass they are two spectrums with a knob, and a spectrum in ink is a grey band that says nothing. So on a still glass
the colour card's first two rows are keys with names, and the key of what the light has now stands filled
(`light_choices.h`, free of LVGL, with `tests/test_light_choices.cpp`; `light_controls.h` draws them). The brightness
under them stays a slider, which that glass draws as a level like every other.

- **The colours** are eight around the wheel: red, orange, yellow, green, cyan, blue, purple, pink. A key sends its
  hue at full saturation, and the hue a light has belongs to the name it is nearest to, around the wheel (350 degrees
  is red).
- **The white shades** are warm, neutral and cool, as lamps are sold (2700 K, 4000 K, 6000 K), each held to the light's
  own range. A light whose range holds fewer than three of them gets the ends and the middle of what it has. Until Home
  Assistant names the range the row waits, as its slider does.
- **How the keys stand.** As many beside each other as the row's width has room for at the widest name in the
  screen's language, and then as few rows as that takes, evenly filled. Each row of the card is as high as what it
  holds; what the glass lacks in height the keys give up, down to their words.
- **The names are screen texts** (`light.color_red` and on, `light.shade_warm` and on), in every language file.

A lamp of a group on the group's page still has the two sliders, drawn as levels: ten steps of a hue mean little
there, and that page is next.

## Standby is rest

A glass that keeps its picture without a light has no dark (`screen_standby.h`, `Glass::keeps`, bound to `paper::is()`
in `packages/core.yaml`). Its standby is rest:

- **With a screensaver set** it shows that one, the sheet over it takes the waking tap, and a finger or a key wakes
  the screen as on any screen: that first press does nothing more.
  A clock face there is paper with everything on it in ink, or the other way round in its dark look
  (`module_clock_faces.cpp`, `ink()`): a pale face would be a raster over the whole glass, and a white hand with a
  pale rim next to nothing. Its hands are solid with a rim of the face's tone, it has no seconds hand, and it does not
  drift. Bauhaus still draws its colours, which print as rasters.
- **Without one** the page stays where it is, readable, and nothing lies over it. A finger or a key on it is used at
  once and ends the rest by the way (`resting()`, `contact()`, `act()`): a first tap that only wakes a page nobody saw
  change would read as a tap that was not heard.

The saving of a screen at rest starts as on a dark screen (`at_rest()`, `screen_power.h`): Wi-Fi dozes between the
router's beacons. LVGL is not paused there, so the page at rest follows the house. There is no brightness, no night
level and no fade, and an alert does not blink. `tests/test_screen_standby.cpp` runs the rest with and without a
screensaver, by a finger and by a key.

The settings follow. A glass of ink has no light of its own (`settings_screen::lit`, false where `PAPER_INKS` is not
0), so its settings page has no row for a brightness or a night, in standby or out of it; Dark mode stays, as ink and
paper traded, and so do Standby and its time. The screen says so with the word `paper` in its Screen features, the
app reads that word or the board's `inks` in `boards.json` (`core.is_paper`), and Screen settings in the editor leaves
the same rows out (`PAPER_KEYS`; `tests/test_settings_screen.cpp`, `tests/test_screen_owned_settings.py`).

## What a board states

A board whose glass is e-paper includes `features/paper.yaml` in place of `features/backlight.yaml`, and its board
file names the panel:

```yaml
packages:
  paper: !include ../features/paper.yaml

display:
  - platform: epaper_spi
    id: paper_panel
    model: ...                 # ESPHome's model of the panel: its pins, its size, its init sequence
    full_update_every: 255     # the driver's partial refresh on; the paper glass asks for the whole ones
    update_interval: never
```

`features/paper.yaml` puts the paper glass on that panel as `my_display`, at the board's `PANEL_W` and `PANEL_H`, and
says once what follows from paper for every such board:

| Substitution | On paper | Why |
|---|---|---|
| `PAPER_INKS` | `"2"`; a board whose panel prints four greys states `"4"` | the inks the ink step and the capability record read |
| `LVGL_WAITS_FOR_GLASS` | `"true"` | LVGL draws only while the panel is not refreshing (`update_when_display_idle`) |
| `FONT_TEXT_BPP`, `FONT_ICON_BPP` | `1` | letters and icons built without soft edges: two inks cannot show them, they cost a quarter of the flash, and on the Sticky's glass they read sharper (2026-11-27) |
| `SET_BACKLIGHT`, `BOOT_BACKLIGHT`, `OTA_BACKLIGHT` | empty | the three places the shared tree sets a light: a level over a time, the light at boot, the light for an update. `features/backlight.yaml` fills them, a glass without a light leaves them empty |
| `BACKLIGHT_DIMMABLE` | `"false"` | there is no brightness to set |
| `ALERT_BLINKS` | `"0"` | an alert does not blink |

The board file itself adds what is the board's own: `LVGL_BUFFER_SIZE: "100%"` where it has the PSRAM, so a refresh of
the panel is one picture and never a row of strips; its touch panel's axes against the panel's own pixels
(`TOUCH_SWAP_XY` and the mirrors), measured with a tap in each corner, because the panel is never turned and LVGL turns
the picture and the touch together; and the ESPHome its panel needs as `esphome: min_version`. The Sticky states
2026.11.0, from which ESPHome drives its panel with a partial refresh that leaves the unchanged pixels alone. A board
file's `min_version` wins over the core's. `boards.json` carries the newest one of a board's files as `esphome`, and
New screen leaves out a board that asks for a newer ESPHome than the app runs (`firmware.offered`,
`tests/test_board_catalog.py`), so nobody starts a build that ends in ESPHome's refusal.

A board with keys the chip can read includes `features/page-keys.yaml` (the page before, the next, and home, which
held sends the screen to standby) and names the three pins; one with a buzzer on a pin includes `features/buzzer.yaml`
and names `BUZZER_PIN`. Neither is tied to paper, but both answer where the glass is slow.

The platform's own options are in `components/paper_glass/display.py`: `panel`, `dimensions`, `inks` (2 or 4) and
`partial` (false for a panel without a partial refresh, which then prints by the poster's rules).

## What is not built yet

- **A picture in ink is as large as a picture in colour.** The app sends it in the format the screen asks for, three
  bytes or one a pixel; a glass of two inks needs one bit.
- **The editor and the host render show such a board in colour.** `paper_ink.h` and the theme's ink table are free of
  LVGL and ESPHome so that the firmware preview and `tools/render` can run them over their own pixels; neither does
  yet.
- **A lamp of a group** (the group's page of a colour card) still has a hue and a white shade as sliders, which a
  still glass draws as levels of ten steps.
- **The entities of a light that is not there.** A paper screen still has Home Assistant's entities for a brightness
  and a night; only the screen's page and the app leave them out.
- **Sleep on a battery.** A screen at rest dozes its Wi-Fi and keeps its chip awake. The panel would keep its page
  through a deep sleep; nothing puts the chip there yet.
- **Four greys.** The ink step, the theme's two tones between and the platform's `inks: 4` are there; no board states
  four, and none has been tried on a panel.
- **Coloured inks.** The ink step prints greys. The printer has the rules of a panel without a partial refresh
  (`poster()`), and `features/paper.yaml` has no substitution for `partial` yet.
- **Redraws that still run by themselves.** A plugin's own interval runs as on any screen, four times a second
  (`plugin_host::tick`, `on_interval`): a plugin that draws there prints as often as the printer lets it. The plugin
  API has no call yet for whether the glass is a still one, and the hello carries `inks` and not `still`.

## Places a change touches

- `components/paper_glass/`: `display.py` (the platform), `paper_glass.h` and `paper_glass.cpp` (the display),
  `paper_ink.h`, `paper_print.h`, `paper.h`.
- `components/smart_display/`: `paper_screen.h` (the calls on every screen), `still_glass_lvgl.h` (the pass) with
  `level_bar.h`, `still_glass.h` (the sums) and `screen_motion.h` (`still()`, `start()`), `light_choices.h` and the
  still rows of `light_controls.h`, `settings_screen.h` (`lit`, the word `paper`), the ink table and its helpers
  in `theme.h`, `hw.h` and `hw.cpp` (`inks`, `still`, the hello), `engine_build.py` and `__init__.py` (the engine of a
  paper build), `screen_standby.h` (`keeps`, `resting`, `act`, `at_rest`).
- `packages/core.yaml`: `PAPER_INKS`, `LVGL_WAITS_FOR_GLASS`, `FONT_TEXT_BPP`, the three backlight hooks,
  `theme::set_paper`, `still_glass::watch`, the standby's `keeps`, the power saving's `freeze`, the touch listener's
  `paper::finger`.
- `packages/features/paper.yaml`, and `page-keys.yaml` and `buzzer.yaml` for a board that has them; the board file's
  `paper_panel`.
- `screen_manager/app/`: `boards.json` `inks` (from `PAPER_INKS`, `tools/generate_board_shapes.py`), `is_paper` and
  `PAPER_KEYS` in `core.py`, the settings view in `server.py`; the names of colours and shades in
  `screen_manager/translations/`.
- `tests/test_paper_ink.cpp`, `tests/test_paper_print.cpp`, `tests/test_level_bar.cpp`, `tests/test_still_glass.cpp`,
  `tests/test_light_choices.cpp`, and the paper cases in `tests/test_settings_screen.cpp`,
  `tests/test_screen_owned_settings.py`,
  `tests/test_theme.cpp`, `tests/test_hw.cpp`, `tests/test_screen_standby.cpp` and `tests/test_live_view.py`.
- This document, docs/ARCHITECTURE.md when a layer or a rule changes, docs/THEME.md for a role's tone, and the board's
  own document for what was seen on its glass. A measurement on real paper goes with the rule it decides.
