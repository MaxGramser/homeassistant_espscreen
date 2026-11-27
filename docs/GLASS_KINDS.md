# Kinds of glass

A screen's glass is one of two kinds. A glass that is lit shows colours and draws sixty frames a second. A glass of
ink (e-paper) prints with a few inks, and every change is a print that takes a part of a second. The firmware is one
set of pages, cards and controls for both. This document says where the two part, and how to keep it that way.
docs/PAPER.md is the story of the paper glass itself: its inks, its printer, its still forms.

The rule in one line: **a card says what a thing is, and never asks which glass it is on.**

## The layers

```
  what a board states      a display of the platform paper_glass with its inks (features/paper.yaml), or none
            │
            ▼
  glass_kind.h             the one fact (the inks) and what follows from it, each under its own name:
                           ink, still, keeps, lit
            │
   ┌────────┼─────────────────┬───────────────────────────┐
   ▼        ▼                 ▼                           ▼
  theme    screen_motion.h   the binder (core.yaml)      hw.cpp
  (ink)    (still)           (keeps, lit)                (inks, in the hello to the app)

  theme.h          the tones: a role as a colour (lit) or as an ink
  theme_parts.h    the parts a card is made of, and the one fork
     ├ theme_lit.h    every part on a glass that is lit
     └ theme_ink.h    every part on a glass of ink

  the cards, the pages, the settings, plugins: ask for a part, a tone or a consequence
  LVGL
  the display: an LCD's driver, or the paper glass (components/paper_glass: ink step and printer)
```

Each box is one file with one job, and each has a test.

| File | What it is | Its test |
|---|---|---|
| `glass_kind.h` | The kind of glass: one fact and its consequences, and the moments the screen tells its glass | `tests/test_glass_kind.cpp` |
| `theme.h` | The tones: every role as a colour in the light and the dark look, and as one of four inks | `tests/test_theme.cpp` |
| `theme_parts.h` | The parts: one name and one meaning each, and the fork between the two stylesheets | `tests/test_theme_parts.cpp` |
| `theme_lit.h` | Every part on a glass that is lit | `tests/test_theme_parts.cpp` |
| `theme_ink.h` | Every part on a glass of ink | `tests/test_theme_parts.cpp` |
| `screen_motion.h` | What moves, and what stands on a still glass | `tests/test_sheet_motion.cpp`, `tests/test_still_glass.cpp` |
| `still_glass_lvgl.h` | The form LVGL's own widgets take where nothing moves (docs/PAPER.md, "A still glass") | the host render |
| `components/paper_glass/` | The display of a glass of ink: every pixel to an ink, and when the panel prints | `tests/test_paper_ink.cpp`, `tests/test_paper_print.cpp` |

`tests/test_glass_kinds.py` holds the layer itself: nothing outside it asks which glass this is, and the two
stylesheets have the same parts. `tests/test_glass_lit.cpp` holds that a lit build carries no ink.

## The one fact

`glass_kind.h` reads the panel's inks from the paper glass, 0 where there is none, and names what follows:

| Answer | True on a glass of ink because | Who asks |
|---|---|---|
| `ink()` | it prints with inks: a role is a tone and a state is a shape | `theme.h` (`theme::inked()`) |
| `still()` | a change is a print, so nothing moves or runs by itself | `screen_motion.h`, `still_glass_lvgl.h` |
| `keeps()` | it keeps its picture without power or light, so its standby is rest | the binder, for `screen_standby.h` |
| `lit()` (false) | it has no light of its own: no brightness, no night level | the binder, for `settings_screen.h` |
| `inks()` | the number itself, for the app and the editor | `hw.cpp`, in the hello |

Today the four follow from the same number. They are four names because they are four reasons: a panel that keeps
its picture and is fast would be `keeps` and not `still`, and nothing but this file would change for it.

## Tones, then parts

**A tone** is what a role is on this glass. `theme::hex(theme::INK)` is graphite on a lit glass and ink on paper;
`theme::hex(theme::KEY)` is a pale grey there and paper here. `theme.h` holds both tables (docs/THEME.md,
docs/PAPER.md "The theme's ink table"). Most of a card needs nothing else.

**A part** is for what a tone cannot say, because the two glasses do not differ by a colour there but by a form. A
tile that is on is a pale disc with a coloured glyph on a lit glass, and a disc of ink with the glyph left open on
paper. A key that waits is paler there and whole here. So a card asks `theme_parts.h` for the part:

