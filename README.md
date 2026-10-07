<p align="center">
  <a href="https://tessera-maxgramser.on-forge.com"><img src="docs/images/tessera-mosaic.jpg" width="100%" alt="A mosaic of real Tessera screens in every size, from the 2.8-inch CYD to the 10.1-inch Guition: lights, music, the thermostat, the weather, locks, blinds and the vacuum, in light and dark mode"></a>
</p>

<p align="center">
  <a href="https://tessera-maxgramser.on-forge.com"><img src="docs/images/tessera-mark.svg" width="112" alt="The Tessera logo: four rounded tiles in yellow, blue, purple and green, like a small mosaic"></a>
</p>

<h1 align="center">Tessera</h1>

<p align="center"><b>Touch screens for Home Assistant. A screen for every room, one simple editor.</b></p>

<p align="center">
  <a href="https://tessera-maxgramser.on-forge.com"><b>Website</b></a> ·
  <a href="https://tessera-maxgramser.on-forge.com/docs/quick-start">Quick start</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/screens">Supported screens</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/community">Community</a> ·
  <a href="https://tessera-maxgramser.on-forge.com/community/share?type=installation">My screen works</a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMaxGramser%2Fhomeassistant_espscreen"><img src="https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg" alt="Add the Tessera repository to your Home Assistant"></a>
</p>

<p align="center"><sub>Tessera is not in the standard App store. This button adds its repository to your Home Assistant. After that, Tessera Screen Manager is in the store like any other app.</sub></p>

<p align="center"><sub>Tessera is the new name for ESP Screens. In Home Assistant the app is called Tessera Screen Manager and its panel Tessera (app 0.3.18); the repository, the add-on and your screens stay exactly as they are.</sub></p>

<p align="center"><sub>Looking for e-ink? Tessera is for colour LCD touch screens. For calm dashboards on e-ink panels, have a look at <a href="https://tesserae.ink">Tesserae (tesserae.ink)</a>, a separate open-source project for Home Assistant with a similar name.</sub></p>

Thank you! I work on this project with a lot of love, and every bit of support helps. I truly love the Home Assistant community.

I lead Tessera's development and maintenance, with contributions from the community. Your support gives me more time to build, review and test improvements. A small monthly contribution or a one-time coffee is welcome.

<a href="https://buymeacoffee.com/f5j9jnkmhpv/membership"><img src="https://img.buymeacoffee.com/button-api/?text=Support%20monthly&emoji=&slug=f5j9jnkmhpv&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" alt="Support monthly" height="42"></a>
&nbsp; or <a href="https://buymeacoffee.com/f5j9jnkmhpv">buy me a coffee once</a>

<p align="center">
  <img src="docs/images/photo-guition-page-2.jpg" width="49%" alt="The Guition 4-inch screen on a table: the Evening page with Movie night and Good night in pastel lilac and blue, and the ceiling light and the bedroom fan as tall tiles with their sliders">
  <img src="docs/images/photo-guition-vacuum.jpg" width="49%" alt="The vacuum card on the Guition: docked at 100 %, Start cleaning and Dock, and the suction from Quiet to Max">
</p>

**A touch screen for every room that you lay out yourself, and manage from Home Assistant. Incredibly easy to set up and to use.**

**Why.** Your phone is in the other room and a tablet on the wall is expensive. A small ESP32 touch
panel costs a fraction of that, sits on a table or in a wall box, and is always at hand for the
lights, the heating or the vacuum.

**What.** Firmware for affordable panels, five of them today, from the 2.8-inch CYD to the 10.1-inch Guition, with
tiles over up to eight pages, or more on the boards with the memory for them, as many per page as the glass holds: lights, climate, humidifiers, blinds and curtains, the vacuum, media, the weather,
history graphs, the energy of your house live, clocks and timers, your alarm with its keypad, and your cameras and a map of where everyone is on every screen with room for pictures. A tile can take the whole page, one big switch you push without
looking, and a tile can go to another page. An automation can put an alert on every screen when someone rings
the bell, and a screen with room for pictures shows who is there with the doorbell camera's picture. A tap can run any
action Home Assistant has for a tile, and Dark mode suits a screen beside the bed.

**How.** Tessera Screen Manager is an app inside Home Assistant. It flashes a new screen over USB, updates
it over Wi-Fi and sends it your tiles. Changing a screen is pick, drag and **Save & send**:
no reflash, no YAML to write, no blueprint, MQTT or token. Brightness, night hours and Dark mode can
also be changed on the screen or by an automation, and your own YAML for one screen survives every update.

