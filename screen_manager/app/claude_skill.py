"""The Claude skill ESP Screens offers under Settings → Claude: installed for Claude Code, or downloaded for claude.ai.

Claude Code finds project skills in `.claude/skills/<name>/SKILL.md` of the folder it starts in; the
Claude Code apps for Home Assistant start in the configuration folder. claude.ai takes the same folder as
a zip. The text is built from the same reference as the Alerts cheatsheet, so it never names a field,
color or icon the firmware lacks, and it is the same on every call: status() compares it byte for byte
to tell an outdated copy.
"""
import io
import os
from pathlib import Path
import zipfile

from i18n import t
import tile_icons
from core import (ALERT_ACTION_FIELD, ALERT_ACTION2_FIELD, ALERT_CHOICE_ACTION, ALERT_CHOICE_FIELDS, ALERT_CHOICE_MIN_FIRMWARE, ALERT_CAMERA_FIELD, ALERT_SCREEN_FIELD, ALERT_ENDINGS, ALERT_EVENT, ALERT_FALLBACK_ICON, ALERT_FIELDS, ALERT_LIMITS, ALERT_MAX_TIMEOUT, BOARD_KEYS, SHAPES, limit_boards,
                  ALERT_MIN_FIRMWARE, ALERT_SUGGESTED_ICONS, AUTO_STANDBY_MIN_FIRMWARE, BROADCAST_DISMISS, BROADCAST_SHOW,
                  CONTROLS, COVER_TILE_MIN_FIRMWARE, DISPLAYS, FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES, FULL_PAGE_MIN_FIRMWARE, LIVE_MIN_FIRMWARE,
                  PAGE_TILE_REPEAT_MIN_FIRMWARE, SETTINGS_PAGE_MIN_FIRMWARE, TILE_BACKGROUNDS, TILE_EVENTS, TILE_RESULT_EVENT,
                  WAKE_SLEEP_MIN_FIRMWARE, SETTING_ENTITIES_MIN_FIRMWARE, DARK_MODE_MIN_FIRMWARE, PAGE_BUTTONS_MIN_FIRMWARE,
                  HOME_BUTTON_MIN_FIRMWARE, SHOW_PAGE_MIN_FIRMWARE)
# Full-page tiles, navigation tiles and one tile per cell of the screen's pages.
FULL_PAGE_VERSION = '.'.join(str(part) for part in FULL_PAGE_MIN_FIRMWARE)
LIVE_VERSION = '.'.join(str(part) for part in LIVE_MIN_FIRMWARE)
COVER_TILE_VERSION = '.'.join(str(part) for part in COVER_TILE_MIN_FIRMWARE)
# The same navigation tile on several pages (app 0.2.78).
PAGE_TILE_REPEAT_VERSION = '.'.join(str(part) for part in PAGE_TILE_REPEAT_MIN_FIRMWARE)

NAME = 'esp-screens'
# claude.ai accepts at most 200 characters; Claude Code picks the skill by this sentence.
def _and(items):
    items = list(items)
    return ', '.join(items[:-1]) + (' and ' if len(items) > 1 else '') + (items[-1] if items else '')

# The boards, by the names and sizes of the catalog (boards.yaml through boards.json), so the skill never names a board
# the add-on does not know or leaves one out.
def _board(board):
    catalog = SHAPES[board].get('catalog', {})
    inch = catalog.get('inch')
    return f"{catalog.get('name', board)} {inch:g}-inch" if inch else catalog.get('name', board)

def _grids():
    """'2 × 3 on the CYD 2.8-inch, ...': the cells of a page lying down, the boards with the same grid together."""
    grids = {}
    for board in BOARD_KEYS:
        grids.setdefault((SHAPES[board]['columns'], SHAPES[board]['rows']), []).append(f'the {_board(board)}')
    return '; '.join(f'{columns} × {rows} on {_and(boards)}' for (columns, rows), boards in grids.items())

NAMES = list(dict.fromkeys(SHAPES[board].get('catalog', {}).get('name', board) for board in BOARD_KEYS))
DESCRIPTION = (f'ESP Screens ({_and(NAMES)} touchscreens run from Home Assistant): put, move or order tiles on a '
               'screen, show an alert or open a page on it, and wake, sleep or keep a screen awake.')
TYPES = {'string': 'text', 'int': 'number', 'bool': 'on/off'}

