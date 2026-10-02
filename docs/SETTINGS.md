# Settings: on the screen, in Home Assistant and in Tessera

Every screen setting can be changed in three places: the **settings page on the screen itself**
(firmware 0.2.44+), its **entity in Home Assistant** (firmware 0.2.49+), and the **Screen settings**
panel of the add-on editor. This page says who owns a value, what the page is made of, and exactly what
adding one more setting takes.

## Who owns a setting

**Firmware 0.2.49 and newer: the screen.** It keeps every value in its own preferences and offers each one
as an entity in the *config* category of its ESPHome device. The settings page, an automation and Tessera
all change a value through `settings_screen::set()`, so they never disagree, and nothing has to catch up
after Tessera or Home Assistant was away. Tessera reads the values from Home Assistant's states,
changes them with the entity's own action, and leaves them out of the layout message.

| Row on the screen | Entity | Key in Tessera |
|---|---|---|
| Brightness | `number.<screen>_normal_brightness` | `brightness` |
| Dark mode (0.2.54+) | `switch.<screen>_dark_mode` | `dark_mode` |
| Auto standby | `switch.<screen>_auto_standby` | `standby_enabled` |
| Standby after | `number.<screen>_standby_after` | `standby_seconds` |
| Standby brightness | `number.<screen>_standby_brightness` | `standby_brightness` |
| Screen on in standby (backlight without levels) | `number.<screen>_standby_brightness` (0 or 100) | `standby_brightness` |
| Night mode | `switch.<screen>_night_mode` | `night_enabled` |
| Starts, Ends | `time.<screen>_night_starts`, `time.<screen>_night_ends` | `night_start`, `night_end` |
| Night brightness | `number.<screen>_night_brightness` | `night_brightness` |
| Screen on at night (backlight without levels) | `number.<screen>_night_brightness` (0 or 100) | `night_brightness` |
| Back to Home, After | `switch.<screen>_back_to_page_1`, `number.<screen>_back_to_page_1_after` | `auto_home`, `auto_home_seconds` |
| Also on standby | `switch.<screen>_back_to_page_1_on_standby` | `home_on_standby` |
| Swipe between pages | `switch.<screen>_swipe_between_pages` | `swipe_pages` |
| Page buttons (0.2.69+) | `switch.<screen>_page_buttons` | `page_buttons` |
| Show home button (0.2.100+) | `switch.<screen>_show_home_button` | `home_button` |
| Rotation | `select.<screen>_rotation` | `rotation` (0.2.80+ on every board: a half turn on any glass, the quarter turns as well on a square one) |

The row on the screen and in the editor says Back to Home; its three entities keep the names
"Back to page 1", "Back to page 1 after" and "Back to page 1 on standby", which `SETTING_ENTITIES` and
`OWNED_SETTINGS_MARKERS` match on. Don't rename them.

Not every board has every row. A board whose screen cannot go dark (`CAN_STANDBY` false: the Waveshare 4.3 and
7 inch) has no Auto standby, Standby after, Standby brightness, Also on standby or Night group, on the screen, in
Home Assistant or in Tessera. A board whose backlight takes no levels (`BACKLIGHT_DIMMABLE` false) has no
Brightness row and shows Standby and Night brightness as the Screen on in standby and Screen on at night toggles,
which write 0 or 100 to the same keys.

The 12 or 24-hour clock was a row and an entity of its own (`switch.<screen>_24_hour_clock`) from firmware 0.2.49 to
0.2.75. Since app 0.2.90 and firmware 0.2.76 it is one setting for every screen, with the language and the number format:
Settings → Language & region in Tessera, which sends `clock_24h` and `numbers` in the layout message.

The first four entities and Auto standby existed before 0.2.49; Tessera recognizes a screen that owns
its settings by one of the others (`OWNED_SETTINGS_MARKERS` in `core.py`). Dark mode came with firmware 0.2.54:
a screen without its switch shows no Dark mode row in Tessera, and firmware that gets its settings with the
layout never gets it at all. What Dark mode changes on the glass is in [docs/THEME.md](THEME.md).

