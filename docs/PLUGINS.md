# Plugins

A plugin adds something to the screens a person chooses, without the core knowing that plugin exists: a tile with data
from a web service, hardware on one board, a feature not everyone needs. How to make one is in the plugins repository,
[github.com/MaxGramser/tessera-plugins](https://github.com/MaxGramser/tessera-plugins) (its `docs/` and `AGENTS.md`).
This page is the core's side: what the firmware, the add-on and the editor do, and the rules a change here keeps.

Plugins are on dev while the plugin API is 0.x (the plugin API is 0.8 now): in an app added from the `#dev` URL, a
local copy of the app, and the editor's development server (`core.plugins_enabled()`). The stable app has no Plugins
page, no routes and no loop.

**The API's number.** A plugin builds on every core with the same major and at least its minor. From 1.0 on that is a
promise: a minor only adds, only a break raises the major. Major 0 is the time before the promise: a minor may still
change a name or a signature while the API settles (0.4 renamed `Plugin::on_tick` to `on_interval`), and Tessera's own
plugins move with it in the same release. A test keeps the number equal in `plugin_api.h`, `__init__.py`,
`plugin_manifest.py`, this page and the host probe's manifest.

## The pieces

| Where | File | What |
|---|---|---|
| Firmware | `components/smart_display/plugin_api.h` | What a plugin uses: `tessera::Plugin`, `tessera::Tile`, `TileContext`, the drawing helpers, the clock. The API's version, `PLUGIN_API_MAJOR/MINOR`. |
| Firmware | `components/smart_display/plugin_host.h`, `plugin_host.cpp` | The core's side: the register, a plugin tile in a card, the moments, the hello. |
| Firmware | `components/smart_display/__init__.py` | `register_plugin()`, which a plugin's `__init__.py` calls: id, version, tile memory and screen texts from its manifest. `PLUGIN_API`. |
| Add-on | `screen_manager/app/plugin_manifest.py` | Reads and checks a manifest. Standalone: the plugins repository's `tools/check.py` runs this file. `PLUGIN_API`. |
| Add-on | `screen_manager/app/plugin_fetch.py` | The building block `fetch`: fill in, ask, map, cache, back off. |
| Add-on | `screen_manager/app/plugin_store.py` | `/data/plugins.json` (per screen) and `/data/plugin_secrets.json` (0600). |
| Add-on | `screen_manager/app/plugins.py` | The index and test folders, the editor's payload, the plugins file, adding and removing, a plugin tile's state message, the fetch loop. |
| Add-on | `firmware.py` (`PLUGINS_SUFFIX`, `save_plugins`), `page_layout.py`, `core.py` (`plugin_tile`, `PLUGIN_MEMORY`), `page_delivery.py` (`plugins_of`) | The sidecar, the document, the layout check and price, the negotiation. |
| Editor | `web/src/model/plugins.ts`, `web/src/plugin-state.ts`, `web/src/components/Plugin*.vue`, `ScreenPluginsTab.vue` | The Plugins page, the screen's Plugins tab, a plugin tile in the library and the inspector. |
| Test | `tests/fixtures/plugins/host_probe/`, `tools/render/run.py --plugin` | The host probe: a complete plugin that logs every moment of the API; the render harness builds it into a board's firmware for this computer and reads the moments back (docs/TESTING.md, "The plugin host"). |

## A plugin tile, end to end

1. **The document** stores `{"kind": "plugin", "plugin": "ov_departures", "tile": "next", "options": {...}}`. Flat, as
   the protocol and the layout check see it, that is `entity: "plugin:ov_departures.next"` with `options.plugin`.
   `core.entity_id()` is unchanged (commands and events use it); `core.plugin_tile()` is the second kind a layout takes.
2. **The layout check** keeps only the shape of a plugin tile: its size, colour, icon, `tap` (auto or none) and at most
   twelve options of its own, each a short text, a number or true/false. A saved layout never becomes unreadable
   because a plugin left a screen.
3. **The price** of a plugin tile is its manifest's `memory` (`core.PLUGIN_MEMORY`, filled by `plugins.Plugins`), plus
   the tile and its extras on a board without PSRAM. The screen counts the same (`plugin_host::bytes`, from the same
   manifest through `register_plugin`). A tile of a plugin the app does not know costs `PLUGIN_PLACEHOLDER_BYTES` (64),
   as on the screen.
4. **Negotiation**: the screen's hello lists the feature `plugins` (it takes plugin tiles and a plugin's item in the
   top bar), with `plugin_api` (the version) and `plugins: [{id, version, tiles}]` (what is built in). A layout with a
   plugin tile, and a top bar with a plugin's item, go only to a screen whose features say `plugins`; one without gets
   the refusal "update the firmware". No firmware number gates it, so dev screens work before a release numbers them.
