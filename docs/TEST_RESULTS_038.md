# 0.3.8 acceptance (firmware 0.3.3)

This release brings four features together: clearer weather, thermostat and select tiles, camera tiles that fill
their card, alerts with two buttons, and the alarm panel. Each was tested on its own branch (the sections below), and
then once more together on the combined release, which is what this first section describes.

## Combined 0.3.8 glass test

Tested on 26 September 2026 on three bench screens (a 4-inch Guition 4848S040, a Waveshare ESP32-S3-Touch-LCD-4.3
and a CYD ESP32-2432S028) over OTA, with a real Home Assistant and the combined add-on installed as a local add-on.
The owner was at the screens for the parts that need a finger.

### Firmware on the screens

- CYD and Waveshare 4.3: the final release commit (the keypad text wrap below included), built at 15:06 and 15:09.
- Guition: the commit before it, built at 14:38; it differs only in that keypad text wrap.
- All three reported firmware 0.3.3 in `device_info`.
- CYD image: 1,689,216 B of 1,835,008 B = 92.1 % (145,792 B free), +39,760 B against 0.3.7 (final `tools/check.sh --all`). Every other board builds; 16 of 16 host render variants pass when each run uses its own `--port-base`.

### What was checked

- **Weather, thermostat and select tiles (Guition, snapshots of the glass):** a double-width weather tile with the
  coming days, a weather tile of two rows with the week's temperature bars, a select tile with its chevrons, the
  select card with a check at the chosen option, and a square thermostat with its mode bar. All as designed. The same
  layouts were Synced on the CYD and the Waveshare without an error in the log.
- **Camera tiles (Guition):** a live camera on a 1 x 2 tile and a second one on a 2 x 2 tile, first with Fill and the
  name, then with Whole picture and nothing on it; both as designed. The screen downloaded 51,238 bytes for the 1 x 2
  picture and 103,222 bytes for the 2 x 2 one, and no image step took longer than 0.12 s. A page that came back
  showed its picture at once, and the owner found switching pages fast.
- **Alert with two buttons (Guition):** two equal buttons, the red one on the left. The owner tapped it: the screen
  logged `dismissed: button2`, the app performed the second button's action (`persistent_notification.create`) and
  the notification appeared in Home Assistant; it was dismissed afterwards. The app delivered the alert to one of one
  screen.
- **Alarm panel (CYD and Waveshare 4.3):** a test alarm, a state set through Home Assistant's REST API with no
  integration behind it, removed afterwards. `pending` woke both screens with the keypad to disarm. The CYD ran 5.5
  minutes with the alarm going off and its card open: no restart, lowest free heap 117 KB. The owner typed three codes
  with a finger: three `alarm_disarm` actions with a code went to the test alarm, which does not answer, so the screen
  counted each as failed after ten seconds and locked the keypad for 30 seconds after the third. The Waveshare stayed
  up for six minutes with its free heap at 93 KB. No real alarm was armed or disarmed.
- **Page swipes (Guition):** the owner swiped through every page: fast, nothing out of place.

### Found and fixed on the way

- **The S3 boards did not link.** With the four features together, the Guition and the Waveshare 4.3 failed to link
  with `dangerous relocation: l32r: literal target out of range` in the protocol parser, and the CYD was 1.5 KB from
  the same error. The parser is now a compilation unit of its own (`components/smart_display/page_receiver.cpp`); every
  board links again, with about 14 KB of margin on the S3 boards and 66 KB on the CYD. The second unit costs the CYD
  about 6 KB for the inline helpers it carries. docs/RELEASING.md tells how to recognise the limit.
- **The keypad's line on the CYD.** Beside the keys the column is about a hundred pixels wide, and "Nothing changed.
  Check the code." (in the screen's language) ended in dots after its first word. It now wraps over up to three
  lines there. The owner checked it on the CYD, and the keypad on the Waveshare.

### Known issue for the next release

- A live camera tile set to refresh every 30 seconds downloaded its picture every 15 seconds.

