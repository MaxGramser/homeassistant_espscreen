# Guition ESP32-S3 4-inch wallbox, 480 × 480

The **Guition 4848S040** has a board file of its own, next to the CYD's, for its
ST7701S RGB display and **GT911 capacitive touch**, ESP32-S3, 16 MB flash, and
8 MB octal PSRAM. The name/2mm wall plate also describes the enclosure; always
check the electronics. The board profile doesn't configure any relay; a wallbox sold with relays
can switch them through the screen's Override YAML ([Relays](#relays)).

Hardware source: the [ESPHome Guition board writeup](https://devices.esphome.io/devices/guition-esp32-s3-4848s040/)
and the built-in [ST7701S driver](https://esphome.io/components/display/st7701s/).
The panel configuration follows the original manufacturer demo, found physically clean;
see [the comparison](GUITION_FACTORY_REFERENCE.md). No local RGB driver
or periodic recovery script is needed. The GT911 uses unmirrored coordinates.

## Files

- `packages/boards/guition-4848s040.yaml`: the board file (hardware, the 480×480 sizes, the Guition's own parts); the
  interface itself is `packages/core.yaml`, shared with the CYD (docs/PROFILES.md).
- `packages/guition.yaml`: what a screen builds from over GitHub; `checkout/guition.yaml` is the same
  for a build from a clone of this repository (checkout/README.md).
- `<your-screen>.yaml`: the screen's own profile, written by Tessera, outside Git.
- `secrets.yaml`: local Wi-Fi/API/OTA settings, outside Git.
- `tools/verify_gt911.py`: physical pixel check; no resistive ADC calibration.

The 2.8-inch CYD profile stays separate. Don't flash that to the Guition, and don't
carry over `calibration.yaml` or the XPT2046 correction.

## Interface

### Mounting and screen rotation (runtime 0.2.9+)

Open the screen in the management page, open the **Screen settings** tab, and choose 0°, 90°,
180°, or 270° (clockwise) under **Rotation**. It applies at once; there is
nothing to save. After that, a firmware flash is no longer needed to change the
angle. The screen keeps the angle after a restart; it can also be changed on the
screen's own settings page (Screen) and, with firmware 0.2.49+, as
`select.<screen>_rotation` in Home Assistant.

The Guition is square, so every quarter turn keeps its canvas and its grid. Since firmware 0.2.80
every board turns: a half turn (180°) on any glass, because width, height, the grid and the whole
size table stay the same, and the quarter turns only on a square screen (docs/RESPONSIVE.md).

This uses native ESPHome/LVGL rotation for both display and touch, with no changes
to the panel initialization or GT911 mirroring. After mounting, physically check the
four corners and navigation; a render test doesn't test touches.
The CYD stays on its existing orientation with its own calibration.

Six tiles of **218 × 108 pixels** per page, 12px spacing, and the page buttons
below them. In Tessera Screen Manager, up to 48 tiles fit across up to
eight pages (firmware 0.2.62+; twenty over four pages before); the page buttons disappear
at six or fewer, or with **Page buttons** off, and the tiles then grow to 218 × 122
(firmware 0.2.69+).

**Four rows** (app 0.4.31, firmware 0.18.1): New screen asks how many tiles go on a page, two columns of three or of
four. Four rows fit eight smaller tiles on a page, about 11 mm high, for a screen with many switches; three keep them
larger and easier to read. The choice is one line in the screen's own YAML, `GRID_ROWS: "4"`, and the board brings the
eight cards that grid needs. A screen already built with three rows gets four by adding that line to its YAML and
installing it again; its saved layout moves on to four rows by itself, every tile on its own page, row and column.

<img src="images/guition-four-rows.png" width="100%" alt="The same thirteen tiles on the 4-inch Guition, rendered from the firmware: three pages with three rows each above, and three pages with four rows below, where the tiles are smaller and the same tiles need fewer pages">

The interface has a light gray background, white cards,
and colored domain icons; **Dark mode** (firmware 0.2.54+) turns it black with graphite
cards. From 0.2.10, you can choose a pastel background with
dark text per tile. Standby starts after ten minutes without touch by default and
is adjustable in the management page.
The backlight dims through ESPHome's own light transition (1.5 s to standby, 80 ms to
wake). Firmware 0.2.13-0.2.56 used the LEDC hardware fader (`backlight_fade.h`) instead;
0.2.57 went back to ESPHome's transition, because that fader reached into ESPHome's LEDC
output, which ESPHome 2026.8 no longer allows.

The existing tile actions, climate control, and vacuum card are preserved.
Every card type works in all 48 positions.

## New installation

Install the screen from Tessera ([EASY_SETUP.md](EASY_SETUP.md)): it writes the
screen's own profile with its name, Wi-Fi reference and unique keys, and flashes it
over USB. Choose the tiles afterwards in the app, not in the YAML.

Check the serial port and chip before uploading. On the tested board,
higher serial speeds proved unreliable when reading. Use 115200 baud:

```sh
python -m esphome config <your-screen>.yaml
python -m esphome compile <your-screen>.yaml
```

Flash via `esphome run` if the USB connection is reliable. For explicit
115200 baud, you can use the combined factory image. Replace both the
port and the device name in the path with your own values:

```sh
python -m esptool --chip esp32s3 --port <USB_PORT> --baud 115200 write-flash 0 .esphome/build/wallbox-kitchen/.pioenvs/wallbox-kitchen/firmware.factory.bin
```

The factory image belongs to this S3 profile and starts at address **0**, unlike
some classic ESP32 images. Keep a recovery copy before replacing
existing firmware if you might need it later. Keep binaries and logs local.

## Testing GT911 and orientation

The GT911 reports pixels directly. Usually no calibration is needed; a wrong
rotation/transform should not be papered over with the CYD affine wizard.

The board file fixes the GT911's range at 0 to 480 (firmware 0.9.1). Without it ESPHome reads
the range from the chip's own configuration, and some panels ship with a generic 1024 x 600
there: every touch then lands too far towards the top left corner, and the bottom right corner
reads as about 224, 383.

With a working Wi-Fi/API connection:

```sh
python diagnostics/control_ui.py touch_diagnostics --host wallbox-kitchen.local --name wallbox-kitchen
python tools/verify_gt911.py --port <USB_PORT> --output measurements-guition.json
python diagnostics/control_ui.py end_touch_diagnostics --host wallbox-kitchen.local --name wallbox-kitchen
```

Five crosshairs appear. The wizard asks for three separate taps per
point; press Enter first, then touch only the named crosshair. Error
at most 16px, spread at most 18px. The test doesn't send any HA actions.

Without Wi-Fi, you can first build with `-s CALIBRATION_ON_BOOT true`,
which shows the GT911 measurement screen right after the USB upload. After
checking, rebuild/reflash without that override. This compatibility name only
opens a pixel test; it doesn't perform any ADC calibration.

On the tested panel, the GT911 needs no transform: `TOUCH_SWAP_XY`, `TOUCH_MIRROR_X` and
`TOUCH_MIRROR_Y` are all `false` in the board file, and the default is `LVGL_ROTATION: "0"`.
For a different mounting, choose the rotation under **Screen settings** (or on the screen) and
give the wizard the same value, for example `--rotation 90`. Check every corner; only change
the GT911 `TOUCH_SWAP_XY` / `TOUCH_MIRROR_X` / `TOUCH_MIRROR_Y` if the physical measurement requires it.

## HA and acceptance

Once the screen is on your Wi-Fi, Tessera adds it to Home Assistant by itself; then choose its tiles in Tessera.

```sh
python diagnostics/run_ui_test.py --host wallbox-kitchen.local --name wallbox-kitchen
tools/check.sh
```

Also go through the physical checks, using the GT911 wizard instead of the XPT2046
calibration. Check the display, correct touches, pagination, long press,
climate and vacuum cards, real HA feedback,
standby, and recovery after a restart. A compile/render test doesn't replace
that physical check. The original CYD board's test outcome
says nothing about this new board.

## Relays

The Guition is also sold on a mains-powered wallbox base with one or three relays. The board profile leaves
them alone, so a screen without relays and one with them run the same firmware. To use the relays, add them in
the screen's **Override YAML** (docs/EASY_SETUP.md) and build the firmware again:

```yaml
switch:
  - platform: gpio
    id: relay_1
    name: "Relay 1"
    restore_mode: RESTORE_DEFAULT_OFF
    pin:
      number: GPIO40
      inverted: false
  - platform: gpio
    id: relay_2
    name: "Relay 2"
    restore_mode: RESTORE_DEFAULT_OFF
    pin:
      number: GPIO2
      inverted: false
  - platform: gpio
    id: relay_3
    name: "Relay 3"
    restore_mode: RESTORE_DEFAULT_OFF
    pin:
      number: GPIO1
      inverted: false
```

The pins are the ones on ESPHome's [device page](https://devices.esphome.io/devices/guition-esp32-s3-4848s040/)
for this board. The one-relay base only has the first. The relays are active-high, which a three-relay base
confirmed: with `inverted: true` every switch read the opposite of its relay. If a relay on your base still
clicks on while its switch reads off, change `inverted` to `true` for that relay. `RESTORE_DEFAULT_OFF` keeps
the state a relay had across a restart.

Each relay shows up in Home Assistant as a switch on the screen's device (`switch.<screen>_relay_1` and so on),
so it can go on a tile of the screen like any other switch, or in an automation. A tile switches through Home
Assistant: when Home Assistant is unreachable, the relay keeps its state but the tile can't change it. Rename the
relays with `name:` to what they switch, for example `"Ceiling light"`.

The base carries mains voltage. Have it wired by someone qualified, and check the relay's rating against the load.

## Inspecting the rendered interface

```sh
python diagnostics/capture_ui.py --host wallbox-kitchen.local --name wallbox-kitchen --output diagnostics/guition-home.png
```

This only takes an LVGL snapshot on request and sends a 240×240 preview
over the encrypted API. The temporary buffer is released after about 24 seconds.
The image verifies the renderer; it doesn't prove the physical
RGB signals, screen colors, or mounting orientation are correct. The render test
also checks that visible click areas fall within the 480×480 screen.

## Recovery copy of this test board

The original firmware in use, including bootloader, partition table,
and NVS, is stored locally as `diagnostics/guition-original-recovery.bin`.
The lengths of the five application segments determined the needed 4,788,224
bytes; this is not a copy of the full 16 MB flash. The stub verified the MD5
of every block read. SHA-256 of the complete recovery file:

```text
a656c793c422848b5ad72bc16545fb92c844b7dfba029f4e4399d22444a9e046
```

This copy is private, belongs only to the tested board, and is not
committed or exported. Recovery happens at address 0, with the same
115200-baud command as the factory image, but with this recovery file.

## RGB memory settings

The pixel clock is set to 16 MHz: on the test board, this removed the faint
flicker seen at the 12MHz setting. Code runs from the octal PSRAM (80 MHz,
`execute_from_psram`), and the panel otherwise uses ESPHome's own `st7701s`
defaults with the manufacturer's timings. The first profile also set a 64KB data
cache, 64-byte cache lines and RGB stream recovery on VSYNC, after
[Espressif's RGB LCD recommendations](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html);
those went when the native configuration proved clean without them
([the comparison](GUITION_FACTORY_REFERENCE.md)).
Physically check for occasional glitches under Wi-Fi/render load; a
software snapshot can't prove a disturbance in the panel signal.

The bounce buffer is refilled from an interrupt every 0.34 ms at this pixel
clock, so nothing may keep this core's interrupts off for longer. Walking the
PSRAM heap does (`heap_caps_get_largest_free_block`, 1.7 to 2.3 ms with a
layout loaded): it shifted a frame on every picture that loaded until firmware
0.3.2 stopped doing it while the glass is lit ([KEPT_PAGES.md](KEPT_PAGES.md)).