5. **The state message** of a plugin tile (`Plugins.tile_message`) has `state: "ok"`, no attributes, `o.plugin` (its
   options with the manifest's defaults) and `x`: the mapped answer of its fetch and, for a tile of an entity
   (`Plugins.entity_part`), the entity's state, name, the attributes the manifest names and the `fields` it takes out
   of them. `x` stays under 2.6 KB (`X_BUDGET`). Bytes decide, not a count: a text is cut at 48 bytes, and lists are
   shortened, all to the same length from the end, only when together they do not fit. Two days of 96 prices fit
   whole. A list of objects never goes as it is: `fields` with `as: numbers` turns `raw_today[*].value` into one list
   of numbers.
6. **On the screen** `page_receiver` keeps `o.plugin` and `x` as JSON in the tile's `Extra` (`plugin_options`,
   `plugin_state`). `render_slot` hands a plugin tile the card's extra layer (`plugin_host::render`): a new
   `tessera::Tile` when the card shows another tile, size or options, `on_state` when the data changed, `on_theme` when
   the look did. The once-a-second gate in `tick()` calls `on_tick` for every plugin card on the glass, and a short tap
   goes to `on_tap` through the same guard as every tile's. `end_extra` and `release_kept` delete the object.
7. **In the editor** a plugin tile is drawn from its data when its manifest has a `preview`: the add-on fills in the
   first rows (`GET api/plugins/<id>/preview/<tile>`, `Plugins.preview`) and the mockup counts down to a moment on the
   editor's clock, so a page in the editor looks like the glass. Without a preview it shows the icon, the name and the
   manifest's `example`. The editor loads the plugins as soon as they are on, so a page with a plugin tile knows its
   type before the Plugins page was opened.
8. **A tile whose plugin this screen lacks** is a plain card: its icon, its name and "Plugin missing"
   (`screen.plugin.missing`). Never an error, never a restart.

## A plugin on a screen

- `<name>.plugins.yaml` beside the screen's YAML holds its plugins; only the app writes it. The screen's YAML attaches it
  once under `packages:` as `tessera_plugins: !include <name>.plugins.yaml`, the way Override YAML attaches
  `<name>.local.yaml`, and with the same rules (`_ensure_include`: the file first, then the line; another include under
  that key is refused).
- A plugin from the index is a remote package and a git external component, both pinned to the commit the index names,
  `refresh: never`. A plugin from a test folder (`tessera-plugins/<id>/` beside the ESPHome folder) is an `!include` and
  a local external component, by a path relative to the ESPHome folder, so the app, Device Builder and a shared folder
  build the same.
