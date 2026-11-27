# Seeed reTerminal Sticky

A 3.97-inch 800 x 480 panel of e-paper with GT911 capacitive touch, on an ESP32-S3R8 with 32 MB of flash and 8 MB of
octal PSRAM, running on a 750 mAh battery. It is the first board whose glass is paper: it prints in black and white,
keeps its page without a light, and takes a part of a second to change (docs/PAPER.md has how the firmware treats such
a glass). Board key `reterminalsticky`, status experimental, board file `packages/boards/seeed-reterminal-sticky.yaml`.
The pins come from Seeed's hardware overview and its ESPHome example for the board.

## Which board

Seeed ships the reTerminal Sticky with one of two panel controllers. This board file drives the **SSD1677** panel,
through ESPHome's `epaper_spi` model `Seeed-reTerminal-Sticky`, and that is the one the project tried. The other, an
**SSD2677**, is not driven by ESPHome yet: a unit with that panel is not covered.

The board needs ESPHome 2026.11.0 or later, and its board file says so (`min_version`): from that version ESPHome
drives this panel with a partial refresh that leaves the unchanged pixels alone, and it brings the fuel gauge's
component.

## What it has, and where Tessera configures it

| Part | Chip, pins | In Tessera |
|---|---|---|
| Panel | SSD1677 over SPI: clock GPIO13, MOSI GPIO14, MISO GPIO12; its other pins come with ESPHome's model | `epaper_spi` as `paper_panel`, under the paper glass of `features/paper.yaml` |
| Touch | GT911 at 0x5D on `touch_bus` (SCL GPIO2, SDA GPIO3, 400 kHz), interrupt GPIO21, reset GPIO41, supply GPIO42 | `features/capacitive-touch.yaml`, with `TOUCH_SWAP_XY` |
| Power hold | GPIO45 and GPIO46, both held high | the board file |
| Charger | BQ25616, charging while GPIO39 is low | the board file switches it on |
| Battery | BQ27220 fuel gauge on `board_bus` (SCL GPIO0, SDA GPIO1, 400 kHz) | level, voltage and current every 30 s; the level is what the top bar shows (docs/BATTERY.md) |
| Keys | three: GPIO5, GPIO6 and GPIO4, each low while pressed | `features/page-keys.yaml`: the page before, the next page, home |
| Buzzer | GPIO48 | `features/buzzer.yaml`: a tick under a finger and a key |
| Temperature, humidity | SHT40 at 0x44 on `board_bus` | two sensors in Home Assistant, every 60 s |
| Motion | LSM6DS3TR-C on `board_bus`, read every 100 ms | Wake when moved, `features/wake-when-moved.yaml`, with its switch under Extras |
| USB | a CH343 bridge on UART0 | the log, and how the board is flashed |
| Clock | PCF8563 on `board_bus` | not used |
| Microphone | | not used |
| microSD slot | on the panel's SPI bus | not used |

## Things to know

- **Strapping pins carry buses and power.** GPIO0 and GPIO3 are strapping pins of the ESP32-S3 and are wired to the
  two I2C buses on this board, GPIO45 and GPIO46 to its power latch. The board file tells ESPHome so
  (`ignore_strapping_warning`); the pins only decide how the chip starts and are free after that.
- **The power hold.** On its battery the board stays on only while GPIO45 and GPIO46 are high. The board file sets
  both before anything else is set up (`setup_priority: 1100`).
- **The touch panel needs its supply before its bus is set up.** Without power the GT911 holds its bus low, and a bus
  set up then finds no chip. The supply on GPIO42 goes high with the power hold, before the buses.
- **The touch panel's axes are swapped against the panel's.** The touch chip counts its x along the panel's short
  side and its y along the long one, with no mirror: a tap in the corner at the panel's (800, 0) read (11, 788) in the
  chip's own numbers. The board file states it once (`TOUCH_SWAP_XY`); do not add a second correction in an Override
  YAML. A test tile on the diagonal hides a swap, so try a tap in each corner.
- **The panel is never turned.** LVGL turns the picture and the touch together, as on every other board, and the
  e-paper driver is left as it lies.
- **LVGL draws the whole glass into one buffer** in PSRAM (`LVGL_BUFFER_SIZE: "100%"`), so a refresh of the panel is
  one picture and never a row of strips.
- **Flashing.** The board is flashed through its USB port, over the CH343 bridge. It works at 460800 baud.
- **The battery.** The fuel gauge works out the level itself. Battery Charging is on while the gauge sees more than
  20 mA flow into the battery. Battery Voltage and Battery Current are diagnostic sensors.
- **The air sensor reads a little warm while the board charges.**
- **32 MB of flash** needs ESP-IDF's experimental features for its update slots, which the board file enables.

## How it hangs

Lying down, the panel is 800 wide and 480 high: two columns of two cells. Standing up, with
the USB port below, is a quarter turn: one column of four cells. The way a screen hangs is chosen in New screen or
with Grid beside the pages in the editor, as on every board whose glass is not square, and the touch turns with the
picture.

## The keys and the buzzer

The two page keys turn one page, as a swipe from the edge does. The home key, pressed, brings the first page with
everything closed; held for 0.7 s it sends the screen to standby. On a page at rest a key is used at once, as a finger
is; under a screensaver the first press only wakes the screen. Each key is also a binary sensor in Home Assistant
(Key previous, Key next, Key home), for an automation of its own.

The buzzer answers before the glass can: a tick of 20 ms at 2700 Hz the moment a finger lands on something that takes
it or a key is pressed. The switch **Tap sound** turns it off: under Extras on the screen's own settings page, under
Screen settings in the app, and in Home Assistant. The buzzer sits on a bare pin and
only ticks; it is not the screen's speaker and plays none of the app's sounds.

## On the glass

- Pages print in black and white. A change is a partial refresh of about 0.7 s. A whole refresh, which flashes the
  panel and takes its traces off, takes 1.8 to 2.0 s: it comes at the first print after a start, and once partial
  refreshes have left enough traces, when the screen has been left alone for half a minute.
- A slider is a row of blocks with a minus and a plus (docs/PAPER.md, "A level").
- Nothing moves by itself (docs/PAPER.md, "A still glass"): a clock has no second hand, a timer counts down in whole
  minutes and in steps of ten seconds inside its last, and a camera tile takes a new still once a minute.
- There is no backlight: no brightness, no night level, and an alert does not blink. Standby is rest: the page stays
  readable, or the screensaver shows where one is set.
- Pictures (camera tiles, an alert's snapshot, media artwork) are configured and print as a raster of dots.

## Tried on the glass

On the project's own unit with the SSD1677 panel, with ESPHome 2026.11.0: it boots, joins Home Assistant and takes a
layout from the app. Measured or seen on its glass, each behind a rule of docs/PAPER.md: the time of a whole and of a
partial refresh; greys of 25, 50 and 75 % and a word at 40 % as rasters; soft edges that frayed when rastered; a glyph
that fell away on a ground of raster; and a tap in each corner, read from the screen's own log, for the touch
panel's axes.

Not used: the microphone, the microSD slot and the clock. Not tried: a unit with the SSD2677 panel.

## What to report while testing

1. Which panel the unit has, a successful boot and appearance in Tessera.
2. A tap near each corner and in the middle, lying down and standing up.
3. The three keys, the tick of the buzzer, and Wake when moved.
4. How the page looks after an hour of use: traces that stay, and whether the whole refresh at rest takes them off.
5. The battery's level against what the board does, and how long a charge lasts.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
