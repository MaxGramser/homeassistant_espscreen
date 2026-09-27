# Pages, top bars and navigation

ESP Screens 0.3.1 stores each page as a complete unit: its tiles, top bar, navigation choice and stable identity. Moving a page keeps links pointing to that page. A page's number is its current position in the editor, not its identity.

## Editing

The toolbar above the pages switches between two views, **Row** and **Map**, and holds Undo, Redo, **Preview**, **Add page** and a **?** with a short how-to.

**Row** is the default: the pages side by side, as you swipe through them on the screen. Drag entities from the library onto the page grid, or select an empty cell and add an entity. Each page has a header with its number, its title, a **Home** label on the Home page and one **···** menu: **Page settings**, **Edit top bar**, **Set as Home**, **Duplicate page**, **New empty page with this top bar** and **Remove page**. Page settings hold the page title (the screen title, which every page without its own title shows, is one click under it), **Set as Home**, **Show in page dots and swipe navigation**, **Show a Home control on this page**, the page order and the page's top bar. Every page can have different top-bar items. Copying a bar creates independent items on the chosen pages.

**Map** adds a spatial page map and links from navigation tiles to their destinations. Workspace positions belong to the editor, so arranging pages vertically does not change their order on the device. Reordering pages changes the device order while preserving destinations. Returning to Row removes the map connections and keeps the same pages and tiles.

The navigation preview runs locally. It does not switch entities in Home Assistant. Entity values and available history come from Home Assistant; unavailable history is left empty.

Explicitly adding a page opens a compact setup dialog for its title, Home control,
clock and optional Home Assistant entities. Cancelling leaves the document unchanged;
creating the page is one undo step. Dragging a tile onto a new page skips the dialog.
The new page gets a title from its shared HA area, or from its entity domain when
there is no shared area. Mixed content without a common area uses the screen title.
Suggestions are applied only at creation and never rename an existing page.

Contextual help uses Floating Vue through `HelpTip.vue`: a small help icon beside a label, only where the
words alone don't say it. Help icons work with keyboard focus, pointer hover and a tap; Escape or leaving the
help closes it. Errors, compatibility notices and unsaved-change status remain visible.

Menus, lists to pick from and switches use Reka UI (app 0.3.19), wrapped in `web/src/components/ui/` so every
panel uses the same few building blocks. The inspector groups a tile's settings in five cards (Text, Look,
Size and place, Controls, Icon and color) and a page's in three (Title, Navigation, Top bar). The icons of the
editor's own controls are Material Design Icons, listed in `web/src/model/ui-icons.json`.

## Home and detail pages

Choose any page as Home. Home controls, automatic return and return on standby use that destination. Existing Home settings and entity identifiers stay compatible. The **Back to Home** setting (internally still named "Back to page 1") returns to the configured Home page, and so do the house in the top bar and a swipe up from the bottom edge; existing entity names and IDs are retained so automations keep working.

Every page initially participates in the bottom paginator and sequential swipes. Turn off **Show in page dots and swipe navigation** to opt a page out. Links and the existing numeric Show page action can still open it. Numeric actions follow the current editor order; links stored in the layout follow stable page IDs.

An excluded page is a detail page:

- With the bottom bar enabled, that strip shows **Back**. It reserves the same space on all pages, so navigating does not resize tiles.
- With the bottom bar hidden, a left chevron replaces the top-bar Home control at the same visible height, with the same touch target and title position. Back works even when the ordinary Home control is disabled.
- Back follows the route used to reach the page. Nested routes keep at most eight page IDs. Deleted destinations are skipped, and an entry without history falls back to Home.
- Home clears that route. Sequential swipes stay within included pages and do not turn a detail page into a shortcut through the paginator.

A single-page layout retains the existing absence of a bottom strip. Device grid dimensions and tile capacity remain authoritative. They cannot be overridden per page.

## Taller tiles, 0.3.1

The tile inspector offers **1 × 2** and **2 × 2**, expressed as width × height in grid cells, when the connected firmware reports support.

Each size reserves two rows, including their normal gap. Tiles cannot overlap or extend beyond a page, and the screen's tile capacity does not change. If there is no free rectangle during resizing, the previous size and position stay intact.

