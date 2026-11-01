# Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, experimental

This is the **ESP32-P4-WIFI6-Touch-LCD-7B**: a 7-inch 1024 x 600 IPS panel with an EK79007 MIPI-DSI driver, GT911
capacitive touch, an ESP32-P4 with 32 MB flash and 32 MB PSRAM, and an ESP32-C6 beside it for Wi-Fi. It is not the
ESP32-S3-Touch-LCD-7B ([its own page](WAVESHARE7B.md)): that one is an RGB panel behind a CH32V003 expander, while this
board drives its panel over MIPI-DSI and has no expander.

Community members ran this board file on boards with rev3 and with earlier silicon (see "Who tried what" below). The
project has not tried it on either, so the board is **experimental**.

## Which silicon

Waveshare sells this board with two revisions of the ESP32-P4 under one name, and firmware for one does not start on the
other. The first lines of the USB log say which one a board has: "chip revision: v3.x" is rev3, which Waveshare ships
now, and "chip revision: v1.3" the earlier silicon. **New screen** asks for it under **Chip revision**: v3 (the default,
`engineering_sample: false`) or v1 (`engineering_sample: true`). A screen set up before this choice existed sets it in
its own substitutions:

```yaml
substitutions:
  CHIP_REVISION: "v1"
```

Both have run this board file: rev3 first, and a board with earlier silicon with `engineering_sample: true` (picture,
touch and the rest worked; with the default rev3 build it did not start).

## Install

Update Tessera Screen Manager and choose **Waveshare · 7 inch, ESP32-P4-WIFI6-Touch-LCD-7B** (marked Experimental, the
one with the ESP32-P4) in **New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name,
Wi-Fi references and unique API/OTA keys. Keep an existing working profile if the board is already installed.

The board has two USB-C ports. The one the firmware flashes and logs over is the chip's own USB ("USB OTG", a `usbmodem`
device); its other port, "USB TO UART", is behind a bridge chip. A screen flashed over that one wants
`hardware_uart: UART0` under `logger:` in its Override YAML.

The remote package is `packages/wavesharep47b.yaml` and the checkout entry `checkout/wavesharep47b.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/wavesharep47b.yaml`. The board needs ESPHome 2026.9.0 or
newer: its display platform is the repository's copy of that version's driver.

## Layout and capabilities

- 1024 x 600 at 170 dpi, the standard look, four columns of four cells lying down and two columns of seven standing up.
  The panel is 1024 x 600 itself, so it lies down without a turn. If the picture is upside down for the way the board
  hangs, the Rotation setting (180°) turns the picture and the touch together.
- The backlight is a PWM pin (GPIO32, inverted) at 1 kHz: brightness is a percentage, and standby, night mode, Sleep,
  Wake and the alert's flashes are enabled.
- The GT911 reports pixel coordinates, with no calibration. Its axes are mirrored against the glass (`TOUCH_MIRROR_X`
  and `TOUCH_MIRROR_Y`), as Waveshare's BSP compensates for this panel. Its interrupt ends at a test point, so it is
  polled.
- Camera tiles, full-screen snapshots and the live camera of the P4 boards, camera alerts and media artwork use the
  shared PSRAM implementation.
- The board's own camera, experimental: an OV5647 on the MIPI-CSI connector, through the Screen camera plugin. See "The
  camera" below.
- A battery on the MX1.25 connector, experimental: **Battery Voltage** and **Battery Level**, and the battery in the
  top bar. See "The battery" below.
- The display runs on `components/mipi_dsi_v3`, ESPHome's driver with the DSI clock left to ESP-IDF: the stock driver's
  fixed clock stops rev3 silicon while the display starts, as on the Guition JC8012P4A1 V3.
- The speaker and the two microphones are the screen's audio, experimental: a media player in Home Assistant for
  announcements and music, Volume, Microphone, Microphone gain, Automatic gain and Echo cancellation under Screen
  settings, and what audio plugins (a voice assistant) need. See "Speaker and microphones" below.
