# The doorbell

Someone rings, and your screens show the door. An automation in Home Assistant fires the event
`esp_screens_doorbell` with the doorbell's camera: an ESP32-P4 screen wakes up, plays a chime and opens the camera full
screen, live, with its sound on; any other screen shows the camera's picture in an alert. Any doorbell works, because
you choose what starts the automation: a doorbell Home Assistant knows as one, a sensor that turns on while someone
rings, a button, anything.

The editor's **Events** page (in the sidebar) has a wizard for it, behind **Create a doorbell automation**: one step at a
time it asks what rings, the camera, the screens and a name, lets you ring once to see it, and then adds the automation
to Home Assistant for you, or gives just its action as YAML to paste into an automation you already have. The wizard offers first the doorbells Home Assistant knows as
such: an event entity of the doorbell class, and the doorbell sensors of Reolink (Visitor), UniFi Protect (Doorbell),
Yale and August (Ding) and Skybell (Button). Under the step it says how the automation will read what you picked: a
doorbell rings, an event fires, a sensor, switch or toggle helper turns on, a button is pressed.

## The event

```yaml
triggers:
  - trigger: doorbell.rang
    target:
      entity_id: event.front_door_doorbell
actions:
  - event: esp_screens_doorbell
    event_data:
      camera: camera.front_door
      title: Front door
      screen: [hallway-screen, kitchen-screen]
      timeout: 60
      keep_minutes: 30
      lock: lock.front_door
```

| Field | What it does |
|---|---|
| `camera` | The doorbell's camera entity. Required. A P4 screen streams it live with its sound; any other screen shows its picture in an alert. |
| `title` | What the screen calls the doorbell, at the top of its view and as the alert's title. Empty takes the name of the camera's device, or the camera's own. |
| `screen` | Which screens get the ring: a device name, the name Home Assistant shows, or a room; a list reaches several. Leave it out for every screen. A name that matches no screen sends nothing. The same rules as an alert's `screen`. |
| `timeout` | Seconds a ring stays when nobody touches it, 10 to 600. Empty is 60. |
| `keep_minutes` | Minutes a missed ring stays in the top bar of the doorbell screens, counted from the moment it rang, 1 to 1440. Empty or 0 keeps it until someone opens it. The wizard offers 10 and 30 minutes, an hour, four hours and until someone opens it, and gives a new automation 30 minutes; an automation without the field keeps its missed rings until they are opened, as before. |
| `sound` | Whether the view opens with **Sound** on, so the doorbell is heard at once. Empty or `true` is on; `false` opens it quiet, for a studio or a bedroom, and a tap on Sound turns it on. |
| `chime` | Whether the screen plays its chime when it rings. Empty or `true` chimes; `false` rings without it, for someone who would rather not hear the ding-dong every time. |
| `lock` | A lock entity the view's **Door** key unlocks, after a second tap. The key shows the lock's state. Leave it out for no door key. |
| `door_action` | Instead of a lock: a Home Assistant action the Door key performs after a second tap, such as `script.open_gate` or `button.press`. |
| `door_data` | The fields of `door_action`, such as `entity_id: button.gate_open`. |

`esp_screens_dismiss_doorbell` closes every ring nobody answered yet, on every screen (for example when the door opens).

What starts the automation is yours to pick:

- A doorbell Home Assistant knows as one, an `event` entity of the doorbell class (UniFi Protect, Ring, Nest, DoorBird
  and others): `trigger: doorbell.rang`. Home Assistant made `ring` the standard event type of a doorbell in April 2026.
- A doorbell that reports a press as a sensor (Reolink's Visitor, UniFi Protect's Doorbell), or a toggle helper:
  `trigger: state`, `from: "off"`, `to: "on"`.
- Anything else: a button, a switch, a script. Each can fire the same event.

## What happens on the screens

1. The app sends every P4 screen the event names the op `doorbell` (its hello says `doorbell`), and every other screen
   the camera's alert (`esp_screens_show_alert` with the title, the doorbell icon and the camera).
2. A P4 screen wakes from standby or Sleep, closes the settings page, a card or another camera, plays a chime it makes
   itself on its speaker, and opens the camera full screen as a doorbell: the doorbell's disc where the back key
   stands, its name and how long ago it rang beside it, the close key at the right, and the picture beside the keys
   (glass lying down) or above them (square or standing glass). The picture is live as soon as the stream starts; until
   then its still and a spinner in the top bar.
3. The first touch on a screen **answers** the ring: the app closes the view on the other screens and the alert on the
   others. The close key answers it too.
