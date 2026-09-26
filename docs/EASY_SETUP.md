# Installing and managing from ESP Screens

A new screen, from USB to everyday use

With **ESP Screen Manager**, you choose your tiles in Home Assistant. You search by
name, device, room, or entity ID, arrange them in the order you want, and click
**Save & send**. After that, the status stays automatically up to date.
You don't need to **reflash** for different tiles.

This works with Home Assistant OS on a 64-bit Raspberry Pi or an amd64 machine,
and one of these exact screen variants. The ESPHome CLI is included in ESP Screen Manager;
ESPHome Device Builder is optional:

| Choice | Hardware |
| --- | --- |
| CYD, 2.8 inch | ESP32-2432S028, 320×240, ILI9341 and XPT2046 |
| Guition, 4 inch | ESP32-S3-4848S040, 480×480, ST7701S and GT911 |
| Waveshare, 4.3 inch | ESP32-S3-Touch-LCD-4.3, 800×480, ST7262 and GT911 |
| Waveshare, 7 inch (experimental) | ESP32-S3-Touch-LCD-7, 800×480, RGB and GT911 |
| Waveshare 4B, 4 inch (experimental) | ESP32-S3-Touch-LCD-4B, 480×480, ST7701S and GT911 ([details](WAVESHARE4B.md)) |
| Waveshare, 3.5 inch (new) | ESP32-S3-Touch-LCD-3.5, 480×320, ST7796 and FT6336 ([details](WAVESHARE35.md)) |
| Guition, 10.1 inch | JC8012P4A1, 1280×800, JD9365 MIPI-DSI and GSL3680, ESP32-P4 |
| Guition, 7 inch (experimental) | JC1060P470 or JC1060P470 V2, 1024×600, JD9165 MIPI-DSI and GT911, ESP32-P4 ([details](JC1060P470.md)) |

Other screens with roughly the same name can have different pins. Use
the board profile that matches the hardware. Use a USB cable that supports data.
Wallbox relays are not used by default; a Guition with relays can switch them
through its Override YAML (docs/GUITION.md, Relays).

## 1. Install ESP Screen Manager

1. Open **Settings → Apps → Install app** (on older HA versions:
   **Settings → Add-ons → Add-on Store**).
2. Open the menu in the top right → **Repositories** and add:
   `https://github.com/MaxGramser/homeassistant_espscreen`.
3. Install and start **ESP Screen Manager**. Turn on **Start on boot**
   and **Show in sidebar**. Open the **ESP Screens** web interface.

This app includes the tested ESPHome 2026.9.0 CLI and runs within your HA login.
A second ESPHome management page, MQTT, blueprint, or long-lived token is not needed.
Use the GitHub version for updates; a local test add-on is a separate app.

## 2. New screen: connecting and installing

1. Connect the screen with a **USB data cable** to the machine running Home
   Assistant. With multiple boards: connect them one at a time for the first
   installation, or check which port belongs to this screen.
2. Click **New screen** in the sidebar of ESP Screens, under your screens. Choose CYD
   or Guition and give the screen a name, for example `Kitchen`. The device name
   (`kitchen`) follows from that; use **customize** to choose a different one.
3. Wi-Fi: if `wifi_ssid` and `wifi_password` are already in the ESPHome `secrets.yaml`,
   the screen uses them automatically. If they're missing, or the file doesn't
   exist yet, the window asks for them once and ESP Screens only adds the
   missing lines to `secrets.yaml`; comments and other secrets are left
   alone. If `secrets.yaml` isn't valid YAML, fix that yourself first.
4. Under **Install via**, choose this screen's USB port and click
   **Install**. ESP Screens stores the profile (`kitchen.yaml`, with unique
   API and OTA keys) in the ESPHome folder, builds the firmware, and writes it
   over USB. The ESPHome log and the current phase (building, writing) are in the same
   window; a first build takes a few minutes on a Raspberry Pi. You can close the
   window: the installation keeps running and picks back up when you reopen it.
5. After **Done**, the window shows the API key with a copy button and the
   pairing steps from chapter 3. If the build fails, the log stays open and
   you can **Retry**.

