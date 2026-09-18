# Home Assistant ESP Screens

Thank you! I work on this project with a lot of love, and every bit of support helps. I truly love the Home Assistant community.

<a href="https://buymeacoffee.com/f5j9jnkmhpv"><img src="https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=f5j9jnkmhpv&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" alt="Buy me a coffee" height="42"></a>

<p align="center">
  <img src="docs/images/photo-guition-page-2.jpg" width="49%" alt="The Guition 4-inch screen on a table: the second page with scenes and scripts, the robot vacuum and a table lamp with a brightness slider">
  <img src="docs/images/photo-guition-vacuum.jpg" width="49%" alt="The vacuum card on the Guition: docked and charging, start cleaning and dock, the cleaning mode, suction and water">
</p>

**A touch screen for every room that you lay out yourself, and manage from Home Assistant. Incredibly easy to set up and to use.**

**Why.** Your phone is in the other room and a tablet on the wall is expensive. A small ESP32 touch
panel costs a fraction of that, sits on a table or in a wall box, and is always at hand for the
lights, the heating or the vacuum.

**What.** Firmware for two affordable panels, the 2.8-inch CYD and the 4-inch Guition, with up to
48 tiles over eight pages: lights, climate, blinds and curtains, the vacuum, media, the weather,
history graphs, clocks and timers, and on a Guition your cameras. A tile can take the whole page, one big switch you push without
looking, and a tile can go to another page. An automation can put an alert on every screen when someone rings
the bell, and a Guition shows who is there with the doorbell camera's picture. A tap can run any
action Home Assistant has for a tile, and Dark mode suits a screen beside the bed.

**How.** ESP Screen Manager is an app inside Home Assistant. It flashes a new screen over USB, updates
it over Wi-Fi and sends it your tiles. Changing a screen is pick, drag and **Save & send**:
no reflash, no YAML to write, no blueprint, MQTT or token. Brightness, night hours and Dark mode can
also be changed on the screen or by an automation, and your own YAML for one screen survives every update.

