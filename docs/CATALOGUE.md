# The tile catalogue

What a tile of each entity type can do lives in one place: `catalogue/`, one YAML file per type. The add-on, the
editor and the screen firmware all read it, so a rule is written once and cannot drift apart between them. Home
Assistant's own facts (feature flags, which action needs which flag) are read from Home Assistant's source code, never
copied by hand.

## How it fits together

```
catalogue/<type>.yaml       our options for one entity type: controls, displays, the small slider, taps, guards
catalogue/_tile.yaml        what every tile has: its taps, its named sizes, the hours a graph shows
catalogue/_ha.json          Home Assistant's facts for every type we have, read from its source (tools/read_ha_source.py)
catalogue/_remote_commands.json  the commands a remote of each integration takes (tools/read_remote_commands.py)
        |
        |  tools/generate_catalogue.py (checks everything, then writes)
        v
screen_manager/app/catalogue.json        read by screen_manager/app/catalogue.py (the add-on)
web/src/model/catalogue.json             read by web/src/model/catalogue.ts (the editor)
components/smart_display/tile_catalogue.h  the firmware: the types it draws, Home Assistant's flags by name
screen_manager/app/remote_commands.json  the add-on: the commands it offers in Send command, per integration
```

At run time the add-on does not guess what a device can do. It asks the user's Home Assistant: the actions Home
Assistant lists for that entity (`get_services_for_target`), the fields of those actions, the entity's
`supported_features`, its attributes and its history. The catalogue only says what each of our options needs, in Home
Assistant's own terms, and the add-on matches the two.

Three questions are answered by the catalogue, the same way in Python and TypeScript:

1. **What may be chosen for an entity** (`offers`): the options of its type whose `needs` the entity meets. The editor
   shows only these.
2. **What a card of a given size draws** (`resolve_controls`): the chosen control or the type's default, and on a card
   one row high what fits there (`one_row`).
