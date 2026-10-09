# Plugins

A plugin adds something to the screens a person chooses, without the core knowing that plugin exists: a tile with data
from a web service, hardware on one board, a feature not everyone needs. How to make one is in the plugins repository,
[github.com/MaxGramser/tessera-plugins](https://github.com/MaxGramser/tessera-plugins) (its `docs/` and `AGENTS.md`).
This page is the core's side: what the firmware, the add-on and the editor do, and the rules a change here keeps.

Plugins are on dev while the plugin API is 0.x (the plugin API is 0.5 now): in an app added from the `#dev` URL, a
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

## What a plugin can add

| Part | Firmware | Add-on | Editor |
|---|---|---|---|
| A tile, with data from a fetch | `Tile`, `add_tile` | `Plugins.tile_message`, `plugin_fetch.py` | library, inspector, `preview` drawn from the data |
| A tile of an entity | `TileContext.entity`, `tessera::action` | the manifest's `domains`, `attributes` and `fields`; `Plugins.entity_part` (state, name, named attributes, fields), `related_entities`; `has_attributes` through `Plugins.entities_with` | entity picker of those domains, also ones Tessera draws no tile for; with `has_attributes` only the entities that have them, and always the one chosen (`offeredEntities`) |
| A card | `Card`, `add_card`, `open_card`; closed by `hide_detail` | nothing | nothing |
| A tap action | `add_tap_action`; `event()` runs a tile's `plugin:` tap | `validate_layout` takes a `plugin:` tap | the tile inspector's tap choices |
| A top bar item | `add_bar_item`; `header_bar::Kind::plugin` | `validate_header` type `plugin`, sent to a screen whose hello says `plugins` | "From plugins" in Top bar, Add |
| Settings rows | `settings(SettingsPage&)`; `settings_screen::plugin_pages` | `Plugins.settings_for`, `set_setting`: the manifest's `settings`, entities of the screen's own device | under Screen settings (`PluginSettings.vue`) |
| A question to Home Assistant | `tessera::send`, `on_message` (op `plugin`) | `Plugins.answer`: only `permissions.ha_commands`, logged; an answer the manifest's `answers` maps goes as its fields, the rest as it came; both bounded (`bounded`, 3.2 KB, by bytes) | the commands under "What it may do" |
| The moments | `on_ready`, `on_interval` (every 250 ms; `on_tick` before 0.4), `on_standby`, `before_update`, `on_cards_closed`, `on_alert`, `on_touch` (0.3: every tap `screen_input::TouchGuard` takes, through `screen_hooks::touched()`) | | |
| A board's own hardware | the plugin's `plugin.yaml` (audio codecs, a relay), its `boards` in the manifest | offered only to the screens of those boards | the Plugins page says which boards |

## Where a plugin comes from

- **The index** (`tessera-plugins/index.json`): Tessera's own plugins (label Tessera) and entries of `community/`
  (label Community), each pinned to a commit, read when the editor opens and at most every ten minutes (ETag).
- **A link** (`POST api/plugins/link`): the newest release of any GitHub repository, pinned to its commit (Community,
  or Tessera for a repository of MaxGramser); a branch to test, which every build takes anew (`refresh: 0s`, Test); or
  a folder in `tessera-plugins/` beside the ESPHome folder (Test). A release added this way follows its repository:
  `Plugins.refresh_links` asks for its newest release at most every hour and offers it as an update, so a maker
  publishes a release and nothing goes through Tessera.
- **An update** is a newer version in the index or of a linked repository: the screen's Plugins tab and the Plugins
  page offer it, and the build queue takes the screens one by one. A screen with more than one update offers "Update all
  on this screen": every update in one request, so the screen builds once (`updateAll` in the editor; `apply` takes up
  to eight plugins at a time). An update keeps what was filled in when the plugin was added: the editor sends the
  screen's stored values and parts again, and `apply` keeps a stored value the request leaves out. A test (a branch or
  a folder) never waits for an update: every build takes what it holds. An update whose rights differ from what the person agreed to
  (`permission_hash`) waits for their yes in the editor; the add-on refuses it without (`consent`).

## What is not built yet

A plugin's own messages beyond Home Assistant commands, pictures of a plugin's own, and Python modules of Tessera's own
plugins in the add-on (the design's `module`).
