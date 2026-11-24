# Eleven plugins keep their placeholder in the editor: their plugin.yaml makes ESPHome entities

## The symptom
Since 2026-11-24 the editor draws a plugin's tile with the plugin's own code, a module built for the editor's preview
(docs/EMULATOR_ARCHITECTURE.md, "Plugins"). Of the 44 plugins the index listed that day, 28 have a module. Five have
none for a reason that stays: four need or bring hardware (`bt_proxy`, `screen_camera`, `tap_sound`, `voice_assist`)
and one draws nothing (`guition_relays`). Eleven have none because their `plugin.yaml` holds more than the component's
own key:

`waste_collection`, `buienradar`, `pollen`, `scmt`, `tankerkoenig`, `timers`, `waste_overview`, `waze_traveltime`,
`weather_warnings`, `wifi_qr`, `world_clock`.

What a person sees for these eleven is what every plugin showed before: on a page and in the library the editor's own
drawing of a plugin tile (its icon, its name, the striped card), and in Preview the plain card of a plugin the preview
does not have. There is no error. The list of modules says why, per plugin, under `skipped` in
`modules/<number>/index.json` on the plugins repository's branch `modules`: "has ESPHome entities of its own in
plugin.yaml: not shown in the browser yet".

## What we know
- The rule is in `web/wasm/build_plugin.py` (`build`): a plugin whose `plugin.yaml` has any key beside `defaults` and
  `substitutions` with content, or more than the one component key, is not built (`Unfit`, exit 2). A module is the
  component's sources and a generated start that does what `smart_display.register_plugin` does on a screen: identity,
  tile memory, texts, `setup()`. It calls no setter, because it does not run the component's `to_code`.
- One of the eleven is in the plugins repository itself. `waste_collection`'s `plugin.yaml` makes two `homeassistant`
  text sensors (a calendar's `message` and `start_time`), a template switch and a template number, and hands their ids
  and the calendar's entity id to its component. Its `to_code` calls `set_message`, `set_start`, `set_in_bar`,
  `set_days_ahead` and `set_calendar`. Without those calls the component reads null pointers.
- The other ten are community plugins. Their `plugin.yaml` files have not been read: their repositories were not
  fetched to a workstation, only by the plugins repository's workflow, which stopped at the rule above.

## Ruled out
- Guessing the setters from the keys of `plugin.yaml`. `waste_collection` happens to name them alike, but a setter's
  name is the component's own `to_code`, and nothing makes a plugin keep to a pattern.
- Stand-ins without values. A `homeassistant` sensor that never has a state would make the card show the plugin's
  "no data" face on a page where the screen shows data: wrong in a new way, and worse than a placeholder that says
  nothing.

## What the road needs
1. Stand-ins in `web/wasm/host_include` for the ESPHome entity classes a component reads: `text_sensor`, `sensor`,
   `binary_sensor`, `switch`, `number`, perhaps `select` and `time`, each with its state, `has_state()` and its
   callbacks.
2. The component's own `to_code`, run for the preview, so its setters are called as on a screen. That makes ESPHome a
   dependency of `build_plugin.py` and of the plugins repository's workflow: a harness that validates the component's
   block of `plugin.yaml` against its schema, registers the stand-ins under their ids, runs `to_code` with
   `smart_display.register_plugin` replaced by what the module's start already does, and takes the generated
   statements into that start.
3. Values for the stand-ins. A `homeassistant` sensor needs Home Assistant's state or attribute in the editor: a road
   from the add-on to the preview beside the tile packets, on the add-on's entity stream, and an example value for a
   tile in the library (`preview.yaml`). A template switch or number takes its restore default.
4. A plugin whose `plugin.yaml` holds a lambda or an automation needs ESPHome's whole code generation, not a harness.
   Whether any of the ten does is not known.

Estimated at two to three days with its tests, and it adds ESPHome to every module build.

## The deciding experiment
`waste_collection` first, because it is ours and uses the four common kinds (two sensors of Home Assistant, a switch,
a number). It is done when its tile in the editor shows the next collection of the calendar that was chosen, as the
screen does, its top bar item follows the switch, and its module is built by the plugins repository's workflow with
the others. Then read the ten community `plugin.yaml` files and sort them: the same road, or the whole code generation
(point 4). That count decides whether the harness is enough.

## Not known yet
- What the ten community plugins' `plugin.yaml` files hold, and which parts of ESPHome their components include.
- How long ESPHome adds to a module build (the workflow builds all 28 modules in under three minutes today).
- Whether the add-on's entity stream can carry an attribute of an entity to the preview as it stands, or needs a new
  kind of packet.

## Pointers
`web/wasm/build_plugin.py` (`build`, `Unfit`, `glue`), `web/wasm/host_include/`, `web/wasm/toolchain.py`;
the plugins repository's `tools/build_modules.py`, its workflow `modules` and `plugins/waste_collection/`;
`screen_manager/app/plugins.py` (`module`, `modules_on`); docs/EMULATOR_ARCHITECTURE.md, "Plugins", "Known limits".