3. **What a screen gets** (`drawn_controls`): what that entity can draw (`fallback`) on that screen (`screen`, what the
   screen's firmware says it draws).

`tests/fixtures/catalogue-conformance.json` holds cases the add-on and the editor must answer alike;
`tests/test_catalogue.py` and `web/tests/catalogue.spec.ts` run them.

Code that tests an entity's `supported_features` names the bit as Home Assistant's source does, never by its number:
`tile_catalogue::cover::SET_TILT_POSITION` in the firmware, `catalogue.bits('cover', 'SET_TILT_POSITION')` in the
add-on and `bits('cover', 'SET_TILT_POSITION')` from `model/catalogue.ts` in the editor. `tests/test_feature_bits.py`
fails where shared code compares `supported_features` with a number or defines a feature constant as one. A bit the
catalogue lacks comes from Home Assistant's source through `catalogue/_ha.json`, never from a constant of our own.

## The files are the list of types

A type exists in the add-on, the editor and the firmware only when it has a file in `catalogue/`. Home Assistant has
many more (valve, humidifier, water heater, lawn mower): none of them appears until someone adds its file, and that
comes after the firmware can draw it. `tools/read_ha_source.py` reads Home Assistant's facts only for types that have a
file; it never adds one.

## The keys of a type's file

```yaml
domain: climate               # the file's name without .yaml
firmware: 0.19.0              # the first firmware that draws this type; required for every type added after 0.4.32
memory: {bytes: 700, extras: true}   # what one tile of it keeps in a screen's memory, measured; required (see "memory")
displays:                     # the faces a tile of this type may have, in the order the editor offers them
  standard: {}
  forecast:
    needs: {features: [FORECAST_DAILY]}   # what the entity must have (see "needs")
    wide: true                            # only on a card of two columns or more
controls:                     # direct controls on a card; the first is the default on a card of more than one column
  setpoint:
    needs: {actions: [climate.set_temperature], features: [TARGET_TEMPERATURE, TARGET_TEMPERATURE_RANGE]}
    range:                                # a variant: when it holds, the screen needs more
      when: {features: [TARGET_TEMPERATURE_RANGE], unless: {features: [TARGET_TEMPERATURE]}}
      screen: {feature: climate_range, else: none}
    fallback: none                        # what is drawn when the entity lacks the features
  setpoint_mode:
    of: [setpoint, mode]                  # a pair: offered when both parts are; drawn as the part that is left
    rows: 2                               # needs a card two rows high
    screen: {firmware: 0.3.1}             # a hard requirement: the add-on asks for this firmware first
    one_row: setpoint                     # what a card one row high draws instead
inline:                       # the small slider beside the name
  needs: {actions: [{action: light.turn_on, field: brightness_pct}]}
toggle: {actions: [lock.lock]}   # what On / off as a tap needs; without this key: <domain>.toggle listed by Home Assistant
taps: [run]                   # taps of this type beyond every tile's
guards: [confirm, lock_only]  # a lock's guard choices
picture: {fit: [...], overlay: [...], refresh: [...]}   # how a live picture sits on its tile
map: {framing: [...], distance: [...], ...}             # a map card's choices, the first of each the default; needs the map display (docs/MAP.md)
keypad:                       # a remote's card: per integration, the command each key sends
  apple_tv: {up: up, down: down, left: left, right: right, ok: select, back: menu, ...}
key: false                    # may not stand as a key under the bedside clock
favorite:                     # what a favourite sets as it starts, each where the player meets its needs; needs the favorite display
  shuffle: {needs: {actions: [media_player.shuffle_set]}}
```

A control may also say `sizes: {full: false}` (not on a full-page card), and the keys of an option are `needs`,
`screen`, `sizes`, `wide`, `rows`, `of`, `one_row`, `fallback` and `range`; `tools/generate_catalogue.py` refuses any
other key (`TOP`, `OPTION`). A `keypad` has up, down, left, right and OK for every integration it names and the other
keys (`back`, `home`, `play`, `volume_up`, `volume_down`, `mute`) where the remote has them, and every command must be
one `catalogue/_remote_commands.json` lists for that integration.

**`memory`**, required in every type's file (firmware 0.34.0+): what one tile of the type keeps in the memory inside a
screen's chip, in bytes, measured on a board with PSRAM, and whether it keeps a block of extras (a forecast, a
thermostat's modes, a player's sources). It is the type's price in the screen's memory budget: the firmware, the add-on
and the editor all count a layout with it (docs/TILE_MEMORY.md says how to measure it and how a board without PSRAM adds
the tile itself and its extras). `catalogue/_tile.yaml` says what a tile's own choices add (`memory: {action, line}`).
`tools/generate_catalogue.py` refuses a type without it, so a new type cannot leave the budget guessing.
`catalogue/screen.yaml` may also give one of the screen's own cards a price of its own (`cards: {energy: {bytes,
extras}}`), counted by its entity (`screen.energy`) before the type's: the energy card keeps far more than a clock.

**`needs`**, what an entity must have:

- `actions`: any one of these actions listed by Home Assistant for the entity, optionally with a `field` Home Assistant
  offers for it.
- `features`: any one of these flags, checked where Home Assistant reports the entity's features. An entity that
  reports none (one that is unavailable) keeps what it may have.
- `attributes`: attributes that must be present.
- `history: line`: a history of numbers (a status sensor has none).
- `unless`: holds when this does not.

A variant's `when` is stricter than `needs`: it only holds on features Home Assistant does report.

**`screen`**, what a screen must have: `firmware` (a version), `feature` (a name in the list its hello message sends),
`pictures` (a board that draws pictures). With `else`, an older screen gets the `else` instead and nothing waits. Without
`else`, the requirement is hard: the add-on asks for a firmware update before it sends a layout that uses the option.

Every action and every feature a file names must be one Home Assistant has for that type (`catalogue/_ha.json`), every
control needs its words in the translations (`addon.labels.controls.<type>.<key>`), and every option another one names
must exist. `tools/generate_catalogue.py` stops on anything else.

## Adding an entity type

1. **The firmware first**: how a tile and its card draw the type (`components/smart_display`), with tests.
2. **The editor's mockup**: how the tile looks in the editor (`web/src/components/TileCard.vue`).
3. **Home Assistant's facts**: make sure `catalogue/_ha.json` has the type (see below).
4. **The file**: `catalogue/<type>.yaml` with `firmware:` set to the version from step 1, its displays and controls,
   its `memory` measured on the bench as docs/TILE_MEMORY.md says, and the words of its controls in
   `screen_manager/translations/en.json` (then the other languages).
5. Run `tools/generate_catalogue.py`, `python tests/catalogue_conformance.py`, `python tests/memory_conformance.py`, add a case to `KINDS` in
   `tests/test_layout_audit.py` (it fails until the type has one, or an `EXCLUDED` entry with the reason the preview
   cannot draw it), and run `tools/check.sh`.

### What a new type touches

The remote tile (firmware 0.22.0, with its keypad and its commands per integration) touched all of these. A file
marked *generated* is written by the tool named and never edited by hand.

- **Firmware** (`components/smart_display`): `runtime_tiles.h` draws the tile and its card (`icon_for`, the palette's
  lists, which taps open a card), `runtime_model.h` holds any new state field, `page_receiver.cpp` reads the new
  attributes, and `tile_controls.h` has hand-written domain lists (toggle, colour). Tests in `tests/test_tile_controls.cpp`
  and a C++ test of the card's layout.
- **Catalogue**: `catalogue/<type>.yaml`; `catalogue/_ha.json` (generated by `tools/read_ha_source.py`). A type that
  needs a new key of its own (as `keypad` and `map` did) adds it to `TOP` in `tools/generate_catalogue.py` and reads it
  in `screen_manager/app/catalogue.py`. `tools/generate_catalogue.py` then writes its four outputs (generated, see "How
  it fits together").
- **Add-on** (`screen_manager/app`): the attributes the screen needs in `ATTRS` in `core.py`; `DOMAIN_ICONS` and the
  domains `accent()` treats as on in `header_bar.py`; the default icons in `tile_icons.py` (`HA_DEFAULTS`, `DEFAULTS`,
  which mirrors the firmware's `icon_for`, and `BIG_GLYPHS`). Then `tools/generate_icons.py` (generated: the glyph lists
  in `packages/core.yaml`, `web/src/assets/tile-icons.woff`, `components/smart_display/tile_icon_names.h`) and
  `tools/generate_page_rules.py` (generated: `web/src/model/page-rules.json`, held by `tests/test_page_conformance.py`).
- **Editor** (`web/src`): `components/Library.vue` (`FILTERS` and `tone()`), `components/TileCard.vue` (`isOn`,
  `status`), `model/layout.ts` (`domains`), `model/tile-palette.ts` and `model/tall-controls.ts` (their domain lists).
  Then `npm test && npm run build`, and commit `screen_manager/app/static` (generated) with it.
- **Translations**: in every full language under `screen_manager/translations/` (`tools/i18n.py check` fails on a
  missing key): `addon.labels.controls.<type>.<control>`, `editor.library.filters.<type>` and `editor.domains.<type>`.
- **Firmware preview** (generated): `web/wasm/generate_renderer_manifest.py --check` fails once the firmware sources
  moved; `sh web/wasm/build.sh` rebuilds it, or `.github/workflows/preview.yml` does on the branch (docs/RELEASING.md).
- **Tests**: a `KINDS` case in `tests/test_layout_audit.py`; `tests/catalogue_conformance.py` rewrites
  `tests/fixtures/catalogue-conformance.json` (generated); a `tests/test_<type>_tiles.py`; and the existing tests that
  list domains by hand. A render stage in `tools/render/run.py` when the card has a moment worth drawing.
- **Release**: `tools/affected_boards.py`, then the shared firmware number (`SCREEN_FIRMWARE_VERSION` in
  `packages/core.yaml`, `FIRMWARE_VERSION` in `screen_manager/app/core.py`), `tools/generate_board_shapes.py`,
  `screen_manager/config.yaml` and the CHANGELOG (docs/BOARD_RELEASES.md, "A shared fix or feature"); the user docs
  that list the tile types (README_EXTENDED.md, docs/EASY_SETUP.md).

## When Home Assistant changes

Home Assistant's code is written in Python 3.14, so the reader runs under it:

```sh
git clone --depth 1 https://github.com/home-assistant/core /tmp/ha-core
uv run --no-project --python 3.14 python tools/read_ha_source.py /tmp/ha-core
git diff catalogue/_ha.json
```

A remote's commands are read the same way, from Home Assistant and the exact library versions its integrations pin
(fetched from PyPI into `.esphome/remote-libs/`):

```sh
python3 tools/read_remote_commands.py /tmp/ha-core
python3 tools/generate_catalogue.py
git diff catalogue/_remote_commands.json
```

Each integration has one rule in that script that names where its remote.py looks a command up. A rule that finds
nothing stops the script: read that integration's remote.py again.

The diff is exactly what Home Assistant changed for our types: a new flag, an action that asks another flag, one that
is gone. `tools/generate_catalogue.py` then says which of our options name something that no longer exists.
`tools/check.sh` runs the same comparison when `HA_CORE` names a checkout. CI has none, so
`.github/workflows/ha-source.yml` does it once a week (and by hand, with any tag or branch) against the newest Home
Assistant release: a sparse clone of only the files the two readers open, both `--check`s, and the diff in the run's
summary when one fails. It passes `--release`: a snapshot taken from a dev build ahead of that release may know more,
which the summary lists, and only what the release has that the snapshot lacks or contradicts fails
(`tools/ha_release.py`). A remote's commands are compared with `--ignore-pins`, without the library versions they were
read from. Without the flags the comparison stays exact, as `tools/check.sh` runs it.

## Updating keeps what people have

`tests/test_compat_0431.py` runs every tile the app of 0.4.31 could save (every type, size and option, on three grids)
through this app and compares with what that release stored and sent (`tests/fixtures/compat/golden-0.4.31.json.gz`):
every saved page loads, compiles to the same tiles, asks no newer firmware and keeps every setting, and a screen that
is not updated gets what it got before, apart from a listed, intended fix. `web/tests/compat-0431.spec.ts` checks the
editor loads the same pages. A change to the catalogue that breaks a saved layout fails these tests.