def skill_dir(config=None):
    """Where the skill goes: <Home Assistant configuration>/.claude/skills/esp-screens."""
    return Path(config or os.environ.get('HA_CONFIG', '/homeassistant')) / '.claude' / 'skills' / NAME

def _limit(name, kind):
    """The bytes a text field holds on each look, with the boards that have it ("CYD 48 · Guition and Waveshare 64 bytes")."""
    boards = limit_boards()
    parts = [f"{' and '.join(boards[look])} {values[name]}" for look, values in ALERT_LIMITS.items() if name in values and boards.get(look)]
    if parts:
        return ' · '.join(parts) + ' bytes'
    return f'0 to {ALERT_MAX_TIMEOUT} s' if kind == 'int' else ''

def text():
    """SKILL.md: the tile events and how to read a screen, then the alert event for every screen, the
    per-screen action, fields, colors and icons, and the standby and brightness entities."""
    fields = '\n'.join(f'| `{name}` | {TYPES[kind]} | {help_} | {_limit(name, kind)} |' for name, kind, _, help_, _ in ALERT_FIELDS)
    choice_fields = '\n'.join(f'- `{name}`: {help_}' for name, _, _, help_, _ in ALERT_CHOICE_FIELDS)
    colors = ', '.join(f"`{name}` ({item['label']})" for name, item in TILE_BACKGROUNDS.items() if item['color'])
    suggested = ', '.join(f'`{name}`' for name in ALERT_SUGGESTED_ICONS)
    groups = '\n'.join(f'- {group}: ' + ', '.join(f'`{name}` ({label})' for name, _, label in icons) for group, icons in tile_icons.GROUPS)
    fixed = ', '.join(f'`{name}`' for name, _ in tile_icons.FIXED + tile_icons.HA_DEFAULTS)
    endings = ', '.join(f'`{action}` ({label[0].lower() + label[1:]})' for action, label in ALERT_ENDINGS)
    controls = '\n'.join(f'| `{domain}` | ' + ', '.join(f'`{key}` ({label.lower()})' for key, label in choices) + ' |'
                         for domain, choices in CONTROLS.items())
    displays = '\n'.join(f'| `{domain}` | ' + ', '.join(f'`{name}`' for name in names) + ' |' for domain, names in DISPLAYS.items())
    events = '\n'.join(f'| `{event}` | {what} |' for event, what in
                       (('esp_screens_add_tile', 'Puts an entity on a screen, or changes the tile that is already there'),
                        ('esp_screens_remove_tile', 'Takes a tile off a screen'),
                        ('esp_screens_move_tile', 'Moves a tile to another page or spot'),
                        ('esp_screens_order_tiles', 'Puts tiles in the order you give')))
    return f'''---
name: {NAME}
description: {DESCRIPTION}
---

# Tiles, alerts and standby on ESP Screens

Made by ESP Screen Manager (ESP Screens → Settings → Claude). Installing it again from there replaces this file, so changes made here get lost.

Four things Home Assistant can do with the screens: choose what a screen shows ([Tiles](#tiles-on-a-screen)), show an alert (below), open a page ([Open a page on a screen](#open-a-page-on-a-screen)), and wake a screen, put it to sleep or keep it awake ([Standby and brightness](#standby-and-brightness)).

An alert is a card over the whole screen with an icon, a title, a subtitle and one button, or two for a choice. It wakes the screen and stays until someone presses the button or the timeout runs out. A new alert replaces the one showing.

## Tiles on a screen

A screen shows tiles on pages, and a page is a grid of cells whose columns and rows depend on the screen: {_grids()} lying down, and other grids standing up. A screen has at most {FIRMWARE_MAX_PAGES} pages and {FIRMWARE_MAX_TILES} tiles, one per cell, so a page with more than eight cells gives fewer pages (seven pages of nine); firmware before {FULL_PAGE_VERSION} holds twenty tiles. The screen's own sensor (below) says its `columns`, `rows` and `max_pages`, so read it before counting. A tile is single, double-width or full-page: a double-width one takes two cells side by side, a full-page one takes a whole page of its own and is one big button, so someone can switch a light by pushing anywhere on the screen without looking. A `controls` choice, a small slider or a graph sits at the bottom of that page (a full-page tile shows no control unless you choose one).

Fire one of these events and ESP Screens changes that screen and sends it right away, the same way its own editor does.

| Event | What it does |
|---|---|
{events}

```yaml
actions:
  - event: esp_screens_add_tile
    event_data:
      screen: living room
      entity: vacuum.s8
```

### What you can put in the event

| Field | Meaning |
|---|---|
| `screen` | Which screen: its device name, the name Home Assistant shows, its area, or the title on the screen. With one screen paired you can leave this out. |
| `entity` | The entity the tile shows. Use the real entity ID; never invent one. |
| `name` | A name of your own on the tile; leave it out to keep Home Assistant's. |
| `page` | Page, counted from 1. Without a spot the tile takes the first free one on that page. |
| `row`, `column` | An exact spot on that page: the row counted from 1, and the column as a number counted from 1 or as `left` or `right` (the first and the last column; `middle` on a screen with three). |
| `slot` | An exact spot as the screen's sensor counts it, from 0 up to its pages times its cells minus one: instead of `page`, `row` and `column`. |
| `from_page`, `from_slot` | Only for `esp_screens_move_tile`: which copy of a navigation tile that is on several pages to move (see below). |
| `size` | `single`, `wide` or `full` (the whole page; firmware {FULL_PAGE_VERSION} or newer). |
| `controls` | What you can operate on the tile itself (see below). |
| `display` | How the tile draws itself (see below). On a screen that draws pictures (every board but {_and(f'the {_board(b)}' for b in BOARD_KEYS if 'camera' not in SHAPES[b])}) a camera or image tile takes `live` (firmware {LIVE_VERSION} or newer): a small live picture in the icon's place, with `refresh` 15 or 30 (seconds); a media player tile takes `cover` (firmware {COVER_TILE_VERSION} or newer): the album cover of what plays in the icon's place. |
| `icon`, `color` | An icon from the list further down, and one of the pastel colors. |
| `tap` | What a tap does: `auto`, `detail` (open the card), `toggle`, `action` or `none`. `toggle` works for anything Home Assistant can toggle for that entity, such as a light, a cover (open, close, or stop while it moves) or a speaker that turns on and off. Holding the tile still opens its card. |
| `action`, `data` | Perform action: an action Home Assistant offers for the tile's own entity, such as `cover.set_cover_position`, with `data` for its fields (`position: 50`). Giving `action` sets `tap` to `action`. The target is always the tile's entity. Only actions and fields Home Assistant lists for that entity are accepted; the answer says what is missing. |
| `entities` | Only for `esp_screens_order_tiles`: the entities in the order you want them. |

A tile with a control, a forecast or a sun path is drawn double-width on its own; you don't have to ask for that.

A navigation tile goes to another page: add the entity `screen.page_3` (for page 3, `screen.page_1` to `screen.page_{FIRMWARE_MAX_PAGES}`, as far as the screen's `max_pages` goes) with a `name` such as "Heating"; it shows an arrow (or an `icon`), its name and the page number, and a tap opens that page. Handy as a menu on page 2 when page 1 is one full-page light switch. It is single or double width, never full-page.

On firmware {PAGE_TILE_REPEAT_VERSION} or newer the same navigation tile can be on several pages, such as a `screen.page_1` named "Back" on every other page: add it with the `page` (or spot) it goes on, and a page without a copy gets a new one. Older firmware has one per page it goes to, and adding it again moves that one. Every other entity is on a screen once.

When a navigation tile is on several pages, say which copy you mean: `page` or `slot` for `esp_screens_add_tile` (change that copy) and `esp_screens_remove_tile`, `from_page` or `from_slot` for `esp_screens_move_tile` (its `page` and `slot` say where to), and in `esp_screens_order_tiles` each time you name it takes the next copy. An event that doesn't say acts on the first copy, the one with the lowest `slot` in the sensor.

### What a tile can do, per kind of entity

| Entity | `controls` |
|---|---|
{controls}

| Entity | `display` |
|---|---|
{displays}

Everything else shows its name and state, and opens a card of its own on a long press.

### Reading a screen first

Every screen also publishes what it shows, as `sensor.esp_screens_<device name>`: the state is the number of tiles, and the attributes hold `title`, the grid of its pages (`columns`, `rows` and `max_pages`), `pages` and `tiles` with `entity`, `name`, `page`, `row`, `column`, `slot`, `size`, `controls` and `display` per tile (and `to_page` for a `screen.page_<n>` tile), every copy of a navigation tile on its own. The `column` is `left` or `right` on a two-column screen and a number counted from 1 on any other. Read that before moving things around, so you know what is already there and where.

Ordering a page means naming the tiles that are on it, in the order you want:

```yaml
actions:
  - event: esp_screens_order_tiles
    event_data:
      screen: living room
      page: 1
      entities: [light.kitchen, light.dining, vacuum.s8]
```

A tile from another page has to be moved there first (`esp_screens_move_tile` with `page`). Leave `page` out to order the whole screen: the entities you name come first, the rest keeps its order behind them.

### What comes back

ESP Screens answers every event with `{TILE_RESULT_EVENT}`, carrying `ok`, the `screen`, the `entity`, the `page` and `slot` of the tile it placed, changed, moved or removed (not for an order) and, when it refused, an `error` that says why ("No screen called ...", "That spot is taken by ...", "This screen already has 48 tiles", "No page is empty; a full-page tile needs a page of its own"). The add-on log says the same. Nothing changes on a refused event.

### How to work

1. Read the screen's sensor, and Home Assistant's own entities for what the user names. Ask which screen when several could fit.
2. Say what you are going to do: which tile, which screen, which spot. A tile appears on a screen in someone's house, so wait for a yes before firing the event.
3. Fire the events one at a time and read `{TILE_RESULT_EVENT}` (or the sensor) before the next one.
4. Sorting by how much something is used comes from Home Assistant itself (history or the logbook), not from the screen.

## All screens, or one: fire an event

ESP Screen Manager listens for two Home Assistant events and passes them on to every paired screen that is online, screens added later included, or only to the screens its `{ALERT_SCREEN_FIELD[0]}` names. Screens need firmware {ALERT_MIN_FIRMWARE} or newer, and the app has to be running.

```yaml
actions:
  - event: {BROADCAST_SHOW}
    event_data:
      title: "Mail!"
      subtitle: "There is post in the mailbox"
      icon: mailbox
      color: orange
      button_text: "OK"
      timeout: 0
      flash: true
```

`{BROADCAST_DISMISS}` (no data, or only a `screen`) takes the alert off every screen, or off the screens it names. Every field of the event is optional: a missing or unusable value becomes empty text, `0` or off. Templates in `event_data` work as usual. For an alert right now, without an automation, fire the same event through Home Assistant's REST API (`POST /api/events/{BROADCAST_SHOW}` with the fields as JSON; inside a Home Assistant app such as Claude Code that is `http://supervisor/core/api/events/{BROADCAST_SHOW}` with `$SUPERVISOR_TOKEN` as the bearer token) or under Developer tools → Events. The ESP Screen Manager log tells how many screens got it.

## One screen: the event with `{ALERT_SCREEN_FIELD[0]}`, or its action

`{ALERT_SCREEN_FIELD[0]}` (app 0.2.133): {ALERT_SCREEN_FIELD[2]} The part of a screen's action between `esphome.` and `_show_alert` works as is (`kitchen_screen`). Use the event with `{ALERT_SCREEN_FIELD[0]}` whenever one screen should get a `{ALERT_CAMERA_FIELD[0]}` picture or an `{ALERT_ACTION_FIELD[0]}`; the screen's own action cannot take those.

```yaml
actions:
  - event: {BROADCAST_SHOW}
    event_data:
      {ALERT_SCREEN_FIELD[0]}: kitchen-screen
      title: "Someone is at the door"
      icon: doorbell
      color: orange
      {ALERT_CAMERA_FIELD[0]}: camera.front_door
```

A plain alert on one screen can also use its own action:

Every screen also has its own actions, `esphome.<device_name>_show_alert` and `esphome.<device_name>_dismiss_alert` (dashes in the device name become underscores). List Home Assistant's `esphome` actions to see which screens exist. These actions need all seven fields; send `""`, `0` or `false` for the ones you don't use.

```yaml
actions:
  - action: esphome.kitchen_screen_show_alert
    data:
      title: "Laundry is done"
      subtitle: ""
      icon: washing-machine
      color: green
      button_text: ""
      timeout: 600
      flash: false
```

## Fields

| Field | Type | Meaning | Limit |
|---|---|---|---|
{fields}

The event for every screen takes one more field, `{ALERT_CAMERA_FIELD[0]}`: {ALERT_CAMERA_FIELD[2]} Example: `{ALERT_CAMERA_FIELD[0]}: {ALERT_CAMERA_FIELD[3]}`. Use a real `camera.*` or `image.*` entity from this Home Assistant (a doorbell integration usually has one); the per-screen actions have no such field, so for one screen add `{ALERT_SCREEN_FIELD[0]}`.

It also takes `{ALERT_ACTION_FIELD[0]}` (app 0.2.91): {ALERT_ACTION_FIELD[2]} Example: `{ALERT_ACTION_FIELD[0]}: {ALERT_ACTION_FIELD[3]}`, or `action: light.turn_off` with `data: {{entity_id: light.hall}}`. Use an action Home Assistant lists; give `button_text` a word that says what the button does ("Open", "Turn off"). The per-screen actions have no such field either.

## Two buttons and button colors

Firmware {ALERT_CHOICE_MIN_FIRMWARE} or newer draws a second button on the left of the first, for a choice such as Not now and Open, and gives either button a color of its own. The event takes these fields, all optional:

{choice_fields}
- `{ALERT_ACTION2_FIELD[0]}`: {ALERT_ACTION2_FIELD[2]}

```yaml
actions:
  - event: {BROADCAST_SHOW}
    event_data:
      title: "Someone is at the door"
      icon: doorbell
      button_text: "Open"
      button_color: green
      action: script.open_gate
      button2_text: "Not now"
      button2_color: red
```

The first button is always on the right; which answer goes on which side is the user's choice. A screen with older firmware shows the alert with its first button only. One screen can also use its own action `esphome.<device_name>_{ALERT_CHOICE_ACTION}`: the seven fields of show_alert plus `button_color`, `button2_text` and `button2_color`, all required (send `""` for the ones you don't use). The second button ends the alert with `action: button2`.

Text limits are in bytes; an accented letter takes two. Keep the title short: a screen shows about twenty characters of it on one line and ends a longer title with an ellipsis. Put details in the subtitle.

## Colors

`color` takes one of {colors}. Empty or unknown gives the white card.

## Icons

`icon` takes one of the names below, exactly as written (`mdi:` in front works too). The firmware carries only these glyphs and shows the warning triangle (`{ALERT_FALLBACK_ICON}`) for any other name, so pick the closest name from this list rather than another Material Design icon.

Good for alerts: {suggested}.

{groups}
- Also available: {fixed}

## When an alert ends

Each screen fires `{ALERT_EVENT}` with `action`: {endings}. The event also carries `title`, `screen` (the device name) and `device_id`. To react to the button:

```yaml
  - wait_for_trigger:
      - trigger: event
        event_type: {ALERT_EVENT}
        event_data:
          action: ok
    timeout: "00:05:00"
```

## Writing the automation

1. Find the real trigger in Home Assistant, such as the mailbox sensor. Never invent an entity ID; ask when several entities could fit.
2. All screens: the `{BROADCAST_SHOW}` event. One screen the user names: that screen's own action.
3. When the situation clears (mailbox emptied, door closed), fire `{BROADCAST_DISMISS}` from the same automation.
4. Take the icon and color from the lists above.
5. Ask before sending a test alert: it lights up the screens around the house.

Example, with the user's own entity in place of `binary_sensor.mailbox`:

```yaml
alias: Mailbox alert on the screens
triggers:
  - trigger: state
    entity_id: binary_sensor.mailbox
    to: "on"
    id: mail
  - trigger: state
    entity_id: binary_sensor.mailbox
    to: "off"
    id: emptied
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: mail
        sequence:
          - event: {BROADCAST_SHOW}
            event_data:
              title: "Mail!"
              subtitle: "There is post in the mailbox"
              icon: mailbox
              color: orange
              timeout: 0
              flash: true
      - conditions:
          - condition: trigger
            id: emptied
        sequence:
          - event: {BROADCAST_DISMISS}
```

## Open a page on a screen

Every screen has the action `esphome.<device_name>_show_page` (firmware {SHOW_PAGE_MIN_FIRMWARE} or newer). It puts one page of the screen's tiles in front, the way a Go to page tile does when someone taps it: the screen wakes if it was in standby, an open card or the settings page closes, and that page is shown. An alert that is showing stays in front. `page` is the page number the editor shows, 1 for the first page; a number past the last page opens the last page. Read the screen first ([Reading a screen first](#reading-a-screen-first)) to see which page holds what.

```yaml
actions:
  - action: esphome.living_room_screen_show_page
    data:
      page: 4
```

Typical use: the page with a full-page player when a media player starts playing, or the page with a camera tile when the doorbell rings. Like a touch, it starts Back to page 1 counting from that moment, so the screen goes back to page 1 on its own time unless `switch.<screen>_back_to_page_1` is off; call the action again to keep the page up. Nothing is saved on the screen, so an automation may call it as often as it likes.

## Standby and brightness

Every screen has these entities in Home Assistant, on its ESPHome device. `<screen>` stands for the start Home Assistant gave the screen's entity IDs, the same as in `text.<screen>_tile_settings`; look them up rather than guessing.

| Entity | What it does |
|---|---|
| `button.<screen>_wake` | Lights the screen up to its normal brightness and counts the standby time from that moment; a screen that is already on only restarts that count. Firmware {WAKE_SLEEP_MIN_FIRMWARE} or newer. Wake is not a touch: from firmware 0.2.56 an open card or a later page still goes back to page 1 on its own time, and a screen whose time ran out during standby wakes on page 1. |
| `button.<screen>_sleep` | Puts the screen in standby right away, also with Auto standby off, and closes an alert that is showing. It stays in standby until someone taps it, Wake is pressed or an alert arrives. Firmware {WAKE_SLEEP_MIN_FIRMWARE} or newer. |
| `switch.<screen>_auto_standby` | On: the screen dims after the standby time without a touch. A screen that cannot go dark ({_and(f'the {_board(b)}' for b in BOARD_KEYS if not SHAPES[b].get('can_standby', True))}, app 0.2.106) has none of the standby and night entities in this table, nor Wake and Sleep: it is always on. Off: the screen wakes up and stays on, except after Sleep, which holds until Wake, a tap or an alert. Firmware {AUTO_STANDBY_MIN_FIRMWARE} or newer. |
| `number.<screen>_standby_after` | Seconds without a touch before standby, 60 to 86400. |
| `number.<screen>_normal_brightness` | Brightness while in use, 5 to 100 %. |
| `number.<screen>_standby_brightness` | Brightness in standby, 0 to 100 %, at most the normal brightness. |
| `number.<screen>_night_brightness` | Brightness in standby during the night hours, 0 to 100 %. |
| `switch.<screen>_dark_mode` | On: the dark look, a black page with graphite cards and soft white text, for a screen beside a bed or in a dark room. Off: the light look. Firmware {DARK_MODE_MIN_FIRMWARE} or newer. |
| `switch.<screen>_night_mode` | Night mode: the night brightness between the two times below. Firmware {SETTING_ENTITIES_MIN_FIRMWARE} or newer, like every row below it. |
| `time.<screen>_night_starts`, `time.<screen>_night_ends` | The night hours; set them with `time.set_value`. |
| `switch.<screen>_back_to_page_1` | On: after `number.<screen>_back_to_page_1_after` seconds without a touch (30 to 3600) the screen closes a card and goes back to page 1. Pressing Wake, an alert or Auto standby don't count as a touch. |
| `switch.<screen>_back_to_page_1_on_standby` | On: going into standby also goes back to page 1. |
| `switch.<screen>_swipe_between_pages` | On: swipe between pages. |
| `switch.<screen>_page_buttons` | On: the Previous and Next bar under the tiles on a screen with more than one page. Off: no bar, the tiles take its room, and only swiping or Go to page tiles change the page. Firmware {PAGE_BUTTONS_MIN_FIRMWARE} or newer. |
| `switch.<screen>_show_home_button` | On: a house at the far left of the top bar; tapping it goes back to page 1. Off: the page title starts at the margin, as before. Firmware {HOME_BUTTON_MIN_FIRMWARE} or newer. |
| `select.<screen>_rotation` | `0°` or `180°`, a half turn that keeps the screen's grid; a square screen also `90°` and `270°`. |

The 12 or 24-hour clock, the language and how numbers are written are one choice for every screen, in ESP Screens under Settings → Language & region; no entity changes them (firmware 0.2.76 or newer; older firmware still has `switch.<screen>_24_hour_clock`).

Wake and Sleep are buttons: press them with the `button.press` action. They save nothing, so an automation may press them as often as it likes, on every motion too. To reach several screens at once, list their buttons under `entity_id`. Don't target an area or a device with `button.press`: that presses every other button there as well, the Wake and Sleep of the same screen included.

```yaml
alias: Screens wake on motion and sleep when the TV goes on
triggers:
  - trigger: state
    entity_id: binary_sensor.hallway_motion
    to: "on"
    id: motion
  - trigger: state
    entity_id: media_player.living_room_tv
    to: "on"
    id: tv
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: motion
        sequence:
          - action: button.press
            target:
              entity_id: button.hallway_screen_wake
      - conditions:
          - condition: trigger
            id: tv
        sequence:
          - action: button.press
            target:
              entity_id:
                - button.living_room_screen_sleep
                - button.kitchen_screen_sleep
```

These switches, numbers, times and the select are the screen's own settings, the same as on its settings page and in ESP Screens: a change made from Home Assistant shows there too and stays after a restart. Turning Auto standby on again counts the standby time from that moment. Every change is saved on the screen, so switch on changes that happen a few times a day (someone comes home, a light goes on, a window opens), never on every motion: press Wake for that.

To keep screens on while something is going on at home, turn Auto standby off when the situation starts and on when it ends, all from one automation. Example with placeholders for the user's own entities:

```yaml
alias: Keep the screens awake
mode: restart
triggers:
  - trigger: state
    entity_id:
      - person.alex
      - light.living_room
      - binary_sensor.bedroom_window
actions:
  - if:
      - condition: state
        entity_id: person.alex
        state: home
      - condition: or
        conditions:
          - condition: state
            entity_id: light.living_room
            state: "on"
          - condition: state
            entity_id: binary_sensor.bedroom_window
            state: "on"
    then:
      - action: switch.turn_off
        target:
          entity_id: switch.kitchen_screen_auto_standby
    else:
      - action: switch.turn_on
        target:
          entity_id: switch.kitchen_screen_auto_standby
```

Replace the person, light, window and screen with the real entity IDs (ask which screens when there are several), and leave out conditions the user did not ask for.

Dark mode follows the same pattern: switch it on and off from an automation, for example at bedtime and in the morning, or with the sun. It changes the colours only, never the tiles or the brightness; lower the brightness with the numbers above.

```yaml
alias: Bedroom screen dark at night
triggers:
  - trigger: time
    at: "21:30:00"
    id: night
  - trigger: time
    at: "07:00:00"
    id: day
actions:
  - if:
      - condition: trigger
        id: night
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.bedroom_screen_dark_mode
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.bedroom_screen_dark_mode
```

## The settings page on the screen itself

Firmware {SETTINGS_PAGE_MIN_FIRMWARE} or newer carries a settings page the user can open at the panel: hold the top bar (the strip with the screen's name and the clock) for about a second and a half, until the blue line along the top edge is full. A screen can also carry a tile for it: put the entity `screen.settings` on a screen like any other tile.

It holds Brightness (with Dark mode), Night, Screen (clock, going back to page 1, swiping, rotation) and This screen (name, address, firmware, whether Home Assistant is connected, and Restart). A change there is saved on the screen and shows up in ESP Screens within a second, exactly like a change made from Home Assistant.

You can open it for someone who is standing at the panel:

```yaml
actions:
  - action: esphome.kitchen_screen_open_settings
    data:
      page: 1
```

`page` 0 is the menu, 1 Brightness, 2 Night, 3 Screen, 4 This screen, and -1 closes the page and puts the screen back on page 1. Use it to walk someone through a setting ("I opened Brightness on the kitchen screen"), not to change something yourself: for that, use the entities above, which do the same thing without anyone at the panel.
'''

def status(directory):
    """Whether the skill is there and equal to what this app version writes."""
    try:
        installed = (directory / 'SKILL.md').read_text(encoding='utf8')
    except FileNotFoundError:
        return {'installed': False, 'current': False, 'path': str(directory)}
    except (OSError, UnicodeDecodeError):
        installed = None
    return {'installed': True, 'current': installed == text(), 'path': str(directory)}

def archive():
    """The skill folder as a zip, the way claude.ai takes an uploaded skill: esp-screens/SKILL.md."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        entry = zipfile.ZipInfo(f'{NAME}/SKILL.md', date_time=(2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        bundle.writestr(entry, text())
    return buffer.getvalue()

def install(directory):
    """Write SKILL.md, replacing an older copy. `restart`: the skills folder is new, and Claude Code only
    watches skills folders that existed when it started."""
    restart = not directory.parent.is_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / 'SKILL.md.tmp'
        temp.write_text(text(), encoding='utf8')
        temp.replace(directory / 'SKILL.md')
    except OSError as error:
        raise ValueError(t('addon.errors.skill_not_written', folder=directory, reason=error.strerror or type(error).__name__)) from error
    return {**status(directory), 'restart': restart}