- Adding or removing writes `plugins.json` and the plugins file, and puts the screen in the queue for its own build and
  update (`firmware.start`, action install). A plugin update is a build of the whole screen, so it shows as every build
  does: `Manager.builds` says per screen what is being built for it, whoever asked (`by`: update, plugins or install;
  `state`; ESPHome's `stage`), in the light inventory the editor gets live; the editor's store (`buildOf`,
  `buildProgress`) is the one place every part reads it from, and `BuildLog.vue` shows the progress and the log in the
  screen's Plugins tab, on the Plugins page and in Settings, Updates. Never track a build in a part of its own. The queue builds one screen at a time, in the order asked, each when the
  app's build slot is free, so ticking three screens on the Plugins page builds them one after the other. A screen
  without a profile in the app gets the file and the line to paste.
- Removing a screen removes its plugins and, when no screen uses a plugin any more, its secrets.

## The fetch loop

`Plugins.loop` runs every 15 s while some layout has a plugin tile: it asks what is due for every plugin tile
(`Fetcher.get`, one ask per distinct URL and headers), and marks the tiles whose answer changed dirty, so the next sync
sends them. The rules (named hosts only, public addresses only, checked again at connect time by `PublicResolver`, no
redirects, 64 KB, 10 s, JSON, every 30 s at most, secrets never logged) are in `plugin_fetch.py` and the plugins
repository's `docs/FETCH.md`.

## Rules a change keeps

- **The core never names a plugin.** A hook a plugin needs goes into `plugin_api.h` for every plugin, and raises
  `PLUGIN_API_MINOR` (`plugin_api.h`, `__init__.py`, `plugin_manifest.py`: a test keeps them equal).
- **No plugin code in the add-on or the editor.** They read the manifest and run their own building blocks.
- **A plugin tile is never an error.** Unknown plugins, missing manifests, failed fetches: a placeholder or a `wait`.
- **Secrets stay in `plugin_secrets.json`**: never in a payload to the editor, a message to a screen, a YAML file or a
  log.
- **Test against real data**: the plugins repository's `tools/check.py` uses this `plugin_manifest.py`; change both in
  step. A series (prices, a forecast) is tested in `tests/test_plugins.py` (`Series`) with two real days of Nord Pool
  prices (`tests/fixtures/plugins/prices/`) in the shape of every integration that gives one: an attribute list of
  numbers or of objects, or an action's answer, with each way Home Assistant writes a moment.
- **One path language.** A fetch's `map`, a tile's `fields` and an answer's `fields` share `parse_path` and
  `plugin_fetch.field_value`, and the kinds `text`, `number`, `epoch` and `numbers`. A new kind or step goes there,
  for all three.
- **The host proves the host.** A change to `plugin_host.cpp`, `plugin_api.h` or the receiver's plugin fields runs
  `tools/render/run.py --plugin tests/fixtures/plugins/host_probe`, plain (the CYD's path: a card made anew when its
  page comes back) and with `KEPT_PAGES_HOST=1` (the kept path of a board with PSRAM), docs/TESTING.md, "The plugin
  host": the probe's log lines are the only proof that a card is made, fed, ticked and deleted at the right moments. A
  new moment of the API gets a line in the probe and a wait in `plugin_round`.
- **One name per thing.** A plugin's part is keyed `plugin:<plugin>.<part>` (`plugin_key()` on the screen,
  `core.plugin_tile()` in the add-on, `TileType::key` and its siblings in the API); the Home Assistant entity a plugin
  tile belongs to is `plugin_entity` (the option, `Extra::plugin_entity`, `TileContext::entity`). The domains a tile, a
  tap action or an input takes are `domains` in the manifest. Keep it so: a new part takes the existing word.
- **The manifest is the plugin's word, not a fence.** What the add-on enforces is `permissions.network` (every fetch)
  and `permissions.ha_commands` (every question through `tessera::send`). `home_assistant_actions` and
  `read_entities` are declarations the screen does not check: code built into the firmware can do what the firmware
  can. The editor says so (`editor.plugins.warning`); never write as if the screen enforced them.

## A plugin's settings on a screen

Everything a person sets for a plugin on a screen is in one place: the plugin's details on the screen's Plugins tab
(`PluginDetail.vue`, section "Settings"), in three groups by what a change does. Screen settings only links there.

