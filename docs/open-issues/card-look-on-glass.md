# A card's look: proven on the host, not yet seen on glass

## The symptom

Nothing is wrong that we know of. The card look (docs/THEME.md "A card's look") changed how every card of a section
whose tiles follow its contrast is painted, and all of it was proven on the host and in the firmware preview, none of
it on a real screen. Until someone has looked, this stays open.

## What we know

- 2026-11-15, on dev: 60e5dce1 (a card carries its look and ground), 37aa954e and b4329353 (what LVGL draws later in
  its card's look), d442c15d and 41b6817a (shared paints once per look), 4851f44e (the card's colour as a value),
  db6cbe99 and the commit after it (the checks).
- tools/render/sections.py on jc8012p4a1: every card the harness feeds in a following and a contrast section, light and
  dark, identical to before where nothing was meant to change; the knob of a switch or slider in a following section on
  a light screen is now the dark look's knob (light grey) instead of a near-black one, by design.
- A kept page with a following section comes back without a single style trade and with the same pixels
  (KEPT_PAGES_HOST=1). A plugin tile in a following section wears its colour in the other look, also when the plugin
  paints it from its own moment (on_interval). The CYD's image did not grow.

## Ruled out

- A cost on a board without sections: the CYD's image and RAM sections were compared before and after each step.

## The deciding experiment: what to look at on glass

On a screen with sections (a 10-inch board), with a build of dev from db6cbe99 or later, each item in the light look
and then in Dark mode:

1. A section with "Tiles in contrast too": its cards are cards of the other look on its panel; no card half light and
   half dark; words and icons read well.
2. Press and hold a card there: the pressed colour belongs to that card, no light flash.
3. A switch or slider in such a section: its knob is light grey, as in Dark mode.
4. A meter, a blind with slats, a calendar or a to-do list in such a section: values and lines read, in the card's look.
5. A section in contrast whose tiles keep their look, with an album cover: no light frame around the cover's card.
6. Dark mode on and off on the screen: both kinds of section turn with it, no card left in the wrong look.
7. Turn to another page and back: the section comes back as it was, without flicker.
8. A plugin tile in such a section (an air quality or radar tile): its parts follow the card's look; a card with an
   instrument's face lightens when pressed, in the light look too.

When all eight look right, this file gets its "Solved" section with the build that was looked at.

### 2026-11-16: a first walk on glass

On a 10-inch Waveshare P4 board on USB, with a camera on the glass, a build of dev from the same day: a section in
contrast with its tiles following and one without, a drawn meter and a bar, Dark mode on and back off, page turns and
the pressed colour all looked right (items 1, 2, 4, 6 and 7, and item 5 without an album cover). Not yet looked at: the
knob of a switch or slider (3), a cover in a contrast section (5) and a plugin tile (8). The file stays open until those
are seen and the look is judged by eye on the screen it was made for.

### 2026-11-18: two boards, read back from the glass

A Guition 10.1 (P4) and a Guition 4-inch (S3) on a test Home Assistant with the app, dev at 75ff7db3: sections in
contrast with and without following tiles, album covers in a contrast section and in a following one (item 5), meters,
blinds and graph tiles, Dark mode on and off from Home Assistant, from the settings page and while asleep, page turns in
both looks (items 1, 4, 6, 7). Each time the frame buffer equalled LVGL's render (docs/open-issues/dark-mode-half-switched.md).
The 4-inch also ran a build with ESPHome 2026.11 (LVGL 9.6) through the same changes. Still not looked at by eye: the
knob of a switch or slider (3), the pressed colour on these boards (2) and a plugin tile (8).

## Pointers

docs/THEME.md "A card's look", docs/PAGES.md "Sections", `runtime_tiles.h` (`CardScope`, `card_surface`,
`card_ground`), `theme.h` (`LookScope`, `restyle_card`, `Face`), `module_sections.h` (`place`).