- The microSD slot and the RS485 and CAN ports stay unused.

## Speaker and microphones

Waveshare's schematic wires the audio of this board exactly as on the
[Waveshare ESP32-P4 86 panel](WAVESHAREP4.md): an ES8311 for the speaker (its ADC is not wired), an ES7210 with the two
microphones on its MIC1 and MIC2 and the speaker circuit's output, through an attenuator, on its MIC3 as the echo
cancellation's reference, one I2S bus for both, and an NS4150B amplifier. So the board takes the 86 panel's audio
(`packages/hardware/wavesharep4-audio.yaml`): its codecs, its transport with echo cancellation by default, and its
Extras. [P4_AUDIO.md](P4_AUDIO.md) says how the echo cancellation works and how to choose the plain half-duplex
transport instead:

```yaml
substitutions:
  AUDIO_TRANSPORT: "i2s"
```

`P4_AUDIO_TRANSPORT`, the old name, still works in firmware 0.58 and goes in the release after.

This is **experimental**. The echo cancellation's libraries were first built for earlier silicon; this board file
builds them for rev3, where they resolve a newer esp_audio_effects (1.4.3, against 1.3.0~1 on earlier silicon).
Nobody has tried this file's audio on the board yet.

## The camera

Waveshare sells this board with an OmniVision OV5647 camera as a kit ("With OV5647 camera"), and its 15-pin MIPI-CSI
connector (two lanes, 1.0 mm pitch) takes the Raspberry Pi cameras of that sensor as well. The sensor's SCCB is the
board's I2C bus, GPIO7 and GPIO8, as in Waveshare's own camera app; the module clocks itself and the board wires no reset
or power-down pin. The board file names that bus in `CAMERA_I2C` (the feature `camera_sensor`, docs/PLUGINS.md), so the
**Screen camera** plugin fits this board. It finds the OV5647 with the driver in Espressif's own `esp_cam_sensor` and
makes it a camera of the screen's device in Home Assistant.

- **A board without a camera** fits Screen camera as well: `CAMERA_I2C` says where a camera answers, not that one is
  there. Without a sensor the camera only logs that it found none.
- **Colours and turning need Screen camera's OV5647 support.** Espressif's driver starts the sensor with one of its two
  mirror bits (register 0x3821 0x03), and the colour order it declares (GBRG) only holds with both (0x07): without it
  the picture is purple and orange shows as green. And the sensor's flips, which turn the picture for a screen hung
  upside down, move its colours: red and blue swap. Screen camera 0.6.16 and later set the second bit and move the
  sensor's window by a pixel for each flip (its `components/ov5647`); an earlier Screen camera shows these colours.
- The camera stands as the glass does (`CAMERA_ORIENTATION` 0): with the screen turned 180 degrees, the picture turns
  with it.

## The battery

The board charges a single lithium cell on its MX1.25 battery connector (forward polarity) with an ETA6098 charger.
Waveshare's schematic puts the cell's voltage on GPIO20 (ADC1) through a divider of 200K over 100K (R92 and R93), so the
pin sees a third of it. The board file reads it (`features/battery-adc.yaml`, `BATTERY_DIVIDER: "3.0"`) and turns it
into a level (`features/battery-voltage.yaml`): a straight line from 3.3 V (empty) to 4.2 V (full). Home Assistant shows
**Battery Voltage** and **Battery Level**, and the editor offers the battery in the top bar ([BATTERY.md](BATTERY.md)).

- The charger's status pin only lights an LED on the board, so the screen cannot tell whether the cell charges: the top
  bar never shows the lightning bolt.
- Without a cell the pin reads next to nothing and the level stays unknown instead of 0 %.
- A curve measured on your own cell gives a better level than the straight line; `BATTERY_LEVEL_FORMULA` in the
  screen's own substitutions replaces it (docs/BATTERY.md).
- Tried on a board with a cell on USB: 4.13 V and 94 %. Please report the voltage it reads without a cell.

## Who tried what