| Group | What | What a change does | Code |
|---|---|---|---|
| On this screen | The manifest's `settings`: ESPHome entities of the plugin's `plugin.yaml` on the screen's device | Takes effect at once, through Home Assistant (`set_setting`) | `PluginSettings.vue`, `Plugins.settings_for` |
| For every screen | `inputs` with `scope: all` | A secret stays in the app (`plugin_secrets.json`); a value goes into each screen's next build | `PluginSetup.vue only="shared"` |
| When building | `inputs` with `scope: screen` and `parts` | Builds the screen again: "Save and build" is the same `apply` as adding, and only lights up when something differs from the build (`setupChanged`) | `PluginSetup.vue only="screen"` |

**How a setting finds its entity.** A setting's `key` is the entity's name in `plugin.yaml` as ESPHome writes it in an
id: "Tap sound" is `tap_sound` (`Plugins.object_id`, ESPHome's `snake_case` then `sanitize`). The app looks in Home
Assistant's entity registry for an `esphome` entity of the screen's device whose `original_name` gives that key, so a
rename in Home Assistant keeps the link. It never uses `unique_id`: its shape changed with the ESPHome integration's
versions (now `mac/0/switch/Tap sound`). An entity without a registry entry is found by the end of its entity id, as
before plugin API 0.6, so older plugins keep working.

**The kinds.** The entity's domain decides the row: a switch, a number with its range and unit, a select (buttons up to
five options, a dropdown from six on, at most 48), a text (`text.set_value`, within the entity's min and max length,
hidden when its mode is password) and a button (`button.press`). A button's `status` names a text sensor the row shows
beside it, read again a few times after a press, so a test can say how it went. A status is only shown, never set.

## What a plugin can add

| Part | Firmware | Add-on | Editor |
|---|---|---|---|
| A tile, with data from a fetch | `Tile`, `add_tile` | `Plugins.tile_message`, `plugin_fetch.py` | library, inspector, `preview` drawn from the data |
| A tile of an entity | `TileContext.entity`, `tessera::action` | the manifest's `domains`, `attributes` and `fields`; `Plugins.entity_part` (state, name, named attributes, fields), `related_entities`; `has_attributes` through `Plugins.entities_with` | entity picker of those domains, also ones Tessera draws no tile for; with `has_attributes` only the entities that have them, and always the one chosen (`offeredEntities`) |
| A card | `Card`, `add_card`, `open_card`; closed by `hide_detail` | nothing | nothing |
| A tap action | `add_tap_action`; `event()` runs a tile's `plugin:` tap | `validate_layout` takes a `plugin:` tap | the tile inspector's tap choices |
| A top bar item | `add_bar_item`, its icon in a `tone` (0.8); `header_bar::Kind::plugin` | `validate_header` type `plugin`, `content` all or icon (wire `o`), sent to a screen whose hello says `plugins` | "From plugins" in Top bar, Add; Show: icon and words, or icon only |
| Settings rows | `settings(SettingsPage&)`; `settings_screen::plugin_pages` | `Plugins.settings_for`, `set_setting`: the manifest's `settings` (switch, number, select, text, button with its `status`), entities of the screen's own device found in the entity registry (`_setting_entities`) | in the plugin's details on the screen's Plugins tab (`PluginSettings.vue`), with its inputs and parts; Screen settings links there |
| A question to Home Assistant | `tessera::send`, `on_message` (op `plugin`) | `Plugins.answer`: only `permissions.ha_commands`, logged; an answer the manifest's `answers` maps goes as its fields, the rest as it came; both bounded (`bounded`, 3.2 KB, by bytes) | the commands under "What it may do" |
| The moments | `on_ready`, `on_interval` (every 250 ms; `on_tick` before 0.4), `on_standby`, `before_update`, `on_cards_closed`, `on_alert`, `on_touch` (0.3: every tap `screen_input::TouchGuard` takes, through `screen_hooks::touched()`) | | |
| A board's own hardware | the plugin's `plugin.yaml` (audio codecs, a relay), its `boards` in the manifest | offered only to the screens of those boards | the Plugins page says which boards |

