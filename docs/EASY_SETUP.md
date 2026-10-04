# Installing and managing from Tessera

A new screen, from USB to everyday use

With **Tessera Screen Manager**, you choose your tiles in Home Assistant. You search by
name, device, room, or entity ID, arrange them in the order you want, and click
**Save & send**. After that, the status stays automatically up to date.
You don't need to **reflash** for different tiles.

This works with Home Assistant OS on a 64-bit Raspberry Pi or an amd64 machine,
and one of these exact screen variants. The ESPHome CLI is included in Tessera Screen Manager;
ESPHome Device Builder is optional:

| Choice | Hardware |
| --- | --- |
| CYD, 2.8 inch | ESP32-2432S028, 320×240, ILI9341 and XPT2046 |
| CYD, 2.8 inch ILI9342 (experimental) | ESP32-2432S028 with an ILI9342 display controller, 320×240, XPT2046 |
| Guition, 4 inch | ESP32-S3-4848S040, 480×480, ST7701S and GT911 |
| Waveshare, 4.3 inch | ESP32-S3-Touch-LCD-4.3, 800×480, ST7262 and GT911 |
| Waveshare, 7 inch (experimental) | ESP32-S3-Touch-LCD-7, 800×480, RGB and GT911 |
| Waveshare, 7 inch 7B (experimental) | ESP32-S3-Touch-LCD-7B, 1024×600, RGB and GT911 ([details](WAVESHARE7B.md)) |
| Sunton, 7 inch (experimental) | ESP32-8048S070, 800×480, RGB and GT911 ([details](SUNTON8048S070.md)) |
| Waveshare 4B, 4 inch (experimental) | ESP32-S3-Touch-LCD-4B, 480×480, ST7701S and GT911 ([details](WAVESHARE4B.md)) |
| Waveshare, 3.5 inch (new) | ESP32-S3-Touch-LCD-3.5, 480×320, ST7796 and FT6336 ([details](WAVESHARE35.md)) |
| Hosyond, 4 inch (experimental) | ESP32-32E 4.0 inch (E32R40T), 480×320, ST7796 and XPT2046 ([details](HOSYOND40.md)) |
| Guition, 3.5 inch (new) | JC3248W535, 480×320, AXS15231B QSPI and AXS15231B touch ([details](JC3248W535.md)) |
| Guition, 10.1 inch (new) | JC8012P4A1, 1280×800, JD9365 MIPI-DSI and GSL3680, ESP32-P4 ([details](JC8012P4A1.md)) |
| Guition, 10.1 inch V2 (experimental) | JC8012P4A1 V2, 1280×800, JD9365 MIPI-DSI and GSL3680, early ESP32-P4 with the newer LCD ([details](JC8012P4A1.md)) |
| Guition, 10.1 inch V3 (experimental) | JC8012P4A1 V3, 1280×800, JD9365 MIPI-DSI and GSL3680, rev3 ESP32-P4 ([details](JC8012P4A1.md)) |
| Guition, 7 inch (experimental) | JC1060P470 or JC1060P470 V2, 1024×600, JD9165 MIPI-DSI and GT911, ESP32-P4 ([details](JC1060P470.md)) |
| M5Stack Tab5, 5 inch (new) | Tab5 ST7121, 1280×720, ST7121 MIPI-DSI and touch, ESP32-P4 ([details](TAB5.md)) |

Other screens with roughly the same name can have different pins. Use
the board profile that matches the hardware. Use a USB cable that supports data.
Wallbox relays are not used by default; a Guition with relays can switch them
through its Override YAML (docs/GUITION.md, Relays).

<a id="1-install-esp-screen-manager"></a>

## 1. Install Tessera Screen Manager

The app is not in the standard App store, so Home Assistant needs its repository first. One click adds it:

