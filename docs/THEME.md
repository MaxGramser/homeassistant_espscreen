# Colours and Dark mode

Every colour the screens choose themselves lives in one file, `components/smart_display/theme.h`
(firmware 0.2.54+). Dark mode is a second value for each of them, not a second design: the
layout, the fonts and the sizes stay exactly as they are. This page says how the colours reach
the glass and what a new colour takes.

## The model

| Part | What it is | Where |
|---|---|---|
| Role | What a colour is for (`PAGE`, `CARD`, `INK`, `MUTED`, `KEY_PRESSED`, ...), with a light and a dark value | `theme::ROLES`, the table at the top of `theme.h` |
| Swatch | A named card colour a tile or an alert can pick (`red` ... `gray`), light and dark | `theme::SWATCHES` |
| State colour | Home Assistant's colour for a state (the amber of a light that is on), the same in both looks | `theme::ha` |
| Paint | A shared LVGL style filled from roles: `card` is a card's background, hairline and text | `theme::Paint`, `theme::PAINTS` |
| Look | `theme::dark`, set by `theme::set_dark()` from the Dark mode setting | `settings_screen::dark_mode` |

The light values are the design as it has always been; `tests/test_theme.cpp` pins the main ones.
The dark values follow a few rules: a black page, graphite cards (`#1A1A1A`) with a hairline,
soft white text (`#DADADA`) and greys for secondary words, Home Assistant's state colours
unchanged, their tints a little stronger over graphite, and a grey whose red, green and blue land
on the same step of the RGB565 panel, so it stays grey on both boards.

## How a colour reaches the glass

- **Board profiles** write no colour. A widget names a paint, `styles: paint_card`, or a style that
  carries one (`style_page`, `style_tile`, `style_room`, ...). The style definitions have no colour;
  `on_boot` sets `theme::paints` to the list of `theme::fill(id(style), Paint::...)` calls and runs it. The list is
  code in flash, not a table in RAM, and `theme::set_dark()` runs it again.
  Scripts that colour a widget by state ask for a role: `theme::color(selected ? theme::ACCENT_BRIGHT : theme::CARD)`.
- **Firmware** asks for roles: `theme::color(theme::INK)`, `theme::hex(theme::MUTED)`, the
  `detail_text(..., theme::SUBTLE)` and `detail_shape(..., theme::TRACK, ...)` overloads. A widget
  that lives as long as the screen and never changes colour by state takes a paint too:
  `lv_obj_add_style(obj, theme::style(theme::Paint::knob), LV_PART_KNOB)`.
- **State colours** pass through a helper on their way to the glass:
  `state()` (Home Assistant's greys become the dark greys), `foreground()` (a glyph, a line or words:
  deep colours are lifted in dark), `tint()` (the pale circle, a halo, a slider track), `icon()`
  (a tile's icon), `surface()` and `outline()` (a card's own colour and hairline), `key_on()` (keys
  inside a card of any colour), `pressed()` (a card under a finger) and `fill_opacity()` (the area
  under a graph).

## A change of look

`settings_screen::set("dark_mode", ...)` stores the setting in its own preference (`DRK1`), runs
`apply_screen_settings`, and that calls `theme::set_dark()`. A look the screen already has costs
nothing. A real change runs `theme::paints`, refills the firmware's own paints, tells LVGL once, and calls
`theme::redraw`, set in `on_boot`, which draws again what code painted by state:

- `runtime_tiles::restyle()`: every tile's palette, the top bar's icons, and an open card, in place;
- `runtime_tiles::colour_restyle()` (the colour card, drawn again), `settings_screen::restyle()`;
- an alert that is up (`theme::surface(id(alert_card_color))`), and the climate card and its mode
  picker when they are open.

Everything happens in the same pass, so no frame shows half of each look. At boot `set_dark()`
runs before the first frame.

A redraw has to give exactly what a first draw gives, whatever came before it. Two things that did
not were found by comparing a screen that switched with one that booted in that look: a position
worked out from coordinates LVGL had not laid out yet (they read 0 until its next pass: use the size
you set), and a palette pass that overwrote a colour the sun path had chosen itself.

`SECTION` is the soft panel behind a section's tiles (docs/PAGES.md "Sections"): light `#F4F4F4`, a shade between the
page and a card, and dark `#101010`, so the cards stand on it as they stand on the page. A section in contrast takes
`SECTION_CONTRAST` (light `#202020`, dark `#E0E0E0`) and its words `SECTION_CONTRAST_INK` (light `#F0F0F0`, dark
`#181818`); both dark values land on one step of an RGB565 panel, so they stay neutral.

## A card's look

A card may be painted in the other look than the screen's: a card in a section whose tiles follow its contrast
(docs/PAGES.md "Sections"). So the theme keeps two looks: `theme::screen_dark`, the screen's, which only `set_dark()`
changes, and `theme::dark`, the look every role and helper reads, which is the screen's except while a card is painted.

- A card holds its look and what lies behind it, relative to the screen's look (`Widgets::look_other`, `ground_role`,
  `ground_other` in `runtime_tiles.h`), set where the card is placed on its own page (`sections::place`). A change of
  Dark mode needs no card told: each card's look follows from the screen's.
- **`CardScope`** is the one door into a card's paint: for as long as it lasts, `theme::dark` is the card's look, and
  after it, what it was. Every path that paints into a card enters through it, so a card outside a section, and every
  card of a board without sections, is painted exactly as before.
- `ground_behind()` is what lies behind the card in that ground's own look (a picture's corners, a bare card), and
  `card_surface()` the card's own colour in the card's look, both answerable away from a paint.

## Adding a colour

1. **A role**: one line in `enum Role` and one row in `ROLES`, in the same order (the tests read
   both). The light value is the design; choose the dark value on a render, not in the table.
2. **In firmware code**: `theme::color(theme::YOUR_ROLE)`. Never `lv_color_hex(0x...)`.
3. **In the profiles**: the widget takes a paint. For a new combination add it to `enum class
   Paint` and `PAINTS`, a colourless `- id: paint_<name>` in the `style_definitions` of `packages/core.yaml`
   (or of the feature that uses it), and `theme::fill(id(paint_<name>), Paint::<name>);` in the core's `theme::paints`
   list (a feature's paint goes into a hook of its own, as `CAMERA_PAINT_FILL` and `CALIBRATION_PAINT_FILL` do).
4. **Something drawn once and kept that changes colour by state**: set it where the state is drawn,
   and make sure the redraw above reaches that code.
5. A local colour always wins over a paint: an object that takes a paint must not also get a local
   colour for the same property and part.

## Checks

- `tests/test_theme.cpp`: the light design, contrast of the text roles on every surface and swatch in
  both looks, neutral dark greys, and the helpers.
- `tests/test_theme.py`: no colour outside `theme.h` (the light's colour picker and the value card's
  colour wheel keep their hues), every paint defined, filled once and used, and the look applied at
  boot, after a change and in the redraw.
- Renders of the host build in both looks (`tools/render/run.py`, docs/TESTING.md): the light
  look pixel for pixel against the previous firmware, a screen that boots dark against one that
  switched, and every card opened in light and switched while open against the same card opened in dark.
