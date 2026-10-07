# A finger's change, shown at once

When a finger changes something on a screen, the screen shows the new value at once and squares it with Home Assistant
afterwards. It never waits for Home Assistant before the glass moves, and it never keeps showing a value Home Assistant
did not take. This document is the rule for every control in the firmware that changes a value of an entity, and the
recipe for adding one.

There are two reasons to show a value before Home Assistant confirms it:

1. **Repeated input.** Four taps on + take a thermostat from 16 to 20 degrees. Each tap moves the number at once, and
   only the last value goes out, once the finger rests: a **step**.
2. **Feel.** A speaker takes a second or two to start playing. The play key turns into a pause key the moment it is
   touched, so the screen says it heard you, and the action goes out at that same moment: a **choice**.

Both are one mechanism, the **wish**, in `components/smart_display/optimistic.h`, with its tests in
`tests/test_optimistic.cpp`.

## Home Assistant is the reference

The rules copy what Home Assistant's own frontend does between a tap and the new state:

| Home Assistant | What it does | Here |
|---|---|---|
| `ha-entity-toggle.ts` | flips the switch at once; if no new state came two seconds after the call returned, flips it back | `TAP_HOLD` |
| `hui-mode-select-card-feature-base.ts` (modes, options) | shows the chosen mode at once; puts the old one back when the call fails | a refusal reverts at once |
| `ha-state-control-lock-toggle.ts` | the same for a lock's toggle | (the lock keeps its own confirm flow, see below) |
| `ha-state-control-climate-temperature.ts` | moves the target with each press, sends the last one after a pause (debounce) | a step's quiet |
| `more-info-media_player.ts` | volume slider sends after a short pause while it is dragged | a step's quiet |
| `ha-control-slider.ts` | the slider stays where it was let go until a new state arrives | `Tile::hold_slider` |
| any of them | a new state from Home Assistant replaces what the control shows | Home Assistant decides |

Home Assistant's frontend shows play, pause, shuffle, repeat and mute only after the player reports them. The screen
goes one step further and shows them at once too, with the same rules as a toggle, because a speaker is often slow to
answer.

## The rules of a wish

A wish is one wanted value of one field of one entity (`optimistic::Field`). Its life:

1. **Shown at once.** The value is written into every tile and the open card of the entity. A card that paints itself
   (docs/CARD_PARTS.md) changes only the parts that show the value, in the same frame as the finger; another card is
   built again. Nothing greys out, no busy sheet appears, and the next tap is accepted.
2. **Out.** A choice goes out at the moment of the tap, so a fast Home Assistant is never held back. One action of a
   wish is on its way at a time: taps that come while it is (five fast taps on play) only change what is wished, and
   when Home Assistant has taken the one on its way (its answer, or its report of the value) the last wish goes out,
   and nothing when it is what was sent already. A fast Home Assistant gets nearly every tap, a slow device a whole
   burst as one action, without a timer that guesses. Where Home Assistant gives no answers the next one goes
   `NEXT_UNWATCHED` (400 ms) after the one before. A step (`quiet` in `optimistic::want`) instead goes out once the
   finger rested that long, as Home Assistant's target temperature waits a second for the last press.
3. **Sent.** The action asks Home Assistant for an answer where it can (`watch_call`). A device that takes longer
   than `SLOW_SHOW` (1 s) to come round gets "Updating..." on the tile's second line and on its card, as Apple's Home
   app says for a slow accessory; the wished value stays. A device that answers in time never shows it.
4. **Squared** by whatever comes first:
   - Home Assistant reports the wished value: the wish ends. This is the normal case.
   - Home Assistant reports the value from before the tap: that message left before the action arrived (a Hue room
     reports its lamps first and itself a second later). The wish stays in front.
   - Home Assistant reports any other value: the wish ends and that value shows. A fan that only knows three speeds
     took the nearest one; Home Assistant decides.
   - Home Assistant refuses the action: the old value comes back at once, and the tile says "Refused" for a moment.
   - Home Assistant answers "it worked" but the value does not change within `TAP_HOLD` (2 s): the old value comes back
     quietly, as Home Assistant's toggle does.
   - No answer at all: the old value comes back after `WATCHED_CAP` (9 s) when an answer was asked for, `HOLD_CAP` (3 s)
     when none could be. When Home Assistant's eight-second verdict says it never answered (the screen may not perform
     actions), the tile says so and the screen explains why once, as for any tap.