[![Add the Tessera repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMaxGramser%2Fhomeassistant_espscreen)

Then continue with step 3. Or add it by hand:

1. Open **Settings → Apps → Install app** (on older HA versions:
   **Settings → Add-ons → Add-on Store**).
2. Open the menu in the top right → **Repositories** and add:
   `https://github.com/MaxGramser/homeassistant_espscreen`.
3. Install and start **Tessera Screen Manager**. Turn on **Start on boot**
   and **Show in sidebar**. Open **Tessera** in the sidebar.

Tessera opens on **Your screens**: every screen in the house with its home page as it looks
right now. Click a screen to change it; the logo at the top of the sidebar brings you back.

This app includes the tested ESPHome 2026.9.0 CLI and runs within your HA login.
A second ESPHome management page, MQTT, blueprint, or long-lived token is not needed.
Use the GitHub version for updates; a local test add-on is a separate app.

## 2. New screen: connecting and installing

1. Connect the screen with a **USB data cable** to the machine running Home
   Assistant. With multiple boards: connect them one at a time for the first
   installation, or check which port belongs to this screen.
2. Click the **+** beside **Screens** in the sidebar of Tessera. New screen walks you through three steps.
   **Screen**: under **Which screen do you have?** pick your board. Type its brand, size or what is printed on
   it to find it, or narrow the list by size. **Set up**: give the screen a name, for example `Kitchen`, and watch
   it appear on the drawing of your screen. A board that can hang both ways asks **Which way will it hang?**
   (**Lying down** or **Standing up**, fixed when the screen is built), and a CYD asks for its **Display
   controller**. The device name (`kitchen`) follows from the name; **Advanced** shows it, lets you choose a
   different one, and lists what the board can and cannot do.
3. Wi-Fi: if `wifi_ssid` and `wifi_password` are already in the ESPHome `secrets.yaml`,
   the screen uses them automatically. If they're missing, or the file doesn't
   exist yet, the Set up step asks for them once and Tessera only adds the
   missing lines to `secrets.yaml`; comments and other secrets are left
   alone. If `secrets.yaml` isn't valid YAML, fix that yourself first.
4. **Install**: choose **USB on Home Assistant** (the port it found has a green light) and click
   **Install**. Tessera stores the profile (`kitchen.yaml`, with unique
   API and OTA keys) in the ESPHome folder, builds the firmware, and writes it
   over USB. The page follows it in steps (getting ready, building the firmware, putting it on the screen,
   starting up), each with how far it is, while the drawing of your screen fills in. **Show details** opens
   ESPHome's own log. A first build takes a few minutes on a Raspberry Pi. You can close the
   page: the installation keeps running and picks back up when you reopen it.
5. When it is done, the page shows what comes next: the pairing steps from chapter 3, with the API key behind
   **Show the API key**. If the build fails, the step it stopped in turns red, the log opens and
   you can **Retry**.

Every screen gets its own profile: four screens means going through **New
screen** four times, with four different names. The shared board package is the
same for every screen; the profile only holds the name, keys, and the Wi-Fi reference.
Keep that profile and reuse it for updates. Going through **New screen**
again for an existing screen generates new keys and is not the
update route.

No USB port in the list? A cable plugged into your laptop isn't visible to the
machine running Home Assistant, and a server or virtual machine may have no USB port
within reach at all. Then put the firmware on the screen from the computer you're using.

**From this browser.** This works in Chrome or Edge on a computer, when Home Assistant is
opened over https (see below):

1. Plug the screen into this computer with a USB data cable.
2. In the Install step of **New screen**, choose **From this computer** and click
   **Connect & install**.
3. The browser asks which port to use: choose the screen's. Tessera first checks that the
   board carries the chip the chosen board needs (an ESP32, ESP32-S3 or ESP32-P4), then builds the
   firmware the same way as over USB. Keep the tab open. As soon as the build is ready, the page
   erases the board and writes the firmware, which takes about two minutes, and the screen
   restarts and joins your Wi-Fi.

A browser only reaches USB ports on a secure page. Home Assistant opened as
`http://homeassistant.local:8123` isn't one: open it over https, for example through your
Home Assistant Cloud address or your own certificate. On a plain http page the option says so and
stays off, and Download below still works. Not in the port list? Use a cable that carries data
(some only charge), and install the driver for the board's USB chip (CP210x, CH340 or CH9102) if
your computer needs one. The board doesn't answer? Hold its **BOOT** button while you choose the
port, until the installation starts.

**Download.** For any other browser:

1. In the Install step of **New screen**, choose **Download the file** and click
   **Build & download**. Tessera builds the firmware the same way; when it's ready,
   the window offers the file, for example `kitchen.factory.bin`.
2. Plug the screen into your own computer with a USB data cable.
3. Open [ESPHome Web](https://web.esphome.io/?dashboard_install) in Chrome or Edge on that
   computer (other browsers can't reach USB), click **Connect** and choose the screen's port.
4. Click **Install** and select the downloaded file. The screen restarts and joins your Wi-Fi.

The file holds your Wi-Fi password and the screen's keys: keep it to yourself. Pairing works
as in chapter 3, and every later update goes over Wi-Fi, so the cable is only needed once.
For an existing profile, both routes are under **Firmware & USB** (in the sidebar): choose the
profile and **This computer · install from this browser** or **Download · flash from your own
computer**. From the browser, Firmware & USB writes the firmware without erasing the board first,
so the screen keeps its settings and touch calibration. That also rescues a screen that keeps
restarting and so never comes online for an update over Wi-Fi.

**Build it yourself.** To build a screen with ESPHome on your own computer instead, choose the screen
in the sidebar, open its details with the arrow at its right and use **Download screen files** (a
screen that isn't in Home Assistant yet has it under its API key). The zip holds the screen's own
YAML, its Override YAML and a `secrets.yaml` with only the secrets the two use, normally the Wi-Fi.
Unpack it and run `esphome run <name>.yaml` in that folder. Like the firmware file, it holds your
Wi-Fi password and the screen's keys. A CYD or a Hosyond you build yourself needs one more step once, for the
partition table its firmware has had since 0.33.1: [UPDATING_4MB_SCREENS.md](UPDATING_4MB_SCREENS.md) says what.

**CYD:** calibration appears on first boot. Calmly tap the visible crosshair
three times, hold each tap briefly, and follow each next crosshair in turn.
There are five positions. The center checks accuracy. On a failed
measurement, the screen asks you to start over. The correction is stored locally
and survives OTA updates. Use the HA device button **Calibrate touch** to
measure again later. For a panel that stays off, or for a measurement report over
USB, see [CALIBRATING.md](CALIBRATING.md).

**Hosyond 4 inch:** its resistive touch calibrates on the first start, the same way as the CYD.

**Every other board:** its capacitive touch reports pixels and its mapping is baked into the board profile; there's no ADC calibration.

## 3. Pair the screen with Home Assistant

This happens in Home Assistant itself, outside Tessera. As long as a profile
hasn't been added to Home Assistant yet, it appears in the sidebar under **Screens**
as a *not yet in Home Assistant* card, with an **Open Devices & services**
button and **Copy API key**; the done screen of **New screen** has the same
button. The card disappears once the screen is in the list.

1. Open **Settings → Devices & services**. Add the discovered ESPHome device.
   Not discovered? Manually add the **ESPHome** integration with the screen's
   IP address, port 6053.
2. Does HA ask for an encryption key? Paste the API key the window shows after
   installation (also found as **api → encryption → key** in the
   profile). Don't use the OTA password. Once the screen is paired, choose it in
   the sidebar, open its details with the arrow at its right, and use **Copy API key**
   there whenever HA asks for it again.
3. On the ESPHome integration, open **Configure** and enable **Allow the device to
   perform Home Assistant actions**. Without this permission, values still show up,
   but the screen can't control lights and devices.
4. Open Tessera. The screen appears within about 30 seconds.

## 4. Choose and edit your tiles

A screen keeps its Wi-Fi awake (`power_save_mode: none`): it is mains-powered, and this way
Home Assistant's messages reach it without waiting for the router. Firmware 0.2.74 and later
do this by themselves; an older screen gets it with its next **Update**. A `power_save_mode`
under `wifi:` in the screen's own ESPHome YAML still wins.

Select your screen, tap the bar at the top of a page to give the screen its name,
and search for entities in the **Library** along the bottom: its head folds it away, and its top edge drags it taller.
With more than one page that bar asks
two things: the **Screen title**, which every page without a title of its own shows, and the
**Title above page N** of the page you tapped, which belongs to that page and travels with it. From
firmware 0.17.0 the screen title may be empty: the top bar then shows only the logo, and a page with a
title of its own still shows that. It has domain filters with
colored icons, a room filter, and **Hide placed**. You can add one tile for every cell of the screen's pages,
48 on a CYD, a 4-inch Guition or the experimental Waveshare 4B (firmware 0.2.62+; see below for older firmware).
The screen preview shows their placement on the screen's own grid, lying down: two columns of three on a CYD, a 4-inch Guition,
the Waveshare 4B or the Hosyond 4-inch, two by two on the Waveshare 3.5-inch and the 3.5-inch Guition, three by three on the Waveshare 4.3-inch,
four by four on the [experimental Waveshare 7-inch](WAVESHARE7.md), the [experimental Waveshare 7B](WAVESHARE7B.md), the [experimental Sunton 7-inch](SUNTON8048S070.md) and the 7-inch Guition, and five by five on the
10.1-inch Guition, either way up (firmware 0.18.0; five by four before, and a saved layout moves on by itself); up to
eight pages and 64 tiles, or more on a board with PSRAM ([TILE_MEMORY.md](TILE_MEMORY.md)). Every tile has a fixed slot that only changes if
you drag it; empty slots stay empty, wherever you leave them. Drag a tile
onto an empty slot and it stays there; drag it onto another tile and the two
swap (the other tile takes the freed-up slot, or otherwise the nearest free
slot); everything else stays put. While dragging, the preview already shows where
everything will land; drop a tile on the page after the last one to start a new page.
The pages stand side by side; **Add page** in the toolbar, or the empty page after the last one, creates
an empty page that's kept, and the **···** menu of every page but the only one has **Remove page**
(app 0.2.123): the page leaves with the tiles in its cells and with the **Go to page** tiles that led to
it, the pages after it move up, and the message offers **Undo**. A page moves as a whole (app 0.2.121):
drag it by its number above it, or press the left and right arrow keys while that number has focus. Its tiles keep
their own cells, its own title goes with it wherever it lands, page 1 included, and a **Go to page**
tile keeps opening the page it means, under its new number.
Click an empty slot to place the next tile from the library
there. Use the arrow keys to move a focused tile.
Click a tile and its settings open in a drawer on the right, with the preview
still in view: a custom name, click behavior, a mini-slider, a large value, a graph
(sensors), a weather forecast (weather), the size: **Normal**, **Double-width**, **1 × 2**, **2 × 2** (firmware 0.3.1+) or **Full
page** (firmware 0.2.62+), and on a screen with more pages the **Page** it is on, to move it without dragging.
A double-width tile for a climate, humidifier, switch, light, fan,
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
- Climate, humidifier, vacuum, and cover: tap to open the control card. Under **On tap**, choose **On / off**
  to open, close, or stop a cover with a tap instead (firmware 0.2.58+); holding it still opens the card.
  Tessera offers **On / off**, a small slider, and direct controls only when Home Assistant has
  the action for that entity. **Perform action** runs any action Home Assistant offers for the
  entity, such as **Set cover position** with a position, under Home Assistant's own names
  (firmware 0.2.58+).
- Long press a fan: speed, if the device supports percentages.
- Scene/script: tap to run; button/input_button: tap to press.
- Automation: tap to turn it on or off, and hold the tile to run its actions now, as **Run actions** does in Home
  Assistant (its conditions are skipped). Under **On tap**, **Run automation actions** swaps the two: a tap runs it and holding the
  tile turns it on or off. The tile then looks like a script's button, coloured while the actions run (firmware 0.7.0+).
- Remote: tap for its card with the power key and, where the remote has them, its activities, or for an Apple TV,
  Android TV, Roku and others a keypad with arrows, OK, Back, Home and the volume (firmware 0.22.0+). For
  a key such as Play or Menu, add the remote again with **On tap** set to **Perform action** and **Send command**, and
  pick the command from the list under the field (Android TV, Apple TV, Roku and others) or type it as Home Assistant
  knows it (Harmony, Broadlink).
- Media player: tap for the media card with the cover (boards with camera pictures), the keys, and the volume row:
  volume down, the slider and volume up, as on the screensaver. Hold volume down to mute; the next tap on either key
  takes the mute off. A player Home Assistant can turn off has its power key at the top right (firmware 0.39.0). The
  speaker it plays on is at the top of the card; tap it to choose another. A player that groups (Sonos and others that
  report it) lists the speakers it can play together with: the plus at the end of a row adds one, the tick takes it out,
  and each speaker in the group has its own volume. A speaker whose library holds your Spotify account is a speaker of
  the Spotify tile too: pick it and the music moves there, and the card follows it. Inputs, such as a Sonos's TV input or
  its favourites, are behind their own key at the end of the volume row (firmware 0.26.0+). Where Home Assistant can
  browse the player, the library key beside it opens its library down to a page of covers, and a tap plays one (firmware 0.24.0+, boards with camera
  pictures). **Display → Favourite** makes the tile play one playlist, album or artist you pick from that library, on
  the speaker you choose. A new media tile shows its cover by default on a board with pictures.
- Camera or image (every board except the CYD, the Waveshare 3.5-inch and the Hosyond 4-inch): tap for the
  picture full screen, refreshed every four seconds. **Display → Live picture** fills the tile itself, on every size, and refreshes every 5, 10, 15 or 30 seconds (firmware 0.3.7+, [CAMERA.md](CAMERA.md)).
- Alarm panel: tap for its card with a key per mode, and a keypad when the panel asks for a code (firmware 0.3.3+).
- A *Go to page* tile: tap to open its page.
- Sensor, number, binary sensor, and person: tap for the history card, for 1 hour,
  24 hours, or 1 week. Long press a switch for its history. A sensor's graph on the tile
  shows 1, 6, or 24 hours.
- Select/input_select: tap for a list of its options with a check at the current one (firmware 0.3.3+).

From firmware 0.2.62, one tile fits in every cell of up to eight pages, 64 tiles at most (48 on a CYD or a 4-inch
Guition). From firmware 0.18.0 every screen has all eight pages and a page need not be full; before, a bigger grid had
as many pages as 64 tiles fill (seven on the Waveshare 4.3-inch, four on the 7-inch boards, three on the 10.1-inch
Guition). From firmware 0.34.0 a board with PSRAM holds more: up to 128 tiles on 24 pages on an ESP32-S3 board and 256
on 16 pages on an ESP32-P4 board, as many as the screen's memory takes. The editor shows that memory beside the tile
count, and a tile that no longer fits can't be added ([TILE_MEMORY.md](TILE_MEMORY.md)). Firmware 0.2.7 to
0.2.61 keeps the limit of twenty (four pages) and older firmware ten, until you
update. In the **Screen settings** tab, **Swipe between pages** turns on swiping.
On a board with capacitive touch (every board but the CYD and the Hosyond, firmware 0.2.24+), you then swipe inward from the left or right
edge, like the back-swipe gesture on a phone; slow or fast, and a swipe starting in the
middle of the screen does nothing, so tapping and dragging tiles never
accidentally changes pages. On the CYD and the Hosyond, it stays a quick swipe across the screen. Sliders
only control their value; detail menus and standby don't change pages. Swiping up from the
bottom edge goes back to the Home page (firmware 0.2.100+; page 1 unless you chose another page as Home, [PAGES.md](PAGES.md)).
With firmware 0.28.0+ it works wherever you are, like the home gesture on a phone: an open card, a camera or the
settings page closes on the way. Swiping down from the top edge opens the screen's settings page. A swipe that starts on
a slider stays that slider's. The CYD and the Hosyond take both from a band along the top and bottom edge as well, and
a quick swipe up anywhere over the tiles still goes home there. Every swipe that is
taken lights the edge it came from for a quarter of a second, so the screen answers the gesture
before the new page is drawn.

A page holds the board's grid of tiles, six on a CYD or a Guition. Under the tiles, the page buttons: a chevron in each half of the
bar and a dot per page between them; tap anywhere in the left or right half. With six or
fewer tiles they disappear and the tiles grow into their room (firmware 0.2.69+). **Page
buttons** in the **Screen settings** tab takes them away on a screen with more pages too:
then only swiping and *Go to page* tiles change the page, and the editor says which pages
that leaves out of reach.

Every page carries a home button at the far left of the top bar (firmware 0.2.100+): one tap and the
screen is back on its Home page, from wherever it stands. Since firmware 0.10.0 it is the Tessera logo
in its own colours (a house before that). It stands on the baseline of the page title, the page title
moves behind it with the same air between them as between the logo and the edge of the glass, and the
items on the right of the bar keep every pixel they had. **Show home button** in the **Screen settings** tab, and on
the screen's own settings page, takes it away.
The default standby time is ten minutes. For offline devices, the screen blocks
actions. If the connection to Home Assistant drops, the screen immediately shows
"HA not connected"; if the app sends nothing for two rounds (about five minutes),
it shows "Tessera not active". In both cases, control is blocked
until data is received again.

You can save layouts while a screen is offline. The app sends them
as soon as the screen comes back. The app must keep running for current tile data.

## 5. Updates without losing your settings

| What changes? | What do you do? | What's kept? |
| --- | --- | --- |
| Different entities, names, or order | Save in Tessera | Wi-Fi, keys, calibration |
| New management page/app version | App store → Tessera Screen Manager → Update | All layouts in `/data/screens.json` |
| New screen feature/card | The **Update** button on the screen, or **Update automatically every night** under Settings (manually: Firmware & USB → Wi-Fi / OTA) | Own YAML, keys, and CYD calibration; the app resends tiles |

The device's own YAML references the firmware packages on `main`. On a new build,
ESPHome fetches the latest published package and component code. So you don't
replace your own YAML with a new downloaded file. Wi-Fi, name, and keys
live outside the shared package and stay the same.

### Hardware-specific YAML overrides

Each screen also has a small local file beside its profile, for example
`kitchen.local.yaml`. Open the screen and choose **More → Override YAML**. The editor is
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
| `DISPLAY_MODEL` | CYD, Hosyond | ESPHome's `mipi_spi` model of the display controller (`ILI9341`, `ST7789V`, ...) |
| `DISPLAY_DATA_RATE` | CYD, Hosyond | the display's SPI clock (`40MHz`; some boards want `20MHz`) |
| `DISPLAY_INVERT_COLORS` | CYD, Hosyond | `true` for a panel that shows its colours inverted |
| `GRID_ROWS` | 4-inch Guition, M5Stack Tab5, 10.1-inch Guition | 4-inch Guition and Tab5: `4` for four rows of smaller tiles a page instead of three (firmware 0.18.1; the Tab5 from app 0.4.64). 10.1-inch: `6`, `7` or `8` for up to forty tiles a page instead of twenty-five (firmware 0.35.0). New screen asks on each |
| `BACKLIGHT_FREQUENCY` | CYD, 4-inch Guition, 3.5-inch Guition, Waveshare 4B, Waveshare 3.5, Hosyond | the backlight's PWM frequency (the 4-inch Guition runs `150Hz` since firmware 0.3.5, the CYD and the Hosyond `1000Hz` since firmware 0.29.0, the Waveshare 4B `300000Hz` since firmware 0.39.0) |

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

Make a Home Assistant backup before updates, including Tessera Screen Manager and
the device's own ESPHome configurations. **Removing/reinstalling** an app is not the same
as updating; that can wipe the data folder. Keep the device name and the
entity ID of **Tile settings** the same, so the existing layout stays linked.

Update Tessera Screen Manager first, then update the screens. The page-owned layout
release changes the storage and firmware protocol. New firmware connected to an
older app displays "Configuration problem. Update add-on." Screens can update at
different times: the new app keeps sending compatible layouts to older firmware.

The app saves the original layout file as `screens.v1.backup.json` before migrating
it once. Returning to an older app requires your backup or that original file and
loses layout edits made after migration. A firmware rollback alone does not undo
the storage migration. See [PAGES.md](PAGES.md) and [RELEASING.md](RELEASING.md).
Reload any editor tabs left open during the update before saving changes.

## 6. Removing a screen

A screen you no longer use goes in one place: choose it in the sidebar, open its
details with the arrow at its right, and click **Remove screen**. The list in Tessera is Home Assistant's own, so removing
only the YAML in ESPHome leaves the screen in the list. What the button does:

- Home Assistant loses the screen's ESPHome integration, with its device and all
  of its entities. Anything that used those entities, such as an automation or a
  dashboard card, loses them too.
- The screen's own YAML profile and its `.local.yaml` leave the ESPHome folder,
  along with what the app built from them. A screen installed outside Tessera
  has no profile there, and nothing in that folder is touched.
- The tiles, the screen settings and the update history kept in the app are gone.

The page names all of this before it asks. A screen that is still running and on
Wi-Fi announces itself to Home Assistant again, so erase or unplug it first if it
should stay away.

## If something doesn't work

The screen says what it is doing while it starts (firmware 0.38.0): the Wi-Fi network it connects to, its address once
it has one, whether Home Assistant came and how many tiles have arrived, each with how long it has waited. When the
Wi-Fi doesn't work it says why, as far as it can tell: the network isn't found, the password isn't accepted, or the
signal is too weak. A step that takes more than 30 seconds adds what usually fixes it, and when Home Assistant tried to
connect with a key that is not this screen's, the screen says so at once. Once the screen runs, **This screen** on its
settings page shows the network and its signal, and the **Wi-Fi signal** item can stand in the top bar. A tap that Home
Assistant ignores says "No answer" and, the first time, shows where to allow the screen's actions.

- **No screen in the list:** check that the new Easy Setup firmware is running,
  the ESPHome integration is connected, and the **Tile settings** text entity
  isn't disabled. The old manual firmware doesn't publish that by default.
- **Tiles show but no actions:** grant the device permission for HA actions.
- **Unavailable:** check that the selected entity exists in HA and is
  available. A renamed entity ID needs to be chosen again.
- **No OTA:** check Wi-Fi/IP and the original OTA password. If needed,
  use the same own YAML over USB. Don't generate a new identity.
- **New Wi-Fi network or password:** change `wifi_ssid` and `wifi_password` in ESPHome's
  `secrets.yaml`. A screen that can't reach the old network can't be updated over Wi-Fi, so:
  - Most boards open a fallback hotspot about 90 seconds after they lose their network, named `Tessera` and the
    screen's name (`<screen name> Setup` on a screen made before app 0.4.63, until its next update). The screen shows
    the hotspot's name, its password and a QR code: point a phone's camera at the code to join, or use the password
    under `wifi:` → `ap:` in the screen's own YAML. Pick the new network on the page that opens.
  - A CYD and the other boards with 4 MB of flash have no hotspot (app 0.4.5+): it would take
    some 90 KB of their update slot. Connect the screen to a computer over USB and install its own
    profile again under **Firmware & USB**. The name, the keys and the calibration stay.
- **Build fails:** read the first error, check the ESPHome version and internet for
  GitHub/font downloads.
- **Build is slow, or the log says `Killed signal terminated program cc1plus`:** the machine is short of memory.
  Compiling a screen's firmware needs about 1.5 GB free for its largest file. Before a build the app reads how much is
  free and runs fewer compilers at once when needed, and when Linux stops a compiler all the same it builds again with
  one compiler at a time, from where it stopped; the installer shows a card that says so (app 0.4.65). That is slower,
  but it finishes. When even one compiler is more than the machine has, the card says how much is free and how much
  is needed: stop a few add-ons for a while or give the machine more memory, then try again. Or compile on a more
  powerful computer with ESPHome Device Builder, with the same YAML.
- **Migrating an existing manual screen:** keep the old YAML and carry over the
  existing device name, API key, and OTA password into the new installation profile.
  Then choose the tiles in the app. The old fixed tile substitutions aren't
  automatically imported into the new management page.

HA Container without Supervisor has no App store. This installation guide
targets Home Assistant OS; for Home Assistant Container, run the app next to it as in
[Tessera with Docker](DOCKER.md). The development server is not a production route for
a standalone public portal.

HA mechanisms used: [Ingress](https://developers.home-assistant.io/docs/apps/presentation/),
[the internal HA API](https://developers.home-assistant.io/docs/apps/communication/), and
[ESPHome packages](https://esphome.io/components/packages/).


## Adjusting screen settings

Open the screen in Tessera and its **Screen settings** tab. A change there applies at
once; there is nothing to save, and no firmware flash is needed. The same settings are on the
screen itself (swipe down from the top edge or hold the top bar, firmware 0.2.44+) and, with firmware 0.2.49+, on the screen's
device in Home Assistant ([SETTINGS.md](SETTINGS.md)).

| Setting | Options | Default |
|---|---|---|
| Brightness | 5–100% (boards with a dimmable backlight) | 100% |
| Dark mode | On/off: black page, graphite cards, firmware 0.2.54+ | Off |
| Auto standby | On/off | On |
| Standby after | 1–1440 minutes after the last touch | 10 minutes |
| Standby brightness | 0–100%, capped at normal brightness | 20% |
| Night mode | On/off; applies during standby | On |
| Starts / Ends | Night hours, hour and minute, can span midnight | 22:00–07:00 |
| Night brightness | 0–100%, capped at normal brightness | 10% |
| Clock | 24 or 12 hour, the same on every screen: Settings → Language & region in Tessera (firmware 0.2.76+); the Simple dial shows AM or PM beside the time (firmware 0.3.6+); the Flip clock on a card as wide as the page and the bedside clock put it under the time (firmware 0.17.0+) | Follows the language |
| Back to Home | Closes an open card and goes back to the Home page after 30 seconds to 60 minutes without a touch, firmware 0.2.44+ | On, 2 minutes |
| Also on standby | Standby goes back to the Home page too (it always closes an open card) | Off |
| Swipe between pages | Native horizontal swipe, firmware 0.2.7+ | Off |
| Page buttons | Off: no buttons under the tiles, the tiles take their room, firmware 0.2.69+ | On |
| Show home button | The Tessera logo at the far left of the top bar; tapping it goes back to the Home page, firmware 0.2.100+ (a house before firmware 0.10.0) | On |
| Rotation | 0° or 180°, and also 90° and 270° on a square screen; every board from firmware 0.2.80 | 0° |

The Waveshare 4.3-inch and 7-inch have a backlight that is only on or off and no standby, so they show no
Brightness, standby or night rows. In Home Assistant the Back to Home entities keep their older names
(**Back to page 1**, **Back to page 1 after**, **Back to page 1 on standby**) so automations keep working; they
go to the Home page.

Home Assistant shows these settings on each screen's ESPHome device, under *Configuration*:
with firmware 0.2.49+ every one of them, older firmware the switch **Auto standby**
(firmware 0.2.41+) and the numbers **Standby after**, **Normal brightness**,
**Standby brightness** and **Night brightness**. Changing them there, for example from an
automation, also changes them in Tessera and keeps them after a restart. Turning Auto
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
not on every motion. Tessera → Settings → Claude installs a skill that writes such
automations for you.

Night hours use the ESPHome device's timezone and the time from HA.
Without a valid time, the screen uses the regular standby brightness; matching
start and end times turn the night window off. At 0%, only the
backlight turns off: this is not deep sleep and not a screensaver.
The first tap wakes the screen without controlling a device, except on a page that is
one full-page switch (firmware 0.2.65+): there the waking push also switches it.

With firmware 0.2.49+ the screen owns its settings and keeps them in its preferences;
an offline screen shows them as unknown in Tessera and takes no changes until it is back.
Older firmware gets them from the add-on's persistent data, also as soon as it comes back.
ESPHome batches the preference writes (normally up to a minute), so don't unplug the power
right after a change. Existing CYD calibration, tiles, API, and OTA keys are preserved.
Regular HA status updates don't wake the screen and don't reset the standby timer.

A setting that needs newer firmware than the screen has doesn't show in Tessera until
the screen is updated. The tiles remain usable.

The current Guition uses the native ST7701S configuration; see
[the hardware comparison](GUITION_FACTORY_REFERENCE.md). Settings and
tile colors don't change panel timings. Physically check the display and touch.