## Where a plugin comes from

- **The index** (`tessera-plugins/index.json`): Tessera's own plugins (label Tessera) and entries of `community/`
  (label Community), each pinned to a commit, read when the editor opens and at most every ten minutes (ETag). An id
  belongs to the repository that first published it (`claims` in the index; a move goes through `transfers.yaml`).
- **A link** (`POST api/plugins/link`): the newest release of any GitHub repository (Community, or Tessera for a
  repository of MaxGramser); a branch to test (Test); a repository without a release, which becomes a test of its default
  branch, so pushing is enough to try a plugin; or a folder in `tessera-plugins/` beside the ESPHome folder (Test).
  Every one but a folder is pinned to the commit it was read at, so what is built is what the editor showed.
  `Plugins.refresh_links` asks for the newest release, or the newest commit of a test's branch, at most every hour and
  offers it as an update. It finds the repository again by GitHub's number of it, so a rename is followed and a new
  repository that takes the old name is never built.
- **An update** is a newer version in the index or of a linked repository (for a test: a newer commit), from the same
  origin: the screen's Plugins tab and the Plugins page offer it, and the build queue takes the screens one by one. A
  screen with more than one update offers "Update all on this screen" (`updateAll`), one request and one build. An
  update keeps what was filled in when the plugin was added. An update whose rights differ from what the person agreed
  to (`permission_hash`) waits for their yes in the editor; the add-on refuses it without (`consent`). A release the
  index blocks leaves the next build of every screen that runs it (`drop_blocked`).

## Which plugin

A plugin is known by its id: it lives in the firmware, in the layouts (`plugin:<id>.<tile>`) and in the secrets, so it
never changes. Its origin (`github.com/<owner>/<repo>[/<folder>]`, lowercase, or `folder`) says which plugin of that id
it is. Two screens may run two plugins of one id (a fork, a folder being made): a tile asks with its screen
(`known(plugin, inbox)`), a secret is kept for the origin it was filled in for and never handed to another, and nothing
moves a screen to another origin unless the person switches in the plugin's details (`switch`).

## What comes along

`requires.plugins` names plugins a plugin needs: they come along from the index, the newest that fits the screen.
`requires.features` names features (`plugin_manifest.FEATURES`: speaker, microphone, media player, camera, camera
sensor), each a promise about one ESPHome id (`ts_speaker`, ...), which a board brings (boards.json `features`) or a
plugin (`provides`). The camera sensor is only a board's (`BOARD_ONLY`): its promise is the board file's substitution
`CAMERA_I2C`, the bus a camera plugin drives the sensor on, and the board powers the sensor itself. A
feature the screen lacks comes along with the one plugin that brings it and fits; with several the person chooses
(`providers`), with none the plugin does not fit. One screen has one of each feature. A part with `features` is
offered and built only where the screen has them. `Plugins.plan` says what a change comes to before anything is built
(the editor's "Comes along", the tray's rows); `apply` carries it out in one build and marks what came along (`auto`).
A plugin another one needs only goes together with it, and what only came along is offered to go as well.

## Finding a plugin, and likes

The Plugins page has a tab per type, read from the manifest (`plugin_type`: tiles, functions, hardware) and one for
what is in use; the maker's `topics` are the chips under it. What fits none of the screens folds away under the list.
One bar holds the search (what narrows the list shows in it as pills), the tabs, a Filter menu (topics, maker, only what fits) and the order: most liked by default, `featured.yaml` in the plugins repository breaking a tie, or newest, or by name. A like is a heart a person gives a plugin of the index
that runs on one of their screens (`plugin_likes.py`): it goes to the Tessera website with a random key of this app
installation, only on a tap and after one yes that it counts in a public number; the plugins repository copies the
counts into `likes.json` every hour, which the app reads from GitHub.

## What is not built yet

A plugin's own messages beyond Home Assistant commands, pictures of a plugin's own, and Python modules of Tessera's own
plugins in the add-on (the design's `module`).