## Two buttons and button colours on an alert

Tested on 26 September 2026 on three bench screens (a 4-inch Guition 4848S040, a Waveshare ESP32-S3-Touch-LCD-4.3 and
a CYD ESP32-2432S028) over OTA, with a real Home Assistant. The alert gets `show_alert_choice` (the seven fields of
`show_alert` plus `button_color`, `button2_text` and `button2_color`), and the `esp_screens_show_alert` event gets
these three and `button2_action` with `button2_data`, all optional.

### Automated checks

- `tools/check.sh --all` on 0.3.7 (main b1184b7) with this change: 740 Python tests, 28 C++ programs, the package,
  cell, board shape, entry file, icon and translation checks, and the editor's tests, types, build and bundle. Every
  board compiles with ESPHome 2026.9.0.
- New tests: `test_alert_overlay.cpp` checks the second button's text and colours and where two buttons stand on every
  glass, look and picture shape. `test_alert.py` and `test_alerts_reference.py` check the action's fields against the
  profiles. `test_alert_broadcast.py` covers the event: `show_alert_choice` for a screen with firmware 0.3.3, `show_alert`
  with one button for an older one, and each button's own action performed once.
- The host render harness (tools/render) passed its self test on all sixteen variants, lying down and standing up.
  It now also renders an alert with two buttons in the keys' own paints, in key colours, on a coloured card, and with a
  camera picture. A standing doorbell camera (3:4), whose picture goes beside the words on wide glass, keeps both
  buttons in the column of words. On this Mac a portrait variant once missed a page swipe while the machine was under
  heavy load; it passed when run again.

### Where two buttons go

Three layouts were rendered on every board before one was chosen:

- both buttons of the one button's width against the right edge: on the CYD a label such as "Remind me" ended in dots;
- one button at each edge of the card: the two answers drifted apart and no longer read as one choice;
- the two buttons sharing the row in equal halves, the first on the right (chosen): each is as large as the card
  allows, and the labels fit.

### On the screens

The alert was sent to each screen through its own `show_alert_choice` action, and someone at the screen pressed the
button asked for:

| Screen | Button pressed | Ending the screen reported |
|---|---|---|
| Guition | the first, green | `ok` |
| Guition | the second, red | `button2` |
| CYD | the second, grey | `button2` |
| Waveshare 4.3 | the first, orange | `ok` |

- The Guition's own LVGL render (`diagnostics/capture_ui.py`) showed the card over the screen's tiles with both keys
  in their colours, side by side.
- `show_alert` still shows one button on all three screens, also right after an alert with two, and closed by its
  timeout.
- With the add-on of this release as a local add-on, `esp_screens_show_alert` with `screen` and a second button reached
  the Waveshare as `show_alert_choice` ("1 of 1 screens", no one-button fallback). The press of the second button and
  its `button2_action` through the add-on were not tried on a screen; the add-on's handling of it is covered by the
  tests above, and the screen's side of it (the `button2` ending) by the presses in the table.

### Firmware sizes

| Board | Image | Share of the update slot |
|---|---|---|
| CYD | 1,657,056 B | 90.3 % of 1,835,008 B, +7,600 B against 0.3.7 |
| Guition 4848S040 | 2,078,000 B | 25.6 % |
| Waveshare 4.3 | 2,334,400 B | 28.7 % |
| Guition JC8012P4A1 | 2,051,088 B | 25.2 % |
| Waveshare 7 | 1,863,792 B | 47.4 % |
| Waveshare 4B | 2,065,904 B | 25.4 % |
| Waveshare 3.5 | 1,900,208 B | 23.4 % |
| Guition JC1060P470 | 2,138,704 B | 26.3 % |
| Guition JC1060P470 V2 | 2,138,752 B | 26.3 % |

The CYD is over 90 % of its slot, which this release accepts; a cleanup of the CYD build follows later.

## The alarm panel

