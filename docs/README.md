# The documents in docs/

## For users

- [EASY_SETUP.md](EASY_SETUP.md): install Tessera Screen Manager, add a screen, flash it and give it tiles.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md): what to check when a screen, its touch or its way into Home Assistant misbehaves.
- [DOCKER.md](DOCKER.md): Tessera Screen Manager on Home Assistant Container, without the App store.
- [BEDSIDE.md](BEDSIDE.md): the bedside clock, a whole-page clock with keys for the night.
- [SCREENSAVER.md](SCREENSAVER.md): what a screen shows in standby instead of its dimmed tiles: a cover, a camera or the clock.
- [BATTERY.md](BATTERY.md): a screen's battery in its top bar, and how a board or your own YAML measures it (also a
  recipe for the code).
- [UPDATING_4MB_SCREENS.md](UPDATING_4MB_SCREENS.md): the CYD and the Hosyond get more room for firmware, and what to do
  if you flash them yourself.

## Per board

- [GUITION.md](GUITION.md): the Guition 4848S040, 4 inch, 480 × 480: hardware, mounting, touch and rotation.
- [GUITION_FACTORY_REFERENCE.md](GUITION_FACTORY_REFERENCE.md): the manufacturer's own demo on the 4848S040, as a
  reference for the panel's driving.
- [JC3248W535.md](JC3248W535.md): the Guition JC3248W535, 3.5 inch.
- [JC1060P470.md](JC1060P470.md): the Guition JC1060P470 and its V2, 7 inch, ESP32-P4.
- [JC8012P4A1.md](JC8012P4A1.md): the Guition JC8012P4A1, 10.1 inch, ESP32-P4, with its V2 and V3.
- [TAB5.md](TAB5.md): the M5Stack Tab5, 5 inch, ESP32-P4, for the confirmed ST7121 variant.
- [WAVESHARE35.md](WAVESHARE35.md): the Waveshare ESP32-S3-Touch-LCD-3.5.
- [WAVESHARE4B.md](WAVESHARE4B.md): the Waveshare ESP32-S3-Touch-LCD-4B.
- [WAVESHARE5.md](WAVESHARE5.md): the Waveshare ESP32-S3-Touch-LCD-5, the 4.3-inch's board with 5-inch glass.
- [WAVESHARE7.md](WAVESHARE7.md): the Waveshare ESP32-S3-Touch-LCD-7, and the backlight mod that makes it dim.
- [WAVESHARE7B.md](WAVESHARE7B.md): the Waveshare ESP32-S3-Touch-LCD-7B.
- [HOSYOND40.md](HOSYOND40.md): the Hosyond 4-inch ESP32-32E.
- [SUNTON8048S070.md](SUNTON8048S070.md): the Sunton ESP32-8048S070, 7 inch.

## Recipes for changing the code

- [CATALOGUE.md](CATALOGUE.md): what a tile of each entity type can do, and adding an entity type.
- [RESPONSIVE.md](RESPONSIVE.md): how one firmware fits every glass: looks, grids, the font set and card design rules.
- [ADDING_A_BOARD.md](ADDING_A_BOARD.md): adding a board, from its datasheet to the glass.
- [BOARD_RELEASES.md](BOARD_RELEASES.md): which boards a change reaches, and the firmware number it gets.
- [PROFILES.md](PROFILES.md): how a screen's YAML is put together from the core, looks, features and board files.
- [THEME.md](THEME.md): colours and Dark mode, from one table.
- [SETTINGS.md](SETTINGS.md): the screen settings, and adding one.
- [PAGES.md](PAGES.md): the page model, tile sizes, navigation, storage and the message rules.
- [KEPT_PAGES.md](KEPT_PAGES.md): pages kept whole, prepared ahead, and pictures kept until they change.
- [TILE_MEMORY.md](TILE_MEMORY.md): how many tiles and pages a board holds, and the memory budget that says how many a
  layout really takes.
- [FLASH_LAYOUT.md](FLASH_LAYOUT.md): the partition table of a board with 4 MB of flash, and how a screen gets it
  without losing its settings (the technical side of UPDATING_4MB_SCREENS.md).
- [CAMERA.md](CAMERA.md): camera pictures and album covers, from Home Assistant to the screen.
- [MAP.md](MAP.md): the map card, drawn by the add-on and sent as a picture.
- [ENERGY.md](ENERGY.md): the energy card, from Home Assistant's Energy settings to the diagram on the glass.
- [EMULATOR_ARCHITECTURE.md](EMULATOR_ARCHITECTURE.md): the editor's firmware preview, the firmware built to
  WebAssembly.
- [TRANSLATING.md](TRANSLATING.md): the languages, and adding one.
- [CALIBRATING.md](CALIBRATING.md): calibrating a resistive panel (the CYD) over USB, and the touch orientation it
  assumes.
- [SWIPE_PROFILE.md](SWIPE_PROFILE.md): measuring what a page swipe costs the main loop.
- [TESTING.md](TESTING.md): the levels of testing, from `tools/check.sh` to the whole chain.
- [RELEASING.md](RELEASING.md): the release steps, the flash budget and the ESPHome versions.
