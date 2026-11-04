# The documents in docs/

## For users

- [EASY_SETUP.md](EASY_SETUP.md): install Tessera Screen Manager, add a screen, flash it and give it tiles.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md): what to check when a screen, its touch or its way into Home Assistant misbehaves.
- [DOCKER.md](DOCKER.md): Tessera Screen Manager on Home Assistant Container, without the App store.
- [BEDSIDE.md](BEDSIDE.md): the bedside clock, a whole-page clock with keys for the night.
- [CALENDAR.md](CALENDAR.md): the calendar card, from what is on now to the week and the month, and its filters.
- [VACUUM.md](VACUUM.md): the vacuum card with the robot's map, cleaning per room and its routines, and what it shows
  for robots that offer less.
- [METER.md](METER.md): the meter display of a sensor, a ring, a tape or a bar, its range and its colours.
- [LIGHT_PRESETS.md](LIGHT_PRESETS.md): a light's presets, round keys that set a colour and a brightness with one tap,
  on its tile and its card.
- [TEXT_TILE.md](TEXT_TILE.md): the template tile, a text with Home Assistant templates in it, how to write one, its
  limits and why it is built so.
- [SCREENSAVER.md](SCREENSAVER.md): what a screen shows in standby instead of its dimmed tiles: a cover, a camera or the clock.
- [BATTERY.md](BATTERY.md): a screen's battery in its top bar, and how a board or your own YAML measures it (also a
  recipe for the code).
- [EXTRA_HARDWARE.md](EXTRA_HARDWARE.md): a wall button, a temperature sensor or other parts on a screen's spare pins,
  through its Override YAML.
- [UPDATING_4MB_SCREENS.md](UPDATING_4MB_SCREENS.md): the CYD and the Hosyond get more room for firmware, and what to do
  if you flash them yourself.

## Per board

- [GUITION.md](GUITION.md): the Guition 4848S040, 4 inch, 480 × 480: hardware, mounting, touch and rotation.
- [GUITION_FACTORY_REFERENCE.md](GUITION_FACTORY_REFERENCE.md): the manufacturer's own demo on the 4848S040, as a
  reference for the panel's driving.
- [CROWPANEL101.md](CROWPANEL101.md): the Elecrow CrowPanel Advanced, 10.1 inch, ESP32-P4.
- [JC3248W535.md](JC3248W535.md): the Guition JC3248W535, 3.5 inch.
- [JC4880P443.md](JC4880P443.md): the Guition JC4880P443, 4.3 inch, ESP32-P4.
- [JC8048W550.md](JC8048W550.md): the Guition JC8048W550C_I, 5 inch.
- [JC1060P470.md](JC1060P470.md): the Guition JC1060P470 and its V2, 7 inch, ESP32-P4.
- [JC8012P4A1.md](JC8012P4A1.md): the Guition JC8012P4A1, 10.1 inch, ESP32-P4, with its V2 and V3.
- [TAB5.md](TAB5.md): the M5Stack Tab5, 5 inch, ESP32-P4, for the confirmed ST7121 variant.
- [WAVESHARE35.md](WAVESHARE35.md): the Waveshare ESP32-S3-Touch-LCD-3.5.
- [WT32SC01PLUS.md](WT32SC01PLUS.md): the Wireless-Tag WT32-SC01 Plus, 3.5 inch.
- [WAVESHARE4B.md](WAVESHARE4B.md): the Waveshare ESP32-S3-Touch-LCD-4B.
- [WAVESHARE4V4.md](WAVESHARE4V4.md): the Waveshare ESP32-S3-Touch-LCD-4, revision 4.0 (without the "B").
- [WAVESHARE43C.md](WAVESHARE43C.md): the Waveshare ESP32-S3-Touch-LCD-4.3C, the 4.3-inch glass with the 7B's expander.
- [WAVESHARE5.md](WAVESHARE5.md): the Waveshare ESP32-S3-Touch-LCD-5, the 4.3-inch's board with 5-inch glass.
- [WAVESHAREP4.md](WAVESHAREP4.md): the Waveshare ESP32-P4-86-Panel-ETH-2RO, 4 inch, 720 × 720, using Wi-Fi.
- [WAVESHAREP47B.md](WAVESHAREP47B.md): the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, 7 inch, rev3 ESP32-P4.
- [WAVESHAREP47.md](WAVESHAREP47.md): the Waveshare ESP32-P4-WIFI6-Touch-LCD-7, 7 inch, 1280 × 720.
- [WAVESHARE101.md](WAVESHARE101.md): the Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1, 10.1 inch, 1280 × 800.
- [WAVESHARE7.md](WAVESHARE7.md): the Waveshare ESP32-S3-Touch-LCD-7, and the backlight mod that makes it dim.
- [WAVESHARE7B.md](WAVESHARE7B.md): the Waveshare ESP32-S3-Touch-LCD-7B.
- [HOSYOND40.md](HOSYOND40.md): the Hosyond 4-inch ESP32-32E.
- [FREENOVEFNK0104S.md](FREENOVEFNK0104S.md): the Freenove FNK0104S, 4 inch.
- [SENSECAP_INDICATOR.md](SENSECAP_INDICATOR.md): the Seeed SenseCAP Indicator D1 series with the GX panel, 4 inch.
- [SUNTON8048S070.md](SUNTON8048S070.md): the Sunton ESP32-8048S070, 7 inch.
- [ZX7D00CE01S.md](ZX7D00CE01S.md): the Panlee ZX7D00CE01S-V13, 7 inch.