**[Install it](#installing-from-home-assistant)** · [Full reference](README_EXTENDED.md) · [What's new](screen_manager/CHANGELOG.md)

## In real life

A Guition in the living room, 37 seconds in one take: tapping tiles, swiping through the pages,
opening cards and a history graph, while the lamp behind it goes from purple to orange.

https://github.com/user-attachments/assets/f9f6a933-d388-4c8b-9c9a-011dfa37617b

<p align="center">
  <img src="docs/images/photo-guition-home.jpg" width="32%" alt="The Guition on a wooden sideboard beside a glowing purple lamp: the living room page with the airco, an analog clock with the date, two scenes and a dimmer at 36 percent">
  <img src="docs/images/photo-guition-history.jpg" width="32%" alt="The same screen showing a temperature history over 24 hours, with its highest and lowest point marked and the 1 hour, 24 hours and 1 week keys">
  <img src="docs/images/photo-guition-light.jpg" width="32%" alt="The light card of the purple lamp: the colour slider at 304 degrees, the brightness slider at 20 percent and the effects key at the top right">
</p>
<p align="center"><sub>Real photos, not renders: the 4-inch Guition next to the lamp it controls.</sub></p>

## On the screen

<p align="center">
  <img src="docs/images/guition-home.png" width="32%" alt="Guition 4-inch screen: an analog clock with the date, a temperature graph, the weather forecast, a lamp and presence">
  <img src="docs/images/guition-controls.png" width="32%" alt="Double-width tiles with direct control: the heating setpoint, a dimmer and the Sonos volume">
  <img src="docs/images/guition-page-4.png" width="32%" alt="An energy graph, the robot vacuum, a coffee machine, a fan and a good-night script with pastel backgrounds">
</p>
<p align="center">
  <img src="docs/images/guition-full-light.png" width="32%" alt="A full-page tile: one big amber light switch that fills the screen, so you push anywhere without looking">
  <img src="docs/images/guition-full-menu.png" width="32%" alt="Navigation tiles: Heating, Blinds and Weather each open their own page, next to a person and a lamp">
  <img src="docs/images/guition-full-climate.png" width="32%" alt="A full-page heating tile: the room temperature big in the middle, the mode keys at the bottom">
</p>
<p align="center">
  <img src="docs/images/guition-weather.png" width="32%" alt="Weather card: current weather, the coming hours and the coming days with chance of rain">
  <img src="docs/images/guition-climate.png" width="32%" alt="Climate card: the target temperature between big minus and plus keys, the mode keys, and fan and swing choices">
  <img src="docs/images/guition-light.png" width="32%" alt="Light control: color, color temperature and brightness">
</p>
<p align="center">
  <img src="docs/images/guition-vacuum.png" width="32%" alt="Vacuum card: docked and charging, start and dock, the cleaning mode vacuum, vac and mop or mop, suction and water">
  <img src="docs/images/guition-blind.png" width="32%" alt="Cover card for a venetian blind: its battery, the position slider with the blind hanging from the top, the tilt slider over slats, and open, stop and close">
  <img src="docs/images/guition-history-touch.png" width="32%" alt="A finger on the history graph: the top of the card shows the average of that hour and its time, the graph stays as it is">
</p>
<p align="center">
  <img src="docs/images/guition-effects.png" width="32%" alt="The effects page of a WLED lamp: the effect, colour palette, preset and playlist rows with what they are set to, and the speed and intensity sliders">
  <img src="docs/images/guition-effects-picker.png" width="32%" alt="The effect picker: a drum with every effect Home Assistant lists, TV Simulator in the middle, and the check key at the top right that sends it">
  <img src="docs/images/cyd-effects.png" width="32%" alt="The same effects page on the CYD: four rows and the two sliders in 320 by 240 pixels">
</p>
<p align="center">
  <img src="docs/images/guition-media.png" width="32%" alt="The media card on the Guition: the album cover, the title, artist and album, a progress bar with the elapsed and total time, previous, pause and next keys and the volume slider">
  <img src="docs/images/guition-media-full.png" width="32%" alt="A media player over the whole page: the cover at the left, the track, the bar and the keys beside it, the volume row along the bottom">
  <img src="docs/images/guition-dark-media.png" width="32%" alt="The media card in dark mode: the same cover and keys on a black page">
</p>
<p align="center"><sub>Tap a tile to switch it, hold it for the full card. Keys and sliders right on the tile, pastel colors, a clock, the weather and history you can read with a finger. A lamp with modes (a WLED) gets an effects page with a drum picker, named and filled from what Home Assistant lists for it. The media card shows what plays with its album cover, fetched by ESP Screens like a camera picture (<a href="docs/CAMERA.md">how</a>). Rendered from the firmware's own LVGL code with a demo home.</sub></p>
<p align="center">
  <img src="docs/images/guition-camera-tiles.png" width="32%" alt="Cameras as tiles on the Guition: the front door camera, the garden camera live, the doorbell's last ring, next to the door, the porch light and the garage door">
  <img src="docs/images/guition-camera.png" width="32%" alt="A camera tile tapped: the front door camera full screen, with the round back key and the camera's name at the top">
  <img src="docs/images/guition-alert-camera.png" width="32%" alt="The same camera in an alert: its picture across the top of the card, with the card's rounded corners">
</p>
<p align="center"><sub>Cameras are tiles too, not only part of an alert: any camera or snapshot in Home Assistant (a doorbell's last ring, for example) goes on a Guition like any other tile. Tap it for the picture full screen, refreshed every four seconds; an alert can carry the same picture. The CYD has no memory for pictures (<a href="docs/CAMERA.md">how it works</a>).</sub></p>
<p align="center">
  <img src="docs/images/cyd-home.png" width="32%" alt="CYD 2.8-inch screen: the weather forecast, a kitchen timer, the coffee machine, a lamp and power usage as a large value">
  <img src="docs/images/cyd-page-2.png" width="32%" alt="Second CYD page: Sonos volume, presence, a scene and an energy graph">
  <img src="docs/images/cyd-weather.png" width="32%" alt="The weather card on the CYD: current weather, the coming hours and the coming days">
</p>
<p align="center">
  <img src="docs/images/cyd-tiles-controls.png" width="32%" alt="The CYD with heating mode keys, playback keys for the radio and a ceiling fan's speed slider">
  <img src="docs/images/cyd-vacuum.png" width="32%" alt="The vacuum card on the CYD: state, battery and charging, clean and dock, the cleaning mode, suction and water">
  <img src="docs/images/cyd-history.png" width="32%" alt="The history card on the CYD: power over 24 hours with its highest and lowest moment, an axis in watts and clock times">
</p>
<p align="center">
  <img src="docs/images/cyd-media.png" width="32%" alt="The media card on the CYD: the player's icon where the cover would be, the title, artist and album, the bar with its times, the keys and the volume slider">
  <img src="docs/images/cyd-media-full.png" width="32%" alt="A media player over the whole CYD page: the icon at the left, the track and the keys beside it, the volume row along the bottom">
  <img src="docs/images/cyd-dark-media.png" width="32%" alt="The media card on the CYD in dark mode">
</p>
<p align="center"><sub>The same cards on the 2.8-inch CYD, 320 × 240. The CYD has no memory for pictures: its media card shows the player's icon in the cover's place.</sub></p>
<p align="center">
  <img src="docs/images/guition-dark-home.png" width="32%" alt="Dark mode on the Guition: the same home page with a black page, graphite cards and soft white text, the clock, the temperature graph, the weather, a lamp and presence">
  <img src="docs/images/guition-dark-controls.png" width="32%" alt="Dark mode with direct control: the heating setpoint, the dimmer's slider and the Sonos volume keep their colours">
  <img src="docs/images/guition-dark-page-4.png" width="32%" alt="Dark mode with pastel backgrounds: the coffee machine and the good-night script keep their colour, deeper">
</p>
<p align="center"><sub>Dark mode, for a screen beside the bed: the same pages, darker. It is a switch on the screen, in ESP Screens and in Home Assistant, so an automation can turn it on at bedtime.</sub></p>
<p align="center">
  <img src="docs/images/guition-settings-screen.png" width="32%" alt="The settings page on the Guition, Screen: the 12 or 24-hour clock, back to page 1 by itself and after how long, also on standby and swiping between pages, with the page buttons and the rotation on its second page">
  <img src="docs/images/guition-settings.png" width="32%" alt="The settings page on the Guition, Brightness: the brightness with minus and plus, Dark mode off, Auto standby on, standby after 10 minutes and the standby brightness">
  <img src="docs/images/guition-dark-settings.png" width="32%" alt="The same Brightness page right after turning Dark mode on: a black page with graphite rows and soft white text">
</p>
<p align="center"><sub>Settings on the screen itself: hold the top bar. The same brightness, Dark mode, standby, night hours, clock and rotation as in ESP Screens, and every one of them is an entity in Home Assistant.</sub></p>

## Managed from Home Assistant

<p align="center">
  <img src="docs/images/editor.png" width="98%" alt="ESP Screens in Home Assistant: your screens in the sidebar, the pages of the living room screen side by side with their top bar, and the entity library on the right">
</p>
<p align="center"><sub>ESP Screens, a page in Home Assistant: your screens on the left, the pages of the chosen screen in the middle with the values Home Assistant reports right now, the library on the right.</sub></p>
<p align="center">
  <img src="docs/images/editor-tiles.png" width="63%" alt="Choosing tiles: the pages of the screen side by side, next to the library with its search and filters">
  <img src="docs/images/editor-tile-settings.png" width="33%" alt="Tile settings of the curtains in the drawer: double-width with open, stop and close on the tile, what a tap does, and the pastel background">
</p>
<p align="center"><sub>Search your home, drop a tile on the preview, tap it for its name, width, control and color, and for what a tap does: open its card, switch it, or run any action Home Assistant has for it, such as the curtains to 50 %. Save, and the screen has it. ⌘K searches screens, entities and actions; Identify blinks a screen so you know which one it is.</sub></p>
<p align="center">
  <img src="docs/images/editor-top-bar.png" width="31%" alt="Add to the top bar, in the drawer: the time, an analog clock, the date, suggestions from your own home and any entity">
  <img src="docs/images/editor-settings.png" width="65%" alt="Settings in ESP Screens: New screen and Firmware & USB, the firmware updates, the Alerts cheatsheet, and the Claude skill">
</p>
<p align="center"><sub>A top bar built from your own home, firmware updates over Wi-Fi (every night if you like), and a skill so Claude can rearrange your screens.</sub></p>
<p align="center">
  <img src="docs/images/editor-screen-settings.png" width="98%" alt="The Screen settings tab in ESP Screens: Brightness with Dark mode and standby, Night with its hours and brightness, and Screen with the clock, back to page 1, swiping, the page buttons and the rotation">
</p>
<p align="center"><sub>Screen settings apply at once, and a change made on the screen or by an automation shows up here too.</sub></p>
<p align="center">
  <img src="docs/images/editor-override-yaml.png" width="50%" alt="Override YAML for the living room screen: a small file of its own, loaded after the shared package, here with the example that changes the display controller">
</p>
<p align="center"><sub>Other hardware, such as a different display controller? Every screen has an Override YAML of its own, checked by ESPHome before a build and kept through every update.</sub></p>

## Alerts

<p align="center">
  <img src="docs/images/guition-alert-camera.png" width="41%" alt="An alert on the Guition with the front door camera's picture across the top: someone is at the door, with a Coming button">
  <img src="docs/images/guition-camera.png" width="41%" alt="The front door camera full screen on the Guition, with the round back key and the camera's name at the top">
</p>
<p align="center"><sub>Someone at the door? One event in an automation wakes every screen and shows it. Add the doorbell camera and a Guition shows who is there; tap the picture, or a camera tile, for the camera full screen, refreshed every few seconds. <a href="docs/CAMERA.md">Camera images</a>.</sub></p>
<p align="center">
  <img src="docs/images/guition-alert.png" width="41%" alt="An alert on the Guition: someone is at the door, with a Coming button">
  <img src="docs/images/editor-alerts.png" width="53%" alt="The Alerts cheatsheet in ESP Screens: the action name of every screen, ready to copy">
</p>
<p align="center"><sub>Any alert, on one screen or all of them, in a pastel color of your choice. <a href="README_EXTENDED.md#alert-from-an-automation">How alerts work</a>.</sub></p>

## Installing from Home Assistant

### Which screen

| Screen | Resolution | Display / touch |
| --- | --- | --- |
| CYD ESP32-2432S028 | 320 × 240 | ILI9341 / resistive XPT2046 |
| Guition ESP32-S3-4848S040, 4 inch | 480 × 480 | ST7701S RGB / capacitive GT911 |
| Guition JC8012P4A1, 10.1 inch | 1280 × 800 | MIPI-DSI / capacitive GSL3680 |

Use these exact board variants: similar-looking product names can have different
controllers or connectors. Wallbox relays are not controlled.
ESP Screens builds with its own **ESPHome 2026.9.0**. The firmware also builds in your own ESPHome Device Builder
with ESPHome 2026.6.2 or newer.

### Do I need ESPHome?

**You don't need to install the separate ESPHome Device Builder app.**
ESP Screen Manager already includes the ESPHome CLI and can build firmware itself,
install it via USB or give you the file to put on the screen from your own computer,
and later update it wirelessly over OTA.

**You do need to pair the flashed screen via the ESPHome integration in HA.**
That pairing lives under **Settings → Devices & services**, not in the
App store. Add the discovered device there. If it doesn't appear automatically,
choose **Add integration → ESPHome** and enter the screen's IP address.
If asked for a key, use the `api.encryption.key` from your own device YAML,
and grant the device permission to perform Home Assistant actions.

| Component | Needed? | What for? |
| --- | --- | --- |
| ESP Screen Manager app | Yes, for this installation route | Installing firmware, managing tiles, and sending current data to the screen |
| ESPHome Device Builder app | No, optional | Alternative editor and firmware installer; the same CLI is already in ESP Screens |
| ESPHome integration in HA | Yes, pair every screen | The connection between Home Assistant and the physical screen |

So a fresh installation without ESPHome Device Builder also works. If there's
no ESPHome `secrets.yaml` yet, our wizard asks for Wi-Fi once and
stores it locally. Existing Wi-Fi secrets are reused. API and OTA keys
are generated per new screen and stay in that device's own profile.

### Step by step

For Home Assistant Container (Docker) without the App store, follow [ESP Screens with Docker](docs/DOCKER.md).

For Home Assistant OS with Apps/Add-ons on **aarch64 or amd64**:

1. Open the App store and add this repository:
   `https://github.com/MaxGramser/homeassistant_espscreen`.
2. Install **ESP Screen Manager**, start the app, and open **ESP Screens**.
   ESPHome Device Builder is optional: the ESPHome CLI is already in this app.
3. Connect the screen with a USB data cable to the **Home Assistant machine**
   and choose **New screen** in the sidebar: CYD, 4-inch Guition, or 10.1-inch JC8012P4A1, a name, the USB port, and
   **Install**. If Wi-Fi is missing from the ESPHome `secrets.yaml`, the window
   asks for it once and ESP Screens only adds the missing lines. The profile
   with unique API and OTA keys goes into the ESPHome folder; the build
   and flash run in the same window (a first build takes a few minutes on a
   Raspberry Pi). Each screen gets its own profile.
   Is Home Assistant on a server or in a virtual machine, out of reach of the screen?
   Choose **Download** under **Install via**: ESP Screens builds the firmware, and you put it
   on the screen from your own computer with [ESPHome Web](https://web.esphome.io) in Chrome
   or Edge. After that, updates go over Wi-Fi as usual.
4. **CYD:** go through the calibration on the screen. **4-inch Guition:** uses GT911.
   **JC8012P4A1:** uses GSL3680. Both Guition variants report pixel coordinates
   without resistive calibration. Then pair the discovered ESPHome device in
   **Settings → Devices & services** using the API key the window
   shows after installation (copy button). Grant the device permission to
   perform Home Assistant actions.
5. Select the screen in ESP Screens, choose your tiles, and click
   **Save & send**. Then test the physical controls.

<p align="center">
  <img src="docs/images/editor-new-screen.png" width="37%" alt="New screen in ESP Screens: choose the board, give it a name, pick the USB port and install">
  <img src="docs/images/editor-tiles.png" width="59%" alt="Choosing tiles: the pages of the screen side by side, next to the library with its search and filters">
</p>
<p align="center"><sub>New screen (step 3) and choosing your tiles (step 5).</sub></p>

New firmware goes on over Wi-Fi with the **Update** button of a screen in ESP Screens, or by itself
every night if you turn that on under **Settings**; **Firmware & USB → Wi-Fi / OTA** in the sidebar
installs it by hand. For an existing screen, always use the existing profile; creating a new
installation profile generates new keys.

The [complete installation guide](docs/EASY_SETUP.md) walks through every step in more detail.

## More

- **[Full reference](README_EXTENDED.md):** every card and setting, alerts and wake/sleep from an
  automation, the top bar, the settings page on the screen, and how updates keep your settings.
- [Guition hardware, mounting, and rotation](docs/GUITION.md) ·
  [CYD calibration and USB diagnostics](docs/CALIBRATING.md) ·
  [Troubleshooting](docs/TROUBLESHOOTING.md) ·
  [Release history](screen_manager/CHANGELOG.md)

## Credits and license

The very first version started from Adrian Kuehlewind's
[ESPHome-touch-display-mount](https://github.com/akuehlewind/ESPHome-touch-display-mount).
Little of that code is left, but his repository has 3D-printable desk, under-desk, wall and flush
mounts for the CYD.

The front door in the camera pictures is a photo by
[Virginia Marinova](https://unsplash.com/photos/the-door-welcomes-with-plants-on-both-sides-80uwJgdeqWg) on Unsplash.

ESP Screens is MIT licensed, see [LICENSE](LICENSE).
