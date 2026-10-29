# Plugins

A plugin adds something to the screens a person chooses, without the core knowing that plugin exists: a tile with data
from a web service, hardware on one board, a feature not everyone needs. How to make one is in the plugins repository,
[github.com/MaxGramser/tessera-plugins](https://github.com/MaxGramser/tessera-plugins) (its `docs/` and `AGENTS.md`).
This page is the core's side: what the firmware, the add-on and the editor do, and the rules a change here keeps.

Plugins are on in every app since 0.4.87 (the plugin API is 0.24 now); before, only in the dev app.
`core.plugins_enabled()` is the one switch: false takes the Plugins page, its routes and its loops out of the app.

**The API's number.** A plugin builds on every core with the same major and at least its minor. From 1.0 on that is a
promise: a minor only adds, only a break raises the major. Major 0 is the time before the promise: a minor may still
change a name or a signature while the API settles, and Tessera's own plugins move with it in the same release. A minor
may take a form away: a plugin that still uses it fails its build with the compiler's error at that call (0.24 took four
second forms away). `PLUGIN_API_BREAKS` (`plugin_manifest.py` and `__init__.py`, a test keeps them equal) is for a minor
after which an older plugin would still build but work wrongly (0.4, where `Plugin::on_tick` changed its meaning and the
old one became `on_interval`): a plugin written before it does not fit a core after it, and its build says so in one
sentence (`api_fits`; the plugins repository's check uses the same rule). A minor that only adds is not listed, so a
0.10 plugin builds on 0.11. A test keeps the number equal in `plugin_api.h`, `__init__.py`,
`plugin_manifest.py`, this page and the host probe's manifest.

## The pieces

| Where | File | What |
|---|---|---|
| Firmware | `components/smart_display/plugin_api.h` | What a plugin uses: `tessera::Plugin`, `tessera::Tile`, `TileContext`, the drawing helpers, the clock. The API's version, `PLUGIN_API_MAJOR/MINOR`. |
| Firmware | `components/smart_display/roomy.h` | Memory that takes PSRAM first: `roomy::Text`, `roomy::List`, the allocator behind `tessera::Text`, `tessera::List` and the plugin host's documents (below, "Rules a change keeps"). |
| Firmware | `components/smart_display/plugin_host.h`, `plugin_host.cpp` | The core's side: the register, a plugin tile in a card, its places for pictures, the moments, the hello. |
| Add-on | `screen_manager/app/plugin_pictures.py` | What a plugin's places may show (0.10 a tile, 0.13 a card, 0.14 a screensaver): the manifest's rules for its addresses and the fetching of them, kept by address. The question, the painting and the link are the one picture system's (docs/PICTURES.md). |
| Firmware | `components/smart_display/__init__.py` | `register_plugin()`, which a plugin's `__init__.py` calls: id, version, tile memory and screen texts from its manifest. `PLUGIN_API`. |
| Add-on | `screen_manager/app/plugin_manifest.py` | Reads and checks a manifest. Standalone: the plugins repository's `tools/check.py` runs this file. `PLUGIN_API`. |
| Add-on | `screen_manager/app/plugin_fetch.py` | The building block `fetch`: fill in, ask, map, cache, back off. |
| Add-on | `screen_manager/app/plugin_store.py` | `/data/plugins.json` (per screen) and `/data/plugin_secrets.json` (0600). |
| Add-on | `screen_manager/app/plugins.py` | The index and test folders, the editor's payload, the plugins file, adding and removing, a plugin tile's state message, the fetch loop. |
| Add-on | `firmware.py` (`PLUGINS_SUFFIX`, `save_plugins`), `page_layout.py`, `core.py` (`plugin_tile`, `PLUGIN_MEMORY`), `page_delivery.py` (`plugins_of`) | The sidecar, the document, the layout check and price, the negotiation. |
| Editor | `web/src/model/plugins.ts`, `web/src/stores/plugins.ts`, `web/src/components/Plugin*.vue`, `ScreenPluginsTab.vue` | The Plugins page, the screen's Plugins tab, a plugin tile in the library and the inspector. |
| Test | `tests/fixtures/plugins/host_probe/`, `tools/render/run.py --plugin` | The host probe: a complete plugin that logs every moment of the API; the render harness builds it into a board's firmware for this computer and reads the moments back (docs/TESTING.md, "The plugin host"). |

## A plugin tile, end to end

1. **The document** stores `{"kind": "plugin", "plugin": "ov_departures", "tile": "next", "options": {...}}`. Flat, as
   the protocol and the layout check see it, that is `entity: "plugin:ov_departures.next"` with `options.plugin`.
   `core.entity_id()` is unchanged (commands and events use it); `core.plugin_tile()` is the second kind a layout takes.
2. **The layout check** keeps only the shape of a plugin tile: its size, colour, icon, `tap` (auto or none) and at most
   twelve options of its own, each a short text, a number, true/false, a pick, an entity or a list (0.12, "Values of JSON" below),
   together at most 1280 bytes of JSON (`core.plugin_options`, the editor's `pluginOptionsShape`). Whether a value fits
   its option is the manifest's (`plugin_manifest.option_value`, in `Plugins.values_of`). A saved layout never becomes
   unreadable because a plugin left a screen.
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
   of them. `x` gets what the 4 KB message leaves after the rest of it, the tile's options included, and at most 2.6 KB
   (`X_BUDGET`): about 2 KB beside options that take their whole 1280 bytes. Bytes decide, not a count: a text is cut at 48 bytes, and lists are
   shortened, all to the same length from the end, only when together they do not fit. Two days of 96 prices fit
   whole. A list of objects never goes as it is: `fields` with `as: numbers` turns `raw_today[*].value` into one list
   of numbers.
   An option of kind `entity` (0.15) names its `domains` and the `attributes` the tile reads, and the editor offers
   the entities of those domains in a searchable picker. The add-on adds the chosen entity under
   `x.entities.<option id>` with the same bounded state, name and named attributes, and `updated`, when Home Assistant
   last heard from it (seconds since 1970), so a tile of several sources can say how old its values are. The chosen
   entities share what the tile's own entity and data leave of the room: one that does not fit waits as `too_large`
   alone. The add-on follows every chosen entity (`related_entities`, with the screen's own plugin) and sends the tile
   again when one changes; a choice is part of the layout, so it changes without a build. A choice of another domain
   is left out. The tile's own entity (`plugin_entity`) keeps its `x` as before, without `updated`.
6. **On the screen** `page_receiver` keeps `o.plugin` and `x` as JSON in the tile's `Extra` (`plugin_options`,
   `plugin_state`). `render_slot` hands a plugin tile the card's extra layer (`plugin_host::render`): a new
   `tessera::Tile` when the card shows another tile, size or options, `on_state` when the data changed, `on_theme` when
   the look did. The once-a-second gate in `tick()` calls `on_tick` for every plugin card on the glass, and a short tap
   goes to `on_tap` through the same guard as every tile's. `hide_extra` (the card shows something else), `end_extra` and `release_kept` delete the object.
7. **In the editor** a plugin tile is drawn from its data when its manifest has a `preview`: the add-on fills in the
   first rows (`POST api/plugins/<id>/preview/<tile>` with the options as they are kept, `Plugins.preview`) and the mockup counts down to a moment on the
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
- In the editor, adding and taking off are both set aside in the tray (`PluginTray.vue`, `setAside`,
  `setAsideRemoval`), with what comes along and what goes along (the add-on's plan), and Install sends each screen's
  changes in one request: one build per screen, whatever it gains and loses. Taking one off asks first when another
  plugin needs it, or one only came along with it (`removalPlan`).
- Adding or removing (`Plugins.apply`) checks everything first, then writes the plugins file, and only then keeps the
  records and the secrets: a request that is refused, or a file that cannot be written, changes nothing. A screen with a
  profile whose address the app does not know is refused before anything changes (`offline`). Then the screen goes into
  the app's one build line for its own build and update (docs/BUILDS.md). A plugin update is a build of the whole screen, so it shows as every build
  does: `Manager.builds` says per screen what is being built for it, whoever asked (`by`: update, plugins or install;
  `state`; ESPHome's `stage`), in the light inventory the editor gets live; the editor's store (`buildOf`,
  `buildProgress`) is the one place every part reads it from, and `BuildLog.vue` shows the progress and the log in the
  screen's Plugins tab, on the Plugins page and in Settings, Updates. Never track a build in a part of its own. The line
  builds one screen at a time, in the order asked, so ticking three screens on the Plugins page builds them one after
  the other. A plugin asked while the screen's update waits comes with that update: the two are one build. A change asked
  while the screen's own build runs gets a build of its own after it: that build may have read the YAML before.
  A screen without a profile in the app gets the file and the line to paste.
- A build that fails leaves the screen as it was (`_built`, `_settle_build`): it still runs its last firmware, so its plugins file
  goes back to that. A plugin added in it stays listed as failed (with the build's reason) and out of the file until the
  person tries again or takes it off; an update goes back to the version that built (`previous`) and keeps which one
  failed (`failed_update`), which the editor says, offering the update again. So a failed plugin never makes the
  screen's next build fail, an update of the core or a build in Device Builder. A build the app lost (a restart during
  it) counts as failed (`settle`).
- Removing a screen removes its plugins and its secrets for that screen alone, and, when no screen uses a plugin any
  more, all of its secrets.

## The fetch loop

`Plugins.loop` runs every 15 s while some layout has a plugin tile: it asks what is due for every plugin tile
(`Fetcher.get`, one ask per distinct URL and headers), and marks the tiles whose answer changed dirty, so the next sync
sends them. The rules (named hosts only, public addresses only, checked again at connect time by `PublicResolver`, no
redirects, 64 KB, 10 s, JSON, every 30 s at most, secrets never logged) are in `plugin_fetch.py` and the plugins
repository's `docs/FETCH.md`.

## Values of JSON (0.12)

A plugin's value may be a list or an object wherever a value travels: an option, a fetch, an action. One mechanism,
typed end to end, within the 4 KB message.

| Part | What | Where |
|---|---|---|
| An option of several values | `multiple: N` (2 to 16) on a text or a choice: a list in the order the person put them. A text list keeps texts; a choice keeps picks, `{value, label}`, the label being the words the person saw, since a list from a fetch may be gone or other later. | `plugin_manifest.check_option`, `option_value`, `keeps_picks`; `core.plugin_options`; `PluginListOption.vue`, `model/plugins.ts` (`picksOf`, `listValue`) |
| A choice found by searching | `search: true` on a choice with `options_from`: what the person types reaches its fetch as `{search}` (from two characters, 300 ms after the last key). One pick, or a list with `multiple`. Its answers stay ten minutes (`SEARCH_EVERY`), the editor keeps the last twelve. | `Plugins.choices`, `POST api/plugins/<id>/choices/<fetch>` with `{options, search, screen}`; `UiPicker` with `remote` |
| A fetch once per value | `each: <list option>`: one ask per value, `{<option>}` in the URL that value, each a question of its own shared as every other. The map runs per answer (`{each: value}` or `{each: label}` as a field), then `sort` and `limit` over all of them together; a map of one object gives one item per value. A value whose ask failed is left out and makes the list `stale`; the tile waits only when none has an answer. | `plugin_manifest.check_fetch`, `Plugins.asks`, `tile_data`, `refresh_data`, `plugin_fetch.apply_each` |
| A list in one ask | `{name\|,}` joins a list option's values, each percent-encoded in a URL, by the separator after the bar (1 to 3 characters). A list in a plain `{name}` is refused by the check. | `FETCH_PLACEHOLDER`, `plugin_fetch.fill` |
| One word per value | A fetch gets every value as one word: `true`/`false`, a whole number without `.0`, a pick as its value (`plugin_fetch.word_of`). The editor sends options as JSON, never in a query string, so `3` stays a number and a toggle one word. | `words_of` |
| An action | `tessera::action(service, entity)`, or `tessera::action(service, entity, fields)` with a JSON object of up to 16 fields, together 1 KB. Texts go in the action's `data` as they are; every other value in `data_template` as the Python literal Home Assistant's ESPHome integration reads back into its type (`helpers/template`, `_parse_result`), with a brace in a text written `\x7b`/`\x7d` so nothing a plugin sends is ever a template. Through the screen's own route, as a tap's: the entity's tiles wait for the answer; `entity` "" for an action whose fields name their own target. | `plugin_action.h` (pure, `tests/test_plugin_action.cpp`), `plugin_host.cpp`; the render harness checks what Home Assistant gets |

The options of a tile go to the screen with its data in one message, so the options of a tile together take at most
1280 bytes (`pm.OPTIONS_BYTES`, `core.PLUGIN_OPTIONS_BYTES`, `PLUGIN_OPTIONS_BYTES` in the editor, a test keeps them
equal) and the data gets what is left (`Plugins.tile_message`). The editor refuses a value that would not fit, with a
line under the list, instead of the delivery being refused later.

An app older than 0.12 does not know `multiple`, `search` or `each` and leaves such a plugin out of its list, as every
newer manifest field. A layout with a list option that such an app reads is kept as it is, and refused only when it is
saved there. Every value kept before 0.12 is still valid.

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
- **Memory: PSRAM first for what a plugin tile keeps** (`roomy.h`). The boards build with
  `CONFIG_SPIRAM_USE_CAPS_ALLOC`: a plain `std::string`, `std::vector` or `new` stays in the few tens of kilobytes inside
  the chip that Wi-Fi and the network stack need, and on a Guition with a few plugin tiles on kept pages a busy moment
  of Wi-Fi ran it out (2026-10-13: a picture's download aborted, or Wi-Fi stalled). So a plugin tile's options and data
  (`Extra::plugin_options`, `plugin_state`) are `roomy::Text`, the host parses them with a PSRAM allocator
  (`json_memory`), `tessera::Tile` and `tessera::Card` take PSRAM in their `operator new` (`tessera::InPsram`), and the
  API offers `tessera::Text` and `tessera::List` for what a plugin keeps. Keep it so: a new field a plugin tile keeps is a
  `roomy::Text` or `roomy::List`, a document the host builds or parses gets `json_memory`. Never what DMA or the network
  reads (a panel's buffer, a socket's): those stay where their driver puts them.
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
| Values of JSON (0.12) | `TileContext::options` holds lists and picks; `tessera::action` with a JSON object | `multiple`, `search`, `each`, `{name\|,}`; above | `PluginListOption.vue` |
| A tile of an entity | `TileContext.entity`, `tessera::action` | the manifest's `domains`, `attributes` and `fields`; `Plugins.entity_part` (state, name, named attributes, fields), `related_entities`; `has_attributes` through `Plugins.entities_with` | entity picker of those domains, also ones Tessera draws no tile for; with `has_attributes` only the entities that have them, and always the one chosen (`offeredEntities`) |
| A card | `Card`, `add_card`, `open_card`; closed by `hide_detail`; `on_tap` (0.12): a short tap on its room through the tiles' guard (`rt::allowed`), keyed by an 8 mm spot so a bounce on one row is one tap and the next row its own, with `tap_point()` in the room's pixels (`card_tap`) | nothing | nothing |
| A tap action | `add_tap_action`; `event()` runs a tile's `plugin:` tap | `validate_layout` takes a `plugin:` tap | the tile inspector's tap choices |
| Pictures on a tile (0.10) | `ui::picture` makes a place (a block in `theme::TRACK`) on the card in a call of the tile, `ui::set_picture` names its address and fit, `ui::pictures` says whether the board shows any. The places are the parts of one picture (`tile_picture::Part`, `set_parts`): `tile_ask` hands a plugin card to `plugin_host::picture_ask`, which measures them on the card; the question goes as every tile picture's, with `src` and `fit`; the atlas lands in the store under the tile's key, and `tile_picture_place` hands it to `plugin_host::picture_place`, which lays each place its piece (`lv_image_set_offset`, as the library's covers). The store counts a place's image as a card that draws (`picture_draws`, `picture_let_go`). A board without pictures has the API and no places. | `server.answer_plugin_pictures`: the tile is a plugin tile of the layout, its manifest gives it `pictures`, every address passes `plugin_pictures.allowed` (a host of `permissions.network`, or Home Assistant's own pictures for a tile of an entity); `Pictures.fetch` keeps each by address; `tile_art.encode` paints the frames (fit `fill` or `within`) and a still link serves the BMP | `PluginTile.pictures`; the mockup draws no picture |
| Pictures on a card (0.13) | The same `ui::picture` and `ui::set_picture` in a card's calls: `placing` is the tile's places in a tile's call and the open card's in a card's (`call`), so the places are the same `Place`s, measured from the card's room (`measure`), laid by the same `lay`. The card is one owner of the loader (`CARD_OWNER`, `Kind::CARD` 1, `Rank::CARD`, the full view's slot), its key apart from every tile's (`tile_picture::card_key`, `pcard|`), its question a tile's with `card` and `for` (`card_fields`), its answer `pcard` (`card_picture_answer`, `card_question`). The store counts its places as on the glass (`card_draws` in `picture_shown` and `picture_away`); closing lets the picture go at once (`card_pictures_end`: the loader's release, then `pictures_collect`). It shares the store's budget as the media card's cover does: the glass under it keeps its pictures, a page out of sight makes room first. | `answer_plugin_pictures` with `question.card`: a card of a plugin the screen runs (`Entry.card`), its manifest's `pictures`, every address through `plugin_pictures.allowed` (Home Assistant's own pictures only for a card shown for an entity of the layout, `of_entity`); the source pictures are kept by address, so the cover a tile shows costs no second fetch | nothing |
| A label of several lines (0.10) | `ui::text`: a label of the plugin's height, wrapped, ending in dots | nothing | nothing |
| Where a tap was (0.10) | `tessera::tap_point()`: the finger of the tile's `on_tap` in the tile's own pixels (`finger_at` in the tile's touch handler, made relative to the extra layer by `plugin_host::tap`) | nothing | nothing |
| The large digits (0.9) | `Font::DIGITS` is `setpoint_digits`, a font every board has, so it costs no flash; `ui::covers()` says whether a value has only its characters (`face_covers`) | nothing | nothing |
| Tones for a block (0.9) | `Tone::GOOD` (Home Assistant's green) beside ACCENT, BUSY and ALERT; `ui::set_fill` gives a block (a bar, a dot) a tone's colour, `ui::tone_color` the colour itself; one `tone_color` in `plugin_host.cpp` for the bar, labels and blocks | nothing | nothing |
| A sound of its own (0.8) | `plugin_sound.h` (`tessera::Sound`, `SoundPlayer` on `ts_speaker`; `add()`, 0.11, plays a sound after the ones before it, each followed by silence to its span, so the speaker spaces a run of clicks evenly); `smart_display.sound()` builds a WAV in | nothing: a plugin that needs the feature `speaker` | nothing |
| A top bar item | `add_bar_item`, its icon in a `tone` (0.8); `header_bar::Kind::plugin` | `validate_header` type `plugin`, `content` all or icon (wire `o`), sent to a screen whose hello says `plugins` | "From plugins" in Top bar, Add; Show: icon and words, or icon only |
| Settings rows | `settings(SettingsPage&)`; `settings_screen::plugin_pages` | `Plugins.settings_for`, `set_setting`: the manifest's `settings` (switch, number, select, text, button with its `status`), entities of the screen's own device found in the entity registry (`_setting_entities`) | in the plugin's details on the screen's Plugins tab (`PluginSettings.vue`), with its inputs and parts; Screen settings links there |
| A question to Home Assistant | `tessera::send`, `on_message` (op `plugin`) | `Plugins.answer`: only `permissions.ha_commands`, logged; an answer the manifest's `answers` maps goes as its fields, the rest as it came; both bounded (`bounded`, 3.2 KB, by bytes) | the commands under "What it may do" |
| The moments | `on_ready`, `on_interval` (every 250 ms; `on_tick` before 0.4), `on_standby`, `before_update`, `on_cards_closed`, `on_alert`, `on_press` and `on_step(Step)` (0.11, "Touch feedback" below) | | |
| Pictures in one system (0.17) | `ui::picture(parent, Placeholder::NONE)`, a place without its block; `on_picture(place, PictureState)` on a `Tile`, a `Card` and a `Saver` (`plugin_host::picture_outcome`, from `tile_picture_done`); the core's own sources as an address; `slide_pictures` from any call; `ui::live`, a tile's place that streams its camera on a P4 (`plugin_host::live_places`, `runtime_tiles` live places, the answer `plive`); `tessera::capturing` and the camera's dot (`plugin_host::camera_dot_update`); "Pictures on a plugin tile" below | `plugin_pictures.py` reads `cover:`, `camera:`, `entity:` and `step:`; `Manager.plugin_picture`; `picture_service._stream` streams a live place's own camera | nothing |
| Waking the screen (0.16) | `tessera::wake(plugin)`: `plugin_host::wake`, which `packages/core.yaml` points at the script `wake_from`, the one way Home Assistant's Wake button and a board's sensor take; "Waking the screen" below | nothing | nothing |
| Entities chosen per tile (0.15) | nothing new: the tile reads `x.entities.<option id>` (state, name, attributes, updated) from its data | an option of kind `entity` (`plugin_manifest.check_option`, `option_value`); `Plugins.tile_message` puts each chosen entity's `state_part` under `entities`, `related_entities` follows them | the tile's inspector: a searchable entity picker per option (`PluginOptions.vue`) |
| A screensaver (0.14) | `Saver`, `add_saver(id, step, make)`, `SaverContext`; `ui::takes_taps` (only for `taps: true`, `Plugin::set_taps`); `wish()`; `drift()`; "A screensaver" below | the manifest's `savers`; `Plugins.saver_kinds`, `saver_plugins`, `saver_step`, `refresh_savers`; `screen_saver.message`'s `pf`; `answer_plugin_pictures` with `question.saver` and `saver:picture` | the Screensaver card: a face per step, a step of its own in the order, its options |
| A popup (0.18) | `Popup`, `show_popup`, `close_popup`, `popup_shown`, `PopupWidth`; `ui::animate` with `Motion` and `ui::still`; `plugin_host` "A plugin's popup"; "A popup" below | nothing | nothing |
| The camera's turn (0.19) | `tessera::camera_turn()`: `camera_turn.h` from the board's `CAMERA_ORIENTATION` (`smart_display: camera_orientation`, 0 or 180), `glass::turn` and `runtime_tiles::landscape_turn` | nothing | nothing |
| What the hardware can do (0.19) | `hw::caps()` (`hw.h`, docs/PLATFORM_PLAN.md 3.3): live video, speaker, microphone, echo cancellation, a camera of the board's own, the live tiles at once, the memory; the build's half from `hw_build.py` (HW_* defines from the components in the configuration), the boot's half from the glass and the heaps; the hello's `caps` | `page_delivery.caps_of`: the record of a screen's hello, `live` from its features for an older firmware | nothing yet |
| The camera only sensing (0.20) | `Capture::SENSING` beside `Capture::CAMERA` in `tessera::capturing`: `capture_dot.h` draws the dot solid while anyone watches (a plugin's CAMERA, Home Assistant's pictures and stream) and as a ring while plugins only sense | nothing | nothing |
| A busy screen (0.21) | `tessera::squeeze(Work)`: how much of its video, its sensing or its background work a plugin gives up now (0, half, three quarters), from the governor (`pressure.h`, docs/PLATFORM_PLAN.md 4.10) | nothing | nothing |
| The screen's own camera on a tile of its own (0.22) | `tessera::offer_own_frames()` once in the plugin's setup, then while `tessera::own_tile_wants()` is true each camera frame to `tessera::own_frame(OwnFrame)` on the camera's task: RGB565 or the P4's YUV420, as the camera gave it. The screen's hello says `own_camera`, the app answers a live tile of the screen's own Video camera `own:`, and the screen draws it from the frames, with no encoder, app or network between. Screen camera 0.6.8 does it. |
| Someone hears the screen's microphone (0.23) | `tessera::capturing(plugin, Capture::SOUND, on)` from the plugin's own calls while anyone hears what the microphone hears (its video watched with its sound, a call). No dot changes; the screen keeps its live tiles at a quarter while it lasts, so the conversation's uplink is not starved by them (the governor, docs/PLATFORM_PLAN.md 4.10 and 5.1). Screen camera 0.6.12 says it while its video plays with sound. |
| Who may play and listen (0.19) | `tessera::audio::claim`, `release`, `open`, `held`, `holder` over `audio_owner.h` (docs/PLATFORM_PLAN.md 3.4): one owner of the loudspeaker and the microphone, roles DOORBELL, VOICE, CAMERA_SOUND, MEDIA, `lost` and `regained`; the core's own claims in `live_view.cpp` (a full view's sound, as CAMERA_SOUND or, for the view a ring opened, DOORBELL: `live_view::open`'s `role`, from `runtime_tiles` `live_begin`) and `features/audio-player.yaml` (music, through the media player's `on_play`, `on_pause`, `on_idle`) | nothing | nothing |
| A board's own hardware | the plugin's `plugin.yaml` (audio codecs, a relay), its `boards` in the manifest | offered only to the screens of those boards | the Plugins page says which boards |

## Touch feedback

A click or a buzz that answers a finger comes at the moment the finger does something, not with the action that follows.
`touch_feedback.h` says those moments and nothing else; a plugin listens (`on_press`, `on_step(Step)`, plugin API 0.11)
and makes the sound or the buzz. The core never plays anything itself.

| Moment | When | Said by |
|---|---|---|
| A press | A finger lands on something that takes it: the object under it, or a parent its events bubble up to, listens for a press, a tap or a hold (a tile, a key, a slider, a row of the settings, the top bar, a plugin's card). Not between the tiles, not for the push that wakes a dimmed screen, not in a calibration (`touch_feedback::quiet`, set in `packages/core.yaml`). | `touch_feedback_lvgl.h`, from LVGL's press of the input device, for every object |
| A step of a drag | A value under the finger passes a step: every 5 % of its range, every position of a range of 20 or fewer. Once per step, two at most for one move; the first value after a landing only marks the start, so a slider that jumps to the finger is no run. `Step.edge` when it reached either end. | `touch_feedback_lvgl.h` for every `lv_slider` and `lv_arc` (a listener goes onto it when a finger first lands on it); `touch_feedback::moved()` for any other |
| A step of a held key | A key held down steps once more. | `touch_feedback::step(direction)` where the key steps |

So a new control needs at most one line, by what it is:

- **An LVGL slider or arc**, anywhere, of the core or of a plugin: nothing. Its range is its own (the core's sliders run
  per mille, a range reaching below 0 to draw a round end counts from 0, a reversed one the other way round).
- **A control dragged by hand** that is no LVGL slider (the player's seek bar, `media_seek_event`): call
  `touch_feedback::moved(object, value, low, high)` on the press and on every move, with the value it shows.
- **A key that repeats while held** (`climate_hold`, the -/+ of a tile's control panel): call
  `touch_feedback::step(direction)` where it actually steps, not on every repeat LVGL sends.

`touch_feedback.h` is free of LVGL (`tests/test_touch_feedback.cpp`); `touch_feedback_lvgl.h` is included by
`plugin_host.cpp` alone and starts listening when the first plugin starts, so a screen without plugins has none of it.
`on_touch` (0.3, the tap as the finger let go) is gone since 0.24: `on_press` is the one moment for a click.

## Waking the screen (0.16)

`tessera::wake(this)` wakes the screen the way Home Assistant's Wake button does. It is for a plugin that senses
someone come: motion in front of a camera, a light coming on, a sound.

Every wake that is not a finger on the glass takes one way, the script `wake_from` in `packages/core.yaml`. Home
Assistant's Wake button runs it, a board's own sensor presses that button (the reTerminal D1001's Wake when moved),
and `tessera::wake` reaches it through `plugin_host::wake`, which the core sets at boot. The log says who woke the
screen (`Wake from plugin <id>`). So a plugin's wake does what Wake does:

- A screen in standby lights up at its brightness, also in the night hours. Its screensaver goes, a Sleep is over, and
  when Back to page 1 came due during standby it lights up on page 1.
- A screen that is on only counts its standby time from now, so it stays on while the plugin keeps sensing someone.
- It is no tap. Back to page 1 keeps counting from the last touch, so waking on every motion holds no card or page 2
  up. A finger on the glass counts as use; a wake does not.
- A board that cannot go dark (`CAN_STANDBY` false) has no standby, so there is nothing to wake.

A plugin that wakes the screen by what it senses:

- has a setting for it, off until someone turns it on: a switch in its `plugin.yaml`, listed under `settings` in its
  manifest. A screen that lights up by itself surprises the people who did not ask for it.
- calls `wake` while it senses someone, also while the screen is on, and at most once every second or two. That keeps a
  lit screen on as long as someone is there, the way an automation that presses Wake on every motion does, without
  filling the log. A plugin that should only light a dark screen, and never keep a lit one on, keeps what `on_standby`
  last said and calls `wake` only while the screen is dark.
- calls it from its own calls on the screen's loop (`on_interval`, `on_message`, a callback of an ESPHome component),
  never from a task of its own: such a task sets a flag that `on_interval` reads.
- leaves the rest to the core. It never runs `wake_display`, `wake_from` or any other script of the core, nor presses
  the Wake button: they are not the plugin API, and their names may change in any release.

## Where a plugin comes from

- **The index** (`tessera-plugins/index.json`): Tessera's own plugins (label Tessera) and entries of `community/`
  (label Community), each pinned to a commit, read when the editor opens and at most every ten minutes (ETag). The
  plugins repository has two branches, as this one has: main for every app, dev for the dev app
  (`Plugins.index_branches`, falling back on main while dev has no index). A plugin that needs what only this dev
  firmware has (a newer plugin API) waits on its dev, where the dev app installs and updates it the ordinary way, and
  goes to its main with the release that brings that firmware ("The release" in docs/RELEASING.md, step 6). An id
  belongs to the repository that first published it (`claims` in the index; a move goes through `transfers.yaml`).
- **A link** (`POST api/plugins/link`): the newest release of any GitHub repository (Community, or Tessera for a
  repository of MaxGramser); a branch to test (Test); a repository without a release, which becomes a test of its default
  branch, so pushing is enough to try a plugin; or a folder in `tessera-plugins/` beside the ESPHome folder (Test).
  Every one but a folder is pinned to the commit it was read at, so what is built is what the editor showed.
  `Plugins.refresh_links` asks for the newest release, or the newest commit of a test's branch, at most every hour and
  offers it as an update; Build again on a branch asks at once (`rebuildTest`, `plugins?refresh=1`). It finds the repository again by GitHub's number of it, so a rename is followed and a new
  repository that takes the old name is never built.
- **An update** is a newer version in the index or of a linked repository (for a test: a newer commit), from the same
  origin: the screen's Plugins tab and the Plugins page offer it, and the build queue takes the screens one by one. A
  screen with more than one update offers "Update all on this screen" (`updateAll`), one request and one build. An
  update keeps what was filled in when the plugin was added. An update whose rights differ from what the person agreed
  to (`permission_hash`) waits for their yes in the editor; the add-on refuses it without (`consent`). A release the
  index blocks leaves the next build of every screen that runs it (`drop_blocked`).

## Where a plugin's code runs

A plugin is two things. Its C++ runs on the screen, with full access to it (the plugins repository's docs/PUBLISHING.md,
"What listing means"). Its ESPHome component's Python, `components/<id>/__init__.py` and what it imports, runs where
the screen is built: in this app's container, when the app builds the screen, as the Python of every external
component of ESPHome does. That build can read and write the Home Assistant config folder the app has
(`homeassistant_config:rw`, where the ESPHome folder is) and reach the network. Two things hold it:

- **The build gets none of the app's own standing.** `Firmware.build_env` hands a build the names and the families the
  build tools read (`firmware.BUILD_ENV_NAMES`, `BUILD_ENV_PREFIXES`: ESPHome, ESP-IDF, PlatformIO, ccache, pip, git,
  Python) and nothing else of the container's environment, never the Supervisor's token or any name that spells one
  (`BUILD_ENV_NEVER`; `tests/test_build_env.py`).
- **A listed plugin's Python does what a component needs.** The plugins repository's `tools/check.py` reads it as a
  syntax tree at every release the index takes: imports of ESPHome and a little of the standard library, files beside
  itself only, no process, environment, network or file of the computer it is built on. Tessera's own plugins keep to
  the same rules. A plugin added with a link or from a folder passes only the app's manifest check: the editor's
  warning names both halves, the screen and the build, before anyone adds one.

## Which plugin

A plugin is known by its id: it lives in the firmware, in the layouts (`plugin:<id>.<tile>`) and in the secrets, so it
never changes. Its origin (`github.com/<owner>/<repo>[/<folder>]`, lowercase, or `folder`) says which plugin of that id
it is. Two screens may run two plugins of one id (a fork, a folder being made): a tile asks with its screen
(`known(plugin, inbox)`), a secret is kept for the origin it was filled in for and never handed to another, and nothing
moves a screen to another origin unless the person switches in the plugin's details (`switch`).

## What comes along

`requires.plugins` names plugins a plugin needs: they come along from the index, the newest that fits the screen.
`requires.features` names features (`plugin_manifest.FEATURES`: speaker, microphone, media player, camera, camera
sensor, Bluetooth), each a promise about one ESPHome id (`ts_speaker`, ...), which a board brings (boards.json
`features`) or a plugin (`provides`). The camera sensor is only a board's (`BOARD_ONLY`): its promise is the board file's
substitution `CAMERA_I2C`, the bus a camera plugin drives the sensor on, and the board powers the sensor itself.
Bluetooth is only a board's as well: a radio for it and the memory to run ESPHome's Bluetooth stack beside the screen.
Its promise is the component `esp32_hosted` in the board's files, an ESP32-C6 beside the chip that does Wi-Fi and
Bluetooth, the same block ESPHome looks for when it decides to run Bluetooth over the C6. Every ESP32-P4 has it; an
ESP32-S3 with an RGB panel never does, its internal memory is spoken for. It follows the hardware, never a list of
boards, so a new board brings it by the hardware file it includes. A
feature the screen lacks comes along with the one plugin that brings it and fits; with several the person chooses
(`providers`), with none the plugin does not fit. One screen has one of each feature. A part with `features` is
offered and built only where the screen has them. `Plugins.plan` says what a change comes to before anything is built
(the editor's "Comes along", the tray's rows); `apply` carries it out in one build and marks what came along (`auto`).
A plugin another one needs only goes together with it, and what only came along is offered to go as well.

## Finding a plugin

The Plugins page has a tab per type, read from the manifest (`plugin_type`: tiles, functions, hardware) and one for
what is in use; the maker's `topics` are the chips under it. What fits none of the screens folds away under the list.
One bar holds the search (what narrows the list shows in it as pills), the tabs, a Filter menu (topics, maker, only
what fits) and the order: most liked by default, `featured.yaml` in the plugins repository breaking a tie, or best
rated, most used, newest, or by name.

## Likes, ratings and counting

What a person shares about plugins, so others find the good ones and a maker sees that the work is used
(`plugin_likes.py`). Each is one per installation of the app, sent only when the person chooses to, under a random key
of the app (not a board's feedback key), and only for a plugin of the index from the index's own origin: one from a
link, a branch or a folder is not the plugin others count.

- **A like** is a heart for any plugin of the index, also one that runs on none of the screens: a thank-you. The heart
  sits on the plugin's card and in its details. The first one asks once that it counts in a public number.
- **A rating** is one to five stars for a plugin one of the screens runs, with its version and the screen's model
  (a board key of `boards.yaml`). The stars card asks for it above a screen five days after that screen first ran the
  plugin (its hello), one plugin at a time and never while the board's own card asks: its picture, its name and maker,
  the stars, and Send and Later. Later asks again after 14 days, a second Later ends it for that plugin; Don't ask again
  (behind the card's menu, with what is shared and the privacy page) ends it for every plugin, until Settings turns it
  on again. After the stars the card offers a heart for four or five, and for one or two the plugin's issues on GitHub,
  filled in with its version and the screen's model. Stars can be given, changed and taken back in the plugin's details
  at any time.
- **Counting** is off until the person turns it on: on the first stars card, on the In use tab, or in Settings. Then,
  like Home Assistant's own analytics for integrations, the app tells the website once a day, and within a minute of a
  change, which plugins of the index its screens have: each id, its version and the screen models. Turning it off
  deletes what was counted there.

The website counts them: a rating shows from three, a home counts while it was seen in the last 30 days, and one home
network adds at most two of each to a plugin (more is held until an administrator looks). It shows them on the
plugin's page there. The plugins repository copies the numbers every hour into `likes.json` (the likes, for apps from
before ratings) and `stats.json` (likes, rating, ratings and homes), and the app reads those from GitHub with the index,
so looking at plugins never asks the website anything. The routes: `PUT api/plugins/<id>/like`,
`PUT api/plugins/<id>/rating` (`{"stars": 1-5 or null, "screen": inbox}`), `POST api/plugins/<id>/ask` (`later`,
`never`, `ask`, `asked_counting`) and `PUT api/plugins/counting` (`{"on": bool}`); the screen's `plugin_ask` in the
inventory is the card, `plugin_sharing` what this app shares.

A plugin can have a picture, `store.png` beside its manifest (the plugins repository's docs/PUBLISHING.md, "The picture
on the Plugins page", and its `tools/store_image.py`). The index names it (`image`), a link finds it in the plugin's
folder, a folder plugin has the file. The editor shows it across the top of the plugin's card and above its details,
through `GET api/plugins/<id>/image` (`plugins.store_image`): the editor's `img-src` is `'self'`, so the app fetches the
file from GitHub at the plugin's commit, checks it is a PNG of at most 1 MB and 2560 x 1440, keeps one per plugin under
`data/images`, and serves it under an address named after the commit, which a browser keeps for a day.

## Pictures on a plugin tile

A plugin never fetches: its tile lays out places (`ui::picture`) and names an address for each (`ui::set_picture`), and
the core takes them the way every picture of the screen comes (docs/PICTURES.md). The places of one card are the parts
of one picture (`tile_picture.h`, `Part`, `set_parts`): the card asks one question with a place for each, from the
card's top left, with its address and its fit (`cover` or `contain`) in the same order (an older app gets the same as
a page of one tile with an `atlas`, `src` and `fit`); the mark of the key is a digest of the places and addresses, so
another address, a place that moved, or the other look is another picture, and the same address again costs nothing.
The app (`Manager.plugin_picture`, `plugin_pictures.py`) answers only for a plugin tile of the screen's layout whose
manifest gives the tile `pictures`, and only addresses the manifest allows: a host of `permissions.network` (as a
fetch, through the plugins' own session: public hosts, no redirects, 2 MB) or, for a tile of an entity, a picture of
Home Assistant's own (`/api/image/serve/`, `/api/image_proxy/`, `/local/`, the paths a map marker takes, with the app's
token), or one of the core's own sources (below). It keeps each picture by address for six hours, paints the places as
it paints every picture (`picture_paint`, `within` is contain on the card's own colour) and serves the atlas as a
still link. On the screen
the atlas is one entry of the store under the tile's key, within the same cap as a camera over the card, and each place
draws its piece of it (`plugin_host::picture_place`); a frame the app had no picture for stays the card's colour, and
an answer without a picture is asked for again later, each time after a longer while (`drawn`). A board without
pictures (no `SCREEN_PICTURES`) has the calls and shows blocks; `ui::pictures()` says so, and a tile lays itself out
without the places. Nothing of this counts in the layout memory: the store's budget and its rule of the picture used
longest ago hold for a plugin's atlas as for every picture.

**Layers, turns and reflections.** The places of one card may overlap: they are its layers, and a place made later
lies over one made earlier. The screen draws them in that order, and the app paints the atlas in the same order
(`picture_paint.picture`): each place over what the ones before it left, on the card's colour where nothing lies yet,
so a rounded corner shows the poster under it. Covers of different tiles still never overlap. A place may
also ask for its picture turned (`tessera::Turn`, `turn` in the question: `left` faces the left, its left edge far) and
with a reflection (`mirror`, the lower `MIRROR_PERCENT` of the place under the picture); the app draws both into the
atlas with Pillow (`picture_paint`), so the screen pays nothing for them. The question names `turn` and `mirror` only
when a place asks for them, and an older app ignores them and draws the pictures flat. A place keeps the picture it
shows while the next one comes (`set_picture` no longer clears it, and `tile_picture_place` keeps the last atlas while
the store holds it), so a cover flow turns without a flash of blocks; the render host with `KEPT_PAGES_HOST=1` has a
picture store of a 4-inch Guition's size, so its renders show every picture of a page as a board with PSRAM does.

**The core's sources (0.17).** Besides a web address, a place may name what the core already shows: `cover:<entity>`,
a media player's cover, `camera:<entity>`, a camera's picture, and `entity:<entity>`, an entity's own picture, each
only for the entity the tile, card or step shows (`picture_sources`, `_plugin_entities`), and `step:`, the screensaver
step's own picture. The app answers them as it answers a tile of that entity: the same
fetching, the same newest frame of a camera's stream while one runs, no permission of the network needed.

**Live (0.17).** A tile's place with the address `camera:<entity>` of its own entity that the tile set live
(`ui::live`) streams on a screen that streams, as a camera tile set to Live does (`runtime_tiles`, live places): while
it is on the glass, the page stands still and nothing lies over it (`drawn_over`; a label over it counts), into the
place's room with its corners and fit, the card's colour around a whole picture. Its question names `live` and the
owner `plugin_tile`, sent only to an app that reads questions, and its answer comes back as `plive` by its number. Until
the camera is live its stills show with the firmware's loader in the place's top right corner, as on a live tile
(docs/CAMERA.md, "Until it is live"); a plugin draws nothing for it. A card's and a saver's places show stills: a card
over the page stops every stream.

**What came (0.17).** A plugin hears whether a place's picture came: `on_picture(place, PictureState)` on its tile, card
or saver, `SHOWN` when it is on the place, `NONE` when the app has no picture at that address now (asked again later,
each time after a longer while), `FAILED` when the download broke off. A place made with `Placeholder::NONE` shows
nothing of its own until then, so places that lie over each other (a cover flow) show no grey bars between pictures; a
plugin that wants a word where no picture came draws it itself on `NONE` or `FAILED`.

**The screen's own camera (0.17).** A plugin that uses the screen's own camera on the screen itself (to sense light or
motion) says so with `tessera::capturing(this, Capture::CAMERA, true)` while it does, and `false` after. The core shows a
small green dot in the top right corner, on the system layer over everything, while any plugin says so or Home
Assistant takes pictures or a stream of the camera (the core hears that by itself on the camera `ts_camera`, which
`register_plugin` binds when a manifest provides `camera`). No plugin and no setting hides it. docs/PICTURES.md,
"Capture", has the rest.

## A screensaver (0.14)

The screensaver is a list of steps in the order the person put them (docs/SCREENSAVER.md): the music that plays, the
photos of a folder, a camera, the clock. ESP Screen Manager picks the first that has something to show; the screen
shows it over the whole glass while Auto standby dims it. A plugin adds to that list in two ways, and never beside it:

- **A face of a step** (`step: clock`, `media` or `photos`): it draws the step the core already has, from the same
  data the core's own face draws from. The person picks it under Face in that step's drawer. A screen that lacks the
  plugin (it left, its build failed, older firmware) shows the step's own face: never a black glass.
- **A step of its own** (`step: own`): a place in the order, from the plugin's fetch (`data`) and its entity
  (`domains`, `attributes`, `fields`, as a tile of an entity), shown while its manifest's `when` holds: `always`,
  `data` (its fetch has an answer) or `{state: [...]}` (its entity is in one of those states).

The core decides when a saver shows: standby at a level above 0, without Sleep from Home Assistant, the cards closed,
no alert. It goes on a wake, an alert, an update (`before_update` first), a level of 0, a new layout or another word.

**A backdrop.** A face of the music or the photos whose manifest says `backdrop: true` has the step's own picture under
it: runtime_tiles opens the full view as Tessera's own face does (the cover, or the photo with its motion), bare
(`saver_bare`: no words, no keys), and lays the saver's glass clear over it (index 1, under an alert). It follows the next
cover or photo as the core's face does (`saver_follow`). The saver draws only what goes over the picture; the drift
moves its stage alone, so a photo that fills the glass never shows a black edge.

**The wire.** The app's word for the step (`op saver`) gains `pf`: `p` the saver (`plugin:<plugin>.<saver>`), `o` its
options and `x` what it draws from. For a step of its own the word is `k: "plugin"` with `pf` alone. `x` is the step's
contract in full words, built by the app (`screen_saver.media_contract`, `clock_contract`, `photos_contract`, or the
plugin's own data), so the short keys of the core's own message can change without a plugin noticing. A field may be
added; within major 0 none is renamed or taken away.

| Step | `x` |
|---|---|
| media | `entity`, `name`, `title`, `artist`, `album`, `state`, `features` (Home Assistant's `supported_features`), `muted`, `volume` (0 to 1), `duration`, `position`, `position_at` (seconds since 1970), `picture` (`step:` while there is a cover), `mark` (the cover's mark), `colour` (`#rrggbb`) |
| clock | `temperature` (`21°`, `""` for none), `items` (`[{icon, text, since?}]`: a codepoint of Tessera's set, its words, or the moment it counts from) |
| photos | `picture` (`step:`), `mark`, `index`, `count`, `album` |
| own | the fetch's answer and the entity's `state`, `name`, `attributes` and fields, as a plugin tile's `x`, and `entity`, the entity chosen for the step: the screen asks for the step's Home Assistant pictures for it, so a field of the fetch's answer called `entity` gives way to it |

**On the screen** (`plugin_host.cpp`, "A plugin's screensaver"): runtime_tiles makes the black glass on LVGL's top layer
(`saver_glass`) and hands it to `plugin_host::saver_show` when `saver_plugin_draws` (the screen has that saver). The
saver draws in a stage over the glass, which the host moves a millimetre along a slow circle every minute
(`saver_view::drift`, the clock faces' rule) unless the manifest says `moves: true` (`Plugin::set_moves`, from
`register_plugin`). Every call of a saver runs in the dark look (`theme::dark` set in `saver_call`), so its roles are
white on black whatever the screen's look. `on_tick` comes from `tick_cards`, so it ticks on boards without pictures
too. A new word for the same saver goes to `on_state` in place (`saver_state`); a finger's wish on the player is laid
over `x` (`state`, `muted`) before the saver hears it. Other options make the saver anew (`saver_sync` compares
`plugin_options`), as a tile's do: it reads its options in `show()`, and the person sees a change at once.

**Taps.** Only parts made with `ui::takes_taps` are clickable (`saver_touch`): a short tap goes to `on_tap` and a hold
of `SAVER_MUTE_HOLD_MS` to `on_hold`, through the touch guard (`rt::allowed`, keys from `SAVER_TOUCH`), and the screen
stays in standby. Everything else of the saver lets the finger through to `dim_wake_overlay`, which wakes the screen,
and `saver_woke` keeps that touch from reaching a tile.

**Pictures.** A saver's places are asked for as a card's (`saver_picture_want`, `SAVER_OWNER`, `Kind::CARD` 2), with
the owner `plugin_saver` and the entity of a step of its own (an older app gets `saver` instead of `card`, `for`, and
answers `psaver`). The address `step:` is the step's own picture: the app answers it
with the cover of the player on the glass or the photo of the photos step (`Manager.saver_picture`), cut to the place. Its key carries the step's `mark`, so the next cover or photo is another
picture under the same address. The store counts a saver's places as on the glass (`card_draws`, `card_letgo`).

**wish().** `tessera::wish(entity, Wish, value)`: for the player on the screensaver `rt::saver_wish` (the core's own
play and mute keys use it too, `saver_wishes`, optimistic.h's rules over the screensaver's word instead of a tile), for
an entity of a tile `rt::wish`, and for any other entity the action alone.

**The hello** lists a plugin's savers (`plugins[].savers`, `page_delivery.plugins_of`); the app offers and sends a face
or step only to a screen that names it and has the plugin in its record (`Plugins.saver_kinds`).

**Tested** by the host probe's three savers (a face of the music with a cover and a key, a face of the clock that
moves itself, a step of its own) in `plugin_round` (`plugin_savers` in tools/render/run.py), and by
tests/test_saver_plugins.py.

## A popup (0.18)

A popup is for a moment that wants the eye now: a voice assistant that listens, thinks and answers, a timer that went
off, a question to answer. It is the card an alert of Home Assistant shows, in the middle of the glass over the alert's
scrim, with what the plugin draws in it.

- **Its size follows the glass and what it says.** The card is as wide as the alert's card on this glass
  (`screen_alert::plain`: the look's size in millimetres, never wider than the glass less its edge), or the glass less
  that edge with `PopupWidth::WIDE`. It is as high as what the plugin puts in its room (`PopupContext::parent`), up to
  `PopupContext::height`, the most this glass gives a card: the plugin lays its parts out from the top, the card grows
  and shrinks with them (a hidden part takes no room) and stays in the middle. A popup that has to fit more than that
  shows its last or first lines, as it chooses; it never scrolls.
- **One at a time, over everything but an alert.** It lies on the top layer over the page, a card, the settings and
  the screensaver (`saver_glass` lies at that layer's bottom); a popup shown while an alert shows goes under the
  alert's overlay, and an alert that comes closes it. Showing another popup replaces it.
- **It lights the screen.** `show_popup` wakes a dark screen as `tessera::wake` does (the log names the plugin; a Sleep
  of Home Assistant is over too), and
  restarts the standby time of a lit one: a popup is something to see. A plugin that shows one unasked, without a
  person in front of the screen, has a setting for it, as a plugin that wakes the screen does.
- **A close key in its corner.** Every popup has the round key of every card's top bar (`detail_bar::key`, its size
  and paint) with the close glyph in the room's top right corner, as far from the card's top and side as the room is.
  It floats over the room; `PopupContext::key` is its size (a plugin's own disc or icon of that size in the top left
  corner stands on one line with it) and `PopupContext::corner` how far the room's first row keeps from the right.
- **How it goes.** Its plugin closes it (`close_popup`) or shows another; it goes by itself on its close key, a tap
  beside the card,
  when the screen goes dark, before an update and when an alert comes, and then hears `on_dismiss` first. A popup may
  close itself in any of its own calls; it leaves the glass at once and is deleted once that call returned, as a card.
- **Taps.** A tap on the card reaches `on_tap` through the touch guard (`rt::allowed`, keys from `POPUP_TOUCH`), with
  `tap_point()` in the room's pixels; the scrim takes every other press, so nothing reaches what lies under it.
- **Moments.** `on_interval` every 250 ms (for words that come one by one), `on_tick` once a second, `on_theme` when
  the look changes (the host paints the scrim and the card itself).
- **Motion.** `ui::animate(part, Motion, period_ms, delay_ms)` makes a part pulse (its opacity), spin (around its
  middle) or ripple (growing by half while it fades), again and again, until `ui::still` or until it is deleted; a
  delay lets parts move one after another. It is for a popup, whose moment is short: the screen draws a moving part
  again in every frame, so a tile, a card and a screensaver stand still, and a part that moves stays small.

The voice assistant (tessera-plugins, `voice_assist`) is the first user: a disc in the colour of where a question is,
rings that ripple out of it while it listens, an arc that turns around it while Assist thinks, what it heard, and the
answer as the speaker says it.

**Tested** by the host probe's popup (`{"do": "popup"}`, `popup_self`, `popup_close`) in `plugin_round`: it shows and
wakes, ticks, takes a tap with its place, goes on a tap beside it and on its close key with `on_dismiss`, by
`close_popup` without it, by itself inside its own `on_tap` (deleted after that call) and when an alert comes, and it
lights a screen in standby.

## What is not built yet

A plugin's own messages beyond Home Assistant commands, Python modules of Tessera's own plugins in the add-on (the
design's `module`), and plugin faces of the camera step.