**Older firmware: Tessera.** The values travel in the layout message: `settings`, the frozen block of
eleven keys, with `swipe_pages`, `auto_home`, `auto_home_seconds` and `rotation` as keys of their own. A
change on the screen comes back as an `esphome.screen_setting` event, which Tessera stores with the
layout without sending it back.

## What the user sees

A swipe down from the top edge of the glass opens the page from anywhere, over a card too (firmware 0.28.0+, the edge
swipe in `runtime_tiles::touch_input`). Holding the top bar of the overview for about one and a half seconds opens it
as well; a line in the accent colour grows along the top edge while you hold, and letting go before it finishes
cancels. Both follow **Swipe between pages** for the swipe and `settings_screen::may_open` for the rest. A screen can also carry a
`screen.settings` tile, which opens the page with or without Home Assistant, and Home Assistant can open it
with `esphome.<screen>_open_settings`.

The page is a menu of groups, each of which opens a page of its own:

| Group | Rows |
|---|---|
| Brightness | Brightness (dimmable backlight), Dark mode, Auto standby, Standby after, Standby brightness or Screen on in standby (boards that can go dark) |
| Night (boards that can go dark) | Night mode, Starts, Ends, Night brightness or Screen on at night |
| Screen | Back to Home, After, Also on standby (boards that can go dark), Swipe between pages, Page buttons, Show home button, Rotation |
| This screen | Screen, Address, Firmware, Home Assistant, Calibrate touch (a resistive panel that has a wizard), Restart |

Every change is stored on the screen, applied at once and published on its entity, so Home Assistant and
Tessera show it within a second. The editor's **Screen settings** panel has the first three groups as
cards with the same rows: a switch for a toggle, `-` and `+` that repeat while held, chips for the
rotation. A screen whose device has a Calibrate touch button also gets a This screen card with that button.
The 12 or 24-hour clock is not on this panel: it is Settings → Language & region, for every screen. A change there applies at once, without Save. An offline screen shows its values as
unknown and takes no changes until it is back.

## The rules the page follows

- **Two levels, never three.** A group page is the deepest place a setting can live.
- **No free scrolling.** A group that does not fit gets the same pager as the tile pages: a chevron in each
  half of the bar and a dot per page between them (firmware 0.2.69+). How many rows fit is measured on
  the glass (`fitting_rows()` in `settings_screen.h`): a 320x240 board shows five rows, a 480x480 board six;
  with the pager four and five.
- **A row is a control, not a form.** Toggles flip on tap, numbers and times have `-` and `+`, a choice
  cycles through its options in a chip on the right.
- **A row that depends on a switch above it is greyed out, not hidden**, so the page never jumps around.
- **Only settings that belong to this piece of glass.** Tiles, the top bar and pages belong to the editor,
  which has a mouse and a keyboard; the screen gets what you want to change while standing in front of it.

## Adding a setting

The example below adds "Beep on touch" (`beep`), a switch. Every firmware that has it also owns its
settings, so a new setting never travels in the layout message.

### 1. Where the value lives

- `screen_settings::Settings` in `components/smart_display/screen_settings.h` is the **frozen** block of
  eleven values that Tessera sends older firmware as `settings`. Its format is version 1 and changing it
  needs a preference migration *and* firmware-version gating in the add-on, because older firmware refuses a
  `settings` object that does not have exactly its own keys. Don't.
- Anything new is a plain value in `settings_screen.h` next to `swipe_pages`, `rotation` and `auto_home`,
  with a preference record of its own: load it in `runtime_tiles::load_settings()` and write it in
  `persist_settings()`.
- Every preference key in use stays what it is: `0x53435231` the frozen block, and one key each for swipe,
  Back to Home (`HomeTimeout`, two uint32), dark mode, page buttons, number format, rotation and the alarm lock
  (`runtime_tiles.h`), and the CYD's calibration (`0x43594403`, `cyd_calibration.h`). Never reuse, renumber or
  reshape an existing key's record without a migration; a new value gets a new key.

