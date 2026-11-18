# The alarm panel

An `alarm_control_panel` entity is a tile with Home Assistant's card and code dialog: a shield in the state's colour, a
key per mode the panel supports, and a keypad when a mode asks for a code. A lock with a code uses the same keypad.
`components/smart_display/alarm_panel.h` holds the logic and the layouts (tested by `tests/test_alarm_panel.cpp`),
`alarm_panel_lvgl.h` draws them, and `tests/test_alarm_panel.py` keeps the firmware, the app and the editor in step.

## What Home Assistant says, and what it does not

A panel reports `code_format` (`number`, `text` or nothing) and `code_arm_required`. It never reports how long a code
is: the manual alarm takes a code of any length or a template, template and MQTT panels say only `number`, and Alarmo
keeps a code per person. Home Assistant's own card and dialog never send a code by themselves. The screen follows that:
it guesses no length.

A code goes out as the action's `code` and is wiped on the screen at once; it is never logged or stored. Three wrong
codes lock the keypad for 30 seconds, and every wrong code after that doubles the time, up to 15 minutes.

## The keypad

The keypad takes the card's place right under its bar, whose name says what the code is for (Disarm, Arm away). The
dots and one line of words stand above the keys, or beside them on glass at least 1.3 times as wide as it is tall.

- **The keys are as large as the room allows.** The twelve keys share all the room the dots leave, a finger's size at
  the least. A key is never more than 2.1 times as wide as it is tall, or more than 1.4 times as tall as it is wide.
- **Up to a large phone keypad's size.** A key stops growing at 24 mm wide and 18 mm tall (`KEY_W_MAX_MM`,
  `KEY_H_MAX_MM`), so a 7 or 10 inch screen shows a keypad of a hand's size in its middle instead of keys of a hand's
  width each. On the CYD and the 4 inch boards the room runs out first.
- **The keys beside 0.** Delete on the left takes back the last digit, and OK on the right sends the code. When the code
  sends itself, the left one is empty and Delete moves to the right, where a phone has it.

Measured by `tests/test_alarm_panel.cpp` with the card's bar at the top, a key is about 10 × 6 mm on a CYD lying down,
19 × 9 mm on the Guition 4 inch, and 24 × 18 mm on the 7 and 10 inch screens, where the ceiling holds it.

## When the alarm goes off

While the panel is `pending` (someone came in and the entry delay counts) or `triggered`, and disarming asks for a code
the screen can type, the card is the keypad at once, on red over the whole glass. The line under the dots says what is
going on and how long is left ("Pending · 0:24"). Back closes the card, since there is no card behind it, and a tap on
the tile opens the keypad again. The screen wakes with this keypad when the state arrives (`alarm_state_arrived`).
During the exit delay (`arming`) the card keeps its one Disarm key, as Home Assistant's dialog does.

## Sending the code by itself

A tile's **Send code after** option (`send_after`: off, or 4 to 8 digits, `catalogue/alarm_control_panel.yaml`) makes
the last digit send the code, without OK. The keypad then shows exactly that many dots. Off is the default and is never
stored. Only the person who sets up the tile knows the length, and a code sent too early counts as a wrong one, so the
editor's hint says to use it only when every code of that alarm has that many digits. A lock's keypad has no such
option and keeps its OK key.

A screen with older firmware ignores the option and shows its OK key, so a layout with it needs no update first.

## Where a change goes

- the logic and the layouts: `alarm_panel.h`, with `tests/test_alarm_panel.cpp`;
- the drawing: `render_code_pad`, `render_alarm_detail` and `alarm_command` in `alarm_panel_lvgl.h` (back on the keypad in `detail_lvgl.h`);
- the option: `catalogue/alarm_control_panel.yaml`, `ALARM_SEND_AFTER` in `screen_manager/app/core.py`,
  `canonicalOptions` in `web/src/model/tile-options.ts`, the editor's `TileInspector.vue`, and its words under
  `editor.tile.send_after` in `screen_manager/translations/en.json`;
- the walk through the card on every board: the alarm round of `tools/render/run.py`.
