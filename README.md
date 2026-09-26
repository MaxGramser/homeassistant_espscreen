<p align="center">
  <a href="https://tessera-maxgramser.on-forge.com"><img src="docs/images/tessera-mark.svg" width="112" alt="The Tessera logo: four rounded tiles in yellow, blue, purple and green, like a small mosaic"></a>
</p>

<h1 align="center">Tessera</h1>

<p align="center"><b>Touch screens for Home Assistant. A screen for every room, one simple editor.</b></p>

<p align="center">
  <a href="https://tessera-maxgramser.on-forge.com"><b>Website</b></a> ·
  <a href="https://tessera-maxgramser.on-forge.com/docs/getting-started">Get started</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/screens">Supported screens</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/community">Community</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/community/share?type=installation">My screen works</a>
</p>

<p align="center"><sub>Tessera is the new name for ESP Screens. In Home Assistant the app is still called ESP Screen Manager and its panel ESP Screens; the repository, the add-on and your screens stay exactly as they are.</sub></p>

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

**What.** Firmware for affordable panels, five of them today, from the 2.8-inch CYD to the 10.1-inch Guition, with
tiles over up to eight pages, as many per page as the glass holds: lights, climate, blinds and curtains, the vacuum, media, the weather,
history graphs, clocks and timers, your alarm with its keypad, and on every screen but the CYD your cameras. A tile can take the whole page, one big switch you push without
looking, and a tile can go to another page. An automation can put an alert on every screen when someone rings
the bell, and a screen with room for pictures shows who is there with the doorbell camera's picture. A tap can run any
action Home Assistant has for a tile, and Dark mode suits a screen beside the bed.

**How.** ESP Screen Manager is an app inside Home Assistant. It flashes a new screen over USB, updates
it over Wi-Fi and sends it your tiles. Changing a screen is pick, drag and **Save & send**:
no reflash, no YAML to write, no blueprint, MQTT or token. Brightness, night hours and Dark mode can
also be changed on the screen or by an automation, and your own YAML for one screen survives every update.

