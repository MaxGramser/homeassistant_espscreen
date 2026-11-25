# Firmware preview architecture

The tile editor remains Vue. Its optional device preview is a single canvas backed
by LVGL and the actual `components/smart_display/runtime_tiles.h` renderer.

```text
Shared firmware YAML ── ESPHome codegen ── styles, widgets, fonts
Shared runtime_tiles.h + ESPHome font.cpp + LVGL ── Emscripten ── WASM
Manager's normal layout/header/state packets ── WASM receive()
Browser pointer events ── firmware touch guard + LVGL pointer input
Firmware ESPHome action requests ── browser transport ── Manager ── Home Assistant
Home Assistant action responses + state packets ── firmware confirmation handling
WASM display flush ── RGBA framebuffer ── canvas
```

The host owns transport, time and input. Firmware owns tile placement, sizing,
colours, glyph selection, detail rendering and page transitions. No browser tile
renderer is a fallback. There are no HTML page dots over the framebuffer.

Taps control the Home Assistant instance connected to Screen Manager, including
real devices if that instance has them. The host copies the firmware's existing
ESPHome service requests into a queue, relays them through a CSRF-protected endpoint,
and supplies Home Assistant's success/refusal to the firmware's normal callbacks.
Live entity changes and a post-command refresh use the manager's device state packets.
There is no browser switch simulation or duplicate thermostat action logic. Commands
must target an existing entity and an action Home Assistant offers for that entity.

Holding the title bar opens `settings_screen.h`, using the same boot geometry, fonts and navigation as
the panel. `settings_transport.h` binds its rows to the selected panel's settings and board Extras.
Extras arrive through the existing per-device SSE stream; the browser supplies values, never widgets.
Writes use the existing validated settings endpoints and require **Taps control devices**. Virtual
screens have no hardware Extras, and the host does not bind restart or calibration actions.

`renderer_host_api.h` declares the browser adapter's C interface. A source fingerprint
covers the shared renderer's local dependencies, generated UI/font assets, UI-related
YAML and the host adapter. Changing board pins alone does not change it. The manifest
check rejects changed source, and the runtime test compares the binary's embedded
fingerprint with the manifest, so updating only a header cannot pass.

When updating firmware:

1. Run the regular firmware checks (`tools/check.sh --firmware`).
2. Run `web/wasm/build.sh` against that same checkout. It uses the add-on's pinned
   ESPHome version and regenerates every font/style profile from the shared YAML.
3. Run the WASM runtime tests at the supported profiles and the normal repository checks.
4. Build the editor and include its generated static assets in the change.

Changes to renderer internals normally compile directly. Changes to hardware APIs or
ESPHome's code-generation shape may require an adapter/generator update; these should
fail the build, rather than loading a stale imitation. Resolution and grid are runtime
inputs. Font/style density profiles are generated at build time. A feature may add glyphs
to a shared font with `- id: !extend <font id>` in its `font:` list; the generator merges
that item into the font with that id, as ESPHome does, and fails when no font has it.

A preview that is older than the firmware says so itself. CI rebuilds the preview and the editor after every firmware
change on dev (`.github/workflows/preview.yml`); when that job fails, the editor that was built last is a developer's,
and `web/preview-age.ts` has told it, from the commits, that the firmware changed after the preview was last built. The
preview pane then shows one quiet line with the date. An editor built by CI never shows it. The built editor carries the
dates only while the preview is stale: a current preview says nothing that changes from one commit to the next, so the
bundle in Git equals a build of the same sources (`tools/check.sh`, "bundle in Git is fresh").

## Plugins

A plugin's tile is drawn by the plugin's own C++ (docs/PLUGINS.md), which is not part of the shared firmware, so the
preview cannot have it built in. It gets it the way a program gets a library: as a module of its own that is loaded
into the running preview.

