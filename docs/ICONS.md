# Icons: the fixed set and a screen's own

Every screen carries a fixed set of Material Design icons, compiled into its firmware (`screen_manager/app/tile_icons.py`,
written into `packages/core.yaml` by `tools/generate_icons.py`). A screen with more than 4 MB of flash can take more,
chosen per screen in the editor: Screen settings, Icons, up to 500 icons in all.

## What it costs

An icon is a bitmap in the firmware, once for each font that carries it, so it costs more on a sharper screen. The fonts
are sized by the glass's density. One hundred extra icons, in the three fonts below, take about 95 KB on a Guition 4848S040
and more than 250 KB on a Tab5. A board with 4 MB of flash is close to its budget (docs/RELEASING.md, step 2), so it has no room for its own icons and shows a sentence instead of the list.

500 is a limit of its own choice, so the flash stays free for what comes next: it fits every board with 8 MB or more. The
fixed set counts towards it (`tile_icons.MOST_ICONS`, `tile_icons.room()`).

## How a chosen icon reaches the screen

Icons are in the firmware, so a change means a build. Three lists per screen (`screen_manager/app/screen_icons.py`, in
`screen_icons.json` in the app's data):

| List | What it says |
|---|---|
| `chosen` | What the person picked. Changes at once. |
| `written` | What the screen's plugins file says, so what its next build brings. |
| `built` | What went onto the screen. What a screen is sent follows this. |

The editor says which is which: a chosen icon that is not on the glass yet waits for a build, and the page has the one
button that does it. A screen shows a chosen icon that it does not have yet as its automatic icon, so nothing is ever
blank. Save, the tile and the layout do not depend on a build.

The icons travel in the screen's plugins file, `<name>.plugins.yaml` (docs/PLUGINS.md), the file this app already writes
and attaches. It gets a `font:` part that extends the three fonts carrying the whole fixed set:

```yaml
font:
  - id: !extend materialdesign_icons
    glyphs: &own_icons
      - "\U000F04CF" # star-circle
  - id: !extend materialdesign_icons_mini
    glyphs: *own_icons
  - id: !extend watch_icon
    glyphs: *own_icons
```

A screen without icons of its own has no such part and builds as it always did. The big font of a full-page card keeps
its short list: a card falls back to the regular icon size there, as it does for any chosen icon.

Three things to keep in mind when you change this:

- ESPHome stops at a glyph it finds twice in a font, so an icon of the fixed set must never be in the file. The list is
  taken against the set whenever it is written, and the file is written again right before every build
  (`ScreenIcons.before_build`), because a release can move an icon into the set.
- The three font ids in `screen_icons.FONTS` are part of a file that lives on people's machines. Don't rename them.
  `tests/test_screen_icons.py` checks they exist.
- A build that fails puts the file back to `built`, so a later update of that screen does not fail on the same list.

The build itself is a build of kind `icons` in the one line (docs/BUILDS.md). **Put on every screen** copies the list to
every screen with room and builds those that differ, as one round: a build that fails ends the ones that still wait, and
a screen that is off keeps its list chosen for later.

A screen built from its own YAML gets the file and the line to add, as for plugins, and that counts as on the screen.

## The editor

`web/src/stores/screenIcons.ts` asks the add-on for the open screen's lists. `web/src/components/ScreenIconsPanel.vue` is
the page (`#/screens/<id>/icons`). The picker of a tile lists the screen's own icons first, then the set, then what every
screen carries beyond the set's groups, on a screen with room for icons of its own.

The list of all icons is `screen_manager/app/mdi_icons.json`, written by `tools/generate_icons.py`, and the page's font is
`web/src/assets/mdi-all.woff`, a fallback behind the set's own font that a browser downloads only for an icon the set lacks.

The firmware preview in the editor uses the fonts it was built with, so it shows a screen's own icon as the automatic
icon, also after the build. The icon picker and the screen itself are right. Alerts that Home Assistant sends keep to the
fixed set, because the firmware looks those up in a table of its own (`tile_icon_names.h`).