**[Install it](#installing-from-home-assistant)** · [Website](https://tessera-maxgramser.on-forge.com) · [Pages and navigation](docs/PAGES.md) · [Full reference](README_EXTENDED.md) · [What's new](screen_manager/CHANGELOG.md)

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

## Five screens supported, 2.8 to 10.1 inch

One home, five panels. A screen is built for the glass it runs on: it measures its own canvas at boot and gives a page
the cells that board has, six tiles on the 2.8-inch CYD and twenty on the 10.1-inch Guition, while a tile stays about
the same size in millimetres. The same tiles, the same cards, the same editor; the bigger the glass, the more of your
home fits on one page.

<p align="center">
  <img src="docs/images/boards-scale.png" width="98%" alt="The five supported screens side by side on one scale, each showing a page of the same home: the small 2.8-inch CYD, the square 4-inch Guition, the wide 4.3-inch Waveshare, the 7-inch Waveshare and the large 10.1-inch Guition">
</p>
<p align="center"><sub>To scale, each with the page it fills: the same home on the 2.8-inch CYD, the 4-inch Guition, the 4.3-inch and 7-inch Waveshare, and the 10.1-inch Guition. Rendered from the firmware's own code, one board at a time.</sub></p>
<p align="center">
  <img src="docs/images/board-cyd.png" width="32%" alt="The kitchen page on the 2.8-inch CYD: the weather with five days, a pasta timer, the coffee machine, the kitchen lamp and the power usage">
  <img src="docs/images/board-guition.png" width="32%" alt="The living room page on the 4-inch Guition: an analog clock with the date, a temperature graph, the weather, the table lamp and Sam at home">
  <img src="docs/images/board-waveshare43.png" width="32%" alt="The hallway page on the 4.3-inch Waveshare: a clock, a wide temperature graph, the weather, Sam, the heating with minus and plus, and the table lamp">
</p>
<p align="center">
  <img src="docs/images/board-waveshare7.png" width="49%" alt="The bedroom page on the 7-inch Waveshare: sixteen cells with a clock, a wide temperature graph, the weather, the heating, the ceiling light and Sonos with sliders, the energy graph, the robot and a good-night script">
  <img src="docs/images/board-jc8012p4a1.png" width="49%" alt="The study page on the 10.1-inch Guition: twenty cells with a clock, graphs, the weather, the heating, the ceiling light, a timer, Sonos, the curtains, the power usage, the robot, the coffee machine and a good-night script">
</p>
<p align="center">
  <img src="docs/images/boards-standing.png" width="66%" alt="Two of the same screens built standing up, to scale: the 10.1-inch Guition as a kitchen wall panel with twenty tiles over four columns, and the 7-inch Waveshare by the front door with fourteen tiles in two columns">
</p>
<p align="center"><sub>The same home standing up. Which way a screen hangs is chosen when it is built, and every board that is not square hangs either way, with a grid of its own: the 10.1-inch Guition 4 × 5 instead of 5 × 4, the 7-inch Waveshare 2 × 7 instead of 4 × 4. Which board is which, and what to look for when you buy one: <a href="#which-screen">Which screen</a>.</sub></p>

## Taller tiles, richer cards

<p align="center">
  <img src="docs/images/tall-jc8012p4a1.png" width="98%" alt="A full page on the 10.1-inch Guition: a clock with the date, the weather for five days, a media tile two cells wide and two high with the album cover dimmed behind the title and the play keys, the blinds one cell wide and two high with a position slider, the heating two by two with minus, plus and every mode key, a temperature graph, a table lamp dimmer and a coffee machine switch">
</p>
<p align="center">
  <img src="docs/images/tall-guition-media.png" width="32%" alt="The 4-inch Guition: a media tile two by two with the album cover behind the track, the artist and the previous, pause and next keys, above a table lamp with its dimmer">
  <img src="docs/images/tall-guition-climate.png" width="32%" alt="The heating two by two: the target temperature between minus and plus, the room temperature under it and a row of mode keys, heat lit in orange, above a temperature graph">
  <img src="docs/images/tall-guition-home.png" width="32%" alt="Two tiles one cell wide and two high: the blinds with their position in large type and a slider, and the coffee machine with its icon, name and switch in the middle; the robot vacuum with start, stop and dock below">
</p>
<p align="center">
  <img src="docs/images/tall-waveshare43-media.png" width="49%" alt="The 4.3-inch Waveshare: the media tile two by two with its album cover, a bedroom thermostat one cell wide and two high, a lamp dimmer and a person">
  <img src="docs/images/tall-waveshare43-climate.png" width="49%" alt="The same screen in dark mode: the heating two by two with its mode keys beside the setpoint, the blinds one by two, a temperature graph and the coffee machine">
</p>
<p align="center"><sub>A tile can be 1 × 2 or 2 × 2 cells as well as one cell, double width or the whole page, and the card follows the room it gets: a player shows its album cover behind the track (every screen but the CYD), the heating shows its setpoint and the modes Home Assistant lists for it (the last key opens the card when they do not all fit), a blind shows its position, and its slats where there is room, an on/off tile stands centred with its switch. Every board works out the same card from its own glass. Each page has its own title and top bar, any page can be Home, and a page can stay out of the page dots and be opened from a tile, with a Back key to return. Rendered from the firmware's own LVGL code with a demo home.</sub></p>

## Weather, heating, cameras and your alarm

<p align="center">
  <img src="docs/images/guition-weather-tiles.png" width="32%" alt="The 4-inch Guition with two weather tiles: a wide one with today and the next three days, and a big one listing the days under each other, each with a coloured bar from its low to its high on one scale">
  <img src="docs/images/guition-thermostat-tiles.png" width="32%" alt="Three thermostats: the heating with its setpoint between minus and plus and a bar with Heat and Auto, an airco on cool with heat, cool and more behind three dots, and a short bedroom tile with the stepper on one row">
  <img src="docs/images/guition-camera-fill.png" width="32%" alt="A garden camera on a tile of two by two cells, its picture filling the whole card with the camera's name at the bottom, above the garden lights and the garden temperature">
</p>
<p align="center">
  <img src="docs/images/guition-alarm-tiles.png" width="32%" alt="Four alarm panels as tiles: the house disarmed in grey, the garage armed away in green, the shed arming in orange and the studio armed home in green">
  <img src="docs/images/guition-alarm-card.png" width="32%" alt="The alarm card: the shield in its circle, keys for Home, Away, Night and Vacation, and the Disarmed key">
  <img src="docs/images/guition-alarm-keypad.png" width="32%" alt="The keypad to arm away: four dots for the code, the digits 1 to 0, a clear key and a check key">
</p>
<p align="center">
  <img src="docs/images/waveshare43-new-tiles.png" width="49%" alt="The 4.3-inch Waveshare: a wide weather tile with the coming days, the heating with its stepper, a front door camera filling a tile of two by two cells, and the dryer">
  <img src="docs/images/waveshare43-select-card.png" width="49%" alt="The select card of a washing machine on the 4.3-inch Waveshare: its programmes in two columns, Cotton eco checked, and page dots for the rest">
</p>
<p align="center"><sub>The weather with the coming days, and on a bigger tile the whole week with a bar from each day's low to its high. A thermostat has its − / + and a bar with a key per mode; an airco shows heat and cool first and the rest behind "…". A live camera on a taller tile fills the card with its picture and its name, or shows the whole picture. Your alarm is a tile in Home Assistant's colours, with a key for every mode and Home Assistant's keypad when the panel asks for a code; someone coming in wakes every screen with the keypad to disarm. A select, such as a washing machine's programme, opens a list with a check at the one it is on. On every screen with the memory for it, every page is built ahead and kept, so the next one is there the moment you turn to it. Rendered from the firmware's own LVGL code with a demo home.</sub></p>

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
<p align="center"><sub>Tap a tile to switch it, hold it for the full card. Keys and sliders right on the tile, pastel colors, a clock, the weather and history you can read with a finger. A lamp with modes (a WLED) gets an effects page with a drum picker, named and filled from what Home Assistant lists for it. The media card shows what plays with its album cover, fetched by ESP Screens like a camera picture, and a media tile can show that cover in the icon's place (<a href="docs/CAMERA.md">how</a>). Rendered from the firmware's own LVGL code with a demo home.</sub></p>
<p align="center">
  <img src="docs/images/guition-camera-tiles.png" width="32%" alt="Cameras as tiles on the Guition: the front door camera filling a tall tile with its name at the bottom, a porch camera showing its whole picture with black above and below, the porch light and Sam at home">
  <img src="docs/images/guition-camera.png" width="32%" alt="A camera tile tapped: the front door camera full screen, with the round back key and the camera's name at the top">
  <img src="docs/images/guition-alert-camera.png" width="32%" alt="The same camera in an alert: its picture across the top of the card, with the card's rounded corners">
</p>
<p align="center"><sub>Cameras are tiles too, not only part of an alert: any camera or snapshot in Home Assistant (a doorbell's last ring, for example) goes on a screen like any other tile. Tap it for the picture full screen, refreshed every four seconds, or let the tile itself show its live picture (Display → Live picture, every 15 or 30 s): in the icon's place, or on a taller tile over the whole card, filled or whole, with or without its name; an alert can carry the same picture. Every screen but the CYD, which has no memory for pictures (<a href="docs/CAMERA.md">how it works</a>).</sub></p>
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
  <img src="docs/images/guition-settings-screen.png" width="32%" alt="The settings page on the Guition, Screen: back to page 1 by itself and after how long, also on standby and swiping between pages, with the page buttons and the rotation on its second page">
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
  <img src="docs/images/editor-screen-settings.png" width="98%" alt="The Screen settings tab in ESP Screens: Brightness with Dark mode and standby, Night with its hours and brightness, and Screen with back to page 1, swiping, the page buttons and the rotation">
</p>
<p align="center"><sub>Screen settings apply at once, and a change made on the screen or by an automation shows up here too.</sub></p>
<p align="center">
  <img src="docs/images/editor-override-yaml.png" width="50%" alt="Override YAML for the living room screen: a small file of its own, loaded after the shared package, here with the example that changes the display controller">
</p>
<p align="center"><sub>Other hardware on your board? A CYD with the other display controller is a choice in New screen, and for anything else every screen has an Override YAML of its own, checked by ESPHome before a build and kept through every update.</sub></p>

## In your language

<p align="center">
  <img src="docs/images/guition-german.png" width="31%" alt="A Guition in German: Dienstag 15 Sept. beside the analog clock, Teilweise bewölkt with the days Di Mi Do Fr Sa, the table lamp at 75 %">
  <img src="docs/images/guition-french.png" width="31%" alt="The same screen in French: mardi 15 sept., Éclaircies with the days ma me je ve sa, and Sam is Maison">
  <img src="docs/images/guition-polish.png" width="31%" alt="The same screen in Polish: wtorek 15 wrz, częściowe zachmurzenie with the days wt śr cz pt sb, and Sam is w domu">
</p>
<p align="center"><sub>The same home in German, French and Polish. The screens follow your Home Assistant: its language, its words for a light or a robot, and how your country writes a date, a time and a number — 75 % in German and French, 75% in Polish and English.</sub></p>

The screens, the editor and its messages speak **English (US and UK), Nederlands, Deutsch, Français, Italiano,
Español, Português and Polski**. Nothing to set up: ESP Screens takes the language of your Home Assistant.

<p align="center">
  <img src="docs/images/editor-language.png" width="36%" alt="Language and region in ESP Screens: the screen language set to Home Assistant's language, the time format and the number format, each following the language">
</p>
<p align="center"><sub>Settings → Language & region, when you want something else than Home Assistant's own.</sub></p>

- **The editor** follows the language of your Home Assistant profile, so two people in one house each read their own.
- **A screen** carries one language, built into its firmware: change it and press **Update** on the screen (or let
  the nightly round do it). The clock (24 hours or 12 with AM/PM) and the number format change straight away, on
  every screen at once.
- **Words from Home Assistant stay Home Assistant's**: what a door, an airco or a robot says on a tile and in its
  card is the word its own dashboard shows, in your language.

Most languages still need someone who speaks them to read the texts through, and a new language is one file.
[Translating ESP Screens](docs/TRANSLATING.md) walks through both; a language without a file falls back to English
while it keeps your country's clock and numbers.

## Alerts

<p align="center">
  <img src="docs/images/guition-alert-camera.png" width="41%" alt="An alert on the Guition with the front door camera's picture across the top: someone is at the door, with a Coming button">
  <img src="docs/images/guition-camera.png" width="41%" alt="The front door camera full screen on the Guition, with the round back key and the camera's name at the top">
</p>
<p align="center"><sub>Someone at the door? One event in an automation wakes every screen and shows it. Add the doorbell camera and a Guition shows who is there; tap the picture, or a camera tile, for the camera full screen, refreshed every few seconds. <a href="docs/CAMERA.md">Camera images</a>.</sub></p>
<p align="center">
  <img src="docs/images/guition-alert-choice-colors.png" width="41%" alt="An alert on the Guition asking to open the garage, with a red Decline and a green Accept button side by side">
  <img src="docs/images/editor-alerts.png" width="53%" alt="The Alerts cheatsheet in ESP Screens: the action name of every screen, ready to copy">
</p>
<p align="center"><sub>Any alert, on one screen or all of them, in a pastel color of your choice, with one button or two to choose from, each in a color of its own and with its own action. <a href="README_EXTENDED.md#alert-from-an-automation">How alerts work</a>. An automation can also put a page in front, such as the page with the full-page player when the music starts: <a href="README_EXTENDED.md#open-a-page-from-an-automation">Open a page from an automation</a>.</sub></p>

## Installing from Home Assistant

### Which screen

| Screen | Resolution | Display / touch |
| --- | --- | --- |
| [CYD ESP32-2432S028](https://tessera-maxgramser.on-forge.com/screens/cyd) | 320 × 240, 2 × 3 tiles | ILI9341 / resistive XPT2046 |
| [Guition ESP32-S3-4848S040](https://tessera-maxgramser.on-forge.com/screens/guition), 4 inch | 480 × 480, 2 × 3 tiles | ST7701S RGB / capacitive GT911 |
| [Waveshare ESP32-S3-Touch-LCD-4.3](https://tessera-maxgramser.on-forge.com/screens/waveshare43) | 800 × 480, 3 × 3 tiles | ST7262 RGB / capacitive GT911 (backlight always on: no standby, no night) |
| [Waveshare ESP32-S3-Touch-LCD-7](https://tessera-maxgramser.on-forge.com/screens/waveshare7) (experimental) | 800 × 480, 4 × 4 tiles | RGB / capacitive GT911; backlight always on, hardware acceptance pending ([details](docs/WAVESHARE7.md)) |
| [Waveshare ESP32-S3-Touch-LCD-4B](https://tessera-maxgramser.on-forge.com/screens/waveshare4b), 4 inch (experimental) | 480 × 480, 2 × 3 tiles | ST7701S RGB / capacitive GT911; dimmable backlight, hardware acceptance pending ([details](docs/WAVESHARE4B.md)) |
| [Waveshare ESP32-S3-Touch-LCD-3.5](https://tessera-maxgramser.on-forge.com/screens/waveshare35) (new) | 480 × 320, 2 × 2 tiles | ST7796 SPI / capacitive FT6336; dimmable backlight, no camera pictures ([details](docs/WAVESHARE35.md)) |
| [Guition JC8012P4A1](https://tessera-maxgramser.on-forge.com/screens/jc8012p4a1), 10.1 inch | 1280 × 800, 5 × 4 tiles | MIPI-DSI JD9365 / capacitive GSL3680, ESP32-P4 (new) |
| Guition [JC1060P470](https://tessera-maxgramser.on-forge.com/screens/jc1060p470) and [JC1060P470 V2](https://tessera-maxgramser.on-forge.com/screens/jc1060p470v2), 7 inch (experimental) | 1024 × 600, 4 × 4 tiles | MIPI-DSI JD9165 / capacitive GT911, ESP32-P4; hardware acceptance pending ([details](docs/JC1060P470.md)) |

Each screen links to its page on the [Tessera website](https://tessera-maxgramser.on-forge.com/screens), with what owners report about it.

> **Got your screen working? Tell the next person.** Whether a board is worth buying is something
> only owners can tell. On the website, [My screen works](https://tessera-maxgramser.on-forge.com/community/share?type=installation)
> records your exact board, its firmware version and whether the display, touch and connection work,
> one report per account and board. It takes a minute (you sign in with GitHub), and it is how an
> experimental board becomes one people can buy with confidence. Something not right?
> [Report a problem](https://tessera-maxgramser.on-forge.com/community/share?type=issue) there, or open an issue here.

Use these exact board variants: similar-looking product names can have different
controllers or connectors. Wallbox relays are not controlled by default; a 4-inch Guition with relays
can switch them through its Override YAML ([docs/GUITION.md](docs/GUITION.md#relays)).

The one we use ourselves is the 4-inch Guition, and it has been good to us: bright,
responsive touch, and it has been on the wall for months without a hiccup. We buy it here:
[Guition ESP32-S3-4848S040 on AliExpress](https://nl.aliexpress.com/item/1005008506761923.html).
AliExpress being AliExpress, that link may go dead at some point. If it does, search for
"ESP32-S3-4848S040" and check the listing says 480 x 480, ST7701S and a capacitive GT911
touch panel before you order.

ESP Screens builds with its own **ESPHome 2026.9.0**. The firmware also builds in your own ESPHome Device Builder
with ESPHome 2026.6.2 or newer; the 10.1-inch Guition asks for 2026.8.0 or newer, because its touch panel is
newer than that.

The 10.1-inch Guition is **new in this release and has not yet been through our own acceptance test**: its
hardware was worked out and flashed on a real panel, and the screens' own software is the same on every board,
but the two have not stood on one desk together. Tell us how it goes. It needs a panel with pre-v3 silicon
(the boot log says `chip revision: v1.3` or another below v3.0), which is what these panels have shipped with
so far; rev3 silicon needs a firmware of its own.

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
   and choose **New screen** in the sidebar: your board, which way it hangs, a name, the USB port, and
   **Install**. If Wi-Fi is missing from the ESPHome `secrets.yaml`, the window
   asks for it once and ESP Screens only adds the missing lines. The profile
   with unique API and OTA keys goes into the ESPHome folder; the build
   and flash run in the same window (a first build takes a few minutes on a
   Raspberry Pi). Each screen gets its own profile.
   Is Home Assistant on a server or in a virtual machine, out of reach of the screen?
   Choose **Download** under **Install via**: ESP Screens builds the firmware, and you put it
   on the screen from your own computer with [ESPHome Web](https://web.esphome.io) in Chrome
   or Edge. After that, updates go over Wi-Fi as usual.
4. **CYD:** go through the calibration on the screen. **Guition:** uses GT911
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

Tessera (formerly ESP Screens) is MIT licensed, see [LICENSE](LICENSE).
