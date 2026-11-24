# Pages, top bars and navigation

App 0.3.1 stores each page as a complete unit: its tiles, top bar, navigation choice and stable identity. Moving a page keeps links pointing to that page. A page's number is its current position in the editor, not its identity.

## Editing

The toolbar above the pages switches between two views, **Row** and **Map**, and holds Undo, Redo, **Preview**, **Add page** and a **?** with a short how-to.

**Row** is the default: the pages side by side, as you swipe through them on the screen. Drag entities from the library onto the page grid, or select an empty cell and add an entity. Each page has a header with its number, its title, a **Home** label on the Home page and one **···** menu: **Page settings**, **Edit top bar**, **Set as Home**, **Duplicate page**, **New empty page with this top bar** and **Remove page**. Page settings hold the page title (the screen title, which every page without its own title shows, is one click under it), **Set as Home**, **Show in page dots and swipe navigation**, **Show a Home control on this page**, the page order and the page's top bar. Every page can have different top-bar items. Copying a bar creates independent items on the chosen pages.

The library lists everything a tile can show: the rows come as the list is scrolled (`libraryWindow` in `web/src/model/library.ts`), and a room's number is the whole room's. A search (`web/src/model/search.ts`) takes each word on its own, in any order, in the name, the entity id, the device, the room or what the entity is: its kind in the editor's language and its device class in Home Assistant's words (`kind_words` in `core.py`). Case, accents and whether words are joined by a space, a dash or an underscore make no difference, and a match in the name stands first.

### The library

The library shows what a tile can show in one of two views, switched at its top right and remembered in the browser:

- **Tiles** (the default): every entity as the tiles it can be on this screen, side by side on a strip of the screen's
  background: one cell, a row of two and two rows of two (the tall size where the grid has no 2 x 2), each size the
  screen or the type does not take left out. These are the mockup's own cards (`TileCard`) at the sizes the glass gives
  them, scaled alike so the sizes compare, and each is as rich as the screen draws it there: from two cells up the face
  its type is shown in (catalogue `showcase`, docs/CATALOGUE.md "The library's tiles"), and of the control sets that
  fit, the one with the most parts. A light shown with presets gets a first set that suits it (`starterPresets` in
  `web/src/model/light-presets.ts`). Only a tile the add-on saves is shown. A click puts that very tile on the marked
  cell or the first free one, a drag where it is let go. `web/src/editor/library-tiles.ts` chooses the tiles,
  `web/src/components/LibraryShelf.vue` draws one entity. A phone keeps the list.
  The cards scale with the drawer: a card of two rows fills the height the list has under a shelf's name and sizes, never
  larger than on the page and never under half of it, and the drawer opens at least that high. The strip they stand
  on takes the screen's own colours, the firmware's roles (`web/src/model/glass-colours.ts`), as the page mockup does.
  A plugin's tile stands on the shelf as the plugin's own code draws it, at each size, with the plugin's own example
  (docs/EMULATOR_ARCHITECTURE.md, "The page editor's own cards"); a plugin without a module for the preview keeps its
  placeholder face, as on a page.
- **List**: the entities as rows, as the library always was.