- [@tomvanoosterwyck](https://github.com/tomvanoosterwyck) ran this board file on a board with rev3 silicon
  ("chip revision: v3.2", 32 MB flash) (#271): a stable picture in the right colours lying down, tiles and pages, taps in
  the right places with the mirrored axes, the brightness setting across its range, and standby with the wake by touch.
- A second owner ran a board file of their own on a board with PCB revision 1.1
  ([wish 136](https://tessera-maxgramser.on-forge.com/wishlist/136)): display, backlight, Wi-Fi, the API, touch targets
  with the X axis mirrored, and an update over Wi-Fi. That file used ESPHome's stock display driver and was built for
  the earlier silicon, so boards of both revisions are out there.
- [@aalaei](https://github.com/aalaei) ran this board file on a board with earlier silicon ("chip revision: v1.3"):
  it did not start with the rev3 build, and starts with the v1 choice (`engineering_sample: true`), joins Wi-Fi and
  Home Assistant, with the voice assistant and other plugins. The battery read 4.13 V (94 %) with a cell on USB, and
  the OV5647 answered on the touch bus and gave pictures through Screen camera, in the right colours upright and turned
  with Screen camera's OV5647 component (see "The camera").
- [@Axellum](https://github.com/Axellum) had the speaker play and the microphone capture on this board with a
  configuration of their own (#271).

Not tried yet with this file: the speaker and microphones, echo cancellation, the battery without a cell, standing up,
and a full page of tiles over a long run.

## Hardware references

- [Waveshare documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-7B) and its
  [schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-7B/ESP32-P4-WIFI6-Touch-LCD-7B.pdf).
- Waveshare's own BSP ([Waveshare-ESP32-components](https://github.com/waveshareteam/Waveshare-ESP32-components),
  `esp32_p4_wifi6_touch_lcd_7b`) is the reference for the pins below.
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/): the panel is ESPHome's own
  `model: WAVESHARE-ESP32-P4-WIFI6-TOUCH-LCD-7B`, the EK79007 at 1024 x 600 on two lanes.
- The pins:
  - Wi-Fi: ESP32-C6 over four-bit SDIO, reset GPIO54, clock GPIO18, command GPIO19, data GPIO14 to GPIO17.
  - The chip's internal regulator on channel 3 at 2.5 V for the MIPI-DSI PHY.
  - I2C: SDA GPIO7, SCL GPIO8, 400 kHz, for the GT911 and the audio codecs (ES8311 at 0x18, ES7210 at 0x40).
  - Touch: GT911, reset GPIO23, polled.
  - Backlight: GPIO32, PWM, inverted.
  - Display reset: GPIO33.
  - Camera: OV5647 on the MIPI-CSI connector, SCCB on the same I2C bus (GPIO7 and GPIO8), its own clock, no reset or
    power-down pin.
  - Battery: GPIO20 (ADC1), a third of the cell's voltage through 200K over 100K. The ETA6098 charger's status pin
    drives an LED only.
  - Audio: I2S MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, speaker data GPIO9, microphone data GPIO11; amplifier enable
    GPIO53, high for on, with a pull-down that keeps it off at reset.
- The 86 panel's two relays are not on this board: its GPIO32 is this board's backlight.

## What to report while testing

1. The silicon revision from the first lines of the USB log, a successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes, a restart from the screen's settings, an update
   over the air and a cold start.
3. Taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode.
5. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes, and with
   Screen camera the OV5647's picture in Home Assistant.
6. With a cell: Battery Voltage against a meter, on the battery and on USB, and the level in the top bar.
7. A text-to-speech announcement and music on the screen's media player, the Volume setting from low to high, and
   whether the speaker stays quiet between sounds.
8. The microphones, with a voice assistant plugin: whether the wake word is heard from across the room, also while
   music plays, and the **Echo cancellation status** entity (Enabled, Bypass, Starting or Error).
9. `sensor.<screen>_heap_free` with a full layout, any reset, Wi-Fi drop or I2C error, and how long the screen stayed
   running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