Every screen gets its own profile: four screens means going through **New
screen** four times, with four different names. The shared board package is the
same for every screen; the profile only holds the name, keys, and the Wi-Fi reference.
Keep that profile and reuse it for updates. Going through **New screen**
again for an existing screen generates new keys and is not the
update route.

No USB port in the list? A cable plugged into your laptop isn't visible to the
machine running Home Assistant, and a server or virtual machine may have no USB port
within reach at all. Then put the firmware on the screen from your own computer:

1. Under **Install via**, choose **Download · flash from your own computer** and click
   **Build & download**. ESP Screens builds the firmware the same way; when it's ready,
   the window offers the file, for example `kitchen.factory.bin`.
2. Plug the screen into your own computer with a USB data cable.
3. Open [ESPHome Web](https://web.esphome.io/?dashboard_install) in Chrome or Edge on that
   computer (other browsers can't reach USB), click **Connect** and choose the screen's port.
4. Click **Install** and select the downloaded file. The screen restarts and joins your Wi-Fi.

The file holds your Wi-Fi password and the screen's keys: keep it to yourself. Pairing works
as in chapter 3, and every later update goes over Wi-Fi, so the cable is only needed once.
For an existing profile, the same file is under **Firmware & USB** (in the sidebar): choose the
profile and **Download · flash from your own computer**, then **Build & download**.

**CYD:** calibration appears on first boot. Calmly tap the visible crosshair
three times, hold each tap briefly, and follow each next crosshair in turn.
There are five positions. The center checks accuracy. On a failed
measurement, the screen asks you to start over. The correction is stored locally
and survives OTA updates. Use the HA device button **Calibrate touch** to
measure again later. For a panel that stays off, or for a measurement report over
USB, see [CALIBRATING.md](CALIBRATING.md).

**Guition:** the GT911 touch mapping is baked into the board profile; there's no ADC calibration.

## 3. Pair the screen with Home Assistant

This happens in Home Assistant itself, outside ESP Screens. As long as a profile
hasn't been added to Home Assistant yet, it appears in the sidebar under **Screens**
as a *not yet in Home Assistant* card, with an **Open Devices & services**
button and **Copy API key**; the done screen of **New screen** has the same
button. The card disappears once the screen is in the list.

1. Open **Settings → Devices & services**. Add the discovered ESPHome device.
   Not discovered? Manually add the **ESPHome** integration with the screen's
   IP address, port 6053.
2. Does HA ask for an encryption key? Paste the API key the window shows after
   installation (also found as **api → encryption → key** in the
   profile). Don't use the OTA password. Once the screen is paired, open it in
   the sidebar and use **Copy API key** there whenever HA asks for it again.
3. On the ESPHome integration, open **Configure** and enable **Allow the device to
   perform Home Assistant actions**. Without this permission, values still show up,
   but the screen can't control lights and devices.
4. Open ESP Screens. The screen appears within about 30 seconds.

## 4. Choose and edit your tiles

A screen keeps its Wi-Fi awake (`power_save_mode: none`): it is mains-powered, and this way
Home Assistant's messages reach it without waiting for the router. Firmware 0.2.74 and later
do this by themselves; an older screen gets it with its next **Update**. A `power_save_mode`
under `wifi:` in the screen's own ESPHome YAML still wins.

Select your screen, tap the bar at the top of a page to give the screen its name,
and search for entities in the **Library** on the right. With more than one page that bar asks
two things: the **Screen title**, which every page without a title of its own shows, and the
**Title above page N** of the page you tapped, which belongs to that page and travels with it. It has domain filters with
colored icons, a room filter, and **Hide placed**. You can add one tile for every cell of the screen's pages,
48 on a CYD, a 4-inch Guition or the experimental Waveshare 4B (firmware 0.2.62+; see below for older firmware).
The screen preview shows their placement on the screen's own grid: two columns of three on a CYD, a 4-inch Guition or the Waveshare 4B,
three by three on the Waveshare 4.3-inch, five by four on the 10.1-inch Guition,
and four by four on the [experimental Waveshare 7-inch](WAVESHARE7.md), lying down,
up to eight pages. Every tile has a fixed slot that only changes if
you drag it; empty slots stay empty, wherever you leave them. Drag a tile
onto an empty slot and it stays there; drag it onto another tile and the two
swap (the other tile takes the freed-up slot, or otherwise the nearest free
slot); everything else stays put. While dragging, the preview already shows where
everything will land; drop a tile on the page after the last one to start a new page.
The pages stand side by side; **+ Add page** after the last one creates an empty page that's kept,
and every page but the only one has **Remove page** beside its cell count (app 0.2.123): the page
leaves with the tiles in its cells and with the **Go to page** tiles that led to it, the pages after
it move up, and the message offers **Undo**. A page moves as a whole (app 0.2.121): drag it by the
label above it, or press the left and right arrow keys while that label has focus. Its tiles keep
their own cells, its own title goes with it wherever it lands, page 1 included, and a **Go to page**
tile keeps opening the page it means, under its new number.
Click an empty slot to place the next tile from the library
there. Use the arrow keys to move a focused tile.
Click a tile and its settings open in a drawer on the right, with the preview
still in view: a custom name, click behavior, a mini-slider, a large value, a graph
(sensors), a weather forecast (weather), the size: **Double-width** or **Full
page** (firmware 0.2.62+), and on a screen with more pages the **Page** it is on, to move it without dragging.
A double-width tile for a climate, switch, light, fan,
vacuum, cover, media player, number, select, timer, scene, script, or button gets **direct
control** on the right, like the rows in Home Assistant (for example temperature − / +,
open/stop/close, volume with mute, a toggle); under **Direct control
on the tile**, choose which set, or **None** (firmware 0.2.19+). **Open control** on
a weather tile shows the weather card with the coming hours and days (rain included);
on a climate tile, the card with an on/off button and the mode, fan, and
swing settings. The built-in **Clock**
sits at the top of the library; find sun, timers, and people via the filters. Under
**Pastel background**, choose a custom color with dark text; **Default** restores
the normal look, and **None** drops the card, so the content sits the same size
directly on the screen background (firmware 0.2.16+). This requires firmware 0.2.10+.
Adding without a chosen slot fills the first free slot. Fixed slots and empty
slots work on the screen from firmware 0.2.26 on; older firmware shifts the
tiles up to the first free slot, and the editor notes that below the preview.
The preview shows the values Home Assistant reports right now (app 0.2.73+).
Click **Save & send** to send your changes.

- Light, switch, input_boolean, and fan: tap to turn on/off.
- Long press a light: brightness, rainbow color, and white temperature, as far as
  the light supports those features.
- Climate, vacuum, and cover: tap to open the control card. Under **On tap**, choose **On / off**
  to open, close, or stop a cover with a tap instead (firmware 0.2.58+); holding it still opens the card.
  ESP Screens offers **On / off**, a small slider, and direct controls only when Home Assistant has
  the action for that entity. **Perform action** runs any action Home Assistant offers for the
  entity, such as **Set cover position** with a position, under Home Assistant's own names
  (firmware 0.2.58+).
- Long press a fan: speed, if the device supports percentages.
- Scene/script: tap to run; button/input_button: tap to press.
- Media player: tap for the media card with the cover (Guition), the keys, and the volume.
- Camera or image (Guition): tap for the picture full screen, refreshed every four seconds.
- A *Go to page* tile: tap to open its page.
- Sensor, number, binary sensor, and person: tap for the history card, for 1 hour,
  24 hours, or 1 week. Long press a switch for its history. A sensor's graph on the tile
  shows 1, 6, or 24 hours.
- Select/input_select: open the picker menu.

From firmware 0.2.62, one tile fits in every cell of up to eight pages (48 on a CYD or a 4-inch Guition, 63 over
seven pages on the Waveshare 4.3-inch, 60 over three on the 10.1-inch Guition). The experimental Waveshare 7-inch
holds 64 over four pages lying down, or 56 over four standing up (firmware 0.2.94+). Firmware 0.2.7 to
0.2.61 keeps the limit of twenty (four pages) and older firmware ten, until you
update. In the **Screen settings** tab, **Swipe between pages** turns on swiping.
On the Guition (firmware 0.2.24+), you then swipe inward from the left or right
edge, like the back-swipe gesture on a phone; slow or fast, and a swipe starting in the
middle of the screen does nothing, so tapping and dragging tiles never
accidentally changes pages. On the CYD, it stays a quick swipe across the screen. Sliders
only control their value; detail menus and standby don't change pages. Swiping up from the
bottom edge goes back to page 1 (firmware 0.2.100+), in the same way: from the bottom edge on
the boards that swipe from an edge, a quick swipe up anywhere on the CYD. Every swipe that is
taken lights the edge it came from for a quarter of a second, so the screen answers the gesture
before the new page is drawn.

A page holds the board's grid of tiles, six on a CYD or a Guition. Under the tiles, the page buttons: a chevron in each half of the
bar and a dot per page between them; tap anywhere in the left or right half. With six or
fewer tiles they disappear and the tiles grow into their room (firmware 0.2.69+). **Page
buttons** in the **Screen settings** tab takes them away on a screen with more pages too:
then only swiping and *Go to page* tiles change the page, and the editor says which pages
that leaves out of reach.

Every page carries a house at the far left of the top bar (firmware 0.2.100+): one tap and the
screen is back on page 1, from wherever it stands. It stands on the baseline of the page title
and is a third taller than the bar's own icons, the page title moves behind it with the same
air between them as between the house and the edge of the glass, and the items on the right of
the bar keep every pixel they had. **Show home button** in the **Screen settings** tab, and on
the screen's own settings page, takes it away.
The default standby time is ten minutes. For offline devices, the screen blocks
actions. If the connection to Home Assistant drops, the screen immediately shows
"HA not connected"; if the app sends nothing for two rounds (about five minutes),
it shows "ESP Screens not active". In both cases, control is blocked
until data is received again.

You can save layouts while a screen is offline. The app sends them
as soon as the screen comes back. The app must keep running for current tile data.

## 5. Updates without losing your settings

| What changes? | What do you do? | What's kept? |
| --- | --- | --- |
| Different entities, names, or order | Save in ESP Screens | Wi-Fi, keys, calibration |
| New management page/app version | App store → ESP Screen Manager → Update | All layouts in `/data/screens.json` |
| New screen feature/card | The **Update** button on the screen, or **Update automatically every night** under Settings (manually: Firmware & USB → Wi-Fi / OTA) | Own YAML, keys, and CYD calibration; the app resends tiles |

The device's own YAML references the firmware packages on `main`. On a new build,
ESPHome fetches the latest published package and component code. So you don't
replace your own YAML with a new downloaded file. Wi-Fi, name, and keys
live outside the shared package and stay the same.

### Hardware-specific YAML overrides

Each screen also has a small local file beside its profile, for example
`kitchen.local.yaml`. Open the screen and click **Override YAML**. The editor is
intended for hardware-specific changes such as a different display controller:

```yaml
display:
  - id: !extend my_display
    model: ST7789V
```

ESPHome appends package lists instead of merging them, so `!extend` is what
changes the display the shared package already defines; a bare `id:` would add
a second, incomplete display and the build fails.

For the changes people ask for most, the board offers a substitution, so the
override is one line (app 0.2.127+):

```yaml
substitutions:
  DISPLAY_MODEL: "ST7789V"        # CYD: the display controller
```

A new CYD needs neither: since app 0.2.129 New screen asks which display controller it has and writes the choice
into the screen's own YAML. That line wins over an override, so the override editor refuses the same substitution for
that screen and says where it is set.

| Substitution | Boards | What it changes |
|---|---|---|
| `DISPLAY_MODEL` | CYD | ESPHome's `mipi_spi` model of the display controller (`ILI9341`, `ST7789V`, ...) |
| `DISPLAY_DATA_RATE` | CYD | the display's SPI clock (`40MHz`; some boards want `20MHz`) |
| `DISPLAY_INVERT_COLORS` | CYD | `true` for a panel that shows its colours inverted |
| `BACKLIGHT_FREQUENCY` | CYD, 4-inch Guition, Waveshare 4B | the backlight's PWM frequency (the 4-inch Guition runs `150Hz` since firmware 0.3.5, the CYD `20000Hz`) |

The parts an override names stay the same on every board and in every update:
`my_display` (the display), `ts_touch` (the touch panel), `gpio_backlight_pwm`
(the output that drives the backlight) and `back_light` (the light on it).
docs/PROFILES.md, "What an override may rely on", has the whole list.

This file is loaded after the shared board package and is kept when the app or
firmware package updates. The editor protects the screen's name, Wi-Fi, API,
OTA and package connection. Use **Save & check** before building a custom
configuration. If the complete ESPHome profile is invalid, the firmware build
does not start.

The override is advanced configuration: the display model, dimensions, pins,
touchscreen and initialization sequence must still match the physical board.
For a similar-looking CYD, check the exact USB/controller variant first.

Make a Home Assistant backup before updates, including ESP Screen Manager and
the device's own ESPHome configurations. **Removing/reinstalling** an app is not the same
as updating; that can wipe the data folder. Keep the device name and the
entity ID of **Tile settings** the same, so the existing layout stays linked.

Update ESP Screen Manager first, then update the screens. The page-owned layout
release changes the storage and firmware protocol. New firmware connected to an
older app displays "Configuration problem. Update add-on." Screens can update at
different times: the new app keeps sending compatible layouts to older firmware.

The app saves the original layout file as `screens.v1.backup.json` before migrating
it once. Returning to an older app requires your backup or that original file and
loses layout edits made after migration. A firmware rollback alone does not undo
the storage migration. See [PAGES.md](PAGES.md) and [RELEASING.md](RELEASING.md).
Reload any editor tabs left open during the update before saving changes.

## 6. Removing a screen

A screen you no longer use goes in one place: open it in the sidebar and click
**Remove screen**. The list in ESP Screens is Home Assistant's own, so removing
only the YAML in ESPHome leaves the screen in the list. What the button does:

- Home Assistant loses the screen's ESPHome integration, with its device and all
  of its entities. Anything that used those entities, such as an automation or a
  dashboard card, loses them too.
- The screen's own YAML profile and its `.local.yaml` leave the ESPHome folder,
  along with what the app built from them. A screen installed outside ESP Screens
  has no profile there, and nothing in that folder is touched.
- The tiles, the screen settings and the update history kept in the app are gone.

The page names all of this before it asks. A screen that is still running and on
Wi-Fi announces itself to Home Assistant again, so erase or unplug it first if it
should stay away.

## If something doesn't work

- **No screen in the list:** check that the new Easy Setup firmware is running,
  the ESPHome integration is connected, and the **Tile settings** text entity
  isn't disabled. The old manual firmware doesn't publish that by default.
- **Tiles show but no actions:** grant the device permission for HA actions.
- **Unavailable:** check that the selected entity exists in HA and is
  available. A renamed entity ID needs to be chosen again.
- **No OTA:** check Wi-Fi/IP and the original OTA password. If needed,
  use the same own YAML over USB. Don't generate a new identity.
- **Build fails:** read the first error, check the ESPHome version and internet for
  GitHub/font downloads. If the Raspberry Pi is low on memory, temporarily use a
  more powerful computer to compile; the YAML stays the same.
- **Migrating an existing manual screen:** keep the old YAML and carry over the
  existing device name, API key, and OTA password into the new installation profile.
  Then choose the tiles in the app. The old fixed tile substitutions aren't
  automatically imported into the new management page.

HA Container without Supervisor has no App store. This installation guide
targets Home Assistant OS; for Home Assistant Container, run the app next to it as in
[ESP Screens with Docker](DOCKER.md). The development server is not a production route for
a standalone public portal.

HA mechanisms used: [Ingress](https://developers.home-assistant.io/docs/apps/presentation/),
[the internal HA API](https://developers.home-assistant.io/docs/apps/communication/), and
[ESPHome packages](https://esphome.io/components/packages/).


## Adjusting screen settings

Open the screen in ESP Screens and its **Screen settings** tab. A change there applies at
once; there is nothing to save, and no firmware flash is needed. The same settings are on the
screen itself (hold the top bar, firmware 0.2.44+) and, with firmware 0.2.49+, on the screen's
device in Home Assistant ([SETTINGS.md](SETTINGS.md)).

| Setting | Options | Default |
|---|---|---|
| Normal brightness | 5–100% | 100% |
| Dark mode | On/off: black page, graphite cards, firmware 0.2.54+ | Off |
| Auto standby | On/off | On |
| Standby after | 1–1440 minutes after the last touch | 10 minutes |
| Standby brightness | 0–100%, capped at normal brightness | 20% |
| Night mode | On/off; applies during standby | On |
| Night start/end | Hour and minute, can span midnight | 22:00–07:00 |
| Night brightness | 0–100%, capped at normal brightness | 10% |
| Clock | 24 or 12 hour, the same on every screen: Settings → Language & region in ESP Screens (firmware 0.2.76+); the clock shows no AM/PM | Follows the language |
| Back to page 1 | Closes an open card and goes back to page 1 after 30 seconds to 60 minutes without a touch, firmware 0.2.44+ | On, 2 minutes |
| Also on standby | Standby goes back to page 1 too (it always closes an open card) | Off |
| Swipe between pages | Native horizontal swipe, firmware 0.2.7+ | Off |
| Page buttons | Off: no buttons under the tiles, the tiles take their room, firmware 0.2.69+ | On |
| Show home button | A house at the far left of the top bar; tapping it goes back to page 1, firmware 0.2.100+ | On |
| Guition rotation | 0°, 90°, 180°, 270°, firmware 0.2.9+ | 0° |

Home Assistant shows these settings on each screen's ESPHome device, under *Configuration*:
with firmware 0.2.49+ every one of them, older firmware the switch **Auto standby**
(firmware 0.2.41+) and the numbers **Standby after**, **Normal brightness**,
**Standby brightness** and **Night brightness**. Changing them there, for example from an
automation, also changes them in ESP Screens and keeps them after a restart. Turning Auto
standby off wakes the screen and keeps it on; turning it on counts the standby time from
that moment. To keep a screen on while someone is home and a light is on:

```yaml
alias: Keep the kitchen screen awake
mode: restart
triggers:
  - trigger: state
    entity_id: [person.alex, light.living_room]
actions:
  - if:
      - condition: state
        entity_id: person.alex
        state: home
      - condition: state
        entity_id: light.living_room
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

Every change is saved on the screen, so switch on changes that happen a few times a day,
not on every motion. ESP Screens → Settings → Claude installs a skill that writes such
automations for you.

Night hours use the ESPHome device's timezone and the time from HA.
Without a valid time, the screen uses the regular standby brightness; matching
start and end times turn the night window off. At 0%, only the
backlight turns off: this is not deep sleep and not a screensaver.
The first tap wakes the screen without controlling a device, except on a page that is
one full-page switch (firmware 0.2.65+): there the waking push also switches it.

With firmware 0.2.49+ the screen owns its settings and keeps them in its preferences;
an offline screen shows them as unknown in ESP Screens and takes no changes until it is back.
Older firmware gets them from the add-on's persistent data, also as soon as it comes back.
ESPHome batches the preference writes (normally up to a minute), so don't unplug the power
right after a change. Existing CYD calibration, tiles, API, and OTA keys are preserved.
Regular HA status updates don't wake the screen and don't reset the standby timer.

A setting that needs newer firmware than the screen has doesn't show in ESP Screens until
the screen is updated. The tiles remain usable.

The current Guition uses the native ST7701S configuration; see
[the hardware comparison](GUITION_FACTORY_REFERENCE.md). Settings and
tile colors don't change panel timings. Physically check the display and touch.