A device's extras stand apart, the way Home Assistant's device page puts them apart from the controls: a setting
(`entity_category: config`, such as a lamp's power-on behaviour), a reading for diagnosis (`diagnostic`) and an entity
hidden in Home Assistant. The add-on marks them (`category`, `hidden` in the inventory, `discover` in `core.py`), and the
library lists them after the rest of their room, folded under "N extras", in both views. A search finds them, after an
equally good match that is not an extra.

**Map** adds a spatial page map and links from navigation tiles to their destinations. Workspace positions belong to the editor, so arranging pages vertically does not change their order on the device. Reordering pages changes the device order while preserving destinations. Returning to Row removes the map connections and keeps the same pages and tiles.

The navigation preview runs locally. It does not switch entities in Home Assistant. Entity values and available history come from Home Assistant; unavailable history is left empty.

**Auto layout** in the toolbar makes a whole layout from the home's areas and devices, and a screen without tiles
offers it at once; it lands as one edit to undo or change (docs/AUTO_LAYOUT.md).

Explicitly adding a page opens a compact setup dialog for its title, Home control,
clock and optional Home Assistant entities. Cancelling leaves the document unchanged;
creating the page is one undo step. Dragging a tile onto a new page skips the dialog.
The new page gets a title from its shared HA area, or from its entity domain when
there is no shared area. Mixed content without a common area uses the screen title.
Suggestions are applied only at creation and never rename an existing page.

A tile is held by the cell you take it by: a large tile taken by its lower right corner lands with that
corner on the cell where you let it go, and one taken by its top left lands as before. It stays on the page under the
pointer, moved just inside it when part of it would fall off, instead of being refused (`anchorAt` in
`web/src/model/layout.ts`, `grabbedCell` in `web/src/drag.ts`).

Several tiles can be chosen at once: hold ⌘ (Ctrl on Windows and Linux) or Shift and click them, drag a band with the
mouse from beside the tiles, or press ⌘A for every tile of the chosen page. The inspector then lists them, with Copy and
Remove. ⌘C copies them with every setting and ⌘X cuts them. ⌘V pastes them on the chosen page, at the empty cell marked
on it if there is one, on the same screen or on another one; another browser tab of the editor can paste them too. The
group keeps its arrangement where it fits. Otherwise the tiles fill the free places of the page in reading order, and
what does not fit goes on new pages right after it, so tiles from a large screen spread over the pages of a smaller
one. A tile larger than the grid it lands on takes the largest size that grid offers for it; a full-page tile stays a
full page. A Go to page tile that leads to a page of another screen, an entity the screen takes only once that is
already there, and anything past the screen's tile limit or page limit are left out, and the message says how many
went on. Paste, cut and removing several tiles are each one undo step. The pasted tiles stay chosen, so they can be
moved or pasted again at once.

Contextual help uses Floating Vue through `HelpTip.vue`: a small help icon beside a label, only where the
words alone don't say it. Help icons work with keyboard focus, pointer hover and a tap; Escape or leaving the
help closes it. Errors, compatibility notices and unsaved-change status remain visible.

Menus, lists to pick from and switches use Reka UI (app 0.3.19), wrapped in `web/src/components/ui/` so every
panel uses the same few building blocks. Build a new control from Reka's rich parts, never from a hand-made list or
popup: `UiMenu` for a few fixed actions, `UiSelect` for one value from a short fixed list, and `UiPicker` (a Reka
Popover with a Combobox) for anything picked from the user's own Home Assistant, such as entities, players or areas.
`UiSegmented` (Reka's ToggleGroup, one at a time) switches between a few views or modes that all stay in sight, such
as the library's Tiles and List; the older hand-made `.seg` rows move to it as they are touched.
Such a list can run to dozens of items, so it needs a search field and a list that scrolls inside the window. When
Reka has a part for what you need (Combobox, Popover, Tooltip, Dialog, Tabs, Slider, ...), wrap it in
`web/src/components/ui/` first and use that wrapper. The inspector groups a tile's settings in five cards (Text, Look,
Size and place, Controls, Icon and color) and a page's in three (Title, Navigation, Top bar). The icons of the
editor's own controls are Material Design Icons, listed in `web/src/model/ui-icons.json`.

### The address

What is open is in the page's address, and nowhere else: the editor has one router (vue-router with a hash history,
`web/src/router.ts`, since the page lives in Home Assistant's ingress iframe where only the hash is the page's own).
`#/` is the overview, `#/screens/<inbox id>` a screen, `#/settings`, `#/new-screen`, `#/firmware`, `#/alerts` and
`#/plugins` the pages of the app, `#/settings/<part>` one part of Settings, `#/override/<profile>` a screen's Override
YAML, `?settings=<part>` on a screen's address one part of its Settings tab (see "Settings" below), and
`?chat=layoutbot` on a screen's address its open Layoutbot chat (docs/LAYOUTBOT.md, "Where the chat stands"). A reload opens the same again
once the inventory has arrived (the session follows the address, `followAddress`), the browser's Back and Forward
walk through what was open, a link to a screen can be kept, and the addresses from before the router (`#settings`)
still work. Home Assistant's sidebar shows the editor in a frame whose address nobody sees, and makes it anew on a
reload at the bare address: the route is mirrored into the hash of Home Assistant's own address
(`/app/<slug>#/screens/...`, which can be copied), kept in the tab as well (`sessionStorage`), and a frame that starts
at the overview goes back to what that hash or the tab says (`restoreKeptRoute`). Leaving a screen with unsaved changes by the address bar asks the same question as the sidebar does
(`router.beforeEach` in the session store), and a no leaves the page and the address where they were. Code never reads
or writes `location.hash`: a view is opened with `ui.go()` (the route names the pages know, `""` being the open screen
or the overview), a screen with `session.select()`, an override with `ui.openOverride()`; what is open is read from
`ui.route`, `scr.selected` and `ui.overrideProfile`.