```cpp
// settings_screen.h, next to the others
inline int32_t swipe_pages = 0, rotation = 0, auto_home = 1, auto_home_seconds = 120, dark_mode = 0, page_buttons = 1, beep = 0;
```

### 2. The one write path, and the row

`settings_screen::set(key, value)` is where every writer ends up. Give the key a branch that clamps it the
way the page steps it, and add the value to the before/after comparison at the bottom, so a value the screen
already has is not stored, applied or reported again:

```cpp
else if (key == "beep") reported = beep = flag(value);
```

Then one line in the table of the group it belongs to. A row's label is a key into the screen's language
(`screen.settings` in `screen_manager/translations/en.json`, turned into `screen_text_keys.h` by `tools/i18n.py`),
not a string:

```cpp
toggle(screen_text::txt::settings_beep, []() -> int32_t { return beep; }, [](int32_t value) { set("beep", value); }),
```

`set()` calls `changed(key, value)`, which stores, applies and reports in one go; `key` must be the add-on's
key exactly. The row kinds are `toggle`, `number` (fixed step, optional unit), `duration` (seconds, steps
grow with the value), `moment` (minutes since midnight, quarters by tap and hours while held), `choice`,
`info` and `action`. A row can carry `shown` (leave it out on boards that lack the hardware) and `enabled`
(grey while the switch it depends on is off).

An `action` is not a setting: it runs something and stores nothing, so it has no key, no entity of its own in
`SETTING_ENTITIES` and no line in `SETTING_RULES`. It takes the glass away for a while, so it names the words it
asks first and shows them in place on the first tap, and it calls a hook the board binds
(`restart_device`, `calibrate_touch`) instead of doing the work itself. Where the add-on offers the same action,
it presses the screen's own entity for it: `Calibrate touch` is a button on the device, and the button being
there is also how the app knows this screen has a wizard at all (`core.calibrate_entity`).

Watch the count: a group of more than five rows gets a pager on a 320x240 board. Six is the maximum
that still fits a 480x480 board in one go. The Screen group already has seven rows.

### 3. The entity

In `packages/core.yaml`, which every board builds from, with the same name as the row:

```yaml
switch:
  - platform: template
    id: setting_beep
    name: "Beep on touch"
    entity_category: config
    restore_mode: DISABLED
    lambda: 'return settings_screen::beep != 0;'
    turn_on_action:
      - lambda: 'settings_screen::set("beep", 1);'
    turn_off_action:
      - lambda: 'settings_screen::set("beep", 0);'
```

The screen's preferences hold the value, so the entity reads it in a lambda instead of keeping a copy
(`restore_value` cannot be combined with a lambda). A switch publishes its own changes. A number, time or
select takes `update_interval: never` and one line in `apply_screen_settings`, which publishes it when it
differs; that script runs after every change and on every Home Assistant connection (the time sync), so the
entity has a value before Home Assistant reads the states. A setting only some boards have is hidden
by a board fact rather than written into one board file: `shown` on the row, and on the entity the
`internal` switch that `packages/features/backlight-always-on.yaml` uses for `CAN_STANDBY` (docs/PROFILES.md).

### 4. The add-on

- `screen_manager/app/core.py`: one line in `SETTING_RULES` (`'beep': (False, None, None)`) for validation,
  one in `SETTING_ENTITIES` (`'beep': ('switch', 'Beep on touch')`, the entity name exactly as in
  `packages/core.yaml`), and the key in `SETTINGS_BESIDE_BLOCK` so it never enters the frozen block.
- `screen_manager/app/server.py`: `settings_view` already leaves a key out for a screen whose device has no
  entity for it. Leave it out for a screen that does not own its settings too (`owner` `'layout'`), as
  `dark_mode` and `page_buttons` are: such firmware cannot have it.