```text
Plugin's components/<name>/*.cpp ── web/wasm/build_plugin.py (Emscripten, the preview's own flags) ── <id>.wasm
<id>.wasm ── checked by the add-on (plugin_module.py) ── api/plugins/<id>/module ── the editor (stores/plugin-code.ts)
The editor writes it into the preview's file system ── loadDynamicLibrary ── preview_plugin() runs the plugin's setup()
The add-on's normal state packets for the plugin tile (its options, its data) ── the plugin's create(), on_state(), on_tick()
```

- **The preview is a main module.** It is built with the plugin host whole (`USE_TESSERA_PLUGINS`), every symbol
  visible and kept (`-fvisibility=default`, `-sMAIN_MODULE=1`), so a plugin's module finds LVGL, the plugin API and the
  C++ library in it, whatever it calls. `web/wasm/toolchain.py` holds the flags the preview and a module share.
  What that costs, measured on 2026-11-24: the binary went from 15.5 MB to 17.4 MB (4.6 MB to 5.3 MB compressed), and
  Emscripten's own script from 43 KB to 584 KB. The app serves the binary as it is, not compressed, under a name of
  its content that a browser keeps, so an editor pays 1.9 MB more once per update of the app: about two seconds at
  1 MB a second. The script is loaded with the first preview and no longer with the editor, so the editor's own
  script did not grow (2.02 MB before, 2.01 MB after). Not measured: the first load through Home Assistant's ingress
  on a slow link, and Safari on a phone.
- **A module is the plugin's component and its start.** `build_plugin.py` compiles every `.cpp` of the component and
  generates what the screen's build generates for it (`smart_display.register_plugin`): its object, its id and version,
  its tiles' memory, its texts in every language (one is chosen when the preview starts it) and a call of its
  `setup()`. Its last section, `tessera`, says what it is: `{id, version, api, abi}`.
- **The number that says whether a module fits** (`toolchain.plugin_abi`, the preview's `preview_plugin_abi()`,
  `plugin_abi` in `renderer.json`): the pinned Emscripten, LVGL and ArduinoJson, the defines, LVGL's configuration and
  every header of the core a plugin can reach through the plugin API, as they are written. A module calls straight into
  the preview's memory, so one built against other headers would be wrong without any error; the number makes it unfit
  instead. A change to `theme.h` or `plugin_api.h` is a new number, and every module is built again for it.
- **What a module may include** is `web/wasm/host_include`: the plugin API and the few headers of ESPHome a tile needs
  (`Component`, `millis`, the log macros). A plugin that needs or brings hardware (a speaker, a camera) has nothing a
  browser can run and is not built, with one sentence saying so. A plugin whose `plugin.yaml` makes ESPHome entities
  for its component to read (a switch, a sensor of Home Assistant) is not built yet either: that needs ESPHome's own
  code generation for the plugin, which the preview does not run.
- **Where a module comes from.** The plugins repository builds one for every release its index lists, for the preview
  of main and of dev, and publishes them on its branch `modules` (`modules/<number>/index.json`,
  `modules/<number>/<id>-<version>.wasm`). The add-on reads the list with the index, fetches a module once, when an
  editor first asks for it, checks it and keeps it under `data/plugins/modules`. A plugin someone is making in a folder
  brings its own: `<folder>/.preview/<id>.wasm`, where `build_plugin.py` writes it. A plugin from a link or a branch has
  none.
- **When a new number has its modules.** The plugins repository's workflow `modules` builds what is missing after each
  run of its index, which is every hour, and by hand; a full run for a new number took 2 minutes 50 seconds on
  2026-11-24. So on dev, a change to one of the headers the number is made of shows placeholders until the next run:
  up to an hour, plus those minutes. Tessera's workflows have no token that reaches the plugins repository, so the
  preview's own build cannot start that run. A release does not wait for the hour: `tools/release.py publish` looks
  whether every plugin the plugins repository's main offers has its module, or the reason it has none, for the number
  of the released preview, has the workflow build what is missing, and says the release is not done while one is
  (docs/RELEASING.md, `tools/release_plugins.py`). The release commit is a commit of dev and the number is made of
  headers, not of a version, so in most releases the modules built for dev are the release's and nothing is built.
