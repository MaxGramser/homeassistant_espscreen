# Seeed reTerminal E1001

A 7.5-inch 800 x 480 panel of black and white e-paper, without touch, on an ESP32-S3 with 32 MB of flash and 8 MB of
octal PSRAM, running on a 2000 mAh battery. Its glass is paper as the reTerminal Sticky's (docs/PAPER.md), and it is
the first board that takes no finger: its pages turn with the three keys on its top. Board key `reterminale1001`,
status experimental, board file `packages/boards/seeed-reterminal-e1001.yaml`. The pins come from Seeed's wiki for the
board: its getting started page and its ESPHome cookbooks for the display, the keys and the battery, and the clock, the
card and the microphone.

The board is built and its firmware compiles. It has not been tried on a unit of the project's own yet: everything
under "On the glass" is what the firmware does on the Sticky's paper, not what has been seen on this panel.

The board needs ESPHome 2026.11.0 or later, and its hardware file `packages/hardware/seeed-reterminal-e1001.yaml` says
so (`min_version`): the paper glass asks the panel for a whole refresh between partial ones, which ESPHome's e-paper
driver has from that version.

## What it has, and where Tessera configures it

| Part | Chip, pins | In Tessera |
|---|---|---|
| Panel | UC8179 over SPI: clock GPIO7, MOSI GPIO9, MISO GPIO8; CS GPIO10, DC GPIO11, reset GPIO12, busy GPIO13 come with ESPHome's model | `epaper_spi` model `Seeed-reTerminal-E1001` as `paper_panel`, under the paper glass of `features/paper.yaml` |
| Touch | none | `features/no-touch.yaml`, a touchscreen of the platform `no_touch` that never reports |
| Keys | three on the top: left GPIO5, right GPIO4, green GPIO3, each low while pressed | `features/page-keys.yaml`: the page before, the next page, home |
| Buzzer | GPIO45 | `features/buzzer.yaml`: a tick under a key |
| Battery | its voltage on GPIO1 through a divider of two, read while GPIO21 is high | `features/battery-adc.yaml` and `features/battery-voltage.yaml`, every 60 s; the level is what the top bar shows (docs/BATTERY.md) |
| Temperature, humidity | SHT40 at 0x44 on `touch_bus` (SDA GPIO19, SCL GPIO20; named as every board's bus, though no touch panel is on it) | two sensors in Home Assistant, every 60 s |
| USB | a CH340K bridge on UART0 | the log, and how the board is flashed |
| Status LED | green, GPIO6 | not used |
| Clock | PCF8563 at 0x51 on `touch_bus` | not used |
| Microphone | PDM: power GPIO38, clock GPIO42, data GPIO41 | not used |
| microSD slot | on the panel's SPI bus, power GPIO16, card detect GPIO15 | not used, its power stays off |

## A screen without a finger

Everything the firmware draws is the same as on every other board. What needs a finger is not there:

- **The keys turn the pages.** The left key is the page before, the right key the next. The green key, pressed, brings
  the first page with everything closed; held for 0.7 s it sends the screen to standby. In standby the first press of
  a key only wakes the screen. Each key is also a binary sensor in Home Assistant (Key previous, Key next, Key home),
  for an automation of its own.
- **A tile shows and is not pressed.** A lamp, a thermostat or a player is changed in Home Assistant, in the app or on
  another screen, and the tile follows.
- **The settings are changed in the app and in Home Assistant.** The hold on the top bar that opens the screen's own
  settings page needs a finger. Every setting is under Screen settings in the app and an entity in Home Assistant.
- **Tap sound** turns the buzzer's tick off, under Screen settings in the app and in Home Assistant.

## Things to know

- **Strapping pins.** GPIO3 (the green key) and GPIO45 (the buzzer) are strapping pins of the ESP32-S3. ESPHome warns
  about them at a build; the pins only decide how the chip starts and are free after that.
- **The log goes over UART0** (`logger: hardware_uart: UART0`). The ESP32-S3's own USB would take GPIO19 and GPIO20,
  the board's I2C bus.
- **The battery's voltage** reaches its pin only while GPIO21 is high, so the hardware file holds it high from the start.
  The level is a straight line from 3.3 V to 4.15 V. A lithium cell is not straight, so the level reads low in the
  middle until a curve measured on this battery replaces it (docs/BATTERY.md).
- **A microSD card in the slot may disturb the panel's bus**, as Seeed's own cookbook says. Test without a card.
- **The power switch** on the back turns the board off. Flash it with the switch on: Seeed's wiki says a board that
  sleeps or is off cannot be flashed.
- **32 MB of flash** needs ESP-IDF's experimental features for its update slots, which the hardware file enables.

## What is still unknown

ESPHome's driver for this panel is new. An ESPHome issue opened on 2026-11-27 (esphome/esphome#23367) reports that on
ESPHome 2026.11.1 none of its refresh modes gave a right picture on that unit: a plain whole refresh showed grey noise,
a fast whole refresh had black and white the other way round, and a partial refresh was shifted sideways and wrapped
at the edge. Another project drives the same panel with the same driver and its partial refresh without such
complaints. The paper glass uses the partial refresh with a fast whole one between, so the first test on a unit says
which of the two holds:

1. Does the first page print at all, and the right way round (black ink on white paper)?
2. A page turn with the right key: does the new page stand where it should, or is it shifted sideways?
3. After a few page turns, what traces stay, and does the whole refresh as the screen goes to standby take them off?

If the colours are the other way round or the picture is shifted, it is the driver, not the layout: report it with a
photo. docs/open-issues/reterminal-e1001-refresh.md keeps what is known.

## How it hangs

Lying down, the panel is 800 wide and 480 high: four columns of four cells, the grid of the other 7-inch 800 x 480
glass. On Seeed's stand it stays lying down. Standing up is a quarter turn: two columns of seven cells.

## What to report while testing

1. That it boots, joins Home Assistant and takes a layout from the app.
2. The three checks under "What is still unknown", with a photo of the glass.
3. The three keys and the tick of the buzzer.
4. The battery's level against the voltage, and how long a charge lasts.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