Hover over a tile or focus its edge handle to resize it. The right handle changes width; the bottom handle changes height. Handles offer only supported sizes that fit at the current position without moving neighbours. Drag to preview, release to apply, or press Escape to cancel. Arrow keys work on a focused handle. Each completed resize is one undo step. Full-page cards retain their existing inspector setting and do not have edge handles.

Most kinds reuse existing designs. A 1 × 2 tile keeps the single-column design, including its optional slider or graph. A 2 × 2 tile keeps the double-width design and its direct controls. Some kinds use the height (app 0.3.8, firmware 0.3.3): a weather tile of two rows lists the days under each other with a low-to-high bar, and a thermostat shows its temperature between − and + with a mode bar under it. A **Live picture** fills its tile on every size (app 0.3.13, firmware 0.3.7). Extra height does not force a full-page design. Moving, copying, exporting and undoing keep the rectangular footprint with the tile.

Taller standard tiles extend the existing header. Media uses the selected playback or volume controls below track information. Selecting **Album cover** uses the artwork as a dimmed background on boards that support pictures; on a Normal tile the cover sits in the icon's place. A thermostat of two rows shows its temperature between − and + and a bar with one segment per mode (the active one filled; an airco shows heat and cool first, the rest behind "…"). Off is not on the bar: a tap on the tile's circle turns the thermostat on or off (firmware 0.3.3). Light brightness and other sliders reuse the existing large controls. Unavailable entities keep their unavailable state and their detail action.

Controls remain an explicit choice in the tile inspector. Increasing height preserves a previously selected group and does not enable a default group on a previously unconfigured tile. There is one selected group per tile, and additional height alone does not combine playback with volume. Two choices are combined groups on purpose: climate's **Temperature − / + and mode keys** (1 × 2, 2 × 2 and Full page only) and a cover's position or buttons with **Slat tilt**. All single-row tiles and existing full-page designs keep their original renderer.

The layout measures the available content rectangle, active fonts and physical touch sizes. Optional text gives way before touch targets. A control group that cannot fit an unusually dense custom grid is left in the detail view instead of drawing overlapping buttons. Source artwork is cropped, dimmed and rounded by the add-on, then decoded into the screen's existing shared image buffer. It does not allocate an additional image per tile. The atlas is bounded by the reported screen canvas; a missing or changed picture returns to the normal tile palette. The editor fetches prepared pixels through its relative Ingress API, never a Home Assistant token or source URL.

Update the screen before choosing a taller size. Its supported sizes are negotiated, separately from the page protocol. The add-on checks them before starting a replacement, so a saved rectangle cannot be silently reduced on an older screen. The storage version and migration path are unchanged.

Add-ons older than 0.3.1 cannot read version 2 storage at all, so going back needs the pre-upgrade backup (see Storage and recovery). There is no public 0.3.0 release: it was the internal page-owned development round, and its test results are linked below.

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

Title, label and background-only saves negotiate `appearance_updates`. The
add-on compares the remaining configuration before choosing one atomic
`appearance` packet, bound to the current revision. The receiver checks every
index and value before updating the existing records. Open cards, page history
and tile storage remain in place. Structural changes, older peers and edits
that exceed one bounded packet use the full transaction. No second layout or
compatibility decoder is stored on the screen.

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

Tile placement has row, column, row span and column span, separated from content, appearance and interaction. Version 0.3.1 adds 1×2 and 2×2 to the permitted sizes. A future 2×3 climate design can extend the negotiated rendering capability without replacing the page model. A full-page card still means the whole current grid, even when its dimensions match another presentation.

Historical readers and the older wire adapter are separate add-on concerns. They can be retired independently after documenting a minimum supported source version and an intermediate upgrade or offline conversion route. Removing them never requires keeping migration machinery in firmware or changing current documents.

See the [page-owned layout test results](TEST_RESULTS_030.md) (the internal 0.3.0 round) for upgrade checks, board builds, measured memory use and the limits of physical validation.
The [0.3.1 test results](TEST_RESULTS_031.md) cover taller tiles, their responsive controls and the tests on real screens.