| A card wants | It asks | On a glass that is lit | On a glass of ink |
|---|---|---|---|
| a disc that says a state | `state_disc(colour, available, on)` | the colour pale, the glyph in the colour | on: ink with the glyph open; off: the glyph in a ring |
| a tile's own disc | `tile_disc(colour, available, key)` | the same | the same pair; unreachable: the glyph alone |
| the one chosen among its row | `chosen(colour)`, `hairline()` | Home Assistant's colour for it | ink; the others in a rim |
| a mark in a state's colour | `mark(colour)` | the colour | ink |
| the pale ground under a glyph | `field(colour, amount)` | a tint | the card |
| the pale share with nothing on it | `tint(colour, amount)` | a tint | the lighter tone |
| the glyph of what is off or away | `absent()` | grey | ink |
| words that stand back | `soft(words, ground, amount)` | a mix towards the ground | the words' own ink |
| a part that holds nothing to read | `gone(opa)` | faint | not there |
| a part that waits but is read | `whole(opa)` | dimmed | whole |
| a key that is a haze | `haze(words, opa)` | the words' colour at that strength | the tone under those words, in a ring |
| a dot of a pager | `pager_dot(current, rest, opa)` | ink, or a quiet grey | ink, or a ring |
| a view dark in both looks | `stage_ground(own)`, `stage_ink()` | black or a cover's colour, white words | the page, ink |
| a calendar's own colour | `calendar_key`, `calendar_block`, `calendar_ink` and their `_past` | Home Assistant's colour and its shares | ink marks, blocks of paper, words of ink |
| a clock face's tones | `clock(dark)`, `bauhaus(dark)` | the faces' own palettes | paper and ink, and two tones for Bauhaus's fields |

`theme_parts.h` has all of them, each with a line that says what it is. A part with a ground and something on it is a
`Dress` (ground, ink, strength, rim, line); `theme::wear(object, dress)` puts it on an LVGL object, and
`theme::rim(object, on)` and `theme::ground(object, role)` are its smaller relatives. They set a property only where
it differs: a set that changes nothing would still draw the object again, and on paper that is a print.

**The fork** is one macro. Every part in `theme_parts.h` is one line:

```cpp
inline uint32_t mark(uint32_t color) { return THEME_ON_GLASS(mark(color)); }
```

`THEME_ON_GLASS` is `inked() ? on_ink::part : on_lit::part`. Nothing else in the firmware chooses between the two.

## A build that is never ink

A board without a paper glass has no `components/paper_glass` in its build. `glass_kind.h` sees that
(`GLASS_MAY_BE_INK` is not defined) and every answer becomes a constant. Then `THEME_ON_GLASS` is the lit stylesheet
alone, `theme_ink.h` is not included, the still glass's pass is an empty call, and the compiler drops every branch
behind `still()` or `shades()`. A lit board pays nothing in flash for a kind of glass it does not have, which matters
on the boards with 4 MB. `tests/test_glass_lit.cpp` builds the theme that way and holds it with `static_assert`s.