**[Install it](#installing-from-home-assistant)** · [The manual](https://tessera-maxgramser.on-forge.com/docs/) · [Pages](https://tessera-maxgramser.on-forge.com/docs/pages) · [Screen settings](https://tessera-maxgramser.on-forge.com/docs/screen-settings) · [Troubleshooting](https://tessera-maxgramser.on-forge.com/docs/troubleshooting) · [What's new](screen_manager/CHANGELOG.md)

> **The manual is on the [Tessera website](https://tessera-maxgramser.on-forge.com/docs/):** from the [quick start](https://tessera-maxgramser.on-forge.com/docs/quick-start) to every tile, every screen setting, every supported screen and troubleshooting, with search. Anyone with a GitHub account can improve a page with **Edit this page**. This README is the overview; the files under `docs/` are the reference for contributors.

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
the cells that board has, six tiles on the 2.8-inch CYD and twenty-five on the 10.1-inch Guition, while a tile stays about
the same size in millimetres. The same tiles, the same cards, the same editor; the bigger the glass, the more of your
home fits on one page. The 10.1-inch Guition holds up to forty on a page: New screen asks for five to eight rows.

<p align="center">
  <img src="docs/images/boards-scale.png" width="98%" alt="The five supported screens side by side on one scale, each showing a page of the same home: the small 2.8-inch CYD, the square 4-inch Guition, the wide 4.3-inch Waveshare, the 7-inch Waveshare and the large 10.1-inch Guition">
</p>
<p align="center"><sub>To scale, each with the page it fills: the same home on the 2.8-inch CYD, the 4-inch Guition, the 4.3-inch and 7-inch Waveshare, and the 10.1-inch Guition. Rendered from the firmware's own code, one board at a time.</sub></p>
<p align="center">
  <img src="docs/images/board-cyd.png" width="32%" alt="The kitchen page on the 2.8-inch CYD: the weather with five days, a pasta timer, the coffee machine, the kitchen lamp and the power usage">
  <img src="docs/images/board-guition.png" width="32%" alt="The Good morning page on the 4-inch Guition: an analog clock with the time and the date, the weather for four days, the coffee machine in orange and Sam at home">
  <img src="docs/images/board-waveshare43.png" width="32%" alt="The front door page on the 4.3-inch Waveshare: the front door camera live on a tile of two by two cells, the lock, the porch light, the weather and Sam">
</p>
<p align="center">
  <img src="docs/images/board-waveshare7.png" width="49%" alt="The living room page on the 7-inch Waveshare: the album cover on a tile of two by two cells, a clock with the date, the weather for five days, the heating and the curtains one cell wide and two high, a temperature graph and a lamp dimmer">
  <img src="docs/images/board-jc8012p4a1.png" width="49%" alt="The living room page on the 10.1-inch Guition: twenty-five cells with a clock, the weather, Sam, the album cover and the front door camera on two by two tiles each, the heating two cells high, graphs for the temperature and the energy, a lamp dimmer, the coffee machine, the robot and a good-night script">
</p>
<p align="center">
  <img src="docs/images/boards-standing.png" width="66%" alt="Two of the same screens built standing up, to scale: the 10.1-inch Guition with the same living room page in five columns of tall cells, and the 7-inch Waveshare by the front door with a clock, the weather, the front door camera, the lock, the porch light, the heating, Sam and the alarm in two columns">
</p>
<p align="center"><sub>The same home standing up. Which way a screen hangs is chosen when it is built, and every board that is not square hangs either way, with a grid of its own: the 7-inch Waveshare 2 × 7 instead of 4 × 4, while the 10.1-inch Guition keeps its 5 × 5 in tall cells. Which board is which, and what to look for when you buy one: <a href="#which-screen">Which screen</a>.</sub></p>
<p align="center">
  <img src="docs/images/jc8012p4a1-6rows.png" width="49%" alt="The living room on the 10.1-inch Guition with six rows, thirty cells: a clock, the weather for five days with the chance of rain, Sam, the album cover and the front door camera live on two by two tiles, the heating two cells high, graphs for the temperature and the energy, a lamp dimmer, the lock, the ceiling light, the robot, the curtains and two scenes">
  <img src="docs/images/jc8012p4a1-7rows.png" width="49%" alt="The same living room with seven rows, thirty-five cells: the alarm, the porch light, a second thermostat for the hallway and the coffee machine join the page">
</p>
<p align="center">
  <img src="docs/images/jc8012p4a1-8rows.png" width="49%" alt="The same living room with eight rows, forty cells: a kitchen speaker with its cover and volume, a small live porch camera, the kitchen lights and Alex fill the last row">
  <img src="docs/images/jc8012p4a1-8rows-dark.png" width="49%" alt="The page with eight rows in Dark mode">
</p>
<p align="center"><sub>Six, seven and eight rows on the 10.1-inch Guition, from thirty to forty tiles on a page, and eight rows in Dark mode. Rendered from the firmware's own code. The rows are chosen when the screen is built; one with five gets more by adding <code>GRID_ROWS: "6"</code> (or 7, or 8) to its own YAML and installing it again, and its saved layout moves along by itself. Thanks to <a href="https://github.com/Heronimonimo">Jeroen Peters</a> for <a href="https://github.com/MaxGramser/homeassistant_espscreen/pull/151">the rows</a>.</sub></p>

## Your house's energy, live

<p align="center">
  <img src="docs/images/energy-jc8012p4a1-dark.png" width="98%" alt="The 10.1-inch Guition in Dark mode with the energy card on three by three cells: the sun gives 5.2 kW, the house uses 2.5 kW, the battery at 64 % charges with 1.5 kW and 1.2 kW goes back to the grid, with lines and moving dots between their circles and the heat pump, the fridge, the washing machine and the office around the house; beside it the weather, the solar energy of today, the EV charger, the battery and graphs of the solar power and the living room temperature">
</p>
<p align="center">
  <img src="docs/images/energy-guition.png" width="32%" alt="The energy card on two by two cells of the 4-inch Guition: solar, grid, battery and the house with their power, above the solar energy of today and the EV charger">
  <img src="docs/images/energy-waveshare43.png" width="41%" alt="The 4.3-inch Waveshare with the energy card two cells wide and three high, beside the solar energy of today, the EV charger and the battery">
  <img src="docs/images/energy-cyd-standing.png" width="20%" alt="The 2.8-inch CYD standing up with the energy card over its whole page, the diagram turned upright: the grid at the top, solar and the battery at the sides and the house at the bottom">
</p>
<p align="center">
  <img src="docs/images/energy-guition-history.png" width="32%" alt="A tap on the solar circle opens the history of the solar sensor: a day with its highest and lowest moment">
  <img src="docs/images/energy-waveshare7-dark.png" width="49%" alt="The 7-inch Waveshare in Dark mode with the energy card on three by three cells and four devices, and the weather, the solar energy of today, the EV charger, the battery, the kitchen light, the heat pump and the car's battery beside and under it">
</p>
<p align="center"><sub>The energy card shows the power of your house right now, the way Home Assistant's own live Energy view and power-flow-card-plus show it: solar, the grid and the battery around the house, dots that run faster as more power flows, and the devices that draw the most. It reads the Energy settings you already have in Home Assistant, so there is nothing to set up, and a tap on a circle opens that sensor's history. It fits every screen, upright on one standing up (<a href="docs/ENERGY.md">how</a>). Rendered from the firmware's own LVGL code with a made-up house.</sub></p>

## Taller tiles, richer cards

<p align="center">
  <img src="docs/images/tall-jc8012p4a1.png" width="98%" alt="The 10.1-inch Guition in Dark mode: a clock with the date, the weather for five days, a media tile two cells wide and two high with the album cover dimmed behind the title and the play keys, the front door camera live beside it, the heating one cell wide and two high with minus, plus and its mode keys, graphs for the temperature and the energy, a table lamp dimmer, the coffee machine, the robot and a good-night script">
</p>
<p align="center">
  <img src="docs/images/tall-guition-media.png" width="32%" alt="The 4-inch Guition: a media tile two by two with the album cover behind the track, the artist and the previous, pause and next keys, above a table lamp with its dimmer">
  <img src="docs/images/tall-guition-climate.png" width="32%" alt="The Comfort page: the heating one cell wide and two high with its setpoint between minus and plus and its mode keys, heat lit in orange, the curtains open at 70 % with a slider, and a temperature graph">
  <img src="docs/images/tall-guition-home.png" width="32%" alt="The Evening page: Movie night and Good night in pastel lilac and blue, and two tiles one cell wide and two high: the ceiling light at 59 % and the bedroom fan, each with a big slider">
</p>
<p align="center">
  <img src="docs/images/tall-waveshare43-media.png" width="49%" alt="The 4.3-inch Waveshare: the media tile two by two with its album cover, the heating one cell wide and two high, a lamp dimmer and Sam at home">
  <img src="docs/images/tall-waveshare43-climate.png" width="49%" alt="The same screen in Dark mode: the bedroom thermostat two by two with its setpoint between minus and plus, the curtains one cell wide and two high, a temperature graph and the coffee machine">
</p>
<p align="center"><sub>A tile can be 1 × 2 or 2 × 2 cells as well as one cell, double width or the whole page, and the card follows the room it gets: a player shows its album cover behind the track (every screen but the CYD), the heating shows its setpoint and the modes Home Assistant lists for it (the last key opens the card when they do not all fit), a blind shows its position, and its slats where there is room, and a lamp, a switch, a script or a scene two cells high is one big key. Every board works out the same card from its own glass. Each page has its own title and top bar, any page can be Home, and a page can stay out of the page dots and be opened from a tile, with a Back key to return. Rendered from the firmware's own LVGL code with a demo home.</sub></p>

## Weather, heating, cameras, your alarm and your locks

<p align="center">
  <img src="docs/images/guition-weather-tiles.png" width="32%" alt="The 4-inch Guition with two weather tiles: a wide one with today and the next three days, and a big one listing the days under each other, each with a coloured bar from its low to its high on one scale">
  <img src="docs/images/guition-thermostat-tiles.png" width="32%" alt="Three thermostats: the heating with its setpoint between minus and plus and a bar with Heat and Auto, an airco on cool with heat, cool and more behind three dots, and a wide bedroom tile with the stepper on one row">
  <img src="docs/images/guition-camera-fill.png" width="32%" alt="A garden camera on a tile of two by two cells, its picture filling the whole card with the camera's name at the bottom, above the garden lights and the garden temperature">
</p>
<p align="center">
  <img src="docs/images/guition-alarm-tiles.png" width="32%" alt="Four alarm panels as tiles: the house disarmed in grey, the garage armed away in green, the shed arming in orange and the studio armed home in green">
  <img src="docs/images/guition-alarm-card.png" width="32%" alt="The alarm card: the shield in its circle, keys for Home, Away, Night and Vacation, and the Disarmed key">
  <img src="docs/images/guition-alarm-keypad.png" width="32%" alt="The keypad to arm away: four dots for the code, the digits 1 to 0, a clear key and a check key">
</p>
<p align="center">
  <img src="docs/images/guition-lock-tiles.png" width="32%" alt="Six locks as tiles: the front door asking to confirm in orange, the back door unlocked in red, the gate locked in green, the garage jammed in red, the shed locking in orange and the cellar unavailable in grey">
  <img src="docs/images/guition-lock-card.png" width="32%" alt="The lock card: a big green lock to tap with Unlock under it, and an Open door key">
  <img src="docs/images/guition-lock-confirm.png" width="32%" alt="The lock card waiting for the second tap: the big lock orange and open, with Confirm under it">
</p>
<p align="center">
  <img src="docs/images/waveshare43-new-tiles.png" width="49%" alt="The 4.3-inch Waveshare: a wide weather tile with the coming days, the bedroom thermostat, a garden camera filling a tile of two by two cells, the washing machine on Cotton eco and the dryer">
  <img src="docs/images/waveshare43-select-card.png" width="49%" alt="The select card of a washing machine on the 4.3-inch Waveshare: its programmes in two columns, Cotton eco checked, and page dots for the rest">
</p>
<p align="center"><sub>The weather with the coming days, and on a bigger tile the whole week with a bar from each day's low to its high. A thermostat has its − / + and a bar with a key per mode; an airco shows heat and cool first and the rest behind "…". A live camera on a taller tile fills the card with its picture and its name, or shows the whole picture. Your alarm is a tile in Home Assistant's colours, with a key for every mode and Home Assistant's keypad when the panel asks for a code; someone coming in wakes every screen with the keypad to disarm. A lock locks with one tap and asks for a second one before it unlocks; its card has Open door where the lock can open its latch, and Home Assistant's keypad when the lock asks for a code. A select, such as a washing machine's programme, opens a list with a check at the one it is on. On every screen with the memory for it, every page is built ahead and kept, so the next one is there the moment you turn to it. Rendered from the firmware's own LVGL code with a demo home.</sub></p>

## Music, from the speaker to the library

<p align="center">
  <img src="docs/images/media-boards-scale.png" width="98%" alt="The same player card on five screens side by side on one scale, from the 2.8-inch CYD to the 10.1-inch Guition: the album cover on a ground in its own colours, the speaker Kitchen at the top, the title, the bar through the track, the keys and the volume">
</p>
<p align="center">
  <img src="docs/images/media-guition-player.png" width="32%" alt="The player card on the 4-inch Guition: the album cover on a ground in the cover's own colours, the speaker Kitchen at the top, the title and artist, a bar to drag through the track, shuffle, previous, pause, next and repeat, and the volume">
  <img src="docs/images/media-guition-speakers.png" width="32%" alt="The speaker menu open over the card: Bedroom, Kitchen with a check mark, and Living room">
  <img src="docs/images/media-guition-favourites.png" width="32%" alt="A page of favourites: an album and a playlist with their covers dimmed behind the name and a play key, the playlist that plays ringed in blue with a pause key, an artist and the player itself">
</p>
<p align="center">
  <img src="docs/images/media-guition-library.png" width="32%" alt="The library of the player: Playlists, Artists, Albums, Liked songs, Podcasts, Recently played, Top artists and Top tracks">
  <img src="docs/images/media-guition-albums.png" width="32%" alt="A page of albums: six covers with their titles, page dots and arrows to turn to the next six">
  <img src="docs/images/media-cyd-favourites.png" width="32%" alt="The same favourites on the 2.8-inch CYD, drawn with icons: an album, two playlists, an artist and the player">
</p>
<p align="center">
  <img src="docs/images/media-waveshare43-player.png" width="49%" alt="The player card on the 4.3-inch Waveshare: the cover at the left on its coloured ground, the title, the bar and the keys beside it, the volume along the bottom">
  <img src="docs/images/media-waveshare43-albums.png" width="49%" alt="A page of albums on the 4.3-inch Waveshare: five covers in a row with page arrows">
</p>
<p align="center">
  <img src="docs/images/media-waveshare43-starting.png" width="49%" alt="Favourites on the 4.3-inch Waveshare: the wide favourite Sunday Morning starting on the Kitchen speaker, a spinner round its play key">
  <img src="docs/images/media-waveshare43-speakers.png" width="49%" alt="The speaker menu over the player card on the 4.3-inch Waveshare: Bedroom, Kitchen with a check mark, and Living room">
</p>
<p align="center">
  <img src="docs/images/media-jc8012p4a1-albums.png" width="66%" alt="A page of albums on the 10.1-inch Guition: eighteen covers in three rows of six">
</p>
<p align="center"><sub>A media player's card sits on the colours of the cover that plays, and the speaker it plays on is at the top: tap it to move the music to another one. Shuffle, repeat and a bar you drag through the track sit under the title. The library key opens what Home Assistant can browse on that player, folder by folder down to a page of covers, and a tap on a cover plays it. A favourite is a tile that plays one playlist, album or artist on the speaker you choose, with its cover behind it, and a player at rest keeps its card, so you pick a speaker and start from there. Nothing here is made for one service: it is the player and its library as Home Assistant reports them, so Spotify works like any other player that can browse. The covers and the library need a screen with the memory for pictures (<a href="https://tessera-maxgramser.on-forge.com/docs/cameras">how</a>); the CYD keeps the card, the speakers and the favourites, drawn with icons. Rendered from the firmware's own LVGL code with made-up records.</sub></p>

## Where everyone is

<p align="center">
  <img src="docs/images/guition-map.png" width="25%" alt="The 4-inch Guition with a map tile of two by two cells: the streets and canals of a city in soft greys, a marker for each person with a photo or initials and their first name beside it, and the tile's name Family at the bottom, above a lamp and a temperature">
  <img src="docs/images/guition-map-dark.png" width="25%" alt="The same map tapped open over the whole screen in Dark mode: dark streets, the people in their own colours, the round back key and the name Family at the top">
  <img src="docs/images/waveshare43-map.png" width="41%" alt="The 4.3-inch Waveshare with the map tile following everyone: four people, two with a photo in their marker, and a car">
</p>
<p align="center"><sub>A person tile can be a map of where they and the people with them are, and the map tile follows everyone Home Assistant knows the place of, or only whom you choose. Photos in the markers and the same colours as Home Assistant's own maps; a tap opens the map over the whole screen. Tessera draws it in the screen's own colours, light or dark, from Home Assistant's own map tiles, and draws it again only when someone moves; the screen gets a picture, never a location (<a href="docs/MAP.md">how</a>). Rendered from the firmware's own LVGL code with a made-up household; map data © OpenStreetMap contributors.</sub></p>

## A clock beside your bed

<p align="center">
  <img src="docs/images/guition-bedside.png" width="49%" alt="The bedside clock on the 4-inch Guition in dark mode: 23:47 in large grey digits on a black page, and under it three round keys: the bedside lamp on in amber, the front door locked in green and the alarm armed for the night in green">
</p>
<p align="center"><sub>The bedside clock takes a whole page: the time as large as the glass allows, with up to three round keys under it for what you reach for at night. A key is a tile in its round form and does what its tile does: the lamp switches with a tap, the front door asks for a second tap before it unlocks, and the alarm shows how it is armed. With Dark mode and the screen's night hours the page is black and the backlight dims. Rendered from the firmware's own LVGL code with a demo home.</sub></p>

## On the screen

<p align="center">
  <img src="docs/images/guition-front-door.png" width="32%" alt="The Front door page on the Guition 4-inch screen: the front door camera live on a tile of two by two cells with its name, the front door locked and the porch light on">
  <img src="docs/images/guition-energy.png" width="32%" alt="The Energy page: today's energy as a graph, the power and the humidity as large values, and the robot vacuum with start, stop and dock">
  <img src="docs/images/guition-weather-page.png" width="32%" alt="The Weather page: the garden forecast on a big tile, each day with a bar from its low to its high, above the sun's path with sunrise and sunset">
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
  <img src="docs/images/guition-vacuum.png" width="32%" alt="Vacuum card: docked at 100 %, Start cleaning and Dock, and the suction from Quiet to Max">
  <img src="docs/images/guition-blind.png" width="32%" alt="Cover card for a venetian blind: its battery, the position slider with the blind hanging from the top, the tilt slider over slats, and open, stop and close">
  <img src="docs/images/guition-history-touch.png" width="32%" alt="A finger on the history graph: the top of the card shows the average of that hour and its time, the graph stays as it is">
</p>
<p align="center">
  <img src="docs/images/guition-effects.png" width="32%" alt="The effects page of a WLED lamp: the effect, colour palette, preset and playlist rows with what they are set to, and the speed and intensity sliders">
  <img src="docs/images/guition-effects-picker.png" width="32%" alt="The effect picker: a drum with every effect Home Assistant lists, TV Simulator in the middle, and the check key at the top right that sends it">
  <img src="docs/images/cyd-effects.png" width="32%" alt="The same effects page on the CYD: four rows and the two sliders in 320 by 240 pixels">
</p>
<p align="center"><sub>Tap a tile to switch it, hold it for the full card. Keys and sliders right on the tile, pastel colors, a clock, the weather and history you can read with a finger. A lamp with modes (a WLED) gets an effects page with a drum picker, named and filled from what Home Assistant lists for it. Rendered from the firmware's own LVGL code with a demo home.</sub></p>
<p align="center">
  <img src="docs/images/guition-camera-tiles.png" width="32%" alt="Cameras as tiles on the Guition: the front door camera filling a tall tile with its name at the bottom, a porch camera showing its whole picture with black above and below, the porch light and Sam at home">
  <img src="docs/images/guition-camera.png" width="32%" alt="A camera tile tapped: the front door camera full screen, with the round back key and the camera's name at the top">
  <img src="docs/images/guition-alert-camera.png" width="32%" alt="The same camera in an alert: its picture across the top of the card, with the card's rounded corners">
</p>
<p align="center"><sub>Cameras are tiles too, not only part of an alert: any camera or snapshot in Home Assistant (a doorbell's last ring, for example) goes on a screen like any other tile. Tap it for the picture full screen, refreshed every four seconds, or let the tile itself show its live picture (Display → Live picture, every 5 to 30 s) over the whole tile, on every size up to a full page, filled or whole, with or without its name; an alert can carry the same picture. Every screen but the CYD, the Waveshare 3.5-inch and the Hosyond 4-inch, which have no memory for pictures (<a href="https://tessera-maxgramser.on-forge.com/docs/cameras">how it works</a>).</sub></p>
<p align="center">
  <img src="docs/images/cyd-home.png" width="32%" alt="CYD 2.8-inch screen: the weather forecast, a pasta timer, the coffee machine in orange, the kitchen lamp and the power usage as a large value">
  <img src="docs/images/cyd-page-2.png" width="32%" alt="Second CYD page: the Sonos volume, Sam at home, the Movie night scene in lilac and an energy graph">
  <img src="docs/images/cyd-weather.png" width="32%" alt="The weather card on the CYD: current weather, the coming hours and the coming days">
</p>
<p align="center">
  <img src="docs/images/cyd-tiles-controls.png" width="32%" alt="The CYD with heating mode keys, playback keys for the radio and a ceiling fan's speed slider">
  <img src="docs/images/cyd-vacuum.png" width="32%" alt="The vacuum card on the CYD: docked at 100 %, clean and dock, and the suction from Quiet to Max">
  <img src="docs/images/cyd-history.png" width="32%" alt="The history card on the CYD: power over 24 hours with its highest and lowest moment, an axis in watts and clock times">
</p>
<p align="center">
  <img src="docs/images/cyd-media.png" width="32%" alt="The media card on the CYD on the colours of its cover: the player's icon where the cover would be, the title, artist and album, the bar with its times, the keys and the volume slider">
  <img src="docs/images/cyd-media-full.png" width="32%" alt="A media player over the whole CYD page: the icon at the left, the track and the keys beside it, the volume row along the bottom">
  <img src="docs/images/cyd-dark-media.png" width="32%" alt="The media card on the CYD in dark mode">
</p>
<p align="center"><sub>The same cards on the 2.8-inch CYD, 320 × 240. The CYD has no memory for pictures: its media card shows the player's icon in the cover's place.</sub></p>
<p align="center">
  <img src="docs/images/guition-dark-home.png" width="32%" alt="Dark mode on the Guition: the living room page on a black page, the album cover and the lamp dimmer in their own colours">
  <img src="docs/images/guition-dark-controls.png" width="32%" alt="Dark mode on the Good morning page: graphite cards and soft white text, the clock, the weather, the coffee machine in a deep orange and Sam">
  <img src="docs/images/guition-dark-page-4.png" width="32%" alt="Dark mode on the Evening page: the two scenes in deeper lilac and blue, and the tall ceiling light and fan sliders keep their colours">
</p>
<p align="center"><sub>Dark mode, for a screen beside the bed: the same pages, darker. It is a switch on the screen, in Tessera and in Home Assistant, so an automation can turn it on at bedtime.</sub></p>
<p align="center">
  <img src="docs/images/guition-settings-screen.png" width="32%" alt="The settings page on the Guition, Screen: back to Home by itself and after how long, also on standby, swiping between pages and the page buttons, with the rotation on its second page">
  <img src="docs/images/guition-settings.png" width="32%" alt="The settings page on the Guition, Brightness: the brightness with minus and plus, Dark mode off, Auto standby on, standby after 10 minutes and the standby brightness">
  <img src="docs/images/guition-dark-settings.png" width="32%" alt="The same Brightness page right after turning Dark mode on: a black page with graphite rows and soft white text">
</p>
<p align="center"><sub>Settings on the screen itself: hold the top bar. The same brightness, Dark mode, standby, night hours, clock and rotation as in Tessera, and every one of them is an entity in Home Assistant.</sub></p>

## Managed from Home Assistant

<p align="center">
  <img src="docs/images/editor-home.png" width="98%" alt="Tessera in Home Assistant: Your screens, seven screens from the 2.8-inch CYD to the 10.1-inch Guition, each with a preview of its first page drawn by its own firmware, one with an update waiting">
</p>
<p align="center">
  <img src="docs/images/editor.png" width="98%" alt="Tessera in Home Assistant: the living room screen's pages side by side, each with its title and top bar, Living room, Good morning, Comfort and Evening, and the library under them grouped by room">
</p>
<p align="center"><sub>Tessera, a page in Home Assistant: every screen at a glance, then the pages of the chosen one side by side with the values Home Assistant reports right now, and the library of your home under them.</sub></p>
<p align="center">
  <img src="docs/images/editor-tiles.png" width="63%" alt="Choosing tiles: the pages of the screen side by side, and the library searched for lamp with the four lamps of the home and their rooms">
  <img src="docs/images/editor-tile-settings.png" width="33%" alt="Tile settings of the curtains in the drawer: on tap Perform action with Set cover position at 50 %, the position slider on the tile, the icon and the pastel background">
</p>
<p align="center"><sub>Search your home, drop a tile on the preview, tap it for its name, width, control and color, and for what a tap does: open its card, switch it, or run any action Home Assistant has for it, such as the curtains to 50 %. Save, and the screen has it. ⌘K searches screens, entities and actions; Identify blinks a screen so you know which one it is.</sub></p>
<p align="center">
  <img src="docs/images/editor-top-bar.png" width="31%" alt="The top bar in the drawer: the page title on the left, and on the right the outdoor temperature, people at home and the time, with how each looks on the screen">
  <img src="docs/images/editor-settings.png" width="65%" alt="Settings in Tessera: New screen and Firmware & USB, the firmware updates, Language & region, the Alerts cheatsheet, and the Claude skill">
</p>
<p align="center"><sub>A top bar built from your own home, firmware updates over Wi-Fi (every night if you like), and a skill so Claude can rearrange your screens.</sub></p>
<p align="center">
  <img src="docs/images/editor-phone-screens.png" width="23%" alt="Tessera on a phone: Your screens, each with a preview of its first page drawn by its own firmware, one with an update waiting">
  <img src="docs/images/editor-phone-screen.png" width="23%" alt="One screen on a phone: its page as the screen shows it, the page picker under it and one big Add tile button">
  <img src="docs/images/editor-phone-tile.png" width="23%" alt="A tile tapped on a phone: a sheet with its icon and pastel background, More settings, Move and Remove">
  <img src="docs/images/editor-phone-add.png" width="23%" alt="Add tile on a phone: a sheet with search, the kinds as chips and the home's devices by room, each with a plus">
</p>
<p align="center"><sub>On a phone, Tessera is the editor of everyday changes: your screens, a page as the screen shows it, a tap on a tile for its icon and colour, and Add tile. Everything else is in the screen's ··· menu, and <b>Full editor</b> there opens the whole editor.</sub></p>
<p align="center">
  <img src="docs/images/editor-screen-settings.png" width="98%" alt="The Screen settings tab in Tessera: Brightness with Dark mode and standby, Night with its hours and brightness, and Screen with back to Home, swiping, the page buttons and the rotation">
</p>
<p align="center"><sub>Screen settings apply at once, and a change made on the screen or by an automation shows up here too.</sub></p>
<p align="center">
  <img src="docs/images/editor-override-yaml.png" width="50%" alt="Override YAML for the living room screen: a small file of its own, loaded after the shared package, here with the example that changes the display controller">
</p>
<p align="center"><sub>Other hardware on your board? A CYD with the other display controller is a choice in New screen, and for anything else every screen has an Override YAML of its own, checked by ESPHome before a build and kept through every update.</sub></p>

## In your language

<p align="center">
  <img src="docs/images/guition-german.png" width="31%" alt="A Guition in German: Wohnzimmer at the top with 16,8 °C, Dienstag, 15. September beside the analog clock, the days Di Mi Do, the Tischlampe at 75 % and Sam Zuhause">
  <img src="docs/images/guition-french.png" width="31%" alt="The same screen in French: Salon, mardi 15 septembre beside the clock, Éclaircies with the days ma me je, the Lampe de table at 75 % and Sam Maison">
  <img src="docs/images/guition-polish.png" width="31%" alt="The same screen in Polish: Salon, wtorek, 15 września beside the clock, the days wt śr cz, the Lampa stołowa at 75% and Sam w domu">
</p>
<p align="center"><sub>The same home in German, French and Polish, its rooms and tiles named in each. The screens follow your Home Assistant: its language, its words for a light or a robot, and how your country writes a date, a time and a number: 75 % in German and French, 75% in Polish and English.</sub></p>

The screens, the editor and its messages speak **English (US and UK), Nederlands, Deutsch, Français, Italiano,
Español, Português, Polski and Magyar**. Nothing to set up: Tessera takes the language of your Home Assistant.

<p align="center">
  <img src="docs/images/editor-language.png" width="36%" alt="Language and region in Tessera: the screen language set to Home Assistant's language, the time format on 24 hour and the number format following the language">
</p>
<p align="center"><sub>Settings → Language & region, when you want something else than Home Assistant's own.</sub></p>

- **The editor** follows the language of your Home Assistant profile, so two people in one house each read their own.
- **A screen** carries one language, built into its firmware: change it and press **Update** on the screen (or let
  the nightly round do it). The clock (24 hours or 12 with AM/PM) and the number format change straight away, on
  every screen at once.
- **Words from Home Assistant stay Home Assistant's**: what a door, an airco or a robot says on a tile and in its
  card is the word its own dashboard shows, in your language.

Most languages still need someone who speaks them to read the texts through, and a new language is one file.
[Translating Tessera](docs/TRANSLATING.md) walks through both; a language without a file falls back to English
while it keeps your country's clock and numbers.

## Alerts

<p align="center">
  <img src="docs/images/guition-alert-camera.png" width="41%" alt="An alert on the Guition with the front door camera's picture across the top: someone is at the door, with a Coming button">
  <img src="docs/images/guition-camera.png" width="41%" alt="The front door camera full screen on the Guition, with the round back key and the camera's name at the top">
</p>
<p align="center"><sub>Someone at the door? One event in an automation wakes every screen and shows it. Add the doorbell camera and a Guition shows who is there; tap the picture, or a camera tile, for the camera full screen, refreshed every few seconds. <a href="docs/CAMERA.md">Camera images</a>.</sub></p>
<p align="center">
  <img src="docs/images/guition-alert-choice-colors.png" width="41%" alt="An alert on the Guition asking to open the garage, with a red Decline and a green Accept button side by side">
  <img src="docs/images/editor-alerts.png" width="53%" alt="The Alerts cheatsheet in Tessera: a preview of the alert, a form to try one, and the action name of every screen, ready to copy">
</p>
<p align="center"><sub>Any alert, on one screen or all of them, in a pastel color of your choice, with one button or two to choose from, each in a color of its own and with its own action. <a href="README_EXTENDED.md#alert-from-an-automation">How alerts work</a>. An automation can also put a page in front, such as the page with the full-page player when the music starts: <a href="README_EXTENDED.md#open-a-page-from-an-automation">Open a page from an automation</a>.</sub></p>

## Installing from Home Assistant

### Which screen

| Screen | Resolution | Display / touch |
| --- | --- | --- |
| [CYD ESP32-2432S028](https://tessera-maxgramser.on-forge.com/screens/cyd) | 320 × 240, 2 × 3 tiles | ILI9341 / resistive XPT2046 |
| CYD ESP32-2432S028 with ILI9342 (experimental) | 320 × 240, 2 × 3 tiles | ILI9342 / resistive XPT2046; hardware acceptance pending |
| [Guition ESP32-S3-4848S040](https://tessera-maxgramser.on-forge.com/screens/guition), 4 inch | 480 × 480, 2 × 3 tiles | ST7701S RGB / capacitive GT911 |
| [Waveshare ESP32-S3-Touch-LCD-4.3](https://tessera-maxgramser.on-forge.com/screens/waveshare43) | 800 × 480, 3 × 3 tiles | ST7262 RGB / capacitive GT911 (backlight always on: no standby, no night) |
| Waveshare ESP32-S3-Touch-LCD-5 (new) | 800 × 480, 3 × 3 tiles | RGB / capacitive GT911, the 4.3-inch's board with 5-inch glass (backlight always on: no standby, no night; [details](docs/WAVESHARE5.md)) |
| [Waveshare ESP32-S3-Touch-LCD-7](https://tessera-maxgramser.on-forge.com/screens/waveshare7) (experimental) | 800 × 480, 4 × 4 tiles | RGB / capacitive GT911; backlight always on, hardware acceptance pending ([details](docs/WAVESHARE7.md)) |
| Waveshare ESP32-S3-Touch-LCD-7B (experimental) | 1024 × 600, 4 × 4 tiles | RGB / capacitive GT911; dimmable backlight, hardware acceptance pending ([details](docs/WAVESHARE7B.md)) |
| Sunton ESP32-8048S070, 7 inch (experimental) | 800 × 480, 4 × 4 tiles | RGB / capacitive GT911; dimmable backlight, hardware acceptance pending ([details](docs/SUNTON8048S070.md)) |
| [Waveshare ESP32-S3-Touch-LCD-4B](https://tessera-maxgramser.on-forge.com/screens/waveshare4b), 4 inch (experimental) | 480 × 480, 2 × 3 tiles | ST7701S RGB / capacitive GT911; dimmable backlight, hardware acceptance pending ([details](docs/WAVESHARE4B.md)) |
| [Waveshare ESP32-S3-Touch-LCD-3.5](https://tessera-maxgramser.on-forge.com/screens/waveshare35) (new) | 480 × 320, 2 × 2 tiles | ST7796 SPI / capacitive FT6336; dimmable backlight, no camera pictures ([details](docs/WAVESHARE35.md)) |
| [Hosyond ESP32-32E](https://tessera-maxgramser.on-forge.com/screens/hosyond40), 4 inch (experimental) | 480 × 320, 2 × 3 tiles | ST7796 SPI / resistive XPT2046; dimmable backlight, no camera pictures, hardware acceptance pending ([details](docs/HOSYOND40.md)) |
| [Guition JC3248W535](docs/JC3248W535.md), 3.5 inch (new) | 480 × 320, 2 × 2 tiles | AXS15231B QSPI / capacitive AXS15231B; dimmable backlight, camera pictures |
| [Guition JC8012P4A1](https://tessera-maxgramser.on-forge.com/screens/jc8012p4a1), 10.1 inch | 1280 × 800, 5 × 5 tiles | MIPI-DSI JD9365 / capacitive GSL3680, ESP32-P4 (new) ([details](docs/JC8012P4A1.md)) |
| Guition JC8012P4A1 V2, 10.1 inch (experimental) | 1280 × 800, 5 × 5 tiles | MIPI-DSI JD9365 / capacitive GSL3680, early ESP32-P4 with the newer LCD; hardware acceptance pending ([details](docs/JC8012P4A1.md)) |
| Guition JC8012P4A1 V3, 10.1 inch (experimental) | 1280 × 800, 5 × 5 tiles | MIPI-DSI JD9365 / capacitive GSL3680, rev3 ESP32-P4; hardware acceptance pending ([details](docs/JC8012P4A1.md)) |
| Guition [JC1060P470](https://tessera-maxgramser.on-forge.com/screens/jc1060p470) and [JC1060P470 V2](https://tessera-maxgramser.on-forge.com/screens/jc1060p470v2), 7 inch (experimental) | 1024 × 600, 4 × 4 tiles | MIPI-DSI JD9165 / capacitive GT911, ESP32-P4; hardware acceptance pending ([details](docs/JC1060P470.md)) |
| M5Stack Tab5 (ST7121 variant, new) | 1280 × 720, 3 × 3 tiles | MIPI-DSI ST7121 / capacitive ST7121, ESP32-P4; hardware tested ([details](docs/TAB5.md)) |

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

Tessera builds with its own **ESPHome 2026.9.0**. The firmware also builds in your own ESPHome Device Builder
with ESPHome 2026.6.2 or newer; the 10.1-inch Guition asks for 2026.8.0 or newer, because its touch panel is
newer than that.

The 10.1-inch Guition is **new in this release and has not yet been through our own acceptance test**: its
hardware was worked out and flashed on a real panel, and the screens' own software is the same on every board,
but the two have not stood on one desk together. Tell us how it goes. It needs a panel with pre-v3 silicon
(the boot log says `chip revision: v1.3` or another below v3.0), which is what these panels have shipped with
so far; rev3 silicon needs a firmware of its own.

### Do I need ESPHome?

**You don't need to install the separate ESPHome Device Builder app.**
Tessera Screen Manager already includes the ESPHome CLI and can build firmware itself,
install it via USB, put it on a screen plugged into your own computer from the browser, or give
you the file,
and later update it wirelessly over OTA.

**Nothing to set up in Home Assistant.** As soon as a flashed screen is on your Wi-Fi, Tessera adds it
to Home Assistant's ESPHome integration with the screen's own key and allows it to perform Home Assistant
actions, which a tile needs to control anything.

| Component | Needed? | What for? |
| --- | --- | --- |
| Tessera Screen Manager app | Yes, for this installation route | Installing firmware, managing tiles, and sending current data to the screen |
| ESPHome Device Builder app | No, optional | Alternative editor and firmware installer; the same CLI is already in Tessera |
| ESPHome integration in HA | Yes, Tessera adds every screen to it by itself | The connection between Home Assistant and the physical screen |

So a fresh installation without ESPHome Device Builder also works. If there's
no ESPHome `secrets.yaml` yet, our wizard asks for Wi-Fi once and
stores it locally. Existing Wi-Fi secrets are reused. API and OTA keys
are generated per new screen and stay in that device's own profile.

### Step by step

For Home Assistant Container (Docker) without the App store, follow [Install with Docker](https://tessera-maxgramser.on-forge.com/docs/docker).

For Home Assistant OS with Apps/Add-ons on **aarch64 or amd64**:

1. Tessera is not in the standard App store, so add its repository first. One click does it:

   [![Add the Tessera repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMaxGramser%2Fhomeassistant_espscreen)

   Or add it by hand: open the App store, choose **Repositories** in the menu in the top right, and add
   `https://github.com/MaxGramser/homeassistant_espscreen`.
2. Install **Tessera Screen Manager** from the store, start the app, and open **Tessera** in the sidebar.
   ESPHome Device Builder is optional: the ESPHome CLI is already in this app.
3. Connect the screen with a USB data cable to the **Home Assistant machine**
   and click **+** beside Screens in the sidebar. New screen takes three steps: **Screen** (pick your board),
   **Set up** (name it and choose which way it hangs) and **Install** (choose **USB on Home Assistant** and click
   **Install**). If Wi-Fi is missing from the ESPHome `secrets.yaml`, Set up
   asks for it once and Tessera only adds the missing lines. The profile
   with unique API and OTA keys goes into the ESPHome folder; the build
   and flash run in the same window (a first build takes a few minutes on a
   Raspberry Pi). Each screen gets its own profile.
   Is Home Assistant on a server or in a virtual machine, out of reach of the screen?
   Plug the screen into your own computer and choose **From this computer** in the Install step:
   Tessera builds the firmware and the page puts it on the screen, in Chrome or Edge with
   Home Assistant opened over https. Or choose **Download the file** and put it on the screen with
   [ESPHome Web](https://web.esphome.io). After that, updates go over Wi-Fi as usual.
4. **CYD:** go through the calibration on the screen. **Guition:** uses GT911
   without resistive calibration. The screen joins your Wi-Fi and shows up in Tessera by itself.
5. Select the screen in Tessera, choose your tiles, and click
   **Save & send**. Then test the physical controls.

<p align="center">
  <img src="docs/images/editor-new-screen.png" width="37%" alt="New screen in Tessera: the first of three steps, every supported board with its size, resolution and touch chip, the 4-inch Guition chosen">
  <img src="docs/images/editor-tiles.png" width="59%" alt="Choosing tiles: the pages of the screen side by side, and the library searched for lamp">
</p>
<p align="center"><sub>New screen, its first step (step 3 above), and choosing your tiles (step 5).</sub></p>

New firmware goes on over Wi-Fi with the **Update** button of a screen in Tessera, or by itself
every night if you turn that on under **Settings**; **Firmware & USB → Wi-Fi / OTA** in the sidebar
installs it by hand. For an existing screen, always use the existing profile; creating a new
installation profile generates new keys.

The [manual](https://tessera-maxgramser.on-forge.com/docs/install) on the website walks through every step in more detail.

## More

- **[The manual on the Tessera website](https://tessera-maxgramser.on-forge.com/docs/):** [installing](https://tessera-maxgramser.on-forge.com/docs/install),
  [pages](https://tessera-maxgramser.on-forge.com/docs/pages), [tiles](https://tessera-maxgramser.on-forge.com/docs/tiles), [screen settings](https://tessera-maxgramser.on-forge.com/docs/screen-settings),
  [cameras](https://tessera-maxgramser.on-forge.com/docs/cameras), [Docker](https://tessera-maxgramser.on-forge.com/docs/docker) and [troubleshooting](https://tessera-maxgramser.on-forge.com/docs/troubleshooting).
- **[Full reference](README_EXTENDED.md):** every card and setting, alerts and wake/sleep from an
  automation, the top bar, the settings page on the screen, and how updates keep your settings.
- [Guition hardware, mounting, and rotation](docs/GUITION.md) ·
  [CYD calibration and USB diagnostics](docs/CALIBRATING.md) ·
  [Release history](screen_manager/CHANGELOG.md)

## Credits and license

ESP Screens was inspired by Adrian Kuehlewind's
[ESPHome-touch-display-mount](https://github.com/akuehlewind/ESPHome-touch-display-mount), and its
very first version started from his code. The project has gone its own way since, but his repository
is still the place to go to give a CYD a proper home. It has beautiful 3D-printable desk, under-desk,
wall and flush mounts.

Not to be confused with [Tesserae (tesserae.ink)](https://tesserae.ink), a separate open-source project that
makes calm dashboards for e-ink panels in Home Assistant. Same word, different screens: Tessera is for colour LCD
touch screens, Tesserae for e-ink. A question meant for the other project is gladly passed on.

The front door in the camera pictures is a photo by
[Virginia Marinova](https://unsplash.com/photos/the-door-welcomes-with-plants-on-both-sides-80uwJgdeqWg) on Unsplash.

Tessera (formerly ESP Screens) is licensed under the GNU Affero General Public License v3.0, see [LICENSE](LICENSE)
and [NOTICE](NOTICE). Releases up to and including 0.4.38 were MIT licensed and stay so.