Tested on 26 September 2026: on the host render harness for every board, and on three bench screens (a 4-inch
Guition 4848S040, a Waveshare ESP32-S3-Touch-LCD-4.3 and a CYD ESP32-2432S028) over OTA, with a real Home Assistant
and this add-on installed as a local add-on. No real alarm was armed or disarmed: the screens got a test alarm, a
state set through Home Assistant's REST API (`POST /api/states/alarm_control_panel.<test>`) with no integration
behind it, removed afterwards.

### What Home Assistant does, which the screen follows

Read in Home Assistant's own code before the design (core `alarm_control_panel`, its `manual` platform, the ESPHome
integration's `manager.py`, and the frontend's alarm dialog, alarm panel card and code dialog, 2026.9):

- The modes come from `supported_features`; the frontend orders them home, away, night, vacation, custom bypass,
  disarmed. Trigger is not offered, as in Home Assistant's own dialogs.
- A code is asked for when disarming and the panel has a `code_format`, or when arming and it also has
  `code_arm_required`, unless the entity has a default code in its registry options.
- Integrations answer a wrong code three ways: a `ServiceValidationError` (the manual alarm), which ESPHome passes back
  to the screen as a refusal; a `HomeAssistantError`, which ESPHome's action response route does not pass back; or
  nothing at all (Alarmo only logs a warning). The screen counts a refusal, or a state that has not moved after ten
  seconds, as a failed attempt.

### Automated checks

- `tools/check.sh`: 747 Python tests (new: `tests/test_alarm_panel.py`, which holds the modes, colours, icons and code
  rule against Home Assistant's and keeps the code out of logs and events), every C++ program (new:
  `tests/test_alarm_panel.cpp`: modes, the code rule, attempts across the `millis()` wrap, the lock times, and the
  card and keypad layouts on eight shapes of glass in both looks with one to six modes), and the editor's 295 tests.
- `tools/check.sh --firmware` on the alarm panel's own branch (0.3.7 plus the panel): every board compiled with ESPHome
  2026.9.0, the CYD image 1,662,416 bytes of 1,835,008 (90.6 %); the alarm panel adds 12,960 bytes. The owner approved that growth on
  the condition that the CYD runs well on the glass, which it did (below).
- The host render harness (`tools/render/run.py --only alarm`) drove the whole flow on all 16 variants with a finger
  on the simulated touchscreen: the tile opens the card, a mode opens the keypad, the digits and OK send the action
  with the code (read back from the host program's action stream), the answer and the new states come back through
  the add-on's own messages, pending wakes the screen with the keypad, a refused code says so and counts, three lock
  the keypad for 30 seconds with every key disabled, triggered shows the Disarm key, and a panel without a code sends
  its mode without one. `render_alarm` checked that every key a finger uses lies inside the glass and over no other.
  All 16 passed.

### On the screens

- **The chain.** A test alarm in Home Assistant went through the add-on to all three screens as a tile. Its colour,
  icon and Home Assistant's own words, in the screen's language, followed every state, and the tile counted the exit delay down.
- **Waking.** Setting the test alarm to `pending` woke each screen and opened its card with the keypad to disarm,
  within four seconds on all three.
- **Snapshots of the Guition.** The card (the shield and a key per mode, the chosen mode in green), the keypad during
  the entry delay and the card while the alarm goes off were drawn as designed.
- **Soak.** With the card open and the alarm going off (the heartbeat running): 4 minutes on the CYD, 2 on the Guition
  and 2 on the Waveshare. No restart and no error in the log. Free heap on the CYD stayed at 136 KB (lowest since the
  start 129 KB), on the Guition 91 KB and on the Waveshare 98 KB. One "api took a long time" warning of 229 ms on the
  CYD, while a card was drawn.
- **No actions.** None of the screens sent an alarm action during the test.

### Not tested on the glass

- Typing a code with a finger and the lock after wrong codes: nobody was at the bench for this branch's own test. The
  host render harness covered both with real touches through ESPHome's touchscreen, and the combined glass test above
  did them on the CYD with a finger.
- A real alarm integration (Alarmo's countdown, a refusal from a real panel).