Measured on the CYD's firmware with ESPHome 2026.9.0 (2026-11-28): 1 951 531 bytes before the firmware knew paper,
1 958 467 with paper asked in every card, and 1 952 999 with this layer. Of the 6 936 bytes paper had cost a board
that has none, 1 468 are left, most of it what every board gained in the same work (a settings page that knows
which of its pages it has, a card's name that takes the room beside two keys, the parts as functions of their own).

The tests on a PC, the editor's preview and the host render of a paper board read `paper.h`, so they can stand on
either glass and choose at run time.

ESPHome includes every header of a component by itself as well, in its own order. So `theme_parts.h`, `theme_lit.h`
and `theme_ink.h` are fenced by a word only their reader says: read alone each is empty, and the ink stylesheet
cannot come into a lit build by that door (a lit board's host build failed on exactly that, 2026-11-28).

## What moves

`screen_motion::still()` is the one question for anything that draws again by itself: a seconds hand, a spinner, a
text that rolls, a bar that runs. `screen_motion::start()` starts an animation the way this glass does it, which on
a still glass is its end, at once. LVGL's own widgets take their still form from one pass
(`still_glass_lvgl.h`): a slider is a level in steps, a part at part strength is whole. docs/PAPER.md, "A still
glass" and "A level", has the rules.

## What the screen tells its glass

The shared code says a few moments out loud without knowing who listens (`glass_moment` in `glass_kind.h`): a
finger down or up, a key, news (an alert, a ring at the door), rest, a layout on its way (`hold`), a change of the
whole look (`whole`). On a glass of ink the printer hears them and times its prints by them
(`components/paper_glass/paper_print.h`). On a lit glass each call is empty.

## What `shades()` is for

A few places do not need another colour on paper but leave something out, or put it elsewhere: a ring at half
strength round a number, a picture under a tile's words, a screensaver's words on the picture itself. They ask
`theme::shades()`, whether this glass shows a shade at all. It is not a way to ask which glass this is: a colour or
a ground comes from a part. `tests/test_glass_kinds.py` names every asker and what it leaves out, so a new one is a
decision someone made.

## The audit

The first rule of a glass of ink is that a glyph or a word stands on ink or on paper, never on a raster and never on
a picture. Every fault the first paper screen showed broke it: a faded key, a tint under an icon, words on a cover.

The host render holds it for every picture it takes of a board whose glass is ink
(`tools/render/ink_audit.py`, `Run.audit` in `tools/render/run.py`):

- The host program records what LVGL draws for the picture (`ink_audit.h`, in the host build alone): the box each
  text's ink lies in, each ground that covers what is under it, each picture, in drawing order.
- The paper glass's own ink step says where it printed a raster (`paper_ink::block`'s `rastered`,
  `tools/render/paper_ink_tool.cpp`).
- A text that shows is at fault when a raster lies in its box, or a picture lies under it with no ground between.

A fault fails the round and is listed in `ink-audit.txt` beside the pictures, with the text and its place. So a new
card that tints the ground under its icon fails the first time it is rendered on paper, without anyone looking.
`tests/test_ink_audit.py` runs the judge on pictures made by hand, one for each thing it tells apart.

## Rules for a card

- Ask for a role (`theme::color(theme::INK)`) or a part. Never write `if` on the kind of glass, and never set a
  colour, a strength or a border for one glass in a card's own code.
- A state that a lit glass shows by colour needs a form on paper. Use a part that has one (`state_disc`, `chosen`,
  `tile_disc`), or add one.
- Something at part strength is `gone()` or `whole()`: decide which, by whether it holds something to read.
- Anything that draws again by itself asks `screen_motion::still()`, and an animation starts through
  `screen_motion::start()`.
- Words never go on a picture or on a tint. Where a lit glass has them there, ask `shades()` and give them a ground.

## Adding a part

1. Say in `theme_parts.h` what the part is, in a line of words and one line of code through `THEME_ON_GLASS`.
2. Give it to `theme_lit.h` as the lit glass has it today, and to `theme_ink.h` by the rules at the head of that file.
3. Hold both in `tests/test_theme_parts.cpp`: the lit one against the colours it had, the ink one against the rule
   that what carries a glyph is ink or paper.
4. Use it in the card. `tests/test_glass_kinds.py` fails if a stylesheet lacks it.

## Adding a kind of glass

A panel with coloured inks, or one that keeps its picture and is fast, joins in these places and in no card:

1. `glass_kind.h`: what follows from it, under the names that are there, or a new name for a new reason.
2. `theme.h`: its tones, as a table beside the two that are there.
3. A third stylesheet beside `theme_lit.h` and `theme_ink.h`, and a third arm in `THEME_ON_GLASS`.
4. `components/paper_glass/paper_ink.h` for how a pixel becomes one of its inks, if it prints.

## Places a change touches

- A new part: `theme_parts.h`, `theme_lit.h`, `theme_ink.h`, `tests/test_theme_parts.cpp`, the table above.
- A new consequence of the kind of glass: `glass_kind.h`, `tests/test_glass_kind.cpp`, `tests/test_glass_lit.cpp`,
  `CONSEQUENCES` in `tests/test_glass_kinds.py`, the table above.
- A new asker of `shades()`: `SHADES` in `tests/test_glass_kinds.py`, with what it leaves out.
- A new moment: `glass_moment` in `glass_kind.h` (both halves), `components/paper_glass/paper.h`.
- A card that paints text itself: through `draw_text::label`, so the audit sees it.