4. Nobody touches it: it closes after its timeout. The ring is then **missed**, and every doorbell screen shows it at the
   left of its top bar (the doorbell's icon and "2 min ago") until someone taps that item, which opens the camera again,
   or answers a later ring of that camera, or until its `keep_minutes` have passed since it rang. The screen counts
   those itself, by its own clock, in standby too: the item carries the moment it leaves (`x`), and a screen that
   wakes after it shows the bar without it.

## The keys

The view has only the keys this ring and this screen can use: **Door** when the ring names a lock or a door action,
**Talk** where the screen has a microphone, and **Sound** where it has a speaker (the screen's capability record). The
wizard asks whether it chimes and whether the sound is on when it rings only when a screen it reaches shows the ring
live and has a speaker; both are on unless you turn them off.

## Open the door

With `lock` or `door_action` in the event, the view has a **Door** key above the others. A screen in a hallway is
touched by everyone who walks past, so one tap never opens the door, as on a lock's tile:

1. The first tap turns the key orange and says "Tap again to open", for five seconds.
2. A second tap within those five seconds opens it. The screen says so to the app, and the app performs it through Home
   Assistant: `lock.unlock` on the lock, or the action with its `door_data`, as it performs an alert's button.
3. With a lock, the key shows the lock's state (locked in green, unlocked in red) and says "Unlocking" until the lock's
   new state comes; the app sends every new state of the lock to the screens that show the ring. With an action, the key
   says "Sent" for two seconds.

A lock opens only from locked or jammed, never while it moves or once it is open. A lock that asks for a code needs a
default code in Home Assistant (the lock's settings): the view has no keypad, since nothing may lie over its picture, so
without a default code the app leaves the key out and says why in its log. The app opens the door only for a screen
that showed that ring, while its view is open, within a quarter of an hour of the ring, and once per press.

The wizard's **A door to open?** step offers a lock, or another action of an entity's own (a script, a gate's button).

While the view is open, standby and Back to Home wait; it closes five minutes after the last touch or ring at most. A
second ring while it is open plays the chime again and starts the timeout over.

Not every doorbell can do everything. The sound comes only when the camera's stream in Home Assistant has it.

## After a ring

Once per ring the app fires one event of its own, for an automation that follows it:

- `esp_screens_doorbell_answered` when someone answered it on a screen, with `camera`, `title` and `screen`;
- `esp_screens_doorbell_missed` when nobody did before its timeout, with `camera` and `title`.

```yaml
triggers:
  - trigger: event
    event_type: esp_screens_doorbell_missed
actions:
  - action: notify.notify
    data:
      message: Someone rang the doorbell
```

Each screen also reports how a ring ended there as `esphome.screen_doorbell` (`action`: answered, closed, missed or
seen; `key`; `screen`), which the app reads; `door` is the Door key's second tap, which the app answers by opening the
ring's door.

## Into Home Assistant

The wizards of Events (the doorbell's and the alerts') save their automation the way Home Assistant's own automation
editor does (`POST /api/config/automation/config/<id>`): Home Assistant writes it into `automations.yaml` and reloads
it, so it works at once, without a restart. Every automation from Tessera is called **Tessera: <name>**, so Home
Assistant's list shows which ones came from here, and the wizard lists them, each with a link to it in Home Assistant.
The app only saves automations whose every action fires one of its events, under ids of its own (`tessera_doorbell_...`,
`tessera_alert_...`), and only changes or removes those. An automation you made yourself and named "Tessera: ..." is
listed too, but left alone.

## How it fits together

| Part | Where |
|---|---|
| The event, its fields, the screens, answered and missed, the wizard's suggestions | `screen_manager/app/doorbell.py`, `Manager.doorbell_*` in `server.py` |
| Automations into Home Assistant | `screen_manager/app/automations.py`, `api/automations` in `server.py` |
| The Events page and its wizards | `web/src/components/EventsView.vue`, `DoorbellView.vue`, `AlertsView.vue`, `events/` (the wizards, in `ui/UiWizard.vue`) |
| The missed ring in the top bar | `page_service.sync_pages` (`with_missed`), the item's `b`, and its `x` (`Doorbells.bar_item`; the screen's `header_bar::shown_at`, tests/test_header_bar.cpp) |
| The op `doorbell` | `page_receiver.cpp` |
| The view, the chime, the times | `module_doorbell.cpp` (module doorbell), hooked into the camera full view of `runtime_tiles.h` |
| The door key: its two taps, which lock states open, its looks | `doorbell_door.h` (tests/test_doorbell_door.cpp); the app's `Manager.doorbell_open_door` and `doorbell_follow_lock` |
| The report of how a ring ended | `doorbell_report` in `packages/core.yaml`, the event `esphome.screen_doorbell` |

The view never lays anything of LVGL over its picture: a live picture is written to the glass past LVGL
(docs/PICTURES.md), so the keys stand beside it.

## Not yet

- **Talk.** The view has its **Talk** key already, grey and saying "Coming soon": the screen's microphone to the
  doorbell's speaker while the key is held, through Home Assistant's two-way audio for cameras once that is there
  (docs/PLATFORM_PLAN.md, section 5). Not every doorbell has a backchannel.