### Pages of parts

A page that holds many things is a page of parts, the way Home Assistant's own Settings are: the app's Settings, a
screen's Settings tab and Events. Each opens on a list of its parts, one row per part with its icon, its name and one
line of what is set now, and a row opens its part as a page of its own, with the way back to the list above its title.
The look is Home Assistant's too: one column of 600 px in the middle of a wide page, the rows in a few separate cards,
each part's icon white on a round colour of its own (`PART_LOOK` in `settings-parts.ts`: every part's icon, colour and
card in one table; the `--tone-*` tokens in
`styles/tokens.css`). A part is in the address, so a link, a reload and Back reach it.

It is one design system, in `web/src/model/parts.ts` and `web/src/components/parts/`:

| Piece | What it is |
|---|---|
| `PartRow`, `cardsOf` (`model/parts.ts`) | a part as its list shows it (icon, colour, card, title, summary, badge), and the rows in their cards |
| `PartsPage.vue` | a whole page of parts: its title and intro over the list, or an open part with the way back; the key that leaves |
| `PartList.vue` | the cards of rows, with a slot for one control of a row's own |
| `PartLink.vue` | one row |
| `PartHead.vue` | the head of an open part: the way back and its title |

| Page | Parts | Address |
|---|---|---|
| Settings (`AppSettingsView.vue`, a `PartsPage`) | Updates, Builds, Language & region, Plugins, Home Assistant | `#/settings/<part>` |
| A screen's Settings tab (`SettingsTab.vue`, `PartList` and `PartHead` inside the screen's tabs) | Display, Standby & night, Navigation, This board, Help | `?settings=<part>` on the screen's address |
| Events (`EventsView.vue`, a `PartsPage`) | Alerts and Doorbell (fired by an automation), Alarm and Calls (followed by the screens) | `#/events/<part>` |

A part that has nothing on this app or this screen (Language on an add-on without languages, This board on a preview
screen) has no row, and its address opens the list. The rows of the screen's own settings are `SettingRows.vue`, which a
part shows by key, so the editor groups them by what a person looks for while the screen's own settings page keeps the
groups of `settings_screen.h`. A row may carry one control for what people change most there, so that needs no page:
dark mode, on the row of Display. A setting ⌘K finds opens its part and marks its row. Leaving the Settings tab takes the
part out of the address again, in place, so Back does not walk through it. Events says of each part what Home Assistant
has: its automations of Tessera, its alarm panels, the ring a call plays, read from the stores the parts read too
(`stores/automations.ts`, `stores/alarms.ts`, `stores/sounds.ts`), so a change in a part shows in the list at once.