- `web/src/store.ts`: one row in `SETTING_GROUPS`; its label is `editor.screen_settings.rows.<key>` in
  `screen_manager/translations/en.json`, in the words the screen uses; then build the editor
  (`cd web && npm test && npm run build`, AGENTS.md).
- `screen_manager/app/claude_skill.py`: a row in the table of screen entities.
- `screen_manager/app/core.py`: a `<KEY>_MIN_FIRMWARE` constant with the first firmware that has the setting, such
  as `HOME_BUTTON_MIN_FIRMWARE = '0.2.100'`. The skill's row prints it ("Firmware X or newer"), and the tests hold it
  at or below `FIRMWARE_VERSION`. It gates nothing by itself: an older screen is kept from the key by `settings_view`
  (no entity on the device, or the list of keys left out for owner `'layout'`).
- The words in every full language under `screen_manager/translations/`, not only `en.json`:
  `screen.settings.<key>` for the row on the screen and `editor.screen_settings.rows.<key>` for the editor.
  `tools/i18n.py check` fails on a missing key, and `tools/i18n.py header` writes
  `components/smart_display/screen_text_keys.h` and `tests/screen_text_en.h` from them (both generated).

### 5. Tests and proof

- `tests/test_settings_screen.cpp` (`clang++ -std=c++17 -Wall -Wextra -Werror -I.`) walks every page and
  every row, and checks `set()`: add the key to its table of clamps.
- `tests/test_screen_owned_settings.py` checks the entities in both profiles, `SETTING_ENTITIES`, the editor
  rows (labels, steps and the duration ladder against `settings_screen.h`) and the add-on's calls;
  `tests/test_settings_view.py` and `tests/test_layout.py` cover the rest of the add-on side.
- Look at it before believing it: `tools/render/run.py <board>` builds the real firmware of a board as a program
  for this computer (`tools/render/host.py`, SDL2) and drives it over its API (docs/TESTING.md). It renders the
  tile pages, the cards and the alerts, not the settings pages, so walk every settings page on a screen as well,
  in English and in one long language. The host build takes its time from the computer instead of Home Assistant
  (`time: platform: host`).

### 6. Release

A setting is firmware, so it is a shared release (docs/BOARD_RELEASES.md, "A shared fix or feature"): the next
shared number from `tools/affected_boards.py` in `packages/core.yaml` and `FIRMWARE_VERSION`, `screen_manager/config.yaml`
and the CHANGELOG. `settings_screen.h` is part of the firmware preview's sources, so the preview is rebuilt
(`sh web/wasm/build.sh`, or `.github/workflows/preview.yml` on the branch). The user docs that list the settings follow:
the tables at the top of this page, README_EXTENDED.md and docs/EASY_SETUP.md.

## Optional audio settings

An audio-enabled board adds an **Audio** group before **This screen**. Its settings use the
same entity-based write path as the other groups; they never enter the legacy eleven-key
layout settings block. The hardware package owns separate saved preferences. Presence of
these ESPHome entities on the screen's device enables the corresponding editor rows:

| Setting | Entity name | Key |
| --- | --- | --- |
| Microphone mute | `switch`, Microphone mute | `microphone_mute` |
| Automatic gain | `switch`, Microphone automatic level control | `microphone_alc` |
| Speaker volume | `number`, Speaker volume | `speaker_volume` |
| Tap sound | `switch`, Tap sound | `tap_sound` |
| Wake word (test builds) | `select`, Wake word | `wake_word` |

Diagnostic builds also expose buttons for speaker, microphone and wake-word tests and stopping
a test. The editor presses only buttons belonging to that same ESPHome device. Test feedback
appears inside the action row; Stop is shown only during a test. Microphone measurements remain
available as HA diagnostic entities, without permanent meter rows in the settings page.

`smart_display.audio` and `smart_display.audio_tests` are compile-time feature flags supplied
by the optional packages, not runtime switches. Without them, the audio menu, callbacks and
recording helper are excluded. Audio-off builds also omit translated audio strings; the shared
text index table retains empty entries for compatibility. See [P4 audio setup](WAVESHAREP4.md#optional-audio).
