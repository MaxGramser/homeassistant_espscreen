# Plugins

A plugin adds something to the screens a person chooses, without the core knowing that plugin exists: a tile with data
from a web service, hardware on one board, a feature not everyone needs. How to make one is in the plugins repository,
[github.com/MaxGramser/tessera-plugins](https://github.com/MaxGramser/tessera-plugins) (its `docs/` and `AGENTS.md`).
This page is the core's side: what the firmware, the add-on and the editor do, and the rules a change here keeps.

Plugins are on in every app since 0.4.87 (the plugin API is 0.13 now); before, only in the dev app.
`core.plugins_enabled()` is the one switch: false takes the Plugins page, its routes and its loops out of the app.

**The API's number.** A plugin builds on every core with the same major and at least its minor. From 1.0 on that is a
promise: a minor only adds, only a break raises the major. Major 0 is the time before the promise: a minor may still
change a name or a signature while the API settles (0.4 renamed `Plugin::on_tick` to `on_interval`), and Tessera's own
plugins move with it in the same release. Such a minor goes into `PLUGIN_API_BREAKS` (`plugin_manifest.py` and
`__init__.py`, a test keeps them equal): a plugin written before it does not fit a core after it, and its build says so in
one sentence instead of a compiler error (`api_fits`; the plugins repository's check uses the same rule). A minor that only
adds is not listed, so a 0.10 plugin builds on 0.11. A test keeps the number equal in `plugin_api.h`, `__init__.py`,
`plugin_manifest.py`, this page and the host probe's manifest.

## The pieces

| Where | File | What |
|---|---|---|
| Firmware | `components/smart_display/plugin_api.h` | What a plugin uses: `tessera::Plugin`, `tessera::Tile`, `TileContext`, the drawing helpers, the clock. The API's version, `PLUGIN_API_MAJOR/MINOR`. |
| Firmware | `components/smart_display/roomy.h` | Memory that takes PSRAM first: `roomy::Text`, `roomy::List`, the allocator behind `tessera::Text`, `tessera::List` and the plugin host's documents (below, "Rules a change keeps"). |
| Firmware | `components/smart_display/plugin_host.h`, `plugin_host.cpp` | The core's side: the register, a plugin tile in a card, its places for pictures, the moments, the hello. |
| Add-on | `screen_manager/app/plugin_pictures.py` | The pictures of a plugin tile (0.10): the question, where a picture may come from, the cache by address, the atlas. |
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
   twelve options of its own, each a short text, a number, true/false, a pick or a list (0.12, "Values of JSON" below),
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
| An action of several fields | `tessera::action(service, entity, fields)`: a JSON object of up to 16 fields, together 1 KB. Texts go in the action's `data` as they are; every other value in `data_template` as the Python literal Home Assistant's ESPHome integration reads back into its type (`helpers/template`, `_parse_result`), with a brace in a text written `\x7b`/`\x7d` so nothing a plugin sends is ever a template. Through the screen's own route, as a tap's: the entity's tiles wait for the answer; `entity` "" for an action whose fields name their own target. | `plugin_action.h` (pure, `tests/test_plugin_action.cpp`), `plugin_host.cpp`; the render harness checks what Home Assistant gets |

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
| The moments | `on_ready`, `on_interval` (every 250 ms; `on_tick` before 0.4), `on_standby`, `before_update`, `on_cards_closed`, `on_alert`, `on_touch` (0.3: every tap `screen_input::TouchGuard` takes, through `screen_hooks::touched()`), `on_press` and `on_step(Step)` (0.11, "Touch feedback" below) | | |
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
`on_touch` (0.3) stays what it was: the tap the touch filter took, as the finger lets go.

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

## Finding a plugin, and likes

The Plugins page has a tab per type, read from the manifest (`plugin_type`: tiles, functions, hardware) and one for
what is in use; the maker's `topics` are the chips under it. What fits none of the screens folds away under the list.
One bar holds the search (what narrows the list shows in it as pills), the tabs, a Filter menu (topics, maker, only what fits) and the order: most liked by default, `featured.yaml` in the plugins repository breaking a tie, or newest, or by name. A like is a heart a person gives a plugin of the index
that runs on one of their screens (`plugin_likes.py`): it goes to the Tessera website with a random key of this app
installation, only on a tap and after one yes that it counts in a public number; the plugins repository copies the
counts into `likes.json` every hour, which the app reads from GitHub.

A plugin can have a picture, `store.png` beside its manifest (the plugins repository's docs/PUBLISHING.md, "The picture
on the Plugins page", and its `tools/store_image.py`). The index names it (`image`), a link finds it in the plugin's
folder, a folder plugin has the file. The editor shows it across the top of the plugin's card and above its details,
through `GET api/plugins/<id>/image` (`plugins.store_image`): the editor's `img-src` is `'self'`, so the app fetches the
file from GitHub at the plugin's commit, checks it is a PNG of at most 1 MB and 2560 x 1440, keeps one per plugin under
`data/images`, and serves it under an address named after the commit, which a browser keeps for a day.

## Pictures on a plugin tile

A plugin never fetches: its tile lays out places (`ui::picture`) and names an address for each (`ui::set_picture`), and
the core takes them the way every picture of the screen comes (docs/CAMERA.md, "A picture per tile"). The places of one
card are the parts of one picture (`tile_picture.h`, `Part`, `set_parts`): the card asks `esphome.screen_camera` as a
page of one tile, with an `atlas` of the places' frames from the card's top left, `src` their addresses and `fit`
(`cover` or `contain`) in the same order; the mark of the key is a digest of the places and addresses, so another
address, a place that moved, or the other look is another picture, and the same address again costs nothing. The app
(`server.answer_plugin_pictures`, `plugin_pictures.py`) answers only for a plugin tile of the screen's layout whose
manifest gives the tile `pictures`, and only addresses the manifest allows: a host of `permissions.network` (as a
fetch, through the plugins' own session: public hosts, no redirects, 2 MB) or, for a tile of an entity, a picture of
Home Assistant's own (`/api/image/serve/`, `/api/image_proxy/`, `/local/`, the paths a map marker takes, with the app's
token). It keeps each picture by address for six hours, paints the frames as it paints every tile picture
(`tile_art.encode`, `within` is contain on the card's own colour) and serves the atlas as a still link. On the screen
the atlas is one entry of the store under the tile's key, within the same cap as a camera over the card, and each place
draws its piece of it (`plugin_host::picture_place`); a frame the app had no picture for stays the card's colour, and
an answer without a picture is asked for again later, each time after a longer while (`drawn`). A board without
pictures (no `SCREEN_PICTURES`) has the calls and shows blocks; `ui::pictures()` says so, and a tile lays itself out
without the places. Nothing of this counts in the layout memory: the store's budget and its rule of the picture used
longest ago hold for a plugin's atlas as for every picture.

**Layers, turns and reflections.** The places of one card may overlap: they are its layers, and a place made later
lies over one made earlier. The screen draws them in that order, and the app paints the atlas in the same order
(`tile_art.layers`): each frame over what the ones before it left, on the card's colour where nothing lies yet, so a
rounded corner shows the poster under it. Covers of different tiles still never overlap (`tile_art.parse`). A place may
also ask for its picture turned (`tessera::Turn`, `turn` in the question: `left` faces the left, its left edge far) and
with a reflection (`mirror`, the lower `MIRROR_PERCENT` of the place under the picture); the app draws both into the
atlas with Pillow (`tile_art.layer`), so the screen pays nothing for them. The question names `turn` and `mirror` only
when a place asks for them, and an older app ignores them and draws the pictures flat. A place keeps the picture it
shows while the next one comes (`set_picture` no longer clears it, and `tile_picture_place` keeps the last atlas while
the store holds it), so a cover flow turns without a flash of blocks; the render host with `KEPT_PAGES_HOST=1` has a
picture store of a 4-inch Guition's size, so its renders show every picture of a page as a board with PSRAM does.

## What is not built yet

A plugin's own messages beyond Home Assistant commands, Python modules of Tessera's own plugins in the add-on (the
design's `module`), and pictures on a plugin's card over the page (the places exist for tiles only).