A page that grows gets one more part, never a longer page; a new page that holds many things is a `PartsPage`. A new
card goes in the part it belongs to, and a new part needs a good reason: its name in the list, an icon of
`web/src/model/ui-icons.json` (`tools/generate_icons.py` puts a new one in the editor's font), its icon, colour and card
in `PART_LOOK`, a summary line made of what is set, and its texts in every language.

### Menus

Everything you do to a thing as a whole, as opposed to its settings, is in one menu, and that menu is the same in two
places: behind the thing's ··· and on the right mouse button on it (`UiContextMenu`). Its items live in one component,
so the two never differ: `TileMenuItems` for a tile, `PageMenuItems` for a page. A new action goes in that component
and shows in both places. The mockup holds one menu per page (`DevicePage`), which shows the items of what is under
the pointer, so a page of many tiles carries one menu, not one per card.

- The right mouse button chooses the thing first, as a file manager does: a tile that isn't chosen opens in the
  inspector, and a right click on one of several chosen tiles keeps them all and offers what works on all of them
  (copy, cut, remove).
- What a thing gets: a tile, the tiles chosen together, an empty cell (add a tile there, or paste there), the page
  anywhere else on it, the top bar's items in the bar at the head of its inspector, and the screensaver clock's row.
- The order is always the same: what changes the thing (rename, its entity, its data), then where it stands (move to
  a page), then the clipboard, and Remove last in red, with a line between the groups. A key that does the same
  shows on the right (`⌘C`, `⌫`).
- A menu holds actions, never settings: a choice with a value (size, colour, display) stays in the inspector, and a
  tile's size stays with the handles on its card.
- The right mouse button is the mouse's alone. A finger held on a tile or a bar item drags it, so on a touch screen
  the ··· is the way to the menu.

## Home and detail pages

Choose any page as Home. Home controls, automatic return and return on standby use that destination. Existing Home settings and entity identifiers stay compatible. The **Back to Home** setting (internally still named "Back to page 1") returns to the configured Home page, and so do the home button in the top bar (the Tessera logo) and a swipe up from the bottom edge; existing entity names and IDs are retained so automations keep working.

Every page initially participates in the bottom paginator and sequential swipes. Turn off **Show in page dots and swipe navigation** to opt a page out. Links and the existing numeric Show page action can still open it. Numeric actions follow the current editor order; links stored in the layout follow stable page IDs.

An excluded page is a detail page:

- With the bottom bar enabled, that strip shows **Back**. It reserves the same space on all pages, so navigating does not resize tiles.
- With the bottom bar hidden, a left chevron replaces the top-bar Home control at the same visible height, with the same touch target and title position. Back works even when the ordinary Home control is disabled.
- Back follows the route used to reach the page. Nested routes keep at most eight page IDs. Deleted destinations are skipped, and an entry without history falls back to Home.
- Home clears that route. Sequential swipes stay within included pages and do not turn a detail page into a shortcut through the paginator.

A single-page layout retains the existing absence of a bottom strip. Device grid dimensions and tile capacity remain authoritative. They cannot be overridden per page.

## Tile sizes

A tile has one of the named sizes in `catalogue/_tile.yaml`: `single` (one cell), `wide` (two cells side by side),
`tall` (two cells stacked), `square` (two by two) and `full` (the whole page). Any other rectangle smaller than the
grid is a span such as `3x2` (columns × rows, app 0.4.32, firmware 0.19.0+). A screen names the spans its grid takes in
its hello (`tile_sizes`), and the add-on never sends a size the screen did not name (`core.TILE_SIZES_ON_SCREEN`,
`core.span_offered`).

A hello from the add-on to a screen it has no tiles for yet carries `"empty": true` (app 0.4.74). The screen's starting
screen then stops waiting for Tessera and says how its tiles are chosen, in three steps (firmware 0.45.0). The first
layout's hello leaves the field out, and older firmware reads only the request.

A tall or square tile reserves two rows, including their normal gap. Tiles cannot overlap or extend beyond a page, and the screen's tile capacity does not change. If there is no free rectangle during resizing, the previous size and position stay intact.

Hover over a tile or focus its edge handle to resize it. The right handle changes width; the bottom handle changes height. Handles offer only supported sizes that fit at the current position without moving neighbours. Drag to preview, release to apply, or press Escape to cancel. Arrow keys work on a focused handle. Each completed resize is one undo step. A tile that grows gets the richest controls its new size has room for, and a tip beside it lists every set that fits, so you can keep that one, pick another or choose none (docs/CATALOGUE.md, "A tile that grows"). Full-page cards retain their existing inspector setting and do not have edge handles.

Most kinds reuse existing designs. A tall tile (1 × 2) keeps the single-column design, including its optional slider or graph. A square tile (2 × 2) keeps the double-width design and its direct controls. Some kinds use the height (app 0.3.8, firmware 0.3.3): a weather tile of two rows lists the days under each other with a low-to-high bar, and a thermostat shows its temperature between − and + with a mode bar under it. A **Live picture** fills its tile on every size (app 0.3.13, firmware 0.3.7). Extra height does not force a full-page design. Moving, copying, exporting and undoing keep the rectangular footprint with the tile.

Taller standard tiles extend the existing header. Media uses the selected playback or volume controls below track information. Selecting **Album cover** uses the artwork as a dimmed background on boards that support pictures, on every size: a card of one row has it behind its name and state too, its words light and its icon in a dark circle (older firmware put it in the icon's place). While nothing plays, a player whose library has covers shows them there, darkened: two along the shorter side of a taller card, one strip as high as the card on a card of one row (`rest_mosaic.py`). A thermostat of two rows shows its temperature between − and + and a bar with one segment per mode (the active one filled; an airco shows heat and cool first, the rest behind "…"). Off is not on the bar: a tap on the tile's circle turns the thermostat on or off (firmware 0.3.3). Light brightness and other sliders reuse the existing large controls. Unavailable entities keep their unavailable state and their detail action.

Controls remain an explicit choice in the tile inspector. Increasing height preserves a previously selected group and does not enable a default group on a previously unconfigured tile. There is one selected group per tile, and additional height alone does not combine playback with volume. Two choices are combined groups on purpose: climate's **Temperature − / + and mode keys** (on a tile of two rows or more) and a cover's position or buttons with **Slat tilt**. Single-row tiles and existing full-page designs keep their original renderer; only the album cover lies behind a single-row card too.

The layout measures the available content rectangle, active fonts and physical touch sizes. Optional text gives way before touch targets. A control group that cannot fit an unusually dense custom grid is left in the detail view instead of drawing overlapping buttons. Source artwork is cropped, dimmed and rounded by the add-on at exactly the tile's pixels, one picture per tile (docs/CAMERA.md, "A picture per tile"), and each picture is bounded by the size cap on its own; a missing or changed picture returns to the normal tile palette. The editor fetches prepared pixels through its relative Ingress API, never a Home Assistant token or source URL.

Update the screen before choosing a taller size. Its supported sizes are negotiated, separately from the page protocol. The add-on checks them before starting a replacement, so a saved rectangle cannot be silently reduced on an older screen. The storage version and migration path are unchanged.

Add-ons older than 0.3.1 cannot read version 2 storage at all, so going back needs the pre-upgrade backup (see Storage and recovery). There is no public 0.3.0 release: it was the internal page-owned development round, and its test results are linked below.

## Sections

A section is a block of cells on a page's grid, like one large tile, with a title, an icon and a soft panel behind its
tiles; its tiles stand inside it. A page's other tiles are loose: they stay on the page's own cells, gaps and all,
exactly as before sections, and never reflow. A section never holds another section. Only screens of the full tier
draw sections (docs/MODULES.md, module `sections`); the editor offers them nowhere else, so a CYD or another board
with 4 MB of flash gets none of it.

A section is for grouping: what the app proposes by itself (a first layout made for a screen) puts two or more cards
in each section and leaves a lone card loose. A user may still make a section of one card, or keep one; nothing warns
or refuses it.

**The look** (`components/smart_display/module_sections.h`): the panel covers exactly the section's cells, the
`SECTION` role, its corner the card's radius plus the padding. The title stands in the panel's top, in the tile name's
font and ink, its capitals as far from the panel's top as from its side; its icon from the small icon font stands
before it, centred on the capitals; the summary, one entity's state in the words of the top bar, stands at the title's
right end in the small grey font. A section can stand out (**Contrast background**, off unless chosen): its panel takes
the page's opposite, `SECTION_CONTRAST`, and its title, icon and summary `SECTION_CONTRAST_INK`; its tiles keep their
own cards. With **Tiles in contrast too** (beside it, off unless chosen) the whole section is a piece of the other look:
its panel, its words and its tiles' cards, dark on a dark panel by day and light in Dark mode. The firmware gives each
card its look and what lies behind it where the card is placed on its own page (`sections::place`), paints the card in
that look through `CardScope` (docs/THEME.md, "A card's look") and trades the shared paints on its objects for their
copies in the other look when it changes look (`theme::restyle_card`); the editor, whose mockup is the light look,
draws them close to the dark look's values (`OTHER_LOOK` in `web/src/model/sections.ts`). A picture on a card in a section (an album cover, a
camera, still or live) rounds its corners over the section's panel, the dark one in contrast, never over the page
(`runtime_tiles::card_ground`): a cover asked over the page left a light frame around its card on
a contrast panel. The editor draws the same from `boards.json`'s `section` metrics, so a page built in the editor is the page
on the glass.

**Room.** Adding a section changes no tile outside it: the page's rows stay what they are, and a loose tile keeps its
full height. The room the title takes (the header: the title's top, its line and a gap) and the padding under the last
row come out of the section's own tiles, shared evenly by its rows, so every tile inside is the same height and the
panel's top and foot stay on the rows beside it. A tile of rows `k1` to `k2` of a section of `n` rows gets the margins
`header - k1·d` above and `(k2 + 1)·d - header` below, `d = (header + gap) / n`, rounded half away from zero in whole
pixels, and the grid's gap at the section's sides (`section_layout.h inside`, `tests/test_section_layout.cpp`; the
editor's `insideMargins` in `web/src/model/sections.ts`, `web/tests/sections.spec.ts`, the same cases).

**Making and changing a section** (editor):

- Choose tiles (⌘ or Ctrl and a click, Shift and a click, or a frame drawn over the page) and click **Make a section**
  beside them, or in the drawer of the chosen tiles, or in their menu. A name field opens at once and the page shows
  the section while you type; Enter makes it, Escape leaves everything as it was. Tiles that fill a rectangle become
  that block where they stand; any other choice gets a block at its first tile, as wide as the choice, its tiles in
  reading order, and loose tiles in the way move aside as a drag moves them.
- Or start from nothing: **Add a section** stands at the top of the library (so a click on an empty cell offers a tile
  or a section in one place), in the right-click menu of an empty cell (**Add a section here**) and in the page's own
  menu. The new section is empty, two by two where that fits around the cell (else two by one, one by two or one cell;
  without a cell, on the page's first free cells), nothing moves, and its drawer opens with the name selected to type
  over. Its empty cells take tiles as any cell does (`emptySection` in `web/src/model/sections.ts`).
- A tile dragged onto a free cell of a section lands there; dragged onto one of its tiles, or onto a full section, it
  takes that place in the section's reading order, the tiles after it move on, and the section grows by rows, or wider
  where the page has no rows left, the loose tiles in the way making room. From the library, from the page and from
  another section alike. A tile dragged out of a section is loose again.
- A section is dragged by its title row, as one block; loose tiles in its way make room. The grips at its right and bottom
  edges make it wider, narrower, taller or lower; a section that gets too narrow for its tiles lays them out again in
  reading order. A click on the title row opens its drawer: name, icon, summary, contrast background, size, and Remove section (its tiles stay,
  loose, where they are) or Remove section and tiles. A click on the title names it in place.
- Hints, never blocks: loose tiles beside a section get the offer to make them a row of their own above the sections,
  and on a grid of three rows or fewer the drawer says how high the tiles of a section become.

**A grid change or a turn** (`adaptGrid`): a section takes part as one unit of its cells. It keeps its place where
the new grid has it free, else goes whole to the first free place of its page, else to a new page after it; only a
section wider than the new grid gets narrower, its tiles laid out again in reading order, and one taller than a page
then continues as a section of its own with the same title and icon.

**The document.** A page keeps every one of its tiles in `tiles`, each at its own cell, exactly as before sections, and
may have `sections`: each with its `id`, `title` (at most 48 bytes), optional `icon`, `summary` (an entity), `contrast`
(true) and `contrastTiles` (true, only beside `contrast`), and its `placement` on the page's grid. A section holds no
tiles of its own. A tile belongs to the section whose block it lies in, and that is said in one place per side:
`page_layout.section_of` in the add-on, `sectionOf` in `web/src/model/page-tiles.ts` in the editor. So nothing that
counts, finds or checks a page's tiles has to know sections, and a tile's section is never said twice. A tile stands
wholly in one block or wholly outside every block, never across an edge, and a tile that fills its page stands in none.
A page without sections has no key, so a layout from before sections is unchanged, and so is every message and
revision a screen gets for it (`tests/test_sections.py`). A tile's slot is its own cell, whatever section it is in.

Sections first kept their tiles inside themselves, placed from the block's corner (on dev from 2026-11-15, never
released). A store written that way is read once, kept beside itself as `screens.v3.backup.json`, and written in the
form above (`page_layout.flattened`, `layout_store`).

**The protocol.** A screen that draws sections says `sections` in its hello's features. Its pages' messages then carry
`"sections": [[column, row, columns, rows, icon, title, summary, options], ...]` (options as bits: 1 the contrast, 2 its tiles in it) for a
page that has some, and a summary that
changes comes as `{"op": "sums", "p": page, "t": [...]}`. A screen without the feature gets the same tiles in the same
cells, without the sections; the editor says the screen needs an update to show them. A screen that starts to draw
sections gets the layout again with them (the revision counts the feature only for a layout that has sections).

The screen takes a page's sections whole or refuses the page with "Error: sections": a list that is not one or has more
than sixteen, a section of fewer than six fields, a place that is not a number or leaves the grid, two sections over each
other, a section without a title. A `sums` update needs one text for each section of its page and changes nothing
otherwise. `tools/render/sections.py` sends each of these to the real firmware on the host as the add-on's Sender sends
them (its receiver round), with a layout from an app that knows no sections and back.

## Updating at different times

Update the add-on and screens in either order. Screens are negotiated individually.

| Add-on | Screen | Behaviour |
| --- | --- | --- |
| Older | Older | Existing behaviour |
| 0.3.1+ | Older | Compatible layouts keep working through the add-on's older wire format. The editor asks to update that screen before enabling independent bars, a different Home target or pagination exclusions. |
| Older | 0.3.1+ | The screen displays a configuration problem asking to update the add-on. New firmware carries no old layout decoder. |
| 0.3.1+ | 0.3.1+ | The latest saved layout is sent and activated automatically. No second Save or activation button is required. |

An unsaved editor draft remains a draft during an update. Updating one screen does not change the capabilities of another. A firmware downgrade cannot represent features its version never supported; the saved document is retained instead of being flattened.

The add-on checks the saved layout before installing new firmware. An external firmware update cannot perform that preflight. Missing grid information or invalid old references are shown as specific migration problems and must be resolved before that layout can activate.

## A hello

The app opens every session with a hello, and the screen answers with a new lease (`page_protocol::Transfer::grant`).
That happens each time the app starts: after an update, a restart or a rebuild. A hello alone costs the glass nothing.
The layout the screen holds stays whole and its values stay trusted, because nothing has said otherwise: while the app
was gone the screen already kept them for its keepalive, and between the hello and the session's begin no value can
land, because the old lease is refused and the new one is not yet begun. The begin then decides:

- **The same layout** (the same revision) is `Begin::unchanged`: nothing is drawn again and no value turns grey.
- **Another layout** is `Begin::replace`: the screen holds no whole layout until its last tile, the loading cover goes
  over the glass, and the new layout comes in whole, as any new layout does.

`begun` says only that the lease has had its one begin. What decides whether the screen shows a whole layout, and
trusts its values, is `Transfer::whole()`: the transfer is active and the model has every tile. `fresh()` (values and
actions) and `navigation_ready()` (turning pages) both ask it. Before firmware of 2026-11-16, `fresh()` also asked for
`begun`, so each start of the app greyed the values for a moment and drew every card twice. The host render's
`hello_again` round proves the rule with a second sender over the same screen.

On glass (2026-11-16): a Waveshare ESP32-P4 10.1 inch (chip revision 3.2) with one Home Assistant and one app, a
layout of three pages with a live camera tile on the glass, its whole log read over the API. The app was stopped and
started again twice, and each time the log was watched for a minute after the screen had its layout again. Neither time
did "the feed is no longer fresh" or "every card drawn" appear, while the log kept coming (69 lines in the second
minute, among them the camera tile's stream starting again about a quarter of a second after it was asked). Before the
change, the same restart on the same board logged "no longer fresh (... transfer active/not begun ...)" and every card
drawn twice.

## Storage and recovery

Layouts live in the add-on's `/data/screens.json`. Wi-Fi, API and OTA keys remain in the screen's ESPHome configuration. Layout exports contain no connection credentials.

On opening a version 1 store, the add-on creates a durable `screens.v1.backup.json` before replacing the store. Each convertible screen receives its stable IDs once. A screen whose source grid or data cannot be established safely keeps its original payload in a pending record. Other screens can still migrate and be edited. Pending records are retried when relevant screen/profile information changes, without requiring Save.

Normal saves write only version 2. State changes never rerun storage migration. Saves compare revisions and use a shared file lock, atomic replacement and durability checks. A stale editor receives a conflict instead of overwriting a newer edit. A failed send leaves a successful save intact for automatic retry.

Migration keeps valid tiles when individual tiles or old page settings are
invalid. The editor lists dropped tiles and settings replaced with defaults;
dismissing that note leaves the original backup intact. A readable pending
layout can still be sent to verified old firmware. For unreadable data,
**Start fresh for this screen** creates one empty page after confirmation,
retains the backup, and leaves other screens unchanged.

Top-bar value updates negotiate the `bar_values` capability. Identical rendered
values share one `bar_value` packet with explicit destinations, encoded as
`page index * 6 + item index`. The receiver validates all destinations before
changing any item. There are at most 48 destinations and no additional stored
firmware configuration. Different formatting remains independent; a change in
the number of visible items replaces that page's bar. Peers without the
capability continue receiving individual `bar` messages.

Cards from the top bar negotiate `bar_cards` (firmware 0.56.0). An entity's item in a top bar opens the card that
holding its tile opens, and nothing else: a switch there opens its card instead of switching. A tile and an item reach
that card the same way (`runtime_tiles::hold_card`). The item names the tile (`d`, its index). An entity that is on no
tile gets a tile of the top bar: a tile without a cell, sent after every other tile with `bar` instead of a slot, drawn
on no page, kept up to date like any tile. The add-on sends these tiles only to a screen whose hello names
`bar_cards`, and only as many as the screen's tile ceiling leaves room for. Past that, an item keeps its value and
opens nothing. They count in the memory budget like any tile (docs/TILE_MEMORY.md). The saved layout does not change,
so a screen without the capability gets the layout as before.

Title, label and background-only saves negotiate `appearance_updates`. The
add-on compares the remaining configuration before choosing one atomic
`appearance` packet, bound to the current revision. The receiver checks every
index and value before updating the existing records. Open cards, page history
and tile storage remain in place. Structural changes, older peers and edits
that exceed one bounded packet use the full transaction. No second layout or
compatibility decoder is stored on the screen.

The store stays at version 2 while no screen has a section, so an older app reads it as before. The first save with
a section keeps the version 2 file as `screens.v2.backup.json` beside the store (never overwritten, as the version 1
backup) and writes version 3, which an older app refuses without rewriting it: going back needs that backup.

Keep the pre-upgrade backup if an older add-on must be restored. Older add-ons cannot read version 2. Stop the add-on before restoring a backup; restoring it deliberately discards changes made after that backup. Unknown future storage versions are refused without rewriting them.

## Code boundaries and later features

| Responsibility | Source |
| --- | --- |
| Validated page document, stable references and compiled card inputs | `screen_manager/app/page_layout.py` |
| Historical storage/export conversion only | `screen_manager/app/layout_migrations.py` |
| Durable storage, backups, revisions and editor workspace | `screen_manager/app/layout_store.py` |
| Acknowledged device delivery and stale-response protection | `screen_manager/app/page_delivery.py` |
| Page save policy and capability checks | `screen_manager/app/page_service.py` |
| Editor history, workspace persistence and conflict recovery | `web/src/model/draft-history.ts`, `page-workspace.ts`, `page-conflict.ts` |
| Editor page operations and preview navigation | `web/src/model/pages.ts` |
| Firmware page metadata, navigation history and transfer guards | `components/smart_display/page_protocol.h` |
| Firmware transaction and appearance receiver | `components/smart_display/page_receiver.h` |
| Header widgets with explicit view data and a guarded action callback | `components/smart_display/page_header.h` |

The firmware keeps one active configuration. A structural replacement checks its required record reservations before releasing old storage; equal-size replacements reuse it. A failed reservation leaves the old model usable. A replacement becomes usable only when complete. Acknowledged sessions and revisions reject stale values and delayed responses. Pages and tiles share the existing PSRAM-first allocator; boards without PSRAM use their internal heap. The small Back history holds IDs only.

Editor placement helpers use a document-owned `createLayout` instance. They read the current document grid synchronously, without a shared mutable grid or watcher. The slot view remains a rendering and drag adapter; an arrangement must include every existing tile ID.

Tile placement has row, column, row span and column span, separated from content, appearance and interaction. A new size extends the negotiated `tile_sizes` capability without replacing the page model. A full-page card still means the whole current grid, even when its dimensions match another presentation.

Three rules hold for every message between the add-on and a screen:

- **4096 bytes at most.** `core.encode` refuses a larger message and `page_receiver.cpp` answers "message too large".
  A new message or extra that can grow caps its own size or sends pages, as the light group's lamps and the effects
  page's options do.
- **A screen asks with an event, never an action.** Requests (`esphome.screen_options`, the history request and the
  others) are fired as `esphome.` events (`is_event = true` in `runtime_tiles.h`). Home Assistant's ESPHome
  integration fires such events without the "perform Home Assistant actions" permission, so a request works on a
  screen that may not run actions.
- **The add-on answers about the screen's own layout only.** A request for history, options, a camera or a live
  picture is answered only for an entity on that screen's layout (or a camera in one of its recent alerts) and only
  for a screen that is online (`server.py`, `answer_options` and its neighbours), so a screen can never read an
  arbitrary Home Assistant entity. A new kind of request makes the same check.

Historical readers and the older wire adapter are separate add-on concerns. They can be retired independently after documenting a minimum supported source version and an intermediate upgrade or offline conversion route. Removing them never requires keeping migration machinery in firmware or changing current documents.