## Recipes for changing the code

- [ARCHITECTURE.md](ARCHITECTURE.md): the one map of the firmware: its layers (the engine per chip, the glass per
  panel kind, the streams, pictures, the capability record, the governor, the audio owner, plugins), the hard rules
  between them with the measurement behind each, where the add-on meets them, and what is built against what is still
  a plan. Read it first.
- [CATALOGUE.md](CATALOGUE.md): what a tile of each entity type can do, and adding an entity type.
- [RESPONSIVE.md](RESPONSIVE.md): how one firmware fits every glass: looks, grids, the font set and card design rules.
- [MODULES.md](MODULES.md): tiers and modules, the parts of the UI only boards with 8 MB of flash or more get (a recipe).
- [ADDING_A_BOARD.md](ADDING_A_BOARD.md): adding a board, from its datasheet to the glass.
- [BOARD_RELEASES.md](BOARD_RELEASES.md): which boards a change reaches, and the firmware number it gets.
- [PROFILES.md](PROFILES.md): how a screen's YAML is put together from the core, looks, features and board files.
- [THEME.md](THEME.md): colours and Dark mode, from one table.
- [SETTINGS.md](SETTINGS.md): the screen settings, and adding one; a board's own settings (Extras), and adding one.
- [PAGES.md](PAGES.md): the page model, tile sizes, navigation, storage and the message rules.
- [KEPT_PAGES.md](KEPT_PAGES.md): pages kept whole, prepared ahead, and pictures kept until they change.
- [OPTIMISTIC.md](OPTIMISTIC.md): a finger's change shown at once and squared with Home Assistant afterwards, the one
  way every control does it.
- [CARD_PARTS.md](CARD_PARTS.md): a card built once and painted in place when a value changes, instead of built again.
- [PLUGINS.md](PLUGINS.md): plugins on the core's side: the plugin API, a plugin tile end to end, the plugins file, fetch.
- [REPORTS.md](REPORTS.md): the troubleshooting report of a screen: what it holds, what never leaves, where it goes, how a crash is read.
- [BUILDS.md](BUILDS.md): the one line every build waits in (updates, plugins, New screen, Firmware & USB), and how a
  build is followed.
- [TILE_MEMORY.md](TILE_MEMORY.md): how many tiles and pages a board holds, and the memory budget that says how many a
  layout really takes.
- [FLASH_LAYOUT.md](FLASH_LAYOUT.md): the partition table of a board with 4 MB of flash, and how a screen gets it
  without losing its settings (the technical side of UPDATING_4MB_SCREENS.md).
- [CAMERA.md](CAMERA.md): camera pictures and album covers, from Home Assistant to the screen.
- [PICTURE_ARCHITECTURE.md](PICTURE_ARCHITECTURE.md): the building blocks under pictures and cameras in the firmware,
  the app and the Screen camera plugin, their seams, and the layers they are moved into (a design with its recipe).
- [PLATFORM_PLAN.md](PLATFORM_PLAN.md): what Tessera builds next on the ESP32-P4 and in what order: the hardware layer
  (parts, the capability record `hw::caps()`, the audio owner), memory and live cameras with limits, the doorbell's
  talk-back prepared; each section says what is built and what is left.
- [DOORBELL.md](DOORBELL.md): a doorbell's ring from an automation, its camera live with sound on the P4 screens, and
  the Events page's wizards that add such automations to Home Assistant.
- [MAP.md](MAP.md): the map card, drawn by the add-on and sent as a picture.
- [ENERGY.md](ENERGY.md): the energy card, from Home Assistant's Energy settings to the diagram on the glass.
- [EMULATOR_ARCHITECTURE.md](EMULATOR_ARCHITECTURE.md): the editor's firmware preview, the firmware built to
  WebAssembly.
- [TRANSLATING.md](TRANSLATING.md): the languages, and adding one.
- [CALIBRATING.md](CALIBRATING.md): calibrating a resistive panel (the CYD) over USB, and the touch orientation it
  assumes.
- [SWIPE_PROFILE.md](SWIPE_PROFILE.md): measuring what a page swipe costs the main loop.
- [TESTING.md](TESTING.md): the levels of testing, from `tools/check.sh` to the whole chain and the upgrade from the last release.
- [RELEASING.md](RELEASING.md): the two branches, the weekly release, a hotfix, the flash budget and the ESPHome versions.