5. **A refusal ends the burst**: the value from before the first tap comes back, and what was wished after it is
   dropped.

The wish changes the value and what the screen draws from it (a switch's colour, a play key, a progress bar). The icon
Home Assistant gives a tile for a state comes with Home Assistant's next report: it depends on the integration and on
icons Home Assistant answers at runtime, so the screen never keeps a table of its own to guess it.

A control that wishes takes every clean tap (`allowed_wish`, the -/+ keys' guard): the wish folds a burst into one
action, so only a bounce of the same key within 150 ms is dropped. A control that is no wish keeps the 600 ms guard
against a second tap.

What a wish never does: guess a value the screen cannot know. The next track's title, the mode a thermostat returns
to when it is switched on, the state of a player after power on: those wait for Home Assistant, with the tile's busy
sheet (`Tile::begin`).

## Using it

In `runtime_tiles.h`, a control that changes a value calls one function:

```cpp
wish(t, optimistic::Field::OPTION, option, t.domain() + ".select_option", "option", option);
```

- `t`: the tile that was touched. Every tile and the open card of `t.entity` show the value.
- `field` and `value`: what changes, in the field's own words (see the table below).
- `service`, `key`, `data`: the action that makes the value come true, built from what the tile shows now, so a second
  tap in a burst undoes the first. Toggles send `turn_on` or `turn_off`, never `toggle`, and a player's key sends
  `media_play` or `media_pause` where the player has them.
- `target` (optional): the entity the action goes to when it is not the tile's own (a Spotify tile that plays on a
  speaker, `media_entity(t)`).

A control never writes a value into the model itself, never calls `Tile::begin` for a value it wishes, and never keeps
a hold of its own. Helpers that already do it right: `toggle_wish` (on and off), `climate_mode_wish`, `climate_power`,
`key_press` (a key of a tile's key row or mode bar, through `tile_controls::wanted`) and `media_action`.

### Parts of an entity

A field can belong to a part of the tile's entity: a lamp of a light group, a row of a light's effects page, a row of a
vacuum. The wish then names the part as its `item`, and the part is also the action's target:

```cpp
wish(group, optimistic::Field::LAMP_ON, "1", "light.turn_on", "", "", "", "light.desk_lamp");
```

Two lamps of one group are two wishes. The pages over a card (`group_page.h`, `effects_page.h`) call it through their
`wish` hook (`runtime_tiles::wish_part`, wired in `packages/core.yaml`) and paint from the tile, which holds the wished
value; they keep no hold of their own. A value Home Assistant renders itself (a lamp's `hs_color` list) passes
`rendered`.

### On the glass at once

A wish writes its value into the tile and paints every tile and the open card of the entity. A card that paints itself
(docs/CARD_PARTS.md) changes only the parts that show the value, in a few milliseconds; another card is built again.

### The fields

| Field | Value | Read from and written to |
|---|---|---|
| `ON_OFF` | `on`, `off` | the state: lights, switches, input booleans, fans, automations, remotes, humidifiers |
| `OPTION` | the option | the state: select, input_select |
| `HVAC_MODE` | the mode | the state: climate (also `off` from the power key) |
| `HUMIDIFIER_MODE` | the mode | the humidifier's `mode` attribute |
| `FAN_MODE` | the fan mode | a thermostat's `fan_mode` |
| `SWING_MODE` | the swing mode | a thermostat's `swing_mode` |
| `ACTIVITY` | the activity, empty for off | a remote's activity and its state |
| `PLAYING` | `1`, `0` | a player's state (`playing` or `paused`); the progress bar stops or runs on from where it is |
| `SHUFFLE` | `1`, `0` | a player's shuffle |
| `REPEAT` | `off`, `all`, `one` | a player's repeat |
| `MUTED` | `1`, `0` | a player's mute |
| `LAMP_ON` | `1`, `0` | a lamp of a group (`item`: the lamp) |
| `LAMP_LEVEL` | 1-100, `0` for off | a lamp's brightness, and on or off with it |
| `LAMP_HUE` | 0-360 | a lamp's hue, at full saturation (sent as `hs_color`, rendered) |
| `LAMP_KELVIN` | kelvin | a lamp's white shade |
| `EFFECT` | the effect | the effect a light runs |
| `ROW_OPTION` | the option | a select of the light's device (`item`: the select) |
| `ROW_NUMBER` | the number | a number of the light's device (`item`: the number) |
| `VACUUM_ROW` | the choice | a vacuum's mode, suction or water row (`item`: `m`, `s` or `w`) |

### Adding a field

1. Add it to `optimistic::Field` in `optimistic.h`.
2. Read and write it in `wish_read` and `wish_write` in `runtime_tiles.h`, in the same words Home Assistant reports.
   A write that touches more than the value (the progress bar under `PLAYING`) does it there, once.
3. If a key of a tile's key row wishes it, say so in `tile_controls::wanted`.
4. Add it to the table above. `tests/test_optimistic_rule.py` fails while the table and the enum differ.
5. Call `wish()` from the control.

## Where it is used, and where not yet

Through a wish today: the tap on a toggling tile, the toggle key of a wide tile, the switch and power key of a card, a
slider that switches an off lamp or fan on, the options of a select (card rows and a tile's arrows), a thermostat's and
a humidifier's modes (card and the tile's mode bar), a thermostat's fan and swing rows, a remote's activities, a
player's play, pause, mute, shuffle and repeat (card, tile over the whole page, key row and favourite), a vacuum's chips,
every lamp of a light group's lamp page (on and off, brightness, colour, white shade) and every row of a light's effects
page (the effect, the device's selects and numbers).

Not a wish, and why:

- the -/+ of a thermostat or number: a step that already shows at once and goes out once the finger rests
  (`Tile::edit_value`, 700 ms, as Home Assistant's target temperature waits for the last press). It follows the rules of
  a step and can move onto a wish with a `quiet` when it needs to;
- the brightness, fan and volume sliders: they follow a fade towards the value let go (`Tile::hold_slider`), not one
  value, so they keep their own hold;
- the screensaver's play key: it has no tile to write into (`saver_flipped` flips its face for five seconds);
- a player's speaker and input in the library menu: the pill shows the choice at once, and a speaker is picked through
  the add-on (an event), not through an action Home Assistant answers.

Not optimistic on purpose:

- a lock's and an alarm panel's end states: "locked" or "armed" is never shown before Home Assistant says so. Their
  attempt (`alarm_panel::Attempt`) shows that a command is under way instead;
- a cover's, a vacuum's and a timer's commands, which have transitional states of their own (`opening`, `returning`);
  a later round may show those words at once as wishes;
- next and previous track, turning a player or thermostat on, a scene, script or button: nothing the screen could show
  is known before Home Assistant reports it.

## Testing

- `tests/test_optimistic.cpp` runs every rule on the host: bursts, stale reports, refusals, "it worked" without a
  change, silence, slow devices, the clock wrapping around.
- `tests/test_tile_controls.cpp` checks what each key wishes for and which action it sends.
- On a screen, every wish logs under the tag `wish`: the value wished, what Home Assistant said, and every value put
  back. `runtime_action` logs each action sent.
- On the bench (docs/TESTING.md): a demo light, select, climate, remote and media player in the bench Home Assistant,
  tapped by hand, with the screen's log open. The paths that need Home Assistant to misbehave use template switches: one
  whose action fails (a refusal), one whose action does nothing (the two-second hold) and one whose action takes a few
  seconds (a slow device).