- **What the add-on checks** (`plugin_module.py`, before any byte reaches a browser): the module names this plugin, this
  version and this preview's number; a published one is the file the list names (its size and SHA-256); and its only
  way out is the preview. A module's imports must come from the preview itself (`env`, `GOT.func`, `GOT.mem`); one that
  carries script for the page (Emscripten's `EM_ASM`, `EM_JS`), asks to run script, or asks for a file or a socket is
  refused. The editor's content security policy forbids evaluating script, so the browser refuses the same.
- **Nothing is built or drawn where the add-on runs.** A module is built by the plugins repository's own build, drawn
  in the browser of whoever has the editor open, and the add-on hands out files of some tens of kilobytes. A module
  file is read and checked once and remembered by its time and size; the list of published modules is read with the
  index, at most every ten minutes; and a module's address names its version and the preview's number, so a browser
  keeps it for a day.
- **A plugin without a module is no error.** The preview draws its tile as a screen without that plugin does (a plain
  card that says the plugin is missing), and the page editor keeps its own drawing of it.

Known limits, each with its cause:

- **A plugin's fetched data follows with the preview's refresh, every ten seconds.** An entity a tile reads is on the
  add-on's entity stream and reaches the editor's card as it changes. What the add-on fetched from a web service for
  a plugin is not on that stream, so the editor's card has it at the next refresh. A screen gets it sooner.
- **A picture a plugin's example names stays a block.** An example in `preview.yaml` names the address of a cover or a
  poster and, for the bench, a file to show in its place (`pictures`). The add-on asks the address itself, as for a
  tile on a screen, and does not read those files; an address that is a stand-in gives no picture. A tile on a page
  shows its real pictures.
- **No module** for a plugin that needs or brings hardware, one whose `plugin.yaml` makes ESPHome entities of its own,
  and one added with a link or from a branch. Each keeps the editor's own drawing. The second kind is eleven plugins
  of the index today, and what building them takes is in docs/open-issues/plugin-modules-with-esphome-entities.md.
- **A card on a page out of sight of the hidden firmware** (more asked faces than one page holds) follows the clock
  once a minute, not each second: a countdown on it steps by the minute until its page has the glass.

### The page editor's own cards

The editor draws every card itself, from the firmware's numbers (docs/PAGES.md), so that a card can be chosen, dragged
and resized. A card it cannot draw well enough that way is shown as the firmware drew it, cut from the firmware's
frame, on the editor's own card, which stays the editor's: its outline, its handles and its menu are the same. Today
that is a plugin's tile, on a page and in the library. The road is one, and any other card can take it later.

**One call.** `useFace(() => ask)` in `web/src/stores/faces.ts` gives a component the picture of a card for as long as
it stands: it asks while it is wanted and gives the asking back when it leaves. `TilePlugin.vue` is its caller. Which
tiles take a firmware-drawn face, and what draws them, is decided in one place outside the store,
`drawnBy()` in `web/src/stores/plugin-code.ts`: a plugin's tile whose plugin has a module in this screen's preview.
The store knows a tile, a size and a glass, and nothing of plugins.

**One key.** A face is keyed by what is drawn and never by where it stands (`faceKey`). A tile moved to another cell,
a copy of it, and the same tile shown in the library ask the same question and share one picture. The key is its own
full text, not a short hash: it names a picture kept for weeks. Its parts, and what each stands for:

| Part | What it stands for |
|---|---|
| The glass: the screen's id | What is installed on that screen and how it is set: its plugins, their versions and inputs, its settings. Two screens never share a card. |
| The glass: pixels, grid, density | The size of a cell and of everything on it. |
| The glass: look and language | Light or dark, and the words the firmware writes. |
| What drew it (`by`) | The code that draws this kind of card: the plugin, its version, and the preview's own number. A card another version drew is another card, so an update never shows an old one as today's. |
| The tile type, its cells | `plugin:<plugin>.<tile>` and columns by rows. A card is drawn per size, never scaled: a plugin lays itself out differently at each. |
| The tile's name and options | As the screen gets them, with the options in a fixed order. |
| `example` | Whether the card shows the plugin's own example instead of what the tile reads now (below). A tile nobody set up and a library sample have the same options and must not share a card. |

Widen the key when something else starts to change the picture, and only then.

**One firmware, fed what is asked for.** `GlassFaces.vue` keeps a single preview nobody sees (`FirmwarePreview` with
`manual`). It does not run the draft. It runs a layout made of the asked tiles alone, each at a place of its own on
pages of the screen's own grid. So the add-on shapes messages only for those tiles, a card is drawn in the screen's own
look whatever section it stands in on its page (the editor's own filter for a contrast section then applies once), and
there is no second firmware for the library. It lives while a face is asked for and a minute after, on the glass it
was asked for: on another screen, or in another look or language, it goes at once, so a screen whose pages ask for no
face runs no firmware behind them.

**What it is loaded with, and when it stops.** What a screen runs is read from the add-on's list of installed plugins,
by the screen's id (`nodeOf` in `model/plugins.ts`, the key every part of the editor reads that list by). `codeFor`
waits for that list, so a preview that starts with the page is not started without its plugins' code, and
`GlassFaces.vue` follows `runsOn(screen)`: a plugin added or updated while the page is open gets its code without a
reload. A refresh the add-on refused or did not answer, as when the app restarts under an open page and a write waits
for its new token, is asked again by the preview ten seconds on, and no card is copied meanwhile (`failed` with
`final` false). A firmware that cannot go on (it did not load in this browser, or it threw in a frame) ends it for
that glass and that code: every card keeps the editor's own drawing, and nothing is tried again and again.

**A tile on no page shows the plugin's own example.** A tile in the library has no id, and nothing of its own to read:
drawn as it is, it would say that it waits to be set up. The request names the slots that want the example
(`examples` in `POST api/firmware-preview`), and the add-on fills each with the plugin's `preview.yaml`, the file its
maker wrote for the plugins repository's bench: the tile's options, the answer of each fetch as the web service gives
it, the entities as Home Assistant has them, and moments written from now (`plugin_examples.py`). It goes through the
app's own shaping (`Plugins.tile_message`: the fetch's map, the entity's part, the bounds of the message), and nothing
is asked of a web service or of Home Assistant for it. The file comes from the plugin's folder, or once from GitHub at
the plugin's commit, kept under `data/plugins/examples`. A plugin without the file shows the tile as it waits.

**Asked, not polled.** The firmware is handed a new layout when what is asked for changes, and new values when the
add-on has them: the entity stream for the entities of the asked tiles, and the preview's slow refresh behind it. Its
clock has to run for a card that counts on it, so it takes one step a second while a face is asked for and the page
is in sight, and stops entirely otherwise. A card is copied only when the firmware says its pixels changed:
`preview_cards` carries a count per card that moves when that card looks different (told from the pixels of the frame,
since the display redraws whole frames and a card redrawn the same has not changed). A step in which nothing changed
copies nothing, not even the frame. With more cards than one page holds, the firmware stays on a page while one of its
faces is still to come, and looks at a page out of sight when a face of it was never drawn, when new values came, and
otherwise every ten seconds. While the layout changed and the firmware does not have it yet, nothing is taken.

**Kept between visits.** The cards are kept in the browser by the same key (`model/face-cache.ts`, IndexedDB).
Starting the firmware takes a few seconds; at the next visit the cards of the last one stand at once, dimmed, until the
firmware has drawn them again. Nothing of this runs while no face is asked for, and the preview's own script is loaded
with the first preview, not with the editor.

`web/wasm/test_plugin_module.mjs` builds the preview probe (`tests/fixtures/plugins/preview_probe`) into a module, loads
it into the real preview and reads back the line only that plugin's code can have written, its ticks, the card a tap
opens, and that a card's count moves only when that card changed. `tests/test_plugin_module.py` holds what the add-on
reads, refuses, fetches and keeps, `tests/test_plugin_examples.py` a plugin's example through the app's shaping, and
`web/tests/plugin-faces.spec.ts` the key, the asking and the preview its owner draws.

See [the build instructions and current limitations](../web/wasm/README.md).
